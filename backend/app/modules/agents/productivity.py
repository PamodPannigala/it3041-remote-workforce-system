from datetime import datetime, timedelta, timezone
import json
import logging
import math
from typing import Annotated, Any, Callable
from bson import ObjectId
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

from backend.app.modules.agents.protocol import (
    AgentFinding,
    AgentIntent,
    AgentName,
    AgentRequest,
    AgentResponse,
    EvidenceReference,
    EvidenceSourceType,
)
from backend.app.modules.agents.runtime import (
    AgentAuthorizationError,
    AgentDefinition,
    AgentRuntime,
    AgentTool,
    AgentToolExecutionError,
    BaseAgentTool,
    ExecutionContext,
)
from backend.app.modules.agents.security_policy import (
    AGENT_ALLOWED_EVIDENCE_SOURCES,
    AGENT_ALLOWED_INTENTS,
    AuthenticatedPrincipal,
    validate_evidence_team_scope,
)

logger = logging.getLogger("remote_workforce.agents.productivity")

PRODUCTIVITY_AGENT_NAME: AgentName = "productivity"
PRODUCTIVITY_EVIDENCE_TOOL_NAME = "productivity_task_evidence"


def get_productivity_tool_name(intent: AgentIntent = "productivity_analysis") -> str:
    """Returns the explicit canonical tool name for a given productivity intent."""
    return f"productivity_task_evidence_{intent}"


