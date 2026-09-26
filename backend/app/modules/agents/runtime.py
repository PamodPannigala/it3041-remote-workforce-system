import asyncio
from datetime import datetime, timezone
import logging
from typing import Annotated, Any, Callable, Generic, Protocol, TypeVar
import uuid

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from backend.app.modules.agents.audit import (
    AgentAuditEvent,
    AgentAuditSink,
    InMemoryAgentAuditSink,
    SafeLoggingAgentAuditSink,
    create_agent_dispatch_audit_event,
    create_authorization_audit_event,
    create_llm_audit_event,
    create_policy_audit_event,
)
from backend.app.modules.agents.llm_gateway import (
    FakeLLMGateway,
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMError,
    LLMGateway,
    LLMRequestError,
    LLMResponseValidationError,
    LLMResult,
    LLMTimeoutError,
    LLMUnavailableError,
    OpenAICompatibleLLMGateway,
)
from backend.app.modules.agents.protocol import (
    AgentFinding,
    AgentIntent,
    AgentName,
    AgentRequest,
    AgentResponse,
    EvidenceReference,
    EvidenceSourceType,
    create_agent_response,
    format_evidence_for_prompt,
)
from backend.app.modules.agents.security_policy import (
    AGENT_ALLOWED_EVIDENCE_SOURCES,
    AGENT_ALLOWED_INTENTS,
    AuthenticatedPrincipal,
    AuthorizationDecision,
    authorize_user_intent,
    validate_agent_capability,
    validate_dependency_flow,
    validate_evidence_team_scope,
    validate_request_dependencies,
    validate_responsible_ai_guardrails,
    sanitize_public_prose,
)

logger = logging.getLogger("remote_workforce.agents.runtime")

T = TypeVar("T", bound=BaseModel)

# =========================================================================
# 1. Typed Runtime Exceptions
# =========================================================================


class AgentRuntimeError(Exception):
    """Base exception for all agent runtime errors."""

    def __init__(
        self,
        message: str,
        safe_reason_code: str = "AGENT_RUNTIME_ERROR",
        safe_message: str | None = None,
    ):
        super().__init__(message)
        self.safe_reason_code = safe_reason_code
        self.safe_message = safe_message or message


class AgentConfigError(AgentRuntimeError):
    """Raised when runtime configuration is invalid."""

    def __init__(self, message: str, safe_reason_code: str = "CONFIG_ERROR"):
        super().__init__(message, safe_reason_code=safe_reason_code)


class AgentRegistrationError(AgentRuntimeError):
    """Raised when registering an agent or tool fails."""

    def __init__(self, message: str, safe_reason_code: str = "REGISTRATION_ERROR"):
        super().__init__(message, safe_reason_code=safe_reason_code)


class UnknownAgentError(AgentRegistrationError):
    """Raised when dispatching to an unregistered agent."""

    def __init__(self, agent_name: str):
        super().__init__(
            f"Agent '{agent_name}' is not registered in runtime",
            safe_reason_code="UNKNOWN_AGENT",
        )
        self.agent_name = agent_name


class UnknownToolError(AgentRegistrationError):
    """Raised when an unregistered tool is requested."""

    def __init__(self, tool_name: str):
        super().__init__(
            f"Tool '{tool_name}' is not registered in runtime",
            safe_reason_code="UNKNOWN_TOOL",
        )
        self.tool_name = tool_name


class AgentAuthorizationError(AgentRuntimeError):
    """Raised when policy, capability, or RBAC authorization fails."""

    def __init__(
        self,
        message: str,
        safe_reason_code: str = "AUTHORIZATION_DENIED",
        safe_message: str | None = None,
    ):
        super().__init__(
            message,
            safe_reason_code=safe_reason_code,
            safe_message=safe_message or "Agent execution not authorized",
        )


class AgentCapabilityError(AgentAuthorizationError):
    """Raised when an agent or tool lacks required capability."""

    def __init__(self, message: str, safe_reason_code: str = "CAPABILITY_UNAUTHORIZED"):
        super().__init__(message, safe_reason_code=safe_reason_code)


class AgentTimeoutError(AgentRuntimeError):
    """Raised when agent execution exceeds configured timeout."""

    def __init__(self, message: str = "Agent execution timed out"):
        super().__init__(
            message,
            safe_reason_code="EXECUTION_TIMEOUT",
            safe_message="Agent execution timed out",
        )


class AgentProviderError(AgentRuntimeError):
    """Raised when LLM provider encounters an error."""

    def __init__(self, message: str, safe_reason_code: str = "PROVIDER_ERROR"):
        super().__init__(
            message,
            safe_reason_code=safe_reason_code,
            safe_message="LLM provider error occurred",
        )


class AgentOutputValidationError(AgentRuntimeError):
    """Raised when LLM structured output fails schema validation."""

    def __init__(self, message: str, safe_reason_code: str = "OUTPUT_VALIDATION_ERROR"):
        super().__init__(
            message,
            safe_reason_code=safe_reason_code,
            safe_message="Structured output validation failed",
        )


class AgentToolExecutionError(AgentRuntimeError):
    """Raised when a registered tool fails during execution."""

    def __init__(self, message: str, safe_reason_code: str = "TOOL_EXECUTION_ERROR"):
        super().__init__(
            message,
            safe_reason_code=safe_reason_code,
            safe_message="Tool execution failed",
        )


# =========================================================================
# 2. Strict Configuration & Runtime Models
# =========================================================================


