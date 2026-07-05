"""Knowledge moat — proactive Theme Intelligence (roadmap point 2).

- BR-KG-01: stack_signature = platform:theme_name:theme_major (VAL-ID-04).
- INV-KG-01: no identity may enter the moat — sanitize_for_moat() is the ONLY
  gate and rejects URLs, domains, emails and UUIDs anywhere in the payload.
- INV-KG-02: writes require data_sharing_consent, checked at write time.
- BR-FP-03: enrichment requires theme confidence ≥ 0.7.
- predict() is the acquisition weapon: known defects for a theme in the two
  seconds after fingerprinting, before any crawl.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

STACK_SIGNATURE_PATTERN = r"^[a-z0-9_]+:[a-z0-9_-]+:[0-9]+$"
THEME_CONFIDENCE_THRESHOLD = 0.7  # BR-FP-01/03 central config, not scattered numbers

_IDENTITY_PATTERNS = [
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"\bwww\.", re.IGNORECASE),
    re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", re.IGNORECASE),  # emails
    re.compile(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        re.IGNORECASE,
    ),  # UUIDs (property/org ids)
    re.compile(r"\b[a-z0-9-]+\.(?:de|com|net|org|shop|eu|io)\b", re.IGNORECASE),  # bare domains
]
_IDENTITY_KEYS = {"url", "domain", "organization", "organization_id", "property",
                  "property_id", "email", "customer", "owner"}


class MoatContaminationError(ValueError):
    """Raised when identity data tries to enter the anonymized moat (INV-KG-01)."""


class ConsentRequired(PermissionError):
    """INV-KG-02: writes without data_sharing_consent are refused at the gate."""


def sanitize_for_moat(payload: object, path: str = "$") -> None:
    """Walk the payload; raise on any identity marker. Mandatory on every write."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key.lower() in _IDENTITY_KEYS:
                raise MoatContaminationError(f"identity key '{key}' at {path} (INV-KG-01)")
            sanitize_for_moat(value, f"{path}.{key}")
    elif isinstance(payload, (list, tuple)):
        for i, item in enumerate(payload):
            sanitize_for_moat(item, f"{path}[{i}]")
    elif isinstance(payload, str):
        for pattern in _IDENTITY_PATTERNS:
            if pattern.search(payload):
                raise MoatContaminationError(
                    f"identity-like string at {path} (INV-KG-01)"
                )


def stack_signature(platform: str, theme_name: str, theme_version: Optional[str]) -> str:
    """BR-KG-01: major version only — patterns survive minor bumps."""
    major = (theme_version or "0").split(".")[0]
    signature = f"{platform.strip().lower()}:{theme_name.strip().lower().replace(' ', '-')}:{major}"
    if not re.match(STACK_SIGNATURE_PATTERN, signature):
        raise ValueError(f"invalid stack_signature '{signature}' (VAL-ID-04)")
    return signature


class KnowledgeEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stack_signature: str = Field(pattern=STACK_SIGNATURE_PATTERN)
    rule_code: str
    pattern: dict
    known_fix: Optional[dict] = None
    occurrence_count: int = Field(default=1, ge=1)
    fix_success_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    validated_by_expert: bool = False


@dataclass
class ThemeIntelligenceReport:
    """The pre-scan report: what we already know about this stack."""

    stack_signature: str
    confidence: float
    hedged: bool  # BR-FP-01: < 0.7 → hedged wording ("المحتمل")
    known_issues: list[dict] = field(default_factory=list)

    @property
    def known_issue_count(self) -> int:
        return len(self.known_issues)


class KnowledgeStore:
    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], KnowledgeEntry] = {}

    def contribute(self, entry: KnowledgeEntry, *, data_sharing_consent: bool) -> None:
        """The single write gate: consent + sanitization, then upsert (BR-KG-02)."""
        if not data_sharing_consent:
            raise ConsentRequired("INV-KG-02: data_sharing_consent required")
        sanitize_for_moat(entry.pattern)
        if entry.known_fix is not None:
            sanitize_for_moat(entry.known_fix)

        key = (entry.stack_signature, entry.rule_code)
        existing = self._entries.get(key)
        if existing is None:
            self._entries[key] = entry
        else:  # BR-KG-02: same signature+rule → update counters, no new row
            merged = existing.model_copy(update={
                "occurrence_count": existing.occurrence_count + entry.occurrence_count,
                "known_fix": entry.known_fix or existing.known_fix,
                "fix_success_rate": (
                    entry.fix_success_rate
                    if entry.fix_success_rate is not None
                    else existing.fix_success_rate
                ),
                "validated_by_expert": existing.validated_by_expert or entry.validated_by_expert,
            })
            self._entries[key] = merged

    def predict(
        self,
        platform: str,
        theme_name: str,
        theme_version: Optional[str],
        theme_confidence: float,
    ) -> ThemeIntelligenceReport:
        """Instant pre-scan intelligence. Below the confidence threshold no
        enrichment happens at all (BR-FP-03: wrong enrichment is worse than none)."""
        signature = stack_signature(platform, theme_name, theme_version)
        if theme_confidence < THEME_CONFIDENCE_THRESHOLD:
            return ThemeIntelligenceReport(
                stack_signature=signature, confidence=theme_confidence,
                hedged=True, known_issues=[],
            )
        issues = [
            {
                "rule_code": entry.rule_code,
                "pattern": entry.pattern,
                "seen_in_stores": entry.occurrence_count,
                "fix_available": entry.known_fix is not None,
                "fix_success_rate": entry.fix_success_rate,
                "validated_by_expert": entry.validated_by_expert,
            }
            for (sig, _), entry in sorted(self._entries.items())
            if sig == signature
        ]
        return ThemeIntelligenceReport(
            stack_signature=signature, confidence=theme_confidence,
            hedged=False, known_issues=issues,
        )
