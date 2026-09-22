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
from backend.app.modules.pulse_surveys.constants import (
    MINIMUM_AGGREGATE_RESPONSES,
    PULSE_COLLECTION_NAME,
    TEAMS_COLLECTION_NAME,
    get_current_week_start,
)

logger = logging.getLogger("remote_workforce.agents.wellbeing")

WELLBEING_AGENT_NAME: AgentName = "wellbeing"
WELLBEING_PULSE_TOOL_NAME = "wellbeing_pulse_evidence"

# Authoritative privacy-preserving minimum response threshold (k-anonymity)
MINIMUM_PULSE_RESPONSES_THRESHOLD: int = MINIMUM_AGGREGATE_RESPONSES

# Bounded lookback window configuration (in UTC weeks)
MIN_WEEKS_LOOKBACK: int = 1
MAX_WEEKS_LOOKBACK: int = 12
DEFAULT_WEEKS_LOOKBACK: int = 4

# Maximum evidence items to prevent prompt payload ballooning
MAX_WELLBEING_EVIDENCE_ITEMS: int = 10


def get_wellbeing_tool_names(intent: AgentIntent = "wellbeing_analysis") -> list[str]:
    """Returns the canonical explicit tool name for a given wellbeing intent."""
    return [f"{WELLBEING_PULSE_TOOL_NAME}_{intent}"]


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


def _parse_rating_value(raw_val: Any) -> float | None:
    """
    Safely parses a pulse survey rating value.
    Rejects booleans, non-numeric strings, NaNs, infinities, and out-of-range values (< 1.0 or > 5.0).
    Returns float value if valid, or None.
    """
    if raw_val is None:
        return None
    if isinstance(raw_val, bool):
        return None
    try:
        val = float(raw_val)
        if math.isnan(val) or math.isinf(val):
            return None
        if val < 1.0 or val > 5.0:
            return None
        return val
    except (ValueError, TypeError):
        return None


def _normalize_team_ids(team_ids: list[str]) -> list[Any]:
    """Builds a MongoDB filter list supporting both ObjectId and string representations."""
    oids: list[Any] = []
    for tid in team_ids:
        tid_str = str(tid).strip()
        if not tid_str:
            continue
        if ObjectId.is_valid(tid_str):
            oids.append(ObjectId(tid_str))
        if tid_str not in oids:
            oids.append(tid_str)
    return oids


# =========================================================================
# 1. Deterministic Metrics Models & Calculation
# =========================================================================


