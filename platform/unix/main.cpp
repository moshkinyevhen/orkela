#include "orkela/localization.h"
#include "orkela/resonith_pull_decoder.h"
#include "orkela/visual_analysis.h"

#include <gst/app/gstappsrc.h>
#include <gst/gst.h>
#include <gtk/gtk.h>

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <limits>
#include <memory>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace {

constexpr std::size_t maximum_input_bytes = 64ULL * 1024ULL * 1024ULL;
constexpr std::size_t analysis_window = 4096U;
constexpr std::size_t language_choice_count =
    orkela::supported_language_count + 1U;

struct app_state {
    GtkApplication* application = nullptr;
    GtkWindow* window = nullptr;
    GtkLabel* title = nullptr;
    GtkLabel* metadata = nullptr;
    GtkLabel* status = nullptr;
    GtkButton* open = nullptr;
    GtkButton* play = nullptr;
    GtkButton* stop = nullptr;
    GtkButton* settings = nullptr;
    GtkDrawingArea* visual = nullptr;
    GtkProgressBar* progress = nullptr;
    std::shared_ptr<orkela::decoded_audio> audio;
    orkela::pcm_visual_analyzer analyzer;
    orkela::visual_snapshot snapshot;
    orkela::visual_mode visual_mode = orkela::visual_mode::field;
    GstElement* pipeline = nullptr;
    GstElement* source = nullptr;
    guint timer = 0U;
    std::uint32_t last_visual_frame =
        std::numeric_limits<std::uint32_t>::max();
    std::uint8_t language_choice = 0U;
    bool paused = false;
};

constexpr std::array languages = {
    orkela::language::english,
    orkela::language::german,
    orkela::language::spanish,
    orkela::language::italian,
    orkela::language::japanese,
    orkela::language::korean,
    orkela::language::chinese_simplified,
    orkela::language::russian,
    orkela::language::ukrainian,
};

std::filesystem::path settings_path() {
    return std::filesystem::path(g_get_user_config_dir())
        / "orkela"
        / "settings.ini";
}

void load_preferences(app_state* state) {
    GKeyFile* file = g_key_file_new();
    GError* error = nullptr;
    const std::string path = settings_path().string();
    if (
        g_key_file_load_from_file(
            file,
            path.c_str(),
            G_KEY_FILE_NONE,
            &error
        )
    ) {
        const gint value = g_key_file_get_integer(
            file,
            "Interface",
            "Language",
            nullptr
        );
        state->language_choice = static_cast<std::uint8_t>(
            std::clamp<gint>(
                value,
                0,
                static_cast<gint>(language_choice_count - 1U)
            )
        );
    }
    if (error != nullptr) {
        g_error_free(error);
    }
    g_key_file_unref(file);
}

void save_preferences(const app_state* state) {
    try {
        const std::filesystem::path path = settings_path();
        std::filesystem::create_directories(path.parent_path());
        GKeyFile* file = g_key_file_new();
        g_key_file_set_integer(
            file,
            "Interface",
            "Language",
            state->language_choice
        );
        GError* error = nullptr;
        static_cast<void>(
            g_key_file_save_to_file(
                file,
                path.string().c_str(),
                &error
            )
        );
        if (error != nullptr) {
            g_error_free(error);
        }
        g_key_file_unref(file);
    } catch (...) {
        // Presentation preferences never block direct codec playback.
    }
}

orkela::language active_language(const app_state* state) {
    if (state->language_choice != 0U) {
        return languages[
            static_cast<std::size_t>(state->language_choice - 1U)
        ];
    }
    const gchar* const* names = g_get_language_names();
    const std::string_view tag =
        names != nullptr && names[0] != nullptr ? names[0] : "en";
    return orkela::language_from_tag(tag);
}

const char* text(const app_state* state, orkela::text_id identifier) {
    return orkela::localized_text(
        active_language(state),
        identifier
    ).data();
}

