import argparse
import copy
import gc
import json
import warnings
from collections import Counter, defaultdict
from datetime import timedelta, timezone

import pytest
from bson import BSON, ObjectId
from pymongo.errors import OperationFailure

from backend.app.core.security import verify_password
from backend.scripts import seed_viva_data as seed
from backend.tests.conftest import FakeAsyncDatabase


MANAGER_EMAIL = "manager.account@example.com"
PASSWORD = "VivaAccessPassword2026!"


def make_manager() -> dict:
    return {
        "_id": ObjectId("64b1f28b4f1c2b3a4e5d6f03"),
        "name": "Existing Manager",
        "email": MANAGER_EMAIL,
        "password_hash": "existing-manager-hash",
        "role": "manager",
        "is_active": True,
    }


def unique_opaque_hasher():
    counter = {"value": 0}

    def hash_value(_password: str) -> str:
        counter["value"] += 1
        return f"opaque-hash-{counter['value']:02d}"

    return hash_value


@pytest.fixture(scope="module")
def plan():
    return seed.build_seed_plan(
        make_manager(),
        PASSWORD,
        password_hasher=unique_opaque_hasher(),
    )


def make_database() -> FakeAsyncDatabase:
    database = FakeAsyncDatabase()
    database["users"].docs.append(copy.deepcopy(make_manager()))
    return database


def make_bson_round_tripped_database(plan) -> FakeAsyncDatabase:
    database = make_database()
    for collection in seed.COLLECTION_ORDER:
        database[collection].docs.extend(
            BSON(BSON.encode(document)).decode()
            for document in plan.documents[collection]
        )
    return database


class RecordingSession:
    def __init__(self, *, start_error=None, commit_error=None, abort_error=None):
        self.start_error = start_error
        self.commit_error = commit_error
        self.abort_error = abort_error
        self.events = []

    async def __aenter__(self):
        self.events.append("session-enter")
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self.events.append("session-exit")

    async def start_transaction(self):
        self.events.append("start")
        if self.start_error is not None:
            raise self.start_error
        return object()

    async def commit_transaction(self):
        self.events.append("commit")
        if self.commit_error is not None:
            raise self.commit_error

    async def abort_transaction(self):
        self.events.append("abort")
        if self.abort_error is not None:
            raise self.abort_error


class RecordingClient:
    def __init__(self, session):
        self.session = session
        self.start_session_calls = 0

    def start_session(self):
        self.start_session_calls += 1
        return self.session


def empty_database_plan():
    return seed.DatabasePlan(
        existing_counts={name: 0 for name in seed.COLLECTION_ORDER},
        to_insert={name: [] for name in seed.COLLECTION_ORDER},
    )


def without_hashes(plan):
    result = copy.deepcopy(plan.documents)
    for user in result["users"]:
        user.pop("password_hash")
    return result


def test_generation_is_deterministic_and_has_exact_counts(plan):
    second = seed.build_seed_plan(
        make_manager(),
        PASSWORD,
        password_hasher=unique_opaque_hasher(),
    )

    assert without_hashes(plan) == without_hashes(second)
    assert plan.counts() == {
        "teams": 4,
        "users": 20,
        "employee_profiles": 20,
        "tasks": 32,
        "collaboration_messages": 48,
        "weekly_pulse_responses": 64,
    }
    ids = [doc["_id"] for documents in plan.documents.values() for doc in documents]
    assert len(ids) == len(set(ids))
    assert all(ObjectId.is_valid(str(value)) for value in ids)


def test_employee_names_emails_profiles_and_manager_ownership_are_realistic(plan):
    users = plan.documents["users"]
    profiles = plan.documents["employee_profiles"]
    teams = plan.documents["teams"]

    assert [user["name"] for user in users] == [item[0] for item in seed.EMPLOYEES]
    assert len({user["email"] for user in users}) == 20
    assert all(user["email"].endswith("@example.com") for user in users)
    assert all(user["role"] == "employee" and user["is_active"] for user in users)
    assert all(team["manager_id"] == plan.manager_id for team in teams)
    assert Counter(user["team_id"] for user in users) == Counter({team["_id"]: 5 for team in teams})
    assert Counter(profile["user_id"] for profile in profiles) == Counter({user["_id"]: 1 for user in users})
    forbidden_names = {"Demo Employee", "Test User", "User 01", "Sample User", "Seed User"}
    assert not forbidden_names.intersection(user["name"] for user in users)


