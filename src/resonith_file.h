#ifndef ORKELA_RESONITH_FILE_H
#define ORKELA_RESONITH_FILE_H

#include "orkela/decoded_audio.h"

#include <filesystem>
#include <span>
#include <string>

namespace orkela {

/*
 * Open one Resonith stream and decode only a bounded visualization preview.
 *
 * The authenticated source bytes remain attached to `audio`; wave_player
 * reopens the allocation-bounded pull decoder and feeds short platform audio
 * buffers while playback progresses. A failure returns false and leaves
 * `audio` empty.
 */
bool decode_resonith_file(
    const std::filesystem::path& path,
    decoded_audio* audio,
    std::wstring* error
);

/*
 * Decode the authenticated stream a second time at background priority and
 * reduce it directly into a bounded peak envelope. No full-track PCM buffer is
 * created, so this never restores the old startup stall or memory spike.
 */
bool analyze_resonith_waveform(
    const decoded_audio& audio,
    std::span<float> waveform,
    std::string* error
);

}  // namespace orkela

#endif
