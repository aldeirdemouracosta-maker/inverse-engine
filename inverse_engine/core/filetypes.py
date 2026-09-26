"""Tipo de arquivo pelo conteúdo (não pela extensão)."""
from __future__ import annotations

import struct

from inverse_engine.formats import tim
from inverse_engine.formats.psexe import MAGIC as PSEXE_MAGIC


def detect(data: bytes, form2: bool = False, is_dir: bool = False) -> str:
    if is_dir:
        return "pasta"
    if form2:
        return "STR/XA (Form 2)"
    if data[:8] == PSEXE_MAGIC:
        return "PS-EXE"
    if data[:4] == tim.MAGIC:
        try:
            tim.parse(data, 0)
            return "TIM"
        except tim.TimError:
            pass
    if len(data) >= 4 and struct.unpack_from("<I", data)[0] == 0x41:
        return "TMD"
    if data[:4] == b"pBAV":
        return "VAB"
    if data[:4] == b"BOOT" or b"BOOT" in data[:64] and data[:64].isascii():
        return "SYSTEM.CNF"
    if data and all(32 <= b < 127 or b in (9, 10, 13) for b in data[:256]):
        return "texto"
    if tim.scan(data, limit=1):
        return "contém TIM"
    return "desconhecido"
