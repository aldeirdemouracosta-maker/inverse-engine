"""RomProfile: âncoras, tabelas genéricas e política de edição por estado do finding."""
import copy
import hashlib
import io
import json
import struct
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from inverse_engine import cli
from inverse_engine.core.profile import RomProfile, match_profiles
from inverse_engine.core.rom_image import RomImage
from inverse_engine.research.findings import FindingsDB, FindingError, edit_policy
from tests.fixture_cd import CdBuilder, make_slus

ROOT = Path(__file__).resolve().parent.parent
REAL_PROFILE = ROOT / "profiles" / "SLUS-00940-USA.json"
REAL_FINDINGS = ROOT / "research" / "findings" / "SLUS-00940-USA.json"


def synthetic_profile(slus: bytes) -> dict:
    """Perfil real com o hash de integridade trocado pelo da tabela sintética."""
    p = json.loads(REAL_PROFILE.read_text(encoding="utf-8"))
    for a in p["identify"]["anchors"]:
        if a["type"] == "sha256_range":
            off = int(a["offset"], 16)
            a["sha256"] = hashlib.sha256(slus[off:off + a["length"]]).hexdigest()
    p["profile_id"] = "SINTETICO"
    return p


class AnchorTest(unittest.TestCase):
    def setUp(self):
        self.slus = make_slus(names={182: "Rebelrod"}, values={(182, 0xA): struct.pack("<H", 30)})
        self.bin = CdBuilder().build({"SLUS_009.40": self.slus, "DATA/X.BIN": b"x"})
        self.image = RomImage.from_bytes(self.bin)

    def test_todas_as_ancoras_passam(self):
        m = RomProfile(synthetic_profile(self.slus)).evaluate(self.image)
        self.assertTrue(m.applies)
        self.assertTrue(m.integrity_ok)
        self.assertEqual(len(m.anchors), 3)
        self.assertTrue(all(a.ok for a in m.anchors))

    def test_required_falha_perfil_nao_se_aplica(self):
        slus = make_slus(names={182: "Outronome"})
        img = RomImage.from_bytes(CdBuilder().build({"SLUS_009.40": slus}))
        m = RomProfile(synthetic_profile(slus)).evaluate(img)
        self.assertFalse(m.applies)
        failed = [a for a in m.anchors if not a.ok]
        self.assertEqual([a.type for a in failed], ["catalog_name"])
        self.assertIn("Rebelrod", failed[0].detail)
        self.assertIn("NÃO se aplica", m.summary())

    def test_magic_errado_falha(self):
        slus = b"XX" + self.slus[2:]
        m = RomProfile(synthetic_profile(self.slus)).evaluate(RomImage.from_bytes(slus, "SLUS_009.40"))
        self.assertFalse(m.applies)

    def test_arquivo_ausente_falha_sem_excecao(self):
        img = RomImage.from_bytes(CdBuilder().build({"OUTRO.EXE": self.slus}))
        m = RomProfile(synthetic_profile(self.slus)).evaluate(img)
        self.assertFalse(m.applies)
        self.assertTrue(all("não existe" in a.detail for a in m.anchors))

    def test_tabela_alterada_por_patch_so_avisa(self):
        # Simula um patch base (ex.: PPF) que muda um byte dentro da tabela de armas.
        patched = bytearray(self.slus)
        patched[0xB5C + 22 * 10 + 3] ^= 0xFF
        img = RomImage.from_bytes(CdBuilder().build({"SLUS_009.40": bytes(patched)}))
        m = RomProfile(synthetic_profile(self.slus)).evaluate(img)
        self.assertTrue(m.applies)
        self.assertFalse(m.integrity_ok)
        self.assertIn("confirmar", m.summary())

    def test_perfil_real_hash_integridade_nao_bate_com_sintetico(self):
        m = RomProfile.load(REAL_PROFILE).evaluate(self.image)
        self.assertTrue(m.applies)          # PS-X EXE + Rebelrod plantados
        self.assertFalse(m.integrity_ok)    # hash do LVCP é da tabela real

    def test_executavel_avulso_com_outro_nome(self):
        img = RomImage.from_bytes(self.slus, "slus_copia.exe")
        m = RomProfile(synthetic_profile(self.slus)).evaluate(img)
        self.assertTrue(m.applies and m.integrity_ok)

    def test_imagem_conhecida_pelo_hash_inteiro_so_registra(self):
        p = synthetic_profile(self.slus)
        p["known_images"] = [{"kind": "bin", "sha256": self.image.sha256, "note": "BIN de teste"}]
        m = RomProfile(p).evaluate(self.image)
        self.assertEqual(m.known_image, "BIN de teste")
        p["identify"]["anchors"][2]["name"] = "Nada"
        self.assertFalse(RomProfile(p).evaluate(self.image).applies)  # hash inteiro não decide

    def test_varios_perfis_ordenados(self):
        good = RomProfile(synthetic_profile(self.slus))
        bad_d = synthetic_profile(self.slus)
        bad_d["profile_id"] = "AAA-OUTRO"
        bad_d["identify"]["anchors"][0]["hex"] = "00"
        ms = match_profiles(self.image, [RomProfile(bad_d), good])
        self.assertEqual([m.profile_id for m in ms], ["SINTETICO", "AAA-OUTRO"])


