from typing import Optional, Callable

import discord
from discord import app_commands
from discord.ext import commands


def has_permissions(**permissions: bool):
    """Allow native Discord permissions or configured fake permissions."""
    if not permissions:
        raise TypeError("has_permissions requires at least one permission")

    invalid = set(permissions) - set(discord.Permissions.VALID_FLAGS)
    if invalid:
        raise TypeError(f"Unknown Discord permission(s): {', '.join(sorted(invalid))}")

    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return False

        if await ctx.bot.is_owner(ctx.author):
            return True

        native_permissions = ctx.author.guild_permissions
        if native_permissions.administrator or all(
            getattr(native_permissions, name) == expected
            for name, expected in permissions.items()
        ):
            return True

        try:
            cursor = await ctx.bot.db.execute(
                "SELECT permissions FROM fake_permission_config WHERE guild_id = ?",
                (ctx.guild.id,),
            )
            row = await cursor.fetchone()
        except Exception:
            return False

        if not row:
            return False

        import json

        try:
            grants = json.loads(row["permissions"] or "{}")
        except (TypeError, ValueError):
            return False

        granted = set()
        for role in ctx.author.roles:
            granted.update(grants.get(str(role.id), []))

        return "administrator" in granted or all(
            (name in granted) == expected
            for name, expected in permissions.items()
        )

    return commands.check(predicate)


def _clean_aliases(name: Optional[str], aliases: Optional[list]) -> list:
    """Strip duplicates/case variants and remove the primary name from aliases."""
    cleaned: list[str] = []
    seen: set[str] = set()
    name_key = name.casefold() if name else None
    for alias in aliases or []:
        if not isinstance(alias, str):
            continue
        key = alias.casefold()
        if key == name_key:
            continue
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(alias)
    return cleaned


def hybrid_command(
    name: Optional[str] = None,
    *,
    aliases: list = None,
    description: Optional[str] = None,
    example: Optional[str] = None,
    **kwargs,
):
    def decorator(func: Callable):
        cmd = commands.hybrid_command(
            name=name,
            aliases=_clean_aliases(name, aliases),
            description=description or func.__doc__ or "",
            help=description or func.__doc__ or "",
            **kwargs,
        )(func)

        if example:
            cmd._example = example

        return cmd

    return decorator


def hybrid_group(
    name: Optional[str] = None,
    *,
    aliases: list = None,
    description: Optional[str] = None,
    example: Optional[str] = None,
    **kwargs,
):
    def decorator(func: Callable):
        cmd = commands.hybrid_group(
            name=name,
            aliases=_clean_aliases(name, aliases),
            description=description or func.__doc__ or "",
            help=description or func.__doc__ or "",
            invoke_without_command=True,
            **kwargs,
        )(func)

        original_callback = cmd.callback

        async def group_callback(cog_self, ctx: commands.Context, *args, **kwargs):
            from core.context import XryptonHelp

            # bare group invocation -> show group help via paginator
            if not args:
                return await XryptonHelp.send_group_help(ctx, ctx.command)
            return await original_callback(cog_self, ctx, *args, **kwargs)

        group_callback.__qualname__ = func.__qualname__
        group_callback.__name__ = func.__name__
        cmd.callback = group_callback

        if example:
            cmd._example = example

        return cmd

    return decorator
