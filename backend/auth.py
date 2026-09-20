from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pymongo.errors import DuplicateKeyError, PyMongoError
from starlette.concurrency import run_in_threadpool

from schemas import RegisterRequest, UserResponse
from security import hash_password


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=201,
)
async def register(payload: RegisterRequest, request: Request):
    database = request.app.state.database

    # Our app treats email addresses as case-insensitive.
    email = str(payload.email).lower()

    hashed_password = await run_in_threadpool(
        hash_password,
        payload.password.get_secret_value(),
    )

    user = {
        "name": payload.name,
        "email": email,
        "password_hash": hashed_password,
        "role": "employee",
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }

    try:
        result = await database["users"].insert_one(user)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists",
        ) from None
    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="Account creation is temporarily unavailable",
        ) from None

    return UserResponse(
        id=str(result.inserted_id),
        name=user["name"],
        email=user["email"],
        role=user["role"],
    )