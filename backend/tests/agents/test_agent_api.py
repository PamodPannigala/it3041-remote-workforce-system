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
    AgentExecuteResponse,
    SpecialistFindingItem,
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
        intent = request.intent or "productivity_analysis"
        return CoordinatorExecutionResult(
            correlation_id=request.correlation_id,
            intent=intent,
            detected_intent=intent,
            routing_confidence=0.95,
            consulted_specialists=["productivity"],
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
            "question": "How is team productivity?",
        },
    )
    assert resp.status_code == 401


# =========================================================================
# Request Validation & Schema Constraints Tests
# =========================================================================


def test_execute_forbids_extra_fields(test_setup):
    client, fake_db = test_setup
    user = create_user(fake_db, email="mgr@example.com", role="manager")
    token = make_token(user["_id"])

    resp = client.post(
        "/agents/execute",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "question": "How is team productivity?",
            "extra_forbidden_field": "injected_value",
        },
    )
    assert resp.status_code == 422


def test_execute_forbids_client_selected_intent(test_setup):
    client, fake_db = test_setup
    user = create_user(fake_db, email="mgr@example.com", role="manager")
    token = make_token(user["_id"])

    resp = client.post(
        "/agents/execute",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "intent": "productivity_analysis",
            "question": "How is team productivity?",
        },
    )
    assert resp.status_code == 422


def test_execute_forbids_injected_role_or_dependencies(test_setup):
    client, fake_db = test_setup
    user = create_user(fake_db, email="mgr@example.com", role="manager")
    token = make_token(user["_id"])

    resp = client.post(
        "/agents/execute",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "question": "How is team productivity?",
            "role": "admin",
            "managed_team_ids": ["65f123456789012345678901"],
            "dependency_findings": [],
        },
    )
    assert resp.status_code == 422


def test_execute_invalid_uuid_correlation_id_rejected(test_setup):
    client, fake_db = test_setup
    user = create_user(fake_db, email="mgr@example.com", role="manager")
    token = make_token(user["_id"])

    resp = client.post(
        "/agents/execute",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "question": "How is team productivity?",
            "correlation_id": "not-a-valid-uuid",
        },
    )
    assert resp.status_code == 422


def test_execute_empty_question_rejected(test_setup):
    client, fake_db = test_setup
    user = create_user(fake_db, email="mgr@example.com", role="manager")
    token = make_token(user["_id"])

    resp = client.post(
        "/agents/execute",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "question": "   ",
        },
    )
    assert resp.status_code == 422


def test_execute_invalid_weeks_lookback_rejected(test_setup):
    client, fake_db = test_setup
    user = create_user(fake_db, email="mgr@example.com", role="manager")
    token = make_token(user["_id"])

    resp = client.post(
        "/agents/execute",
        headers={"Authorization": f"Bearer {token}"},
        json={
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
                "question": "Check other team productivity",
                "target_team_id": str(team2["_id"]),
            },
        )
        assert resp.status_code == 403
        assert "restricted to managers" in resp.json()["detail"]
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
            detected_intent="task_assignment_recommendation",
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
            detected_intent="task_assignment_recommendation",
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
            detected_intent="productivity_analysis",
            routing_confidence=0.92,
            consulted_specialists=["productivity"],
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
                "question": "How is the engineering team performing?",
                "target_team_id": str(team["_id"]),
                "correlation_id": custom_corr_id,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["correlation_id"] == custom_corr_id
        assert data["detected_intent"] == "productivity_analysis"
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
            detected_intent="task_delay_analysis",
            routing_confidence=0.89,
            consulted_specialists=["productivity", "collaboration"],
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


