"""Continuous monitoring (Flow C) + queue durability.

- tick(): enqueue a fresh scan for every monitoring+ property whose last
  completed scan is older than the interval (default weekly). Skips
  properties with a queued/running scan (EDGE-SCAN-01).
- recover_stuck_scans(): re-enqueue scans left in 'queued' (e.g. after a
  process death) — the durability shim under the in-process worker; a
  distributed queue replaces the transport, not these semantics.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from konformos.billing.service import TIER_MATRIX
from konformos.db.models import Property, Scan, Subscription
from konformos.db.session import set_org_context, set_system_context

SCHEDULED_TIERS = {"monitoring", "dev", "agency"}


def scan_interval() -> timedelta:
    return timedelta(hours=int(os.environ.get("KONFORMOS_SCAN_INTERVAL_HOURS", "168")))


def tick(session: Session, worker) -> list[str]:
    """One scheduler pass; returns the enqueued scan ids."""
    set_system_context(session)
    cutoff = datetime.now(timezone.utc) - scan_interval()
    enqueued: list[str] = []

    subscriptions = session.execute(
        select(Subscription).where(Subscription.status == "active",
                                   Subscription.tier.in_(SCHEDULED_TIERS))
    ).scalars().all()

    for subscription in subscriptions:
        set_org_context(session, subscription.organization_id)
        properties = session.execute(
            select(Property).where(
                Property.organization_id == subscription.organization_id)
        ).scalars().all()
        caps = TIER_MATRIX[subscription.tier]
        for prop in properties:
            active = session.execute(
                select(Scan.id).where(Scan.property_id == prop.id,
                                      Scan.status.in_(("queued", "running")))
            ).scalar_one_or_none()
            if active:  # EDGE-SCAN-01
                continue
            last = session.execute(
                select(Scan.created_at).where(Scan.property_id == prop.id,
                                              Scan.status == "completed")
                .order_by(Scan.created_at.desc()).limit(1)
            ).scalar_one_or_none()
            if last is not None and last > cutoff:
                continue
            scan = Scan(
                property_id=prop.id,
                organization_id=subscription.organization_id,
                trigger="scheduled", input_type="url", status="queued",
                profile_snapshot={"input_ref": {"url": prop.url},
                                  "page_cap": caps["scan_pages"]},
            )
            session.add(scan)
            session.flush()
            session.commit()
            worker.enqueue(scan.id)
            enqueued.append(str(scan.id))
    return enqueued


def recover_stuck_scans(session: Session, worker) -> list[str]:
    """Re-enqueue scans stranded in 'queued' (process restart recovery)."""
    stuck = session.execute(
        select(Scan.id).where(Scan.status == "queued")
    ).scalars().all()
    for scan_id in stuck:
        worker.enqueue(scan_id)
    return [str(s) for s in stuck]
