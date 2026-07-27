#ifndef ORKELA_DECODED_AUDIO_H
#define ORKELA_DECODED_AUDIO_H

#include <cstdint>
#include <vector>

namespace orkela {

struct decoded_audio {
    std::uint32_t sample_rate = 0U;
    std::uint16_t channels = 0U;
    std::uint32_t frame_count = 0U;
    std::vector<std::int16_t> samples;
};

}  // namespace orkela

#endif
