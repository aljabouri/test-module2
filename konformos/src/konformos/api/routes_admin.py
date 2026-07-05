"""Admin control plane — /v1/admin/* — fully isolated from the customer
surface (ISO rules):

- ISO-01  Disjoint token audiences: these endpoints ONLY accept aud=admin
          tokens, minted exclusively by the step-up flow below (fresh TOTP,
          15-minute TTL). Customer endpoints reject aud=admin symmetrically.
- ISO-02  Cross-org visibility is READ-ONLY at the database layer: the
          `admin_ro` RLS bypass grants SELECT and nothing else. Mutations go
          through named flows (tier, suspend, lifecycle) that are…
- ISO-03  …individually AUDITED into a hash-chained, append-only log — the
          same INV-TL-02/03 sealing machinery that protects customer
          evidence protects the control plane against tampering.
- ISO-04  Impersonation ("عرض كالعميل") mints a 15-minute app-surface token
          hard-wired read-only, and is itself an audited action.

Client management (CM): lifecycle state machine (SM-CLIENT), explainable
health scoring, churn signals with playbook recommendations, append-only
interaction notes — a full CRM overlay with zero new identity leakage
(everything keys on organization_id, nothing touches knowledge_entries).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from konformos.api.routes_db import ApiError, claims_dep, db_session, not_found
from konformos.api.security import (
    ADMIN_ROLES,
    ADMIN_TOKEN_TTL,
    TokenClaims,
    create_token,
    verify_totp,
)
from konformos.billing.service import TIER_MATRIX
from konformos.core.hashing import GENESIS, canonical_hash
from konformos.db.models import (
    AdminAuditLog,
    ClientNote,
    ClientProfile,
    ComplianceProfileRow,
    Finding,
    KnowledgeEntryRow,
    Organization,
    Property,
    RulePackRow,
    Scan,
    Subscription,
    User,
    WebhookEndpoint,
)
from konformos.db.session import set_admin_context, set_system_context

router = APIRouter()

LIFECYCLE_STATES = ("onboarding", "active", "at_risk", "dormant", "churned")


# ── dependencies (ISO-01) ────────────────────────────────────────────────
def admin_authed(session: Session = Depends(db_session),
                 claims: TokenClaims = Depends(claims_dep)) -> tuple[Session, TokenClaims]:
    if claims.surface != "admin":
        raise ApiError(401, "admin_token_required",
                       "لوحة التحكم تتطلب توكن إدارة مصعَّداً (TOTP).")
    if claims.role not in ADMIN_ROLES:
        raise ApiError(403, "forbidden", "الدور لا يخوّل الوصول للوحة التحكم.")
    set_admin_context(session)  # ISO-02: SELECT-only cross-org visibility
    return session, claims


# ── audit (ISO-03) — hash-chained like the evidence timeline ─────────────
def audit(session: Session, actor: uuid.UUID, action: str,
          target_type: str | None = None, target_id: str | None = None,
          data: dict | None = None) -> AdminAuditLog:
    # serialize the chain head (advisory lock: single global audit chain)
    session.execute(select(func.pg_advisory_xact_lock(0x41554449)))  # "AUDI"
    last = session.execute(
        select(AdminAuditLog).order_by(AdminAuditLog.sequence_number.desc()).limit(1)
    ).scalar_one_or_none()
    seq = 1 if last is None else last.sequence_number + 1
    payload = {"action": action, "actor": str(actor), "target_type": target_type,
               "target_id": target_id, "data": data or {}, "seq": seq}
    row = AdminAuditLog(
        sequence_number=seq, actor_user_id=actor, action=action,
        target_type=target_type, target_id=target_id, payload=payload,
        content_hash=canonical_hash(payload),
        prev_hash=GENESIS if last is None else last.content_hash,
    )
    session.add(row)
    session.flush()
    return row


# ── step-up elevation (ISO-01) ───────────────────────────────────────────
class ElevateBody(BaseModel):
    totp_code: str = Field(min_length=6, max_length=8)


@router.post("/v1/admin/auth/elevate")
def elevate(body: ElevateBody, session: Session = Depends(db_session),
            claims: TokenClaims = Depends(claims_dep)):
    """App token + fresh TOTP → 15-minute admin-surface token. The ONLY mint
    path for aud=admin; a leaked admin token dies in minutes."""
    if claims.role not in ADMIN_ROLES:
        raise ApiError(403, "forbidden", "الدور لا يخوّل التصعيد للوحة التحكم.")
    set_system_context(session)  # user lookup crosses no customer data
    user = session.get(User, claims.user_id)
    if user is None or not user.mfa_enabled or not user.mfa_secret:
        raise ApiError(401, "mfa_required", "التصعيد يتطلب MFA مفعّلاً (RBAC-02).")
    if not verify_totp(user.mfa_secret, body.totp_code):
        raise ApiError(401, "auth_required", "رمز TOTP غير صحيح.")
    token = create_token(TokenClaims(
        user.id, user.organization_id, user.role, True, surface="admin"))
    audit(session, user.id, "admin.elevate")
    return {"token": token, "surface": "admin",
            "expires_in_seconds": int(ADMIN_TOKEN_TTL.total_seconds())}


# ── health scoring (CM) — explainable, component by component ────────────
def _client_metrics(session: Session, org: Organization) -> dict:
    props = session.execute(
        select(Property).where(Property.organization_id == org.id)
    ).scalars().all()
    sub = session.execute(
        select(Subscription).where(Subscription.organization_id == org.id)
    ).scalars().first()
    users = session.execute(
        select(User).where(User.organization_id == org.id)
    ).scalars().all()
    last_scan_at = session.execute(
        select(func.max(Scan.created_at)).where(
            Scan.organization_id == org.id, Scan.status == "completed")
    ).scalar()
    scan_count = session.execute(
        select(func.count(Scan.id)).where(Scan.organization_id == org.id)
    ).scalar() or 0
    webhook_count = session.execute(
        select(func.count(WebhookEndpoint.id)).where(
            WebhookEndpoint.organization_id == org.id)
    ).scalar() or 0
    profile_count = 0
    if props:
        profile_count = session.execute(
            select(func.count(ComplianceProfileRow.id)).where(
                ComplianceProfileRow.property_id.in_([p.id for p in props]))
        ).scalar() or 0

    readiness_values = [
        v for p in props for v in (p.readiness_current or {}).values()
        if isinstance(v, (int, float))
    ]
    now = datetime.now(timezone.utc)
    days_idle = None
    if last_scan_at is not None:
        anchored = last_scan_at if last_scan_at.tzinfo else last_scan_at.replace(tzinfo=timezone.utc)
        days_idle = (now - anchored).days

    # ── components (max 100 total) ──────────────────────────────────
    if days_idle is None:
        activity = 0
    elif days_idle <= 3:
        activity = 30
    elif days_idle <= 7:
        activity = 24
    elif days_idle <= 14:
        activity = 16
    elif days_idle <= 30:
        activity = 8
    else:
        activity = 0
    readiness = round((sum(readiness_values) / len(readiness_values)) * 0.25) \
        if readiness_values else 0
    adoption = (7 if props else 0) + (6 if profile_count else 0) \
        + (6 if any(u.mfa_enabled for u in users) else 0) \
        + (6 if webhook_count else 0)
    billing = {"active": 20, "trialing": 12, "past_due": 4}.get(
        sub.status if sub else "", 0)
    score = activity + readiness + adoption + billing

    signals, playbook = [], []
    if not props:
        signals.append("no_properties")
        playbook.append("رافق العميل لإضافة أول عقار رقمي — جلسة onboarding.")
    if days_idle is None and props:
        signals.append("never_scanned")
        playbook.append("شغّل أول فحص معهم مباشرة — أول قيمة ملموسة خلال دقائق.")
    if days_idle is not None and days_idle > 14:
        signals.append(f"idle_{days_idle}d")
        playbook.append("أرسل تقرير تغيّر القانون/الجاهزية لإعادة التنشيط.")
    if readiness_values and (sum(readiness_values) / len(readiness_values)) < 50:
        signals.append("low_readiness")
        playbook.append("اقترح جلسة إصلاحات موجّهة — أعلى 5 findings أثراً.")
    if sub and sub.status == "past_due":
        signals.append("past_due")
        playbook.append("تواصل فوري بخصوص الدفع قبل تعليق القدرات (SM-SUB).")
    if users and not any(u.mfa_enabled for u in users):
        signals.append("no_mfa")
        playbook.append("ادفع نحو تفعيل MFA — يرفع الأمان ودرجة التبنّي.")

    return {
        "score": score,
        "components": {
            "activity": {"score": activity, "max": 30,
                         "days_since_last_scan": days_idle},
            "readiness": {"score": readiness, "max": 25,
                          "avg": round(sum(readiness_values) / len(readiness_values), 1)
                          if readiness_values else None},
            "adoption": {"score": adoption, "max": 25,
                         "properties": len(props), "profiles": profile_count,
                         "mfa": any(u.mfa_enabled for u in users),
                         "webhooks": webhook_count},
            "billing": {"score": billing, "max": 20,
                        "status": sub.status if sub else None},
        },
        "signals": signals,
        "playbook": playbook,
        "_props": props, "_sub": sub, "_users": users,
        "_scan_count": scan_count, "_days_idle": days_idle,
    }


def _derive_lifecycle(org: Organization, metrics: dict,
                      profile: ClientProfile | None) -> str:
    if profile is not None and profile.lifecycle_pinned:
        return profile.lifecycle  # SM-CLIENT: manual pin wins
    age_days = None
    if org.created_at is not None:
        created = org.created_at if org.created_at.tzinfo else \
            org.created_at.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - created).days
    days_idle = metrics["_days_idle"]
    if metrics["_scan_count"] == 0 and (age_days is None or age_days < 14):
        return "onboarding"
    if days_idle is not None and days_idle > 30:
        return "dormant"
    if metrics["_scan_count"] == 0 or metrics["score"] < 40:
        return "at_risk"
    return "active"


def _client_summary(session: Session, org: Organization) -> dict:
    metrics = _client_metrics(session, org)
    profile = session.execute(
        select(ClientProfile).where(ClientProfile.organization_id == org.id)
    ).scalar_one_or_none()
    lifecycle = _derive_lifecycle(org, metrics, profile)
    return {
        "organization_id": str(org.id),
        "name": org.name,
        "type": org.type,
        "country": org.country,
        "suspended": bool(getattr(org, "suspended", False)),
        "created_at": org.created_at.isoformat() if org.created_at else None,
        "tier": metrics["_sub"].tier if metrics["_sub"] else None,
        "subscription_status": metrics["_sub"].status if metrics["_sub"] else None,
        "users": len(metrics["_users"]),
        "properties": len(metrics["_props"]),
        "scans": metrics["_scan_count"],
        "health": metrics["score"],
        "signals": metrics["signals"],
        "lifecycle": lifecycle,
        "lifecycle_pinned": bool(profile.lifecycle_pinned) if profile else False,
        "account_owner": profile.account_owner if profile else None,
        "tags": list(profile.tags or []) if profile else [],
    }


# ── platform overview ────────────────────────────────────────────────────
@router.get("/v1/admin/overview")
def overview(request: Request, auth=Depends(admin_authed)):
    session, _ = auth
    orgs = session.execute(select(Organization)).scalars().all()
    tier_counts: dict[str, int] = {}
    for sub in session.execute(select(Subscription)).scalars().all():
        if sub.status in ("active", "trialing"):
            tier_counts[sub.tier] = tier_counts.get(sub.tier, 0) + 1
    month_ago = datetime.now(timezone.utc) - timedelta(days=30)
    scans_30d = session.execute(
        select(func.count(Scan.id)).where(Scan.created_at >= month_ago)
    ).scalar() or 0
    findings_open = session.execute(
        select(func.count(Finding.id)).where(Finding.status == "open")
    ).scalar() or 0
    findings_fixed = session.execute(
        select(func.count(Finding.id)).where(Finding.status == "fixed")
    ).scalar() or 0
    moat = session.execute(select(func.count(KnowledgeEntryRow.id))).scalar() or 0
    packs = session.execute(
        select(RulePackRow).where(RulePackRow.status == "active")
    ).scalars().all()
    summaries = [_client_summary(session, o) for o in orgs]
    queued = session.execute(
        select(func.count(Scan.id)).where(Scan.status.in_(("queued", "running")))
    ).scalar() or 0
    return {
        "organizations": len(orgs),
        "suspended": sum(1 for s in summaries if s["suspended"]),
        "tiers": tier_counts,
        "scans_30d": scans_30d,
        "scan_queue": queued,
        "findings": {"open": findings_open, "fixed": findings_fixed},
        "knowledge_entries": moat,
        "active_packs": [{"jurisdiction": p.jurisdiction, "version": p.version}
                         for p in packs],
        "lifecycle_breakdown": {
            state: sum(1 for s in summaries if s["lifecycle"] == state)
            for state in LIFECYCLE_STATES
        },
        "at_risk_clients": [s for s in summaries if s["lifecycle"] in
                            ("at_risk", "dormant")][:10],
        "avg_health": round(sum(s["health"] for s in summaries) / len(summaries), 1)
        if summaries else None,
        "rls_enforceable": request.app.state.rls_enforceable,
    }


# ── client list + 360 (CM) ───────────────────────────────────────────────
@router.get("/v1/admin/clients")
def list_clients(segment: Optional[str] = None, q: Optional[str] = None,
                 auth=Depends(admin_authed)):
    session, _ = auth
    orgs = session.execute(
        select(Organization).order_by(Organization.created_at.desc())
    ).scalars().all()
    out = [_client_summary(session, o) for o in orgs]
    if q:
        needle = q.lower()
        out = [c for c in out if needle in (c["name"] or "").lower()
               or needle in (c["country"] or "").lower()]
    if segment:
        if segment == "suspended":
            out = [c for c in out if c["suspended"]]
        elif segment in LIFECYCLE_STATES:
            out = [c for c in out if c["lifecycle"] == segment]
        else:
            raise ApiError(422, "validation_error",
                           f"segment يجب أن يكون أحد {LIFECYCLE_STATES + ('suspended',)}.")
    return {"clients": out, "total": len(out)}


@router.get("/v1/admin/clients/{org_id}")
def client_360(org_id: str, auth=Depends(admin_authed)):
    session, _ = auth
    org = session.get(Organization, _uuid(org_id))
    if org is None:
        raise not_found()
    metrics = _client_metrics(session, org)
    summary = _client_summary(session, org)
    notes = session.execute(
        select(ClientNote).where(ClientNote.organization_id == org.id)
        .order_by(ClientNote.created_at.desc()).limit(50)
    ).scalars().all()
    recent_scans = session.execute(
        select(Scan).where(Scan.organization_id == org.id)
        .order_by(Scan.created_at.desc()).limit(10)
    ).scalars().all()
    return {
        **summary,
        "billing_email": org.billing_email,
        "data_sharing_consent": org.data_sharing_consent,
        "health_breakdown": {k: v for k, v in metrics["components"].items()},
        "playbook": metrics["playbook"],
        "members": [
            {"id": str(u.id), "email": u.email, "role": u.role,
             "mfa_enabled": u.mfa_enabled,
             "created_at": u.created_at.isoformat() if u.created_at else None}
            for u in metrics["_users"]
        ],
        "properties": [
            {"id": str(p.id), "url": p.url, "label": p.label,
             "readiness": p.readiness_current}
            for p in metrics["_props"]
        ],
        "recent_scans": [
            {"id": str(s.id), "status": s.status, "trigger": s.trigger,
             "input_type": s.input_type,
             "created_at": s.created_at.isoformat() if s.created_at else None}
            for s in recent_scans
        ],
        "notes": [
            {"id": str(n.id), "kind": n.kind, "body": n.body,
             "author_user_id": str(n.author_user_id),
             "created_at": n.created_at.isoformat() if n.created_at else None}
            for n in notes
        ],
        "capabilities": TIER_MATRIX.get(summary["tier"] or "", None),
    }


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise ApiError(422, "validation_error", "معرّف غير صالح.")


def _get_or_create_profile(session: Session, org_id: uuid.UUID) -> ClientProfile:
    profile = session.execute(
        select(ClientProfile).where(ClientProfile.organization_id == org_id)
    ).scalar_one_or_none()
    if profile is None:
        profile = ClientProfile(organization_id=org_id)
        session.add(profile)
        session.flush()
    return profile


# ── notes (append-only) ──────────────────────────────────────────────────
class NoteBody(BaseModel):
    kind: Literal["note", "call", "email", "escalation", "decision"] = "note"
    body: str = Field(min_length=1, max_length=8000)


@router.post("/v1/admin/clients/{org_id}/notes", status_code=201)
def add_note(org_id: str, body: NoteBody, auth=Depends(admin_authed)):
    session, claims = auth
    org = session.get(Organization, _uuid(org_id))
    if org is None:
        raise not_found()
    note = ClientNote(organization_id=org.id, author_user_id=claims.user_id,
                      kind=body.kind, body=body.body)
    session.add(note)
    session.flush()
    audit(session, claims.user_id, "client.note_added", "organization",
          str(org.id), {"kind": body.kind})
    return {"id": str(note.id)}


# ── lifecycle (SM-CLIENT) ────────────────────────────────────────────────
class LifecycleBody(BaseModel):
    state: Literal["onboarding", "active", "at_risk", "dormant", "churned"]
    pinned: bool = True  # pin by default: a manual decision should stick
    account_owner: Optional[str] = None
    tags: Optional[list[str]] = None


@router.post("/v1/admin/clients/{org_id}/lifecycle")
def set_lifecycle(org_id: str, body: LifecycleBody, auth=Depends(admin_authed)):
    session, claims = auth
    org = session.get(Organization, _uuid(org_id))
    if org is None:
        raise not_found()
    profile = _get_or_create_profile(session, org.id)
    previous = profile.lifecycle
    profile.lifecycle = body.state
    profile.lifecycle_pinned = body.pinned
    if body.account_owner is not None:
        profile.account_owner = body.account_owner
    if body.tags is not None:
        profile.tags = body.tags
    audit(session, claims.user_id, "client.lifecycle_changed", "organization",
          str(org.id), {"from": previous, "to": body.state, "pinned": body.pinned})
    return {"lifecycle": profile.lifecycle, "pinned": profile.lifecycle_pinned}


# ── tier override (audited, named write flow) ────────────────────────────
class TierBody(BaseModel):
    tier: str
    reason: str = Field(min_length=1, max_length=500)


@router.post("/v1/admin/clients/{org_id}/tier")
def change_tier(org_id: str, body: TierBody, auth=Depends(admin_authed)):
    session, claims = auth
    if body.tier not in TIER_MATRIX:
        raise ApiError(422, "validation_error",
                       f"tier يجب أن يكون أحد {sorted(TIER_MATRIX)}.")
    org = session.get(Organization, _uuid(org_id))
    if org is None:
        raise not_found()
    # ISO-02: admin_ro cannot write — the named 'system' flow can (0003
    # policy on subscriptions), and the action lands in the audit chain.
    set_system_context(session)
    sub = session.execute(
        select(Subscription).where(Subscription.organization_id == org.id)
    ).scalars().first()
    if sub is None:
        raise not_found()
    previous = sub.tier
    sub.tier = body.tier
    session.flush()
    set_admin_context(session)
    audit(session, claims.user_id, "client.tier_changed", "organization",
          str(org.id), {"from": previous, "to": body.tier, "reason": body.reason})
    return {"tier": sub.tier, "previous": previous}


# ── suspension kill-switch (audited) ─────────────────────────────────────
class SuspendBody(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


@router.post("/v1/admin/clients/{org_id}/suspend")
def suspend_client(org_id: str, body: SuspendBody, auth=Depends(admin_authed)):
    session, claims = auth
    org = session.get(Organization, _uuid(org_id))
    if org is None:
        raise not_found()
    org.suspended = True
    audit(session, claims.user_id, "client.suspended", "organization",
          str(org.id), {"reason": body.reason})
    return {"suspended": True}


@router.post("/v1/admin/clients/{org_id}/reactivate")
def reactivate_client(org_id: str, auth=Depends(admin_authed)):
    session, claims = auth
    org = session.get(Organization, _uuid(org_id))
    if org is None:
        raise not_found()
    org.suspended = False
    audit(session, claims.user_id, "client.reactivated", "organization", str(org.id))
    return {"suspended": False}


# ── read-only impersonation (ISO-04) ─────────────────────────────────────
@router.post("/v1/admin/clients/{org_id}/impersonate")
def impersonate(org_id: str, auth=Depends(admin_authed)):
    """Mint a 15-minute app-surface token bound to the client org, hard-wired
    read-only (claims_dep blocks every non-GET). Heavy audit."""
    session, claims = auth
    org = session.get(Organization, _uuid(org_id))
    if org is None:
        raise not_found()
    token = create_token(
        TokenClaims(claims.user_id, org.id, "owner", True,
                    surface="app", read_only=True, actor_id=claims.user_id),
        ttl=ADMIN_TOKEN_TTL,
    )
    audit(session, claims.user_id, "client.impersonated", "organization",
          str(org.id), {"read_only": True,
                        "ttl_seconds": int(ADMIN_TOKEN_TTL.total_seconds())})
    return {"token": token, "read_only": True, "organization_id": str(org.id),
            "expires_in_seconds": int(ADMIN_TOKEN_TTL.total_seconds())}


# ── audit access + chain verification ────────────────────────────────────
@router.get("/v1/admin/audit")
def list_audit(limit: int = 100, auth=Depends(admin_authed)):
    session, _ = auth
    rows = session.execute(
        select(AdminAuditLog).order_by(AdminAuditLog.sequence_number.desc())
        .limit(min(max(limit, 1), 500))
    ).scalars().all()
    return {"entries": [
        {"seq": r.sequence_number, "action": r.action,
         "actor_user_id": str(r.actor_user_id), "target_type": r.target_type,
         "target_id": r.target_id, "data": (r.payload or {}).get("data"),
         "content_hash": r.content_hash,
         "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in rows
    ]}


@router.get("/v1/admin/audit/verify")
def verify_audit_chain(auth=Depends(admin_authed)):
    session, _ = auth
    rows = session.execute(
        select(AdminAuditLog).order_by(AdminAuditLog.sequence_number)
    ).scalars().all()
    prev_hash = GENESIS
    for row in rows:
        if row.prev_hash != prev_hash:
            return {"valid": False, "broken_at": row.sequence_number,
                    "reason": "prev_hash mismatch"}
        if canonical_hash(row.payload or {}) != row.content_hash:
            return {"valid": False, "broken_at": row.sequence_number,
                    "reason": "content_hash mismatch"}
        prev_hash = row.content_hash
    return {"valid": True, "entries": len(rows)}


# ── system panel ─────────────────────────────────────────────────────────
@router.get("/v1/admin/system")
def system_status(request: Request, auth=Depends(admin_authed)):
    import os
    session, _ = auth
    catalog = request.app.state.catalog
    queue = {
        status: session.execute(
            select(func.count(Scan.id)).where(Scan.status == status)
        ).scalar() or 0
        for status in ("queued", "running", "completed", "failed")
    }
    return {
        "db": request.app.state.session_factory is not None,
        "rls_enforceable": request.app.state.rls_enforceable,
        "catalog": {"rules": len(catalog.rules),
                    "packs": [p.version for p in catalog.packs]},
        "scan_queue": queue,
        "rate_limit_per_min": int(os.environ.get("KONFORMOS_RATE_LIMIT_PER_MIN", "120")),
        "admin_token_ttl_seconds": int(ADMIN_TOKEN_TTL.total_seconds()),
    }
