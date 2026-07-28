#import <AVFAudio/AVFAudio.h>
#import <CommonCrypto/CommonDigest.h>
#import <UIKit/UIKit.h>
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>

#include "orkela/resonith_pull_decoder.h"
#include "orkela/localization.h"
#include "orkela/visual_analysis.h"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <limits>
#include <memory>
#include <span>
#include <string>
#include <utility>
#include <vector>

namespace {

constexpr std::size_t maximum_mobile_input_bytes =
    64ULL * 1024ULL * 1024ULL;
constexpr std::uint32_t ci_expected_sample_rate = 44100U;
constexpr std::uint32_t ci_expected_channels = 2U;
constexpr std::uint32_t ci_expected_frames = 352800U;
constexpr const char* ci_expected_pcm_sha256 =
    "3cfcae4996a08976f42ec83744ea0130935ca53d83b37129c001581697618618";
NSString* const interface_language_key = @"OrkelaInterfaceLanguage";

NSString* ns_string(std::string_view value) {
    return [[NSString alloc]
        initWithBytes:value.data()
               length:value.size()
             encoding:NSUTF8StringEncoding];
}

orkela::language active_language() {
    NSString* override = [
        [NSUserDefaults standardUserDefaults]
        stringForKey:interface_language_key
    ];
    NSString* tag = override.length == 0U
        ? NSLocale.preferredLanguages.firstObject
        : override;
    if (tag.length == 0U) {
        tag = @"en";
    }
    return orkela::language_from_tag(tag.UTF8String);
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

bool ci_smoke_enabled() noexcept {
    const char* value = std::getenv("ORKELA_CI_SMOKE");
    return value != nullptr && value[0] == '1' && value[1] == '\0';
}

NSString* pcm_sha256_hex(const std::vector<std::int16_t>& samples) {
    CC_SHA256_CTX context{};
    CC_SHA256_Init(&context);
    const auto* bytes = reinterpret_cast<const std::uint8_t*>(
        samples.data()
    );
    std::size_t remaining = samples.size() * sizeof(std::int16_t);
    while (remaining != 0U) {
        const std::size_t chunk = std::min(
            remaining,
            static_cast<std::size_t>(
                std::numeric_limits<CC_LONG>::max()
            )
        );
        CC_SHA256_Update(
            &context,
            bytes,
            static_cast<CC_LONG>(chunk)
        );
        bytes += chunk;
        remaining -= chunk;
    }
    unsigned char digest[CC_SHA256_DIGEST_LENGTH]{};
    CC_SHA256_Final(digest, &context);
    char encoded[CC_SHA256_DIGEST_LENGTH * 2U + 1U]{};
    constexpr char alphabet[] = "0123456789abcdef";
    for (std::size_t index = 0U; index < CC_SHA256_DIGEST_LENGTH; ++index) {
        const unsigned char value = digest[index];
        encoded[index * 2U] = alphabet[value >> 4U];
        encoded[index * 2U + 1U] = alphabet[value & 0x0FU];
    }
    return [NSString stringWithUTF8String:encoded];
}

void write_ci_smoke_marker(NSDictionary<NSString*, id>* marker) {
    if (!ci_smoke_enabled()) {
        return;
    }
    NSError* error = nil;
    NSData* json = [NSJSONSerialization dataWithJSONObject:marker
                                                   options:NSJSONWritingPrettyPrinted
                                                     error:&error];
    NSFileManager* fileManager = [NSFileManager defaultManager];
    NSURL* documents = [
        fileManager
        URLsForDirectory:NSDocumentDirectory
        inDomains:NSUserDomainMask
    ].firstObject;
    NSURL* destination = [
        documents
        URLByAppendingPathComponent:@"orkela-ci-smoke.json"
    ];
    if (
        json == nil
        || destination == nil
        || ![fileManager createDirectoryAtURL:documents
                   withIntermediateDirectories:YES
                                    attributes:nil
                                         error:&error]
        || ![json writeToURL:destination
                     options:NSDataWritingAtomic
                       error:&error]
    ) {
        NSLog(
            @"ORKELA_CI_SMOKE MARKER_ERROR %@",
            error.localizedDescription
        );
    }
}

bool write_ci_decode_pass(const orkela::decoded_audio& decoded) {
    if (!ci_smoke_enabled()) {
        return true;
    }
    NSString* pcmHash = pcm_sha256_hex(decoded.samples);
    const bool matches =
        decoded.sample_rate == ci_expected_sample_rate
        && decoded.channels == ci_expected_channels
        && decoded.frame_count == ci_expected_frames
        && [pcmHash isEqualToString:
            [NSString stringWithUTF8String:ci_expected_pcm_sha256]];
    NSDictionary<NSString*, id>* marker = @{
        @"schema": @1,
        @"status": matches ? @"pass" : @"fail",
        @"sample_rate": @(decoded.sample_rate),
        @"channels": @(decoded.channels),
        @"frames": @(decoded.frame_count),
        @"pcm16_sha256": pcmHash,
    };
    write_ci_smoke_marker(marker);
    NSLog(
        @"ORKELA_CI_SMOKE %@ frames=%u channels=%u sample_rate=%u pcm16_sha256=%@",
        matches ? @"PASS" : @"FAIL",
        decoded.frame_count,
        decoded.channels,
        decoded.sample_rate,
        pcmHash
    );
    return matches;
}

void write_ci_decode_failure(NSString* message) {
    if (!ci_smoke_enabled()) {
        return;
    }
    write_ci_smoke_marker(@{
        @"schema": @1,
        @"status": @"fail",
        @"error": message != nil ? message : @"unknown error",
    });
    NSLog(
        @"ORKELA_CI_SMOKE FAIL error=%@",
        message != nil ? message : @"unknown error"
    );
}

UIColor* orkela_color(
    CGFloat red,
    CGFloat green,
    CGFloat blue
) {
    return [UIColor colorWithRed:red green:green blue:blue alpha:1.0];
}

UIButton* orkela_button(NSString* title) {
    UIButton* button = [UIButton buttonWithType:UIButtonTypeSystem];
    UIButtonConfiguration* configuration =
        [UIButtonConfiguration filledButtonConfiguration];
    configuration.title = title;
    configuration.baseForegroundColor = UIColor.whiteColor;
    configuration.baseBackgroundColor = orkela_color(0.17, 0.15, 0.26);
    configuration.cornerStyle = UIButtonConfigurationCornerStyleLarge;
    configuration.contentInsets =
        NSDirectionalEdgeInsetsMake(14.0, 24.0, 14.0, 24.0);
    button.configuration = configuration;
    return button;
}

}  // namespace

@interface OrkelaVisualView : UIView {
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
- (void)cycleMode;
- (orkela::visual_mode)visualMode;
@end

@implementation OrkelaVisualView

- (instancetype)init {
    self = [super init];
    if (self != nil) {
        _mode = orkela::visual_mode::field;
        self.backgroundColor = orkela_color(0.055, 0.060, 0.105);
        self.layer.cornerRadius = 30.0;
        self.layer.borderWidth = 1.0;
        self.layer.borderColor =
            orkela_color(0.24, 0.25, 0.39).CGColor;
        self.clipsToBounds = YES;
        UITapGestureRecognizer* tap = [[UITapGestureRecognizer alloc]
            initWithTarget:self
                    action:@selector(cycleMode)];
        [self addGestureRecognizer:tap];
        self.isAccessibilityElement = YES;
        self.accessibilityLabel =
            ui_text(mode_text_id(orkela::visual_mode::field));
        self.accessibilityHint = ui_text(orkela::text_id::visual_hint);
    }
    return self;
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
    [self setNeedsDisplay];
}

- (void)resetAnalysis {
    _analyzer.reset();
    _snapshot = {};
    [self setNeedsDisplay];
}

- (void)cycleMode {
    _mode = orkela::next_visual_mode(_mode);
    self.accessibilityLabel = ui_text(mode_text_id(_mode));
    [self setNeedsDisplay];
}

- (orkela::visual_mode)visualMode {
    return _mode;
}

- (void)drawRect:(CGRect)rectangle {
    [super drawRect:rectangle];
    const CGFloat inset = 18.0;
    const CGRect area = CGRectInset(rectangle, inset, inset + 8.0);
    NSString* label = [
        ui_text(mode_text_id(_mode))
        uppercaseStringWithLocale:[NSLocale currentLocale]
    ];
    [label drawAtPoint:CGPointMake(inset, 12.0)
        withAttributes:@{
            NSFontAttributeName:
                [UIFont systemFontOfSize:11.0 weight:UIFontWeightSemibold],
            NSForegroundColorAttributeName:
                orkela_color(0.64, 0.60, 1.0),
        }];

    if (_mode == orkela::visual_mode::spectrum) {
        const CGFloat width = CGRectGetWidth(area)
            / static_cast<CGFloat>(orkela::visual_spectrum_bands);
        for (
            std::size_t band = 0U;
            band < orkela::visual_spectrum_bands;
            ++band
        ) {
            const CGFloat level =
                static_cast<CGFloat>(_snapshot.spectrum[band]);
            const CGFloat height = 2.0 + level * CGRectGetHeight(area);
            [orkela_color(0.42, 0.36 + 0.30 * level, 1.0)
                setFill];
            UIBezierPath* bar = [UIBezierPath
                bezierPathWithRoundedRect:CGRectMake(
                    CGRectGetMinX(area)
                        + static_cast<CGFloat>(band) * width,
                    CGRectGetMaxY(area) - height,
                    std::max<CGFloat>(1.0, width - 2.0),
                    height
                )
                cornerRadius:2.0];
            [bar fill];
        }
        return;
    }

    if (_mode == orkela::visual_mode::history) {
        const std::size_t columns = std::max<std::size_t>(
            1U,
            _snapshot.history_columns
        );
        const CGFloat width =
            CGRectGetWidth(area) / static_cast<CGFloat>(columns);
        const CGFloat height = CGRectGetHeight(area)
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
                        0.30 + 0.30 * level,
                        0.35 + 0.45 * level,
                        0.88 + 0.12 * level
                    )
                    setFill
                ];
                UIRectFill(CGRectMake(
                    CGRectGetMinX(area)
                        + static_cast<CGFloat>(column) * width,
                    CGRectGetMaxY(area)
                        - static_cast<CGFloat>(band + 1U) * height,
                    width + 0.5,
                    height + 0.5
                ));
            }
        }
        return;
    }

    const CGFloat center = CGRectGetMidY(area);
    const CGFloat step = CGRectGetWidth(area)
        / static_cast<CGFloat>(orkela::visual_wave_points - 1U);
    UIBezierPath* wave = [UIBezierPath bezierPath];
    for (
        std::size_t index = 0U;
        index < orkela::visual_wave_points;
        ++index
    ) {
        const CGFloat x = CGRectGetMinX(area)
            + static_cast<CGFloat>(index) * step;
        const CGFloat y = center
            - static_cast<CGFloat>(_snapshot.wave[index])
                * CGRectGetHeight(area) * 0.47;
        if (index == 0U) {
            [wave moveToPoint:CGPointMake(x, y)];
        } else {
            [wave addLineToPoint:CGPointMake(x, y)];
        }
    }
    wave.lineWidth = _mode == orkela::visual_mode::field ? 2.8 : 1.8;
    [orkela_color(0.43, 0.39, 1.0) setStroke];
    [wave stroke];

    if (_mode == orkela::visual_mode::field) {
        const CGFloat width = CGRectGetWidth(area)
            / static_cast<CGFloat>(orkela::visual_spectrum_bands);
        for (
            std::size_t band = 0U;
            band < orkela::visual_spectrum_bands;
            ++band
        ) {
            const CGFloat level =
                static_cast<CGFloat>(_snapshot.spectrum[band]);
            [[
                orkela_color(0.30, 0.60, 0.98)
                colorWithAlphaComponent:0.12 + level * 0.35
            ] setFill];
            UIRectFill(CGRectMake(
                CGRectGetMinX(area)
                    + static_cast<CGFloat>(band) * width,
                CGRectGetMaxY(area)
                    - level * CGRectGetHeight(area) * 0.62,
                std::max<CGFloat>(1.0, width - 1.0),
                level * CGRectGetHeight(area) * 0.62
            ));
        }
    }
}

