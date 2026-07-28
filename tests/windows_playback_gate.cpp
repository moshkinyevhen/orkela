#include "resonith_file.h"
#include "wave_player.h"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <memory>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

namespace {

bool exercise(
    const std::filesystem::path& path,
    bool allow_headless
) {
    const auto load_begin = std::chrono::steady_clock::now();
    auto audio = std::make_shared<orkela::decoded_audio>();
    std::wstring error;
    if (!orkela::decode_resonith_file(path, audio.get(), &error)) {
        std::wcerr << path.filename().wstring()
                   << L": load failed: " << error << L'\n';
        return false;
    }
    const auto load_end = std::chrono::steady_clock::now();

    const UINT output_device_count = waveOutGetNumDevs();
    if (allow_headless && output_device_count == 0U) {
        std::int32_t preview_peak = 0;
        for (const std::int16_t sample : audio->samples) {
            preview_peak = std::max(
                preview_peak,
                std::abs(static_cast<std::int32_t>(sample))
            );
        }
        if (audio->samples.empty() || preview_peak == 0) {
            std::wcerr << path.filename().wstring()
                       << L": headless preview is empty or silent\n";
            return false;
        }
        std::wcout << path.filename().wstring()
                   << L" hardware_playback=skipped"
                   << L" reason=no_waveout_device"
                   << L" preview_elements=" << audio->samples.size()
                   << L" preview_peak=" << preview_peak << L'\n';
        return true;
    }

    orkela::wave_player player;
    player.play(audio, 0U, [](std::wstring) {});
    const auto playback_begin = std::chrono::steady_clock::now();
    const auto deadline = playback_begin + std::chrono::seconds(5);
    std::vector<std::int16_t> visual(8192U);
    std::size_t visual_elements = 0U;
    std::uint32_t visual_start = 0U;
    std::uint16_t visual_channels = 0U;
    std::int32_t visual_peak = 0;
    auto first_advance = deadline;
    while (
        player.is_playing()
        && std::chrono::steady_clock::now() < deadline
    ) {
        visual_elements = player.copy_visual_snapshot(
            visual,
            &visual_start,
            &visual_channels
        );
        visual_peak = 0;
        for (std::size_t index = 0U; index < visual_elements; ++index) {
            visual_peak = std::max(
                visual_peak,
                std::abs(static_cast<std::int32_t>(visual[index]))
            );
        }
        const std::uint32_t current_position = player.position_frame();
        if (current_position != 0U && first_advance == deadline) {
            first_advance = std::chrono::steady_clock::now();
        }
        const std::size_t current_visual_frames = visual_channels == 0U
            ? 0U
            : visual_elements / visual_channels;
        if (
            current_position != 0U
            && visual_peak != 0
            && current_position >= visual_start
            && static_cast<std::uint64_t>(current_position)
                < static_cast<std::uint64_t>(visual_start)
                    + current_visual_frames
        ) {
            break;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    const auto visual_ready = std::chrono::steady_clock::now();
    const std::uint32_t position = player.position_frame();
    const std::size_t visual_frames = visual_channels == 0U
        ? 0U
        : visual_elements / visual_channels;
    const bool position_in_visual = position >= visual_start
        && static_cast<std::uint64_t>(position)
            < static_cast<std::uint64_t>(visual_start) + visual_frames;
    player.stop();
    if (position == 0U) {
        std::wcerr << path.filename().wstring()
                   << L": Windows playback did not advance\n";
        return false;
    }
    if (
        visual_elements == 0U
        || visual_channels != audio->channels
        || visual_peak == 0
        || !position_in_visual
    ) {
        std::wcerr << path.filename().wstring()
                   << L": live PCM visualization snapshot is invalid"
                   << L" elements=" << visual_elements
                   << L" channels=" << visual_channels
                   << L" peak=" << visual_peak
                   << L" start=" << visual_start
                   << L" position=" << position
                   << L'\n';
        return false;
    }

    const double load_seconds =
        std::chrono::duration<double>(load_end - load_begin).count();
    const double advance_seconds =
        std::chrono::duration<double>(first_advance - playback_begin).count();
    const double visual_seconds =
        std::chrono::duration<double>(visual_ready - playback_begin).count();
    std::wcout << path.filename().wstring()
               << L" load_seconds=" << load_seconds
               << L" advance_seconds=" << advance_seconds
               << L" visual_seconds=" << visual_seconds
               << L" first_position=" << position
               << L" visual_start=" << visual_start
               << L" visual_frames=" << visual_frames
               << L" visual_peak=" << visual_peak
               << L'\n';
    return true;
}

}  // namespace

int main(int argc, char** argv) {
    bool allow_headless = false;
    int first_path = 1;
    if (
        argc >= 2
        && std::string_view(argv[1]) == "--allow-headless"
    ) {
        allow_headless = true;
        first_path = 2;
    }
    if (argc <= first_path) {
        std::cerr
            << "usage: orkela_windows_playback_gate "
            << "[--allow-headless] <stream> [stream...]\n";
        return 2;
    }
    for (int index = first_path; index < argc; ++index) {
        if (!exercise(
                std::filesystem::path(argv[index]),
                allow_headless
            )) {
            return 1;
        }
    }
    return 0;
}
