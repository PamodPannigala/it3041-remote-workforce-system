from datetime import datetime, timezone
import uuid
import pytest
from pydantic import ValidationError

from backend.app.modules.agents.protocol import (
    AgentFinding,
    AgentRequest,
    EvidenceReference,
)
from backend.app.modules.agents.security_policy import (
    AuthenticatedPrincipal,
    authorize_user_intent,
    validate_agent_capability,
    validate_dependency_flow,
    validate_evidence_team_scope,
    validate_request_dependencies,
    validate_responsible_ai_guardrails,
)


# =========================================================================
# 1. Trusted Principal Context Tests
# =========================================================================


def test_valid_employee_principal_context():
    emp = AuthenticatedPrincipal(
        user_id="emp-001",
        role="employee",
        assigned_team_id="team-alpha",
    )
    assert emp.user_id == "emp-001"
    assert emp.role == "employee"
    assert emp.assigned_team_id == "team-alpha"
    assert emp.managed_team_ids == []
    assert emp.resolved_at.tzinfo == timezone.utc
    assert emp.is_admin_org_wide_read is False


def test_valid_manager_principal_context():
    mgr = AuthenticatedPrincipal(
        user_id="mgr-002",
        role="manager",
        assigned_team_id="team-alpha",
        managed_team_ids=["team-alpha", "team-beta"],
    )
    assert mgr.role == "manager"
    assert len(mgr.managed_team_ids) == 2
    assert mgr.is_admin_org_wide_read is False


def test_valid_admin_principal_context():
    admin = AuthenticatedPrincipal(
        user_id="admin-003",
        role="admin",
    )
    assert admin.role == "admin"
    assert admin.assigned_team_id is None
    assert admin.is_admin_org_wide_read is True


def test_admin_is_admin_org_wide_read_property():
    emp = AuthenticatedPrincipal(user_id="e1", role="employee")
    mgr = AuthenticatedPrincipal(user_id="m1", role="manager", managed_team_ids=["t1"])
    admin = AuthenticatedPrincipal(user_id="a1", role="admin")

    assert emp.is_admin_org_wide_read is False
    assert mgr.is_admin_org_wide_read is False
    assert admin.is_admin_org_wide_read is True


def test_employee_cannot_carry_managed_teams():
    with pytest.raises(ValidationError) as exc:
        AuthenticatedPrincipal(
            user_id="emp-001",
            role="employee",
            assigned_team_id="team-alpha",
            managed_team_ids=["team-rogue"],
        )
    assert "Employee principal cannot carry managed_team_ids" in str(exc.value)


def test_manager_managed_teams_deduplicated():
    mgr = AuthenticatedPrincipal(
        user_id="mgr-002",
        role="manager",
        managed_team_ids=["team-alpha", "team-beta", "team-alpha", "team-beta"],
    )
    assert mgr.managed_team_ids == ["team-alpha", "team-beta"]


def test_principal_unknown_fields_rejected():
    with pytest.raises(ValidationError):
        AuthenticatedPrincipal(
            user_id="emp-001",
            role="employee",
            injected_admin_grant=True,
        )


def test_principal_invalid_role_rejected():
    with pytest.raises(ValidationError):
        AuthenticatedPrincipal(
            user_id="emp-001",
            role="unauthorized_role",
        )


def test_principal_string_length_bounds():
    with pytest.raises(ValidationError):
        AuthenticatedPrincipal(
            user_id="x" * 65,
            role="employee",
        )

    with pytest.raises(ValidationError):
        AuthenticatedPrincipal(
            user_id="emp-1",
            role="employee",
            assigned_team_id="x" * 65,
        )


# =========================================================================
# 2. Agent Capability Matrix Tests
# =========================================================================


def test_coordinator_capability_allows_all_intents():
    for intent in (
        "productivity_analysis",
        "collaboration_analysis",
        "wellbeing_analysis",
        "task_assignment_recommendation",
        "task_delay_analysis",
        "team_workload_analysis",
        "general_workforce_question",
    ):
        dec = validate_agent_capability("coordinator", intent)
        assert dec.allowed is True