class AgentRuntimeConfig(BaseModel):
    """
    Strict, immutable runtime configuration.
    Prohibits memory, autonomous delegation, dynamic code execution, and unconstrained retries.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    default_timeout_seconds: float = Field(default=30.0, ge=1.0, le=300.0)
    max_evidence_items: int = Field(default=20, ge=1, le=50)
    max_concurrent_executions: int = Field(default=5, ge=1, le=20)
    max_output_chars: int = Field(default=10_000, ge=100, le=50_000)
    max_evidence_chars: int = Field(default=15_000, ge=500, le=50_000)


class AgentDefinition(BaseModel):
    """
    Strict immutable definition for a registered application agent.
    Never holds credentials, database connections, or mutable state.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: AgentName
    role: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
    ]
    goal: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
    ]
    allowed_intents: set[AgentIntent] = Field(default_factory=set)
    allowed_evidence_sources: set[EvidenceSourceType] = Field(default_factory=set)
    system_prompt: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000),
    ]
    response_model: type[BaseModel]
    timeout_seconds: float | None = Field(default=None, ge=1.0, le=300.0)

    @model_validator(mode="after")
    def validate_capabilities(self) -> "AgentDefinition":
        policy_intents = AGENT_ALLOWED_INTENTS.get(self.name, set())
        if not self.allowed_intents:
            object.__setattr__(self, "allowed_intents", set(policy_intents))
        else:
            invalid_intents = self.allowed_intents - policy_intents
            if invalid_intents:
                raise ValueError(
                    f"Agent '{self.name}' declared intents {invalid_intents} not allowed by security policy"
                )

        policy_sources = AGENT_ALLOWED_EVIDENCE_SOURCES.get(self.name, set())
        if not self.allowed_evidence_sources:
            object.__setattr__(self, "allowed_evidence_sources", set(policy_sources))
        else:
            invalid_sources = self.allowed_evidence_sources - policy_sources
            if invalid_sources:
                raise ValueError(
                    f"Agent '{self.name}' declared evidence sources {invalid_sources} not allowed by security policy"
                )
        return self