orkela::text_id mode_text_id(orkela::visual_mode mode) {
    switch (mode) {
    case orkela::visual_mode::field:
        return orkela::text_id::field;
    case orkela::visual_mode::spectrum:
        return orkela::text_id::spectrum;
    case orkela::visual_mode::wave:
        return orkela::text_id::wave;
    case orkela::visual_mode::history:
        return orkela::text_id::history;
    }
    return orkela::text_id::field;
}

void stop_pipeline(app_state* state) {
    if (state->timer != 0U) {
        g_source_remove(state->timer);
        state->timer = 0U;
    }
    if (state->pipeline != nullptr) {
        gst_element_set_state(state->pipeline, GST_STATE_NULL);
        gst_object_unref(state->pipeline);
        state->pipeline = nullptr;
        state->source = nullptr;
    }
    state->paused = false;
}

void apply_localization(app_state* state) {
    const std::string window_title =
        std::string(text(state, orkela::text_id::app_name))
        + " — "
        + text(state, orkela::text_id::tagline);
    gtk_window_set_title(state->window, window_title.c_str());
    gtk_widget_set_tooltip_text(
        GTK_WIDGET(state->settings),
        text(state, orkela::text_id::settings)
    );
    gtk_accessible_update_property(
        GTK_ACCESSIBLE(state->settings),
        GTK_ACCESSIBLE_PROPERTY_LABEL,
        text(state, orkela::text_id::settings),
        -1
    );
    gtk_button_set_label(
        state->open,
        text(state, orkela::text_id::open_resonith)
    );
    gtk_button_set_label(
        state->stop,
        text(state, orkela::text_id::stop_action)
    );
    gtk_button_set_label(
        state->play,
        text(
            state,
            state->paused
                ? orkela::text_id::resume_action
                : orkela::text_id::play_action
        )
    );
    gtk_label_set_text(
        state->status,
        text(
            state,
            state->audio == nullptr
                ? orkela::text_id::authenticating
                : orkela::text_id::ready
        )
    );
    gtk_accessible_update_property(
        GTK_ACCESSIBLE(state->visual),
        GTK_ACCESSIBLE_PROPERTY_LABEL,
        text(state, mode_text_id(state->visual_mode)),
        GTK_ACCESSIBLE_PROPERTY_DESCRIPTION,
        text(state, orkela::text_id::visual_hint),
        -1
    );
    gtk_accessible_update_property(
        GTK_ACCESSIBLE(state->progress),
        GTK_ACCESSIBLE_PROPERTY_LABEL,
        text(state, orkela::text_id::playback_timeline),
        -1
    );
    gtk_widget_queue_draw(GTK_WIDGET(state->visual));
}

void draw_wave(
    cairo_t* context,
    const app_state* state,
    double left,
    double top,
    double width,
    double height,
    double line_width
) {
    const double center = top + height * 0.5;
    for (
        std::size_t index = 0U;
        index < orkela::visual_wave_points;
        ++index
    ) {
        const double x = left
            + static_cast<double>(index) * width
                / static_cast<double>(orkela::visual_wave_points - 1U);
        const double y = center
            - static_cast<double>(state->snapshot.wave[index])
                * height * 0.47;
        if (index == 0U) {
            cairo_move_to(context, x, y);
        } else {
            cairo_line_to(context, x, y);
        }
    }
    cairo_set_source_rgba(context, 0.46, 0.40, 1.0, 0.96);
    cairo_set_line_width(context, line_width);
    cairo_stroke(context);
}

