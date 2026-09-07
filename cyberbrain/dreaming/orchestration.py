# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from cyberbrain.dreaming.reasoner import (
    DreamCandidate,
    DreamReasoner,
    DreamReasoningRequest,
    DreamReasoningResult,
    EvidenceItem,
    MicroReasoner,
    ReasoningClaim,
    ReasoningTask,
    ReasoningTaskKind,
    ReasoningTaskResult,
)
from cyberbrain.dreaming.relevance import TopicRelevanceGuard

_REPLACEMENT = ("removed", "replaced", "deprecated", "loại bỏ", "thay bằng", "không dùng nữa")
_CAVEAT = ("caveat", "lưu ý", "unresolved", "đang tắt", "fail", "failed", "không phải regression")
_VALIDATION = ("validate", "validation", "validated", "production_mode", "production mode")
_DECISION = ("decision", "quyết định", "llm", "script", "engine", "architecture", "kiến trúc")


@dataclass(frozen=True)
class MultipassPolicy:
    max_evidence_per_task: int = 4
    current_task_count: int = 2
    lesson_task_count: int = 2
    caveat_task_count: int = 2


class MultipassDreamReasoner(DreamReasoner):
    """Deterministically decomposes Dreaming into small evidence-grounded reasoning tasks."""

    def __init__(
        self,
        *,
        micro_reasoner: MicroReasoner,
        policy: MultipassPolicy | None = None,
        relevance_guard: TopicRelevanceGuard | None = None,
    ) -> None:
        self._micro_reasoner = micro_reasoner
        self._policy = policy or MultipassPolicy()
        self._relevance_guard = relevance_guard or TopicRelevanceGuard()

    def reason(self, request: DreamReasoningRequest) -> DreamReasoningResult:
        tasks = self.build_tasks(request)
        results = [self._micro_reasoner.reason_task(task) for task in tasks]
        return self.assemble(request, tasks=tasks, results=results)

    def build_tasks(self, request: DreamReasoningRequest) -> list[ReasoningTask]:
        return self._build_tasks(request)

    def assemble(
        self,
        request: DreamReasoningRequest,
        *,
        tasks: list[ReasoningTask],
        results: list[ReasoningTaskResult],
    ) -> DreamReasoningResult:
        task_ids = [task.task_id for task in tasks]
        duplicate_tasks = sorted(
            task_id for task_id in set(task_ids) if task_ids.count(task_id) > 1
        )
        if duplicate_tasks:
            raise ValueError(f"duplicate reasoning task IDs: {duplicate_tasks}")

        result_ids = [result.task_id for result in results]
        duplicate_results = sorted(
            task_id for task_id in set(result_ids) if result_ids.count(task_id) > 1
        )
        if duplicate_results:
            raise ValueError(f"duplicate micro reasoner result task IDs: {duplicate_results}")

        expected = set(task_ids)
        actual = set(result_ids)
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        if missing or unexpected:
            raise ValueError(
                "micro reasoner result task set mismatch: "
                f"missing={missing}, unexpected={unexpected}"
            )

        result_by_id = {result.task_id: result for result in results}
        candidates: list[DreamCandidate] = []
        dropped_advice_claims = 0
        dropped_irrelevant_claims = 0

        for task in tasks:
            result = result_by_id[task.task_id]
            if result.task_id != task.task_id:
                raise ValueError("micro reasoner response task_id does not match task")
            allowed = {item.id for item in task.evidence}
            for index, claim in enumerate(result.claims):
                self._validate_claim(task, claim, allowed)
                if self._contains_advice(claim.claim):
                    dropped_advice_claims += 1
                    continue
                if not self._relevance_guard.claim_relevant(topic=task.topic, text=claim.claim):
                    dropped_irrelevant_claims += 1
                    continue
                candidates.append(self._candidate_from_claim(task, claim, index))

        notes = [f"multipass_tasks={len(tasks)}"]
        if dropped_advice_claims:
            notes.append(f"dropped_advice_claims={dropped_advice_claims}")
        if dropped_irrelevant_claims:
            notes.append(f"dropped_irrelevant_claims={dropped_irrelevant_claims}")
        return DreamReasoningResult(
            request_id=request.request_id,
            candidates=candidates,
            notes=notes,
        )

    def _build_tasks(self, request: DreamReasoningRequest) -> list[ReasoningTask]:
        tasks: list[ReasoningTask] = []
        sequence = 0
        for topic in request.focal_topics:
            evidence = request.evidence_by_topic.get(topic, [])
            if not evidence:
                continue

            ordered = sorted(evidence, key=self._evidence_sort_key)
            latest = list(reversed(ordered))[: self._policy.max_evidence_per_task]
            replacement = self._matching(ordered, _REPLACEMENT)
            caveats = self._matching(ordered, _CAVEAT)
            decisions = self._matching(ordered, _DECISION)
            validation = self._matching(ordered, _VALIDATION)

            for task_index in range(min(self._policy.current_task_count, len(latest))):
                selected = latest[task_index : task_index + 2]
                sequence += 1
                tasks.append(
                    self._task(
                        request,
                        topic,
                        sequence,
                        ReasoningTaskKind.CURRENT_STATE,
                        "Extract one current supported fact. No advice or future plan.",
                        selected,
                    )
                )

            if replacement:
                sequence += 1
                tasks.append(
                    self._task(
                        request,
                        topic,
                        sequence,
                        ReasoningTaskKind.SUPERSEDED_OR_REMOVED,
                        (
                            "State one explicit removed, replaced, or superseded fact "
                            "and its replacement if present."
                        ),
                        replacement[: self._policy.max_evidence_per_task],
                    )
                )

            lesson_sources = self._dedupe_evidence(decisions + validation + latest)
            lesson_pairs = (
                self._pairwise(lesson_sources, self._policy.lesson_task_count)
                if len(lesson_sources) >= 2
                else []
            )
            for pair in lesson_pairs:
                sequence += 1
                tasks.append(
                    self._task(
                        request,
                        topic,
                        sequence,
                        ReasoningTaskKind.DURABLE_LESSON,
                        (
                            "Infer one established durable lesson supported by the supplied "
                            "evidence. Do not recommend future work."
                        ),
                        pair,
                    )
                )

            for item in caveats[: self._policy.caveat_task_count]:
                sequence += 1
                tasks.append(
                    self._task(
                        request,
                        topic,
                        sequence,
                        ReasoningTaskKind.CAVEAT,
                        (
                            "Extract only the unresolved caveat explicitly present in this "
                            "evidence. Do not interpret completed work as unresolved."
                        ),
                        [item],
                    )
                )

        return tasks

    @staticmethod
    def _task(
        request: DreamReasoningRequest,
        topic: str,
        sequence: int,
        kind: ReasoningTaskKind,
        instruction: str,
        evidence: list[EvidenceItem],
    ) -> ReasoningTask:
        return ReasoningTask(
            task_id=f"{request.request_id}:{sequence}:{kind.value}",
            request_id=request.request_id,
            topic=topic,
            kind=kind,
            instruction=instruction,
            evidence=evidence,
        )

    @staticmethod
    def _validate_claim(task: ReasoningTask, claim: ReasoningClaim, allowed: set[str]) -> None:
        if not claim.claim.strip():
            raise ValueError("micro reasoner returned an empty claim")
        if not 0.0 <= claim.confidence <= 1.0:
            raise ValueError("micro reasoner confidence must be within [0,1]")
        if not claim.evidence_ids:
            raise ValueError("micro reasoner claim must cite evidence")
        unknown = sorted(set(claim.evidence_ids) - allowed)
        if unknown:
            raise ValueError(f"micro reasoner fabricated evidence IDs: {unknown}")

    @staticmethod
    def _contains_advice(value: str) -> bool:
        lowered = value.casefold()
        return any(marker in lowered for marker in ("nên ", "đề xuất", "recommend", "should "))

    @staticmethod
    def _candidate_from_claim(
        task: ReasoningTask,
        claim: ReasoningClaim,
        index: int,
    ) -> DreamCandidate:
        mapping = {
            ReasoningTaskKind.CURRENT_STATE: ("fact", "new_knowledge", False),
            ReasoningTaskKind.SUPERSEDED_OR_REMOVED: (
                "rejected_approach",
                "rejected_approach",
                True,
            ),
            ReasoningTaskKind.DURABLE_LESSON: ("lesson", "new_knowledge", False),
            ReasoningTaskKind.CAVEAT: ("caveat", "context_dependent", False),
        }
        entity_type, classification, negative = mapping[task.kind]
        entity_name = MultipassDreamReasoner._entity_name(task.topic, task.kind, index)
        return DreamCandidate(
            entity_name=entity_name,
            entity_type=entity_type,
            summary=claim.claim[:180],
            content=claim.claim,
            evidence_ids=claim.evidence_ids,
            confidence=claim.confidence,
            classification=classification,
            negative_knowledge=negative,
            context={
                "reasoning_section": task.kind.value,
                "task_id": task.task_id,
                "topic": task.topic,
            },
        )

    @staticmethod
    def _entity_name(topic: str, kind: ReasoningTaskKind, index: int) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "_", topic.casefold()).strip("_") or "topic"
        return f"{normalized}_{kind.value}_{index + 1}"

    @staticmethod
    def _evidence_sort_key(item: EvidenceItem) -> tuple[int, str]:
        if item.event_time is None:
            return (1, "")
        return (0, item.event_time.isoformat())

    @staticmethod
    def _matching(items: Iterable[EvidenceItem], markers: tuple[str, ...]) -> list[EvidenceItem]:
        return [
            item
            for item in items
            if any(marker in item.content.casefold() for marker in markers)
        ]

    @staticmethod
    def _dedupe_evidence(items: Iterable[EvidenceItem]) -> list[EvidenceItem]:
        result: list[EvidenceItem] = []
        seen: set[str] = set()
        for item in items:
            if item.id in seen:
                continue
            seen.add(item.id)
            result.append(item)
        return result

    @staticmethod
    def _pairwise(items: list[EvidenceItem], limit: int) -> list[list[EvidenceItem]]:
        if not items:
            return []
        if len(items) == 1:
            return [[items[0]]]
        pairs: list[list[EvidenceItem]] = []
        for index in range(min(limit, len(items) - 1)):
            pairs.append([items[index], items[index + 1]])
        return pairs
