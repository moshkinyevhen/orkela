#include "orkela/resonith_pull_decoder.h"

#include "resonith/maf_typed.h"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
#include <utility>
#include <vector>

namespace {

void append_u16(std::vector<std::uint8_t>& output, std::uint16_t value) {
    output.push_back(static_cast<std::uint8_t>(value));
    output.push_back(static_cast<std::uint8_t>(value >> 8U));
}

void append_i16(std::vector<std::uint8_t>& output, std::int16_t value) {
    append_u16(output, static_cast<std::uint16_t>(value));
}

void append_u32(std::vector<std::uint8_t>& output, std::uint32_t value) {
    for (unsigned int shift = 0U; shift < 32U; shift += 8U) {
        output.push_back(static_cast<std::uint8_t>(value >> shift));
    }
}

void append_i32(std::vector<std::uint8_t>& output, std::int32_t value) {
    append_u32(output, static_cast<std::uint32_t>(value));
}

void write_u16(
    std::vector<std::uint8_t>& output,
    std::size_t offset,
    std::uint16_t value
) {
    output[offset] = static_cast<std::uint8_t>(value);
    output[offset + 1U] = static_cast<std::uint8_t>(value >> 8U);
}

void write_u32(
    std::vector<std::uint8_t>& output,
    std::size_t offset,
    std::uint32_t value
) {
    for (unsigned int shift = 0U; shift < 32U; shift += 8U) {
        output[offset + shift / 8U] =
            static_cast<std::uint8_t>(value >> shift);
    }
}

void write_u64(
    std::vector<std::uint8_t>& output,
    std::size_t offset,
    std::uint64_t value
) {
    for (unsigned int shift = 0U; shift < 64U; shift += 8U) {
        output[offset + shift / 8U] =
            static_cast<std::uint8_t>(value >> shift);
    }
}

std::uint32_t crc32(const std::uint8_t* data, std::size_t size) {
    std::uint32_t crc = 0xFFFF'FFFFU;
    for (std::size_t index = 0U; index < size; ++index) {
        crc ^= data[index];
        for (unsigned int bit = 0U; bit < 8U; ++bit) {
            const std::uint32_t mask =
                static_cast<std::uint32_t>(
                    -static_cast<std::int32_t>(crc & 1U)
                );
            crc = (crc >> 1U) ^ (0xEDB8'8320U & mask);
        }
    }
    return ~crc;
}

void append_record(
    std::vector<std::uint8_t>& payload,
    std::uint8_t type,
    const std::vector<std::uint8_t>& body
) {
    payload.push_back(type);
    payload.push_back(1U);
    append_u16(payload, 0U);
    append_u32(payload, static_cast<std::uint32_t>(body.size()));
    payload.insert(payload.end(), body.begin(), body.end());
}

std::vector<std::uint8_t> build_reverse_stream() {
    std::vector<std::uint8_t> payload;

    std::vector<std::uint8_t> mix;
    append_u16(mix, 0U);
    append_u16(mix, 1U);
    append_u32(mix, 0U);
    append_u32(mix, 8U);
    append_u16(mix, 1U);
    append_u16(mix, 0U);
    append_u16(mix, 0U);
    append_i16(mix, 32767);
    append_record(payload, RESONITH_MAF_TYPED_MIX, mix);

    std::vector<std::uint8_t> basis;
    append_u16(basis, 0U);
    append_u16(basis, 4U);
    append_u32(basis, 0U);
    for (const std::int16_t value : std::array<std::int16_t, 4>{
             100,
             -200,
             300,
             -400,
         }) {
        append_i16(basis, value);
    }
    append_record(payload, RESONITH_MAF_TYPED_BASIS, basis);

    for (std::uint16_t id = 0U; id < 2U; ++id) {
        std::vector<std::uint8_t> instance;
        append_u16(instance, id);
        append_u16(instance, 0U);
        append_u16(instance, 0U);
        append_u16(
            instance,
            RESONITH_MAF_TYPED_BASIS_INSTANCE_REVERSE
                | (
                    id == 1U
                        ? static_cast<std::uint16_t>(
                              RESONITH_MAF_TYPED_BASIS_INSTANCE_CIRCULAR
                          )
                        : 0U
                )
        );
        append_u32(instance, id == 0U ? 0U : 4U);
        append_i32(instance, 32768);
        append_u16(instance, id == 0U ? 3U : 1U);
        append_u16(instance, 4U);
        append_i32(instance, 0);
        append_record(
            payload,
            RESONITH_MAF_TYPED_BASIS_INSTANCE,
            instance
        );
    }

    std::vector<std::uint8_t> stream(
        RESONITH_MAF_TYPED_HEADER_BYTES,
        0U
    );
    std::memcpy(stream.data(), "MFT1", 4U);
    stream[4] = 1U;
    write_u16(stream, 6U, RESONITH_MAF_TYPED_HEADER_BYTES);
    write_u32(stream, 8U, 48000U);
    write_u32(stream, 12U, 8U);
    write_u32(stream, 16U, 4U);
    write_u16(stream, 20U, 1U);
    write_u16(stream, 22U, 1U);
    write_u16(stream, 32U, 1U);
    write_u16(stream, 34U, 4U);
    write_u64(stream, 36U, 0x5245'534f'4e49'5448ULL);
    write_u32(stream, 44U, 128U);
    write_u32(stream, 48U, static_cast<std::uint32_t>(payload.size()));
    write_u32(stream, 52U, 40U);
    write_u32(stream, 56U, 26U);
    stream.insert(stream.end(), payload.begin(), payload.end());
    append_u32(stream, crc32(stream.data(), stream.size()));
    return stream;
}

}  // namespace

int main() {
    std::vector<std::uint8_t> stream = build_reverse_stream();
    orkela::decoded_audio audio{};
    std::string error;
    if (!orkela::decode_resonith_bytes(stream, &audio, &error)) {
        std::cerr << "Orkela MFT1 decode failed: " << error << '\n';
        return 1;
    }
    const std::array<std::int16_t, 8> expected{
        -400,
        300,
        -200,
        100,
        -200,
        100,
        -400,
        300,
    };
    if (
        audio.sample_rate != 48000U
        || audio.channels != 1U
        || audio.frame_count != expected.size()
        || audio.samples.size() != expected.size()
        || !std::equal(
            audio.samples.begin(),
            audio.samples.end(),
            expected.begin()
        )
    ) {
        std::cerr << "Orkela MFT1 reverse output mismatch\n";
        return 1;
    }

    stream.pop_back();
    if (orkela::decode_resonith_bytes(std::move(stream), &audio, &error)) {
        std::cerr << "Orkela accepted a truncated MFT1 stream\n";
        return 1;
    }
    std::cout << "Orkela MFT1 forward/reverse playback gate passed\n";
    return 0;
}
