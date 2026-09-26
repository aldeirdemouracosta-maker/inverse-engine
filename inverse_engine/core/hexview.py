"""Visualização em hexa (não é um editor): escritas, registros de tabela e blocos de TIM.

Linha de escrita: OFFSET (arquivo) | LBA | RAM | ORIGINAL (hex) | NOVO (hex) | CAMPO
"""
from __future__ import annotations

from dataclasses import dataclass

from inverse_engine.core.patch_stack import PatchStack
from inverse_engine.core.profile import RomProfile, TableSpec
from inverse_engine.formats.psexe import PsExe, MAGIC as PSEXE_MAGIC
from inverse_engine.formats.tim import TimInfo
from inverse_engine.research.findings import FindingsDB


@dataclass(frozen=True)
class HexRow:
    layer: str
    file: str | None
    file_offset: int | None
    lba: int | None
    ram: int | None
    original: bytes
    new: bytes
    field: str | None

    def cells(self) -> list[str]:
        return [f"0x{self.file_offset:X}" if self.file_offset is not None else "-",
                str(self.lba) if self.lba is not None else "-",
                f"0x{self.ram:08X}" if self.ram is not None else "-",
                self.original.hex(" ").upper(), self.new.hex(" ").upper(), self.field or "",
                f"{self.file or ''} [{self.layer}]"]


HEADERS = ["OFFSET", "LBA", "RAM", "ORIGINAL", "NOVO", "CAMPO", "ARQUIVO [CAMADA]"]


def _ram(stack: PatchStack, file: str | None, offset: int | None, cache: dict) -> int | None:
    if file is None or offset is None:
        return None
    if file not in cache:
        try:
            data = stack.image.read_file(file) if stack.image.disc else stack.image.data
            cache[file] = PsExe.parse(data) if data[:8] == PSEXE_MAGIC else None
        except Exception:
            cache[file] = None
    exe = cache[file]
    if exe is None or offset < 0x800:
        return None
    return exe.file_to_ram(offset)


def write_rows(stack: PatchStack, only_active: bool = True) -> list[HexRow]:
    """Uma linha por escrita (quebrada por campo do perfil quando cai numa tabela)."""
    rows = []
    cache: dict = {}
    for li, layer in enumerate(stack.layers):
        if only_active and not layer.active:
            continue
        ws, _, _ = stack.writes(li)
        for w in ws:
            k = 0
            while k < len(w.data):
                file, foff, lba = stack.locate(w.pos + k)
                label = stack.field_label(file, foff)
                j = k + 1
                while j < len(w.data):  # agrupa bytes seguidos do mesmo campo
                    f2, o2, _ = stack.locate(w.pos + j)
                    if stack.field_label(f2, o2) != label or (label is None and j - k >= 16):
                        break
                    j += 1
                if label is None and w.label and not w.label.startswith(("ppf", "bps")):
                    label = w.label
                rows.append(HexRow(layer.name, file, foff, lba, _ram(stack, file, foff, cache),
                                   stack.image.data[w.pos + k:w.pos + j], w.data[k:j], label))
                k = j
    return rows


def record_view(table: TableSpec, data: bytes, index: int, findings: FindingsDB | None = None) -> list[dict]:
    """Registro inteiro com as fronteiras dos campos; bytes sem campo aparecem como byte_0xNN."""
    rec = table.read_record(data, index)
    by_offset = {f.offset: f for f in table.fields.values()}
    out = []
    rel = 0
    while rel < table.stride:
        f = by_offset.get(rel)
        if f is not None:
            raw = rec[rel:rel + f.size]
            status = findings.status(f.finding) if findings else "?"
            out.append({"campo": f.name, "offset": rel, "tamanho": f.size, "hex": raw.hex(" ").upper(),
                        "valor": table.read_field(data, index, f.name), "estado": status})
            rel += f.size
        else:
            out.append({"campo": f"byte_0x{rel:02X}", "offset": rel, "tamanho": 1, "hex": f"{rec[rel]:02X}",
                        "valor": rec[rel], "estado": "DESCONHECIDO"})
            rel += 1
    return out


def tim_sections(info: TimInfo) -> list[tuple[str, int, int]]:
    """(nome, início, fim) relativos ao início do TIM: cabeçalho, bloco de paleta, bloco de pixels."""
    out = [("cabeçalho", 0, 8)]
    if info.clut_offset is not None:
        out.append(("paleta: cabeçalho", 8, 20))
        clut_end = info.clut_offset - info.offset + info.clut_colors * info.clut_count * 2
        out.append(("paleta: cores", 20, clut_end))
    px = info.pixel_offset - info.offset
    out.append(("pixels: cabeçalho", px - 12, px))
    out.append(("pixels", px, px + info.pixel_bytes))
    return out


def tim_changes(info: TimInfo, original: bytes, new: bytes) -> list[tuple[str, int, int]]:
    """Só as faixas alteradas, com o bloco em que caem."""
    sections = tim_sections(info)
    out = []
    i = 0
    while i < len(original):
        if original[i] == new[i]:
            i += 1
            continue
        j = i
        while j < len(original) and original[j] != new[j]:
            j += 1
        name = next((n for n, a, b in sections if a <= i < b), "?")
        out.append((name, i, j))
        i = j
    return out


def format_table(rows: list[list[str]], headers: list[str]) -> str:
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(headers)]
    line = lambda cells: " | ".join(c.ljust(w) for c, w in zip(cells, widths)).rstrip()
    return "\n".join([line(headers), "-+-".join("-" * w for w in widths)] + [line(r) for r in rows])
