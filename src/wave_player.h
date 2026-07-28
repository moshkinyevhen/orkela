#ifndef ORKELA_WAVE_PLAYER_H
#define ORKELA_WAVE_PLAYER_H

#include "resonith_file.h"

#include <atomic>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <span>
#include <string>
#include <thread>
#include <vector>

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
    std::size_t copy_visual_snapshot(
        std::span<std::int16_t> destination,
        std::uint32_t* logical_start,
        std::uint16_t* channels
    ) const noexcept;

private:
    [[nodiscard]] std::wstring run_streamed(
        const decoded_audio& audio,
        std::uint32_t start_frame
    ) noexcept;
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
    mutable std::mutex visual_mutex_;
    std::vector<std::int16_t> visual_samples_;
    std::size_t visual_elements_ = 0U;
    std::uint32_t visual_start_frame_ = 0U;
    std::uint16_t visual_channels_ = 0U;
    HWAVEOUT device_ = nullptr;
    std::jthread worker_;
};

}  // namespace orkela

#endif
