"""Nomes por matriz de ponteiros: análise, hipóteses de alinhamento e edição de texto sem realocar.

A análise nunca grava nada. O alinhamento (shift) só é gravado no perfil com confirmação explícita do
usuário depois de ver as amostras, com evidência registrada no finding dos nomes.
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

from inverse_engine.core.profile import TableSpec, NAME_MAX
from inverse_engine.formats.psexe import PsExe
from inverse_engine.research.findings import FindingsDB


class NamesError(ValueError):
    pass


@dataclass(frozen=True)
class PointerEntry:
    index: int
    pointer: int
    file_offset: int | None
    name: str | None          # None = ponteiro fora da faixa de textos ou texto inválido


@dataclass
class Hypothesis:
    shift: int
    description: str
    samples: list[tuple[int, str | None]]
    records_without_name: list[int]


@dataclass
class NamesReport:
    table: str
    pointer_table: int
    pointer_count: int
    record_count: int
    entries: list[PointerEntry]
    runs: list[tuple[int, int, int]]            # (índice inicial, offset do ponteiro, quantidade) de válidos
    invalid: list[int]
    hypotheses: list[Hypothesis] = field(default_factory=list)

    @property
    def divergence(self) -> int:
        return self.pointer_count - self.record_count

    def summary(self) -> str:
        runs = ", ".join(f"0x{off:X} ({n})" for _, off, n in self.runs)
        s = (f"{self.table}: {self.pointer_count} ponteiros × {self.record_count} registros "
             f"(divergência {self.divergence:+d}); sequências válidas: {runs or 'nenhuma'}")
        if self.invalid:
            s += f"; entradas inválidas: {', '.join(map(str, self.invalid))}"
        return s


def analyze(table: TableSpec, data: bytes, samples: int = 6) -> NamesReport:
    if table.names_pointer_table is None:
        raise NamesError(f"{table.name}: o perfil não indica matriz de ponteiros de nomes")
    exe = PsExe.parse(data)
    pt = table.names_pointer_table
    # Matriz imediatamente antes da tabela (padrão armas/habilidades/armaduras): conta pelos bytes entre as duas.
    n = (table.offset - pt) // 4 if pt < table.offset else table.count
    entries = []
    for i in range(n):
        ptr = struct.unpack_from("<I", data, pt + 4 * i)[0]
        try:
            off = exe.ram_to_file(ptr)
            off = off if 0 <= off < len(data) else None
        except ValueError:
            off = None
        hit = table.name_at(data, off) if off is not None else None
        entries.append(PointerEntry(i, ptr, off, hit[2] if hit else None))
    runs, start = [], None
    for e in entries + [PointerEntry(n, 0, None, None)]:
        if e.name is not None and start is None:
            start = e.index
        elif e.name is None and start is not None:
            runs.append((start, pt + 4 * start, e.index - start))
            start = None
    rep = NamesReport(table.name, pt, n, table.count, entries, runs, [e.index for e in entries if e.name is None])
    shifts = [0] if rep.divergence <= 0 else list(range(rep.divergence + 1))
    for sh in shifts:
        names = [(i, entries[i + sh].name if i + sh < n else None) for i in range(table.count)]
        missing = [i for i, nm in names if nm is None]
        desc = {0: "registro i ↔ ponteiro i (sobra o último ponteiro)" if rep.divergence > 0 else "registro i ↔ ponteiro i"}
        rep.hypotheses.append(Hypothesis(sh, desc.get(sh, f"registro i ↔ ponteiro i+{sh} (o primeiro ponteiro é de outra coisa)"),
                                         names[:samples] + names[-2:], missing))
    return rep


def confirm_shift(profile_path: str | Path, table: str, shift: int, db: FindingsDB | None, evidence: str,
                  confirmed: bool = False) -> None:
    """Grava o alinhamento no perfil. Exige confirmed=True (o usuário conferiu as amostras) e evidência."""
    if not confirmed:
        raise NamesError("gravar o alinhamento dos nomes exige a confirmação do usuário (conferir as amostras)")
    if not evidence.strip():
        raise NamesError("descreva a evidência (ex.: 'nomes 0..5 conferidos no menu do jogo')")
    path = Path(profile_path)
    d = json.loads(path.read_text(encoding="utf-8"))
    names = d["tables"][table].setdefault("names", {})
    names["shift"] = shift
    path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fid = names.get("finding")
    if db is not None and fid in db.findings:
        db.add_evidence(fid, "static_values", f"alinhamento dos nomes: shift {shift}; {evidence}")
        db.save()


def encode_name(table: TableSpec, data: bytes, index: int, text: str,
                pad: bytes | None = None) -> tuple[int, bytes, bytes]:
    """(offset, bytes antigos, bytes novos) para trocar o nome no mesmo espaço.

    Texto maior é recusado (exigiria realocar e ajustar ponteiros: fase de tradução). Nome solto termina em NUL:
    o menor é completado com NUL. Nome dentro de um texto com campos ("…|Nome|…"): um NUL cortaria o resto do
    texto, então o menor só é aceito com `pad` explícito (ex.: espaços, no Modo Pesquisa, experimental).
    """
    slot = table.name_slot(data, index)
    if slot is None:
        raise NamesError(f"{table.name}[{index}]: nome não resolvido pela matriz de ponteiros")
    off, size = slot
    try:
        raw = text.encode("ascii")
    except UnicodeEncodeError:
        raise NamesError("só texto ASCII nesta fase (a tabela de caracteres do jogo ainda não foi mapeada)") from None
    if not raw:
        raise NamesError("nome vazio não é permitido")
    if table.names_separator and table.names_separator.encode("ascii") in raw:
        raise NamesError(f"o nome não pode conter o separador {table.names_separator!r}")
    if len(raw) > size:
        raise NamesError(f"'{text}' tem {len(raw)} bytes; o espaço original tem {size}. Texto maior exige realocar "
                         f"e ajustar ponteiros (fase de tradução)")
    if len(raw) < size:
        if table.names_separator and pad is None:
            raise NamesError(f"'{text}' tem {len(raw)} bytes e o nome original {size}: neste texto com campos o nome "
                             f"precisa ter o mesmo tamanho (no Modo Pesquisa dá para completar com espaços, "
                             f"experimental)")
        raw += (pad or b"\x00") * (size - len(raw))
    return off, data[off:off + size], raw
