# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from typing import Any


class DeterministicMicroReasoningBackend:
    """Deterministic dev/integration backend that never invents beyond supplied evidence."""

    def reason_task(self, request: dict[str, Any]) -> dict[str, Any]:
        evidence = list(request.get("evidence") or [])
        if not evidence:
            return {"task_id": request["task_id"], "claims": []}

        first = evidence[0]
        content = str(first.get("content") or "").strip()
        evidence_id = str(first.get("id") or "").strip()
        if not content or not evidence_id:
            return {"task_id": request["task_id"], "claims": []}

        return {
            "task_id": request["task_id"],
            "claims": [
                {
                    "claim": content,
                    "evidence_ids": [evidence_id],
                    "confidence": 0.9,
                }
            ],
        }
