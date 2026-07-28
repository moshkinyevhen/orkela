# Instructions for Orkela agents

## Product scope

**Orkela** is a standalone media player, pronounced `or-ke-la`. Its canonical
synchronized-package extension is `.orka`. It directly plays `.resonith`
through Resonith Core and will play `.scenelith` through SceneLith Core when
that decoder exists. It must never disguise WAV export or an external
transcoder as native codec playback.

Orkela is a separate product and repository from the Resonith audio codec and
the SceneLith video codec. Decoder behavior remains normative in the codec
repositories; Orkela consumes their public APIs.

## Engineering contract

- C++23 is the implementation language for the portable core and native
  platform adapters. Use only the mobile-safe subset documented in
  `docs/PLATFORM_ARCHITECTURE.md`.
- Keep platform code behind narrow adapters so Windows x64/ARM64, Android,
  iOS, macOS, Linux, FreeBSD, and embedded front ends can reuse the
  media/session, visual-analysis, and localization layers.
- Prefer operating-system APIs over a large mandatory GUI framework.
- Treat input files as untrusted. Validate sizes and decoder preflight before
  allocating or writing PCM.
- Audio callbacks must not allocate, lock, log, or perform file I/O.
- Public code identifiers, comments, documentation, commits, and repository
  metadata are English only. Localized product-string resources may contain
  the explicitly supported interface languages; their identifiers and
  translator notes remain English.
- `.resonith`, `.scenelith`, and `.orka` are canonical public extensions.
  `.lps4` and `.lps5` are accepted only as research compatibility inputs.

## Source-comment contract

- Comment intent, ownership, concurrency, resource ceilings, state
  transitions, and non-obvious API constraints.
- Use a few named phases in complex functions when this improves debugging.
- Do not narrate syntax, comment every line, or keep dead code in comments.
- A comment that no longer matches behavior is a defect.

## Validation

Before publishing a change:

1. build Windows x64/ARM64, Android ARM64/x86-64, iOS device/simulator,
   macOS ARM64/x86-64, Ubuntu, Debian, and FreeBSD with warnings as errors;
   Android must compile and target API 37 while retaining `minSdk` 26;
2. run the decoder smoke test against a real LPS5 artifact;
3. verify playback reads LPS5 directly and creates no WAV;
4. verify malformed input fails before playback;
5. verify public identifiers, comments, and documentation remain English;
   Cyrillic, CJK, and other non-English text is permitted only in the
   centralized localization catalog and localization-specific test evidence;
6. verify the repository contains no secrets or machine-specific paths;
7. verify the pinned short LibriSpeech and full-length Mozart `.resonith`
   files, including responsive background decode, playback, seeking, timeline,
   spectrum, and high-DPI rendering;
8. run the real Windows audio-device gate on compact Truth, raw MFT1, and
   composite RSC1 (`MFT1 + MRI1`); a build is not releasable unless playback
   position advances and measured full-Mozart load/start remain below the
   recorded two-second reference ceiling;
9. publish the QA report with the exact Orkela version, commit, executable
   hash, input hashes, and pass/fail result;
10. run the same exact Android APK and instrumentation APK on API 26 and API
    37 with 4 KiB memory pages and on API 37 with 16 KiB pages; every runtime
    must reproduce the pinned PCM16 SHA-256 and retain no WAV or decoded-PCM
    filesystem intermediary;
11. update `VERSION` and the English `CHANGELOG.md`; local artifacts and the
   corresponding GitHub release must carry matching versions and hashes.
12. verify automatic system-language selection and the persistent manual
    Settings override for English, German, Spanish, Italian, Japanese,
    Korean, Simplified Chinese, Russian, and Ukrainian;
13. exercise Field, Spectrum, Wave, and accumulating multiresolution History
    on every application platform; UI tiles may differ, but the C++23
    analysis dimensions and history-compaction semantics must match.
14. package native installers separately from portable archives and generate
    the deterministic signed-update metadata described in
    `docs/UPDATE_AND_PACKAGING.md`; never label an unsigned CI archive as an
    automatic update.
