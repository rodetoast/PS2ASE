# -*- mode: python ; coding: utf-8 -*-

def validate_qt_icu(binaries):
    """Reject a same-name ICU from PATH with a different exported ABI."""
    from pathlib import Path
    import pefile
    files = {Path(name).name.lower(): source for name, source, kind in binaries}
    if 'qt6core.dll' not in files or 'icuuc.dll' not in files:
        return
    core = pefile.PE(files['qt6core.dll'])
    required = {entry.name for dependency in core.DIRECTORY_ENTRY_IMPORT
                if dependency.dll.lower() == b'icuuc.dll' for entry in dependency.imports if entry.name}
    icu = pefile.PE(files['icuuc.dll'])
    exported = {entry.name for entry in icu.DIRECTORY_ENTRY_EXPORT.symbols}
    core.close()
    icu.close()
    if not required.issubset(exported):
        raise SystemExit('Incompatible ICU DLL collected from: ' + files['icuuc.dll'] +
                         '. Build in an isolated environment with a clean PATH.')

a = Analysis(
    ['bridge_ui.py'],
    pathex=[],
    binaries=[],
    datas=[('bridge_icon.ico', '.'), ('bridge_splash.png', '.'), ('scripts', 'scripts'),
           ('assets/practice/testfile.aseprite', 'assets/practice'),
           ('assets/practice/character.png', 'assets/practice'),
           ('assets/practice/photoshop-practice.psd', 'assets/practice'),
           ('assets/practice/photoshop-parts.png', 'assets/practice'),
           ('assets/practice/aseprite-scripts-menu.png', 'assets/practice'),
           ('assets/fonts/PretendardVariable.ttf', 'assets/fonts'),
           ('assets/fonts/Pretendard-OFL.txt', 'assets/fonts')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
validate_qt_icu(a.binaries)
pyz = PYZ(a.pure)

splash = Splash(
    'bridge_splash.png',
    binaries=a.binaries,
    datas=a.datas,
    text_pos=None,
    always_on_top=False,
)

exe = EXE(
    pyz,
    a.scripts,
    splash,
    splash.binaries,
    a.binaries,
    a.datas,
    [],
    name='bridge_ui',
    version='bridge_version_info.txt',
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
    icon=['bridge_icon.ico'],
)
