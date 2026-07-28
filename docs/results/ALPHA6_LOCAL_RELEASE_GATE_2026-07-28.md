# Orkela Alpha.6 Local Release Gate

Date: 2026-07-28  
Candidate: `0.3.0-alpha.6`  
Resonith pin: `c6640fcd84f5be81863da6f0b8e5c3cf8ea65abd`  
Status: **LOCAL WINDOWS/ANDROID PASS; NATIVE CI MATRIX PENDING**

## Public dependency gate

Fresh Windows x64 and ARM64 build trees resolved Resonith only through the
public GitHub FetchContent URL and the immutable commit above. The fetched
checkout in both trees matched the requested commit exactly.

The x64 public-pin build passed all six CTest entries:

1. bounded Resonith session;
2. typed MAF session;
3. visual analysis;
4. nine-language localization;
5. deterministic update manifest;
6. cross-platform packaging/version contract.

The ARM64 public-pin build completed with Clang 22.1.8 and strict warnings.

## Windows installer transaction

The final public-pin x64 installer was installed silently into a unique
current-user test location. The gate verified payload/version/architecture,
README/changelog/version files, product and uninstall keys, and the Resonith
ProgID. The installed package then uninstalled with exit code zero and left
none of those files or registry keys behind.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| Windows x64 EXE | 2,763,264 | `880314be56b2a6b2bc5918fca6c55f2c3cb2ea75e5090673f220aadca2952e4d` |
| Windows ARM64 EXE | 2,475,008 | `617b73d7e76c531200c031e4de8e8249d95882be058804388b26cf9c2fa2ee00` |
| Windows x64 Setup | 1,187,202 | `dc069e09a6065a9dd8aa58a091f81ff5791e3d5c47609155d1dce8b3c0d52644` |
| Windows ARM64 Setup | 1,073,250 | `7dd95cedcfccfcc0e1d200513dc5172e43800e0f5402b9086d759271e55f1989` |

## Android 17 physical-device gate

Gradle rebuilt both native ABIs without `ORKELA_RESONITH_SOURCE_DIR`. The
FetchContent checkout inside both `arm64-v8a` and `x86_64` build trees matched
the public Resonith pin exactly.

The resulting APK pair was installed on the connected Android 17 device. The
native instrumentation returned `orkela.result=pass`. The player was then
force-stopped; the device remained in `Dozing` state throughout the gate.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| Android multi-ABI debug APK | 4,519,546 | `be3024d68d2bcbb16c39bd0b1388e25649d8fc775ddd9098792571400219821a` |
| Android instrumentation APK | 45,203 | `cbd8c5b484422f7c18272d33e0c46b55fbc9bc6502a58796e0484638edb3b754` |

## Publication boundary

The local evidence does not substitute for native GitHub runners. Publication
still requires successful Windows x64/ARM64, Ubuntu, Debian, FreeBSD, macOS,
Android boundary-emulator, and iOS compile/runtime workflows from the exact
Orkela commit. The prerelease assembler refuses to publish without those
successful run identities.
