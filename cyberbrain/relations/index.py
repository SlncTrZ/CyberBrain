# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from typing import Any

from cyberbrain.core.errors import ConfigurationError

from .models import EntityRef, RelationStatus, bundle_from_extensions, canonical_json

INDEX_KEY = "_relation_index"
INDEX_PREFIX = "extensions." + INDEX_KEY
INDEX_FIELDS = {
    INDEX_PREFIX + ".schema_version": "integer",
    INDEX_PREFIX + ".owner_key": "keyword",
    INDEX_PREFIX + ".target_keys": "keyword",
    "created_at": "datetime",
}


def project_relations(payload: dict[str, Any]) -> dict[str, Any]:
    """Rebuildable projection, never an independent relationship truth store."""
    bundle = bundle_from_extensions(payload.get("extensions") or {})
    try:
        owner = EntityRef.from_payload(payload)
    except (KeyError, TypeError, ValueError):
        if bundle.edges:
            raise ConfigurationError("relation owner identity is not indexable") from None
        return {"schema_version": 1, "eligible": False}
    if any(edge.source.key != owner.key for edge in bundle.edges):
        raise ConfigurationError("relation source differs from canonical Knowledge identity")
    return {
        "schema_version": 1,
        "eligible": True,
        "owner_key": owner.key,
        "target_keys": sorted(
            {edge.target.key for edge in bundle.edges if edge.status == RelationStatus.ACCEPTED}
        ),
        "bundle_digest": bundle.digest,
    }


def verify_projection(payload: dict[str, Any]) -> None:
    if canonical_json((payload.get("extensions") or {}).get(INDEX_KEY)) != canonical_json(
        project_relations(payload)
    ):
        raise ConfigurationError("relation index is missing or inconsistent; rebuild required")
