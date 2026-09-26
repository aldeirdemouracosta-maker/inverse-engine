"""PatchStack: camadas PPF + changeset + gráficos, conflitos e montagem com EDC/ECC."""
import struct
import unittest
from pathlib import Path

from inverse_engine.core.paths import with_ext, replace_ext
from inverse_engine.core.patch_stack import (PatchStack, Layer, FieldEdit, RawEdit, GraphicEdit, PatchError)
from inverse_engine.core.profile import RomProfile
from inverse_engine.core.rom_image import RomImage
from inverse_engine.formats import edc_ecc, ppf, tim, png
from inverse_engine.formats.disc import RAW_SECTOR
from inverse_engine.research.findings import FindingsDB
from tests.fixture_cd import CdBuilder, make_slus

ROOT = Path(__file__).resolve().parent.parent
PROFILE = RomProfile.load(ROOT / "profiles" / "SLUS-00940-USA.json")
FINDINGS = FindingsDB.load(ROOT / "research" / "findings" / "SLUS-00940-USA.json")
ATTACK_182 = 0xB5C + 182 * 22 + 0xA          # 0x1B0A, setor 3 do SLUS
SAME_SECTOR_OUTSIDE_TABLE = 0x1F00           # setor 3, depois do fim da tabela (0x1DD6)

PAL = [0x0000, 0x001F, 0x03E0, 0x7C00] + [0x7FFF] * 12
TIM = tim.build(4, 8, 2, [[x % 4 for x in range(8)]] * 2, clut=[PAL])


def files(slus=None, spr_extra=b""):
    slus = slus or make_slus(names={182: "Rebelrod"}, values={(182, 0xA): struct.pack("<H", 30)})
    return {"SLUS_009.40": slus, "DATA/CHR/SPR.BIN": b"\x00" * 64 + TIM + spr_extra + TIM,
            "DATA/OUTRO.BIN": b"o" * 5000}


def cd(slus=None):
    return CdBuilder().build(files(slus))


def slus_with(changes):
    s = bytearray(files()["SLUS_009.40"])
    for off, data in changes:
        s[off:off + len(data)] = data
    return bytes(s)


def ppf_layer(name, changes, **kw):
    """PPF gerado entre o CD original e o CD com o SLUS alterado (inclui bytes de EDC/ECC)."""
    return Layer(name, "ppf", ppf=ppf.parse(ppf.build_ppf3(cd(), cd(slus_with(changes)))), **kw)


def recolor(info_offset, color_index=1, new_rgba=(255, 0, 255, 255)):
    data = files()["DATA/CHR/SPR.BIN"]
    info = tim.parse(data, info_offset)
    img = png.read(tim.export_png(data, info))
    pal = list(img.palette)
    pal[color_index] = new_rgba
    new = tim.import_colors(data, info, png.write_indexed(info.width, info.height, img.rows, pal))
    return GraphicEdit("DATA/CHR/SPR.BIN", info.offset, data[info.offset:info.offset + info.size], new,
                       "cores", 0, info.clut_pos)


