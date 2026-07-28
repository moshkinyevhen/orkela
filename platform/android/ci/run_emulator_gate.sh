#!/usr/bin/env bash

# Exercise the exact APK pair built by CI on one Android runtime. The gate
# proves deterministic native Resonith decode and PCM acceptance by the
# Android audio queue. A virtual device still cannot prove audibility.

set -euo pipefail

gate="${1:?usage: run_emulator_gate.sh <26|37|37-16k>}"
case "$gate" in
  26)
    runtime_api=26
    expected_page_size=4096
    system_image="system-images;android-26;google_apis;x86_64"
    expected_fingerprint=""
    emulator_console_port=5554
    ;;
  37)
    runtime_api=37
    expected_page_size=4096
    system_image="system-images;android-37.0;google_apis;x86_64"
    expected_fingerprint="google/sdk_gphone64_x86_64/emu64xa:17/CE2A.260420.019/15611780:userdebug/dev-keys"
    emulator_console_port=5556
    ;;
  37-16k)
    runtime_api=37
    expected_page_size=16384
    system_image="system-images;android-37.0;google_apis_ps16k;x86_64"
    expected_fingerprint="google/sdk_gphone16k_x86_64/emu64xa16k:17/CE2A.260420.019/15611780:userdebug/dev-keys"
    emulator_console_port=5558
    ;;
  *)
    echo "Unsupported runtime gate: $gate" >&2
    exit 2
    ;;
esac

app="${ORKELA_ANDROID_APP_APK:-platform/android/app/build/outputs/apk/debug/app-debug.apk}"
test_apk="${ORKELA_ANDROID_TEST_APK:-platform/android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk}"
evidence_root="${ORKELA_ANDROID_EVIDENCE_ROOT:-build/mobile-evidence/android/diagnostics}"
evidence="$evidence_root/runtime-api${gate}"
avd_name="orkela-api${gate}"
expected_pcm="${EXPECTED_PCM_SHA256:?EXPECTED_PCM_SHA256 is required}"
emulator_pid=""
device_serial="emulator-$emulator_console_port"
app_sha256="$(sha256sum "$app" | cut -d' ' -f1)"
test_apk_sha256="$(sha256sum "$test_apk" | cut -d' ' -f1)"
export ANDROID_USER_HOME="${ANDROID_USER_HOME:-${RUNNER_TEMP:-/tmp}/orkela-android-user}"
export ANDROID_AVD_HOME="${ANDROID_AVD_HOME:-$ANDROID_USER_HOME/avd}"

mkdir -p "$evidence/logs" "$ANDROID_AVD_HOME"
test -s "$app"
test -s "$test_apk"

cleanup() {
  set +e
  timeout --signal=TERM --kill-after=5s 15s \
    adb -s "$device_serial" emu kill >/dev/null 2>&1
  if [[ -n "$emulator_pid" ]]; then
    if ! timeout --signal=TERM --kill-after=5s 15s \
        tail --pid="$emulator_pid" -f /dev/null; then
      kill "$emulator_pid" >/dev/null 2>&1
      sleep 1
      kill -9 "$emulator_pid" >/dev/null 2>&1
    fi
    wait "$emulator_pid" >/dev/null 2>&1
  fi
  "$ANDROID_HOME/cmdline-tools/latest/bin/avdmanager" \
    delete avd \
    --name "$avd_name" \
    >/dev/null 2>&1
}
trap cleanup EXIT

"$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" \
  "emulator" \
  "platform-tools" \
  "$system_image"
export PATH="$ANDROID_HOME/platform-tools:$PATH"
command -v adb
printf 'no\n' | "$ANDROID_HOME/cmdline-tools/latest/bin/avdmanager" \
  create avd \
  --force \
  --name "$avd_name" \
  --package "$system_image" \
  --device "pixel_2" \
  --path "$ANDROID_AVD_HOME/$avd_name.avd"
"$ANDROID_HOME/emulator/emulator" -list-avds \
  | grep -Fx "$avd_name" > /dev/null

# Start the ADB server before the emulator so its console/ADB port pair is
# allocated while ADB is already listening. Android Emulator documents this
# ordering as material to device discovery for some port assignments.
adb start-server
gpu_mode="software"
if [[ "$runtime_api" -eq 37 ]]; then
  # Use one coherent official software renderer for both GLES and Vulkan on the
  # pinned Android 17 image. Emulator's generic `software` selector chose the
  # mixed swangle/lavapipe path on GitHub and repeatedly crashed SurfaceFlinger
  # RegionSampling in GoldfishMapper. SwiftShader keeps the guest compositor,
  # luma sampling, DMA features, and SELinux unchanged while replacing only the
  # host renderer selection.
  gpu_mode="swiftshader"
fi
"$ANDROID_HOME/emulator/emulator" "@$avd_name" \
  -no-window \
  -no-boot-anim \
  -no-snapshot \
  -no-audio \
  -accel on \
  -cores 2 \
  -memory 4096 \
  -partition-size 4096 \
  -gpu "$gpu_mode" \
  -port "$emulator_console_port" \
  -verbose \
  > "$evidence/logs/emulator.log" 2>&1 &
