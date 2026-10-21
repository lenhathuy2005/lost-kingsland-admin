-- LOST KINGSLAND — PostgreSQL Database Baseline
-- Version: DB v2.0
-- Basis: Master GDD v4.0 + Combat Engine v2.2 + Multi-March / Market / Cultivation / YouTube Music + Source Ownership Update
-- Target: PostgreSQL 16+
-- Architecture: modular monolith; PostgreSQL source of truth; Redis ephemeral/cache; RabbitMQ async
-- IMPORTANT: This is a baseline schema, intended to be split into Flyway/Liquibase migrations in implementation.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

-- ============================================================
-- 0. SCHEMAS
-- ============================================================
CREATE SCHEMA IF NOT EXISTS platform;
CREATE SCHEMA IF NOT EXISTS identity;
CREATE SCHEMA IF NOT EXISTS content;
CREATE SCHEMA IF NOT EXISTS hero;
CREATE SCHEMA IF NOT EXISTS adventure;
CREATE SCHEMA IF NOT EXISTS combat;
CREATE SCHEMA IF NOT EXISTS inventory;
CREATE SCHEMA IF NOT EXISTS kingdom;
CREATE SCHEMA IF NOT EXISTS clan;
CREATE SCHEMA IF NOT EXISTS competitive;
CREATE SCHEMA IF NOT EXISTS liveops;
CREATE SCHEMA IF NOT EXISTS economy;
CREATE SCHEMA IF NOT EXISTS commerce;
CREATE SCHEMA IF NOT EXISTS ops;
CREATE SCHEMA IF NOT EXISTS commander;
CREATE SCHEMA IF NOT EXISTS media;
CREATE SCHEMA IF NOT EXISTS march;
CREATE SCHEMA IF NOT EXISTS market;

-- ============================================================
-- 1. COMMON DOMAIN TYPES
-- ============================================================
DO $$ BEGIN
    CREATE TYPE platform.record_status AS ENUM ('ACTIVE','INACTIVE','ARCHIVED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE platform.job_status AS ENUM ('PENDING','RUNNING','SUCCEEDED','FAILED','CANCELLED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE platform.queue_status AS ENUM ('RUNNING','COMPLETED','CANCELLED','FAILED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE platform.integrity_tier AS ENUM ('A','B','C');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE platform.entity_scope AS ENUM ('ACCOUNT','PLAYER','HERO','CLAN','SEASON','SYSTEM');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE inventory.item_rarity AS ENUM ('COMMON','UNCOMMON','RARE','EPIC','LEGENDARY');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE inventory.item_state AS ENUM ('OWNED','EQUIPPED','LOCKED','LISTED','CONSUMED','SALVAGED','DESTROYED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE adventure.run_status AS ENUM ('ACTIVE','PAUSED','COMPLETED','FAILED','ABANDONED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE adventure.node_type AS ENUM ('COMBAT','ELITE','EVENT','SHOP','REST','TREASURE','BOSS');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE combat.combat_status AS ENUM ('CREATED','ACTIVE','WON','LOST','FLED','CANCELLED','SETTLED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE combat.actor_type AS ENUM ('PLAYER_HERO','COMMANDER','COMPANION','ENEMY','BOSS','ARENA_DEFENDER');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE combat.damage_channel AS ENUM ('PHYSICAL','MYSTIC','TRUE','HYBRID');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE combat.profile_code AS ENUM ('PVE_STANDARD','PVE_BOSS','PVP_ARENA','PVP_CLAN_SIEGE','BREAKTHROUGH_TRIAL');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE clan.member_rank AS ENUM ('RECRUIT','MEMBER','VETERAN','OFFICER','LEADER');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE competitive.season_status AS ENUM ('DRAFT','SCHEDULED','ACTIVE','SETTLEMENT','CLOSED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE commerce.payment_status AS ENUM ('RECEIVED','VALIDATING','VALID','GRANTED','REFUNDED','CHARGEBACK','REJECTED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE content.source_game AS ENUM ('LOST_KINGSLAND','PATH_OF_KINGS','RISE_OF_KINGDOMS','ORIGINAL_HYBRID');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE commander.commander_status AS ENUM ('RESERVED','AVAILABLE','OWNED','DISABLED','ARCHIVED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE march.march_status AS ENUM ('AVAILABLE','HUNTING','GATHERING','STOPPING','DISABLED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE march.assignment_type AS ENUM ('HUNT','GATHER');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE march.resource_site_status AS ENUM ('AVAILABLE','OCCUPIED','DEPLETED','DISABLED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE market.listing_status AS ENUM ('ACTIVE','SOLD','CANCELLED','EXPIRED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE market.transfer_type AS ENUM ('MARKET','DIRECT_TRADE');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE market.trade_status AS ENUM ('PENDING','ACCEPTED','DECLINED','CANCELLED','EXPIRED','SETTLED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ============================================================
-- 2. PLATFORM / CONFIG / IDEMPOTENCY / OUTBOX
-- ============================================================
CREATE TABLE IF NOT EXISTS platform.config_versions (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    version_code        varchar(64) NOT NULL UNIQUE,
    description         text,
    status              platform.record_status NOT NULL DEFAULT 'ACTIVE',
    effective_from      timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    created_by          varchar(128)
);

CREATE TABLE IF NOT EXISTS platform.feature_flags (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    flag_key            varchar(128) NOT NULL,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    enabled             boolean NOT NULL DEFAULT false,
    rule_json           jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(flag_key, config_version_id)
);

CREATE TABLE IF NOT EXISTS platform.idempotency_records (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_scope         varchar(64) NOT NULL,
    actor_id            uuid,
    operation_type      varchar(96) NOT NULL,
    idempotency_key     varchar(160) NOT NULL,
    request_hash        varchar(128) NOT NULL,
    status              varchar(32) NOT NULL,
    response_code       varchar(64),
    response_json       jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),
    completed_at        timestamptz,
    expires_at          timestamptz,
    UNIQUE NULLS NOT DISTINCT (actor_scope, actor_id, operation_type, idempotency_key)
);
CREATE INDEX IF NOT EXISTS ix_idempotency_expiry
    ON platform.idempotency_records(expires_at) WHERE expires_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS platform.outbox_events (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type      varchar(64) NOT NULL,
    aggregate_id        uuid,
    event_type          varchar(128) NOT NULL,
    routing_key         varchar(160) NOT NULL,
    payload             jsonb NOT NULL,
    headers             jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),
    published_at        timestamptz,
    publish_attempts    integer NOT NULL DEFAULT 0,
    last_error          text
);
CREATE INDEX IF NOT EXISTS ix_outbox_unpublished
    ON platform.outbox_events(created_at) WHERE published_at IS NULL;

CREATE TABLE IF NOT EXISTS platform.scheduled_actions (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    action_type         varchar(96) NOT NULL,
    aggregate_type      varchar(64) NOT NULL,
    aggregate_id        uuid NOT NULL,
    execute_at          timestamptz NOT NULL,
    status              platform.job_status NOT NULL DEFAULT 'PENDING',
    payload             jsonb NOT NULL DEFAULT '{}'::jsonb,
    attempt_count       integer NOT NULL DEFAULT 0,
    locked_at           timestamptz,
    locked_by           varchar(128),
    completed_at        timestamptz,
    last_error          text,
    created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_scheduled_due
    ON platform.scheduled_actions(execute_at, id)
    WHERE status = 'PENDING';

-- ============================================================
-- 3. IDENTITY / DISCORD
-- ============================================================
CREATE TABLE IF NOT EXISTS identity.accounts (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    public_id           uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    status              varchar(32) NOT NULL DEFAULT 'ACTIVE',
    locale              varchar(16) NOT NULL DEFAULT 'vi-VN',
    timezone            varchar(64) NOT NULL DEFAULT 'UTC',
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    version             bigint NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS identity.discord_links (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id          uuid NOT NULL REFERENCES identity.accounts(id) ON DELETE CASCADE,
    discord_user_id     bigint NOT NULL UNIQUE,
    discord_username    varchar(128),
    linked_at           timestamptz NOT NULL DEFAULT now(),
    revoked_at          timestamptz,
    is_primary          boolean NOT NULL DEFAULT true
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_discord_primary_link_per_account
    ON identity.discord_links(account_id)
    WHERE is_primary = true AND revoked_at IS NULL;


CREATE TABLE IF NOT EXISTS identity.players (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id          uuid NOT NULL UNIQUE REFERENCES identity.accounts(id) ON DELETE CASCADE,
    display_name        citext NOT NULL UNIQUE,
    account_level       integer NOT NULL DEFAULT 1 CHECK (account_level > 0),
    account_xp          bigint NOT NULL DEFAULT 0 CHECK (account_xp >= 0),
    avatar_key          varchar(128),
    active_hero_id      uuid,
    active_screen_key   varchar(128),
    tutorial_step       varchar(96),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    version             bigint NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS identity.player_settings (
    player_id           uuid PRIMARY KEY REFERENCES identity.players(id) ON DELETE CASCADE,
    notification_json   jsonb NOT NULL DEFAULT '{}'::jsonb,
    privacy_json        jsonb NOT NULL DEFAULT '{}'::jsonb,
    accessibility_json  jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS identity.discord_guild_bindings (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    discord_guild_id    bigint NOT NULL UNIQUE,
    owner_account_id    uuid REFERENCES identity.accounts(id),
    clan_id             uuid,
    game_channel_id     bigint,
    clan_channel_id     bigint,
    announcement_channel_id bigint,
    settings_json       jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),
    version             bigint NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS identity.interaction_refs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id           uuid REFERENCES identity.players(id) ON DELETE CASCADE,
    interaction_type    varchar(64) NOT NULL,
    aggregate_type      varchar(64),
    aggregate_id        uuid,
    expected_version    bigint,
    expires_at          timestamptz NOT NULL,
    consumed_at         timestamptz,
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_interaction_refs_expiry
    ON identity.interaction_refs(expires_at);

-- ============================================================
-- 4. CONTENT DEFINITIONS — VERSIONED / CONFIG-DRIVEN
-- ============================================================
CREATE TABLE IF NOT EXISTS content.tags (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tag_code            varchar(64) NOT NULL UNIQUE,
    category            varchar(64),
    description         text
);

CREATE TABLE IF NOT EXISTS content.race_defs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code                varchar(64) NOT NULL,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    name_key            varchar(128) NOT NULL,
    description_key     varchar(128),
    base_effects        jsonb NOT NULL DEFAULT '[]'::jsonb,
    status              platform.record_status NOT NULL DEFAULT 'ACTIVE',
    UNIQUE(code, config_version_id)
);

CREATE TABLE IF NOT EXISTS content.bloodline_defs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code                varchar(64) NOT NULL,
    race_code           varchar(64) NOT NULL,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    tier                integer NOT NULL DEFAULT 1,
    effects             jsonb NOT NULL DEFAULT '[]'::jsonb,
    unlock_rule         jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(code, config_version_id)
);

CREATE TABLE IF NOT EXISTS content.path_defs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code                varchar(64) NOT NULL,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    name_key            varchar(128) NOT NULL,
    resource_type       varchar(64),
    base_stats          jsonb NOT NULL DEFAULT '{}'::jsonb,
    rules               jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(code, config_version_id)
);

CREATE TABLE IF NOT EXISTS content.affinity_defs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code                varchar(64) NOT NULL,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    name_key            varchar(128) NOT NULL,
    resonance_curve     jsonb NOT NULL DEFAULT '{}'::jsonb,
    tags                varchar(64)[] NOT NULL DEFAULT '{}',
    UNIQUE(code, config_version_id)
);

CREATE TABLE IF NOT EXISTS content.realm_defs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code                varchar(64) NOT NULL,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    ordinal             integer NOT NULL,
    minor_stage_count   integer NOT NULL DEFAULT 10 CHECK (minor_stage_count = 10),
    base_stat_budget    jsonb NOT NULL DEFAULT '{}'::jsonb,
    unlocks             jsonb NOT NULL DEFAULT '[]'::jsonb,
    breakthrough_rule   jsonb NOT NULL DEFAULT '{}'::jsonb,
    base_tribulation_chance numeric(8,6) CHECK (base_tribulation_chance IS NULL OR (base_tribulation_chance >= 0 AND base_tribulation_chance <= 1)),
    UNIQUE(code, config_version_id),
    UNIQUE(ordinal, config_version_id)
);


-- v4.0 Exploration Floor / monster reward / march-gate configuration.
CREATE TABLE IF NOT EXISTS content.exploration_floor_profiles (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    min_floor           integer NOT NULL CHECK(min_floor >= 1),
    max_floor           integer CHECK(max_floor IS NULL OR max_floor >= min_floor),
    max_natural_rarity  inventory.item_rarity NOT NULL,
    rarity_weights      jsonb NOT NULL DEFAULT '{}'::jsonb,
    item_level_rule     jsonb NOT NULL DEFAULT '{}'::jsonb,
    monster_profile     jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(config_version_id, min_floor)
);

CREATE TABLE IF NOT EXISTS content.monster_reward_profiles (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_code        varchar(96) NOT NULL,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    guaranteed_equipment_count smallint NOT NULL DEFAULT 1 CHECK(guaranteed_equipment_count >= 1),
    gold_rule           jsonb NOT NULL DEFAULT '{}'::jsonb,
    sp_rule             jsonb NOT NULL DEFAULT '{}'::jsonb,
    construction_resource_rule jsonb NOT NULL DEFAULT '{}'::jsonb,
    equipment_rule      jsonb NOT NULL DEFAULT '{}'::jsonb,
    crafting_choice_material_rule jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(profile_code, config_version_id)
);

CREATE TABLE IF NOT EXISTS content.march_slot_unlock_rules (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    city_hall_level_min integer NOT NULL CHECK(city_hall_level_min >= 1),
    max_march_slots     smallint NOT NULL CHECK(max_march_slots BETWEEN 1 AND 5),
    UNIQUE(config_version_id, city_hall_level_min)
);
COMMENT ON TABLE content.march_slot_unlock_rules IS
'v4.0 required thresholds include City Hall Lv8=>3 slots, Lv17=>4, Lv23=>5. The pre-Lv8 baseline remains configuration-owned until product locks it.';

CREATE TABLE IF NOT EXISTS content.sect_defs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code                varchar(64) NOT NULL,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    name_key            varchar(128) NOT NULL,
    philosophy_tags     varchar(64)[] NOT NULL DEFAULT '{}',
    join_rule           jsonb NOT NULL DEFAULT '{}'::jsonb,
    leave_rule          jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(code, config_version_id)
);

CREATE TABLE IF NOT EXISTS content.profession_defs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code                varchar(64) NOT NULL,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    name_key            varchar(128) NOT NULL,
    rules               jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(code, config_version_id)
);

CREATE TABLE IF NOT EXISTS content.technique_defs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code                varchar(96) NOT NULL,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    technique_type      varchar(32) NOT NULL CHECK (technique_type IN ('COMBAT_SKILL','PASSIVE_ART','CULTIVATION_ART','SECRET_ART')),
    name_key            varchar(128) NOT NULL,
    max_level           integer NOT NULL DEFAULT 1 CHECK (max_level > 0),
    tags                varchar(64)[] NOT NULL DEFAULT '{}',
    martial_scaling     numeric(10,4) NOT NULL DEFAULT 0,
    mystic_scaling      numeric(10,4) NOT NULL DEFAULT 0,
    flat_power          numeric(18,4) NOT NULL DEFAULT 0,
    skill_coefficient   numeric(10,4) NOT NULL DEFAULT 1,
    damage_channel      combat.damage_channel,
    resource_cost       jsonb NOT NULL DEFAULT '{}'::jsonb,
    cooldown_rounds     integer NOT NULL DEFAULT 0,
    effect_list         jsonb NOT NULL DEFAULT '[]'::jsonb,
    unlock_rule         jsonb NOT NULL DEFAULT '{}'::jsonb,
    profile_scaling     jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(code, config_version_id)
);

CREATE TABLE IF NOT EXISTS content.technique_tag_links (
    technique_def_id    uuid NOT NULL REFERENCES content.technique_defs(id) ON DELETE CASCADE,
    tag_id              bigint NOT NULL REFERENCES content.tags(id) ON DELETE CASCADE,
    PRIMARY KEY(technique_def_id, tag_id)
);

CREATE TABLE IF NOT EXISTS content.enemy_defs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code                varchar(96) NOT NULL,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    enemy_type          varchar(32) NOT NULL DEFAULT 'NORMAL',
    name_key            varchar(128) NOT NULL,
    base_stats          jsonb NOT NULL,
    skills              jsonb NOT NULL DEFAULT '[]'::jsonb,
    ai_policy           jsonb NOT NULL DEFAULT '{}'::jsonb,
    reward_table_code   varchar(96),
    tags                varchar(64)[] NOT NULL DEFAULT '{}',
    UNIQUE(code, config_version_id)
);

CREATE TABLE IF NOT EXISTS content.region_defs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code                varchar(96) NOT NULL,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    name_key            varchar(128) NOT NULL,
    ordinal             integer NOT NULL,
    theme_key           varchar(128),
    unlock_rule         jsonb NOT NULL DEFAULT '{}'::jsonb,
    modifiers           jsonb NOT NULL DEFAULT '[]'::jsonb,
    loot_profile_code   varchar(96),
    UNIQUE(code, config_version_id)
);

