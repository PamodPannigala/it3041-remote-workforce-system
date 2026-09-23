from datetime import datetime, timedelta, timezone
from typing import Any
import uuid
from bson import ObjectId
from fastapi.testclient import TestClient
import jwt
import pytest

from backend.app.core.security import JWT_ALGORITHM, JWT_AUDIENCE, JWT_ISSUER, hash_password
from backend.app.main import app
from backend.app.modules.agents.coordinator import (
    AgentCoordinator,
    CoordinatorExecutionRequest,
    CoordinatorExecutionResult,
)
from backend.app.modules.agents.protocol import AgentFinding
from backend.app.modules.agents.router import (
    get_agent_coordinator,
    resolve_authenticated_principal,
)
from backend.tests.conftest import TEST_JWT_SECRET


# =========================================================================
# Test Helpers & Fixtures
# =========================================================================


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


class MockCoordinator:
    """Mock coordinator recording invocations and returning configured results."""

    def __init__(self, result: CoordinatorExecutionResult | None = None, raise_exc: Exception | None = None):
        self.invocations: list[CoordinatorExecutionRequest] = []
        self.result = result
        self.raise_exc = raise_exc

    async def orchestrate(self, request: CoordinatorExecutionRequest) -> CoordinatorExecutionResult:
        self.invocations.append(request)
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.result is not None:
            return self.result
        finding = AgentFinding(
            agent="productivity",
            correlation_id=request.correlation_id,
            summary="Mock productivity analysis completed.",
            confidence=0.95,
            limitations=["Based on available mock data."],
            recommended_actions=["Review sprint backlog."],
        )
        return CoordinatorExecutionResult(
            correlation_id=request.correlation_id,
            intent=request.intent,
            status="completed",
            findings=[finding],
            synthesized_finding=finding,
            errors=[],
            safe_error_message=None,
        )


# =========================================================================
# Authentication & Authorization Tests
# =========================================================================


def test_execute_unauthenticated_rejected(test_setup):
    client, _ = test_setup
    resp = client.post(
        "/agents/execute",
        json={
            "intent": "productivity_analysis",
            "question": "How is team productivity?",
        },
    )
    assert resp.status_code == 401


def test_capabilities_unauthenticated_rejected(test_setup):
    client, _ = test_setup
    resp = client.get("/agents/capabilities")
    assert resp.status_code == 401


def test_execute_invalid_token_rejected(test_setup):
    client, _ = test_setup
    resp = client.post(
        "/agents/execute",
        headers={"Authorization": "Bearer invalid.token.value"},
        json={
            "intent": "productivity_analysis",
            "question": "How is team productivity?",
        },
    )
    assert resp.status_code == 401


# =========================================================================
# Request Validation & Schema Constraints Tests
# =========================================================================


def test_execute_forbids_extra_fields(test_setup):
    client, fake_db = test_setup
    user = create_user(fake_db, email="emp@example.com", role="employee")
    token = make_token(user["_id"])

    resp = client.post(
        "/agents/execute",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "intent": "productivity_analysis",
            "question": "How is team productivity?",
            "extra_forbidden_field": "injected_value",
        },
    )
    assert resp.status_code == 422


def test_execute_forbids_injected_role_or_dependencies(test_setup):
    client, fake_db = test_setup
    user = create_user(fake_db, email="emp@example.com", role="employee")
    token = make_token(user["_id"])

    resp = client.post(
        "/agents/execute",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "intent": "productivity_analysis",
            "question": "How is team productivity?",
            "role": "admin",
            "managed_team_ids": ["65f123456789012345678901"],
            "dependency_findings": [],
        },
    )
    assert resp.status_code == 422


def test_execute_invalid_uuid_correlation_id_rejected(test_setup):
    client, fake_db = test_setup
    user = create_user(fake_db, email="emp@example.com", role="employee")
    token = make_token(user["_id"])

    resp = client.post(
        "/agents/execute",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "intent": "productivity_analysis",
            "question": "How is team productivity?",
            "correlation_id": "not-a-valid-uuid",
        },
    )
    assert resp.status_code == 422


def test_execute_empty_question_rejected(test_setup):
    client, fake_db = test_setup
    user = create_user(fake_db, email="emp@example.com", role="employee")
    token = make_token(user["_id"])

    resp = client.post(
        "/agents/execute",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "intent": "productivity_analysis",
            "question": "   ",
        },
    )
    assert resp.status_code == 422


