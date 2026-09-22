import asyncio
from datetime import datetime, timezone
import pytest
from pydantic import BaseModel, ValidationError

from backend.app.modules.agents.audit import (
    AgentAuditEvent,
    InMemoryAgentAuditSink,
)
from backend.app.modules.agents.llm_gateway import (
    FakeLLMGateway,
    LLMAuthenticationError,
    LLMError,
    LLMResponseValidationError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from backend.app.modules.agents.protocol import (
    AgentFinding,
    AgentRequest,
    AgentResponse,
    EvidenceReference,
    create_agent_request,
)
from backend.app.modules.agents.runtime import (
    AgentAuthorizationError,
    AgentCapabilityError,
    AgentConfigError,
    AgentDefinition,
    AgentOutputValidationError,
    AgentProviderError,
    AgentRegistrationError,
    AgentRuntime,
    AgentRuntimeConfig,
    AgentRuntimeError,
    AgentTimeoutError,
    AgentTool,
    AgentToolExecutionError,
    BaseAgentTool,
    ExecutionContext,
    FakeAgentRuntime,
    StructuredAgentFindingOutput,
    UnknownAgentError,
    UnknownToolError,
)
from backend.app.modules.agents.security_policy import (
    AuthenticatedPrincipal,
)


# =========================================================================
# Test Helpers and Fixtures
# =========================================================================


def make_manager_principal(
    user_id: str = "mgr-1",
    assigned_team: str = "team-eng",
    managed_teams: list[str] | None = None,
) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=user_id,
        role="manager",
        assigned_team_id=assigned_team,
        managed_team_ids=managed_teams or ["team-eng"],
    )


def make_employee_principal(
    user_id: str = "emp-1",
    assigned_team: str = "team-eng",
) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=user_id,
        role="employee",
        assigned_team_id=assigned_team,
    )


def make_admin_principal(user_id: str = "admin-1") -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=user_id,
        role="admin",
    )


def make_productivity_agent_def() -> AgentDefinition:
    return AgentDefinition(
        name="productivity",
        role="Productivity Analyst",
        goal="Analyze task velocity and sprint delivery milestones",
        allowed_intents={"productivity_analysis", "task_delay_analysis"},
        allowed_evidence_sources={"task", "agent_finding"},
        system_prompt="Analyze productivity metrics and sprint performance.",
        response_model=StructuredAgentFindingOutput,
    )


def make_task_assigning_agent_def() -> AgentDefinition:
    return AgentDefinition(
        name="task_assigning",
        role="Task Assignment Advisor",
        goal="Recommend optimal task distribution based on capacity",
        allowed_intents={"task_assignment_recommendation"},
        allowed_evidence_sources={"task", "employee_profile", "agent_finding"},
        system_prompt="Recommend task distribution advisory only.",
        response_model=StructuredAgentFindingOutput,
    )


def make_wellbeing_agent_def() -> AgentDefinition:
    return AgentDefinition(
        name="wellbeing",
        role="Wellbeing Analyst",
        goal="Analyze aggregate team pulse summaries",
        allowed_intents={"wellbeing_analysis"},
        allowed_evidence_sources={"pulse_summary", "agent_finding"},
        system_prompt="Analyze team wellbeing summaries.",
        response_model=StructuredAgentFindingOutput,
    )


# =========================================================================
# 1. Configuration & Registration Tests
# =========================================================================


def test_runtime_config_strict_and_immutable():
    cfg = AgentRuntimeConfig(
        default_timeout_seconds=45.0,
        max_evidence_items=15,
        max_concurrent_executions=4,
    )
    assert cfg.default_timeout_seconds == 45.0
    assert cfg.max_evidence_items == 15
    assert cfg.max_concurrent_executions == 4

    # Frozen: mutations forbidden
    with pytest.raises(ValidationError):
        cfg.default_timeout_seconds = 60.0

    # Forbid extra unknown fields
    with pytest.raises(ValidationError):
        AgentRuntimeConfig(unknown_field="injected")


def test_runtime_config_bounds_validation():
    with pytest.raises(ValidationError):
        AgentRuntimeConfig(default_timeout_seconds=0.5)

    with pytest.raises(ValidationError):
        AgentRuntimeConfig(default_timeout_seconds=500.0)

    with pytest.raises(ValidationError):
        AgentRuntimeConfig(max_evidence_items=0)

    with pytest.raises(ValidationError):
        AgentRuntimeConfig(max_concurrent_executions=0)


def test_agent_definition_registration_success():
    runtime = AgentRuntime()
    agent_def = make_productivity_agent_def()
    runtime.register_agent(agent_def)

    retrieved = runtime.get_agent("productivity")
    assert retrieved.name == "productivity"
    assert retrieved.role == "Productivity Analyst"


