import discord
from discord.interactions import Interaction

from core.config import COLORS, EMOJIS
from core.context import Paginator


class PatchedInteraction(Interaction):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def embed(self, message: str, emoji: str = "", delete_after: float = None):
        return await self.response.send_message(
            embed=discord.Embed(
                description=f"{emoji} {self.user.mention}: {message}",
                color=COLORS.neutral,
            ),
            delete_after=delete_after,
            ephemeral=True,
        )

    async def deny(self, message: str) -> discord.Message:  # type: ignore
        return await self.response.send_message(
            embed=discord.Embed(
                description=f"{EMOJIS.DENY} {self.user.mention}: {message}",
                color=COLORS.neutral,
            ),
            ephemeral=True,
        )  # type: ignore

    async def warn(self, message: str) -> discord.Message:  # type: ignore
        return await self.response.send_message(
            embed=discord.Embed(
                description=f"{EMOJIS.WARN} {self.user.mention}: {message}",
                color=COLORS.neutral,
            ),
            ephemeral=True,
        )  # type: ignore

    async def approve(self, message: str, url: str = None) -> discord.Message:  # type: ignore
        if url is None:
            return await self.response.send_message(
                embed=discord.Embed(
                    description=f"{EMOJIS.APPROVE} {self.user.mention}: {message}",
                    color=COLORS.neutral,
                ),
                ephemeral=True,
            )
        return await self.response.send_message(
            embed=discord.Embed(
                description=f"{EMOJIS.APPROVE} {self.user.mention}: {message}",
                color=COLORS.neutral,
            ).set_image(url=url),
            ephemeral=True,
        )  # type: ignore

    async def paginate(self, embeds: list[discord.Embed], **kwargs) -> None:
        await self.response.send_message(
            embed=embeds[0],
            view=Paginator(self, embeds),
            **kwargs,
        )


Interaction.warn = PatchedInteraction.warn
Interaction.embed = PatchedInteraction.embed
Interaction.deny = PatchedInteraction.deny
Interaction.approve = PatchedInteraction.approve
Interaction.paginate = PatchedInteraction.paginate


class PatchedWebhook(discord.Webhook):
    async def embed(self, message: str, emoji: str = "", delete_after: float = None):
        return await self.send(
            embed=discord.Embed(
                description=f"{emoji} {self.user.mention}: {message}",
                color=COLORS.neutral,
            ),
            ephemeral=True,
        )

    async def deny(self, message: str):
        return await self.send(
            embed=discord.Embed(
                description=f"{EMOJIS.DENY} {self.user.mention}: {message}",
                color=COLORS.neutral,
            ),
            ephemeral=True,
        )

    async def warn(self, message: str, ephemeral: bool = True):
        return await self.send(
            embed=discord.Embed(
                description=f"{EMOJIS.WARN} {self.user.mention}: {message}",
                color=COLORS.neutral,
            ),
            ephemeral=ephemeral,
        )

    async def approve(self, message: str, url: str = None):
        if url is None:
            return await self.send(
                embed=discord.Embed(
                    description=f"{EMOJIS.APPROVE} {self.user.mention}: {message}",
                    color=COLORS.neutral,
                ),
                ephemeral=True,
            )
        return await self.send(
            embed=discord.Embed(
                description=f"{EMOJIS.APPROVE} {self.user.mention}: {message}",
                color=COLORS.neutral,
            ).set_image(url=url),
            ephemeral=True,
        )


discord.Webhook.embed = PatchedWebhook.embed
discord.Webhook.deny = PatchedWebhook.deny
discord.Webhook.warn = PatchedWebhook.warn
discord.Webhook.approve = PatchedWebhook.approve
