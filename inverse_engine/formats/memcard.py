"""Memory card de PS1 (.mcr/.mcd, 128 KiB): listar saves, ícone, exportar/importar save (.mcs).

Estrutura (psx-spx): 16 blocos de 8 KiB (64 quadros de 128 bytes). Bloco 0 = cabeçalho "MC" e diretório
(quadros 1–15, um por bloco de dados); o último byte de cada quadro é o XOR dos 127 anteriores.
O primeiro bloco de cada save começa com "SC" (título Shift-JIS, paleta e 1–3 quadros de ícone 16×16 4bpp).
"""
from __future__ import annotations

import struct
import unicodedata
from dataclasses import dataclass

from inverse_engine.formats import png
from inverse_engine.formats.tim import to_rgba

CARD_SIZE = 128 * 1024
BLOCK = 8192
FRAME = 128
FIRST, MIDDLE, LAST, FREE = 0x51, 0x52, 0x53, 0xA0
DELETED = (0xA1, 0xA2, 0xA3)


class MemCardError(ValueError):
    pass


def checksum(frame: bytes) -> int:
    x = 0
    for b in frame[:127]:
        x ^= b
    return x


def _seal(frame: bytearray) -> bytearray:
    frame[127] = checksum(frame)
    return frame


@dataclass
class Save:
    slot: int                 # 0–14 (bloco de dados slot+1)
    name: str                 # nome do arquivo no diretório (ex.: BASLUS-00940…)
    size: int
    blocks: list[int]         # slots em ordem
    title: str
    icon_frames: int
    palette: list[int]
    checksum_ok: bool


