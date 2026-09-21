from datetime import datetime, timedelta, timezone
from bson import ObjectId
import jwt
import pytest
from unittest.mock import patch
from pymongo.errors import PyMongoError, DuplicateKeyError

from backend.app.core.security import JWT_ALGORITHM, JWT_AUDIENCE, JWT_ISSUER, hash_password
from backend.app.modules.pulse_surveys.router import get_current_week_start, parse_week_start
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


# =============================================================================
# Helper Unit Tests
# =============================================================================


def test_get_current_week_start_returns_monday():
    # Tuesday 2026-09-22 15:30:00 UTC -> Monday 2026-09-21 00:00:00 UTC
    dt = datetime(2026, 9, 22, 15, 30, tzinfo=timezone.utc)
    ws = get_current_week_start(dt)
    assert ws.year == 2026
    assert ws.month == 9
    assert ws.day == 21
    assert ws.hour == 0
    assert ws.minute == 0
    assert ws.second == 0
    assert ws.tzinfo == timezone.utc

    # Sunday 2026-09-27 23:59:59 UTC -> Monday 2026-09-21 00:00:00 UTC
    sunday = datetime(2026, 9, 27, 23, 59, 59, tzinfo=timezone.utc)
    ws_sun = get_current_week_start(sunday)
    assert ws_sun.day == 21

    # Monday 2026-09-21 00:00:00 UTC -> Monday 2026-09-21 00:00:00 UTC
    monday = datetime(2026, 9, 21, 0, 0, 0, tzinfo=timezone.utc)
    ws_mon = get_current_week_start(monday)
    assert ws_mon.day == 21


def test_parse_week_start_validation():
    # Valid Monday
    ws = parse_week_start("2026-09-21")
    assert ws == datetime(2026, 9, 21, 0, 0, 0, tzinfo=timezone.utc)

    # None returns current week start
    ws_none = parse_week_start(None)
    assert ws_none.weekday() == 0

    # Non-Monday date
    with pytest.raises(Exception) as exc_info:
        parse_week_start("2026-09-22")
    assert "week_start must be a Monday" in str(exc_info.value.detail)

    # Invalid format
    with pytest.raises(Exception) as exc_info:
        parse_week_start("invalid-date")
    assert "Invalid week_start date format" in str(exc_info.value.detail)


# =============================================================================
# 1. Employee Submission Tests (Endpoints 1)
# =============================================================================


