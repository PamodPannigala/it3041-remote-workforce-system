import abc
from datetime import datetime, timezone
import logging
from typing import Annotated, Literal
import uuid

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

from backend.app.modules.agents.protocol import (
    AgentIntent,
    AgentName,
    EvidenceSourceType,
)

logger = logging.getLogger("remote_workforce.agents.audit")

AuditEventType = Literal[
    "authorization_allowed",
    "authorization_denied",
    "agent_request_dispatched",
    "agent_response_received",
    "evidence_scope_applied",
    "llm_request_started",
    "llm_request_completed",
    "llm_request_failed",
    "output_validation_failed",
    "prompt_security_boundary_applied",
    "responsible_ai_policy_applied",
]

AuditOutcome = Literal["allowed", "denied", "success", "failure"]
PrincipalRole = Literal["employee", "manager", "admin"]


def _ensure_utc(v: datetime | None) -> datetime:
    if v is None:
        return datetime.now(timezone.utc)
    if v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v.astimezone(timezone.utc)


def _validate_uuid_str(v: str, field_name: str) -> str:
    if not v:
        raise ValueError(f"{field_name} is required")
    s = str(v).strip()
    try:
        val_uuid = uuid.UUID(s)
        return str(val_uuid)
    except (ValueError, TypeError, AttributeError):
        raise ValueError(f"Invalid {field_name} format: '{v}' is not a valid UUID")


class AgentAuditEvent(BaseModel):
    """
    Structured, privacy-safe audit record of an agent action or security decision.

    Privacy & Security Guarantees:
    This model strictly forbids and excludes:
    - User questions and prompts
    - System instructions
    - Evidence titles, snippets, and message contents
    - Pulse survey responses, comments, and metrics
    - PII (user names, email addresses)
    - Credentials (API keys, JWTs, Bearer tokens)
    - Raw LLM provider response bodies
    - Chain-of-thought or internal reasoning
    - Arbitrary metadata dictionaries
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str
    actor_user_id: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
    ]
    actor_role: PrincipalRole
    agent: AgentName
    event_type: AuditEventType
    outcome: AuditOutcome
    intent: AgentIntent | None = None
    evidence_source_types: list[EvidenceSourceType] = Field(default_factory=list)
    evidence_count: int = Field(default=0, ge=0)
    safe_reason_code: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
    ] | None = None
    model_name: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    ] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("event_id", mode="before")
    @classmethod
    def validate_event_id(cls, v):
        if v is None:
            return str(uuid.uuid4())
        return _validate_uuid_str(v, "event_id")

    @field_validator("correlation_id", mode="before")
    @classmethod
    def validate_correlation_id(cls, v):
        return _validate_uuid_str(v, "correlation_id")

    @field_validator("created_at", mode="before")
    @classmethod
    def validate_created_at(cls, v):
        return _ensure_utc(v)


# =========================================================================
# Audit Sink Interface & Implementations
# =========================================================================


class AgentAuditSink(abc.ABC):
    """Abstract interface for recording Agent Audit Events."""

    @abc.abstractmethod
    async def record_event(self, event: AgentAuditEvent) -> None:
        """Record an immutable, privacy-safe audit event."""
        pass


class InMemoryAgentAuditSink(AgentAuditSink):
    """
    In-memory audit event store for unit and integration testing.
    """

    def __init__(self):
        self.events: list[AgentAuditEvent] = []

    async def record_event(self, event: AgentAuditEvent) -> None:
        self.events.append(event)

    def get_events_by_correlation(self, correlation_id: str) -> list[AgentAuditEvent]:
        return [e for e in self.events if e.correlation_id == correlation_id]

    def get_events_by_type(self, event_type: AuditEventType) -> list[AgentAuditEvent]:
        return [e for e in self.events if e.event_type == event_type]

    def get_all_events(self) -> list[AgentAuditEvent]:
        return list(self.events)

    def clear(self) -> None:
        self.events.clear()


class SafeLoggingAgentAuditSink(AgentAuditSink):
    """
    Standard logger audit sink that emits structured key-value audit events
    containing only explicit, pre-vetted safe metadata fields.
    """

    def __init__(self, logger_instance: logging.Logger | None = None):
        self._logger = logger_instance or logger

    async def record_event(self, event: AgentAuditEvent) -> None:
        self._logger.info(
            "AGENT_AUDIT: event_id=%s correlation_id=%s actor=%s role=%s agent=%s event_type=%s outcome=%s intent=%s evidence_count=%d reason=%s model=%s",
            event.event_id,
            event.correlation_id,
            event.actor_user_id,
            event.actor_role,
            event.agent,
            event.event_type,
            event.outcome,
            event.intent or "none",
            event.evidence_count,
            event.safe_reason_code or "none",
            event.model_name or "none",
        )


# =========================================================================
# Typed Security Event Factories
# =========================================================================


def create_authorization_audit_event(
    *,
    correlation_id: str,
    actor_user_id: str,
    actor_role: PrincipalRole,
    agent: AgentName,
    allowed: bool,
    safe_reason_code: str,
    intent: AgentIntent | None = None,
) -> AgentAuditEvent:
    """Factory helper to construct an authorization decision audit event."""
    return AgentAuditEvent(
        correlation_id=correlation_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        agent=agent,
        event_type="authorization_allowed" if allowed else "authorization_denied",
        outcome="allowed" if allowed else "denied",
        intent=intent,
        safe_reason_code=safe_reason_code,
    )


def create_agent_dispatch_audit_event(
    *,
    correlation_id: str,
    actor_user_id: str,
    actor_role: PrincipalRole,
    sender: AgentName,
    recipient: AgentName,
    intent: AgentIntent,
    evidence_source_types: list[EvidenceSourceType] | None = None,
    evidence_count: int = 0,
) -> AgentAuditEvent:
    """Factory helper to construct an agent request dispatch audit event."""
    return AgentAuditEvent(
        correlation_id=correlation_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        agent=recipient,
        event_type="agent_request_dispatched",
        outcome="success",
        intent=intent,
        evidence_source_types=evidence_source_types or [],
        evidence_count=evidence_count,
        safe_reason_code=f"DISPATCH_FROM_{sender.upper()}",
    )


def create_llm_audit_event(
    *,
    correlation_id: str,
    actor_user_id: str,
    actor_role: PrincipalRole,
    agent: AgentName,
    event_type: Literal["llm_request_started", "llm_request_completed", "llm_request_failed"],
    outcome: Literal["success", "failure"],
    model_name: str,
    safe_reason_code: str | None = None,
) -> AgentAuditEvent:
    """Factory helper to construct a privacy-safe LLM interaction audit event."""
    return AgentAuditEvent(
        correlation_id=correlation_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        agent=agent,
        event_type=event_type,
        outcome=outcome,
        model_name=model_name,
        safe_reason_code=safe_reason_code,
    )


def create_policy_audit_event(
    *,
    correlation_id: str,
    actor_user_id: str,
    actor_role: PrincipalRole,
    agent: AgentName,
    event_type: Literal["evidence_scope_applied", "prompt_security_boundary_applied", "responsible_ai_policy_applied", "output_validation_failed"],
    outcome: AuditOutcome,
    safe_reason_code: str,
    evidence_count: int = 0,
) -> AgentAuditEvent:
    """Factory helper to construct a security policy enforcement audit event."""
    return AgentAuditEvent(
        correlation_id=correlation_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        agent=agent,
        event_type=event_type,
        outcome=outcome,
        evidence_count=evidence_count,
        safe_reason_code=safe_reason_code,
    )