def test_real_argon_hashes_are_independent_and_verify_with_production_utility():
    hashed_plan = seed.build_seed_plan(make_manager(), PASSWORD)
    hashes = [user["password_hash"] for user in hashed_plan.documents["users"]]

    assert len(set(hashes)) == 20
    assert all(hash_value != PASSWORD for hash_value in hashes)
    assert all(verify_password(PASSWORD, hash_value) for hash_value in hashes)


def test_task_progress_blocker_and_assignment_evidence_invariants(plan):
    validation = seed.validate_seed_plan(plan)
    tasks = plan.documents["tasks"]
    users = {user["_id"]: user for user in plan.documents["users"]}

    assert validation["task_statuses"] == {"todo": 6, "in_progress": 12, "blocked": 6, "completed": 8}
    assert validation["progress_count"] == 80
    assert validation["blocker_count"] == 16
    assert validation["unresolved_blocker_count"] == 8
    assert validation["stale_blocker_count"] == 3
    assert validation["resolved_blocker_count"] == 8
    assert any(task["assigned_to"] is None for task in tasks)
    assert any(task["priority"] == "urgent" and task["due_date"] < plan.snapshot_at and task["status"] != "completed" for task in tasks)

    for task in tasks:
        if task["assigned_to"]:
            assert users[task["assigned_to"]]["team_id"] == task["team_id"]
        percentages = [progress["percentage"] for progress in task["progress_history"]]
        timestamps = [progress["logged_at"] for progress in task["progress_history"]]
        assert percentages == sorted(percentages)
        assert timestamps == sorted(timestamps)
        if task["status"] == "completed":
            assert percentages[-1] == 100
        if task["status"] == "blocked":
            assert any(not blocker["is_resolved"] for blocker in task["blockers"])

    assert validation["evidence"]["task_assignment_scenarios"] == {
        "multiple_eligible_candidates": True,
        "exactly_one_eligible_candidate": True,
        "no_eligible_candidate": True,
        "capacity_review_required": True,
        "overdue_work_risk": True,
    }


def test_resolved_and_stale_blockers_are_consistent(plan):
    blockers = [blocker for task in plan.documents["tasks"] for blocker in task["blockers"]]
    unresolved = [blocker for blocker in blockers if not blocker["is_resolved"]]
    resolved = [blocker for blocker in blockers if blocker["is_resolved"]]
    stale_threshold = plan.snapshot_at - seed.timedelta(days=seed.STALE_BLOCKER_THRESHOLD_DAYS)

    assert sum(blocker["created_at"] < stale_threshold for blocker in unresolved) == 3
    assert all(blocker["resolution_note"] and blocker["resolved_by"] == plan.manager_id for blocker in resolved)
    assert all(blocker["resolved_at"] > blocker["created_at"] for blocker in resolved)
    assert all(blocker["resolution_note"] is None and blocker["resolved_at"] is None for blocker in unresolved)


def test_messages_are_authorized_team_level_and_within_production_limit(plan):
    users = {user["_id"]: user for user in plan.documents["users"]}
    messages = plan.documents["collaboration_messages"]

    assert len(messages) == 48
    assert sum(seed.MESSAGE_CATEGORY_COUNTS.values()) == 48
    assert all("task_id" not in message for message in messages)
    assert all(0 < len(message["content"]) <= seed.TEAM_MESSAGE_MAX_LENGTH for message in messages)
    assert all(message["updated_at"] >= message["created_at"] for message in messages)
    for message in messages:
        if message["sender_id"] != plan.manager_id:
            assert users[message["sender_id"]]["team_id"] == message["team_id"]


def test_pulses_are_unique_private_and_cover_four_weeks(plan):
    pulses = plan.documents["weekly_pulse_responses"]
    keys = {(pulse["user_id"], pulse["week_start"]) for pulse in pulses}
    grouped = Counter((pulse["team_id"], pulse["week_start"]) for pulse in pulses)

    assert len(keys) == len(pulses) == 64
    assert len(grouped) == 16
    assert set(grouped.values()) == {4}
    assert len({week for _team, week in grouped}) == 4
    assert all(count >= seed.MINIMUM_AGGREGATE_RESPONSES for count in grouped.values())
    assert all(1 <= pulse[field] <= 5 for pulse in pulses for field in ("workload_manageability", "work_life_balance", "team_support", "engagement"))
    assert all("@" not in pulse["optional_comment"] for pulse in pulses)


