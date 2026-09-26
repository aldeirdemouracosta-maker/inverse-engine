"""PatchStack: imagem base + pilha ordenada de camadas, detector de conflitos e montagem da saída.

Toda camada é normalizada para escritas em dados de usuário. A saída é sempre reconstruída a partir
do original, aplicando as camadas ativas em ordem (a posterior vence). EDC/ECC é conferido no
original e recalculado uma vez, no fim, só nos setores tocados.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from inverse_engine.core.profile import RomProfile, TYPES
from inverse_engine.core.rom_image import RomImage
from inverse_engine.formats import edc_ecc
from inverse_engine.formats.disc import RAW_SECTOR
from inverse_engine.formats.ppf import Ppf
from inverse_engine.research.findings import FindingsDB


class PatchError(ValueError):
    pass


# --- operações das camadas ---------------------------------------------
@dataclass(frozen=True)
class FieldEdit:
    table: str
    index: int
    field: str
    value: int

    @property
    def target(self) -> str:
        return f"{self.table}[{self.index}].{self.field}"


@dataclass(frozen=True)
class RawEdit:
    file: str
    offset: int
    data: bytes


@dataclass(frozen=True)
class GraphicEdit:
    file: str
    offset: int                      # início do TIM no arquivo
    original: bytes                  # TIM original inteiro
    new: bytes                       # TIM novo (mesmo tamanho)
    kind: str                        # "desenho" | "cores"
    palette_index: int = 0
    clut_pos: tuple[int, int] | None = None

    def __post_init__(self):
        if len(self.original) != len(self.new):
            raise PatchError("gráfico mudou de tamanho: não permitido nesta fase")
        if self.kind not in ("desenho", "cores"):
            raise PatchError(f"tipo de gráfico inválido: {self.kind}")


@dataclass
class Layer:
    name: str
    kind: str                                   # ppf | bps_import | changeset | graphics | raw
    active: bool = True
    ppf: Ppf | None = None
    ppf_block_acknowledged: bool = False        # P4: aplicar mesmo com bloco que não confere
    bps_target: bytes | None = None             # bps_import: imagem inteira resultante
    edits: list = field(default_factory=list)   # FieldEdit | RawEdit | GraphicEdit


@dataclass(frozen=True)
class Write:
    layer: int
    item: int
    pos: int              # BIN: offset absoluto de dado de usuário; avulso: offset no arquivo
    data: bytes
    label: str            # campo do perfil ou descrição


@dataclass(frozen=True)
class Conflict:
    kind: str             # CONFLITO | REDUNDANTE | INTEGRIDADE | PALETA_COMPARTILHADA
    layers: tuple[str, ...]
    detail: str
    file: str | None = None
    file_range: tuple[int, int] | None = None   # [início, fim) no arquivo
    lba_range: tuple[int, int] | None = None    # LBA inicial e final
    target: str | None = None

    @property
    def id(self) -> str:
        return f"{self.kind}:{'+'.join(self.layers)}:{self.file}:{self.file_range}"

    @property
    def needs_ack(self) -> bool:
        return self.kind == "CONFLITO"


@dataclass
class BuildResult:
    data: bytes
    touched_sectors: list[int]
    system_bytes_ignored: int
    conflicts: list[Conflict]
    experimental: list[str]


class PatchStack:
    def __init__(self, image: RomImage, profile: RomProfile | None = None,
                 findings: FindingsDB | None = None, research_mode: bool = False):
        self.image = image
        self.profile = profile
        self.findings = findings
        self.research_mode = research_mode
        self.layers: list[Layer] = []

    def add(self, layer: Layer) -> Layer:
        self.layers.append(layer)
        return layer

    # --- endereçamento ---------------------------------------------------
    def _file_pos(self, file: str, offset: int, n: int) -> list[tuple[int, int]]:
        """Faixas [pos, tamanho] na imagem para n bytes de um arquivo (quebra por setor)."""
        if self.image.disc is None:
            if not self._is_single_file(file):
                raise PatchError(f"a imagem aberta não contém {file}")
            if offset < 0 or offset + n > len(self.image.data):
                raise PatchError(f"escrita fora do arquivo: 0x{offset:X}+{n}")
            return [(offset, n)]
        f = self.image.disc.get(file)
        if f.form2:
            raise PatchError(f"{file} é Form 2: não editável")
        if offset < 0 or offset + n > f.size:
            raise PatchError(f"escrita fora de {file}: 0x{offset:X}+{n} (tamanho {f.size})")
        out = []
        while n:
            lba, pos = self.image.disc.file_offset_to_lba(file, offset)
            take = min(n, 2048 - pos)
            out.append((self.image.disc.bin_offset(lba, pos), take))
            offset += take
            n -= take
        return out

    def _is_single_file(self, file: str) -> bool:
        return self.image.has_file(file) or (self.profile is not None and file == self.profile.executable)

    def locate(self, pos: int) -> tuple[str | None, int | None, int | None]:
        """Posição na imagem → (arquivo, offset no arquivo, LBA)."""
        if self.image.disc is None:
            return (self.profile.executable if self.profile else self.image.list_files()[0].path), pos, None
        lba, in_sector = self.image.disc.locate_bin_offset(pos)
        if in_sector is None:
            return None, None, lba
        hit = self.image.disc.lba_to_file_offset(lba, in_sector)
        return (hit[0], hit[1], lba) if hit else (None, None, lba)

    def field_label(self, file: str | None, offset: int | None) -> str | None:
        if self.profile is None or file is None or offset is None:
            return None
        for t in self.profile.tables.values():
            if t.file.upper() != file.upper() or not t.offset <= offset < t.end:
                continue
            idx, rel = divmod(offset - t.offset, t.stride)
            for f in t.fields.values():
                if f.offset <= rel < f.offset + f.size:
                    return f"{t.name}[{idx}].{f.name}"
            return f"{t.name}[{idx}]+0x{rel:X}"
        return None

    # --- normalização ----------------------------------------------------
    def writes(self, layer_index: int) -> tuple[list[Write], int, list[str]]:
        """(escritas em dados de usuário, bytes de sistema ignorados, operações experimentais)."""
        layer = self.layers[layer_index]
        out: list[Write] = []
        ignored = 0
        experimental: list[str] = []
        if layer.kind == "ppf":
            for i, (off, data) in enumerate(layer.ppf.records):
                ignored += self._split_image_write(layer_index, i, off, data, out, "ppf")
        elif layer.kind == "bps_import":
            base = self.image.data
            tgt = layer.bps_target
            if len(tgt) != len(base):
                raise PatchError("camada BPS muda o tamanho da imagem: não suportado")
            i = 0
            while i < len(base):
                if base[i] == tgt[i]:
                    i += 1
                    continue
                j = i
                while j < len(base) and base[j] != tgt[j]:
                    j += 1
                ignored += self._split_image_write(layer_index, i, i, tgt[i:j], out, "bps")
                i = j
        else:
            for i, e in enumerate(layer.edits):
                for file, off, data, label, exp in self._resolve_edit(layer, e):
                    if exp:
                        experimental.append(label)
                    k = 0
                    for pos, n in self._file_pos(file, off, len(data)):
                        out.append(Write(layer_index, i, pos, data[k:k + n], label))
                        k += n
        return out, ignored, experimental

    def _split_image_write(self, li: int, item: int, off: int, data: bytes, out: list[Write], label: str) -> int:
        """Escrita em offsets da imagem (PPF/BPS): separa dados de usuário e bytes de sistema."""
        if off + len(data) > len(self.image.data):
            raise PatchError(f"{label}: escrita em 0x{off:X} passa do fim da imagem")
        if self.image.disc is None:
            out.append(Write(li, item, off, data, label))
            return 0
        ignored = 0
        run_start = None
        for k in range(len(data) + 1):
            user = k < len(data) and self.image.disc.locate_bin_offset(off + k)[1] is not None
            if user and run_start is None:
                run_start = k
            elif not user and run_start is not None:
                out.append(Write(li, item, off + run_start, data[run_start:k], label))
                run_start = None
            if k < len(data) and not user:
                ignored += 1
        return ignored

    def _resolve_edit(self, layer: Layer, e):
        if isinstance(e, FieldEdit):
            if layer.kind != "changeset":
                raise PatchError("edição de campo só em camada changeset")
            if self.profile is None:
                raise PatchError("edição de campo exige um perfil que se aplique")
            t = self.profile.table(e.table)
            if e.field not in t.fields:
                raise PatchError(f"{e.target}: campo não existe no perfil")
            spec = t.fields[e.field]
            exp = False
            if self.findings is not None:
                pol = self.findings.policy(spec.finding, self.research_mode)
                if not pol.editable:
                    raise PatchError(f"{e.target}: {pol.reason}")
                exp = pol.experimental
            try:
                data = struct.pack(TYPES[spec.type][0], e.value)
            except struct.error:
                raise PatchError(f"{e.target}: valor {e.value} não cabe em {spec.type}") from None
            yield t.file, t.field_offset(e.index, e.field), data, e.target, exp
        elif isinstance(e, RawEdit):
            if layer.kind == "raw" and not self.research_mode:
                raise PatchError("camada raw só no Modo Pesquisa")
            label = self.field_label(e.file, e.offset) or f"{e.file}+0x{e.offset:X}"
            yield e.file, e.offset, e.data, label, layer.kind == "raw"
        elif isinstance(e, GraphicEdit):
            if layer.kind != "graphics":
                raise PatchError("edição de gráfico só em camada graphics")
            n = len(e.original)
            i = 0
            while i < n:  # só as faixas que mudaram
                if e.original[i] == e.new[i]:
                    i += 1
                    continue
                j = i
                while j < n and e.original[j] != e.new[j]:
                    j += 1
                yield e.file, e.offset + i, e.new[i:j], f"gráfico {e.file}+0x{e.offset:X} ({e.kind})", False
                i = j
        else:
            raise PatchError(f"operação desconhecida: {e!r}")

    # --- conflitos -------------------------------------------------------
    def conflicts(self) -> list[Conflict]:
        active = [i for i, l in enumerate(self.layers) if l.active]
        per_byte: dict[int, list[tuple[int, int, int]]] = {}
        labels: dict[tuple[int, int], str] = {}
        for li in active:
            ws, _, _ = self.writes(li)
            for w in ws:
                labels[(w.layer, w.item)] = w.label
                for k, b in enumerate(w.data):
                    per_byte.setdefault(w.pos + k, []).append((w.layer, w.item, b))
        out: list[Conflict] = []
        # Sobreposição entre escritas distintas (camadas diferentes, ou itens diferentes da mesma camada).
        runs: list[list] = []
        for pos in sorted(per_byte):
            hits = per_byte[pos]
            owners = {(l, i) for l, i, _ in hits}
            if len(owners) < 2:
                continue
            kind = "REDUNDANTE" if len({b for _, _, b in hits}) == 1 else "CONFLITO"
            key = (kind, tuple(sorted(owners)))
            if runs and runs[-1][0] == key and runs[-1][2] == pos:
                runs[-1][2] = pos + 1
            else:
                runs.append([key, pos, pos + 1])
        for (kind, owners), start, end in runs:
            names = tuple(dict.fromkeys(self.layers[l].name for l, _ in owners))
            file, foff, lba0 = self.locate(start)
            _, _, lba1 = self.locate(end - 1)
            target = self.field_label(file, foff) or next(
                (labels[o] for o in owners if not labels[o].startswith(("ppf", "bps"))), None)
            rng = (foff, foff + (end - start)) if foff is not None else None
            detail = (f"{' × '.join(names)} escrevem {end - start} byte(s)"
                      + (f" em {file} 0x{foff:X}" if file else f" na imagem 0x{start:X}")
                      + (f" (LBA {lba0})" if lba0 is not None else "")
                      + (" com os mesmos valores" if kind == "REDUNDANTE" else " com valores diferentes; a camada posterior vence"))
            out.append(Conflict(kind, names, detail, file, rng, (lba0, lba1) if lba0 is not None else None, target))
        out += self._integrity_warnings(active)
        out += self._palette_warnings(active)
        return out

    def _integrity_warnings(self, active: list[int]) -> list[Conflict]:
        if self.profile is None:
            return []
        out = []
        for li in active:
            layer = self.layers[li]
            if layer.kind == "changeset":
                continue
            ws, _, _ = self.writes(li)
            for t in self.profile.tables.values():
                hit = None
                for w in ws:
                    file, foff, _ = self.locate(w.pos)
                    if file and file.upper() == t.file.upper() and foff is not None \
                            and foff < t.end and foff + len(w.data) > t.offset:
                        hit = foff
                        break
                if hit is not None:
                    out.append(Conflict("INTEGRIDADE", (layer.name,),
                                        f"camada {layer.kind} '{layer.name}' altera a tabela {t.name} "
                                        f"({t.file} 0x{hit:X}) sem ser changeset",
                                        t.file, (t.offset, t.end), None, t.name))
        return out

    def _palette_warnings(self, active: list[int]) -> list[Conflict]:
        edits = [(self.layers[li].name, e) for li in active if self.layers[li].kind == "graphics"
                 for e in self.layers[li].edits if isinstance(e, GraphicEdit) and e.clut_pos is not None]
        out = []
        for i, (na, a) in enumerate(edits):
            for nb, b in edits[i + 1:]:
                if a.clut_pos == b.clut_pos and (a.file, a.offset) != (b.file, b.offset) \
                        and "cores" in (a.kind, b.kind):
                    out.append(Conflict("PALETA_COMPARTILHADA", tuple(dict.fromkeys((na, nb))),
                                        f"{a.file}+0x{a.offset:X} e {b.file}+0x{b.offset:X} usam a paleta em "
                                        f"{a.clut_pos} na VRAM e uma delas foi recolorida: paleta possivelmente "
                                        f"compartilhada no jogo", a.file, None, None, None))
        return out

    # --- montagem --------------------------------------------------------
    def build(self, acknowledged: set[str] = frozenset()) -> BuildResult:
        conflicts = self.conflicts()
        pending = [c for c in conflicts if c.needs_ack and c.id not in acknowledged]
        if pending:
            raise PatchError("conflitos não reconhecidos (portão P4):\n" + "\n".join(c.detail for c in pending))
        for l in self.layers:
            if l.active and l.kind == "ppf":
                why = l.ppf.check_block(self.image.data)
                if why and not l.ppf_block_acknowledged:
                    raise PatchError(f"PPF '{l.name}': {why} (portão P4)")
            if l.active and l.kind == "graphics":
                for e in l.edits:
                    base = self.image.read_file(e.file) if self.image.disc else self.image.data
                    if base[e.offset:e.offset + len(e.original)] != e.original:
                        raise PatchError(f"gráfico {e.file}+0x{e.offset:X}: os bytes originais não estão "
                                         f"no lugar (o arquivo base mudou)")
        out = bytearray(self.image.data)
        touched: set[int] = set()
        ignored = 0
        experimental: list[str] = []
        all_writes: list[Write] = []
        for li, layer in enumerate(self.layers):
            if not layer.active:
                continue
            ws, ign, exp = self.writes(li)
            ignored += ign
            experimental += exp
            all_writes += ws
        if self.image.disc is not None:
            for w in all_writes:
                touched.update(range(w.pos // RAW_SECTOR, (w.pos + len(w.data) - 1) // RAW_SECTOR + 1))
            bad = [lba for lba in sorted(touched) if not edc_ecc.is_valid(self.image.disc.raw_sector(lba))]
            if bad:
                raise PatchError(f"setores do original com EDC/ECC inválido: {bad[:10]} — imagem base corrompida?")
        for w in all_writes:  # em ordem de camada: a posterior vence
            out[w.pos:w.pos + len(w.data)] = w.data
        if self.image.disc is not None:
            for lba in sorted(touched):  # EDC/ECC uma vez, no fim, só nos setores tocados
                s = lba * RAW_SECTOR
                out[s:s + RAW_SECTOR] = edc_ecc.compute(bytes(out[s:s + RAW_SECTOR]))
        return BuildResult(bytes(out), sorted(touched), ignored, conflicts, experimental)
