#import <AppKit/AppKit.h>
#import <AVFAudio/AVFAudio.h>
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>

#include "orkela/localization.h"
#include "orkela/resonith_pull_decoder.h"
#include "orkela/visual_analysis.h"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <memory>
#include <span>
#include <string>
#include <utility>
#include <vector>

namespace {

NSString* const interface_language_key = @"OrkelaInterfaceLanguage";
constexpr std::size_t maximum_input_bytes = 64ULL * 1024ULL * 1024ULL;

NSString* ns_string(std::string_view value) {
    return [[NSString alloc]
        initWithBytes:value.data()
               length:value.size()
             encoding:NSUTF8StringEncoding];
}

orkela::language active_language() {
    NSString* selected = [
        [NSUserDefaults standardUserDefaults]
        stringForKey:interface_language_key
    ];
    NSString* tag = selected.length == 0U
        ? NSLocale.preferredLanguages.firstObject
        : selected;
    return orkela::language_from_tag(
        tag.length == 0U ? "en" : tag.UTF8String
    );
}

NSString* ui_text(orkela::text_id identifier) {
    return ns_string(
        orkela::localized_text(active_language(), identifier)
    );
}

orkela::text_id mode_text_id(orkela::visual_mode mode) {
    switch (mode) {
    case orkela::visual_mode::field:
        return orkela::text_id::field;
    case orkela::visual_mode::spectrum:
        return orkela::text_id::spectrum;
    case orkela::visual_mode::wave:
        return orkela::text_id::wave;
    case orkela::visual_mode::history:
        return orkela::text_id::history;
    }
    return orkela::text_id::field;
}

NSColor* orkela_color(
    CGFloat red,
    CGFloat green,
    CGFloat blue,
    CGFloat alpha = 1.0
) {
    return [NSColor colorWithSRGBRed:red
                              green:green
                               blue:blue
                              alpha:alpha];
}

}  // namespace

@interface OrkelaMacVisualView : NSView {
@private
    orkela::pcm_visual_analyzer _analyzer;
    orkela::visual_snapshot _snapshot;
    orkela::visual_mode _mode;
}
- (void)offerPCM:(const std::int16_t*)samples
        elements:(std::size_t)elements
        channels:(std::uint16_t)channels
      sampleRate:(std::uint32_t)sampleRate;
- (void)resetAnalysis;
- (orkela::visual_mode)visualMode;
@end

@implementation OrkelaMacVisualView

- (instancetype)init {
    self = [super initWithFrame:NSZeroRect];
    if (self != nil) {
        _mode = orkela::visual_mode::field;
        self.wantsLayer = YES;
        self.layer.backgroundColor = orkela_color(
            0.045,
            0.052,
            0.095
        ).CGColor;
        self.layer.cornerRadius = 24.0;
        self.layer.borderWidth = 1.0;
        self.layer.borderColor =
            orkela_color(0.24, 0.26, 0.42).CGColor;
        self.toolTip = ui_text(mode_text_id(orkela::visual_mode::field));
        [self setAccessibilityLabel:
            ui_text(mode_text_id(orkela::visual_mode::field))];
        [self setAccessibilityHelp:
            ui_text(orkela::text_id::visual_hint)];
    }
    return self;
}

- (BOOL)isFlipped {
    return YES;
}

- (void)mouseDown:(NSEvent*)event {
    (void)event;
    _mode = orkela::next_visual_mode(_mode);
    self.toolTip = ui_text(mode_text_id(_mode));
    [self setAccessibilityLabel:ui_text(mode_text_id(_mode))];
    [self setNeedsDisplay:YES];
}

- (void)offerPCM:(const std::int16_t*)samples
        elements:(std::size_t)elements
        channels:(std::uint16_t)channels
      sampleRate:(std::uint32_t)sampleRate {
    if (samples == nullptr || elements == 0U) {
        return;
    }
    static_cast<void>(
        _analyzer.offer(
            std::span<const std::int16_t>(samples, elements),
            channels,
            sampleRate
        )
    );
    _snapshot = _analyzer.snapshot();
    [self setNeedsDisplay:YES];
}

