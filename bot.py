import discord
from discord import app_commands
from discord.ext import commands
import docker
import secrets
from urllib.parse import urljoin
import asyncio

from database import ContainerDB
from config import DISCORD_TOKEN, TERMINAL_SERVICE_URL, is_authorized

# Initialize Docker client
docker_client = docker.from_env()

# Initialize database
db = ContainerDB()


class DockerBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self):
        """Called when the bot is starting up."""
        await db.init_db()
        await self.tree.sync()
        print("Bot is ready!")

    async def on_ready(self):
        print(f"{self.user} has logged in!")


bot = DockerBot()


def check_authorized(interaction: discord.Interaction) -> bool:
    """Check if the user is authorized to use commands."""
    if not is_authorized(str(interaction.user.id)):
        return False
    return True


@bot.tree.command(name="create", description="Create a Docker container for a user: Default Ubuntu 24.04 image")
@app_commands.describe(
    user="The Discord user to create a container for",
    container_name="Name for the container",
    image="The Docker image to use (default: ubuntu:24.04)"
)
async def create_container(
    interaction: discord.Interaction,
    user: discord.User,
    container_name: str,
    image: str = "ubuntu:24.04"
):
    """Create a Docker container bound to a Discord user."""
    if not check_authorized(interaction):
        await interaction.response.send_message(
            "❌ You are not authorized to use this command.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    try:
        # Check if user already has a container
        existing = await db.get_container_by_user(str(user.id))
        if existing:
            await interaction.followup.send(
                f"❌ User {user.mention} already has a container: `{existing['container_name']}`\n"
                f"Each user can only have ONE container. Destroy the existing one first.",
                ephemeral=True
            )
            return

        # Check if container name is already in use
        all_containers = await db.get_all_containers()
        if any(c['container_name'] == container_name for c in all_containers):
            await interaction.followup.send(
                f"❌ Container name `{container_name}` is already in use.",
                ephemeral=True
            )
            return

        # Pull image if needed (in background thread)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: docker_client.images.pull(image)
        )

        # Create container
        container = await loop.run_in_executor(
            None,
            lambda: docker_client.containers.create(
                image=image,
                name=container_name,
                detach=True,
                stdin_open=True,
                tty=True,
                command=["tail", "-f", "/dev/null"]
            )
        )

        # Ensure container is running for terminal access
        await loop.run_in_executor(None, container.start)

        # Store in database
        await db.create_container_record(
            discord_user_id=str(user.id),
            container_name=container_name,
            container_id=container.id,
            image=image
        )

        await interaction.followup.send(
            f"✅ Successfully created container `{container_name}` for {user.mention}\n"
            f"**Image:** {image}\n"
            f"**Container ID:** {container.id[:12]}",
            ephemeral=True
        )

    except docker.errors.ImageNotFound:
        await interaction.followup.send(
            f"❌ Docker image `{image}` not found.",
            ephemeral=True
        )
    except docker.errors.APIError as e:
        await interaction.followup.send(
            f"❌ Docker API error: {str(e)}",
            ephemeral=True
        )
    except Exception as e:
        await interaction.followup.send(
            f"❌ Error creating container: {str(e)}",
            ephemeral=True
        )