CREATE TABLE IF NOT EXISTS content.node_defs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    region_def_id       uuid NOT NULL REFERENCES content.region_defs(id) ON DELETE CASCADE,
    node_code           varchar(96) NOT NULL,
    node_type           adventure.node_type NOT NULL,
    ordinal             integer NOT NULL,
    encounter_json      jsonb NOT NULL DEFAULT '{}'::jsonb,
    route_choices       jsonb NOT NULL DEFAULT '[]'::jsonb,
    reward_table_code   varchar(96),
    UNIQUE(region_def_id, node_code)
);

CREATE TABLE IF NOT EXISTS content.building_defs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code                varchar(64) NOT NULL,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    source_game         content.source_game NOT NULL DEFAULT 'RISE_OF_KINGDOMS',
    source_building_key varchar(128),
    source_revision     varchar(64),
    source_metadata     jsonb NOT NULL DEFAULT '{}'::jsonb,
    name_key            varchar(128) NOT NULL,
    max_level           integer NOT NULL,
    level_table         jsonb NOT NULL,
    UNIQUE(code, config_version_id)
);

CREATE TABLE IF NOT EXISTS content.research_defs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code                varchar(96) NOT NULL,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    tree_code           varchar(32) NOT NULL,
    max_level           integer NOT NULL DEFAULT 1,
    prerequisites       jsonb NOT NULL DEFAULT '[]'::jsonb,
    level_table         jsonb NOT NULL,
    effects             jsonb NOT NULL DEFAULT '[]'::jsonb,
    UNIQUE(code, config_version_id)
);

CREATE TABLE IF NOT EXISTS content.combat_profiles (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_code        combat.profile_code NOT NULL,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    crit_cap             numeric(8,6) NOT NULL,
    crit_damage_cap      numeric(8,4),
    penetration_cap      numeric(8,6),
    realm_pressure_cap   numeric(8,6),
    healing_modifier     numeric(8,4) NOT NULL DEFAULT 1,
    shield_modifier      numeric(8,4) NOT NULL DEFAULT 1,
    cc_modifier          numeric(8,4) NOT NULL DEFAULT 1,
    constants            jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(profile_code, config_version_id)
);

-- ============================================================
-- 5. HERO / CHARACTER / CULTIVATION
-- ============================================================
CREATE TABLE IF NOT EXISTS hero.player_heroes (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id           uuid NOT NULL REFERENCES identity.players(id) ON DELETE CASCADE,
    name                citext NOT NULL,
    level               integer NOT NULL DEFAULT 1 CHECK (level > 0),
    xp                  bigint NOT NULL DEFAULT 0 CHECK (xp >= 0),
    race_code           varchar(64) NOT NULL,
    path_code           varchar(64) NOT NULL,
    realm_code          varchar(64) NOT NULL DEFAULT 'MORTAL',
    realm_minor_stage   integer NOT NULL DEFAULT 1 CHECK(realm_minor_stage BETWEEN 1 AND 10),
    cultivation_xp      bigint NOT NULL DEFAULT 0 CHECK (cultivation_xp >= 0),
    tribulation_fail_streak integer NOT NULL DEFAULT 0 CHECK(tribulation_fail_streak >= 0),
    voice_qi_total      bigint NOT NULL DEFAULT 0 CHECK(voice_qi_total >= 0),
    sect_code           varchar(64),
    sect_rank           integer NOT NULL DEFAULT 0,
    sect_reputation     bigint NOT NULL DEFAULT 0 CHECK (sect_reputation >= 0),
    base_stats          jsonb NOT NULL DEFAULT '{}'::jsonb,
    derived_snapshot    jsonb NOT NULL DEFAULT '{}'::jsonb,
    active_loadout_id   uuid,
    portrait_key        varchar(128),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    version             bigint NOT NULL DEFAULT 0,
    UNIQUE(player_id, name),
    UNIQUE(player_id, id)
);
CREATE INDEX IF NOT EXISTS ix_player_heroes_player ON hero.player_heroes(player_id);

ALTER TABLE identity.players
    DROP CONSTRAINT IF EXISTS fk_players_active_hero;
