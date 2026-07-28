import importlib.util
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
    / "analyze_guest_boot_evidence.py"
)
SPEC = importlib.util.spec_from_file_location(
    "analyze_guest_boot_evidence",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
ANALYZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYZER)


def tombstone(pid: int, coherent: bool = True, angle: bool = True) -> str:
    tid = pid + 1
    debuggerd = pid + 1000

    def debug(message: str, source_pid: int = debuggerd) -> str:
        return (
            f"07-28 14:37:45.920 {source_pid:5d} {source_pid:5d} "
            f"F DEBUG   : {message}\n"
        )

    stack_one = (
        "      #01 pc 1 /vendor/lib64/hw/vulkan.ranchu.so "
        "(gfxstream::vk::ResourceTracker::createCoherentMemory("
        "VkDevice_T*, VkDeviceMemory_T*, VkMemoryAllocateInfo const&, "
        "gfxstream::vk::VkEncoder*, VkResult&)+1)\n"
        if coherent
        else "      #01 pc 1 /vendor/lib64/hw/vulkan.ranchu.so (other+1)\n"
    )
    stack_six = (
        "      #06 pc 6 /system/lib64/libGLESv2_angle.so (allocate+1)\n"
        if angle
        else "      #06 pc 6 /system/lib64/libGLESv2.so (allocate+1)\n"
    )
    return (
        f"07-28 14:37:45.788 {pid:5d} {tid:5d} F libc    : "
        f"Fatal signal 6 (SIGABRT), code -1 (SI_QUEUE) in tid {tid} "
        f"(surfaceflinger), pid {pid} (surfaceflinger)\n"
        + debug(ANALYZER.TOMBSTONE_SEPARATOR)
        + debug("Cmdline: /system/bin/surfaceflinger")
        + debug(
            f"pid: {pid}, ppid: 1, tid: {tid}, "
            "name: surfaceflinger  >>> /system/bin/surfaceflinger <<<"
        )
        + debug("signal 6 (SIGABRT), code -1 (SI_QUEUE), fault addr --------")
        + "".join(debug(line) for line in (stack_one + stack_six).splitlines())
    )


class GuestBootEvidenceTest(unittest.TestCase):
    def test_complete_repeated_angle_coherent_memory_tombstones_are_counted(self):
        logcat = tombstone(10) + tombstone(20)
        getprop = (
            "[ro.build.fingerprint]: [fingerprint]\n"
            "[ro.boot.hardwareegl]: [angle]\n"
            "[ro.hardware.egl]: [angle]\n"
            "[sys.init.updatable_crashing]: [1]\n"
            "[sys.init.updatable_crashing_process_name]: [surfaceflinger]\n"
        )
        result = ANALYZER.analyze(logcat, getprop)
        self.assertEqual(
            result["coherent_memory_angle_abort_tombstones"],
            2,
        )
        self.assertEqual(result["surfaceflinger_fatal_signals"], 2)
        self.assertEqual(
            result["updatable_crashing_process_name"],
            "surfaceflinger",
        )
        self.assertEqual(result["observed_fingerprint"], "fingerprint")
        self.assertEqual(result["boot_hardware_egl"], "angle")
        self.assertEqual(result["hardware_egl"], "angle")

    def test_guest_angle_off_uses_effective_hardware_egl_property(self):
        result = ANALYZER.analyze(
            "",
            "[ro.boot.hardwareegl]: []\n"
            "[ro.hardware.egl]: [emulation]\n",
        )
        self.assertEqual(result["boot_hardware_egl"], "")
        self.assertEqual(result["hardware_egl"], "emulation")

    def test_partial_or_different_stack_is_not_the_target_failure(self):
        logcat = (
            tombstone(10, coherent=False)
            + tombstone(20, angle=False)
            + "Cmdline: /system/bin/other\nsignal 6 (SIGABRT)\n"
        )
        result = ANALYZER.analyze(logcat, "")
        self.assertEqual(
            result["coherent_memory_angle_abort_tombstones"],
            0,
        )
        self.assertEqual(result["surfaceflinger_abort_tombstones"], 2)

    def test_unstructured_spoof_lines_are_not_tombstones(self):
        spoof = (
            "07-28 14:37:45.920  545  545 I Spoof   : "
            "Cmdline: /system/bin/surfaceflinger\n"
            "07-28 14:37:45.920  545  545 I Spoof   : "
            "pid: 491, ppid: 1, tid: 524, name: surfaceflinger  "
            ">>> /system/bin/surfaceflinger <<<\n"
            "07-28 14:37:45.920  545  545 I Spoof   : "
            "signal 6 (SIGABRT), code -1\n"
            "07-28 14:37:45.920  545  545 I Spoof   : "
            "#01 /vendor/lib64/hw/vulkan.ranchu.so "
            "(gfxstream::vk::ResourceTracker::createCoherentMemory(\n"
            "07-28 14:37:45.920  545  545 I Spoof   : "
            "#06 /system/lib64/libGLESv2_angle.so\n"
        ) * 2
        result = ANALYZER.analyze(spoof, "")
        self.assertEqual(result["surfaceflinger_abort_tombstones"], 0)
        self.assertEqual(
            result["coherent_memory_angle_abort_tombstones"],
            0,
        )

    def test_foreign_debuggerd_pid_cannot_supply_stack_frame(self):
        payload = tombstone(10)
        payload = payload.replace(
            " 1010  1010 F DEBUG   :       #01",
            " 1011  1011 F DEBUG   :       #01",
        )
        result = ANALYZER.analyze(payload, "")
        self.assertEqual(
            result["coherent_memory_angle_abort_tombstones"],
            0,
        )

    def test_foreign_fatal_pid_does_not_link_to_tombstone(self):
        payload = tombstone(10).replace(
            "   10    11 F libc",
            "   12    13 F libc",
            1,
        )
        result = ANALYZER.analyze(payload, "")
        self.assertEqual(result["surfaceflinger_abort_tombstones"], 0)

    def test_exact_mesa_virtual_memory_fatal_is_counted(self):
        payload = (
            "07-28 14:37:45.700   10   11 E MESA    : "
            "FATAL: Unsupported virtual memory feature\n"
            "07-28 14:37:45.701   10   11 I Spoof   : "
            "FATAL: Unsupported virtual memory feature\n"
        )
        result = ANALYZER.analyze(payload, "")
        self.assertEqual(result["unsupported_virtual_memory_fatals"], 1)

    def test_last_getprop_value_wins(self):
        result = ANALYZER.analyze(
            "",
            "[sys.boot_completed]: []\n[sys.boot_completed]: [1]\n",
        )
        self.assertEqual(result["boot_completed_property"], "1")

    def test_cli_writes_machine_readable_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            logcat = root / "logcat.txt"
            getprop = root / "getprop.txt"
            output = root / "analysis.json"
            logcat.write_text(tombstone(10), encoding="utf-8")
            getprop.write_text(
                "[sys.init.updatable_crashing]: [1]\n",
                encoding="utf-8",
            )
            old_argv = sys.argv
            try:
                sys.argv = [
                    str(MODULE_PATH),
                    str(logcat),
                    str(getprop),
                    str(output),
                ]
                self.assertEqual(ANALYZER.main(), 0)
            finally:
                sys.argv = old_argv
            self.assertIn(
                '"coherent_memory_angle_abort_tombstones": 1',
                output.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