@end

@interface OrkelaViewController
    : UIViewController <UIDocumentPickerDelegate>
{
@private
    std::shared_ptr<orkela::decoded_audio> _decodedAudio;
    std::uint32_t _lastVisualFrame;
}
@property(nonatomic, strong) UILabel* titleLabel;
@property(nonatomic, strong) UILabel* metadataLabel;
@property(nonatomic, strong) UILabel* statusLabel;
@property(nonatomic, strong) UIProgressView* progressView;
@property(nonatomic, strong) UIButton* playButton;
@property(nonatomic, strong) UIButton* openButton;
@property(nonatomic, strong) UIButton* stopButton;
@property(nonatomic, strong) UIButton* settingsButton;
@property(nonatomic, strong) OrkelaVisualView* visualView;
@property(nonatomic, strong) AVAudioEngine* audioEngine;
@property(nonatomic, strong) AVAudioPlayerNode* playerNode;
@property(nonatomic, strong) AVAudioPCMBuffer* activeBuffer;
@property(nonatomic, strong) NSTimer* progressTimer;
@property(nonatomic, assign) AVAudioFramePosition totalFrames;
@property(nonatomic, assign) BOOL decoding;
@end

@implementation OrkelaViewController

- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = orkela_color(0.035, 0.043, 0.078);
    [self buildInterface];
    [self loadBundledDemonstration];
}

