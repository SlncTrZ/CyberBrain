# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from unittest.mock import MagicMock

from scripts.cutover_v2_to_canonical import cutover_collections


def test_cutover_dry_run():
    mock_repo = MagicMock()
    mock_repo.collection_info.side_effect = lambda name: {
        "points_count": 5000 if "knowledge" in name else 7000,
        "status": "green",
    }

    import scripts.cutover_v2_to_canonical
    orig_repo = scripts.cutover_v2_to_canonical.QdrantRepository
    orig_client = scripts.cutover_v2_to_canonical.QdrantSnapshotClient
    scripts.cutover_v2_to_canonical.QdrantRepository = MagicMock(return_value=mock_repo)
    scripts.cutover_v2_to_canonical.QdrantSnapshotClient = MagicMock()
    try:
        result = cutover_collections(
            qdrant_url="http://fake:6333",
            dry_run=True,
        )
        assert result["status"] == "DRY_RUN_PASS"
        assert result["source_knowledge"]["cyberbrain_knowledge_v2_stage"] == 5000
        assert result["source_episodic"]["cyberbrain_episodic_v2_stage"] == 7000
    finally:
        scripts.cutover_v2_to_canonical.QdrantRepository = orig_repo
        scripts.cutover_v2_to_canonical.QdrantSnapshotClient = orig_client
