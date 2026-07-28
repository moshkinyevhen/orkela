#!/usr/bin/env bash

# Probe one Android 17 host renderer without installing Orkela. This isolates
# Emulator/guest-compositor stability from application and decoder behavior.

set -u -o pipefail

renderer="${1:?usage: probe_renderer.sh <swiftshader|lavapipe|swangle|host>}"
case "$renderer" in
  swiftshader|lavapipe|swangle|host) ;;
  *)
    echo "Unsupported renderer: $renderer" >&2
    exit 2
    ;;
esac

system_image="system-images;android-37.0;google_apis;x86_64"
expected_fingerprint="google/sdk_gphone64_x86_64/emu64xa:17/CE2A.260420.019/15611780:userdebug/dev-keys"
expected_emulator_version="36.6.11.0"
emulator_bin="${ORKELA_EMULATOR_BIN:-$ANDROID_HOME/emulator/emulator}"
emulator_console_port=5554
device_serial="emulator-$emulator_console_port"
avd_name="orkela-renderer-probe-$renderer"
evidence_root="${ORKELA_RENDERER_PROBE_ROOT:-build/android37-renderer-probe}"
evidence="$evidence_root/$renderer"
export ANDROID_USER_HOME="${ANDROID_USER_HOME:-${RUNNER_TEMP:-/tmp}/orkela-renderer-probe-$renderer}"
export ANDROID_AVD_HOME="${ANDROID_AVD_HOME:-$ANDROID_USER_HOME/avd}"
export PATH="$ANDROID_HOME/platform-tools:$PATH"

emulator_pid=""
failure_file="$evidence/failures.txt"
observations_file="$evidence/observations.csv"
screenshots_json="$evidence/SCREENSHOTS.json"
result_json="$evidence/PROBE-RESULT.json"
boot_completed=false
environment_exact=false
stable=false
observations=0
healthy_observations=0
pid_changes=0
crash_signatures=0
valid_screenshots=0
initial_surfaceflinger_pid=""
final_surfaceflinger_pid=""
observed_fingerprint=""
observed_selinux=""
observed_luma=""
observed_page_size=""
effective_renderer_line=""
known_failing_tuple=false
stage1_candidate=false
known_control_crash_reproduced=false
crash_evidence_complete=false
pre_soak_log_ok=false
post_soak_log_ok=false
luma_query_ok=false
display_width=0
display_height=0

mkdir -p "$evidence/logs" "$evidence/screenshots" "$ANDROID_AVD_HOME"
: > "$failure_file"
printf '%s\n' \
  "utc,index,elapsed_seconds,healthy,surfaceflinger_pid,package,surfaceflinger,mount,storage" \
  > "$observations_file"

record_failure() {
  printf '%s\n' "$1" >> "$failure_file"
}

capture_optional_diagnostics() {
  timeout --signal=TERM --kill-after=3s 10s \
    adb -s "$device_serial" shell getprop \
    > "$evidence/logs/getprop.txt" 2>&1 || true
  timeout --signal=TERM --kill-after=3s 10s \
    adb -s "$device_serial" shell dumpsys SurfaceFlinger \
    > "$evidence/logs/dumpsys-SurfaceFlinger.txt" 2>&1 || true
  timeout --signal=TERM --kill-after=3s 10s \
    adb -s "$device_serial" shell dumpsys display \
    > "$evidence/logs/dumpsys-display.txt" 2>&1 || true
  timeout --signal=TERM --kill-after=3s 15s \
    adb -s "$device_serial" logcat -b all -d -v threadtime \
    > "$evidence/logs/logcat-all.txt" 2>&1 || true
}

cleanup() {
  set +e
  capture_optional_diagnostics
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
    delete avd --name "$avd_name" >/dev/null 2>&1
}
trap cleanup EXIT

emulator_version="$(
  "$emulator_bin" -version 2>&1 \
    | tee "$evidence/EMULATOR-VERSION.txt" \
    | sed -n 's/^Android emulator version \([^ ]*\).*/\1/p' \
    | head -n 1
)"
if [[ "$emulator_version" != "$expected_emulator_version" ]]; then
  record_failure \
    "emulator-version:${emulator_version:-missing}:expected:$expected_emulator_version"
