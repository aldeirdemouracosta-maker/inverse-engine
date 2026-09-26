"""Banco de descobertas (findings) e política de edição por estado.

Descoberta comprovada e hipótese nunca se misturam: cada campo do perfil aponta para um
finding, e o estado do finding decide se o campo pode ser editado.
"""
from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass
from pathlib import Path

STATES = ("DESCONHECIDO", "HIPOTESE", "PROVAVEL", "CONFIRMADO")  # ordem crescente de certeza
EVIDENCE_KINDS = {"static_values", "reference_value", "statistical_match", "in_game_test",
                  "emulator_breakpoint", "lvcp_evidence", "tim_scan", "analysis_note"}


class FindingError(ValueError):
    pass


@dataclass(frozen=True)
class EditPolicy:
    editable: bool          # pode editar como campo
    raw_only: bool          # só como byte cru (Modo Pesquisa)
    experimental: bool      # operação marcada como experimental no relatório
    badge: str              # selo discreto na interface ("" quando não há)
    reason: str


def edit_policy(status: str, research_mode: bool = False) -> EditPolicy:
    if status == "CONFIRMADO":
        return EditPolicy(True, False, False, "", "confirmado")
    if status == "PROVAVEL":
        return EditPolicy(True, False, False, "provável", "provável: editável, com selo")
    if status == "HIPOTESE":
        if research_mode:
            return EditPolicy(True, False, True, "hipótese", "hipótese: só no Modo Pesquisa, experimental")
        return EditPolicy(False, False, True, "hipótese", "hipótese: ative o Modo Pesquisa para editar")
    if status == "DESCONHECIDO":
        return EditPolicy(False, research_mode, True, "desconhecido",
                          "desconhecido: sem edição por campo; só byte cru no Modo Pesquisa")
    raise FindingError(f"estado inválido: {status}")


class FindingsDB:
    def __init__(self, data: dict, path: Path | None = None):
        self.path = path
        self.meta = {k: v for k, v in data.items() if k != "findings"}
        self.findings: dict[str, dict] = {}
        for f in data.get("findings", []):
            if f["status"] not in STATES:
                raise FindingError(f"{f['id']}: estado inválido {f['status']}")
            if f["id"] in self.findings:
                raise FindingError(f"finding duplicado: {f['id']}")
            self.findings[f["id"]] = f

    @classmethod
    def load(cls, path: str | Path) -> "FindingsDB":
        p = Path(path)
        return cls(json.loads(p.read_text(encoding="utf-8")), p)

    def save(self, path: str | Path | None = None) -> Path:
        p = Path(path or self.path)
        doc = dict(self.meta, findings=list(self.findings.values()))
        p.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return p

    def get(self, finding_id: str) -> dict:
        return self.findings[finding_id]

    def status(self, finding_id: str | None) -> str:
        if not finding_id or finding_id not in self.findings:
            return "DESCONHECIDO"
        return self.findings[finding_id]["status"]

    def policy(self, finding_id: str | None, research_mode: bool = False) -> EditPolicy:
        return edit_policy(self.status(finding_id), research_mode)

    def by_status(self) -> dict[str, int]:
        out = {s: 0 for s in STATES}
        for f in self.findings.values():
            out[f["status"]] += 1
        return out

    def add_evidence(self, finding_id: str, kind: str, detail: str, date: str | None = None) -> dict:
        if kind not in EVIDENCE_KINDS:
            raise FindingError(f"tipo de evidência desconhecido: {kind}")
        ev = {"kind": kind, "detail": detail, "date": date or _today()}
        self.findings[finding_id]["evidence"].append(ev)
        return ev

    def set_status(self, finding_id: str, new: str, why: str, evidence: dict | None = None) -> None:
        """Rebaixar é sempre permitido. Promover exige evidência nova registrada nesta chamada.

        Promover a CONFIRMADO é o portão P3: quem chama só faz isso depois que o usuário confirmou.
        """
        if new not in STATES:
            raise FindingError(f"estado inválido: {new}")
        f = self.findings[finding_id]
        old = f["status"]
        if STATES.index(new) > STATES.index(old):
            if not evidence:
                raise FindingError(f"{finding_id}: promover de {old} para {new} exige evidência nova")
            self.add_evidence(finding_id, evidence["kind"], evidence["detail"], evidence.get("date"))
        f["status"] = new
        f.setdefault("history", []).append({"date": _today(), "from": old, "to": new, "why": why})


def _today() -> str:
    return _dt.date.today().isoformat()
