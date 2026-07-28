# Orkela Authenticated Update Core Gate

Date: 2026-07-28
Candidate: `0.3.0-alpha.6`
Status: **LOCAL CORE PASS; REMOTE NATIVE/SIGNING GATES PENDING**

## Decision

The previous detached-manifest proposal is rejected as insufficient. Orkela
now uses the upstream TUF 1.0 model for authenticated desktop release
evidence. Installation remains delegated to each platform's native authority.

This separation is intentional:

- TUF authenticates timely metadata and exact package bytes;
- Windows App Installer, Sparkle/Developer ID, apt, FreeBSD pkg, Google Play,
  and the App Store own privileged installation;
- the media decoder and audio callback contain no network, Python, key, or
  updater code.

## Implemented gate

The repository generator creates:

- a versioned 2-of-3 Ed25519 root role;
- a 2-of-3 targets role;
- independent snapshot and timestamp roles;
- monotonically versioned metadata with ordered expiry;
- consistent snapshots and full SHA-256 target names;
- signed custom target fields for platform, architecture, package kind,
  release version, channel, source commit, and sequence.

Disposable hostile-client keys require the explicit
`--development-test-keys` switch, must reside in a directory disjoint from the
trusted root and outside the checkout, and cannot be mistaken for production
key custody. Existing key stores and output repositories are never
overwritten.

## Measured local result

The hostile-client suite passed:

| Gate | Result |
|---|---|
| Threshold-signed refresh and exact target download | PASS |
| Persisted client rejects an older fully signed repository | PASS |
| Expired signed timestamp is rejected | PASS |
| Snapshot rejects targets metadata from another generation | PASS |
| Corrupt target bytes are rejected before delivery | PASS |
| One remaining targets key cannot satisfy 2-of-3 | PASS |
| Non-HTTPS release inventory is rejected | PASS |
| Abbreviated source commit is rejected | PASS |
| Failed wrong-architecture/corrupt-target refresh preserves state byte-for-byte | PASS |
| v1 client accepts v2 root only after old and new 2-of-3 thresholds | PASS |
| Missing intermediate root is rejected | PASS |
| Development-key root is rejected by production build and verify | PASS |
| Version/commit/target-hash equivocation is rejected by the client ledger | PASS |
| Android debug bundle is excluded from desktop update targets | PASS |
| macOS x86_64 release token matches the signed artifact policy | PASS |
| Beta timestamp/snapshot/targets maximum lifetime is enforced | PASS |
| Crash after trusted-state backup restores the newest ledger before refresh | PASS |
| Repeated snapshot/timestamp renewal works without an application release | PASS |
| New application release stays monotonic after repeated online renewal | PASS |
| Expired targets cannot be hidden behind fresh online metadata | PASS |
| Cumulative history rejects a signed fork after an accepted release | PASS |
| x64/ARM64 targets share release identity without false equivocation | PASS |
| Old-only and new-only root rotations are both rejected | PASS |
| Test-key trust cannot rotate into a production-key profile | PASS |
| Missing or malformed persisted client ledger fails closed | PASS |
| Refresh cannot copy embedded signer material or symlinked repository data | PASS |

The implementation also replaces Python-TUF's root symlink on Windows with an
fsync-plus-atomic-replace copy. This removes the Developer Mode/administrator
requirement without changing TUF signature, version, expiry, or hash checks.
The complete local Python regression discovery ran 91 tests successfully.

The Windows x64 installed-product gate also passed with the exact candidate
payload. `Orkela.exe --self-test` completely decoded 352,800 frames of the
checked Resonith sample and emitted PCM FNV64
`12408445622142514315` and PCM SHA-256
`3cfcae4996a08976f42ec83744ea0130935ca53d83b37129c001581697618618`
before uninstall residue checks.

## Honest boundary

This result does not claim a production update channel. Remaining external
and platform gates are:

- offline/protected production key custody;
- Authenticode-signed MSIX/App Installer packages;
- Developer ID signing, notarization, and Sparkle EdDSA appcast;
- signed apt and FreeBSD pkg repositories;
- release AAB and TestFlight/App Store products;
- real upgrade, interruption, downgrade, and rollback transactions.
- an independently witnessed offline production-root bootstrap/rotation
  ceremony.
- immutable GitHub release-tag repository rules.
- a protected scheduled production snapshot/timestamp signer and atomic
  publisher; the daily public workflow proves renewal liveness only.

No unsigned alpha metadata is accepted by an Orkela runtime as update
authority.
