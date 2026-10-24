#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Laya System 1 Triage Worker for CyberBrain Review Backlog.

Connects CyberBrain's dream_reviews queue to the Laya Decision Engine (System 1)
on port 8772 to fast-triage candidates into:
  - auto-reject: obvious noise, stop-word artifacts, duplicate chatter.
  - auto-approve: high-confidence, clean, verified engineering knowledge.
  - escalate: contradictions, low-confidence or ambiguous items preserved for human review.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("laya-triage")

# Known stop-word artifacts from regex entity extractors
STOP_WORD_PREFIXES = (
    "and_", "the_", "or_", "in_", "to_", "of_", "a_", "an_", "is_", "it_",
    "that_", "this_", "for_", "with_", "as_", "at_", "by_", "from_", "on_",
)

DEFAULT_QUESTIONS = {
    "knowledge_quality": {
        "type": "choice",
        "instructions": "Đánh giá chất lượng và giá trị lưu trữ của tri thức này:",
        "criteria": {
            "junk": (
                "Thông tin chào hỏi, trạng thái tạm thời, rác ngôn ngữ, "
                "tên thực thể vô nghĩa (stop-words), lỗi metadata."
            ),
            "durable_knowledge": (
                "Quy tắc kiến trúc, thông số kỹ thuật, bài học kinh nghiệm, "
                "ràng buộc hệ thống có giá trị lâu dài."
            ),
            "ambiguous": "Thông tin mơ hồ, ngữ cảnh hẹp, hoặc không thể kiểm chứng chắc chắn.",
        },
    },
    "action": {
        "type": "choice",
        "instructions": "Hành động đề xuất cho candidate này:",
        "criteria": {
            "reject": "Bác bỏ vì là rác, vô nghĩa, hoặc lỗi trích xuất.",
            "approve": (
                "Duyệt lưu trữ vào Knowledge vì thông tin rõ ràng, "
                "giá trị cao và căn cứ vững chắc."
            ),
            "escalate": "Chuyển người duyệt vì mâu thuẫn hoặc chưa đủ chắc chắn.",
        },
    },
}


@dataclass
class TriageStats:
    total_evaluated: int = 0
    auto_rejected: int = 0
    auto_approved: int = 0
    escalated_for_human: int = 0
    errors: int = 0


class CyberBrainMCPClient:
    """Lightweight HTTP client for CyberBrain MCP server."""

    def __init__(self, base_url: str, token: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.session_id: str | None = None
        self.client = httpx.Client(
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json, text/event-stream",
            },
            timeout=self.timeout,
        )

    def ensure_session(self) -> None:
        if self.session_id:
            return
        logger.info("Initializing MCP session with %s...", self.base_url)
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "laya-review-triage", "version": "1.0.0"},
            },
        }
        res = self.client.post(self.base_url, json=payload)
        res.raise_for_status()
        self.session_id = res.headers.get("mcp-session-id")
        if not self.session_id:
            raise RuntimeError("CyberBrain MCP failed to provide mcp-session-id")
        self.client.headers["mcp-session-id"] = self.session_id
        logger.info("MCP session established (id: %s)", self.session_id)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self.ensure_session()
        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000) % 1000000,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        try:
            res = self.client.post(self.base_url, json=payload)
            res.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400 and "session" in exc.response.text.lower():
                logger.warning("Session expired, reconnecting...")
                self.session_id = None
                self.ensure_session()
                res = self.client.post(self.base_url, json=payload)
                res.raise_for_status()
            else:
                raise

        # Parse SSE data
        for line in res.text.splitlines():
            if line.startswith("data: "):
                data = json.loads(line[6:])
                if "error" in data:
                    raise RuntimeError(f"MCP error: {data['error']}")
                content = data["result"]["content"]
                if content and content[0]["type"] == "text":
                    return json.loads(content[0]["text"])
                return data["result"]
        raise RuntimeError(f"No valid response data in MCP answer: {res.text[:200]}")


