# Orkela Update and Packaging Contract

Status: **TUF SECURITY CORE IMPLEMENTED; PLATFORM SIGNING PENDING**

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

`orkela-update-v1.unsigned.json` is deterministic release inventory generated
from the exact artifacts. It is not update authority. Authenticated desktop
update evidence uses a TUF 1.0 repository with:

- versioned offline root metadata and sequential client root rotation;
- `targets`, `snapshot`, and short-lived `timestamp` roles;
- a 2-of-3 threshold for root and targets;
- monotonically increasing metadata versions and expiry;
- consistent snapshots with hash-prefixed target files;
- target byte length, SHA-256, platform, architecture, package kind, release
  version, channel, and immutable source commit.
- a signed release ledger chaining each sequence to the exact preceding
  targets metadata, a cumulative signed history that proves safe skipped
  releases, plus a client ledger that separates release-wide identity from
  per-platform target hashes and rejects equivocation even when a caller
  supplies a stale installed version;
- channel-specific maximum metadata lifetimes so a valid signature cannot
  silently extend the beta/nightly freeze window.

The TUF client rejects rollback, freeze/expired metadata, mix-and-match
metadata, unknown or insufficient signatures, oversized metadata, and target
length/hash mismatch before a package reaches platform installation.
`tools/release/tuf_repository.py` uses the upstream Python-TUF 7.0.0 reference
implementation only as release tooling and independent repository evidence.
Its Ubuntu x64 CI dependencies are hash-locked in
`tools/release/requirements-tuf-ci-linux-x64.txt`.

The built-in `bootstrap --development-test-keys` route creates disposable,
unencrypted keys only for hostile-client tests. It is fail-closed without that
explicit flag. Production root/targets keys require an offline witnessed
ceremony and protected hardware or OS-backed custody; only short-lived online
role material may enter a protected release environment. No private key may
enter source, Actions artifacts, logs, or application packages. Stable, beta,
and nightly channels use independent repositories and may use independent
keys.

`refresh-online-metadata` renews snapshot and timestamp metadata without a new
application release. Their versions increase independently of the application
targets sequence, so repeated refreshes followed by a new application release
remain monotonic for existing clients. Refresh refuses expired targets,
snapshot expiry beyond targets expiry, nested signer custody, and any output
path overlapping a signer directory.

Python remains outside Orkela Core, SDK, audio callbacks, and application
runtime. Platform-native authorities perform installation: App Installer on
Windows, Sparkle/Developer ID on macOS, signed apt/pkg repositories on
Ubuntu/Debian/FreeBSD, and store update services on Android/iOS.

## Platform packages

| Platform | Installation artifact | Update authority |
|---|---|---|
| Windows x64 | per-user NSIS alpha; signed MSIX for promotion | MSIX App Installer; Authenticode before promotion |
| Windows ARM64 | per-user NSIS alpha; signed MSIX for promotion | MSIX App Installer; Authenticode before promotion |
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
8. run the same installer on a native runner for its declared architecture;
9. retain a verified previous package and prove interrupted-install recovery.

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

Windows x64 and ARM64 now use separate native GitHub runners. The gate reads
the installed executable's PE machine field, proves that the installed bytes
match the tested build payload, and runs a bounded installed `--self-test`
that completely decodes a real Resonith input and records its PCM fingerprint.
It then performs the isolated uninstall transaction and checks filesystem,
registry, file-association, and Start-menu residue. A cross-compiled ARM64
payload or a merely long-lived GUI process is no longer accepted as native
execution evidence.

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

The `Update Security` workflow installs Python-TUF and its crypto dependencies
from hash-locked wheels and runs hostile-client tests. This proves the
repository contract, not production key custody. Public update promotion is
still blocked until protected/offline keys and every platform signing identity
are configured. Development roots are marked inside signed root metadata and
both build and verify reject them unless an explicit test-only override is
present. All verification occurs in a sibling transaction directory under an
OS advisory lock; architecture, channel, version, ledger, and target failures
leave every byte of the previous trusted state unchanged.

The workflow also runs daily as a liveness regression for the renewal path.
It does not publish production metadata. A real channel still requires a
protected scheduled signer/publisher backed by production online keys; until
that external service exists, automatic update promotion remains disabled and
the public release contains only transparent unsigned inventory.

GitHub release tags must be immutable through the repository ruleset. The
assembler checks the local and remote peeled tag immediately before
`gh release create --verify-tag`; the protected immutable-tag rule remains an
external repository-administration prerequisite because client-side checks
cannot close a server-side ref-update race by themselves.