emulator_pid="$!"

# `adb wait-for-device` can remain blocked after GNU timeout sends TERM. Poll
# instead so a broken image or ADB bridge always fails within a known bound and
# leaves diagnostics rather than consuming most of the workflow timeout. Each
# gate owns a distinct even console port and therefore a distinct ADB serial.
# This prevents a stale earlier runtime from satisfying a later gate.
device_seen=0
device_deadline=$((SECONDS + 345))
while ((SECONDS < device_deadline)); do
  if timeout --signal=TERM --kill-after=5s 10s \
      adb devices -l > "$evidence/logs/adb-devices.txt"; then
    if awk \
        -v expected="$device_serial" \
        '$1 == expected && $2 == "device" { found = 1 }
         END { exit !found }' \
        "$evidence/logs/adb-devices.txt"; then
      device_seen=1
      break
    fi
  fi
  if ! kill -0 "$emulator_pid" 2>/dev/null; then
    echo "Android Emulator exited before becoming visible to ADB" >&2
    exit 1
  fi
  sleep 2
done
if [[ "$device_seen" -ne 1 ]]; then
  echo "Android Emulator did not become visible to ADB within 360 seconds" >&2
  exit 1
fi
export ANDROID_SERIAL="$device_serial"

# API 37 explicitly selects the official SwiftShader software renderer, while
# all Emulator feature flags and the Android guest compositor remain stock.
# API 26 retains Emulator's general software selector for legacy coverage.
emulator_graphics_workaround="none"
stock_android_guest_compositor_configuration=true
stock_emulator_graphics_feature_configuration=true
surfaceflinger_crash_signatures_before=0
compositor_soak_seconds=0
compositor_soak_screenshots=0
observed_fingerprint=""

ready=0
boot_deadline=$((SECONDS + 285))
while ((SECONDS < boot_deadline)); do
  boot_completed="$(
    timeout --signal=TERM --kill-after=5s 10s \
      adb -s "$device_serial" shell getprop sys.boot_completed \
      2>/dev/null \
      | tr -d '\r' \
      || true
  )"
  if [[ "$boot_completed" == "1" ]]; then
    ready=1
    break
  fi
  if ! kill -0 "$emulator_pid" 2>/dev/null; then
    echo "Android Emulator exited before completing boot" >&2
    exit 1
  fi
  sleep 2
done
if [[ "$ready" -ne 1 ]]; then
  echo "Android Emulator did not complete boot within 300 seconds" >&2
  exit 1
fi

# `sys.boot_completed=1` can precede the end of first-boot package and
# animation work. Require several consecutive healthy service observations so
# instrumentation never races a newly started API 37 system_server.
#
# Keep every observation. A readiness failure happens before the application
# is installed, so without this ledger it is impossible to distinguish a slow
# first boot from a missing Binder service, storage transition, or compositor
# restart on the exact pinned system image.
readiness_log="$evidence/logs/services-readiness.log"
printf '%s\n' \
  "utc,seconds,healthy,stable,package,surfaceflinger,mount,bootanim,storage_ready,volumes" \
  > "$readiness_log"
stable_observations=0
services_deadline=$((SECONDS + 90))
while ((SECONDS < services_deadline)); do
  package_service="$(
    timeout --signal=TERM --kill-after=5s 10s \
      adb -s "$device_serial" shell service check package \
      2>/dev/null \
      | tr -d '\r' \
      || true
  )"
  boot_animation="$(
    timeout --signal=TERM --kill-after=5s 10s \
      adb -s "$device_serial" shell getprop init.svc.bootanim \
      2>/dev/null \
      | tr -d '\r' \
      || true
  )"
  surfaceflinger_service="$(
    timeout --signal=TERM --kill-after=5s 10s \
      adb -s "$device_serial" shell service check SurfaceFlinger \
      2>/dev/null \
      | tr -d '\r' \
      || true
  )"
  mount_service="$(
    timeout --signal=TERM --kill-after=5s 10s \
      adb -s "$device_serial" shell service check mount \
      2>/dev/null \
      | tr -d '\r' \
      || true
  )"
  boot_animation_ready=0
  if [[ -z "$boot_animation" || "$boot_animation" == "stopped" ]]; then
    boot_animation_ready=1
  fi
  storage_ready=1
  storage_volumes="not-required"
  if [[ "$runtime_api" -ge 37 ]]; then
    storage_volumes="$(
      timeout --signal=TERM --kill-after=5s 10s \
        adb -s "$device_serial" shell sm list-volumes all \
        2>/dev/null \
        | tr -d '\r' \
        || true
    )"
    storage_ready=0
    if grep -Eq "^private mounted([[:space:]]|$)" <<< "$storage_volumes" \
        && grep -Eq "^emulated;0 mounted([[:space:]]|$)" \
          <<< "$storage_volumes"; then
      storage_ready=1
    fi
  fi
  package_service_log="$(
    printf '%s' "$package_service" | tr '\r\n\t,' '    '
  )"
  surfaceflinger_service_log="$(
    printf '%s' "$surfaceflinger_service" | tr '\r\n\t,' '    '
  )"
  mount_service_log="$(
    printf '%s' "$mount_service" | tr '\r\n\t,' '    '
  )"
  boot_animation_log="$(
    printf '%s' "${boot_animation:-empty}" | tr '\r\n\t,' '    '
  )"
  storage_volumes_log="$(
    printf '%s' "$storage_volumes" | tr '\r\n\t,' '    '
  )"
  readiness_healthy=0
  if [[ "$package_service" == "Service package: found" \
      && "$surfaceflinger_service" == "Service SurfaceFlinger: found" \
      && "$mount_service" == "Service mount: found" \
      && "$boot_animation_ready" -eq 1 \
      && "$storage_ready" -eq 1 ]]; then
    readiness_healthy=1
    stable_observations=$((stable_observations + 1))
  else
    stable_observations=0
  fi
  printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
    "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
    "$SECONDS" \
    "$readiness_healthy" \
    "$stable_observations" \
    "$package_service_log" \
    "$surfaceflinger_service_log" \
    "$mount_service_log" \
    "$boot_animation_log" \
    "$storage_ready" \
    "$storage_volumes_log" \
    >> "$readiness_log"
  if [[ "$stable_observations" -ge 5 ]]; then
    break
  fi
  sleep 2
