"""Auth primitives — Engineering Rules v1.1 §7.3 / VAL-USER-01 / RBAC-02.

Argon2id for passwords, short-lived HS256 JWT. Sensitive roles (expert_reviewer,
legal_curator, admin) are refused at login until MFA is enabled on the account
(RBAC-02: the role is suspended, not the check skipped).
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()  # argon2id by default

TOKEN_TTL = timedelta(hours=1)
ADMIN_TOKEN_TTL = timedelta(minutes=15)  # ISO-01: elevated surface is short-lived
SENSITIVE_ROLES = {"expert_reviewer", "legal_curator", "admin"}
ADMIN_ROLES = SENSITIVE_ROLES  # roles allowed onto the /admin surface
MIN_PASSWORD_LENGTH = 12  # VAL-USER-01
PUBLIC_REGISTER_ROLES = {"owner"}  # VAL-USER-01: no self-service elevated roles


def jwt_secret() -> str:
    return os.environ.get("KONFORMOS_JWT_SECRET", "dev-secret-change-in-production")


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError("VAL-USER-01: password must be at least 12 characters")
    return _hasher.hash(password)


def verify_password(hashed: str, password: str) -> bool:
    try:
        return _hasher.verify(hashed, password)
    except VerifyMismatchError:
        return False


@dataclass(frozen=True)
class TokenClaims:
    user_id: uuid.UUID
    organization_id: uuid.UUID
    role: str
    mfa_enabled: bool
    # ── surface isolation (ISO-01..03) ────────────────────────────────
    # Two disjoint token populations: "app" (customer workspace) and
    # "admin" (control plane). Admin endpoints ONLY accept aud=admin;
    # customer endpoints REJECT aud=admin — no accidental crossover.
    surface: str = "app"
    read_only: bool = False           # impersonation tokens can never write
    actor_id: uuid.UUID | None = None  # the real admin behind an impersonation


def create_token(claims: TokenClaims, ttl: timedelta | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(claims.user_id),
        "org": str(claims.organization_id),
        "role": claims.role,
        "mfa": claims.mfa_enabled,
        "aud": claims.surface,
        "iat": now,
        "exp": now + (ttl or (ADMIN_TOKEN_TTL if claims.surface == "admin"
                              else TOKEN_TTL)),
    }
    if claims.read_only:
        payload["ro"] = True
    if claims.actor_id is not None:
        payload["act"] = str(claims.actor_id)
    return jwt.encode(payload, jwt_secret(), algorithm="HS256")


class AuthError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


# ── TOTP (RFC 6238, stdlib only) — RBAC-02 ───────────────────────────────
import base64
import hmac as hmac_module
import hashlib
import secrets as py_secrets
import struct
import time


def generate_totp_secret() -> str:
    return base64.b32encode(py_secrets.token_bytes(20)).decode()


def totp_code(secret: str, at: float | None = None,
              step: int = 30, digits: int = 6) -> str:
    counter = int((at if at is not None else time.time()) // step)
    key = base64.b32decode(secret)
    digest = hmac_module.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0xF
    value = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF)
    return f"{value % 10 ** digits:0{digits}d}"


def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    now = time.time()
    return any(
        hmac_module.compare_digest(totp_code(secret, now + drift * 30), code)
        for drift in range(-window, window + 1)
    )


def decode_token(token: str) -> TokenClaims:
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=["HS256"],
                             options={"verify_aud": False})
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("token_expired", "انتهت صلاحية الجلسة.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("auth_required", "اعتماد غير صالح.") from exc
    return TokenClaims(
        user_id=uuid.UUID(payload["sub"]),
        organization_id=uuid.UUID(payload["org"]),
        role=payload["role"],
        mfa_enabled=bool(payload.get("mfa", False)),
        surface=payload.get("aud", "app"),  # legacy tokens are app-surface
        read_only=bool(payload.get("ro", False)),
        actor_id=uuid.UUID(payload["act"]) if payload.get("act") else None,
    )
