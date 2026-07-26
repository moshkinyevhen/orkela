#ifndef ORKELA_WAVE_PLAYER_H
#define ORKELA_WAVE_PLAYER_H

#include "resonith_file.h"

#include <atomic>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <thread>

#include <windows.h>
#include <mmsystem.h>

namespace orkela {

class wave_player {
public:
    using completion = std::function<void(std::wstring)>;

    wave_player() = default;
    wave_player(const wave_player&) = delete;
    wave_player& operator=(const wave_player&) = delete;
    ~wave_player();

    void play(
        std::shared_ptr<const decoded_audio> audio,
        std::uint32_t start_frame,
        completion callback
    );
    void stop() noexcept;
    void pause() noexcept;
    void resume() noexcept;
    void set_volume(float volume) noexcept;
    [[nodiscard]] bool is_playing() const noexcept;
    [[nodiscard]] bool is_paused() const noexcept;
    [[nodiscard]] std::uint32_t position_frame() const noexcept;

private:
    void run(
        std::shared_ptr<const decoded_audio> audio,
        std::uint32_t start_frame,
        completion callback
    ) noexcept;

    std::atomic_bool stop_requested_{false};
    std::atomic_bool playing_{false};
    std::atomic_bool paused_{false};
    std::atomic_uint32_t position_frame_{0U};
    std::atomic<float> volume_{0.85F};
    std::mutex device_mutex_;
    HWAVEOUT device_ = nullptr;
    std::jthread worker_;
};

}  // namespace orkela

#endif
