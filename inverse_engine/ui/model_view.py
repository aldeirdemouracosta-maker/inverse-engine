"""Visualizador de TMD em arame (QPainter): girar com o mouse ou setas, zoom com a roda ou +/-.

Não depende de OpenGL, então funciona em qualquer máquina e no CI (modo offscreen).
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class ModelView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAccessibleName("Visualizador do modelo 3D (setas giram, + e - dão zoom)")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(320, 240)
        self.edges: list[tuple[tuple, tuple]] = []
        self.yaw, self.pitch, self.zoom = 0.6, 0.4, 1.0
        self._drag = None

    def set_model(self, tmd_obj) -> None:
        """Arestas das primitivas decodificadas, centradas e normalizadas."""
        verts = tmd_obj.vertices
        edges = set()
        for p in tmd_obj.primitives:
            v = p.vertices
            if not v:
                continue
            loop = [v[0], v[1], v[3], v[2]] if len(v) == 4 else v
            for a, b in zip(loop, loop[1:] + loop[:1]):
                edges.add((min(a, b), max(a, b)))
        if verts:
            cx, cy, cz = (sum(c[i] for c in verts) / len(verts) for i in range(3))
            r = max(max(abs(x - cx), abs(y - cy), abs(z - cz)) for x, y, z in verts) or 1
            norm = [((x - cx) / r, (y - cy) / r, (z - cz) / r) for x, y, z in verts]
        else:
            norm = []
        self.edges = [(norm[a], norm[b]) for a, b in sorted(edges)]
        self.update()

    def _project(self, p) -> QPointF:
        x, y, z = p
        cy, sy, cp, sp = math.cos(self.yaw), math.sin(self.yaw), math.cos(self.pitch), math.sin(self.pitch)
        x, z = x * cy + z * sy, -x * sy + z * cy
        y, z = y * cp - z * sp, y * sp + z * cp
        s = min(self.width(), self.height()) * 0.4 * self.zoom
        return QPointF(self.width() / 2 + x * s, self.height() / 2 + y * s)  # Y do PS1 já aponta para baixo

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), self.palette().base())
        p.setPen(QPen(QColor(self.palette().text().color()), 1))
        if not self.edges:
            p.drawText(self.rect(), Qt.AlignCenter, "Nenhum modelo selecionado")
        for a, b in self.edges:
            p.drawLine(self._project(a), self._project(b))
        p.end()

    def mousePressEvent(self, e) -> None:
        self._drag = e.position()

    def mouseMoveEvent(self, e) -> None:
        if self._drag is not None:
            d = e.position() - self._drag
            self.yaw += d.x() * 0.01
            self.pitch += d.y() * 0.01
            self._drag = e.position()
            self.update()

    def mouseReleaseEvent(self, _e) -> None:
        self._drag = None

    def wheelEvent(self, e) -> None:
        self.zoom *= 1.1 if e.angleDelta().y() > 0 else 1 / 1.1
        self.update()

    def keyPressEvent(self, e) -> None:
        step = {Qt.Key_Left: (-0.1, 0), Qt.Key_Right: (0.1, 0), Qt.Key_Up: (0, -0.1), Qt.Key_Down: (0, 0.1)}
        if e.key() in step:
            self.yaw += step[e.key()][0]
            self.pitch += step[e.key()][1]
        elif e.key() in (Qt.Key_Plus, Qt.Key_Equal):
            self.zoom *= 1.1
        elif e.key() == Qt.Key_Minus:
            self.zoom /= 1.1
        else:
            return super().keyPressEvent(e)
        self.update()
