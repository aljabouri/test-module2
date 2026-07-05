"""DB-backed platform routes — Tech Spec v1.0 §5 endpoints wired to PostgreSQL.

RBAC per Engineering Rules v1.1 §5: cross-org resources 404 (RBAC-03, mostly
free via RLS), sensitive roles need MFA (RBAC-02), tier gates per BR-BIL.
All errors use the ERR-00 envelope.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from konformos.api.security import (
    SENSITIVE_ROLES,
    AuthError,
    TokenClaims,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from konformos.billing.service import (
    TIER_MATRIX,
    InvalidSignature,
    SubscriptionPastDue,
    TierInsufficient,
    check_dossier_allowance,
    check_scan_allowance,
    get_subscription,
    handle_stripe_event,
    require_writable,
)
from konformos.core.hashing import ChainBroken
from konformos.db.models import (
    ComplianceProfileRow,
    Dossier as DossierRow,
    ExpertReview,
    Finding as FindingRow,
    KnowledgeEntryRow,
    LegalChangeEvent,
    LegalSource,
    Organization,
    Property,
    ReadinessResultRow,
    RulePackRow,
    Scan,
    StackFingerprint,
    Subscription,
    TimelineEventRow,
    User,
)
from konformos.db.repository import TimelineRepository
from konformos.db.session import set_org_context, set_system_context
from konformos.dossier.pdf import generate_pdf_dossier, verify_pdf_dossier
from konformos.evaluation.scoring import FindingInput, compute_readiness
from konformos.registry.resolver import resolve
from konformos.schemas import ComplianceProfile, RulePack

router = APIRouter()


# ── error plumbing (ERR-00) ──────────────────────────────────────────────
class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        self.status, self.code, self.message, self.details = status, code, message, details
        super().__init__(message)


def not_found() -> ApiError:
    return ApiError(404, "not_found", "غير موجود.")  # RBAC-03: no existence leak


# ── dependencies ─────────────────────────────────────────────────────────
def db_session(request: Request):
    factory = request.app.state.session_factory
    if factory is None:
        raise ApiError(503, "db_unavailable", "قاعدة البيانات غير مهيأة لهذه الجلسة.")
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def claims_dep(request: Request) -> TokenClaims:
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        raise ApiError(401, "auth_required", "مصادقة مطلوبة.")
    try:
        claims = decode_token(header.removeprefix("Bearer ").strip())
    except AuthError as exc:
        raise ApiError(401, exc.code, exc.message)
    # ISO-03: impersonation ("عرض كالعميل") is strictly read-only.
    if claims.read_only and request.method not in ("GET", "HEAD", "OPTIONS"):
        raise ApiError(403, "impersonation_read_only",
                       "جلسة الانتحال للقراءة فقط — لا كتابة باسم العميل.")
    return claims


def authed(session: Session = Depends(db_session),
           claims: TokenClaims = Depends(claims_dep)) -> tuple[Session, TokenClaims]:
    # ISO-01: admin-surface tokens NEVER work on the customer surface — the
    # two token populations are disjoint by audience, not by UI convention.
    if claims.surface != "app":
        raise ApiError(403, "wrong_surface",
                       "توكن لوحة التحكم لا يعمل على واجهة العميل (عزل الأسطح).")
    if claims.role in SENSITIVE_ROLES and not claims.mfa_enabled:
        raise ApiError(401, "mfa_required", "MFA إلزامي لهذا الدور (RBAC-02).")
    set_org_context(session, claims.organization_id)
    org = session.get(Organization, claims.organization_id)
    if org is not None and getattr(org, "suspended", False):
        raise ApiError(403, "org_suspended",
                       "الحساب موقوف — تواصل مع الدعم.")  # admin kill-switch
    return session, claims


def require_role(claims: TokenClaims, *roles: str) -> None:
    if claims.role not in roles:
        raise ApiError(403, "forbidden", "الدور لا يسمح بهذه العملية.")


def _guard_billing(callable_, *args):
    try:
        return callable_(*args)
    except TierInsufficient as exc:
        raise ApiError(403, "tier_insufficient", exc.message)
    except SubscriptionPastDue as exc:
        raise ApiError(403, "subscription_past_due", str(exc))


# ── auth ─────────────────────────────────────────────────────────────────
class RegisterBody(BaseModel):
    organization_name: str = Field(min_length=1)
    organization_type: Literal["merchant", "agency"] = "merchant"
    country: Optional[str] = None
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=12)  # VAL-USER-01


@router.post("/v1/auth/register", status_code=201)
def register(body: RegisterBody, session: Session = Depends(db_session)):
    org = Organization(type=body.organization_type, name=body.organization_name,
                       billing_email=body.email, country=body.country)
    session.add(org)
    session.flush()
    set_org_context(session, org.id)
    user = User(organization_id=org.id, email=body.email,
                hashed_password=hash_password(body.password), role="owner")
    session.add(user)
    session.add(Subscription(organization_id=org.id, tier="free_scan", status="active"))
    try:
        session.flush()
    except Exception:
        raise ApiError(422, "validation_error", "البريد مستخدم مسبقاً أو بيانات غير صالحة.")
    token = create_token(TokenClaims(user.id, org.id, user.role, user.mfa_enabled))
    return {"token": token, "organization_id": str(org.id)}


class LoginBody(BaseModel):
    email: str
    password: str
    totp_code: Optional[str] = None


@router.post("/v1/auth/login")
def login(body: LoginBody, session: Session = Depends(db_session)):
    set_system_context(session)  # narrow bypass: lookup by email pre-org
    user = session.execute(
        select(User).where(User.email == body.email)
    ).scalar_one_or_none()
    if user is None or not verify_password(user.hashed_password, body.password):
        raise ApiError(401, "auth_required", "بيانات دخول غير صحيحة.")
    if user.mfa_enabled and user.mfa_secret:
        from konformos.api.security import verify_totp
        if not body.totp_code or not verify_totp(user.mfa_secret, body.totp_code):
            raise ApiError(401, "mfa_required", "رمز TOTP مطلوب أو غير صحيح.")
    return {"token": create_token(
        TokenClaims(user.id, user.organization_id, user.role, user.mfa_enabled)
    )}


# ── org ──────────────────────────────────────────────────────────────────
@router.get("/v1/orgs/me")
def org_me(auth=Depends(authed)):
    session, claims = auth
    org = session.get(Organization, claims.organization_id)
    subscription = get_subscription(session, claims.organization_id)
    return {
        "id": str(org.id), "name": org.name, "type": org.type,
        "data_sharing_consent": org.data_sharing_consent,
        "subscription": {
            "tier": subscription.tier, "status": subscription.status,
            "capabilities": TIER_MATRIX[subscription.tier],
        } if subscription else None,
    }


class OrgPatch(BaseModel):
    name: Optional[str] = None
    data_sharing_consent: Optional[bool] = None


@router.patch("/v1/orgs/me")
def org_patch(body: OrgPatch, auth=Depends(authed)):
    session, claims = auth
    require_role(claims, "owner", "admin")
    org = session.get(Organization, claims.organization_id)
    if body.name is not None:
        org.name = body.name
    if body.data_sharing_consent is not None:
        org.data_sharing_consent = body.data_sharing_consent
    return {"ok": True}


# ── properties ───────────────────────────────────────────────────────────
class PropertyBody(BaseModel):
    url: str = Field(pattern=r"^https?://")
    label: Optional[str] = None


@router.post("/v1/properties", status_code=201)
def create_property(body: PropertyBody, auth=Depends(authed)):
    session, claims = auth
    require_role(claims, "owner", "member", "admin")
    subscription = get_subscription(session, claims.organization_id)
    caps = _guard_billing(require_writable, subscription)
    count = len(session.execute(select(Property.id)).scalars().all())
    if count >= caps["properties"]:
        raise ApiError(403, "tier_insufficient",
                       f"حد الـproperties لمستواك هو {caps['properties']}.")
    from konformos.scan.crawler import UnsafeUrl, assert_public_host
    try:
        assert_public_host(body.url)  # VAL-PROP-01
    except UnsafeUrl as exc:
        raise ApiError(422, "validation_error", f"عنوان غير مسموح: {exc}")
    prop = Property(organization_id=claims.organization_id, url=body.url, label=body.label)
    session.add(prop)
    session.flush()
    return {"id": str(prop.id)}


def _grant_scope(session: Session, claims: TokenClaims) -> set[uuid.UUID] | None:
    """BR-CUST-04: a member with explicit grants sees only those properties.
    Returns None = unrestricted (owner/admin, or member with no grants)."""
    if claims.role != "member":
        return None
    from konformos.db.models import PropertyGrant
    granted = set(session.execute(
        select(PropertyGrant.property_id)
        .where(PropertyGrant.user_id == claims.user_id)
    ).scalars().all())
    return granted or None


@router.get("/v1/properties")
def list_properties(auth=Depends(authed)):
    session, claims = auth
    rows = session.execute(select(Property)).scalars().all()
    scope = _grant_scope(session, claims)
    if scope is not None:
        rows = [p for p in rows if p.id in scope]
    return {"properties": [
        {"id": str(p.id), "url": p.url, "label": p.label,
         "readiness_current": p.readiness_current} for p in rows
    ]}


def _get_property(session: Session, property_id: str,
                  claims: TokenClaims | None = None) -> Property:
    try:
        pid = uuid.UUID(property_id)
    except ValueError:
        raise not_found()
    prop = session.get(Property, pid)  # RLS already scopes to the org
    if prop is None:
        raise not_found()
    if claims is not None:
        scope = _grant_scope(session, claims)
        if scope is not None and prop.id not in scope:
            raise not_found()  # RBAC-03: no existence leak within the org
    return prop


@router.get("/v1/properties/{property_id}")
def property_detail(property_id: str, auth=Depends(authed)):
    session, claims = auth
    prop = _get_property(session, property_id, claims)
    return {"id": str(prop.id), "url": prop.url, "label": prop.label,
            "readiness_current": prop.readiness_current,
            "current_fingerprint_id": str(prop.current_fingerprint_id)
            if prop.current_fingerprint_id else None}


@router.put("/v1/properties/{property_id}/compliance-profile")
def put_profile(property_id: str, body: dict, auth=Depends(authed)):
    session, claims = auth
    require_role(claims, "owner", "admin")
    prop = _get_property(session, property_id, claims)
    profile = ComplianceProfile.model_validate({**body, "property_id": str(prop.id)})
    row = ComplianceProfileRow(
        property_id=prop.id,
        selected_jurisdictions=profile.selected_jurisdictions,
        pack_binding=profile.pack_binding,
        pinned_versions=profile.pinned_versions,
        combination_mode=profile.combination_mode,
    )
    session.add(row)
    session.flush()
    prop.active_profile_id = row.id
    return {"ok": True}


@router.post("/v1/properties/{property_id}/fingerprint")
def run_fingerprint(property_id: str, auth=Depends(authed)):
    session, claims = auth
    prop = _get_property(session, property_id, claims)
    from konformos.fingerprint.engine import fingerprint_html
    from konformos.scan.crawler import UnsafeUrl, crawl

    try:
        crawled = crawl(prop.url, max_pages=1, max_depth=0)
    except UnsafeUrl as exc:
        raise ApiError(422, "validation_error", str(exc))
    if not crawled.pages:
        raise ApiError(422, "validation_error", "تعذر جلب الصفحة الجذر.")
    result = fingerprint_html(crawled.pages[0][1])

    previous = session.get(StackFingerprint, prop.current_fingerprint_id) \
        if prop.current_fingerprint_id else None
    drift = bool(previous and (previous.platform != result.platform
                               or previous.theme != result.theme))  # BR-FP-02
    row = StackFingerprint(
        property_id=prop.id, platform=result.platform,
        platform_version=result.platform_version, theme=result.theme,
        detection_confidence=result.detection_confidence,
        raw_signals={"signals": result.raw_signals},
    )
    session.add(row)
    session.flush()
    prop.current_fingerprint_id = row.id
    return {"platform": result.platform, "platform_display": result.platform_display,
            "platform_version": result.platform_version, "theme": result.theme,
            "detection_confidence": result.detection_confidence, "drift": drift}


@router.get("/v1/properties/{property_id}/timeline")
def property_timeline(property_id: str, auth=Depends(authed)):
    session, claims = auth
    prop = _get_property(session, property_id, claims)
    rows = session.execute(
        select(TimelineEventRow).where(TimelineEventRow.property_id == prop.id)
        .order_by(TimelineEventRow.sequence_number)
    ).scalars().all()
    return {"events": [
        {"sequence_number": r.sequence_number, "event_type": r.event_type,
         "payload": r.payload, "content_hash": r.content_hash,
         "prev_hash": r.prev_hash, "created_at": r.created_at.isoformat()}
        for r in rows
    ]}


# ── scans (202 + poll) ───────────────────────────────────────────────────
class ScanBody(BaseModel):
    input_type: Literal["url"] = "url"


@router.post("/v1/properties/{property_id}/scans", status_code=202)
def start_scan(property_id: str, body: ScanBody, request: Request, auth=Depends(authed)):
    session, claims = auth
    require_role(claims, "owner", "member", "admin")
    prop = _get_property(session, property_id, claims)
    subscription = get_subscription(session, claims.organization_id)
    caps = _guard_billing(check_scan_allowance, session, claims.organization_id, subscription)

    running = session.execute(
        select(Scan.id).where(
            Scan.property_id == prop.id, Scan.input_type == body.input_type,
            Scan.status.in_(("queued", "running")),
        )
    ).scalar_one_or_none()
    if running:  # EDGE-SCAN-01
        raise ApiError(409, "scan_already_running", "يوجد فحص جارٍ لهذا المتجر.",
                       {"scan_id": str(running)})

    scan = Scan(
        property_id=prop.id, organization_id=claims.organization_id,
        trigger="manual", input_type=body.input_type, status="queued",
        profile_snapshot={"input_ref": {"url": prop.url}, "page_cap": caps["scan_pages"]},
    )
    session.add(scan)
    session.flush()
    session.commit()  # visible to the worker thread before enqueue
    future = request.app.state.worker.enqueue(scan.id)
    request.app.state.scan_futures[str(scan.id)] = future
    return {"scan_id": str(scan.id), "status": "queued",
            "poll": f"/v1/scans/{scan.id}"}


def _get_scan(session: Session, claims: TokenClaims, scan_id: str) -> Scan:
    try:
        sid = uuid.UUID(scan_id)
    except ValueError:
        raise not_found()
    scan = session.get(Scan, sid)
    if scan is None:
        raise not_found()
    if claims.role not in ("expert_reviewer", "admin") \
            and scan.organization_id != claims.organization_id:
        raise not_found()  # RBAC-03
    return scan


@router.get("/v1/scans/{scan_id}")
def scan_status(scan_id: str, auth=Depends(authed)):
    session, claims = auth
    scan = _get_scan(session, claims, scan_id)
    readiness = None
    if scan.status == "completed":
        rows = session.execute(
            select(ReadinessResultRow).where(ReadinessResultRow.scan_id == scan.id)
        ).scalars().all()
        readiness = {r.jurisdiction: {
            "score": r.score, "computed_against_pack": r.computed_against_pack,
        } for r in rows}
    return {"id": str(scan.id), "status": scan.status,
            "engine_versions": scan.engine_versions, "readiness": readiness,
            "error": (scan.profile_snapshot or {}).get("error")}


@router.get("/v1/scans/{scan_id}/findings")
def scan_findings(scan_id: str, severity: Optional[str] = None, auth=Depends(authed)):
    session, claims = auth
    scan = _get_scan(session, claims, scan_id)
    query = select(FindingRow).where(FindingRow.scan_id == scan.id)
    if severity:
        query = query.where(FindingRow.severity == severity)
    rows = session.execute(query).scalars().all()
    return {"findings": [
        {"id": str(f.id), "rule_code": f.rule_code, "severity": f.severity,
         "location": f.location, "evidence": f.evidence,
         "source": f.source, "status": f.status} for f in rows
    ]}


class FindingPatch(BaseModel):
    status: Literal["fixed", "wont_fix", "false_positive", "open"]
    reason: Optional[str] = None


@router.patch("/v1/findings/{finding_id}")
def patch_finding(finding_id: str, body: FindingPatch, auth=Depends(authed)):
    session, claims = auth
    try:
        fid = uuid.UUID(finding_id)
    except ValueError:
        raise not_found()
    finding = session.get(FindingRow, fid)
    if finding is None:
        raise not_found()
    _get_scan(session, claims, str(finding.scan_id))  # org check
    # SM-FND transitions
    allowed = {("open", "fixed"), ("open", "wont_fix"), ("open", "false_positive"),
               ("fixed", "open")}
    if (finding.status, body.status) not in allowed:
        raise ApiError(409, "invalid_state_transition",
                       f"SM-FND: {finding.status} → {body.status} مرفوض.")
    if body.status == "wont_fix" and not body.reason:
        raise ApiError(422, "validation_error", "wont_fix يتطلب سبباً (SM-FND).")
    finding.status = body.status
    if body.status == "fixed":
        finding.evidence = {**(finding.evidence or {}), "manually_marked": True}  # BR-FIX-03
    if body.reason:
        finding.evidence = {**(finding.evidence or {}), "status_reason": body.reason}
    return {"ok": True}


# ── fix (BR-FIX-01 order, BR-FIX-02 labeling) ───────────────────────────
@router.get("/v1/findings/{finding_id}/fix")
def get_fix(finding_id: str, request: Request, auth=Depends(authed)):
    session, claims = auth
    try:
        fid = uuid.UUID(finding_id)
    except ValueError:
        raise not_found()
    finding = session.get(FindingRow, fid)
    if finding is None:
        raise not_found()
    scan = _get_scan(session, claims, str(finding.scan_id))

    # 1) knowledge graph first (BR-FIX-01)
    prop = session.get(Property, scan.property_id)
    signature = None
    if prop and prop.current_fingerprint_id:
        fingerprint = session.get(StackFingerprint, prop.current_fingerprint_id)
        theme_confidence = (fingerprint.detection_confidence or {}).get("theme", 0)
        if fingerprint and fingerprint.theme.get("name") and theme_confidence >= 0.7:
            from konformos.moat.knowledge import stack_signature
            signature = stack_signature(
                fingerprint.platform, fingerprint.theme["name"],
                fingerprint.platform_version,
            )
    if signature:
        entry = session.execute(
            select(KnowledgeEntryRow).where(
                KnowledgeEntryRow.stack_signature == signature,
                KnowledgeEntryRow.rule_code == finding.rule_code,
                KnowledgeEntryRow.occurrence_count >= 3,
                KnowledgeEntryRow.fix_success_rate >= 0.6,
            )
        ).scalar_one_or_none()
        if entry and entry.known_fix:
            return {"source": "knowledge_graph", "fix": entry.known_fix,
                    "fix_success_rate": entry.fix_success_rate,
                    "seen_in_stores": entry.occurrence_count,
                    "notice": "إصلاح مُختبَر من قاعدة المعرفة — راجعه مطوّر قبل التطبيق."}

    # 2) Claude API generation (BR-FIX-01 step 2) when credentials exist
    rule = request.app.state.catalog.rules.get(finding.rule_code)
    if rule is None:
        raise not_found()
    generator = getattr(request.app.state, "fix_generator", None)
    if generator is not None and generator.available:
        generated = generator.generate(
            rule_title=rule.title, rule_description=rule.description,
            severity=finding.severity,
            selector=(finding.location or {}).get("selector", ""),
            snippet=str((finding.evidence or {}).get("snippet", ""))[:1000],
            stack_hint=signature,
        )
        if generated:
            return {"source": "ai_generated", "fix": generated,
                    "notice": "اقتراح مولَّد آلياً عبر Claude — يتطلب مراجعة مطوّر قبل التطبيق (BR-FIX-02)."}

    # 3) template guidance from the catalog rule (final fallback)
    guidance = rule.description
    if not rule.automatable:
        guidance += " | إرشاد الخبير: " + rule.test_logic.expert_guidance
    return {
        "source": "manual_guidance",
        "fix": {"type": "manual_guidance", "explanation": guidance,
                "rule": rule.title, "location": finding.location},
        "notice": "اقتراح مولَّد آلياً — يتطلب مراجعة مطوّر قبل التطبيق (BR-FIX-02).",
    }


# ── dossiers (PDF + public verify) ───────────────────────────────────────
@router.post("/v1/properties/{property_id}/dossier", status_code=201)
def create_dossier_db(property_id: str, auth=Depends(authed)):
    session, claims = auth
    require_role(claims, "owner", "admin")
    prop = _get_property(session, property_id, claims)
    subscription = get_subscription(session, claims.organization_id)
    _guard_billing(check_dossier_allowance, session, claims.organization_id, subscription)

    scan = session.execute(
        select(Scan).where(Scan.property_id == prop.id, Scan.status == "completed")
        .order_by(Scan.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    if scan is None:
        raise ApiError(422, "validation_error",
                       "لا فحص مكتمل — افحص المتجر أولاً (EDGE-DS-01).")

    try:  # NFR-REL-02: full chain verification BEFORE sealing
        chain_length = TimelineRepository.verify_property_chain(session, prop.id)
    except ChainBroken as exc:
        raise ApiError(409, "chain_broken", f"سلسلة الإثبات مكسورة: {exc}")

    last_event = session.execute(
        select(TimelineEventRow).where(TimelineEventRow.property_id == prop.id)
        .order_by(TimelineEventRow.sequence_number.desc()).limit(1)
    ).scalar_one()
    readiness_rows = session.execute(
        select(ReadinessResultRow).where(ReadinessResultRow.scan_id == scan.id)
    ).scalars().all()
    readiness = {r.jurisdiction: r.score for r in readiness_rows}
    pack_versions = {r.jurisdiction: r.computed_against_pack for r in readiness_rows}
    gaps = [g for r in readiness_rows for g in (r.gaps or [])]
    gaps.sort(key=lambda g: g.get("penalty", 0), reverse=True)

    result = generate_pdf_dossier(
        jurisdictions=list(readiness),
        pack_versions=pack_versions,
        readiness=readiness,
        gaps=gaps,
        generated_at=datetime.now(timezone.utc).isoformat(),
        timeline_length=chain_length,
        timeline_head_hash=last_event.content_hash,
        engine_versions=scan.engine_versions or {},
        pages_scanned=(scan.profile_snapshot or {}).get("page_cap", 0),
        rules_evaluated=len({g["rule_code"] for g in gaps}) if gaps else 0,
        rules_manual_pending=0,
        scoring_version=(scan.profile_snapshot or {}).get("scoring_version", "1.0"),
    )
    row = DossierRow(
        property_id=prop.id, generated_at=datetime.now(timezone.utc),
        jurisdictions=sorted(readiness), pack_versions=pack_versions,
        readiness_snapshot=readiness,
        timeline_range={"to_sequence": last_event.sequence_number},
        pdf_url=str(result.pdf_path), dossier_hash=result.dossier_hash,
    )
    session.add(row)
    session.flush()
    return {"dossier_id": str(row.id), "dossier_hash": result.dossier_hash,
            "verify_url": f"/v1/verify/{result.dossier_hash}",
            "pdf": f"/v1/dossiers/{row.id}"}


@router.get("/v1/dossiers/{dossier_id}")
def download_dossier(dossier_id: str, auth=Depends(authed)):
    session, _ = auth
    try:
        did = uuid.UUID(dossier_id)
    except ValueError:
        raise not_found()
    row = session.get(DossierRow, did)
    if row is None or session.get(Property, row.property_id) is None:  # RLS org check
        raise not_found()
    return FileResponse(row.pdf_url, media_type="application/pdf",
                        filename=Path(row.pdf_url).name)


# ── billing webhook ──────────────────────────────────────────────────────
@router.post("/v1/billing/webhook")
async def stripe_webhook(request: Request, session: Session = Depends(db_session)):
    payload = await request.body()
    set_system_context(session)  # lookup by stripe customer id, no org yet
    try:
        outcome = handle_stripe_event(
            session, payload, request.headers.get("stripe-signature"))
    except InvalidSignature as exc:
        raise ApiError(401, "auth_required", f"توقيع Stripe غير صالح: {exc}")
    return {"received": outcome.event_id, "duplicate": outcome.duplicate,
            "applied": outcome.applied}


# ── legal curator portal ─────────────────────────────────────────────────
class SourceBody(BaseModel):
    jurisdiction: Literal["DE", "EU", "US"]
    name: str
    url: str
    source_type: str = "standard"
    extraction_method: str = "html"
    check_frequency: str = "weekly"


@router.post("/v1/legal/sources", status_code=201)
def create_source(body: SourceBody, auth=Depends(authed)):
    session, claims = auth
    require_role(claims, "legal_curator", "admin")
    row = LegalSource(**body.model_dump())
    session.add(row)
    session.flush()
    return {"id": str(row.id)}


class ChangeEventBody(BaseModel):
    source_id: str
    change_type: Literal["new_text", "version_bump", "deadline_change", "new_case"]
    llm_summary: str
    semantic_diff: Optional[dict] = None


@router.post("/v1/legal/change-events", status_code=201)
def create_change_event(body: ChangeEventBody, auth=Depends(authed)):
    session, claims = auth
    require_role(claims, "legal_curator", "admin")
    row = LegalChangeEvent(
        source_id=uuid.UUID(body.source_id),
        detected_at=datetime.now(timezone.utc),
        change_type=body.change_type, llm_summary=body.llm_summary,
        semantic_diff=body.semantic_diff, status="pending_review",
    )
    session.add(row)
    session.flush()
    return {"id": str(row.id)}


@router.get("/v1/legal/change-events")
def list_change_events(status: Optional[str] = None, auth=Depends(authed)):
    session, claims = auth
    require_role(claims, "legal_curator", "admin", "expert_reviewer")
    query = select(LegalChangeEvent)
    if status:
        query = query.where(LegalChangeEvent.status == status)
    rows = session.execute(query.order_by(LegalChangeEvent.detected_at)).scalars().all()
    return {"change_events": [
        {"id": str(r.id), "change_type": r.change_type, "status": r.status,
         "llm_summary": r.llm_summary, "detected_at": r.detected_at.isoformat()}
        for r in rows
    ]}


class ApproveBody(BaseModel):
    pack: dict  # full RulePack document, validated against the strict schema


@router.post("/v1/legal/change-events/{event_id}/approve")
def approve_change_event(event_id: str, body: ApproveBody, auth=Depends(authed)):
    session, claims = auth
    require_role(claims, "legal_curator", "admin")
    event = session.get(LegalChangeEvent, uuid.UUID(event_id))
    if event is None:
        raise not_found()
    if event.status != "pending_review":  # SM-LCE
        raise ApiError(409, "invalid_state_transition",
                       f"SM-LCE: {event.status} → approved مرفوض.")
    pack = RulePack.model_validate({
        **body.pack, "status": "draft",
        "source_change_events": [str(event.id)],
    })
    session.add(RulePackRow(
        jurisdiction=pack.jurisdiction, version=pack.version,
        effective_from=pack.effective_from, status="draft",
        legal_basis=pack.legal_basis,
        rule_refs=[r.model_dump() for r in pack.rule_refs],
        source_change_events=[event.id],
    ))
    event.status = "approved"
    session.flush()
    return {"pack_version": pack.version, "status": "draft"}


class RejectBody(BaseModel):
    reason: str = Field(min_length=1)  # SM-LCE: reason mandatory


@router.post("/v1/legal/change-events/{event_id}/reject")
def reject_change_event(event_id: str, body: RejectBody, auth=Depends(authed)):
    session, claims = auth
    require_role(claims, "legal_curator", "admin")
    event = session.get(LegalChangeEvent, uuid.UUID(event_id))
    if event is None:
        raise not_found()
    if event.status != "pending_review":
        raise ApiError(409, "invalid_state_transition", "SM-LCE: انتقال مرفوض.")
    event.status = "rejected"
    event.semantic_diff = {**(event.semantic_diff or {}), "reject_reason": body.reason}
    return {"ok": True}


@router.get("/v1/legal/rule-packs")
def list_packs_db(jurisdiction: Optional[str] = None, auth=Depends(authed)):
    session, _ = auth
    query = select(RulePackRow)
    if jurisdiction:
        query = query.where(RulePackRow.jurisdiction == jurisdiction)
    rows = session.execute(query.order_by(RulePackRow.version)).scalars().all()
    return {"rule_packs": [
        {"version": r.version, "jurisdiction": r.jurisdiction, "status": r.status,
         "effective_from": r.effective_from.isoformat(), "legal_basis": r.legal_basis,
         "rule_count": len(r.rule_refs or [])} for r in rows
    ]}


@router.post("/v1/legal/rule-packs/{version}/publish")
def publish_pack(version: str, request: Request, auth=Depends(authed)):
    """draft → active: sign (INV-RP-03), atomically supersede (INV-RP-02),
    then recompute latest-bound properties (BR-LEG-05/06)."""
    session, claims = auth
    require_role(claims, "legal_curator", "admin")
    pack = session.execute(
        select(RulePackRow).where(RulePackRow.version == version)
    ).scalar_one_or_none()
    if pack is None:
        raise not_found()
    if pack.status != "draft":  # SM-RP
        raise ApiError(409, "invalid_state_transition",
                       f"SM-RP: {pack.status} → active مرفوض.")

    current = session.execute(
        select(RulePackRow).where(
            RulePackRow.jurisdiction == pack.jurisdiction,
            RulePackRow.status == "active",
        )
    ).scalar_one_or_none()
    if current is not None:
        current.status = "superseded"
        # flush the supersede FIRST — the INV-RP-02 partial unique index is
        # not deferrable, so statement order inside the transaction matters
        session.flush()
    pack.status = "active"
    pack.signed_by = claims.user_id
    pack.signed_at = datetime.now(timezone.utc)
    session.flush()

    affected = _recompute_latest_bound(session, request.app.state.catalog, pack)
    return {"version": pack.version, "status": "active",
            "superseded": current.version if current else None,
            "recomputed_properties": affected}


def _recompute_latest_bound(session: Session, catalog, pack_row: RulePackRow) -> int:
    """BR-LEG-06: re-evaluate ONLY (last completed scan findings), no re-crawl.
    Org context per property comes from its scans (properties RLS stays strict)."""
    profiles = session.execute(select(ComplianceProfileRow)).scalars().all()
    affected = 0
    for profile_row in profiles:
        if pack_row.jurisdiction not in (profile_row.selected_jurisdictions or []):
            continue
        if profile_row.pack_binding != "latest":
            continue  # BR-LEG-07
        scan = session.execute(
            select(Scan).where(Scan.property_id == profile_row.property_id,
                               Scan.status == "completed")
            .order_by(Scan.created_at.desc()).limit(1)
        ).scalar_one_or_none()
        if scan is None:
            continue
        set_org_context(session, scan.organization_id)

        profile = ComplianceProfile(
            property_id=str(profile_row.property_id),
            selected_jurisdictions=list(profile_row.selected_jurisdictions),
            pack_binding="latest", combination_mode=profile_row.combination_mode,
        )
        from konformos.scan.worker import ScanWorker
        packs = ScanWorker._db_packs(None, session)  # type: ignore[arg-type]
        ruleset = resolve(profile, date.today(), packs)
        findings = session.execute(
            select(FindingRow).where(FindingRow.scan_id == scan.id)
        ).scalars().all()
        inputs = [FindingInput(f.rule_code, f.severity, f.status,
                               (f.location or {}).get("page", "/")) for f in findings]
        pages = max(1, (scan.profile_snapshot or {}).get("page_cap", 1))
        results = compute_readiness(ruleset, catalog.rules, inputs, pages)
        scores = {}
        for label, result in results.items():
            scores[label] = result.score
            session.add(ReadinessResultRow(
                scan_id=scan.id, jurisdiction=label, score=result.score,
                gaps=[vars(g) for g in result.gaps],
                computed_against_pack=result.computed_against_pack,
            ))
        prop = session.get(Property, profile_row.property_id)
        if prop is not None:
            prop.readiness_current = scores
        TimelineRepository.append(session, profile_row.property_id,
                                  "legal_update_applied", {
                                      "pack": pack_row.version, "scores": scores,
                                  })
        affected += 1
    return affected


# ── expert (Prüfstelle) portal ───────────────────────────────────────────
@router.get("/v1/expert/review-queue")
def review_queue(auth=Depends(authed)):
    session, claims = auth
    require_role(claims, "expert_reviewer", "admin")
    signed = select(ExpertReview.scan_id).where(ExpertReview.status == "signed")
    rows = session.execute(
        select(Scan).where(Scan.status == "completed", ~Scan.id.in_(signed))
        .order_by(Scan.created_at)
    ).scalars().all()
    return {"queue": [{"scan_id": str(s.id), "created_at": s.created_at.isoformat()}
                      for s in rows]}


class ManualFindingBody(BaseModel):
    rule_code: str
    severity: Literal["critical", "serious", "moderate", "minor"]
    location: dict
    evidence: Optional[dict] = None


@router.post("/v1/expert/scans/{scan_id}/manual-findings", status_code=201)
def add_manual_findings(scan_id: str, body: list[ManualFindingBody], auth=Depends(authed)):
    session, claims = auth
    require_role(claims, "expert_reviewer", "admin")
    scan = session.get(Scan, uuid.UUID(scan_id))
    if scan is None or scan.status != "completed":
        raise not_found()
    review = session.execute(
        select(ExpertReview).where(ExpertReview.scan_id == scan.id,
                                   ExpertReview.reviewer_id == claims.user_id)
    ).scalar_one_or_none()
    if review is None:
        review = ExpertReview(scan_id=scan.id, property_id=scan.property_id,
                              reviewer_id=claims.user_id, status="in_progress")
        session.add(review)
    elif review.status == "signed":  # INV-ER-01
        raise ApiError(409, "invalid_state_transition", "SM-ER: المراجعة موقَّعة.")
    ids = []
    for item in body:
        finding = FindingRow(scan_id=scan.id, rule_code=item.rule_code,
                             severity=item.severity, location=item.location,
                             evidence=item.evidence, source="manual_expert")
        session.add(finding)
        session.flush()
        ids.append(finding.id)
    review.manual_findings = (review.manual_findings or []) + ids
    return {"added": len(ids)}


class SignBody(BaseModel):
    signature: dict  # qualification + date etc.
    insurance_ref: Optional[str] = None


@router.post("/v1/expert/scans/{scan_id}/sign")
def sign_review(scan_id: str, body: SignBody, auth=Depends(authed)):
    session, claims = auth
    require_role(claims, "expert_reviewer", "admin")
    scan = session.get(Scan, uuid.UUID(scan_id))
    if scan is None:
        raise not_found()
    review = session.execute(
        select(ExpertReview).where(ExpertReview.scan_id == scan.id,
                                   ExpertReview.reviewer_id == claims.user_id)
    ).scalar_one_or_none()
    if review is None:
        review = ExpertReview(scan_id=scan.id, property_id=scan.property_id,
                              reviewer_id=claims.user_id, status="in_progress")
        session.add(review)
        session.flush()
    if review.status == "signed":
        raise ApiError(409, "invalid_state_transition", "SM-ER: موقَّعة مسبقاً.")
    review.signature = {**body.signature, "signed_at":
                        datetime.now(timezone.utc).isoformat()}
    review.insurance_ref = body.insurance_ref
    review.status = "signed"
    # timeline write needs the property's org context (RBAC-01 engagement scope)
    set_org_context(session, scan.organization_id)
    TimelineRepository.append(session, scan.property_id, "expert_review_signed", {
        "scan_id": str(scan.id), "reviewer": str(claims.user_id),
        "manual_findings": len(review.manual_findings or []),
        "insurance_ref": body.insurance_ref,
    })
    return {"status": "signed"}
