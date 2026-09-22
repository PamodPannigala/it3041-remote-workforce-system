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

logger = logging.getLogger("remote_workforce.agents.collaboration")

COLLABORATION_AGENT_NAME: AgentName = "collaboration"
COLLABORATION_MESSAGE_TOOL_NAME = "collaboration_message_evidence"
COLLABORATION_TASK_BLOCKER_TOOL_NAME = "collaboration_task_blocker_evidence"

DEFAULT_LOOKBACK_DAYS: int = 30
STALE_BLOCKER_THRESHOLD_DAYS: int = 7

# Explicit evidence bounds to prevent payload ballooning
MAX_MESSAGE_EVIDENCE_ITEMS: int = 15
MAX_BLOCKER_EVIDENCE_ITEMS: int = 15
MAX_MESSAGE_SNIPPET_CHARS: int = 300
MAX_BLOCKER_SNIPPET_CHARS: int = 150


def get_collaboration_tool_names(intent: AgentIntent = "collaboration_analysis") -> list[str]:
    """Returns the explicit canonical tool names for a given collaboration intent."""
    return [
        f"{COLLABORATION_MESSAGE_TOOL_NAME}_{intent}",
        f"{COLLABORATION_TASK_BLOCKER_TOOL_NAME}_{intent}",
    ]


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


# =========================================================================
# 1. Deterministic Collaboration & Blocker Metrics
# =========================================================================