class WeeklyTeamPulseAggregate(BaseModel):
    """
    Factual, deterministic aggregate metrics for a single team in a single UTC week.
    Strictly preserves k-anonymity privacy by withholding averages when response_count < 3
    or when valid rating count for a specific metric < 3.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    team_id: str
    team_name: str | None = None
    week_start: datetime
    response_count: int
    is_privacy_threshold_met: bool
    average_workload_manageability: float | None = None
    average_work_life_balance: float | None = None
    average_team_support: float | None = None
    average_engagement: float | None = None
    invalid_rating_count: int = 0

    def to_summary_text(self) -> str:
        week_str = self.week_start.strftime("%Y-%m-%d UTC")
        t_name = f"'{self.team_name}'" if self.team_name else f"Team {self.team_id}"

        if not self.is_privacy_threshold_met:
            return (
                f"[{t_name} | Week {week_str}] Responses: fewer than minimum required "
                f"(Threshold: {MINIMUM_PULSE_RESPONSES_THRESHOLD}) — INSUFFICIENT DATA. "
                "Aggregated metrics suppressed to protect employee anonymity."
            )

        wm = f"{self.average_workload_manageability:.2f}" if self.average_workload_manageability is not None else "N/A"
        wlb = f"{self.average_work_life_balance:.2f}" if self.average_work_life_balance is not None else "N/A"
        ts = f"{self.average_team_support:.2f}" if self.average_team_support is not None else "N/A"
        eng = f"{self.average_engagement:.2f}" if self.average_engagement is not None else "N/A"
        inv_note = f" (Excluded {self.invalid_rating_count} invalid ratings)" if self.invalid_rating_count > 0 else ""

        return (
            f"[{t_name} | Week {week_str}] Responses: {self.response_count} | "
            f"Avg Workload Manageability: {wm}/5, Avg Work-Life Balance: {wlb}/5, "
            f"Avg Team Support: {ts}/5, Avg Engagement: {eng}/5{inv_note}"
        )


class DeterministicWellbeingMetrics(BaseModel):
    """
    Comprehensive, deterministic well-being metrics computed directly in Python
    from pre-filtered, authorized MongoDB pulse records prior to LLM reasoning.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    total_responses_analyzed: int = 0
    total_privacy_safe_weeks: int = 0
    total_insufficient_data_weeks: int = 0
    weekly_aggregates: list[WeeklyTeamPulseAggregate] = Field(default_factory=list)
    workload_manageability_trend: float | None = None
    work_life_balance_trend: float | None = None
    team_support_trend: float | None = None
    engagement_trend: float | None = None
    overall_average_workload_manageability: float | None = None
    overall_average_work_life_balance: float | None = None
    overall_average_team_support: float | None = None
    overall_average_engagement: float | None = None
    invalid_rating_count: int = 0
    analyzed_team_count: int = 0
    calculation_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_summary_text(self) -> str:
        if not self.weekly_aggregates:
            return "No pulse survey response data available for the analyzed period."

        trends_parts = []
        if self.workload_manageability_trend is not None:
            trends_parts.append(f"Workload Manageability Delta: {self.workload_manageability_trend:+.2f}")
        if self.work_life_balance_trend is not None:
            trends_parts.append(f"Work-Life Balance Delta: {self.work_life_balance_trend:+.2f}")
        if self.team_support_trend is not None:
            trends_parts.append(f"Team Support Delta: {self.team_support_trend:+.2f}")
        if self.engagement_trend is not None:
            trends_parts.append(f"Engagement Delta: {self.engagement_trend:+.2f}")

        trend_str = "; ".join(trends_parts) if trends_parts else "No multi-week trend available (requires at least 2 privacy-safe consecutive weeks for the team)"

        wm = f"{self.overall_average_workload_manageability:.2f}" if self.overall_average_workload_manageability is not None else "N/A"
        wlb = f"{self.overall_average_work_life_balance:.2f}" if self.overall_average_work_life_balance is not None else "N/A"
        ts = f"{self.overall_average_team_support:.2f}" if self.overall_average_team_support is not None else "N/A"
        eng = f"{self.overall_average_engagement:.2f}" if self.overall_average_engagement is not None else "N/A"

        if self.total_privacy_safe_weeks == 0 and self.total_responses_analyzed > 0:
            total_resp_str = f"fewer than minimum required ({MINIMUM_PULSE_RESPONSES_THRESHOLD})"
        else:
            total_resp_str = str(self.total_responses_analyzed)

        header = (
            f"Analyzed Teams: {self.analyzed_team_count} | Total Responses: {total_resp_str} | "
            f"Privacy-Safe Weeks: {self.total_privacy_safe_weeks}, Insufficient-Data Weeks: {self.total_insufficient_data_weeks} | "
            f"Overall Averages across safe weeks — Workload: {wm}/5, Work-Life Balance: {wlb}/5, Support: {ts}/5, Engagement: {eng}/5 | "
            f"Week-over-Week Trends: {trend_str}"
        )

        details = "\n".join(f"- {w.to_summary_text()}" for w in self.weekly_aggregates)
        return f"{header}\n\nWeekly Breakdown:\n{details}"


