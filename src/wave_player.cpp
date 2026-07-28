#include "wave_player.h"

#include "orkela/resonith_pull_decoder.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstring>
#include <limits>
#include <span>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace orkela {
namespace {

std::wstring wave_error(MMRESULT result) {
    wchar_t buffer[MAXERRORLENGTH]{};
    if (
        waveOutGetErrorTextW(result, buffer, MAXERRORLENGTH)
        == MMSYSERR_NOERROR
    ) {
        return buffer;
    }
    return L"Windows audio error " + std::to_wstring(result);
}

std::wstring widen_ascii(const std::string& text) {
    std::wstring result;
    result.reserve(text.size());
    for (const char character : text) {
        result.push_back(static_cast<wchar_t>(
            static_cast<unsigned char>(character)
        ));
    }
    return result;
}

struct playback_buffer {
    std::vector<std::int16_t> samples;
    WAVEHDR header{};
    std::uint32_t logical_start = 0U;
    std::uint32_t frame_count = 0U;
    bool prepared = false;
    bool submitted = false;
};

}  // namespace

wave_player::~wave_player() {
    stop();
}

void wave_player::play(
    std::shared_ptr<const decoded_audio> audio,
    std::uint32_t start_frame,
    completion callback
) {
    stop();
    stop_requested_.store(false);
    paused_.store(false);
    position_frame_.store(start_frame);
    playing_.store(true);
    {
        std::scoped_lock lock(visual_mutex_);
        const std::size_t channels =
            audio == nullptr ? 0U : audio->channels;
        visual_samples_.assign(4096U * channels, 0);
        visual_elements_ = 0U;
        visual_start_frame_ = start_frame;
        visual_channels_ = audio == nullptr ? 0U : audio->channels;
    }
    worker_ = std::jthread(
        [
            this,
            audio = std::move(audio),
            start_frame,
            callback = std::move(callback)
        ] {
            run(audio, start_frame, callback);
        }
    );
}

void wave_player::stop() noexcept {
    stop_requested_.store(true);
    {
        std::scoped_lock lock(device_mutex_);
        if (device_ != nullptr) {
            waveOutReset(device_);
        }
    }
    if (worker_.joinable()) {
        worker_.join();
    }
    paused_.store(false);
    playing_.store(false);
}

void wave_player::pause() noexcept {
    std::scoped_lock lock(device_mutex_);
    if (
        device_ != nullptr
        && waveOutPause(device_) == MMSYSERR_NOERROR
    ) {
        paused_.store(true);
    }
}

void wave_player::resume() noexcept {
    std::scoped_lock lock(device_mutex_);
    if (
        device_ != nullptr
        && waveOutRestart(device_) == MMSYSERR_NOERROR
    ) {
        paused_.store(false);
    }
}

void wave_player::set_volume(float volume) noexcept {
    const float bounded = std::clamp(volume, 0.0F, 1.0F);
    volume_.store(bounded);
    const auto level = static_cast<DWORD>(
        std::lround(static_cast<double>(bounded) * 65535.0)
    );
    const DWORD stereo = level | (level << 16U);
    std::scoped_lock lock(device_mutex_);
    if (device_ != nullptr) {
        waveOutSetVolume(device_, stereo);
    }
}

bool wave_player::is_playing() const noexcept {
    return playing_.load();
}

bool wave_player::is_paused() const noexcept {
    return paused_.load();
}

std::uint32_t wave_player::position_frame() const noexcept {
    return position_frame_.load();
}

std::size_t wave_player::copy_visual_snapshot(
    std::span<std::int16_t> destination,
    std::uint32_t* logical_start,
    std::uint16_t* channels
) const noexcept {
    if (logical_start == nullptr || channels == nullptr) {
        return 0U;
    }
    std::scoped_lock lock(visual_mutex_);
    const std::size_t count = std::min(
        destination.size(),
        visual_elements_
    );
    if (count != 0U) {
        std::copy_n(visual_samples_.data(), count, destination.data());
    }
    *logical_start = visual_start_frame_;
    *channels = visual_channels_;
    return count;
}

