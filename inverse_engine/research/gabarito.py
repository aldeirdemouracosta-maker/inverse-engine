"""Gabarito: CSV preenchido pelo usuário (id,atributo,valor,fonte) casado com as posições do registro.

Posições onde os valores batem em ≥ N% dos registros viram proposta de finding PROVAVEL com evidência
statistical_match. O repositório não guarda texto de guias: só o CSV do usuário, na pasta do projeto.
"""
from __future__ import annotations

import csv
import io
import struct
from dataclasses import dataclass
from pathlib import Path

from inverse_engine.core.profile import TableSpec
from inverse_engine.research.findings import FindingsDB, STATES

TYPES = {"u8": ("<B", 1), "s8": ("<b", 1), "u16le": ("<H", 2), "s16le": ("<h", 2)}


@dataclass(frozen=True)
class Row:
    index: int
    attribute: str
    value: int
    source: str


@dataclass(frozen=True)
class Proposal:
    table: str
    attribute: str
    offset: int
    type: str
    matched: int
    total: int
    distinct: int
    sources: tuple[str, ...]
    existing: str | None          # finding que já cobre essa posição, se houver

    @property
    def ratio(self) -> float:
        return self.matched / self.total if self.total else 0.0

    def detail(self) -> str:
        return (f"{self.attribute}: {self.table} +0x{self.offset:X} {self.type} bate em {self.matched}/{self.total} "
                f"registros ({self.distinct} valores distintos; fonte: {', '.join(self.sources)})")


def load(text_or_path, table: TableSpec | None = None, data: bytes | None = None) -> list[Row]:
    """Lê o CSV. `id` pode ser número (10 ou 0xB6) ou o nome do item (resolvido pela matriz de nomes)."""
    text = Path(text_or_path).read_text(encoding="utf-8") if isinstance(text_or_path, Path) else str(text_or_path)
    names = {}
    if table is not None and data is not None and table.names_pointer_table is not None:
        for i in range(table.count):
            n = table.read_name(data, i)
            if n:
                names.setdefault(n.lower(), i)
    rows = []
    for k, r in enumerate(csv.DictReader(io.StringIO(text))):
        key = (r.get("id") or r.get("nome") or "").strip()
        try:
            index = int(key, 0)
        except ValueError:
            if key.lower() not in names:
                raise ValueError(f"linha {k + 2}: item {key!r} não encontrado") from None
            index = names[key.lower()]
        rows.append(Row(index, r["atributo"].strip(), int(r["valor"].strip(), 0), (r.get("fonte") or "").strip()))
    return rows


def match(table: TableSpec, data: bytes, rows: list[Row], threshold: float = 0.9, min_records: int = 3,
          findings: FindingsDB | None = None) -> list[Proposal]:
    """Para cada atributo, as posições/tipos cujo valor bate em ≥ threshold dos registros do gabarito."""
    out = []
    for attr in sorted({r.attribute for r in rows}):
        rs = [r for r in rows if r.attribute == attr]
        if len(rs) < min_records:
            continue
        distinct = len({r.value for r in rs})
        cands = []
        for type_, (fmt, size) in TYPES.items():
            for off in range(0, table.stride - size + 1):
                ok = sum(struct.unpack_from(fmt, data, table.record_offset(r.index) + off)[0] == r.value for r in rs)
                if ok / len(rs) >= threshold:
                    cands.append((ok, size, type_, off))
        # mesma posição achada como u8 e u16: fica a leitura com mais acertos; no empate, a maior (u16 também
        # confere o byte alto) e a sem sinal
        best: dict[int, tuple] = {}
        for c in sorted(cands, reverse=True):
            best.setdefault(c[3], c)
        for ok, _, type_, off in sorted(best.values(), reverse=True):
            existing = None
            for f in table.fields.values():
                if f.offset == off:
                    existing = f.finding
            out.append(Proposal(table.name, attr, off, type_, ok, len(rs), distinct,
                                tuple(sorted({r.source for r in rs if r.source})), existing))
    return out


def apply(db: FindingsDB, table: TableSpec, p: Proposal) -> dict:
    """Registra a proposta: promove o finding da posição até PROVAVEL, ou cria um novo PROVAVEL.

    Nunca passa de PROVAVEL (CONFIRMADO só com teste no jogo, portão P3). Proposta com um só valor distinto
    no gabarito vira HIPOTESE: uma coluna constante bateria com qualquer coisa.
    """
    target = "PROVAVEL" if p.distinct >= 2 else "HIPOTESE"
    ev = {"kind": "statistical_match", "detail": p.detail()}
    if p.existing and p.existing in db.findings:
        f = db.get(p.existing)
        if STATES.index(f["status"]) < STATES.index(target):
            db.set_status(p.existing, target, f"gabarito: {p.attribute}", ev)
        else:
            db.add_evidence(p.existing, ev["kind"], ev["detail"])
        return f
    same = db.find(subject=f"{table.name}.{p.attribute}", record_offset=f"0x{p.offset:X}")
    if same:
        db.add_evidence(same[0]["id"], ev["kind"], ev["detail"])
        return same[0]
    prefix = (table.finding or "R-").split("-")[0] or "R"
    return db.add_finding(prefix, f"{table.name}.{p.attribute}", p.attribute, target, [ev], file=table.file,
                          record_offset=f"0x{p.offset:X}", size=TYPES[p.type][1], type=p.type)
