"""axe-core (second engine) measured on the SAME Golden Corpus.

The internal-engine labels stay the hand-authored ground truth; axe results
are pinned as a drift snapshot: core defects must be found, everything must
map through the shared Normalizer, and the clean page must stay clean.
Skips when Chromium/Playwright cannot run."""
import json
from pathlib import Path

import pytest

from konformos.registry.loader import load_catalog
from konformos.scan.normalizer import normalize

CORPUS_PAGES = Path(__file__).resolve().parents[1] / "corpus" / "pages"


@pytest.fixture(scope="module")
def axe_issues():
    try:
        from konformos.scan.axe_engine import AxeEngine, AxeUnavailable
    except ImportError:
        pytest.skip("playwright not installed")
    try:
        engine = AxeEngine()
        pages = [
            (name, (CORPUS_PAGES / name).read_text(encoding="utf-8"))
            for name in ("shop-home.html", "product-page.html", "clean-page.html")
        ]
        return engine.scan_pages(pages)
    except AxeUnavailable as exc:
        pytest.skip(str(exc))


def by_page(issues, page):
    return {i.issue_id for i in issues if i.page == page}


def test_axe_finds_the_core_labeled_defects(axe_issues):
    shop_home = by_page(axe_issues, "shop-home.html")
    # the corpus ground-truth defects axe MUST also see.
    # Known divergence (documented): axe accepts a placeholder as accessible
    # name, so it does NOT flag the newsletter input — our internal engine is
    # deliberately stricter (placeholder is not a label).
    assert {"html-has-lang", "image-alt", "link-name", "meta-viewport"} <= shop_home
    product = by_page(axe_issues, "product-page.html")
    # axe reports unlabeled <select> as its own id (select-name) — same
    # rule_code (wcag-2.2-3.3.2) after normalization.
    assert {"document-title", "image-alt", "link-name", "select-name"} <= product


def test_clean_page_is_clean_for_axe_too(axe_issues):
    assert by_page(axe_issues, "clean-page.html") == set()


def test_every_axe_violation_maps_through_shared_normalizer(axe_issues):
    """INV-FD-01: a second engine must not create unmapped noise on the corpus.
    If axe adds a rule, it must be added to the catalog, not guessed."""
    catalog = load_catalog()
    result = normalize(axe_issues, catalog)
    assert result.unmapped == [], [u.issue_id for u in result.unmapped]
    assert all(f.rule_code in catalog.rules for f in result.findings)


def test_engines_agree_on_shared_scope(axe_issues):
    """Cross-engine consistency: on checks both engines implement, they must
    agree on the corpus (same pages flagged for the same issue ids)."""
    from konformos.scan.static_engine import scan_html

    # "label" excluded: placeholder-as-name divergence (see above)
    shared = {"html-has-lang", "image-alt", "link-name", "document-title"}
    for page_name in ("shop-home.html", "product-page.html", "clean-page.html"):
        internal = {
            i.issue_id
            for i in scan_html(page_name, (CORPUS_PAGES / page_name).read_text(encoding="utf-8"))
        } & shared
        axe = by_page(axe_issues, page_name) & shared
        assert internal == axe, f"{page_name}: internal={internal} axe={axe}"


def test_pinned_axe_snapshot(axe_issues):
    """Drift pin: the full axe result set on the frozen corpus. A failure here
    means the vendored axe version or corpus changed — review deliberately."""
    snapshot = sorted({(i.page, i.issue_id) for i in axe_issues})
    expected = json.loads(
        (Path(__file__).parent / "axe_corpus_snapshot.json").read_text(encoding="utf-8")
    )
    assert snapshot == [tuple(e) for e in expected]
