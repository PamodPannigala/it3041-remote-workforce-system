from typing import Literal
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pymongo.errors import PyMongoError

from backend.app.api.dependencies import get_current_user
from backend.app.modules.information_retrieval.service import (
    BM25Ranker,
    SearchableDocument,
    build_collaboration_document,
    build_task_document,
)
from backend.app.modules.information_retrieval.tokenizer import is_valid_query
from backend.app.schemas import SearchResponse

router = APIRouter(tags=["Information Retrieval"])


def _validate_object_id(id_str: str, field_name: str = "ID") -> ObjectId:
    if not isinstance(id_str, str) or not ObjectId.is_valid(id_str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name} format",
        )
    return ObjectId(id_str)


async def _fetch_team_name_map(database, team_oids: list[ObjectId]) -> dict[str, str]:
    """Safely build a mapping of team_id string to team name."""
    if not team_oids:
        return {}
    try:
        t_cursor = database["teams"].find({"_id": {"$in": team_oids}})
        if hasattr(t_cursor, "to_list"):
            t_docs = await t_cursor.to_list(length=len(team_oids) + 10)
        elif hasattr(t_cursor, "__aiter__"):
            t_docs = [t async for t in t_cursor]
        else:
            t_docs = [
                t for t in getattr(database["teams"], "docs", [])
                if t.get("_id") in team_oids
            ]
        return {str(t["_id"]): str(t.get("name", "")) for t in t_docs}
    except Exception:
        return {}


