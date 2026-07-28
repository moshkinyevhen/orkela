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
    emulator_console_port=5554
    ;;
  37)
    runtime_api=37
    expected_page_size=4096
    system_image="system-images;android-37.0;google_apis;x86_64"
    emulator_console_port=5556
    ;;
  37-16k)
    runtime_api=37
    expected_page_size=16384
    system_image="system-images;android-37.0;google_apis_ps16k;x86_64"
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
adb shell getprop ro.build.version.sdk | tr -d '\r' | grep -Fxq "$runtime_api"
# Android 8 / API 26 does not ship the `getconf` shell utility. Read the
# kernel-reported mapping page size instead; unlike a build property, this
# measures the runtime that is actually executing the APK gate.
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
test "$actual_page_size" -eq "$expected_page_size"
adb shell getprop > "$evidence/DEVICE-PROPERTIES.txt"

adb install --no-streaming -r "$app"
adb install --no-streaming -r "$test_apk"
adb shell am instrument -w -r \
  org.scenelith.orkela.test/org.scenelith.orkela.NativeDecodeInstrumentation \
  2>&1 | tee "$evidence/logs/instrumentation.log"
grep -Fq "INSTRUMENTATION_CODE: -1" "$evidence/logs/instrumentation.log"
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

jq -n \
  --argjson runtime_api "$runtime_api" \
  --argjson page_size "$actual_page_size" \
  --arg system_image "$system_image" \
  --arg expected_pcm16_sha256 "$expected_pcm" \
  --arg app_sha256 "$app_sha256" \
  --arg test_apk_sha256 "$test_apk_sha256" \
  '{
    schema: 1,
    runtime_api: $runtime_api,
    page_size: $page_size,
    system_image: $system_image,
    app_sha256: $app_sha256,
    test_apk_sha256: $test_apk_sha256,
    native_decode: "pass",
    expected_pcm16_sha256: $expected_pcm16_sha256,
    audibility_claim: false
  }' > "$evidence/RUNTIME-GATE.json"
