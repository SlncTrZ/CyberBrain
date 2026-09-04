# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cyberbrain.core.runtime import RuntimeServices, build_runtime
from cyberbrain.core.settings import Settings
from cyberbrain.dreaming.adapters.mcp_micro_reasoner import MCPMicroReasoner
from cyberbrain.dreaming.adapters.mcp_transport import MCPStreamableHTTPInvoker
from cyberbrain.dreaming.associative import BoundedAssociativeRecall
from cyberbrain.dreaming.audit import DreamRunAuditStore
from cyberbrain.dreaming.engine import DreamingEngine
from cyberbrain.dreaming.gate import DreamEvidenceGate
from cyberbrain.dreaming.operations import DreamOperations
from cyberbrain.dreaming.orchestration import MultipassDreamReasoner
from cyberbrain.dreaming.promotion import DreamPromotionCoordinator
from cyberbrain.dreaming.queue import DreamQueue
from cyberbrain.dreaming.retriever import QdrantEvidenceRetriever
from cyberbrain.dreaming.session import QdrantSessionEpisodeLoader
from cyberbrain.dreaming.worker import DreamWorker
from cyberbrain.dreaming.writeback import DreamKnowledgeWriter, DreamWritebackCoordinator


@dataclass(frozen=True)
class DreamWorkerRuntime:
    services: RuntimeServices
    queue: DreamQueue
    audit: DreamRunAuditStore
    worker: DreamWorker


def build_dream_operations(
    settings: Settings,
    *,
    services: RuntimeServices | None = None,
) -> DreamOperations:
    _ensure_parent(settings.dream_queue_db)
    _ensure_parent(settings.dream_audit_db)
    writer = (
        DreamKnowledgeWriter(services.knowledge_evolution)
        if services is not None
        else None
    )
    return DreamOperations(
        queue=DreamQueue(settings.dream_queue_db),
        audit=DreamRunAuditStore(settings.dream_audit_db),
        writer=writer,
    )


def build_dream_worker_runtime(settings: Settings) -> DreamWorkerRuntime:
    settings.validate_dream_worker()
    _ensure_parent(settings.dream_queue_db)
    _ensure_parent(settings.dream_audit_db)

    services = build_runtime(settings)
    queue = DreamQueue(settings.dream_queue_db)
    audit = DreamRunAuditStore(settings.dream_audit_db)

    retriever = QdrantEvidenceRetriever(
        repository=services.repository,
        embedding=services.embedding,
        knowledge_collection=settings.knowledge_collection,
        episodic_collection=settings.episodic_collection,
    )
    associative = BoundedAssociativeRecall(
        retriever=retriever,
        max_depth=settings.dream_association_depth,
        per_query_limit=settings.dream_association_per_query_limit,
        total_limit=settings.dream_association_total_limit,
    )
    invoker = MCPStreamableHTTPInvoker(
        url=str(settings.dream_reasoner_url),
        bearer_token=settings.dream_reasoner_bearer_token,
        api_key=settings.dream_reasoner_api_key,
        timeout_seconds=settings.dream_reasoner_timeout_seconds,
        metrics=services.metrics,
    )
    micro_reasoner = MCPMicroReasoner(
        invoker=invoker,
        tool=settings.dream_reasoner_tool,
    )
    reasoner = MultipassDreamReasoner(micro_reasoner=micro_reasoner)
    engine = DreamingEngine(
        retriever=retriever,
        reasoner=reasoner,
        associative_expander=associative,
        per_bucket_limit=settings.dream_per_bucket_limit,
    )
    promotion = DreamPromotionCoordinator(
        gate=DreamEvidenceGate(),
        audit_store=audit,
    )
    writer = DreamKnowledgeWriter(services.knowledge_evolution)
    writeback = DreamWritebackCoordinator(
        writer=writer,
        audit_store=audit,
    )
    session_loader = QdrantSessionEpisodeLoader(
        repository=services.repository,
        collection=settings.episodic_collection,
    )
    worker = DreamWorker(
        queue=queue,
        session_loader=session_loader,
        engine=engine,
        promotion=promotion,
        writeback=writeback,
        metrics=services.metrics,
    )
    return DreamWorkerRuntime(
        services=services,
        queue=queue,
        audit=audit,
        worker=worker,
    )


def _ensure_parent(path: str) -> None:
    parent = Path(path).expanduser().resolve().parent
    parent.mkdir(parents=True, exist_ok=True)
