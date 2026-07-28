# Orkela 0.3.0-alpha.4 RSC1 Streaming Player Gate

Date: 2026-07-27  
Status: **WINDOWS AND ANDROID PASS; IOS SAME-REVISION GATES PENDING**

## Scope

This gate fixes two release blockers found while opening the complete Mozart
research artifacts:

1. composite profile-0/level-6 RSC1 streams (`CONF + MFT1 + MRI1`) were sent to
   the compact Truth decoder and rejected with `bad magic`;
2. the Windows shell decoded the complete recording into one PCM allocation
   before Play became available.

The portable session now verifies the outer RSC1 directory, verifies every
section, opens the typed MAF predictor and bounded LPF1 innovation renderer,
and saturating-adds matched pull intervals. Windows keeps four reusable
4096-frame `waveOut` buffers and requests new PCM only as playback advances.

## Build

- Orkela candidate: `0.3.0-alpha.4`
- Source base before this uncommitted candidate: `b93a995bc7818aff407a329792ec2928a47233c4`
- Resonith source base before this uncommitted candidate:
  `86e1f131100ad3b44e55083c3c5c15463bc89a55`
- Language: strict C++23
- Compiler: LLVM/Clang 22 llvm-mingw
- Configuration: Release, warnings as errors
- Executable:
  `artifacts/packages/Orkela-Windows-x64-0.3.0-alpha.4/Orkela.exe`
- Executable size: `2,721,792` bytes
- Executable SHA-256:
  `5A554FDEA9D54234C0A1DF5E090BC55FB308C68E9BF479E49A52C37C9341A253`
- ZIP SHA-256:
  `03CCD49C7C13B70ED9B05580870CC91CAF7556A2CDA6292663F157D346F36B47`
- Embedded file/product version: `0.3.0-alpha.4`

## Real Windows audio-device results

`orkela_windows_playback_gate` opens each authenticated source, starts the
actual Windows multimedia output device, requires the playback position to
advance, and then stops the bounded queue.

| Input | Transport | Load (s) | First advanced position (s) | First position |
|---|---|---:|---:|---:|
| `emotional-piano.resonith` | compact Truth | 0.0253 | 0.1388 | 644 |
| `periodic-debug.mft1` | raw typed MAF | 0.0002 | 0.0587 | 66 |
| `mozart-r155-selected.resonith` | complete compact Truth | 0.0490 | 0.1167 | 1,174 |
| `mozart-r155-candidate.resonith` | complete composite RSC1 | 0.5513 | 0.5927 | 953 |

The prior complete-Mozart preparation path took approximately 32.5 seconds.
The measured startup reduction is therefore roughly 55-280x depending on the
transport and which latency boundary is compared.

## Input integrity

| Input | Bytes | SHA-256 |
|---|---:|---|
| `emotional-piano.resonith` | 117,643 | `FBD985CCE4091D92C911E93A617FADDF0B94370D6677640AA0DC94A12623A05A` |
| `periodic-debug.mft1` | 704 | `522F5EF329A51D01C553D9B4BCE16AD42C0745D12C340E61FF42696B7E1CBE6C` |
| `mozart-r155-selected.resonith` | 6,521,233 | `946DB08BF3E73CA54441A6972B6F339BAB9ADEA8AAFB547FC5B6A49D48FE65FA` |
| `mozart-r155-candidate.resonith` | 7,003,168 | `C83A3DD20EE367CD67645663AFA591BDF8907439D54B14A5FD1C9C74A4FC3C58` |

## Decoder conformance

- Composite Mozart full pull: 19,237,088 stereo frames at 48 kHz.
- Composite PCM FNV-1a/64:
  `11193349815165915293`.
- Fixed-density LPF1 pull equals whole-stream decode across deliberately
  non-window-aligned 17-frame requests.
- Variable-density LPF1 pull equals whole-stream decode across the same
  boundaries.
- Raw MFT1 forward/reverse conformance gate: pass.
- Compact Truth full decode and deterministic truncation rejection: pass.
- Composite full decode and deterministic truncation rejection: pass.

## Release status

The Android debug application built for ARM64 and x86-64, installed on the
API-36 x86-64 emulator, loaded its bundled Resonith stream, reported 44.1 kHz
stereo, reached `Playback complete`, and produced no AndroidRuntime/libc fatal
log. The APK is 3,768,337 bytes with SHA-256
`13CE3CD33BD5BB14A2510ACEF835C9129CB80BC6B49BE0A7CD4A89FD1D9B5E5E`.

The Windows package is locally usable and Android has passed its build/runtime
gate. GitHub publication remains blocked until the same source revision passes
the iOS device/simulator CI gates required by the accepted release protocol.
