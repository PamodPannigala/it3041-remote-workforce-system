from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    StringConstraints,
)


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=2,
            max_length=100,
        ),
    ]
    email: EmailStr
    password: SecretStr = Field(min_length=15, max_length=128)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 900


class UserResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    role: Literal["employee", "manager", "admin"]
    is_active: bool = True
    team_id: str | None = None


class UserAdminResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    role: Literal["employee", "manager", "admin"]
    is_active: bool
    team_id: str | None = None
    team_name: str | None = None
    created_at: str | None = None


class UserListResponse(BaseModel):
    items: list[UserAdminResponse]
    total: int
    page: int
    limit: int
    total_pages: int


class UpdateUserRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["employee", "manager", "admin"]


class UpdateUserStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool


class CreateTeamRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=2,
            max_length=100,
        ),
    ]
    manager_id: str


class UpdateTeamManagerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manager_id: str


class AssignTeamMemberRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str


class TeamMemberResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    role: Literal["employee", "manager", "admin"]
    is_active: bool


class TeamResponse(BaseModel):
    id: str
    name: str
    manager_id: str
    manager_name: str | None = None
    manager_email: str | None = None
    members_count: int = 0
    created_at: str | None = None


class TeamDetailResponse(BaseModel):
    id: str
    name: str
    manager_id: str
    manager_name: str | None = None
    manager_email: str | None = None
    members: list[TeamMemberResponse] = []
    created_at: str | None = None


class EmployeeTeamSummaryResponse(BaseModel):
    has_team: bool
    team_id: str | None = None
    team_name: str | None = None
    manager_name: str | None = None
    manager_email: str | None = None