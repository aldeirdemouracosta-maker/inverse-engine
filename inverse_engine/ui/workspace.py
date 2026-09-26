"""EditorWorkspaceState: workspace com painéis (QDockWidget) sobre o núcleo.

A interface só apresenta o núcleo: toda escrita passa pelo ChangeSet; toda saída pelo export (P2);
conflitos e arquivos alterados são reconhecidos no diálogo P4. Cada ação mostra o comando equivalente.
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt, Signal
from PySide6.QtGui import QAction, QFont, QKeySequence, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDockWidget,
                               QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
                               QTableWidget, QTableWidgetItem, QTabWidget, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from inverse_engine.core import filetypes, hexview
from inverse_engine.core.export import export, output_paths, ExportError
from inverse_engine.core.patch_stack import GraphicEdit, PatchError
from inverse_engine.core.project import Project, ProjectError
from inverse_engine.formats import tim
from inverse_engine.research import gabarito, profiler, testbin
from inverse_engine.research.findings import EVIDENCE_KINDS, STATES, FindingError
from inverse_engine.ui import recent, terminal
from inverse_engine.ui.worker import Task, run_sync

MONO = QFont("Monospace")
MONO.setStyleHint(QFont.TypeWriter)
TOOLS = ["duckstation", "duckstation-qt", "pcsx-redux", "ollama", "ghidraRun", "flatpak"]


def _btn(text: str, slot, tip: str = "") -> QPushButton:
    b = QPushButton(text)
    b.setAccessibleName(text.replace("&", "").rstrip("…"))
    if tip:
        b.setToolTip(tip)
    b.clicked.connect(lambda _checked=False: slot())  # não repassa o bool do clicked
    return b


class Workspace(QMainWindow):
    back = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDockNestingEnabled(True)
        self.project: Project | None = None
        self.image = None
        self.cs_name: str | None = None
        self.tims: list[tuple[str, tim.TimInfo]] = []
        self._task: Task | None = None
        self._build_central()
        self._build_docks()
        self._build_actions()
        docks = {d.windowTitle(): d for d in self.findChildren(QDockWidget)}
        self.resizeDocks([docks["Arquivos do CD"], docks["Inspetor"]], [340, 420], Qt.Horizontal)
        self.resizeDocks([docks["Console"]], [150], Qt.Vertical)
        self._default_layout = self.saveState()

    # ------------------------------------------------------------------ montagem
    def _build_central(self) -> None:
        self.tabs = QTabWidget()
        self.tabs.setAccessibleName("Áreas de trabalho")
        self.setCentralWidget(self.tabs)
        # Tabelas
        w = QWidget()
        v = QVBoxLayout(w)
        top = QHBoxLayout()
        self.table_combo = QComboBox()
        self.table_combo.setAccessibleName("Tabela do perfil")
        self.table_combo.currentTextChanged.connect(lambda _t: self.fill_table())
        self.research = QCheckBox("Modo &Pesquisa (edita hipóteses; operações experimentais)")
        self.research.setAccessibleName("Modo Pesquisa")
        self.research.toggled.connect(self._toggle_research)
        top.addWidget(QLabel("Tabela:"))
        top.addWidget(self.table_combo)
        top.addWidget(self.research)
        top.addWidget(_btn("&Nomes…", self.names_dialog, "Analisa a matriz de ponteiros de nomes (nada é gravado sem confirmar)"))
        top.addStretch(1)
        v.addLayout(top)
        self.grid = QTableWidget()
        self.grid.setAccessibleName("Registros da tabela")
        self.grid.verticalHeader().setVisible(False)  # o id já é a primeira coluna (começa em 0)
        self.grid.setWordWrap(False)
        self.grid.itemChanged.connect(self._cell_changed)
        self.grid.currentCellChanged.connect(lambda r, c, *_: self._record_selected(r))
        v.addWidget(self.grid)
        self.tabs.addTab(w, "&Tabelas")
        # Gráficos
        w = QWidget()
        v = QVBoxLayout(w)
        row = QHBoxLayout()
        row.addWidget(_btn("Procurar &TIMs", self.scan_tims, "Procura imagens TIM em todos os arquivos"))
        self.palette_combo = QComboBox()
        self.palette_combo.setAccessibleName("Paleta")
        self.palette_combo.currentIndexChanged.connect(lambda _i: self._tim_selected())
        row.addWidget(QLabel("Paleta:"))
        row.addWidget(self.palette_combo)
        row.addStretch(1)
        v.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(_btn("Exportar PNG…", self.export_png))
        row.addWidget(_btn("Importar desenho…", lambda: self.import_png("desenho"),
                           "PNG do mesmo tamanho, só com cores da paleta"))
        row.addWidget(_btn("Importar cores…", lambda: self.import_png("cores"),
                           "PNG indexado: troca só a paleta; pixels não mudam"))
        row.addStretch(1)
        v.addLayout(row)
        h = QHBoxLayout()
        self.tim_list = QListWidget()
        self.tim_list.setAccessibleName("TIMs encontrados")
        self.tim_list.currentRowChanged.connect(lambda _r: self._tim_selected())
        h.addWidget(self.tim_list, 1)
        self.preview = QLabel("Selecione um TIM")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(256, 256)
        self.preview.setAccessibleName("Prévia do TIM")
        h.addWidget(self.preview, 1)
        v.addLayout(h)
        self.tabs.addTab(w, "&Gráficos")
        self._build_research_tab()
        # Exportar
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("A saída é sempre remontada a partir do original. Nada é gravado sem a revisão (P2)."))
        v.addWidget(_btn("&Revisar e exportar… (P2)", self.review_and_export))
        v.addWidget(_btn("Abrir no &emulador", self.run_emulator, "DuckStation ou PCSX-Redux, se instalado"))
        self.export_info = QPlainTextEdit()
        self.export_info.setReadOnly(True)
        self.export_info.setAccessibleName("Resultado da exportação")
        v.addWidget(self.export_info)
        self.tabs.addTab(w, "E&xportar")
        # Sistema
        w = QWidget()
        v = QVBoxLayout(w)
        self.system_info = QPlainTextEdit()
        self.system_info.setReadOnly(True)
        self.system_info.setFont(MONO)
        self.system_info.setAccessibleName("Ferramentas detectadas")
        v.addWidget(_btn("Detectar ferramentas", self.detect_tools))
        v.addWidget(self.system_info)
        self.tabs.addTab(w, "&Sistema")

    def _build_research_tab(self) -> None:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Modo Pesquisa: estatísticas, gabarito e testes. Nada aqui entra na saída final."))
        top = QHBoxLayout()
        self.research_table = QComboBox()
        self.research_table.setAccessibleName("Tabela pesquisada")
        top.addWidget(QLabel("Tabela:"))
        top.addWidget(self.research_table)
        top.addWidget(_btn("Perfilar &colunas", self.run_profiler, "Estatísticas de cada posição do registro"))
        top.addWidget(_btn("Importar gabarito CSV…", self.import_gabarito, "id,atributo,valor,fonte"))
        top.addStretch(1)
        v.addLayout(top)
        h = QHBoxLayout()
        self.profile_grid = QTableWidget()
        self.profile_grid.setAccessibleName("Perfil das colunas")
        self.profile_grid.verticalHeader().setVisible(False)
        h.addWidget(self.profile_grid, 3)
        col = QVBoxLayout()
        col.addWidget(QLabel("Propostas do gabarito (marque e registre):"))
        self.proposals = QListWidget()
        self.proposals.setAccessibleName("Propostas do gabarito")
        col.addWidget(self.proposals)
        col.addWidget(_btn("Registrar propostas marcadas", self.apply_proposals, "Viram PROVAVEL com statistical_match"))
        h.addLayout(col, 2)
        v.addLayout(h, 2)

        row = QHBoxLayout()
        box = QGroupBox("Marcar bytes como hipótese / BIN de teste")
        form = QFormLayout(box)
        self.r_index = QSpinBox()
        self.r_index.setAccessibleName("Registro")
        self.r_index.setRange(0, 9999)
        self.r_offset = QSpinBox()
        self.r_offset.setAccessibleName("Posição no registro")
        self.r_offset.setRange(0, 255)
        self.r_offset.setDisplayIntegerBase(16)
        self.r_offset.setPrefix("0x")
        self.r_type = QComboBox()
        self.r_type.setAccessibleName("Tipo")
        self.r_type.addItems(["u8", "s8", "u16le", "s16le"])
        self.r_value = QSpinBox()
        self.r_value.setAccessibleName("Valor de teste")
        self.r_value.setRange(-32768, 65535)
        self.r_text = QLineEdit()
        self.r_text.setAccessibleName("Interpretação da hipótese")
        self.r_text.setPlaceholderText("ex.: custo de MP (hipótese)")
        form.addRow("Registro:", self.r_index)
        form.addRow("Posição:", self.r_offset)
        form.addRow("Tipo:", self.r_type)
        form.addRow("Valor de teste:", self.r_value)
        form.addRow("Interpretação:", self.r_text)
        bb = QHBoxLayout()
        bb.addWidget(_btn("Marcar como hipótese", self.mark_hypothesis))
        bb.addWidget(_btn("Gerar BIN de teste", self.make_test_bin, "Altera só este campo; vai para testes/"))
        form.addRow(bb)
        row.addWidget(box, 1)
        box = QGroupBox("Findings")
        fv = QVBoxLayout(box)
        self.findings_list = QListWidget()
        self.findings_list.setAccessibleName("Findings do perfil")
        fv.addWidget(self.findings_list)
        fb = QHBoxLayout()
        fb.addWidget(_btn("Promover/rebaixar… (P3)", self.promote_dialog))
        fb.addWidget(_btn("Registrar TIMs como findings", self.register_tims))
        fb.addWidget(_btn("Recolorir TIM (magenta) para teste", self.recolor_test, "Usa o TIM selecionado em Gráficos"))
        fv.addLayout(fb)
        row.addWidget(box, 1)
        v.addLayout(row, 2)
        self.research_tab_index = self.tabs.addTab(w, "Pes&quisa")

    def _dock(self, title: str, widget: QWidget, area) -> QDockWidget:
        d = QDockWidget(title, self)
        d.setObjectName("dock_" + title)
        d.setWidget(widget)
        d.setAccessibleName(title)
        self.addDockWidget(area, d)
        return d

    def _build_docks(self) -> None:
        self.files = QTreeWidget()
        self.files.setHeaderLabels(["Arquivo", "Tipo", "Tamanho", "LBA"])
        self.files.setAccessibleName("Arquivos do CD")
        self._dock("Arquivos do CD", self.files, Qt.LeftDockWidgetArea)

        self.inspector = QPlainTextEdit()
        self.inspector.setReadOnly(True)
        self.inspector.setFont(MONO)
        self.inspector.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.inspector.setAccessibleName("Inspetor em hexa")
        self._dock("Inspetor", self.inspector, Qt.RightDockWidgetArea)

        w = QWidget()
        v = QVBoxLayout(w)
        self.layers = QListWidget()
        self.layers.setAccessibleName("Camadas (marque para ativar)")
        self.layers.itemChanged.connect(self._layer_toggled)
        v.addWidget(QLabel("Camadas (ordem de aplicação):"))
        v.addWidget(self.layers)
        row = QHBoxLayout()
        row.addWidget(_btn("Adicionar PPF/BPS…", self.add_patch))
        row.addWidget(_btn("Subir", lambda: self.move_layer(-1)))
        row.addWidget(_btn("Descer", lambda: self.move_layer(1)))
        v.addLayout(row)
        v.addWidget(QLabel("Conflitos e avisos:"))
        self.conflicts = QListWidget()
        self.conflicts.setAccessibleName("Conflitos e avisos")
        v.addWidget(self.conflicts)
        v.addWidget(_btn("Reconhecer conflitos… (P4)", self.acknowledge_dialog))
        self._dock("Camadas e conflitos", w, Qt.RightDockWidgetArea)

        w = QWidget()
        v = QVBoxLayout(w)
        self.history = QListWidget()
        self.history.setAccessibleName("Histórico de operações")
        v.addWidget(self.history)
        row = QHBoxLayout()
        row.addWidget(_btn("Desfazer (Ctrl+Z)", self.undo))
        row.addWidget(_btn("Refazer (Ctrl+Y)", self.redo))
        v.addLayout(row)
        self._dock("Histórico", w, Qt.LeftDockWidgetArea)

        self.console_tabs = QTabWidget()
        self.console_tabs.setAccessibleName("Console")
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setAccessibleName("Log")
        self.term_view = QPlainTextEdit()
        self.term_view.setReadOnly(True)
        self.term_view.setFont(MONO)
        self.term_view.setAccessibleName("Terminal equivalente")
        self.console_tabs.addTab(self.log_view, "Log")
        self.console_tabs.addTab(self.term_view, "Terminal equivalente")
        self._dock("Console", self.console_tabs, Qt.BottomDockWidgetArea)

    def _build_actions(self) -> None:
        for text, key, slot in (("Desfazer", QKeySequence.Undo, self.undo), ("Refazer", "Ctrl+Y", self.redo),
                                ("Salvar", QKeySequence.Save, self.save),
                                ("Revisar e exportar", "Ctrl+E", self.review_and_export),
                                ("Atualizar", "F5", self.refresh_all), ("Voltar ao menu", "Esc", self.go_back),
                                ("Restaurar layout", "Ctrl+Shift+R", self.restore_layout)):
            a = QAction(text, self)
            a.setShortcut(QKeySequence(key))
            a.setShortcutContext(Qt.WindowShortcut)
            a.triggered.connect(lambda _checked=False, f=slot: f())
            self.addAction(a)
        bar = self.menuBar().addMenu("&Projeto")
        for a in self.actions():
            bar.addAction(a)

    # ------------------------------------------------------------------ projeto
    def load_project(self, project: Project) -> None:
        self.project = project
        self.image = project.open_image()
        if not project.changesets:
            project.add_changeset("Alterações")
        self.cs_name = next(iter(project.changesets))
        self.research.blockSignals(True)
        self.research.setChecked(project.research_mode)
        self.research.blockSignals(False)
        self.tims = []
        self.tim_list.clear()
        self.log(f"Projeto aberto: {project.name} (perfil {project.profile_id or 'nenhum'})",
                 terminal.projeto("mostrar", project.path))
        problems = project.check_hashes(self.image)
        if problems:
            self.log("ATENÇÃO (P4): " + "; ".join(problems))
        self.fill_files()
        prof = project.profile()
        self.table_combo.blockSignals(True)
        self.table_combo.clear()
        if prof:
            self.table_combo.addItems(list(prof.tables))
        self.table_combo.blockSignals(False)
        self.tabs.setTabEnabled(0, prof is not None)
        self.findings_db = project.findings()
        self.research_table.clear()
        if prof:
            self.research_table.addItems(list(prof.tables))
        self._update_research_enabled()
        self.fill_findings()
        self.fill_table()
        self.refresh_all()
        layout = project.ui.get("layout")
        if layout:
            self.restoreState(QByteArray.fromBase64(layout.encode()))
        self.detect_tools()

    def cs(self):
        return self.project.bind(self.cs_name, self.image)

    def save(self) -> None:
        if self.project:
            self.project.ui["layout"] = bytes(self.saveState().toBase64()).decode()
            self.project.save()

    def go_back(self) -> None:
        self.save()
        self.back.emit()

    def restore_layout(self) -> None:
        self.restoreState(self._default_layout)
        for d in self.findChildren(QDockWidget):
            d.show()

    # ------------------------------------------------------------------ console
    def log(self, text: str, command: str | None = None) -> None:
        self.log_view.appendPlainText(text)
        if command:
            self.term_view.appendPlainText("$ " + command)

    # ------------------------------------------------------------------ arquivos
    def fill_files(self) -> None:
        self.files.clear()
        nodes: dict[str, QTreeWidgetItem] = {}
        for f in self.image.list_files():
            if self.image.disc is not None and not f.is_dir and not f.form2 and f.size:
                head = self.image.disc.user_data(f.lba)[:min(f.size, 2048)]
            elif self.image.disc is None:
                head = self.image.data[:2048]
            else:
                head = b""
            kind = filetypes.detect(head, f.form2, f.is_dir)
            parent_path, _, name = f.path.rpartition("/")
            parent = nodes.get(parent_path)
            item = QTreeWidgetItem([name, kind, "" if f.is_dir else str(f.size), "" if f.lba is None else str(f.lba)])
            (parent.addChild(item) if parent else self.files.addTopLevelItem(item))
            nodes[f.path] = item
        self.files.expandAll()
        self.log(f"{len(nodes)} entradas no CD", terminal.abrir(self.image.path))

    # ------------------------------------------------------------------ tabelas
    def _update_research_enabled(self) -> None:
        on = bool(self.project and self.project.research_mode and self.project.profile_id)
        self.tabs.setTabEnabled(self.research_tab_index, on)
        self.tabs.setTabToolTip(self.research_tab_index, "" if on else "Ligue o Modo Pesquisa na aba Tabelas")

    def _toggle_research(self, on: bool) -> None:
        self.project.research_mode = on
        self._update_research_enabled()
        self.project.save()
        self.log(f"Modo Pesquisa {'ligado' if on else 'desligado'}")
        self.fill_table()

    def fill_table(self) -> None:
        prof = self.project.profile() if self.project else None
        name = self.table_combo.currentText()
        self.grid.blockSignals(True)
        self.grid.clear()
        self._cols: list[tuple] = []
        if not prof or not name:
            self.grid.setRowCount(0)
            self.grid.blockSignals(False)
            return
        t = prof.table(name)
        findings = self.project.findings()
        research = self.project.research_mode
        cs = self.cs()
        data = self.image.read_file(t.file) if self.image.disc else self.image.data
        name_pol = findings.policy(t.names_finding, research) if findings else None
        headers = ["id", "nome" + (f"\n({name_pol.badge})" if name_pol and name_pol.badge else ""), "grupo"]
        self._cols = [("id",), ("name",), ("group",)]
        policies = {}
        for f in t.fields:
            pol = findings.policy(t.fields[f].finding, research) if findings else None
            policies[f] = pol
            headers.append(f + (f"\n({pol.badge})" if pol and pol.badge else ""))
            self._cols.append(("field", f))
        if research:  # Modo Pesquisa: bytes sem campo aparecem como byte cru editável
            covered = {f.offset + k for f in t.fields.values() for k in range(f.size)}
            for rel in range(t.stride):
                if rel not in covered:
                    headers.append(f"byte_0x{rel:02X}\n(cru)")
                    self._cols.append(("byte", rel))
        self.grid.setColumnCount(len(headers))
        self.grid.setHorizontalHeaderLabels(headers)
        self.grid.setRowCount(t.count)
        names_now = {(o.table, o.index): o.after for o in cs.ops if o.kind == "text"}
        raw_now = {}
        for o in cs.ops:
            if o.kind == "raw":
                for k, b in enumerate(bytes.fromhex(o.after)):
                    raw_now[o.offset + k] = b
        for i in range(t.count):
            for c, col in enumerate(self._cols):
                editable = True
                tip = ""
                if col[0] == "id":
                    val, editable = str(i), False
                elif col[0] == "name":
                    val = names_now.get((name, i), t.read_name(data, i) or "")
                    if t.names_pointer_table is None or (name_pol and not name_pol.editable):
                        editable, tip = False, name_pol.reason if name_pol else "sem nomes no perfil"
                elif col[0] == "group":
                    val, editable = t.category(i) or "", False
                elif col[0] == "field":
                    val = str(cs.current_field(name, i, col[1]))
                    pol = policies[col[1]]
                    if pol is not None and not pol.editable:
                        editable, tip = False, pol.reason
                else:
                    off = t.record_offset(i) + col[1]
                    val = str(raw_now.get(off, data[off]))
                it = QTableWidgetItem(val)
                if not editable:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                if tip:
                    it.setToolTip(tip)
                self.grid.setItem(i, c, it)
        self.grid.resizeColumnsToContents()
        self.grid.blockSignals(False)
        if not t.fields and not research:
            self.log(f"Tabela {name}: nenhum campo com evidência; ligue o Modo Pesquisa para ver os bytes crus")

    def _cell_changed(self, item: QTableWidgetItem) -> None:
        col = self._cols[item.column()]
        name = self.table_combo.currentText()
        t = self.project.profile().table(name)
        index = item.row()
        cs = self.cs()
        try:
            if col[0] == "field":
                value = int(item.text(), 0)
                op = cs.set_field(name, index, col[1], value)
                cmd = terminal.campo(self.project.path, name, index, col[1], value)
            elif col[0] == "name":
                op = cs.set_name(name, index, item.text())
                cmd = terminal.projeto("nome", self.project.path, name, str(index), item.text())
            elif col[0] == "byte":
                value = int(item.text(), 0)
                if not 0 <= value <= 255:
                    raise ValueError("byte cru vai de 0 a 255")
                op = cs.set_raw(t.file, t.record_offset(index) + col[1], bytes([value]))
                cmd = None
            else:
                return
            self.project.save()
            self.log(f"{op.target}: {op.before} → {op.after}", cmd)
        except (ValueError, PatchError) as e:
            self.log(f"Recusado: {e}")
            self.fill_table()
        self.refresh_all()

    def names_report(self):
        from inverse_engine.research import names
        t = self.project.profile().table(self.table_combo.currentText())
        data = self.image.read_file(t.file) if self.image.disc else self.image.data
        return names.analyze(t, data)

    def names_dialog(self) -> None:
        """Mostra a análise dos ponteiros de nomes e as amostras de cada hipótese antes de gravar."""
        from inverse_engine.research import names
        try:
            rep = self.names_report()
        except (names.NamesError, ValueError) as e:
            self.log(f"Nomes: {e}")
            return
        lines = [rep.summary(), ""]
        for h in rep.hypotheses:
            lines.append(f"shift {h.shift}: {h.description}")
            lines += [f"   [{i}] {n or '(sem nome)'}" for i, n in h.samples]
            if h.records_without_name:
                lines.append(f"   registros sem nome: {h.records_without_name[:10]}")
        self.log(rep.summary(), f"{terminal.CLI} nomes {terminal.q(self.image.path)} {rep.table}")
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Nomes de {rep.table}")
        form = QFormLayout(dlg)
        view = QPlainTextEdit("\n".join(lines))
        view.setReadOnly(True)
        view.setFont(MONO)
        view.setAccessibleName("Análise dos ponteiros de nomes")
        form.addRow(view)
        shift = QComboBox()
        shift.setAccessibleName("Alinhamento a gravar")
        shift.addItems([str(h.shift) for h in rep.hypotheses])
        ev = QLineEdit()
        ev.setAccessibleName("Evidência do alinhamento")
        ev.setPlaceholderText("ex.: nomes 0..5 conferidos no menu do jogo")
        ok = QCheckBox("Conferi as amostras e quero gravar este alinhamento no perfil")
        ok.setAccessibleName("Confirmo o alinhamento")
        form.addRow("Shift:", shift)
        form.addRow("Evidência:", ev)
        form.addRow(ok)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        dlg.resize(760, 560)
        if dlg.exec() == QDialog.Accepted:
            self.names_confirm(rep.table, int(shift.currentText()), ev.text(), ok.isChecked())

    def names_confirm(self, table: str, shift: int, evidence: str, confirmed: bool) -> bool:
        from inverse_engine.research import names
        try:
            names.confirm_shift(self.project.profiles_dir / f"{self.project.profile_id}.json", table, shift,
                                self.findings_db, evidence, confirmed)
        except names.NamesError as e:
            self.log(f"Recusado: {e}")
            return False
        self.log(f"Alinhamento dos nomes de {table} gravado: shift {shift}")
        self.fill_table()
        self.fill_findings()
        return True

    def _record_selected(self, row: int) -> None:
        if row < 0 or not self.project or not self.project.profile():
            return
        name = self.table_combo.currentText()
        t = self.project.profile().table(name)
        data = self.image.read_file(t.file) if self.image.disc else self.image.data
        rows = hexview.record_view(t, data, row, self.project.findings())
        text = hexview.format_table([[f"+0x{r['offset']:02X}", r["campo"], r["hex"], str(r["valor"]), r["estado"]]
                                     for r in rows], ["OFF", "CAMPO", "HEX", "VALOR", "ESTADO"])
        self.inspector.setPlainText(f"{name}[{row}] {t.read_name(data, row) or ''}\n"
                                    f"{t.file} 0x{t.record_offset(row):X} (original)\n\n{text}")
        self.term_view.appendPlainText("$ " + terminal.registro(self.image.path, name, row))

    # ------------------------------------------------------------------ gráficos
    def scan_tims(self, sync: bool = False) -> None:
        image = self.image

        def job(progress, cancelled):
            out = []
            files = [f for f in image.list_files() if not f.is_dir and not f.form2]
            for k, f in enumerate(files):
                if cancelled():
                    from inverse_engine.ui.worker import Cancelled
                    raise Cancelled()
                progress(k, len(files), f.path)
                for info in tim.scan(image.read_file(f.path)):
                    out.append((f.path, info))
            return out

        self.term_view.appendPlainText("$ " + terminal.tims(image.path))
        if sync:
            self._tims_found(run_sync(job))
        else:
            self._start(job, self._tims_found, "Procurando TIMs")

    def _tims_found(self, found) -> None:
        self.tims = found
        self.tim_list.clear()
        for path, info in found:
            self.tim_list.addItem(f"{path} 0x{info.offset:X} — {info.describe()}")
        self.log(f"{len(found)} TIM(s) encontrados")

    def _current_tim(self):
        r = self.tim_list.currentRow()
        if r < 0 or r >= len(self.tims):
            return None
        path, info = self.tims[r]
        return path, info, self.image.read_file(path)

    def _tim_selected(self) -> None:
        cur = self._current_tim()
        if cur is None:
            return
        path, info, data = cur
        if self.palette_combo.count() != max(1, info.clut_count) or self.palette_combo.property("tim") != (path, info.offset):
            self.palette_combo.blockSignals(True)
            self.palette_combo.clear()
            self.palette_combo.addItems([str(i) for i in range(max(1, info.clut_count))])
            self.palette_combo.setProperty("tim", (path, info.offset))
            self.palette_combo.blockSignals(False)
        pal = max(0, self.palette_combo.currentIndex())
        try:
            png = tim.export_png(data, info, pal)
        except tim.TimError as e:
            self.preview.setText(str(e))
            return
        pix = QPixmap()
        pix.loadFromData(png, "PNG")
        scale = max(1, min(32, 320 // max(info.width, info.height, 1)))
        self.preview.setPixmap(pix.scaled(info.width * scale, info.height * scale, Qt.KeepAspectRatio,
                                          Qt.FastTransformation))
        secs = "\n".join(f"{n:<18} +0x{a:X}..+0x{b:X}" for n, a, b in hexview.tim_sections(info))
        self.inspector.setPlainText(f"{path} 0x{info.offset:X}\n{info.describe()}\n\n{secs}")

    def export_png(self, target: str | None = None) -> Path | None:
        cur = self._current_tim()
        if cur is None:
            self.log("Selecione um TIM primeiro")
            return None
        path, info, data = cur
        if target is None:
            target, _ = QFileDialog.getSaveFileName(self, "Exportar PNG", f"{Path(path).name}_{info.offset:X}.png",
                                                    "PNG (*.png)")
            if not target:
                return None
        Path(target).write_bytes(tim.export_png(data, info, max(0, self.palette_combo.currentIndex())))
        self.log(f"PNG exportado: {target}")
        return Path(target)

    def import_png(self, kind: str, source: str | None = None) -> None:
        cur = self._current_tim()
        if cur is None:
            self.log("Selecione um TIM primeiro")
            return
        path, info, data = cur
        if source is None:
            source, _ = QFileDialog.getOpenFileName(self, "Importar PNG", "", "PNG (*.png)")
            if not source:
                return
        pal = max(0, self.palette_combo.currentIndex())
        try:
            fn = tim.import_drawing if kind == "desenho" else tim.import_colors
            new = fn(data, info, Path(source).read_bytes(), pal)
            edit = GraphicEdit(path, info.offset, data[info.offset:info.offset + info.size], new, kind, pal,
                               info.clut_pos)
            op = self.cs().set_graphic(edit)
            self.project.save()
            self.log(f"{op.target}: {kind} importado de {source}")
        except (tim.TimError, PatchError, ValueError) as e:
            self.log(f"Recusado: {e}")
        self.refresh_all()

    # ------------------------------------------------------------------ camadas e conflitos
    def refresh_all(self) -> None:
        if not self.project:
            return
        self.layers.blockSignals(True)
        self.layers.clear()
        for o in self.project.order:
            ref = self.project.patches.get(o["name"]) or self.project.changesets[o["name"]]
            kind = ref.kind if o["type"] == "patch" else "changeset"
            it = QListWidgetItem(f"{kind:<10} {o['name']}")
            it.setData(Qt.UserRole, o["name"])
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if ref.active else Qt.Unchecked)
            self.layers.addItem(it)
        self.layers.blockSignals(False)
        self.conflicts.clear()
        try:
            for c in self.project.stack().conflicts():
                mark = " (reconhecido)" if c.id in self.project.acknowledged else ""
                self.conflicts.addItem(f"{c.kind}{mark}: {c.detail}")
        except (ProjectError, PatchError) as e:
            self.conflicts.addItem(f"ERRO: {e}")
        self.history.clear()
        for cs in self.project.changesets.values():
            for h in cs.history():
                self.history.addItem(f"#{h['id']} [{h['rótulo']}] {h['alvo']}: {h['antes']} → {h['depois']} "
                                     f"({h['origem']})")
            for g in reversed(cs.redo_groups):
                self.history.addItem(f"(refazer) [{g[0].group_label}] {len(g)} operação(ões)")

    def _layer_toggled(self, item: QListWidgetItem) -> None:
        name = item.data(Qt.UserRole)
        on = item.checkState() == Qt.Checked
        self.project.set_active(name, on)
        self.project.save()
        self.log(f"Camada {name} {'ativada' if on else 'desativada'}")
        self.refresh_all()

    def move_layer(self, delta: int) -> None:
        row = self.layers.currentRow()
        if row < 0:
            return
        new = max(0, min(len(self.project.order) - 1, row + delta))
        self.project.move(self.project.order[row]["name"], new)
        self.project.save()
        self.refresh_all()
        self.layers.setCurrentRow(new)

    def add_patch(self, source: str | None = None) -> None:
        if source is None:
            source, _ = QFileDialog.getOpenFileName(self, "Adicionar patch", "", "Patches (*.ppf *.bps)")
            if not source:
                return
        try:
            ref = self.project.add_patch(source)
            self.project.save()
            self.log(f"Camada {ref.kind} '{ref.name}' acrescentada", terminal.projeto("patch", self.project.path, source))
        except (ProjectError, ValueError) as e:
            self.log(f"Recusado: {e}")
        self.refresh_all()

    def pending_conflicts(self):
        return [c for c in self.project.stack().conflicts() if c.needs_ack and c.id not in self.project.acknowledged]

    def acknowledge_dialog(self, auto_accept: bool = False) -> bool:
        """Portão P4: lista conflitos pendentes; aceitar grava o reconhecimento no projeto."""
        pend = self.pending_conflicts()
        if not pend:
            self.log("Nenhum conflito pendente")
            return True
        if not auto_accept:
            text = "\n\n".join(f"• {c.detail}" + (f"\n  campo: {c.target}" if c.target else "") for c in pend)
            ans = QMessageBox.question(self, "Reconhecer conflitos (P4)",
                                       f"A camada posterior vence nestes pontos:\n\n{text}\n\nReconhecer todos?")
            if ans != QMessageBox.Yes:
                return False
        self.project.acknowledged += [c.id for c in pend]
        self.project.save()
        self.log(f"{len(pend)} conflito(s) reconhecido(s)", terminal.projeto("reconhecer", self.project.path))
        self.refresh_all()
        return True

    # ------------------------------------------------------------------ desfazer/refazer
    def undo(self) -> None:
        ops = self.project.changesets[self.cs_name].undo()
        self._after_undo_redo("Desfeito", ops, "desfazer")

    def redo(self) -> None:
        ops = self.project.changesets[self.cs_name].redo()
        self._after_undo_redo("Refeito", ops, "refazer")

    def _after_undo_redo(self, verb: str, ops, cmd: str) -> None:
        if not ops:
            self.log(f"Nada para {cmd}")
            return
        self.project.save()
        self.log(f"{verb}: grupo '{ops[0].group_label}' ({len(ops)} operação(ões))",
                 terminal.projeto(cmd, self.project.path))
        self.fill_table()
        self.refresh_all()

    # ------------------------------------------------------------------ pesquisa
    def _rtable(self):
        t = self.project.profile().table(self.research_table.currentText())
        return t, (self.image.read_file(t.file) if self.image.disc else self.image.data)

    def fill_findings(self) -> None:
        self.findings_list.clear()
        if not getattr(self, "findings_db", None):
            return
        for f in self.findings_db.findings.values():
            it = QListWidgetItem(f"{f['id']:<7} {f['status']:<12} {f['subject']}")
            it.setData(Qt.UserRole, f["id"])
            it.setToolTip(f.get("interpretation", ""))
            self.findings_list.addItem(it)

    def _save_findings(self) -> None:
        self.findings_db.save()
        self.fill_findings()
        self.fill_table()

    def run_profiler(self) -> None:
        t, data = self._rtable()
        stats = profiler.profile(t, data)
        headers = ["pos", "tipo", "mín", "máx", "distintos", "zeros", "×10", "×5", "cresce", "campo", "notas"]
        self.profile_grid.setColumnCount(len(headers))
        self.profile_grid.setHorizontalHeaderLabels(headers)
        self.profile_grid.setRowCount(len(stats))
        for r, s in enumerate(stats):
            vals = [f"0x{s.offset:02X}", s.type, str(s.min), str(s.max), str(s.distinct), f"{s.zeros:.0%}",
                    f"{s.mult10:.0%}", f"{s.mult5:.0%}", f"{s.monotonic:.0%}", s.field or "", s.notes()]
            for c, val in enumerate(vals):
                it = QTableWidgetItem(val)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.profile_grid.setItem(r, c, it)
        self.profile_grid.resizeColumnsToContents()
        self.log(f"Perfilador: {t.name}, {len(stats)} colunas analisadas",
                 f"{terminal.CLI} perfilar {terminal.q(self.image.path)} {t.name}")

    def import_gabarito(self, source: str | None = None) -> None:
        if source is None:
            source, _ = QFileDialog.getOpenFileName(self, "Gabarito CSV", "", "CSV (*.csv)")
            if not source:
                return
        t, data = self._rtable()
        try:
            rows = gabarito.load(Path(source), t, data)
        except (ValueError, KeyError) as e:
            self.log(f"Gabarito recusado: {e}")
            return
        self._proposals = gabarito.match(t, data, rows, findings=self.findings_db)
        self.proposals.clear()
        for p in self._proposals:
            it = QListWidgetItem(p.detail() + (f" — já existe {p.existing}" if p.existing else ""))
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if p.distinct >= 2 else Qt.Unchecked)
            self.proposals.addItem(it)
        self.log(f"Gabarito: {len(rows)} linha(s), {len(self._proposals)} proposta(s)",
                 f"{terminal.CLI} gabarito {terminal.q(self.image.path)} {t.name} {terminal.q(source)}")

    def apply_proposals(self) -> None:
        t, _ = self._rtable()
        done = []
        for k, p in enumerate(getattr(self, "_proposals", [])):
            if self.proposals.item(k).checkState() == Qt.Checked:
                f = gabarito.apply(self.findings_db, t, p)
                done.append(f"{f['id']} {f['status']}")
        if done:
            self._save_findings()
            self.log("Registrado: " + ", ".join(done))
        else:
            self.log("Nenhuma proposta marcada")

    def mark_hypothesis(self) -> None:
        t, _ = self._rtable()
        off, typ = self.r_offset.value(), self.r_type.currentText()
        size = 2 if "16" in typ else 1
        if off + size > t.stride:
            self.log("Recusado: passa do fim do registro")
            return
        prefix = (t.finding or "R-").split("-")[0]
        f = self.findings_db.add_finding(prefix, f"{t.name}.byte_0x{off:02X}", self.r_text.text() or "hipótese",
                                         file=t.file, record_offset=f"0x{off:X}", size=size, type=typ)
        self._save_findings()
        self.log(f"Hipótese registrada: {f['id']} {f['subject']}")

    def make_test_bin(self, overwrite: bool = False):
        t, _ = self._rtable()
        try:
            res = testbin.value_test(self.project, t.name, self.r_index.value(), self.r_offset.value(),
                                     self.r_type.currentText(), self.r_value.value(), overwrite=overwrite)
        except (testbin.TestBinError, ValueError, IndexError, PatchError, ProjectError) as e:
            self.log(f"BIN de teste recusada: {e}")
            return None
        self.log(f"BIN de teste: {res.image}\n{res.instructions}",
                 f"{terminal.CLI} teste-campo {terminal.q(self.project.path)} {t.name} {self.r_index.value()} "
                 f"0x{self.r_offset.value():X} {self.r_type.currentText()} {self.r_value.value()}")
        return res

    def recolor_test(self):
        cur = self._current_tim()
        if cur is None:
            self.log("Selecione um TIM na aba Gráficos primeiro")
            return None
        path, info, _ = cur
        try:
            res = testbin.recolor_test(self.project, path, info.offset, overwrite=True)
        except (testbin.TestBinError, tim.TimError) as e:
            self.log(f"Recusado: {e}")
            return None
        self.log(f"BIN de teste (magenta): {res.image}\n{res.instructions}")
        return res

    def register_tims(self) -> None:
        if not self.tims:
            self.scan_tims(sync=True)
        new = testbin.register_tims(self.findings_db, self.tims)
        self._save_findings()
        self.log(f"{len(new)} finding(s) de gráficos registrados")

    def promote(self, finding_id: str, status: str, kind: str, detail: str, confirmed: bool = False) -> bool:
        """Portão P3: CONFIRMADO só com a confirmação do usuário do que viu (ex.: print do emulador)."""
        if status == "CONFIRMADO" and not confirmed:
            self.log("CONFIRMADO exige a sua confirmação do que viu no jogo (P3)")
            return False
        try:
            ev = {"kind": kind, "detail": detail} if detail else None
            self.findings_db.set_status(finding_id, status, detail or "rebaixado", ev)
        except FindingError as e:
            self.log(f"Recusado: {e}")
            return False
        self._save_findings()
        self.log(f"{finding_id} → {status}")
        return True

    def promote_dialog(self) -> None:
        item = self.findings_list.currentItem()
        if item is None:
            self.log("Selecione um finding")
            return
        fid = item.data(Qt.UserRole)
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Mudar estado de {fid} (P3)")
        form = QFormLayout(dlg)
        st = QComboBox()
        st.setAccessibleName("Novo estado")
        st.addItems(list(STATES))
        st.setCurrentText(self.findings_db.status(fid))
        kind = QComboBox()
        kind.setAccessibleName("Tipo de evidência")
        kind.addItems(sorted(EVIDENCE_KINDS))
        kind.setCurrentText("in_game_test")
        detail = QLineEdit()
        detail.setAccessibleName("Evidência nova")
        detail.setPlaceholderText("o que foi visto (obrigatório para promover)")
        seen = QCheckBox("Confirmo que vi o resultado no jogo/emulador")
        seen.setAccessibleName("Confirmo que vi o resultado")
        form.addRow("Estado:", st)
        form.addRow("Evidência:", kind)
        form.addRow("Detalhe:", detail)
        form.addRow(seen)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec() == QDialog.Accepted:
            self.promote(fid, st.currentText(), kind.currentText(), detail.text().strip(), seen.isChecked())

    # ------------------------------------------------------------------ exportação (P2)
    def review_text(self) -> str:
        st = self.project.stack()
        lines = ["CAMADAS:"]
        for o in self.project.order:
            ref = self.project.patches.get(o["name"]) or self.project.changesets[o["name"]]
            lines.append(f"  [{'x' if ref.active else ' '}] {o['name']}")
        lines.append("\nOPERAÇÕES:")
        for cs in self.project.changesets.values():
            lines += [f"  {h['alvo']}: {h['antes']} → {h['depois']} ({h['origem']})" for h in cs.history()]
        lines.append("\nCONFLITOS E AVISOS:")
        lines += [f"  {c.kind}: {c.detail}" for c in st.conflicts()] or ["  nenhum"]
        rows = hexview.write_rows(st)
        lines.append("\nFAIXAS AFETADAS:")
        lines.append(hexview.format_table([r.cells() for r in rows], hexview.HEADERS))
        lines.append("\nSAÍDA:")
        lines += [f"  {v}" for v in output_paths(self.project).values()]
        return "\n".join(lines)

    def review_and_export(self, auto_confirm: bool = False) -> None:
        try:
            if self.pending_conflicts() and not self.acknowledge_dialog(auto_accept=auto_confirm):
                self.log("Exportação cancelada: há conflitos não reconhecidos (P4)")
                return
            text = self.review_text()
        except (ProjectError, PatchError) as e:
            self.log(f"Não é possível exportar: {e}")
            return
        if not auto_confirm:
            dlg = QDialog(self)
            dlg.setWindowTitle("Revisar exportação (P2)")
            v = QVBoxLayout(dlg)
            view = QPlainTextEdit(text)
            view.setReadOnly(True)
            view.setFont(MONO)
            view.setAccessibleName("Resumo da exportação")
            v.addWidget(view)
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.button(QDialogButtonBox.Ok).setText("&Exportar")
            buttons.accepted.connect(dlg.accept)
            buttons.rejected.connect(dlg.reject)
            v.addWidget(buttons)
            dlg.resize(900, 600)
            if dlg.exec() != QDialog.Accepted:
                return
        overwrite = False
        if any(p.exists() for p in output_paths(self.project).values()):
            if not auto_confirm and QMessageBox.question(self, "Sobrescrever?",
                                                         "Os arquivos de saída já existem. Sobrescrever?") != QMessageBox.Yes:
                return
            overwrite = True
        self.save()
        project = self.project
        job = lambda progress, cancelled: export(project, overwrite=overwrite)
        self.term_view.appendPlainText("$ " + terminal.projeto("exportar", project.path)
                                       + (" --sobrescrever" if overwrite else ""))
        if auto_confirm:
            self._exported(run_sync(job))
        else:
            self._start(job, self._exported, "Exportando")

    def _exported(self, res) -> None:
        lines = [f"{k}: {v}" for k, v in res.files.items()]
        self.export_info.setPlainText("\n".join(lines))
        self.log("Exportado:\n" + "\n".join(lines), terminal.reproduzir(res.files["relatorio_json"]))
        self.last_export = res

    def run_emulator(self) -> None:
        paths = output_paths(self.project)
        target = paths.get("cue") or paths["imagem"]
        if not target.exists():
            self.log("Exporte primeiro (Revisar e exportar)")
            return
        emu = next((t for t in ("duckstation-qt", "duckstation", "pcsx-redux") if shutil.which(t)), None)
        if emu is None:
            self.log("Nenhum emulador encontrado. Instale, por exemplo:",
                     terminal.INSTALL["duckstation"])
            return
        subprocess.Popen([emu, str(target)])
        self.log(f"Emulador iniciado: {emu}", terminal.emulador(emu, target))

    # ------------------------------------------------------------------ sistema
    def detect_tools(self) -> None:
        lines = [f"Python {sys.version.split()[0]} · {platform.system()} {platform.release()}"]
        try:
            import PySide6
            lines.append(f"PySide6 {PySide6.__version__}")
        except ImportError:
            pass
        for t in TOOLS:
            where = shutil.which(t)
            hint = terminal.INSTALL.get(t.replace("-qt", "").replace("Run", ""), "")
            lines.append(f"{t:<16} {where or 'não encontrado'}" + ("" if where or not hint else f"   instalar: {hint}"))
        self.system_info.setPlainText("\n".join(lines))

    # ------------------------------------------------------------------ tarefas
    def _start(self, job, on_done, label: str) -> None:
        if self._task and self._task.isRunning():
            self.log("Já existe uma tarefa em andamento")
            return
        self._task = Task(job, self)
        self._task.progress.connect(lambda a, b, t: self.statusBar().showMessage(f"{label}: {a}/{b} {t}"))
        self._task.done.connect(lambda r: (self.statusBar().clearMessage(), on_done(r)))
        self._task.failed.connect(lambda m: (self.statusBar().clearMessage(), self.log(f"{label} falhou: {m}")))
        self._task.start()
