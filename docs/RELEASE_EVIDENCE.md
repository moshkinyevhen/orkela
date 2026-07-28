# Orkela Release Evidence Protocol

Status: **ACCEPTED**

This protocol applies to every Orkela release that changes decoding, playback,
media-session behavior, packaging, file association, or visible UI behavior.

## Pinned inputs

- short speech: the public LibriSpeech `1272-128104-0000` Resonith artifact;
- long music: the complete 400.773-second Mozart *Die Zauberflöte* overture
  Resonith artifact;
- composite music: the matching RSC1 `MFT1 + MRI1` Mozart candidate;
- raw typed MAF: the deterministic periodic MFT1 conformance artifact;
- malformed and truncated variants derived from the short input.

The report records input filenames, complete sizes, and SHA-256 hashes.

## Required checks

1. Build Windows x64 Release with warnings as errors.
2. Verify Resonith Core preflight and native decode on short and long inputs.
3. Run the native Windows audio-device gate. Playback position must advance
   for compact Truth, raw MFT1, and composite RSC1 without a WAV intermediary.
4. Record file-open and first-position latency. On the pinned reference system
   each must remain below two seconds for the complete Mozart anchors.
5. Exercise play, pause, stop, seek, skip, volume, end-of-stream, reopen, and
   drag-and-drop.
6. Observe advancing playback position, waveform cursor, and PCM-derived
   spectrum.
7. Reject malformed and truncated input before audio-device playback.
8. Verify the `.resonith` current-user association. Add `.scenelith` and
   `.orka` associations to this gate only when their native backends can
   actually open those formats; an installer must not claim unsupported
   playback.
9. Inspect high-DPI, constrained-work-area, and minimum-window layouts.
10. Confirm that direct Resonith playback creates no WAV intermediary.
11. Build one Android APK with compile/target API 37 and `minSdk` 26, then run
    that exact APK and its exact instrumentation APK on API 26 and API 37
    with 4 KiB pages and on API 37 with 16 KiB pages. Every boundary runtime
    must reproduce the pinned PCM16 SHA-256 and retain no WAV or decoded-PCM
    filesystem artifact.
12. Build the Windows x64 and ARM64 installers from the matching native
    payloads. On x64, install silently into an isolated current-user location,
    verify version/architecture/uninstall/ProgID state, uninstall, and require
    that the transaction leaves neither files nor Orkela registry keys.
13. On Ubuntu and Debian, build and inspect a native `.deb`, install it, launch
    the installed binary under a virtual display, remove it, and verify the
    executable is gone. Perform the corresponding native `.pkg` transaction on
    FreeBSD.
14. On each macOS architecture, verify the application bundle, ad-hoc sign it
    for CI execution, build a `productbuild` installer, and inspect the package
    payload. Developer ID signing and notarization remain mandatory before
    public promotion.

## Publication and versioning

The QA report identifies the semantic version, source commit, executable
SHA-256, Resonith Core commit, compiler, operating system, DPI, test inputs,
and each pass/fail result. Failed checks block release.

Every release updates `VERSION` and `CHANGELOG.md`. Local packages and the
matching GitHub release use the same version, source commit, filenames, and
SHA-256 hashes. Measured fixes and regressions are separated from planned
features and unverified claims.

Codec quality remains governed by the Resonith evidence protocol. Orkela QA
proves correct, responsive presentation of a decoded stream; it does not prove
that the codec is perceptually superior.
