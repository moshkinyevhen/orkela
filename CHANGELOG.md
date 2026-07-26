# Orkela Changelog

All notable released changes are recorded here. Every playback or interface
release links to reproducible QA evidence and identifies the exact executable.

## [Unreleased]

### Planned

- Complete the release-blocking Premium Command Center goal: global setting
  search, keyboard-only navigation, full category coverage, premium motion and
  focus states, persisted working controls, and explicit status labels for
  capabilities that do not yet have a backend.
- Streaming Resonith decode, playlists, and portable media/session adapters.

## [0.2.0-alpha.2] - 2026-07-26

### Added

- Responsive background Resonith validation and decode for long-form media.
- Mandatory short/long playback, malformed-input, high-DPI, association, and
  visual release-evidence gate.
- Versioned local package and GitHub publication contract.
- Embedded Windows file/product version and versioned CI release build.
- Premium icon-led Command Center foundation with persistent working playback,
  audio, visual, interface, and trust preferences.

### Fixed

- Long `.resonith` files no longer block the Windows message loop while the
  native decoder prepares playback PCM.

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
