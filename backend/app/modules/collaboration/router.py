from datetime import datetime, timezone
import math
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from backend.app.api.dependencies import get_current_user, require_roles
from backend.app.schemas import (
    CollaborationMessageListResponse,
    CollaborationMessageResponse,
    CreateCollaborationMessageRequest,
    UpdateCollaborationMessageRequest,
)

router = APIRouter(prefix="/collaboration/messages", tags=["Collaboration Messages"])
admin_collaboration_router = APIRouter(
    prefix="/admin/collaboration/messages",
    tags=["Admin Collaboration Audit"],
    dependencies=[Depends(require_roles("admin"))],
)


def _validate_object_id(id_str: str, field_name: str = "ID") -> ObjectId:
    if not isinstance(id_str, str) or not ObjectId.is_valid(id_str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name} format",
        )
    return ObjectId(id_str)


def _format_message_doc(
    doc: dict,
    user_map: dict | None = None,
    team_map: dict | None = None,
    include_raw_content_if_deleted: bool = False,
) -> CollaborationMessageResponse:
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

    edited_at = doc.get("edited_at")
    if isinstance(edited_at, datetime):
        edited_at = edited_at.isoformat()
    elif edited_at is not None:
        edited_at = str(edited_at)

    deleted_at = doc.get("deleted_at")
    if isinstance(deleted_at, datetime):
        deleted_at = deleted_at.isoformat()
    elif deleted_at is not None:
        deleted_at = str(deleted_at)

    is_deleted = bool(doc.get("is_deleted", False))

    if is_deleted and not include_raw_content_if_deleted:
        content = None
    else:
        content = doc.get("content")

    sender_id_str = str(doc["sender_id"]) if doc.get("sender_id") else ""
    sender_user = user_map.get(sender_id_str) if sender_id_str else None

    team_id_str = str(doc["team_id"]) if doc.get("team_id") else ""
    team_obj = team_map.get(team_id_str) if team_id_str else None

    return CollaborationMessageResponse(
        id=str(doc["_id"]),
        team_id=team_id_str,
        sender_id=sender_id_str,
        content=content,
        created_at=created_at,
        updated_at=updated_at,
        edited_at=edited_at,
        is_deleted=is_deleted,
        deleted_at=deleted_at,
        sender_name=sender_user.get("name") if sender_user else None,
        sender_email=sender_user.get("email") if sender_user else None,
        team_name=team_obj.get("name") if team_obj else None,
    )


async def _enrich_and_format_messages(
    message_docs: list[dict],
    database,
    include_raw_content_if_deleted: bool = False,
) -> list[CollaborationMessageResponse]:
    if not message_docs:
        return []

    sender_ids = set()
    team_ids = set()

    for doc in message_docs:
        if doc.get("sender_id"):
            sender_ids.add(doc["sender_id"])
        if doc.get("team_id"):
            team_ids.add(doc["team_id"])

    user_oids = [
        uid if isinstance(uid, ObjectId) else ObjectId(str(uid))
        for uid in sender_ids
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

    return [
        _format_message_doc(
            doc,
            user_map=user_map,
            team_map=team_map,
            include_raw_content_if_deleted=include_raw_content_if_deleted,
        )
        for doc in message_docs
    ]


async def _enrich_and_format_message(
    message_doc: dict,
    database,
    include_raw_content_if_deleted: bool = False,
) -> CollaborationMessageResponse:
    results = await _enrich_and_format_messages(
        [message_doc],
        database,
        include_raw_content_if_deleted=include_raw_content_if_deleted,
    )
    return results[0]


# =========================================================================
# User / Team Endpoints
# =========================================================================


@router.post(
    "",
    response_model=CollaborationMessageResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("employee", "manager"))],
)
async def create_collaboration_message(
    payload: CreateCollaborationMessageRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Post a collaboration message strictly within the user's assigned or managed team scope."""
    team_oid = _validate_object_id(payload.team_id, "Team ID")
    database = request.app.state.database

    team = await database["teams"].find_one({"_id": team_oid})
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )

    user_role = current_user.get("role")
    if user_role == "employee":
        user_team_id = current_user.get("team_id")
        if not user_team_id or user_team_id != team_oid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You can only post messages to your assigned team",
            )
    elif user_role == "manager":
        if team.get("manager_id") != current_user["_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not manage this team",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation not permitted",
        )

    now = datetime.now(timezone.utc)
    message_doc = {
        "team_id": team_oid,
        "sender_id": current_user["_id"],
        "content": payload.content,
        "created_at": now,
        "updated_at": now,
        "edited_at": None,
        "is_deleted": False,
        "deleted_at": None,
        "deleted_by": None,
    }

    res = await database["collaboration_messages"].insert_one(message_doc)
    message_doc["_id"] = getattr(res, "inserted_id", message_doc.get("_id"))
    return await _enrich_and_format_message(message_doc, database)


