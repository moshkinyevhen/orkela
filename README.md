# Orkela

Orkela is a native media player for the SceneLith ecosystem. It plays real
**Resonith** audio on Windows, Android, iOS, macOS, Ubuntu, Debian, and
FreeBSD by calling the public Resonith Core decoder and sending reconstructed
PCM directly to the platform audio path.

Current candidate version: **0.3.0-alpha.6**.

`.resonith file -> Resonith Core -> PCM16 -> Windows audio`

There is no WAV conversion in this path.

## Name

**Orkela** is pronounced `or-ke-la`. The name combines orchestration with the
musical syllable *la*: the player will ultimately orchestrate independent
Resonith audio, SceneLith video, subtitles, and the optional AV bridge.

The product name and international pronunciation are accepted project
decisions pending formal trademark clearance.

## Canonical media names

- `.resonith` — standalone Resonith audio;
- `.scenelith` — standalone SceneLith visual bitstream;
- `.orka` — synchronized package binding independent audio and visual streams
  through the separate SceneLith AV Bridge.

Research `.lps4` and `.lps5` inputs remain readable during development but are
not stable user-facing extensions. Orkela recognizes `.scenelith` now and will
decode it when a conforming SceneLith Core exists; the player never simulates
an unavailable decoder.

## Current milestone

- shared strict C++23 session/core with native platform shells;
- shared nine-language interface catalog with automatic system-locale
  selection and a persistent manual override inside Settings;
- shared fixed-memory Field, Spectrum, Wave, and multiresolution History
  analyzer with native rendering on each platform;
- DPI-aware Direct2D/DirectWrite interface with a PCM-derived spectrum;
- open, play/pause, stop, seek, skip, volume, keyboard controls, and
  file drag-and-drop;
- direct LPS4/LPS5 preflight and decoding through Resonith Core;
- direct bounded `MFT1` execution through Resonith Core, including immutable
  Basis placement, circular alignment, and reverse instances;
- direct composite `RSC1` MAF Truth playback (`MFT1` prediction plus `MRI1`
  innovation) with saturating deterministic reconstruction;
- pinned bounded MAF DSP Core revision `9f7650b`, including deterministic
  periodic, source-filter, stochastic, transient, Innovation, and mix
  operations beneath the existing admitted transport;
- sub-second reference-system load and first-audio latency for the complete
  400.773-second Mozart anchors;
- bounded four-buffer Windows playback fed directly by the Resonith pull
  decoder instead of a complete predecoded PCM allocation;
- mono and stereo PCM16 output through the Windows multimedia device;
- no runtime network access and no external codec process.

The Android application has a compatibility floor of Android 8 / API 26 and
compiles and targets Android 17 / API 37. Release CI installs the same exact
APK on API 26 and API 37 with 4 KiB pages and on API 37 with 16 KiB pages. Each
runtime must reproduce the pinned PCM16 SHA-256 without a WAV intermediary.
The Android APK and iOS
application bundle share the same
allocation-bounded Resonith pull session. Android streams packet PCM through
JNI to `AudioTrack`; iOS performs background decode and schedules PCM through
`AVAudioEngine`. See
[Platform Architecture](docs/PLATFORM_ARCHITECTURE.md) for the exact
responsibility split and mandatory build matrix.
The first package and Android-emulator evidence is recorded in the
[Mobile Player Gate](docs/results/MOBILE_PLAYER_GATE_2026-07-27.md).
The bounded MAF Core update, complete speech/piano/Mozart pull-session results,
and same-revision Windows/mobile CI are recorded in the
[0.3.0-alpha.2 Player Gate](docs/results/BOUNDED_MAF_PLAYER_2026-07-27.md).
The direct typed-MAF playback addition is recorded in the
[0.3.0-alpha.3 MFT1 Gate](docs/results/MFT1_PLAYER_GATE_2026-07-27.md).
Composite playback and the long-track startup fix are recorded in the
[0.3.0-alpha.4 Streaming Gate](docs/results/RSC1_STREAMING_PLAYER_GATE_2026-07-27.md).
The first physical-device compile/target API-37 result is recorded in the
[Android 17 Boundary Gate](docs/results/ANDROID_17_BOUNDARY_GATE_2026-07-28.md);
the repeatable API-26/API-37 GitHub boundary matrix remains release-blocking.
The premium Android surface, direct external-stream launch, four live PCM
views, physical-device transport checks, and exact final-APK fingerprint are
recorded in the
[Android Premium Visual Gate](docs/results/ANDROID_PREMIUM_VISUALS_ALPHA5_2026-07-28.md).