void draw_visual(
    GtkDrawingArea* area,
    cairo_t* context,
    int width,
    int height,
    gpointer user_data
) {
    (void)area;
    auto* state = static_cast<app_state*>(user_data);
    cairo_set_source_rgb(context, 0.045, 0.052, 0.095);
    cairo_paint(context);

    cairo_set_source_rgba(context, 0.68, 0.63, 1.0, 0.95);
    cairo_select_font_face(
        context,
        "Sans",
        CAIRO_FONT_SLANT_NORMAL,
        CAIRO_FONT_WEIGHT_BOLD
    );
    cairo_set_font_size(context, 13.0);
    cairo_move_to(context, 22.0, 26.0);
    cairo_show_text(
        context,
        text(state, mode_text_id(state->visual_mode))
    );

    const double left = 22.0;
    const double top = 42.0;
    const double available_width =
        std::max(1.0, static_cast<double>(width) - 44.0);
    const double available_height =
        std::max(1.0, static_cast<double>(height) - 64.0);

    if (state->visual_mode == orkela::visual_mode::spectrum) {
        const double step = available_width
            / static_cast<double>(orkela::visual_spectrum_bands);
        for (
            std::size_t band = 0U;
            band < orkela::visual_spectrum_bands;
            ++band
        ) {
            const double level = state->snapshot.spectrum[band];
            const double bar_height = 2.0 + level * available_height;
            cairo_set_source_rgba(
                context,
                0.42,
                0.48 + 0.35 * level,
                1.0,
                0.92
            );
            cairo_rectangle(
                context,
                left + static_cast<double>(band) * step,
                top + available_height - bar_height,
                std::max(1.0, step - 2.0),
                bar_height
            );
            cairo_fill(context);
        }
        return;
    }

    if (state->visual_mode == orkela::visual_mode::history) {
        const std::size_t columns = std::max<std::size_t>(
            1U,
            state->snapshot.history_columns
        );
        const double column_width =
            available_width / static_cast<double>(columns);
        const double band_height = available_height
            / static_cast<double>(orkela::visual_spectrum_bands);
        for (std::size_t column = 0U; column < columns; ++column) {
            for (
                std::size_t band = 0U;
                band < orkela::visual_spectrum_bands;
                ++band
            ) {
                const double level = state->snapshot.history[
                    column * orkela::visual_spectrum_bands + band
                ];
                if (level <= 0.015) {
                    continue;
                }
                cairo_set_source_rgba(
                    context,
                    0.30 + level * 0.30,
                    0.36 + level * 0.44,
                    0.90,
                    0.18 + level * 0.82
                );
                cairo_rectangle(
                    context,
                    left + static_cast<double>(column) * column_width,
                    top + available_height
                        - static_cast<double>(band + 1U) * band_height,
                    column_width + 0.5,
                    band_height + 0.5
                );
                cairo_fill(context);
            }
        }
        return;
    }

    draw_wave(
        context,
        state,
        left,
        top,
        available_width,
        available_height,
        state->visual_mode == orkela::visual_mode::field ? 2.8 : 1.8
    );
    if (state->visual_mode == orkela::visual_mode::field) {
        const double step = available_width
            / static_cast<double>(orkela::visual_spectrum_bands);
        for (
            std::size_t band = 0U;
            band < orkela::visual_spectrum_bands;
            ++band
        ) {
            const double level = state->snapshot.spectrum[band];
            cairo_set_source_rgba(
                context,
                0.28,
                0.64,
                1.0,
                0.10 + 0.35 * level
            );
            cairo_rectangle(
                context,
                left + static_cast<double>(band) * step,
                top + available_height
                    - level * available_height * 0.62,
                std::max(1.0, step - 1.0),
                level * available_height * 0.62
            );
            cairo_fill(context);
        }
    }
}

void offer_visual_at(app_state* state, std::uint32_t frame) {
    if (
        state->audio == nullptr
        || state->audio->channels == 0U
        || state->audio->frame_count == 0U
        || frame == state->last_visual_frame
    ) {
        return;
    }
    const std::size_t bounded = std::min<std::size_t>(
        frame,
        state->audio->frame_count
    );
    const std::size_t start = bounded > analysis_window / 2U
        ? bounded - analysis_window / 2U
        : 0U;
    const std::size_t count = std::min<std::size_t>(
        analysis_window,
        state->audio->frame_count - start
    );
    static_cast<void>(
        state->analyzer.offer(
            std::span<const std::int16_t>(
                state->audio->samples.data()
                    + start * state->audio->channels,
                count * state->audio->channels
            ),
            state->audio->channels,
            state->audio->sample_rate
        )
    );
    state->snapshot = state->analyzer.snapshot();
    state->last_visual_frame = frame;
    gtk_widget_queue_draw(GTK_WIDGET(state->visual));
}

