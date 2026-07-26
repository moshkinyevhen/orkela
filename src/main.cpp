#include "app_preferences.h"
#include "resonith_file.h"
#include "wave_player.h"

#include "../resources/resource.h"

#include <commdlg.h>
#include <d2d1.h>
#include <d2d1helper.h>
#include <dwmapi.h>
#include <dwrite.h>
#include <shellapi.h>
#include <uxtheme.h>
#include <windows.h>
#include <wincodec.h>
#include <windowsx.h>
#include <wrl/client.h>

#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <cwctype>
#include <filesystem>
#include <iomanip>
#include <memory>
#include <numbers>
#include <sstream>
#include <string>
#include <thread>
#include <utility>
#include <vector>

namespace {

using Microsoft::WRL::ComPtr;

constexpr UINT playback_done_message = WM_APP + 1U;
constexpr UINT decode_done_message = WM_APP + 2U;
constexpr UINT animation_timer_id = 1U;
constexpr UINT animation_interval_ms = 16U;
constexpr float design_dpi = 96.0F;
constexpr std::size_t spectrum_bar_count = 24U;
constexpr std::size_t command_page_count = 8U;

enum class command_page : std::size_t {
    overview,
    playback,
    audio,
    visuals,
    video,
    subtitles,
    interface_page,
    advanced,
};

struct completion_payload {
    std::uint64_t generation = 0U;
    std::wstring message;
};

struct decode_payload {
    std::uint64_t generation = 0U;
    std::filesystem::path path;
    std::shared_ptr<const orkela::decoded_audio> audio;
    std::wstring error;
};

struct visual_layout {
    D2D1_RECT_F command;
    D2D1_RECT_F open;
    D2D1_RECT_F hero;
    D2D1_RECT_F visualizer;
    D2D1_RECT_F progress;
    D2D1_RECT_F rewind;
    D2D1_RECT_F play;
    D2D1_RECT_F stop;
    D2D1_RECT_F forward;
    D2D1_RECT_F volume;
};

struct command_center_layout {
    D2D1_RECT_F panel;
    D2D1_RECT_F close;
    std::array<D2D1_RECT_F, command_page_count> navigation;
    std::array<D2D1_RECT_F, 6U> actions;
};

struct graphics_state {
    ComPtr<ID2D1Factory> d2d_factory;
    ComPtr<IDWriteFactory> dwrite_factory;
    ComPtr<IWICImagingFactory> wic_factory;
    ComPtr<ID2D1HwndRenderTarget> target;
    ComPtr<ID2D1Bitmap> brand_mark;
    ComPtr<ID2D1SolidColorBrush> text_primary;
    ComPtr<ID2D1SolidColorBrush> text_secondary;
    ComPtr<ID2D1SolidColorBrush> accent;
    ComPtr<ID2D1SolidColorBrush> accent_soft;
    ComPtr<ID2D1SolidColorBrush> panel;
    ComPtr<ID2D1SolidColorBrush> panel_edge;
    ComPtr<ID2D1SolidColorBrush> muted;
    ComPtr<ID2D1SolidColorBrush> warning;
    ComPtr<ID2D1LinearGradientBrush> hero_gradient;
    ComPtr<ID2D1RadialGradientBrush> ambient_glow;
    ComPtr<IDWriteTextFormat> brand_format;
    ComPtr<IDWriteTextFormat> headline_format;
    ComPtr<IDWriteTextFormat> body_format;
    ComPtr<IDWriteTextFormat> label_format;
    ComPtr<IDWriteTextFormat> button_format;
    ComPtr<IDWriteTextFormat> time_format;