def test_productivity_capability_intents_and_evidence():
    assert validate_agent_capability("productivity", "productivity_analysis").allowed is True
    assert validate_agent_capability("productivity", "task_delay_analysis").allowed is True
    assert validate_agent_capability("productivity", "team_workload_analysis").allowed is True
    assert validate_agent_capability("productivity", "task_assignment_recommendation").allowed is False

    # Evidence sources
    assert validate_agent_capability("productivity", "productivity_analysis", ["task", "agent_finding"]).allowed is True
    assert validate_agent_capability("productivity", "productivity_analysis", ["pulse_summary"]).allowed is False


def test_collaboration_capability_intents_and_evidence():
    assert validate_agent_capability("collaboration", "collaboration_analysis").allowed is True
    assert validate_agent_capability("collaboration", "task_delay_analysis").allowed is True
    assert validate_agent_capability("collaboration", "wellbeing_analysis").allowed is False

    # Evidence sources
    assert validate_agent_capability("collaboration", "collaboration_analysis", ["task", "collaboration_message"]).allowed is True
    assert validate_agent_capability("collaboration", "collaboration_analysis", ["pulse_summary"]).allowed is False


def test_wellbeing_capability_intents_and_evidence():
    assert validate_agent_capability("wellbeing", "wellbeing_analysis").allowed is True
    assert validate_agent_capability("wellbeing", "team_workload_analysis").allowed is True
    assert validate_agent_capability("wellbeing", "task_assignment_recommendation").allowed is False

    # Evidence sources
    assert validate_agent_capability("wellbeing", "wellbeing_analysis", ["pulse_summary", "agent_finding"]).allowed is True
    assert validate_agent_capability("wellbeing", "wellbeing_analysis", ["collaboration_message"]).allowed is False
    assert validate_agent_capability("wellbeing", "wellbeing_analysis", ["task"]).allowed is False


def test_task_assigning_capability_intents_and_evidence():
    assert validate_agent_capability("task_assigning", "task_assignment_recommendation").allowed is True
    assert validate_agent_capability("task_assigning", "productivity_analysis").allowed is False

    # Evidence sources
    assert validate_agent_capability("task_assigning", "task_assignment_recommendation", ["task", "employee_profile", "agent_finding"]).allowed is True


def test_unsupported_intent_rejected():
    dec = validate_agent_capability("productivity", "general_workforce_question")
    assert dec.allowed is False
    assert dec.safe_reason_code == "AGENT_INTENT_NOT_ALLOWED"


def test_unsupported_evidence_source_rejected():
    dec = validate_agent_capability("productivity", "productivity_analysis", ["employee_profile"])
    assert dec.allowed is False
    assert dec.safe_reason_code == "AGENT_EVIDENCE_SOURCE_NOT_ALLOWED"


def test_task_assigning_strictly_rejects_pulse_summary():
    dec = validate_agent_capability("task_assigning", "task_assignment_recommendation", ["pulse_summary"])
    assert dec.allowed is False
    assert dec.safe_reason_code == "AGENT_EVIDENCE_SOURCE_NOT_ALLOWED"


def test_task_assigning_strictly_rejects_collaboration_message():
    dec = validate_agent_capability("task_assigning", "task_assignment_recommendation", ["collaboration_message"])
    assert dec.allowed is False
    assert dec.safe_reason_code == "AGENT_EVIDENCE_SOURCE_NOT_ALLOWED"


# =========================================================================
# 3. Role Policy Tests
# =========================================================================


def test_employee_role_allowed_intents():
    emp = AuthenticatedPrincipal(user_id="emp-1", role="employee", assigned_team_id="team-alpha")
    assert authorize_user_intent(emp, "productivity_analysis", "team-alpha").allowed is True
    assert authorize_user_intent(emp, "collaboration_analysis", "team-alpha").allowed is True
    assert authorize_user_intent(emp, "wellbeing_analysis", "team-alpha").allowed is True


