#!/usr/bin/env python3

"""Assess provenance-locked Android 17 Vulkan backend micro-probes."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from analyze_guest_boot_evidence import analyze
from reduce_emulator_probe import (
    validate_result,
    validate_startup_evidence_file,
)


BASELINE_CELL_ID = "diagnostic-37_2_1-swiftshader-vulkan-vns"
CANDIDATE_CELL_ID = (
    "diagnostic-37_2_1-swiftshader-vulkan-vns-guest-angle-off"
)
CELL_ID = CANDIDATE_CELL_ID
COMMON_EXPECTED: dict[str, Any] = {
    "renderer": "swiftshader",
    "revision": "37.2.1",
    "build_id": 15875889,
    "binary_version": "37.2.1.0",
    "archive_sha1": "1c39ceb4bca042b973344d252a051189d367ab83",
    "archive_sha256": (
        "3fb1f765795b284f864b9b3403d1c5e1"
        "ad0f317eb6522441460001ff660d3d7d"
    ),
    "archive_size": 346539649,
    "probe_scope": "startup",
    "vulkan": 1,
    "vulkan_native_swapchain": 1,
    "allow_unsupported_feature": True,
    "allow_guest_boot_rejection": True,
}
EXPECTED: dict[str, dict[str, Any]] = {
    BASELINE_CELL_ID: {
        **COMMON_EXPECTED,
        "feature_profile": "vulkan-native-swapchain-with-vulkan",
        "feature_overrides": "Vulkan,VulkanNativeSwapchain",
        "guest_vulkan_only": 1,
        "expected_status": "BACKEND_REACHED_ADB_GUEST_BOOT_REJECTED",
    },
    CANDIDATE_CELL_ID: {
        **COMMON_EXPECTED,
        "feature_profile": (
            "vulkan-native-swapchain-with-vulkan-guest-angle-off"
        ),
        "feature_overrides": (
            "Vulkan,VulkanNativeSwapchain,-GuestAngle"
        ),
        "guest_vulkan_only": 0,
        "expected_status": "BACKEND_REACHED_ADB_BOOT_COMPLETED",
    },
}
PAIR_EXPECTED_STATUS = "GUEST_ANGLE_OFF_BOOT_RECOVERY_ON_SAME_HOST"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_host_evidence(
    result: dict[str, Any],
    result_path: Path,
) -> dict[str, str]:
    """Validate the same immutable host-identity payload used for hashing."""
    evidence_path = result_path.with_name("HOST-IDENTITY.txt")
    require(evidence_path.is_file(), "host identity evidence is missing")
    payload = evidence_path.read_bytes()
    require(
        hashlib.sha256(payload).hexdigest()
        == result["host"]["evidence_sha256"],
        "host identity evidence hash mismatch",
    )
    pairs = [
        line.split("=", 1)
        for line in payload.decode("utf-8").splitlines()
        if line
    ]
    require(
        all(len(pair) == 2 for pair in pairs),
        "host identity evidence contains a malformed line",
    )
    require(
        len({pair[0] for pair in pairs}) == len(pairs),
        "host identity evidence contains duplicate keys",
    )
    evidence = {key: value for key, value in pairs}
    expected = {
        "runner_os": result["host"]["runner_os"],
        "runner_arch": result["host"]["runner_arch"],
        "runner_name": result["host"]["runner_name"],
        "image_os": result["host"]["image_os"],
        "image_version": result["host"]["image_version"],
        "github_run_id": str(result["host"]["github_run_id"]),
        "github_run_attempt": str(result["host"]["github_run_attempt"]),
        "github_sha": result["host"]["github_sha"],
        "kernel_release": result["host"]["kernel_release"],
        "machine": result["host"]["machine"],
        "boot_id": result["host"]["boot_id"],
        "kvm_access": str(result["host"]["kvm_access"]).lower(),
    }
    require(evidence == expected, "host identity evidence contradicts result")
    return evidence


def validate_guest_evidence(
    result: dict[str, Any],
    result_path: Path,
) -> dict[str, Any] | None:
    """Recompute guest facts from SHA-linked raw captures."""
    claimed = result["startup"]["guest_evidence"]
    if not result["adb_reached"]:
        require(
            not claimed["captured"],
            "pre-ADB result claims guest evidence",
        )
        return None
    require(claimed["captured"], "ADB result lacks guest evidence")
    logcat_path = result_path.parent / "logs" / "logcat-all.txt"
    getprop_path = result_path.parent / "logs" / "getprop.txt"
    analysis_path = result_path.with_name("GUEST-STARTUP-ANALYSIS.json")
    for path in (logcat_path, getprop_path, analysis_path):
        require(path.is_file(), f"missing guest evidence: {path.name}")
    logcat_payload = logcat_path.read_bytes()
    getprop_payload = getprop_path.read_bytes()
    analysis_payload = analysis_path.read_bytes()
    require(
        hashlib.sha256(logcat_payload).hexdigest()
        == claimed["logcat_sha256"],
        "guest logcat hash mismatch",
    )
    require(
        hashlib.sha256(getprop_payload).hexdigest()
        == claimed["getprop_sha256"],
        "guest getprop hash mismatch",
    )
    require(
        hashlib.sha256(analysis_payload).hexdigest()
        == claimed["analysis_sha256"],
        "guest analysis hash mismatch",
    )
    recomputed = analyze(
        logcat_payload.decode("utf-8", errors="replace"),
        getprop_payload.decode("utf-8", errors="replace"),
    )
    stored = json.loads(analysis_payload.decode("utf-8"))
    require(stored == recomputed, "stored guest analysis is not reproducible")
    require(
        claimed["surfaceflinger_abort_tombstones"]
        == recomputed["surfaceflinger_abort_tombstones"],
        "claimed SurfaceFlinger tombstone count is false",
    )
    require(
        claimed["coherent_memory_angle_abort_tombstones"]
        == recomputed["coherent_memory_angle_abort_tombstones"],
        "claimed coherent-memory tombstone count is false",
    )
    require(
        claimed["updatable_crashing"]
        == recomputed["updatable_crashing_property"],
        "claimed updatable-crashing property is false",
    )
    require(
        claimed["updatable_crashing_process_name"]
        == recomputed["updatable_crashing_process_name"],
        "claimed crashing process is false",
    )
    require(
        claimed["boot_completed_property"]
        == recomputed["boot_completed_property"],
        "claimed boot-completed property is false",
    )
    require(
        result["boot_completed"]
        == (recomputed["boot_completed_property"] == "1"),
        "boot result contradicts recomputed guest property",
    )
    require(
        claimed["boot_hardware_egl"]
        == recomputed["boot_hardware_egl"],
        "claimed boot hardware EGL route is false",
    )
    require(
        claimed["hardware_egl"] == recomputed["hardware_egl"],
        "claimed hardware EGL route is false",
    )
    require(
        result["guest"]["observed_fingerprint"]
        == recomputed["observed_fingerprint"],
        "claimed guest fingerprint is false",
    )
    return recomputed


def assess(
    result: dict[str, Any],
    result_path: Path,
) -> dict[str, Any]:
    cell_id = result["cell_id"]
    expected = EXPECTED[cell_id]
    disposition = validate_result(result, EXPECTED)
    startup_lines = validate_startup_evidence_file(
        result,
        result_path.with_name("STARTUP-FAILURE-EVIDENCE.txt"),
    )
    guest_evidence = validate_guest_evidence(result, result_path)
    startup = result["startup"]

    def singular_index(pattern: str) -> int | None:
        indices = [
            index
            for index, line in enumerate(startup_lines)
            if re.search(pattern, line)
        ]
        return indices[0] if len(indices) == 1 else None

    guest_vulkan_only = expected["guest_vulkan_only"]
    feature_overrides = expected["feature_overrides"]
    override_index = singular_index(
        rf"parseAndApplyOverrides, overrides='"
        rf"{re.escape(feature_overrides)}'$"
    )
    guest_angle_disabled_index = singular_index(
        r"Feature 'GuestAngle'.*overridden to 'disabled'$"
    )
    guest_angle_auto_enabled_index = singular_index(
        r"Auto-enabled GuestAngle feature for VulkanNativeSwapchain$"
    )
    state_indices = [
        singular_index(r"gfxstreamFeature:Vulkan\s*=\s*1$"),
        singular_index(
            r"gfxstreamFeature:VulkanNativeSwapchain\s*=\s*1$"
        ),
        singular_index(
            rf"gfxstreamFeature:GuestVulkanOnly\s*=\s*"
            rf"{guest_vulkan_only}$"
        ),
    ]
    initialization_index = singular_index(
        r"Initializing VkEmulation features"
    )
    composition_indices = [
        singular_index(r"useVulkanComposition:\s*true"),
        singular_index(r"useVulkanNativeSwapchain:\s*true"),
    ]
    compositor_index = singular_index(
        r"Performing composition using CompositorVk"
    )
    ordered_markers = (
        override_index is not None
        and all(index is not None for index in state_indices)
        and initialization_index is not None
        and all(index is not None for index in composition_indices)
        and compositor_index is not None
        and override_index
        < min(index for index in state_indices if index is not None)
        and max(index for index in state_indices if index is not None)
        < initialization_index
        < min(
            index
            for index in composition_indices
            if index is not None
        )
        and max(
            index
            for index in composition_indices
            if index is not None
        )
        < compositor_index
    )
    guest_state_exact = (
        startup["guest_vulkan_only_state_count"] == 1
        and startup["guest_vulkan_only_enabled_count"]
        == guest_vulkan_only
    )
    guest_angle_intervention_index = (
        guest_angle_auto_enabled_index
        if guest_vulkan_only == 1
        else guest_angle_disabled_index
    )
    feature_intervention_exact = (
        result["host_feature"]["requested_overrides"]
        == feature_overrides
        and startup["feature_override_request_count"] == 1
        and override_index is not None
        and guest_angle_intervention_index is not None
        and all(index is not None for index in state_indices)
        and override_index
        < guest_angle_intervention_index
        < min(index for index in state_indices if index is not None)
        and (
            (
                guest_vulkan_only == 1
                and startup["guest_angle_disabled_override_count"] == 0
                and startup["guest_angle_auto_enabled_count"] == 1
                and guest_angle_disabled_index is None
                and guest_angle_auto_enabled_index is not None
            )
            or (
                guest_vulkan_only == 0
                and startup["guest_angle_disabled_override_count"] == 1
                and startup["guest_angle_auto_enabled_count"] == 0
                and guest_angle_disabled_index is not None
                and guest_angle_auto_enabled_index is None
            )
        )
    )
    guest_graphics_route_exact = (
        guest_evidence is not None
        and (
            (
                guest_vulkan_only == 1
                and guest_evidence["boot_hardware_egl"] == "angle"
                and guest_evidence["hardware_egl"] == "angle"
                and startup[
                    "surfaceflinger_angle_vk_instance_created_count"
                ]
                >= 2
            )
            or (
                guest_vulkan_only == 0
                and guest_evidence["boot_hardware_egl"] == ""
                and guest_evidence["hardware_egl"] == "emulation"
                and startup[
                    "surfaceflinger_angle_vk_instance_created_count"
                ]
                == 0
            )
        )
    )
    backend_markers = {
        "feature_tuple_exact": (
            result["host_feature"]["exact"]
            and result["host_feature"]["effective_vulkan"] == 1
            and (
                result["host_feature"][
                    "effective_vulkan_native_swapchain"
                ]
                == 1
            )
        ),
        "emulator_process_alive": (
            result["process"]["alive_after_probe"]
            and result["process"]["exit_code"] is None
        ),
        "feature_intervention_exact": feature_intervention_exact,
        "guest_vulkan_only_exact": guest_state_exact,
        "guest_graphics_route_exact": guest_graphics_route_exact,
        "ordered_backend_markers": ordered_markers,
        "vulkan_initialization": (
            startup["vulkan_initialization_count"] == 1
        ),
        "vulkan_composition_enabled": (
            startup["vulkan_composition_enabled_count"] == 1
            and startup["vulkan_composition_state_count"] == 1
        ),
        "vulkan_native_swapchain_enabled": (
            startup["vulkan_native_swapchain_enabled_count"] == 1
            and startup["vulkan_native_swapchain_state_count"] == 1
        ),
        "compositor_vk_selected": startup["compositor_vk_count"] == 1,
        "host_compositor_error_absent": (
            startup["host_compositor_error_count"] == 0
        ),
        "adb_reached": result["adb_reached"],
        "boot_completed": result["boot_completed"],
    }
    backend_reached_adb = all(
        value
        for key, value in backend_markers.items()
        if key != "boot_completed"
    )
    target_guest_loop = (
        guest_evidence is not None
        and guest_evidence[
            "coherent_memory_angle_abort_tombstones"
        ]
        >= 2
        and guest_evidence["updatable_crashing_property"] == "1"
        and guest_evidence["updatable_crashing_process_name"]
        == "surfaceflinger"
    )
    clean_guest_boot = (
        guest_evidence is not None
        and guest_evidence["surfaceflinger_abort_tombstones"] == 0
        and guest_evidence[
            "coherent_memory_angle_abort_tombstones"
        ]
        == 0
        and guest_evidence["surfaceflinger_fatal_signals"] == 0
        and guest_evidence["unsupported_virtual_memory_fatals"] == 0
        and guest_evidence["updatable_crashing_property"] != "1"
        and guest_evidence["updatable_crashing_process_name"]
        != "surfaceflinger"
    )
    if (
        backend_reached_adb
        and result["boot_completed"]
        and clean_guest_boot
    ):
        status = "BACKEND_REACHED_ADB_BOOT_COMPLETED"
    elif (
        backend_reached_adb
        and disposition
        == "provenance-valid-adb-reached-guest-boot-rejection"
        and target_guest_loop
    ):
        status = "BACKEND_REACHED_ADB_GUEST_BOOT_REJECTED"
    else:
        status = "BACKEND_REJECTED"
    return {
        "schema": 1,
        "scope": (
            "Exact GitHub Linux host, Android 17 guest hash set, "
            "Emulator 37.2.1 SwiftShader, and explicit "
            "Vulkan+VulkanNativeSwapchain feature tuple"
        ),
        "status": status,
        "expected_status": expected["expected_status"],
        "promotion_eligible": False,
        "disposition": disposition,
        "backend_markers": backend_markers,
        "clean_guest_boot_recomputed": clean_guest_boot,
        "target_guest_abort_loop_recomputed": target_guest_loop,
        "guest_evidence_recomputed": guest_evidence,
        "result": result,
    }


def assess_pair(
    baseline_result: dict[str, Any],
    baseline_path: Path,
    candidate_result: dict[str, Any],
    candidate_path: Path,
    baseline_result_sha256: str,
    candidate_result_sha256: str,
) -> dict[str, Any]:
    """Reduce a sequential same-runner one-coordinate intervention."""
    require(
        baseline_result["cell_id"] == BASELINE_CELL_ID,
        "joint assessment baseline cell is incorrect",
    )
    require(
        candidate_result["cell_id"] == CANDIDATE_CELL_ID,
        "joint assessment candidate cell is incorrect",
    )
    baseline = assess(baseline_result, baseline_path)
    candidate = assess(candidate_result, candidate_path)
    baseline_host = validate_host_evidence(
        baseline_result,
        baseline_path,
    )
    candidate_host = validate_host_evidence(
        candidate_result,
        candidate_path,
    )
    same_host = (
        baseline_host == candidate_host
        and baseline_result["host"] == candidate_result["host"]
    )
    isolated_probe_instances = (
        baseline_result["probe_instance"]["android_user_home"]
        != candidate_result["probe_instance"]["android_user_home"]
        and baseline_result["probe_instance"]["android_avd_home"]
        != candidate_result["probe_instance"]["android_avd_home"]
        and baseline_result["probe_instance"]["avd_name"]
        != candidate_result["probe_instance"]["avd_name"]
    )
    baseline_feature = dict(baseline_result["host_feature"])
    candidate_feature = dict(candidate_result["host_feature"])
    intervention_fields = {
        "profile",
        "requested_overrides",
        "requested_guest_vulkan_only",
    }
    common_baseline_feature = {
        key: value
        for key, value in baseline_feature.items()
        if key not in intervention_fields
    }
    common_candidate_feature = {
        key: value
        for key, value in candidate_feature.items()
        if key not in intervention_fields
    }
    intervention_exact = (
        common_baseline_feature == common_candidate_feature
        and baseline_feature["profile"]
        == EXPECTED[BASELINE_CELL_ID]["feature_profile"]
        and candidate_feature["profile"]
        == EXPECTED[CANDIDATE_CELL_ID]["feature_profile"]
        and baseline_feature["requested_overrides"]
        == EXPECTED[BASELINE_CELL_ID]["feature_overrides"]
        and candidate_feature["requested_overrides"]
        == EXPECTED[CANDIDATE_CELL_ID]["feature_overrides"]
        and baseline_feature["requested_guest_vulkan_only"] == 1
        and candidate_feature["requested_guest_vulkan_only"] == 0
        and baseline_result["renderer"] == candidate_result["renderer"]
        and baseline_result["probe_scope"]
        == candidate_result["probe_scope"]
        and baseline_result["emulator"] == candidate_result["emulator"]
        and baseline_result["guest"]["expected_hash_set"]
        == candidate_result["guest"]["expected_hash_set"]
        and baseline_result["guest"]["hash_set"]
        == candidate_result["guest"]["hash_set"]
        and baseline_result["guest"]["expected_fingerprint"]
        == candidate_result["guest"]["expected_fingerprint"]
    )
    status = (
        PAIR_EXPECTED_STATUS
        if (
            same_host
            and isolated_probe_instances
            and intervention_exact
            and baseline["status"]
            == "BACKEND_REACHED_ADB_GUEST_BOOT_REJECTED"
            and candidate["status"]
            == "BACKEND_REACHED_ADB_BOOT_COMPLETED"
        )
        else "JOINT_BACKEND_REJECTED"
    )
    return {
        "schema": 1,
        "scope": (
            "Sequential same-GitHub-runner Android 17 guest hash set, "
            "Emulator 37.2.1 SwiftShader, Vulkan composition backend, "
            "with GuestAngle override as the sole configured coordinate"
        ),
        "status": status,
        "expected_status": PAIR_EXPECTED_STATUS,
        "promotion_eligible": False,
        "same_host_identity": same_host,
        "isolated_probe_instances": isolated_probe_instances,
        "one_coordinate_intervention_exact": intervention_exact,
        "inputs": {
            "baseline": {
                "cell_id": baseline_result["cell_id"],
                "result_sha256": baseline_result_sha256,
                "startup_evidence_sha256": baseline_result[
                    "startup"
                ]["evidence_sha256"],
                "host_evidence_sha256": baseline_result[
                    "host"
                ]["evidence_sha256"],
            },
            "candidate": {
                "cell_id": candidate_result["cell_id"],
                "result_sha256": candidate_result_sha256,
                "startup_evidence_sha256": candidate_result[
                    "startup"
                ]["evidence_sha256"],
                "host_evidence_sha256": candidate_result[
                    "host"
                ]["evidence_sha256"],
            },
        },
        "baseline": baseline,
        "candidate": candidate,
    }


def main() -> int:
    if len(sys.argv) not in {3, 4}:
        raise SystemExit(
            "usage: assess_vulkan_backend_probe.py "
            "<probe-result-json> <assessment-json> | "
            "<baseline-result-json> <candidate-result-json> "
            "<joint-assessment-json>"
        )
    baseline_path = Path(sys.argv[1])
    if len(sys.argv) == 3:
        result_payload = baseline_path.read_bytes()
        result = json.loads(result_payload.decode("utf-8"))
        assessment = assess(result, baseline_path)
        assessment_path = Path(sys.argv[2])
    else:
        candidate_path = Path(sys.argv[2])
        baseline_payload = baseline_path.read_bytes()
        candidate_payload = candidate_path.read_bytes()
        baseline_result = json.loads(baseline_payload.decode("utf-8"))
        candidate_result = json.loads(candidate_payload.decode("utf-8"))
        assessment = assess_pair(
            baseline_result,
            baseline_path,
            candidate_result,
            candidate_path,
            hashlib.sha256(baseline_payload).hexdigest(),
            hashlib.sha256(candidate_payload).hexdigest(),
        )
        assessment_path = Path(sys.argv[3])
    assessment_path.unlink(missing_ok=True)
    assessment_path.write_text(
        json.dumps(assessment, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if assessment["status"] != assessment["expected_status"]:
        raise SystemExit(
            "Vulkan backend probe status mismatch: "
            f"observed={assessment['status']} "
            f"expected={assessment['expected_status']}"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError) as error:
        raise SystemExit(
            f"invalid Vulkan backend probe evidence: {error}"
        ) from error
