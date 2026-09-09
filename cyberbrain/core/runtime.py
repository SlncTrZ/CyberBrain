# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from dataclasses import dataclass

from cyberbrain.cognition.calibration import MetacognitionCalibrationService
from cyberbrain.cognition.prediction import PredictionLearningService
from cyberbrain.cognition.runtime_path import CognitiveRuntimePath
from cyberbrain.core.metrics import MetricsRegistry
from cyberbrain.core.settings import Settings
from cyberbrain.embedding.base import EmbeddingProvider
from cyberbrain.embedding.ollama import OllamaEmbeddingProvider
from cyberbrain.knowledge.evolution import KnowledgeEvolutionService
from cyberbrain.knowledge.search import KnowledgeSearchService
from cyberbrain.lifecycle import MemoryLifecycleService
from cyberbrain.memory.service import MemoryService
from cyberbrain.retrieval.shadow import KnowledgeLiteralShadowObserver
from cyberbrain.self_model import SelfModelPersistence, SelfModelService
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
    prediction_learning: PredictionLearningService
    metacognition_calibration: MetacognitionCalibrationService
    self_model: SelfModelService
    self_model_persistence: SelfModelPersistence
    memory_lifecycle: MemoryLifecycleService
    cognition_path: CognitiveRuntimePath


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

    memory = MemoryService(
        repository=repository,
        embedding=embedding,
        collection=settings.episodic_collection,
        score_threshold=settings.memory_search_score_threshold,
    )
    prediction_learning = PredictionLearningService(
        memory=memory,
        repository=repository,
        episodic_collection=settings.episodic_collection,
    )
    literal_shadow = (
        KnowledgeLiteralShadowObserver(
            repository=repository,
            collection=settings.knowledge_collection,
            metrics=metrics,
            cache_ttl_seconds=settings.retrieval_literal_shadow_cache_ttl_seconds,
            max_records=settings.retrieval_literal_shadow_max_records,
        )
        if settings.retrieval_literal_shadow_enabled
        else None
    )
    self_model = SelfModelService()
    self_model_persistence = SelfModelPersistence(
        evolution=knowledge_evolution,
        repository=repository,
        collection=settings.knowledge_collection,
    )
    memory_lifecycle = MemoryLifecycleService(repository=repository)
    cognition_path = CognitiveRuntimePath(
        repository=repository,
        knowledge_collection=settings.knowledge_collection,
        episodic_collection=settings.episodic_collection,
        metrics=metrics,
        self_model=self_model,
        self_model_persistence=self_model_persistence,
        memory_lifecycle=memory_lifecycle,
        enabled=settings.cognition_m3_m7_enabled,
        m6_auto_accept=settings.cognition_m6_auto_accept_enabled,
        m7_actuation=settings.cognition_m7_actuation_enabled,
        prefetch_multiplier=settings.cognition_prefetch_multiplier,
        concept_evidence_limit=settings.cognition_concept_evidence_limit,
    )
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
            literal_shadow=literal_shadow,
        ),
        memory=memory,
        prediction_learning=prediction_learning,
        metacognition_calibration=MetacognitionCalibrationService(
            prediction_learning=prediction_learning,
        ),
        self_model=self_model,
        self_model_persistence=self_model_persistence,
        memory_lifecycle=memory_lifecycle,
        cognition_path=cognition_path,
    )
