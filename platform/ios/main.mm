#import <AVFAudio/AVFAudio.h>
#import <UIKit/UIKit.h>
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>

#include "orkela/resonith_pull_decoder.h"

#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <utility>
#include <vector>

namespace {

constexpr std::size_t maximum_mobile_input_bytes =
    64ULL * 1024ULL * 1024ULL;

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

@interface OrkelaViewController
    : UIViewController <UIDocumentPickerDelegate>
@property(nonatomic, strong) UILabel* titleLabel;
@property(nonatomic, strong) UILabel* metadataLabel;
@property(nonatomic, strong) UILabel* statusLabel;
@property(nonatomic, strong) UIProgressView* progressView;
@property(nonatomic, strong) UIButton* playButton;
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
    self.titleLabel.text = @"Native Resonith";
    self.titleLabel.textColor = UIColor.whiteColor;
    self.titleLabel.font =
        [UIFont systemFontOfSize:34.0 weight:UIFontWeightBold];
    self.titleLabel.textAlignment = NSTextAlignmentCenter;
    self.titleLabel.numberOfLines = 2;

    self.metadataLabel = [[UILabel alloc] init];
    self.metadataLabel.translatesAutoresizingMaskIntoConstraints = NO;
    self.metadataLabel.text = @"C++23 portable session • Apple audio";
    self.metadataLabel.textColor = orkela_color(0.63, 0.66, 0.73);
    self.metadataLabel.font = [UIFont systemFontOfSize:15.0];
    self.metadataLabel.textAlignment = NSTextAlignmentCenter;

    UIView* art = [[UIView alloc] init];
    art.translatesAutoresizingMaskIntoConstraints = NO;
    art.layer.cornerRadius = 30.0;
    CAGradientLayer* gradient = [CAGradientLayer layer];
    gradient.colors = @[
        (__bridge id)orkela_color(0.49, 0.41, 1.0).CGColor,
        (__bridge id)orkela_color(0.24, 0.79, 1.0).CGColor,
        (__bridge id)orkela_color(0.35, 0.88, 0.71).CGColor,
    ];
    gradient.startPoint = CGPointMake(0.0, 0.0);
    gradient.endPoint = CGPointMake(1.0, 1.0);
    gradient.cornerRadius = 30.0;
    [art.layer addSublayer:gradient];

    self.progressView =
        [[UIProgressView alloc] initWithProgressViewStyle:
            UIProgressViewStyleDefault];
    self.progressView.translatesAutoresizingMaskIntoConstraints = NO;
    self.progressView.progressTintColor =
        orkela_color(0.61, 0.55, 1.0);
    self.progressView.trackTintColor = orkela_color(0.15, 0.16, 0.23);

    UIButton* openButton = orkela_button(@"Open");
    openButton.translatesAutoresizingMaskIntoConstraints = NO;
    [openButton addTarget:self
                   action:@selector(openDocument)
         forControlEvents:UIControlEventTouchUpInside];

    self.playButton = orkela_button(@"Play");
    self.playButton.translatesAutoresizingMaskIntoConstraints = NO;
    [self.playButton addTarget:self
                        action:@selector(togglePlayback)
              forControlEvents:UIControlEventTouchUpInside];

    UIButton* stopButton = orkela_button(@"Stop");
    stopButton.translatesAutoresizingMaskIntoConstraints = NO;
    [stopButton addTarget:self
                   action:@selector(stopPlayback)
         forControlEvents:UIControlEventTouchUpInside];

    UIStackView* controls = [[UIStackView alloc] initWithArrangedSubviews:@[
        openButton,
        self.playButton,
        stopButton,
    ]];
    controls.translatesAutoresizingMaskIntoConstraints = NO;
    controls.axis = UILayoutConstraintAxisHorizontal;
    controls.spacing = 12.0;
    controls.alignment = UIStackViewAlignmentCenter;
    controls.distribution = UIStackViewDistributionFillEqually;

    self.statusLabel = [[UILabel alloc] init];
    self.statusLabel.translatesAutoresizingMaskIntoConstraints = NO;
    self.statusLabel.text = @"Loading signed demonstration…";
    self.statusLabel.textColor = orkela_color(0.78, 0.80, 0.86);
    self.statusLabel.font = [UIFont systemFontOfSize:14.0];
    self.statusLabel.textAlignment = NSTextAlignmentCenter;
    self.statusLabel.numberOfLines = 2;