async def _execute_search(
    request: Request,
    q: str,
    source: Literal["all", "tasks", "collaboration"],
    team_id: str | None,
    limit: int,
    include_deleted: bool,
    current_user: dict,
) -> SearchResponse:
    # 1. Query text validation
    valid_q, err_msg = is_valid_query(q)
    if not valid_q:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=err_msg,
        )

    database = request.app.state.database
    user_role = current_user.get("role")
    user_team_id = current_user.get("team_id")

    task_filter: dict | None = None
    message_filter: dict | None = None
    admin_allow_deleted = False

    # 2. Role-Aware Pre-Ranking Scope Construction
    try:
        if user_role == "employee":
            # Employee may only retrieve assigned tasks and active messages from assigned team
            if team_id is not None:
                req_team_oid = _validate_object_id(team_id, "Team ID")
                if not user_team_id or req_team_oid != user_team_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access denied: You can only search within your assigned team scope",
                    )

            task_filter = {"assigned_to": current_user["_id"]}
            if user_team_id:
                message_filter = {"team_id": user_team_id, "is_deleted": False}
            else:
                message_filter = None  # No team assigned

        elif user_role == "manager":
            # Manager may only retrieve tasks and messages from managed teams
            team_cursor = database["teams"].find({"manager_id": current_user["_id"]})
            if hasattr(team_cursor, "to_list"):
                managed_teams = await team_cursor.to_list(length=100)
            elif hasattr(team_cursor, "__aiter__"):
                managed_teams = [t async for t in team_cursor]
            else:
                managed_teams = [
                    t for t in getattr(database["teams"], "docs", [])
                    if t.get("manager_id") == current_user["_id"]
                ]

            managed_team_ids = [t["_id"] for t in managed_teams]
            if not managed_team_ids:
                return SearchResponse(
                    query=q,
                    source=source,
                    total_candidates=0,
                    total_matches=0,
                    results=[],
                )

            if team_id is not None:
                req_team_oid = _validate_object_id(team_id, "Team ID")
                if req_team_oid not in managed_team_ids:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access denied: You do not manage this team",
                    )
                target_team_ids = [req_team_oid]
            else:
                target_team_ids = managed_team_ids

            task_filter = {"team_id": {"$in": target_team_ids}}
            message_filter = {"team_id": {"$in": target_team_ids}, "is_deleted": False}

        elif user_role == "admin":
            # Admin read-only audit retrieval across organization
            task_filter = {}
            message_filter = {}
            if team_id is not None:
                req_team_oid = _validate_object_id(team_id, "Team ID")
                task_filter["team_id"] = req_team_oid
                message_filter["team_id"] = req_team_oid

            if include_deleted:
                admin_allow_deleted = True
            else:
                message_filter["is_deleted"] = False

        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted",
            )

        # 3. Candidate Document Collection (Pre-filtered at database query level)
        candidate_docs: list[SearchableDocument] = []
        team_oids_to_resolve: set[ObjectId] = set()

        # Fetch tasks if requested
        if source in ("all", "tasks") and task_filter is not None:
            t_cursor = database["tasks"].find(task_filter)
            if hasattr(t_cursor, "to_list"):
                raw_tasks = await t_cursor.to_list(length=1000)
            elif hasattr(t_cursor, "__aiter__"):
                raw_tasks = [t async for t in t_cursor]
            else:
                all_tasks = getattr(database["tasks"], "docs", [])
                raw_tasks = [
                    t for t in all_tasks
                    if (
                        ("assigned_to" not in task_filter or t.get("assigned_to") == task_filter["assigned_to"])
                        and ("team_id" not in task_filter or (
                            t.get("team_id") in task_filter["team_id"]["$in"]
                            if isinstance(task_filter.get("team_id"), dict) and "$in" in task_filter["team_id"]
                            else t.get("team_id") == task_filter.get("team_id")
                        ))
                    )
                ]
            for t in raw_tasks:
                if t.get("team_id"):
                    team_oids_to_resolve.add(t["team_id"])
        else:
            raw_tasks = []

        # Fetch collaboration messages if requested
        if source in ("all", "collaboration") and message_filter is not None:
            m_cursor = database["collaboration_messages"].find(message_filter)
            if hasattr(m_cursor, "to_list"):
                raw_messages = await m_cursor.to_list(length=1000)
            elif hasattr(m_cursor, "__aiter__"):
                raw_messages = [m async for m in m_cursor]
            else:
                all_msgs = getattr(database["collaboration_messages"], "docs", [])
                raw_messages = [
                    m for m in all_msgs
                    if (
                        ("team_id" not in message_filter or (
                            m.get("team_id") in message_filter["team_id"]["$in"]
                            if isinstance(message_filter.get("team_id"), dict) and "$in" in message_filter["team_id"]
                            else m.get("team_id") == message_filter.get("team_id")
                        ))
                        and ("is_deleted" not in message_filter or m.get("is_deleted", False) == message_filter["is_deleted"])
                    )
                ]
            for m in raw_messages:
                if m.get("team_id"):
                    team_oids_to_resolve.add(m["team_id"])
        else:
            raw_messages = []

        # Resolve human-readable team names safely
        team_name_map = await _fetch_team_name_map(database, list(team_oids_to_resolve))

        # Convert raw records into SearchableDocuments
        for t in raw_tasks:
            candidate_docs.append(build_task_document(t, team_name_map=team_name_map))

        for m in raw_messages:
            msg_doc = build_collaboration_document(
                m,
                team_name_map=team_name_map,
                include_deleted_content=admin_allow_deleted,
            )
            if msg_doc is not None:
                candidate_docs.append(msg_doc)

        total_candidates = len(candidate_docs)

        # 4. Lexical BM25 Ranking over Authorized Candidates
        ranker = BM25Ranker(candidate_docs)
        total_matches, results = ranker.rank(q, limit=limit)

        return SearchResponse(
            query=q,
            source=source,
            total_candidates=total_candidates,
            total_matches=total_matches,
            results=results,
        )

    except HTTPException:
        raise
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from None


@router.get(
    "/api/search",
    response_model=SearchResponse,
    status_code=status.HTTP_200_OK,
)
async def search_workforce(
    request: Request,
    q: str = Query(..., description="Search query string"),
    source: Literal["all", "tasks", "collaboration"] = Query("all", description="Filter source collection"),
    team_id: str | None = Query(None, description="Optional team scope filter"),
    limit: int = Query(10, ge=1, le=20, description="Maximum number of search results"),
    include_deleted: bool = Query(False, description="Admin audit: include retained deleted content"),
    current_user: dict = Depends(get_current_user),
):
    """Lexical Information Retrieval over authorized Tasks and Collaboration Messages."""
    return await _execute_search(
        request=request,
        q=q,
        source=source,
        team_id=team_id,
        limit=limit,
        include_deleted=include_deleted,
        current_user=current_user,
    )
