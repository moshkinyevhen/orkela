plugins {
    id("com.android.application")
}

android {
    namespace = "org.scenelith.orkela"
    compileSdk = 36
    ndkVersion = "29.0.14206865"

    defaultConfig {
        applicationId = "org.scenelith.orkela"
        minSdk = 26
        targetSdk = 36
        versionCode = 30001
        versionName = "0.3.0-alpha.1"

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
