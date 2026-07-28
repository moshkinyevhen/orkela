#!/usr/bin/env python3
"""Generate deterministic Orkela update metadata from release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


@dataclass(frozen=True)
class Artifact:
    path: Path
    platform: str
    architecture: str
    kind: str


def parse_artifact(value: str) -> Artifact:
    parts = value.rsplit(":", 3)
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            "artifact must be PATH:PLATFORM:ARCHITECTURE:KIND"
        )
    path, platform, architecture, kind = parts
    candidate = Path(path)
    if not candidate.is_file():
        raise argparse.ArgumentTypeError(f"artifact does not exist: {path}")
    for label, field in (
        ("platform", platform),
        ("architecture", architecture),
        ("kind", kind),
    ):
        if not field or any(character.isspace() for character in field):
            raise argparse.ArgumentTypeError(
                f"{label} must be a non-empty token"
            )
    return Artifact(candidate, platform, architecture, kind)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_record(artifact: Artifact, base_url: str) -> dict[str, object]:
    filename = artifact.path.name
    return {
        "arch": artifact.architecture,
        "bytes": artifact.path.stat().st_size,
        "kind": artifact.kind,
        "name": filename,
        "platform": artifact.platform,
        "sha256": sha256(artifact.path),
        "url": f"{base_url.rstrip('/')}/{quote(filename)}",
    }


def build_manifest(
    *,
    version: str,
    channel: str,
    commit: str,
    published_at: str,
    base_url: str,
    artifacts: list[Artifact],
) -> dict[str, object]:
    filenames = [artifact.path.name for artifact in artifacts]
    if len(filenames) != len(set(filenames)):
        raise ValueError(
            "release artifact filenames must be globally unique"
        )
    records = sorted(
        (artifact_record(artifact, base_url) for artifact in artifacts),
        key=lambda record: (
            str(record["platform"]),
            str(record["arch"]),
            str(record["kind"]),
            str(record["name"]),
        ),
    )
    return {
        "artifacts": records,
        "channel": channel,
        "commit": commit,
        "published_at": published_at,
        "schema": "org.scenelith.orkela.update.v1",
        "version": version,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--version-file", type=Path, required=True)
    result.add_argument(
        "--channel",
        choices=("stable", "beta", "nightly"),
        required=True,
    )
    result.add_argument("--commit", required=True)
    result.add_argument("--published-at", required=True)
    result.add_argument("--base-url", required=True)
    result.add_argument(
        "--artifact",
        action="append",
        type=parse_artifact,
        required=True,
    )
    result.add_argument("--output", type=Path, required=True)
    return result


def main() -> int:
    arguments = parser().parse_args()
    version = arguments.version_file.read_text(encoding="utf-8").strip()
    if not version:
        raise SystemExit("version file is empty")
    manifest = build_manifest(
        version=version,
        channel=arguments.channel,
        commit=arguments.commit,
        published_at=arguments.published_at,
        base_url=arguments.base_url,
        artifacts=arguments.artifact,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
