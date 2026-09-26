"""Marco 7: tabelas genéricas (armas, habilidades, armaduras), nomes por ponteiros e edição de texto."""
import copy
import json
import shutil
import struct
import tempfile
import unittest
from pathlib import Path

from inverse_engine.core import hexview
from inverse_engine.core.changeset import ChangeSet
from inverse_engine.core.patch_stack import PatchError, PatchStack
from inverse_engine.core.profile import RomProfile
from inverse_engine.core.rom_image import RomImage
from inverse_engine.research import names, profiler
from tests.fixture_cd import CdBuilder, make_slus, LOAD_ADDRESS
from tests.test_patch_stack import PROFILE, FINDINGS

ROOT = Path(__file__).resolve().parent.parent
TEXT_AT = 0x14000


def ram(off):
    return LOAD_ADDRESS + off - 0x800


def make_full_slus():
    """SLUS com armas, habilidades (204 ponteiros × 203 registros, entrada 143 inválida) e armaduras."""
    data = bytearray(make_slus(names={182: "Rebelrod", 1: "Espada1"}, size=0x18000))
    at = TEXT_AT
    for i in range(204):  # habilidades: 0x15A1C … 0x15D4C
        if i == 143:
            struct.pack_into("<I", data, 0x15A1C + 4 * i, 0)  # aponta para fora da faixa de textos
            continue
        txt = f"Tecnica{i:03d}".encode() + b"\x00"
        data[at:at + len(txt)] = txt
        struct.pack_into("<I", data, 0x15A1C + 4 * i, ram(at))
        at += len(txt)
    for i in range(203):  # coluna plantada: +0x05 múltiplos de 5 crescentes
        data[0x15D4C + 18 * i + 5] = (5 * (i + 1)) & 0xFF if i < 51 else 255
    for i in range(158):  # armaduras: 0x16D2C … 0x16FA4
        txt = f"Armadura{i:03d}".encode() + b"\x00"
        data[at:at + len(txt)] = txt
        struct.pack_into("<I", data, 0x16D2C + 4 * i, ram(at))
        at += len(txt)
        struct.pack_into("<H", data, 0x16FA4 + 26 * i + 4, 10 * i)
    assert at < 0x15A1C
    return bytes(data)


SKILLS = PROFILE.table("skills")
ARMORS = PROFILE.table("armors")
WEAPONS = PROFILE.table("weapons")


class NamesAnalysisTest(unittest.TestCase):
    def setUp(self):
        self.data = make_full_slus()

    def test_divergencia_204_por_203_exibida(self):
        rep = names.analyze(SKILLS, self.data)
        self.assertEqual((rep.pointer_count, rep.record_count, rep.divergence), (204, 203, 1))
        self.assertEqual(rep.invalid, [143])
        self.assertEqual(rep.runs, [(0, 0x15A1C, 143), (144, 0x15C5C, 60)])  # os números do LVCP
        self.assertIn("204 ponteiros × 203 registros", rep.summary())
        self.assertEqual([h.shift for h in rep.hypotheses], [0, 1])
        h0, h1 = rep.hypotheses
        self.assertEqual(h0.records_without_name, [143])
        self.assertEqual(h1.records_without_name, [142])
        self.assertEqual(h0.samples[0], (0, "Tecnica000"))
        self.assertEqual(h1.samples[0], (0, "Tecnica001"))

    def test_armaduras_sem_divergencia(self):
        rep = names.analyze(ARMORS, self.data)
        self.assertEqual((rep.pointer_count, rep.divergence, rep.invalid), (158, 0, []))
        self.assertEqual(ARMORS.read_name(self.data, 157), "Armadura157")

    def test_nada_gravado_sem_confirmacao(self):
        with tempfile.TemporaryDirectory() as d:
            prof = Path(d) / "perfil.json"
            shutil.copy(ROOT / "profiles" / "SLUS-00940-USA.json", prof)
            before = prof.read_text()
            db = copy.deepcopy(FINDINGS)
            with self.assertRaisesRegex(names.NamesError, "confirmação"):
                names.confirm_shift(prof, "skills", 1, db, "conferi no menu")
            with self.assertRaisesRegex(names.NamesError, "evidência"):
                names.confirm_shift(prof, "skills", 1, db, " ", confirmed=True)
            self.assertEqual(prof.read_text(), before)
            db.path = Path(d) / "f.json"
            names.confirm_shift(prof, "skills", 1, db, "nomes 0..5 conferidos no menu", confirmed=True)
            t = RomProfile.load(prof).table("skills")
            self.assertEqual(t.names_shift, 1)
            self.assertEqual(t.read_name(self.data, 0), "Tecnica001")
            self.assertIn("shift 1", db.get("S-0002")["evidence"][-1]["detail"])
            self.assertEqual(db.status("S-0002"), "HIPOTESE")  # evidência não promove sozinha