def test_employee_task_assignment_denied():
    emp = AuthenticatedPrincipal(user_id="emp-1", role="employee", assigned_team_id="team-alpha")
    dec = authorize_user_intent(emp, "task_assignment_recommendation")
    assert dec.allowed is False
    assert dec.safe_reason_code == "EMPLOYEE_TASK_ASSIGNMENT_FORBIDDEN"


def test_employee_team_workload_denied():
    emp = AuthenticatedPrincipal(user_id="emp-1", role="employee", assigned_team_id="team-alpha")
    dec = authorize_user_intent(emp, "team_workload_analysis")
    assert dec.allowed is False
    assert dec.safe_reason_code == "EMPLOYEE_TEAM_WORKLOAD_FORBIDDEN"


def test_employee_cross_team_denied():
    emp = AuthenticatedPrincipal(user_id="emp-1", role="employee", assigned_team_id="team-alpha")
    dec = authorize_user_intent(emp, "productivity_analysis", target_team_id="team-beta")
    assert dec.allowed is False
    assert dec.safe_reason_code == "EMPLOYEE_CROSS_TEAM_FORBIDDEN"


def test_manager_role_allowed_intents():
    mgr = AuthenticatedPrincipal(user_id="mgr-1", role="manager", managed_team_ids=["team-alpha"])
    assert authorize_user_intent(mgr, "productivity_analysis", "team-alpha").allowed is True
    assert authorize_user_intent(mgr, "collaboration_analysis", "team-alpha").allowed is True
    assert authorize_user_intent(mgr, "wellbeing_analysis", "team-alpha").allowed is True
    assert authorize_user_intent(mgr, "team_workload_analysis", "team-alpha").allowed is True


def test_manager_task_assignment_allowed_for_managed_teams():
    mgr = AuthenticatedPrincipal(user_id="mgr-1", role="manager", managed_team_ids=["team-alpha"])
    dec = authorize_user_intent(mgr, "task_assignment_recommendation", target_team_id="team-alpha")
    assert dec.allowed is True
    assert dec.safe_reason_code == "ROLE_INTENT_AUTHORIZED"


def test_manager_unmanaged_team_denied():
    mgr = AuthenticatedPrincipal(user_id="mgr-1", role="manager", managed_team_ids=["team-alpha"])
    dec = authorize_user_intent(mgr, "task_assignment_recommendation", target_team_id="team-beta")
    assert dec.allowed is False
    assert dec.safe_reason_code == "MANAGER_UNMANAGED_TEAM_FORBIDDEN"


def test_admin_role_read_only_allowed():
    admin = AuthenticatedPrincipal(user_id="admin-1", role="admin")
    assert authorize_user_intent(admin, "productivity_analysis").allowed is True
    assert authorize_user_intent(admin, "collaboration_analysis").allowed is True
    assert authorize_user_intent(admin, "wellbeing_analysis").allowed is True


def test_admin_task_assignment_denied_by_default():
    admin = AuthenticatedPrincipal(user_id="admin-1", role="admin")
    dec = authorize_user_intent(admin, "task_assignment_recommendation")
    assert dec.allowed is False
    assert dec.safe_reason_code == "ADMIN_TASK_ASSIGNMENT_DISABLED"


def test_safe_reason_codes_returned_on_authorization_decisions():
    admin = AuthenticatedPrincipal(user_id="admin-1", role="admin")
    dec = authorize_user_intent(admin, "task_assignment_recommendation")
    assert dec.safe_reason_code == "ADMIN_TASK_ASSIGNMENT_DISABLED"
    assert len(dec.safe_message) > 0
    assert "admin-1" not in dec.safe_message


# =========================================================================
# 4. Team-Scope Policy Tests
# =========================================================================


def test_employee_team_scope_own_team_allowed():
    emp = AuthenticatedPrincipal(user_id="emp-1", role="employee", assigned_team_id="team-alpha")
    ev = EvidenceReference(source_type="task", record_id="t1", team_id="team-alpha")
    assert validate_evidence_team_scope(emp, ev).allowed is True