- (void)resetAnalysis {
    _analyzer.reset();
    _snapshot = {};
    [self setNeedsDisplay:YES];
}

- (orkela::visual_mode)visualMode {
    return _mode;
}

- (void)drawRect:(NSRect)dirtyRect {
    [super drawRect:dirtyRect];
    const NSRect area = NSInsetRect(self.bounds, 22.0, 34.0);
    NSDictionary<NSAttributedStringKey, id>* attributes = @{
        NSFontAttributeName:
            [NSFont systemFontOfSize:11.0 weight:NSFontWeightSemibold],
        NSForegroundColorAttributeName:
            orkela_color(0.68, 0.63, 1.0),
    };
    [ui_text(mode_text_id(_mode))
        drawAtPoint:NSMakePoint(22.0, 14.0)
     withAttributes:attributes];

    if (_mode == orkela::visual_mode::spectrum) {
        const CGFloat width = NSWidth(area)
            / static_cast<CGFloat>(orkela::visual_spectrum_bands);
        for (
            std::size_t band = 0U;
            band < orkela::visual_spectrum_bands;
            ++band
        ) {
            const CGFloat level =
                static_cast<CGFloat>(_snapshot.spectrum[band]);
            const CGFloat height = 2.0 + level * NSHeight(area);
            [orkela_color(0.42, 0.48 + level * 0.35, 1.0) setFill];
            [[NSBezierPath bezierPathWithRoundedRect:NSMakeRect(
                NSMinX(area) + static_cast<CGFloat>(band) * width,
                NSMaxY(area) - height,
                std::max<CGFloat>(1.0, width - 2.0),
                height
            ) xRadius:2.0 yRadius:2.0] fill];
        }
        return;
    }

    if (_mode == orkela::visual_mode::history) {
        const std::size_t columns = std::max<std::size_t>(
            1U,
            _snapshot.history_columns
        );
        const CGFloat width =
            NSWidth(area) / static_cast<CGFloat>(columns);
        const CGFloat height = NSHeight(area)
            / static_cast<CGFloat>(orkela::visual_spectrum_bands);
        for (std::size_t column = 0U; column < columns; ++column) {
            for (
                std::size_t band = 0U;
                band < orkela::visual_spectrum_bands;
                ++band
            ) {
                const CGFloat level = static_cast<CGFloat>(
                    _snapshot.history[
                        column * orkela::visual_spectrum_bands + band
                    ]
                );
                if (level <= 0.015) {
                    continue;
                }
                [
                    orkela_color(
                        0.30 + level * 0.30,
                        0.36 + level * 0.44,
                        0.90,
                        0.18 + level * 0.82
                    )
                    setFill
                ];
                NSRectFill(NSMakeRect(
                    NSMinX(area) + static_cast<CGFloat>(column) * width,
                    NSMaxY(area)
                        - static_cast<CGFloat>(band + 1U) * height,
                    width + 0.5,
                    height + 0.5
                ));
            }
        }
        return;
    }

    const CGFloat center = NSMidY(area);
    const CGFloat step = NSWidth(area)
        / static_cast<CGFloat>(orkela::visual_wave_points - 1U);
    NSBezierPath* wave = [NSBezierPath bezierPath];
    for (
        std::size_t index = 0U;
        index < orkela::visual_wave_points;
        ++index
    ) {
        const NSPoint point = NSMakePoint(
            NSMinX(area) + static_cast<CGFloat>(index) * step,
            center - static_cast<CGFloat>(_snapshot.wave[index])
                * NSHeight(area) * 0.47
        );
        if (index == 0U) {
            [wave moveToPoint:point];
        } else {
            [wave lineToPoint:point];
        }
    }
    [orkela_color(0.46, 0.40, 1.0) setStroke];
    wave.lineWidth = _mode == orkela::visual_mode::field ? 2.8 : 1.8;
    [wave stroke];
    if (_mode == orkela::visual_mode::field) {
        const CGFloat width = NSWidth(area)
            / static_cast<CGFloat>(orkela::visual_spectrum_bands);
        for (
            std::size_t band = 0U;
            band < orkela::visual_spectrum_bands;
            ++band
        ) {
            const CGFloat level =
                static_cast<CGFloat>(_snapshot.spectrum[band]);
            [orkela_color(0.28, 0.64, 1.0, 0.10 + 0.35 * level)
                setFill];
            NSRectFill(NSMakeRect(
                NSMinX(area) + static_cast<CGFloat>(band) * width,
                NSMaxY(area) - level * NSHeight(area) * 0.62,
                std::max<CGFloat>(1.0, width - 1.0),
                level * NSHeight(area) * 0.62
            ));
        }
    }
}

