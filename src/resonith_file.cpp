#include "resonith_file.h"

#include "resonith/lapped_compact.h"
#include "resonith/status.h"

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
constexpr std::uint64_t maximum_output_seconds = 2ULL * 60ULL * 60ULL;

struct field_storage {
    std::vector<std::uint8_t> scales;
    std::vector<std::uint16_t> counts;
    std::vector<std::uint16_t> positions;
    std::vector<std::int8_t> coefficients;
    std::vector<std::int64_t> overlap;

    field_storage(
        const resonith_lapped_requirements& requirements,
        bool include_overlap
    )
        : scales(std::max<std::size_t>(1U, requirements.scale_elements)),
          counts(std::max<std::size_t>(1U, requirements.count_elements)),
          positions(
              std::max<std::size_t>(1U, requirements.position_elements)
          ),
          coefficients(
              std::max<std::size_t>(1U, requirements.coefficient_elements)
          ),
          overlap(
              include_overlap
                  ? std::max<std::size_t>(
                        1U,
                        requirements.overlap_elements
                    )
                  : 0U
          ) {}

    resonith_lapped_workspace view(
        const resonith_lapped_requirements& requirements
    ) noexcept {
        return {
            scales.data(),
            requirements.scale_elements,
            counts.data(),
            requirements.count_elements,
            positions.data(),
            requirements.position_elements,
            coefficients.data(),
            requirements.coefficient_elements,
            overlap.empty() ? nullptr : overlap.data(),
            overlap.empty() ? 0U : requirements.overlap_elements,
        };
    }
};

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
        // Phase 1: authenticate shape and records before allocating PCM.
        const std::vector<std::uint8_t> input = read_file(path);
        resonith_lapped_compact_session session{};
        resonith_lapped_compact_requirements requirements{};
        const resonith_status open_status = resonith_lapped_compact_open(
            input.data(),
            input.size(),
            &session,
            &requirements
        );
        if (open_status != RESONITH_STATUS_OK) {
            return fail(
                L"Resonith preflight failed: "
                    + widen_ascii(resonith_status_string(open_status)),
                error
            );
        }
        if (
            requirements.output_channels == 0U
            || requirements.output_channels > 2U
            || requirements.sample_rate == 0U
        ) {
            return fail(
                L"This Orkela milestone supports mono or stereo PCM16.",
                error
            );
        }
        if (
            static_cast<std::uint64_t>(requirements.frame_count)
                > maximum_output_seconds
                    * static_cast<std::uint64_t>(requirements.sample_rate)
        ) {
            return fail(
                L"Decoded duration exceeds the two-hour research limit.",
                error
            );
        }

        const std::size_t channels = requirements.output_channels;
        if (
            static_cast<std::uint64_t>(requirements.frame_count)
                > std::numeric_limits<std::size_t>::max() / channels
        ) {
            return fail(L"Decoded PCM size overflows this process.", error);
        }
        const std::size_t output_elements =
            static_cast<std::size_t>(requirements.frame_count) * channels;

        // Phase 2: allocate exactly the bounds reported by Resonith Core.
        field_storage current(requirements.maximum_current, true);
        field_storage lookahead(requirements.maximum_lookahead, false);
        resonith_lapped_workspace current_view =
            current.view(requirements.maximum_current);
        resonith_lapped_workspace lookahead_view =
            lookahead.view(requirements.maximum_lookahead);
        std::vector<std::int16_t> packet_output(
            std::max<std::size_t>(
                1U,
                requirements.maximum_logical_output_elements
            )
        );
        std::vector<std::int16_t> decoded(output_elements);

        // Phase 3: pull logical intervals and place them at authenticated
        // timeline offsets. No WAV or external transcoder exists in this path.
        std::uint32_t expected_start = 0U;
        while (session.next_packet < session.packet_count) {
            const bool final_packet =
                session.next_packet + 1U == session.packet_count;
            std::uint32_t logical_start = 0U;
            std::size_t frames_written = 0U;
            const resonith_status decode_status =
                resonith_lapped_compact_decode_next(
                    &session,
                    &current_view,
                    final_packet ? nullptr : &lookahead_view,
                    packet_output.data(),
                    packet_output.size(),
                    &logical_start,
                    &frames_written
                );
            if (decode_status != RESONITH_STATUS_OK) {
                return fail(
                    L"Resonith decode failed: "
                        + widen_ascii(resonith_status_string(decode_status)),
                    error
                );
            }
            if (logical_start != expected_start) {
                return fail(
                    L"Resonith stream produced a discontinuous timeline.",
                    error
                );
            }
            if (
                frames_written
                    > static_cast<std::size_t>(requirements.frame_count)
                        - logical_start
                || frames_written > packet_output.size() / channels
            ) {
                return fail(
                    L"Resonith stream exceeded its preflight bounds.",
                    error
                );
            }

            const std::size_t element_start =
                static_cast<std::size_t>(logical_start) * channels;
            const std::size_t element_count = frames_written * channels;
            std::copy_n(
                packet_output.data(),
                element_count,
                decoded.data() + element_start
            );
            expected_start += static_cast<std::uint32_t>(frames_written);
        }
        if (expected_start != requirements.frame_count) {
            return fail(
                L"Resonith stream ended before its declared frame count.",
                error
            );
        }

        audio->sample_rate = requirements.sample_rate;
        audio->channels = requirements.output_channels;
        audio->frame_count = requirements.frame_count;
        audio->samples = std::move(decoded);
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

}  // namespace orkela
