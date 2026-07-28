#!/usr/bin/env python3
"""Build and verify Orkela's TUF 1.0 update repository.

This tool is release infrastructure, never a player runtime dependency.
Private keys are accepted only as explicit filesystem inputs and are never
written into an artifact or source tree by the build command.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from cryptography.hazmat.primitives.serialization import load_pem_private_key
from securesystemslib.signer import CryptoSigner
from tuf.api.metadata import (
    MetaFile,
    Metadata,
    Root,
    Snapshot,
    TargetFile,
    Targets,
    Timestamp,
)
from tuf.api.exceptions import DownloadHTTPError
from tuf.api.serialization.json import JSONSerializer
from tuf.ngclient import Updater
from tuf.ngclient.fetcher import FetcherInterface


ROLE_NAMES = ("root", "targets", "snapshot", "timestamp")
SERIALIZER = JSONSerializer(compact=False)
SOURCE_ROOT = Path(__file__).parents[2].resolve()
KEY_ID_PATTERN = re.compile(r"[0-9a-f]{64}")
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
ARTIFACT_POLICY = {
    ("windows", "x64"): {"installer", "msix"},
    ("windows", "arm64"): {"installer", "msix"},
    ("ubuntu", "x64"): {"deb"},
    ("debian", "x64"): {"deb"},
    ("freebsd", "x64"): {"pkg"},
    ("macos", "x86_64"): {"pkg"},
    ("macos", "arm64"): {"pkg"},
}
MAXIMUM_METADATA_LIFETIME = {
    "stable": {
        "targets": 90 * 24 * 60 * 60,
        "snapshot": 7 * 24 * 60 * 60,
        "timestamp": 24 * 60 * 60,
    },
    "beta": {
        "targets": 45 * 24 * 60 * 60,
        "snapshot": 3 * 24 * 60 * 60,
        "timestamp": 24 * 60 * 60,
    },
    "nightly": {
        "targets": 7 * 24 * 60 * 60,
        "snapshot": 24 * 60 * 60,
        "timestamp": 6 * 60 * 60,
    },
}


def parse_utc(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def semantic_version_key(value: str) -> tuple:
    match = SEMVER_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError(f"invalid semantic version: {value}")
    prerelease = match.group(4)
    if prerelease is None:
        prerelease_key = (1, ())
    else:
        identifiers = []
        for identifier in prerelease.split("."):
            if identifier.isdigit():
                if len(identifier) > 1 and identifier.startswith("0"):
                    raise ValueError(
                        f"invalid numeric prerelease identifier: {value}"
                    )
                identifiers.append((0, int(identifier)))
            else:
                identifiers.append((1, identifier))
        prerelease_key = (0, tuple(identifiers))
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
        prerelease_key,
    )


def root_channel(root: Root) -> str:
    orkela = root.unrecognized_fields.get("orkela")
    if not isinstance(orkela, dict):
        raise ValueError("trusted root has no Orkela channel binding")
    channel = orkela.get("channel")
    if channel not in ("stable", "beta", "nightly"):
        raise ValueError("trusted root has an invalid Orkela channel")
    return str(channel)


def root_uses_development_keys(root: Root) -> bool:
    orkela = root.unrecognized_fields.get("orkela")
    if not isinstance(orkela, dict) or not isinstance(
        orkela.get("test_keys"),
        bool,
    ):
        raise ValueError(
            "trusted root must explicitly declare its test-key profile"
        )
    return bool(orkela["test_keys"])


def validate_root_profile(
    root: Root,
    channel: str,
    allow_development_test_keys: bool,
) -> None:
    if root_channel(root) != channel:
        raise ValueError("trusted root is bound to another release channel")
    if not root.consistent_snapshot:
        raise ValueError("Orkela requires consistent_snapshot=true")
    if root_uses_development_keys(root) and not allow_development_test_keys:
        raise ValueError(
            "development test-key root is forbidden without an explicit "
            "test-only override"
        )


def private_key_path(directory: Path, role: str, key_id: str) -> Path:
    if not KEY_ID_PATTERN.fullmatch(key_id):
        raise ValueError(f"invalid TUF key ID: {key_id}")
    root = directory.resolve()
    path = (root / f"{role}-{key_id}.pem").resolve()
    if not path.is_relative_to(root):
        raise ValueError("private key path escaped its signer directory")
    return path


def require_external_key_store(directory: Path) -> None:
    if directory.resolve().is_relative_to(SOURCE_ROOT):
        raise ValueError("private key store must be outside the source tree")


def write_private_key(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def write_metadata(path: Path, metadata: Metadata) -> bytes:
    encoded = metadata.to_bytes(SERIALIZER)
    with path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return encoded


def sign_with_role(
    metadata: Metadata,
    root: Root,
    role: str,
    key_directories: list[Path],
) -> None:
    role_definition = root.roles[role]
    authorized_names = {
        f"{role}-{key_id}.pem"
        for key_id in role_definition.keyids
        if KEY_ID_PATTERN.fullmatch(key_id)
    }
    for directory in key_directories:
        supplied = list(directory.glob("*.pem"))
        unexpected = [
            path.name for path in supplied if path.name not in authorized_names
        ]
        if unexpected:
            raise ValueError(
                f"{role} signer directory contains unauthorized PEM files"
            )
        if len(supplied) > 1:
            raise ValueError(
                f"{role} signer directory violates one-key custody"
            )
    accepted = 0
    for key_id in sorted(role_definition.keyids):
        paths = [
            private_key_path(directory, role, key_id)
            for directory in key_directories
        ]
        present = [path for path in paths if path.is_file()]
        if not present:
            continue
        if len(present) != 1:
            raise ValueError(f"duplicate private key custody for {key_id}")
        path = present[0]
        private_key = load_pem_private_key(path.read_bytes(), password=None)
        signer = CryptoSigner(private_key)
        if signer.public_key.keyid != key_id:
            raise ValueError(f"{path} does not match authorized key {key_id}")
        metadata.sign(signer, append=accepted > 0)
        accepted += 1
    if accepted < role_definition.threshold:
        raise ValueError(
            f"{role} requires {role_definition.threshold} signatures, "
            f"but only {accepted} authorized private keys were supplied"
        )
    Metadata(root).verify_delegate(role, metadata)


def bootstrap(args: argparse.Namespace) -> None:
    if not getattr(args, "development_test_keys", False):
        raise ValueError(
            "test-key bootstrap requires --development-test-keys; "
            "production roots require an offline witnessed ceremony"
        )
    root_path = args.root
    key_directory = args.key_directory
    if root_path.exists() or key_directory.exists():
        raise ValueError("refusing to overwrite an existing root or key store")
    require_external_key_store(key_directory)
    resolved_root = root_path.resolve()
    resolved_keys = key_directory.resolve()
    if (
        resolved_root.is_relative_to(resolved_keys)
        or resolved_keys.is_relative_to(resolved_root.parent)
    ):
        raise ValueError(
            "trusted root and private key store must use disjoint directories"
        )

    root_path.parent.mkdir(parents=True, exist_ok=True)
    key_directory.mkdir(parents=True)
    root = Metadata(
        Root(
            version=1,
            expires=args.root_expires,
            consistent_snapshot=True,
            unrecognized_fields={
                "orkela": {
                    "channel": args.channel,
                    "test_keys": True,
                }
            },
        )
    )
    signers: dict[str, list[CryptoSigner]] = {}
    for role in ROLE_NAMES:
        count = 3 if role in ("root", "targets") else 1
        signers[role] = []
        for _ in range(count):
            signer = CryptoSigner.generate_ed25519()
            signers[role].append(signer)
            root.signed.add_key(signer.public_key, role)
            write_private_key(
                private_key_path(
                    (
                        key_directory
                        / role
                        / (
                            f"custodian-{len(signers[role])}"
                            if role in ("root", "targets")
                            else "online"
                        )
                    ),
                    role,
                    signer.public_key.keyid,
                ),
                signer.private_bytes,
            )
    root.signed.roles["root"].threshold = 2
    root.signed.roles["targets"].threshold = 2
    for index, signer in enumerate(signers["root"]):
        root.sign(signer, append=index > 0)
    write_metadata(root_path, root)
    write_metadata(root_path.parent / "1.root.json", root)


def load_release_manifest(path: Path, artifact_directory: Path) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "org.scenelith.orkela.update.v1":
        raise ValueError("unsupported release manifest schema")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("release manifest has no artifacts")
    if manifest.get("channel") not in ("stable", "beta", "nightly"):
        raise ValueError("release manifest has an invalid channel")
    if not re.fullmatch(r"[0-9a-f]{40}", str(manifest.get("commit", ""))):
        raise ValueError("release manifest must contain a full source commit")
    semantic_version_key(str(manifest.get("version", "")))
    parse_utc(str(manifest.get("published_at", "")))
    names: set[str] = set()
    artifact_root = artifact_directory.resolve()
    for record in artifacts:
        if not isinstance(record, dict):
            raise ValueError("artifact record must be an object")
        name = str(record.get("name", ""))
        if (
            not name
            or Path(name).name != name
            or "/" in name
            or "\\" in name
        ):
            raise ValueError("artifact name must be a plain filename")
        if name in names:
            raise ValueError(f"duplicate artifact name: {name}")
        names.add(name)
        for field in ("arch", "kind", "platform"):
            token = record.get(field)
            if (
                not isinstance(token, str)
                or not token
                or any(character.isspace() for character in token)
            ):
                raise ValueError(f"artifact {field} must be a token")
        policy_key = (record["platform"], record["arch"])
        if (
            policy_key not in ARTIFACT_POLICY
            or record["kind"] not in ARTIFACT_POLICY[policy_key]
        ):
            raise ValueError(
                "artifact platform/architecture/kind is not allowlisted"
            )
        digest = record.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(
            r"[0-9a-f]{64}",
            digest,
        ):
            raise ValueError(f"artifact SHA-256 is invalid for {name}")
        url = urlparse(str(record.get("url", "")))
        if (
            url.scheme != "https"
            or not url.netloc
            or Path(unquote(url.path)).name != name
        ):
            raise ValueError(f"artifact URL is invalid for {name}")
        path = (artifact_root / name).resolve()
        if not path.is_relative_to(artifact_root):
            raise ValueError("artifact path escaped its release directory")
        if not path.is_file():
            raise ValueError(f"missing release artifact: {path}")
        if not isinstance(record.get("bytes"), int) or record["bytes"] < 0:
            raise ValueError(f"byte length is invalid for {name}")
    return manifest


def copy_and_measure(source: Path, destination: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    length = 0
    with source.open("rb") as input_stream, destination.open("xb") as output:
        while chunk := input_stream.read(1024 * 1024):
            output.write(chunk)
            digest.update(chunk)
            length += len(chunk)
        output.flush()
        os.fsync(output.fileno())
    return length, digest.hexdigest()


def write_blob(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def sync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def load_root_history(
    current_root_path: Path,
    history_directory: Path,
) -> tuple[Metadata, list[tuple[str, bytes]]]:
    current = Metadata.from_file(str(current_root_path))
    if not isinstance(current.signed, Root):
        raise ValueError("trusted root file does not contain root metadata")
    if current.signed.version < 1:
        raise ValueError("trusted root version must be positive")

    history: list[tuple[str, bytes]] = []
    previous: Metadata | None = None
    trust_profile: bool | None = None
    for version in range(1, current.signed.version + 1):
        name = f"{version}.root.json"
        path = history_directory / name
        if not path.is_file():
            raise ValueError(f"root history is missing {name}")
        encoded = path.read_bytes()
        metadata = Metadata.from_bytes(encoded)
        if not isinstance(metadata.signed, Root):
            raise ValueError(f"{name} does not contain root metadata")
        if metadata.signed.version != version:
            raise ValueError(f"{name} has the wrong root version")
        if not metadata.signed.consistent_snapshot:
            raise ValueError(
                f"{name} must declare consistent_snapshot=true"
            )
        entry_profile = root_uses_development_keys(metadata.signed)
        if trust_profile is None:
            trust_profile = entry_profile
        elif entry_profile != trust_profile:
            raise ValueError(
                "root rotation cannot change the trust-key profile"
            )
        metadata.verify_delegate("root", metadata)
        if previous is not None:
            previous.verify_delegate("root", metadata)
            if root_channel(previous.signed) != root_channel(metadata.signed):
                raise ValueError("root rotation cannot change release channel")
        history.append((name, encoded))
        previous = metadata

    assert previous is not None
    if previous.to_bytes(SERIALIZER) != current.to_bytes(SERIALIZER):
        raise ValueError("current root does not match final root history entry")
    if current.signed.is_expired():
        raise ValueError("trusted root metadata has expired")
    return current, history


def load_previous_release(
    repository: Path,
    expected_sequence: int,
    channel: str,
) -> tuple[str, str, str, list[dict], int, int, int, bytes]:
    metadata_directory = repository / "metadata"
    previous_root, _ = load_root_history(
        metadata_directory / "root.json",
        metadata_directory,
    )
    validate_root_profile(
        previous_root.signed,
        channel,
        allow_development_test_keys=True,
    )

    timestamp = Metadata.from_file(
        str(metadata_directory / "timestamp.json")
    )
    if not isinstance(timestamp.signed, Timestamp):
        raise ValueError("previous timestamp metadata has the wrong role")
    previous_root.verify_delegate("timestamp", timestamp)
    snapshot_meta = timestamp.signed.snapshot_meta
    snapshot_bytes = (
        metadata_directory / f"{snapshot_meta.version}.snapshot.json"
    ).read_bytes()
    snapshot_meta.verify_length_and_hashes(snapshot_bytes)
    snapshot = Metadata.from_bytes(snapshot_bytes)
    if not isinstance(snapshot.signed, Snapshot):
        raise ValueError("previous snapshot metadata has the wrong role")
    previous_root.verify_delegate("snapshot", snapshot)
    if snapshot.signed.version != snapshot_meta.version:
        raise ValueError("previous snapshot version is inconsistent")
    targets_meta = snapshot.signed.meta.get("targets.json")
    if targets_meta is None or targets_meta.version != expected_sequence:
        raise ValueError("previous targets sequence is not contiguous")

    targets_bytes = (
        metadata_directory / f"{expected_sequence}.targets.json"
    ).read_bytes()
    targets_meta.verify_length_and_hashes(targets_bytes)
    targets = Metadata.from_bytes(targets_bytes)
    if not isinstance(targets.signed, Targets):
        raise ValueError("previous targets metadata has the wrong role")
    previous_root.verify_delegate("targets", targets)
    release = targets.signed.unrecognized_fields.get("orkela")
    if not isinstance(release, dict):
        raise ValueError("previous targets has no Orkela release ledger")
    if (
        release.get("sequence") != expected_sequence
        or release.get("channel") != channel
    ):
        raise ValueError("previous release ledger is inconsistent")
    version = str(release.get("release_version", ""))
    semantic_version_key(version)
    commit = str(release.get("commit", ""))
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("previous release ledger has an invalid commit")
    history = validate_signed_release_history(
        release,
        expected_sequence,
    )
    return (
        version,
        commit,
        hashlib.sha256(targets_bytes).hexdigest(),
        history,
        snapshot.signed.version,
        timestamp.signed.version,
        previous_root.signed.version,
        previous_root.to_bytes(SERIALIZER),
    )


def validate_signed_release_history(
    release: dict,
    current_sequence: int,
) -> list[dict]:
    history = release.get("history", [])
    if not isinstance(history, list):
        raise ValueError("signed release history must be a list")
    if len(history) != current_sequence - 1:
        raise ValueError("signed release history is not contiguous")
    previous_version = None
    normalized = []
    for expected_sequence, entry in enumerate(history, start=1):
        if not isinstance(entry, dict):
            raise ValueError("signed release history entry is malformed")
        if entry.get("sequence") != expected_sequence:
            raise ValueError("signed release history sequence has a gap")
        version = str(entry.get("release_version", ""))
        version_key = semantic_version_key(version)
        if (
            previous_version is not None
            and version_key <= previous_version
        ):
            raise ValueError("signed release history version is not increasing")
        commit = str(entry.get("commit", ""))
        targets_sha256 = str(entry.get("targets_metadata_sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("signed release history commit is invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", targets_sha256):
            raise ValueError("signed release history hash is invalid")
        normalized.append(
            {
                "commit": commit,
                "release_version": version,
                "sequence": expected_sequence,
                "targets_metadata_sha256": targets_sha256,
            }
        )
        previous_version = version_key
    return normalized


def signer_directories(args: argparse.Namespace) -> dict[str, list[Path]]:
    directories = {
        "targets": list(args.targets_key_directories),
        "snapshot": [args.snapshot_key_directory],
        "timestamp": [args.timestamp_key_directory],
    }
    flattened = [path.resolve() for values in directories.values() for path in values]
    if len(flattened) != len(set(flattened)):
        raise ValueError("each online signer directory must be distinct")
    for index, first in enumerate(flattened):
        for second in flattened[index + 1:]:
            if first.is_relative_to(second) or second.is_relative_to(first):
                raise ValueError(
                    "online signer directories cannot contain one another"
                )
    for path in flattened:
        require_external_key_store(path)
        if not path.is_dir():
            raise ValueError(f"signer directory does not exist: {path}")
        if next(path.glob("root-*.pem"), None) is not None:
            raise ValueError("online signer directory contains an offline root key")
    return directories


def build(args: argparse.Namespace) -> None:
    if args.sequence < 1:
        raise ValueError("metadata sequence must be positive")
    signers = signer_directories(args)
    resolved_output = args.output.resolve()
    for values in signers.values():
        for directory in values:
            resolved_keys = directory.resolve()
            if (
                resolved_output.is_relative_to(resolved_keys)
                or resolved_keys.is_relative_to(resolved_output)
            ):
                raise ValueError(
                    "repository output and private keys must be disjoint"
                )
    history_directory = getattr(
        args,
        "root_history_directory",
        args.root.parent,
    )
    root_metadata, root_history = load_root_history(
        args.root,
        history_directory,
    )
    manifest = load_release_manifest(args.manifest, args.artifact_directory)
    artifacts = manifest["artifacts"]
    channel = root_channel(root_metadata.signed)
    if manifest["channel"] != channel:
        raise ValueError("release manifest channel does not match trusted root")
    validate_root_profile(
        root_metadata.signed,
        channel,
        getattr(args, "allow_development_test_keys", False),
    )

    now = datetime.now(timezone.utc)
    if not getattr(args, "allow_expired_test_metadata", False):
        if args.timestamp_expires <= now:
            raise ValueError("timestamp metadata must expire in the future")
        if not (
            args.timestamp_expires
            <= args.snapshot_expires
            <= args.targets_expires
            <= root_metadata.signed.expires
        ):
            raise ValueError(
                "expiry order must be timestamp <= snapshot <= targets <= root"
            )
        expiries = {
            "targets": args.targets_expires,
            "snapshot": args.snapshot_expires,
            "timestamp": args.timestamp_expires,
        }
        for role, expires in expiries.items():
            lifetime = (expires - now).total_seconds()
            if lifetime > MAXIMUM_METADATA_LIFETIME[channel][role]:
                raise ValueError(
                    f"{role} metadata exceeds the {channel} lifetime limit"
                )

    previous_targets_sha256 = None
    previous_repository = getattr(args, "previous_repository", None)
    if args.sequence == 1:
        if previous_repository is not None:
            raise ValueError("sequence 1 cannot declare a previous repository")
        snapshot_version = 1
        timestamp_version = 1
    else:
        if previous_repository is None:
            raise ValueError(
                "sequence greater than 1 requires --previous-repository"
            )
        (
            previous_version,
            previous_commit,
            previous_targets_sha256,
            previous_history,
            previous_snapshot_version,
            previous_timestamp_version,
            previous_root_version,
            previous_root_bytes,
        ) = load_previous_release(
            previous_repository,
            args.sequence - 1,
            channel,
        )
        current_history = dict(root_history)
        if (
            current_history.get(
                f"{previous_root_version}.root.json"
            ) != previous_root_bytes
        ):
            raise ValueError(
                "previous repository root is not in the current root history"
            )
        if semantic_version_key(manifest["version"]) <= semantic_version_key(
            previous_version
        ):
            raise ValueError(
                "release version must increase across contiguous sequences"
            )
        previous_history = previous_history + [
            {
                "commit": previous_commit,
                "release_version": previous_version,
                "sequence": args.sequence - 1,
                "targets_metadata_sha256": previous_targets_sha256,
            }
        ]
        snapshot_version = previous_snapshot_version + 1
        timestamp_version = previous_timestamp_version + 1
    if args.sequence == 1:
        previous_history = []

    output = args.output
    if output.exists():
        raise ValueError("refusing to overwrite an update repository")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=output.parent,
        prefix=f".{output.name}-",
    ) as temporary:
        staged = Path(temporary) / "repository"
        metadata_directory = staged / "metadata"
        target_directory = staged / "targets"
        metadata_directory.mkdir(parents=True)
        target_directory.mkdir()

        targets = Metadata(
            Targets(
                version=args.sequence,
                expires=args.targets_expires,
                unrecognized_fields={
                    "orkela": {
                        "channel": channel,
                        "commit": manifest["commit"],
                        "history": previous_history,
                        "previous_targets_sha256": previous_targets_sha256,
                        "release_version": manifest["version"],
                        "sequence": args.sequence,
                    }
                },
            )
        )
        artifact_root = args.artifact_directory.resolve()
        for index, record in enumerate(artifacts):
            name = str(record["name"])
            source = (artifact_root / name).resolve()
            incoming = target_directory / f".incoming-{index}"
            length, digest = copy_and_measure(source, incoming)
            if length != record["bytes"]:
                raise ValueError(f"byte length mismatch for {name}")
            if digest != record["sha256"]:
                raise ValueError(f"SHA-256 mismatch for {name}")
            target = TargetFile(
                length,
                {"sha256": digest},
                name,
                {
                    "custom": {
                        "arch": record["arch"],
                        "channel": channel,
                        "commit": manifest["commit"],
                        "kind": record["kind"],
                        "platform": record["platform"],
                        "release_version": manifest["version"],
                        "sequence": args.sequence,
                    }
                },
            )
            targets.signed.targets[name] = target
            incoming.replace(target_directory / f"{digest}.{name}")
        sign_with_role(
            targets,
            root_metadata.signed,
            "targets",
            signers["targets"],
        )
        targets_bytes = write_metadata(
            metadata_directory / f"{args.sequence}.targets.json",
            targets,
        )

        snapshot = Metadata(
            Snapshot(
                version=snapshot_version,
                expires=args.snapshot_expires,
                meta={
                    "targets.json": MetaFile.from_data(
                        args.sequence,
                        targets_bytes,
                        ["sha256"],
                    )
                },
            )
        )
        sign_with_role(
            snapshot,
            root_metadata.signed,
            "snapshot",
            signers["snapshot"],
        )
        snapshot_bytes = write_metadata(
            metadata_directory / f"{snapshot_version}.snapshot.json",
            snapshot,
        )

        timestamp = Metadata(
            Timestamp(
                version=timestamp_version,
                expires=args.timestamp_expires,
                snapshot_meta=MetaFile.from_data(
                    snapshot_version,
                    snapshot_bytes,
                    ["sha256"],
                ),
            )
        )
        sign_with_role(
            timestamp,
            root_metadata.signed,
            "timestamp",
            signers["timestamp"],
        )
        write_metadata(metadata_directory / "timestamp.json", timestamp)
        for name, encoded in root_history:
            write_blob(metadata_directory / name, encoded)
        write_blob(
            metadata_directory / "root.json",
            root_metadata.to_bytes(SERIALIZER),
        )
        sync_directory(target_directory)
        sync_directory(metadata_directory)
        sync_directory(staged)
        os.replace(staged, output)
        sync_directory(output.parent)


def refresh_online_metadata(args: argparse.Namespace) -> None:
    repository = args.repository.resolve()
    metadata_directory = repository / "metadata"
    target_directory = repository / "targets"
    if not metadata_directory.is_dir() or not target_directory.is_dir():
        raise ValueError("repository must contain metadata and targets")
    if {entry.name for entry in repository.iterdir()} != {
        "metadata",
        "targets",
    }:
        raise ValueError("repository copy source has unexpected top-level data")
    for path in repository.rglob("*"):
        if path.is_symlink():
            raise ValueError("repository copy source cannot contain symlinks")
        relative = path.relative_to(repository)
        if path.is_dir() and len(relative.parts) > 1:
            raise ValueError("repository copy source cannot contain subfolders")
        if (
            path.is_file()
            and relative.parts[0] == "metadata"
            and path.suffix != ".json"
        ):
            raise ValueError("repository metadata contains a non-JSON file")
    output = args.output.resolve()
    if output.exists():
        raise ValueError("refusing to overwrite refreshed repository output")
    if output.is_relative_to(repository) or repository.is_relative_to(output):
        raise ValueError("input and output repositories must be disjoint")

    root_metadata, _ = load_root_history(
        metadata_directory / "root.json",
        metadata_directory,
    )
    channel = root_channel(root_metadata.signed)
    validate_root_profile(
        root_metadata.signed,
        channel,
        getattr(args, "allow_development_test_keys", False),
    )
    now = datetime.now(timezone.utc)
    if not (
        now < args.timestamp_expires
        <= args.snapshot_expires
        <= root_metadata.signed.expires
    ):
        raise ValueError(
            "online expiry order must be now < timestamp <= snapshot <= root"
        )
    for role, expires in {
        "snapshot": args.snapshot_expires,
        "timestamp": args.timestamp_expires,
    }.items():
        if (
            expires - now
        ).total_seconds() > MAXIMUM_METADATA_LIFETIME[channel][role]:
            raise ValueError(
                f"{role} metadata exceeds the {channel} lifetime limit"
            )

    signer_paths = {
        "snapshot": args.snapshot_key_directory.resolve(),
        "timestamp": args.timestamp_key_directory.resolve(),
    }
    signer_values = list(signer_paths.values())
    for index, first in enumerate(signer_values):
        for second in signer_values[index + 1:]:
            if first.is_relative_to(second) or second.is_relative_to(first):
                raise ValueError(
                    "online signer directories cannot contain one another"
                )
    for path in signer_values:
        require_external_key_store(path)
        if not path.is_dir():
            raise ValueError(f"signer directory does not exist: {path}")
        if next(path.glob("root-*.pem"), None) is not None:
            raise ValueError("online signer directory contains an offline key")
        if (
            repository.is_relative_to(path)
            or path.is_relative_to(repository)
        ):
            raise ValueError(
                "input repository and private keys must be disjoint"
            )
        if output.is_relative_to(path) or path.is_relative_to(output):
            raise ValueError(
                "refreshed repository output and keys must be disjoint"
            )
    if next(repository.rglob("*.pem"), None) is not None:
        raise ValueError("input repository contains forbidden PEM material")

    old_timestamp = Metadata.from_file(
        str(metadata_directory / "timestamp.json")
    )
    if not isinstance(old_timestamp.signed, Timestamp):
        raise ValueError("repository timestamp has the wrong role")
    root_metadata.verify_delegate("timestamp", old_timestamp)
    old_snapshot_meta = old_timestamp.signed.snapshot_meta
    old_snapshot_path = (
        metadata_directory
        / f"{old_snapshot_meta.version}.snapshot.json"
    )
    old_snapshot_bytes = old_snapshot_path.read_bytes()
    old_snapshot_meta.verify_length_and_hashes(old_snapshot_bytes)
    old_snapshot = Metadata.from_bytes(old_snapshot_bytes)
    if not isinstance(old_snapshot.signed, Snapshot):
        raise ValueError("repository snapshot has the wrong role")
    root_metadata.verify_delegate("snapshot", old_snapshot)
    targets_meta = old_snapshot.signed.meta.get("targets.json")
    if targets_meta is None:
        raise ValueError("repository snapshot has no targets entry")
    targets_path = (
        metadata_directory
        / f"{targets_meta.version}.targets.json"
    )
    targets_bytes = targets_path.read_bytes()
    targets_meta.verify_length_and_hashes(targets_bytes)
    targets = Metadata.from_bytes(targets_bytes)
    if not isinstance(targets.signed, Targets):
        raise ValueError("repository targets has the wrong role")
    root_metadata.verify_delegate("targets", targets)
    if targets.signed.is_expired():
        raise ValueError("cannot refresh around expired targets metadata")
    if args.snapshot_expires > targets.signed.expires:
        raise ValueError(
            "snapshot expiry cannot outlive authenticated targets"
        )

    snapshot_version = old_snapshot.signed.version + 1
    timestamp_version = old_timestamp.signed.version + 1
    snapshot = Metadata(
        Snapshot(
            version=snapshot_version,
            expires=args.snapshot_expires,
            meta={
                "targets.json": MetaFile.from_data(
                    targets_meta.version,
                    targets_bytes,
                    ["sha256"],
                )
            },
        )
    )
    sign_with_role(
        snapshot,
        root_metadata.signed,
        "snapshot",
        [signer_paths["snapshot"]],
    )
    snapshot_bytes = snapshot.to_bytes(SERIALIZER)
    timestamp = Metadata(
        Timestamp(
            version=timestamp_version,
            expires=args.timestamp_expires,
            snapshot_meta=MetaFile.from_data(
                snapshot_version,
                snapshot_bytes,
                ["sha256"],
            ),
        )
    )
    sign_with_role(
        timestamp,
        root_metadata.signed,
        "timestamp",
        [signer_paths["timestamp"]],
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=output.parent,
        prefix=f".{output.name}-",
    ) as temporary:
        staged = Path(temporary) / "repository"
        shutil.copytree(repository, staged)
        staged_metadata = staged / "metadata"
        write_metadata(
            staged_metadata / f"{snapshot_version}.snapshot.json",
            snapshot,
        )
        (staged_metadata / "timestamp.json").unlink()
        write_metadata(staged_metadata / "timestamp.json", timestamp)
        sync_directory(staged_metadata)
        sync_directory(staged)
        os.replace(staged, output)
        sync_directory(output.parent)


class LocalRepositoryFetcher(FetcherInterface):
    """Map synthetic HTTPS repository URLs to immutable local evidence."""

    def __init__(self, metadata: Path, targets: Path):
        self._roots = {
            "metadata": metadata.resolve(),
            "targets": targets.resolve(),
        }

    def _fetch(self, url: str) -> Iterator[bytes]:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "orkela.invalid":
            raise ValueError("unexpected repository URL")
        category, separator, relative = parsed.path.lstrip("/").partition("/")
        if not separator or category not in self._roots:
            raise ValueError("unexpected repository path")
        root = self._roots[category]
        path = (root / unquote(relative)).resolve()
        if not path.is_relative_to(root):
            raise DownloadHTTPError("repository path escaped its root", 403)
        if not path.is_file():
            raise DownloadHTTPError(f"repository file not found: {path}", 404)
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                yield chunk


class PortableUpdater(Updater):
    """Persist the trusted root without requiring symlink privileges."""

    def _persist_file(self, filename: str, data: bytes) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self._dir,
            prefix="metadata-",
            suffix=".tmp",
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, filename)
            sync_directory(Path(filename).parent)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise

    def _update_root_symlink(self) -> None:
        root_history = (
            Path(self._dir)
            / "root_history"
            / f"{self._trusted_set.root.version}.root.json"
        )
        destination = Path(self._dir) / "root.json"
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self._dir,
            prefix="root-",
            suffix=".tmp",
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(root_history.read_bytes())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, destination)
            sync_directory(Path(self._dir))
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise


@contextmanager
def client_state_lock(state: Path) -> Iterator[None]:
    state.parent.mkdir(parents=True, exist_ok=True)
    lock = state.parent / f".{state.name}.update.lock"
    descriptor = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if os.name == "nt":
            import msvcrt

            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
                os.fsync(descriptor)
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        os.close(descriptor)
        raise ValueError("update client state is already locked") from error
    try:
        yield
    finally:
        if os.name == "nt":
            import msvcrt

            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def write_json_atomic(path: Path, value: dict) -> None:
    encoded = (
        json.dumps(value, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}-",
        suffix=".tmp",
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
        sync_directory(path.parent)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def transaction_paths(state: Path) -> tuple[Path, Path]:
    return (
        state.parent / f".{state.name}.update-pending",
        state.parent / f".{state.name}.update-backup",
    )


def recover_client_state(state: Path) -> None:
    pending, backup = transaction_paths(state)
    if state.exists():
        if pending.exists() and backup.exists():
            raise ValueError("ambiguous update transaction requires recovery")
        if pending.exists():
            shutil.rmtree(pending)
        if backup.exists():
            shutil.rmtree(backup)
        sync_directory(state.parent)
        return

    if backup.exists():
        os.replace(backup, state)
        sync_directory(state.parent)
        if pending.exists():
            shutil.rmtree(pending)
            sync_directory(state.parent)
        return
    if pending.exists():
        shutil.rmtree(pending)
        sync_directory(state.parent)


def commit_client_state(staged: Path, destination: Path) -> None:
    pending, backup = transaction_paths(destination)
    if pending.exists() or backup.exists():
        raise ValueError("unrecovered update transaction blocks commit")
    had_destination = destination.exists()
    try:
        os.replace(staged, pending)
        sync_directory(destination.parent)
        if had_destination:
            os.replace(destination, backup)
            sync_directory(destination.parent)
        os.replace(pending, destination)
        sync_directory(destination.parent)
    except Exception:
        if not destination.exists() and had_destination and backup.exists():
            os.replace(backup, destination)
        if pending.exists():
            shutil.rmtree(pending)
        sync_directory(destination.parent)
        raise
    if backup.exists():
        shutil.rmtree(backup)
        sync_directory(destination.parent)


def validate_release_ledger(
    staged_state: Path,
    channel: str,
    release_version: str,
    commit: str,
    sequence: int,
    target_sha256: str,
    targets_metadata_sha256: str,
    signed_history: list[dict],
    current_version: str,
    selector: str,
    require_existing: bool,
) -> dict:
    ledger_path = staged_state / "orkela-release-ledger.json"
    if ledger_path.exists():
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        if ledger.get("schema") != "org.scenelith.orkela.release-ledger.v1":
            raise ValueError("release ledger schema is invalid")
        if ledger.get("channel") != channel:
            raise ValueError("release ledger belongs to another channel")
    else:
        if require_existing:
            raise ValueError("existing trusted state has no release ledger")
        ledger = {
            "channel": channel,
            "highest_sequence": 0,
            "highest_version": current_version,
            "releases": {},
            "schema": "org.scenelith.orkela.release-ledger.v1",
        }

    release_key = semantic_version_key(release_version)
    installed_key = semantic_version_key(current_version)
    highest_version = str(ledger.get("highest_version", current_version))
    highest_key = semantic_version_key(highest_version)
    if release_key < max(installed_key, highest_key):
        raise ValueError("application version downgrade is forbidden")

    releases = ledger.get("releases")
    if not isinstance(releases, dict):
        raise ValueError("release ledger is malformed")
    for recorded_version, recorded in releases.items():
        semantic_version_key(recorded_version)
        if (
            not isinstance(recorded, dict)
            or not re.fullmatch(
                r"[0-9a-f]{40}",
                str(recorded.get("commit", "")),
            )
            or not isinstance(recorded.get("sequence"), int)
            or recorded["sequence"] < 1
            or not re.fullmatch(
                r"[0-9a-f]{64}",
                str(recorded.get("targets_metadata_sha256", "")),
            )
            or not isinstance(recorded.get("artifacts"), dict)
        ):
            raise ValueError("release ledger entry is malformed")
        for artifact_selector, artifact_hash in recorded["artifacts"].items():
            if (
                not isinstance(artifact_selector, str)
                or not artifact_selector
                or not re.fullmatch(r"[0-9a-f]{64}", str(artifact_hash))
            ):
                raise ValueError("release ledger artifact entry is malformed")

    accepted = releases.get(release_version)
    release_identity = {
        "commit": commit,
        "sequence": sequence,
        "targets_metadata_sha256": targets_metadata_sha256,
    }
    if accepted is not None:
        if any(
            accepted.get(field) != expected
            for field, expected in release_identity.items()
        ):
            raise ValueError("signed release version attempted equivocation")
        identity = accepted
    else:
        identity = {
            **release_identity,
            "artifacts": {},
        }
    artifacts = identity["artifacts"]
    accepted_artifact = artifacts.get(selector)
    if (
        accepted_artifact is not None
        and accepted_artifact != target_sha256
    ):
        raise ValueError("signed target selector attempted equivocation")
    artifacts[selector] = target_sha256

    highest_sequence = ledger.get("highest_sequence", 0)
    if not isinstance(highest_sequence, int) or highest_sequence < 0:
        raise ValueError("release ledger sequence is malformed")
    if releases:
        if highest_version not in releases:
            raise ValueError("release ledger highest version is missing")
        if releases[highest_version]["sequence"] != highest_sequence:
            raise ValueError("release ledger highest sequence is inconsistent")
        if semantic_version_key(highest_version) != max(
            semantic_version_key(version) for version in releases
        ):
            raise ValueError("release ledger highest version is inconsistent")
    if release_key > highest_key and sequence <= highest_sequence:
        raise ValueError("new release has a non-increasing sequence")
    if sequence > highest_sequence and highest_sequence > 0:
        if highest_sequence > len(signed_history):
            raise ValueError("signed release history cannot prove this skip")
        checkpoint = signed_history[highest_sequence - 1]
        previous_identity = releases.get(highest_version)
        if (
            not isinstance(previous_identity, dict)
            or checkpoint.get("release_version") != highest_version
            or checkpoint.get("commit") != previous_identity.get("commit")
            or checkpoint.get("targets_metadata_sha256")
                != previous_identity.get("targets_metadata_sha256")
        ):
            raise ValueError(
                "signed cumulative history does not extend trusted state"
            )
    releases[release_version] = identity
    if release_key >= highest_key:
        ledger["highest_version"] = release_version
        ledger["highest_sequence"] = max(highest_sequence, sequence)
    return ledger


def verify(args: argparse.Namespace) -> None:
    metadata = args.repository / "metadata"
    targets = args.repository / "targets"
    if not metadata.is_dir() or not targets.is_dir():
        raise ValueError("repository must contain metadata and targets")
    with client_state_lock(args.state):
        recover_client_state(args.state)
        original_root = args.state / "root.json"
        if args.state.exists() and not original_root.is_file():
            raise ValueError("existing client state has no trusted root")
        root_path = original_root if original_root.is_file() else args.root
        preflight_root = Metadata.from_file(str(root_path))
        if not isinstance(preflight_root.signed, Root):
            raise ValueError("client bootstrap has the wrong role")
        validate_root_profile(
            preflight_root.signed,
            args.channel,
            getattr(args, "allow_development_test_keys", False),
        )

        with tempfile.TemporaryDirectory(
            dir=args.state.parent,
            prefix=f".{args.state.name}.transaction-",
        ) as transaction:
            staged_state = Path(transaction) / "state"
            if args.state.exists():
                shutil.copytree(args.state, staged_state)
                bootstrap_root = None
            else:
                staged_state.mkdir()
                bootstrap_root = args.root.read_bytes()

            download_directory = Path(transaction) / "download"
            download_directory.mkdir()
            updater = PortableUpdater(
                str(staged_state),
                "https://orkela.invalid/metadata/",
                str(download_directory),
                "https://orkela.invalid/targets/",
                fetcher=LocalRepositoryFetcher(metadata, targets),
                bootstrap=bootstrap_root,
            )
            updater.refresh()
            trusted_root_metadata = Metadata.from_file(
                str(staged_state / "root.json")
            )
            if not isinstance(trusted_root_metadata.signed, Root):
                raise ValueError("client trusted root has the wrong role")
            validate_root_profile(
                trusted_root_metadata.signed,
                args.channel,
                getattr(args, "allow_development_test_keys", False),
            )
            cached_targets = Metadata.from_file(
                str(staged_state / "targets.json")
            )
            if not isinstance(cached_targets.signed, Targets):
                raise ValueError("client did not trust targets metadata")
            matches = []
            for name, candidate in cached_targets.signed.targets.items():
                custom = candidate.unrecognized_fields.get("custom")
                if not isinstance(custom, dict):
                    continue
                if (
                    custom.get("channel") == args.channel
                    and custom.get("platform") == args.platform
                    and custom.get("arch") == args.architecture
                    and custom.get("kind") == args.kind
                ):
                    matches.append((name, candidate, custom))
            if len(matches) != 1:
                raise ValueError(
                    "trusted repository must contain exactly one "
                    "matching target"
                )
            name, candidate, custom = matches[0]
            if custom.get("sequence") != cached_targets.signed.version:
                raise ValueError(
                    "target sequence does not match targets metadata"
                )
            release_version = str(custom.get("release_version", ""))
            semantic_version_key(release_version)
            commit = str(custom.get("commit", ""))
            if not re.fullmatch(r"[0-9a-f]{40}", commit):
                raise ValueError("trusted target has an invalid source commit")
            target = updater.get_targetinfo(name)
            if target is None or target != candidate:
                raise ValueError(f"trusted target disappeared: {name}")
            updater.download_target(target)
            release = cached_targets.signed.unrecognized_fields.get("orkela")
            if not isinstance(release, dict):
                raise ValueError("targets metadata has no release ledger")
            for field, expected in {
                "channel": args.channel,
                "commit": commit,
                "release_version": release_version,
                "sequence": cached_targets.signed.version,
            }.items():
                if release.get(field) != expected:
                    raise ValueError(
                        f"target and release ledger disagree on {field}"
                    )
            signed_history = validate_signed_release_history(
                release,
                cached_targets.signed.version,
            )
            previous_targets_sha256 = release.get(
                "previous_targets_sha256"
            )
            if cached_targets.signed.version == 1:
                if previous_targets_sha256 is not None:
                    raise ValueError("first release has a previous target")
            elif (
                previous_targets_sha256
                != signed_history[-1]["targets_metadata_sha256"]
            ):
                raise ValueError(
                    "release predecessor disagrees with cumulative history"
                )
            target_sha256 = str(candidate.hashes.get("sha256", ""))
            if not re.fullmatch(r"[0-9a-f]{64}", target_sha256):
                raise ValueError("trusted target has no SHA-256 identity")
            ledger = validate_release_ledger(
                staged_state,
                args.channel,
                release_version,
                commit,
                cached_targets.signed.version,
                target_sha256,
                hashlib.sha256(
                    (staged_state / "targets.json").read_bytes()
                ).hexdigest(),
                signed_history,
                args.current_version,
                f"{args.platform}/{args.architecture}/{args.kind}",
                args.state.exists(),
            )
            write_json_atomic(
                staged_state / "orkela-release-ledger.json",
                ledger,
            )
            del updater
            sync_directory(staged_state)
            commit_client_state(staged_state, args.state)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    subparsers = result.add_subparsers(dest="command", required=True)

    bootstrap_parser = subparsers.add_parser("bootstrap")
    bootstrap_parser.add_argument("--root", type=Path, required=True)
    bootstrap_parser.add_argument(
        "--key-directory",
        type=Path,
        required=True,
    )
    bootstrap_parser.add_argument(
        "--root-expires",
        type=parse_utc,
        required=True,
    )
    bootstrap_parser.add_argument(
        "--channel",
        choices=("stable", "beta", "nightly"),
        required=True,
    )
    bootstrap_parser.add_argument(
        "--development-test-keys",
        action="store_true",
        help="generate unencrypted disposable keys for hostile-client tests",
    )
    bootstrap_parser.set_defaults(function=bootstrap)

    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--root", type=Path, required=True)
    build_parser.add_argument(
        "--root-history-directory",
        type=Path,
        required=True,
    )
    build_parser.add_argument(
        "--targets-key-directory",
        dest="targets_key_directories",
        action="append",
        type=Path,
        required=True,
    )
    build_parser.add_argument(
        "--snapshot-key-directory",
        type=Path,
        required=True,
    )
    build_parser.add_argument(
        "--timestamp-key-directory",
        type=Path,
        required=True,
    )
    build_parser.add_argument("--manifest", type=Path, required=True)
    build_parser.add_argument(
        "--artifact-directory",
        type=Path,
        required=True,
    )
    build_parser.add_argument("--output", type=Path, required=True)
    build_parser.add_argument("--sequence", type=int, required=True)
    build_parser.add_argument(
        "--previous-repository",
        type=Path,
        help="authenticated previous sequence; mandatory after sequence 1",
    )
    build_parser.add_argument(
        "--allow-development-test-keys",
        action="store_true",
        help="test-only: accept roots marked as disposable development trust",
    )
    build_parser.add_argument(
        "--targets-expires",
        type=parse_utc,
        required=True,
    )
    build_parser.add_argument(
        "--snapshot-expires",
        type=parse_utc,
        required=True,
    )
    build_parser.add_argument(
        "--timestamp-expires",
        type=parse_utc,
        required=True,
    )
    build_parser.set_defaults(function=build)

    refresh_parser = subparsers.add_parser("refresh-online-metadata")
    refresh_parser.add_argument("--repository", type=Path, required=True)
    refresh_parser.add_argument("--output", type=Path, required=True)
    refresh_parser.add_argument(
        "--snapshot-key-directory",
        type=Path,
        required=True,
    )
    refresh_parser.add_argument(
        "--timestamp-key-directory",
        type=Path,
        required=True,
    )
    refresh_parser.add_argument(
        "--snapshot-expires",
        type=parse_utc,
        required=True,
    )
    refresh_parser.add_argument(
        "--timestamp-expires",
        type=parse_utc,
        required=True,
    )
    refresh_parser.add_argument(
        "--allow-development-test-keys",
        action="store_true",
        help="test-only: accept roots marked as disposable development trust",
    )
    refresh_parser.set_defaults(function=refresh_online_metadata)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--root", type=Path, required=True)
    verify_parser.add_argument("--repository", type=Path, required=True)
    verify_parser.add_argument("--state", type=Path, required=True)
    verify_parser.add_argument(
        "--channel",
        choices=("stable", "beta", "nightly"),
        required=True,
    )
    verify_parser.add_argument("--platform", required=True)
    verify_parser.add_argument("--architecture", required=True)
    verify_parser.add_argument("--kind", required=True)
    verify_parser.add_argument("--current-version", required=True)
    verify_parser.add_argument(
        "--allow-development-test-keys",
        action="store_true",
        help="test-only: accept roots marked as disposable development trust",
    )
    verify_parser.set_defaults(function=verify)
    return result


def main() -> int:
    args = parser().parse_args()
    if getattr(args, "sequence", 1) < 1:
        raise ValueError("metadata sequence must be positive")
    args.function(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
