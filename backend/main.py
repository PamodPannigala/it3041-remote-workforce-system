from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from pymongo.errors import PyMongoError

from database import create_database_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    client, database = create_database_client()

    try:
        try:
            await client.admin.command("ping")
            await database["users"].find_one({}, {"_id": 1})
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