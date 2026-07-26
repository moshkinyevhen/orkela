#include "resonith_file.h"
#include "wave_player.h"

#include <commdlg.h>
#include <shellapi.h>
#include <windows.h>

#include <array>
#include <atomic>
#include <filesystem>
#include <iomanip>
#include <memory>
#include <sstream>
#include <string>

namespace {

constexpr int open_button_id = 1001;
constexpr int play_button_id = 1002;
constexpr int stop_button_id = 1003;
constexpr UINT playback_done_message = WM_APP + 1U;

struct app_state {
    HWND window = nullptr;
    HWND path_label = nullptr;
    HWND details_label = nullptr;
    HWND status_label = nullptr;
    HWND play_button = nullptr;
    HWND stop_button = nullptr;
    std::filesystem::path path;
    std::shared_ptr<const orkela::decoded_audio> audio;
    orkela::wave_player player;
    std::atomic_bool closing{false};
};

void set_text(HWND control, const std::wstring& text) {
    SetWindowTextW(control, text.c_str());
}

std::wstring format_details(const orkela::decoded_audio& audio) {
    const double seconds = static_cast<double>(audio.frame_count)
        / static_cast<double>(audio.sample_rate);
    std::wostringstream output;
    output << audio.sample_rate << L" Hz  |  " << audio.channels
           << (audio.channels == 1U ? L" channel" : L" channels")
           << L"  |  " << std::fixed << std::setprecision(2) << seconds
           << L" s  |  decoded by Resonith Core";
    return output.str();
}

void stop_playback(app_state* state) {
    if (state == nullptr) {
        return;
    }
    state->player.stop();
    EnableWindow(state->play_button, state->audio != nullptr);
    EnableWindow(state->stop_button, FALSE);
}

void load_file(app_state* state, const std::filesystem::path& path) {
    if (state == nullptr || path.empty()) {
        return;
    }
    stop_playback(state);
    set_text(state->status_label, L"Validating and decoding Resonith LPS5...");
    UpdateWindow(state->window);

    auto decoded = std::make_shared<orkela::decoded_audio>();
    std::wstring error;
    if (!orkela::decode_resonith_file(path, decoded.get(), &error)) {
        state->audio.reset();
        state->path.clear();
        set_text(state->path_label, L"No Resonith file loaded");
        set_text(state->details_label, L"");
        set_text(state->status_label, error);
        EnableWindow(state->play_button, FALSE);
        return;
    }

    state->path = path;
    state->audio = std::move(decoded);
    set_text(state->path_label, state->path.filename().wstring());
    set_text(state->details_label, format_details(*state->audio));
    set_text(
        state->status_label,
        L"Ready. Press Play to hear the native Resonith reconstruction."
    );
    EnableWindow(state->play_button, TRUE);
}

void choose_file(app_state* state) {
    std::array<wchar_t, 32768> buffer{};
    OPENFILENAMEW dialog{};
    dialog.lStructSize = sizeof(dialog);
    dialog.hwndOwner = state->window;
    dialog.lpstrFilter =
        L"Resonith LPS files (*.lps5;*.lps4)\0*.lps5;*.lps4\0"
        L"All files (*.*)\0*.*\0";
    dialog.lpstrFile = buffer.data();
    dialog.nMaxFile = static_cast<DWORD>(buffer.size());
    dialog.lpstrTitle = L"Open a Resonith file";
    dialog.Flags =
        OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR;
    if (GetOpenFileNameW(&dialog) != FALSE) {
        load_file(state, std::filesystem::path(buffer.data()));
    }
}

void begin_playback(app_state* state) {
    if (state == nullptr || state->audio == nullptr) {
        return;
    }
    EnableWindow(state->play_button, FALSE);
    EnableWindow(state->stop_button, TRUE);
    set_text(state->status_label, L"Playing native Resonith reconstruction...");

    const HWND window = state->window;
    state->player.play(
        state->audio,
        [window, state](std::wstring message) {
            if (state->closing.load()) {
                return;
            }
            auto* payload = new std::wstring(std::move(message));
            if (
                PostMessageW(
                    window,
                    playback_done_message,
                    0U,
                    reinterpret_cast<LPARAM>(payload)
                ) == FALSE
            ) {
                delete payload;
            }
        }
    );
}

void create_controls(HWND window, app_state* state) {
    constexpr DWORD label_style = WS_CHILD | WS_VISIBLE | SS_LEFT;
    constexpr DWORD button_style =
        WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON;

    CreateWindowExW(
        0U,
        L"BUTTON",
        L"Open Resonith file",
        button_style,
        24,
        24,
        170,
        36,
        window,
        reinterpret_cast<HMENU>(
            static_cast<std::intptr_t>(open_button_id)
        ),
        nullptr,
        nullptr
    );
    state->play_button = CreateWindowExW(
        0U,
        L"BUTTON",
        L"Play",
        button_style | WS_DISABLED,
        210,
        24,
        96,
        36,
        window,
        reinterpret_cast<HMENU>(
            static_cast<std::intptr_t>(play_button_id)
        ),
        nullptr,
        nullptr
    );
    state->stop_button = CreateWindowExW(
        0U,
        L"BUTTON",
        L"Stop",
        button_style | WS_DISABLED,
        318,
        24,
        96,
        36,
        window,
        reinterpret_cast<HMENU>(
            static_cast<std::intptr_t>(stop_button_id)
        ),
        nullptr,
        nullptr
    );
    state->path_label = CreateWindowExW(
        0U,
        L"STATIC",
        L"No Resonith file loaded",
        label_style,
        24,
        88,
        690,
        28,
        window,
        nullptr,
        nullptr,
        nullptr
    );
    state->details_label = CreateWindowExW(
        0U,
        L"STATIC",
        L"",
        label_style,
        24,
        122,
        690,
        28,
        window,
        nullptr,
        nullptr,
        nullptr
    );
    state->status_label = CreateWindowExW(
        WS_EX_CLIENTEDGE,
        L"STATIC",
        L"Open or drop an .lps5 file. No WAV conversion is used.",
        label_style | SS_CENTERIMAGE,
        24,
        168,
        690,
        46,
        window,
        nullptr,
        nullptr,
        nullptr
    );
}

LRESULT CALLBACK window_procedure(
    HWND window,
    UINT message,
    WPARAM word,
    LPARAM long_word
) {
    auto* state = reinterpret_cast<app_state*>(
        GetWindowLongPtrW(window, GWLP_USERDATA)
    );
    switch (message) {
    case WM_CREATE: {
        auto* created = new app_state{};
        created->window = window;
        SetWindowLongPtrW(
            window,
            GWLP_USERDATA,
            reinterpret_cast<LONG_PTR>(created)
        );
        create_controls(window, created);
        DragAcceptFiles(window, TRUE);
        return 0;
    }
    case WM_COMMAND:
        if (state == nullptr) {
            return 0;
        }
        switch (LOWORD(word)) {
        case open_button_id:
            choose_file(state);
            return 0;
        case play_button_id:
            begin_playback(state);
            return 0;
        case stop_button_id:
            stop_playback(state);
            set_text(state->status_label, L"Playback stopped.");
            return 0;
        default:
            return 0;
        }
    case WM_DROPFILES: {
        if (state == nullptr) {
            return 0;
        }
        const HDROP drop = reinterpret_cast<HDROP>(word);
        std::array<wchar_t, 32768> path{};
        if (
            DragQueryFileW(
                drop,
                0U,
                path.data(),
                static_cast<UINT>(path.size())
            ) != 0U
        ) {
            load_file(state, std::filesystem::path(path.data()));
        }
        DragFinish(drop);
        return 0;
    }
    case playback_done_message: {
        std::unique_ptr<std::wstring> payload(
            reinterpret_cast<std::wstring*>(long_word)
        );
        if (state != nullptr) {
            set_text(
                state->status_label,
                payload == nullptr ? L"Playback ended." : *payload
            );
            EnableWindow(state->play_button, state->audio != nullptr);
            EnableWindow(state->stop_button, FALSE);
        }
        return 0;
    }
    case WM_CLOSE:
        if (state != nullptr) {
            state->closing.store(true);
            stop_playback(state);
        }
        DestroyWindow(window);
        return 0;
    case WM_DESTROY:
        SetWindowLongPtrW(window, GWLP_USERDATA, 0);
        delete state;
        PostQuitMessage(0);
        return 0;
    default:
        return DefWindowProcW(window, message, word, long_word);
    }
}

}  // namespace