The accepted interface-language behavior is defined in the
[Interface Localization Contract](docs/INTERFACE_LOCALIZATION.md). The
supported languages are English, German, Spanish, Italian, Japanese, Korean,
Simplified Chinese, Russian, and Ukrainian. Language follows the operating
system by default; the only manual selector is under
**Settings → Interface → Language**.

This milestone authenticates a complete stream before playback but synthesizes
PCM into a bounded platform queue only as time advances. Playlists, the media
library, and SceneLith video remain subsequent milestones.

## Release evidence

Every playback or interface release is tested with the pinned short
LibriSpeech and full-length Mozart `.resonith` files. The gate covers
responsive background validation/decode, actual playback, play/pause/stop,
seeking, timeline and spectrum motion, volume, malformed-input rejection, file
associations, high DPI, and constrained monitor work areas.

Each published improvement updates [`CHANGELOG.md`](CHANGELOG.md) and
[`VERSION`](VERSION). The local package and GitHub release must identify the
same semantic version, source commit, filenames, and SHA-256 hashes. See
[Release Evidence Protocol](docs/RELEASE_EVIDENCE.md).

Portable archives and installable products are intentionally distinct.
The cross-platform installer, store, and signed update contract is documented
in [Update and Packaging](docs/UPDATE_AND_PACKAGING.md).

The release-blocking next product milestone is the
[Premium Command Center](docs/PRODUCT_ROADMAP.md): icon-led navigation,
high-quality motion and focus states, working quick controls, searchable deep
settings, and explicit capability status instead of non-functional controls.
The evolving setting-surface comparison is recorded in
[Settings Coverage](docs/SETTINGS_COVERAGE.md).

## Build

Requirements:

- Windows 10 or later;
- Visual Studio 2022 with the Desktop C++ workload;
- CMake 3.24 or later.

```powershell
cmake -S . -B build -A x64
cmake --build build --config Release
```

Android uses its pinned Gradle wrapper:

```powershell
cd platform/android
.\gradlew.bat :app:assembleDebug
```

The build requires Android SDK Platform 37 and Build-Tools 37.0.0. NDK r29
provides the native 16 KiB page-size baseline. The APK still runs from API 26
upward; raising the compile/target level does not raise the minimum supported
runtime.

For a local unpublished Resonith integration checkout, set
`ORKELA_RESONITH_SOURCE_DIR` before invoking Gradle. Public and CI builds omit
that variable and use the immutable Resonith revision pinned by CMake.

The local APK is
`platform/android/app/build/outputs/apk/debug/app-debug.apk`. iOS device and
simulator bundles are built by the checked-in CMake presets on macOS/Xcode:

```bash
cmake --preset ios-simulator-x86_64
cmake --build --preset ios-simulator-x86_64
```

macOS uses the matching native AppKit presets:

```bash
cmake --preset macos-arm64
cmake --build --preset macos-arm64
```

Ubuntu, Debian, and FreeBSD use GTK4 for the shell and GStreamer for direct
PCM output:

```bash
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build
```

The executable is `build/Release/Orkela.exe`. To register the three canonical
extensions for the current Windows user without administrator access:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\tools\Register-Orkela.ps1 `
  -ExePath .\build\Release\Orkela.exe
```

Open `samples/emotional-piano.resonith` and press **Play** for a native
end-to-end demonstration. The sample contains the real LPS5 research
transport under the canonical public extension; it is not PCM with a renamed
extension. Its provenance and hashes are recorded beside the file.

To build against a local Resonith checkout:

```powershell
cmake -S . -B build -A x64 `
  -DRESONITH_SOURCE_DIR=C:/src/resonith
cmake --build build --config Release
```

## Safety boundary

The application treats every media file as untrusted. Resonith Core preflights
the complete LPS transport before Orkela allocates the final PCM buffer or opens
an audio device. The current research build also rejects files above 512 MiB
and output longer than two hours.

## Project status

Orkela is experimental research software. Bitstream and player interfaces may
change before the first stable release. No patent, trademark, or legal
clearance is implied by publication.