def test_employee_submits_valid_current_week_response(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager", name="Team Manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", name="Alice Worker", team_id=team["_id"])

    token = make_token(emp["_id"])
    payload = {
        "workload_manageability": 4,
        "work_life_balance": 5,
        "team_support": 3,
        "engagement": 4,
        "optional_comment": "Feeling productive this sprint.",
    }

    res = client.post("/pulse-surveys/responses", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 201
    data = res.json()

    assert data["workload_manageability"] == 4
    assert data["work_life_balance"] == 5
    assert data["team_support"] == 3
    assert data["engagement"] == 4
    assert data["optional_comment"] == "Feeling productive this sprint."
    assert data["user_id"] == str(emp["_id"])
    assert data["team_id"] == str(team["_id"])
    assert data["team_name"] == "Alpha Team"
    assert "week_start" in data
    assert "submitted_at" in data
    assert "id" in data

    # Verify stored document in fake database
    stored = fake_db["weekly_pulse_responses"].docs[0]
    assert stored["user_id"] == emp["_id"]
    assert stored["team_id"] == team["_id"]
    assert stored["workload_manageability"] == 4
    assert stored["work_life_balance"] == 5
    assert stored["team_support"] == 3
    assert stored["engagement"] == 4
    assert stored["optional_comment"] == "Feeling productive this sprint."
    assert isinstance(stored["submitted_at"], datetime)
    assert stored["submitted_at"].tzinfo is not None
    assert isinstance(stored["week_start"], datetime)
    assert stored["week_start"].tzinfo is not None
    assert stored["week_start"].weekday() == 0


def test_server_derives_identity_and_rejects_client_server_fields(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])
    other_user = create_user(fake_db, email="other@example.com", role="employee")

    token = make_token(emp["_id"])

    # 1. Attempt to supply client user_id
    res1 = client.post(
        "/pulse-surveys/responses",
        json={"workload_manageability": 3, "work_life_balance": 3, "team_support": 3, "engagement": 3, "user_id": str(other_user["_id"])},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res1.status_code == 422

    # 2. Attempt to supply client team_id
    res2 = client.post(
        "/pulse-surveys/responses",
        json={"workload_manageability": 3, "work_life_balance": 3, "team_support": 3, "engagement": 3, "team_id": str(ObjectId())},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res2.status_code == 422

    # 3. Attempt to supply client week_start
    res3 = client.post(
        "/pulse-surveys/responses",
        json={"workload_manageability": 3, "work_life_balance": 3, "team_support": 3, "engagement": 3, "week_start": "2026-09-01"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res3.status_code == 422

    # 4. Attempt to supply client submitted_at
    res4 = client.post(
        "/pulse-surveys/responses",
        json={"workload_manageability": 3, "work_life_balance": 3, "team_support": 3, "engagement": 3, "submitted_at": "2026-09-21T00:00:00Z"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res4.status_code == 422


def test_duplicate_response_same_week_returns_409(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])

    token = make_token(emp["_id"])
    payload = {"workload_manageability": 3, "work_life_balance": 3, "team_support": 3, "engagement": 3}

    res1 = client.post("/pulse-surveys/responses", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert res1.status_code == 201

    res2 = client.post("/pulse-surveys/responses", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert res2.status_code == 409
    assert "already been submitted" in res2.json()["detail"]


def test_duplicate_key_error_caught_and_returns_409(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])

    token = make_token(emp["_id"])
    payload = {"workload_manageability": 3, "work_life_balance": 3, "team_support": 3, "engagement": 3}

    # Simulate race condition where find_one returns None, but insert_one raises DuplicateKeyError
    with patch.object(fake_db["weekly_pulse_responses"], "find_one", return_value=None):
        with patch.object(fake_db["weekly_pulse_responses"], "insert_one", side_effect=DuplicateKeyError("dup")):
            res = client.post("/pulse-surveys/responses", json=payload, headers={"Authorization": f"Bearer {token}"})
            assert res.status_code == 409
            assert "already been submitted" in res.json()["detail"]


def test_employee_without_team_receives_409(test_setup):
    client, fake_db = test_setup
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=None)

    token = make_token(emp["_id"])
    payload = {"workload_manageability": 3, "work_life_balance": 3, "team_support": 3, "engagement": 3}

    res = client.post("/pulse-surveys/responses", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 409
    assert "valid team assignment is required" in res.json()["detail"].lower()


def test_employee_referencing_nonexistent_team_receives_409(test_setup):
    client, fake_db = test_setup
    fake_team_id = ObjectId()
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=fake_team_id)

    token = make_token(emp["_id"])
    payload = {"workload_manageability": 3, "work_life_balance": 3, "team_support": 3, "engagement": 3}

    res = client.post("/pulse-surveys/responses", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 409
    assert "valid team assignment is required" in res.json()["detail"].lower()


def test_manager_and_admin_cannot_submit_pulse_survey(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    admin = create_user(fake_db, email="admin@example.com", role="admin")

    mgr_token = make_token(mgr["_id"])
    admin_token = make_token(admin["_id"])
    payload = {"workload_manageability": 3, "work_life_balance": 3, "team_support": 3, "engagement": 3}

    res_mgr = client.post("/pulse-surveys/responses", json=payload, headers={"Authorization": f"Bearer {mgr_token}"})
    assert res_mgr.status_code == 403

    res_admin = client.post("/pulse-surveys/responses", json=payload, headers={"Authorization": f"Bearer {admin_token}"})
    assert res_admin.status_code == 403


def test_ratings_validation_bounds(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])
    token = make_token(emp["_id"])

    # Score below 1
    res = client.post(
        "/pulse-surveys/responses",
        json={"workload_manageability": 0, "work_life_balance": 3, "team_support": 3, "engagement": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422

    # Score above 5
    res = client.post(
        "/pulse-surveys/responses",
        json={"workload_manageability": 3, "work_life_balance": 6, "team_support": 3, "engagement": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422


def test_ratings_strict_types_rejected(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])
    token = make_token(emp["_id"])

    # Boolean
    res = client.post(
        "/pulse-surveys/responses",
        json={"workload_manageability": True, "work_life_balance": 3, "team_support": 3, "engagement": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422

    # String integer
    res = client.post(
        "/pulse-surveys/responses",
        json={"workload_manageability": "3", "work_life_balance": 3, "team_support": 3, "engagement": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422

    # Float
    res = client.post(
        "/pulse-surveys/responses",
        json={"workload_manageability": 3.5, "work_life_balance": 3, "team_support": 3, "engagement": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422


def test_comment_normalization_and_length_limit(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp1 = create_user(fake_db, email="emp1@example.com", role="employee", team_id=team["_id"])
    emp2 = create_user(fake_db, email="emp2@example.com", role="employee", team_id=team["_id"])

    token1 = make_token(emp1["_id"])
    token2 = make_token(emp2["_id"])

    # Whitespace-only comment normalizes to None
    res1 = client.post(
        "/pulse-surveys/responses",
        json={"workload_manageability": 4, "work_life_balance": 4, "team_support": 4, "engagement": 4, "optional_comment": "   "},
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert res1.status_code == 201
    assert res1.json()["optional_comment"] is None

    # Comment over 1000 chars rejected with 422
    res2 = client.post(
        "/pulse-surveys/responses",
        json={"workload_manageability": 4, "work_life_balance": 4, "team_support": 4, "engagement": 4, "optional_comment": "a" * 1001},
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert res2.status_code == 422


def test_unexpected_request_fields_rejected(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])
    token = make_token(emp["_id"])

    res = client.post(
        "/pulse-surveys/responses",
        json={"workload_manageability": 4, "work_life_balance": 4, "team_support": 4, "engagement": 4, "mood_score": 88},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422


# =============================================================================
# 2. Employee History Tests (Endpoint 2)
# =============================================================================


def test_employee_lists_only_own_responses_with_deterministic_sort(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp1 = create_user(fake_db, email="emp1@example.com", role="employee", team_id=team["_id"])
    emp2 = create_user(fake_db, email="emp2@example.com", role="employee", team_id=team["_id"])

    # Seed 3 responses for emp1 across 3 different weeks
    ws1 = datetime(2026, 9, 7, 0, 0, tzinfo=timezone.utc)
    ws2 = datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)
    ws3 = datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc)

    fake_db["weekly_pulse_responses"].docs.append({
        "_id": ObjectId(), "user_id": emp1["_id"], "team_id": team["_id"], "week_start": ws1,
        "workload_manageability": 2, "work_life_balance": 2, "team_support": 2, "engagement": 2,
        "optional_comment": "Week 1", "submitted_at": ws1 + timedelta(days=1),
    })
    fake_db["weekly_pulse_responses"].docs.append({
        "_id": ObjectId(), "user_id": emp1["_id"], "team_id": team["_id"], "week_start": ws3,
        "workload_manageability": 4, "work_life_balance": 4, "team_support": 4, "engagement": 4,
        "optional_comment": "Week 3", "submitted_at": ws3 + timedelta(days=1),
    })
    fake_db["weekly_pulse_responses"].docs.append({
        "_id": ObjectId(), "user_id": emp1["_id"], "team_id": team["_id"], "week_start": ws2,
        "workload_manageability": 3, "work_life_balance": 3, "team_support": 3, "engagement": 3,
        "optional_comment": "Week 2", "submitted_at": ws2 + timedelta(days=1),
    })

    # Seed 1 response for emp2
    fake_db["weekly_pulse_responses"].docs.append({
        "_id": ObjectId(), "user_id": emp2["_id"], "team_id": team["_id"], "week_start": ws3,
        "workload_manageability": 5, "work_life_balance": 5, "team_support": 5, "engagement": 5,
        "optional_comment": "Emp2", "submitted_at": ws3 + timedelta(days=1),
    })

    token1 = make_token(emp1["_id"])
    res = client.get("/pulse-surveys/my-responses", headers={"Authorization": f"Bearer {token1}"})
    assert res.status_code == 200
    data = res.json()

    assert data["total"] == 3
    assert len(data["items"]) == 3
    # Check descending order by week_start
    assert data["items"][0]["optional_comment"] == "Week 3"
    assert data["items"][1]["optional_comment"] == "Week 2"
    assert data["items"][2]["optional_comment"] == "Week 1"
    for item in data["items"]:
        assert item["user_id"] == str(emp1["_id"])
        assert item["team_name"] == "Alpha Team"


def test_employee_history_pagination(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])

    for i in range(5):
        ws = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc) + timedelta(weeks=i)
        fake_db["weekly_pulse_responses"].docs.append({
            "_id": ObjectId(), "user_id": emp["_id"], "team_id": team["_id"], "week_start": ws,
            "workload_manageability": 3, "work_life_balance": 3, "team_support": 3, "engagement": 3,
            "optional_comment": f"Week {i}", "submitted_at": ws,
        })

    token = make_token(emp["_id"])
    res = client.get("/pulse-surveys/my-responses?page=2&limit=2", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 5
    assert data["page"] == 2
    assert data["limit"] == 2
    assert data["total_pages"] == 3
    assert len(data["items"]) == 2


def test_historical_missing_team_safely_returns_none(test_setup):
    client, fake_db = test_setup
    emp = create_user(fake_db, email="emp@example.com", role="employee")
    deleted_team_id = ObjectId()

    ws = datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc)
    fake_db["weekly_pulse_responses"].docs.append({
        "_id": ObjectId(), "user_id": emp["_id"], "team_id": deleted_team_id, "week_start": ws,
        "workload_manageability": 3, "work_life_balance": 3, "team_support": 3, "engagement": 3,
        "optional_comment": "Old response", "submitted_at": ws,
    })

    token = make_token(emp["_id"])
    res = client.get("/pulse-surveys/my-responses", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["team_name"] is None
    assert data["items"][0]["team_id"] == str(deleted_team_id)


# =============================================================================
# 3. Manager Summary & Privacy Threshold Tests (Endpoint 3)
# =============================================================================


def test_manager_receives_unavailable_summary_below_threshold(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager", name="Team Manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp1 = create_user(fake_db, email="emp1@example.com", role="employee", team_id=team["_id"])
    emp2 = create_user(fake_db, email="emp2@example.com", role="employee", team_id=team["_id"])

    ws = datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc)
    # Seed 2 responses (below MINIMUM_AGGREGATE_RESPONSES = 3)
    fake_db["weekly_pulse_responses"].docs.append({
        "_id": ObjectId(), "user_id": emp1["_id"], "team_id": team["_id"], "week_start": ws,
        "workload_manageability": 4, "work_life_balance": 4, "team_support": 4, "engagement": 4,
        "optional_comment": "Secret comment 1", "submitted_at": ws,
    })
    fake_db["weekly_pulse_responses"].docs.append({
        "_id": ObjectId(), "user_id": emp2["_id"], "team_id": team["_id"], "week_start": ws,
        "workload_manageability": 5, "work_life_balance": 5, "team_support": 5, "engagement": 5,
        "optional_comment": "Secret comment 2", "submitted_at": ws,
    })

    token = make_token(mgr["_id"])
    res = client.get(f"/pulse-surveys/team-summary?team_id={team['_id']}&week_start=2026-09-21", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()

    assert data["available"] is False
    assert data["response_count"] == 2
    assert data["minimum_required"] == 3
    assert data["averages"] is None
    assert "Insufficient responses" in data["message"]
    assert "Secret comment" not in str(data)
    assert str(emp1["_id"]) not in str(data)


def test_manager_receives_averages_at_or_above_threshold(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager", name="Team Manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp1 = create_user(fake_db, email="emp1@example.com", role="employee", team_id=team["_id"])
    emp2 = create_user(fake_db, email="emp2@example.com", role="employee", team_id=team["_id"])
    emp3 = create_user(fake_db, email="emp3@example.com", role="employee", team_id=team["_id"])

    ws = datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc)
    # Seed 3 responses:
    # workload_manageability: 3, 4, 5 -> avg 4.0
    # work_life_balance: 2, 3, 4 -> avg 3.0
    # team_support: 5, 4, 4 -> avg 4.33
    # engagement: 1, 2, 4 -> avg 2.33
    fake_db["weekly_pulse_responses"].docs.append({
        "_id": ObjectId(), "user_id": emp1["_id"], "team_id": team["_id"], "week_start": ws,
        "workload_manageability": 3, "work_life_balance": 2, "team_support": 5, "engagement": 1,
        "optional_comment": "Secret comment 1", "submitted_at": ws,
    })
    fake_db["weekly_pulse_responses"].docs.append({
        "_id": ObjectId(), "user_id": emp2["_id"], "team_id": team["_id"], "week_start": ws,
        "workload_manageability": 4, "work_life_balance": 3, "team_support": 4, "engagement": 2,
        "optional_comment": "Secret comment 2", "submitted_at": ws,
    })
    fake_db["weekly_pulse_responses"].docs.append({
        "_id": ObjectId(), "user_id": emp3["_id"], "team_id": team["_id"], "week_start": ws,
        "workload_manageability": 5, "work_life_balance": 4, "team_support": 4, "engagement": 4,
        "optional_comment": "Secret comment 3", "submitted_at": ws,
    })

    token = make_token(mgr["_id"])
    res = client.get(f"/pulse-surveys/team-summary?team_id={team['_id']}&week_start=2026-09-21", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()

    assert data["available"] is True
    assert data["response_count"] == 3
    assert data["minimum_required"] == 3
    assert data["message"] is None
    assert data["averages"]["workload_manageability"] == 4.0
    assert data["averages"]["work_life_balance"] == 3.0
    assert data["averages"]["team_support"] == 4.33
    assert data["averages"]["engagement"] == 2.33

    # Ensure no privacy leaks
    assert "Secret comment" not in str(data)
    assert str(emp1["_id"]) not in str(data)
    assert "emp1@example.com" not in str(data)


def test_manager_cannot_access_unmanaged_team(test_setup):
    client, fake_db = test_setup
    mgr1 = create_user(fake_db, email="mgr1@example.com", role="manager")
    mgr2 = create_user(fake_db, email="mgr2@example.com", role="manager")
    team2 = create_team(fake_db, name="Beta Team", manager_id=mgr2["_id"])

    token1 = make_token(mgr1["_id"])
    res = client.get(f"/pulse-surveys/team-summary?team_id={team2['_id']}", headers={"Authorization": f"Bearer {token1}"})
    assert res.status_code == 403
    assert "not authorized" in res.json()["detail"].lower()


def test_manager_team_summary_validation_errors(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    token = make_token(mgr["_id"])

    # 1. Missing team_id query parameter
    res1 = client.get("/pulse-surveys/team-summary", headers={"Authorization": f"Bearer {token}"})
    assert res1.status_code == 422

    # 2. Invalid team_id ObjectId
    res2 = client.get("/pulse-surveys/team-summary?team_id=invalid-oid", headers={"Authorization": f"Bearer {token}"})
    assert res2.status_code == 400

    # 3. Nonexistent team
    res3 = client.get(f"/pulse-surveys/team-summary?team_id={ObjectId()}", headers={"Authorization": f"Bearer {token}"})
    assert res3.status_code == 404

    # 4. Invalid date format
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    res4 = client.get(f"/pulse-surveys/team-summary?team_id={team['_id']}&week_start=2026-13-45", headers={"Authorization": f"Bearer {token}"})
    assert res4.status_code == 400

    # 5. Non-Monday date (2026-09-22 is Tuesday)
    res5 = client.get(f"/pulse-surveys/team-summary?team_id={team['_id']}&week_start=2026-09-22", headers={"Authorization": f"Bearer {token}"})
    assert res5.status_code == 400
    assert "must be a monday" in res5.json()["detail"].lower()


# =============================================================================
# 4. Admin Audit & Summary Tests (Endpoints 4 & 5)
# =============================================================================


def test_admin_audit_listing_privacy_safe_and_filterable(test_setup):
    client, fake_db = test_setup
    admin = create_user(fake_db, email="admin@example.com", role="admin")
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team1 = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    team2 = create_team(fake_db, name="Beta Team", manager_id=mgr["_id"])
    emp1 = create_user(fake_db, email="emp1@example.com", role="employee", team_id=team1["_id"])
    emp2 = create_user(fake_db, email="emp2@example.com", role="employee", team_id=team2["_id"])

    ws1 = datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)
    ws2 = datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc)

    # Team 1 week 1
    fake_db["weekly_pulse_responses"].docs.append({
        "_id": ObjectId(), "user_id": emp1["_id"], "team_id": team1["_id"], "week_start": ws1,
        "workload_manageability": 5, "work_life_balance": 5, "team_support": 5, "engagement": 5,
        "optional_comment": "Top secret comment", "submitted_at": ws1,
    })
    # Team 1 week 2
    fake_db["weekly_pulse_responses"].docs.append({
        "_id": ObjectId(), "user_id": emp1["_id"], "team_id": team1["_id"], "week_start": ws2,
        "workload_manageability": 4, "work_life_balance": 4, "team_support": 4, "engagement": 4,
        "optional_comment": "Top secret comment 2", "submitted_at": ws2,
    })
    # Team 2 week 2
    fake_db["weekly_pulse_responses"].docs.append({
        "_id": ObjectId(), "user_id": emp2["_id"], "team_id": team2["_id"], "week_start": ws2,
        "workload_manageability": 3, "work_life_balance": 3, "team_support": 3, "engagement": 3,
        "optional_comment": "Top secret comment 3", "submitted_at": ws2,
    })

    admin_token = make_token(admin["_id"])

    # 1. Unfiltered list
    res = client.get("/admin/pulse-surveys", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3

    # Check that privacy is strictly maintained: no user_id, ratings, or comments
    for item in data["items"]:
        assert "user_id" not in item
        assert "workload_manageability" not in item
        assert "optional_comment" not in item
        assert "team_id" in item
        assert "team_name" in item
        assert "week_start" in item
        assert "submitted_at" in item
    assert "Top secret" not in str(data)
    assert str(emp1["_id"]) not in str(data)

    # 2. Filter by team
    res_team = client.get(f"/admin/pulse-surveys?team_id={team1['_id']}", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_team.status_code == 200
    assert res_team.json()["total"] == 2

    # 3. Filter by week
    res_week = client.get("/admin/pulse-surveys?week_start=2026-09-14", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_week.status_code == 200
    assert res_week.json()["total"] == 1


def test_admin_summary_applies_threshold_independently_per_team(test_setup):
    client, fake_db = test_setup
    admin = create_user(fake_db, email="admin@example.com", role="admin")
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team1 = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    team2 = create_team(fake_db, name="Beta Team", manager_id=mgr["_id"])

    ws = datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc)

    # Seed 3 responses for team1 (>= 3)
    for i in range(3):
        fake_db["weekly_pulse_responses"].docs.append({
            "_id": ObjectId(), "user_id": ObjectId(), "team_id": team1["_id"], "week_start": ws,
            "workload_manageability": 4, "work_life_balance": 4, "team_support": 4, "engagement": 4,
            "optional_comment": f"Comment {i}", "submitted_at": ws,
        })

    # Seed 1 response for team2 (< 3)
    fake_db["weekly_pulse_responses"].docs.append({
        "_id": ObjectId(), "user_id": ObjectId(), "team_id": team2["_id"], "week_start": ws,
        "workload_manageability": 5, "work_life_balance": 5, "team_support": 5, "engagement": 5,
        "optional_comment": "Comment T2", "submitted_at": ws,
    })

    admin_token = make_token(admin["_id"])
    res = client.get("/admin/pulse-surveys/summary?week_start=2026-09-21", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    data = res.json()

    assert data["week_start"] == ws.isoformat()
    assert len(data["items"]) == 2

    # Alpha Team (team1)
    alpha_summary = next(item for item in data["items"] if item["team_name"] == "Alpha Team")
    assert alpha_summary["available"] is True
    assert alpha_summary["response_count"] == 3
    assert alpha_summary["averages"]["workload_manageability"] == 4.0

    # Beta Team (team2)
    beta_summary = next(item for item in data["items"] if item["team_name"] == "Beta Team")
    assert beta_summary["available"] is False
    assert beta_summary["response_count"] == 1
    assert beta_summary["averages"] is None
    assert "Insufficient responses" in beta_summary["message"]

    # Ensure no privacy leaks
    assert "Comment" not in str(data)


def test_rbac_boundary_for_pulse_survey_routes(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    emp = create_user(fake_db, email="emp@example.com", role="employee")
    admin = create_user(fake_db, email="admin@example.com", role="admin")

    emp_token = make_token(emp["_id"])
    mgr_token = make_token(mgr["_id"])
    admin_token = make_token(admin["_id"])

    # Employee cannot access admin audit routes
    res_emp_admin = client.get("/admin/pulse-surveys", headers={"Authorization": f"Bearer {emp_token}"})
    assert res_emp_admin.status_code == 403

    # Manager cannot access admin audit routes
    res_mgr_admin = client.get("/admin/pulse-surveys", headers={"Authorization": f"Bearer {mgr_token}"})
    assert res_mgr_admin.status_code == 403

    # Employee cannot access manager summary route
    res_emp_mgr = client.get(f"/pulse-surveys/team-summary?team_id={ObjectId()}", headers={"Authorization": f"Bearer {emp_token}"})
    assert res_emp_mgr.status_code == 403

    # Manager cannot access employee my-responses route
    res_mgr_emp = client.get("/pulse-surveys/my-responses", headers={"Authorization": f"Bearer {mgr_token}"})
    assert res_mgr_emp.status_code == 403

    # Admin cannot access employee my-responses route
    res_admin_emp = client.get("/pulse-surveys/my-responses", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_admin_emp.status_code == 403

    # Admin cannot submit response
    res_admin_post = client.post(
        "/pulse-surveys/responses",
        json={"workload_manageability": 4, "work_life_balance": 4, "team_support": 4, "engagement": 4},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_admin_post.status_code == 403


# =============================================================================
# 5. Database Sanitization & Error Handling Tests
# =============================================================================


def test_database_error_sanitization_on_submit(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])
    token = make_token(emp["_id"])

    with patch.object(fake_db["weekly_pulse_responses"], "find_one", side_effect=PyMongoError("Raw DB Error")):
        res = client.post(
            "/pulse-surveys/responses",
            json={"workload_manageability": 4, "work_life_balance": 4, "team_support": 4, "engagement": 4},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 503
        assert res.json()["detail"] == "Database unavailable"
        assert "Raw DB Error" not in res.text


def test_database_error_sanitization_on_my_responses(test_setup):
    client, fake_db = test_setup
    emp = create_user(fake_db, email="emp@example.com", role="employee")
    token = make_token(emp["_id"])

    with patch.object(fake_db["weekly_pulse_responses"], "count_documents", side_effect=PyMongoError("Raw DB Error")):
        res = client.get("/pulse-surveys/my-responses", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 503
        assert res.json()["detail"] == "Database unavailable"
        assert "Raw DB Error" not in res.text


def test_database_error_sanitization_on_team_summary(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    token = make_token(mgr["_id"])

    with patch.object(fake_db["teams"], "find_one", side_effect=PyMongoError("Raw DB Error")):
        res = client.get(f"/pulse-surveys/team-summary?team_id={team['_id']}", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 503
        assert res.json()["detail"] == "Database unavailable"
        assert "Raw DB Error" not in res.text


def test_database_error_sanitization_on_admin_audit(test_setup):
    client, fake_db = test_setup
    admin = create_user(fake_db, email="admin@example.com", role="admin")
    token = make_token(admin["_id"])

    with patch.object(fake_db["weekly_pulse_responses"], "count_documents", side_effect=PyMongoError("Raw DB Error")):
        res = client.get("/admin/pulse-surveys", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 503
        assert res.json()["detail"] == "Database unavailable"
        assert "Raw DB Error" not in res.text


def test_database_error_sanitization_on_admin_summary(test_setup):
    client, fake_db = test_setup
    admin = create_user(fake_db, email="admin@example.com", role="admin")
    token = make_token(admin["_id"])

    with patch.object(fake_db["teams"], "find", side_effect=PyMongoError("Raw DB Error")):
        res = client.get("/admin/pulse-surveys/summary", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 503
        assert res.json()["detail"] == "Database unavailable"
        assert "Raw DB Error" not in res.text


# =============================================================================
# 6. Additional Dedicated Compliance Tests
# =============================================================================


def test_compound_unique_index_in_fake_db(fake_db):
    user_id = ObjectId()
    ws = datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc)

    # First insert succeeds
    fake_db["weekly_pulse_responses"].docs.append({
        "_id": ObjectId(), "user_id": user_id, "week_start": ws, "workload_manageability": 3,
    })

    # Second insert with same user_id and week_start must raise DuplicateKeyError via insert_one
    import asyncio
    with pytest.raises(DuplicateKeyError):
        asyncio.run(fake_db["weekly_pulse_responses"].insert_one({
            "user_id": user_id, "week_start": ws, "workload_manageability": 4,
        }))


def test_employee_cannot_filter_or_request_another_user_history(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp1 = create_user(fake_db, email="emp1@example.com", role="employee", team_id=team["_id"])
    emp2 = create_user(fake_db, email="emp2@example.com", role="employee", team_id=team["_id"])

    ws = datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc)
    fake_db["weekly_pulse_responses"].docs.append({
        "_id": ObjectId(), "user_id": emp2["_id"], "team_id": team["_id"], "week_start": ws,
        "workload_manageability": 5, "work_life_balance": 5, "team_support": 5, "engagement": 5,
        "optional_comment": "Emp2 private comment", "submitted_at": ws,
    })

    token1 = make_token(emp1["_id"])
    # Employee 1 attempts to pass user_id parameter to view Employee 2's responses
    res = client.get(f"/pulse-surveys/my-responses?user_id={emp2['_id']}", headers={"Authorization": f"Bearer {token1}"})
    assert res.status_code == 200
    data = res.json()
    # Must only return Employee 1's records (which is 0)
    assert data["total"] == 0
    assert len(data["items"]) == 0
    assert "Emp2 private comment" not in res.text


def test_admin_audit_pagination(test_setup):
    client, fake_db = test_setup
    admin = create_user(fake_db, email="admin@example.com", role="admin")
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])

    for i in range(5):
        ws = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc) + timedelta(weeks=i)
        fake_db["weekly_pulse_responses"].docs.append({
            "_id": ObjectId(), "user_id": ObjectId(), "team_id": team["_id"], "week_start": ws,
            "workload_manageability": 3, "work_life_balance": 3, "team_support": 3, "engagement": 3,
            "optional_comment": f"Comment {i}", "submitted_at": ws,
        })

    token = make_token(admin["_id"])
    res = client.get("/admin/pulse-surveys?page=2&limit=2", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 5
    assert data["page"] == 2
    assert data["limit"] == 2
    assert data["total_pages"] == 3
    assert len(data["items"]) == 2

def test_required_indexes_configured_in_fake_db(fake_db):
    pulse_indexes = fake_db["weekly_pulse_responses"].indexes
    assert (("user_id", 1), ("week_start", -1)) in pulse_indexes
    assert pulse_indexes[(("user_id", 1), ("week_start", -1))]["unique"] is True
    assert (("team_id", 1), ("week_start", -1)) in pulse_indexes
    assert pulse_indexes[(("team_id", 1), ("week_start", -1))]["unique"] is False


# =============================================================================
# 7. Employee Response Current-Week Edit Tests (PATCH /pulse-surveys/responses/{id})
# =============================================================================


def test_own_current_week_edit_succeeds(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])
    token = make_token(emp["_id"])

    # Submit initial response
    create_res = client.post(
        "/pulse-surveys/responses",
        json={"workload_manageability": 3, "work_life_balance": 3, "team_support": 3, "engagement": 3, "optional_comment": "Initial comment"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_res.status_code == 201
    resp_id = create_res.json()["id"]

    # Edit the response
    patch_payload = {
        "workload_manageability": 5,
        "work_life_balance": 4,
        "team_support": 5,
        "engagement": 4,
        "optional_comment": "Updated reflection note",
        "expected_revision": 1,
    }
    patch_res = client.patch(
        f"/pulse-surveys/responses/{resp_id}",
        json=patch_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert patch_res.status_code == 200
    data = patch_res.json()

    assert data["id"] == resp_id
    assert data["workload_manageability"] == 5
    assert data["work_life_balance"] == 4
    assert data["team_support"] == 5
    assert data["engagement"] == 4
    assert data["optional_comment"] == "Updated reflection note"
    assert data["is_edited"] is True
    assert data["revision"] == 2
    assert data["updated_at"] is not None
    assert data["submitted_at"] == create_res.json()["submitted_at"]
    assert data["week_start"] == create_res.json()["week_start"]

    # Verify internal edit_history in fake_db
    stored_doc = fake_db["weekly_pulse_responses"].docs[0]
    assert stored_doc["revision"] == 2
    assert stored_doc["is_edited"] is True
    assert len(stored_doc["edit_history"]) == 1
    hist = stored_doc["edit_history"][0]
    assert hist["revision"] == 1
    assert hist["workload_manageability"] == 3
    assert hist["optional_comment"] == "Initial comment"
    assert hist["edited_by"] == emp["_id"]


def test_previous_week_edit_is_rejected(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])
    token = make_token(emp["_id"])

    # Seed past-week response
    past_ws = get_current_week_start() - timedelta(weeks=1)
    fake_db["weekly_pulse_responses"].docs.append({
        "_id": ObjectId(),
        "user_id": emp["_id"],
        "team_id": team["_id"],
        "week_start": past_ws,
        "workload_manageability": 3,
        "work_life_balance": 3,
        "team_support": 3,
        "engagement": 3,
        "optional_comment": "Old week",
        "submitted_at": past_ws,
        "revision": 1,
    })
    resp_id = str(fake_db["weekly_pulse_responses"].docs[0]["_id"])

    patch_res = client.patch(
        f"/pulse-surveys/responses/{resp_id}",
        json={"workload_manageability": 5, "expected_revision": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert patch_res.status_code == 400
    assert "Previous-week responses are read-only" in patch_res.json()["detail"]


def test_another_employee_response_cannot_be_edited(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp1 = create_user(fake_db, email="emp1@example.com", role="employee", team_id=team["_id"])
    emp2 = create_user(fake_db, email="emp2@example.com", role="employee", team_id=team["_id"])

    token1 = make_token(emp1["_id"])
    token2 = make_token(emp2["_id"])

    # emp1 submits
    create_res = client.post(
        "/pulse-surveys/responses",
        json={"workload_manageability": 3, "work_life_balance": 3, "team_support": 3, "engagement": 3},
        headers={"Authorization": f"Bearer {token1}"},
    )
    resp_id = create_res.json()["id"]

    # emp2 attempts to edit emp1's response
    patch_res = client.patch(
        f"/pulse-surveys/responses/{resp_id}",
        json={"workload_manageability": 5, "expected_revision": 1},
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert patch_res.status_code == 403
    assert "You can only edit your own pulse survey response" in patch_res.json()["detail"]


def test_manager_and_admin_cannot_edit_pulse_survey(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    admin = create_user(fake_db, email="admin@example.com", role="admin")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])

    emp_token = make_token(emp["_id"])
    mgr_token = make_token(mgr["_id"])
    admin_token = make_token(admin["_id"])

    create_res = client.post(
        "/pulse-surveys/responses",
        json={"workload_manageability": 3, "work_life_balance": 3, "team_support": 3, "engagement": 3},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    resp_id = create_res.json()["id"]

    # Manager attempts edit
    res_mgr = client.patch(
        f"/pulse-surveys/responses/{resp_id}",
        json={"workload_manageability": 5, "expected_revision": 1},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_mgr.status_code == 403

    # Admin attempts edit
    res_admin = client.patch(
        f"/pulse-surveys/responses/{resp_id}",
        json={"workload_manageability": 5, "expected_revision": 1},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_admin.status_code == 403


def test_unauthenticated_edit_rejected(test_setup):
    client, fake_db = test_setup
    res = client.patch(
        f"/pulse-surveys/responses/{ObjectId()}",
        json={"workload_manageability": 4, "expected_revision": 1},
    )
    assert res.status_code == 401


def test_invalid_ratings_and_forged_fields_rejected(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])
    token = make_token(emp["_id"])

    create_res = client.post(
        "/pulse-surveys/responses",
        json={"workload_manageability": 3, "work_life_balance": 3, "team_support": 3, "engagement": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp_id = create_res.json()["id"]

    # 1. Rating out of bounds (< 1)
    res1 = client.patch(f"/pulse-surveys/responses/{resp_id}", json={"workload_manageability": 0, "expected_revision": 1}, headers={"Authorization": f"Bearer {token}"})
    assert res1.status_code == 422

    # 2. Rating out of bounds (> 5)
    res2 = client.patch(f"/pulse-surveys/responses/{resp_id}", json={"workload_manageability": 6, "expected_revision": 1}, headers={"Authorization": f"Bearer {token}"})
    assert res2.status_code == 422

    # 3. Explicit null rating
    res3 = client.patch(f"/pulse-surveys/responses/{resp_id}", json={"workload_manageability": None, "expected_revision": 1}, headers={"Authorization": f"Bearer {token}"})
    assert res3.status_code == 422

    # 4. Forged field (user_id / team_id / week_start)
    res4 = client.patch(f"/pulse-surveys/responses/{resp_id}", json={"user_id": str(ObjectId()), "expected_revision": 1}, headers={"Authorization": f"Bearer {token}"})
    assert res4.status_code == 422

    # 5. Empty update
    res5 = client.patch(f"/pulse-surveys/responses/{resp_id}", json={}, headers={"Authorization": f"Bearer {token}"})
    assert res5.status_code == 422


def test_missing_expected_revision_rejected_with_422(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])
    token = make_token(emp["_id"])

    create_res = client.post(
        "/pulse-surveys/responses",
        json={"workload_manageability": 3, "work_life_balance": 3, "team_support": 3, "engagement": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp_id = create_res.json()["id"]

    # Missing expected_revision field
    res1 = client.patch(
        f"/pulse-surveys/responses/{resp_id}",
        json={"workload_manageability": 4},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res1.status_code == 422

    # Invalid expected_revision (< 1)
    res2 = client.patch(
        f"/pulse-surveys/responses/{resp_id}",
        json={"workload_manageability": 4, "expected_revision": 0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res2.status_code == 422

    # Invalid expected_revision (non-integer string)
    res3 = client.patch(
        f"/pulse-surveys/responses/{resp_id}",
        json={"workload_manageability": 4, "expected_revision": "abc"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res3.status_code == 422


def test_only_expected_revision_without_editable_fields_rejected_with_422(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])
    token = make_token(emp["_id"])

    create_res = client.post(
        "/pulse-surveys/responses",
        json={"workload_manageability": 3, "work_life_balance": 3, "team_support": 3, "engagement": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp_id = create_res.json()["id"]

    # Only expected_revision provided, no ratings or comment
    res = client.patch(
        f"/pulse-surveys/responses/{resp_id}",
        json={"expected_revision": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422
    assert "At least one rating or optional_comment field must be provided" in res.json()["detail"]


def test_omitted_vs_cleared_comment_behaves_correctly(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])
    token = make_token(emp["_id"])

    create_res = client.post(
        "/pulse-surveys/responses",
        json={"workload_manageability": 3, "work_life_balance": 3, "team_support": 3, "engagement": 3, "optional_comment": "Keep this comment"},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp_id = create_res.json()["id"]

    # Edit without optional_comment -> comment must remain unchanged
    res1 = client.patch(f"/pulse-surveys/responses/{resp_id}", json={"workload_manageability": 4, "expected_revision": 1}, headers={"Authorization": f"Bearer {token}"})
    assert res1.status_code == 200
    assert res1.json()["optional_comment"] == "Keep this comment"
    assert res1.json()["revision"] == 2

    # Edit with optional_comment: null -> comment must be cleared
    res2 = client.patch(f"/pulse-surveys/responses/{resp_id}", json={"optional_comment": None, "expected_revision": 2}, headers={"Authorization": f"Bearer {token}"})
    assert res2.status_code == 200
    assert res2.json()["optional_comment"] is None
    assert res2.json()["revision"] == 3


def test_original_submission_metadata_unchanged_and_team_switch_preserved(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team1 = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    team2 = create_team(fake_db, name="Beta Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team1["_id"])
    token = make_token(emp["_id"])

    create_res = client.post(
        "/pulse-surveys/responses",
        json={"workload_manageability": 3, "work_life_balance": 3, "team_support": 3, "engagement": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp_id = create_res.json()["id"]
    orig_submitted_at = create_res.json()["submitted_at"]

    # Employee changes team assignment in DB
    emp["team_id"] = team2["_id"]

    # Edit the pulse response
    patch_res = client.patch(
        f"/pulse-surveys/responses/{resp_id}",
        json={"workload_manageability": 5, "expected_revision": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert patch_res.status_code == 200
    data = patch_res.json()

    # Original team_id must NOT be moved to team2
    assert data["team_id"] == str(team1["_id"])
    assert data["team_name"] == "Alpha Team"
    assert data["submitted_at"] == orig_submitted_at


def test_editing_keeps_response_count_unchanged_and_updates_aggregate_averages(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp1 = create_user(fake_db, email="emp1@example.com", role="employee", team_id=team["_id"])
    emp2 = create_user(fake_db, email="emp2@example.com", role="employee", team_id=team["_id"])
    emp3 = create_user(fake_db, email="emp3@example.com", role="employee", team_id=team["_id"])

    token1 = make_token(emp1["_id"])
    token2 = make_token(emp2["_id"])
    token3 = make_token(emp3["_id"])
    mgr_token = make_token(mgr["_id"])

    # 3 employees submit responses
    res1 = client.post("/pulse-surveys/responses", json={"workload_manageability": 2, "work_life_balance": 2, "team_support": 2, "engagement": 2}, headers={"Authorization": f"Bearer {token1}"})
    client.post("/pulse-surveys/responses", json={"workload_manageability": 3, "work_life_balance": 3, "team_support": 3, "engagement": 3}, headers={"Authorization": f"Bearer {token2}"})
    client.post("/pulse-surveys/responses", json={"workload_manageability": 4, "work_life_balance": 4, "team_support": 4, "engagement": 4}, headers={"Authorization": f"Bearer {token3}"})

    resp1_id = res1.json()["id"]

    # Initial manager summary: averages 3.0, count 3
    summary1 = client.get(f"/pulse-surveys/team-summary?team_id={team['_id']}", headers={"Authorization": f"Bearer {mgr_token}"}).json()
    assert summary1["response_count"] == 3
    assert summary1["averages"]["workload_manageability"] == 3.0

    # emp1 updates their workload_manageability from 2 to 5
    client.patch(f"/pulse-surveys/responses/{resp1_id}", json={"workload_manageability": 5, "expected_revision": 1}, headers={"Authorization": f"Bearer {token1}"})

    # Updated manager summary: (5 + 3 + 4) / 3 = 4.0, count remains 3
    summary2 = client.get(f"/pulse-surveys/team-summary?team_id={team['_id']}", headers={"Authorization": f"Bearer {mgr_token}"}).json()
    assert summary2["response_count"] == 3
    assert summary2["averages"]["workload_manageability"] == 4.0


def test_concurrent_stale_edits_rejected(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])
    token = make_token(emp["_id"])

    create_res = client.post(
        "/pulse-surveys/responses",
        json={"workload_manageability": 3, "work_life_balance": 3, "team_support": 3, "engagement": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp_id = create_res.json()["id"]

    # First update succeeds (revision moves from 1 to 2)
    res1 = client.patch(
        f"/pulse-surveys/responses/{resp_id}",
        json={"workload_manageability": 4, "expected_revision": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res1.status_code == 200

    # Stale second update with expected_revision=1 is rejected
    res2 = client.patch(
        f"/pulse-surveys/responses/{resp_id}",
        json={"workload_manageability": 5, "expected_revision": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res2.status_code == 409
    assert "modified concurrently" in res2.json()["detail"]


def test_two_edits_using_same_expected_revision_cannot_both_succeed(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])
    token = make_token(emp["_id"])

    create_res = client.post(
        "/pulse-surveys/responses",
        json={"workload_manageability": 3, "work_life_balance": 3, "team_support": 3, "engagement": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp_id = create_res.json()["id"]

    # Request A with expected_revision = 1 succeeds
    res_a = client.patch(
        f"/pulse-surveys/responses/{resp_id}",
        json={"workload_manageability": 4, "expected_revision": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_a.status_code == 200
    assert res_a.json()["revision"] == 2

    # Request B with the same expected_revision = 1 must fail with 409
    res_b = client.patch(
        f"/pulse-surveys/responses/{resp_id}",
        json={"workload_manageability": 5, "expected_revision": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_b.status_code == 409
    assert "modified concurrently" in res_b.json()["detail"]


def test_revision_history_preserved_in_db_but_absent_from_manager_admin_apis(test_setup):
    client, fake_db = test_setup
    admin = create_user(fake_db, email="admin@example.com", role="admin")
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])

    token = make_token(emp["_id"])
    admin_token = make_token(admin["_id"])
    mgr_token = make_token(mgr["_id"])

    create_res = client.post(
        "/pulse-surveys/responses",
        json={"workload_manageability": 3, "work_life_balance": 3, "team_support": 3, "engagement": 3, "optional_comment": "Secret 1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp_id = create_res.json()["id"]

    client.patch(
        f"/pulse-surveys/responses/{resp_id}",
        json={"workload_manageability": 4, "optional_comment": "Secret 2", "expected_revision": 1},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Check Manager API does not leak edit history or comments
    mgr_res = client.get(f"/pulse-surveys/team-summary?team_id={team['_id']}", headers={"Authorization": f"Bearer {mgr_token}"})
    assert "edit_history" not in mgr_res.text
    assert "Secret 1" not in mgr_res.text
    assert "Secret 2" not in mgr_res.text

    # Check Admin API does not leak edit history or comments
    admin_res = client.get("/admin/pulse-surveys", headers={"Authorization": f"Bearer {admin_token}"})
    assert "edit_history" not in admin_res.text
    assert "Secret 1" not in admin_res.text
    assert "Secret 2" not in admin_res.text


def test_legacy_records_remain_usable(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])
    token = make_token(emp["_id"])

    # Legacy record without revision, is_edited, updated_at, edit_history
    current_ws = get_current_week_start()
    fake_db["weekly_pulse_responses"].docs.append({
        "_id": ObjectId(),
        "user_id": emp["_id"],
        "team_id": team["_id"],
        "week_start": current_ws,
        "workload_manageability": 2,
        "work_life_balance": 2,
        "team_support": 2,
        "engagement": 2,
        "submitted_at": current_ws,
    })
    resp_id = str(fake_db["weekly_pulse_responses"].docs[0]["_id"])

    patch_res = client.patch(
        f"/pulse-surveys/responses/{resp_id}",
        json={"workload_manageability": 5, "engagement": 5, "expected_revision": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert patch_res.status_code == 200
    data = patch_res.json()
    assert data["workload_manageability"] == 5
    assert data["engagement"] == 5
    assert data["is_edited"] is True
    assert data["revision"] == 2


def test_legacy_record_revision_mismatch_rejected(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])
    token = make_token(emp["_id"])

    # Legacy record without revision
    current_ws = get_current_week_start()
    fake_db["weekly_pulse_responses"].docs.append({
        "_id": ObjectId(),
        "user_id": emp["_id"],
        "team_id": team["_id"],
        "week_start": current_ws,
        "workload_manageability": 2,
        "work_life_balance": 2,
        "team_support": 2,
        "engagement": 2,
        "submitted_at": current_ws,
    })
    resp_id = str(fake_db["weekly_pulse_responses"].docs[0]["_id"])

    # Expected revision 2 for legacy record (which is treated as revision 1) must be rejected with 409
    patch_res = client.patch(
        f"/pulse-surveys/responses/{resp_id}",
        json={"workload_manageability": 5, "expected_revision": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert patch_res.status_code == 409
    assert "modified concurrently" in patch_res.json()["detail"]