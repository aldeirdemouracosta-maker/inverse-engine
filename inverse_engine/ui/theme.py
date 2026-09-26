"""Temas da interface: cores em JSON, checagem de contraste WCAG AA e folha de estilo Qt.

Sem PySide6 aqui: pode ser testado sem interface gráfica.
"""
from __future__ import annotations

import json
from pathlib import Path

THEMES_DIR = Path(__file__).resolve().parent / "themes"
AA_TEXT = 4.5
# (texto, fundo) que precisam passar em AA
PAIRS = [("texto", "fundo"), ("texto", "painel"), ("texto_suave", "painel"), ("texto_suave", "fundo"),
         ("botao_texto", "botao"), ("destaque_texto", "destaque"), ("erro", "painel"), ("ok", "painel"),
         ("aviso", "painel")]


def _lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def load(name: str) -> dict:
    return json.loads((THEMES_DIR / f"{name}.json").read_text(encoding="utf-8"))


def available() -> list[str]:
    return sorted(p.stem for p in THEMES_DIR.glob("*.json"))


def check(theme: dict) -> list[str]:
    """Pares que não passam em WCAG AA (lista vazia = aprovado)."""
    c = theme["cores"]
    return [f"{fg} sobre {bg}: {contrast(c[fg], c[bg]):.2f} < {AA_TEXT}"
            for fg, bg in PAIRS if contrast(c[fg], c[bg]) < AA_TEXT]


def art_path(theme: dict) -> Path | None:
    art = theme.get("fundo_arte")
    if not art:
        return None
    p = THEMES_DIR / art
    return p if p.exists() else None


def stylesheet(theme: dict, font_pt: int = 11) -> str:
    c = theme["cores"]
    return f"""
    QWidget {{ background: {c['fundo']}; color: {c['texto']}; font-size: {font_pt}pt; }}
    QFrame#painel, QDockWidget, QTabWidget::pane, QGroupBox, QListWidget, QTreeWidget, QTableWidget,
    QPlainTextEdit, QLineEdit, QComboBox, QSpinBox {{ background: {c['painel']}; color: {c['texto']}; }}
    QLabel#suave {{ color: {c['texto_suave']}; }}
    QPushButton {{ background: {c['botao']}; color: {c['botao_texto']}; border: 1px solid {c['borda']};
                   padding: 6px 12px; border-radius: 4px; }}
    QPushButton#principal {{ background: {c['destaque']}; color: {c['destaque_texto']}; font-weight: bold; }}
    QPushButton:disabled {{ color: {c['texto_suave']}; border-style: dashed; }}
    *:focus {{ outline: 2px solid {c['foco']}; border: 2px solid {c['foco']}; }}
    QHeaderView::section {{ background: {c['botao']}; color: {c['botao_texto']}; }}
    QTabBar::tab {{ background: {c['botao']}; color: {c['botao_texto']}; padding: 6px 10px; }}
    QTabBar::tab:selected {{ background: {c['destaque']}; color: {c['destaque_texto']}; }}
    QLabel#erro {{ color: {c['erro']}; }} QLabel#ok {{ color: {c['ok']}; }} QLabel#aviso {{ color: {c['aviso']}; }}
    """
