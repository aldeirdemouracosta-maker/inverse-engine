"""Imagem de CD de PS1 (BIN 2352 bytes/setor) e sistema de arquivos ISO9660.

Só leitura. Expõe os dados de usuário (2048 bytes por setor Mode 2 Form 1 ou Mode 1).
Sync, cabeçalho, subcabeçalho e EDC/ECC são bytes de sistema e nunca são alvo de edição.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

RAW_SECTOR = 2352
USER_SIZE = 2048
FORM2_USER_SIZE = 2324
SYNC = b"\x00" + b"\xFF" * 10 + b"\x00"
PVD_LBA = 16

# Deslocamento dos dados de usuário dentro do setor cru, por modo.
USER_OFFSET = {"mode1": 16, "mode2_form1": 24, "mode2_form2": 24}
SUBMODE_FORM2 = 0x20


class DiscError(ValueError):
    pass


def sector_kind(raw: bytes) -> str:
    """Classifica um setor cru: mode1, mode2_form1, mode2_form2, mode0 ou unknown."""
    if raw[:12] != SYNC:
        return "unknown"
    mode = raw[15]
    if mode == 1:
        return "mode1"
    if mode == 2:
        return "mode2_form2" if raw[18] & SUBMODE_FORM2 else "mode2_form1"
    if mode == 0:
        return "mode0"
    return "unknown"


def user_range(kind: str) -> tuple[int, int]:
    """(início, tamanho) dos dados de usuário dentro do setor cru."""
    if kind == "mode2_form2":
        return USER_OFFSET[kind], FORM2_USER_SIZE
    if kind in USER_OFFSET:
        return USER_OFFSET[kind], USER_SIZE
    raise DiscError(f"setor {kind} não tem dados de usuário conhecidos")


@dataclass
class DiscFile:
    path: str            # caminho sem ';1', separado por '/', ex.: 'DATA/BATTLE.BIN'
    lba: int
    size: int
    is_dir: bool = False
    form2: bool = False  # vídeo/áudio XA: listado, nunca editado nem varrido

    @property
    def sectors(self) -> int:
        return max(1, -(-self.size // USER_SIZE)) if self.size else 0


@dataclass
class Disc:
    data: bytes = field(repr=False)
    files: dict[str, DiscFile] = field(default_factory=dict)
    volume_id: str = ""

    @property
    def sector_count(self) -> int:
        return len(self.data) // RAW_SECTOR

    def raw_sector(self, lba: int) -> bytes:
        if not 0 <= lba < self.sector_count:
            raise DiscError(f"LBA {lba} fora da imagem ({self.sector_count} setores)")
        start = lba * RAW_SECTOR
        return self.data[start:start + RAW_SECTOR]

    def kind(self, lba: int) -> str:
        return sector_kind(self.raw_sector(lba))

    def user_data(self, lba: int) -> bytes:
        raw = self.raw_sector(lba)
        start, size = user_range(sector_kind(raw))
        return raw[start:start + size]

    def bin_offset(self, lba: int, offset_in_sector: int) -> int:
        """Offset absoluto na BIN de um byte de dados de usuário."""
        start, size = user_range(self.kind(lba))
        if not 0 <= offset_in_sector < size:
            raise DiscError(f"offset {offset_in_sector} fora dos dados de usuário do setor")
        return lba * RAW_SECTOR + start + offset_in_sector

    def locate_bin_offset(self, bin_offset: int) -> tuple[int, int | None]:
        """BIN → (LBA, offset nos dados de usuário). None quando o byte é de sistema."""
        lba, pos = divmod(bin_offset, RAW_SECTOR)
        kind = self.kind(lba)
        try:
            start, size = user_range(kind)
        except DiscError:
            return lba, None
        if start <= pos < start + size:
            return lba, pos - start
        return lba, None

    def get(self, path: str) -> DiscFile:
        key = normalize_path(path)
        if key not in self.files:
            raise DiscError(f"arquivo não encontrado no CD: {path}")
        return self.files[key]

    def read_file(self, path: str) -> bytes:
        f = self.get(path)
        if f.is_dir:
            raise DiscError(f"{path} é uma pasta")
        if f.form2:
            raise DiscError(f"{path} é Form 2 (vídeo/áudio XA): tratado só como bytes crus")
        out = bytearray()
        for i in range(f.sectors):
            out += self.user_data(f.lba + i)
        return bytes(out[:f.size])

    def file_offset_to_lba(self, path: str, offset: int) -> tuple[int, int]:
        f = self.get(path)
        if not 0 <= offset < f.size:
            raise DiscError(f"offset 0x{offset:X} fora de {path} ({f.size} bytes)")
        q, r = divmod(offset, USER_SIZE)
        return f.lba + q, r

    def lba_to_file_offset(self, lba: int, offset_in_sector: int) -> tuple[str, int] | None:
        for f in self.files.values():
            if not f.is_dir and f.lba <= lba < f.lba + f.sectors:
                off = (lba - f.lba) * USER_SIZE + offset_in_sector
                if off < f.size:
                    return f.path, off
        return None


def normalize_path(path: str) -> str:
    p = path.replace("\\", "/").strip("/").upper()
    return p.split(";", 1)[0]


def looks_like_bin(data: bytes) -> bool:
    return len(data) >= RAW_SECTOR * (PVD_LBA + 1) and len(data) % RAW_SECTOR == 0 and data[:12] == SYNC


def open_disc(data: bytes) -> Disc:
    if not looks_like_bin(data):
        raise DiscError("não parece uma BIN de 2352 bytes por setor")
    disc = Disc(data)
    pvd = disc.user_data(PVD_LBA)
    if pvd[0] != 1 or pvd[1:6] != b"CD001":
        raise DiscError("descritor de volume primário ISO9660 não encontrado no setor 16")
    if struct.unpack_from("<H", pvd, 128)[0] != USER_SIZE:
        raise DiscError("tamanho de bloco lógico diferente de 2048 não suportado")
    disc.volume_id = pvd[40:72].decode("ascii", "replace").strip()
    root = _parse_record(pvd, 156)
    _walk(disc, root[0], root[1], "", set())
    return disc


def _parse_record(buf: bytes, pos: int):
    lba = struct.unpack_from("<I", buf, pos + 2)[0]
    size = struct.unpack_from("<I", buf, pos + 10)[0]
    flags = buf[pos + 25]
    name_len = buf[pos + 32]
    name = buf[pos + 33:pos + 33 + name_len]
    return lba, size, flags, name


def _walk(disc: Disc, lba: int, size: int, prefix: str, seen: set[int]) -> None:
    if lba in seen:
        raise DiscError(f"diretório em laço no LBA {lba}")
    seen.add(lba)
    for i in range(-(-size // USER_SIZE)):
        sector = disc.user_data(lba + i)
        pos = 0
        while pos < USER_SIZE:
            length = sector[pos]
            if length == 0:
                break  # registros não cruzam setor; o resto do setor é preenchimento
            rec_lba, rec_size, flags, name = _parse_record(sector, pos)
            pos += length
            if name in (b"\x00", b"\x01"):
                continue
            path = normalize_path(prefix + name.decode("ascii", "replace"))
            is_dir = bool(flags & 0x02)
            form2 = False
            if not is_dir and rec_size and rec_lba < disc.sector_count:
                form2 = disc.kind(rec_lba) == "mode2_form2"
            disc.files[path] = DiscFile(path, rec_lba, rec_size, is_dir, form2)
            if is_dir:
                _walk(disc, rec_lba, rec_size, path + "/", seen)
