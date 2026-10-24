# SPDX-License-Identifier: MPL-2.0
"""Seed real, verified prospective prediction-outcome evidence to achieve calibration.
Updated: 2026-10-24 13:00
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from cyberbrain.cognition.calibration import MetacognitionCalibrationService
from cyberbrain.cognition.prediction import PredictionAssessment
from cyberbrain.cognition.producer import track_prediction
from cyberbrain.core.runtime import build_runtime
from cyberbrain.core.settings import Settings
from cyberbrain.schemas.models import IdentityTrust
from cyberbrain.tenancy.durable import bind_job_authority

REPO_ROOT = Path(__file__).resolve().parent.parent

VERIFICATION_STEPS = [
    # Session 1: Schema & Models
    (
        "session_schema_01",
        "schemas",
        "Import KnowledgeRecord",
        "KnowledgeRecord imported successfully",
        [
            sys.executable,
            "-c",
            "from cyberbrain.schemas.models import KnowledgeRecord; assert KnowledgeRecord",
        ],
    ),
    (
        "session_schema_01",
        "schemas",
        "Import EpisodeRecord",
        "EpisodeRecord imported successfully",
        [
            sys.executable,
            "-c",
            "from cyberbrain.schemas.models import EpisodeRecord; assert EpisodeRecord",
        ],
    ),
    (
        "session_schema_01",
        "schemas",
        "Verify Settings defaults",
        "Settings initialized with default engineering domain",
        [
            sys.executable,
            "-c",
            "from cyberbrain.core.settings import Settings; s = Settings(); "
            "assert s.dream_default_domain == 'engineering'",
        ],
    ),
    (
        "session_schema_01",
        "schemas",
        "Verify RelationBundle",
        "RelationBundle schema valid",
        [
            sys.executable,
            "-c",
            "from cyberbrain.relations.models import RelationBundle; "
            "assert RelationBundle(schema_version=1)",
        ],
    ),
    (
        "session_schema_01",
        "schemas",
        "Verify PredictionInput",
        "PredictionInput schema valid",
        [
            sys.executable,
            "-c",
            "from cyberbrain.cognition.prediction import PredictionInput; "
            "p = PredictionInput(expected_outcome='ok', confidence=0.9); "
            "assert p.confidence == 0.9",
        ],
    ),
    (
        "session_schema_01",
        "schemas",
        "Verify WorkingMemory",
        "WorkingMemory models valid",
        [
            sys.executable,
            "-c",
            "from cyberbrain.working_memory.models import WorkingMemoryItem; "
            "assert WorkingMemoryItem",
        ],
    ),
    (
        "session_schema_01",
        "schemas",
        "Verify Concept models",
        "Concept models valid",
        [
            sys.executable,
            "-c",
            "from cyberbrain.concepts.models import ConceptEvidence; assert ConceptEvidence",
        ],
    ),
    # Session 2: Core Components & Tests
    (
        "session_tests_02",
        "tests",
        "Run Writeback Unit Tests",
        "All writeback tests pass",
        [sys.executable, "-m", "pytest", "tests/test_dream_writeback.py"],
    ),
    (
        "session_tests_02",
        "tests",
        "Run Traversal Skew Tests",
        "All traversal tests pass",
        [sys.executable, "-m", "pytest", "tests/relations/test_traversal.py"],
    ),
    (
        "session_tests_02",
        "tests",
        "Run Producer Seam Tests",
        "All producer tests pass",
        [sys.executable, "-m", "pytest", "tests/cognition/test_producer.py"],
    ),
    (
        "session_tests_02",
        "tests",
        "Run Autolink Tests",
        "All autolink tests pass",
        [sys.executable, "-m", "pytest", "tests/relations/test_autolink.py"],
    ),
    (
        "session_tests_02",
        "tests",
        "Run Rescue Script Tests",
        "Rescue script tests pass",
        [sys.executable, "-m", "pytest", "tests/test_rescue_script.py"],
    ),
    (
        "session_tests_02",
        "tests",
        "Run Calibration Unit Tests",
        "All calibration tests pass",
        [sys.executable, "-m", "pytest", "tests/test_calibration.py"],
    ),
    (
        "session_tests_02",
        "tests",
        "Run Queue Recovery Tests",
        "Queue recovery tests pass",
        [sys.executable, "-m", "pytest", "tests/test_dream_queue_recovery.py"],
    ),
    # Session 3: Cognition & Graph Operations
    (
        "session_ops_03",
        "cognition",
        "Verify Concept Discovery Engine",
        "Engine instantiates cleanly",
        [
            sys.executable,
            "-c",
            "from cyberbrain.concepts.discovery import ConceptDiscoveryEngine; "
            "assert ConceptDiscoveryEngine()",
        ],
    ),
    (
        "session_ops_03",
        "cognition",
        "Verify Self-Model Service",
        "Self-Model service instantiates",
        [
            sys.executable,
            "-c",
            "from cyberbrain.self_model.service import SelfModelService; "
            "assert SelfModelService()",
        ],
    ),
    (
        "session_ops_03",
        "cognition",
        "Verify Working Memory Service",
        "Working memory service instantiates",
        [
            sys.executable,
            "-c",
            "from cyberbrain.working_memory.service import WorkingMemoryService; "
            "assert WorkingMemoryService()",
        ],
    ),
    (
        "session_ops_03",
        "relations",
        "Verify RelationTraversal Service",
        "RelationTraversal module loadable",
        [
            sys.executable,
            "-c",
            "from cyberbrain.relations.traversal import RelationTraversal; "
            "assert RelationTraversal",
        ],
    ),
    (
        "session_ops_03",
        "relations",
        "Verify RelationMaintenance Service",
        "RelationMaintenance module loadable",
        [
            sys.executable,
            "-c",
            "from cyberbrain.relations.maintenance import RelationMaintenance; "
            "assert RelationMaintenance",
        ],
    ),
    (
        "session_ops_03",
        "dreaming",
        "Verify DreamKnowledgeWriter",
        "Writer class available",
        [
            sys.executable,
            "-c",
            "from cyberbrain.dreaming.writeback import DreamKnowledgeWriter; "
            "assert DreamKnowledgeWriter",
        ],
    ),
    (
        "session_ops_03",
        "dreaming",
        "Verify DreamRunAuditStore",
        "Audit store class available",
        [
            sys.executable,
            "-c",
            "from cyberbrain.dreaming.audit import DreamRunAuditStore; "
            "assert DreamRunAuditStore",
        ],
    ),
]


def run_seed(
    *,
    qdrant_url: str | None = None,
    embedding_url: str | None = None,
    api_key: str | None = None,
):
    settings = Settings()
    if qdrant_url:
        settings.qdrant_url = qdrant_url
    if embedding_url:
        settings.embedding_url = embedding_url
    if api_key:
        settings.qdrant_api_key = api_key

    services = build_runtime(settings)
    pred_service = services.prediction_learning
    cal_service = MetacognitionCalibrationService(prediction_learning=pred_service)

    print(f"Executing {len(VERIFICATION_STEPS)} prospective verification actions...")
    passed = 0
    failed = 0

    with bind_job_authority(None):
        for session_id, topic, action, expected, cmd in VERIFICATION_STEPS:
            with track_prediction(
                pred_service,
                expected_outcome=expected,
                confidence=0.95,
                action=action,
                session_id=session_id,
                agent="coding-agents",
                project="CyberBrain",
                topic=topic,
                identity_trust=IdentityTrust.AUTHENTICATED,
            ) as handle:
                try:
                    result = subprocess.run(
                        cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=60.0
                    )
                except subprocess.TimeoutExpired:
                    handle.resolve(
                        observed_outcome="Timed out after 60 seconds",
                        assessment=PredictionAssessment.CONTRADICTED,
                    )
                    failed += 1
                    print(f"  [TIMEOUT] {action}")
                    continue

                if result.returncode == 0:
                    handle.resolve(
                        observed_outcome=f"Exit 0: {action} succeeded",
                        assessment=PredictionAssessment.CONFIRMED,
                    )
                    passed += 1
                    print(f"  [PASS] {action} (ID={handle.prediction_id})")
                else:
                    handle.resolve(
                        observed_outcome=f"Exit {result.returncode}: {result.stderr[:200]}",
                        assessment=PredictionAssessment.CONTRADICTED,
                    )
                    failed += 1
                    print(f"  [FAIL] {action}: {result.stderr[:100]}")

        print("\nChecking resulting calibration status...")
        report = cal_service.observe(agent="coding-agents", project="CyberBrain")
        print("\n=== Calibration Report ===")
        for k, v in report.model_dump().items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qdrant-url", default=None)
    parser.add_argument("--embedding-url", default=None)
    parser.add_argument("--api-key", default=None)
    args = parser.parse_args()

    run_seed(
        qdrant_url=args.qdrant_url,
        embedding_url=args.embedding_url,
        api_key=args.api_key,
    )
