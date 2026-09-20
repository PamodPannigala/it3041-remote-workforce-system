import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

from main import app


TEST_JWT_SECRET = "test-secret-key-that-is-at-least-32-bytes-long-for-hs256-testing!!"


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

    async def update_one(self, filter_query: dict, update_query: dict):
        doc = await self.find_one(filter_query)
        if doc and "$set" in update_query:
            for k, v in update_query["$set"].items():
                doc[k] = v


class FakeAsyncDatabase:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name: str):
        if name not in self.collections:
            self.collections[name] = FakeAsyncCollection(name)
        return self.collections[name]

    async def command(self, cmd):
        return {"ok": 1}


@pytest.fixture(autouse=True)
def isolated_jwt_secret(monkeypatch):
    # Ensure tests always run with an isolated test JWT secret
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)


@pytest.fixture
def fake_db():
    db = FakeAsyncDatabase()
    db["users"].indexes["email"] = {"unique": True}
    return db


@pytest.fixture
def test_setup(fake_db):
    app.state.database = fake_db
    client = TestClient(app)
    return client, fake_db
