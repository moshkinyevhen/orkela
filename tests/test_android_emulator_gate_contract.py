from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "platform" / "android" / "ci" / "run_emulator_gate.sh"


class AndroidEmulatorGateContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = GATE.read_text(encoding="utf-8")

    def test_every_raw_manifest_is_preceded_by_an_emulator_stop(self):
        manifest_offsets = [
            match.start()
            for match in re.finditer(
                r'> "\$evidence/RAW-EVIDENCE-SHA256SUMS"',
                self.source,
            )
        ]
        call_offsets = [
            match.start()
            for match in re.finditer(
                r"(?m)^[ ]{0,2}stop_emulator_before_evidence_seal$",
                self.source,
            )
        ]

        self.assertEqual(len(manifest_offsets), 2)
        self.assertEqual(len(call_offsets), 2)
        for manifest_offset, call_offset in zip(manifest_offsets, call_offsets):
            self.assertLess(call_offset, manifest_offset)
            self.assertLess(manifest_offset - call_offset, 500)

    def test_stop_waits_for_writer_and_clears_cleanup_ownership(self):
        function = self.source[
            self.source.index("stop_emulator_before_evidence_seal() {") :
            self.source.index(
                "\n}\n\nexport PATH=",
                self.source.index(
                    "stop_emulator_before_evidence_seal() {"
                ),
            )
        ]

        self.assertIn('tail --pid="$emulator_pid" -f /dev/null', function)
        self.assertIn('wait "$emulator_pid"', function)
        self.assertIn('emulator_pid=""', function)
        self.assertIn("EMULATOR-PROCESS-EXIT.txt", function)
        self.assertEqual(function.count("sha256sum"), 2)
        self.assertIn(
            'test "$log_hash_before" = "$log_hash_after"',
            function,
        )


if __name__ == "__main__":
    unittest.main()
