#!/usr/bin/env bash

# Install and verify one exact Android Emulator host package and the shared
# Android 17 guest payload used by renderer-isolation probes.

set -euo pipefail

revision="${1:?usage: prepare_emulator_probe.sh <revision> <build-id> <sha1> <sha256> <size> <binary-version>}"
build_id="${2:?missing build ID}"
archive_sha1="${3:?missing archive SHA-1}"
archive_sha256="${4:?missing archive SHA-256}"
archive_size="${5:?missing archive size}"
expected_binary_version="${6:?missing binary version}"

case "$revision:$build_id:$archive_sha1:$archive_sha256:$archive_size:$expected_binary_version" in
  *[!A-Za-z0-9._:-]*)
    echo "Unsafe Emulator probe metadata" >&2
    exit 2
    ;;
esac

guest_hash_set="android17-r06-google-apis-x86_64-4k-v1"
archive_url="https://dl.google.com/android/repository/emulator-linux_x64-${build_id}.zip"
archive="$RUNNER_TEMP/emulator-linux_x64-${build_id}.zip"
pinned="$RUNNER_TEMP/android-emulator-${revision}-${build_id}"

sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  'libpulse0=1:16.1+dfsg1-2ubuntu10.1'
test "$(
  dpkg-query -W -f='${Version}' libpulse0
)" = "1:16.1+dfsg1-2ubuntu10.1"

"$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" \
  "platform-tools" \
  "system-images;android-37.0;google_apis;x86_64"
image="$ANDROID_HOME/system-images/android-37.0/google_apis/x86_64"
test -d "$image"
(
  cd "$image"
  printf '%s  %s\n' \
    4b8a752539c967c3959af6768c1e118a0e41b36b53dcf03a122a011725c14896 kernel-ranchu \
    1a3822e981bd07308b48882d205e91e893eff40a27e566a84b597180f2ad426b ramdisk.img \
    ca98470938276fbdf5501dfda3c276a5b43e32514900f2ceeec808bdc7711d17 system.img \
    fb76b3cb619100e5d63f5147be982bb31afeb9beb726e82ce9239d295487ad9b vendor.img \
    bf15b0b43bd0155b258b3756cf523dd917735042633edbb645b34c285a45832d source.properties \
    7e0d7d2acf0ded1bc4b445356d93fd6759c99956620c4141cd63f7363c326149 advancedFeatures.ini \
    9a7e1122391cf8e23674d8c293b81faa3be4163886c976a478864be062ffe5ba build.prop \
    | sha256sum -c -
)

curl --fail --location --retry 3 \
  --output "$archive" \
  "$archive_url"
test "$(stat -c '%s' "$archive")" = "$archive_size"
printf '%s  %s\n' "$archive_sha1" "$archive" | sha1sum -c -
printf '%s  %s\n' "$archive_sha256" "$archive" | sha256sum -c -

mkdir -p "$pinned"
unzip -q "$archive" -d "$pinned"
emulator_bin="$pinned/emulator/emulator"
source_properties="$pinned/emulator/source.properties"
test -x "$emulator_bin"
test -s "$source_properties"
grep -Fxq "Pkg.Revision=$revision" "$source_properties"
grep -Fxq "Pkg.BuildId=$build_id" "$source_properties"

emulator_version_output="$("$emulator_bin" -version 2>&1 || true)"
printf '%s\n' "$emulator_version_output"
parsed_emulator_version="$(
  printf '%s\n' "$emulator_version_output" \
    | sed -n 's/^.*Android emulator version \([^ ]*\).*/\1/p' \
    | head -n 1
)"
printf 'Parsed Emulator version: %s\n' "$parsed_emulator_version"
test "$parsed_emulator_version" = "$expected_binary_version"

{
  echo "ORKELA_EMULATOR_BIN=$emulator_bin"
  echo "ORKELA_EXPECTED_EMULATOR_VERSION=$expected_binary_version"
  echo "ORKELA_EMULATOR_REVISION=$revision"
  echo "ORKELA_EMULATOR_BUILD_ID=$build_id"
  echo "ORKELA_EMULATOR_ARCHIVE_URL=$archive_url"
  echo "ORKELA_EMULATOR_ARCHIVE_SHA1=$archive_sha1"
  echo "ORKELA_EMULATOR_ARCHIVE_SHA256=$archive_sha256"
  echo "ORKELA_EMULATOR_ARCHIVE_SIZE=$archive_size"
  echo "ORKELA_EMULATOR_ARCHIVE_VERIFIED=true"
  echo "ORKELA_EXPECTED_GUEST_HASH_SET=$guest_hash_set"
  echo "ORKELA_GUEST_HASH_SET=$guest_hash_set"
  echo "ORKELA_IMAGE_HASHES_VERIFIED=true"
} >> "$GITHUB_ENV"

sudo chown "$(id -un)" /dev/kvm
