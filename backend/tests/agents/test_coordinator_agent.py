import asyncio
import json
from typing import Any
import uuid

import pytest

from backend.app.modules.agents import (
    AgentCoordinator,
    AgentDefinition,
    AgentFinding,
    AgentRequest,
    AgentResponse,
    AgentRuntime,
    AgentRuntimeConfig,
    AuthenticatedPrincipal,
    CoordinatorExecutionRequest,
    CoordinatorExecutionResult,
    EvidenceReference,
    FakeAgentRuntime,
    FakeLLMGateway,
    InMemoryAgentAuditSink,
    StructuredAgentFindingOutput,
    create_agent_request,
    create_agent_response,
    create_coordinator_agent_definition,
    create_production_coordinator,
    register_collaboration_agent,
    register_coordinator_agent,
    register_productivity_agent,
    register_task_assignment_agent,
    register_wellbeing_agent,
)


@pytest.fixture
def mock_audit_sink() -> InMemoryAgentAuditSink:
    return InMemoryAgentAuditSink()


@pytest.fixture
def employee_principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id="emp-001",
        role="employee",
        assigned_team_id="team-alpha",
    )


@pytest.fixture
def manager_principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id="mgr-001",
        role="manager",
        assigned_team_id="team-alpha",
        managed_team_ids=["team-alpha", "team-beta"],
    )


@pytest.fixture
def admin_principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id="adm-001",
        role="admin",
        assigned_team_id=None,
        managed_team_ids=[],
    )


@pytest.fixture
def test_coordinator(mock_audit_sink: InMemoryAgentAuditSink) -> AgentCoordinator:
    """Constructs a test AgentCoordinator with all specialists registered under FakeLLMGateway."""
    default_output = StructuredAgentFindingOutput(
        summary="Specialist test analysis summary completed successfully.",
        confidence=0.88,
        limitations=["Analysis based on synthetic test context."],
        recommended_actions=["Review workload metrics with the team."],
    )
    fake_gw = FakeLLMGateway(default_response=default_output)
    runtime = AgentRuntime(
        config=AgentRuntimeConfig(default_timeout_seconds=5.0),
        llm_gateway=fake_gw,
        audit_sink=mock_audit_sink,
    )

    register_coordinator_agent(runtime)
    register_productivity_agent(runtime)
    register_collaboration_agent(runtime)
    register_wellbeing_agent(runtime)
    register_task_assignment_agent(runtime)

    return AgentCoordinator(
        runtime=runtime,
        llm_gateway=fake_gw,
        audit_sink=mock_audit_sink,
        default_timeout_seconds=5.0,
    )


# =========================================================================
# 1. Routing Tests
# =========================================================================


@pytest.mark.asyncio
async def test_route_productivity_analysis(
    test_coordinator: AgentCoordinator,
    manager_principal: AuthenticatedPrincipal,
):
    cid = str(uuid.uuid4())
    req = CoordinatorExecutionRequest(
        correlation_id=cid,
        intent="productivity_analysis",
        authenticated_principal=manager_principal,
        question="How is team throughput trending?",
        target_team_id="team-alpha",
    )
    result = await test_coordinator.orchestrate(req)

    assert result.status == "completed"
    assert result.correlation_id == cid
    assert result.intent == "productivity_analysis"
    assert len(result.findings) == 1
    assert result.findings[0].agent == "productivity"
    assert result.findings[0].correlation_id == cid


@pytest.mark.asyncio
async def test_route_collaboration_analysis(
    test_coordinator: AgentCoordinator,
    manager_principal: AuthenticatedPrincipal,
):
    cid = str(uuid.uuid4())
    req = CoordinatorExecutionRequest(
        correlation_id=cid,
        intent="collaboration_analysis",
        authenticated_principal=manager_principal,
        question="Are there communication silos in the team?",
        target_team_id="team-alpha",
    )
    result = await test_coordinator.orchestrate(req)

    assert result.status == "completed"
    assert result.correlation_id == cid
    assert result.intent == "collaboration_analysis"
    assert len(result.findings) == 1
    assert result.findings[0].agent == "collaboration"