def test_employee_team_scope_foreign_team_denied():
    emp = AuthenticatedPrincipal(user_id="emp-1", role="employee", assigned_team_id="team-alpha")
    ev = EvidenceReference(source_type="task", record_id="t2", team_id="team-beta")
    dec = validate_evidence_team_scope(emp, ev)
    assert dec.allowed is False
    assert dec.safe_reason_code == "EVIDENCE_TEAM_SCOPE_MISMATCH"


def test_manager_team_scope_managed_teams_allowed():
    mgr = AuthenticatedPrincipal(user_id="mgr-1", role="manager", managed_team_ids=["team-alpha", "team-beta"])
    ev1 = EvidenceReference(source_type="task", record_id="t1", team_id="team-alpha")
    ev2 = EvidenceReference(source_type="task", record_id="t2", team_id="team-beta")
    assert validate_evidence_team_scope(mgr, ev1).allowed is True
    assert validate_evidence_team_scope(mgr, ev2).allowed is True


def test_manager_team_scope_unmanaged_teams_denied():
    mgr = AuthenticatedPrincipal(user_id="mgr-1", role="manager", managed_team_ids=["team-alpha"])
    ev = EvidenceReference(source_type="task", record_id="t3", team_id="team-gamma")
    dec = validate_evidence_team_scope(mgr, ev)
    assert dec.allowed is False
    assert dec.safe_reason_code == "UNMANAGED_TEAM_EVIDENCE_FORBIDDEN"


def test_missing_team_scope_does_not_grant_access():
    emp = AuthenticatedPrincipal(user_id="emp-1", role="employee", assigned_team_id="team-alpha")
    mgr = AuthenticatedPrincipal(user_id="mgr-1", role="manager", managed_team_ids=["team-alpha"])
    ev = EvidenceReference(source_type="task", record_id="t4", team_id=None)

    assert validate_evidence_team_scope(emp, ev).allowed is False
    assert validate_evidence_team_scope(mgr, ev).allowed is False


def test_admin_organization_read_scope_authorized():
    admin = AuthenticatedPrincipal(user_id="admin-1", role="admin")
    ev = EvidenceReference(source_type="task", record_id="t5", team_id="team-gamma")
    assert validate_evidence_team_scope(admin, ev).allowed is True


def test_agent_finding_inherits_scope():
    emp = AuthenticatedPrincipal(user_id="emp-1", role="employee", assigned_team_id="team-alpha")
    ev = EvidenceReference(source_type="agent_finding", record_id="finding-1", team_id=None)
    assert validate_evidence_team_scope(emp, ev).allowed is True


# =========================================================================
# 5. Cross-Agent Dependency Flow Tests
# =========================================================================


def test_approved_cross_agent_dependency_flows():
    assert validate_dependency_flow("coordinator", "productivity").allowed is True
    assert validate_dependency_flow("coordinator", "collaboration").allowed is True
    assert validate_dependency_flow("coordinator", "wellbeing").allowed is True
    assert validate_dependency_flow("coordinator", "task_assigning").allowed is True
    assert validate_dependency_flow("productivity", "task_assigning").allowed is True
    assert validate_dependency_flow("collaboration", "task_assigning").allowed is True
    assert validate_dependency_flow("productivity", "coordinator").allowed is True
    assert validate_dependency_flow("collaboration", "coordinator").allowed is True
    assert validate_dependency_flow("wellbeing", "coordinator").allowed is True
    assert validate_dependency_flow("task_assigning", "coordinator").allowed is True


def test_forbidden_wellbeing_to_task_assigning_flow():
    dec = validate_dependency_flow("wellbeing", "task_assigning")
    assert dec.allowed is False
    assert dec.safe_reason_code == "DEPENDENCY_FLOW_FORBIDDEN"


def test_forbidden_task_assigning_to_wellbeing_flow():
    dec = validate_dependency_flow("task_assigning", "wellbeing")
    assert dec.allowed is False
    assert dec.safe_reason_code == "DEPENDENCY_FLOW_FORBIDDEN"


