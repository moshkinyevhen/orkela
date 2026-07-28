from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).parents[1]
    / "tools"
    / "release"
    / "generate_update_manifest.py"
)
SPEC = importlib.util.spec_from_file_location(
    "orkela_update_manifest",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class UpdateManifestTest(unittest.TestCase):
    def test_manifest_is_sorted_and_hashes_exact_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "Orkela-z.bin"
            second = root / "Orkela-a.bin"
            first.write_bytes(b"windows-arm64")
            second.write_bytes(b"android-arm64")
            manifest = MODULE.build_manifest(
                version="0.3.0-alpha.6",
                channel="beta",
                commit="0123456789abcdef",
                published_at="2026-07-28T12:00:00Z",
                base_url="https://example.invalid/releases/",
                artifacts=[
                    MODULE.Artifact(first, "windows", "arm64", "installer"),
                    MODULE.Artifact(second, "android", "arm64", "apk"),
                ],
            )
            records = manifest["artifacts"]
            self.assertEqual(records[0]["platform"], "android")
            self.assertEqual(records[1]["platform"], "windows")
            self.assertEqual(
                records[1]["sha256"],
                hashlib.sha256(b"windows-arm64").hexdigest(),
            )
            encoded = json.dumps(manifest, sort_keys=True)
            self.assertNotIn(str(root), encoded)
            self.assertEqual(
                records[0]["url"],
                "https://example.invalid/releases/Orkela-a.bin",
            )

    def test_duplicate_release_filenames_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_root = root / "first"
            second_root = root / "second"
            first_root.mkdir()
            second_root.mkdir()
            first = first_root / "Orkela.exe"
            second = second_root / "Orkela.exe"
            first.write_bytes(b"x64")
            second.write_bytes(b"arm64")
            with self.assertRaisesRegex(ValueError, "globally unique"):
                MODULE.build_manifest(
                    version="0.3.0-alpha.6",
                    channel="beta",
                    commit="0123456789abcdef",
                    published_at="2026-07-28T12:00:00Z",
                    base_url="https://example.invalid/releases",
                    artifacts=[
                        MODULE.Artifact(
                            first,
                            "windows",
                            "x64",
                            "portable",
                        ),
                        MODULE.Artifact(
                            second,
                            "windows",
                            "arm64",
                            "portable",
                        ),
                    ],
                )


if __name__ == "__main__":
    unittest.main()
