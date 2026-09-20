from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    StringConstraints,
    field_validator,
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


class UpdateEmployeeProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_title: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=100,
        ),
    ]
    skills: list[str] = Field(default_factory=list)
    availability_status: Literal["available", "busy", "on_leave"] = "available"
    weekly_capacity_hours: float = Field(default=40.0, ge=0.0, le=80.0)

    @field_validator("skills", mode="before")
    @classmethod
    def validate_and_normalize_skills(cls, v):
        if not isinstance(v, list):
            raise ValueError("Skills must be a list of strings")
        normalized = []
        seen = set()
        for item in v:
            if not isinstance(item, str):
                raise ValueError("Each skill must be a string")
            trimmed = item.strip()
            if not trimmed:
                raise ValueError("Skill item cannot be empty or whitespace only")
            if len(trimmed) > 50:
                raise ValueError("Skill item cannot exceed 50 characters")
            key = trimmed.lower()
            if key not in seen:
                seen.add(key)
                normalized.append(trimmed)
        return normalized


class EmployeeProfileResponse(BaseModel):
    id: str
    user_id: str
    job_title: str
    skills: list[str]
    availability_status: Literal["available", "busy", "on_leave"]
    weekly_capacity_hours: float
    created_at: str | None = None
    updated_at: str | None = None


class EmployeeProfileListResponse(BaseModel):
    items: list[EmployeeProfileResponse]
    total: int
    page: int
    limit: int
    total_pages: int


class CreateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=200,
        ),
    ]
    description: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=0,
            max_length=2000,
        ),
    ] = ""
    team_id: str
    assigned_to: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    due_date: str | None = None
    estimated_hours: float = Field(default=0.0, ge=0.0, le=1000.0)

    @field_validator("required_skills", mode="before")
    @classmethod
    def validate_skills(cls, v):
        if not isinstance(v, list):
            raise ValueError("Required skills must be a list of strings")
        normalized = []
        seen = set()
        for item in v:
            if not isinstance(item, str):
                raise ValueError("Each skill must be a string")
            trimmed = item.strip()
            if not trimmed:
                raise ValueError("Skill cannot be empty or whitespace only")
            if len(trimmed) > 50:
                raise ValueError("Skill cannot exceed 50 characters")
            key = trimmed.lower()
            if key not in seen:
                seen.add(key)
                normalized.append(trimmed)
        return normalized

    @field_validator("due_date")
    @classmethod
    def validate_due_date(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            v_str = v.strip()
            if not v_str:
                return None
            try:
                datetime.fromisoformat(v_str.replace("Z", "+00:00"))
                return v_str
            except ValueError:
                raise ValueError("due_date must be a valid ISO 8601 datetime string")
        return v


class UpdateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=200,
        ),
    ] | None = None
    description: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=0,
            max_length=2000,
        ),
    ] | None = None
    required_skills: list[str] | None = None
    priority: Literal["low", "medium", "high", "urgent"] | None = None
    due_date: str | None = None
    estimated_hours: float | None = Field(default=None, ge=0.0, le=1000.0)

    @field_validator("required_skills", mode="before")
    @classmethod
    def validate_skills(cls, v):
        if v is None:
            return None
        if not isinstance(v, list):
            raise ValueError("Required skills must be a list of strings")
        normalized = []
        seen = set()
        for item in v:
            if not isinstance(item, str):
                raise ValueError("Each skill must be a string")
            trimmed = item.strip()
            if not trimmed:
                raise ValueError("Skill cannot be empty or whitespace only")
            if len(trimmed) > 50:
                raise ValueError("Skill cannot exceed 50 characters")
            key = trimmed.lower()
            if key not in seen:
                seen.add(key)
                normalized.append(trimmed)
        return normalized

    @field_validator("due_date")
    @classmethod
    def validate_due_date(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            v_str = v.strip()
            if not v_str:
                return None
            try:
                datetime.fromisoformat(v_str.replace("Z", "+00:00"))
                return v_str
            except ValueError:
                raise ValueError("due_date must be a valid ISO 8601 datetime string")
        return v


class UpdateTaskAssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assigned_to: str | None = None


class UpdateTaskStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["todo", "in_progress", "blocked", "completed"]


class AddProgressUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    percentage: int = Field(ge=0, le=100)
    notes: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=1000,
        ),
    ]


class AddBlockerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=1000,
        ),
    ]


class ProgressUpdateResponse(BaseModel):
    id: str
    user_id: str
    percentage: int
    notes: str
    logged_at: str


class BlockerResponse(BaseModel):
    id: str
    user_id: str
    description: str
    is_resolved: bool
    resolved_at: str | None = None
    resolved_by: str | None = None
    created_at: str


class TaskResponse(BaseModel):
    id: str
    title: str
    description: str
    team_id: str
    created_by: str
    assigned_to: str | None = None
    required_skills: list[str] = []
    priority: Literal["low", "medium", "high", "urgent"]
    status: Literal["todo", "in_progress", "blocked", "completed"]
    due_date: str | None = None
    estimated_hours: float
    progress_history: list[ProgressUpdateResponse] = []
    blockers: list[BlockerResponse] = []
    created_at: str | None = None
    updated_at: str | None = None


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int
    page: int
    limit: int
    total_pages: int
