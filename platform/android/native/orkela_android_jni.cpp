#include "orkela/localization.h"
#include "orkela/resonith_pull_decoder.h"

#include <jni.h>

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <limits>
#include <memory>
#include <string>
#include <utility>
#include <vector>

namespace {

constexpr std::size_t maximum_java_input_bytes = 64ULL * 1024ULL * 1024ULL;

struct android_decoder {
    std::unique_ptr<orkela::resonith_pull_decoder> decoder;
    std::vector<std::int16_t> packet;
    std::string last_error;
};

android_decoder* from_handle(jlong handle) noexcept {
    return reinterpret_cast<android_decoder*>(
        static_cast<std::uintptr_t>(handle)
    );
}

jlong to_handle(android_decoder* decoder) noexcept {
    return static_cast<jlong>(
        reinterpret_cast<std::uintptr_t>(decoder)
    );
}

void throw_java(
    JNIEnv* environment,
    const char* type,
    const std::string& message
) noexcept {
    jclass exception_class = environment->FindClass(type);
    if (exception_class != nullptr) {
        environment->ThrowNew(exception_class, message.c_str());
    }
}

android_decoder* require_decoder(
    JNIEnv* environment,
    jlong handle
) noexcept {
    android_decoder* state = from_handle(handle);
    if (state == nullptr || state->decoder == nullptr) {
        throw_java(
            environment,
            "java/lang/IllegalStateException",
            "Resonith decoder is not open"
        );
        return nullptr;
    }
    return state;
}

}  // namespace

extern "C" JNIEXPORT jlong JNICALL
Java_org_scenelith_orkela_MainActivity_nativeOpen(
    JNIEnv* environment,
    jclass,
    jbyteArray input
) {
    if (input == nullptr) {
        throw_java(
            environment,
            "java/lang/IllegalArgumentException",
            "Input is null"
        );
        return 0;
    }
    const jsize java_size = environment->GetArrayLength(input);
    if (java_size <= 0) {
        throw_java(
            environment,
            "java/lang/IllegalArgumentException",
            "Input is empty"
        );
        return 0;
    }
    const auto byte_count = static_cast<std::size_t>(java_size);
    if (byte_count > maximum_java_input_bytes) {
        throw_java(
            environment,
            "java/lang/IllegalArgumentException",
            "Mobile alpha input exceeds 64 MiB"
        );
        return 0;
    }

    try {
        std::vector<std::uint8_t> bytes(byte_count);
        environment->GetByteArrayRegion(
            input,
            0,
            java_size,
            reinterpret_cast<jbyte*>(bytes.data())
        );
        if (environment->ExceptionCheck() == JNI_TRUE) {
            return 0;
        }

        std::string error;
        auto decoder =
            orkela::resonith_pull_decoder::open(std::move(bytes), &error);
        if (decoder == nullptr) {
            throw_java(environment, "java/io/IOException", error);
            return 0;
        }

        auto state = std::make_unique<android_decoder>();
        const std::size_t packet_elements =
            decoder->info().maximum_packet_elements;
        state->packet.resize(std::max<std::size_t>(1U, packet_elements));
        state->decoder = std::move(decoder);
        return to_handle(state.release());
    } catch (const std::exception& exception) {
        throw_java(
            environment,
            "java/lang/RuntimeException",
            exception.what()
        );
        return 0;
    }
}

extern "C" JNIEXPORT jint JNICALL
Java_org_scenelith_orkela_MainActivity_nativeSampleRate(
    JNIEnv* environment,
    jclass,
    jlong handle
) {
    const android_decoder* state = require_decoder(environment, handle);
    return state == nullptr
        ? 0
        : static_cast<jint>(state->decoder->info().sample_rate);
}

extern "C" JNIEXPORT jint JNICALL
Java_org_scenelith_orkela_MainActivity_nativeChannels(
    JNIEnv* environment,
    jclass,
    jlong handle
) {
    const android_decoder* state = require_decoder(environment, handle);
    return state == nullptr
        ? 0
        : static_cast<jint>(state->decoder->info().channels);
}

