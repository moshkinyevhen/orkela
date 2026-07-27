# Orkela Mobile Player Gate

Date: **2026-07-27**
Status: **PASSED FOR BUILD; ANDROID RUNTIME PASSED; IOS RUNTIME PENDING DEVICE**

## Scope

This gate distinguishes three claims that must not be conflated:

1. the portable decoder/session compiles for a target;
2. a platform-native installable application package is produced;
3. the application launches and plays direct Resonith PCM through the
   platform audio backend.

## Same-revision package gate

GitHub Actions run
[`30239069067`](https://github.com/moshkinyevhen/orkela/actions/runs/30239069067)
passed from commit `868ed1d8073f6d6d5ab1393ffc12a17e4d39a0f0`. It used
Xcode 26.4.1 for Apple targets and
produced all three mobile package classes:

| Artifact | Architecture | GitHub archive SHA-256 |
|---|---|---|
| Orkela Android debug APK | ARM64 + x86-64 | `d0badddd1a0bd14bae857f60dcae389531acdd088cfd6a252081efe45e1a9cc3` |
| Orkela iOS device app | ARM64 | `ba3afb97c511b947278d37e9c3a52bc674426e93a4ae553e1b43fb6a479bbd30` |
| Orkela iOS simulator app | x86-64 | `b88ba3578d3f9c625d092fa84b46e51c9ffd0a6bcb920e20c100e4b573202cad` |

The hashes above identify GitHub artifact ZIPs. The workflow separately
checks each application binary's requested architecture, the bundled signed
demonstration stream, and non-empty package contents. The Windows workflow
also passed from the same source line.

The strict local Windows C++23/Clang 22 regression build produced
`Orkela.exe` at 2,678,272 bytes with SHA-256
`8bfc0aa59ae687c2c41a511700b4fc2d2f4c18f670f91b492e01c7a0ec754ff7`.

## Local Android package

The post-drain-fix APK was built with AGP 9.2.1, Gradle 9.4.1, SDK 36,
NDK r29, CMake 4.1.2, Clang 21, and Temurin JDK 25 LTS.

| Property | Result |
|---|---|
| Path | `platform/android/app/build/outputs/apk/debug/app-debug.apk` |
| Complete bytes | 4,181,554 |
| SHA-256 | `6bbd5aefe6fc85642af9faeb312e4231461e1585627089d84e9348dc9a277d95` |
| Package | `org.scenelith.orkela` |
| Minimum / target API | 26 / 36 |
| Native ABIs | `arm64-v8a`, `x86_64` |
| Bundled input | `emotional-piano.resonith`, 117,643 bytes |

Debug signing makes local APK bytes environment-specific; release evidence
will use a reproducible release-signing process.

## Android runtime result

Android Emulator 36.6.11 with the Google APIs Android 16/API 36 x86-64 image
was installed locally. The AVD is intentionally stored on the project drive
because the system drive cannot safely host a multi-gigabyte data partition.

The following runtime checks passed:

- cold installation and launch of `MainActivity`;
- bundled `.resonith` loaded with no external transcoder or WAV file;
- native JNI library loaded;
- Resonith preflight and packet pull reported 44,100 Hz stereo;
- streaming `AudioTrack` playback reached completion;
- the application process remained alive;
- AndroidRuntime, libc, and native-debug fatal logs remained empty.

Runtime inspection exposed and fixed a real queue-lifetime defect: successful
`AudioTrack.write` only means PCM entered the device queue. Orkela now keeps
the device alive until the playback head reaches the final submitted frame
before reporting completion and releasing the track.

## Honest iOS boundary

Device and simulator `.app` bundles compile and link against UIKit,
AVFAudio/AVAudioEngine, UniformTypeIdentifiers, and QuartzCore. No Apple
simulator or device is available on the Windows host, so launch, document
picker, audio-session interruption, backgrounding, headphones, and real
device playback remain explicit iOS runtime gates. A successful Xcode package
is not reported as proof of audible iOS playback.
