# Discord Docker Container Manager

A Discord bot that manages Docker containers, allowing authorized users to create and destroy containers bound to Discord accounts.

## Features

- **One container per user**: Each Discord user can only have one container
- **Allowlist system**: Only specific users can create/destroy containers
- **Database tracking**: SQLite database stores container records linked to Discord user IDs (snowflakes)
- **Docker integration**: Full Docker API support for container management

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Copy `env.example` to `.env` and configure:
```bash
cp env.example .env
```

3. Edit `.env` and add:
   - Your Discord bot token
   - Authorized user IDs (comma-separated Discord user IDs)

4. Run the bot:
```bash
python bot.py
```

## Configuration

The `.env` file should contain:
- `DISCORD_TOKEN`: Your Discord bot token
- `AUTHORIZED_USERS`: Comma-separated list of Discord user IDs (snowflakes) allowed to use commands

## Commands

- `/create <image> <container_name>` - Create a container for a user
- `/destroy <user_id>` - Destroy a user's container
- `/list` - List all containers
- `/status <user_id>` - Check container status for a user

## Database

The bot uses SQLite (`containers.db`) to track:
- Discord user ID (snowflake)
- Container name
- Container ID
- Image used
- Created timestamp

