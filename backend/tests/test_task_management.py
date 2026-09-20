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


def test_manager_creates_task_for_managed_team(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr1@example.com", role="manager")
    team = create_team(fake_db, name="Frontend Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp1@example.com", role="employee", team_id=team["_id"])

    mgr_token = make_token(mgr["_id"])

    task_payload = {
        "title": "Build Task List Component",
        "description": "Implement responsive task list with filter controls.",
        "team_id": str(team["_id"]),
        "assigned_to": str(emp["_id"]),
        "required_skills": ["React", "TypeScript", "CSS"],
        "priority": "high",
        "due_date": "2026-09-30T17:00:00Z",
        "estimated_hours": 16.0,
    }

    res = client.post(
        "/tasks",
        json=task_payload,
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Build Task List Component"
    assert data["team_id"] == str(team["_id"])
    assert data["created_by"] == str(mgr["_id"])
    assert data["assigned_to"] == str(emp["_id"])
    assert data["required_skills"] == ["React", "TypeScript", "CSS"]
    assert data["priority"] == "high"
    assert data["status"] == "todo"
    assert data["estimated_hours"] == 16.0
    assert data["progress_history"] == []
    assert data["blockers"] == []
    assert "id" in data
    assert data["created_at"] is not None


def test_manager_cannot_create_task_for_unmanaged_team(test_setup):
    client, fake_db = test_setup
    mgr1 = create_user(fake_db, email="mgr1@example.com", role="manager")
    mgr2 = create_user(fake_db, email="mgr2@example.com", role="manager")
    team2 = create_team(fake_db, name="Backend Team", manager_id=mgr2["_id"])

    mgr1_token = make_token(mgr1["_id"])

    task_payload = {
        "title": "Unauthorized Task",
        "team_id": str(team2["_id"]),
    }
    res = client.post(
        "/tasks",
        json=task_payload,
        headers={"Authorization": f"Bearer {mgr1_token}"},
    )
    assert res.status_code == 403
    assert "Access denied" in res.json()["detail"]


def test_employee_and_admin_cannot_create_tasks(test_setup):
    client, fake_db = test_setup
    admin = create_user(fake_db, email="admin@example.com", role="admin")
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Core Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])

    emp_token = make_token(emp["_id"])
    admin_token = make_token(admin["_id"])

    task_payload = {
        "title": "Some Task",
        "team_id": str(team["_id"]),
    }

    # Employee cannot create tasks
    res_emp = client.post(
        "/tasks",
        json=task_payload,
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res_emp.status_code == 403

    # Admin cannot create tasks through normal endpoint
    res_admin = client.post(
        "/tasks",
        json=task_payload,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_admin.status_code == 403


def test_task_creation_assignment_validation(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team1 = create_team(fake_db, name="Team 1", manager_id=mgr["_id"])
    team2 = create_team(fake_db, name="Team 2", manager_id=ObjectId())

    emp_team2 = create_user(fake_db, email="emp2@example.com", role="employee", team_id=team2["_id"])
    inactive_emp = create_user(
        fake_db, email="inactive@example.com", role="employee", is_active=False, team_id=team1["_id"]
    )
    mgr_user = create_user(fake_db, email="other_mgr@example.com", role="manager")

    mgr_token = make_token(mgr["_id"])

    # Reject assigning employee from another team
    res_other_team = client.post(
        "/tasks",
        json={"title": "Cross-team Task", "team_id": str(team1["_id"]), "assigned_to": str(emp_team2["_id"])},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_other_team.status_code == 400
    assert "another team" in res_other_team.json()["detail"]

    # Reject assigning inactive employee
    res_inactive = client.post(
        "/tasks",
        json={"title": "Inactive Task", "team_id": str(team1["_id"]), "assigned_to": str(inactive_emp["_id"])},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_inactive.status_code == 400
    assert "inactive" in res_inactive.json()["detail"]

    # Reject assigning user with non-employee role
    res_non_emp = client.post(
        "/tasks",
        json={"title": "Manager Task", "team_id": str(team1["_id"]), "assigned_to": str(mgr_user["_id"])},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_non_emp.status_code == 400
    assert "employee role" in res_non_emp.json()["detail"]


def test_manager_lists_and_views_managed_tasks(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Team Alpha", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])

    mgr_token = make_token(mgr["_id"])

    # Create two tasks
    res1 = client.post(
        "/tasks",
        json={"title": "Task 1", "team_id": str(team["_id"]), "priority": "high"},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    task1_id = res1.json()["id"]

    client.post(
        "/tasks",
        json={"title": "Task 2", "team_id": str(team["_id"]), "priority": "low"},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )

    # List managed tasks
    res_list = client.get("/tasks/managed", headers={"Authorization": f"Bearer {mgr_token}"})
    assert res_list.status_code == 200
    data = res_list.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["page"] == 1

    # Filter by priority
    res_filtered = client.get(
        "/tasks/managed?priority=high",
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_filtered.status_code == 200
    assert res_filtered.json()["total"] == 1
    assert res_filtered.json()["items"][0]["title"] == "Task 1"

    # View individual task
    res_view = client.get(f"/tasks/{task1_id}", headers={"Authorization": f"Bearer {mgr_token}"})
    assert res_view.status_code == 200
    assert res_view.json()["id"] == task1_id


def test_manager_cannot_view_or_update_other_teams_tasks(test_setup):
    client, fake_db = test_setup
    mgr1 = create_user(fake_db, email="mgr1@example.com", role="manager")
    mgr2 = create_user(fake_db, email="mgr2@example.com", role="manager")

    team1 = create_team(fake_db, name="Team 1", manager_id=mgr1["_id"])
    team2 = create_team(fake_db, name="Team 2", manager_id=mgr2["_id"])

    mgr2_token = make_token(mgr2["_id"])
    res_t2 = client.post(
        "/tasks",
        json={"title": "Team 2 Task", "team_id": str(team2["_id"])},
        headers={"Authorization": f"Bearer {mgr2_token}"},
    )
    task2_id = res_t2.json()["id"]

    mgr1_token = make_token(mgr1["_id"])

    # Manager 1 attempts to view Team 2 task
    res_view = client.get(f"/tasks/{task2_id}", headers={"Authorization": f"Bearer {mgr1_token}"})
    assert res_view.status_code == 403

    # Manager 1 attempts to update Team 2 task
    res_update = client.patch(
        f"/tasks/{task2_id}",
        json={"title": "Hacked Title"},
        headers={"Authorization": f"Bearer {mgr1_token}"},
    )
    assert res_update.status_code == 403


def test_manager_updates_task_metadata(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Team Dev", manager_id=mgr["_id"])
    mgr_token = make_token(mgr["_id"])

    res_create = client.post(
        "/tasks",
        json={"title": "Original Title", "team_id": str(team["_id"]), "priority": "low"},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    task_id = res_create.json()["id"]

    res_patch = client.patch(
        f"/tasks/{task_id}",
        json={
            "title": "Updated Title",
            "description": "Updated Description",
            "priority": "urgent",
            "required_skills": ["Python", "FastAPI"],
            "estimated_hours": 24.5,
        },
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_patch.status_code == 200
    updated = res_patch.json()
    assert updated["title"] == "Updated Title"
    assert updated["description"] == "Updated Description"
    assert updated["priority"] == "urgent"
    assert updated["required_skills"] == ["Python", "FastAPI"]
    assert updated["estimated_hours"] == 24.5


def test_manager_assigns_and_unassigns_tasks(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Team Assign", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp_assign@example.com", role="employee", team_id=team["_id"])
    mgr_token = make_token(mgr["_id"])

    # Create unassigned task
    res_create = client.post(
        "/tasks",
        json={"title": "Unassigned Task", "team_id": str(team["_id"])},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    task_id = res_create.json()["id"]
    assert res_create.json()["assigned_to"] is None

    # Assign employee
    res_assign = client.patch(
        f"/tasks/{task_id}/assignment",
        json={"assigned_to": str(emp["_id"])},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_assign.status_code == 200
    assert res_assign.json()["assigned_to"] == str(emp["_id"])

    # Unassign
    res_unassign = client.patch(
        f"/tasks/{task_id}/assignment",
        json={"assigned_to": None},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_unassign.status_code == 200
    assert res_unassign.json()["assigned_to"] is None


def test_employee_lists_and_views_only_assigned_tasks(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Team Work", manager_id=mgr["_id"])

    emp1 = create_user(fake_db, email="emp1@example.com", role="employee", team_id=team["_id"])
    emp2 = create_user(fake_db, email="emp2@example.com", role="employee", team_id=team["_id"])

    mgr_token = make_token(mgr["_id"])

    # Create task assigned to emp1
    res1 = client.post(
        "/tasks",
        json={"title": "Emp1 Task", "team_id": str(team["_id"]), "assigned_to": str(emp1["_id"])},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    task1_id = res1.json()["id"]

    # Create task assigned to emp2
    res2 = client.post(
        "/tasks",
        json={"title": "Emp2 Task", "team_id": str(team["_id"]), "assigned_to": str(emp2["_id"])},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    task2_id = res2.json()["id"]

    emp1_token = make_token(emp1["_id"])

    # Emp1 retrieves only their tasks
    res_my_tasks = client.get("/tasks/my-tasks", headers={"Authorization": f"Bearer {emp1_token}"})
    assert res_my_tasks.status_code == 200
    my_tasks = res_my_tasks.json()
    assert my_tasks["total"] == 1
    assert my_tasks["items"][0]["id"] == task1_id

    # Emp1 views permitted task detail
    res_detail = client.get(f"/tasks/{task1_id}", headers={"Authorization": f"Bearer {emp1_token}"})
    assert res_detail.status_code == 200
    assert res_detail.json()["id"] == task1_id

    # Emp1 denied access to Emp2's task
    res_denied = client.get(f"/tasks/{task2_id}", headers={"Authorization": f"Bearer {emp1_token}"})
    assert res_denied.status_code == 403


def test_employee_updates_status(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Team Status", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])
    other_emp = create_user(fake_db, email="other@example.com", role="employee", team_id=team["_id"])

    mgr_token = make_token(mgr["_id"])
    res_task = client.post(
        "/tasks",
        json={"title": "Status Task", "team_id": str(team["_id"]), "assigned_to": str(emp["_id"])},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    task_id = res_task.json()["id"]

    emp_token = make_token(emp["_id"])

    # Transition to in_progress
    res_in_prog = client.patch(
        f"/tasks/{task_id}/status",
        json={"status": "in_progress"},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res_in_prog.status_code == 200
    assert res_in_prog.json()["status"] == "in_progress"

    # Transition to completed
    res_complete = client.patch(
        f"/tasks/{task_id}/status",
        json={"status": "completed"},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res_complete.status_code == 200
    assert res_complete.json()["status"] == "completed"

    # Other employee cannot modify status
    other_token = make_token(other_emp["_id"])
    res_other = client.patch(
        f"/tasks/{task_id}/status",
        json={"status": "todo"},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert res_other.status_code == 403

    # Manager cannot modify status through employee endpoint
    res_mgr_status = client.patch(
        f"/tasks/{task_id}/status",
        json={"status": "todo"},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_mgr_status.status_code == 403


def test_employee_logs_progress_and_manager_forbidden(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Team Prog", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])

    mgr_token = make_token(mgr["_id"])
    res_task = client.post(
        "/tasks",
        json={"title": "Progress Task", "team_id": str(team["_id"]), "assigned_to": str(emp["_id"])},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    task_id = res_task.json()["id"]

    emp_token = make_token(emp["_id"])

    # Employee logs progress
    res_prog = client.post(
        f"/tasks/{task_id}/progress",
        json={"percentage": 50, "notes": "Completed initial frontend wireframe."},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res_prog.status_code == 200
    data = res_prog.json()
    assert len(data["progress_history"]) == 1
    prog_entry = data["progress_history"][0]
    assert prog_entry["user_id"] == str(emp["_id"])
    assert prog_entry["percentage"] == 50
    assert prog_entry["notes"] == "Completed initial frontend wireframe."
    assert "id" in prog_entry
    assert "logged_at" in prog_entry

    # Manager forbidden from adding progress pretending to be employee
    res_mgr_prog = client.post(
        f"/tasks/{task_id}/progress",
        json={"percentage": 75, "notes": "Manager logging progress"},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_mgr_prog.status_code == 403

    # Invalid percentage rejected
    res_bad_pct = client.post(
        f"/tasks/{task_id}/progress",
        json={"percentage": 110, "notes": "Overflow"},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res_bad_pct.status_code == 422


def test_blocker_reporting_and_resolution_flow(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Team Blocker", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])

    mgr_token = make_token(mgr["_id"])
    emp_token = make_token(emp["_id"])

    # Create task and start it
    res_task = client.post(
        "/tasks",
        json={"title": "Blocker Task", "team_id": str(team["_id"]), "assigned_to": str(emp["_id"])},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    task_id = res_task.json()["id"]

    client.patch(
        f"/tasks/{task_id}/status",
        json={"status": "in_progress"},
        headers={"Authorization": f"Bearer {emp_token}"},
    )

    # 1. Employee reports blocker -> status automatically becomes 'blocked'
    res_blocker = client.post(
        f"/tasks/{task_id}/blockers",
        json={"description": "Missing database connection string."},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res_blocker.status_code == 200
    task_data = res_blocker.json()
    assert task_data["status"] == "blocked"
    assert len(task_data["blockers"]) == 1
    blocker_id = task_data["blockers"][0]["id"]
    assert task_data["blockers"][0]["user_id"] == str(emp["_id"])
    assert task_data["blockers"][0]["is_resolved"] is False

    # 2. Employee cannot mark completed while blocker unresolved
    res_fail_complete = client.patch(
        f"/tasks/{task_id}/status",
        json={"status": "completed"},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res_fail_complete.status_code == 400
    assert "unresolved blockers" in res_fail_complete.json()["detail"]

    # 3. Manager resolves blocker -> status automatically becomes 'in_progress'
    res_resolve = client.patch(
        f"/tasks/{task_id}/blockers/{blocker_id}/resolve",
        json={"resolution_note": "Provisioned database connection string and credentials."},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_resolve.status_code == 200
    resolved_task = res_resolve.json()
    assert resolved_task["status"] == "in_progress"
    assert resolved_task["blockers"][0]["is_resolved"] is True
    assert resolved_task["blockers"][0]["resolution_note"] == "Provisioned database connection string and credentials."
    assert resolved_task["blockers"][0]["resolved_by"] == str(mgr["_id"])
    assert resolved_task["blockers"][0]["resolved_at"] is not None

    # 4. Now employee can complete task
    res_done = client.patch(
        f"/tasks/{task_id}/status",
        json={"status": "completed"},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res_done.status_code == 200
    assert res_done.json()["status"] == "completed"

    # 5. Completed task cannot receive a new blocker
    res_late_blocker = client.post(
        f"/tasks/{task_id}/blockers",
        json={"description": "Late issue"},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res_late_blocker.status_code == 400
    assert "Completed task cannot receive new blockers" in res_late_blocker.json()["detail"]


def test_admin_read_only_audit_access(test_setup):
    client, fake_db = test_setup
    admin = create_user(fake_db, email="admin@example.com", role="admin")
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, name="Team Audit", manager_id=mgr["_id"])

    mgr_token = make_token(mgr["_id"])
    res_task = client.post(
        "/tasks",
        json={"title": "Audit Task", "team_id": str(team["_id"])},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    task_id = res_task.json()["id"]

    admin_token = make_token(admin["_id"])

    # Admin lists all tasks
    res_admin_list = client.get("/admin/tasks", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_admin_list.status_code == 200
    assert res_admin_list.json()["total"] == 1

    # Admin views task detail
    res_admin_detail = client.get(f"/admin/tasks/{task_id}", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_admin_detail.status_code == 200
    assert res_admin_detail.json()["id"] == task_id


def test_prevent_deactivating_or_reassigning_employee_with_open_tasks(test_setup):
    client, fake_db = test_setup
    admin = create_user(fake_db, email="admin@example.com", role="admin")
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team1 = create_team(fake_db, name="Team 1", manager_id=mgr["_id"])
    team2 = create_team(fake_db, name="Team 2", manager_id=mgr["_id"])

    emp = create_user(fake_db, email="emp_locked@example.com", role="employee", team_id=team1["_id"])

    mgr_token = make_token(mgr["_id"])
    admin_token = make_token(admin["_id"])

    # Create task assigned to employee
    res_task = client.post(
        "/tasks",
        json={"title": "Blocking Task", "team_id": str(team1["_id"]), "assigned_to": str(emp["_id"])},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    task_id = res_task.json()["id"]

    # 1. Admin attempts to deactivate employee -> 409 Conflict
    res_deact = client.patch(
        f"/admin/users/{emp['_id']}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_deact.status_code == 409
    assert "open assigned tasks" in res_deact.json()["detail"]

    # 2. Admin attempts to transfer employee to Team 2 -> 409 Conflict
    res_xfer = client.post(
        f"/admin/teams/{team2['_id']}/members",
        json={"user_id": str(emp["_id"])},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_xfer.status_code == 409
    assert "open assigned tasks" in res_xfer.json()["detail"]

    # 3. Admin attempts to remove employee from Team 1 -> 409 Conflict
    res_rem = client.delete(
        f"/admin/teams/{team1['_id']}/members/{emp['_id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_rem.status_code == 409
    assert "open assigned tasks" in res_rem.json()["detail"]

    # 4. Admin attempts to promote employee to manager -> 409 Conflict
    res_role = client.patch(
        f"/admin/users/{emp['_id']}/role",
        json={"role": "manager"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_role.status_code == 409
    assert "open assigned tasks" in res_role.json()["detail"]

    # 5. Manager unassigns task
    client.patch(
        f"/tasks/{task_id}/assignment",
        json={"assigned_to": None},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )

    # Now deactivation succeeds
    res_deact_ok = client.patch(
        f"/admin/users/{emp['_id']}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_deact_ok.status_code == 200
    assert res_deact_ok.json()["is_active"] is False


def test_invalid_object_ids_in_tasks_endpoints(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    mgr_token = make_token(mgr["_id"])

    res1 = client.post(
        "/tasks",
        json={"title": "Invalid Team", "team_id": "bad-team-id"},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res1.status_code == 400

    res2 = client.get(
        "/tasks/bad-task-id",
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res2.status_code == 400


def test_task_progress_invariants_and_completed_consistency(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr_inv@example.com", role="manager")
    team = create_team(fake_db, name="Invariant Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp_inv@example.com", role="employee", team_id=team["_id"])

    mgr_token = make_token(mgr["_id"])
    emp_token = make_token(emp["_id"])

    # 1. Create task in todo status (progress is 0, progress_history empty)
    res_create = client.post(
        "/tasks",
        json={"title": "Progress Invariants Task", "team_id": str(team["_id"]), "assigned_to": str(emp["_id"])},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_create.status_code == 201
    task_id = res_create.json()["id"]
    assert res_create.json()["status"] == "todo"
    assert res_create.json()["progress_history"] == []

    # 2. Moving from todo to in_progress does NOT automatically increase progress to 10%
    res_in_prog = client.patch(
        f"/tasks/{task_id}/status",
        json={"status": "in_progress"},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res_in_prog.status_code == 200
    assert res_in_prog.json()["status"] == "in_progress"
    assert res_in_prog.json()["progress_history"] == []  # No arbitrary 10% increase!

    # 3. Explicit progress logging to 40%
    res_prog = client.post(
        f"/tasks/{task_id}/progress",
        json={"percentage": 40, "notes": "Initial implementation completed."},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res_prog.status_code == 200
    assert len(res_prog.json()["progress_history"]) == 1
    assert res_prog.json()["progress_history"][0]["percentage"] == 40

    # 4. Reporting blocker marks status 'blocked' and preserves 40% progress
    res_blocker = client.post(
        f"/tasks/{task_id}/blockers",
        json={"description": "Missing API key for external service."},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res_blocker.status_code == 200
    blocked_data = res_blocker.json()
    assert blocked_data["status"] == "blocked"
    assert len(blocked_data["progress_history"]) == 1
    assert blocked_data["progress_history"][0]["percentage"] == 40
    blocker_id = blocked_data["blockers"][0]["id"]

    # 5. Resolving blocker returns status to 'in_progress' and preserves 40% progress
    res_resolve = client.patch(
        f"/tasks/{task_id}/blockers/{blocker_id}/resolve",
        json={"resolution_note": "Generated and deployed new API keys to secret vault."},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_resolve.status_code == 200
    resolved_data = res_resolve.json()
    assert resolved_data["status"] == "in_progress"
    assert len(resolved_data["progress_history"]) == 1
    assert resolved_data["progress_history"][0]["percentage"] == 40

    # 6. Moving status to completed enforces 100% progress consistency
    res_complete = client.patch(
        f"/tasks/{task_id}/status",
        json={"status": "completed"},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res_complete.status_code == 200
    complete_data = res_complete.json()
    assert complete_data["status"] == "completed"
    assert len(complete_data["progress_history"]) == 2
    assert complete_data["progress_history"][-1]["percentage"] == 100
    assert complete_data["progress_history"][-1]["notes"] == "Task completed"

    # 7. If task already had 100% progress before completing another task, no duplicate 100% entry
    res_create2 = client.post(
        "/tasks",
        json={"title": "Task Already 100%", "team_id": str(team["_id"]), "assigned_to": str(emp["_id"])},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    task2_id = res_create2.json()["id"]
    client.post(
        f"/tasks/{task2_id}/progress",
        json={"percentage": 100, "notes": "All done via progress log."},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    res_complete2 = client.patch(
        f"/tasks/{task2_id}/status",
        json={"status": "completed"},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res_complete2.status_code == 200
    assert len(res_complete2.json()["progress_history"]) == 1
    assert res_complete2.json()["progress_history"][0]["percentage"] == 100


def test_blocker_resolution_validation_and_duplicate_prevention(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr_blk@example.com", role="manager")
    team = create_team(fake_db, name="Blocker Validation Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp_blk@example.com", role="employee", team_id=team["_id"])

    mgr_token = make_token(mgr["_id"])
    emp_token = make_token(emp["_id"])

    res_task = client.post(
        "/tasks",
        json={"title": "Blocker Validation Task", "team_id": str(team["_id"]), "assigned_to": str(emp["_id"])},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    task_id = res_task.json()["id"]

    res_blocker = client.post(
        f"/tasks/{task_id}/blockers",
        json={"description": "Dependencies failed to download."},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    blocker_id = res_blocker.json()["blockers"][0]["id"]

    # 1. Missing resolution note rejected with 422
    res_empty_body = client.patch(
        f"/tasks/{task_id}/blockers/{blocker_id}/resolve",
        json={},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_empty_body.status_code == 422

    # 2. Empty or whitespace-only resolution note rejected with 422
    res_blank_note = client.patch(
        f"/tasks/{task_id}/blockers/{blocker_id}/resolve",
        json={"resolution_note": "   "},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_blank_note.status_code == 422

    # 3. Valid resolution succeeds and stores note, resolved_by, resolved_at
    res_valid_resolve = client.patch(
        f"/tasks/{task_id}/blockers/{blocker_id}/resolve",
        json={"resolution_note": "Fixed proxy configuration and npm mirror."},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_valid_resolve.status_code == 200
    blk = res_valid_resolve.json()["blockers"][0]
    assert blk["is_resolved"] is True
    assert blk["resolution_note"] == "Fixed proxy configuration and npm mirror."
    assert blk["resolved_by"] == str(mgr["_id"])
    assert blk["resolved_at"] is not None
    assert blk["description"] == "Dependencies failed to download."

    # 4. Duplicate resolution attempt rejected with 400 Bad Request
    res_dup = client.patch(
        f"/tasks/{task_id}/blockers/{blocker_id}/resolve",
        json={"resolution_note": "Second resolution attempt."},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_dup.status_code == 400
    assert "already resolved" in res_dup.json()["detail"].lower()


def test_multiple_open_blockers_resolution_semantics(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr_blk@example.com", role="manager", name="Manager Blk")
    team = create_team(fake_db, name="Multi Blocker Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp_blk@example.com", role="employee", name="Emp Blk", team_id=team["_id"])

    mgr_token = make_token(mgr["_id"])
    emp_token = make_token(emp["_id"])

    # Create task
    res_task = client.post(
        "/tasks",
        json={"title": "Multi Blocker Task", "team_id": str(team["_id"]), "assigned_to": str(emp["_id"])},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_task.status_code == 201
    task_id = res_task.json()["id"]

    # 1. Report first blocker -> task becomes blocked
    res_b1 = client.post(
        f"/tasks/{task_id}/blockers",
        json={"description": "First blocker: Waiting for API key."},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res_b1.status_code == 200
    b1_data = res_b1.json()
    assert b1_data["status"] == "blocked"
    assert len(b1_data["blockers"]) == 1
    b1_id = b1_data["blockers"][0]["id"]

    # 2. Report second blocker -> task remains blocked with 2 blockers
    res_b2 = client.post(
        f"/tasks/{task_id}/blockers",
        json={"description": "Second blocker: Database connection timed out."},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res_b2.status_code == 200
    b2_data = res_b2.json()
    assert b2_data["status"] == "blocked"
    assert len(b2_data["blockers"]) == 2
    b2_id = b2_data["blockers"][1]["id"]

    # 3. Resolve only the first blocker -> Task MUST REMAIN blocked because blocker 2 is still open
    res_resolve_b1 = client.patch(
        f"/tasks/{task_id}/blockers/{b1_id}/resolve",
        json={"resolution_note": "API key generated and shared in secure vault."},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_resolve_b1.status_code == 200
    r1_data = res_resolve_b1.json()
    assert r1_data["status"] == "blocked"  # Still blocked!
    assert len(r1_data["blockers"]) == 2

    resolved_b1 = next(b for b in r1_data["blockers"] if b["id"] == b1_id)
    assert resolved_b1["is_resolved"] is True
    assert resolved_b1["resolution_note"] == "API key generated and shared in secure vault."
    assert resolved_b1["resolved_by_name"] == "Manager Blk"

    unresolved_b2 = next(b for b in r1_data["blockers"] if b["id"] == b2_id)
    assert unresolved_b2["is_resolved"] is False

    # 4. Duplicate resolution on first blocker rejected with 400
    res_dup = client.patch(
        f"/tasks/{task_id}/blockers/{b1_id}/resolve",
        json={"resolution_note": "Trying to resolve first blocker again."},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_dup.status_code == 400
    assert "already resolved" in res_dup.json()["detail"].lower()

    # 5. Resolve the second (final) blocker -> Task transitions to in_progress
    res_resolve_b2 = client.patch(
        f"/tasks/{task_id}/blockers/{b2_id}/resolve",
        json={"resolution_note": "Database firewall rules updated for VPC."},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_resolve_b2.status_code == 200
    r2_data = res_resolve_b2.json()
    assert r2_data["status"] == "in_progress"  # Final blocker resolved!
    assert all(b["is_resolved"] is True for b in r2_data["blockers"])


def test_task_response_identity_enrichment_and_legacy_blockers(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr_enrich@example.com", role="manager", name="Carol Manager")
    team = create_team(fake_db, name="Enriched Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp_enrich@example.com", role="employee", name="Dave Engineer", team_id=team["_id"])
    admin = create_user(fake_db, email="admin_audit@example.com", role="admin", name="Admin Auditor")

    mgr_token = make_token(mgr["_id"])
    emp_token = make_token(emp["_id"])
    admin_token = make_token(admin["_id"])

    # Manager creates task
    res_task = client.post(
        "/tasks",
        json={"title": "Enriched Task", "team_id": str(team["_id"]), "assigned_to": str(emp["_id"])},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    task_id = res_task.json()["id"]
    t_data = res_task.json()
    assert t_data["assigned_to_name"] == "Dave Engineer"
    assert t_data["assigned_to_email"] == "emp_enrich@example.com"
    assert t_data["created_by_name"] == "Carol Manager"
    assert t_data["created_by_email"] == "mgr_enrich@example.com"
    assert t_data["team_name"] == "Enriched Team"

    # Employee logs progress
    res_prog = client.post(
        f"/tasks/{task_id}/progress",
        json={"percentage": 30, "notes": "Initial setup."},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    p_data = res_prog.json()["progress_history"][0]
    assert p_data["user_name"] == "Dave Engineer"
    assert p_data["user_email"] == "emp_enrich@example.com"

    # Insert a legacy blocker directly into fake_db with resolution_note = None
    legacy_blocker = {
        "id": "legacy-blk-99",
        "user_id": emp["_id"],
        "description": "Legacy historical blocker before notes were required.",
        "is_resolved": True,
        "resolution_note": None,
        "resolved_at": datetime.now(timezone.utc),
        "resolved_by": mgr["_id"],
        "created_at": datetime.now(timezone.utc),
    }
    for doc in fake_db["tasks"].docs:
        if str(doc["_id"]) == task_id:
            doc["blockers"].append(legacy_blocker)

    # Admin audits the task
    res_admin = client.get(
        f"/admin/tasks/{task_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_admin.status_code == 200
    admin_task = res_admin.json()
    assert admin_task["assigned_to_name"] == "Dave Engineer"
    assert admin_task["assigned_to_email"] == "emp_enrich@example.com"
    assert admin_task["team_name"] == "Enriched Team"

    blk = next(b for b in admin_task["blockers"] if b["id"] == "legacy-blk-99")
    assert blk["is_resolved"] is True
    assert blk["resolution_note"] is None  # Not fabricated by backend
    assert blk["user_name"] == "Dave Engineer"
    assert blk["user_email"] == "emp_enrich@example.com"
    assert blk["resolved_by_name"] == "Carol Manager"
    assert blk["resolved_by_email"] == "mgr_enrich@example.com"


def test_employee_and_admin_cannot_edit_managed_tasks(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr_edit@example.com", role="manager", name="Task Manager")
    team = create_team(fake_db, name="Edit Test Team", manager_id=mgr["_id"])
    emp = create_user(fake_db, email="emp_edit@example.com", role="employee", name="Worker", team_id=team["_id"])
    admin = create_user(fake_db, email="admin_edit@example.com", role="admin", name="Admin User")

    mgr_token = make_token(mgr["_id"])
    emp_token = make_token(emp["_id"])
    admin_token = make_token(admin["_id"])

    res_task = client.post(
        "/tasks",
        json={"title": "Governance Task", "team_id": str(team["_id"]), "assigned_to": str(emp["_id"])},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    task_id = res_task.json()["id"]

    # 1. Employee cannot edit task metadata (PATCH /tasks/{id})
    res_emp_edit = client.patch(
        f"/tasks/{task_id}",
        json={"title": "Employee Hijacked Title"},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res_emp_edit.status_code == 403

    # 2. Admin cannot edit task metadata (Admin is strictly read-only audit)
    res_admin_edit = client.patch(
        f"/tasks/{task_id}",
        json={"title": "Admin Hijacked Title"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_admin_edit.status_code == 403

    # 3. Employee cannot update task assignment
    res_emp_assign = client.patch(
        f"/tasks/{task_id}/assignment",
        json={"assigned_to": str(emp["_id"])},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res_emp_assign.status_code == 403

    # 4. Admin cannot update task assignment
    res_admin_assign = client.patch(
        f"/tasks/{task_id}/assignment",
        json={"assigned_to": str(emp["_id"])},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_admin_assign.status_code == 403
