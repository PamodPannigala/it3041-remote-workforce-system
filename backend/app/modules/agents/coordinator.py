import asyncio
from datetime import datetime, timezone
import logging
from typing import Annotated, Any, Literal
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
from backend.app.modules.agents.collaboration_agent import (
    get_collaboration_tool_names,
    register_collaboration_agent,
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
    create_production_llm_gateway,
)
from backend.app.modules.agents.productivity import (
    get_productivity_tool_name,
    register_productivity_agent,
)
from backend.app.modules.agents.protocol import (
    AgentFinding,
    AgentIntent,
    AgentName,
    AgentRequest,
    AgentResponse,
    EvidenceReference,
    EvidenceSourceType,
    ResponseStatus,
    create_agent_request,
    create_agent_response,
)
from backend.app.modules.agents.runtime import (
    AgentAuthorizationError,
    AgentCapabilityError,
    AgentConfigError,
    AgentDefinition,
    AgentRuntime,
    AgentRuntimeConfig,
    AgentRuntimeError,
    AgentTimeoutError,
    StructuredAgentFindingOutput,
)
from backend.app.modules.agents.security_policy import (
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
from backend.app.modules.agents.task_assignment import (
    get_task_assignment_tool_names,
    register_task_assignment_agent,
)
from backend.app.modules.agents.wellbeing import (
    get_wellbeing_tool_names,
    register_wellbeing_agent,
)

logger = logging.getLogger("remote_workforce.agents.coordinator")

COORDINATOR_AGENT_NAME: AgentName = "coordinator"
DEFAULT_COORDINATOR_TIMEOUT_SECONDS: float = 30.0

COORDINATOR_SYSTEM_PROMPT = """You are the Central Coordinator and Orchestrator Agent for the Remote Workforce System.
Your responsibility is to analyze, consolidate, and synthesize findings from specialized domain agents:
- Productivity Specialist (task throughput, velocity, completion, bottlenecks)
- Collaboration Specialist (cross-functional communication, blocker discussions, response latency)
- Well-being Specialist (aggregated team pulse metrics, burnout indicators, workload balance)
- Task Assignment Specialist (skill-based candidate recommendations, workload-balanced allocation)

CRITICAL RESPONSIBILITIES & CONSTRAINTS:
1. Synthesize multi-agent findings into a cohesive, actionable executive summary.
2. Formulate high-impact, balanced recommendations that respect employee privacy and wellbeing.
3. Explicitly state limitations, data boundaries, and areas requiring human judgment.
4. Strictly forbid punitive measures, individual blame, termination advice, or disciplinary ranking.
5. Uphold strict privacy boundaries: never expose raw pulse survey responses or private communication snippets.
6. All recommendations are advisory and require human manager review and approval."""


def _ensure_utc(v: datetime | None) -> datetime:
    if v is None:
        return datetime.now(timezone.utc)
    if v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v.astimezone(timezone.utc)


def _validate_uuid_str(v: Any, field_name: str = "correlation_id") -> str:
    if v is None:
        raise ValueError(f"{field_name} is required")
    s = str(v).strip()
    try:
        val_uuid = uuid.UUID(s)
        return str(val_uuid)
    except (ValueError, TypeError, AttributeError):
        raise ValueError(f"Invalid {field_name} format: '{v}' is not a valid UUID")


# =========================================================================
# 1. Coordinator Request and Result Contracts
# =========================================================================


class CoordinatorExecutionRequest(BaseModel):
    """
    Validated request envelope for orchestrating specialist agent execution.
    """

    model_config = ConfigDict(extra="forbid")

    correlation_id: str
    intent: AgentIntent
    authenticated_principal: AuthenticatedPrincipal
    question: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
    ]
    target_team_id: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=64),
    ] | None = None
    target_task_id: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=64),
    ] | None = None
    evidence_refs: list[EvidenceReference] = Field(
        default_factory=list,
        max_length=50,
    )
    dependency_findings: list[AgentFinding] = Field(
        default_factory=list,
        max_length=20,
    )
    conversation_id: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=64),
    ] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("correlation_id", mode="before")
    @classmethod
    def validate_correlation_id(cls, v):
        return _validate_uuid_str(v, "correlation_id")

    @field_validator("created_at", mode="before")
    @classmethod
    def validate_created_at(cls, v):
        return _ensure_utc(v)

    @model_validator(mode="after")
    def validate_dependency_constraints(self) -> "CoordinatorExecutionRequest":
        # Strict Well-being to Task Assignment data flow rejection
        if self.intent == "task_assignment_recommendation":
            for dep in self.dependency_findings:
                if dep.agent == "wellbeing":
                    raise ValueError(
                        "Wellbeing findings cannot be supplied as dependencies for task assignment recommendations"
                    )
                if dep.agent not in ("productivity", "collaboration"):
                    raise ValueError(
                        f"Agent '{dep.agent}' findings cannot be supplied as dependencies for task assignment recommendations"
                    )
        # Correlation ID consistency check
        for dep in self.dependency_findings:
            if dep.correlation_id and dep.correlation_id != self.correlation_id:
                raise ValueError(
                    f"Dependency finding correlation_id '{dep.correlation_id}' "
                    f"does not match request correlation_id '{self.correlation_id}'"
                )
        return self


