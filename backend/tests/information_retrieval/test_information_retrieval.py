from datetime import datetime, timezone
import pytest
from bson import ObjectId
from pymongo.errors import PyMongoError

from backend.app.core.security import create_access_token
from backend.app.modules.information_retrieval.service import (
    BM25Ranker,
    SearchableDocument,
    build_collaboration_document,
    build_task_document,
)
from backend.app.modules.information_retrieval.tokenizer import (
    generate_snippet,
    is_valid_query,
    normalize_text,
    tokenize,
)


@pytest.fixture
def client(test_setup):
    c, _ = test_setup
    return c


@pytest.fixture(autouse=True)
def clean_db(fake_db):
    """Ensure clean collections for each test."""
    for col in (
        "users",
        "teams",
        "tasks",
        "collaboration_messages",
        "weekly_pulse_responses",
        "employee_profiles",
    ):
        fake_db[col].docs = []
        fake_db[col].indexes = {}


def _create_user(fake_db, email: str, role: str, team_id=None, name="Test User"):
    user_id = ObjectId()
    doc = {
        "_id": user_id,
        "name": name,
        "email": email,
        "role": role,
        "is_active": True,
        "team_id": team_id,
        "created_at": datetime.now(timezone.utc),
    }
    fake_db["users"].docs.append(doc)
    token, _ = create_access_token(str(user_id))
    return doc, token


def _create_team(fake_db, name: str, manager_id):
    team_id = ObjectId()
    doc = {
        "_id": team_id,
        "name": name,
        "manager_id": manager_id,
        "created_at": datetime.now(timezone.utc),
    }
    fake_db["teams"].docs.append(doc)
    return doc


# =========================================================================
# Unit Tests: Tokenizer & BM25 Scoring
# =========================================================================


def test_tokenizer_unicode_casefold_and_stopwords():
    raw_text = "  The quick   BROWN FÖX jumps over the lazy dog!  "
    tokens = tokenize(raw_text, filter_stopwords=True)
    # 'the' is a stopword and should be removed
    assert "the" not in tokens
    assert "quick" in tokens
    assert "brown" in tokens
    assert "föx" in tokens
    assert "jumps" in tokens
    assert "over" in tokens
    assert "lazy" in tokens
    assert "dog" in tokens


def test_tokenizer_query_validation():
    # Valid query
    is_valid, msg = is_valid_query("kubernetes deployment")
    assert is_valid is True
    assert msg == ""

    # Empty query
    is_valid, msg = is_valid_query("")
    assert is_valid is False
    assert "empty" in msg.lower()

    # Whitespace only
    is_valid, msg = is_valid_query("   \t\n  ")
    assert is_valid is False

    # Punctuation only
    is_valid, msg = is_valid_query("!@#$%^&*()_+-=")
    assert is_valid is False

    # Stopwords only
    is_valid, msg = is_valid_query("the and or in")
    assert is_valid is False

    # Excessively long query (> 200 chars)
    long_q = "term " * 50
    is_valid, msg = is_valid_query(long_q, max_length=200)
    assert is_valid is False
    assert "exceeds" in msg.lower()


def test_snippet_generator_plain_text():
    sections = [
        ("Title", "Implement OAuth2 Authentication"),
        ("Description", "Secure the backend endpoints using JWT and OAuth2 flows with role-based access control."),
    ]
    snippet = generate_snippet(sections, ["oauth2", "jwt"])
    assert "[Title]" in snippet or "[Description]" in snippet
    assert "OAuth2" in snippet
    assert "<" not in snippet  # No HTML tags


def test_bm25_ranking_math_and_length_normalization():
    doc1 = SearchableDocument(
        source_type="task",
        record_id="1",
        title="Database Optimization",
        sections=[("Title", "Database Optimization")],
        tokens=["database", "optimization", "indexes"],
    )
    doc2 = SearchableDocument(
        source_type="task",
        record_id="2",
        title="Unrelated UI Styling",
        sections=[("Title", "Unrelated UI Styling")],
        tokens=["css", "tailwind", "colors", "buttons"],
    )

    ranker = BM25Ranker([doc1, doc2])
    total, results = ranker.rank("database optimization")
    assert total == 1
    assert len(results) == 1
    assert results[0].record_id == "1"
    assert results[0].score > 0.0
    assert "database" in results[0].matched_terms


# =========================================================================
# Integration & Security Tests: Lexical Search API
# =========================================================================


def test_search_requires_authentication(client):
    res = client.get("/api/search?q=database")
    assert res.status_code == 401