    void discard_device_resources() noexcept {
        time_format.Reset();
        button_format.Reset();
        label_format.Reset();
        body_format.Reset();
        headline_format.Reset();
        brand_format.Reset();
        ambient_glow.Reset();
        hero_gradient.Reset();
        warning.Reset();
        muted.Reset();
        panel_edge.Reset();
        panel.Reset();
        accent_soft.Reset();
        accent.Reset();
        text_secondary.Reset();
        text_primary.Reset();
        brand_mark.Reset();
        target.Reset();
    }
};

struct app_state {
    HWND window = nullptr;
    HINSTANCE instance = nullptr;
    graphics_state graphics;
    std::filesystem::path path;
    std::shared_ptr<const orkela::decoded_audio> audio;
    orkela::wave_player player;
    std::vector<float> waveform;
    std::array<float, spectrum_bar_count> spectrum{};
    orkela::app_preferences preferences;
    std::wstring format_name = L"NO MEDIA";
    std::wstring status =
        L"Drop a .resonith file here or choose Open media.";
    std::uint32_t cursor_frame = 0U;
    std::uint64_t playback_generation = 0U;
    std::uint64_t decode_generation = 0U;
    std::uint32_t animation_tick = 0U;
    float volume = 0.85F;
    float dpi = design_dpi;
    D2D1_POINT_2F mouse{};
    bool mouse_inside = false;
    bool decoding = false;
    bool command_center_open = false;
    command_page active_command_page = command_page::overview;
    std::atomic_bool closing{false};
};

bool contains(const D2D1_RECT_F& rectangle, D2D1_POINT_2F point) noexcept {
    return point.x >= rectangle.left
        && point.x <= rectangle.right
        && point.y >= rectangle.top
        && point.y <= rectangle.bottom;
}

float rectangle_width(const D2D1_RECT_F& rectangle) noexcept {
    return rectangle.right - rectangle.left;
}

float rectangle_height(const D2D1_RECT_F& rectangle) noexcept {
    return rectangle.bottom - rectangle.top;
}

D2D1_COLOR_F color(float red, float green, float blue, float alpha = 1.0F) {
    return D2D1::ColorF(red, green, blue, alpha);
}

visual_layout make_layout(D2D1_SIZE_F size) {
    const float width = size.width;
    const float height = size.height;
    const float margin = width < 820.0F ? 24.0F : 32.0F;
    const float header_bottom = height < 600.0F ? 76.0F : 92.0F;
    const float hero_height = std::clamp(
        height * 0.30F,
        144.0F,
        200.0F
    );
    const float hero_bottom = header_bottom + hero_height;
    const float control_y = height - 75.0F;
    const float progress_y = height - 130.0F;
    const float center_x = width * 0.5F;
    return {
        D2D1::RectF(width - 346.0F, 24.0F, width - 198.0F, 66.0F),
        D2D1::RectF(width - 186.0F, 24.0F, width - margin, 66.0F),
        D2D1::RectF(
            margin,
            header_bottom,
            width - margin,
            hero_bottom
        ),
        D2D1::RectF(
            margin,
            hero_bottom + 16.0F,
            width - margin,
            progress_y - 26.0F
        ),
        D2D1::RectF(
            margin,
            progress_y,
            width - margin,
            progress_y + 6.0F
        ),
        D2D1::RectF(center_x - 116.0F, control_y - 23.0F,
                    center_x - 70.0F, control_y + 23.0F),
        D2D1::RectF(center_x - 30.0F, control_y - 30.0F,
                    center_x + 30.0F, control_y + 30.0F),
        D2D1::RectF(center_x + 52.0F, control_y - 21.0F,
                    center_x + 94.0F, control_y + 21.0F),
        D2D1::RectF(center_x + 116.0F, control_y - 23.0F,
                    center_x + 162.0F, control_y + 23.0F),
        D2D1::RectF(width - 190.0F, control_y - 3.0F,
                    width - margin, control_y + 3.0F),
    };
}

command_center_layout make_command_center_layout(D2D1_SIZE_F size) {
    const float outer = size.width < 860.0F ? 14.0F : 24.0F;
    const D2D1_RECT_F panel = D2D1::RectF(
        outer,
        outer,
        size.width - outer,
        size.height - outer
    );
    const float navigation_left = panel.left + 18.0F;
    const float navigation_right = std::min(
        panel.left + 196.0F,
        panel.right - 410.0F
    );
    std::array<D2D1_RECT_F, command_page_count> navigation{};
    for (std::size_t index = 0U; index < navigation.size(); ++index) {
        const float top = panel.top + 96.0F
            + static_cast<float>(index) * 46.0F;
        navigation[index] = D2D1::RectF(
            navigation_left,
            top,
            navigation_right,
            top + 38.0F
        );
    }

    const float content_left = navigation_right + 26.0F;
    const float content_right = panel.right - 22.0F;
    const float content_top = panel.top + 148.0F;
    const float gap = 12.0F;
    const float tile_width = (content_right - content_left - gap) * 0.5F;
    const float available_height = panel.bottom - content_top - 24.0F;
    const float tile_height = (available_height - gap * 2.0F) / 3.0F;
    std::array<D2D1_RECT_F, 6U> actions{};
    for (std::size_t index = 0U; index < actions.size(); ++index) {
        const float left = content_left
            + static_cast<float>(index % 2U) * (tile_width + gap);
        const float top = content_top
            + static_cast<float>(index / 2U) * (tile_height + gap);
        actions[index] = D2D1::RectF(
            left,
            top,
            left + tile_width,
            top + tile_height
        );
    }
    return {
        panel,
        D2D1::RectF(
            panel.right - 54.0F,
            panel.top + 18.0F,
            panel.right - 18.0F,
            panel.top + 54.0F
        ),
        navigation,
        actions,
    };
}

std::wstring lowercase(std::wstring value) {
    std::transform(
        value.begin(),
        value.end(),
        value.begin(),
        [](wchar_t character) {
            return static_cast<wchar_t>(std::towlower(character));
        }
    );
    return value;
}

std::wstring format_clock(
    std::uint32_t frame,
    std::uint32_t sample_rate
) {
    if (sample_rate == 0U) {
        return L"00:00";
    }
    const std::uint64_t seconds = frame / sample_rate;
    const std::uint64_t minutes = seconds / 60U;
    const std::uint64_t hours = minutes / 60U;
    std::wostringstream output;
    output << std::setfill(L'0');
    if (hours != 0U) {
        output << hours << L':' << std::setw(2) << minutes % 60U << L':';
    } else {
        output << std::setw(2) << minutes << L':';
    }
    output << std::setw(2) << seconds % 60U;
    return output.str();
}

std::wstring format_details(const orkela::decoded_audio& audio) {
    const double seconds = static_cast<double>(audio.frame_count)
        / static_cast<double>(audio.sample_rate);
    std::wostringstream output;
    output << audio.sample_rate << L" Hz  ·  "
           << (audio.channels == 1U ? L"Mono  ·  " : L"Stereo  ·  ")
           << std::fixed << std::setprecision(2) << seconds
           << L" s  ·  PCM16";
    return output.str();
}

std::vector<float> build_waveform(const orkela::decoded_audio& audio) {
    constexpr std::size_t column_count = 640U;
    std::vector<float> result(column_count, 0.0F);
    if (
        audio.samples.empty()
        || audio.frame_count == 0U
        || audio.channels == 0U
    ) {
        return result;
    }

    for (std::size_t column = 0U; column < column_count; ++column) {
        const std::uint64_t begin =
            static_cast<std::uint64_t>(column) * audio.frame_count
            / column_count;
        const std::uint64_t end = std::max<std::uint64_t>(
            begin + 1U,
            static_cast<std::uint64_t>(column + 1U) * audio.frame_count
                / column_count
        );
        std::int32_t peak = 0;
        for (std::uint64_t frame = begin; frame < end; ++frame) {
            std::int32_t mixed = 0;
            for (
                std::uint16_t channel = 0U;
                channel < audio.channels;
                ++channel
            ) {
                mixed += std::abs(
                    static_cast<std::int32_t>(
                        audio.samples[
                            static_cast<std::size_t>(frame) * audio.channels
                            + channel
                        ]
                    )
                );
            }
            peak = std::max(
                peak,
                mixed / static_cast<std::int32_t>(audio.channels)
            );
        }
        result[column] = std::clamp(
            static_cast<float>(peak) / 32768.0F,
            0.0F,
            1.0F
        );
    }
    return result;
}

void update_spectrum(app_state* state) {
    if (
        state == nullptr
        || state->audio == nullptr
        || state->audio->samples.empty()
        || state->audio->frame_count == 0U
        || state->audio->sample_rate == 0U
    ) {
        return;
    }

    constexpr std::size_t window = 256U;
    const auto& audio = *state->audio;
    const std::uint32_t center = std::min(
        state->cursor_frame,
        audio.frame_count - 1U
    );
    const std::uint32_t begin =
        center > window / 2U
            ? center - static_cast<std::uint32_t>(window / 2U)
            : 0U;

    for (std::size_t band = 0U; band < spectrum_bar_count; ++band) {
        const double ratio = static_cast<double>(band)
            / static_cast<double>(spectrum_bar_count - 1U);
        const double frequency = 45.0 * std::pow(18000.0 / 45.0, ratio);
        double real = 0.0;
        double imaginary = 0.0;
        for (std::size_t index = 0U; index < window; ++index) {
            const std::uint64_t frame =
                static_cast<std::uint64_t>(begin) + index;
            if (frame >= audio.frame_count) {
                break;
            }
            double sample = 0.0;
            for (
                std::uint16_t channel = 0U;
                channel < audio.channels;
                ++channel
            ) {
                sample += audio.samples[
                    static_cast<std::size_t>(frame) * audio.channels
                    + channel
                ];
            }
            sample /= static_cast<double>(audio.channels) * 32768.0;
            const double hann = 0.5 - 0.5 * std::cos(
                2.0 * std::numbers::pi * static_cast<double>(index)
                / static_cast<double>(window - 1U)
            );
            const double phase =
                2.0 * std::numbers::pi * frequency
                * static_cast<double>(index)
                / static_cast<double>(audio.sample_rate);
            real += sample * hann * std::cos(phase);
            imaginary -= sample * hann * std::sin(phase);
        }
        const float raw = std::clamp(
            static_cast<float>(
                std::log1p(
                    18.0 * std::sqrt(real * real + imaginary * imaginary)
                    / static_cast<double>(window)
                )
            ),
            0.0F,
            1.0F
        );
        state->spectrum[band] =
            0.78F * state->spectrum[band] + 0.22F * raw;
    }
}

HRESULT create_text_format(
    IDWriteFactory* factory,
    const wchar_t* family,
    float size,
    DWRITE_FONT_WEIGHT weight,
    IDWriteTextFormat** output
) {
    return factory->CreateTextFormat(
        family,
        nullptr,
        weight,
        DWRITE_FONT_STYLE_NORMAL,
        DWRITE_FONT_STRETCH_NORMAL,
        size,
        L"en-us",
        output
    );
}

HRESULT load_brand_bitmap(
    app_state* state,
    ID2D1Bitmap** output
) {
    if (
        state == nullptr
        || output == nullptr
        || state->graphics.wic_factory == nullptr
        || state->graphics.target == nullptr
    ) {
        return E_INVALIDARG;
    }
    *output = nullptr;
    const HRSRC resource = FindResourceW(
        state->instance,
        MAKEINTRESOURCEW(IDR_ORKELA_MARK),
        RT_RCDATA
    );
    if (resource == nullptr) {
        return HRESULT_FROM_WIN32(GetLastError());
    }
    const HGLOBAL loaded = LoadResource(state->instance, resource);
    const DWORD byte_count = SizeofResource(state->instance, resource);
    auto* data = static_cast<BYTE*>(LockResource(loaded));
    if (loaded == nullptr || data == nullptr || byte_count == 0U) {
        return E_FAIL;
    }

    ComPtr<IWICStream> stream;
    HRESULT status = state->graphics.wic_factory->CreateStream(&stream);
    if (SUCCEEDED(status)) {
        status = stream->InitializeFromMemory(data, byte_count);
    }
    ComPtr<IWICBitmapDecoder> decoder;
    if (SUCCEEDED(status)) {
        status = state->graphics.wic_factory->CreateDecoderFromStream(
            stream.Get(),
            nullptr,
            WICDecodeMetadataCacheOnLoad,
            &decoder
        );
    }
    ComPtr<IWICBitmapFrameDecode> frame;
    if (SUCCEEDED(status)) {
        status = decoder->GetFrame(0U, &frame);
    }
    ComPtr<IWICFormatConverter> converter;
    if (SUCCEEDED(status)) {
        status = state->graphics.wic_factory->CreateFormatConverter(
            &converter
        );
    }
    if (SUCCEEDED(status)) {
        status = converter->Initialize(
            frame.Get(),
            GUID_WICPixelFormat32bppPBGRA,
            WICBitmapDitherTypeNone,
            nullptr,
            0.0,
            WICBitmapPaletteTypeMedianCut
        );
    }
    if (SUCCEEDED(status)) {
        status = state->graphics.target->CreateBitmapFromWicBitmap(
            converter.Get(),
            nullptr,
            output
        );
    }
    return status;
}

HRESULT ensure_graphics(app_state* state) {
    if (state == nullptr) {
        return E_INVALIDARG;
    }
    auto& graphics = state->graphics;
    if (graphics.target != nullptr) {
        return S_OK;
    }

    RECT client{};
    GetClientRect(state->window, &client);
    HRESULT status = graphics.d2d_factory->CreateHwndRenderTarget(
        D2D1::RenderTargetProperties(),
        D2D1::HwndRenderTargetProperties(
            state->window,
            D2D1::SizeU(
                static_cast<UINT>(std::max(0L, client.right)),
                static_cast<UINT>(std::max(0L, client.bottom))
            ),
            D2D1_PRESENT_OPTIONS_IMMEDIATELY
        ),
        &graphics.target
    );
    if (FAILED(status)) {
        return status;
    }
    graphics.target->SetDpi(state->dpi, state->dpi);

    status = graphics.target->CreateSolidColorBrush(
        color(0.96F, 0.97F, 1.0F),
        &graphics.text_primary
    );
    if (SUCCEEDED(status)) {
        status = graphics.target->CreateSolidColorBrush(
            color(0.57F, 0.61F, 0.72F),
            &graphics.text_secondary
        );
    }
    if (SUCCEEDED(status)) {
        status = graphics.target->CreateSolidColorBrush(
            color(0.35F, 0.31F, 1.0F),
            &graphics.accent
        );
    }
    if (SUCCEEDED(status)) {
        status = graphics.target->CreateSolidColorBrush(
            color(0.18F, 0.74F, 1.0F, 0.32F),
            &graphics.accent_soft
        );
    }
    if (SUCCEEDED(status)) {
        status = graphics.target->CreateSolidColorBrush(
            color(0.055F, 0.061F, 0.09F, 0.90F),
            &graphics.panel
        );
    }
    if (SUCCEEDED(status)) {
        status = graphics.target->CreateSolidColorBrush(
            color(0.22F, 0.25F, 0.36F, 0.65F),
            &graphics.panel_edge
        );
    }
    if (SUCCEEDED(status)) {
        status = graphics.target->CreateSolidColorBrush(
            color(0.24F, 0.27F, 0.36F, 0.55F),
            &graphics.muted
        );
    }
    if (SUCCEEDED(status)) {
        status = graphics.target->CreateSolidColorBrush(
            color(1.0F, 0.66F, 0.18F),
            &graphics.warning
        );
    }

    const std::array<D2D1_GRADIENT_STOP, 4U> hero_stops = {{
        {0.0F, color(0.18F, 0.10F, 0.46F, 0.98F)},
        {0.38F, color(0.09F, 0.12F, 0.29F, 0.98F)},
        {0.72F, color(0.035F, 0.14F, 0.21F, 0.98F)},
        {1.0F, color(0.025F, 0.035F, 0.07F, 0.98F)},
    }};
    ComPtr<ID2D1GradientStopCollection> hero_collection;
    if (SUCCEEDED(status)) {
        status = graphics.target->CreateGradientStopCollection(
            hero_stops.data(),
            static_cast<UINT32>(hero_stops.size()),
            &hero_collection
        );
    }
    if (SUCCEEDED(status)) {
        status = graphics.target->CreateLinearGradientBrush(
            D2D1::LinearGradientBrushProperties(
                D2D1::Point2F(0.0F, 0.0F),
                D2D1::Point2F(1000.0F, 220.0F)
            ),
            hero_collection.Get(),
            &graphics.hero_gradient
        );
    }

    const std::array<D2D1_GRADIENT_STOP, 2U> glow_stops = {{
        {0.0F, color(0.37F, 0.24F, 1.0F, 0.22F)},
        {1.0F, color(0.06F, 0.10F, 0.20F, 0.0F)},
    }};
    ComPtr<ID2D1GradientStopCollection> glow_collection;
    if (SUCCEEDED(status)) {
        status = graphics.target->CreateGradientStopCollection(
            glow_stops.data(),
            static_cast<UINT32>(glow_stops.size()),
            &glow_collection
        );
    }
    if (SUCCEEDED(status)) {
        status = graphics.target->CreateRadialGradientBrush(
            D2D1::RadialGradientBrushProperties(
                D2D1::Point2F(270.0F, 120.0F),
                D2D1::Point2F(0.0F, 0.0F),
                340.0F,
                260.0F
            ),
            glow_collection.Get(),
            &graphics.ambient_glow
        );
    }

    if (SUCCEEDED(status)) {
        status = create_text_format(
            graphics.dwrite_factory.Get(),
            L"Segoe UI Variable Display",
            26.0F,
            DWRITE_FONT_WEIGHT_SEMI_BOLD,
            &graphics.brand_format
        );
    }
    if (SUCCEEDED(status)) {
        status = create_text_format(
            graphics.dwrite_factory.Get(),
            L"Segoe UI Variable Display",
            30.0F,
            DWRITE_FONT_WEIGHT_SEMI_BOLD,
            &graphics.headline_format
        );
    }
    if (SUCCEEDED(status)) {
        status = create_text_format(
            graphics.dwrite_factory.Get(),
            L"Segoe UI Variable Text",
            15.0F,
            DWRITE_FONT_WEIGHT_NORMAL,
            &graphics.body_format
        );
    }
    if (SUCCEEDED(status)) {
        status = create_text_format(
            graphics.dwrite_factory.Get(),
            L"Segoe UI Variable Text",
            12.0F,
            DWRITE_FONT_WEIGHT_SEMI_BOLD,
            &graphics.label_format
        );
    }
    if (SUCCEEDED(status)) {
        status = create_text_format(
            graphics.dwrite_factory.Get(),
            L"Segoe UI Variable Text",
            13.0F,
            DWRITE_FONT_WEIGHT_SEMI_BOLD,
            &graphics.button_format
        );
    }
    if (SUCCEEDED(status)) {
        status = create_text_format(
            graphics.dwrite_factory.Get(),
            L"Cascadia Mono",
            12.0F,
            DWRITE_FONT_WEIGHT_NORMAL,
            &graphics.time_format
        );
    }
    if (SUCCEEDED(status)) {
        status = load_brand_bitmap(
            state,
            graphics.brand_mark.ReleaseAndGetAddressOf()
        );
    }
    if (FAILED(status)) {
        graphics.discard_device_resources();
    }
    return status;
}

void draw_text(
    ID2D1RenderTarget* target,
    const std::wstring& text,
    IDWriteTextFormat* format,
    D2D1_RECT_F rectangle,
    ID2D1Brush* brush,
    D2D1_DRAW_TEXT_OPTIONS options = D2D1_DRAW_TEXT_OPTIONS_CLIP
) {
    target->DrawTextW(
        text.c_str(),
        static_cast<UINT32>(text.size()),
        format,
        rectangle,
        brush,
        options
    );
}

void draw_round_button(
    app_state* state,
    D2D1_RECT_F rectangle,
    bool hovered,
    bool primary
) {
    auto* target = state->graphics.target.Get();
    const float radius = rectangle_height(rectangle) * 0.5F;
    const D2D1_ROUNDED_RECT rounded =
        D2D1::RoundedRect(rectangle, radius, radius);
    if (primary) {
        state->graphics.accent->SetOpacity(hovered ? 1.0F : 0.88F);
        target->FillRoundedRectangle(rounded, state->graphics.accent.Get());
        state->graphics.accent->SetOpacity(1.0F);
    } else {
        state->graphics.panel_edge->SetOpacity(hovered ? 0.85F : 0.42F);
        target->FillRoundedRectangle(
            rounded,
            state->graphics.panel_edge.Get()
        );
        state->graphics.panel_edge->SetOpacity(1.0F);
    }
}

void draw_play_icon(
    ID2D1RenderTarget* target,
    ID2D1Factory* factory,
    ID2D1Brush* brush,
    D2D1_RECT_F rectangle,
    bool paused
) {
    const float center_x = (rectangle.left + rectangle.right) * 0.5F;
    const float center_y = (rectangle.top + rectangle.bottom) * 0.5F;
    if (paused) {
        target->FillRectangle(
            D2D1::RectF(center_x - 8.0F, center_y - 10.0F,
                        center_x - 3.0F, center_y + 10.0F),
            brush
        );
        target->FillRectangle(
            D2D1::RectF(center_x + 3.0F, center_y - 10.0F,
                        center_x + 8.0F, center_y + 10.0F),
            brush
        );
        return;
    }
    ComPtr<ID2D1PathGeometry> geometry;
    ComPtr<ID2D1GeometrySink> sink;
    if (
        SUCCEEDED(factory->CreatePathGeometry(&geometry))
        && SUCCEEDED(geometry->Open(&sink))
    ) {
        sink->BeginFigure(
            D2D1::Point2F(center_x - 7.0F, center_y - 11.0F),
            D2D1_FIGURE_BEGIN_FILLED
        );
        sink->AddLine(D2D1::Point2F(center_x + 11.0F, center_y));
        sink->AddLine(
            D2D1::Point2F(center_x - 7.0F, center_y + 11.0F)
        );
        sink->EndFigure(D2D1_FIGURE_END_CLOSED);
        sink->Close();
        target->FillGeometry(geometry.Get(), brush);
    }
}

void draw_skip_icon(
    ID2D1RenderTarget* target,
    ID2D1Factory* factory,
    ID2D1Brush* brush,
    D2D1_RECT_F rectangle,
    bool forward
) {
    const float center_x = (rectangle.left + rectangle.right) * 0.5F;
    const float center_y = (rectangle.top + rectangle.bottom) * 0.5F;
    const float direction = forward ? 1.0F : -1.0F;
    target->DrawLine(
        D2D1::Point2F(center_x + direction * 9.0F, center_y - 9.0F),
        D2D1::Point2F(center_x + direction * 9.0F, center_y + 9.0F),
        brush,
        2.2F
    );
    ComPtr<ID2D1PathGeometry> geometry;
    ComPtr<ID2D1GeometrySink> sink;
    if (
        SUCCEEDED(factory->CreatePathGeometry(&geometry))
        && SUCCEEDED(geometry->Open(&sink))
    ) {
        sink->BeginFigure(
            D2D1::Point2F(
                center_x + direction * 7.0F,
                center_y - 10.0F
            ),
            D2D1_FIGURE_BEGIN_FILLED
        );
        sink->AddLine(
            D2D1::Point2F(
                center_x - direction * 10.0F,
                center_y
            )
        );
        sink->AddLine(
            D2D1::Point2F(
                center_x + direction * 7.0F,
                center_y + 10.0F
            )
        );
        sink->EndFigure(D2D1_FIGURE_END_CLOSED);
        sink->Close();
        target->FillGeometry(geometry.Get(), brush);
    }
}

struct setting_tile {
    std::wstring title;
    std::wstring detail;
    std::wstring value;
    bool interactive = false;
    bool active = false;
    bool locked = false;
};

const std::array<std::wstring, command_page_count> command_navigation = {
    L"✦  Overview",
    L"▶  Playback",
    L"◉  Audio",
    L"▥  Visuals",
    L"▣  Video",
    L"CC  Subtitles",
    L"◇  Interface",
    L"⚙  Advanced",
};

std::wstring command_page_title(command_page page) {
    switch (page) {
    case command_page::overview:
        return L"Command Center";
    case command_page::playback:
        return L"Playback";
    case command_page::audio:
        return L"Audio";
    case command_page::visuals:
        return L"Visual Intelligence";
    case command_page::video:
        return L"SceneLith Video";
    case command_page::subtitles:
        return L"Subtitles & Accessibility";
    case command_page::interface_page:
        return L"Interface";
    case command_page::advanced:
        return L"Advanced & Trust";
    }
    return L"Command Center";
}

std::wstring command_page_description(command_page page) {
    switch (page) {
    case command_page::overview:
        return L"Your most useful session controls, one glance away.";
    case command_page::playback:
        return L"Behavior, navigation, continuity, and repeat.";
    case command_page::audio:
        return L"Truth-preserving audio output and listening preferences.";
    case command_page::visuals:
        return L"Responsive signal views with a restrained GPU footprint.";
    case command_page::video:
        return L"Prepared for the independent SceneLith decoder.";
    case command_page::subtitles:
        return L"Readable, synchronized, multilingual presentation.";
    case command_page::interface_page:
        return L"Motion, density, DPI, theme, and interaction.";
    case command_page::advanced:
        return L"Decoder integrity, offline guarantees, and diagnostics.";
    }
    return {};
}

std::array<setting_tile, 6U> command_tiles(const app_state* state) {
    const auto& preferences = state->preferences;
    const auto toggle_value = [](bool value) {
        return value ? std::wstring(L"ON") : std::wstring(L"OFF");
    };
    switch (state->active_command_page) {
    case command_page::overview:
        return {{
            {
                L"Autoplay",
                L"Start verified media immediately after decode.",
                toggle_value(preferences.autoplay_on_open),
                true,
                preferences.autoplay_on_open,
            },
            {
                L"Resume position",
                L"Continue the last opened file from its saved point.",
                toggle_value(preferences.resume_last_position),
                true,
                preferences.resume_last_position,
            },
            {
                L"Living visuals",
                L"Animate spectrum and playback field at display cadence.",
                toggle_value(preferences.animate_visuals),
                true,
                preferences.animate_visuals,
            },
            {
                L"Truth spectrum",
                L"Show analysis derived from reconstructed PCM.",
                toggle_value(preferences.show_spectrum),
                true,
                preferences.show_spectrum,
            },
            {
                L"Navigation step",
                L"Click to cycle the keyboard and transport skip interval.",
                std::to_wstring(preferences.skip_seconds) + L" SECONDS",
                true,
                true,
            },
            {
                L"Repeat current",
                L"Restart the current item after clean end-of-stream.",
                toggle_value(preferences.loop_current_media),
                true,
                preferences.loop_current_media,
            },
        }};
    case command_page::playback:
        return {{
            {
                L"Autoplay on open",
                L"Runs only after successful bounded decoder preflight.",
                toggle_value(preferences.autoplay_on_open),
                true,
                preferences.autoplay_on_open,
            },
            {
                L"Remember position",
                L"Stores one local resume point; never enters the codec.",
                toggle_value(preferences.resume_last_position),
                true,
                preferences.resume_last_position,
            },
            {
                L"Repeat current",
                L"Loop the active item without rebuilding its bitstream.",
                toggle_value(preferences.loop_current_media),
                true,
                preferences.loop_current_media,
            },
            {
                L"Seek step",
                L"Cycle between precise, standard, and long navigation.",
                std::to_wstring(preferences.skip_seconds) + L" SECONDS",
                true,
                true,
            },
            {
                L"Playback speed",
                L"Pitch-safe time scaling needs a dedicated DSP path.",
                L"ROADMAP",
                false,
                false,
            },
            {
                L"Bookmarks & queue",
                L"Versioned media-library state arrives with playlists.",
                L"ROADMAP",
                false,
                false,
            },
        }};
    case command_page::audio:
        return {{
            {
                L"Remember volume",
                L"Restore the listening level when Orkela starts.",
                toggle_value(preferences.remember_volume),
                true,
                preferences.remember_volume,
            },
            {
                L"Listening level",
                L"Click to cycle 50%, 85%, and 100%.",
                std::to_wstring(
                    static_cast<int>(std::lround(state->volume * 100.0F))
                ) + L"%",
                true,
                state->volume > 0.0F,
            },
            {
                L"Output device",
                L"Uses the Windows default PCM endpoint in this milestone.",
                L"SYSTEM DEFAULT",
                false,
                true,
                true,
            },
            {
                L"Truth path",
                L"Resonith Core → PCM16 → device; no WAV intermediary.",
                L"DIRECT",
                false,
                true,
                true,
            },
            {
                L"Equalizer & dynamics",
                L"Will run after Truth decode as optional presentation DSP.",
                L"ROADMAP",
                false,
                false,
            },
            {
                L"Spatial rendering",
                L"Headphones, speakers, room, and SceneLith AV Bridge.",
                L"ROADMAP",
                false,
                false,
            },
        }};
    case command_page::visuals:
        return {{
            {
                L"Living visuals",
                L"Animate only presentation state, never decoder Truth.",
                toggle_value(preferences.animate_visuals),
                true,
                preferences.animate_visuals,
            },
            {
                L"PCM spectrum",
                L"Show or hide the reconstructed-signal spectrum.",
                toggle_value(preferences.show_spectrum),
                true,
                preferences.show_spectrum,
            },
            {
                L"Truth waveform",
                L"Whole-file waveform computed from decoded PCM.",
                L"ALWAYS ON",
                false,
                true,
                true,
            },
            {
                L"Refresh cadence",
                L"Presentation follows a 16 ms timer while active.",
                L"UP TO 60 HZ",
                false,
                true,
                true,
            },
            {
                L"Visualizers",
                L"Scope, field, phase, loudness, and immersive views.",
                L"ROADMAP",
                false,
                false,
            },
            {
                L"Fullscreen focus",
                L"Distraction-free visualization and video canvas.",
                L"ROADMAP",
                false,
                false,
            },
        }};
    case command_page::video:
        return {{
            {L"SceneLith Core", L"Independent visual decoder integration.", L"PENDING CORE"},
            {L"Aspect & crop", L"Fit, fill, native ratio, and safe crop.", L"PLANNED"},
            {L"HDR pipeline", L"Color management and display capability map.", L"PLANNED"},
            {L"Frame presentation", L"Continuous scene state to display cadence.", L"PLANNED"},
            {L"Deinterlace", L"Compatibility path for legacy raster sources.", L"PLANNED"},
            {L"Snapshot", L"Export the exact presented visual state.", L"PLANNED"},
        }};
    case command_page::subtitles:
        return {{
            {L"Track selection", L"Embedded and external subtitle streams.", L"PLANNED"},
            {L"Typography", L"Font, size, weight, outline, and background.", L"PLANNED"},
            {L"Synchronization", L"Fine delay and durable per-item correction.", L"PLANNED"},
            {L"Languages", L"Preference order and accessibility metadata.", L"PLANNED"},
            {L"Position", L"Safe-area alignment and collision avoidance.", L"PLANNED"},
            {L"Live captions", L"Optional non-Truth local accessibility layer.", L"RESEARCH"},
        }};
    case command_page::interface_page:
        return {{
            {
                L"Interface motion",
                L"Disable animation while keeping transport responsive.",
                toggle_value(preferences.animate_visuals),
                true,
                preferences.animate_visuals,
            },
            {
                L"High-DPI layout",
                L"Per-monitor scaling with work-area constraints.",
                L"AUTOMATIC",
                false,
                true,
                true,
            },
            {L"Theme", L"Midnight glass is the current authored theme.", L"MIDNIGHT"},
            {L"Compact mode", L"Reduced chrome for small desktop windows.", L"PLANNED"},
            {L"Global hotkeys", L"System-wide transport controls.", L"PLANNED"},
            {L"Language", L"Localized UI with invariant format terminology.", L"PLANNED"},
        }};
    case command_page::advanced:
        return {{
            {
                L"Bounded preflight",
                L"Sizes and decoder limits are validated before playback.",
                L"LOCKED ON",
                false,
                true,
                true,
            },
            {
                L"Offline playback",
                L"No runtime network access or remote codec execution.",
                L"LOCKED ON",
                false,
                true,
                true,
            },
            {
                L"Reset preferences",
                L"Return session and presentation settings to defaults.",
                L"RESET",
                true,
                false,
            },
            {
                L"Format compatibility",
                L"Prospective LPS4/LPS5 inputs remain explicitly research.",
                L"VISIBLE",
                false,
                true,
                true,
            },
            {
                L"Diagnostics",
                L"Hashes and release evidence are published per version.",
                L"VERSIONED",
                false,
                true,
                true,
            },
            {
                L"Developer controls",
                L"Verbose traces stay out of the audio callback.",
                L"ROADMAP",
                false,
                false,
            },
        }};
    }
    return {};
}

void draw_toggle(
    ID2D1RenderTarget* target,
    ID2D1Brush* active_brush,
    ID2D1Brush* inactive_brush,
    D2D1_RECT_F rectangle,
    bool active
) {
    target->FillRoundedRectangle(
        D2D1::RoundedRect(rectangle, 10.0F, 10.0F),
        active ? active_brush : inactive_brush
    );
    const float center_y = (rectangle.top + rectangle.bottom) * 0.5F;
    const float center_x = active
        ? rectangle.right - 10.0F
        : rectangle.left + 10.0F;
    target->FillEllipse(
        D2D1::Ellipse(D2D1::Point2F(center_x, center_y), 6.0F, 6.0F),
        active ? inactive_brush : active_brush
    );
}

void render_command_center(app_state* state, D2D1_SIZE_F size) {
    if (!state->command_center_open) {
        return;
    }
    auto& graphics = state->graphics;
    auto* target = graphics.target.Get();
    const command_center_layout layout = make_command_center_layout(size);

    graphics.panel->SetOpacity(0.96F);
    target->FillRectangle(
        D2D1::RectF(0.0F, 0.0F, size.width, size.height),
        graphics.panel.Get()
    );
    target->FillRoundedRectangle(
        D2D1::RoundedRect(layout.panel, 26.0F, 26.0F),
        graphics.hero_gradient.Get()
    );
    graphics.panel->SetOpacity(0.94F);
    target->FillRoundedRectangle(
        D2D1::RoundedRect(
            D2D1::RectF(
                layout.panel.left + 1.0F,
                layout.panel.top + 1.0F,
                layout.panel.right - 1.0F,
                layout.panel.bottom - 1.0F
            ),
            25.0F,
            25.0F
        ),
        graphics.panel.Get()
    );
    graphics.panel->SetOpacity(1.0F);
    target->DrawRoundedRectangle(
        D2D1::RoundedRect(layout.panel, 26.0F, 26.0F),
        graphics.panel_edge.Get(),
        1.0F
    );

    draw_text(
        target,
        L"ORKELA",
        graphics.label_format.Get(),
        D2D1::RectF(
            layout.panel.left + 24.0F,
            layout.panel.top + 20.0F,
            layout.panel.left + 160.0F,
            layout.panel.top + 42.0F
        ),
        graphics.accent.Get()
    );
    draw_text(
        target,
        L"Control without clutter",
        graphics.body_format.Get(),
        D2D1::RectF(
            layout.panel.left + 24.0F,
            layout.panel.top + 45.0F,
            layout.panel.left + 210.0F,
            layout.panel.top + 70.0F
        ),
        graphics.text_secondary.Get()
    );

    const bool close_hovered =
        state->mouse_inside && contains(layout.close, state->mouse);
    draw_round_button(state, layout.close, close_hovered, false);
    draw_text(
        target,
        L"×",
        graphics.headline_format.Get(),
        D2D1::RectF(
            layout.close.left + 8.0F,
            layout.close.top - 1.0F,
            layout.close.right,
            layout.close.bottom
        ),
        graphics.text_primary.Get()
    );

    for (std::size_t index = 0U; index < layout.navigation.size(); ++index) {
        const bool selected =
            index == static_cast<std::size_t>(state->active_command_page);
        const bool hovered = state->mouse_inside
            && contains(layout.navigation[index], state->mouse);
        if (selected || hovered) {
            graphics.accent_soft->SetOpacity(selected ? 0.74F : 0.25F);
            target->FillRoundedRectangle(
                D2D1::RoundedRect(layout.navigation[index], 12.0F, 12.0F),
                graphics.accent_soft.Get()
            );
            graphics.accent_soft->SetOpacity(1.0F);
        }
        draw_text(
            target,
            command_navigation[index],
            graphics.button_format.Get(),
            D2D1::RectF(
                layout.navigation[index].left + 12.0F,
                layout.navigation[index].top + 9.0F,
                layout.navigation[index].right - 4.0F,
                layout.navigation[index].bottom
            ),
            selected
                ? graphics.text_primary.Get()
                : graphics.text_secondary.Get()
        );
    }

    const float content_left = layout.actions[0].left;
    draw_text(
        target,
        command_page_title(state->active_command_page),
        graphics.headline_format.Get(),
        D2D1::RectF(
            content_left,
            layout.panel.top + 24.0F,
            layout.close.left - 12.0F,
            layout.panel.top + 66.0F
        ),
        graphics.text_primary.Get()
    );
    draw_text(
        target,
        command_page_description(state->active_command_page),
        graphics.body_format.Get(),
        D2D1::RectF(
            content_left + 2.0F,
            layout.panel.top + 70.0F,
            layout.close.left - 8.0F,
            layout.panel.top + 96.0F
        ),
        graphics.text_secondary.Get()
    );
    draw_text(
        target,
        L"LIVE SETTINGS  ·  0.2.0-alpha.2",
        graphics.label_format.Get(),
        D2D1::RectF(
            content_left + 2.0F,
            layout.panel.top + 108.0F,
            layout.panel.right - 24.0F,
            layout.panel.top + 132.0F
        ),
        graphics.accent.Get()
    );

    const auto tiles = command_tiles(state);
    for (std::size_t index = 0U; index < tiles.size(); ++index) {
        const auto& tile = tiles[index];
        const D2D1_RECT_F rectangle = layout.actions[index];
        const bool hovered = tile.interactive
            && state->mouse_inside
            && contains(rectangle, state->mouse);
        graphics.panel_edge->SetOpacity(hovered ? 0.86F : 0.40F);
        target->FillRoundedRectangle(
            D2D1::RoundedRect(rectangle, 16.0F, 16.0F),
            graphics.panel_edge.Get()
        );
        graphics.panel_edge->SetOpacity(1.0F);
        target->DrawRoundedRectangle(
            D2D1::RoundedRect(rectangle, 16.0F, 16.0F),
            hovered ? graphics.accent.Get() : graphics.panel_edge.Get(),
            hovered ? 1.4F : 0.8F
        );
        target->FillEllipse(
            D2D1::Ellipse(
                D2D1::Point2F(rectangle.left + 18.0F, rectangle.top + 21.0F),
                4.0F,
                4.0F
            ),
            tile.active ? graphics.accent.Get() : graphics.muted.Get()
        );
        draw_text(
            target,
            tile.title,
            graphics.button_format.Get(),
            D2D1::RectF(
                rectangle.left + 31.0F,
                rectangle.top + 11.0F,
                rectangle.right - 52.0F,
                rectangle.top + 34.0F
            ),
            graphics.text_primary.Get()
        );
        draw_text(
            target,
            tile.detail,
            graphics.label_format.Get(),
            D2D1::RectF(
                rectangle.left + 16.0F,
                rectangle.top + 40.0F,
                rectangle.right - 16.0F,
                rectangle.bottom - 26.0F
            ),
            graphics.text_secondary.Get()
        );
        draw_text(
            target,
            tile.value,
            graphics.label_format.Get(),
            D2D1::RectF(
                rectangle.left + 16.0F,
                rectangle.bottom - 24.0F,
                rectangle.right - 16.0F,
                rectangle.bottom - 4.0F
            ),
            tile.interactive
                ? graphics.accent.Get()
                : graphics.text_secondary.Get()
        );
        if (
            tile.interactive
            && (
                tile.value == L"ON"
                || tile.value == L"OFF"
            )
        ) {
            draw_toggle(
                target,
                graphics.accent.Get(),
                graphics.text_primary.Get(),
                D2D1::RectF(
                    rectangle.right - 42.0F,
                    rectangle.top + 12.0F,
                    rectangle.right - 14.0F,
                    rectangle.top + 30.0F
                ),
                tile.active
            );
        } else if (tile.locked) {
            draw_text(
                target,
                L"◆",
                graphics.label_format.Get(),
                D2D1::RectF(
                    rectangle.right - 31.0F,
                    rectangle.top + 12.0F,
                    rectangle.right - 10.0F,
                    rectangle.top + 31.0F
                ),
                graphics.accent.Get()
            );
        }
    }
}

void render(app_state* state) {
    if (state == nullptr || FAILED(ensure_graphics(state))) {
        return;
    }
    auto& graphics = state->graphics;
    auto* target = graphics.target.Get();
    const D2D1_SIZE_F size = target->GetSize();
    const visual_layout layout = make_layout(size);
    const bool has_audio = state->audio != nullptr;

    target->BeginDraw();
    target->SetTransform(D2D1::Matrix3x2F::Identity());
    target->Clear(color(0.018F, 0.021F, 0.035F));
    target->FillEllipse(
        D2D1::Ellipse(D2D1::Point2F(270.0F, 120.0F), 340.0F, 260.0F),
        graphics.ambient_glow.Get()
    );

    const D2D1_RECT_F mark_rectangle =
        D2D1::RectF(28.0F, 19.0F, 78.0F, 69.0F);
    target->DrawBitmap(
        graphics.brand_mark.Get(),
        mark_rectangle,
        1.0F,
        D2D1_BITMAP_INTERPOLATION_MODE_LINEAR
    );
    draw_text(
        target,
        L"Orkela",
        graphics.brand_format.Get(),
        D2D1::RectF(88.0F, 21.0F, 260.0F, 58.0F),
        graphics.text_primary.Get()
    );
    draw_text(
        target,
        L"Truth-aware media",
        graphics.label_format.Get(),
        D2D1::RectF(90.0F, 53.0F, 300.0F, 74.0F),
        graphics.text_secondary.Get()
    );

    const bool command_hovered =
        state->mouse_inside && contains(layout.command, state->mouse);
    draw_round_button(
        state,
        layout.command,
        command_hovered || state->command_center_open,
        false
    );
    target->DrawLine(
        D2D1::Point2F(
            layout.command.left + 15.0F,
            layout.command.top + 16.0F
        ),
        D2D1::Point2F(
            layout.command.left + 25.0F,
            layout.command.top + 16.0F
        ),
        graphics.accent.Get(),
        1.8F
    );
    target->DrawLine(
        D2D1::Point2F(
            layout.command.left + 15.0F,
            layout.command.top + 22.0F
        ),
        D2D1::Point2F(
            layout.command.left + 25.0F,
            layout.command.top + 22.0F
        ),
        graphics.accent.Get(),
        1.8F
    );
    target->DrawLine(
        D2D1::Point2F(
            layout.command.left + 15.0F,
            layout.command.top + 28.0F
        ),
        D2D1::Point2F(
            layout.command.left + 25.0F,
            layout.command.top + 28.0F
        ),
        graphics.accent.Get(),
        1.8F
    );
    draw_text(
        target,
        L"COMMAND",
        graphics.button_format.Get(),
        D2D1::RectF(
            layout.command.left + 36.0F,
            layout.command.top + 11.0F,
            layout.command.right - 10.0F,
            layout.command.bottom
        ),
        graphics.text_primary.Get()
    );

    const bool open_hovered =
        state->mouse_inside && contains(layout.open, state->mouse);
    draw_round_button(state, layout.open, open_hovered, false);
    draw_text(
        target,
        L"OPEN MEDIA",
        graphics.button_format.Get(),
        D2D1::RectF(
            layout.open.left + 20.0F,
            layout.open.top + 11.0F,
            layout.open.right - 16.0F,
            layout.open.bottom
        ),
        graphics.text_primary.Get()
    );
    target->DrawLine(
        D2D1::Point2F(layout.open.left + 15.0F, layout.open.top + 21.0F),
        D2D1::Point2F(layout.open.left + 22.0F, layout.open.top + 21.0F),
        graphics.accent.Get(),
        2.0F
    );

    target->FillRoundedRectangle(
        D2D1::RoundedRect(layout.hero, 24.0F, 24.0F),
        graphics.hero_gradient.Get()
    );
    target->DrawRoundedRectangle(
        D2D1::RoundedRect(layout.hero, 24.0F, 24.0F),
        graphics.panel_edge.Get(),
        1.0F
    );
    const float hero_height = rectangle_height(layout.hero);
    const float hero_mark_size = std::clamp(
        hero_height - 40.0F,
        92.0F,
        136.0F
    );
    const float hero_mark_top =
        layout.hero.top + (hero_height - hero_mark_size) * 0.5F;
    const float hero_content_left =
        layout.hero.left + hero_mark_size + 64.0F;
    target->DrawBitmap(
        graphics.brand_mark.Get(),
        D2D1::RectF(
            layout.hero.left + 28.0F,
            hero_mark_top,
            layout.hero.left + 28.0F + hero_mark_size,
            hero_mark_top + hero_mark_size
        ),
        has_audio ? 0.95F : 0.35F,
        D2D1_BITMAP_INTERPOLATION_MODE_LINEAR
    );

    const std::wstring title = has_audio
        ? state->path.stem().wstring()
        : L"Your scene. Your sound.";
    const std::wstring subtitle = has_audio
        ? format_details(*state->audio)
        : L"Native Resonith playback · SceneLith-ready orchestration";
    draw_text(
        target,
        title,
        graphics.headline_format.Get(),
        D2D1::RectF(
            hero_content_left,
            layout.hero.top + 24.0F,
            layout.hero.right - 28.0F,
            layout.hero.top + 69.0F
        ),
        graphics.text_primary.Get()
    );
    draw_text(
        target,
        subtitle,
        graphics.body_format.Get(),
        D2D1::RectF(
            hero_content_left + 2.0F,
            layout.hero.top + 70.0F,
            layout.hero.right - 28.0F,
            layout.hero.top + 96.0F
        ),
        graphics.text_secondary.Get()
    );
    const D2D1_RECT_F badge = D2D1::RectF(
        hero_content_left + 2.0F,
        layout.hero.bottom - 44.0F,
        hero_content_left + 2.0F
            + std::max(
                116.0F,
                9.0F * static_cast<float>(state->format_name.size())
            ),
        layout.hero.bottom - 12.0F
    );
    graphics.accent_soft->SetOpacity(has_audio ? 0.75F : 0.28F);
    target->FillRoundedRectangle(
        D2D1::RoundedRect(badge, 16.0F, 16.0F),
        graphics.accent_soft.Get()
    );
    graphics.accent_soft->SetOpacity(1.0F);
    draw_text(
        target,
        state->format_name,
        graphics.label_format.Get(),
        D2D1::RectF(
            badge.left + 15.0F,
            badge.top + 8.0F,
            badge.right - 10.0F,
            badge.bottom
        ),
        has_audio ? graphics.text_primary.Get()
                  : graphics.text_secondary.Get()
    );

    target->FillRoundedRectangle(
        D2D1::RoundedRect(layout.visualizer, 20.0F, 20.0F),
        graphics.panel.Get()
    );
    target->DrawRoundedRectangle(
        D2D1::RoundedRect(layout.visualizer, 20.0F, 20.0F),
        graphics.panel_edge.Get(),
        1.0F
    );
    draw_text(
        target,
        L"CAUSAL FIELD",
        graphics.label_format.Get(),
        D2D1::RectF(
            layout.visualizer.left + 22.0F,
            layout.visualizer.top + 17.0F,
            layout.visualizer.right,
            layout.visualizer.top + 38.0F
        ),
        graphics.text_secondary.Get()
    );

    const D2D1_RECT_F wave_area = D2D1::RectF(
        layout.visualizer.left + 24.0F,
        layout.visualizer.top + 43.0F,
        layout.visualizer.right - 24.0F,
        layout.visualizer.bottom - 18.0F
    );
    const float wave_center =
        (wave_area.top + wave_area.bottom) * 0.5F;
    const float progress = has_audio && state->audio->frame_count != 0U
        ? static_cast<float>(state->cursor_frame)
            / static_cast<float>(state->audio->frame_count)
        : 0.0F;
    const float progress_x =
        wave_area.left + rectangle_width(wave_area) * progress;

    if (has_audio && !state->waveform.empty()) {
        const float step =
            rectangle_width(wave_area)
            / static_cast<float>(state->waveform.size());
        for (std::size_t index = 0U; index < state->waveform.size(); ++index) {
            const float x = wave_area.left
                + (static_cast<float>(index) + 0.5F) * step;
            const float amplitude = std::max(
                1.5F,
                state->waveform[index]
                    * rectangle_height(wave_area) * 0.44F
            );
            target->DrawLine(
                D2D1::Point2F(x, wave_center - amplitude),
                D2D1::Point2F(x, wave_center + amplitude),
                x <= progress_x
                    ? graphics.accent.Get()
                    : graphics.muted.Get(),
                std::max(1.0F, step * 0.52F)
            );
        }
    } else {
        target->DrawLine(
            D2D1::Point2F(wave_area.left, wave_center),
            D2D1::Point2F(wave_area.right, wave_center),
            graphics.muted.Get(),
            1.0F
        );
    }

    const float spectrum_width = std::min(
        280.0F,
        rectangle_width(wave_area) * 0.32F
    );
    const float spectrum_left = wave_area.right - spectrum_width;
    const float bar_step =
        spectrum_width / static_cast<float>(spectrum_bar_count);
    if (state->preferences.show_spectrum) {
        graphics.accent_soft->SetOpacity(has_audio ? 0.70F : 0.12F);
        for (std::size_t index = 0U; index < spectrum_bar_count; ++index) {
            const float height = 4.0F
                + state->spectrum[index] * rectangle_height(wave_area) * 0.72F;
            const float left = spectrum_left
                + static_cast<float>(index) * bar_step;
            target->FillRoundedRectangle(
                D2D1::RoundedRect(
                    D2D1::RectF(
                        left + 1.0F,
                        wave_area.bottom - height,
                        left + bar_step - 1.5F,
                        wave_area.bottom
                    ),
                    2.5F,
                    2.5F
                ),
                graphics.accent_soft.Get()
            );
        }
        graphics.accent_soft->SetOpacity(1.0F);
    } else {
        draw_text(
            target,
            L"SPECTRUM HIDDEN",
            graphics.label_format.Get(),
            D2D1::RectF(
                spectrum_left,
                wave_area.bottom - 24.0F,
                wave_area.right,
                wave_area.bottom
            ),
            graphics.text_secondary.Get()
        );
    }

    target->FillRoundedRectangle(
        D2D1::RoundedRect(layout.progress, 3.0F, 3.0F),
        graphics.muted.Get()
    );
    if (has_audio) {
        target->FillRoundedRectangle(
            D2D1::RoundedRect(
                D2D1::RectF(
                    layout.progress.left,
                    layout.progress.top,
                    layout.progress.left
                        + rectangle_width(layout.progress) * progress,
                    layout.progress.bottom
                ),
                3.0F,
                3.0F
            ),
            graphics.accent.Get()
        );
        target->FillEllipse(
            D2D1::Ellipse(
                D2D1::Point2F(
                    layout.progress.left
                        + rectangle_width(layout.progress) * progress,
                    (layout.progress.top + layout.progress.bottom) * 0.5F
                ),
                5.0F,
                5.0F
            ),
            graphics.text_primary.Get()
        );
    }

    const std::wstring current_time = has_audio
        ? format_clock(state->cursor_frame, state->audio->sample_rate)
        : L"00:00";
    const std::wstring total_time = has_audio
        ? format_clock(state->audio->frame_count, state->audio->sample_rate)
        : L"00:00";
    draw_text(
        target,
        current_time,
        graphics.time_format.Get(),
        D2D1::RectF(
            layout.progress.left,
            layout.progress.top - 25.0F,
            layout.progress.left + 90.0F,
            layout.progress.top
        ),
        graphics.text_secondary.Get()
    );
    graphics.time_format->SetTextAlignment(DWRITE_TEXT_ALIGNMENT_TRAILING);
    draw_text(
        target,
        total_time,
        graphics.time_format.Get(),
        D2D1::RectF(
            layout.progress.right - 90.0F,
            layout.progress.top - 25.0F,
            layout.progress.right,
            layout.progress.top
        ),
        graphics.text_secondary.Get()
    );
    graphics.time_format->SetTextAlignment(DWRITE_TEXT_ALIGNMENT_LEADING);

    const bool play_hovered =
        state->mouse_inside && contains(layout.play, state->mouse);
    draw_round_button(state, layout.play, play_hovered, true);
    draw_play_icon(
        target,
        graphics.d2d_factory.Get(),
        graphics.text_primary.Get(),
        layout.play,
        state->player.is_playing() && !state->player.is_paused()
    );
    for (const auto pair : {
        std::pair{layout.rewind, false},
        std::pair{layout.forward, true},
    }) {
        const bool hovered =
            state->mouse_inside && contains(pair.first, state->mouse);
        draw_round_button(state, pair.first, hovered, false);
        draw_skip_icon(
            target,
            graphics.d2d_factory.Get(),
            graphics.text_primary.Get(),
            pair.first,
            pair.second
        );
    }
    const bool stop_hovered =
        state->mouse_inside && contains(layout.stop, state->mouse);
    draw_round_button(state, layout.stop, stop_hovered, false);
    const float stop_center_x =
        (layout.stop.left + layout.stop.right) * 0.5F;
    const float stop_center_y =
        (layout.stop.top + layout.stop.bottom) * 0.5F;
    target->FillRoundedRectangle(
        D2D1::RoundedRect(
            D2D1::RectF(
                stop_center_x - 7.0F,
                stop_center_y - 7.0F,
                stop_center_x + 7.0F,
                stop_center_y + 7.0F
            ),
            2.0F,
            2.0F
        ),
        graphics.text_primary.Get()
    );

    target->FillRoundedRectangle(
        D2D1::RoundedRect(layout.volume, 3.0F, 3.0F),
        graphics.muted.Get()
    );
    target->FillRoundedRectangle(
        D2D1::RoundedRect(
            D2D1::RectF(
                layout.volume.left,
                layout.volume.top,
                layout.volume.left
                    + rectangle_width(layout.volume) * state->volume,
                layout.volume.bottom
            ),
            3.0F,
            3.0F
        ),
        graphics.accent.Get()
    );
    draw_text(
        target,
        L"VOLUME",
        graphics.label_format.Get(),
        D2D1::RectF(
            layout.volume.left,
            layout.volume.top - 25.0F,
            layout.volume.right,
            layout.volume.top - 5.0F
        ),
        graphics.text_secondary.Get()
    );

    draw_text(
        target,
        state->status,
        graphics.body_format.Get(),
        D2D1::RectF(32.0F, size.height - 38.0F, size.width - 32.0F,
                    size.height - 12.0F),
        graphics.text_secondary.Get()
    );

    render_command_center(state, size);

    const HRESULT status = target->EndDraw();
    if (status == D2DERR_RECREATE_TARGET) {
        graphics.discard_device_resources();
    }
}

void invalidate(app_state* state) {
    if (state != nullptr && state->window != nullptr) {
        InvalidateRect(state->window, nullptr, FALSE);
    }
}

void save_session_preferences(app_state* state) {
    if (state == nullptr) {
        return;
    }
    state->preferences.volume = state->volume;
    if (
        state->preferences.resume_last_position
        && state->audio != nullptr
        && !state->path.empty()
    ) {
        state->preferences.last_media = state->path;
        state->preferences.last_frame = state->cursor_frame;
    }
    orkela::save_preferences(state->preferences);
}

void stop_playback(app_state* state, bool reset_position) {
    if (state == nullptr) {
        return;
    }
    if (state->player.is_playing()) {
        state->cursor_frame = state->player.position_frame();
    }
    ++state->playback_generation;
    state->player.stop();
    save_session_preferences(state);
    if (reset_position) {
        state->cursor_frame = 0U;
    }
}

void begin_playback(app_state* state, std::uint32_t start_frame) {
    if (
        state == nullptr
        || state->audio == nullptr
        || state->audio->frame_count == 0U
    ) {
        return;
    }
    const std::uint32_t bounded = std::min(
        start_frame,
        state->audio->frame_count - 1U
    );
    state->cursor_frame = bounded;
    state->status = L"Playing native Resonith Truth reconstruction.";
    const std::uint64_t generation = ++state->playback_generation;
    const HWND window = state->window;
    state->player.set_volume(state->volume);
    state->player.play(
        state->audio,
        bounded,
        [window, state, generation](std::wstring message) {
            if (state->closing.load()) {
                return;
            }
            auto* payload = new completion_payload{
                generation,
                std::move(message),
            };
            if (
                PostMessageW(
                    window,
                    playback_done_message,
                    0U,
                    reinterpret_cast<LPARAM>(payload)
                ) == FALSE
            ) {
                delete payload;
            }
        }
    );
    invalidate(state);
}

void toggle_playback(app_state* state) {
    if (state == nullptr || state->audio == nullptr) {
        return;
    }
    if (state->player.is_playing()) {
        if (state->player.is_paused()) {
            state->player.resume();
            state->status = L"Playback resumed.";
        } else {
            state->cursor_frame = state->player.position_frame();
            state->player.pause();
            state->status = L"Playback paused.";
        }
    } else {
        const std::uint32_t start =
            state->cursor_frame >= state->audio->frame_count
                ? 0U
                : state->cursor_frame;
        begin_playback(state, start);
    }
    invalidate(state);
}

void seek_to(app_state* state, std::uint32_t frame) {
    if (state == nullptr || state->audio == nullptr) {
        return;
    }
    const bool restart =
        state->player.is_playing() && !state->player.is_paused();
    stop_playback(state, false);
    state->cursor_frame = std::min(frame, state->audio->frame_count);
    if (restart && state->cursor_frame < state->audio->frame_count) {
        begin_playback(state, state->cursor_frame);
    } else {
        state->status = L"Playback position changed.";
        invalidate(state);
    }
}

void seek_relative(app_state* state, std::int64_t seconds) {
    if (state == nullptr || state->audio == nullptr) {
        return;
    }
    const std::int64_t delta =
        seconds * static_cast<std::int64_t>(state->audio->sample_rate);
    const std::int64_t target = std::clamp<std::int64_t>(
        static_cast<std::int64_t>(state->cursor_frame) + delta,
        0,
        state->audio->frame_count
    );
    seek_to(state, static_cast<std::uint32_t>(target));
}

void load_file(app_state* state, const std::filesystem::path& path) {
    if (state == nullptr || path.empty()) {
        return;
    }
    if (state->decoding) {
        state->status =
            L"One bitstream is already being authenticated and decoded.";
        invalidate(state);
        return;
    }
    stop_playback(state, true);
    state->audio.reset();
    state->waveform.clear();
    state->spectrum.fill(0.0F);
    state->path = path;
    state->format_name = L"VALIDATING";
    state->status = L"Authenticating bitstream and preflighting decoder bounds…";
    invalidate(state);
    UpdateWindow(state->window);

    const std::wstring extension =
        lowercase(path.extension().wstring());
    if (extension == L".scenelith") {
        state->format_name = L"SCENELITH";
        state->status =
            L"SceneLith is recognized. Playback activates when SceneLith "
            L"Core reaches its first conforming decoder.";
        invalidate(state);
        return;
    }
    if (extension == L".orka") {
        state->format_name = L"ORKA PACKAGE";
        state->status =
            L"Orkela package recognized. The package binary layout remains "
            L"gated until the AV Bridge conformance draft.";
        invalidate(state);
        return;
    }
    if (
        extension != L".resonith"
        && extension != L".lps4"
        && extension != L".lps5"
        && extension != L".lps"
    ) {
        state->format_name = L"UNSUPPORTED";
        state->status =
            L"Unsupported input. Open .resonith, .scenelith, or .orka.";
        invalidate(state);
        return;
    }

    state->decoding = true;
    const std::uint64_t generation = ++state->decode_generation;
    const HWND window = state->window;
    std::thread(
        [window, generation, path]() {
            auto decoded = std::make_shared<orkela::decoded_audio>();
            std::wstring error;
            if (!orkela::decode_resonith_file(path, decoded.get(), &error)) {
                decoded.reset();
            }
            auto* payload = new decode_payload{
                generation,
                path,
                std::move(decoded),
                std::move(error),
            };
            if (
                PostMessageW(
                    window,
                    decode_done_message,
                    0U,
                    reinterpret_cast<LPARAM>(payload)
                ) == FALSE
            ) {
                delete payload;
            }
        }
    ).detach();
}

void choose_file(app_state* state) {
    if (state == nullptr) {
        return;
    }
    std::array<wchar_t, 32768> buffer{};
    OPENFILENAMEW dialog{};
    dialog.lStructSize = sizeof(dialog);
    dialog.hwndOwner = state->window;
    dialog.lpstrFilter =
        L"Orkela media (*.resonith;*.scenelith;*.orka)\0"
        L"*.resonith;*.scenelith;*.orka\0"
        L"Resonith research transport (*.lps4;*.lps5)\0"
        L"*.lps4;*.lps5\0"
        L"All files (*.*)\0*.*\0";
    dialog.lpstrFile = buffer.data();
    dialog.nMaxFile = static_cast<DWORD>(buffer.size());
    dialog.lpstrTitle = L"Open media in Orkela";
    dialog.Flags =
        OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR;
    if (GetOpenFileNameW(&dialog) != FALSE) {
        load_file(state, std::filesystem::path(buffer.data()));
    }
}

D2D1_POINT_2F point_from_message(app_state* state, LPARAM value) {
    const float scale = design_dpi / state->dpi;
    return D2D1::Point2F(
        static_cast<float>(GET_X_LPARAM(value)) * scale,
        static_cast<float>(GET_Y_LPARAM(value)) * scale
    );
}

void cycle_skip_interval(orkela::app_preferences* preferences) {
    if (preferences->skip_seconds == 5U) {
        preferences->skip_seconds = 10U;
    } else if (preferences->skip_seconds == 10U) {
        preferences->skip_seconds = 30U;
    } else {
        preferences->skip_seconds = 5U;
    }
}

void cycle_listening_level(app_state* state) {
    const int percent = static_cast<int>(
        std::lround(state->volume * 100.0F)
    );
    if (percent < 67) {
        state->volume = 0.85F;
    } else if (percent < 93) {
        state->volume = 1.0F;
    } else {
        state->volume = 0.50F;
    }
    state->player.set_volume(state->volume);
}

void activate_command_tile(app_state* state, std::size_t index) {
    auto& preferences = state->preferences;
    switch (state->active_command_page) {
    case command_page::overview:
        if (index == 0U) {
            preferences.autoplay_on_open = !preferences.autoplay_on_open;
        } else if (index == 1U) {
            preferences.resume_last_position =
                !preferences.resume_last_position;
        } else if (index == 2U) {
            preferences.animate_visuals = !preferences.animate_visuals;
        } else if (index == 3U) {
            preferences.show_spectrum = !preferences.show_spectrum;
        } else if (index == 4U) {
            cycle_skip_interval(&preferences);
        } else if (index == 5U) {
            preferences.loop_current_media =
                !preferences.loop_current_media;
        }
        break;
    case command_page::playback:
        if (index == 0U) {
            preferences.autoplay_on_open = !preferences.autoplay_on_open;
        } else if (index == 1U) {
            preferences.resume_last_position =
                !preferences.resume_last_position;
        } else if (index == 2U) {
            preferences.loop_current_media =
                !preferences.loop_current_media;
        } else if (index == 3U) {
            cycle_skip_interval(&preferences);
        } else {
            return;
        }
        break;
    case command_page::audio:
        if (index == 0U) {
            preferences.remember_volume = !preferences.remember_volume;
        } else if (index == 1U) {
            cycle_listening_level(state);
        } else {
            return;
        }
        break;
    case command_page::visuals:
        if (index == 0U) {
            preferences.animate_visuals = !preferences.animate_visuals;
        } else if (index == 1U) {
            preferences.show_spectrum = !preferences.show_spectrum;
        } else {
            return;
        }
        break;
    case command_page::interface_page:
        if (index == 0U) {
            preferences.animate_visuals = !preferences.animate_visuals;
        } else {
            return;
        }
        break;
    case command_page::advanced:
        if (index != 2U) {
            return;
        }
        orkela::reset_preferences();
        preferences = {};
        state->volume = preferences.volume;
        state->player.set_volume(state->volume);
        state->status = L"Preferences reset to Orkela defaults.";
        break;
    case command_page::video:
    case command_page::subtitles:
        return;
    }
    save_session_preferences(state);
    invalidate(state);
}

bool handle_command_center_click(
    app_state* state,
    D2D1_POINT_2F point,
    const visual_layout& base_layout
) {
    if (contains(base_layout.command, point)) {
        state->command_center_open = !state->command_center_open;
        invalidate(state);
        return true;
    }
    if (!state->command_center_open) {
        return false;
    }
    const command_center_layout layout = make_command_center_layout(
        state->graphics.target->GetSize()
    );
    if (contains(layout.close, point)) {
        state->command_center_open = false;
        invalidate(state);
        return true;
    }
    for (std::size_t index = 0U; index < layout.navigation.size(); ++index) {
        if (contains(layout.navigation[index], point)) {
            state->active_command_page =
                static_cast<command_page>(index);
            invalidate(state);
            return true;
        }
    }
    const auto tiles = command_tiles(state);
    for (std::size_t index = 0U; index < layout.actions.size(); ++index) {
        if (
            tiles[index].interactive
            && contains(layout.actions[index], point)
        ) {
            activate_command_tile(state, index);
            return true;
        }
    }
    return true;
}

void handle_click(app_state* state, D2D1_POINT_2F point) {
    if (
        state == nullptr
        || state->graphics.target == nullptr
    ) {
        return;
    }
    const visual_layout layout =
        make_layout(state->graphics.target->GetSize());
    if (handle_command_center_click(state, point, layout)) {
        return;
    }
    if (contains(layout.open, point)) {
        choose_file(state);
    } else if (contains(layout.play, point)) {
        toggle_playback(state);
    } else if (contains(layout.stop, point)) {
        stop_playback(state, true);
        state->status = L"Playback stopped.";
        invalidate(state);
    } else if (contains(layout.rewind, point)) {
        seek_relative(
            state,
            -static_cast<std::int64_t>(state->preferences.skip_seconds)
        );
    } else if (contains(layout.forward, point)) {
        seek_relative(
            state,
            static_cast<std::int64_t>(state->preferences.skip_seconds)
        );
    } else if (
        contains(layout.progress, point)
        && state->audio != nullptr
    ) {
        const float ratio = std::clamp(
            (point.x - layout.progress.left)
                / rectangle_width(layout.progress),
            0.0F,
            1.0F
        );
        seek_to(
            state,
            static_cast<std::uint32_t>(
                ratio * static_cast<float>(state->audio->frame_count)
            )
        );
    } else if (contains(layout.volume, point)) {
        state->volume = std::clamp(
            (point.x - layout.volume.left)
                / rectangle_width(layout.volume),
            0.0F,
            1.0F
        );
        state->player.set_volume(state->volume);
        save_session_preferences(state);
        invalidate(state);
    }
}

void configure_window_appearance(HWND window) {
    const BOOL dark = TRUE;
    DwmSetWindowAttribute(window, 20U, &dark, sizeof(dark));
    const int rounded = 2;
    DwmSetWindowAttribute(window, 33U, &rounded, sizeof(rounded));
    const int backdrop = 2;
    DwmSetWindowAttribute(window, 38U, &backdrop, sizeof(backdrop));
    SetWindowTheme(window, L"DarkMode_Explorer", nullptr);
}

HRESULT initialize_factories(app_state* state) {
    HRESULT status = D2D1CreateFactory(
        D2D1_FACTORY_TYPE_SINGLE_THREADED,
        state->graphics.d2d_factory.ReleaseAndGetAddressOf()
    );
    if (SUCCEEDED(status)) {
        status = DWriteCreateFactory(
            DWRITE_FACTORY_TYPE_SHARED,
            __uuidof(IDWriteFactory),
            reinterpret_cast<IUnknown**>(
                state->graphics.dwrite_factory.ReleaseAndGetAddressOf()
            )
        );
    }
    if (SUCCEEDED(status)) {
        status = CoCreateInstance(
            CLSID_WICImagingFactory,
            nullptr,
            CLSCTX_INPROC_SERVER,
            IID_PPV_ARGS(
                state->graphics.wic_factory.ReleaseAndGetAddressOf()
            )
        );
    }
    return status;
}

LRESULT CALLBACK window_procedure(
    HWND window,
    UINT message,
    WPARAM word,
    LPARAM long_word
) {
    auto* state = reinterpret_cast<app_state*>(
        GetWindowLongPtrW(window, GWLP_USERDATA)
    );
    switch (message) {
    case WM_CREATE: {
        auto* created = new app_state{};
        created->window = window;
        created->instance = reinterpret_cast<LPCREATESTRUCTW>(long_word)
            ->hInstance;
        created->dpi = static_cast<float>(GetDpiForWindow(window));
        created->preferences = orkela::load_preferences();
        created->volume = created->preferences.remember_volume
            ? created->preferences.volume
            : 0.85F;
        created->player.set_volume(created->volume);
        SetWindowLongPtrW(
            window,
            GWLP_USERDATA,
            reinterpret_cast<LONG_PTR>(created)
        );
        if (FAILED(initialize_factories(created))) {
            delete created;
            SetWindowLongPtrW(window, GWLP_USERDATA, 0);
            return -1;
        }
        configure_window_appearance(window);
        DragAcceptFiles(window, TRUE);
        SetTimer(
            window,
            animation_timer_id,
            animation_interval_ms,
            nullptr
        );
        return 0;
    }
    case WM_PAINT: {
        PAINTSTRUCT paint{};
        BeginPaint(window, &paint);
        render(state);
        EndPaint(window, &paint);
        return 0;
    }
    case WM_ERASEBKGND:
        return 1;
    case WM_SIZE:
        if (state != nullptr && state->graphics.target != nullptr) {
            state->graphics.target->Resize(
                D2D1::SizeU(LOWORD(long_word), HIWORD(long_word))
            );
            invalidate(state);
        }
        return 0;
    case WM_DPICHANGED:
        if (state != nullptr) {
            state->dpi = static_cast<float>(HIWORD(word));
            const auto* suggested =
                reinterpret_cast<const RECT*>(long_word);
            SetWindowPos(
                window,
                nullptr,
                suggested->left,
                suggested->top,
                suggested->right - suggested->left,
                suggested->bottom - suggested->top,
                SWP_NOACTIVATE | SWP_NOZORDER
            );
            state->graphics.discard_device_resources();
            invalidate(state);
        }
        return 0;
    case WM_GETMINMAXINFO: {
        auto* limits = reinterpret_cast<MINMAXINFO*>(long_word);
        const UINT dpi = state == nullptr
            ? GetDpiForWindow(window)
            : static_cast<UINT>(state->dpi);
        limits->ptMinTrackSize.x = MulDiv(760, dpi, 96);
        limits->ptMinTrackSize.y = MulDiv(480, dpi, 96);
        return 0;
    }
    case WM_MOUSEMOVE:
        if (state != nullptr) {
            state->mouse = point_from_message(state, long_word);
            if (!state->mouse_inside) {
                state->mouse_inside = true;
                TRACKMOUSEEVENT tracking{
                    sizeof(TRACKMOUSEEVENT),
                    TME_LEAVE,
                    window,
                    0U,
                };
                TrackMouseEvent(&tracking);
            }
            invalidate(state);
        }
        return 0;
    case WM_MOUSELEAVE:
        if (state != nullptr) {
            state->mouse_inside = false;
            invalidate(state);
        }
        return 0;
    case WM_LBUTTONDOWN:
        if (state != nullptr) {
            handle_click(
                state,
                point_from_message(state, long_word)
            );
        }
        return 0;
    case WM_KEYDOWN:
        if (state == nullptr) {
            return 0;
        }
        if (
            word == VK_OEM_COMMA
            && (GetKeyState(VK_CONTROL) < 0)
        ) {
            state->command_center_open = !state->command_center_open;
            invalidate(state);
        } else if (
            state->command_center_open
            && word == VK_ESCAPE
        ) {
            state->command_center_open = false;
            invalidate(state);
        } else if (
            state->command_center_open
            && (word == VK_UP || word == VK_DOWN)
        ) {
            const std::size_t current =
                static_cast<std::size_t>(state->active_command_page);
            const std::size_t next = word == VK_DOWN
                ? (current + 1U) % command_page_count
                : (current + command_page_count - 1U)
                    % command_page_count;
            state->active_command_page = static_cast<command_page>(next);
            invalidate(state);
        } else if (state->command_center_open) {
            return 0;
        } else if (word == VK_SPACE) {
            toggle_playback(state);
        } else if (word == VK_LEFT) {
            seek_relative(
                state,
                -static_cast<std::int64_t>(
                    state->preferences.skip_seconds
                )
            );
        } else if (word == VK_RIGHT) {
            seek_relative(
                state,
                static_cast<std::int64_t>(
                    state->preferences.skip_seconds
                )
            );
        } else if (word == VK_ESCAPE) {
            stop_playback(state, true);
            state->status = L"Playback stopped.";
            invalidate(state);
        } else if (word == L'O' && (GetKeyState(VK_CONTROL) < 0)) {
            choose_file(state);
        }
        return 0;
    case WM_DROPFILES: {
        if (state == nullptr) {
            return 0;
        }
        const HDROP drop = reinterpret_cast<HDROP>(word);
        std::array<wchar_t, 32768> path{};
        if (
            DragQueryFileW(
                drop,
                0U,
                path.data(),
                static_cast<UINT>(path.size())
            ) != 0U
        ) {
            load_file(state, std::filesystem::path(path.data()));
        }
        DragFinish(drop);
        return 0;
    }
    case WM_TIMER:
        if (state != nullptr && word == animation_timer_id) {
            ++state->animation_tick;
            if (state->player.is_playing()) {
                state->cursor_frame = state->player.position_frame();
            }
            const bool animate = state->preferences.animate_visuals;
            const bool coarse_tick = state->animation_tick % 15U == 0U;
            if (
                state->preferences.show_spectrum
                && (animate || coarse_tick)
            ) {
                update_spectrum(state);
            }
            if (
                animate
                || coarse_tick
                || state->decoding
                || state->command_center_open
            ) {
                invalidate(state);
            }
        }
        return 0;
    case playback_done_message: {
        std::unique_ptr<completion_payload> payload(
            reinterpret_cast<completion_payload*>(long_word)
        );
        if (
            state != nullptr
            && payload != nullptr
            && payload->generation == state->playback_generation
        ) {
            state->cursor_frame = state->player.position_frame();
            state->status = std::move(payload->message);
            if (
                state->preferences.loop_current_media
                && state->status == L"Playback complete."
                && state->audio != nullptr
            ) {
                begin_playback(state, 0U);
                return 0;
            }
            save_session_preferences(state);
            invalidate(state);
        }
        return 0;
    }
    case decode_done_message: {
        std::unique_ptr<decode_payload> payload(
            reinterpret_cast<decode_payload*>(long_word)
        );
        if (
            state == nullptr
            || payload == nullptr
            || payload->generation != state->decode_generation
        ) {
            return 0;
        }
        state->decoding = false;
        if (payload->audio == nullptr) {
            state->format_name = L"REJECTED";
            state->status = std::move(payload->error);
            invalidate(state);
            return 0;
        }
        state->path = std::move(payload->path);
        state->audio = std::move(payload->audio);
        state->waveform = build_waveform(*state->audio);
        const std::wstring extension =
            lowercase(state->path.extension().wstring());
        state->format_name = extension == L".resonith"
            ? L"RESONITH · NATIVE TRUTH"
            : L"RESONITH · RESEARCH TRANSPORT";
        state->status =
            L"Ready. Space plays or pauses; arrows use the selected seek step.";
        const bool same_resume_item =
            state->preferences.resume_last_position
            && lowercase(state->preferences.last_media.wstring())
                == lowercase(state->path.wstring());
        state->cursor_frame = same_resume_item
            ? std::min(
                state->preferences.last_frame,
                state->audio->frame_count
            )
            : 0U;
        state->preferences.last_media = state->path;
        state->preferences.last_frame = state->cursor_frame;
        save_session_preferences(state);
        update_spectrum(state);
        invalidate(state);
        if (state->preferences.autoplay_on_open) {
            begin_playback(state, state->cursor_frame);
        }
        return 0;
    }
    case WM_CLOSE:
        if (state != nullptr) {
            state->closing.store(true);
            ++state->decode_generation;
            save_session_preferences(state);
            stop_playback(state, false);
        }
        DestroyWindow(window);
        return 0;
    case WM_DESTROY:
        KillTimer(window, animation_timer_id);
        SetWindowLongPtrW(window, GWLP_USERDATA, 0);
        delete state;
        PostQuitMessage(0);
        return 0;
    default:
        return DefWindowProcW(window, message, word, long_word);
    }
}

}  // namespace

