# Android 17 SwiftShader Compositor Gate

Date: 2026-07-28  
Candidate: `0.3.0-alpha.6`  
System images: Android 17 build `CE2A.260420.019`, 4 KiB and 16 KiB x86-64  
Emulator: `36.6.11`  
Status: **LOCAL 4-KIB/16-KIB CAUSAL GATE PASS; GITHUB LINUX GATE PENDING**

## Failure mechanism

The generic `-gpu software` selection chose a mixed host renderer on the
GitHub Linux runner:

- GLES: `swangle`;
- Vulkan: `lavapipe`.

SurfaceFlinger then aborted in `RegionSamplingThread` approximately every
30–31 seconds:

```text
GoldfishMapper::readFromHost
Assertion failed: !rcEnc->featureInfo()->hasReadColorBufferDma
```

Every compositor restart also restarted dependent Android services. The
package and mount Binder services temporarily disappeared and `emulated;0`
cycled from `mounted` through `checking`. Extending boot or service timeouts
could therefore never make this configuration stable.

Disabling the visible `GLDMA` and `GLDMA2` host feature flags was rejected as a
fix. The resulting Emulator log reported those flags as disabled, but the
guest mapper still observed the readback capability and crashed. This proved
that feature-log state was not an adequate conformance claim.

## Selected correction

Android 17 gates now request the official unified software renderer:

```text
-gpu swiftshader
```

No Android guest property, root command, SurfaceFlinger restart, luma-sampling
setting, SELinux mode, or Emulator feature flag is changed. The gate requires
the effective Emulator log to prove SwiftShader was selected for both GLES and
Vulkan.

This follows Android's current documented software-renderer modes and keeps the
problematic RegionSampling/readback path enabled:

- [Configure graphics acceleration](https://developer.android.com/studio/run/emulator-acceleration#command-gpu)
- [Android Emulator graphics troubleshooting](https://developer.android.com/studio/run/emulator-troubleshooting#graphics-issues)
- [AOSP host graphics feature mapping](https://android.googlesource.com/platform/external/qemu/+/emu-master-dev/android/android-emu/android/opengles.cpp)

## Strengthened gate

After the system first becomes ready, every API 37 run must pass:

1. exact image fingerprint, build ID, API, SELinux, and page-size checks;
2. exact SwiftShader request/effective-renderer log checks;
3. stock/default enabled luma sampling;
4. zero pre-existing target crash signatures;
5. at least 120 measured seconds of compositor soak;
6. 24 healthy observations of package, SurfaceFlinger, mount, and storage
   state;
7. one invariant SurfaceFlinger PID;
8. four screenshots spread across the soak;
9. complete PNG chunk bounds, CRC, IHDR, IDAT, terminal IEND, and no-tail
   validation;
10. decoded RGB/RGBA pixel diversity and luminance-span validation;
11. zero target crash signatures after the soak and after the application
    decode/UI/AudioTrack gate.

The player gate still makes no audibility claim for a virtual audio device.

## Local causal results

Both tests used a cold boot and pure SwiftShader. The physical Android device
was not addressed and remained screen-off.

| Runtime | Kernel page size | SurfaceFlinger | Target crash hits | PNGs | Sampled RGB classes | Luma span |
|---|---:|---|---:|---:|---:|---:|
| Android 17 4 KiB | 4,096 | PID `500`, invariant | 0 | 4/4 | 856–1,011 | 225–245 |
| Android 17 16 KiB | 16,384 | PID `497`, invariant | 0 | 4/4 | 875–1,010 | 235–245 |

All package/SurfaceFlinger/mount checks remained found and both `private` and
`emulated;0` volumes remained mounted throughout both local soaks.

## Publication boundary

These local Windows-hosted causal tests validate the renderer hypothesis but
do not replace the pinned GitHub Ubuntu runner. Release promotion remains
blocked until the exact APK pair passes the full API 26, API 37/4-KiB, and API
37/16-KiB workflow from one immutable source revision.
