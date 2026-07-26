#include "wave_player.h"

#include <chrono>
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
    completion callback
) {
    stop();
    stop_requested_.store(false);
    playing_.store(true);
    worker_ = std::jthread(
        [this, audio = std::move(audio), callback = std::move(callback)] {
            run(audio, callback);
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
    playing_.store(false);
}

bool wave_player::is_playing() const noexcept {
    return playing_.load();
}

void wave_player::run(
    std::shared_ptr<const decoded_audio> audio,
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
    ) {
        result = L"No decoded audio is available.";
    } else if (
        audio->samples.size()
            > std::numeric_limits<DWORD>::max() / sizeof(std::int16_t)
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
            }

            header.lpData = reinterpret_cast<LPSTR>(
                const_cast<std::int16_t*>(audio->samples.data())
            );
            header.dwBufferLength = static_cast<DWORD>(
                audio->samples.size() * sizeof(std::int16_t)
            );
            status = waveOutPrepareHeader(
                local_device,
                &header,
                sizeof(header)
            );
            if (status != MMSYSERR_NOERROR) {
                result =
                    L"Cannot prepare playback buffer: " + wave_error(status);
            } else {
                prepared = true;
                status = waveOutWrite(local_device, &header, sizeof(header));
                if (status != MMSYSERR_NOERROR) {
                    result =
                        L"Cannot start playback: " + wave_error(status);
                } else {
                    while (
                        (header.dwFlags & WHDR_DONE) == 0U
                        && !stop_requested_.load()
                    ) {
                        std::this_thread::sleep_for(
                            std::chrono::milliseconds(10)
                        );
                    }
                    result = stop_requested_.load()
                        ? L"Playback stopped."
                        : L"Playback complete.";
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
    if (callback) {
        callback(std::move(result));
    }
}

}  // namespace orkela
