from datetime import datetime, timedelta, timezone
import math
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pymongo.errors import DuplicateKeyError, PyMongoError

from backend.app.api.dependencies import get_current_user, require_roles
from backend.app.schemas import (
    AdminPulseSummaryResponse,
    CreatePulseSurveyResponseRequest,
    PulseAuditListResponse,
    PulseAuditRecordResponse,
    PulseMetricAverages,
    PulseSurveyResponse,
    PulseSurveyResponseList,
    PulseTeamSummaryResponse,
    UpdatePulseSurveyResponseRequest,
)

MINIMUM_AGGREGATE_RESPONSES = 3

router = APIRouter(prefix="/pulse-surveys", tags=["Weekly Pulse Surveys"])
admin_pulse_surveys_router = APIRouter(
    prefix="/admin/pulse-surveys",
    tags=["Admin Pulse Survey Audit"],
    dependencies=[Depends(require_roles("admin"))],
)


def _validate_object_id(id_str: str, field_name: str = "ID") -> ObjectId:
    """Validate and convert string to MongoDB ObjectId."""
    if not isinstance(id_str, str) or not ObjectId.is_valid(id_str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name} format",
        )
    return ObjectId(id_str)


def _format_datetime_utc(dt: datetime | str | None) -> str | None:
    """Format a datetime or string consistently as an ISO 8601 UTC string with timezone offset."""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.isoformat()
    dt_str = str(dt).strip()
    if not dt_str:
        return None
    if len(dt_str) == 10 and dt_str.count("-") == 2:
        return f"{dt_str}T00:00:00+00:00"
    if "T" in dt_str and not dt_str.endswith("Z") and "+" not in dt_str[10:] and "-" not in dt_str[10:]:
        return f"{dt_str}+00:00"
    return dt_str


def get_current_week_start(now: datetime | None = None) -> datetime:
    """Derive the Monday 00:00:00 UTC datetime for the server's current UTC week."""
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start - timedelta(days=start.weekday())


def parse_week_start(date_str: str | None) -> datetime:
    """Parse and validate an optional YYYY-MM-DD week_start query parameter representing a Monday."""
    if date_str is None:
        return get_current_week_start()
    if not isinstance(date_str, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid week_start date format. Expected YYYY-MM-DD",
        )
    try:
        dt = datetime.strptime(date_str.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid week_start date format. Expected YYYY-MM-DD",
        )
    if dt.weekday() != 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="week_start must be a Monday",
        )
    return dt


# =============================================================================
# Employee / Team Endpoints
# =============================================================================


