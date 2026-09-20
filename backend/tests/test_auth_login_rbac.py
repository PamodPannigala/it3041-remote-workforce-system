from datetime import datetime, timedelta, timezone
from bson import ObjectId
from fastapi.testclient import TestClient
import jwt
import pytest

from main import app
from security import (
    JWT_ALGORITHM,
    JWT_AUDIENCE,
    JWT_ISSUER,
    hash_password,
)
from tests.conftest import TEST_JWT_SECRET


def create_test_user(
    fake_db,
    email: str = "test@example.com",
    password: str = "ValidPassword12345!",
    role: str = "employee",
    is_active: bool = True,
    name: str = "Test User",
) -> dict:
    user_doc = {
        "_id": ObjectId(),
        "name": name,
        "email": email.lower(),
        "password_hash": hash_password(password),
        "role": role,
        "is_active": is_active,
        "created_at": datetime.now(timezone.utc),
    }
    fake_db["users"].docs.append(user_doc)
    return user_doc


def test_successful_login_and_auth_me(test_setup):
    client, fake_db = test_setup
    password = "CorrectSecretPassword123!"
    user = create_test_user(fake_db, email="login.user@example.com", password=password)

    # Login
    response = client.post(
        "/auth/login",
        json={"email": "login.user@example.com", "password": password},
    )
    assert response.status_code == 200
    assert response.headers.get("Cache-Control") == "no-store"
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 900

    token = data["access_token"]

    # Verify /auth/me
    me_resp = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["id"] == str(user["_id"])
    assert me_data["email"] == "login.user@example.com"
    assert me_data["name"] == user["name"]
    assert me_data["role"] == "employee"
    assert "password" not in me_data
    assert "password_hash" not in me_data


def test_login_wrong_password(test_setup):
    client, fake_db = test_setup
    create_test_user(fake_db, email="wrongpass@example.com", password="CorrectPassword123!")

    response = client.post(
        "/auth/login",
        json={"email": "wrongpass@example.com", "password": "WrongPassword1234!"},
    )
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["detail"] == "Invalid email or password"


def test_login_unknown_user(test_setup):
    client, fake_db = test_setup
    response = client.post(
        "/auth/login",
        json={"email": "nonexistent@example.com", "password": "RandomPassword123!"},
    )
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["detail"] == "Invalid email or password"


def test_login_inactive_user(test_setup):
    client, fake_db = test_setup
    create_test_user(
        fake_db,
        email="inactive@example.com",
        password="ValidPassword123!",
        is_active=False,
    )

    response = client.post(
        "/auth/login",
        json={"email": "inactive@example.com", "password": "ValidPassword123!",},
    )
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["detail"] == "Invalid email or password"


def test_missing_and_malformed_auth_header(test_setup):
    client, fake_db = test_setup

    # Missing header
    res1 = client.get("/auth/me")
    assert res1.status_code == 401
    assert res1.headers.get("WWW-Authenticate") == "Bearer"

    # Non-Bearer scheme
    res2 = client.get("/auth/me", headers={"Authorization": "Basic 123456"})
    assert res2.status_code == 401
    assert res2.headers.get("WWW-Authenticate") == "Bearer"

    # Malformed token
    res3 = client.get("/auth/me", headers={"Authorization": "Bearer not-a-jwt-token"})
    assert res3.status_code == 401
    assert res3.headers.get("WWW-Authenticate") == "Bearer"


