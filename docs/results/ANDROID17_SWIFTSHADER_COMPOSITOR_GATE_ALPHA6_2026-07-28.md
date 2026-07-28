# Android 17 Software-Renderer Compositor Gate

Date: 2026-07-28

Candidate: `0.3.0-alpha.6`

Initial source: `68580b576a44cadbff0e29d95b91294098dc3cec`

Archive-matrix source: `1e8d164f5b2231fb5c10d36bfb0f48f4775a698a`

GitHub Actions runs:
[`30360265886`](https://github.com/moshkinyevhen/orkela/actions/runs/30360265886)
and
[`30363213810`](https://github.com/moshkinyevhen/orkela/actions/runs/30363213810)

System image: Android 17 build `CE2A.260420.019`, 4 KiB x86-64

Emulator: `36.6.11.0`

Status: **GITHUB LINUX RENDERER MATRIX REJECTED; RELEASE GATE REMAINS BLOCKED**

## Scope

This was an isolated renderer probe. It installed no Orkela APK and makes no
application, audio, or release claim. Its purpose was to identify a stable,
deterministic software-renderer tuple before rerunning the much more expensive
exact-APK matrix.

The probe pinned the Android 17 guest fingerprint, Emulator archive, guest
payload hashes, loader dependency, runner, source revision, and artifact
identity. Every boot requested 4 KiB pages and preserved the stock Android
guest, SELinux enforcing mode, luma sampling, DMA features, and compositor.

## Failure mechanism

On this exact Linux-hosted Emulator pair, SurfaceFlinger repeatedly aborted in
`RegionSamplingThread`:

```text
GoldfishMapper::readFromHost
Assertion failed: !rcEnc->featureInfo()->hasReadColorBufferDma
```

Every compositor restart also restarted dependent Android services. Package,
mount, and storage state therefore became transiently unhealthy. Extending
boot or service timeouts cannot make this pair conformant.

Disabling visible DMA feature flags was previously rejected as a correction:
the guest mapper still observed the readback capability and crashed. No guest
property, root command, SurfaceFlinger restart, luma-sampling change, SELinux
change, or feature override is accepted by the gate.

## Exact GitHub results

Each matrix cell ran a 120-second soak with 24 service/PID observations and
four requested screenshots. A screenshot counted only after complete PNG
chunk-bound, CRC, IHDR, IDAT, IEND, decoded-dimension, pixel-diversity, and
luminance validation.

| Requested backend | Effective tuple | Healthy observations | PID changes | Crash signatures | Valid PNGs | Result |
|---|---|---:|---:|---:|---:|---|
| `swiftshader` | `swiftshader / swiftshader` | 7/24 | 22 | 74 | 0/4 | exact control crash |
| `lavapipe` | `swangle / lavapipe` | 0/24 | 22 | 144 | 0/4 | rejected |
| `swangle` | `swangle / swiftshader` | 0/24 | initial PID unavailable | 125 | 0/4 | rejected |
| `host` | `host / host` | 0/24 | n/a | n/a | 0/4 | diagnostic boot timeout |

The reducer correctly failed because the expected SwiftShader control failure
was reproduced but no deterministic candidate survived.

## Local contrast

The same Android 17 guest had previously completed 4 KiB and 16 KiB causal
soaks on a Windows host using pure SwiftShader, with invariant SurfaceFlinger,
zero target crash signatures, and four valid screenshots per runtime. Those
measurements remain useful host-specific evidence, but they do not override
the pinned GitHub Ubuntu failure.

SwiftShader is therefore no longer described as the selected GitHub
correction. It was a valid local hypothesis that the Linux evidence rejected
for Emulator `36.6.11.0`.

## Adjacent official Emulator archive gate

The completed second experiment kept the exact Android 17 guest and repeated
the control while varying only the official Emulator host package:

- `36.6.11.0` SwiftShader: required failing control;
- `37.1.10` with SwiftShader, swangle, and lavapipe;
- `37.2.1` with SwiftShader, swangle, and lavapipe.

Every archive is verified against Google's published SHA-1 and an independently
recorded SHA-256 and byte size before extraction. Every cell has a unique
identity, and a known failure is keyed by guest hash set, archive identity,
binary version, and effective renderer tuple. A newer package therefore remains
eligible even if it reports the same human-readable tuple.

| Revision | Channel at test date | Build | Official SHA-1 | Independent SHA-256 | Bytes |
|---|---|---:|---|---|---:|
| 36.6.11 | stable | 15507667 | `f8d8b83cf21a04966326eb1378bacda255f63b93` | `1eade4cf2df6ea8eeead4902c635897ba12aaa32aac4389eaae0fdb498a5b830` | 331,232,577 |
| 37.1.10 | beta | 15888535 | `489e57e560e310f9dfadf098951a713bf5651cd2` | `5ca4e61b25e4fe94224ef7af745e1c5d6901c2e957ccfb30b5f7fed3fad0e317` | 334,377,561 |
| 37.2.1 | canary | 15875889 | `1c39ceb4bca042b973344d252a051189d367ab83` | `3fb1f765795b284f864b9b3403d1c5e1ad0f317eb6522441460001ff660d3d7d` | 346,539,649 |

A newer package was eligible only if its complete exact-environment soak
succeeded. The independent reducer confirmed the failing control and emitted
an empty `stage1_candidates` list. It emitted no promotion identity.

| Emulator | Requested backend | Effective tuple | Healthy observations | PID changes | Crash signatures | Valid PNGs | Result |
|---|---|---|---:|---:|---:|---:|---|
| 36.6.11 | SwiftShader | SwiftShader / SwiftShader | 9/24 | 23 | 68 | 0/4 | required control failure reproduced |
| 37.1.10 | SwiftShader | SwiftShader / SwiftShader | 9/24 | 22 | 62 | 0/4 | rejected |
| 37.1.10 | swangle | swangle / SwiftShader | 2/24 | 24 | 187 | 0/4 | rejected |
| 37.1.10 | lavapipe | swangle / lavapipe | 1/24 | 24 | 157 | 0/4 | rejected |
| 37.2.1 | SwiftShader | SwiftShader / SwiftShader | 8/24 | 21 | 63 | 0/4 | rejected |
| 37.2.1 | swangle | swangle / SwiftShader | 1/24 | initial PID unavailable | 170 | 0/4 | rejected |
| 37.2.1 | lavapipe | swangle / lavapipe | 2/24 | initial PID unavailable | 124 | 0/4 | rejected |

All seven cells verified the requested archive, observed Emulator version,
Android guest payload hash set, guest fingerprint, 4 KiB page size, SELinux
enforcing state, default luma sampling, and positive display dimensions. Every
candidate then failed the same promotion requirements: one invariant
SurfaceFlinger lifetime, 24 healthy observations, zero matching compositor
crashes, and four valid screenshots.

This rejects the hypothesis that merely moving from stable Emulator 36.6.11 to
the adjacent 37.1.10 beta or 37.2.1 canary archive corrects the Linux-hosted
Android 17 compositor path. The failed assessment job is intentional
fail-closed behavior, not an infrastructure success falsely marked as a
release pass.

The next experiment must change one independently justified host-side
mechanism or runner family while preserving the exact stock Android 17 guest.
It must remain an isolated compositor probe until a stage-one candidate exists.
Only then may that exact identity advance to three cold 4 KiB and three cold
16 KiB boots with the same Orkela and instrumentation APK pair.

## Causal host-composition experiment

The R-185 red-team review approved one bounded follow-up. Emulator 36.4.9
introduced Vulkan composition and documents the
`VulkanNativeSwapchain` feature as a route that can disable host GL usage. That
is causally relevant because the observed abort occurs in the host GL/readback
path. It is not accepted as a correction merely because its command-line flag
was supplied: the complete Emulator log must contain exactly one effective
`gfxstreamFeature:VulkanNativeSwapchain` state with the requested value.

The same GitHub run contains exactly four Emulator 37.2.1 cells:

- SwiftShader with the feature off, as a fresh failing control;
- SwiftShader with the documented feature on;
- swangle/SwiftShader with the documented feature on;
- swangle/lavapipe with the documented feature on.

Because matrix cells use separate hosted VMs, every result records the GitHub
run, attempt, source SHA, runner OS/architecture, image OS/version, kernel,
machine architecture, and KVM access. The reducer rejects the complete matrix
if any of those identities differ.

No guest property, luma setting, DMA capability, SELinux mode, application, or
Android image changes between those cells. A feature-on cell is unsupported
and inconclusive if the effective state remains zero. It is rejected if the
effective state is one and the compositor still crashes. It becomes only a
stage-one candidate after 24/24 healthy observations, one invariant
SurfaceFlinger PID, zero crash signatures, and four valid screenshots.

The review rejected `swiftshader_indirect` because it is deprecated and the
measured renderer tuple already uses the indirect SwiftShader path. Android
Test Devices were also rejected for this gate because no official API 37 ATD
image exists and ATD is not a screenshot-rendering substitute. A pinned
`macos-26-intel` pure-SwiftShader probe remains an orthogonal fallback only if
the Linux Vulkan-composition hypothesis is unsupported or rejected.

This follows Android's documented renderer controls and emulator archive:

- [Configure graphics acceleration](https://developer.android.com/studio/run/emulator-acceleration#command-gpu)
- [Android Emulator graphics troubleshooting](https://developer.android.com/studio/run/emulator-troubleshooting#graphics-issues)
- [Android Emulator release notes](https://developer.android.com/studio/releases/emulator)
- [Android Emulator archive](https://developer.android.com/studio/emulator_archive)

## Publication boundary

Orkela `0.3.0-alpha.6` remains blocked until the same immutable APK pair passes
API 26, Android 17/4-KiB, and Android 17/16-KiB runtime gates. Neither the local
Windows result nor an isolated renderer candidate is sufficient for release
promotion.
