# Orkela Update and Packaging Contract

Status: **ACCEPTED ARCHITECTURE; SIGNED DISTRIBUTION PENDING**

## Product rule

An archive is not called an installer, and a downloadable file is not called
an automatic update. A promoted Orkela release must distinguish:

- a portable archive;
- a native installer or store package;
- a cryptographically authenticated update path.

No Orkela process may execute a downloaded artifact until the release
metadata signature, artifact SHA-256, declared byte length, platform,
architecture, and version transition have all passed validation.

## Release metadata

`orkela-update-v1.json` is deterministic metadata generated from the exact
release artifacts. It carries:

- schema identifier and release channel;
- semantic version and immutable source commit;
- publication timestamp;
- platform, architecture, package kind, filename, byte length, SHA-256, and
  HTTPS URL for every artifact.

The JSON is signed as a detached Ed25519 document. Private signing material
exists only in the protected release environment. Applications contain only
the public verification key. Stable, beta, and nightly channels have
independent metadata and may use independent signing keys.

The generator is release tooling and is not shipped in the player. Python
therefore remains outside Orkela Core, SDK, audio callbacks, and application
runtime.

## Platform packages

| Platform | Installation artifact | Update authority |
|---|---|---|
| Windows x64 | per-user NSIS installer with native x64 payload | signed Orkela metadata; Authenticode before stable |
| Windows ARM64 | per-user NSIS installer with native ARM64 payload | signed Orkela metadata; Authenticode before stable |
| macOS ARM64/x86-64 | notarized application archive or DMG | Sparkle 2 appcast with EdDSA and Apple code signing |
| Ubuntu | signed `.deb` and updateable AppImage | apt repository or embedded AppImage zsync metadata |
| Debian | signed `.deb` and updateable AppImage | apt repository or embedded AppImage zsync metadata |
| FreeBSD | native `.pkg` | signed FreeBSD package repository metadata |
| Android | signed AAB/APK | Google Play update authority for public releases |
| iOS | signed archive delivered through TestFlight/App Store | App Store update authority |

Debug APKs, ad-hoc macOS bundles, unsigned iOS simulator applications, and
CI tar archives remain test artifacts. They are never presented as
production installers.

## Update behavior

- System/store policy is the default on Android and iOS.
- Desktop builds check in the background only after the application has
  started successfully; playback never waits for an update request.
- Automatic download is opt-in. Installation is atomic and occurs only after
  playback has stopped.
- A failed network request, malformed manifest, unknown signing key, hash
  mismatch, downgrade, architecture mismatch, or missing code signature
  leaves the installed application untouched.
- The updater retains one rollback-capable previous desktop build.
- Telemetry is not required for update checks.

## Release gate

Before an update channel is enabled, CI must:

1. build each artifact from the same immutable commit;
2. test the installed product, not only the unpacked executable;
3. generate deterministic metadata from those exact files;
4. sign metadata in the protected release job;
5. verify the signature and every artifact hash in a clean environment;
6. test upgrade, downgrade rejection, interrupted download, corrupt package,
   wrong architecture, rollback, and uninstall;
7. publish package hashes and evidence in the matching changelog entry.

Until those gates and signing identities exist, Orkela exposes no non-working
“automatic updates” control.

## Current alpha implementation

`tools/release/bootstrap_nsis.ps1` accepts only NSIS 3.12 with the pinned
SHA-256 recorded in source. `build_windows_installer.ps1` produces distinct
x64 and ARM64 filenames, and `test_windows_installer.ps1` verifies the complete
x64 current-user install/uninstall transaction. The package registers
`.resonith` as an available Open With application. It deliberately does not
claim `.scenelith` or `.orka` until those native readers exist.

Alpha installers are unsigned development artifacts. They are valid
installation packages, but they are not promoted to an authenticated automatic
update channel until the detached-signature and platform code-signing gates
above pass.

Linux packaging is generated from the same CMake install graph. Ubuntu 24.04
and Debian 13 jobs build `.deb` packages, inspect them, install them, launch the
installed binary under a virtual display, remove them, and require that
`/usr/bin/orkela` is gone. The FreeBSD job performs the analogous native
`.pkg` transaction under FreeBSD 14. macOS jobs build both a checked
application archive and a `productbuild` `.pkg`; public distribution remains
blocked on Developer ID signing and notarization.

The public alpha assembler is manual and fail-closed. It resolves successful
required workflow runs by exact source SHA, downloads only product artifacts,
rejects filename collisions or a missing platform package, and refuses to
overwrite an existing GitHub release. Until protected signing exists it emits
`orkela-update-v1.unsigned.json`; that filename is intentional and no Orkela
runtime treats it as update authority.
