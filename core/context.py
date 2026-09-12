from typing import Any, Dict, List, Optional, TYPE_CHECKING

import discord
from discord import ButtonStyle, Embed
from discord.ext import commands
from discord.ui import Button, Select, View

from core.config import COLORS, EMOJIS

if TYPE_CHECKING:
    from core.Xrypton import Xrypton

# --------------------------------------------------------------------------- #
#  ANSI helpers                                                               #
# --------------------------------------------------------------------------- #
_RESET = "\033[0m"


def _ansi(value: str, *codes: int) -> str:
    """Wrap *value* with the given ANSI escape codes (renders in ```ansi blocks)."""
    prefix = "".join(f"\033[{code}m" for code in codes)
    return f"{prefix}{value}{_RESET}"


class XryptonHelp:
    @staticmethod
    def command_description(command: commands.Command) -> str:
        return command.help or getattr(command, "description", None) or "No description"

    @staticmethod
    def command_permission(command: commands.Command) -> str:
        found: List[str] = []

        def _register(name: str) -> None:
            label = name.replace("_", " ").title()
            if label not in found:
                found.append(label)

        def _collect(value: Any) -> None:
            if isinstance(value, dict):
                for name, allowed in value.items():
                    if allowed and name in discord.Permissions.VALID_FLAGS:
                        _register(name)
            elif isinstance(value, discord.Permissions):
                for name, allowed in value:
                    if allowed and name in discord.Permissions.VALID_FLAGS:
                        _register(name)

        for check in getattr(command, "checks", []) or []:
            for cell in getattr(check, "__closure__", None) or ():
                try:
                    _collect(cell.cell_contents)
                except ValueError:
                    continue
        return ", ".join(found) if found else "N/A"

    @staticmethod
    def collect_commands(cog: commands.Cog) -> List[commands.Command]:
        """Return every leaf command of a cog with its full qualified path (no duplicate group shells)."""
        leaves = []
        for cmd in cog.walk_commands():
            if isinstance(cmd, commands.Group) and cmd.commands:
                continue  # group shells are implied by their subcommands
            leaves.append(cmd)
        return sorted(leaves, key=lambda c: c.qualified_name)

    @staticmethod
    def build_help_embed(bot: "Xrypton", cog_name: Optional[str] = None) -> Embed:
        embed = Embed(
            title="Help",
            description="Select a plugin from the dropdown below to view its commands.",
            color=COLORS.neutral,
        )

        if cog_name and cog_name != "Index":
            cog = next(
                (c for c in bot.cogs.values() if c.qualified_name.lower() == cog_name.lower()),
                None,
            )
            if cog is None:
                embed.description = f"No plugin found for **{cog_name}**"
                return embed

            commands_list = XryptonHelp.collect_commands(cog)
            if commands_list:
                embed.title = f"{cog.qualified_name} Commands"
                lines = [
                    f"`{cmd.qualified_name}` - {XryptonHelp.command_description(cmd)}"
                    for cmd in commands_list
                ]
                embed.description = "\n".join(lines)[:4096]
            else:
                embed.description = f"No commands found for **{cog_name}**"
        else:
            embed.title = "Help Index"
            embed.description = "Browse all available plugins from the dropdown below."
            for cog in bot.cogs.values():
                if cog.qualified_name == "HelpCog":
                    continue
                cmd_count = len(XryptonHelp.collect_commands(cog))
                embed.add_field(
                    name=f"• {cog.qualified_name}",
                    value=f"_{cmd_count} command{'s' if cmd_count != 1 else ''}_",
                    inline=True,
                )

        total_commands = sum(len(XryptonHelp.collect_commands(cog)) for name, cog in bot.cogs.items() if name != "HelpCog")
        embed.set_footer(text=f"{total_commands} total commands")
        return embed

    @staticmethod
    async def send_bot_help(ctx: commands.Context) -> discord.Message:
        bot: Xrypton = ctx.bot

        initial_cogs = [name for name in bot.cogs.keys() if name != "HelpCog"]

        total_commands = sum(
            len(XryptonHelp.collect_commands(cog))
            for name, cog in bot.cogs.items()
            if name != "HelpCog"
        )
        total_categories = len(initial_cogs)

        embed = (
            discord.Embed(
                color=COLORS.neutral,
                description=(
                    "## Xrypton Help\n"
                    "Welcome to **Xrypton**, a free all-in one bot for every community.\n"
                    f"> {total_commands} commands from {total_categories} categories\n"
                ),
            )
            .set_thumbnail(url="https://zne.breed.rip/assets/xrypton/avatar.png")
            .set_footer(
                text="Choose a plugin from the dropdown below.",
            )
        )
        view = HelpView(ctx, bot, initial_cogs, None)

        return await ctx.send(embed=embed, view=view)

    @staticmethod
    async def send_command_help(ctx: commands.Context, command: commands.Command) -> discord.Message:
        author = ctx.author
        author_name = getattr(author, "display_name", None) or getattr(author, "name", "N/A")
        author_avatar = getattr(getattr(author, "display_avatar", None), "url", None)
        module = getattr(command, "cog_name", None) or getattr(command, "cog", None)
        module = module if isinstance(module, str) else (module.qualified_name if module else "N/A")

        parent = f"{command.parent.name} " if command.parent else ""
        syntax = f",{parent}{command.name} {command.signature}".strip()
        example = getattr(command, "_example", None) or f",{parent}{command.name}"
        aliases = ", ".join(command.aliases) if command.aliases else "N/A"
        parameters = command.signature or "N/A"

        embed = (
            discord.Embed(
                title=f"Command: {command.qualified_name}",
                description=XryptonHelp.command_description(command),
                color=COLORS.neutral,
            )
            .set_author(
                name=author_name,
                icon_url=author_avatar,
            )
            .set_footer(
                text=f"Page 1/1 (1 entries) \u2219 Module: {module}",
            )
            .add_field(
                name="Aliases",
                value=aliases,
                inline=True,
            )
            .add_field(
                name="Parameters",
                value=parameters,
                inline=True,
            )
            .add_field(
                name="Permissions",
                value=f"{EMOJIS.WARN} {XryptonHelp.command_permission(command)}",
                inline=True,
            )
            .add_field(
                name="Usage",
                value=(
                    f"```ansi\n"
                    f"{_ansi('Syntax:', 32)} {_ansi(syntax, 34)}\n"
                    f"{_ansi('Example:', 32)} {_ansi(example, 90)}\n"
                    f"```"
                ),
                inline=False,
            )
        )

        return await ctx.send(embed=embed)

    @staticmethod
    async def send_group_help(ctx: commands.Context, group: commands.Group) -> discord.Message:
        if not group.commands:
            return await XryptonHelp.send_command_help(ctx, group)

        author = ctx.author
        author_name = getattr(author, "display_name", None) or getattr(author, "name", "N/A")
        author_avatar = getattr(getattr(author, "display_avatar", None), "url", None)
        module = getattr(group, "cog_name", None) or getattr(group, "cog", None)
        module = module if isinstance(module, str) else (module.qualified_name if module else "N/A")

        subcommands = list(group.commands)
        total = len(subcommands)

        pages = []
        for index, subcommand in enumerate(subcommands, start=1):
            parent = f"{group.name} " if subcommand.parent else ""
            syntax = f",{parent}{subcommand.name} {subcommand.signature}".strip()
            example = getattr(subcommand, "_example", None) or f",{parent}{subcommand.name}"
            aliases = ", ".join(subcommand.aliases) if subcommand.aliases else "N/A"
            parameters = subcommand.signature or "N/A"

            embed = (
                discord.Embed(
                    title=f"Group Command: {subcommand.qualified_name}",
                    description=XryptonHelp.command_description(subcommand),
                    color=COLORS.neutral,
                )
                .set_author(
                    name=author_name,
                    icon_url=author_avatar,
                )
                .set_footer(
                    text=f"Page {index}/{total} ({total} entries) ∙ Module: {module}",
                )
                .add_field(
                    name="Aliases",
                    value=aliases,
                    inline=True,
                )
                .add_field(
                    name="Parameters",
                    value=parameters,
                    inline=True,
                )
                .add_field(
                    name="Permission",
                    value=f"{EMOJIS.WARN} {XryptonHelp.command_permission(group)}",
                    inline=True,
                )
                .add_field(
                    name="Usage",
                    value=(
                        f"```ansi\n"
                        f"{_ansi('Syntax:', 32)} {_ansi(syntax, 34)}\n"
                        f"{_ansi('Example:', 32)} {_ansi(example, 90)}\n"
                        f"```"
                    ),
                    inline=False,
                )
            )
            pages.append(embed)

        return await ctx.paginate(pages)


