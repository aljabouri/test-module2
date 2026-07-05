"""axe-core engine via Playwright — the second engine, normalized through the
SAME catalog-derived table as the internal engine (Tech Spec v1.0 §4.4.3: the
evaluator never knows which engine found a defect).

- axe-core is vendored (konformos/vendor/axe.min.js, MPL-2.0) so scans are
  reproducible offline against a pinned version (INV-SC-02).
- Only WCAG-tagged rules run (best-practice rules are out of legal scope).
- Chromium comes from PLAYWRIGHT_BROWSERS_PATH or an explicit executable path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from konformos.scan.static_engine import RawIssue

ENGINE_NAME = "axe-core"
AXE_SOURCE_PATH = Path(__file__).resolve().parents[1] / "vendor" / "axe.min.js"

WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"]

# Map axe impact → our severity enum (same scale the internal engine uses)
IMPACT_TO_SEVERITY = {
    "critical": "critical",
    "serious": "serious",
    "moderate": "moderate",
    "minor": "minor",
}


def _find_chromium() -> str | None:
    """Resolve a Chromium executable without downloading anything."""
    candidates = []
    browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if browsers_path:
        base = Path(browsers_path)
        candidates.append(base / "chromium")  # direct symlink layout
        for revision_dir in sorted(base.glob("chromium-*")):
            candidates.append(revision_dir / "chrome-linux" / "chrome")
            candidates.append(revision_dir / "chrome-linux" / "headless_shell")
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


class AxeUnavailable(RuntimeError):
    """Raised when Playwright/Chromium cannot run in this environment."""


class AxeEngine:
    """Batch runner: one browser for many pages (NFR-SCAN performance)."""

    def __init__(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover
            raise AxeUnavailable("playwright not installed") from exc
        self._sync_playwright = sync_playwright
        self._axe_source = AXE_SOURCE_PATH.read_text(encoding="utf-8")
        self.version: str | None = None

    def scan_pages(self, pages: list[tuple[str, str]]) -> list[RawIssue]:
        """pages: [(page_path, html)] → RawIssues from axe violations."""
        issues: list[RawIssue] = []
        with self._sync_playwright() as playwright:
            try:
                executable = _find_chromium()
                browser = playwright.chromium.launch(
                    headless=True,
                    executable_path=executable,
                )
            except Exception as exc:  # pragma: no cover
                raise AxeUnavailable(f"chromium launch failed: {exc}") from exc
            try:
                context = browser.new_context()
                for page_path, html in pages:
                    page = context.new_page()
                    page.set_content(html, wait_until="load")
                    page.add_script_tag(content=self._axe_source)
                    result = page.evaluate(
                        "async (tags) => await axe.run(document, "
                        "{ runOnly: { type: 'tag', values: tags } })",
                        WCAG_TAGS,
                    )
                    self.version = result.get("testEngine", {}).get("version")
                    for violation in result["violations"]:
                        for node in violation["nodes"]:
                            issues.append(RawIssue(
                                engine=ENGINE_NAME,
                                issue_id=violation["id"],
                                page=page_path,
                                selector=(node.get("target") or ["?"])[0],
                                evidence=json.dumps({
                                    "impact": violation.get("impact"),
                                    "html": (node.get("html") or "")[:200],
                                }, ensure_ascii=False),
                            ))
                    page.close()
            finally:
                browser.close()
        return issues
