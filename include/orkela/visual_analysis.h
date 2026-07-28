#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <mutex>
#include <span>
#include <string_view>

namespace orkela {

inline constexpr std::size_t visual_wave_points = 128U;
inline constexpr std::size_t visual_spectrum_bands = 42U;
inline constexpr std::size_t visual_history_columns = 96U;

enum class visual_mode : std::uint8_t {
    field,
    spectrum,
    wave,
    history,
};

struct visual_snapshot {
    std::array<float, visual_wave_points> wave{};
    std::array<float, visual_spectrum_bands> spectrum{};
    std::array<
        float,
        visual_history_columns * visual_spectrum_bands
    > history{};
    std::size_t history_columns = 0U;
    float peak = 0.0F;
};

/**
 * Builds bounded presentation data from interleaved PCM16 packets.
 *
 * Feed this object from a decoder or playback worker, never from a real-time
 * device callback: snapshot publication takes a short mutex. All storage is
 * fixed at construction and offer() performs no allocation or file I/O.
 */
class pcm_visual_analyzer final {
public:
    pcm_visual_analyzer();

    void reset();

    [[nodiscard]] float offer(
        std::span<const std::int16_t> interleaved_pcm,
        std::uint16_t channels,
        std::uint32_t sample_rate
    );

    [[nodiscard]] visual_snapshot snapshot() const;

private:
    static constexpr std::size_t analysis_samples = 256U;

    void append_history_column();

    mutable std::mutex mutex_;
    std::array<float, visual_wave_points> wave_{};
    std::array<float, visual_spectrum_bands> spectrum_{};
    std::array<float, visual_spectrum_bands> magnitudes_{};
    std::array<float, analysis_samples> analysis_{};
    std::array<
        float,
        visual_history_columns * visual_spectrum_bands
    > history_{};
    std::array<float, analysis_samples> window_{};
    std::size_t history_columns_ = 0U;
    float peak_ = 0.0F;
};

[[nodiscard]] visual_mode next_visual_mode(visual_mode mode) noexcept;
[[nodiscard]] std::string_view visual_mode_name(visual_mode mode) noexcept;

}  // namespace orkela
