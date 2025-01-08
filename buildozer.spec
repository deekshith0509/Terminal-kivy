[app]
title = Terminal Emulator
package.name = terminal
package.domain = com.kivy
source.main = main.py
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,dm,ttf
requirements = python3,kivy
orientation = portrait 
icon.filename = icon.png
fullscreen = 0
version = 1.0
android.gradle_dependencies = 'com.android.support:appcompat-v7:28.0.0'  # Adding appcompat dependency for compatibility
# Android specific settings
android.archs = arm64-v8a
android.release_artifact = apk
android.accept_sdk_license = True
android.api = 33
android.sdk = 33
android.minapi = 21
android.ndk = 21e
android.permissions = MANAGE_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE, INTERNET, READ_MEDIA_IMAGES, READ_MEDIA_VIDEO, READ_MEDIA_AUDIO
android.allow_backup = True


[buildozer]
log_level = 2
warn_on_root = 1
