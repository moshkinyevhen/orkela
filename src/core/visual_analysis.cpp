#include "orkela/visual_analysis.h"

#include <algorithm>
#include <cmath>
#include <numbers>

namespace orkela {
namespace {

float mono_sample(
    std::span<const std::int16_t> pcm,
    std::size_t frame,
    std::uint16_t channels
) {
    std::int64_t sum = 0;
    const std::size_t base =
        frame * static_cast<std::size_t>(channels);
    for (std::uint16_t channel = 0U; channel < channels; ++channel) {
        sum += pcm[base + channel];
    }
    return static_cast<float>(sum)
        / (
            32768.0F
            * static_cast<float>(channels)
        );
}

}  // namespace

pcm_visual_analyzer::pcm_visual_analyzer() {
    for (std::size_t index = 0U; index < window_.size(); ++index) {
        window_[index] = static_cast<float>(
            0.5
            - 0.5 * std::cos(
                2.0
                * std::numbers::pi
                * static_cast<double>(index)
                / static_cast<double>(window_.size() - 1U)
            )
        );
    }
}

void pcm_visual_analyzer::reset() {
    std::scoped_lock lock(mutex_);
    wave_.fill(0.0F);
    spectrum_.fill(0.0F);
    magnitudes_.fill(0.0F);
    analysis_.fill(0.0F);
    history_.fill(0.0F);
    history_columns_ = 0U;
    peak_ = 0.0F;
}

float pcm_visual_analyzer::offer(
    std::span<const std::int16_t> interleaved_pcm,
    std::uint16_t channels,
    std::uint32_t sample_rate
) {
    if (
        channels == 0U
        || sample_rate == 0U
        || interleaved_pcm.size() < channels
        || interleaved_pcm.size() % channels != 0U
    ) {
        return 0.0F;
    }

    const std::size_t channel_count =
        static_cast<std::size_t>(channels);
    const std::size_t frames =
        interleaved_pcm.size() / channel_count;
    const std::size_t analyzed = std::min(
        analysis_samples,
        frames
    );
    const std::size_t analysis_start = frames - analyzed;
    float peak = 0.0F;

    std::scoped_lock lock(mutex_);
    for (std::size_t index = 0U; index < wave_.size(); ++index) {
        const std::size_t frame = std::min(
            frames - 1U,
            index * frames / wave_.size()
        );
        const float sample = mono_sample(
            interleaved_pcm,
            frame,
            channels
        );
        wave_[index] = 0.67F * wave_[index] + 0.33F * sample;
        peak = std::max(peak, std::abs(sample));
    }

    analysis_.fill(0.0F);
    for (std::size_t index = 0U; index < analyzed; ++index) {
        const std::size_t window_index = analyzed <= 1U
            ? window_.size() - 1U
            : std::min(
                window_.size() - 1U,
                static_cast<std::size_t>(
                    std::lround(
                        static_cast<double>(index)
                        * static_cast<double>(window_.size() - 1U)
                        / static_cast<double>(analyzed - 1U)
                    )
                )
            );
        analysis_[index] = mono_sample(
            interleaved_pcm,
            analysis_start + index,
            channels
        ) * window_[window_index];
    }

    const double nyquist = std::max(
        80.0,
        static_cast<double>(sample_rate) * 0.5
    );
    float maximum_magnitude = 0.0F;
    for (
        std::size_t band = 0U;
        band < visual_spectrum_bands;
        ++band
    ) {
        const double ratio = static_cast<double>(band)
            / static_cast<double>(visual_spectrum_bands - 1U);
        const double frequency = 45.0 * std::pow(
            nyquist / 45.0,
            ratio
        );
        const double omega =
            2.0 * std::numbers::pi * frequency
            / static_cast<double>(sample_rate);
        const double cosine = std::cos(omega);
        const double sine = std::sin(omega);
        const double coefficient = 2.0 * cosine;
        double previous = 0.0;
        double previous_two = 0.0;
        for (std::size_t index = 0U; index < analyzed; ++index) {
            const double current =
                static_cast<double>(analysis_[index])
                + coefficient * previous
                - previous_two;
            previous_two = previous;
            previous = current;
        }
        const double real = previous - previous_two * cosine;
        const double imaginary = previous_two * sine;
        const double magnitude =
            std::sqrt(real * real + imaginary * imaginary)
            / static_cast<double>(std::max<std::size_t>(1U, analyzed));
        magnitudes_[band] = std::isfinite(magnitude)
            ? static_cast<float>(magnitude)
            : 0.0F;
        maximum_magnitude = std::max(
            maximum_magnitude,
            magnitudes_[band]
        );
    }

    const float visible_level = std::min(
        1.0F,
        std::sqrt(peak * 3.2F)
    );
    for (
        std::size_t band = 0U;
        band < visual_spectrum_bands;
        ++band
    ) {
        const float relative_db = maximum_magnitude <= 1.0e-9F
            ? -60.0F
            : 20.0F * std::log10(
                std::max(1.0e-9F, magnitudes_[band])
                / maximum_magnitude
            );
        const float shape = std::clamp(
            (relative_db + 54.0F) / 54.0F,
            0.0F,
            1.0F
        );
        const float mapped =
            shape * (0.12F + 0.88F * visible_level);
        spectrum_[band] = std::max(
            mapped,
            spectrum_[band] * 0.84F
        );
    }
    append_history_column();
    peak_ = peak;
    return peak;
}

visual_snapshot pcm_visual_analyzer::snapshot() const {
    std::scoped_lock lock(mutex_);
    return {
        .wave = wave_,
        .spectrum = spectrum_,
        .history = history_,
        .history_columns = history_columns_,
        .peak = peak_,
    };
}

void pcm_visual_analyzer::append_history_column() {
    if (history_columns_ == visual_history_columns) {
        constexpr std::size_t compacted =
            visual_history_columns / 2U;
        for (std::size_t column = 0U; column < compacted; ++column) {
            const std::size_t first =
                column * 2U * visual_spectrum_bands;
            const std::size_t second =
                first + visual_spectrum_bands;
            const std::size_t output =
                column * visual_spectrum_bands;
            for (
                std::size_t band = 0U;
                band < visual_spectrum_bands;
                ++band
            ) {
                history_[output + band] = std::max(
                    history_[first + band],
                    history_[second + band]
                );
            }
        }
        std::fill(
            history_.begin()
                + static_cast<std::ptrdiff_t>(
                    compacted * visual_spectrum_bands
                ),
            history_.end(),
            0.0F
        );
        history_columns_ = compacted;
    }
    std::copy(
        spectrum_.begin(),
        spectrum_.end(),
        history_.begin()
            + static_cast<std::ptrdiff_t>(
                history_columns_ * visual_spectrum_bands
            )
    );
    ++history_columns_;
}

visual_mode next_visual_mode(visual_mode mode) noexcept {
    switch (mode) {
    case visual_mode::field:
        return visual_mode::spectrum;
    case visual_mode::spectrum:
        return visual_mode::wave;
    case visual_mode::wave:
        return visual_mode::history;
    case visual_mode::history:
        return visual_mode::field;
    }
    return visual_mode::field;
}

std::string_view visual_mode_name(visual_mode mode) noexcept {
    switch (mode) {
    case visual_mode::field:
        return "Field";
    case visual_mode::spectrum:
        return "Spectrum";
    case visual_mode::wave:
        return "Wave";
    case visual_mode::history:
        return "History";
    }
    return "Field";
}

}  // namespace orkela