@end

@interface OrkelaMacController : NSObject <NSWindowDelegate> {
@private
    std::shared_ptr<orkela::decoded_audio> _decoded;
    std::uint32_t _lastVisualFrame;
}
@property(nonatomic, strong) NSWindow* window;
@property(nonatomic, strong) NSTextField* titleLabel;
@property(nonatomic, strong) NSTextField* metadataLabel;
@property(nonatomic, strong) NSTextField* statusLabel;
@property(nonatomic, strong) NSButton* openButton;
@property(nonatomic, strong) NSButton* playButton;
@property(nonatomic, strong) NSButton* stopButton;
@property(nonatomic, strong) NSButton* settingsButton;
@property(nonatomic, strong) NSProgressIndicator* progress;
@property(nonatomic, strong) OrkelaMacVisualView* visual;
@property(nonatomic, strong) AVAudioEngine* engine;
@property(nonatomic, strong) AVAudioPlayerNode* player;
@property(nonatomic, strong) AVAudioPCMBuffer* buffer;
@property(nonatomic, strong) NSTimer* timer;
@end

@implementation OrkelaMacController

- (void)showWindow {
    self.window = [[NSWindow alloc]
        initWithContentRect:NSMakeRect(0.0, 0.0, 940.0, 700.0)
                  styleMask:NSWindowStyleMaskTitled
                            | NSWindowStyleMaskClosable
                            | NSWindowStyleMaskMiniaturizable
                            | NSWindowStyleMaskResizable
                    backing:NSBackingStoreBuffered
                      defer:NO];
    self.window.title = @"Orkela";
    self.window.minSize = NSMakeSize(760.0, 560.0);
    self.window.delegate = self;
    [self.window center];

    NSView* content = self.window.contentView;
    content.wantsLayer = YES;
    content.layer.backgroundColor =
        orkela_color(0.018, 0.022, 0.040).CGColor;

    NSTextField* brand = [NSTextField labelWithString:@"O R K E L A"];
    brand.font = [NSFont systemFontOfSize:13.0 weight:NSFontWeightBold];
    brand.textColor = orkela_color(0.64, 0.58, 1.0);
    self.titleLabel = [NSTextField
        labelWithString:ui_text(orkela::text_id::native_resonith)];
    self.titleLabel.font =
        [NSFont systemFontOfSize:32.0 weight:NSFontWeightBold];
    self.titleLabel.textColor = NSColor.whiteColor;
    self.metadataLabel = [NSTextField labelWithString:@""];
    self.metadataLabel.textColor = orkela_color(0.66, 0.69, 0.78);
    self.statusLabel = [NSTextField
        labelWithString:ui_text(orkela::text_id::authenticating)];
    self.statusLabel.textColor = orkela_color(0.74, 0.77, 0.86);
    self.statusLabel.alignment = NSTextAlignmentCenter;

    self.settingsButton = [NSButton buttonWithImage:
        [NSImage imageWithSystemSymbolName:@"gearshape.fill"
                 accessibilityDescription:
                     ui_text(orkela::text_id::settings)]
                                           target:self
                                           action:@selector(showSettings)];
    self.settingsButton.bezelStyle = NSBezelStyleTexturedRounded;
    self.visual = [[OrkelaMacVisualView alloc] init];
    self.progress = [[NSProgressIndicator alloc] init];
    self.progress.indeterminate = NO;
    self.progress.minValue = 0.0;
    self.progress.maxValue = 1.0;
    [self.progress setAccessibilityLabel:
        ui_text(orkela::text_id::playback_timeline)];
    self.openButton = [NSButton
        buttonWithTitle:ui_text(orkela::text_id::open_resonith)
                 target:self
                 action:@selector(openDocument)];
    self.playButton = [NSButton
        buttonWithTitle:ui_text(orkela::text_id::play_action)
                 target:self
                 action:@selector(togglePlayback)];
    self.stopButton = [NSButton
        buttonWithTitle:ui_text(orkela::text_id::stop_action)
                 target:self
                 action:@selector(stopPlayback)];

    NSArray<NSView*>* views = @[
        brand,
        self.titleLabel,
        self.metadataLabel,
        self.settingsButton,
        self.visual,
        self.progress,
        self.openButton,
        self.playButton,
        self.stopButton,
        self.statusLabel,
    ];
    for (NSView* view in views) {
        view.translatesAutoresizingMaskIntoConstraints = NO;
        [content addSubview:view];
    }
    [NSLayoutConstraint activateConstraints:@[
        [brand.topAnchor constraintEqualToAnchor:content.topAnchor
                                        constant:28.0],
        [brand.leadingAnchor constraintEqualToAnchor:content.leadingAnchor
                                            constant:34.0],
        [self.settingsButton.topAnchor
            constraintEqualToAnchor:content.topAnchor
                           constant:22.0],
        [self.settingsButton.trailingAnchor
            constraintEqualToAnchor:content.trailingAnchor
                           constant:-30.0],
        [self.titleLabel.topAnchor constraintEqualToAnchor:brand.bottomAnchor
                                                   constant:20.0],
        [self.titleLabel.centerXAnchor
            constraintEqualToAnchor:content.centerXAnchor],
        [self.metadataLabel.topAnchor
            constraintEqualToAnchor:self.titleLabel.bottomAnchor
                           constant:7.0],
        [self.metadataLabel.centerXAnchor
            constraintEqualToAnchor:content.centerXAnchor],
        [self.visual.topAnchor
            constraintEqualToAnchor:self.metadataLabel.bottomAnchor
                           constant:28.0],
        [self.visual.leadingAnchor
            constraintEqualToAnchor:content.leadingAnchor
                           constant:44.0],
        [self.visual.trailingAnchor
            constraintEqualToAnchor:content.trailingAnchor
                           constant:-44.0],
        [self.visual.heightAnchor constraintEqualToConstant:330.0],
        [self.progress.topAnchor
            constraintEqualToAnchor:self.visual.bottomAnchor
                           constant:24.0],
        [self.progress.leadingAnchor
            constraintEqualToAnchor:self.visual.leadingAnchor],
        [self.progress.trailingAnchor
            constraintEqualToAnchor:self.visual.trailingAnchor],
        [self.openButton.topAnchor
            constraintEqualToAnchor:self.progress.bottomAnchor
                           constant:24.0],
        [self.playButton.topAnchor
            constraintEqualToAnchor:self.openButton.topAnchor],
        [self.stopButton.topAnchor
            constraintEqualToAnchor:self.openButton.topAnchor],
        [self.playButton.centerXAnchor
            constraintEqualToAnchor:content.centerXAnchor],
        [self.openButton.trailingAnchor
            constraintEqualToAnchor:self.playButton.leadingAnchor
                           constant:-16.0],
        [self.stopButton.leadingAnchor
            constraintEqualToAnchor:self.playButton.trailingAnchor
                           constant:16.0],
        [self.openButton.widthAnchor constraintEqualToConstant:180.0],
        [self.playButton.widthAnchor constraintEqualToConstant:140.0],
        [self.stopButton.widthAnchor constraintEqualToConstant:140.0],
        [self.statusLabel.topAnchor
            constraintEqualToAnchor:self.playButton.bottomAnchor
                           constant:20.0],
        [self.statusLabel.centerXAnchor
            constraintEqualToAnchor:content.centerXAnchor],
    ]];
    [self applyLocalization];
    [self.window makeKeyAndOrderFront:nil];
    [self loadBundledDemo];
}