def test_duplicate_agent_registration_rejected():
    runtime = AgentRuntime()
    agent_def = make_productivity_agent_def()
    runtime.register_agent(agent_def)

    with pytest.raises(AgentRegistrationError) as exc_info:
        runtime.register_agent(agent_def)
    assert exc_info.value.safe_reason_code == "DUPLICATE_AGENT_REGISTRATION"


def test_unknown_agent_retrieval_rejected():
    runtime = AgentRuntime()
    with pytest.raises(UnknownAgentError):
        runtime.get_agent("collaboration")


def test_agent_definition_rejects_disallowed_policy_capabilities():
    with pytest.raises(ValueError, match="declared intents"):
        AgentDefinition(
            name="productivity",
            role="Productivity Analyst",
            goal="Analyze task velocity",
            allowed_intents={"task_assignment_recommendation"},  # Not allowed for productivity
            system_prompt="Analyze metrics.",
            response_model=StructuredAgentFindingOutput,
        )

    with pytest.raises(ValueError, match="declared evidence sources"):
        AgentDefinition(
            name="task_assigning",
            role="Task Advisor",
            goal="Assign tasks",
            allowed_evidence_sources={"pulse_summary"},  # Forbidden for task assigning
            system_prompt="Assign tasks.",
            response_model=StructuredAgentFindingOutput,
        )


# =========================================================================
# 2. Tool Registration & Capability Authorization Tests
# =========================================================================


def test_tool_registration_success():
    runtime = AgentRuntime()

    async def mock_handler(ctx: ExecutionContext):
        return [
            EvidenceReference(
                source_type="task",
                record_id="t-101",
                title="Sprint Task",
                team_id="team-eng",
            )
        ]

    tool = BaseAgentTool(
        name="task_metrics_collector",
        target_agent="productivity",
        required_intent="productivity_analysis",
        source_type="task",
        handler=mock_handler,
    )
    runtime.register_tool(tool)

    retrieved = runtime.get_tool("task_metrics_collector")
    assert retrieved.name == "task_metrics_collector"
    assert retrieved.target_agent == "productivity"


def test_duplicate_and_unknown_tool_rejected():
    runtime = AgentRuntime()

    tool = BaseAgentTool(
        name="task_tool",
        target_agent="productivity",
        required_intent="productivity_analysis",
        source_type="task",
        handler=lambda ctx: [],
    )
    runtime.register_tool(tool)

    with pytest.raises(AgentRegistrationError) as exc_info:
        runtime.register_tool(tool)
    assert exc_info.value.safe_reason_code == "DUPLICATE_TOOL_REGISTRATION"

    with pytest.raises(UnknownToolError):
        runtime.get_tool("nonexistent_tool")


# =========================================================================
# 3. Execution & Security Policy Enforcement Tests
# =========================================================================


@pytest.mark.asyncio
async def test_normal_execution_calls_llm_gateway_once():
    audit_sink = InMemoryAgentAuditSink()
    fake_gw = FakeLLMGateway(
        default_response=StructuredAgentFindingOutput(
            summary="Sprint velocity is on track at 45 points.",
            confidence=0.92,
            limitations=["Based on 2 completed sprints"],
            recommended_actions=["Maintain current sprint velocity"],
        )
    )
    runtime = AgentRuntime(llm_gateway=fake_gw, audit_sink=audit_sink)
    runtime.register_agent(make_productivity_agent_def())

    req = create_agent_request(
        correlation_id="11111111-1111-4111-8111-111111111111",
        sender="coordinator",
        recipient="productivity",
        intent="productivity_analysis",
        authenticated_user_id="mgr-1",
        question="What is the team velocity?",
    )
    principal = make_manager_principal()

    resp = await runtime.execute_agent(req, principal)

    assert resp.status == "completed"
    assert resp.finding is not None
    assert resp.finding.summary == "Sprint velocity is on track at 45 points."
    assert resp.finding.confidence == 0.92
    assert fake_gw.call_count == 1

    # Verify audit events
    events = audit_sink.get_events_by_correlation("11111111-1111-4111-8111-111111111111")
    event_types = [e.event_type for e in events]
    assert "agent_request_dispatched" in event_types
    assert "llm_request_started" in event_types
    assert "llm_request_completed" in event_types


