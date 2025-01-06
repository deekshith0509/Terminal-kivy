[app]
title = Terminal Emulator
package.name = kivy
package.domain = terminal
source.main = main.py
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,dm,ttf
requirements = python3,kivy
orientation = portrait 
icon.filename = icon.png
source.include_patterns = bin/*
fullscreen = 0
android.archs = arm64-v8a
android.release_artifact = apk
android.accept_sdk_license = True
android.api = 33
android.ndk = 25c
android.permissions = MANAGE_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE, INTERNET, READ_MEDIA_IMAGES, READ_MEDIA_VIDEO, READ_MEDIA_AUDIO
# Versioning
version = 1.0

# Debug mode
debug = 1

[buildozer]
log_level = 1
warn_on_root = 1

android.allow_backup = True
android.logcat = True