- (void)buildInterface {
    UILabel* brand = [[UILabel alloc] init];
    brand.translatesAutoresizingMaskIntoConstraints = NO;
    brand.text = @"O R K E L A";
    brand.textColor = orkela_color(0.61, 0.55, 1.0);
    brand.font = [UIFont systemFontOfSize:13.0 weight:UIFontWeightBold];

    self.titleLabel = [[UILabel alloc] init];
    self.titleLabel.translatesAutoresizingMaskIntoConstraints = NO;
    self.titleLabel.text = ui_text(orkela::text_id::native_resonith);
    self.titleLabel.textColor = UIColor.whiteColor;
    self.titleLabel.font =
        [UIFont systemFontOfSize:34.0 weight:UIFontWeightBold];
    self.titleLabel.textAlignment = NSTextAlignmentCenter;
    self.titleLabel.numberOfLines = 2;

    self.metadataLabel = [[UILabel alloc] init];
    self.metadataLabel.translatesAutoresizingMaskIntoConstraints = NO;
    self.metadataLabel.text = [
        ui_text(orkela::text_id::portable_session)
        stringByAppendingString:@" • Apple Audio"
    ];
    self.metadataLabel.textColor = orkela_color(0.63, 0.66, 0.73);
    self.metadataLabel.font = [UIFont systemFontOfSize:15.0];
    self.metadataLabel.textAlignment = NSTextAlignmentCenter;

    self.visualView = [[OrkelaVisualView alloc] init];
    self.visualView.translatesAutoresizingMaskIntoConstraints = NO;

    self.progressView =
        [[UIProgressView alloc] initWithProgressViewStyle:
            UIProgressViewStyleDefault];
    self.progressView.translatesAutoresizingMaskIntoConstraints = NO;
    self.progressView.progressTintColor =
        orkela_color(0.61, 0.55, 1.0);
    self.progressView.trackTintColor = orkela_color(0.15, 0.16, 0.23);
    self.progressView.accessibilityLabel =
        ui_text(orkela::text_id::playback_timeline);

    self.openButton = orkela_button(
        ui_text(orkela::text_id::open_resonith)
    );
    self.openButton.translatesAutoresizingMaskIntoConstraints = NO;
    [self.openButton addTarget:self
                   action:@selector(openDocument)
         forControlEvents:UIControlEventTouchUpInside];

    self.playButton = orkela_button(
        ui_text(orkela::text_id::play_action)
    );
    self.playButton.translatesAutoresizingMaskIntoConstraints = NO;
    [self.playButton addTarget:self
                        action:@selector(togglePlayback)
              forControlEvents:UIControlEventTouchUpInside];

    self.stopButton = orkela_button(
        ui_text(orkela::text_id::stop_action)
    );
    self.stopButton.translatesAutoresizingMaskIntoConstraints = NO;
    [self.stopButton addTarget:self
                   action:@selector(stopPlayback)
         forControlEvents:UIControlEventTouchUpInside];

    self.settingsButton = [UIButton buttonWithType:UIButtonTypeSystem];
    self.settingsButton.translatesAutoresizingMaskIntoConstraints = NO;
    [self.settingsButton setImage:
        [UIImage systemImageNamed:@"gearshape.fill"]
                        forState:UIControlStateNormal];
    self.settingsButton.tintColor = orkela_color(0.70, 0.67, 1.0);
    self.settingsButton.accessibilityLabel =
        ui_text(orkela::text_id::settings);
    [self.settingsButton addTarget:self
                            action:@selector(showSettings)
                  forControlEvents:UIControlEventTouchUpInside];

    UIStackView* controls = [[UIStackView alloc] initWithArrangedSubviews:@[
        self.openButton,
        self.playButton,
        self.stopButton,
    ]];
    controls.translatesAutoresizingMaskIntoConstraints = NO;
    controls.axis = UILayoutConstraintAxisHorizontal;
    controls.spacing = 12.0;
    controls.alignment = UIStackViewAlignmentCenter;
    controls.distribution = UIStackViewDistributionFillEqually;

    self.statusLabel = [[UILabel alloc] init];
    self.statusLabel.translatesAutoresizingMaskIntoConstraints = NO;
    self.statusLabel.text = ui_text(orkela::text_id::authenticating);
    self.statusLabel.textColor = orkela_color(0.78, 0.80, 0.86);
    self.statusLabel.font = [UIFont systemFontOfSize:14.0];
    self.statusLabel.textAlignment = NSTextAlignmentCenter;
    self.statusLabel.numberOfLines = 2;

    [self.view addSubview:brand];
    [self.view addSubview:self.titleLabel];
    [self.view addSubview:self.metadataLabel];
    [self.view addSubview:self.visualView];
    [self.view addSubview:self.progressView];
    [self.view addSubview:controls];
    [self.view addSubview:self.statusLabel];
    [self.view addSubview:self.settingsButton];

    UILayoutGuide* safe = self.view.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [brand.topAnchor constraintEqualToAnchor:safe.topAnchor
                                        constant:24.0],
        [brand.centerXAnchor constraintEqualToAnchor:safe.centerXAnchor],
        [self.settingsButton.centerYAnchor
            constraintEqualToAnchor:brand.centerYAnchor],
        [self.settingsButton.trailingAnchor
            constraintEqualToAnchor:safe.trailingAnchor
                           constant:-22.0],
        [self.settingsButton.widthAnchor constraintEqualToConstant:44.0],
        [self.settingsButton.heightAnchor constraintEqualToConstant:44.0],
        [self.titleLabel.topAnchor constraintEqualToAnchor:brand.bottomAnchor
                                                   constant:26.0],
        [self.titleLabel.leadingAnchor
            constraintGreaterThanOrEqualToAnchor:safe.leadingAnchor
                                       constant:24.0],
        [self.titleLabel.trailingAnchor
            constraintLessThanOrEqualToAnchor:safe.trailingAnchor
                                    constant:-24.0],
        [self.titleLabel.centerXAnchor
            constraintEqualToAnchor:safe.centerXAnchor],
        [self.metadataLabel.topAnchor
            constraintEqualToAnchor:self.titleLabel.bottomAnchor
                           constant:8.0],
        [self.metadataLabel.centerXAnchor
            constraintEqualToAnchor:safe.centerXAnchor],
        [self.visualView.topAnchor
            constraintEqualToAnchor:self.metadataLabel.bottomAnchor
                           constant:34.0],
        [self.visualView.centerXAnchor
            constraintEqualToAnchor:safe.centerXAnchor],
        [self.visualView.leadingAnchor
            constraintEqualToAnchor:safe.leadingAnchor
                           constant:24.0],
        [self.visualView.trailingAnchor
            constraintEqualToAnchor:safe.trailingAnchor
                           constant:-24.0],
        [self.visualView.heightAnchor constraintEqualToConstant:248.0],
        [self.progressView.topAnchor
            constraintEqualToAnchor:self.visualView.bottomAnchor
                                                    constant:34.0],
        [self.progressView.leadingAnchor
            constraintEqualToAnchor:safe.leadingAnchor
                           constant:28.0],
        [self.progressView.trailingAnchor
            constraintEqualToAnchor:safe.trailingAnchor
                           constant:-28.0],
        [controls.topAnchor
            constraintEqualToAnchor:self.progressView.bottomAnchor
                           constant:24.0],
        [controls.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor
                                               constant:24.0],
        [controls.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor
                                                constant:-24.0],
        [self.statusLabel.topAnchor constraintEqualToAnchor:controls.bottomAnchor
                                                   constant:24.0],
        [self.statusLabel.leadingAnchor
            constraintEqualToAnchor:safe.leadingAnchor
                           constant:24.0],
        [self.statusLabel.trailingAnchor
            constraintEqualToAnchor:safe.trailingAnchor
                           constant:-24.0],
    ]];

    [self.view layoutIfNeeded];
}