done
if [[ "$stable_observations" -lt 5 ]]; then
  {
    echo "gate=$gate"
    echo "runtime_api=$runtime_api"
    echo "device_serial=$device_serial"
    echo "seconds=$SECONDS"
    echo "stable_observations=$stable_observations"
    echo "package_service=$package_service"
    echo "surfaceflinger_service=$surfaceflinger_service"
    echo "mount_service=$mount_service"
    echo "boot_animation=${boot_animation:-empty}"
    echo "storage_ready=$storage_ready"
    echo "storage_volumes_begin"
    printf '%s\n' "$storage_volumes"
    echo "storage_volumes_end"
  } > "$evidence/SERVICES-READINESS-FAILURE.txt"
  timeout --signal=TERM --kill-after=5s 20s \
    adb -s "$device_serial" shell getprop \
    > "$evidence/logs/device-properties-readiness-failure.txt" \
    2>&1 \
    || true
  timeout --signal=TERM --kill-after=5s 20s \
    adb -s "$device_serial" shell service list \
    > "$evidence/logs/service-list-readiness-failure.txt" \
    2>&1 \
    || true
  timeout --signal=TERM --kill-after=5s 20s \
    adb -s "$device_serial" shell sm list-volumes all \
    > "$evidence/logs/storage-volumes-readiness-failure.txt" \
    2>&1 \
    || true
  timeout --signal=TERM --kill-after=5s 20s \
    adb -s "$device_serial" shell df -k \
    > "$evidence/logs/filesystems-readiness-failure.txt" \
    2>&1 \
    || true
  timeout --signal=TERM --kill-after=5s 30s \
    adb -s "$device_serial" logcat -b crash -d \
    > "$evidence/logs/logcat-crash-readiness-failure.txt" \
    2>&1 \
    || true
  timeout --signal=TERM --kill-after=5s 45s \
    adb -s "$device_serial" logcat -b all -d \
    > "$evidence/logs/logcat-all-readiness-failure.txt" \
    2>&1 \
    || true
  {
    printf 'surfaceflinger='
    timeout --signal=TERM --kill-after=5s 10s \
      adb -s "$device_serial" shell pidof surfaceflinger \
      2>&1 \
      || true
    printf '\n'
    printf 'system_server='
    timeout --signal=TERM --kill-after=5s 10s \
      adb -s "$device_serial" shell pidof system_server \
      2>&1 \
      || true
    printf '\n'
  } > "$evidence/logs/core-pids-readiness-failure.txt"
  echo "Android system services did not become stably ready" >&2
  exit 1
fi

adb shell getprop ro.build.version.sdk | tr -d '\r' | grep -Fxq "$runtime_api"
observed_fingerprint="$(
  adb shell getprop ro.build.fingerprint | tr -d '\r'
)"
surfaceflinger_pid_initial="$(
  timeout --signal=TERM --kill-after=5s 10s \
    adb shell pidof surfaceflinger \
    | tr -d '\r'
)"
test -n "$surfaceflinger_pid_initial"
renderer_egl="$(adb shell getprop ro.hardware.egl | tr -d '\r')"
renderer_transport="$(
  adb shell getprop ro.boot.qemu.gltransport.name | tr -d '\r'
)"
luma_sampling="$(
  adb shell getprop debug.sf.luma_sampling | tr -d '\r'
)"
emulator_version="$(
  grep -m1 -F "Android emulator version" \
    "$evidence/logs/emulator.log" \
    | sed -E 's/^[^|]*\|[[:space:]]*//'
)"
test -n "$emulator_version"

