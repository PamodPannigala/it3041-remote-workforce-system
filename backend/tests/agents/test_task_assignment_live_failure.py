"""Assignment regressions through the real API, coordinator, tools and validator.

Database records and provider responses are controlled at their boundaries. The
mobile-task fixture copies the evidence shape observed in the read-only live
diagnosis, with synthetic identities and dates instead of production records.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from bson import ObjectId
import pytest

from backend.app.main import app
from backend.app.modules.agents import task_assignment
from backend.app.modules.agents.llm_gateway import LLMResponseValidationError, LLMUnavailableError
from backend.app.modules.agents.router import get_agent_coordinator
from backend.app.modules.agents.task_assignment import TaskAssignmentFindingOutput
from backend.tests.agents.test_agent_api import create_user
from backend.tests.agents.test_coordinator_corrections import production_case


QUESTION = (
    "Recommend up to 3 eligible candidates for the selected task. Explain "
    "required-skill coverage, current workload, overdue risk, capacity "
    "limitations, and the manager decision required."
)


@pytest.fixture
def assignment_case(test_setup, production_case, monkeypatch):
    client, _ = test_setup
    db, gateway, coordinator, _, team, _, task_id, token = production_case
    task = next(t for t in db["tasks"].docs if t["_id"] == task_id)
    task.update(title="Mobile APP development", status="todo", priority="medium",
                assigned_to=None, required_skills=["ReactNative"], blockers=[])
    candidates = []
    now = datetime.now(timezone.utc)
    for index, skills in enumerate((["docker", "Angular", "Nodejs"], ["PowerBI"],
                                    ["Python", "FastAPI", "React"]), 1):
        user = create_user(db, email=f"fixture{index}@example.com", name=f"Candidate {index}",
                           role="employee", team_id=team["_id"])
        profile = {"_id": ObjectId(), "user_id": user["_id"], "skills": skills,
                   "weekly_capacity_hours": 40.0, "availability_status": "available"}
        db["employee_profiles"].docs.append(profile)
        candidates.append((user, profile))
        if index != 2:
            db["tasks"].docs.append({
                "_id": ObjectId(), "team_id": team["_id"], "assigned_to": user["_id"],
                "title": f"Existing commitment {index}", "status": "in_progress", "blockers": [],
                "due_date": now + timedelta(days=2) if index == 1 else now - timedelta(days=2),
            })
    validation_calls = []
    original = task_assignment.validate_task_assignment_grounding
    def observe(output, source):
        result = original(output, source)
        validation_calls.append((output, source, result))
        return result
    monkeypatch.setattr(task_assignment, "validate_task_assignment_grounding", observe)
    app.state.database = db
    app.dependency_overrides[get_agent_coordinator] = lambda: coordinator
    def execute():
        return client.post("/agents/execute", headers={"Authorization": f"Bearer {token}"}, json={
            "question": QUESTION, "target_team_id": str(team["_id"]), "target_task_id": str(task_id),
        })
    yield db, gateway, task, candidates, execute, validation_calls
    app.dependency_overrides.pop(get_agent_coordinator, None)


def provider_candidate(user, **changes):
    values = dict(candidate_id=str(user["_id"]), candidate_name=user["name"],
                  matched_skills=[], missing_skills=["ReactNative"],
                  rationale="Candidate lacks the mandatory skill.", confidence=0.0)
    values.update(changes)
    return values


def inject(case, recommendations, **changes):
    _, gateway, *_ = case
    values = dict(summary="Provider candidate explanation.", confidence=0.99,
                  candidate_recommendations=recommendations)
    values.update(changes)
    gateway.default_responses[TaskAssignmentFindingOutput] = TaskAssignmentFindingOutput(**values)


def completed(case):
    response = case[4]()
    assert response.status_code == 200, response.json()
    data = response.json()
    assert data["status"] == "completed"
    assert data["detected_intent"] == "task_assignment_recommendation"
    assert data["routing_confidence"] == 0.95
    assert data["consulted_specialists"] == ["task_assigning"]
    assert data["safe_error_message"] is None
    assert data["errors"] == []
    assert data["task_assignment_details"]["human_decision_required"] is True
    assert len(data["findings"]) == 1
    return data


def test_demonstrated_reactnative_task_returns_completed_no_eligible_result(assignment_case):
    _, gateway, _, candidates, _, calls = assignment_case
    inject(assignment_case, [provider_candidate(user) for user, _ in candidates])
    data = completed(assignment_case)
    assert len(calls) == 1
    assert calls[0][1] == []
    assert calls[0][2] == (False, "LLM returned 3 candidates, exceeding deterministic candidate pool (0)")
    details = data["task_assignment_details"]
    assert details["task_title"] == "Mobile APP development"
    assert details["required_skills"] == ["ReactNative"]
    assert details["current_assignee"] is None
    assert details["requested_candidate_count"] == details["evaluated_candidate_count"] == 3
    assert details["eligible_candidate_count"] == 0
    assert details["candidate_recommendations"] == []
    assert [c["missing_required_skills"] for c in details["other_evaluated_candidates"]] == [["ReactNative"]] * 3
    assert data["confidence"] == data["findings"][0]["confidence"] == 0.30
    assert "no supported recommendation" in data["summary"].lower()
    assert "ranked eligible candidates" not in " ".join(data["recommended_actions"]).lower()
    assert any(c["response_model"] == TaskAssignmentFindingOutput for c in gateway.calls)


@pytest.mark.parametrize("mismatch", ["name", "skills", "confidence", "ordering", "count"])
def test_grounding_mismatch_preserves_valid_deterministic_candidate_evidence(assignment_case, mismatch):
    _, _, task, candidates, _, calls = assignment_case
    task["required_skills"] = ["React", "FastAPI"]
    eligible, _ = candidates[2]
    rec = provider_candidate(eligible, matched_skills=["React", "FastAPI"], missing_skills=[], confidence=0.5)
    if mismatch == "name": rec["candidate_name"] = "Invented identity"
    if mismatch == "skills": rec["matched_skills"] = ["Angular"]
    if mismatch == "confidence": rec["confidence"] = 0.99
    if mismatch == "ordering": rec["candidate_id"] = str(candidates[0][0]["_id"])
    recs = [rec, provider_candidate(candidates[0][0])] if mismatch == "count" else [rec]
    inject(assignment_case, recs)
    data = completed(assignment_case)
    assert calls[0][2][0] is False
    assert [c.candidate_id for c in calls[0][1]] == [str(eligible["_id"])]
    card = data["task_assignment_details"]["candidate_recommendations"][0]
    assert card["candidate_name"] == eligible["name"]
    assert card["rank"] == 1
    assert set(card["matched_skills"]) == {"React", "FastAPI"}
    assert card["active_task_count"] == card["overdue_task_count"] == 1
    assert card["suitability_score"] == 0.91
    assert data["confidence"] == 0.95


@pytest.mark.parametrize("requirements", [[], None, "ReactNative"])
def test_zero_required_skills_returns_conservative_completed_assignment(assignment_case, requirements):
    _, _, task, candidates, *_ = assignment_case
    task["required_skills"] = requirements
    inject(assignment_case, [provider_candidate(candidates[2][0], matched_skills=["React"], missing_skills=[])])
    data = completed(assignment_case)
    assert data["confidence"] == 0.30
    assert data["task_assignment_details"]["required_skills"] == []
    assert data["task_assignment_details"]["eligible_candidate_count"] == 0
    assert data["task_assignment_details"]["candidate_recommendations"] == []
    assert "define" in " ".join(data["recommended_actions"]).lower()
    assert "no supported recommendation" in data["summary"].lower()


def test_no_eligible_candidates_preserves_verified_missing_skills(assignment_case):
    inject(assignment_case, [])
    data = completed(assignment_case)
    rejected = data["task_assignment_details"]["other_evaluated_candidates"]
    assert len(rejected) == 3
    for candidate in rejected:
        assert candidate["eligibility_status"] == "not_eligible"
        assert candidate["required_skill_coverage"] == 0.0
        assert candidate["missing_required_skills"] == ["ReactNative"]
        assert "ReactNative" in candidate["reason"]
    assert data["confidence"] == 0.30


def test_incomplete_profile_and_capacity_evidence_retains_penalty(assignment_case):
    db, _, task, candidates, *_ = assignment_case
    task["required_skills"] = ["React"]
    candidates[2][1].pop("weekly_capacity_hours")
    db["employee_profiles"].docs.remove(candidates[0][1])
    candidates[1][1].pop("weekly_capacity_hours")
    inject(assignment_case, [provider_candidate(candidates[2][0], matched_skills=["React"], missing_skills=[], confidence=1.0)])
    data = completed(assignment_case)
    assert data["confidence"] == 0.48
    details = data["task_assignment_details"]
    assert details["eligible_candidate_count"] == 1
    card = details["candidate_recommendations"][0]
    assert card["weekly_capacity_hours"] is None
    assert card["recommendation_label"] == "capacity_review_required"
    assert card["suitability_score"] == 0.59
    assert any("unverified" in s.lower() for s in card["limitations"])
    assert len(details["other_evaluated_candidates"]) == 2


def test_current_assignee_is_preserved_without_ranking_boost(assignment_case):
    _, _, task, candidates, *_ = assignment_case
    task["required_skills"] = ["React"]
    task["assigned_to"] = candidates[2][0]["_id"]
    candidates[1][1]["skills"] = ["React"]
    inject(assignment_case, [provider_candidate(candidates[2][0], matched_skills=["React"], missing_skills=[])])
    data = completed(assignment_case)
    details = data["task_assignment_details"]
    assert details["current_assignee"] == candidates[2][0]["name"]
    assert [c["candidate_name"] for c in details["candidate_recommendations"]] == [candidates[1][0]["name"], candidates[2][0]["name"]]
    assert [c["suitability_score"] for c in details["candidate_recommendations"]] == [1.0, 0.87]
    assert details["candidate_recommendations"][1]["active_task_count"] == 2
    assert any("retain" in action for action in data["recommended_actions"])
    assert data["confidence"] == 0.95


def test_conflicting_llm_candidate_prose_uses_deterministic_fallback(assignment_case):
    _, _, task, candidates, _, calls = assignment_case
    task["required_skills"] = ["React", "FastAPI"]
    rec = provider_candidate(candidates[2][0], matched_skills=["React", "FastAPI"], missing_skills=[], confidence=0.5,
                             rationale="MAGIC_EXPERT has spare capacity and no overdue tasks.",
                             workload_observations=["No overdue tasks."], assignment_risks=["No risks."])
    inject(assignment_case, [rec], summary="MAGIC_EXPERT has no workload or overdue risk.",
           recommended_actions=["Select MAGIC_EXPERT based on exceptional unverified credentials."])
    data = completed(assignment_case)
    assert calls[0][2] == (True, None)  # Validator covers candidate fields, not prose.
    assert "MAGIC_EXPERT" not in str(data)
    card = data["task_assignment_details"]["candidate_recommendations"][0]
    assert card["overdue_task_count"] == 1
    assert card["recommendation_label"] == "capacity_review_required"


def test_assignment_public_output_hides_internal_grounding_errors(assignment_case):
    _, _, _, candidates, *_ = assignment_case
    inject(assignment_case, [provider_candidate(candidates[0][0])],
           summary="Task assignment output did not match verified candidate evidence. OUTPUT_GROUNDING_ERROR")
    data = completed(assignment_case)
    for internal in ("OUTPUT_GROUNDING_ERROR", "did not match verified candidate evidence", "exceeding deterministic candidate pool", "candidate_id"):
        assert internal not in str(data)
    for user, _ in candidates:
        assert str(user["_id"]) not in str(data)
        assert user["email"] not in str(data)


def test_post_routing_assignment_failure_preserves_intent_metadata(assignment_case):
    _, gateway, *_ = assignment_case
    gateway.generate_structured = AsyncMock(side_effect=LLMUnavailableError("Private provider diagnostic"))
    response = assignment_case[4]()
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "failed"
    assert data["detected_intent"] == "task_assignment_recommendation"
    assert data["routing_confidence"] == 0.95
    assert data["consulted_specialists"] == ["task_assigning"]
    assert data["confidence"] is None
    assert "Private provider diagnostic" not in str(data)
    assert "LLM_PROVIDER_ERROR" not in str(data)
    gateway.generate_structured.assert_awaited_once()


def test_assignment_schema_mismatch_preserves_valid_deterministic_evidence(assignment_case):
    _, gateway, task, _, _, calls = assignment_case
    task["required_skills"] = ["React", "FastAPI"]
    gateway.generate_structured = AsyncMock(side_effect=LLMResponseValidationError("PRIVATE_PROVIDER_SCHEMA_ERROR"))
    data = completed(assignment_case)
    assert data["confidence"] == 0.95
    card = data["task_assignment_details"]["candidate_recommendations"][0]
    assert card["suitability_score"] == 0.91
    assert card["active_task_count"] == card["overdue_task_count"] == 1
    assert "PRIVATE_PROVIDER_SCHEMA_ERROR" not in str(data)
    assert "validation" not in str(data).lower()
    assert len(calls) == 1
    gateway.generate_structured.assert_awaited_once()


def test_assignment_evidence_read_failure_preserves_routing_metadata(assignment_case):
    db, gateway, *_ = assignment_case
    db["employee_profiles"].find = MagicMock(side_effect=RuntimeError("PRIVATE_DATABASE_DIAGNOSTIC"))
    response = assignment_case[4]()
    assert response.status_code == 500
    data = response.json()
    assert data["detected_intent"] == "task_assignment_recommendation"
    assert data["routing_confidence"] == 0.95
    assert data["consulted_specialists"] == ["task_assigning"]
    assert data["confidence"] is None
    assert data["task_assignment_details"] is None
    assert "PRIVATE_DATABASE_DIAGNOSTIC" not in str(data)
    assert "DATABASE_ERROR" not in str(data)
    assert gateway.calls == []
    db["employee_profiles"].find.assert_called_once()


def test_complete_working_assignment_evidence_and_ranking_are_unchanged(assignment_case):
    _, _, task, candidates, *_ = assignment_case
    task.update(title="Web App Development", required_skills=["React", "FastAPI"])
    inject(assignment_case, [provider_candidate(candidates[2][0], matched_skills=[" React ", "fastapi"], missing_skills=[], confidence=0.91)])
    data = completed(assignment_case)
    assert assignment_case[5][0][2] == (True, None)
    assert data["confidence"] == 0.95
    card = data["task_assignment_details"]["candidate_recommendations"][0]
    assert card["suitability_score"] == 0.91
    assert card["rank"] == 1
    assert card["active_task_count"] == card["overdue_task_count"] == 1
    assert card["weekly_capacity_hours"] == 40.0
    assert data["task_assignment_details"]["requested_candidate_count"] == 3
