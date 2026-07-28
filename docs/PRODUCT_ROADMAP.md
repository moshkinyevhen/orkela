# Orkela Product Roadmap

Status: **ACCEPTED**

## O-2 — Premium Command Center

Status: **IMPLEMENTED / FINAL QA IN PROGRESS / RELEASE-BLOCKING FOR
0.2.0-alpha.2**

### Goal

Deliver a settings and control experience that is faster to understand than a
traditional desktop menu while exposing at least the same major capability
classes expected from a mature player.

This is the immediate product goal. Do not tag `0.2.0-alpha.2` until the
Command Center, its real settings, and its release evidence satisfy this
milestone.

The milestone requires:

- an authored icon-led Command Center with premium depth, focus, hover,
  transition, and high-DPI behavior;
- one-glance quick controls plus categorized Playback, Audio, Visuals, Video,
  Subtitles, Library, Interface, Performance, Privacy, Hotkeys, and Advanced
  settings;
- instant setting search and keyboard navigation;
- persistence for settings that are safe to retain locally;
- working controls only; unavailable codec/backend features display an
  explicit `PLANNED`, `RESEARCH`, or `PENDING CORE` status;
- no presentation setting may alter Resonith Truth reference state;
- visual QA at 100%, 150%, and 200% DPI, minimum size, constrained work area,
  keyboard-only use, and reduced-motion mode.

### Next implementation step

Complete the Command Center before any additional codec-facing player work:

- [x] finish the premium icon-led shell, focus states, and compact quick
  controls;
- [x] add global setting search and complete keyboard-only navigation;
- [x] expose the full category map: Playback, Audio, Video, Subtitles,
  Library, Interface, Performance, Privacy, Hotkeys, and Advanced;
- [x] connect every currently available preference to real persisted
  behavior;
- [x] mark unavailable capabilities visibly as `PLANNED`, `RESEARCH`, or
  `PENDING CORE` instead of presenting inert controls;
- [x] compare capability coverage against the documented VLC preference and
  playback-control surface, then preserve only settings that are meaningful
  to Orkela's architecture;
- [ ] pass the remaining 100%, 150%, constrained-layout, reduced-motion,
  malformed-input, and complete O-2 release gates before tagging
  `0.2.0-alpha.2`.

### Release gate

The Command Center must be exercised while the full Mozart reference is
decoding and playing. Opening settings, switching categories, changing a live
preference, seeking, and closing the panel must not block playback or the
Windows message loop. Screenshots and executable hashes belong in the Orkela
release-evidence report.

## O-3 — Portable media session

Status: **IN IMPLEMENTATION**

- [x] strict C++23 platform-neutral Resonith pull session;
- [x] Android ARM64/x86-64 JNI package and streaming `AudioTrack` path;
- [x] iOS device/simulator UIKit package and `AVAudioEngine` path;
- [ ] bounded cross-platform producer/ring buffer for Windows and iOS;
- playlist, queue, bookmarks, history, and library adapters;
- WASAPI output with device selection and gapless transition;
- [x] mandatory Windows, Android, and iOS build matrix;
- [ ] Linux and macOS desktop adapters;
- first SceneLith video surface when a conforming Core exists.

## O-4 — Native installation and authenticated updates

Status: **IN IMPLEMENTATION**

- [x] native NSIS install/uninstall transaction on Windows x64;
- [x] move Windows ARM64 build, tests, install, launch, and uninstall to the
  native `windows-11-arm` GitHub runner;
- [x] validate installed PE architecture instead of trusting registry text;
- [x] replace GUI-liveness probing with a bounded installed full-decode
  self-test and deterministic PCM fingerprint;
- [x] implement TUF 1.0 repository generation with 2-of-3 root/targets
  thresholds, consistent snapshots, expiry, and persisted client state;
- [x] reject signed rollback, expired/frozen metadata, mix-and-match metadata,
  insufficient signatures, and corrupt targets in hostile-client tests;
- [x] make verifier state transactional and preserve it byte-for-byte on any
  rejected target;
- [x] enforce contiguous signed release history, root rotation, maximum
  channel lifetimes, and persisted version/commit/hash anti-equivocation;
- [x] decouple online snapshot/timestamp renewal from application releases and
  test renewal → renewal → application-release monotonicity;
- [x] add cumulative signed release history and reject forks after an accepted
  release while allowing platform-target migration within one release;
- [ ] deploy the protected scheduled production metadata signer/publisher;
- [ ] publish signed MSIX/App Installer packages for Windows;
- [ ] publish Developer ID signed, notarized Sparkle packages for macOS;
- [ ] publish signed apt and FreeBSD pkg repositories;
- [ ] publish release AAB/TestFlight products through store authority;
- [ ] prove upgrade, interrupted update, downgrade rejection, and retained
  rollback on each desktop platform;
- [ ] synchronize every exact tested artifact into the local release archive.