fi

printf 'no\n' | "$ANDROID_HOME/cmdline-tools/latest/bin/avdmanager" \
  create avd \
  --force \
  --name "$avd_name" \
  --package "$system_image" \
  --device "pixel_2" \
  --path "$ANDROID_AVD_HOME/$avd_name.avd" \
  > "$evidence/logs/avd-create.txt" 2>&1
if [[ "$?" -ne 0 ]]; then
  record_failure "avd-create"
fi

adb start-server > "$evidence/logs/adb-start-server.txt" 2>&1 || true
"$emulator_bin" "@$avd_name" \
  -no-window \
  -no-boot-anim \
  -no-snapshot \
  -no-audio \
  -accel on \
  -cores 2 \
  -memory 4096 \
  -partition-size 4096 \
  -gpu "$renderer" \
  -port "$emulator_console_port" \
  -verbose \
  > "$evidence/logs/emulator.log" 2>&1 &
emulator_pid="$!"

device_seen=false
device_deadline=$((SECONDS + 345))
while ((SECONDS < device_deadline)); do
  timeout --signal=TERM --kill-after=5s 10s \
    adb devices -l > "$evidence/logs/adb-devices.txt" 2>&1 || true
  if awk \
      -v expected="$device_serial" \
      '$1 == expected && $2 == "device" { found = 1 }
       END { exit !found }' \
      "$evidence/logs/adb-devices.txt"; then
    device_seen=true
    break
  fi
  if ! kill -0 "$emulator_pid" 2>/dev/null; then
    record_failure "emulator-exited-before-adb"
    break
  fi
  sleep 2
done
if [[ "$device_seen" != "true" ]]; then
  record_failure "adb-device-timeout"
else
  boot_deadline=$((SECONDS + 285))
  while ((SECONDS < boot_deadline)); do
    boot_property="$(
      timeout --signal=TERM --kill-after=5s 10s \
        adb -s "$device_serial" shell getprop sys.boot_completed \
        2>/dev/null \
        | tr -d '\r' \
        || true
    )"
    if [[ "$boot_property" == "1" ]]; then
      boot_completed=true
      break
    fi
    if ! kill -0 "$emulator_pid" 2>/dev/null; then
      record_failure "emulator-exited-before-boot"
      break
    fi
    sleep 2
  done
fi

