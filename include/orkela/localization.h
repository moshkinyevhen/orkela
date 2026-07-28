#pragma once

#include <cstddef>
#include <cstdint>
#include <string_view>

namespace orkela {

enum class language : std::uint8_t {
    english,
    german,
    spanish,
    italian,
    japanese,
    korean,
    chinese_simplified,
    russian,
    ukrainian,
};

enum class text_id : std::uint8_t {
    app_name,
    tagline,
    local_private,
    now_playing,
    native_resonith,
    portable_session,
    resonith,
    causal_field,
    decoded_truth,
    visual_hint,
    ready,
    playing,
    paused,
    playback_complete,
    stopped,
    authenticating,
    seeking,
    listening,
    volume,
    repeat_off,
    repeat_on,
    source,
    open_resonith,
    load_demo,
    settings,
    interface_settings,
    language,
    language_description,
    system_default,
    done,
    field,
    spectrum,
    wave,
    history,
    privacy_detail,
    source_footer,
    playback_failed,
    overview,
    playback,
    audio,
    visuals,
    video,
    subtitles,
    library,
    performance,
    privacy,
    hotkeys,
    advanced,
    command_center,
    play_action,
    pause_action,
    resume_action,
    stop_action,
    back_ten_action,
    forward_ten_action,
    playback_timeline,
    playback_information,
    count,
};

[[nodiscard]] language language_from_tag(std::string_view tag) noexcept;
[[nodiscard]] std::string_view language_tag(language value) noexcept;
[[nodiscard]] std::string_view language_autonym(language value) noexcept;
[[nodiscard]] std::string_view localized_text(
    language selected,
    text_id id
) noexcept;

inline constexpr std::size_t supported_language_count = 9U;

}  // namespace orkela
