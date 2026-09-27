"""Marco 10: TMD sintético (contagens, layouts, OBJ, textura pela VRAM)."""
import struct
import unittest

from inverse_engine.core.rom_image import RomImage
from inverse_engine.formats import tim, tmd
from tests.fixture_cd import CdBuilder


def prim(mode, halves, flag=0):
    body = struct.pack(f"<{len(halves)}H", *halves)
    return bytes([0, len(body) // 4, flag, mode]) + body


def build_tmd(fixp=False):
    """2 objetos. Obj 0: 4 vértices; triângulo plano, quadrilátero plano, triângulo texturizado,
    uma primitiva sem luz (layout não decodificado) e uma com índice fora. Obj 1: 3 vértices, Gouraud."""
    v0 = b"".join(struct.pack("<hhhh", *p, 0) for p in [(0, 0, 0), (100, 0, 0), (0, 100, 0), (100, 100, 0)])
    n0 = struct.pack("<hhhh", 0, 0, -4096, 0)
    p0 = (prim(0x20, [0x00FF, 0x2000, 0, 0, 1, 2])
          + prim(0x28, [0xFF00, 0x2800, 0, 0, 1, 2, 3, 0])
          + prim(0x24, [0x0000, (480 << 6) | 0, 0x0010, 5, 0x1000, 0, 0, 1, 2, 3])
          + prim(0x20, [0, 0, 0, 0, 1, 2], flag=1)
          + prim(0x20, [0, 0, 0, 0, 1, 9]))
    v1 = b"".join(struct.pack("<hhhh", *p, 0) for p in [(0, 0, 50), (10, 0, 50), (0, 10, 50)])
    p1 = prim(0x30, [0x0F0F, 0x3000, 0, 0, 0, 1, 0, 2])
    table_at = 12
    data_at = table_at + 2 * 28
    blobs = [v0, n0, p0, v1, n0, p1]
    offs, cur = [], data_at
    for b in blobs:
        offs.append(cur)
        cur += len(b)
    base = 0 if fixp else table_at
    rel = [o - base for o in offs]
    table = (struct.pack("<IIIIIIi", rel[0], 4, rel[1], 1, rel[2], 5, 0)
             + struct.pack("<IIIIIIi", rel[3], 3, rel[4], 1, rel[5], 1, 0))
    return struct.pack("<III", tmd.ID, 1 if fixp else 0, 2) + table + b"".join(blobs)


class TmdTest(unittest.TestCase):
    def test_contagem_de_vertices_e_faces(self):
        t = tmd.parse(build_tmd())
        o0, o1 = t.objects
        self.assertEqual((len(o0.vertices), len(o1.vertices)), (4, 3))
        self.assertEqual(len(o0.primitives), 5)
        self.assertEqual(o0.faces, 4)  # tri + quad (2) + tri texturizado
        self.assertEqual(o1.faces, 1)
        kinds = o0.counts()
        self.assertEqual(kinds["triângulo plano"], 1)
        self.assertEqual(sum(v for k, v in kinds.items() if k.startswith("layout desconhecido")), 2)
        self.assertEqual(o0.primitives[1].vertices, [0, 1, 2, 3])
        self.assertEqual(o1.primitives[0].vertices, [0, 1, 2])
        self.assertEqual(t.size, len(build_tmd()))

    def test_ponteiros_absolutos_fixp(self):
        t = tmd.parse(build_tmd(fixp=True))
        self.assertEqual([len(o.vertices) for o in t.objects], [4, 3])

    def test_textura_uv_cba_tsb(self):
        p = tmd.parse(build_tmd()).objects[0].primitives[2]
        self.assertEqual((p.uv, p.cba, p.tsb), ([(0, 0), (16, 0), (0, 16)], 480 << 6, 5))
        self.assertEqual(tmd.texture_page(5), (320, 0, 4))
        self.assertEqual(tmd.clut_position(480 << 6), (0, 480))
        t_ok = tim.parse(tim.build(4, 8, 2, [[0] * 8] * 2, clut=[[0] * 16], vram=(320, 0), clut_pos=(0, 480)), 0)
        t_other = tim.parse(tim.build(4, 8, 2, [[0] * 8] * 2, clut=[[0] * 16], vram=(512, 0), clut_pos=(0, 480)), 0)
        self.assertEqual(tmd.find_texture(p, [("B.TIM", t_other), ("A.TIM", t_ok)])[0], "A.TIM")
        self.assertIsNone(tmd.find_texture(p, [("B.TIM", t_other)]))

    def test_obj(self):
        obj = tmd.to_obj(tmd.parse(build_tmd()), "teste", mtl="teste.mtl")
        lines = obj.splitlines()
        self.assertEqual(sum(l.startswith("v ") for l in lines), 7)
        self.assertEqual(sum(l.startswith("f ") for l in lines), 5)
        self.assertEqual(sum(l.startswith("vt ") for l in lines), 3)
        self.assertIn("f 1 2 3", lines)
        self.assertIn("f 2 4 3", lines)   # quad: 0,1,2 e 1,3,2
        self.assertIn("f 5 6 7", lines)   # segundo objeto com índices deslocados
        self.assertIn("mtllib teste.mtl", lines)

    def test_procura_e_rejeita_lixo(self):
        blob = b"\x41\x00\x00\x00" + b"\xFF" * 60 + build_tmd() + b"fim!"
        found = tmd.scan(blob)
        self.assertEqual([t.offset for t in found], [64])
        with self.assertRaises(tmd.TmdError):
            tmd.parse(struct.pack("<III", tmd.ID, 0, 0))
        cd = CdBuilder().build({"MODEL/A.TMD": build_tmd(), "MOVIE/X.STR": build_tmd()}, form2={"MOVIE/X.STR"})
        self.assertEqual([p for p, _ in tmd.scan_image(RomImage.from_bytes(cd))], ["MODEL/A.TMD"])


if __name__ == "__main__":
    unittest.main()
