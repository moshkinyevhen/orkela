# Orkela Android 17 Boundary Gate

Date: **2026-07-28**

Status: **LOCAL PASS; GITHUB BOUNDARY MATRIX PENDING**

This report records a local physical-device gate for the Android application.
It is not a release record because the tested Orkela and local Resonith working
trees are not yet immutable Git commits and the API-26/API-37 GitHub workflow
has not run.

## Build identity

- Orkela base source revision:
  `b93a995bc7818aff407a329792ec2928a47233c4`, with local uncommitted changes;
- local Resonith base source revision:
  `86e1f131100ad3b44e55083c3c5c15463bc89a55`, with local uncommitted changes;
- application version: `0.3.0-alpha.4` / version code `30004`;
- Android Gradle Plugin: `9.2.1`;
- Gradle wrapper: `9.4.1`;
- compile SDK: `37`;
- target SDK: `37`;
- minimum SDK: `26`;
- Build-Tools: `37.0.0`;
- NDK: `29.0.14206865`;
- packaged ABIs: `arm64-v8a`, `x86_64`;
- every native `LOAD` segment alignment: `0x4000` / 16 KiB;
- Build-Tools 37 `zipalign -c -P 16 -v 4`: **PASS**;
- `app-debug.apk` SHA-256:
  `64f16768772aae99c311484cb7dd69d1d49c1465c5a83a106d413525b8776400`;
- `app-debug-androidTest.apk` SHA-256:
  `3a4a7c05fd0b71a95dc2ff70e20741808d196011ec972999fe1f5b929a5132e9`.

## Physical Android 17 gate

- device class: Pixel 7 Pro;
- architecture: `arm64-v8a`;
- Android release: `17`;
- API level: `37`;
- build ID: `CP41.260701.005`;
- security patch: `2026-07-05`;
- memory page size: `4096` bytes;
- application install: **PASS**;
- instrumentation APK install: **PASS**;
- application launch: **PASS**; the latest locked-device Activity Manager gate
  completed in 3028 ms and reported an unknown launch state;
- native Resonith decode: **PASS**;
- decoded sample rate: `44100`;
- decoded channels: `2`;
- decoded frames: `352800`;
- PCM16 SHA-256:
  `3cfcae4996a08976f42ec83744ea0130935ca53d83b37129c001581697618618`;
- retained application files: only `files/orkela-ci-smoke.json`;
- retained WAV/PCM/raw intermediary: **none**.

The device was locked during the UI inspection, so this gate does not claim
audibility or physical Play-control interaction. It proves installation,
application startup, exact native decoder execution, and deterministic PCM
reconstruction on a real Android 17 device.

## Release-blocking follow-up

The checked-in `Mobile Applications` workflow builds one exact target-37 APK
pair and runs it sequentially on Android 8 / API 26 and Android 17 / API 37
with 4 KiB pages, then Android 17 / API 37 with 16 KiB pages. Every x86-64
runtime must reproduce the same PCM16 SHA-256 before the Android product
artifact can be published. The GitHub result and immutable artifact identities
must be appended in a later report; this local pass cannot substitute for that
boundary matrix.