def compute_deterministic_wellbeing_metrics(
    pulse_docs: list[dict],
    team_names_map: dict[str, str] | None = None,
    min_threshold: int = MINIMUM_PULSE_RESPONSES_THRESHOLD,
    now: datetime | None = None,
    weeks_lookback: int = DEFAULT_WEEKS_LOOKBACK,
) -> DeterministicWellbeingMetrics:
    """
    Computes deterministic well-being metrics from authorized MongoDB pulse documents.

    Privacy & Mathematical Guarantee:
    1. Independent Grouping: Records are grouped strictly by (team_id, week_start).
    2. k-Anonymity Privacy Threshold (Overall & Per-Metric):
       - If a (team_id, week_start) bucket has fewer than `min_threshold` total responses (default 3),
         is_privacy_threshold_met = False, and NO averages are computed for that bucket.
       - If total responses >= min_threshold, each metric independently requires at least
         `min_threshold` valid numeric (1-5) ratings. If valid ratings for a metric < min_threshold,
         that specific metric average is strictly set to None.
    3. Invalid Value Resilience:
       - Non-numeric, boolean, NaN, inf, or out-of-range (<1 or >5) values are counted as invalid
         and excluded from metric calculations without raising uncaught exceptions.
    4. Week-over-Week Trends:
       - Calculated per-team as the difference (newest - previous) between the two most recent
         privacy-safe weeks for that team.
       - A metric trend delta is computed ONLY when BOTH weeks contain non-None privacy-safe averages
         for that specific metric.
       - Cross-team weeks are NEVER compared against each other.
    5. Overall Averages:
       - Computed strictly across all privacy-safe metric values.
    """
    team_names = team_names_map or {}
    now_utc = _ensure_utc(now) or datetime.now(timezone.utc)
    current_ws = get_current_week_start(now_utc)
    bounded_lookback = min(max(int(weeks_lookback), MIN_WEEKS_LOOKBACK), MAX_WEEKS_LOOKBACK)
    earliest_ws = current_ws - timedelta(weeks=max(bounded_lookback - 1, 0))

    # Buckets: (team_id_str, week_start_dt) -> list of docs
    buckets: dict[tuple[str, datetime], list[dict]] = {}
    distinct_teams: set[str] = set()

    for doc in pulse_docs:
        team_id_raw = doc.get("team_id")
        if not team_id_raw:
            continue
        team_id_str = str(team_id_raw).strip()
        if not team_id_str:
            continue
        distinct_teams.add(team_id_str)

        ws_raw = doc.get("week_start")
        ws_dt = _ensure_utc(ws_raw)
        if ws_dt is None:
            continue
        # Normalize to Monday 00:00:00 UTC using authoritative helper
        ws_normalized = get_current_week_start(ws_dt)

        # Defense-in-depth: enforce lower and upper week boundaries
        if ws_normalized < earliest_ws or ws_normalized > current_ws:
            continue

        key = (team_id_str, ws_normalized)
        if key not in buckets:
            buckets[key] = []
        buckets[key].append(doc)

    weekly_aggregates: list[WeeklyTeamPulseAggregate] = []
    total_responses = 0
    total_privacy_safe_weeks = 0
    total_insufficient_data_weeks = 0
    total_invalid_ratings = 0

    safe_wm_averages: list[float] = []
    safe_wlb_averages: list[float] = []
    safe_ts_averages: list[float] = []
    safe_eng_averages: list[float] = []

    # Sort buckets chronologically descending (newest week first), then by team_id
    sorted_keys = sorted(buckets.keys(), key=lambda k: (k[1], k[0]), reverse=True)

    for team_id_str, ws_dt in sorted_keys:
        docs = buckets[(team_id_str, ws_dt)]
        resp_count = len(docs)
        total_responses += resp_count
        team_name = team_names.get(team_id_str)

        invalid_count = 0
        wm_vals: list[float] = []
        wlb_vals: list[float] = []
        ts_vals: list[float] = []
        eng_vals: list[float] = []

        for d in docs:
            for field_name, target_list in (
                ("workload_manageability", wm_vals),
                ("work_life_balance", wlb_vals),
                ("team_support", ts_vals),
                ("engagement", eng_vals),
            ):
                raw = d.get(field_name)
                parsed = _parse_rating_value(raw)
                if parsed is not None:
                    target_list.append(parsed)
                elif raw is not None:
                    invalid_count += 1

        total_invalid_ratings += invalid_count

        if resp_count < min_threshold:
            total_insufficient_data_weeks += 1
            weekly_aggregates.append(
                WeeklyTeamPulseAggregate(
                    team_id=team_id_str,
                    team_name=team_name,
                    week_start=ws_dt,
                    response_count=resp_count,
                    is_privacy_threshold_met=False,
                    average_workload_manageability=None,
                    average_work_life_balance=None,
                    average_team_support=None,
                    average_engagement=None,
                    invalid_rating_count=invalid_count,
                )
            )
        else:
            # Overall team/week response threshold is met.
            # Enforce PER-METRIC privacy threshold (each metric must independently have >= min_threshold valid ratings)
            avg_wm = round(sum(wm_vals) / len(wm_vals), 2) if len(wm_vals) >= min_threshold else None
            avg_wlb = round(sum(wlb_vals) / len(wlb_vals), 2) if len(wlb_vals) >= min_threshold else None
            avg_ts = round(sum(ts_vals) / len(ts_vals), 2) if len(ts_vals) >= min_threshold else None
            avg_eng = round(sum(eng_vals) / len(eng_vals), 2) if len(eng_vals) >= min_threshold else None

            has_at_least_one_safe_metric = any(
                m is not None for m in (avg_wm, avg_wlb, avg_ts, avg_eng)
            )

            if has_at_least_one_safe_metric:
                total_privacy_safe_weeks += 1
                if avg_wm is not None:
                    safe_wm_averages.append(avg_wm)
                if avg_wlb is not None:
                    safe_wlb_averages.append(avg_wlb)
                if avg_ts is not None:
                    safe_ts_averages.append(avg_ts)
                if avg_eng is not None:
                    safe_eng_averages.append(avg_eng)
            else:
                total_insufficient_data_weeks += 1

            weekly_aggregates.append(
                WeeklyTeamPulseAggregate(
                    team_id=team_id_str,
                    team_name=team_name,
                    week_start=ws_dt,
                    response_count=resp_count,
                    is_privacy_threshold_met=has_at_least_one_safe_metric,
                    average_workload_manageability=avg_wm,
                    average_work_life_balance=avg_wlb,
                    average_team_support=avg_ts,
                    average_engagement=avg_eng,
                    invalid_rating_count=invalid_count,
                )
            )

    # Week-over-week trends: calculated per-team to prevent cross-team delta contamination
    wm_trend = None
    wlb_trend = None
    ts_trend = None
    eng_trend = None

    # Group privacy-safe weeks by team_id
    team_safe_weeks: dict[str, list[WeeklyTeamPulseAggregate]] = {}
    for w in weekly_aggregates:
        if w.is_privacy_threshold_met:
            if w.team_id not in team_safe_weeks:
                team_safe_weeks[w.team_id] = []
            team_safe_weeks[w.team_id].append(w)

    # If single team analyzed or for primary team, compute per-metric trend between 2 most recent weeks
    if len(team_safe_weeks) == 1:
        primary_tid = list(team_safe_weeks.keys())[0]
        t_weeks = team_safe_weeks[primary_tid]
        if len(t_weeks) >= 2:
            newest = t_weeks[0]
            prev = t_weeks[1]
            if newest.average_workload_manageability is not None and prev.average_workload_manageability is not None:
                wm_trend = round(newest.average_workload_manageability - prev.average_workload_manageability, 2)
            if newest.average_work_life_balance is not None and prev.average_work_life_balance is not None:
                wlb_trend = round(newest.average_work_life_balance - prev.average_work_life_balance, 2)
            if newest.average_team_support is not None and prev.average_team_support is not None:
                ts_trend = round(newest.average_team_support - prev.average_team_support, 2)
            if newest.average_engagement is not None and prev.average_engagement is not None:
                eng_trend = round(newest.average_engagement - prev.average_engagement, 2)
    elif len(team_safe_weeks) > 1:
        # Multi-team org view: calculate average trend across teams that have >= 2 safe weeks
        wm_deltas, wlb_deltas, ts_deltas, eng_deltas = [], [], [], []
        for tid, t_weeks in team_safe_weeks.items():
            if len(t_weeks) >= 2:
                newest = t_weeks[0]
                prev = t_weeks[1]
                if newest.average_workload_manageability is not None and prev.average_workload_manageability is not None:
                    wm_deltas.append(newest.average_workload_manageability - prev.average_workload_manageability)
                if newest.average_work_life_balance is not None and prev.average_work_life_balance is not None:
                    wlb_deltas.append(newest.average_work_life_balance - prev.average_work_life_balance)
                if newest.average_team_support is not None and prev.average_team_support is not None:
                    ts_deltas.append(newest.average_team_support - prev.average_team_support)
                if newest.average_engagement is not None and prev.average_engagement is not None:
                    eng_deltas.append(newest.average_engagement - prev.average_engagement)

        if wm_deltas:
            wm_trend = round(sum(wm_deltas) / len(wm_deltas), 2)
        if wlb_deltas:
            wlb_trend = round(sum(wlb_deltas) / len(wlb_deltas), 2)
        if ts_deltas:
            ts_trend = round(sum(ts_deltas) / len(ts_deltas), 2)
        if eng_deltas:
            eng_trend = round(sum(eng_deltas) / len(eng_deltas), 2)

    overall_wm = round(sum(safe_wm_averages) / len(safe_wm_averages), 2) if safe_wm_averages else None
    overall_wlb = round(sum(safe_wlb_averages) / len(safe_wlb_averages), 2) if safe_wlb_averages else None
    overall_ts = round(sum(safe_ts_averages) / len(safe_ts_averages), 2) if safe_ts_averages else None
    overall_eng = round(sum(safe_eng_averages) / len(safe_eng_averages), 2) if safe_eng_averages else None

    return DeterministicWellbeingMetrics(
        total_responses_analyzed=total_responses,
        total_privacy_safe_weeks=total_privacy_safe_weeks,
        total_insufficient_data_weeks=total_insufficient_data_weeks,
        weekly_aggregates=weekly_aggregates,
        workload_manageability_trend=wm_trend,
        work_life_balance_trend=wlb_trend,
        team_support_trend=ts_trend,
        engagement_trend=eng_trend,
        overall_average_workload_manageability=overall_wm,
        overall_average_work_life_balance=overall_wlb,
        overall_average_team_support=overall_ts,
        overall_average_engagement=overall_eng,
        invalid_rating_count=total_invalid_ratings,
        analyzed_team_count=len(distinct_teams),
        calculation_timestamp=now_utc,
    )


