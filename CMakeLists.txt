cmake_minimum_required(VERSION 3.24)

project(orkela VERSION 0.3.0 LANGUAGES C CXX)

include(FetchContent)

option(ORKELA_WARNINGS_AS_ERRORS "Treat Orkela warnings as errors" ON)
option(ORKELA_BUILD_APPLICATIONS "Build available platform applications" ON)
option(ORKELA_BUILD_GATES "Build portable Orkela session gates" ON)
set(
    RESONITH_SOURCE_DIR
    ""
    CACHE PATH
    "Optional local Resonith repository used instead of FetchContent"
)

set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(RESONITH_BUILD_SHARED OFF CACHE BOOL "" FORCE)
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
        GIT_TAG 9f7650bf0bf06a35388119614745c6db1dbef709
        SOURCE_SUBDIR native
    )
    FetchContent_MakeAvailable(resonith)
endif()

add_library(
    orkela_session STATIC
    src/core/resonith_pull_decoder.cpp
)
add_library(Orkela::Session ALIAS orkela_session)
target_include_directories(
    orkela_session
    PUBLIC
        "${CMAKE_CURRENT_SOURCE_DIR}/include"
)
target_compile_features(orkela_session PUBLIC cxx_std_23)
target_link_libraries(orkela_session PUBLIC Resonith::Core)
set_target_properties(
    orkela_session
    PROPERTIES
        CXX_EXTENSIONS OFF
        POSITION_INDEPENDENT_CODE ON
)

function(orkela_enable_strict_warnings target)
    if(MSVC)
        target_compile_options(${target} PRIVATE /W4 /permissive- /utf-8)
        if(ORKELA_WARNINGS_AS_ERRORS)
            target_compile_options(${target} PRIVATE /WX)
        endif()
    else()
        target_compile_options(
            ${target}
            PRIVATE -Wall -Wextra -Wconversion -Wpedantic -Wshadow
        )
        if(ORKELA_WARNINGS_AS_ERRORS)
            target_compile_options(${target} PRIVATE -Werror)
        endif()
    endif()
endfunction()

orkela_enable_strict_warnings(orkela_session)

if(ORKELA_BUILD_GATES AND NOT ANDROID AND NOT CMAKE_SYSTEM_NAME STREQUAL "iOS")
    add_executable(
        orkela_session_gate
        tests/resonith_session_gate.cpp
    )
    target_compile_features(orkela_session_gate PRIVATE cxx_std_23)
    target_link_libraries(orkela_session_gate PRIVATE Orkela::Session)
    set_target_properties(
        orkela_session_gate
        PROPERTIES CXX_EXTENSIONS OFF
    )
    orkela_enable_strict_warnings(orkela_session_gate)
    enable_testing()
    add_test(
        NAME orkela_session_gate
        COMMAND
            orkela_session_gate
            "${CMAKE_CURRENT_SOURCE_DIR}/samples/emotional-piano.resonith"
    )

    add_executable(
        orkela_maf_session_gate
        tests/maf_session_gate.cpp
    )
    target_compile_features(orkela_maf_session_gate PRIVATE cxx_std_23)
    target_link_libraries(orkela_maf_session_gate PRIVATE Orkela::Session)
    set_target_properties(
        orkela_maf_session_gate
        PROPERTIES CXX_EXTENSIONS OFF
    )
    orkela_enable_strict_warnings(orkela_maf_session_gate)
    add_test(
        NAME orkela_maf_session_gate
        COMMAND orkela_maf_session_gate
    )
endif()

if(NOT ORKELA_BUILD_APPLICATIONS)
    return()
endif()

if(WIN32)
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
    target_compile_features(Orkela PRIVATE cxx_std_23)
    target_compile_definitions(
        Orkela
        PRIVATE
            NOMINMAX
            UNICODE
            _UNICODE
            WINVER=0x0A00
            _WIN32_WINNT=0x0A00
            WIN32_LEAN_AND_MEAN
    )
    target_link_libraries(
        Orkela
        PRIVATE
            Orkela::Session
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
    if(MINGW)
        target_link_options(Orkela PRIVATE -municode)
    endif()
    orkela_enable_strict_warnings(Orkela)
    install(TARGETS Orkela RUNTIME DESTINATION .)
elseif(ANDROID)
    add_library(
        orkela_android SHARED
        platform/android/native/orkela_android_jni.cpp
    )
    target_compile_features(orkela_android PRIVATE cxx_std_23)
    target_link_libraries(orkela_android PRIVATE Orkela::Session)
    set_target_properties(
        orkela_android
        PROPERTIES
            CXX_EXTENSIONS OFF
            OUTPUT_NAME orkela_android
    )
    orkela_enable_strict_warnings(orkela_android)
elseif(APPLE AND CMAKE_SYSTEM_NAME STREQUAL "iOS")
    enable_language(OBJCXX)
    add_executable(
        OrkelaIOS MACOSX_BUNDLE
        platform/ios/main.mm
        platform/ios/Info.plist
        samples/emotional-piano.resonith
    )
    set_source_files_properties(
        samples/emotional-piano.resonith
        PROPERTIES MACOSX_PACKAGE_LOCATION Resources
    )
    target_compile_features(OrkelaIOS PRIVATE cxx_std_23)
    target_link_libraries(
        OrkelaIOS
        PRIVATE
            Orkela::Session
            "-framework AVFAudio"
            "-framework Foundation"
            "-framework QuartzCore"
            "-framework UIKit"
            "-framework UniformTypeIdentifiers"
    )
    set_target_properties(
        OrkelaIOS
        PROPERTIES
            CXX_EXTENSIONS OFF
            MACOSX_BUNDLE_INFO_PLIST
                "${CMAKE_CURRENT_SOURCE_DIR}/platform/ios/Info.plist"
            XCODE_ATTRIBUTE_CLANG_ENABLE_OBJC_ARC YES
            XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED NO
            XCODE_ATTRIBUTE_CODE_SIGNING_REQUIRED NO
            XCODE_ATTRIBUTE_IPHONEOS_DEPLOYMENT_TARGET 15.0
            XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER
                org.scenelith.orkela
            XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY "1,2"
    )
    orkela_enable_strict_warnings(OrkelaIOS)
endif()
