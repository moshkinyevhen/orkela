#include "resonith_file.h"

#include "orkela/resonith_pull_decoder.h"

#include <cstddef>
#include <fstream>
#include <limits>
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
        // File ownership is platform-specific; bitstream validation and
        // decode policy live in the portable session library.
        std::vector<std::uint8_t> input = read_file(path);
        std::string portable_error;
        if (
            !decode_resonith_bytes(
                std::move(input),
                audio,
                &portable_error
            )
        ) {
            return fail(
                L"Cannot decode file: " + widen_ascii(portable_error.c_str()),
                error
            );
        }
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
