"""Live-report reproductions through the production FastAPI/coordinator/runtime path."""
import re

import pytest

from backend.app.modules.agents.collaboration_agent import CollaborationFindingOutput
from backend.app.modules.agents.productivity import ProductivityFindingOutput
from backend.tests.agents.test_manual_corrections import (
    PROTECTIVE_QUERY, execute_api, production_case, seed_manual_evidence, seed_candidate,
)

TASK_DELAY = "Why is this task delayed? Separate verified observations, evidence gaps, and hypotheses for investigation."
TEAM_DELAY = "Why are team tasks delayed? Review task progress and verified collaboration blocker evidence."
WORKLOAD = "Review overdue tasks and anonymous well-being for team workload over four weeks. Distinguish delivery strain from verified capacity evidence."
WORKFORCE = "Give a general workforce overview over four weeks covering productivity, collaboration, and anonymous well-being."

MALFORMED = [
    "8 hours it is a planning estimate",
    "due date overdue status",
    "were not retrieved current task states",
    "where applicable Productivity",
    "spans team tasks it is not all attributed",
    "reported experience they do not establish",
    "has in the past, but",
    "Anonymous single-week snapshot, for",
]


@pytest.fixture
def live_case(production_case):
    seed_manual_evidence(production_case)
    db, gateway, _, _, team, *_ = production_case
    for message in db["collaboration_messages"].docs:
        if message["team_id"] == team["_id"]:
            message["content"] = "What is the development task's current status? Can we arrange a coordination meeting?"
    gateway.default_responses[CollaborationFindingOutput] = CollaborationFindingOutput(
        summary=("Recent messages included requests for coordination meetings. "
                 "Recent inquiries confirming the completion status of the development work. "
                 "The resolved API access dependency caused the delay. The team has in the past, but..."),
        communication_observations=["Recent messages included requests for coordination meetings."],
        recommended_actions=[
            "Verify that the resolved API access dependency is functioning as expected in the production environment.",
            "Review the API-access blocker resolution.",
            "Schedule a coordination meeting to clarify status inquiries.",
            "Schedule a coordination meeting to clarify status inquiries!",
        ],
        limitations=[
            "Task-linked collaboration-message evidence is unavailable; no trustworthy messages explicitly linked to the selected task were available.",
            "Task-linked collaboration-message evidence is unavailable no trustworthy messages explicitly linked to the selected task were available.",
            "The development task is complete.",
        ], confidence=0.99,
    )
    return production_case


def response_for(execute_api, question=TASK_DELAY, task=True):
    response = execute_api(question, task_scope=task)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    return data


def items(data, field):
    return [*data[field], *(item for finding in data["findings"] for item in finding[field])]


def visible(data):
    return " ".join([data["summary"], *items(data, "limitations"),
                     *items(data, "recommended_actions"), *(f["summary"] for f in data["findings"])])


def key(text):
    return " ".join(re.findall(r"\w+", text.casefold()))


def assert_clean(data):
    text = visible(data)
    for malformed in MALFORMED:
        assert malformed not in text
    assert "API access" not in text and "API-access" not in text
    assert "confirming the completion" not in text
    assert "..." not in text
    for owner in [data, *data["findings"]]:
        for field in ("limitations", "recommended_actions"):
            values = [key(value) for value in owner[field]]
            assert len(values) == len(set(values))
            assert all(value.endswith(".") for value in owner[field])
        assert owner["summary"].endswith(".")


def test_task_delay_estimate_sentence_is_grammatically_complete(execute_api, live_case):
    data = response_for(execute_api)
    assert "The recorded estimate is 8 hours. This is a planning estimate, not actual time spent." in data["summary"]
    assert data["confidence"] == 0.60


def test_missing_due_date_limitation_is_two_complete_sentences(execute_api, live_case):
    data = response_for(execute_api, TEAM_DELAY, task=False)
    assert "One task has no verified due date. Its overdue status cannot be established." in data["limitations"]
    assert "Web App Development has no due date" not in visible(data)


def test_productivity_snapshot_limitations_are_grammatically_complete(execute_api, live_case):
    data = response_for(execute_api)
    assert "Actual time-spent records and historical throughput were not retrieved. Current task states do not establish elapsed effort or delay causes." in data["limitations"]
    assert "The 4-week request limits task activity dates where applicable. Productivity is a current snapshot, not historical throughput over that window." in data["limitations"]


def test_team_collaboration_scope_limitation_is_grammatically_complete(execute_api, live_case):
    data = response_for(execute_api, TEAM_DELAY, task=False)
    assert "Team collaboration evidence spans multiple team tasks. It is not all attributed to any one task." in data["limitations"]


def test_wellbeing_scope_limitation_is_grammatically_complete(execute_api, live_case):
    data = response_for(execute_api, WORKLOAD, task=False)
    assert "Anonymous well-being ratings describe reported experience. They do not establish delivery capacity or individual performance." in data["limitations"]


