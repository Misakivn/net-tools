# -*- mode: python ; coding: utf-8 -*-
# Đóng gói:  python -m PyInstaller --noconfirm --clean NetTools.spec
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("customtkinter") + [("assets/icon.ico", "assets"), ("assets/icon.png", "assets")]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=["pystray._win32", "PIL._tkinter_finder"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "numpy", "pandas", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="NetTools",
    icon="assets/icon.ico",
    version="version_info.txt",
    debug=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    uac_admin=True,
)