class HelpSelect(Select):
    def __init__(self, bot: "Xrypton", cog_names: List[str], current: Optional[str]):
        options = [
            discord.SelectOption(
                label="Index",
                value="Index",
                default=(current == "Index"),
            )
        ]
        for name in cog_names:
            options.append(
                discord.SelectOption(
                    label=name,
                    value=name,
                    default=(name == current),
                )
            )
        super().__init__(
            placeholder="Select a plugin...",
            options=options,
            custom_id="HELP:COG_SELECT",
            row=0,
        )
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        # Acknowledge immediately so Discord never shows "did not respond"
        await interaction.response.defer()
        try:
            selected = self.values[0]
            embed = XryptonHelp.build_help_embed(self.bot, selected)

            for child in self.view.children:
                if isinstance(child, Select) and child.custom_id == "HELP:COG_SELECT":
                    for option in child.options:
                        option.default = option.value == selected

            await interaction.message.edit(embed=embed, view=self.view)
        except Exception:
            import traceback

            traceback.print_exc()
            try:
                await interaction.message.edit(
                    embed=discord.Embed(
                        description="⚠️ Something went wrong while loading that plugin's commands.",
                        color=COLORS.warn,
                    ),
                    view=self.view,
                )
            except discord.HTTPException:
                pass


