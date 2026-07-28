package org.scenelith.orkela;

import android.app.Activity;
import android.app.Dialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.ColorDrawable;
import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioTrack;
import android.media.PlaybackParams;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.util.Log;
import android.view.Gravity;
import android.view.HapticFeedbackConstants;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowManager;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.TextView;

import java.io.IOException;
import java.io.InputStream;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class MainActivity extends Activity {
    private static final String PLAYBACK_LOG_TAG = "OrkelaPlayback";
    private static final int OPEN_DOCUMENT = 41;
    private static final int MAXIMUM_INPUT_BYTES = 64 * 1024 * 1024;
    private static final int NO_SEEK_REQUEST = -1;
    private static final String INTERFACE_PREFERENCES =
        "orkela_interface";
    private static final String LANGUAGE_PREFERENCE = "language";
    private static final String SYSTEM_LANGUAGE = "system";

    private static final int T_APP_NAME = 0;
    private static final int T_TAGLINE = 1;
    private static final int T_LOCAL_PRIVATE = 2;
    private static final int T_NOW_PLAYING = 3;
    private static final int T_NATIVE_RESONITH = 4;
    private static final int T_PORTABLE_SESSION = 5;
    private static final int T_RESONITH = 6;
    private static final int T_CAUSAL_FIELD = 7;
    private static final int T_DECODED_TRUTH = 8;
    private static final int T_VISUAL_HINT = 9;
    private static final int T_READY = 10;
    private static final int T_PLAYING = 11;
    private static final int T_PAUSED = 12;
    private static final int T_PLAYBACK_COMPLETE = 13;
    private static final int T_STOPPED = 14;
    private static final int T_AUTHENTICATING = 15;
    private static final int T_SEEKING = 16;
    private static final int T_LISTENING = 17;
    private static final int T_VOLUME = 18;
    private static final int T_REPEAT_OFF = 19;
    private static final int T_REPEAT_ON = 20;
    private static final int T_SOURCE = 21;
    private static final int T_OPEN_RESONITH = 22;
    private static final int T_LOAD_DEMO = 23;
    private static final int T_SETTINGS = 24;
    private static final int T_INTERFACE = 25;
    private static final int T_LANGUAGE = 26;
    private static final int T_LANGUAGE_DESCRIPTION = 27;
    private static final int T_SYSTEM_DEFAULT = 28;
    private static final int T_DONE = 29;
    private static final int T_FIELD = 30;
    private static final int T_SPECTRUM = 31;
    private static final int T_WAVE = 32;
    private static final int T_HISTORY = 33;
    private static final int T_PRIVACY_DETAIL = 34;
    private static final int T_SOURCE_FOOTER = 35;
    private static final int T_PLAYBACK_FAILED = 36;
    private static final int T_PLAY_ACTION = 49;
    private static final int T_PAUSE_ACTION = 50;
    private static final int T_RESUME_ACTION = 51;
    private static final int T_STOP_ACTION = 52;
    private static final int T_BACK_TEN_ACTION = 53;
    private static final int T_FORWARD_TEN_ACTION = 54;
    private static final int T_PLAYBACK_TIMELINE = 55;
    private static final int T_PLAYBACK_INFORMATION = 56;

    static {
        System.loadLibrary("orkela_android");
    }

    private final Handler ui = new Handler(Looper.getMainLooper());
    private final ExecutorService inputExecutor =
        Executors.newSingleThreadExecutor();
    private final ExecutorService playbackExecutor =
        Executors.newSingleThreadExecutor();
    private final AtomicBoolean paused = new AtomicBoolean(false);
    private final AtomicBoolean repeat = new AtomicBoolean(false);
    private final AtomicInteger playbackGeneration = new AtomicInteger(0);
    private final AtomicInteger requestedSeekFrame =
        new AtomicInteger(NO_SEEK_REQUEST);
    private final AtomicInteger volumePermille = new AtomicInteger(820);

    private TextView title;
    private TextView metadata;
    private TextView status;
    private TextView elapsed;
    private TextView duration;
    private TextView truthDetail;
    private PremiumViews.AudioFieldView visualizer;
    private PremiumViews.TimelineView timeline;
    private PremiumViews.IconButton playButton;
    private PremiumViews.PillButton repeatButton;
    private PremiumViews.PillButton speedButton;
    private PremiumViews.PillButton visualButton;

    private byte[] selectedBytes;
    private String selectedName = "Resonith";
    private volatile AudioTrack activeTrack;
    private volatile boolean playbackRunning;
    private volatile float playbackSpeed = 1F;
    private volatile int knownFrameCount;
    private volatile int knownSampleRate;
    private volatile int knownChannels;
    private volatile int currentFrame;

    // Instrumentation invokes the exact JNI pull path packaged in the APK.
    // This Java linkage surface is intentionally not a stable public SDK.
    public static native long nativeOpen(byte[] input) throws IOException;
    public static native int nativeSampleRate(long handle);
    public static native int nativeChannels(long handle);
    public static native int nativeFrameCount(long handle);
    public static native int nativePacketElements(long handle);
    public static native int nativeRead(long handle, short[] output)
        throws IOException;
    public static native void nativeClose(long handle);
    public static native String nativeText(String localeTag, int textId);

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        configureWindow();
        setContentView(createInterface());
        if (!loadIncomingIntent(getIntent())) {
            loadBundledDemonstration();
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        loadIncomingIntent(intent);
    }

    private void configureWindow() {
        Window window = getWindow();
        window.setStatusBarColor(Color.TRANSPARENT);
        window.setNavigationBarColor(0xFF070A12);
        window.addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS);
        window.getDecorView().setSystemUiVisibility(
            View.SYSTEM_UI_FLAG_LAYOUT_STABLE
            | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
        );
    }

    private View createInterface() {
        FrameLayout root = new FrameLayout(this);
        root.addView(
            new PremiumViews.AuroraBackdrop(this),
            matchParent()
        );

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setClipToPadding(false);
        scroll.setOverScrollMode(View.OVER_SCROLL_NEVER);
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(
            dp(20),
            statusBarInset() + dp(18),
            dp(20),
            dp(40)
        );
        scroll.addView(content, matchWidthWrap());
        root.addView(scroll, matchParent());

        content.addView(createTopBar(), matchWidth(dp(42)));

        TextView eyebrow = PremiumViews.text(
            this,
            text(T_NOW_PLAYING),
            12,
            PremiumViews.VIOLET,
            Typeface.BOLD
        );
        eyebrow.setLetterSpacing(0.18F);
        LinearLayout.LayoutParams eyebrowLayout = matchWidthWrap();
        eyebrowLayout.topMargin = dp(26);
        content.addView(eyebrow, eyebrowLayout);

        title = PremiumViews.text(
            this,
            text(T_NATIVE_RESONITH),
            31,
            PremiumViews.INK,
            Typeface.BOLD
        );
        title.setMaxLines(2);
        title.setLineSpacing(0F, 0.96F);
        LinearLayout.LayoutParams titleLayout = matchWidthWrap();
        titleLayout.topMargin = dp(8);
        content.addView(title, titleLayout);

        metadata = PremiumViews.text(
            this,
            text(T_PORTABLE_SESSION) + " • Android 17",
            14,
            PremiumViews.MUTED,
            Typeface.NORMAL
        );
        LinearLayout.LayoutParams metadataLayout = matchWidthWrap();
        metadataLayout.topMargin = dp(8);
        content.addView(metadata, metadataLayout);

        FrameLayout hero = new FrameLayout(this);
        hero.setBackground(PremiumViews.card(this, 30));
        hero.setClipToOutline(true);
        visualizer = new PremiumViews.AudioFieldView(this);
        hero.addView(visualizer, matchParent());
        hero.addView(createHeroOverlay(), matchParent());
        LinearLayout.LayoutParams heroLayout = matchWidth(dp(314));
        heroLayout.topMargin = dp(24);
        content.addView(hero, heroLayout);

        timeline = new PremiumViews.TimelineView(this);
        timeline.setContentDescription(text(T_PLAYBACK_TIMELINE));
        timeline.setOnSeekListener(this::requestSeek);
        LinearLayout.LayoutParams timelineLayout = matchWidth(dp(58));
        timelineLayout.topMargin = dp(18);
        content.addView(timeline, timelineLayout);

        LinearLayout timeRow = new LinearLayout(this);
        timeRow.setGravity(Gravity.CENTER_VERTICAL);
        elapsed = PremiumViews.text(
            this,
            "0:00",
            12,
            0xFFD8D8E7,
            Typeface.BOLD
        );
        duration = PremiumViews.text(
            this,
            "0:00",
            12,
            PremiumViews.MUTED,
            Typeface.BOLD
        );
        timeRow.addView(elapsed, weightedWrap(1F));
        duration.setGravity(Gravity.END);
        timeRow.addView(duration, weightedWrap(1F));
        content.addView(timeRow, matchWidthWrap());

        LinearLayout transport = createTransport();
        LinearLayout.LayoutParams transportLayout = matchWidth(dp(82));
        transportLayout.topMargin = dp(16);
        content.addView(transport, transportLayout);

        content.addView(createStatusCard(), withTopMargin(matchWidthWrap(), 18));
        content.addView(createQuickControls(), withTopMargin(matchWidthWrap(), 14));
        content.addView(createSourceCard(), withTopMargin(matchWidthWrap(), 14));
        return root;
    }

    private View createTopBar() {
        LinearLayout bar = new LinearLayout(this);
        bar.setGravity(Gravity.CENTER_VERTICAL);

        FrameLayout mark = new FrameLayout(this);
        mark.setBackground(PremiumViews.gradient(
            this,
            new int[] {0xFF725FFF, 0xFF37B6D8},
            14
        ));
        TextView markText = PremiumViews.text(
            this,
            "O",
            20,
            Color.WHITE,
            Typeface.BOLD
        );
        markText.setGravity(Gravity.CENTER);
        mark.addView(markText, matchParent());
        bar.addView(mark, new LinearLayout.LayoutParams(dp(42), dp(42)));

        LinearLayout brand = new LinearLayout(this);
        brand.setOrientation(LinearLayout.VERTICAL);
        brand.setPadding(dp(12), 0, 0, 0);
        TextView wordmark = PremiumViews.text(
            this,
            text(T_APP_NAME).toUpperCase(activeLocale()),
            15,
            PremiumViews.INK,
            Typeface.BOLD
        );
        wordmark.setLetterSpacing(0.18F);
        TextView promise = PremiumViews.text(
            this,
            text(T_TAGLINE),
            11,
            PremiumViews.MUTED,
            Typeface.NORMAL
        );
        brand.addView(wordmark, matchWidthWrap());
        brand.addView(promise, withTopMargin(matchWidthWrap(), 3));
        bar.addView(brand, new LinearLayout.LayoutParams(0, dp(42), 1F));

        PremiumViews.PillButton local = new PremiumViews.PillButton(
            this,
            text(T_LOCAL_PRIVATE)
        );
        local.setTextSize(9);
        local.setSingleLine(true);
        local.setHorizontallyScrolling(true);
        local.setContentDescription(text(T_PRIVACY_DETAIL));
        bar.addView(local, new LinearLayout.LayoutParams(dp(120), dp(38)));

        PremiumViews.IconButton settings = new PremiumViews.IconButton(
            this,
            PremiumViews.IconButton.Icon.SETTINGS,
            false
        );
        settings.setContentDescription(text(T_SETTINGS));
        settings.setOnClickListener(view -> {
            haptic(view);
            showSettings();
        });
        LinearLayout.LayoutParams settingsLayout =
            new LinearLayout.LayoutParams(dp(38), dp(38));
        settingsLayout.leftMargin = dp(8);
        bar.addView(settings, settingsLayout);
        return bar;
    }

    private View createHeroOverlay() {
        FrameLayout overlay = new FrameLayout(this);
        LinearLayout top = new LinearLayout(this);
        top.setGravity(Gravity.CENTER_VERTICAL);
        top.setPadding(dp(18), dp(17), dp(18), 0);
        PremiumViews.PillButton format = new PremiumViews.PillButton(
            this,
            text(T_RESONITH)
        );
        format.setTextSize(10);
        format.setSelectedState(true);
        top.addView(format, new LinearLayout.LayoutParams(dp(92), dp(34)));

        TextView mode = PremiumViews.text(
            this,
            text(T_CAUSAL_FIELD),
            10,
            0xFFC8C4E9,
            Typeface.BOLD
        );
        mode.setGravity(Gravity.END | Gravity.CENTER_VERTICAL);
        mode.setLetterSpacing(0.13F);
        top.addView(mode, new LinearLayout.LayoutParams(0, dp(34), 1F));
        overlay.addView(top, topAligned());

        LinearLayout bottom = new LinearLayout(this);
        bottom.setOrientation(LinearLayout.VERTICAL);
        bottom.setPadding(dp(18), 0, dp(18), dp(18));
        bottom.setGravity(Gravity.BOTTOM);
        TextView caption = PremiumViews.text(
            this,
            text(T_DECODED_TRUTH),
            13,
            0xEFFFFFFF,
            Typeface.BOLD
        );
        TextView hint = PremiumViews.text(
            this,
            text(T_VISUAL_HINT),
            11,
            0xBFD9DCF1,
            Typeface.NORMAL
        );
        bottom.addView(caption, matchWidthWrap());
        bottom.addView(hint, withTopMargin(matchWidthWrap(), 5));
        overlay.addView(bottom, bottomAligned());
        return overlay;
    }

    private LinearLayout createTransport() {
        LinearLayout controls = new LinearLayout(this);
        controls.setGravity(Gravity.CENTER);

        PremiumViews.IconButton back = new PremiumViews.IconButton(
            this,
            PremiumViews.IconButton.Icon.BACK_TEN,
            false
        );
        back.setContentDescription(text(T_BACK_TEN_ACTION));
        back.setOnClickListener(view -> {
            haptic(view);
            skipSeconds(-10);
        });
        controls.addView(back, transportSide());

        playButton = new PremiumViews.IconButton(
            this,
            PremiumViews.IconButton.Icon.PLAY,
            true
        );
        playButton.setId(R.id.play_button);
        playButton.setContentDescription(text(T_PLAY_ACTION));
        playButton.setOnClickListener(view -> {
            haptic(view);
            togglePlayback();
        });
        LinearLayout.LayoutParams playLayout =
            new LinearLayout.LayoutParams(dp(78), dp(78));
        playLayout.setMargins(dp(22), 0, dp(22), 0);
        controls.addView(playButton, playLayout);

        PremiumViews.IconButton forward = new PremiumViews.IconButton(
            this,
            PremiumViews.IconButton.Icon.FORWARD_TEN,
            false
        );
        forward.setContentDescription(text(T_FORWARD_TEN_ACTION));
        forward.setOnClickListener(view -> {
            haptic(view);
            skipSeconds(10);
        });
        controls.addView(forward, transportSide());

        PremiumViews.IconButton stop = new PremiumViews.IconButton(
            this,
            PremiumViews.IconButton.Icon.STOP,
            false
        );
        stop.setContentDescription(text(T_STOP_ACTION));
        stop.setOnClickListener(view -> {
            haptic(view);
            stopPlayback(text(T_STOPPED), true);
        });
        LinearLayout.LayoutParams stopLayout = transportSide();
        stopLayout.leftMargin = dp(14);
        controls.addView(stop, stopLayout);
        return controls;
    }

    private View createStatusCard() {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(18), dp(16), dp(18), dp(16));
        card.setBackground(PremiumViews.card(this, 20));

        LinearLayout row = new LinearLayout(this);
        row.setGravity(Gravity.CENTER_VERTICAL);
        TextView dot = PremiumViews.text(
            this,
            "●",
            12,
            PremiumViews.MINT,
            Typeface.BOLD
        );
        row.addView(dot, new LinearLayout.LayoutParams(dp(20), dp(28)));
        status = PremiumViews.text(
            this,
            text(T_AUTHENTICATING),
            13,
            0xFFE3E3EE,
            Typeface.BOLD
        );
        row.addView(status, new LinearLayout.LayoutParams(0, dp(28), 1F));
        PremiumViews.IconButton info = new PremiumViews.IconButton(
            this,
            PremiumViews.IconButton.Icon.INFO,
            false
        );
        info.setContentDescription(text(T_PLAYBACK_INFORMATION));
        info.setOnClickListener(view -> {
            haptic(view);
            truthDetail.setVisibility(
                truthDetail.getVisibility() == View.VISIBLE
                    ? View.GONE
                    : View.VISIBLE
            );
        });
        row.addView(info, new LinearLayout.LayoutParams(dp(38), dp(38)));
        card.addView(row, matchWidthWrap());

        truthDetail = PremiumViews.text(
            this,
            text(T_PRIVACY_DETAIL),
            12,
            PremiumViews.MUTED,
            Typeface.NORMAL
        );
        truthDetail.setLineSpacing(dp(2), 1F);
        truthDetail.setVisibility(View.GONE);
        card.addView(truthDetail, withTopMargin(matchWidthWrap(), 10));
        return card;
    }

    private View createQuickControls() {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(18), dp(17), dp(18), dp(18));
        card.setBackground(PremiumViews.card(this, 20));

        LinearLayout heading = new LinearLayout(this);
        heading.setGravity(Gravity.CENTER_VERTICAL);
        heading.addView(
            PremiumViews.text(
                this,
                text(T_LISTENING),
                11,
                PremiumViews.MUTED,
                Typeface.BOLD
            ),
            new LinearLayout.LayoutParams(0, dp(28), 1F)
        );
        TextView output = PremiumViews.text(
            this,
            "ANDROID AUDIO",
            10,
            PremiumViews.CYAN,
            Typeface.BOLD
        );
        output.setGravity(Gravity.END | Gravity.CENTER_VERTICAL);
        heading.addView(output, new LinearLayout.LayoutParams(dp(130), dp(28)));
        card.addView(heading, matchWidthWrap());

        LinearLayout volumeRow = new LinearLayout(this);
        volumeRow.setGravity(Gravity.CENTER_VERTICAL);
        TextView volumeLabel = PremiumViews.text(
            this,
            text(T_VOLUME),
            13,
            PremiumViews.INK,
            Typeface.BOLD
        );
        volumeRow.addView(volumeLabel, new LinearLayout.LayoutParams(dp(74), dp(42)));
        SeekBar volume = new SeekBar(this);
        volume.setMax(1000);
        volume.setProgress(volumePermille.get());
        volume.setProgressTintList(ColorStateList.valueOf(PremiumViews.CYAN));
        volume.setThumbTintList(ColorStateList.valueOf(PremiumViews.INK));
        volume.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override
            public void onProgressChanged(
                SeekBar seekBar,
                int progress,
                boolean fromUser
            ) {
                volumePermille.set(progress);
                AudioTrack track = activeTrack;
                if (track != null) {
                    track.setVolume(progress / 1000F);
                }
            }

            @Override
            public void onStartTrackingTouch(SeekBar seekBar) {}

            @Override
            public void onStopTrackingTouch(SeekBar seekBar) {
                haptic(seekBar);
            }
        });
        volumeRow.addView(volume, new LinearLayout.LayoutParams(0, dp(42), 1F));
        card.addView(volumeRow, withTopMargin(matchWidthWrap(), 6));

        LinearLayout pills = new LinearLayout(this);
        pills.setGravity(Gravity.CENTER_VERTICAL);
        speedButton = new PremiumViews.PillButton(this, "1.00×");
        speedButton.setOnClickListener(view -> {
            haptic(view);
            cycleSpeed();
        });
        pills.addView(speedButton, weightedPill());

        repeatButton = new PremiumViews.PillButton(
            this,
            text(T_REPEAT_OFF)
        );
        repeatButton.setOnClickListener(view -> {
            haptic(view);
            boolean enabled = !repeat.get();
            repeat.set(enabled);
            repeatButton.setText(
                enabled ? text(T_REPEAT_ON) : text(T_REPEAT_OFF)
            );
            repeatButton.setSelectedState(enabled);
        });
        LinearLayout.LayoutParams repeatLayout = weightedPill();
        repeatLayout.setMargins(dp(8), 0, dp(8), 0);
        pills.addView(repeatButton, repeatLayout);

        visualButton = new PremiumViews.PillButton(this, text(T_FIELD));
        visualButton.setOnClickListener(view -> {
            haptic(view);
            PremiumViews.AudioFieldView.Mode mode = visualizer.cycleMode();
            visualButton.setText(visualModeLabel(mode));
        });
        pills.addView(visualButton, weightedPill());
        card.addView(pills, withTopMargin(matchWidth(dp(44)), 7));
        return card;
    }

    private View createSourceCard() {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(18), dp(17), dp(18), dp(18));
        card.setBackground(PremiumViews.card(this, 20));
        card.addView(
            PremiumViews.text(
                this,
                text(T_SOURCE),
                11,
                PremiumViews.MUTED,
                Typeface.BOLD
            ),
            matchWidthWrap()
        );

        LinearLayout buttons = new LinearLayout(this);
        PremiumViews.PillButton open = new PremiumViews.PillButton(
            this,
            text(T_OPEN_RESONITH)
        );
        open.setSelectedState(true);
        open.setOnClickListener(view -> {
            haptic(view);
            openDocument();
        });
        buttons.addView(open, weightedPill());
        PremiumViews.PillButton demo = new PremiumViews.PillButton(
            this,
            text(T_LOAD_DEMO)
        );
        demo.setOnClickListener(view -> {
            haptic(view);
            stopPlayback(text(T_AUTHENTICATING), true);
            loadBundledDemonstration();
        });
        LinearLayout.LayoutParams demoLayout = weightedPill();
        demoLayout.leftMargin = dp(10);
        buttons.addView(demo, demoLayout);
        card.addView(buttons, withTopMargin(matchWidth(dp(46)), 12));

        TextView footer = PremiumViews.text(
            this,
            text(T_SOURCE_FOOTER),
            11,
            PremiumViews.MUTED,
            Typeface.NORMAL
        );
        footer.setLineSpacing(dp(2), 1F);
        card.addView(footer, withTopMargin(matchWidthWrap(), 13));
        return card;
    }

    private String text(int identifier) {
        return nativeText(activeLocale().toLanguageTag(), identifier);
    }

    private Locale activeLocale() {
        String selected = getSharedPreferences(
            INTERFACE_PREFERENCES,
            MODE_PRIVATE
        ).getString(LANGUAGE_PREFERENCE, SYSTEM_LANGUAGE);
        if (selected == null || SYSTEM_LANGUAGE.equals(selected)) {
            return Locale.getDefault();
        }
        Locale locale = Locale.forLanguageTag(selected);
        return locale.getLanguage().isEmpty()
            ? Locale.ENGLISH
            : locale;
    }

    private String visualModeLabel(PremiumViews.AudioFieldView.Mode mode) {
        if (mode == PremiumViews.AudioFieldView.Mode.FIELD) {
            return text(T_FIELD);
        }
        if (mode == PremiumViews.AudioFieldView.Mode.SPECTRUM) {
            return text(T_SPECTRUM);
        }
        if (mode == PremiumViews.AudioFieldView.Mode.WAVE) {
            return text(T_WAVE);
        }
        return text(T_HISTORY);
    }

    private void showSettings() {
        Dialog dialog = new Dialog(this);
        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(dp(22), dp(22), dp(22), dp(22));
        panel.setBackground(PremiumViews.card(this, 26));

        TextView titleView = PremiumViews.text(
            this,
            text(T_SETTINGS),
            25,
            PremiumViews.INK,
            Typeface.BOLD
        );
        panel.addView(titleView, matchWidthWrap());
        TextView section = PremiumViews.text(
            this,
            text(T_INTERFACE) + "  /  " + text(T_LANGUAGE),
            12,
            PremiumViews.VIOLET,
            Typeface.BOLD
        );
        section.setLetterSpacing(0.08F);
        panel.addView(section, withTopMargin(matchWidthWrap(), 10));
        TextView description = PremiumViews.text(
            this,
            text(T_LANGUAGE_DESCRIPTION),
            13,
            PremiumViews.MUTED,
            Typeface.NORMAL
        );
        description.setLineSpacing(dp(2), 1F);
        panel.addView(description, withTopMargin(matchWidthWrap(), 10));

        ScrollView languageScroll = new ScrollView(this);
        languageScroll.setOverScrollMode(View.OVER_SCROLL_NEVER);
        LinearLayout languageList = new LinearLayout(this);
        languageList.setOrientation(LinearLayout.VERTICAL);
        String[] tags = {
            SYSTEM_LANGUAGE,
            "en",
            "de",
            "es",
            "it",
            "ja",
            "ko",
            "zh-Hans",
            "ru",
            "uk"
        };
        String[] autonyms = {
            text(T_SYSTEM_DEFAULT),
            "English",
            "Deutsch",
            "Español",
            "Italiano",
            "日本語",
            "한국어",
            "简体中文",
            "Русский",
            "Українська"
        };
        SharedPreferences preferences = getSharedPreferences(
            INTERFACE_PREFERENCES,
            MODE_PRIVATE
        );
        String selected = preferences.getString(
            LANGUAGE_PREFERENCE,
            SYSTEM_LANGUAGE
        );
        for (int index = 0; index < tags.length; ++index) {
            String tag = tags[index];
            PremiumViews.PillButton languageButton =
                new PremiumViews.PillButton(this, autonyms[index]);
            languageButton.setSelectedState(tag.equals(selected));
            languageButton.setOnClickListener(view -> {
                haptic(view);
                preferences.edit()
                    .putString(LANGUAGE_PREFERENCE, tag)
                    .apply();
                dialog.dismiss();
                recreate();
            });
            LinearLayout.LayoutParams row = matchWidth(dp(46));
            row.topMargin = dp(index == 0 ? 0 : 7);
            languageList.addView(languageButton, row);
        }
        languageScroll.addView(languageList, matchWidthWrap());
        LinearLayout.LayoutParams languageLayout = matchWidth(dp(430));
        languageLayout.topMargin = dp(18);
        panel.addView(languageScroll, languageLayout);

        PremiumViews.PillButton done = new PremiumViews.PillButton(
            this,
            text(T_DONE)
        );
        done.setSelectedState(true);
        done.setOnClickListener(view -> dialog.dismiss());
        panel.addView(done, withTopMargin(matchWidth(dp(48)), 16));

        dialog.setContentView(panel);
        Window window = dialog.getWindow();
        if (window != null) {
            window.setBackgroundDrawable(new ColorDrawable(Color.TRANSPARENT));
            window.addFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND);
            WindowManager.LayoutParams attributes = window.getAttributes();
            attributes.width = WindowManager.LayoutParams.MATCH_PARENT;
            attributes.height = WindowManager.LayoutParams.WRAP_CONTENT;
            attributes.dimAmount = 0.72F;
            window.setAttributes(attributes);
        }
        dialog.show();
        if (window != null) {
            window.setLayout(
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.WRAP_CONTENT
            );
        }
    }

    private void loadBundledDemonstration() {
        inputExecutor.execute(() -> {
            try (InputStream input =
                    getAssets().open("emotional-piano.resonith")) {
                byte[] bytes = readBounded(input);
                ui.post(() -> select(
                    bytes,
                    "Emotional Piano"
                ));
            } catch (IOException exception) {
                showError(exception.getMessage());
            }
        });
    }

    private void openDocument() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("application/octet-stream");
        intent.addFlags(
            Intent.FLAG_GRANT_READ_URI_PERMISSION
            | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION
        );
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
        loadUri(data.getData(), data.getFlags());
    }

    private boolean loadIncomingIntent(Intent intent) {
        if (
            intent == null
            || !Intent.ACTION_VIEW.equals(intent.getAction())
            || intent.getData() == null
        ) {
            return false;
        }
        loadUri(intent.getData(), intent.getFlags());
        return true;
    }

    private void loadUri(Uri uri, int grantFlags) {
        try {
            if (
                (grantFlags & Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
                    != 0
            ) {
                getContentResolver().takePersistableUriPermission(
                    uri,
                    Intent.FLAG_GRANT_READ_URI_PERMISSION
                );
            }
        } catch (SecurityException ignored) {
            // Some providers grant only one-shot access; the current open
            // remains valid and no persistence claim is shown to the user.
        }
        stopPlayback(text(T_AUTHENTICATING), true);
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
                    cleanDisplayName(label)
                ));
            } catch (IOException exception) {
                showError(exception.getMessage());
            }
        });
    }

    private static String cleanDisplayName(String value) {
        if (value == null || value.isBlank()) {
            return "Selected Resonith stream";
        }
        int slash = Math.max(value.lastIndexOf('/'), value.lastIndexOf(':'));
        String result = slash >= 0 ? value.substring(slash + 1) : value;
        return result.replaceFirst("(?i)\\.resonith$", "");
    }

    private static byte[] readBounded(InputStream input) throws IOException {
        java.io.ByteArrayOutputStream output =
            new java.io.ByteArrayOutputStream();
        byte[] buffer = new byte[64 * 1024];
        int total = 0;
        for (;;) {
            int count = input.read(buffer);
            if (count < 0) {
                return output.toByteArray();
            }
            total = Math.addExact(total, count);
            if (total > MAXIMUM_INPUT_BYTES) {
                throw new IOException("mobile input profile is limited to 64 MiB");
            }
            output.write(buffer, 0, count);
        }
    }

    private void select(byte[] bytes, String name) {
        selectedBytes = bytes;
        selectedName = name;
        knownFrameCount = 0;
        knownSampleRate = 0;
        knownChannels = 0;
        currentFrame = 0;
        title.setText(name);
        metadata.setText(
            String.format(
                Locale.ROOT,
                "%,d compressed bytes • awaiting native preflight",
                bytes.length
            )
        );
        status.setText(text(T_READY));
        elapsed.setText("0:00");
        duration.setText("0:00");
        timeline.reset();
        visualizer.resetAnalysis();
        visualizer.setActive(false);
        playButton.setIcon(PremiumViews.IconButton.Icon.PLAY);
        playButton.setContentDescription(text(T_PLAY_ACTION));
    }

    private void togglePlayback() {
        if (selectedBytes == null) {
            status.setText(text(T_OPEN_RESONITH));
            return;
        }
        if (playbackRunning) {
            if (paused.compareAndSet(false, true)) {
                AudioTrack track = activeTrack;
                if (track != null) {
                    track.pause();
                }
                playButton.setIcon(PremiumViews.IconButton.Icon.PLAY);
                playButton.setContentDescription(text(T_RESUME_ACTION));
                visualizer.setActive(false);
                status.setText(text(T_PAUSED));
            } else {
                paused.set(false);
                playButton.setIcon(PremiumViews.IconButton.Icon.PAUSE);
                playButton.setContentDescription(text(T_PAUSE_ACTION));
                visualizer.setActive(true);
                status.setText(text(T_PLAYING) + " " + selectedName);
            }
            return;
        }
        int start = currentFrame >= knownFrameCount && knownFrameCount > 0
            ? 0
            : currentFrame;
        startPlayback(start);
    }

    private void startPlayback(int startFrame) {
        int generation = playbackGeneration.incrementAndGet();
        requestedSeekFrame.set(NO_SEEK_REQUEST);
        paused.set(false);
        playbackRunning = true;
        playButton.setIcon(PremiumViews.IconButton.Icon.PAUSE);
        playButton.setContentDescription(text(T_PAUSE_ACTION));
        visualizer.setActive(true);
        status.setText(text(T_AUTHENTICATING));
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        byte[] input = selectedBytes;
        String name = selectedName;
        playbackExecutor.execute(() -> play(
            input,
            name,
            generation,
            Math.max(0, startFrame)
        ));
    }

    private void play(
        byte[] input,
        String name,
        int generation,
        int initialFrame
    ) {
        int targetFrame = initialFrame;
        try {
            for (;;) {
                if (generation != playbackGeneration.get()) {
                    return;
                }
                PlaybackPass result = playPass(
                    input,
                    name,
                    generation,
                    targetFrame
                );
                if (result == PlaybackPass.STOPPED) {
                    return;
                }
                if (result == PlaybackPass.SEEK) {
                    targetFrame = Math.max(
                        0,
                        requestedSeekFrame.getAndSet(NO_SEEK_REQUEST)
                    );
                    continue;
                }
                if (repeat.get()) {
                    targetFrame = 0;
                    continue;
                }
                ui.post(() -> finishPlayback(
                    text(T_PLAYBACK_COMPLETE),
                    false
                ));
                return;
            }
        } catch (Exception exception) {
            if (generation == playbackGeneration.get()) {
                showError(exception.getMessage());
            }
        } finally {
            activeTrack = null;
        }
    }

    private PlaybackPass playPass(
        byte[] input,
        String name,
        int generation,
        int requestedStart
    ) throws Exception {
        long handle = 0L;
        AudioTrack track = null;
        try {
            handle = nativeOpen(input);
            int sampleRate = nativeSampleRate(handle);
            int channels = nativeChannels(handle);
            int frameCount = nativeFrameCount(handle);
            int packetElements = nativePacketElements(handle);
            if (sampleRate <= 0 || channels < 1 || channels > 2) {
                throw new IOException("unsupported native PCM metadata");
            }
            int target = Math.min(Math.max(0, requestedStart), frameCount);
            int channelMask = channels == 1
                ? AudioFormat.CHANNEL_OUT_MONO
                : AudioFormat.CHANNEL_OUT_STEREO;
            track = createAudioTrack(
                sampleRate,
                channelMask,
                packetElements
            );
            activeTrack = track;
            applyPresentation(track);

            knownSampleRate = sampleRate;
            knownChannels = channels;
            knownFrameCount = frameCount;
            currentFrame = target;
            ui.post(() -> {
                metadata.setText(
                    String.format(
                        Locale.ROOT,
                        "%,d Hz • %s • %,d frames",
                        sampleRate,
                        channels == 1 ? "mono" : "stereo",
                        frameCount
                    )
                );
                duration.setText(formatFrames(frameCount, sampleRate));
                status.setText(
                    target == 0
                        ? text(T_PLAYING) + " " + name
                        : text(T_SEEKING)
                            + " • "
                            + formatFrames(target, sampleRate)
                );
                updateProgressUi(target);
            });

            short[] packet = new short[packetElements];
            PendingPacket pending = skipToFrame(
                handle,
                packet,
                channels,
                target,
                generation
            );
            currentFrame = pending.decodedFrame;
            boolean started = false;
            boolean reportedFirstQueueWrite = false;
            long lastUiUpdate = 0L;
            long submittedFrames = 0L;

            for (;;) {
                if (generation != playbackGeneration.get()) {
                    return PlaybackPass.STOPPED;
                }
                if (requestedSeekFrame.get() != NO_SEEK_REQUEST) {
                    return PlaybackPass.SEEK;
                }
                if (paused.get()) {
                    if (started) {
                        track.pause();
                    }
                    Thread.sleep(12L);
                    continue;
                }
                if (!started || track.getPlayState() != AudioTrack.PLAYSTATE_PLAYING) {
                    applyPresentation(track);
                    track.play();
                    started = true;
                }

                int offset;
                int elements;
                if (pending.elements != 0) {
                    offset = pending.offset;
                    elements = pending.elements;
                    pending = PendingPacket.empty(currentFrame);
                } else {
                    offset = 0;
                    elements = nativeRead(handle, packet);
                }
                if (elements == 0) {
                    break;
                }

                float peak = visualizer.offerPcm(
                    packet,
                    offset,
                    elements,
                    channels,
                    sampleRate
                );
                int written = 0;
                while (
                    written < elements
                    && generation == playbackGeneration.get()
                ) {
                    int count = track.write(
                        packet,
                        offset + written,
                        elements - written,
                        AudioTrack.WRITE_BLOCKING
                    );
                    if (count < 0) {
                        throw new IOException(
                            "Android audio write failed: " + count
                        );
                    }
                    if (count > 0 && !reportedFirstQueueWrite) {
                        Log.i(
                            PLAYBACK_LOG_TAG,
                            "ORKELA_AUDIO_QUEUE_WRITE accepted_elements=" + count
                        );
                        reportedFirstQueueWrite = true;
                    }
                    written += count;
                }
                int frames = written / channels;
                submittedFrames += frames;
                currentFrame = Math.min(frameCount, currentFrame + frames);
                float fraction = frameCount == 0
                    ? 0F
                    : currentFrame / (float) frameCount;
                timeline.pushPeak(fraction, peak);

                long now = SystemClock.uptimeMillis();
                if (now - lastUiUpdate >= 40L) {
                    int displayedFrame = currentFrame;
                    ui.post(() -> updateProgressUi(displayedFrame));
                    lastUiUpdate = now;
                }
            }

            // A blocking write proves queue acceptance, not audible completion.
            // Keep the device alive until its playback head drains submitted PCM.
            while (
                generation == playbackGeneration.get()
                && Integer.toUnsignedLong(track.getPlaybackHeadPosition())
                    < submittedFrames
            ) {
                if (requestedSeekFrame.get() != NO_SEEK_REQUEST) {
                    return PlaybackPass.SEEK;
                }
                Thread.sleep(10L);
            }
            currentFrame = frameCount;
            ui.post(() -> updateProgressUi(frameCount));
            return PlaybackPass.COMPLETE;
        } finally {
            if (track != null) {
                if (track.getState() == AudioTrack.STATE_INITIALIZED) {
                    track.pause();
                    track.flush();
                }
                track.release();
            }
            if (activeTrack == track) {
                activeTrack = null;
            }
            if (handle != 0L) {
                nativeClose(handle);
            }
        }
    }

    private PendingPacket skipToFrame(
        long handle,
        short[] packet,
        int channels,
        int targetFrame,
        int generation
    ) throws IOException {
        int decoded = 0;
        while (decoded < targetFrame) {
            if (generation != playbackGeneration.get()) {
                return PendingPacket.empty(decoded);
            }
            int elements = nativeRead(handle, packet);
            if (elements == 0) {
                return PendingPacket.empty(decoded);
            }
            int frames = elements / channels;
            if (decoded + frames <= targetFrame) {
                decoded += frames;
                continue;
            }
            int skippedFrames = targetFrame - decoded;
            int offset = skippedFrames * channels;
            return new PendingPacket(
                offset,
                elements - offset,
                targetFrame
            );
        }
        return PendingPacket.empty(decoded);
    }

    private AudioTrack createAudioTrack(
        int sampleRate,
        int channelMask,
        int packetElements
    ) {
        int minimumBytes = AudioTrack.getMinBufferSize(
            sampleRate,
            channelMask,
            AudioFormat.ENCODING_PCM_16BIT
        );
        int packetBytes = Math.multiplyExact(packetElements, 2);
        int bufferBytes = Math.max(minimumBytes, packetBytes * 3);
        return new AudioTrack.Builder()
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
    }

    private void applyPresentation(AudioTrack track) {
        track.setVolume(volumePermille.get() / 1000F);
        try {
            PlaybackParams params = new PlaybackParams()
                .allowDefaults()
                .setSpeed(playbackSpeed)
                .setPitch(1F);
            track.setPlaybackParams(params);
        } catch (IllegalArgumentException exception) {
            Log.w(
                PLAYBACK_LOG_TAG,
                "Device rejected playback speed " + playbackSpeed,
                exception
            );
        }
    }

    private void requestSeek(float fraction) {
        if (knownFrameCount <= 0) {
            return;
        }
        int target = Math.max(
            0,
            Math.min(
                knownFrameCount,
                Math.round(fraction * knownFrameCount)
            )
        );
        currentFrame = target;
        updateProgressUi(target);
        if (playbackRunning) {
            visualizer.resetAnalysis();
            requestedSeekFrame.set(target);
        }
    }

    private void skipSeconds(int seconds) {
        if (knownSampleRate <= 0 || knownFrameCount <= 0) {
            status.setText(text(T_READY));
            return;
        }
        long target = (long) currentFrame + (long) seconds * knownSampleRate;
        requestSeek(
            Math.max(0L, Math.min(knownFrameCount, target))
                / (float) knownFrameCount
        );
    }

    private void cycleSpeed() {
        float[] speeds = {0.75F, 1F, 1.25F, 1.5F};
        int current = 0;
        for (int index = 0; index < speeds.length; ++index) {
            if (Math.abs(speeds[index] - playbackSpeed) < 0.01F) {
                current = index;
                break;
            }
        }
        playbackSpeed = speeds[(current + 1) % speeds.length];
        speedButton.setText(String.format(Locale.ROOT, "%.2f×", playbackSpeed));
        speedButton.setSelectedState(Math.abs(playbackSpeed - 1F) > 0.01F);
        AudioTrack track = activeTrack;
        if (track != null) {
            applyPresentation(track);
        }
    }

    private void updateProgressUi(int frame) {
        if (knownFrameCount <= 0 || knownSampleRate <= 0) {
            return;
        }
        float fraction = Math.max(
            0F,
            Math.min(1F, frame / (float) knownFrameCount)
        );
        timeline.setProgressFraction(fraction);
        elapsed.setText(formatFrames(frame, knownSampleRate));
        duration.setText(formatFrames(knownFrameCount, knownSampleRate));
    }

    private static String formatFrames(int frames, int sampleRate) {
        if (sampleRate <= 0) {
            return "0:00";
        }
        long totalSeconds = Math.max(0L, frames / sampleRate);
        long hours = totalSeconds / 3600L;
        long minutes = (totalSeconds / 60L) % 60L;
        long seconds = totalSeconds % 60L;
        return hours == 0L
            ? String.format(Locale.ROOT, "%d:%02d", minutes, seconds)
            : String.format(
                Locale.ROOT,
                "%d:%02d:%02d",
                hours,
                minutes,
                seconds
            );
    }

    private void stopPlayback(String message, boolean resetPosition) {
        playbackGeneration.incrementAndGet();
        requestedSeekFrame.set(NO_SEEK_REQUEST);
        paused.set(false);
        playbackRunning = false;
        if (resetPosition) {
            currentFrame = 0;
            timeline.setProgressFraction(0F);
            elapsed.setText("0:00");
        }
        finishPlayback(message, false);
    }

    private void finishPlayback(String message, boolean keepPosition) {
        playbackRunning = false;
        paused.set(false);
        playButton.setIcon(PremiumViews.IconButton.Icon.PLAY);
        playButton.setContentDescription(text(T_PLAY_ACTION));
        visualizer.setActive(false);
        status.setText(message);
        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        if (!keepPosition && currentFrame >= knownFrameCount) {
            currentFrame = knownFrameCount;
        }
    }

    private void showError(String message) {
        ui.post(() -> {
            playbackRunning = false;
            playButton.setIcon(PremiumViews.IconButton.Icon.PLAY);
            playButton.setContentDescription(text(T_PLAY_ACTION));
            visualizer.setActive(false);
            status.setText(
                text(T_PLAYBACK_FAILED)
                    + ": "
                    + (message == null ? "unknown error" : message)
            );
            getWindow().clearFlags(
                WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
            );
        });
    }

    @Override
    protected void onDestroy() {
        stopPlayback("Closing", false);
        inputExecutor.shutdownNow();
        playbackExecutor.shutdownNow();
        super.onDestroy();
    }

    private static void haptic(View view) {
        view.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP);
    }

    private int statusBarInset() {
        int identifier = getResources().getIdentifier(
            "status_bar_height",
            "dimen",
            "android"
        );
        return identifier == 0
            ? dp(24)
            : getResources().getDimensionPixelSize(identifier);
    }

    private int dp(float value) {
        return PremiumViews.dp(this, value);
    }

    private FrameLayout.LayoutParams matchParent() {
        return new FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        );
    }

    private LinearLayout.LayoutParams matchWidth(int height) {
        return new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            height
        );
    }

    private LinearLayout.LayoutParams matchWidthWrap() {
        return new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        );
    }

    private LinearLayout.LayoutParams weightedWrap(float weight) {
        return new LinearLayout.LayoutParams(
            0,
            LinearLayout.LayoutParams.WRAP_CONTENT,
            weight
        );
    }

    private LinearLayout.LayoutParams weightedPill() {
        return new LinearLayout.LayoutParams(0, dp(44), 1F);
    }

    private LinearLayout.LayoutParams transportSide() {
        return new LinearLayout.LayoutParams(dp(56), dp(56));
    }

    private LinearLayout.LayoutParams withTopMargin(
        LinearLayout.LayoutParams layout,
        float margin
    ) {
        layout.topMargin = dp(margin);
        return layout;
    }

    private FrameLayout.LayoutParams topAligned() {
        FrameLayout.LayoutParams layout = matchParent();
        layout.gravity = Gravity.TOP;
        return layout;
    }

    private FrameLayout.LayoutParams bottomAligned() {
        FrameLayout.LayoutParams layout = matchParent();
        layout.gravity = Gravity.BOTTOM;
        return layout;
    }

    private enum PlaybackPass {
        COMPLETE,
        SEEK,
        STOPPED
    }

    private static final class PendingPacket {
        final int offset;
        final int elements;
        final int decodedFrame;

        PendingPacket(int valueOffset, int valueElements, int valueFrame) {
            offset = valueOffset;
            elements = valueElements;
            decodedFrame = valueFrame;
        }

        static PendingPacket empty(int frame) {
            return new PendingPacket(0, 0, frame);
        }
    }
}
