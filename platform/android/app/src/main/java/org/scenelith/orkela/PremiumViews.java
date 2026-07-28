package org.scenelith.orkela;

import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RadialGradient;
import android.graphics.RectF;
import android.graphics.Shader;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.os.SystemClock;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.widget.TextView;

import java.util.Arrays;
import java.util.Locale;

final class PremiumViews {
    static final int INK = 0xFFF8F7FF;
    static final int MUTED = 0xFFA9AABD;
    static final int VIOLET = 0xFF8B7CFF;
    static final int CYAN = 0xFF54D7FF;
    static final int MINT = 0xFF69E7BF;
    static final int CARD = 0xD91B1B2B;
    static final int CARD_STROKE = 0x2EFFFFFF;

    private PremiumViews() {}

    static int dp(Context context, float value) {
        return Math.round(
            value * context.getResources().getDisplayMetrics().density
        );
    }

    static GradientDrawable gradient(
        Context context,
        int[] colors,
        float radiusDp
    ) {
        GradientDrawable drawable = new GradientDrawable(
            GradientDrawable.Orientation.TL_BR,
            colors
        );
        drawable.setCornerRadius(dp(context, radiusDp));
        return drawable;
    }

    static GradientDrawable card(Context context, float radiusDp) {
        GradientDrawable drawable = gradient(
            context,
            new int[] {0xE6212134, 0xE6131825},
            radiusDp
        );
        drawable.setStroke(dp(context, 1), CARD_STROKE);
        return drawable;
    }

    static TextView text(
        Context context,
        String value,
        float sizeSp,
        int color,
        int style
    ) {
        TextView view = new TextView(context);
        view.setText(value);
        view.setTextSize(sizeSp);
        view.setTextColor(color);
        view.setTypeface(Typeface.create("sans", style));
        view.setIncludeFontPadding(false);
        return view;
    }

    static final class AuroraBackdrop extends View {
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint line = new Paint(Paint.ANTI_ALIAS_FLAG);

        AuroraBackdrop(Context context) {
            super(context);
            line.setStyle(Paint.Style.STROKE);
            line.setStrokeWidth(dp(context, 1));
            line.setColor(0x0FFFFFFF);
        }

        @Override
        protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            float width = getWidth();
            float height = getHeight();
            paint.setShader(new LinearGradient(
                0,
                0,
                width,
                height,
                new int[] {0xFF070811, 0xFF111126, 0xFF071622},
                new float[] {0F, 0.52F, 1F},
                Shader.TileMode.CLAMP
            ));
            canvas.drawRect(0, 0, width, height, paint);

            paint.setShader(new RadialGradient(
                width * 0.12F,
                height * 0.13F,
                width * 0.82F,
                new int[] {0x554F3DCE, 0x004F3DCE},
                null,
                Shader.TileMode.CLAMP
            ));
            canvas.drawRect(0, 0, width, height, paint);
            paint.setShader(new RadialGradient(
                width * 0.92F,
                height * 0.44F,
                width * 0.75F,
                new int[] {0x343BD0D8, 0x003BD0D8},
                null,
                Shader.TileMode.CLAMP
            ));
            canvas.drawRect(0, 0, width, height, paint);
            paint.setShader(null);