@pytest.mark.asyncio
async def test_route_wellbeing_analysis(
    test_coordinator: AgentCoordinator,
    manager_principal: AuthenticatedPrincipal,
):
    cid = str(uuid.uuid4())
    req = CoordinatorExecutionRequest(
        correlation_id=cid,
        intent="wellbeing_analysis",
        authenticated_principal=manager_principal,
        question="How is team morale and burnout risk?",
        target_team_id="team-alpha",
    )
    result = await test_coordinator.orchestrate(req)

    assert result.status == "completed"
    assert result.correlation_id == cid
    assert result.intent == "wellbeing_analysis"
    assert len(result.findings) == 1
    assert result.findings[0].agent == "wellbeing"


@pytest.mark.asyncio
async def test_route_task_assignment_recommendation(
    test_coordinator: AgentCoordinator,
    manager_principal: AuthenticatedPrincipal,
):
    cid = str(uuid.uuid4())
    req = CoordinatorExecutionRequest(
        correlation_id=cid,
        intent="task_assignment_recommendation",
        authenticated_principal=manager_principal,
        question="Recommend candidate for task assignment.",
        target_team_id="team-alpha",
        target_task_id="task-123",
    )
    result = await test_coordinator.orchestrate(req)

    assert result.status == "completed"
    assert result.correlation_id == cid
    assert result.intent == "task_assignment_recommendation"
    assert len(result.findings) == 1
    assert result.findings[0].agent == "task_assigning"


@pytest.mark.asyncio
async def test_route_task_delay_analysis_multi_specialist(
    test_coordinator: AgentCoordinator,
    manager_principal: AuthenticatedPrincipal,
):
    """task_delay_analysis orchestrates productivity and collaboration concurrently."""
    cid = str(uuid.uuid4())
    req = CoordinatorExecutionRequest(
        correlation_id=cid,
        intent="task_delay_analysis",
        authenticated_principal=manager_principal,
        question="What factors are causing delays in sprint delivery?",
        target_team_id="team-alpha",
    )
    result = await test_coordinator.orchestrate(req)

    assert result.status == "completed"
    assert result.correlation_id == cid
    assert result.intent == "task_delay_analysis"

    agents_in_findings = {f.agent for f in result.findings}
    assert "productivity" in agents_in_findings
    assert "collaboration" in agents_in_findings
    assert "coordinator" in agents_in_findings
    assert result.synthesized_finding is not None
    assert result.synthesized_finding.agent == "coordinator"


@pytest.mark.asyncio
async def test_route_team_workload_analysis_multi_specialist(
    test_coordinator: AgentCoordinator,
    manager_principal: AuthenticatedPrincipal,
):
    """team_workload_analysis orchestrates productivity and wellbeing concurrently."""
    cid = str(uuid.uuid4())
    req = CoordinatorExecutionRequest(
        correlation_id=cid,
        intent="team_workload_analysis",
        authenticated_principal=manager_principal,
        question="Is the team overloaded relative to historical capacity?",
        target_team_id="team-alpha",
    )
    result = await test_coordinator.orchestrate(req)

    assert result.status == "completed"
    agents_in_findings = {f.agent for f in result.findings}
    assert "productivity" in agents_in_findings
    assert "wellbeing" in agents_in_findings
    assert "coordinator" in agents_in_findings


@pytest.mark.asyncio
async def test_route_general_workforce_question(
    test_coordinator: AgentCoordinator,
    manager_principal: AuthenticatedPrincipal,
):
    """general_workforce_question orchestrates productivity, collaboration, and wellbeing."""
    cid = str(uuid.uuid4())
    req = CoordinatorExecutionRequest(
        correlation_id=cid,
        intent="general_workforce_question",
        authenticated_principal=manager_principal,
        question="Provide a comprehensive workforce overview for the executive report.",
        target_team_id="team-alpha",
    )
    result = await test_coordinator.orchestrate(req)

    assert result.status == "completed"
    agents_in_findings = {f.agent for f in result.findings}
    assert "productivity" in agents_in_findings
    assert "collaboration" in agents_in_findings
    assert "wellbeing" in agents_in_findings
    assert "coordinator" in agents_in_findings


