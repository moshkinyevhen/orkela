#!/usr/bin/env python3

"""Reduce the exact Android 17 Emulator matrix into a fail-closed verdict."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


GUEST_HASH_SET = "android17-r06-google-apis-x86_64-4k-v1"
GUEST_FINGERPRINT = (
    "google/sdk_gphone64_x86_64/emu64xa:17/"
    "CE2A.260420.019/15611780:userdebug/dev-keys"
)

ARCHIVE_EXPECTED: dict[str, dict[str, Any]] = {
    "control-36_6_11-swiftshader": {
        "renderer": "swiftshader",
        "revision": "36.6.11",
        "build_id": 15507667,
        "binary_version": "36.6.11.0",
        "archive_sha1": "f8d8b83cf21a04966326eb1378bacda255f63b93",
        "archive_sha256": (
            "1eade4cf2df6ea8eeead4902c635897ba"
            "12aaa32aac4389eaae0fdb498a5b830"
        ),
        "archive_size": 331232577,
    },
    "candidate-37_1_10-swiftshader": {
        "renderer": "swiftshader",
        "revision": "37.1.10",
        "build_id": 15888535,
        "binary_version": "37.1.10.0",
        "archive_sha1": "489e57e560e310f9dfadf098951a713bf5651cd2",
        "archive_sha256": (
            "5ca4e61b25e4fe94224ef7af745e1c5d"
            "6901c2e957ccfb30b5f7fed3fad0e317"
        ),
        "archive_size": 334377561,
    },
    "candidate-37_1_10-swangle": {
        "renderer": "swangle",
        "revision": "37.1.10",
        "build_id": 15888535,
        "binary_version": "37.1.10.0",
        "archive_sha1": "489e57e560e310f9dfadf098951a713bf5651cd2",
        "archive_sha256": (
            "5ca4e61b25e4fe94224ef7af745e1c5d"
            "6901c2e957ccfb30b5f7fed3fad0e317"
        ),
        "archive_size": 334377561,
    },
    "candidate-37_1_10-lavapipe": {
        "renderer": "lavapipe",
        "revision": "37.1.10",
        "build_id": 15888535,
        "binary_version": "37.1.10.0",
        "archive_sha1": "489e57e560e310f9dfadf098951a713bf5651cd2",
        "archive_sha256": (
            "5ca4e61b25e4fe94224ef7af745e1c5d"
            "6901c2e957ccfb30b5f7fed3fad0e317"
        ),
        "archive_size": 334377561,
    },
    "candidate-37_2_1-swiftshader": {
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
    },
    "candidate-37_2_1-swangle": {
        "renderer": "swangle",
        "revision": "37.2.1",
        "build_id": 15875889,
        "binary_version": "37.2.1.0",
        "archive_sha1": "1c39ceb4bca042b973344d252a051189d367ab83",
        "archive_sha256": (
            "3fb1f765795b284f864b9b3403d1c5e1"
            "ad0f317eb6522441460001ff660d3d7d"
        ),
        "archive_size": 346539649,
    },
    "candidate-37_2_1-lavapipe": {
        "renderer": "lavapipe",
        "revision": "37.2.1",
        "build_id": 15875889,
        "binary_version": "37.2.1.0",
        "archive_sha1": "1c39ceb4bca042b973344d252a051189d367ab83",
        "archive_sha256": (
            "3fb1f765795b284f864b9b3403d1c5e1"
            "ad0f317eb6522441460001ff660d3d7d"
        ),
        "archive_size": 346539649,
    },
}

ARCHIVE_PROMOTION_ORDER = (
    "candidate-37_2_1-swiftshader",
    "candidate-37_2_1-swangle",
    "candidate-37_2_1-lavapipe",
    "candidate-37_1_10-swiftshader",
    "candidate-37_1_10-swangle",
    "candidate-37_1_10-lavapipe",
)

VULKAN_SWAPCHAIN_EXPECTED: dict[str, dict[str, Any]] = {
    cell_id: {
        "renderer": renderer,
        "revision": "37.2.1",
        "build_id": 15875889,
        "binary_version": "37.2.1.0",
        "archive_sha1": "1c39ceb4bca042b973344d252a051189d367ab83",
        "archive_sha256": (
            "3fb1f765795b284f864b9b3403d1c5e1"
            "ad0f317eb6522441460001ff660d3d7d"
        ),
        "archive_size": 346539649,
        "feature_profile": feature_profile,
        "vulkan_native_swapchain": feature_state,
        "allow_unsupported_feature": feature_state == 1,
    }
    for cell_id, renderer, feature_profile, feature_state in (
        (
            "control-37_2_1-swiftshader-feature-off",
            "swiftshader",
            "default",
            0,
        ),
        (
            "candidate-37_2_1-swiftshader-vulkan-swapchain",
            "swiftshader",
            "vulkan-native-swapchain",
            1,
        ),
        (
            "candidate-37_2_1-swangle-vulkan-swapchain",
            "swangle",
            "vulkan-native-swapchain",
            1,
        ),
        (
            "candidate-37_2_1-lavapipe-vulkan-swapchain",
            "lavapipe",
            "vulkan-native-swapchain",
            1,
        ),
    )
}

VULKAN_SWAPCHAIN_PROMOTION_ORDER = (
    "candidate-37_2_1-swiftshader-vulkan-swapchain",
    "candidate-37_2_1-swangle-vulkan-swapchain",
    "candidate-37_2_1-lavapipe-vulkan-swapchain",
)

# Kept as the public module alias used by the archive-matrix unit fixtures.
EXPECTED = ARCHIVE_EXPECTED
PROMOTION_ORDER = ARCHIVE_PROMOTION_ORDER

MATRICES = {
    "archive": {
        "expected": ARCHIVE_EXPECTED,
        "control": "control-36_6_11-swiftshader",
        "promotion_order": ARCHIVE_PROMOTION_ORDER,
        "scope": (
            "This exact GitHub runner, Android 17 guest hash set, "
            "Emulator archive matrix, and requested renderer set"
        ),
    },
    "vulkan-native-swapchain": {
        "expected": VULKAN_SWAPCHAIN_EXPECTED,
        "control": "control-37_2_1-swiftshader-feature-off",
        "promotion_order": VULKAN_SWAPCHAIN_PROMOTION_ORDER,
        "scope": (
            "This exact GitHub Linux runner, Android 17 guest hash set, "
            "Emulator 37.2.1 archive, renderer set, and documented "
            "VulkanNativeSwapchain host feature"
        ),
    },
}

EXPECTED_RENDERER_LINES = {
    "swiftshader": (
        "setCurrentRenderer: swiftshader swiftshader "
        "gles:Swiftshader Indirect vulkan:Swiftshader Indirect"
    ),
    "swangle": (
        "setCurrentRenderer: swangle swiftshader "
        "gles:Angle Indirect vulkan:Swiftshader Indirect"
    ),
    "lavapipe": (
        "setCurrentRenderer: swangle lavapipe "
        "gles:Angle Indirect vulkan:Lavapipe"
    ),
}

HOST_IDENTITY_FIELDS = (
    "runner_os",
    "runner_arch",
    "image_os",
    "image_version",
    "github_run_id",
    "github_run_attempt",
    "github_sha",
    "kernel_release",
    "machine",
    "kvm_access",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_startup_evidence_file(
    result: dict[str, Any],
    evidence_path: Path,
) -> list[str]:
    cell_id = result["cell_id"]
    require(
        evidence_path.is_file(),
        f"{cell_id}: startup evidence file is missing",
    )
    payload = evidence_path.read_bytes()
    observed_hash = hashlib.sha256(payload).hexdigest()
    require(
        observed_hash == result["startup"]["evidence_sha256"],
        f"{cell_id}: startup evidence hash mismatch",
    )
    lines = [
        line
        for line in payload.decode("utf-8").splitlines()
        if line
    ]
    require(
        len(lines) == result["startup"]["evidence_count"],
        f"{cell_id}: startup evidence count mismatch",
    )
    count_patterns = {
        "feature_override_request_count": (
            r"parseAndApplyOverrides, overrides='[^']*'"
        ),
        "guest_angle_disabled_override_count": (
            r"Feature 'GuestAngle'.*overridden to 'disabled'"
        ),
        "guest_angle_auto_enabled_count": (
            r"Auto-enabled GuestAngle feature for VulkanNativeSwapchain"
        ),
        "vulkan_initialization_count": (
            r"Initializing VkEmulation features"
        ),
        "vulkan_composition_enabled_count": (
            r"useVulkanComposition:\s*true"
        ),
        "vulkan_composition_state_count": (
            r"useVulkanComposition:\s*(?:true|false)"
        ),
        "vulkan_native_swapchain_enabled_count": (
            r"useVulkanNativeSwapchain:\s*true"
        ),
        "vulkan_native_swapchain_state_count": (
            r"useVulkanNativeSwapchain:\s*(?:true|false)"
        ),
        "guest_vulkan_only_enabled_count": (
            r"gfxstreamFeature:GuestVulkanOnly\s*=\s*1"
        ),
        "guest_vulkan_only_state_count": (
            r"gfxstreamFeature:GuestVulkanOnly\s*=\s*[01]"
        ),
        "surfaceflinger_angle_vk_instance_created_count": (
            r"Created VkInstance:.*application:'surfaceflinger'.*engine:'ANGLE'"
        ),
        "compositor_vk_count": (
            r"Performing composition using CompositorVk"
        ),
        "host_compositor_error_count": (
            r"Failed to initialize the compositor"
            r"|Failed to initialize FrameBuffer"
            r"|Could not start renderer"
        ),
    }
    for field, pattern in count_patterns.items():
        observed_count = sum(
            1 for line in lines if re.search(pattern, line)
        )
        require(
            observed_count == result["startup"][field],
            f"{cell_id}: {field} does not match startup evidence",
        )
    if result["startup"]["failure_class"] == "host-compositor-init-error":
        for signature in (
            "Failed to initialize the compositor.",
            "Failed to initialize FrameBuffer().",
            "Could not start renderer! (Error: -2)",
        ):
            require(
                any(signature in line for line in lines),
                f"{cell_id}: required startup signature is missing",
            )
    return lines


def archive_url(build_id: int) -> str:
    return (
        "https://dl.google.com/android/repository/"
        f"emulator-linux_x64-{build_id}.zip"
    )


def validate_result(
    result: dict[str, Any],
    expected_matrix: dict[str, dict[str, Any]] = EXPECTED,
) -> str:
    cell_id = result.get("cell_id")
    require(
        cell_id in expected_matrix,
        f"unexpected cell ID: {cell_id!r}",
    )
    expected = expected_matrix[cell_id]
    emulator = result["emulator"]
    guest = result["guest"]
    host_feature = result["host_feature"]
    host = result["host"]

    require(result["schema"] == 1, f"{cell_id}: schema mismatch")
    expected_probe_scope = expected.get("probe_scope", "soak")
    require(
        result["probe_scope"] == expected_probe_scope,
        f"{cell_id}: probe scope mismatch",
    )
    require(
        result["renderer"] == expected["renderer"],
        f"{cell_id}: requested renderer mismatch",
    )
    require(
        result["expected_control_failure"]
        == cell_id.startswith("control-"),
        f"{cell_id}: control role mismatch",
    )
    require(
        emulator["revision"] == expected["revision"],
        f"{cell_id}: archive revision mismatch",
    )
    require(
        emulator["build_id"] == expected["build_id"],
        f"{cell_id}: archive build mismatch",
    )
    require(
        emulator["archive_url"] == archive_url(expected["build_id"]),
        f"{cell_id}: archive URL mismatch",
    )
    require(
        emulator["archive_sha1"] == expected["archive_sha1"],
        f"{cell_id}: archive SHA-1 mismatch",
    )
    require(
        emulator["archive_sha256"] == expected["archive_sha256"],
        f"{cell_id}: archive SHA-256 mismatch",
    )
    require(
        emulator["archive_size"] == expected["archive_size"],
        f"{cell_id}: archive size mismatch",
    )
    require(
        emulator["expected"] == expected["binary_version"],
        f"{cell_id}: expected binary version mismatch",
    )
    require(
        emulator["observed"] == expected["binary_version"],
        f"{cell_id}: observed binary version mismatch",
    )
    require(emulator["archive_verified"], f"{cell_id}: archive unverified")
    require(
        guest["expected_hash_set"] == GUEST_HASH_SET,
        f"{cell_id}: expected guest hash-set mismatch",
    )
    require(
        guest["hash_set"] == GUEST_HASH_SET,
        f"{cell_id}: observed guest hash-set mismatch",
    )
    require(
        guest["expected_fingerprint"] == GUEST_FINGERPRINT,
        f"{cell_id}: expected fingerprint mismatch",
    )
    require(
        result["effective_renderer_count"] == 1,
        f"{cell_id}: effective renderer tuple is not singular",
    )
    require(
        result["effective_renderer_line"]
        == EXPECTED_RENDERER_LINES[expected["renderer"]],
        f"{cell_id}: effective renderer tuple is not allowlisted",
    )
    expected_feature_profile = expected.get("feature_profile", "default")
    expected_feature_state = expected.get("vulkan_native_swapchain", 0)
    require(
        host_feature["profile"] == expected_feature_profile,
        f"{cell_id}: requested host-feature profile mismatch",
    )
    require(
        host_feature["requested_vulkan_native_swapchain"]
        == expected_feature_state,
        f"{cell_id}: requested VulkanNativeSwapchain state mismatch",
    )
    expected_vulkan_state = expected.get("vulkan", 0)
    require(
        host_feature["requested_vulkan"] == expected_vulkan_state,
        f"{cell_id}: requested Vulkan state mismatch",
    )
    if "guest_vulkan_only" in expected:
        require(
            host_feature["requested_guest_vulkan_only"]
            == expected["guest_vulkan_only"],
            f"{cell_id}: requested GuestVulkanOnly state mismatch",
        )
    require(
        host_feature["effective_vulkan_state_count"] == 1,
        f"{cell_id}: Vulkan state is not singular",
    )
    require(
        host_feature["effective_vulkan"] == expected_vulkan_state,
        f"{cell_id}: effective Vulkan state mismatch",
    )
    require(
        host_feature["effective_state_count"] == 1,
        f"{cell_id}: host-feature state is not singular",
    )
    effective_feature_state = host_feature[
        "effective_vulkan_native_swapchain"
    ]
    require(
        effective_feature_state in {0, 1},
        f"{cell_id}: invalid effective VulkanNativeSwapchain state",
    )
    if expected.get("allow_unsupported_feature", False):
        require(
            host_feature["exact"]
            == (effective_feature_state == expected_feature_state),
            f"{cell_id}: host-feature exactness is contradictory",
        )
    else:
        require(
            effective_feature_state == expected_feature_state,
            f"{cell_id}: effective VulkanNativeSwapchain state mismatch",
        )
        require(
            host_feature["exact"],
            f"{cell_id}: host-feature state is inexact",
        )
    require(host["runner_os"] == "Linux", f"{cell_id}: runner OS mismatch")
    require(host["runner_arch"] == "X64", f"{cell_id}: runner arch mismatch")
    require(
        host["runner_name"] not in {"", "missing"},
        f"{cell_id}: runner name is missing",
    )
    require(
        host["image_os"] not in {"", "missing"},
        f"{cell_id}: runner image OS is missing",
    )
    require(
        host["image_version"] not in {"", "missing"},
        f"{cell_id}: runner image version is missing",
    )
    require(
        str(host["github_run_id"]).isdigit(),
        f"{cell_id}: GitHub run ID is invalid",
    )
    require(
        str(host["github_run_attempt"]).isdigit(),
        f"{cell_id}: GitHub run attempt is invalid",
    )
    require(
        re.fullmatch(r"[0-9a-f]{40}", str(host["github_sha"])) is not None,
        f"{cell_id}: GitHub source SHA is invalid",
    )
    require(
        host["kernel_release"] not in {"", "missing"},
        f"{cell_id}: host kernel release is missing",
    )
    require(
        host["machine"] == "x86_64",
        f"{cell_id}: host machine mismatch",
    )
    require(
        re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
            r"[0-9a-f]{4}-[0-9a-f]{12}",
            host["boot_id"],
        )
        is not None,
        f"{cell_id}: host boot ID is invalid",
    )
    require(
        re.fullmatch(r"[0-9a-f]{64}", host["evidence_sha256"])
        is not None,
        f"{cell_id}: host evidence hash is invalid",
    )
    require(host["kvm_access"], f"{cell_id}: KVM access is missing")
    probe_instance = result["probe_instance"]
    require(
        probe_instance["avd_name"] == f"orkela-renderer-probe-{cell_id}",
        f"{cell_id}: AVD identity mismatch",
    )
    require(
        probe_instance["android_avd_home"]
        == f"{probe_instance['android_user_home']}/avd",
        f"{cell_id}: AVD home is not scoped to the probe user home",
    )
    process = result["process"]
    startup = result["startup"]
    guest_evidence = startup["guest_evidence"]
    require(
        isinstance(result["adb_reached"], bool),
        f"{cell_id}: ADB reachability is invalid",
    )
    require(process["started"], f"{cell_id}: emulator process was not started")
    require(
        re.fullmatch(r"[0-9a-f]{64}", startup["evidence_sha256"])
        is not None,
        f"{cell_id}: invalid startup evidence hash",
    )
    require(
        isinstance(guest_evidence["boot_completed_property"], str),
        f"{cell_id}: boot-completed property is invalid",
    )
    require(
        result["boot_completed"]
        == (guest_evidence["boot_completed_property"] == "1"),
        f"{cell_id}: boot result contradicts captured guest property",
    )
    for field in ("boot_hardware_egl", "hardware_egl"):
        require(
            isinstance(guest_evidence[field], str),
            f"{cell_id}: guest EGL property is invalid: {field}",
        )
    if not result["boot_completed"]:
        if result["adb_reached"]:
            require(
                expected.get("allow_guest_boot_rejection", False),
                f"{cell_id}: ADB-reached guest boot rejection is not allowed",
            )
            require(
                not result["environment_exact"],
                f"{cell_id}: rejected guest boot cannot be exact",
            )
            require(not result["stable"], f"{cell_id}: rejected guest is stable")
            require(
                not result["stage1_candidate"],
                f"{cell_id}: rejected guest is promotion eligible",
            )
            require(
                guest["observed_fingerprint"] == GUEST_FINGERPRINT,
                f"{cell_id}: rejected guest fingerprint mismatch",
            )
            require(
                guest["selinux"] == ""
                and guest["luma_sampling"] == ""
                and guest["page_size"] == 0
                and guest["display_width"] == 0
                and guest["display_height"] == 0,
                f"{cell_id}: rejected guest has post-boot conformance",
            )
            require(
                startup["failure_class"]
                == "guest-surfaceflinger-vulkan-coherent-memory-abort-loop",
                f"{cell_id}: guest boot failure class is not allowlisted",
            )
            require(
                guest_evidence["captured"],
                f"{cell_id}: guest startup evidence was not captured",
            )
            for field in (
                "logcat_sha256",
                "getprop_sha256",
                "analysis_sha256",
            ):
                require(
                    re.fullmatch(
                        r"[0-9a-f]{64}",
                        guest_evidence[field],
                    )
                    is not None,
                    f"{cell_id}: invalid guest evidence hash: {field}",
                )
            require(
                guest_evidence[
                    "coherent_memory_angle_abort_tombstones"
                ]
                >= 2
                and guest_evidence["surfaceflinger_abort_tombstones"] >= 2,
                f"{cell_id}: repeated guest crash evidence is incomplete",
            )
            require(
                guest_evidence["updatable_crashing"] == "1"
                and guest_evidence[
                    "updatable_crashing_process_name"
                ]
                == "surfaceflinger",
                f"{cell_id}: updatable crash property is not causal",
            )
            require(
                process["alive_after_probe"] and process["exit_code"] is None,
                f"{cell_id}: ADB-reached rejected process is not alive",
            )
            require(
                set(result["failures"])
                == {
                    "boot-completion-timeout",
                    (
                        "guest-surfaceflinger-vulkan-coherent-memory-"
                        "abort-loop"
                    ),
                },
                f"{cell_id}: guest boot failure list is not exact",
            )
            require(
                result["soak"]["requested_seconds"]
                == (0 if expected_probe_scope == "startup" else 120)
                and result["soak"]["observations"] == 0
                and result["soak"]["healthy_observations"] == 0
                and result["soak"]["valid_screenshots"] == 0,
                f"{cell_id}: rejected guest contains runtime evidence",
            )
            require(
                startup["host_compositor_error_count"] == 0,
                f"{cell_id}: guest rejection overlaps a host compositor error",
            )
            return "provenance-valid-adb-reached-guest-boot-rejection"
        require(
            expected.get("allow_unsupported_feature", False),
            f"{cell_id}: pre-boot rejection is not allowed for this cell",
        )
        require(
            not result["environment_exact"],
            f"{cell_id}: pre-boot environment cannot be exact",
        )
        require(not result["stable"], f"{cell_id}: pre-boot cell is stable")
        require(
            not result["stage1_candidate"],
            f"{cell_id}: pre-boot cell is promotion eligible",
        )
        require(
            guest["observed_fingerprint"] == "",
            f"{cell_id}: pre-boot fingerprint must be empty",
        )
        require(
            guest["selinux"] == "",
            f"{cell_id}: pre-boot SELinux state must be empty",
        )
        require(
            guest["luma_sampling"] == "",
            f"{cell_id}: pre-boot luma state must be empty",
        )
        require(
            guest["page_size"] == 0,
            f"{cell_id}: pre-boot page size must be zero",
        )
        require(
            guest["display_width"] == 0 and guest["display_height"] == 0,
            f"{cell_id}: pre-boot display dimensions must be zero",
        )
        require(
            result["soak"]["observations"] == 0
            and result["soak"]["healthy_observations"] == 0
            and result["soak"]["valid_screenshots"] == 0,
            f"{cell_id}: pre-boot runtime evidence must be empty",
        )
        require(
            result["soak"]["requested_seconds"]
            == (0 if expected_probe_scope == "startup" else 120),
            f"{cell_id}: pre-boot requested duration mismatch",
        )
        require(
            result["soak"]["initial_surfaceflinger_pid"] == ""
            and result["soak"]["final_surfaceflinger_pid"] == ""
            and result["soak"]["pid_changes"] == 0,
            f"{cell_id}: pre-boot SurfaceFlinger evidence must be empty",
        )
        require(
            startup["failure_class"] == "host-compositor-init-error",
            f"{cell_id}: pre-boot failure class is not allowlisted",
        )
        require(
            startup["host_compositor_error_count"] >= 3,
            f"{cell_id}: host compositor failure evidence is incomplete",
        )
        require(
            startup["evidence_count"] >= 5,
            f"{cell_id}: startup failure evidence is incomplete",
        )
        require(
            (process["alive_after_probe"] and process["exit_code"] is None)
            or (
                not process["alive_after_probe"]
                and isinstance(process["exit_code"], int)
            ),
            f"{cell_id}: process termination evidence is contradictory",
        )
        require(
            any(
                failure in {
                    "emulator-exited-before-adb",
                    "adb-device-timeout",
                }
                for failure in result["failures"]
            ),
            f"{cell_id}: pre-boot transport failure is missing",
        )
        require(
            set(result["failures"]).issubset({
                "emulator-exited-before-adb",
                "adb-device-timeout",
            }),
            f"{cell_id}: pre-boot failure list is not allowlisted",
        )
        require(
            not result["crash_evidence_complete"]
            and result["soak"]["crash_signatures"] == 0
            and result["soak"]["target_crash_signatures"] == 0,
            f"{cell_id}: pre-boot crash evidence is contradictory",
        )
        return "provenance-valid-preboot-rejection"
    require(result["adb_reached"], f"{cell_id}: boot completed without ADB")
    require(
        guest["observed_fingerprint"] == GUEST_FINGERPRINT,
        f"{cell_id}: observed fingerprint mismatch",
    )
    require(
        result["environment_exact"],
        f"{cell_id}: environment is not exact",
    )
    require(
        guest["selinux"] == "Enforcing",
        f"{cell_id}: SELinux mismatch",
    )
    require(
        str(guest["luma_sampling"]) in {"", "default", "1"},
        f"{cell_id}: luma-sampling mismatch",
    )
    require(guest["page_size"] == 4096, f"{cell_id}: page-size mismatch")
    require(
        guest["display_width"] > 0 and guest["display_height"] > 0,
        f"{cell_id}: invalid display dimensions",
    )
    if expected_probe_scope == "startup":
        require(
            result["soak"]["requested_seconds"] == 0
            and result["soak"]["observations"] == 0
            and result["soak"]["healthy_observations"] == 0,
            f"{cell_id}: startup probe contains soak evidence",
        )
        require(
            result["soak"]["initial_surfaceflinger_pid"] == ""
            and result["soak"]["final_surfaceflinger_pid"] == ""
            and result["soak"]["pid_changes"] == 0
            and result["soak"]["crash_signatures"] == 0
            and result["soak"]["target_crash_signatures"] == 0
            and result["soak"]["valid_screenshots"] == 0,
            f"{cell_id}: startup probe contains runtime evidence",
        )
        require(
            result["failures"] == [],
            f"{cell_id}: successful startup probe records failures",
        )
        require(
            startup["failure_class"] == "none",
            f"{cell_id}: successful startup probe has a failure class",
        )
        require(
            not result["crash_evidence_complete"]
            and not result["stable"]
            and not result["stage1_candidate"],
            f"{cell_id}: startup-only derived state is contradictory",
        )
        require(
            process["alive_after_probe"] and process["exit_code"] is None,
            f"{cell_id}: startup process was not alive at capture",
        )
        return "runtime-conformant-startup"
    require(
        result["crash_evidence_complete"],
        f"{cell_id}: crash evidence is incomplete",
    )
    require(
        result["soak"]["requested_seconds"] == 120,
        f"{cell_id}: soak duration mismatch",
    )
    return "runtime-conformant"


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: reduce_emulator_probe.py "
            "<artifact-root> <assessment-json> <promotion-json>"
        )
    artifact_root = Path(sys.argv[1])
    assessment_path = Path(sys.argv[2])
    promotion_path = Path(sys.argv[3])
    assessment_path.unlink(missing_ok=True)
    promotion_path.unlink(missing_ok=True)
    paths = sorted(artifact_root.glob("**/PROBE-RESULT.json"))
    raw_results = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in paths
    ]
    observed_cells = [result.get("cell_id") for result in raw_results]
    require(
        len(observed_cells) == len(set(observed_cells)),
        "duplicate cell ID",
    )
    matrix_matches = [
        (name, matrix)
        for name, matrix in MATRICES.items()
        if set(observed_cells) == set(matrix["expected"])
        and len(observed_cells) == len(matrix["expected"])
    ]
    require(
        len(matrix_matches) == 1,
        f"unknown exact cell set: {sorted(str(cell) for cell in observed_cells)}",
    )
    matrix_name, matrix = matrix_matches[0]
    expected_matrix = matrix["expected"]

    results: dict[str, dict[str, Any]] = {}
    dispositions: dict[str, str] = {}
    result_paths = {
        json.loads(path.read_text(encoding="utf-8")).get("cell_id"): path
        for path in paths
    }
    for result in raw_results:
        disposition = validate_result(result, expected_matrix)
        cell_id = result["cell_id"]
        validate_startup_evidence_file(
            result,
            result_paths[cell_id].with_name("STARTUP-FAILURE-EVIDENCE.txt"),
        )
        results[cell_id] = result
        dispositions[cell_id] = disposition
    require(set(results) == set(expected_matrix), "exact cell set mismatch")

    first_cell = next(iter(expected_matrix))
    host_identity = {
        field: results[first_cell]["host"][field]
        for field in HOST_IDENTITY_FIELDS
    }
    for cell_id, result in results.items():
        observed_identity = {
            field: result["host"][field]
            for field in HOST_IDENTITY_FIELDS
        }
        require(
            observed_identity == host_identity,
            f"{cell_id}: GitHub runner image identity mismatch",
        )

    control = results[matrix["control"]]
    control_soak = control["soak"]
    crash_failure_recorded = any(
        failure.startswith("surfaceflinger-crash-signatures:")
        for failure in control["failures"]
    )
    control_is_observably_unstable = (
        control_soak["healthy_observations"]
        < control_soak["observations"]
        or control_soak["pid_changes"] > 0
        or (
            control_soak["final_surfaceflinger_pid"]
            != control_soak["initial_surfaceflinger_pid"]
        )
        or control_soak["valid_screenshots"] < 4
    )
    control_reproduced = (
        control["environment_exact"]
        and control["crash_evidence_complete"]
        and control["known_control_crash_reproduced"]
        and control["known_failing_tuple"]
        and control["host_feature"]["exact"]
        and (
            control["host_feature"]["effective_vulkan_native_swapchain"]
            == 0
        )
        and control_soak["observations"] == 24
        and control_soak["crash_signatures"] > 0
        and control_soak["target_crash_signatures"] > 0
        and crash_failure_recorded
        and control_is_observably_unstable
        and bool(control["failures"])
        and "setCurrentRenderer: swiftshader swiftshader"
        in control["effective_renderer_line"]
        and not control["stable"]
    )
    candidates = [
        cell_id
        for cell_id in matrix["promotion_order"]
        if (
            results[cell_id]["environment_exact"]
            and results[cell_id]["host_feature"]["exact"]
            and (
                results[cell_id]["host_feature"][
                    "effective_vulkan_native_swapchain"
                ]
                == expected_matrix[cell_id].get(
                    "vulkan_native_swapchain",
                    0,
                )
            )
            and results[cell_id]["stable"]
            and results[cell_id]["stage1_candidate"]
            and not results[cell_id]["known_failing_tuple"]
            and results[cell_id]["soak"]["observations"] == 24
            and results[cell_id]["soak"]["healthy_observations"] == 24
            and bool(
                results[cell_id]["soak"]["initial_surfaceflinger_pid"]
            )
            and (
                results[cell_id]["soak"]["final_surfaceflinger_pid"]
                == results[cell_id]["soak"]["initial_surfaceflinger_pid"]
            )
            and results[cell_id]["soak"]["pid_changes"] == 0
            and results[cell_id]["soak"]["crash_signatures"] == 0
            and results[cell_id]["soak"]["valid_screenshots"] == 4
            and not results[cell_id]["failures"]
        )
    ]
    assessment = {
        "schema": 1,
        "matrix": matrix_name,
        "scope": matrix["scope"],
        "host_identity": host_identity,
        "control_reproduced": control_reproduced,
        "stage1_candidates": candidates,
        "cell_dispositions": dispositions,
        "results": results,
    }
    assessment_path.write_text(
        json.dumps(assessment, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not control_reproduced:
        raise SystemExit("exact same-run control crash was not reproduced")
    if not candidates:
        raise SystemExit(
            "no Stage-1 candidate in this exact run/runner/guest matrix"
        )

    selected = results[candidates[0]]
    promotion = {
        "schema": 1,
        "cell_id": selected["cell_id"],
        "emulator": selected["emulator"],
        "guest": {
            "hash_set": selected["guest"]["hash_set"],
            "fingerprint": selected["guest"]["observed_fingerprint"],
        },
        "requested_renderer": selected["renderer"],
        "effective_renderer": selected["effective_renderer_line"],
        "host_feature": selected["host_feature"],
        "host": selected["host"],
        "required_next_gate": {
            "cold_4k_boots": 3,
            "cold_16k_boots": 3,
            "exact_orkela_apk_pair": True,
            "sdkmanager_latest_emulator_forbidden": True,
        },
    }
    promotion_path.write_text(
        json.dumps(promotion, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError) as error:
        raise SystemExit(f"invalid Emulator probe evidence: {error}") from error
