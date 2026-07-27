package org.scenelith.orkela;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioTrack;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class MainActivity extends Activity {
    private static final int OPEN_DOCUMENT = 41;
    private static final int MAXIMUM_INPUT_BYTES = 64 * 1024 * 1024;

    static {
        System.loadLibrary("orkela_android");
    }

    private final Handler ui = new Handler(Looper.getMainLooper());
    private final ExecutorService inputExecutor =
        Executors.newSingleThreadExecutor();
    private final ExecutorService playbackExecutor =
        Executors.newSingleThreadExecutor();
    private final AtomicBoolean paused = new AtomicBoolean(false);
    private final AtomicInteger playbackGeneration = new AtomicInteger(0);

    private TextView title;
    private TextView metadata;
    private TextView status;
    private ProgressBar progress;
    private Button playButton;
    private byte[] selectedBytes;
    private String selectedName = "No stream selected";

    private static native long nativeOpen(byte[] input) throws IOException;
    private static native int nativeSampleRate(long handle);
    private static native int nativeChannels(long handle);
    private static native int nativeFrameCount(long handle);
    private static native int nativePacketElements(long handle);
    private static native int nativeRead(long handle, short[] output)
        throws IOException;
    private static native void nativeClose(long handle);

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        setContentView(createInterface());
        loadBundledDemonstration();
    }

    private View createInterface() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER_HORIZONTAL);
        root.setPadding(dp(28), dp(42), dp(28), dp(32));
        root.setBackground(
            gradient(
                GradientDrawable.Orientation.TL_BR,
                new int[] {0xFF090B14, 0xFF17142A, 0xFF0A1621},
                0
            )
        );

        TextView brand = text("ORKELA", 13, 0xFF9B8CFF);
        brand.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        brand.setLetterSpacing(0.28F);
        root.addView(brand, centeredWrap());

        title = text("Native Resonith", 34, Color.WHITE);
        title.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        title.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams titleLayout = centeredWrap();
        titleLayout.topMargin = dp(26);
        root.addView(title, titleLayout);

        metadata = text("C++23 portable session • Android audio", 15, 0xFF9EA6B8);
        metadata.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams metadataLayout = centeredWrap();
        metadataLayout.topMargin = dp(9);
        root.addView(metadata, metadataLayout);

        View art = new View(this);
        art.setBackground(
            gradient(
                GradientDrawable.Orientation.TL_BR,
                new int[] {0xFF7E68FF, 0xFF3ECAFF, 0xFF58E0B5},
                dp(30)
            )
        );
        LinearLayout.LayoutParams artLayout =
            new LinearLayout.LayoutParams(dp(252), dp(252));
        artLayout.topMargin = dp(36);
        root.addView(art, artLayout);

        progress = new ProgressBar(
            this,
            null,
            android.R.attr.progressBarStyleHorizontal
        );
        progress.setMax(1000);
        progress.setProgress(0);
        LinearLayout.LayoutParams progressLayout =
            new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(5)
            );
        progressLayout.topMargin = dp(34);
        root.addView(progress, progressLayout);

        LinearLayout controls = new LinearLayout(this);
        controls.setGravity(Gravity.CENTER);
        controls.setOrientation(LinearLayout.HORIZONTAL);

        Button openButton = button("Open");
        openButton.setOnClickListener(view -> openDocument());
        controls.addView(openButton, buttonLayout());

        playButton = button("Play");
        playButton.setOnClickListener(view -> togglePlayback());
        controls.addView(playButton, buttonLayout());

        Button stopButton = button("Stop");
        stopButton.setOnClickListener(view -> stopPlayback("Stopped"));
        controls.addView(stopButton, buttonLayout());

        LinearLayout.LayoutParams controlsLayout = centeredWrap();
        controlsLayout.topMargin = dp(24);
        root.addView(controls, controlsLayout);

        status = text("Loading signed demonstration…", 14, 0xFFC6CDDA);
        status.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams statusLayout = centeredWrap();
        statusLayout.topMargin = dp(24);
        root.addView(status, statusLayout);
        return root;
    }

    private void loadBundledDemonstration() {
        inputExecutor.execute(() -> {
            try (InputStream input =
                    getAssets().open("emotional-piano.resonith")) {
                byte[] bytes = readBounded(input);
                ui.post(() -> select(
                    bytes,
                    "Emotional Piano • Resonith demonstration"
                ));
            } catch (IOException exception) {
                showError("Cannot load demonstration: " + exception.getMessage());
            }
        });
    }

    private void openDocument() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("application/octet-stream");
        startActivityForResult(intent, OPEN_DOCUMENT);
    }

    @Override
    protected void onActivityResult(
        int requestCode,
        int resultCode,
        Intent data
    ) {
        super.onActivityResult(requestCode, resultCode, data);
        if (
            requestCode != OPEN_DOCUMENT
            || resultCode != RESULT_OK
            || data == null
            || data.getData() == null
        ) {
            return;
        }
        Uri uri = data.getData();
        stopPlayback("Opening stream…");
        inputExecutor.execute(() -> {
            try (InputStream input =
                    getContentResolver().openInputStream(uri)) {
                if (input == null) {
                    throw new IOException("content provider returned no data");
                }
                byte[] bytes = readBounded(input);
                String label = uri.getLastPathSegment();
                ui.post(() -> select(
                    bytes,
                    label == null ? "Selected Resonith stream" : label
                ));
            } catch (IOException exception) {
                showError("Cannot open stream: " + exception.getMessage());
            }
        });
    }

    private static byte[] readBounded(InputStream input) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buffer = new byte[64 * 1024];
        int total = 0;
        for (;;) {
            int count = input.read(buffer);
            if (count < 0) {
                return output.toByteArray();
            }
            total += count;
            if (total > MAXIMUM_INPUT_BYTES) {
                throw new IOException("mobile alpha limit is 64 MiB");
            }
            output.write(buffer, 0, count);
        }
    }

    private void select(byte[] bytes, String name) {
        selectedBytes = bytes;
        selectedName = name;
        title.setText(name);
        metadata.setText(
            String.format(Locale.ROOT, "%,d compressed bytes", bytes.length)
        );
        status.setText("Ready • native pull decode • no WAV intermediary");
        progress.setProgress(0);
    }

    private void togglePlayback() {
        if (selectedBytes == null) {
            status.setText("Open a .resonith stream first");
            return;
        }
        if ("Pause".contentEquals(playButton.getText())) {
            paused.set(true);
            playButton.setText("Resume");
            status.setText("Paused");
            return;
        }
        if ("Resume".contentEquals(playButton.getText())) {
            paused.set(false);
            playButton.setText("Pause");
            status.setText("Playing " + selectedName);
            return;
        }
        startPlayback();
    }

    private void startPlayback() {
        int generation = playbackGeneration.incrementAndGet();
        paused.set(false);
        playButton.setText("Pause");
        status.setText("Authenticating Resonith stream…");
        byte[] input = selectedBytes;
        String name = selectedName;
        playbackExecutor.execute(() -> play(input, name, generation));
    }

    private void play(byte[] input, String name, int generation) {
        long handle = 0L;
        AudioTrack track = null;
        try {
            handle = nativeOpen(input);
            int sampleRate = nativeSampleRate(handle);
            int channels = nativeChannels(handle);
            int frameCount = nativeFrameCount(handle);
            int packetElements = nativePacketElements(handle);
            int channelMask = channels == 1
                ? AudioFormat.CHANNEL_OUT_MONO
                : AudioFormat.CHANNEL_OUT_STEREO;
            int minimumBytes = AudioTrack.getMinBufferSize(
                sampleRate,
                channelMask,
                AudioFormat.ENCODING_PCM_16BIT
            );
            int packetBytes = Math.multiplyExact(packetElements, 2);
            int bufferBytes = Math.max(minimumBytes, packetBytes * 2);

            track = new AudioTrack.Builder()
                .setAudioAttributes(
                    new AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                        .build()
                )
                .setAudioFormat(
                    new AudioFormat.Builder()
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .setSampleRate(sampleRate)
                        .setChannelMask(channelMask)
                        .build()
                )
                .setTransferMode(AudioTrack.MODE_STREAM)
                .setBufferSizeInBytes(bufferBytes)
                .build();

            short[] packet = new short[packetElements];
            track.play();
            ui.post(() -> {
                metadata.setText(
                    sampleRate + " Hz • " + channels
                        + (channels == 1 ? " channel" : " channels")
                );
                status.setText("Playing " + name);
            });

            int framesPlayed = 0;
            while (generation == playbackGeneration.get()) {
                if (paused.get()) {
                    track.pause();
                    Thread.sleep(12L);
                    continue;
                }
                if (track.getPlayState() != AudioTrack.PLAYSTATE_PLAYING) {
                    track.play();
                }
                int elements = nativeRead(handle, packet);
                if (elements == 0) {
                    break;
                }
                int written = 0;
                while (
                    written < elements
                    && generation == playbackGeneration.get()
                ) {
                    int count = track.write(
                        packet,
                        written,
                        elements - written,
                        AudioTrack.WRITE_BLOCKING
                    );
                    if (count < 0) {
                        throw new IOException(
                            "Android audio write failed: " + count
                        );
                    }
                    written += count;
                }
                framesPlayed += elements / channels;
                int position = frameCount == 0
                    ? 0
                    : (int) Math.min(
                        1000L,
                        (long) framesPlayed * 1000L / frameCount
                    );
                ui.post(() -> progress.setProgress(position));
            }
            if (generation == playbackGeneration.get()) {
                ui.post(() -> finishPlayback("Playback complete"));
            }
        } catch (Exception exception) {
            if (generation == playbackGeneration.get()) {
                showError("Playback failed: " + exception.getMessage());
            }
        } finally {
            if (track != null) {
                track.pause();
                track.flush();
                track.release();
            }
            if (handle != 0L) {
                nativeClose(handle);
            }
        }
    }

    private void stopPlayback(String message) {
        playbackGeneration.incrementAndGet();
        paused.set(false);
        finishPlayback(message);
    }

    private void finishPlayback(String message) {
        playButton.setText("Play");
        status.setText(message);
    }

    private void showError(String message) {
        ui.post(() -> {
            playButton.setText("Play");
            status.setText(message);
        });
    }

    @Override
    protected void onDestroy() {
        stopPlayback("Closing");
        inputExecutor.shutdownNow();
        playbackExecutor.shutdownNow();
        super.onDestroy();
    }

    private Button button(String label) {
        Button result = new Button(this);
        result.setText(label);
        result.setTextColor(Color.WHITE);
        result.setTextSize(14);
        result.setAllCaps(false);
        result.setBackground(
            gradient(
                GradientDrawable.Orientation.LEFT_RIGHT,
                new int[] {0xFF27243D, 0xFF34304C},
                dp(18)
            )
        );
        return result;
    }

    private LinearLayout.LayoutParams buttonLayout() {
        LinearLayout.LayoutParams layout =
            new LinearLayout.LayoutParams(dp(98), dp(52));
        layout.setMargins(dp(6), 0, dp(6), 0);
        return layout;
    }

    private TextView text(String value, int size, int color) {
        TextView result = new TextView(this);
        result.setText(value);
        result.setTextSize(size);
        result.setTextColor(color);
        return result;
    }

    private LinearLayout.LayoutParams centeredWrap() {
        return new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        );
    }

    private GradientDrawable gradient(
        GradientDrawable.Orientation orientation,
        int[] colors,
        int radius
    ) {
        GradientDrawable result = new GradientDrawable(orientation, colors);
        result.setCornerRadius(radius);
        return result;
    }

    private int dp(int value) {
        return Math.round(
            value * getResources().getDisplayMetrics().density
        );
    }
}
