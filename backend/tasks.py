from datetime import datetime, timezone
import math
import uuid
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from dependencies import get_current_user, require_roles
from schemas import (
    AddBlockerRequest,
    AddProgressUpdateRequest,
    BlockerResponse,
    CreateTaskRequest,
    ProgressUpdateResponse,
    ResolveBlockerRequest,
    TaskListResponse,
    TaskResponse,
    UpdateTaskAssignmentRequest,
    UpdateTaskRequest,
    UpdateTaskStatusRequest,
)

router = APIRouter(prefix="/tasks", tags=["Task Management"])
admin_tasks_router = APIRouter(
    prefix="/admin/tasks",
    tags=["Admin Task Audit"],
    dependencies=[Depends(require_roles("admin"))],
)


def _validate_object_id(id_str: str, field_name: str = "ID") -> ObjectId:
    if not isinstance(id_str, str) or not ObjectId.is_valid(id_str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name} format",
        )
    return ObjectId(id_str)


def _format_task_doc(
    doc: dict,
    user_map: dict | None = None,
    team_map: dict | None = None,
) -> TaskResponse:
    user_map = user_map or {}
    team_map = team_map or {}

    created_at = doc.get("created_at")
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    elif created_at is not None:
        created_at = str(created_at)

    updated_at = doc.get("updated_at")
    if isinstance(updated_at, datetime):
        updated_at = updated_at.isoformat()
    elif updated_at is not None:
        updated_at = str(updated_at)

    due_date = doc.get("due_date")
    if isinstance(due_date, datetime):
        due_date = due_date.isoformat()
    elif due_date is not None:
        due_date = str(due_date)

    progress_history = []
    for p in doc.get("progress_history", []):
        p_logged = p.get("logged_at")
        if isinstance(p_logged, datetime):
            p_logged = p_logged.isoformat()
        elif p_logged is not None:
            p_logged = str(p_logged)

        p_uid = str(p.get("user_id")) if p.get("user_id") is not None else ""
        p_user = user_map.get(p_uid)

        progress_history.append(
            ProgressUpdateResponse(
                id=str(p.get("id")),
                user_id=p_uid,
                percentage=int(p.get("percentage", 0)),
                notes=p.get("notes", ""),
                logged_at=p_logged or "",
                user_name=p_user.get("name") if p_user else None,
                user_email=p_user.get("email") if p_user else None,
            )
        )

    blockers = []
    for b in doc.get("blockers", []):
        b_created = b.get("created_at")
        if isinstance(b_created, datetime):
            b_created = b_created.isoformat()
        elif b_created is not None:
            b_created = str(b_created)

        b_resolved = b.get("resolved_at")
        if isinstance(b_resolved, datetime):
            b_resolved = b_resolved.isoformat()
        elif b_resolved is not None:
            b_resolved = str(b_resolved)

        b_resolver_id = str(b.get("resolved_by")) if b.get("resolved_by") else None
        b_resolution_note = b.get("resolution_note")
        b_uid = str(b.get("user_id")) if b.get("user_id") is not None else ""

        b_user = user_map.get(b_uid)
        b_resolver_user = user_map.get(b_resolver_id) if b_resolver_id else None

        blockers.append(
            BlockerResponse(
                id=str(b.get("id")),
                user_id=b_uid,
                description=b.get("description", ""),
                is_resolved=bool(b.get("is_resolved", False)),
                resolution_note=b_resolution_note,
                resolved_at=b_resolved,
                resolved_by=b_resolver_id,
                created_at=b_created or "",
                user_name=b_user.get("name") if b_user else None,
                user_email=b_user.get("email") if b_user else None,
                resolved_by_name=b_resolver_user.get("name") if b_resolver_user else None,
                resolved_by_email=b_resolver_user.get("email") if b_resolver_user else None,
            )
        )

    assigned_to_id = str(doc["assigned_to"]) if doc.get("assigned_to") else None
    assigned_user = user_map.get(assigned_to_id) if assigned_to_id else None

    created_by_id = str(doc["created_by"]) if doc.get("created_by") else ""
    created_user = user_map.get(created_by_id) if created_by_id else None

    team_id_str = str(doc["team_id"]) if doc.get("team_id") else ""
    team_obj = team_map.get(team_id_str)

    return TaskResponse(
        id=str(doc["_id"]),
        title=doc.get("title", ""),
        description=doc.get("description", ""),
        team_id=team_id_str,
        created_by=created_by_id,
        assigned_to=assigned_to_id,
        required_skills=doc.get("required_skills", []),
        priority=doc.get("priority", "medium"),
        status=doc.get("status", "todo"),
        due_date=due_date,
        estimated_hours=float(doc.get("estimated_hours", 0.0)),
        progress_history=progress_history,
        blockers=blockers,
        created_at=created_at,
        updated_at=updated_at,
        assigned_to_name=assigned_user.get("name") if assigned_user else None,
        assigned_to_email=assigned_user.get("email") if assigned_user else None,
        created_by_name=created_user.get("name") if created_user else None,
        created_by_email=created_user.get("email") if created_user else None,
        team_name=team_obj.get("name") if team_obj else None,
    )


