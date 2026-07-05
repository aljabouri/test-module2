"""Table-driven guards for the reference readiness formula (BR-EVAL-01..07)."""
from datetime import date, datetime

import pytest

from konformos.evaluation.scoring import (
    FindingInput,
    NoPagesScanned,
    compute_readiness,
    page_spread,
)
from konformos.registry.resolver import resolve
from konformos.schemas import ComplianceProfile, Rule, RulePack


def rule(code, automatable=True):
    if automatable:
        tl = {"engine": "axe-core", "rule_id": "x", "manual_fallback": False}
    else:
        tl = {"manual_only": True, "expert_guidance": "check manually"}
    return Rule.model_validate(dict(
        code=code, title=code, description="d", source_standard="WCAG 2.2",
        wcag_level="AA", automatable=automatable, test_logic=tl,
    ))


RULES = {
    "wcag-2.2-1.4.3": rule("wcag-2.2-1.4.3"),            # weight 10
    "wcag-2.2-2.4.2": rule("wcag-2.2-2.4.2"),            # weight 5
    "wcag-2.2-2.4.7": rule("wcag-2.2-2.4.7", False),     # manual
}

PACK = RulePack.model_validate(dict(
    jurisdiction="DE", version="DE-2026.1", effective_from=date(2025, 6, 28),
    status="active", legal_basis="test", seed=True, seed_provenance="fixture",
    signed_by="c", signed_at=datetime(2026, 1, 1),
    rule_refs=[
        {"rule_code": "wcag-2.2-1.4.3", "weight": 10, "mandatory": True},
        {"rule_code": "wcag-2.2-2.4.2", "weight": 5, "mandatory": True},
        {"rule_code": "wcag-2.2-2.4.7", "weight": 8, "mandatory": True},
    ],
))

PROFILE = ComplianceProfile(
    property_id="p1", selected_jurisdictions=["DE"],
    pack_binding="latest", combination_mode="strictest",
)


def score(findings, pages=10):
    ruleset = resolve(PROFILE, date(2026, 1, 1), [PACK])
    return compute_readiness(ruleset, RULES, findings, pages)["DE"]


def test_clean_scan_scores_100_with_manual_coverage_disclosed():
    result = score([])
    assert result.score == 100
    # BR-EVAL-04: manual rule excluded from automated score but disclosed
    assert result.rules_evaluated == 2
    assert result.rules_manual_pending == 1
    assert result.computed_against_pack == "DE-2026.1"  # INV-RD-01


def test_exact_formula_single_finding():
    # critical contrast finding on 1 page of 10:
    # penalty = 10 * 1.0 * min(1, 0.6 + 0.4*(1/10)) = 6.4 ; max_raw = 15
    # score = round(100 * (1 - 6.4/15)) = round(57.33) = 57
    result = score([FindingInput("wcag-2.2-1.4.3", "critical", "open", "/")])
    assert result.score == 57
    assert result.gaps[0].penalty == 6.4


def test_severity_max_not_sum_per_rule():
    # BR-EVAL-02: max severity among findings of a rule, not sum
    findings = [
        FindingInput("wcag-2.2-1.4.3", "minor", "open", "/"),
        FindingInput("wcag-2.2-1.4.3", "critical", "open", "/"),
    ]
    assert score(findings).score == 57  # same as single critical on same page


def test_page_spread_full_site_worse_than_one_page():
    one = score([FindingInput("wcag-2.2-1.4.3", "critical", "open", "/")])
    everywhere = score([
        FindingInput("wcag-2.2-1.4.3", "critical", "open", f"/p{i}") for i in range(10)
    ])
    assert everywhere.score < one.score
    # spread caps at 1.0: penalty = 10 → score = round(100*(1-10/15)) = 33
    assert everywhere.score == 33
    assert page_spread(10, 10) == 1.0


def test_wont_fix_excluded_from_score_but_disclosed():
    # BR-EVAL-03 / SM-FND-01
    result = score([FindingInput("wcag-2.2-1.4.3", "critical", "wont_fix", "/")])
    assert result.score == 100
    assert result.wont_fix == ["wcag-2.2-1.4.3"]


def test_false_positive_and_fixed_fully_excluded():
    result = score([
        FindingInput("wcag-2.2-1.4.3", "critical", "false_positive", "/"),
        FindingInput("wcag-2.2-2.4.2", "serious", "fixed", "/"),
    ])
    assert result.score == 100
    assert result.wont_fix == []


def test_gaps_sorted_by_penalty_desc():
    result = score([
        FindingInput("wcag-2.2-2.4.2", "critical", "open", "/"),
        FindingInput("wcag-2.2-1.4.3", "critical", "open", "/"),
    ])
    assert [g.rule_code for g in result.gaps] == ["wcag-2.2-1.4.3", "wcag-2.2-2.4.2"]


def test_zero_pages_refused():
    with pytest.raises(NoPagesScanned):
        score([], pages=0)  # BR-EVAL-07
