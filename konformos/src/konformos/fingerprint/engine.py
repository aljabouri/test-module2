"""Fingerprint Engine — Tech Spec v1.0 §4.3, the technical Router axis.

Weighted signals (headers, asset paths, DOM markers) → platform/theme with a
confidence score per field. BR-FP-01: below 0.4 we say `unknown` and claim
NOTHING; between 0.4 and 0.7 the UI must hedge ("المحتمل"). Every conclusion
keeps its raw evidence (`raw_signals`) for audit.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

CONFIDENCE_HEDGED = 0.7   # central thresholds (BR-FP-01)
CONFIDENCE_UNKNOWN = 0.4

# (platform, regex on html/headers blob, weight, signal name)
_PLATFORM_SIGNALS = [
    ("shopware", r'content="Shopware', 0.9, "meta-generator-shopware"),
    ("shopware", r"/bundles/storefront/", 0.5, "asset-path-shopware"),
    ("shopware", r"sw-cache-hash|shopware", 0.3, "marker-shopware"),
    ("woocommerce", r"woocommerce", 0.6, "marker-woocommerce"),
    ("wordpress", r"/wp-content/", 0.7, "asset-path-wp-content"),
    ("wordpress", r'content="WordPress', 0.9, "meta-generator-wordpress"),
    ("shopify", r"cdn\.shopify\.com", 0.9, "asset-cdn-shopify"),
    ("shopify", r"Shopify\.theme", 0.7, "js-shopify-theme"),
    ("magento", r"/static/version\d+/frontend/|Magento", 0.7, "marker-magento"),
]

_THEME_EXTRACTORS = [
    ("wordpress", re.compile(r"/wp-content/themes/([a-z0-9_-]+)/", re.I), 0.85),
    ("woocommerce", re.compile(r"/wp-content/themes/([a-z0-9_-]+)/", re.I), 0.85),
    ("shopify", re.compile(r'Shopify\.theme\s*=\s*{[^}]*"name"\s*:\s*"([^"]+)"'), 0.85),
    ("shopware", re.compile(r"/theme/([a-z0-9_-]+)/", re.I), 0.6),
]

_VERSION_EXTRACTORS = [
    re.compile(r'content="WordPress ([\d.]+)"'),
    re.compile(r'content="Shopware ([\d.]+)"'),
]


@dataclass
class FingerprintResult:
    platform: str = "unknown"
    platform_version: str | None = None
    theme: dict = field(default_factory=dict)
    detection_confidence: dict = field(default_factory=dict)
    raw_signals: list[dict] = field(default_factory=list)

    @property
    def platform_display(self) -> str:
        """BR-FP-01: safe legal wording built in, not left to the UI."""
        conf = self.detection_confidence.get("platform", 0.0)
        if conf < CONFIDENCE_UNKNOWN:
            return "unknown"
        if conf < CONFIDENCE_HEDGED:
            return f"{self.platform} (المحتمل)"
        return self.platform


def fingerprint_html(html: str, headers: dict[str, str] | None = None) -> FingerprintResult:
    result = FingerprintResult()
    blob = html + "\n" + "\n".join(f"{k}: {v}" for k, v in (headers or {}).items())

    scores: dict[str, float] = {}
    for platform, pattern, weight, signal in _PLATFORM_SIGNALS:
        if re.search(pattern, blob, re.IGNORECASE):
            # diminishing accumulation, capped at 0.98 — never claim certainty
            scores[platform] = min(0.98, scores.get(platform, 0.0) + weight * (1 - scores.get(platform, 0.0)))
            result.raw_signals.append({"signal": signal, "platform": platform, "weight": weight})

    # WooCommerce is WordPress + woocommerce marker: prefer the more specific
    if "woocommerce" in scores and "wordpress" in scores:
        scores["woocommerce"] = min(0.98, max(scores["woocommerce"], scores["wordpress"]))
        del scores["wordpress"]

    if scores:
        platform, confidence = max(scores.items(), key=lambda item: item[1])
        if confidence >= CONFIDENCE_UNKNOWN:
            result.platform = platform
        result.detection_confidence["platform"] = round(confidence, 2)
    else:
        result.detection_confidence["platform"] = 0.0

    for target_platform, extractor, confidence in _THEME_EXTRACTORS:
        if result.platform in (target_platform,):
            match = extractor.search(html)
            if match:
                result.theme = {"name": match.group(1).lower()}
                result.detection_confidence["theme"] = confidence
                result.raw_signals.append({"signal": "theme-path", "value": match.group(1)})
                break
    if not result.theme:
        result.detection_confidence["theme"] = 0.0

    for extractor in _VERSION_EXTRACTORS:
        match = extractor.search(html)
        if match:
            result.platform_version = match.group(1)
            result.detection_confidence["platform_version"] = 0.8
            break

    return result
