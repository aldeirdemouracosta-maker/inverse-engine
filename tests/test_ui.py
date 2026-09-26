"""Interface: temas (WCAG AA), tipos de arquivo, terminal equivalente e o fluxo no PySide6 (offscreen)."""
import os
import struct
import tempfile
import unittest
from pathlib import Path

from inverse_engine.core import filetypes
from inverse_engine.formats import png, ppf
from inverse_engine.ui import terminal, theme
from tests.fixture_cd import make_slus
from tests.test_patch_stack import cd, files, TIM, slus_with, ATTACK_182

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QMetaMethod, Qt
    from PySide6.QtWidgets import (QAbstractButton, QAbstractItemView, QApplication, QComboBox, QLineEdit,
                                   QPlainTextEdit, QPushButton, QSpinBox, QWidget)
    _APP = QApplication.instance() or QApplication([])
    HAS_QT = True
except Exception:  # PySide6 ausente ou sem bibliotecas do sistema: testes de interface pulados
    HAS_QT = False


class ThemeTest(unittest.TestCase):
    def test_todos_os_temas_passam_em_wcag_aa(self):
        self.assertEqual(set(theme.available()), {"simples", "fantasia"})
        for name in theme.available():
            self.assertEqual(theme.check(theme.load(name)), [], name)

    def test_contraste_conhecido(self):
        self.assertAlmostEqual(theme.contrast("#000000", "#FFFFFF"), 21.0, places=1)
        self.assertAlmostEqual(theme.contrast("#777777", "#FFFFFF"), 4.48, places=2)
        bad = {"cores": dict(theme.load("simples")["cores"], texto_suave="#333333")}
        self.assertTrue(theme.check(bad))

    def test_arte_e_arquivo_configuravel_nao_embutido(self):
        t = theme.load("fantasia")
        self.assertEqual(t["fundo_arte"], "fantasia_fundo.png")
        self.assertFalse(any(p.suffix in (".png", ".jpg") for p in theme.THEMES_DIR.iterdir()))
        self.assertIsNone(theme.art_path(t))  # sem arte no repositório: o tema funciona sem ela
        self.assertIn("font-size: 14pt", theme.stylesheet(t, 14))


class FileTypesTest(unittest.TestCase):
    def test_tipo_pelo_conteudo(self):
        self.assertEqual(filetypes.detect(make_slus()), "PS-EXE")
        self.assertEqual(filetypes.detect(TIM), "TIM")
        self.assertEqual(filetypes.detect(struct.pack("<I", 0x41) + b"\x00" * 8), "TMD")
        self.assertEqual(filetypes.detect(b"pBAV" + b"\x00" * 20), "VAB")
        self.assertEqual(filetypes.detect(b"BOOT = cdrom:\\SLUS_009.40;1\r\n"), "SYSTEM.CNF")
        self.assertEqual(filetypes.detect(b"\x00" * 50 + TIM), "contém TIM")
        self.assertEqual(filetypes.detect(bytes(range(256))), "desconhecido")
        self.assertEqual(filetypes.detect(b"", form2=True), "STR/XA (Form 2)")
        self.assertEqual(filetypes.detect(b"", is_dir=True), "pasta")


class TerminalTest(unittest.TestCase):
    def test_comandos_com_aspas_seguras(self):
        self.assertEqual(terminal.abrir("Vandal Hearts II (USA).cue"),
                         "python3 -m inverse_engine.cli abrir 'Vandal Hearts II (USA).cue'")
        self.assertEqual(terminal.campo("p.vh2proj.json", "weapons", 182, "attack", 45),
                         "python3 -m inverse_engine.cli projeto campo p.vh2proj.json weapons 182 attack 45")
        self.assertIn("sha256sum", terminal.hash_arquivo("x.bin"))


def json_status(path):
    import json
    return {f["id"]: f["status"] for f in json.loads(path.read_text(encoding="utf-8"))["findings"]}


