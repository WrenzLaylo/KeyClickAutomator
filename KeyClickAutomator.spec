# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project = Path(SPECPATH)
app_data = [
    (str(project / 'qml'), 'qml'),
    (str(project / 'assets'), 'assets'),
]

analysis = Analysis(
    ['qt_app.py'],
    pathex=[],
    binaries=[],
    datas=app_data,
    hiddenimports=['pynput.keyboard._win32', 'pynput.mouse._win32', 'websocket'],
    hookspath=[str(project / 'hooks')],
    hooksconfig={},
    runtime_hooks=[],
    # PyAutoGUI imports these optional screenshot/dialog helpers behind
    # ImportError guards. KeyClick only uses its keyboard and mouse backend.
    excludes=[
        'PIL',
        '_tkinter',
        'mouseinfo',
        'pygetwindow',
        'pymsgbox',
        'pyperclip',
        'pyscreeze',
        'pytweening',
        'tkinter',
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name='KeyClickAutomator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/app.ico'],
    version='version_info.txt',
)