def test_arbitrary_unapproved_dependency_flows_rejected():
    assert validate_dependency_flow("productivity", "wellbeing").allowed is False
    assert validate_dependency_flow("collaboration", "wellbeing").allowed is False
    assert validate_dependency_flow("wellbeing", "productivity").allowed is False


def test_agent_impersonation_in_dependency_findings_rejected():
    prod_finding = AgentFinding(
        agent="productivity",
        summary="Productivity summary",
        confidence=0.9,
    )
    dec = validate_dependency_flow("collaboration", "task_assigning", dependency_findings=[prod_finding])
    assert dec.allowed is False
    assert dec.safe_reason_code == "AGENT_IMPERSONATION_FORBIDDEN"


def test_dependency_flow_missing_correlation_id_rejected():
    cid_req = str(uuid.uuid4())
    finding = AgentFinding(
        agent="productivity",
        summary="Productivity summary without correlation_id",
        correlation_id=None,
        confidence=0.9,
    )
    dec = validate_dependency_flow(
        sender="productivity",
        recipient="task_assigning",
        dependency_findings=[finding],
        expected_correlation_id=cid_req,
    )
    assert dec.allowed is False
    assert dec.safe_reason_code == "DEPENDENCY_CORRELATION_MISSING"


def test_dependency_flow_correlation_id_mismatch_rejected():
    cid_req = str(uuid.uuid4())
    cid_finding = str(uuid.uuid4())
    finding = AgentFinding(
        agent="productivity",
        summary="Productivity summary with mismatched correlation_id",
        correlation_id=cid_finding,
        confidence=0.9,
    )
    dec = validate_dependency_flow(
        sender="productivity",
        recipient="task_assigning",
        dependency_findings=[finding],
        expected_correlation_id=cid_req,
    )
    assert dec.allowed is False
    assert dec.safe_reason_code == "DEPENDENCY_CORRELATION_MISMATCH"


def test_dependency_flow_multiple_matching_findings_accepted():
    cid = str(uuid.uuid4())
    finding1 = AgentFinding(
        agent="productivity",
        summary="Productivity finding 1",
        correlation_id=cid,
        confidence=0.9,
    )
    finding2 = AgentFinding(
        agent="collaboration",
        summary="Collaboration finding 2",
        correlation_id=cid,
        confidence=0.85,
    )
    dec = validate_dependency_flow(
        sender="coordinator",
        recipient="task_assigning",
        dependency_findings=[finding1, finding2],
        expected_correlation_id=cid,
    )
    assert dec.allowed is True
    assert dec.safe_reason_code == "DEPENDENCY_FLOW_AUTHORIZED"


def test_dependency_flow_one_mismatch_among_multiple_findings_rejected():
    cid = str(uuid.uuid4())
    finding1 = AgentFinding(
        agent="productivity",
        summary="Productivity finding 1",
        correlation_id=cid,
        confidence=0.9,
    )
    finding_rogue = AgentFinding(
        agent="collaboration",
        summary="Collaboration finding with rogue correlation_id",
        correlation_id=str(uuid.uuid4()),
        confidence=0.85,
    )
    dec = validate_dependency_flow(
        sender="coordinator",
        recipient="task_assigning",
        dependency_findings=[finding1, finding_rogue],
        expected_correlation_id=cid,
    )
    assert dec.allowed is False
    assert dec.safe_reason_code == "DEPENDENCY_CORRELATION_MISMATCH"


def test_dependency_flow_no_dependency_findings_authorized():
    assert validate_dependency_flow("coordinator", "task_assigning", dependency_findings=[]).allowed is True
    assert validate_dependency_flow("coordinator", "task_assigning", dependency_findings=None).allowed is True


