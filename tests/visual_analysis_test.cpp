#include "orkela/visual_analysis.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <numbers>
#include <span>

namespace {

constexpr std::uint32_t sample_rate = 48000U;
constexpr std::uint16_t channels = 2U;
constexpr std::size_t frames = 1024U;

std::array<std::int16_t, frames * channels> make_tone(
    double frequency,
    double gain
) {
    std::array<std::int16_t, frames * channels> result{};
    for (std::size_t frame = 0U; frame < frames; ++frame) {
        const double phase =
            2.0 * std::numbers::pi * frequency
            * static_cast<double>(frame)
            / static_cast<double>(sample_rate);
        const auto sample = static_cast<std::int16_t>(
            std::lround(std::sin(phase) * gain * 32767.0)
        );
        result[frame * channels] = sample;
        result[frame * channels + 1U] = sample;
    }
    return result;
}

bool nonzero(std::span<const float> values) {
    return std::any_of(
        values.begin(),
        values.end(),
        [](float value) {
            return value > 0.001F;
        }
    );
}

}  // namespace

int main() {
    orkela::pcm_visual_analyzer analyzer;
    const auto initial = analyzer.snapshot();
    if (
        initial.history_columns != 0U
        || initial.peak != 0.0F
        || nonzero(initial.wave)
        || nonzero(initial.spectrum)
    ) {
        std::cerr << "initial visual state is not empty\n";
        return 1;
    }

    const auto tone = make_tone(440.0, 0.65);
    for (
        std::size_t packet = 0U;
        packet < orkela::visual_history_columns + 37U;
        ++packet
    ) {
        if (
            analyzer.offer(tone, channels, sample_rate)
                < 0.60F
        ) {
            std::cerr << "tone peak was not measured\n";
            return 2;
        }
    }

    const auto snapshot = analyzer.snapshot();
    if (
        snapshot.history_columns == 0U
        || snapshot.history_columns > orkela::visual_history_columns
        || !nonzero(snapshot.wave)
        || !nonzero(snapshot.spectrum)
        || !nonzero(snapshot.history)
    ) {
        std::cerr << "visual analysis did not retain signal structure\n";
        return 3;
    }

    auto mode = orkela::visual_mode::field;
    mode = orkela::next_visual_mode(mode);
    mode = orkela::next_visual_mode(mode);
    mode = orkela::next_visual_mode(mode);
    if (
        mode != orkela::visual_mode::history
        || orkela::visual_mode_name(mode) != "History"
        || orkela::next_visual_mode(mode) != orkela::visual_mode::field
    ) {
        std::cerr << "visual mode cycle is inconsistent\n";
        return 4;
    }

    analyzer.reset();
    const auto reset = analyzer.snapshot();
    if (
        reset.history_columns != 0U
        || reset.peak != 0.0F
        || nonzero(reset.wave)
        || nonzero(reset.spectrum)
        || nonzero(reset.history)
    ) {
        std::cerr << "reset retained stale visual state\n";
        return 5;
    }
    return 0;
}
