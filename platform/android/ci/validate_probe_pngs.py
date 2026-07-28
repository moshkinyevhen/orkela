#!/usr/bin/env python3

"""Validate Android Emulator screenshots without third-party dependencies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys
import zlib


MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_DIMENSION = 8192
MAX_PIXELS = 32 * 1024 * 1024
MAX_PACKED_BYTES = 128 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def paeth(left: int, above: int, upper_left: int) -> int:
    prediction = left + above - upper_left
    left_distance = abs(prediction - left)
    above_distance = abs(prediction - above)
    diagonal_distance = abs(prediction - upper_left)
    if left_distance <= above_distance and left_distance <= diagonal_distance:
        return left
    if above_distance <= diagonal_distance:
        return above
    return upper_left


def validate_png(
    path: Path,
    expected_width: int,
    expected_height: int,
) -> dict[str, int | str]:
    file_size = path.stat().st_size
    if file_size < 45 or file_size > MAX_FILE_BYTES:
        raise ValueError(f"{path.name}: PNG file size exceeds bounds")
    data = path.read_bytes()
    if len(data) != file_size or not data.startswith(PNG_SIGNATURE):
        raise ValueError(f"{path.name}: not a bounded complete PNG")

    offset = len(PNG_SIGNATURE)
    chunks: list[bytes] = []
    idat = bytearray()
    width = height = 0
    bit_depth = color_type = compression = filter_method = interlace = -1
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError(f"{path.name}: truncated chunk header")
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        payload_start = offset + 8
        payload_end = payload_start + length
        chunk_end = payload_end + 4
        if chunk_end > len(data):
            raise ValueError(f"{path.name}: truncated chunk payload")
        expected_crc = struct.unpack(">I", data[payload_end:chunk_end])[0]
        actual_crc = zlib.crc32(kind + data[payload_start:payload_end])
        if actual_crc != expected_crc:
            raise ValueError(f"{path.name}: invalid CRC for {kind!r}")
        chunks.append(kind)
        if len(chunks) == 1:
            if kind != b"IHDR" or length != 13:
                raise ValueError(f"{path.name}: no canonical IHDR")
            width, height = struct.unpack(
                ">II",
                data[payload_start : payload_start + 8],
            )
            (
                bit_depth,
                color_type,
                compression,
                filter_method,
                interlace,
            ) = data[payload_start + 8 : payload_start + 13]
        if kind == b"IDAT":
            idat.extend(data[payload_start:payload_end])
        offset = chunk_end
        if kind == b"IEND":
            break

    if width <= 0 or height <= 0:
        raise ValueError(f"{path.name}: invalid dimensions")
    if width != expected_width or height != expected_height:
        raise ValueError(
            f"{path.name}: dimensions {width}x{height} do not match "
            f"guest display {expected_width}x{expected_height}"
        )
    if b"IDAT" not in chunks or chunks[-1] != b"IEND" or offset != len(data):
        raise ValueError(f"{path.name}: incomplete IDAT/IEND sequence")
    if (
        bit_depth != 8
        or color_type not in (2, 6)
        or compression != 0
        or filter_method != 0
        or interlace != 0
    ):
        raise ValueError(f"{path.name}: unsupported screenshot mode")
    if (
        width > MAX_DIMENSION
        or height > MAX_DIMENSION
        or width * height > MAX_PIXELS
    ):
        raise ValueError(f"{path.name}: dimensions exceed bounds")

    channels = 3 if color_type == 2 else 4
    stride = width * channels
    expected_packed_bytes = height * (stride + 1)
    if expected_packed_bytes > MAX_PACKED_BYTES:
        raise ValueError(f"{path.name}: decompressed data exceeds bounds")
    decompressor = zlib.decompressobj()
    packed = decompressor.decompress(
        bytes(idat),
        expected_packed_bytes + 1,
    )
    if (
        len(packed) != expected_packed_bytes
        or not decompressor.eof
        or decompressor.unconsumed_tail
        or decompressor.unused_data
    ):
        raise ValueError(f"{path.name}: unexpected decompressed size")

    previous = bytearray(stride)
    pixels: list[tuple[int, int, int]] = []
    sampled_alpha: list[int] = []
    source_offset = 0
    x_step = max(1, width // 64)
    y_step = max(1, height // 64)
    for y in range(height):
        filter_type = packed[source_offset]
        source_offset += 1
        row = bytearray(packed[source_offset : source_offset + stride])
        source_offset += stride
        for byte_index in range(stride):
            left = row[byte_index - channels] if byte_index >= channels else 0
            above = previous[byte_index]
            upper_left = (
                previous[byte_index - channels]
                if byte_index >= channels
                else 0
            )
            if filter_type == 1:
                row[byte_index] = (row[byte_index] + left) & 0xFF
            elif filter_type == 2:
                row[byte_index] = (row[byte_index] + above) & 0xFF
            elif filter_type == 3:
                row[byte_index] = (
                    row[byte_index] + ((left + above) >> 1)
                ) & 0xFF
            elif filter_type == 4:
                row[byte_index] = (
                    row[byte_index] + paeth(left, above, upper_left)
                ) & 0xFF
            elif filter_type != 0:
                raise ValueError(f"{path.name}: invalid PNG filter")
        if y % y_step == 0:
            for x in range(0, width, x_step):
                pixel_offset = x * channels
                red, green, blue = row[pixel_offset : pixel_offset + 3]
                alpha = row[pixel_offset + 3] if channels == 4 else 255
                sampled_alpha.append(alpha)
                # Evaluate visible pixels, not hidden RGB values in a fully
                # transparent RGBA buffer.
                pixels.append(
                    (
                        (red * alpha + 127) // 255,
                        (green * alpha + 127) // 255,
                        (blue * alpha + 127) // 255,
                    )
                )
        previous = row

    unique_pixels = len(set(pixels))
    luminance = [
        (54 * red + 183 * green + 19 * blue) >> 8
        for red, green, blue in pixels
    ]
    luminance_span = max(luminance) - min(luminance)
    if unique_pixels < 8 or luminance_span < 8:
        raise ValueError(f"{path.name}: screenshot lacks visual diversity")
    return {
        "file": path.name,
        "width": width,
        "height": height,
        "bytes": len(data),
        "sampled_unique_rgb": unique_pixels,
        "sampled_luminance_span": luminance_span,
        "sampled_alpha_min": min(sampled_alpha),
        "sampled_alpha_max": max(sampled_alpha),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("screenshots", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-width", required=True, type=int)
    parser.add_argument("--expected-height", required=True, type=int)
    args = parser.parse_args()
    if args.expected_width <= 0 or args.expected_height <= 0:
        parser.error("expected display dimensions must be positive")
    try:
        records = [
            validate_png(
                path,
                args.expected_width,
                args.expected_height,
            )
            for path in args.screenshots
        ]
    except (OSError, ValueError, zlib.error) as error:
        print(error, file=sys.stderr)
        return 1
    args.output.write_text(
        json.dumps(
            {
                "schema": 1,
                "screenshots": records,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
