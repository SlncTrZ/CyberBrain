# SPDX-License-Identifier: MPL-2.0

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from cyberbrain.relations import EntityRef, RelationBundle
from tests.relations.test_persistence import raw, setup


def test_fingerprint_is_independent_of_record_version_and_context_key_order():
    state = setup()
    payload = state.target.model_dump(mode="json")
    first = EntityRef.from_payload({**payload, "context": {"b": [1, 2], "a": {"z": "x"}}})
    second = EntityRef.from_payload(
        {
            **payload,
            "id": str(UUID(int=999)),
            "version": 100,
            "context": {"a": {"z": "x"}, "b": [1, 2]},
        }
    )
    assert first.key == second.key
    other_scope = first.model_dump()
    other_scope["scope"]["tenant"] = "other"
    assert EntityRef.model_validate(other_scope).key != first.key


@pytest.mark.parametrize("schema", [True, 0, 2, "1", 1.0, None])
def test_unknown_or_coerced_schema_is_rejected(schema):
    with pytest.raises(ValidationError):
        RelationBundle.model_validate({"schema_version": schema, "edges": []})


def test_explicit_schema_is_required():
    with pytest.raises(ValidationError):
        RelationBundle.model_validate({"edges": []})


@pytest.mark.parametrize(
    "changes",
    [
        {"kind": "inferred_neighbor"},
        {"kind": "supersedes"},
        {"relation_id": "forged"},
        {"evidence": []},
        {"valid_from": "2026-10-01T00:00:00"},
        {"valid_until": "2026-09-30T00:00:00Z"},
        {"status": "accepted"},
        {"status": "rejected", "review_note": "   "},
        {"unknown": "extension bypass"},
    ],
)
def test_invalid_assertions_fail_closed(changes):
    state = setup()
    with pytest.raises(ValidationError):
        RelationBundle.model_validate(raw(state.edge, **changes))


def test_self_link_and_duplicate_identity_are_rejected():
    state = setup()
    invalid = raw(state.edge)
    invalid["edges"][0]["target"] = invalid["edges"][0]["source"]
    invalid["edges"][0]["relation_id"] = None
    with pytest.raises(ValidationError):
        RelationBundle.model_validate(invalid)
    invalid = raw(state.edge)
    invalid["edges"].append(invalid["edges"][0])
    with pytest.raises(ValidationError):
        RelationBundle.model_validate(invalid)


def test_provenance_order_and_timezone_do_not_change_bundle_digest():
    state = setup()
    one = raw(state.edge)
    one["edges"][0]["evidence"].append(one["edges"][0]["evidence"][0])
    one["edges"][0]["valid_from"] = "2026-10-01T07:00:00+07:00"
    assert (
        RelationBundle.model_validate(one).digest
        == RelationBundle.model_validate(raw(state.edge)).digest
    )


def test_direction_changes_dependency_id_but_not_symmetric_contradiction_id():
    state = setup()
    forward = raw(state.edge)
    backward = raw(state.edge)
    backward["edges"][0]["source"], backward["edges"][0]["target"] = (
        backward["edges"][0]["target"],
        backward["edges"][0]["source"],
    )
    backward["edges"][0]["relation_id"] = None
    assert RelationBundle.model_validate(forward).edges[0].relation_id != (
        RelationBundle.model_validate(backward).edges[0].relation_id
    )
    forward["edges"][0].update(kind="contradicts", relation_id=None)
    backward["edges"][0].update(kind="contradicts", relation_id=None)
    assert RelationBundle.model_validate(forward).edges[0].relation_id == (
        RelationBundle.model_validate(backward).edges[0].relation_id
    )


def test_nested_model_copy_cannot_bypass_revalidation():
    state = setup()
    forged = state.edge.model_copy(update={"kind": "unsupported"})
    with pytest.raises(ValidationError):
        RelationBundle.model_validate({"schema_version": 1, "edges": [forged]})


@pytest.mark.parametrize("context", [{"number": float("nan")}, {"number": float("inf")}])
def test_nonfinite_context_is_not_a_stable_identity(context):
    state = setup()
    with pytest.raises(ValidationError):
        EntityRef.model_validate({**state.edge.source.model_dump(), "context": context})


def test_untrimmed_labels_cannot_alias_existing_canonical_identity():
    state = setup()
    with pytest.raises(ValidationError):
        EntityRef.model_validate({**state.edge.source.model_dump(), "entity_name": " api "})


def test_bundle_bounds_are_enforced_before_admission_reads():
    state = setup()
    invalid = raw(state.edge)
    invalid["edges"] *= 65
    with pytest.raises(ValidationError):
        RelationBundle.model_validate(invalid)


def test_causal_assertion_remains_proposed_without_explicit_review():
    state = setup()
    bundle = RelationBundle.model_validate(raw(state.edge, kind="causes", relation_id=None))
    assert bundle.edges[0].status.value == "proposed"
    assert bundle.edges[0].valid_from == datetime(2026, 10, 1, tzinfo=UTC)
