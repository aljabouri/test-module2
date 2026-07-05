"""Golden Corpus regression suite (roadmap point 7).

The corpus pages are FROZEN with hand-labeled ground truth. 100% precision AND
recall required: a missed defect or a phantom detection both fail — engine or
normalizer drift is caught before it silently moves customer scores.
"""
import json
from pathlib import Path

import pytest

from konformos.registry.loader import load_catalog
from konformos.scan.normalizer import build_issue_map, normalize
from konformos.scan.static_engine import scan_html

CORPUS = Path(__file__).resolve().parents[1] / "corpus"
LABELS = json.loads((CORPUS / "labels.json").read_text(encoding="utf-8"))


def issues_for(page_name: str):
    html = (CORPUS / "pages" / page_name).read_text(encoding="utf-8")
    return scan_html(page_name, html)


def test_corpus_exact_match_no_misses_no_phantoms():
    expected = {
        (e["page"], e["issue_id"], e["selector"]) for e in LABELS["expected_issues"]
    }
    actual = set()
    for page in ("shop-home.html", "product-page.html", "clean-page.html"):
        for issue in issues_for(page):
            actual.add((issue.page, issue.issue_id, issue.selector))

    missed = expected - actual
    phantoms = actual - expected
    assert not missed, f"engine MISSED labeled defects: {sorted(missed)}"
    assert not phantoms, f"engine invented PHANTOM defects: {sorted(phantoms)}"


def test_clean_page_is_clean():
    assert issues_for("clean-page.html") == []


def test_normalized_rule_codes_match_labels():
    catalog = load_catalog()
    for page, expected_codes in LABELS["expected_rule_codes"].items():
        result = normalize(issues_for(page), catalog)
        actual_codes = sorted({f.rule_code for f in result.findings})
        assert actual_codes == expected_codes, f"{page}: {actual_codes}"
        assert result.unmapped == []  # every corpus issue must map (INV-FD-01)


def test_labels_reference_only_real_catalog_rules():
    catalog = load_catalog()
    issue_map = build_issue_map(catalog)
    for entry in LABELS["expected_issues"]:
        assert entry["issue_id"] in issue_map, f"label {entry['issue_id']} unmapped"
    for codes in LABELS["expected_rule_codes"].values():
        for code in codes:
            assert code in catalog.rules


def test_dedup_and_multi_engine_merge():
    """BR-SCAN-03/04: same defect twice (or from two engines) = one Finding."""
    from konformos.scan.static_engine import RawIssue

    catalog = load_catalog()
    twice = [
        RawIssue("internal", "image-alt", "/", "img[src='/x.jpg']", "<img>"),
        RawIssue("internal", "image-alt", "/", "img[src='/x.jpg']", "<img>"),
        RawIssue("axe-core", "image-alt", "/", "img[src='/x.jpg']", "<img>"),
    ]
    result = normalize(twice, catalog)
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.evidence["occurrences"] == 3
    assert finding.evidence["engines"] == ["internal", "axe-core"]


def test_unknown_engine_issue_queues_never_guessed():
    """INV-FD-01 / EDGE-SCAN-03."""
    from konformos.scan.static_engine import RawIssue

    catalog = load_catalog()
    result = normalize(
        [RawIssue("axe-core", "future-check-9000", "/", "div", "<div>")], catalog
    )
    assert result.findings == []
    assert len(result.unmapped) == 1
    assert result.unmapped[0].issue_id == "future-check-9000"
