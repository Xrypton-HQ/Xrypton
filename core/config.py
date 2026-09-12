import os
from enum import Enum


class EMOJIS:
    DENY = "<:deny:1547570956191535144>"
    APPROVE = "<:approve:1547570974457733141>"
    WARN = "<:warning:1547570970791772270>"
    COOLDOWN = "<:cooldown:1547572522004914218>"
    PREVIOUS = "<:left:1547570958754390086>"
    NEXT = "<:right:1547570961857904710>"
    NAVIGATE = "<:skipto:1547570966731816980>"
    CANCEL = "<:cancel:1547570977813299290>"
    ONLINE = "🟢"
    IDLE = "🟡"
    DND = "🔴"
    OFFLINE = "⚫"

class ButtonStyle(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    SUCCESS = "success"
    DANGER = "danger"
    WARNING = "warning"
    BLURPLE = "blurple"
    GREY = "grey"


class COLORS:
    approve = 0x57F287
    warn = 0xFEE75C
    deny = 0xED4245
    neutral = 0x2B2D31


class DEV:
    JOIN_LOG_CHANNEL = ""
    LEAVE_LOG_CHANNEL = ""
    GUILD_LOG_CHANNEL = ""