gboolean playback_tick(gpointer user_data) {
    auto* state = static_cast<app_state*>(user_data);
    if (state->pipeline == nullptr || state->audio == nullptr) {
        return G_SOURCE_REMOVE;
    }
    GstBus* bus = gst_element_get_bus(state->pipeline);
    GstMessage* message = gst_bus_pop_filtered(
        bus,
        static_cast<GstMessageType>(GST_MESSAGE_EOS | GST_MESSAGE_ERROR)
    );
    gst_object_unref(bus);
    if (message != nullptr) {
        const GstMessageType type = GST_MESSAGE_TYPE(message);
        gst_message_unref(message);
        stop_pipeline(state);
        gtk_progress_bar_set_fraction(state->progress, 1.0);
        gtk_label_set_text(
            state->status,
            text(
                state,
                type == GST_MESSAGE_EOS
                    ? orkela::text_id::playback_complete
                    : orkela::text_id::playback_failed
            )
        );
        gtk_button_set_label(
            state->play,
            text(state, orkela::text_id::play_action)
        );
        return G_SOURCE_REMOVE;
    }

    gint64 position = 0;
    if (
        gst_element_query_position(
            state->pipeline,
            GST_FORMAT_TIME,
            &position
        )
        && position >= 0
    ) {
        const double duration = static_cast<double>(
            gst_util_uint64_scale(
                state->audio->frame_count,
                GST_SECOND,
                state->audio->sample_rate
            )
        );
        gtk_progress_bar_set_fraction(
            state->progress,
            duration <= 0.0
                ? 0.0
                : std::clamp(
                    static_cast<double>(position) / duration,
                    0.0,
                    1.0
                )
        );
        const std::uint32_t frame = static_cast<std::uint32_t>(
            gst_util_uint64_scale(
                static_cast<guint64>(position),
                state->audio->sample_rate,
                GST_SECOND
            )
        );
        offer_visual_at(state, frame);
    }
    return G_SOURCE_CONTINUE;
}

bool start_pipeline(app_state* state) {
    if (state->audio == nullptr) {
        return false;
    }
    GError* error = nullptr;
    state->pipeline = gst_parse_launch(
        "appsrc name=source format=time ! queue ! "
        "audioconvert ! audioresample ! autoaudiosink",
        &error
    );
    if (state->pipeline == nullptr || error != nullptr) {
        if (error != nullptr) {
            g_error_free(error);
        }
        stop_pipeline(state);
        return false;
    }
    state->source = gst_bin_get_by_name(
        GST_BIN(state->pipeline),
        "source"
    );
    GstCaps* caps = gst_caps_new_simple(
        "audio/x-raw",
        "format",
        G_TYPE_STRING,
        "S16LE",
        "layout",
        G_TYPE_STRING,
        "interleaved",
        "rate",
        G_TYPE_INT,
        static_cast<gint>(state->audio->sample_rate),
        "channels",
        G_TYPE_INT,
        static_cast<gint>(state->audio->channels),
        nullptr
    );
    gst_app_src_set_caps(GST_APP_SRC(state->source), caps);
    gst_caps_unref(caps);

    const std::size_t byte_count =
        state->audio->samples.size() * sizeof(std::int16_t);
    GstBuffer* buffer = gst_buffer_new_allocate(
        nullptr,
        byte_count,
        nullptr
    );
    GstMapInfo mapping{};
    if (
        buffer == nullptr
        || !gst_buffer_map(buffer, &mapping, GST_MAP_WRITE)
    ) {
        if (buffer != nullptr) {
            gst_buffer_unref(buffer);
        }
        stop_pipeline(state);
        return false;
    }
    std::memcpy(
        mapping.data,
        state->audio->samples.data(),
        byte_count
    );
    gst_buffer_unmap(buffer, &mapping);
    GST_BUFFER_DURATION(buffer) = gst_util_uint64_scale(
        state->audio->frame_count,
        GST_SECOND,
        state->audio->sample_rate
    );
    if (
        gst_app_src_push_buffer(GST_APP_SRC(state->source), buffer)
            != GST_FLOW_OK
        || gst_app_src_end_of_stream(GST_APP_SRC(state->source))
            != GST_FLOW_OK
    ) {
        stop_pipeline(state);
        return false;
    }
    gst_object_unref(state->source);
    state->source = nullptr;
    if (
        gst_element_set_state(state->pipeline, GST_STATE_PLAYING)
            == GST_STATE_CHANGE_FAILURE
    ) {
        stop_pipeline(state);
        return false;
    }
    state->timer = g_timeout_add(50U, playback_tick, state);
    return true;
}

