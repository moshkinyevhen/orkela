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
"$ANDROID_HOME/emulator/emulator" "@$avd_name" \
  -no-window \
  -no-boot-anim \
  -no-snapshot \
  -no-audio \
  -accel on \
  -cores 2 \
  -memory 4096 \
  -partition-size 4096 \
  -gpu software \
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

# Android 17 build CE2A.260420.019 has a host/guest mapper mismatch in the
# emulator's system RegionSampling path. On Linux it can abort SurfaceFlinger
# before app instrumentation starts. Restrict the workaround to the exact two
# audited userdebug fingerprints, disable only luma-region sampling, restart
# SurfaceFlinger so it reads the property, then return ADB to an unprivileged
# shell before any Orkela APK is installed. Rendering, screenshots, UIAutomator,
# AudioTrack, native decode and the exact PCM gate remain enabled.
compositor_workaround="none"
stock_compositor_configuration=true
surfaceflinger_crash_signatures_before=0
observed_fingerprint=""
if [[ "$runtime_api" -eq 37 ]]; then
  observed_fingerprint="$(
    adb shell getprop ro.build.fingerprint | tr -d '\r'
  )"
  build_id="$(adb shell getprop ro.build.id | tr -d '\r')"
  debuggable="$(adb shell getprop ro.debuggable | tr -d '\r')"
  selinux_before="$(adb shell getenforce | tr -d '\r')"
  renderer_egl="$(adb shell getprop ro.hardware.egl | tr -d '\r')"
  renderer_transport="$(
    adb shell getprop ro.boot.qemu.gltransport.name | tr -d '\r'
  )"
  test "$observed_fingerprint" = "$expected_fingerprint"
  test "$build_id" = "CE2A.260420.019"
  test "$debuggable" = "1"
  test "$selinux_before" = "Enforcing"

  adb logcat -b crash -d \
    > "$evidence/logs/logcat-crash-before-surfaceflinger-stabilization.txt"
  surfaceflinger_crash_signatures_before="$(
    grep -Eic \
      "GoldfishMapper::readFromHost|hasReadColorBufferDma|RegionSampling" \
      "$evidence/logs/logcat-crash-before-surfaceflinger-stabilization.txt" \
      || true
  )"

  timeout --signal=TERM --kill-after=5s 30s adb root
  adb_root_ready=0
  root_deadline=$((SECONDS + 60))
  while ((SECONDS < root_deadline)); do
    if [[ "$(
        timeout --signal=TERM --kill-after=5s 10s \
          adb -s "$device_serial" shell id -u 2>/dev/null \
          | tr -d '\r' \
          || true
      )" == "0" ]]; then
      adb_root_ready=1
      break
    fi
    sleep 1
  done
  test "$adb_root_ready" -eq 1

  surfaceflinger_pid_before=""
  surfaceflinger_deadline=$((SECONDS + 60))
  while ((SECONDS < surfaceflinger_deadline)); do
    surfaceflinger_pid_before="$(
      adb shell pidof surfaceflinger 2>/dev/null | tr -d '\r' || true
    )"
    if [[ -n "$surfaceflinger_pid_before" ]]; then
      break
    fi
    sleep 1
  done
  test -n "$surfaceflinger_pid_before"

  adb shell setprop debug.sf.luma_sampling 0
  test "$(
      adb shell getprop debug.sf.luma_sampling | tr -d '\r'
    )" = "0"
  adb shell setprop ctl.restart surfaceflinger

  surfaceflinger_pid_after=""
  surfaceflinger_restarted=0
  surfaceflinger_deadline=$((SECONDS + 90))
  while ((SECONDS < surfaceflinger_deadline)); do
    surfaceflinger_pid_after="$(
      adb shell pidof surfaceflinger 2>/dev/null | tr -d '\r' || true
    )"
    surfaceflinger_state="$(
      adb shell getprop init.svc.surfaceflinger 2>/dev/null \
        | tr -d '\r' \
        || true
    )"
    surfaceflinger_service="$(
      adb shell service check SurfaceFlinger 2>/dev/null \
        | tr -d '\r' \
        || true
    )"
    if [[ -n "$surfaceflinger_pid_after" \
        && "$surfaceflinger_pid_after" != "$surfaceflinger_pid_before" \
        && "$surfaceflinger_state" = "running" \
        && "$surfaceflinger_service" = *"found"* ]]; then
      surfaceflinger_restarted=1
      break
    fi
    sleep 1
  done
  test "$surfaceflinger_restarted" -eq 1

  timeout --signal=TERM --kill-after=5s 30s adb unroot
  adb_shell_ready=0
  shell_deadline=$((SECONDS + 60))
  while ((SECONDS < shell_deadline)); do
    shell_uid="$(
      timeout --signal=TERM --kill-after=5s 10s \
        adb -s "$device_serial" shell id -u 2>/dev/null \
        | tr -d '\r' \
        || true
    )"
    if [[ "$shell_uid" = "2000" ]]; then
      adb_shell_ready=1
      break
    fi
    sleep 1
  done
  test "$adb_shell_ready" -eq 1
  test "$(adb shell getenforce | tr -d '\r')" = "Enforcing"
  test "$(
      adb shell getprop debug.sf.luma_sampling | tr -d '\r'
    )" = "0"

  {
    echo "fingerprint=$observed_fingerprint"
    echo "build_id=$build_id"
    echo "selinux_before=$selinux_before"
    echo "renderer_egl=$renderer_egl"
    echo "renderer_transport=$renderer_transport"
    echo "surfaceflinger_pid_before=$surfaceflinger_pid_before"
    echo "surfaceflinger_pid_after=$surfaceflinger_pid_after"
    echo "luma_sampling=0"
    echo "post_workaround_adb_uid=$shell_uid"
    echo "post_workaround_selinux=Enforcing"
  } > "$evidence/SURFACEFLINGER-STABILIZATION.txt"
  compositor_workaround="disable-region-luma-sampling-and-restart-surfaceflinger"
  stock_compositor_configuration=false
