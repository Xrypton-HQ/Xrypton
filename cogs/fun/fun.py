import os
import random
import re
import base64
import asyncio
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View

from core.client.commands import hybrid_command, hybrid_group
from core.config import COLORS, EMOJIS

try:
    from fishr import AsyncClient

    FISHR_AVAILABLE = True
except ImportError:
    FISHR_AVAILABLE = False

JEYY_API = "https://api.jeyy.xyz/v2"
JEYY_KEY = os.getenv("JEYY_KEY", "")

try:
    from ddgs import DDGS

    def _run_ddg_text(query: str, max_results: int = 5):
        return list(DDGS().text(query, max_results=max_results))

    def _run_ddg_images(query: str, max_results: int = 5):
        return list(DDGS().images(query, max_results=max_results))
except ImportError:
    def _run_ddg_text(query: str, max_results: int = 5):
        return []

    def _run_ddg_images(query: str, max_results: int = 5):
        return []


class RPSGameView(View):
    def __init__(self, player1, player2, timeout: int = 60):
        self.player1 = player1
        self.player2 = player2
        self.p1_choice = None
        self.p2_choice = None
        self.message = None
        super().__init__(timeout=timeout)

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user not in [self.player1, self.player2]:
            await interaction.response.send_message("You're not part of this game!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Rock", emoji="\U0001faa8", style=discord.ButtonStyle.primary)
    async def rock(self, interaction, button):
        await self.make_choice(interaction, "rock")

    @discord.ui.button(label="Paper", emoji="\U0001f4c4", style=discord.ButtonStyle.primary)
    async def paper(self, interaction, button):
        await self.make_choice(interaction, "paper")

    @discord.ui.button(label="Scissors", emoji="\u2702\ufe0f", style=discord.ButtonStyle.primary)
    async def scissors(self, interaction, button):
        await self.make_choice(interaction, "scissors")

    async def make_choice(self, interaction, choice):
        if interaction.user == self.player1:
            self.p1_choice = choice
        else:
            self.p2_choice = choice

        if self.p1_choice and self.p2_choice:
            result = self._determine_winner(self.p1_choice, self.p2_choice)
            self.stop()
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(content=result, view=self)
        else:
            await interaction.response.send_message(
                f"You chose **{choice.title()}**! Waiting for opponent...",
                ephemeral=True,
            )

    def _determine_winner(self, p1, p2):
        if p1 == p2:
            return f"\U0001f91d It's a tie! Both chose **{p1.title()}**!"
        wins = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
        if wins[p1] == p2:
            return f"\U0001f3c5 {self.player1.mention} wins! **{p1.title()}** beats **{p2.title()}**!"
        return f"\U0001f3c5 {self.player2.mention} wins! **{p2.title()}** beats **{p1.title()}**!"

    async def on_timeout(self):
        if self.message:
            for child in self.children:
                child.disabled = True
            try:
                await self.message.edit(content="\u23f1\ufe0f Game expired!", view=self)
            except Exception:
                pass


class RPSAIView(View):
    def __init__(self, player, timeout: int = 60):
        self.player = player
        self.message = None
        super().__init__(timeout=timeout)

    @discord.ui.button(label="Rock", emoji="\U0001faa8", style=discord.ButtonStyle.primary)
    async def rock(self, interaction, button):
        await self.play(interaction, "rock")

    @discord.ui.button(label="Paper", emoji="\U0001f4c4", style=discord.ButtonStyle.primary)
    async def paper(self, interaction, button):
        await self.play(interaction, "paper")

    @discord.ui.button(label="Scissors", emoji="\u2702\ufe0f", style=discord.ButtonStyle.primary)
    async def scissors(self, interaction, button):
        await self.play(interaction, "scissors")

    async def play(self, interaction, choice):
        ai_choice = random.choice(["rock", "paper", "scissors"])
        result = self._determine_winner(choice, ai_choice)
        self.stop()
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content=result, view=self)

    def _determine_winner(self, player, ai):
        if player == ai:
            return f"\U0001f91d It's a tie! Both chose **{player.title()}**!"
        wins = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
        if wins[player] == ai:
            return f"\U0001f3c5 You win! **{player.title()}** beats **{ai.title()}**!"
        return f"\U0001f916 AI wins! **{ai.title()}** beats **{player.title()}**!"

    async def on_timeout(self):
        if self.message:
            for child in self.children:
                child.disabled = True
            try:
                await self.message.edit(content="\u23f1\ufe0f Game expired!", view=self)
            except Exception:
                pass