def repo_profile_shift(table):
    import json
    d = json.loads((Path(__file__).resolve().parent.parent / "profiles" / "SLUS-00940-USA.json").read_text())
    return d["tables"][table].get("names", {}).get("shift", 0)


@unittest.skipUnless(HAS_QT, "PySide6 indisponível")
class UiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["INVERSE_ENGINE_CONFIG"] = str(Path(self.tmp.name) / "config")
        from inverse_engine.ui.app import App
        self.app = App()
        root = Path(self.tmp.name)
        self.bin = root / "Vandal Hearts II (USA).bin"
        self.bin.write_bytes(cd())

    def tearDown(self):
        self.app.close()
        self.app.deleteLater()
        self.tmp.cleanup()
        os.environ.pop("INVERSE_ENGINE_CONFIG", None)

    @staticmethod
    def _internal(w):
        """Peças internas do Qt (lista do QComboBox, barras de rolagem etc.), não controles do app."""
        p = w.parent()
        while p is not None:
            if "Private" in type(p).__name__ or isinstance(p, (QComboBox, QAbstractItemView)):
                return True
            p = p.parent()
        return False

    def interactive(self, root):
        kinds = (QAbstractButton, QAbstractItemView, QComboBox, QLineEdit, QPlainTextEdit, QSpinBox)
        return [w for w in root.findChildren(QWidget) if isinstance(w, kinds) and not self._internal(w)
                and not w.objectName().startswith("qt_") and w.parent() is not None
                and type(w.parent()).__name__ not in ("QTabBar", "QDockWidget", "QScrollBar", "QHeaderView",
                                                      "QTableCornerButton", "QComboBox", "QCalendarWidget")]

    def test_menu_botoes_ligados_com_nome_e_atalho(self):
        buttons = self.app.menu.findChildren(QPushButton)
        self.assertGreaterEqual(len(buttons), 8)
        for b in buttons:
            signal = QMetaMethod.fromSignal(b.clicked)
            self.assertTrue(b.accessibleName(), b.text())
            self.assertIn("&", b.text(), "atalho de teclado visível")
            if b.isEnabled():
                self.assertTrue(b.isSignalConnected(signal), f"botão sem ação: {b.text()}")
            else:
                self.assertIn("marco", b.toolTip())  # desativado explica quando chega

    def test_fluxo_completo_no_workspace(self):
        p = self.app.start_project(self.bin, Path(self.tmp.name) / "proj", "Rebalance")
        ws = self.app.workspace
        self.assertIs(self.app.stack.currentWidget(), ws)
        self.assertEqual(p.profile_id, "SLUS-00940-USA")
        # acessibilidade em todos os controles do workspace
        for w in self.interactive(ws):
            self.assertTrue(w.accessibleName(), f"{type(w).__name__} sem nome acessível")
        # arquivos com tipo pelo conteúdo
        items = ws.files.findItems("SLUS_009.40", Qt.MatchRecursive)
        self.assertEqual(items[0].text(1), "PS-EXE")
        self.assertEqual(ws.files.findItems("SPR.BIN", Qt.MatchRecursive)[0].text(1), "contém TIM")
        # tabela de armas
        self.assertEqual(ws.grid.rowCount(), 215)
        headers = [ws.grid.horizontalHeaderItem(c).text() for c in range(ws.grid.columnCount())]
        col = headers.index("attack\n(provável)")
        price_col = next(i for i, h in enumerate(headers) if h.startswith("price"))
        self.assertFalse(ws.grid.item(1, price_col).flags() & Qt.ItemIsEditable)  # hipótese fora do Modo Pesquisa
        ws.grid.item(182, col).setText("45")
        self.assertEqual(len(p.changesets["Alterações"].ops), 1)
        self.assertIn("projeto campo", ws.term_view.toPlainText())
        self.assertEqual(ws.history.count(), 1)
        ws.grid.item(182, col).setText("99999")  # não cabe em u16
        self.assertEqual(ws.grid.item(182, col).text(), "45")
        self.assertIn("Recusado", ws.log_view.toPlainText())
        ws.undo()
        self.assertEqual(ws.grid.item(182, col).text(), "30")
        ws.redo()
        self.assertEqual(ws.grid.item(182, col).text(), "45")
        # inspetor mostra o registro
        ws._record_selected(182)
        self.assertIn("attack", ws.inspector.toPlainText())
        # gráficos
        ws.scan_tims(sync=True)
        self.assertEqual(ws.tim_list.count(), 2)
        ws.tim_list.setCurrentRow(0)
        self.assertFalse(ws.preview.pixmap().isNull())
        out_png = ws.export_png(str(Path(self.tmp.name) / "t.png"))
        img = png.read(out_png.read_bytes())
        img.palette[1] = (255, 0, 255, 255)
        new_png = Path(self.tmp.name) / "t2.png"
        new_png.write_bytes(png.write_indexed(img.width, img.height, img.rows, img.palette))
        ws.import_png("cores", str(new_png))
        self.assertEqual(len(p.changesets["Alterações"].ops), 2)
        # camada PPF e conflito (P4)
        bad = Path(self.tmp.name) / "conflito.ppf"
        bad.write_bytes(ppf.build_ppf3(cd(), cd(slus_with([(ATTACK_182, struct.pack("<H", 99))]))))
        ws.add_patch(str(bad))
        self.assertEqual(ws.layers.count(), 2)
        self.assertTrue(any("CONFLITO" in ws.conflicts.item(i).text() for i in range(ws.conflicts.count())))
        # exportação (P2 + P4 confirmados)
        ws.review_and_export(auto_confirm=True)
        res = ws.last_export
        self.assertTrue(res.files["imagem"].exists())
        self.assertIn("reproduzir", ws.term_view.toPlainText())
        # desativar camada pelo painel
        ws.layers.item(0).setCheckState(Qt.Unchecked)
        self.assertFalse(p.patches["conflito.ppf"].active)
        # voltar ao menu salva layout e aparece nos recentes
        ws.go_back()
        self.assertIs(self.app.stack.currentWidget(), self.app.menu)
        self.assertEqual(self.app.menu.recent_list.count(), 1)
        self.assertIn("layout", p.ui)
        # reabrir o projeto pelo recente
        self.app.open_project(p.path)
        self.assertEqual(ws.grid.item(182, col).text(), "45")

    def test_modo_pesquisa(self):
        import shutil
        from tests.test_research import planted
        from tests.fixture_cd import CdBuilder
        root = Path(self.tmp.name)
        fdir = root / "findings"
        fdir.mkdir()
        shutil.copy(Path(__file__).resolve().parent.parent / "research" / "findings" / "SLUS-00940-USA.json", fdir)
        b = root / "pesquisa.bin"
        b.write_bytes(CdBuilder().build(dict(files(), **{"SLUS_009.40": planted()})))
        p = self.app.start_project(b, root / "p3", "Pesquisa")
        p.findings_dir = fdir  # nunca gravar nos findings do repositório durante os testes
        ws = self.app.workspace
        ws.load_project(p)
        self.assertFalse(ws.tabs.isTabEnabled(ws.research_tab_index))
        ws.research.setChecked(True)
        self.assertTrue(ws.tabs.isTabEnabled(ws.research_tab_index))
        for w in self.interactive(ws):
            self.assertTrue(w.accessibleName(), f"{type(w).__name__} sem nome acessível")
        ws.run_profiler()
        self.assertEqual(ws.profile_grid.rowCount(), 43)
        csv = root / "gabarito.csv"
        csv.write_text("id,atributo,valor,fonte\n" + "".join(f"{i},poder,{100 + i},teste\n" for i in range(10, 22)))
        ws.import_gabarito(str(csv))
        self.assertEqual(ws.proposals.count(), 1)
        ws.apply_proposals()
        self.assertEqual(ws.findings_db.status("F-0100"), "PROVAVEL")
        self.assertEqual(p.findings().status("F-0100"), "PROVAVEL")  # gravado na cópia
        ws.r_offset.setValue(0x05)
        ws.r_text.setText("nível mínimo?")
        ws.mark_hypothesis()
        self.assertEqual(ws.findings_db.get("F-0101")["status"], "HIPOTESE")
        ws.r_index.setValue(182)
        ws.r_offset.setValue(0x0C)
        ws.r_type.setCurrentText("u16le")
        ws.r_value.setValue(999)
        res = ws.make_test_bin()
        self.assertTrue(res.image.exists())
        self.assertIn("teste-campo", ws.term_view.toPlainText())
        self.assertFalse(ws.promote("F-0101", "CONFIRMADO", "in_game_test", "vi no menu"))  # sem confirmar (P3)
        self.assertTrue(ws.promote("F-0101", "CONFIRMADO", "in_game_test", "vi no menu", confirmed=True))
        self.assertEqual(ws.findings_db.status("F-0101"), "CONFIRMADO")
        self.assertFalse(ws.promote("F-0012", "PROVAVEL", "in_game_test", ""))  # promover sem evidência
        self.assertTrue(ws.promote("F-0011", "HIPOTESE", "in_game_test", ""))   # rebaixar sempre pode
        ws.register_tims()
        self.assertTrue(ws.findings_db.find(subject="graphics.tim"))
        ws.tabs.setCurrentIndex(1)
        ws.tim_list.setCurrentRow(0)
        self.assertTrue(ws.recolor_test().image.exists())
        repo = json_status(Path(__file__).resolve().parent.parent / "research" / "findings" / "SLUS-00940-USA.json")
        self.assertEqual(repo["F-0011"], "PROVAVEL")  # repositório intocado

    def test_habilidades_nomes_e_bytes_crus(self):
        import shutil
        from tests.test_tables_names import make_full_slus
        from tests.fixture_cd import CdBuilder
        root = Path(self.tmp.name)
        for sub, src in (("perfis", "profiles/SLUS-00940-USA.json"), ("findings", "research/findings/SLUS-00940-USA.json")):
            (root / sub).mkdir()
            shutil.copy(Path(__file__).resolve().parent.parent / src, root / sub)
        b = root / "tabelas.bin"
        b.write_bytes(CdBuilder().build({"SLUS_009.40": make_full_slus()}))
        p = self.app.start_project(b, root / "p4", "Tabelas")
        p.findings_dir, p.profiles_dir = root / "findings", root / "perfis"  # nunca gravar no repositório
        ws = self.app.workspace
        ws.load_project(p)
        ws.table_combo.setCurrentText("skills")
        self.assertEqual(ws.grid.columnCount(), 3)                     # sem campos e sem Modo Pesquisa
        self.assertEqual(ws.grid.item(0, 1).text(), "Tecnica000")
        self.assertFalse(ws.grid.item(0, 1).flags() & Qt.ItemIsEditable)  # nomes em hipótese
        ws.research.setChecked(True)
        self.assertEqual(ws.grid.columnCount(), 3 + 18)
        ws.grid.item(10, 3 + 5).setText("99")
        op = p.changesets["Alterações"].ops[-1]
        self.assertEqual((op.kind, op.target), ("raw", "SLUS_009.40+0x%X" % (0x15D4C + 18 * 10 + 5)))
        self.assertEqual(ws.grid.item(10, 3 + 5).text(), "99")
        ws.grid.item(10, 3 + 5).setText("300")                        # byte cru só 0..255
        self.assertIn("Recusado", ws.log_view.toPlainText())
        rep = ws.names_report()
        self.assertEqual((rep.pointer_count, rep.record_count), (204, 203))
        self.assertFalse(ws.names_confirm("skills", 1, "conferi", confirmed=False))
        self.assertTrue(ws.names_confirm("skills", 1, "nomes conferidos no menu", confirmed=True))
        self.assertEqual(ws.grid.item(0, 1).text(), "Tecnica001")
        self.assertEqual(repo_profile_shift("skills"), 0)                 # repositório intocado
        ws.table_combo.setCurrentText("weapons")
        ws.research.setChecked(False)
        ws.grid.item(182, 1).setText("Rodex")
        self.assertEqual(p.changesets["Alterações"].ops[-1].target, "weapons[182].nome")
        ws.grid.item(182, 1).setText("NomeGrandeDemais")
        self.assertIn("realocar", ws.log_view.toPlainText())
        self.assertEqual(ws.grid.item(182, 1).text(), "Rodex")

    def test_cheats_e_memory_card(self):
        from inverse_engine.formats import memcard
        from tests.test_cheats_memcard import make_mcs
        root = Path(self.tmp.name)
        p = self.app.start_project(self.bin, root / "p5", "Cheats")
        ws = self.app.workspace
        self.app.show_menu()
        self.app.open_cheats()                      # botão do menu com projeto aberto
        self.assertEqual(ws.tabs.currentIndex(), ws.cheats_tab_index)
        ws.c_table.setCurrentText("weapons")
        ws.c_index.setValue(182)
        ws.c_field.setCurrentText("attack")
        ws.c_value.setValue(45)
        self.assertIsNone(ws.add_cheat())           # sem record_ram com evidência
        self.assertIn("Cheat recusado", ws.log_view.toPlainText())
        ws.research.setChecked(True)
        c = ws.add_cheat()
        self.assertTrue(c.experimental)
        self.assertIn(c.lines[0], ws.cheat_view.toPlainText())
        self.assertIn("cheat", ws.term_view.toPlainText())
        out = ws.export_cheats("cht", str(root / "vh2.cht"))
        self.assertIn("Type = Gameshark", out.read_text())
        card = root / "cartao.mcr"
        blank = memcard.MemCard.blank()
        blank.import_mcs(make_mcs())
        card.write_bytes(blank.to_bytes())
        ws.open_memcard(str(card))
        self.assertEqual(ws.mc_list.count(), 1)
        ws.mc_list.setCurrentRow(0)
        self.assertFalse(ws.mc_icon.pixmap().isNull())
        mcs = ws.export_save(str(root / "save.mcs"))
        self.assertEqual(mcs.read_bytes(), make_mcs())
        ws.import_save(str(mcs))                    # duplicado: recusado
        self.assertIn("recusada", ws.log_view.toPlainText())
        other = root / "outro.mcs"
        other.write_bytes(make_mcs(b"BASLUS-00940OUTRO", 1, 9))
        ws.import_save(str(other))
        self.assertEqual(ws.mc_list.count(), 2)
        self.assertEqual(memcard.MemCard(card.read_bytes()).saves().__len__(), 1)  # original intocado
        copy_path = ws.save_memcard(str(root / "novo.mcr"))
        self.assertEqual(len(memcard.MemCard(copy_path.read_bytes()).saves()), 2)

    def test_sem_perfil_so_formatos_genericos(self):
        other = Path(self.tmp.name) / "outro.bin"
        from tests.fixture_cd import CdBuilder
        other.write_bytes(CdBuilder().build({"DATA/A.TIM": TIM}))
        p = self.app.start_project(other, Path(self.tmp.name) / "p2", "Outro")
        self.assertIsNone(p.profile_id)
        ws = self.app.workspace
        self.assertFalse(ws.tabs.isTabEnabled(0))
        self.assertEqual(ws.files.findItems("A.TIM", Qt.MatchRecursive)[0].text(1), "TIM")


if __name__ == "__main__":
    unittest.main()
