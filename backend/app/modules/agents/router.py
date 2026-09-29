import asyncio
from datetime import datetime, timezone
import logging
from typing import Annotated, Any, Literal
import uuid

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from backend.app.api.dependencies import get_current_user
from backend.app.modules.agents.coordinator import (
    AgentCoordinator,
    CoordinatorExecutionRequest,
    CoordinatorExecutionResult,
    create_production_coordinator,
)
from backend.app.modules.agents.llm_gateway import LLMConfigurationError
from backend.app.modules.agents.confidence_scorer import is_prohibited_request
from backend.app.modules.agents.protocol import (
    AgentIntent,
    AgentName,
    ResponseStatus,
    TaskAssignmentDetails,
)
from backend.app.modules.agents.security_policy import (
    ADMIN_ALLOWED_INTENTS,
    EMPLOYEE_ALLOWED_INTENTS,
    MANAGER_ALLOWED_INTENTS,
    INTENT_CONTEXT_RELEVANCE_MATRIX,
    AuthenticatedPrincipal,
    ContextFieldRelevance,
    PrincipalRole,
    get_allowed_intents_for_role,
    sanitize_public_prose,
)

logger = logging.getLogger("remote_workforce.agents.router")

class ProhibitedAnalysisRequest(HTTPException):
    def __init__(self, correlation_id: str):
        super().__init__(403, "This request cannot be analysed. Please ask a workforce question using authorized team evidence.")
        self.correlation_id = correlation_id


class AnalysisExecutionFailure(HTTPException):
    """Carries only server-owned routing metadata across HTTP failure mapping."""

    def __init__(self, status_code: int, detail: str, result: CoordinatorExecutionResult):
        super().__init__(status_code, detail)
        self.correlation_id = result.correlation_id
        self.detected_intent = result.detected_intent
        self.routing_confidence = result.routing_confidence
        self.consulted_specialists = result.consulted_specialists
        self.executed_at = result.executed_at


class AnalysisRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def safe_handler(request: Request):
            try:
                return await handler(request)
            except (HTTPException, RequestValidationError) as exc:
                # Validation exceptions contain raw input values. Never serialize
                # them, including the original question or injected field values.
                code = exc.status_code if isinstance(exc, HTTPException) else 422
                message = (sanitize_public_prose(exc.detail) if isinstance(exc, HTTPException)
                           and isinstance(exc.detail, str) else "Request context is not supported for this analysis.")
                correlation_id = getattr(exc, "correlation_id", None) or str(uuid.uuid4())
                # Reuse a valid request reference without echoing any other input.
                try:
                    candidate = (await request.json()).get("correlation_id")
                    if candidate:
                        correlation_id = _validate_uuid_str(candidate)
                except (ValueError, TypeError, AttributeError):
                    pass
                message = sanitize_public_prose(message, {correlation_id})
                metadata = {}
                if isinstance(exc, AnalysisExecutionFailure):
                    metadata = dict(
                        detected_intent=exc.detected_intent,
                        routing_confidence=exc.routing_confidence,
                        consulted_specialists=exc.consulted_specialists,
                    )
                envelope = AgentExecuteResponse(
                    correlation_id=correlation_id, status="failed", summary=message,
                    confidence=None, safe_error_message=message,
                    executed_at=(exc.executed_at if isinstance(exc, AnalysisExecutionFailure)
                                 else datetime.now(timezone.utc)),
                    **metadata,
                ).model_dump(mode="json")
                # Keep detail for existing HTTP error clients; all analysis fields
                # now have the same deliberate shape, including refusals.
                envelope["detail"] = message
                return JSONResponse(status_code=code, content=envelope)
        return safe_handler


router = APIRouter(prefix="/agents", tags=["Multi-Agent System"], route_class=AnalysisRoute)