@pytest.mark.asyncio
async def test_execution_with_authorized_tool():
    audit_sink = InMemoryAgentAuditSink()
    fake_gw = FakeLLMGateway(
        default_response=StructuredAgentFindingOutput(
            summary="All tasks analyzed.",
            confidence=0.9,
            limitations=[],
            recommended_actions=[],
        )
    )
    runtime = AgentRuntime(llm_gateway=fake_gw, audit_sink=audit_sink)
    runtime.register_agent(make_productivity_agent_def())

    tool_called = False

    async def fetch_tasks(ctx: ExecutionContext):
        nonlocal tool_called
        tool_called = True
        return [
            EvidenceReference(
                source_type="task",
                record_id="t-1",
                title="Implement auth",
                snippet="Auth module delivery",
                team_id="team-eng",
            )
        ]

    runtime.register_tool(
        BaseAgentTool(
            name="fetch_eng_tasks",
            target_agent="productivity",
            required_intent="productivity_analysis",
            source_type="task",
            handler=fetch_tasks,
        )
    )

    req = create_agent_request(
        correlation_id="22222222-2222-4222-8222-222222222222",
        sender="coordinator",
        recipient="productivity",
        intent="productivity_analysis",
        authenticated_user_id="mgr-1",
        question="Check sprint tasks",
    )
    principal = make_manager_principal(managed_teams=["team-eng"])

    resp = await runtime.execute_agent(req, principal, tool_names=["fetch_eng_tasks"])
    assert resp.status == "completed"
    assert tool_called is True
    assert len(resp.finding.evidence_refs) == 1
    assert resp.finding.evidence_refs[0].record_id == "t-1"


@pytest.mark.asyncio
async def test_capability_enforcement_prevents_tool_execution():
    runtime = AgentRuntime()
    runtime.register_agent(make_productivity_agent_def())

    tool_called = False

    async def malicious_tool(ctx: ExecutionContext):
        nonlocal tool_called
        tool_called = True
        return []

    runtime.register_tool(
        BaseAgentTool(
            name="mismatched_tool",
            target_agent="task_assigning",  # Does not match recipient 'productivity'
            required_intent="task_assignment_recommendation",
            source_type="task",
            handler=malicious_tool,
        )
    )

    req = create_agent_request(
        correlation_id="33333333-3333-4333-8333-333333333333",
        sender="coordinator",
        recipient="productivity",
        intent="productivity_analysis",
        authenticated_user_id="mgr-1",
        question="Check productivity",
    )
    principal = make_manager_principal()

    resp = await runtime.execute_agent(req, principal, tool_names=["mismatched_tool"])
    assert resp.status == "failed"
    assert resp.error_code == "TOOL_TARGET_AGENT_MISMATCH"
    assert tool_called is False  # Tool was NEVER executed


@pytest.mark.asyncio
async def test_tool_evidence_unmanaged_team_rejected():
    runtime = AgentRuntime()
    runtime.register_agent(make_productivity_agent_def())

    async def cross_team_tool(ctx: ExecutionContext):
        return [
            EvidenceReference(
                source_type="task",
                record_id="t-unmanaged",
                title="Cross Team Task",
                team_id="team-sales",  # Manager manages team-eng, not team-sales
            )
        ]

    runtime.register_tool(
        BaseAgentTool(
            name="cross_team_tool",
            target_agent="productivity",
            required_intent="productivity_analysis",
            source_type="task",
            handler=cross_team_tool,
        )
    )

    req = create_agent_request(
        correlation_id="44444444-4444-4444-8444-444444444444",
        sender="coordinator",
        recipient="productivity",
        intent="productivity_analysis",
        authenticated_user_id="mgr-1",
        question="Analyze team tasks",
    )
    principal = make_manager_principal(managed_teams=["team-eng"])

    resp = await runtime.execute_agent(req, principal, tool_names=["cross_team_tool"])
    assert resp.status == "failed"
    assert resp.error_code == "UNMANAGED_TEAM_EVIDENCE_FORBIDDEN"


# =========================================================================
# 4. Dependency Provenance & Responsible AI Guardrail Tests
# =========================================================================


@pytest.mark.asyncio
async def test_dependency_correlation_provenance_enforced():
    runtime = AgentRuntime()
    runtime.register_agent(make_task_assigning_agent_def())

    upstream_finding = AgentFinding(
        agent="productivity",
        summary="Velocity is high",
        correlation_id="99999999-9999-4999-8999-999999999999",  # Mismatched correlation_id
        confidence=0.9,
    )

    req = create_agent_request(
        correlation_id="55555555-5555-4555-8555-555555555555",
        sender="productivity",
        recipient="task_assigning",
        intent="task_assignment_recommendation",
        authenticated_user_id="mgr-1",
        question="Recommend assignee",
        message_type="dependency_request",
    )
    # Bypass model_validator to simulate forged/modified request
    object.__setattr__(req, "dependency_findings", [upstream_finding])

    principal = make_manager_principal()
    resp = await runtime.execute_agent(req, principal)
    assert resp.status == "failed"
    assert resp.error_code == "DEPENDENCY_CORRELATION_MISMATCH"


