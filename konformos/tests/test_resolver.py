"""Guards §8.7 resolution + BR-LEG-04 + BR-EVAL-05 weight merging."""
from datetime import date, datetime

import pytest

from konformos.registry.resolver import (
    PackNotEffective,
    get_active_pack,
    resolve,
)
from konformos.schemas import ComplianceProfile, RulePack


def pack(jurisdiction, version, effective, refs, status="active"):
    return RulePack.model_validate(dict(
        jurisdiction=jurisdiction,
        version=version,
        effective_from=effective,
        status=status,
        legal_basis="test",
        rule_refs=refs,
        seed=True,
        seed_provenance="test fixture",
        signed_by="curator-1" if status != "draft" else None,
        signed_at=datetime(2026, 1, 1) if status != "draft" else None,
    ))


CONTRAST = {"rule_code": "wcag-2.2-1.4.3", "weight": 9, "mandatory": True}
CONTRAST_US = {"rule_code": "wcag-2.2-1.4.3", "weight": 8, "mandatory": False}
KEYBOARD = {"rule_code": "wcag-2.2-2.1.1", "weight": 10, "mandatory": True}
FOCUS_22 = {"rule_code": "wcag-2.2-2.4.11", "weight": 6, "mandatory": True}

DE_1 = pack("DE", "DE-2026.1", date(2025, 6, 28), [CONTRAST, KEYBOARD])
DE_2 = pack("DE", "DE-2026.2", date(2026, 6, 28), [CONTRAST, KEYBOARD, FOCUS_22])
US_1 = pack("US", "US-2026.1", date(2026, 4, 24), [CONTRAST_US])
PACKS = [DE_1, DE_2, US_1]


def profile(jurisdictions, binding="latest", pinned=None, mode="strictest"):
    return ComplianceProfile(
        property_id="p1",
        selected_jurisdictions=jurisdictions,
        pack_binding=binding,
        pinned_versions=pinned,
        combination_mode=mode,
    )


def test_latest_respects_effective_from():
    # BR-LEG-04: before DE-2026.2's effective date, DE-2026.1 wins despite both active
    assert get_active_pack(PACKS, "DE", date(2026, 1, 1)).version == "DE-2026.1"
    assert get_active_pack(PACKS, "DE", date(2026, 7, 1)).version == "DE-2026.2"


def test_pinned_resolution():
    rs = resolve(profile(["DE"], "pinned", {"DE": "DE-2026.1"}), date(2026, 7, 1), PACKS)
    assert rs.pack_versions == {"DE": "DE-2026.1"}
    assert "wcag-2.2-2.4.11" not in rs.rules  # pinned pack predates WCAG 2.2 upgrade


def test_pinned_future_pack_rejected():
    with pytest.raises(PackNotEffective):
        resolve(profile(["DE"], "pinned", {"DE": "DE-2026.2"}), date(2026, 1, 1), PACKS)


def test_multi_jurisdiction_merge_strictest_and_union():
    rs = resolve(profile(["DE", "US"]), date(2026, 7, 1), PACKS)
    contrast = rs.rules["wcag-2.2-1.4.3"]
    # one canonical node, two weights (v1.0 §8.5 — never counted twice)
    assert contrast.weights == {"DE": 9, "US": 8}
    assert contrast.combined_weight("strictest") == 9
    assert contrast.combined_weight("union") == 17
    # BR-EVAL-05: mandatory merges with OR
    assert contrast.combined_mandatory is True
    # EDGE-LEG-02: WCAG-2.2-only rule applies to DE alone, no implicit upgrade for US
    focus = rs.rules["wcag-2.2-2.4.11"]
    assert focus.weights == {"DE": 6}
    assert "wcag-2.2-2.4.11" not in rs.jurisdiction_rules("US")


def test_per_jurisdiction_matrix():
    rs = resolve(profile(["DE", "US"]), date(2026, 7, 1), PACKS)
    assert rs.jurisdiction_rules("US") == {"wcag-2.2-1.4.3": 8}