# =========================================================================
# 2. Specialist Structured Output Schema
# =========================================================================


class WellbeingFindingOutput(BaseModel):
    """
    Strict Pydantic structured output returned by LLM completions for Wellbeing Agent.
    Enforces privacy-preserving, evidence-based team well-being observations.
    Strictly forbids chain-of-thought, respondent identities, and punitive/clinical claims.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=3000),
    ]
    aggregate_observations: list[
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
        ]
    ] = Field(default_factory=list, max_length=20)
    trend_observations: list[
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
# 3. Wellbeing Evidence Collection Tool
# =========================================================================


class WellbeingPulseEvidenceTool(BaseAgentTool):
    """
    Deterministic async MongoDB evidence tool for the Well-being Agent.
    Strictly queries only pre-scoped, authorized pulse records based on the authenticated principal.
    Enforces minimal projection and k-anonymity privacy protection.
    """

    def __init__(
        self,
        database: Any,
        target_team_id: str | None = None,
        weeks_lookback: int = DEFAULT_WEEKS_LOOKBACK,
        name: str = WELLBEING_PULSE_TOOL_NAME,
        required_intent: AgentIntent = "wellbeing_analysis",
    ):
        self.database = database
        self.target_team_id = str(target_team_id).strip() if target_team_id else None

        # Bounded lookback validation
        if weeks_lookback is None:
            lookback = DEFAULT_WEEKS_LOOKBACK
        else:
            try:
                lookback = int(weeks_lookback)
            except (ValueError, TypeError):
                lookback = DEFAULT_WEEKS_LOOKBACK
        self.weeks_lookback = min(max(lookback, MIN_WEEKS_LOOKBACK), MAX_WEEKS_LOOKBACK)

        super().__init__(
            name=name,
            target_agent=WELLBEING_AGENT_NAME,
            required_intent=required_intent,
            source_type="pulse_summary",
            handler=self._fetch_pulse_evidence,
        )

    async def _fetch_pulse_evidence(
        self, context: ExecutionContext
    ) -> list[EvidenceReference]:
        principal = context.principal
        if self.database is None:
            return []

        # 1. Authoritative Role & Team Filtering
        filter_query: dict[str, Any] = {}

        if principal.role == "employee":
            if self.target_team_id:
                if principal.assigned_team_id and self.target_team_id != principal.assigned_team_id:
                    raise AgentAuthorizationError(
                        message=f"Employee cannot access team '{self.target_team_id}'",
                        safe_reason_code="EMPLOYEE_CROSS_TEAM_FORBIDDEN",
                        safe_message="Employees cannot request analyses for teams other than their assigned team",
                    )

            if not principal.assigned_team_id:
                # Unassigned employee safely returns empty evidence
                return []

            team_id = self.target_team_id or principal.assigned_team_id
            team_oids = _normalize_team_ids([team_id])
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
                    # Manager without managed teams safely returns empty candidate set
                    return []
                target_teams = principal.managed_team_ids

            managed_oids = _normalize_team_ids(target_teams)
            filter_query["team_id"] = {"$in": managed_oids} if len(managed_oids) > 1 else managed_oids[0]

        elif principal.role == "admin":
            if self.target_team_id:
                admin_oids = _normalize_team_ids([self.target_team_id])
                filter_query["team_id"] = {"$in": admin_oids} if len(admin_oids) > 1 else admin_oids[0]
            else:
                filter_query = {}
        else:
            return []

        # 2. Add strict lower and upper time boundary filters
        now_utc = datetime.now(timezone.utc)
        current_ws = get_current_week_start(now_utc)
        earliest_ws = current_ws - timedelta(weeks=max(self.weeks_lookback - 1, 0))
        filter_query["week_start"] = {"$gte": earliest_ws, "$lte": current_ws}

        # 3. Query MongoDB with STRICT minimal projection
        # NEVER project user_id, optional_comment, edit_history, submitted_at, or credentials
        strict_projection = {
            "_id": 0,
            "team_id": 1,
            "week_start": 1,
            "workload_manageability": 1,
            "work_life_balance": 1,
            "team_support": 1,
            "engagement": 1,
        }

        try:
            pulse_collection = self.database[PULSE_COLLECTION_NAME]
            cursor = pulse_collection.find(filter_query, strict_projection)

            if hasattr(cursor, "to_list"):
                pulse_docs = await cursor.to_list(length=1000)
            elif hasattr(cursor, "__aiter__"):
                pulse_docs = [doc async for doc in cursor]
            else:
                pulse_docs = [
                    d
                    for d in getattr(pulse_collection, "docs", [])
                    if self._match_doc(d, filter_query)
                ]
        except Exception as e:
            logger.warning("Database pulse query failed: %s", e)
            raise AgentToolExecutionError(
                message="Failed to query weekly pulse collection",
                safe_reason_code="DATABASE_ERROR",
            )

        # 4. Fetch team names for clear provenance
        team_names_map: dict[str, str] = {}
        try:
            teams_collection = self.database[TEAMS_COLLECTION_NAME]
            t_cursor = teams_collection.find({}, {"name": 1})
            if hasattr(t_cursor, "to_list"):
                team_records = await t_cursor.to_list(length=500)
            elif hasattr(t_cursor, "__aiter__"):
                team_records = [t async for t in t_cursor]
            else:
                team_records = list(getattr(teams_collection, "docs", []))
            for t in team_records:
                tid_str = str(t.get("_id", "")).strip()
                t_name = str(t.get("name", "")).strip()
                if tid_str and t_name:
                    team_names_map[tid_str] = t_name
        except Exception:
            pass

        # 5. Compute deterministic metrics from collected documents
        metrics = compute_deterministic_wellbeing_metrics(
            pulse_docs=pulse_docs,
            team_names_map=team_names_map,
            min_threshold=MINIMUM_PULSE_RESPONSES_THRESHOLD,
            now=now_utc,
            weeks_lookback=self.weeks_lookback,
        )

        # 6. Build structured, privacy-safe EvidenceReference records
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

        # Primary summary reference containing overall computed metrics
        primary_ref = EvidenceReference(
            source_type="pulse_summary",
            record_id="wellbeing-pulse-metrics-summary",
            title="Aggregated Team Well-being Metrics & Trends",
            snippet=metrics.to_summary_text()[:1000],
            team_id=summary_team_id,
        )
        scope_decision = validate_evidence_team_scope(principal, primary_ref)
        if scope_decision.allowed:
            evidence_refs.append(primary_ref)

        # Weekly team aggregate references (bounded by MAX_WELLBEING_EVIDENCE_ITEMS)
        for weekly_agg in metrics.weekly_aggregates[:MAX_WELLBEING_EVIDENCE_ITEMS]:
            week_str = weekly_agg.week_start.strftime("%Y-%m-%d")
            t_name = weekly_agg.team_name or f"Team-{weekly_agg.team_id}"
            rec_id = f"pulse-agg-{weekly_agg.team_id}-{week_str}"

            ref = EvidenceReference(
                source_type="pulse_summary",
                record_id=rec_id[:64],
                title=f"Weekly Pulse Aggregate: {t_name} ({week_str})"[:200],
                snippet=weekly_agg.to_summary_text()[:1000],
                team_id=weekly_agg.team_id[:64],
            )
            scope_decision = validate_evidence_team_scope(principal, ref)
            if scope_decision.allowed:
                evidence_refs.append(ref)

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
        if "week_start" in filter_query:
            ws_cond = filter_query["week_start"]
            doc_ws = _ensure_utc(doc.get("week_start"))
            if isinstance(ws_cond, dict):
                if "$gte" in ws_cond:
                    gte_val = _ensure_utc(ws_cond["$gte"])
                    if doc_ws is None or (gte_val is not None and doc_ws < gte_val):
                        return False
                if "$lte" in ws_cond:
                    lte_val = _ensure_utc(ws_cond["$lte"])
                    if doc_ws is None or (lte_val is not None and doc_ws > lte_val):
                        return False
            elif doc_ws != _ensure_utc(ws_cond):
                return False
        return True


# =========================================================================
# 4. System Prompt, Definition, and Execution Helpers
# =========================================================================

WELLBEING_SYSTEM_PROMPT = """You are the Well-being Specialist Agent for an enterprise workforce intelligence platform.

