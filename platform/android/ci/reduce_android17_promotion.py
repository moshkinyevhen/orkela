#!/usr/bin/env python3

"""Reduce Android 17 cold-boot and exact-APK evidence without fallbacks."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import re
import struct
import xml.etree.ElementTree as ET
import zlib
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any


HEX64 = re.compile(r"^[0-9a-f]{64}$")
FEATURE_TUPLE = (
    "GLDirectMem,HasSharedSlotsHostMemoryAllocator,"
    "-Vulkan,-VulkanNativeSwapchain,-GuestAngle"
)
RENDERER_TUPLE = (
    "setCurrentRenderer: swiftshader swiftshader "
    "gles:Swiftshader Indirect vulkan:Swiftshader Indirect"
)
EXPECTED_BASELINE = {
    "run_id": 30374223297,
    "source_sha": "5dfb64af5db86f5a838d7dfe77ea9ed373fb2dc8",
    "assessment_sha256": (
        "3593de10e5a2a000364639f1d115dd63"
        "f08844bb1d4e2541bc84fc6d17c21478"
    ),
    "status": "GUEST_ANGLE_OFF_BOOT_RECOVERY_ON_SAME_HOST",
}
EXPECTED_EMULATOR = {
    "emulator_version": "37.2.1.0",
    "emulator_revision": "37.2.1",
    "emulator_build_id": 15875889,
    "emulator_archive_sha1": "1c39ceb4bca042b973344d252a051189d367ab83",
    "emulator_archive_sha256": (
        "3fb1f765795b284f864b9b3403d1c5e"
        "1ad0f317eb6522441460001ff660d3d7d"
    ),
    "emulator_archive_size": 346539649,
}
EXPECTED_GRAPHICS_CORRECTION = {
    "requested_feature_overrides": FEATURE_TUPLE,
    "expected_effective": {
        "GlDirectMem": 1,
        "HasSharedSlotsHostMemoryAllocator": 1,
        "GlDma": 1,
        "GlDma2": 0,
        "Vulkan": 0,
        "VulkanNativeSwapchain": 0,
        "GuestVulkanOnly": 0,
    },
    "host_parsed_api_level": 3,
    "read_color_buffer_dma_proxy": (
        "GlDirectMem && HasSharedSlotsHostMemoryAllocator && GlDma"
    ),
    "guest_payload_unmodified": True,
}
EXPECTED_PROFILES = {
    "37": {
        "page_size": 4096,
        "system_image": "system-images;android-37.0;google_apis;x86_64",
        "system_fingerprint": (
            "google/sdk_gphone64_x86_64/emu64xa:17/"
            "CE2A.260420.019/15611780:userdebug/dev-keys"
        ),
    },
    "37-16k": {
        "page_size": 16384,
        "system_image": (
            "system-images;android-37.0;google_apis_ps16k;x86_64"
        ),
        "system_fingerprint": (
            "google/sdk_gphone16k_x86_64/emu64xa16k:17/"
            "CE2A.260420.019/15611780:userdebug/dev-keys"
        ),
    },
}
HOST_KEYS = (
    "source_sha",
    "run_id",
    "run_attempt",
    "runner_name",
    "runner_os",
    "runner_arch",
    "image_os",
    "image_version",
    "host_kernel_boot_id",
    "host_kernel_release",
    "host_kvm_identity",
    "emulator_bin",
)


ANALYZER_PATH = Path(__file__).with_name("analyze_guest_boot_evidence.py")
ANALYZER_SPEC = importlib.util.spec_from_file_location(
    "orkela_android_guest_analyzer",
    ANALYZER_PATH,
)
if ANALYZER_SPEC is None or ANALYZER_SPEC.loader is None:
    raise RuntimeError("cannot load Android guest evidence analyzer")
GUEST_ANALYZER = importlib.util.module_from_spec(ANALYZER_SPEC)
ANALYZER_SPEC.loader.exec_module(GUEST_ANALYZER)


class GateError(RuntimeError):
    """A promotion invariant was absent, duplicated, or contradictory."""


def fail(message: str) -> None:
    raise GateError(message)


def object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            fail(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=object_without_duplicates,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        fail(f"{path}: invalid JSON: {error}")
    if not isinstance(value, dict):
        fail(f"{path}: top-level JSON value must be an object")
    return value


def validate_contract(contract: dict[str, Any]) -> None:
    require_equal(contract, "schema", 1, "promotion contract")
    require_equal(
        contract,
        "baseline_evidence",
        EXPECTED_BASELINE,
        "promotion contract",
    )
    require_equal(
        contract,
        "emulator",
        EXPECTED_EMULATOR,
        "promotion contract",
    )
    require_equal(
        contract,
        "graphics_correction",
        EXPECTED_GRAPHICS_CORRECTION,
        "promotion contract",
    )
    profiles = contract.get("profiles")
    if not isinstance(profiles, dict) or set(profiles) != set(EXPECTED_PROFILES):
        fail("promotion contract: exact 4 KiB and 16 KiB profiles are required")
    for name, expected in EXPECTED_PROFILES.items():
        profile = profiles.get(name)
        if not isinstance(profile, dict):
            fail(f"promotion contract: profile {name} must be an object")
        expected_keys = set(expected) | {"system_image_manifest_sha256"}
        if set(profile) != expected_keys:
            fail(f"promotion contract: unexpected profile {name} fields")
        for key, value in expected.items():
            require_equal(profile, key, value, f"promotion profile {name}")
        if not HEX64.fullmatch(profile["system_image_manifest_sha256"]):
            fail(f"promotion profile {name}: invalid image manifest SHA-256")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_manifest_path(raw: str) -> str:
    if raw.startswith("./"):
        raw = raw[2:]
    path = PurePosixPath(raw)
    if (
        not raw
        or path.is_absolute()
        or "\\" in raw
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        fail(f"unsafe evidence manifest path: {raw!r}")
    return path.as_posix()


def verify_raw_manifest(root: Path, record_name: str, expected_hash: str) -> None:
    manifest = root / "RAW-EVIDENCE-SHA256SUMS"
    if not HEX64.fullmatch(expected_hash):
        fail(f"{root}: invalid raw manifest SHA-256")
    if sha256_file(manifest) != expected_hash:
        fail(f"{root}: raw manifest SHA-256 mismatch")

    entries: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            fail(f"{manifest}: malformed sha256sum line")
        relative = normalized_manifest_path(match.group(2))
        if relative in entries:
            fail(f"{manifest}: duplicate path {relative}")
        entries[relative] = match.group(1)

    actual_files: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            fail(f"{root}: symlink is forbidden: {path}")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            if relative not in (record_name, "RAW-EVIDENCE-SHA256SUMS"):
                actual_files.add(relative)
    if set(entries) != actual_files:
        missing = sorted(actual_files - set(entries))
        extra = sorted(set(entries) - actual_files)
        fail(f"{root}: raw manifest coverage mismatch missing={missing} extra={extra}")
    for relative, expected in entries.items():
        if sha256_file(root / relative) != expected:
            fail(f"{root}: evidence hash mismatch: {relative}")


def require_equal(record: dict[str, Any], key: str, expected: Any, scope: str) -> None:
    if record.get(key) != expected:
        fail(f"{scope}: {key} mismatch: {record.get(key)!r} != {expected!r}")


def validate_guest_analysis(
    path: Path,
    logcat_path: Path,
    getprop_path: Path,
    fingerprint: str,
) -> None:
    analysis = read_json(path)
    try:
        recomputed = GUEST_ANALYZER.analyze(
            logcat_path.read_text(encoding="utf-8", errors="replace"),
            getprop_path.read_text(encoding="utf-8", errors="replace"),
        )
    except OSError as error:
        fail(f"{path}: cannot reparse raw guest evidence: {error}")
    if analysis != recomputed:
        fail(f"{path}: derived guest analysis contradicts raw evidence")
    for key in (
        "surfaceflinger_tombstone_records",
        "surfaceflinger_abort_tombstones",
        "coherent_memory_angle_abort_tombstones",
        "surfaceflinger_fatal_signals",
        "unsupported_virtual_memory_fatals",
    ):
        require_equal(analysis, key, 0, str(path))
    require_equal(analysis, "boot_completed_property", "1", str(path))
    if analysis.get("updatable_crashing_property") == "1":
        fail(f"{path}: updatable crashing state is active")
    if analysis.get("updatable_crashing_process_name") == "surfaceflinger":
        fail(f"{path}: SurfaceFlinger remains in updatable-crashing state")
    require_equal(analysis, "observed_fingerprint", fingerprint, str(path))
    require_equal(analysis, "boot_hardware_egl", "", str(path))
    require_equal(analysis, "hardware_egl", "emulation", str(path))


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


def parse_png(path: Path) -> dict[str, int]:
    try:
        data = path.read_bytes()
    except OSError as error:
        fail(f"{path}: unreadable PNG: {error}")
    if len(data) < 45 or len(data) > 64 * 1024 * 1024:
        fail(f"{path}: PNG size is outside the evidence bound")
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        fail(f"{path}: invalid PNG signature")

    offset = 8
    width = height = channels = 0
    idat = bytearray()
    chunks: list[bytes] = []
    while offset < len(data):
        if offset + 12 > len(data):
            fail(f"{path}: truncated PNG chunk header")
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        payload_start = offset + 8
        payload_end = payload_start + length
        chunk_end = payload_end + 4
        if chunk_end > len(data):
            fail(f"{path}: truncated PNG chunk payload")
        payload = data[payload_start:payload_end]
        expected_crc = struct.unpack(">I", data[payload_end:chunk_end])[0]
        if zlib.crc32(kind + payload) != expected_crc:
            fail(f"{path}: invalid PNG CRC for {kind!r}")
        chunks.append(kind)
        if len(chunks) == 1:
            if kind != b"IHDR" or length != 13:
                fail(f"{path}: PNG has no canonical IHDR")
            (
                width,
                height,
                bit_depth,
                color_type,
                compression,
                filter_method,
                interlace,
            ) = struct.unpack(">IIBBBBB", payload)
            if (
                bit_depth != 8
                or color_type not in (2, 6)
                or compression != 0
                or filter_method != 0
                or interlace != 0
            ):
                fail(f"{path}: unsupported canonical screenshot mode")
            channels = 3 if color_type == 2 else 4
            if (
                width <= 0
                or height <= 0
                or width > 4096
                or height > 4096
            ):
                fail(f"{path}: invalid screenshot dimensions")
        elif kind == b"IHDR":
            fail(f"{path}: duplicate PNG IHDR")
        if kind == b"IDAT":
            idat.extend(payload)
            if len(idat) > 64 * 1024 * 1024:
                fail(f"{path}: compressed screenshot exceeds bounds")
        offset = chunk_end
        if kind == b"IEND":
            break
    if (
        not idat
        or b"IDAT" not in chunks
        or not chunks
        or chunks[-1] != b"IEND"
        or offset != len(data)
    ):
        fail(f"{path}: incomplete PNG stream")

    stride = width * channels
    expected_packed_bytes = height * (stride + 1)
    if expected_packed_bytes > 64 * 1024 * 1024:
        fail(f"{path}: decompressed screenshot exceeds bounds")
    decompressor = zlib.decompressobj()
    try:
        packed = decompressor.decompress(
            bytes(idat),
            expected_packed_bytes + 1,
        )
    except zlib.error as error:
        fail(f"{path}: invalid PNG deflate stream: {error}")
    if (
        len(packed) != expected_packed_bytes
        or not decompressor.eof
        or decompressor.unconsumed_tail
        or decompressor.unused_data
    ):
        fail(f"{path}: unexpected decompressed screenshot size")

    previous = bytearray(stride)
    pixels: list[tuple[int, int, int]] = []
    source_offset = 0
    x_step = max(1, width // 64)
    y_step = max(1, height // 64)
    for y in range(height):
        filter_type = packed[source_offset]
        source_offset += 1
        row = bytearray(packed[source_offset:source_offset + stride])
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
                fail(f"{path}: invalid PNG filter")
        if y % y_step == 0:
            for x in range(0, width, x_step):
                pixel_offset = x * channels
                pixels.append(tuple(row[pixel_offset:pixel_offset + 3]))
        previous = row
    if not pixels:
        fail(f"{path}: PNG yielded no sampled pixels")
    luminance = [
        (54 * red + 183 * green + 19 * blue) >> 8
        for red, green, blue in pixels
    ]
    return {
        "width": width,
        "height": height,
        "bytes": len(data),
        "sampled_unique_rgb": len(set(pixels)),
        "sampled_luminance_span": max(luminance) - min(luminance),
    }


def require_regex_count(
    text: str,
    pattern: str,
    expected: int,
    scope: str,
) -> None:
    count = len(re.findall(pattern, text, flags=re.MULTILINE))
    if count != expected:
        fail(f"{scope}: expected {expected} matches for {pattern!r}, found {count}")


def validate_emulator_log(root: Path) -> None:
    path = root / "logs" / "emulator.log"
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as error:
        fail(f"{path}: unreadable Emulator log: {error}")
    require_regex_count(
        text,
        r"Android emulator version 37\.2\.1\.0",
        1,
        str(path),
    )
    require_regex_count(
        text,
        rf"parseAndApplyOverrides, overrides='{re.escape(FEATURE_TUPLE)}'",
        1,
        str(path),
    )
    require_regex_count(
        text,
        r"Feature 'GLDirectMem'.*overridden to 'enabled'",
        1,
        str(path),
    )
    require_regex_count(
        text,
        r"Feature 'HasSharedSlotsHostMemoryAllocator'.*overridden to 'enabled'",
        1,
        str(path),
    )
    require_regex_count(
        text,
        r"Feature 'GuestAngle'.*overridden to 'disabled'",
        1,
        str(path),
    )
    require_regex_count(
        text,
        r"gfxstreamFeature:Vulkan\s*=\s*0\s*$",
        1,
        str(path),
    )
    require_regex_count(
        text,
        r"gfxstreamFeature:VulkanNativeSwapchain\s*=\s*0\s*$",
        1,
        str(path),
    )
    require_regex_count(
        text,
        r"gfxstreamFeature:GuestVulkanOnly\s*=\s*0\s*$",
        1,
        str(path),
    )
    require_regex_count(
        text,
        r"gfxstreamFeature:HasSharedSlotsHostMemoryAllocator\s*=\s*1\s*$",
        1,
        str(path),
    )
    require_regex_count(
        text,
        r"gfxstreamFeature:GlDma\s*=\s*1\s*$",
        1,
        str(path),
    )
    require_regex_count(
        text,
        r"gfxstreamFeature:GlDma2\s*=\s*0\s*$",
        1,
        str(path),
    )
    require_regex_count(
        text,
        r"gfxstreamFeature:GlDirectMem\s*=\s*1\s*$",
        1,
        str(path),
    )
    require_regex_count(
        text,
        r"Deciding if GLDirectMem/Vulkan should be enabled.*API level: 3 ",
        1,
        str(path),
    )
    require_regex_count(
        text,
        re.escape(RENDERER_TUPLE),
        1,
        str(path),
    )
    forbidden = (
        r"Auto-enabled GuestAngle feature for VulkanNativeSwapchain|"
        r"required for VulkanNativeSwapchain|"
        r"Initializing VkEmulation features|"
        r"useVulkanComposition:\s*true|"
        r"useVulkanNativeSwapchain:\s*true|"
        r"Performing composition using CompositorVk|"
        r"Failed to initialize the compositor|"
        r"Failed to initialize FrameBuffer|"
        r"Could not start renderer"
    )
    require_regex_count(text, forbidden, 0, str(path))
    ordered_markers = (
        f"parseAndApplyOverrides, overrides='{FEATURE_TUPLE}'",
        "Feature 'GLDirectMem'",
        "Feature 'HasSharedSlotsHostMemoryAllocator'",
        "Feature 'GuestAngle'",
        "API level: 3 ",
        RENDERER_TUPLE,
        "gfxstreamFeature:Vulkan = 0",
        "gfxstreamFeature:HasSharedSlotsHostMemoryAllocator = 1",
        "gfxstreamFeature:VulkanNativeSwapchain = 0",
        "gfxstreamFeature:GuestVulkanOnly = 0",
        "gfxstreamFeature:GlDma = 1",
        "gfxstreamFeature:GlDma2 = 0",
        "gfxstreamFeature:GlDirectMem = 1",
    )
    positions = [text.find(marker) for marker in ordered_markers]
    if any(position < 0 for position in positions):
        fail(f"{path}: an ordered graphics marker is absent")
    if positions != sorted(positions) or len(set(positions)) != len(positions):
        fail(f"{path}: graphics initialization order is contradictory")


def validate_emulator_command(root: Path, record: dict[str, Any]) -> None:
    path = root / "EMULATOR-COMMAND.txt"
    try:
        command = path.read_text(
            encoding="utf-8",
            errors="strict",
        ).splitlines()
    except (OSError, UnicodeError) as error:
        fail(f"{path}: unreadable Emulator command: {error}")
    host = record["host"]
    emulator_bin = host.get("emulator_bin")
    if not isinstance(emulator_bin, str) or re.fullmatch(
        r".*/android-emulator-37\.2\.1-15875889/emulator/emulator",
        emulator_bin,
    ) is None:
        fail(f"{path}: Emulator binary path is not the pinned extraction")
    serial = host.get("device_serial", "")
    serial_match = re.fullmatch(r"emulator-(\d+)", serial)
    if serial_match is None:
        fail(f"{path}: invalid Emulator device serial")
    expected = [
        emulator_bin,
        f"@{host['avd_name']}",
        "-no-window",
        "-no-boot-anim",
        "-no-snapshot",
        "-no-snapshot-load",
        "-no-snapshot-save",
        "-no-audio",
        "-accel",
        "on",
        "-cores",
        "2",
        "-memory",
        "4096",
        "-partition-size",
        "4096",
        "-gpu",
        "swiftshader",
        "-port",
        serial_match.group(1),
        "-verbose",
        "-feature",
        FEATURE_TUPLE,
    ]
    if command != expected:
        fail(f"{path}: Emulator launch arguments differ from the contract")


def validate_soak_evidence(root: Path, record: dict[str, Any]) -> None:
    screenshot_path = root / "COMPOSITOR-SOAK-SCREENSHOTS.json"
    screenshots = read_json(screenshot_path)
    require_equal(
        screenshots,
        "soak_seconds",
        record["compositor_soak_seconds"],
        str(screenshot_path),
    )
    records = screenshots.get("screenshots")
    if not isinstance(records, list) or len(records) != 4:
        fail(f"{screenshot_path}: exactly four screenshots are required")
    expected_names = {
        f"compositor-soak-{index}.png"
        for index in range(1, 5)
    }
    actual_names: set[str] = set()
    for item in records:
        if not isinstance(item, dict):
            fail(f"{screenshot_path}: screenshot record must be an object")
        name = item.get("file")
        if name in actual_names or name not in expected_names:
            fail(f"{screenshot_path}: unexpected or duplicate screenshot {name!r}")
        actual_names.add(name)
        for key in ("width", "height", "bytes"):
            if not isinstance(item.get(key), int) or item[key] <= 0:
                fail(f"{screenshot_path}: invalid {key} for {name}")
        if not isinstance(item.get("sampled_unique_rgb"), int):
            fail(f"{screenshot_path}: invalid diversity count for {name}")
        if item["sampled_unique_rgb"] < 8:
            fail(f"{screenshot_path}: insufficient color diversity for {name}")
        if not isinstance(item.get("sampled_luminance_span"), int):
            fail(f"{screenshot_path}: invalid luminance span for {name}")
        if item["sampled_luminance_span"] < 8:
            fail(f"{screenshot_path}: insufficient luminance span for {name}")
        png_path = root / name
        recomputed = parse_png(png_path)
        for key, value in recomputed.items():
            require_equal(item, key, value, str(png_path))
    if actual_names != expected_names:
        fail(f"{screenshot_path}: incomplete screenshot set")

    soak_path = root / "logs" / "compositor-soak.log"
    try:
        soak_text = soak_path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as error:
        fail(f"{soak_path}: unreadable soak ledger: {error}")
    rows = list(csv.DictReader(io.StringIO(soak_text)))
    if len(rows) != 24:
        fail(f"{soak_path}: expected 24 observations, found {len(rows)}")
    uptime_path = root / "COMPOSITOR-SOAK-UPTIME.txt"
    try:
        uptime_lines = uptime_path.read_text(
            encoding="utf-8",
            errors="strict",
        ).splitlines()
    except (OSError, UnicodeError) as error:
        fail(f"{uptime_path}: unreadable raw monotonic clock: {error}")
    if len(uptime_lines) != 2:
        fail(f"{uptime_path}: expected exactly two monotonic clock values")
    values: dict[str, Decimal] = {}
    for line in uptime_lines:
        match = re.fullmatch(
            r"(start_uptime_seconds|end_uptime_seconds)="
            r"([0-9]+(?:\.[0-9]+)?)",
            line,
        )
        if match is None or match.group(1) in values:
            fail(f"{uptime_path}: malformed or duplicate clock value")
        try:
            values[match.group(1)] = Decimal(match.group(2))
        except InvalidOperation:
            fail(f"{uptime_path}: invalid decimal clock value")
    if set(values) != {"start_uptime_seconds", "end_uptime_seconds"}:
        fail(f"{uptime_path}: incomplete monotonic clock")
    start_uptime = values["start_uptime_seconds"]
    end_uptime = values["end_uptime_seconds"]
    elapsed = end_uptime - start_uptime
    if elapsed < Decimal(120):
        fail(f"{uptime_path}: measured compositor soak is shorter than 120 s")
    if int(elapsed) != record["compositor_soak_seconds"]:
        fail(f"{uptime_path}: record duration contradicts monotonic clock")

    previous_uptime = start_uptime
    for expected_observation, row in enumerate(rows, start=1):
        if row.get("observation") != str(expected_observation):
            fail(f"{soak_path}: non-canonical observation sequence")
        try:
            current_uptime = Decimal(row.get("host_uptime_seconds", ""))
        except InvalidOperation:
            fail(f"{soak_path}: invalid observation monotonic clock")
        if current_uptime < previous_uptime or current_uptime > end_uptime:
            fail(f"{soak_path}: non-monotonic or out-of-range clock")
        previous_uptime = current_uptime
        if row.get("surfaceflinger_pid") != record["initial_surfaceflinger_pid"]:
            fail(f"{soak_path}: SurfaceFlinger PID changed")
        if row.get("package") != "Service package: found":
            fail(f"{soak_path}: package service was unhealthy")
        if row.get("surfaceflinger") != "Service SurfaceFlinger: found":
            fail(f"{soak_path}: SurfaceFlinger service was unhealthy")
        if row.get("mount") != "Service mount: found":
            fail(f"{soak_path}: mount service was unhealthy")
        volumes = row.get("volumes", "")
        if "private mounted" not in volumes or "emulated;0 mounted" not in volumes:
            fail(f"{soak_path}: storage volumes were unhealthy")


def read_strict_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as error:
        fail(f"{path}: unreadable UTF-8 evidence: {error}")


def read_exact_key_values(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in read_strict_text(path).splitlines():
        match = re.fullmatch(r"([a-z0-9_]+)=(.*)", line)
        if match is None or match.group(1) in result:
            fail(f"{path}: malformed or duplicate key/value evidence")
        result[match.group(1)] = match.group(2)
    return result


def validate_raw_runtime_identity(
    root: Path,
    record: dict[str, Any],
    profile: dict[str, Any],
) -> None:
    page_path = root / "PAGE-SIZE.txt"
    if read_strict_text(page_path) != f"{profile['page_size']}\n":
        fail(f"{page_path}: raw guest page size contradicts the profile")
    selinux_path = root / "SELINUX.txt"
    if read_strict_text(selinux_path) != "Enforcing\n":
        fail(f"{selinux_path}: raw SELinux mode is not enforcing")

    graphics_path = root / "EMULATOR-GRAPHICS-CONFIGURATION.txt"
    graphics = read_exact_key_values(graphics_path)
    expected = {
        "fingerprint": profile["system_fingerprint"],
        "build_id": "CE2A.260420.019",
        "selinux": "Enforcing",
        "renderer_egl": "emulation",
        "boot_hardware_egl": "empty",
        "renderer_transport": record["renderer_transport"],
        "effective_renderer": RENDERER_TUPLE,
        "emulator": record["emulator_version"],
        "gpu_mode": "swiftshader",
        "gles_backend": "emulation",
        "vulkan_backend": "disabled",
        "emulator_feature_overrides": FEATURE_TUPLE,
        "host_api_decision_level": "3",
        "effective_gl_direct_mem": "1",
        "effective_has_shared_slots_host_memory_allocator": "1",
        "effective_gl_dma": "1",
        "effective_gl_dma2": "0",
        "emulator_archive_sha256": record["emulator_archive_sha256"],
        "guest_luma_sampling": record["luma_sampling"],
        "surfaceflinger_pid": record["initial_surfaceflinger_pid"],
    }
    if graphics != expected:
        fail(f"{graphics_path}: graphics identity is not exact")


def validate_runtime_raw_evidence(
    root: Path,
    record: dict[str, Any],
    expected: dict[str, str],
) -> None:
    instrumentation_path = root / "logs" / "instrumentation.log"
    instrumentation = read_strict_text(instrumentation_path)
    require_regex_count(
        instrumentation,
        r"^INSTRUMENTATION_CODE: -1\r?$",
        1,
        str(instrumentation_path),
    )
    if re.search(
        r"INSTRUMENTATION_FAILED|FAILURES!!!|Process crashed|FATAL EXCEPTION",
        instrumentation,
        flags=re.IGNORECASE,
    ):
        fail(f"{instrumentation_path}: instrumentation failure marker found")

    smoke_path = root / "orkela-ci-smoke.json"
    smoke = read_json(smoke_path)
    smoke_expected = {
        "schema": 1,
        "status": "pass",
        "sample_rate": 44100,
        "channels": 2,
        "frames": 352800,
        "pcm16_sha256": expected["expected_pcm16_sha256"],
    }
    if smoke != smoke_expected:
        fail(f"{smoke_path}: native decode smoke record is not exact")
    require_equal(record, "native_decode", "pass", str(root))
    require_equal(record, "decoded_frames", smoke["frames"], str(root))
    require_equal(
        record,
        "decoded_sample_rate",
        smoke["sample_rate"],
        str(root),
    )
    require_equal(record, "decoded_channels", smoke["channels"], str(root))

    activity_path = root / "logs" / "activity-start.log"
    activity = read_strict_text(activity_path)
    if not re.search(r"^Status:\s+ok\r?$", activity, flags=re.MULTILINE):
        fail(f"{activity_path}: activity start did not report success")
    if not re.search(
        r"^Activity:\s+org\.scenelith\.orkela/\.MainActivity\r?$",
        activity,
        flags=re.MULTILINE,
    ):
        fail(f"{activity_path}: wrong activity was launched")

    xml_path = root / "orkela-window.xml"
    try:
        xml_root = ET.parse(xml_path).getroot()
    except (OSError, ET.ParseError) as error:
        fail(f"{xml_path}: invalid UI hierarchy: {error}")
    play_nodes = [
        node
        for node in xml_root.iter("node")
        if node.attrib.get("resource-id")
        == "org.scenelith.orkela:id/play_button"
    ]
    if len(play_nodes) != 1:
        fail(f"{xml_path}: expected exactly one Play control")
    bounds = play_nodes[0].attrib.get("bounds", "")
    bounds_match = re.fullmatch(
        r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]",
        bounds,
    )
    if bounds_match is None:
        fail(f"{xml_path}: invalid Play bounds")
    x1, y1, x2, y2 = map(int, bounds_match.groups())
    if x2 <= x1 or y2 <= y1:
        fail(f"{xml_path}: empty Play bounds")
    expected_point = f"{(x1 + x2) // 2} {(y1 + y2) // 2}"
    point_path = root / "play-point.txt"
    if read_strict_text(point_path).strip() != expected_point:
        fail(f"{point_path}: Play invocation point contradicts UI hierarchy")

    screenshot_path = root / "orkela-android.png"
    screenshot = parse_png(screenshot_path)
    screenshot_record_path = root / "ORKELA-SCREENSHOT.json"
    screenshot_record = read_json(screenshot_record_path)
    expected_screenshot_record = {
        "schema": 1,
        "format": "PNG",
        "width": screenshot["width"],
        "height": screenshot["height"],
        "bytes": screenshot["bytes"],
    }
    if screenshot_record != expected_screenshot_record:
        fail(f"{screenshot_record_path}: screenshot record contradiction")

    before_path = root / "logs" / "logcat-before-play.txt"
    after_path = root / "logs" / "logcat.txt"
    before = read_strict_text(before_path)
    after = read_strict_text(after_path)
    marker = r"ORKELA_AUDIO_QUEUE_WRITE accepted_elements=([0-9]+)"
    before_writes = re.findall(marker, before)
    after_writes = re.findall(marker, after)
    if len(after_writes) <= len(before_writes):
        fail(f"{after_path}: Play did not add an AudioTrack queue event")
    accepted = int(after_writes[-1])
    if accepted <= 0:
        fail(f"{after_path}: AudioTrack accepted zero elements")
    if accepted != record.get("accepted_audio_elements"):
        fail(f"{after_path}: AudioTrack count contradicts runtime record")
    errors = r"FATAL EXCEPTION|Playback failed:"
    if len(re.findall(errors, after)) > len(re.findall(errors, before)):
        fail(f"{after_path}: Play added a process/playback error")

    audio_path = root / "AUDIO-QUEUE-EVIDENCE.txt"
    if read_strict_text(audio_path) != f"accepted_elements={accepted}\n":
        fail(f"{audio_path}: AudioTrack summary contradicts raw logcat")
    control_path = root / "PLAY-CONTROL-DIAGNOSTIC.txt"
    if read_strict_text(control_path) != (
        "play_control_diagnostic="
        "audio-queue-write-observed-without-audibility-claim\n"
    ):
        fail(f"{control_path}: Play-control result is not exact")

    expected_app_files = ["./files/orkela-ci-smoke.json"]
    app_files_path = root / "APP-DATA-FILES.txt"
    allowlist_path = root / "EXPECTED-APP-DATA-FILES.txt"
    if read_strict_text(app_files_path).splitlines() != expected_app_files:
        fail(f"{app_files_path}: decoded PCM/WAV or another file persisted")
    if read_strict_text(allowlist_path).splitlines() != expected_app_files:
        fail(f"{allowlist_path}: app-data allowlist is not canonical")
    require_equal(record, "wav_or_pcm_intermediary", False, str(root))

    after_xml_path = root / "orkela-after-play.xml"
    if after_xml_path.exists():
        after_xml = read_strict_text(after_xml_path)
        try:
            ET.fromstring(after_xml)
        except ET.ParseError as error:
            fail(f"{after_xml_path}: invalid post-Play UI hierarchy: {error}")
        if re.search(r"failed|cannot decode|error", after_xml, re.IGNORECASE):
            fail(f"{after_xml_path}: visible post-Play error found")


def parse_certificate_digest(path: Path) -> str:
    text = read_strict_text(path)
    values = {
        match.lower()
        for match in re.findall(
            r"certificate SHA-256 digest:\s*([0-9A-Fa-f]{64})",
            text,
        )
    }
    if len(values) != 1:
        fail(f"{path}: expected one signing-certificate digest")
    return values.pop()


def validate_top_level_apk_evidence(
    diagnostics: Path,
    expected: dict[str, str],
) -> None:
    require_equal(
        {"digest": parse_certificate_digest(diagnostics / "APK-SIGNATURE.txt")},
        "digest",
        expected["app_cert_sha256"],
        str(diagnostics),
    )
    require_equal(
        {
            "digest": parse_certificate_digest(
                diagnostics / "TEST-APK-SIGNATURE.txt"
            )
        },
        "digest",
        expected["test_apk_cert_sha256"],
        str(diagnostics),
    )
    sums_path = diagnostics / "APK-SHA256SUMS"
    sums: dict[str, str] = {}
    for line in read_strict_text(sums_path).splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            fail(f"{sums_path}: malformed APK sha256sum line")
        name = PurePosixPath(match.group(2).replace("\\", "/")).name
        if name in sums:
            fail(f"{sums_path}: duplicate APK sha256sum entry")
        sums[name] = match.group(1)
    expected_sums = {
        "app-debug.apk": expected["app_sha256"],
        "app-debug-androidTest.apk": expected["test_apk_sha256"],
    }
    if sums != expected_sums:
        fail(f"{sums_path}: APK hash evidence differs from final inputs")


def validate_host(record: dict[str, Any], root: Path) -> tuple[Any, ...]:
    host = record.get("host")
    if not isinstance(host, dict):
        fail(f"{root}: missing host identity")
    stored = read_json(root / "HOST-AND-AVD-IDENTITY.json")
    if stored != host:
        fail(f"{root}: embedded host identity differs from raw identity")
    values = tuple(host.get(key) for key in HOST_KEYS)
    if any(value in (None, "", "local") for value in values):
        fail(f"{root}: incomplete GitHub host identity")
    for key in ("avd_name", "avd_path", "device_serial", "guest_boot_id"):
        if host.get(key) in (None, ""):
            fail(f"{root}: missing unique identity coordinate {key}")
    if host["guest_boot_id"] != record.get("guest_boot_id"):
        fail(f"{root}: guest boot ID contradiction")
    boot_id_path = root / "GUEST-BOOT-ID.txt"
    if read_strict_text(boot_id_path) != f"{host['guest_boot_id']}\n":
        fail(f"{boot_id_path}: raw guest boot ID contradiction")
    return values


def validate_common(
    root: Path,
    record: dict[str, Any],
    profile: dict[str, Any],
    contract: dict[str, Any],
    record_name: str,
) -> tuple[Any, ...]:
    scope = str(root)
    require_equal(record, "runtime_api", 37, scope)
    for key in (
        "app_sha256",
        "test_apk_sha256",
        "app_cert_sha256",
        "test_apk_cert_sha256",
    ):
        value = record.get(key)
        if not isinstance(value, str) or not HEX64.fullmatch(value):
            fail(f"{scope}: invalid artifact identity {key}")
    require_equal(record, "source_sha", record["host"]["source_sha"], scope)
    for key in ("page_size", "system_image", "system_fingerprint"):
        require_equal(record, key, profile[key], scope)
    require_equal(
        record,
        "system_image_manifest_sha256",
        profile["system_image_manifest_sha256"],
        scope,
    )

    emulator = contract["emulator"]
    for key in (
        "emulator_version",
        "emulator_revision",
        "emulator_archive_sha1",
        "emulator_archive_sha256",
    ):
        require_equal(record, key, emulator[key], scope)
    if str(record.get("emulator_build_id")) != str(emulator["emulator_build_id"]):
        fail(f"{scope}: emulator_build_id mismatch")
    if str(record.get("emulator_archive_size")) != str(
        emulator["emulator_archive_size"]
    ):
        fail(f"{scope}: emulator_archive_size mismatch")

    require_equal(record, "emulator_feature_overrides", FEATURE_TUPLE, scope)
    require_equal(record, "effective_renderer", RENDERER_TUPLE, scope)
    renderer_transport = record.get("renderer_transport")
    if (
        not isinstance(renderer_transport, str)
        or re.fullmatch(r"[A-Za-z0-9._-]{1,64}", renderer_transport) is None
    ):
        fail(f"{scope}: renderer transport is absent or malformed")
    require_equal(record, "effective_vulkan", 0, scope)
    require_equal(record, "effective_vulkan_native_swapchain", 0, scope)
    require_equal(record, "effective_guest_vulkan_only", 0, scope)
    require_equal(record, "effective_gl_direct_mem", 1, scope)
    require_equal(
        record,
        "effective_has_shared_slots_host_memory_allocator",
        1,
        scope,
    )
    require_equal(record, "effective_gl_dma", 1, scope)
    require_equal(record, "effective_gl_dma2", 0, scope)
    require_equal(record, "host_api_decision_level", 3, scope)
    require_equal(record, "vk_emulation_count", 0, scope)
    require_equal(record, "compositor_vk_count", 0, scope)
    require_equal(record, "selinux", "Enforcing", scope)
    if record.get("luma_sampling") not in ("default", "1"):
        fail(f"{scope}: luma sampling is not default/enabled")
    require_equal(record, "guest_payload_unmodified", True, scope)
    require_equal(record, "runtime_graphics_configuration_stock", False, scope)
    require_equal(record, "compositor_soak_screenshots", 4, scope)
    if not isinstance(record.get("compositor_soak_seconds"), int):
        fail(f"{scope}: invalid soak duration")
    if record["compositor_soak_seconds"] < 120:
        fail(f"{scope}: compositor soak is shorter than 120 seconds")
    require_equal(record, "healthy_observations", 24, scope)
    for key in (
        "surfaceflinger_crash_signatures_before",
        "surfaceflinger_crash_signatures_after",
    ):
        require_equal(record, key, 0, scope)
    initial_pid = record.get("initial_surfaceflinger_pid")
    final_pid = record.get("final_surfaceflinger_pid")
    if not isinstance(initial_pid, str) or not initial_pid or initial_pid != final_pid:
        fail(f"{scope}: SurfaceFlinger PID was absent or changed")
    require_equal(record, "boot_completed", True, scope)

    expected_manifest_hash = sha256_file(root / "SYSTEM-IMAGE-SHA256SUMS")
    require_equal(
        record,
        "system_image_manifest_sha256",
        expected_manifest_hash,
        scope,
    )
    after_manifest = root / "SYSTEM-IMAGE-SHA256SUMS-AFTER"
    if read_strict_text(after_manifest) != read_strict_text(
        root / "SYSTEM-IMAGE-SHA256SUMS"
    ):
        fail(f"{after_manifest}: guest system-image payload changed during gate")
    verify_raw_manifest(root, record_name, record["raw_evidence_manifest_sha256"])
    validate_emulator_log(root)
    validate_emulator_command(root, record)
    validate_soak_evidence(root, record)
    validate_raw_runtime_identity(root, record, profile)
    if record_name == "BOOT-GATE.json":
        analysis_name = "GUEST-BOOT-ANALYSIS.json"
        logcat_name = "logs/logcat-all-after-compositor-soak.txt"
        getprop_name = "logs/getprop-after-compositor-soak.txt"
    else:
        analysis_name = "GUEST-RUNTIME-ANALYSIS.json"
        logcat_name = "logs/logcat-all-after-runtime-gate.txt"
        getprop_name = "logs/getprop-after-runtime-gate.txt"
    validate_guest_analysis(
        root / analysis_name,
        root / logcat_name,
        root / getprop_name,
        profile["system_fingerprint"],
    )
    return validate_host(record, root)


def profile_roots(diagnostics: Path, profile_name: str) -> list[Path]:
    cold_root = diagnostics / f"cold-api{profile_name}"
    actual = sorted(path.name for path in cold_root.glob("attempt-*") if path.is_dir())
    expected = ["attempt-1", "attempt-2", "attempt-3"]
    if actual != expected:
        fail(f"{cold_root}: expected {expected}, found {actual}")
    return [cold_root / name for name in expected]


def validate_cold(
    diagnostics: Path,
    contract: dict[str, Any],
) -> tuple[
    tuple[Any, ...],
    tuple[str, str, str, str, str],
    set[str],
    set[str],
    set[str],
    set[str],
]:
    host_identity: tuple[Any, ...] | None = None
    artifact_identity: tuple[str, str, str, str, str] | None = None
    avd_names: set[str] = set()
    avd_paths: set[str] = set()
    serials: set[str] = set()
    boot_ids: set[str] = set()

    for profile_name in ("37", "37-16k"):
        profile = contract["profiles"][profile_name]
        for expected_attempt, root in enumerate(
            profile_roots(diagnostics, profile_name),
            start=1,
        ):
            record = read_json(root / "BOOT-GATE.json")
            require_equal(record, "gate", "cold-boot", str(root))
            require_equal(record, "attempt", expected_attempt, str(root))
            current_host = validate_common(
                root,
                record,
                profile,
                contract,
                "BOOT-GATE.json",
            )
            if host_identity is None:
                host_identity = current_host
            elif current_host != host_identity:
                fail(f"{root}: cold boots did not share one exact GitHub host")
            current_artifacts = tuple(
                record[key]
                for key in (
                    "app_sha256",
                    "test_apk_sha256",
                    "app_cert_sha256",
                    "test_apk_cert_sha256",
                    "source_sha",
                )
            )
            if artifact_identity is None:
                artifact_identity = current_artifacts
            elif current_artifacts != artifact_identity:
                fail(f"{root}: cold boots did not share one artifact identity")
            host = record["host"]
            for key, values in (
                ("avd_name", avd_names),
                ("avd_path", avd_paths),
                ("device_serial", serials),
                ("guest_boot_id", boot_ids),
            ):
                value = host[key]
                if value in values:
                    fail(f"{root}: duplicate cold-boot coordinate {key}={value}")
                values.add(value)
    if host_identity is None or artifact_identity is None:
        fail("no cold-boot evidence")
    if not all(len(values) == 6 for values in (avd_names, avd_paths, serials, boot_ids)):
        fail("cold-boot uniqueness cardinality mismatch")
    return (
        host_identity,
        artifact_identity,
        avd_names,
        avd_paths,
        serials,
        boot_ids,
    )


def validate_runtime(
    diagnostics: Path,
    contract: dict[str, Any],
    host_identity: tuple[Any, ...],
    artifact_identity: tuple[str, str, str, str, str],
    unique_sets: tuple[set[str], set[str], set[str], set[str]],
    expected: dict[str, str],
) -> None:
    expected_artifacts = tuple(
        expected[key]
        for key in (
            "app_sha256",
            "test_apk_sha256",
            "app_cert_sha256",
            "test_apk_cert_sha256",
            "source_sha",
        )
    )
    if expected_artifacts != artifact_identity:
        fail("final expected artifact identity differs from cold-boot identity")
    validate_top_level_apk_evidence(diagnostics, expected)
    for profile_name in ("37", "37-16k"):
        root = diagnostics / f"runtime-api{profile_name}"
        record = read_json(root / "RUNTIME-GATE.json")
        current_host = validate_common(
            root,
            record,
            contract["profiles"][profile_name],
            contract,
            "RUNTIME-GATE.json",
        )
        if current_host != host_identity:
            fail(f"{root}: runtime boot used a different GitHub host")
        host = record["host"]
        for key, values in zip(
            ("avd_name", "avd_path", "device_serial", "guest_boot_id"),
            unique_sets,
            strict=True,
        ):
            if host[key] in values:
                fail(f"{root}: runtime reused {key}={host[key]}")
            values.add(host[key])

        for key in (
            "app_sha256",
            "test_apk_sha256",
            "app_cert_sha256",
            "test_apk_cert_sha256",
            "source_sha",
            "expected_stream_sha256",
            "expected_pcm16_sha256",
        ):
            require_equal(record, key, expected[key], str(root))
        require_equal(record, "application_id", "org.scenelith.orkela", str(root))
        require_equal(record, "version_name", "0.3.0-alpha.6", str(root))
        require_equal(record, "native_decode", "pass", str(root))
        require_equal(record, "decoded_frames", 352800, str(root))
        require_equal(record, "decoded_sample_rate", 44100, str(root))
        require_equal(record, "decoded_channels", 2, str(root))
        if not isinstance(record.get("accepted_audio_elements"), int):
            fail(f"{root}: accepted_audio_elements is not an integer")
        if record["accepted_audio_elements"] <= 0:
            fail(f"{root}: AudioTrack accepted no elements")
        require_equal(record, "wav_or_pcm_intermediary", False, str(root))
        require_equal(record, "audibility_claim", False, str(root))
        validate_runtime_raw_evidence(root, record, expected)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("cold", "final"))
    parser.add_argument("diagnostics", type=Path)
    parser.add_argument("contract", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--app-sha256", default="")
    parser.add_argument("--test-apk-sha256", default="")
    parser.add_argument("--app-cert-sha256", default="")
    parser.add_argument("--test-apk-cert-sha256", default="")
    parser.add_argument("--source-sha", default="")
    parser.add_argument("--stream-sha256", default="")
    parser.add_argument("--pcm-sha256", default="")
    args = parser.parse_args()

    contract = read_json(args.contract)
    validate_contract(contract)
    (
        host_identity,
        artifact_identity,
        avd_names,
        avd_paths,
        serials,
        boot_ids,
    ) = validate_cold(args.diagnostics, contract)
    result: dict[str, Any] = {
        "schema": 1,
        "phase": args.phase,
        "status": "ANDROID17_COLD_PROMOTION_PASSED",
        "cold_boots": 6,
        "host_identity": dict(zip(HOST_KEYS, host_identity, strict=True)),
        "baseline_evidence": contract["baseline_evidence"],
    }
    if args.phase == "final":
        expected = {
            "app_sha256": args.app_sha256,
            "test_apk_sha256": args.test_apk_sha256,
            "app_cert_sha256": args.app_cert_sha256,
            "test_apk_cert_sha256": args.test_apk_cert_sha256,
            "source_sha": args.source_sha,
            "expected_stream_sha256": args.stream_sha256,
            "expected_pcm16_sha256": args.pcm_sha256,
        }
        for key, value in expected.items():
            if key != "source_sha" and not HEX64.fullmatch(value):
                fail(f"invalid expected digest for {key}")
            if key == "source_sha" and not re.fullmatch(r"[0-9a-f]{40}", value):
                fail("invalid expected Git source SHA")
        validate_runtime(
            args.diagnostics,
            contract,
            host_identity,
            artifact_identity,
            (avd_names, avd_paths, serials, boot_ids),
            expected,
        )
        result.update({
            "status": "ANDROID17_EXACT_APK_PROMOTION_PASSED",
            "runtime_boots": 2,
            "app_sha256": args.app_sha256,
            "test_apk_sha256": args.test_apk_sha256,
            "app_cert_sha256": args.app_cert_sha256,
            "test_apk_cert_sha256": args.test_apk_cert_sha256,
            "source_sha": args.source_sha,
            "expected_stream_sha256": args.stream_sha256,
            "expected_pcm16_sha256": args.pcm_sha256,
            "system_image_manifest_sha256": {
                profile: contract["profiles"][profile][
                    "system_image_manifest_sha256"
                ]
                for profile in ("37", "37-16k")
            },
        })

    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GateError as error:
        raise SystemExit(str(error)) from error
