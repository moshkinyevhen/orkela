import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPO_ROOT
    / "platform"
    / "android"
    / "ci"
    / "reduce_emulator_probe.py"
)
SPEC = importlib.util.spec_from_file_location(
    "reduce_emulator_probe",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
REDUCER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REDUCER)


class EmulatorProbeReducerTest(unittest.TestCase):
    def make_result(self, cell_id, stable=False, expected_matrix=None):
        expected_matrix = expected_matrix or REDUCER.EXPECTED
        expected = expected_matrix[cell_id]
        is_control = cell_id.startswith("control-")
        renderer = expected["renderer"]
        feature_profile = expected.get("feature_profile", "default")
        feature_state = expected.get("vulkan_native_swapchain", 0)
        tuple_name = REDUCER.EXPECTED_RENDERER_LINES[renderer]
        if stable:
            failures = []
        elif is_control:
            failures = [
                "surfaceflinger-pid-instability",
                "surfaceflinger-crash-signatures:2",
            ]
        else:
            failures = ["synthetic-rejection"]
        return {
            "schema": 1,
            "purpose": "test fixture",
            "cell_id": cell_id,
            "renderer": renderer,
            "effective_renderer_line": tuple_name,
            "effective_renderer_count": 1,
            "host_feature": {
                "profile": feature_profile,
                "requested_vulkan_native_swapchain": feature_state,
                "effective_vulkan_native_swapchain": feature_state,
                "effective_state_count": 1,
                "exact": True,
            },
            "host": {
                "runner_os": "Linux",
                "runner_arch": "X64",
                "image_os": "ubuntu24",
                "image_version": "20260720.1",
                "github_run_id": "123456789",
                "github_run_attempt": "1",
                "github_sha": "a" * 40,
                "kernel_release": "6.11.0-test",
                "machine": "x86_64",
                "kvm_access": True,
            },
            "expected_control_failure": is_control,
            "known_control_crash_reproduced": is_control,
            "crash_evidence_complete": True,
            "known_failing_tuple": is_control,
            "stage1_candidate": stable and not is_control,
            "stable": stable,
            "boot_completed": True,
            "environment_exact": True,
            "emulator": {
                "expected": expected["binary_version"],
                "observed": expected["binary_version"],
                "revision": expected["revision"],
                "build_id": expected["build_id"],
                "archive_url": REDUCER.archive_url(expected["build_id"]),
                "archive_sha1": expected["archive_sha1"],
                "archive_sha256": expected["archive_sha256"],
                "archive_size": expected["archive_size"],
                "archive_verified": True,
            },
            "guest": {
                "expected_hash_set": REDUCER.GUEST_HASH_SET,
                "hash_set": REDUCER.GUEST_HASH_SET,
                "expected_fingerprint": REDUCER.GUEST_FINGERPRINT,
                "observed_fingerprint": REDUCER.GUEST_FINGERPRINT,
                "selinux": "Enforcing",
                "luma_sampling": "default",
                "page_size": 4096,
                "display_width": 1080,
                "display_height": 1920,
            },
            "soak": {
                "requested_seconds": 120,
                "observations": 24,
                "healthy_observations": 24 if stable else 0,
                "initial_surfaceflinger_pid": "100",
                "final_surfaceflinger_pid": "100" if stable else "200",
                "pid_changes": 0 if stable else 1,
                "crash_signatures": 0 if stable else 1,
                "target_crash_signatures": (
                    0 if stable or not is_control else 2
                ),
                "valid_screenshots": 4 if stable else 0,
            },
            "failures": failures,
        }

    def write_matrix(self, root, winner=None, expected_matrix=None):
        expected_matrix = expected_matrix or REDUCER.EXPECTED
        for cell_id in expected_matrix:
            cell = root / cell_id
            cell.mkdir()
            result = self.make_result(
                cell_id,
                stable=cell_id == winner,
                expected_matrix=expected_matrix,
            )
            (cell / "PROBE-RESULT.json").write_text(
                json.dumps(result),
                encoding="utf-8",
            )

    def invoke(self, root):
        assessment = root / "assessment.json"
        promotion = root / "promotion.json"
        old_argv = sys.argv
        try:
            sys.argv = [
                str(MODULE_PATH),
                str(root),
                str(assessment),
                str(promotion),
            ]
            result = REDUCER.main()
        finally:
            sys.argv = old_argv
        return result, assessment, promotion

    def test_new_archive_can_pass_with_old_renderer_tuple_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            winner = "candidate-37_2_1-swiftshader"
            self.write_matrix(root, winner)

            result, assessment, promotion = self.invoke(root)

            self.assertEqual(result, 0)
            self.assertTrue(assessment.is_file())
            selected = json.loads(promotion.read_text(encoding="utf-8"))
            self.assertEqual(selected["cell_id"], winner)
            self.assertEqual(
                selected["emulator"]["archive_sha256"],
                REDUCER.EXPECTED[winner]["archive_sha256"],
            )
            self.assertTrue(
                selected["required_next_gate"][
                    "sdkmanager_latest_emulator_forbidden"
                ]
            )

    def test_archive_identity_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            winner = "candidate-37_1_10-swangle"
            self.write_matrix(root, winner)
            path = root / winner / "PROBE-RESULT.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            result["emulator"]["archive_size"] += 1
            path.write_text(json.dumps(result), encoding="utf-8")

            with self.assertRaisesRegex(
                ValueError,
                "archive size mismatch",
            ):
                self.invoke(root)

    def test_derived_environment_fields_are_revalidated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            winner = "candidate-37_2_1-lavapipe"
            self.write_matrix(root, winner)
            path = root / winner / "PROBE-RESULT.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            result["guest"]["page_size"] = 16384
            path.write_text(json.dumps(result), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "page-size mismatch"):
                self.invoke(root)

    def test_incomplete_boot_is_rejected_even_if_summary_claims_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            winner = "candidate-37_1_10-swiftshader"
            self.write_matrix(root, winner)
            path = root / winner / "PROBE-RESULT.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            result["boot_completed"] = False
            path.write_text(json.dumps(result), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "boot did not complete"):
                self.invoke(root)

    def test_no_candidate_records_scoped_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_matrix(root)

            with self.assertRaisesRegex(
                SystemExit,
                "no Stage-1 candidate in this exact",
            ):
                self.invoke(root)
            assessment = json.loads(
                (root / "assessment.json").read_text(encoding="utf-8")
            )
            self.assertEqual(assessment["stage1_candidates"], [])
            self.assertIn("exact GitHub runner", assessment["scope"])

    def test_vulkan_swapchain_matrix_promotes_only_effective_on(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = REDUCER.VULKAN_SWAPCHAIN_EXPECTED
            winner = (
                "candidate-37_2_1-swiftshader-vulkan-swapchain"
            )
            self.write_matrix(root, winner, expected)

            result, assessment, promotion = self.invoke(root)

            self.assertEqual(result, 0)
            reduced = json.loads(assessment.read_text(encoding="utf-8"))
            self.assertEqual(
                reduced["matrix"],
                "vulkan-native-swapchain",
            )
            selected = json.loads(promotion.read_text(encoding="utf-8"))
            self.assertEqual(selected["cell_id"], winner)
            self.assertEqual(
                selected["host_feature"][
                    "effective_vulkan_native_swapchain"
                ],
                1,
            )

    def test_vulkan_swapchain_cli_request_without_effect_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = REDUCER.VULKAN_SWAPCHAIN_EXPECTED
            winner = "candidate-37_2_1-swangle-vulkan-swapchain"
            self.write_matrix(root, winner, expected)
            path = root / winner / "PROBE-RESULT.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            result["host_feature"][
                "effective_vulkan_native_swapchain"
            ] = 0
            path.write_text(json.dumps(result), encoding="utf-8")

            with self.assertRaisesRegex(
                ValueError,
                "host-feature exactness is contradictory",
            ):
                self.invoke(root)

    def test_vulkan_swapchain_candidate_cannot_pass_without_fresh_control(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = REDUCER.VULKAN_SWAPCHAIN_EXPECTED
            winner = (
                "candidate-37_2_1-lavapipe-vulkan-swapchain"
            )
            self.write_matrix(root, winner, expected)
            control = "control-37_2_1-swiftshader-feature-off"
            path = root / control / "PROBE-RESULT.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            result["known_control_crash_reproduced"] = False
            path.write_text(json.dumps(result), encoding="utf-8")

            with self.assertRaisesRegex(
                SystemExit,
                "same-run control crash was not reproduced",
            ):
                self.invoke(root)

    def test_vulkan_swapchain_duplicate_effective_state_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = REDUCER.VULKAN_SWAPCHAIN_EXPECTED
            winner = (
                "candidate-37_2_1-swiftshader-vulkan-swapchain"
            )
            self.write_matrix(root, winner, expected)
            path = root / winner / "PROBE-RESULT.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            result["host_feature"]["effective_state_count"] = 2
            path.write_text(json.dumps(result), encoding="utf-8")

            with self.assertRaisesRegex(
                ValueError,
                "host-feature state is not singular",
            ):
                self.invoke(root)

    def test_one_unsupported_feature_cell_does_not_block_another_winner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = REDUCER.VULKAN_SWAPCHAIN_EXPECTED
            winner = "candidate-37_2_1-swangle-vulkan-swapchain"
            self.write_matrix(root, winner, expected)
            unsupported = (
                "candidate-37_2_1-lavapipe-vulkan-swapchain"
            )
            path = root / unsupported / "PROBE-RESULT.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            result["host_feature"][
                "effective_vulkan_native_swapchain"
            ] = 0
            result["host_feature"]["exact"] = False
            result["environment_exact"] = True
            path.write_text(json.dumps(result), encoding="utf-8")

            code, assessment, promotion = self.invoke(root)

            self.assertEqual(code, 0)
            reduced = json.loads(assessment.read_text(encoding="utf-8"))
            self.assertEqual(reduced["stage1_candidates"], [winner])
            selected = json.loads(promotion.read_text(encoding="utf-8"))
            self.assertEqual(selected["cell_id"], winner)

    def test_contradictory_control_summary_cannot_unlock_promotion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = REDUCER.VULKAN_SWAPCHAIN_EXPECTED
            winner = (
                "candidate-37_2_1-swiftshader-vulkan-swapchain"
            )
            self.write_matrix(root, winner, expected)
            control = "control-37_2_1-swiftshader-feature-off"
            path = root / control / "PROBE-RESULT.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            result["soak"].update({
                "healthy_observations": 24,
                "final_surfaceflinger_pid": "100",
                "pid_changes": 0,
                "crash_signatures": 0,
                "target_crash_signatures": 0,
                "valid_screenshots": 4,
            })
            result["failures"] = []
            path.write_text(json.dumps(result), encoding="utf-8")

            with self.assertRaisesRegex(
                SystemExit,
                "same-run control crash was not reproduced",
            ):
                self.invoke(root)

    def test_runner_image_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = REDUCER.VULKAN_SWAPCHAIN_EXPECTED
            winner = (
                "candidate-37_2_1-swiftshader-vulkan-swapchain"
            )
            self.write_matrix(root, winner, expected)
            path = root / winner / "PROBE-RESULT.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            result["host"]["image_version"] = "20260720.2"
            path.write_text(json.dumps(result), encoding="utf-8")

            with self.assertRaisesRegex(
                ValueError,
                "runner image identity mismatch",
            ):
                self.invoke(root)

    def test_unknown_effective_renderer_tuple_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = REDUCER.VULKAN_SWAPCHAIN_EXPECTED
            winner = (
                "candidate-37_2_1-swiftshader-vulkan-swapchain"
            )
            self.write_matrix(root, winner, expected)
            path = root / winner / "PROBE-RESULT.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            result["effective_renderer_line"] = (
                "setCurrentRenderer: malicious unknown "
                "gles:Unknown vulkan:Unknown"
            )
            path.write_text(json.dumps(result), encoding="utf-8")

            with self.assertRaisesRegex(
                ValueError,
                "effective renderer tuple is not allowlisted",
            ):
                self.invoke(root)


if __name__ == "__main__":
    unittest.main()
