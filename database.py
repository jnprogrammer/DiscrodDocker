import aiosqlite
from typing import Optional, List, Dict
from datetime import datetime, timedelta


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
            await db.execute("""
                CREATE TABLE IF NOT EXISTS terminal_tokens (
                    container_id TEXT PRIMARY KEY,
                    token TEXT NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    FOREIGN KEY(container_id) REFERENCES containers(container_id) ON DELETE CASCADE
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

    async def store_terminal_token(self, container_id: str, token: str, expiry: int = 3600):
        """Store or update a terminal token for a container."""
        expires_at = (datetime.utcnow() + timedelta(seconds=expiry)).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO terminal_tokens (container_id, token, expires_at)
                VALUES (?, ?, ?)
                ON CONFLICT(container_id) DO UPDATE SET token = excluded.token, expires_at = excluded.expires_at
            """, (container_id, token, expires_at))
            await db.commit()

    async def get_terminal_token(self, container_id: str) -> Optional[Dict]:
        """Retrieve a valid terminal token for a container."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT token, expires_at FROM terminal_tokens WHERE container_id = ?",
                (container_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None

                if datetime.fromisoformat(row["expires_at"]) < datetime.utcnow():
                    await self.delete_terminal_token(container_id)
                    return None

                return {
                    "token": row["token"],
                    "expires_at": row["expires_at"]
                }

    async def delete_terminal_token(self, container_id: str):
        """Remove a terminal token for a container."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM terminal_tokens WHERE container_id = ?",
                (container_id,)
            )
            await db.commit()