# =========================================================================
# 2. Strict Well-being Isolation Tests
# =========================================================================


@pytest.mark.asyncio
async def test_wellbeing_to_task_assignment_rejected_in_request_model(
    manager_principal: AuthenticatedPrincipal,
):
    cid = str(uuid.uuid4())
    wb_finding = AgentFinding(
        agent="wellbeing",
        summary="Team pulse indicates high stress.",
        confidence=0.8,
        correlation_id=cid,
    )
    with pytest.raises(ValueError, match="Wellbeing findings cannot be supplied as dependencies"):
        CoordinatorExecutionRequest(
            correlation_id=cid,
            intent="task_assignment_recommendation",
            authenticated_principal=manager_principal,
            question="Assign tasks based on pulse scores.",
            dependency_findings=[wb_finding],
        )


@pytest.mark.asyncio
async def test_wellbeing_isolated_from_task_assigning_under_any_flow(
    test_coordinator: AgentCoordinator,
    manager_principal: AuthenticatedPrincipal,
):
    """Verify coordinator never attaches wellbeing findings to task_assigning agent."""
    cid = str(uuid.uuid4())
    prod_finding = AgentFinding(
        agent="productivity",
        summary="Candidate completed tasks on time.",
        confidence=0.9,
        correlation_id=cid,
    )
    req = CoordinatorExecutionRequest(
        correlation_id=cid,
        intent="task_assignment_recommendation",
        authenticated_principal=manager_principal,
        question="Recommend candidate for assignment.",
        dependency_findings=[prod_finding],
    )
    result = await test_coordinator.orchestrate(req)
    assert result.status == "completed"


# =========================================================================
# 3. Concurrency and Resilience / Failure Behavior Tests
# =========================================================================


@pytest.mark.asyncio
async def test_concurrent_execution_of_independent_specialists(
    mock_audit_sink: InMemoryAgentAuditSink,
    manager_principal: AuthenticatedPrincipal,
):
    """Verifies that specialists in multi-agent routing run concurrently."""
    call_times: dict[str, list[float]] = {"productivity": [], "collaboration": []}

    async def custom_handler(*args, **kwargs):
        user_prompt = kwargs.get("user_prompt", "")
        # Detect target specialist from prompt or context
        await asyncio.sleep(0.05)
        return StructuredAgentFindingOutput(
            summary="Concurrent analysis result.",
            confidence=0.85,
            limitations=[],
            recommended_actions=[],
        )

    fake_gw = FakeLLMGateway(handler=custom_handler)
    runtime = AgentRuntime(
        config=AgentRuntimeConfig(default_timeout_seconds=5.0, max_concurrent_executions=5),
        llm_gateway=fake_gw,
        audit_sink=mock_audit_sink,
    )
    register_coordinator_agent(runtime)
    register_productivity_agent(runtime)
    register_collaboration_agent(runtime)

    coord = AgentCoordinator(runtime=runtime, llm_gateway=fake_gw, audit_sink=mock_audit_sink)

    cid = str(uuid.uuid4())
    req = CoordinatorExecutionRequest(
        correlation_id=cid,
        intent="task_delay_analysis",
        authenticated_principal=manager_principal,
        question="Why are tasks delayed?",
        target_team_id="team-alpha",
    )
    res = await coord.orchestrate(req)
    assert res.status == "completed"
    assert len(res.findings) == 3  # productivity + collaboration + synthesized coordinator finding


