#include "orkela/resonith_pull_decoder.h"

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <span>
#include <string>
#include <vector>

namespace {

std::vector<std::uint8_t> read_file(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        throw std::runtime_error("cannot open input");
    }
    return {
        std::istreambuf_iterator<char>(input),
        std::istreambuf_iterator<char>(),
    };
}

std::uint64_t update_hash(
    std::uint64_t hash,
    std::span<const std::int16_t> samples
) noexcept {
    constexpr std::uint64_t prime = 1099511628211ULL;
    for (const std::int16_t sample : samples) {
        const auto bits = static_cast<std::uint16_t>(sample);
        hash ^= static_cast<std::uint8_t>(bits & 0xFFU);
        hash *= prime;
        hash ^= static_cast<std::uint8_t>(bits >> 8U);
        hash *= prime;
    }
    return hash;
}

bool decode_one(const std::filesystem::path& path) {
    std::vector<std::uint8_t> payload = read_file(path);
    std::string error;
    auto decoder = orkela::resonith_pull_decoder::open(payload, &error);
    if (decoder == nullptr) {
        std::cerr << path.filename().string() << ": open failed: " << error
                  << '\n';
        return false;
    }
    const orkela::resonith_stream_info info = decoder->info();
    if (
        info.sample_rate == 0U
        || info.channels == 0U
        || info.frame_count == 0U
        || info.maximum_packet_elements == 0U
    ) {
        std::cerr << path.filename().string() << ": invalid preflight\n";
        return false;
    }

    std::vector<std::int16_t> packet(info.maximum_packet_elements);
    std::uint64_t pcm_hash = 1469598103934665603ULL;
    std::uint64_t decoded_frames = 0U;
    while (true) {
        std::uint32_t logical_start = 0U;
        std::size_t frames_written = 0U;
        const orkela::pull_result result = decoder->read_next(
            packet,
            &logical_start,
            &frames_written,
            &error
        );
        if (result == orkela::pull_result::end) {
            break;
        }
        if (result != orkela::pull_result::data) {
            std::cerr << path.filename().string() << ": pull failed: " << error
                      << '\n';
            return false;
        }
        if (logical_start != decoded_frames) {
            std::cerr << path.filename().string() << ": discontinuous timeline\n";
            return false;
        }
        const std::size_t elements =
            frames_written * static_cast<std::size_t>(info.channels);
        pcm_hash = update_hash(
            pcm_hash,
            std::span<const std::int16_t>(packet.data(), elements)
        );
        decoded_frames += frames_written;
    }
    if (decoded_frames != info.frame_count) {
        std::cerr << path.filename().string() << ": incomplete decode\n";
        return false;
    }

    // The same parser must reject a deterministic truncation before playback.
    if (payload.size() < 2U) {
        std::cerr << path.filename().string() << ": input is unexpectedly tiny\n";
        return false;
    }
    payload.pop_back();
    if (orkela::resonith_pull_decoder::open(std::move(payload), &error) != nullptr) {
        std::cerr << path.filename().string() << ": truncation was accepted\n";
        return false;
    }

    std::cout << path.filename().string() << " frames=" << decoded_frames
              << " channels=" << info.channels
              << " sample_rate=" << info.sample_rate
              << " pcm_fnv64=" << pcm_hash << '\n';
    return true;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        std::cerr << "usage: orkela_session_gate <stream> [stream...]\n";
        return 2;
    }
    try {
        for (int index = 1; index < argc; ++index) {
            if (!decode_one(std::filesystem::path(argv[index]))) {
                return 1;
            }
        }
    } catch (const std::exception& exception) {
        std::cerr << "session gate failed: " << exception.what() << '\n';
        return 1;
    }
    return 0;
}