void toggle_playback(GtkButton* button, gpointer user_data) {
    (void)button;
    auto* state = static_cast<app_state*>(user_data);
    if (state->pipeline == nullptr) {
        if (!start_pipeline(state)) {
            gtk_label_set_text(
                state->status,
                text(state, orkela::text_id::playback_failed)
            );
            return;
        }
        gtk_button_set_label(
            state->play,
            text(state, orkela::text_id::pause_action)
        );
        gtk_label_set_text(
            state->status,
            text(state, orkela::text_id::playing)
        );
        return;
    }
    state->paused = !state->paused;
    gst_element_set_state(
        state->pipeline,
        state->paused ? GST_STATE_PAUSED : GST_STATE_PLAYING
    );
    gtk_button_set_label(
        state->play,
        text(
            state,
            state->paused
                ? orkela::text_id::resume_action
                : orkela::text_id::pause_action
        )
    );
    gtk_label_set_text(
        state->status,
        text(
            state,
            state->paused
                ? orkela::text_id::paused
                : orkela::text_id::playing
        )
    );
}

void stop_playback(GtkButton* button, gpointer user_data) {
    (void)button;
    auto* state = static_cast<app_state*>(user_data);
    stop_pipeline(state);
    gtk_progress_bar_set_fraction(state->progress, 0.0);
    gtk_button_set_label(
        state->play,
        text(state, orkela::text_id::play_action)
    );
    gtk_label_set_text(
        state->status,
        text(state, orkela::text_id::stopped)
    );
}

bool load_file(app_state* state, const std::filesystem::path& path) {
    std::error_code file_error;
    const std::uintmax_t size = std::filesystem::file_size(
        path,
        file_error
    );
    if (
        file_error
        || size == 0U
        || size > maximum_input_bytes
    ) {
        return false;
    }
    std::ifstream input(path, std::ios::binary);
    std::vector<std::uint8_t> bytes(
        std::istreambuf_iterator<char>(input),
        std::istreambuf_iterator<char>()
    );
    auto decoded = std::make_shared<orkela::decoded_audio>();
    std::string error;
    if (
        !orkela::decode_resonith_bytes(
            std::move(bytes),
            decoded.get(),
            &error
        )
    ) {
        return false;
    }
    stop_pipeline(state);
    state->audio = std::move(decoded);
    state->analyzer.reset();
    state->snapshot = {};
    state->last_visual_frame =
        std::numeric_limits<std::uint32_t>::max();
    gtk_label_set_text(state->title, path.stem().string().c_str());
    const std::string details =
        std::to_string(state->audio->sample_rate)
        + " Hz • "
        + std::to_string(state->audio->channels)
        + " ch • C++23";
    gtk_label_set_text(state->metadata, details.c_str());
    gtk_label_set_text(
        state->status,
        text(state, orkela::text_id::ready)
    );
    gtk_progress_bar_set_fraction(state->progress, 0.0);
    offer_visual_at(state, 0U);
    return true;
}

