# Instructions for Orkela agents

## Product scope

**Orkela** is a standalone media player. Its first milestone is a small native
Windows application that plays real Resonith LPS5 files through Resonith Core.
It must never disguise WAV export or an external transcoder as native playback.

Orkela is a separate product and repository from the Resonith audio codec and
the SceneLith video codec. Decoder behavior remains normative in the codec
repositories; Orkela consumes their public APIs.

## Engineering contract

- C++20 is the implementation language for the portable core and native UI.
- Keep platform code behind narrow adapters so Android, iOS, Linux, macOS, and
  embedded front ends can reuse the media/session layer.
- Prefer operating-system APIs over a large mandatory GUI framework.
- Treat input files as untrusted. Validate sizes and decoder preflight before
  allocating or writing PCM.
- Audio callbacks must not allocate, lock, log, or perform file I/O.
- Public code, comments, documentation, commits, and repository metadata are
  English only.

## Source-comment contract

- Comment intent, ownership, concurrency, resource ceilings, state
  transitions, and non-obvious API constraints.
- Use a few named phases in complex functions when this improves debugging.
- Do not narrate syntax, comment every line, or keep dead code in comments.
- A comment that no longer matches behavior is a defect.

## Validation

Before publishing a change:

1. build Windows x64 with warnings as errors;
2. run the decoder smoke test against a real LPS5 artifact;
3. verify playback reads LPS5 directly and creates no WAV;
4. verify malformed input fails before playback;
5. verify no Cyrillic text is tracked;
6. verify the repository contains no secrets or machine-specific paths.