def test_execute_invalid_weeks_lookback_rejected(test_setup):
    client, fake_db = test_setup
    user = create_user(fake_db, email="emp@example.com", role="employee")
    token = make_token(user["_id"])

    resp = client.post(
        "/agents/execute",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "intent": "productivity_analysis",
            "question": "Analyze productivity.",
            "weeks_lookback": 100,
        },
    )
    assert resp.status_code == 422


# =========================================================================
# Server-Side Principal Derivation & Scope Validation
# =========================================================================


@pytest.mark.asyncio
async def test_principal_derivation_from_db(fake_db):
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team1 = create_team(fake_db, "Engineering", mgr["_id"])
    team2 = create_team(fake_db, "Product", mgr["_id"])

    principal = await resolve_authenticated_principal(fake_db, mgr)
    assert principal.user_id == str(mgr["_id"])
    assert principal.role == "manager"
    assert str(team1["_id"]) in principal.managed_team_ids
    assert str(team2["_id"]) in principal.managed_team_ids


def test_employee_cross_team_rejection(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team1 = create_team(fake_db, "Team 1", mgr["_id"])
    team2 = create_team(fake_db, "Team 2", mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team1["_id"])
    token = make_token(emp["_id"])

    mock_coord = MockCoordinator(
        result=CoordinatorExecutionResult(
            correlation_id=str(uuid.uuid4()),
            intent="productivity_analysis",
            status="failed",
            errors=[{"agent": "coordinator", "error_code": "EMPLOYEE_CROSS_TEAM_FORBIDDEN", "message": "Employees cannot access data outside their assigned team"}],
            safe_error_message="Employees cannot access data outside their assigned team",
        )
    )
    app.dependency_overrides[get_agent_coordinator] = lambda: mock_coord
    try:
        resp = client.post(
            "/agents/execute",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "intent": "productivity_analysis",
                "question": "Check other team productivity",
                "target_team_id": str(team2["_id"]),
            },
        )
        assert resp.status_code == 403
        assert "outside their assigned team" in resp.json()["detail"]
        assert len(mock_coord.invocations) == 1
        invoked_req = mock_coord.invocations[0]
        assert invoked_req.authenticated_principal.user_id == str(emp["_id"])
        assert invoked_req.authenticated_principal.role == "employee"
        assert invoked_req.authenticated_principal.assigned_team_id == str(team1["_id"])
    finally:
        app.dependency_overrides.pop(get_agent_coordinator, None)


def test_employee_task_assignment_forbidden(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, "Team", mgr["_id"])
    emp = create_user(fake_db, email="emp@example.com", role="employee", team_id=team["_id"])
    token = make_token(emp["_id"])

    mock_coord = MockCoordinator(
        result=CoordinatorExecutionResult(
            correlation_id=str(uuid.uuid4()),
            intent="task_assignment_recommendation",
            status="failed",
            errors=[{"agent": "coordinator", "error_code": "EMPLOYEE_TASK_ASSIGNMENT_FORBIDDEN", "message": "Task assignment recommendation is restricted to managers"}],
            safe_error_message="Task assignment recommendation is restricted to managers",
        )
    )
    app.dependency_overrides[get_agent_coordinator] = lambda: mock_coord
    try:
        resp = client.post(
            "/agents/execute",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "intent": "task_assignment_recommendation",
                "question": "Recommend assignees for task 123",
                "target_team_id": str(team["_id"]),
                "target_task_id": "task_123",
            },
        )
        assert resp.status_code == 403
        assert "restricted to managers" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_agent_coordinator, None)


def test_manager_unmanaged_team_rejection(test_setup):
    client, fake_db = test_setup
    mgr1 = create_user(fake_db, email="mgr1@example.com", role="manager")
    mgr2 = create_user(fake_db, email="mgr2@example.com", role="manager")
    team2 = create_team(fake_db, "Team 2", mgr2["_id"])
    token = make_token(mgr1["_id"])

    mock_coord = MockCoordinator(
        result=CoordinatorExecutionResult(
            correlation_id=str(uuid.uuid4()),
            intent="task_assignment_recommendation",
            status="failed",
            errors=[{"agent": "coordinator", "error_code": "MANAGER_UNMANAGED_TEAM_FORBIDDEN", "message": "Managers cannot access teams they do not manage"}],
            safe_error_message="Managers cannot access teams they do not manage",
        )
    )
    app.dependency_overrides[get_agent_coordinator] = lambda: mock_coord
    try:
        resp = client.post(
            "/agents/execute",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "intent": "task_assignment_recommendation",
                "question": "Assign task in team 2",
                "target_team_id": str(team2["_id"]),
                "target_task_id": "task_123",
            },
        )
        assert resp.status_code == 403
        assert "Managers cannot access teams" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_agent_coordinator, None)


