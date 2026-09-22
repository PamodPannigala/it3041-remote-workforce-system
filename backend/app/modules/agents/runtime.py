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
        user_auth = authorize_user_intent(principal, request.intent)
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
                except Exception as e:
                    logger.warning("Tool %s execution failed: %s", t_name, e)
                    await self._record_audit(
                        create_policy_audit_event(
                            correlation_id=correlation_id,
                            actor_user_id=principal.user_id,
                            actor_role=principal.role,
                            agent=target_agent,
                            event_type="responsible_ai_policy_applied",
                            outcome="failure",
                            safe_reason_code="TOOL_EXECUTION_FAILURE",
                        )
                    )
                    return create_agent_response(
                        correlation_id=correlation_id,
                        sender=target_agent,
                        recipient=request.sender,
                        status="failed",
                        message_type="error",
                        error_code="TOOL_EXECUTION_FAILURE",
                        safe_error_message=f"Execution of tool '{t_name}' failed",
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
            logger.exception("Unexpected error during agent execution: %s", type(e).__name__)
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
        structured_content = llm_result.content
        if isinstance(structured_content, AgentFinding):
            finding = structured_content
        elif isinstance(structured_content, StructuredAgentFindingOutput):
            finding = AgentFinding(
                agent=target_agent,
                summary=structured_content.summary,
                correlation_id=correlation_id,
                evidence_refs=final_evidence,
                confidence=structured_content.confidence,
                limitations=structured_content.limitations,
                recommended_actions=structured_content.recommended_actions,
            )
        elif hasattr(structured_content, "summary"):
            finding = AgentFinding(
                agent=target_agent,
                summary=str(getattr(structured_content, "summary")),
                correlation_id=correlation_id,
                evidence_refs=final_evidence,
                confidence=float(getattr(structured_content, "confidence", 1.0)),
                limitations=list(getattr(structured_content, "limitations", [])),
                recommended_actions=list(getattr(structured_content, "recommended_actions", [])),
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
            logger.warning("Failed to record agent audit event: %s", e)


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
