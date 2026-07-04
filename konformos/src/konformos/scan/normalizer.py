"""The Normalizer — the heart of the Multi-Input Scan Engine (Tech Spec v1.0
§4.4.3): every engine issue becomes one unified Finding via the catalog-derived
mapping table. Engine 5 never learns where a Finding came from.

- Mapping table derives from Rule.test_logic (rule_id + additional_rule_ids),
  so extending detection = extending the catalog, not this code.
- INV-FD-01: unmapped issues are never dropped or guessed — they queue for
  review (EDGE-SCAN-03).
- BR-SCAN-03: dedup on (rule_code, selector, page) with an occurrence counter.
- BR-SCAN-04: the same defect from two engines merges into one Finding that
  records both engines.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from konformos.evaluation.scoring import FindingInput
from konformos.registry.loader import Catalog
from konformos.scan.static_engine import RawIssue
from konformos.schemas.rule import AutomatedTestLogic

# Severity per engine issue id, aligned with axe-core impact levels.
SEVERITY_BY_ISSUE: dict[str, str] = {
    "image-alt": "critical",
    "label": "critical",
    "meta-viewport": "critical",
    "html-has-lang": "serious",
    "document-title": "serious",
    "link-name": "serious",
    "tabindex": "serious",
    "marquee": "serious",
    "color-contrast": "serious",
    "video-caption": "critical",
}
DEFAULT_SEVERITY = "moderate"


def build_issue_map(catalog: Catalog) -> dict[str, str]:
    """engine issue_id → rule_code, derived from the catalog itself."""
    mapping: dict[str, str] = {}
    for rule in catalog.rules.values():
        logic = rule.test_logic
        if isinstance(logic, AutomatedTestLogic):
            for issue_id in [logic.rule_id, *logic.additional_rule_ids]:
                mapping.setdefault(issue_id, rule.code)
    return mapping


@dataclass
class NormalizedFinding:
    rule_code: str
    severity: str
    page: str
    location: dict
    evidence: dict
    status: str = "open"

    def to_finding_input(self) -> FindingInput:
        return FindingInput(
            rule_code=self.rule_code,
            severity=self.severity,  # type: ignore[arg-type]
            status=self.status,  # type: ignore[arg-type]
            page=self.page,
        )


@dataclass
class UnmappedIssue:
    engine: str
    issue_id: str
    sample_selector: str
    occurrence_count: int = 1


@dataclass
class NormalizationResult:
    findings: list[NormalizedFinding] = field(default_factory=list)
    unmapped: list[UnmappedIssue] = field(default_factory=list)


def normalize(raw_issues: list[RawIssue], catalog: Catalog) -> NormalizationResult:
    issue_map = build_issue_map(catalog)
    findings: dict[tuple[str, str, str], NormalizedFinding] = {}
    unmapped: dict[tuple[str, str], UnmappedIssue] = {}

    for issue in raw_issues:
        rule_code = issue_map.get(issue.issue_id)
        if rule_code is None:
            key = (issue.engine, issue.issue_id)
            if key in unmapped:
                unmapped[key].occurrence_count += 1
            else:
                unmapped[key] = UnmappedIssue(
                    engine=issue.engine,
                    issue_id=issue.issue_id,
                    sample_selector=issue.selector,
                )
            continue

        dedup_key = (rule_code, issue.selector, issue.page)  # BR-SCAN-03
        if dedup_key in findings:
            finding = findings[dedup_key]
            finding.evidence["occurrences"] += 1
            if issue.engine not in finding.evidence["engines"]:  # BR-SCAN-04
                finding.evidence["engines"].append(issue.engine)
        else:
            findings[dedup_key] = NormalizedFinding(
                rule_code=rule_code,
                severity=SEVERITY_BY_ISSUE.get(issue.issue_id, DEFAULT_SEVERITY),
                page=issue.page,
                location={"selector": issue.selector},
                evidence={
                    "engines": [issue.engine],
                    "engine_issue_id": issue.issue_id,
                    "snippet": issue.evidence,
                    "occurrences": 1,
                },
            )

    return NormalizationResult(
        findings=list(findings.values()),
        unmapped=list(unmapped.values()),
    )
