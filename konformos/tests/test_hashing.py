"""Guards INV-TL-02/03/04 (Engineering Rules v1.1 §1.1)."""
import pytest

from konformos.core.hashing import (
    GENESIS,
    ChainBroken,
    SealedEvent,
    canonical_hash,
    canonical_json,
    seal_event,
    verify_chain,
)


def test_canonical_json_is_key_order_independent():
    a = {"b": 1, "a": {"y": None, "x": [1, 2]}}
    b = {"a": {"x": [1, 2], "y": None}, "b": 1}
    assert canonical_json(a) == canonical_json(b)
    assert canonical_hash(a) == canonical_hash(b)


def test_canonical_json_exact_form():
    # INV-TL-02: sorted keys, no whitespace, nulls written, UTF-8 preserved
    assert canonical_json({"b": None, "a": "نص"}) == '{"a":"نص","b":null}'


def test_first_event_links_to_genesis():
    event = seal_event("scan_completed", {"scan": "s1"}, prev=None)
    assert event.sequence_number == 1
    assert event.prev_hash == GENESIS


def test_chain_verifies_and_detects_tampering():
    e1 = seal_event("scan_completed", {"scan": "s1"}, None)
    e2 = seal_event("fix_applied", {"fix": "f1"}, e1)
    e3 = seal_event("readiness_changed", {"from": 61, "to": 78}, e2)
    verify_chain([e1, e2, e3])

    tampered = SealedEvent(
        sequence_number=e2.sequence_number,
        event_type=e2.event_type,
        payload={"fix": "f1-FORGED"},
        content_hash=e2.content_hash,
        prev_hash=e2.prev_hash,
    )
    with pytest.raises(ChainBroken) as exc:
        verify_chain([e1, tampered, e3])
    assert exc.value.sequence_number == 2


def test_chain_detects_sequence_gap():
    e1 = seal_event("scan_completed", {"scan": "s1"}, None)
    e2 = seal_event("fix_applied", {"fix": "f1"}, e1)
    e3 = seal_event("fix_applied", {"fix": "f2"}, e2)
    with pytest.raises(ChainBroken):
        verify_chain([e1, e3])  # missing #2 (INV-TL-04)


def test_chain_detects_relinking():
    """Rewriting history consistently still breaks at the splice point."""
    e1 = seal_event("scan_completed", {"scan": "s1"}, None)
    e2 = seal_event("fix_applied", {"fix": "f1"}, e1)
    forged_e1 = seal_event("scan_completed", {"scan": "FORGED"}, None)
    with pytest.raises(ChainBroken):
        verify_chain([forged_e1, e2])