@router.post(
    "/responses",
    response_model=PulseSurveyResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("employee"))],
)
async def submit_pulse_survey_response(
    body: CreatePulseSurveyResponseRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Employee endpoint: Submits a weekly pulse survey response.

    Server derives user identity, team association, week start, and timestamp.
    Enforces single submission per UTC week.
    """
    database = request.app.state.database

    team_id = current_user.get("team_id")
    if not team_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A valid team assignment is required",
        )

    try:
        team_oid = team_id if isinstance(team_id, ObjectId) else ObjectId(str(team_id))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A valid team assignment is required",
        )

    try:
        team = await database["teams"].find_one({"_id": team_oid})
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from None

    if not team:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A valid team assignment is required",
        )

    week_start = get_current_week_start()
    now = datetime.now(timezone.utc)
    user_oid = current_user["_id"]

    try:
        existing = await database["weekly_pulse_responses"].find_one(
            {"user_id": user_oid, "week_start": week_start}
        )
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from None

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A pulse survey response has already been submitted for this week",
        )

    response_doc = {
        "user_id": user_oid,
        "team_id": team_oid,
        "week_start": week_start,
        "workload_manageability": body.workload_manageability,
        "work_life_balance": body.work_life_balance,
        "team_support": body.team_support,
        "engagement": body.engagement,
        "optional_comment": body.optional_comment,
        "submitted_at": now,
        "updated_at": None,
        "is_edited": False,
        "revision": 1,
        "edit_history": [],
    }

    try:
        result = await database["weekly_pulse_responses"].insert_one(response_doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A pulse survey response has already been submitted for this week",
        ) from None
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from None

    return PulseSurveyResponse(
        id=str(result.inserted_id),
        user_id=str(user_oid),
        team_id=str(team_oid),
        team_name=team.get("name"),
        week_start=_format_datetime_utc(week_start),
        workload_manageability=body.workload_manageability,
        work_life_balance=body.work_life_balance,
        team_support=body.team_support,
        engagement=body.engagement,
        optional_comment=body.optional_comment,
        submitted_at=_format_datetime_utc(now),
        updated_at=None,
        is_edited=False,
        revision=1,
    )


@router.patch(
    "/responses/{response_id}",
    response_model=PulseSurveyResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles("employee"))],
)
async def update_pulse_survey_response(
    response_id: str,
    body: UpdatePulseSurveyResponseRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Employee endpoint: Updates an employee's own current-UTC-week pulse survey response.

    Validates ownership, current UTC week, non-empty update, and optimistic concurrency.
    Preserves original user_id, team_id, week_start, and submitted_at.
    Maintains internal revision history atomically.
    """
    response_oid = _validate_object_id(response_id, "Response ID")
    database = request.app.state.database
    user_oid = current_user["_id"]

    # Check for non-empty update
    update_fields = body.model_fields_set - {"expected_revision"}
    if not update_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one rating or optional_comment field must be provided for update",
        )

    try:
        doc = await database["weekly_pulse_responses"].find_one({"_id": response_oid})
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from None

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pulse survey response not found",
        )

    if doc.get("user_id") != user_oid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You can only edit your own pulse survey response",
        )

    # Validate week_start matches the current UTC week
    current_week_start = get_current_week_start()
    doc_ws = doc.get("week_start")
    if isinstance(doc_ws, datetime):
        if doc_ws.tzinfo is None:
            doc_ws = doc_ws.replace(tzinfo=timezone.utc)
        else:
            doc_ws = doc_ws.astimezone(timezone.utc)
    else:
        doc_ws = parse_week_start(str(doc_ws))

    if doc_ws != current_week_start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only current-week pulse survey responses can be edited. Previous-week responses are read-only.",
        )

    current_revision = int(doc.get("revision", 1))

    # Fast-path concurrency check against loaded document revision
    if body.expected_revision != current_revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflict: The pulse survey response has been modified concurrently. Please refresh and try again.",
        )

    now = datetime.now(timezone.utc)
    history_entry = {
        "revision": current_revision,
        "workload_manageability": doc["workload_manageability"],
        "work_life_balance": doc["work_life_balance"],
        "team_support": doc["team_support"],
        "engagement": doc["engagement"],
        "optional_comment": doc.get("optional_comment"),
        "edited_at": now,
        "edited_by": user_oid,
    }

    set_doc = {
        "updated_at": now,
        "is_edited": True,
        "revision": body.expected_revision + 1,
    }

    if "workload_manageability" in body.model_fields_set:
        set_doc["workload_manageability"] = body.workload_manageability
    if "work_life_balance" in body.model_fields_set:
        set_doc["work_life_balance"] = body.work_life_balance
    if "team_support" in body.model_fields_set:
        set_doc["team_support"] = body.team_support
    if "engagement" in body.model_fields_set:
        set_doc["engagement"] = body.engagement
    if "optional_comment" in body.model_fields_set:
        set_doc["optional_comment"] = body.optional_comment

    # Query filter for atomic update with optimistic locking:
    # Matches record ID, authenticated owner, week_start, and expected revision.
    # Legacy records missing the revision field match ONLY when expected_revision == 1.
    if body.expected_revision == 1:
        query_filter = {
            "_id": response_oid,
            "user_id": user_oid,
            "week_start": doc.get("week_start"),
            "$or": [{"revision": 1}, {"revision": {"$exists": False}}],
        }
    else:
        query_filter = {
            "_id": response_oid,
            "user_id": user_oid,
            "week_start": doc.get("week_start"),
            "revision": body.expected_revision,
        }

    try:
        updated_doc = await database["weekly_pulse_responses"].find_one_and_update(
            query_filter,
            {
                "$set": set_doc,
                "$push": {"edit_history": history_entry},
            },
            return_document=True,
        )
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from None

    if not updated_doc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflict: The pulse survey response has been modified concurrently. Please refresh and try again.",
        )

    # Enrich team name from original team_id
    team_name = None
    team_oid = updated_doc.get("team_id")
    if team_oid:
        try:
            team = await database["teams"].find_one({"_id": team_oid})
            if team:
                team_name = team.get("name")
        except PyMongoError:
            pass

    return PulseSurveyResponse(
        id=str(updated_doc["_id"]),
        user_id=str(updated_doc["user_id"]),
        team_id=str(updated_doc["team_id"]) if updated_doc.get("team_id") else "",
        team_name=team_name,
        week_start=_format_datetime_utc(updated_doc.get("week_start")),
        workload_manageability=updated_doc["workload_manageability"],
        work_life_balance=updated_doc["work_life_balance"],
        team_support=updated_doc["team_support"],
        engagement=updated_doc["engagement"],
        optional_comment=updated_doc.get("optional_comment"),
        submitted_at=_format_datetime_utc(updated_doc.get("submitted_at")),
        updated_at=_format_datetime_utc(now),
        is_edited=True,
        revision=int(updated_doc.get("revision", current_revision + 1)),
    )


