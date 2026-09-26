"""AppState: troca entre MainMenuState e EditorWorkspaceState (QStackedWidget).

    python3 -m inverse_engine.ui.app
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QInputDialog, QMainWindow, QMessageBox, QSpinBox, QStackedWidget)

from inverse_engine.core.profile import RomProfile, match_profiles
from inverse_engine.core.project import Project, ProjectError, EXT, ROOT
from inverse_engine.core.rom_image import RomImage
from inverse_engine.ui import recent, theme, terminal
from inverse_engine.ui.main_menu import MainMenu
from inverse_engine.ui.workspace import Workspace

IMAGE_FILTER = "Imagens de PS1 (*.bin *.cue *.BIN *.CUE);;Executável (*)"


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Inverse Engine")
        self.resize(1280, 800)
        self.stack = QStackedWidget()
        self.menu = MainMenu()
        self.workspace = Workspace()
        self.stack.addWidget(self.menu)
        self.stack.addWidget(self.workspace)
        self.setCentralWidget(self.stack)
        self.menu.start_project.connect(lambda: self.start_project())
        self.menu.open_image.connect(lambda: self.open_image())
        self.menu.open_project.connect(self.open_project)
        self.menu.options.connect(self.options)
        self.menu.quit.connect(self.close)
        self.workspace.back.connect(self.show_menu)
        self.apply_theme()

    # --- tema -------------------------------------------------------------
    def apply_theme(self) -> None:
        s = recent.settings()
        t = theme.load(s.get("tema", "simples"))
        css = theme.stylesheet(t, int(s.get("fonte", 11)))
        art = theme.art_path(t)
        if art:
            css += f"\nQWidget#menu {{ border-image: url('{art.as_posix()}') 0 0 0 0 stretch stretch; }}"
        self.setStyleSheet(css)

    def options(self) -> None:
        s = recent.settings()
        dlg = QDialog(self)
        dlg.setWindowTitle("Opções")
        form = QFormLayout(dlg)
        combo = QComboBox()
        combo.setAccessibleName("Tema")
        combo.addItems(theme.available())
        combo.setCurrentText(s.get("tema", "simples"))
        size = QSpinBox()
        size.setAccessibleName("Tamanho da fonte")
        size.setRange(8, 24)
        size.setValue(int(s.get("fonte", 11)))
        form.addRow("&Tema:", combo)
        form.addRow("&Fonte (pt):", size)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)
        if dlg.exec() == QDialog.Accepted:
            recent.save_settings({"tema": combo.currentText(), "fonte": size.value()})
            self.apply_theme()

    # --- navegação ---------------------------------------------------------
    def show_menu(self) -> None:
        self.menu.refresh()
        self.stack.setCurrentWidget(self.menu)

    def show_project(self, project: Project) -> None:
        self.workspace.load_project(project)
        m = None
        prof = project.profile()
        if prof:
            m = prof.evaluate(self.workspace.image)
        recent.add(project.path, project.name, project.profile_id, None if m is None else (m.applies and m.integrity_ok))
        self.stack.setCurrentWidget(self.workspace)
        self.setWindowTitle(f"Inverse Engine — {project.name}")

    # --- ações do menu -------------------------------------------------------
    def start_project(self, image_path=None, folder=None, name=None) -> Project | None:
        """Assistente: imagem → pasta → nome. Parâmetros preenchidos pulam as perguntas."""
        if image_path is None:
            image_path, _ = QFileDialog.getOpenFileName(self, "Escolher imagem", "", IMAGE_FILTER)
            if not image_path:
                return None
        if folder is None:
            folder = QFileDialog.getExistingDirectory(self, "Pasta do projeto (pode ser partição compartilhada)")
            if not folder:
                return None
        if name is None:
            name, ok = QInputDialog.getText(self, "Nome do projeto", "Nome:", text="Rebalance 2026")
            if not ok or not name.strip():
                return None
        try:
            p = Project.create(folder, name.strip(), image_path)
            p.add_changeset("Alterações")
            p.save()
        except (ProjectError, ValueError, OSError) as e:
            QMessageBox.warning(self, "Não foi possível criar o projeto", str(e))
            return None
        self.show_project(p)
        self.workspace.log("Projeto criado", terminal.projeto_novo(folder, name, image_path))
        if p.profile_id is None:
            self.workspace.log("Nenhum perfil se aplica: só formatos genéricos (arquivos, TIM, hexa).")
        return p

    def open_image(self, image_path=None) -> None:
        if image_path is None:
            image_path, _ = QFileDialog.getOpenFileName(self, "Abrir imagem", "", IMAGE_FILTER)
            if not image_path:
                return
        try:
            image = RomImage.open(image_path)
        except (ValueError, OSError) as e:
            QMessageBox.warning(self, "Imagem inválida", str(e))
            return
        lines = [f"SHA-256: {image.sha256}", f"Comando: {terminal.abrir(image_path)}", ""]
        for m in match_profiles(image, RomProfile.load_all(ROOT / "profiles")):
            lines.append(f"Perfil {m.profile_id}: {m.summary()}")
            lines += [f"  [{'OK' if a.ok else 'FALHOU'}] {a.type}: {a.detail}" for a in m.anchors]
        lines += ["", "Criar um projeto com esta imagem?"]
        if QMessageBox.question(self, "Âncoras", "\n".join(lines)) == QMessageBox.Yes:
            self.start_project(image_path)

    def open_project(self, path=None) -> None:
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "Abrir projeto", "", f"Projeto (*{EXT})")
            if not path:
                return
        try:
            self.show_project(Project.load(path))
        except (ProjectError, ValueError, OSError) as e:
            QMessageBox.warning(self, "Não foi possível abrir o projeto", str(e))

    def closeEvent(self, event) -> None:
        if self.stack.currentWidget() is self.workspace:
            self.workspace.save()
        super().closeEvent(event)


def main(argv=None) -> int:
    app = QApplication(sys.argv if argv is None else argv)
    app.setApplicationName("Inverse Engine")
    w = App()
    w.show()
    args = (argv if argv is not None else sys.argv)[1:]
    if args and args[0].endswith(EXT):
        w.open_project(Path(args[0]))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
