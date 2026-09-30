"""Executável empacotado: perfis e findings copiados para a pasta do usuário sem sobrescrever."""
import tempfile
import unittest
from pathlib import Path

from inverse_engine.core import resources


class ResourcesTest(unittest.TestCase):
    def test_fora_do_executavel_usa_o_repositorio(self):
        self.assertFalse(resources.frozen())
        self.assertEqual(resources.DATA_ROOT, resources.SOURCE_ROOT)
        self.assertTrue((resources.DATA_ROOT / "profiles" / "SLUS-00940-USA.json").is_file())

    def test_pasta_de_dados_por_sistema(self):
        w = resources.user_data_dir({"APPDATA": "C:/U/AppData/Roaming"}, "win32")
        self.assertEqual(w, Path("C:/U/AppData/Roaming") / "InverseEngine")
        l = resources.user_data_dir({"XDG_DATA_HOME": "/x/share"}, "linux")
        self.assertEqual(l, Path("/x/share/inverse-engine"))

    def test_copia_so_o_que_falta(self):
        with tempfile.TemporaryDirectory() as t:
            src, dst = Path(t) / "src", Path(t) / "dst"
            (src / "profiles").mkdir(parents=True)
            (src / "research" / "findings").mkdir(parents=True)
            (src / "profiles" / "p.json").write_text("novo", encoding="utf-8")
            (src / "research" / "findings" / "f.json").write_text("embutido", encoding="utf-8")
            (dst / "research" / "findings").mkdir(parents=True)
            (dst / "research" / "findings" / "f.json").write_text("do usuário", encoding="utf-8")
            resources.seed(src, dst)
            self.assertEqual((dst / "profiles" / "p.json").read_text(encoding="utf-8"), "novo")
            self.assertEqual((dst / "research" / "findings" / "f.json").read_text(encoding="utf-8"), "do usuário")


class EntryTest(unittest.TestCase):
    def test_comando_vai_para_o_terminal(self):
        import contextlib, io
        from inverse_engine.__main__ import main
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(main(["abrir", "/nao/existe.cue"]), 2)
        self.assertIn("Erro:", err.getvalue())


if __name__ == "__main__":
    unittest.main()
