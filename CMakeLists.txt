cmake_minimum_required(VERSION 3.24)

project(orkela VERSION 0.2.0 LANGUAGES C CXX)

include(FetchContent)

option(ORKELA_WARNINGS_AS_ERRORS "Treat Orkela warnings as errors" ON)
set(
    RESONITH_SOURCE_DIR
    ""
    CACHE PATH
    "Optional local Resonith repository used instead of FetchContent"
)

set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(RESONITH_BUILD_TOOLS OFF CACHE BOOL "" FORCE)
set(RESONITH_BUILD_FUZZERS OFF CACHE BOOL "" FORCE)

if(RESONITH_SOURCE_DIR)
    add_subdirectory(
        "${RESONITH_SOURCE_DIR}/native"
        "${CMAKE_BINARY_DIR}/resonith"
    )
else()
    FetchContent_Declare(
        resonith
        GIT_REPOSITORY https://github.com/moshkinyevhen/resonith.git
        GIT_TAG c37c8bf6fac52f5833d2db2b7469050d3a3ad8da
        SOURCE_SUBDIR native
    )
    FetchContent_MakeAvailable(resonith)
endif()

if(NOT WIN32)
    message(FATAL_ERROR "The first Orkela milestone currently targets Windows")
endif()

add_executable(Orkela WIN32
    src/app_preferences.cpp
    src/app_preferences.h
    src/main.cpp
    src/resonith_file.cpp
    src/resonith_file.h
    src/wave_player.cpp
    src/wave_player.h
    resources/orkela.rc
    resources/resource.h
)

target_compile_features(Orkela PRIVATE cxx_std_20)
target_compile_definitions(
    Orkela
    PRIVATE
        NOMINMAX
        UNICODE
        _UNICODE
        WIN32_LEAN_AND_MEAN
)
target_link_libraries(
    Orkela
    PRIVATE
        Resonith::Core
        comdlg32
        d2d1
        dwrite
        dwmapi
        ole32
        shell32
        uxtheme
        winmm
        windowscodecs
)
set_target_properties(Orkela PROPERTIES CXX_EXTENSIONS OFF)

if(MSVC)
    target_compile_options(Orkela PRIVATE /W4 /permissive- /utf-8)
    target_link_options(Orkela PRIVATE /Brepro)
    if(ORKELA_WARNINGS_AS_ERRORS)
        target_compile_options(Orkela PRIVATE /WX)
    endif()
else()
    target_compile_options(
        Orkela
        PRIVATE -Wall -Wextra -Wconversion -Wpedantic -Wshadow
    )
    if(ORKELA_WARNINGS_AS_ERRORS)
        target_compile_options(Orkela PRIVATE -Werror)
    endif()
endif()

install(TARGETS Orkela RUNTIME DESTINATION .)
