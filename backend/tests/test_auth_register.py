import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

from main import app
from security import verify_password


class FakeAsyncCollection:
    def __init__(self, name: str):
        self.name = name
        self.docs = []
        self.indexes = {}

    async def create_index(self, key: str, unique: bool = False):
        self.indexes[key] = {"unique": unique}

    async def find_one(self, filter_query=None, projection=None):
        if not filter_query:
            return self.docs[0] if self.docs else None
        for doc in self.docs:
            match = True
            for k, v in filter_query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                return doc
        return None

    async def insert_one(self, doc: dict):
        if "email" in self.indexes and self.indexes["email"].get("unique"):
            email_val = doc.get("email")
            for existing in self.docs:
                if existing.get("email") == email_val:
                    raise DuplicateKeyError(
                        f"E11000 duplicate key error collection: test.{self.name} index: email dup key: {{ email: '{email_val}' }}"
                    )

        doc_copy = dict(doc)
        if "_id" not in doc_copy:
            doc_copy["_id"] = ObjectId()
        self.docs.append(doc_copy)

        class InsertResult:
            def __init__(self, inserted_id):
                self.inserted_id = inserted_id

        return InsertResult(doc_copy["_id"])


class FakeAsyncDatabase:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name: str):
        if name not in self.collections:
            self.collections[name] = FakeAsyncCollection(name)
        return self.collections[name]

    async def command(self, cmd):
        return {"ok": 1}


@pytest.fixture
def test_setup():
    fake_db = FakeAsyncDatabase()
    # Configure unique index on email
    fake_db["users"].indexes["email"] = {"unique": True}
    app.state.database = fake_db

    client = TestClient(app)
    return client, fake_db


def test_valid_registration(test_setup):
    client, fake_db = test_setup
    payload = {
        "name": "Jane Developer",
        "email": "jane.dev@example.com",
        "password": "SecurePassword123!#$",
    }
    response = client.post("/auth/register", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Jane Developer"
    assert data["email"] == "jane.dev@example.com"
    assert data["role"] == "employee"
    assert "id" in data
    assert "password" not in data
    assert "password_hash" not in data

    # Verify stored record in database
    users = fake_db["users"].docs
    assert len(users) == 1
    stored = users[0]
    assert stored["email"] == "jane.dev@example.com"
    assert stored["role"] == "employee"
    assert stored["is_active"] is True
    assert "password" not in stored
    assert "password_hash" in stored
    assert verify_password(payload["password"], stored["password_hash"])


def test_duplicate_email_rejected(test_setup):
    client, fake_db = test_setup
    payload = {
        "name": "User One",
        "email": "duplicate@example.com",
        "password": "Password123456789!",
    }
    first_response = client.post("/auth/register", json=payload)
    assert first_response.status_code == 201

    # Attempt second registration with same email
    second_response = client.post(
        "/auth/register",
        json={
            "name": "User Two",
            "email": "duplicate@example.com",
            "password": "DifferentPassword123!",
        },
    )
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "An account with this email already exists"
    assert len(fake_db["users"].docs) == 1


def test_email_case_insensitivity(test_setup):
    client, fake_db = test_setup
    first_payload = {
        "name": "Case Sensitive User",
        "email": "alex.smith@example.com",
        "password": "ValidPassword98765!",
    }
    res1 = client.post("/auth/register", json=first_payload)
    assert res1.status_code == 201

    # Attempt registration with upper/mixed case variant
    second_payload = {
        "name": "Case Sensitive Clone",
        "email": "ALEX.SMITH@EXAMPLE.COM",
        "password": "ValidPassword98765!",
    }
    res2 = client.post("/auth/register", json=second_payload)
    assert res2.status_code == 409
    assert len(fake_db["users"].docs) == 1


def test_extra_role_field_forbidden(test_setup):
    client, fake_db = test_setup
    payload = {
        "name": "Attacker",
        "email": "attacker@example.com",
        "password": "AdminPassword1234!",
        "role": "admin",
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 422
    assert len(fake_db["users"].docs) == 0


def test_short_password_rejected(test_setup):
    client, fake_db = test_setup
    secret_password = "short-secret"
    payload = {
        "name": "Short Pwd",
        "email": "short@example.com",
        "password": secret_password,
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 422
    # Ensure submitted password is not leaked in error response
    response_text = response.text
    assert secret_password not in response_text
    assert len(fake_db["users"].docs) == 0


def test_invalid_email_rejected(test_setup):
    client, fake_db = test_setup
    payload = {
        "name": "Invalid Email",
        "email": "not-an-email",
        "password": "ValidPassword12345!",
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 422
    assert len(fake_db["users"].docs) == 0


def test_empty_or_whitespace_name_rejected(test_setup):
    client, fake_db = test_setup
    payload = {
        "name": "   ",
        "email": "spaces@example.com",
        "password": "ValidPassword12345!",
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 422
    assert len(fake_db["users"].docs) == 0
