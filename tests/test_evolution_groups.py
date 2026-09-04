# SPDX-License-Identifier: MPL-2.0

from cyberbrain.dreaming.evolution_groups import (
    NormalizedEvidence,
    build_evolution_bundle,
)


def test_groups_version_chain_and_flags_multiple_active() -> None:
    records = [
        NormalizedEvidence(
            id="v2",
            content="Second version validated.",
            domain="code",
            topic="x",
            entity_type="config",
            entity_name="Thing",
            version=2,
            status="active",
        ),
        NormalizedEvidence(
            id="v1",
            content="First version.",
            domain="code",
            topic="x",
            entity_type="config",
            entity_name="Thing",
            version=1,
            status="active",
        ),
    ]

    bundle = build_evolution_bundle(records)
    group = bundle.groups[0]

    assert [item.id for item in group.chain] == ["v1", "v2"]
    assert "multiple_active_versions" in group.anomalies


def test_related_replacement_is_hint_not_chain_member() -> None:
    records = [
        NormalizedEvidence(
            id="v1",
            content="Current config.",
            domain="code",
            topic="x",
            entity_type="config",
            entity_name="Thing",
            version=1,
            status="active",
        ),
        NormalizedEvidence(
            id="event",
            content="Old dependency was removed and replaced by internal stack.",
            domain="code",
            topic="x",
            entity_type="concept",
            entity_name="OtherThing",
            version=1,
            status="active",
        ),
    ]

    bundle = build_evolution_bundle(records)
    thing = next(group for group in bundle.groups if group.identity["entity_name"] == "Thing")

    assert [item.id for item in thing.chain] == ["v1"]
    assert any(
        item.id == "event" and item.relation_hint == "replacement_or_removal"
        for item in thing.related_events
    )
