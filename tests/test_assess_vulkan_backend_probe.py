import importlib.util
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from test_reduce_emulator_probe import EmulatorProbeReducerTest


REPO_ROOT = Path(__file__).resolve().parents[1]
CI_DIR = REPO_ROOT / "platform" / "android" / "ci"
sys.path.insert(0, str(CI_DIR))
MODULE_PATH = CI_DIR / "assess_vulkan_backend_probe.py"
SPEC = importlib.util.spec_from_file_location(
    "assess_vulkan_backend_probe",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
ASSESSOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ASSESSOR)


class VulkanBackendProbeAssessmentTest(unittest.TestCase):
    def fixture(self, boot_completed: bool) -> dict:
        factory = EmulatorProbeReducerTest()
        result = factory.make_result(
            ASSESSOR.CELL_ID,
            stable=boot_completed,
            expected_matrix=ASSESSOR.EXPECTED,
        )
        result["expected_control_failure"] = False
        result["known_control_crash_reproduced"] = False
        result["known_failing_tuple"] = False
        result["stage1_candidate"] = False
        result["stable"] = False
        result["crash_evidence_complete"] = False
        result["soak"].update({
            "requested_seconds": 0,
            "observations": 0,
            "healthy_observations": 0,
            "initial_surfaceflinger_pid": "",
            "final_surfaceflinger_pid": "",
            "pid_changes": 0,
            "crash_signatures": 0,
            "target_crash_signatures": 0,
            "valid_screenshots": 0,
        })
        result["startup"].update({
            "vulkan_initialization_count": 1,
            "vulkan_composition_enabled_count": 1,
            "vulkan_composition_state_count": 1,
            "vulkan_native_swapchain_enabled_count": 1,
            "vulkan_native_swapchain_state_count": 1,
            "guest_vulkan_only_enabled_count": 1,
            "guest_vulkan_only_state_count": 1,
            "compositor_vk_count": 1,
        })
        if boot_completed:
            result["failures"] = []
            return result
        result.update({
            "boot_completed": False,
            "environment_exact": False,
            "stable": False,
            "crash_evidence_complete": False,
        })
        result["guest"].update({
            "observed_fingerprint": "",
            "selinux": "",
            "luma_sampling": "",
            "page_size": 0,
            "display_width": 0,
            "display_height": 0,
        })
        result["process"].update({
            "alive_after_probe": False,
            "exit_code": 1,
        })
        result["startup"].update({
            "failure_class": "host-compositor-init-error",
            "evidence_count": 8,
            "evidence_sha256": "c" * 64,
            "vulkan_initialization_count": 0,
            "vulkan_composition_enabled_count": 0,
            "vulkan_composition_state_count": 0,
            "vulkan_native_swapchain_enabled_count": 0,
            "vulkan_native_swapchain_state_count": 0,
            "guest_vulkan_only_enabled_count": 0,
            "guest_vulkan_only_state_count": 0,
            "compositor_vk_count": 0,
            "host_compositor_error_count": 3,
        })
        result["failures"] = ["emulator-exited-before-adb"]
        return result

    def invoke(
        self,
        root: Path,
        result: dict,
        evidence: bytes | None = None,
    ) -> tuple[int, Path]:
        result_path = root / "PROBE-RESULT.json"
        assessment_path = root / "ASSESSMENT.json"
        if evidence is None:
            if result["startup"]["failure_class"] == \
                    "host-compositor-init-error":
                evidence = (
                    b"Failed to initialize the compositor.\n"
                    b"Failed to initialize FrameBuffer().\n"
                    b"Could not start renderer! (Error: -2)\n"
                    b"gfxstreamFeature:Vulkan = 1\n"
                    b"gfxstreamFeature:VulkanNativeSwapchain = 1\n"
                    b"extra-a\nextra-b\nextra-c\n"
                )
            else:
                evidence = (
                    b"gfxstreamFeature:Vulkan = 1\n"
                    b"gfxstreamFeature:VulkanNativeSwapchain = 1\n"
                    b"gfxstreamFeature:GuestVulkanOnly = 1\n"
                    b"Initializing VkEmulation features\n"
                    b"useVulkanComposition: true\n"
                    b"useVulkanNativeSwapchain: true\n"
                    b"Performing composition using CompositorVk\n"
                )
        result["startup"]["evidence_count"] = len(
            [line for line in evidence.splitlines() if line]
        )
        result["startup"]["evidence_sha256"] = hashlib.sha256(
            evidence
        ).hexdigest()
        result_path.write_text(json.dumps(result), encoding="utf-8")
        result_path.with_name(
            "STARTUP-FAILURE-EVIDENCE.txt"
        ).write_bytes(evidence)
        old_argv = sys.argv
        try:
            sys.argv = [
                str(MODULE_PATH),
                str(result_path),
                str(assessment_path),
            ]
            code = ASSESSOR.main()
        finally:
            sys.argv = old_argv
        return code, assessment_path

    def test_exact_backend_reaching_adb_is_evidence_success_not_promotion(self):
        with tempfile.TemporaryDirectory() as directory:
            code, assessment_path = self.invoke(
                Path(directory),
                self.fixture(boot_completed=True),
            )
            self.assertEqual(code, 0)
            assessment = json.loads(
                assessment_path.read_text(encoding="utf-8")
            )
            self.assertEqual(assessment["status"], "BACKEND_REACHED_ADB")
            self.assertFalse(assessment["promotion_eligible"])

    def test_preboot_host_compositor_failure_is_preserved_as_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(
                SystemExit,
                "did not reach ADB",
            ):
                self.invoke(root, self.fixture(boot_completed=False))
            assessment = json.loads(
                (root / "ASSESSMENT.json").read_text(encoding="utf-8")
            )
            self.assertEqual(assessment["status"], "BACKEND_REJECTED")
            self.assertFalse(assessment["promotion_eligible"])

    def test_missing_vulkan_backend_marker_rejects_after_assessment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.fixture(boot_completed=True)
            result["startup"]["compositor_vk_count"] = 0
            evidence = (
                b"gfxstreamFeature:Vulkan = 1\n"
                b"gfxstreamFeature:VulkanNativeSwapchain = 1\n"
                b"gfxstreamFeature:GuestVulkanOnly = 1\n"
                b"Initializing VkEmulation features\n"
                b"useVulkanComposition: true\n"
                b"useVulkanNativeSwapchain: true\n"
            )
            with self.assertRaisesRegex(
                SystemExit,
                "did not reach ADB",
            ):
                self.invoke(root, result, evidence)
            assessment = json.loads(
                (root / "ASSESSMENT.json").read_text(encoding="utf-8")
            )
            self.assertFalse(
                assessment["backend_markers"]["compositor_vk_selected"]
            )

    def test_claimed_markers_with_empty_evidence_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(
                ValueError,
                "does not match startup evidence",
            ):
                self.invoke(
                    root,
                    self.fixture(boot_completed=True),
                    b"",
                )
            self.assertFalse((root / "ASSESSMENT.json").exists())

    def test_dead_process_after_boot_is_not_backend_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.fixture(boot_completed=True)
            result["process"].update({
                "alive_after_probe": False,
                "exit_code": 1,
            })
            with self.assertRaisesRegex(
                ValueError,
                "process was not alive",
            ):
                self.invoke(root, result)
            self.assertFalse((root / "ASSESSMENT.json").exists())

    def test_reordered_backend_markers_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = (
                b"Initializing VkEmulation features\n"
                b"gfxstreamFeature:Vulkan = 1\n"
                b"gfxstreamFeature:VulkanNativeSwapchain = 1\n"
                b"gfxstreamFeature:GuestVulkanOnly = 1\n"
                b"useVulkanComposition: true\n"
                b"useVulkanNativeSwapchain: true\n"
                b"Performing composition using CompositorVk\n"
            )
            with self.assertRaisesRegex(
                SystemExit,
                "did not reach ADB",
            ):
                self.invoke(
                    root,
                    self.fixture(boot_completed=True),
                    evidence,
                )
            assessment = json.loads(
                (root / "ASSESSMENT.json").read_text(encoding="utf-8")
            )
            self.assertFalse(
                assessment["backend_markers"]["ordered_backend_markers"]
            )

    def test_effective_feature_downgrade_is_not_backend_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.fixture(boot_completed=True)
            result["host_feature"].update({
                "effective_vulkan_native_swapchain": 0,
                "exact": False,
            })
            with self.assertRaisesRegex(
                SystemExit,
                "did not reach ADB",
            ):
                self.invoke(root, result)
            assessment = json.loads(
                (root / "ASSESSMENT.json").read_text(encoding="utf-8")
            )
            self.assertFalse(
                assessment["backend_markers"]["feature_tuple_exact"]
            )

    def test_mixed_guest_vulkan_only_states_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.fixture(boot_completed=True)
            result["startup"]["guest_vulkan_only_state_count"] = 2
            evidence = (
                b"gfxstreamFeature:Vulkan = 1\n"
                b"gfxstreamFeature:VulkanNativeSwapchain = 1\n"
                b"gfxstreamFeature:GuestVulkanOnly = 0\n"
                b"gfxstreamFeature:GuestVulkanOnly = 1\n"
                b"Initializing VkEmulation features\n"
                b"useVulkanComposition: true\n"
                b"useVulkanNativeSwapchain: true\n"
                b"Performing composition using CompositorVk\n"
            )
            with self.assertRaisesRegex(
                SystemExit,
                "did not reach ADB",
            ):
                self.invoke(root, result, evidence)
            assessment = json.loads(
                (root / "ASSESSMENT.json").read_text(encoding="utf-8")
            )
            self.assertFalse(
                assessment["backend_markers"]["guest_vulkan_only"]
            )

    def test_nonempty_failure_list_cannot_produce_success_assessment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.fixture(boot_completed=True)
            result["failures"] = ["avd-create"]
            with self.assertRaisesRegex(
                ValueError,
                "records failures",
            ):
                self.invoke(root, result)
            self.assertFalse((root / "ASSESSMENT.json").exists())


if __name__ == "__main__":
    unittest.main()