- (void)applyLocalization {
    self.window.title = [
        [ui_text(orkela::text_id::app_name)
            stringByAppendingString:@" — "]
        stringByAppendingString:ui_text(orkela::text_id::tagline)
    ];
    self.titleLabel.stringValue =
        ui_text(orkela::text_id::native_resonith);
    self.openButton.title = ui_text(orkela::text_id::open_resonith);
    self.playButton.title = self.player.isPlaying
        ? ui_text(orkela::text_id::pause_action)
        : ui_text(orkela::text_id::play_action);
    self.stopButton.title = ui_text(orkela::text_id::stop_action);
    self.settingsButton.toolTip = ui_text(orkela::text_id::settings);
    [self.settingsButton setAccessibilityLabel:
        ui_text(orkela::text_id::settings)];
    [self.progress setAccessibilityLabel:
        ui_text(orkela::text_id::playback_timeline)];
    self.visual.toolTip = ui_text(mode_text_id(self.visual.visualMode));
    [self.visual setAccessibilityLabel:
        ui_text(mode_text_id(self.visual.visualMode))];
    [self.visual setAccessibilityHelp:
        ui_text(orkela::text_id::visual_hint)];
    self.statusLabel.stringValue = _decoded == nullptr
        ? ui_text(orkela::text_id::authenticating)
        : ui_text(orkela::text_id::ready);
    [self.visual setNeedsDisplay:YES];
}

