import aiosqlite
from typing import Optional, List, Dict
from datetime import datetime


class ContainerDB:
    def __init__(self, db_path: str = "containers.db"):
        self.db_path = db_path

    async def init_db(self):
        """Initialize the database and create tables."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS containers (
                    discord_user_id TEXT PRIMARY KEY,
                    container_name TEXT NOT NULL,
                    container_id TEXT NOT NULL UNIQUE,
                    image TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
            """)
            await db.commit()

    async def get_container_by_user(self, discord_user_id: str) -> Optional[Dict]:
        """Get container information for a Discord user."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM containers WHERE discord_user_id = ?",
                (discord_user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "discord_user_id": row["discord_user_id"],
                        "container_name": row["container_name"],
                        "container_id": row["container_id"],
                        "image": row["image"],
                        "created_at": row["created_at"]
                    }
                return None

    async def get_container_by_container_id(self, container_id: str) -> Optional[Dict]:
        """Get container information by container ID."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM containers WHERE container_id = ?",
                (container_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "discord_user_id": row["discord_user_id"],
                        "container_name": row["container_name"],
                        "container_id": row["container_id"],
                        "image": row["image"],
                        "created_at": row["created_at"]
                    }
                return None

    async def create_container_record(
        self,
        discord_user_id: str,
        container_name: str,
        container_id: str,
        image: str
    ):
        """Create a new container record."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO containers (discord_user_id, container_name, container_id, image, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (discord_user_id, container_name, container_id, image, datetime.utcnow().isoformat()))
            await db.commit()

    async def delete_container_record(self, discord_user_id: str):
        """Delete a container record."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM containers WHERE discord_user_id = ?",
                (discord_user_id,)
            )
            await db.commit()

    async def get_all_containers(self) -> List[Dict]:
        """Get all container records."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM containers") as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        "discord_user_id": row["discord_user_id"],
                        "container_name": row["container_name"],
                        "container_id": row["container_id"],
                        "image": row["image"],
                        "created_at": row["created_at"]
                    }
                    for row in rows
                ]