def _validate_uuid_str(v: Any, field_name: str = "correlation_id") -> str:
    if v is None:
        raise ValueError(f"{field_name} is required")
    s = str(v).strip()
    try:
        val_uuid = uuid.UUID(s)
        return str(val_uuid)
    except (ValueError, TypeError, AttributeError):
        raise ValueError(f"Invalid {field_name} format: a valid UUID is required")


# =========================================================================
# 1. Strict Request & Response Schemas
# =========================================================================


class AgentExecuteRequest(BaseModel):
    """
    Validated client request envelope for executing multi-agent workflows.
    The client provides only a natural language question and safe optional context.
    Accepts explicit target team/task selectors; forbids injected roles, intents, and specialist agents.
    """

    model_config = ConfigDict(extra="forbid")

    question: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
    ]
    target_team_id: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
    ] | None = None
    target_task_id: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
    ] | None = None
    weeks_lookback: Annotated[int, Field(ge=1, le=12)] | None = None
    conversation_id: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
    ] | None = None
    correlation_id: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
    ] | None = None

    @field_validator("correlation_id", mode="before")
    @classmethod
    def validate_correlation_id(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return _validate_uuid_str(v, "correlation_id")


class SpecialistFindingItem(BaseModel):
    """Sanitized structured finding produced by an individual specialist or coordinator."""

    model_config = ConfigDict(extra="forbid")

    agent: AgentName
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    limitations: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)


class SafeExecutionError(BaseModel):
    """Sanitized error description for partial or failed agent executions."""

    model_config = ConfigDict(extra="forbid")

    agent: str
    error_code: str
    message: str


class AgentExecuteResponse(BaseModel):
    """
    Validated, privacy-safe response returned by the multi-agent execution endpoint.
    Excludes internal prompts, raw database records, API keys, and employee secrets.
    """

    model_config = ConfigDict(extra="forbid")

    correlation_id: str
    detected_intent: AgentIntent | None = None
    routing_confidence: float | None = None
    consulted_specialists: list[AgentName] = Field(default_factory=list)
    clarification_question: str | None = None
    required_context: list[str] = Field(default_factory=list)
    status: ResponseStatus
    summary: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    findings: list[SpecialistFindingItem] = Field(default_factory=list)
    task_assignment_details: TaskAssignmentDetails | None = None
    limitations: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    errors: list[SafeExecutionError] = Field(default_factory=list)
    safe_error_message: str | None = None
    executed_at: datetime

    @field_validator("findings", mode="after")
    @classmethod
    def validate_no_coordinator_in_findings(
        cls, v: list[SpecialistFindingItem]
    ) -> list[SpecialistFindingItem]:
        for finding in v:
            if finding.agent == "coordinator":
                raise ValueError("AgentExecuteResponse.findings must never contain agent='coordinator'")
        return v

    @model_validator(mode="after")
    def validate_clarification_and_confidence_invariants(self) -> "AgentExecuteResponse":
        if self.status == "clarification_required":
            if self.confidence is not None:
                raise ValueError("AgentExecuteResponse with status='clarification_required' strictly requires confidence=None")
            if len(self.findings) > 0:
                raise ValueError("AgentExecuteResponse with status='clarification_required' strictly requires findings=[]")
            if len(self.consulted_specialists) > 0:
                raise ValueError("AgentExecuteResponse with status='clarification_required' strictly requires consulted_specialists=[]")
            if self.task_assignment_details is not None:
                raise ValueError("AgentExecuteResponse with status='clarification_required' strictly requires task_assignment_details=None")
            if len(self.limitations) > 0:
                raise ValueError("AgentExecuteResponse with status='clarification_required' strictly requires limitations=[]")
            if len(self.recommended_actions) > 0:
                raise ValueError("AgentExecuteResponse with status='clarification_required' strictly requires recommended_actions=[]")
        elif self.status in ("completed", "partial"):
            if self.confidence is None:
                raise ValueError(f"AgentExecuteResponse with status='{self.status}' strictly requires non-null confidence")
        return self


