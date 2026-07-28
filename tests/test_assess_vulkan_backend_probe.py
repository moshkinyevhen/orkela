import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from unittest import mock
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


def tombstone(pid: int) -> str:
    tid = pid + 1
    debuggerd = pid + 1000

    def debug(message: str) -> str:
        return (
            f"07-28 14:37:45.920 {debuggerd:5d} {debuggerd:5d} "
            f"F DEBUG   : {message}\n"
        )

    return (
        f"07-28 14:37:45.788 {pid:5d} {tid:5d} F libc    : "
        f"Fatal signal 6 (SIGABRT), code -1 (SI_QUEUE) in tid {tid} "
        f"(surfaceflinger), pid {pid} (surfaceflinger)\n"
        + debug(ASSESSOR.analyze.__globals__["TOMBSTONE_SEPARATOR"])
        + debug("Cmdline: /system/bin/surfaceflinger")
        + debug(
            f"pid: {pid}, ppid: 1, tid: {tid}, "
            "name: surfaceflinger  >>> /system/bin/surfaceflinger <<<"
        )
        + debug("signal 6 (SIGABRT), code -1 (SI_QUEUE), fault addr --------")
        + debug(
            "      #01 pc 1 /vendor/lib64/hw/vulkan.ranchu.so "
            "(gfxstream::vk::ResourceTracker::createCoherentMemory("
            "VkDevice_T*, VkDeviceMemory_T*, VkMemoryAllocateInfo const&, "
            "gfxstream::vk::VkEncoder*, VkResult&)+1)"
        )
        + debug(
            "      #06 pc 6 /system/lib64/libGLESv2_angle.so "
            "(allocate+1)"
        )
    )


