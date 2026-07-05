"""Automatic moat feeding — closes the P7 loop: every completed scan of a
confidently-fingerprinted, consenting store enriches knowledge_entries.

Gates (all mandatory, checked at write time):
- INV-KG-02: organization.data_sharing_consent
- BR-FP-03:  theme confidence ≥ 0.7
- INV-KG-01: payload passes sanitize_for_moat (no identity ever)
- BR-KG-02:  upsert by (stack_signature, rule_code), counters merge
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from konformos.db.models import (
    KnowledgeEntryRow,
    Organization,
    Property,
    StackFingerprint,
)
from konformos.moat.knowledge import (
    THEME_CONFIDENCE_THRESHOLD,
    MoatContaminationError,
    sanitize_for_moat,
    stack_signature,
)
from konformos.scan.normalizer import NormalizedFinding


def feed_from_scan(session: Session, organization_id: uuid.UUID,
                   property_id: uuid.UUID,
                   findings: list[NormalizedFinding]) -> int:
    """Returns the number of knowledge entries created/updated (0 = gated)."""
    org = session.get(Organization, organization_id)
    if org is None or not org.data_sharing_consent:  # INV-KG-02
        return 0
    prop = session.get(Property, property_id)
    if prop is None or prop.current_fingerprint_id is None:
        return 0
    fingerprint = session.get(StackFingerprint, prop.current_fingerprint_id)
    if fingerprint is None:
        return 0
    theme_name = (fingerprint.theme or {}).get("name")
    theme_confidence = (fingerprint.detection_confidence or {}).get("theme", 0.0)
    if not theme_name or theme_confidence < THEME_CONFIDENCE_THRESHOLD:  # BR-FP-03
        return 0

    signature = stack_signature(
        fingerprint.platform, theme_name, fingerprint.platform_version)

    fed = 0
    for finding in findings:
        # Technical pattern only: selector shape + engine id. No page paths,
        # no evidence snippets (those can embed URLs/content).
        pattern = {
            "selector_shape": (finding.location or {}).get("selector", ""),
            "engine_issue_id": (finding.evidence or {}).get("engine_issue_id"),
            "severity": finding.severity,
        }
        try:
            sanitize_for_moat(pattern)  # INV-KG-01 — the only gate to the moat
        except MoatContaminationError:
            continue  # never let identity leak; skip silently

        existing = session.execute(
            select(KnowledgeEntryRow).where(
                KnowledgeEntryRow.stack_signature == signature,
                KnowledgeEntryRow.rule_code == finding.rule_code,
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(KnowledgeEntryRow(
                stack_signature=signature, rule_code=finding.rule_code,
                pattern=pattern, occurrence_count=1,
            ))
        else:  # BR-KG-02
            existing.occurrence_count += 1
        fed += 1
    session.flush()
    return fed
