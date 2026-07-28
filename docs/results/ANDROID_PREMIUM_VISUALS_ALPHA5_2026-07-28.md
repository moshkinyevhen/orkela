# Orkela Android Premium Visual Gate

Date: **2026-07-28**

Version: **0.3.0-alpha.5** / version code **30005**

Status: **LOCAL PHYSICAL-DEVICE PASS; RELEASE MATRIX PENDING**

This report covers the exact local Android candidate installed on a physical
Pixel 7 Pro. It proves native Resonith reconstruction, external-stream launch,
transport behavior, and responsive live PCM presentation. It is not a public
release record until the immutable GitHub API-26/API-37 matrix and the other
required platform gates pass.

## Exact artifacts

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `orkela-0.3.0-alpha.5-android-debug.apk` | 3,802,857 | `ea5d0f800876ac5198a4486267aabb74ce6505f387a00bd3f9d7b1d600c179c7` |
| `orkela-0.3.0-alpha.5-androidTest-debug.apk` | 40,276 | `3a4a7c05fd0b71a95dc2ff70e20741808d196011ec972999fe1f5b929a5132e9` |

Local artifact directory:
`artifacts/releases/0.3.0-alpha.5`.

## Device

- model: Pixel 7 Pro;
- architecture: ARM64;
- Android: 17 / API 37;
- build: `CP41.260701.005`;
- security patch: `2026-07-05`;
- memory page size: 4 KiB.

## Decoder conformance

The instrumentation APK invoked the exact JNI and Resonith Core packaged in
the application APK.

- status: **PASS**;
- sample rate: 44,100 Hz;
- channels: 2;
- frames: 352,800;
- PCM16 SHA-256:
  `3cfcae4996a08976f42ec83744ea0130935ca53d83b37129c001581697618618`;
- WAV/raw/decoded-PCM filesystem intermediary: **none**.

## Long external-stream gate

Input:
`mozart-original-selected.resonith`

- full bytes: 1,883,620;
- SHA-256:
  `f6646d85309cb15f83fd10f110c4b707821bc18d82296db5397c3bf5f737ae9c`;
- duration: 120 seconds;
- sample rate: 48,000 Hz;
- channels: 2;
- frames: 5,760,000;
- launch mechanism: Android `VIEW` content URI;
- cold Activity launch: 268 ms;
- first queued native PCM observed by the host gate: 750 ms after the
  automated Play command began;
- play/pause: **PASS**;
- seek while paused to 1:32: **PASS**;
- resume after seek: **PASS**;
- ten-second transport: **PASS**;
- pitch-preserving 1.25x speed: **PASS**;
- external `.resonith` title and metadata: **PASS**.

The host-observed 750 ms includes ADB command latency and 80 ms polling
granularity; it is an upper-bound integration measurement, not an audio-device
callback timestamp.

## Visual and frame gate

All plots consume the PCM packet passed to `AudioTrack`; no second decode or
WAV visualization source exists.

- causal field: **PASS**;
- adaptive normalized spectrum: **PASS**;
- live waveform: **PASS**;
- accumulating multiresolution spectral History: **PASS**;
- History compacts old columns and retains the complete observed interval:
  **PASS**;
- timeline signal and cursor motion: **PASS**;
- final History run total rendered frames: 424;
- janky frames: 2 / **0.47%**;
- 50th percentile: 8 ms;
- 90th percentile: 11 ms;
- 95th percentile: 11 ms;
- 99th percentile: 13 ms.

The PCM analyzer uses a cached Hann window and bounded Goertzel bank. It no
longer performs per-sample trigonometric evaluation during playback.

## Malformed input

A WAV payload deliberately presented with a `.resonith` filename produced:

`Playback failed: Resonith preflight: bad magic`

The timeline remained at 0:00 and no new playback stream was created:
**PASS**.

## Remaining release blockers

- API 26 / API 37 / API 37-16K exact-APK GitHub runtime matrix;
- signed release package and update channel;
- matching Windows, Apple, Linux, and FreeBSD feature/build gates;
- immutable source commit and public release artifact hashes.
