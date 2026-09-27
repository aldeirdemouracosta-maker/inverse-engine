"""ChangeSet: operações registradas, agrupáveis, com desfazer/refazer.

Toda edição é uma operação com alvo, antes, depois, origem e finding. Uma frase do assistente ou um
plano em lote é um grupo, desfeito de uma vez. O ChangeSet não escreve bytes: gera camadas do PatchStack.
"""
from __future__ import annotations

import datetime as _dt
import struct
from contextlib import contextmanager
from dataclasses import dataclass, asdict, field

from inverse_engine.core.patch_stack import FieldEdit, RawEdit, GraphicEdit, Layer, PatchError
from inverse_engine.core.profile import RomProfile, TYPES
from inverse_engine.core.rom_image import RomImage
from inverse_engine.research.findings import FindingsDB

ORIGINS = ("manual", "regras", "IA", "script")


@dataclass
class Operation:
    id: int
    kind: str                     # field | raw | graphic | text
    target: str                   # "weapons[182].attack", "SLUS_009.40+0x3000", "gráfico DATA/X.BIN+0x40"
    before: object                # int (field) ou hex (raw/graphic)
    after: object
    origin: str = "manual"
    finding: str | None = None
    date: str = ""
    group: int = 0
    group_label: str = ""
    experimental: bool = False
    # dados para regenerar a edição
    table: str | None = None
    index: int | None = None
    field: str | None = None
    file: str | None = None
    offset: int | None = None
    graphic_kind: str | None = None
    palette_index: int = 0
    clut_pos: list[int] | None = None
    payload: str | None = None    # text: bytes exatos gravados (hex)

    def to_edit(self):
        if self.kind == "field":
            return FieldEdit(self.table, self.index, self.field, self.after)
        if self.kind == "raw":
            return RawEdit(self.file, self.offset, bytes.fromhex(self.after))
        if self.kind == "text":  # bytes gravados ficam em `payload` (texto + NUL até o tamanho original)
            return RawEdit(self.file, self.offset, bytes.fromhex(self.payload))
        return GraphicEdit(self.file, self.offset, bytes.fromhex(self.before), bytes.fromhex(self.after),
                           self.graphic_kind, self.palette_index, tuple(self.clut_pos) if self.clut_pos else None)