- (void)applyLocalization {
    self.titleLabel.text = ui_text(orkela::text_id::native_resonith);
    self.metadataLabel.text = [
        ui_text(orkela::text_id::portable_session)
        stringByAppendingString:@" • Apple Audio"
    ];
    self.settingsButton.accessibilityLabel =
        ui_text(orkela::text_id::settings);
    self.progressView.accessibilityLabel =
        ui_text(orkela::text_id::playback_timeline);
    [self.openButton
        setTitle:ui_text(orkela::text_id::open_resonith)
        forState:UIControlStateNormal];
    [self.stopButton
        setTitle:ui_text(orkela::text_id::stop_action)
        forState:UIControlStateNormal];
    if (self.playerNode.isPlaying) {
        [self.playButton
            setTitle:ui_text(orkela::text_id::pause_action)
            forState:UIControlStateNormal];
        self.statusLabel.text = ui_text(orkela::text_id::playing);
    } else {
        [self.playButton
            setTitle:ui_text(orkela::text_id::play_action)
            forState:UIControlStateNormal];
        self.statusLabel.text = _decodedAudio == nullptr
            ? ui_text(orkela::text_id::authenticating)
            : ui_text(orkela::text_id::ready);
    }
    self.visualView.accessibilityLabel =
        ui_text(mode_text_id(self.visualView.visualMode));
    self.visualView.accessibilityHint =
        ui_text(orkela::text_id::visual_hint);
    [self.visualView setNeedsDisplay];
}