class CoordinatorExecutionResult(BaseModel):
    """
    Validated result of coordinator orchestration containing specialist findings,
    synthesized executive finding, execution status, and safe error details.
    """

    model_config = ConfigDict(extra="forbid")

    correlation_id: str
    intent: AgentIntent
    status: ResponseStatus
    findings: list[AgentFinding] = Field(default_factory=list)
    synthesized_finding: AgentFinding | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)
    safe_error_message: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=500),
    ] | None = None
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("correlation_id", mode="before")
    @classmethod
    def validate_correlation_id(cls, v):
        return _validate_uuid_str(v, "correlation_id")

    @field_validator("executed_at", mode="before")
    @classmethod
    def validate_executed_at(cls, v):
        return _ensure_utc(v)


# =========================================================================
# 2. Coordinator Agent Definition
# =========================================================================


def create_coordinator_agent_definition(
    timeout_seconds: float = DEFAULT_COORDINATOR_TIMEOUT_SECONDS,
) -> AgentDefinition:
    """Creates the immutable AgentDefinition for the Coordinator."""
    return AgentDefinition(
        name=COORDINATOR_AGENT_NAME,
        role="Central multi-agent coordinator and synthesis orchestrator",
        goal="Route intents to specialist agents, enforce safety policies, and synthesize multi-agent findings",
        allowed_intents=AGENT_ALLOWED_INTENTS["coordinator"],
        allowed_evidence_sources={
            "task",
            "collaboration_message",
            "pulse_summary",
            "employee_profile",
            "agent_finding",
        },
        system_prompt=COORDINATOR_SYSTEM_PROMPT,
        response_model=StructuredAgentFindingOutput,
        timeout_seconds=timeout_seconds,
    )


def register_coordinator_agent(
    runtime: AgentRuntime,
    timeout_seconds: float = DEFAULT_COORDINATOR_TIMEOUT_SECONDS,
) -> None:
    """Registers the Coordinator Agent definition with the runtime."""
    agent_def = create_coordinator_agent_definition(timeout_seconds=timeout_seconds)
    runtime.register_agent(agent_def)


# =========================================================================
# 3. Intent Routing Map
# =========================================================================

# Declarative dispatch map: intent -> tuple of (target_agent, specialist_sub_intent)
INTENT_SPECIALIST_DISPATCH: dict[AgentIntent, tuple[tuple[AgentName, AgentIntent], ...]] = {
    "productivity_analysis": (("productivity", "productivity_analysis"),),
    "collaboration_analysis": (("collaboration", "collaboration_analysis"),),
    "wellbeing_analysis": (("wellbeing", "wellbeing_analysis"),),
    "task_assignment_recommendation": (("task_assigning", "task_assignment_recommendation"),),
    "task_delay_analysis": (
        ("productivity", "task_delay_analysis"),
        ("collaboration", "task_delay_analysis"),
    ),
    "team_workload_analysis": (
        ("productivity", "team_workload_analysis"),
        ("wellbeing", "team_workload_analysis"),
    ),
    "general_workforce_question": (
        ("productivity", "productivity_analysis"),
        ("collaboration", "collaboration_analysis"),
        ("wellbeing", "wellbeing_analysis"),
    ),
}

