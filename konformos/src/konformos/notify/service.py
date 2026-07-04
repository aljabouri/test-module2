"""Notifications & outbound webhooks — System 10 (BR-NOTIF-01/02/03).

- Every notification is a row (audit trail); email delivery is an adapter
  (SMTP plugs in via env; without it the row is the record).
- Outbound webhooks are HMAC-signed per endpoint; BR-NOTIF-03: failures
  count up and the endpoint auto-disables at the threshold.
- BR-NOTIF-02: readiness-drop noise gate (≥5 points).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from konformos.db.models import Notification, WebhookEndpoint

READINESS_DROP_THRESHOLD = 5  # BR-NOTIF-02
WEBHOOK_DISABLE_AFTER = 5     # BR-NOTIF-03 (simplified counter)


def record(session: Session, organization_id: uuid.UUID, type_: str,
           payload: dict, channel: str = "email") -> Notification:
    row = Notification(organization_id=organization_id, type=type_,
                       payload=payload, channel=channel, status="queued")
    session.add(row)
    session.flush()
    return row


def sign_payload(secret: str, body: bytes) -> str:
    timestamp = str(int(time.time()))
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body,
                   hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={mac}"


def deliver_webhooks(session: Session, organization_id: uuid.UUID,
                     event_type: str, payload: dict,
                     transport=None) -> list[dict]:
    """transport(url, body, headers) -> status_code; injectable for tests."""
    if transport is None:
        import httpx

        def transport(url, body, headers):  # pragma: no cover - network
            return httpx.post(url, content=body, headers=headers, timeout=10).status_code

    endpoints = session.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.organization_id == organization_id,
            WebhookEndpoint.active.is_(True),
        )
    ).scalars().all()

    outcomes = []
    body = json.dumps({"type": event_type, "data": payload},
                      ensure_ascii=False).encode()
    for endpoint in endpoints:
        headers = {
            "Content-Type": "application/json",
            "Konformos-Signature": sign_payload(endpoint.secret, body),
        }
        try:
            status = transport(endpoint.url, body, headers)
            ok = 200 <= status < 300
        except Exception:
            ok = False
        if ok:
            endpoint.failure_count = 0
        else:
            endpoint.failure_count += 1
            if endpoint.failure_count >= WEBHOOK_DISABLE_AFTER:  # BR-NOTIF-03
                endpoint.active = False
        outcomes.append({"endpoint": str(endpoint.id), "delivered": ok,
                         "active": endpoint.active})
    return outcomes


def notify_scan_completed(session: Session, organization_id: uuid.UUID,
                          scan_id: uuid.UUID, scores: dict,
                          previous: dict | None, transport=None) -> None:
    record(session, organization_id, "scan_done",
           {"scan_id": str(scan_id), "scores": scores})
    deliver_webhooks(session, organization_id, "scan.completed",
                     {"scan_id": str(scan_id), "scores": scores},
                     transport=transport)
    if previous:
        drops = {
            jurisdiction: (previous.get(jurisdiction), score)
            for jurisdiction, score in scores.items()
            if isinstance(previous.get(jurisdiction), int)
            and previous[jurisdiction] - score >= READINESS_DROP_THRESHOLD
        }
        if drops:  # BR-NOTIF-02
            record(session, organization_id, "readiness_drop",
                   {"scan_id": str(scan_id), "drops": {
                       j: {"from": pair[0], "to": pair[1]} for j, pair in drops.items()
                   }})
            deliver_webhooks(session, organization_id, "readiness.changed",
                             {"scan_id": str(scan_id), "scores": scores},
                             transport=transport)


def notify_pack_published(session: Session, organization_ids: set[uuid.UUID],
                          pack_version: str, transport=None) -> None:
    """BR-LEG-05 Changelog: 'المعيار تحدّث → Readiness أُعيد حسابه'."""
    for organization_id in organization_ids:
        record(session, organization_id, "legal_update",
               {"pack": pack_version,
                "message": f"المعيار تحدّث إلى {pack_version} وأُعيد حساب الجاهزية."})
        deliver_webhooks(session, organization_id, "legal.pack_published",
                         {"pack": pack_version}, transport=transport)


def notify_drift(session: Session, organization_id: uuid.UUID,
                 property_id: uuid.UUID, detail: dict) -> None:
    record(session, organization_id, "drift",
           {"property_id": str(property_id), **detail})
