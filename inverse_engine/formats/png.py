"""PNG só com zlib/struct: escrita (indexado ou RGBA) e leitura (indexado, RGB, RGBA; 8 bits ou menos)."""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

SIGNATURE = b"\x89PNG\r\n\x1a\n"


class PngError(ValueError):
    pass


@dataclass
class PngImage:
    width: int
    height: int
    color_type: int                      # 3 indexado, 2 RGB, 6 RGBA
    rows: list[list]                     # índice (tipo 3) ou tupla RGBA
    palette: list[tuple[int, int, int, int]] | None = None

    def rgba(self, x: int, y: int) -> tuple[int, int, int, int]:
        v = self.rows[y][x]
        if self.color_type == 3:
            if v >= len(self.palette):
                raise PngError(f"pixel ({x},{y}) usa índice {v} fora da paleta do PNG")
            return self.palette[v]
        return v


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def write_indexed(width: int, height: int, rows: list[list[int]], palette: list[tuple[int, int, int, int]]) -> bytes:
    if not 1 <= len(palette) <= 256:
        raise PngError("paleta PNG precisa de 1 a 256 cores")
    raw = b"".join(b"\x00" + bytes(r) for r in rows)
    plte = b"".join(bytes(c[:3]) for c in palette)
    trns = bytes(c[3] for c in palette)
    return (SIGNATURE + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 3, 0, 0, 0))
            + _chunk(b"PLTE", plte) + _chunk(b"tRNS", trns)
            + _chunk(b"IDAT", zlib.compress(raw, 9)) + _chunk(b"IEND", b""))


def write_rgba(width: int, height: int, rows: list[list[tuple[int, int, int, int]]]) -> bytes:
    raw = b"".join(b"\x00" + b"".join(bytes(p) for p in r) for r in rows)
    return (SIGNATURE + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(raw, 9)) + _chunk(b"IEND", b""))


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def read(data: bytes) -> PngImage:
    if data[:8] != SIGNATURE:
        raise PngError("não é um arquivo PNG")
    pos = 8
    ihdr = None
    plte = trns = None
    idat = bytearray()
    while pos + 8 <= len(data):
        n, kind = struct.unpack_from(">I4s", data, pos)
        body = data[pos + 8:pos + 8 + n]
        if zlib.crc32(kind + body) != struct.unpack_from(">I", data, pos + 8 + n)[0]:
            raise PngError(f"CRC do bloco {kind.decode('latin-1')} não confere")
        pos += 12 + n
        if kind == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            plte = body
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
    if ihdr is None:
        raise PngError("PNG sem cabeçalho IHDR")
    w, h, depth, ctype, _, _, interlace = ihdr
    if interlace:
        raise PngError("PNG entrelaçado não é aceito: salve sem entrelaçamento")
    if ctype == 3:
        if depth not in (1, 2, 4, 8) or plte is None:
            raise PngError("PNG indexado inválido")
        channels, bits = 1, depth
    elif ctype in (2, 6) and depth == 8:
        channels, bits = (3 if ctype == 2 else 4), 8
    else:
        raise PngError("tipo de PNG não suportado: use indexado ou RGB/RGBA de 8 bits")
    bpp = max(1, channels * bits // 8)
    stride = (w * channels * bits + 7) // 8
    raw = zlib.decompress(bytes(idat))
    if len(raw) < (stride + 1) * h:
        raise PngError("dados de imagem do PNG truncados")
    prev = bytearray(stride)
    rows = []
    for y in range(h):
        f = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if f == 1:
                line[i] = (line[i] + a) & 0xFF
            elif f == 2:
                line[i] = (line[i] + b) & 0xFF
            elif f == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 0xFF
            elif f == 4:
                line[i] = (line[i] + _paeth(a, b, c)) & 0xFF
            elif f != 0:
                raise PngError(f"filtro PNG desconhecido: {f}")
        prev = line
        if ctype == 3:
            per = 8 // bits
            mask = (1 << bits) - 1
            row = [(line[x // per] >> ((per - 1 - x % per) * bits)) & mask for x in range(w)]
        elif ctype == 2:
            row = [(line[3 * x], line[3 * x + 1], line[3 * x + 2], 255) for x in range(w)]
        else:
            row = [tuple(line[4 * x:4 * x + 4]) for x in range(w)]
        rows.append(row)
    palette = None
    if ctype == 3:
        palette = [(plte[3 * i], plte[3 * i + 1], plte[3 * i + 2],
                    trns[i] if trns and i < len(trns) else 255) for i in range(len(plte) // 3)]
    return PngImage(w, h, ctype, rows, palette)