@pytest.mark.asyncio
async def test_id_collision_and_unique_field_collision_are_rejected(plan):
    database = make_database()
    conflicting = copy.deepcopy(plan.documents["teams"][0])
    conflicting["name"] = "Unrelated Existing Team"
    database["teams"].docs.append(conflicting)
    with pytest.raises(ValueError, match="Deterministic ID collision"):
        await seed.inspect_database_plan(database, plan)

    database = make_database()
    database["users"].docs.append(
        {
            "_id": ObjectId(),
            "name": "Unrelated Account",
            "email": plan.documents["users"][0]["email"],
            "role": "employee",
            "is_active": True,
        }
    )
    with pytest.raises(ValueError, match="email"):
        await seed.inspect_database_plan(database, plan)


def test_real_bson_round_trip_matches_every_stable_planned_field(plan):
    for collection in seed.COLLECTION_ORDER:
        for document in plan.documents[collection]:
            stored = BSON(BSON.encode(document)).decode()
            assert seed._identity_matches(collection, stored, document)


def test_datetime_comparison_normalizes_naive_utc_and_millisecond_precision(plan):
    expected = copy.deepcopy(plan.documents["collaboration_messages"][0])
    expected["created_at"] = expected["created_at"].replace(microsecond=987654)
    stored = BSON(BSON.encode(expected)).decode()

    assert expected["created_at"].tzinfo == timezone.utc
    assert stored["created_at"].tzinfo is None
    assert stored["created_at"].microsecond == 987000
    assert seed._identity_matches("collaboration_messages", stored, expected)

    stored["created_at"] += timedelta(milliseconds=1)
    assert not seed._identity_matches("collaboration_messages", stored, expected)


def test_only_supported_optional_null_fields_are_missing_null_equivalent(plan):
    expected = copy.deepcopy(
        next(message for message in plan.documents["collaboration_messages"] if message["edited_at"] is None)
    )
    stored = BSON(BSON.encode(expected)).decode()
    stored.pop("edited_at")
    assert seed._identity_matches("collaboration_messages", stored, expected)

    stored = BSON(BSON.encode(expected)).decode()
    stored.pop("is_deleted")
    assert not seed._identity_matches("collaboration_messages", stored, expected)


@pytest.mark.parametrize("changed_field", ["content", "sender_id", "team_id", "is_deleted"])
def test_genuine_message_content_scope_and_deletion_changes_still_abort(plan, changed_field):
    expected = copy.deepcopy(plan.documents["collaboration_messages"][0])
    stored = BSON(BSON.encode(expected)).decode()
    if changed_field == "content":
        stored[changed_field] = "Altered collaboration content."
    elif changed_field == "is_deleted":
        stored[changed_field] = True
    else:
        stored[changed_field] = ObjectId()

    assert not seed._identity_matches("collaboration_messages", stored, expected)


@pytest.mark.asyncio
async def test_unrelated_collaboration_document_at_deterministic_id_is_rejected(plan):
    database = make_database()
    conflicting = BSON(BSON.encode(plan.documents["collaboration_messages"][0])).decode()
    conflicting["sender_id"] = ObjectId()
    database["collaboration_messages"].docs.append(conflicting)

    with pytest.raises(ValueError, match="Deterministic ID collision detected in collaboration_messages"):
        await seed.inspect_database_plan(database, plan)


@pytest.mark.asyncio
async def test_post_apply_bson_round_trip_plans_zero_inserts_for_every_collection(plan):
    database = make_bson_round_tripped_database(plan)
    db_plan = await seed.inspect_database_plan(database, plan)

    assert db_plan.existing_counts == plan.counts()
    assert {name: len(documents) for name, documents in db_plan.to_insert.items()} == {
        name: 0 for name in seed.COLLECTION_ORDER
    }
    assert (await seed.apply_seed_plan(database, plan)).insert_count == 0


@pytest.mark.asyncio
async def test_post_apply_dry_run_reports_all_existing_and_zero_planned_inserts(
    plan, monkeypatch, capsys
):
    database = make_bson_round_tripped_database(plan)
    monkeypatch.setenv("VIVA_DEMO_PASSWORD", PASSWORD)
    monkeypatch.setattr(seed, "hash_password", unique_opaque_hasher())
    args = argparse.Namespace(
        dry_run=True,
        apply=False,
        cleanup_dry_run=False,
        cleanup=False,
        manager_email=MANAGER_EMAIL,
        confirm=None,
    )

    assert await seed.run_command(args, database=database) == 0
    output = capsys.readouterr().out
    report = json.loads(output.split("\nDry run complete:", 1)[0])
    assert report["existing"] == plan.counts()
    assert report["planned_inserts"] == {name: 0 for name in seed.COLLECTION_ORDER}


