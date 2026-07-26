#include "wave_player.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <limits>
#include <utility>

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

void wave_player::run(
    std::shared_ptr<const decoded_audio> audio,
    std::uint32_t start_frame,
    completion callback
) noexcept {
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