class IntentCapabilityInfo(BaseModel):
    """Metadata describing a supported intent and its server-owned context requirements."""

    model_config = ConfigDict(extra="forbid")

    intent: AgentIntent
    name: str
    description: str
    target_specialists: list[AgentName]
    requires_team_scope: bool
    context_requirements: ContextFieldRelevance


class SpecialistCapabilityInfo(BaseModel):
    """Metadata describing a registered specialist agent."""

    model_config = ConfigDict(extra="forbid")

    name: AgentName
    title: str
    description: str
    advisory_scope: str


class AgentCapabilitiesResponse(BaseModel):
    """Capabilities and advisory limitations filtered by caller's authenticated role."""

    model_config = ConfigDict(extra="forbid")

    role: PrincipalRole
    supported_intents: list[IntentCapabilityInfo]
    available_specialists: list[SpecialistCapabilityInfo]
    advisory_limitations: list[str]


# =========================================================================
# 2. Dependency Helpers & Principal Resolution
# =========================================================================


async def resolve_authenticated_principal(
    database: Any,
    current_user: dict,
) -> AuthenticatedPrincipal:
    """
    Constructs an AuthenticatedPrincipal strictly from authoritative server-side
    database records. Never trusts client-supplied headers or request body roles.
    Fails closed on inactive or malformed user documents.
    """
    if (
        not current_user
        or not isinstance(current_user, dict)
        or not current_user.get("_id")
        or current_user.get("is_active") is False
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    raw_user_id = current_user["_id"]
    user_id = str(raw_user_id)
    role_str = str(current_user.get("role", "employee"))
    if role_str not in ("employee", "manager", "admin"):
        role_str = "employee"
    role: PrincipalRole = role_str  # type: ignore

    # Employees receive only assigned_team_id
    if role == "employee":
        assigned_team = current_user.get("team_id")
        assigned_team_id = str(assigned_team) if assigned_team is not None else None
        return AuthenticatedPrincipal(
            user_id=user_id,
            role=role,
            assigned_team_id=assigned_team_id,
            managed_team_ids=[],
        )

    # Admins do not inherit fabricated team assignments
    if role == "admin":
        return AuthenticatedPrincipal(
            user_id=user_id,
            role=role,
            assigned_team_id=None,
            managed_team_ids=[],
        )

    # Managers receive only verified teams they manage
    assigned_team = current_user.get("team_id")
    assigned_team_id = str(assigned_team) if assigned_team is not None else None
    managed_team_ids: list[str] = []

    if database is not None:
        try:
            candidate_ids = [raw_user_id, user_id]
            if isinstance(raw_user_id, str) and ObjectId.is_valid(raw_user_id):
                candidate_ids.append(ObjectId(raw_user_id))
            elif isinstance(raw_user_id, ObjectId):
                candidate_ids.append(str(raw_user_id))

            teams_col = database["teams"]
            team_cursor = teams_col.find({"manager_id": {"$in": candidate_ids}})
            if hasattr(team_cursor, "to_list"):
                teams = await team_cursor.to_list(length=100)
            elif hasattr(team_cursor, "__aiter__"):
                teams = [t async for t in team_cursor]
            else:
                teams = [
                    t
                    for t in getattr(teams_col, "docs", [])
                    if t.get("manager_id") in candidate_ids
                    or str(t.get("manager_id", "")) == user_id
                ]
            managed_team_ids = [str(t["_id"]) for t in teams if t.get("_id")]
        except Exception as e:
            logger.warning("Failed to query managed teams for manager %s: %s", user_id, type(e).__name__)
            managed_team_ids = []

    return AuthenticatedPrincipal(
        user_id=user_id,
        role=role,
        assigned_team_id=assigned_team_id,
        managed_team_ids=managed_team_ids,
    )


_coordinator_lock = asyncio.Lock()


async def require_ai_user(request: Request, current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "manager":
        subject = "AI Insights capabilities" if request.url.path.endswith("/capabilities") else "AI Insights and Coordinator workflows"
        raise HTTPException(status_code=403, detail=f"{subject} are restricted to managers")
    return current_user


async def require_safe_ai_request(
    payload: AgentExecuteRequest,
    current_user: dict = Depends(require_ai_user),
) -> dict:
    if is_prohibited_request(payload.question):
        raise ProhibitedAnalysisRequest(payload.correlation_id or str(uuid.uuid4()))
    return current_user


async def get_agent_coordinator(
    request: Request, current_user: dict = Depends(require_safe_ai_request),
) -> AgentCoordinator:
    """
    FastAPI dependency resolving the application's shared AgentCoordinator instance.
    Supports dependency overrides in unit/integration tests and lazy production creation.
    Thread/concurrency-safe against simultaneous initial requests.
    """
    coordinator = getattr(request.app.state, "agent_coordinator", None)
    if coordinator is not None:
        return coordinator

    async with _coordinator_lock:
        coordinator = getattr(request.app.state, "agent_coordinator", None)
        if coordinator is not None:
            return coordinator

        database = getattr(request.app.state, "database", None)
        try:
            coordinator = create_production_coordinator(database=database)
            request.app.state.agent_coordinator = coordinator
            return coordinator
        except LLMConfigurationError as e:
            logger.error("Production LLM configuration unavailable")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="LLM service is not configured or unavailable",
            ) from None
        except Exception as e:
            logger.error("Failed to initialize AgentCoordinator (%s)", type(e).__name__)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="LLM service is currently unavailable",
            ) from None


