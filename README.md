# Orkela

Orkela is a small native media player for the SceneLith ecosystem. The first
research release plays real **Resonith LPS5** audio files on Windows by calling
the public Resonith Core decoder and sending the reconstructed PCM directly to
the Windows audio device.

`LPS5 file -> Resonith Core -> PCM16 -> Windows audio`

There is no WAV conversion in this path.

## Name

**Orkela** is pronounced `or-ke-la`. The name combines orchestration with the
musical syllable *la*: the player will ultimately orchestrate independent
Resonith audio, SceneLith video, subtitles, and the optional AV bridge.

The name is a working product decision pending formal trademark clearance.

## Current milestone

- native C++20 and Win32;
- Open, Play, Stop, and file drag-and-drop;
- direct LPS4/LPS5 preflight and decoding through Resonith Core;
- mono and stereo PCM16 output through the Windows multimedia device;
- no runtime network access and no external codec process.

This first milestone decodes a complete research clip into bounded application
memory before playback. Streaming, seeking, playlists, mobile front ends, and
SceneLith video are subsequent milestones.

## Build

Requirements:

- Windows 10 or later;
- Visual Studio 2022 with the Desktop C++ workload;
- CMake 3.24 or later.

```powershell
cmake -S . -B build -A x64
cmake --build build --config Release
```

The executable is `build/Release/Orkela.exe`.

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
