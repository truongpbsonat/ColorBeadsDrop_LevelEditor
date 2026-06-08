# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['ball_drop_level_editor.py'],
    pathex=[],
    binaries=[],
    datas=[('Icon', 'Icon')],
    hiddenimports=['ball_drop_editor.level_tester_app', 'ball_drop_editor.level_generator_window', 'ball_drop_editor.level_generator', 'ball_drop_editor.level_tester_score', 'ball_drop_editor.color_replace_tool'],
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
    a.binaries,
    a.datas,
    [],
    name='BallDropParty_LevelEditor',
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
)
