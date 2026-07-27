# Orkela 0.3.0-alpha.3 Direct MFT1 Player Gate

Date: **2026-07-27**  
Status: **PUBLIC-PIN WINDOWS AND ANDROID PASS; IOS CI PENDING**

Pinned Resonith revision:
`9f7650bf0bf06a35388119614745c6db1dbef709`.

## Result

Orkela now opens and pulls bounded typed-MAF `MFT1` streams directly through
the same strict C++23 `Orkela::Session` used by its desktop and mobile shells.
No WAV intermediary, Python runtime, provider SDK, network request, or
per-stream executable DSP is involved.

The new backend:

- recognizes `MFT1` by magic and validates the complete stream before
  playback;
- enforces the existing 512 MiB input, two-hour output, mono/stereo, and
  preflight workspace bounds;
- allocates the exact declared MAF workspace once;
- executes successful pull calls without allocation;
- supports immutable Basis instances with crop, integer/circular alignment,
  signed gain, and reverse traversal;
- rejects truncated input before audio reaches the device adapter.

## Windows C++23 gate

Toolchain: LLVM-MinGW Clang 22.1.8, CMake 4.4.0, Ninja 1.13.2, strict C++23,
warnings as errors.

| Test | Result |
|---|---|
| Existing lapped `.resonith` complete pull/corruption gate | PASS |
| New direct `MFT1` forward/reverse/circular/truncation gate | PASS |

CTest: **2/2 passed**.

| Artifact | Complete bytes | SHA-256 |
|---|---:|---|
| `build/cpp23-clang22-pinned-r151/Orkela.exe` | 2,700,288 | `9945f6665b454f7e0b9fca0fe45ee4a99903d361a159cf96162dd6a35f978865` |
| `build/cpp23-clang22-pinned-r151/orkela_maf_session_gate.exe` | 1,585,664 | `95d1e5ed0aaa53b4bebe7bba03a98cc3aadd288603325dc0c0911db3acbbd045` |

## Android gate

The local Gradle 9.4.1 / AGP 9.2.1 build used SDK 36, NDK r29, CMake 4.1.2,
Clang 21, Java 25, C++23, and the public immutable Resonith revision pinned by
Orkela CMake. `ORKELA_RESONITH_SOURCE_DIR` was deliberately unset.

Both `arm64-v8a` and `x86_64` native libraries compiled and the debug APK
assembled successfully.

| Artifact | Complete bytes | SHA-256 |
|---|---:|---|
| `platform/android/app/build/outputs/apk/debug/app-debug.apk` | 4,306,666 | `4e1bb04b3b662c95a1a77795ecae1b824e9cbf3a65a394ac8c512d80f3809a6c` |

## Remaining release boundary

The candidate is not tagged yet. The exact Resonith source revision containing
`MFT1` and reverse Basis support is public, pinned, and passes local Windows
and Android builds without a source override. Orkela must still pass public
Windows/Android/iOS CI from that pin and complete the interactive
audible-output and Premium Command Center gates.