class HelpView(View):
    def __init__(self, ctx: commands.Context, bot: "Xrypton", cog_names: List[str], current: Optional[str]):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.add_item(HelpSelect(bot, cog_names, current))

    async def interaction_check(self, interaction: discord.Interaction[discord.Client]) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.warn("You're not the **author** of this menu!")
            return False
        return True


class PaginatorButton(Button):
    def __init__(self, style: ButtonStyle, emoji: str, custom_id: str = None):
        # An empty string is not a valid emoji for Discord's API; treat it as "no emoji".
        super().__init__(style=style, custom_id=custom_id, emoji=emoji or None)

    async def callback(self, interaction: discord.Interaction):
        if self.custom_id == "previous":
            return await self.previous(interaction)
        if self.custom_id == "next":
            return await self.next(interaction)
        if self.custom_id == "pages":
            return await self.pages(interaction)
        if self.custom_id == "cancel":
            return await self.cancel(interaction)

    async def previous(self, interaction: discord.Interaction):
        if self.view.current == 0:
            self.view.current = len(self.view.pages) - 1
        else:
            self.view.current -= 1
        await interaction.response.edit_message(
            embed=self.view.pages[self.view.current]
        )

    async def next(self, interaction: discord.Interaction):
        if self.view.current == len(self.view.pages) - 1:
            self.view.current = 0
        else:
            self.view.current += 1
        await interaction.response.edit_message(
            embed=self.view.pages[self.view.current]
        )

    async def cancel(self, interaction: discord.Interaction):
        self.view.stop()
        await interaction.message.delete()

    async def pages(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PagesModal(self.view))


class PagesModal(discord.ui.Modal, title="Select Page"):
    def __init__(self, view):
        super().__init__()
        self.view = view
        self.selector = discord.ui.TextInput(
            label="Page",
            placeholder="5",
            custom_id="PAGINATOR:PAGES",
            style=discord.TextStyle.short,
            min_length=1,
            max_length=3,
            required=True,
            row=0,
        )
        self.add_item(self.selector)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            page = int(self.selector.value)
        except ValueError:
            await interaction.warn("Please provide a valid page number.")
            return
        if page < 1 or page > len(self.view.pages):
            await interaction.warn("Please provide a valid page number.")
            return
        self.view.current = page - 1
        await interaction.response.edit_message(
            embed=self.view.pages[self.view.current]
        )