class LayaTriageWorker:
    def __init__(
        self,
        mcp_url: str,
        mcp_token: str,
        laya_url: str,
        min_approve_conf: float = 0.85,
        min_reject_conf: float = 0.80,
        dry_run: bool = True,
    ) -> None:
        self.mcp = CyberBrainMCPClient(mcp_url, mcp_token)
        self.laya_url = laya_url.rstrip("/")
        self.min_approve_conf = min_approve_conf
        self.min_reject_conf = min_reject_conf
        self.dry_run = dry_run
        self.laya_client = httpx.Client(timeout=20.0)

    def fetch_pending_reviews(
        self, limit: int = 50, project: str | None = None
    ) -> list[dict[str, Any]]:
        args: dict[str, Any] = {"limit": limit}
        if project:
            args["project"] = project
        return self.mcp.call_tool("dream_reviews", args)

    def evaluate_candidate(self, item: dict[str, Any]) -> dict[str, Any]:
        candidate = item.get("candidate", {})
        entity_name = str(candidate.get("entity_name") or "")
        entity_type = str(candidate.get("entity_type") or "")
        summary = str(candidate.get("summary") or "")
        content = str(candidate.get("content") or "")
        reasons = item.get("reasons") or []
        classification = candidate.get("classification") or ""

        # RULE 1: Stop-word artifact fast-path
        if any(entity_name.lower().startswith(p) for p in STOP_WORD_PREFIXES):
            return {
                "decision": "reject",
                "confidence": 0.99,
                "reason": f"Laya S1 rule: stop-word entity_name artifact '{entity_name}'",
            }

        # RULE 2: Contradictions must NEVER be auto-resolved
        if classification in ("contradiction", "true_contradiction"):
            return {
                "decision": "escalate",
                "confidence": 1.0,
                "reason": "Safety rule: contradiction requires human review",
            }

        # RULE 3: Send to Laya for System 1 Evaluation
        state = (
            f"Entity Name: {entity_name}\n"
            f"Entity Type: {entity_type}\n"
            f"Summary: {summary}\n"
            f"Content: {content}\n"
            f"Gate Reasons: {reasons}\n"
            f"Promotion Confidence: {item.get('promotion_confidence', 0.0)}"
        )

        try:
            req_payload = {
                "state": state,
                "questions": DEFAULT_QUESTIONS,
                "model": "multilingual",
            }
            res = self.laya_client.post(f"{self.laya_url}/v1/systemone", json=req_payload)
            res.raise_for_status()
            data = res.json()
            answers = data["answers"]

            act_choice = answers["action"]["choice"]
            act_conf = float(answers["action"]["confidence"])
            qual_choice = answers["knowledge_quality"]["choice"]
            qual_conf = float(answers["knowledge_quality"]["confidence"])

            max_conf = max(act_conf, qual_conf)
            is_reject = act_choice == "reject" or qual_choice == "junk"
            if is_reject and max_conf >= self.min_reject_conf:
                return {
                    "decision": "reject",
                    "confidence": max_conf,
                    "reason": f"Laya S1 auto-reject: {qual_choice} (conf={max_conf:.2f})",
                }

            if (
                act_choice == "approve"
                and qual_choice == "durable_knowledge"
                and act_conf >= self.min_approve_conf
            ):
                return {
                    "decision": "approve",
                    "confidence": act_conf,
                    "reason": f"Laya S1 auto-approve: durable_knowledge (conf={act_conf:.2f})",
                }

            reason_msg = f"Laya S1 triage: ambiguous ({act_choice}, conf={act_conf:.2f})"
            return {
                "decision": "escalate",
                "confidence": act_conf,
                "reason": reason_msg,
            }

        except Exception as exc:
            logger.error("Laya inference failed for %s: %s", entity_name, exc)
            return {
                "decision": "error",
                "confidence": 0.0,
                "reason": f"Inference error: {exc}",
            }

    def resolve_review(
        self,
        dream_run_id: str,
        candidate_index: int,
        resolution: str,
        reason: str,
    ) -> Any:
        if self.dry_run:
            return {"status": "dry_run"}
        args = {
            "dream_run_id": dream_run_id,
            "candidate_index": candidate_index,
            "resolution": resolution,
            "reviewer": "laya:system-1",
            "reason": reason,
        }
        return self.mcp.call_tool("dream_review_resolve", args)

    def run_batch(self, limit: int = 50, project: str | None = None) -> TriageStats:
        stats = TriageStats()
        items = self.fetch_pending_reviews(limit=limit, project=project)
        if not items:
            logger.info("No pending review items found.")
            return stats

        logger.info(
            "Evaluating batch of %d candidates (dry_run=%s)...",
            len(items),
            self.dry_run,
        )

        for idx, item in enumerate(items, 1):
            stats.total_evaluated += 1
            dream_run_id = item["dream_run_id"]
            candidate_index = item["candidate_index"]
            candidate = item.get("candidate", {})
            entity = candidate.get("entity_name", "unknown")
            summary = candidate.get("summary", "")[:60]

            eval_res = self.evaluate_candidate(item)
            decision = eval_res["decision"]
            reason = eval_res["reason"]

            if decision == "reject":
                stats.auto_rejected += 1
                logger.info(
                    "[%d/%d] ❌ REJECT: %s (%s) -> %s",
                    idx, len(items), entity, summary, reason,
                )
                self.resolve_review(dream_run_id, candidate_index, "rejected", reason)

            elif decision == "approve":
                stats.auto_approved += 1
                logger.info(
                    "[%d/%d] ✅ APPROVE: %s (%s) -> %s",
                    idx, len(items), entity, summary, reason,
                )
                self.resolve_review(dream_run_id, candidate_index, "approved", reason)

            elif decision == "escalate":
                stats.escalated_for_human += 1
                logger.info(
                    "[%d/%d] ⏸️ ESCALATE: %s (%s) -> %s",
                    idx, len(items), entity, summary, reason,
                )

            else:
                stats.errors += 1
                logger.warning("[%d/%d] ⚠️ ERROR: %s -> %s", idx, len(items), entity, reason)

        return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Laya System 1 Triage Worker for CyberBrain Backlog"
    )
    parser.add_argument(
        "--mcp-url",
        default=os.environ.get("CYBERBRAIN_MCP_URL", "http://127.0.0.1:8767/mcp"),
        help="CyberBrain MCP URL",
    )
    parser.add_argument(
        "--mcp-token",
        default=os.environ.get("CYBERBRAIN_MCP_TOKEN", ""),
        help="CyberBrain MCP Token",
    )
    parser.add_argument(
        "--laya-url",
        default=os.environ.get("LAYA_URL", "http://127.0.0.1:8772"),
        help="Laya service URL",
    )
    parser.add_argument(
        "--limit", type=int, default=50, help="Batch limit per run (default: 50)"
    )
    parser.add_argument("--project", default=None, help="Filter by project scope")
    parser.add_argument(
        "--apply", action="store_true", help="Apply resolutions (default is dry-run)"
    )
    parser.add_argument(
        "--daemon", action="store_true", help="Run continuously in background daemon mode"
    )
    parser.add_argument(
        "--interval", type=int, default=60, help="Sleep interval in seconds for daemon mode"
    )
    args = parser.parse_args()

    if not args.mcp_token:
        parser.error("--mcp-token or CYBERBRAIN_MCP_TOKEN environment variable is required")

    dry_run = not args.apply

    logger.info("Starting Laya Triage Worker (dry_run=%s, limit=%d)...", dry_run, args.limit)
    worker = LayaTriageWorker(
        mcp_url=args.mcp_url,
        mcp_token=args.mcp_token,
        laya_url=args.laya_url,
        dry_run=dry_run,
    )

    if args.daemon:
        logger.info("Running in daemon mode (interval: %ds)...", args.interval)
        while True:
            try:
                stats = worker.run_batch(limit=args.limit, project=args.project)
                logger.info(
                    "Batch summary: Total=%d | Auto-Reject=%d | Auto-Approve=%d "
                    "| Escalated=%d | Errors=%d",
                    stats.total_evaluated, stats.auto_rejected, stats.auto_approved,
                    stats.escalated_for_human, stats.errors,
                )
            except Exception as exc:
                logger.error("Daemon error during batch run: %s", exc)
            time.sleep(args.interval)
    else:
        stats = worker.run_batch(limit=args.limit, project=args.project)
        print("\n" + "=" * 60)
        print("TRIAGE WORKER SUMMARY REPORT:")
        mode_str = "DRY-RUN (Simulated)" if dry_run else "APPLIED (Live Writes)"
        print(f"  Mode:                {mode_str}")
        print(f"  Total Evaluated:     {stats.total_evaluated}")
        rej_pct = (stats.auto_rejected / max(1, stats.total_evaluated)) * 100
        print(f"  Auto-Rejected:       {stats.auto_rejected} ({rej_pct:.1f}%)")
        app_pct = (stats.auto_approved / max(1, stats.total_evaluated)) * 100
        print(f"  Auto-Approved:       {stats.auto_approved} ({app_pct:.1f}%)")
        esc_pct = (stats.escalated_for_human / max(1, stats.total_evaluated)) * 100
        print(f"  Escalated to Human:  {stats.escalated_for_human} ({esc_pct:.1f}%)")
        print(f"  Errors:              {stats.errors}")
        print("=" * 60)


if __name__ == "__main__":
    main()