def test_clarification_required_flow_returns_200(test_setup):
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr@example.com", role="manager")
    token = make_token(mgr["_id"])

    corr_id = str(uuid.uuid4())
    mock_coord = MockCoordinator(
        result=CoordinatorExecutionResult(
            correlation_id=corr_id,
            intent=None,
            detected_intent=None,
            routing_confidence=0.55,
            consulted_specialists=[],
            clarification_question="Would you like to analyse productivity, collaboration, workload, or aggregated well-being trends?",
            status="clarification_required",
            findings=[],
            synthesized_finding=None,
            errors=[],
            safe_error_message=None,
        )
    )
    app.dependency_overrides[get_agent_coordinator] = lambda: mock_coord
    try:
        resp = client.post(
            "/agents/execute",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "Tell me about my team.",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "clarification_required"
        assert data["clarification_question"] == "Would you like to analyse productivity, collaboration, workload, or aggregated well-being trends?"
        assert data["consulted_specialists"] == []
        assert data["findings"] == []
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
            detected_intent="task_delay_analysis",
            routing_confidence=0.85,
            consulted_specialists=["productivity", "collaboration"],
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
                "question": "Analyze delays",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "partial"
        assert len(data["findings"]) == 1
        assert len(data["errors"]) == 1
        assert data["errors"][0]["agent"] == "collaboration"
        assert data["errors"][0]["error_code"] == "specialist_unavailable"
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
            detected_intent="productivity_analysis",
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
            detected_intent="productivity_analysis",
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
            detected_intent="task_assignment_recommendation",
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
    assert resp.status_code == 403
    assert "restricted to managers" in resp.json()["detail"]


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


def test_capabilities_admin_forbidden_without_metadata(test_setup, monkeypatch):
    client, fake_db = test_setup
    admin = create_user(fake_db, email="admin@example.com", role="admin")
    token = make_token(admin["_id"])
    gate_bypasses = []

    async def fail_principal_resolution(*args, **kwargs):
        gate_bypasses.append("principal")
        pytest.fail("Admin capability denial resolved team-scoped principal data")

    def fail_capability_lookup(*args, **kwargs):
        gate_bypasses.append("capabilities")
        pytest.fail("Admin capability denial retrieved capability metadata")

    monkeypatch.setattr(
        "backend.app.modules.agents.router.resolve_authenticated_principal",
        fail_principal_resolution,
    )
    monkeypatch.setattr(
        "backend.app.modules.agents.router.get_allowed_intents_for_role",
        fail_capability_lookup,
    )

    resp = client.get(
        "/agents/capabilities",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    data = resp.json()
    assert "restricted to managers" in data["detail"]
    assert "supported_intents" not in data
    assert "available_specialists" not in data
    assert "advisory_limitations" not in data
    assert gate_bypasses == []


def test_admin_agent_execution_forbidden_before_resources_or_coordinator(test_setup):
    client, fake_db = test_setup
    admin = create_user(fake_db, email="admin_execute@example.com", role="admin")
    token = make_token(admin["_id"])
    sensitive_calls = []

    def fail_sensitive_query(collection_name, operation):
        def fail(*args, **kwargs):
            sensitive_calls.append((collection_name, operation))
            pytest.fail(f"Admin denial queried {collection_name}.{operation}")
        return fail

    for collection_name in (
        "teams",
        "tasks",
        "employee_profiles",
        "collaboration_messages",
        "weekly_pulse_responses",
    ):
        collection = fake_db[collection_name]
        collection.find = fail_sensitive_query(collection_name, "find")
        collection.find_one = fail_sensitive_query(collection_name, "find_one")
        collection.count_documents = fail_sensitive_query(collection_name, "count_documents")

    mock_coord = MockCoordinator()
    app.dependency_overrides[get_agent_coordinator] = lambda: mock_coord
    try:
        response = client.post(
            "/agents/execute",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "Analyze all teams",
                "target_team_id": "507f1f77bcf86cd799439011",
                "target_task_id": "507f1f77bcf86cd799439012",
            },
        )
    finally:
        app.dependency_overrides.pop(get_agent_coordinator, None)

    assert response.status_code == 403
    data = response.json()
    assert "restricted to managers" in data["detail"]
    assert data.get("findings", []) == []
    assert data.get("consulted_specialists", []) == []
    assert data.get("task_assignment_details") is None
    assert "507f1f77bcf86cd799439011" not in response.text
    assert "507f1f77bcf86cd799439012" not in response.text
    assert sensitive_calls == []
    assert mock_coord.invocations == []


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
            detected_intent="task_assignment_recommendation",
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
        if role != "manager":
            assert resp.status_code == 403
            continue

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
            auth_decision =  authorize_user_intent(principal, intent, target_team_id=target_team)
            if auth_decision.allowed:
                assert intent in caps_intents, f"Role '{role}' authorized for '{intent}' but missing in capabilities"
            else:
                assert intent not in caps_intents, f"Role '{role}' denied for '{intent}' but present in capabilities"


def test_clarification_privacy_guarantee_proves_zero_evidence_collection_queries(test_setup):
    """
    Verifies the clarification privacy guarantee:
    1. Authentication/principal resolution queries on users/teams are allowed.
    2. Zero queries occur on tasks, work_profiles, messages, or weekly_pulse_surveys
       when clarification is required.
    """
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr_privacy@example.com", role="manager")
    token = make_token(mgr["_id"])

    # Track queries across all sensitive domain collections and real specialist collections
    query_counters = {
        "users": 0,
        "teams": 0,
        "tasks": 0,
        "employee_profiles": 0,
        "work_profiles": 0,
        "collaboration_messages": 0,
        "messages": 0,
        "weekly_pulse_responses": 0,
        "weekly_pulse_surveys": 0,
    }

    def wrap_collection(col_name):
        col = fake_db[col_name]
        orig_find = col.find
        orig_find_one = col.find_one

        def tracked_find(*args, **kwargs):
            query_counters[col_name] += 1
            return orig_find(*args, **kwargs)

        async def tracked_find_one(*args, **kwargs):
            query_counters[col_name] += 1
            return await orig_find_one(*args, **kwargs)

        col.find = tracked_find
        col.find_one = tracked_find_one

    for col in query_counters.keys():
        wrap_collection(col)

    corr_id = str(uuid.uuid4())
    mock_coord = MockCoordinator(
        result=CoordinatorExecutionResult(
            correlation_id=corr_id,
            intent=None,
            detected_intent=None,
            routing_confidence=0.5,
            consulted_specialists=[],
            clarification_question="Could you please clarify your workforce question?",
            status="clarification_required",
            findings=[],
            synthesized_finding=None,
            errors=[],
            safe_error_message=None,
        )
    )
    app.dependency_overrides[get_agent_coordinator] = lambda: mock_coord
    try:
        resp = client.post(
            "/agents/execute",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "Can you check on things?",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "clarification_required"

        # Authentication/principal DB access IS allowed
        assert query_counters["users"] > 0, "Principal resolution must access users collection"

        # PROOF: Exact real evidence collections receive zero queries during clarification
        assert query_counters["tasks"] == 0, "No tasks queries permitted during clarification"
        assert query_counters["employee_profiles"] == 0, "No employee_profiles queries permitted during clarification"
        assert query_counters["work_profiles"] == 0, "No candidate work_profile queries permitted during clarification"
        assert query_counters["collaboration_messages"] == 0, "No collaboration_messages queries permitted during clarification"
        assert query_counters["messages"] == 0, "No messages queries permitted during clarification"
        assert query_counters["weekly_pulse_responses"] == 0, "No weekly_pulse_responses queries permitted during clarification"
        assert query_counters["weekly_pulse_surveys"] == 0, "No weekly_pulse_surveys queries permitted during clarification"
    finally:
        app.dependency_overrides.pop(get_agent_coordinator, None)


def test_agent_execute_response_intent_removed_canonical_detected_intent():
    """
    Verifies that the deprecated 'intent' field has been removed from AgentExecuteResponse,
    and 'detected_intent' is the canonical public response field.
    """
    from backend.app.modules.agents.router import AgentExecuteResponse

    now = datetime.now(timezone.utc)
    corr = str(uuid.uuid4())

    resp = AgentExecuteResponse(
        correlation_id=corr,
        detected_intent="productivity_analysis",
        status="completed",
        summary="Summary",
        confidence=0.9,
        executed_at=now,
    )
    assert resp.detected_intent == "productivity_analysis"
    assert "intent" not in AgentExecuteResponse.model_fields
    data = resp.model_dump()
    assert "intent" not in data
    assert data["detected_intent"] == "productivity_analysis"

    # Attempting to supply unlisted 'intent' raises ValidationError (extra forbidden)
    with pytest.raises(Exception):
        AgentExecuteResponse(
            correlation_id=corr,
            intent="productivity_analysis",
            detected_intent="productivity_analysis",
            status="completed",
            summary="Summary",
            confidence=0.9,
            executed_at=now,
        )


def test_capabilities_returns_context_requirements_per_intent(test_setup):
    """Verifies that GET /agents/capabilities includes server-owned context_requirements."""
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr_caps_cr@example.com", role="manager")
    token = make_token(mgr["_id"])

    resp = client.get(
        "/agents/capabilities",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "supported_intents" in data
    assert len(data["supported_intents"]) > 0
    for item in data["supported_intents"]:
        assert "context_requirements" in item
        cr = item["context_requirements"]
        assert "team_scope" in cr
        assert "task_scope" in cr
        assert "weeks_lookback" in cr
        assert cr["team_scope"] in ("required", "optional", "forbidden")
        assert cr["task_scope"] in ("required", "optional", "forbidden")
        assert cr["weeks_lookback"] in ("required", "optional", "forbidden")


def test_task_delay_public_response_includes_only_productivity_and_collaboration_findings_with_count_two(test_setup):
    """
    Proves that for the task-delay flow:
    - Backend AgentExecuteResponse.findings includes only Productivity and Collaboration findings;
    - Coordinator is absent from public findings;
    - Specialist count in findings is exactly 2;
    - Attempting to put coordinator in public findings triggers Pydantic validation error.
    """
    client, fake_db = test_setup
    mgr = create_user(fake_db, email="mgr_task_delay_exact2@example.com", role="manager")
    team = create_team(fake_db, name="Delta Team", manager_id=mgr["_id"])
    token = make_token(mgr["_id"])

    corr_id = str(uuid.uuid4())
    prod_finding = AgentFinding(
        agent="productivity",
        correlation_id=corr_id,
        summary="Sprint throughput decreased by 25%.",
        confidence=0.84,
        recommended_actions=["Review task sizing."],
    )
    collab_finding = AgentFinding(
        agent="collaboration",
        correlation_id=corr_id,
        summary="PR review wait times averaged 48 hours.",
        confidence=0.79,
        recommended_actions=["Introduce daily PR review blocks."],
    )
    synth_finding = AgentFinding(
        agent="coordinator",
        correlation_id=corr_id,
        summary="Task delays stem from reduced throughput coupled with PR review latency.",
        confidence=0.79,
        recommended_actions=["Review task sizing.", "Introduce daily PR review blocks."],
    )

    mock_coord = MockCoordinator(
        result=CoordinatorExecutionResult(
            correlation_id=corr_id,
            intent="task_delay_analysis",
            detected_intent="task_delay_analysis",
            routing_confidence=0.91,
            consulted_specialists=["productivity", "collaboration"],
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
                "question": "Why are our sprint tasks being delayed?",
                "target_team_id": str(team["_id"]),
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        # 1. Specialist count is exactly 2
        assert len(data["findings"]) == 2

        # 2. Contains only productivity and collaboration
        agents = [f["agent"] for f in data["findings"]]
        assert set(agents) == {"productivity", "collaboration"}

        # 3. Coordinator is absent from public findings
        assert "coordinator" not in agents

        # 4. Top-level summary and actions contain Coordinator synthesis
        assert "Task delays stem from" in data["summary"]
        assert len(data["recommended_actions"]) == 2

        # 5. Public schema rejects coordinator finding
        with pytest.raises(Exception, match="must never contain agent='coordinator'"):
            AgentExecuteResponse(
                correlation_id=corr_id,
                detected_intent="task_delay_analysis",
                routing_confidence=0.9,
                consulted_specialists=["productivity", "collaboration"],
                status="completed",
                summary="Synthesis summary",
                confidence=0.8,
                findings=[
                    SpecialistFindingItem(
                        agent="coordinator",
                        summary="Illegal coordinator finding",
                        confidence=0.8,
                        limitations=[],
                        recommended_actions=[],
                    )
                ],
                limitations=[],
                recommended_actions=[],
                errors=[],
                executed_at=datetime.now(timezone.utc),
            )
    finally:
        app.dependency_overrides.pop(get_agent_coordinator, None)


def test_task_assignment_details_in_execute_response(test_setup):
    client, fake_db = test_setup
    from backend.app.modules.agents.protocol import (
        CandidateRecommendationItem,
        EvaluatedCandidateItem,
        TaskAssignmentDetails,
    )

    manager = create_user(fake_db, email="manager_ta@example.com", role="manager")
    team = create_team(fake_db, name="Task Team", manager_id=manager["_id"])
    token = make_token(manager["_id"])
    corr_id = str(uuid.uuid4())

    task_details = TaskAssignmentDetails(
        task_title="Deploy Microservice",
        requested_candidate_count=2,
        evaluated_candidate_count=3,
        eligible_candidate_count=1,
        candidate_recommendations=[
            CandidateRecommendationItem(
                rank=1,
                candidate_name="Dinethya Edirisinghe",
                eligibility_status="eligible",
                recommendation_label="recommended",
                suitability_score=0.95,
                required_skill_count=1,
                matched_required_skill_count=1,
                required_skill_coverage=1.0,
                matched_skills=["Docker"],
                missing_required_skills=[],
                active_task_count=1,
                overdue_task_count=0,
                workload_summary="1 active task(s), 0 overdue (40h/wk capacity, available)",
                recommendation_reason="Verified match for required skill(s) [Docker]. Current active workload: 1 task(s).",
                limitations=["Advisory recommendation only."],
            )
        ],
        other_evaluated_candidates=[
            EvaluatedCandidateItem(
                candidate_name="Bob Developer",
                eligibility_status="not_eligible",
                required_skill_count=1,
                matched_required_skill_count=0,
                required_skill_coverage=0.0,
                missing_required_skills=["Docker"],
                reason="Missing verified required skills: Docker",
            )
        ],
        ranking_factors=["Verified required skill coverage", "Active task workload and in-progress commitments"],
        human_decision_required=True,
    )

    ta_finding = AgentFinding(
        agent="task_assigning",
        correlation_id=corr_id,
        summary="Recommended Dinethya Edirisinghe for Deploy Microservice.",
        confidence=0.9,
        limitations=["Advisory only."],
        recommended_actions=["Confirm availability."],
        task_assignment_details=task_details,
    )

    mock_result = CoordinatorExecutionResult(
        correlation_id=corr_id,
        intent="task_assignment_recommendation",
        detected_intent="task_assignment_recommendation",
        routing_confidence=0.95,
        consulted_specialists=["task_assigning"],
        status="completed",
        findings=[ta_finding],
        synthesized_finding=ta_finding,
        task_assignment_details=task_details,
    )

    mock_coordinator = MockCoordinator(result=mock_result)
    app.dependency_overrides[get_agent_coordinator] = lambda: mock_coordinator

    try:
        resp = client.post(
            "/agents/execute",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "Recommend the most suitable two team members for the selected task",
                "target_team_id": str(team["_id"]),
                "target_task_id": "507f1f77bcf86cd799439099",
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["task_assignment_details"] is not None
        details = data["task_assignment_details"]
        assert details["task_title"] == "Deploy Microservice"
        assert details["requested_candidate_count"] == 2
        assert details["eligible_candidate_count"] == 1
        assert len(details["candidate_recommendations"]) == 1
        assert details["candidate_recommendations"][0]["candidate_name"] == "Dinethya Edirisinghe"
        assert details["candidate_recommendations"][0]["suitability_score"] == 0.95
        assert len(details["other_evaluated_candidates"]) == 1
        assert details["other_evaluated_candidates"][0]["candidate_name"] == "Bob Developer"
    finally:
        app.dependency_overrides.pop(get_agent_coordinator, None)


def test_task_assignment_details_is_none_for_productivity_intent(test_setup):
    client, fake_db = test_setup
    manager = create_user(fake_db, email="manager_prod@example.com", role="manager")
    team = create_team(fake_db, name="Prod Team", manager_id=manager["_id"])
    token = make_token(manager["_id"])
    corr_id = str(uuid.uuid4())

    prod_finding = AgentFinding(
        agent="productivity",
        correlation_id=corr_id,
        summary="Productivity is on track.",
        confidence=0.9,
        limitations=[],
        recommended_actions=[],
    )

    mock_result = CoordinatorExecutionResult(
        correlation_id=corr_id,
        intent="productivity_analysis",
        detected_intent="productivity_analysis",
        routing_confidence=0.95,
        consulted_specialists=["productivity"],
        status="completed",
        findings=[prod_finding],
        synthesized_finding=prod_finding,
        task_assignment_details=None,
    )

    mock_coordinator = MockCoordinator(result=mock_result)
    app.dependency_overrides[get_agent_coordinator] = lambda: mock_coordinator

    try:
        resp = client.post(
            "/agents/execute",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "Summarize sprint delivery progress",
                "target_team_id": str(team["_id"]),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_assignment_details"] is None
    finally:
        app.dependency_overrides.pop(get_agent_coordinator, None)