def test_task_linked_message_limitation_is_canonical_and_not_duplicated(execute_api, live_case):
    data = response_for(execute_api)
    expected = "Task-linked collaboration-message evidence is unavailable. No trustworthy messages explicitly linked to the selected task were available."
    for owner in (data, next(f for f in data["findings"] if f["agent"] == "collaboration")):
        related = [lim for lim in owner["limitations"] if "collaboration-message evidence is unavailable" in lim]
        assert related == [expected]


@pytest.mark.parametrize("question,task", [(TASK_DELAY, True), (TEAM_DELAY, False), (WORKLOAD, False), (WORKFORCE, False)])
def test_top_level_limitations_are_semantically_nonduplicative(execute_api, live_case, question, task):
    data = response_for(execute_api, question, task)
    values = [key(value) for value in data["limitations"]]
    assert len(values) == len(set(values))
    assert sum("collaboration-message evidence is unavailable" in lim for lim in data["limitations"]) <= 1
    # These distinct evidence gaps must both survive even though both discuss tasks.
    assert any("historical throughput" in lim for lim in data["limitations"])
    assert any("4-week request" in lim for lim in data["limitations"])


@pytest.mark.parametrize("question", [WORKLOAD, WORKFORCE])
def test_top_level_recommended_actions_are_semantically_nonduplicative(execute_api, live_case, question):
    data = response_for(execute_api, question, task=False)
    assert sum("Collect privacy-safe" in action for action in data["recommended_actions"]) == 1
    assert any("Review overdue delivery risks" in action for action in data["recommended_actions"])


@pytest.mark.parametrize("question", [WORKLOAD, WORKFORCE])
def test_wellbeing_collection_action_is_not_repeated(execute_api, live_case, question):
    data = response_for(execute_api, question, task=False)
    expected = "Collect privacy-safe team pulse ratings in upcoming weeks for comparison, and review current delivery priorities with the manager."
    for owner in (data, next(f for f in data["findings"] if f["agent"] == "wellbeing")):
        assert [action for action in owner["recommended_actions"] if "Collect privacy-safe" in action] == [expected]


def test_collaboration_status_inquiry_does_not_confirm_task_completion(execute_api, live_case):
    data = response_for(execute_api, PROTECTIVE_QUERY, task=False)
    assert data["consulted_specialists"] == ["collaboration"]
    for owner in (data, data["findings"][0]):
        assert "confirming the completion" not in owner["summary"]
        assert "do not independently verify task completion" in owner["summary"]
        assert "requests for coordination meetings" in owner["summary"]
    assert "The development task is complete" not in visible(data)


@pytest.mark.parametrize("note", ["", "API access was restored"])
def test_collaboration_does_not_emit_unverified_blocker_cause(execute_api, live_case, note):
    db, gateway, _, _, _, _, task_id, _ = live_case
    selected = next(t for t in db["tasks"].docs if t["_id"] == task_id)
    selected["blockers"][0]["resolution_note"] = note
    data = response_for(execute_api, PROTECTIVE_QUERY, task=False)
    assert "API access" not in visible(data) and "API-access" not in visible(data)
    assert "Review the documented resolution steps for the resolved blockers before attributing a recurring cause." in data["recommended_actions"]
    assert "requests for coordination meetings" in data["summary"]
    # Retrieval alone does not establish sanitized note-to-output provenance.
    assert any("Verified resolved blocker" in call["user_prompt"] for call in gateway.calls)


def test_general_workforce_uses_workflow_appropriate_collaboration_limitation(execute_api, live_case):
    data = response_for(execute_api, WORKFORCE, task=False)
    expected = "Blocker status and resolution records establish Collaboration-domain observations. They do not independently explain overall delivery performance."
    assert expected in data["limitations"]
    assert "current delay" not in visible(data)


def test_single_week_heading_has_no_spurious_comma(execute_api, live_case):
    data = response_for(execute_api, WORKLOAD, task=False)
    assert "Anonymous single-week snapshot for the week starting" in data["summary"]
    assert "snapshot, for" not in visible(data)
    assert data["confidence"] == 0.45


def test_live_task_delay_payload_has_complete_nonduplicated_public_prose(execute_api, live_case):
    data = response_for(execute_api)
    assert_clean(data)
    assert data["consulted_specialists"] == ["productivity", "collaboration"]
    assert data["confidence"] == 0.60
    assert "progress is 20%" in data["summary"]
    assert "5 linked blocker(s) resolved" in data["summary"]


def test_live_team_delay_payload_has_complete_nonduplicated_public_prose(execute_api, live_case):
    data = response_for(execute_api, TEAM_DELAY, task=False)
    assert_clean(data)
    assert data["confidence"] == 0.77
    assert "3 are overdue" in data["summary"]


def test_live_team_workload_payload_has_complete_nonduplicated_public_prose(execute_api, live_case):
    data = response_for(execute_api, WORKLOAD, task=False)
    assert_clean(data)
    assert data["consulted_specialists"] == ["productivity", "wellbeing"]
    assert data["confidence"] == 0.45
    assert "workload manageability is 4.00 out of 5" in data["summary"]