if [[ "$boot_completed" == "true" ]]; then
  if timeout --signal=TERM --kill-after=3s 10s \
      adb -s "$device_serial" shell \
        getprop ro.build.fingerprint \
        > "$evidence/logs/fingerprint.txt" 2>&1; then
    observed_fingerprint="$(
      tr -d '\r' < "$evidence/logs/fingerprint.txt"
    )"
  else
    record_failure "fingerprint-query"
  fi
  if timeout --signal=TERM --kill-after=3s 10s \
      adb -s "$device_serial" shell getenforce \
        > "$evidence/logs/selinux.txt" 2>&1; then
    observed_selinux="$(tr -d '\r' < "$evidence/logs/selinux.txt")"
  else
    record_failure "selinux-query"
  fi
  if timeout --signal=TERM --kill-after=3s 10s \
      adb -s "$device_serial" shell \
        getprop debug.sf.luma_sampling \
        > "$evidence/logs/luma-sampling.txt" 2>&1; then
    luma_query_ok=true
    observed_luma="$(
      tr -d '\r' < "$evidence/logs/luma-sampling.txt"
    )"
  else
    record_failure "luma-sampling-query"
  fi
  if timeout --signal=TERM --kill-after=3s 10s \
      adb -s "$device_serial" shell getconf PAGE_SIZE \
        > "$evidence/logs/page-size.txt" 2>&1; then
    observed_page_size="$(
      tr -d '\r' < "$evidence/logs/page-size.txt"
    )"
  else
    record_failure "page-size-query"
  fi
  if timeout --signal=TERM --kill-after=3s 10s \
      adb -s "$device_serial" shell wm size \
        > "$evidence/logs/wm-size.txt" 2>&1; then
    display_dimensions="$(
      sed -n \
        's/^Physical size: \([0-9][0-9]*\)x\([0-9][0-9]*\)$/\1 \2/p' \
        "$evidence/logs/wm-size.txt" \
        | head -n 1
    )"
    if [[ -n "$display_dimensions" ]]; then
      read -r display_width display_height <<< "$display_dimensions"
    else
      record_failure "display-size-parse"
    fi
  else
    record_failure "display-size-query"
  fi
  {
    echo "requested_renderer=$renderer"
    echo "fingerprint=$observed_fingerprint"
    echo "selinux=$observed_selinux"
    echo "luma_sampling=${observed_luma:-default}"
    echo "page_size=$observed_page_size"
    echo "display_size=${display_width}x${display_height}"
    echo "emulator_archive_sha256=${ORKELA_EMULATOR_ARCHIVE_SHA256:-missing}"
    echo "emulator_archive_verified=${ORKELA_EMULATOR_ARCHIVE_VERIFIED:-false}"
    echo "system_image_hashes_verified=${ORKELA_IMAGE_HASHES_VERIFIED:-false}"
  } > "$evidence/GUEST-ENVIRONMENT.txt"
  if [[ "$observed_fingerprint" != "$expected_fingerprint" ]]; then
    record_failure "fingerprint-mismatch"
  fi
  if [[ "$observed_selinux" != "Enforcing" ]]; then
    record_failure "selinux-not-enforcing"
  fi
  if [[ "$luma_query_ok" != "true" ]]; then
    record_failure "luma-sampling-not-default-enabled"
  elif [[ -n "$observed_luma" && "$observed_luma" != "1" ]]; then
    record_failure "luma-sampling-not-default-enabled"
  fi
  if [[ "$observed_page_size" != "4096" ]]; then
    record_failure "page-size-not-4096"
  fi
  luma_exact=false
  if [[ "$luma_query_ok" == "true" ]]; then
    if [[ -z "$observed_luma" || "$observed_luma" == "1" ]]; then
      luma_exact=true
    fi
  fi
  if [[ "$emulator_version" == "$expected_emulator_version" \
      && "$observed_fingerprint" == "$expected_fingerprint" \
      && "$observed_selinux" == "Enforcing" \
      && "$luma_exact" == "true" \
      && "$observed_page_size" == "4096" \
      && "$display_width" -gt 0 \
      && "$display_height" -gt 0 \
      && "${ORKELA_EMULATOR_ARCHIVE_VERIFIED:-false}" == "true" \
      && "${ORKELA_IMAGE_HASHES_VERIFIED:-false}" == "true" ]]; then
    environment_exact=true
  fi

  if timeout --signal=TERM --kill-after=3s 15s \
      adb -s "$device_serial" logcat -b all -d -v threadtime \
      > "$evidence/logs/logcat-pre-soak.txt" 2>&1; then
    pre_soak_log_ok=true
  else
    record_failure "pre-soak-logcat-capture"
  fi
  initial_surfaceflinger_pid="$(
    timeout --signal=TERM --kill-after=3s 10s \
      adb -s "$device_serial" shell pidof surfaceflinger \
      2>/dev/null | tr -d '\r' || true
  )"
  if [[ -z "$initial_surfaceflinger_pid" ]]; then
    record_failure "surfaceflinger-pid-missing-at-soak-start"
  fi
  soak_started="$SECONDS"
  timeout --signal=TERM --kill-after=3s 10s \
    adb -s "$device_serial" exec-out screencap -p \
    > "$evidence/screenshots/soak-1.png" \
    2> "$evidence/logs/screencap-1.txt" \
    || true
  for index in $(seq 1 24); do
    target_elapsed=$((index * 5))
    now_elapsed=$((SECONDS - soak_started))
    if ((now_elapsed < target_elapsed)); then
      sleep $((target_elapsed - now_elapsed))
    fi
    observation="$(
      timeout --signal=TERM --kill-after=3s 8s \
        adb -s "$device_serial" shell '
          echo "PID=$(pidof surfaceflinger)"
          service check package
          service check SurfaceFlinger
          service check mount
          sm list-volumes all
        ' 2>&1 \
        | tr -d '\r' \
        || true
    )"
    surfaceflinger_pid="$(
      sed -n 's/^PID=//p' <<< "$observation" | head -n 1
    )"
    package_ok=0
    surfaceflinger_ok=0
    mount_ok=0
    storage_ok=0
    grep -Fq "Service package: found" <<< "$observation" \
      && package_ok=1
    grep -Fq "Service SurfaceFlinger: found" <<< "$observation" \
      && surfaceflinger_ok=1
    grep -Fq "Service mount: found" <<< "$observation" \
      && mount_ok=1
    if grep -Eq "^private mounted([[:space:]]|$)" <<< "$observation" \
        && grep -Eq "^emulated;0 mounted([[:space:]]|$)" \
          <<< "$observation"; then
      storage_ok=1
    fi
    if [[ -n "$initial_surfaceflinger_pid" \
        && "$surfaceflinger_pid" != "$initial_surfaceflinger_pid" ]]; then
      pid_changes=$((pid_changes + 1))
    fi
    healthy=0
    if [[ -n "$surfaceflinger_pid" \
        && "$package_ok" -eq 1 \
        && "$surfaceflinger_ok" -eq 1 \
        && "$mount_ok" -eq 1 \
        && "$storage_ok" -eq 1 ]]; then
      healthy=1
      healthy_observations=$((healthy_observations + 1))
    fi
    observations=$((observations + 1))
    printf '%s,%d,%d,%d,%s,%d,%d,%d,%d\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      "$index" \
      "$((SECONDS - soak_started))" \
      "$healthy" \
      "${surfaceflinger_pid:-missing}" \
      "$package_ok" \
      "$surfaceflinger_ok" \
      "$mount_ok" \
      "$storage_ok" \
      >> "$observations_file"
    case "$index" in
      7|14|22)
        screenshot_index="$(
          case "$index" in
            7) echo 2 ;;
            14) echo 3 ;;
            22) echo 4 ;;
          esac
        )"
        timeout --signal=TERM --kill-after=3s 10s \
          adb -s "$device_serial" exec-out screencap -p \
          > "$evidence/screenshots/soak-$screenshot_index.png" \
          2> "$evidence/logs/screencap-$screenshot_index.txt" \
          || true
        ;;
    esac
  done

  final_surfaceflinger_pid="$(
    timeout --signal=TERM --kill-after=3s 10s \
      adb -s "$device_serial" shell pidof surfaceflinger \
      2>/dev/null | tr -d '\r' || true
  )"
  if timeout --signal=TERM --kill-after=3s 15s \
      adb -s "$device_serial" logcat -b all -d -v threadtime \
      > "$evidence/logs/logcat-soak.txt" 2>&1; then
    post_soak_log_ok=true
  else
    record_failure "post-soak-logcat-capture"
  fi
  if [[ "$pre_soak_log_ok" == "true" \
      && "$post_soak_log_ok" == "true" ]]; then
    crash_evidence_complete=true
  fi
  crash_signatures="$(
    {
      grep -Eic \
        'GoldfishMapper::readFromHost|hasReadColorBufferDma|RegionSampling|surfaceflinger.*(fatal|crash)|Fatal signal.*surfaceflinger' \
        "$evidence/logs/emulator.log" || true
      grep -Eic \
        'GoldfishMapper::readFromHost|hasReadColorBufferDma|RegionSampling|surfaceflinger.*(fatal|crash)|Fatal signal.*surfaceflinger' \
        "$evidence/logs/logcat-pre-soak.txt" || true
      grep -Eic \
        'GoldfishMapper::readFromHost|hasReadColorBufferDma|RegionSampling|surfaceflinger.*(fatal|crash)|Fatal signal.*surfaceflinger' \
        "$evidence/logs/logcat-soak.txt" || true
    } | awk '{ total += $1 } END { print total + 0 }'
  )"
  if [[ "$crash_evidence_complete" == "true" ]] \
      && grep -Fq \
      "GoldfishMapper::readFromHost" \
      "$evidence/logs/emulator.log" \
      "$evidence/logs/logcat-pre-soak.txt" \
      "$evidence/logs/logcat-soak.txt" \
      && grep -Fq \
        "hasReadColorBufferDma" \
        "$evidence/logs/emulator.log" \
        "$evidence/logs/logcat-pre-soak.txt" \
        "$evidence/logs/logcat-soak.txt"; then
    known_control_crash_reproduced=true
  fi
  if python3 platform/android/ci/validate_probe_pngs.py \
      "$evidence/screenshots/soak-1.png" \
      "$evidence/screenshots/soak-2.png" \
      "$evidence/screenshots/soak-3.png" \
      "$evidence/screenshots/soak-4.png" \
      --expected-width "$display_width" \
      --expected-height "$display_height" \
      --output "$screenshots_json" \
      > "$evidence/logs/png-validation.txt" 2>&1; then
    valid_screenshots=4
  else
    record_failure "screenshot-validation"
  fi
  if [[ "$observations" -ne 24 ]]; then
    record_failure "observation-count:$observations"
  fi
  if [[ "$healthy_observations" -ne 24 ]]; then
    record_failure "unhealthy-observations:$healthy_observations"
  fi
  if [[ -z "$initial_surfaceflinger_pid" \
      || "$final_surfaceflinger_pid" != "$initial_surfaceflinger_pid" \
      || "$pid_changes" -ne 0 ]]; then
    record_failure "surfaceflinger-pid-instability"
  fi
  if [[ "$crash_signatures" -ne 0 ]]; then
    record_failure "surfaceflinger-crash-signatures:$crash_signatures"
  fi