# =========================================================================
# 3. Intent Metadata Registry
# =========================================================================

INTENT_METADATA: dict[AgentIntent, dict[str, Any]] = {
    "productivity_analysis": {
        "name": "Productivity Analysis",
        "description": "Analyzes task throughput, velocity, completion rates, and delivery bottlenecks.",
        "target_specialists": ["productivity"],
        "requires_team_scope": True,
    },
    "collaboration_analysis": {
        "name": "Collaboration Analysis",
        "description": "Analyzes cross-functional communication, blocker discussions, and response latency.",
        "target_specialists": ["collaboration"],
        "requires_team_scope": True,
    },
    "wellbeing_analysis": {
        "name": "Well-being Analysis",
        "description": "Analyzes aggregated anonymous team pulse trends, burnout indicators, and balance metrics.",
        "target_specialists": ["wellbeing"],
        "requires_team_scope": True,
    },
    "task_assignment_recommendation": {
        "name": "Task Assignment Recommendation",
        "description": "Recommends eligible team members for task allocation based on required skills and active workload.",
        "target_specialists": ["task_assigning"],
        "requires_team_scope": True,
    },
    "task_delay_analysis": {
        "name": "Task Delay Root-Cause Analysis",
        "description": "Orchestrates productivity and collaboration specialists to identify bottlenecks behind delayed tasks.",
        "target_specialists": ["productivity", "collaboration"],
        "requires_team_scope": True,
    },
    "team_workload_analysis": {
        "name": "Team Workload & Capacity Analysis",
        "description": "Orchestrates productivity and wellbeing specialists to evaluate workload balance against historical capacity.",
        "target_specialists": ["productivity", "wellbeing"],
        "requires_team_scope": True,
    },
    "general_workforce_question": {
        "name": "General Workforce Executive Overview",
        "description": "Synthesizes multi-domain insights across productivity, collaboration, and wellbeing.",
        "target_specialists": ["productivity", "collaboration", "wellbeing"],
        "requires_team_scope": True,
    },
}