- (void)showSettings {
    UIAlertController* settings = [UIAlertController
        alertControllerWithTitle:ui_text(orkela::text_id::settings)
                         message:ui_text(
                             orkela::text_id::language_description
                         )
                  preferredStyle:UIAlertControllerStyleActionSheet];
    NSUserDefaults* defaults = [NSUserDefaults standardUserDefaults];
    NSString* selected = [defaults stringForKey:interface_language_key];
    NSString* systemTitle = ui_text(orkela::text_id::system_default);
    if (selected.length == 0U) {
        systemTitle = [@"✓  " stringByAppendingString:systemTitle];
    }
    [settings addAction:[UIAlertAction
        actionWithTitle:systemTitle
                  style:UIAlertActionStyleDefault
                handler:^(__unused UIAlertAction* action) {
        [defaults removeObjectForKey:interface_language_key];
        [self applyLocalization];
    }]];

    constexpr std::array languages = {
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
    for (orkela::language language : languages) {
        NSString* tag = ns_string(orkela::language_tag(language));
        NSString* title = ns_string(orkela::language_autonym(language));
        if ([selected isEqualToString:tag]) {
            title = [@"✓  " stringByAppendingString:title];
        }
        [settings addAction:[UIAlertAction
            actionWithTitle:title
                      style:UIAlertActionStyleDefault
                    handler:^(__unused UIAlertAction* action) {
            [defaults setObject:tag forKey:interface_language_key];
            [self applyLocalization];
        }]];
    }
    [settings addAction:[UIAlertAction
        actionWithTitle:ui_text(orkela::text_id::done)
                  style:UIAlertActionStyleCancel
                handler:nil]];
    UIPopoverPresentationController* popover =
        settings.popoverPresentationController;
    if (popover != nil) {
        popover.sourceView = self.settingsButton;
        popover.sourceRect = self.settingsButton.bounds;
    }
    [self presentViewController:settings animated:YES completion:nil];
}

- (void)loadBundledDemonstration {
    NSString* path = [NSBundle.mainBundle
        pathForResource:@"emotional-piano"
                 ofType:@"resonith"];
    if (path == nil) {
        self.statusLabel.text =
            ui_text(orkela::text_id::playback_failed);
        return;
    }
    [self decodeURL:[NSURL fileURLWithPath:path]
               name:@"Emotional Piano • Resonith demonstration"];
}

- (void)openDocument {
    UTType* resonith = [UTType typeWithIdentifier:@"org.scenelith.resonith"];
    NSArray<UTType*>* types = resonith == nil
        ? @[UTTypeData]
        : @[resonith];
    UIDocumentPickerViewController* picker =
        [[UIDocumentPickerViewController alloc]
            initForOpeningContentTypes:types
                                asCopy:YES];
    picker.delegate = self;
    picker.allowsMultipleSelection = NO;
    [self presentViewController:picker animated:YES completion:nil];
}

- (void)documentPicker:
            (UIDocumentPickerViewController*)controller
        didPickDocumentsAtURLs:(NSArray<NSURL*>*)urls {
    (void)controller;
    NSURL* url = urls.firstObject;
    if (url != nil) {
        [self decodeURL:url name:url.lastPathComponent];
    }
}

- (void)decodeURL:(NSURL*)url name:(NSString*)name {
    if (self.decoding) {
        return;
    }
    self.decoding = YES;
    self.statusLabel.text =
        ui_text(orkela::text_id::authenticating);
    [self stopEngine];

    dispatch_async(
        dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0),
        ^{
            NSError* readError = nil;
            NSData* data = [NSData dataWithContentsOfURL:url
                                                options:NSDataReadingMappedIfSafe
                                                  error:&readError];
            if (data == nil) {
                [self reportError:readError.localizedDescription];
                return;
            }
            if (data.length > maximum_mobile_input_bytes) {
                [self reportError:@"Mobile alpha input exceeds 64 MiB"];
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
                [self reportError:
                    [NSString stringWithUTF8String:error.c_str()]];
                return;
            }
            dispatch_async(dispatch_get_main_queue(), ^{
                [self installDecodedAudio:decoded name:name];
            });
        }
    );
}

