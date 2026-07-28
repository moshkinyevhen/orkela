package org.scenelith.orkela;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.os.Bundle;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/**
 * Proves that the APK's exact JNI and Resonith Core decode the pinned asset.
 *
 * The JSON marker is test evidence, not a player cache. Production execution
 * never creates it because this class ships only in the instrumentation APK.
 */
public final class NativeDecodeInstrumentation extends Instrumentation {
    private static final int EXPECTED_SAMPLE_RATE = 44100;
    private static final int EXPECTED_CHANNELS = 2;
    private static final int EXPECTED_FRAMES = 352800;
    private static final String EXPECTED_PCM_SHA256 =
        "3cfcae4996a08976f42ec83744ea0130935ca53d83b37129c001581697618618";

    @Override
    public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        start();
    }

    @Override
    public void onStart() {
        super.onStart();
        Bundle result = new Bundle();
        try {
            runPinnedDecode();
            result.putString("orkela.result", "pass");
            finish(Activity.RESULT_OK, result);
        } catch (Throwable failure) {
            result.putString("orkela.result", "fail");
            result.putString("orkela.error", failure.toString());
            writeFailureMarker(failure.toString());
            finish(Activity.RESULT_CANCELED, result);
        }
    }

    private void runPinnedDecode() throws Exception {
        verifyLocalizationContract();
        Context context = getTargetContext();
        byte[] payload;
        try (InputStream input =
                context.getAssets().open("emotional-piano.resonith")) {
            payload = readAll(input);
        }

        long handle = MainActivity.nativeOpen(payload);
        require(handle != 0L, "native decoder handle is null");
        try {
            int sampleRate = MainActivity.nativeSampleRate(handle);
            int channels = MainActivity.nativeChannels(handle);
            int frameCount = MainActivity.nativeFrameCount(handle);
            int packetElements = MainActivity.nativePacketElements(handle);
            require(sampleRate == EXPECTED_SAMPLE_RATE, "sample-rate mismatch");
            require(channels == EXPECTED_CHANNELS, "channel-count mismatch");
            require(frameCount == EXPECTED_FRAMES, "frame-count mismatch");
            require(packetElements > 0, "packet size is not positive");

            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            short[] packet = new short[packetElements];
            byte[] littleEndian = new byte[packetElements * 2];
            int decodedElements = 0;
            for (;;) {
                int elements = MainActivity.nativeRead(handle, packet);
                if (elements == 0) {
                    break;
                }
                require(elements <= packet.length, "packet exceeds buffer");
                for (int index = 0; index < elements; ++index) {
                    int bits = packet[index] & 0xffff;
                    littleEndian[index * 2] = (byte) bits;
                    littleEndian[index * 2 + 1] = (byte) (bits >>> 8);
                }
                digest.update(littleEndian, 0, elements * 2);
                decodedElements = Math.addExact(decodedElements, elements);
            }

            require(
                decodedElements
                    == Math.multiplyExact(EXPECTED_FRAMES, EXPECTED_CHANNELS),
                "decoded element count mismatch"
            );
            String pcmSha256 = lowerHex(digest.digest());
            require(
                EXPECTED_PCM_SHA256.equals(pcmSha256),
                "decoded PCM fingerprint mismatch"
            );
            writePassMarker(
                context,
                sampleRate,
                channels,
                frameCount,
                pcmSha256
            );
        } finally {
            MainActivity.nativeClose(handle);
        }
    }

    private static void verifyLocalizationContract() {
        String[] localeTags = {
            "en-US",
            "de-DE",
            "es-ES",
            "it-IT",
            "ja-JP",
            "ko-KR",
            "zh-CN",
            "ru-RU",
            "uk-UA",
        };
        for (String localeTag : localeTags) {
            for (int textId = 0; textId < 57; ++textId) {
                String value = MainActivity.nativeText(localeTag, textId);
                require(
                    value != null && !value.isEmpty(),
                    "empty localized text for " + localeTag
                );
            }
        }
        require(
            "Einstellungen".equals(MainActivity.nativeText("de-DE", 24)),
            "German settings translation mismatch"
        );
        require(
            "設定".equals(MainActivity.nativeText("ja-JP", 24)),
            "Japanese settings translation mismatch"
        );
        require(
            "Налаштування".equals(MainActivity.nativeText("uk-UA", 24)),
            "Ukrainian settings translation mismatch"
        );
    }

    private static byte[] readAll(InputStream input) throws Exception {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buffer = new byte[64 * 1024];
        for (;;) {
            int count = input.read(buffer);
            if (count < 0) {
                return output.toByteArray();
            }
            output.write(buffer, 0, count);
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static String lowerHex(byte[] bytes) {
        char[] alphabet = "0123456789abcdef".toCharArray();
        char[] output = new char[bytes.length * 2];
        for (int index = 0; index < bytes.length; ++index) {
            int value = bytes[index] & 0xff;
            output[index * 2] = alphabet[value >>> 4];
            output[index * 2 + 1] = alphabet[value & 0x0f];
        }
        return new String(output);
    }

    private static void writePassMarker(
        Context context,
        int sampleRate,
        int channels,
        int frames,
        String pcmSha256
    ) throws Exception {
        String json = "{\n"
            + "  \"schema\": 1,\n"
            + "  \"status\": \"pass\",\n"
            + "  \"sample_rate\": " + sampleRate + ",\n"
            + "  \"channels\": " + channels + ",\n"
            + "  \"frames\": " + frames + ",\n"
            + "  \"pcm16_sha256\": \"" + pcmSha256 + "\"\n"
            + "}\n";
        writeMarker(context, json);
    }

    private void writeFailureMarker(String error) {
        String safe = error.replace("\\", "\\\\").replace("\"", "\\\"");
        String json = "{\n"
            + "  \"schema\": 1,\n"
            + "  \"status\": \"fail\",\n"
            + "  \"error\": \"" + safe + "\"\n"
            + "}\n";
        try {
            writeMarker(getTargetContext(), json);
        } catch (Exception ignored) {
            // The instrumentation result still carries the primary failure.
        }
    }

    private static void writeMarker(Context context, String json)
            throws Exception {
        File marker = new File(
            context.getFilesDir(),
            "orkela-ci-smoke.json"
        );
        try (FileOutputStream output = new FileOutputStream(marker, false)) {
            output.write(json.getBytes(StandardCharsets.UTF_8));
        }
    }
}
