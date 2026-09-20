from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from database import create_database_client
from auth import router as auth_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    client, database = create_database_client()

    try:
        try:
            await client.admin.command("ping")
            await database["users"].find_one({}, {"_id": 1})
            await database["users"].create_index("email", unique=True)
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
            error_info["ctx"] = err["ctx"]
        sanitized_errors.append(error_info)
    return JSONResponse(status_code=422, content={"detail": sanitized_errors})


app.include_router(auth_router)

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