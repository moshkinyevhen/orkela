#ifndef ORKELA_APP_PREFERENCES_H
#define ORKELA_APP_PREFERENCES_H

#include <cstdint>
#include <filesystem>

namespace orkela {

// User-facing preferences remain separate from codec Truth state. They may
// change presentation and session behavior but never alter decoded PCM.
struct app_preferences {
    bool autoplay_on_open = false;
    bool resume_last_position = true;
    bool loop_current_media = false;
    bool animate_visuals = true;
    bool show_spectrum = true;
    bool remember_volume = true;
    std::uint32_t skip_seconds = 10U;
    float volume = 0.85F;
    std::filesystem::path last_media;
    std::uint32_t last_frame = 0U;
};

[[nodiscard]] app_preferences load_preferences();
void save_preferences(const app_preferences& preferences) noexcept;
void reset_preferences() noexcept;

}  // namespace orkela

#endif