    [self.view addSubview:brand];
    [self.view addSubview:self.titleLabel];
    [self.view addSubview:self.metadataLabel];
    [self.view addSubview:art];
    [self.view addSubview:self.progressView];
    [self.view addSubview:controls];
    [self.view addSubview:self.statusLabel];

    UILayoutGuide* safe = self.view.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [brand.topAnchor constraintEqualToAnchor:safe.topAnchor
                                        constant:24.0],
        [brand.centerXAnchor constraintEqualToAnchor:safe.centerXAnchor],
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
        [art.topAnchor constraintEqualToAnchor:self.metadataLabel.bottomAnchor
                                      constant:34.0],
        [art.centerXAnchor constraintEqualToAnchor:safe.centerXAnchor],
        [art.widthAnchor constraintEqualToConstant:248.0],
        [art.heightAnchor constraintEqualToAnchor:art.widthAnchor],
        [self.progressView.topAnchor constraintEqualToAnchor:art.bottomAnchor
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
    gradient.frame = art.bounds;
}

- (void)loadBundledDemonstration {
    NSString* path = [NSBundle.mainBundle
        pathForResource:@"emotional-piano"
                 ofType:@"resonith"];
    if (path == nil) {
        self.statusLabel.text = @"Bundled demonstration is unavailable";
        return;
    }
    [self decodeURL:[NSURL fileURLWithPath:path]
               name:@"Emotional Piano • Resonith demonstration"];
}

- (void)openDocument {
    UTType* resonith = [UTType typeWithIdentifier:@"org.scenelith.resonith"];
    NSArray<UTType*>* types = resonith == nil
        ? @[[UTType data]]
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
    self.statusLabel.text = @"Authenticating Resonith stream…";
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
    self.totalFrames = decoded->frame_count;
    self.titleLabel.text = name;
    self.metadataLabel.text = [NSString stringWithFormat:
        @"%u Hz • %u %@",
        decoded->sample_rate,
        decoded->channels,
        decoded->channels == 1U ? @"channel" : @"channels"];
    self.statusLabel.text =
        @"Ready • native decode • no WAV intermediary";
    self.progressView.progress = 0.0F;
    [self.playButton setTitle:@"Play" forState:UIControlStateNormal];
}

- (void)togglePlayback {
    if (self.activeBuffer == nil || self.decoding) {
        return;
    }
    if (self.playerNode.isPlaying) {
        [self.playerNode pause];
        [self.playButton setTitle:@"Resume" forState:UIControlStateNormal];
        self.statusLabel.text = @"Paused";
        return;
    }
    if (self.audioEngine != nil && self.playerNode != nil) {
        [self.playerNode play];
        [self.playButton setTitle:@"Pause" forState:UIControlStateNormal];
        self.statusLabel.text = @"Playing";
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
            self.statusLabel.text = @"Playback complete";
        });
    }];

    NSError* engineError = nil;
    if (![self.audioEngine startAndReturnError:&engineError]) {
        [self reportError:engineError.localizedDescription];
        return;
    }
    [self.playerNode play];
    [self.playButton setTitle:@"Pause" forState:UIControlStateNormal];
    self.statusLabel.text = @"Playing";
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
    }
}

- (void)stopPlayback {
    [self stopEngine];
    self.progressView.progress = 0.0F;
    self.statusLabel.text = @"Stopped";
}

- (void)stopEngine {
    [self.progressTimer invalidate];
    self.progressTimer = nil;
    [self.playerNode stop];
    [self.audioEngine stop];
    self.playerNode = nil;
    self.audioEngine = nil;
    [self.playButton setTitle:@"Play" forState:UIControlStateNormal];
}

- (void)reportError:(NSString*)message {
    dispatch_async(dispatch_get_main_queue(), ^{
        self.decoding = NO;
        [self stopEngine];
        self.statusLabel.text = [@"Playback failed: "
            stringByAppendingString:
                (message != nil ? message : @"unknown error")];
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