std::wstring wave_player::run_streamed(
    const decoded_audio& audio,
    std::uint32_t start_frame
) noexcept {
    constexpr std::size_t queue_buffer_count = 4U;
    constexpr std::uint32_t queue_frames = 4096U;

    if (
        audio.source_bytes == nullptr
        || audio.source_bytes->empty()
        || audio.channels == 0U
        || audio.sample_rate == 0U
        || start_frame >= audio.frame_count
    ) {
        return L"No authenticated streaming source is available.";
    }

    try {
        std::string decoder_error;
        auto decoder = resonith_pull_decoder::open(
            *audio.source_bytes,
            &decoder_error
        );
        if (decoder == nullptr) {
            return L"Cannot open Resonith stream: "
                + widen_ascii(decoder_error);
        }
        const resonith_stream_info info = decoder->info();
        if (
            info.sample_rate != audio.sample_rate
            || info.channels != audio.channels
            || info.frame_count != audio.frame_count
        ) {
            return L"Resonith preflight changed between load and playback.";
        }

        WAVEFORMATEX format{};
        format.wFormatTag = WAVE_FORMAT_PCM;
        format.nChannels = info.channels;
        format.nSamplesPerSec = info.sample_rate;
        format.wBitsPerSample = 16U;
        format.nBlockAlign = static_cast<WORD>(
            format.nChannels * (format.wBitsPerSample / 8U)
        );
        format.nAvgBytesPerSec =
            format.nSamplesPerSec * format.nBlockAlign;

        HWAVEOUT local_device = nullptr;
        MMRESULT status = waveOutOpen(
            &local_device,
            WAVE_MAPPER,
            &format,
            0U,
            0U,
            CALLBACK_NULL
        );
        if (status != MMSYSERR_NOERROR) {
            return L"Cannot open Windows audio: " + wave_error(status);
        }

        {
            std::scoped_lock lock(device_mutex_);
            device_ = local_device;
            const auto level = static_cast<DWORD>(
                std::lround(
                    static_cast<double>(
                        std::clamp(volume_.load(), 0.0F, 1.0F)
                    ) * 65535.0
                )
            );
            waveOutSetVolume(local_device, level | (level << 16U));
        }

        std::vector<std::int16_t> decoded_packet(
            std::max<std::size_t>(1U, info.maximum_packet_elements)
        );
        std::uint32_t packet_start = 0U;
        std::size_t packet_frames = 0U;
        std::size_t packet_offset = 0U;
        bool decoder_finished = false;
        std::uint32_t next_frame = start_frame;

        std::array<playback_buffer, queue_buffer_count> buffers{};
        const std::size_t buffer_elements =
            static_cast<std::size_t>(queue_frames) * info.channels;
        for (auto& buffer : buffers) {
            buffer.samples.resize(buffer_elements);
        }

        auto fill_buffer = [&](playback_buffer& buffer) -> bool {
            while (
                !decoder_finished
                && (
                    packet_offset >= packet_frames
                    || packet_start + packet_offset < next_frame
                )
            ) {
                std::uint32_t logical_start = 0U;
                std::size_t frames_written = 0U;
                const pull_result result = decoder->read_next(
                    decoded_packet,
                    &logical_start,
                    &frames_written,
                    &decoder_error
                );
                if (result == pull_result::error) {
                    throw std::runtime_error(decoder_error);
                }
                if (result == pull_result::end) {
                    decoder_finished = true;
                    break;
                }
                packet_start = logical_start;
                packet_frames = frames_written;
                packet_offset = next_frame > packet_start
                    ? std::min<std::size_t>(
                        next_frame - packet_start,
                        packet_frames
                    )
                    : 0U;
            }
            if (decoder_finished && packet_offset >= packet_frames) {
                return false;
            }

            const std::size_t available = packet_frames - packet_offset;
            const std::size_t frames = std::min<std::size_t>(
                queue_frames,
                available
            );
            const std::size_t elements =
                frames * static_cast<std::size_t>(info.channels);
            const std::size_t source_element =
                packet_offset * static_cast<std::size_t>(info.channels);
            std::copy_n(
                decoded_packet.data() + source_element,
                elements,
                buffer.samples.data()
            );
            buffer.logical_start = next_frame;
            buffer.frame_count = static_cast<std::uint32_t>(frames);
            packet_offset += frames;
            next_frame += static_cast<std::uint32_t>(frames);

            buffer.header = {};
            buffer.header.lpData = reinterpret_cast<LPSTR>(
                buffer.samples.data()
            );
            buffer.header.dwBufferLength = static_cast<DWORD>(
                elements * sizeof(std::int16_t)
            );
            return true;
        };

        auto submit_buffer = [&](playback_buffer& buffer) {
            status = waveOutPrepareHeader(
                local_device,
                &buffer.header,
                sizeof(buffer.header)
            );
            if (status != MMSYSERR_NOERROR) {
                throw std::runtime_error("cannot prepare playback buffer");
            }
            buffer.prepared = true;
            status = waveOutWrite(
                local_device,
                &buffer.header,
                sizeof(buffer.header)
            );
            if (status != MMSYSERR_NOERROR) {
                throw std::runtime_error("cannot submit playback buffer");
            }
            buffer.submitted = true;
        };

        std::size_t active_buffers = 0U;
        for (auto& buffer : buffers) {
            if (!fill_buffer(buffer)) {
                break;
            }
            submit_buffer(buffer);
            ++active_buffers;
        }

        auto publish_visual = [&](const playback_buffer& buffer) {
            const std::size_t elements =
                static_cast<std::size_t>(buffer.frame_count) * info.channels;
            // This mutex is observed only by the UI timer. waveOut owns no
            // callback into this code, so the audio device thread never
            // allocates, locks, or touches visualization state.
            std::scoped_lock lock(visual_mutex_);
            std::copy_n(
                buffer.samples.data(),
                elements,
                visual_samples_.data()
            );
            visual_elements_ = elements;
            visual_start_frame_ = buffer.logical_start;
            visual_channels_ = info.channels;
        };
        if (active_buffers != 0U) {
            publish_visual(buffers.front());
        }

        std::wstring result;
        while (
            active_buffers != 0U
            && !stop_requested_.load()
        ) {
            MMTIME position{};
            position.wType = TIME_SAMPLES;
            if (
                waveOutGetPosition(
                    local_device,
                    &position,
                    sizeof(position)
                ) == MMSYSERR_NOERROR
            ) {
                std::uint64_t relative = 0U;
                if (position.wType == TIME_SAMPLES) {
                    relative = position.u.sample;
                } else if (position.wType == TIME_BYTES) {
                    relative = position.u.cb / format.nBlockAlign;
                } else if (position.wType == TIME_MS) {
                    relative =
                        static_cast<std::uint64_t>(position.u.ms)
                        * info.sample_rate / 1000U;
                }
                position_frame_.store(
                    static_cast<std::uint32_t>(
                        std::min<std::uint64_t>(
                            static_cast<std::uint64_t>(start_frame)
                                + relative,
                            info.frame_count
                        )
                    )
                );
            }
            const std::uint32_t visible_frame = position_frame_.load();
            for (const auto& buffer : buffers) {
                if (
                    buffer.submitted
                    && visible_frame >= buffer.logical_start
                    && visible_frame
                        < buffer.logical_start + buffer.frame_count
                ) {
                    publish_visual(buffer);
                    break;
                }
            }

            for (auto& buffer : buffers) {
                if (
                    !buffer.submitted
                    || (buffer.header.dwFlags & WHDR_DONE) == 0U
                ) {
                    continue;
                }
                waveOutUnprepareHeader(
                    local_device,
                    &buffer.header,
                    sizeof(buffer.header)
                );
                buffer.prepared = false;
                buffer.submitted = false;
                --active_buffers;
                if (!decoder_finished || packet_offset < packet_frames) {
                    if (fill_buffer(buffer)) {
                        submit_buffer(buffer);
                        ++active_buffers;
                    }
                }
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(2));
        }

        if (stop_requested_.load()) {
            waveOutReset(local_device);
            result = L"Playback stopped.";
        } else {
            position_frame_.store(info.frame_count);
            result = L"Playback complete.";
        }
        for (auto& buffer : buffers) {
            if (buffer.prepared) {
                waveOutUnprepareHeader(
                    local_device,
                    &buffer.header,
                    sizeof(buffer.header)
                );
            }
        }
        {
            std::scoped_lock lock(device_mutex_);
            if (device_ == local_device) {
                device_ = nullptr;
            }
        }
        waveOutClose(local_device);
        return result;
    } catch (const std::exception& exception) {
        std::scoped_lock lock(device_mutex_);
        if (device_ != nullptr) {
            waveOutReset(device_);
            waveOutClose(device_);
            device_ = nullptr;
        }
        return L"Streaming playback failed: "
            + widen_ascii(exception.what());
    }
}