def test_validate_request_dependencies_helper():
    cid = str(uuid.uuid4())
    finding_matching = AgentFinding(
        agent="productivity",
        summary="Productivity summary",
        correlation_id=cid,
        confidence=0.9,
    )
    req_valid = AgentRequest(
        correlation_id=cid,
        sender="productivity",
        recipient="task_assigning",
        message_type="dependency_request",
        intent="task_assignment_recommendation",
        authenticated_user_id="u1",
        question="Find assignee",
        dependency_findings=[finding_matching],
    )
    assert validate_request_dependencies(req_valid).allowed is True


# =========================================================================
# 6. Responsible AI Policy Tests
# =========================================================================


def test_responsible_ai_task_assignment_recommendation_only():
    finding_rec = AgentFinding(
        agent="task_assigning",
        summary="Recommended assignee: user-1",
        confidence=0.9,
        evidence_refs=[EvidenceReference(source_type="task", record_id="t1")],
        recommended_actions=["Review recommendation with manager"],
    )
    dec = validate_responsible_ai_guardrails("task_assigning", "task_assignment_recommendation", finding=finding_rec)
    assert dec.allowed is True


def test_responsible_ai_automatic_mutation_prohibited():
    finding_auto = AgentFinding(
        agent="task_assigning",
        summary="Recommended assignee user-1",
        confidence=0.9,
        recommended_actions=["Auto-assign task 101 to user-1 immediately"],
    )
    dec = validate_responsible_ai_guardrails("task_assigning", "task_assignment_recommendation", finding=finding_auto)
    assert dec.allowed is False
    assert dec.safe_reason_code == "RESPONSIBLE_AI_AUTO_MUTATION_FORBIDDEN"


def test_responsible_ai_wellbeing_influence_on_assignment_prohibited():
    wb_finding = AgentFinding(
        agent="wellbeing",
        summary="Employee is burned out",
        confidence=0.9,
    )
    dec = validate_responsible_ai_guardrails(
        "task_assigning",
        "task_assignment_recommendation",
        dependency_findings=[wb_finding],
    )
    assert dec.allowed is False
    assert dec.safe_reason_code == "RESPONSIBLE_AI_WELLBEING_LEAKAGE"


def test_responsible_ai_medical_diagnosis_prohibited():
    finding_diag = AgentFinding(
        agent="wellbeing",
        summary="Employee shows symptoms of clinical depression and disorder",
        confidence=0.7,
    )
    dec = validate_responsible_ai_guardrails("wellbeing", "wellbeing_analysis", finding=finding_diag)
    assert dec.allowed is False
    assert dec.safe_reason_code == "RESPONSIBLE_AI_MEDICAL_DIAGNOSIS_FORBIDDEN"


def test_responsible_ai_punitive_ranking_prohibited():
    finding_punitive = AgentFinding(
        agent="wellbeing",
        summary="Identify worst employee to terminate employee",
        confidence=0.8,
    )
    dec = validate_responsible_ai_guardrails("wellbeing", "wellbeing_analysis", finding=finding_punitive)
    assert dec.allowed is False
    assert dec.safe_reason_code == "RESPONSIBLE_AI_PUNITIVE_RANKING_FORBIDDEN"


def test_responsible_ai_unsubstantiated_recommendations_prohibited():
    finding_empty = AgentFinding(
        agent="task_assigning",
        summary="Recommended assignee user-1",
        confidence=0.9,
        evidence_refs=[],
        limitations=[],
    )
    dec = validate_responsible_ai_guardrails("task_assigning", "task_assignment_recommendation", finding=finding_empty)
    assert dec.allowed is False
    assert dec.safe_reason_code == "RESPONSIBLE_AI_UNSUBSTANTIATED_RECOMMENDATION"


def test_responsible_ai_insufficient_evidence_with_limitations_allowed():
    finding_limited = AgentFinding(
        agent="task_assigning",
        summary="Insufficient evidence to make assignment recommendation",
        confidence=0.2,
        evidence_refs=[],
        limitations=["No employee profiles with required skill found"],
    )
    dec = validate_responsible_ai_guardrails("task_assigning", "task_assignment_recommendation", finding=finding_limited)
    assert dec.allowed is True