def _ensure_utc(v: Any) -> datetime | None:
    """
    Safely normalizes any date representation (datetime, ISO string) into a timezone-aware UTC datetime.
    Returns None if missing, empty, or malformed.
    """
    if v is None:
        return None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)
    if isinstance(v, str):
        v_str = v.strip()
        if not v_str or v_str.lower() in ("none", "null", "undefined", "n/a"):
            return None
        try:
            if v_str.endswith("Z"):
                v_str = v_str[:-1] + "+00:00"
            dt = datetime.fromisoformat(v_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (ValueError, TypeError):
            return None
    return None


def _parse_progress_value(raw_val: Any) -> float | None:
    """
    Safely parses a progress percentage value.
    Rejects booleans, non-numeric strings, NaNs, infinities, and out-of-range values (< 0 or > 100).
    Returns None if missing or invalid.
    """
    if raw_val is None:
        return None
    if isinstance(raw_val, bool):
        return None
    try:
        val = float(raw_val)
        if math.isnan(val) or math.isinf(val):
            return None
        if val < 0.0 or val > 100.0:
            return None
        return val
    except (ValueError, TypeError):
        return None


# =========================================================================
# 1. Deterministic Metrics Models & Calculation
# =========================================================================


class DeterministicTaskMetrics(BaseModel):
    """
    Factual, deterministic productivity metrics computed directly in Python
    from verified MongoDB task records prior to LLM reasoning.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    total_tasks: int = 0
    completed_count: int = 0
    in_progress_count: int = 0
    blocked_count: int = 0
    todo_count: int = 0
    overdue_count: int = 0
    due_soon_count: int = 0  # Tasks due within upcoming 7 days UTC (not overdue or completed)
    average_progress: float | None = None  # Percentage 0.0 to 100.0 or None if no valid progress
    invalid_progress_count: int = 0
    unresolved_blockers_count: int = 0
    resolved_blockers_count: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    priority_counts: dict[str, int] = Field(default_factory=dict)
    calculation_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_summary_text(self) -> str:
        avg_prog_str = (
            f"{self.average_progress:.1f}%"
            if self.average_progress is not None
            else "N/A"
        )
        invalid_note = (
            f" (Excluded {self.invalid_progress_count} invalid progress entries)"
            if self.invalid_progress_count > 0
            else ""
        )
        return (
            f"Total Tasks: {self.total_tasks} | "
            f"Completed: {self.completed_count}, Blocked: {self.blocked_count}, "
            f"In Progress: {self.in_progress_count}, Todo: {self.todo_count} | "
            f"Overdue: {self.overdue_count}, Due Soon (7d): {self.due_soon_count} | "
            f"Average Progress: {avg_prog_str}{invalid_note} | "
            f"Unresolved Blockers: {self.unresolved_blockers_count}, Resolved Blockers: {self.resolved_blockers_count}"
        )


def compute_deterministic_task_metrics(
    task_docs: list[dict],
    now: datetime | None = None,
) -> DeterministicTaskMetrics:
    """
    Computes deterministic task management metrics from verified MongoDB task documents.

    Mutually Exclusive Lifecycle Task Bucket Precedence:
    1. completed: task status is 'completed' or genuinely valid progress is exactly 100.0%.
    2. blocked: non-completed task where status is 'blocked' or has active unresolved blockers.
    3. in_progress: non-completed, non-blocked task where status is 'in_progress' or valid progress > 0.0%.
    4. todo: all other tasks (status is 'todo' or unstarted/other).
    Guarantee: completed_count + blocked_count + in_progress_count + todo_count == total_tasks.

    Overdue & Due-Soon Risk Dimensions:
    - overdue: non-completed task with a valid due_date strictly < now_utc.
    - due_soon: non-completed task with a valid due_date where now_utc <= due_date <= now_utc + 7 days.
    - completed tasks NEVER count as overdue or due_soon.

    Invalid Progress Handling:
    - Out-of-range (<0 or >100), boolean, NaN, inf, or non-numeric progress is treated as missing.
    - Invalid progress never marks a task completed.
    - Invalid progress is excluded from average_progress.
    """
    now_utc = _ensure_utc(now) or datetime.now(timezone.utc)
    due_soon_window = now_utc + timedelta(days=7)

    total_tasks = len(task_docs)
    completed_count = 0
    in_progress_count = 0
    blocked_count = 0
    todo_count = 0
    overdue_count = 0
    due_soon_count = 0
    unresolved_blockers = 0
    resolved_blockers = 0
    invalid_progress_count = 0

    status_counts: dict[str, int] = {}
    priority_counts: dict[str, int] = {}
    valid_progress_values: list[float] = []

    for doc in task_docs:
        status = str(doc.get("status", "todo")).strip().lower()
        priority = str(doc.get("priority", "medium")).strip().lower()
        priority_counts[priority] = priority_counts.get(priority, 0) + 1

        # Check raw progress percentage from doc or progress_history
        raw_progress = doc.get("progress_percentage")
        if raw_progress is None:
            history = doc.get("progress_history") or []
            if isinstance(history, list) and history:
                latest = history[-1]
                if isinstance(latest, dict) and "percentage" in latest:
                    raw_progress = latest.get("percentage")

        parsed_progress = _parse_progress_value(raw_progress)
        if raw_progress is not None and parsed_progress is None:
            invalid_progress_count += 1

        # Precedence 1: Completed
        is_completed = (status == "completed") or (parsed_progress == 100.0)

        # Check blockers
        blockers = doc.get("blockers") or []
        doc_has_unresolved_blocker = False
        if isinstance(blockers, list):
            for b in blockers:
                if isinstance(b, dict):
                    if b.get("is_resolved", False) or b.get("resolved_at") is not None:
                        resolved_blockers += 1
                    elif not is_completed:
                        unresolved_blockers += 1
                        doc_has_unresolved_blocker = True

        if is_completed:
            completed_count += 1
            valid_progress_values.append(100.0)
            status_counts["completed"] = status_counts.get("completed", 0) + 1
        elif status == "blocked" or doc_has_unresolved_blocker:
            # Precedence 2: Blocked
            blocked_count += 1
            if parsed_progress is not None:
                valid_progress_values.append(parsed_progress)
            status_counts["blocked"] = status_counts.get("blocked", 0) + 1
        elif status == "in_progress" or (parsed_progress is not None and parsed_progress > 0.0):
            # Precedence 3: In Progress
            in_progress_count += 1
            if parsed_progress is not None:
                valid_progress_values.append(parsed_progress)
            status_counts["in_progress"] = status_counts.get("in_progress", 0) + 1
        else:
            # Precedence 4: Todo / Other
            todo_count += 1
            if parsed_progress is not None:
                valid_progress_values.append(parsed_progress)
            status_counts["todo"] = status_counts.get("todo", 0) + 1

        # Due Date evaluation (completed tasks are NEVER overdue or due soon)
        if not is_completed:
            due_date_raw = doc.get("due_date")
            due_dt = _ensure_utc(due_date_raw)
            if due_dt is not None:
                if due_dt < now_utc:
                    overdue_count += 1
                elif now_utc <= due_dt <= due_soon_window:
                    due_soon_count += 1

    avg_progress = (
        round(sum(valid_progress_values) / len(valid_progress_values), 2)
        if valid_progress_values
        else None
    )

    return DeterministicTaskMetrics(
        total_tasks=total_tasks,
        completed_count=completed_count,
        in_progress_count=in_progress_count,
        blocked_count=blocked_count,
        todo_count=todo_count,
        overdue_count=overdue_count,
        due_soon_count=due_soon_count,
        average_progress=avg_progress,
        invalid_progress_count=invalid_progress_count,
        unresolved_blockers_count=unresolved_blockers,
        resolved_blockers_count=resolved_blockers,
        status_counts=status_counts,
        priority_counts=priority_counts,
        calculation_timestamp=now_utc,
    )


# =========================================================================
# 2. Specialist Structured Output Schema
# =========================================================================


class ProductivityFindingOutput(BaseModel):
    """
    Strict Pydantic structured output returned by LLM completions for Productivity Agent.
    Enforces evidence-based workload, milestone, and blocker observations.
    Excludes chain-of-thought and punitive/medical claims.
    """

    model_config = ConfigDict(extra="forbid")

    summary: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=3000),
    ]
    workload_observations: list[
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
        ]
    ] = Field(default_factory=list, max_length=20)
    completion_and_overdue_observations: list[
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
        ]
    ] = Field(default_factory=list, max_length=20)
    blocker_observations: list[
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
        ]
    ] = Field(default_factory=list, max_length=20)
    recommended_actions: list[
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
        ]
    ] = Field(default_factory=list, max_length=20)
    confidence: float = Field(ge=0.0, le=1.0)
    limitations: list[
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
        ]
    ] = Field(default_factory=list, max_length=20)


# =========================================================================
# 3. Productivity Evidence Collection Tool
# =========================================================================


def _format_task_snippet(doc: dict) -> str:
    """
    Builds a concise, safe summary snippet for a single task document.
    Omits unnecessary user PII and excessive details while preserving key milestone metadata.
    """
    task_id = str(doc.get("_id", "unknown"))
    title = str(doc.get("title", "")).strip()
    status = str(doc.get("status", "todo")).strip()
    priority = str(doc.get("priority", "medium")).strip()
    est_hours = doc.get("estimated_hours", 0)

    # Progress
    raw_prog = doc.get("progress_percentage")
    if raw_prog is None:
        history = doc.get("progress_history") or []
        if isinstance(history, list) and history and isinstance(history[-1], dict):
            raw_prog = history[-1].get("percentage", 0)
        else:
            raw_prog = 100 if status == "completed" else 0

    parsed_prog = _parse_progress_value(raw_prog)
    prog_str = f"{int(parsed_prog)}%" if parsed_prog is not None else "N/A"

    # Due Date
    due_str = "None"
    due_dt = _ensure_utc(doc.get("due_date"))
    if due_dt:
        due_str = due_dt.strftime("%Y-%m-%d UTC")

    # Blockers summary
    blockers = doc.get("blockers") or []
    unresolved_desc = []
    if isinstance(blockers, list) and status != "completed":
        for b in blockers:
            if isinstance(b, dict) and not b.get("is_resolved", False) and b.get("resolved_at") is None:
                b_desc = str(b.get("description", "")).strip()
                if b_desc:
                    unresolved_desc.append(b_desc[:80])

    blocker_info = (
        f"Blockers: {len(unresolved_desc)} active"
        if not unresolved_desc
        else f"Active Blockers: {'; '.join(unresolved_desc)}"
    )

    desc = str(doc.get("description", "")).strip()
    desc_info = f" | Desc: {desc[:100]}" if desc else ""

    return (
        f"[Task ID: {task_id}] '{title}'{desc_info} | Status: {status} | Priority: {priority} | "
        f"Progress: {prog_str} | Est: {est_hours}h | Due: {due_str} | {blocker_info}"
    )


class ProductivityTaskEvidenceTool(BaseAgentTool):
    """
    Deterministic async MongoDB evidence tool for the Productivity Agent.
    Strictly queries only pre-scoped, authorized task records based on the authenticated principal.
    """

    def __init__(
        self,
        database: Any,
        target_team_id: str | None = None,
        name: str = PRODUCTIVITY_EVIDENCE_TOOL_NAME,
        required_intent: AgentIntent = "productivity_analysis",
    ):
        self.database = database
        self.target_team_id = str(target_team_id).strip() if target_team_id else None
        super().__init__(
            name=name,
            target_agent=PRODUCTIVITY_AGENT_NAME,
            required_intent=required_intent,
            source_type="task",
            handler=self._fetch_task_evidence,
        )

    async def _fetch_task_evidence(
        self, context: ExecutionContext
    ) -> list[EvidenceReference]:
        principal = context.principal
        if self.database is None:
            return []

        # 1. Build authoritative database filter based on role and team scope
        filter_query: dict[str, Any] = {}

        if principal.role == "employee":
            # Employee: reject cross-team requests before querying
            if self.target_team_id:
                if principal.assigned_team_id and self.target_team_id != principal.assigned_team_id:
                    raise AgentAuthorizationError(
                        message=f"Employee cannot access team '{self.target_team_id}'",
                        safe_reason_code="EMPLOYEE_CROSS_TEAM_FORBIDDEN",
                        safe_message="Employees cannot request analyses for teams other than their assigned team",
                    )

            if not principal.assigned_team_id:
                # Unassigned employee returns empty evidence set without error
                return []

            # Canonical ObjectId + string compatibility
            user_id = principal.user_id
            user_oids: list[Any] = []
            if ObjectId.is_valid(user_id):
                user_oids.append(ObjectId(user_id))
            if user_id not in user_oids:
                user_oids.append(user_id)

            filter_query["assigned_to"] = {"$in": user_oids} if len(user_oids) > 1 else user_oids[0]

            team_id = self.target_team_id or principal.assigned_team_id
            team_oids: list[Any] = []
            if ObjectId.is_valid(team_id):
                team_oids.append(ObjectId(team_id))
            if team_id not in team_oids:
                team_oids.append(team_id)

            filter_query["team_id"] = {"$in": team_oids} if len(team_oids) > 1 else team_oids[0]

        elif principal.role == "manager":
            # Manager: reject cross-team requests before querying
            if self.target_team_id:
                if self.target_team_id not in principal.managed_team_ids:
                    raise AgentAuthorizationError(
                        message=f"Manager does not manage team '{self.target_team_id}'",
                        safe_reason_code="MANAGER_UNMANAGED_TEAM_FORBIDDEN",
                        safe_message="Managers cannot request analyses for teams they do not manage",
                    )
                target_teams = [self.target_team_id]
            else:
                if not principal.managed_team_ids:
                    # Manager with no managed teams returns empty candidate set without error
                    return []
                target_teams = principal.managed_team_ids

            managed_oids: list[Any] = []
            for tid in target_teams:
                if ObjectId.is_valid(tid):
                    managed_oids.append(ObjectId(tid))
                if tid not in managed_oids:
                    managed_oids.append(tid)

            filter_query["team_id"] = {"$in": managed_oids} if len(managed_oids) > 1 else managed_oids[0]

        elif principal.role == "admin":
            # Admin: organization read scope or specific target team
            if self.target_team_id:
                admin_team_oids: list[Any] = []
                if ObjectId.is_valid(self.target_team_id):
                    admin_team_oids.append(ObjectId(self.target_team_id))
                if self.target_team_id not in admin_team_oids:
                    admin_team_oids.append(self.target_team_id)
                filter_query["team_id"] = {"$in": admin_team_oids} if len(admin_team_oids) > 1 else admin_team_oids[0]
            else:
                filter_query = {}
        else:
            return []

        # 2. Query MongoDB collection directly with pre-filtering
        try:
            tasks_collection = self.database["tasks"]
            cursor = tasks_collection.find(filter_query)

            if hasattr(cursor, "to_list"):
                task_docs = await cursor.to_list(length=100)
            elif hasattr(cursor, "__aiter__"):
                task_docs = [doc async for doc in cursor]
            else:
                task_docs = [
                    d
                    for d in getattr(tasks_collection, "docs", [])
                    if self._match_doc(d, filter_query)
                ]
        except Exception as e:
            logger.warning("Database task query failed: %s", e)
            raise AgentToolExecutionError(
                message="Failed to query tasks collection",
                safe_reason_code="DATABASE_ERROR",
            )

        if not task_docs:
            return []

        # 3. Compute deterministic metrics from collected records
        metrics = compute_deterministic_task_metrics(task_docs)

        # 4. Construct bounded, JSON-safe EvidenceReference list
        evidence_refs: list[EvidenceReference] = []

        # Primary summary reference containing computed metrics
        summary_team_id = (
            principal.assigned_team_id
            if principal.role == "employee"
            else (
                principal.managed_team_ids[0]
                if principal.managed_team_ids
                else "workspace-org"
            )
        )
        evidence_refs.append(
            EvidenceReference(
                source_type="task",
                record_id="metrics-summary",
                title="Aggregated Task Management Metrics",
                snippet=metrics.to_summary_text(),
                team_id=summary_team_id,
            )
        )

        # Individual task references
        for doc in task_docs:
            task_id = str(doc.get("_id", "unknown"))
            team_id_str = str(doc.get("team_id", summary_team_id))
            title = str(doc.get("title", "Task Record")).strip()
            snippet = _format_task_snippet(doc)

            ref = EvidenceReference(
                source_type="task",
                record_id=task_id,
                title=title[:200],
                snippet=snippet[:1000],
                team_id=team_id_str[:64],
            )
            # Validate team scope defense-in-depth before inclusion
            scope_decision = validate_evidence_team_scope(principal, ref)
            if scope_decision.allowed:
                evidence_refs.append(ref)

        return evidence_refs

    def _match_doc(self, doc: dict, filter_query: dict) -> bool:
        if not filter_query:
            return True
        if "$and" in filter_query:
            return all(self._match_doc(doc, sub) for sub in filter_query["$and"])
        if "assigned_to" in filter_query:
            val = filter_query["assigned_to"]
            doc_val = doc.get("assigned_to")
            if isinstance(val, dict) and "$in" in val:
                allowed_vals = [str(x) for x in val["$in"]] + val["$in"]
                if doc_val not in allowed_vals and str(doc_val) not in allowed_vals:
                    return False
            elif doc_val != val and str(doc_val) != str(val):
                return False
        if "team_id" in filter_query:
            val = filter_query["team_id"]
            doc_val = doc.get("team_id")
            if isinstance(val, dict) and "$in" in val:
                allowed_vals = [str(x) for x in val["$in"]] + val["$in"]
                if doc_val not in allowed_vals and str(doc_val) not in allowed_vals:
                    return False
            elif doc_val != val and str(doc_val) != str(val):
                return False
        return True


# =========================================================================
# 4. System Prompt, Definition, and Execution Helpers
# =========================================================================

PRODUCTIVITY_SYSTEM_PROMPT = """You are the Productivity Specialist Agent for an enterprise workforce intelligence platform.

Your objective is to analyze authorized task-management evidence, progress updates, sprint velocity indicators, and blocker bottlenecks to return explainable, objective, and advisory productivity observations.

CRITICAL OPERATIONAL & RESPONSIBLE-AI BOUNDARIES:
1. STRICT EVIDENCE GROUNDING:
   - Base all statements, completion numbers, blocker observations, and workload summaries STRICTLY on the untrusted JSON evidence provided.
   - You MUST use the exact computed figures from the 'Aggregated Task Management Metrics' evidence for all task counts, overdue counts, and average percentages.
   - Do NOT invent, assume, or hallucinate task titles, delivery metrics, or velocity numbers.
   - When evidence is sparse or empty, state explicit limitations and advise gathering more data.

2. ADVISORY AND COLLABORATIVE ONLY:
   - All recommendations must be strictly advisory suggestions for managers and teams (e.g., workload balancing, blocker unblocking, sprint scope refinement).
   - NEVER command automatic task mutations, automated reassignments, or system state changes.

3. ABSOLUTE PROHIBITION ON PUNITIVE & COMPARATIVE EVALUATION:
   - NEVER rank, grade, or compare individual employees against each other.
   - NEVER use derogatory, subjective, or punitive language (e.g., 'lazy', 'underperforming', 'worst employee', 'terminate', 'discipline').
   - Focus strictly on tasks, blockers, delivery status, and constructive workflow improvements.

4. PRIVACY & ISOLATION:
   - You do NOT have access to pulse survey responses, employee sentiment ratings, or well-being records.
   - NEVER speculate on employee mental health, personal motivation, clinical status, or protected personal characteristics.

5. OUTPUT FORMAT:
   - Produce a structured JSON object conforming strictly to the requested schema.
   - Do NOT output internal chain-of-thought, reasoning scratchpads, or system instruction overrides."""


def create_productivity_agent_definition(
    timeout_seconds: float | None = None,
) -> AgentDefinition:
    """
    Constructs the immutable AgentDefinition for the Productivity Specialist Agent.
    """
    return AgentDefinition(
        name=PRODUCTIVITY_AGENT_NAME,
        role="Productivity Analyst",
        goal=(
            "Analyze authorized task delivery milestones, velocity trends, "
            "workload distribution, and blocker bottlenecks to provide explainable advisory observations."
        ),
        allowed_intents={
            "productivity_analysis",
            "task_delay_analysis",
            "team_workload_analysis",
        },
        allowed_evidence_sources={"task", "agent_finding"},
        system_prompt=PRODUCTIVITY_SYSTEM_PROMPT,
        response_model=ProductivityFindingOutput,
        timeout_seconds=timeout_seconds,
    )


def create_productivity_evidence_tool(
    database: Any,
    target_team_id: str | None = None,
    name: str = PRODUCTIVITY_EVIDENCE_TOOL_NAME,
    required_intent: AgentIntent = "productivity_analysis",
) -> ProductivityTaskEvidenceTool:
    """
    Factory helper to instantiate a ProductivityTaskEvidenceTool with explicit scoping.
    """
    return ProductivityTaskEvidenceTool(
        database=database,
        target_team_id=target_team_id,
        name=name,
        required_intent=required_intent,
    )


def register_productivity_agent(
    runtime: AgentRuntime,
    database: Any = None,
    target_team_id: str | None = None,
    timeout_seconds: float | None = None,
) -> None:
    """
    Registers the Productivity Specialist Agent and its task evidence tools into the provided AgentRuntime.
    """
    agent_def = create_productivity_agent_definition(timeout_seconds=timeout_seconds)
    runtime.register_agent(agent_def)

    if database is not None:
        for intent in (
            "productivity_analysis",
            "task_delay_analysis",
            "team_workload_analysis",
        ):
            tool = create_productivity_evidence_tool(
                database=database,
                target_team_id=target_team_id,
                name=f"productivity_task_evidence_{intent}",
                required_intent=intent,  # type: ignore
            )
            runtime.register_tool(tool)


async def execute_productivity_agent(
    runtime: AgentRuntime,
    request: AgentRequest,
    principal: AuthenticatedPrincipal,
    tool_names: list[str] | None = None,
) -> AgentResponse:
    """
    Productivity-specific execution helper that explicitly supplies the canonical
    productivity evidence tool when invoking the runtime.
    """
    explicit_tools = (
        tool_names
        if tool_names is not None
        else [get_productivity_tool_name(request.intent)]
    )
    return await runtime.execute_agent(
        request=request,
        principal=principal,
        tool_names=explicit_tools,
    )
