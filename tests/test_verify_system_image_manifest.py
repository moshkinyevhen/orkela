import hashlib
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPO_ROOT
    / "platform"
    / "android"
    / "ci"
    / "verify_system_image_manifest.py"
)
SPEC = importlib.util.spec_from_file_location(
    "verify_system_image_manifest",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class SystemImageManifestTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.image = self.root / "image"
        self.image.mkdir()
        (self.image / "system.img").write_bytes(b"system")
        (self.image / "vendor.img").write_bytes(b"vendor")
        (self.image / "package.xml").write_text("host metadata", encoding="utf-8")
        self.manifest = self.root / "expected.sha256"
        self.manifest.write_text(
            f"{digest(b'system')}  system.img\n"
            f"{digest(b'vendor')}  vendor.img\n",
            encoding="utf-8",
            newline="\n",
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_exact_payload_with_host_metadata_passes(self):
        entries = VERIFIER.verify(self.image, self.manifest)
        self.assertEqual(
            set(entries),
            {"system.img", "vendor.img"},
        )
        output = self.root / "canonical.sha256"
        VERIFIER.write_canonical(entries, output)
        self.assertEqual(output.read_bytes(), self.manifest.read_bytes())

    def test_changed_payload_fails(self):
        (self.image / "system.img").write_bytes(b"changed")
        with self.assertRaises(VERIFIER.VerificationError):
            VERIFIER.verify(self.image, self.manifest)

    def test_extra_regular_file_fails(self):
        (self.image / "extra.img").write_bytes(b"extra")
        with self.assertRaises(VERIFIER.VerificationError):
            VERIFIER.verify(self.image, self.manifest)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_extra_symlink_fails(self):
        try:
            os.symlink(
                self.image / "system.img",
                self.image / "linked-system.img",
            )
        except OSError as error:
            self.skipTest(f"symlink creation is unavailable: {error}")
        with self.assertRaises(VERIFIER.VerificationError):
            VERIFIER.verify(self.image, self.manifest)

    def test_unsafe_manifest_path_fails(self):
        self.manifest.write_text(
            f"{digest(b'system')}  ../system.img\n",
            encoding="utf-8",
        )
        with self.assertRaises(VERIFIER.VerificationError):
            VERIFIER.verify(self.image, self.manifest)


class CheckedInSystemImageManifestTest(unittest.TestCase):
    def test_checked_in_manifests_are_canonical_byte_for_byte(self):
        manifest_root = (
            REPO_ROOT / "platform" / "android" / "ci" / "manifests"
        )
        manifests = sorted(manifest_root.glob("android17-*.sha256"))
        self.assertEqual(len(manifests), 2)
        with tempfile.TemporaryDirectory() as temporary:
            for manifest in manifests:
                with self.subTest(manifest=manifest.name):
                    output = Path(temporary) / manifest.name
                    VERIFIER.write_canonical(
                        VERIFIER.read_manifest(manifest),
                        output,
                    )
                    self.assertEqual(output.read_bytes(), manifest.read_bytes())


if __name__ == "__main__":
    unittest.main()
