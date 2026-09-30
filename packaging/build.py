"""Monta o executável com PyInstaller (o mesmo comando que o GitHub Actions usa).

    python -m pip install pyinstaller PySide6
    python packaging/build.py            # Windows: dist/InverseEngine.exe + dist/inverse-engine-cli.exe
                                         # Linux:   dist/InverseEngine/ (pasta; o AppImage é montado dela)
"""
import os
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent.parent
SEP = os.pathsep
DATA = [
    (ROOT / "profiles", "profiles"),
    (ROOT / "research" / "findings", "research/findings"),
    (ROOT / "inverse_engine" / "ui" / "themes", "inverse_engine/ui/themes"),
]
# Módulos do Qt que o aplicativo não usa: deixam o executável bem menor
EXCLUDE = ["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQuick", "PySide6.QtQml",
           "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
           "PySide6.QtPdf", "PySide6.QtSql", "PySide6.QtTest", "tkinter"]


def run(name, script, windowed, onefile):
    args = [str(script), "--name", name, "--noconfirm", "--clean",
            "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build"), "--specpath", str(ROOT / "build"), "--paths", str(ROOT)]
    args += ["--windowed" if windowed else "--console", "--onefile" if onefile else "--onedir"]
    for src, dst in DATA:
        args += ["--add-data", f"{src}{SEP}{dst}"]
    for m in EXCLUDE:
        args += ["--exclude-module", m]
    PyInstaller.__main__.run(args)


def main():
    entry = ROOT / "packaging" / "entry.py"
    if sys.platform.startswith("win"):
        run("InverseEngine", entry, windowed=True, onefile=True)
        run("inverse-engine-cli", entry, windowed=False, onefile=True)
    else:
        run("InverseEngine", entry, windowed=False, onefile=False)


if __name__ == "__main__":
    main()
