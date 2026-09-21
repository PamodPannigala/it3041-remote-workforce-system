from datetime import datetime, timezone
import logging
import uuid
import pytest
from pydantic import ValidationError

from backend.app.modules.agents.audit import (
    AgentAuditEvent,
    InMemoryAgentAuditSink,
    SafeLoggingAgentAuditSink,
    create_agent_dispatch_audit_event,
    create_authorization_audit_event,
    create_llm_audit_event,
    create_policy_audit_event,
)


def test_valid_audit_event_creation():
    cid = str(uuid.uuid4())
    event = AgentAuditEvent(
        correlation_id=cid,
        actor_user_id="user-123",
        actor_role="manager",
        agent="productivity",
        event_type="agent_request_dispatched",
        outcome="success",
        intent="productivity_analysis",
        evidence_source_types=["task"],
        evidence_count=3,
        safe_reason_code="DISPATCH_AUTHORIZED",
    )

    assert uuid.UUID(event.event_id)
    assert event.correlation_id == cid
    assert event.actor_user_id == "user-123"
    assert event.actor_role == "manager"
    assert event.agent == "productivity"
    assert event.event_type == "agent_request_dispatched"
    assert event.outcome == "success"
    assert event.evidence_count == 3
    assert event.created_at.tzinfo == timezone.utc


def test_audit_event_auto_generates_uuid_and_utc_timestamp():
    cid = str(uuid.uuid4())
    ev = AgentAuditEvent(
        correlation_id=cid,
        actor_user_id="u1",
        actor_role="employee",
        agent="collaboration",
        event_type="authorization_allowed",
        outcome="allowed",
    )
    assert uuid.UUID(ev.event_id).version == 4
    assert ev.created_at.tzinfo == timezone.utc


def test_audit_event_rejects_unknown_fields():
    cid = str(uuid.uuid4())
    with pytest.raises(ValidationError):
        AgentAuditEvent(
            correlation_id=cid,
            actor_user_id="user-123",
            actor_role="manager",
            agent="productivity",
            event_type="llm_request_started",
            outcome="success",
            user_prompt="Confidential user text",
        )


def test_audit_event_rejects_arbitrary_metadata_dictionaries():
    cid = str(uuid.uuid4())
    with pytest.raises(ValidationError):
        AgentAuditEvent(
            correlation_id=cid,
            actor_user_id="user-123",
            actor_role="manager",
            agent="productivity",
            event_type="llm_request_started",
            outcome="success",
            arbitrary_metadata={"api_key": "secret", "raw_response": {}},
        )


def test_audit_event_prompts_and_questions_cannot_be_included():
    cid = str(uuid.uuid4())
    with pytest.raises(ValidationError):
        AgentAuditEvent(
            correlation_id=cid,
            actor_user_id="user-123",
            actor_role="employee",
            agent="wellbeing",
            event_type="evidence_scope_applied",
            outcome="allowed",
            question="My private question",
            evidence_snippet="Private snippet text",
        )


def test_audit_event_invalid_uuid_rejected():
    with pytest.raises(ValidationError) as exc:
        AgentAuditEvent(
            correlation_id="invalid-correlation-uuid",
            actor_user_id="user-123",
            actor_role="manager",
            agent="productivity",
            event_type="authorization_allowed",
            outcome="allowed",
        )
    assert "not a valid UUID" in str(exc.value)


def test_audit_event_invalid_outcome_rejected():
    with pytest.raises(ValidationError):
        AgentAuditEvent(
            correlation_id=str(uuid.uuid4()),
            actor_user_id="user-123",
            actor_role="manager",
            agent="productivity",
            event_type="authorization_allowed",
            outcome="unrecognized_outcome",
        )


def test_audit_event_invalid_event_type_rejected():
    with pytest.raises(ValidationError):
        AgentAuditEvent(
            correlation_id=str(uuid.uuid4()),
            actor_user_id="user-123",
            actor_role="manager",
            agent="productivity",
            event_type="arbitrary_event_type",
            outcome="success",
        )


@pytest.mark.asyncio
async def test_in_memory_agent_audit_sink_recording_and_queries():
    sink = InMemoryAgentAuditSink()
    cid1 = str(uuid.uuid4())
    cid2 = str(uuid.uuid4())

    ev1 = create_authorization_audit_event(
        correlation_id=cid1,
        actor_user_id="user-1",
        actor_role="manager",
        agent="coordinator",
        allowed=True,
        safe_reason_code="ROLE_INTENT_AUTHORIZED",
        intent="productivity_analysis",
    )

    ev2 = create_agent_dispatch_audit_event(
        correlation_id=cid1,
        actor_user_id="user-1",
        actor_role="manager",
        sender="coordinator",
        recipient="productivity",
        intent="productivity_analysis",
        evidence_source_types=["task"],
        evidence_count=2,
    )

    ev3 = create_authorization_audit_event(
        correlation_id=cid2,
        actor_user_id="user-2",
        actor_role="employee",
        agent="task_assigning",
        allowed=False,
        safe_reason_code="EMPLOYEE_TASK_ASSIGNMENT_FORBIDDEN",
        intent="task_assignment_recommendation",
    )

    await sink.record_event(ev1)
    await sink.record_event(ev2)
    await sink.record_event(ev3)

    assert len(sink.get_all_events()) == 3

    # Query by correlation ID
    cid1_events = sink.get_events_by_correlation(cid1)
    assert len(cid1_events) == 2

    # Query by event type
    auth_events = sink.get_events_by_type("authorization_allowed")
    assert len(auth_events) == 1
    assert auth_events[0].actor_user_id == "user-1"


