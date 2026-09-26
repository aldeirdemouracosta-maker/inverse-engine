"""Fixtures sintéticas: CD Mode 2 (2352 bytes/setor) com ISO9660 e um SLUS artificial.

Nada aqui vem do jogo. Os nomes e valores são inventados para teste.
Todos os setores saem com EDC/ECC corretos (formats/edc_ecc.py).
"""
from __future__ import annotations

import struct

from inverse_engine.formats import edc_ecc
from inverse_engine.formats.disc import RAW_SECTOR, SYNC, USER_SIZE, FORM2_USER_SIZE

LOAD_ADDRESS = 0x80010000


def _bcd(n: int) -> int:
    return (n // 10) << 4 | (n % 10)


def raw_sector(lba: int, payload: bytes, form2: bool = False, mode: int = 2) -> bytes:
    m, rem = divmod(lba + 150, 75 * 60)
    s, f = divmod(rem, 75)
    header = bytes([_bcd(m), _bcd(s), _bcd(f), mode])
    if mode == 1:
        body = payload.ljust(USER_SIZE, b"\x00") + b"\x00" * (RAW_SECTOR - 16 - USER_SIZE)
        return edc_ecc.compute(SYNC + header + body)
    submode = 0x20 if form2 else 0x08
    sub = bytes([0, 0, submode, 0]) * 2
    size = FORM2_USER_SIZE if form2 else USER_SIZE
    body = payload.ljust(size, b"\x00")
    sector = SYNC + header + sub + body
    return edc_ecc.compute(sector.ljust(RAW_SECTOR, b"\x00"))


def _both16(v: int) -> bytes:
    return struct.pack("<H", v) + struct.pack(">H", v)


def _both32(v: int) -> bytes:
    return struct.pack("<I", v) + struct.pack(">I", v)


def _dir_record(name: bytes, lba: int, size: int, is_dir: bool) -> bytes:
    body = (_both32(lba) + _both32(size) + bytes(7) + bytes([0x02 if is_dir else 0]) + b"\x00\x00"
            + _both16(1) + bytes([len(name)]) + name)
    if (len(body) + 2) % 2:
        body += b"\x00"  # o preenchimento conta no comprimento do registro
    return bytes([len(body) + 2, 0]) + body


class CdBuilder:
    """Monta um CD: build(files) com {'CAMINHO/NOME.EXT': bytes}; nomes em `form2` viram XA."""

    def __init__(self, volume_id: str = "INVERSE_TEST"):
        self.volume_id = volume_id

    def build(self, files: dict[str, bytes], form2: set[str] = frozenset()) -> bytes:
        tree: dict = {}
        for path, data in files.items():
            node = tree
            parts = path.split("/")
            for d in parts[:-1]:
                node = node.setdefault(d, {})
            node[parts[-1]] = data

        next_lba = [18]  # 16 = PVD, 17 = terminador
        dir_lba: dict[int, int] = {}
        file_lba: dict[str, int] = {}

        def alloc(n: int) -> int:
            lba = next_lba[0]
            next_lba[0] += n
            return lba

        def plan(node: dict, prefix: str) -> None:
            dir_lba[id(node)] = alloc(1)
            for name, v in sorted(node.items()):
                if isinstance(v, dict):
                    plan(v, prefix + name + "/")
            for name, v in sorted(node.items()):
                if not isinstance(v, dict):
                    file_lba[prefix + name] = alloc(max(1, -(-len(v) // USER_SIZE)))

        plan(tree, "")
        sectors: dict[int, bytes] = {}

        def emit(node: dict, prefix: str, parent_lba: int) -> None:
            me = dir_lba[id(node)]
            recs = _dir_record(b"\x00", me, USER_SIZE, True) + _dir_record(b"\x01", parent_lba, USER_SIZE, True)
            for name, v in sorted(node.items()):
                if isinstance(v, dict):
                    recs += _dir_record(name.encode(), dir_lba[id(v)], USER_SIZE, True)
                else:
                    recs += _dir_record((name + ";1").encode(), file_lba[prefix + name], len(v), False)
            assert len(recs) <= USER_SIZE, "fixture: diretório maior que um setor"
            sectors[me] = raw_sector(me, recs)
            for name, v in sorted(node.items()):
                if isinstance(v, dict):
                    emit(v, prefix + name + "/", me)
                else:
                    path = prefix + name
                    xa = path in form2
                    lba = file_lba[path]
                    step = USER_SIZE
                    for i in range(max(1, -(-len(v) // step))):
                        sectors[lba + i] = raw_sector(lba + i, v[i * step:(i + 1) * step], form2=xa)

        root_lba = dir_lba[id(tree)]
        emit(tree, "", root_lba)
        pvd = bytearray(USER_SIZE)
        pvd[0:6] = b"\x01CD001"
        pvd[6] = 1
        pvd[40:72] = self.volume_id.encode().ljust(32)
        pvd[80:88] = _both32(next_lba[0])
        pvd[128:132] = _both16(USER_SIZE)
        pvd[156:156 + 34] = _dir_record(b"\x00", root_lba, USER_SIZE, True)
        sectors[16] = raw_sector(16, bytes(pvd))
        sectors[17] = raw_sector(17, b"\xFFCD001\x01")
        out = bytearray()
        for lba in range(next_lba[0]):
            out += sectors.get(lba, raw_sector(lba, b""))
        return bytes(out)


def make_slus(names: dict[int, str] | None = None, table_offset: int = 0xB5C, stride: int = 22,
              count: int = 215, pointer_table: int = 0x800, values: dict[tuple[int, int], bytes] | None = None,
              size: int = 0x4000) -> bytes:
    """SLUS artificial: cabeçalho PS-X EXE, matriz de ponteiros de nomes e tabela de registros.

    `values[(id, rel_offset)] = bytes` planta valores em registros.
    """
    data = bytearray(size)
    data[:8] = b"PS-X EXE"
    struct.pack_into("<I", data, 0x10, LOAD_ADDRESS)
    struct.pack_into("<II", data, 0x18, LOAD_ADDRESS, size - 0x800)
    text_at = table_offset + stride * count + 0x10
    names = names or {}
    for i in range(count):
        name = names.get(i, f"ITEM{i:03d}").encode("ascii") + b"\x00"
        struct.pack_into("<I", data, pointer_table + 4 * i, LOAD_ADDRESS + text_at - 0x800)
        data[text_at:text_at + len(name)] = name
        text_at += len(name)
        assert text_at < size, "fixture: SLUS pequeno demais"
    for (i, rel), raw in (values or {}).items():
        start = table_offset + i * stride + rel
        data[start:start + len(raw)] = raw
    return bytes(data)