- (void)installDecodedAudio:
            (std::shared_ptr<orkela::decoded_audio>)decoded
                       name:(NSString*)name {
    self.decoding = NO;
    if (
        decoded == nullptr
        || decoded->samples.empty()
        || decoded->channels == 0U
    ) {
        [self reportError:@"Decoder returned no PCM"];
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
        [self reportError:@"Cannot allocate Apple audio buffer"];
        return;
    }
    buffer.frameLength = decoded->frame_count;

    const std::size_t channels = decoded->channels;
    const std::size_t frames = decoded->frame_count;
    for (std::size_t channel = 0U; channel < channels; ++channel) {
        float* output = buffer.floatChannelData[channel];
        for (std::size_t frame = 0U; frame < frames; ++frame) {
            const std::int16_t sample =
                decoded->samples[frame * channels + channel];
            output[frame] = static_cast<float>(sample) / 32768.0F;
        }
    }

    self.activeBuffer = buffer;
    _decodedAudio = decoded;
    _lastVisualFrame = std::numeric_limits<std::uint32_t>::max();
    [self.visualView resetAnalysis];
    const std::size_t initialFrames = std::min<std::size_t>(
        frames,
        4096U
    );
    [self.visualView offerPCM:decoded->samples.data()
                     elements:initialFrames * channels
                     channels:decoded->channels
                   sampleRate:decoded->sample_rate];
    self.totalFrames = decoded->frame_count;
    self.titleLabel.text = name;
    self.metadataLabel.text = [NSString stringWithFormat:
        @"%u Hz • %u %@",
        decoded->sample_rate,
        decoded->channels,
        decoded->channels == 1U ? @"channel" : @"channels"];
    self.statusLabel.text = ui_text(orkela::text_id::ready);
    self.progressView.progress = 0.0F;
    [self.playButton
        setTitle:ui_text(orkela::text_id::play_action)
        forState:UIControlStateNormal];
    if (!write_ci_decode_pass(*decoded)) {
        self.statusLabel.text =
            ui_text(orkela::text_id::playback_failed);
    }
}

