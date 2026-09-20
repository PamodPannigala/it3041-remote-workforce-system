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


def test_team_creation_and_validation(test_setup):
    client, fake_db = test_setup

    admin = create_user(fake_db, email="admin@example.com", role="admin")
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    emp = create_user(fake_db, email="emp@example.com", role="employee")

    admin_token = make_token(admin["_id"])

    # Cannot create team with employee as manager
    res_bad_mgr = client.post(
        "/admin/teams",
        json={"name": "Dev Team", "manager_id": str(emp["_id"])},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_bad_mgr.status_code == 400
    assert "role 'manager'" in res_bad_mgr.json()["detail"]

    # Success creating team with manager
    res_create = client.post(
        "/admin/teams",
        json={"name": "Dev Team", "manager_id": str(mgr["_id"])},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_create.status_code == 201
    team_data = res_create.json()
    assert team_data["name"] == "Dev Team"
    assert team_data["manager_id"] == str(mgr["_id"])
    assert team_data["manager_name"] == mgr["name"]
    assert team_data["members"] == []

    # Duplicate team name rejected
    res_dup = client.post(
        "/admin/teams",
        json={"name": "Dev Team", "manager_id": str(mgr["_id"])},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_dup.status_code == 409


def test_team_member_assignment_and_reassignment(test_setup):
    client, fake_db = test_setup

    admin = create_user(fake_db, email="admin@example.com", role="admin")
    mgr1 = create_user(fake_db, email="mgr1@example.com", role="manager")
    mgr2 = create_user(fake_db, email="mgr2@example.com", role="manager")
    emp = create_user(fake_db, email="emp@example.com", role="employee")

    admin_token = make_token(admin["_id"])

    # Create Team A and Team B
    res_a = client.post(
        "/admin/teams",
        json={"name": "Team Alpha", "manager_id": str(mgr1["_id"])},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    team_a_id = res_a.json()["id"]

    res_b = client.post(
        "/admin/teams",
        json={"name": "Team Beta", "manager_id": str(mgr2["_id"])},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    team_b_id = res_b.json()["id"]

    # Assign employee to Team Alpha
    res_assign_a = client.post(
        f"/admin/teams/{team_a_id}/members",
        json={"user_id": str(emp["_id"])},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_assign_a.status_code == 200
    assert len(res_assign_a.json()["members"]) == 1
    assert res_assign_a.json()["members"][0]["id"] == str(emp["_id"])

    # Reassign employee to Team Beta (employee belongs to at most one team)
    res_assign_b = client.post(
        f"/admin/teams/{team_b_id}/members",
        json={"user_id": str(emp["_id"])},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_assign_b.status_code == 200
    assert len(res_assign_b.json()["members"]) == 1

    # Check Team Alpha now has 0 members
    res_teams_list = client.get("/admin/teams", headers={"Authorization": f"Bearer {admin_token}"})
    teams = res_teams_list.json()
    alpha = next(t for t in teams if t["id"] == team_a_id)
    beta = next(t for t in teams if t["id"] == team_b_id)
    assert len(alpha["members"]) == 0
    assert len(beta["members"]) == 1

    # Remove member from Team Beta
    res_del = client.delete(
        f"/admin/teams/{team_b_id}/members/{emp['_id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_del.status_code == 200

    # Verify member is removed
    res_teams_list2 = client.get("/admin/teams", headers={"Authorization": f"Bearer {admin_token}"})
    beta2 = next(t for t in res_teams_list2.json() if t["id"] == team_b_id)
    assert len(beta2["members"]) == 0


def test_manager_scoping_and_cross_team_access_rejection(test_setup):
    client, fake_db = test_setup

    mgr1 = create_user(fake_db, email="mgr1@example.com", role="manager", name="Manager One")
    mgr2 = create_user(fake_db, email="mgr2@example.com", role="manager", name="Manager Two")

    emp1 = create_user(fake_db, email="emp1@example.com", role="employee", name="Emp 1")
    emp2 = create_user(fake_db, email="emp2@example.com", role="employee", name="Emp 2")

    # Team 1 managed by mgr1 with emp1
    team1_id = ObjectId()
    fake_db["teams"].docs.append({
        "_id": team1_id,
        "name": "Team One",
        "manager_id": mgr1["_id"],
        "created_at": datetime.now(timezone.utc),
    })
    emp1["team_id"] = team1_id

    # Team 2 managed by mgr2 with emp2
    team2_id = ObjectId()
    fake_db["teams"].docs.append({
        "_id": team2_id,
        "name": "Team Two",
        "manager_id": mgr2["_id"],
        "created_at": datetime.now(timezone.utc),
    })
    emp2["team_id"] = team2_id

    mgr1_token = make_token(mgr1["_id"])
    mgr2_token = make_token(mgr2["_id"])

    # Manager 1 calls /teams/managed -> sees only Team 1
    res_m1_teams = client.get("/teams/managed", headers={"Authorization": f"Bearer {mgr1_token}"})
    assert res_m1_teams.status_code == 200
    m1_teams = res_m1_teams.json()
    assert len(m1_teams) == 1
    assert m1_teams[0]["id"] == str(team1_id)
    assert len(m1_teams[0]["members"]) == 1
    assert m1_teams[0]["members"][0]["id"] == str(emp1["_id"])

    # Manager 1 calls /teams/{team1_id}/members -> permitted
    res_m1_own_members = client.get(f"/teams/{team1_id}/members", headers={"Authorization": f"Bearer {mgr1_token}"})
    assert res_m1_own_members.status_code == 200
    assert len(res_m1_own_members.json()) == 1

    # Cross-team access: Manager 1 attempts to access Team 2's members -> 403 Forbidden!
    res_cross_access = client.get(f"/teams/{team2_id}/members", headers={"Authorization": f"Bearer {mgr1_token}"})
    assert res_cross_access.status_code == 403
    assert "access denied" in res_cross_access.json()["detail"].lower()

    # Manager 2 attempts to access Team 1's members -> 403 Forbidden!
    res_cross_access2 = client.get(f"/teams/{team1_id}/members", headers={"Authorization": f"Bearer {mgr2_token}"})
    assert res_cross_access2.status_code == 403


def test_employee_team_summary_and_boundary_enforcement(test_setup):
    client, fake_db = test_setup

    mgr = create_user(fake_db, email="mgr@example.com", role="manager", name="Lead Manager")
    emp_unassigned = create_user(fake_db, email="unassigned@example.com", role="employee")
    emp_assigned = create_user(fake_db, email="assigned@example.com", role="employee")

    team_id = ObjectId()
    fake_db["teams"].docs.append({
        "_id": team_id,
        "name": "Frontend Team",
        "manager_id": mgr["_id"],
        "created_at": datetime.now(timezone.utc),
    })
    emp_assigned["team_id"] = team_id

    unassigned_token = make_token(emp_unassigned["_id"])
    assigned_token = make_token(emp_assigned["_id"])

    # Unassigned employee summary
    res_unassigned = client.get("/teams/my-summary", headers={"Authorization": f"Bearer {unassigned_token}"})
    assert res_unassigned.status_code == 200
    data_unassigned = res_unassigned.json()
    assert data_unassigned["has_team"] is False
    assert data_unassigned["team_id"] is None

    # Assigned employee summary
    res_assigned = client.get("/teams/my-summary", headers={"Authorization": f"Bearer {assigned_token}"})
    assert res_assigned.status_code == 200
    data_assigned = res_assigned.json()
    assert data_assigned["has_team"] is True
    assert data_assigned["team_id"] == str(team_id)
    assert data_assigned["team_name"] == "Frontend Team"
    assert data_assigned["manager_name"] == "Lead Manager"
    assert data_assigned["manager_email"] == "mgr@example.com"

    # Employees CANNOT list members of any team directly
    assert client.get(f"/teams/{team_id}/members", headers={"Authorization": f"Bearer {assigned_token}"}).status_code == 403
    assert client.get("/teams/managed", headers={"Authorization": f"Bearer {assigned_token}"}).status_code == 403
    assert client.get("/admin/teams", headers={"Authorization": f"Bearer {assigned_token}"}).status_code == 403