ALTER TABLE identity.players
    ADD CONSTRAINT fk_players_active_hero
    FOREIGN KEY(id, active_hero_id) REFERENCES hero.player_heroes(player_id, id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE IF NOT EXISTS hero.hero_bloodlines (
    hero_id             uuid NOT NULL REFERENCES hero.player_heroes(id) ON DELETE CASCADE,
    bloodline_code      varchar(64) NOT NULL,
    tier                integer NOT NULL DEFAULT 1,
    awakened_at         timestamptz,
    progress            bigint NOT NULL DEFAULT 0,
    state_json          jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY(hero_id, bloodline_code)
);

CREATE TABLE IF NOT EXISTS hero.hero_affinities (
    hero_id             uuid NOT NULL REFERENCES hero.player_heroes(id) ON DELETE CASCADE,
    affinity_code       varchar(64) NOT NULL,
    slot                smallint NOT NULL CHECK(slot BETWEEN 1 AND 2),
    resonance_score     numeric(18,4) NOT NULL DEFAULT 0,
    mastery_level       integer NOT NULL DEFAULT 1,
    PRIMARY KEY(hero_id, affinity_code),
    UNIQUE(hero_id, slot)
);

CREATE TABLE IF NOT EXISTS hero.hero_techniques (
    hero_id             uuid NOT NULL REFERENCES hero.player_heroes(id) ON DELETE CASCADE,
    technique_code      varchar(96) NOT NULL,
    learned_level       integer NOT NULL DEFAULT 1,
    mastery_xp          bigint NOT NULL DEFAULT 0,
    unlocked_at         timestamptz NOT NULL DEFAULT now(),
    source_type         varchar(64),
    source_id           varchar(128),
    PRIMARY KEY(hero_id, technique_code)
);

CREATE TABLE IF NOT EXISTS hero.technique_loadouts (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    hero_id             uuid NOT NULL REFERENCES hero.player_heroes(id) ON DELETE CASCADE,
    name                varchar(64) NOT NULL,
    slot_layout         jsonb NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    version             bigint NOT NULL DEFAULT 0,
    UNIQUE(hero_id, name),
    UNIQUE(hero_id, id)
);

ALTER TABLE hero.player_heroes
    DROP CONSTRAINT IF EXISTS fk_hero_active_loadout;
ALTER TABLE hero.player_heroes
    ADD CONSTRAINT fk_hero_active_loadout
    FOREIGN KEY(id, active_loadout_id) REFERENCES hero.technique_loadouts(hero_id, id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE IF NOT EXISTS hero.talent_nodes (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    path_code           varchar(64) NOT NULL,
    node_code           varchar(96) NOT NULL,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    tier                integer NOT NULL,
    prerequisites       jsonb NOT NULL DEFAULT '[]'::jsonb,
    max_rank            integer NOT NULL DEFAULT 1,
    effects             jsonb NOT NULL DEFAULT '[]'::jsonb,
    UNIQUE(path_code, node_code, config_version_id)
);

CREATE TABLE IF NOT EXISTS hero.hero_talent_allocations (
    hero_id             uuid NOT NULL REFERENCES hero.player_heroes(id) ON DELETE CASCADE,
    talent_node_id      uuid NOT NULL REFERENCES hero.talent_nodes(id),
    rank                integer NOT NULL CHECK(rank > 0),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(hero_id, talent_node_id)
);

CREATE TABLE IF NOT EXISTS hero.profession_progress (
    hero_id             uuid NOT NULL REFERENCES hero.player_heroes(id) ON DELETE CASCADE,
    profession_code     varchar(64) NOT NULL,
    level               integer NOT NULL DEFAULT 1,
    xp                  bigint NOT NULL DEFAULT 0,
    specialization_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_specialized      boolean NOT NULL DEFAULT false,
    PRIMARY KEY(hero_id, profession_code)
);

CREATE TABLE IF NOT EXISTS hero.breakthrough_attempts (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    hero_id             uuid NOT NULL REFERENCES hero.player_heroes(id) ON DELETE CASCADE,
    from_realm_code     varchar(64) NOT NULL,
    to_realm_code       varchar(64) NOT NULL,
    from_stage          smallint NOT NULL DEFAULT 10 CHECK(from_stage BETWEEN 1 AND 10),
    to_stage            smallint CHECK(to_stage BETWEEN 1 AND 10),
    xp_before           bigint NOT NULL DEFAULT 0 CHECK(xp_before >= 0),
    xp_after            bigint CHECK(xp_after IS NULL OR xp_after >= 0),
    fail_streak_before  integer NOT NULL DEFAULT 0 CHECK(fail_streak_before >= 0),
    fail_streak_after   integer CHECK(fail_streak_after IS NULL OR fail_streak_after >= 0),
    base_success_chance numeric(8,6) NOT NULL CHECK(base_success_chance BETWEEN 0 AND 1),
    pity_bonus          numeric(8,6) NOT NULL DEFAULT 0 CHECK(pity_bonus BETWEEN 0 AND 1),
    booster_bonus       numeric(8,6) NOT NULL DEFAULT 0 CHECK(booster_bonus BETWEEN 0 AND 1),
    final_success_chance numeric(8,6) NOT NULL CHECK(final_success_chance BETWEEN 0 AND 1),
    rng_roll            numeric(8,6) CHECK(rng_roll IS NULL OR (rng_roll >= 0 AND rng_roll < 1)),
    protection_used     boolean NOT NULL DEFAULT false,
    booster_used        boolean NOT NULL DEFAULT false,
    protection_item_code varchar(96),
    booster_item_code   varchar(96),
    preparation_json    jsonb NOT NULL DEFAULT '{}'::jsonb,
    combat_instance_id  uuid,
    result              varchar(32) CHECK(result IS NULL OR result IN ('SUCCESS','FAILED_DEFAULT','FAILED_PROTECTED','CANCELLED')),
    consume_operation_id uuid,
    pity_progress       numeric(12,6) NOT NULL DEFAULT 0,
    started_at          timestamptz NOT NULL DEFAULT now(),
    resolved_at         timestamptz,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    CHECK(from_stage = 10),
    CHECK(final_success_chance = LEAST(1::numeric, GREATEST(0::numeric, base_success_chance + pity_bonus + booster_bonus)))
);

CREATE TABLE IF NOT EXISTS hero.voice_cultivation_sessions (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    hero_id             uuid NOT NULL REFERENCES hero.player_heroes(id) ON DELETE CASCADE,
    player_id           uuid NOT NULL REFERENCES identity.players(id) ON DELETE CASCADE,
    guild_binding_id    uuid REFERENCES identity.discord_guild_bindings(id) ON DELETE SET NULL,
    discord_channel_id  bigint,
    joined_at           timestamptz NOT NULL,
    left_at             timestamptz,
    eligible_seconds    bigint NOT NULL DEFAULT 0 CHECK(eligible_seconds >= 0),
    qi_granted          bigint NOT NULL DEFAULT 0 CHECK(qi_granted >= 0),
    eligibility_json    jsonb NOT NULL DEFAULT '{}'::jsonb,
    grant_operation_id  uuid,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    settled_at          timestamptz,
    version             bigint NOT NULL DEFAULT 0,
    FOREIGN KEY(player_id, hero_id) REFERENCES hero.player_heroes(player_id, id)
);
CREATE INDEX IF NOT EXISTS ix_voice_cultivation_player_time
    ON hero.voice_cultivation_sessions(player_id, joined_at DESC);
COMMENT ON TABLE hero.voice_cultivation_sessions IS
'Voice Cultivation stores presence/eligibility settlement metadata only; it does not store or inspect voice audio. /music playback itself is not a reward source.';

-- ============================================================
-- 6. INVENTORY / ITEMS / EQUIPMENT / CRAFTING
-- ============================================================
CREATE TABLE IF NOT EXISTS inventory.item_defs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code                varchar(96) NOT NULL,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    source_game         content.source_game NOT NULL DEFAULT 'PATH_OF_KINGS',
    source_item_key     varchar(128),
    source_revision     varchar(64),
    source_metadata     jsonb NOT NULL DEFAULT '{}'::jsonb,
    item_type           varchar(48) NOT NULL,
    family_code         varchar(64),
    rarity              inventory.item_rarity NOT NULL,
    stackable           boolean NOT NULL DEFAULT false,
    max_stack           bigint,
    bind_rule           varchar(32) NOT NULL DEFAULT 'ACCOUNT',
    transferable        boolean NOT NULL DEFAULT true,
    tags                varchar(64)[] NOT NULL DEFAULT '{}',
    base_stats          jsonb NOT NULL DEFAULT '{}'::jsonb,
    base_effects        jsonb NOT NULL DEFAULT '[]'::jsonb,
    salvage_rule        jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(code, config_version_id)
);

CREATE TABLE IF NOT EXISTS inventory.rarity_policy (
    rarity              inventory.item_rarity PRIMARY KEY,
    power_ordinal       smallint NOT NULL UNIQUE CHECK(power_ordinal > 0)
);
INSERT INTO inventory.rarity_policy(rarity, power_ordinal) VALUES
    ('COMMON',1),('UNCOMMON',2),('RARE',3),('EPIC',4),('LEGENDARY',5)
ON CONFLICT (rarity) DO UPDATE SET power_ordinal=EXCLUDED.power_ordinal;

CREATE OR REPLACE FUNCTION market.can_receive_rarity(
    p_item_rarity inventory.item_rarity,
    p_natural_max inventory.item_rarity
) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT item.power_ordinal <= LEAST(natural.power_ordinal + 1, global_max.max_ordinal)
    FROM inventory.rarity_policy item
    JOIN inventory.rarity_policy natural ON natural.rarity = p_natural_max
    CROSS JOIN (SELECT max(power_ordinal) AS max_ordinal FROM inventory.rarity_policy) global_max
    WHERE item.rarity = p_item_rarity;
$$;
COMMENT ON FUNCTION market.can_receive_rarity(inventory.item_rarity, inventory.item_rarity) IS
'Recipient eligibility helper: market/direct trade item rarity may be at most one tier above the recipient current-floor NaturalMaxRarity.';

CREATE TABLE IF NOT EXISTS inventory.item_instances (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id           uuid NOT NULL REFERENCES identity.players(id) ON DELETE CASCADE,
    hero_id             uuid REFERENCES hero.player_heroes(id) ON DELETE SET NULL,
    item_code           varchar(96) NOT NULL,
    item_config_version_id bigint NOT NULL,
    source_game         content.source_game NOT NULL DEFAULT 'PATH_OF_KINGS',
    source_item_key     varchar(128),
    source_snapshot     jsonb NOT NULL DEFAULT '{}'::jsonb,
    rarity              inventory.item_rarity NOT NULL,
    item_level          integer NOT NULL DEFAULT 1,
    state               inventory.item_state NOT NULL DEFAULT 'OWNED',
    durability          integer,
    affixes             jsonb NOT NULL DEFAULT '[]'::jsonb,
    unique_effects      jsonb NOT NULL DEFAULT '[]'::jsonb,
    provenance          jsonb NOT NULL DEFAULT '{}'::jsonb,
    locked              boolean NOT NULL DEFAULT false,
    acquired_at         timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    version             bigint NOT NULL DEFAULT 0,
    UNIQUE(player_id, id),
    FOREIGN KEY(item_code, item_config_version_id)
        REFERENCES inventory.item_defs(code, config_version_id),
    FOREIGN KEY(player_id, hero_id)
        REFERENCES hero.player_heroes(player_id, id)
);
CREATE INDEX IF NOT EXISTS ix_item_instances_owner
    ON inventory.item_instances(player_id, state, acquired_at DESC);
CREATE INDEX IF NOT EXISTS ix_item_instances_hero
    ON inventory.item_instances(hero_id) WHERE hero_id IS NOT NULL;
COMMENT ON TABLE inventory.item_instances IS
'Equipment may be market/direct-trade eligible when item_defs.transferable=true. LISTED/LOCKED state plus optimistic version prevents equip/sell/transfer races.';

CREATE TABLE IF NOT EXISTS inventory.inventory_stacks (
    player_id           uuid NOT NULL REFERENCES identity.players(id) ON DELETE CASCADE,
    item_code           varchar(96) NOT NULL,
    binding             varchar(32) NOT NULL DEFAULT 'ACCOUNT',
    quantity            bigint NOT NULL DEFAULT 0 CHECK(quantity >= 0),
    version             bigint NOT NULL DEFAULT 0,
    updated_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(player_id, item_code, binding)
);

CREATE TABLE IF NOT EXISTS inventory.equipment_loadouts (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    hero_id             uuid NOT NULL REFERENCES hero.player_heroes(id) ON DELETE CASCADE,
    name                varchar(64) NOT NULL,
    slots               jsonb NOT NULL,
    is_active           boolean NOT NULL DEFAULT false,
    version             bigint NOT NULL DEFAULT 0,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE(hero_id, name)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_equipment_loadout_active_per_hero
    ON inventory.equipment_loadouts(hero_id)
    WHERE is_active = true;


CREATE TABLE IF NOT EXISTS inventory.recipes (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    recipe_code         varchar(96) NOT NULL,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    profession_code     varchar(64),
    required_level      integer NOT NULL DEFAULT 1,
    inputs              jsonb NOT NULL,
    outputs             jsonb NOT NULL,
    duration_seconds    integer NOT NULL DEFAULT 0,
    building_requirement jsonb NOT NULL DEFAULT '{}'::jsonb,
    discovery_rule      jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(recipe_code, config_version_id)
);

CREATE TABLE IF NOT EXISTS inventory.player_recipes (
    player_id           uuid NOT NULL REFERENCES identity.players(id) ON DELETE CASCADE,
    recipe_code         varchar(96) NOT NULL,
    discovered_at       timestamptz NOT NULL DEFAULT now(),
    source_type         varchar(64),
    source_id           varchar(128),
    PRIMARY KEY(player_id, recipe_code)
);

CREATE TABLE IF NOT EXISTS inventory.craft_jobs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id           uuid NOT NULL REFERENCES identity.players(id) ON DELETE CASCADE,
    hero_id             uuid REFERENCES hero.player_heroes(id),
    recipe_code         varchar(96) NOT NULL,
    building_id         uuid,
    status              platform.queue_status NOT NULL DEFAULT 'RUNNING',
    input_operation_id  uuid NOT NULL,
    started_at          timestamptz NOT NULL DEFAULT now(),
    completes_at        timestamptz NOT NULL,
    completed_at        timestamptz,
    output_operation_id uuid,
    result_json         jsonb,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    version             bigint NOT NULL DEFAULT 0,
    CHECK(completes_at >= started_at),
    FOREIGN KEY(player_id, hero_id)
        REFERENCES hero.player_heroes(player_id, id)
);
CREATE INDEX IF NOT EXISTS ix_craft_jobs_due
    ON inventory.craft_jobs(completes_at) WHERE status='RUNNING';

-- ============================================================
-- 7. ADVENTURE / REGIONS / RUNS
-- ============================================================
CREATE TABLE IF NOT EXISTS adventure.player_region_progress (
    player_id           uuid NOT NULL REFERENCES identity.players(id) ON DELETE CASCADE,
    region_code         varchar(96) NOT NULL,
    unlocked_at         timestamptz,
    highest_node_ordinal integer NOT NULL DEFAULT 0,
    boss_kills          integer NOT NULL DEFAULT 0,
    mastery_level       integer NOT NULL DEFAULT 0,
    stars               integer NOT NULL DEFAULT 0,
    best_result_json    jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY(player_id, region_code)
);

CREATE TABLE IF NOT EXISTS adventure.player_exploration_progress (
    player_id           uuid PRIMARY KEY REFERENCES identity.players(id) ON DELETE CASCADE,
    current_floor       integer NOT NULL DEFAULT 1 CHECK(current_floor >= 1),
    highest_floor       integer NOT NULL DEFAULT 1 CHECK(highest_floor >= 1),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    version             bigint NOT NULL DEFAULT 0,
    CHECK(highest_floor >= current_floor)
);
CREATE INDEX IF NOT EXISTS ix_exploration_highest_floor
    ON adventure.player_exploration_progress(highest_floor DESC);

CREATE TABLE IF NOT EXISTS adventure.adventure_runs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id           uuid NOT NULL REFERENCES identity.players(id) ON DELETE CASCADE,
    hero_id             uuid NOT NULL REFERENCES hero.player_heroes(id),
    region_code         varchar(96) NOT NULL,
    region_config_version bigint NOT NULL,
    status              adventure.run_status NOT NULL DEFAULT 'ACTIVE',
    current_node_code   varchar(96),
    route_state         jsonb NOT NULL DEFAULT '{}'::jsonb,
    run_modifiers       jsonb NOT NULL DEFAULT '[]'::jsonb,
    consumable_state    jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at          timestamptz NOT NULL DEFAULT now(),
    last_action_at      timestamptz NOT NULL DEFAULT now(),
    completed_at        timestamptz,
    version             bigint NOT NULL DEFAULT 0,
    FOREIGN KEY(region_code, region_config_version)
        REFERENCES content.region_defs(code, config_version_id),
    FOREIGN KEY(player_id, hero_id)
        REFERENCES hero.player_heroes(player_id, id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_active_run_per_player
    ON adventure.adventure_runs(player_id)
    WHERE status IN ('ACTIVE','PAUSED');

CREATE TABLE IF NOT EXISTS adventure.run_node_states (
    run_id              uuid NOT NULL REFERENCES adventure.adventure_runs(id) ON DELETE CASCADE,
    node_code           varchar(96) NOT NULL,
    node_type           adventure.node_type NOT NULL,
    state               varchar(32) NOT NULL DEFAULT 'AVAILABLE',
    encounter_snapshot  jsonb,
    reward_snapshot     jsonb,
    entered_at          timestamptz,
    resolved_at         timestamptz,
    PRIMARY KEY(run_id, node_code)
);

CREATE TABLE IF NOT EXISTS adventure.energy_balances (
    player_id           uuid PRIMARY KEY REFERENCES identity.players(id) ON DELETE CASCADE,
    current_value       integer NOT NULL DEFAULT 0 CHECK(current_value >= 0),
    cap_value           integer NOT NULL CHECK(cap_value > 0),
    last_regen_at       timestamptz NOT NULL DEFAULT now(),
    regen_seconds       integer NOT NULL CHECK(regen_seconds > 0),
    version             bigint NOT NULL DEFAULT 0
);

-- ============================================================
-- 8. COMBAT ENGINE v2
-- ============================================================
CREATE TABLE IF NOT EXISTS combat.combat_instances (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id           uuid REFERENCES identity.players(id) ON DELETE SET NULL,
    hero_id             uuid REFERENCES hero.player_heroes(id) ON DELETE SET NULL,
    source_type         varchar(48) NOT NULL,
    source_id           uuid,
    profile_code        combat.profile_code NOT NULL,
    combat_version      varchar(64) NOT NULL,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    seed_ref            varchar(128) NOT NULL,
    rng_algorithm_version varchar(48) NOT NULL DEFAULT 'XOSHIRO256SS_V1',
    seed_commitment     varchar(128),
    status              combat.combat_status NOT NULL DEFAULT 'CREATED',
    round_number        integer NOT NULL DEFAULT 0,
    current_actor_ref   varchar(128),
    summary_state       jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),
    started_at          timestamptz,
    ended_at            timestamptz,
    settled_at          timestamptz,
    version             bigint NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_combat_player_status
    ON combat.combat_instances(player_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS combat.actor_snapshots (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    combat_id           uuid NOT NULL REFERENCES combat.combat_instances(id) ON DELETE CASCADE,
    actor_key           varchar(128) NOT NULL,
    actor_type          combat.actor_type NOT NULL,
    source_entity_id    uuid,
    level               integer NOT NULL,
    realm_code          varchar(64),
    realm_minor_stage   integer,
    tags                varchar(64)[] NOT NULL DEFAULT '{}',
    stats               jsonb NOT NULL,
    loadout             jsonb NOT NULL DEFAULT '{}'::jsonb,
    effects             jsonb NOT NULL DEFAULT '[]'::jsonb,
    initial_hp          numeric(24,6) NOT NULL,
    initial_resource    jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(combat_id, actor_key)
);

CREATE TABLE IF NOT EXISTS combat.combat_actions (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    combat_id           uuid NOT NULL REFERENCES combat.combat_instances(id) ON DELETE CASCADE,
    round_number        integer NOT NULL,
    sequence_no         integer NOT NULL,
    actor_key           varchar(128) NOT NULL,
    target_key          varchar(128),
    action_type         varchar(48) NOT NULL,
    action_code         varchar(96),
    command_json        jsonb NOT NULL DEFAULT '{}'::jsonb,
    expected_state_version bigint,
    submitted_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE(combat_id, round_number, sequence_no)
);

CREATE TABLE IF NOT EXISTS combat.status_instances (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    combat_id           uuid NOT NULL REFERENCES combat.combat_instances(id) ON DELETE CASCADE,
    target_key          varchar(128) NOT NULL,
    source_key          varchar(128),
    status_code         varchar(96) NOT NULL,
    status_version      bigint NOT NULL,
    stacks              integer NOT NULL DEFAULT 1,
    remaining_rounds    integer,
    potency_snapshot    numeric(24,6),
    state_json          jsonb NOT NULL DEFAULT '{}'::jsonb,
    applied_round       integer NOT NULL,
    expires_round       integer,
    active              boolean NOT NULL DEFAULT true
);
CREATE INDEX IF NOT EXISTS ix_status_active
    ON combat.status_instances(combat_id, target_key) WHERE active=true;

CREATE TABLE IF NOT EXISTS combat.combat_events (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    combat_id           uuid NOT NULL REFERENCES combat.combat_instances(id) ON DELETE CASCADE,
    sequence_no         bigint NOT NULL,
    round_number        integer NOT NULL,
    phase               varchar(48) NOT NULL,
    actor_key           varchar(128),
    target_key          varchar(128),
    event_type          varchar(96) NOT NULL,
    source_code         varchar(128),
    numeric_payload     jsonb NOT NULL DEFAULT '{}'::jsonb,
    detail_payload      jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE(combat_id, sequence_no)
);
-- Intentionally unpartitioned in DB v1.2: replay correctness requires global uniqueness
-- of (combat_id, sequence_no). Partition only after a cross-partition uniqueness strategy is locked.

CREATE INDEX IF NOT EXISTS ix_combat_events_combat_seq
    ON combat.combat_events(combat_id, sequence_no);

CREATE TABLE IF NOT EXISTS combat.combat_settlements (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    combat_id           uuid NOT NULL UNIQUE REFERENCES combat.combat_instances(id),
    outcome             varchar(32) NOT NULL,
    reward_operation_id uuid,
    score_json          jsonb NOT NULL DEFAULT '{}'::jsonb,
    contribution_json   jsonb NOT NULL DEFAULT '{}'::jsonb,
    settled_at          timestamptz NOT NULL DEFAULT now()
);

-- ============================================================
-- 9. KINGDOM / BUILDINGS / RESEARCH
-- ============================================================
CREATE TABLE IF NOT EXISTS kingdom.player_kingdoms (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id           uuid NOT NULL UNIQUE REFERENCES identity.players(id) ON DELETE CASCADE,
    level               integer NOT NULL DEFAULT 1,
    castle_level        integer NOT NULL DEFAULT 1,
    banner_key          varchar(128),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    version             bigint NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS kingdom.kingdom_buildings (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kingdom_id          uuid NOT NULL REFERENCES kingdom.player_kingdoms(id) ON DELETE CASCADE,
    building_code       varchar(64) NOT NULL,
    level               integer NOT NULL DEFAULT 0 CHECK(level >= 0),
    state_json          jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at          timestamptz NOT NULL DEFAULT now(),
    version             bigint NOT NULL DEFAULT 0,
    UNIQUE(kingdom_id, building_code),
    UNIQUE(kingdom_id, id)
);

CREATE TABLE IF NOT EXISTS kingdom.construction_jobs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kingdom_id          uuid NOT NULL REFERENCES kingdom.player_kingdoms(id) ON DELETE CASCADE,
    building_id         uuid NOT NULL REFERENCES kingdom.kingdom_buildings(id),
    from_level          integer NOT NULL,
    to_level            integer NOT NULL,
    queue_slot          integer NOT NULL DEFAULT 1,
    status              platform.queue_status NOT NULL DEFAULT 'RUNNING',
    cost_operation_id   uuid NOT NULL,
    base_duration_seconds integer NOT NULL,
    help_seconds_applied integer NOT NULL DEFAULT 0,
    started_at          timestamptz NOT NULL DEFAULT now(),
    completes_at        timestamptz NOT NULL,
    completed_at        timestamptz,
    apply_operation_id  uuid,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    version             bigint NOT NULL DEFAULT 0,
    CHECK(to_level > from_level),
    CHECK(base_duration_seconds > 0),
    CHECK(help_seconds_applied >= 0),
    CHECK(completes_at >= started_at),
    FOREIGN KEY(kingdom_id, building_id)
        REFERENCES kingdom.kingdom_buildings(kingdom_id, id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_construction_slot_running
    ON kingdom.construction_jobs(kingdom_id, queue_slot)
    WHERE status='RUNNING';

CREATE TABLE IF NOT EXISTS kingdom.player_research (
    kingdom_id          uuid NOT NULL REFERENCES kingdom.player_kingdoms(id) ON DELETE CASCADE,
    research_code       varchar(96) NOT NULL,
    level               integer NOT NULL DEFAULT 0,
    updated_at          timestamptz NOT NULL DEFAULT now(),
    version             bigint NOT NULL DEFAULT 0,
    PRIMARY KEY(kingdom_id, research_code)
);

CREATE TABLE IF NOT EXISTS kingdom.research_jobs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kingdom_id          uuid NOT NULL REFERENCES kingdom.player_kingdoms(id) ON DELETE CASCADE,
    research_code       varchar(96) NOT NULL,
    from_level          integer NOT NULL,
    to_level            integer NOT NULL,
    status              platform.queue_status NOT NULL DEFAULT 'RUNNING',
    cost_operation_id   uuid NOT NULL,
    help_seconds_applied integer NOT NULL DEFAULT 0,
    started_at          timestamptz NOT NULL DEFAULT now(),
    completes_at        timestamptz NOT NULL,
    completed_at        timestamptz,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    version             bigint NOT NULL DEFAULT 0,
    CHECK(to_level > from_level),
    CHECK(help_seconds_applied >= 0),
    CHECK(completes_at >= started_at)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_research_running
    ON kingdom.research_jobs(kingdom_id) WHERE status='RUNNING';

CREATE TABLE IF NOT EXISTS kingdom.production_sites (
    kingdom_id          uuid NOT NULL REFERENCES kingdom.player_kingdoms(id) ON DELETE CASCADE,
    resource_code       varchar(64) NOT NULL,
    building_code       varchar(64) NOT NULL,
    production_per_hour numeric(24,6) NOT NULL DEFAULT 0,
    storage_cap         numeric(24,6) NOT NULL DEFAULT 0,
    stored_amount       numeric(24,6) NOT NULL DEFAULT 0,
    last_accrual_at     timestamptz NOT NULL DEFAULT now(),
    version             bigint NOT NULL DEFAULT 0,
    PRIMARY KEY(kingdom_id, resource_code, building_code)
);

-- ============================================================
-- 10. ECONOMY / REWARDS / LEDGER
-- ============================================================
CREATE TABLE IF NOT EXISTS economy.asset_defs (
    code                varchar(64) PRIMARY KEY,
    asset_type          varchar(32) NOT NULL,
    integrity_tier      platform.integrity_tier NOT NULL,
    precision_scale     integer NOT NULL DEFAULT 0,
    transferable        boolean NOT NULL DEFAULT false,
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE economy.asset_defs IS
'v4.0 expected gameplay assets include GOLD, SP_POINT (Skill Points) and construction resources. Cultivation Linh khí is hero progression state settled through auditable operations, not Mystic Power/MYS.';

CREATE TABLE IF NOT EXISTS economy.ledger_accounts (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_scope         platform.entity_scope NOT NULL,
    owner_id            uuid,
    asset_code          varchar(64) NOT NULL REFERENCES economy.asset_defs(code),
    available_balance   numeric(30,8) NOT NULL DEFAULT 0,
    reserved_balance    numeric(30,8) NOT NULL DEFAULT 0,
    sequence_no         bigint NOT NULL DEFAULT 0,
    version             bigint NOT NULL DEFAULT 0,
    created_at          timestamptz NOT NULL DEFAULT now(),
    CHECK ((owner_scope = 'SYSTEM' AND owner_id IS NULL)
        OR (owner_scope <> 'SYSTEM' AND owner_id IS NOT NULL)),
    UNIQUE NULLS NOT DISTINCT (owner_scope, owner_id, asset_code)
);

CREATE TABLE IF NOT EXISTS economy.ledger_operations (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    operation_type      varchar(96) NOT NULL,
    actor_type          varchar(64),
    actor_id            uuid,
    source_type         varchar(64) NOT NULL,
    source_id           varchar(128),
    reason_code         varchar(96) NOT NULL,
    idempotency_key     varchar(160) NOT NULL,
    config_version_id   bigint REFERENCES platform.config_versions(id),
    request_id          varchar(128),
    status              varchar(32) NOT NULL DEFAULT 'COMMITTED',
    created_at          timestamptz NOT NULL DEFAULT now(),
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE NULLS NOT DISTINCT (operation_type, actor_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS economy.ledger_entries (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    operation_id        uuid NOT NULL REFERENCES economy.ledger_operations(id),
    ledger_account_id   uuid NOT NULL REFERENCES economy.ledger_accounts(id),
    account_sequence    bigint NOT NULL,
    delta_available     numeric(30,8) NOT NULL DEFAULT 0,
    delta_reserved      numeric(30,8) NOT NULL DEFAULT 0,
    balance_before      numeric(30,8) NOT NULL,
    balance_after       numeric(30,8) NOT NULL,
    entry_role          varchar(32) NOT NULL DEFAULT 'PRIMARY',
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE(ledger_account_id, account_sequence)
);
-- Intentionally unpartitioned in DB v1.2: ledger correctness requires one global
-- sequence number per ledger account. Partition only after preserving that invariant.
CREATE INDEX IF NOT EXISTS ix_ledger_operation
    ON economy.ledger_entries(operation_id);
CREATE INDEX IF NOT EXISTS ix_ledger_account_time
    ON economy.ledger_entries(ledger_account_id, created_at DESC);

CREATE TABLE IF NOT EXISTS economy.reward_grants (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id           uuid NOT NULL REFERENCES identity.players(id) ON DELETE CASCADE,
    grant_type          varchar(64) NOT NULL,
    source_type         varchar(64) NOT NULL,
    source_id           varchar(128) NOT NULL,
    eligibility_key     varchar(160),
    reward_bundle       jsonb NOT NULL,
    operation_id        uuid REFERENCES economy.ledger_operations(id),
    status              varchar(32) NOT NULL DEFAULT 'PENDING',
    created_at          timestamptz NOT NULL DEFAULT now(),
    granted_at          timestamptz,
    UNIQUE NULLS NOT DISTINCT (player_id, grant_type, source_type, source_id, eligibility_key)
);

CREATE TABLE IF NOT EXISTS economy.inventory_operations (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id           uuid NOT NULL REFERENCES identity.players(id),
    operation_type      varchar(64) NOT NULL,
    source_type         varchar(64) NOT NULL,
    source_id           varchar(128),
    idempotency_key     varchar(160) NOT NULL,
    before_hash         varchar(128),
    after_hash          varchar(128),
    detail_json         jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE(player_id, operation_type, idempotency_key)
);

-- ============================================================
-- 11. CLAN SOCIAL SYSTEM
-- ============================================================
CREATE TABLE IF NOT EXISTS clan.clans (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    public_id           uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    name                citext NOT NULL UNIQUE,
    tag                 citext NOT NULL UNIQUE,
    leader_player_id    uuid NOT NULL REFERENCES identity.players(id),
    level               integer NOT NULL DEFAULT 1,
    xp                  bigint NOT NULL DEFAULT 0,
    member_cap          integer NOT NULL DEFAULT 50,
    join_policy         varchar(32) NOT NULL DEFAULT 'APPLICATION',
    description         text,
    banner_key          varchar(128),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    version             bigint NOT NULL DEFAULT 0
);

ALTER TABLE identity.discord_guild_bindings
    DROP CONSTRAINT IF EXISTS fk_guild_binding_clan;
ALTER TABLE identity.discord_guild_bindings
    ADD CONSTRAINT fk_guild_binding_clan
    FOREIGN KEY(clan_id) REFERENCES clan.clans(id) DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE IF NOT EXISTS clan.clan_members (
    clan_id             uuid NOT NULL REFERENCES clan.clans(id) ON DELETE CASCADE,
    player_id           uuid NOT NULL UNIQUE REFERENCES identity.players(id) ON DELETE CASCADE,
    rank                clan.member_rank NOT NULL DEFAULT 'RECRUIT',
    contribution        bigint NOT NULL DEFAULT 0,
    joined_at           timestamptz NOT NULL DEFAULT now(),
    last_active_at      timestamptz,
    probation_until     timestamptz,
    PRIMARY KEY(clan_id, player_id)
);
CREATE INDEX IF NOT EXISTS ix_clan_members_clan_rank
    ON clan.clan_members(clan_id, rank);

CREATE TABLE IF NOT EXISTS clan.clan_permissions (
    clan_id             uuid NOT NULL REFERENCES clan.clans(id) ON DELETE CASCADE,
    rank                clan.member_rank NOT NULL,
    permission_code     varchar(96) NOT NULL,
    allowed             boolean NOT NULL DEFAULT true,
    PRIMARY KEY(clan_id, rank, permission_code)
);

CREATE TABLE IF NOT EXISTS clan.clan_applications (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    clan_id             uuid NOT NULL REFERENCES clan.clans(id) ON DELETE CASCADE,
    player_id           uuid NOT NULL REFERENCES identity.players(id) ON DELETE CASCADE,
    message             text,
    status              varchar(32) NOT NULL DEFAULT 'PENDING',
    created_at          timestamptz NOT NULL DEFAULT now(),
    resolved_at         timestamptz,
    resolved_by         uuid REFERENCES identity.players(id),
    UNIQUE(clan_id, player_id, status)
);

CREATE TABLE IF NOT EXISTS clan.clan_help_requests (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    clan_id             uuid NOT NULL REFERENCES clan.clans(id) ON DELETE CASCADE,
    requester_player_id uuid NOT NULL REFERENCES identity.players(id),
    target_type         varchar(32) NOT NULL,
    target_id           uuid NOT NULL,
    requested_at        timestamptz NOT NULL DEFAULT now(),
    expires_at          timestamptz NOT NULL,
    max_help_count      integer NOT NULL,
    current_help_count  integer NOT NULL DEFAULT 0,
    max_reduction_seconds integer NOT NULL,
    applied_reduction_seconds integer NOT NULL DEFAULT 0,
    status              varchar(32) NOT NULL DEFAULT 'OPEN',
    version             bigint NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS clan.clan_help_actions (
    request_id          uuid NOT NULL REFERENCES clan.clan_help_requests(id) ON DELETE CASCADE,
    helper_player_id    uuid NOT NULL REFERENCES identity.players(id) ON DELETE CASCADE,
    reduction_seconds   integer NOT NULL CHECK(reduction_seconds > 0),
    created_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(request_id, helper_player_id)
);

CREATE TABLE IF NOT EXISTS clan.clan_tech_defs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tech_code           varchar(96) NOT NULL,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    branch_code         varchar(32) NOT NULL,
    max_level           integer NOT NULL,
    level_table         jsonb NOT NULL,
    effects             jsonb NOT NULL DEFAULT '[]'::jsonb,
    UNIQUE(tech_code, config_version_id)
);

CREATE TABLE IF NOT EXISTS clan.clan_technology (
    clan_id             uuid NOT NULL REFERENCES clan.clans(id) ON DELETE CASCADE,
    tech_code           varchar(96) NOT NULL,
    level               integer NOT NULL DEFAULT 0,
    progress_points     bigint NOT NULL DEFAULT 0,
    version             bigint NOT NULL DEFAULT 0,
    PRIMARY KEY(clan_id, tech_code)
);

COMMENT ON TABLE clan.clan_tech_defs IS
'v4.0 effects may include EQUIPMENT_DROP_LEVEL_PCT. Product example: technology level 10 grants +10% generated monster equipment item level; this does not raise rarity chance.';

CREATE TABLE IF NOT EXISTS clan.clan_donations (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    clan_id             uuid NOT NULL REFERENCES clan.clans(id),
    player_id           uuid NOT NULL REFERENCES identity.players(id),
    tech_code           varchar(96),
    operation_id        uuid REFERENCES economy.ledger_operations(id),
    contribution_points bigint NOT NULL DEFAULT 0,
    created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_clan_donation_member_day
    ON clan.clan_donations(clan_id, player_id, created_at DESC);

CREATE TABLE IF NOT EXISTS clan.clan_quest_defs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    quest_code          varchar(96) NOT NULL,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    objective_json      jsonb NOT NULL,
    reward_json         jsonb NOT NULL,
    duration_seconds    integer,
    UNIQUE(quest_code, config_version_id)
);

CREATE TABLE IF NOT EXISTS clan.clan_quests (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    clan_id             uuid NOT NULL REFERENCES clan.clans(id) ON DELETE CASCADE,
    quest_code          varchar(96) NOT NULL,
    starts_at           timestamptz NOT NULL,
    ends_at             timestamptz NOT NULL,
    progress_json       jsonb NOT NULL DEFAULT '{}'::jsonb,
    status              varchar(32) NOT NULL DEFAULT 'ACTIVE',
    version             bigint NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS clan.clan_quest_contributions (
    clan_quest_id       uuid NOT NULL REFERENCES clan.clan_quests(id) ON DELETE CASCADE,
    player_id           uuid NOT NULL REFERENCES identity.players(id),
    contribution_json   jsonb NOT NULL DEFAULT '{}'::jsonb,
    eligibility         boolean NOT NULL DEFAULT false,
    PRIMARY KEY(clan_quest_id, player_id)
);


-- ============================================================
-- 11B. RISE OF KINGDOMS-SOURCED ALLIANCE STRUCTURES
-- Internal DB keeps clan.* for compatibility; product naming may be Alliance.
-- ============================================================
CREATE TABLE IF NOT EXISTS clan.alliance_building_defs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code varchar(96) NOT NULL,
    config_version_id bigint NOT NULL REFERENCES platform.config_versions(id),
    source_game content.source_game NOT NULL DEFAULT 'RISE_OF_KINGDOMS',
    source_building_key varchar(128),
    source_revision varchar(64),
    name_key varchar(128) NOT NULL,
    category varchar(48) NOT NULL,
    max_level integer NOT NULL DEFAULT 1 CHECK(max_level > 0),
    placement_mode varchar(32) NOT NULL DEFAULT 'NON_SPATIAL',
    level_table jsonb NOT NULL DEFAULT '{}'::jsonb,
    costs jsonb NOT NULL DEFAULT '{}'::jsonb,
    effects jsonb NOT NULL DEFAULT '[]'::jsonb,
    unlock_rule jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    status platform.record_status NOT NULL DEFAULT 'ACTIVE',
    UNIQUE(code, config_version_id)
);

CREATE TABLE IF NOT EXISTS clan.alliance_buildings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    clan_id uuid NOT NULL REFERENCES clan.clans(id) ON DELETE CASCADE,
    building_code varchar(96) NOT NULL,
    level integer NOT NULL DEFAULT 0 CHECK(level >= 0),
    progress_points bigint NOT NULL DEFAULT 0 CHECK(progress_points >= 0),
    state_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    version bigint NOT NULL DEFAULT 0,
    UNIQUE(clan_id, building_code)
);

CREATE TABLE IF NOT EXISTS clan.alliance_building_contributions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    clan_id uuid NOT NULL REFERENCES clan.clans(id) ON DELETE CASCADE,
    alliance_building_id uuid NOT NULL REFERENCES clan.alliance_buildings(id) ON DELETE CASCADE,
    player_id uuid NOT NULL REFERENCES identity.players(id),
    contribution_type varchar(48) NOT NULL,
    operation_id uuid REFERENCES economy.ledger_operations(id),
    contribution_points bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_alliance_building_contrib
    ON clan.alliance_building_contributions(clan_id, alliance_building_id, created_at DESC);

-- ============================================================
-- 11C. COMMANDER SYSTEM — GAMEPLAY ACTIVE IN V4.0
-- Commander core is active; stat/skill budget remains versioned config.
-- ============================================================
CREATE TABLE IF NOT EXISTS commander.commander_defs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code varchar(96) NOT NULL,
    config_version_id bigint NOT NULL REFERENCES platform.config_versions(id),
    source_game content.source_game NOT NULL DEFAULT 'RISE_OF_KINGDOMS',
    source_commander_key varchar(128),
    source_revision varchar(64),
    name_key varchar(128) NOT NULL,
    rarity_code varchar(32),
    archetype_tags varchar(64)[] NOT NULL DEFAULT '{}',
    role_tags varchar(64)[] NOT NULL DEFAULT '{}',
    base_profile jsonb NOT NULL DEFAULT '{}'::jsonb,
    skill_profile jsonb NOT NULL DEFAULT '[]'::jsonb,
    talent_profile jsonb NOT NULL DEFAULT '{}'::jsonb,
    acquisition_rule jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    max_level integer NOT NULL DEFAULT 5000 CHECK(max_level = 5000),
    gameplay_enabled boolean NOT NULL DEFAULT true,
    status platform.record_status NOT NULL DEFAULT 'ACTIVE',
    UNIQUE(code, config_version_id)
);

CREATE TABLE IF NOT EXISTS commander.player_commanders (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id uuid NOT NULL REFERENCES identity.players(id) ON DELETE CASCADE,
    commander_code varchar(96) NOT NULL,
    level integer NOT NULL DEFAULT 1 CHECK(level BETWEEN 1 AND 5000),
    xp bigint NOT NULL DEFAULT 0 CHECK(xp >= 0),
    gold_spent_total numeric(30,0) NOT NULL DEFAULT 0 CHECK(gold_spent_total >= 0),
    star_level integer NOT NULL DEFAULT 1 CHECK(star_level > 0),
    skill_state jsonb NOT NULL DEFAULT '{}'::jsonb,
    talent_state jsonb NOT NULL DEFAULT '{}'::jsonb,
    equipment_state jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    status commander.commander_status NOT NULL DEFAULT 'OWNED',
    acquired_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    version bigint NOT NULL DEFAULT 0,
    UNIQUE(player_id, commander_code),
    UNIQUE(player_id, id)
);

CREATE TABLE IF NOT EXISTS commander.commander_presets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id uuid NOT NULL REFERENCES identity.players(id) ON DELETE CASCADE,
    name varchar(64) NOT NULL,
    primary_commander_id uuid REFERENCES commander.player_commanders(id),
    secondary_commander_id uuid REFERENCES commander.player_commanders(id),
    context_code varchar(48) NOT NULL DEFAULT 'MARCH',
    preset_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    active boolean NOT NULL DEFAULT false,
    version bigint NOT NULL DEFAULT 0,
    UNIQUE(player_id, name)
);

CREATE INDEX IF NOT EXISTS ix_commander_player
    ON commander.player_commanders(player_id, status);
CREATE INDEX IF NOT EXISTS ix_alliance_buildings_clan
    ON clan.alliance_buildings(clan_id, building_code);

COMMENT ON TABLE commander.commander_defs IS
'v4.0 Commander catalog is gameplay-active. Core rule: Commander level is 1..5000; march/combat effects remain versioned config, not hidden damage multipliers.';
COMMENT ON TABLE commander.player_commanders IS
'Commander ownership state is separate from the Lost Kingsland Hero/Cultivation character. v4.0 max level is 5000 and upgrades spend Gold through commander.level_up_events.';



CREATE TABLE IF NOT EXISTS commander.level_up_events (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    player_commander_id uuid NOT NULL REFERENCES commander.player_commanders(id) ON DELETE CASCADE,
    player_id           uuid NOT NULL REFERENCES identity.players(id) ON DELETE CASCADE,
    from_level          integer NOT NULL CHECK(from_level BETWEEN 1 AND 4999),
    to_level            integer NOT NULL CHECK(to_level BETWEEN 2 AND 5000),
    gold_cost           numeric(30,0) NOT NULL CHECK(gold_cost > 0),
    ledger_operation_id uuid NOT NULL REFERENCES economy.ledger_operations(id),
    idempotency_key     varchar(160) NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    CHECK(to_level = from_level + 1),
    CHECK(gold_cost = 1000 + 100 * (from_level - 1)),
    UNIQUE(player_commander_id, from_level, to_level),
    UNIQUE(player_id, idempotency_key),
    FOREIGN KEY(player_id, player_commander_id) REFERENCES commander.player_commanders(player_id, id)
);
COMMENT ON TABLE commander.level_up_events IS
'v4.0 Gold sink: upgrading Commander L->L+1 costs 1000 + 100*(L-1); max level 5000.';

-- ============================================================
-- 11D. MULTI-MARCH / MONSTER HUNT / SHARED RESOURCE SITES
-- Non-spatial asynchronous dispatch; no pathfinding/coordinates.
-- ============================================================
CREATE TABLE IF NOT EXISTS march.player_march_slots (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id           uuid NOT NULL REFERENCES identity.players(id) ON DELETE CASCADE,
    slot_no             smallint NOT NULL CHECK(slot_no BETWEEN 1 AND 5),
    commander_id        uuid REFERENCES commander.player_commanders(id) ON DELETE SET NULL,
    status              march.march_status NOT NULL DEFAULT 'AVAILABLE',
    assignment_type     march.assignment_type,
    loadout_snapshot    jsonb NOT NULL DEFAULT '{}'::jsonb,
    unlocked_at_city_hall_level integer,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    version             bigint NOT NULL DEFAULT 0,
    UNIQUE(player_id, slot_no),
    UNIQUE(player_id, id),
    FOREIGN KEY(player_id, commander_id) REFERENCES commander.player_commanders(player_id, id)
);
CREATE INDEX IF NOT EXISTS ix_march_slots_player_status
    ON march.player_march_slots(player_id, status, slot_no);

CREATE TABLE IF NOT EXISTS march.hunt_loops (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    march_slot_id       uuid NOT NULL REFERENCES march.player_march_slots(id) ON DELETE CASCADE,
    player_id           uuid NOT NULL REFERENCES identity.players(id) ON DELETE CASCADE,
    exploration_floor   integer NOT NULL CHECK(exploration_floor >= 1),
    monster_profile_code varchar(96) NOT NULL,
    status              varchar(32) NOT NULL DEFAULT 'RUNNING' CHECK(status IN ('RUNNING','STOP_REQUESTED','STOPPED','FAILED','COMPLETED')),
    current_round       bigint NOT NULL DEFAULT 0 CHECK(current_round >= 0),
    started_at          timestamptz NOT NULL DEFAULT now(),
    stopped_at          timestamptz,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    version             bigint NOT NULL DEFAULT 0,
    FOREIGN KEY(player_id, march_slot_id) REFERENCES march.player_march_slots(player_id, id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_hunt_loop_active_slot
    ON march.hunt_loops(march_slot_id) WHERE status IN ('RUNNING','STOP_REQUESTED');

CREATE TABLE IF NOT EXISTS march.hunt_rounds (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    hunt_loop_id        uuid NOT NULL REFERENCES march.hunt_loops(id) ON DELETE CASCADE,
    round_no            bigint NOT NULL CHECK(round_no > 0),
    combat_instance_id  uuid NOT NULL UNIQUE REFERENCES combat.combat_instances(id),
    reward_grant_id     uuid REFERENCES economy.reward_grants(id),
    exploration_floor_snapshot integer NOT NULL CHECK(exploration_floor_snapshot >= 1),
    clan_id_snapshot    uuid REFERENCES clan.clans(id) ON DELETE SET NULL,
    clan_drop_level_bonus_pct numeric(8,6) NOT NULL DEFAULT 0 CHECK(clan_drop_level_bonus_pct >= 0),
    loot_snapshot       jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at          timestamptz NOT NULL DEFAULT now(),
    settled_at          timestamptz,
    UNIQUE(hunt_loop_id, round_no)
);

CREATE TABLE IF NOT EXISTS march.resource_sites (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    resource_code       varchar(64) NOT NULL,
    tier                integer NOT NULL CHECK(tier > 0),
    richness_code       varchar(48) NOT NULL,
    initial_amount      numeric(30,8) NOT NULL CHECK(initial_amount > 0),
    remaining_amount    numeric(30,8) NOT NULL CHECK(remaining_amount >= 0),
    base_gather_rate_per_second numeric(30,8) NOT NULL CHECK(base_gather_rate_per_second > 0),
    status              march.resource_site_status NOT NULL DEFAULT 'AVAILABLE',
    generated_from      varchar(64),
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    created_at          timestamptz NOT NULL DEFAULT now(),
    reopened_at         timestamptz,
    depleted_at         timestamptz,
    version             bigint NOT NULL DEFAULT 0,
    CHECK(remaining_amount <= initial_amount)
);
CREATE INDEX IF NOT EXISTS ix_resource_site_find
    ON march.resource_sites(resource_code, tier, status, remaining_amount)
    WHERE status='AVAILABLE' AND remaining_amount > 0;

CREATE TABLE IF NOT EXISTS march.gather_jobs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    march_slot_id       uuid NOT NULL REFERENCES march.player_march_slots(id) ON DELETE CASCADE,
    player_id           uuid NOT NULL REFERENCES identity.players(id) ON DELETE CASCADE,
    resource_site_id    uuid NOT NULL REFERENCES march.resource_sites(id),
    status              varchar(32) NOT NULL DEFAULT 'RUNNING' CHECK(status IN ('RUNNING','WITHDRAW_REQUESTED','WITHDRAWN','DEPLETED','FAILED')),
    start_remaining_amount numeric(30,8) NOT NULL CHECK(start_remaining_amount >= 0),
    gather_rate_per_second numeric(30,8) NOT NULL CHECK(gather_rate_per_second > 0),
    gathered_amount     numeric(30,8) NOT NULL DEFAULT 0 CHECK(gathered_amount >= 0),
    started_at          timestamptz NOT NULL DEFAULT now(),
    last_settled_at     timestamptz NOT NULL DEFAULT now(),
    ended_at            timestamptz,
    settlement_operation_id uuid REFERENCES economy.ledger_operations(id),
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    version             bigint NOT NULL DEFAULT 0,
    FOREIGN KEY(player_id, march_slot_id) REFERENCES march.player_march_slots(player_id, id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_gather_active_slot
    ON march.gather_jobs(march_slot_id) WHERE status IN ('RUNNING','WITHDRAW_REQUESTED');
CREATE UNIQUE INDEX IF NOT EXISTS ux_gather_active_site
    ON march.gather_jobs(resource_site_id) WHERE status IN ('RUNNING','WITHDRAW_REQUESTED');
COMMENT ON TABLE march.gather_jobs IS
'Withdraw may be requested at any time. Service settles accrued amount to the withdrawal timestamp, releases remaining site capacity, and makes the march slot immediately reusable; there is no gameplay return cooldown.';

-- ============================================================
-- 11E. PLAYER MARKET / DIRECT EQUIPMENT TRADE
-- Same recipient rarity gate is authoritative for BOTH paths.
-- ============================================================
CREATE TABLE IF NOT EXISTS market.listings (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    seller_player_id    uuid NOT NULL REFERENCES identity.players(id) ON DELETE CASCADE,
    item_instance_id    uuid NOT NULL REFERENCES inventory.item_instances(id),
    listed_rarity       inventory.item_rarity NOT NULL,
    listed_item_level   integer NOT NULL CHECK(listed_item_level > 0),
    price_asset_code    varchar(64) NOT NULL REFERENCES economy.asset_defs(code),
    price_amount        numeric(30,8) NOT NULL CHECK(price_amount > 0),
    status              market.listing_status NOT NULL DEFAULT 'ACTIVE',
    buyer_player_id     uuid REFERENCES identity.players(id),
    created_at          timestamptz NOT NULL DEFAULT now(),
    expires_at          timestamptz,
    settled_at          timestamptz,
    settlement_operation_id uuid REFERENCES economy.ledger_operations(id),
    version             bigint NOT NULL DEFAULT 0,
    FOREIGN KEY(seller_player_id, item_instance_id) REFERENCES inventory.item_instances(player_id, id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_market_active_item
    ON market.listings(item_instance_id) WHERE status='ACTIVE';
CREATE INDEX IF NOT EXISTS ix_market_browse
    ON market.listings(status, listed_rarity, listed_item_level, created_at DESC);

CREATE TABLE IF NOT EXISTS market.direct_trade_offers (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sender_player_id    uuid NOT NULL REFERENCES identity.players(id) ON DELETE CASCADE,
    recipient_player_id uuid NOT NULL REFERENCES identity.players(id) ON DELETE CASCADE,
    item_instance_id    uuid NOT NULL REFERENCES inventory.item_instances(id),
    requested_gold      numeric(30,0) NOT NULL DEFAULT 0 CHECK(requested_gold >= 0),
    status              market.trade_status NOT NULL DEFAULT 'PENDING',
    created_at          timestamptz NOT NULL DEFAULT now(),
    expires_at          timestamptz,
    resolved_at         timestamptz,
    version             bigint NOT NULL DEFAULT 0,
    FOREIGN KEY(sender_player_id, item_instance_id) REFERENCES inventory.item_instances(player_id, id),
    CHECK(sender_player_id <> recipient_player_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_direct_trade_pending_item
    ON market.direct_trade_offers(item_instance_id) WHERE status='PENDING';

CREATE TABLE IF NOT EXISTS market.item_transfers (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    transfer_type       market.transfer_type NOT NULL,
    source_ref_id       uuid,
    item_instance_id    uuid NOT NULL REFERENCES inventory.item_instances(id),
    from_player_id      uuid NOT NULL REFERENCES identity.players(id),
    to_player_id        uuid NOT NULL REFERENCES identity.players(id),
    recipient_floor_snapshot integer NOT NULL CHECK(recipient_floor_snapshot >= 1),
    recipient_natural_max_rarity inventory.item_rarity NOT NULL,
    recipient_allowed_max_rarity inventory.item_rarity NOT NULL,
    item_rarity         inventory.item_rarity NOT NULL,
    eligibility_passed  boolean NOT NULL,
    ownership_operation_id uuid REFERENCES economy.inventory_operations(id),
    idempotency_key     varchar(160) NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    settled_at          timestamptz,
    UNIQUE(to_player_id, idempotency_key),
    FOREIGN KEY(from_player_id, item_instance_id) REFERENCES inventory.item_instances(player_id, id),
    CHECK(from_player_id <> to_player_id)
);
COMMENT ON TABLE market.item_transfers IS
'Authoritative recipient gate: item rarity ordinal must be <= min(global max, NaturalMaxRarity(current Exploration Floor)+1). Re-check at settlement for Market and Direct Trade so one path cannot bypass the other.';

-- ============================================================
-- 12. CLAN BOSS
-- ============================================================
CREATE TABLE IF NOT EXISTS clan.clan_boss_defs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    boss_code           varchar(96) NOT NULL,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    enemy_code          varchar(96) NOT NULL,
    hp_total            numeric(30,6) NOT NULL,
    phase_rules         jsonb NOT NULL,
    attempt_rules       jsonb NOT NULL,
    rewards             jsonb NOT NULL,
    UNIQUE(boss_code, config_version_id)
);

CREATE TABLE IF NOT EXISTS clan.clan_bosses (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    clan_id             uuid NOT NULL REFERENCES clan.clans(id) ON DELETE CASCADE,
    boss_code           varchar(96) NOT NULL,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    status              varchar(32) NOT NULL DEFAULT 'SCHEDULED',
    opens_at            timestamptz NOT NULL,
    closes_at           timestamptz NOT NULL,
    max_hp              numeric(30,6) NOT NULL,
    current_hp          numeric(30,6) NOT NULL,
    current_phase       integer NOT NULL DEFAULT 1,
    phase_state         jsonb NOT NULL DEFAULT '{}'::jsonb,
    killed_at           timestamptz,
    version             bigint NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_clan_boss_open
    ON clan.clan_bosses(clan_id, opens_at, closes_at);

CREATE TABLE IF NOT EXISTS clan.clan_boss_attempts (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    clan_boss_id        uuid NOT NULL REFERENCES clan.clan_bosses(id) ON DELETE CASCADE,
    player_id           uuid NOT NULL REFERENCES identity.players(id),
    hero_id             uuid NOT NULL REFERENCES hero.player_heroes(id),
    attempt_no          integer NOT NULL,
    reserved_at         timestamptz NOT NULL DEFAULT now(),
    combat_id           uuid REFERENCES combat.combat_instances(id),
    phase_snapshot      jsonb NOT NULL,
    damage_committed    numeric(30,6) NOT NULL DEFAULT 0,
    result_json         jsonb,
    settled_at          timestamptz,
    UNIQUE(clan_boss_id, player_id, attempt_no)
);

-- ============================================================
-- 13. ARENA / CLAN SIEGE / SEASONS
-- ============================================================
CREATE TABLE IF NOT EXISTS competitive.seasons (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    season_code         varchar(64) NOT NULL UNIQUE,
    name_key            varchar(128) NOT NULL,
    status              competitive.season_status NOT NULL DEFAULT 'DRAFT',
    starts_at           timestamptz,
    conflict_at         timestamptz,
    settlement_at       timestamptz,
    closes_at           timestamptz,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    reset_rule          jsonb NOT NULL DEFAULT '{}'::jsonb,
    reward_rule         jsonb NOT NULL DEFAULT '{}'::jsonb,
    version             bigint NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS competitive.arena_profiles (
    player_id           uuid PRIMARY KEY REFERENCES identity.players(id) ON DELETE CASCADE,
    rating              integer NOT NULL DEFAULT 1000,
    mmr                 integer NOT NULL DEFAULT 1000,
    wins                integer NOT NULL DEFAULT 0,
    losses              integer NOT NULL DEFAULT 0,
    season_id           uuid REFERENCES competitive.seasons(id),
    defense_snapshot_id uuid,
    attempts_used       integer NOT NULL DEFAULT 0,
    attempts_reset_at   timestamptz,
    version             bigint NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS competitive.defense_snapshots (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id           uuid NOT NULL REFERENCES identity.players(id),
    hero_id             uuid NOT NULL REFERENCES hero.player_heroes(id),
    snapshot_json       jsonb NOT NULL,
    combat_power_estimate numeric(24,4),
    ai_policy_version   varchar(64),
    created_at          timestamptz NOT NULL DEFAULT now(),
    valid_until         timestamptz,
    hash                varchar(128) NOT NULL
);

ALTER TABLE competitive.arena_profiles
    DROP CONSTRAINT IF EXISTS fk_arena_def_snapshot;
ALTER TABLE competitive.arena_profiles
    ADD CONSTRAINT fk_arena_def_snapshot
    FOREIGN KEY(defense_snapshot_id) REFERENCES competitive.defense_snapshots(id);

CREATE TABLE IF NOT EXISTS competitive.arena_matches (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    season_id           uuid REFERENCES competitive.seasons(id),
    attacker_player_id  uuid NOT NULL REFERENCES identity.players(id),
    defender_player_id  uuid NOT NULL REFERENCES identity.players(id),
    defense_snapshot_id uuid NOT NULL REFERENCES competitive.defense_snapshots(id),
    combat_id           uuid REFERENCES combat.combat_instances(id),
    attacker_rating_before integer NOT NULL,
    defender_rating_before integer NOT NULL,
    attacker_rating_after integer,
    defender_rating_after integer,
    result              varchar(16),
    created_at          timestamptz NOT NULL DEFAULT now(),
    settled_at          timestamptz
);

CREATE TABLE IF NOT EXISTS competitive.clan_sieges (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    season_id           uuid REFERENCES competitive.seasons(id),
    clan_a_id           uuid NOT NULL REFERENCES clan.clans(id),
    clan_b_id           uuid NOT NULL REFERENCES clan.clans(id),
    status              varchar(32) NOT NULL DEFAULT 'MATCHED',
    roster_lock_at      timestamptz NOT NULL,
    opens_at            timestamptz NOT NULL,
    closes_at           timestamptz NOT NULL,
    clan_a_score        numeric(24,4) NOT NULL DEFAULT 0,
    clan_b_score        numeric(24,4) NOT NULL DEFAULT 0,
    rules_snapshot      jsonb NOT NULL,
    winner_clan_id      uuid REFERENCES clan.clans(id),
    version             bigint NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS competitive.siege_rosters (
    siege_id            uuid NOT NULL REFERENCES competitive.clan_sieges(id) ON DELETE CASCADE,
    clan_id             uuid NOT NULL REFERENCES clan.clans(id),
    player_id           uuid NOT NULL REFERENCES identity.players(id),
    defense_snapshot_id uuid NOT NULL REFERENCES competitive.defense_snapshots(id),
    node_key            varchar(64) NOT NULL,
    fortification_json  jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY(siege_id, clan_id, player_id)
);

CREATE TABLE IF NOT EXISTS competitive.siege_attacks (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    siege_id            uuid NOT NULL REFERENCES competitive.clan_sieges(id) ON DELETE CASCADE,
    attacker_player_id  uuid NOT NULL REFERENCES identity.players(id),
    defender_player_id  uuid NOT NULL REFERENCES identity.players(id),
    defense_snapshot_id uuid NOT NULL REFERENCES competitive.defense_snapshots(id),
    attack_token_no     integer NOT NULL,
    combat_id           uuid REFERENCES combat.combat_instances(id),
    result              varchar(16),
    score               numeric(24,4) NOT NULL DEFAULT 0,
    objective_json      jsonb NOT NULL DEFAULT '{}'::jsonb,
    settled_at          timestamptz,
    UNIQUE(siege_id, attacker_player_id, attack_token_no)
);

-- ============================================================
-- 14. EVENTS / LIVEOPS / LEADERBOARDS
-- ============================================================
CREATE TABLE IF NOT EXISTS liveops.event_defs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_code          varchar(96) NOT NULL,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    event_type          varchar(64) NOT NULL,
    eligibility_rule    jsonb NOT NULL DEFAULT '{}'::jsonb,
    objective_rule      jsonb NOT NULL DEFAULT '{}'::jsonb,
    caps_rule           jsonb NOT NULL DEFAULT '{}'::jsonb,
    reward_table        jsonb NOT NULL DEFAULT '{}'::jsonb,
    anti_abuse_rule     jsonb NOT NULL DEFAULT '{}'::jsonb,
    rollback_plan       jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(event_code, config_version_id)
);

CREATE TABLE IF NOT EXISTS liveops.events (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_code          varchar(96) NOT NULL,
    season_id           uuid REFERENCES competitive.seasons(id),
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    starts_at           timestamptz NOT NULL,
    ends_at             timestamptz NOT NULL,
    status              varchar(32) NOT NULL DEFAULT 'SCHEDULED',
    cohort_rule         jsonb NOT NULL DEFAULT '{}'::jsonb,
    runtime_config      jsonb NOT NULL DEFAULT '{}'::jsonb,
    version             bigint NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS liveops.player_event_progress (
    event_id            uuid NOT NULL REFERENCES liveops.events(id) ON DELETE CASCADE,
    player_id           uuid NOT NULL REFERENCES identity.players(id) ON DELETE CASCADE,
    score               numeric(30,6) NOT NULL DEFAULT 0,
    progress_json       jsonb NOT NULL DEFAULT '{}'::jsonb,
    reward_state        jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at          timestamptz NOT NULL DEFAULT now(),
    version             bigint NOT NULL DEFAULT 0,
    PRIMARY KEY(event_id, player_id)
);

CREATE TABLE IF NOT EXISTS liveops.leaderboards (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    leaderboard_code    varchar(96) NOT NULL,
    season_id           uuid REFERENCES competitive.seasons(id),
    event_id            uuid REFERENCES liveops.events(id),
    subject_type        varchar(32) NOT NULL,
    scoring_rule        jsonb NOT NULL,
    closes_at           timestamptz,
    status              varchar(32) NOT NULL DEFAULT 'ACTIVE',
    UNIQUE NULLS NOT DISTINCT (leaderboard_code, season_id, event_id)
);

CREATE TABLE IF NOT EXISTS liveops.leaderboard_entries (
    leaderboard_id      uuid NOT NULL REFERENCES liveops.leaderboards(id) ON DELETE CASCADE,
    subject_id          uuid NOT NULL,
    score               numeric(30,6) NOT NULL DEFAULT 0,
    rank_snapshot       integer,
    tiebreak_json       jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(leaderboard_id, subject_id)
);
CREATE INDEX IF NOT EXISTS ix_leaderboard_score
    ON liveops.leaderboard_entries(leaderboard_id, score DESC, subject_id);

CREATE TABLE IF NOT EXISTS liveops.merchant_rotations (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_code       varchar(64) NOT NULL,
    player_id           uuid REFERENCES identity.players(id),
    cohort_key          varchar(96),
    starts_at           timestamptz NOT NULL,
    ends_at             timestamptz NOT NULL,
    offers_json         jsonb NOT NULL,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id)
);

-- ============================================================
-- 15. COMMERCE
-- ============================================================
CREATE TABLE IF NOT EXISTS commerce.offer_defs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    offer_code          varchar(96) NOT NULL,
    config_version_id   bigint NOT NULL REFERENCES platform.config_versions(id),
    product_type        varchar(48) NOT NULL,
    eligibility_rule    jsonb NOT NULL DEFAULT '{}'::jsonb,
    reward_bundle       jsonb NOT NULL,
    purchase_limits     jsonb NOT NULL DEFAULT '{}'::jsonb,
    sku_map             jsonb NOT NULL DEFAULT '{}'::jsonb,
    status              platform.record_status NOT NULL DEFAULT 'ACTIVE',
    UNIQUE(offer_code, config_version_id),
    UNIQUE(id, offer_code)
);

CREATE TABLE IF NOT EXISTS commerce.offer_instances (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id           uuid NOT NULL REFERENCES identity.players(id) ON DELETE CASCADE,
    offer_def_id        uuid NOT NULL,
    offer_code          varchar(96) NOT NULL,
    price_sku           varchar(128) NOT NULL,
    starts_at           timestamptz NOT NULL DEFAULT now(),
    expires_at          timestamptz,
    eligibility_snapshot jsonb NOT NULL,
    purchase_count      integer NOT NULL DEFAULT 0,
    version             bigint NOT NULL DEFAULT 0,
    CHECK(purchase_count >= 0),
    FOREIGN KEY(offer_def_id, offer_code)
        REFERENCES commerce.offer_defs(id, offer_code)
);

CREATE TABLE IF NOT EXISTS commerce.payments (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id           uuid NOT NULL REFERENCES identity.players(id),
    platform            varchar(32) NOT NULL,
    provider_event_id   varchar(160),
    external_txn_id     varchar(160),
    offer_instance_id   uuid REFERENCES commerce.offer_instances(id),
    amount_minor        bigint NOT NULL CHECK(amount_minor > 0),
    currency            varchar(3) NOT NULL,
    status              commerce.payment_status NOT NULL DEFAULT 'RECEIVED',
    receipt_hash        varchar(128),
    entitlement_operation_id uuid,
    received_at         timestamptz NOT NULL DEFAULT now(),
    validated_at        timestamptz,
    settled_at          timestamptz,
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(platform, external_txn_id),
    UNIQUE(platform, provider_event_id)
);

CREATE TABLE IF NOT EXISTS commerce.entitlements (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id           uuid NOT NULL REFERENCES identity.players(id),
    entitlement_code    varchar(96) NOT NULL,
    source_payment_id   uuid REFERENCES commerce.payments(id),
    granted_at          timestamptz NOT NULL DEFAULT now(),
    expires_at          timestamptz,
    revoked_at          timestamptz,
    state_json          jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS commerce.refunds (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id          uuid NOT NULL REFERENCES commerce.payments(id),
    provider_refund_id  varchar(160),
    amount_minor        bigint NOT NULL CHECK(amount_minor > 0),
    reason_code         varchar(64),
    idempotency_key     varchar(160) NOT NULL,
    status              varchar(32) NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    resolved_at         timestamptz,
    UNIQUE(payment_id, idempotency_key),
    UNIQUE(payment_id, provider_refund_id)
);

-- ============================================================
-- 15B. MEDIA COMPANION — DURABLE SETTINGS ONLY
-- Playback session/queue is Redis-ephemeral by design. /music never grants gameplay rewards; Voice Cultivation is a separate hero.* gameplay flow.
-- ============================================================
CREATE TABLE IF NOT EXISTS media.guild_media_settings (
    guild_binding_id        uuid PRIMARY KEY REFERENCES identity.discord_guild_bindings(id) ON DELETE CASCADE,
    enabled                 boolean NOT NULL DEFAULT true,
    dj_role_id              bigint,
    default_volume          smallint NOT NULL DEFAULT 70 CHECK(default_volume BETWEEN 0 AND 100),
    max_queue_items         integer NOT NULL DEFAULT 100 CHECK(max_queue_items BETWEEN 1 AND 500),
    max_track_seconds       integer NOT NULL DEFAULT 14400 CHECK(max_track_seconds BETWEEN 30 AND 86400),
    idle_disconnect_seconds integer NOT NULL DEFAULT 180 CHECK(idle_disconnect_seconds BETWEEN 30 AND 3600),
    youtube_enabled         boolean NOT NULL DEFAULT true,
    youtube_search_limit    smallint NOT NULL DEFAULT 10 CHECK(youtube_search_limit BETWEEN 1 AND 25),
    search_timeout_seconds  smallint NOT NULL DEFAULT 60 CHECK(search_timeout_seconds BETWEEN 15 AND 300),
    source_policy           jsonb NOT NULL DEFAULT '{"youtubeMode":"AUDIO_SEARCH_OR_DIRECT_URL","searchResultLimit":10,"playIfIdleElseEnqueue":true}'::jsonb,
    updated_at              timestamptz NOT NULL DEFAULT now(),
    version                 bigint NOT NULL DEFAULT 0
);

COMMENT ON TABLE media.guild_media_settings IS
'Durable guild policy for optional YouTube Music Companion. /music text queries return up to youtube_search_limit selectable YouTube results; valid YouTube video URLs resolve directly. Playback/search session state remains Redis-ephemeral and is not authoritative gameplay state. Eligible voice presence may grant cultivation Qi through hero.voice_cultivation_sessions, independent of /music playback.';

-- ============================================================
-- 16. OPS / AUDIT / ADMIN / MODERATION
-- ============================================================
CREATE TABLE IF NOT EXISTS ops.audit_logs (
    id                  bigint GENERATED ALWAYS AS IDENTITY,
    actor_type          varchar(32) NOT NULL,
    actor_id            varchar(128),
    action              varchar(96) NOT NULL,
    object_type         varchar(64) NOT NULL,
    object_id           varchar(128),
    reason_code         varchar(96),
    before_json         jsonb,
    after_json          jsonb,
    request_id          varchar(128),
    created_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(id, created_at)
) PARTITION BY RANGE(created_at);

CREATE TABLE IF NOT EXISTS ops.audit_logs_default
    PARTITION OF ops.audit_logs DEFAULT;
CREATE INDEX IF NOT EXISTS ix_audit_object
    ON ops.audit_logs(object_type, object_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ops.compensation_cases (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id           uuid NOT NULL REFERENCES identity.players(id),
    reason_code         varchar(96) NOT NULL,
    evidence_json       jsonb NOT NULL DEFAULT '{}'::jsonb,
    reward_bundle       jsonb NOT NULL,
    requested_by        varchar(128) NOT NULL,
    approved_by         varchar(128),
    status              varchar(32) NOT NULL DEFAULT 'PENDING',
    operation_id        uuid REFERENCES economy.ledger_operations(id),
    created_at          timestamptz NOT NULL DEFAULT now(),
    resolved_at         timestamptz
);

CREATE TABLE IF NOT EXISTS ops.player_sanctions (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id           uuid NOT NULL REFERENCES identity.players(id),
    sanction_type       varchar(48) NOT NULL,
    reason_code         varchar(96) NOT NULL,
    evidence_json       jsonb NOT NULL DEFAULT '{}'::jsonb,
    starts_at           timestamptz NOT NULL DEFAULT now(),
    ends_at             timestamptz,
    revoked_at          timestamptz,
    created_by          varchar(128) NOT NULL
);

CREATE TABLE IF NOT EXISTS ops.abuse_signals (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id           uuid REFERENCES identity.players(id),
    signal_type         varchar(64) NOT NULL,
    severity            integer NOT NULL CHECK(severity BETWEEN 1 AND 5),
    signal_json         jsonb NOT NULL,
    detected_at         timestamptz NOT NULL DEFAULT now(),
    reviewed_at         timestamptz,
    disposition         varchar(64)
);

-- ============================================================
-- 16B. DEFERRED CROSS-MODULE FOREIGN KEYS
-- Declared here because module creation order places economy/kingdom/combat later.
-- ============================================================
ALTER TABLE hero.breakthrough_attempts DROP CONSTRAINT IF EXISTS fk_breakthrough_combat;
ALTER TABLE hero.breakthrough_attempts
    ADD CONSTRAINT fk_breakthrough_combat
    FOREIGN KEY(combat_instance_id) REFERENCES combat.combat_instances(id)
    DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE hero.breakthrough_attempts DROP CONSTRAINT IF EXISTS fk_breakthrough_consume_operation;
ALTER TABLE hero.breakthrough_attempts
    ADD CONSTRAINT fk_breakthrough_consume_operation
    FOREIGN KEY(consume_operation_id) REFERENCES economy.inventory_operations(id)
    DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE hero.voice_cultivation_sessions DROP CONSTRAINT IF EXISTS fk_voice_cultivation_grant_operation;
ALTER TABLE hero.voice_cultivation_sessions
    ADD CONSTRAINT fk_voice_cultivation_grant_operation
    FOREIGN KEY(grant_operation_id) REFERENCES economy.ledger_operations(id)
    DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE combat.combat_settlements DROP CONSTRAINT IF EXISTS fk_combat_settlement_reward_operation;
ALTER TABLE combat.combat_settlements
    ADD CONSTRAINT fk_combat_settlement_reward_operation
    FOREIGN KEY(reward_operation_id) REFERENCES economy.ledger_operations(id)
    DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE inventory.craft_jobs
    DROP CONSTRAINT IF EXISTS fk_craft_input_operation,
    DROP CONSTRAINT IF EXISTS fk_craft_output_operation,
    DROP CONSTRAINT IF EXISTS fk_craft_building;
ALTER TABLE inventory.craft_jobs
    ADD CONSTRAINT fk_craft_input_operation
    FOREIGN KEY(input_operation_id) REFERENCES economy.ledger_operations(id)
    DEFERRABLE INITIALLY DEFERRED,
    ADD CONSTRAINT fk_craft_output_operation
    FOREIGN KEY(output_operation_id) REFERENCES economy.ledger_operations(id)
    DEFERRABLE INITIALLY DEFERRED,
    ADD CONSTRAINT fk_craft_building
    FOREIGN KEY(building_id) REFERENCES kingdom.kingdom_buildings(id)
    DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE kingdom.construction_jobs
    DROP CONSTRAINT IF EXISTS fk_construction_cost_operation,
    DROP CONSTRAINT IF EXISTS fk_construction_apply_operation;
ALTER TABLE kingdom.construction_jobs
    ADD CONSTRAINT fk_construction_cost_operation
    FOREIGN KEY(cost_operation_id) REFERENCES economy.ledger_operations(id)
    DEFERRABLE INITIALLY DEFERRED,
    ADD CONSTRAINT fk_construction_apply_operation
    FOREIGN KEY(apply_operation_id) REFERENCES economy.ledger_operations(id)
    DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE kingdom.research_jobs DROP CONSTRAINT IF EXISTS fk_research_cost_operation;
ALTER TABLE kingdom.research_jobs
    ADD CONSTRAINT fk_research_cost_operation
    FOREIGN KEY(cost_operation_id) REFERENCES economy.ledger_operations(id)
    DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE commerce.payments DROP CONSTRAINT IF EXISTS fk_payment_entitlement_operation;
ALTER TABLE commerce.payments
    ADD CONSTRAINT fk_payment_entitlement_operation
    FOREIGN KEY(entitlement_operation_id) REFERENCES economy.ledger_operations(id)
    DEFERRABLE INITIALLY DEFERRED;

-- ============================================================
-- 17. PERFORMANCE / SAFETY INDEXES
-- ============================================================
CREATE INDEX IF NOT EXISTS ix_player_name ON identity.players(display_name);
CREATE INDEX IF NOT EXISTS ix_hero_realm ON hero.player_heroes(realm_code, realm_minor_stage);
CREATE INDEX IF NOT EXISTS ix_runs_player_time ON adventure.adventure_runs(player_id, started_at DESC);
CREATE INDEX IF NOT EXISTS ix_construction_due ON kingdom.construction_jobs(completes_at) WHERE status='RUNNING';
CREATE INDEX IF NOT EXISTS ix_research_due ON kingdom.research_jobs(completes_at) WHERE status='RUNNING';
CREATE INDEX IF NOT EXISTS ix_boss_attempts_player ON clan.clan_boss_attempts(player_id, reserved_at DESC);
CREATE INDEX IF NOT EXISTS ix_arena_matches_attacker ON competitive.arena_matches(attacker_player_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_arena_matches_defender ON competitive.arena_matches(defender_player_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_events_window ON liveops.events(starts_at, ends_at, status);
CREATE INDEX IF NOT EXISTS ix_payment_player_time ON commerce.payments(player_id, received_at DESC);
CREATE INDEX IF NOT EXISTS ix_discord_links_account ON identity.discord_links(account_id);
CREATE INDEX IF NOT EXISTS ix_craft_jobs_player_status ON inventory.craft_jobs(player_id, status, completes_at);
CREATE INDEX IF NOT EXISTS ix_combat_events_time ON combat.combat_events(created_at DESC);
CREATE INDEX IF NOT EXISTS ix_reward_grants_player_status ON economy.reward_grants(player_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_leaderboard_entries_score ON liveops.leaderboard_entries(leaderboard_id, score DESC);

-- ============================================================
-- 18. INITIAL CONTENT SEED (MINIMAL, NON-BALANCE LOCK)
-- ============================================================
INSERT INTO platform.config_versions(version_code, description, status)
VALUES ('GDD-3.3-INITIAL', 'Initial content/config anchor for GDD v3.3 / Combat Engine v2.2', 'ACTIVE')
ON CONFLICT (version_code) DO NOTHING;

INSERT INTO economy.asset_defs(code, asset_type, integrity_tier, precision_scale, transferable)
VALUES
('WOOD','BASE_RESOURCE','B',0,false),
('ORE','BASE_RESOURCE','B',0,false),
('FOOD','BASE_RESOURCE','B',0,false),
('GOLD','BASE_RESOURCE','B',0,false),
('ESSENCE','CRAFT_MATERIAL','B',0,false),
('INSIGHT','CULTIVATION','B',0,false),
('GEMS','PREMIUM','A',0,false),
('CLAN_MARKS','CLAN','B',0,false),
('SEASON_TOKEN','SEASON','B',0,false)
ON CONFLICT (code) DO NOTHING;

-- ============================================================
-- 19. COMMENTS / CRITICAL INVARIANTS
-- ============================================================
COMMENT ON TABLE economy.ledger_operations IS
'One business operation identity. Retry must reuse idempotency key and never double-grant assets; NULL actor IDs are NOT DISTINCT for uniqueness.';
COMMENT ON TABLE combat.combat_events IS
'Tier C deterministic combat events. (combat_id, sequence_no) is globally unique for exact replay. Final settlement/rewards persist as Tier B/A operations.';
COMMENT ON TABLE competitive.defense_snapshots IS
'Immutable-ish snapshot used by async PvP so Discord latency/current defender edits do not alter an ongoing attack.';
COMMENT ON TABLE platform.outbox_events IS
'Transactional outbox. Insert in same PostgreSQL transaction as durable domain change; publisher delivers to RabbitMQ.';
COMMENT ON TABLE platform.scheduled_actions IS
'Durable timer source for construction/research/craft/event jobs. Redis may accelerate due lookup but is not source of truth.';
COMMENT ON TABLE adventure.energy_balances IS
'Authoritative Energy state including cap/regen timing. ENERGY is intentionally not duplicated in economy.asset_defs.';
COMMENT ON TABLE hero.hero_affinities IS
'Authoritative 1–2 Affinity slots per hero. Do not duplicate primary/secondary affinity columns on player_heroes.';
COMMENT ON TABLE economy.ledger_accounts IS
'Authoritative balance store for ledger-owned assets such as ESSENCE and INSIGHT; do not duplicate these balances on hero rows.';
COMMENT ON TABLE inventory.item_defs IS
'Equipment catalog defaults to PATH_OF_KINGS ownership; exact imported source values remain versioned/provenanced.';
COMMENT ON TABLE content.building_defs IS
'Kingdom buildings default to RISE_OF_KINGDOMS ownership while Discord execution remains non-spatial unless later changed.';


-- ============================================================
-- 18. V4.0 NORMATIVE GAMEPLAY INVARIANTS (DB-SUPPORTED)
-- ============================================================
COMMENT ON TABLE march.player_march_slots IS
'At most five slot numbers per player. Application eligibility derives from City Hall thresholds: Lv8=3, Lv17=4, Lv23=5; pre-Lv8 baseline is versioned config.';
COMMENT ON TABLE march.hunt_rounds IS
'Each hunt round settles one Combat Engine result then reward. v4.0 reward profile guarantees >=1 equipment item per monster kill; retries must reuse persisted reward/RNG identity.';
COMMENT ON TABLE content.exploration_floor_profiles IS
'Floor milestones 25/50/100/150 must raise high-rarity access/probability through config. The recipient market gate uses max_natural_rarity from the current eligible floor profile.';
COMMENT ON TABLE hero.breakthrough_attempts IS
'v4.0 Tribulation: Stage10 only; higher Realms have lower configured base chance. Consecutive failure pity adds +5 percentage points per fail; booster adds +10pp for one attempt; protected failure keeps Stage10 and loses 50% XP, default failure loses all XP and drops to Stage9. Success resets fail streak.';

COMMIT;