- (void)showSettings {
    NSAlert* alert = [[NSAlert alloc] init];
    alert.messageText = ui_text(orkela::text_id::settings);
    alert.informativeText =
        ui_text(orkela::text_id::language_description);
    [alert addButtonWithTitle:ui_text(orkela::text_id::done)];
    NSPopUpButton* languages = [[NSPopUpButton alloc]
        initWithFrame:NSMakeRect(0.0, 0.0, 310.0, 32.0)
            pullsDown:NO];
    [languages addItemWithTitle:
        ui_text(orkela::text_id::system_default)];
    constexpr std::array values = {
        orkela::language::english,
        orkela::language::german,
        orkela::language::spanish,
        orkela::language::italian,
        orkela::language::japanese,
        orkela::language::korean,
        orkela::language::chinese_simplified,
        orkela::language::russian,
        orkela::language::ukrainian,
    };
    NSString* selected = [
        [NSUserDefaults standardUserDefaults]
        stringForKey:interface_language_key
    ];
    NSInteger selectedIndex = 0;
    for (std::size_t index = 0U; index < values.size(); ++index) {
        [languages addItemWithTitle:
            ns_string(orkela::language_autonym(values[index]))];
        if ([selected isEqualToString:
            ns_string(orkela::language_tag(values[index]))]) {
            selectedIndex = static_cast<NSInteger>(index + 1U);
        }
    }
    [languages selectItemAtIndex:selectedIndex];
    alert.accessoryView = languages;
    [alert runModal];
    if (languages.indexOfSelectedItem == 0) {
        [[NSUserDefaults standardUserDefaults]
            removeObjectForKey:interface_language_key];
    } else {
        const std::size_t index = static_cast<std::size_t>(
            languages.indexOfSelectedItem - 1
        );
        [[NSUserDefaults standardUserDefaults]
            setObject:ns_string(orkela::language_tag(values[index]))
               forKey:interface_language_key];
    }
    [self applyLocalization];
}