class DeterministicCollaborationMetrics(BaseModel):
    """
    Factual, deterministic collaboration and blocker metrics computed directly in Python
    from pre-filtered, authorized MongoDB records prior to LLM reasoning.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    active_message_count: int = 0
    distinct_active_participant_count: int = 0
    task_count_with_active_blockers: int = 0
    unresolved_blocker_count: int = 0
    resolved_blocker_count: int = 0
    stale_unresolved_blocker_count: int = 0
    average_resolution_hours: float | None = None
    invalid_timestamp_count: int = 0
    analyzed_team_count: int = 0
    evidence_start: datetime
    evidence_end: datetime
    calculation_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_summary_text(self) -> str:
        avg_res_str = (
            f"{self.average_resolution_hours:.1f}h"
            if self.average_resolution_hours is not None
            else "N/A"
        )
        invalid_note = (
            f" (Excluded {self.invalid_timestamp_count} invalid timestamps)"
            if self.invalid_timestamp_count > 0
            else ""
        )
        start_str = self.evidence_start.strftime("%Y-%m-%d UTC")
        end_str = self.evidence_end.strftime("%Y-%m-%d UTC")

        msg_part = (
            f"Active Messages: {self.active_message_count}, Distinct Participants: {self.distinct_active_participant_count} | "
            if (self.active_message_count > 0 or self.distinct_active_participant_count > 0)
            else ""
        )

        return (
            f"Analyzed Period: {start_str} to {end_str} (Teams: {self.analyzed_team_count}) | "
            f"{msg_part}"
            f"Tasks with Active Blockers: {self.task_count_with_active_blockers} | "
            f"Unresolved Blockers: {self.unresolved_blocker_count} (Stale >{STALE_BLOCKER_THRESHOLD_DAYS}d: {self.stale_unresolved_blocker_count}), "
            f"Resolved Blockers (Recent): {self.resolved_blocker_count} | "
            f"Avg Resolution Time: {avg_res_str}{invalid_note}"
        )


def compute_deterministic_collaboration_metrics(
    message_docs: list[dict],
    task_docs: list[dict],
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    now: datetime | None = None,
) -> DeterministicCollaborationMetrics:
    """
    Computes deterministic collaboration and blocker metrics from authorized MongoDB documents.

    Documented Lookback & Scoping Policy:
    1. Collaboration Messages:
       - Strictly excludes soft-deleted messages (is_deleted == False).
       - Bounded by lookback window [evidence_start, evidence_end] where evidence_start = now - lookback_days.
       - Distinct participants: Count of distinct sender_ids in active messages within the lookback window.
    2. Active / Unresolved Blockers:
       - Evaluated across authorized non-completed tasks.
       - Unresolved blockers created before the lookback window are INTENTIONALLY included because
         an unresolved blocker represents an active ongoing delivery bottleneck regardless of when it was first logged.
       - Stale blockers: Unresolved blockers with created_at strictly older than STALE_BLOCKER_THRESHOLD_DAYS (7 UTC days).
    3. Resolved Blockers & Resolution Velocity:
       - Evaluated for blockers with resolution timestamps within the lookback window (resolved_at >= evidence_start)
         or created within the lookback window to provide a bounded recent resolution velocity metric.
       - Average resolution hours: Computed strictly when both valid created_at and resolved_at timestamps exist
         and resolved_at >= created_at.
    4. Malformed Timestamp Resilience:
       - Unparseable timestamps, negative durations (resolved_at < created_at), and non-finite numbers
         are counted as invalid and excluded from averages without raising uncaught exceptions.
    """
    now_utc = _ensure_utc(now) or datetime.now(timezone.utc)
    evidence_start = now_utc - timedelta(days=lookback_days)
    evidence_end = now_utc
    stale_threshold = now_utc - timedelta(days=STALE_BLOCKER_THRESHOLD_DAYS)

    invalid_timestamps = 0
    analyzed_teams: set[str] = set()

    # 1. Process Messages (strictly active, non-deleted, within lookback window)
    active_message_count = 0
    active_senders: set[str] = set()

    for m in message_docs:
        # Strict soft-deletion check
        if m.get("is_deleted", False):
            continue

        team_id = str(m.get("team_id", "")).strip()
        if team_id:
            analyzed_teams.add(team_id)

        created_raw = m.get("created_at")
        created_dt = _ensure_utc(created_raw)
        if created_raw is not None and created_dt is None:
            invalid_timestamps += 1

        # Check lookback window if created_at is present
        if created_dt is not None:
            if created_dt < evidence_start or created_dt > evidence_end:
                continue

        active_message_count += 1
        sender_id = str(m.get("sender_id", "")).strip()
        if sender_id:
            active_senders.add(sender_id)

    # 2. Process Tasks and Blockers
    task_count_with_active_blockers = 0
    unresolved_blocker_count = 0
    resolved_blocker_count = 0
    stale_unresolved_blocker_count = 0
    resolution_durations_hours: list[float] = []

    for t in task_docs:
        team_id = str(t.get("team_id", "")).strip()
        if team_id:
            analyzed_teams.add(team_id)

        task_status = str(t.get("status", "todo")).strip().lower()
        is_task_completed = task_status == "completed"

        blockers = t.get("blockers") or []
        has_active_blocker = False

        if isinstance(blockers, list):
            for b in blockers:
                if not isinstance(b, dict):
                    continue

                is_resolved = bool(b.get("is_resolved", False))
                resolved_at_raw = b.get("resolved_at")
                resolved_dt = _ensure_utc(resolved_at_raw)
                if resolved_at_raw is not None and resolved_dt is None:
                    invalid_timestamps += 1

                created_raw = b.get("created_at")
                created_dt = _ensure_utc(created_raw)
                if created_raw is not None and created_dt is None:
                    invalid_timestamps += 1

                if is_resolved or resolved_dt is not None:
                    # Bounded resolved blocker policy: count resolved blockers occurring within lookback
                    if resolved_dt is not None and resolved_dt < evidence_start:
                        continue
                    if resolved_dt is None and created_dt is not None and created_dt < evidence_start:
                        continue

                    resolved_blocker_count += 1
                    # Compute resolution hours only if both valid timestamps exist
                    if created_dt is not None and resolved_dt is not None:
                        diff_seconds = (resolved_dt - created_dt).total_seconds()
                        if diff_seconds >= 0:
                            resolution_durations_hours.append(diff_seconds / 3600.0)
                        else:
                            invalid_timestamps += 1
                else:
                    if not is_task_completed:
                        unresolved_blocker_count += 1
                        has_active_blocker = True

                        if created_dt is not None:
                            # Stale: strictly older than 7 UTC days
                            if created_dt < stale_threshold:
                                stale_unresolved_blocker_count += 1

        if not is_task_completed and (task_status == "blocked" or has_active_blocker):
            task_count_with_active_blockers += 1

    avg_resolution_hours = (
        round(sum(resolution_durations_hours) / len(resolution_durations_hours), 2)
        if resolution_durations_hours
        else None
    )

    return DeterministicCollaborationMetrics(
        active_message_count=active_message_count,
        distinct_active_participant_count=len(active_senders),
        task_count_with_active_blockers=task_count_with_active_blockers,
        unresolved_blocker_count=unresolved_blocker_count,
        resolved_blocker_count=resolved_blocker_count,
        stale_unresolved_blocker_count=stale_unresolved_blocker_count,
        average_resolution_hours=avg_resolution_hours,
        invalid_timestamp_count=invalid_timestamps,
        analyzed_team_count=len(analyzed_teams),
        evidence_start=evidence_start,
        evidence_end=evidence_end,
        calculation_timestamp=now_utc,
    )


# =========================================================================
# 2. Specialist Structured Output Schema
# =========================================================================


class CollaborationFindingOutput(BaseModel):
    """
    Strict frozen Pydantic structured output returned by LLM completions for Collaboration Agent.
    Enforces evidence-grounded communication patterns, blocker observations, and dependency risks.
    Excludes chain-of-thought, employee rankings, sentiment scores, and punitive/medical claims.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=3000),
    ]
    communication_observations: list[
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
    dependency_risks: list[
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
# 3. Evidence Formatting & Snippet Helpers
# =========================================================================


def _format_message_snippet(doc: dict) -> str:
    """
    Builds a concise, safe summary snippet for a collaboration message.
    Strictly omits sender_id, credentials, and personal details to preserve privacy.
    """
    msg_id = str(doc.get("_id", "unknown"))
    created_dt = _ensure_utc(doc.get("created_at"))
    created_str = created_dt.strftime("%Y-%m-%d %H:%M UTC") if created_dt else "Unknown Date"
    content = str(doc.get("content", "")).strip()

    # Bounded snippet length
    content_snip = (
        content[:MAX_MESSAGE_SNIPPET_CHARS]
        if len(content) > MAX_MESSAGE_SNIPPET_CHARS
        else content
    )
    return f"[Message ID: {msg_id}] Created: {created_str} | Content: \"{content_snip}\""


def _format_task_blocker_snippet(doc: dict) -> str:
    """
    Builds a concise, safe summary snippet for a task with blockers.
    Strictly omits user_id and resolver_id to preserve privacy.
    """
    task_id = str(doc.get("_id", "unknown"))
    title = str(doc.get("title", "")).strip()
    status = str(doc.get("status", "todo")).strip()

    blockers = doc.get("blockers") or []
    blocker_lines = []
    if isinstance(blockers, list):
        for b in blockers:
            if not isinstance(b, dict):
                continue
            b_desc = str(b.get("description", "")).strip()
            is_res = bool(b.get("is_resolved", False))
            res_at = _ensure_utc(b.get("resolved_at"))
            created_at = _ensure_utc(b.get("created_at"))

            status_str = "RESOLVED" if is_res or res_at else "ACTIVE"
            created_str = created_at.strftime("%Y-%m-%d") if created_at else "N/A"
            res_str = f" on {res_at.strftime('%Y-%m-%d')}" if res_at else ""
            res_note = f" (Note: {str(b.get('resolution_note', ''))[:60]})" if b.get("resolution_note") else ""

            b_desc_bounded = b_desc[:MAX_BLOCKER_SNIPPET_CHARS]
            blocker_lines.append(f"[{status_str} since {created_str}{res_str}] {b_desc_bounded}{res_note}")

    blockers_text = " | ".join(blocker_lines) if blocker_lines else "No blockers recorded"
    return f"[Task ID: {task_id}] '{title}' (Status: {status}) | Blockers: {blockers_text}"


def _is_task_blocker_relevant(doc: dict, lookback_start: datetime) -> bool:
    """
    Determines if an authorized task document is relevant for collaboration blocker analysis:
    1. Tasks with status == 'blocked'
    2. Tasks containing an unresolved blocker (is_resolved == False and resolved_at is None, on non-completed tasks)
    3. Tasks containing a blocker resolved within the lookback window (resolved_at >= lookback_start or created_at >= lookback_start)
    """
    task_status = str(doc.get("status", "")).strip().lower()
    is_completed = task_status == "completed"
    if not is_completed and task_status == "blocked":
        return True

    blockers = doc.get("blockers") or []
    if isinstance(blockers, list) and blockers:
        for b in blockers:
            if not isinstance(b, dict):
                continue
            is_res = bool(b.get("is_resolved", False))
            res_dt = _ensure_utc(b.get("resolved_at"))
            created_dt = _ensure_utc(b.get("created_at"))

            # Active/unresolved blocker on non-completed task
            if not is_res and res_dt is None:
                if not is_completed:
                    return True
            else:
                # Resolved blocker within lookback window
                if res_dt is not None and res_dt >= lookback_start:
                    return True
                if res_dt is None and is_res and created_dt is not None and created_dt >= lookback_start:
                    return True
    return False


# =========================================================================
# 4. Specialist Evidence Collection Tools
# =========================================================================


class CollaborationMessageEvidenceTool(BaseAgentTool):
    """
    Deterministic async MongoDB evidence tool collecting active collaboration messages.
    Strictly queries only pre-scoped, authorized, non-deleted collaboration messages within the lookback window.
    """

    def __init__(
        self,
        database: Any,
        target_team_id: str | None = None,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        name: str = COLLABORATION_MESSAGE_TOOL_NAME,
        required_intent: AgentIntent = "collaboration_analysis",
        now_fn: Callable[[], datetime] | None = None,
    ):
        self.database = database
        self.target_team_id = str(target_team_id).strip() if target_team_id else None
        self.lookback_days = lookback_days
        self.now_fn = now_fn
        super().__init__(
            name=name,
            target_agent=COLLABORATION_AGENT_NAME,
            required_intent=required_intent,
            source_type="collaboration_message",
            handler=self._fetch_message_evidence,
        )

    async def _fetch_message_evidence(
        self, context: ExecutionContext
    ) -> list[EvidenceReference]:
        principal = context.principal
        if self.database is None:
            return []

        # Calculate database-side lookback window boundary [evidence_start, evidence_end]
        now_utc = self.now_fn() if self.now_fn is not None else datetime.now(timezone.utc)
        lookback_start = now_utc - timedelta(days=self.lookback_days)
        lookback_end = now_utc

        # 1. Build authoritative database query based on role, team scope, soft-deletion, and lookback
        filter_query: dict[str, Any] = {
            "is_deleted": False,
            "created_at": {
                "$gte": lookback_start,
                "$lte": lookback_end,
            },
        }

        if principal.role == "employee":
            if self.target_team_id:
                if principal.assigned_team_id and self.target_team_id != principal.assigned_team_id:
                    raise AgentAuthorizationError(
                        message=f"Employee cannot access team '{self.target_team_id}'",
                        safe_reason_code="EMPLOYEE_CROSS_TEAM_FORBIDDEN",
                        safe_message="Employees cannot request analyses for teams other than their assigned team",
                    )

            if not principal.assigned_team_id:
                return []

            team_id = self.target_team_id or principal.assigned_team_id
            team_oids: list[Any] = []
            if ObjectId.is_valid(team_id):
                team_oids.append(ObjectId(team_id))
            if team_id not in team_oids:
                team_oids.append(team_id)

            filter_query["team_id"] = {"$in": team_oids} if len(team_oids) > 1 else team_oids[0]

        elif principal.role == "manager":
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
            if self.target_team_id:
                admin_team_oids: list[Any] = []
                if ObjectId.is_valid(self.target_team_id):
                    admin_team_oids.append(ObjectId(self.target_team_id))
                if self.target_team_id not in admin_team_oids:
                    admin_team_oids.append(self.target_team_id)
                filter_query["team_id"] = {"$in": admin_team_oids} if len(admin_team_oids) > 1 else admin_team_oids[0]
        else:
            return []

        # 2. Query MongoDB collection directly with pre-filtering
        try:
            coll = self.database["collaboration_messages"]
            cursor = coll.find(filter_query)

            if hasattr(cursor, "to_list"):
                message_docs = await cursor.to_list(length=100)
            elif hasattr(cursor, "__aiter__"):
                message_docs = [doc async for doc in cursor]
            else:
                message_docs = [
                    d
                    for d in getattr(coll, "docs", [])
                    if self._match_doc(d, filter_query)
                ]
        except Exception as e:
            logger.warning("Database collaboration message query failed: %s", e)
            raise AgentToolExecutionError(
                message="Failed to query collaboration messages collection",
                safe_reason_code="DATABASE_ERROR",
            )

        # In-memory defense-in-depth: strictly filter out any soft-deleted messages or messages outside lookback
        active_messages = []
        for m in message_docs:
            if m.get("is_deleted", False):
                continue
            c_dt = _ensure_utc(m.get("created_at"))
            if c_dt is not None:
                if c_dt < lookback_start or c_dt > lookback_end:
                    continue
            active_messages.append(m)

        if not active_messages:
            return []

        evidence_refs: list[EvidenceReference] = []
        default_team = (
            principal.assigned_team_id
            if principal.role == "employee"
            else (
                principal.managed_team_ids[0]
                if principal.managed_team_ids
                else "workspace-org"
            )
        )

        for doc in active_messages[:MAX_MESSAGE_EVIDENCE_ITEMS]:
            msg_id = str(doc.get("_id", "unknown"))
            team_id_str = str(doc.get("team_id", default_team))
            snippet = _format_message_snippet(doc)

            ref = EvidenceReference(
                source_type="collaboration_message",
                record_id=msg_id,
                title=f"Collaboration Message {msg_id[:8]}",
                snippet=snippet[:1000],
                team_id=team_id_str[:64],
            )
            scope_decision = validate_evidence_team_scope(principal, ref)
            if scope_decision.allowed:
                evidence_refs.append(ref)

        return evidence_refs

    def _match_doc(self, doc: dict, filter_query: dict) -> bool:
        if not filter_query:
            return True
        if filter_query.get("is_deleted") is False and doc.get("is_deleted", False):
            return False
        if "created_at" in filter_query:
            c_query = filter_query["created_at"]
            if isinstance(c_query, dict):
                doc_dt = _ensure_utc(doc.get("created_at"))
                if doc_dt is not None:
                    if "$gte" in c_query and doc_dt < c_query["$gte"]:
                        return False
                    if "$lte" in c_query and doc_dt > c_query["$lte"]:
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


class CollaborationTaskBlockerEvidenceTool(BaseAgentTool):
    """
    Deterministic async MongoDB evidence tool collecting task blocker evidence.
    Exclusively queries the 'tasks' collection with a strict projection and in-memory blocker relevance filtering.
    Does NOT query the collaboration_messages collection.
    """

    def __init__(
        self,
        database: Any,
        target_team_id: str | None = None,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        name: str = COLLABORATION_TASK_BLOCKER_TOOL_NAME,
        required_intent: AgentIntent = "collaboration_analysis",
        now_fn: Callable[[], datetime] | None = None,
    ):
        self.database = database
        self.target_team_id = str(target_team_id).strip() if target_team_id else None
        self.lookback_days = lookback_days
        self.now_fn = now_fn
        super().__init__(
            name=name,
            target_agent=COLLABORATION_AGENT_NAME,
            required_intent=required_intent,
            source_type="task",
            handler=self._fetch_blocker_evidence,
        )

    async def _fetch_blocker_evidence(
        self, context: ExecutionContext
    ) -> list[EvidenceReference]:
        principal = context.principal
        if self.database is None:
            return []

        now_utc = self.now_fn() if self.now_fn is not None else datetime.now(timezone.utc)
        lookback_start = now_utc - timedelta(days=self.lookback_days)

        # 1. Build authoritative database task filters scoped strictly by role & team
        task_filter: dict[str, Any] = {}

        if principal.role == "employee":
            if self.target_team_id:
                if principal.assigned_team_id and self.target_team_id != principal.assigned_team_id:
                    raise AgentAuthorizationError(
                        message=f"Employee cannot access team '{self.target_team_id}'",
                        safe_reason_code="EMPLOYEE_CROSS_TEAM_FORBIDDEN",
                        safe_message="Employees cannot request analyses for teams other than their assigned team",
                    )

            if not principal.assigned_team_id:
                return []

            team_id = self.target_team_id or principal.assigned_team_id
            team_oids: list[Any] = []
            if ObjectId.is_valid(team_id):
                team_oids.append(ObjectId(team_id))
            if team_id not in team_oids:
                team_oids.append(team_id)

            task_filter["team_id"] = {"$in": team_oids} if len(team_oids) > 1 else team_oids[0]

        elif principal.role == "manager":
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
                    return []
                target_teams = principal.managed_team_ids

            managed_oids: list[Any] = []
            for tid in target_teams:
                if ObjectId.is_valid(tid):
                    managed_oids.append(ObjectId(tid))
                if tid not in managed_oids:
                    managed_oids.append(tid)

            task_filter["team_id"] = {"$in": managed_oids} if len(managed_oids) > 1 else managed_oids[0]

        elif principal.role == "admin":
            if self.target_team_id:
                admin_team_oids: list[Any] = []
                if ObjectId.is_valid(self.target_team_id):
                    admin_team_oids.append(ObjectId(self.target_team_id))
                if self.target_team_id not in admin_team_oids:
                    admin_team_oids.append(self.target_team_id)
                task_filter["team_id"] = {"$in": admin_team_oids} if len(admin_team_oids) > 1 else admin_team_oids[0]

        # 2. Strict MongoDB projection: retrieve only minimal fields required for blocker analysis
        task_projection = {
            "_id": 1,
            "team_id": 1,
            "title": 1,
            "status": 1,
            "blockers": 1,
        }

        # 3. Query ONLY the tasks collection (zero queries to collaboration_messages)
        try:
            tasks_coll = self.database["tasks"]
            t_cursor = tasks_coll.find(task_filter, task_projection)
            if hasattr(t_cursor, "to_list"):
                task_docs = await t_cursor.to_list(length=100)
            elif hasattr(t_cursor, "__aiter__"):
                task_docs = [doc async for doc in t_cursor]
            else:
                task_docs = [
                    d
                    for d in getattr(tasks_coll, "docs", [])
                    if self._match_doc(d, task_filter)
                ]
        except Exception as e:
            logger.warning("Database task/blocker query failed: %s", e)
            raise AgentToolExecutionError(
                message="Failed to query task/blocker collection",
                safe_reason_code="DATABASE_ERROR",
            )

        # 4. In-memory blocker relevance filtering
        # Excludes tasks without blockers and without blocked status, and old resolved blockers
        relevant_task_docs = [
            t for t in task_docs if _is_task_blocker_relevant(t, lookback_start)
        ]

        # 5. Compute Deterministic Blocker Metrics strictly from relevant task records
        metrics = compute_deterministic_collaboration_metrics(
            message_docs=[],
            task_docs=relevant_task_docs,
            lookback_days=self.lookback_days,
            now=now_utc,
        )

        evidence_refs: list[EvidenceReference] = []
        summary_team_id = (
            principal.assigned_team_id
            if principal.role == "employee"
            else (
                principal.managed_team_ids[0]
                if principal.managed_team_ids
                else "workspace-org"
            )
        )

        # Aggregated Metrics Summary Reference
        evidence_refs.append(
            EvidenceReference(
                source_type="task",
                record_id="collaboration-metrics-summary",
                title="Aggregated Task Blocker Metrics",
                snippet=metrics.to_summary_text(),
                team_id=summary_team_id,
            )
        )

        # Individual Task Blocker References (strictly relevant tasks with blockers)
        blocker_refs: list[EvidenceReference] = []
        for doc in relevant_task_docs:
            task_id = str(doc.get("_id", "unknown"))
            team_id_str = str(doc.get("team_id", summary_team_id))
            title = str(doc.get("title", "Task Record")).strip()
            snippet = _format_task_blocker_snippet(doc)

            ref = EvidenceReference(
                source_type="task",
                record_id=task_id,
                title=f"Task Blocker: {title[:150]}",
                snippet=snippet[:1000],
                team_id=team_id_str[:64],
            )
            scope_decision = validate_evidence_team_scope(principal, ref)
            if scope_decision.allowed:
                blocker_refs.append(ref)

        evidence_refs.extend(blocker_refs[:MAX_BLOCKER_EVIDENCE_ITEMS])
        return evidence_refs

    def _match_doc(self, doc: dict, filter_query: dict) -> bool:
        if not filter_query:
            return True
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
# 5. System Prompt, Definition, and Registration Helpers
# =========================================================================

COLLABORATION_SYSTEM_PROMPT = """You are the Collaboration Specialist Agent for an enterprise workforce intelligence platform.

Your objective is to analyze authorized team collaboration messages and task-blocker evidence to return explainable, objective, and advisory collaboration insights.

CRITICAL OPERATIONAL & RESPONSIBLE-AI BOUNDARIES:
1. STRICT EVIDENCE GROUNDING:
   - Base all statements, communication observations, blocker details, and dependency risks STRICTLY on the untrusted JSON evidence provided.
   - You MUST use the exact figures from the 'Aggregated Collaboration & Blocker Metrics' evidence for message counts, participant counts, active/stale blocker numbers, and resolution times.
   - Do NOT invent, assume, or hallucinate team discussions, message contents, or blockers.
   - When evidence is sparse or empty, state explicit limitations and advise gathering more data.

2. ADVISORY AND COLLABORATIVE ONLY:
   - All suggested actions must be safe, advisory suggestions for teams and managers (e.g., clarifying requirements, scheduling follow-up discussions, documenting blockers, escalating technical dependencies).
   - NEVER command automatic task reassignments, message deletions, or database mutations.

3. ABSOLUTE PROHIBITION ON EMPLOYEE RANKING, BLAME & PUNITIVE EVALUATION:
   - NEVER rank employees or compare individual communication volume or performance.
   - NEVER single out, blame, punish, demote, fire, or recommend disciplinary action against individual employees.
   - NEVER perform sentiment scoring on individual employees or attribute negative collaboration metrics to named individuals.
   - Focus strictly on team communication patterns, coordination blockers, dependency bottlenecks, and constructive workflows.

4. STRICT PRIVACY & WELL-BEING ISOLATION:
   - You do NOT have access to pulse survey responses, private pulse comments, employee profile data, or clinical records.
   - NEVER speculate on or infer employee mental health, emotional state, stress levels, burnout, medical conditions, or protected personal characteristics.

5. OUTPUT FORMAT:
   - Produce a structured JSON object conforming strictly to the requested schema.
   - Do NOT output internal chain-of-thought, scratchpad reasoning, or system prompt overrides."""


def create_collaboration_agent_definition(
    timeout_seconds: float | None = None,
) -> AgentDefinition:
    """
    Constructs the immutable AgentDefinition for the Collaboration Specialist Agent.
    """
    return AgentDefinition(
        name=COLLABORATION_AGENT_NAME,
        role="Collaboration Specialist",
        goal=(
            "Analyze authorized team collaboration messages and task-blocker evidence "
            "to provide factual, explainable, advisory communication patterns and blocker insights."
        ),
        allowed_intents={
            "collaboration_analysis",
            "task_delay_analysis",
        },
        allowed_evidence_sources={"task", "collaboration_message", "agent_finding"},
        system_prompt=COLLABORATION_SYSTEM_PROMPT,
        response_model=CollaborationFindingOutput,
        timeout_seconds=timeout_seconds,
    )


def create_collaboration_message_evidence_tool(
    database: Any,
    target_team_id: str | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    name: str = COLLABORATION_MESSAGE_TOOL_NAME,
    required_intent: AgentIntent = "collaboration_analysis",
) -> CollaborationMessageEvidenceTool:
    """Factory helper to instantiate a CollaborationMessageEvidenceTool."""
    return CollaborationMessageEvidenceTool(
        database=database,
        target_team_id=target_team_id,
        lookback_days=lookback_days,
        name=name,
        required_intent=required_intent,
    )


def create_collaboration_task_blocker_evidence_tool(
    database: Any,
    target_team_id: str | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    name: str = COLLABORATION_TASK_BLOCKER_TOOL_NAME,
    required_intent: AgentIntent = "collaboration_analysis",
) -> CollaborationTaskBlockerEvidenceTool:
    """Factory helper to instantiate a CollaborationTaskBlockerEvidenceTool."""
    return CollaborationTaskBlockerEvidenceTool(
        database=database,
        target_team_id=target_team_id,
        lookback_days=lookback_days,
        name=name,
        required_intent=required_intent,
    )


def register_collaboration_agent(
    runtime: AgentRuntime,
    database: Any = None,
    target_team_id: str | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    timeout_seconds: float | None = None,
) -> None:
    """
    Registers the Collaboration Specialist Agent and its evidence tools into the provided AgentRuntime.
    """
    agent_def = create_collaboration_agent_definition(timeout_seconds=timeout_seconds)
    runtime.register_agent(agent_def)

    if database is not None:
        for intent in ("collaboration_analysis", "task_delay_analysis"):
            msg_tool = create_collaboration_message_evidence_tool(
                database=database,
                target_team_id=target_team_id,
                lookback_days=lookback_days,
                name=f"{COLLABORATION_MESSAGE_TOOL_NAME}_{intent}",
                required_intent=intent,  # type: ignore
            )
            runtime.register_tool(msg_tool)

            blocker_tool = create_collaboration_task_blocker_evidence_tool(
                database=database,
                target_team_id=target_team_id,
                lookback_days=lookback_days,
                name=f"{COLLABORATION_TASK_BLOCKER_TOOL_NAME}_{intent}",
                required_intent=intent,  # type: ignore
            )
            runtime.register_tool(blocker_tool)


async def execute_collaboration_agent(
    runtime: AgentRuntime,
    request: AgentRequest,
    principal: AuthenticatedPrincipal,
    tool_names: list[str] | None = None,
) -> AgentResponse:
    """
    Collaboration-specific execution helper that explicitly supplies the canonical
    collaboration evidence tools when invoking the runtime.
    """
    explicit_tools = (
        tool_names
        if tool_names is not None
        else get_collaboration_tool_names(request.intent)
    )
    return await runtime.execute_agent(
        request=request,
        principal=principal,
        tool_names=explicit_tools,
    )
