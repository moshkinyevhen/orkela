#ifndef ORKELA_RESONITH_PULL_DECODER_H
#define ORKELA_RESONITH_PULL_DECODER_H

#include "orkela/decoded_audio.h"

#include <cstddef>
#include <cstdint>
#include <memory>
#include <span>
#include <string>
#include <vector>

namespace orkela {

struct resonith_stream_info {
    std::uint32_t sample_rate = 0U;
    std::uint32_t frame_count = 0U;
    std::uint16_t channels = 0U;
    std::size_t maximum_packet_elements = 0U;
};

enum class pull_result {
    data,
    end,
    error,
};

/*
 * Allocation-owning adapter around Resonith Core's allocation-free pull API.
 *
 * Opening authenticates either compact lapped transport or prospective MFT1
 * and allocates its bounded workspace once. `read_next` performs no allocation
 * on its successful real-time path; callers may therefore decode on a
 * dedicated producer thread and feed a platform audio queue without exposing
 * codec state to UI code.
 */
class resonith_pull_decoder final {
public:
    static std::unique_ptr<resonith_pull_decoder> open(
        std::vector<std::uint8_t> input,
        std::string* error
    );

    resonith_pull_decoder(const resonith_pull_decoder&) = delete;
    resonith_pull_decoder& operator=(const resonith_pull_decoder&) = delete;
    resonith_pull_decoder(resonith_pull_decoder&&) noexcept;
    resonith_pull_decoder& operator=(resonith_pull_decoder&&) noexcept;
    ~resonith_pull_decoder();

    [[nodiscard]] const resonith_stream_info& info() const noexcept;

    pull_result read_next(
        std::span<std::int16_t> destination,
        std::uint32_t* logical_start,
        std::size_t* frames_written,
        std::string* error
    );

private:
    struct implementation;

    explicit resonith_pull_decoder(
        std::unique_ptr<implementation> state
    ) noexcept;

    std::unique_ptr<implementation> implementation_;
};

/*
 * Convenience path for desktop visualization and bounded short media.
 * Mobile playback uses `resonith_pull_decoder` directly and never needs a
 * complete decoded-PCM allocation.
 */
bool decode_resonith_bytes(
    std::vector<std::uint8_t> input,
    decoded_audio* audio,
    std::string* error
);

}  // namespace orkela

#endif