if [[ "$runtime_api" -eq 37 ]]; then
  build_id="$(adb shell getprop ro.build.id | tr -d '\r')"
  debuggable="$(adb shell getprop ro.debuggable | tr -d '\r')"
  selinux_mode="$(adb shell getenforce | tr -d '\r')"
  test "$observed_fingerprint" = "$expected_fingerprint"
  test "$build_id" = "CE2A.260420.019"
  test "$debuggable" = "1"
  test "$selinux_mode" = "Enforcing"
  if [[ -n "$luma_sampling" && "$luma_sampling" != "1" ]]; then
    echo "Guest luma sampling is not in its stock enabled/default state" >&2
    exit 1
  fi

  grep -Fq \
    "emuglConfig_init: gpu_mode_requested: swiftshader" \
    "$evidence/logs/emulator.log"
  grep -Fq \
    "emuglConfig_init: vulkan_mode_selected:swiftshader gles_mode_selected:swiftshader" \
    "$evidence/logs/emulator.log"
  grep -Fq \
    "Graphics Adapter Android Emulator OpenGL ES Translator (Google SwiftShader)" \
    "$evidence/logs/emulator.log"

  {
    echo "fingerprint=$observed_fingerprint"
    echo "build_id=$build_id"
    echo "selinux=$selinux_mode"
    echo "renderer_egl=$renderer_egl"
    echo "renderer_transport=$renderer_transport"
    echo "emulator=$emulator_version"
    echo "gpu_mode=$gpu_mode"
    echo "gles_backend=swiftshader"
    echo "vulkan_backend=swiftshader"
    echo "emulator_feature_overrides=none"
    echo "guest_luma_sampling=${luma_sampling:-default}"
    echo "surfaceflinger_pid=$surfaceflinger_pid_initial"
  } > "$evidence/EMULATOR-GRAPHICS-CONFIGURATION.txt"
  emulator_graphics_workaround="official-explicit-swiftshader"
fi

timeout --signal=TERM --kill-after=5s 30s adb logcat -b crash -d \
  > "$evidence/logs/logcat-crash-before-app-gate.txt"
surfaceflinger_crash_signatures_before="$(
  grep -Eic \
    "GoldfishMapper::readFromHost|hasReadColorBufferDma|RegionSampling|surfaceflinger.+SIGABRT" \
    "$evidence/logs/logcat-crash-before-app-gate.txt" \
    || true
)"

if [[ "$runtime_api" -eq 37 ]]; then
  # The original failure recurred every 30-31 seconds in RegionSampling. A few
  # fast service checks can therefore pass between crashes. Exercise the stock
  # luma/compositor path for four full failure periods and require the same
  # SurfaceFlinger process, healthy Binder/storage state, four complete
  # screenshots, and no matching crash record.
  test "$surfaceflinger_crash_signatures_before" -eq 0
  compositor_soak_screenshots=4
  soak_log="$evidence/logs/compositor-soak.log"
  soak_started="$SECONDS"
  printf '%s\n' \
    "utc,observation,surfaceflinger_pid,package,surfaceflinger,mount,volumes" \
    > "$soak_log"
  for observation in $(seq 1 24); do
    soak_surfaceflinger_pid="$(
      timeout --signal=TERM --kill-after=5s 10s \
        adb -s "$device_serial" shell pidof surfaceflinger \
        | tr -d '\r'
    )"
    soak_package="$(
      timeout --signal=TERM --kill-after=5s 10s \
        adb -s "$device_serial" shell service check package \
        | tr -d '\r'
    )"
    soak_surfaceflinger="$(
      timeout --signal=TERM --kill-after=5s 10s \
        adb -s "$device_serial" shell service check SurfaceFlinger \
        | tr -d '\r'
    )"
    soak_mount="$(
      timeout --signal=TERM --kill-after=5s 10s \
        adb -s "$device_serial" shell service check mount \
        | tr -d '\r'
    )"
    soak_volumes="$(
      timeout --signal=TERM --kill-after=5s 10s \
        adb -s "$device_serial" shell sm list-volumes all \
        | tr -d '\r'
    )"
    printf '%s,%s,%s,%s,%s,%s,%s\n' \
      "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
      "$observation" \
      "$soak_surfaceflinger_pid" \
      "$(printf '%s' "$soak_package" | tr '\r\n\t,' '    ')" \
      "$(printf '%s' "$soak_surfaceflinger" | tr '\r\n\t,' '    ')" \
      "$(printf '%s' "$soak_mount" | tr '\r\n\t,' '    ')" \
      "$(printf '%s' "$soak_volumes" | tr '\r\n\t,' '    ')" \
      >> "$soak_log"
    if [[ "$soak_surfaceflinger_pid" != "$surfaceflinger_pid_initial" \
        || "$soak_package" != "Service package: found" \
        || "$soak_surfaceflinger" != "Service SurfaceFlinger: found" \
        || "$soak_mount" != "Service mount: found" ]] \
        || ! grep -Eq "^private mounted([[:space:]]|$)" \
          <<< "$soak_volumes" \
        || ! grep -Eq "^emulated;0 mounted([[:space:]]|$)" \
          <<< "$soak_volumes"; then
      echo "Android compositor became unhealthy during the 120-second soak" >&2
      exit 1
    fi
    case "$observation" in
      1|8|16|24)
        screenshot_index=$(
          case "$observation" in
            1) echo 1 ;;
            8) echo 2 ;;
            16) echo 3 ;;
            24) echo 4 ;;
          esac
        )
        timeout --signal=TERM --kill-after=5s 30s \
          adb -s "$device_serial" exec-out screencap -p \
          > "$evidence/compositor-soak-$screenshot_index.png"
        ;;
    esac
    sleep 5
  done
  compositor_soak_seconds=$((SECONDS - soak_started))
  test "$compositor_soak_seconds" -ge 120
  soak_surfaceflinger_pid_final="$(
    adb -s "$device_serial" shell pidof surfaceflinger | tr -d '\r'
  )"
  test "$soak_surfaceflinger_pid_final" = "$surfaceflinger_pid_initial"
  timeout --signal=TERM --kill-after=5s 30s adb logcat -b crash -d \
    > "$evidence/logs/logcat-crash-after-compositor-soak.txt"
  soak_crash_signatures="$(
    grep -Eic \
      "GoldfishMapper::readFromHost|hasReadColorBufferDma|RegionSampling|surfaceflinger.+SIGABRT" \
      "$evidence/logs/logcat-crash-after-compositor-soak.txt" \
      || true
  )"
  test "$soak_crash_signatures" -eq 0
  python3 - \
    "$compositor_soak_seconds" \
    "$evidence/compositor-soak-1.png" \
    "$evidence/compositor-soak-2.png" \
    "$evidence/compositor-soak-3.png" \
    "$evidence/compositor-soak-4.png" \
    > "$evidence/COMPOSITOR-SOAK-SCREENSHOTS.json" <<'PY'