- (void)togglePlayback {
    if (self.activeBuffer == nil || self.decoding) {
        return;
    }
    if (self.playerNode.isPlaying) {
        [self.playerNode pause];
        [self.playButton
            setTitle:ui_text(orkela::text_id::resume_action)
            forState:UIControlStateNormal];
        self.statusLabel.text = ui_text(orkela::text_id::paused);
        return;
    }
    if (self.audioEngine != nil && self.playerNode != nil) {
        [self.playerNode play];
        [self.playButton
            setTitle:ui_text(orkela::text_id::pause_action)
            forState:UIControlStateNormal];
        self.statusLabel.text = ui_text(orkela::text_id::playing);
        return;
    }
    [self startEngine];
}

- (void)startEngine {
    NSError* sessionError = nil;
    AVAudioSession* session = AVAudioSession.sharedInstance;
    [session setCategory:AVAudioSessionCategoryPlayback
                   mode:AVAudioSessionModeDefault
                options:0
                  error:&sessionError];
    if (sessionError != nil) {
        [self reportError:sessionError.localizedDescription];
        return;
    }
    [session setActive:YES error:&sessionError];
    if (sessionError != nil) {
        [self reportError:sessionError.localizedDescription];
        return;
    }

    self.audioEngine = [[AVAudioEngine alloc] init];
    self.playerNode = [[AVAudioPlayerNode alloc] init];
    [self.audioEngine attachNode:self.playerNode];
    [self.audioEngine connect:self.playerNode
                           to:self.audioEngine.mainMixerNode
                       format:self.activeBuffer.format];
    [self.playerNode scheduleBuffer:self.activeBuffer
                             atTime:nil
                            options:0
                  completionHandler:^{
        dispatch_async(dispatch_get_main_queue(), ^{
            [self stopEngine];
            self.progressView.progress = 1.0F;
            self.statusLabel.text =
                ui_text(orkela::text_id::playback_complete);
        });
    }];

    NSError* engineError = nil;
    if (![self.audioEngine startAndReturnError:&engineError]) {
        [self reportError:engineError.localizedDescription];
        return;
    }
    [self.playerNode play];
    [self.playButton
        setTitle:ui_text(orkela::text_id::pause_action)
        forState:UIControlStateNormal];
    self.statusLabel.text = ui_text(orkela::text_id::playing);
    self.progressTimer = [NSTimer
        scheduledTimerWithTimeInterval:0.1
                                target:self
                              selector:@selector(updateProgress)
                              userInfo:nil
                               repeats:YES];
}

