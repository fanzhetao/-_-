# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all


maa_datas, maa_binaries, maa_hiddenimports = collect_all("maa")

a = Analysis(
    ["client.py"],
    pathex=[],
    binaries=maa_binaries,
    datas=maa_datas
    + [
        ("resource", "resource"),
    ],
    hiddenimports=maa_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FashionMallClient",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="FashionMallAutomation",
)