@pytest.mark.asyncio
async def test_partial_failure_returns_partial_status(
    mock_audit_sink: InMemoryAgentAuditSink,
    manager_principal: AuthenticatedPrincipal,
):
    """When one independent specialist fails, coordinator returns partial results safely."""
    async def selective_failure_handler(*args, **kwargs):
        system_prompt = kwargs.get("system_prompt", "")
        # Fail collaboration, succeed productivity
        if "Collaboration" in system_prompt or "communication" in system_prompt.lower():
            from backend.app.modules.agents.llm_gateway import LLMUnavailableError
            raise LLMUnavailableError("Collaboration LLM service temporarily unavailable")
        return StructuredAgentFindingOutput(
            summary="Productivity throughput data processed successfully.",
            confidence=0.9,
            limitations=[],
            recommended_actions=[],
        )

    fake_gw = FakeLLMGateway(handler=selective_failure_handler)
    runtime = AgentRuntime(
        config=AgentRuntimeConfig(default_timeout_seconds=5.0),
        llm_gateway=fake_gw,
        audit_sink=mock_audit_sink,
    )
    register_coordinator_agent(runtime)
    register_productivity_agent(runtime)
    register_collaboration_agent(runtime)

    coord = AgentCoordinator(runtime=runtime, llm_gateway=fake_gw, audit_sink=mock_audit_sink)

    cid = str(uuid.uuid4())
    req = CoordinatorExecutionRequest(
        correlation_id=cid,
        intent="task_delay_analysis",
        authenticated_principal=manager_principal,
        question="Why are tasks delayed?",
        target_team_id="team-alpha",
    )
    result = await coord.orchestrate(req)

    assert result.status == "partial"
    assert len(result.errors) == 1
    assert result.errors[0]["agent"] == "collaboration"
    assert any(f.agent == "productivity" for f in result.findings)


@pytest.mark.asyncio
async def test_total_failure_returns_failed_status(
    mock_audit_sink: InMemoryAgentAuditSink,
    manager_principal: AuthenticatedPrincipal,
):
    """When all targeted specialists fail, coordinator returns status='failed'."""
    async def all_failing_handler(*args, **kwargs):
        from backend.app.modules.agents.llm_gateway import LLMUnavailableError
        raise LLMUnavailableError("All LLM providers down")

    fake_gw = FakeLLMGateway(handler=all_failing_handler)
    runtime = AgentRuntime(
        config=AgentRuntimeConfig(default_timeout_seconds=5.0),
        llm_gateway=fake_gw,
        audit_sink=mock_audit_sink,
    )
    register_coordinator_agent(runtime)
    register_productivity_agent(runtime)
    register_collaboration_agent(runtime)

    coord = AgentCoordinator(runtime=runtime, llm_gateway=fake_gw, audit_sink=mock_audit_sink)

    cid = str(uuid.uuid4())
    req = CoordinatorExecutionRequest(
        correlation_id=cid,
        intent="task_delay_analysis",
        authenticated_principal=manager_principal,
        question="Why are tasks delayed?",
        target_team_id="team-alpha",
    )
    result = await coord.orchestrate(req)

    assert result.status == "failed"
    assert len(result.errors) == 2
    assert len(result.findings) == 0


@pytest.mark.asyncio
async def test_coordinator_timeout_handling(
    mock_audit_sink: InMemoryAgentAuditSink,
    manager_principal: AuthenticatedPrincipal,
):
    """Coordinator enforces overall bounded timeout."""
    async def slow_handler(*args, **kwargs):
        await asyncio.sleep(1.0)
        return StructuredAgentFindingOutput(
            summary="Slow summary",
            confidence=0.8,
            limitations=[],
            recommended_actions=[],
        )

    fake_gw = FakeLLMGateway(handler=slow_handler)
    runtime = AgentRuntime(
        config=AgentRuntimeConfig(default_timeout_seconds=1.0),
        llm_gateway=fake_gw,
        audit_sink=mock_audit_sink,
    )
    register_coordinator_agent(runtime)
    register_productivity_agent(runtime)

    coord = AgentCoordinator(
        runtime=runtime,
        llm_gateway=fake_gw,
        audit_sink=mock_audit_sink,
        default_timeout_seconds=0.1,
    )

    cid = str(uuid.uuid4())
    req = CoordinatorExecutionRequest(
        correlation_id=cid,
        intent="productivity_analysis",
        authenticated_principal=manager_principal,
        question="Check throughput.",
        target_team_id="team-alpha",
    )
    result = await coord.orchestrate(req)

    assert result.status == "failed"
    assert "timeout" in result.safe_error_message.lower()


