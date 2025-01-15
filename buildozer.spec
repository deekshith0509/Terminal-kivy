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
# Android specific settings
android.release_artifact = apk
android.permissions = MANAGE_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE, INTERNET, READ_MEDIA_IMAGES, READ_MEDIA_VIDEO, READ_MEDIA_AUDIO
source.include_patterns = bin/*

log_level = 2

# Use a compatible Android API level
android.api = 33
android.minapi = 21

# Use specific NDK version
android.ndk = 25b

# Use specific build tools version
android.build_tools = 33.0.2

# Specify python-for-android version
p4a.branch = master
android.sdk = 33
android.accept_sdk_license = True
android.arch = arm64-v8a

# Add debug keystore settings
android.keystore = debug.keystore
android.keyalias = androiddebugkey
android.keystore_password = android
android.keyalias_password = android
[buildozer]
log_level = 2
warn_on_root = 1
