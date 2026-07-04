"""Repositories — the only write paths for their aggregates.

- TimelineRepository.append: THE single entry point for timeline writes
  (INV-TL-05); per-property row lock serializes sequence numbers (INV-TL-04),
  hashes come exclusively from core.hashing (INV-TL-02/03).
- seed_from_catalog: idempotent Rules-as-Data ingestion (upsert by natural
  keys — re-running never duplicates, matching BR-KG-02 spirit for rules).
- get_active_pack_db: BR-LEG-04 (newest active pack effective on the date).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from konformos.core.hashing import GENESIS, SealedEvent, canonical_hash, verify_chain
from konformos.db.models import (
    Property,
    RuleMappingRow,
    RulePackRow,
    RuleRow,
    TimelineEventRow,
)
from konformos.registry.loader import Catalog


class PropertyNotFound(LookupError):
    pass


class TimelineRepository:
    @staticmethod
    def append(
        session: Session,
        property_id: uuid.UUID,
        event_type: str,
        payload: dict,
        timestamp_token: str | None = None,  # INV-TL-06: TSA failure never blocks
    ) -> TimelineEventRow:
        # INV-TL-04: lock the property row → sequence numbers can never race
        locked = session.execute(
            select(Property.id).where(Property.id == property_id).with_for_update()
        ).scalar_one_or_none()
        if locked is None:
            raise PropertyNotFound(str(property_id))

        last = session.execute(
            select(TimelineEventRow)
            .where(TimelineEventRow.property_id == property_id)
            .order_by(TimelineEventRow.sequence_number.desc())
            .limit(1)
        ).scalar_one_or_none()

        row = TimelineEventRow(
            property_id=property_id,
            sequence_number=1 if last is None else last.sequence_number + 1,
            event_type=event_type,
            payload=payload,
            content_hash=canonical_hash(payload),
            prev_hash=GENESIS if last is None else last.content_hash,
            timestamp_token=timestamp_token,
        )
        session.add(row)
        session.flush()
        return row

    @staticmethod
    def verify_property_chain(session: Session, property_id: uuid.UUID) -> int:
        """Recompute the whole chain from stored rows; raises ChainBroken on
        any tampering (EDGE-TL-01). Returns the chain length."""
        rows = session.execute(
            select(TimelineEventRow)
            .where(TimelineEventRow.property_id == property_id)
            .order_by(TimelineEventRow.sequence_number)
        ).scalars().all()
        verify_chain([
            SealedEvent(
                sequence_number=row.sequence_number,
                event_type=row.event_type,
                payload=row.payload,
                content_hash=row.content_hash,
                prev_hash=row.prev_hash,
            )
            for row in rows
        ])
        return len(rows)


@dataclass
class SeedReport:
    rules_inserted: int = 0
    rules_updated: int = 0
    packs_inserted: int = 0
    packs_skipped: int = 0
    mappings_inserted: int = 0
    mappings_updated: int = 0


def seed_from_catalog(session: Session, catalog: Catalog) -> SeedReport:
    report = SeedReport()

    for rule in catalog.rules.values():
        existing = session.execute(
            select(RuleRow).where(RuleRow.code == rule.code)
        ).scalar_one_or_none()
        values = dict(
            title=rule.title,
            description=rule.description,
            wcag_level=rule.wcag_level,
            test_logic=rule.test_logic.model_dump(),
            automatable=rule.automatable,
            source_standard=rule.source_standard,
        )
        if existing is None:
            session.add(RuleRow(code=rule.code, **values))
            report.rules_inserted += 1
        else:
            for key, value in values.items():
                setattr(existing, key, value)
            report.rules_updated += 1

    for pack in catalog.packs:
        existing = session.execute(
            select(RulePackRow).where(RulePackRow.version == pack.version)
        ).scalar_one_or_none()
        if existing is not None:
            # INV-RP-01: published packs are immutable; drafts are re-seedable
            # only by explicit curator action, never silently — skip either way.
            report.packs_skipped += 1
            continue
        session.add(RulePackRow(
            jurisdiction=pack.jurisdiction,
            version=pack.version,
            effective_from=pack.effective_from,
            status=pack.status,
            legal_basis=pack.legal_basis,
            rule_refs=[r.model_dump() for r in pack.rule_refs],
            report_template_id=pack.report_template_id,
            seed=pack.seed,
            seed_provenance=pack.seed_provenance,
            signed_by=uuid.UUID(pack.signed_by) if pack.signed_by else None,
            signed_at=pack.signed_at,
            source_change_events=[uuid.UUID(e) for e in pack.source_change_events],
        ))
        report.packs_inserted += 1

    for mapping in catalog.mappings.values():
        existing = session.execute(
            select(RuleMappingRow).where(RuleMappingRow.rule_code == mapping.rule_code)
        ).scalar_one_or_none()
        if existing is None:
            session.add(RuleMappingRow(
                rule_code=mapping.rule_code, equivalences=mapping.equivalences,
            ))
            report.mappings_inserted += 1
        else:
            existing.equivalences = mapping.equivalences
            report.mappings_updated += 1

    session.flush()
    return report


def get_active_pack_db(
    session: Session, jurisdiction: str, on_date: date
) -> RulePackRow | None:
    """BR-LEG-04: newest active pack whose effective_from <= on_date."""
    return session.execute(
        select(RulePackRow)
        .where(
            RulePackRow.jurisdiction == jurisdiction,
            RulePackRow.status == "active",
            RulePackRow.effective_from <= on_date,
        )
        .order_by(RulePackRow.effective_from.desc(), RulePackRow.version.desc())
        .limit(1)
    ).scalar_one_or_none()
