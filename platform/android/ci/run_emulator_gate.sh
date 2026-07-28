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
    ;;
  37)
    runtime_api=37
    expected_page_size=4096
    system_image="system-images;android-37.0;google_apis;x86_64"
    ;;
  37-16k)
    runtime_api=37
    expected_page_size=16384
    system_image="system-images;android-37.0;google_apis_ps16k;x86_64"
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
app_sha256="$(sha256sum "$app" | cut -d' ' -f1)"
test_apk_sha256="$(sha256sum "$test_apk" | cut -d' ' -f1)"

mkdir -p "$evidence/logs"
test -s "$app"
test -s "$test_apk"

cleanup() {
  set +e
  adb emu kill >/dev/null 2>&1
  if [[ -n "$emulator_pid" ]]; then
    if ! timeout 15 tail --pid="$emulator_pid" -f /dev/null; then
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
echo "no" | "$ANDROID_HOME/cmdline-tools/latest/bin/avdmanager" \
  create avd \
  --force \
  --name "$avd_name" \
  --package "$system_image"

"$ANDROID_HOME/emulator/emulator" "@$avd_name" \
  -no-window \
  -no-boot-anim \
  -no-snapshot \
  -gpu swiftshader_indirect \
  > "$evidence/logs/emulator.log" 2>&1 &
emulator_pid="$!"

timeout 60 adb wait-for-device
ready=0
for _ in $(seq 1 150); do
  if [[ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == "1" ]]; then
    ready=1
    break
  fi
  sleep 2
done
test "$ready" -eq 1
adb shell getprop ro.build.version.sdk | tr -d '\r' | grep -Fxq "$runtime_api"
actual_page_size="$(adb shell getconf PAGE_SIZE | tr -d '\r')"
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

adb logcat -c
adb shell am force-stop org.scenelith.orkela
adb shell am start -W \
  -n org.scenelith.orkela/.MainActivity \
  | tee "$evidence/logs/activity-start.log"
ui_ready=0
for _ in $(seq 1 30); do
  if adb shell uiautomator dump /sdcard/orkela-window.xml >/dev/null \
      && adb pull /sdcard/orkela-window.xml \
        "$evidence/orkela-window.xml" >/dev/null; then
    if grep -Fq "Ready • native pull decode • no WAV intermediary" \
        "$evidence/orkela-window.xml"; then
      ui_ready=1
      break
    fi
  fi
  sleep 1
done
test "$ui_ready" -eq 1
adb exec-out screencap -p > "$evidence/orkela-android.png"
grep -Fq "Ready • native pull decode • no WAV intermediary" \
  "$evidence/orkela-window.xml"

# Locate and invoke the real Play control. This proves UI-to-AudioTrack adapter
# submission without making an audibility claim.
python3 - "$evidence/orkela-window.xml" > "$evidence/play-point.txt" <<'PY'
import re
import sys
import xml.etree.ElementTree as ET

root = ET.parse(sys.argv[1]).getroot()
for node in root.iter("node"):
    if node.attrib.get("text") == "Play":
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
  if grep -Eq "FATAL EXCEPTION|Playback failed:" \
      "$evidence/logs/logcat.txt"; then
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
  if grep -Fq "ORKELA_AUDIO_QUEUE_WRITE accepted_elements=" \
      "$evidence/logs/logcat.txt"; then
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