@router.get(
    "/my-responses",
    response_model=PulseSurveyResponseList,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles("employee"))],
)
async def get_my_pulse_survey_responses(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """Employee endpoint: Retrieves the authenticated employee's response history.

    Sorted deterministically by week_start descending, then _id descending.
    """
    database = request.app.state.database
    user_oid = current_user["_id"]
    filter_query = {"user_id": user_oid}

    try:
        total = await database["weekly_pulse_responses"].count_documents(filter_query)
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from None

    skip = (page - 1) * limit
    total_pages = math.ceil(total / limit) if total > 0 else 1

    try:
        cursor = (
            database["weekly_pulse_responses"]
            .find(filter_query)
            .sort([("week_start", -1), ("_id", -1)])
            .skip(skip)
            .limit(limit)
        )
        if hasattr(cursor, "to_list"):
            docs = await cursor.to_list(length=limit)
        elif hasattr(cursor, "__aiter__"):
            docs = [d async for d in cursor]
        else:
            docs = [
                d for d in getattr(database["weekly_pulse_responses"], "docs", [])
                if d.get("user_id") == user_oid
            ]
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from None

    # Batch enrich team names
    team_ids = {d["team_id"] for d in docs if d.get("team_id")}
    team_map = {}
    if team_ids:
        try:
            t_cursor = database["teams"].find({"_id": {"$in": list(team_ids)}})
            if hasattr(t_cursor, "to_list"):
                t_docs = await t_cursor.to_list(length=len(team_ids) + 10)
            elif hasattr(t_cursor, "__aiter__"):
                t_docs = [t async for t in t_cursor]
            else:
                t_docs = [
                    t for t in getattr(database["teams"], "docs", [])
                    if t.get("_id") in team_ids
                ]
            for t in t_docs:
                team_map[str(t["_id"])] = t.get("name")
        except PyMongoError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database unavailable",
            ) from None

    items = []
    for d in docs:
        tid_str = str(d["team_id"]) if d.get("team_id") else ""
        items.append(
            PulseSurveyResponse(
                id=str(d["_id"]),
                user_id=str(d["user_id"]),
                team_id=tid_str,
                team_name=team_map.get(tid_str),
                week_start=_format_datetime_utc(d.get("week_start")),
                workload_manageability=d["workload_manageability"],
                work_life_balance=d["work_life_balance"],
                team_support=d["team_support"],
                engagement=d["engagement"],
                optional_comment=d.get("optional_comment"),
                submitted_at=_format_datetime_utc(d.get("submitted_at")),
                updated_at=_format_datetime_utc(d.get("updated_at")),
                is_edited=bool(d.get("is_edited", False)),
                revision=int(d.get("revision", 1)),
            )
        )

    return PulseSurveyResponseList(
        items=items,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@router.get(
    "/team-summary",
    response_model=PulseTeamSummaryResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles("manager"))],
)
async def get_team_pulse_summary(
    team_id: str = Query(..., description="Team ID to retrieve aggregate summary for"),
    week_start: str | None = Query(None, description="Optional Monday week date (YYYY-MM-DD)"),
    request: Request = None,
    current_user: dict = Depends(get_current_user),
):
    """Manager endpoint: Returns privacy-thresholded team aggregate metrics.

    Enforces manager scope and minimum response threshold (3).
    Never exposes respondent identities or individual comments.
    """
    team_oid = _validate_object_id(team_id, "Team ID")
    week_start_dt = parse_week_start(week_start)

    database = request.app.state.database
    try:
        team = await database["teams"].find_one({"_id": team_oid})
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from None

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )

    if team.get("manager_id") != current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You are not authorized to view summary for this team",
        )

    filter_query = {"team_id": team_oid, "week_start": week_start_dt}
    try:
        cursor = database["weekly_pulse_responses"].find(filter_query)
        if hasattr(cursor, "to_list"):
            docs = await cursor.to_list(length=1000)
        elif hasattr(cursor, "__aiter__"):
            docs = [d async for d in cursor]
        else:
            docs = [
                d for d in getattr(database["weekly_pulse_responses"], "docs", [])
                if d.get("team_id") == team_oid and d.get("week_start") == week_start_dt
            ]
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from None

    response_count = len(docs)
    team_name = team.get("name")

    if response_count < MINIMUM_AGGREGATE_RESPONSES:
        return PulseTeamSummaryResponse(
            available=False,
            team_id=str(team_oid),
            team_name=team_name,
            week_start=week_start_dt.isoformat(),
            response_count=response_count,
            minimum_required=MINIMUM_AGGREGATE_RESPONSES,
            averages=None,
            message="Insufficient responses to display aggregated metrics (minimum 3 required for privacy).",
        )

    avg_wm = round(sum(d["workload_manageability"] for d in docs) / response_count, 2)
    avg_wlb = round(sum(d["work_life_balance"] for d in docs) / response_count, 2)
    avg_ts = round(sum(d["team_support"] for d in docs) / response_count, 2)
    avg_eng = round(sum(d["engagement"] for d in docs) / response_count, 2)

    return PulseTeamSummaryResponse(
        available=True,
        team_id=str(team_oid),
        team_name=team_name,
        week_start=week_start_dt.isoformat(),
        response_count=response_count,
        minimum_required=MINIMUM_AGGREGATE_RESPONSES,
        averages=PulseMetricAverages(
            workload_manageability=avg_wm,
            work_life_balance=avg_wlb,
            team_support=avg_ts,
            engagement=avg_eng,
        ),
        message=None,
    )