void wave_player::run(
    std::shared_ptr<const decoded_audio> audio,
    std::uint32_t start_frame,
    completion callback
) noexcept {
    if (audio != nullptr && audio->source_bytes != nullptr) {
        std::wstring result = run_streamed(*audio, start_frame);
        playing_.store(false);
        paused_.store(false);
        if (callback) {
            callback(std::move(result));
        }
        return;
    }

    std::wstring result;
    HWAVEOUT local_device = nullptr;
    WAVEHDR header{};
    bool prepared = false;

    if (
        audio == nullptr
        || audio->samples.empty()
        || audio->channels == 0U
        || audio->sample_rate == 0U
        || start_frame >= audio->frame_count
    ) {
        result = L"No decoded audio is available.";
    } else {
        const std::size_t start_element =
            static_cast<std::size_t>(start_frame) * audio->channels;
        const std::size_t remaining_elements =
            audio->samples.size() - start_element;
        if (
            remaining_elements
                > std::numeric_limits<DWORD>::max()
                    / sizeof(std::int16_t)
        ) {
            result = L"Clip is too large for this playback milestone.";
        } else {
            WAVEFORMATEX format{};
            format.wFormatTag = WAVE_FORMAT_PCM;
            format.nChannels = audio->channels;
            format.nSamplesPerSec = audio->sample_rate;
            format.wBitsPerSample = 16U;
            format.nBlockAlign = static_cast<WORD>(
                format.nChannels * (format.wBitsPerSample / 8U)
            );
            format.nAvgBytesPerSec =
                format.nSamplesPerSec * format.nBlockAlign;
            format.cbSize = 0U;

            MMRESULT status = waveOutOpen(
                &local_device,
                WAVE_MAPPER,
                &format,
                0U,
                0U,
                CALLBACK_NULL
            );
            if (status != MMSYSERR_NOERROR) {
                result = L"Cannot open Windows audio: " + wave_error(status);
            } else {
                {
                    std::scoped_lock lock(device_mutex_);
                    device_ = local_device;
                    const float bounded = std::clamp(
                        volume_.load(),
                        0.0F,
                        1.0F
                    );
                    const auto level = static_cast<DWORD>(
                        std::lround(
                            static_cast<double>(bounded) * 65535.0
                        )
                    );
                    waveOutSetVolume(
                        local_device,
                        level | (level << 16U)
                    );
                }

                header.lpData = reinterpret_cast<LPSTR>(
                    const_cast<std::int16_t*>(
                        audio->samples.data() + start_element
                    )
                );
                header.dwBufferLength = static_cast<DWORD>(
                    remaining_elements * sizeof(std::int16_t)
                );
                status = waveOutPrepareHeader(
                    local_device,
                    &header,
                    sizeof(header)
                );
                if (status != MMSYSERR_NOERROR) {
                    result =
                        L"Cannot prepare playback buffer: "
                        + wave_error(status);
                } else {
                    prepared = true;
                    status = waveOutWrite(
                        local_device,
                        &header,
                        sizeof(header)
                    );
                    if (status != MMSYSERR_NOERROR) {
                        result =
                            L"Cannot start playback: "
                            + wave_error(status);
                    } else {
                        while (
                            (header.dwFlags & WHDR_DONE) == 0U
                            && !stop_requested_.load()
                        ) {
                            MMTIME position{};
                            position.wType = TIME_SAMPLES;
                            if (
                                waveOutGetPosition(
                                    local_device,
                                    &position,
                                    sizeof(position)
                                ) == MMSYSERR_NOERROR
                            ) {
                                std::uint64_t relative = 0U;
                                if (position.wType == TIME_SAMPLES) {
                                    relative = position.u.sample;
                                } else if (position.wType == TIME_BYTES) {
                                    relative =
                                        position.u.cb / format.nBlockAlign;
                                } else if (position.wType == TIME_MS) {
                                    relative =
                                        static_cast<std::uint64_t>(
                                            position.u.ms
                                        )
                                        * audio->sample_rate / 1000U;
                                }
                                const std::uint64_t absolute =
                                    static_cast<std::uint64_t>(start_frame)
                                    + relative;
                                position_frame_.store(
                                    static_cast<std::uint32_t>(
                                        std::min<std::uint64_t>(
                                            absolute,
                                            audio->frame_count
                                        )
                                    )
                                );
                            }
                            std::this_thread::sleep_for(
                                std::chrono::milliseconds(10)
                            );
                        }
                        if (!stop_requested_.load()) {
                            position_frame_.store(audio->frame_count);
                        }
                        result = stop_requested_.load()
                            ? L"Playback stopped."
                            : L"Playback complete.";
                    }
                }
            }
        }
    }

    if (local_device != nullptr) {
        if (prepared) {
            waveOutUnprepareHeader(local_device, &header, sizeof(header));
        }
        {
            std::scoped_lock lock(device_mutex_);
            if (device_ == local_device) {
                device_ = nullptr;
            }
        }
        waveOutClose(local_device);
    }

    playing_.store(false);
    paused_.store(false);
    if (callback) {
        callback(std::move(result));
    }
}

}  // namespace orkela
