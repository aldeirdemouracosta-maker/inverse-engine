"""Nomes de saída. Nomes de jogo têm pontos (SLUS_009.40, "Jogo (USA).bin"): nunca usar with_suffix."""
from __future__ import annotations

from pathlib import Path


def with_ext(path: str | Path, ext: str) -> Path:
    """Acrescenta a extensão ao nome inteiro: 'SLUS_009.40' + '.bps' → 'SLUS_009.40.bps'."""
    p = Path(path)
    if not ext.startswith("."):
        ext = "." + ext
    return p.with_name(p.name + ext)


def replace_ext(path: str | Path, old: str, new: str) -> Path:
    """Troca a extensão só quando ela é exatamente `old` (sem diferenciar maiúsculas)."""
    p = Path(path)
    if p.name.lower().endswith(old.lower()):
        return p.with_name(p.name[:len(p.name) - len(old)] + new)
    return with_ext(p, new)
