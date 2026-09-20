from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pymongo.errors import DuplicateKeyError, PyMongoError

from backend.app.api.dependencies import get_current_user, require_roles
from backend.app.schemas import (
    AssignTeamMemberRequest,
    CreateTeamRequest,
    TeamDetailResponse,
    TeamMemberResponse,
    UpdateTeamManagerRequest,
    UpdateUserRoleRequest,
    UpdateUserStatusRequest,
    UserAdminResponse,
    UserListResponse,
)

router = APIRouter(
    prefix="/admin",
    tags=["Admin Management"],
    dependencies=[Depends(require_roles("admin"))],
)


def _validate_object_id(id_str: str, field_name: str = "ID") -> ObjectId:
    if not isinstance(id_str, str) or not ObjectId.is_valid(id_str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name} format",
        )
    return ObjectId(id_str)


async def _get_team_name(database, team_id) -> str | None:
    if not team_id:
        return None
    team = await database["teams"].find_one({"_id": team_id})
    return team["name"] if team else None


@router.get("/users", response_model=UserListResponse, status_code=status.HTTP_200_OK)
async def list_users(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
):
    database = request.app.state.database
    skip = (page - 1) * limit

    total = await database["users"].count_documents({})

    cursor = database["users"].find({})
    if hasattr(cursor, "skip") and hasattr(cursor, "limit"):
        cursor = cursor.skip(skip).limit(limit)
        if hasattr(cursor, "to_list"):
            user_docs = await cursor.to_list(length=limit)
        else:
            user_docs = [doc async for doc in cursor]
    else:
        # Fallback for fake / non-cursor objects
        user_docs = getattr(database["users"], "docs", [])[skip : skip + limit]

    # Pre-fetch team names if any
    team_ids = [doc["team_id"] for doc in user_docs if doc.get("team_id")]
    teams_map = {}
    if team_ids:
        team_cursor = database["teams"].find({"_id": {"$in": team_ids}})
        if hasattr(team_cursor, "to_list"):
            teams_list = await team_cursor.to_list(length=len(team_ids))
        elif hasattr(team_cursor, "__aiter__"):
            teams_list = [t async for t in team_cursor]
        else:
            teams_list = [
                t for t in getattr(database["teams"], "docs", [])
                if t.get("_id") in team_ids
            ]
        teams_map = {str(t["_id"]): t.get("name") for t in teams_list}

    items = []
    for doc in user_docs:
        t_id = str(doc["team_id"]) if doc.get("team_id") else None
        t_name = teams_map.get(t_id) if t_id else None
        created_at_str = (
            doc["created_at"].isoformat()
            if isinstance(doc.get("created_at"), datetime)
            else str(doc.get("created_at"))
            if doc.get("created_at")
            else None
        )
        items.append(
            UserAdminResponse(
                id=str(doc["_id"]),
                name=doc["name"],
                email=doc["email"],
                role=doc["role"],
                is_active=doc.get("is_active", True),
                team_id=t_id,
                team_name=t_name,
                created_at=created_at_str,
            )
        )

    total_pages = (total + limit - 1) // limit if total > 0 else 1

    return UserListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@router.patch("/users/{user_id}/role", response_model=UserAdminResponse, status_code=status.HTTP_200_OK)
