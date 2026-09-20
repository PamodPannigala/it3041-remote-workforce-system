import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError


load_dotenv(Path(__file__).parent / ".env", encoding="utf-8-sig")


async def main():
    required = [
        "MONGODB_HOST",
        "MONGODB_USERNAME",
        "MONGODB_PASSWORD",
        "MONGODB_DATABASE",
    ]

    missing = [key for key in required if not os.getenv(key)]
    if missing:
        print("Missing settings:", ", ".join(missing))
        return

    client = None

    try:
        client = AsyncMongoClient(
            f"mongodb+srv://{os.environ['MONGODB_HOST']}/",
            username=os.environ["MONGODB_USERNAME"],
            password=os.environ["MONGODB_PASSWORD"],
            authSource="admin",
            serverSelectionTimeoutMS=10000,
            connectTimeoutMS=10000,
        )

        await client.admin.command("ping")
        print("PASS: MongoDB connection")

        database = client[os.environ["MONGODB_DATABASE"]]
        await database["users"].find_one({}, {"_id": 1})
        print("PASS: Database read access")

    except PyMongoError as error:
        print("FAIL:", type(error).__name__)
        print("Error code:", getattr(error, "code", None))

    finally:
        if client is not None:
            await client.close()


if __name__ == "__main__":
    asyncio.run(main())
