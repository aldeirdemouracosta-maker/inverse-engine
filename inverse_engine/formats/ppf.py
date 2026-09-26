"""PPF 1.0 / 2.0 / 3.0: leitura, conferência do bloco e criação (PPF3, para testes e exportação)."""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

BLOCK_SIZE = 1024
BLOCK_AT = {0: 0x9320, 1: 0x80A0}  # imagetype 0 = BIN, 1 = GI
DIZ_BEGIN = b"@BEGIN_FILE_ID.DIZ"
DIZ_END = b"@END_FILE_ID.DIZ"


class PpfError(ValueError):
    pass


@dataclass
class Ppf:
    version: int
    description: str
    records: list[tuple[int, bytes]]            # (offset na imagem, bytes novos)
    image_type: int = 0
    block: bytes | None = None                   # bloco de conferência (1024 bytes), se houver
    image_size: int | None = None                # só PPF2
    undo: list[bytes] = field(default_factory=list)
    file_id: str = ""

    def check_block(self, image: bytes) -> str | None:
        """None se confere; senão, o motivo (portão P4 para continuar mesmo assim)."""
        if self.image_size is not None and self.image_size != len(image):
            return f"tamanho da imagem {len(image)} ≠ {self.image_size} esperado pelo PPF"
        if self.block is None:
            return None
        at = BLOCK_AT.get(self.image_type, 0x9320)
        if image[at:at + BLOCK_SIZE] != self.block:
            return f"bloco de conferência em 0x{at:X} não confere: o PPF foi feito para outra imagem"
        return None

    def apply_to(self, image: bytes) -> bytes:
        out = bytearray(image)
        for off, data in self.records:
            if off + len(data) > len(out):
                raise PpfError(f"registro em 0x{off:X} passa do fim da imagem")
            out[off:off + len(data)] = data
        return bytes(out)


def _strip_diz(data: bytes, start: int) -> tuple[bytes, str]:
    for trailer, fmt in ((2, "<H"), (4, "<I")):
        if len(data) >= start + len(DIZ_BEGIN) + len(DIZ_END) + trailer and \
                data[-trailer - len(DIZ_END):-trailer] == DIZ_END:
            n = struct.unpack(fmt, data[-trailer:])[0]
            begin = len(data) - trailer - len(DIZ_END) - n - len(DIZ_BEGIN)
            if begin >= start and data[begin:begin + len(DIZ_BEGIN)] == DIZ_BEGIN:
                text = data[begin + len(DIZ_BEGIN):begin + len(DIZ_BEGIN) + n]
                return data[:begin], text.decode("latin-1").strip()
    return data, ""


def parse(data: bytes) -> Ppf:
    magic = data[:5]
    if magic not in (b"PPF10", b"PPF20", b"PPF30"):
        raise PpfError("não é um arquivo PPF (assinatura PPF10/PPF20/PPF30 ausente)")
    version = int(chr(magic[3]))
    desc = data[6:56].rstrip(b"\x00 ").decode("latin-1")
    ppf = Ppf(version, desc, [])
    if version == 1:
        pos, off_fmt = 56, "<I"
        body = data
    elif version == 2:
        ppf.image_size = struct.unpack_from("<I", data, 56)[0]
        ppf.block = data[60:60 + BLOCK_SIZE]
        pos, off_fmt = 60 + BLOCK_SIZE, "<I"
        body, ppf.file_id = _strip_diz(data, pos)
    else:
        ppf.image_type, blockcheck, undo, _ = data[56:60]
        pos, off_fmt = 60, "<Q"
        if blockcheck:
            ppf.block = data[60:60 + BLOCK_SIZE]
            pos += BLOCK_SIZE
        body, ppf.file_id = _strip_diz(data, pos)
        has_undo = bool(undo)
    off_size = struct.calcsize(off_fmt)
    while pos < len(body):
        if pos + off_size + 1 > len(body):
            raise PpfError(f"registro truncado em 0x{pos:X}")
        off = struct.unpack_from(off_fmt, body, pos)[0]
        n = body[pos + off_size]
        pos += off_size + 1
        chunk = body[pos:pos + n]
        if len(chunk) != n:
            raise PpfError(f"dados do registro em 0x{pos:X} truncados")
        pos += n
        ppf.records.append((off, chunk))
        if version == 3 and has_undo:
            ppf.undo.append(body[pos:pos + n])
            pos += n
    return ppf


def build_ppf3(original: bytes, patched: bytes, description: str = "", blockcheck: bool = True,
               undo: bool = False) -> bytes:
    if len(original) != len(patched):
        raise PpfError("PPF3 aqui só cobre imagens do mesmo tamanho")
    head = b"PPF30" + b"\x02" + description.encode("latin-1")[:50].ljust(50, b" ")
    block = original[0x9320:0x9320 + BLOCK_SIZE] if blockcheck else b""
    if blockcheck and len(block) != BLOCK_SIZE:
        raise PpfError("imagem pequena demais para o bloco de conferência")
    out = bytearray(head + bytes([0, int(blockcheck), int(undo), 0]) + block)
    i, n = 0, len(original)
    while i < n:
        if original[i] == patched[i]:
            i += 1
            continue
        j = i
        while j < n and j - i < 255 and original[j] != patched[j]:
            j += 1
        out += struct.pack("<QB", i, j - i) + patched[i:j]
        if undo:
            out += original[i:j]
        i = j
    return bytes(out)