@pytest.mark.asyncio
async def test_in_memory_agent_audit_sink_clear():
    sink = InMemoryAgentAuditSink()
    ev = create_authorization_audit_event(
        correlation_id=str(uuid.uuid4()),
        actor_user_id="user-1",
        actor_role="manager",
        agent="coordinator",
        allowed=True,
        safe_reason_code="ROLE_INTENT_AUTHORIZED",
    )
    await sink.record_event(ev)
    assert len(sink.get_all_events()) == 1
    sink.clear()
    assert len(sink.get_all_events()) == 0


@pytest.mark.asyncio
async def test_safe_logging_audit_sink_logs_safe_fields(caplog):
    test_logger = logging.getLogger("test_audit_logger_safe")
    sink = SafeLoggingAgentAuditSink(logger_instance=test_logger)

    cid = str(uuid.uuid4())
    ev = create_llm_audit_event(
        correlation_id=cid,
        actor_user_id="user-456",
        actor_role="admin",
        agent="productivity",
        event_type="llm_request_completed",
        outcome="success",
        model_name="gpt-4o-mini",
        safe_reason_code="STRUCTURED_OUTPUT_VALIDATED",
    )

    with caplog.at_level(logging.INFO, logger="test_audit_logger_safe"):
        await sink.record_event(ev)

    log_output = caplog.text
    assert "AGENT_AUDIT:" in log_output
    assert cid in log_output
    assert "user-456" in log_output
    assert "admin" in log_output
    assert "productivity" in log_output
    assert "llm_request_completed" in log_output
    assert "gpt-4o-mini" in log_output
    assert "STRUCTURED_OUTPUT_VALIDATED" in log_output


@pytest.mark.asyncio
async def test_safe_logging_audit_sink_never_logs_prompts_secrets_or_pii(caplog):
    test_logger = logging.getLogger("test_audit_logger_pii")
    sink = SafeLoggingAgentAuditSink(logger_instance=test_logger)

    cid = str(uuid.uuid4())
    ev = create_authorization_audit_event(
        correlation_id=cid,
        actor_user_id="user-789",
        actor_role="manager",
        agent="coordinator",
        allowed=False,
        safe_reason_code="ROLE_NOT_AUTHORIZED",
    )

    with caplog.at_level(logging.INFO, logger="test_audit_logger_pii"):
        await sink.record_event(ev)

    log_output = caplog.text
    assert "Authorization" not in log_output
    assert "Bearer" not in log_output
    assert "password" not in log_output
    assert "email" not in log_output
    assert "prompt" not in log_output
    assert "question" not in log_output
    assert "snippet" not in log_output


def test_factory_create_authorization_audit_event():
    cid = str(uuid.uuid4())
    ev = create_authorization_audit_event(
        correlation_id=cid,
        actor_user_id="u1",
        actor_role="manager",
        agent="coordinator",
        allowed=True,
        safe_reason_code="ROLE_INTENT_AUTHORIZED",
        intent="productivity_analysis",
    )
    assert ev.correlation_id == cid
    assert ev.event_type == "authorization_allowed"
    assert ev.outcome == "allowed"
    assert ev.intent == "productivity_analysis"


def test_factory_create_agent_dispatch_audit_event():
    cid = str(uuid.uuid4())
    ev = create_agent_dispatch_audit_event(
        correlation_id=cid,
        actor_user_id="u1",
        actor_role="manager",
        sender="coordinator",
        recipient="productivity",
        intent="productivity_analysis",
        evidence_source_types=["task"],
        evidence_count=4,
    )
    assert ev.correlation_id == cid
    assert ev.agent == "productivity"
    assert ev.event_type == "agent_request_dispatched"
    assert ev.evidence_count == 4


def test_factory_create_llm_audit_event():
    cid = str(uuid.uuid4())
    ev = create_llm_audit_event(
        correlation_id=cid,
        actor_user_id="u1",
        actor_role="manager",
        agent="productivity",
        event_type="llm_request_completed",
        outcome="success",
        model_name="gpt-4o-mini",
        safe_reason_code="PARSED_OK",
    )
    assert ev.correlation_id == cid
    assert ev.model_name == "gpt-4o-mini"
    assert ev.event_type == "llm_request_completed"


def test_factory_create_policy_audit_event():
    cid = str(uuid.uuid4())
    ev = create_policy_audit_event(
        correlation_id=cid,
        actor_user_id="user-789",
        actor_role="manager",
        agent="wellbeing",
        event_type="responsible_ai_policy_applied",
        outcome="success",
        safe_reason_code="RESPONSIBLE_AI_GUARDRAILS_PASSED",
        evidence_count=1,
    )
    assert ev.correlation_id == cid
    assert ev.event_type == "responsible_ai_policy_applied"
    assert ev.outcome == "success"
    assert ev.evidence_count == 1
    assert ev.safe_reason_code == "RESPONSIBLE_AI_GUARDRAILS_PASSED"
