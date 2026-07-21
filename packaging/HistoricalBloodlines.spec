# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path


project_dir = Path(SPECPATH).parent
source_dir = project_dir / "src"
graphviz_dir = project_dir / "vendor" / "graphviz"
example_workbook = project_dir / "examples" / "input.example.xlsx"

if not (graphviz_dir / "bin" / "dot.exe").is_file():
    raise FileNotFoundError(
        "Bundled Graphviz is missing. Run scripts/prepare_graphviz.ps1 first."
    )
if not (graphviz_dir / "bin" / "neato.exe").is_file():
    raise FileNotFoundError(
        "Bundled Graphviz does not contain bin/neato.exe."
    )


a = Analysis(
    [
        str(
            source_dir
            / "historical_bloodlines"
            / "presentation"
            / "launcher"
            / "__main__.py"
        )
    ],
    pathex=[str(source_dir)],
    binaries=[],
    datas=[
        (str(graphviz_dir), "graphviz"),
        (str(example_workbook), "examples"),
    ],
    hiddenimports=[
        "tkinter",
        "tkinter.filedialog",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HistoricalBloodlines",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory="_internal",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="HistoricalBloodlines",
)