import json
from pathlib import Path
import struct
import sys
import zlib

soak_seconds = int(sys.argv[1])
records = []
for raw_path in sys.argv[2:]:
    path = Path(raw_path)
    data = path.read_bytes()
    signature = b"\x89PNG\r\n\x1a\n"
    if (
        len(data) < 45
        or len(data) > 64 * 1024 * 1024
        or not data.startswith(signature)
    ):
        raise SystemExit(f"{path.name}: not a complete PNG")

    offset = len(signature)
    chunks = []
    idat = bytearray()
    width = height = 0
    bit_depth = color_type = compression = filter_method = interlace = -1
    while offset < len(data):
        if offset + 12 > len(data):
            raise SystemExit(f"{path.name}: truncated chunk header")
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        payload_start = offset + 8
        payload_end = payload_start + length
        chunk_end = payload_end + 4
        if chunk_end > len(data):
            raise SystemExit(f"{path.name}: truncated chunk payload")
        expected_crc = struct.unpack(">I", data[payload_end:chunk_end])[0]
        actual_crc = zlib.crc32(kind + data[payload_start:payload_end])
        if actual_crc != expected_crc:
            raise SystemExit(f"{path.name}: invalid CRC for {kind!r}")
        chunks.append(kind)
        if len(chunks) == 1:
            if kind != b"IHDR" or length != 13:
                raise SystemExit(f"{path.name}: no canonical IHDR")
            width, height = struct.unpack(
                ">II",
                data[payload_start:payload_start + 8],
            )
            (
                bit_depth,
                color_type,
                compression,
                filter_method,
                interlace,
            ) = data[payload_start + 8:payload_start + 13]
        if kind == b"IDAT":
            idat.extend(data[payload_start:payload_end])
        offset = chunk_end
        if kind == b"IEND":
            break

    if width <= 0 or height <= 0:
        raise SystemExit(f"{path.name}: invalid dimensions")
    if b"IDAT" not in chunks or chunks[-1] != b"IEND" or offset != len(data):
        raise SystemExit(f"{path.name}: incomplete IDAT/IEND sequence")
    if (
        bit_depth != 8
        or color_type not in (2, 6)
        or compression != 0
        or filter_method != 0
        or interlace != 0
    ):
        raise SystemExit(f"{path.name}: unsupported canonical screenshot mode")
    if (
        width > 8192
        or height > 8192
        or width * height > 32 * 1024 * 1024
    ):
        raise SystemExit(f"{path.name}: screenshot dimensions exceed bounds")

    channels = 3 if color_type == 2 else 4
    stride = width * channels
    expected_packed_bytes = height * (stride + 1)
    if expected_packed_bytes > 128 * 1024 * 1024:
        raise SystemExit(f"{path.name}: decompressed screenshot exceeds bounds")
    decompressor = zlib.decompressobj()
    packed = decompressor.decompress(
        bytes(idat),
        expected_packed_bytes + 1,
    )
    if (
        len(packed) != expected_packed_bytes
        or not decompressor.eof
        or decompressor.unconsumed_tail
        or decompressor.unused_data
    ):
        raise SystemExit(f"{path.name}: unexpected decompressed size")
    previous = bytearray(stride)
    pixels = []

    def paeth(left, above, upper_left):
        prediction = left + above - upper_left
        left_distance = abs(prediction - left)
        above_distance = abs(prediction - above)
        diagonal_distance = abs(prediction - upper_left)
        if left_distance <= above_distance and left_distance <= diagonal_distance:
            return left
        if above_distance <= diagonal_distance:
            return above
        return upper_left

    source_offset = 0
    x_step = max(1, width // 64)
    y_step = max(1, height // 64)
    for y in range(height):
        filter_type = packed[source_offset]
        source_offset += 1
        row = bytearray(packed[source_offset:source_offset + stride])
        source_offset += stride
        for byte_index in range(stride):
            left = row[byte_index - channels] if byte_index >= channels else 0
            above = previous[byte_index]
            upper_left = (
                previous[byte_index - channels]
                if byte_index >= channels
                else 0
            )
            if filter_type == 1:
                row[byte_index] = (row[byte_index] + left) & 0xFF
            elif filter_type == 2:
                row[byte_index] = (row[byte_index] + above) & 0xFF
            elif filter_type == 3:
                row[byte_index] = (
                    row[byte_index] + ((left + above) >> 1)
                ) & 0xFF
            elif filter_type == 4:
                row[byte_index] = (
                    row[byte_index] + paeth(left, above, upper_left)
                ) & 0xFF
            elif filter_type != 0:
                raise SystemExit(f"{path.name}: invalid PNG filter")
        if y % y_step == 0:
            for x in range(0, width, x_step):
                pixel_offset = x * channels
                pixels.append(tuple(row[pixel_offset:pixel_offset + 3]))
        previous = row

    unique_pixels = len(set(pixels))
    luminance = [
        (54 * red + 183 * green + 19 * blue) >> 8
        for red, green, blue in pixels
    ]
    luminance_span = max(luminance) - min(luminance)
    if unique_pixels < 8 or luminance_span < 8:
        raise SystemExit(f"{path.name}: screenshot lacks visual diversity")
    records.append({
        "file": path.name,
        "width": width,
        "height": height,
        "bytes": len(data),
        "sampled_unique_rgb": unique_pixels,
        "sampled_luminance_span": luminance_span,
    })

if len(records) != 4:
    raise SystemExit(f"expected four screenshots, found {len(records)}")
print(json.dumps({
    "schema": 1,
    "soak_seconds": soak_seconds,
    "screenshots": records,
}, indent=2, sort_keys=True))
PY
fi

# API 26 lacks getconf. Newer runtimes expose the kernel page size directly;
# this is essential for the Android 17 16-KiB gate because /proc/self/smaps can
# describe a 4-KiB compatibility mapping even on a 16-KiB kernel.
if [[ "$runtime_api" -ge 37 ]]; then
  actual_page_size="$(
    adb shell getconf PAGE_SIZE | tr -d '\r'
  )"
else
  actual_page_kib="$(
    adb shell cat /proc/self/smaps \
      | tr -d '\r' \
      | awk '
          $1 == "KernelPageSize:" && $3 == "kB" {
            value = $2
          }
          END {
            print value
          }
        '
  )"
  test -n "$actual_page_kib"
  actual_page_size="$((actual_page_kib * 1024))"
