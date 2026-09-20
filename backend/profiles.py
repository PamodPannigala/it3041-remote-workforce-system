from datetime import datetime
import math
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from dependencies import get_current_user, require_roles
from schemas import (
    EmployeeProfileListResponse,
    EmployeeProfileResponse,
    UpdateEmployeeProfileRequest,
)

router = APIRouter(prefix="/profiles", tags=["Employee Work Profiles"])


def _validate_object_id(id_str: str, field_name: str = "ID") -> ObjectId:
    if not isinstance(id_str, str) or not ObjectId.is_valid(id_str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name} format",
        )
    return ObjectId(id_str)


def _format_profile_doc(doc: dict) -> EmployeeProfileResponse:
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

    return EmployeeProfileResponse(
        id=str(doc["_id"]),
        user_id=str(doc["user_id"]),
        job_title=doc.get("job_title", ""),
        skills=doc.get("skills", []),
        availability_status=doc.get("availability_status", "available"),
        weekly_capacity_hours=float(doc.get("weekly_capacity_hours", 40.0)),
        created_at=created_at,
        updated_at=updated_at,
    )


@router.get(
    "/me",
    response_model=EmployeeProfileResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles("employee", "manager"))],
)
async def get_my_profile(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Retrieve the authenticated caller's employee work profile without auto-creating."""
    database = request.app.state.database
    profile = await database["employee_profiles"].find_one({"user_id": current_user["_id"]})
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee profile not found",
        )
    return _format_profile_doc(profile)


@router.put(
    "/me",
    response_model=EmployeeProfileResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles("employee", "manager"))],
)
async def update_my_profile(
    payload: UpdateEmployeeProfileRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Create or update the authenticated caller's employee work profile."""
    database = request.app.state.database
    now = datetime.utcnow()
    existing = await database["employee_profiles"].find_one({"user_id": current_user["_id"]})

    if not existing:
        new_doc = {
            "user_id": current_user["_id"],
            "job_title": payload.job_title,
            "skills": payload.skills,
            "availability_status": payload.availability_status,
            "weekly_capacity_hours": float(payload.weekly_capacity_hours),
            "created_at": now,
            "updated_at": now,
        }
        res = await database["employee_profiles"].insert_one(new_doc)
        new_doc["_id"] = getattr(res, "inserted_id", new_doc.get("_id"))
        return _format_profile_doc(new_doc)
    else:
        update_data = {
            "job_title": payload.job_title,
            "skills": payload.skills,
            "availability_status": payload.availability_status,
            "weekly_capacity_hours": float(payload.weekly_capacity_hours),
            "updated_at": now,
        }
        await database["employee_profiles"].update_one(
            {"_id": existing["_id"]},
            {"$set": update_data},
        )
        existing.update(update_data)
        return _format_profile_doc(existing)


@router.get(
    "/user/{user_id}",
    response_model=EmployeeProfileResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles("manager", "admin"))],
)
async def get_user_profile(
    user_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Manager/Admin endpoint: Access individual employee profile with team scoping."""
    user_oid = _validate_object_id(user_id, "User ID")
    database = request.app.state.database

    target_user = await database["users"].find_one({"_id": user_oid})
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user_role = current_user.get("role")
    if user_role != "admin":
        if not target_user.get("is_active", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Target user is inactive",
            )
        team_id = target_user.get("team_id")
        if not team_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Target user does not belong to a managed team",
            )
        team = await database["teams"].find_one({"_id": team_id})
        if not team or team.get("manager_id") != current_user["_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not manage this user's team",
            )

    profile = await database["employee_profiles"].find_one({"user_id": user_oid})
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee profile not found",
        )

    return _format_profile_doc(profile)


@router.get(
    "/team/{team_id}",
    response_model=EmployeeProfileListResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles("manager", "admin"))],
)
async def get_team_profiles(
    team_id: str,
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """Manager/Admin endpoint: List paginated profiles for members of a team."""
    team_oid = _validate_object_id(team_id, "Team ID")
    database = request.app.state.database

    team = await database["teams"].find_one({"_id": team_oid})
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )

    user_role = current_user.get("role")
    if user_role != "admin":
        if user_role != "manager" or team.get("manager_id") != current_user["_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not manage this team",
            )

    member_cursor = database["users"].find({"team_id": team_oid, "is_active": True})
    if hasattr(member_cursor, "to_list"):
        members = await member_cursor.to_list(length=1000)
    elif hasattr(member_cursor, "__aiter__"):
        members = [m async for m in member_cursor]
    else:
        members = [
            m for m in getattr(database["users"], "docs", [])
            if m.get("team_id") == team_oid and m.get("is_active", True)
        ]

    member_user_ids = [m["_id"] for m in members]
    if not member_user_ids:
        return EmployeeProfileListResponse(
            items=[],
            total=0,
            page=page,
            limit=limit,
            total_pages=0,
        )

    filter_query = {"user_id": {"$in": member_user_ids}}
    total = await database["employee_profiles"].count_documents(filter_query)
    total_pages = math.ceil(total / limit) if total > 0 else 0
    skip = (page - 1) * limit

    profile_cursor = (
        database["employee_profiles"]
        .find(filter_query)
        .skip(skip)
        .limit(limit)
    )
    if hasattr(profile_cursor, "to_list"):
        profile_docs = await profile_cursor.to_list(length=limit)
    elif hasattr(profile_cursor, "__aiter__"):
        profile_docs = [p async for p in profile_cursor]
    else:
        profile_docs = [
            p for p in getattr(database["employee_profiles"], "docs", [])
            if p.get("user_id") in member_user_ids
        ][skip : skip + limit]

    items = [_format_profile_doc(doc) for doc in profile_docs]

    return EmployeeProfileListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )
