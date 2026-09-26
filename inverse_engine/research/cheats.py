"""Códigos GameShark a partir de campos do perfil (ferramenta de pesquisa; nunca substitui o patch final).

O endereço de RAM do registro vem de `record_ram` no perfil e só é aceito quando o finding dele está
PROVAVEL ou CONFIRMADO (ex.: emulator_breakpoint). No Modo Pesquisa dá para usar o endereço onde o
executável é carregado (PsExe), mas o código sai marcado como experimental: o jogo pode copiar a tabela
para outro lugar em tempo de execução.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from inverse_engine.core.profile import TableSpec, TYPES
from inverse_engine.formats.psexe import PsExe
from inverse_engine.research.findings import FindingsDB


class CheatError(ValueError):
    pass


@dataclass
class Cheat:
    name: str
    lines: list[str]
    experimental: bool
    address: int
    note: str = ""

    def text(self) -> str:
        return "\n".join(self.lines)


def write16(address: int, value: int) -> str:
    if address & 1:
        raise CheatError(f"escrita de 16 bits precisa de endereço par (0x{address:08X})")
    return f"80{address & 0xFFFFFF:06X} {value & 0xFFFF:04X}"


def write8(address: int, value: int) -> str:
    return f"30{address & 0xFFFFFF:06X} 00{value & 0xFF:02X}"


def if_equal16(address: int, value: int) -> str:
    return f"D0{address & 0xFFFFFF:06X} {value & 0xFFFF:04X}"


def record_address(table: TableSpec, data: bytes, findings: FindingsDB | None,
                   research_mode: bool = False) -> tuple[int, bool, str]:
    """(endereço do registro 0, experimental, origem). Recusa sem evidência fora do Modo Pesquisa."""
    if table.record_ram is not None:
        status = findings.status(table.record_ram_finding) if findings else "DESCONHECIDO"
        if status in ("PROVAVEL", "CONFIRMADO"):
            return table.record_ram, False, f"record_ram ({table.record_ram_finding} {status})"
        if not research_mode:
            raise CheatError(f"record_ram de {table.name} está {status}: sem evidência para gerar cheat")
        return table.record_ram, True, f"record_ram ({status}, experimental)"
    if not research_mode:
        raise CheatError(f"{table.name} não tem endereço de RAM com evidência (record_ram). "
                         f"No Modo Pesquisa dá para testar com o endereço do executável (experimental)")
    return PsExe.parse(data).file_to_ram(table.offset), True, "endereço de carga do executável (HIPOTESE)"


def field_cheat(table: TableSpec, data: bytes, index: int, field_name: str, value: int,
                findings: FindingsDB | None = None, research_mode: bool = False,
                only_if: int | None = None) -> Cheat:
    """Cheat que grava `value` no campo. `only_if`: só escreve se o valor atual for esse (D0, 16 bits)."""
    spec = table.fields.get(field_name)
    if spec is None:
        raise CheatError(f"{table.name}.{field_name}: campo não existe no perfil")
    try:
        struct.pack(TYPES[spec.type][0], value)
    except struct.error:
        raise CheatError(f"valor {value} não cabe em {spec.type}") from None
    base, exp, origin = record_address(table, data, findings, research_mode)
    if findings is not None and findings.status(spec.finding) not in ("PROVAVEL", "CONFIRMADO"):
        exp = True
    addr = base + index * table.stride + spec.offset
    lines = []
    if only_if is not None:
        if addr & 1:
            raise CheatError("condição D0 precisa de endereço par")
        lines.append(if_equal16(addr, only_if))
    if spec.size == 1:
        lines.append(write8(addr, value & 0xFF))
    elif spec.size == 2 and not addr & 1:
        lines.append(write16(addr, value & 0xFFFF))
    else:  # 16 bits em endereço ímpar ou 32 bits: bytes separados (little-endian)
        raw = struct.pack(TYPES[spec.type][0], value)
        if only_if is not None and len(raw) > 1:
            raise CheatError("condição D0 só vale para a próxima linha; use campo alinhado")
        lines += [write8(addr + k, b) for k, b in enumerate(raw)]
    name = f"{table.name}[{index}].{field_name} = {value}" + (" (experimental)" if exp else "")
    return Cheat(name, lines, exp, addr, origin)


def to_duckstation(cheats: list[Cheat]) -> str:
    """Arquivo .cht do DuckStation (formato de lista de códigos GameShark)."""
    out = []
    for c in cheats:
        out += [f"[{c.name}]", "Type = Gameshark", "Activation = EndlessLoop", *c.lines, ""]
    return "\n".join(out)


def to_text(cheats: list[Cheat]) -> str:
    out = []
    for c in cheats:
        out += [f"# {c.name}", f"# {c.note}", *c.lines, ""]
    return "\n".join(out)