- (void)updateProgress {
    AVAudioTime* nodeTime = [self.playerNode
        playerTimeForNodeTime:self.playerNode.lastRenderTime];
    if (nodeTime != nil && self.totalFrames > 0) {
        const double fraction =
            static_cast<double>(nodeTime.sampleTime)
            / static_cast<double>(self.totalFrames);
        self.progressView.progress =
            static_cast<float>(fraction > 1.0 ? 1.0 : fraction);
        if (_decodedAudio != nullptr) {
            const std::uint32_t frame = static_cast<std::uint32_t>(
                std::clamp<AVAudioFramePosition>(
                    nodeTime.sampleTime,
                    0,
                    static_cast<AVAudioFramePosition>(
                        _decodedAudio->frame_count
                    )
                )
            );
            if (frame != _lastVisualFrame) {
                constexpr std::size_t window = 4096U;
                const std::size_t start = frame > window / 2U
                    ? static_cast<std::size_t>(frame) - window / 2U
                    : 0U;
                const std::size_t available =
                    static_cast<std::size_t>(_decodedAudio->frame_count)
                    - std::min(
                        start,
                        static_cast<std::size_t>(
                            _decodedAudio->frame_count
                        )
                    );
                const std::size_t count =
                    std::min(window, available);
                [self.visualView
                    offerPCM:_decodedAudio->samples.data()
                        + start * _decodedAudio->channels
                    elements:count * _decodedAudio->channels
                    channels:_decodedAudio->channels
                  sampleRate:_decodedAudio->sample_rate];
                _lastVisualFrame = frame;
            }
        }
    }
}

- (void)stopPlayback {
    [self stopEngine];
    self.progressView.progress = 0.0F;
    self.statusLabel.text = ui_text(orkela::text_id::stopped);
}

- (void)stopEngine {
    [self.progressTimer invalidate];
    self.progressTimer = nil;
    [self.playerNode stop];
    [self.audioEngine stop];
    self.playerNode = nil;
    self.audioEngine = nil;
    [self.playButton
        setTitle:ui_text(orkela::text_id::play_action)
        forState:UIControlStateNormal];
}

- (void)reportError:(NSString*)message {
    write_ci_decode_failure(message);
    dispatch_async(dispatch_get_main_queue(), ^{
        self.decoding = NO;
        [self stopEngine];
        NSString* detail =
            message != nil ? message : @"unknown error";
        self.statusLabel.text = [
            [ui_text(orkela::text_id::playback_failed)
                stringByAppendingString:@": "]
            stringByAppendingString:detail
        ];
    });
}

@end

@interface OrkelaAppDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic, strong) UIWindow* window;
@end

@implementation OrkelaAppDelegate

- (BOOL)application:
            (UIApplication*)application
        didFinishLaunchingWithOptions:
            (NSDictionary<UIApplicationLaunchOptionsKey, id>*)options {
    (void)application;
    (void)options;
    self.window = [[UIWindow alloc]
        initWithFrame:UIScreen.mainScreen.bounds];
    self.window.rootViewController = [[OrkelaViewController alloc] init];
    [self.window makeKeyAndVisible];
    return YES;
}

@end

int main(int argc, char* argv[]) {
    @autoreleasepool {
        return UIApplicationMain(
            argc,
            argv,
            nil,
            NSStringFromClass([OrkelaAppDelegate class])
        );
    }
}