class TextEditTest(unittest.TestCase):
    def setUp(self):
        self.data = make_full_slus()
        self.image = RomImage.from_bytes(CdBuilder().build({"SLUS_009.40": self.data}))

    def test_menor_preenche_com_nul_e_maior_recusado(self):
        off, old, new = names.encode_name(WEAPONS, self.data, 182, "Rebel")
        self.assertEqual((old, new), (b"Rebelrod", b"Rebel\x00\x00\x00"))
        with self.assertRaisesRegex(names.NamesError, "realocar"):
            names.encode_name(WEAPONS, self.data, 182, "RebelrodXL")
        with self.assertRaisesRegex(names.NamesError, "ASCII"):
            names.encode_name(WEAPONS, self.data, 182, "Rébel")

    def test_trocar_nome_pelo_changeset(self):
        cs = ChangeSet("R").bind(self.image, PROFILE, FINDINGS)
        op = cs.set_name("weapons", 182, "Rodex")
        self.assertEqual((op.target, op.before, op.after), ("weapons[182].nome", "Rebelrod", "Rodex"))
        op2 = cs.set_name("weapons", 182, "Rod")
        self.assertEqual(op2.before, "Rodex")
        st = PatchStack(self.image, PROFILE, FINDINGS)
        for layer in cs.to_layers():
            st.add(layer)
        out = RomImage.from_bytes(st.build().data).read_file("SLUS_009.40")
        self.assertEqual(WEAPONS.read_name(out, 182), "Rod")
        cs.undo()
        self.assertEqual(cs.ops[-1].after, "Rodex")

    def test_nomes_em_hipotese_so_no_modo_pesquisa(self):
        cs = ChangeSet("R").bind(self.image, PROFILE, FINDINGS)
        with self.assertRaisesRegex(PatchError, "Modo Pesquisa"):
            cs.set_name("skills", 0, "Golpe")
        cs = ChangeSet("R").bind(self.image, PROFILE, FINDINGS, research_mode=True)
        self.assertEqual(cs.set_name("skills", 0, "Golpe").after, "Golpe")


class GenericTablesTest(unittest.TestCase):
    def setUp(self):
        self.data = make_full_slus()

    def test_mesmo_codigo_para_as_tres_tabelas(self):
        self.assertEqual({t: (PROFILE.table(t).stride, PROFILE.table(t).count) for t in ("weapons", "skills", "armors")},
                         {"weapons": (22, 215), "skills": (18, 203), "armors": (26, 158)})
        self.assertEqual(ARMORS.end, 0x16FA4 + 26 * 158)
        stats = {(s.offset, s.type): s for s in profiler.profile(SKILLS, self.data, skip=set())}
        self.assertIn("múltiplos de 5", stats[(5, "u8")].notes())
        astats = {(s.offset, s.type): s for s in profiler.profile(ARMORS, self.data, skip=set())}
        self.assertIn("múltiplos de 10", astats[(4, "u16le")].notes())

    def test_habilidades_so_com_bytes_desconhecidos(self):
        rows = hexview.record_view(SKILLS, self.data, 0, FINDINGS)
        self.assertEqual(len(rows), 18)
        self.assertTrue(all(r["campo"].startswith("byte_0x") and r["estado"] == "DESCONHECIDO" for r in rows))
        rows = hexview.record_view(ARMORS, self.data, 0, FINDINGS)
        self.assertEqual(len(rows), 26)

    def test_byte_cru_das_habilidades_so_no_modo_pesquisa(self):
        image = RomImage.from_bytes(CdBuilder().build({"SLUS_009.40": self.data}))
        cs = ChangeSet("R").bind(image, PROFILE, FINDINGS)
        with self.assertRaises(PatchError):
            cs.set_raw("SLUS_009.40", SKILLS.record_offset(10) + 5, b"\x63")
        cs = ChangeSet("R").bind(image, PROFILE, FINDINGS, research_mode=True)
        op = cs.set_raw("SLUS_009.40", SKILLS.record_offset(10) + 5, b"\x63")
        self.assertTrue(op.experimental)
        st = PatchStack(image, PROFILE, FINDINGS, research_mode=True)
        for layer in cs.to_layers():
            st.add(layer)
        self.assertEqual(st.field_label("SLUS_009.40", SKILLS.record_offset(10) + 5), "skills[10]+0x5")
        self.assertEqual(st.build().experimental, ["skills[10]+0x5"])

    def test_integridade_por_tabela(self):
        self.assertFalse(SKILLS.integrity(self.data))   # hash do LVCP é da tabela real
        self.assertFalse(WEAPONS.integrity(self.data))
        d = json.loads((ROOT / "profiles" / "SLUS-00940-USA.json").read_text())
        d["tables"]["skills"].pop("integrity_sha256")
        self.assertIsNone(RomProfile(d).table("skills").integrity(self.data))


if __name__ == "__main__":
    unittest.main()
