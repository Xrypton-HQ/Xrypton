import re
import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from core.client.commands import has_permissions, hybrid_command, hybrid_group
from core.config import COLORS
from core.context import XryptonHelp


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

DURATION_RE = re.compile(
    r"^\s*(\d+)\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days|w|week|weeks|mo|month|months|y|year|years)?\s*$",
    re.IGNORECASE,
)

def parse_duration(arg: Optional[str]) -> Optional[timedelta]:
    if not arg:
        return None
    arg = arg.strip()
    # pure number -> seconds? treat as seconds? but more sensible as days? we treat as seconds if digit only without unit -> maybe minutes? use discord timeout: assume arg like "10m" else "10" -> minutes
    m = DURATION_RE.match(arg)
    if not m:
        return None
    amount = int(m.group(1))
    unit = (m.group(2) or "s").lower()
    if unit in ("s", "sec", "secs", "second", "seconds"):
        return timedelta(seconds=amount)
    if unit in ("m", "min", "mins", "minute", "minutes"):
        return timedelta(minutes=amount)
    if unit in ("h", "hr", "hrs", "hour", "hours"):
        return timedelta(hours=amount)
    if unit in ("d", "day", "days"):
        return timedelta(days=amount)
    if unit in ("w", "week", "weeks"):
        return timedelta(weeks=amount)
    if unit in ("mo", "month", "months"):
        return timedelta(days=amount * 30)
    if unit in ("y", "year", "years"):
        return timedelta(days=amount * 365)
    return timedelta(seconds=amount)

def human_duration(td: timedelta) -> str:
    secs = int(td.total_seconds())
    if secs < 60:
        return f"{secs}s"
    mins, secs = divmod(secs, 60)
    hrs, mins = divmod(mins, 60)
    days, hrs = divmod(hrs, 24)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hrs:
        parts.append(f"{hrs}h")
    if mins:
        parts.append(f"{mins}m")
    if secs and not days:
        parts.append(f"{secs}s")
    return " ".join(parts) if parts else "0s"

def can_moderate(ctx: commands.Context, target: discord.Member | discord.User) -> tuple[bool, str]:
    if isinstance(target, discord.User) and not isinstance(target, discord.Member):
        return True, ""
    # target is Member in guild
    if ctx.author.id == ctx.guild.owner_id:
        return True, ""
    if target.id == ctx.guild.owner_id:
        return False, "You cannot moderate the server owner."
    if target.id == ctx.bot.user.id:
        return False, "I cannot moderate myself."
    # role hierarchy
    if isinstance(target, discord.Member) and isinstance(ctx.author, discord.Member):
        if target.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            return False, "That user has a higher or equal role than you."
        if target.top_role >= ctx.guild.me.top_role:
            return False, "That user has a higher or equal role than me."
    return True, ""

class ConfirmView(discord.ui.View):
    def __init__(self, author: discord.Member, timeout: float = 30):
        super().__init__(timeout=timeout)
        self.author = author
        self.value: Optional[bool] = None

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            return await interaction.response.send_message(embed=discord.Embed(description=f"{discord.utils.escape_markdown(interaction.user.mention)} you're not the author.", color=COLORS.deny), ephemeral=True)
        self.value = True
        self.stop()
        try:
            await interaction.response.defer()
        except Exception:
            pass

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            return await interaction.response.send_message(embed=discord.Embed(description="You're not the author.", color=COLORS.deny), ephemeral=True)
        self.value = False
        self.stop()
        try:
            await interaction.response.defer()
        except Exception:
            pass

    async def on_timeout(self):
        self.value = False


