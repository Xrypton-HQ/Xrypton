CREATE TABLE IF NOT EXISTS guild_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER UNIQUE NOT NULL,
    prefix TEXT NOT NULL DEFAULT ','
);

CREATE TABLE IF NOT EXISTS user_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE NOT NULL,
    prefix TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bot_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    emoji_approve TEXT DEFAULT '✅',
    emoji_deny TEXT DEFAULT '❌',
    emoji_warn TEXT DEFAULT '⚠️',
    emoji_cooldown TEXT DEFAULT '⏱️',
    neutral_color INTEGER DEFAULT 0x2B2D31
);

INSERT OR IGNORE INTO bot_config (id, emoji_approve, emoji_deny, emoji_warn, emoji_cooldown, neutral_color)
VALUES (1, '✅', '❌', '⚠️', '⏱️', 0x2B2D31);

CREATE TABLE IF NOT EXISTS aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    command_name TEXT NOT NULL,
    shortcut TEXT NOT NULL,
    UNIQUE(guild_id, shortcut)
);
-- ── cogs/server ──

CREATE TABLE IF NOT EXISTS welcome_config (
    guild_id INTEGER PRIMARY KEY,
    channels TEXT NOT NULL DEFAULT '[]',
    message TEXT,
    dm_enabled INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS leave_config (
    guild_id INTEGER PRIMARY KEY,
    channels TEXT NOT NULL DEFAULT '[]',
    message TEXT
);

CREATE TABLE IF NOT EXISTS log_config (
    guild_id INTEGER PRIMARY KEY,
    category_id INTEGER,
    channels TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS ignore_config (
    guild_id INTEGER PRIMARY KEY,
    users TEXT NOT NULL DEFAULT '[]',
    channels TEXT NOT NULL DEFAULT '[]',
    roles TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS fake_permission_config (
    guild_id INTEGER PRIMARY KEY,
    permissions TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS sticky_config (
    guild_id INTEGER NOT NULL,
    channel_id INTEGER PRIMARY KEY,
    message TEXT NOT NULL,
    last_message_id INTEGER,
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mod_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    moderator_id INTEGER,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admin_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    author_id INTEGER NOT NULL,
    note TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS webhook_store (
    identifier TEXT PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    webhook_id INTEGER NOT NULL,
    webhook_token TEXT NOT NULL,
    webhook_url TEXT NOT NULL,
    creator_id INTEGER NOT NULL,
    name TEXT,
    locked INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── cogs/moderation ──

CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    moderator_id INTEGER,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reactmute (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS imagemute (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS forcenick (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    forced_nick TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS lock_snapshot (
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    was_locked INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, channel_id)
);

CREATE TABLE IF NOT EXISTS ghostping_config (
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    delay INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (guild_id, channel_id)
);

-- ── cogs/fun ──

CREATE TABLE IF NOT EXISTS juul_stats (
    guild_id TEXT PRIMARY KEY,
    data TEXT,
    enabled INTEGER,
    flavor TEXT,
    holder_id TEXT,
    hits INTEGER DEFAULT 0,
    passes INTEGER DEFAULT 0,
    steals INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS juul_users (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    hits INTEGER DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

-- ── cogs/automation ──

CREATE TABLE IF NOT EXISTS autorole_config (
    guild_id INTEGER PRIMARY KEY,
    everyone TEXT NOT NULL DEFAULT '[]',
    humans TEXT NOT NULL DEFAULT '[]',
    bots TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS autoreact_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    trigger TEXT NOT NULL,
    emoji TEXT NOT NULL,
    exclusive_channels TEXT NOT NULL DEFAULT '[]',
    exclusive_roles TEXT NOT NULL DEFAULT '[]',
    UNIQUE(guild_id, trigger)
);

CREATE TABLE IF NOT EXISTS trigger_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    trigger TEXT NOT NULL,
    response TEXT NOT NULL,
    exclusive_channels TEXT NOT NULL DEFAULT '[]',
    exclusive_roles TEXT NOT NULL DEFAULT '[]',
    UNIQUE(guild_id, trigger)
);

CREATE TABLE IF NOT EXISTS image_search_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    query TEXT NOT NULL,
    image_data TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- -- cogs/server (giveaway) --

CREATE TABLE IF NOT EXISTS giveaways (
    message_id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    host_id INTEGER NOT NULL,
    prize TEXT NOT NULL,
    winners INTEGER NOT NULL DEFAULT 1,
    duration_seconds INTEGER NOT NULL,
    minimum_age_seconds INTEGER NOT NULL DEFAULT 0,
    required_role_id INTEGER,
    entries TEXT NOT NULL DEFAULT '[]',
    ended INTEGER NOT NULL DEFAULT 0,
    winner_ids TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ends_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS giveaway_config (
    guild_id INTEGER PRIMARY KEY,
    default_channel_id INTEGER
);

CREATE TABLE IF NOT EXISTS saved_embeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    script TEXT NOT NULL,
    UNIQUE(user_id, name)
);

CREATE TABLE IF NOT EXISTS buttonroles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    button_style TEXT NOT NULL DEFAULT 'primary',
    label TEXT NOT NULL,
    emoji TEXT,
    user_limit INTEGER,
    UNIQUE(guild_id, message_id, role_id)
);

-- ── cogs/engagement ──

-- Suggestions: per-guild configuration plus the active "panel" message that
-- users click to open the suggestion modal.
CREATE TABLE IF NOT EXISTS suggestions_config (
    guild_id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    panel_message_id INTEGER,
    panel_template TEXT,
    embed_template TEXT
);

-- Individual suggestions posted to the suggestion channel.
CREATE TABLE IF NOT EXISTS suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER,
    message_id INTEGER UNIQUE,
    author_id INTEGER NOT NULL,
    suggestion TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', -- pending | approved | denied | implemented | considered
    responder_id INTEGER,
    response TEXT,
    response_message_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Block-list of members that cannot create suggestions.
CREATE TABLE IF NOT EXISTS suggestions_blacklist (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    moderator_id INTEGER,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, user_id)
);

-- Invite tracker: one row per unique invite code that we have seen in a
-- guild, recording who created it and how often it has been used.
CREATE TABLE IF NOT EXISTS invites (
    guild_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    inviter_id INTEGER,
    channel_id INTEGER,
    url TEXT,
    uses INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, code)
);

-- Tracks which invite code a member joined through so we can attribute
-- future invites back to the correct inviter.
CREATE TABLE IF NOT EXISTS invite_joins (
    guild_id INTEGER NOT NULL,
    user_id INTEGER PRIMARY KEY,
    invite_code TEXT,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Per-(guild, user) XP for the leveling system.
CREATE TABLE IF NOT EXISTS levels (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    xp INTEGER NOT NULL DEFAULT 0,
    total_xp INTEGER NOT NULL DEFAULT 0,
    last_message_ts INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

-- Per-guild leveling configuration.
CREATE TABLE IF NOT EXISTS level_config (
    guild_id INTEGER PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 1,
    xp_min INTEGER NOT NULL DEFAULT 15,
    xp_max INTEGER NOT NULL DEFAULT 25,
    cooldown_seconds INTEGER NOT NULL DEFAULT 60,
    level_up_message TEXT,
    level_up_channel_id INTEGER,
    announce INTEGER NOT NULL DEFAULT 1
);

-- Channels and roles excluded from gaining XP.
CREATE TABLE IF NOT EXISTS level_excludes (
    guild_id INTEGER NOT NULL,
    kind TEXT NOT NULL,                       -- 'channel' | 'role'
    target_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, kind, target_id)
);

-- Role rewards awarded when a user reaches a given level.
CREATE TABLE IF NOT EXISTS level_rewards (
    guild_id INTEGER NOT NULL,
    level INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, level)
);

-- Starboard configuration. Up to 3 rows per guild, identified by name.
CREATE TABLE IF NOT EXISTS starboards (
    guild_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    channel_id INTEGER NOT NULL,
    emoji TEXT NOT NULL,
    threshold INTEGER NOT NULL,
    locked INTEGER NOT NULL DEFAULT 0,
    self_react INTEGER NOT NULL DEFAULT 0,
    color INTEGER,
    PRIMARY KEY (guild_id, name)
);

-- Channels/roles/users ignored by a starboard.
CREATE TABLE IF NOT EXISTS starboard_ignores (
    guild_id INTEGER NOT NULL,
    starboard_name TEXT NOT NULL,
    kind TEXT NOT NULL,                       -- 'channel' | 'role' | 'user'
    target_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, starboard_name, kind, target_id)
);

-- Tracks which messages already have a starboard embed so we don't repost.
CREATE TABLE IF NOT EXISTS starboard_posts (
    guild_id INTEGER NOT NULL,
    starboard_name TEXT NOT NULL,
    source_message_id INTEGER NOT NULL,
    starboard_message_id INTEGER NOT NULL,
    stargazers TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (guild_id, starboard_name, source_message_id)
);

-- -- cogs/engagement (giveaways & afk extensions) --

-- Per-guild extra entry roles: hold an additional number of entries per role.
CREATE TABLE IF NOT EXISTS giveaway_extra_entries (
    guild_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    entries INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (guild_id, role_id)
);

-- Required roles (per-guild) — server-wide list of roles that *can* be required
-- for a giveaway (set with `,giveaways edit requiredroles`).
CREATE TABLE IF NOT EXISTS giveaway_required_roles (
    guild_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, role_id)
);

-- Members blacklisted from entering giveaways in a particular guild.
CREATE TABLE IF NOT EXISTS giveaway_blacklist (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    moderator_id INTEGER,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, user_id)
);

-- Per-user AFK status (one row per user across all guilds).
CREATE TABLE IF NOT EXISTS afk_users (
    user_id INTEGER PRIMARY KEY,
    reason TEXT NOT NULL,
    since TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_autoclear TIMESTAMP
);

-- Channels ignored by the AFK system on a per-guild basis (e.g. bot commands
-- channels where the user is allowed to talk while AFK).
CREATE TABLE IF NOT EXISTS afk_ignore_channels (
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, channel_id)
);

-- Per-guild AFK configuration: autoclear timeout and log channel.
CREATE TABLE IF NOT EXISTS afk_config (
    guild_id INTEGER PRIMARY KEY,
    timeout_minutes INTEGER NOT NULL DEFAULT 0,
    log_channel_id INTEGER
);

-- Per-user AFK presets saved for quick re-use.
CREATE TABLE IF NOT EXISTS afk_presets (
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    reason TEXT NOT NULL,
    PRIMARY KEY (user_id, name)
);


