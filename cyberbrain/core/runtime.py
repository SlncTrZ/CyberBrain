# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass

from cyberbrain.core.metrics import MetricsRegistry
from cyberbrain.core.settings import Settings
from cyberbrain.embedding.base import EmbeddingProvider
from cyberbrain.embedding.ollama import OllamaEmbeddingProvider
from cyberbrain.knowledge.evolution import KnowledgeEvolutionService
from cyberbrain.knowledge.search import KnowledgeSearchService
from cyberbrain.memory.service import MemoryService
from cyberbrain.storage.base import PointRepository
from cyberbrain.storage.qdrant import QdrantRepository


@dataclass
class RuntimeServices:
    metrics: MetricsRegistry
    repository: PointRepository
    embedding: EmbeddingProvider
    knowledge_evolution: KnowledgeEvolutionService
    knowledge_search: KnowledgeSearchService
    memory: MemoryService


def build_runtime(settings: Settings) -> RuntimeServices:
    metrics = MetricsRegistry()
    repository = QdrantRepository(
        base_url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        metrics=metrics,
    )
    embedding = OllamaEmbeddingProvider(
        base_url=settings.embedding_url,
        model=settings.embedding_model,
        dimension=settings.embedding_dimension,
        version=settings.embedding_version,
        metrics=metrics,
    )

    probe = embedding.embed("cyberbrain startup probe")
    if len(probe) != settings.embedding_dimension:
        raise RuntimeError(
            "embedding runtime dimension mismatch: "
            f"expected {settings.embedding_dimension}, got {len(probe)}"
        )

    repository.ensure_collection(
        settings.knowledge_collection,
        vector_size=settings.embedding_dimension,
    )
    repository.ensure_collection(
        settings.episodic_collection,
        vector_size=settings.embedding_dimension,
    )

    knowledge_evolution = KnowledgeEvolutionService(
        repository=repository,
        embedding=embedding,
        collection=settings.knowledge_collection,
        process_lock_file=settings.knowledge_evolution_lock_file,
    )
    knowledge_evolution.reconcile_pending()

    return RuntimeServices(
        metrics=metrics,
        repository=repository,
        embedding=embedding,
        knowledge_evolution=knowledge_evolution,
        knowledge_search=KnowledgeSearchService(
            repository=repository,
            embedding=embedding,
            collection=settings.knowledge_collection,
            score_threshold=settings.knowledge_search_score_threshold,
        ),
        memory=MemoryService(
            repository=repository,
            embedding=embedding,
            collection=settings.episodic_collection,
            score_threshold=settings.memory_search_score_threshold,
        ),
    )
