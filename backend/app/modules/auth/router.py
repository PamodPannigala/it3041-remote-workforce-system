import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pymongo import ReturnDocument
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
from backend.app.modules.auth.constants import (
    ACCOUNT_LOCKOUT_MINUTES,
    AUTH_RATE_LIMIT,
    MAX_FAILED_LOGIN_ATTEMPTS,
)
from backend.app.core.rate_limiting import limiter


router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def _record_failed_login(database, user: dict, email: str) -> None:
    users = database["users"]
    while True:
        current = await users.find_one({"_id": user["_id"]})
        if current is None:
            return

        failed_attempts = int(current.get("failed_login_attempts", 0))
        next_attempts = failed_attempts + 1
        now = datetime.now(timezone.utc)
        update_fields = {"failed_login_attempts": next_attempts}
        if next_attempts >= MAX_FAILED_LOGIN_ATTEMPTS:
            locked_until = now + timedelta(minutes=ACCOUNT_LOCKOUT_MINUTES)
            update_fields["locked_until"] = locked_until

        if "failed_login_attempts" in current:
            compare_filter = {"failed_login_attempts": failed_attempts}
        else:
            compare_filter = {"failed_login_attempts": {"$exists": False}}

        updated = await users.find_one_and_update(
            {"_id": user["_id"], **compare_filter},
            {"$set": update_fields},
            return_document=ReturnDocument.AFTER,
        )
        if updated is not None:
            if next_attempts == MAX_FAILED_LOGIN_ATTEMPTS:
                logger.warning(
                    "Account login lockout activated for email=%s until=%s",
                    email,
                    locked_until.isoformat(),
                )
            return


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(AUTH_RATE_LIMIT)
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
@limiter.limit(AUTH_RATE_LIMIT)
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

    now = datetime.now(timezone.utc)
    locked_until = user.get("locked_until")
    if isinstance(locked_until, datetime):
        locked_until = _as_utc(locked_until)
        if locked_until > now:
            await run_in_threadpool(
                verify_password,
                payload.password.get_secret_value(),
                user.get("password_hash", ""),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        await database["users"].update_one(
            {"_id": user["_id"], "locked_until": user.get("locked_until")},
            {"$set": {"failed_login_attempts": 0, "locked_until": None}},
        )
        user["failed_login_attempts"] = 0
        user["locked_until"] = None

    is_valid = await run_in_threadpool(
        verify_password,
        payload.password.get_secret_value(),
        user.get("password_hash", ""),
    )

    if not is_valid or not user.get("is_active", False):
        await _record_failed_login(database, user, email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    await database["users"].update_one(
        {"_id": user["_id"]},
        {"$set": {"failed_login_attempts": 0, "locked_until": None}},
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
