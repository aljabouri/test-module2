"""Growth routes: TOTP MFA (RBAC-02), accessibility statement (§ Erklärung),
deploy webhooks (Flow C), agency property grants (BR-CUST-04), outbound
webhook endpoints, notifications, code-input scans (theme/plugin/pdf/design
system — BR-BIL code_inputs gate), and the scheduler tick."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from konformos.api.routes_db import (
    ApiError,
    _get_property,
    _guard_billing,
    authed,
    claims_dep,
    db_session,
    not_found,
    require_role,
)
from konformos.api.security import (
    TokenClaims,
    create_token,
    generate_totp_secret,
    verify_totp,
)
from konformos.billing.service import (
    check_scan_allowance,
    get_subscription,
    require_writable,
)
from konformos.db.models import (
    DeployToken,
    Notification,
    Property,
    PropertyGrant,
    ReadinessResultRow,
    Scan,
    User,
    WebhookEndpoint,
)
from konformos.db.repository import TimelineRepository
from konformos.db.session import set_org_context
from konformos.dossier.pdf import storage_dir

router = APIRouter()


# ── MFA (TOTP) — RBAC-02 ─────────────────────────────────────────────────
# These two endpoints intentionally bypass the sensitive-role MFA gate:
# they ARE the enrollment path.
@router.post("/v1/auth/mfa/setup")
def mfa_setup(session: Session = Depends(db_session),
              claims: TokenClaims = Depends(claims_dep)):
    set_org_context(session, claims.organization_id)
    user = session.get(User, claims.user_id)
    if user is None:
        raise not_found()
    user.mfa_secret = generate_totp_secret()
    user.mfa_enabled = False  # enabled only after a verified code
    return {"secret": user.mfa_secret,
            "otpauth": f"otpauth://totp/KonformOS:{user.email}"
                       f"?secret={user.mfa_secret}&issuer=KonformOS"}


class MfaVerifyBody(BaseModel):
    code: str = Field(min_length=6, max_length=8)


@router.post("/v1/auth/mfa/verify")
def mfa_verify(body: MfaVerifyBody, session: Session = Depends(db_session),
               claims: TokenClaims = Depends(claims_dep)):
    set_org_context(session, claims.organization_id)
    user = session.get(User, claims.user_id)
    if user is None or not user.mfa_secret:
        raise ApiError(422, "validation_error", "شغّل /mfa/setup أولاً.")
    if not verify_totp(user.mfa_secret, body.code):
        raise ApiError(401, "auth_required", "رمز TOTP غير صحيح.")
    user.mfa_enabled = True
    token = create_token(TokenClaims(user.id, user.organization_id,
                                     user.role, True))
    return {"mfa_enabled": True, "token": token}


# ── Accessibility statement (v1.0 §5.4) ──────────────────────────────────
@router.post("/v1/properties/{property_id}/statement")
def generate_statement(property_id: str, auth=Depends(authed)):
    session, claims = auth
    require_role(claims, "owner", "admin")
    prop = _get_property(session, property_id, claims)
    scan = session.execute(
        select(Scan).where(Scan.property_id == prop.id, Scan.status == "completed")
        .order_by(Scan.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    if scan is None:
        raise ApiError(422, "validation_error", "لا فحص مكتمل بعد (EDGE-DS-01).")
    readiness = session.execute(
        select(ReadinessResultRow).where(ReadinessResultRow.scan_id == scan.id)
    ).scalars().all()
    generated_at = datetime.now(timezone.utc).date().isoformat()
    lines = [
        "# Erklärung zur Barrierefreiheit — بيان الوصولية",
        "",
        f"يسري هذا البيان على: {prop.url}",
        f"تاريخ الإعداد: {generated_at}",
        "",
        "## حالة التوافق",
    ]
    for row in readiness:
        lines.append(
            f"- {row.jurisdiction}: تقييم آلي {row.score}/100 مقابل الحزمة "
            f"{row.computed_against_pack}."
        )
    lines += [
        "",
        "## المنهجية والحدود",
        "أُعد هذا البيان بالاستناد إلى تقييم آلي عبر KonformOS "
        "(Assessment/Nachweis der Bemühungen — ليس اعتماداً رسمياً). "
        "القواعد التي تتطلب تحققاً بشرياً مُعلَّمة في تقرير الجاهزية.",
        "",
        "## آلية الملاحظات",
        "إن واجهت حاجزاً في الوصول لهذا الموقع فراسلنا وسنعالجه ضمن مهلة معقولة.",
    ]
    text = "\n".join(lines)
    TimelineRepository.append(session, prop.id, "statement_generated", {
        "scan_id": str(scan.id), "generated_at": generated_at,
    })
    return {"statement": text}


# ── Deploy webhooks (Flow C) ─────────────────────────────────────────────
@router.post("/v1/properties/{property_id}/deploy-token", status_code=201)
def create_deploy_token(property_id: str, auth=Depends(authed)):
    session, claims = auth
    require_role(claims, "owner", "admin")
    prop = _get_property(session, property_id, claims)
    token = f"dk_{secrets.token_urlsafe(24)}"
    session.add(DeployToken(token=token, property_id=prop.id,
                            organization_id=claims.organization_id))
    return {"deploy_token": token,
            "hook_url": f"/v1/deploy/{token}"}


@router.post("/v1/deploy/{token}", status_code=202)
def deploy_hook(token: str, request: Request,
                session: Session = Depends(db_session)):
    """Public hook: CI calls it after deploy → drift re-scan (Flow C)."""
    row = session.get(DeployToken, token)
    if row is None:
        raise not_found()
    set_org_context(session, row.organization_id)
    subscription = get_subscription(session, row.organization_id)
    caps = _guard_billing(check_scan_allowance, session,
                          row.organization_id, subscription)
    prop = session.get(Property, row.property_id)
    if prop is None:
        raise not_found()
    running = session.execute(
        select(Scan.id).where(Scan.property_id == prop.id,
                              Scan.status.in_(("queued", "running")))
    ).scalar_one_or_none()
    if running:
        return {"scan_id": str(running), "status": "already_running"}
    scan = Scan(property_id=prop.id, organization_id=row.organization_id,
                trigger="deploy_webhook", input_type="url", status="queued",
                profile_snapshot={"input_ref": {"url": prop.url},
                                  "page_cap": caps["scan_pages"]})
    session.add(scan)
    session.flush()
    session.commit()
    future = request.app.state.worker.enqueue(scan.id)
    request.app.state.scan_futures[str(scan.id)] = future
    return {"scan_id": str(scan.id), "status": "queued"}


# ── Agency seats (BR-CUST-04) ────────────────────────────────────────────
class GrantBody(BaseModel):
    user_id: str


@router.post("/v1/properties/{property_id}/grants", status_code=201)
def grant_property(property_id: str, body: GrantBody, auth=Depends(authed)):
    session, claims = auth
    require_role(claims, "owner", "admin")
    prop = _get_property(session, property_id, claims)
    member = session.get(User, uuid.UUID(body.user_id))
    if member is None or member.organization_id != claims.organization_id:
        raise not_found()
    session.merge(PropertyGrant(user_id=member.id, property_id=prop.id))
    return {"ok": True}


# ── Outbound webhook endpoints (dev+ tiers) ──────────────────────────────
class WebhookBody(BaseModel):
    url: str = Field(pattern=r"^https?://")


@router.post("/v1/webhook-endpoints", status_code=201)
def create_webhook_endpoint(body: WebhookBody, auth=Depends(authed)):
    session, claims = auth
    require_role(claims, "owner", "admin")
    _guard_billing(require_writable, get_subscription(session, claims.organization_id))
    secret = f"whsec_{secrets.token_urlsafe(24)}"
    endpoint = WebhookEndpoint(organization_id=claims.organization_id,
                               url=body.url, secret=secret)
    session.add(endpoint)
    session.flush()
    return {"id": str(endpoint.id), "secret": secret}  # secret shown once


@router.get("/v1/notifications")
def list_notifications(auth=Depends(authed)):
    session, claims = auth
    rows = session.execute(
        select(Notification)
        .where(Notification.organization_id == claims.organization_id)
        .order_by(Notification.created_at.desc()).limit(100)
    ).scalars().all()
    return {"notifications": [
        {"id": str(n.id), "type": n.type, "payload": n.payload,
         "created_at": n.created_at.isoformat()} for n in rows
    ]}


# ── Code-input scans: theme/plugin/pdf upload + design system ────────────
@router.post("/v1/properties/{property_id}/scans/upload", status_code=202)
async def upload_scan(property_id: str, request: Request,
                      input_type: Literal["theme", "plugin", "pdf"] = Form(...),
                      file: UploadFile = File(...),
                      auth=Depends(authed)):
    session, claims = auth
    prop = _get_property(session, property_id, claims)
    subscription = get_subscription(session, claims.organization_id)
    caps = _guard_billing(check_scan_allowance, session,
                          claims.organization_id, subscription)
    if not caps["code_inputs"]:  # BR-BIL: dev/agency only
        raise ApiError(403, "tier_insufficient",
                       "مدخلات Theme/Plugin/PDF تتطلب مستوى dev أو أعلى.")
    data = await file.read()
    limit = 50_000_000 if input_type == "pdf" else 100_000_000  # NFR-SIZE-01
    if len(data) > limit:
        raise ApiError(413, "validation_error", "الملف يتجاوز حد الحجم.")
    path = storage_dir() / f"upload-{uuid.uuid4().hex}-{file.filename}"
    path.write_bytes(data)
    scan = Scan(property_id=prop.id, organization_id=claims.organization_id,
                trigger="manual", input_type=input_type, status="queued",
                profile_snapshot={"input_ref": {"file": str(path),
                                                "name": file.filename}})
    session.add(scan)
    session.flush()
    session.commit()
    future = request.app.state.worker.enqueue(scan.id)
    request.app.state.scan_futures[str(scan.id)] = future
    return {"scan_id": str(scan.id), "status": "queued",
            "poll": f"/v1/scans/{scan.id}"}


class ComponentBody(BaseModel):
    name: str
    html: str


class DesignSystemBody(BaseModel):
    components: list[ComponentBody] = Field(min_length=1, max_length=100)


@router.post("/v1/properties/{property_id}/scans/design-system", status_code=202)
def design_system_scan(property_id: str, body: DesignSystemBody,
                       request: Request, auth=Depends(authed)):
    session, claims = auth
    prop = _get_property(session, property_id, claims)
    subscription = get_subscription(session, claims.organization_id)
    caps = _guard_billing(check_scan_allowance, session,
                          claims.organization_id, subscription)
    if not caps["code_inputs"]:
        raise ApiError(403, "tier_insufficient",
                       "مدخل Design System يتطلب مستوى dev أو أعلى.")
    scan = Scan(property_id=prop.id, organization_id=claims.organization_id,
                trigger="manual", input_type="design_system", status="queued",
                profile_snapshot={"input_ref": {
                    "components": [c.model_dump() for c in body.components]}})
    session.add(scan)
    session.flush()
    session.commit()
    future = request.app.state.worker.enqueue(scan.id)
    request.app.state.scan_futures[str(scan.id)] = future
    return {"scan_id": str(scan.id), "status": "queued",
            "poll": f"/v1/scans/{scan.id}"}


# ── Scheduler (admin) ────────────────────────────────────────────────────
@router.post("/v1/internal/scheduler/tick")
def scheduler_tick(request: Request, auth=Depends(authed)):
    session, claims = auth
    require_role(claims, "admin")
    from konformos.scan.scheduler import tick
    return {"enqueued": tick(session, request.app.state.worker)}
