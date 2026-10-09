# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['xlsx_report']
hiddenimports += collect_submodules('pyodbc')


a = Analysis(
    ['server.py'],
    pathex=[],
    binaries=[],
    datas=[('build_web/index.html', '.'), ('build_web/app.js', '.'), ('build_web/app.css', '.'), ('build_web/vendor', 'vendor'), ('install_driver.ps1', '.'), ('manifest.json', '.'), ('icon.svg', '.'), ('build_web/assets', 'assets'), ('version.txt', '.')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['IPython', 'matplotlib', 'matplotlib_inline', 'numpy', 'pandas', 'PIL', 'win32evtlog', 'win32evtlogutil', 'win32api', 'win32con', 'pywintypes'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='iPOS_Ledger_Studio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt',
    icon=['icon.ico'],
)
