"""Onde ficam perfis e findings: na pasta do código ou, no executável empacotado, na pasta do usuário.

Dentro do executável (PyInstaller) os arquivos embutidos são só leitura e somem a cada execução;
por isso, na primeira abertura, `profiles/` e `research/findings/` são copiados para a pasta de
dados do usuário e dali em diante tudo é lido e gravado lá.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIRS = ("profiles", Path("research") / "findings")


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    """Arquivos embutidos: `sys._MEIPASS` no executável, a raiz do repositório fora dele."""
    return Path(getattr(sys, "_MEIPASS", SOURCE_ROOT))


def user_data_dir(env=None, platform=None) -> Path:
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    if platform.startswith("win"):
        base = env.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "InverseEngine"
    base = env.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "inverse-engine"


def seed(src: Path, dst: Path) -> None:
    """Copia só o que falta: nunca sobrescreve perfis/findings que o usuário já tem."""
    for rel in DATA_DIRS:
        s = src / rel
        if not s.is_dir():
            continue
        for f in s.rglob("*"):
            if f.is_file():
                t = dst / rel / f.relative_to(s)
                if not t.exists():
                    t.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, t)


def data_root() -> Path:
    if not frozen():
        return SOURCE_ROOT
    root = user_data_dir()
    seed(bundle_root(), root)
    return root


DATA_ROOT = data_root()