def test_search_empty_and_punctuation_query_validation(client, fake_db):
    _, emp_token = _create_user(fake_db, "emp@example.com", "employee")
    headers = {"Authorization": f"Bearer {emp_token}"}

    # Empty query string
    res = client.get("/api/search?q=", headers=headers)
    assert res.status_code == 422

    # Whitespace only
    res = client.get("/api/search?q=%20%20%20", headers=headers)
    assert res.status_code == 422

    # Punctuation only
    res = client.get("/api/search?q=!!%3F%23%24", headers=headers)
    assert res.status_code == 422

    # Excessively long query (> 200 chars)
    long_q = "word" * 60
    res = client.get(f"/api/search?q={long_q}", headers=headers)
    assert res.status_code == 422


def test_search_invalid_source_and_limit_validation(client, fake_db):
    _, emp_token = _create_user(fake_db, "emp@example.com", "employee")
    headers = {"Authorization": f"Bearer {emp_token}"}

    # Invalid source filter
    res = client.get("/api/search?q=database&source=invalid_source", headers=headers)
    assert res.status_code == 422

    # Limit less than 1
    res = client.get("/api/search?q=database&limit=0", headers=headers)
    assert res.status_code == 422

    # Limit greater than 20
    res = client.get("/api/search?q=database&limit=25", headers=headers)
    assert res.status_code == 422


def test_search_invalid_team_id_format(client, fake_db):
    _, emp_token = _create_user(fake_db, "emp@example.com", "employee")
    headers = {"Authorization": f"Bearer {emp_token}"}

    res = client.get("/api/search?q=database&team_id=invalid-not-an-oid", headers=headers)
    assert res.status_code == 400
    assert "Invalid Team ID format" in res.json()["detail"]


