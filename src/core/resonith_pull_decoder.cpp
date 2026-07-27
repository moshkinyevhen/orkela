#include "orkela/resonith_pull_decoder.h"

#include "resonith/lapped_compact.h"
#include "resonith/maf_typed.h"
#include "resonith/status.h"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace orkela {
namespace {

constexpr std::size_t maximum_input_bytes = 512ULL * 1024ULL * 1024ULL;
constexpr std::uint64_t maximum_output_seconds = 2ULL * 60ULL * 60ULL;

class decoder_error final : public std::runtime_error {
public:
    explicit decoder_error(const std::string& message)
        : std::runtime_error(message) {}
};

std::string status_message(
    const char* phase,
    resonith_status status
) {
    const char* detail = resonith_status_string(status);
    return std::string(phase) + ": "
        + (detail == nullptr ? "unknown Resonith error" : detail);
}

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

struct maf_storage {
    std::vector<std::int32_t> coefficients;
    std::vector<std::int16_t> bases;
    std::vector<std::int16_t> histories;
    std::vector<std::int16_t> planar;
    std::vector<std::int16_t> excitation;
    std::vector<std::int16_t> filtered;
    std::vector<std::int16_t> matrix;

    explicit maf_storage(
        const resonith_maf_typed_requirements& requirements
    )
        : coefficients(
              std::max<std::size_t>(
                  1U,
                  requirements.filter_coefficient_elements
              )
          ),
          bases(std::max<std::size_t>(1U, requirements.basis_elements)),
          histories(
              std::max<std::size_t>(
                  1U,
                  requirements.filter_history_elements
              )
          ),
          planar(std::max<std::size_t>(1U, requirements.planar_elements)),
          excitation(
              std::max<std::size_t>(1U, requirements.working_elements / 2U)
          ),
          filtered(
              std::max<std::size_t>(1U, requirements.working_elements / 2U)
          ),
          matrix(
              std::max<std::size_t>(
                  1U,
                  requirements.mix_matrix_elements
              )
          ) {}

    resonith_maf_typed_workspace view(
        const resonith_maf_typed_requirements& requirements
    ) noexcept {
        return {
            coefficients.data(),
            requirements.filter_coefficient_elements,
            bases.data(),
            requirements.basis_elements,
            histories.data(),
            requirements.filter_history_elements,
            planar.data(),
            requirements.planar_elements,
            excitation.data(),
            requirements.working_elements / 2U,
            filtered.data(),
            requirements.working_elements / 2U,
            matrix.data(),
            requirements.mix_matrix_elements,
        };
    }
};

bool fail(std::string message, std::string* error) {
    if (error != nullptr) {
        *error = std::move(message);
    }
    return false;
}

}  // namespace

struct resonith_pull_decoder::implementation {
    enum class backend {
        lapped_compact,
        maf_typed,
    };

    std::vector<std::uint8_t> input;
    backend active_backend = backend::lapped_compact;
    resonith_lapped_compact_session session{};
    resonith_lapped_compact_requirements requirements{};
    resonith_maf_typed_session maf_session{};
    resonith_maf_typed_requirements maf_requirements{};
    resonith_stream_info stream_info{};
    std::unique_ptr<field_storage> current;
    std::unique_ptr<field_storage> lookahead;
    std::unique_ptr<maf_storage> maf_memory;
    std::uint32_t expected_start = 0U;

    explicit implementation(std::vector<std::uint8_t> bytes)
        : input(std::move(bytes)) {
        if (input.empty()) {
            throw decoder_error("input is empty");
        }
        if (input.size() > maximum_input_bytes) {
            throw decoder_error("input exceeds the 512 MiB research limit");
        }

        if (
            input.size() >= 4U
            && input[0] == static_cast<std::uint8_t>('M')
            && input[1] == static_cast<std::uint8_t>('F')
            && input[2] == static_cast<std::uint8_t>('T')
            && input[3] == static_cast<std::uint8_t>('1')
        ) {
            open_maf();
            return;
        }
        open_lapped();
    }