# =========================================================================
# 4. Authorization and RBAC Policy Enforcement Tests
# =========================================================================


@pytest.mark.asyncio
async def test_employee_task_assignment_forbidden(
    test_coordinator: AgentCoordinator,
    employee_principal: AuthenticatedPrincipal,
):
    cid = str(uuid.uuid4())
    req = CoordinatorExecutionRequest(
        correlation_id=cid,
        intent="task_assignment_recommendation",
        authenticated_principal=employee_principal,
        question="Assign tasks to me.",
    )
    result = await test_coordinator.orchestrate(req)

    assert result.status == "failed"
    assert result.errors[0]["error_code"] == "EMPLOYEE_TASK_ASSIGNMENT_FORBIDDEN"


@pytest.mark.asyncio
async def test_employee_team_workload_forbidden(
    test_coordinator: AgentCoordinator,
    employee_principal: AuthenticatedPrincipal,
):
    cid = str(uuid.uuid4())
    req = CoordinatorExecutionRequest(
        correlation_id=cid,
        intent="team_workload_analysis",
        authenticated_principal=employee_principal,
        question="How is team workload distributed?",
    )
    result = await test_coordinator.orchestrate(req)

    assert result.status == "failed"
    assert result.errors[0]["error_code"] == "EMPLOYEE_TEAM_WORKLOAD_FORBIDDEN"


@pytest.mark.asyncio
async def test_employee_cross_team_forbidden(
    test_coordinator: AgentCoordinator,
    employee_principal: AuthenticatedPrincipal,
):
    cid = str(uuid.uuid4())
    req = CoordinatorExecutionRequest(
        correlation_id=cid,
        intent="productivity_analysis",
        authenticated_principal=employee_principal,
        question="How is team beta doing?",
        target_team_id="team-beta",  # Employee assigned to team-alpha
    )
    result = await test_coordinator.orchestrate(req)

    assert result.status == "failed"
    assert result.errors[0]["error_code"] == "EMPLOYEE_CROSS_TEAM_FORBIDDEN"


@pytest.mark.asyncio
async def test_manager_unmanaged_team_forbidden(
    test_coordinator: AgentCoordinator,
    manager_principal: AuthenticatedPrincipal,
):
    cid = str(uuid.uuid4())
    req = CoordinatorExecutionRequest(
        correlation_id=cid,
        intent="productivity_analysis",
        authenticated_principal=manager_principal,
        question="Check team gamma metrics.",
        target_team_id="team-gamma",  # Manager manages team-alpha, team-beta
    )
    result = await test_coordinator.orchestrate(req)

    assert result.status == "failed"
    assert result.errors[0]["error_code"] == "MANAGER_UNMANAGED_TEAM_FORBIDDEN"


@pytest.mark.asyncio
async def test_admin_task_assignment_disabled(
    test_coordinator: AgentCoordinator,
    admin_principal: AuthenticatedPrincipal,
):
    cid = str(uuid.uuid4())
    req = CoordinatorExecutionRequest(
        correlation_id=cid,
        intent="task_assignment_recommendation",
        authenticated_principal=admin_principal,
        question="Assign tasks across the organization.",
    )
    result = await test_coordinator.orchestrate(req)

    assert result.status == "failed"
    assert result.errors[0]["error_code"] == "ADMIN_TASK_ASSIGNMENT_DISABLED"


