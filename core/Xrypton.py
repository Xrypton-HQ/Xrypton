import os
import time
from datetime import timedelta
from typing import Optional
import discord_ios
import discord

from discord.ext import commands
from discord.utils import MISSING
from dotenv import load_dotenv
import humanize

from core.context import Context
from core.logger import log
import core.client.interactions  # noqa: F401 - patches Interaction/Webhook

load_dotenv()

OWNER_IDS = [int(x) for x in os.getenv("OWNER_IDS", "").split(",") if x.strip().isdigit()]
DEFAULT_PREFIX = os.getenv("PREFIX", ",")
DATABASE_PATH = os.getenv("DATABASE_PATH", "core/schema/Xrypton.db")


class Xrypton(commands.AutoShardedBot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix=self.get_prefix,
            owner_ids=OWNER_IDS,
            allowed_mentions=discord.AllowedMentions(
                users=True,
                roles=False,
                everyone=False,
                replied_user=False,
            ),
            intents=discord.Intents.all(),
            help_command=None,
            context_class=Context,
        )
        self.start_time: Optional[float] = None

    async def get_prefix(self, message: discord.Message) -> list[str]:
        if not message.guild:
            return [DEFAULT_PREFIX]
        try:
            cursor = await self.db.execute(
                "SELECT prefix FROM guild_config WHERE guild_id = ?",
                (message.guild.id,),
            )
            row = await cursor.fetchone()
            if row and row["prefix"]:
                return [row["prefix"]]
        except Exception:
            pass
        return [DEFAULT_PREFIX]

    async def get_context(self, origin, *, cls=MISSING):
        if cls is MISSING:
            cls = Context
        return await super().get_context(origin, cls=cls)

    async def setup_hook(self) -> None:
        self.start_time = time.time()
        log.banner("Xrypton", "discord bot")
        await self.initialize_database()
        await self.load_cogs()
        self.tree.on_error = self.on_app_command_error
        synced = await self.tree.sync()
        log.success(f"Synced {len(synced)} application commands")

    async def initialize_database(self) -> None:
        """Initialize the database connection pool and run schema migrations."""
        import aiosqlite
        import os

        # Create database directory if it doesn't exist
        db_dir = os.path.dirname(DATABASE_PATH)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)

        # Connect to database and run schema
        self.db = await aiosqlite.connect(DATABASE_PATH)
        self.db.row_factory = aiosqlite.Row

        # Read and execute schema
        schema_path = os.path.join(os.path.dirname(__file__), "schema", "schema.sql")
        if os.path.exists(schema_path):
            with open(schema_path, "r", encoding="utf-8") as f:
                schema = f.read()
            await self.db.executescript(schema)
        else:
            # Fallback to basic tables if schema file missing
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS guild_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER UNIQUE NOT NULL,
                    prefix TEXT NOT NULL DEFAULT ','
                )
            """)
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS user_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE NOT NULL,
                    prefix TEXT NOT NULL
                )
            """)
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS bot_config (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    emoji_approve TEXT DEFAULT '✅',
                    emoji_deny TEXT DEFAULT '❌',
                    emoji_warn TEXT DEFAULT '⚠️',
                    emoji_cooldown TEXT DEFAULT '⏱️',
                    neutral_color INTEGER DEFAULT 0x2B2D31
                )
            """)
            await self.db.execute("""
                INSERT OR IGNORE INTO bot_config (id, emoji_approve, emoji_deny, emoji_warn, emoji_cooldown, neutral_color)
                VALUES (1, '✅', '❌', '⚠️', '⏱️', 0x2B2D31)
            """)
        await self.db.commit()
    async def on_shard(self) -> None:
        log.info(f"Shard {self.shard_id} ready")

    async def on_ready(self) -> None:
        log.success(f"Connected as {self.user}")

    async def on_command(self, ctx) -> None:
        log.info(f"{ctx.user} used command: {ctx.command}", name="Commands")

    async def on_command_error(self, ctx, error) -> None:
        from core.context import XryptonHelp

        if isinstance(error, commands.MissingRequiredArgument):
            return await XryptonHelp.send_command_help(ctx, ctx.command)

        if isinstance(error, (commands.MissingRole, commands.MissingPermissions, commands.CheckFailure)):
            return await ctx.deny("You don't have permission to use this command.")

        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.CommandInvokeError):
            error = error.original

        # Unhandled error — log the full traceback and notify the user
        log.traceback(error, f"Ignoring exception in command {ctx.command}")

        try:
            await ctx.deny(f"Error while invoking the command: {error}")
        except Exception:
            pass

    async def on_app_command_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError) -> None:
        # Unwrap original error if wrapped
        original = getattr(error, "original", error)
        log.traceback(original, f"Ignoring exception in app command {interaction.command}")

        # Try to notify user if possible (interaction may already be responded to)
        try:
            msg = f"Error while invoking the command: {original}"
            if interaction.response.is_done():
                await interaction.followup.send(embed=discord.Embed(description=msg, color=0xED4245), ephemeral=True)
            else:
                await interaction.response.send_message(embed=discord.Embed(description=msg, color=0xED4245), ephemeral=True)
        except Exception:
            pass

    async def load_cogs(self) -> None:
        for root, dirs, files in os.walk("./cogs"):
            if "__init__.py" in files:
                # Package with __init__.py: load the package itself, skip its modules
                relpath = os.path.relpath(root, "./cogs")
                module_path = "" if relpath == "." else relpath.replace(os.sep, ".")
                if module_path:
                    try:
                        await self.load_extension(f"cogs.{module_path}")
                        log.success(f"Loaded cog: cogs.{module_path}")
                    except Exception as e:
                        log.error(f"Failed to load cog cogs.{module_path}: {e}")
                dirs.clear()  # don't descend, the package handles its own contents
                continue
            for filename in files:
                if not filename.endswith(".py"):
                    continue
                relpath = os.path.relpath(os.path.join(root, filename), "./cogs")
                module_path = relpath.replace(os.sep, ".")[:-3]
                try:
                    await self.load_extension(f"cogs.{module_path}")
                    log.success(f"Loaded cog: cogs.{module_path}")
                except Exception as e:
                    log.error(f"Failed to load cog cogs.{module_path}: {e}")

    def booted(self, unix: bool = False) -> str | float:
        if self.start_time is None:
            return "not booted yet"
        if unix:
            return time.time() - self.start_time
        elapsed = time.time() - self.start_time
        return humanize.naturaldelta(timedelta(seconds=elapsed))

    def ping(self) -> int:
        return round(self.latency * 1000)

    def run(self) -> None:
        token = os.getenv("DISCORD_TOKEN")
        if not token:
            raise RuntimeError("DISCORD_TOKEN is not set in the environment")
        super().run(token, log_handler=None)


bot = Xrypton()
