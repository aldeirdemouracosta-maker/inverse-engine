"""Tarefas longas em segundo plano (QThread) com progresso e cancelamento."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class Cancelled(Exception):
    pass


class Task(QThread):
    """Roda fn(progress, cancelled) numa thread. progress(atual, total, texto); cancelled() → bool."""
    progress = Signal(int, int, str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            result = self._fn(lambda a, b, t="": self.progress.emit(a, b, t), lambda: self._cancel)
            self.done.emit(result)
        except Cancelled:
            self.failed.emit("cancelado")
        except Exception as e:  # erro vira mensagem na interface, nunca derruba o app
            self.failed.emit(f"{type(e).__name__}: {e}")


def run_sync(fn):
    """Mesma assinatura, sem thread (testes e chamadas rápidas)."""
    return fn(lambda a, b, t="": None, lambda: False)
