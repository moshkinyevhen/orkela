# Orkela

Orkela is a native media player for the SceneLith ecosystem. It plays real
**Resonith** audio on Windows by calling the public Resonith Core decoder and
sending reconstructed PCM directly to the Windows audio device.

Current version: **0.2.0-alpha.2**.

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

- native C++20 and Win32;
- DPI-aware Direct2D/DirectWrite interface with a PCM-derived spectrum;
- open, play/pause, stop, seek, skip, volume, keyboard controls, and
  file drag-and-drop;
- direct LPS4/LPS5 preflight and decoding through Resonith Core;
- responsive background preflight/decode for long-form media;
- mono and stereo PCM16 output through the Windows multimedia device;
- no runtime network access and no external codec process.

This milestone decodes a complete research clip into bounded application
memory before playback. Streaming decode, playlists, mobile front ends, and
SceneLith video are subsequent milestones.

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

## Build

Requirements:

- Windows 10 or later;
- Visual Studio 2022 with the Desktop C++ workload;
- CMake 3.24 or later.

```powershell
cmake -S . -B build -A x64
cmake --build build --config Release
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