def test_live_general_workforce_payload_has_complete_nonduplicated_public_prose(execute_api, live_case):
    data = response_for(execute_api, WORKFORCE, task=False)
    assert_clean(data)
    assert data["consulted_specialists"] == ["productivity", "collaboration", "wellbeing"]
    assert data["confidence"] == 0.45
    assert data["confidence"] == min(f["confidence"] for f in data["findings"])


@pytest.mark.parametrize("claim", [
    "Recent messages confirm the development task is complete.",
    "Recent messages prove delivery success.",
    "Communication shows productivity success.",
    "Communication demonstrates effective task management.",
    "Recent messages show workload manageability is high.",
    "Recent messages show well-being is strong.",
])
def test_collaboration_visible_fields_reject_cross_domain_conclusions(execute_api, live_case, claim):
    gateway = live_case[1]
    theme = "Recent messages included requests for coordination meetings."
    gateway.default_responses[CollaborationFindingOutput] = CollaborationFindingOutput(
        summary=f"{theme} {claim}", communication_observations=[claim],
        limitations=[claim], recommended_actions=[claim], confidence=0.99,
    )
    data = response_for(execute_api, PROTECTIVE_QUERY, task=False)
    assert claim not in visible(data)
    assert theme in data["summary"] and theme in data["findings"][0]["summary"]
    assert data["confidence"] == 0.77


def test_collaboration_preserves_complete_themes_and_rejects_provider_fragments(execute_api, live_case):
    theme = "Recent messages included requests for coordination meetings."
    live_case[1].default_responses[CollaborationFindingOutput] = CollaborationFindingOutput(
        summary=f"{theme} Messages included status inquiries and",
        communication_observations=["Communication has in the past, but..."],
        recommended_actions=["Review messages and"], confidence=0.99,
    )
    data = response_for(execute_api, PROTECTIVE_QUERY, task=False)
    assert theme in visible(data)
    assert "inquiries and" not in visible(data)
    assert "has in the past" not in visible(data)
    assert "Review messages and" not in visible(data)


def test_specialist_item_deduplication_preserves_distinct_evidence_gaps(execute_api, live_case):
    live_case[1].default_responses[ProductivityFindingOutput] = ProductivityFindingOutput(
        summary="The task snapshot was reviewed.", confidence=0.99,
        limitations=["Actual time logs are unavailable.", "actual time logs are unavailable!",
                     "Historical throughput records are unavailable."],
        recommended_actions=["Review task priorities.", "review task priorities!",
                             "Collect verified time logs."],
    )
    data = response_for(execute_api, "Summarize task progress", task=False)
    for owner in (data, data["findings"][0]):
        assert owner["limitations"].count("Actual time logs are unavailable.") == 1
        assert "Historical throughput records are unavailable." in owner["limitations"]
        assert owner["recommended_actions"] == ["Review task priorities.", "Collect verified time logs."]


def test_live_assignment_payload_preserves_evidence_confidence_and_suitability(execute_api, live_case):
    user, profile = seed_candidate(live_case)
    profile["skills"] = ["React", "FastAPI"]
    db, _, _, _, _, _, task_id, _ = live_case
    selected = next(t for t in db["tasks"].docs if t["_id"] == task_id)
    selected["assigned_to"] = user["_id"]
    question = ("Recommend up to 3 eligible candidates for the selected task. Explain required-skill coverage, "
                "current workload, overdue risk, capacity limitations, and the manager decision required.")
    response = execute_api(question, task_scope=True, weeks_lookback=None)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["consulted_specialists"] == ["task_assigning"]
    assert data["confidence"] == 0.95
    details = data["task_assignment_details"]
    assert details["human_decision_required"] is True
    candidate = details["candidate_recommendations"][0]
    assert candidate["suitability_score"] == 0.91
    assert candidate["recommendation_label"] == "capacity_review_required"
    assert candidate["active_task_count"] == candidate["overdue_task_count"] == 1


def test_production_sentence_filter_preserves_legitimate_semicolon_punctuation(execute_api, live_case):
    summary = "Current task states were retrieved; actual time logs are unavailable."
    limitation = "The current snapshot is available; historical throughput is not available."
    live_case[1].default_responses[ProductivityFindingOutput] = ProductivityFindingOutput(
        summary=summary, limitations=[limitation], confidence=0.99,
    )
    data = response_for(execute_api, "Summarize task progress", task=False)
    assert data["summary"] == summary
    assert limitation in data["limitations"]
    assert data["findings"][0]["summary"] == summary


def test_collaboration_output_budget_does_not_cut_a_communication_sentence(execute_api, live_case):
    live_case[1].default_responses[CollaborationFindingOutput] = CollaborationFindingOutput(
        summary="Recent messages included " + "coordination requests " * 130 + ".",
        confidence=0.99,
    )
    data = response_for(execute_api, PROTECTIVE_QUERY, task=False)
    for owner in (data, data["findings"][0]):
        assert owner["summary"].endswith(".")
        assert "do not independently verify task completion" in owner["summary"]