async def _enrich_and_format_tasks(task_docs: list[dict], database) -> list[TaskResponse]:
    if not task_docs:
        return []

    user_ids = set()
    team_ids = set()

    for doc in task_docs:
        if doc.get("created_by"):
            user_ids.add(doc["created_by"])
        if doc.get("assigned_to"):
            user_ids.add(doc["assigned_to"])
        if doc.get("team_id"):
            team_ids.add(doc["team_id"])
        for b in doc.get("blockers", []):
            if b.get("user_id"):
                user_ids.add(b["user_id"])
            if b.get("resolved_by"):
                user_ids.add(b["resolved_by"])
        for p in doc.get("progress_history", []):
            if p.get("user_id"):
                user_ids.add(p["user_id"])

    user_oids = [
        uid if isinstance(uid, ObjectId) else ObjectId(str(uid))
        for uid in user_ids
        if uid and ObjectId.is_valid(str(uid))
    ]
    team_oids = [
        tid if isinstance(tid, ObjectId) else ObjectId(str(tid))
        for tid in team_ids
        if tid and ObjectId.is_valid(str(tid))
    ]

    user_map = {}
    if user_oids:
        u_cursor = database["users"].find({"_id": {"$in": user_oids}})
        if hasattr(u_cursor, "to_list"):
            u_docs = await u_cursor.to_list(length=len(user_oids) + 10)
        elif hasattr(u_cursor, "__aiter__"):
            u_docs = [u async for u in u_cursor]
        else:
            u_docs = [
                u for u in getattr(database["users"], "docs", [])
                if u.get("_id") in user_oids
            ]
        for u in u_docs:
            user_map[str(u["_id"])] = u

    team_map = {}
    if team_oids:
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
        for t in t_docs:
            team_map[str(t["_id"])] = t

    return [_format_task_doc(doc, user_map=user_map, team_map=team_map) for doc in task_docs]


