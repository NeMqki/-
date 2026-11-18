plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.remotecontrol.app"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.pocketdesk.app"
        minSdk = 26
        targetSdk = 34
        // GitHub Actions の実行番号を使い、更新のたびに番号が上がるようにする
        versionCode = System.getenv("GITHUB_RUN_NUMBER")?.toIntOrNull() ?: 1
        versionName = "1.0"
    }

    signingConfigs {
        getByName("debug") {
            // 固定の署名鍵があれば使う (無いとビルドごとに鍵が変わり、上書き更新できない)
            System.getenv("KEYSTORE_FILE")?.let {
                storeFile = file(it)
                storePassword = System.getenv("KEYSTORE_PASSWORD")
                keyAlias = System.getenv("KEY_ALIAS")
                keyPassword = System.getenv("KEY_PASSWORD")
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.journeyapps:zxing-android-embedded:4.3.0")
}
