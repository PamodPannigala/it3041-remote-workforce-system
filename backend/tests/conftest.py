import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

from backend.app.main import app


TEST_JWT_SECRET = "test-secret-key-that-is-at-least-32-bytes-long-for-hs256-testing!!"


def _matches_filter(doc: dict, filter_query: dict | None) -> bool:
    if not filter_query:
        return True
    for k, v in filter_query.items():
        doc_val = doc.get(k)
        if isinstance(v, dict):
            if "$in" in v:
                if doc_val not in v["$in"]:
                    return False
            elif "$ne" in v:
                if doc_val == v["$ne"]:
                    return False
        else:
            if doc_val != v:
                return False
    return True


class FakeAsyncCursor:
    def __init__(self, docs: list):
        self._docs = list(docs)
        self._skip = 0
        self._limit = None

    def sort(self, key_or_list, direction=1):
        if isinstance(key_or_list, str):
            sort_fields = [(key_or_list, direction)]
        elif isinstance(key_or_list, (list, tuple)):
            sort_fields = list(key_or_list)
        else:
            return self

        for field, order in reversed(sort_fields):
            reverse = order == -1 or order == "desc" or order == "DESC"
            self._docs.sort(
                key=lambda d: (
                    (d.get(field) is not None),
                    str(d.get(field)) if d.get(field) is not None else "",
                ),
                reverse=reverse,
            )
        return self

    def skip(self, count: int):
        self._skip = count
        return self

    def limit(self, count: int):
        self._limit = count
        return self

    def _get_sliced(self):
        sliced = self._docs[self._skip:]
        if self._limit is not None:
            sliced = sliced[:self._limit]
        return sliced

    async def to_list(self, length: int | None = None):
        res = self._get_sliced()
        if length is not None:
            res = res[:length]
        return res

    def __aiter__(self):
        async def gen():
            for doc in self._get_sliced():
                yield doc
        return gen()


class FakeAsyncCollection:
    def __init__(self, name: str):
        self.name = name
        self.docs = []
        self.indexes = {}

    async def create_index(self, key, unique: bool = False):
        if isinstance(key, list):
            key = tuple(key)
        self.indexes[key] = {"unique": unique}

    async def count_documents(self, filter_query: dict | None = None) -> int:
        return sum(1 for doc in self.docs if _matches_filter(doc, filter_query))

    async def find_one(self, filter_query=None, projection=None):
        for doc in self.docs:
            if _matches_filter(doc, filter_query):
                return doc
        return None

    def find(self, filter_query=None, projection=None):
        matching = [doc for doc in self.docs if _matches_filter(doc, filter_query)]
        return FakeAsyncCursor(matching)

    async def insert_one(self, doc: dict):
        # Check unique indexes
        for idx_key, idx_meta in self.indexes.items():
            if idx_meta.get("unique"):
                if isinstance(idx_key, (tuple, list)):
                    field_names = [k[0] if isinstance(k, (tuple, list)) else k for k in idx_key]
                    doc_vals = tuple(doc.get(f) for f in field_names)
                    if all(v is not None for v in doc_vals):
                        for existing in self.docs:
                            existing_vals = tuple(existing.get(f) for f in field_names)
                            if existing_vals == doc_vals:
                                raise DuplicateKeyError(
                                    f"E11000 duplicate key error collection: test.{self.name} index: {idx_key} dup key: {dict(zip(field_names, doc_vals))}"
                                )
                else:
                    val = doc.get(idx_key)
                    if val is not None:
                        for existing in self.docs:
                            if existing.get(idx_key) == val:
                                raise DuplicateKeyError(
                                    f"E11000 duplicate key error collection: test.{self.name} index: {idx_key} dup key: {{ {idx_key}: '{val}' }}"
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

    async def delete_one(self, filter_query: dict):
        for idx, doc in enumerate(self.docs):
            if _matches_filter(doc, filter_query):
                self.docs.pop(idx)
                break


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
    db["teams"].indexes["name"] = {"unique": True}
    db["employee_profiles"].indexes["user_id"] = {"unique": True}
    db["tasks"].indexes[tuple([("team_id", 1), ("status", 1)])] = {"unique": False}
    db["tasks"].indexes[tuple([("assigned_to", 1), ("status", 1)])] = {"unique": False}
    db["tasks"].indexes["due_date"] = {"unique": False}
    db["collaboration_messages"].indexes[tuple([("team_id", 1), ("created_at", -1)])] = {"unique": False}
    db["collaboration_messages"].indexes[tuple([("sender_id", 1), ("created_at", -1)])] = {"unique": False}
    db["weekly_pulse_responses"].indexes[tuple([("user_id", 1), ("week_start", -1)])] = {"unique": True}
    db["weekly_pulse_responses"].indexes[tuple([("team_id", 1), ("week_start", -1)])] = {"unique": False}
    return db





@pytest.fixture
def test_setup(fake_db):
    app.state.database = fake_db
    client = TestClient(app)
    return client, fake_db