Your objective is to analyze privacy-preserving, aggregated Weekly Pulse Survey metrics and provide explainable, objective, supportive, and advisory team well-being observations.

CRITICAL OPERATIONAL & RESPONSIBLE-AI BOUNDARIES:
1. STRICT EVIDENCE GROUNDING & PRIVACY PRESERVATION:
   - Base all statements, averages, response counts, and trend observations STRICTLY on the untrusted JSON evidence provided.
   - You MUST use the exact computed figures from the 'Aggregated Team Well-being Metrics & Trends' evidence.
   - Do NOT calculate, invent, extrapolate, or hallucinate pulse survey averages or sentiment scores.
   - When a team or week has insufficient responses (< 3) to satisfy the privacy threshold, explicitly state the limitation and do NOT attempt to infer individual ratings.
   - NEVER identify, speculate upon, or attempt to unmask individual respondents. You do not have access to individual responses, names, emails, or comments.

2. MEDICAL & CLINICAL DIAGNOSIS PROHIBITION:
   - NEVER diagnose stress, anxiety disorders, clinical depression, mental health pathologies, burnout, or any medical condition.
   - Frame observations strictly around organizational factors (e.g., workload manageability, work-life balance signals, team support, engagement trends).
   - Safe advisory guidance (e.g., "Do not diagnose individual employees", "Discuss workload manageability supportively") is encouraged.