void open_response(
    GObject* source,
    GAsyncResult* result,
    gpointer user_data
) {
    auto* state = static_cast<app_state*>(user_data);
    GError* error = nullptr;
    GFile* file = gtk_file_dialog_open_finish(
        GTK_FILE_DIALOG(source),
        result,
        &error
    );
    if (file != nullptr) {
        char* path = g_file_get_path(file);
        const bool loaded = path != nullptr
            && load_file(state, std::filesystem::path(path));
        if (!loaded) {
            gtk_label_set_text(
                state->status,
                text(state, orkela::text_id::playback_failed)
            );
        }
        g_free(path);
        g_object_unref(file);
    }
    if (error != nullptr) {
        if (!g_error_matches(error, GTK_DIALOG_ERROR, GTK_DIALOG_ERROR_DISMISSED)) {
            gtk_label_set_text(
                state->status,
                text(state, orkela::text_id::playback_failed)
            );
        }
        g_error_free(error);
    }
}

void open_document(GtkButton* button, gpointer user_data) {
    (void)button;
    auto* state = static_cast<app_state*>(user_data);
    GtkFileDialog* chooser = gtk_file_dialog_new();
    gtk_file_dialog_set_title(
        chooser,
        text(state, orkela::text_id::open_resonith)
    );
    gtk_file_dialog_set_accept_label(
        chooser,
        text(state, orkela::text_id::open_resonith)
    );
    gtk_file_dialog_set_modal(chooser, TRUE);
    GtkFileFilter* filter = gtk_file_filter_new();
    gtk_file_filter_set_name(filter, "Resonith Audio");
    gtk_file_filter_add_pattern(filter, "*.resonith");
    GListStore* filters = g_list_store_new(GTK_TYPE_FILE_FILTER);
    g_list_store_append(filters, filter);
    gtk_file_dialog_set_filters(chooser, G_LIST_MODEL(filters));
    gtk_file_dialog_set_default_filter(chooser, filter);
    gtk_file_dialog_open(
        chooser,
        state->window,
        nullptr,
        open_response,
        state
    );
    g_object_unref(filters);
    g_object_unref(filter);
    g_object_unref(chooser);
}

void settings_done(GtkButton* button, gpointer user_data) {
    (void)button;
    GtkWindow* settings_window = GTK_WINDOW(user_data);
    auto* state = static_cast<app_state*>(
        g_object_get_data(
            G_OBJECT(settings_window),
            "orkela-state"
        )
    );
    GtkDropDown* languages_drop_down = GTK_DROP_DOWN(
        g_object_get_data(
            G_OBJECT(settings_window),
            "orkela-language-dropdown"
        )
    );
    state->language_choice = static_cast<std::uint8_t>(
        gtk_drop_down_get_selected(languages_drop_down)
    );
    save_preferences(state);
    apply_localization(state);
    gtk_window_destroy(settings_window);
}

void show_settings(GtkButton* button, gpointer user_data) {
    (void)button;
    auto* state = static_cast<app_state*>(user_data);
    GtkWindow* dialog = GTK_WINDOW(gtk_window_new());
    gtk_window_set_title(
        dialog,
        text(state, orkela::text_id::settings)
    );
    gtk_window_set_transient_for(dialog, state->window);
    gtk_window_set_modal(dialog, TRUE);
    gtk_window_set_resizable(dialog, FALSE);
    GtkWidget* content = gtk_box_new(
        GTK_ORIENTATION_VERTICAL,
        12
    );
    gtk_widget_set_margin_top(content, 18);
    gtk_widget_set_margin_bottom(content, 18);
    gtk_widget_set_margin_start(content, 18);
    gtk_widget_set_margin_end(content, 18);
    GtkWidget* description = gtk_label_new(
        text(state, orkela::text_id::language_description)
    );
    gtk_label_set_wrap(GTK_LABEL(description), TRUE);
    gtk_box_append(GTK_BOX(content), description);

    GtkStringList* values = gtk_string_list_new(nullptr);
    gtk_string_list_append(
        values,
        text(state, orkela::text_id::system_default)
    );
    for (orkela::language language : languages) {
        gtk_string_list_append(
            values,
            orkela::language_autonym(language).data()
        );
    }
    GtkWidget* drop_down = gtk_drop_down_new(
        G_LIST_MODEL(values),
        nullptr
    );
    g_object_unref(values);
    gtk_drop_down_set_selected(
        GTK_DROP_DOWN(drop_down),
        state->language_choice
    );
    gtk_widget_set_margin_bottom(drop_down, 18);
    gtk_box_append(GTK_BOX(content), drop_down);
    GtkWidget* done = gtk_button_new_with_label(
        text(state, orkela::text_id::done)
    );
    gtk_box_append(GTK_BOX(content), done);
    g_object_set_data(
        G_OBJECT(dialog),
        "orkela-language-dropdown",
        drop_down
    );
    g_object_set_data(
        G_OBJECT(dialog),
        "orkela-state",
        state
    );
    g_signal_connect(done, "clicked", G_CALLBACK(settings_done), dialog);
    gtk_window_set_child(dialog, content);
    gtk_window_present(GTK_WINDOW(dialog));
}

