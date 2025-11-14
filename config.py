import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
AUTHORIZED_USERS = [
    user_id.strip()
    for user_id in os.getenv("AUTHORIZED_USERS", "").split(",")
    if user_id.strip()
]
TERMINAL_SERVICE_URL = os.getenv("TERMINAL_SERVICE_URL", "http://localhost:5000")

def is_authorized(user_id: str) -> bool:
    """Check if a user ID is in the authorized users list."""
    return str(user_id) in AUTHORIZED_USERS

