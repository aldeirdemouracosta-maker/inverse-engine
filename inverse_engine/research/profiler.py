"""Perfilador de colunas: estatísticas de cada posição do registro em todos os registros da tabela."""
from __future__ import annotations

import struct
from dataclasses import dataclass

from inverse_engine.core.profile import TableSpec

TYPES = {"u8": ("<B", 1), "u16le": ("<H", 2)}


@dataclass(frozen=True)
class ColumnStats:
    offset: int
    type: str
    min: int
    max: int
    distinct: int
    zeros: float          # fração de registros com valor 0
    mult10: float         # fração (entre os não nulos) múltipla de 10
    mult5: float
    monotonic: float      # fração dos grupos em que a coluna não diminui (1.0 = sempre crescente no grupo)
    field: str | None     # campo do perfil nessa posição, se houver

    def notes(self) -> str:
        out = []
        if self.distinct == 1:
            out.append("constante")
        if self.mult10 >= 0.9 and self.distinct > 2:
            out.append("múltiplos de 10")
        elif self.mult5 >= 0.9 and self.distinct > 2:
            out.append("múltiplos de 5")
        if self.monotonic >= 0.9 and self.distinct > 2:
            out.append("cresce dentro dos grupos")
        if self.zeros >= 0.9:
            out.append("quase sempre 0")
        return ", ".join(out)


def values(table: TableSpec, data: bytes, offset: int, type_: str, indices) -> list[int]:
    fmt, _ = TYPES[type_]
    return [struct.unpack_from(fmt, data, table.record_offset(i) + offset)[0] for i in indices]


def _monotonic(table: TableSpec, data: bytes, offset: int, type_: str) -> float:
    groups = table.groups or [{"start": 0, "end": table.count - 1}]
    ok = total = 0
    for g in groups:
        vs = values(table, data, offset, type_, range(g["start"], g["end"] + 1))
        if len(vs) < 3:
            continue
        total += 1
        ok += all(a <= b for a, b in zip(vs, vs[1:]))
    return ok / total if total else 0.0


def profile(table: TableSpec, data: bytes, skip: set[int] = frozenset({0})) -> list[ColumnStats]:
    """Uma linha por (posição, tipo): u8 em todas as posições e u16le em todas as posições possíveis."""
    idx = [i for i in range(table.count) if i not in skip]
    by_offset = {}
    for f in table.fields.values():
        by_offset.setdefault(f.offset, f.name)
    out = []
    for type_, (_, size) in TYPES.items():
        for off in range(0, table.stride - size + 1):
            vs = values(table, data, off, type_, idx)
            nz = [v for v in vs if v]
            out.append(ColumnStats(off, type_, min(vs), max(vs), len(set(vs)),
                                   vs.count(0) / len(vs),
                                   sum(v % 10 == 0 for v in nz) / len(nz) if nz else 0.0,
                                   sum(v % 5 == 0 for v in nz) / len(nz) if nz else 0.0,
                                   _monotonic(table, data, off, type_), by_offset.get(off)))
    return out
