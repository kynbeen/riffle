# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

webview_data, webview_binaries, webview_hidden = collect_all("webview")

# 배포 빌드는 `python -m riffle.stamp_version` 이 먼저 만들어 둔다. 이 파일이 빠지면
# 설치된 앱은 깃이 없어 자기 버전을 모른다. 없을 때 hiddenimports 에 넣으면 빌드가
# 경고를 내므로, 있을 때만 넣는다.
version_stamp = ["riffle._version"] if Path("riffle/_version.py").exists() else []

desktop_a = Analysis(
    ["launch.pyw"],
    pathex=[],
    binaries=webview_binaries,
    datas=webview_data + [
        ("riffle/ui", "riffle/ui"),
        ("assets/icon.ico", "assets"),
    ],
    hiddenimports=webview_hidden + collect_submodules("pymupdf") + ["pikepdf"] + version_stamp,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter.test"],
    noarchive=False,
    optimize=1,
)

desktop_pyz = PYZ(desktop_a.pure)
desktop_exe = EXE(
    desktop_pyz,
    desktop_a.scripts,
    [],
    exclude_binaries=True,
    name="Riffle",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon="assets/icon.ico",
)
coll = COLLECT(
    desktop_exe,
    desktop_a.binaries,
    desktop_a.datas,
    strip=False,
    upx=True,
    name="Riffle",
)
