# Orkela media-name contract

Status: **ACCEPTED**
Date: 2026-07-26

## Products and pronunciation

- **Resonith** (`re-zo-nit`) is the standalone audio codec.
- **SceneLith** (`seen-lit`) is the standalone visual codec.
- **Orkela** (`or-ke-la`) is the standalone player and media orchestrator.

## Canonical extensions

| Extension | Owner | Role |
|---|---|---|
| `.resonith` | Resonith | Independent audio bitstream |
| `.scenelith` | SceneLith | Independent visual bitstream |
| `.orka` | Orkela / SceneLith AV Bridge | Synchronized media package |

An `.orka` package may share timeline, entity, trajectory, and presentation
metadata. It MUST keep the contained Resonith and SceneLith Truth streams
independently decodable and MUST NOT merge their reference graphs.

The `.lps`, `.lps4`, `.lps5`, and `.rsc` suffixes are research compatibility
identifiers. They are not stable public media extensions.

MIME types, FourCC values, codec strings, and the `.orka` binary layout remain
unassigned until registry and conformance gates pass.