class Paginator(View):
    def __init__(
        self,
        ctx,
        pages: list[discord.Embed],
        current: int = 0,
    ):
        self.ctx = ctx
        self.pages = pages
        self.current = current
        super().__init__(timeout=10)

        self.add_item(
            PaginatorButton(
                style=discord.ButtonStyle.blurple,
                custom_id="previous",
                emoji=EMOJIS.PREVIOUS,
            )
        )
        self.add_item(
            PaginatorButton(
                style=discord.ButtonStyle.blurple,
                custom_id="next",
                emoji=EMOJIS.NEXT,
            )
        )
        self.add_item(
            PaginatorButton(
                style=discord.ButtonStyle.grey,
                custom_id="pages",
                emoji=EMOJIS.NAVIGATE,
            )
        )
        self.add_item(
            PaginatorButton(
                style=discord.ButtonStyle.danger,
                custom_id="cancel",
                emoji=EMOJIS.CANCEL,
            )
        )

    async def interaction_check(
        self, interaction: discord.Interaction[discord.Client]
    ) -> bool:
        if interaction.user.id != getattr(self.ctx, "author", interaction.user).id:
            await interaction.warn("You're not the **author** of this embed!")
            return False
        return True


class Context(commands.Context):
    bot: "Xrypton"

    async def embed(self, **kwargs) -> discord.Message:
        return await self.send(**self.create(**kwargs))

    def create(self, **kwargs) -> Dict[str, Any]:
        view = View()

        for button in kwargs.get("buttons") or []:
            if not button or not button.get("label"):
                continue
            view.add_item(Button(
                label=button.get("label"),
                style=button.get("style") or ButtonStyle.secondary,
                emoji=button.get("emoji"),
                url=button.get("url"),
            ))

        embed = (
            Embed(
                url=kwargs.get("url"),
                description=kwargs.get("description"),
                title=kwargs.get("title"),
                color=kwargs.get("color") or COLORS.neutral,
                timestamp=kwargs.get("timestamp"),
            )
            .set_image(url=kwargs.get("image"))
            .set_thumbnail(url=kwargs.get("thumbnail"))
            .set_footer(
                text=kwargs.get("footer", {}).get("text"),
                icon_url=kwargs.get("footer", {}).get("icon_url"),
            )
            .set_author(
                name=kwargs.get("author", {}).get("name", ""),
                icon_url=kwargs.get("author", {}).get("icon_url", ""),
            )
        )

        for field in kwargs.get("fields") or []:
            if not field:
                continue
            embed.add_field(
                name=field.get("name"),
                value=field.get("value"),
                inline=field.get("inline", False),
            )

        return {
            "content": kwargs.get("content"),
            "embed": embed,
            "view": kwargs.get("view") or view,
            "delete_after": kwargs.get("delete_after"),
        }

    async def _config_emoji(self, column: str, fallback: str) -> str:
        try:
            cursor = await self.bot.db.execute(
                f"SELECT {column} FROM bot_config WHERE id = 1"
            )
            row = await cursor.fetchone()
            if row and row[column]:
                return row[column]
        except Exception:
            pass
        return fallback

    async def approve(self, message: str, **kwargs) -> discord.Message:
        emoji = await self._config_emoji("emoji_approve", EMOJIS.APPROVE)
        return await self.send(
            embed=Embed(
                color=COLORS.approve,
                description=f"{emoji} {self.author.mention}: {message}",
            ),
            **kwargs,
        )

    async def warn(self, message: str, **kwargs) -> discord.Message:
        emoji = await self._config_emoji("emoji_warn", EMOJIS.WARN)
        return await self.send(
            embed=Embed(
                color=COLORS.warn,
                description=f"{emoji} {self.author.mention}: {message}",
            ),
            **kwargs,
        )

    async def deny(self, message: str, **kwargs) -> discord.Message:
        emoji = await self._config_emoji("emoji_deny", EMOJIS.DENY)
        return await self.send(
            embed=Embed(
                color=COLORS.deny,
                description=f"{emoji} {self.author.mention}: {message}",
            ),
            **kwargs,
        )

    async def paginate(self, embeds: List[discord.Embed], **kwargs) -> discord.Message:
        if len(embeds) == 1:
            if isinstance(embeds[0], discord.Embed):
                return await self.send(embed=embeds[0], **kwargs)
        return await self.send(embed=embeds[0], view=Paginator(self, embeds), **kwargs)