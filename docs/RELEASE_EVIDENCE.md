# Orkela Release Evidence Protocol

Status: **ACCEPTED**

This protocol applies to every Orkela release that changes decoding, playback,
media-session behavior, packaging, file association, or visible UI behavior.

## Pinned inputs

- short speech: the public LibriSpeech `1272-128104-0000` Resonith artifact;
- long music: the complete 400.773-second Mozart *Die Zauberflöte* overture
  Resonith artifact;
- malformed and truncated variants derived from the short input.

The report records input filenames, complete sizes, and SHA-256 hashes.

## Required checks

1. Build Windows x64 Release with warnings as errors.
2. Verify Resonith Core preflight and native decode on short and long inputs.
3. Confirm that long decode runs off the Windows message thread and that the
   window remains responsive throughout.
4. Exercise play, pause, stop, seek, skip, volume, end-of-stream, reopen, and
   drag-and-drop.
5. Observe advancing playback position, waveform cursor, and PCM-derived
   spectrum.
6. Reject malformed and truncated input before audio-device playback.
7. Verify `.resonith`, `.scenelith`, and `.orka` current-user associations.
8. Inspect high-DPI, constrained-work-area, and minimum-window layouts.
9. Confirm that direct Resonith playback creates no WAV intermediary.

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
