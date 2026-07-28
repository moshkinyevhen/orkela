#!/usr/bin/env python3

"""Assess the exact same-host Android 17 ReadColorBufferDMA causal A/B."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


CONTROL_PROFILE = "read-color-buffer-dma-off"
CANDIDATE_PROFILE = "read-color-buffer-dma-on"
CONTROL_TUPLE = (
    "-GLDirectMem,-HasSharedSlotsHostMemoryAllocator,"
    "-GuestAngle,-Vulkan,-VulkanNativeSwapchain"
)
CANDIDATE_TUPLE = (
    "GLDirectMem,HasSharedSlotsHostMemoryAllocator,"
    "-GuestAngle,-Vulkan,-VulkanNativeSwapchain"
)


class AssessmentError(RuntimeError):
    """The evidence cannot prove the requested causal intervention."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssessmentError(message)


def read_result(path: Path) -> dict[str, Any]:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AssessmentError(f"{path}: invalid probe result: {error}") from error
    require(isinstance(result, dict), f"{path}: result must be an object")
    return result


def common_identity(result: dict[str, Any]) -> dict[str, Any]:
    emulator = result.get("emulator", {})
    guest = result.get("guest", {})
    host = result.get("host", {})
    return {
        "renderer": result.get("renderer"),
        "probe_scope": result.get("probe_scope"),
        "emulator": {
            key: emulator.get(key)
            for key in (
                "expected",
                "observed",
                "revision",
                "build_id",
                "archive_url",
                "archive_sha1",
                "archive_sha256",
                "archive_size",
                "archive_verified",
            )
        },
        "guest": {
            key: guest.get(key)
            for key in (
                "expected_hash_set",
                "hash_set",
                "expected_fingerprint",
            )
        },
        "host": {
            key: host.get(key)
            for key in (
                "runner_os",
                "runner_arch",
                "runner_name",
                "image_os",
                "image_version",
                "github_run_id",
                "github_run_attempt",
                "github_sha",
                "kernel_release",
                "machine",
                "boot_id",
                "kvm_access",
            )
        },
    }


def validate_feature_state(
    result: dict[str, Any],
    *,
    profile: str,
    overrides: str,
    enabled: int,
) -> None:
    feature = result.get("host_feature")
    require(isinstance(feature, dict), f"{profile}: host_feature absent")
    expected = {
        "profile": profile,
        "requested_overrides": overrides,
        "requested_vulkan": 0,
        "effective_vulkan": 0,
        "effective_vulkan_state_count": 1,
        "requested_vulkan_native_swapchain": 0,
        "effective_vulkan_native_swapchain": 0,
        "effective_state_count": 1,
        "requested_guest_vulkan_only": 0,
        "requested_gl_direct_mem": enabled,
        "effective_gl_direct_mem": enabled,
        "effective_gl_direct_mem_state_count": 1,
        "requested_has_shared_slots_host_memory_allocator": enabled,
        "effective_has_shared_slots_host_memory_allocator": enabled,
        "effective_has_shared_slots_state_count": 1,
        "requested_gl_dma": 1,
        "effective_gl_dma": 1,
        "effective_gl_dma_state_count": 1,
        "effective_gl_dma2": 0,
        "effective_gl_dma2_state_count": 1,
        "host_api_decision_level": 3,
        "host_api_decision_level_count": 1,
        "read_color_buffer_dma_proxy": bool(enabled),
        "exact": True,
    }
    for key, value in expected.items():
        require(
            feature.get(key) == value,
            f"{profile}: {key}={feature.get(key)!r}, expected {value!r}",
        )


def assess(
    control: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    require(
        common_identity(control) == common_identity(candidate),
        "control and candidate did not run on one exact host/environment",
    )
    require(control.get("renderer") == "swiftshader", "renderer is not SwiftShader")
    require(control.get("probe_scope") == "soak", "control is not a full soak")
    validate_feature_state(
        control,
        profile=CONTROL_PROFILE,
        overrides=CONTROL_TUPLE,
        enabled=0,
    )
    validate_feature_state(
        candidate,
        profile=CANDIDATE_PROFILE,
        overrides=CANDIDATE_TUPLE,
        enabled=1,
    )

    control_soak = control.get("soak")
    candidate_soak = candidate.get("soak")
    require(isinstance(control_soak, dict), "control soak evidence absent")
    require(isinstance(candidate_soak, dict), "candidate soak evidence absent")
    control_crashes = control_soak.get("target_crash_signatures")
    require(
        isinstance(control_crashes, int) and control_crashes > 0,
        "negative control did not reproduce ReadColorBufferDMA failure",
    )
    require(not control.get("stable", False), "negative control unexpectedly stable")

    candidate_expectations = {
        "stable": True,
        "boot_completed": True,
        "adb_reached": True,
        "environment_exact": True,
    }
    for key, value in candidate_expectations.items():
        require(
            candidate.get(key) == value,
            f"candidate {key}={candidate.get(key)!r}, expected {value!r}",
        )
    require(candidate.get("failures") == [], "candidate has recorded failures")
    for key, value in {
        "requested_seconds": 120,
        "observations": 24,
        "healthy_observations": 24,
        "pid_changes": 0,
        "crash_signatures": 0,
        "target_crash_signatures": 0,
        "valid_screenshots": 4,
    }.items():
        require(
            candidate_soak.get(key) == value,
            f"candidate soak {key}={candidate_soak.get(key)!r}, expected {value!r}",
        )
    initial_pid = candidate_soak.get("initial_surfaceflinger_pid")
    require(
        isinstance(initial_pid, str)
        and initial_pid
        and initial_pid == candidate_soak.get("final_surfaceflinger_pid"),
        "candidate SurfaceFlinger PID is absent or changed",
    )

    return {
        "schema": 1,
        "status": "READ_COLOR_BUFFER_DMA_CAUSAL_AB_PASSED",
        "promotion_eligible": False,
        "reason": (
            "causal graphics correction proved; exact APK and API-gated host "
            "feature audits remain separate mandatory gates"
        ),
        "same_host_identity": True,
        "control": {
            "profile": CONTROL_PROFILE,
            "read_color_buffer_dma_proxy": False,
            "target_crash_signatures": control_crashes,
        },
        "candidate": {
            "profile": CANDIDATE_PROFILE,
            "read_color_buffer_dma_proxy": True,
            "healthy_observations": 24,
            "target_crash_signatures": 0,
        },
        "host_api_decision_level": 3,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("control", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = assess(read_result(args.control), read_result(args.candidate))
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssessmentError as error:
        raise SystemExit(str(error)) from error
