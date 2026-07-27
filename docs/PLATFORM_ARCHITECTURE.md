# Orkela Platform Architecture

Status: **ACCEPTED**

## One player, three native products

Orkela is not three independent ports. The product is split at the narrowest
stable boundary:

1. Resonith Core owns normative bitstream validation and reconstruction.
2. `Orkela::Session` owns untrusted-input ceilings, decoder workspace
   lifetime, pull scheduling, and platform-neutral PCM metadata.
3. A platform adapter owns file selection, application lifecycle, UI,
   background work, and the operating-system audio API.

The shared layers are strict C++23. Platform UI and lifecycle code use the
native language and API of each operating system where that reduces binary
size and improves accessibility or power behavior.

| Platform | UI/lifecycle | Audio output | Required artifact |
|---|---|---|---|
| Windows x64 | C++23 + Win32/Direct2D | Windows multimedia; WASAPI planned | `Orkela.exe` |
| Android ARM64/x86-64 | Java 17 shell + C++23 JNI | streaming `AudioTrack` | APK/AAB |
| iOS ARM64/x86-64 simulator | Objective-C++23 + UIKit | `AVAudioEngine` | unsigned CI `.app`; signed archive at release |

## Portable C++23 subset

The portable layer may use deterministic value types, RAII, `std::span`,
`std::vector`, `std::unique_ptr`, fixed-width integers, and exceptions during
session construction. It must not depend on:

- a filesystem path encoding;
- a window system or platform event loop;
- a platform audio handle;
- JIT compilation, runtime code download, or Python;
- implementation-defined binary serialization;
- allocation, logging, locks, or file I/O in an audio callback.

The successful `read_next` path performs no allocation. Mobile adapters decode
on a dedicated producer thread; the audio backend consumes PCM and never owns
normative codec state.

## Current mobile milestone

The Android alpha is a real APK. It opens `.resonith`, preflights through
Resonith Core, pulls decoded packets through JNI, and writes PCM16 to a
streaming `AudioTrack`. It also includes the signed demonstration stream.

The iOS alpha is a real UIKit application bundle. It opens `.resonith`,
decodes on a background queue through the same portable session, and schedules
PCM through `AVAudioEngine`. The first iOS milestone uses a complete bounded
PCM buffer; replacing it with the same producer/ring-buffer model as Android
is an explicit optimization gate, not a bitstream change.

Both mobile alphas cap compressed input at 64 MiB. Resonith Core still applies
its stricter authenticated resource requirements. Network access and external
transcoders are absent.

## Mandatory release matrix

Beginning with the 0.3 mobile line, every promoted Orkela playback revision
must build from one commit as:

- Windows x64;
- Android ARM64 and x86-64 in one package;
- iOS device ARM64;
- iOS simulator x86-64.

A successful library compile is not a player result. The release report must
separately record package creation, native architecture, direct Resonith
decode, malformed-input rejection, lifecycle behavior, actual audio-device
playback, and UI evidence. iOS compilation is performed on a real macOS/Xcode
runner; Windows cannot substitute for the Apple SDK or signing service.

## Pinned toolchain

| Component | Version |
|---|---:|
| C++ language | C++23 |
| Android Gradle Plugin | 9.2.1 |
| Gradle | 9.4.1 |
| Android compile/target SDK | 36 |
| Android minimum API | 26 |
| Android NDK | r29 (`29.0.14206865`) |
| Android Clang | 21 |
| Android CMake | 4.1.2 |
| Java source level | 17 |
| Build JDK | Temurin 25 LTS |
| iOS deployment target | 15.0 |
| CI Xcode | 26.4.1 |

The Gradle wrapper pins the binary distribution and its SHA-256. Resonith is
pinned by full Git commit rather than a mutable branch or abbreviated hash.