@pytest.mark.asyncio
async def test_wellbeing_findings_strictly_rejected_for_task_assignment():
    runtime = AgentRuntime()
    runtime.register_agent(make_task_assigning_agent_def())

    wellbeing_finding = AgentFinding(
        agent="wellbeing",
        summary="Team is reporting elevated stress",
        correlation_id="66666666-6666-4666-8666-666666666666",
        confidence=0.85,
    )

    req = create_agent_request(
        correlation_id="66666666-6666-4666-8666-666666666666",
        sender="coordinator",
        recipient="task_assigning",
        intent="task_assignment_recommendation",
        authenticated_user_id="mgr-1",
        question="Recommend assignee based on stress levels",
    )
    object.__setattr__(req, "dependency_findings", [wellbeing_finding])

    principal = make_manager_principal()
    resp = await runtime.execute_agent(req, principal)
    assert resp.status == "failed"
    assert resp.error_code == "WELLBEING_TASK_ASSIGNMENT_FORBIDDEN"


@pytest.mark.asyncio
async def test_employee_role_cannot_request_task_assignment():
    runtime = AgentRuntime()
    runtime.register_agent(make_task_assigning_agent_def())

    req = create_agent_request(
        correlation_id="77777777-7777-4777-8777-777777777777",
        sender="coordinator",
        recipient="task_assigning",
        intent="task_assignment_recommendation",
        authenticated_user_id="emp-1",
        question="Assign task to me",
    )
    principal = make_employee_principal()

    resp = await runtime.execute_agent(req, principal)
    assert resp.status == "failed"
    assert resp.error_code == "EMPLOYEE_TASK_ASSIGNMENT_FORBIDDEN"


# =========================================================================
# 5. LLM Failure, Timeout, and Validation Tests
# =========================================================================


@pytest.mark.asyncio
async def test_timeout_cancels_execution_and_reports_sanitized_error():
    audit_sink = InMemoryAgentAuditSink()

    async def slow_handler(**kwargs):
        await asyncio.sleep(5.0)
        return StructuredAgentFindingOutput(
            summary="Late response", confidence=1.0
        )

    fake_gw = FakeLLMGateway(handler=slow_handler)
    runtime = AgentRuntime(
        config=AgentRuntimeConfig(default_timeout_seconds=1.0),
        llm_gateway=fake_gw,
        audit_sink=audit_sink,
    )
    runtime.register_agent(
        AgentDefinition(
            name="productivity",
            role="Productivity Analyst",
            goal="Analyze velocity",
            allowed_intents={"productivity_analysis"},
            system_prompt="Analyze.",
            response_model=StructuredAgentFindingOutput,
            timeout_seconds=1.0,
        )
    )

    req = create_agent_request(
        correlation_id="88888888-8888-4888-8888-888888888888",
        sender="coordinator",
        recipient="productivity",
        intent="productivity_analysis",
        authenticated_user_id="mgr-1",
        question="Check velocity",
    )
    principal = make_manager_principal()

    resp = await runtime.execute_agent(req, principal)
    assert resp.status == "failed"
    assert resp.error_code == "EXECUTION_TIMEOUT"
    assert "timeout" in resp.safe_error_message.lower()

    # Check audit failure event
    failed_events = audit_sink.get_events_by_type("llm_request_failed")
    assert len(failed_events) == 1
    assert failed_events[0].safe_reason_code == "EXECUTION_TIMEOUT"


@pytest.mark.asyncio
async def test_provider_failure_maps_to_sanitized_error():
    async def failing_handler(**kwargs):
        raise LLMUnavailableError("Upstream LLM cluster 503 Overloaded")

    fake_gw = FakeLLMGateway(handler=failing_handler)
    runtime = AgentRuntime(llm_gateway=fake_gw)
    runtime.register_agent(make_productivity_agent_def())

    req = create_agent_request(
        correlation_id="99999999-9999-4999-8999-999999999999",
        sender="coordinator",
        recipient="productivity",
        intent="productivity_analysis",
        authenticated_user_id="mgr-1",
        question="Check velocity",
    )
    principal = make_manager_principal()

    resp = await runtime.execute_agent(req, principal)
    assert resp.status == "failed"
    assert resp.error_code == "LLM_PROVIDER_ERROR"
    # Never leak internal error message
    assert "503 Overloaded" not in resp.safe_error_message


@pytest.mark.asyncio
async def test_schema_mismatch_maps_to_validation_error():
    async def invalid_schema_handler(**kwargs):
        raise LLMResponseValidationError("Missing required field 'confidence'")

    fake_gw = FakeLLMGateway(handler=invalid_schema_handler)
    runtime = AgentRuntime(llm_gateway=fake_gw)
    runtime.register_agent(make_productivity_agent_def())

    req = create_agent_request(
        correlation_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        sender="coordinator",
        recipient="productivity",
        intent="productivity_analysis",
        authenticated_user_id="mgr-1",
        question="Check velocity",
    )
    principal = make_manager_principal()

    resp = await runtime.execute_agent(req, principal)
    assert resp.status == "failed"
    assert resp.error_code == "OUTPUT_VALIDATION_ERROR"


# =========================================================================
# 6. Audit Privacy & Secret Sanitization Tests
# =========================================================================


