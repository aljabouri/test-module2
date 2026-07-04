"""Guards dossier sealing + public verification (INV-DS-01/02/03, EDGE-TL-01)."""
import pytest

from konformos.core.hashing import ChainBroken, SealedEvent, seal_event
from konformos.dossier.sealing import build_dossier, verify_dossier


def make_events():
    e1 = seal_event("scan_completed", {"pages_scanned": 3, "findings": 9}, None)
    e2 = seal_event("readiness_changed", {"scores": {"DE": 61}}, e1)
    return [e1, e2]


def make_dossier(events=None):
    return build_dossier(
        jurisdictions=["DE"],
        pack_versions={"DE": "DE-2026.1"},
        readiness={"DE": 61},
        generated_at="2026-07-04T12:00:00+00:00",
        events=events or make_events(),
        scoring_version="1.0",
        engine_versions={"internal": "internal-0.1"},
    )


def test_seal_roundtrip():
    dossier = make_dossier()
    assert verify_dossier(dossier.content, dossier.dossier_hash)


def test_any_tampering_breaks_the_seal():
    dossier = make_dossier()
    tampered = dict(dossier.content)
    tampered["readiness"] = {"DE": 95}  # forge a better score
    assert not verify_dossier(tampered, dossier.dossier_hash)


def test_pack_versions_inside_sealed_content():
    # INV-DS-02: the legal anchor lives inside the sealed content itself
    dossier = make_dossier()
    assert dossier.content["pack_versions"] == {"DE": "DE-2026.1"}


def test_no_certification_wording():
    # INV-DS-03 forbidden-vocabulary guard
    dossier = make_dossier()
    text = str(dossier.content).lower()
    for forbidden in ("certif", "guarantee", "zertifiziert", "garantiert"):
        assert forbidden not in text


def test_broken_chain_blocks_dossier():
    # EDGE-TL-01 / NFR-REL-02: never seal broken evidence
    e1, e2 = make_events()
    forged = SealedEvent(
        sequence_number=e2.sequence_number,
        event_type=e2.event_type,
        payload={"scores": {"DE": 99}},
        content_hash=e2.content_hash,
        prev_hash=e2.prev_hash,
    )
    with pytest.raises(ChainBroken):
        make_dossier(events=[e1, forged])


def test_content_is_public_by_construction():
    """No identity fields may exist in the public record."""
    dossier = make_dossier()
    for key in ("organization", "property", "url", "email", "label"):
        assert key not in dossier.content