@bot.tree.command(name="destroy", description="Destroy a user's Docker container")
@app_commands.describe(user="The Discord user whose container to destroy")
async def destroy_container(
    interaction: discord.Interaction,
    user: discord.User
):
    """Destroy a Docker container for a user."""
    if not check_authorized(interaction):
        await interaction.response.send_message(
            "❌ You are not authorized to use this command.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    try:
        # Check if user has a container
        container_record = await db.get_container_by_user(str(user.id))
        if not container_record:
            await interaction.followup.send(
                f"❌ User {user.mention} does not have a container.",
                ephemeral=True
            )
            return

        container_name = container_record['container_name']
        container_id = container_record['container_id']

        # Get Docker container
        loop = asyncio.get_event_loop()
        try:
            docker_container = await loop.run_in_executor(
                None,
                lambda: docker_client.containers.get(container_id)
            )

            # Stop and remove container
            if docker_container.status == 'running':
                await loop.run_in_executor(
                    None,
                    docker_container.stop
                )
            
            await loop.run_in_executor(
                None,
                docker_container.remove
            )

        except docker.errors.NotFound:
            # Container doesn't exist in Docker but is in DB - clean up DB
            pass

        # Remove from database
        await db.delete_container_record(str(user.id))

        await interaction.followup.send(
            f"✅ Successfully destroyed container `{container_name}` for {user.mention}",
            ephemeral=True
        )

    except Exception as e:
        await interaction.followup.send(
            f"❌ Error destroying container: {str(e)}",
            ephemeral=True
        )


@bot.tree.command(name="list", description="List all containers")
async def list_containers(interaction: discord.Interaction):
    """List all containers in the database."""
    if not check_authorized(interaction):
        await interaction.response.send_message(
            "❌ You are not authorized to use this command.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    try:
        containers = await db.get_all_containers()
        
        if not containers:
            await interaction.followup.send(
                "📋 No containers found.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📋 Container List",
            description=f"Total containers: {len(containers)}",
            color=discord.Color.blue()
        )

        loop = asyncio.get_event_loop()
        for container_record in containers:
            user_id = container_record['discord_user_id']
            container_name = container_record['container_name']
            container_id = container_record['container_id']
            image = container_record['image']

            # Get container status from Docker
            try:
                docker_container = await loop.run_in_executor(
                    None,
                    lambda: docker_client.containers.get(container_id)
                )
                status = docker_container.status
                status_emoji = "🟢" if status == "running" else "🔴"
            except docker.errors.NotFound:
                status = "not found"
                status_emoji = "⚠️"

            embed.add_field(
                name=f"{status_emoji} {container_name}",
                value=f"**User:** <@{user_id}>\n**Image:** {image}\n**Status:** {status}",
                inline=False
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        await interaction.followup.send(
            f"❌ Error listing containers: {str(e)}",
            ephemeral=True
        )


@bot.tree.command(name="status", description="Check container status for a user")
@app_commands.describe(user="The Discord user to check")
async def container_status(interaction: discord.Interaction, user: discord.User):
    """Check the status of a user's container."""
    if not check_authorized(interaction):
        await interaction.response.send_message(
            "❌ You are not authorized to use this command.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    try:
        container_record = await db.get_container_by_user(str(user.id))
        
        if not container_record:
            await interaction.followup.send(
                f"❌ User {user.mention} does not have a container.",
                ephemeral=True
            )
            return

        container_name = container_record['container_name']
        container_id = container_record['container_id']
        image = container_record['image']
        created_at = container_record['created_at']

        # Get container status from Docker
        loop = asyncio.get_event_loop()
        try:
            docker_container = await loop.run_in_executor(
                None,
                lambda: docker_client.containers.get(container_id)
            )
            status = docker_container.status
            status_emoji = "🟢" if status == "running" else "🔴"
        except docker.errors.NotFound:
            status = "not found"
            status_emoji = "⚠️"

        embed = discord.Embed(
            title=f"{status_emoji} Container Status",
            color=discord.Color.green() if status == "running" else discord.Color.red()
        )
        embed.add_field(name="User", value=user.mention, inline=True)
        embed.add_field(name="Container Name", value=container_name, inline=True)
        embed.add_field(name="Image", value=image, inline=True)
        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(name="Created At", value=created_at, inline=True)
        embed.add_field(name="Container ID", value=container_id[:12], inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        await interaction.followup.send(
            f"❌ Error checking status: {str(e)}",
            ephemeral=True
        )

@bot.tree.command(name="terminal", description="Open a web terminal to your container")
async def terminal(interaction: discord.Interaction):
    if not check_authorized(interaction):
        await interaction.response.send_message("Unauthorized.", ephemeral=True)
        return

    container = await db.get_container_by_user(str(interaction.user.id))
    if not container:
        await interaction.response.send_message("You have no container.", ephemeral=True)
        return

    # Generate secure one-time URL
    token = secrets.token_urlsafe(16)
    url = urljoin(
        TERMINAL_SERVICE_URL.rstrip("/") + "/",
        f"terminal/{container['container_id']}?token={token}"
    )

    await db.store_terminal_token(container['container_id'], token, expiry=3600)

    embed = discord.Embed(title="Web Terminal", color=0x00ff00)
    embed.add_field(name="Container", value=container['container_name'], inline=False)
    embed.add_field(name="Click to Open", value=f"[Open Terminal]({url})", inline=False)

    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Open Terminal", url=url))

    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ DISCORD_TOKEN not found in environment variables!")
        print("Please create a .env file with your Discord bot token.")
        exit(1)

    bot.run(DISCORD_TOKEN)

