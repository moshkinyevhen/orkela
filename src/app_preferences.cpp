#include "app_preferences.h"

#include <algorithm>
#include <array>
#include <charconv>
#include <string>

#include <shlobj.h>
#include <windows.h>

namespace orkela {
namespace {

constexpr wchar_t section[] = L"Orkela";

std::filesystem::path preferences_path() {
    PWSTR local_app_data = nullptr;
    if (
        SHGetKnownFolderPath(
            FOLDERID_LocalAppData,
            KF_FLAG_CREATE,
            nullptr,
            &local_app_data
        ) != S_OK
        || local_app_data == nullptr
    ) {
        return {};
    }
    const std::filesystem::path directory =
        std::filesystem::path(local_app_data) / L"Orkela";
    CoTaskMemFree(local_app_data);
    std::error_code error;
    std::filesystem::create_directories(directory, error);
    return error ? std::filesystem::path{} : directory / L"settings.ini";
}

bool read_bool(
    const std::filesystem::path& path,
    const wchar_t* key,
    bool fallback
) {
    return GetPrivateProfileIntW(
        section,
        key,
        fallback ? 1 : 0,
        path.c_str()
    ) != 0;
}

std::uint32_t read_uint(
    const std::filesystem::path& path,
    const wchar_t* key,
    std::uint32_t fallback
) {
    return static_cast<std::uint32_t>(
        GetPrivateProfileIntW(
            section,
            key,
            static_cast<int>(fallback),
            path.c_str()
        )
    );
}

std::wstring read_text(
    const std::filesystem::path& path,
    const wchar_t* key
) {
    std::array<wchar_t, 32768U> value{};
    GetPrivateProfileStringW(
        section,
        key,
        L"",
        value.data(),
        static_cast<DWORD>(value.size()),
        path.c_str()
    );
    return value.data();
}

void write_text(
    const std::filesystem::path& path,
    const wchar_t* key,
    const std::wstring& value
) {
    WritePrivateProfileStringW(section, key, value.c_str(), path.c_str());
}

}  // namespace

app_preferences load_preferences() {
    app_preferences result;
    const std::filesystem::path path = preferences_path();
    if (path.empty()) {
        return result;
    }
    result.autoplay_on_open = read_bool(path, L"AutoplayOnOpen", false);
    result.resume_last_position =
        read_bool(path, L"ResumeLastPosition", true);
    result.loop_current_media = read_bool(path, L"LoopCurrentMedia", false);
    result.animate_visuals = read_bool(path, L"AnimateVisuals", true);
    result.show_spectrum = read_bool(path, L"ShowSpectrum", true);
    result.remember_volume = read_bool(path, L"RememberVolume", true);
    const std::uint32_t skip = read_uint(path, L"SkipSeconds", 10U);
    result.skip_seconds = skip == 5U || skip == 10U || skip == 30U
        ? skip
        : 10U;
    const std::uint32_t volume_percent = std::min(
        100U,
        read_uint(path, L"VolumePercent", 85U)
    );
    result.volume = static_cast<float>(volume_percent) / 100.0F;
    result.last_media = read_text(path, L"LastMedia");
    result.last_frame = read_uint(path, L"LastFrame", 0U);
    return result;
}

void save_preferences(const app_preferences& preferences) noexcept {
    try {
        const std::filesystem::path path = preferences_path();
        if (path.empty()) {
            return;
        }
        write_text(
            path,
            L"AutoplayOnOpen",
            preferences.autoplay_on_open ? L"1" : L"0"
        );
        write_text(
            path,
            L"ResumeLastPosition",
            preferences.resume_last_position ? L"1" : L"0"
        );
        write_text(
            path,
            L"LoopCurrentMedia",
            preferences.loop_current_media ? L"1" : L"0"
        );
        write_text(
            path,
            L"AnimateVisuals",
            preferences.animate_visuals ? L"1" : L"0"
        );
        write_text(
            path,
            L"ShowSpectrum",
            preferences.show_spectrum ? L"1" : L"0"
        );
        write_text(
            path,
            L"RememberVolume",
            preferences.remember_volume ? L"1" : L"0"
        );
        write_text(
            path,
            L"SkipSeconds",
            std::to_wstring(preferences.skip_seconds)
        );
        const auto volume_percent = static_cast<std::uint32_t>(
            std::clamp(preferences.volume, 0.0F, 1.0F) * 100.0F + 0.5F
        );
        write_text(path, L"VolumePercent", std::to_wstring(volume_percent));
        write_text(path, L"LastMedia", preferences.last_media.wstring());
        write_text(path, L"LastFrame", std::to_wstring(preferences.last_frame));
    } catch (...) {
        // Preferences are non-critical; codec playback must remain available
        // when the profile directory is unavailable or malformed.
    }
}

void reset_preferences() noexcept {
    try {
        const std::filesystem::path path = preferences_path();
        if (!path.empty()) {
            std::error_code error;
            std::filesystem::remove(path, error);
        }
    } catch (...) {
    }
}

}  // namespace orkela