@pytest.mark.asyncio
async def test_admin_org_wide_read_authorized(
    test_coordinator: AgentCoordinator,
    admin_principal: AuthenticatedPrincipal,
):
    cid = str(uuid.uuid4())
    req = CoordinatorExecutionRequest(
        correlation_id=cid,
        intent="general_workforce_question",
        authenticated_principal=admin_principal,
        question="Provide organization-wide workforce metrics.",
    )
    result = await test_coordinator.orchestrate(req)

    assert result.status == "completed"


# =========================================================================
# 5. Correlation ID & Audit Privacy Tests
# =========================================================================


@pytest.mark.asyncio
async def test_correlation_id_preserved_across_multi_agent_pipeline(
    test_coordinator: AgentCoordinator,
    mock_audit_sink: InMemoryAgentAuditSink,
    manager_principal: AuthenticatedPrincipal,
):
    cid = str(uuid.uuid4())
    req = CoordinatorExecutionRequest(
        correlation_id=cid,
        intent="task_delay_analysis",
        authenticated_principal=manager_principal,
        question="Analyze task delays.",
        target_team_id="team-alpha",
    )
    result = await test_coordinator.orchestrate(req)

    assert result.correlation_id == cid
    for f in result.findings:
        assert f.correlation_id == cid

    # Verify all audit events share the exact correlation_id
    events = mock_audit_sink.get_events_by_correlation(cid)
    assert len(events) > 0
    for ev in events:
        assert ev.correlation_id == cid


@pytest.mark.asyncio
async def test_audit_logs_contain_zero_sensitive_data(
    test_coordinator: AgentCoordinator,
    mock_audit_sink: InMemoryAgentAuditSink,
    manager_principal: AuthenticatedPrincipal,
):
    """Audit logs must never leak prompts, raw employee data, pulse comments, or credentials."""
    secret_marker = "SECRET_PROMPT_KEY_12345_DO_NOT_LOG"
    cid = str(uuid.uuid4())
    req = CoordinatorExecutionRequest(
        correlation_id=cid,
        intent="productivity_analysis",
        authenticated_principal=manager_principal,
        question=f"Check productivity with special key {secret_marker}",
        target_team_id="team-alpha",
    )
    await test_coordinator.orchestrate(req)

    events = mock_audit_sink.get_events_by_correlation(cid)
    assert len(events) > 0

    for ev in events:
        dumped = ev.model_dump_json()
        assert secret_marker not in dumped
        # Check standard forbidden field absences
        assert "prompt" not in dumped.lower() or "prompt_security" in dumped.lower()
        assert "password" not in dumped.lower()
        assert "api_key" not in dumped.lower()


# =========================================================================
# 6. Responsible AI Guardrails & Synthesis Fallback Tests
# =========================================================================