fi
test -n "$actual_page_size"
test "$actual_page_size" -eq "$expected_page_size"
adb shell getprop > "$evidence/DEVICE-PROPERTIES.txt"
adb shell df -k > "$evidence/DEVICE-STORAGE.txt"

adb install --no-streaming -r "$app"
adb install --no-streaming -r "$test_apk"
adb shell pm path org.scenelith.orkela \
  | tr -d '\r' \
  | grep -Fq "package:"
adb shell pm path org.scenelith.orkela.test \
  | tr -d '\r' \
  | grep -Fq "package:"
sleep 5
adb logcat -b all -d \
  > "$evidence/logs/logcat-before-instrumentation.txt"

set +e
adb shell am instrument -w -r \
  org.scenelith.orkela.test/org.scenelith.orkela.NativeDecodeInstrumentation \
  2>&1 | tee "$evidence/logs/instrumentation.log"
instrumentation_status="${PIPESTATUS[0]}"
set -e
instrumentation_ok=0
if [[ "$instrumentation_status" -eq 0 ]] \
    && grep -Fq "INSTRUMENTATION_CODE: -1" \
      "$evidence/logs/instrumentation.log"; then
  instrumentation_ok=1
fi
if [[ "$instrumentation_ok" -ne 1 ]]; then
  timeout --signal=TERM --kill-after=5s 30s \
    adb -s "$device_serial" logcat -b all -d \
    > "$evidence/logs/logcat-after-instrumentation-failure.txt" \
    2>&1 \
    || true
  timeout --signal=TERM --kill-after=5s 30s \
    adb -s "$device_serial" logcat -b crash -d \
    > "$evidence/logs/logcat-crash-buffer.txt" \
    2>&1 \
    || true
  timeout --signal=TERM --kill-after=5s 30s \
    adb -s "$device_serial" shell dumpsys dropbox --print system_server_crash \
    > "$evidence/logs/dropbox-system-server-crash.txt" \
    2>&1 \
    || true
  timeout --signal=TERM --kill-after=5s 30s \
    adb -s "$device_serial" shell dumpsys dropbox --print system_app_crash \
    > "$evidence/logs/dropbox-system-app-crash.txt" \
    2>&1 \
    || true
  exit 1
fi
adb exec-out run-as org.scenelith.orkela \
  cat files/orkela-ci-smoke.json \
  > "$evidence/orkela-ci-smoke.json"
