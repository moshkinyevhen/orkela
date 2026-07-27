# Orkela Changelog

All notable released changes are recorded here. Every playback or interface
release links to reproducible QA evidence and identifies the exact executable.

## [Unreleased]

Candidate version: **0.3.0-alpha.2**. Publication remains blocked until the
complete platform and O-2 release-evidence gates pass.

### Added

- Strict C++23 `Orkela::Session` with bounded Resonith preflight and an
  allocation-free successful packet-pull path.
- Native Android application project for ARM64 and x86-64 with direct
  Resonith JNI decode and streaming PCM16 `AudioTrack` output.
- Native iOS device and simulator application project with background
  Resonith decode and `AVAudioEngine` output.
- Mandatory same-revision Windows, Android, iOS device, and iOS simulator
  build contract.
- Pinned Gradle 9.4.1 wrapper, Android Gradle Plugin 9.2.1, SDK 36, NDK r29,
  and macOS/Xcode CI gates.
- Resonith Core revision `d8245c207ada6cd7a1f72ad595e7edbd933d2da4`,
  including the bounded integer MAF DSP substrate and its cross-platform
  conformance fixes.
- A portable pull-session executable gate that decodes complete streams,
  verifies timeline/resource bounds, fingerprints PCM, and rejects a
  deterministic truncation before playback.

### Changed

- Windows file loading is now a narrow adapter over the same portable
  decoder/session implementation used by mobile builds.
- The implementation language baseline is C++23 on every native target.
- The player now identifies the active path as bounded MAF Truth playback.
  Optional Gemini Foundry analysis remains encoder-side and adds no player
  network or credential dependency.
- Published reproducible `0.3.0-alpha.2` Core/build/mobile evidence and
  complete speech, piano, and 400.773-second Mozart pull-session results.

### Planned

- Complete the release-blocking Premium Command Center goal: global setting
  search, keyboard-only navigation, full category coverage, premium motion and
  focus states, persisted working controls, and explicit status labels for
  capabilities that do not yet have a backend.
- Bounded producer/ring-buffer playback on every platform, playlists, and
  library adapters.

## [0.2.0-alpha.2] - 2026-07-26

### Added

- Responsive background Resonith validation and decode for long-form media.
- Mandatory short/long playback, malformed-input, high-DPI, association, and
  visual release-evidence gate.
- Versioned local package and GitHub publication contract.
- Embedded Windows file/product version and versioned CI release build.
- Premium icon-led Command Center foundation with persistent working playback,
  audio, visual, interface, and trust preferences.
- Instant cross-category setting search, twelve-area capability navigation,
  and keyboard-only focus and activation.

### Fixed

- Long `.resonith` files no longer block the Windows message loop while the
  native decoder prepares playback PCM.
- Skip glyphs now point in their actual transport direction.

### Compatibility

- Direct prospective LPS4/LPS5 playback through Resonith Core.
- `.resonith`, `.scenelith`, and `.orka` remain the canonical public file
  associations.

## [0.2.0-alpha.1] - 2026-07-26

### Added

- Modern DPI-aware Direct2D/DirectWrite playback surface.
- PCM-derived spectrum, waveform, timeline, seeking, skip, volume, drag and
  drop, keyboard controls, and current-user file registration.
- Direct Resonith Core decode to the Windows audio device without a WAV
  intermediary.

[Unreleased]: https://github.com/moshkinyevhen/orkela/compare/v0.2.0-alpha.2...HEAD
[0.2.0-alpha.2]: https://github.com/moshkinyevhen/orkela/releases/tag/v0.2.0-alpha.2
[0.2.0-alpha.1]: https://github.com/moshkinyevhen/orkela/releases/tag/v0.2.0-alpha.1