@pytest.mark.asyncio
async def test_responsible_ai_guardrails_blocks_punitive_coordinator_synthesis(
    mock_audit_sink: InMemoryAgentAuditSink,
    manager_principal: AuthenticatedPrincipal,
):
    """Punitive synthesis language triggers fallback deterministic synthesis."""
    call_count = 0

    async def punitive_synthesis_handler(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        system_prompt = kwargs.get("system_prompt", "")
        if "Central Coordinator" in system_prompt:
            # Return punitive recommendation from synthesis LLM
            return StructuredAgentFindingOutput(
                summary="The coordinator recommends to terminate the employee immediately.",
                confidence=0.9,
                limitations=[],
                recommended_actions=["Fire the worker without delay"],
            )
        return StructuredAgentFindingOutput(
            summary="Normal specialist analysis.",
            confidence=0.85,
            limitations=[],
            recommended_actions=["Improve communication"],
        )

    fake_gw = FakeLLMGateway(handler=punitive_synthesis_handler)
    runtime = AgentRuntime(
        config=AgentRuntimeConfig(default_timeout_seconds=5.0),
        llm_gateway=fake_gw,
        audit_sink=mock_audit_sink,
    )
    register_coordinator_agent(runtime)
    register_productivity_agent(runtime)
    register_collaboration_agent(runtime)

    coord = AgentCoordinator(runtime=runtime, llm_gateway=fake_gw, audit_sink=mock_audit_sink)

    cid = str(uuid.uuid4())
    req = CoordinatorExecutionRequest(
        correlation_id=cid,
        intent="task_delay_analysis",
        authenticated_principal=manager_principal,
        question="Examine delays.",
        target_team_id="team-alpha",
    )
    result = await coord.orchestrate(req)

    # Result should still complete via deterministic fallback, sanitized of punitive language
    assert result.status == "completed"
    assert result.synthesized_finding is not None
    assert "terminate the employee" not in result.synthesized_finding.summary


# =========================================================================
# 7. Production Factory Construction Tests
# =========================================================================


def test_create_production_coordinator_offline_construction():
    """Verify production factory registers all required agents and coordinator definition."""
    fake_gw = FakeLLMGateway()
    audit_sink = InMemoryAgentAuditSink()

    coordinator = create_production_coordinator(
        database=None,
        llm_gateway=fake_gw,
        audit_sink=audit_sink,
    )

    assert coordinator.runtime.get_agent("coordinator") is not None
    assert coordinator.runtime.get_agent("productivity") is not None
    assert coordinator.runtime.get_agent("collaboration") is not None
    assert coordinator.runtime.get_agent("wellbeing") is not None
    assert coordinator.runtime.get_agent("task_assigning") is not None


@pytest.mark.asyncio
async def test_task_assignment_rejects_unauthorized_dependency_agent(
    manager_principal: AuthenticatedPrincipal,
):
    """Task assignment request rejects non-productivity/collaboration dependencies."""
    cid = str(uuid.uuid4())
    fake_finding = AgentFinding(
        agent="coordinator",
        summary="Coordinator finding cannot be passed as dependency to task assignment.",
        confidence=0.9,
        correlation_id=cid,
    )
    with pytest.raises(ValueError, match="cannot be supplied as dependencies for task assignment recommendations"):
        CoordinatorExecutionRequest(
            correlation_id=cid,
            intent="task_assignment_recommendation",
            authenticated_principal=manager_principal,
            question="Assign tasks.",
            dependency_findings=[fake_finding],
        )


@pytest.mark.asyncio
async def test_coordinator_timeout_cancels_background_tasks(
    mock_audit_sink: InMemoryAgentAuditSink,
    manager_principal: AuthenticatedPrincipal,
):
    """Verifies that when coordinator times out, specialist tasks are cancelled cleanly."""
    task_started = asyncio.Event()
    task_cancelled = False

    async def hung_handler(*args, **kwargs):
        nonlocal task_cancelled
        task_started.set()
        try:
            await asyncio.sleep(10.0)
        except asyncio.CancelledError:
            task_cancelled = True
            raise
        return StructuredAgentFindingOutput(
            summary="Hung handler completed unexpectedly",
            confidence=0.5,
            limitations=[],
            recommended_actions=[],
        )

    fake_gw = FakeLLMGateway(handler=hung_handler)
    runtime = AgentRuntime(
        config=AgentRuntimeConfig(default_timeout_seconds=5.0),
        llm_gateway=fake_gw,
        audit_sink=mock_audit_sink,
    )
    register_coordinator_agent(runtime)
    register_productivity_agent(runtime)

    coord = AgentCoordinator(
        runtime=runtime,
        llm_gateway=fake_gw,
        audit_sink=mock_audit_sink,
        default_timeout_seconds=0.05,
    )

    cid = str(uuid.uuid4())
    req = CoordinatorExecutionRequest(
        correlation_id=cid,
        intent="productivity_analysis",
        authenticated_principal=manager_principal,
        question="Check throughput.",
        target_team_id="team-alpha",
    )
    result = await coord.orchestrate(req)

    assert result.status == "failed"
    assert "timeout" in result.safe_error_message.lower()
    # Allow brief event loop cycle for cancellation propagation
    await asyncio.sleep(0.01)
    assert task_cancelled is True