jq -e \
  --arg expected "$expected_pcm" \
  '
    .schema == 1
    and .status == "pass"
    and .sample_rate == 44100
    and .channels == 2
    and .frames == 352800
    and .pcm16_sha256 == $expected
  ' "$evidence/orkela-ci-smoke.json"

# API 26 logd can reject `logcat -c` even on an emulator. Keep the existing
# ring buffer and establish monotonic baselines instead: the UI gate must add a
# new AudioTrack write and must not add a new fatal/playback error.
adb logcat -d > "$evidence/logs/logcat-before-play.txt"
baseline_queue_writes="$(
  grep -Fc "ORKELA_AUDIO_QUEUE_WRITE accepted_elements=" \
    "$evidence/logs/logcat-before-play.txt" \
    || true
)"
baseline_playback_errors="$(
  grep -Ec "FATAL EXCEPTION|Playback failed:" \
    "$evidence/logs/logcat-before-play.txt" \
    || true
)"
adb shell am force-stop org.scenelith.orkela
adb shell am start -W \
  -n org.scenelith.orkela/.MainActivity \
  | tee "$evidence/logs/activity-start.log"
ui_ready=0
for _ in $(seq 1 30); do
  if adb shell uiautomator dump /sdcard/orkela-window.xml >/dev/null \
      && adb pull /sdcard/orkela-window.xml \
        "$evidence/orkela-window.xml" >/dev/null; then
    if grep -Fq \
        'resource-id="org.scenelith.orkela:id/play_button"' \
        "$evidence/orkela-window.xml"; then
      ui_ready=1
      break
    fi
  fi
  sleep 1
done
test "$ui_ready" -eq 1
adb exec-out screencap -p > "$evidence/orkela-android.png"
python3 - "$evidence/orkela-android.png" \
  > "$evidence/ORKELA-SCREENSHOT.json" <<'PY'
import json
from pathlib import Path
import struct
import sys
import zlib

path = Path(sys.argv[1])
data = path.read_bytes()
signature = b"\x89PNG\r\n\x1a\n"
if len(data) < 45 or not data.startswith(signature):
    raise SystemExit("screenshot is not a complete PNG")

offset = len(signature)
chunks = []
width = height = 0
while offset < len(data):
    if offset + 12 > len(data):
        raise SystemExit("truncated PNG chunk header")
    length = struct.unpack(">I", data[offset:offset + 4])[0]
    kind = data[offset + 4:offset + 8]
    payload_start = offset + 8
    payload_end = payload_start + length
    chunk_end = payload_end + 4
    if chunk_end > len(data):
        raise SystemExit("truncated PNG chunk payload")
    expected_crc = struct.unpack(">I", data[payload_end:chunk_end])[0]
    actual_crc = zlib.crc32(kind + data[payload_start:payload_end])
    if actual_crc != expected_crc:
        raise SystemExit(f"invalid PNG CRC for {kind!r}")
    chunks.append(kind)
    if len(chunks) == 1:
        if kind != b"IHDR" or length != 13:
            raise SystemExit("screenshot has no canonical IHDR")
        width, height = struct.unpack(">II", data[payload_start:payload_start + 8])
    offset = chunk_end
    if kind == b"IEND":
        break

if width <= 0 or height <= 0:
    raise SystemExit("screenshot dimensions are invalid")
if b"IDAT" not in chunks or chunks[-1] != b"IEND" or offset != len(data):
    raise SystemExit("screenshot has no complete IDAT/IEND sequence")
print(json.dumps({
    "schema": 1,
    "format": "PNG",
    "width": width,
    "height": height,
    "bytes": len(data),
}, sort_keys=True))
PY
grep -Fq 'resource-id="org.scenelith.orkela:id/play_button"' \
  "$evidence/orkela-window.xml"

# Locate and invoke the real Play control through a language-independent
# resource ID. This proves UI-to-AudioTrack adapter submission without making
# an audibility claim.
python3 - "$evidence/orkela-window.xml" > "$evidence/play-point.txt" <<'PY'
import re
import sys
import xml.etree.ElementTree as ET

root = ET.parse(sys.argv[1]).getroot()
for node in root.iter("node"):
    if node.attrib.get("resource-id") == (
        "org.scenelith.orkela:id/play_button"
    ):
        match = re.fullmatch(
            r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]",
            node.attrib["bounds"],
        )
        if match:
            x1, y1, x2, y2 = map(int, match.groups())
            print((x1 + x2) // 2, (y1 + y2) // 2)
            raise SystemExit(0)
raise SystemExit(1)
PY
read -r play_x play_y < "$evidence/play-point.txt"
adb shell input tap "$play_x" "$play_y"
queue_write_seen=0
for _ in $(seq 1 20); do
  adb logcat -d > "$evidence/logs/logcat.txt"
  current_playback_errors="$(
    grep -Ec "FATAL EXCEPTION|Playback failed:" \
      "$evidence/logs/logcat.txt" \
      || true
  )"
  if ((current_playback_errors > baseline_playback_errors)); then
    echo "play_control_diagnostic=process-crash-observed" \
      > "$evidence/PLAY-CONTROL-DIAGNOSTIC.txt"
    exit 1
  fi
  if adb shell uiautomator dump /sdcard/orkela-after-play.xml >/dev/null \
      && adb pull /sdcard/orkela-after-play.xml \
        "$evidence/orkela-after-play.xml" >/dev/null; then
    if grep -Eiq "failed|cannot decode|error" \
        "$evidence/orkela-after-play.xml"; then
      echo "play_control_diagnostic=visible-error-after-invocation" \
        > "$evidence/PLAY-CONTROL-DIAGNOSTIC.txt"
      exit 1
    fi
  fi
  current_queue_writes="$(
    grep -Fc "ORKELA_AUDIO_QUEUE_WRITE accepted_elements=" \
      "$evidence/logs/logcat.txt" \
      || true
  )"
  if ((current_queue_writes > baseline_queue_writes)); then
    queue_write_seen=1
    break
  fi
  sleep 1
