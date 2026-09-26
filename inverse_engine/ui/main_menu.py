"""MainMenuState: tela inicial com ações principais, projetos recentes e estatísticas."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout, QWidget)

from inverse_engine import __version__
from inverse_engine.ui import recent


class MainMenu(QWidget):
    start_project = Signal()
    open_image = Signal()
    open_project = Signal(object)     # Path ou None (pergunta)
    options = Signal()
    cheats = Signal()
    audio = Signal()
    quit = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("menu")
        root = QHBoxLayout(self)
        panel = QFrame()
        panel.setObjectName("painel")  # painel sólido atrás dos botões (contraste no tema fantasia)
        col = QVBoxLayout(panel)
        title = QLabel(f"<h1>Inverse Engine</h1>")
        title.setAccessibleName("Título: Inverse Engine")
        sub = QLabel(f"Modificador de jogos de PS1 · versão {__version__}")
        sub.setObjectName("suave")
        col.addWidget(title)
        col.addWidget(sub)
        self.buttons: dict[str, QPushButton] = {}

        def button(key, text, tip, signal=None, disabled_reason=None, primary=False):
            b = QPushButton(text)
            b.setAccessibleName(text.replace("&", ""))
            b.setToolTip(tip)
            b.setMinimumHeight(40)
            if primary:
                b.setObjectName("principal")
            if disabled_reason:
                b.setEnabled(False)
                b.setToolTip(f"{tip} — {disabled_reason}")
                b.setAccessibleDescription(disabled_reason)
            else:
                b.clicked.connect(signal)
            self.buttons[key] = b
            col.addWidget(b)
            return b

        button("iniciar", "&Iniciar projeto", "Escolher imagem, pasta e nome do projeto",
               self.start_project.emit, primary=True)
        button("imagem", "Abrir i&magem", "Abrir .bin, .cue ou executável e conferir as âncoras",
               self.open_image.emit)
        button("projeto", "Abrir &projeto", "Abrir um arquivo .vh2proj.json", lambda: self.open_project.emit(None))
        button("cheats", "Criar &cheats", "Códigos GameShark a partir do perfil (abre um projeto)", self.cheats.emit)
        button("modelos", "Modelos &3D", "Visualizador TMD", disabled_reason="chega no marco 10")
        button("audio", "Á&udio e texturas", "Bancos de som VAB e texturas TIM (abre um projeto)", self.audio.emit)
        button("opcoes", "&Opções", "Tema e tamanho da fonte", self.options.emit)
        button("sair", "&Sair", "Fechar o Inverse Engine", self.quit.emit)
        col.addStretch(1)
        root.addWidget(panel, 1)

        side = QFrame()
        side.setObjectName("painel")
        sv = QVBoxLayout(side)
        sv.addWidget(QLabel("<b>Projetos recentes</b> (Enter abre)"))
        self.recent_list = QListWidget()
        self.recent_list.setAccessibleName("Projetos recentes")
        self.recent_list.itemActivated.connect(self._open_recent)
        self.recent_list.currentItemChanged.connect(self._show_stats)
        sv.addWidget(self.recent_list, 1)
        self.stats = QLabel("")
        self.stats.setWordWrap(True)
        self.stats.setAccessibleName("Estatísticas do projeto selecionado")
        sv.addWidget(self.stats)
        root.addWidget(side, 1)
        self.refresh()

    def refresh(self) -> None:
        self.recent_list.clear()
        for r in recent.load():
            ok = {True: "âncoras OK", False: "âncoras falharam", None: "sem perfil"}[r.get("ancoras_ok")]
            item = QListWidgetItem(f"{r['nome']} — {r.get('perfil') or 'sem perfil'} — {r['data']} — {ok}")
            item.setData(Qt.UserRole, r["caminho"])
            item.setToolTip(r["caminho"])
            self.recent_list.addItem(item)
        if self.recent_list.count():
            self.recent_list.setCurrentRow(0)
        else:
            self.stats.setText("Nenhum projeto ainda. Use “Iniciar projeto”.")

    def _open_recent(self, item) -> None:
        self.open_project.emit(Path(item.data(Qt.UserRole)))

    def _show_stats(self, item, _prev=None) -> None:
        if item is None:
            return
        path = Path(item.data(Qt.UserRole))
        if not path.exists():
            self.stats.setText(f"Arquivo não encontrado:\n{path}")
            return
        try:
            from inverse_engine.core.project import Project
            s = recent.project_stats(Project.load(path))
            f = ", ".join(f"{k} {v}" for k, v in s["findings"].items() if v) or "—"
            self.stats.setText(f"Camadas: {s['camadas']} · Operações: {s['operacoes']} · "
                               f"Tabelas mapeadas: {s['tabelas']}\nFindings: {f}")
        except Exception as e:
            self.stats.setText(f"Não foi possível ler o projeto: {e}")
