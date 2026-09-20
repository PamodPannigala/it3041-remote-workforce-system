import pytest
from bson import ObjectId

from backend.scripts.create_admin import bootstrap_admin
from backend.app.core.security import verify_password
from backend.tests.conftest import FakeAsyncDatabase



@pytest.mark.asyncio
async def test_bootstrap_admin_success():
    db = FakeAsyncDatabase()
    db["users"].indexes["email"] = {"unique": True}

    result = await bootstrap_admin(
        name="Super Admin",
        email="admin@example.com",
        password="SuperSecretPassword123!",
        database=db,
    )

    assert result["name"] == "Super Admin"
    assert result["email"] == "admin@example.com"
    assert result["role"] == "admin"
    assert "password" not in result
    assert "password_hash" not in result

    # Check database record
    user_in_db = await db["users"].find_one({"email": "admin@example.com"})
    assert user_in_db is not None
    assert user_in_db["role"] == "admin"
    assert user_in_db["is_active"] is True
    assert verify_password("SuperSecretPassword123!", user_in_db["password_hash"])


@pytest.mark.asyncio
async def test_bootstrap_admin_refuses_when_admin_exists():
    db = FakeAsyncDatabase()
    db["users"].indexes["email"] = {"unique": True}

    # Pre-create an admin
    db["users"].docs.append({
        "_id": ObjectId(),
        "name": "Existing Admin",
        "email": "existing.admin@example.com",
        "password_hash": "dummyhash",
        "role": "admin",
        "is_active": True,
    })

    with pytest.raises(PermissionError) as exc_info:
        await bootstrap_admin(
            name="Second Admin",
            email="second.admin@example.com",
            password="AnotherPassword123!",
            database=db,
        )

    assert "refused" in str(exc_info.value).lower()
    assert "already exists" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_bootstrap_admin_refuses_duplicate_email():
    db = FakeAsyncDatabase()
    db["users"].indexes["email"] = {"unique": True}

    # Pre-create an employee with email
    db["users"].docs.append({
        "_id": ObjectId(),
        "name": "Employee John",
        "email": "john@example.com",
        "password_hash": "dummyhash",
        "role": "employee",
        "is_active": True,
    })

    with pytest.raises(ValueError) as exc_info:
        await bootstrap_admin(
            name="John Admin",
            email="john@example.com",
            password="AnotherPassword123!",
            database=db,
        )

    assert "already exists" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_bootstrap_admin_password_validation():
    db = FakeAsyncDatabase()
    db["users"].indexes["email"] = {"unique": True}

    # Short password (< 15 chars)
    with pytest.raises(ValueError) as exc_info:
        await bootstrap_admin(
            name="Short Pass Admin",
            email="short@example.com",
            password="short",
            database=db,
        )
    assert "password" in str(exc_info.value).lower()