INTENT_SPECIALIST_ROUTING: dict[AgentIntent, tuple[AgentName, ...]] = {
    k: tuple(agent for agent, _ in v) for k, v in INTENT_SPECIALIST_DISPATCH.items()
}


# =========================================================================
# 4. AgentCoordinator Orchestrator
# =========================================================================


class AgentCoordinator:
    """
    Central Coordinator / Orchestrator for the custom multi-agent runtime.

    Key Guarantees:
    1. Intent-to-Specialist Routing: Routes single or multi-specialist requests safely.
    2. Policy & Authorization: Validates user intent, role, team scope, and agent capabilities.
    3. Concurrency: Executes independent specialist agents concurrently with bounded limits.
    4. Dependency Ordering: Validates prerequisite findings before passing downstream.
    5. Well-being Isolation: Strictly rejects Well-being findings flowing to Task Assignment at all layers.
    6. Resilience & Bounded Timeouts: Applies whole-execution and per-agent timeouts, returning partial safe results.
    7. Privacy & Audit: Enforces zero prompt/PII/secret leakage into audit logs.
    8. Advisory Only: Performs zero database writes or automatic task mutations.
    """

    def __init__(
        self,
        runtime: AgentRuntime,
        llm_gateway: LLMGateway | None = None,
        audit_sink: AgentAuditSink | None = None,
        config: AgentRuntimeConfig | None = None,
        default_timeout_seconds: float = DEFAULT_COORDINATOR_TIMEOUT_SECONDS,
    ):
        self.runtime = runtime
        self.llm_gateway = llm_gateway or runtime.llm_gateway
        self.audit_sink = audit_sink or runtime.audit_sink
        self.config = config or runtime.config
        self.default_timeout_seconds = default_timeout_seconds

    async def orchestrate(
        self,
        request: CoordinatorExecutionRequest,
    ) -> CoordinatorExecutionResult:
        """
        Main orchestration entry point: validates authorization, executes specialists,
        and synthesizes results under an overall bounded timeout.
        """
        correlation_id = request.correlation_id
        principal = request.authenticated_principal
        intent = request.intent

        # 1. Authorize User Intent and Team Scope
        user_auth = authorize_user_intent(
            principal=principal,
            intent=intent,
            target_team_id=request.target_team_id,
        )
        if not user_auth.allowed:
            await self._record_audit(
                create_authorization_audit_event(
                    correlation_id=correlation_id,
                    actor_user_id=principal.user_id,
                    actor_role=principal.role,
                    agent=COORDINATOR_AGENT_NAME,
                    allowed=False,
                    safe_reason_code=user_auth.safe_reason_code,
                    intent=intent,
                )
            )
            return CoordinatorExecutionResult(
                correlation_id=correlation_id,
                intent=intent,
                status="failed",
                safe_error_message=user_auth.safe_message,
                errors=[
                    {
                        "agent": COORDINATOR_AGENT_NAME,
                        "error_code": user_auth.safe_reason_code,
                        "message": user_auth.safe_message,
                    }
                ],
            )

        # 2. Validate Evidence Team Scopes (Defense-in-depth)
        for ev_ref in request.evidence_refs:
            scope_auth = validate_evidence_team_scope(principal, ev_ref)
            if not scope_auth.allowed:
                await self._record_audit(
                    create_policy_audit_event(
                        correlation_id=correlation_id,
                        actor_user_id=principal.user_id,
                        actor_role=principal.role,
                        agent=COORDINATOR_AGENT_NAME,
                        event_type="responsible_ai_policy_applied",
                        outcome="denied",
                        safe_reason_code=scope_auth.safe_reason_code,
                    )
                )
                return CoordinatorExecutionResult(
                    correlation_id=correlation_id,
                    intent=intent,
                    status="failed",
                    safe_error_message=scope_auth.safe_message,
                    errors=[
                        {
                            "agent": COORDINATOR_AGENT_NAME,
                            "error_code": scope_auth.safe_reason_code,
                            "message": scope_auth.safe_message,
                        }
                    ],
                )

        # 3. Validate Dependency Findings & Strict Wellbeing Isolation
        if request.dependency_findings:
            if intent == "task_assignment_recommendation":
                for dep in request.dependency_findings:
                    if dep.agent == "wellbeing":
                        await self._record_audit(
                            create_policy_audit_event(
                                correlation_id=correlation_id,
                                actor_user_id=principal.user_id,
                                actor_role=principal.role,
                                agent=COORDINATOR_AGENT_NAME,
                                event_type="responsible_ai_policy_applied",
                                outcome="denied",
                                safe_reason_code="WELLBEING_TASK_ASSIGNMENT_FORBIDDEN",
                            )
                        )
                        return CoordinatorExecutionResult(
                            correlation_id=correlation_id,
                            intent=intent,
                            status="failed",
                            safe_error_message="Wellbeing findings cannot be supplied as dependencies for task assignment",
                            errors=[
                                {
                                    "agent": COORDINATOR_AGENT_NAME,
                                    "error_code": "WELLBEING_TASK_ASSIGNMENT_FORBIDDEN",
                                    "message": "Wellbeing findings cannot be supplied as dependencies for task assignment",
                                }
                            ],
                        )
                    if dep.agent not in ("productivity", "collaboration"):
                        await self._record_audit(
                            create_policy_audit_event(
                                correlation_id=correlation_id,
                                actor_user_id=principal.user_id,
                                actor_role=principal.role,
                                agent=COORDINATOR_AGENT_NAME,
                                event_type="responsible_ai_policy_applied",
                                outcome="denied",
                                safe_reason_code="DEPENDENCY_FLOW_FORBIDDEN",
                            )
                        )
                        return CoordinatorExecutionResult(
                            correlation_id=correlation_id,
                            intent=intent,
                            status="failed",
                            safe_error_message=f"Agent '{dep.agent}' cannot supply dependencies for task assignment",
                            errors=[
                                {
                                    "agent": COORDINATOR_AGENT_NAME,
                                    "error_code": "DEPENDENCY_FLOW_FORBIDDEN",
                                    "message": f"Agent '{dep.agent}' cannot supply dependencies for task assignment",
                                }
                            ],
                        )

            # Validate dependency flow and correlation ID
            for dep in request.dependency_findings:
                flow_auth = validate_dependency_flow(
                    sender=dep.agent,
                    recipient="coordinator",
                    dependency_findings=[dep],
                    expected_correlation_id=correlation_id,
                )
                if not flow_auth.allowed:
                    await self._record_audit(
                        create_policy_audit_event(
                            correlation_id=correlation_id,
                            actor_user_id=principal.user_id,
                            actor_role=principal.role,
                            agent=COORDINATOR_AGENT_NAME,
                            event_type="responsible_ai_policy_applied",
                            outcome="denied",
                            safe_reason_code=flow_auth.safe_reason_code,
                        )
                    )
                    return CoordinatorExecutionResult(
                        correlation_id=correlation_id,
                        intent=intent,
                        status="failed",
                        safe_error_message=flow_auth.safe_message,
                        errors=[
                            {
                                "agent": COORDINATOR_AGENT_NAME,
                                "error_code": flow_auth.safe_reason_code,
                                "message": flow_auth.safe_message,
                            }
                        ],
                    )

        # 4. Record Successful Coordinator Dispatch Audit Event
        await self._record_audit(
            create_authorization_audit_event(
                correlation_id=correlation_id,
                actor_user_id=principal.user_id,
                actor_role=principal.role,
                agent=COORDINATOR_AGENT_NAME,
                allowed=True,
                safe_reason_code="COORDINATOR_AUTHORIZED",
                intent=intent,
            )
        )

        # 5. Execute Specialists under Overall Timeout with Clean Task Cleanup
        dispatch_task = asyncio.create_task(self._dispatch_and_synthesize(request))
        try:
            return await asyncio.wait_for(
                asyncio.shield(dispatch_task),
                timeout=self.default_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Coordinator execution timed out for correlation_id=%s intent=%s",
                correlation_id,
                intent,
            )
            # Ensure background execution is cancelled cleanly
            if not dispatch_task.done():
                dispatch_task.cancel()
                try:
                    await dispatch_task
                except (asyncio.CancelledError, Exception):
                    pass

            model_name = str(getattr(self.llm_gateway, "model", "default-llm"))
            await self._record_audit(
                create_llm_audit_event(
                    correlation_id=correlation_id,
                    actor_user_id=principal.user_id,
                    actor_role=principal.role,
                    agent=COORDINATOR_AGENT_NAME,
                    event_type="llm_request_failed",
                    outcome="failure",
                    model_name=model_name,
                    safe_reason_code="EXECUTION_TIMEOUT",
                )
            )
            return CoordinatorExecutionResult(
                correlation_id=correlation_id,
                intent=intent,
                status="failed",
                safe_error_message="Coordinator execution exceeded timeout limit",
                errors=[
                    {
                        "agent": COORDINATOR_AGENT_NAME,
                        "error_code": "EXECUTION_TIMEOUT",
                        "message": "Coordinator execution exceeded timeout limit",
                    }
                ],
            )

    async def _dispatch_and_synthesize(
        self,
        request: CoordinatorExecutionRequest,
    ) -> CoordinatorExecutionResult:
        correlation_id = request.correlation_id
        principal = request.authenticated_principal
        intent = request.intent

        dispatch_items = INTENT_SPECIALIST_DISPATCH.get(intent)
        if not dispatch_items:
            return CoordinatorExecutionResult(
                correlation_id=correlation_id,
                intent=intent,
                status="failed",
                safe_error_message=f"No specialist agents configured for intent '{intent}'",
                errors=[
                    {
                        "agent": COORDINATOR_AGENT_NAME,
                        "error_code": "UNSUPPORTED_INTENT",
                        "message": f"Intent '{intent}' has no registered specialists",
                    }
                ],
            )

        # Single-specialist direct execution
        if len(dispatch_items) == 1:
            target_agent, specialist_intent = dispatch_items[0]
            resp = await self._execute_single_specialist(
                target_agent=target_agent,
                specialist_intent=specialist_intent,
                request=request,
            )

            if resp.status == "completed" and resp.finding:
                return CoordinatorExecutionResult(
                    correlation_id=correlation_id,
                    intent=intent,
                    status="completed",
                    findings=[resp.finding],
                    synthesized_finding=resp.finding,
                )
            else:
                return CoordinatorExecutionResult(
                    correlation_id=correlation_id,
                    intent=intent,
                    status="failed",
                    safe_error_message=resp.safe_error_message or "Specialist agent execution failed",
                    errors=[
                        {
                            "agent": target_agent,
                            "error_code": resp.error_code or "EXECUTION_FAILED",
                            "message": resp.safe_error_message or "Specialist agent failed",
                        }
                    ],
                )

        # Multi-specialist concurrent execution with cancellation safety
        tasks = [
            asyncio.create_task(
                self._execute_single_specialist(
                    target_agent=agent_name,
                    specialist_intent=spec_intent,
                    request=request,
                )
            )
            for agent_name, spec_intent in dispatch_items
        ]

        try:
            responses = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception:
            for t in tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

        successful_findings: list[AgentFinding] = []
        errors: list[dict[str, Any]] = []

        for (agent_name, _), res in zip(dispatch_items, responses):
            if isinstance(res, Exception):
                logger.warning(
                    "Specialist '%s' raised exception: %s",
                    agent_name,
                    res,
                )
                errors.append(
                    {
                        "agent": agent_name,
                        "error_code": "EXCEPTION",
                        "message": "Specialist execution failed due to an exception",
                    }
                )
            elif isinstance(res, AgentResponse):
                if res.status == "completed" and res.finding is not None:
                    successful_findings.append(res.finding)
                else:
                    errors.append(
                        {
                            "agent": agent_name,
                            "error_code": res.error_code or "EXECUTION_FAILED",
                            "message": res.safe_error_message or "Specialist failed",
                        }
                    )
            else:
                errors.append(
                    {
                        "agent": agent_name,
                        "error_code": "UNKNOWN_RESPONSE",
                        "message": "Invalid response type received from specialist",
                    }
                )

        # Failure Behavior:
        # All failed -> status: "failed"
        if not successful_findings:
            return CoordinatorExecutionResult(
                correlation_id=correlation_id,
                intent=intent,
                status="failed",
                safe_error_message="All targeted specialist agents failed to execute",
                errors=errors,
            )

        # Synthesize successful findings
        synthesized_finding = await self._synthesize_findings(
            request=request,
            findings=successful_findings,
        )

        all_findings = list(successful_findings)
        if synthesized_finding:
            all_findings.append(synthesized_finding)

        # If any specialist failed -> status: "partial", else "completed"
        final_status: ResponseStatus = "partial" if errors else "completed"
        safe_err_msg = (
            f"{len(errors)} of {len(dispatch_items)} specialist agents encountered issues"
            if errors
            else None
        )

        return CoordinatorExecutionResult(
            correlation_id=correlation_id,
            intent=intent,
            status=final_status,
            findings=all_findings,
            synthesized_finding=synthesized_finding or (successful_findings[0] if successful_findings else None),
            errors=errors,
            safe_error_message=safe_err_msg,
        )

    async def _execute_single_specialist(
        self,
        target_agent: AgentName,
        specialist_intent: AgentIntent,
        request: CoordinatorExecutionRequest,
    ) -> AgentResponse:
        correlation_id = request.correlation_id
        principal = request.authenticated_principal

        # Validate agent capability for this intent
        cap_auth = validate_agent_capability(target_agent, specialist_intent)
        if not cap_auth.allowed:
            return create_agent_response(
                correlation_id=correlation_id,
                sender=target_agent,
                recipient=COORDINATOR_AGENT_NAME,
                status="failed",
                message_type="error",
                error_code=cap_auth.safe_reason_code,
                safe_error_message=cap_auth.safe_message,
            )

        # Enforce Task Assignment dependency boundaries
        prereq_deps = list(request.dependency_findings)
        if target_agent == "task_assigning" and prereq_deps:
            for dep in prereq_deps:
                if dep.agent == "wellbeing":
                    return create_agent_response(
                        correlation_id=correlation_id,
                        sender=target_agent,
                        recipient=COORDINATOR_AGENT_NAME,
                        status="failed",
                        message_type="error",
                        error_code="WELLBEING_TASK_ASSIGNMENT_FORBIDDEN",
                        safe_error_message="Wellbeing findings cannot be supplied as dependencies to Task Assigning Agent",
                    )
                if dep.agent not in ("productivity", "collaboration"):
                    return create_agent_response(
                        correlation_id=correlation_id,
                        sender=target_agent,
                        recipient=COORDINATOR_AGENT_NAME,
                        status="failed",
                        message_type="error",
                        error_code="DEPENDENCY_FLOW_FORBIDDEN",
                        safe_error_message=f"Agent '{dep.agent}' cannot supply dependencies to Task Assigning Agent",
                    )

        # Validate dependency flow from coordinator to specialist
        dep_flow_auth = validate_dependency_flow(
            sender=COORDINATOR_AGENT_NAME,
            recipient=target_agent,
            dependency_findings=prereq_deps,
            expected_correlation_id=correlation_id,
        )
        if not dep_flow_auth.allowed:
            return create_agent_response(
                correlation_id=correlation_id,
                sender=target_agent,
                recipient=COORDINATOR_AGENT_NAME,
                status="failed",
                message_type="error",
                error_code=dep_flow_auth.safe_reason_code,
                safe_error_message=dep_flow_auth.safe_message,
            )

        # Build standard AgentRequest envelope
        agent_req = create_agent_request(
            correlation_id=correlation_id,
            sender=COORDINATOR_AGENT_NAME,
            recipient=target_agent,
            intent=specialist_intent,
            authenticated_user_id=principal.user_id,
            question=request.question,
            conversation_id=request.conversation_id,
            evidence_refs=request.evidence_refs,
            dependency_findings=prereq_deps,
        )

        # Resolve explicit canonical tool names for target agent
        tool_names = self._resolve_specialist_tools(target_agent, specialist_intent)

        # Record dispatch audit event
        await self._record_audit(
            create_agent_dispatch_audit_event(
                correlation_id=correlation_id,
                actor_user_id=principal.user_id,
                actor_role=principal.role,
                sender=COORDINATOR_AGENT_NAME,
                recipient=target_agent,
                intent=specialist_intent,
            )
        )

        # Execute via runtime
        return await self.runtime.execute_agent(
            request=agent_req,
            principal=principal,
            tool_names=tool_names,
        )

    def _resolve_specialist_tools(
        self,
        agent: AgentName,
        intent: AgentIntent,
    ) -> list[str] | None:
        """Resolves registered explicit tool names for specialist execution."""
        candidate_tools: list[str] = []
        if agent == "productivity":
            candidate_tools = [get_productivity_tool_name(intent)]
        elif agent == "collaboration":
            candidate_tools = get_collaboration_tool_names(intent)
        elif agent == "wellbeing":
            candidate_tools = get_wellbeing_tool_names(intent)
        elif agent == "task_assigning":
            candidate_tools = get_task_assignment_tool_names(intent)

        # Only pass tools that are actually registered in runtime
        registered = [t for t in candidate_tools if t in self.runtime._tools]
        return registered if registered else None

    async def _synthesize_findings(
        self,
        request: CoordinatorExecutionRequest,
        findings: list[AgentFinding],
    ) -> AgentFinding | None:
        """
        Synthesizes multiple specialist findings into a unified, balanced executive analysis.
        Enforces Responsible AI guardrails and falls back to deterministic aggregation on failure.
        """
        if not findings:
            return None

        if len(findings) == 1:
            return findings[0]

        correlation_id = request.correlation_id
        principal = request.authenticated_principal

        # Aggregate evidence references from all specialists
        aggregated_evidence: list[EvidenceReference] = []
        seen_records: set[tuple[str, str]] = set()
        for f in findings:
            for ev in f.evidence_refs:
                key = (ev.source_type, ev.record_id)
                if key not in seen_records:
                    seen_records.add(key)
                    aggregated_evidence.append(ev)

        # Format input prompt for coordinator LLM synthesis
        finding_blocks = []
        for f in findings:
            finding_blocks.append(
                f"SPECIALIST AGENT: {f.agent}\n"
                f"CONFIDENCE: {f.confidence:.2f}\n"
                f"SUMMARY: {f.summary}\n"
                f"LIMITATIONS:\n" + "\n".join(f"- {l}" for l in f.limitations) + "\n"
                f"RECOMMENDED ACTIONS:\n" + "\n".join(f"- {r}" for r in f.recommended_actions)
            )
        context = "\n\n".join(finding_blocks)

        user_prompt = (
            f"ORIGINAL USER QUESTION / INSTRUCTION:\n{request.question}\n\n"
            f"SPECIALIST AGENT FINDINGS:\n{context}\n\n"
            "Synthesize these findings into a unified, balanced executive analysis with summary, confidence, "
            "limitations, and recommended_actions. Do not output internal chain-of-thought."
        )

        try:
            llm_result = await self.llm_gateway.generate_structured(
                system_prompt=COORDINATOR_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_model=StructuredAgentFindingOutput,
                correlation_id=correlation_id,
            )

            synth_content = llm_result.content
            synth_finding = AgentFinding(
                agent=COORDINATOR_AGENT_NAME,
                summary=synth_content.summary,
                correlation_id=correlation_id,
                evidence_refs=aggregated_evidence,
                confidence=synth_content.confidence,
                limitations=synth_content.limitations,
                recommended_actions=synth_content.recommended_actions,
            )

            # Responsible AI Guardrails Validation
            rai_auth = validate_responsible_ai_guardrails(
                agent=COORDINATOR_AGENT_NAME,
                intent=request.intent,
                finding=synth_finding,
                dependency_findings=findings,
            )
            if not rai_auth.allowed:
                logger.warning(
                    "Coordinator synthesis failed RAI validation: %s",
                    rai_auth.safe_reason_code,
                )
                return self._deterministic_fallback_synthesis(
                    correlation_id=correlation_id,
                    intent=request.intent,
                    findings=findings,
                    evidence_refs=aggregated_evidence,
                )

            return synth_finding

        except Exception as exc:
            logger.warning(
                "Coordinator LLM synthesis encountered error: %s. Using deterministic fallback.",
                exc,
            )
            return self._deterministic_fallback_synthesis(
                correlation_id=correlation_id,
                intent=request.intent,
                findings=findings,
                evidence_refs=aggregated_evidence,
            )

    def _deterministic_fallback_synthesis(
        self,
        correlation_id: str,
        intent: AgentIntent,
        findings: list[AgentFinding],
        evidence_refs: list[EvidenceReference],
    ) -> AgentFinding:
        """Deterministic, safe fallback synthesis when LLM generation is unavailable."""
        summaries = [f"[{f.agent.upper()} ANALYSIS]: {f.summary}" for f in findings]
        limitations: list[str] = []
        recommendations: list[str] = []

        for f in findings:
            for l in f.limitations:
                if l not in limitations:
                    limitations.append(l)
            for r in f.recommended_actions:
                if r not in recommendations:
                    recommendations.append(r)

        avg_confidence = (
            sum(f.confidence for f in findings) / len(findings)
            if findings
            else 0.5
        )

        finding = AgentFinding(
            agent=COORDINATOR_AGENT_NAME,
            summary="\n\n".join(summaries),
            correlation_id=correlation_id,
            evidence_refs=evidence_refs,
            confidence=round(min(max(avg_confidence, 0.0), 1.0), 2),
            limitations=limitations[:20],
            recommended_actions=recommendations[:20],
        )

        return finding

    async def _record_audit(self, event: AgentAuditEvent) -> None:
        try:
            await self.audit_sink.record_event(event)
        except Exception as e:
            logger.warning("Failed to record coordinator audit event: %s", e)