class VulkanBackendProbeAssessmentTest(unittest.TestCase):
    def fixture(self, cell_id: str, boot_completed: bool) -> dict:
        factory = EmulatorProbeReducerTest()
        result = factory.make_result(
            cell_id,
            stable=boot_completed,
            expected_matrix=ASSESSOR.EXPECTED,
        )
        expected = ASSESSOR.EXPECTED[cell_id]
        guest_only = expected["guest_vulkan_only"]
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
            "feature_override_request_count": 1,
            "guest_angle_disabled_override_count": (
                1 if guest_only == 0 else 0
            ),
            "guest_angle_auto_enabled_count": (
                1 if guest_only == 1 else 0
            ),
            "vulkan_initialization_count": 1,
            "vulkan_composition_enabled_count": 1,
            "vulkan_composition_state_count": 1,
            "vulkan_native_swapchain_enabled_count": 1,
            "vulkan_native_swapchain_state_count": 1,
            "guest_vulkan_only_enabled_count": guest_only,
            "guest_vulkan_only_state_count": 1,
            "surfaceflinger_angle_vk_instance_created_count": (
                2 if guest_only == 1 else 0
            ),
            "compositor_vk_count": 1,
            "host_compositor_error_count": 0,
        })
        result["adb_reached"] = True
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
            "observed_fingerprint": ASSESSOR.COMMON_EXPECTED.get(
                "fingerprint",
                (
                    "google/sdk_gphone64_x86_64/emu64xa:17/"
                    "CE2A.260420.019/15611780:userdebug/dev-keys"
                ),
            ),
            "selinux": "",
            "luma_sampling": "",
            "page_size": 0,
            "display_width": 0,
            "display_height": 0,
        })
        result["process"].update({
            "alive_after_probe": True,
            "exit_code": None,
        })
        result["startup"]["failure_class"] = (
            "guest-surfaceflinger-vulkan-coherent-memory-abort-loop"
        )
        result["failures"] = [
            "boot-completion-timeout",
            "guest-surfaceflinger-vulkan-coherent-memory-abort-loop",
        ]
        return result

    def invoke(
        self,
        root: Path,
        result: dict,
        startup_evidence: bytes | None = None,
        logcat: str | None = None,
        getprop: str | None = None,
    ) -> tuple[int, Path, Path]:
        result_path = root / "PROBE-RESULT.json"
        assessment_path = root / "ASSESSMENT.json"
        logs = root / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        guest_only = ASSESSOR.EXPECTED[
            result["cell_id"]
        ]["guest_vulkan_only"]
        if startup_evidence is None:
            feature_overrides = ASSESSOR.EXPECTED[
                result["cell_id"]
            ]["feature_overrides"]
            angle_intervention = (
                b"Auto-enabled GuestAngle feature for "
                b"VulkanNativeSwapchain\n"
                if guest_only == 1
                else (
                    b"Feature 'GuestAngle' (93) is overridden to "
                    b"'disabled'\n"
                )
            )
            angle_instances = (
                b"Created VkInstance: application:'surfaceflinger' engine:'ANGLE'\n"
                b"Created VkInstance: application:'surfaceflinger' engine:'ANGLE'\n"
                if guest_only == 1
                else b""
            )
            startup_evidence = (
                (
                    f"parseAndApplyOverrides, overrides='"
                    f"{feature_overrides}'\n"
                ).encode()
                + angle_intervention
                + b"gfxstreamFeature:Vulkan = 1\n"
                b"gfxstreamFeature:VulkanNativeSwapchain = 1\n"
                + (
                    f"gfxstreamFeature:GuestVulkanOnly = "
                    f"{guest_only}\n"
                ).encode()
                + b"Initializing VkEmulation features\n"
                b"useVulkanComposition: true\n"
                b"useVulkanNativeSwapchain: true\n"
                b"Performing composition using CompositorVk\n"
                + angle_instances
            )
        if logcat is None:
            logcat = (
                tombstone(10) + tombstone(20)
                if not result["boot_completed"]
                else ""
            )
        if getprop is None:
            getprop = (
                "[ro.build.fingerprint]: "
                "[google/sdk_gphone64_x86_64/emu64xa:17/"
                "CE2A.260420.019/15611780:userdebug/dev-keys]\n"
                + (
                    "[sys.boot_completed]: []\n"
                    "[ro.boot.hardwareegl]: [angle]\n"
                    "[ro.hardware.egl]: [angle]\n"
                    "[sys.init.updatable_crashing]: [1]\n"
                    "[sys.init.updatable_crashing_process_name]: "
                    "[surfaceflinger]\n"
                    if not result["boot_completed"]
                    else (
                        "[ro.hardware.egl]: [emulation]\n"
                        "[sys.boot_completed]: [1]\n"
                    )
                )
            )
        logcat_path = logs / "logcat-all.txt"
        getprop_path = logs / "getprop.txt"
        analysis_path = root / "GUEST-STARTUP-ANALYSIS.json"
        logcat_path.write_bytes(logcat.encode("utf-8"))
        getprop_path.write_bytes(getprop.encode("utf-8"))
        analysis = ASSESSOR.analyze(logcat, getprop)
        analysis_path.write_text(
            json.dumps(analysis, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result["startup"]["guest_evidence"].update({
            "captured": True,
            "logcat_sha256": hashlib.sha256(
                logcat_path.read_bytes()
            ).hexdigest(),
            "getprop_sha256": hashlib.sha256(
                getprop_path.read_bytes()
            ).hexdigest(),
            "analysis_sha256": hashlib.sha256(
                analysis_path.read_bytes()
            ).hexdigest(),
            "surfaceflinger_abort_tombstones": analysis[
                "surfaceflinger_abort_tombstones"
            ],
            "coherent_memory_angle_abort_tombstones": analysis[
                "coherent_memory_angle_abort_tombstones"
            ],
            "updatable_crashing": analysis[
                "updatable_crashing_property"
            ],
            "updatable_crashing_process_name": analysis[
                "updatable_crashing_process_name"
            ],
            "boot_completed_property": analysis[
                "boot_completed_property"
            ],
            "boot_hardware_egl": analysis["boot_hardware_egl"],
            "hardware_egl": analysis["hardware_egl"],
        })
        result["startup"]["evidence_count"] = len(
            [line for line in startup_evidence.splitlines() if line]
        )
        result["startup"]["evidence_sha256"] = hashlib.sha256(
            startup_evidence
        ).hexdigest()
        host = result["host"]
        host_evidence = "".join(
            f"{key}={value}\n"
            for key, value in (
                ("runner_os", host["runner_os"]),
                ("runner_arch", host["runner_arch"]),
                ("runner_name", host["runner_name"]),
                ("image_os", host["image_os"]),
                ("image_version", host["image_version"]),
                ("github_run_id", host["github_run_id"]),
                ("github_run_attempt", host["github_run_attempt"]),
                ("github_sha", host["github_sha"]),
                ("kernel_release", host["kernel_release"]),
                ("machine", host["machine"]),
                ("boot_id", host["boot_id"]),
                ("kvm_access", str(host["kvm_access"]).lower()),
            )
        ).encode("utf-8")
        (root / "HOST-IDENTITY.txt").write_bytes(host_evidence)
        result["host"]["evidence_sha256"] = hashlib.sha256(
            host_evidence
        ).hexdigest()
        result_path.write_text(json.dumps(result), encoding="utf-8")
        result_path.with_name(
            "STARTUP-FAILURE-EVIDENCE.txt"
        ).write_bytes(startup_evidence)
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
        return code, result_path, assessment_path

    def test_guest_angle_off_candidate_boots_with_exact_vulkan_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            code, _, assessment_path = self.invoke(
                Path(directory),
                self.fixture(ASSESSOR.CANDIDATE_CELL_ID, True),
            )
            self.assertEqual(code, 0)
            assessment = json.loads(
                assessment_path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                assessment["status"],
                "BACKEND_REACHED_ADB_BOOT_COMPLETED",
            )
            self.assertTrue(
                assessment["backend_markers"]["guest_vulkan_only_exact"]
            )

    def test_baseline_guest_abort_loop_is_valid_negative_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            code, _, assessment_path = self.invoke(
                Path(directory),
                self.fixture(ASSESSOR.BASELINE_CELL_ID, False),
            )
            self.assertEqual(code, 0)
            assessment = json.loads(
                assessment_path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                assessment["status"],
                "BACKEND_REACHED_ADB_GUEST_BOOT_REJECTED",
            )
            self.assertTrue(
                assessment["target_guest_abort_loop_recomputed"]
            )

    def test_candidate_repeating_guest_abort_loop_fails_expected_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(SystemExit, "status mismatch"):
                self.invoke(
                    root,
                    self.fixture(ASSESSOR.CANDIDATE_CELL_ID, False),
                )
            assessment = json.loads(
                (root / "ASSESSMENT.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                assessment["status"],
                "BACKEND_REJECTED",
            )

    def test_candidate_boot_with_target_abort_loop_is_not_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.fixture(ASSESSOR.CANDIDATE_CELL_ID, True)
            logcat = tombstone(10) + tombstone(20)
            getprop = (
                "[ro.build.fingerprint]: "
                "[google/sdk_gphone64_x86_64/emu64xa:17/"
                "CE2A.260420.019/15611780:userdebug/dev-keys]\n"
                "[ro.hardware.egl]: [emulation]\n"
                "[sys.boot_completed]: [1]\n"
                "[sys.init.updatable_crashing]: [1]\n"
                "[sys.init.updatable_crashing_process_name]: "
                "[surfaceflinger]\n"
            )
            with self.assertRaisesRegex(SystemExit, "status mismatch"):
                self.invoke(
                    root,
                    result,
                    logcat=logcat,
                    getprop=getprop,
                )
            assessment = json.loads(
                (root / "ASSESSMENT.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                assessment["status"],
                "BACKEND_REJECTED",
            )
            self.assertFalse(
                assessment["clean_guest_boot_recomputed"]
            )
            self.assertTrue(
                assessment["target_guest_abort_loop_recomputed"]
            )

    def test_raw_logcat_tamper_after_hash_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, result_path, _ = self.invoke(
                root,
                self.fixture(ASSESSOR.BASELINE_CELL_ID, False),
            )
            (root / "logs" / "logcat-all.txt").write_text(
                "tampered",
                encoding="utf-8",
            )
            result = json.loads(result_path.read_text(encoding="utf-8"))
            with self.assertRaisesRegex(ValueError, "logcat hash mismatch"):
                ASSESSOR.assess(result, result_path)

    def test_claimed_crash_count_is_recomputed_from_raw_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, result_path, _ = self.invoke(
                root,
                self.fixture(ASSESSOR.BASELINE_CELL_ID, False),
            )
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["startup"]["guest_evidence"][
                "coherent_memory_angle_abort_tombstones"
            ] = 99
            with self.assertRaisesRegex(
                ValueError,
                "claimed coherent-memory tombstone count is false",
            ):
                ASSESSOR.assess(result, result_path)

    def test_guest_evidence_is_hashed_and_parsed_from_one_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, result_path, _ = self.invoke(
                root,
                self.fixture(ASSESSOR.BASELINE_CELL_ID, False),
            )
            result = json.loads(result_path.read_text(encoding="utf-8"))
            original_read_bytes = Path.read_bytes
            reads: dict[str, int] = {}

            def counted_read_bytes(path: Path) -> bytes:
                reads[path.name] = reads.get(path.name, 0) + 1
                return original_read_bytes(path)

            with mock.patch.object(
                Path,
                "read_bytes",
                new=counted_read_bytes,
            ):
                ASSESSOR.validate_guest_evidence(result, result_path)
            self.assertEqual(reads["logcat-all.txt"], 1)
            self.assertEqual(reads["getprop.txt"], 1)
            self.assertEqual(reads["GUEST-STARTUP-ANALYSIS.json"], 1)

    def test_candidate_mixed_guest_vulkan_only_state_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.fixture(ASSESSOR.CANDIDATE_CELL_ID, True)
            result["startup"]["guest_vulkan_only_enabled_count"] = 1
            result["startup"]["guest_vulkan_only_state_count"] = 2
            result["startup"][
                "surfaceflinger_angle_vk_instance_created_count"
            ] = 0
            evidence = (
                b"parseAndApplyOverrides, overrides='Vulkan,"
                b"VulkanNativeSwapchain,-GuestAngle'\n"
                b"Feature 'GuestAngle' (93) is overridden to 'disabled'\n"
                b"gfxstreamFeature:Vulkan = 1\n"
                b"gfxstreamFeature:VulkanNativeSwapchain = 1\n"
                b"gfxstreamFeature:GuestVulkanOnly = 0\n"
                b"gfxstreamFeature:GuestVulkanOnly = 1\n"
                b"Initializing VkEmulation features\n"
                b"useVulkanComposition: true\n"
                b"useVulkanNativeSwapchain: true\n"
                b"Performing composition using CompositorVk\n"
            )
            with self.assertRaisesRegex(SystemExit, "status mismatch"):
                self.invoke(root, result, evidence)

    def test_successful_boot_with_nonempty_failure_list_is_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.fixture(ASSESSOR.CANDIDATE_CELL_ID, True)
            result["failures"] = ["boot-completion-timeout"]
            with self.assertRaisesRegex(ValueError, "records failures"):
                self.invoke(root, result)
            self.assertFalse((root / "ASSESSMENT.json").exists())

    def test_claimed_success_with_empty_boot_property_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.fixture(ASSESSOR.CANDIDATE_CELL_ID, True)
            getprop = (
                "[ro.build.fingerprint]: "
                "[google/sdk_gphone64_x86_64/emu64xa:17/"
                "CE2A.260420.019/15611780:userdebug/dev-keys]\n"
                "[ro.hardware.egl]: [emulation]\n"
                "[sys.boot_completed]: []\n"
            )
            with self.assertRaisesRegex(
                ValueError,
                "boot result contradicts captured guest property",
            ):
                self.invoke(Path(directory), result, getprop=getprop)

    def test_candidate_without_explicit_guest_angle_disable_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.fixture(ASSESSOR.CANDIDATE_CELL_ID, True)
            result["startup"]["guest_angle_disabled_override_count"] = 0
            evidence = (
                b"parseAndApplyOverrides, overrides='Vulkan,"
                b"VulkanNativeSwapchain,-GuestAngle'\n"
                b"gfxstreamFeature:Vulkan = 1\n"
                b"gfxstreamFeature:VulkanNativeSwapchain = 1\n"
                b"gfxstreamFeature:GuestVulkanOnly = 0\n"
                b"Initializing VkEmulation features\n"
                b"useVulkanComposition: true\n"
                b"useVulkanNativeSwapchain: true\n"
                b"Performing composition using CompositorVk\n"
            )
            with self.assertRaisesRegex(SystemExit, "status mismatch"):
                self.invoke(root, result, evidence)

    def test_joint_same_host_pair_proves_one_coordinate_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, baseline_path, _ = self.invoke(
                root / "baseline",
                self.fixture(ASSESSOR.BASELINE_CELL_ID, False),
            )
            _, candidate_path, _ = self.invoke(
                root / "candidate",
                self.fixture(ASSESSOR.CANDIDATE_CELL_ID, True),
            )
            baseline_payload = baseline_path.read_bytes()
            candidate_payload = candidate_path.read_bytes()
            assessment = ASSESSOR.assess_pair(
                json.loads(baseline_payload),
                baseline_path,
                json.loads(candidate_payload),
                candidate_path,
                hashlib.sha256(baseline_payload).hexdigest(),
                hashlib.sha256(candidate_payload).hexdigest(),
            )
            self.assertEqual(
                assessment["status"],
                ASSESSOR.PAIR_EXPECTED_STATUS,
            )
            self.assertTrue(assessment["same_host_identity"])
            self.assertTrue(assessment["isolated_probe_instances"])
            self.assertTrue(
                assessment["one_coordinate_intervention_exact"]
            )

    def test_joint_cli_writes_the_same_host_assessment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, baseline_path, _ = self.invoke(
                root / "baseline",
                self.fixture(ASSESSOR.BASELINE_CELL_ID, False),
            )
            _, candidate_path, _ = self.invoke(
                root / "candidate",
                self.fixture(ASSESSOR.CANDIDATE_CELL_ID, True),
            )
            output = root / "JOINT-ASSESSMENT.json"
            old_argv = sys.argv
            try:
                sys.argv = [
                    str(MODULE_PATH),
                    str(baseline_path),
                    str(candidate_path),
                    str(output),
                ]
                self.assertEqual(ASSESSOR.main(), 0)
            finally:
                sys.argv = old_argv
            assessment = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                assessment["status"],
                ASSESSOR.PAIR_EXPECTED_STATUS,
            )

    def test_joint_pair_rejects_a_different_host_boot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, baseline_path, _ = self.invoke(
                root / "baseline",
                self.fixture(ASSESSOR.BASELINE_CELL_ID, False),
            )
            candidate = self.fixture(ASSESSOR.CANDIDATE_CELL_ID, True)
            candidate["host"]["boot_id"] = (
                "87654321-4321-4321-4321-cba987654321"
            )
            _, candidate_path, _ = self.invoke(
                root / "candidate",
                candidate,
            )
            baseline_payload = baseline_path.read_bytes()
            candidate_payload = candidate_path.read_bytes()
            assessment = ASSESSOR.assess_pair(
                json.loads(baseline_payload),
                baseline_path,
                json.loads(candidate_payload),
                candidate_path,
                hashlib.sha256(baseline_payload).hexdigest(),
                hashlib.sha256(candidate_payload).hexdigest(),
            )
            self.assertEqual(
                assessment["status"],
                "JOINT_BACKEND_REJECTED",
            )
            self.assertFalse(assessment["same_host_identity"])


if __name__ == "__main__":
    unittest.main()