class RPSChallengeView(View):
    def __init__(self, challenger, opponent, timeout: int = 60):
        self.challenger = challenger
        self.opponent = opponent
        self.message = None
        super().__init__(timeout=timeout)

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green, emoji="\u2694\ufe0f")
    async def accept(self, interaction, button):
        if interaction.user != self.opponent:
            await interaction.response.send_message("You're not the challenged user!", ephemeral=True)
            return

        self.stop()
        game_view = RPSGameView(self.challenger, self.opponent)
        await interaction.response.edit_message(
            content=f"\u2694\ufe0f {self.challenger.mention} vs {self.opponent.mention}\nBoth players, make your choice!",
            view=game_view,
        )
        game_view.message = interaction.message

    async def on_timeout(self):
        if self.message:
            for child in self.children:
                child.disabled = True
            try:
                await self.message.edit(content="\u23f1\ufe0f Challenge expired!", view=self)
            except Exception:
                pass


class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._fishr_client = None

    @property
    def fishr(self):
        if not FISHR_AVAILABLE:
            return None
        if self._fishr_client is None:
            self._fishr_client = AsyncClient()
        return self._fishr_client

    @hybrid_command(aliases=["8ball"], description="Ask the AI-powered 8ball a question")
    async def ball(self, ctx, *, question: str):
        if not self.fishr:
            return await ctx.warn("AI is currently unavailable. Please install fishr.")

        try:
            response = await self.fishr.chat.completions.create(
                model="noxus/openai",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a mystic 8ball. Answer any question with a cryptic, short prophecy (1-2 sentences). Only respond with the prophecy, no extra text or explanations.",
                    },
                    {"role": "user", "content": question},
                ],
            )
            answer = response.text.strip()
            embed = discord.Embed(
                title="\U0001f3b1 Magic 8-Ball",
                color=COLORS.neutral,
            )
            embed.add_field(name="Question", value=question, inline=False)
            embed.add_field(name="Answer", value=answer, inline=False)
            embed.set_footer(
                text=f"Asked by {ctx.author.display_name}",
                icon_url=ctx.author.display_avatar.url,
            )
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.deny(f"Failed to get an answer: {e}")

    @hybrid_command(description="Roll a dice")
    async def dice(self, ctx):
        result = random.randint(1, 6)
        dice_emojis = {1: "\u2680", 2: "\u2681", 3: "\u2682", 4: "\u2683", 5: "\u2684", 6: "\u2685"}
        await ctx.embed(
            title="\U0001f3b2 Dice Roll",
            description=f"You rolled a **{result}**! {dice_emojis[result]}",
            color=COLORS.neutral,
        )

    @hybrid_command(aliases=["rockpaperscissors"], description="Play rock paper scissors")
    async def rps(self, ctx, user: Optional[discord.Member] = None):
        if user is None:
            view = RPSAIView(ctx.author)
            msg = await ctx.send("\U0001f916 Playing against **AI**! Choose your move:", view=view)
            view.message = msg
            return

        if user == ctx.author:
            return await ctx.warn("You can't play against yourself!")

        view = RPSChallengeView(ctx.author, user)
        msg = await ctx.send(
            f"\u2694\ufe0f {ctx.author.mention} has challenged {user.mention} to Rock Paper Scissors!\n{user.mention}, do you accept?",
            view=view,
        )
        view.message = msg

    @hybrid_group(name="base64", aliases=["b64"], description="Base64 encoder/decoder commands")
    async def base64(self, ctx):
        if ctx.invoked_subcommand is None:
            from core.context import XryptonHelp
            await XryptonHelp.send_group_help(ctx, ctx.command)

    @base64.command(name="encode", description="Encode text to base64")
    async def base64_encode(self, ctx, *, message: str):
        encoded = base64.b64encode(message.encode()).decode()
        await ctx.embed(
            title="Base64 Encode",
            description=f"**Input:** {message}\n**Output:** `{encoded}`",
            color=COLORS.neutral,
        )

    @base64.command(name="decode", description="Decode base64 back to text")
    async def base64_decode(self, ctx, *, base64_string: str):
        try:
            decoded = base64.b64decode(base64_string).decode()
            await ctx.embed(
                title="Base64 Decode",
                description=f"**Input:** `{base64_string}`\n**Output:** {decoded}",
                color=COLORS.neutral,
            )
        except Exception:
            await ctx.deny("Invalid base64 string.")

    @hybrid_command(aliases=["cf"], description="Flip a coin")
    async def coinflip(self, ctx):
        result = random.choice(["Heads", "Tails"])
        emoji = "\U0001f3f4\U0000200d\U00002663\ufe0f" if result == "Heads" else "\U0001f3f4\U0000200d\U00002660\ufe0f"
        await ctx.embed(
            title="\U0001fa99 Coin Flip",
            description=f"The coin landed on **{result}**! {emoji}",
            color=COLORS.neutral,
        )

    @hybrid_command(description="Steal an emoji from another server")
    async def steal(self, ctx, emoji: Optional[str] = None):
        if not emoji:
            if ctx.message.reference:
                try:
                    ref = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                    emoji = ref.content
                except Exception:
                    pass

            if not emoji:
                return await ctx.warn("Please provide an emoji or reply to a message containing one.")

        match = re.search(r"<(a?):(\w+):(\d+)>", emoji)
        if not match:
            return await ctx.deny("That doesn't look like a valid custom emoji.")

        animated, name, emoji_id = match.groups()
        ext = "gif" if animated else "png"
        url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return await ctx.deny("Failed to fetch that emoji.")
                    data = await resp.read()

            if len(data) > 256 * 1024:
                return await ctx.deny("That emoji is too large to add.")

            try:
                added = await ctx.guild.create_custom_emoji(name=name, image=data)
                await ctx.approve(f"Added emoji **:{name}:** `{added}`")
            except discord.Forbidden:
                await ctx.deny("I need the **Manage Emojis** permission to add emojis.")
            except discord.HTTPException as e:
                await ctx.deny(f"Failed to add emoji: {e}")
        except Exception as e:
            await ctx.deny(f"Something went wrong: {e}")

    @hybrid_command(aliases=["pp", "dih"], description="Check your dih size")
    async def dick(self, ctx, user: Optional[discord.Member] = None):
        target = user or ctx.author
        length = random.randint(1, 15)
        bar = "8" + "=" * length + "D"
        inches = round(length / 2 + 1, 1)
        await ctx.embed(
            title=f"\U0001f3a9 {target.display_name}'s DIH",
            description=f"**{bar}**\n**{inches}\"**",
            color=COLORS.neutral,
        )

    @hybrid_command(description="Search for an image")
    async def image(self, ctx, *, query: str):
        try:
            results = _run_ddg_images(query, max_results=5)
        except Exception:
            results = []

        if not results:
            return await ctx.deny("No images found.")

        embeds = []
        for result in results:
            embed = discord.Embed(
                title=result.get("title", "Image Result"),
                url=result.get("link"),
                color=COLORS.neutral,
            )
            embed.set_image(url=result.get("image"))
            embeds.append(embed)

        if len(embeds) == 1:
            await ctx.send(embed=embeds[0])
        else:
            await ctx.paginate(embeds)

    @hybrid_command(description="Search the web")
    async def search(self, ctx, *, query: str):
        try:
            results = _run_ddg_text(query, max_results=5)
        except Exception:
            results = []

        if not results:
            return await ctx.deny("No results found.")

        lines = []
        for result in results:
            title = result.get("title", "No title")
            href = result.get("href", result.get("link", ""))
            lines.append(f"**[{title}]({href})**")

        await ctx.embed(
            title=f"Search: {query}",
            description="\n".join(lines),
            color=COLORS.neutral,
        )

    @hybrid_command(description="AI-powered packgod style roast")
    async def humble(self, ctx, *, roast: str):
        if not self.fishr:
            return await ctx.warn("AI is currently unavailable. Please install fishr.")

        try:
            response = await self.fishr.chat.completions.create(
                model="noxus/openai",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a packgod-style roaster. Generate a short, silly, ALL CAPS roast for the target. Start with SHUT YO. Include emojis. Keep it playful and non-offensive.",
                    },
                    {"role": "user", "content": f"Target: {roast}"},
                ],
            )
            await ctx.send(response.text.strip())
        except Exception as e:
            await ctx.deny(f"Failed to generate roast: {e}")

    @hybrid_command(description="Search Urban Dictionary")
    async def urban(self, ctx, *, query: str):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://api.urbandictionary.com/v0/define?term={discord.utils.escape_markdown(query)}") as resp:
                    if resp.status != 200:
                        return await ctx.deny("Failed to fetch Urban Dictionary.")
                    data = await resp.json()
        except Exception as e:
            return await ctx.deny(f"Something went wrong: {e}")

        if not data.get("list"):
            return await ctx.deny("No results found.")

        top = data["list"][0]
        embed = discord.Embed(
            title=top.get("word", query),
            url=top.get("permalink"),
            color=COLORS.neutral,
        )
        definition = top.get("definition", "No definition.")
        example = top.get("example", "No example.")
        embed.add_field(name="Definition", value=definition[:1024], inline=False)
        embed.add_field(name="Example", value=example[:1024], inline=False)
        embed.set_footer(text=f"👍 {top.get('thumbs_up', 0)} | 👎 {top.get('thumbs_down', 0)}")
        await ctx.send(embed=embed)

    @hybrid_command(description="How gay is someone?")
    async def howgay(self, ctx, user: Optional[discord.Member] = None):
        target = user or ctx.author
        if target.id in getattr(self.bot, "owner_ids", []) or target.id == self.bot.user.id:
            percent = 100
        else:
            percent = random.randint(0, 100)

        bar = "█" * (percent // 5) + "░" * (20 - percent // 5)
        await ctx.embed(
            title="\U0001f308 How Gay?",
            description=f"{target.mention} is **{percent}%** gay\n`{bar}`",
            color=COLORS.neutral,
        )

    @hybrid_command(aliases=["dickr", "ppr"], description="Check your real dih size")
    async def dihr(self, ctx):
        length = 67
        bar = "8" + "=" * length + "D"
        await ctx.embed(
            title="\U0001f3a9 Real DIH Checker",
            description=f"**{bar}**\n**67 inches**",
            color=COLORS.neutral,
        )

    async def _jeyy_request(self, endpoint: str, params: Optional[dict] = None):
        if not JEYY_KEY:
            return None
        headers = {"Authorization": f"Bearer {JEYY_KEY}"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{JEYY_API}{endpoint}", headers=headers, params=params) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception:
            pass
        return None

    @hybrid_group(name="fun", description="Jeyy image effects")
    async def fun(self, ctx):
        if ctx.invoked_subcommand is None:
            from core.context import XryptonHelp
            await XryptonHelp.send_group_help(ctx, ctx.command)

    @fun.command(description="ASCII text style")
    async def ascii(self, ctx, *, text: str):
        data = await self._jeyy_request("/discord/ansi", {"text": text, "bold": True, "codeblock": True})
        if not data:
            return await ctx.deny("JeyyAPI is unavailable or missing API key.")
        image_url = data.get("url")
        if not image_url:
            return await ctx.deny("No image returned.")
        await ctx.send(image_url)

    @fun.command(description="Discord player card")
    async def player(self, ctx, title: str, seconds_played: int, total_seconds: int, thumbnail_url: Optional[str] = None):
        if not thumbnail_url:
            thumbnail_url = ctx.author.display_avatar.url
        data = await self._jeyy_request(
            "/discord/player",
            {"title": title, "thumbnail_url": thumbnail_url, "seconds_played": seconds_played, "total_seconds": total_seconds},
        )
        if not data:
            return await ctx.deny("JeyyAPI is unavailable or missing API key.")
        image_url = data.get("url")
        if not image_url:
            return await ctx.deny("No image returned.")
        await ctx.send(image_url)

    @fun.command(description="Discord Spotify card")
    async def spotifycard(self, ctx, title: str, cover_url: str, duration_seconds: int, start_timestamp: float, artists: str):
        artist_list = [a.strip() for a in artists.split(",") if a.strip()]
        data = await self._jeyy_request(
            "/discord/spotify",
            {
                "title": title,
                "cover_url": cover_url,
                "duration_seconds": duration_seconds,
                "start_timestamp": start_timestamp,
                "artists": artist_list,
            },
        )
        if not data:
            return await ctx.deny("JeyyAPI is unavailable or missing API key.")
        image_url = data.get("url")
        if not image_url:
            return await ctx.deny("No image returned.")
        await ctx.send(image_url)

    @fun.command(description="Spin wheel")
    async def wheel(self, ctx, *, options: str):
        args = [a.strip() for a in options.replace(",", " ").split() if a.strip()]
        if len(args) < 2:
            return await ctx.warn("Please provide at least 2 options.")
        data = await self._jeyy_request("/discord/wheel", {"args": args})
        if not data:
            return await ctx.deny("JeyyAPI is unavailable or missing API key.")
        image_url = data.get("url")
        if not image_url:
            return await ctx.deny("No image returned.")
        await ctx.send(image_url)

    async def _jeyy_image(self, ctx, endpoint: str, params: Optional[dict] = None):
        if not ctx.message.attachments:
            return await ctx.warn("Please attach an image.")
        attachment = ctx.message.attachments[0]
        if not attachment.content_type or not attachment.content_type.startswith("image/"):
            return await ctx.warn("That attachment is not an image.")

        upload_url = f"{JEYY_API}/general/image_upload"
        try:
            form = aiohttp.FormData()
            form.add_field("image", await attachment.read(), filename=attachment.filename, content_type=attachment.content_type)
            async with aiohttp.ClientSession() as session:
                async with session.post(upload_url, headers={"Authorization": f"Bearer {JEYY_KEY}"}, data=form) as resp:
                    if resp.status != 200:
                        return await ctx.deny("Failed to upload image.")
                    upload_data = await resp.json()
                    image_url = upload_data.get("url")
        except Exception:
            return await ctx.deny("Something went wrong while uploading the image.")

        if not image_url:
            return await ctx.deny("No URL returned from image upload.")

        endpoint_params = {"image_url": image_url}
        if params:
            endpoint_params.update(params)

        data = await self._jeyy_request(endpoint, endpoint_params)
        if not data:
            return await ctx.deny("JeyyAPI image endpoint failed.")
        result_url = data.get("url")
        if not result_url:
            return await ctx.deny("No image result returned.")
        await ctx.send(result_url)

    @fun.command(description="Scrapbook text image")
    async def jeyyscrapbook(self, ctx, text: str):
        data = await self._jeyy_request("/image/scrapbook", {"text": text[:20]})
        if not data:
            return await ctx.deny("JeyyAPI is unavailable or missing API key.")
        image_url = data.get("url")
        if not image_url:
            return await ctx.deny("No image returned.")
        await ctx.send(image_url)

    @fun.command(description="Glitch effect on an image")
    async def jeyyglitch(self, ctx, level: Optional[int] = 3):
        await self._jeyy_image(ctx, "/image/glitch", {"level": level})

    @fun.command(description="Fire effect on an image")
    async def jeyyfire(self, ctx):
        await self._jeyy_image(ctx, "/image/fire")

    @fun.command(description="Neon effect on an image")
    async def jeyyneon(self, ctx):
        await self._jeyy_image(ctx, "/image/neon")

    @fun.command(description="Bomb effect on an image")
    async def jeyybomb(self, ctx):
        await self._jeyy_image(ctx, "/image/bomb")

    @fun.command(description="Bonks effect on an image")
    async def jeyybonks(self, ctx):
        await self._jeyy_image(ctx, "/image/bonks")

    @fun.command(description="Cartoon effect on an image")
    async def jeyycartoon(self, ctx):
        await self._jeyy_image(ctx, "/image/cartoon")


async def setup(bot):
    await bot.add_cog(Fun(bot))