# =========================================================================
# Successful Execution & Coordinator Orchestration Tests
# =========================================================================


def test_valid_productivity_request(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, "Engineering", mgr["_id"])
    token = make_token(mgr["_id"])

    custom_corr_id = str(uuid.uuid4())
    mock_finding = AgentFinding(
        agent="productivity",
        correlation_id=custom_corr_id,
        summary="Sprint velocity increased by 14% over past 2 weeks.",
        confidence=0.92,
        limitations=["Recent task logs only."],
        recommended_actions=["Maintain current workload distribution."],
    )
    mock_coord = MockCoordinator(
        result=CoordinatorExecutionResult(
            correlation_id=custom_corr_id,
            intent="productivity_analysis",
            status="completed",
            findings=[mock_finding],
            synthesized_finding=mock_finding,
            errors=[],
        )
    )
    app.dependency_overrides[get_agent_coordinator] = lambda: mock_coord
    try:
        resp = client.post(
            "/agents/execute",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "intent": "productivity_analysis",
                "question": "How is the engineering team performing?",
                "target_team_id": str(team["_id"]),
                "correlation_id": custom_corr_id,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["correlation_id"] == custom_corr_id
        assert data["intent"] == "productivity_analysis"
        assert data["status"] == "completed"
        assert "Sprint velocity" in data["summary"]
        assert data["confidence"] == 0.92
        assert len(data["findings"]) == 1
        assert data["findings"][0]["agent"] == "productivity"
        assert len(mock_coord.invocations) == 1
    finally:
        app.dependency_overrides.pop(get_agent_coordinator, None)


def test_valid_multi_agent_request(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    team = create_team(fake_db, "Engineering", mgr["_id"])
    token = make_token(mgr["_id"])

    corr_id = str(uuid.uuid4())
    prod_finding = AgentFinding(
        agent="productivity",
        correlation_id=corr_id,
        summary="Task delay identified in backend module.",
        confidence=0.90,
    )
    collab_finding = AgentFinding(
        agent="collaboration",
        correlation_id=corr_id,
        summary="Cross-team response latency is elevated.",
        confidence=0.88,
    )
    synth_finding = AgentFinding(
        agent="coordinator",
        correlation_id=corr_id,
        summary="Backend module delay is exacerbated by cross-team communication friction.",
        confidence=0.89,
        recommended_actions=["Schedule alignment sync."],
    )

    mock_coord = MockCoordinator(
        result=CoordinatorExecutionResult(
            correlation_id=corr_id,
            intent="task_delay_analysis",
            status="completed",
            findings=[prod_finding, collab_finding],
            synthesized_finding=synth_finding,
            errors=[],
        )
    )
    app.dependency_overrides[get_agent_coordinator] = lambda: mock_coord
    try:
        resp = client.post(
            "/agents/execute",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "intent": "task_delay_analysis",
                "question": "What is causing the delays on task 456?",
                "target_team_id": str(team["_id"]),
                "target_task_id": "task_456",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert "exacerbated by cross-team" in data["summary"]
        assert len(data["findings"]) == 2
        assert data["findings"][0]["agent"] == "productivity"
        assert data["findings"][1]["agent"] == "collaboration"
        assert len(data["recommended_actions"]) == 1
    finally:
        app.dependency_overrides.pop(get_agent_coordinator, None)


def test_partial_coordinator_result_returns_200(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    token = make_token(mgr["_id"])

    corr_id = str(uuid.uuid4())
    prod_finding = AgentFinding(
        agent="productivity",
        correlation_id=corr_id,
        summary="Productivity analysis completed successfully.",
        confidence=0.85,
    )
    mock_coord = MockCoordinator(
        result=CoordinatorExecutionResult(
            correlation_id=corr_id,
            intent="task_delay_analysis",
            status="partial",
            findings=[prod_finding],
            synthesized_finding=prod_finding,
            errors=[{"agent": "collaboration", "error_code": "EXECUTION_TIMEOUT", "message": "Collaboration agent timed out"}],
            safe_error_message="Collaboration agent timed out",
        )
    )
    app.dependency_overrides[get_agent_coordinator] = lambda: mock_coord
    try:
        resp = client.post(
            "/agents/execute",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "intent": "task_delay_analysis",
                "question": "Analyze delays",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "partial"
        assert len(data["findings"]) == 1
        assert len(data["errors"]) == 1
        assert data["errors"][0]["agent"] == "collaboration"
        assert data["errors"][0]["error_code"] == "EXECUTION_TIMEOUT"
    finally:
        app.dependency_overrides.pop(get_agent_coordinator, None)


# =========================================================================
# Error Mapping Tests
# =========================================================================


def test_timeout_maps_to_504(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    token = make_token(mgr["_id"])

    mock_coord = MockCoordinator(
        result=CoordinatorExecutionResult(
            correlation_id=str(uuid.uuid4()),
            intent="productivity_analysis",
            status="failed",
            errors=[{"agent": "coordinator", "error_code": "EXECUTION_TIMEOUT", "message": "Multi-agent execution timed out"}],
            safe_error_message="Multi-agent execution timed out",
        )
    )
    app.dependency_overrides[get_agent_coordinator] = lambda: mock_coord
    try:
        resp = client.post(
            "/agents/execute",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "intent": "productivity_analysis",
                "question": "Analyze productivity",
            },
        )
        assert resp.status_code == 504
        assert "timed out" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_agent_coordinator, None)


def test_provider_unavailable_maps_to_503(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    token = make_token(mgr["_id"])

    mock_coord = MockCoordinator(
        result=CoordinatorExecutionResult(
            correlation_id=str(uuid.uuid4()),
            intent="productivity_analysis",
            status="failed",
            errors=[{"agent": "coordinator", "error_code": "LLM_PROVIDER_ERROR", "message": "LLM provider service unavailable"}],
            safe_error_message="LLM provider service unavailable",
        )
    )
    app.dependency_overrides[get_agent_coordinator] = lambda: mock_coord
    try:
        resp = client.post(
            "/agents/execute",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "intent": "productivity_analysis",
                "question": "Analyze productivity",
            },
        )
        assert resp.status_code == 503
        assert "unavailable" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_agent_coordinator, None)


def test_resource_not_found_maps_to_404(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    token = make_token(mgr["_id"])

    mock_coord = MockCoordinator(
        result=CoordinatorExecutionResult(
            correlation_id=str(uuid.uuid4()),
            intent="task_assignment_recommendation",
            status="failed",
            errors=[{"agent": "task_assigning", "error_code": "TARGET_TASK_NOT_FOUND", "message": "Target task 999 not found"}],
            safe_error_message="Target task 999 not found",
        )
    )
    app.dependency_overrides[get_agent_coordinator] = lambda: mock_coord
    try:
        resp = client.post(
            "/agents/execute",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "intent": "task_assignment_recommendation",
                "question": "Recommend assignees for task 999",
                "target_task_id": "999",
            },
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_agent_coordinator, None)


def test_unexpected_coordinator_exception_maps_to_500(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    token = make_token(mgr["_id"])

    mock_coord = MockCoordinator(raise_exc=RuntimeError("Internal coordinator crash"))
    app.dependency_overrides[get_agent_coordinator] = lambda: mock_coord
    try:
        resp = client.post(
            "/agents/execute",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "intent": "productivity_analysis",
                "question": "Analyze productivity",
            },
        )
        assert resp.status_code == 500
        assert "Internal coordinator crash" not in resp.json()["detail"]
        assert "internal error occurred" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_agent_coordinator, None)


# =========================================================================
# Read-Only & Zero-Leakage Privacy Invariants
# =========================================================================


def test_execute_causes_zero_database_writes(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    token = make_token(mgr["_id"])

    tasks_count_before = len(fake_db["tasks"].docs)
    users_count_before = len(fake_db["users"].docs)
    teams_count_before = len(fake_db["teams"].docs)

    mock_coord = MockCoordinator()
    app.dependency_overrides[get_agent_coordinator] = lambda: mock_coord
    try:
        resp = client.post(
            "/agents/execute",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "intent": "productivity_analysis",
                "question": "Analyze productivity",
            },
        )
        assert resp.status_code == 200
        assert len(fake_db["tasks"].docs) == tasks_count_before
        assert len(fake_db["users"].docs) == users_count_before
        assert len(fake_db["teams"].docs) == teams_count_before
    finally:
        app.dependency_overrides.pop(get_agent_coordinator, None)


def test_response_contains_no_prompts_or_raw_evidence(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    token = make_token(mgr["_id"])

    mock_coord = MockCoordinator()
    app.dependency_overrides[get_agent_coordinator] = lambda: mock_coord
    try:
        resp = client.post(
            "/agents/execute",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "intent": "productivity_analysis",
                "question": "Analyze productivity",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        raw_text = resp.text
        assert "prompt" not in data
        assert "evidence_source_records" not in data
        assert "database" not in data
        assert "GEMINI_API_KEY" not in raw_text
    finally:
        app.dependency_overrides.pop(get_agent_coordinator, None)


# =========================================================================
# Role-Filtered Capabilities Endpoint Tests
# =========================================================================


def test_capabilities_employee_filtered(test_setup):
    client, fake_db = test_setup
    emp = create_user(fake_db, email="emp@example.com", role="employee")
    token = make_token(emp["_id"])

    resp = client.get(
        "/agents/capabilities",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "employee"
    intents = [item["intent"] for item in data["supported_intents"]]
    assert "productivity_analysis" in intents
    assert "collaboration_analysis" in intents
    assert "task_assignment_recommendation" not in intents
    assert "team_workload_analysis" not in intents
    assert len(data["available_specialists"]) == 4
    assert len(data["advisory_limitations"]) > 0


def test_capabilities_manager_filtered(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    token = make_token(mgr["_id"])

    resp = client.get(
        "/agents/capabilities",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "manager"
    intents = [item["intent"] for item in data["supported_intents"]]
    assert "task_assignment_recommendation" in intents
    assert "team_workload_analysis" in intents
    assert "productivity_analysis" in intents
    assert "collaboration_analysis" in intents


def test_capabilities_admin_filtered(test_setup):
    client, fake_db = test_setup
    admin = create_user(fake_db, email="admin@example.com", role="admin")
    token = make_token(admin["_id"])

    resp = client.get(
        "/agents/capabilities",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "admin"
    intents = [item["intent"] for item in data["supported_intents"]]
    assert "general_workforce_question" in intents
    assert "task_assignment_recommendation" not in intents


def test_execute_generates_valid_correlation_id_when_omitted(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    token = make_token(mgr["_id"])

    mock_coord = MockCoordinator()
    app.dependency_overrides[get_agent_coordinator] = lambda: mock_coord
    try:
        resp = client.post(
            "/agents/execute",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "intent": "productivity_analysis",
                "question": "Analyze productivity",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "correlation_id" in data
        assert len(data["correlation_id"]) == 36
        # Verify valid UUID
        parsed_uuid = uuid.UUID(data["correlation_id"])
        assert str(parsed_uuid) == data["correlation_id"]
        assert len(mock_coord.invocations) == 1
        assert mock_coord.invocations[0].correlation_id == data["correlation_id"]
    finally:
        app.dependency_overrides.pop(get_agent_coordinator, None)


def test_coordinator_invoked_exactly_once(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    token = make_token(mgr["_id"])

    mock_coord = MockCoordinator()
    app.dependency_overrides[get_agent_coordinator] = lambda: mock_coord
    try:
        resp = client.post(
            "/agents/execute",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "intent": "productivity_analysis",
                "question": "Analyze productivity",
            },
        )
        assert resp.status_code == 200
        assert len(mock_coord.invocations) == 1
    finally:
        app.dependency_overrides.pop(get_agent_coordinator, None)


def test_wellbeing_to_task_assignment_isolation(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    token = make_token(mgr["_id"])

    mock_coord = MockCoordinator(
        result=CoordinatorExecutionResult(
            correlation_id=str(uuid.uuid4()),
            intent="task_assignment_recommendation",
            status="failed",
            errors=[{
                "agent": "coordinator",
                "error_code": "WELLBEING_TASK_ASSIGNMENT_FORBIDDEN",
                "message": "Well-being pulse data is strictly isolated from task assignment recommendations",
            }],
            safe_error_message="Well-being pulse data is strictly isolated from task assignment recommendations",
        )
    )
    app.dependency_overrides[get_agent_coordinator] = lambda: mock_coord
    try:
        resp = client.post(
            "/agents/execute",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "intent": "task_assignment_recommendation",
                "question": "Recommend assignees using wellbeing scores",
                "target_task_id": "task_123",
            },
        )
        assert resp.status_code == 403
        assert "strictly isolated" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_agent_coordinator, None)


def test_missing_llm_configuration_fails_closed_with_503(test_setup, monkeypatch):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    token = make_token(mgr["_id"])

    # Clear app.state.agent_coordinator and env keys
    if hasattr(app.state, "agent_coordinator"):
        delattr(app.state, "agent_coordinator")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")

    resp = client.post(
        "/agents/execute",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "intent": "productivity_analysis",
            "question": "Analyze productivity without LLM config",
        },
    )
    assert resp.status_code == 503
    assert "LLM service is not configured or unavailable" in resp.json()["detail"]


# =========================================================================
# Regression Tests for Production Contract Audit
# =========================================================================


def test_weeks_lookback_bounded_1_to_12_regression(test_setup):
    """Verifies weeks_lookback is strictly validated between 1 and 12."""
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr_wb@example.com", role="manager")
    token = make_token(mgr["_id"])

    # 13 is above specialist maximum (12) -> rejected with 422
    resp_over = client.post(
        "/agents/execute",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "intent": "wellbeing_analysis",
            "question": "Analyze wellbeing trends",
            "weeks_lookback": 13,
        },
    )
    assert resp_over.status_code == 422

    # 0 is below specialist minimum (1) -> rejected with 422
    resp_zero = client.post(
        "/agents/execute",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "intent": "wellbeing_analysis",
            "question": "Analyze wellbeing trends",
            "weeks_lookback": 0,
        },
    )
    assert resp_zero.status_code == 422


def test_missing_task_assignment_target_fails_validation(test_setup):
    """Verifies task_assignment_recommendation fails validation when target_task_id is omitted or empty."""
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr_ta@example.com", role="manager")
    token = make_token(mgr["_id"])

    # Missing target_task_id
    resp_missing = client.post(
        "/agents/execute",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "intent": "task_assignment_recommendation",
            "question": "Recommend assignees for new task",
        },
    )
    assert resp_missing.status_code == 422

    # Empty/whitespace target_task_id
    resp_empty = client.post(
        "/agents/execute",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "intent": "task_assignment_recommendation",
            "question": "Recommend assignees for new task",
            "target_task_id": "   ",
        },
    )
    assert resp_empty.status_code == 422


def test_irrelevant_target_fields_rejected_by_intent(test_setup):
    """Verifies that irrelevant target_task_id and weeks_lookback are rejected for mismatched intents."""
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr_irr@example.com", role="manager")
    token = make_token(mgr["_id"])

    # Wellbeing analysis rejects target_task_id
    resp_wb = client.post(
        "/agents/execute",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "intent": "wellbeing_analysis",
            "question": "Check team wellbeing",
            "target_task_id": "task_123",
        },
    )
    assert resp_wb.status_code == 422

    # Task assignment rejects weeks_lookback
    resp_ta_wb = client.post(
        "/agents/execute",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "intent": "task_assignment_recommendation",
            "question": "Recommend assignees for task",
            "target_task_id": "task_123",
            "weeks_lookback": 4,
        },
    )
    assert resp_ta_wb.status_code == 422


@pytest.mark.asyncio
async def test_simultaneous_coordinator_dependency_resolution(fake_db):
    """Verifies that simultaneous calls to get_agent_coordinator create exactly one shared instance."""
    import asyncio
    from fastapi import Request

    class DummyState:
        def __init__(self):
            self.database = fake_db

    class DummyApp:
        def __init__(self):
            self.state = DummyState()

    mock_request = type("MockReq", (), {"app": DummyApp()})()

    # Launch 10 concurrent requests to resolve coordinator
    results = await asyncio.gather(
        *(get_agent_coordinator(mock_request) for _ in range(10))
    )

    first_coord = results[0]
    for coord in results[1:]:
        assert coord is first_coord
    assert mock_request.app.state.agent_coordinator is first_coord


@pytest.mark.asyncio
async def test_resolve_principal_objectid_and_string_normalization(fake_db):
    """Verifies resolve_authenticated_principal normalizes ObjectId and string representations."""
    mgr_oid = ObjectId()
    team1 = create_team(fake_db, "Alpha Team", manager_id=mgr_oid)
    # Team 2 has string manager_id representation
    team2_doc = {
        "_id": ObjectId(),
        "name": "Beta Team",
        "manager_id": str(mgr_oid),
        "created_at": datetime.now(timezone.utc),
    }
    fake_db["teams"].docs.append(team2_doc)

    mgr_user = {
        "_id": mgr_oid,
        "name": "Manager User",
        "email": "mgr_norm@example.com",
        "role": "manager",
        "is_active": True,
    }

    principal = await resolve_authenticated_principal(fake_db, mgr_user)
    assert principal.user_id == str(mgr_oid)
    assert principal.role == "manager"
    assert str(team1["_id"]) in principal.managed_team_ids
    assert str(team2_doc["_id"]) in principal.managed_team_ids

    # Admin principal receives no fabricated team assignments
    admin_user = {
        "_id": ObjectId(),
        "name": "Admin User",
        "email": "admin_norm@example.com",
        "role": "admin",
        "is_active": True,
        "team_id": ObjectId(),
    }
    admin_principal = await resolve_authenticated_principal(fake_db, admin_user)
    assert admin_principal.role == "admin"
    assert admin_principal.assigned_team_id is None
    assert admin_principal.managed_team_ids == []

    # Employee principal receives only assigned_team_id
    emp_team_oid = ObjectId()
    emp_user = {
        "_id": ObjectId(),
        "name": "Emp User",
        "email": "emp_norm@example.com",
        "role": "employee",
        "is_active": True,
        "team_id": emp_team_oid,
    }
    emp_principal = await resolve_authenticated_principal(fake_db, emp_user)
    assert emp_principal.role == "employee"
    assert emp_principal.assigned_team_id == str(emp_team_oid)
    assert emp_principal.managed_team_ids == []


@pytest.mark.asyncio
async def test_resolve_principal_inactive_and_malformed_fail_closed(fake_db):
    """Verifies that inactive or malformed users fail closed with 401."""
    from fastapi import HTTPException

    inactive_user = {
        "_id": ObjectId(),
        "name": "Inactive User",
        "email": "inactive@example.com",
        "role": "employee",
        "is_active": False,
    }
    with pytest.raises(HTTPException) as exc_info:
        await resolve_authenticated_principal(fake_db, inactive_user)
    assert exc_info.value.status_code == 401

    malformed_user = {"role": "manager"}
    with pytest.raises(HTTPException) as exc_info2:
        await resolve_authenticated_principal(fake_db, malformed_user)
    assert exc_info2.value.status_code == 401


def test_capabilities_match_runtime_authorization_for_all_roles(test_setup):
    """Verifies that /agents/capabilities matches authorize_user_intent for all roles."""
    from backend.app.modules.agents.security_policy import (
        AuthenticatedPrincipal,
        authorize_user_intent,
    )
    from backend.app.modules.agents.protocol import AgentIntent

    all_intents: list[AgentIntent] = [
        "productivity_analysis",
        "collaboration_analysis",
        "wellbeing_analysis",
        "task_assignment_recommendation",
        "task_delay_analysis",
        "team_workload_analysis",
        "general_workforce_question",
    ]

    client, fake_db = test_setup

    for role in ("employee", "manager", "admin"):
        user = create_user(fake_db, email=f"{role}_caps@example.com", role=role)
        token = make_token(user["_id"])

        resp = client.get(
            "/agents/capabilities",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        caps_data = resp.json()
        caps_intents = {item["intent"] for item in caps_data["supported_intents"]}

        principal = AuthenticatedPrincipal(
            user_id=str(user["_id"]),
            role=role,  # type: ignore
            assigned_team_id="team_1",
            managed_team_ids=["team_1"] if role == "manager" else [],
        )

        for intent in all_intents:
            target_team = "team_1"
            auth_decision = authorize_user_intent(principal, intent, target_team_id=target_team)
            if auth_decision.allowed:
                assert intent in caps_intents, f"Role '{role}' authorized for '{intent}' but missing in capabilities"
            else:
                assert intent not in caps_intents, f"Role '{role}' denied for '{intent}' but present in capabilities"
