# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

project_root = Path.cwd().resolve()
conda_prefix = Path(sys.prefix)
library_bin = conda_prefix / 'Library' / 'bin'
qt_plugins_dir = conda_prefix / 'Library' / 'lib' / 'qt6' / 'plugins'

binaries = []
if library_bin.exists():
    binaries.extend((str(p), '.') for p in library_bin.glob('*.dll'))

datas = [
    ('config/paper_sizes.json', 'config'),
    ('assets/app.ico', 'assets'),
]

if qt_plugins_dir.exists():
    for p in qt_plugins_dir.rglob('*'):
        if p.is_file():
            rel_parent = p.relative_to(qt_plugins_dir).parent
            datas.append((str(p), str(Path('PySide6') / 'plugins' / rel_parent)))


a = Analysis(
    ['main.py'],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
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
    name='EasyPhotoPrinter',
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
    icon=str(project_root / 'assets' / 'app.ico'),
    codesign_identity=None,
    entitlements_file=None,
)
