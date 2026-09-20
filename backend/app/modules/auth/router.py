from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pymongo.errors import DuplicateKeyError, PyMongoError
from starlette.concurrency import run_in_threadpool

from backend.app.api.dependencies import get_current_user
from backend.app.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from backend.app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    hash_password,
    verify_password,
)


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(payload: RegisterRequest, request: Request):
    database = request.app.state.database

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
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from None
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account creation is temporarily unavailable",
        ) from None

    return UserResponse(
        id=str(result.inserted_id),
        name=user["name"],
        email=user["email"],
        role=user["role"],
        is_active=user["is_active"],
        team_id=None,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
async def login(payload: LoginRequest, request: Request, response: Response):
    database = request.app.state.database
    email = str(payload.email).lower()

    user = await database["users"].find_one({"email": email})

    if not user:
        # Run dummy hash verification to mitigate timing differences for non-existent users
        await run_in_threadpool(
            verify_password,
            payload.password.get_secret_value(),
            DUMMY_PASSWORD_HASH,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    is_valid = await run_in_threadpool(
        verify_password,
        payload.password.get_secret_value(),
        user.get("password_hash", ""),
    )

    if not is_valid or not user.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token, expires_in = create_access_token(str(user["_id"]))
    response.headers["Cache-Control"] = "no-store"

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
)
async def get_my_profile(current_user: dict = Depends(get_current_user)):
    return UserResponse(
        id=str(current_user["_id"]),
        name=current_user["name"],
        email=current_user["email"],
        role=current_user["role"],
        is_active=current_user.get("is_active", True),
        team_id=str(current_user["team_id"]) if current_user.get("team_id") else None,
    )
