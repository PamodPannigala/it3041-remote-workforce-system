from datetime import datetime, timedelta, timezone
from bson import ObjectId
import jwt
import pytest

from backend.app.core.security import JWT_ALGORITHM, JWT_AUDIENCE, JWT_ISSUER, hash_password
from backend.tests.conftest import TEST_JWT_SECRET



def create_user(
    fake_db,
    email: str = "test@example.com",
    role: str = "employee",
    is_active: bool = True,
    name: str = "Test User",
    team_id: ObjectId | None = None,
) -> dict:
    user_doc = {
        "_id": ObjectId(),
        "name": name,
        "email": email.lower(),
        "password_hash": hash_password("ValidPassword12345!"),
        "role": role,
        "is_active": is_active,
        "team_id": team_id,
        "created_at": datetime.now(timezone.utc),
    }
    fake_db["users"].docs.append(user_doc)
    return user_doc


def make_token(user_id: ObjectId) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=15)).timestamp()),
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
        },
        TEST_JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def test_admin_endpoints_rbac_protection(test_setup):
    client, fake_db = test_setup

    emp = create_user(fake_db, email="emp@example.com", role="employee")
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    target = create_user(fake_db, email="target@example.com", role="employee")

    # Anonymous -> 401
    assert client.get("/admin/users").status_code == 401
    assert client.patch(f"/admin/users/{target['_id']}/role", json={"role": "manager"}).status_code == 401
    assert client.patch(f"/admin/users/{target['_id']}/status", json={"is_active": False}).status_code == 401

    # Employee -> 403
    emp_token = make_token(emp["_id"])
    assert client.get("/admin/users", headers={"Authorization": f"Bearer {emp_token}"}).status_code == 403
    assert client.patch(f"/admin/users/{target['_id']}/role", json={"role": "manager"}, headers={"Authorization": f"Bearer {emp_token}"}).status_code == 403
    assert client.patch(f"/admin/users/{target['_id']}/status", json={"is_active": False}, headers={"Authorization": f"Bearer {emp_token}"}).status_code == 403

    # Manager -> 403
    mgr_token = make_token(mgr["_id"])
    assert client.get("/admin/users", headers={"Authorization": f"Bearer {mgr_token}"}).status_code == 403


def test_admin_list_users_paginated_and_safe_fields(test_setup):
    client, fake_db = test_setup

    admin = create_user(fake_db, email="admin@example.com", role="admin")
    for i in range(15):
        create_user(fake_db, email=f"user{i}@example.com", name=f"User {i}")

    admin_token = make_token(admin["_id"])

    # Page 1, limit 10
    res1 = client.get("/admin/users?page=1&limit=10", headers={"Authorization": f"Bearer {admin_token}"})
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["total"] == 16  # 1 admin + 15 users
    assert data1["page"] == 1
    assert data1["limit"] == 10
    assert data1["total_pages"] == 2
    assert len(data1["items"]) == 10

    # Ensure safe fields only
    for item in data1["items"]:
        assert "id" in item
        assert "name" in item
        assert "email" in item
        assert "role" in item
        assert "is_active" in item
        assert "password" not in item
        assert "password_hash" not in item

    # Page 2
    res2 = client.get("/admin/users?page=2&limit=10", headers={"Authorization": f"Bearer {admin_token}"})
    assert res2.status_code == 200
    data2 = res2.json()
    assert len(data2["items"]) == 6


def test_admin_update_user_role_and_status(test_setup):
    client, fake_db = test_setup

    admin = create_user(fake_db, email="admin@example.com", role="admin")
    emp = create_user(fake_db, email="target.emp@example.com", role="employee", is_active=True)

    admin_token = make_token(admin["_id"])

    # Update role to manager
    res_role = client.patch(
        f"/admin/users/{emp['_id']}/role",
        json={"role": "manager"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_role.status_code == 200
    assert res_role.json()["role"] == "manager"

    # Update status to inactive
    res_status = client.patch(
        f"/admin/users/{emp['_id']}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_status.status_code == 200
    assert res_status.json()["is_active"] is False


def test_admin_self_demotion_and_deactivation_protection(test_setup):
    client, fake_db = test_setup

    admin1 = create_user(fake_db, email="admin1@example.com", role="admin")
    create_user(fake_db, email="admin2@example.com", role="admin")  # second admin exists

    admin1_token = make_token(admin1["_id"])

    # Self-demotion should be rejected
    res_self_demote = client.patch(
        f"/admin/users/{admin1['_id']}/role",
        json={"role": "employee"},
        headers={"Authorization": f"Bearer {admin1_token}"},
    )
    assert res_self_demote.status_code == 400
    assert "cannot change their own role" in res_self_demote.json()["detail"].lower()

    # Self-deactivation should be rejected
    res_self_deact = client.patch(
        f"/admin/users/{admin1['_id']}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {admin1_token}"},
    )
    assert res_self_deact.status_code == 400
    assert "cannot deactivate their own account" in res_self_deact.json()["detail"].lower()


def test_last_active_admin_protection(test_setup):
    client, fake_db = test_setup

    admin1 = create_user(fake_db, email="admin1@example.com", role="admin", is_active=True)
    admin2 = create_user(fake_db, email="admin2@example.com", role="admin", is_active=True)

    admin1_token = make_token(admin1["_id"])

    # Demote admin2 -> 1 active admin remains (admin1)
    res_demote2 = client.patch(
        f"/admin/users/{admin2['_id']}/role",
        json={"role": "manager"},
        headers={"Authorization": f"Bearer {admin1_token}"},
    )
    assert res_demote2.status_code == 200

    # admin1 is now the sole active admin. Any attempt by admin1 to demote themselves is rejected
    res_demote_sole = client.patch(
        f"/admin/users/{admin1['_id']}/role",
        json={"role": "manager"},
        headers={"Authorization": f"Bearer {admin1_token}"},
    )
    assert res_demote_sole.status_code == 400

    # Any attempt by admin1 to deactivate themselves is rejected
    res_deact_sole = client.patch(
        f"/admin/users/{admin1['_id']}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {admin1_token}"},
    )
    assert res_deact_sole.status_code == 400


def test_active_team_manager_reassignment_protection(test_setup):
    client, fake_db = test_setup

    admin = create_user(fake_db, email="admin@example.com", role="admin")
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")

    # Create team with this manager
    fake_db["teams"].docs.append({
        "_id": ObjectId(),
        "name": "Engineering Team",
        "manager_id": mgr["_id"],
        "created_at": datetime.now(timezone.utc),
    })

    admin_token = make_token(admin["_id"])

    # Attempt to demote manager without reassigning team -> rejected
    res_demote = client.patch(
        f"/admin/users/{mgr['_id']}/role",
        json={"role": "employee"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_demote.status_code == 400
    assert "reassign the team" in res_demote.json()["detail"].lower()

    # Attempt to deactivate manager without reassigning team -> rejected
    res_deact = client.patch(
        f"/admin/users/{mgr['_id']}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_deact.status_code == 400
    assert "reassign the team" in res_deact.json()["detail"].lower()