SPECIALIST_METADATA: list[dict[str, Any]] = [
    {
        "name": "productivity",
        "title": "Productivity Specialist Agent",
        "description": "Evaluates task throughput, cycle times, workload distribution, and delivery bottlenecks.",
        "advisory_scope": "Read-only deterministic metrics and advisory recommendations.",
    },
    {
        "name": "collaboration",
        "title": "Collaboration Specialist Agent",
        "description": "Evaluates cross-team communication patterns, response latency, and task blockers.",
        "advisory_scope": "Read-only aggregated communication metrics and blocker analysis.",
    },
    {
        "name": "wellbeing",
        "title": "Well-being Specialist Agent",
        "description": "Evaluates aggregated anonymous team pulse trends, burnout indicators, and balance metrics.",
        "advisory_scope": "Aggregated team pulse metrics with strict k-anonymity (min 3 responses).",
    },
    {
        "name": "task_assigning",
        "title": "Task Assignment Specialist Agent",
        "description": "Evaluates objective skill coverage and active capacity to recommend candidates for human manager assignment.",
        "advisory_scope": "Advisory candidate recommendations; human manager retains final assignment authority.",
    },
]

STANDARD_ADVISORY_LIMITATIONS = [
    "All AI agent findings and recommendations are strictly advisory and require human manager review and approval.",
    "AI agents never automatically assign or reassign tasks, mutate employee records, or execute database writes.",
    "Well-being pulse survey responses are aggregated with a strict minimum anonymity threshold and are permanently isolated from task assignment.",
    "Evaluation based on protected demographic attributes, punitive actions, and individual performance rankings is strictly prohibited.",
]

FORBIDDEN_ERROR_CODES = {
    "PROHIBITED_REQUEST",
    "ROLE_INTENT_FORBIDDEN",
    "EMPLOYEE_AI_INSIGHTS_FORBIDDEN",
    "EMPLOYEE_TASK_ASSIGNMENT_FORBIDDEN",
    "EMPLOYEE_TEAM_WORKLOAD_FORBIDDEN",
    "EMPLOYEE_CROSS_TEAM_FORBIDDEN",
    "MANAGER_UNMANAGED_TEAM_FORBIDDEN",
    "ADMIN_TASK_ASSIGNMENT_DISABLED",
    "UNMANAGED_TEAM_EVIDENCE_FORBIDDEN",
    "EVIDENCE_TEAM_SCOPE_MISMATCH",
    "WELLBEING_TASK_ASSIGNMENT_FORBIDDEN",
    "AUTHORIZATION_DENIED",
    "CAPABILITY_UNAUTHORIZED",
    "DEPENDENCY_FLOW_FORBIDDEN",
    "AGENT_IMPERSONATION_FORBIDDEN",
    "PUNITIVE_RECOMMENDATIONS_FORBIDDEN",
}


# =========================================================================
# 4. API Endpoints
# =========================================================================


