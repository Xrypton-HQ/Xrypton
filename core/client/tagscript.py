from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING, Optional, Union

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from core.Xrypton import Xrypton


PST_OFFSET = timezone(timedelta(hours=-8))
UTC_ZONE = timezone.utc


class TagScriptParser:
    GUILD_VARS = {
        "{guild.name}", "{guild}", "{server}", "{server.name}",
        "{guild.id}", "{guild.owner_id}", "{guild.owner}",
        "{guild.created_at}", "{guild.created_at_timestamp}",
        "{guild.region}", "{guild.shard}",
        "{guild.emoji_count}", "{guild.role_count}",
        "{guild.boost_count}", "{guild.boost_tier}",
        "{guild.preferred_locale}", "{guild.key_features}",
        "{guild.icon}", "{guild.banner}", "{guild.splash}",
        "{guild.discovery}", "{guild.max_presences}",
        "{guild.max_members}", "{guild.max_video_channel_users}",
        "{guild.afk_timeout}", "{guild.afk_channel}",
        "{guild.channels_count}", "{guild.text_channels_count}",
        "{guild.voice_channels_count}", "{guild.category_channels_count}",
        "{guild.vanity}",
        "{server.tag}", "{guild.tag}", "{tag.icon}",
    }

    USER_VARS = {
        "{user}", "{user.mention}", "{user.name}", "{username}",
        "{user.id}", "{id}", "{user.discriminator}", "{tag}",
        "{user.avatar}", "{user.display_avatar}",
        "{user.created_at}", "{user.created_at_timestamp}",
        "{user.joined_at}", "{user.joined_at_timestamp}",
        "{user.display_name}", "{user.bot}",
        "{account_age}", "{user.join_position}", "{user.join_position_suffix}",
        "{user.color}", "{user.top_role}",
        "{user.role_list}", "{user.role_text_list}",
        "{user.boost}", "{user.boost_since}", "{user.boost_since_timestamp}",
        "{user.guild_avatar}", "{user.badges}", "{user.badges_icons}",
        "{user_mention}", "{user_name}", "{user_id}",
    }

    CHANNEL_VARS = {
        "{channel.name}", "{channel.id}", "{channel.mention}",
        "{channel.type}", "{channel.position}", "{channel.category_id}",
        "{channel.category_name}", "{channel.topic}",
        "{channel.slowmode_delay}", "{channel.created_at}",
    }

    DATE_VARS = {
        "{date.now}", "{date.now_proper}", "{date.now_short}",
        "{date.now_shorter}", "{date.utc_timestamp}",
    }

    TIME_VARS = {
        "{time.now}", "{time.now_military}",
    }

    @staticmethod
    def ordinal(n: int) -> str:
        if 11 <= (n % 100) <= 13:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"{n}{suffix}"

    @staticmethod
    def get_pst_time() -> datetime:
        return datetime.now(PST_OFFSET)

    @staticmethod
    def get_utc_time() -> datetime:
        return datetime.now(UTC_ZONE)

    @staticmethod
    def format_date(style: str = "default") -> str:
        pst = TagScriptParser.get_pst_time()
        if style == "proper":
            return pst.strftime("%A, %B %d, %Y")
        elif style == "short":
            return pst.strftime("%m/%d/%y")
        elif style == "shorter":
            return pst.strftime("%B %d")
        elif style == "utc_timestamp":
            return str(int(TagScriptParser.get_utc_time().timestamp()))
        else:
            return pst.strftime("%m/%d/%Y")

    @staticmethod
    def format_time(military: bool = False) -> str:
        pst = TagScriptParser.get_pst_time()
        if military:
            return pst.strftime("%H:%M")
        return pst.strftime("%I:%M %p")

    @staticmethod
    def get_user_badges(user: Union[discord.Member, discord.User]) -> tuple[str, str]:
        flags = user.public_flags
        badge_texts = []
        badge_icons = []

        if flags.hypesquad:
            badge_texts.append("HypeSquad")
            badge_icons.append("<:hypesquad:>")
        if flags.hypesquad_balance:
            badge_texts.append("HypeSquad Balance")
            badge_icons.append("<:balance:>")
        if flags.hypesquad_brilliance:
            badge_texts.append("HypeSquad Brilliance")
            badge_icons.append("<:brilliance:>")
        if flags.hypesquad_hospitality:
            badge_texts.append("HypeSquad Hospitality")
            badge_icons.append("<:hospitality:>")
        if flags.discord_certified_moderator:
            badge_texts.append("Certified Moderator")
            badge_icons.append("<:mod:>")
        if flags.discord_employee:
            badge_texts.append("Discord Staff")
            badge_icons.append("<:staff:>")
        if flags.discord_partner:
            badge_texts.append("Partner")
            badge_icons.append("<:partner:>")
        if flags.bug_hunter:
            badge_texts.append("Bug Hunter")
            badge_icons.append("<:bughunter:>")
        if flags.bug_hunter_level_2:
            badge_texts.append("Bug Hunter Level 2")
            badge_icons.append("<:bughuntergold:>")
        if flags.early_supporter:
            badge_texts.append("Early Supporter")
            badge_icons.append("<:early:>")
        if flags.active_period:
            badge_texts.append("Nitro")
            badge_icons.append("<:nitro:>")
        if flags.verified_bot_developer:
            badge_texts.append("Verified Bot Developer")
            badge_icons.append("<:botdev:>")

        return ", ".join(badge_texts) if badge_texts else "None", " ".join(badge_icons) if badge_icons else "None"

    @staticmethod
    async def parse(
        text: str,
        user: Union[discord.Member, discord.User],
        guild: Optional[discord.Guild] = None,
        channel: Optional[discord.abc.GuildChannel] = None,
        bot: Optional["Xrypton"] = None,
    ) -> str:
        if not text:
            return text

        result = text

        result = TagScriptParser._parse_date_vars(result)
        result = TagScriptParser._parse_time_vars(result)
        result = await TagScriptParser._parse_user_vars(result, user, guild, bot)
        result = await TagScriptParser._parse_guild_vars(result, user, bot)
        result = TagScriptParser._parse_channel_vars(result, channel)

        return result

    @staticmethod
    def _parse_date_vars(text: str) -> str:
        result = text
        if "{date.now}" in result:
            result = result.replace("{date.now}", TagScriptParser.format_date())
        if "{date.now_proper}" in result:
            result = result.replace("{date.now_proper}", TagScriptParser.format_date("proper"))
        if "{date.now_short}" in result:
            result = result.replace("{date.now_short}", TagScriptParser.format_date("short"))
        if "{date.now_shorter}" in result:
            result = result.replace("{date.now_shorter}", TagScriptParser.format_date("shorter"))
        if "{date.utc_timestamp}" in result:
            result = result.replace("{date.utc_timestamp}", TagScriptParser.format_date("utc_timestamp"))
        return result

    @staticmethod
    def _parse_time_vars(text: str) -> str:
        result = text
        if "{time.now}" in result:
            result = result.replace("{time.now}", TagScriptParser.format_time())
        if "{time.now_military}" in result:
            result = result.replace("{time.now_military}", TagScriptParser.format_time(military=True))
        return result

    @staticmethod
    async def _parse_user_vars(
        text: str,
        user: Union[discord.Member, discord.User],
        guild: Optional[discord.Guild],
        bot: Optional["Xrypton"] = None,
    ) -> str:
        result = text

        is_member = isinstance(user, discord.Member)

        mention = user.mention
        name = user.name
        discriminator = getattr(user, "discriminator", "0")
        user_id = str(user.id)
        tag = f"{name}#{discriminator}"

        if "{user}" in result:
            result = result.replace("{user}", mention)
        if "{user.mention}" in result:
            result = result.replace("{user.mention}", mention)
        if "{user_mention}" in result:
            result = result.replace("{user_mention}", mention)
        if "{user.name}" in result:
            result = result.replace("{user.name}", name)
        if "{username}" in result:
            result = result.replace("{username}", name)
        if "{user_name}" in result:
            result = result.replace("{user_name}", name)
        if "{user.id}" in result:
            result = result.replace("{user.id}", user_id)
        if "{id}" in result:
            result = result.replace("{id}", user_id)
        if "{user_id}" in result:
            result = result.replace("{user_id}", user_id)
        if "{user.discriminator}" in result:
            result = result.replace("{user.discriminator}", discriminator)
        if "{tag}" in result:
            result = result.replace("{tag}", tag)

        avatar_url = str(user.display_avatar.url)
        if "{user.avatar}" in result:
            result = result.replace("{user.avatar}", avatar_url)
        if "{user.display_avatar}" in result:
            result = result.replace("{user.display_avatar}", avatar_url)

        created_at = getattr(user, "created_at", None)
        if created_at:
            result = result.replace("{user.created_at}", discord.utils.format_dt(created_at, style="R"))
            result = result.replace("{user.created_at_timestamp}", str(int(created_at.timestamp())))
        else:
            for var in ["{user.created_at}", "{user.created_at_timestamp}"]:
                result = result.replace(var, "N/A")

        display_name = getattr(user, "display_name", name)
        if "{user.display_name}" in result:
            result = result.replace("{user.display_name}", display_name)

        is_bot = getattr(user, "bot", False)
        if "{user.bot}" in result:
            result = result.replace("{user.bot}", "Yes" if is_bot else "No")

        account_age_days = None
        if created_at:
            account_age_days = (datetime.now(timezone.utc) - created_at.replace(tzinfo=timezone.utc)).days
            if "{account_age}" in result:
                result = result.replace("{account_age}", str(account_age_days))
        else:
            result = result.replace("{account_age}", "N/A")

        badges_text, badges_icons = TagScriptParser.get_user_badges(user)
        if "{user.badges}" in result:
            result = result.replace("{user.badges}", badges_text)
        if "{user.badges_icons}" in result:
            result = result.replace("{user.badges_icons}", badges_icons)

        if is_member and guild:
            joined_at = getattr(user, "joined_at", None)
            if joined_at:
                result = result.replace("{user.joined_at}", discord.utils.format_dt(joined_at, style="R"))
                result = result.replace("{user.joined_at_timestamp}", str(int(joined_at.timestamp())))
            else:
                for var in ["{user.joined_at}", "{user.joined_at_timestamp}"]:
                    result = result.replace(var, "N/A")

            sorted_members = sorted(guild.members, key=lambda m: m.joined_at or datetime.min.replace(tzinfo=timezone.utc))
            join_position = None
            for i, member in enumerate(sorted_members, 1):
                if member.id == user.id:
                    join_position = i
                    break

            if join_position is not None:
                if "{user.join_position}" in result:
                    result = result.replace("{user.join_position}", str(join_position))
                if "{user.join_position_suffix}" in result:
                    result = result.replace("{user.join_position_suffix}", TagScriptParser.ordinal(join_position))
            else:
                for var in ["{user.join_position}", "{user.join_position_suffix}"]:
                    result = result.replace(var, "N/A")

            top_role = getattr(user, "top_role", None)
            if top_role:
                if "{user.color}" in result:
                    result = result.replace("{user.color}", str(top_role.color) if top_role.color else "#000000")
                if "{user.top_role}" in result:
                    result = result.replace("{user.top_role}", top_role.name)
            else:
                for var in ["{user.color}", "{user.top_role}"]:
                    result = result.replace(var, "N/A")

            if "{user.role_list}" in result:
                roles = [role.mention for role in user.roles[1:] if role != guild.default_role]
                result = result.replace("{user.role_list}", " ".join(roles) if roles else "None")
            if "{user.role_text_list}" in result:
                roles = [role.name for role in user.roles[1:] if role != guild.default_role]
                result = result.replace("{user.role_text_list}", ", ".join(roles) if roles else "None")

            premium_since = getattr(user, "premium_since", None)
            if "{user.boost}" in result:
                result = result.replace("{user.boost}", "Yes" if premium_since else "No")
            if premium_since:
                if "{user.boost_since}" in result:
                    result = result.replace("{user.boost_since}", discord.utils.format_dt(premium_since, style="R"))
                if "{user.boost_since_timestamp}" in result:
                    result = result.replace("{user.boost_since_timestamp}", str(int(premium_since.timestamp())))
            else:
                for var in ["{user.boost_since}", "{user.boost_since_timestamp}"]:
                    result = result.replace(var, "N/A")

            guild_avatar = user.guild_avatar
            if "{user.guild_avatar}" in result:
                result = result.replace("{user.guild_avatar}", str(guild_avatar.url) if guild_avatar else "N/A")
        else:
            na_vars = [
                "{user.joined_at}", "{user.joined_at_timestamp}", "{account_age}",
                "{user.join_position}", "{user.join_position_suffix}",
                "{user.color}", "{user.top_role}", "{user.role_list}", "{user.role_text_list}",
                "{user.boost}", "{user.boost_since}", "{user.boost_since_timestamp}",
                "{user.guild_avatar}",
            ]
            for var in na_vars:
                result = result.replace(var, "N/A")

        return result

    @staticmethod
    async def _parse_guild_vars(
        text: str,
        user: Union[discord.Member, discord.User],
        bot: Optional["Xrypton"] = None,
    ) -> str:
        result = text

        if not user.guild:
            for var in TagScriptParser.GUILD_VARS:
                if var in result:
                    result = result.replace(var, "N/A")
            return result

        guild = user.guild

        if "{guild.name}" in result:
            result = result.replace("{guild.name}", guild.name)
        if "{guild}" in result:
            result = result.replace("{guild}", guild.name)
        if "{server}" in result:
            result = result.replace("{server}", guild.name)
        if "{server.name}" in result:
            result = result.replace("{server.name}", guild.name)

        if "{guild.id}" in result:
            result = result.replace("{guild.id}", str(guild.id))

        owner_id = str(guild.owner_id) if guild.owner_id else "N/A"
        if "{guild.owner_id}" in result:
            result = result.replace("{guild.owner_id}", owner_id)
        if "{guild.owner}" in result:
            result = result.replace("{guild.owner}", owner_id)

        created_at = getattr(guild, "created_at", None)
        if created_at:
            if "{guild.created_at}" in result:
                result = result.replace("{guild.created_at}", discord.utils.format_dt(created_at, style="R"))
            if "{guild.created_at_timestamp}" in result:
                result = result.replace("{guild.created_at_timestamp}", str(int(created_at.timestamp())))
        else:
            result = result.replace("{guild.created_at}", "N/A")
            result = result.replace("{guild.created_at_timestamp}", "N/A")

        region = getattr(guild, "region", None) or getattr(guild, "preferred_locale", "Unknown")
        if "{guild.region}" in result:
            result = result.replace("{guild.region}", str(region))

        shard_id = getattr(guild, "shard_id", 0)
        if "{guild.shard}" in result:
            result = result.replace("{guild.shard}", str(shard_id))

        emoji_count = len(guild.emojis)
        if "{guild.emoji_count}" in result:
            result = result.replace("{guild.emoji_count}", str(emoji_count))

        role_count = len(guild.roles)
        if "{guild.role_count}" in result:
            result = result.replace("{guild.role_count}", str(role_count))

        boost_count = getattr(guild, "premium_subscription_count", 0)
        if "{guild.boost_count}" in result:
            result = result.replace("{guild.boost_count}", str(boost_count))

        boost_tier = getattr(guild, "premium_tier", 0)
        if "{guild.boost_tier}" in result:
            result = result.replace("{guild.boost_tier}", str(boost_tier))

        preferred_locale = getattr(guild, "preferred_locale", "en-US")
        if "{guild.preferred_locale}" in result:
            result = result.replace("{guild.preferred_locale}", str(preferred_locale))

        features = getattr(guild, "features", [])
        if "{guild.key_features}" in result:
            result = result.replace("{guild.key_features}", ", ".join(features) if features else "None")

        icon_url = str(guild.icon.url) if guild.icon else "N/A"
        if "{guild.icon}" in result:
            result = result.replace("{guild.icon}", icon_url)

        banner_url = str(guild.banner.url) if guild.banner else "N/A"
        if "{guild.banner}" in result:
            result = result.replace("{guild.banner}", banner_url)

        splash_url = str(guild.splash.url) if guild.splash else "N/A"
        if "{guild.splash}" in result:
            result = result.replace("{guild.splash}", splash_url)

        discovery_url = str(guild.discovery_splash.url) if getattr(guild, "discovery_splash", None) else "N/A"
        if "{guild.discovery}" in result:
            result = result.replace("{guild.discovery}", discovery_url)

        max_presences = getattr(guild, "max_presences", None)
        if "{guild.max_presences}" in result:
            result = result.replace("{guild.max_presences}", str(max_presences) if max_presences else "N/A")

        max_members = getattr(guild, "max_members", None)
        if "{guild.max_members}" in result:
            result = result.replace("{guild.max_members}", str(max_members) if max_members else "N/A")

        max_video_users = getattr(guild, "max_video_channel_users", None)
        if "{guild.max_video_channel_users}" in result:
            result = result.replace("{guild.max_video_channel_users}", str(max_video_users) if max_video_users else "N/A")

        afk_timeout = getattr(guild, "afk_timeout", None)
        if "{guild.afk_timeout}" in result:
            result = result.replace("{guild.afk_timeout}", str(afk_timeout) if afk_timeout else "N/A")

        afk_channel = guild.afk_channel
        if "{guild.afk_channel}" in result:
            result = result.replace("{guild.afk_channel}", afk_channel.name if afk_channel else "N/A")

        total_channels = len(guild.channels)
        if "{guild.channels_count}" in result:
            result = result.replace("{guild.channels_count}", str(total_channels))

        text_channels = len([c for c in guild.channels if isinstance(c, (discord.TextChannel, discord.ForumChannel))])
        if "{guild.text_channels_count}" in result:
            result = result.replace("{guild.text_channels_count}", str(text_channels))

        voice_channels = len([c for c in guild.channels if isinstance(c, discord.VoiceChannel)])
        if "{guild.voice_channels_count}" in result:
            result = result.replace("{guild.voice_channels_count}", str(voice_channels))

        categories = len([c for c in guild.channels if isinstance(c, discord.CategoryChannel)])
        if "{guild.category_channels_count}" in result:
            result = result.replace("{guild.category_channels_count}", str(categories))

        vanity_code = getattr(guild, "vanity_url_code", None)
        if "{guild.vanity}" in result:
            result = result.replace("{guild.vanity}", f"/{vanity_code}" if vanity_code else "N/A")

        member_count = guild.member_count or len(guild.members)
        for var in ["{guild.count}", "{guild.member_count}", "{count}", "{membercount}", "{members}"]:
            if var in result:
                result = result.replace(var, str(member_count))

        primary_tag = "N/A"
        primary_tag_icon = "N/A"

        if bot:
            try:
                cursor = await bot.db.execute(
                    "SELECT guild_id FROM user_config WHERE user_id = ? LIMIT 1",
                    (user.id,),
                )
                row = await cursor.fetchone()
                if row:
                    primary_guild_id = row["guild_id"]
                    primary_guild = bot.get_guild(primary_guild_id)
                    if primary_guild:
                        primary_tag = f"@{primary_guild.name}"
                        if primary_guild.icon:
                            primary_tag_icon = primary_guild.icon.url
            except Exception:
                pass

        if "{server.tag}" in result:
            result = result.replace("{server.tag}", primary_tag)
        if "{guild.tag}" in result:
            result = result.replace("{guild.tag}", primary_tag)
        if "{tag.icon}" in result:
            result = result.replace("{tag.icon}", primary_tag_icon)

        return result

    @staticmethod
    def _parse_channel_vars(text: str, channel: Optional[discord.abc.GuildChannel]) -> str:
        result = text

        if not channel:
            for var in TagScriptParser.CHANNEL_VARS:
                result = result.replace(var, "N/A")
            return result

        if "{channel.name}" in result:
            result = result.replace("{channel.name}", channel.name)
        if "{channel.id}" in result:
            result = result.replace("{channel.id}", str(channel.id))
        if "{channel.mention}" in result:
            result = result.replace("{channel.mention}", getattr(channel, "mention", channel.name))
        if "{channel.type}" in result:
            result = result.replace("{channel.type}", str(channel.type.name))
        if "{channel.position}" in result:
            result = result.replace("{channel.position}", str(channel.position))
        if "{channel.category_id}" in result:
            category_id = str(channel.category_id) if channel.category_id else "N/A"
            result = result.replace("{channel.category_id}", category_id)
        if "{channel.category_name}" in result:
            category = getattr(channel, "category", None)
            result = result.replace("{channel.category_name}", category.name if category else "N/A")
        if "{channel.topic}" in result:
            topic = getattr(channel, "topic", None)
            result = result.replace("{channel.topic}", topic if topic else "N/A")
        if "{channel.slowmode_delay}" in result:
            delay = getattr(channel, "slowmode_delay", 0)
            result = result.replace("{channel.slowmode_delay}", str(delay))
        if "{channel.created_at}" in result:
            created_at = getattr(channel, "created_at", None)
            if created_at:
                result = result.replace("{channel.created_at}", discord.utils.format_dt(created_at, style="R"))
            else:
                result = result.replace("{channel.created_at}", "N/A")

        return result


class TagScriptConverter(commands.Converter):
    async def convert(self, ctx, argument: str) -> str:
        guild = ctx.guild
        channel = ctx.channel
        bot = ctx.bot
        return await TagScriptParser.parse(argument, ctx.author, guild, channel, bot)