int WINAPI wWinMain(
    HINSTANCE instance,
    HINSTANCE,
    PWSTR,
    int show_command
) {
    SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
    if (FAILED(CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED))) {
        return 1;
    }

    const wchar_t class_name[] = L"OrkelaMainWindow";
    const auto large_icon = static_cast<HICON>(LoadImageW(
        instance,
        MAKEINTRESOURCEW(IDI_ORKELA),
        IMAGE_ICON,
        48,
        48,
        LR_DEFAULTCOLOR
    ));
    const auto small_icon = static_cast<HICON>(LoadImageW(
        instance,
        MAKEINTRESOURCEW(IDI_ORKELA),
        IMAGE_ICON,
        20,
        20,
        LR_DEFAULTCOLOR
    ));

    WNDCLASSEXW window_class{};
    window_class.cbSize = sizeof(window_class);
    window_class.style = CS_HREDRAW | CS_VREDRAW | CS_DBLCLKS;
    window_class.lpfnWndProc = window_procedure;
    window_class.hInstance = instance;
    window_class.hCursor = LoadCursorW(nullptr, IDC_ARROW);
    window_class.hIcon = large_icon;
    window_class.hbrBackground = nullptr;
    window_class.lpszClassName = class_name;
    window_class.hIconSm = small_icon;
    if (RegisterClassExW(&window_class) == 0U) {
        CoUninitialize();
        return 1;
    }

    const HWND window = CreateWindowExW(
        0U,
        class_name,
        L"Orkela — Truth-aware media",
        WS_OVERLAPPEDWINDOW,
        CW_USEDEFAULT,
        CW_USEDEFAULT,
        1120,
        720,
        nullptr,
        nullptr,
        instance,
        nullptr
    );
    if (window == nullptr) {
        CoUninitialize();
        return 1;
    }

    // CreateWindowEx receives physical pixels for a per-monitor-aware process.
    // Resize only after Windows has selected a monitor and assigned its DPI,
    // then clamp to that monitor's work area so 200% displays remain usable.
    MONITORINFO monitor_info{sizeof(MONITORINFO)};
    GetMonitorInfoW(
        MonitorFromWindow(window, MONITOR_DEFAULTTONEAREST),
        &monitor_info
    );
    const RECT work_area = monitor_info.rcWork;
    const int available_width = work_area.right - work_area.left;
    const int available_height = work_area.bottom - work_area.top;
    const UINT window_dpi = GetDpiForWindow(window);
    const int initial_width = std::min(
        MulDiv(1120, window_dpi, 96),
        available_width * 92 / 100
    );
    const int initial_height = std::min(
        MulDiv(720, window_dpi, 96),
        available_height * 92 / 100
    );
    SetWindowPos(
        window,
        nullptr,
        work_area.left + (available_width - initial_width) / 2,
        work_area.top + (available_height - initial_height) / 2,
        initial_width,
        initial_height,
        SWP_NOACTIVATE | SWP_NOZORDER
    );

    ShowWindow(window, show_command);
    UpdateWindow(window);

    int argument_count = 0;
    LPWSTR* arguments = CommandLineToArgvW(
        GetCommandLineW(),
        &argument_count
    );
    if (arguments != nullptr) {
        if (argument_count >= 2) {
            auto* state = reinterpret_cast<app_state*>(
                GetWindowLongPtrW(window, GWLP_USERDATA)
            );
            load_file(state, std::filesystem::path(arguments[1]));
        }
        LocalFree(arguments);
    }

    MSG message{};
    while (GetMessageW(&message, nullptr, 0U, 0U) > 0) {
        TranslateMessage(&message);
        DispatchMessageW(&message);
    }
    CoUninitialize();
    return static_cast<int>(message.wParam);
}