async def _enrich_and_format_task(task_doc: dict, database) -> TaskResponse:
    results = await _enrich_and_format_tasks([task_doc], database)
    return results[0]


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("manager"))],
)
async def create_task(
    payload: CreateTaskRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Manager endpoint: Create task strictly for a team managed by the current manager."""
    team_oid = _validate_object_id(payload.team_id, "Team ID")
    database = request.app.state.database

    team = await database["teams"].find_one({"_id": team_oid})
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )

    if team.get("manager_id") != current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not manage this team",
        )

    assignee_oid = None
    if payload.assigned_to:
        assignee_oid = _validate_object_id(payload.assigned_to, "Assignee ID")
        assignee = await database["users"].find_one({"_id": assignee_oid})
        if not assignee:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Assigned employee not found",
            )
        if not assignee.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot assign an inactive employee",
            )
        if assignee.get("role") != "employee":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Assigned user must have the employee role",
            )
        if assignee.get("team_id") != team_oid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot assign an employee from another team",
            )

    due_date_val = None
    if payload.due_date:
        try:
            due_date_val = datetime.fromisoformat(payload.due_date.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid ISO 8601 datetime format for due_date",
            )

    now = datetime.now(timezone.utc)
    task_doc = {
        "title": payload.title,
        "description": payload.description,
        "team_id": team_oid,
        "created_by": current_user["_id"],
        "assigned_to": assignee_oid,
        "required_skills": payload.required_skills,
        "priority": payload.priority,
        "status": "todo",
        "due_date": due_date_val,
        "estimated_hours": float(payload.estimated_hours),
        "progress_history": [],
        "blockers": [],
        "created_at": now,
        "updated_at": now,
    }

    res = await database["tasks"].insert_one(task_doc)
    task_doc["_id"] = getattr(res, "inserted_id", task_doc.get("_id"))
    return await _enrich_and_format_task(task_doc, database)


@router.get(
    "/managed",
    response_model=TaskListResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles("manager"))],
)
async def get_managed_tasks(
    request: Request,
    team_id: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    priority_filter: str | None = Query(None, alias="priority"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """Manager endpoint: List tasks belonging strictly to teams managed by current manager."""
    database = request.app.state.database

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
        return TaskListResponse(items=[], total=0, page=page, limit=limit, total_pages=0)

    filter_query = {}
    if team_id:
        t_oid = _validate_object_id(team_id, "Team ID")
        if t_oid not in managed_team_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not manage this team",
            )
        filter_query["team_id"] = t_oid
    else:
        filter_query["team_id"] = {"$in": managed_team_ids}

    if status_filter:
        filter_query["status"] = status_filter
    if priority_filter:
        filter_query["priority"] = priority_filter

    total = await database["tasks"].count_documents(filter_query)
    total_pages = math.ceil(total / limit) if total > 0 else 0
    skip = (page - 1) * limit

    task_cursor = database["tasks"].find(filter_query).skip(skip).limit(limit)
    if hasattr(task_cursor, "to_list"):
        task_docs = await task_cursor.to_list(length=limit)
    elif hasattr(task_cursor, "__aiter__"):
        task_docs = [doc async for doc in task_cursor]
    else:
        task_docs = getattr(database["tasks"], "docs", [])[skip : skip + limit]

    items = await _enrich_and_format_tasks(task_docs, database)
    return TaskListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@router.get(
    "/my-tasks",
    response_model=TaskListResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles("employee"))],
)
async def get_my_tasks(
    request: Request,
    status_filter: str | None = Query(None, alias="status"),
    priority_filter: str | None = Query(None, alias="priority"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """Employee endpoint: List only tasks assigned to the current employee."""
    database = request.app.state.database
    filter_query = {"assigned_to": current_user["_id"]}

    if status_filter:
        filter_query["status"] = status_filter
    if priority_filter:
        filter_query["priority"] = priority_filter

    total = await database["tasks"].count_documents(filter_query)
    total_pages = math.ceil(total / limit) if total > 0 else 0
    skip = (page - 1) * limit

    task_cursor = database["tasks"].find(filter_query).skip(skip).limit(limit)
    if hasattr(task_cursor, "to_list"):
        task_docs = await task_cursor.to_list(length=limit)
    elif hasattr(task_cursor, "__aiter__"):
        task_docs = [doc async for doc in task_cursor]
    else:
        task_docs = getattr(database["tasks"], "docs", [])[skip : skip + limit]

    items = await _enrich_and_format_tasks(task_docs, database)
    return TaskListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles("employee", "manager"))],
)
async def get_task_by_id(
    task_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """View task details: Permitted only for assigned employee or manager of task's team."""
    task_oid = _validate_object_id(task_id, "Task ID")
    database = request.app.state.database

    task = await database["tasks"].find_one({"_id": task_oid})
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    user_role = current_user.get("role")
    if user_role == "employee":
        if task.get("assigned_to") != current_user["_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You are not assigned to this task",
            )
    elif user_role == "manager":
        team = await database["teams"].find_one({"_id": task["team_id"]})
        if not team or team.get("manager_id") != current_user["_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not manage this task's team",
            )

    return await _enrich_and_format_task(task, database)


@router.patch(
    "/{task_id}",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles("manager"))],
)
async def update_task_metadata(
    task_id: str,
    payload: UpdateTaskRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Manager endpoint: Update task metadata (title, description, priority, due date, etc.)."""
    task_oid = _validate_object_id(task_id, "Task ID")
    database = request.app.state.database

    task = await database["tasks"].find_one({"_id": task_oid})
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    team = await database["teams"].find_one({"_id": task["team_id"]})
    if not team or team.get("manager_id") != current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not manage this task's team",
        )

    update_fields = {}
    if payload.title is not None:
        update_fields["title"] = payload.title
    if payload.description is not None:
        update_fields["description"] = payload.description
    if payload.required_skills is not None:
        update_fields["required_skills"] = payload.required_skills
    if payload.priority is not None:
        update_fields["priority"] = payload.priority
    if payload.estimated_hours is not None:
        update_fields["estimated_hours"] = float(payload.estimated_hours)
    if payload.due_date is not None:
        if payload.due_date == "":
            update_fields["due_date"] = None
        else:
            try:
                update_fields["due_date"] = datetime.fromisoformat(
                    payload.due_date.replace("Z", "+00:00")
                )
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Invalid ISO 8601 datetime format for due_date",
                )

    update_fields["updated_at"] = datetime.now(timezone.utc)

    await database["tasks"].update_one(
        {"_id": task_oid},
        {"$set": update_fields},
    )

    task.update(update_fields)
    return await _enrich_and_format_task(task, database)


@router.patch(
    "/{task_id}/assignment",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles("manager"))],
)
async def update_task_assignment(
    task_id: str,
    payload: UpdateTaskAssignmentRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Manager endpoint: Assign or unassign task to an active employee belonging to task's team."""
    task_oid = _validate_object_id(task_id, "Task ID")
    database = request.app.state.database

    task = await database["tasks"].find_one({"_id": task_oid})
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    team = await database["teams"].find_one({"_id": task["team_id"]})
    if not team or team.get("manager_id") != current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not manage this task's team",
        )

    assignee_oid = None
    if payload.assigned_to:
        assignee_oid = _validate_object_id(payload.assigned_to, "Assignee ID")
        assignee = await database["users"].find_one({"_id": assignee_oid})
        if not assignee:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Assigned employee not found",
            )
        if not assignee.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot assign an inactive employee",
            )
        if assignee.get("role") != "employee":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Assigned user must have the employee role",
            )
        if assignee.get("team_id") != task["team_id"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot assign an employee from another team",
            )

    update_fields = {
        "assigned_to": assignee_oid,
        "updated_at": datetime.now(timezone.utc),
    }

    await database["tasks"].update_one(
        {"_id": task_oid},
        {"$set": update_fields},
    )

    task.update(update_fields)
    return await _enrich_and_format_task(task, database)