class Moderation(commands.Cog):
    """Moderation tools: bans, kicks, timeouts, mutes, warns, snipe and nuke."""

    def __init__(self, bot):
        self.bot = bot
        # snipe stores: guild_id -> channel_id -> data
        self._snipe: dict[int, dict] = {}
        self._editsnipe: dict[int, dict] = {}
        self._reactsnipe: dict[int, dict] = {}
        # forcenick cache: guild_id -> user_id -> nick
        self._forcenick: dict[int, dict[int, str]] = {}

    async def cog_load(self) -> None:
        # table schemas live in core/schema/schema.sql (applied at startup)
        # load forcenick cache
        try:
            cursor = await self.bot.db.execute("SELECT guild_id, user_id, forced_nick FROM forcenick")
            rows = await cursor.fetchall()
            for r in rows:
                self._forcenick.setdefault(r["guild_id"], {})[r["user_id"]] = r["forced_nick"]
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    async def is_muted_react(self, guild_id: int, user_id: int) -> bool:
        cur = await self.bot.db.execute("SELECT 1 FROM reactmute WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        return await cur.fetchone() is not None

    async def is_muted_image(self, guild_id: int, user_id: int) -> bool:
        cur = await self.bot.db.execute("SELECT 1 FROM imagemute WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        return await cur.fetchone() is not None

    async def resolve_user(self, ctx: commands.Context, arg: str) -> Optional[discord.User]:
        # Try mention / id / fetch
        # Remove possible <@...> wrapper
        raw = arg.strip()
        m = re.match(r"<@!?(\d+)>", raw)
        if m:
            raw = m.group(1)
        if raw.isdigit():
            uid = int(raw)
            # Try guild member first, then fetch
            member = ctx.guild.get_member(uid) if ctx.guild else None
            if member:
                return member
            try:
                return await self.bot.fetch_user(uid)
            except Exception:
                return discord.Object(id=uid)  # fallback for ban/unban with ID
        # try by name#discrim or name search? fallback to Member converter
        try:
            converter = commands.MemberConverter()
            return await converter.convert(ctx, arg)
        except Exception:
            pass
        try:
            converter = commands.UserConverter()
            return await converter.convert(ctx, arg)
        except Exception:
            return None

    async def log_mod(self, guild_id: int, user_id: int, action: str, moderator_id: Optional[int], reason: Optional[str]):
        try:
            await self.bot.db.execute(
                "INSERT INTO mod_history (guild_id, user_id, action, moderator_id, reason) VALUES (?, ?, ?, ?, ?)",
                (guild_id, user_id, action, moderator_id, reason),
            )
            await self.bot.db.commit()
        except Exception:
            # table may be in server cog with different name; ignore
            pass

    # ------------------------------------------------------------------ #
    # Listeners: snipe / editsnipe / reactsnipe / mutes / forcenick
    # ------------------------------------------------------------------ #

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        # snipe storage
        self._snipe[message.channel.id] = {
            "content": message.content,
            "author": message.author,
            "author_id": message.author.id,
            "channel": message.channel,
            "attachments": [a.url for a in message.attachments],
            "embeds": message.embeds,
            "created_at": message.created_at,
            "deleted_at": datetime.now(timezone.utc),
        }

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not after.guild or after.author.bot or before.content == after.content:
            return
        self._editsnipe[after.channel.id] = {
            "before": before.content,
            "after": after.content,
            "author": after.author,
            "channel": after.channel,
            "jump_url": after.jump_url,
            "edited_at": datetime.now(timezone.utc),
        }

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return
        # store reactsnipe
        guild = self.bot.get_guild(payload.guild_id)
        channel = guild.get_channel(payload.channel_id) if guild else None
        self._reactsnipe[payload.channel_id] = {
            "emoji": str(payload.emoji),
            "user_id": payload.user_id,
            "member": payload.member,
            "channel": channel,
            "message_id": payload.message_id,
            "guild_id": payload.guild_id,
        }
        # reactmute handling: remove reaction if user is reactmuted
        if await self.is_muted_react(payload.guild_id, payload.user_id):
            try:
                # need to fetch channel and message to remove reaction - best effort
                ch = guild.get_channel(payload.channel_id) if guild else None
                if ch:
                    msg = await ch.fetch_message(payload.message_id)
                    member = payload.member or guild.get_member(payload.user_id)
                    await msg.remove_reaction(payload.emoji, member)
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        # imagemute: delete message if it contains images/attachments
        if message.attachments or any(ext in message.content.lower() for ext in (".png",".jpg",".jpeg",".gif",".webp","http")):
            # check if message has image embed/attachment
            has_image = False
            if message.attachments:
                has_image = True
            # also check embeds with image
            if message.embeds:
                for e in message.embeds:
                    if e.image or e.thumbnail:
                        has_image = True
            # also simple link detection for image urls
            if not has_image and re.search(r"https?://\S+\.(png|jpe?g|gif|webp)", message.content, re.I):
                has_image = True
            if has_image and await self.is_muted_image(message.guild.id, message.author.id):
                try:
                    await message.delete()
                    try:
                        await message.channel.send(f"{message.author.mention} you are **imagemuted** and cannot send images.", delete_after=5)
                    except Exception:
                        pass
                except Exception:
                    pass

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # forcenick enforcement
        guild_forces = self._forcenick.get(after.guild.id, {})
        forced = guild_forces.get(after.id)
        if forced and after.nick != forced:
            try:
                await after.edit(nick=forced, reason="Forcenick enforcement")
            except (discord.Forbidden, discord.HTTPException):
                pass

    # ------------------------------------------------------------------ #
    # Ban / Unban / Kick / Timeout
    # ------------------------------------------------------------------ #

    @hybrid_command(name="ban", aliases=["b", "deport", "boot"], description="Ban someone with confirmation", example=",ban @user 7d Spamming")
    @app_commands.describe(user="User to ban", duration="Duration like 7d, 1h (optional, tempban)", reason="Reason for the ban")
    @commands.guild_only()
    @has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, user: discord.User, duration: Optional[str] = None, *, reason: Optional[str] = None):
        # duration/reason juggling: if duration provided but not a valid duration, treat as part of reason
        actual_reason = reason
        td = parse_duration(duration) if duration else None
        if duration and td is None:
            # duration is actually start of reason
            actual_reason = (duration + (" " + reason if reason else "")).strip()
            duration = None
            td = None
        else:
            actual_reason = reason
        # resolve target if passed as string? user is already converted
        target = user
        # hierarchy check if member
        member_target = ctx.guild.get_member(target.id) if hasattr(target, "id") else None
        if member_target:
            ok, msg = can_moderate(ctx, member_target)
            if not ok:
                return await ctx.deny(msg)
        if target.id == ctx.author.id:
            return await ctx.deny("You cannot ban yourself.")
        # confirmation
        embed = discord.Embed(title="Confirm Ban", description=f"Are you sure you want to ban **{target}** (`{target.id}`)?" + (f"\n**Duration:** {human_duration(td)}" if td else "") + (f"\n**Reason:** {actual_reason}" if actual_reason else ""), color=COLORS.warn)
        view = ConfirmView(ctx.author)
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()
        try:
            await msg.delete()
        except Exception:
            pass
        if not view.value:
            return await ctx.warn("Ban cancelled.")
        try:
            await ctx.guild.ban(target, reason=actual_reason or f"Banned by {ctx.author} (ID: {ctx.author.id})", delete_message_days=1)
        except discord.Forbidden:
            return await ctx.deny("I don't have permission to ban that user.")
        except discord.HTTPException as e:
            return await ctx.deny(f"Failed to ban: `{e}`")
        await self.log_mod(ctx.guild.id, target.id, "ban", ctx.author.id, actual_reason)
        # tempban scheduling
        if td:
            # schedule unban
            async def _temp_unban():
                await asyncio.sleep(td.total_seconds())
                try:
                    await ctx.guild.unban(target, reason="Tempban expired")
                except Exception:
                    pass
            self.bot.loop.create_task(_temp_unban())
            return await ctx.approve(f"**{target}** has been banned for **{human_duration(td)}**." + (f" Reason: {actual_reason}" if actual_reason else ""))
        await ctx.approve(f"**{target}** has been banned." + (f" Reason: {actual_reason}" if actual_reason else ""))

    @hybrid_command(name="unban", aliases=["ub"], description="Unban someone", example=",unban 123456789012345678")
    @app_commands.describe(user="User ID or name to unban")
    @commands.guild_only()
    @has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, *, user: str):
        # user may be ID or tag
        target = await self.resolve_user(ctx, user)
        if not target:
            return await ctx.warn("Could not find that user. Provide an ID or mention.")
        uid = target.id if hasattr(target, "id") else None
        if not uid:
            return await ctx.warn("Invalid user.")
        # try fetch ban entry to confirm
        try:
            # check if banned
            bans = [b async for b in ctx.guild.bans(limit=200)]
            banned_ids = [b.user.id for b in bans]
            if uid not in banned_ids:
                # still try unban; discord will error if not banned
                pass
        except Exception:
            pass
        try:
            await ctx.guild.unban(discord.Object(id=uid), reason=f"Unbanned by {ctx.author} (ID: {ctx.author.id})")
        except discord.NotFound:
            return await ctx.warn("That user is not banned.")
        except discord.Forbidden:
            return await ctx.deny("I don't have permission to unban.")
        except discord.HTTPException as e:
            return await ctx.deny(f"Failed to unban: `{e}`")
        await ctx.approve(f"**{target}** has been unbanned.")

    @hybrid_command(name="kick", description="Kick someone with confirmation", example=",kick @user Spamming")
    @app_commands.describe(user="User to kick", reason="Reason")
    @commands.guild_only()
    @has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, user: discord.Member, *, reason: Optional[str] = None):
        ok, msg = can_moderate(ctx, user)
        if not ok:
            return await ctx.deny(msg)
        embed = discord.Embed(title="Confirm Kick", description=f"Kick **{user}** (`{user.id}`)?" + (f"\n**Reason:** {reason}" if reason else ""), color=COLORS.warn)
        view = ConfirmView(ctx.author)
        m = await ctx.send(embed=embed, view=view)
        await view.wait()
        try:
            await m.delete()
        except Exception:
            pass
        if not view.value:
            return await ctx.warn("Kick cancelled.")
        try:
            await user.kick(reason=reason or f"Kicked by {ctx.author} (ID: {ctx.author.id})")
        except discord.Forbidden:
            return await ctx.deny("I don't have permission to kick that user.")
        except discord.HTTPException as e:
            return await ctx.deny(f"Failed to kick: `{e}`")
        await self.log_mod(ctx.guild.id, user.id, "kick", ctx.author.id, reason)
        await ctx.approve(f"**{user}** has been kicked." + (f" Reason: {reason}" if reason else ""))

    @hybrid_command(name="timeout", aliases=["mute", "m"], description="Timeout someone with confirmation", example=",timeout @user 10m Spamming")
    @app_commands.describe(user="User to timeout", duration="Duration like 10m, 1h, 7d", reason="Reason")
    @commands.guild_only()
    @has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def timeout(self, ctx: commands.Context, user: discord.Member, duration: str, *, reason: Optional[str] = None):
        td = parse_duration(duration)
        if not td:
            return await ctx.warn("Invalid duration. Use like `10m`, `1h`, `7d`. Max 28 days.")
        if td.total_seconds() > 28 * 24 * 3600:
            return await ctx.warn("Timeout cannot be longer than 28 days.")
        if td.total_seconds() < 1:
            return await ctx.warn("Duration must be at least 1 second.")
        ok, msg = can_moderate(ctx, user)
        if not ok:
            return await ctx.deny(msg)
        if user.is_timed_out():
            # still allow re-timeout
            pass
        embed = discord.Embed(title="Confirm Timeout", description=f"Timeout **{user}** for **{human_duration(td)}**?" + (f"\n**Reason:** {reason}" if reason else ""), color=COLORS.warn)
        view = ConfirmView(ctx.author)
        m = await ctx.send(embed=embed, view=view)
        await view.wait()
        try:
            await m.delete()
        except Exception:
            pass
        if not view.value:
            return await ctx.warn("Timeout cancelled.")
        try:
            await user.timeout(timedelta(seconds=td.total_seconds()), reason=reason or f"Timed out by {ctx.author} (ID: {ctx.author.id})")
        except discord.Forbidden:
            return await ctx.deny("I don't have permission to timeout that user.")
        except discord.HTTPException as e:
            return await ctx.deny(f"Failed to timeout: `{e}`")
        await self.log_mod(ctx.guild.id, user.id, "timeout", ctx.author.id, f"{human_duration(td)} | {reason}" if reason else human_duration(td))
        await ctx.approve(f"**{user}** has been timed out for **{human_duration(td)}**." + (f" Reason: {reason}" if reason else ""))

    @hybrid_command(name="untimeout", aliases=["utimeout", "ut", "unmute", "um"], description="Untimeout someone", example=",untimeout @user")
    @app_commands.describe(user="User to untimeout", reason="Reason")
    @commands.guild_only()
    @has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def untimeout(self, ctx: commands.Context, user: discord.Member, *, reason: Optional[str] = None):
        if not user.is_timed_out():
            return await ctx.warn(f"**{user}** is not timed out.")
        try:
            await user.timeout(None, reason=reason or f"Untimed out by {ctx.author}")
        except discord.Forbidden:
            return await ctx.deny("I don't have permission to untimeout that user.")
        except discord.HTTPException as e:
            return await ctx.deny(f"Failed to untimeout: `{e}`")
        await ctx.approve(f"**{user}** has been untimed out." + (f" Reason: {reason}" if reason else ""))

    # ------------------------------------------------------------------ #
    # Reactmute / Imagemute
    # ------------------------------------------------------------------ #

    @hybrid_command(name="reactmute", description="Mute someones ability to react to messages", example=",reactmute @user")
    @app_commands.describe(user="User to reactmute")
    @commands.guild_only()
    @has_permissions(moderate_members=True)
    async def reactmute(self, ctx: commands.Context, user: discord.Member):
        ok, msg = can_moderate(ctx, user)
        if not ok:
            return await ctx.deny(msg)
        if await self.is_muted_react(ctx.guild.id, user.id):
            return await ctx.warn(f"**{user}** is already reactmuted.")
        await self.bot.db.execute("INSERT INTO reactmute (guild_id, user_id) VALUES (?, ?)", (ctx.guild.id, user.id))
        await self.bot.db.commit()
        await ctx.approve(f"**{user}** has been **reactmuted**.")

    @hybrid_command(name="unreactmute", description="Unmute someones ability to react", example=",unreactmute @user")
    @app_commands.describe(user="User to unreactmute")
    @commands.guild_only()
    @has_permissions(moderate_members=True)
    async def unreactmute(self, ctx: commands.Context, user: discord.Member):
        cur = await self.bot.db.execute("DELETE FROM reactmute WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, user.id))
        await self.bot.db.commit()
        if cur.rowcount == 0:
            return await ctx.warn(f"**{user}** is not reactmuted.")
        await ctx.approve(f"**{user}** has been **unreactmuted**.")

    @hybrid_command(name="imagemute", description="Mute someones ability to send images", example=",imagemute @user")
    @app_commands.describe(user="User to imagemute")
    @commands.guild_only()
    @has_permissions(moderate_members=True)
    async def imagemute(self, ctx: commands.Context, user: discord.Member):
        ok, msg = can_moderate(ctx, user)
        if not ok:
            return await ctx.deny(msg)
        if await self.is_muted_image(ctx.guild.id, user.id):
            return await ctx.warn(f"**{user}** is already imagemuted.")
        await self.bot.db.execute("INSERT INTO imagemute (guild_id, user_id) VALUES (?, ?)", (ctx.guild.id, user.id))
        await self.bot.db.commit()
        await ctx.approve(f"**{user}** has been **imagemuted**.")

    @hybrid_command(name="unimagemute", description="Unmute someones ability to send images", example=",unimagemute @user")
    @app_commands.describe(user="User to unimagemute")
    @commands.guild_only()
    @has_permissions(moderate_members=True)
    async def unimagemute(self, ctx: commands.Context, user: discord.Member):
        cur = await self.bot.db.execute("DELETE FROM imagemute WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, user.id))
        await self.bot.db.commit()
        if cur.rowcount == 0:
            return await ctx.warn(f"**{user}** is not imagemuted.")
        await ctx.approve(f"**{user}** has been **unimagemuted**.")

    # ------------------------------------------------------------------ #
    # Warn system
    # ------------------------------------------------------------------ #

    @hybrid_command(name="warn", description="Warn someone", example=",warn @user Spamming")
    @app_commands.describe(user="User to warn", reason="Reason", duration="Duration for temp warn like 7d")
    @commands.guild_only()
    @has_permissions(moderate_members=True)
    async def warn(self, ctx: commands.Context, user: discord.Member, reason: Optional[str] = None, duration: Optional[str] = None):
        # handle case where reason might be duration if 3rd arg is duration-like and reason is None swapped? For hybrid, reason and duration are named, so if user does prefix ",warn @user 7d Spamming" parser will put reason="7d", duration="Spamming" ??? We normalize.
        # Normalize: if reason looks like duration and duration is None, swap? Actually warn spec is [user] [reason opt] [duration opt] -> reason second, duration third.
        # But if user typed ",warn @user Spamming 7d" -> reason="Spamming", duration="7d" correct.
        # If ",warn @user 7d" -> reason="7d" duration=None -> we should detect duration in reason.
        actual_reason = reason
        actual_duration = duration
        # if reason looks like duration and no duration provided, treat as duration? but spec says reason before duration, so ambiguous - we support both.
        if actual_reason and parse_duration(actual_reason) and not actual_duration:
            # check if there is no actual reason text besides duration, maybe user meant duration
            # But we treat as duration only if no other words in reason and next arg missing.
            # Keep reason as duration? For now, if reason is duration-like and duration is None, move to duration and clear reason.
            td_test = parse_duration(actual_reason)
            # Only move if reason contains only duration pattern (no spaces extra)
            if td_test and actual_reason.strip().lower() == actual_reason.strip().lower() and len(actual_reason.split()) == 1:
                actual_duration = actual_reason
                actual_reason = None
        # Also if duration provided but not valid duration, merge into reason
        if actual_duration and not parse_duration(actual_duration):
            actual_reason = (actual_reason + " " + actual_duration).strip() if actual_reason else actual_duration
            actual_duration = None
        td = parse_duration(actual_duration) if actual_duration else None
        ok, msg = can_moderate(ctx, user)
        if not ok:
            return await ctx.deny(msg)
        expires_at = None
        if td:
            expires_at = datetime.now(timezone.utc) + td
        await self.bot.db.execute(
            "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, expires_at) VALUES (?, ?, ?, ?, ?)",
            (ctx.guild.id, user.id, ctx.author.id, actual_reason or "No reason", expires_at.isoformat() if expires_at else None),
        )
        await self.bot.db.commit()
        # count warnings for user
        cur = await self.bot.db.execute("SELECT COUNT(*) as c FROM warnings WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, user.id))
        row = await cur.fetchone()
        count = row["c"] if row else 1
        await ctx.approve(f"**{user}** has been warned" + (f" for **{human_duration(td)}**" if td else "") + f" (now **{count}** warning(s))." + (f" Reason: {actual_reason}" if actual_reason else ""))
        if td:
            # schedule auto unwarn
            async def _auto():
                await asyncio.sleep(td.total_seconds())
                try:
                    await self.bot.db.execute("DELETE FROM warnings WHERE guild_id = ? AND user_id = ? AND expires_at = ?", (ctx.guild.id, user.id, expires_at.isoformat()))
                    await self.bot.db.commit()
                except Exception:
                    pass
            self.bot.loop.create_task(_auto())

    @hybrid_command(name="unwarn", description="Unwarn someone", example=",unwarn @user")
    @app_commands.describe(user="User to unwarn", reason="Reason to match (optional, removes latest if not provided)")
    @commands.guild_only()
    @has_permissions(moderate_members=True)
    async def unwarn(self, ctx: commands.Context, user: discord.Member, *, reason: Optional[str] = None):
        if reason:
            cur = await self.bot.db.execute("SELECT id FROM warnings WHERE guild_id = ? AND user_id = ? AND reason = ? ORDER BY id DESC LIMIT 1", (ctx.guild.id, user.id, reason))
            row = await cur.fetchone()
            if not row:
                # try like search
                cur = await self.bot.db.execute("SELECT id FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY id DESC", (ctx.guild.id, user.id))
                rows = await cur.fetchall()
                # find first where reason contains provided text?
                found = None
                for r in rows:
                    # fetch actual reason
                    cur2 = await self.bot.db.execute("SELECT reason FROM warnings WHERE id = ?", (r["id"],))
                    rr = await cur2.fetchone()
                    if rr and reason.lower() in (rr["reason"] or "").lower():
                        found = r["id"]
                        break
                if not found:
                    return await ctx.warn(f"No warning found for **{user}** matching that reason.")
                row_id = found
            else:
                row_id = row["id"]
            await self.bot.db.execute("DELETE FROM warnings WHERE id = ?", (row_id,))
            await self.bot.db.commit()
            return await ctx.approve(f"Removed warning for **{user}** (reason matched).")
        else:
            cur = await self.bot.db.execute("SELECT id FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY id DESC LIMIT 1", (ctx.guild.id, user.id))
            row = await cur.fetchone()
            if not row:
                return await ctx.warn(f"**{user}** has no warnings.")
            await self.bot.db.execute("DELETE FROM warnings WHERE id = ?", (row["id"],))
            await self.bot.db.commit()
            await ctx.approve(f"Removed latest warning for **{user}**.")

    @hybrid_command(name="unbanall", description="Unban everyone with confirmation", example=",unbanall")
    @commands.guild_only()
    @has_permissions(administrator=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unbanall(self, ctx: commands.Context):
        bans = [b async for b in ctx.guild.bans(limit=None)]
        if not bans:
            return await ctx.warn("No banned users.")
        embed = discord.Embed(title="Confirm Unbanall", description=f"Are you sure you want to unban **{len(bans)}** users?", color=COLORS.warn)
        view = ConfirmView(ctx.author, timeout=30)
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()
        try:
            await msg.delete()
        except Exception:
            pass
        if not view.value:
            return await ctx.warn("Unbanall cancelled.")
        unbanned = 0
        failed = 0
        for ban in bans:
            try:
                await ctx.guild.unban(ban.user, reason=f"Unbanall by {ctx.author}")
                unbanned += 1
            except Exception:
                failed += 1
        await ctx.approve(f"Unbanned **{unbanned}** users." + (f" Failed: {failed}." if failed else ""))

    @hybrid_command(name="unmuteall", description="Unmute everyone who is muted with confirmation", example=",unmuteall")
    @commands.guild_only()
    @has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def unmuteall(self, ctx: commands.Context):
        # find timed out members
        muted = [m for m in ctx.guild.members if m.is_timed_out()]
        if not muted:
            return await ctx.warn("No timed out members.")
        embed = discord.Embed(title="Confirm Unmuteall", description=f"Remove timeout from **{len(muted)}** members?", color=COLORS.warn)
        view = ConfirmView(ctx.author)
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()
        try:
            await msg.delete()
        except Exception:
            pass
        if not view.value:
            return await ctx.warn("Unmuteall cancelled.")
        count = 0
        for m in muted:
            try:
                await m.timeout(None, reason=f"Unmuteall by {ctx.author}")
                count += 1
            except Exception:
                pass
        await ctx.approve(f"Unmuted **{count}** members.")

    @hybrid_command(name="unwarnall", description="Unwarn everyone who has a warning ONCE (deduct one)", example=",unwarnall")
    @commands.guild_only()
    @has_permissions(moderate_members=True)
    async def unwarnall(self, ctx: commands.Context):
        cur = await self.bot.db.execute("SELECT user_id, COUNT(*) as c FROM warnings WHERE guild_id = ? GROUP BY user_id", (ctx.guild.id,))
        rows = await cur.fetchall()
        if not rows:
            return await ctx.warn("No warnings to remove.")
        embed = discord.Embed(title="Confirm Unwarnall", description=f"Deduct **one** warning from **{len(rows)}** users? (total warnings: {sum(r['c'] for r in rows)})", color=COLORS.warn)
        view = ConfirmView(ctx.author)
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()
        try:
            await msg.delete()
        except Exception:
            pass
        if not view.value:
            return await ctx.warn("Cancelled.")
        removed = 0
        for r in rows:
            cur2 = await self.bot.db.execute("SELECT id FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY id DESC LIMIT 1", (ctx.guild.id, r["user_id"]))
            row = await cur2.fetchone()
            if row:
                await self.bot.db.execute("DELETE FROM warnings WHERE id = ?", (row["id"],))
                removed += 1
        await self.bot.db.commit()
        await ctx.approve(f"Deducted one warning from **{removed}** users.")

    @hybrid_command(name="resetwarns", description="Remove everyones warnings", example=",resetwarns")
    @commands.guild_only()
    @has_permissions(administrator=True)
    async def resetwarns(self, ctx: commands.Context):
        cur = await self.bot.db.execute("SELECT COUNT(*) as c FROM warnings WHERE guild_id = ?", (ctx.guild.id,))
        row = await cur.fetchone()
        total = row["c"] if row else 0
        if total == 0:
            return await ctx.warn("No warnings to reset.")
        embed = discord.Embed(title="Confirm Resetwarns", description=f"Remove **all {total}** warnings for everyone? This cannot be undone.", color=COLORS.deny)
        view = ConfirmView(ctx.author, timeout=30)
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()
        try:
            await msg.delete()
        except Exception:
            pass
        if not view.value:
            return await ctx.warn("Cancelled.")
        await self.bot.db.execute("DELETE FROM warnings WHERE guild_id = ?", (ctx.guild.id,))
        await self.bot.db.commit()
        await ctx.approve(f"Removed **{total}** warnings.")

    # ------------------------------------------------------------------ #
    # Nuke
    # ------------------------------------------------------------------ #

    @hybrid_command(name="nuke", aliases=["recreate"], description="Delete and recreate a channel", example=",nuke #general")
    @app_commands.describe(channel="Channel to nuke (defaults to current)")
    @commands.guild_only()
    @has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def nuke(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        channel = channel or ctx.channel
        if not isinstance(channel, discord.TextChannel):
            return await ctx.warn("Can only nuke text channels.")
        embed = discord.Embed(title="Confirm Nuke", description=f"Are you sure you want to nuke {channel.mention}?\nThis will delete and recreate it (all messages will be lost).", color=COLORS.deny)
        view = ConfirmView(ctx.author)
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()
        try:
            await msg.delete()
        except Exception:
            pass
        if not view.value:
            return await ctx.warn("Nuke cancelled.")
        try:
            # clone preserves overwrites, topic, category, position, nsfw, rate_limit, etc.
            new_channel = await channel.clone(reason=f"Nuked by {ctx.author} (ID: {ctx.author.id})")
            await channel.delete(reason=f"Nuked by {ctx.author}")
            # try to keep position similar? clone already does.
            await new_channel.send(f"🔥 Channel nuked by {ctx.author.mention}")
        except discord.Forbidden:
            return await ctx.deny("I don't have permission to nuke that channel.")
        except discord.HTTPException as e:
            return await ctx.deny(f"Failed to nuke: `{e}`")

    # ------------------------------------------------------------------ #
    # Snipe family
    # ------------------------------------------------------------------ #

    @hybrid_command(name="snipe", aliases=["s"], description="View the last deleted message", example=",snipe")
    @app_commands.describe(channel="Channel to snipe from (defaults to current)")
    @commands.guild_only()
    async def snipe(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        channel = channel or ctx.channel
        data = self._snipe.get(channel.id)
        if not data:
            return await ctx.warn(f"No deleted message found in {channel.mention}.")
        embed = discord.Embed(
            title="Snipe",
            description=data["content"][:4096] or "*No text content*",
            color=COLORS.neutral,
            timestamp=data["deleted_at"],
        )
        embed.set_author(name=f"{data['author']} ({data['author_id']})", icon_url=data["author"].display_avatar.url if hasattr(data["author"], "display_avatar") else None)
        if data["attachments"]:
            embed.add_field(name="Attachments", value="\n".join(data["attachments"])[:1024], inline=False)
        embed.set_footer(text=f"Deleted in #{channel.name} • Original: {discord.utils.format_dt(data['created_at'], 'F')}")
        await ctx.send(embed=embed)

    @hybrid_command(name="editsnipe", aliases=["es"], description="View the last edited message (before/after)", example=",editsnipe")
    @app_commands.describe(channel="Channel to editsnipe from")
    @commands.guild_only()
    async def editsnipe(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        channel = channel or ctx.channel
        data = self._editsnipe.get(channel.id)
        if not data:
            return await ctx.warn(f"No edited message found in {channel.mention}.")
        embed = discord.Embed(title="Edit Snipe", color=COLORS.neutral, timestamp=data["edited_at"])
        embed.set_author(name=f"{data['author']} ({data['author'].id})", icon_url=data["author"].display_avatar.url if hasattr(data["author"], "display_avatar") else None)
        embed.add_field(name="Before", value=data["before"][:1024] or "*No content*", inline=False)
        embed.add_field(name="After", value=data["after"][:1024] or "*No content*", inline=False)
        embed.add_field(name="Channel", value=channel.mention, inline=True)
        embed.add_field(name="Link", value=f"[Jump]({data['jump_url']})", inline=True)
        await ctx.send(embed=embed)

    @hybrid_command(name="reactsnipe", aliases=["rs"], description="View the last reaction on a message", example=",reactsnipe")
    @app_commands.describe(channel="Channel to reactsnipe from")
    @commands.guild_only()
    async def reactsnipe(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        channel = channel or ctx.channel
        data = self._reactsnipe.get(channel.id)
        if not data:
            return await ctx.warn(f"No recent reaction found in {channel.mention}.")
        user = data.get("member") or self.bot.get_user(data["user_id"]) or f"ID {data['user_id']}"
        mention = user.mention if hasattr(user, "mention") else str(user)
        embed = discord.Embed(
            title="React Snipe",
            description=f"{mention} reacted with {data['emoji']} in {channel.mention}\n[Jump to message](https://discord.com/channels/{ctx.guild.id}/{channel.id}/{data['message_id']})",
            color=COLORS.neutral,
        )
        await ctx.send(embed=embed)

    @hybrid_command(name="clearsnipe", aliases=["cs"], description="Clear all snipes.", example=",clearsnipe")
    @commands.guild_only()
    @has_permissions(manage_messages=True)
    async def clearsnipe(self, ctx: commands.Context):
        # clear for guild's channels only
        to_delete = []
        for cid in list(self._snipe.keys()):
            ch = ctx.guild.get_channel(cid)
            if ch:
                to_delete.append(cid)
        for cid in to_delete:
            self._snipe.pop(cid, None)
        for cid in list(self._editsnipe.keys()):
            if ctx.guild.get_channel(cid):
                self._editsnipe.pop(cid, None)
        for cid in list(self._reactsnipe.keys()):
            if ctx.guild.get_channel(cid):
                self._reactsnipe.pop(cid, None)
        await ctx.approve("Cleared all snipes for this server.")

    # ------------------------------------------------------------------ #
    # Forcenick / Nickname
    # ------------------------------------------------------------------ #

    @hybrid_command(name="forcenick", aliases=["fn", "focenickname"], description="Force someone's nickname to be that, they cant change it", example=",forcenick @user NewName")
    @app_commands.describe(user="User to forcenick", new_name="Forced nickname")
    @commands.guild_only()
    @has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    async def forcenick(self, ctx: commands.Context, user: discord.Member, *, new_name: str):
        if len(new_name) > 32:
            return await ctx.warn("Nickname cannot be longer than 32 characters.")
        ok, msg = can_moderate(ctx, user)
        if not ok:
            return await ctx.deny(msg)
        if user.id == ctx.guild.owner_id:
            return await ctx.warn("Cannot forcenick the server owner.")
        # store
        await self.bot.db.execute(
            "INSERT INTO forcenick (guild_id, user_id, forced_nick) VALUES (?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET forced_nick = excluded.forced_nick",
            (ctx.guild.id, user.id, new_name),
        )
        await self.bot.db.commit()
        self._forcenick.setdefault(ctx.guild.id, {})[user.id] = new_name
        try:
            await user.edit(nick=new_name, reason=f"Forcenick by {ctx.author}")
        except discord.Forbidden:
            return await ctx.deny("I don't have permission to change that user's nickname.")
        except discord.HTTPException as e:
            return await ctx.deny(f"Failed: `{e}`")
        await ctx.approve(f"Forced **{user}**'s nickname to **{new_name}**.")

    @hybrid_command(name="unforcenick", aliases=["ufn", "unfn", "unforcenickname"], description="Remove forced nickname", example=",unforcenick @user")
    @app_commands.describe(user="User to unforcenick")
    @commands.guild_only()
    @has_permissions(manage_nicknames=True)
    async def unforcenick(self, ctx: commands.Context, user: discord.Member):
        cur = await self.bot.db.execute("DELETE FROM forcenick WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, user.id))
        await self.bot.db.commit()
        self._forcenick.get(ctx.guild.id, {}).pop(user.id, None)
        if cur.rowcount == 0:
            return await ctx.warn(f"**{user}** is not forcenicked.")
        await ctx.approve(f"Removed forcenick for **{user}**.")
        # optionally reset nick? leave as is

    @hybrid_command(name="nickname", aliases=["nick"], description="Change someones nickname", example=",nickname @user CoolName")
    @app_commands.describe(user="User to change nickname for", new_name="New nickname (leave empty to reset)")
    @commands.guild_only()
    @has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    async def nickname(self, ctx: commands.Context, user: discord.Member, *, new_name: Optional[str] = None):
        if new_name and len(new_name) > 32:
            return await ctx.warn("Nickname too long (32 max).")
        ok, msg = can_moderate(ctx, user)
        if not ok:
            return await ctx.deny(msg)
        try:
            await user.edit(nick=new_name, reason=f"Nickname changed by {ctx.author}")
        except discord.Forbidden:
            return await ctx.deny("I don't have permission to change that nickname.")
        except discord.HTTPException as e:
            return await ctx.deny(f"Failed: `{e}`")
        if new_name:
            await ctx.approve(f"Changed **{user}**'s nickname to **{new_name}**.")
        else:
            await ctx.approve(f"Reset **{user}**'s nickname.")

    @hybrid_command(name="resetnickname", aliases=["resetnick", "rn"], description="Reset someones server nickname to global", example=",resetnickname @user")
    @app_commands.describe(user="User to reset nickname for (defaults to yourself)")
    @commands.guild_only()
    @has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    async def resetnickname(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        user = user or ctx.author  # type: ignore
        try:
            await user.edit(nick=None, reason=f"Reset nickname by {ctx.author}")
        except discord.Forbidden:
            return await ctx.deny("I don't have permission to reset that nickname.")
        except discord.HTTPException as e:
            return await ctx.deny(f"Failed: `{e}`")
        await ctx.approve(f"Reset **{user}**'s nickname.")

    # ------------------------------------------------------------------ #
    # Lock / Unlock / Lockall
    # ------------------------------------------------------------------ #

    @hybrid_command(name="lock", aliases=["lockdown"], description="Lock a channel and prevent users from sending messages", example=",lock #general")
    @app_commands.describe(channel="Channel to lock (defaults to current)")
    @commands.guild_only()
    @has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def lock(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        channel = channel or ctx.channel
        # check if already locked for default_role
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        if overwrite.send_messages is False:
            return await ctx.warn(f"{channel.mention} is already locked.")
        try:
            await channel.set_permissions(ctx.guild.default_role, send_messages=False, reason=f"Locked by {ctx.author}")
        except discord.Forbidden:
            return await ctx.deny("I don't have permission to lock that channel.")
        except discord.HTTPException as e:
            return await ctx.deny(f"Failed: `{e}`")
        await ctx.approve(f"🔒 Locked {channel.mention}.")

    @hybrid_command(name="unlock", aliases=["unlockdown"], description="Unlock a channel", example=",unlock #general")
    @app_commands.describe(channel="Channel to unlock (defaults to current)")
    @commands.guild_only()
    @has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def unlock(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        if overwrite.send_messages is not False:
            # Could be None (inherit) = not locked; still unlock should set to None? We'll treat None as unlocked
            return await ctx.warn(f"{channel.mention} is not locked.")
        try:
            await channel.set_permissions(ctx.guild.default_role, send_messages=None, reason=f"Unlocked by {ctx.author}")
        except discord.Forbidden:
            return await ctx.deny("I don't have permission to unlock that channel.")
        except discord.HTTPException as e:
            return await ctx.deny(f"Failed: `{e}`")
        await ctx.approve(f"🔓 Unlocked {channel.mention}.")

    @hybrid_command(name="lockall", description="Lock every channel (keep snapshot of previous server)", example=",lockall")
    @commands.guild_only()
    @has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def lockall(self, ctx: commands.Context):
        # snapshot
        embed = discord.Embed(title="Confirm Lockall", description=f"Lock **{len(ctx.guild.text_channels)}** text channels? Previous states will be saved for `,unlockall`.", color=COLORS.warn)
        view = ConfirmView(ctx.author)
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()
        try:
            await msg.delete()
        except Exception:
            pass
        if not view.value:
            return await ctx.warn("Lockall cancelled.")
        locked = 0
        for ch in ctx.guild.text_channels:
            overwrite = ch.overwrites_for(ctx.guild.default_role)
            was_locked = 1 if overwrite.send_messages is False else 0
            # save snapshot
            await self.bot.db.execute(
                "INSERT INTO lock_snapshot (guild_id, channel_id, was_locked) VALUES (?, ?, ?) ON CONFLICT(guild_id, channel_id) DO UPDATE SET was_locked = excluded.was_locked",
                (ctx.guild.id, ch.id, was_locked),
            )
            if was_locked:
                continue
            try:
                await ch.set_permissions(ctx.guild.default_role, send_messages=False, reason=f"Lockall by {ctx.author}")
                locked += 1
            except Exception:
                pass
        await self.bot.db.commit()
        await ctx.approve(f"🔒 Locked **{locked}** channels (snapshot saved).")

    @hybrid_command(name="unlockall", description="Unlock every channel (excluding ones that were locked before)", example=",unlockall")
    @commands.guild_only()
    @has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def unlockall(self, ctx: commands.Context):
        # fetch snapshot
        cursor = await self.bot.db.execute("SELECT channel_id, was_locked FROM lock_snapshot WHERE guild_id = ?", (ctx.guild.id,))
        rows = await cursor.fetchall()
        snapshot = {r["channel_id"]: bool(r["was_locked"]) for r in rows} if rows else {}
        if not snapshot:
            # if no snapshot, unlock all that are currently locked
            to_check = ctx.guild.text_channels
        else:
            to_check = [ch for ch in ctx.guild.text_channels if not snapshot.get(ch.id, False)]
        embed = discord.Embed(title="Confirm Unlockall", description=f"Unlock **{len(to_check)}** channels? (excludes those that were locked before lockall)", color=COLORS.warn)
        view = ConfirmView(ctx.author)
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()
        try:
            await msg.delete()
        except Exception:
            pass
        if not view.value:
            return await ctx.warn("Unlockall cancelled.")
        unlocked = 0
        for ch in to_check:
            overwrite = ch.overwrites_for(ctx.guild.default_role)
            if overwrite.send_messages is not False:
                continue
            try:
                await ch.set_permissions(ctx.guild.default_role, send_messages=None, reason=f"Unlockall by {ctx.author}")
                unlocked += 1
            except Exception:
                pass
        # clear snapshot after unlock
        await self.bot.db.execute("DELETE FROM lock_snapshot WHERE guild_id = ?", (ctx.guild.id,))
        await self.bot.db.commit()
        await ctx.approve(f"🔓 Unlocked **{unlocked}** channels.")

    # ------------------------------------------------------------------ #
    # Purge
    # ------------------------------------------------------------------ #

    INVITE_RE = re.compile(
        r"(?:https?:\/\/)?(?:www\.|ptb\.|canary\.)?discord(?:app)?\.(?:(?:com|gg)[/\\]+(?:invite|servers)[/\\]+[a-z0-9-_]+)|(?:https?://)?(?:www\.)?(?:dsc\.gg|invite\.gg+|discord\.link|(?:discord\.(?:gg|io|me|li|id))|disboard\.org)[/\\]+[a-z0-9-_/]+",
        re.IGNORECASE,
    )
    LINK_RE = re.compile(r"https?://\S+", re.IGNORECASE)
    EMOJI_RE = re.compile(r"<a?:\w+:\d+>")

    def _clamp_amount(self, amount: Optional[int]) -> int:
        if amount is None:
            return 100
        try:
            amount = int(amount)
        except Exception:
            return 100
        return max(1, min(amount, 1000))

    async def _do_purge(self, ctx: commands.Context, amount: int, check=None):
        amount = self._clamp_amount(amount)
        # delete invoking message if possible to keep channel clean? we keep it until purge finishes then it gets deleted if check passes, but we want to ensure command message not counted.
        # Use purge with check; discord.py handles bulk delete limit and 14-day limit.
        deleted = []
        try:
            # Try to delete the invoking message first to avoid it being counted if no check
            # but we keep it for feedback; purge will handle it via before parameter
            if check is None:
                check = lambda m: True  # type: ignore
            # Use channel.purge - it will fetch `amount` messages before ctx.message
            deleted = await ctx.channel.purge(limit=amount, check=check, before=ctx.message, bulk=True)
        except discord.Forbidden:
            return await ctx.deny("I need **Manage Messages** and **Read Message History** in this channel.")
        except discord.HTTPException as e:
            # Fallback for messages older than 14 days: try manual delete
            if "14 days" in str(e).lower() or "14-day" in str(e).lower():
                return await ctx.deny("Cannot bulk delete messages older than 14 days.")
            return await ctx.deny(f"Purge failed: `{e}`")
        except Exception as e:
            return await ctx.deny(f"Purge failed: `{e}`")
        # feedback - auto delete after 5s
        try:
            # Try to delete invoking message if not already deleted
            try:
                await ctx.message.delete()
            except Exception:
                pass
            await ctx.send(embed=discord.Embed(description=f"{ctx.author.mention} purged **{len(deleted)}** messages.", color=COLORS.neutral), delete_after=5)
        except Exception:
            pass

    @commands.hybrid_group(name="purge", aliases=["prune", "clean", "p"], description="Bulk-delete messages", example=",purge 50", invoke_without_command=True)
    @app_commands.describe(amount="Number of messages to purge (default 100)")
    @commands.guild_only()
    @has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def purge(self, ctx: commands.Context, amount: Optional[int] = 100):
        if ctx.invoked_subcommand is None:
            # base purge - delete any messages
            if amount is not None and isinstance(amount, str) and amount.isdigit() is False:
                # Handle case where user passed something like ",purge 50" but converter fails - fallback
                pass
            await self._do_purge(ctx, amount)

    @purge.command(name="embed", description="Purge messages with embeds", example=",purge embed 50")
    @app_commands.describe(amount="Number of messages to scan (default 100)")
    @commands.guild_only()
    @has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def purge_embed(self, ctx: commands.Context, amount: Optional[int] = 100):
        await self._do_purge(ctx, amount, check=lambda m: len(m.embeds) > 0)

    @purge.command(name="humans", description="Purge messages from humans", example=",purge humans 50")
    @app_commands.describe(amount="Number of messages to scan (default 100)")
    @commands.guild_only()
    @has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def purge_humans(self, ctx: commands.Context, amount: Optional[int] = 100):
        await self._do_purge(ctx, amount, check=lambda m: not m.author.bot)

    @purge.command(name="bots", description="Purge messages from bots", example=",purge bots 50")
    @app_commands.describe(amount="Number of messages to scan (default 100)")
    @commands.guild_only()
    @has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def purge_bots(self, ctx: commands.Context, amount: Optional[int] = 100):
        await self._do_purge(ctx, amount, check=lambda m: m.author.bot)

    @purge.command(name="links", description="Purge messages containing links", example=",purge links 50")
    @app_commands.describe(amount="Number of messages to scan (default 100)")
    @commands.guild_only()
    @has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def purge_links(self, ctx: commands.Context, amount: Optional[int] = 100):
        await self._do_purge(ctx, amount, check=lambda m: bool(self.LINK_RE.search(m.content)))

    @purge.command(name="invites", description="Purge discord invite links", example=",purge invites 50")
    @app_commands.describe(amount="Number of messages to scan (default 100)")
    @commands.guild_only()
    @has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def purge_invites(self, ctx: commands.Context, amount: Optional[int] = 100):
        await self._do_purge(ctx, amount, check=lambda m: bool(self.INVITE_RE.search(m.content)))

    @purge.command(name="contains", description="Purge messages containing a word", example=",purge contains hello 50")
    @app_commands.describe(word="Word/phrase to match", amount="Number of messages to scan (default 100)")
    @commands.guild_only()
    @has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def purge_contains(self, ctx: commands.Context, word: str, amount: Optional[int] = 100):
        # For prefix, word may contain spaces if user quoted? Handle as first arg is word, second is amount. If user does ",purge contains hello world" we treat word="hello", amount tries to parse "world" as int -> fallback 100 and word will be incomplete.
        # Better handle flexible prefix: if amount is None and word contains spaces? Actually hybrid will parse word as single word. For phrases, user should quote.
        # Also handle case where amount passed as string inside word for prefix misuse: try to re-parse raw content.
        # If the command was invoked via prefix and amount is actually part of word, we can attempt to extract trailing number from word.
        # But keep simple: word lower match.
        wl = word.lower()
        await self._do_purge(ctx, amount, check=lambda m: wl in m.content.lower())

    @purge.command(name="emojis", description="Purge messages containing emojis", example=",purge emojis 50")
    @app_commands.describe(amount="Number of messages to scan (default 100)")
    @commands.guild_only()
    @has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def purge_emojis(self, ctx: commands.Context, amount: Optional[int] = 100):
        def _check(m: discord.Message) -> bool:
            if self.EMOJI_RE.search(m.content):
                return True
            # unicode emoji check: look for characters in emoji ranges (simple heuristic)
            # count if any char ord > 127 and is not ascii
            for ch in m.content:
                if ord(ch) > 127 and ch not in ("©", "®", "™"):
                    # rough emoji detection: if char is in emoji unicode blocks, treat as emoji
                    # We'll just check if not alphanumeric and not common punctuation
                    if ch.strip() and not ch.isalnum():
                        # Use broader check: if content contains any non-ascii symbol, assume emoji for purge emojis
                        # More accurate: check against emoji ranges
                        o = ord(ch)
                        if 0x1F300 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF or 0x2300 <= o <= 0x23FF:
                            return True
            return False
        await self._do_purge(ctx, amount, check=_check)

    @purge.command(name="mentions", description="Purge messages containing mentions", example=",purge mentions 50")
    @app_commands.describe(amount="Number of messages to scan (default 100)")
    @commands.guild_only()
    @has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def purge_mentions(self, ctx: commands.Context, amount: Optional[int] = 100):
        await self._do_purge(ctx, amount, check=lambda m: len(m.mentions) > 0 or len(m.role_mentions) > 0 or m.mention_everyone)

    @purge.command(name="bulkmentions", description="Purge messages with more than 5 mentions", example=",purge bulkmentions 50")
    @app_commands.describe(amount="Number of messages to scan (default 100)")
    @commands.guild_only()
    @has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def purge_bulkmentions(self, ctx: commands.Context, amount: Optional[int] = 100):
        await self._do_purge(ctx, amount, check=lambda m: (len(m.mentions) + len(m.role_mentions) > 5) or (m.mention_everyone and (len(m.mentions) + len(m.role_mentions) >= 5)))

    @purge.command(name="images", description="Purge messages containing images", example=",purge images 50")
    @app_commands.describe(amount="Number of messages to scan (default 100)")
    @commands.guild_only()
    @has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def purge_images(self, ctx: commands.Context, amount: Optional[int] = 100):
        def _check(m: discord.Message) -> bool:
            # attachments that are images
            for a in m.attachments:
                if a.content_type and a.content_type.startswith("image/"):
                    return True
                if re.search(r"\.(png|jpe?g|gif|webp|bmp|tiff)$", a.filename, re.I):
                    return True
            for e in m.embeds:
                if e.image or e.thumbnail:
                    return True
            if re.search(r"https?://\S+\.(png|jpe?g|gif|webp|bmp)", m.content, re.I):
                return True
            return False
        await self._do_purge(ctx, amount, check=_check)

    @purge.command(name="files", description="Purge messages containing files/attachments", example=",purge files 50")
    @app_commands.describe(amount="Number of messages to scan (default 100)")
    @commands.guild_only()
    @has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def purge_files(self, ctx: commands.Context, amount: Optional[int] = 100):
        await self._do_purge(ctx, amount, check=lambda m: len(m.attachments) > 0)

    @purge.command(name="length", description="Purge messages above a character length", example=",purge length 100 50")
    @app_commands.describe(length="Minimum length", amount="Number of messages to scan (default 100)")
    @commands.guild_only()
    @has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def purge_length(self, ctx: commands.Context, length: int, amount: Optional[int] = 100):
        if length < 1:
            return await ctx.warn("Length must be at least 1.")
        await self._do_purge(ctx, amount, check=lambda m: len(m.content) > length)

    # ------------------------------------------------------------------ #
    # Ghostping (pingonjoin)
    # ------------------------------------------------------------------ #

    @commands.hybrid_group(name="ghostping", aliases=["pingonjoin"], description="Ghostping when someone joins the server", example=",ghostping add #channel 5", invoke_without_command=True)
    @commands.guild_only()
    async def ghostping(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await XryptonHelp.send_group_help(ctx, ctx.command)

    def _parse_delay(self, delay: Optional[str | int]) -> int:
        if delay is None:
            return 1
        if isinstance(delay, int):
            return max(0, min(delay, 86400))
        # try parse as int seconds or duration string
        try:
            iv = int(str(delay).strip())
            return max(0, min(iv, 86400))
        except Exception:
            pass
        td = parse_duration(str(delay))
        if td:
            return max(0, min(int(td.total_seconds()), 86400))
        return 1

    @ghostping.command(name="add", description="Add a ghostping for when someone joins the server", example=",ghostping add #welcome 2")
    @app_commands.describe(channel="Channel to send ghostping in", delay="Delay in seconds before delete (default 1)")
    @commands.guild_only()
    @has_permissions(manage_guild=True)
    async def ghostping_add(self, ctx: commands.Context, channel: discord.TextChannel, delay: Optional[int] = 1):
        delay = self._parse_delay(delay)
        await self.bot.db.execute(
            "INSERT INTO ghostping_config (guild_id, channel_id, delay) VALUES (?, ?, ?) ON CONFLICT(guild_id, channel_id) DO UPDATE SET delay = excluded.delay",
            (ctx.guild.id, channel.id, delay),
        )
        await self.bot.db.commit()
        await ctx.approve(f"Ghostping will be sent in {channel.mention} and deleted after **{delay}s**.")

    @ghostping.command(name="remove", description="Remove ghostping from a channel", example=",ghostping remove #welcome")
    @app_commands.describe(channel="Channel to remove ghostping from")
    @commands.guild_only()
    @has_permissions(manage_guild=True)
    async def ghostping_remove(self, ctx: commands.Context, channel: discord.TextChannel):
        cur = await self.bot.db.execute("DELETE FROM ghostping_config WHERE guild_id = ? AND channel_id = ?", (ctx.guild.id, channel.id))
        await self.bot.db.commit()
        if cur.rowcount == 0:
            return await ctx.warn(f"No ghostping configured for {channel.mention}.")
        await ctx.approve(f"Removed ghostping from {channel.mention}.")

    @ghostping.command(name="list", description="List all ghostping channels", example=",ghostping list")
    @commands.guild_only()
    @has_permissions(manage_guild=True)
    async def ghostping_list(self, ctx: commands.Context):
        cur = await self.bot.db.execute("SELECT channel_id, delay FROM ghostping_config WHERE guild_id = ?", (ctx.guild.id,))
        rows = await cur.fetchall()
        if not rows:
            return await ctx.warn("No ghostping channels configured. Use `,ghostping add #channel [delay]`.")
        lines = []
        for r in rows:
            ch = ctx.guild.get_channel(r["channel_id"])
            ch_str = ch.mention if ch else f"`deleted ({r['channel_id']})`"
            lines.append(f"{ch_str} — delete after **{r['delay']}s**")
        await ctx.embed(title="Ghostping Channels", description="\n".join(lines)[:4096])

    @ghostping.command(name="edit", description="Edit ghostping delay for a channel", example=",ghostping edit #welcome 5")
    @app_commands.describe(channel="Channel to edit", delay="New delay in seconds")
    @commands.guild_only()
    @has_permissions(manage_guild=True)
    async def ghostping_edit(self, ctx: commands.Context, channel: discord.TextChannel, delay: int):
        delay = self._parse_delay(delay)
        cur = await self.bot.db.execute("SELECT 1 FROM ghostping_config WHERE guild_id = ? AND channel_id = ?", (ctx.guild.id, channel.id))
        if not await cur.fetchone():
            return await ctx.warn(f"No ghostping configured for {channel.mention}. Use `,ghostping add` first.")
        await self.bot.db.execute("UPDATE ghostping_config SET delay = ? WHERE guild_id = ? AND channel_id = ?", (delay, ctx.guild.id, channel.id))
        await self.bot.db.commit()
        await ctx.approve(f"Updated ghostping in {channel.mention} to **{delay}s** delay.")

    @ghostping.command(name="reset", description="Remove all ghostping configs", example=",ghostping reset")
    @commands.guild_only()
    @has_permissions(manage_guild=True)
    async def ghostping_reset(self, ctx: commands.Context):
        cur = await self.bot.db.execute("SELECT COUNT(*) as c FROM ghostping_config WHERE guild_id = ?", (ctx.guild.id,))
        row = await cur.fetchone()
        cnt = row["c"] if row else 0
        if cnt == 0:
            return await ctx.warn("No ghostping configs to reset.")
        embed = discord.Embed(title="Confirm Ghostping Reset", description=f"Remove all **{cnt}** ghostping channel(s)?", color=COLORS.warn)
        view = ConfirmView(ctx.author)
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()
        try:
            await msg.delete()
        except Exception:
            pass
        if not view.value:
            return await ctx.warn("Cancelled.")
        await self.bot.db.execute("DELETE FROM ghostping_config WHERE guild_id = ?", (ctx.guild.id,))
        await self.bot.db.commit()
        await ctx.approve(f"Removed **{cnt}** ghostping channel(s).")

    @commands.Cog.listener("on_member_join")
    async def on_member_join_ghostping(self, member: discord.Member):
        # fetch ghostping configs for this guild
        try:
            cur = await self.bot.db.execute("SELECT channel_id, delay FROM ghostping_config WHERE guild_id = ?", (member.guild.id,))
            rows = await cur.fetchall()
        except Exception:
            return
        if not rows:
            return
        for r in rows:
            ch = member.guild.get_channel(r["channel_id"])
            if not isinstance(ch, discord.TextChannel):
                continue
            perms = ch.permissions_for(member.guild.me)
            if not perms.send_messages:
                continue
            try:
                msg = await ch.send(f"{member.mention} welcome!")
                # ghost delete after delay
                delay = int(r["delay"] or 1)
                if delay <= 0:
                    # delete immediately (ghost)
                    try:
                        await msg.delete()
                    except Exception:
                        pass
                else:
                    await asyncio.sleep(delay)
                    try:
                        await msg.delete()
                    except Exception:
                        pass
            except (discord.Forbidden, discord.HTTPException):
                continue

async def setup(bot):
    await bot.add_cog(Moderation(bot))
