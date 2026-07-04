"""Guards the anonymized moat (INV-KG-01/02, BR-KG-01/02, BR-FP-01/03)."""
import pytest

from konformos.moat.knowledge import (
    ConsentRequired,
    KnowledgeEntry,
    KnowledgeStore,
    MoatContaminationError,
    sanitize_for_moat,
    stack_signature,
)


def entry(**overrides):
    base = dict(
        stack_signature="shopware:vision:3",
        rule_code="wcag-2.2-1.1.1",
        pattern={"where": "product gallery images", "selector_shape": "img.gallery-item"},
        known_fix={"type": "code_patch", "hint": "add alt from product title variable"},
        occurrence_count=1,
    )
    base.update(overrides)
    return KnowledgeEntry.model_validate(base)


def test_signature_uses_major_version_only():
    # BR-KG-01
    assert stack_signature("Shopware", "Vision", "3.4.1") == "shopware:vision:3"
    assert stack_signature("woocommerce", "Store Front", None) == "woocommerce:store-front:0"


@pytest.mark.parametrize("poison", [
    {"where": "seen on https://kunde-shop.de/product"},
    {"contact": "owner@kunde-shop.de"},
    {"ref": "property 3f2504e0-4f89-41d3-9a0c-0305e82c3301"},
    {"note": "customer domain kunde-shop.de shows this"},
    {"url": "anything"},          # identity key
    {"organization_id": "x"},     # identity key
])
def test_sanitizer_rejects_identity(poison):
    # INV-KG-01: URLs, emails, UUIDs, domains, identity keys — all rejected
    with pytest.raises(MoatContaminationError):
        sanitize_for_moat(poison)


def test_sanitizer_accepts_clean_technical_pattern():
    sanitize_for_moat({"selector_shape": "img.gallery-item", "depth": 3, "note": None})


def test_write_gate_requires_consent():
    # INV-KG-02: checked at write time
    store = KnowledgeStore()
    with pytest.raises(ConsentRequired):
        store.contribute(entry(), data_sharing_consent=False)


def test_write_gate_sanitizes_payloads():
    store = KnowledgeStore()
    poisoned = entry(pattern={"where": "https://kunde-shop.de"})
    with pytest.raises(MoatContaminationError):
        store.contribute(poisoned, data_sharing_consent=True)


def test_upsert_merges_not_duplicates():
    # BR-KG-02
    store = KnowledgeStore()
    store.contribute(entry(), data_sharing_consent=True)
    store.contribute(entry(occurrence_count=4, validated_by_expert=True),
                     data_sharing_consent=True)
    report = store.predict("shopware", "vision", "3.2", 0.95)
    assert report.known_issue_count == 1
    assert report.known_issues[0]["seen_in_stores"] == 5
    assert report.known_issues[0]["validated_by_expert"] is True


def test_low_confidence_gives_no_enrichment():
    # BR-FP-03: below 0.7 → hedged, zero pre-scan claims
    store = KnowledgeStore()
    store.contribute(entry(), data_sharing_consent=True)
    report = store.predict("shopware", "vision", "3.2", 0.5)
    assert report.hedged is True
    assert report.known_issues == []


def test_prediction_matches_major_version_across_minors():
    store = KnowledgeStore()
    store.contribute(entry(), data_sharing_consent=True)  # learned on 3.x
    report = store.predict("shopware", "vision", "3.9.7", 0.9)
    assert report.known_issue_count == 1