@pytest.mark.asyncio
async def test_audit_records_exclude_prompts_evidence_and_secrets():
    audit_sink = InMemoryAgentAuditSink()
    fake_gw = FakeLLMGateway(
        default_response=StructuredAgentFindingOutput(
            summary="Velocity is normal", confidence=0.9
        )
    )
    runtime = AgentRuntime(llm_gateway=fake_gw, audit_sink=audit_sink)
    runtime.register_agent(make_productivity_agent_def())

    question_secret = "Confidential Question with SECRET_KEY_12345"
    req = create_agent_request(
        correlation_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        sender="coordinator",
        recipient="productivity",
        intent="productivity_analysis",
        authenticated_user_id="mgr-1",
        question=question_secret,
    )
    principal = make_manager_principal()

    await runtime.execute_agent(req, principal)

    events = audit_sink.get_all_events()
    assert len(events) >= 2
    for event in events:
        event_str = str(event.model_dump())
        assert "SECRET_KEY_12345" not in event_str
        assert "Confidential Question" not in event_str
        # Verify strict fields
        assert event.actor_user_id == "mgr-1"
        assert event.actor_role == "manager"
        assert event.agent == "productivity"


# =========================================================================
# 7. Multi-Agent execute_many Concurrency Tests
# =========================================================================


@pytest.mark.asyncio
async def test_execute_many_preserves_order_and_respects_concurrency():
    call_order = []

    async def slow_agent_handler(**kwargs):
        user_prompt = kwargs.get("user_prompt", "")
        if "fast" in user_prompt:
            await asyncio.sleep(0.01)
            call_order.append("fast")
            return StructuredAgentFindingOutput(summary="Fast output", confidence=0.9)
        else:
            await asyncio.sleep(0.05)
            call_order.append("slow")
            return StructuredAgentFindingOutput(summary="Slow output", confidence=0.8)

    fake_gw = FakeLLMGateway(handler=slow_agent_handler)
    runtime = AgentRuntime(
        config=AgentRuntimeConfig(max_concurrent_executions=3),
        llm_gateway=fake_gw,
    )
    runtime.register_agent(make_productivity_agent_def())
    runtime.register_agent(make_wellbeing_agent_def())

    principal = make_manager_principal()

    req_slow = create_agent_request(
        correlation_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        sender="coordinator",
        recipient="productivity",
        intent="productivity_analysis",
        authenticated_user_id="mgr-1",
        question="Analyze slow sprint",
    )
    req_fast = create_agent_request(
        correlation_id="dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        sender="coordinator",
        recipient="wellbeing",
        intent="wellbeing_analysis",
        authenticated_user_id="mgr-1",
        question="Analyze fast pulse",
    )

    # Submit [slow, fast]
    results = await runtime.execute_many(
        [(req_slow, principal), (req_fast, principal)]
    )

    # Order must be strictly preserved: [slow result, fast result]
    assert len(results) == 2
    assert results[0].sender == "productivity"
    assert results[0].finding.summary == "Slow output"
    assert results[1].sender == "wellbeing"
    assert results[1].finding.summary == "Fast output"


@pytest.mark.asyncio
async def test_execute_many_isolates_failures_without_fail_fast():
    fake_gw = FakeLLMGateway(
        default_response=StructuredAgentFindingOutput(
            summary="Success summary", confidence=0.9
        )
    )
    runtime = AgentRuntime(llm_gateway=fake_gw)
    runtime.register_agent(make_productivity_agent_def())
    # Note: 'task_assigning' is intentionally NOT registered to trigger an isolated failure

    principal = make_manager_principal()

    req_valid = create_agent_request(
        correlation_id="eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        sender="coordinator",
        recipient="productivity",
        intent="productivity_analysis",
        authenticated_user_id="mgr-1",
        question="Valid request",
    )
    req_invalid = create_agent_request(
        correlation_id="ffffffff-ffff-4fff-8fff-ffffffffffff",
        sender="coordinator",
        recipient="task_assigning",
        intent="task_assignment_recommendation",
        authenticated_user_id="mgr-1",
        question="Unregistered agent request",
    )

    results = await runtime.execute_many(
        [(req_valid, principal), (req_invalid, principal)],
        fail_fast=False,
    )

    assert len(results) == 2
    assert results[0].status == "completed"
    assert results[1].status == "failed"
    assert results[1].error_code == "UNKNOWN_AGENT"


@pytest.mark.asyncio
async def test_execute_many_fail_fast_raises_runtime_error():
    fake_gw = FakeLLMGateway(
        default_response=StructuredAgentFindingOutput(
            summary="Success summary", confidence=0.9
        )
    )
    runtime = AgentRuntime(llm_gateway=fake_gw)
    runtime.register_agent(make_productivity_agent_def())

    principal = make_manager_principal()

    req_invalid = create_agent_request(
        correlation_id="10101010-1010-4010-8010-101010101010",
        sender="coordinator",
        recipient="task_assigning",  # Not registered
        intent="task_assignment_recommendation",
        authenticated_user_id="mgr-1",
        question="Invalid agent request",
    )

    with pytest.raises(AgentRuntimeError) as exc_info:
        await runtime.execute_many([(req_invalid, principal)], fail_fast=True)
    assert exc_info.value.safe_reason_code == "UNKNOWN_AGENT"


