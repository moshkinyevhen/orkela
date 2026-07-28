# Android 17 Software-Renderer Compositor Gate

Date: 2026-07-28

Candidate: `0.3.0-alpha.6`

Initial source: `68580b576a44cadbff0e29d95b91294098dc3cec`

Archive-matrix source: `1e8d164f5b2231fb5c10d36bfb0f48f4775a698a`

Vulkan-composition source: `414b4ed45d5bc0fb3fdb47c882991630dda2ca87`

GitHub Actions runs:
[`30360265886`](https://github.com/moshkinyevhen/orkela/actions/runs/30360265886)
and
[`30363213810`](https://github.com/moshkinyevhen/orkela/actions/runs/30363213810),
followed by
[`30365673867`](https://github.com/moshkinyevhen/orkela/actions/runs/30365673867)

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

## Vulkan-composition result

Run `30365673867` used one source SHA, run/attempt, Ubuntu image
`ubuntu24/20260720.247.2`, kernel `6.17.0-1020-azure`, x86-64 machine contract,
and usable KVM across all four hosted VMs.

| Cell | Requested/effective feature | Boot | Compositor evidence | Result |
|---|---:|---:|---|---|
| SwiftShader control | 0 / 0 | yes | 67 crash signatures, 26 target signatures, 22 PID changes, 9/24 healthy, 0/4 PNG | exact control failure |
| SwiftShader | 1 / 1 | no | framebuffer/compositor initialization error `-2` before ADB | rejected |
| swangle/SwiftShader | 1 / 1 | no | framebuffer/compositor initialization error `-2` before ADB | rejected |
| swangle/lavapipe | 1 / 1 | no | framebuffer/compositor initialization error `-2` before ADB | rejected |

The command-line feature was therefore supported and became effective in every
candidate; this was not a silent feature fallback. Each feature-on log
auto-enabled GuestAngle, selected its allowlisted renderer tuple, attempted the
X11/Vulkan compositor path, and then reported:

```text
Failed to initialize the compositor.
Failed to initialize FrameBuffer().
Could not start renderer! (Error: -2)
```

The feature-on route avoids the later guest SurfaceFlinger crash only by
failing earlier during host framebuffer initialization, so it is not a
stage-one candidate. The assessment job correctly failed closed. Its first
reducer version stopped on the absent post-boot fingerprint instead of writing
a consolidated rejection file; the four per-cell artifacts remain complete
and authoritative. The corrected reducer now separates host provenance from
guest runtime conformance. It records a provenance-valid pre-boot failure as
`REJECTED`, validates the normalized startup-evidence file against its recorded
SHA-256 and line count, removes any stale promotion file before reduction, and
never makes a pre-boot cell promotion-eligible.

## Explicit Vulkan backend micro-probe

The previous result is not evidence that an X server is the missing variable.
Its effective feature tuple was `Vulkan=0`,
`VulkanNativeSwapchain=1`, and `GuestVulkanOnly=1`; the host never initialized
VkEmulation or `CompositorVk`. An Xvfb experiment would therefore change a
downstream display mechanism before proving that the Vulkan composition
backend exists.

The next and only Linux diagnostic cell preserves the exact 37.2.1 archive,
SwiftShader renderer, Android 17 guest hashes, GitHub host identity, and
headless execution, while requesting:

```text
-feature Vulkan,VulkanNativeSwapchain
```

This is evidence-only and cannot emit a promotion identity. The Linux route
may continue only when the log proves effective `Vulkan=1` and
`VulkanNativeSwapchain=1`, initializes VkEmulation, reports both Vulkan
composition flags, selects `CompositorVk`, contains no host compositor
initialization error, and reaches ADB. A feature downgrade, the same
framebuffer error, or failure to reach ADB rejects this route. Xvfb becomes a
causal follow-up only if Vulkan initialization succeeds and the remaining
failure explicitly names an X11/XCB surface or display connection.

### Completed explicit-backend run

[GitHub run 30369153246](https://github.com/moshkinyevhen/orkela/actions/runs/30369153246)
resolved the previously missing coordinate:

- effective `Vulkan=1`, `VulkanNativeSwapchain=1`, and
  `GuestVulkanOnly=1` were singular;
- VkEmulation initialized, both Vulkan composition flags were true, and
  `CompositorVk` performed composition;
- no host framebuffer or compositor initialization error occurred;
- the Emulator process remained alive and ADB reached `device` state;
- `sys.boot_completed` did not become `1`.

The failed boot was a guest failure, not a backend or ADB failure. Raw logcat
contains 58 structurally valid SurfaceFlinger fatal-signal records. The
bounded parser links 51 of them to complete same-debuggerd tombstone episodes;
all 51 contain the causal stack through `libGLESv2_angle.so` and
`vulkan.ranchu.so::ResourceTracker::createCoherentMemory`. It rejects
truncated episodes instead of counting partial evidence. Raw getprop
simultaneously reports `sys.init.updatable_crashing=1` and
`sys.init.updatable_crashing_process_name=surfaceflinger`.

The original producer wrote `failure_class=none` because it captured logcat
only in its cleanup trap, after writing `PROBE-RESULT.json`, and treated
`boot_completed` as a surrogate for ADB reachability. The corrected evidence
schema records `adb_reached` independently, adds `boot-completion-timeout`,
captures logcat and getprop before classification, SHA-256 links both raw
files, and requires the assessor to recompute complete tombstone episodes.
Replaying the immutable run evidence through that fail-closed assessor yields:

```text
BACKEND_REACHED_ADB_GUEST_BOOT_REJECTED
```

This status remains non-promotable. It preserves the proved host backend while
rejecting the crashing guest route.

### Causal GuestAngle A/B experiment

The R-185 audit rejected `Vulkan=1, VulkanNativeSwapchain=0` as the next
primary experiment. Gfxstream selects Vulkan composition when
`GuestVulkanOnly || VulkanNativeSwapchain`; disabling both guest Vulkan-only
mode and the native swapchain would also remove `CompositorVk`, confounding the
experiment.

The next exact pair therefore retains the completed tuple as its baseline and
changes one coordinate in the candidate:

```text
-feature Vulkan,VulkanNativeSwapchain,-GuestAngle
```

Android Emulator 37.2.1 explicitly logged that
`VulkanNativeSwapchain` auto-enabled `GuestAngle`. A command-line feature
override is therefore the narrowest tested intervention. Baseline and
candidate run sequentially in one GitHub job on the same VM, kernel boot ID,
runner image, KVM device, source revision, Emulator archive, and Android guest.
They use separate `ANDROID_USER_HOME`, AVD directories, and AVD names. A joint
SHA-linked reducer rejects the causal claim if either host identity differs or
if any configured coordinate other than GuestAngle differs.

The candidate is accepted only if the Emulator log proves the exact
`Vulkan,VulkanNativeSwapchain,-GuestAngle` override, one explicit
`GuestAngle=disabled` marker, no auto-enable marker, and effective
`Vulkan=1`, `VulkanNativeSwapchain=1`, `GuestVulkanOnly=0`. VkEmulation,
`useVulkanComposition=true`, `useVulkanNativeSwapchain=true`, and
`CompositorVk` must remain present. Raw getprop must independently show
`sys.boot_completed=1`, no `ro.boot.hardwareegl` override, and effective
`ro.hardware.egl=emulation`. A boot-completed candidate is still rejected if
raw evidence contains any SurfaceFlinger abort tombstone or fatal signal, any
target coherent-memory/ANGLE episode, any MESA virtual-memory fatal, or a
final updatable-crashing SurfaceFlinger state. Any mixed feature state, changed
host identity, missing marker, result/property contradiction, or a boot that
recovers while still crashing is an evidence rejection, not a fallback.

The evidence parser accepts only bounded `logcat -v threadtime` episodes. It
requires the linked SurfaceFlinger `F libc` PID/TID, a single-debuggerd
`F DEBUG` tombstone, and the complete target stack. Hashing and parsing use
the same immutable read of each raw file, preventing a hash/parse TOCTOU.

### Completed same-host GuestAngle result

[GitHub run 30374223297](https://github.com/moshkinyevhen/orkela/actions/runs/30374223297)
completed successfully from source
`5dfb64af5db86f5a838d7dfe77ea9ed373fb2dc8`. The baseline and candidate used
the same GitHub runner, run/attempt, Ubuntu image
`ubuntu24/20260720.247.2`, kernel `6.17.0-1020-azure`, KVM device, and kernel
boot ID `6d57a5ff-206a-489c-9749-be8e65b737bd`. Their Android user homes,
AVD homes, and AVD names were distinct.

| Evidence | Baseline | `-GuestAngle` candidate |
|---|---:|---:|
| Effective `GuestVulkanOnly` | 1 | 0 |
| Created SurfaceFlinger ANGLE VkInstances | 58 | 0 |
| SurfaceFlinger fatal signals | 58 | 0 |
| Complete bounded tombstones | 40 | 0 |
| Target coherent-memory/ANGLE tombstones | 40 | 0 |
| `sys.boot_completed` | empty | 1 |
| `ro.boot.hardwareegl` | `angle` | empty |
| `ro.hardware.egl` | `angle` | `emulation` |
| Clean guest-boot predicate | false | true |
| Cell status | `BACKEND_REACHED_ADB_GUEST_BOOT_REJECTED` | `BACKEND_REACHED_ADB_BOOT_COMPLETED` |

Both cells retained effective `Vulkan=1`,
`VulkanNativeSwapchain=1`, VkEmulation,
`useVulkanComposition=true`, `useVulkanNativeSwapchain=true`, and
`CompositorVk`, with no host compositor initialization error. The joint
assessment therefore produced:

```text
GUEST_ANGLE_OFF_BOOT_RECOVERY_ON_SAME_HOST
```

The downloaded artifact was independently reprocessed locally with the same
assessor and reproduced the joint status. This proves the bounded
startup/backend correction on this exact Linux-hosted Emulator identity. It
does not yet promote an APK, claim runtime soak stability, or release
`0.3.0-alpha.6`; those remain separate cold-boot, exact-APK, playback, and
packaging gates.

The source basis for this experiment is the
[AEMU feature catalog](https://android.googlesource.com/platform/external/qemu/+/emu-master-dev/android/data/advancedFeatures.ini),
[AEMU OpenGLES feature mapping](https://android.googlesource.com/platform/external/qemu/+/emu-master-dev/android/android-emu/android/opengles.cpp),
and [Gfxstream FrameBuffer selection](https://android.googlesource.com/platform/hardware/google/gfxstream/+/refs/heads/main/host/FrameBuffer.cpp).

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

## Exact-APK attempt and corrected root cause

[GitHub run 30396131139](https://github.com/moshkinyevhen/orkela/actions/runs/30396131139)
invalidated the earlier GuestAngle-only correction before release. The API 26
application gate passed, but the first Android 17 4-KiB cold boot entered a
repeatable SurfaceFlinger `RegionSampling` abort loop. The complete tombstone
ended in `GoldfishMapper::readFromHost` with:

```text
Assertion failed: !rcEnc->featureInfo()->hasReadColorBufferDma
```

The assertion means that `hasReadColorBufferDma` was false, not that DMA was
enabled incorrectly. Android 17's Goldfish mapper then has no non-DMA fallback.
The matching Android 17 gfxstream host advertises this capability only when
both `GlDirectMem` and `HasSharedSlotsHostMemoryAllocator` are enabled.

The pinned Emulator log proved the exact mismatch:

```text
API level: 3
gfxstreamFeature:GlDma = 1
gfxstreamFeature:GlDirectMem = 0
gfxstreamFeature:HasSharedSlotsHostMemoryAllocator = 0
```

The official image metadata is `AndroidVersion.ApiLevel=37.0`, while the
pinned host interpreted it as API 3 and consequently disabled API-gated memory
features. Disabling GLDMA would invert the source requirement and is explicitly
forbidden.

The next evidence profile therefore keeps guest bytes and GLDMA unchanged and
requests:

```text
-gpu swiftshader
-feature GLDirectMem,HasSharedSlotsHostMemoryAllocator,-GuestAngle,-Vulkan,-VulkanNativeSwapchain
```

Before promotion, a same-host causal A/B must reproduce the RegionSampling
failure with both prerequisites disabled and eliminate it with both enabled.
The positive cell must survive 24 observations over 120 seconds with one
SurfaceFlinger PID, four valid screenshots, stock luma, enforcing SELinux, and
zero crash signatures. The full 3+3 cold-boot and exact-APK gates remain
mandatory afterward. The host-parsed API level is now a contracted coordinate;
the API-3 parser defect remains a separate compatibility audit rather than
being hidden by a green boot.

Primary source basis:

- [Android 17 Goldfish mapper](https://android.googlesource.com/device/generic/goldfish/+/refs/tags/android-17.0.0_r1/hals/gralloc/mapper.cpp)
- [Android 17 gfxstream render-control capability](https://android.googlesource.com/platform/hardware/google/gfxstream/+/refs/tags/android-17.0.0_r1/host/render_control.cpp)
- [AEMU API-gated graphics selection](https://android.googlesource.com/platform/external/qemu/+/emu-master-dev/android-qemu2-glue/main.cpp)

## ReadColorBufferDMA causal result

[GitHub run 30399094666](https://github.com/moshkinyevhen/orkela/actions/runs/30399094666)
completed the deliberately minimal same-host intervention on commit
`cfe08f3ccade873b9bf9be9fbd3b182679c086d4`. Both cells used the same runner,
kernel boot ID, verified Emulator 37.2.1 archive, verified Android 17 4-KiB
guest bytes, SwiftShader renderer, Vulkan-disabled route, enforcing SELinux,
and unmodified luma policy. The only causal coordinate was the pair required
to advertise ReadColorBufferDMA:

| Evidence | Prerequisites off | Prerequisites on |
| --- | ---: | ---: |
| Effective `GlDirectMem` | 0 | 1 |
| Effective shared host slots | 0 | 1 |
| Effective `GlDma` / `GlDma2` | 1 / 0 | 1 / 0 |
| Target RegionSampling crash signatures | 25 | 0 |
| SurfaceFlinger PID changes | 22 | 0 |
| Healthy soak observations | 8 / 24 | 24 / 24 |
| Valid screenshots | 0 / 4 | 4 / 4 |
| Final `updatable_crashing` process | `surfaceflinger` | empty |

The assessor emitted
`READ_COLOR_BUFFER_DMA_CAUSAL_AB_PASSED`, retained
`promotion_eligible=false`, and recorded the host parser decision as API 3.
The downloaded raw artifact was independently reprocessed on Windows; its
assessment JSON was semantically identical to the GitHub-produced assessment
(the byte difference was CRLF versus LF line endings only).

This closes the causal renderer question without expanding the renderer
matrix. Public promotion still requires the one contracted 3x4-KiB +
3x16-KiB cold-boot gate and exact-APK runtime decode on both Android 17 page
sizes.

## First full cold-promotion execution

Attempt 2 of
[GitHub run 30399084868](https://github.com/moshkinyevhen/orkela/actions/runs/30399084868)
passed API 26 and all six required Android 17 cold boots:

- three fresh 4-KiB guests;
- three fresh 16-KiB guests;
- 24/24 healthy observations, one SurfaceFlinger lifetime, four valid
  screenshots, and zero target crash signatures for every cold boot.

The first reducer invocation rejected the evidence because the gate had
hashed `logs/emulator.log` before its EXIT cleanup appended normal Emulator
shutdown lines. Every one of the six cold gates and the API-26 runtime gate
showed this same single-file mismatch. After downloading the complete
artifact, recomputing only the seven raw manifests over the now-closed logs,
and updating their manifest digests, the corrected reducer emitted:

```text
ANDROID17_COLD_PROMOTION_PASSED
```

The source gate now stops and reaps the Emulator, records its commanded exit,
checks that the closed log hash remains stable, and only then writes the raw
manifest. The reducer also now validates the actual partial order of startup
phases rather than requiring a semantically meaningless total order among
effective feature-state log lines. These infrastructure corrections must pass
on the committed source before exact-APK promotion and packaging continue.
