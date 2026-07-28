cmake_minimum_required(VERSION 3.24)

project(
    orkela
    VERSION 0.3.0
    DESCRIPTION "Truth-aware native player for Resonith audio"
    HOMEPAGE_URL "https://github.com/moshkinyevhen/orkela"
    LANGUAGES C CXX
)

include(FetchContent)
include(GNUInstallDirs)

file(
    STRINGS
    "${CMAKE_CURRENT_SOURCE_DIR}/VERSION"
    ORKELA_PACKAGE_VERSION
    LIMIT_COUNT 1
)
string(STRIP "${ORKELA_PACKAGE_VERSION}" ORKELA_PACKAGE_VERSION)

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
        GIT_TAG c6640fcd84f5be81863da6f0b8e5c3cf8ea65abd
        SOURCE_SUBDIR native
    )
    FetchContent_MakeAvailable(resonith)
endif()

add_library(
    orkela_session STATIC
    src/core/localization.cpp
    src/core/resonith_pull_decoder.cpp
    src/core/visual_analysis.cpp
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

    add_executable(
        orkela_visual_analysis_test
        tests/visual_analysis_test.cpp
    )
    target_compile_features(
        orkela_visual_analysis_test
        PRIVATE cxx_std_23
    )
    target_link_libraries(
        orkela_visual_analysis_test
        PRIVATE Orkela::Session
    )
    set_target_properties(
        orkela_visual_analysis_test
        PROPERTIES CXX_EXTENSIONS OFF
    )
    orkela_enable_strict_warnings(orkela_visual_analysis_test)
    add_test(
        NAME orkela_visual_analysis_test
        COMMAND orkela_visual_analysis_test
    )

    add_executable(
        orkela_localization_test
        tests/localization_test.cpp
    )
    target_compile_features(
        orkela_localization_test
        PRIVATE cxx_std_23
    )
    target_link_libraries(
        orkela_localization_test
        PRIVATE Orkela::Session
    )
    set_target_properties(
        orkela_localization_test
        PROPERTIES CXX_EXTENSIONS OFF
    )
    orkela_enable_strict_warnings(orkela_localization_test)
    add_test(
        NAME orkela_localization_test
        COMMAND orkela_localization_test
    )
    find_package(Python3 COMPONENTS Interpreter QUIET)
    if(Python3_Interpreter_FOUND)
        add_test(
            NAME orkela_update_manifest_test
            COMMAND
                "${Python3_EXECUTABLE}"
                -m
                unittest
                -v
                tests/test_update_manifest.py
            WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
        )
        add_test(
            NAME orkela_packaging_contract_test
            COMMAND
                "${Python3_EXECUTABLE}"
                -m
                unittest
                -v
                tests/test_packaging_contract.py
            WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
        )
    endif()
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

    if(ORKELA_BUILD_GATES)
        add_executable(
            orkela_windows_playback_gate
            tests/windows_playback_gate.cpp
            src/resonith_file.cpp
            src/resonith_file.h
            src/wave_player.cpp
            src/wave_player.h
        )
        target_compile_features(
            orkela_windows_playback_gate
            PRIVATE cxx_std_23
        )
        target_compile_definitions(
            orkela_windows_playback_gate
            PRIVATE
                NOMINMAX
                UNICODE
                _UNICODE
                WINVER=0x0A00
                _WIN32_WINNT=0x0A00
                WIN32_LEAN_AND_MEAN
        )
        target_include_directories(
            orkela_windows_playback_gate
            PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src"
        )
        target_link_libraries(
            orkela_windows_playback_gate
            PRIVATE Orkela::Session winmm
        )
        set_target_properties(
            orkela_windows_playback_gate
            PROPERTIES CXX_EXTENSIONS OFF
        )
        orkela_enable_strict_warnings(orkela_windows_playback_gate)
    endif()
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
            "-framework CoreGraphics"
            "-framework Foundation"
            "-framework QuartzCore"
            "-framework UniformTypeIdentifiers"
            "-framework UIKit"
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
elseif(APPLE)
    enable_language(OBJCXX)
    add_executable(
        OrkelaMac MACOSX_BUNDLE
        platform/macos/main.mm
        platform/macos/Info.plist
        samples/emotional-piano.resonith
    )
    set_source_files_properties(
        samples/emotional-piano.resonith
        PROPERTIES MACOSX_PACKAGE_LOCATION Resources
    )
    target_compile_features(OrkelaMac PRIVATE cxx_std_23)
    target_link_libraries(
        OrkelaMac
        PRIVATE
            Orkela::Session
            "-framework AppKit"
            "-framework AVFAudio"
            "-framework Foundation"
            "-framework QuartzCore"
            "-framework UniformTypeIdentifiers"
    )
    set_target_properties(
        OrkelaMac
        PROPERTIES
            CXX_EXTENSIONS OFF
            OUTPUT_NAME Orkela
            MACOSX_BUNDLE_INFO_PLIST
                "${CMAKE_CURRENT_SOURCE_DIR}/platform/macos/Info.plist"
            XCODE_ATTRIBUTE_CLANG_ENABLE_OBJC_ARC YES
            XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED NO
            XCODE_ATTRIBUTE_CODE_SIGNING_REQUIRED NO
            XCODE_ATTRIBUTE_MACOSX_DEPLOYMENT_TARGET 13.0
            XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER
                org.scenelith.orkela
    )
    orkela_enable_strict_warnings(OrkelaMac)
elseif(UNIX)
    find_package(PkgConfig REQUIRED)
    pkg_check_modules(GTK4 REQUIRED IMPORTED_TARGET "gtk4>=4.12")
    pkg_check_modules(
        GSTREAMER
        REQUIRED
        IMPORTED_TARGET
        gstreamer-1.0
        gstreamer-app-1.0
    )
    add_executable(
        OrkelaUnix
        platform/unix/main.cpp
    )
    target_compile_features(OrkelaUnix PRIVATE cxx_std_23)
    target_link_libraries(
        OrkelaUnix
        PRIVATE
            Orkela::Session
            PkgConfig::GTK4
            PkgConfig::GSTREAMER
    )
    set_target_properties(
        OrkelaUnix
        PROPERTIES
            CXX_EXTENSIONS OFF
            OUTPUT_NAME orkela
    )
    orkela_enable_strict_warnings(OrkelaUnix)
    install(
        TARGETS OrkelaUnix
        RUNTIME DESTINATION "${CMAKE_INSTALL_BINDIR}"
    )
    install(
        FILES packaging/linux/org.scenelith.orkela.desktop
        DESTINATION "${CMAKE_INSTALL_DATADIR}/applications"
    )
    install(
        FILES packaging/linux/org.scenelith.orkela.metainfo.xml
        DESTINATION "${CMAKE_INSTALL_DATADIR}/metainfo"
    )
    install(
        FILES packaging/linux/org.scenelith.resonith.xml
        DESTINATION "${CMAKE_INSTALL_DATADIR}/mime/packages"
    )
    install(
        FILES resources/orkela-mark.png
        DESTINATION "${CMAKE_INSTALL_DATADIR}/pixmaps"
        RENAME orkela.png
    )
    install(
        FILES README.md CHANGELOG.md
        DESTINATION "${CMAKE_INSTALL_DATADIR}/doc/orkela"
    )

    set(CPACK_PACKAGE_NAME "orkela")
    set(CPACK_PACKAGE_VENDOR "SceneLith Project")
    set(CPACK_PACKAGE_CONTACT "Yevhen Moshkin")
    set(CPACK_PACKAGE_HOMEPAGE_URL "${PROJECT_HOMEPAGE_URL}")
    set(CPACK_PACKAGE_DESCRIPTION_SUMMARY "${PROJECT_DESCRIPTION}")
    set(CPACK_PACKAGE_VERSION "${ORKELA_PACKAGE_VERSION}")
    set(CPACK_STRIP_FILES ON)

    set(CPACK_DEBIAN_FILE_NAME DEB-DEFAULT)
    set(CPACK_DEBIAN_PACKAGE_MAINTAINER "Yevhen Moshkin")
    set(CPACK_DEBIAN_PACKAGE_SECTION "sound")
    set(CPACK_DEBIAN_PACKAGE_PRIORITY "optional")
    set(CPACK_DEBIAN_PACKAGE_VERSION "0.3.0~alpha.6")
    set(CPACK_DEBIAN_PACKAGE_RELEASE "1")
    set(CPACK_DEBIAN_PACKAGE_SHLIBDEPS ON)
    set(CPACK_DEBIAN_COMPRESSION_TYPE "zstd")

    set(CPACK_FREEBSD_PACKAGE_NAME "orkela")
    set(CPACK_FREEBSD_PACKAGE_COMMENT "${PROJECT_DESCRIPTION}")
    set(
        CPACK_FREEBSD_PACKAGE_DESCRIPTION
        "Orkela is a native C++23 player for bounded Resonith audio streams."
    )
    set(CPACK_FREEBSD_PACKAGE_WWW "${PROJECT_HOMEPAGE_URL}")
    set(CPACK_FREEBSD_PACKAGE_LICENSE "UNKNOWN")
    set(CPACK_FREEBSD_PACKAGE_MAINTAINER "Yevhen Moshkin")
    set(CPACK_FREEBSD_PACKAGE_ORIGIN "audio/orkela")
    set(CPACK_FREEBSD_PACKAGE_CATEGORIES "audio")
    # CPack 4.4 serializes one string as both the dependency name and origin.
    # FreeBSD's GTK 4 port has origin x11-toolkits/gtk40 but package name gtk4,
    # so use the installed package names until CPack can represent both fields.
    set(
        CPACK_FREEBSD_PACKAGE_DEPS
        "gtk4"
        "gstreamer1"
        "gstreamer1-plugins"
    )

    include(CPack)
endif()