fi

grep -E \
  'Graphics Adapter|GPU mode|Vulkan|GLDirectMem|GlDma|HasSharedSlots|Renderer|renderer' \
  "$evidence/logs/emulator.log" \
  > "$evidence/HOST-GRAPHICS-TUPLE.txt" || true
grep 'setCurrentRenderer:' "$evidence/logs/emulator.log" \
  | sed 's/^[^|]*|[[:space:]]*//' \
  | sort -u \
  > "$evidence/EFFECTIVE-RENDERER-TUPLES.txt" || true
effective_renderer_count="$(
  awk 'NF { count += 1 } END { print count + 0 }' \
    "$evidence/EFFECTIVE-RENDERER-TUPLES.txt"
)"
effective_renderer_line="$(
  paste -sd ';' "$evidence/EFFECTIVE-RENDERER-TUPLES.txt"
)"
if [[ "$effective_renderer_count" -ne 1 ]]; then
  record_failure "effective-renderer-tuple-count:$effective_renderer_count"
fi
# The generic software selector already proved this mixed tuple unstable on
# the same pinned GitHub runner/image pair. A nominally different selector
# that resolves to it is evidence of fallback, not an independent candidate.
if grep -Eq \
    "setCurrentRenderer: (swangle lavapipe|swiftshader swiftshader)" \
    "$evidence/EFFECTIVE-RENDERER-TUPLES.txt"; then
  known_failing_tuple=true
  if [[ "$renderer" == "lavapipe" || "$renderer" == "swangle" ]]; then
    record_failure "effective-renderer-collapsed-to-known-failing-tuple"
  fi