class TableTest(unittest.TestCase):
    def setUp(self):
        self.slus = make_slus(names={182: "Rebelrod", 1: "Espada1"},
                              values={(182, 0xA): struct.pack("<H", 30), (182, 0x7): b"\x03"})
        self.profile = RomProfile.load(REAL_PROFILE)

    def test_le_campos_e_nomes(self):
        t = self.profile.table("weapons")
        self.assertEqual(t.read_field(self.slus, 182, "attack"), 30)
        self.assertEqual(t.read_field(self.slus, 182, "range"), 3)
        self.assertEqual(t.read_name(self.slus, 1), "Espada1")
        self.assertEqual(t.field_offset(182, "attack"), 0xB5C + 182 * 22 + 0xA)
        self.assertEqual(len(t.read_record(self.slus, 0)), 22)
        self.assertEqual(t.end, 0xB5C + 215 * 22)

    def test_grupos(self):
        t = self.profile.table("weapons")
        self.assertEqual(t.category(1), "espada")
        self.assertEqual(t.category(182), "especial")
        self.assertIsNone(t.category(0))

    def test_indice_fora_recusado(self):
        with self.assertRaises(IndexError):
            self.profile.table("weapons").record_offset(215)

    def test_campo_fora_do_registro_recusado(self):
        d = json.loads(REAL_PROFILE.read_text(encoding="utf-8"))
        d["tables"]["weapons"]["fields"]["ruim"] = {"offset": "0x15", "type": "u16le"}
        with self.assertRaises(ValueError):
            RomProfile(d)

    def test_mesmo_codigo_para_habilidades(self):
        s = self.profile.table("skills")
        self.assertEqual((s.offset, s.stride, s.count), (0x15D4C, 18, 203))
        self.assertEqual(s.fields, {})
        self.assertEqual(s.end, 0x16B92)  # fim informado pelo LVCP


class FindingsPolicyTest(unittest.TestCase):
    def setUp(self):
        self.db = FindingsDB.load(REAL_FINDINGS)

    def test_estado_inicial(self):
        st = self.db.status
        self.assertEqual(st("F-0001"), "CONFIRMADO")
        self.assertEqual(st("F-0011"), "PROVAVEL")
        self.assertEqual(st("F-0015"), "PROVAVEL")
        for f in ("F-0010", "F-0012", "F-0013", "F-0014", "F-0016", "S-0002"):
            self.assertEqual(st(f), "HIPOTESE", f)
        self.assertEqual(st("S-0003"), "DESCONHECIDO")
        self.assertEqual(st("NAO-EXISTE"), "DESCONHECIDO")

    def test_politica_por_estado(self):
        self.assertTrue(edit_policy("CONFIRMADO").editable)
        p = edit_policy("PROVAVEL")
        self.assertTrue(p.editable and p.badge)
        self.assertFalse(edit_policy("HIPOTESE").editable)
        p = edit_policy("HIPOTESE", research_mode=True)
        self.assertTrue(p.editable and p.experimental)
        self.assertFalse(edit_policy("DESCONHECIDO").editable)
        self.assertFalse(edit_policy("DESCONHECIDO").raw_only)
        p = edit_policy("DESCONHECIDO", research_mode=True)
        self.assertFalse(p.editable)
        self.assertTrue(p.raw_only)

    def test_campos_do_perfil_seguem_politica(self):
        t = RomProfile.load(REAL_PROFILE).table("weapons")
        self.assertTrue(self.db.policy(t.fields["attack"].finding).editable)
        self.assertFalse(self.db.policy(t.fields["price"].finding).editable)
        self.assertTrue(self.db.policy(t.fields["price"].finding, research_mode=True).editable)

    def test_promover_exige_evidencia_rebaixar_nao(self):
        db = copy.deepcopy(self.db)
        with self.assertRaises(FindingError):
            db.set_status("F-0012", "PROVAVEL", "sem prova")
        self.assertEqual(db.status("F-0012"), "HIPOTESE")
        db.set_status("F-0012", "PROVAVEL", "preços batem",
                      {"kind": "statistical_match", "detail": "sintético"})
        self.assertEqual(db.status("F-0012"), "PROVAVEL")
        self.assertEqual(db.get("F-0012")["history"][-1]["to"], "PROVAVEL")
        db.set_status("F-0011", "HIPOTESE", "rebaixado")
        self.assertEqual(db.status("F-0011"), "HIPOTESE")
        with self.assertRaises(FindingError):
            db.add_evidence("F-0011", "palpite", "x")

    def test_salvar_e_recarregar_identico(self):
        with tempfile.TemporaryDirectory() as d:
            p = self.db.save(Path(d) / "f.json")
            self.assertEqual(FindingsDB.load(p).findings, self.db.findings)


class CliTest(unittest.TestCase):
    def test_abrir_mostra_cada_ancora(self):
        slus = make_slus(names={182: "Rebelrod"})
        with tempfile.TemporaryDirectory() as d:
            binp = Path(d) / "teste.bin"
            binp.write_bytes(CdBuilder().build({"SLUS_009.40": slus, "DATA/A.BIN": b"a"}))
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cli.main(["abrir", str(binp)]), 0)
            text = out.getvalue()
            self.assertIn("SLUS-00940-USA", text)
            self.assertEqual(text.count("[OK ]"), 2)
            self.assertEqual(text.count("[FALHOU]"), 1)  # integridade: tabela sintética ≠ real
            self.assertIn("DATA/A.BIN", text)
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cli.main(["tabela", str(binp), "weapons", "--id", "182"]), 0)
            self.assertIn("Rebelrod", out.getvalue())
            self.assertIn("AVISO", out.getvalue())


if __name__ == "__main__":
    unittest.main()
