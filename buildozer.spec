[app]

# Datos básicos
title = Planilla de Caja
package.name = appazar
package.domain = ar.com
source.dir = .
source.include_exts = py,kv,png,jpg,jpeg,atlas
source.exclude_dirs = tests,bin,.git,.buildozer,__pycache__
version = 1.0.0
requirements = python3,kivy
p4a.branch = develop
orientation = portrait
fullscreen = 0

# Android
android.api = 36
android.minapi = 24
android.ndk = 28c
android.archs = arm64-v8a
android.accept_sdk_license = True

# Registro más detallado para facilitar el diagnóstico
[buildozer]
log_level = 2
warn_on_root = 0
