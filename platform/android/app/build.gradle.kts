plugins {
    id("com.android.application")
}

val localResonithSource = System.getenv("ORKELA_RESONITH_SOURCE_DIR")

android {
    namespace = "org.scenelith.orkela"
    // API 37 proves Android 17 behavior while minSdk 26 preserves the
    // compatibility floor tested by the same APK in CI.
    compileSdk = 37
    buildToolsVersion = "37.0.0"
    ndkVersion = "29.0.14206865"

    defaultConfig {
        applicationId = "org.scenelith.orkela"
        minSdk = 26
        targetSdk = 37
        versionCode = 30006
        versionName = "0.3.0-alpha.6"
        testInstrumentationRunner =
            "org.scenelith.orkela.NativeDecodeInstrumentation"

        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
        externalNativeBuild {
            cmake {
                arguments += listOf(
                    "-DORKELA_BUILD_APPLICATIONS=ON",
                    "-DORKELA_WARNINGS_AS_ERRORS=ON",
                    "-DRESONITH_BUILD_SHARED=OFF",
                    "-DRESONITH_BUILD_TOOLS=OFF",
                    "-DRESONITH_BUILD_FUZZERS=OFF",
                    "-DANDROID_STL=c++_static",
                )
                if (!localResonithSource.isNullOrBlank()) {
                    arguments += "-DRESONITH_SOURCE_DIR=$localResonithSource"
                }
                cppFlags += listOf("-std=c++23")
            }
        }
    }

    externalNativeBuild {
        cmake {
            path = file("../../../CMakeLists.txt")
            version = "4.1.2"
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    sourceSets {
        getByName("main").assets.directories.add("../../../samples")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }
}
