#!/usr/bin/env python3

"""Assess one provenance-locked Android 17 Vulkan backend micro-probe."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from reduce_emulator_probe import (
    validate_result,
    validate_startup_evidence_file,
)


CELL_ID = "diagnostic-37_2_1-swiftshader-vulkan-vns"
EXPECTED: dict[str, dict[str, Any]] = {
    CELL_ID: {
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
        "feature_profile": "vulkan-native-swapchain-with-vulkan",
        "probe_scope": "startup",
        "vulkan": 1,
        "vulkan_native_swapchain": 1,
        "allow_unsupported_feature": True,
    },
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: assess_vulkan_backend_probe.py "
            "<probe-result-json> <assessment-json>"
        )
    result_path = Path(sys.argv[1])
    assessment_path = Path(sys.argv[2])
    assessment_path.unlink(missing_ok=True)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    disposition = validate_result(result, EXPECTED)
    startup_lines = validate_startup_evidence_file(
        result,
        result_path.with_name("STARTUP-FAILURE-EVIDENCE.txt"),
    )
    startup = result["startup"]

    def singular_index(pattern: str) -> int | None:
        indices = [
            index
            for index, line in enumerate(startup_lines)
            if re.search(pattern, line)
        ]
        return indices[0] if len(indices) == 1 else None

    state_indices = [
        singular_index(r"gfxstreamFeature:Vulkan\s*=\s*1$"),
        singular_index(
            r"gfxstreamFeature:VulkanNativeSwapchain\s*=\s*1$"
        ),
        singular_index(r"gfxstreamFeature:GuestVulkanOnly\s*=\s*1$"),
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
        all(index is not None for index in state_indices)
        and initialization_index is not None
        and all(index is not None for index in composition_indices)
        and compositor_index is not None
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
        "guest_vulkan_only": (
            startup["guest_vulkan_only_enabled_count"] == 1
            and startup["guest_vulkan_only_state_count"] == 1
        ),
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
        "adb_reached": result["boot_completed"],
    }
    backend_reached_adb = all(backend_markers.values())
    status = (
        "BACKEND_REACHED_ADB"
        if backend_reached_adb
        else "BACKEND_REJECTED"
    )
    assessment = {
        "schema": 1,
        "scope": (
            "Exact GitHub Linux host, Android 17 guest hash set, "
            "Emulator 37.2.1 SwiftShader, and explicit "
            "Vulkan+VulkanNativeSwapchain feature tuple"
        ),
        "status": status,
        "promotion_eligible": False,
        "disposition": disposition,
        "backend_markers": backend_markers,
        "result": result,
    }
    assessment_path.write_text(
        json.dumps(assessment, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not backend_reached_adb:
        raise SystemExit(
            "explicit Vulkan backend did not reach ADB with every "
            "required composition marker"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError) as error:
        raise SystemExit(
            f"invalid Vulkan backend probe evidence: {error}"
        ) from error
