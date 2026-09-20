from datetime import datetime, timedelta, timezone
from bson import ObjectId
import jwt
import pytest

from security import JWT_ALGORITHM, JWT_AUDIENCE, JWT_ISSUER, hash_password
from tests.conftest import TEST_JWT_SECRET


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


def create_team(fake_db, name: str, manager_id: ObjectId) -> dict:
    team_doc = {
        "_id": ObjectId(),
        "name": name,
        "manager_id": manager_id,
        "created_at": datetime.now(timezone.utc),
    }
    fake_db["teams"].docs.append(team_doc)
    return team_doc


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


def test_employee_creates_and_reads_own_profile(test_setup):
    client, fake_db = test_setup
    emp = create_user(fake_db, email="emp1@example.com", role="employee", name="Employee One")
    token = make_token(emp["_id"])

    # 1. GET /profiles/me before creation returns 404
    res_get_empty = client.get("/profiles/me", headers={"Authorization": f"Bearer {token}"})
    assert res_get_empty.status_code == 404
    assert res_get_empty.json()["detail"] == "Employee profile not found"
    assert len(fake_db["employee_profiles"].docs) == 0

    # 2. PUT /profiles/me creates the profile
    profile_payload = {
        "job_title": "Software Engineer",
        "skills": ["Python", "FastAPI", "MongoDB"],
        "availability_status": "available",
        "weekly_capacity_hours": 40.0,
    }
    res_put = client.put(
        "/profiles/me",
        json=profile_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_put.status_code == 200
    data = res_put.json()
    assert data["user_id"] == str(emp["_id"])
    assert data["job_title"] == "Software Engineer"
    assert data["skills"] == ["Python", "FastAPI", "MongoDB"]
    assert data["availability_status"] == "available"
    assert data["weekly_capacity_hours"] == 40.0
    assert "id" in data
    assert data["created_at"] is not None
    assert data["updated_at"] is not None

    # Verify exactly 1 profile in database
    assert len(fake_db["employee_profiles"].docs) == 1

    # 3. GET /profiles/me returns the created profile
    res_get = client.get("/profiles/me", headers={"Authorization": f"Bearer {token}"})
    assert res_get.status_code == 200
    assert res_get.json() == data


def test_employee_updates_own_profile(test_setup):
    client, fake_db = test_setup
    emp = create_user(fake_db, email="emp2@example.com", role="employee")
    token = make_token(emp["_id"])

    # Create initial profile
    client.put(
        "/profiles/me",
        json={
            "job_title": "Junior Developer",
            "skills": ["HTML", "CSS"],
            "availability_status": "available",
            "weekly_capacity_hours": 20.0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert len(fake_db["employee_profiles"].docs) == 1

    # Update profile
    update_payload = {
        "job_title": "Senior Developer",
        "skills": ["React", "TypeScript", "Node.js"],
        "availability_status": "busy",
        "weekly_capacity_hours": 35.5,
    }
    res_update = client.put(
        "/profiles/me",
        json=update_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_update.status_code == 200
    updated_data = res_update.json()
    assert updated_data["job_title"] == "Senior Developer"
    assert updated_data["skills"] == ["React", "TypeScript", "Node.js"]
    assert updated_data["availability_status"] == "busy"
    assert updated_data["weekly_capacity_hours"] == 35.5
    assert updated_data["user_id"] == str(emp["_id"])

    # Ensure still exactly 1 document in database
    assert len(fake_db["employee_profiles"].docs) == 1


def test_get_does_not_auto_create_profile(test_setup):
    client, fake_db = test_setup
    emp = create_user(fake_db, email="emp3@example.com", role="employee")
    token = make_token(emp["_id"])

    for _ in range(3):
        res = client.get("/profiles/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 404

    assert len(fake_db["employee_profiles"].docs) == 0


def test_employee_cannot_access_other_profiles(test_setup):
    client, fake_db = test_setup
    emp1 = create_user(fake_db, email="emp4@example.com", role="employee")
    emp2 = create_user(fake_db, email="emp5@example.com", role="employee")
    emp1_token = make_token(emp1["_id"])

    # Employee calling /profiles/user/{user_id} is rejected with 403 Forbidden
    res_user = client.get(
        f"/profiles/user/{emp2['_id']}",
        headers={"Authorization": f"Bearer {emp1_token}"},
    )
    assert res_user.status_code == 403

    # Employee calling /profiles/team/{team_id} is rejected with 403 Forbidden
    res_team = client.get(
        f"/profiles/team/{ObjectId()}",
        headers={"Authorization": f"Bearer {emp1_token}"},
    )
    assert res_team.status_code == 403


def test_manager_accesses_profile_in_managed_team(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr1@example.com", role="manager")
    team = create_team(fake_db, name="Team Alpha", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp6@example.com", role="employee", team_id=team["_id"])

    # Create profile for employee
    emp_token = make_token(emp["_id"])
    client.put(
        "/profiles/me",
        json={
            "job_title": "Fullstack Dev",
            "skills": ["React", "Python"],
            "availability_status": "available",
            "weekly_capacity_hours": 40.0,
        },
        headers={"Authorization": f"Bearer {emp_token}"},
    )

    mgr_token = make_token(mgr["_id"])

    # Manager reads employee profile via /profiles/user/{user_id}
    res_emp = client.get(
        f"/profiles/user/{emp['_id']}",
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_emp.status_code == 200
    assert res_emp.json()["user_id"] == str(emp["_id"])
    assert res_emp.json()["job_title"] == "Fullstack Dev"

    # Manager reads team profiles via /profiles/team/{team_id}
    res_team = client.get(
        f"/profiles/team/{team['_id']}",
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_team.status_code == 200
    team_data = res_team.json()
    assert team_data["total"] == 1
    assert len(team_data["items"]) == 1
    assert team_data["items"][0]["user_id"] == str(emp["_id"])


def test_manager_rejected_from_another_team(test_setup):
    client, fake_db = test_setup
    mgr1 = create_user(fake_db, email="mgr2@example.com", role="manager")
    mgr2 = create_user(fake_db, email="mgr3@example.com", role="manager")

    team1 = create_team(fake_db, name="Team One", manager_id=mgr1["_id"])
    team2 = create_team(fake_db, name="Team Two", manager_id=mgr2["_id"])

    emp_team2 = create_user(fake_db, email="emp7@example.com", role="employee", team_id=team2["_id"])

    emp2_token = make_token(emp_team2["_id"])
    client.put(
        "/profiles/me",
        json={
            "job_title": "Backend Dev",
            "skills": ["Go", "Kubernetes"],
            "availability_status": "busy",
            "weekly_capacity_hours": 40.0,
        },
        headers={"Authorization": f"Bearer {emp2_token}"},
    )

    mgr1_token = make_token(mgr1["_id"])

    # Manager 1 attempts to access employee from Team 2
    res_user = client.get(
        f"/profiles/user/{emp_team2['_id']}",
        headers={"Authorization": f"Bearer {mgr1_token}"},
    )
    assert res_user.status_code == 403
    assert "Access denied" in res_user.json()["detail"]

    # Manager 1 attempts to access Team 2 profiles list
    res_team = client.get(
        f"/profiles/team/{team2['_id']}",
        headers={"Authorization": f"Bearer {mgr1_token}"},
    )
    assert res_team.status_code == 403
    assert "Access denied" in res_team.json()["detail"]


def test_admin_read_only_profile_access(test_setup):
    client, fake_db = test_setup
    admin = create_user(fake_db, email="admin@example.com", role="admin")
    mgr = create_user(fake_db, email="mgr4@example.com", role="manager")
    team = create_team(fake_db, name="Team Beta", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp8@example.com", role="employee", team_id=team["_id"])

    emp_token = make_token(emp["_id"])
    client.put(
        "/profiles/me",
        json={
            "job_title": "DevOps Engineer",
            "skills": ["Terraform", "AWS"],
            "availability_status": "on_leave",
            "weekly_capacity_hours": 0.0,
        },
        headers={"Authorization": f"Bearer {emp_token}"},
    )

    admin_token = make_token(admin["_id"])

    # Admin reads employee profile
    res_user = client.get(
        f"/profiles/user/{emp['_id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_user.status_code == 200
    assert res_user.json()["user_id"] == str(emp["_id"])
    assert res_user.json()["job_title"] == "DevOps Engineer"

    # Admin reads team profiles
    res_team = client.get(
        f"/profiles/team/{team['_id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_team.status_code == 200
    assert res_team.json()["total"] == 1
    assert res_team.json()["items"][0]["user_id"] == str(emp["_id"])


def test_invalid_availability_and_capacity_rejected(test_setup):
    client, fake_db = test_setup
    emp = create_user(fake_db, email="emp9@example.com", role="employee")
    token = make_token(emp["_id"])

    # Invalid availability
    res1 = client.put(
        "/profiles/me",
        json={
            "job_title": "Developer",
            "skills": ["Python"],
            "availability_status": "sleeping",
            "weekly_capacity_hours": 40.0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res1.status_code == 422

    # Negative capacity
    res2 = client.put(
        "/profiles/me",
        json={
            "job_title": "Developer",
            "skills": ["Python"],
            "availability_status": "available",
            "weekly_capacity_hours": -5.0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res2.status_code == 422

    # Capacity exceeding 80 hours
    res3 = client.put(
        "/profiles/me",
        json={
            "job_title": "Developer",
            "skills": ["Python"],
            "availability_status": "available",
            "weekly_capacity_hours": 90.0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res3.status_code == 422

    # Empty job title
    res4 = client.put(
        "/profiles/me",
        json={
            "job_title": "   ",
            "skills": ["Python"],
            "availability_status": "available",
            "weekly_capacity_hours": 40.0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res4.status_code == 422


def test_extra_fields_and_request_user_id_rejected(test_setup):
    client, fake_db = test_setup
    emp = create_user(fake_db, email="emp10@example.com", role="employee")
    other_user_id = str(ObjectId())
    token = make_token(emp["_id"])

    # Injecting user_id in body
    res_user_id = client.put(
        "/profiles/me",
        json={
            "user_id": other_user_id,
            "job_title": "Developer",
            "skills": ["Python"],
            "availability_status": "available",
            "weekly_capacity_hours": 40.0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_user_id.status_code == 422

    # Injecting unknown extra field
    res_extra = client.put(
        "/profiles/me",
        json={
            "role": "admin",
            "job_title": "Developer",
            "skills": ["Python"],
            "availability_status": "available",
            "weekly_capacity_hours": 40.0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_extra.status_code == 422


def test_duplicate_and_empty_skills_normalized_or_rejected(test_setup):
    client, fake_db = test_setup
    emp = create_user(fake_db, email="emp11@example.com", role="employee")
    token = make_token(emp["_id"])

    # Duplicate case-insensitive skills normalized and trimmed
    res_dup = client.put(
        "/profiles/me",
        json={
            "job_title": "Developer",
            "skills": [" Python ", "python", "PYTHON  ", " FastAPI", "fastapi "],
            "availability_status": "available",
            "weekly_capacity_hours": 40.0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_dup.status_code == 200
    assert res_dup.json()["skills"] == ["Python", "FastAPI"]

    # Whitespace-only skill rejected
    res_empty_skill = client.put(
        "/profiles/me",
        json={
            "job_title": "Developer",
            "skills": ["Python", "   "],
            "availability_status": "available",
            "weekly_capacity_hours": 40.0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_empty_skill.status_code == 422


def test_inactive_user_rejected(test_setup):
    client, fake_db = test_setup
    inactive_emp = create_user(
        fake_db,
        email="inactive@example.com",
        role="employee",
        is_active=False,
    )
    token = make_token(inactive_emp["_id"])

    # Inactive caller cannot access /profiles/me
    res = client.get("/profiles/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
    assert "inactive" in res.json()["detail"].lower()

    # Manager attempting to access profile of inactive employee is rejected
    mgr = create_user(fake_db, email="mgr5@example.com", role="manager")
    team = create_team(fake_db, name="Team Gamma", manager_id=mgr["_id"])
    inactive_emp["team_id"] = team["_id"]

    # Add profile for inactive user directly in database
    fake_db["employee_profiles"].docs.append(
        {
            "_id": ObjectId(),
            "user_id": inactive_emp["_id"],
            "job_title": "Dev",
            "skills": ["Python"],
            "availability_status": "available",
            "weekly_capacity_hours": 40.0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    mgr_token = make_token(mgr["_id"])
    res_mgr = client.get(
        f"/profiles/user/{inactive_emp['_id']}",
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_mgr.status_code == 403
    assert "inactive" in res_mgr.json()["detail"].lower()


def test_invalid_object_id_handling(test_setup):
    client, fake_db = test_setup
    admin = create_user(fake_db, email="admin2@example.com", role="admin")
    admin_token = make_token(admin["_id"])

    res_bad_user = client.get(
        "/profiles/user/invalid-id",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_bad_user.status_code == 400
    assert "Invalid User ID format" in res_bad_user.json()["detail"]

    res_bad_team = client.get(
        "/profiles/team/invalid-id",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_bad_team.status_code == 400
    assert "Invalid Team ID format" in res_bad_team.json()["detail"]
