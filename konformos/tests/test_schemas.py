"""Guards VAL-RULE-01, VAL-PACK-01, VAL-ID-02, VAL-PROF-01, INV-RP-03, BR-LEG-03."""
from datetime import date, datetime

import pytest
from pydantic import ValidationError

from konformos.schemas import ComplianceProfile, Rule, RulePack


def make_rule(**overrides):
    base = dict(
        code="wcag-2.2-1.4.3",
        title="Contrast (Minimum)",
        description="desc",
        source_standard="WCAG 2.2",
        wcag_level="AA",
        automatable=True,
        test_logic={"engine": "axe-core", "rule_id": "color-contrast", "manual_fallback": False},
    )
    base.update(overrides)
    return Rule.model_validate(base)


def make_pack(**overrides):
    base = dict(
        jurisdiction="DE",
        version="DE-2026.1",
        effective_from=date(2025, 6, 28),
        status="draft",
        legal_basis="BFSG",
        rule_refs=[{"rule_code": "wcag-2.2-1.4.3", "weight": 9, "mandatory": True}],
    )
    base.update(overrides)
    return RulePack.model_validate(base)


def test_rule_no_middle_state():
    with pytest.raises(ValidationError, match="VAL-RULE-01"):
        make_rule(automatable=False)  # automatable=false with automated logic
    with pytest.raises(ValidationError, match="VAL-RULE-01"):
        make_rule(test_logic={"manual_only": True, "expert_guidance": "check"})
    make_rule(automatable=False, test_logic={"manual_only": True, "expert_guidance": "check"})


def test_rule_code_pattern():
    with pytest.raises(ValidationError):
        make_rule(code="WCAG_1.4.3")


def test_pack_version_prefix_must_match_jurisdiction():
    with pytest.raises(ValidationError, match="VAL-ID-02"):
        make_pack(version="US-2026.1")


def test_pack_rejects_duplicate_rule_refs():
    with pytest.raises(ValidationError, match="VAL-PACK-01"):
        make_pack(rule_refs=[
            {"rule_code": "wcag-2.2-1.4.3", "weight": 9, "mandatory": True},
            {"rule_code": "wcag-2.2-1.4.3", "weight": 5, "mandatory": True},
        ])


def test_pack_weight_bounds():
    with pytest.raises(ValidationError):
        make_pack(rule_refs=[{"rule_code": "wcag-2.2-1.4.3", "weight": 11, "mandatory": True}])


def test_published_pack_requires_signature():
    with pytest.raises(ValidationError, match="INV-RP-03"):
        make_pack(status="active", seed=True, seed_provenance="seed docs")
    make_pack(
        status="active", seed=True, seed_provenance="seed docs",
        signed_by="curator-1", signed_at=datetime(2026, 6, 1),
    )


def test_published_nonseed_pack_requires_change_events():
    with pytest.raises(ValidationError, match="BR-LEG-03"):
        make_pack(status="active", signed_by="curator-1", signed_at=datetime(2026, 6, 1))
    make_pack(
        status="active", signed_by="curator-1", signed_at=datetime(2026, 6, 1),
        source_change_events=["evt-1"],
    )


def test_profile_pinned_requires_all_versions():
    with pytest.raises(ValidationError, match="VAL-PROF-01"):
        ComplianceProfile(
            property_id="p1",
            selected_jurisdictions=["DE", "US"],
            pack_binding="pinned",
            pinned_versions={"DE": "DE-2026.1"},
            combination_mode="strictest",
        )


def test_profile_latest_forbids_pinned_versions():
    with pytest.raises(ValidationError, match="VAL-PROF-01"):
        ComplianceProfile(
            property_id="p1",
            selected_jurisdictions=["DE"],
            pack_binding="latest",
            pinned_versions={"DE": "DE-2026.1"},
            combination_mode="union",
        )