# =========================================================================
# 5. Production Factory
# =========================================================================


def create_production_coordinator(
    database: Any = None,
    llm_gateway: LLMGateway | None = None,
    audit_sink: AgentAuditSink | None = None,
    config: AgentRuntimeConfig | None = None,
    default_timeout_seconds: float = DEFAULT_COORDINATOR_TIMEOUT_SECONDS,
) -> AgentCoordinator:
    """
    Factory creating a fully configured, production-ready AgentCoordinator.
    Instantiates the production LLM gateway via create_production_llm_gateway()
    and registers all specialist agents into a clean AgentRuntime.
    """
    selected_gw = llm_gateway or create_production_llm_gateway()
    selected_sink = audit_sink or SafeLoggingAgentAuditSink()
    selected_config = config or AgentRuntimeConfig()

    runtime = AgentRuntime(
        config=selected_config,
        llm_gateway=selected_gw,
        audit_sink=selected_sink,
    )

    # Register Coordinator Definition
    register_coordinator_agent(runtime, timeout_seconds=default_timeout_seconds)

    # Register all Specialists
    register_productivity_agent(runtime, database=database)
    register_collaboration_agent(runtime, database=database)
    register_wellbeing_agent(runtime, database=database)
    register_task_assignment_agent(runtime, database=database)

    return AgentCoordinator(
        runtime=runtime,
        llm_gateway=selected_gw,
        audit_sink=selected_sink,
        config=selected_config,
        default_timeout_seconds=default_timeout_seconds,
    )
