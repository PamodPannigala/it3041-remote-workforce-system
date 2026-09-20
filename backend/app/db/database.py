import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import AsyncMongoClient


def create_database_client():
    load_dotenv(
        Path(__file__).resolve().parent.parent.parent / ".env",
        encoding="utf-8-sig",
    )

    required = [
        "MONGODB_HOST",
        "MONGODB_USERNAME",
        "MONGODB_PASSWORD",
        "MONGODB_DATABASE",
    ]

    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError(
            "Missing database settings: " + ", ".join(missing)
        )

    client = AsyncMongoClient(
        f"mongodb+srv://{os.environ['MONGODB_HOST']}/",
        username=os.environ["MONGODB_USERNAME"],
        password=os.environ["MONGODB_PASSWORD"],
        authSource="admin",
        serverSelectionTimeoutMS=10000,
        connectTimeoutMS=10000,
        socketTimeoutMS=10000,
    )

    database = client[os.environ["MONGODB_DATABASE"]]
    return client, database
