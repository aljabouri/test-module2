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
SENSITIVE_ROLES = {"expert_reviewer", "legal_curator", "admin"}
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


def create_token(claims: TokenClaims) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(claims.user_id),
            "org": str(claims.organization_id),
            "role": claims.role,
            "mfa": claims.mfa_enabled,
            "iat": now,
            "exp": now + TOKEN_TTL,
        },
        jwt_secret(),
        algorithm="HS256",
    )


class AuthError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def decode_token(token: str) -> TokenClaims:
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("token_expired", "انتهت صلاحية الجلسة.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("auth_required", "اعتماد غير صالح.") from exc
    return TokenClaims(
        user_id=uuid.UUID(payload["sub"]),
        organization_id=uuid.UUID(payload["org"]),
        role=payload["role"],
        mfa_enabled=bool(payload.get("mfa", False)),
    )
