"""Projetos recentes e configurações da interface (~/.config/inverse_engine)."""
from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path

MAX = 10


def config_dir() -> Path:
    d = Path(os.environ.get("INVERSE_ENGINE_CONFIG") or Path.home() / ".config" / "inverse_engine")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _file() -> Path:
    return config_dir() / "recentes.json"


def load() -> list[dict]:
    try:
        return json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def add(path, name: str, profile: str | None, anchors_ok: bool | None) -> list[dict]:
    path = str(Path(path).resolve())
    items = [r for r in load() if r["caminho"] != path]
    items.insert(0, {"caminho": path, "nome": name, "perfil": profile, "ancoras_ok": anchors_ok,
                     "data": _dt.datetime.now().isoformat(timespec="minutes")})
    items = items[:MAX]
    _file().write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return items


def settings() -> dict:
    try:
        return json.loads((config_dir() / "opcoes.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"tema": "simples", "fonte": 11}


def save_settings(s: dict) -> None:
    (config_dir() / "opcoes.json").write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


def project_stats(project) -> dict:
    """Estatísticas do projeto para o painel lateral."""
    out = {"camadas": len(project.order),
           "operacoes": sum(len(c.ops) for c in project.changesets.values()),
           "tabelas": 0, "findings": {}}
    try:
        prof = project.profile()
        out["tabelas"] = len(prof.tables) if prof else 0
        f = project.findings()
        out["findings"] = f.by_status() if f else {}
    except Exception:
        pass
    return out