class ExecutionContext(BaseModel):
    """
    Typed, immutable execution context preserving correlation ID and authenticated principal.
    Never accepts client-controlled identity overrides.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    correlation_id: str
    principal: AuthenticatedPrincipal
    request: AgentRequest
    dependency_findings: list[AgentFinding] = Field(default_factory=list)
    # Per-execution tool facts; never accepted in client requests or shared across tasks.
    evidence_metrics: dict[str, Any] = Field(default_factory=dict, exclude=True)


# =========================================================================
# 3. Agent Tool / Evidence Provider Contract
# =========================================================================


class AgentTool(Protocol):
    """
    Typed protocol for explicit, deterministic evidence tools.
    """

    name: str
    target_agent: AgentName
    required_intent: AgentIntent
    source_type: EvidenceSourceType

    async def execute(self, context: ExecutionContext) -> list[EvidenceReference]:
        """Execute tool and return structured evidence references."""
        ...


class BaseAgentTool:
    """
    Standard base class for explicitly registered evidence collection tools.
    """

    def __init__(
        self,
        name: str,
        target_agent: AgentName,
        required_intent: AgentIntent,
        source_type: EvidenceSourceType,
        handler: Callable[[ExecutionContext], Any],
    ):
        self.name = str(name).strip()
        self.target_agent = target_agent
        self.required_intent = required_intent
        self.source_type = source_type
        self.handler = handler

        if not self.name:
            raise AgentConfigError("Tool name cannot be empty")

    async def execute(self, context: ExecutionContext) -> list[EvidenceReference]:
        res = self.handler(context)
        if asyncio.iscoroutine(res):
            res = await res
        if not isinstance(res, list):
            raise AgentToolExecutionError(
                f"Tool '{self.name}' must return a list of EvidenceReference objects"
            )
        for item in res:
            if not isinstance(item, EvidenceReference):
                raise AgentToolExecutionError(
                    f"Tool '{self.name}' returned invalid item of type {type(item)}"
                )
        return res


# =========================================================================
# 4. Standard Agent Finding Output Schema for LLM Responses
# =========================================================================


class StructuredAgentFindingOutput(BaseModel):
    """
    Standard structured schema requested from LLM completions.
    Maps directly into AgentFinding.
    """

    model_config = ConfigDict(extra="forbid")

    summary: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=3000),
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    limitations: list[
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
        ]
    ] = Field(default_factory=list, max_length=20)
    recommended_actions: list[
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
        ]
    ] = Field(default_factory=list, max_length=20)


def bound_specialist_confidence(
    raw_confidence: float,
    evidence_refs: list[EvidenceReference] | None = None,
    limitations: list[str] | None = None,
) -> float:
    """
    Bounds specialist confidence deterministically by evidence completeness.
    A finding with a small evidence sample or missing important fields or explicit
    limitations must never return 1.0.
    """
    conf = float(raw_confidence)
    ev_count = len(evidence_refs) if evidence_refs else 0
    lims = [l for l in (limitations or []) if l.strip()]

    # If explicit evidence limitations exist, cap at 0.85 (never 1.0)
    if lims:
        conf = min(conf, 0.85)

    # Bound by evidence completeness:
    if ev_count == 0:
        conf = min(conf, 0.30)
    elif ev_count < 3:
        conf = min(conf, 0.70)
    elif ev_count < 5:
        conf = min(conf, 0.85)

    if lims or ev_count < 5:
        conf = min(conf, 0.85)

    return round(max(0.0, min(conf, 1.0)), 2)


# =========================================================================
# 5. Core Agent Runtime
# =========================================================================


class AgentRuntime:
    """
    Lightweight, explicit, testable custom multi-agent runtime.
    Reuses existing protocol, security policy, LLM gateway, and audit infrastructure.
    """

    def __init__(
        self,
        config: AgentRuntimeConfig | None = None,
        llm_gateway: LLMGateway | None = None,
        audit_sink: AgentAuditSink | None = None,
    ):
        self.config = config or AgentRuntimeConfig()
        self.llm_gateway = llm_gateway or FakeLLMGateway()
        self.audit_sink = audit_sink or SafeLoggingAgentAuditSink()
        self._agents: dict[AgentName, AgentDefinition] = {}
        self._tools: dict[str, AgentTool] = {}

    def register_agent(self, definition: AgentDefinition) -> None:
        """Register an agent definition in the runtime."""
        if definition.name in self._agents:
            raise AgentRegistrationError(
                f"Agent '{definition.name}' is already registered",
                safe_reason_code="DUPLICATE_AGENT_REGISTRATION",
            )
        self._agents[definition.name] = definition

    def register_tool(self, tool: AgentTool) -> None:
        """Register an explicit tool in the runtime."""
        if tool.name in self._tools:
            raise AgentRegistrationError(
                f"Tool '{tool.name}' is already registered",
                safe_reason_code="DUPLICATE_TOOL_REGISTRATION",
            )
        self._tools[tool.name] = tool

    def get_agent(self, name: AgentName) -> AgentDefinition:
        """Retrieve registered agent definition or raise UnknownAgentError."""
        if name not in self._agents:
            raise UnknownAgentError(name)
        return self._agents[name]

    def get_tool(self, name: str) -> AgentTool:
        """Retrieve registered tool or raise UnknownToolError."""
        if name not in self._tools:
            raise UnknownToolError(name)
        return self._tools[name]

    async def execute_agent(
        self,
        request: AgentRequest,
        principal: AuthenticatedPrincipal,
        tool_names: list[str] | None = None,
    ) -> AgentResponse:
        """
        Safely executes a registered agent against a validated AgentRequest.
        Enforces security policy, tool authorization, whole-execution timeout,
        bounded LLM gateway call, output limits, and privacy-safe audit logging.
        """
        correlation_id = request.correlation_id
        target_agent = request.recipient

        # 1. Verify target agent registration
        if target_agent not in self._agents:
            await self._record_audit(
                create_authorization_audit_event(
                    correlation_id=correlation_id,
                    actor_user_id=principal.user_id,
                    actor_role=principal.role,
                    agent=target_agent,
                    allowed=False,
                    safe_reason_code="UNKNOWN_AGENT",
                    intent=request.intent,
                )
            )
            return create_agent_response(
                correlation_id=correlation_id,
                sender=target_agent,
                recipient=request.sender,
                status="failed",
                message_type="error",
                error_code="UNKNOWN_AGENT",
                safe_error_message=f"Target agent '{target_agent}' is not registered",
            )

        agent_def = self._agents[target_agent]
        timeout_sec = agent_def.timeout_seconds or self.config.default_timeout_seconds
        model_name = getattr(self.llm_gateway, "model", "default-llm")

        # Execute the complete agent pipeline under the whole-execution timeout
        try:
            return await asyncio.wait_for(
                self._execute_agent_pipeline(
                    request=request,
                    principal=principal,
                    agent_def=agent_def,
                    tool_names=tool_names,
                    model_name=str(model_name),
                ),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError:
            await self._record_audit(
                create_llm_audit_event(
                    correlation_id=correlation_id,
                    actor_user_id=principal.user_id,
                    actor_role=principal.role,
                    agent=target_agent,
                    event_type="llm_request_failed",
                    outcome="failure",
                    model_name=str(model_name),
                    safe_reason_code="EXECUTION_TIMEOUT",
                )
            )
            return create_agent_response(
                correlation_id=correlation_id,
                sender=target_agent,
                recipient=request.sender,
                status="failed",
                message_type="error",
                error_code="EXECUTION_TIMEOUT",
                safe_error_message="Agent execution exceeded timeout limit",
            )

    async def _execute_agent_pipeline(
        self,
        request: AgentRequest,
        principal: AuthenticatedPrincipal,
        agent_def: AgentDefinition,
        tool_names: list[str] | None,
        model_name: str,
    ) -> AgentResponse:
        correlation_id = request.correlation_id
        target_agent = agent_def.name

        # 2. Enforce Security Policy: User Intent & Role Scope
        user_auth = authorize_user_intent(principal, request.intent, target_team_id=request.target_team_id)
        if not user_auth.allowed:
            await self._record_audit(
                create_authorization_audit_event(
                    correlation_id=correlation_id,
                    actor_user_id=principal.user_id,
                    actor_role=principal.role,
                    agent=target_agent,
                    allowed=False,
                    safe_reason_code=user_auth.safe_reason_code,
                    intent=request.intent,
                )
            )
            return create_agent_response(
                correlation_id=correlation_id,
                sender=target_agent,
                recipient=request.sender,
                status="failed",
                message_type="error",
                error_code=user_auth.safe_reason_code,
                safe_error_message=user_auth.safe_message,
            )

        # 3. Enforce Security Policy: Agent Capability & Evidence Matrix
        cap_auth = validate_agent_capability(target_agent, request.intent)
        if not cap_auth.allowed:
            await self._record_audit(
                create_authorization_audit_event(
                    correlation_id=correlation_id,
                    actor_user_id=principal.user_id,
                    actor_role=principal.role,
                    agent=target_agent,
                    allowed=False,
                    safe_reason_code=cap_auth.safe_reason_code,
                    intent=request.intent,
                )
            )
            return create_agent_response(
                correlation_id=correlation_id,
                sender=target_agent,
                recipient=request.sender,
                status="failed",
                message_type="error",
                error_code=cap_auth.safe_reason_code,
                safe_error_message=cap_auth.safe_message,
            )

        # 4. Enforce Security Policy: Cross-Agent Dependency Flow & Provenance
        dep_auth = validate_request_dependencies(request)
        if not dep_auth.allowed:
            await self._record_audit(
                create_policy_audit_event(
                    correlation_id=correlation_id,
                    actor_user_id=principal.user_id,
                    actor_role=principal.role,
                    agent=target_agent,
                    event_type="responsible_ai_policy_applied",
                    outcome="denied",
                    safe_reason_code=dep_auth.safe_reason_code,
                )
            )
            return create_agent_response(
                correlation_id=correlation_id,
                sender=target_agent,
                recipient=request.sender,
                status="failed",
                message_type="error",
                error_code=dep_auth.safe_reason_code,
                safe_error_message=dep_auth.safe_message,
            )

        # 5. Enforce Security Policy: Responsible AI Guardrails on Request
        rai_req_auth = validate_responsible_ai_guardrails(
            agent=target_agent,
            intent=request.intent,
            dependency_findings=request.dependency_findings,
        )
        if not rai_req_auth.allowed:
            await self._record_audit(
                create_policy_audit_event(
                    correlation_id=correlation_id,
                    actor_user_id=principal.user_id,
                    actor_role=principal.role,
                    agent=target_agent,
                    event_type="responsible_ai_policy_applied",
                    outcome="denied",
                    safe_reason_code=rai_req_auth.safe_reason_code,
                )
            )
            return create_agent_response(
                correlation_id=correlation_id,
                sender=target_agent,
                recipient=request.sender,
                status="failed",
                message_type="error",
                error_code=rai_req_auth.safe_reason_code,
                safe_error_message=rai_req_auth.safe_message,
            )

        # 6. Build typed Execution Context
        context = ExecutionContext(
            correlation_id=correlation_id,
            principal=principal,
            request=request,
            dependency_findings=request.dependency_findings,
        )
        from backend.app.modules.agents.confidence_scorer import is_prohibited_request
        if is_prohibited_request(request.question):
            return create_agent_response(
                correlation_id=correlation_id, sender=target_agent, recipient=request.sender,
                status="failed", message_type="error", error_code="PROHIBITED_REQUEST",
                safe_error_message="This request cannot be analysed using authorized team evidence.",
            )

        # 7. Collect and Validate Tools / Evidence
        collected_evidence: list[EvidenceReference] = list(request.evidence_refs)
        if tool_names:
            for t_name in tool_names:
                if t_name not in self._tools:
                    await self._record_audit(
                        create_policy_audit_event(
                            correlation_id=correlation_id,
                            actor_user_id=principal.user_id,
                            actor_role=principal.role,
                            agent=target_agent,
                            event_type="responsible_ai_policy_applied",
                            outcome="denied",
                            safe_reason_code="UNKNOWN_TOOL",
                        )
                    )
                    return create_agent_response(
                        correlation_id=correlation_id,
                        sender=target_agent,
                        recipient=request.sender,
                        status="failed",
                        message_type="error",
                        error_code="UNKNOWN_TOOL",
                        safe_error_message=f"Tool '{t_name}' is not registered",
                    )

                tool = self._tools[t_name]

                # Verify tool belongs to target agent
                if tool.target_agent != target_agent:
                    await self._record_audit(
                        create_policy_audit_event(
                            correlation_id=correlation_id,
                            actor_user_id=principal.user_id,
                            actor_role=principal.role,
                            agent=target_agent,
                            event_type="responsible_ai_policy_applied",
                            outcome="denied",
                            safe_reason_code="TOOL_TARGET_AGENT_MISMATCH",
                        )
                    )
                    return create_agent_response(
                        correlation_id=correlation_id,
                        sender=target_agent,
                        recipient=request.sender,
                        status="failed",
                        message_type="error",
                        error_code="TOOL_TARGET_AGENT_MISMATCH",
                        safe_error_message=f"Tool '{t_name}' is not authorized for agent '{target_agent}'",
                    )

                # Verify tool intent capability
                if tool.required_intent != request.intent:
                    await self._record_audit(
                        create_policy_audit_event(
                            correlation_id=correlation_id,
                            actor_user_id=principal.user_id,
                            actor_role=principal.role,
                            agent=target_agent,
                            event_type="responsible_ai_policy_applied",
                            outcome="denied",
                            safe_reason_code="TOOL_CAPABILITY_UNAUTHORIZED",
                        )
                    )
                    return create_agent_response(
                        correlation_id=correlation_id,
                        sender=target_agent,
                        recipient=request.sender,
                        status="failed",
                        message_type="error",
                        error_code="TOOL_CAPABILITY_UNAUTHORIZED",
                        safe_error_message=f"Tool '{t_name}' is not authorized for intent '{request.intent}'",
                    )

                # Verify agent is allowed to process this evidence source type
                if tool.source_type not in agent_def.allowed_evidence_sources:
                    await self._record_audit(
                        create_policy_audit_event(
                            correlation_id=correlation_id,
                            actor_user_id=principal.user_id,
                            actor_role=principal.role,
                            agent=target_agent,
                            event_type="responsible_ai_policy_applied",
                            outcome="denied",
                            safe_reason_code="EVIDENCE_SOURCE_UNAUTHORIZED",
                        )
                    )
                    return create_agent_response(
                        correlation_id=correlation_id,
                        sender=target_agent,
                        recipient=request.sender,
                        status="failed",
                        message_type="error",
                        error_code="EVIDENCE_SOURCE_UNAUTHORIZED",
                        safe_error_message=f"Agent '{target_agent}' is not authorized to collect evidence from '{tool.source_type}'",
                    )

                # Execute tool safely
                try:
                    tool_refs = await tool.execute(context)
                except AgentAuthorizationError as e:
                    logger.warning("Tool %s authorization failed: %s", t_name, type(e).__name__)
                    await self._record_audit(
                        create_authorization_audit_event(
                            correlation_id=correlation_id,
                            actor_user_id=principal.user_id,
                            actor_role=principal.role,
                            agent=target_agent,
                            allowed=False,
                            safe_reason_code=e.safe_reason_code,
                            intent=request.intent,
                        )
                    )
                    return create_agent_response(
                        correlation_id=correlation_id,
                        sender=target_agent,
                        recipient=request.sender,
                        status="failed",
                        message_type="error",
                        error_code=e.safe_reason_code,
                        safe_error_message=e.safe_message,
                    )
                except Exception as e:
                    logger.warning("Tool %s execution failed: %s", t_name, type(e).__name__)
                    await self._record_audit(
                        create_policy_audit_event(
                            correlation_id=correlation_id,
                            actor_user_id=principal.user_id,
                            actor_role=principal.role,
                            agent=target_agent,
                            event_type="responsible_ai_policy_applied",
                            outcome="failure",
                            safe_reason_code=getattr(e, "safe_reason_code", "TOOL_EXECUTION_FAILURE"),
                        )
                    )
                    return create_agent_response(
                        correlation_id=correlation_id,
                        sender=target_agent,
                        recipient=request.sender,
                        status="failed",
                        message_type="error",
                        error_code=getattr(e, "safe_reason_code", "TOOL_EXECUTION_FAILURE"),
                        safe_error_message=getattr(e, "safe_message", f"Execution of tool '{t_name}' failed"),
                    )

                # Apply team-scope policy to each evidence item (defense in depth)
                for ref in tool_refs:
                    scope_auth = validate_evidence_team_scope(principal, ref)
                    if not scope_auth.allowed:
                        await self._record_audit(
                            create_policy_audit_event(
                                correlation_id=correlation_id,
                                actor_user_id=principal.user_id,
                                actor_role=principal.role,
                                agent=target_agent,
                                event_type="evidence_scope_applied",
                                outcome="denied",
                                safe_reason_code=scope_auth.safe_reason_code,
                            )
                        )
                        return create_agent_response(
                            correlation_id=correlation_id,
                            sender=target_agent,
                            recipient=request.sender,
                            status="failed",
                            message_type="error",
                            error_code=scope_auth.safe_reason_code,
                            safe_error_message=scope_auth.safe_message,
                        )
                    collected_evidence.append(ref)

        # Enforce max evidence items bound
        final_evidence = collected_evidence[: self.config.max_evidence_items]
        ev_sources = list(dict.fromkeys(ref.source_type for ref in final_evidence))

        # 8. Record Dispatch Audit Event
        await self._record_audit(
            create_agent_dispatch_audit_event(
                correlation_id=correlation_id,
                actor_user_id=principal.user_id,
                actor_role=principal.role,
                sender=request.sender,
                recipient=target_agent,
                intent=request.intent,
                evidence_source_types=ev_sources,
                evidence_count=len(final_evidence),
            )
        )

        # 9. Format Evidence and Build Prompt
        formatted_evidence = format_evidence_for_prompt(
            final_evidence, max_chars=self.config.max_evidence_chars
        )

        # Format dependency findings if present
        dep_section = ""
        if request.dependency_findings:
            dep_summaries = []
            for dep in request.dependency_findings:
                dep_summaries.append(
                    f"- Agent: {dep.agent}\n  Summary: {dep.summary}\n  Confidence: {dep.confidence}"
                )
            dep_section = (
                "\n\nUPSTREAM DEPENDENCY FINDINGS:\n" + "\n".join(dep_summaries) + "\n"
            )

        user_prompt = (
            f"QUESTION / INSTRUCTION:\n{request.question}\n"
            f"{dep_section}\n"
            f"{formatted_evidence}\n\n"
            "Produce a structured analysis with summary, confidence (0.0 to 1.0), "
            "limitations list, and recommended_actions list. Do NOT output internal chain-of-thought."
        )

        # 10. Execute LLM Gateway Call exactly once
        await self._record_audit(
            create_llm_audit_event(
                correlation_id=correlation_id,
                actor_user_id=principal.user_id,
                actor_role=principal.role,
                agent=target_agent,
                event_type="llm_request_started",
                outcome="success",
                model_name=model_name,
            )
        )

        try:
            llm_result: LLMResult[Any] = await self.llm_gateway.generate_structured(
                system_prompt=agent_def.system_prompt,
                user_prompt=user_prompt,
                response_model=agent_def.response_model,
                correlation_id=correlation_id,
            )
            structured_content = llm_result.content
            await self._record_audit(
                create_llm_audit_event(
                    correlation_id=correlation_id,
                    actor_user_id=principal.user_id,
                    actor_role=principal.role,
                    agent=target_agent,
                    event_type="llm_request_completed",
                    outcome="success",
                    model_name=str(llm_result.model),
                )
            )
        except (LLMResponseValidationError, LLMRequestError) as e:
            await self._record_audit(
                create_policy_audit_event(
                    correlation_id=correlation_id,
                    actor_user_id=principal.user_id,
                    actor_role=principal.role,
                    agent=target_agent,
                    event_type="output_validation_failed",
                    outcome="failure",
                    safe_reason_code="OUTPUT_VALIDATION_ERROR",
                )
            )
            if (target_agent == "task_assigning"
                    and isinstance(e, LLMResponseValidationError)
                    and context.evidence_metrics.get("task_assignment") is not None):
                from backend.app.modules.agents.task_assignment import TaskAssignmentFindingOutput
                # No provider claims survived parsing. Continue through the same
                # deterministic formatting, privacy and policy checks below.
                structured_content = TaskAssignmentFindingOutput(
                    summary="Verified task and candidate evidence reviewed.",
                    confidence=context.evidence_metrics["task_assignment_confidence"],
                )
            else:
                return create_agent_response(
                    correlation_id=correlation_id,
                    sender=target_agent,
                    recipient=request.sender,
                    status="failed",
                    message_type="error",
                    error_code="OUTPUT_VALIDATION_ERROR",
                    safe_error_message="Structured LLM response validation failed",
                )
        except (LLMAuthenticationError, LLMConfigurationError, LLMUnavailableError, LLMError) as e:
            await self._record_audit(
                create_llm_audit_event(
                    correlation_id=correlation_id,
                    actor_user_id=principal.user_id,
                    actor_role=principal.role,
                    agent=target_agent,
                    event_type="llm_request_failed",
                    outcome="failure",
                    model_name=model_name,
                    safe_reason_code="LLM_PROVIDER_ERROR",
                )
            )
            return create_agent_response(
                correlation_id=correlation_id,
                sender=target_agent,
                recipient=request.sender,
                status="failed",
                message_type="error",
                error_code="LLM_PROVIDER_ERROR",
                safe_error_message="LLM provider is currently unavailable",
            )
        except Exception as e:
            logger.error("Unexpected error during agent execution: %s", type(e).__name__)
            await self._record_audit(
                create_llm_audit_event(
                    correlation_id=correlation_id,
                    actor_user_id=principal.user_id,
                    actor_role=principal.role,
                    agent=target_agent,
                    event_type="llm_request_failed",
                    outcome="failure",
                    model_name=model_name,
                    safe_reason_code="INTERNAL_RUNTIME_ERROR",
                )
            )
            return create_agent_response(
                correlation_id=correlation_id,
                sender=target_agent,
                recipient=request.sender,
                status="failed",
                message_type="error",
                error_code="INTERNAL_RUNTIME_ERROR",
                safe_error_message="An internal runtime error occurred during execution",
            )

        # 11. Convert LLM structured output to AgentFinding
        from backend.app.modules.agents.confidence_scorer import (
            compute_productivity_confidence_from_evidence,
            compute_collaboration_confidence, compute_collaboration_confidence_from_evidence,
            sanitize_specialist_output,
        )
        metrics = context.evidence_metrics
        wb_metrics = metrics.get("wellbeing")
        task_metrics = metrics.get("task_assignment")
        task_details = task_metrics.task_assignment_details if task_metrics else None
        if target_agent == "productivity":
            evidence_confidence = metrics.get("productivity_confidence", compute_productivity_confidence_from_evidence(final_evidence))
        elif target_agent == "collaboration":
            evidence_confidence = (
                compute_collaboration_confidence(
                    metrics.get("collaboration_messages", 0), metrics.get("collaboration_blockers", 0),
                    metrics.get("collaboration_timestamps", True) and metrics.get("collaboration_blocker_timestamps", True),
                ) if metrics or request.target_task_id else compute_collaboration_confidence_from_evidence(final_evidence)
            )
        elif target_agent == "wellbeing":
            evidence_confidence = wb_metrics.deterministic_confidence if wb_metrics else 0.0
        elif target_agent == "task_assigning":
            evidence_confidence = metrics.get("task_assignment_confidence", 0.30)
        else:
            evidence_confidence = 0.0

        if isinstance(structured_content, AgentFinding):
            finding = structured_content.model_copy(update={
                "agent": target_agent, "correlation_id": correlation_id,
                "evidence_refs": final_evidence, "task_assignment_details": task_details,
                "confidence": evidence_confidence,
            })
        elif isinstance(structured_content, StructuredAgentFindingOutput):
            finding = AgentFinding(
                agent=target_agent,
                summary=structured_content.summary,
                correlation_id=correlation_id,
                evidence_refs=final_evidence,
                confidence=evidence_confidence,
                limitations=structured_content.limitations,
                recommended_actions=structured_content.recommended_actions,
                task_assignment_details=task_details,
            )
        elif hasattr(structured_content, "summary"):
            finding = AgentFinding(
                agent=target_agent,
                summary=str(getattr(structured_content, "summary")),
                correlation_id=correlation_id,
                evidence_refs=final_evidence,
                confidence=evidence_confidence,
                limitations=list(getattr(structured_content, "limitations", [])),
                recommended_actions=list(getattr(structured_content, "recommended_actions", [])),
                task_assignment_details=task_details,
            )
        else:
            await self._record_audit(
                create_policy_audit_event(
                    correlation_id=correlation_id,
                    actor_user_id=principal.user_id,
                    actor_role=principal.role,
                    agent=target_agent,
                    event_type="output_validation_failed",
                    outcome="failure",
                    safe_reason_code="OUTPUT_SCHEMA_INVALID",
                )
            )
            return create_agent_response(
                correlation_id=correlation_id,
                sender=target_agent,
                recipient=request.sender,
                status="failed",
                message_type="error",
                error_code="OUTPUT_SCHEMA_INVALID",
                safe_error_message="LLM output schema does not conform to expected format",
            )

        # Check the original output before removing unsupported domain claims.
        raw_policy = validate_responsible_ai_guardrails(
            agent=target_agent, intent=request.intent, finding=finding,
            dependency_findings=request.dependency_findings,
        )
        if not raw_policy.allowed:
            return create_agent_response(
                correlation_id=correlation_id, sender=target_agent, recipient=request.sender,
                status="failed", message_type="error", error_code=raw_policy.safe_reason_code,
                safe_error_message=raw_policy.safe_message,
            )

        if target_agent == "task_assigning" and task_metrics:
            from backend.app.modules.agents.task_assignment import validate_task_assignment_grounding
            eligible_matches = [c for c in task_metrics.candidate_matches if c.skill_coverage_ratio == 1.0]
            ok, _ = validate_task_assignment_grounding(structured_content, eligible_matches)
            if not ok:
                # Reject the provider's candidate claims, not the verified evaluation.
                # Never log the validator's reason: it may contain candidate IDs or names.
                await self._record_audit(
                    create_policy_audit_event(
                        correlation_id=correlation_id,
                        actor_user_id=principal.user_id,
                        actor_role=principal.role,
                        agent=target_agent,
                        event_type="output_validation_failed",
                        outcome="failure",
                        safe_reason_code="OUTPUT_GROUNDING_ERROR",
                    )
                )
            # Candidate reasoning is constructed from the same deterministic data as
            # the cards. Free-form LLM rationale cannot add an unverified candidate.
            finding = finding.model_copy(update={
                "summary": task_metrics.to_summary_text()[:3000],
                "recommended_actions": task_metrics.to_manager_actions(),
                "limitations": ["Advisory only; the manager makes the final decision."],
            })

        if target_agent == "collaboration" and request.target_task_id:
            # A phrase replacement cannot ground a numerical claim (including a
            # claimed absence of blockers). Render task-scoped findings from the
            # same trusted facts used by the evidence tools and confidence scorer.
            blocker_metrics = metrics.get("collaboration_task_blocker_metrics")
            message_count = metrics.get("collaboration_messages", 0)
            scoped_summary = (
                blocker_metrics.to_task_summary_text() if blocker_metrics else
                "No verified blocker metrics for the selected task were available."
            )
            if message_count:
                scoped_summary += f" {message_count} collaboration message(s) explicitly linked to the selected task were found within the requested period."
            scoped_limitations = ["Only blockers and messages explicitly linked to the selected task were evaluated."]
            if blocker_metrics and blocker_metrics.invalid_timestamp_count:
                scoped_limitations.append("Invalid timestamps in selected-task blocker records limit resolution-time calculations.")
            if not metrics.get("collaboration_timestamps", True):
                scoped_limitations.append("Missing or invalid timestamps in selected-task messages limit time-based observations.")
            scoped_actions = [
                "Review the active blockers explicitly linked to the selected task and confirm their resolution status."
                if blocker_metrics and blocker_metrics.unresolved_blocker_count else
                "Record and review any new blockers explicitly linked to the selected task."
            ]
            if not message_count:
                scoped_actions.append("Link relevant collaboration messages explicitly to the selected task before assessing its communication evidence.")
            finding = finding.model_copy(update={
                "summary": scoped_summary, "limitations": scoped_limitations,
                "recommended_actions": scoped_actions,
            })

        from backend.app.modules.agents.grounded_reporting import grounded_specialist_update
        grounded_update = grounded_specialist_update(target_agent, context)
        if grounded_update:
            finding = finding.model_copy(update=grounded_update)
        elif target_agent == "collaboration" and not request.target_task_id:
            from backend.app.modules.agents.collaboration_reporting import validated_team_collaboration_update
            collaboration_update = validated_team_collaboration_update(finding, structured_content, context)
            if collaboration_update:
                finding = finding.model_copy(update=collaboration_update)
        elif target_agent == "productivity" and request.weeks_lookback:
            finding = finding.model_copy(update={"limitations": list(dict.fromkeys([
                *finding.limitations,
                f"The {request.weeks_lookback}-week request limits task activity dates where applicable. Productivity is a current snapshot, not historical throughput over that window.",
            ]))})

        known_ids = {principal.user_id, request.target_team_id or "", request.target_task_id or "", correlation_id}
        known_ids.add(request.conversation_id or "")
        known_ids.update(principal.managed_team_ids)
        known_ids.update(ref.record_id for ref in final_evidence)
        if task_metrics:
            known_ids.update(c.candidate_id for c in task_metrics.candidate_matches)
        if task_details:
            def public_details(value, key=""):
                if isinstance(value, str):
                    if key in ("eligibility_status", "recommendation_label"):
                        return value
                    return sanitize_public_prose(value, known_ids)
                if isinstance(value, list):
                    return [public_details(item) for item in value]
                if isinstance(value, dict):
                    return {k: public_details(item, k) for k, item in value.items()}
                return value
            task_details = type(task_details).model_validate(public_details(task_details.model_dump()))
        summary, limitations, actions = sanitize_specialist_output(
            target_agent, finding.summary, finding.limitations, finding.recommended_actions,
            target_task_id=request.target_task_id,
            is_single_week_wellbeing=target_agent == "wellbeing" and wb_metrics is not None and wb_metrics.total_privacy_safe_weeks == 1,
            task_messages_unavailable=not any(ref.source_type == "collaboration_message" for ref in final_evidence),
            known_identifiers=known_ids,
            workflow_intent=request.workflow_intent or request.intent,
        )
        finding = finding.model_copy(update={
            "summary": summary, "limitations": limitations, "recommended_actions": actions,
            # The domain scorer is authoritative; generic schema heuristics cannot
            # change its verified score based on the LLM's advisory wording.
            "confidence": evidence_confidence,
            "task_assignment_details": task_details,
        })

        # 12. Enforce output character limits (max_output_chars)
        total_output_chars = (
            len(finding.summary)
            + sum(len(a) for a in finding.recommended_actions)
            + sum(len(l) for l in finding.limitations)
        )
        if len(finding.summary) > self.config.max_output_chars or total_output_chars > self.config.max_output_chars:
            await self._record_audit(
                create_policy_audit_event(
                    correlation_id=correlation_id,
                    actor_user_id=principal.user_id,
                    actor_role=principal.role,
                    agent=target_agent,
                    event_type="output_validation_failed",
                    outcome="failure",
                    safe_reason_code="OUTPUT_SIZE_EXCEEDED",
                )
            )
            return create_agent_response(
                correlation_id=correlation_id,
                sender=target_agent,
                recipient=request.sender,
                status="failed",
                message_type="error",
                error_code="OUTPUT_SIZE_EXCEEDED",
                safe_error_message="Agent output exceeded maximum character limit",
            )

        # 13. Enforce Responsible AI Guardrails on Result Finding
        rai_res_auth = validate_responsible_ai_guardrails(
            agent=target_agent,
            intent=request.intent,
            finding=finding,
            dependency_findings=request.dependency_findings,
        )
        if not rai_res_auth.allowed:
            await self._record_audit(
                create_policy_audit_event(
                    correlation_id=correlation_id,
                    actor_user_id=principal.user_id,
                    actor_role=principal.role,
                    agent=target_agent,
                    event_type="responsible_ai_policy_applied",
                    outcome="denied",
                    safe_reason_code=rai_res_auth.safe_reason_code,
                )
            )
            return create_agent_response(
                correlation_id=correlation_id,
                sender=target_agent,
                recipient=request.sender,
                status="failed",
                message_type="error",
                error_code=rai_res_auth.safe_reason_code,
                safe_error_message=rai_res_auth.safe_message,
            )

        # 14. Construct Completed Response
        return create_agent_response(
            correlation_id=correlation_id,
            sender=target_agent,
            recipient=request.sender,
            status="completed",
            finding=finding,
        )

    async def execute_many(
        self,
        executions: list[tuple[AgentRequest, AuthenticatedPrincipal]],
        tool_names_map: dict[str, list[str]] | None = None,
        fail_fast: bool = False,
    ) -> list[AgentResponse]:
        """
        Executes multiple independent AgentRequests concurrently with bounded concurrency.
        Preserves input order in results and enforces independent security checks per item.
        When fail_fast is True, cancels and awaits all remaining pending tasks upon failure.
        """
        if not executions:
            return []

        semaphore = asyncio.Semaphore(self.config.max_concurrent_executions)

        async def _run_one(
            idx: int, req: AgentRequest, princ: AuthenticatedPrincipal
        ) -> tuple[int, AgentResponse]:
            async with semaphore:
                tools = (
                    tool_names_map.get(req.recipient)
                    if tool_names_map and req.recipient in tool_names_map
                    else None
                )
                res = await self.execute_agent(req, princ, tool_names=tools)
                if fail_fast and res.status == "failed":
                    raise AgentRuntimeError(
                        f"Execution failed for agent '{req.recipient}': {res.safe_error_message}",
                        safe_reason_code=res.error_code or "EXECUTION_FAILED",
                        safe_message=res.safe_error_message,
                    )
                return idx, res

        tasks = [
            asyncio.create_task(_run_one(i, req, princ))
            for i, (req, princ) in enumerate(executions)
        ]

        try:
            results = await asyncio.gather(*tasks)
            results.sort(key=lambda x: x[0])
            return [res for _, res in results]
        except Exception:
            for t in tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    async def _record_audit(self, event: AgentAuditEvent) -> None:
        try:
            await self.audit_sink.record_event(event)
        except Exception as e:
            logger.warning("Failed to record agent audit event: %s", type(e).__name__)


# =========================================================================
# 6. Deterministic Fake Runtime Test Double
# =========================================================================


class FakeAgentRuntime(AgentRuntime):
    """
    Deterministic offline test double for unit and integration tests.
    Matches the exact validation rules and interfaces of AgentRuntime without network access.
    """

    def __init__(
        self,
        config: AgentRuntimeConfig | None = None,
        default_finding: AgentFinding | StructuredAgentFindingOutput | None = None,
        audit_sink: AgentAuditSink | None = None,
        handler: Callable[..., Any] | None = None,
    ):
        if default_finding is not None:
            if isinstance(default_finding, AgentFinding):
                default_resp: BaseModel = StructuredAgentFindingOutput(
                    summary=default_finding.summary,
                    confidence=default_finding.confidence,
                    limitations=default_finding.limitations,
                    recommended_actions=default_finding.recommended_actions,
                )
            else:
                default_resp = default_finding
        else:
            default_resp = None

        fake_gw = FakeLLMGateway(default_response=default_resp, handler=handler)
        sink = audit_sink or InMemoryAgentAuditSink()
        super().__init__(config=config, llm_gateway=fake_gw, audit_sink=sink)
        self.default_finding = default_finding

    @property
    def in_memory_audit_sink(self) -> InMemoryAgentAuditSink | None:
        if isinstance(self.audit_sink, InMemoryAgentAuditSink):
            return self.audit_sink
        return None
