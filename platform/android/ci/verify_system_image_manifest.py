#!/usr/bin/env python3

"""Verify every Android guest-image payload byte against a pinned manifest."""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path, PurePosixPath


HEX64 = re.compile(r"^[0-9a-f]{64}$")
HOST_METADATA = {"package.xml"}


class VerificationError(RuntimeError):
    """The image tree was unsafe, incomplete, extra, or byte-modified."""


def normalized_path(raw: str) -> str:
    path = PurePosixPath(raw)
    if (
        not raw
        or raw.startswith("./")
        or path.is_absolute()
        or "\\" in raw
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise VerificationError(f"unsafe manifest path: {raw!r}")
    return path.as_posix()


def read_manifest(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="strict").splitlines()
    except (OSError, UnicodeError) as error:
        raise VerificationError(f"{path}: unreadable manifest: {error}") from error
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            raise VerificationError(f"{path}: malformed manifest line")
        relative = normalized_path(match.group(2))
        if relative in HOST_METADATA:
            raise VerificationError(
                f"{path}: host metadata must not enter the guest manifest"
            )
        if relative in entries:
            raise VerificationError(f"{path}: duplicate path {relative}")
        entries[relative] = match.group(1)
    if not entries:
        raise VerificationError(f"{path}: empty manifest")
    return entries


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan_image(image: Path) -> dict[str, str]:
    if not image.is_dir():
        raise VerificationError(f"{image}: image directory is absent")
    entries: dict[str, str] = {}
    for path in sorted(image.rglob("*")):
        relative = path.relative_to(image).as_posix()
        if path.is_symlink():
            raise VerificationError(f"{image}: symlink is forbidden: {relative}")
        if path.is_file() and relative not in HOST_METADATA:
            entries[relative] = sha256_file(path)
    if not entries:
        raise VerificationError(f"{image}: image contains no payload files")
    return entries


def verify(image: Path, manifest: Path) -> dict[str, str]:
    expected = read_manifest(manifest)
    actual = scan_image(image)
    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        raise VerificationError(
            f"{image}: manifest coverage mismatch missing={missing} extra={extra}"
        )
    changed = sorted(
        relative
        for relative, digest in actual.items()
        if digest != expected[relative]
    )
    if changed:
        raise VerificationError(f"{image}: byte mismatch: {changed}")
    return actual


def write_canonical(entries: dict[str, str], output: Path) -> None:
    output.write_text(
        "".join(
            f"{digest}  {relative}\n"
            for relative, digest in sorted(entries.items())
        ),
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        entries = verify(args.image, args.manifest)
        if args.output is not None:
            write_canonical(entries, args.output)
    except VerificationError as error:
        parser.exit(1, f"{error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
