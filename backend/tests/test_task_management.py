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
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_resolve.status_code == 200
    resolved_task = res_resolve.json()
    assert resolved_task["status"] == "in_progress"
    assert resolved_task["blockers"][0]["is_resolved"] is True
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
