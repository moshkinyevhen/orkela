#include "resonith_file.h"

#include "orkela/resonith_pull_decoder.h"

#include <algorithm>
#include <cstddef>
#include <fstream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>

namespace orkela {
namespace {

constexpr std::uintmax_t maximum_input_bytes = 512ULL * 1024ULL * 1024ULL;

bool fail(std::wstring message, std::wstring* error) {
    if (error != nullptr) {
        *error = std::move(message);
    }
    return false;
}

std::wstring widen_ascii(const char* text) {
    std::wstring result;
    if (text == nullptr) {
        return result;
    }
    while (*text != '\0') {
        result.push_back(static_cast<wchar_t>(
            static_cast<unsigned char>(*text)
        ));
        ++text;
    }
    return result;
}

std::vector<std::uint8_t> read_file(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary | std::ios::ate);
    if (!input) {
        throw std::runtime_error("cannot open input file");
    }

    const std::streampos end_position = input.tellg();
    if (end_position <= std::streampos(0)) {
        throw std::runtime_error("input file is empty");
    }
    const auto byte_count = static_cast<std::uintmax_t>(
        end_position - std::streampos(0)
    );
    if (
        byte_count > maximum_input_bytes
        || byte_count > std::numeric_limits<std::size_t>::max()
        || byte_count
            > static_cast<std::uintmax_t>(
                std::numeric_limits<std::streamsize>::max()
            )
    ) {
        throw std::runtime_error("input file exceeds the research limit");
    }

    std::vector<std::uint8_t> bytes(static_cast<std::size_t>(byte_count));
    input.seekg(0, std::ios::beg);
    input.read(
        reinterpret_cast<char*>(bytes.data()),
        static_cast<std::streamsize>(bytes.size())
    );
    if (!input) {
        throw std::runtime_error("cannot read the complete input file");
    }
    return bytes;
}

}  // namespace

bool decode_resonith_file(
    const std::filesystem::path& path,
    decoded_audio* audio,
    std::wstring* error
) {
    if (audio == nullptr) {
        return fail(L"Internal error: null output.", error);
    }
    *audio = {};

    try {
        // File ownership is platform-specific; validation and synthesis
        // policy remain in the portable pull session.
        auto source = std::make_shared<const std::vector<std::uint8_t>>(
            read_file(path)
        );
        std::string portable_error;
        auto decoder = resonith_pull_decoder::open(
            *source,
            &portable_error
        );
        if (decoder == nullptr) {
            return fail(
                L"Cannot decode file: " + widen_ascii(portable_error.c_str()),
                error
            );
        }
        const resonith_stream_info info = decoder->info();
        std::vector<std::int16_t> preview(
            std::max<std::size_t>(1U, info.maximum_packet_elements)
        );
        std::uint32_t logical_start = 0U;
        std::size_t frames_written = 0U;
        const pull_result result = decoder->read_next(
            preview,
            &logical_start,
            &frames_written,
            &portable_error
        );
        if (
            result != pull_result::data
            || logical_start != 0U
            || frames_written == 0U
        ) {
            return fail(
                L"Cannot decode first audio packet: "
                    + widen_ascii(portable_error.c_str()),
                error
            );
        }
        preview.resize(
            frames_written * static_cast<std::size_t>(info.channels)
        );
        audio->sample_rate = info.sample_rate;
        audio->channels = info.channels;
        audio->frame_count = info.frame_count;
        audio->source_bytes = std::move(source);
        audio->samples = std::move(preview);
        if (error != nullptr) {
            error->clear();
        }
        return true;
    } catch (const std::exception& exception) {
        return fail(
            L"Cannot decode file: " + widen_ascii(exception.what()),
            error
        );
    }
}

bool analyze_resonith_waveform(
    const decoded_audio& audio,
    std::span<float> waveform,
    std::string* error
) {
    std::fill(waveform.begin(), waveform.end(), 0.0F);
    if (
        audio.source_bytes == nullptr
        || audio.source_bytes->empty()
        || audio.channels == 0U
        || audio.frame_count == 0U
        || waveform.empty()
    ) {
        if (error != nullptr) {
            *error = "invalid waveform-analysis input";
        }
        return false;
    }

    try {
        std::string portable_error;
        auto decoder = resonith_pull_decoder::open(
            *audio.source_bytes,
            &portable_error
        );
        if (decoder == nullptr) {
            if (error != nullptr) {
                *error = std::move(portable_error);
            }
            return false;
        }
        const resonith_stream_info info = decoder->info();
        if (
            info.channels != audio.channels
            || info.frame_count != audio.frame_count
        ) {
            if (error != nullptr) {
                *error = "waveform stream metadata changed after preflight";
            }
            return false;
        }

        std::vector<std::int16_t> packet(
            std::max<std::size_t>(1U, info.maximum_packet_elements)
        );
        while (true) {
            std::uint32_t logical_start = 0U;
            std::size_t frames_written = 0U;
            const pull_result result = decoder->read_next(
                packet,
                &logical_start,
                &frames_written,
                &portable_error
            );
            if (result == pull_result::error) {
                if (error != nullptr) {
                    *error = std::move(portable_error);
                }
                return false;
            }
            if (result == pull_result::end) {
                break;
            }
            for (std::size_t local = 0U; local < frames_written; ++local) {
                const std::uint64_t absolute =
                    static_cast<std::uint64_t>(logical_start) + local;
                if (absolute >= audio.frame_count) {
                    if (error != nullptr) {
                        *error = "waveform packet exceeds declared duration";
                    }
                    return false;
                }
                const std::size_t column = std::min<std::size_t>(
                    waveform.size() - 1U,
                    absolute * waveform.size() / audio.frame_count
                );
                std::int32_t mixed = 0;
                for (
                    std::uint16_t channel = 0U;
                    channel < audio.channels;
                    ++channel
                ) {
                    mixed += std::abs(
                        static_cast<std::int32_t>(
                            packet[
                                local * audio.channels + channel
                            ]
                        )
                    );
                }
                const float peak = static_cast<float>(
                    mixed / static_cast<std::int32_t>(audio.channels)
                ) / 32768.0F;
                waveform[column] = std::max(waveform[column], peak);
            }
        }
        if (error != nullptr) {
            error->clear();
        }
        return true;
    } catch (const std::exception& exception) {
        if (error != nullptr) {
            *error = exception.what();
        }
        return false;
    }
}

}  // namespace orkela
