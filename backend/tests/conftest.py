import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

from main import app


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

    async def create_index(self, key: str, unique: bool = False):
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
    return db


@pytest.fixture
def test_setup(fake_db):
    app.state.database = fake_db
    client = TestClient(app)
    return client, fake_db