done
test "$queue_write_seen" -eq 1
echo "play_control_diagnostic=audio-queue-write-observed-without-audibility-claim" \
  > "$evidence/PLAY-CONTROL-DIAGNOSTIC.txt"
adb shell am force-stop org.scenelith.orkela

adb shell run-as org.scenelith.orkela find . -type f \
  | tr -d '\r' \
  | sort \
  > "$evidence/APP-DATA-FILES.txt"
printf '%s\n' "./files/orkela-ci-smoke.json" \
  > "$evidence/EXPECTED-APP-DATA-FILES.txt"
diff -u \
  "$evidence/EXPECTED-APP-DATA-FILES.txt" \
  "$evidence/APP-DATA-FILES.txt"

timeout --signal=TERM --kill-after=5s 30s adb logcat -b crash -d \
  > "$evidence/logs/logcat-crash-after-gate.txt"
surfaceflinger_crash_signatures_after="$(
  grep -Eic \
    "GoldfishMapper::readFromHost|hasReadColorBufferDma|RegionSampling|surfaceflinger.+SIGABRT" \
    "$evidence/logs/logcat-crash-after-gate.txt" \
    || true
)"
if [[ "$runtime_api" -eq 37 ]]; then
  surfaceflinger_pid_final="$(
    timeout --signal=TERM --kill-after=5s 10s \
      adb shell pidof surfaceflinger \
      | tr -d '\r'
  )"
  test "$surfaceflinger_pid_final" = "$surfaceflinger_pid_initial"
  test "$surfaceflinger_crash_signatures_after" \
    -le "$surfaceflinger_crash_signatures_before"
fi

jq -n \
  --argjson runtime_api "$runtime_api" \
  --argjson page_size "$actual_page_size" \
  --arg system_image "$system_image" \
  --arg expected_pcm16_sha256 "$expected_pcm" \
  --arg app_sha256 "$app_sha256" \
  --arg test_apk_sha256 "$test_apk_sha256" \
  --arg system_fingerprint "$observed_fingerprint" \
  --arg emulator_version "$emulator_version" \
  --arg renderer_egl "$renderer_egl" \
  --arg renderer_transport "$renderer_transport" \
  --arg emulator_gpu_mode "$gpu_mode" \
  --arg emulator_graphics_workaround "$emulator_graphics_workaround" \
  --argjson compositor_soak_seconds "$compositor_soak_seconds" \
  --argjson compositor_soak_screenshots "$compositor_soak_screenshots" \
  --argjson stock_android_guest_compositor_configuration \
    "$stock_android_guest_compositor_configuration" \
  --argjson stock_emulator_graphics_feature_configuration \
    "$stock_emulator_graphics_feature_configuration" \
  --argjson surfaceflinger_crash_signatures_before \
    "$surfaceflinger_crash_signatures_before" \
  --argjson surfaceflinger_crash_signatures_after \
    "$surfaceflinger_crash_signatures_after" \
  '{
    schema: 1,
    runtime_api: $runtime_api,
    page_size: $page_size,
    system_image: $system_image,
    app_sha256: $app_sha256,
    test_apk_sha256: $test_apk_sha256,
    native_decode: "pass",
    expected_pcm16_sha256: $expected_pcm16_sha256,
    system_fingerprint: $system_fingerprint,
    emulator_version: $emulator_version,
    renderer_egl: $renderer_egl,
    renderer_transport: $renderer_transport,
    emulator_gpu_mode: $emulator_gpu_mode,
    compositor_soak_seconds: $compositor_soak_seconds,
    compositor_soak_screenshots: $compositor_soak_screenshots,
    stock_android_guest_compositor_configuration:
      $stock_android_guest_compositor_configuration,
    stock_emulator_graphics_feature_configuration:
      $stock_emulator_graphics_feature_configuration,
    emulator_graphics_workaround: $emulator_graphics_workaround,
    surfaceflinger_crash_signatures_before:
      $surfaceflinger_crash_signatures_before,
    surfaceflinger_crash_signatures_after:
      $surfaceflinger_crash_signatures_after,
    audibility_claim: false
  }' > "$evidence/RUNTIME-GATE.json"
