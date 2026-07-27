#ifndef ORKELA_RESONITH_FILE_H
#define ORKELA_RESONITH_FILE_H

#include "orkela/decoded_audio.h"

#include <filesystem>
#include <string>

namespace orkela {

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
