"""Rate-match an official opusenc build by complete Ogg file bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import wave


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as source:
        return source.getnframes() / source.getframerate()


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--encoder", type=Path, required=True)
    parser.add_argument("--decoder", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target-bytes", type=int, required=True)
    parser.add_argument("--mode", choices=("music", "speech"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--decoded", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_arguments()
    if args.target_bytes <= 0:
        raise ValueError("target bytes must be positive")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    candidates = args.output.parent / f".{args.output.stem}-candidates"
    candidates.mkdir(parents=True, exist_ok=True)

    duration = _duration_seconds(args.source)
    nominal_step = round(args.target_bytes * 8 / duration / 100)
    lower = max(50, round(nominal_step * 0.45))
    upper = min(5100, max(lower + 1, round(nominal_step * 1.65)))
    encoded: dict[int, tuple[Path, int]] = {}

    def encode(step: int) -> tuple[Path, int]:
        bounded = min(5100, max(50, step))
        if bounded in encoded:
            return encoded[bounded]
        candidate = candidates / f"{bounded}.opus"
        subprocess.run(
            [
                str(args.encoder),
                "--quiet",
                f"--{args.mode}",
                "--vbr",
                "--comp",
                "10",
                "--framesize",
                "20",
                "--expect-loss",
                "0",
                "--max-delay",
                "1000",
                "--padding",
                "0",
                "--discard-comments",
                "--serial",
                "1",
                "--bitrate",
                f"{bounded / 10:.1f}",
                str(args.source),
                str(candidate),
            ],
            check=True,
        )
        result = (candidate, candidate.stat().st_size)
        encoded[bounded] = result
        return result

    # True VBR does not map requested bitrate directly to complete file bytes.
    # Binary search locates the crossing, then a dense local scan finds the
    # closest complete Ogg file without hundreds of full-track encodes.
    while lower <= upper:
        middle = (lower + upper) // 2
        _, size = encode(middle)
        if size < args.target_bytes:
            lower = middle + 1
        else:
            upper = middle - 1
    crossing = lower
    for step in range(max(50, crossing - 20), min(5100, crossing + 20) + 1):
        encode(step)

    selected_step, (selected_path, selected_size) = min(
        encoded.items(),
        key=lambda item: (
            abs(item[1][1] - args.target_bytes),
            item[1][1] > args.target_bytes,
            item[0],
        ),
    )
    shutil.copyfile(selected_path, args.output)
    subprocess.run(
        [
            str(args.decoder),
            "--quiet",
            str(args.output),
            str(args.decoded),
        ],
        check=True,
    )
    version = subprocess.run(
        [str(args.encoder), "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    report = {
        "schema": "orkela-opus-rate-match-1",
        "source": {
            "path": args.source.name,
            "bytes": args.source.stat().st_size,
            "sha256": _sha256(args.source),
            "duration_seconds": duration,
        },
        "target_complete_bytes": args.target_bytes,
        "opus": {
            "path": args.output.name,
            "decoded_path": args.decoded.name,
            "encoder": version,
            "mode": f"{args.mode} true VBR",
            "complexity": 10,
            "frame_milliseconds": 20,
            "expected_packet_loss_percent": 0,
            "requested_bitrate_kbps": selected_step / 10,
            "complete_bytes": selected_size,
            "complete_byte_delta_from_target": (
                selected_size - args.target_bytes
            ),
            "sha256": _sha256(args.output),
            "decoded_sha256": _sha256(args.decoded),
        },
        "search": {
            "encoded_candidate_count": len(encoded),
            "minimum_requested_bitrate_kbps": min(encoded) / 10,
            "maximum_requested_bitrate_kbps": max(encoded) / 10,
        },
    }
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
