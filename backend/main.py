from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from database import create_database_client
from dependencies import require_roles
from security import get_jwt_secret_key
from auth import router as auth_router
from admin import router as admin_router
from teams import router as teams_router
from profiles import router as profiles_router
from tasks import router as tasks_router, admin_tasks_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Verify JWT signing key is available at startup
    try:
        get_jwt_secret_key()
    except Exception:
        raise RuntimeError("Startup failed: missing or invalid JWT signing configuration") from None

    client, database = create_database_client()

    try:
        try:
            await client.admin.command("ping")
            await database["users"].find_one({}, {"_id": 1})
            await database["users"].create_index("email", unique=True)
            await database["teams"].create_index("name", unique=True)
            await database["employee_profiles"].create_index("user_id", unique=True)
            await database["tasks"].create_index([("team_id", 1), ("status", 1)])
            await database["tasks"].create_index([("assigned_to", 1), ("status", 1)])
            await database["tasks"].create_index("due_date")
        except PyMongoError:
            raise RuntimeError(
                "Database startup check failed"
            ) from None

        app.state.database = database
        print("MongoDB connected")

        yield
    finally:
        await client.close()


app = FastAPI(
    title="Remote Workforce API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    sanitized_errors = []
    for err in exc.errors():
        error_info = {
            "loc": err.get("loc"),
            "msg": err.get("msg"),
            "type": err.get("type"),
        }
        if "ctx" in err:
            ctx_clean = {}
            for k, val in err["ctx"].items():
                if isinstance(val, Exception):
                    ctx_clean[k] = str(val)
                else:
                    ctx_clean[k] = val
            error_info["ctx"] = ctx_clean
        sanitized_errors.append(error_info)
    return JSONResponse(status_code=422, content={"detail": sanitized_errors})


app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(admin_tasks_router)
app.include_router(teams_router)
app.include_router(profiles_router)
app.include_router(tasks_router)




@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/health/db")
async def database_health(request: Request):
    try:
        await request.app.state.database.command("ping")
    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from None

    return {"status": "ok", "database": "connected"}


@app.get("/admin/access-check", dependencies=[Depends(require_roles("admin"))])
def admin_access_check():
    return {"status": "ok", "access": "admin"}


@app.get(
    "/management/access-check",
    dependencies=[Depends(require_roles("manager", "admin"))],
)
def management_access_check():
    return {"status": "ok", "access": "management"}