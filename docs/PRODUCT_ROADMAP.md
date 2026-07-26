# Orkela Product Roadmap

Status: **ACCEPTED**

## O-2 — Premium Command Center

Status: **IN PROGRESS / RELEASE-BLOCKING FOR 0.2.0-alpha.2**

### Goal

Deliver a settings and control experience that is faster to understand than a
traditional desktop menu while exposing at least the same major capability
classes expected from a mature player.

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

### Release gate

The Command Center must be exercised while the full Mozart reference is
decoding and playing. Opening settings, switching categories, changing a live
preference, seeking, and closing the panel must not block playback or the
Windows message loop. Screenshots and executable hashes belong in the Orkela
release-evidence report.

## O-3 — Portable media session

After O-2 passes:

- streaming Resonith decode and bounded ring-buffer playback;
- playlist, queue, bookmarks, history, and library adapters;
- WASAPI output with device selection and gapless transition;
- portable session core for Windows, Android, iOS, Linux, and macOS;
- first SceneLith video surface when a conforming Core exists.