@router.post(
    "/execute",
    response_model=AgentExecuteResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute Multi-Agent Workflow",
    description="Orchestrates specialist AI agents to analyze workforce productivity, collaboration, wellbeing, or task assignment.",
)
async def execute_agent_workflow(
    payload: AgentExecuteRequest,
    request: Request,
    current_user: dict = Depends(require_safe_ai_request),
    coordinator: AgentCoordinator = Depends(get_agent_coordinator),
) -> AgentExecuteResponse:
    """
    Authenticated execution endpoint:
    1. Derives trusted AuthenticatedPrincipal from session user and database.
    2. Constructs validated CoordinatorExecutionRequest.
    3. Calls AgentCoordinator.orchestrate() exactly once.
    4. Maps status and errors to safe, typed HTTP responses.
    """
    database = getattr(request.app.state, "database", None)
    principal = await resolve_authenticated_principal(database, current_user)

    if principal.role != "manager":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AI Insights and Coordinator workflows are restricted to managers",
        )

    correlation_id = payload.correlation_id or str(uuid.uuid4())

    coord_req = CoordinatorExecutionRequest(
        correlation_id=correlation_id,
        intent=None,
        authenticated_principal=principal,
        question=payload.question,
        target_team_id=payload.target_team_id,
        target_task_id=payload.target_task_id,
        weeks_lookback=payload.weeks_lookback,
        conversation_id=payload.conversation_id,
    )

    try:
        result: CoordinatorExecutionResult = await coordinator.orchestrate(coord_req)
    except Exception as exc:
        logger.error("Unexpected exception in coordinator.orchestrate: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred during agent execution",
        ) from None

    # Extract known identifiers for defense-in-depth prose sanitization
    known_ids: set[str] = {
        principal.user_id,
        principal.assigned_team_id or "",
        *(principal.managed_team_ids or []),
        payload.target_team_id or "",
        payload.target_task_id or "",
        payload.conversation_id or "",
        correlation_id,
    }
    known_ids.discard("")

    # Handle clarification required state
    if result.status == "clarification_required":
        sanitized_clarification_q = sanitize_public_prose(
            result.clarification_question,
            known_identifiers=known_ids,
        )
        return AgentExecuteResponse(
            correlation_id=result.correlation_id,
            detected_intent=result.detected_intent,
            routing_confidence=result.routing_confidence,
            consulted_specialists=[],
            clarification_question=sanitized_clarification_q,
            required_context=result.required_context,
            status="clarification_required",
            summary=sanitized_clarification_q or "Please clarify your workforce question.",
            confidence=None,
            findings=[],
            limitations=[],
            recommended_actions=[],
            errors=[],
            safe_error_message=None,
            executed_at=result.executed_at,
        )

    # Handle total failure mapping
    if result.status == "failed":
        first_error_code = (
            result.errors[0]["error_code"]
            if result.errors and "error_code" in result.errors[0]
            else "EXECUTION_FAILED"
        )
        safe_msg = sanitize_public_prose(
            result.safe_error_message or "Agent execution failed",
            known_identifiers=known_ids,
        )

        if first_error_code in FORBIDDEN_ERROR_CODES:
            http_status = status.HTTP_403_FORBIDDEN
        elif first_error_code in ("EXECUTION_TIMEOUT", "TIMEOUT"):
            http_status = status.HTTP_504_GATEWAY_TIMEOUT
        elif first_error_code in ("LLM_PROVIDER_ERROR", "PROVIDER_ERROR", "SERVICE_UNAVAILABLE"):
            http_status = status.HTTP_503_SERVICE_UNAVAILABLE
        elif first_error_code in ("TARGET_TASK_NOT_FOUND", "RESOURCE_NOT_FOUND"):
            http_status = status.HTTP_404_NOT_FOUND
        elif first_error_code in ("IRRELEVANT_CONTEXT_REJECTED", "VALIDATION_FAILED", "VALIDATION_ERROR"):
            http_status = status.HTTP_422_UNPROCESSABLE_ENTITY
        else:
            http_status = status.HTTP_500_INTERNAL_SERVER_ERROR
        raise AnalysisExecutionFailure(http_status, safe_msg, result)

    # Completed or Partial result maps to HTTP 200
    primary_finding = (
        result.synthesized_finding
        if result.synthesized_finding is not None
        else (result.findings[0] if result.findings else None)
    )

    summary_text = sanitize_public_prose(
        primary_finding.summary
        if primary_finding is not None
        else "Agent workflow execution completed.",
        known_identifiers=known_ids,
    )
    confidence_val = (
        primary_finding.confidence
        if primary_finding is not None
        else None
    )
    limitations_list = [
        sanitize_public_prose(lim, known_identifiers=known_ids)
        for lim in (primary_finding.limitations if primary_finding is not None else [])
    ]
    recommendations_list = [
        sanitize_public_prose(act, known_identifiers=known_ids)
        for act in (primary_finding.recommended_actions if primary_finding is not None else [])
    ]

    findings_items = [
        SpecialistFindingItem(
            agent=f.agent,
            summary=sanitize_public_prose(f.summary, known_identifiers=known_ids),
            confidence=f.confidence,
            limitations=[
                sanitize_public_prose(lim, known_identifiers=known_ids)
                for lim in f.limitations
            ],
            recommended_actions=[
                sanitize_public_prose(act, known_identifiers=known_ids)
                for act in f.recommended_actions
            ],
        )
        for f in result.findings
        if f.agent != "coordinator"
    ]

    errors_items = [
        SafeExecutionError(
            agent=str(e.get("agent", "unknown")),
            # Public classification only; internal runtime codes stay in audit logs.
            error_code="specialist_unavailable",
            message=sanitize_public_prose(str(e.get("message", "An error occurred")), known_identifiers=known_ids),
        )
        for e in result.errors
    ]

    sanitized_safe_err = (
        sanitize_public_prose(result.safe_error_message, known_identifiers=known_ids)
        if result.safe_error_message
        else None
    )

    sanitized_clarification_q = (
        sanitize_public_prose(result.clarification_question, known_identifiers=known_ids)
        if result.clarification_question
        else None
    )

    def sanitize_details(value):
        if isinstance(value, str):
            return sanitize_public_prose(value, known_identifiers=known_ids)
        if isinstance(value, list):
            return [sanitize_details(item) for item in value]
        if isinstance(value, dict):
            return {key: item if key in ("eligibility_status", "recommendation_label") else sanitize_details(item)
                    for key, item in value.items()}
        return value
    public_task_details = (
        TaskAssignmentDetails.model_validate(sanitize_details(result.task_assignment_details.model_dump()))
        if result.task_assignment_details else None
    )

    return AgentExecuteResponse(
        correlation_id=result.correlation_id,
        detected_intent=result.detected_intent or result.intent,
        routing_confidence=result.routing_confidence,
        consulted_specialists=result.consulted_specialists,
        clarification_question=sanitized_clarification_q,
        required_context=result.required_context,
        status=result.status,
        summary=summary_text,
        confidence=confidence_val,
        findings=findings_items,
        task_assignment_details=public_task_details,
        limitations=limitations_list,
        recommended_actions=recommendations_list,
        errors=errors_items,
        safe_error_message=sanitized_safe_err,
        executed_at=result.executed_at,
    )