    void validate_output_bounds(
        std::uint32_t sample_rate,
        std::uint32_t frame_count,
        std::uint16_t channels
    ) {
        if (channels == 0U || channels > 2U || sample_rate == 0U) {
            throw decoder_error(
                "this Orkela milestone supports mono or stereo PCM16"
            );
        }
        if (
            static_cast<std::uint64_t>(frame_count)
                > maximum_output_seconds
                    * static_cast<std::uint64_t>(sample_rate)
        ) {
            throw decoder_error(
                "decoded duration exceeds the two-hour research limit"
            );
        }
    }

    void open_lapped() {
        const resonith_status status = resonith_lapped_compact_open(
            input.data(),
            input.size(),
            &session,
            &requirements
        );
        if (status != RESONITH_STATUS_OK) {
            throw decoder_error(status_message("Resonith preflight", status));
        }
        validate_output_bounds(
            requirements.sample_rate,
            requirements.frame_count,
            requirements.output_channels
        );
        current = std::make_unique<field_storage>(
            requirements.maximum_current,
            true
        );
        lookahead = std::make_unique<field_storage>(
            requirements.maximum_lookahead,
            false
        );
        stream_info = {
            requirements.sample_rate,
            requirements.frame_count,
            requirements.output_channels,
            requirements.maximum_logical_output_elements,
        };
    }

    void open_maf() {
        active_backend = backend::maf_typed;
        resonith_status status = resonith_maf_typed_inspect(
            input.data(),
            input.size(),
            &maf_requirements
        );
        if (status != RESONITH_STATUS_OK) {
            throw decoder_error(
                status_message("Resonith MFT1 preflight", status)
            );
        }
        validate_output_bounds(
            maf_requirements.sample_rate,
            maf_requirements.total_frames,
            maf_requirements.output_channels
        );
        maf_memory = std::make_unique<maf_storage>(maf_requirements);
        resonith_maf_typed_workspace workspace =
            maf_memory->view(maf_requirements);
        status = resonith_maf_typed_open(
            input.data(),
            input.size(),
            &workspace,
            &maf_session
        );
        if (status != RESONITH_STATUS_OK) {
            throw decoder_error(status_message("Resonith MFT1 open", status));
        }
        stream_info = {
            maf_requirements.sample_rate,
            maf_requirements.total_frames,
            maf_requirements.output_channels,
            static_cast<std::size_t>(maf_requirements.render_quantum)
                * maf_requirements.output_channels,
        };
    }
};

resonith_pull_decoder::resonith_pull_decoder(
    std::unique_ptr<implementation> implementation
) noexcept
    : implementation_(std::move(implementation)) {}

resonith_pull_decoder::resonith_pull_decoder(
    resonith_pull_decoder&&
) noexcept = default;

resonith_pull_decoder& resonith_pull_decoder::operator=(
    resonith_pull_decoder&&
) noexcept = default;

resonith_pull_decoder::~resonith_pull_decoder() = default;

std::unique_ptr<resonith_pull_decoder> resonith_pull_decoder::open(
    std::vector<std::uint8_t> input,
    std::string* error
) {
    try {
        auto state = std::make_unique<implementation>(std::move(input));
        if (error != nullptr) {
            error->clear();
        }
        return std::unique_ptr<resonith_pull_decoder>(
            new resonith_pull_decoder(std::move(state))
        );
    } catch (const std::exception& exception) {
        fail(exception.what(), error);
        return nullptr;
    }
}

const resonith_stream_info& resonith_pull_decoder::info() const noexcept {
    return implementation_->stream_info;
}

