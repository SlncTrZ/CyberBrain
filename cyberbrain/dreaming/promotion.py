# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from cyberbrain.dreaming.audit import DreamRun, DreamRunAuditStore
from cyberbrain.dreaming.gate import DreamEvidenceGate, DreamGateResult
from cyberbrain.dreaming.reasoner import DreamReasoningRequest, DreamReasoningResult


@dataclass(frozen=True)
class DreamPromotionEvaluation:
    dream_run: DreamRun
    gate: DreamGateResult


class DreamPromotionCoordinator:
    """Evaluates and audits Dream candidates without mutating Knowledge."""

    def __init__(
        self,
        *,
        gate: DreamEvidenceGate,
        audit_store: DreamRunAuditStore,
    ) -> None:
        self._gate = gate
        self._audit_store = audit_store

    def evaluate(
        self,
        *,
        request: DreamReasoningRequest,
        result: DreamReasoningResult,
        dream_run_id: str | None = None,
    ) -> DreamPromotionEvaluation:
        run_id = dream_run_id or str(uuid4())
        dream_run = self._audit_store.start(dream_run_id=run_id, request=request)
        try:
            gate_result = self._gate.evaluate(request, result)
            dream_run = self._audit_store.complete(
                dream_run_id=dream_run.id,
                result=result,
                gate=gate_result,
            )
        except Exception:
            self._audit_store.mark_failed(dream_run.id)
            raise

        return DreamPromotionEvaluation(
            dream_run=dream_run,
            gate=gate_result,
        )
