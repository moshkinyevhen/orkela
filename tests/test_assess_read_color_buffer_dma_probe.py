import copy
import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPO_ROOT
    / "platform"
    / "android"
    / "ci"
    / "assess_read_color_buffer_dma_probe.py"
)
SPEC = importlib.util.spec_from_file_location("dma_assessor", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
ASSESSOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ASSESSOR)


def result(profile, overrides, enabled, *, stable, target_crashes):
    return {
        "renderer": "swiftshader",
        "probe_scope": "soak",
        "emulator": {"observed": "37.2.1.0"},
        "guest": {"observed_fingerprint": "fingerprint"},
        "host": {"boot_id": "host-boot"},
        "host_feature": {
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
        },
        "stable": stable,
        "boot_completed": stable,
        "adb_reached": True,
        "environment_exact": True,
        "failures": [] if stable else ["surfaceflinger-crash"],
        "soak": {
            "requested_seconds": 120,
            "observations": 24,
            "healthy_observations": 24 if stable else 0,
            "initial_surfaceflinger_pid": "100",
            "final_surfaceflinger_pid": "100" if stable else "200",
            "pid_changes": 0 if stable else 1,
            "crash_signatures": 0 if stable else target_crashes,
            "target_crash_signatures": target_crashes,
            "valid_screenshots": 4 if stable else 0,
        },
    }


@pytest.fixture
def evidence():
    return (
        result(
            ASSESSOR.CONTROL_PROFILE,
            ASSESSOR.CONTROL_TUPLE,
            0,
            stable=False,
            target_crashes=5,
        ),
        result(
            ASSESSOR.CANDIDATE_PROFILE,
            ASSESSOR.CANDIDATE_TUPLE,
            1,
            stable=True,
            target_crashes=0,
        ),
    )


def test_valid_causal_ab_passes(evidence):
    verdict = ASSESSOR.assess(*evidence)
    assert verdict["status"] == "READ_COLOR_BUFFER_DMA_CAUSAL_AB_PASSED"
    assert verdict["promotion_eligible"] is False


@pytest.mark.parametrize(
    ("side", "field", "value"),
    [
        ("candidate", "effective_gl_direct_mem", 0),
        ("candidate", "effective_has_shared_slots_host_memory_allocator", 0),
        ("candidate", "effective_gl_dma", 0),
        ("candidate", "host_api_decision_level", 37),
        ("candidate", "effective_vulkan_native_swapchain", 1),
        ("control", "read_color_buffer_dma_proxy", True),
    ],
)
def test_feature_contradictions_fail(evidence, side, field, value):
    control, candidate = copy.deepcopy(evidence)
    target = control if side == "control" else candidate
    target["host_feature"][field] = value
    with pytest.raises(ASSESSOR.AssessmentError):
        ASSESSOR.assess(control, candidate)


def test_control_without_target_crash_fails(evidence):
    control, candidate = copy.deepcopy(evidence)
    control["soak"]["target_crash_signatures"] = 0
    with pytest.raises(ASSESSOR.AssessmentError):
        ASSESSOR.assess(control, candidate)


def test_candidate_delayed_crash_fails(evidence):
    control, candidate = copy.deepcopy(evidence)
    candidate["soak"]["target_crash_signatures"] = 1
    candidate["soak"]["crash_signatures"] = 1
    with pytest.raises(ASSESSOR.AssessmentError):
        ASSESSOR.assess(control, candidate)


def test_different_host_fails(evidence):
    control, candidate = copy.deepcopy(evidence)
    candidate["host"]["boot_id"] = "other-host"
    with pytest.raises(ASSESSOR.AssessmentError):
        ASSESSOR.assess(control, candidate)