class PatchStackTest(unittest.TestCase):
    def stack(self, research=False):
        return PatchStack(RomImage.from_bytes(cd()), PROFILE, FINDINGS, research_mode=research)

    def test_ppf_e_changeset_no_mesmo_setor_sem_conflito_falso(self):
        st = self.stack()
        st.add(ppf_layer("Take Turns (sintético)", [(SAME_SECTOR_OUTSIDE_TABLE, b"\xEE\xEE")]))
        st.add(Layer("Rebalance", "changeset", edits=[FieldEdit("weapons", 182, "attack", 45)]))
        self.assertEqual([c for c in st.conflicts() if c.kind in ("CONFLITO", "REDUNDANTE")], [])
        res = st.build()
        self.assertGreater(res.system_bytes_ignored, 0)  # EDC/ECC do PPF ignorados, recalculados no fim
        out = RomImage.from_bytes(res.data).read_file("SLUS_009.40")
        self.assertEqual(struct.unpack_from("<H", out, ATTACK_182)[0], 45)
        self.assertEqual(out[SAME_SECTOR_OUTSIDE_TABLE:SAME_SECTOR_OUTSIDE_TABLE + 2], b"\xEE\xEE")
        self.assertEqual(len(res.touched_sectors), 1)

    def test_conflito_real_com_camadas_faixa_e_campo(self):
        st = self.stack()
        st.add(ppf_layer("PPF", [(ATTACK_182, struct.pack("<H", 99))]))
        st.add(Layer("Rebalance", "changeset", edits=[FieldEdit("weapons", 182, "attack", 45)]))
        conf = [c for c in st.conflicts() if c.kind == "CONFLITO"]
        self.assertEqual(len(conf), 1)
        c = conf[0]
        self.assertEqual(c.layers, ("PPF", "Rebalance"))
        self.assertEqual(c.target, "weapons[182].attack")
        self.assertEqual(c.file, "SLUS_009.40")
        self.assertEqual(c.file_range, (ATTACK_182, ATTACK_182 + 1))  # só o byte baixo difere (30→99 vs 45)
        self.assertIsNotNone(c.lba_range)
        with self.assertRaisesRegex(PatchError, "P4"):
            st.build()
        res = st.build(acknowledged={c.id})
        out = RomImage.from_bytes(res.data).read_file("SLUS_009.40")
        self.assertEqual(struct.unpack_from("<H", out, ATTACK_182)[0], 45)  # a posterior vence

    def test_redundante_e_informativo(self):
        st = self.stack()
        st.add(ppf_layer("PPF", [(ATTACK_182, struct.pack("<H", 45))]))
        st.add(Layer("Rebalance", "changeset", edits=[FieldEdit("weapons", 182, "attack", 45)]))
        kinds = [c.kind for c in st.conflicts()]
        self.assertIn("REDUNDANTE", kinds)
        self.assertNotIn("CONFLITO", kinds)
        st.build()

    def test_ppf_na_tabela_gera_aviso_de_integridade(self):
        st = self.stack()
        st.add(ppf_layer("PPF", [(0xB5C + 5 * 22 + 1, b"\x01")]))
        warn = [c for c in st.conflicts() if c.kind == "INTEGRIDADE"]
        self.assertEqual(len(warn), 1)
        self.assertEqual(warn[0].target, "weapons")
        self.assertFalse(warn[0].needs_ack)

    def test_grafico_e_arma_na_mesma_bin(self):
        st = self.stack()
        g = recolor(64)
        st.add(Layer("Rebalance", "changeset", edits=[FieldEdit("weapons", 182, "attack", 12)]))
        st.add(Layer("Cores", "graphics", edits=[g]))
        res = st.build()
        img = RomImage.from_bytes(res.data)
        self.assertEqual(struct.unpack_from("<H", img.read_file("SLUS_009.40"), ATTACK_182)[0], 12)
        spr = img.read_file("DATA/CHR/SPR.BIN")
        self.assertEqual(spr[64:64 + len(TIM)], g.new)
        for lba in range(len(res.data) // RAW_SECTOR):
            raw = res.data[lba * RAW_SECTOR:(lba + 1) * RAW_SECTOR]
            self.assertTrue(edc_ecc.is_valid(raw), lba)
            if lba not in res.touched_sectors:
                self.assertEqual(raw, cd()[lba * RAW_SECTOR:(lba + 1) * RAW_SECTOR])
        self.assertEqual(len(res.touched_sectors), 2)

    def test_desativar_camada_e_gerar_de_novo(self):
        st = self.stack()
        a = st.add(Layer("A", "changeset", edits=[FieldEdit("weapons", 182, "attack", 12)]))
        st.add(Layer("B", "graphics", edits=[recolor(64)]))
        both = st.build().data
        a.active = False
        only_b = st.build().data
        st2 = self.stack()
        st2.add(Layer("B", "graphics", edits=[recolor(64)]))
        self.assertEqual(only_b, st2.build().data)
        self.assertNotEqual(both, only_b)
        a.active = True
        self.assertEqual(st.build().data, both)
        for l in st.layers:
            l.active = False
        self.assertEqual(st.build().data, cd())

    def test_setor_original_com_edc_invalido_recusado(self):
        broken = bytearray(cd())
        img = RomImage.from_bytes(bytes(broken))
        pos = img.file_offset_to_bin("SLUS_009.40", ATTACK_182 + 40)
        broken[pos] ^= 0xFF  # dado mudou sem recalcular EDC/ECC
        st = PatchStack(RomImage.from_bytes(bytes(broken)), PROFILE, FINDINGS)
        st.add(Layer("R", "changeset", edits=[FieldEdit("weapons", 182, "attack", 12)]))
        with self.assertRaisesRegex(PatchError, "EDC/ECC inválido"):
            st.build()

    def test_grafico_com_base_mudada_recusado(self):
        g = recolor(64)
        wrong = GraphicEdit(g.file, g.offset, b"\x00" + g.original[1:], b"\x00" + g.new[1:], "cores")
        st = self.stack()
        st.add(Layer("G", "graphics", edits=[wrong]))
        with self.assertRaisesRegex(PatchError, "arquivo base mudou"):
            st.build()

    def test_grafico_nao_muda_de_tamanho(self):
        with self.assertRaises(PatchError):
            GraphicEdit("X", 0, b"ab", b"abc", "desenho")

    def test_grafico_x_grafico_e_grafico_x_campo(self):
        st = self.stack()
        g = recolor(64)
        g2 = recolor(64, 1, (0, 255, 0, 255))  # 0x03E0: byte alto difere de 0x7C1F
        st.add(Layer("G", "graphics", edits=[g, g2]))
        self.assertEqual([c.kind for c in st.conflicts()].count("CONFLITO"), 1)
        st = self.stack()
        exe_tim = GraphicEdit("SLUS_009.40", ATTACK_182 - 1, b"\x00\x1e\x00", b"\x00\x05\x00", "desenho")
        st.add(Layer("G", "graphics", edits=[exe_tim]))
        st.add(Layer("R", "changeset", edits=[FieldEdit("weapons", 182, "attack", 7)]))
        c = [c for c in st.conflicts() if c.kind == "CONFLITO"]
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0].target, "weapons[182].attack")

    def test_paleta_possivelmente_compartilhada(self):
        st = self.stack()
        st.add(Layer("G", "graphics", edits=[recolor(64), recolor(64 + len(TIM))]))
        warn = [c for c in st.conflicts() if c.kind == "PALETA_COMPARTILHADA"]
        self.assertEqual(len(warn), 1)
        self.assertFalse(warn[0].needs_ack)
        st.build()

    def test_politica_de_edicao(self):
        st = self.stack()
        st.add(Layer("R", "changeset", edits=[FieldEdit("weapons", 1, "price", 100)]))
        with self.assertRaisesRegex(PatchError, "Modo Pesquisa"):
            st.build()
        st = self.stack(research=True)
        st.add(Layer("R", "changeset", edits=[FieldEdit("weapons", 1, "price", 100)]))
        self.assertEqual(st.build().experimental, ["weapons[1].price"])

    def test_raw_so_no_modo_pesquisa(self):
        st = self.stack()
        st.add(Layer("X", "raw", edits=[RawEdit("SLUS_009.40", 0x3000, b"\x01")]))
        with self.assertRaises(PatchError):
            st.build()
        st.research_mode = True
        self.assertEqual(len(st.build().touched_sectors), 1)

    def test_valor_fora_do_tipo_recusado(self):
        st = self.stack()
        st.add(Layer("R", "changeset", edits=[FieldEdit("weapons", 1, "attack", 70000)]))
        with self.assertRaisesRegex(PatchError, "não cabe"):
            st.build()

    def test_ppf_de_outra_imagem_exige_reconhecimento(self):
        layer = ppf_layer("PPF", [(0x3000, b"\x01")])
        other = bytearray(cd())
        other[0x9320 + 100] ^= 1  # muda o bloco de conferência (setor de sistema, fora de arquivos)
        img_bytes = bytes(other)
        st = PatchStack(RomImage.from_bytes(img_bytes), PROFILE, FINDINGS)
        st.add(layer)
        with self.assertRaisesRegex(PatchError, "bloco de conferência"):
            st.build()
        layer.ppf_block_acknowledged = True
        st.build()

    def test_escrita_em_form2_recusada(self):
        data = CdBuilder().build({"SLUS_009.40": files()["SLUS_009.40"], "M.STR": b"m" * 100}, form2={"M.STR"})
        st = PatchStack(RomImage.from_bytes(data), PROFILE, FINDINGS, research_mode=True)
        st.add(Layer("X", "raw", edits=[RawEdit("M.STR", 0, b"x")]))
        with self.assertRaisesRegex(PatchError, "Form 2"):
            st.build()

    def test_executavel_avulso(self):
        slus = files()["SLUS_009.40"]
        st = PatchStack(RomImage.from_bytes(slus, "slus.exe"), PROFILE, FINDINGS)
        st.add(Layer("R", "changeset", edits=[FieldEdit("weapons", 182, "attack", 77)]))
        res = st.build()
        self.assertEqual(struct.unpack_from("<H", res.data, ATTACK_182)[0], 77)
        self.assertEqual(res.touched_sectors, [])
        self.assertEqual(sum(a != b for a, b in zip(res.data, slus)), 1)

    def test_original_intocado(self):
        base = cd()
        img = RomImage.from_bytes(base)
        st = PatchStack(img, PROFILE, FINDINGS)
        st.add(Layer("R", "changeset", edits=[FieldEdit("weapons", 182, "attack", 1)]))
        st.build()
        self.assertEqual(img.data, base)


class PathsTest(unittest.TestCase):
    def test_nomes_com_pontos(self):
        self.assertEqual(with_ext("saida/SLUS_009.40", ".bps").name, "SLUS_009.40.bps")
        self.assertEqual(with_ext("Vandal Hearts II (USA).bin", "bps").name, "Vandal Hearts II (USA).bin.bps")
        self.assertEqual(replace_ext("Jogo v1.2 (USA).bin", ".bin", ".cue").name, "Jogo v1.2 (USA).cue")
        self.assertEqual(replace_ext("SLUS_009.40", ".bin", ".cue").name, "SLUS_009.40.cue")


if __name__ == "__main__":
    unittest.main()