# =========================================================================
# 8. FakeAgentRuntime Test Double Tests
# =========================================================================


@pytest.mark.asyncio
async def test_fake_agent_runtime_deterministic_success():
    expected_finding = AgentFinding(
        agent="productivity",
        summary="Deterministic test summary",
        correlation_id="12121212-1212-4212-8212-121212121212",
        confidence=0.99,
        limitations=["Unit test mock"],
        recommended_actions=["Approve PR"],
    )
    fake_runtime = FakeAgentRuntime(default_finding=expected_finding)
    fake_runtime.register_agent(make_productivity_agent_def())

    req = create_agent_request(
        correlation_id="12121212-1212-4212-8212-121212121212",
        sender="coordinator",
        recipient="productivity",
        intent="productivity_analysis",
        authenticated_user_id="mgr-1",
        question="Run test",
    )
    principal = make_manager_principal()

    resp = await fake_runtime.execute_agent(req, principal)
    assert resp.status == "completed"
    assert resp.finding.summary == "Deterministic test summary"
    assert resp.finding.confidence == 0.99

    assert fake_runtime.in_memory_audit_sink is not None
    events = fake_runtime.in_memory_audit_sink.get_all_events()
    assert len(events) >= 2


@pytest.mark.asyncio
async def test_fake_agent_runtime_simulates_provider_failure():
    async def fail_handler(**kwargs):
        raise LLMAuthenticationError("Simulated 401 Unauthorized")

    fake_runtime = FakeAgentRuntime(handler=fail_handler)
    fake_runtime.register_agent(make_productivity_agent_def())

    req = create_agent_request(
        correlation_id="13131313-1313-4313-8313-131313131313",
        sender="coordinator",
        recipient="productivity",
        intent="productivity_analysis",
        authenticated_user_id="mgr-1",
        question="Run test",
    )
    principal = make_manager_principal()

    resp = await fake_runtime.execute_agent(req, principal)
    assert resp.status == "failed"
    assert resp.error_code == "LLM_PROVIDER_ERROR"


@pytest.mark.asyncio
async def test_fake_agent_runtime_simulates_timeout_and_invalid_output():
    # 1. Timeout simulation
    async def timeout_handler(**kwargs):
        raise LLMTimeoutError("Simulated Timeout")

    fake_runtime_timeout = FakeAgentRuntime(handler=timeout_handler)
    fake_runtime_timeout.register_agent(make_productivity_agent_def())

    req_timeout = create_agent_request(
        correlation_id="14141414-1414-4414-8414-141414141414",
        sender="coordinator",
        recipient="productivity",
        intent="productivity_analysis",
        authenticated_user_id="mgr-1",
        question="Timeout test",
    )
    principal = make_manager_principal()
    resp_timeout = await fake_runtime_timeout.execute_agent(req_timeout, principal)
    assert resp_timeout.status == "failed"
    assert resp_timeout.error_code == "LLM_PROVIDER_ERROR"

    # 2. Schema mismatch simulation
    async def schema_err_handler(**kwargs):
        raise LLMResponseValidationError("Missing required field")

    fake_runtime_schema = FakeAgentRuntime(handler=schema_err_handler)
    fake_runtime_schema.register_agent(make_productivity_agent_def())

    req_schema = create_agent_request(
        correlation_id="15151515-1515-4515-8515-151515151515",
        sender="coordinator",
        recipient="productivity",
        intent="productivity_analysis",
        authenticated_user_id="mgr-1",
        question="Schema test",
    )
    resp_schema = await fake_runtime_schema.execute_agent(req_schema, principal)
    assert resp_schema.status == "failed"
    assert resp_schema.error_code == "OUTPUT_VALIDATION_ERROR"


# =========================================================================
# 9. Additional Regression Tests for Pre-Commit Correctness & Security
# =========================================================================


