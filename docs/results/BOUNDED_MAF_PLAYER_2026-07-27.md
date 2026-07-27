# Orkela 0.3.0-alpha.2 Bounded MAF Player Gate

Date: **2026-07-27**  
Status: **CORE/BUILD/MOBILE PASS; INTERACTIVE RELEASE GATE STILL REQUIRED**

## Scope

Orkela candidate `0.3.0-alpha.2` updates the player to the bounded integer MAF
DSP substrate while preserving the admitted LPS4/LPS5 transport. Optional
Gemini Foundry analysis remains encoder-side: the player has no provider SDK,
network call, API key, Python runtime, or cloud dependency.

Player source revision:
`0fd7d361e70c3787aeb5354960fb941c3c98f9d2`.

Pinned Resonith revision:
`d8245c207ada6cd7a1f72ad595e7edbd933d2da4`.

The local integration build used Resonith revision
`f16fbd0ed3b07a6587284c70330b7dc3a19d0b85`; its `native/` tree is exactly
identical to the pinned revision at Git tree
`7a5afce1bcf04d6986d90a33faa60b3babc5f5db`.

## Windows C++23 build

The strict Release build used CMake 4.4.0, Ninja 1.13.2, and LLVM-MinGW Clang
22.1.8 with warnings as errors.

| Artifact | Complete bytes | SHA-256 |
|---|---:|---|
| `Orkela.exe` | 2,683,392 | `db6b216f81f5717c0b3ae3d53b461c24d1e2410623d8200294a2ff56a3246b4c` |
| `orkela_session_gate.exe` | 1,598,976 | `67cb045eb7ed97d2642f391149a7b1c149b3762ade86370f66b9c10412b03a37` |

Windows file and product versions both report `0.3.0-alpha.2`.

Local candidate package:

```text
G:\Orkela\artifacts\packages\Orkela-Windows-x64-0.3.0-alpha.2\Orkela.exe
```

## Complete pull-session results

The new portable gate opens each real stream through the same
`Orkela::Session` used by Windows, Android, and iOS, pulls every packet,
verifies the logical timeline and declared frame count, fingerprints decoded
PCM, and requires a one-byte truncation to fail before playback.

| Input | Bytes | Frames / format | PCM FNV-1a 64 | Wall time | Result |
|---|---:|---|---:|---:|---|
| `speech.resonith` | 17,929 | 93,680 / 16 kHz mono | `8339610397528337204` | 0.111 s | PASS |
| `emotional-piano.resonith` | 117,643 | 352,800 / 44.1 kHz stereo | `12408445622142514315` | 0.631 s | PASS |
| `mozart.resonith` | 6,508,774 | 19,237,088 / 48 kHz stereo | `15780289417298120880` | 34.492 s | PASS |

Input identities:

| Input | SHA-256 |
|---|---|
| `speech.resonith` | `a85b1308a252714298f9ac5155d29c45b7a763275a28eef88fcc38ffd3042e80` |
| `emotional-piano.resonith` | `fbd985cce4091d92c911e93a617faddf0b94370d6677640aa0dc94a12623a05a` |
| `mozart.resonith` | `77eb9751603f4a37fae4ef961ab3423accbc0bef576ee2101f4081b3616edf8b` |

CTest passed the bundled emotional-piano session and corruption gate.

## Public CI

GitHub Actions passed from the exact player source revision:

- [Windows run 30257538416](https://github.com/moshkinyevhen/orkela/actions/runs/30257538416):
  build PASS;
- [mobile run 30257538455](https://github.com/moshkinyevhen/orkela/actions/runs/30257538455):
  Android APK, iOS device ARM64, and iOS simulator x86-64 all PASS.

## Honest boundary

This report proves the updated player and portable session compile and decode
the complete public references. It does not replace the interactive release
gate for audible device output, play/pause/seek/stop, timeline and spectrum
motion, drag-and-drop, high-DPI layout, or iOS device runtime. Therefore
`0.3.0-alpha.2` remains an untagged candidate.
