"""Executável PS-X EXE: cabeçalho de 0x800 bytes e conversão arquivo ↔ RAM."""
from __future__ import annotations

import struct
from dataclasses import dataclass

MAGIC = b"PS-X EXE"
HEADER_SIZE = 0x800


@dataclass(frozen=True)
class PsExe:
    initial_pc: int
    load_address: int   # t_addr: onde o corpo (após o cabeçalho) é carregado na RAM
    body_size: int

    @classmethod
    def parse(cls, data: bytes) -> "PsExe":
        if data[:8] != MAGIC or len(data) < HEADER_SIZE:
            raise ValueError("não é um executável PS-X EXE")
        pc = struct.unpack_from("<I", data, 0x10)[0]
        t_addr, t_size = struct.unpack_from("<II", data, 0x18)
        return cls(pc, t_addr, t_size)

    def file_to_ram(self, offset: int) -> int:
        if offset < HEADER_SIZE:
            raise ValueError(f"offset 0x{offset:X} está no cabeçalho, não é carregado na RAM")
        return self.load_address + offset - HEADER_SIZE

    def ram_to_file(self, address: int) -> int:
        off = address - self.load_address + HEADER_SIZE
        if off < HEADER_SIZE:
            raise ValueError(f"endereço 0x{address:08X} fica antes do corpo do executável")
        return off
