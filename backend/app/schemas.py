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


class ResolveBlockerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution_note: Annotated[
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
    user_name: str | None = None
    user_email: str | None = None


class BlockerResponse(BaseModel):
    id: str
    user_id: str
    description: str
    is_resolved: bool
    resolution_note: str | None = None
    resolved_at: str | None = None
    resolved_by: str | None = None
    created_at: str
    user_name: str | None = None
    user_email: str | None = None
    resolved_by_name: str | None = None
    resolved_by_email: str | None = None


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
    assigned_to_name: str | None = None
    assigned_to_email: str | None = None
    created_by_name: str | None = None
    created_by_email: str | None = None
    team_name: str | None = None


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int
    page: int
    limit: int
    total_pages: int


class CreateCollaborationMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    team_id: str
    content: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=4000,
        ),
    ]


class UpdateCollaborationMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=4000,
        ),
    ]


class CollaborationMessageResponse(BaseModel):
    id: str
    team_id: str
    sender_id: str
    content: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    edited_at: str | None = None
    is_deleted: bool = False
    deleted_at: str | None = None
    sender_name: str | None = None
    sender_email: str | None = None
    team_name: str | None = None


class CollaborationMessageListResponse(BaseModel):
    items: list[CollaborationMessageResponse] = Field(default_factory=list)
    total: int
    page: int
    limit: int
    total_pages: int


class CreatePulseSurveyResponseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workload_manageability: Annotated[int, Field(strict=True, ge=1, le=5)]
    work_life_balance: Annotated[int, Field(strict=True, ge=1, le=5)]
    team_support: Annotated[int, Field(strict=True, ge=1, le=5)]
    engagement: Annotated[int, Field(strict=True, ge=1, le=5)]
    optional_comment: str | None = None

    @field_validator("optional_comment", mode="before")
    @classmethod
    def validate_and_normalize_comment(cls, v):
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("optional_comment must be a string")
        stripped = v.strip()
        if not stripped:
            return None
        if len(stripped) > 1000:
            raise ValueError("optional_comment cannot exceed 1000 characters")
        return stripped


class UpdatePulseSurveyResponseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workload_manageability: Annotated[int, Field(strict=True, ge=1, le=5)] | None = None
    work_life_balance: Annotated[int, Field(strict=True, ge=1, le=5)] | None = None
    team_support: Annotated[int, Field(strict=True, ge=1, le=5)] | None = None
    engagement: Annotated[int, Field(strict=True, ge=1, le=5)] | None = None
    optional_comment: str | None = None
    expected_revision: Annotated[int, Field(strict=True, ge=1)]

    @field_validator(
        "workload_manageability",
        "work_life_balance",
        "team_support",
        "engagement",
        mode="before",
    )
    @classmethod
    def validate_rating_not_none(cls, v, info):
        if v is None:
            raise ValueError(f"{info.field_name} cannot be null")
        return v

    @field_validator("optional_comment", mode="before")
    @classmethod
    def validate_and_normalize_comment(cls, v):
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("optional_comment must be a string")
        stripped = v.strip()
        if not stripped:
            return None
        if len(stripped) > 1000:
            raise ValueError("optional_comment cannot exceed 1000 characters")
        return stripped


class PulseSurveyResponse(BaseModel):
    id: str
    user_id: str
    team_id: str
    team_name: str | None = None
    week_start: str
    workload_manageability: int
    work_life_balance: int
    team_support: int
    engagement: int
    optional_comment: str | None = None
    submitted_at: str
    updated_at: str | None = None
    is_edited: bool = False
    revision: int = 1


class PulseSurveyResponseList(BaseModel):
    items: list[PulseSurveyResponse] = Field(default_factory=list)
    total: int
    page: int
    limit: int
    total_pages: int


class PulseMetricAverages(BaseModel):
    workload_manageability: float
    work_life_balance: float
    team_support: float
    engagement: float


class PulseTeamSummaryResponse(BaseModel):
    available: bool
    team_id: str
    team_name: str | None = None
    week_start: str
    response_count: int
    minimum_required: int = 3
    averages: PulseMetricAverages | None = None
    message: str | None = None


class PulseAuditRecordResponse(BaseModel):
    id: str
    team_id: str
    team_name: str | None = None
    week_start: str
    submitted_at: str


class PulseAuditListResponse(BaseModel):
    items: list[PulseAuditRecordResponse] = Field(default_factory=list)
    total: int
    page: int
    limit: int
    total_pages: int


class AdminPulseSummaryResponse(BaseModel):
    week_start: str
    items: list[PulseTeamSummaryResponse] = Field(default_factory=list)


# =========================================================================
# Information Retrieval Schemas
# =========================================================================


class SearchResultItem(BaseModel):
    source_type: Literal["task", "collaboration"]
    record_id: str
    title: str | None = None
    snippet: str
    score: float
    matched_terms: list[str] = Field(default_factory=list)
    team_id: str | None = None
    team_name: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class SearchResponse(BaseModel):
    query: str
    source: Literal["all", "tasks", "collaboration"]
    total_candidates: int
    total_matches: int
    results: list[SearchResultItem] = Field(default_factory=list)