@pytest.mark.asyncio
async def test_hanging_tool_times_out_and_emits_failure_audit():
    """Confirms whole-execution timeout bounds tool execution and cancels hanging tools."""
    audit_sink = InMemoryAgentAuditSink()

    async def hanging_tool_handler(ctx: ExecutionContext):
        await asyncio.sleep(10.0)
        return []

    tool = BaseAgentTool(
        name="slow_tool",
        target_agent="productivity",
        required_intent="productivity_analysis",
        source_type="task",
        handler=hanging_tool_handler,
    )

    fake_gw = FakeLLMGateway(
        default_response=StructuredAgentFindingOutput(
            summary="Should not be reached", confidence=1.0
        )
    )
    runtime = AgentRuntime(
        config=AgentRuntimeConfig(default_timeout_seconds=1.0),
        llm_gateway=fake_gw,
        audit_sink=audit_sink,
    )
    runtime.register_agent(
        AgentDefinition(
            name="productivity",
            role="Productivity Analyst",
            goal="Analyze velocity",
            allowed_intents={"productivity_analysis"},
            allowed_evidence_sources={"task"},
            system_prompt="Analyze.",
            response_model=StructuredAgentFindingOutput,
            timeout_seconds=1.0,
        )
    )
    runtime.register_tool(tool)

    req = create_agent_request(
        correlation_id="16161616-1616-4616-8616-161616161616",
        sender="coordinator",
        recipient="productivity",
        intent="productivity_analysis",
        authenticated_user_id="mgr-1",
        question="Analyze tasks with slow tool",
    )
    principal = make_manager_principal()

    resp = await runtime.execute_agent(req, principal, tool_names=["slow_tool"])
    assert resp.status == "failed"
    assert resp.error_code == "EXECUTION_TIMEOUT"
    assert fake_gw.call_count == 0  # Tool timed out before LLM gateway was ever reached

    # Verify audit failure recorded and NO false success recorded
    failed_events = audit_sink.get_events_by_type("llm_request_failed")
    assert len(failed_events) == 1
    assert failed_events[0].safe_reason_code == "EXECUTION_TIMEOUT"
    assert len(audit_sink.get_events_by_type("llm_request_completed")) == 0


@pytest.mark.asyncio
async def test_oversized_output_rejected_with_sanitized_error():
    """Confirms max_output_chars config is strictly enforced on agent output."""
    audit_sink = InMemoryAgentAuditSink()
    oversized_summary = "X" * 1500  # Exceeds max_output_chars=500
    fake_gw = FakeLLMGateway(
        default_response=StructuredAgentFindingOutput(
            summary=oversized_summary, confidence=0.9
        )
    )
    runtime = AgentRuntime(
        config=AgentRuntimeConfig(max_output_chars=500),
        llm_gateway=fake_gw,
        audit_sink=audit_sink,
    )
    runtime.register_agent(make_productivity_agent_def())

    req = create_agent_request(
        correlation_id="17171717-1717-4717-8717-171717171717",
        sender="coordinator",
        recipient="productivity",
        intent="productivity_analysis",
        authenticated_user_id="mgr-1",
        question="Check velocity",
    )
    principal = make_manager_principal()

    resp = await runtime.execute_agent(req, principal)
    assert resp.status == "failed"
    assert resp.error_code == "OUTPUT_SIZE_EXCEEDED"
    assert "character limit" in resp.safe_error_message.lower()

    # Verify audit event
    failed_events = audit_sink.get_events_by_type("output_validation_failed")
    assert len(failed_events) == 1
    assert failed_events[0].safe_reason_code == "OUTPUT_SIZE_EXCEEDED"


@pytest.mark.asyncio
async def test_execute_many_fail_fast_cancels_and_awaits_remaining_tasks():
    """Confirms fail_fast cancels in-flight tasks and leaves no orphan background execution."""
    cancelled_observed = False

    async def slow_handler(**kwargs):
        nonlocal cancelled_observed
        try:
            await asyncio.sleep(5.0)
            return StructuredAgentFindingOutput(summary="Slow task", confidence=0.8)
        except asyncio.CancelledError:
            cancelled_observed = True
            raise

    fake_gw = FakeLLMGateway(handler=slow_handler)
    runtime = AgentRuntime(llm_gateway=fake_gw)
    runtime.register_agent(make_productivity_agent_def())

    principal = make_manager_principal()

    req_fail = create_agent_request(
        correlation_id="18181818-1818-4818-8818-181818181818",
        sender="coordinator",
        recipient="task_assigning",  # Not registered -> fails immediately
        intent="task_assignment_recommendation",
        authenticated_user_id="mgr-1",
        question="Immediate fail",
    )
    req_slow = create_agent_request(
        correlation_id="19191919-1919-4919-8919-191919191919",
        sender="coordinator",
        recipient="productivity",
        intent="productivity_analysis",
        authenticated_user_id="mgr-1",
        question="Slow task",
    )

    with pytest.raises(AgentRuntimeError):
        await runtime.execute_many(
            [(req_fail, principal), (req_slow, principal)],
            fail_fast=True,
        )

    # Allow event loop tick to verify task cancellation
    await asyncio.sleep(0.01)
    assert cancelled_observed is True


