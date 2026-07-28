from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from unittest import mock
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives.serialization import load_pem_private_key
from securesystemslib.signer import CryptoSigner
from tuf.api.exceptions import (
    BadVersionNumberError,
    ExpiredMetadataError,
    LengthOrHashMismatchError,
    UnsignedMetadataError,
)


MODULE_PATH = (
    Path(__file__).parents[1]
    / "tools"
    / "release"
    / "tuf_repository.py"
)
SPEC = importlib.util.spec_from_file_location(
    "orkela_tuf_repository",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def utc_after(days: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=days)


def tree_snapshot(path: Path) -> dict[str, bytes]:
    if not path.exists():
        return {}
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in path.rglob("*")
        if item.is_file()
    }


class TufRepositoryTest(unittest.TestCase):
    def make_fixture(self, root: Path) -> tuple[Path, Path, Path, Path]:
        trusted_root = root / "trust" / "root.json"
        keys = root / "private"
        MODULE.bootstrap(
            Namespace(
                root=trusted_root,
                key_directory=keys,
                root_expires=utc_after(3650),
                development_test_keys=True,
                channel="beta",
            )
        )
        artifacts = root / "artifacts"
        artifacts.mkdir()
        package = artifacts / "Orkela-test.bin"
        package.write_bytes(b"Orkela authenticated package")
        manifest = root / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "artifacts": [
                        {
                            "arch": "x64",
                            "bytes": package.stat().st_size,
                            "kind": "installer",
                            "name": package.name,
                            "platform": "windows",
                            "sha256": hashlib.sha256(
                                package.read_bytes()
                            ).hexdigest(),
                            "url": (
                                "https://example.invalid/"
                                "Orkela-test.bin"
                            ),
                        }
                    ],
                    "channel": "beta",
                    "commit": "0123456789abcdef0123456789abcdef01234567",
                    "published_at": "2026-07-28T00:00:00Z",
                    "schema": "org.scenelith.orkela.update.v1",
                    "version": "0.3.0-alpha.1",
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return trusted_root, keys, artifacts, manifest

    def build_repository(
        self,
        output: Path,
        trusted_root: Path,
        keys: Path,
        artifacts: Path,
        manifest: Path,
        sequence: int,
        expiry_days: int = 7,
        previous_repository: Path | None = None,
        allow_test_keys: bool = True,
        targets_expiry_days: int = 30,
    ) -> None:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["version"] = f"0.3.0-alpha.{sequence}"
        payload["commit"] = f"{sequence:040x}"
        manifest.write_text(
            json.dumps(payload, sort_keys=True),
            encoding="utf-8",
        )
        MODULE.build(
            Namespace(
                root=trusted_root,
                root_history_directory=trusted_root.parent,
                targets_key_directories=sorted(
                    (keys / "targets").iterdir()
                ),
                snapshot_key_directory=keys / "snapshot" / "online",
                timestamp_key_directory=keys / "timestamp" / "online",
                manifest=manifest,
                artifact_directory=artifacts,
                output=output,
                sequence=sequence,
                previous_repository=previous_repository,
                channel="beta",
                allow_development_test_keys=allow_test_keys,
                allow_expired_test_metadata=expiry_days < 0,
                targets_expires=utc_after(targets_expiry_days),
                snapshot_expires=utc_after(2),
                timestamp_expires=utc_after(
                    min(expiry_days, 1) if expiry_days > 0 else -1
                ),
            )
        )

    def refresh_repository(
        self,
        repository: Path,
        output: Path,
        keys: Path,
    ) -> None:
        MODULE.refresh_online_metadata(
            Namespace(
                repository=repository,
                output=output,
                snapshot_key_directory=keys / "snapshot" / "online",
                timestamp_key_directory=keys / "timestamp" / "online",
                snapshot_expires=utc_after(2),
                timestamp_expires=utc_after(1),
                allow_development_test_keys=True,
            )
        )

    def test_threshold_signed_repository_downloads_exact_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            repository = root / "repository"
            self.build_repository(
                repository,
                trusted_root,
                keys,
                artifacts,
                manifest,
                1,
            )
            MODULE.verify(
                Namespace(
                    root=trusted_root,
                    repository=repository,
                    state=root / "client",
                    channel="beta",
                    platform="windows",
                    architecture="x64",
                    kind="installer",
                    current_version="0.3.0-alpha.0",
                    allow_development_test_keys=True,
                )
            )

    def test_persisted_client_rejects_signed_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            first = root / "first"
            second = root / "second"
            self.build_repository(
                first,
                trusted_root,
                keys,
                artifacts,
                manifest,
                1,
            )
            self.build_repository(
                second,
                trusted_root,
                keys,
                artifacts,
                manifest,
                2,
                previous_repository=first,
            )
            state = root / "client"
            MODULE.verify(
                Namespace(
                    root=trusted_root,
                    repository=second,
                    state=state,
                    channel="beta",
                    platform="windows",
                    architecture="x64",
                    kind="installer",
                    current_version="0.3.0-alpha.0",
                    allow_development_test_keys=True,
                )
            )
            with self.assertRaises(BadVersionNumberError):
                MODULE.verify(
                    Namespace(
                        root=trusted_root,
                        repository=first,
                        state=state,
                        channel="beta",
                        platform="windows",
                        architecture="x64",
                        kind="installer",
                        current_version="0.3.0-alpha.0",
                        allow_development_test_keys=True,
                    )
                )

    def test_cumulative_history_rejects_a_fork_after_accepted_release(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            first = root / "first"
            canonical_second = root / "canonical-second"
            self.build_repository(
                first,
                trusted_root,
                keys,
                artifacts,
                manifest,
                1,
            )
            self.build_repository(
                canonical_second,
                trusted_root,
                keys,
                artifacts,
                manifest,
                2,
                previous_repository=first,
            )
            state = root / "client"
            arguments = Namespace(
                root=trusted_root,
                repository=first,
                state=state,
                channel="beta",
                platform="windows",
                architecture="x64",
                kind="installer",
                current_version="0.3.0-alpha.0",
                allow_development_test_keys=True,
            )
            MODULE.verify(arguments)
            arguments.repository = canonical_second
            MODULE.verify(arguments)
            before = tree_snapshot(state)

            package = artifacts / "Orkela-test.bin"
            package.write_bytes(b"forked but valid package")
            manifest_value = json.loads(
                manifest.read_text(encoding="utf-8")
            )
            manifest_value["artifacts"][0]["bytes"] = package.stat().st_size
            manifest_value["artifacts"][0]["sha256"] = hashlib.sha256(
                package.read_bytes()
            ).hexdigest()
            manifest.write_text(
                json.dumps(manifest_value),
                encoding="utf-8",
            )
            fork_second = root / "fork-second"
            fork_third = root / "fork-third"
            self.build_repository(
                fork_second,
                trusted_root,
                keys,
                artifacts,
                manifest,
                2,
                previous_repository=first,
            )
            self.build_repository(
                fork_third,
                trusted_root,
                keys,
                artifacts,
                manifest,
                3,
                previous_repository=fork_second,
            )
            arguments.repository = fork_third
            with self.assertRaisesRegex(
                ValueError,
                "does not extend trusted state",
            ):
                MODULE.verify(arguments)
            self.assertEqual(tree_snapshot(state), before)

    def test_expired_signed_metadata_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            repository = root / "expired"
            self.build_repository(
                repository,
                trusted_root,
                keys,
                artifacts,
                manifest,
                1,
                expiry_days=-1,
            )
            with self.assertRaises(ExpiredMetadataError):
                MODULE.verify(
                    Namespace(
                        root=trusted_root,
                        repository=repository,
                        state=root / "client",
                        channel="beta",
                        platform="windows",
                        architecture="x64",
                        kind="installer",
                        current_version="0.3.0-alpha.0",
                        allow_development_test_keys=True,
                    )
                )

    def test_target_corruption_never_reaches_client(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            repository = root / "repository"
            self.build_repository(
                repository,
                trusted_root,
                keys,
                artifacts,
                manifest,
                1,
            )
            target = next((repository / "targets").iterdir())
            target.write_bytes(b"attacker-controlled bytes")
            state = root / "client"
            with self.assertRaises(LengthOrHashMismatchError):
                MODULE.verify(
                    Namespace(
                        root=trusted_root,
                        repository=repository,
                        state=state,
                        channel="beta",
                        platform="windows",
                        architecture="x64",
                        kind="installer",
                        current_version="0.3.0-alpha.0",
                        allow_development_test_keys=True,
                    )
                )
            self.assertFalse(state.exists())

    def test_failed_refresh_preserves_every_byte_of_existing_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            first = root / "first"
            second = root / "second"
            self.build_repository(
                first,
                trusted_root,
                keys,
                artifacts,
                manifest,
                1,
            )
            self.build_repository(
                second,
                trusted_root,
                keys,
                artifacts,
                manifest,
                2,
                previous_repository=first,
            )
            state = root / "client"
            arguments = Namespace(
                root=trusted_root,
                repository=first,
                state=state,
                channel="beta",
                platform="windows",
                architecture="x64",
                kind="installer",
                current_version="0.3.0-alpha.0",
                allow_development_test_keys=True,
            )
            MODULE.verify(arguments)
            before = tree_snapshot(state)
            next((second / "targets").iterdir()).write_bytes(b"corrupt")
            arguments.repository = second
            with self.assertRaises(LengthOrHashMismatchError):
                MODULE.verify(arguments)
            self.assertEqual(tree_snapshot(state), before)

    def test_interrupted_target_download_preserves_existing_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            first = root / "first"
            second = root / "second"
            self.build_repository(
                first,
                trusted_root,
                keys,
                artifacts,
                manifest,
                1,
            )
            self.build_repository(
                second,
                trusted_root,
                keys,
                artifacts,
                manifest,
                2,
                previous_repository=first,
            )
            state = root / "client"
            arguments = Namespace(
                root=trusted_root,
                repository=first,
                state=state,
                channel="beta",
                platform="windows",
                architecture="x64",
                kind="installer",
                current_version="0.3.0-alpha.0",
                allow_development_test_keys=True,
            )
            MODULE.verify(arguments)
            before = tree_snapshot(state)
            arguments.repository = second
            with (
                mock.patch.object(
                    MODULE.PortableUpdater,
                    "download_target",
                    side_effect=OSError("simulated interruption"),
                ),
                self.assertRaisesRegex(OSError, "simulated interruption"),
            ):
                MODULE.verify(arguments)
            self.assertEqual(tree_snapshot(state), before)

    def test_crash_after_backup_rename_cannot_reopen_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            first = root / "first"
            second = root / "second"
            self.build_repository(
                first,
                trusted_root,
                keys,
                artifacts,
                manifest,
                1,
            )
            self.build_repository(
                second,
                trusted_root,
                keys,
                artifacts,
                manifest,
                2,
                previous_repository=first,
            )
            state = root / "client"
            arguments = Namespace(
                root=trusted_root,
                repository=second,
                state=state,
                channel="beta",
                platform="windows",
                architecture="x64",
                kind="installer",
                current_version="0.3.0-alpha.0",
                allow_development_test_keys=True,
            )
            MODULE.verify(arguments)
            before = tree_snapshot(state)
            pending, backup = MODULE.transaction_paths(state)
            state.replace(backup)
            shutil.copytree(backup, pending)

            arguments.repository = first
            with self.assertRaises(BadVersionNumberError):
                MODULE.verify(arguments)
            self.assertEqual(tree_snapshot(state), before)
            self.assertFalse(pending.exists())
            self.assertFalse(backup.exists())

    def test_snapshot_rejects_mix_and_match_targets_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            first = root / "first"
            second = root / "second"
            self.build_repository(
                first,
                trusted_root,
                keys,
                artifacts,
                manifest,
                1,
            )
            self.build_repository(
                second,
                trusted_root,
                keys,
                artifacts,
                manifest,
                2,
                previous_repository=first,
            )
            (second / "metadata" / "2.targets.json").write_bytes(
                (first / "metadata" / "1.targets.json").read_bytes()
            )
            with self.assertRaises(LengthOrHashMismatchError):
                MODULE.verify(
                    Namespace(
                        root=trusted_root,
                        repository=second,
                        state=root / "client",
                        channel="beta",
                        platform="windows",
                        architecture="x64",
                        kind="installer",
                        current_version="0.3.0-alpha.0",
                        allow_development_test_keys=True,
                    )
                )

    def test_build_requires_threshold_number_of_private_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            targets_keys = sorted(keys.glob("targets/*/targets-*.pem"))
            targets_keys[0].unlink()
            targets_keys[1].unlink()
            output = root / "repository"
            with self.assertRaisesRegex(ValueError, "requires 2 signatures"):
                self.build_repository(
                    output,
                    trusted_root,
                    keys,
                    artifacts,
                    manifest,
                    1,
                )
            self.assertFalse(output.exists())

    def test_manifest_filename_cannot_escape_artifact_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["artifacts"][0]["name"] = "../Orkela-test.bin"
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "plain filename"):
                self.build_repository(
                    root / "repository",
                    trusted_root,
                    keys,
                    artifacts,
                    manifest,
                    1,
                )

    def test_root_channel_cannot_sign_another_channel(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["channel"] = "stable"
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match"):
                self.build_repository(
                    root / "repository",
                    trusted_root,
                    keys,
                    artifacts,
                    manifest,
                    1,
                )

    def test_target_selection_rejects_wrong_architecture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            repository = root / "repository"
            self.build_repository(
                repository,
                trusted_root,
                keys,
                artifacts,
                manifest,
                1,
            )
            state = root / "client"
            with self.assertRaisesRegex(ValueError, "exactly one"):
                MODULE.verify(
                    Namespace(
                        root=trusted_root,
                        repository=repository,
                        state=state,
                        channel="beta",
                        platform="windows",
                        architecture="arm64",
                        kind="installer",
                        current_version="0.3.0-alpha.0",
                        allow_development_test_keys=True,
                    )
                )
            self.assertFalse(state.exists())

    def test_one_release_ledger_accepts_distinct_architecture_targets(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            arm = artifacts / "Orkela-test-arm64.bin"
            arm.write_bytes(b"Orkela ARM64 authenticated package")
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["artifacts"].append(
                {
                    "arch": "arm64",
                    "bytes": arm.stat().st_size,
                    "kind": "installer",
                    "name": arm.name,
                    "platform": "windows",
                    "sha256": hashlib.sha256(
                        arm.read_bytes()
                    ).hexdigest(),
                    "url": f"https://example.invalid/{arm.name}",
                }
            )
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            repository = root / "repository"
            self.build_repository(
                repository,
                trusted_root,
                keys,
                artifacts,
                manifest,
                1,
            )
            state = root / "client"
            arguments = Namespace(
                root=trusted_root,
                repository=repository,
                state=state,
                channel="beta",
                platform="windows",
                architecture="x64",
                kind="installer",
                current_version="0.3.0-alpha.0",
                allow_development_test_keys=True,
            )
            MODULE.verify(arguments)
            arguments.architecture = "arm64"
            MODULE.verify(arguments)
            ledger = json.loads(
                (state / "orkela-release-ledger.json").read_text(
                    encoding="utf-8"
                )
            )
            artifacts_by_selector = ledger["releases"][
                "0.3.0-alpha.1"
            ]["artifacts"]
            self.assertEqual(len(artifacts_by_selector), 2)

    def test_target_selection_rejects_application_downgrade(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            repository = root / "repository"
            self.build_repository(
                repository,
                trusted_root,
                keys,
                artifacts,
                manifest,
                1,
            )
            with self.assertRaisesRegex(ValueError, "downgrade"):
                MODULE.verify(
                    Namespace(
                        root=trusted_root,
                        repository=repository,
                        state=root / "client",
                        channel="beta",
                        platform="windows",
                        architecture="x64",
                        kind="installer",
                        current_version="0.3.0-alpha.7",
                        allow_development_test_keys=True,
                    )
                )

    def test_changed_artifact_aborts_without_partial_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            (artifacts / "Orkela-test.bin").write_bytes(b"mutated")
            output = root / "repository"
            with self.assertRaisesRegex(ValueError, "byte length mismatch"):
                self.build_repository(
                    output,
                    trusted_root,
                    keys,
                    artifacts,
                    manifest,
                    1,
                )
            self.assertFalse(output.exists())

    def test_development_root_is_rejected_without_test_override(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            with self.assertRaisesRegex(ValueError, "test-key root"):
                self.build_repository(
                    root / "repository",
                    trusted_root,
                    keys,
                    artifacts,
                    manifest,
                    1,
                    allow_test_keys=False,
                )

    def test_verifier_rejects_development_root_without_test_override(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            repository = root / "repository"
            self.build_repository(
                repository,
                trusted_root,
                keys,
                artifacts,
                manifest,
                1,
            )
            state = root / "client"
            with self.assertRaisesRegex(ValueError, "test-key root"):
                MODULE.verify(
                    Namespace(
                        root=trusted_root,
                        repository=repository,
                        state=state,
                        channel="beta",
                        platform="windows",
                        architecture="x64",
                        kind="installer",
                        current_version="0.3.0-alpha.0",
                        allow_development_test_keys=False,
                    )
                )
            self.assertFalse(state.exists())

    def test_inconsistent_snapshot_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            metadata = MODULE.Metadata.from_file(str(trusted_root))
            metadata.signed.consistent_snapshot = False
            metadata.signatures.clear()
            MODULE.sign_with_role(
                metadata,
                metadata.signed,
                "root",
                sorted((keys / "root").iterdir()),
            )
            trusted_root.unlink()
            (trusted_root.parent / "1.root.json").unlink()
            MODULE.write_metadata(trusted_root, metadata)
            MODULE.write_metadata(trusted_root.parent / "1.root.json", metadata)
            with self.assertRaisesRegex(
                ValueError,
                "consistent_snapshot=true",
            ):
                self.build_repository(
                    root / "repository",
                    trusted_root,
                    keys,
                    artifacts,
                    manifest,
                    1,
                )

    def test_beta_metadata_lifetime_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            with self.assertRaisesRegex(ValueError, "lifetime limit"):
                self.build_repository(
                    root / "repository",
                    trusted_root,
                    keys,
                    artifacts,
                    manifest,
                    1,
                    targets_expiry_days=46,
                )

    def test_expired_app_release_can_renew_online_metadata_repeatedly(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            repository = root / "generation-1"
            self.build_repository(
                repository,
                trusted_root,
                keys,
                artifacts,
                manifest,
                1,
                expiry_days=-1,
            )
            current = repository
            state = root / "client"
            for expected_metadata_version in range(2, 7):
                refreshed = root / f"generation-{expected_metadata_version}"
                self.refresh_repository(current, refreshed, keys)
                timestamp = MODULE.Metadata.from_file(
                    str(refreshed / "metadata" / "timestamp.json")
                )
                self.assertEqual(
                    timestamp.signed.version,
                    expected_metadata_version,
                )
                snapshot = MODULE.Metadata.from_file(
                    str(
                        refreshed
                        / "metadata"
                        / f"{expected_metadata_version}.snapshot.json"
                    )
                )
                self.assertEqual(snapshot.signed.version, expected_metadata_version)
                self.assertEqual(
                    snapshot.signed.meta["targets.json"].version,
                    1,
                )
                MODULE.verify(
                    Namespace(
                        root=trusted_root,
                        repository=refreshed,
                        state=state,
                        channel="beta",
                        platform="windows",
                        architecture="x64",
                        kind="installer",
                        current_version="0.3.0-alpha.0",
                        allow_development_test_keys=True,
                    )
                )
                current = refreshed

    def test_app_release_after_online_refresh_keeps_metadata_monotonic(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            first = root / "app-1"
            online_2 = root / "online-2"
            online_3 = root / "online-3"
            second = root / "app-2"
            self.build_repository(
                first,
                trusted_root,
                keys,
                artifacts,
                manifest,
                1,
            )
            self.refresh_repository(first, online_2, keys)
            self.refresh_repository(online_2, online_3, keys)
            self.build_repository(
                second,
                trusted_root,
                keys,
                artifacts,
                manifest,
                2,
                previous_repository=online_3,
            )
            timestamp = MODULE.Metadata.from_file(
                str(second / "metadata" / "timestamp.json")
            )
            self.assertEqual(timestamp.signed.version, 4)
            snapshot = MODULE.Metadata.from_file(
                str(second / "metadata" / "4.snapshot.json")
            )
            self.assertEqual(snapshot.signed.version, 4)
            self.assertEqual(snapshot.signed.meta["targets.json"].version, 2)

            state = root / "client"
            arguments = Namespace(
                root=trusted_root,
                repository=online_3,
                state=state,
                channel="beta",
                platform="windows",
                architecture="x64",
                kind="installer",
                current_version="0.3.0-alpha.0",
                allow_development_test_keys=True,
            )
            MODULE.verify(arguments)
            arguments.repository = second
            MODULE.verify(arguments)

    def test_online_refresh_rejects_expired_targets_without_output(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            repository = root / "expired-targets"
            self.build_repository(
                repository,
                trusted_root,
                keys,
                artifacts,
                manifest,
                1,
                expiry_days=-1,
                targets_expiry_days=-1,
            )
            output = root / "must-not-exist"
            with self.assertRaisesRegex(ValueError, "expired targets"):
                self.refresh_repository(repository, output, keys)
            self.assertFalse(output.exists())

    def test_online_refresh_rejects_nested_or_output_overlapping_custody(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            repository = root / "repository"
            self.build_repository(
                repository,
                trusted_root,
                keys,
                artifacts,
                manifest,
                1,
            )
            common = dict(
                repository=repository,
                snapshot_expires=utc_after(2),
                timestamp_expires=utc_after(1),
                allow_development_test_keys=True,
            )
            with self.assertRaisesRegex(ValueError, "cannot contain"):
                MODULE.refresh_online_metadata(
                    Namespace(
                        **common,
                        output=root / "nested-output",
                        snapshot_key_directory=keys / "snapshot",
                        timestamp_key_directory=keys / "snapshot" / "online",
                    )
                )
            with self.assertRaisesRegex(ValueError, "must be disjoint"):
                MODULE.refresh_online_metadata(
                    Namespace(
                        **common,
                        output=keys / "snapshot" / "online" / "repository",
                        snapshot_key_directory=keys / "snapshot" / "online",
                        timestamp_key_directory=keys / "timestamp" / "online",
                    )
                )

    def test_online_refresh_cannot_copy_embedded_private_keys_to_output(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            repository = root / "repository"
            self.build_repository(
                repository,
                trusted_root,
                keys,
                artifacts,
                manifest,
                1,
            )
            embedded_keys = repository / "PRIVATE_KEYS"
            shutil.move(keys, embedded_keys)
            output = root / "public-output"
            with self.assertRaisesRegex(
                ValueError,
                "unexpected top-level|must be disjoint",
            ):
                MODULE.refresh_online_metadata(
                    Namespace(
                        repository=repository,
                        output=output,
                        snapshot_key_directory=(
                            embedded_keys / "snapshot" / "online"
                        ),
                        timestamp_key_directory=(
                            embedded_keys / "timestamp" / "online"
                        ),
                        snapshot_expires=utc_after(2),
                        timestamp_expires=utc_after(1),
                        allow_development_test_keys=True,
                    )
                )
            self.assertFalse(output.exists())

    def test_sequence_after_one_requires_authenticated_previous_repo(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            with self.assertRaisesRegex(
                ValueError,
                "requires --previous-repository",
            ):
                self.build_repository(
                    root / "repository",
                    trusted_root,
                    keys,
                    artifacts,
                    manifest,
                    2,
                )

    def test_release_manifest_policy_matches_desktop_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            records = []
            matrix = (
                ("windows", "x64", "installer"),
                ("windows", "arm64", "msix"),
                ("ubuntu", "x64", "deb"),
                ("debian", "x64", "deb"),
                ("freebsd", "x64", "pkg"),
                ("macos", "x86_64", "pkg"),
                ("macos", "arm64", "pkg"),
            )
            for index, (platform, arch, kind) in enumerate(matrix):
                name = f"artifact-{index}.bin"
                payload = f"payload-{index}".encode()
                (artifacts / name).write_bytes(payload)
                records.append(
                    {
                        "arch": arch,
                        "bytes": len(payload),
                        "kind": kind,
                        "name": name,
                        "platform": platform,
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "url": f"https://example.invalid/{name}",
                    }
                )
            manifest = root / "manifest.json"
            value = {
                "artifacts": records,
                "channel": "beta",
                "commit": "1" * 40,
                "published_at": "2026-07-28T00:00:00Z",
                "schema": "org.scenelith.orkela.update.v1",
                "version": "0.3.0-alpha.6",
            }
            manifest.write_text(json.dumps(value), encoding="utf-8")
            MODULE.load_release_manifest(manifest, artifacts)

            mobile = artifacts / "debug.zip"
            mobile.write_bytes(b"debug")
            value["artifacts"].append(
                {
                    "arch": "multi",
                    "bytes": 5,
                    "kind": "tested-debug-bundle",
                    "name": mobile.name,
                    "platform": "android",
                    "sha256": hashlib.sha256(b"debug").hexdigest(),
                    "url": "https://example.invalid/debug.zip",
                }
            )
            manifest.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not allowlisted"):
                MODULE.load_release_manifest(manifest, artifacts)

    def test_client_rotates_root_only_with_old_and_new_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            v1_bootstrap = root / "v1-root.json"
            v1_bootstrap.write_bytes(trusted_root.read_bytes())
            first = root / "first"
            self.build_repository(
                first,
                trusted_root,
                keys,
                artifacts,
                manifest,
                1,
            )

            v2 = MODULE.Metadata.from_file(str(trusted_root))
            old_signers = [
                CryptoSigner(
                    load_pem_private_key(path.read_bytes(), password=None)
                )
                for path in sorted(keys.glob("root/*/root-*.pem"))
            ]
            new_signers = [
                CryptoSigner.generate_ed25519()
                for _ in range(3)
            ]
            v2.signed.version = 2
            for signer in new_signers:
                v2.signed.keys[
                    signer.public_key.keyid
                ] = signer.public_key
            v2.signed.roles["root"].keyids = [
                signer.public_key.keyid for signer in new_signers
            ]
            v2.signed.roles["root"].threshold = 2
            v2.signatures.clear()
            for signer in old_signers + new_signers:
                v2.sign(signer, append=bool(v2.signatures))
            trusted_root.unlink()
            MODULE.write_metadata(trusted_root, v2)
            MODULE.write_metadata(trusted_root.parent / "2.root.json", v2)

            second = root / "second"
            self.build_repository(
                second,
                trusted_root,
                keys,
                artifacts,
                manifest,
                2,
                previous_repository=first,
            )
            state = root / "client"
            arguments = Namespace(
                root=v1_bootstrap,
                repository=first,
                state=state,
                channel="beta",
                platform="windows",
                architecture="x64",
                kind="installer",
                current_version="0.3.0-alpha.0",
                allow_development_test_keys=True,
            )
            MODULE.verify(arguments)
            arguments.repository = second
            MODULE.verify(arguments)
            rotated = MODULE.Metadata.from_file(str(state / "root.json"))
            self.assertEqual(rotated.signed.version, 2)

    def test_root_rotation_rejects_old_only_and_new_only_signatures(
        self,
    ) -> None:
        for signature_set in ("old-only", "new-only"):
            with self.subTest(signature_set=signature_set):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    trusted_root, keys, artifacts, manifest = (
                        self.make_fixture(root)
                    )
                    v2 = MODULE.Metadata.from_file(str(trusted_root))
                    old_signers = [
                        CryptoSigner(
                            load_pem_private_key(
                                path.read_bytes(),
                                password=None,
                            )
                        )
                        for path in sorted(
                            keys.glob("root/*/root-*.pem")
                        )
                    ]
                    new_signers = [
                        CryptoSigner.generate_ed25519()
                        for _ in range(3)
                    ]
                    v2.signed.version = 2
                    for signer in new_signers:
                        v2.signed.keys[
                            signer.public_key.keyid
                        ] = signer.public_key
                    v2.signed.roles["root"].keyids = [
                        signer.public_key.keyid
                        for signer in new_signers
                    ]
                    v2.signed.roles["root"].threshold = 2
                    v2.signatures.clear()
                    selected = (
                        old_signers
                        if signature_set == "old-only"
                        else new_signers
                    )
                    for signer in selected:
                        v2.sign(signer, append=bool(v2.signatures))
                    trusted_root.unlink()
                    MODULE.write_metadata(trusted_root, v2)
                    MODULE.write_metadata(
                        trusted_root.parent / "2.root.json",
                        v2,
                    )
                    with self.assertRaises(UnsignedMetadataError):
                        self.build_repository(
                            root / "repository",
                            trusted_root,
                            keys,
                            artifacts,
                            manifest,
                            1,
                        )

    def test_missing_intermediate_root_history_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            metadata = MODULE.Metadata.from_file(str(trusted_root))
            metadata.signed.version = 3
            metadata.signatures.clear()
            MODULE.sign_with_role(
                metadata,
                metadata.signed,
                "root",
                sorted((keys / "root").iterdir()),
            )
            trusted_root.unlink()
            MODULE.write_metadata(trusted_root, metadata)
            MODULE.write_metadata(trusted_root.parent / "3.root.json", metadata)
            with self.assertRaisesRegex(ValueError, "missing 2.root.json"):
                self.build_repository(
                    root / "repository",
                    trusted_root,
                    keys,
                    artifacts,
                    manifest,
                    1,
                )

    def test_test_root_cannot_launder_itself_into_production_profile(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted_root, keys, artifacts, manifest = self.make_fixture(root)
            metadata = MODULE.Metadata.from_file(str(trusted_root))
            metadata.signed.version = 2
            metadata.signed.unrecognized_fields["orkela"][
                "test_keys"
            ] = False
            metadata.signatures.clear()
            MODULE.sign_with_role(
                metadata,
                metadata.signed,
                "root",
                sorted((keys / "root").iterdir()),
            )
            trusted_root.unlink()
            MODULE.write_metadata(trusted_root, metadata)
            MODULE.write_metadata(trusted_root.parent / "2.root.json", metadata)
            with self.assertRaisesRegex(ValueError, "trust-key profile"):
                self.build_repository(
                    root / "repository",
                    trusted_root,
                    keys,
                    artifacts,
                    manifest,
                    1,
                    allow_test_keys=False,
                )

    def test_release_ledger_rejects_version_equivocation_and_downgrade(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            ledger = MODULE.validate_release_ledger(
                state,
                "beta",
                "0.3.0-alpha.2",
                "2" * 40,
                2,
                "a" * 64,
                "d" * 64,
                [],
                "0.3.0-alpha.0",
                "windows/x64/installer",
                False,
            )
            MODULE.write_json_atomic(
                state / "orkela-release-ledger.json",
                ledger,
            )
            with self.assertRaisesRegex(ValueError, "equivocation"):
                MODULE.validate_release_ledger(
                    state,
                    "beta",
                    "0.3.0-alpha.2",
                    "3" * 40,
                    2,
                    "b" * 64,
                    "d" * 64,
                    [],
                    "0.3.0-alpha.0",
                    "windows/x64/installer",
                    True,
                )
            with self.assertRaisesRegex(ValueError, "downgrade"):
                MODULE.validate_release_ledger(
                    state,
                    "beta",
                    "0.3.0-alpha.1",
                    "1" * 40,
                    3,
                    "c" * 64,
                    "e" * 64,
                    [],
                    "0.3.0-alpha.0",
                    "windows/x64/installer",
                    True,
                )

    def test_existing_trust_rejects_missing_or_wrong_ledger_schema(
        self,
    ) -> None:
        for corruption in ("missing", "wrong-schema"):
            with self.subTest(corruption=corruption):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    trusted_root, keys, artifacts, manifest = (
                        self.make_fixture(root)
                    )
                    repository = root / "repository"
                    self.build_repository(
                        repository,
                        trusted_root,
                        keys,
                        artifacts,
                        manifest,
                        1,
                    )
                    state = root / "client"
                    arguments = Namespace(
                        root=trusted_root,
                        repository=repository,
                        state=state,
                        channel="beta",
                        platform="windows",
                        architecture="x64",
                        kind="installer",
                        current_version="0.3.0-alpha.0",
                        allow_development_test_keys=True,
                    )
                    MODULE.verify(arguments)
                    ledger_path = state / "orkela-release-ledger.json"
                    if corruption == "missing":
                        ledger_path.unlink()
                        expected = "has no release ledger"
                    else:
                        value = json.loads(
                            ledger_path.read_text(encoding="utf-8")
                        )
                        value["schema"] = "attacker.invalid"
                        ledger_path.write_text(
                            json.dumps(value),
                            encoding="utf-8",
                        )
                        expected = "schema is invalid"
                    before = tree_snapshot(state)
                    with self.assertRaisesRegex(ValueError, expected):
                        MODULE.verify(arguments)
                    self.assertEqual(tree_snapshot(state), before)
if __name__ == "__main__":
    unittest.main()