async def update_user_role(
    user_id: str,
    payload: UpdateUserRoleRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    target_oid = _validate_object_id(user_id, "User ID")
    database = request.app.state.database

    target_user = await database["users"].find_one({"_id": target_oid})
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Prevent self-demotion
    if target_user["_id"] == current_user["_id"] and payload.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot change their own role.",
        )

    # Prevent demoting last active admin
    if (
        target_user.get("role") == "admin"
        and payload.role != "admin"
        and target_user.get("is_active", True)
    ):
        active_admins = await database["users"].count_documents(
            {"role": "admin", "is_active": True}
        )
        if active_admins <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the last active administrator.",
            )

    # Prevent inconsistent role change for actively assigned manager
    if target_user.get("role") == "manager" and payload.role != "manager":
        managed_team = await database["teams"].find_one({"manager_id": target_user["_id"]})
        if managed_team:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User is assigned as manager of team '{managed_team.get('name', 'Unknown')}'. Reassign the team before changing this user's role.",
            )

    # Prevent changing role of employee with open assigned tasks
    if target_user.get("role") == "employee" and payload.role != "employee":
        open_tasks = await database["tasks"].count_documents(
            {"assigned_to": target_oid, "status": {"$in": ["todo", "in_progress", "blocked"]}}
        )
        if open_tasks > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot change role of an employee with open assigned tasks. Unassign or reassign tasks first.",
            )

    update_fields = {"role": payload.role}
    # If role changed to non-employee, clear team_id
    if payload.role != "employee" and target_user.get("team_id"):
        update_fields["team_id"] = None

    await database["users"].update_one(
        {"_id": target_oid},
        {"$set": update_fields},
    )

    updated_user = await database["users"].find_one({"_id": target_oid})
    team_name = await _get_team_name(database, updated_user.get("team_id"))

    return UserAdminResponse(
        id=str(updated_user["_id"]),
        name=updated_user["name"],
        email=updated_user["email"],
        role=updated_user["role"],
        is_active=updated_user.get("is_active", True),
        team_id=str(updated_user["team_id"]) if updated_user.get("team_id") else None,
        team_name=team_name,
        created_at=updated_user["created_at"].isoformat() if isinstance(updated_user.get("created_at"), datetime) else None,
    )


@router.patch("/users/{user_id}/status", response_model=UserAdminResponse, status_code=status.HTTP_200_OK)
async def update_user_status(
    user_id: str,
    payload: UpdateUserStatusRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    target_oid = _validate_object_id(user_id, "User ID")
    database = request.app.state.database

    target_user = await database["users"].find_one({"_id": target_oid})
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Prevent self-deactivation
    if target_user["_id"] == current_user["_id"] and not payload.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot deactivate their own account.",
        )

    # Prevent deactivating last active admin
    if (
        target_user.get("role") == "admin"
        and not payload.is_active
        and target_user.get("is_active", True)
    ):
        active_admins = await database["users"].count_documents(
            {"role": "admin", "is_active": True}
        )
        if active_admins <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate the last active administrator.",
            )

    # Prevent deactivating actively assigned team manager
    if not payload.is_active and target_user.get("role") == "manager":
        managed_team = await database["teams"].find_one({"manager_id": target_user["_id"]})
        if managed_team:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User is assigned as manager of team '{managed_team.get('name', 'Unknown')}'. Reassign the team before deactivating this user.",
            )

    # Prevent deactivating employee with open assigned tasks
    if not payload.is_active and target_user.get("role") == "employee":
        open_tasks = await database["tasks"].count_documents(
            {"assigned_to": target_oid, "status": {"$in": ["todo", "in_progress", "blocked"]}}
        )
        if open_tasks > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot deactivate an employee with open assigned tasks. Unassign or reassign tasks first.",
            )


    await database["users"].update_one(
        {"_id": target_oid},
        {"$set": {"is_active": payload.is_active}},
    )

    updated_user = await database["users"].find_one({"_id": target_oid})
    team_name = await _get_team_name(database, updated_user.get("team_id"))

    return UserAdminResponse(
        id=str(updated_user["_id"]),
        name=updated_user["name"],
        email=updated_user["email"],
        role=updated_user["role"],
        is_active=updated_user.get("is_active", True),
        team_id=str(updated_user["team_id"]) if updated_user.get("team_id") else None,
        team_name=team_name,
        created_at=updated_user["created_at"].isoformat() if isinstance(updated_user.get("created_at"), datetime) else None,
    )