            float step = dp(getContext(), 42);
            for (float x = -height; x < width + height; x += step) {
                canvas.drawLine(x, 0, x - height, height, line);
            }
        }
    }

    static final class AudioFieldView extends View {
        enum Mode {
            FIELD,
            SPECTRUM,
            WAVE,
            HISTORY
        }

        private static final int WAVE_POINTS = 128;
        private static final int SPECTRUM_BANDS = 42;
        private static final int ANALYSIS_SAMPLES = 256;
        private static final int HISTORY_COLUMNS = 96;
        private static final float[] ANALYSIS_WINDOW = buildAnalysisWindow();

        private final Object analysisLock = new Object();
        private final float[] wave = new float[WAVE_POINTS];
        private final float[] spectrum = new float[SPECTRUM_BANDS];
        private final float[] waveSnapshot = new float[WAVE_POINTS];
        private final float[] spectrumSnapshot = new float[SPECTRUM_BANDS];
        private final float[] magnitudes = new float[SPECTRUM_BANDS];
        private final float[] analysis = new float[ANALYSIS_SAMPLES];
        private final float[] history =
            new float[HISTORY_COLUMNS * SPECTRUM_BANDS];
        private final float[] historySnapshot =
            new float[HISTORY_COLUMNS * SPECTRUM_BANDS];
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint stroke = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Path path = new Path();
        private final RectF bounds = new RectF();

        private volatile boolean active;
        private Mode mode = Mode.FIELD;
        private volatile float latestPeak;
        private int historyCount;
        private int historySnapshotCount;

        AudioFieldView(Context context) {
            super(context);
            setLayerType(View.LAYER_TYPE_HARDWARE, null);
            stroke.setStyle(Paint.Style.STROKE);
            stroke.setStrokeCap(Paint.Cap.ROUND);
        }

        void setActive(boolean value) {
            active = value;
            postInvalidateOnAnimation();
        }

        Mode cycleMode() {
            mode = Mode.values()[(mode.ordinal() + 1) % Mode.values().length];
            invalidate();
            return mode;
        }

        Mode getMode() {
            return mode;
        }

        void resetAnalysis() {
            synchronized (analysisLock) {
                Arrays.fill(wave, 0F);
                Arrays.fill(spectrum, 0F);
                Arrays.fill(magnitudes, 0F);
                Arrays.fill(analysis, 0F);
                Arrays.fill(history, 0F);
                historyCount = 0;
                latestPeak = 0F;
            }
            postInvalidateOnAnimation();
        }

        float offerPcm(
            short[] pcm,
            int offset,
            int elementCount,
            int channels,
            int sampleRate
        ) {
            if (
                pcm == null
                || channels <= 0
                || elementCount < channels
                || offset < 0
                || offset + elementCount > pcm.length
            ) {
                return 0F;
            }
            int frames = elementCount / channels;
            int analyzed = Math.min(ANALYSIS_SAMPLES, frames);
            int startFrame = Math.max(0, frames - analyzed);
            float peak = 0F;

            synchronized (analysisLock) {
                for (int index = 0; index < WAVE_POINTS; ++index) {
                    int frame = Math.min(
                        frames - 1,
                        index * frames / WAVE_POINTS
                    );
                    float sample = mono(pcm, offset, frame, channels);
                    wave[index] = 0.67F * wave[index] + 0.33F * sample;
                    peak = Math.max(peak, Math.abs(sample));
                }
                Arrays.fill(analysis, 0F);
                for (int index = 0; index < analyzed; ++index) {
                    int windowIndex = analyzed <= 1
                        ? ANALYSIS_SAMPLES - 1
                        : Math.round(
                            index
                            * (ANALYSIS_SAMPLES - 1F)
                            / (analyzed - 1F)
                        );
                    analysis[index] = mono(
                        pcm,
                        offset,
                        startFrame + index,
                        channels
                    ) * ANALYSIS_WINDOW[windowIndex];
                }
                double nyquist = Math.max(80.0, sampleRate * 0.5);
                float maximumMagnitude = 0F;
                for (int band = 0; band < SPECTRUM_BANDS; ++band) {
                    double ratio = band / (double) (SPECTRUM_BANDS - 1);
                    double frequency = 45.0 * Math.pow(
                        nyquist / 45.0,
                        ratio
                    );
                    double omega = 2.0 * Math.PI * frequency / sampleRate;
                    double cosine = Math.cos(omega);
                    double sine = Math.sin(omega);
                    double coefficient = 2.0 * cosine;
                    double previous = 0.0;
                    double previousTwo = 0.0;
                    for (int index = 0; index < analyzed; ++index) {
                        double current = analysis[index]
                            + coefficient * previous
                            - previousTwo;
                        previousTwo = previous;
                        previous = current;
                    }
                    double real = previous - previousTwo * cosine;
                    double imaginary = previousTwo * sine;
                    double magnitude = Math.sqrt(
                        real * real + imaginary * imaginary
                    ) / Math.max(1, analyzed);
                    magnitudes[band] = Double.isFinite(magnitude)
                        ? (float) magnitude
                        : 0F;
                    maximumMagnitude = Math.max(
                        maximumMagnitude,
                        magnitudes[band]
                    );
                }
                float visibleLevel = Math.min(
                    1F,
                    (float) Math.sqrt(peak * 3.2F)
                );
                for (int band = 0; band < SPECTRUM_BANDS; ++band) {
                    float relativeDb = maximumMagnitude <= 1.0e-9F
                        ? -60F
                        : 20F * (float) Math.log10(
                            Math.max(1.0e-9F, magnitudes[band])
                                / maximumMagnitude
                        );
                    float shape = Math.max(
                        0F,
                        Math.min(1F, (relativeDb + 54F) / 54F)
                    );
                    float mapped = shape * (0.12F + 0.88F * visibleLevel);
                    // Keep the visual stable without hiding real transients.
                    spectrum[band] = Math.max(
                        mapped,
                        spectrum[band] * 0.84F
                    );
                }
                appendHistoryColumn();
                latestPeak = peak;
            }
            postInvalidateOnAnimation();
            return peak;
        }

        private static float[] buildAnalysisWindow() {
            float[] result = new float[ANALYSIS_SAMPLES];
            for (int index = 0; index < ANALYSIS_SAMPLES; ++index) {
                result[index] = (float) (
                    0.5
                    - 0.5 * Math.cos(
                        2.0
                        * Math.PI
                        * index
                        / (ANALYSIS_SAMPLES - 1)
                    )
                );
            }
            return result;
        }

        private void appendHistoryColumn() {
            if (historyCount == HISTORY_COLUMNS) {
                int compacted = HISTORY_COLUMNS / 2;
                for (int column = 0; column < compacted; ++column) {
                    int first = column * 2 * SPECTRUM_BANDS;
                    int second = first + SPECTRUM_BANDS;
                    int output = column * SPECTRUM_BANDS;
                    for (int band = 0; band < SPECTRUM_BANDS; ++band) {
                        history[output + band] = Math.max(
                            history[first + band],
                            history[second + band]
                        );
                    }
                }
                Arrays.fill(
                    history,
                    compacted * SPECTRUM_BANDS,
                    history.length,
                    0F
                );
                historyCount = compacted;
            }
            System.arraycopy(
                spectrum,
                0,
                history,
                historyCount * SPECTRUM_BANDS,
                SPECTRUM_BANDS
            );
            ++historyCount;
        }

        private static float mono(
            short[] pcm,
            int offset,
            int frame,
            int channels
        ) {
            long sum = 0L;
            int base = offset + frame * channels;
            for (int channel = 0; channel < channels; ++channel) {
                sum += pcm[base + channel];
            }
            return (float) (
                sum / (32768.0 * channels)
            );
        }

        @Override
        protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            float width = getWidth();
            float height = getHeight();
            if (width <= 0F || height <= 0F) {
                return;
            }
            bounds.set(0, 0, width, height);
            float radius = dp(getContext(), 30);
            canvas.save();
            path.reset();
            path.addRoundRect(
                bounds,
                radius,
                radius,
                Path.Direction.CW
            );
            canvas.clipPath(path);

            float pulse = active
                ? 0.5F + 0.5F * (float) Math.sin(
                    SystemClock.uptimeMillis() * 0.0018
                )
                : 0.22F;
            paint.setShader(new LinearGradient(
                0,
                0,
                width,
                height,
                new int[] {0xFF2D225E, 0xFF102743, 0xFF0B3134},
                new float[] {0F, 0.57F, 1F},
                Shader.TileMode.CLAMP
            ));
            canvas.drawRect(bounds, paint);
            paint.setShader(new RadialGradient(
                width * (0.28F + pulse * 0.12F),
                height * 0.24F,
                width * 0.8F,
                new int[] {0x907B5CFF, 0x003F7BFF},
                null,
                Shader.TileMode.CLAMP
            ));
            canvas.drawRect(bounds, paint);
            paint.setShader(null);

            synchronized (analysisLock) {
                System.arraycopy(
                    wave,
                    0,
                    waveSnapshot,
                    0,
                    wave.length
                );
                System.arraycopy(
                    spectrum,
                    0,
                    spectrumSnapshot,
                    0,
                    spectrum.length
                );
                System.arraycopy(
                    history,
                    0,
                    historySnapshot,
                    0,
                    history.length
                );
                historySnapshotCount = historyCount;
            }

            drawOrbitalGrid(canvas, width, height, pulse);
            if (mode == Mode.WAVE) {
                drawWave(canvas, width, height, 0.88F);
            } else if (mode == Mode.HISTORY) {
                drawHistory(canvas, width, height);
                drawWave(canvas, width, height, 0.18F);
            } else {
                drawSpectrum(canvas, width, height, mode == Mode.FIELD);
                drawWave(canvas, width, height, mode == Mode.FIELD ? 0.42F : 0.2F);
            }
            canvas.restore();
            if (active) {
                postInvalidateDelayed(32L);
            }
        }

        private void drawHistory(Canvas canvas, float width, float height) {
            if (historySnapshotCount == 0) {
                drawSpectrum(canvas, width, height, false);
                return;
            }
            float left = width * 0.07F;
            float right = width * 0.93F;
            float top = height * 0.12F;
            float bottom = height * 0.79F;
            float columnWidth = (right - left) / historySnapshotCount;
            float bandHeight = (bottom - top) / SPECTRUM_BANDS;
            paint.setStyle(Paint.Style.FILL);
            for (int column = 0; column < historySnapshotCount; ++column) {
                float x0 = left + column * columnWidth;
                float x1 = left + (column + 1F) * columnWidth + 0.6F;
                int base = column * SPECTRUM_BANDS;
                for (int band = 0; band < SPECTRUM_BANDS; ++band) {
                    float value = historySnapshot[base + band];
                    if (value < 0.018F) {
                        continue;
                    }
                    float frequencyPosition =
                        band / (float) (SPECTRUM_BANDS - 1);
                    int color = blend(
                        frequencyPosition,
                        VIOLET,
                        frequencyPosition < 0.58F ? CYAN : MINT
                    );
                    int alpha = Math.max(
                        20,
                        Math.min(232, Math.round(22F + 210F * value))
                    );
                    paint.setColor(
                        (color & 0x00FFFFFF) | (alpha << 24)
                    );
                    float y1 = bottom - band * bandHeight;
                    canvas.drawRect(
                        x0,
                        y1 - bandHeight - 0.5F,
                        x1,
                        y1 + 0.5F,
                        paint
                    );
                }
            }
            paint.setColor(0xB8FFFFFF);
            float newest = left + historySnapshotCount * columnWidth;
            canvas.drawRect(
                newest - dp(getContext(), 1),
                top,
                newest,
                bottom,
                paint
            );
        }

        private void drawOrbitalGrid(
            Canvas canvas,
            float width,
            float height,
            float pulse
        ) {
            stroke.setStrokeWidth(dp(getContext(), 1));
            stroke.setColor(0x18FFFFFF);
            float centerX = width * 0.51F;
            float centerY = height * 0.43F;
            for (int ring = 1; ring <= 4; ++ring) {
                float radius = Math.min(width, height)
                    * (0.11F * ring + pulse * 0.006F);
                canvas.drawCircle(centerX, centerY, radius, stroke);
            }
            for (int line = 1; line < 6; ++line) {
                float y = height * line / 6F;
                canvas.drawLine(width * 0.07F, y, width * 0.93F, y, stroke);
            }
        }

        private void drawSpectrum(
            Canvas canvas,
            float width,
            float height,
            boolean radial
        ) {
            float base = height * 0.76F;
            float available = height * 0.46F;
            float step = width * 0.86F / SPECTRUM_BANDS;
            float start = width * 0.07F;
            stroke.setStrokeCap(Paint.Cap.ROUND);
            stroke.setStrokeWidth(Math.max(dp(getContext(), 2), step * 0.54F));
            for (int index = 0; index < SPECTRUM_BANDS; ++index) {
                float value = Math.max(
                    spectrumSnapshot[index],
                    active ? 0.006F : 0.028F
                );
                float shaped = (float) Math.sqrt(value);
                int color = blend(
                    index / (float) (SPECTRUM_BANDS - 1),
                    VIOLET,
                    index < SPECTRUM_BANDS / 2 ? CYAN : MINT
                );
                stroke.setColor((color & 0x00FFFFFF) | 0xD9000000);
                float x = start + step * (index + 0.5F);
                float top = base - available * shaped;
                if (radial) {
                    top -= (float) Math.sin(index * 0.53F)
                        * height
                        * 0.006F
                        * shaped;
                }
                canvas.drawLine(x, base, x, top, stroke);
            }
        }

        private void drawWave(
            Canvas canvas,
            float width,
            float height,
            float alpha
        ) {
            path.reset();
            float center = height * (mode == Mode.WAVE ? 0.53F : 0.39F);
            float amplitude = height * (mode == Mode.WAVE ? 0.31F : 0.14F);
            float maximum = 0F;
            for (float sample : waveSnapshot) {
                maximum = Math.max(maximum, Math.abs(sample));
            }
            float adaptiveScale = maximum <= 1.0e-5F
                ? 1F
                : Math.min(8F, 0.82F / maximum);
            for (int index = 0; index < WAVE_POINTS; ++index) {
                float x = width * index / (WAVE_POINTS - 1F);
                float idle = 0.028F * (float) Math.sin(
                    index * 0.29F + SystemClock.uptimeMillis() * 0.002
                );
                float sample = waveSnapshot[index];
                if (Math.abs(sample) < 0.0001F) {
                    sample = idle;
                } else {
                    sample *= adaptiveScale;
                }
                float y = center - sample * amplitude;
                if (index == 0) {
                    path.moveTo(x, y);
                } else {
                    path.lineTo(x, y);
                }
            }
            stroke.setStyle(Paint.Style.STROKE);
            stroke.setStrokeWidth(dp(getContext(), mode == Mode.WAVE ? 2.4F : 1.5F));
            stroke.setColor(
                ((int) (255F * alpha) << 24) | (CYAN & 0x00FFFFFF)
            );
            canvas.drawPath(path, stroke);
        }

        private static int blend(float amount, int first, int second) {
            float clamped = Math.max(0F, Math.min(1F, amount));
            int red = Math.round(
                Color.red(first) * (1F - clamped)
                + Color.red(second) * clamped
            );
            int green = Math.round(
                Color.green(first) * (1F - clamped)
                + Color.green(second) * clamped
            );
            int blue = Math.round(
                Color.blue(first) * (1F - clamped)
                + Color.blue(second) * clamped
            );
            return Color.rgb(red, green, blue);
        }
    }

    static final class TimelineView extends View {
        interface SeekListener {
            void onSeek(float fraction);
        }

        private static final int PEAKS = 192;
        private final float[] peaks = new float[PEAKS];
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final RectF touchTrack = new RectF();
        private float progress;
        private SeekListener listener;

        TimelineView(Context context) {
            super(context);
            setFocusable(true);
            setContentDescription("Playback timeline");
        }

        void setOnSeekListener(SeekListener value) {
            listener = value;
        }

        synchronized void reset() {
            Arrays.fill(peaks, 0F);
            progress = 0F;
            invalidate();
        }

        synchronized void setProgressFraction(float value) {
            progress = Math.max(0F, Math.min(1F, value));
            postInvalidateOnAnimation();
        }

        synchronized void pushPeak(float fraction, float value) {
            int index = Math.max(
                0,
                Math.min(PEAKS - 1, (int) (fraction * (PEAKS - 1)))
            );
            peaks[index] = Math.max(peaks[index] * 0.96F, value);
            postInvalidateOnAnimation();
        }

        @Override
        protected synchronized void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            float width = getWidth();
            float height = getHeight();
            float center = height * 0.5F;
            float left = dp(getContext(), 4);
            float right = width - left;
            touchTrack.set(left, 0, right, height);
            paint.setStrokeCap(Paint.Cap.ROUND);
            paint.setStrokeWidth(Math.max(1F, (right - left) / PEAKS * 0.54F));
            float step = (right - left) / PEAKS;
            int played = Math.round(progress * PEAKS);
            for (int index = 0; index < PEAKS; ++index) {
                float remembered = peaks[index];
                float idle = 0.09F + 0.08F * (float) Math.sin(index * 0.41F);
                float value = Math.max(remembered, idle);
                float half = dp(getContext(), 4) + value * height * 0.34F;
                paint.setColor(index <= played ? 0xFF82DFFF : 0x416F7188);
                float x = left + (index + 0.5F) * step;
                canvas.drawLine(x, center - half, x, center + half, paint);
            }
            float thumbX = left + progress * (right - left);
            paint.setColor(INK);
            canvas.drawCircle(thumbX, center, dp(getContext(), 5.5F), paint);
            paint.setStyle(Paint.Style.STROKE);
            paint.setStrokeWidth(dp(getContext(), 5));
            paint.setColor(0x288B7CFF);
            canvas.drawCircle(thumbX, center, dp(getContext(), 9), paint);
            paint.setStyle(Paint.Style.FILL);
        }

        @Override
        public boolean onTouchEvent(MotionEvent event) {
            if (
                event.getActionMasked() != MotionEvent.ACTION_DOWN
                && event.getActionMasked() != MotionEvent.ACTION_MOVE
                && event.getActionMasked() != MotionEvent.ACTION_UP
            ) {
                return super.onTouchEvent(event);
            }
            float fraction = (event.getX() - touchTrack.left)
                / Math.max(1F, touchTrack.width());
            setProgressFraction(fraction);
            if (listener != null) {
                listener.onSeek(progress);
            }
            if (event.getActionMasked() == MotionEvent.ACTION_UP) {
                performClick();
            }
            return true;
        }

        @Override
        public boolean performClick() {
            super.performClick();
            return true;
        }
    }

    static final class IconButton extends View {
        enum Icon {
            PLAY,
            PAUSE,
            BACK_TEN,
            FORWARD_TEN,
            STOP,
            FOLDER,
            REPEAT,
            INFO,
            SETTINGS
        }

        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Path path = new Path();
        private Icon icon;
        private final boolean primary;

        IconButton(Context context, Icon value, boolean isPrimary) {
            super(context);
            icon = value;
            primary = isPrimary;
            setClickable(true);
            setFocusable(true);
            updateDescription();
            GradientDrawable content = gradient(
                context,
                isPrimary
                    ? new int[] {0xFF7867FF, 0xFF5D8DFF}
                    : new int[] {0xE52C2B44, 0xE51B2133},
                100
            );
            content.setStroke(
                dp(context, 1),
                isPrimary ? 0x44FFFFFF : 0x24FFFFFF
            );
            setBackground(new RippleDrawable(
                ColorStateList.valueOf(0x44FFFFFF),
                content,
                null
            ));
        }

        void setIcon(Icon value) {
            icon = value;
            updateDescription();
            invalidate();
        }

        private void updateDescription() {
            setContentDescription(
                icon.name().toLowerCase(Locale.ROOT).replace('_', ' ')
            );
        }

        @Override
        protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            float width = getWidth();
            float height = getHeight();
            float cx = width * 0.5F;
            float cy = height * 0.5F;
            float unit = Math.min(width, height) * (primary ? 0.22F : 0.18F);
            paint.setColor(Color.WHITE);
            paint.setStyle(Paint.Style.FILL);
            paint.setStrokeCap(Paint.Cap.ROUND);
            paint.setStrokeJoin(Paint.Join.ROUND);
            paint.setStrokeWidth(dp(getContext(), 2));
            path.reset();
            switch (icon) {
            case PLAY:
                path.moveTo(cx - unit * 0.55F, cy - unit);
                path.lineTo(cx + unit, cy);
                path.lineTo(cx - unit * 0.55F, cy + unit);
                path.close();
                canvas.drawPath(path, paint);
                break;
            case PAUSE:
                canvas.drawRoundRect(
                    cx - unit * 0.8F,
                    cy - unit,
                    cx - unit * 0.18F,
                    cy + unit,
                    unit * 0.16F,
                    unit * 0.16F,
                    paint
                );
                canvas.drawRoundRect(
                    cx + unit * 0.18F,
                    cy - unit,
                    cx + unit * 0.8F,
                    cy + unit,
                    unit * 0.16F,
                    unit * 0.16F,
                    paint
                );
                break;
            case STOP:
                canvas.drawRoundRect(
                    cx - unit * 0.76F,
                    cy - unit * 0.76F,
                    cx + unit * 0.76F,
                    cy + unit * 0.76F,
                    unit * 0.18F,
                    unit * 0.18F,
                    paint
                );
                break;
            case BACK_TEN:
            case FORWARD_TEN:
                drawTen(canvas, cx, cy, unit, icon == Icon.FORWARD_TEN);
                break;
            case FOLDER:
                path.moveTo(cx - unit, cy - unit * 0.62F);
                path.lineTo(cx - unit * 0.2F, cy - unit * 0.62F);
                path.lineTo(cx + unit * 0.05F, cy - unit * 0.3F);
                path.lineTo(cx + unit, cy - unit * 0.3F);
                path.lineTo(cx + unit, cy + unit * 0.72F);
                path.lineTo(cx - unit, cy + unit * 0.72F);
                path.close();
                canvas.drawPath(path, paint);
                break;
            case REPEAT:
                paint.setStyle(Paint.Style.STROKE);
                canvas.drawArc(
                    cx - unit,
                    cy - unit * 0.65F,
                    cx + unit,
                    cy + unit * 0.65F,
                    205,
                    250,
                    false,
                    paint
                );
                paint.setStyle(Paint.Style.FILL);
                break;
            case INFO:
                paint.setStyle(Paint.Style.STROKE);
                canvas.drawCircle(cx, cy, unit, paint);
                paint.setStyle(Paint.Style.FILL);
                canvas.drawCircle(cx, cy - unit * 0.48F, unit * 0.11F, paint);
                canvas.drawRoundRect(
                    cx - unit * 0.1F,
                    cy - unit * 0.12F,
                    cx + unit * 0.1F,
                    cy + unit * 0.58F,
                    unit * 0.1F,
                    unit * 0.1F,
                    paint
                );
                break;
            case SETTINGS:
                paint.setStyle(Paint.Style.STROKE);
                paint.setStrokeWidth(Math.max(dp(getContext(), 2), unit * 0.22F));
                canvas.drawCircle(cx, cy, unit * 0.78F, paint);
                canvas.drawCircle(cx, cy, unit * 0.28F, paint);
                for (int tooth = 0; tooth < 8; ++tooth) {
                    double angle = tooth * Math.PI * 0.25;
                    float inner = unit * 0.82F;
                    float outer = unit * 1.08F;
                    canvas.drawLine(
                        cx + (float) Math.cos(angle) * inner,
                        cy + (float) Math.sin(angle) * inner,
                        cx + (float) Math.cos(angle) * outer,
                        cy + (float) Math.sin(angle) * outer,
                        paint
                    );
                }
                break;
            default:
                break;
            }
        }

        private void drawTen(
            Canvas canvas,
            float cx,
            float cy,
            float unit,
            boolean forward
        ) {
            paint.setStyle(Paint.Style.STROKE);
            RectF arc = new RectF(
                cx - unit,
                cy - unit,
                cx + unit,
                cy + unit
            );
            canvas.drawArc(
                arc,
                forward ? -65F : 115F,
                forward ? 275F : -275F,
                false,
                paint
            );
            paint.setStyle(Paint.Style.FILL);
            path.reset();
            float direction = forward ? 1F : -1F;
            path.moveTo(cx + direction * unit * 0.93F, cy - unit * 0.4F);
            path.lineTo(cx + direction * unit * 0.27F, cy - unit * 0.65F);
            path.lineTo(cx + direction * unit * 0.56F, cy + unit * 0.02F);
            path.close();
            canvas.drawPath(path, paint);
            paint.setTextAlign(Paint.Align.CENTER);
            paint.setTypeface(Typeface.DEFAULT_BOLD);
            paint.setTextSize(unit * 0.78F);
            canvas.drawText("10", cx, cy + unit * 0.28F, paint);
        }
    }

    static final class PillButton extends TextView {
        private boolean selected;

        PillButton(Context context, String label) {
            super(context);
            setText(label);
            setTextSize(13);
            setTextColor(INK);
            setGravity(Gravity.CENTER);
            setTypeface(Typeface.create("sans", Typeface.BOLD));
            setAllCaps(false);
            setClickable(true);
            setFocusable(true);
            setPadding(dp(context, 16), 0, dp(context, 16), 0);
            refresh();
        }

        void setSelectedState(boolean value) {
            selected = value;
            refresh();
        }

        private void refresh() {
            GradientDrawable content = gradient(
                getContext(),
                selected
                    ? new int[] {0xFF6959EF, 0xFF3F8BCC}
                    : new int[] {0xDF2A293E, 0xDF1E2434},
                100
            );
            content.setStroke(
                dp(getContext(), 1),
                selected ? 0x66A9E8FF : 0x24FFFFFF
            );
            setBackground(new RippleDrawable(
                ColorStateList.valueOf(0x33FFFFFF),
                content,
                null
            ));
        }
    }
}
