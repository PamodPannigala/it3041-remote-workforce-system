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


# =========================================================================
# 1. Message Creation Tests
# =========================================================================


def test_employee_creates_valid_message_in_own_team(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager", name="Team Manager")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", name="Alice Worker", team_id=team["_id"])

    token = make_token(emp["_id"])
    payload = {"team_id": str(team["_id"]), "content": "Hello team, starting work on component A."}

    res = client.post("/collaboration/messages", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 201
    data = res.json()
    assert data["content"] == "Hello team, starting work on component A."
    assert data["team_id"] == str(team["_id"])
    assert data["sender_id"] == str(emp["_id"])
    assert data["sender_name"] == "Alice Worker"
    assert data["sender_email"] == "emp@example.com"
    assert data["team_name"] == "Alpha Team"
    assert data["is_deleted"] is False
    assert data["deleted_at"] is None
    assert data["edited_at"] is None
    assert "id" in data
    assert data["created_at"] is not None


def test_manager_creates_valid_message_in_managed_team(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager", name="Bob Manager")
    team = create_team(fake_db, name="Beta Team", manager_id=mgr["_id"])

    token = make_token(mgr["_id"])
    payload = {"team_id": str(team["_id"]), "content": "Sprint goals are published."}

    res = client.post("/collaboration/messages", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 201
    data = res.json()
    assert data["content"] == "Sprint goals are published."
    assert data["sender_name"] == "Bob Manager"
    assert data["team_name"] == "Beta Team"


def test_employee_cannot_post_to_another_team(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team1 = create_team(fake_db, name="Team 1", manager_id=mgr["_id"])
    team2 = create_team(fake_db, name="Team 2", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team1["_id"])

    token = make_token(emp["_id"])
    payload = {"team_id": str(team2["_id"]), "content": "Cross-team unauthorized message"}

    res = client.post("/collaboration/messages", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403
    assert "assigned team" in res.json()["detail"].lower()


def test_manager_cannot_post_to_unmanaged_team(test_setup):
    client, fake_db = test_setup
    mgr1 = create_user(fake_db, email="mgr1@example.com", role="manager")
    mgr2 = create_user(fake_db, email="mgr2@example.com", role="manager")
    team1 = create_team(fake_db, name="Team 1", manager_id=mgr1["_id"])

    token2 = make_token(mgr2["_id"])
    payload = {"team_id": str(team1["_id"]), "content": "Manager unmanaged post"}

    res = client.post("/collaboration/messages", json=payload, headers={"Authorization": f"Bearer {token2}"})
    assert res.status_code == 403
    assert "do not manage" in res.json()["detail"].lower()


def test_user_without_valid_team_scope_cannot_post(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Team 1", manager_id=mgr["_id"])
    unassigned_emp = create_user(fake_db, email="unassigned@example.com", role="employee", team_id=None)

    token = make_token(unassigned_emp["_id"])
    payload = {"team_id": str(team["_id"]), "content": "Unassigned post"}

    res = client.post("/collaboration/messages", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


def test_admin_cannot_create_message(test_setup):
    client, fake_db = test_setup
    admin = create_user(fake_db, email="admin@example.com", role="admin")
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Team 1", manager_id=mgr["_id"])

    token = make_token(admin["_id"])
    payload = {"team_id": str(team["_id"]), "content": "Admin trying to post"}

    res = client.post("/collaboration/messages", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


def test_post_message_to_nonexistent_team_returns_404(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    token = make_token(mgr["_id"])
    fake_team_id = str(ObjectId())

    payload = {"team_id": fake_team_id, "content": "Nonexistent team post"}
    res = client.post("/collaboration/messages", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 404


def test_sender_cannot_be_impersonated_via_payload(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Team 1", manager_id=mgr["_id"])
    emp1 = create_user(fake_db, email="emp1@example.com", role="employee", team_id=team["_id"])
    emp2 = create_user(fake_db, email="emp2@example.com", role="employee", team_id=team["_id"])

    token = make_token(emp1["_id"])
    # extra field should be rejected with 422
    payload = {"team_id": str(team["_id"]), "content": "Impersonation test", "sender_id": str(emp2["_id"])}
    res = client.post("/collaboration/messages", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 422


# =========================================================================
# 2. Message Listing Tests
# =========================================================================


def test_employee_lists_only_own_team_messages(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team1 = create_team(fake_db, name="Team 1", manager_id=mgr["_id"])
    team2 = create_team(fake_db, name="Team 2", manager_id=mgr["_id"])
    emp1 = create_user(fake_db, email="emp1@example.com", role="employee", team_id=team1["_id"])
    emp2 = create_user(fake_db, email="emp2@example.com", role="employee", team_id=team2["_id"])

    t1 = datetime.now(timezone.utc) - timedelta(minutes=10)
    t2 = datetime.now(timezone.utc) - timedelta(minutes=5)
    msg1 = {
        "_id": ObjectId(),
        "team_id": team1["_id"],
        "sender_id": emp1["_id"],
        "content": "Message in Team 1",
        "created_at": t1,
        "updated_at": t1,
        "edited_at": None,
        "is_deleted": False,
        "deleted_at": None,
        "deleted_by": None,
    }
    msg2 = {
        "_id": ObjectId(),
        "team_id": team2["_id"],
        "sender_id": emp2["_id"],
        "content": "Message in Team 2",
        "created_at": t2,
        "updated_at": t2,
        "edited_at": None,
        "is_deleted": False,
        "deleted_at": None,
        "deleted_by": None,
    }
    fake_db["collaboration_messages"].docs.extend([msg1, msg2])

    token1 = make_token(emp1["_id"])
    res = client.get("/collaboration/messages", headers={"Authorization": f"Bearer {token1}"})
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["content"] == "Message in Team 1"
    assert data["items"][0]["team_id"] == str(team1["_id"])


def test_employee_querying_another_team_returns_403(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team1 = create_team(fake_db, name="Team 1", manager_id=mgr["_id"])
    team2 = create_team(fake_db, name="Team 2", manager_id=mgr["_id"])
    emp1 = create_user(fake_db, email="emp1@example.com", role="employee", team_id=team1["_id"])

    token = make_token(emp1["_id"])
    res = client.get(f"/collaboration/messages?team_id={team2['_id']}", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


def test_manager_lists_only_managed_team_messages(test_setup):
    client, fake_db = test_setup
    mgr1 = create_user(fake_db, email="mgr1@example.com", role="manager")
    mgr2 = create_user(fake_db, email="mgr2@example.com", role="manager")
    team1 = create_team(fake_db, name="Team 1", manager_id=mgr1["_id"])
    team2 = create_team(fake_db, name="Team 2", manager_id=mgr2["_id"])

    msg1 = {
        "_id": ObjectId(),
        "team_id": team1["_id"],
        "sender_id": mgr1["_id"],
        "content": "Team 1 announcement",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "edited_at": None,
        "is_deleted": False,
        "deleted_at": None,
        "deleted_by": None,
    }
    fake_db["collaboration_messages"].docs.append(msg1)

    token1 = make_token(mgr1["_id"])
    res = client.get(f"/collaboration/messages?team_id={team1['_id']}", headers={"Authorization": f"Bearer {token1}"})
    assert res.status_code == 200
    assert res.json()["total"] == 1

    # Attempt listing team 2 managed by mgr2
    res_unauth = client.get(f"/collaboration/messages?team_id={team2['_id']}", headers={"Authorization": f"Bearer {token1}"})
    assert res_unauth.status_code == 403


def test_manager_must_provide_team_id_when_listing(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    token = make_token(mgr["_id"])

    res = client.get("/collaboration/messages", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 400
    assert "team_id" in res.json()["detail"].lower()


# =========================================================================
# 3. Message Detail and Cross-Team Access Tests
# =========================================================================


def test_cross_team_detail_access_is_rejected(test_setup):
    client, fake_db = test_setup
    mgr1 = create_user(fake_db, email="mgr1@example.com", role="manager")
    mgr2 = create_user(fake_db, email="mgr2@example.com", role="manager")
    team1 = create_team(fake_db, name="Team 1", manager_id=mgr1["_id"])
    team2 = create_team(fake_db, name="Team 2", manager_id=mgr2["_id"])
    emp2 = create_user(fake_db, email="emp2@example.com", role="employee", team_id=team2["_id"])

    msg = {
        "_id": ObjectId(),
        "team_id": team1["_id"],
        "sender_id": mgr1["_id"],
        "content": "Secret team 1 note",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "edited_at": None,
        "is_deleted": False,
        "deleted_at": None,
        "deleted_by": None,
    }
    fake_db["collaboration_messages"].docs.append(msg)

    # Employee in team 2 attempts to view team 1 message
    emp2_token = make_token(emp2["_id"])
    res = client.get(f"/collaboration/messages/{msg['_id']}", headers={"Authorization": f"Bearer {emp2_token}"})
    assert res.status_code == 403

    # Manager of team 2 attempts to view team 1 message
    mgr2_token = make_token(mgr2["_id"])
    res_mgr = client.get(f"/collaboration/messages/{msg['_id']}", headers={"Authorization": f"Bearer {mgr2_token}"})
    assert res_mgr.status_code == 403


# =========================================================================
# 4. Message Edit Tests
# =========================================================================


def test_original_sender_can_edit_message(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Team 1", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])

    msg = {
        "_id": ObjectId(),
        "team_id": team["_id"],
        "sender_id": emp["_id"],
        "content": "Initial text",
        "created_at": datetime.now(timezone.utc) - timedelta(minutes=5),
        "updated_at": datetime.now(timezone.utc) - timedelta(minutes=5),
        "edited_at": None,
        "is_deleted": False,
        "deleted_at": None,
        "deleted_by": None,
    }
    fake_db["collaboration_messages"].docs.append(msg)

    token = make_token(emp["_id"])
    update_payload = {"content": "Updated text"}

    res = client.patch(f"/collaboration/messages/{msg['_id']}", json=update_payload, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["content"] == "Updated text"
    assert data["edited_at"] is not None
    assert data["updated_at"] is not None


def test_another_employee_cannot_edit_message(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Team 1", manager_id=mgr["_id"])
    emp1 = create_user(fake_db, email="emp1@example.com", role="employee", team_id=team["_id"])
    emp2 = create_user(fake_db, email="emp2@example.com", role="employee", team_id=team["_id"])

    msg = {
        "_id": ObjectId(),
        "team_id": team["_id"],
        "sender_id": emp1["_id"],
        "content": "Emp1 message",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "edited_at": None,
        "is_deleted": False,
        "deleted_at": None,
        "deleted_by": None,
    }
    fake_db["collaboration_messages"].docs.append(msg)

    token2 = make_token(emp2["_id"])
    res = client.patch(f"/collaboration/messages/{msg['_id']}", json={"content": "Hacked"}, headers={"Authorization": f"Bearer {token2}"})
    assert res.status_code == 403
    assert "original sender" in res.json()["detail"].lower()


def test_manager_cannot_edit_employee_message(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Team 1", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])

    msg = {
        "_id": ObjectId(),
        "team_id": team["_id"],
        "sender_id": emp["_id"],
        "content": "Employee thought",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "edited_at": None,
        "is_deleted": False,
        "deleted_at": None,
        "deleted_by": None,
    }
    fake_db["collaboration_messages"].docs.append(msg)

    mgr_token = make_token(mgr["_id"])
    res = client.patch(f"/collaboration/messages/{msg['_id']}", json={"content": "Manager edit"}, headers={"Authorization": f"Bearer {mgr_token}"})
    assert res.status_code == 403


def test_deleted_message_cannot_be_edited(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Team 1", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])

    msg = {
        "_id": ObjectId(),
        "team_id": team["_id"],
        "sender_id": emp["_id"],
        "content": "Deleted note",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "edited_at": None,
        "is_deleted": True,
        "deleted_at": datetime.now(timezone.utc),
        "deleted_by": emp["_id"],
    }
    fake_db["collaboration_messages"].docs.append(msg)

    token = make_token(emp["_id"])
    res = client.patch(f"/collaboration/messages/{msg['_id']}", json={"content": "Try editing"}, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 409


# =========================================================================
# 5. Message Deletion Tests
# =========================================================================


def test_original_sender_can_soft_delete(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Team 1", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])

    msg = {
        "_id": ObjectId(),
        "team_id": team["_id"],
        "sender_id": emp["_id"],
        "content": "To be deleted",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "edited_at": None,
        "is_deleted": False,
        "deleted_at": None,
        "deleted_by": None,
    }
    fake_db["collaboration_messages"].docs.append(msg)

    token = make_token(emp["_id"])
    res = client.delete(f"/collaboration/messages/{msg['_id']}", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 204

    # Confirm soft deletion in database
    db_msg = fake_db["collaboration_messages"].docs[0]
    assert db_msg["is_deleted"] is True
    assert db_msg["deleted_at"] is not None
    assert db_msg["deleted_by"] == emp["_id"]
    assert db_msg["content"] == "To be deleted"  # content preserved in DB for audit


def test_another_user_cannot_delete_message(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Team 1", manager_id=mgr["_id"])
    emp1 = create_user(fake_db, email="emp1@example.com", role="employee", team_id=team["_id"])
    emp2 = create_user(fake_db, email="emp2@example.com", role="employee", team_id=team["_id"])

    msg = {
        "_id": ObjectId(),
        "team_id": team["_id"],
        "sender_id": emp1["_id"],
        "content": "Emp1 post",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "edited_at": None,
        "is_deleted": False,
        "deleted_at": None,
        "deleted_by": None,
    }
    fake_db["collaboration_messages"].docs.append(msg)

    token2 = make_token(emp2["_id"])
    res = client.delete(f"/collaboration/messages/{msg['_id']}", headers={"Authorization": f"Bearer {token2}"})
    assert res.status_code == 403


def test_duplicate_deletion_returns_409(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Team 1", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])

    msg = {
        "_id": ObjectId(),
        "team_id": team["_id"],
        "sender_id": emp["_id"],
        "content": "Already deleted",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "edited_at": None,
        "is_deleted": True,
        "deleted_at": datetime.now(timezone.utc),
        "deleted_by": emp["_id"],
    }
    fake_db["collaboration_messages"].docs.append(msg)

    token = make_token(emp["_id"])
    res = client.delete(f"/collaboration/messages/{msg['_id']}", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 409


def test_soft_deletion_does_not_remove_database_document(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Team 1", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])

    msg = {
        "_id": ObjectId(),
        "team_id": team["_id"],
        "sender_id": emp["_id"],
        "content": "Soft delete test",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "edited_at": None,
        "is_deleted": False,
        "deleted_at": None,
        "deleted_by": None,
    }
    fake_db["collaboration_messages"].docs.append(msg)

    token = make_token(emp["_id"])
    res = client.delete(f"/collaboration/messages/{msg['_id']}", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 204
    assert len(fake_db["collaboration_messages"].docs) == 1


def test_normal_team_users_see_null_content_for_deleted_messages(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager", name="Team Lead")
    team = create_team(fake_db, name="Alpha Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", name="Alice Worker", team_id=team["_id"])

    msg = {
        "_id": ObjectId(),
        "team_id": team["_id"],
        "sender_id": emp["_id"],
        "content": "Original secret text",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "edited_at": None,
        "is_deleted": True,
        "deleted_at": datetime.now(timezone.utc),
        "deleted_by": emp["_id"],
    }
    fake_db["collaboration_messages"].docs.append(msg)

    token = make_token(emp["_id"])
    # List endpoint
    res_list = client.get("/collaboration/messages", headers={"Authorization": f"Bearer {token}"})
    assert res_list.status_code == 200
    item = res_list.json()["items"][0]
    assert item["is_deleted"] is True
    assert item["content"] is None
    assert item["sender_name"] == "Alice Worker"

    # Detail endpoint
    res_detail = client.get(f"/collaboration/messages/{msg['_id']}", headers={"Authorization": f"Bearer {token}"})
    assert res_detail.status_code == 200
    detail_data = res_detail.json()
    assert detail_data["is_deleted"] is True
    assert detail_data["content"] is None


# =========================================================================
# 6. Admin Read-Only Audit Tests
# =========================================================================


def test_admin_audit_sees_deleted_history_and_stored_content(test_setup):
    client, fake_db = test_setup
    admin = create_user(fake_db, email="admin@example.com", role="admin", name="Admin User")
    mgr = create_user(fake_db, email="mgr@example.com", role="manager", name="Team Manager")
    team = create_team(fake_db, name="Secure Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", name="Alice Worker", team_id=team["_id"])

    msg = {
        "_id": ObjectId(),
        "team_id": team["_id"],
        "sender_id": emp["_id"],
        "content": "Sensitive audit message",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "edited_at": None,
        "is_deleted": True,
        "deleted_at": datetime.now(timezone.utc),
        "deleted_by": emp["_id"],
    }
    fake_db["collaboration_messages"].docs.append(msg)

    admin_token = make_token(admin["_id"])

    # Admin List
    res = client.get("/admin/collaboration/messages", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["content"] == "Sensitive audit message"
    assert data["items"][0]["is_deleted"] is True
    assert data["items"][0]["sender_name"] == "Alice Worker"
    assert data["items"][0]["team_name"] == "Secure Team"

    # Admin Detail
    res_detail = client.get(f"/admin/collaboration/messages/{msg['_id']}", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_detail.status_code == 200
    assert res_detail.json()["content"] == "Sensitive audit message"
    assert res_detail.json()["is_deleted"] is True


def test_admin_audit_is_read_only(test_setup):
    client, fake_db = test_setup
    admin = create_user(fake_db, email="admin@example.com", role="admin")
    admin_token = make_token(admin["_id"])

    # No mutation endpoints exist on /admin/collaboration/messages
    post_res = client.post("/admin/collaboration/messages", json={"content": "test"}, headers={"Authorization": f"Bearer {admin_token}"})
    assert post_res.status_code in [404, 405]

    patch_res = client.patch("/admin/collaboration/messages/123", json={"content": "test"}, headers={"Authorization": f"Bearer {admin_token}"})
    assert patch_res.status_code in [404, 405]

    delete_res = client.delete("/admin/collaboration/messages/123", headers={"Authorization": f"Bearer {admin_token}"})
    assert delete_res.status_code in [404, 405]


def test_non_admin_cannot_access_admin_endpoints(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    emp = create_user(fake_db, email="emp@example.com", role="employee")

    mgr_token = make_token(mgr["_id"])
    emp_token = make_token(emp["_id"])

    res_mgr = client.get("/admin/collaboration/messages", headers={"Authorization": f"Bearer {mgr_token}"})
    assert res_mgr.status_code == 403

    res_emp = client.get("/admin/collaboration/messages", headers={"Authorization": f"Bearer {emp_token}"})
    assert res_emp.status_code == 403


# =========================================================================
# 7. Validation & Error Handling Tests
# =========================================================================


def test_invalid_message_team_sender_objectids_return_400(test_setup):
    client, fake_db = test_setup
    admin = create_user(fake_db, email="admin@example.com", role="admin")
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    emp = create_user(fake_db, email="emp@example.com", role="employee")

    emp_token = make_token(emp["_id"])
    admin_token = make_token(admin["_id"])

    # Invalid team ID in post
    res = client.post("/collaboration/messages", json={"team_id": "invalid-id", "content": "test"}, headers={"Authorization": f"Bearer {emp_token}"})
    assert res.status_code == 400

    # Invalid message ID in get
    res = client.get("/collaboration/messages/not-an-oid", headers={"Authorization": f"Bearer {emp_token}"})
    assert res.status_code == 400

    # Invalid message ID in patch
    res = client.patch("/collaboration/messages/not-an-oid", json={"content": "test"}, headers={"Authorization": f"Bearer {emp_token}"})
    assert res.status_code == 400

    # Invalid message ID in delete
    res = client.delete("/collaboration/messages/not-an-oid", headers={"Authorization": f"Bearer {emp_token}"})
    assert res.status_code == 400

    # Invalid filters in admin list
    res = client.get("/admin/collaboration/messages?team_id=invalid", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 400
    res = client.get("/admin/collaboration/messages?sender_id=invalid", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 400


def test_missing_message_returns_404(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    emp = create_user(fake_db, email="emp@example.com", role="employee")
    admin = create_user(fake_db, email="admin@example.com", role="admin")

    emp_token = make_token(emp["_id"])
    admin_token = make_token(admin["_id"])
    non_existent_id = str(ObjectId())

    # User get
    res = client.get(f"/collaboration/messages/{non_existent_id}", headers={"Authorization": f"Bearer {emp_token}"})
    assert res.status_code == 404

    # User patch
    res = client.patch(f"/collaboration/messages/{non_existent_id}", json={"content": "test"}, headers={"Authorization": f"Bearer {emp_token}"})
    assert res.status_code == 404

    # User delete
    res = client.delete(f"/collaboration/messages/{non_existent_id}", headers={"Authorization": f"Bearer {emp_token}"})
    assert res.status_code == 404

    # Admin get
    res = client.get(f"/admin/collaboration/messages/{non_existent_id}", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 404


def test_empty_and_whitespace_content_returns_422(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Team 1", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])

    token = make_token(emp["_id"])

    # Empty string
    res = client.post("/collaboration/messages", json={"team_id": str(team["_id"]), "content": ""}, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 422

    # Whitespace only
    res = client.post("/collaboration/messages", json={"team_id": str(team["_id"]), "content": "    "}, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 422

    # Update empty
    msg = {
        "_id": ObjectId(),
        "team_id": team["_id"],
        "sender_id": emp["_id"],
        "content": "Valid",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "edited_at": None,
        "is_deleted": False,
        "deleted_at": None,
        "deleted_by": None,
    }
    fake_db["collaboration_messages"].docs.append(msg)

    res_patch = client.patch(f"/collaboration/messages/{msg['_id']}", json={"content": "  "}, headers={"Authorization": f"Bearer {token}"})
    assert res_patch.status_code == 422


def test_content_longer_than_4000_chars_returns_422(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Team 1", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])

    token = make_token(emp["_id"])
    long_content = "A" * 4001

    res = client.post("/collaboration/messages", json={"team_id": str(team["_id"]), "content": long_content}, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 422


def test_unexpected_request_fields_return_422(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Team 1", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])

    token = make_token(emp["_id"])

    # Extra field on create
    res = client.post(
        "/collaboration/messages",
        json={"team_id": str(team["_id"]), "content": "Hello", "sentiment_score": 0.9},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422

    # Extra field on update
    msg = {
        "_id": ObjectId(),
        "team_id": team["_id"],
        "sender_id": emp["_id"],
        "content": "Valid",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "edited_at": None,
        "is_deleted": False,
        "deleted_at": None,
        "deleted_by": None,
    }
    fake_db["collaboration_messages"].docs.append(msg)

    res_patch = client.patch(
        f"/collaboration/messages/{msg['_id']}",
        json={"content": "Updated", "mood": "happy"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_patch.status_code == 422


# =========================================================================
# 8. Ordering, Pagination & Enrichment Tests
# =========================================================================


def test_messages_are_returned_newest_first(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Team 1", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])

    now = datetime.now(timezone.utc)
    for i in range(5):
        msg = {
            "_id": ObjectId(),
            "team_id": team["_id"],
            "sender_id": emp["_id"],
            "content": f"Message {i}",
            "created_at": now + timedelta(minutes=i),
            "updated_at": now + timedelta(minutes=i),
            "edited_at": None,
            "is_deleted": False,
            "deleted_at": None,
            "deleted_by": None,
        }
        fake_db["collaboration_messages"].docs.append(msg)

    token = make_token(emp["_id"])
    res = client.get("/collaboration/messages", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 5
    assert items[0]["content"] == "Message 4"
    assert items[1]["content"] == "Message 3"
    assert items[4]["content"] == "Message 0"


def test_pagination_metadata_is_correct(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Team 1", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])

    now = datetime.now(timezone.utc)
    for i in range(15):
        msg = {
            "_id": ObjectId(),
            "team_id": team["_id"],
            "sender_id": emp["_id"],
            "content": f"Msg {i}",
            "created_at": now + timedelta(seconds=i),
            "updated_at": now + timedelta(seconds=i),
            "edited_at": None,
            "is_deleted": False,
            "deleted_at": None,
            "deleted_by": None,
        }
        fake_db["collaboration_messages"].docs.append(msg)

    token = make_token(emp["_id"])
    res = client.get("/collaboration/messages?page=2&limit=5", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 15
    assert data["page"] == 2
    assert data["limit"] == 5
    assert data["total_pages"] == 3
    assert len(data["items"]) == 5


def test_sender_name_email_and_team_name_are_enriched(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Dev Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", name="Bob Developer", team_id=team["_id"])

    msg = {
        "_id": ObjectId(),
        "team_id": team["_id"],
        "sender_id": emp["_id"],
        "content": "Enriched message test",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "edited_at": None,
        "is_deleted": False,
        "deleted_at": None,
        "deleted_by": None,
    }
    fake_db["collaboration_messages"].docs.append(msg)

    token = make_token(emp["_id"])
    res = client.get(f"/collaboration/messages/{msg['_id']}", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["sender_name"] == "Bob Developer"
    assert data["sender_email"] == "emp@example.com"
    assert data["team_name"] == "Dev Team"


def test_missing_historical_user_and_team_references_serialize_safely(test_setup):
    client, fake_db = test_setup
    admin = create_user(fake_db, email="admin@example.com", role="admin")

    deleted_user_oid = ObjectId()
    deleted_team_oid = ObjectId()

    msg = {
        "_id": ObjectId(),
        "team_id": deleted_team_oid,
        "sender_id": deleted_user_oid,
        "content": "Orphaned historical message",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "edited_at": None,
        "is_deleted": False,
        "deleted_at": None,
        "deleted_by": None,
    }
    fake_db["collaboration_messages"].docs.append(msg)

    admin_token = make_token(admin["_id"])
    res = client.get(f"/admin/collaboration/messages/{msg['_id']}", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["sender_id"] == str(deleted_user_oid)
    assert data["team_id"] == str(deleted_team_oid)
    assert data["sender_name"] is None
    assert data["sender_email"] is None
    assert data["team_name"] is None
    assert data["content"] == "Orphaned historical message"
