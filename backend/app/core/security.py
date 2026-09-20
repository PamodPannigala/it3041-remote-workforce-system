import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
import jwt
from pwdlib import PasswordHash

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env", encoding="utf-8-sig")

password_hasher = PasswordHash.recommended()

# Pre-computed dummy hash for timing mitigation against non-existent users
DUMMY_PASSWORD_HASH = password_hasher.hash("dummy-password-for-timing-mitigation-only")

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "remote-workforce-system"
JWT_AUDIENCE = "remote-workforce-users"
ACCESS_TOKEN_EXPIRE_MINUTES = 15


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hasher.verify(password, hashed_password)


def get_jwt_secret_key() -> str:
    key = os.getenv("JWT_SECRET_KEY")
    if not key or not key.strip():
        raise RuntimeError("Missing JWT signing configuration: JWT_SECRET_KEY is not set")
    return key


def create_access_token(user_id: str, secret_key: str | None = None) -> tuple[str, int]:
    if secret_key is None:
        secret_key = get_jwt_secret_key()
    now = datetime.now(timezone.utc)
    expires_in = ACCESS_TOKEN_EXPIRE_MINUTES * 60
    expire = now + timedelta(seconds=expires_in)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
    }
    token = jwt.encode(payload, secret_key, algorithm=JWT_ALGORITHM)
    return token, expires_in


def decode_access_token(token: str, secret_key: str | None = None) -> dict:
    if secret_key is None:
        secret_key = get_jwt_secret_key()
    payload = jwt.decode(
        token,
        secret_key,
        algorithms=[JWT_ALGORITHM],
        issuer=JWT_ISSUER,
        audience=JWT_AUDIENCE,
        options={
            "require": ["sub", "iat", "exp", "iss", "aud"],
            "verify_signature": True,
            "verify_exp": True,
            "verify_iat": True,
            "verify_iss": True,
            "verify_aud": True,
        },
    )
    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub.strip():
        raise jwt.InvalidTokenError("Invalid token subject")
    return payload
