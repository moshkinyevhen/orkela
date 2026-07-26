#ifndef ORKELA_RESONITH_FILE_H
#define ORKELA_RESONITH_FILE_H

#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

namespace orkela {

struct decoded_audio {
    std::uint32_t sample_rate = 0U;
    std::uint16_t channels = 0U;
    std::uint32_t frame_count = 0U;
    std::vector<std::int16_t> samples;
};

/*
 * Decode one complete LPS4/LPS5 research stream through Resonith Core.
 *
 * The Core preflights every record before this function allocates the final
 * PCM buffer. A failure returns false and leaves `audio` empty.
 */
bool decode_resonith_file(
    const std::filesystem::path& path,
    decoded_audio* audio,
    std::wstring* error
);

}  // namespace orkela

#endif
