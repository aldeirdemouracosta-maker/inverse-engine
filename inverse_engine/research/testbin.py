"""BINs de teste para conferir hipóteses no emulador, e findings de gráficos.

Uma BIN de teste parte da imagem base + camadas de patch ativas (ex.: Take Turns) e altera UMA coisa.
Ela vai para <projeto>/testes/, nunca para a saída final.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from inverse_engine.core.paths import with_ext
from inverse_engine.core.patch_stack import GraphicEdit, Layer, RawEdit, PatchStack
from inverse_engine.core.project import Project
from inverse_engine.formats import tim
from inverse_engine.research.findings import FindingsDB

MAGENTA = 0x7C1F


class TestBinError(ValueError):
    pass


@dataclass
class TestBin:
    image: Path
    cue: Path | None
    description: str
    instructions: str


def _base_stack(project: Project) -> PatchStack:
    """Imagem base + só as camadas de patch ativas (sem os changesets do usuário)."""
    full = project.stack()
    st = PatchStack(full.image, full.profile, full.findings, research_mode=True)
    for layer in full.layers:
        if layer.active and layer.kind in ("ppf", "bps_import"):
            st.add(layer)
    return st


def _write(project: Project, st: PatchStack, name: str, description: str, overwrite: bool) -> TestBin:
    folder = project.folder / "testes"
    folder.mkdir(parents=True, exist_ok=True)
    img = with_ext(folder / name, ".bin" if st.image.kind == "bin" else ".exe")
    if img.exists() and not overwrite:
        raise TestBinError(f"{img} já existe (confirme a sobrescrita)")
    res = st.build(acknowledged=set(project.acknowledged))
    img.write_bytes(res.data)
    cue = None
    if st.image.kind == "bin":
        cue = with_ext(folder / name, ".cue")
        cue.write_text(f'FILE "{img.name}" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n', encoding="utf-8")
    how = (f"1. Abra {cue or img} no emulador (use um savestate da tela certa).\n"
           f"2. Compare com o jogo original: {description}.\n"
           f"3. Se a mudança apareceu, registre a evidência in_game_test no finding (portão P3 para CONFIRMADO).")
    return TestBin(img, cue, description, how)


def field_test(project: Project, file: str, offset: int, data: bytes, name: str, overwrite: bool = False) -> TestBin:
    """BIN de teste com um único trecho alterado (um campo candidato)."""
    st = _base_stack(project)
    label = st.field_label(file, offset) or f"{file}+0x{offset:X}"
    st.add(Layer("teste", "raw", edits=[RawEdit(file, offset, data)]))
    return _write(project, st, name, f"{label} = {data.hex(' ').upper()}", overwrite)


def value_test(project: Project, table: str, index: int, rel_offset: int, type_: str, value: int,
               name: str | None = None, overwrite: bool = False) -> TestBin:
    prof = project.profile()
    t = prof.table(table)
    fmt = {"u8": "<B", "s8": "<b", "u16le": "<H", "s16le": "<h", "u32le": "<I"}[type_]
    return field_test(project, t.file, t.record_offset(index) + rel_offset, struct.pack(fmt, value),
                      name or f"teste {table}[{index}]+0x{rel_offset:X}={value}", overwrite)


def recolor_test(project: Project, file: str, tim_offset: int, overwrite: bool = False) -> TestBin:
    """Troca todas as cores não transparentes da paleta por magenta, para achar o sprite no emulador."""
    image = project.open_image()
    data = image.read_file(file) if image.disc else image.data
    info = tim.parse(data, tim_offset)
    if info.clut_offset is None:
        raise TestBinError("TIM sem paleta: o teste de recolorir precisa de CLUT")
    new = bytearray(data[info.offset:info.offset + info.size])
    at = info.clut_offset - info.offset
    for k in range(info.clut_colors * info.clut_count):
        v = struct.unpack_from("<H", new, at + 2 * k)[0]
        if v != 0:
            struct.pack_into("<H", new, at + 2 * k, MAGENTA)
    st = _base_stack(project)
    st.add(Layer("teste", "graphics", edits=[GraphicEdit(file, info.offset, data[info.offset:info.offset + info.size],
                                                         bytes(new), "cores", 0, info.clut_pos)]))
    return _write(project, st, f"teste magenta {Path(file).name} 0x{info.offset:X}",
                  f"o sprite de {file} 0x{info.offset:X} aparece magenta", overwrite)


def register_tims(db: FindingsDB, found: list[tuple[str, tim.TimInfo]]) -> list[dict]:
    """Um finding G-xxxx HIPOTESE por TIM ainda não registrado (o que a imagem representa é desconhecido)."""
    new = []
    for path, info in found:
        if db.find(subject="graphics.tim", file=path, offset=f"0x{info.offset:X}"):
            continue
        new.append(db.add_finding("G", "graphics.tim", "o que a imagem representa ainda não foi testado",
                                  "HIPOTESE", [{"kind": "tim_scan", "detail": "cabeçalho TIM coerente"}],
                                  file=path, offset=f"0x{info.offset:X}", size=info.size, type=info.describe()))
    if not found and not db.find(subject="graphics.characters"):
        new.append(db.add_finding("G", "graphics.characters", "sprites de personagem", "DESCONHECIDO",
                                  [{"kind": "tim_scan", "detail": "sem TIM solto: provável formato comprimido "
                                                                  "(fase Ghidra, descompressor)"}]))
    return new