void visual_pressed(
    GtkGestureClick* gesture,
    gint press_count,
    double x,
    double y,
    gpointer user_data
) {
    (void)gesture;
    (void)press_count;
    (void)x;
    (void)y;
    auto* state = static_cast<app_state*>(user_data);
    state->visual_mode =
        orkela::next_visual_mode(state->visual_mode);
    apply_localization(state);
}

void activate(GtkApplication* application, gpointer user_data) {
    auto* state = static_cast<app_state*>(user_data);
    if (state->window != nullptr) {
        gtk_window_present(state->window);
        return;
    }
    state->application = application;
    load_preferences(state);

    state->window = GTK_WINDOW(gtk_application_window_new(application));
    gtk_window_set_default_size(state->window, 980, 720);
    gtk_window_set_title(state->window, "Orkela");

    GtkCssProvider* css = gtk_css_provider_new();
    gtk_css_provider_load_from_string(
        css,
        "window { background: #050714; color: #f7f7ff; }"
        ".orkela-card { background: #0c1025; border-radius: 24px;"
        " border: 1px solid #343866; }"
        "button { border-radius: 14px; padding: 11px 20px;"
        " background: #292449; color: #ffffff; }"
        ".orkela-title { font-size: 30px; font-weight: 800; }"
        ".orkela-brand { color: #a49aff; font-weight: 800;"
        " letter-spacing: 4px; }"
        ".orkela-muted { color: #a5a9bd; }"
    );
    gtk_style_context_add_provider_for_display(
        gtk_widget_get_display(GTK_WIDGET(state->window)),
        GTK_STYLE_PROVIDER(css),
        GTK_STYLE_PROVIDER_PRIORITY_APPLICATION
    );
    g_object_unref(css);

    GtkWidget* root = gtk_box_new(GTK_ORIENTATION_VERTICAL, 12);
    gtk_widget_set_margin_top(root, 26);
    gtk_widget_set_margin_bottom(root, 26);
    gtk_widget_set_margin_start(root, 36);
    gtk_widget_set_margin_end(root, 36);

    GtkWidget* header = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 12);
    GtkWidget* brand = gtk_label_new("O R K E L A");
    gtk_widget_add_css_class(brand, "orkela-brand");
    gtk_widget_set_hexpand(brand, TRUE);
    gtk_widget_set_halign(brand, GTK_ALIGN_START);
    state->settings = GTK_BUTTON(
        gtk_button_new_from_icon_name("emblem-system-symbolic")
    );
    gtk_box_append(GTK_BOX(header), brand);
    gtk_box_append(GTK_BOX(header), GTK_WIDGET(state->settings));

    state->title = GTK_LABEL(gtk_label_new(
        text(state, orkela::text_id::native_resonith)
    ));
    gtk_widget_add_css_class(GTK_WIDGET(state->title), "orkela-title");
    state->metadata = GTK_LABEL(gtk_label_new(
        text(state, orkela::text_id::portable_session)
    ));
    gtk_widget_add_css_class(GTK_WIDGET(state->metadata), "orkela-muted");
    state->visual = GTK_DRAWING_AREA(gtk_drawing_area_new());
    gtk_widget_set_vexpand(GTK_WIDGET(state->visual), TRUE);
    gtk_widget_set_size_request(GTK_WIDGET(state->visual), -1, 360);
    gtk_widget_add_css_class(GTK_WIDGET(state->visual), "orkela-card");
    gtk_drawing_area_set_draw_func(
        state->visual,
        draw_visual,
        state,
        nullptr
    );
    GtkGesture* click = gtk_gesture_click_new();
    g_signal_connect(
        click,
        "pressed",
        G_CALLBACK(visual_pressed),
        state
    );
    gtk_widget_add_controller(
        GTK_WIDGET(state->visual),
        GTK_EVENT_CONTROLLER(click)
    );

    state->progress = GTK_PROGRESS_BAR(gtk_progress_bar_new());
    GtkWidget* controls = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 12);
    gtk_widget_set_halign(controls, GTK_ALIGN_CENTER);
    state->open = GTK_BUTTON(gtk_button_new());
    state->play = GTK_BUTTON(gtk_button_new());
    state->stop = GTK_BUTTON(gtk_button_new());
    gtk_box_append(GTK_BOX(controls), GTK_WIDGET(state->open));
    gtk_box_append(GTK_BOX(controls), GTK_WIDGET(state->play));
    gtk_box_append(GTK_BOX(controls), GTK_WIDGET(state->stop));
    state->status = GTK_LABEL(gtk_label_new(""));
    gtk_widget_add_css_class(GTK_WIDGET(state->status), "orkela-muted");

    gtk_box_append(GTK_BOX(root), header);
    gtk_box_append(GTK_BOX(root), GTK_WIDGET(state->title));
    gtk_box_append(GTK_BOX(root), GTK_WIDGET(state->metadata));
    gtk_box_append(GTK_BOX(root), GTK_WIDGET(state->visual));
    gtk_box_append(GTK_BOX(root), GTK_WIDGET(state->progress));
    gtk_box_append(GTK_BOX(root), controls);
    gtk_box_append(GTK_BOX(root), GTK_WIDGET(state->status));
    gtk_window_set_child(state->window, root);

    g_signal_connect(
        state->open,
        "clicked",
        G_CALLBACK(open_document),
        state
    );
    g_signal_connect(
        state->play,
        "clicked",
        G_CALLBACK(toggle_playback),
        state
    );
    g_signal_connect(
        state->stop,
        "clicked",
        G_CALLBACK(stop_playback),
        state
    );
    g_signal_connect(
        state->settings,
        "clicked",
        G_CALLBACK(show_settings),
        state
    );
    apply_localization(state);
    gtk_window_present(state->window);
}

