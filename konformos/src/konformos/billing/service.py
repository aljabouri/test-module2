"""Billing & access — Engineering Rules v1.1 BR-BIL matrix, SM-SUB read-only
states, EDGE-BIL-02 idempotent webhooks. Stripe is the source of truth for
subscription state; verification uses Stripe's v1 HMAC scheme when
STRIPE_WEBHOOK_SECRET is set."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from konformos.db.models import Scan, Subscription

# BR-BIL: tier × capability matrix (v1.1 §3.8)
TIER_MATRIX: dict[str, dict] = {
    "free_scan": {"properties": 1, "scan_pages": 1, "scans_per_day": 1,
                  "dossier": "none", "code_inputs": False},
    "report": {"properties": 1, "scan_pages": 20, "scans_per_day": 5,
               "dossier": "once", "code_inputs": False},
    "monitoring": {"properties": 3, "scan_pages": 50, "scans_per_day": 20,
                   "dossier": "unlimited", "code_inputs": False},
    "dev": {"properties": 10, "scan_pages": 50, "scans_per_day": 20,
            "dossier": "unlimited", "code_inputs": True},
    "agency": {"properties": 100000, "scan_pages": 50, "scans_per_day": 20,
               "dossier": "unlimited", "code_inputs": True},
}


class TierInsufficient(PermissionError):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class SubscriptionPastDue(PermissionError):
    """SM-SUB: past_due/canceled = read-only. Existing data stays visible."""


def get_subscription(session: Session, organization_id: uuid.UUID) -> Subscription | None:
    return session.execute(
        select(Subscription).where(Subscription.organization_id == organization_id)
        .order_by(Subscription.created_at.desc()).limit(1)
    ).scalar_one_or_none()


def require_writable(subscription: Subscription | None) -> dict:
    """Returns the tier capabilities or raises. BR-BIL-01: checked at the
    START of an operation only."""
    if subscription is None or subscription.status != "active":
        raise SubscriptionPastDue("الحساب للقراءة فقط (اشتراك غير نشط).")
    return TIER_MATRIX[subscription.tier]


def check_scan_allowance(session: Session, organization_id: uuid.UUID,
                         subscription: Subscription) -> dict:
    caps = require_writable(subscription)
    since = datetime.now(timezone.utc) - timedelta(days=1)
    scans_today = session.execute(
        select(func.count(Scan.id)).where(
            Scan.organization_id == organization_id, Scan.created_at >= since,
        )
    ).scalar_one()
    if scans_today >= caps["scans_per_day"]:
        raise TierInsufficient(
            f"حد الفحوصات اليومية لمستوى {subscription.tier} هو {caps['scans_per_day']}."
        )
    return caps


def check_dossier_allowance(session: Session, organization_id: uuid.UUID,
                            subscription: Subscription) -> None:
    caps = require_writable(subscription)
    if caps["dossier"] == "none":
        raise TierInsufficient("توليد Dossier يتطلب مستوى report أو أعلى.")
    if caps["dossier"] == "once":
        from konformos.db.models import Dossier, Property
        count = session.execute(
            select(func.count(Dossier.id))
            .join(Property, Property.id == Dossier.property_id)
            .where(Property.organization_id == organization_id)
        ).scalar_one()
        if count >= 1:
            raise TierInsufficient("مستوى report يتيح Dossier واحداً — رقِّ للمستوى الأعلى.")


# ── Stripe webhook (EDGE-BIL-02, BR-BIL-03) ──────────────────────────────
class InvalidSignature(ValueError):
    pass


def verify_stripe_signature(payload: bytes, header: str, secret: str) -> None:
    """Stripe v1 scheme: header 't=<ts>,v1=<hmac>'."""
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    timestamp, signature = parts.get("t"), parts.get("v1")
    if not timestamp or not signature:
        raise InvalidSignature("malformed Stripe-Signature header")
    expected = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise InvalidSignature("signature mismatch")


STATUS_MAP = {  # Stripe status → SM-SUB state
    "active": "active",
    "trialing": "active",
    "past_due": "past_due",
    "unpaid": "past_due",
    "canceled": "canceled",
}


@dataclass
class WebhookOutcome:
    event_id: str
    duplicate: bool = False
    applied: str | None = None


def handle_stripe_event(session: Session, payload: bytes,
                        signature_header: str | None) -> WebhookOutcome:
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    if secret:
        if not signature_header:
            raise InvalidSignature("missing Stripe-Signature")
        verify_stripe_signature(payload, signature_header, secret)

    event = json.loads(payload)
    event_id = event["id"]

    # EDGE-BIL-02: idempotency by event id
    already = session.execute(text(
        "SELECT 1 FROM processed_stripe_events WHERE event_id = :e"
    ), {"e": event_id}).scalar()
    if already:
        return WebhookOutcome(event_id=event_id, duplicate=True)
    session.execute(text(
        "INSERT INTO processed_stripe_events (event_id) VALUES (:e)"
    ), {"e": event_id})

    outcome = WebhookOutcome(event_id=event_id)
    if event.get("type", "").startswith("customer.subscription."):
        obj = event["data"]["object"]
        subscription = session.execute(
            select(Subscription).where(
                Subscription.stripe_customer_id == obj.get("customer")
            )
        ).scalar_one_or_none()
        if subscription is not None:
            new_status = STATUS_MAP.get(obj.get("status", ""), subscription.status)
            if event["type"] == "customer.subscription.deleted":
                new_status = "canceled"
            subscription.status = new_status
            tier = (obj.get("metadata") or {}).get("tier")
            if tier in TIER_MATRIX:
                subscription.tier = tier
            outcome.applied = f"{subscription.tier}/{new_status}"
    session.flush()
    return outcome
