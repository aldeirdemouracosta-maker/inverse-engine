"""BPS (beat): criação e aplicação com conferência de CRC32 da origem, do destino e do patch."""
from __future__ import annotations

import struct
import zlib

SOURCE_READ, TARGET_READ, SOURCE_COPY, TARGET_COPY = range(4)


class BpsError(ValueError):
    pass


def _vlq(n: int) -> bytes:
    out = bytearray()
    while True:
        x = n & 0x7F
        n >>= 7
        if n == 0:
            out.append(0x80 | x)
            return bytes(out)
        out.append(x)
        n -= 1


def _read_vlq(data: bytes, pos: int) -> tuple[int, int]:
    n, shift = 0, 1
    while True:
        if pos >= len(data):
            raise BpsError("número truncado no patch BPS")
        x = data[pos]
        pos += 1
        n += (x & 0x7F) * shift
        if x & 0x80:
            return n, pos
        shift <<= 7
        n += shift


def create(source: bytes, target: bytes, metadata: str = "") -> bytes:
    """Patch linear: SourceRead onde os bytes são iguais e na mesma posição, TargetRead onde mudam."""
    meta = metadata.encode("utf-8")
    out = bytearray(b"BPS1" + _vlq(len(source)) + _vlq(len(target)) + _vlq(len(meta)) + meta)
    i, n = 0, len(target)
    while i < n:
        same = i < len(source) and source[i] == target[i]
        j = i
        while j < n and (j < len(source) and source[j] == target[j]) == same:
            j += 1
        out += _vlq(((j - i - 1) << 2) | (SOURCE_READ if same else TARGET_READ))
        if not same:
            out += target[i:j]
        i = j
    out += struct.pack("<II", zlib.crc32(source), zlib.crc32(target))
    out += struct.pack("<I", zlib.crc32(bytes(out)))
    return bytes(out)


def apply(source: bytes, patch: bytes) -> bytes:
    if patch[:4] != b"BPS1":
        raise BpsError("não é um patch BPS")
    if len(patch) < 16:
        raise BpsError("patch BPS truncado")
    body, footer = patch[:-12], patch[-12:]
    src_crc, tgt_crc, patch_crc = struct.unpack("<III", footer)
    if zlib.crc32(patch[:-4]) != patch_crc:
        raise BpsError("CRC do patch não confere: arquivo BPS corrompido")
    if zlib.crc32(source) != src_crc:
        raise BpsError("CRC da origem não confere: o BPS foi feito para outra imagem")
    pos = 4
    src_size, pos = _read_vlq(body, pos)
    tgt_size, pos = _read_vlq(body, pos)
    meta_size, pos = _read_vlq(body, pos)
    pos += meta_size
    if src_size != len(source):
        raise BpsError("tamanho da origem não confere")
    target = bytearray()
    src_rel = tgt_rel = 0
    while pos < len(body):
        cmd, pos = _read_vlq(body, pos)
        action, length = cmd & 3, (cmd >> 2) + 1
        if action == SOURCE_READ:
            target += source[len(target):len(target) + length]
        elif action == TARGET_READ:
            target += body[pos:pos + length]
            pos += length
        else:
            d, pos = _read_vlq(body, pos)
            delta = -(d >> 1) if d & 1 else d >> 1
            if action == SOURCE_COPY:
                src_rel += delta
                target += source[src_rel:src_rel + length]
                src_rel += length
            else:
                tgt_rel += delta
                for _ in range(length):  # pode sobrepor o que está sendo escrito
                    target.append(target[tgt_rel])
                    tgt_rel += 1
    if len(target) != tgt_size:
        raise BpsError("tamanho do destino não confere")
    if zlib.crc32(bytes(target)) != tgt_crc:
        raise BpsError("CRC do destino não confere")
    return bytes(target)
