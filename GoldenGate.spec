# PyInstaller spec: builds GoldenGate.exe, which seeds demo data on first launch and
# serves the dashboard at http://localhost:8000. Build with build_exe.bat.
# Writable state goes to a "goldengate_workspace" folder next to the executable.
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hiddenimports = (
    collect_submodules("uvicorn")
    + collect_submodules("goldengate")
    + ["sqlalchemy.dialects.sqlite", "rank_bm25"]
)

datas = [
    ("corpus", "corpus"),
    ("golden", "golden"),
    ("rubrics", "rubrics"),
    ("frontend/dist", "frontend/dist"),
    ("gates.yaml", "."),
    ("goldengate/systems/prompts", "goldengate/systems/prompts"),
    ("goldengate/reports/templates", "goldengate/reports/templates"),
]
datas += collect_data_files("anthropic")

a = Analysis(
    ["goldengate/server/launcher.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PyQt5", "PySide6", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="GoldenGate",
    debug=False,
    strip=False,
    upx=False,
    console=True,
    icon=None,
)