def test_tampered_and_expired_tokens(test_setup):
    client, fake_db = test_setup
    user = create_test_user(fake_db)
    now = datetime.now(timezone.utc)

    # Valid token structure signed with different secret
    tampered_token = jwt.encode(
        {
            "sub": str(user["_id"]),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=15)).timestamp()),
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
        },
        "wrong-secret-key-that-is-at-least-32-bytes-long!",
        algorithm=JWT_ALGORITHM,
    )
    res_tampered = client.get("/auth/me", headers={"Authorization": f"Bearer {tampered_token}"})
    assert res_tampered.status_code == 401
    assert res_tampered.headers.get("WWW-Authenticate") == "Bearer"

    # Expired token
    expired_token = jwt.encode(
        {
            "sub": str(user["_id"]),
            "iat": int((now - timedelta(minutes=30)).timestamp()),
            "exp": int((now - timedelta(minutes=15)).timestamp()),
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
        },
        TEST_JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    res_expired = client.get("/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert res_expired.status_code == 401
    assert res_expired.headers.get("WWW-Authenticate") == "Bearer"
    assert "expired" in res_expired.json()["detail"].lower()


def test_invalid_claims_and_algorithms(test_setup):
    client, fake_db = test_setup
    user = create_test_user(fake_db)
    now = datetime.now(timezone.utc)

    # Wrong issuer
    token_wrong_iss = jwt.encode(
        {
            "sub": str(user["_id"]),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=15)).timestamp()),
            "iss": "wrong-issuer",
            "aud": JWT_AUDIENCE,
        },
        TEST_JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    res_iss = client.get("/auth/me", headers={"Authorization": f"Bearer {token_wrong_iss}"})
    assert res_iss.status_code == 401

    # Wrong audience
    token_wrong_aud = jwt.encode(
        {
            "sub": str(user["_id"]),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=15)).timestamp()),
            "iss": JWT_ISSUER,
            "aud": "wrong-audience",
        },
        TEST_JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    res_aud = client.get("/auth/me", headers={"Authorization": f"Bearer {token_wrong_aud}"})
    assert res_aud.status_code == 401

    # Missing exp
    token_no_exp = jwt.encode(
        {
            "sub": str(user["_id"]),
            "iat": int(now.timestamp()),
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
        },
        TEST_JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    res_no_exp = client.get("/auth/me", headers={"Authorization": f"Bearer {token_no_exp}"})
    assert res_no_exp.status_code == 401

    # Missing sub
    token_no_sub = jwt.encode(
        {
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=15)).timestamp()),
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
        },
        TEST_JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    res_no_sub = client.get("/auth/me", headers={"Authorization": f"Bearer {token_no_sub}"})
    assert res_no_sub.status_code == 401

    # Malformed sub (not a valid ObjectId)
    token_bad_sub = jwt.encode(
        {
            "sub": "not-a-valid-object-id",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=15)).timestamp()),
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
        },
        TEST_JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    res_bad_sub = client.get("/auth/me", headers={"Authorization": f"Bearer {token_bad_sub}"})
    assert res_bad_sub.status_code == 401

    # Disallowed algorithm (e.g. HS384 instead of fixed HS256)
    token_hs384 = jwt.encode(
        {
            "sub": str(user["_id"]),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=15)).timestamp()),
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
        },
        TEST_JWT_SECRET,
        algorithm="HS384",
    )
    res_hs384 = client.get("/auth/me", headers={"Authorization": f"Bearer {token_hs384}"})
    assert res_hs384.status_code == 401


def test_role_based_access_control(test_setup):
    client, fake_db = test_setup

    emp_user = create_test_user(fake_db, email="emp@example.com", role="employee")
    mgr_user = create_test_user(fake_db, email="mgr@example.com", role="manager")
    adm_user = create_test_user(fake_db, email="adm@example.com", role="admin")

    now = datetime.now(timezone.utc)
    exp = int((now + timedelta(minutes=15)).timestamp())
    iat = int(now.timestamp())

    def make_token(uid):
        return jwt.encode(
            {"sub": str(uid), "iat": iat, "exp": exp, "iss": JWT_ISSUER, "aud": JWT_AUDIENCE},
            TEST_JWT_SECRET,
            algorithm=JWT_ALGORITHM,
        )

    emp_token = make_token(emp_user["_id"])
    mgr_token = make_token(mgr_user["_id"])
    adm_token = make_token(adm_user["_id"])

    # Employee checks
    assert client.get("/admin/access-check", headers={"Authorization": f"Bearer {emp_token}"}).status_code == 403
    assert client.get("/management/access-check", headers={"Authorization": f"Bearer {emp_token}"}).status_code == 403

    # Manager checks
    assert client.get("/admin/access-check", headers={"Authorization": f"Bearer {mgr_token}"}).status_code == 403
    mgr_resp = client.get("/management/access-check", headers={"Authorization": f"Bearer {mgr_token}"})
    assert mgr_resp.status_code == 200
    assert mgr_resp.json() == {"status": "ok", "access": "management"}

    # Admin checks
    adm_resp_admin = client.get("/admin/access-check", headers={"Authorization": f"Bearer {adm_token}"})
    assert adm_resp_admin.status_code == 200
    assert adm_resp_admin.json() == {"status": "ok", "access": "admin"}

    adm_resp_mgmt = client.get("/management/access-check", headers={"Authorization": f"Bearer {adm_token}"})
    assert adm_resp_mgmt.status_code == 200
    assert adm_resp_mgmt.json() == {"status": "ok", "access": "management"}


def test_dynamic_role_change_and_deactivation_for_issued_token(test_setup):
    client, fake_db = test_setup

    user = create_test_user(fake_db, email="dynamic@example.com", role="employee", is_active=True)
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": str(user["_id"]),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=15)).timestamp()),
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
        },
        TEST_JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )

    # Initially employee: denied admin
    assert client.get("/admin/access-check", headers={"Authorization": f"Bearer {token}"}).status_code == 403

    # Dynamically promote to admin in database
    user["role"] = "admin"

    # Same token now grants admin access because role is retrieved from DB record
    res_promoted = client.get("/admin/access-check", headers={"Authorization": f"Bearer {token}"})
    assert res_promoted.status_code == 200
    assert res_promoted.json() == {"status": "ok", "access": "admin"}

    # Dynamically deactivate account in database
    user["is_active"] = False

    # Same token is now rejected with 401
    res_deactivated = client.get("/admin/access-check", headers={"Authorization": f"Bearer {token}"})
    assert res_deactivated.status_code == 401
    assert res_deactivated.headers.get("WWW-Authenticate") == "Bearer"


def test_lifespan_fails_without_jwt_secret(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError) as exc_info:
        with TestClient(app):
            pass
    assert "JWT" in str(exc_info.value)
