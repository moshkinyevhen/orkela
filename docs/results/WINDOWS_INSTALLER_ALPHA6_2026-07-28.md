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
| `Orkela-Windows-x64-0.3.0-alpha.6-Setup.exe` | 1,190,739 | `6c077e2360a49b5040d5003a19e8a9a2375cc8dd59c10fc580fc830fbceed3c8` |
| `Orkela-Windows-arm64-0.3.0-alpha.6-Setup.exe` | 1,078,768 | `fedf90afe585ce2e6151deaf61cb0b862be690ced74b0c5dfc1e097ebac58908` |

The embedded native payloads retain the separately tested hashes:

| Payload | Bytes | SHA-256 |
|---|---:|---|
| Windows x64 | 2,770,432 | `30cd5a9a3f266c9c83c9e86d4bb95eba99981ec6761d6280f48d1c51b04da842` |
| Windows ARM64 | 2,481,664 | `d4aa3b198381ff556c918875b8adaea25218a668a411725a0a2dd43e2b2840cb` |

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
- installed bytes equal the tested build payload;
- bounded complete decode of 352,800 frames with PCM FNV64
  `12408445622142514315` and PCM SHA-256
  `3cfcae4996a08976f42ec83744ea0130935ca53d83b37129c001581697618618`;
- uninstaller exit code `0`;
- removal of the installation directory, product key, uninstall key, ProgID,
  association value, and Start-menu directory.

ARM64 cannot be executed on the x64 reference host. Its native executable
passed the strict ARM64 cross-build; the same installer script is exercised in
the Windows ARM64 GitHub job before publication.

## Remaining release blockers

- Merge the published Resonith Core draft PR after review.
- Run the public Windows x64/ARM64 jobs from that exact revision.
- Establish protected release signing and Authenticode identities before a
  stable automatic-update channel is enabled.