@router.post("/teams", response_model=TeamDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_team(payload: CreateTeamRequest, request: Request):
    database = request.app.state.database
    manager_oid = _validate_object_id(payload.manager_id, "Manager ID")

    # Validate manager exists, is active, and has manager role
    manager = await database["users"].find_one({"_id": manager_oid})
    if (
        not manager
        or manager.get("role") != "manager"
        or not manager.get("is_active", True)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assigned manager must be an active user with role 'manager'.",
        )

    # Check for duplicate team name
    clean_name = payload.name.strip()
    existing_team = await database["teams"].find_one({"name": clean_name})
    if existing_team:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A team with this name already exists.",
        )

    team_doc = {
        "name": clean_name,
        "manager_id": manager["_id"],
        "created_at": datetime.now(timezone.utc),
    }

    try:
        result = await database["teams"].insert_one(team_doc)
        team_doc["_id"] = result.inserted_id
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A team with this name already exists.",
        ) from None
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Team creation is temporarily unavailable.",
        ) from None

    return TeamDetailResponse(
        id=str(team_doc["_id"]),
        name=team_doc["name"],
        manager_id=str(manager["_id"]),
        manager_name=manager.get("name"),
        manager_email=manager.get("email"),
        members=[],
        created_at=team_doc["created_at"].isoformat(),
    )


@router.get("/teams", response_model=list[TeamDetailResponse], status_code=status.HTTP_200_OK)
async def list_teams(request: Request):
    database = request.app.state.database

    team_cursor = database["teams"].find({})
    if hasattr(team_cursor, "to_list"):
        team_docs = await team_cursor.to_list(length=1000)
    elif hasattr(team_cursor, "__aiter__"):
        team_docs = [t async for t in team_cursor]
    else:
        team_docs = getattr(database["teams"], "docs", [])

    teams_response = []
    for team in team_docs:
        manager = await database["users"].find_one({"_id": team.get("manager_id")})

        member_cursor = database["users"].find({"team_id": team["_id"]})
        if hasattr(member_cursor, "to_list"):
            member_docs = await member_cursor.to_list(length=1000)
        elif hasattr(member_cursor, "__aiter__"):
            member_docs = [m async for m in member_cursor]
        else:
            member_docs = [
                m for m in getattr(database["users"], "docs", [])
                if m.get("team_id") == team["_id"]
            ]

        members = [
            TeamMemberResponse(
                id=str(m["_id"]),
                name=m["name"],
                email=m["email"],
                role=m["role"],
                is_active=m.get("is_active", True),
            )
            for m in member_docs
        ]

        teams_response.append(
            TeamDetailResponse(
                id=str(team["_id"]),
                name=team["name"],
                manager_id=str(team["manager_id"]),
                manager_name=manager.get("name") if manager else None,
                manager_email=manager.get("email") if manager else None,
                members=members,
                created_at=(
                    team["created_at"].isoformat()
                    if isinstance(team.get("created_at"), datetime)
                    else None
                ),
            )
        )

    return teams_response


@router.patch("/teams/{team_id}/manager", response_model=TeamDetailResponse, status_code=status.HTTP_200_OK)
async def reassign_team_manager(
    team_id: str,
    payload: UpdateTeamManagerRequest,
    request: Request,
):
    team_oid = _validate_object_id(team_id, "Team ID")
    manager_oid = _validate_object_id(payload.manager_id, "Manager ID")
    database = request.app.state.database

    team = await database["teams"].find_one({"_id": team_oid})
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )

    manager = await database["users"].find_one({"_id": manager_oid})
    if (
        not manager
        or manager.get("role") != "manager"
        or not manager.get("is_active", True)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assigned manager must be an active user with role 'manager'.",
        )

    await database["teams"].update_one(
        {"_id": team_oid},
        {"$set": {"manager_id": manager_oid}},
    )

    updated_team = await database["teams"].find_one({"_id": team_oid})

    member_cursor = database["users"].find({"team_id": team_oid})
    if hasattr(member_cursor, "to_list"):
        member_docs = await member_cursor.to_list(length=1000)
    elif hasattr(member_cursor, "__aiter__"):
        member_docs = [m async for m in member_cursor]
    else:
        member_docs = [
            m for m in getattr(database["users"], "docs", [])
            if m.get("team_id") == team_oid
        ]

    members = [
        TeamMemberResponse(
            id=str(m["_id"]),
            name=m["name"],
            email=m["email"],
            role=m["role"],
            is_active=m.get("is_active", True),
        )
        for m in member_docs
    ]

    return TeamDetailResponse(
        id=str(updated_team["_id"]),
        name=updated_team["name"],
        manager_id=str(manager["_id"]),
        manager_name=manager.get("name"),
        manager_email=manager.get("email"),
        members=members,
        created_at=(
            updated_team["created_at"].isoformat()
            if isinstance(updated_team.get("created_at"), datetime)
            else None
        ),
    )


