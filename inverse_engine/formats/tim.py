"""TIM (formato de imagem da Sony): procura, exportação para PNG e reimportação com o mesmo tamanho.

Regras desta fase: o TIM nunca muda de tamanho em bytes nem de posição na VRAM.
Redesenho usa só cores da paleta; recolorir troca só a paleta e não mexe em pixels.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

from inverse_engine.formats import png as pngmod

MAGIC = b"\x10\x00\x00\x00"
BPP = {0: 4, 1: 8, 2: 16, 3: 24}
VRAM_W, VRAM_H = 1024, 512


class TimError(ValueError):
    pass


@dataclass(frozen=True)
class TimInfo:
    offset: int
    size: int                 # bytes totais do TIM
    bpp: int
    width: int                # em pixels
    height: int
    vram_pos: tuple[int, int]
    pixel_offset: int         # absoluto no arquivo
    pixel_bytes: int
    clut_pos: tuple[int, int] | None = None
    clut_colors: int = 0
    clut_count: int = 0
    clut_offset: int | None = None   # absoluto, início das cores

    def describe(self) -> str:
        s = f"TIM {self.bpp}bpp {self.width}×{self.height}, VRAM {self.vram_pos}"
        if self.clut_pos is not None:
            s += f", {self.clut_count} paleta(s) de {self.clut_colors} cores em {self.clut_pos}"
        return s


def parse(data: bytes, offset: int) -> TimInfo:
    if data[offset:offset + 4] != MAGIC:
        raise TimError("assinatura TIM ausente")
    if offset + 8 > len(data):
        raise TimError("TIM truncado")
    flags = struct.unpack_from("<I", data, offset + 4)[0]
    if flags & ~0xB:
        raise TimError("flags do TIM inválidas")
    bpp = BPP[flags & 3]
    p = offset + 8
    clut = None
    if flags & 8:
        if p + 12 > len(data):
            raise TimError("CLUT truncada")
        n, cx, cy, cw, ch = struct.unpack_from("<IHHHH", data, p)
        if cw == 0 or ch == 0 or n != 12 + cw * ch * 2 or p + n > len(data):
            raise TimError("bloco de CLUT incoerente")
        if cx + cw > VRAM_W or cy + ch > VRAM_H:
            raise TimError("CLUT fora da VRAM")
        clut = (cx, cy, cw, ch, p + 12)
        p += n
    elif bpp in (4, 8):
        raise TimError(f"TIM {bpp}bpp sem CLUT")
    if p + 12 > len(data):
        raise TimError("bloco de imagem truncado")
    n, ix, iy, iw, ih = struct.unpack_from("<IHHHH", data, p)
    if iw == 0 or ih == 0 or n != 12 + iw * ih * 2 or p + n > len(data):
        raise TimError("bloco de imagem incoerente")
    if ix + iw > VRAM_W or iy + ih > VRAM_H:
        raise TimError("imagem fora da VRAM")
    width = {4: iw * 4, 8: iw * 2, 16: iw, 24: iw * 2 // 3}[bpp]
    info = TimInfo(offset, p + n - offset, bpp, width, ih, (ix, iy), p + 12, n - 12)
    if clut:
        cx, cy, cw, ch, co = clut
        info = TimInfo(offset, info.size, bpp, width, ih, (ix, iy), p + 12, n - 12, (cx, cy), cw, ch, co)
    return info


def scan(data: bytes, limit: int = 10000) -> list[TimInfo]:
    out = []
    pos = data.find(MAGIC)
    while pos >= 0 and len(out) < limit:
        try:
            info = parse(data, pos)
            out.append(info)
            pos = data.find(MAGIC, pos + info.size)
            continue
        except TimError:
            pass
        pos = data.find(MAGIC, pos + 1)
    return out


def scan_image(image) -> list[tuple[str, TimInfo]]:
    """TIMs em todos os arquivos de dados de uma RomImage (Form 2 e pastas ignorados)."""
    out = []
    for f in image.list_files():
        if f.is_dir or f.form2:
            continue
        for info in scan(image.read_file(f.path)):
            out.append((f.path, info))
    return out


# --- cores -------------------------------------------------------------
def to_rgba(v: int) -> tuple[int, int, int, int]:
    if v == 0:
        return (0, 0, 0, 0)
    r, g, b = v & 31, (v >> 5) & 31, (v >> 10) & 31
    return (r * 255 // 31, g * 255 // 31, b * 255 // 31, 255)


def from_rgba(c: tuple[int, int, int, int], stp: bool = False) -> int:
    """RGBA → 16 bits. Transparente vira 0x0000; preto opaco recebe o bit STP (0x8000)."""
    if c[3] < 128:
        return 0
    v = (round(c[0] * 31 / 255)) | (round(c[1] * 31 / 255) << 5) | (round(c[2] * 31 / 255) << 10)
    if stp or v == 0:
        v |= 0x8000
    return v


def palette(data: bytes, info: TimInfo, index: int = 0) -> list[int]:
    if info.clut_offset is None:
        raise TimError("TIM sem paleta")
    if not 0 <= index < info.clut_count:
        raise TimError(f"paleta {index} não existe (0..{info.clut_count - 1})")
    start = info.clut_offset + index * info.clut_colors * 2
    return list(struct.unpack_from(f"<{info.clut_colors}H", data, start))


def indices(data: bytes, info: TimInfo) -> list[list[int]]:
    """Linhas de índices (4/8bpp) ou de valores 16 bits (16bpp)."""
    pix = data[info.pixel_offset:info.pixel_offset + info.pixel_bytes]
    row_bytes = info.pixel_bytes // info.height
    rows = []
    for y in range(info.height):
        line = pix[y * row_bytes:(y + 1) * row_bytes]
        if info.bpp == 4:
            rows.append([(line[x // 2] >> (4 * (x & 1))) & 15 for x in range(info.width)])
        elif info.bpp == 8:
            rows.append(list(line[:info.width]))
        elif info.bpp == 16:
            rows.append(list(struct.unpack_from(f"<{info.width}H", line)))
        else:
            raise TimError("TIM 24bpp: só exportação")
    return rows


def _pack_pixels(info: TimInfo, rows: list[list[int]], original: bytes) -> bytes:
    row_bytes = info.pixel_bytes // info.height
    out = bytearray(original)
    for y, row in enumerate(rows):
        base = y * row_bytes
        if info.bpp == 4:
            for x, v in enumerate(row):
                b = out[base + x // 2]
                out[base + x // 2] = (b & 0xF0) | v if x & 1 == 0 else (b & 0x0F) | (v << 4)
        elif info.bpp == 8:
            out[base:base + len(row)] = bytes(row)
        else:
            struct.pack_into(f"<{len(row)}H", out, base, *row)
    return bytes(out)


# --- PNG ---------------------------------------------------------------
def export_png(data: bytes, info: TimInfo, palette_index: int = 0) -> bytes:
    if info.bpp in (4, 8):
        pal = [to_rgba(v) for v in palette(data, info, palette_index)]
        return pngmod.write_indexed(info.width, info.height, indices(data, info), pal)
    if info.bpp == 16:
        rows = [[to_rgba(v) for v in r] for r in indices(data, info)]
        return pngmod.write_rgba(info.width, info.height, rows)
    pix = data[info.pixel_offset:info.pixel_offset + info.pixel_bytes]
    row_bytes = info.pixel_bytes // info.height
    rows = [[(pix[y * row_bytes + 3 * x], pix[y * row_bytes + 3 * x + 1], pix[y * row_bytes + 3 * x + 2], 255)
             for x in range(info.width)] for y in range(info.height)]
    return pngmod.write_rgba(info.width, info.height, rows)


def _check_size(img: pngmod.PngImage, info: TimInfo) -> None:
    if (img.width, img.height) != (info.width, info.height):
        raise TimError(f"PNG {img.width}×{img.height} ≠ TIM {info.width}×{info.height}: o tamanho não pode mudar")


def import_drawing(data: bytes, info: TimInfo, png_bytes: bytes, palette_index: int = 0) -> bytes:
    """Novo desenho mapeado por cor na paleta atual. Devolve o TIM inteiro (mesmo tamanho)."""
    img = pngmod.read(png_bytes)
    _check_size(img, info)
    tim = data[info.offset:info.offset + info.size]
    old_pix = data[info.pixel_offset:info.pixel_offset + info.pixel_bytes]
    old = indices(data, info)
    if info.bpp == 16:
        rows = []
        for y in range(info.height):
            row = []
            for x in range(info.width):
                c = img.rgba(x, y)
                keep = old[y][x]
                row.append(keep if to_rgba(keep) == c else from_rgba(c))
            rows.append(row)
    elif info.bpp in (4, 8):
        pal = [to_rgba(v) for v in palette(data, info, palette_index)]
        first = {}
        for i, c in enumerate(pal):
            first.setdefault(c, i)
        rows = []
        for y in range(info.height):
            row = []
            for x in range(info.width):
                c = img.rgba(x, y)
                if pal[old[y][x]] == c:
                    row.append(old[y][x])       # cor repetida na paleta: mantém o índice original
                elif c in first:
                    row.append(first[c])
                else:
                    raise TimError(f"pixel ({x},{y}) usa cor {c} que não existe na paleta {palette_index}")
            rows.append(row)
    else:
        raise TimError("TIM 24bpp não pode ser reimportado nesta fase")
    new_pix = _pack_pixels(info, rows, old_pix)
    rel = info.pixel_offset - info.offset
    return tim[:rel] + new_pix + tim[rel + len(new_pix):]


def import_colors(data: bytes, info: TimInfo, png_bytes: bytes, palette_index: int = 0) -> bytes:
    """Troca só a paleta, a partir de um PNG indexado com os mesmos índices de pixel."""
    if info.clut_offset is None:
        raise TimError("TIM sem paleta: use importação de desenho")
    img = pngmod.read(png_bytes)
    _check_size(img, info)
    if img.color_type != 3:
        raise TimError("para trocar cores, o PNG precisa ser indexado (com paleta)")
    if img.rows != indices(data, info):
        raise TimError("os pixels do PNG mudaram: recolorir não pode mexer em pixels (use importação de desenho)")
    if len(img.palette) > info.clut_colors:
        raise TimError(f"paleta do PNG tem {len(img.palette)} cores; o TIM tem {info.clut_colors}")
    old = palette(data, info, palette_index)
    new = list(old)
    for i, c in enumerate(img.palette):
        new[i] = old[i] if to_rgba(old[i]) == c else from_rgba(c)
    tim = bytearray(data[info.offset:info.offset + info.size])
    at = info.clut_offset - info.offset + palette_index * info.clut_colors * 2
    struct.pack_into(f"<{info.clut_colors}H", tim, at, *new)
    return bytes(tim)


def build(bpp: int, width: int, height: int, pixels: list[list[int]], clut: list[list[int]] | None = None,
          vram: tuple[int, int] = (320, 0), clut_pos: tuple[int, int] = (0, 480)) -> bytes:
    """Monta um TIM (usado em testes e fixtures)."""
    mode = {4: 0, 8: 1, 16: 2}[bpp]
    out = bytearray(MAGIC + struct.pack("<I", mode | (8 if clut else 0)))
    if clut:
        cw, ch = len(clut[0]), len(clut)
        out += struct.pack("<IHHHH", 12 + cw * ch * 2, clut_pos[0], clut_pos[1], cw, ch)
        for pal in clut:
            out += struct.pack(f"<{cw}H", *pal)
    words = {4: width // 4, 8: width // 2, 16: width}[bpp]
    info_stub = TimInfo(0, 0, bpp, width, height, vram, 0, words * 2 * height)
    pix = _pack_pixels(info_stub, pixels, bytes(words * 2 * height))
    out += struct.pack("<IHHHH", 12 + len(pix), vram[0], vram[1], words, height) + pix
    return bytes(out)
