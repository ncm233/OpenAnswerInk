# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_all

base_dir = os.path.dirname(os.path.abspath(SPEC))

datas = [
    (os.path.join(base_dir, 'assets'), 'assets'),
]
binaries = []
hiddenimports = [
    'keyboard',
    'docx',
    'ctypes',
    'PyQt6',
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'httpx',
    'json',
    'uuid',
    'time',
    'threading'
]

# 收集语音转写与音频依赖库
for pkg in ['soundcard', 'faster_whisper', 'ctranslate2']:
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# 排除巨型且不相关的科学计算库，极大缩减体积并加速打包
excludes = [
    'torch', 'torchvision', 'cv2', 'pandas', 'polars',
    'scipy', 'matplotlib', 'streamlit', 'playwright',
    'altair', 'statsmodels', 'onnxruntime', 'sklearn',
    'tkinter', 'unittest', 'pytest', 'IPython', 'notebook'
]

a = Analysis(
    [os.path.join(base_dir, 'main.py')],
    pathex=[base_dir],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='OpenAnswerInk',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,  # 无黑框 GUI 模式
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(base_dir, 'assets', 'icon.ico'),
)