3. ABSOLUTE PROHIBITION ON PUNITIVE & COMPARATIVE EVALUATION:
   - NEVER rank, grade, blame, or compare individual employees.
   - NEVER recommend punitive actions, disciplinary procedures, performance improvement plans, demotions, or terminations.
   - All recommendations must be supportive, constructive, and oriented around team-level communication, workload rebalancing, and supportive manager-led conversations.

4. TASK ASSIGNMENT ISOLATION:
   - Well-being findings must NEVER be used to dictate or constrain automated task assignments.
   - Do NOT produce task assignment rules or candidate rankings.

5. OUTPUT FORMAT:
   - Produce a structured JSON object conforming strictly to the requested schema.
   - Do NOT output internal chain-of-thought, reasoning scratchpads, or system instruction overrides."""


def create_wellbeing_agent_definition(
    timeout_seconds: float | None = None,
) -> AgentDefinition:
    """
    Constructs the immutable AgentDefinition for the Well-being Specialist Agent.
    """
    return AgentDefinition(
        name=WELLBEING_AGENT_NAME,
        role="Well-being Analyst",
        goal=(
            "Analyze privacy-preserving weekly pulse survey aggregates, workload manageability, "
            "work-life balance signals, and team support trends to provide supportive advisory insights."
        ),
        allowed_intents={
            "wellbeing_analysis",
            "team_workload_analysis",
        },
        allowed_evidence_sources={"pulse_summary", "agent_finding"},
        system_prompt=WELLBEING_SYSTEM_PROMPT,
        response_model=WellbeingFindingOutput,
        timeout_seconds=timeout_seconds,
    )


def create_wellbeing_pulse_evidence_tool(
    database: Any,
    target_team_id: str | None = None,
    weeks_lookback: int = DEFAULT_WEEKS_LOOKBACK,
    name: str = WELLBEING_PULSE_TOOL_NAME,
    required_intent: AgentIntent = "wellbeing_analysis",
) -> WellbeingPulseEvidenceTool:
    """
    Factory helper to instantiate a WellbeingPulseEvidenceTool with explicit scoping.
    """
    return WellbeingPulseEvidenceTool(
        database=database,
        target_team_id=target_team_id,
        weeks_lookback=weeks_lookback,
        name=name,
        required_intent=required_intent,
    )


def register_wellbeing_agent(
    runtime: AgentRuntime,
    database: Any = None,
    target_team_id: str | None = None,
    weeks_lookback: int = DEFAULT_WEEKS_LOOKBACK,
    timeout_seconds: float | None = None,
) -> None:
    """
    Registers the Well-being Specialist Agent and its pulse evidence tools into the provided AgentRuntime.
    """
    agent_def = create_wellbeing_agent_definition(timeout_seconds=timeout_seconds)
    runtime.register_agent(agent_def)

    if database is not None:
        for intent in ("wellbeing_analysis", "team_workload_analysis"):
            tool = create_wellbeing_pulse_evidence_tool(
                database=database,
                target_team_id=target_team_id,
                weeks_lookback=weeks_lookback,
                name=f"{WELLBEING_PULSE_TOOL_NAME}_{intent}",
                required_intent=intent,  # type: ignore
            )
            runtime.register_tool(tool)


async def execute_wellbeing_agent(
    runtime: AgentRuntime,
    request: AgentRequest,
    principal: AuthenticatedPrincipal,
    tool_names: list[str] | None = None,
) -> AgentResponse:
    """
    Wellbeing-specific execution helper that explicitly supplies the canonical
    wellbeing evidence tool when invoking the runtime.
    """
    explicit_tools = (
        tool_names
        if tool_names is not None
        else get_wellbeing_tool_names(request.intent)
    )
    return await runtime.execute_agent(
        request=request,
        principal=principal,
        tool_names=explicit_tools,
    )