@router.get(
    "/capabilities",
    response_model=AgentCapabilitiesResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Multi-Agent Capabilities",
    description="Returns supported intents and specialist capabilities filtered by caller's authenticated role.",
)
async def get_agent_capabilities(
    request: Request,
    current_user: dict = Depends(require_ai_user),
) -> AgentCapabilitiesResponse:
    """
    Role-aware capabilities endpoint:
    Returns supported intents, registered specialist summaries, and advisory limits.
    Strictly forbids exposing prompts, database queries, credentials, or internal rules.
    """
    database = getattr(request.app.state, "database", None)
    principal = await resolve_authenticated_principal(database, current_user)
    role = principal.role

    if role != "manager":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AI Insights capabilities are restricted to managers",
        )

    allowed_intents = get_allowed_intents_for_role(role)

    supported_intents_list = []
    for intent, meta in INTENT_METADATA.items():
        if intent in allowed_intents:
            context_req = INTENT_CONTEXT_RELEVANCE_MATRIX[intent]
            supported_intents_list.append(
                IntentCapabilityInfo(
                    intent=intent,
                    name=meta["name"],
                    description=meta["description"],
                    target_specialists=meta["target_specialists"],
                    requires_team_scope=context_req.team_scope == "required",
                    context_requirements=context_req,
                )
            )

    specialists_list = [
        SpecialistCapabilityInfo(
            name=s["name"],
            title=s["title"],
            description=s["description"],
            advisory_scope=s["advisory_scope"],
        )
        for s in SPECIALIST_METADATA
    ]

    return AgentCapabilitiesResponse(
        role=role,
        supported_intents=supported_intents_list,
        available_specialists=specialists_list,
        advisory_limitations=STANDARD_ADVISORY_LIMITATIONS,
    )
