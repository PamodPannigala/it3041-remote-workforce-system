import asyncio
import getpass
import sys
from datetime import datetime, timezone

from pydantic import BaseModel, EmailStr, Field, SecretStr, ValidationError
from pymongo.errors import DuplicateKeyError, PyMongoError

from backend.app.db.database import create_database_client
from backend.app.core.security import hash_password


class AdminBootstrapModel(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: SecretStr = Field(min_length=15, max_length=128)


async def bootstrap_admin(
    name: str,
    email: str,
    password: str,
    database=None,
) -> dict:
    """Core bootstrap logic that can be run against a provided database or live DB."""
    email_clean = email.strip().lower()
    name_clean = name.strip()

    try:
        validated = AdminBootstrapModel(
            name=name_clean,
            email=email_clean,
            password=password,
        )
    except ValidationError as e:
        error_msgs = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
        raise ValueError("; ".join(error_msgs)) from e

    # Check if any admin already exists in the database
    existing_admin = await database["users"].find_one({"role": "admin"})
    if existing_admin:
        raise PermissionError(
            "Bootstrap refused: An administrator account already exists."
        )

    # Check if a user with this email already exists
    existing_user = await database["users"].find_one({"email": email_clean})
    if existing_user:
        raise ValueError(
            "Account creation failed: An account with this email already exists."
        )

    hashed_pw = hash_password(validated.password.get_secret_value())

    admin_doc = {
        "name": validated.name,
        "email": email_clean,
        "password_hash": hashed_pw,
        "role": "admin",
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }

    try:
        result = await database["users"].insert_one(admin_doc)
        admin_doc["_id"] = result.inserted_id
    except DuplicateKeyError:
        raise ValueError(
            "Account creation failed: An account with this email already exists."
        ) from None
    except PyMongoError as e:
        raise RuntimeError(f"Database error during admin bootstrap: {e}") from e

    return {
        "id": str(admin_doc["_id"]),
        "name": admin_doc["name"],
        "email": admin_doc["email"],
        "role": admin_doc["role"],
    }


async def main():
    print("=== Remote Workforce System: Initial Admin Setup ===")
    print("This command creates the bootstrap administrator account.")
    print("It will be refused if an admin account already exists.\n")

    try:
        name = input("Admin Full Name: ").strip()
        email = input("Admin Email Address: ").strip()
        password = getpass.getpass("Admin Password (min 15 characters): ")
        confirm_password = getpass.getpass("Confirm Admin Password: ")
    except (KeyboardInterrupt, EOFError):
        print("\nOperation cancelled by user.")
        sys.exit(1)

    if not name:
        print("Error: Name cannot be empty.")
        sys.exit(1)

    if password != confirm_password:
        print("Error: Passwords do not match.")
        sys.exit(1)

    try:
        client, database = create_database_client()
    except Exception as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)

    try:
        created = await bootstrap_admin(
            name=name,
            email=email,
            password=password,
            database=database,
        )
        print("\n✓ Initial admin account created successfully!")
        print(f"  ID:    {created['id']}")
        print(f"  Name:  {created['name']}")
        print(f"  Email: {created['email']}")
        print(f"  Role:  {created['role']}")
    except (ValueError, PermissionError) as e:
        print(f"\nError: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
