# Orkela Changelog

All notable released changes are recorded here. Every playback or interface
release links to reproducible QA evidence and identifies the exact executable.

## [Unreleased]

Candidate version: **0.3.0-alpha.6**. Publication remains blocked until the
complete platform and O-2 release-evidence gates pass.

Local public-pin evidence:
[`Alpha.6 Local Release Gate`](docs/results/ALPHA6_LOCAL_RELEASE_GATE_2026-07-28.md).

### Added

- Strict C++23 `Orkela::Session` with bounded Resonith preflight and an
  allocation-free successful packet-pull path.
- Native Android application project for ARM64 and x86-64 with direct
  Resonith JNI decode and streaming PCM16 `AudioTrack` output.
- Native iOS device and simulator application project with background
  Resonith decode and `AVAudioEngine` output.
- Mandatory same-revision Windows, Android, iOS device, and iOS simulator
  build contract.
- Pinned Gradle 9.4.1 wrapper, Android Gradle Plugin 9.2.1, Android 17
  compile/target SDK 37, Android 8 minimum SDK 26, NDK r29,
  and macOS/Xcode CI gates.
- Boundary-runtime Android gate that installs the same exact APK on API 26 and
  API 37 with 4 KiB pages and on API 37 with 16 KiB pages, requiring identical
  native Resonith PCM fingerprints.
- Resonith Core revision `c6640fcd84f5be81863da6f0b8e5c3cf8ea65abd`,
  including the bounded integer MAF DSP substrate and its cross-platform
  conformance fixes.
- A portable pull-session executable gate that decodes complete streams,
  verifies timeline/resource bounds, fingerprints PCM, and rejects a
  deterministic truncation before playback.
- Direct bounded `MFT1` pull playback through Resonith Core, including
  forward/reverse immutable Basis instances, circular alignment, callback
  partitioning, and preflight rejection of a truncated stream.
- Direct composite `RSC1` MAF Truth playback with matched `MFT1` prediction,
  `MRI1` lapped innovation, and saturating PCM reconstruction.
- A real Windows audio-device release gate that requires playback position to
  advance for compact Truth, raw MFT1, and composite RSC1 files.
- Premium Android Now Playing surface with an edge-to-edge aurora backdrop,
  custom vector transport controls, responsive cards, native haptics, and an
  adaptive launcher icon.
- Four live PCM analytical views: causal field, normalized spectrum, waveform,
  and an accumulating multiresolution spectral history.
- Native Android timeline seeking, ten-second transport, repeat, volume, and
  pitch-preserving playback-speed controls.
- Incoming Android `VIEW` handling for direct system launch of external
  `.resonith` content streams.
- Shared allocation-bounded C++23 PCM visual-analysis core for Field,
  Spectrum, Wave, and multiresolution History presentation on every platform.
- Shared interface localization contract for English, German, Spanish,
  Italian, Japanese, Korean, Simplified Chinese, Russian, and Ukrainian,
  including BCP-47 system-language routing and English fallback.
- Android Interface settings surface with automatic system-language selection
  and a persistent manual language override.
- Windows x64/ARM64 Field, Spectrum, Wave, and compacting History views using
  the shared analyzer, including click/`V` switching and persisted mode.
- Windows automatic UI-language selection and a manual
  Settings → Interface → Language override backed by the shared catalog.
- Native macOS AppKit shell for ARM64/x86-64 with direct `AVAudioEngine`
  playback, all four visual modes, and the same Settings language contract.
- Native GTK4/GStreamer shell for Ubuntu, Debian, and FreeBSD with direct PCM
  playback, all four visual modes, and the same Settings language contract.
- Cross-platform GitHub build matrix for Windows x64/ARM64, macOS
  ARM64/x86-64, Ubuntu, Debian, and FreeBSD.
- Deterministic multi-platform update-manifest generator and a signed
  packaging contract that distinguishes installers, store packages, portable
  archives, and authenticated automatic updates.
