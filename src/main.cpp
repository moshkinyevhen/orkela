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
#include <utility>
#include <vector>

namespace {

using Microsoft::WRL::ComPtr;

constexpr UINT playback_done_message = WM_APP + 1U;
constexpr UINT animation_timer_id = 1U;
constexpr UINT animation_interval_ms = 16U;
constexpr float design_dpi = 96.0F;
constexpr std::size_t spectrum_bar_count = 24U;

struct completion_payload {
    std::uint64_t generation = 0U;
    std::wstring message;
};

struct visual_layout {
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
    std::wstring format_name = L"NO MEDIA";
    std::wstring status =
        L"Drop a .resonith file here or choose Open media.";
    std::uint32_t cursor_frame = 0U;
    std::uint64_t playback_generation = 0U;
    float volume = 0.85F;
    float dpi = design_dpi;
    D2D1_POINT_2F mouse{};
    bool mouse_inside = false;
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

void stop_playback(app_state* state, bool reset_position) {
    if (state == nullptr) {
        return;
    }
    ++state->playback_generation;
    state->player.stop();
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

    auto decoded = std::make_shared<orkela::decoded_audio>();
    std::wstring error;
    if (!orkela::decode_resonith_file(path, decoded.get(), &error)) {
        state->format_name = L"REJECTED";
        state->status = std::move(error);
        invalidate(state);
        return;
    }

    state->audio = std::move(decoded);
    state->waveform = build_waveform(*state->audio);
    state->format_name = extension == L".resonith"
        ? L"RESONITH · NATIVE TRUTH"
        : L"RESONITH · RESEARCH TRANSPORT";
    state->status =
        L"Ready. Space plays or pauses; arrows seek by five seconds.";
    state->cursor_frame = 0U;
    update_spectrum(state);
    invalidate(state);
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

void handle_click(app_state* state, D2D1_POINT_2F point) {
    if (
        state == nullptr
        || state->graphics.target == nullptr
    ) {
        return;
    }
    const visual_layout layout =
        make_layout(state->graphics.target->GetSize());
    if (contains(layout.open, point)) {
        choose_file(state);
    } else if (contains(layout.play, point)) {
        toggle_playback(state);
    } else if (contains(layout.stop, point)) {
        stop_playback(state, true);
        state->status = L"Playback stopped.";
        invalidate(state);
    } else if (contains(layout.rewind, point)) {
        seek_relative(state, -10);
    } else if (contains(layout.forward, point)) {
        seek_relative(state, 10);
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
        if (word == VK_SPACE) {
            toggle_playback(state);
        } else if (word == VK_LEFT) {
            seek_relative(state, -5);
        } else if (word == VK_RIGHT) {
            seek_relative(state, 5);
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
            if (state->player.is_playing()) {
                state->cursor_frame = state->player.position_frame();
            }
            update_spectrum(state);
            invalidate(state);
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
            invalidate(state);
        }
        return 0;
    }
    case WM_CLOSE:
        if (state != nullptr) {
            state->closing.store(true);
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

    RECT work_area{};
    SystemParametersInfoW(
        SPI_GETWORKAREA,
        0U,
        &work_area,
        0U
    );
    const UINT system_dpi = GetDpiForSystem();
    const int available_width = work_area.right - work_area.left;
    const int available_height = work_area.bottom - work_area.top;
    const int initial_width = std::min(
        MulDiv(1120, system_dpi, 96),
        available_width * 92 / 100
    );
    const int initial_height = std::min(
        MulDiv(720, system_dpi, 96),
        available_height * 92 / 100
    );
    const int initial_x =
        work_area.left + (available_width - initial_width) / 2;
    const int initial_y =
        work_area.top + (available_height - initial_height) / 2;

    const HWND window = CreateWindowExW(
        0U,
        class_name,
        L"Orkela — Truth-aware media",
        WS_OVERLAPPEDWINDOW,
        initial_x,
        initial_y,
        initial_width,
        initial_height,
        nullptr,
        nullptr,
        instance,
        nullptr
    );
    if (window == nullptr) {
        CoUninitialize();
        return 1;
    }

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