extern "C" JNIEXPORT jint JNICALL
Java_org_scenelith_orkela_MainActivity_nativeFrameCount(
    JNIEnv* environment,
    jclass,
    jlong handle
) {
    const android_decoder* state = require_decoder(environment, handle);
    if (state == nullptr) {
        return 0;
    }
    const std::uint32_t frame_count = state->decoder->info().frame_count;
    if (
        frame_count
        > static_cast<std::uint32_t>(std::numeric_limits<jint>::max())
    ) {
        throw_java(
            environment,
            "java/lang/ArithmeticException",
            "Frame count exceeds Java integer range"
        );
        return 0;
    }
    return static_cast<jint>(frame_count);
}

extern "C" JNIEXPORT jint JNICALL
Java_org_scenelith_orkela_MainActivity_nativePacketElements(
    JNIEnv* environment,
    jclass,
    jlong handle
) {
    const android_decoder* state = require_decoder(environment, handle);
    if (state == nullptr) {
        return 0;
    }
    const std::size_t count =
        state->decoder->info().maximum_packet_elements;
    if (count > static_cast<std::size_t>(std::numeric_limits<jint>::max())) {
        throw_java(
            environment,
            "java/lang/ArithmeticException",
            "Packet bound exceeds Java integer range"
        );
        return 0;
    }
    return static_cast<jint>(count);
}

extern "C" JNIEXPORT jint JNICALL
Java_org_scenelith_orkela_MainActivity_nativeRead(
    JNIEnv* environment,
    jclass,
    jlong handle,
    jshortArray output
) {
    android_decoder* state = require_decoder(environment, handle);
    if (state == nullptr || output == nullptr) {
        return -1;
    }
    const jsize output_size = environment->GetArrayLength(output);
    if (
        output_size <= 0
        || static_cast<std::size_t>(output_size) < state->packet.size()
    ) {
        throw_java(
            environment,
            "java/lang/IllegalArgumentException",
            "PCM array is smaller than the authenticated packet bound"
        );
        return -1;
    }

    std::uint32_t logical_start = 0U;
    std::size_t frames_written = 0U;
    orkela::pull_result result = orkela::pull_result::error;
    try {
        result = state->decoder->read_next(
            state->packet,
            &logical_start,
            &frames_written,
            &state->last_error
        );
    } catch (const std::exception& exception) {
        throw_java(
            environment,
            "java/lang/RuntimeException",
            exception.what()
        );
        return -1;
    }
    if (result == orkela::pull_result::end) {
        return 0;
    }
    if (result == orkela::pull_result::error) {
        throw_java(
            environment,
            "java/io/IOException",
            state->last_error
        );
        return -1;
    }

    const std::size_t element_count =
        frames_written * state->decoder->info().channels;
    if (
        element_count
        > static_cast<std::size_t>(std::numeric_limits<jsize>::max())
    ) {
        throw_java(
            environment,
            "java/lang/ArithmeticException",
            "Decoded packet exceeds Java array range"
        );
        return -1;
    }
    environment->SetShortArrayRegion(
        output,
        0,
        static_cast<jsize>(element_count),
        reinterpret_cast<const jshort*>(state->packet.data())
    );
    if (environment->ExceptionCheck() == JNI_TRUE) {
        return -1;
    }
    return static_cast<jint>(element_count);
}

extern "C" JNIEXPORT void JNICALL
Java_org_scenelith_orkela_MainActivity_nativeClose(
    JNIEnv*,
    jclass,
    jlong handle
) {
    delete from_handle(handle);
}

extern "C" JNIEXPORT jstring JNICALL
Java_org_scenelith_orkela_MainActivity_nativeText(
    JNIEnv* environment,
    jclass,
    jstring locale_tag,
    jint text_identifier
) {
    if (
        locale_tag == nullptr
        || text_identifier < 0
        || text_identifier
            >= static_cast<jint>(orkela::text_id::count)
    ) {
        throw_java(
            environment,
            "java/lang/IllegalArgumentException",
            "Invalid localization request"
        );
        return nullptr;
    }
    const char* locale = environment->GetStringUTFChars(
        locale_tag,
        nullptr
    );
    if (locale == nullptr) {
        return nullptr;
    }
    const orkela::language selected =
        orkela::language_from_tag(locale);
    environment->ReleaseStringUTFChars(locale_tag, locale);
    const std::string_view translated = orkela::localized_text(
        selected,
        static_cast<orkela::text_id>(text_identifier)
    );
    return environment->NewStringUTF(
        std::string(translated).c_str()
    );
}
