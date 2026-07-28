import hashlib
import importlib.util
import json
import shutil
import struct
import tempfile
import unittest
import zlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPO_ROOT
    / "platform"
    / "android"
    / "ci"
    / "reduce_android17_promotion.py"
)
SPEC = importlib.util.spec_from_file_location(
    "reduce_android17_promotion",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
REDUCER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REDUCER)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def png_chunk(kind, payload):
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload))
    )


def make_test_png(solid=False):
    width = height = 4
    rows = []
    pixels = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            if solid:
                pixel = (16, 16, 16)
            else:
                pixel = (x * 50, y * 50, (x + y) * 30)
            pixels.append(pixel)
            row.extend(pixel)
        rows.append(bytes(row))
    payload = b"".join(rows)
    data = (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(
            b"IHDR",
            struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0),
        )
        + png_chunk(b"IDAT", zlib.compress(payload))
        + png_chunk(b"IEND", b"")
    )
    luminance = [
        (54 * red + 183 * green + 19 * blue) >> 8
        for red, green, blue in pixels
    ]
    return data, {
        "width": width,
        "height": height,
        "bytes": len(data),
        "sampled_unique_rgb": len(set(pixels)),
        "sampled_luminance_span": max(luminance) - min(luminance),
    }


def surfaceflinger_tombstone(pid=100):
    tid = pid + 1
    debuggerd = pid + 1000

    def debug(message):
        return (
            f"07-28 14:37:45.920 {debuggerd:5d} {debuggerd:5d} "
            f"F DEBUG   : {message}\n"
        )

    return (
        f"07-28 14:37:45.788 {pid:5d} {tid:5d} F libc    : "
        f"Fatal signal 6 (SIGABRT), code -1 (SI_QUEUE) in tid {tid} "
        f"(surfaceflinger), pid {pid} (surfaceflinger)\n"
        + debug(REDUCER.GUEST_ANALYZER.TOMBSTONE_SEPARATOR)
        + debug("Cmdline: /system/bin/surfaceflinger")
        + debug(
            f"pid: {pid}, ppid: 1, tid: {tid}, "
            "name: surfaceflinger  >>> /system/bin/surfaceflinger <<<"
        )
        + debug("signal 6 (SIGABRT), code -1 (SI_QUEUE), fault addr --------")
        + debug(
            "#01 pc 1 /vendor/lib64/hw/vulkan.ranchu.so "
            "(gfxstream::vk::ResourceTracker::createCoherentMemory("
            "VkDevice_T*, VkDeviceMemory_T*, VkMemoryAllocateInfo const&, "
            "gfxstream::vk::VkEncoder*, VkResult&)+1)"
        )
        + debug(
            "#06 pc 6 /system/lib64/libGLESv2_angle.so (allocate+1)"
        )
    )


def write_gate_record(root, record, record_name):
    raw_manifest = root / "RAW-EVIDENCE-SHA256SUMS"
    record_path = root / record_name
    if raw_manifest.exists():
        raw_manifest.unlink()
    if record_path.exists():
        record_path.unlink()
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            entries.append(f"{digest(path)}  ./{relative}")
    raw_manifest.write_text("\n".join(entries) + "\n", encoding="utf-8")
    record["raw_evidence_manifest_sha256"] = digest(raw_manifest)
    record_path.write_text(json.dumps(record), encoding="utf-8")