@router.patch(
    "/{task_id}/status",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles("employee"))],
)
async def update_task_status(
    task_id: str,
    payload: UpdateTaskStatusRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Employee endpoint: Update status of assigned task."""
    task_oid = _validate_object_id(task_id, "Task ID")
    database = request.app.state.database

    task = await database["tasks"].find_one({"_id": task_oid})
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    if task.get("assigned_to") != current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You are not assigned to this task",
        )

    unresolved_blockers = [
        b for b in task.get("blockers", []) if not b.get("is_resolved", False)
    ]
    if payload.status == "completed" and unresolved_blockers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot complete a task with unresolved blockers",
        )

    if unresolved_blockers and payload.status not in ["blocked"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change status away from 'blocked' while unresolved blockers exist",
        )

    update_fields = {
        "status": payload.status,
        "updated_at": datetime.now(timezone.utc),
    }

    # Completed-task consistency rule: completed status implies 100% progress
    if payload.status == "completed":
        progress_history = list(task.get("progress_history", []))
        latest_pct = (
            progress_history[-1].get("percentage", 0) if progress_history else 0
        )
        if latest_pct < 100:
            progress_history.append(
                {
                    "id": uuid.uuid4().hex,
                    "user_id": current_user["_id"],
                    "percentage": 100,
                    "notes": "Task completed",
                    "logged_at": update_fields["updated_at"],
                }
            )
            update_fields["progress_history"] = progress_history

    await database["tasks"].update_one(
        {"_id": task_oid},
        {"$set": update_fields},
    )

    task.update(update_fields)
    return await _enrich_and_format_task(task, database)


@router.post(
    "/{task_id}/progress",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles("employee"))],
)
async def add_task_progress(
    task_id: str,
    payload: AddProgressUpdateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Employee endpoint: Append progress update to assigned task."""
    task_oid = _validate_object_id(task_id, "Task ID")
    database = request.app.state.database

    task = await database["tasks"].find_one({"_id": task_oid})
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    if task.get("assigned_to") != current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You are not assigned to this task",
        )

    if task.get("status") == "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot add progress to a completed task",
        )

    now = datetime.now(timezone.utc)
    entry = {
        "id": uuid.uuid4().hex,
        "user_id": current_user["_id"],
        "percentage": int(payload.percentage),
        "notes": payload.notes,
        "logged_at": now,
    }

    progress_history = list(task.get("progress_history", []))
    progress_history.append(entry)

    update_fields = {
        "progress_history": progress_history,
        "updated_at": now,
    }

    await database["tasks"].update_one(
        {"_id": task_oid},
        {"$set": update_fields},
    )

    task.update(update_fields)
    return await _enrich_and_format_task(task, database)


