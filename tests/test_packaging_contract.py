from __future__ import annotations

import re
import unittest
import xml.etree.ElementTree as element_tree
from pathlib import Path


ROOT = Path(__file__).parents[1]


class PackagingContractTest(unittest.TestCase):
    def test_all_platform_versions_match_candidate(self) -> None:
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(version, "0.3.0-alpha.6")

        android = (
            ROOT / "platform/android/app/build.gradle.kts"
        ).read_text(encoding="utf-8")
        self.assertIn(f'versionName = "{version}"', android)
        self.assertIn("versionCode = 30006", android)

        resource = (ROOT / "resources/orkela.rc").read_text(
            encoding="utf-8"
        )
        self.assertIn('FILEVERSION 0,3,0,6', resource)
        self.assertIn(f'"ProductVersion", "{version}\\0"', resource)

        installer = (
            ROOT / "packaging/windows/Orkela.nsi"
        ).read_text(encoding="utf-8")
        self.assertIn('VIProductVersion "0.3.0.6"', installer)

        for relative in (
            "platform/ios/Info.plist",
            "platform/macos/Info.plist",
        ):
            plist = (ROOT / relative).read_text(encoding="utf-8")
            self.assertRegex(
                plist,
                re.compile(
                    r"<key>CFBundleShortVersionString</key>\s*"
                    r"<string>0\.3\.0</string>"
                ),
            )
            self.assertRegex(
                plist,
                re.compile(
                    r"<key>CFBundleVersion</key>\s*"
                    r"<string>30006</string>"
                ),
            )

        metainfo = element_tree.parse(
            ROOT
            / "packaging/linux/org.scenelith.orkela.metainfo.xml"
        )
        release = metainfo.find("./releases/release")
        self.assertIsNotNone(release)
        assert release is not None
        self.assertEqual(release.attrib["version"], version)

    def test_installer_claims_only_supported_file_type(self) -> None:
        installer = (
            ROOT / "packaging/windows/Orkela.nsi"
        ).read_text(encoding="utf-8")
        self.assertIn(r"Software\Classes\.resonith\OpenWithProgids", installer)
        self.assertNotIn(r"Software\Classes\.scenelith", installer)
        self.assertNotIn(r"Software\Classes\.orka", installer)

        desktop = (
            ROOT / "packaging/linux/org.scenelith.orkela.desktop"
        ).read_text(encoding="utf-8")
        self.assertIn("Exec=orkela %f", desktop)
        self.assertIn("MimeType=audio/x-resonith;", desktop)
        mime_line = next(
            line for line in desktop.splitlines()
            if line.startswith("MimeType=")
        )
        self.assertNotIn("video/x-scenelith", mime_line.lower())
        self.assertNotIn("application/x-orka", mime_line.lower())

    def test_nsis_bootstrap_is_pinned_and_uses_binary_route(self) -> None:
        bootstrap = (
            ROOT / "tools/release/bootstrap_nsis.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "3bc2b06253a7e4957111be152ac6a536e0c7478a706e19da814038db5d706495",
            bootstrap,
        )
        self.assertIn("downloads.sourceforge.net/project/nsis/", bootstrap)
        self.assertNotIn("nsis-$version-setup.exe/download", bootstrap)
        self.assertIn("--retry-all-errors", bootstrap)


if __name__ == "__main__":
    unittest.main()