- (void)loadBundledDemo {
    NSURL* url = [NSBundle.mainBundle
        URLForResource:@"emotional-piano"
         withExtension:@"resonith"];
    if (url != nil) {
        [self decodeURL:url name:@"Emotional Piano"];
    }
}

- (void)openDocument {
    NSOpenPanel* panel = [NSOpenPanel openPanel];
    panel.canChooseDirectories = NO;
    panel.allowsMultipleSelection = NO;
    UTType* resonith =
        [UTType typeWithIdentifier:@"org.scenelith.resonith"];
    if (resonith != nil) {
        panel.allowedContentTypes = @[resonith];
    }
    if ([panel runModal] == NSModalResponseOK && panel.URL != nil) {
        [self decodeURL:panel.URL name:panel.URL.lastPathComponent];
    }
}

- (void)decodeURL:(NSURL*)url name:(NSString*)name {
    NSData* data = [NSData dataWithContentsOfURL:url];
    if (data == nil || data.length > maximum_input_bytes) {
        self.statusLabel.stringValue =
            ui_text(orkela::text_id::playback_failed);
        return;
    }
    const auto* begin =
        static_cast<const std::uint8_t*>(data.bytes);
    std::vector<std::uint8_t> bytes(
        begin,
        begin + static_cast<std::size_t>(data.length)
    );
    auto decoded = std::make_shared<orkela::decoded_audio>();
    std::string error;
    if (
        !orkela::decode_resonith_bytes(
            std::move(bytes),
            decoded.get(),
            &error
        )
    ) {
        self.statusLabel.stringValue =
            ui_text(orkela::text_id::playback_failed);
        return;
    }
    AVAudioFormat* format = [[AVAudioFormat alloc]
        initWithCommonFormat:AVAudioPCMFormatFloat32
                  sampleRate:static_cast<double>(decoded->sample_rate)
                    channels:decoded->channels
                 interleaved:NO];
    AVAudioPCMBuffer* buffer = [[AVAudioPCMBuffer alloc]
        initWithPCMFormat:format
             frameCapacity:decoded->frame_count];
    if (buffer == nil || buffer.floatChannelData == nullptr) {
        return;
    }
    buffer.frameLength = decoded->frame_count;
    for (
        std::size_t channel = 0U;
        channel < decoded->channels;
        ++channel
    ) {
        float* output = buffer.floatChannelData[channel];
        for (
            std::size_t frame = 0U;
            frame < decoded->frame_count;
            ++frame
        ) {
            output[frame] = static_cast<float>(
                decoded->samples[
                    frame * decoded->channels + channel
                ]
            ) / 32768.0F;
        }
    }
    _decoded = decoded;
    _lastVisualFrame = std::numeric_limits<std::uint32_t>::max();
    self.buffer = buffer;
    self.titleLabel.stringValue = name;
    self.metadataLabel.stringValue = [NSString stringWithFormat:
        @"%u Hz • %u ch • C++23",
        decoded->sample_rate,
        decoded->channels];
    self.statusLabel.stringValue =
        ui_text(orkela::text_id::ready);
    self.progress.doubleValue = 0.0;
    [self.visual resetAnalysis];
    const std::size_t frames = std::min<std::size_t>(
        decoded->frame_count,
        4096U
    );
    [self.visual offerPCM:decoded->samples.data()
                 elements:frames * decoded->channels
                 channels:decoded->channels
               sampleRate:decoded->sample_rate];
}

