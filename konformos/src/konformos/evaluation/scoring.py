"""Readiness scoring — the reference formula from Engineering Rules v1.1
BR-EVAL-01..07, implemented verbatim.

score = round(100 × (1 − raw / max_raw)) over the automatable subset of the
resolved rule set; manual rules are reported as coverage, never silently
counted as passing (BR-EVAL-04).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from konformos.registry.resolver import ResolvedRuleSet
from konformos.schemas import Rule
from konformos.schemas.pack import Jurisdiction

# BR-EVAL-01: severity multipliers are a versioned constant of the algorithm.
SEVERITY_FACTOR: dict[str, float] = {
    "critical": 1.0,
    "serious": 0.7,
    "moderate": 0.4,
    "minor": 0.15,
}
SCORING_VERSION = "1.0"

FindingStatus = Literal["open", "fixed", "wont_fix", "false_positive"]


@dataclass(frozen=True)
class FindingInput:
    """The slice of a Finding the evaluator needs (System 5 never knows the
    finding's source — Tech Spec v1.0 §4.4.3)."""

    rule_code: str
    severity: Literal["critical", "serious", "moderate", "minor"]
    status: FindingStatus
    page: str


@dataclass
class Gap:
    rule_code: str
    pack_version: str
    weight: int
    penalty: float
    pages_affected: int
    mandatory: bool


@dataclass
class ReadinessResult:
    jurisdiction: Jurisdiction | Literal["combined"]
    score: int
    computed_against_pack: str  # INV-RD-01: never floating
    gaps: list[Gap]
    rules_evaluated: int
    rules_manual_pending: int  # BR-EVAL-04: shown, never hidden
    scoring_version: str = SCORING_VERSION
    wont_fix: list[str] = field(default_factory=list)  # BR-EVAL-03: excluded but disclosed


class NoPagesScanned(Exception):
    """BR-EVAL-07: a score from no data is worse than no score."""


def page_spread(pages_affected: int, pages_scanned: int) -> float:
    """BR-EVAL-02: a defect on every page is worse than on one page, but a
    single defect is not multiplied linearly by its repetition count."""
    return min(1.0, 0.6 + 0.4 * (pages_affected / pages_scanned))


def _score(
    label: Jurisdiction | Literal["combined"],
    weights: dict[str, int],
    mandatory: dict[str, bool],
    pack_label: str,
    rules_by_code: dict[str, Rule],
    findings: list[FindingInput],
    pages_scanned: int,
) -> ReadinessResult:
    if pages_scanned <= 0:
        raise NoPagesScanned("BR-EVAL-07: no successfully scanned pages")

    open_findings: dict[str, list[FindingInput]] = {}
    wont_fix: set[str] = set()
    for finding in findings:
        if finding.status == "open":
            open_findings.setdefault(finding.rule_code, []).append(finding)
        elif finding.status == "wont_fix":
            wont_fix.add(finding.rule_code)

    evaluable = {
        code: weight
        for code, weight in weights.items()
        if rules_by_code[code].automatable
    }
    manual_pending = len(weights) - len(evaluable)

    max_raw = float(sum(evaluable.values()))
    raw = 0.0
    gaps: list[Gap] = []
    for code, weight in evaluable.items():
        rule_findings = open_findings.get(code, [])
        if not rule_findings:
            continue  # BR-EVAL-03: no open finding → zero penalty
        severity = max(SEVERITY_FACTOR[f.severity] for f in rule_findings)
        pages_affected = len({f.page for f in rule_findings})
        penalty = weight * severity * page_spread(pages_affected, pages_scanned)
        raw += penalty
        gaps.append(
            Gap(
                rule_code=code,
                pack_version=pack_label,
                weight=weight,
                penalty=round(penalty, 4),
                pages_affected=pages_affected,
                mandatory=mandatory[code],
            )
        )

    score = round(100 * (1 - raw / max_raw)) if max_raw else 100
    gaps.sort(key=lambda g: g.penalty, reverse=True)  # BR-EVAL-06
    return ReadinessResult(
        jurisdiction=label,
        score=score,
        computed_against_pack=pack_label,
        gaps=gaps,
        rules_evaluated=len(evaluable),
        rules_manual_pending=manual_pending,
        wont_fix=sorted(wont_fix & set(weights)),
    )


def compute_readiness(
    ruleset: ResolvedRuleSet,
    rules_by_code: dict[str, Rule],
    findings: list[FindingInput],
    pages_scanned: int,
) -> dict[str, ReadinessResult]:
    """Per-jurisdiction scores (each jurisdiction's own weights only —
    BR-EVAL-05) plus a 'combined' score when more than one jurisdiction."""
    results: dict[str, ReadinessResult] = {}

    for jurisdiction, pack_version in ruleset.pack_versions.items():
        weights = ruleset.jurisdiction_rules(jurisdiction)
        mandatory = {
            code: ruleset.rules[code].mandatory[jurisdiction] for code in weights
        }
        results[jurisdiction] = _score(
            jurisdiction, weights, mandatory, pack_version,
            rules_by_code, findings, pages_scanned,
        )

    if len(ruleset.pack_versions) > 1:
        combined_weights = {
            code: rule.combined_weight(ruleset.combination_mode)
            for code, rule in ruleset.rules.items()
        }
        combined_mandatory = {
            code: rule.combined_mandatory for code, rule in ruleset.rules.items()
        }
        pack_label = "+".join(sorted(ruleset.pack_versions.values()))
        results["combined"] = _score(
            "combined", combined_weights, combined_mandatory, pack_label,
            rules_by_code, findings, pages_scanned,
        )

    return results
