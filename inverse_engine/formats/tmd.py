"""TMD (modelo 3D da Sony, id 0x41): objetos, vértices, normais e primitivas. Só leitura.

Estrutura (PsyQ / psx-spx): cabeçalho de 12 bytes (id 0x41, flags, número de objetos); tabela de objetos
(28 bytes cada: vert_top, n_vert, normal_top, n_normal, prim_top, n_prim, scale); vértices e normais em
SVECTOR (3 × s16 + preenchimento); cada primitiva = cabeçalho (olen, ilen, flag, mode) + ilen palavras.

Só os layouts de polígono com luz (flag LGT = 0) abaixo são decodificados; os outros são contados e
marcados como "layout desconhecido" (confira com um TMD real antes de ampliar a tabela).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

ID = 0x41
FIXP = 1
OBJ_SIZE = 28

# mode → (nome, vértices, texturizado, ilen esperado, posições (em u16, após os bytes de UV/cor) dos índices)
# Índices contados em meias-palavras a partir do início do pacote (depois do cabeçalho de 4 bytes).
LAYOUTS = {
    0x20: ("triângulo plano", 3, False, 3, [3, 4, 5]),
    0x24: ("triângulo plano texturizado", 3, True, 5, [7, 8, 9]),
    0x30: ("triângulo Gouraud", 3, False, 4, [3, 5, 7]),
    0x34: ("triângulo Gouraud texturizado", 3, True, 6, [7, 9, 11]),
    0x28: ("quadrilátero plano", 4, False, 4, [3, 4, 5, 6]),
    0x2C: ("quadrilátero plano texturizado", 4, True, 7, [9, 10, 11, 12]),
    0x38: ("quadrilátero Gouraud", 4, False, 5, [3, 5, 7, 9]),
    0x3C: ("quadrilátero Gouraud texturizado", 4, True, 8, [9, 11, 13, 15]),
}


class TmdError(ValueError):
    pass


@dataclass
class Primitive:
    mode: int
    flag: int
    kind: str
    vertices: list[int]                 # índices (vazio se layout desconhecido)
    uv: list[tuple[int, int]] = field(default_factory=list)
    cba: int | None = None              # posição da paleta na VRAM
    tsb: int | None = None              # página de textura

    @property
    def known(self) -> bool:
        return bool(self.vertices)


@dataclass
class TmdObject:
    vertices: list[tuple[int, int, int]]
    normals: list[tuple[int, int, int]]
    primitives: list[Primitive]
    scale: int

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for p in self.primitives:
            out[p.kind] = out.get(p.kind, 0) + 1
        return out

    @property
    def faces(self) -> int:
        return sum(1 if len(p.vertices) == 3 else 2 for p in self.primitives if p.known)


@dataclass
class Tmd:
    offset: int
    size: int
    flags: int
    objects: list[TmdObject]


def _svectors(data: bytes, off: int, n: int) -> list[tuple[int, int, int]]:
    if off < 0 or off + 8 * n > len(data):
        raise TmdError("lista de vértices/normais fora do arquivo")
    return [struct.unpack_from("<hhh", data, off + 8 * i) for i in range(n)]


def parse(data: bytes, offset: int = 0) -> Tmd:
    if offset + 12 > len(data):
        raise TmdError("cabeçalho TMD truncado")
    ident, flags, nobj = struct.unpack_from("<III", data, offset)
    if ident != ID or flags & ~FIXP or not 1 <= nobj <= 512:
        raise TmdError("cabeçalho TMD incoerente")
    table = offset + 12
    if table + nobj * OBJ_SIZE > len(data):
        raise TmdError("tabela de objetos fora do arquivo")
    base = 0 if flags & FIXP else table
    objects, end = [], table + nobj * OBJ_SIZE
    for k in range(nobj):
        vt, nv, nt, nn, pt, np_, scale = struct.unpack_from("<IIIIIIi", data, table + k * OBJ_SIZE)
        if nv > 65535 or nn > 65535 or np_ > 65535:
            raise TmdError(f"objeto {k}: contagens absurdas")
        verts = _svectors(data, base + vt, nv)
        norms = _svectors(data, base + nt, nn) if nn else []
        end = max(end, base + vt + 8 * nv, base + nt + 8 * nn)
        pos = base + pt
        prims = []
        for _ in range(np_):
            if pos + 4 > len(data):
                raise TmdError(f"objeto {k}: primitivas fora do arquivo")
            olen, ilen, flag, mode = data[pos:pos + 4]
            body = data[pos + 4:pos + 4 + 4 * ilen]
            if len(body) != 4 * ilen:
                raise TmdError(f"objeto {k}: primitiva truncada")
            prims.append(_primitive(mode, flag, ilen, body, nv))
            pos += 4 + 4 * ilen
        end = max(end, pos)
        objects.append(TmdObject(verts, norms, prims, scale))
    return Tmd(offset, end - offset, flags, objects)


def _primitive(mode: int, flag: int, ilen: int, body: bytes, nverts: int) -> Primitive:
    lay = LAYOUTS.get(mode)
    if lay is None or flag & 1 or ilen != lay[3]:  # LGT=1 (sem luz) ou tamanho diferente: não decodifica
        return Primitive(mode, flag, f"layout desconhecido (mode 0x{mode:02X}, flag 0x{flag:02X}, ilen {ilen})", [])
    name, n, textured, _, idx_pos = lay
    halves = struct.unpack_from(f"<{len(body) // 2}H", body)
    verts = [halves[i] for i in idx_pos]
    if any(v >= nverts for v in verts):
        return Primitive(mode, flag, f"layout desconhecido (índice fora: mode 0x{mode:02X})", [])
    prim = Primitive(mode, flag, name, verts)
    if textured:
        prim.uv = [(body[4 * i], body[4 * i + 1]) for i in range(n)]
        prim.cba = halves[1]
        prim.tsb = halves[3]
    return prim


def scan(data: bytes, limit: int = 500) -> list[Tmd]:
    out = []
    pos = 0
    pat = struct.pack("<I", ID)
    while len(out) < limit:
        pos = data.find(pat, pos)
        if pos < 0:
            break
        if pos % 4 == 0:
            try:
                t = parse(data, pos)
                if sum(len(o.vertices) for o in t.objects) >= 3 and any(o.primitives for o in t.objects):
                    out.append(t)
                    pos += max(4, t.size)
                    continue
            except TmdError:
                pass
        pos += 4
    return out


def scan_image(image) -> list[tuple[str, Tmd]]:
    out = []
    for f in image.list_files():
        if f.is_dir or f.form2:
            continue
        for t in scan(image.read_file(f.path)):
            out.append((f.path, t))
    return out


def texture_page(tsb: int) -> tuple[int, int, int]:
    """(x, y, bits por pixel) da página de textura indicada pela TSB."""
    return (tsb & 0x0F) * 64, ((tsb >> 4) & 1) * 256, {0: 4, 1: 8, 2: 16}.get((tsb >> 7) & 3, 16)


def clut_position(cba: int) -> tuple[int, int]:
    return (cba & 0x3F) * 16, (cba >> 6) & 0x1FF


def to_obj(t: Tmd, name: str = "modelo", mtl: str | None = None) -> str:
    """OBJ com todos os objetos; quadriláteros viram dois triângulos (ordem PS1: 0,1,2 e 1,3,2)."""
    lines = [f"# exportado pelo Inverse Engine: {name}", "# coordenadas cruas do PS1 (Y para baixo)"]
    if mtl:
        lines.append(f"mtllib {mtl}")
    vbase, tbase = 1, 1
    for k, o in enumerate(t.objects):
        lines.append(f"o objeto_{k}")
        lines += [f"v {x} {-y} {-z}" for x, y, z in o.vertices]
        for p in o.primitives:
            if not p.known:
                continue
            v = [i + vbase for i in p.vertices]
            if p.uv:
                lines += [f"vt {u / 255:.4f} {1 - vv / 255:.4f}" for u, vv in p.uv]
                vt = list(range(tbase, tbase + len(p.uv)))
                tbase += len(p.uv)
                tri = lambda a, b, c: f"f {v[a]}/{vt[a]} {v[b]}/{vt[b]} {v[c]}/{vt[c]}"
            else:
                tri = lambda a, b, c: f"f {v[a]} {v[b]} {v[c]}"
            lines.append(tri(0, 1, 2))
            if len(v) == 4:
                lines.append(tri(1, 3, 2))
        vbase += len(o.vertices)
    return "\n".join(lines) + "\n"


def find_texture(prim: Primitive, tims: list) -> tuple[str, object] | None:
    """TIM (arquivo, TimInfo) cuja imagem cai na página de textura (TSB) e cuja paleta está na CBA."""
    if prim.tsb is None:
        return None
    px, py, _ = texture_page(prim.tsb)
    clut = clut_position(prim.cba) if prim.cba is not None else None
    for path, info in tims:
        x, y = info.vram_pos
        if px <= x < px + 64 and py <= y < py + 256 and (clut is None or info.clut_pos == clut):
            return path, info
    return None
