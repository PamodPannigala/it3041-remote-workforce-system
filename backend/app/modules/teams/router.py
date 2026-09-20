from datetime import datetime
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.app.api.dependencies import get_current_user, require_roles
from backend.app.schemas import EmployeeTeamSummaryResponse, TeamDetailResponse, TeamMemberResponse

router = APIRouter(prefix="/teams", tags=["Team Scoped Access"])


def _validate_object_id(id_str: str, field_name: str = "ID") -> ObjectId:
    if not isinstance(id_str, str) or not ObjectId.is_valid(id_str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name} format",
        )
    return ObjectId(id_str)


@router.get(
    "/managed",
    response_model=list[TeamDetailResponse],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles("manager", "admin"))],
)
async def get_managed_teams(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Manager endpoint: Returns strictly the teams managed by the current manager."""
    database = request.app.state.database

    # If admin calls this endpoint, return all teams managed by admin or empty if none.
    # Scoped query on manager_id ensures strict boundary.
    filter_query = {"manager_id": current_user["_id"]}
    team_cursor = database["teams"].find(filter_query)

    if hasattr(team_cursor, "to_list"):
        team_docs = await team_cursor.to_list(length=100)
    elif hasattr(team_cursor, "__aiter__"):
        team_docs = [t async for t in team_cursor]
    else:
        team_docs = [
            t for t in getattr(database["teams"], "docs", [])
            if t.get("manager_id") == current_user["_id"]
        ]

    teams_response = []
    for team in team_docs:
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
                manager_id=str(current_user["_id"]),
                manager_name=current_user.get("name"),
                manager_email=current_user.get("email"),
                members=members,
                created_at=(
                    team["created_at"].isoformat()
                    if isinstance(team.get("created_at"), datetime)
                    else None
                ),
            )
        )

    return teams_response


@router.get(
    "/my-summary",
    response_model=EmployeeTeamSummaryResponse,
    status_code=status.HTTP_200_OK,
)
async def get_my_team_summary(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Employee endpoint: Returns high-level summary of the user's assigned team only."""
    database = request.app.state.database

    team_id = current_user.get("team_id")
    if not team_id:
        return EmployeeTeamSummaryResponse(has_team=False)

    team = await database["teams"].find_one({"_id": team_id})
    if not team:
        return EmployeeTeamSummaryResponse(has_team=False)

    manager = await database["users"].find_one({"_id": team.get("manager_id")})

    return EmployeeTeamSummaryResponse(
        has_team=True,
        team_id=str(team["_id"]),
        team_name=team["name"],
        manager_name=manager.get("name") if manager else None,
        manager_email=manager.get("email") if manager else None,
    )


@router.get(
    "/{team_id}/members",
    response_model=list[TeamMemberResponse],
    status_code=status.HTTP_200_OK,
)
async def get_team_members(
    team_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Protected team member listing: Only permitted for admin or the assigned manager of THIS team."""
    team_oid = _validate_object_id(team_id, "Team ID")
    database = request.app.state.database

    team = await database["teams"].find_one({"_id": team_oid})
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )

    # Role and scope check:
    user_role = current_user.get("role")
    if user_role != "admin":
        if user_role != "manager" or team.get("manager_id") != current_user["_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You are not authorized to view members of this team.",
            )

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

    return [
        TeamMemberResponse(
            id=str(m["_id"]),
            name=m["name"],
            email=m["email"],
            role=m["role"],
            is_active=m.get("is_active", True),
        )
        for m in member_docs
    ]