int WINAPI wWinMain(
    HINSTANCE instance,
    HINSTANCE,
    PWSTR command_line,
    int show_command
) {
    const wchar_t class_name[] = L"OrkelaMainWindow";
    WNDCLASSEXW window_class{};
    window_class.cbSize = sizeof(window_class);
    window_class.style = CS_HREDRAW | CS_VREDRAW;
    window_class.lpfnWndProc = window_procedure;
    window_class.hInstance = instance;
    window_class.hCursor = LoadCursorW(nullptr, IDC_ARROW);
    window_class.hIcon = LoadIconW(nullptr, IDI_APPLICATION);
    window_class.hbrBackground =
        reinterpret_cast<HBRUSH>(COLOR_WINDOW + 1);
    window_class.lpszClassName = class_name;
    window_class.hIconSm = LoadIconW(nullptr, IDI_APPLICATION);
    if (RegisterClassExW(&window_class) == 0U) {
        return 1;
    }

    const HWND window = CreateWindowExW(
        0U,
        class_name,
        L"Orkela — Resonith Player",
        WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX,
        CW_USEDEFAULT,
        CW_USEDEFAULT,
        760,
        280,
        nullptr,
        nullptr,
        instance,
        nullptr
    );
    if (window == nullptr) {
        return 1;
    }

    ShowWindow(window, show_command);
    UpdateWindow(window);

    if (command_line != nullptr && command_line[0] != L'\0') {
        int argument_count = 0;
        LPWSTR* arguments = CommandLineToArgvW(
            GetCommandLineW(),
            &argument_count
        );
        if (arguments != nullptr) {
            if (argument_count >= 2) {
                auto* state = reinterpret_cast<app_state*>(
                    GetWindowLongPtrW(window, GWLP_USERDATA)
                );
                load_file(state, std::filesystem::path(arguments[1]));
            }
            LocalFree(arguments);
        }
    }

    MSG message{};
    while (GetMessageW(&message, nullptr, 0U, 0U) > 0) {
        TranslateMessage(&message);
        DispatchMessageW(&message);
    }
    return static_cast<int>(message.wParam);
}
