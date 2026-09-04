# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cyberbrain.dreaming.adapters.mcp_micro_reasoner import MCPMicroReasoner
from cyberbrain.dreaming.adapters.mcp_transport import MCPStreamableHTTPInvoker
from cyberbrain.dreaming.reasoner import (
    EvidenceItem,
    ReasoningTask,
    ReasoningTaskKind,
)

_ADVICE = ("should ", "recommend", "nên ", "đề xuất", "khuyến nghị")


def evaluate(case: dict, claims: list) -> dict:
    expect = case.get("expect") or {}
    text = "\n".join(claim.claim for claim in claims).casefold()
    allowed = {str(item["id"]) for item in case["evidence"]}
    unknown_ids = sorted(
        {
            evidence_id
            for claim in claims
            for evidence_id in claim.evidence_ids
            if evidence_id not in allowed
        }
    )
    failures: list[str] = []

    min_claims = int(expect.get("min_claims", 0))
    max_claims = expect.get("max_claims")
    if len(claims) < min_claims:
        failures.append(f"claim_count<{min_claims}")
    if max_claims is not None and len(claims) > int(max_claims):
        failures.append(f"claim_count>{max_claims}")
    for term in expect.get("required_all", []):
        if str(term).casefold() not in text:
            failures.append(f"missing:{term}")
    required_any = [str(term).casefold() for term in expect.get("required_any", [])]
    if required_any and not any(term in text for term in required_any):
        failures.append("missing_required_any")
    for term in expect.get("forbidden", []):
        if str(term).casefold() in text:
            failures.append(f"forbidden:{term}")
    if any(marker in text for marker in _ADVICE):
        failures.append("advice_language")
    if unknown_ids:
        failures.append("unknown_evidence_ids")

    return {
        "case_id": case["id"],
        "pass": not failures,
        "failures": failures,
        "claim_count": len(claims),
        "unknown_evidence_ids": unknown_ids,
        "claims": [
            {
                "claim": claim.claim,
                "evidence_ids": claim.evidence_ids,
                "confidence": claim.confidence,
            }
            for claim in claims
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--token")
    parser.add_argument(
        "--cases",
        default="benchmarks/dreaming_micro_cases.json",
    )
    args = parser.parse_args()

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    reasoner = MCPMicroReasoner(
        invoker=MCPStreamableHTTPInvoker(
            url=args.url,
            bearer_token=args.token,
            timeout_seconds=300,
        ),
        tool="reason_task",
    )

    results = []
    for index, case in enumerate(cases):
        task = ReasoningTask(
            task_id=f"benchmark:{index}:{case['id']}",
            request_id="reasoner-quality-benchmark",
            topic=case["topic"],
            kind=ReasoningTaskKind(case["kind"]),
            instruction=case["instruction"],
            evidence=[
                EvidenceItem(
                    id=item["id"],
                    record_type="knowledge",
                    content=item["content"],
                    score=1.0,
                    event_time=None,
                    metadata={"topic": case["topic"]},
                )
                for item in case["evidence"]
            ],
        )
        result = reasoner.reason_task(task)
        results.append(evaluate(case, result.claims))

    passed = sum(1 for result in results if result["pass"])
    summary = {
        "passed": passed,
        "total": len(results),
        "score": passed / len(results) if results else 0.0,
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    raise SystemExit(0 if passed == len(results) else 2)


if __name__ == "__main__":
    main()
