"""Live URL crawler — Tech Spec v1.0 §4.4 URL Adapter, limits per BR-SCAN-01,
SSRF guard per VAL-PROP-01.

- Sequential, polite (≤2 in-flight satisfied by sequential fetching), UA
  identifies the scanner, robots.txt honored.
- SSRF: hostname resolved BEFORE fetching; private/loopback/link-local ranges
  refused unless explicitly allowed (tests/local dev via
  KONFORMOS_ALLOW_PRIVATE_URLS=1).
- Page priority when over the cap (BR-SCAN-02): root first, then
  commerce-critical URL patterns, then discovery order.
"""
from __future__ import annotations

import ipaddress
import os
import socket
import urllib.robotparser
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

USER_AGENT = "KonformOS-Scanner/0.1 (+https://konformos.dev/scanner)"
PAGE_TIMEOUT_MS = 60_000  # NFR-SCAN-02
CRITICAL_PATTERNS = ("cart", "checkout", "warenkorb", "kasse", "register",
                     "login", "search", "product", "produkt")


class UnsafeUrl(ValueError):
    """VAL-PROP-01: private/loopback targets are refused (SSRF guard)."""


def assert_public_host(url: str) -> None:
    if os.environ.get("KONFORMOS_ALLOW_PRIVATE_URLS") == "1":
        return
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrl(f"scheme {parsed.scheme!r} not allowed")
    host = parsed.hostname or ""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UnsafeUrl(f"cannot resolve {host}") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if (address.is_private or address.is_loopback or address.is_link_local
                or address.is_reserved or address.is_multicast):
            raise UnsafeUrl(f"{host} resolves to non-public address {address}")


@dataclass
class CrawlResult:
    pages: list[tuple[str, str]] = field(default_factory=list)  # (path, html)
    pages_skipped: list[dict] = field(default_factory=list)     # EDGE-SCAN-04


def _prioritize(links: list[str]) -> list[str]:
    critical = [l for l in links if any(p in l.lower() for p in CRITICAL_PATTERNS)]
    rest = [l for l in links if l not in critical]
    return critical + rest


def crawl(root_url: str, max_pages: int, max_depth: int = 3) -> CrawlResult:
    assert_public_host(root_url)
    from playwright.sync_api import sync_playwright

    from konformos.scan.axe_engine import _find_chromium

    origin = urlparse(root_url).netloc
    robots = urllib.robotparser.RobotFileParser()
    robots_url = urljoin(root_url, "/robots.txt")
    try:
        robots.set_url(robots_url)
        robots.read()
        have_robots = True
    except Exception:
        have_robots = False

    result = CrawlResult()
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(root_url, 0)]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=_find_chromium())
        context = browser.new_context(user_agent=USER_AGENT)
        try:
            while queue and len(result.pages) < max_pages:
                url, depth = queue.pop(0)
                if url in visited or depth > max_depth:
                    continue
                visited.add(url)
                if have_robots and not robots.can_fetch(USER_AGENT, url):
                    result.pages_skipped.append({"url": url, "reason": "robots_disallow"})
                    continue
                page = context.new_page()
                try:
                    response = page.goto(url, wait_until="load", timeout=PAGE_TIMEOUT_MS)
                    if response is None or response.status >= 400:
                        status = response.status if response else "no-response"
                        result.pages_skipped.append({"url": url, "reason": f"http_{status}"})
                        continue
                    html = page.content()
                    path = urlparse(url).path or "/"
                    result.pages.append((path, html))
                    if depth < max_depth:
                        links = page.eval_on_selector_all(
                            "a[href]", "els => els.map(e => e.href)"
                        )
                        same_origin = [
                            l.split("#")[0] for l in links
                            if urlparse(l).netloc == origin and l.split("#")[0] not in visited
                        ]
                        for link in _prioritize(sorted(set(same_origin))):
                            queue.append((link, depth + 1))
                except Exception as exc:  # timeout etc. → skipped, not fatal
                    result.pages_skipped.append({"url": url, "reason": f"error:{type(exc).__name__}"})
                finally:
                    page.close()
        finally:
            browser.close()
    return result