def test_exact_and_multiterm_retrieval(client, fake_db):
    mgr, mgr_token = _create_user(fake_db, "mgr@example.com", "manager")
    team = _create_team(fake_db, "Backend Alpha", mgr["_id"])
    emp, emp_token = _create_user(fake_db, "emp@example.com", "employee", team_id=team["_id"])

    task_id = ObjectId()
    fake_db["tasks"].docs.append(
        {
            "_id": task_id,
            "title": "Migrate Redis caching layer",
            "description": "Improve API latency with distributed Redis caching",
            "team_id": team["_id"],
            "assigned_to": emp["_id"],
            "created_by": mgr["_id"],
            "required_skills": ["Redis", "FastAPI"],
            "priority": "high",
            "status": "in_progress",
            "progress_history": [],
            "blockers": [],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    headers = {"Authorization": f"Bearer {emp_token}"}

    # Exact single term
    res1 = client.get("/api/search?q=Redis", headers=headers)
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["total_matches"] == 1
    assert data1["results"][0]["record_id"] == str(task_id)
    assert data1["results"][0]["title"] == "Migrate Redis caching layer"
    assert data1["results"][0]["team_name"] == "Backend Alpha"

    # Multi-term query
    res2 = client.get("/api/search?q=distributed caching layer", headers=headers)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["total_matches"] == 1
    assert data2["results"][0]["record_id"] == str(task_id)
    assert "caching" in data2["results"][0]["matched_terms"]


def test_ranking_relevance_and_title_weighting(client, fake_db):
    mgr, mgr_token = _create_user(fake_db, "mgr@example.com", "manager")
    team = _create_team(fake_db, "Infra Team", mgr["_id"])
    emp, emp_token = _create_user(fake_db, "emp@example.com", "employee", team_id=team["_id"])

    # Doc A: mentions 'Kubernetes' in the Title (boosted)
    task_a = ObjectId()
    fake_db["tasks"].docs.append(
        {
            "_id": task_a,
            "title": "Kubernetes Cluster Upgrade",
            "description": "General maintenance of the infrastructure",
            "team_id": team["_id"],
            "assigned_to": emp["_id"],
            "created_by": mgr["_id"],
            "required_skills": [],
            "progress_history": [],
            "blockers": [],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    # Doc B: mentions 'Kubernetes' only once in the description
    task_b = ObjectId()
    fake_db["tasks"].docs.append(
        {
            "_id": task_b,
            "title": "Update Documentation",
            "description": "Update developer guide for deploying services on Kubernetes clusters.",
            "team_id": team["_id"],
            "assigned_to": emp["_id"],
            "created_by": mgr["_id"],
            "required_skills": [],
            "progress_history": [],
            "blockers": [],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    headers = {"Authorization": f"Bearer {emp_token}"}
    res = client.get("/api/search?q=Kubernetes", headers=headers)
    assert res.status_code == 200
    results = res.json()["results"]
    assert len(results) == 2
    # Title-boosted task A must rank above task B
    assert results[0]["record_id"] == str(task_a)
    assert results[1]["record_id"] == str(task_b)
    assert results[0]["score"] > results[1]["score"]


def test_progress_note_and_blocker_retrieval(client, fake_db):
    mgr, mgr_token = _create_user(fake_db, "mgr@example.com", "manager")
    team = _create_team(fake_db, "Core Platform", mgr["_id"])
    emp, emp_token = _create_user(fake_db, "emp@example.com", "employee", team_id=team["_id"])

    task_id = ObjectId()
    fake_db["tasks"].docs.append(
        {
            "_id": task_id,
            "title": "Payment Gateway Integration",
            "description": "Integrate Stripe checkout for subscription billing.",
            "team_id": team["_id"],
            "assigned_to": emp["_id"],
            "created_by": mgr["_id"],
            "required_skills": ["Python"],
            "progress_history": [
                {
                    "id": str(ObjectId()),
                    "user_id": emp["_id"],
                    "percentage": 50,
                    "notes": "Completed webhook signature verification and sandbox testing.",
                    "logged_at": datetime.now(timezone.utc),
                }
            ],
            "blockers": [
                {
                    "id": str(ObjectId()),
                    "user_id": emp["_id"],
                    "description": "Blocked by merchant account KYC approval delay from provider.",
                    "is_resolved": True,
                    "resolution_note": "KYC documentation approved via merchant compliance hotline.",
                    "created_at": datetime.now(timezone.utc),
                    "resolved_at": datetime.now(timezone.utc),
                }
            ],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    headers = {"Authorization": f"Bearer {emp_token}"}

    # Search progress update note
    res_prog = client.get("/api/search?q=webhook sandbox testing", headers=headers)
    assert res_prog.status_code == 200
    assert res_prog.json()["total_matches"] == 1
    assert res_prog.json()["results"][0]["record_id"] == str(task_id)

    # Search blocker description
    res_block = client.get("/api/search?q=merchant approval delay", headers=headers)
    assert res_block.status_code == 200
    assert res_block.json()["total_matches"] == 1
    assert res_block.json()["results"][0]["record_id"] == str(task_id)

    # Search blocker resolution note
    res_res = client.get("/api/search?q=compliance hotline", headers=headers)
    assert res_res.status_code == 200
    assert res_res.json()["total_matches"] == 1
    assert res_res.json()["results"][0]["record_id"] == str(task_id)


def test_collaboration_message_retrieval(client, fake_db):
    mgr, mgr_token = _create_user(fake_db, "mgr@example.com", "manager")
    team = _create_team(fake_db, "Design Squad", mgr["_id"])
    emp, emp_token = _create_user(fake_db, "emp@example.com", "employee", team_id=team["_id"])

    msg_id = ObjectId()
    fake_db["collaboration_messages"].docs.append(
        {
            "_id": msg_id,
            "team_id": team["_id"],
            "sender_id": emp["_id"],
            "content": "Please review the updated Figma prototypes for the onboarding workflow.",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "is_deleted": False,
        }
    )

    headers = {"Authorization": f"Bearer {emp_token}"}
    res = client.get("/api/search?q=Figma prototypes onboarding&source=collaboration", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total_matches"] == 1
    assert data["results"][0]["source_type"] == "collaboration"
    assert data["results"][0]["record_id"] == str(msg_id)
    assert "Figma" in data["results"][0]["snippet"]


def test_employee_cannot_retrieve_other_team_content(client, fake_db):
    mgr, mgr_token = _create_user(fake_db, "mgr@example.com", "manager")
    team1 = _create_team(fake_db, "Team 1", mgr["_id"])
    team2 = _create_team(fake_db, "Team 2", mgr["_id"])

    emp1, emp1_token = _create_user(fake_db, "emp1@example.com", "employee", team_id=team1["_id"])
    emp2, emp2_token = _create_user(fake_db, "emp2@example.com", "employee", team_id=team2["_id"])

    # Task assigned to emp2 in team2
    fake_db["tasks"].docs.append(
        {
            "_id": ObjectId(),
            "title": "Confidential Security Audit Protocol",
            "description": "Sensitive vulnerability scanning across perimeter.",
            "team_id": team2["_id"],
            "assigned_to": emp2["_id"],
            "created_by": mgr["_id"],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    # Message in team2
    fake_db["collaboration_messages"].docs.append(
        {
            "_id": ObjectId(),
            "team_id": team2["_id"],
            "sender_id": emp2["_id"],
            "content": "Confidential discussion regarding Team 2 internal reorganizations.",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "is_deleted": False,
        }
    )

    # Employee 1 attempts to search for team 2 terms
    headers1 = {"Authorization": f"Bearer {emp1_token}"}
    res = client.get("/api/search?q=Confidential Security Audit", headers=headers1)
    assert res.status_code == 200
    assert res.json()["total_matches"] == 0
    assert len(res.json()["results"]) == 0

    # Employee 1 attempts to explicitly pass Team 2 ID -> 403 Forbidden
    res_forbidden = client.get(f"/api/search?q=Confidential&team_id={team2['_id']}", headers=headers1)
    assert res_forbidden.status_code == 403
    assert "assigned team scope" in res_forbidden.json()["detail"]


def test_manager_scope_and_unmanaged_team_isolation(client, fake_db):
    mgr1, mgr1_token = _create_user(fake_db, "mgr1@example.com", "manager")
    mgr2, mgr2_token = _create_user(fake_db, "mgr2@example.com", "manager")

    team1 = _create_team(fake_db, "Managed Team 1", mgr1["_id"])
    team2 = _create_team(fake_db, "Unmanaged Team 2", mgr2["_id"])

    # Task in team1
    task1 = ObjectId()
    fake_db["tasks"].docs.append(
        {
            "_id": task1,
            "title": "Quantum Encryption Protocol",
            "description": "Developing quantum-resistant keys for Team 1.",
            "team_id": team1["_id"],
            "created_by": mgr1["_id"],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    # Task in team2
    fake_db["tasks"].docs.append(
        {
            "_id": ObjectId(),
            "title": "Quantum Algorithm Testing",
            "description": "Team 2 specific quantum benchmark scripts.",
            "team_id": team2["_id"],
            "created_by": mgr2["_id"],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    headers1 = {"Authorization": f"Bearer {mgr1_token}"}

    # Manager 1 searches broadly
    res = client.get("/api/search?q=Quantum", headers=headers1)
    assert res.status_code == 200
    data = res.json()
    assert data["total_matches"] == 1
    assert data["results"][0]["record_id"] == str(task1)

    # Manager 1 attempts to scope to unmanaged team 2 -> 403 Forbidden
    res_denied = client.get(f"/api/search?q=Quantum&team_id={team2['_id']}", headers=headers1)
    assert res_denied.status_code == 403
    assert "do not manage this team" in res_denied.json()["detail"]


def test_admin_organization_wide_read_only_retrieval(client, fake_db):
    admin, admin_token = _create_user(fake_db, "admin@example.com", "admin")
    mgr, _ = _create_user(fake_db, "mgr@example.com", "manager")
    team1 = _create_team(fake_db, "Ops Alpha", mgr["_id"])
    team2 = _create_team(fake_db, "Ops Beta", mgr["_id"])

    t1 = ObjectId()
    fake_db["tasks"].docs.append(
        {
            "_id": t1,
            "title": "Global Backup Architecture",
            "description": "Alpha team backup replication plan.",
            "team_id": team1["_id"],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    t2 = ObjectId()
    fake_db["tasks"].docs.append(
        {
            "_id": t2,
            "title": "Global Storage Architecture",
            "description": "Beta team storage redundancy plan.",
            "team_id": team2["_id"],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    headers = {"Authorization": f"Bearer {admin_token}"}

    # Admin searches organization-wide
    res = client.get("/api/search?q=Global Architecture", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total_matches"] == 2
    matched_ids = {r["record_id"] for r in data["results"]}
    assert str(t1) in matched_ids
    assert str(t2) in matched_ids

    # Admin can also filter by team_id
    res_filtered = client.get(f"/api/search?q=Global&team_id={team1['_id']}", headers=headers)
    assert res_filtered.status_code == 200
    assert res_filtered.json()["total_matches"] == 1
    assert res_filtered.json()["results"][0]["record_id"] == str(t1)


def test_pulse_surveys_never_indexed_or_retrieved(client, fake_db):
    admin, admin_token = _create_user(fake_db, "admin@example.com", "admin")
    emp, emp_token = _create_user(fake_db, "emp@example.com", "employee")

    # Insert private pulse survey responses
    fake_db["weekly_pulse_responses"].docs.append(
        {
            "_id": ObjectId(),
            "user_id": emp["_id"],
            "workload_manageability": 1,
            "work_life_balance": 1,
            "team_support": 1,
            "engagement": 1,
            "optional_comment": "Extremely stressed and completely overwhelmed by project deadlines.",
            "week_start": "2026-09-21T00:00:00Z",
            "submitted_at": datetime.now(timezone.utc),
        }
    )

    # Search using distinct terms from pulse comment as Admin
    res_admin = client.get(
        "/api/search?q=overwhelmed project deadlines",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_admin.status_code == 200
    assert res_admin.json()["total_matches"] == 0

    # Search as Employee
    res_emp = client.get(
        "/api/search?q=overwhelmed project deadlines",
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res_emp.status_code == 200
    assert res_emp.json()["total_matches"] == 0


def test_soft_deleted_messages_hidden_from_users_and_admin_toggle(client, fake_db):
    admin, admin_token = _create_user(fake_db, "admin@example.com", "admin")
    mgr, mgr_token = _create_user(fake_db, "mgr@example.com", "manager")
    team = _create_team(fake_db, "Team Alpha", mgr["_id"])
    emp, emp_token = _create_user(fake_db, "emp@example.com", "employee", team_id=team["_id"])

    msg_deleted = ObjectId()
    fake_db["collaboration_messages"].docs.append(
        {
            "_id": msg_deleted,
            "team_id": team["_id"],
            "sender_id": emp["_id"],
            "content": "Secret discontinued project details that were subsequently deleted.",
            "is_deleted": True,
            "deleted_at": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    # 1. Employee cannot search deleted message
    res_emp = client.get(
        "/api/search?q=discontinued project details",
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res_emp.status_code == 200
    assert res_emp.json()["total_matches"] == 0

    # 2. Manager cannot search deleted message
    res_mgr = client.get(
        "/api/search?q=discontinued project details",
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_mgr.status_code == 200
    assert res_mgr.json()["total_matches"] == 0

    # 3. Admin default (include_deleted=False) hides deleted message
    res_admin_default = client.get(
        "/api/search?q=discontinued project details",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_admin_default.status_code == 200
    assert res_admin_default.json()["total_matches"] == 0

    # 4. Admin with explicit include_deleted=True retrieves the deleted message for audit
    res_admin_audit = client.get(
        "/api/search?q=discontinued project details&include_deleted=true",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_admin_audit.status_code == 200
    assert res_admin_audit.json()["total_matches"] == 1
    assert res_admin_audit.json()["results"][0]["record_id"] == str(msg_deleted)


def test_zero_score_documents_excluded_and_deterministic_tie_breaker(client, fake_db):
    mgr, mgr_token = _create_user(fake_db, "mgr@example.com", "manager")
    team = _create_team(fake_db, "Tiebreaker Team", mgr["_id"])
    emp, emp_token = _create_user(fake_db, "emp@example.com", "employee", team_id=team["_id"])

    t1 = ObjectId("64b1f28b4f1c2b3a4e5d6001")
    t2 = ObjectId("64b1f28b4f1c2b3a4e5d6002")
    unrelated_id = ObjectId()

    now = datetime(2026, 9, 21, 12, 0, 0, tzinfo=timezone.utc)

    # Doc 1
    fake_db["tasks"].docs.append(
        {
            "_id": t1,
            "title": "Refactor microservice architecture",
            "description": "Standardize logging.",
            "team_id": team["_id"],
            "assigned_to": emp["_id"],
            "created_at": now,
            "updated_at": now,
        }
    )

    # Doc 2 (identical match terms, identical score and timestamp)
    fake_db["tasks"].docs.append(
        {
            "_id": t2,
            "title": "Refactor microservice architecture",
            "description": "Standardize logging.",
            "team_id": team["_id"],
            "assigned_to": emp["_id"],
            "created_at": now,
            "updated_at": now,
        }
    )

    # Doc 3 (completely unrelated zero-score document)
    fake_db["tasks"].docs.append(
        {
            "_id": unrelated_id,
            "title": "Unrelated gardening activities",
            "description": "Plants and flowers.",
            "team_id": team["_id"],
            "assigned_to": emp["_id"],
            "created_at": now,
            "updated_at": now,
        }
    )

    headers = {"Authorization": f"Bearer {emp_token}"}
    res = client.get("/api/search?q=microservice architecture", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total_matches"] == 2
    # Unrelated zero-score document must not be present
    result_ids = [r["record_id"] for r in data["results"]]
    assert str(unrelated_id) not in result_ids
    # Deterministic tie-breaker sorts by record_id ascending when score & timestamp are tied
    assert result_ids[0] == str(t1)
    assert result_ids[1] == str(t2)


def test_missing_team_or_user_reference_handled_safely(client, fake_db):
    mgr, mgr_token = _create_user(fake_db, "mgr@example.com", "manager")
    orphan_team_id = ObjectId()

    # Task assigned to a team that was deleted or doesn't exist in teams collection
    fake_db["tasks"].docs.append(
        {
            "_id": ObjectId(),
            "title": "Orphaned Task Record",
            "description": "This task references an unresolvable team ID.",
            "team_id": orphan_team_id,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    admin, admin_token = _create_user(fake_db, "admin@example.com", "admin")
    res = client.get("/api/search?q=Orphaned Record", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["total_matches"] == 1
    assert data["results"][0]["team_name"] is None or data["results"][0]["team_name"] == ""


def test_sanitized_503_database_failure(client, fake_db, monkeypatch):
    emp, emp_token = _create_user(fake_db, "emp@example.com", "employee")

    def broken_find(*args, **kwargs):
        raise PyMongoError("Internal connection failed to mongo-cluster.internal:27017 with credentials user:pass")

    monkeypatch.setattr(fake_db["tasks"], "find", broken_find)

    res = client.get("/api/search?q=database", headers={"Authorization": f"Bearer {emp_token}"})
    assert res.status_code == 503
    assert res.json()["detail"] == "Database unavailable"
    # Ensure no credentials or raw trace leaked
    assert "mongo-cluster" not in res.text
    assert "credentials" not in res.text


def test_search_endpoint_performs_no_mutation(client, fake_db):
    mgr, mgr_token = _create_user(fake_db, "mgr@example.com", "manager")
    team = _create_team(fake_db, "Alpha Team", mgr["_id"])
    emp, emp_token = _create_user(fake_db, "emp@example.com", "employee", team_id=team["_id"])

    task_doc = {
        "_id": ObjectId(),
        "title": "Immutable Verification Task",
        "description": "Checking for read-only guarantees.",
        "team_id": team["_id"],
        "assigned_to": emp["_id"],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    fake_db["tasks"].docs.append(dict(task_doc))

    initial_tasks = [dict(t) for t in fake_db["tasks"].docs]
    initial_messages = [dict(m) for m in fake_db["collaboration_messages"].docs]

    headers = {"Authorization": f"Bearer {emp_token}"}
    res = client.get("/api/search?q=Immutable Verification", headers=headers)
    assert res.status_code == 200

    # Ensure database records were strictly untouched
    assert fake_db["tasks"].docs == initial_tasks
    assert fake_db["collaboration_messages"].docs == initial_messages


def test_source_filtering_tasks_and_collaboration_strictly_isolated(client, fake_db):
    mgr, mgr_token = _create_user(fake_db, "mgr@example.com", "manager")
    team = _create_team(fake_db, "Filter Team", mgr["_id"])
    emp, emp_token = _create_user(fake_db, "emp@example.com", "employee", team_id=team["_id"])

    task_id = ObjectId()
    fake_db["tasks"].docs.append(
        {
            "_id": task_id,
            "title": "TypeScript Migration Project",
            "description": "Convert all components to TypeScript.",
            "team_id": team["_id"],
            "assigned_to": emp["_id"],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    msg_id = ObjectId()
    fake_db["collaboration_messages"].docs.append(
        {
            "_id": msg_id,
            "team_id": team["_id"],
            "sender_id": emp["_id"],
            "content": "TypeScript compiler settings updated in tsconfig.json.",
            "is_deleted": False,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    headers = {"Authorization": f"Bearer {emp_token}"}

    # source=tasks: returns ONLY the task
    res_tasks = client.get("/api/search?q=TypeScript&source=tasks", headers=headers)
    assert res_tasks.status_code == 200
    data_tasks = res_tasks.json()
    assert data_tasks["source"] == "tasks"
    assert data_tasks["total_matches"] == 1
    assert data_tasks["results"][0]["source_type"] == "task"
    assert data_tasks["results"][0]["record_id"] == str(task_id)

    # source=collaboration: returns ONLY the message
    res_msgs = client.get("/api/search?q=TypeScript&source=collaboration", headers=headers)
    assert res_msgs.status_code == 200
    data_msgs = res_msgs.json()
    assert data_msgs["source"] == "collaboration"
    assert data_msgs["total_matches"] == 1
    assert data_msgs["results"][0]["source_type"] == "collaboration"
    assert data_msgs["results"][0]["record_id"] == str(msg_id)

    # source=all: returns BOTH
    res_all = client.get("/api/search?q=TypeScript&source=all", headers=headers)
    assert res_all.status_code == 200
    data_all = res_all.json()
    assert data_all["total_matches"] == 2


def test_task_competency_and_skills_retrieval(client, fake_db):
    mgr, mgr_token = _create_user(fake_db, "mgr@example.com", "manager")
    team = _create_team(fake_db, "Frontend Engineering", mgr["_id"])
    emp, emp_token = _create_user(fake_db, "emp@example.com", "employee", team_id=team["_id"])

    task1 = ObjectId()
    fake_db["tasks"].docs.append(
        {
            "_id": task1,
            "title": "Build Dashboard Component",
            "description": "Create responsive dashboard cards.",
            "team_id": team["_id"],
            "assigned_to": emp["_id"],
            "required_skills": ["WebSockets", "TailwindCSS"],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    task2 = ObjectId()
    fake_db["tasks"].docs.append(
        {
            "_id": task2,
            "title": "Backend Optimization",
            "description": "Async query optimization.",
            "team_id": team["_id"],
            "assigned_to": emp["_id"],
            "required_competencies": ["PyMongoAsync", "DistributedLocking"],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    headers = {"Authorization": f"Bearer {emp_token}"}

    # Verify task1 found via required_skills term
    res1 = client.get("/api/search?q=WebSockets", headers=headers)
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["total_matches"] == 1
    assert data1["results"][0]["record_id"] == str(task1)
    assert "websockets" in data1["results"][0]["matched_terms"]

    # Verify task2 found via required_competencies term
    res2 = client.get("/api/search?q=PyMongoAsync", headers=headers)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["total_matches"] == 1
    assert data2["results"][0]["record_id"] == str(task2)
    assert "pymongoasync" in data2["results"][0]["matched_terms"]


def test_unauthorized_documents_excluded_from_total_candidates(client, fake_db):
    mgr, mgr_token = _create_user(fake_db, "mgr@example.com", "manager")
    team1 = _create_team(fake_db, "Team 1", mgr["_id"])
    team2 = _create_team(fake_db, "Team 2", mgr["_id"])

    emp1, emp1_token = _create_user(fake_db, "emp1@example.com", "employee", team_id=team1["_id"])
    emp2, emp2_token = _create_user(fake_db, "emp2@example.com", "employee", team_id=team2["_id"])

    # 2 tasks for employee 1
    for i in range(2):
        fake_db["tasks"].docs.append(
            {
                "_id": ObjectId(),
                "title": f"Emp1 Task {i}",
                "description": "Work item",
                "team_id": team1["_id"],
                "assigned_to": emp1["_id"],
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        )

    # 1 message in team 1
    fake_db["collaboration_messages"].docs.append(
        {
            "_id": ObjectId(),
            "team_id": team1["_id"],
            "sender_id": emp1["_id"],
            "content": "Team 1 standup message",
            "is_deleted": False,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    # 10 tasks and 10 messages in team 2 (unauthorized for emp 1)
    for i in range(10):
        fake_db["tasks"].docs.append(
            {
                "_id": ObjectId(),
                "title": f"Emp2 Task {i}",
                "description": "Other team work item",
                "team_id": team2["_id"],
                "assigned_to": emp2["_id"],
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        )
        fake_db["collaboration_messages"].docs.append(
            {
                "_id": ObjectId(),
                "team_id": team2["_id"],
                "sender_id": emp2["_id"],
                "content": f"Team 2 chat {i}",
                "is_deleted": False,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        )

    # Total documents in DB = 23.
    # Employee 1 authorized candidate pool = 2 tasks + 1 message = 3 candidates.
    headers = {"Authorization": f"Bearer {emp1_token}"}
    res = client.get("/api/search?q=Work item", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total_candidates"] == 3  # Pre-ranking strictly filtered to 3 candidates!
    assert data["total_matches"] == 2


def test_bm25_duplicate_query_terms_score_invariance(client, fake_db):
    mgr, mgr_token = _create_user(fake_db, "mgr@example.com", "manager")
    team = _create_team(fake_db, "Search Team", mgr["_id"])
    emp, emp_token = _create_user(fake_db, "emp@example.com", "employee", team_id=team["_id"])

    task_id = ObjectId()
    fake_db["tasks"].docs.append(
        {
            "_id": task_id,
            "title": "PostgreSQL Performance Tuning",
            "description": "Optimize query plans and indexes.",
            "team_id": team["_id"],
            "assigned_to": emp["_id"],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    headers = {"Authorization": f"Bearer {emp_token}"}
    res1 = client.get("/api/search?q=PostgreSQL", headers=headers)
    assert res1.status_code == 200
    score1 = res1.json()["results"][0]["score"]

    # Repeated query term must not artificially inflate the score
    res2 = client.get("/api/search?q=PostgreSQL PostgreSQL", headers=headers)
    assert res2.status_code == 200
    score2 = res2.json()["results"][0]["score"]

    assert score1 == score2
    assert res2.json()["results"][0]["matched_terms"] == ["postgresql"]


def test_unassigned_employee_and_manager_without_teams_handled_cleanly(client, fake_db):
    unassigned_emp, emp_token = _create_user(fake_db, "unassigned@example.com", "employee", team_id=None)
    headers_emp = {"Authorization": f"Bearer {emp_token}"}

    # Unassigned employee searching messages returns 0 candidates cleanly
    res_emp = client.get("/api/search?q=Sprint planning&source=collaboration", headers=headers_emp)
    assert res_emp.status_code == 200
    assert res_emp.json()["total_candidates"] == 0
    assert res_emp.json()["total_matches"] == 0

    # Manager without any teams returns 0 candidates cleanly
    teamless_mgr, mgr_token = _create_user(fake_db, "teamless_mgr@example.com", "manager")
    headers_mgr = {"Authorization": f"Bearer {mgr_token}"}
    res_mgr = client.get("/api/search?q=Sprint planning", headers=headers_mgr)
    assert res_mgr.status_code == 200
    assert res_mgr.json()["total_candidates"] == 0
    assert res_mgr.json()["total_matches"] == 0


def test_e2e_task_workflow_blocker_resolution_and_progress_retrieval(client, fake_db):
    """
    Integration regression test:
    - creates a task using the existing task workflow / data contract,
    - logs a progress update with unique note text,
    - reports a blocker through existing task behavior,
    - resolves the blocker through existing blocker resolution behavior,
    - searches for unique terms in resolution_note, progress notes, and blocker description,
    - verifies GET /api/search returns the task with accurate snippets and matched terms.
    """
    mgr, mgr_token = _create_user(fake_db, "flow_mgr@example.com", "manager")
    team = _create_team(fake_db, "Telemetry Squad", mgr["_id"])
    emp, emp_token = _create_user(fake_db, "flow_emp@example.com", "employee", team_id=team["_id"])

    # 1. Manager creates task
    res_create = client.post(
        "/tasks",
        json={
            "title": "Pipeline Telemetry Migration",
            "description": "Port telemetry event stream to new cluster.",
            "team_id": str(team["_id"]),
            "assigned_to": str(emp["_id"]),
            "priority": "high",
            "required_skills": ["Telemetry", "EventStream"],
        },
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_create.status_code == 201
    task_id = res_create.json()["id"]

    # 2. Employee logs progress with unique progress note
    res_prog = client.post(
        f"/tasks/{task_id}/progress",
        json={
            "percentage": 35,
            "notes": "Configured telemetry buffer ingestion parameters.",
        },
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res_prog.status_code == 200

    # 3. Employee reports blocker with unique blocker description
    res_block = client.post(
        f"/tasks/{task_id}/blockers",
        json={"description": "Encountered deadlock on checkpoint ledger partition."},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res_block.status_code == 200
    blockers = res_block.json()["blockers"]
    assert len(blockers) == 1
    blocker_id = blockers[0]["id"]

    # 4. Manager resolves blocker with unique resolution note
    res_resolve = client.patch(
        f"/tasks/{task_id}/blockers/{blocker_id}/resolve",
        json={"resolution_note": "Rebalanced partition consumers and cleared deadlock lockfiles."},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_resolve.status_code == 200
    assert res_resolve.json()["blockers"][0]["resolution_note"] == "Rebalanced partition consumers and cleared deadlock lockfiles."

    # 5. Search for unique word from resolution_note: "lockfiles"
    res_search_res = client.get(
        "/api/search?q=lockfiles",
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res_search_res.status_code == 200
    data_res = res_search_res.json()
    assert data_res["total_matches"] == 1
    assert data_res["results"][0]["record_id"] == task_id
    assert "lockfiles" in data_res["results"][0]["snippet"]
    assert "lockfiles" in data_res["results"][0]["matched_terms"]

    # 6. Search for unique word from progress note: "ingestion"
    res_search_prog = client.get(
        "/api/search?q=ingestion",
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res_search_prog.status_code == 200
    data_prog = res_search_prog.json()
    assert data_prog["total_matches"] == 1
    assert data_prog["results"][0]["record_id"] == task_id
    assert "ingestion" in data_prog["results"][0]["matched_terms"]

    # 7. Search for unique word from blocker description: "ledger"
    res_search_block = client.get(
        "/api/search?q=ledger",
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert res_search_block.status_code == 200
    data_block = res_search_block.json()
    assert data_block["total_matches"] == 1
    assert data_block["results"][0]["record_id"] == task_id
    assert "ledger" in data_block["results"][0]["matched_terms"]


def test_builder_canonical_blocker_resolution_priority():
    """Verify build_task_document prioritizes canonical singular resolution_note over legacy resolution_notes."""
    # Canonical only
    doc_canonical = {
        "_id": ObjectId(),
        "title": "Canonical Task",
        "description": "Desc",
        "blockers": [
            {
                "description": "Blocker Desc",
                "resolution_note": "Canonical Resolution Value",
            }
        ],
    }
    task_doc1 = build_task_document(doc_canonical)
    assert "canonical" in task_doc1.tokens
    assert "resolution" in task_doc1.tokens
    assert "value" in task_doc1.tokens

    # Priority when both exist (canonical wins)
    doc_both = {
        "_id": ObjectId(),
        "title": "Both Task",
        "description": "Desc",
        "blockers": [
            {
                "description": "Blocker Desc",
                "resolution_note": "CanonicalWins",
                "resolution_notes": "LegacyPlural",
            }
        ],
    }
    task_doc2 = build_task_document(doc_both)
    assert "canonicalwins" in task_doc2.tokens
    assert "legacyplural" not in task_doc2.tokens