@router.post("/teams/{team_id}/members", response_model=TeamDetailResponse, status_code=status.HTTP_200_OK)
async def assign_team_member(
    team_id: str,
    payload: AssignTeamMemberRequest,
    request: Request,
):
    team_oid = _validate_object_id(team_id, "Team ID")
    user_oid = _validate_object_id(payload.user_id, "User ID")
    database = request.app.state.database

    team = await database["teams"].find_one({"_id": team_oid})
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )

    user = await database["users"].find_one({"_id": user_oid})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user.get("role") != "employee":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only users with role 'employee' can be assigned as team members.",
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot assign an inactive employee to a team.",
        )

    # Prevent moving employee with open assigned tasks to another team
    if user.get("team_id") and user.get("team_id") != team_oid:
        open_tasks = await database["tasks"].count_documents(
            {"assigned_to": user_oid, "status": {"$in": ["todo", "in_progress", "blocked"]}}
        )
        if open_tasks > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot transfer an employee with open assigned tasks to another team. Unassign or reassign tasks first.",
            )

    # Assign/reassign employee to team (employee belongs to at most one team)
    await database["users"].update_one(
        {"_id": user_oid},
        {"$set": {"team_id": team_oid}},
    )

    manager = await database["users"].find_one({"_id": team.get("manager_id")})
    member_cursor = database["users"].find({"team_id": team_oid})
    if hasattr(member_cursor, "to_list"):
        member_docs = await member_cursor.to_list(length=1000)
    elif hasattr(member_cursor, "__aiter__"):
        member_docs = [m async for m in member_cursor]
    else:
        member_docs = [
            m for m in getattr(database["users"], "docs", [])
            if m.get("team_id") == team_oid
        ]

    members = [
        TeamMemberResponse(
            id=str(m["_id"]),
            name=m["name"],
            email=m["email"],
            role=m["role"],
            is_active=m.get("is_active", True),
        )
        for m in member_docs
    ]

    return TeamDetailResponse(
        id=str(team["_id"]),
        name=team["name"],
        manager_id=str(team["manager_id"]),
        manager_name=manager.get("name") if manager else None,
        manager_email=manager.get("email") if manager else None,
        members=members,
        created_at=(
            team["created_at"].isoformat()
            if isinstance(team.get("created_at"), datetime)
            else None
        ),
    )


@router.delete("/teams/{team_id}/members/{user_id}", status_code=status.HTTP_200_OK)
async def remove_team_member(
    team_id: str,
    user_id: str,
    request: Request,
):
    team_oid = _validate_object_id(team_id, "Team ID")
    user_oid = _validate_object_id(user_id, "User ID")
    database = request.app.state.database

    team = await database["teams"].find_one({"_id": team_oid})
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )

    user = await database["users"].find_one({"_id": user_oid})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user.get("team_id") == team_oid:
        open_tasks = await database["tasks"].count_documents(
            {"assigned_to": user_oid, "status": {"$in": ["todo", "in_progress", "blocked"]}}
        )
        if open_tasks > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot remove an employee with open assigned tasks from their team. Unassign or reassign tasks first.",
            )

        await database["users"].update_one(
            {"_id": user_oid},
            {"$set": {"team_id": None}},
        )

    return {"status": "ok", "message": "Member removed from team"}
