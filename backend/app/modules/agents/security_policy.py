from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from backend.app.modules.agents.protocol import (
    AgentFinding,
    AgentIntent,
    AgentName,
    AgentRequest,
    EvidenceReference,
    EvidenceSourceType,
)

PrincipalRole = Literal["employee", "manager", "admin"]


def _ensure_utc(v: datetime | None) -> datetime:
    if v is None:
        return datetime.now(timezone.utc)
    if v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v.astimezone(timezone.utc)


class AuthenticatedPrincipal(BaseModel):
    """
    Trusted authorization context resolved strictly by server-side authentication
    and database lookups.

    Security Note: Never construct this principal from untrusted client JSON or A2A message headers.
    Later routers and services must resolve this model directly from the authenticated session user
    and verified team management records.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
    ]
    role: PrincipalRole
    assigned_team_id: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
    ] | None = None
    managed_team_ids: list[
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
        ]
    ] = Field(default_factory=list)
    resolved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_admin_org_wide_read(self) -> bool:
        """Explicit computed property determining whether principal possesses organization-wide read scope."""
        return self.role == "admin"

    @field_validator("resolved_at", mode="before")
    @classmethod
    def validate_resolved_at(cls, v):
        return _ensure_utc(v)

    @field_validator("managed_team_ids", mode="before")
    @classmethod
    def deduplicate_managed_teams(cls, v):
        if not v:
            return []
        if isinstance(v, list):
            # Preserve order while deduplicating
            return list(dict.fromkeys(str(item).strip() for item in v if str(item).strip()))
        return v

    @model_validator(mode="after")
    def validate_role_team_constraints(self) -> "AuthenticatedPrincipal":
        if self.role == "employee" and len(self.managed_team_ids) > 0:
            raise ValueError("Employee principal cannot carry managed_team_ids")
        return self


class AuthorizationDecision(BaseModel):
    """
    Structured authorization decision returned by security policies.
    Guaranteed to contain only safe, PII-free reason codes and messages.
    """

    model_config = ConfigDict(extra="forbid")

    allowed: bool
    safe_reason_code: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
    ]
    safe_message: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
    ]


# =========================================================================
# 1. Agent Capability Matrix & Allowlist
# =========================================================================

AGENT_ALLOWED_INTENTS: dict[AgentName, set[AgentIntent]] = {
    "coordinator": {
        "productivity_analysis",
        "collaboration_analysis",
        "wellbeing_analysis",
        "task_assignment_recommendation",
        "task_delay_analysis",
        "team_workload_analysis",
        "general_workforce_question",
    },
    "productivity": {
        "productivity_analysis",
        "task_delay_analysis",
        "team_workload_analysis",
    },
    "collaboration": {
        "collaboration_analysis",
        "task_delay_analysis",
    },
    "wellbeing": {
        "wellbeing_analysis",
        "team_workload_analysis",
    },
    "task_assigning": {
        "task_assignment_recommendation",
    },
}

AGENT_ALLOWED_EVIDENCE_SOURCES: dict[AgentName, set[EvidenceSourceType]] = {
    "coordinator": {
        "task",
        "collaboration_message",
        "pulse_summary",
        "employee_profile",
        "agent_finding",
    },
    "productivity": {
        "task",
        "agent_finding",
    },
    "collaboration": {
        "task",
        "collaboration_message",
        "agent_finding",
    },
    "wellbeing": {
        "pulse_summary",
        "agent_finding",
    },
    "task_assigning": {
        "task",
        "employee_profile",
        "agent_finding",
    },
}


def validate_agent_capability(
    agent: AgentName,
    intent: AgentIntent,
    evidence_sources: list[EvidenceSourceType] | None = None,
) -> AuthorizationDecision:
    """
    Validates whether an agent is authorized to handle a given intent and evidence sources.
    Strictly forbids cross-domain leakage (e.g. pulse summaries or collaboration text to task assigning).
    """
    allowed_intents = AGENT_ALLOWED_INTENTS.get(agent, set())
    if intent not in allowed_intents:
        return AuthorizationDecision(
            allowed=False,
            safe_reason_code="AGENT_INTENT_NOT_ALLOWED",
            safe_message=f"Agent '{agent}' is not authorized to handle intent '{intent}'",
        )

    allowed_sources = AGENT_ALLOWED_EVIDENCE_SOURCES.get(agent, set())
    if evidence_sources:
        for source in evidence_sources:
            if source not in allowed_sources:
                return AuthorizationDecision(
                    allowed=False,
                    safe_reason_code="AGENT_EVIDENCE_SOURCE_NOT_ALLOWED",
                    safe_message=f"Agent '{agent}' is not authorized to process evidence source '{source}'",
                )

    return AuthorizationDecision(
        allowed=True,
        safe_reason_code="AGENT_CAPABILITY_AUTHORIZED",
        safe_message="Agent capability and evidence sources authorized",
    )


# =========================================================================
# 2. Role Policy
# =========================================================================

EMPLOYEE_ALLOWED_INTENTS: set[AgentIntent] = {
    "productivity_analysis",
    "collaboration_analysis",
    "wellbeing_analysis",
    "task_delay_analysis",
    "general_workforce_question",
}

MANAGER_ALLOWED_INTENTS: set[AgentIntent] = {
    "productivity_analysis",
    "collaboration_analysis",
    "wellbeing_analysis",
    "task_assignment_recommendation",
    "task_delay_analysis",
    "team_workload_analysis",
    "general_workforce_question",
}

ADMIN_ALLOWED_INTENTS: set[AgentIntent] = {
    "productivity_analysis",
    "collaboration_analysis",
    "wellbeing_analysis",
    "task_delay_analysis",
    "team_workload_analysis",
    "general_workforce_question",
}


def authorize_user_intent(
    principal: AuthenticatedPrincipal,
    intent: AgentIntent,
    target_team_id: str | None = None,
) -> AuthorizationDecision:
    """
    Validates user role permissions for requesting agent analyses.
    - Employee: Cannot request task assignments or organization-wide analyses.
    - Manager: Can request task assignments and analyses for managed teams.
    - Admin: Read-only organization-wide analyses; task assignment disabled by default.
    """
    if principal.role == "employee":
        if intent == "task_assignment_recommendation":
            return AuthorizationDecision(
                allowed=False,
                safe_reason_code="EMPLOYEE_TASK_ASSIGNMENT_FORBIDDEN",
                safe_message="Employees are not authorized to request task assignment recommendations",
            )
        if intent == "team_workload_analysis":
            return AuthorizationDecision(
                allowed=False,
                safe_reason_code="EMPLOYEE_TEAM_WORKLOAD_FORBIDDEN",
                safe_message="Employees are not authorized to request team-wide workload analyses",
            )
        if target_team_id and target_team_id != principal.assigned_team_id:
            return AuthorizationDecision(
                allowed=False,
                safe_reason_code="EMPLOYEE_CROSS_TEAM_FORBIDDEN",
                safe_message="Employees cannot request analyses for teams other than their assigned team",
            )
        if intent not in EMPLOYEE_ALLOWED_INTENTS:
            return AuthorizationDecision(
                allowed=False,
                safe_reason_code="ROLE_INTENT_FORBIDDEN",
                safe_message=f"Role 'employee' is not authorized to request intent '{intent}'",
            )

    elif principal.role == "manager":
        if target_team_id and target_team_id not in principal.managed_team_ids:
            return AuthorizationDecision(
                allowed=False,
                safe_reason_code="MANAGER_UNMANAGED_TEAM_FORBIDDEN",
                safe_message="Managers cannot request analyses for teams they do not manage",
            )
        if intent not in MANAGER_ALLOWED_INTENTS:
            return AuthorizationDecision(
                allowed=False,
                safe_reason_code="ROLE_INTENT_FORBIDDEN",
                safe_message=f"Role 'manager' is not authorized to request intent '{intent}'",
            )

    elif principal.role == "admin":
        if intent == "task_assignment_recommendation":
            return AuthorizationDecision(
                allowed=False,
                safe_reason_code="ADMIN_TASK_ASSIGNMENT_DISABLED",
                safe_message="Task assignment recommendations are disabled for Administrator role",
            )
        if intent not in ADMIN_ALLOWED_INTENTS:
            return AuthorizationDecision(
                allowed=False,
                safe_reason_code="ROLE_INTENT_FORBIDDEN",
                safe_message=f"Role 'admin' is not authorized to request intent '{intent}'",
            )

    return AuthorizationDecision(
        allowed=True,
        safe_reason_code="ROLE_INTENT_AUTHORIZED",
        safe_message="User intent authorized for current role",
    )


# =========================================================================
# 3. Team-Scope Policy (Defense-in-Depth)
# =========================================================================


def validate_evidence_team_scope(
    principal: AuthenticatedPrincipal,
    evidence_ref: EvidenceReference,
) -> AuthorizationDecision:
    """
    Validates evidence references against the authenticated principal's team scope.

    Security Note: This is defense-in-depth. Specialist data services MUST also
    re-fetch and filter records from MongoDB applying authoritative database RBAC filters.
    """
    # 1. Agent findings inherit caller authorization in the same correlation context
    if evidence_ref.source_type == "agent_finding":
        return AuthorizationDecision(
            allowed=True,
            safe_reason_code="AGENT_FINDING_SCOPE_AUTHORIZED",
            safe_message="Agent finding evidence scope authorized",
        )

    # 2. Evidence must have a verifiable team scope for team-bound resources
    ev_team_id = evidence_ref.team_id

    if principal.role == "employee":
        if not ev_team_id:
            return AuthorizationDecision(
                allowed=False,
                safe_reason_code="EVIDENCE_MISSING_TEAM_SCOPE",
                safe_message="Evidence lacks team scope and cannot be authorized for employee access",
            )
        if ev_team_id != principal.assigned_team_id:
            return AuthorizationDecision(
                allowed=False,
                safe_reason_code="EVIDENCE_TEAM_SCOPE_MISMATCH",
                safe_message="Evidence team does not match employee assigned team scope",
            )

    elif principal.role == "manager":
        if not ev_team_id:
            return AuthorizationDecision(
                allowed=False,
                safe_reason_code="EVIDENCE_MISSING_TEAM_SCOPE",
                safe_message="Evidence lacks team scope and cannot be authorized for manager access",
            )
        if ev_team_id not in principal.managed_team_ids:
            return AuthorizationDecision(
                allowed=False,
                safe_reason_code="UNMANAGED_TEAM_EVIDENCE_FORBIDDEN",
                safe_message="Evidence belongs to a team not managed by the authenticated manager",
            )

    elif principal.role == "admin":
        # Admin has organization-wide read scope, while source-specific exclusions remain enforced
        return AuthorizationDecision(
            allowed=True,
            safe_reason_code="ADMIN_ORGANIZATION_SCOPE_AUTHORIZED",
            safe_message="Administrator organization-wide read scope authorized",
        )

    return AuthorizationDecision(
        allowed=True,
        safe_reason_code="EVIDENCE_SCOPE_AUTHORIZED",
        safe_message="Evidence team scope authorized",
    )


# =========================================================================
# 4. Cross-Agent Dependency Policy
# =========================================================================

# Allowed direct communication flows: (sender -> recipient)
ALLOWED_DEPENDENCY_FLOWS: set[tuple[AgentName, AgentName]] = {
    # Coordinator dispatch to specialists
    ("coordinator", "productivity"),
    ("coordinator", "collaboration"),
    ("coordinator", "wellbeing"),
    ("coordinator", "task_assigning"),
    # Specialist returns to coordinator
    ("productivity", "coordinator"),
    ("collaboration", "coordinator"),
    ("wellbeing", "coordinator"),
    ("task_assigning", "coordinator"),
    # Allowlisted specialist-to-specialist dependency flows
    ("productivity", "task_assigning"),
    ("collaboration", "task_assigning"),
}


def validate_dependency_flow(
    sender: AgentName,
    recipient: AgentName,
    dependency_findings: list[AgentFinding] | None = None,
    expected_correlation_id: str | None = None,
) -> AuthorizationDecision:
    """
    Validates whether an A2A message or dependency finding flow is permitted.
    Strictly forbids Wellbeing findings from flowing into Task Assigning Agent.
    Strictly rejects agent impersonation.
    Strictly rejects dependency findings with a mismatched correlation_id if correlation information is represented.
    """
    if (sender, recipient) not in ALLOWED_DEPENDENCY_FLOWS:
        return AuthorizationDecision(
            allowed=False,
            safe_reason_code="DEPENDENCY_FLOW_FORBIDDEN",
            safe_message=f"Communication flow from '{sender}' to '{recipient}' is forbidden",
        )

    # Validate attached dependency findings
    if dependency_findings:
        for finding in dependency_findings:
            # 1. Reject Wellbeing findings flowing to Task Assigning
            if recipient == "task_assigning" and finding.agent == "wellbeing":
                return AuthorizationDecision(
                    allowed=False,
                    safe_reason_code="WELLBEING_TASK_ASSIGNMENT_FORBIDDEN",
                    safe_message="Wellbeing findings cannot be supplied as dependencies to Task Assigning Agent",
                )

            # 2. Reject agent impersonation: finding author must match sender (unless coordinator routing)
            if sender != "coordinator" and finding.agent != sender:
                return AuthorizationDecision(
                    allowed=False,
                    safe_reason_code="AGENT_IMPERSONATION_FORBIDDEN",
                    safe_message=f"Dependency finding agent '{finding.agent}' does not match sender '{sender}'",
                )

            # 3. Provenance hardening: reject missing or mismatched correlation ID
            if expected_correlation_id:
                if not finding.correlation_id:
                    return AuthorizationDecision(
                        allowed=False,
                        safe_reason_code="DEPENDENCY_CORRELATION_MISSING",
                        safe_message="Dependency finding is missing required correlation_id",
                    )
                if finding.correlation_id != expected_correlation_id:
                    return AuthorizationDecision(
                        allowed=False,
                        safe_reason_code="DEPENDENCY_CORRELATION_MISMATCH",
                        safe_message=(
                            f"Dependency finding correlation_id '{finding.correlation_id}' "
                            f"does not match expected correlation_id '{expected_correlation_id}'"
                        ),
                    )

    return AuthorizationDecision(
        allowed=True,
        safe_reason_code="DEPENDENCY_FLOW_AUTHORIZED",
        safe_message="Cross-agent dependency flow authorized",
    )


def validate_request_dependencies(
    request: AgentRequest,
) -> AuthorizationDecision:
    """
    Validates an incoming AgentRequest's dependency findings against the request's
    declared sender, recipient, and correlation_id.
    """
    return validate_dependency_flow(
        sender=request.sender,
        recipient=request.recipient,
        dependency_findings=request.dependency_findings,
        expected_correlation_id=request.correlation_id,
    )


# =========================================================================
# 5. Responsible AI Guardrails Policy
# =========================================================================

TASK_ASSIGNMENT_IS_RECOMMENDATION_ONLY: bool = True
AUTOMATIC_TASK_MUTATION_PROHIBITED: bool = True
HUMAN_CONFIRMATION_REQUIRED: bool = True
WELLBEING_INFLUENCED_ASSIGNMENT_PROHIBITED: bool = True
PROTECTED_ATTRIBUTES_PROHIBITED: bool = True
MEDICAL_DIAGNOSIS_PROHIBITED: bool = True
PUNITIVE_RANKING_PROHIBITED: bool = True


def validate_responsible_ai_guardrails(
    agent: AgentName,
    intent: AgentIntent,
    finding: AgentFinding | None = None,
    dependency_findings: list[AgentFinding] | None = None,
) -> AuthorizationDecision:
    """
    Enforces Responsible AI boundaries:
    - Task assignment recommendations are strictly advisory and require human confirmation.
    - Prohibits medical diagnoses, punitive employee rankings, and wellbeing-influenced assignments.
    - Requires evidence references or explicit limitations when evidence is insufficient.
    """
    # 1. Task Assigning Boundaries
    if agent == "task_assigning" or intent == "task_assignment_recommendation":
        if dependency_findings:
            for dep in dependency_findings:
                if dep.agent == "wellbeing":
                    return AuthorizationDecision(
                        allowed=False,
                        safe_reason_code="RESPONSIBLE_AI_WELLBEING_LEAKAGE",
                        safe_message="Responsible AI violation: Wellbeing data cannot influence task assignment",
                    )

        if finding:
            # Must be recommendation only, cannot contain automatic execution commands
            actions_text = " ".join(finding.recommended_actions).lower()
            if "auto-assign" in actions_text or "force assignment" in actions_text or "commit assignment" in actions_text:
                return AuthorizationDecision(
                    allowed=False,
                    safe_reason_code="RESPONSIBLE_AI_AUTO_MUTATION_FORBIDDEN",
                    safe_message="Responsible AI violation: Task assignment must be recommendation-only requiring human approval",
                )

            # Employment recommendations require evidence or declared limitations
            if not finding.evidence_refs and not finding.limitations:
                return AuthorizationDecision(
                    allowed=False,
                    safe_reason_code="RESPONSIBLE_AI_UNSUBSTANTIATED_RECOMMENDATION",
                    safe_message="Responsible AI violation: Recommendations require evidence references or explicit limitations",
                )

    # 2. Wellbeing Boundaries
    if agent == "wellbeing" or intent == "wellbeing_analysis":
        if finding:
            summary_lower = finding.summary.lower()
            diagnoses = ["diagnos", "clinical", "disorder", "depression", "anxiety disorder", "pathology"]
            if any(d in summary_lower for d in diagnoses):
                return AuthorizationDecision(
                    allowed=False,
                    safe_reason_code="RESPONSIBLE_AI_MEDICAL_DIAGNOSIS_FORBIDDEN",
                    safe_message="Responsible AI violation: Medical diagnosis is strictly outside Wellbeing Agent scope",
                )

            punitive_terms = ["punish", "terminate employee", "demote", "worst employee", "fire employee"]
            if any(p in summary_lower for p in punitive_terms):
                return AuthorizationDecision(
                    allowed=False,
                    safe_reason_code="RESPONSIBLE_AI_PUNITIVE_RANKING_FORBIDDEN",
                    safe_message="Responsible AI violation: Punitive rankings and actions are prohibited",
                )

    return AuthorizationDecision(
        allowed=True,
        safe_reason_code="RESPONSIBLE_AI_GUARDRAILS_PASSED",
        safe_message="Responsible AI guardrails validated successfully",
    )