@router.get(
    "",
    response_model=CollaborationMessageListResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles("employee", "manager"))],
)
async def list_collaboration_messages(
    request: Request,
    team_id: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """List team collaboration messages ordered newest first."""
    database = request.app.state.database
    user_role = current_user.get("role")

    if user_role == "employee":
        user_team_id = current_user.get("team_id")
        if team_id is not None:
            req_team_oid = _validate_object_id(team_id, "Team ID")
            if not user_team_id or req_team_oid != user_team_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: You can only view messages from your assigned team",
                )
            target_team_oid = req_team_oid
        else:
            if not user_team_id:
                return CollaborationMessageListResponse(
                    items=[],
                    total=0,
                    page=page,
                    limit=limit,
                    total_pages=0,
                )
            target_team_oid = user_team_id
    elif user_role == "manager":
        if not team_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="team_id query parameter is required for managers",
            )
        req_team_oid = _validate_object_id(team_id, "Team ID")
        team = await database["teams"].find_one({"_id": req_team_oid})
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
        target_team_oid = req_team_oid
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation not permitted",
        )

    filter_query = {"team_id": target_team_oid}
    total = await database["collaboration_messages"].count_documents(filter_query)
    total_pages = math.ceil(total / limit) if total > 0 else 0
    skip = (page - 1) * limit

    cursor = (
        database["collaboration_messages"]
        .find(filter_query)
        .sort([("created_at", -1), ("_id", -1)])
        .skip(skip)
        .limit(limit)
    )
    if hasattr(cursor, "to_list"):
        message_docs = await cursor.to_list(length=limit)
    elif hasattr(cursor, "__aiter__"):
        message_docs = [doc async for doc in cursor]
    else:
        all_matched = [
            m for m in getattr(database["collaboration_messages"], "docs", [])
            if m.get("team_id") == target_team_oid
        ]
        all_matched.sort(key=lambda x: x.get("created_at"), reverse=True)
        message_docs = all_matched[skip : skip + limit]

    items = await _enrich_and_format_messages(
        message_docs,
        database,
        include_raw_content_if_deleted=False,
    )
    return CollaborationMessageListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@router.get(
    "/{message_id}",
    response_model=CollaborationMessageResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles("employee", "manager"))],
)
async def get_collaboration_message(
    message_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Retrieve details for a single collaboration message within user's team scope."""
    message_oid = _validate_object_id(message_id, "Message ID")
    database = request.app.state.database

    message = await database["collaboration_messages"].find_one({"_id": message_oid})
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    user_role = current_user.get("role")
    if user_role == "employee":
        user_team_id = current_user.get("team_id")
        if not user_team_id or user_team_id != message.get("team_id"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You are not a member of this team",
            )
    elif user_role == "manager":
        team = await database["teams"].find_one({"_id": message.get("team_id")})
        if not team or team.get("manager_id") != current_user["_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not manage this team",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation not permitted",
        )

    return await _enrich_and_format_message(
        message,
        database,
        include_raw_content_if_deleted=False,
    )


@router.patch(
    "/{message_id}",
    response_model=CollaborationMessageResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles("employee", "manager"))],
)
async def update_collaboration_message(
    message_id: str,
    payload: UpdateCollaborationMessageRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Update message content (permitted only for the original sender)."""
    message_oid = _validate_object_id(message_id, "Message ID")
    database = request.app.state.database

    message = await database["collaboration_messages"].find_one({"_id": message_oid})
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    user_role = current_user.get("role")
    if user_role == "employee":
        user_team_id = current_user.get("team_id")
        if not user_team_id or user_team_id != message.get("team_id"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You are not a member of this team",
            )
    elif user_role == "manager":
        team = await database["teams"].find_one({"_id": message.get("team_id")})
        if not team or team.get("manager_id") != current_user["_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not manage this team",
            )

    if message.get("sender_id") != current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Only the original sender can edit this message",
        )

    if message.get("is_deleted", False):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot edit a deleted message",
        )

    now = datetime.now(timezone.utc)
    update_fields = {
        "content": payload.content,
        "updated_at": now,
        "edited_at": now,
    }

    await database["collaboration_messages"].update_one(
        {"_id": message_oid},
        {"$set": update_fields},
    )

    message.update(update_fields)
    return await _enrich_and_format_message(
        message,
        database,
        include_raw_content_if_deleted=False,
    )


@router.delete(
    "/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("employee", "manager"))],
)
async def delete_collaboration_message(
    message_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Soft-delete a message (permitted only for the original sender)."""
    message_oid = _validate_object_id(message_id, "Message ID")
    database = request.app.state.database

    message = await database["collaboration_messages"].find_one({"_id": message_oid})
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    user_role = current_user.get("role")
    if user_role == "employee":
        user_team_id = current_user.get("team_id")
        if not user_team_id or user_team_id != message.get("team_id"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You are not a member of this team",
            )
    elif user_role == "manager":
        team = await database["teams"].find_one({"_id": message.get("team_id")})
        if not team or team.get("manager_id") != current_user["_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not manage this team",
            )

    if message.get("sender_id") != current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Only the original sender can delete this message",
        )

    if message.get("is_deleted", False):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Message is already deleted",
        )

    now = datetime.now(timezone.utc)
    update_fields = {
        "is_deleted": True,
        "deleted_at": now,
        "deleted_by": current_user["_id"],
        "updated_at": now,
    }

    await database["collaboration_messages"].update_one(
        {"_id": message_oid},
        {"$set": update_fields},
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =========================================================================
# Admin Read-Only Audit Endpoints
# =========================================================================


@admin_collaboration_router.get(
    "",
    response_model=CollaborationMessageListResponse,
    status_code=status.HTTP_200_OK,
)
async def admin_list_collaboration_messages(
    request: Request,
    team_id: str | None = None,
    sender_id: str | None = None,
    include_deleted: bool = True,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """Admin read-only audit endpoint: List organization-wide collaboration messages."""
    database = request.app.state.database
    filter_query = {}

    if team_id:
        filter_query["team_id"] = _validate_object_id(team_id, "Team ID")
    if sender_id:
        filter_query["sender_id"] = _validate_object_id(sender_id, "Sender ID")
    if not include_deleted:
        filter_query["is_deleted"] = False

    total = await database["collaboration_messages"].count_documents(filter_query)
    total_pages = math.ceil(total / limit) if total > 0 else 0
    skip = (page - 1) * limit

    cursor = (
        database["collaboration_messages"]
        .find(filter_query)
        .sort([("created_at", -1), ("_id", -1)])
        .skip(skip)
        .limit(limit)
    )
    if hasattr(cursor, "to_list"):
        message_docs = await cursor.to_list(length=limit)
    elif hasattr(cursor, "__aiter__"):
        message_docs = [doc async for doc in cursor]
    else:
        all_matched = [
            m for m in getattr(database["collaboration_messages"], "docs", [])
        ]
        if "team_id" in filter_query:
            all_matched = [m for m in all_matched if m.get("team_id") == filter_query["team_id"]]
        if "sender_id" in filter_query:
            all_matched = [m for m in all_matched if m.get("sender_id") == filter_query["sender_id"]]
        if not include_deleted:
            all_matched = [m for m in all_matched if not m.get("is_deleted", False)]
        all_matched.sort(key=lambda x: x.get("created_at"), reverse=True)
        message_docs = all_matched[skip : skip + limit]

    items = await _enrich_and_format_messages(
        message_docs,
        database,
        include_raw_content_if_deleted=True,
    )
    return CollaborationMessageListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@admin_collaboration_router.get(
    "/{message_id}",
    response_model=CollaborationMessageResponse,
    status_code=status.HTTP_200_OK,
)
async def admin_get_collaboration_message(
    message_id: str,
    request: Request,
):
    """Admin read-only audit endpoint: Retrieve single collaboration message with audit details."""
    message_oid = _validate_object_id(message_id, "Message ID")
    database = request.app.state.database

    message = await database["collaboration_messages"].find_one({"_id": message_oid})
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    return await _enrich_and_format_message(
        message,
        database,
        include_raw_content_if_deleted=True,
    )
