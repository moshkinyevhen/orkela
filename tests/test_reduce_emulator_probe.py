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
    def make_result(self, cell_id, stable=False):
        expected = REDUCER.EXPECTED[cell_id]
        is_control = cell_id.startswith("control-")
        renderer = expected["renderer"]
        tuple_name = {
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
        }[renderer]
        failures = [] if stable else ["synthetic-rejection"]
        return {
            "schema": 1,
            "purpose": "test fixture",
            "cell_id": cell_id,
            "renderer": renderer,
            "effective_renderer_line": tuple_name,
            "effective_renderer_count": 1,
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
                "valid_screenshots": 4 if stable else 0,
            },
            "failures": failures,
        }

    def write_matrix(self, root, winner=None):
        for cell_id in REDUCER.EXPECTED:
            cell = root / cell_id
            cell.mkdir()
            result = self.make_result(cell_id, stable=cell_id == winner)
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


if __name__ == "__main__":
    unittest.main()