- (void)togglePlayback {
    if (self.buffer == nil) {
        return;
    }
    if (self.player.isPlaying) {
        [self.player pause];
        self.playButton.title =
            ui_text(orkela::text_id::resume_action);
        self.statusLabel.stringValue =
            ui_text(orkela::text_id::paused);
        return;
    }
    if (self.engine != nil && self.player != nil) {
        [self.player play];
        self.playButton.title =
            ui_text(orkela::text_id::pause_action);
        self.statusLabel.stringValue =
            ui_text(orkela::text_id::playing);
        return;
    }
    self.engine = [[AVAudioEngine alloc] init];
    self.player = [[AVAudioPlayerNode alloc] init];
    [self.engine attachNode:self.player];
    [self.engine connect:self.player
                      to:self.engine.mainMixerNode
                  format:self.buffer.format];
    [self.player scheduleBuffer:self.buffer
                         atTime:nil
                        options:0
              completionHandler:^{
        dispatch_async(dispatch_get_main_queue(), ^{
            [self stopPlayback];
            self.progress.doubleValue = 1.0;
            self.statusLabel.stringValue =
                ui_text(orkela::text_id::playback_complete);
        });
    }];
    NSError* error = nil;
    if (![self.engine startAndReturnError:&error]) {
        self.statusLabel.stringValue =
            ui_text(orkela::text_id::playback_failed);
        return;
    }
    [self.player play];
    self.playButton.title =
        ui_text(orkela::text_id::pause_action);
    self.statusLabel.stringValue =
        ui_text(orkela::text_id::playing);
    self.timer = [NSTimer scheduledTimerWithTimeInterval:0.08
                                                  target:self
                                                selector:@selector(tick)
                                                userInfo:nil
                                                 repeats:YES];
}

- (void)tick {
    AVAudioTime* time = [self.player
        playerTimeForNodeTime:self.player.lastRenderTime];
    if (
        time == nil
        || _decoded == nullptr
        || _decoded->frame_count == 0U
    ) {
        return;
    }
    const std::uint32_t frame = static_cast<std::uint32_t>(
        std::clamp<AVAudioFramePosition>(
            time.sampleTime,
            0,
            static_cast<AVAudioFramePosition>(_decoded->frame_count)
        )
    );
    self.progress.doubleValue = static_cast<double>(frame)
        / static_cast<double>(_decoded->frame_count);
    if (frame == _lastVisualFrame) {
        return;
    }
    constexpr std::size_t window = 4096U;
    const std::size_t start = frame > window / 2U
        ? static_cast<std::size_t>(frame) - window / 2U
        : 0U;
    const std::size_t available =
        static_cast<std::size_t>(_decoded->frame_count) - start;
    const std::size_t count = std::min(window, available);
    [self.visual
        offerPCM:_decoded->samples.data()
            + start * _decoded->channels
        elements:count * _decoded->channels
        channels:_decoded->channels
      sampleRate:_decoded->sample_rate];
    _lastVisualFrame = frame;
}

- (void)stopPlayback {
    [self.timer invalidate];
    self.timer = nil;
    [self.player stop];
    [self.engine stop];
    self.player = nil;
    self.engine = nil;
    self.playButton.title =
        ui_text(orkela::text_id::play_action);
    self.statusLabel.stringValue =
        ui_text(orkela::text_id::stopped);
}

- (BOOL)windowShouldClose:(NSWindow*)sender {
    (void)sender;
    [NSApp terminate:nil];
    return YES;
}

@end

@interface OrkelaMacDelegate : NSObject <NSApplicationDelegate>
@property(nonatomic, strong) OrkelaMacController* controller;
@end

@implementation OrkelaMacDelegate

- (void)applicationDidFinishLaunching:(NSNotification*)notification {
    (void)notification;
    self.controller = [[OrkelaMacController alloc] init];
    [self.controller showWindow];
    [NSApp activateIgnoringOtherApps:YES];
}

- (BOOL)applicationShouldTerminateAfterLastWindowClosed:
        (NSApplication*)sender {
    (void)sender;
    return YES;
}

@end

int main(int argc, const char* argv[]) {
    (void)argc;
    (void)argv;
    @autoreleasepool {
        NSApplication* application = [NSApplication sharedApplication];
        application.activationPolicy =
            NSApplicationActivationPolicyRegular;
        OrkelaMacDelegate* delegate = [[OrkelaMacDelegate alloc] init];
        application.delegate = delegate;
        [application run];
    }
    return 0;
}
