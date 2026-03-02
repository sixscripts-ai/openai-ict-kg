from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import HTTPException, status

JWT_SECRET = os.getenv("ICT_KG_JWT_SECRET", "dev-secret")
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_MINUTES = int(os.getenv("ICT_KG_JWT_EXPIRES_MINUTES", "120"))
ALLOWED_ROLES = {"admin", "writer", "reader"}
AUTH_MODE = os.getenv("ICT_KG_AUTH_MODE", "local").lower()  # local|jwks
JWKS_URL = os.getenv("ICT_KG_JWKS_URL", "")
JWT_ISSUER = os.getenv("ICT_KG_JWT_ISSUER", "")
JWT_AUDIENCE = os.getenv("ICT_KG_JWT_AUDIENCE", "")


def create_access_token(subject: str, tenant_id: str, role: str = "writer") -> str:
    if role not in ALLOWED_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "tenant_id": tenant_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=JWT_EXPIRES_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_local(token: str) -> dict[str, Any]:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def _decode_jwks(token: str) -> dict[str, Any]:
    if not JWKS_URL:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="JWKS URL is not configured")
    jwk_client = jwt.PyJWKClient(JWKS_URL)
    signing_key = jwk_client.get_signing_key_from_jwt(token)
    kwargs: dict[str, Any] = {"algorithms": ["RS256"]}
    if JWT_AUDIENCE:
        kwargs["audience"] = JWT_AUDIENCE
    if JWT_ISSUER:
        kwargs["issuer"] = JWT_ISSUER
    return jwt.decode(token, signing_key.key, **kwargs)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = _decode_jwks(token) if AUTH_MODE == "jwks" else _decode_local(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    if "tenant_id" not in payload or "sub" not in payload or payload.get("role") not in ALLOWED_ROLES:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token claims")
    return payload


def role_allowed(role: str, required: str) -> bool:
    order = {"reader": 1, "writer": 2, "admin": 3}
    return order.get(role, 0) >= order.get(required, 0)