fi

if [[ "$environment_exact" == "true" \
    && "$observations" -eq 24 \
    && "$healthy_observations" -eq 24 \
    && "$pid_changes" -eq 0 \
    && "$crash_signatures" -eq 0 \
    && "$valid_screenshots" -eq 4 \
    && -n "$initial_surfaceflinger_pid" \
    && "$final_surfaceflinger_pid" == "$initial_surfaceflinger_pid" \
    && ! -s "$failure_file" ]]; then
  stable=true
fi
deterministic_candidate=false
if [[ "$renderer" == "lavapipe" || "$renderer" == "swangle" ]]; then
  deterministic_candidate=true
fi
if [[ "$stable" == "true" \
    && "$deterministic_candidate" == "true" \
    && "$known_failing_tuple" == "false" ]]; then
  stage1_candidate=true
fi

RENDERER="$renderer" \
EXPECTED_EMULATOR_VERSION="$expected_emulator_version" \
EMULATOR_VERSION="$emulator_version" \
EXPECTED_FINGERPRINT="$expected_fingerprint" \
OBSERVED_FINGERPRINT="$observed_fingerprint" \
OBSERVED_SELINUX="$observed_selinux" \
OBSERVED_LUMA="$observed_luma" \
OBSERVED_PAGE_SIZE="$observed_page_size" \
BOOT_COMPLETED="$boot_completed" \
ENVIRONMENT_EXACT="$environment_exact" \
STABLE="$stable" \
OBSERVATIONS="$observations" \
HEALTHY_OBSERVATIONS="$healthy_observations" \
PID_CHANGES="$pid_changes" \
INITIAL_SURFACEFLINGER_PID="$initial_surfaceflinger_pid" \
FINAL_SURFACEFLINGER_PID="$final_surfaceflinger_pid" \
CRASH_SIGNATURES="$crash_signatures" \
VALID_SCREENSHOTS="$valid_screenshots" \
EFFECTIVE_RENDERER_LINE="$effective_renderer_line" \
EFFECTIVE_RENDERER_COUNT="$effective_renderer_count" \
KNOWN_FAILING_TUPLE="$known_failing_tuple" \
STAGE1_CANDIDATE="$stage1_candidate" \
KNOWN_CONTROL_CRASH_REPRODUCED="$known_control_crash_reproduced" \
CRASH_EVIDENCE_COMPLETE="$crash_evidence_complete" \
DISPLAY_WIDTH="$display_width" \
DISPLAY_HEIGHT="$display_height" \
FAILURE_FILE="$failure_file" \
python3 - <<'PY' > "$result_json"
import json
import os
from pathlib import Path


