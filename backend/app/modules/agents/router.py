import asyncio
from datetime import datetime, timezone
import logging
from typing import Annotated, Any, Literal
import uuid

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, status
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
from backend.app.modules.agents.protocol import (
    AgentIntent,
    AgentName,
    ResponseStatus,
)
from backend.app.modules.agents.security_policy import (
    ADMIN_ALLOWED_INTENTS,
    EMPLOYEE_ALLOWED_INTENTS,
    MANAGER_ALLOWED_INTENTS,
    AuthenticatedPrincipal,
    PrincipalRole,
    get_allowed_intents_for_role,
)

logger = logging.getLogger("remote_workforce.agents.router")

router = APIRouter(prefix="/agents", tags=["Multi-Agent System"])


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
# 1. Strict Request & Response Schemas
# =========================================================================


class AgentExecuteRequest(BaseModel):
    """
    Validated client request envelope for executing multi-agent workflows.
    Strictly forbids client-injected roles, team scopes, or dependency findings.
    """

    model_config = ConfigDict(extra="forbid")

    intent: AgentIntent
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

    @model_validator(mode="after")
    def validate_intent_parameters(self) -> "AgentExecuteRequest":
        if self.intent == "task_assignment_recommendation":
            if not self.target_task_id or not self.target_task_id.strip():
                raise ValueError("target_task_id is required for task_assignment_recommendation")
            if self.weeks_lookback is not None:
                raise ValueError("weeks_lookback is not supported for task_assignment_recommendation")
        elif self.intent in (
            "wellbeing_analysis",
            "team_workload_analysis",
            "general_workforce_question",
            "productivity_analysis",
            "collaboration_analysis",
        ):
            if self.target_task_id is not None:
                raise ValueError(f"target_task_id is not permitted for intent '{self.intent}'")
        return self


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
    intent: AgentIntent
    status: ResponseStatus
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    findings: list[SpecialistFindingItem] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    errors: list[SafeExecutionError] = Field(default_factory=list)
    safe_error_message: str | None = None
    executed_at: datetime


class IntentCapabilityInfo(BaseModel):
    """Metadata describing a supported intent."""

    model_config = ConfigDict(extra="forbid")

    intent: AgentIntent
    name: str
    description: str
    target_specialists: list[AgentName]
    requires_team_scope: bool


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
            logger.warning("Failed to query managed teams for manager %s: %s", user_id, e)
            managed_team_ids = []

    return AuthenticatedPrincipal(
        user_id=user_id,
        role=role,
        assigned_team_id=assigned_team_id,
        managed_team_ids=managed_team_ids,
    )


_coordinator_lock = asyncio.Lock()


async def get_agent_coordinator(request: Request) -> AgentCoordinator:
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
            logger.error("Production LLM configuration error: %s", e)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="LLM service is not configured or unavailable",
            ) from None
        except Exception as e:
            logger.error("Failed to initialize AgentCoordinator: %s", e)
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
        "requires_team_scope": False,
    },
    "collaboration_analysis": {
        "name": "Collaboration Analysis",
        "description": "Analyzes cross-functional communication, blocker discussions, and response latency.",
        "target_specialists": ["collaboration"],
        "requires_team_scope": False,
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
        "requires_team_scope": False,
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
        "requires_team_scope": False,
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
    "ROLE_INTENT_FORBIDDEN",
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
    current_user: dict = Depends(get_current_user),
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

    correlation_id = payload.correlation_id or str(uuid.uuid4())

    coord_req = CoordinatorExecutionRequest(
        correlation_id=correlation_id,
        intent=payload.intent,
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
        logger.exception("Unexpected exception in coordinator.orchestrate: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred during agent execution",
        ) from None

    # Handle total failure mapping
    if result.status == "failed":
        first_error_code = (
            result.errors[0]["error_code"]
            if result.errors and "error_code" in result.errors[0]
            else "EXECUTION_FAILED"
        )
        safe_msg = result.safe_error_message or "Agent execution failed"

        if first_error_code in FORBIDDEN_ERROR_CODES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=safe_msg,
            )

        if first_error_code in ("EXECUTION_TIMEOUT", "TIMEOUT"):
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=safe_msg,
            )

        if first_error_code in ("LLM_PROVIDER_ERROR", "PROVIDER_ERROR", "SERVICE_UNAVAILABLE"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=safe_msg,
            )

        if first_error_code in ("TARGET_TASK_NOT_FOUND", "RESOURCE_NOT_FOUND"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=safe_msg,
            )

        # Generic safe 500 error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_msg,
        )

    # Completed or Partial result maps to HTTP 200
    primary_finding = (
        result.synthesized_finding
        if result.synthesized_finding is not None
        else (result.findings[0] if result.findings else None)
    )

    summary_text = (
        primary_finding.summary
        if primary_finding is not None
        else "Agent workflow execution completed."
    )
    confidence_val = (
        primary_finding.confidence
        if primary_finding is not None
        else 1.0
    )
    limitations_list = (
        primary_finding.limitations
        if primary_finding is not None
        else []
    )
    recommendations_list = (
        primary_finding.recommended_actions
        if primary_finding is not None
        else []
    )

    findings_items = [
        SpecialistFindingItem(
            agent=f.agent,
            summary=f.summary,
            confidence=f.confidence,
            limitations=f.limitations,
            recommended_actions=f.recommended_actions,
        )
        for f in result.findings
    ]

    errors_items = [
        SafeExecutionError(
            agent=str(e.get("agent", "unknown")),
            error_code=str(e.get("error_code", "ERROR")),
            message=str(e.get("message", "An error occurred")),
        )
        for e in result.errors
    ]

    return AgentExecuteResponse(
        correlation_id=result.correlation_id,
        intent=result.intent,
        status=result.status,
        summary=summary_text,
        confidence=confidence_val,
        findings=findings_items,
        limitations=limitations_list,
        recommended_actions=recommendations_list,
        errors=errors_items,
        safe_error_message=result.safe_error_message,
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
    current_user: dict = Depends(get_current_user),
) -> AgentCapabilitiesResponse:
    """
    Role-aware capabilities endpoint:
    Returns supported intents, registered specialist summaries, and advisory limits.
    Strictly forbids exposing prompts, database queries, credentials, or internal rules.
    """
    database = getattr(request.app.state, "database", None)
    principal = await resolve_authenticated_principal(database, current_user)
    role = principal.role

    allowed_intents = get_allowed_intents_for_role(role)

    supported_intents_list = []
    for intent, meta in INTENT_METADATA.items():
        if intent in allowed_intents:
            supported_intents_list.append(
                IntentCapabilityInfo(
                    intent=intent,
                    name=meta["name"],
                    description=meta["description"],
                    target_specialists=meta["target_specialists"],
                    requires_team_scope=meta["requires_team_scope"],
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
