# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import replace

from cyberbrain.dreaming.audit import DreamRunAuditStore
from cyberbrain.dreaming.gate import DreamGateResult, PromotionDecision


class DreamReviewResolver:
    def __init__(self, audit_store: DreamRunAuditStore) -> None:
        self._audit_store = audit_store

    def apply(self, *, dream_run_id: str, gate: DreamGateResult) -> DreamGateResult:
        resolved = []
        for decision in gate.candidates:
            if decision.decision != PromotionDecision.REVIEW:
                resolved.append(decision)
                continue

            review = self._audit_store.review_resolution(
                dream_run_id,
                decision.candidate_index,
            )
            if review is None:
                resolved.append(decision)
                continue

            if review["resolution"] == "approved":
                resolved.append(
                    replace(
                        decision,
                        decision=PromotionDecision.PROMOTE,
                        reasons=[*decision.reasons, "human_review_approved"],
                    )
                )
            elif review["resolution"] == "rejected":
                resolved.append(
                    replace(
                        decision,
                        decision=PromotionDecision.REJECT,
                        reasons=[*decision.reasons, "human_review_rejected"],
                    )
                )
            else:
                raise ValueError(f"unsupported review resolution: {review['resolution']}")

        return DreamGateResult(request_id=gate.request_id, candidates=resolved)
