# Orkela Settings Coverage

Status: **LIVING IMPLEMENTATION MAP**

VLC exposes simple and advanced preferences for Interface, Audio, Video,
Subtitles/OSD, Input/Codecs, and Hotkeys, plus runtime Media, Playback, Audio,
Video, Subtitle, Tools, and View commands. Orkela uses those mature capability
classes as a coverage floor, not as a visual or architectural template.

Primary references:

- [VLC Preferences](https://docs.videolan.me/vlc-user/desktop/3.0/en/basic/settings/preferences.html)
- [VLC Menu Bar](https://docs.videolan.me/vlc-user/desktop/3.0/en/gettingstarted/desktopoverview/windows_and_linux/menu_bar.html)
- [VLC Adjustment and Effects](https://docs.videolan.me/vlc-user/desktop/3.0/en/basic/settings/adjustmentsandeffects.html)
- [VLC Hotkeys](https://docs.videolan.me/vlc-user/desktop/3.0/en/basic/hotkeys.html)

## Status vocabulary

- **WORKING** — implemented and included in release QA.
- **FOUNDATION** — visible, structurally integrated, and partially functional.
- **PLANNED** — intentionally unavailable until its backend exists.
- **PENDING CORE** — depends on the independent SceneLith decoder.
- **LOCKED** — safety or Truth invariant that user settings cannot disable.

## Coverage map

| Area | Current Orkela state | Status |
|---|---|---|
| Open, drag/drop, canonical associations | Resonith, SceneLith, and Orka recognition | **WORKING** |
| Play/pause/stop/seek/skip/volume | Native transport and keyboard controls | **WORKING** |
| Autoplay, resume, repeat, seek interval | Persistent Command Center preferences | **WORKING** |
| Audio output | Windows default PCM endpoint | **WORKING** |
| Device selection and exclusive mode | WASAPI session adapter | **PLANNED** |
| Equalizer, compressor, spatializer | Post-Truth presentation DSP | **PLANNED** |
| Waveform and spectrum | Reconstructed-PCM analysis | **WORKING** |
| Additional visualizers and fullscreen focus | Scope, phase, loudness, field | **PLANNED** |
| Video aspect, crop, HDR, presentation | SceneLith surface | **PENDING CORE** |
| Subtitle tracks, typography, delay, encoding | Accessibility renderer | **PLANNED** |
| Playlist, bookmarks, history, library | Portable media session | **PLANNED** |
| Theme, DPI, motion | Midnight theme, per-monitor DPI, live motion switch | **FOUNDATION** |
| Global and customizable hotkeys | Local playback keys exist | **FOUNDATION** |
| Codec/input tuning | Decoder resource profile and diagnostics | **PLANNED** |
| Bounded preflight and offline decode | Cannot be disabled by presentation UI | **LOCKED** |
| Privacy and telemetry | No runtime network or telemetry | **LOCKED** |
| Settings search and keyboard navigation | Live cross-category index, type-to-search, Tab/arrows/Enter/Escape | **WORKING** |
| Full capability category map | Playback, Audio, Visuals, Video, Subtitles, Library, Interface, Performance, Privacy, Hotkeys, Advanced | **WORKING** |

The map grows only when a feature has a real owner and release gate. The UI
does not advertise a checkbox that silently does nothing.