@pytest.mark.asyncio
async def test_max_evidence_items_config_strictly_bounds_evidence_count():
    """Confirms max_evidence_items config bounds the evidence provided to prompt and findings."""
    fake_gw = FakeLLMGateway(
        default_response=StructuredAgentFindingOutput(
            summary="Processed evidence", confidence=0.9
        )
    )
    # Configure max_evidence_items to 2
    runtime = AgentRuntime(
        config=AgentRuntimeConfig(max_evidence_items=2),
        llm_gateway=fake_gw,
    )
    runtime.register_agent(make_productivity_agent_def())

    # Provide 5 evidence items
    refs = [
        EvidenceReference(
            source_type="task",
            record_id=f"t-{i}",
            title=f"Task {i}",
            team_id="team-eng",
        )
        for i in range(5)
    ]

    req = create_agent_request(
        correlation_id="20202020-2020-4020-8020-202020202020",
        sender="coordinator",
        recipient="productivity",
        intent="productivity_analysis",
        authenticated_user_id="mgr-1",
        question="Analyze tasks",
        evidence_refs=refs,
    )
    principal = make_manager_principal()

    resp = await runtime.execute_agent(req, principal)
    assert resp.status == "completed"
    # Finding evidence_refs bounded by max_evidence_items (2)
    assert len(resp.finding.evidence_refs) == 2


@pytest.mark.asyncio
async def test_execute_many_provider_failure_cancels_slow_peer_in_fail_fast_mode():
    """
    Confirms that a failed AgentResponse from a provider failure triggers immediate fail-fast
    cancellation of slow peers, prevents false success audits from the slow peer, and
    under fail_fast=False waits for and returns both ordered responses.
    """
    audit_sink_fail_fast = InMemoryAgentAuditSink()
    b_cancelled_observed = False
    b_success_returned = False

    async def dynamic_handler(**kwargs):
        nonlocal b_cancelled_observed, b_success_returned
        user_prompt = kwargs.get("user_prompt", "")
        if "failing_request_A" in user_prompt:
            # Request A fails immediately via simulated provider outage
            raise LLMUnavailableError("Simulated LLM outage for Request A")
        elif "slow_request_B" in user_prompt:
            # Request B is deliberately slow
            try:
                await asyncio.sleep(2.0)
                b_success_returned = True
                return StructuredAgentFindingOutput(
                    summary="Slow peer completed", confidence=0.85
                )
            except asyncio.CancelledError:
                b_cancelled_observed = True
                raise
        return StructuredAgentFindingOutput(summary="Default", confidence=0.9)

    fake_gw = FakeLLMGateway(handler=dynamic_handler)
    runtime = AgentRuntime(llm_gateway=fake_gw, audit_sink=audit_sink_fail_fast)
    runtime.register_agent(make_productivity_agent_def())
    runtime.register_agent(make_wellbeing_agent_def())

    principal = make_manager_principal()

    req_a = create_agent_request(
        correlation_id="21212121-2121-4121-8121-212121212121",
        sender="coordinator",
        recipient="productivity",
        intent="productivity_analysis",
        authenticated_user_id="mgr-1",
        question="Analyze failing_request_A",
    )
    req_b = create_agent_request(
        correlation_id="22222222-2222-4222-8222-222222222222",
        sender="coordinator",
        recipient="wellbeing",
        intent="wellbeing_analysis",
        authenticated_user_id="mgr-1",
        question="Analyze slow_request_B",
    )

    # 1. Test fail_fast=True: Failed AgentResponse from A cancels slow peer B immediately
    with pytest.raises(AgentRuntimeError) as exc_info:
        await runtime.execute_many(
            [(req_a, principal), (req_b, principal)],
            fail_fast=True,
        )

    assert exc_info.value.safe_reason_code == "LLM_PROVIDER_ERROR"
    assert "unavailable" in exc_info.value.safe_message.lower()
    assert b_cancelled_observed is True
    assert b_success_returned is False

    # Verify B has NO success audit event recorded in sink
    events_b = audit_sink_fail_fast.get_events_by_correlation("22222222-2222-4222-8222-222222222222")
    completed_b = [e for e in events_b if e.event_type == "llm_request_completed"]
    assert len(completed_b) == 0

    # 2. Test fail_fast=False: Returns both ordered responses without cancelling B
    audit_sink_non_fail_fast = InMemoryAgentAuditSink()
    runtime_non_ff = AgentRuntime(
        llm_gateway=fake_gw, audit_sink=audit_sink_non_fail_fast
    )
    runtime_non_ff.register_agent(make_productivity_agent_def())
    runtime_non_ff.register_agent(make_wellbeing_agent_def())

    b_cancelled_observed = False
    b_success_returned = False

    results = await runtime_non_ff.execute_many(
        [(req_a, principal), (req_b, principal)],
        fail_fast=False,
    )

    assert len(results) == 2
    # Result A in position 0: failed response
    assert results[0].sender == "productivity"
    assert results[0].status == "failed"
    assert results[0].error_code == "LLM_PROVIDER_ERROR"
    # Result B in position 1: completed response
    assert results[1].sender == "wellbeing"
    assert results[1].status == "completed"
    assert results[1].finding.summary == "Slow peer completed"
    assert b_success_returned is True
