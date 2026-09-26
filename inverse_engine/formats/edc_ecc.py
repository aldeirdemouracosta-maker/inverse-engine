"""EDC/ECC de setores de CD (ECMA-130): cálculo, conferência e regravação.

EDC: CRC-32 refletido, polinômio 0x8001801B, valor inicial 0, sem XOR final.
ECC: Reed-Solomon P (86 colunas × 24+2) e Q (52 diagonais × 43+2) sobre GF(2^8), polinômio 0x11D.
"""
from __future__ import annotations

import struct

from inverse_engine.formats.disc import RAW_SECTOR, sector_kind

EDC_POLY_REFLECTED = 0xD8018001


def _edc_table() -> list[int]:
    table = []
    for i in range(256):
        e = i
        for _ in range(8):
            e = (e >> 1) ^ (EDC_POLY_REFLECTED if e & 1 else 0)
        table.append(e)
    return table


_EDC = _edc_table()
_F = [0] * 256
_B = [0] * 256
for _i in range(256):
    _j = ((_i << 1) ^ (0x11D if _i & 0x80 else 0)) & 0xFF
    _F[_i] = _j
    _B[_i ^ _j] = _i


def edc(data: bytes, crc: int = 0) -> int:
    for b in data:
        crc = (crc >> 8) ^ _EDC[(crc ^ b) & 0xFF]
    return crc


# (início, fim exclusivo, posição do EDC) por tipo de setor
_EDC_SPAN = {"mode1": (0, 2064, 2064), "mode2_form1": (16, 2072, 2072), "mode2_form2": (16, 2348, 2348)}
P_AT, Q_AT = 0x81C, 0x8C8


def _ecc_block(sector: bytearray, major_count: int, minor_count: int, major_mult: int,
               minor_inc: int, dest: int) -> None:
    src = 0xC
    size = major_count * minor_count
    for major in range(major_count):
        index = (major >> 1) * major_mult + (major & 1)
        a = c = 0
        for _ in range(minor_count):
            t = sector[src + index]
            index += minor_inc
            if index >= size:
                index -= size
            a ^= t
            c ^= t
            a = _F[a]
        a = _B[_F[a] ^ c]
        sector[dest + major] = a
        sector[dest + major + major_count] = a ^ c


def _ecc_generate(sector: bytearray, zero_header: bool) -> None:
    saved = bytes(sector[12:16])
    if zero_header:
        sector[12:16] = b"\x00\x00\x00\x00"
    _ecc_block(sector, 86, 24, 2, 86, P_AT)
    _ecc_block(sector, 52, 43, 86, 88, Q_AT)
    sector[12:16] = saved


def compute(raw: bytes) -> bytes:
    """Setor com EDC (e ECC, quando o modo tem) recalculados. Outros modos voltam iguais."""
    kind = sector_kind(raw)
    if kind not in _EDC_SPAN or len(raw) != RAW_SECTOR:
        return bytes(raw)
    s = bytearray(raw)
    start, end, at = _EDC_SPAN[kind]
    struct.pack_into("<I", s, at, edc(s[start:end]))
    if kind == "mode1":
        s[2068:2076] = bytes(8)
        _ecc_generate(s, zero_header=False)
    elif kind == "mode2_form1":
        _ecc_generate(s, zero_header=True)
    return bytes(s)


def is_valid(raw: bytes) -> bool:
    """True se EDC/ECC conferem. Form 2 com EDC zerado é aceito (é opcional). Modos sem EDC: True."""
    kind = sector_kind(raw)
    if kind not in _EDC_SPAN:
        return True
    if kind == "mode2_form2" and raw[2348:2352] == b"\x00\x00\x00\x00":
        return True
    return compute(raw) == bytes(raw)