class Android17PromotionReducerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.profile = {
            "page_size": 4096,
            "system_image": "system-images;android-37.0;google_apis;x86_64",
            "system_fingerprint": "fingerprint-4k",
            "system_image_manifest_sha256": "",
        }
        self.contract = {
            "emulator": {
                "emulator_version": "37.2.1.0",
                "emulator_revision": "37.2.1",
                "emulator_build_id": 15875889,
                "emulator_archive_sha1": "1" * 40,
                "emulator_archive_sha256": "2" * 64,
                "emulator_archive_size": 346539649,
            },
        }
        self.host = {
            "schema": 1,
            "source_sha": "3" * 40,
            "run_id": "10",
            "run_attempt": "1",
            "runner_name": "runner",
            "runner_os": "Linux",
            "runner_arch": "X64",
            "image_os": "ubuntu24",
            "image_version": "version",
            "host_kernel_boot_id": "host-boot",
            "host_kernel_release": "kernel",
            "host_kvm_identity": "a:b:1:660:0:108",
            "emulator_bin": (
                "/tmp/android-emulator-37.2.1-15875889/emulator/emulator"
            ),
            "avd_name": "avd-1",
            "avd_path": "/tmp/avd-1",
            "device_serial": "emulator-5556",
            "guest_boot_id": "guest-boot-1",
        }
        self.analysis = {
            "schema": 1,
            "surfaceflinger_tombstone_records": 0,
            "surfaceflinger_abort_tombstones": 0,
            "coherent_memory_angle_abort_tombstones": 0,
            "surfaceflinger_fatal_signals": 0,
            "unsupported_virtual_memory_fatals": 0,
            "boot_completed_property": "1",
            "updatable_crashing_property": "",
            "updatable_crashing_process_name": "",
            "observed_fingerprint": "fingerprint-4k",
            "boot_hardware_egl": "",
            "hardware_egl": "emulation",
        }
        self.record = {
            "schema": 1,
            "gate": "cold-boot",
            "attempt": 1,
            "host": self.host,
            "runtime_api": 37,
            "page_size": 4096,
            "system_image": self.profile["system_image"],
            "system_fingerprint": self.profile["system_fingerprint"],
            "app_sha256": "a" * 64,
            "test_apk_sha256": "b" * 64,
            "app_cert_sha256": "c" * 64,
            "test_apk_cert_sha256": "d" * 64,
            "source_sha": self.host["source_sha"],
            "guest_boot_id": self.host["guest_boot_id"],
            "emulator_version": "37.2.1.0",
            "emulator_revision": "37.2.1",
            "emulator_build_id": 15875889,
            "emulator_archive_sha1": "1" * 40,
            "emulator_archive_sha256": "2" * 64,
            "emulator_archive_size": 346539649,
            "emulator_feature_overrides": REDUCER.FEATURE_TUPLE,
            "effective_renderer": REDUCER.RENDERER_TUPLE,
            "renderer_transport": "virtio-gpu-pipe",
            "effective_vulkan": 1,
            "effective_vulkan_native_swapchain": 1,
            "effective_guest_vulkan_only": 0,
            "vk_emulation_count": 1,
            "compositor_vk_count": 1,
            "boot_completed": True,
            "selinux": "Enforcing",
            "luma_sampling": "default",
            "guest_payload_unmodified": True,
            "runtime_graphics_configuration_stock": False,
            "healthy_observations": 24,
            "initial_surfaceflinger_pid": "100",
            "final_surfaceflinger_pid": "100",
            "compositor_soak_seconds": 120,
            "compositor_soak_screenshots": 4,
            "surfaceflinger_crash_signatures_before": 0,
            "surfaceflinger_crash_signatures_after": 0,
        }
        self.write_evidence()

    def tearDown(self):
        if hasattr(self, "promotion_temp"):
            self.promotion_temp.cleanup()
        self.temp.cleanup()

    def write_evidence(self):
        (self.root / "HOST-AND-AVD-IDENTITY.json").write_text(
            json.dumps(self.host),
            encoding="utf-8",
        )
        (self.root / "GUEST-BOOT-ID.txt").write_text(
            self.host["guest_boot_id"] + "\n",
            encoding="utf-8",
        )
        (self.root / "GUEST-BOOT-ANALYSIS.json").write_text(
            json.dumps(self.analysis),
            encoding="utf-8",
        )
        logs = self.root / "logs"
        logs.mkdir()
        (logs / "emulator.log").write_text(
            "\n".join([
                "Android emulator version 37.2.1.0",
                "Feature 'GuestAngle' overridden to 'disabled'",
                REDUCER.RENDERER_TUPLE,
                "gfxstreamFeature:Vulkan = 1",
                "gfxstreamFeature:VulkanNativeSwapchain = 1",
                "gfxstreamFeature:GuestVulkanOnly = 0",
                "Initializing VkEmulation features",
                "useVulkanComposition: true",
                "useVulkanNativeSwapchain: true",
                "Performing composition using CompositorVk",
            ]) + "\n",
            encoding="utf-8",
        )
        (self.root / "EMULATOR-COMMAND.txt").write_text(
            "\n".join([
                self.host["emulator_bin"],
                f"@{self.host['avd_name']}",
                "-no-window",
                "-no-boot-anim",
                "-no-snapshot",
                "-no-snapshot-load",
                "-no-snapshot-save",
                "-no-audio",
                "-accel",
                "on",
                "-cores",
                "2",
                "-memory",
                "4096",
                "-partition-size",
                "4096",
                "-gpu",
                "swiftshader",
                "-port",
                "5556",
                "-verbose",
                "-feature",
                REDUCER.FEATURE_TUPLE,
            ]) + "\n",
            encoding="utf-8",
        )
        soak_rows = [
            (
                f"2026-07-28T00:00:{index:02d}Z,"
                f"{100 + (index - 1) * 5}.00,{index},100,"
                "Service package: found,Service SurfaceFlinger: found,"
                "Service mount: found,"
                "private mounted emulated;0 mounted"
            )
            for index in range(1, 25)
        ]
        (logs / "compositor-soak.log").write_text(
            (
                "utc,host_uptime_seconds,observation,"
                "surfaceflinger_pid,package,"
                "surfaceflinger,mount,volumes\n"
                + "\n".join(soak_rows)
                + "\n"
            ),
            encoding="utf-8",
        )
        (self.root / "COMPOSITOR-SOAK-UPTIME.txt").write_text(
            "start_uptime_seconds=100.00\n"
            "end_uptime_seconds=220.00\n",
            encoding="utf-8",
        )
        screenshot_records = []
        for index in range(1, 5):
            name = f"compositor-soak-{index}.png"
            png, png_record = make_test_png()
            (self.root / name).write_bytes(png)
            screenshot_records.append({
                "file": name,
                **png_record,
            })
        (self.root / "COMPOSITOR-SOAK-SCREENSHOTS.json").write_text(
            json.dumps({
                "schema": 1,
                "soak_seconds": 120,
                "screenshots": screenshot_records,
            }),
            encoding="utf-8",
        )
        (logs / "logcat-all-after-compositor-soak.txt").write_text(
            "",
            encoding="utf-8",
        )
        (logs / "getprop-after-compositor-soak.txt").write_text(
            "\n".join([
                "[sys.boot_completed]: [1]",
                "[sys.init.updatable_crashing]: []",
                "[sys.init.updatable_crashing_process_name]: []",
                "[ro.build.fingerprint]: [fingerprint-4k]",
                "[ro.boot.hardwareegl]: []",
                "[ro.hardware.egl]: [emulation]",
            ]) + "\n",
            encoding="utf-8",
        )
        (self.root / "payload.bin").write_bytes(b"payload")
        system_manifest = self.root / "SYSTEM-IMAGE-SHA256SUMS"
        system_manifest.write_text(
            f"{'4' * 64}  system.img\n",
            encoding="utf-8",
        )
        (self.root / "SYSTEM-IMAGE-SHA256SUMS-AFTER").write_text(
            system_manifest.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        system_hash = digest(system_manifest)
        self.profile["system_image_manifest_sha256"] = system_hash
        self.record["system_image_manifest_sha256"] = system_hash
        (self.root / "PAGE-SIZE.txt").write_text("4096\n", encoding="utf-8")
        (self.root / "SELINUX.txt").write_text(
            "Enforcing\n",
            encoding="utf-8",
        )
        (self.root / "EMULATOR-GRAPHICS-CONFIGURATION.txt").write_text(
            "\n".join([
                "fingerprint=fingerprint-4k",
                "build_id=CE2A.260420.019",
                "selinux=Enforcing",
                "renderer_egl=emulation",
                "boot_hardware_egl=empty",
                "renderer_transport=virtio-gpu-pipe",
                f"effective_renderer={REDUCER.RENDERER_TUPLE}",
                "emulator=37.2.1.0",
                "gpu_mode=swiftshader",
                "gles_backend=emulation",
                "vulkan_backend=swiftshader",
                f"emulator_feature_overrides={REDUCER.FEATURE_TUPLE}",
                f"emulator_archive_sha256={'2' * 64}",
                "guest_luma_sampling=default",
                "surfaceflinger_pid=100",
            ]) + "\n",
            encoding="utf-8",
        )

        self.refresh_raw_manifest()
        (self.root / "BOOT-GATE.json").write_text(
            json.dumps(self.record),
            encoding="utf-8",
        )

    def refresh_raw_manifest(self):
        write_gate_record(
            self.root,
            self.record,
            "BOOT-GATE.json",
        )

    def validate(self):
        return REDUCER.validate_common(
            self.root,
            self.record,
            self.profile,
            self.contract,
            "BOOT-GATE.json",
        )

    def validate_full_promotion(self, diagnostics, contract, expected):
        cold = REDUCER.validate_cold(diagnostics, contract)
        REDUCER.validate_runtime(
            diagnostics,
            contract,
            cold[0],
            cold[1],
            cold[2:],
            expected,
        )

    def test_valid_evidence_passes(self):
        self.validate()

    def test_feature_fallback_fails(self):
        self.record["effective_guest_vulkan_only"] = 1
        with self.assertRaises(REDUCER.GateError):
            self.validate()

    def test_raw_feature_fallback_fails(self):
        path = self.root / "logs" / "emulator.log"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "gfxstreamFeature:GuestVulkanOnly = 0",
                "gfxstreamFeature:GuestVulkanOnly = 1",
            ),
            encoding="utf-8",
        )
        self.refresh_raw_manifest()
        with self.assertRaises(REDUCER.GateError):
            self.validate()

    def test_incomplete_soak_ledger_fails(self):
        path = self.root / "logs" / "compositor-soak.log"
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
        self.refresh_raw_manifest()
        with self.assertRaises(REDUCER.GateError):
            self.validate()

    def test_invalid_cold_artifact_identity_fails(self):
        self.record["app_sha256"] = "not-a-digest"
        with self.assertRaises(REDUCER.GateError):
            self.validate()

    def test_surfaceflinger_pid_change_fails(self):
        self.record["final_surfaceflinger_pid"] = "101"
        with self.assertRaises(REDUCER.GateError):
            self.validate()

    def test_late_surfaceflinger_crash_fails(self):
        self.analysis["surfaceflinger_fatal_signals"] = 1
        (self.root / "GUEST-BOOT-ANALYSIS.json").write_text(
            json.dumps(self.analysis),
            encoding="utf-8",
        )
        with self.assertRaises(REDUCER.GateError):
            self.validate()

    def test_changed_raw_file_fails(self):
        (self.root / "payload.bin").write_bytes(b"changed")
        with self.assertRaises(REDUCER.GateError):
            self.validate()

    def test_changed_image_manifest_fails(self):
        self.record["system_image_manifest_sha256"] = "5" * 64
        with self.assertRaises(REDUCER.GateError):
            self.validate()

    def test_host_identity_contradiction_fails(self):
        self.record["host"] = dict(self.host, runner_name="other")
        with self.assertRaises(REDUCER.GateError):
            self.validate()

    def test_duplicate_manifest_path_fails(self):
        manifest = self.root / "RAW-EVIDENCE-SHA256SUMS"
        first = manifest.read_text(encoding="utf-8").splitlines()[0]
        manifest.write_text(
            manifest.read_text(encoding="utf-8") + first + "\n",
            encoding="utf-8",
        )
        self.record["raw_evidence_manifest_sha256"] = digest(manifest)
        with self.assertRaises(REDUCER.GateError):
            self.validate()

    def test_unsafe_manifest_path_fails(self):
        manifest = self.root / "RAW-EVIDENCE-SHA256SUMS"
        manifest.write_text(f"{'6' * 64}  ../escape\n", encoding="utf-8")
        self.record["raw_evidence_manifest_sha256"] = digest(manifest)
        with self.assertRaises(REDUCER.GateError):
            self.validate()

    def test_duplicate_json_key_fails(self):
        duplicate = self.root / "duplicate.json"
        duplicate.write_text('{"schema":1,"schema":2}', encoding="utf-8")
        with self.assertRaises(REDUCER.GateError):
            REDUCER.read_json(duplicate)

    def exact_contract(self):
        profiles = {}
        for name, profile in REDUCER.EXPECTED_PROFILES.items():
            profiles[name] = {
                **profile,
                "system_image_manifest_sha256": "7" * 64,
            }
        return {
            "schema": 1,
            "baseline_evidence": REDUCER.EXPECTED_BASELINE,
            "emulator": REDUCER.EXPECTED_EMULATOR,
            "profiles": profiles,
        }

    def build_promotion_fixture(self):
        if not hasattr(self, "promotion_temp"):
            self.promotion_temp = tempfile.TemporaryDirectory()
        diagnostics = Path(self.promotion_temp.name) / "diagnostics"
        diagnostics.mkdir()
        profile_4k = dict(self.profile)
        profile_16k = {
            "page_size": 16384,
            "system_image": (
                "system-images;android-37.0;google_apis_ps16k;x86_64"
            ),
            "system_fingerprint": "fingerprint-16k",
            "system_image_manifest_sha256": self.profile[
                "system_image_manifest_sha256"
            ],
        }
        contract = {
            "baseline_evidence": REDUCER.EXPECTED_BASELINE,
            "emulator": self.contract["emulator"],
            "profiles": {
                "37": profile_4k,
                "37-16k": profile_16k,
            },
        }
        expected = {
            "app_sha256": "a" * 64,
            "test_apk_sha256": "b" * 64,
            "app_cert_sha256": "c" * 64,
            "test_apk_cert_sha256": "d" * 64,
            "source_sha": self.host["source_sha"],
            "expected_stream_sha256": "f" * 64,
            "expected_pcm16_sha256": "e" * 64,
        }
        (diagnostics / "APK-SIGNATURE.txt").write_text(
            "Signer #1 certificate SHA-256 digest: " + "c" * 64 + "\n",
            encoding="utf-8",
        )
        (diagnostics / "TEST-APK-SIGNATURE.txt").write_text(
            "Signer #1 certificate SHA-256 digest: " + "d" * 64 + "\n",
            encoding="utf-8",
        )
        (diagnostics / "APK-SHA256SUMS").write_text(
            f"{'a' * 64}  platform/android/app-debug.apk\n"
            f"{'b' * 64}  platform/android/app-debug-androidTest.apk\n",
            encoding="utf-8",
        )

        def make_root(profile_name, attempt, runtime):
            profile = contract["profiles"][profile_name]
            if profile_name == "37":
                base_port = 5556
            else:
                base_port = 5558
            port = base_port + (attempt - 1) * 4
            mode = "runtime" if runtime else "boot"
            avd_name = f"orkela-api{profile_name}-{mode}-{attempt}"
            if runtime:
                root = diagnostics / f"runtime-api{profile_name}"
            else:
                root = (
                    diagnostics
                    / f"cold-api{profile_name}"
                    / f"attempt-{attempt}"
                )
            root.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(self.root, root)
            host = {
                **self.host,
                "avd_name": avd_name,
                "avd_path": f"/tmp/{avd_name}",
                "device_serial": f"emulator-{port}",
                "guest_boot_id": f"{profile_name}-{mode}-{attempt}-boot",
            }
            (root / "HOST-AND-AVD-IDENTITY.json").write_text(
                json.dumps(host),
                encoding="utf-8",
            )
            (root / "GUEST-BOOT-ID.txt").write_text(
                host["guest_boot_id"] + "\n",
                encoding="utf-8",
            )
            command = [
                host["emulator_bin"],
                f"@{avd_name}",
                "-no-window",
                "-no-boot-anim",
                "-no-snapshot",
                "-no-snapshot-load",
                "-no-snapshot-save",
                "-no-audio",
                "-accel",
                "on",
                "-cores",
                "2",
                "-memory",
                "4096",
                "-partition-size",
                "4096",
                "-gpu",
                "swiftshader",
                "-port",
                str(port),
                "-verbose",
                "-feature",
                REDUCER.FEATURE_TUPLE,
            ]
            (root / "EMULATOR-COMMAND.txt").write_text(
                "\n".join(command) + "\n",
                encoding="utf-8",
            )
            analysis = {
                **self.analysis,
                "observed_fingerprint": profile["system_fingerprint"],
            }
            (root / "GUEST-BOOT-ANALYSIS.json").write_text(
                json.dumps(analysis),
                encoding="utf-8",
            )
            properties = "\n".join([
                "[sys.boot_completed]: [1]",
                "[sys.init.updatable_crashing]: []",
                "[sys.init.updatable_crashing_process_name]: []",
                (
                    "[ro.build.fingerprint]: "
                    f"[{profile['system_fingerprint']}]"
                ),
                "[ro.boot.hardwareegl]: []",
                "[ro.hardware.egl]: [emulation]",
            ]) + "\n"
            (root / "logs" / "getprop-after-compositor-soak.txt").write_text(
                properties,
                encoding="utf-8",
            )
            (root / "PAGE-SIZE.txt").write_text(
                f"{profile['page_size']}\n",
                encoding="utf-8",
            )
            graphics_path = root / "EMULATOR-GRAPHICS-CONFIGURATION.txt"
            graphics_path.write_text(
                graphics_path.read_text(encoding="utf-8").replace(
                    "fingerprint=fingerprint-4k",
                    f"fingerprint={profile['system_fingerprint']}",
                ),
                encoding="utf-8",
            )
            record = {
                **self.record,
                "host": host,
                "runtime_api": 37,
                "page_size": profile["page_size"],
                "system_image": profile["system_image"],
                "system_fingerprint": profile["system_fingerprint"],
                "system_image_manifest_sha256": profile[
                    "system_image_manifest_sha256"
                ],
                "source_sha": expected["source_sha"],
                "guest_boot_id": host["guest_boot_id"],
            }
            if not runtime:
                record["gate"] = "cold-boot"
                record["attempt"] = attempt
                write_gate_record(root, record, "BOOT-GATE.json")
                return root

            for stale in ("BOOT-GATE.json", "RAW-EVIDENCE-SHA256SUMS"):
                path = root / stale
                if path.exists():
                    path.unlink()
            (root / "GUEST-RUNTIME-ANALYSIS.json").write_text(
                json.dumps(analysis),
                encoding="utf-8",
            )
            (root / "logs" / "logcat-all-after-runtime-gate.txt").write_text(
                "",
                encoding="utf-8",
            )
            (root / "logs" / "getprop-after-runtime-gate.txt").write_text(
                properties,
                encoding="utf-8",
            )
            (root / "logs" / "instrumentation.log").write_text(
                "INSTRUMENTATION_CODE: -1\n",
                encoding="utf-8",
            )
            (root / "orkela-ci-smoke.json").write_text(
                json.dumps({
                    "schema": 1,
                    "status": "pass",
                    "sample_rate": 44100,
                    "channels": 2,
                    "frames": 352800,
                    "pcm16_sha256": expected["expected_pcm16_sha256"],
                }),
                encoding="utf-8",
            )
            (root / "logs" / "activity-start.log").write_text(
                "Status: ok\n"
                "Activity: org.scenelith.orkela/.MainActivity\n",
                encoding="utf-8",
            )
            xml = (
                '<hierarchy><node resource-id="'
                'org.scenelith.orkela:id/play_button" '
                'bounds="[10,20][110,120]" /></hierarchy>'
            )
            (root / "orkela-window.xml").write_text(xml, encoding="utf-8")
            (root / "orkela-after-play.xml").write_text(
                xml,
                encoding="utf-8",
            )
            (root / "play-point.txt").write_text("60 70\n", encoding="utf-8")
            png, png_record = make_test_png()
            (root / "orkela-android.png").write_bytes(png)
            (root / "ORKELA-SCREENSHOT.json").write_text(
                json.dumps({
                    "schema": 1,
                    "format": "PNG",
                    "width": png_record["width"],
                    "height": png_record["height"],
                    "bytes": png_record["bytes"],
                }),
                encoding="utf-8",
            )
            (root / "logs" / "logcat-before-play.txt").write_text(
                "",
                encoding="utf-8",
            )
            (root / "logs" / "logcat.txt").write_text(
                "ORKELA_AUDIO_QUEUE_WRITE accepted_elements=1024\n",
                encoding="utf-8",
            )
            (root / "AUDIO-QUEUE-EVIDENCE.txt").write_text(
                "accepted_elements=1024\n",
                encoding="utf-8",
            )
            (root / "PLAY-CONTROL-DIAGNOSTIC.txt").write_text(
                "play_control_diagnostic="
                "audio-queue-write-observed-without-audibility-claim\n",
                encoding="utf-8",
            )
            app_files = "./files/orkela-ci-smoke.json\n"
            (root / "APP-DATA-FILES.txt").write_text(
                app_files,
                encoding="utf-8",
            )
            (root / "EXPECTED-APP-DATA-FILES.txt").write_text(
                app_files,
                encoding="utf-8",
            )
            record.pop("gate", None)
            record.pop("attempt", None)
            record.update({
                "application_id": "org.scenelith.orkela",
                "version_name": "0.3.0-alpha.6",
                "native_decode": "pass",
                "expected_stream_sha256": expected[
                    "expected_stream_sha256"
                ],
                "expected_pcm16_sha256": expected[
                    "expected_pcm16_sha256"
                ],
                "decoded_frames": 352800,
                "decoded_sample_rate": 44100,
                "decoded_channels": 2,
                "accepted_audio_elements": 1024,
                "wav_or_pcm_intermediary": False,
                "audibility_claim": False,
            })
            write_gate_record(root, record, "RUNTIME-GATE.json")
            return root

        for profile_name in ("37", "37-16k"):
            for attempt in (1, 2, 3):
                make_root(profile_name, attempt, False)
            make_root(profile_name, 4, True)
        return diagnostics, contract, expected

    def test_exact_promotion_contract_passes(self):
        REDUCER.validate_contract(self.exact_contract())

    def test_changed_baseline_assessment_fails(self):
        contract = self.exact_contract()
        contract["baseline_evidence"] = {
            **contract["baseline_evidence"],
            "assessment_sha256": "8" * 64,
        }
        with self.assertRaises(REDUCER.GateError):
            REDUCER.validate_contract(contract)

    def test_unexpected_profile_fails(self):
        contract = self.exact_contract()
        contract["profiles"]["37-fallback"] = contract["profiles"]["37"]
        with self.assertRaises(REDUCER.GateError):
            REDUCER.validate_contract(contract)

    def test_full_cold_and_final_paths_pass(self):
        diagnostics, contract, expected = self.build_promotion_fixture()
        (
            host_identity,
            artifact_identity,
            avd_names,
            avd_paths,
            serials,
            boot_ids,
        ) = REDUCER.validate_cold(diagnostics, contract)
        REDUCER.validate_runtime(
            diagnostics,
            contract,
            host_identity,
            artifact_identity,
            (avd_names, avd_paths, serials, boot_ids),
            expected,
        )

    def test_zero_audio_queue_fails_full_final_path(self):
        diagnostics, contract, expected = self.build_promotion_fixture()
        runtime = diagnostics / "runtime-api37"
        record = REDUCER.read_json(runtime / "RUNTIME-GATE.json")
        record["accepted_audio_elements"] = 0
        (runtime / "logs" / "logcat.txt").write_text(
            "ORKELA_AUDIO_QUEUE_WRITE accepted_elements=0\n",
            encoding="utf-8",
        )
        (runtime / "AUDIO-QUEUE-EVIDENCE.txt").write_text(
            "accepted_elements=0\n",
            encoding="utf-8",
        )
        write_gate_record(runtime, record, "RUNTIME-GATE.json")
        cold = REDUCER.validate_cold(diagnostics, contract)
        with self.assertRaises(REDUCER.GateError):
            REDUCER.validate_runtime(
                diagnostics,
                contract,
                cold[0],
                cold[1],
                cold[2:],
                expected,
            )

    def test_missing_cold_attempt_fails(self):
        diagnostics, contract, _ = self.build_promotion_fixture()
        shutil.rmtree(diagnostics / "cold-api37" / "attempt-3")
        with self.assertRaises(REDUCER.GateError):
            REDUCER.validate_cold(diagnostics, contract)

    def test_replayed_cold_attempt_fails(self):
        diagnostics, contract, _ = self.build_promotion_fixture()
        replay = diagnostics / "cold-api37" / "attempt-3"
        shutil.rmtree(replay)
        shutil.copytree(
            diagnostics / "cold-api37" / "attempt-1",
            replay,
        )
        with self.assertRaises(REDUCER.GateError):
            REDUCER.validate_cold(diagnostics, contract)

    def test_duplicate_cold_identity_fails(self):
        diagnostics, contract, _ = self.build_promotion_fixture()
        first = diagnostics / "cold-api37" / "attempt-1"
        duplicate = diagnostics / "cold-api37" / "attempt-2"
        record = REDUCER.read_json(duplicate / "BOOT-GATE.json")
        host = REDUCER.read_json(first / "HOST-AND-AVD-IDENTITY.json")
        record["host"] = host
        record["guest_boot_id"] = host["guest_boot_id"]
        (duplicate / "HOST-AND-AVD-IDENTITY.json").write_text(
            json.dumps(host),
            encoding="utf-8",
        )
        (duplicate / "GUEST-BOOT-ID.txt").write_text(
            host["guest_boot_id"] + "\n",
            encoding="utf-8",
        )
        shutil.copy2(
            first / "EMULATOR-COMMAND.txt",
            duplicate / "EMULATOR-COMMAND.txt",
        )
        write_gate_record(duplicate, record, "BOOT-GATE.json")
        with self.assertRaises(REDUCER.GateError):
            REDUCER.validate_cold(diagnostics, contract)

    def test_runtime_reuse_of_cold_identity_fails(self):
        diagnostics, contract, expected = self.build_promotion_fixture()
        cold = REDUCER.validate_cold(diagnostics, contract)
        first = diagnostics / "cold-api37" / "attempt-1"
        runtime = diagnostics / "runtime-api37"
        record = REDUCER.read_json(runtime / "RUNTIME-GATE.json")
        host = REDUCER.read_json(first / "HOST-AND-AVD-IDENTITY.json")
        record["host"] = host
        record["guest_boot_id"] = host["guest_boot_id"]
        (runtime / "HOST-AND-AVD-IDENTITY.json").write_text(
            json.dumps(host),
            encoding="utf-8",
        )
        (runtime / "GUEST-BOOT-ID.txt").write_text(
            host["guest_boot_id"] + "\n",
            encoding="utf-8",
        )
        shutil.copy2(
            first / "EMULATOR-COMMAND.txt",
            runtime / "EMULATOR-COMMAND.txt",
        )
        write_gate_record(runtime, record, "RUNTIME-GATE.json")
        with self.assertRaises(REDUCER.GateError):
            REDUCER.validate_runtime(
                diagnostics,
                contract,
                cold[0],
                cold[1],
                cold[2:],
                expected,
            )

    def test_wrong_raw_page_size_fails(self):
        diagnostics, contract, _ = self.build_promotion_fixture()
        root = diagnostics / "cold-api37" / "attempt-1"
        record = REDUCER.read_json(root / "BOOT-GATE.json")
        (root / "PAGE-SIZE.txt").write_text("16384\n", encoding="utf-8")
        write_gate_record(root, record, "BOOT-GATE.json")
        with self.assertRaises(REDUCER.GateError):
            REDUCER.validate_cold(diagnostics, contract)

    def test_wrong_raw_fingerprint_fails(self):
        diagnostics, contract, _ = self.build_promotion_fixture()
        root = diagnostics / "cold-api37" / "attempt-1"
        record = REDUCER.read_json(root / "BOOT-GATE.json")
        properties = root / "logs" / "getprop-after-compositor-soak.txt"
        properties.write_text(
            properties.read_text(encoding="utf-8").replace(
                "fingerprint-4k",
                "forged-fingerprint",
            ),
            encoding="utf-8",
        )
        write_gate_record(root, record, "BOOT-GATE.json")
        with self.assertRaises(REDUCER.GateError):
            REDUCER.validate_cold(diagnostics, contract)

    def test_wrong_raw_selinux_fails(self):
        diagnostics, contract, _ = self.build_promotion_fixture()
        root = diagnostics / "cold-api37" / "attempt-1"
        record = REDUCER.read_json(root / "BOOT-GATE.json")
        (root / "SELINUX.txt").write_text("Permissive\n", encoding="utf-8")
        write_gate_record(root, record, "BOOT-GATE.json")
        with self.assertRaises(REDUCER.GateError):
            REDUCER.validate_cold(diagnostics, contract)

    def test_wrong_raw_archive_identity_fails(self):
        diagnostics, contract, _ = self.build_promotion_fixture()
        root = diagnostics / "cold-api37" / "attempt-1"
        record = REDUCER.read_json(root / "BOOT-GATE.json")
        graphics = root / "EMULATOR-GRAPHICS-CONFIGURATION.txt"
        graphics.write_text(
            graphics.read_text(encoding="utf-8").replace(
                "emulator_archive_sha256=" + "2" * 64,
                "emulator_archive_sha256=" + "9" * 64,
            ),
            encoding="utf-8",
        )
        write_gate_record(root, record, "BOOT-GATE.json")
        with self.assertRaises(REDUCER.GateError):
            REDUCER.validate_cold(diagnostics, contract)

    def test_malformed_compositor_png_fails(self):
        diagnostics, contract, _ = self.build_promotion_fixture()
        root = diagnostics / "cold-api37" / "attempt-1"
        record = REDUCER.read_json(root / "BOOT-GATE.json")
        (root / "compositor-soak-1.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        write_gate_record(root, record, "BOOT-GATE.json")
        with self.assertRaises(REDUCER.GateError):
            REDUCER.validate_cold(diagnostics, contract)

    def test_solid_compositor_png_fails_even_with_matching_metadata(self):
        diagnostics, contract, _ = self.build_promotion_fixture()
        root = diagnostics / "cold-api37" / "attempt-1"
        record = REDUCER.read_json(root / "BOOT-GATE.json")
        png, png_record = make_test_png(solid=True)
        (root / "compositor-soak-1.png").write_bytes(png)
        screenshots_path = root / "COMPOSITOR-SOAK-SCREENSHOTS.json"
        screenshots = REDUCER.read_json(screenshots_path)
        screenshots["screenshots"][0] = {
            "file": "compositor-soak-1.png",
            **png_record,
        }
        screenshots_path.write_text(json.dumps(screenshots), encoding="utf-8")
        write_gate_record(root, record, "BOOT-GATE.json")
        with self.assertRaises(REDUCER.GateError):
            REDUCER.validate_cold(diagnostics, contract)

    def test_raw_surfaceflinger_crash_beats_unchanged_derived_json(self):
        diagnostics, contract, _ = self.build_promotion_fixture()
        root = diagnostics / "cold-api37" / "attempt-1"
        record = REDUCER.read_json(root / "BOOT-GATE.json")
        logcat = root / "logs" / "logcat-all-after-compositor-soak.txt"
        logcat.write_text(
            surfaceflinger_tombstone(),
            encoding="utf-8",
        )
        write_gate_record(root, record, "BOOT-GATE.json")
        with self.assertRaises(REDUCER.GateError):
            REDUCER.validate_cold(diagnostics, contract)

    def test_modified_pcm_marker_fails(self):
        diagnostics, contract, expected = self.build_promotion_fixture()
        runtime = diagnostics / "runtime-api37"
        record = REDUCER.read_json(runtime / "RUNTIME-GATE.json")
        smoke_path = runtime / "orkela-ci-smoke.json"
        smoke = REDUCER.read_json(smoke_path)
        smoke["pcm16_sha256"] = "9" * 64
        smoke_path.write_text(json.dumps(smoke), encoding="utf-8")
        write_gate_record(runtime, record, "RUNTIME-GATE.json")
        with self.assertRaises(REDUCER.GateError):
            self.validate_full_promotion(diagnostics, contract, expected)

    def test_wrong_signing_certificate_fails(self):
        diagnostics, contract, expected = self.build_promotion_fixture()
        (diagnostics / "APK-SIGNATURE.txt").write_text(
            "Signer #1 certificate SHA-256 digest: " + "9" * 64 + "\n",
            encoding="utf-8",
        )
        with self.assertRaises(REDUCER.GateError):
            self.validate_full_promotion(diagnostics, contract, expected)

    def test_wrong_runtime_source_fails(self):
        diagnostics, contract, expected = self.build_promotion_fixture()
        runtime = diagnostics / "runtime-api37"
        record = REDUCER.read_json(runtime / "RUNTIME-GATE.json")
        record["source_sha"] = "9" * 40
        write_gate_record(runtime, record, "RUNTIME-GATE.json")
        with self.assertRaises(REDUCER.GateError):
            self.validate_full_promotion(diagnostics, contract, expected)

    def test_wrong_runtime_stream_fails(self):
        diagnostics, contract, expected = self.build_promotion_fixture()
        runtime = diagnostics / "runtime-api37"
        record = REDUCER.read_json(runtime / "RUNTIME-GATE.json")
        record["expected_stream_sha256"] = "9" * 64
        write_gate_record(runtime, record, "RUNTIME-GATE.json")
        with self.assertRaises(REDUCER.GateError):
            self.validate_full_promotion(diagnostics, contract, expected)

    def test_out_of_order_graphics_markers_fail(self):
        diagnostics, contract, _ = self.build_promotion_fixture()
        root = diagnostics / "cold-api37" / "attempt-1"
        record = REDUCER.read_json(root / "BOOT-GATE.json")
        emulator_log = root / "logs" / "emulator.log"
        lines = emulator_log.read_text(encoding="utf-8").splitlines()
        lines[3], lines[6] = lines[6], lines[3]
        emulator_log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        write_gate_record(root, record, "BOOT-GATE.json")
        with self.assertRaises(REDUCER.GateError):
            REDUCER.validate_cold(diagnostics, contract)

    def test_host_compositor_error_fails(self):
        diagnostics, contract, _ = self.build_promotion_fixture()
        root = diagnostics / "cold-api37" / "attempt-1"
        record = REDUCER.read_json(root / "BOOT-GATE.json")
        emulator_log = root / "logs" / "emulator.log"
        emulator_log.write_text(
            emulator_log.read_text(encoding="utf-8")
            + "Failed to initialize FrameBuffer\n",
            encoding="utf-8",
        )
        write_gate_record(root, record, "BOOT-GATE.json")
        with self.assertRaises(REDUCER.GateError):
            REDUCER.validate_cold(diagnostics, contract)


if __name__ == "__main__":
    unittest.main()