@pytest.mark.asyncio
async def test_transaction_start_is_awaited_and_success_commits_without_warning(monkeypatch):
    session = RecordingSession()
    client = RecordingClient(session)

    async def record_insert(_database, _db_plan, *, session):
        session.events.append("insert")

    monkeypatch.setattr(seed, "_insert_missing", record_insert)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        await seed._insert_in_transaction(client, object(), empty_database_plan())
        gc.collect()

    assert client.start_session_calls == 1
    assert session.events == ["session-enter", "start", "insert", "commit", "session-exit"]
    assert not any("was never awaited" in str(item.message) for item in caught)


@pytest.mark.asyncio
async def test_transaction_insert_failure_is_safely_aborted(monkeypatch):
    session = RecordingSession()

    async def fail_insert(_database, _db_plan, *, session):
        session.events.append("insert")
        raise RuntimeError("injected transactional write failure")

    monkeypatch.setattr(seed, "_insert_missing", fail_insert)
    with pytest.raises(RuntimeError, match="transactional write failure"):
        await seed._insert_in_transaction(RecordingClient(session), object(), empty_database_plan())

    assert session.events == ["session-enter", "start", "insert", "abort", "session-exit"]


@pytest.mark.asyncio
async def test_commit_failure_attempts_safe_abort_and_preserves_original_error(monkeypatch):
    session = RecordingSession(
        commit_error=RuntimeError("injected commit failure"),
        abort_error=OperationFailure("transaction is no longer active", code=251),
    )

    async def record_insert(_database, _db_plan, *, session):
        session.events.append("insert")

    monkeypatch.setattr(seed, "_insert_missing", record_insert)
    with pytest.raises(RuntimeError, match="injected commit failure"):
        await seed._insert_in_transaction(RecordingClient(session), object(), empty_database_plan())

    assert session.events == ["session-enter", "start", "insert", "commit", "abort", "session-exit"]


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [AttributeError, TypeError, RuntimeError])
async def test_programming_error_before_transaction_is_not_misclassified_or_written(plan, error_type):
    database = make_database()
    session = RecordingSession(start_error=error_type("injected programming error"))

    with pytest.raises(error_type, match="injected programming error"):
        await seed.apply_seed_plan(database, plan, client=RecordingClient(session))

    assert session.events == ["session-enter", "start", "session-exit"]
    assert len(database["users"].docs) == 1
    assert all(
        not database[name].docs
        for name in ("teams", "employee_profiles", "tasks", "collaboration_messages", "weekly_pulse_responses")
    )


@pytest.mark.asyncio
async def test_genuine_unsupported_transaction_uses_tracked_fallback(plan):
    database = make_database()
    session = RecordingSession()
    original_insert = database["teams"].insert_one

    async def reject_transaction(document, **kwargs):
        if kwargs.get("session") is not None:
            raise OperationFailure(
                "Transaction numbers are only allowed on a replica set member or mongos",
                code=20,
            )
        return await original_insert(document)

    database["teams"].insert_one = reject_transaction
    result = await seed.apply_seed_plan(database, plan, client=RecordingClient(session))

    assert result.insert_count == 188
    assert session.events == ["session-enter", "start", "abort", "session-exit"]
    assert {name: len(database[name].docs) for name in seed.COLLECTION_ORDER} == {
        **plan.counts(),
        "users": 21,
    }


@pytest.mark.asyncio
async def test_operation_error_inside_supported_transaction_does_not_fallback(plan, monkeypatch):
    database = make_database()
    session = RecordingSession()

    async def fail_insert(_database, _db_plan, *, session):
        session.events.append("insert")
        raise OperationFailure("Operation is not supported in a transaction", code=263)

    monkeypatch.setattr(seed, "_insert_missing", fail_insert)
    with pytest.raises(OperationFailure, match="not supported in a transaction"):
        await seed.apply_seed_plan(database, plan, client=RecordingClient(session))

    assert session.events == ["session-enter", "start", "insert", "abort", "session-exit"]
    assert len(database["users"].docs) == 1


@pytest.mark.asyncio
async def test_second_apply_plans_zero_inserts_and_preserves_existing_records(plan):
    database = make_database()
    original_manager = copy.deepcopy(database["users"].docs[0])
    gama = {"_id": ObjectId(), "name": "Gama", "manager_id": plan.manager_id}
    database["teams"].docs.append(gama)

    first = await seed.apply_seed_plan(database, plan)
    second = await seed.apply_seed_plan(database, plan)

    assert first.insert_count == 188
    assert second.insert_count == 0
    assert database["users"].docs[0] == original_manager
    assert await database["teams"].find_one({"_id": gama["_id"]}) == gama