class MemCard:
    def __init__(self, data: bytes):
        if len(data) != CARD_SIZE:
            raise MemCardError(f"memory card precisa ter {CARD_SIZE} bytes (tem {len(data)})")
        if data[:2] != b"MC":
            raise MemCardError("cabeçalho 'MC' ausente: não é um memory card de PS1 em formato cru")
        self.data = bytearray(data)

    @classmethod
    def blank(cls) -> "MemCard":
        d = bytearray(CARD_SIZE)
        f0 = bytearray(FRAME)
        f0[:2] = b"MC"
        d[0:FRAME] = _seal(f0)
        for i in range(1, 16):
            f = bytearray(FRAME)
            struct.pack_into("<IIH", f, 0, FREE, 0, 0xFFFF)
            d[i * FRAME:(i + 1) * FRAME] = _seal(f)
        for i in range(16, 36):  # lista de setores defeituosos: vazia
            f = bytearray(FRAME)
            struct.pack_into("<IIH", f, 0, 0xFFFFFFFF, 0, 0xFFFF)
            d[i * FRAME:(i + 1) * FRAME] = _seal(f)
        d[63 * FRAME:64 * FRAME] = d[0:FRAME]  # quadro de teste de escrita = cópia do quadro 0
        return cls(bytes(d))

    # --- diretório ------------------------------------------------------
    def dir_frame(self, slot: int) -> bytearray:
        return self.data[(slot + 1) * FRAME:(slot + 2) * FRAME]

    def _state(self, slot: int) -> int:
        return struct.unpack_from("<I", self.data, (slot + 1) * FRAME)[0]

    def bad_checksums(self) -> list[int]:
        """Quadros do bloco 0 (cabeçalho e diretório) com checksum errado."""
        return [i for i in range(0, 16) if checksum(self.data[i * FRAME:(i + 1) * FRAME]) != self.data[i * FRAME + 127]]

    def saves(self) -> list[Save]:
        out = []
        for slot in range(15):
            if self._state(slot) != FIRST:
                continue
            f = self.dir_frame(slot)
            size = struct.unpack_from("<I", f, 4)[0]
            name = f[0x0A:0x1F].split(b"\x00", 1)[0].decode("ascii", "replace")
            blocks, cur, seen = [slot], struct.unpack_from("<H", f, 8)[0], {slot}
            while cur != 0xFFFF:
                if cur > 14 or cur in seen:
                    raise MemCardError(f"save {name}: encadeamento de blocos inválido")
                blocks.append(cur)
                seen.add(cur)
                cur = struct.unpack_from("<H", self.data, (cur + 1) * FRAME + 8)[0]
            head = self.block(slot)
            title, frames, pal = "", 0, []
            if head[:2] == b"SC":
                title = unicodedata.normalize("NFKC", head[4:0x44].split(b"\x00", 1)[0]
                                              .decode("shift_jis", "replace")).strip()
                frames = {0x11: 1, 0x12: 2, 0x13: 3}.get(head[2], 0)
                pal = list(struct.unpack_from("<16H", head, 0x60))
            ok = all(checksum(self.dir_frame(b)) == self.dir_frame(b)[127] for b in blocks)
            out.append(Save(slot, name, size, blocks, title, frames, pal, ok))
        return out

    def free_slots(self) -> list[int]:
        return [s for s in range(15) if self._state(s) == FREE or self._state(s) in DELETED]

    def block(self, slot: int) -> bytes:
        start = (slot + 1) * BLOCK
        return bytes(self.data[start:start + BLOCK])

    # --- exportar / importar ----------------------------------------------
    def export_mcs(self, save: Save) -> bytes:
        """Save avulso .mcs: quadro de diretório (128 bytes) + blocos."""
        f = bytearray(self.dir_frame(save.slot))
        struct.pack_into("<H", f, 8, 0xFFFF)
        return bytes(_seal(f)) + b"".join(self.block(b) for b in save.blocks)

    def import_mcs(self, mcs: bytes) -> Save:
        if len(mcs) < FRAME + BLOCK or (len(mcs) - FRAME) % BLOCK:
            raise MemCardError("arquivo .mcs com tamanho inválido")
        head = mcs[:FRAME]
        if struct.unpack_from("<I", head)[0] != FIRST:
            raise MemCardError(".mcs sem quadro de diretório de início de save")
        name = head[0x0A:0x1F].split(b"\x00", 1)[0]
        if any(s.name.encode() == name for s in self.saves()):
            raise MemCardError(f"já existe um save chamado {name.decode()} neste cartão")
        n = (len(mcs) - FRAME) // BLOCK
        free = self.free_slots()
        if len(free) < n:
            raise MemCardError(f"o save precisa de {n} bloco(s); o cartão tem {len(free)} livre(s)")
        slots = free[:n]
        size = struct.unpack_from("<I", head, 4)[0] or n * BLOCK
        for k, slot in enumerate(slots):
            f = bytearray(FRAME)
            state = FIRST if k == 0 else (LAST if k == n - 1 else MIDDLE)
            nxt = slots[k + 1] if k < n - 1 else 0xFFFF
            struct.pack_into("<IIH", f, 0, state, size if k == 0 else 0, nxt)
            if k == 0:
                f[0x0A:0x0A + len(name)] = name
            self.data[(slot + 1) * FRAME:(slot + 2) * FRAME] = _seal(f)
            start = (slot + 1) * BLOCK
            self.data[start:start + BLOCK] = mcs[FRAME + k * BLOCK:FRAME + (k + 1) * BLOCK]
        return next(s for s in self.saves() if s.slot == slots[0])

    def icon_png(self, save: Save, frame: int = 0) -> bytes:
        if save.icon_frames == 0:
            raise MemCardError("save sem ícone")
        pix = self.block(save.slot)[FRAME * (1 + frame):FRAME * (2 + frame)]
        rows = [[(pix[y * 8 + x // 2] >> (4 * (x & 1))) & 15 for x in range(16)] for y in range(16)]
        return png.write_indexed(16, 16, rows, [to_rgba(c) for c in save.palette])

    def to_bytes(self) -> bytes:
        return bytes(self.data)
