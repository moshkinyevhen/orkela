# Orkela Interface Localization Contract

Status: **ACCEPTED**

## Required languages

Every Orkela application shell must provide the following interface languages
from the shared C++23 catalog:

| Stable tag | Display name |
|---|---|
| `en` | English |
| `de` | Deutsch |
| `es` | Español |
| `it` | Italiano |
| `ja` | 日本語 |
| `ko` | 한국어 |
| `zh-Hans` | 简体中文 |
| `ru` | Русский |
| `uk` | Українська |

An unknown or unsupported locale falls back to English. Codec names, public
extensions, sample rates, channel counts, and other invariant technical terms
are not translated.

## Selection behavior

The default preference is **System default**. At application start, the native
shell supplies the operating system's preferred BCP-47 locale to the shared
catalog:

- Windows uses the current user's default UI language;
- Android uses the process default `Locale`;
- iOS and macOS use the first preferred `NSLocale` language;
- Ubuntu, Debian, and FreeBSD use the first GLib language preference.

The user may override this only from **Settings → Interface → Language**.
Language selection is not a permanent top-level switch or transport control.
The override is stored as presentation state outside `.resonith`,
`.scenelith`, and `.orka`; it can never change reconstructed media.

Choosing **System default** removes the override rather than copying the
current locale. A later operating-system language change therefore takes
effect on the next application start. A manual selection remains stable until
the user changes it.

## Catalog and fallback rules

`orkela::text_id` is the stable platform-independent string identity.
`orkela::localized_text()` is the single source of product copy for all
native shells. Platform resource identifiers remain English. A missing
translation returns the corresponding English string; an empty visible label
is a conformance failure.

The catalog test must enumerate every `text_id` in every supported language.
Platform package gates additionally prove that the native bridge can request
all entries without an exception or invalid UTF-8. Font selection must retain
glyph coverage for Latin, Cyrillic, Japanese, Korean, and Simplified Chinese.

## Accessibility and layout

Translation must not be implemented by rasterizing text. Native text widgets
or the operating system's shaping stack remain mandatory for accessibility,
dynamic type, bidirectional safety, and CJK rendering. Layouts must tolerate
German and Ukrainian expansion without clipping and must not force uppercase
transformations that damage locale-specific text.

The language autonym is always shown in its own script. Settings remain usable
when the currently selected language is unfamiliar because every choice is an
autonym and the first entry always means system default.
