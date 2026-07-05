"""Internal static HTML accessibility engine ("internal" in Rule.test_logic).

Deterministic, dependency-free checks emitting axe-compatible issue ids so the
Normalizer maps them through the same catalog table (Tech Spec v1.0 §4.4.3).
This engine powers the Golden Corpus regression baseline: its output on the
frozen corpus MUST stay byte-stable across releases — any drift is caught by
tests before it can silently move customer scores.
"""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser

ENGINE_NAME = "internal"
ENGINE_VERSION = "internal-0.1"

# Void/skippable input types for the label check
UNLABELLED_EXEMPT_TYPES = {"hidden", "submit", "button", "reset"}


@dataclass(frozen=True)
class RawIssue:
    engine: str
    issue_id: str  # axe-compatible id, resolved to rule_code by the Normalizer
    page: str
    selector: str
    evidence: str


class _Collector(HTMLParser):
    def __init__(self, page: str):
        super().__init__(convert_charrefs=True)
        self.page = page
        self.issues: list[RawIssue] = []
        self.tag_counts: dict[str, int] = {}
        self.saw_html_lang: bool | None = None
        self.title_text = ""
        self._in_title = False
        self._label_depth = 0
        self.label_for_ids: set[str] = set()
        self.pending_inputs: list[tuple[str, dict, bool]] = []  # selector, attrs, inside_label
        # anchor tracking: (selector, attrs, text_parts, has_img_alt)
        self._anchor_stack: list[list] = []

    # -- helpers -------------------------------------------------------
    def _selector(self, tag: str, attrs: dict) -> str:
        for key in ("id", "name", "src", "href"):
            if attrs.get(key):
                return f"{tag}[{key}='{attrs[key]}']"
        n = self.tag_counts.get(tag, 1)
        return f"{tag}:nth-of-type({n})"

    def _issue(self, issue_id: str, selector: str) -> None:
        self.issues.append(RawIssue(
            engine=ENGINE_NAME,
            issue_id=issue_id,
            page=self.page,
            selector=selector,
            evidence=(self.get_starttag_text() or selector)[:200],
        ))

    # -- parser hooks --------------------------------------------------
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_starttag(self, tag, attrs_list):
        attrs = dict(attrs_list)
        self.tag_counts[tag] = self.tag_counts.get(tag, 0) + 1
        selector = self._selector(tag, attrs)

        if tag == "html" and self.saw_html_lang is None:
            self.saw_html_lang = bool((attrs.get("lang") or "").strip())
            if not self.saw_html_lang:
                self._issue("html-has-lang", "html")
        elif tag == "title":
            self._in_title = True
        elif tag == "img":
            if "alt" not in attrs:  # empty alt = decorative, allowed
                self._issue("image-alt", selector)
            if self._anchor_stack and (attrs.get("alt") or "").strip():
                self._anchor_stack[-1][3] = True
        elif tag == "label":
            self._label_depth += 1
            if attrs.get("for"):
                self.label_for_ids.add(attrs["for"])
        elif tag in ("input", "select", "textarea"):
            input_type = (attrs.get("type") or "text").lower()
            if not (tag == "input" and input_type in UNLABELLED_EXEMPT_TYPES):
                self.pending_inputs.append((selector, attrs, self._label_depth > 0))
        elif tag == "a" and attrs.get("href"):
            self._anchor_stack.append([selector, attrs, [], False])
        elif tag == "marquee":
            self._issue("marquee", selector)
        elif tag == "meta" and (attrs.get("name") or "").lower() == "viewport":
            content = (attrs.get("content") or "").replace(" ", "").lower()
            if "user-scalable=no" in content or "maximum-scale=1" in content:
                self._issue("meta-viewport", "meta[name='viewport']")

        tabindex = attrs.get("tabindex")
        if tabindex is not None:
            try:
                if int(tabindex) > 0:
                    self._issue("tabindex", selector)
            except ValueError:
                pass

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "label" and self._label_depth:
            self._label_depth -= 1
        elif tag == "a" and self._anchor_stack:
            selector, attrs, text_parts, has_img_alt = self._anchor_stack.pop()
            text = "".join(text_parts).strip()
            accessible = (
                text
                or (attrs.get("aria-label") or "").strip()
                or attrs.get("aria-labelledby")
                or (attrs.get("title") or "").strip()
                or has_img_alt
            )
            if not accessible:
                self.issues.append(RawIssue(
                    engine=ENGINE_NAME, issue_id="link-name",
                    page=self.page, selector=selector,
                    evidence=f"<a href='{attrs.get('href', '')}'> بلا اسم برمجي"[:200],
                ))

    def handle_data(self, data):
        if self._in_title:
            self.title_text += data
        if self._anchor_stack:
            self._anchor_stack[-1][2].append(data)

    # -- post-parse checks ---------------------------------------------
    def finalize(self) -> list[RawIssue]:
        if not self.title_text.strip():
            self.issues.append(RawIssue(
                engine=ENGINE_NAME, issue_id="document-title",
                page=self.page, selector="html", evidence="لا <title> غير فارغ",
            ))
        for selector, attrs, inside_label in self.pending_inputs:
            labelled = (
                inside_label
                or (attrs.get("id") and attrs["id"] in self.label_for_ids)
                or (attrs.get("aria-label") or "").strip()
                or attrs.get("aria-labelledby")
                or (attrs.get("title") or "").strip()
            )
            if not labelled:
                self.issues.append(RawIssue(
                    engine=ENGINE_NAME, issue_id="label",
                    page=self.page, selector=selector,
                    evidence=f"{selector} بلا وسم مرتبط",
                ))
        return self.issues


def scan_html(page: str, html: str) -> list[RawIssue]:
    collector = _Collector(page)
    collector.feed(html)
    return collector.finalize()