@router.post(
    "/{task_id}/blockers",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles("employee"))],
)
async def add_task_blocker(
    task_id: str,
    payload: AddBlockerRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Employee endpoint: Report a blocker on assigned task, automatically marking task as blocked."""
    task_oid = _validate_object_id(task_id, "Task ID")
    database = request.app.state.database

    task = await database["tasks"].find_one({"_id": task_oid})
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    if task.get("assigned_to") != current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You are not assigned to this task",
        )

    if task.get("status") == "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Completed task cannot receive new blockers",
        )

    now = datetime.now(timezone.utc)
    blocker_entry = {
        "id": uuid.uuid4().hex,
        "user_id": current_user["_id"],
        "description": payload.description,
        "is_resolved": False,
        "resolution_note": None,
        "resolved_at": None,
        "resolved_by": None,
        "created_at": now,
    }

    blockers = list(task.get("blockers", []))
    blockers.append(blocker_entry)

    update_fields = {
        "blockers": blockers,
        "status": "blocked",
        "updated_at": now,
    }

    await database["tasks"].update_one(
        {"_id": task_oid},
        {"$set": update_fields},
    )

    task.update(update_fields)
    return await _enrich_and_format_task(task, database)


@router.patch(
    "/{task_id}/blockers/{blocker_id}/resolve",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles("manager"))],
)
async def resolve_task_blocker(
    task_id: str,
    blocker_id: str,
    payload: ResolveBlockerRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Manager endpoint: Resolve blocker; transitions task back to in_progress if no unresolved blockers remain."""
    task_oid = _validate_object_id(task_id, "Task ID")
    database = request.app.state.database

    task = await database["tasks"].find_one({"_id": task_oid})
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    team = await database["teams"].find_one({"_id": task["team_id"]})
    if not team or team.get("manager_id") != current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not manage this task's team",
        )

    blockers = list(task.get("blockers", []))
    found_blocker = None
    for b in blockers:
        if b.get("id") == blocker_id:
            found_blocker = b
            break

    if not found_blocker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Blocker not found",
        )

    if found_blocker.get("is_resolved", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Blocker is already resolved",
        )

    now = datetime.now(timezone.utc)
    found_blocker["is_resolved"] = True
    found_blocker["resolution_note"] = payload.resolution_note
    found_blocker["resolved_at"] = now
    found_blocker["resolved_by"] = current_user["_id"]

    remaining_unresolved = [b for b in blockers if not b.get("is_resolved", False)]
    new_status = "in_progress" if len(remaining_unresolved) == 0 else "blocked"

    update_fields = {
        "blockers": blockers,
        "status": new_status,
        "updated_at": now,
    }

    await database["tasks"].update_one(
        {"_id": task_oid},
        {"$set": update_fields},
    )

    task.update(update_fields)
    return await _enrich_and_format_task(task, database)


# =========================================================================
# Admin Read-Only Audit Endpoints
# =========================================================================


@admin_tasks_router.get(
    "",
    response_model=TaskListResponse,
    status_code=status.HTTP_200_OK,
)
async def admin_list_tasks(
    request: Request,
    team_id: str | None = None,
    assigned_to: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
):
    """Admin read-only audit endpoint: List all tasks in workspace with pagination and filters."""
    database = request.app.state.database
    filter_query = {}

    if team_id:
        filter_query["team_id"] = _validate_object_id(team_id, "Team ID")
    if assigned_to:
        filter_query["assigned_to"] = _validate_object_id(assigned_to, "Assigned User ID")
    if status_filter:
        filter_query["status"] = status_filter

    total = await database["tasks"].count_documents(filter_query)
    total_pages = math.ceil(total / limit) if total > 0 else 0
    skip = (page - 1) * limit

    task_cursor = database["tasks"].find(filter_query).skip(skip).limit(limit)
    if hasattr(task_cursor, "to_list"):
        task_docs = await task_cursor.to_list(length=limit)
    elif hasattr(task_cursor, "__aiter__"):
        task_docs = [doc async for doc in task_cursor]
    else:
        task_docs = getattr(database["tasks"], "docs", [])[skip : skip + limit]

    items = await _enrich_and_format_tasks(task_docs, database)
    return TaskListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@admin_tasks_router.get(
    "/{task_id}",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
)
async def admin_get_task(
    task_id: str,
    request: Request,
):
    """Admin read-only audit endpoint: View any task detail."""
    task_oid = _validate_object_id(task_id, "Task ID")
    database = request.app.state.database

    task = await database["tasks"].find_one({"_id": task_oid})
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    return await _enrich_and_format_task(task, database)
