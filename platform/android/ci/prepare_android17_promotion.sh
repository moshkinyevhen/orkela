#!/usr/bin/env bash

# Prepare the exact Android 17 promotion environment once. Runtime attempts are
# read-only consumers: they must never call sdkmanager or select another
# Emulator binary after these byte-level checks pass.

set -euo pipefail

revision="37.2.1"
build_id="15875889"
binary_version="37.2.1.0"
archive_sha1="1c39ceb4bca042b973344d252a051189d367ab83"
archive_sha256="3fb1f765795b284f864b9b3403d1c5e1ad0f317eb6522441460001ff660d3d7d"
archive_size="346539649"
archive_url="https://dl.google.com/android/repository/emulator-linux_x64-${build_id}.zip"
archive="$RUNNER_TEMP/emulator-linux_x64-${build_id}.zip"
pinned="$RUNNER_TEMP/android-emulator-${revision}-${build_id}"
manifest_root="$GITHUB_WORKSPACE/platform/android/ci/manifests"
manifest_4k="$manifest_root/android17-r06-google-apis-x86_64-4k.sha256"
manifest_16k="$manifest_root/android17-r06-google-apis-x86_64-16k.sha256"
contract="$GITHUB_WORKSPACE/platform/android/ci/android17_promotion_contract.json"
image_4k="$ANDROID_HOME/system-images/android-37.0/google_apis/x86_64"
image_16k="$ANDROID_HOME/system-images/android-37.0/google_apis_ps16k/x86_64"

test -s "$manifest_4k"
test -s "$manifest_16k"
test -s "$contract"
test "$(
  sha256sum "$manifest_4k" | cut -d' ' -f1
)" = "$(
  jq -er '.profiles["37"].system_image_manifest_sha256' "$contract"
)"
test "$(
  sha256sum "$manifest_16k" | cut -d' ' -f1
)" = "$(
  jq -er '.profiles["37-16k"].system_image_manifest_sha256' "$contract"
)"

timeout --signal=TERM --kill-after=15s 600s \
  sudo apt-get update
timeout --signal=TERM --kill-after=15s 600s \
  sudo apt-get install -y --no-install-recommends \
  'libpulse0=1:16.1+dfsg1-2ubuntu10.1'
test "$(
  dpkg-query -W -f='${Version}' libpulse0
)" = "1:16.1+dfsg1-2ubuntu10.1"

timeout --signal=TERM --kill-after=15s 1800s \
  "$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" \
  "platform-tools" \
  "system-images;android-37.0;google_apis;x86_64" \
  "system-images;android-37.0;google_apis_ps16k;x86_64"

verify_image() {
  local image_dir="$1"
  local manifest="$2"
  local label="$3"
  local verified_manifest="$RUNNER_TEMP/${label}-verified.sha256"

  test -d "$image_dir"
  python3 \
    "$GITHUB_WORKSPACE/platform/android/ci/verify_system_image_manifest.py" \
    "$image_dir" \
    "$manifest" \
    --output "$verified_manifest"
  cmp "$manifest" "$verified_manifest"
}

verify_image "$image_4k" "$manifest_4k" android17-4k
verify_image "$image_16k" "$manifest_16k" android17-16k

curl --fail --location --retry 3 \
  --connect-timeout 30 \
  --max-time 900 \
  --output "$archive" \
  "$archive_url"
test "$(stat -c '%s' "$archive")" = "$archive_size"
printf '%s  %s\n' "$archive_sha1" "$archive" | sha1sum -c -
printf '%s  %s\n' "$archive_sha256" "$archive" | sha256sum -c -

mkdir -p "$pinned"
timeout --signal=TERM --kill-after=15s 300s \
  unzip -q "$archive" -d "$pinned"
emulator_bin="$pinned/emulator/emulator"
source_properties="$pinned/emulator/source.properties"
test -x "$emulator_bin"
test -s "$source_properties"
grep -Fxq "Pkg.Revision=$revision" "$source_properties"
grep -Fxq "Pkg.BuildId=$build_id" "$source_properties"

emulator_version_output="$(
  timeout --signal=TERM --kill-after=5s 20s \
    "$emulator_bin" -version 2>&1 \
    || true
)"
parsed_emulator_version="$(
  printf '%s\n' "$emulator_version_output" \
    | sed -n 's/^.*Android emulator version \([^ ]*\).*/\1/p' \
    | head -n 1
)"
test "$parsed_emulator_version" = "$binary_version"

{
  echo "ORKELA_EMULATOR_BIN=$emulator_bin"
  echo "ORKELA_EXPECTED_EMULATOR_VERSION=$binary_version"
  echo "ORKELA_EMULATOR_REVISION=$revision"
  echo "ORKELA_EMULATOR_BUILD_ID=$build_id"
  echo "ORKELA_EMULATOR_ARCHIVE_URL=$archive_url"
  echo "ORKELA_EMULATOR_ARCHIVE_SHA1=$archive_sha1"
  echo "ORKELA_EMULATOR_ARCHIVE_SHA256=$archive_sha256"
  echo "ORKELA_EMULATOR_ARCHIVE_SIZE=$archive_size"
  echo "ORKELA_EMULATOR_ARCHIVE_VERIFIED=true"
  echo "ORKELA_ANDROID17_4K_IMAGE_MANIFEST=$manifest_4k"
  echo "ORKELA_ANDROID17_4K_IMAGE_VERIFIED=true"
  echo "ORKELA_ANDROID17_16K_IMAGE_MANIFEST=$manifest_16k"
  echo "ORKELA_ANDROID17_16K_IMAGE_VERIFIED=true"
} >> "$GITHUB_ENV"

sudo chown "$(id -un)" /dev/kvm
