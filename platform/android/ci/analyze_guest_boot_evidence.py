#!/usr/bin/env python3

"""Derive fail-closed Android guest boot evidence from raw ADB captures."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


PROPERTY_PATTERN = re.compile(r"^\[([^\]]+)\]: \[(.*)\]$", re.MULTILINE)
THREADTIME_PATTERN = re.compile(
    r"^(?P<stamp>\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})"
    r"\s+(?P<pid>\d+)\s+(?P<tid>\d+)\s+"
    r"(?P<priority>[VDIWEF])\s+(?P<tag>[^:]+?)\s*:\s"
    r"(?P<message>.*)$"
)
FATAL_SURFACEFLINGER_PATTERN = re.compile(
    r"^Fatal signal 6 \(SIGABRT\), code -1 .*"
    r"in tid (?P<tid>\d+) \(surfaceflinger\), "
    r"pid (?P<pid>\d+) \(surfaceflinger\)$"
)
TOMBSTONE_PROCESS_PATTERN = re.compile(
    r"^pid: (?P<pid>\d+), ppid: \d+, tid: (?P<tid>\d+), "
    r"name: surfaceflinger\s+>>> /system/bin/surfaceflinger <<<$"
)
TOMBSTONE_SEPARATOR = "*** *** *** *** *** *** *** *** *** *** *** *** *** *** *** ***"
MAX_TOMBSTONE_LINES = 256
MAX_FATAL_LINK_DISTANCE = 64


def parse_properties(text: str) -> dict[str, str]:
    """Return the last observed value for every exact getprop key."""
    return {
        match.group(1): match.group(2)
        for match in PROPERTY_PATTERN.finditer(text)
    }


def parse_threadtime(logcat: str) -> list[dict[str, Any]]:
    """Parse only complete `logcat -v threadtime` records."""
    records: list[dict[str, Any]] = []
    for line_index, line in enumerate(logcat.splitlines()):
        match = THREADTIME_PATTERN.fullmatch(line)
        if match is None:
            continue
        records.append({
            "line_index": line_index,
            "pid": int(match.group("pid")),
            "tid": int(match.group("tid")),
            "priority": match.group("priority"),
            "tag": match.group("tag").strip(),
            "message": match.group("message"),
        })
    return records


def tombstone_records(logcat: str) -> list[str]:
    """Return bounded SurfaceFlinger tombstones linked to a fatal signal."""
    records = parse_threadtime(logcat)
    fatal_signals: list[tuple[int, int, int]] = []
    for index, record in enumerate(records):
        if record["priority"] != "F" or record["tag"] != "libc":
            continue
        match = FATAL_SURFACEFLINGER_PATTERN.fullmatch(record["message"])
        if match is None:
            continue
        process_pid = int(match.group("pid"))
        process_tid = int(match.group("tid"))
        if record["pid"] == process_pid and record["tid"] == process_tid:
            fatal_signals.append((index, process_pid, process_tid))

    separator_indices = [
        index
        for index, record in enumerate(records)
        if record["priority"] == "F"
        and record["tag"] == "DEBUG"
        and record["message"] == TOMBSTONE_SEPARATOR
    ]
    tombstones: list[str] = []
    for separator_offset, start in enumerate(separator_indices):
        next_start = (
            separator_indices[separator_offset + 1]
            if separator_offset + 1 < len(separator_indices)
            else len(records)
        )
        end = min(next_start, start + MAX_TOMBSTONE_LINES)
        debuggerd_pid = records[start]["pid"]
        debuggerd_tid = records[start]["tid"]
        episode = [
            record
            for record in records[start:end]
            if record["priority"] == "F"
            and record["tag"] == "DEBUG"
            and record["pid"] == debuggerd_pid
            and record["tid"] == debuggerd_tid
        ]
        messages = [record["message"] for record in episode]
        if messages.count("Cmdline: /system/bin/surfaceflinger") != 1:
            continue
        process_matches = [
            TOMBSTONE_PROCESS_PATTERN.fullmatch(message)
            for message in messages
        ]
        process_matches = [
            match for match in process_matches if match is not None
        ]
        if len(process_matches) != 1:
            continue
        process_pid = int(process_matches[0].group("pid"))
        process_tid = int(process_matches[0].group("tid"))
        if not any(
            fatal_index < start
            and start - fatal_index <= MAX_FATAL_LINK_DISTANCE
            and fatal_pid == process_pid
            and fatal_tid == process_tid
            for fatal_index, fatal_pid, fatal_tid in fatal_signals
        ):
            continue
        if sum(
            message.startswith("signal 6 (SIGABRT), code -1")
            for message in messages
        ) != 1:
            continue
        tombstones.append("\n".join(messages))
    return tombstones


def analyze(logcat: str, getprop: str) -> dict[str, Any]:
    """Count only complete, causally specific SurfaceFlinger tombstones."""
    properties = parse_properties(getprop)
    records = tombstone_records(logcat)
    coherent_memory_angle_records = [
        record
        for record in records
        if re.search(
            r"^\s*#01\b.*?/vendor/lib64/hw/vulkan\.ranchu\.so "
            r"\(gfxstream::vk::ResourceTracker::createCoherentMemory\(",
            record,
            re.MULTILINE,
        )
        and re.search(
            r"^\s*#\d+\b.*?/system/lib64/libGLESv2_angle\.so",
            record,
            re.MULTILINE,
        )
    ]
    threadtime = parse_threadtime(logcat)
    surfaceflinger_fatal_signals = sum(
        1
        for record in threadtime
        if record["priority"] == "F"
        and record["tag"] == "libc"
        and FATAL_SURFACEFLINGER_PATTERN.fullmatch(record["message"])
        is not None
    )
    return {
        "schema": 1,
        "surfaceflinger_tombstone_records": len(records),
        "surfaceflinger_abort_tombstones": len(records),
        "coherent_memory_angle_abort_tombstones": len(
            coherent_memory_angle_records
        ),
        "surfaceflinger_fatal_signals": surfaceflinger_fatal_signals,
        "unsupported_virtual_memory_fatals": sum(
            1
            for record in threadtime
            if record["priority"] == "E"
            and record["tag"] == "MESA"
            and record["message"]
            == "FATAL: Unsupported virtual memory feature"
        ),
        "boot_completed_property": properties.get(
            "sys.boot_completed",
            "",
        ),
        "updatable_crashing_property": properties.get(
            "sys.init.updatable_crashing",
            "",
        ),
        "updatable_crashing_process_name": properties.get(
            "sys.init.updatable_crashing_process_name",
            "",
        ),
        "observed_fingerprint": properties.get(
            "ro.build.fingerprint",
            "",
        ),
        "boot_hardware_egl": properties.get(
            "ro.boot.hardwareegl",
            "",
        ),
        "hardware_egl": properties.get("ro.hardware.egl", ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("logcat", type=Path)
    parser.add_argument("getprop", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = analyze(
        args.logcat.read_text(encoding="utf-8", errors="replace"),
        args.getprop.read_text(encoding="utf-8", errors="replace"),
    )
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