@dataclass
class ChangeSet:
    name: str = "Alterações"
    active: bool = True
    ops: list[Operation] = field(default_factory=list)
    redo_groups: list[list[Operation]] = field(default_factory=list)
    next_id: int = 1
    next_group: int = 1
    _open_group: tuple[int, str] | None = field(default=None, repr=False, compare=False)

    # --- contexto de validação (não persistido) --------------------------
    def bind(self, image: RomImage, profile: RomProfile | None, findings: FindingsDB | None,
             research_mode: bool = False) -> "ChangeSet":
        self._image, self._profile, self._findings, self._research = image, profile, findings, research_mode
        return self

    def _ctx(self):
        if not hasattr(self, "_image"):
            raise PatchError("ChangeSet sem imagem: chame bind(imagem, perfil, findings)")
        return self._image, self._profile, self._findings, self._research

    # --- grupos ------------------------------------------------------------
    @contextmanager
    def group(self, label: str):
        """Tudo o que for feito dentro do bloco vira um grupo (desfeito de uma vez)."""
        if self._open_group is not None:
            yield self._open_group[0]
            return
        self._open_group = (self.next_group, label)
        self.next_group += 1
        start = len(self.ops)
        try:
            yield self._open_group[0]
        except Exception:
            del self.ops[start:]  # grupo com erro não entra pela metade
            raise
        finally:
            self._open_group = None

    def _record(self, op: Operation) -> Operation:
        if self._open_group is not None:
            op.group, op.group_label = self._open_group
        else:
            op.group, op.group_label = self.next_group, op.target
            self.next_group += 1
        op.id = self.next_id
        self.next_id += 1
        op.date = op.date or _dt.datetime.now().isoformat(timespec="seconds")
        self.ops.append(op)
        self.redo_groups.clear()
        return op

    # --- operações ---------------------------------------------------------
    def current_field(self, table: str, index: int, field_name: str) -> int:
        target = f"{table}[{index}].{field_name}"
        for op in reversed(self.ops):
            if op.kind == "field" and op.target == target:
                return op.after
        image, profile, _, _ = self._ctx()
        t = profile.table(table)
        return t.read_field(image.read_file(t.file) if image.disc else image.data, index, field_name)

    def set_field(self, table: str, index: int, field_name: str, value: int, origin: str = "manual") -> Operation:
        image, profile, findings, research = self._ctx()
        if origin not in ORIGINS:
            raise PatchError(f"origem inválida: {origin}")
        if profile is None:
            raise PatchError("edição de campo exige um perfil que se aplique")
        t = profile.table(table)
        if field_name not in t.fields:
            raise PatchError(f"{table}[{index}].{field_name}: campo não existe no perfil")
        t.record_offset(index)
        spec = t.fields[field_name]
        exp = False
        if findings is not None:
            pol = findings.policy(spec.finding, research)
            if not pol.editable:
                raise PatchError(f"{table}[{index}].{field_name}: {pol.reason}")
            exp = pol.experimental
        try:
            struct.pack(TYPES[spec.type][0], value)
        except struct.error:
            raise PatchError(f"{table}[{index}].{field_name}: valor {value} não cabe em {spec.type}") from None
        before = self.current_field(table, index, field_name)
        return self._record(Operation(0, "field", f"{table}[{index}].{field_name}", before, value, origin,
                                      spec.finding, experimental=exp, table=table, index=index, field=field_name))

    def set_raw(self, file: str, offset: int, data: bytes, origin: str = "manual") -> Operation:
        image, _, _, research = self._ctx()
        if not research:
            raise PatchError("edição de byte cru só no Modo Pesquisa")
        base = image.read_file(file) if image.disc else image.data
        if offset < 0 or offset + len(data) > len(base):
            raise PatchError(f"escrita fora de {file}")
        before = base[offset:offset + len(data)]
        for op in self.ops:  # "antes" considera edições cruas anteriores na mesma faixa
            if op.kind == "raw" and op.file == file and op.offset == offset and len(op.after) == 2 * len(data):
                before = bytes.fromhex(op.after)
        return self._record(Operation(0, "raw", f"{file}+0x{offset:X}", before.hex().upper(), data.hex().upper(),
                                      origin, None, experimental=True, file=file, offset=offset))

    def set_name(self, table: str, index: int, text: str, origin: str = "manual") -> Operation:
        """Troca o nome no mesmo espaço (mesmo tamanho ou menor, completando com NUL).

        Nomes cujo finding ainda é HIPOTESE/DESCONHECIDO só no Modo Pesquisa.
        """
        from inverse_engine.research.names import encode_name
        image, profile, findings, research = self._ctx()
        t = profile.table(table)
        if findings is not None:
            pol = findings.policy(t.names_finding, research)
            if not pol.editable:
                raise PatchError(f"nomes de {table}: {pol.reason}")
        data = image.read_file(t.file) if image.disc else image.data
        pad = b" " if (research and t.names_separator) else None
        off, old, new = encode_name(t, data, index, text, pad)
        padded = bool(t.names_separator) and len(text.encode("ascii")) < len(old)
        before = old.decode("ascii")
        for op in self.ops:  # "antes" considera trocas anteriores do mesmo nome
            if op.kind == "text" and op.file == t.file and op.offset == off:
                before = op.after
        return self._record(Operation(0, "text", f"{table}[{index}].nome", before, text, origin, t.names_finding,
                                      experimental=padded, file=t.file, offset=off, table=table, index=index,
                                      field="nome", payload=new.hex().upper()))

    def set_graphic(self, edit: GraphicEdit, origin: str = "manual") -> Operation:
        return self._record(Operation(0, "graphic", f"gráfico {edit.file}+0x{edit.offset:X}",
                                      edit.original.hex().upper(), edit.new.hex().upper(), origin, None,
                                      file=edit.file, offset=edit.offset, graphic_kind=edit.kind,
                                      palette_index=edit.palette_index,
                                      clut_pos=list(edit.clut_pos) if edit.clut_pos else None))

    # --- desfazer / refazer --------------------------------------------------
    def undo(self) -> list[Operation]:
        if not self.ops:
            return []
        g = self.ops[-1].group
        k = len(self.ops)
        while k and self.ops[k - 1].group == g:
            k -= 1
        undone = self.ops[k:]
        del self.ops[k:]
        self.redo_groups.append(undone)
        return undone

    def redo(self) -> list[Operation]:
        if not self.redo_groups:
            return []
        group = self.redo_groups.pop()
        self.ops.extend(group)
        return group

    def can_undo(self) -> bool:
        return bool(self.ops)

    def can_redo(self) -> bool:
        return bool(self.redo_groups)

    def history(self) -> list[dict]:
        return [{"id": o.id, "grupo": o.group, "rótulo": o.group_label, "alvo": o.target, "antes": o.before,
                 "depois": o.after, "origem": o.origin, "finding": o.finding, "data": o.date} for o in self.ops]

    # --- camadas -------------------------------------------------------------
    def to_layers(self) -> list[Layer]:
        """Uma camada por tipo; só a última operação de cada alvo conta (sem conflito consigo mesmo)."""
        last: dict[tuple[str, str], Operation] = {}
        for op in self.ops:
            last[(op.kind, op.target)] = op
        by_kind = {"field": [], "graphic": [], "raw": [], "text": []}
        for (kind, _), op in last.items():
            by_kind["field" if kind == "text" else kind].append(op)  # nomes vão na camada changeset
        out = []
        for kind, layer_kind, suffix in (("field", "changeset", ""), ("graphic", "graphics", " (gráficos)"),
                                         ("raw", "raw", " (bytes crus)")):
            if by_kind[kind]:
                edits = []
                for op in by_kind[kind]:
                    if kind == "graphic":  # "antes" do gráfico é sempre o TIM original da primeira operação
                        first = next(o for o in self.ops if o.kind == "graphic" and o.target == op.target)
                        edits.append(GraphicEdit(op.file, op.offset, bytes.fromhex(first.before),
                                                 bytes.fromhex(op.after), op.graphic_kind, op.palette_index,
                                                 tuple(op.clut_pos) if op.clut_pos else None))
                    else:
                        edits.append(op.to_edit())
                out.append(Layer(self.name + suffix, layer_kind, self.active, edits=edits))
        return out

    # --- persistência ----------------------------------------------------------
    def to_dict(self) -> dict:
        return {"name": self.name, "active": self.active, "next_id": self.next_id, "next_group": self.next_group,
                "ops": [asdict(o) for o in self.ops],
                "redo_groups": [[asdict(o) for o in g] for g in self.redo_groups]}

    @classmethod
    def from_dict(cls, d: dict) -> "ChangeSet":
        return cls(d["name"], d.get("active", True), [Operation(**o) for o in d["ops"]],
                   [[Operation(**o) for o in g] for g in d.get("redo_groups", [])],
                   d.get("next_id", 1), d.get("next_group", 1))
