from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import struct

try:
    from PIL import Image
except Exception:  # Pillow optional until preview is used
    Image = None

TIM_MAGIC = b"\x10\x00\x00\x00"


@dataclass
class TimInfo:
    offset: int
    bpp: int
    has_clut: bool
    width: int
    height: int
    pixel_offset: int
    palette_count: int = 0


def _psx555_to_rgba(v: int):
    r = (v & 0x1F) * 255 // 31
    g = ((v >> 5) & 0x1F) * 255 // 31
    b = ((v >> 10) & 0x1F) * 255 // 31
    stp = (v >> 15) & 1
    if v == 0:
        a = 0
    else:
        a = 128 if stp else 255
    return (r, g, b, a)


def parse_tim(data: bytes, offset: int) -> TimInfo:
    if data[offset:offset+4] != TIM_MAGIC:
        raise ValueError("Assinatura TIM não encontrada.")
    if offset + 8 > len(data):
        raise ValueError("TIM truncado.")
    flags = struct.unpack_from("<I", data, offset + 4)[0]
    mode = flags & 0x7
    has_clut = bool(flags & 0x8)
    bpp_map = {0: 4, 1: 8, 2: 16, 3: 24}
    if mode not in bpp_map:
        raise ValueError("Modo TIM não suportado.")
    bpp = bpp_map[mode]
    p = offset + 8
    palette_count = 0
    if has_clut:
        if p + 12 > len(data):
            raise ValueError("CLUT truncado.")
        clut_len, _x, _y, colors, palettes = struct.unpack_from("<IHHHH", data, p)
        palette_count = palettes
        p += clut_len
    if p + 12 > len(data):
        raise ValueError("Bloco de pixels truncado.")
    img_len, _x, _y, width_words, height = struct.unpack_from("<IHHHH", data, p)
    if bpp == 4:
        width = width_words * 4
    elif bpp == 8:
        width = width_words * 2
    elif bpp == 16:
        width = width_words
    else:
        width = (width_words * 2) // 3
    return TimInfo(offset, bpp, has_clut, width, height, p + 12, palette_count)


def scan_tims(data: bytes, max_results: int = 5000) -> list[TimInfo]:
    out = []
    pos = 0
    while len(out) < max_results:
        pos = data.find(TIM_MAGIC, pos)
        if pos < 0:
            break
        try:
            info = parse_tim(data, pos)
            if 0 < info.width <= 4096 and 0 < info.height <= 4096:
                out.append(info)
        except Exception:
            pass
        pos += 4
    return out


def decode_tim(data: bytes, offset: int, palette_index: int = 0):
    if Image is None:
        raise RuntimeError("Pillow não está instalado. Execute instalar.sh ou pip install Pillow.")
    info = parse_tim(data, offset)
    flags = struct.unpack_from("<I", data, offset + 4)[0]
    p = offset + 8
    palette = None
    if info.has_clut:
        clut_len, _x, _y, colors, palettes = struct.unpack_from("<IHHHH", data, p)
        total = colors * palettes
        raw_colors = struct.unpack_from("<" + "H" * total, data, p + 12)
        palette_index = max(0, min(palettes - 1, palette_index))
        start = palette_index * colors
        palette = [_psx555_to_rgba(v) for v in raw_colors[start:start+colors]]
        p += clut_len
    img_len, _x, _y, width_words, height = struct.unpack_from("<IHHHH", data, p)
    pix = data[p+12:p+img_len]
    w, h = info.width, info.height
    im = Image.new("RGBA", (w, h))
    pixels = []
    if info.bpp == 4:
        if palette is None:
            raise ValueError("TIM 4bpp sem CLUT.")
        for byte in pix[: (w*h + 1)//2]:
            pixels.append(palette[byte & 0x0F])
            if len(pixels) < w*h:
                pixels.append(palette[(byte >> 4) & 0x0F])
    elif info.bpp == 8:
        if palette is None:
            raise ValueError("TIM 8bpp sem CLUT.")
        pixels = [palette[b] for b in pix[:w*h]]
    elif info.bpp == 16:
        count = min(w*h, len(pix)//2)
        vals = struct.unpack_from("<" + "H"*count, pix, 0)
        pixels = [_psx555_to_rgba(v) for v in vals]
    elif info.bpp == 24:
        for i in range(0, min(len(pix), w*h*3), 3):
            pixels.append((pix[i], pix[i+1], pix[i+2], 255))
    if len(pixels) < w*h:
        pixels += [(0,0,0,0)] * (w*h-len(pixels))
    im.putdata(pixels[:w*h])
    return im, info
