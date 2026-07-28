# Windows Installer Alpha.6 Gate

Date: 2026-07-28  
Candidate: `0.3.0-alpha.6`  
Status: **LOCAL GATE PASS; SIGNED PUBLICATION PENDING**

## Scope

This gate turns the existing portable Windows executables into real per-user
installers. It does not claim that unsigned alpha packages are authenticated
automatic updates.

The installer:

- requires no administrator privilege;
- installs under `%LOCALAPPDATA%\Programs\Orkela` by default;
- records the native payload architecture;
- creates Start-menu launch and uninstall entries;
- registers Orkela as an available handler for `.resonith`;
- supplies Windows uninstall metadata;
- removes its files, ProgID, and product/uninstall keys transactionally.

`.scenelith` and `.orka` are intentionally not registered yet because their
native readers are not implemented.

## Toolchain integrity

NSIS 3.12 was downloaded from the official SourceForge project. The local
bootstrap binary matched both hashes exposed by the official file metadata:

| Hash | Value |
|---|---|
| SHA-1 | `6381316aa3f8203688082c0b88fc5ff304c89b69` |
| MD5 | `d5d54c2a96c1bcb25764adc9f9ff97f2` |
| Locally recorded SHA-256 | `3bc2b06253a7e4957111be152ac6a536e0c7478a706e19da814038db5d706495` |

The reproducible bootstrap pins the SHA-256 and refuses to execute a mismatch.

## Artifacts

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `Orkela-Windows-x64-0.3.0-alpha.6-Setup.exe` | 1,187,202 | `dc069e09a6065a9dd8aa58a091f81ff5791e3d5c47609155d1dce8b3c0d52644` |
| `Orkela-Windows-arm64-0.3.0-alpha.6-Setup.exe` | 1,073,250 | `7dd95cedcfccfcc0e1d200513dc5172e43800e0f5402b9086d759271e55f1989` |

The embedded native payloads retain the separately tested hashes:

| Payload | Bytes | SHA-256 |
|---|---:|---|
| Windows x64 | 2,763,264 | `880314be56b2a6b2bc5918fca6c55f2c3cb2ea75e5090673f220aadca2952e4d` |
| Windows ARM64 | 2,475,008 | `617b73d7e76c531200c031e4de8e8249d95882be058804388b26cf9c2fa2ee00` |

Both payloads were configured from a fresh public FetchContent clone pinned to
Resonith commit
`c6640fcd84f5be81863da6f0b8e5c3cf8ea65abd`; neither build used the local
Resonith source-tree override.

## Transaction gate

The x64 package was installed silently into a unique isolated directory,
without changing the default installation location. The gate verified:

- installer exit code `0`;
- installed `Orkela.exe`, uninstaller, README, changelog, and version file;
- executable product version `0.3.0-alpha.6`;
- registry architecture `x64`;
- exact isolated `InstallLocation`;
- the `Orkela.Resonith` ProgID;
- uninstaller exit code `0`;
- removal of the executable, product key, uninstall key, ProgID, association
  value, and installation directory.

ARM64 cannot be executed on the x64 reference host. Its native executable
passed the strict ARM64 cross-build; the same installer script is exercised in
the Windows ARM64 GitHub job before publication.

## Remaining release blockers

- Merge the published Resonith Core draft PR after review.
- Run the public Windows x64/ARM64 jobs from that exact revision.
- Establish protected release signing and Authenticode identities before a
  stable automatic-update channel is enabled.