- Reproducible per-user Windows x64 and ARM64 NSIS installers with Start-menu
  entries, uninstall metadata, the native payload architecture recorded in
  the registry, and honest `.resonith` Open With registration.
- A pinned NSIS 3.12 bootstrap whose downloaded binary must match the accepted
  SHA-256 before execution, plus a transactional install/uninstall gate.
- Linux desktop integration metadata, direct file-activation handling, and
  CPack definitions for installable Debian/Ubuntu `.deb` and FreeBSD `.pkg`
  artifacts.
- A macOS `productbuild` package lane alongside the application archive; the
  alpha package remains ad-hoc until Developer ID signing and notarization are
  configured.
- A cross-platform packaging-contract test that prevents Windows, Android,
  Apple, and Linux release versions or supported file-type claims from
  silently drifting apart.
- A fail-closed manual prerelease assembler that accepts an immutable version
  tag only after successful Windows, desktop Unix/Apple, and mobile workflows
  exist for the exact source commit. The old x64-only tag publisher was
  removed.

### Changed

- Windows file loading is now a narrow adapter over the same portable
  decoder/session implementation used by mobile builds.
- The implementation language baseline is C++23 on every native target.
- The player now identifies the active path as bounded MAF Truth playback.
  Optional Gemini Foundry analysis remains encoder-side and adds no player
  network or credential dependency.
- Published reproducible `0.3.0-alpha.2` Core/build/mobile evidence and
  complete speech, piano, and 400.773-second Mozart pull-session results.
- Windows playback now pulls into four reusable 4096-frame `waveOut` buffers;
  file open decodes only one bounded visualization preview instead of the
  complete track.
- On the reference Windows system, full Mozart load/start fell from about
  32.5 seconds to 0.049/0.173 seconds for compact Truth and 0.571/0.625 seconds
  for composite RSC1.
- Android live spectral analysis now uses a bounded Goertzel bank and cached
  Hann window instead of per-sample trigonometric evaluation.
- The mobile timeline and analytical views consume the same native PCM packets
  queued to the audio device; they do not predecode a WAV or maintain a second
  media representation.
- Windows executable and installer version resources now agree with
  `VERSION` at `0.3.0-alpha.6`.

### Fixed

- Android 17 renderer diagnosis is now fail-closed and evidence-gated. The
  isolated GitHub matrix proved that Emulator `36.6.11.0` crashes the pinned
  Android 17 compositor with SwiftShader, swangle/SwiftShader, and
  swangle/lavapipe; the host backend never reached ADB. The gate preserves the
  stock guest and requires a 120-second compositor soak, one SurfaceFlinger
  lifetime, 24 healthy service/storage observations, zero matching crash
  signatures, and four decoded, CRC-valid non-uniform screenshots before any
  backend can become a candidate. Release promotion remains blocked while
  adjacent official Emulator packages are tested.
- Android 17 16-KiB page-size validation now uses the kernel-facing
  `getconf PAGE_SIZE`; `/proc/self/smaps` remains only the API 26 fallback
  because compatibility mappings can report 4 KiB on a 16-KiB kernel.
- Composite Resonith files no longer fail with `Resonith preflight: bad magic`.
- Long recordings no longer require a complete PCM allocation before the Play
  command becomes available.
- Android external streams no longer depend on the bundled demonstration path.
- Quiet passages no longer collapse the primary analyzer into a flat line;
  adaptive dB shaping preserves their real spectral contour while the timeline
  retains absolute event strength.
- Android transport and timeline controls now expose localized TalkBack
  labels in all nine supported interface languages.

### Planned

- Complete the release-blocking Premium Command Center goal: global setting
  search, keyboard-only navigation, full category coverage, premium motion and
  focus states, persisted working controls, and explicit status labels for
  capabilities that do not yet have a backend.
- Complete the same composite transport and measured startup gate on Android
  and iOS; add playlists and library adapters.

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