pull_result resonith_pull_decoder::read_next(
    std::span<std::int16_t> destination,
    std::uint32_t* logical_start,
    std::size_t* frames_written,
    std::string* error
) {
    if (logical_start == nullptr || frames_written == nullptr) {
        fail("null pull result pointer", error);
        return pull_result::error;
    }
    *logical_start = implementation_->expected_start;
    *frames_written = 0U;

    auto& state = *implementation_;
    if (
        state.active_backend
        == implementation::backend::maf_typed
    ) {
        if (state.expected_start == state.maf_requirements.total_frames) {
            if (error != nullptr) {
                error->clear();
            }
            return pull_result::end;
        }
        if (destination.size() < state.stream_info.maximum_packet_elements) {
            fail("pull destination is smaller than the preflight bound", error);
            return pull_result::error;
        }
        const std::uint32_t remaining =
            state.maf_requirements.total_frames - state.expected_start;
        const std::uint32_t requested = std::min(
            state.maf_requirements.render_quantum,
            remaining
        );
        std::uint32_t written = 0U;
        const resonith_status status = resonith_maf_typed_render(
            &state.maf_session,
            requested,
            destination.data(),
            destination.size(),
            &written
        );
        if (status != RESONITH_STATUS_OK || written > requested) {
            fail(status_message("Resonith MFT1 render", status), error);
            return pull_result::error;
        }
        if (written == 0U) {
            fail("Resonith MFT1 ended before its declared frame count", error);
            return pull_result::error;
        }
        *frames_written = written;
        state.expected_start += written;
        if (error != nullptr) {
            error->clear();
        }
        return pull_result::data;
    }
    if (state.session.next_packet >= state.session.packet_count) {
        if (state.expected_start != state.requirements.frame_count) {
            fail("Resonith stream ended before its declared frame count", error);
            return pull_result::error;
        }
        if (error != nullptr) {
            error->clear();
        }
        return pull_result::end;
    }
    if (destination.size() < state.stream_info.maximum_packet_elements) {
        fail("pull destination is smaller than the preflight bound", error);
        return pull_result::error;
    }

    const bool final_packet =
        state.session.next_packet + 1U == state.session.packet_count;
    resonith_lapped_workspace current_view =
        state.current->view(state.requirements.maximum_current);
    resonith_lapped_workspace lookahead_view =
        state.lookahead->view(state.requirements.maximum_lookahead);
    const resonith_status status = resonith_lapped_compact_decode_next(
        &state.session,
        &current_view,
        final_packet ? nullptr : &lookahead_view,
        destination.data(),
        destination.size(),
        logical_start,
        frames_written
    );
    if (status != RESONITH_STATUS_OK) {
        fail(status_message("Resonith decode", status), error);
        return pull_result::error;
    }
    if (*logical_start != state.expected_start) {
        fail("Resonith stream produced a discontinuous timeline", error);
        return pull_result::error;
    }
    const std::size_t channels = state.requirements.output_channels;
    if (
        *frames_written
            > static_cast<std::size_t>(state.requirements.frame_count)
                - *logical_start
        || *frames_written > destination.size() / channels
    ) {
        fail("Resonith stream exceeded its preflight bounds", error);
        return pull_result::error;
    }
    state.expected_start += static_cast<std::uint32_t>(*frames_written);
    if (error != nullptr) {
        error->clear();
    }
    return pull_result::data;
}

bool decode_resonith_bytes(
    std::vector<std::uint8_t> input,
    decoded_audio* audio,
    std::string* error
) {
    if (audio == nullptr) {
        return fail("null decoded-audio output", error);
    }
    *audio = {};

    auto decoder = resonith_pull_decoder::open(std::move(input), error);
    if (decoder == nullptr) {
        return false;
    }
    const resonith_stream_info stream = decoder->info();
    const std::size_t channels = stream.channels;
    if (
        static_cast<std::uint64_t>(stream.frame_count)
            > std::numeric_limits<std::size_t>::max() / channels
    ) {
        return fail("decoded PCM size overflows this process", error);
    }
    const std::size_t output_elements =
        static_cast<std::size_t>(stream.frame_count) * channels;

    try {
        std::vector<std::int16_t> decoded(output_elements);
        std::vector<std::int16_t> packet(
            std::max<std::size_t>(1U, stream.maximum_packet_elements)
        );
        for (;;) {
            std::uint32_t logical_start = 0U;
            std::size_t frames_written = 0U;
            const pull_result result = decoder->read_next(
                packet,
                &logical_start,
                &frames_written,
                error
            );
            if (result == pull_result::end) {
                break;
            }
            if (result == pull_result::error) {
                return false;
            }
            const std::size_t element_start =
                static_cast<std::size_t>(logical_start) * channels;
            const std::size_t element_count = frames_written * channels;
            std::copy_n(
                packet.data(),
                element_count,
                decoded.data() + element_start
            );
        }

        audio->sample_rate = stream.sample_rate;
        audio->channels = stream.channels;
        audio->frame_count = stream.frame_count;
        audio->samples = std::move(decoded);
        if (error != nullptr) {
            error->clear();
        }
        return true;
    } catch (const std::exception& exception) {
        return fail(exception.what(), error);
    }
}

}  // namespace orkela