# =============================================================================
# Admin Audit Endpoints
# =============================================================================


@admin_pulse_surveys_router.get(
    "",
    response_model=PulseAuditListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_admin_pulse_audit_records(
    request: Request,
    team_id: str | None = Query(None, description="Optional team ID filter"),
    week_start: str | None = Query(None, description="Optional Monday week date (YYYY-MM-DD)"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """Admin read-only audit endpoint: Returns privacy-safe submission metadata.

    Excludes user IDs, respondent names, individual scores, and comments.
    """
    filter_query = {}
    if team_id is not None:
        team_oid = _validate_object_id(team_id, "Team ID")
        filter_query["team_id"] = team_oid

    if week_start is not None:
        week_start_dt = parse_week_start(week_start)
        filter_query["week_start"] = week_start_dt

    database = request.app.state.database
    try:
        total = await database["weekly_pulse_responses"].count_documents(filter_query)
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from None

    skip = (page - 1) * limit
    total_pages = math.ceil(total / limit) if total > 0 else 1

    try:
        cursor = (
            database["weekly_pulse_responses"]
            .find(filter_query)
            .sort([("week_start", -1), ("_id", -1)])
            .skip(skip)
            .limit(limit)
        )
        if hasattr(cursor, "to_list"):
            docs = await cursor.to_list(length=limit)
        elif hasattr(cursor, "__aiter__"):
            docs = [d async for d in cursor]
        else:
            docs = [
                d for d in getattr(database["weekly_pulse_responses"], "docs", [])
                if (
                    (filter_query.get("team_id") is None or d.get("team_id") == filter_query.get("team_id"))
                    and (filter_query.get("week_start") is None or d.get("week_start") == filter_query.get("week_start"))
                )
            ]
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from None

    team_ids = {d["team_id"] for d in docs if d.get("team_id")}
    team_map = {}
    if team_ids:
        try:
            t_cursor = database["teams"].find({"_id": {"$in": list(team_ids)}})
            if hasattr(t_cursor, "to_list"):
                t_docs = await t_cursor.to_list(length=len(team_ids) + 10)
            elif hasattr(t_cursor, "__aiter__"):
                t_docs = [t async for t in t_cursor]
            else:
                t_docs = [
                    t for t in getattr(database["teams"], "docs", [])
                    if t.get("_id") in team_ids
                ]
            for t in t_docs:
                team_map[str(t["_id"])] = t.get("name")
        except PyMongoError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database unavailable",
            ) from None

    items = []
    for d in docs:
        tid_str = str(d["team_id"]) if d.get("team_id") else ""
        items.append(
            PulseAuditRecordResponse(
                id=str(d["_id"]),
                team_id=tid_str,
                team_name=team_map.get(tid_str),
                week_start=_format_datetime_utc(d.get("week_start")),
                submitted_at=_format_datetime_utc(d.get("submitted_at")),
            )
        )

    return PulseAuditListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@admin_pulse_surveys_router.get(
    "/summary",
    response_model=AdminPulseSummaryResponse,
    status_code=status.HTTP_200_OK,
)
async def get_admin_pulse_summary(
    request: Request,
    week_start: str | None = Query(None, description="Optional Monday week date (YYYY-MM-DD)"),
    current_user: dict = Depends(get_current_user),
):
    """Admin read-only summary endpoint: Returns privacy-safe per-team summaries across the organization.

    Applies the 3-response minimum threshold independently to each team.
    """
    week_start_dt = parse_week_start(week_start)
    database = request.app.state.database

    try:
        t_cursor = database["teams"].find({})
        if hasattr(t_cursor, "to_list"):
            teams = await t_cursor.to_list(length=1000)
        elif hasattr(t_cursor, "__aiter__"):
            teams = [t async for t in t_cursor]
        else:
            teams = list(getattr(database["teams"], "docs", []))
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from None

    # Sort teams consistently by team name, then team ID
    teams.sort(key=lambda t: (t.get("name", "").lower(), str(t.get("_id", ""))))

    team_summaries = []
    for team in teams:
        team_oid = team["_id"]
        filter_query = {"team_id": team_oid, "week_start": week_start_dt}
        try:
            cursor = database["weekly_pulse_responses"].find(filter_query)
            if hasattr(cursor, "to_list"):
                docs = await cursor.to_list(length=1000)
            elif hasattr(cursor, "__aiter__"):
                docs = [d async for d in cursor]
            else:
                docs = [
                    d for d in getattr(database["weekly_pulse_responses"], "docs", [])
                    if d.get("team_id") == team_oid and d.get("week_start") == week_start_dt
                ]
        except PyMongoError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database unavailable",
            ) from None

        response_count = len(docs)
        team_name = team.get("name")

        if response_count < MINIMUM_AGGREGATE_RESPONSES:
            team_summaries.append(
                PulseTeamSummaryResponse(
                    available=False,
                    team_id=str(team_oid),
                    team_name=team_name,
                    week_start=week_start_dt.isoformat(),
                    response_count=response_count,
                    minimum_required=MINIMUM_AGGREGATE_RESPONSES,
                    averages=None,
                    message="Insufficient responses to display aggregated metrics (minimum 3 required for privacy).",
                )
            )
        else:
            avg_wm = round(sum(d["workload_manageability"] for d in docs) / response_count, 2)
            avg_wlb = round(sum(d["work_life_balance"] for d in docs) / response_count, 2)
            avg_ts = round(sum(d["team_support"] for d in docs) / response_count, 2)
            avg_eng = round(sum(d["engagement"] for d in docs) / response_count, 2)

            team_summaries.append(
                PulseTeamSummaryResponse(
                    available=True,
                    team_id=str(team_oid),
                    team_name=team_name,
                    week_start=week_start_dt.isoformat(),
                    response_count=response_count,
                    minimum_required=MINIMUM_AGGREGATE_RESPONSES,
                    averages=PulseMetricAverages(
                        workload_manageability=avg_wm,
                        work_life_balance=avg_wlb,
                        team_support=avg_ts,
                        engagement=avg_eng,
                    ),
                    message=None,
                )
            )

    return AdminPulseSummaryResponse(
        week_start=week_start_dt.isoformat(),
        items=team_summaries,
    )
