"""Confere a consistência entre o perfil SLUS-00940-USA e o banco de findings."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "profiles" / "SLUS-00940-USA.json"
FINDINGS = ROOT / "research" / "findings" / "SLUS-00940-USA.json"
STATES = {"CONFIRMADO", "PROVAVEL", "HIPOTESE", "DESCONHECIDO"}


class ProfileDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        cls.findings = {f["id"]: f for f in json.loads(FINDINGS.read_text(encoding="utf-8"))["findings"]}

    def test_estados_validos(self):
        for f in self.findings.values():
            self.assertIn(f["status"], STATES, f["id"])

    def test_promovido_tem_evidencia(self):
        for f in self.findings.values():
            if f["status"] in ("CONFIRMADO", "PROVAVEL"):
                self.assertTrue(f["evidence"], f["id"])

    def test_todo_campo_aponta_para_finding(self):
        for name, table in self.profile["tables"].items():
            self.assertIn(table["finding"], self.findings, name)
            for field, spec in table["fields"].items():
                self.assertIn(spec["finding"], self.findings, f"{name}.{field}")
                f = self.findings[spec["finding"]]
                self.assertEqual(int(spec["offset"], 16), int(f["record_offset"], 16), f"{name}.{field}")
                self.assertEqual(spec["type"], f["type"], f"{name}.{field}")

    def test_campos_cabem_no_registro(self):
        sizes = {"u8": 1, "u16le": 2, "u32le": 4}
        for name, table in self.profile["tables"].items():
            for field, spec in table["fields"].items():
                self.assertLessEqual(int(spec["offset"], 16) + sizes[spec["type"]], table["stride"], f"{name}.{field}")

    def test_grupos_de_armas_contiguos(self):
        groups = self.profile["tables"]["weapons"]["groups"]
        for a, b in zip(groups, groups[1:]):
            self.assertEqual(a["end"] + 1, b["start"])
        self.assertLess(groups[-1]["end"], self.profile["tables"]["weapons"]["count"])

    def test_ancoras_obrigatorias_existem(self):
        ident = self.profile["identify"]
        kinds = {a["type"] for a in ident["anchors"]}
        for k in ident["required"] + ident["table_integrity"]:
            self.assertIn(k, kinds)

    def test_armaduras_sem_nomes_de_campo(self):
        self.assertEqual(self.profile["tables"]["armors"]["fields"], {})
        for i in range(26):
            self.assertEqual(self.findings["A-%04d" % (0x10 + i)]["status"], "DESCONHECIDO")
        # A-0002 subiu para PROVAVEL com a evidência da BIN real; CONFIRMADO só com o portão P3.
        self.assertIn(self.findings["A-0002"]["status"], ("HIPOTESE", "PROVAVEL"))
        self.assertTrue(self.findings["A-0002"]["evidence"])

    def test_habilidades_sem_nomes_de_campo(self):
        self.assertEqual(self.profile["tables"]["skills"]["fields"], {})
        for i in range(18):
            f = self.findings["S-%04d" % (0x10 + i)]
            # Sem nome de campo no perfil; sair de DESCONHECIDO só com evidência e no máximo até HIPOTESE.
            self.assertIn(f["status"], ("DESCONHECIDO", "HIPOTESE"))
            if f["status"] == "HIPOTESE":
                self.assertTrue(f["evidence"])


if __name__ == "__main__":
    unittest.main()