@pytest.mark.asyncio
async def test_failed_nontransactional_apply_rolls_back_only_new_records(plan):
    database = make_database()
    unrelated_team = {"_id": ObjectId(), "name": "Gama", "manager_id": plan.manager_id}
    database["teams"].docs.append(unrelated_team)
    original_insert = database["tasks"].insert_one
    calls = {"value": 0}

    async def fail_first_task(document):
        calls["value"] += 1
        if calls["value"] == 1:
            raise RuntimeError("injected write failure")
        return await original_insert(document)

    database["tasks"].insert_one = fail_first_task
    with pytest.raises(RuntimeError, match="injected write failure"):
        await seed.apply_seed_plan(database, plan)

    assert len(database["users"].docs) == 1
    assert database["teams"].docs == [unrelated_team]
    assert all(not database[name].docs for name in ("employee_profiles", "tasks", "collaboration_messages", "weekly_pulse_responses"))


@pytest.mark.asyncio
async def test_cleanup_targets_only_exact_seed_records(plan):
    database = make_database()
    await seed.apply_seed_plan(database, plan)
    unrelated = {"_id": ObjectId(), "name": "Gama", "manager_id": plan.manager_id}
    database["teams"].docs.append(unrelated)

    targets = await seed.inspect_cleanup_targets(database, plan)
    assert {name: len(values) for name, values in targets.items()} == plan.counts()
    deleted = await seed.cleanup_seed_plan(database, plan)

    assert deleted == plan.counts()
    assert await database["teams"].find_one({"_id": unrelated["_id"]}) == unrelated
    assert len(database["users"].docs) == 1


@pytest.mark.asyncio
async def test_dry_run_performs_zero_writes_and_output_contains_no_password_or_hash(monkeypatch, capsys):
    database = make_database()
    before = {name: copy.deepcopy(database[name].docs) for name in seed.COLLECTION_ORDER}
    monkeypatch.setenv("VIVA_DEMO_PASSWORD", PASSWORD)
    monkeypatch.setattr(seed, "hash_password", unique_opaque_hasher())
    args = argparse.Namespace(
        dry_run=True,
        apply=False,
        cleanup_dry_run=False,
        cleanup=False,
        manager_email=MANAGER_EMAIL,
        confirm=None,
    )

    assert await seed.run_command(args, database=database) == 0
    output = capsys.readouterr().out

    assert PASSWORD not in output
    assert "opaque-hash" not in output
    assert "password_hash" not in output
    assert all(database[name].docs == before[name] for name in seed.COLLECTION_ORDER)
    assert "zero database writes" in output.lower()


@pytest.mark.asyncio
async def test_dry_run_refuses_missing_password_without_writes(monkeypatch):
    database = make_database()
    monkeypatch.delenv("VIVA_DEMO_PASSWORD", raising=False)
    args = argparse.Namespace(
        dry_run=True,
        apply=False,
        cleanup_dry_run=False,
        cleanup=False,
        manager_email=MANAGER_EMAIL,
        confirm=None,
    )
    with pytest.raises(ValueError, match="VIVA_DEMO_PASSWORD"):
        await seed.run_command(args, database=database)
    assert len(database["users"].docs) == 1


@pytest.mark.asyncio
async def test_manager_selection_requires_one_active_manager():
    database = make_database()
    selected = await seed.select_manager(database, MANAGER_EMAIL)
    assert selected["_id"] == make_manager()["_id"]

    database["users"].docs[0]["is_active"] = False
    with pytest.raises(PermissionError, match="active Manager"):
        await seed.select_manager(database, MANAGER_EMAIL)


def test_safe_manifest_excludes_password_hashes_and_ids(plan, tmp_path):
    manifest = seed.write_safe_account_manifest(plan, tmp_path / "accounts.json")
    text = manifest.read_text(encoding="utf-8")

    assert PASSWORD not in text
    assert "password" not in text.lower()
    assert "_id" not in text
    assert "ObjectId" not in text
    assert seed.BATCH_NAMESPACE in text

    internal_manifest = seed.write_internal_id_manifest(plan, tmp_path / "document-ids.json")
    internal_text = internal_manifest.read_text(encoding="utf-8")
    assert PASSWORD not in internal_text
    assert "password" not in internal_text.lower()
    assert str(plan.documents["users"][0]["_id"]) in internal_text