void open_files(
    GApplication* application,
    GFile** files,
    gint file_count,
    const gchar* hint,
    gpointer user_data
) {
    (void)hint;
    auto* state = static_cast<app_state*>(user_data);
    activate(GTK_APPLICATION(application), state);
    if (file_count <= 0 || files == nullptr || files[0] == nullptr) {
        return;
    }

    char* path = g_file_get_path(files[0]);
    const bool loaded = path != nullptr
        && load_file(state, std::filesystem::path(path));
    g_free(path);
    if (!loaded) {
        gtk_label_set_text(
            state->status,
            text(state, orkela::text_id::playback_failed)
        );
    }
    gtk_window_present(state->window);
}

void shutdown(GApplication* application, gpointer user_data) {
    (void)application;
    auto* state = static_cast<app_state*>(user_data);
    stop_pipeline(state);
}

}  // namespace

int main(int argc, char** argv) {
    gst_init(&argc, &argv);
    auto state = std::make_unique<app_state>();
    GtkApplication* application = gtk_application_new(
        "org.scenelith.orkela",
        G_APPLICATION_HANDLES_OPEN
    );
    g_signal_connect(
        application,
        "activate",
        G_CALLBACK(activate),
        state.get()
    );
    g_signal_connect(
        application,
        "open",
        G_CALLBACK(open_files),
        state.get()
    );
    g_signal_connect(
        application,
        "shutdown",
        G_CALLBACK(shutdown),
        state.get()
    );
    const int result = g_application_run(
        G_APPLICATION(application),
        argc,
        argv
    );
    g_object_unref(application);
    return result;
}