fi

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
  if [[ "$runtime_api" -ge 37 ]]; then
    storage_volumes="$(
      timeout --signal=TERM --kill-after=5s 10s \
        adb -s "$device_serial" shell sm list-volumes all \
        2>/dev/null \
        | tr -d '\r' \
        || true
    )"
    storage_ready=0
    if grep -Eq "^private mounted" <<< "$storage_volumes" \
        && grep -Eq "^emulated;0 mounted" <<< "$storage_volumes"; then
      storage_ready=1
    fi
  fi
  if [[ "$package_service" == *"found"* \
      && "$surfaceflinger_service" == *"found"* \
      && "$mount_service" == *"found"* \
      && "$boot_animation_ready" -eq 1 \
      && "$storage_ready" -eq 1 ]]; then
    stable_observations=$((stable_observations + 1))
    if [[ "$stable_observations" -ge 5 ]]; then
      break
    fi
  else
    stable_observations=0
  fi
  sleep 2
done
if [[ "$stable_observations" -lt 5 ]]; then
  echo "Android system services did not become stably ready" >&2
  exit 1
fi

adb shell getprop ro.build.version.sdk | tr -d '\r' | grep -Fxq "$runtime_api"
if [[ -z "$observed_fingerprint" ]]; then
  observed_fingerprint="$(
    adb shell getprop ro.build.fingerprint | tr -d '\r'
  )"
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
    "GoldfishMapper::readFromHost|hasReadColorBufferDma|RegionSampling" \
    "$evidence/logs/logcat-crash-after-gate.txt" \
    || true
)"
if [[ "$runtime_api" -eq 37 ]]; then
  surfaceflinger_pid_final="$(
    timeout --signal=TERM --kill-after=5s 10s \
      adb shell pidof surfaceflinger \
      | tr -d '\r'
  )"
  test "$surfaceflinger_pid_final" = "$surfaceflinger_pid_after"
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
  --arg compositor_workaround "$compositor_workaround" \
  --argjson stock_compositor_configuration \
    "$stock_compositor_configuration" \
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
    compositor_workaround: $compositor_workaround,
    stock_compositor_configuration: $stock_compositor_configuration,
    surfaceflinger_crash_signatures_before:
      $surfaceflinger_crash_signatures_before,
    surfaceflinger_crash_signatures_after:
      $surfaceflinger_crash_signatures_after,
    audibility_claim: false
  }' > "$evidence/RUNTIME-GATE.json"