def boolean(name: str) -> bool:
    return os.environ[name].lower() == "true"


failure_path = Path(os.environ["FAILURE_FILE"])
failures = [
    line
    for line in failure_path.read_text(encoding="utf-8").splitlines()
    if line
]
print(json.dumps({
    "schema": 1,
    "purpose": "Android 17 renderer isolation probe; no Orkela APK installed",
    "renderer": os.environ["RENDERER"],
    "effective_renderer_line": os.environ["EFFECTIVE_RENDERER_LINE"],
    "effective_renderer_count": int(os.environ["EFFECTIVE_RENDERER_COUNT"]),
    "expected_control_failure": os.environ["RENDERER"] == "swiftshader",
    "known_control_crash_reproduced": boolean(
        "KNOWN_CONTROL_CRASH_REPRODUCED"
    ),
    "crash_evidence_complete": boolean("CRASH_EVIDENCE_COMPLETE"),
    "known_failing_tuple": boolean("KNOWN_FAILING_TUPLE"),
    "stage1_candidate": boolean("STAGE1_CANDIDATE"),
    "stable": boolean("STABLE"),
    "boot_completed": boolean("BOOT_COMPLETED"),
    "environment_exact": boolean("ENVIRONMENT_EXACT"),
    "emulator": {
        "expected": os.environ["EXPECTED_EMULATOR_VERSION"],
        "observed": os.environ["EMULATOR_VERSION"],
    },
    "guest": {
        "expected_fingerprint": os.environ["EXPECTED_FINGERPRINT"],
        "observed_fingerprint": os.environ["OBSERVED_FINGERPRINT"],
        "selinux": os.environ["OBSERVED_SELINUX"],
        "luma_sampling": os.environ["OBSERVED_LUMA"] or "default",
        "page_size": int(os.environ["OBSERVED_PAGE_SIZE"] or 0),
        "display_width": int(os.environ["DISPLAY_WIDTH"]),
        "display_height": int(os.environ["DISPLAY_HEIGHT"]),
    },
    "soak": {
        "requested_seconds": 120,
        "observations": int(os.environ["OBSERVATIONS"]),
        "healthy_observations": int(os.environ["HEALTHY_OBSERVATIONS"]),
        "initial_surfaceflinger_pid": os.environ["INITIAL_SURFACEFLINGER_PID"],
        "final_surfaceflinger_pid": os.environ["FINAL_SURFACEFLINGER_PID"],
        "pid_changes": int(os.environ["PID_CHANGES"]),
        "crash_signatures": int(os.environ["CRASH_SIGNATURES"]),
        "valid_screenshots": int(os.environ["VALID_SCREENSHOTS"]),
    },
    "failures": failures,
}, indent=2, sort_keys=True))
PY

cat "$result_json"

# Probe jobs remain green so one expected renderer failure cannot cancel the
# other matrix cells. Promotion is a separate evidence decision.
exit 0
