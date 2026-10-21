-- LOST KINGSLAND ADMIN V6.1 MEGAOPS — ALL-IN-ONE V27 INSTALLER
-- Target database: lost_kingsland_v4_reconciled
-- Run this ONE FILE in DBeaver as DB owner (lost_kingsland).
-- Additive/rerunnable. Does not modify gameplay Flyway history.
-- Includes: admin roles + shared content media + giftcode/player-control permissions.


-- ======================================================================
-- BEGIN 20_admin_roles.sql
-- ======================================================================
-- Lost Kingsland Admin V27 — least-privilege roles
-- Run while connected as owner to: lost_kingsland_v4_reconciled
-- Additive/rerunnable. No gameplay data mutation.

DO $$ BEGIN
  CREATE ROLE lk_admin_readonly NOLOGIN;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE ROLE lk_admin_config_editor NOLOGIN;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$
DECLARE
  s text;
  t text;
  read_schemas text[] := ARRAY[
    'admin','platform','identity','content','hero','adventure','combat','inventory',
    'kingdom','clan','competitive','liveops','economy','commerce','ops','commander',
    'media','march','market','gacha'
  ];
  editable_tables text[] := ARRAY[
    'inventory.item_defs','inventory.equipment_set_defs','inventory.equipment_set_bonuses',
    'inventory.equipment_stat_defs','inventory.equipment_affix_combinations','inventory.rarity_policy',
    'inventory.recipes','inventory.equipment_forge_recipes',
    'content.race_defs','content.path_defs','content.affinity_defs','content.bloodline_defs',
    'content.realm_defs','content.sect_defs','content.profession_defs','content.technique_defs',
    'content.tags','content.region_defs','content.node_defs','content.enemy_defs',
    'content.exploration_floor_profiles','content.monster_reward_profiles','content.building_defs',
    'content.research_defs','content.march_slot_unlock_rules','content.combat_profiles',
    'content.path_starting_techniques','content.technique_tag_links','content.section_rules',
    'content.adventure_encounter_profiles','content.technique_slot_rules',
    'hero.talent_nodes','hero.character_defs','hero.cultivation_stage_defs','hero.party_combat_rules',
    'commander.commander_defs','clan.clan_tech_defs','clan.clan_quest_defs','clan.clan_boss_defs',
    'clan.playtest_rules','economy.asset_defs','commerce.offer_defs','liveops.event_defs',
    'liveops.leaderboards','liveops.merchant_rotations','platform.feature_flags','competitive.seasons',
    'competitive.arena_rules','media.guild_media_settings','adventure.faction_boss_catalog',
    'adventure.faction_boss_reward_rules','gacha.wheel_rules','market.playtest_rules'
  ];
BEGIN
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO lk_admin_readonly', current_database());
  EXECUTE 'GRANT lk_admin_readonly TO lk_admin_config_editor';

  FOREACH s IN ARRAY read_schemas LOOP
    IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname=s) THEN
      EXECUTE format('GRANT USAGE ON SCHEMA %I TO lk_admin_readonly', s);
      EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA %I TO lk_admin_readonly', s);
    END IF;
  END LOOP;

  FOREACH t IN ARRAY editable_tables LOOP
    IF to_regclass(t) IS NOT NULL THEN
      EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE %s TO lk_admin_config_editor', t);
    END IF;
  END LOOP;

  FOREACH s IN ARRAY ARRAY['inventory','content','hero','commander','clan','economy','commerce','liveops','platform','ops','adventure','competitive','gacha','market'] LOOP
    IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname=s) THEN
      EXECUTE format('GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA %I TO lk_admin_config_editor', s);
    END IF;
  END LOOP;

  IF to_regclass('ops.audit_logs') IS NOT NULL THEN
    EXECUTE 'GRANT INSERT ON ops.audit_logs TO lk_admin_config_editor';
  END IF;
  IF to_regclass('ops.compensation_cases') IS NOT NULL THEN
    EXECUTE 'GRANT SELECT,INSERT,UPDATE ON ops.compensation_cases TO lk_admin_config_editor';
  END IF;
  IF to_regclass('ops.player_sanctions') IS NOT NULL THEN
    EXECUTE 'GRANT SELECT,INSERT,UPDATE ON ops.player_sanctions TO lk_admin_config_editor';
  END IF;
END $$;

-- Create the actual login separately, then grant the editor role:
-- CREATE ROLE lost_kingsland_admin LOGIN PASSWORD 'CHANGE_ME';
-- GRANT lk_admin_config_editor TO lost_kingsland_admin;

-- END 20_admin_roles.sql

-- ======================================================================
-- BEGIN 40_v27_shared_content_media_and_permissions.sql
-- ======================================================================
-- Lost Kingsland Admin V27 Studio
-- Run against: lost_kingsland_v4_reconciled
-- Additive only. Does not modify gameplay state or Flyway history.

BEGIN;

CREATE TABLE IF NOT EXISTS platform.media_assets (
    asset_key           varchar(256) PRIMARY KEY,
    category            varchar(64) NOT NULL DEFAULT 'CONTENT_IMAGE',
    content_type        varchar(128) NOT NULL,
    content_bytes       bytea NOT NULL,
    sha256              char(64) NOT NULL,
    size_bytes          bigint NOT NULL CHECK(size_bytes >= 0),
    width               integer CHECK(width IS NULL OR width > 0),
    height              integer CHECK(height IS NULL OR height > 0),
    original_filename   varchar(255),
    created_by          varchar(160),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    active              boolean NOT NULL DEFAULT true,
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS ix_media_assets_category_updated ON platform.media_assets(category, updated_at DESC);
CREATE INDEX IF NOT EXISTS ix_media_assets_sha256 ON platform.media_assets(sha256);

CREATE TABLE IF NOT EXISTS platform.entity_media_links (
    entity_type     varchar(64)  NOT NULL,
    entity_id       varchar(160) NOT NULL,
    asset_key       varchar(256) NOT NULL REFERENCES platform.media_assets(asset_key) ON DELETE CASCADE,
    media_role      varchar(32)  NOT NULL DEFAULT 'GALLERY',
    sort_order      integer      NOT NULL DEFAULT 0 CHECK(sort_order >= 0),
    is_primary      boolean      NOT NULL DEFAULT false,
    created_by      varchar(160),
    created_at      timestamptz  NOT NULL DEFAULT now(),
    metadata        jsonb        NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY(entity_type, entity_id, asset_key)
);
CREATE INDEX IF NOT EXISTS ix_entity_media_links_entity ON platform.entity_media_links(entity_type, entity_id, sort_order);
CREATE INDEX IF NOT EXISTS ix_entity_media_links_asset ON platform.entity_media_links(asset_key);
CREATE UNIQUE INDEX IF NOT EXISTS ux_entity_media_one_primary ON platform.entity_media_links(entity_type, entity_id) WHERE is_primary=true;

-- Keep existing direct image fields compatible with the generic media system.
INSERT INTO platform.entity_media_links(entity_type, entity_id, asset_key, media_role, sort_order, is_primary, created_by)
SELECT 'ITEM_DEF', i.id::text, i.image_asset_key, 'PRIMARY', 0, true, 'v27-backfill'
FROM inventory.item_defs i JOIN platform.media_assets m ON m.asset_key=i.image_asset_key
WHERE i.image_asset_key IS NOT NULL
ON CONFLICT(entity_type, entity_id, asset_key) DO UPDATE SET media_role='PRIMARY', sort_order=0, is_primary=true;

INSERT INTO platform.entity_media_links(entity_type, entity_id, asset_key, media_role, sort_order, is_primary, created_by)
SELECT 'CHARACTER_DEF', c.code, c.image_asset_key, 'PRIMARY', 0, true, 'v27-backfill'
FROM hero.character_defs c JOIN platform.media_assets m ON m.asset_key=c.image_asset_key
WHERE c.image_asset_key IS NOT NULL
ON CONFLICT(entity_type, entity_id, asset_key) DO UPDATE SET media_role='PRIMARY', sort_order=0, is_primary=true;

CREATE SCHEMA IF NOT EXISTS admin;
CREATE OR REPLACE VIEW admin.v_content_media AS
SELECT 'ITEM_DEF'::varchar AS entity_type, i.id::text AS entity_id, i.code, i.display_name_vi AS display_name,
       COALESCE(i.image_asset_key, l.asset_key) AS primary_asset_key
FROM inventory.item_defs i
LEFT JOIN LATERAL (
  SELECT asset_key FROM platform.entity_media_links x
  WHERE x.entity_type='ITEM_DEF' AND x.entity_id=i.id::text AND x.is_primary=true LIMIT 1
) l ON true
UNION ALL
SELECT 'CHARACTER_DEF', c.code, c.code, c.display_name_vi, COALESCE(c.image_asset_key, l.asset_key)
FROM hero.character_defs c
LEFT JOIN LATERAL (
  SELECT asset_key FROM platform.entity_media_links x
  WHERE x.entity_type='CHARACTER_DEF' AND x.entity_id=c.code AND x.is_primary=true LIMIT 1
) l ON true
UNION ALL
SELECT 'FACTION_BOSS', b.boss_code, b.boss_code, b.display_name_vi, l.asset_key
FROM adventure.faction_boss_catalog b
LEFT JOIN LATERAL (
  SELECT asset_key FROM platform.entity_media_links x
  WHERE x.entity_type='FACTION_BOSS' AND x.entity_id=b.boss_code AND x.is_primary=true LIMIT 1
) l ON true
UNION ALL
SELECT 'ENEMY_DEF', e.id::text, e.code, e.name_key, l.asset_key
FROM content.enemy_defs e
LEFT JOIN LATERAL (
  SELECT asset_key FROM platform.entity_media_links x
  WHERE x.entity_type='ENEMY_DEF' AND x.entity_id=e.id::text AND x.is_primary=true LIMIT 1
) l ON true
UNION ALL
SELECT 'COMMANDER_DEF', c.id::text, c.code, c.name_key, l.asset_key
FROM commander.commander_defs c
LEFT JOIN LATERAL (
  SELECT asset_key FROM platform.entity_media_links x
  WHERE x.entity_type='COMMANDER_DEF' AND x.entity_id=c.id::text AND x.is_primary=true LIMIT 1
) l ON true
UNION ALL
SELECT 'EQUIPMENT_SET', s.set_code, s.set_code, s.set_name, l.asset_key
FROM inventory.equipment_set_defs s
LEFT JOIN LATERAL (
  SELECT asset_key FROM platform.entity_media_links x
  WHERE x.entity_type='EQUIPMENT_SET' AND x.entity_id=s.set_code AND x.is_primary=true LIMIT 1
) l ON true
UNION ALL
SELECT 'TECHNIQUE_DEF', t.id::text, t.code, t.name_key, l.asset_key
FROM content.technique_defs t
LEFT JOIN LATERAL (
  SELECT asset_key FROM platform.entity_media_links x
  WHERE x.entity_type='TECHNIQUE_DEF' AND x.entity_id=t.id::text AND x.is_primary=true LIMIT 1
) l ON true
UNION ALL
SELECT 'BUILDING_DEF', b.id::text, b.code, b.name_key, l.asset_key
FROM content.building_defs b
LEFT JOIN LATERAL (
  SELECT asset_key FROM platform.entity_media_links x
  WHERE x.entity_type='BUILDING_DEF' AND x.entity_id=b.id::text AND x.is_primary=true LIMIT 1
) l ON true
UNION ALL
SELECT 'RESEARCH_DEF', r.id::text, r.code, r.code, l.asset_key
FROM content.research_defs r
LEFT JOIN LATERAL (
  SELECT asset_key FROM platform.entity_media_links x
  WHERE x.entity_type='RESEARCH_DEF' AND x.entity_id=r.id::text AND x.is_primary=true LIMIT 1
) l ON true
UNION ALL
SELECT 'RACE_DEF', r.id::text, r.code, r.name_key, l.asset_key
FROM content.race_defs r
LEFT JOIN LATERAL (
  SELECT asset_key FROM platform.entity_media_links x
  WHERE x.entity_type='RACE_DEF' AND x.entity_id=r.id::text AND x.is_primary=true LIMIT 1
) l ON true
UNION ALL
SELECT 'PATH_DEF', p.id::text, p.code, p.name_key, l.asset_key
FROM content.path_defs p
LEFT JOIN LATERAL (
  SELECT asset_key FROM platform.entity_media_links x
  WHERE x.entity_type='PATH_DEF' AND x.entity_id=p.id::text AND x.is_primary=true LIMIT 1
) l ON true
UNION ALL
SELECT 'AFFINITY_DEF', a.id::text, a.code, a.name_key, l.asset_key
FROM content.affinity_defs a
LEFT JOIN LATERAL (
  SELECT asset_key FROM platform.entity_media_links x
  WHERE x.entity_type='AFFINITY_DEF' AND x.entity_id=a.id::text AND x.is_primary=true LIMIT 1
) l ON true
UNION ALL
SELECT 'SECT_DEF', s.id::text, s.code, s.name_key, l.asset_key
FROM content.sect_defs s
LEFT JOIN LATERAL (
  SELECT asset_key FROM platform.entity_media_links x
  WHERE x.entity_type='SECT_DEF' AND x.entity_id=s.id::text AND x.is_primary=true LIMIT 1
) l ON true
UNION ALL
SELECT 'REGION_DEF', r.id::text, r.code, r.name_key, l.asset_key
FROM content.region_defs r
LEFT JOIN LATERAL (
  SELECT asset_key FROM platform.entity_media_links x
  WHERE x.entity_type='REGION_DEF' AND x.entity_id=r.id::text AND x.is_primary=true LIMIT 1
) l ON true
UNION ALL
SELECT 'CLAN_BOSS_DEF', c.id::text, c.boss_code, c.boss_code, l.asset_key
FROM clan.clan_boss_defs c
LEFT JOIN LATERAL (
  SELECT asset_key FROM platform.entity_media_links x
  WHERE x.entity_type='CLAN_BOSS_DEF' AND x.entity_id=c.id::text AND x.is_primary=true LIMIT 1
) l ON true
UNION ALL
SELECT 'CLAN_TECH_DEF', c.id::text, c.tech_code, c.tech_code, l.asset_key
FROM clan.clan_tech_defs c
LEFT JOIN LATERAL (
  SELECT asset_key FROM platform.entity_media_links x
  WHERE x.entity_type='CLAN_TECH_DEF' AND x.entity_id=c.id::text AND x.is_primary=true LIMIT 1
) l ON true;

-- Grants are conditional so the patch remains rerunnable before/after role setup.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='lk_admin_readonly') THEN
    EXECUTE 'GRANT SELECT ON platform.media_assets, platform.entity_media_links, admin.v_content_media TO lk_admin_readonly';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='lk_admin_config_editor') THEN
    EXECUTE 'GRANT SELECT,INSERT,UPDATE,DELETE ON platform.media_assets, platform.entity_media_links TO lk_admin_config_editor';
    EXECUTE 'GRANT SELECT,INSERT,UPDATE,DELETE ON hero.character_defs, adventure.faction_boss_catalog, adventure.faction_boss_reward_rules, content.section_rules, content.adventure_encounter_profiles, content.technique_slot_rules, hero.cultivation_stage_defs, hero.party_combat_rules, inventory.equipment_forge_recipes, gacha.wheel_rules, competitive.arena_rules, market.playtest_rules, clan.playtest_rules TO lk_admin_config_editor';
    EXECUTE 'GRANT SELECT ON admin.v_content_media TO lk_admin_config_editor';
  END IF;
END $$;

COMMIT;

-- END 40_v27_shared_content_media_and_permissions.sql

-- ======================================================================
-- BEGIN 50_giftcode_player_control.sql
-- ======================================================================
-- Lost Kingsland Admin V6 — Gift Code + Player Control Center
-- Target DB: lost_kingsland_v4_reconciled
-- Additive / rerunnable. Does not modify Flyway history.
-- Run AFTER sql/20_admin_roles.sql and sql/40_v27_shared_content_media_and_permissions.sql.

BEGIN;

CREATE SCHEMA IF NOT EXISTS liveops;
CREATE SCHEMA IF NOT EXISTS admin;

CREATE TABLE IF NOT EXISTS liveops.gift_codes (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code                varchar(64) NOT NULL,
    display_name        varchar(160) NOT NULL,
    description         text,
    status              varchar(24) NOT NULL DEFAULT 'DRAFT',
    starts_at           timestamptz,
    ends_at             timestamptz,
    max_redemptions     integer,
    per_player_limit    integer NOT NULL DEFAULT 1,
    redemption_count    integer NOT NULL DEFAULT 0,
    reward_bundle       jsonb NOT NULL DEFAULT '{}'::jsonb,
    eligibility_json    jsonb NOT NULL DEFAULT '{}'::jsonb,
    tags                text[] NOT NULL DEFAULT '{}'::text[],
    config_version_id   bigint,
    created_by          varchar(160),
    updated_by          varchar(160),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    version             bigint NOT NULL DEFAULT 0,
    CONSTRAINT gift_codes_code_upper CHECK (code = upper(code)),
    CONSTRAINT gift_codes_status_check CHECK (status IN ('DRAFT','ACTIVE','PAUSED','EXPIRED','ARCHIVED')),
    CONSTRAINT gift_codes_max_redemptions_check CHECK (max_redemptions IS NULL OR max_redemptions > 0),
    CONSTRAINT gift_codes_per_player_limit_check CHECK (per_player_limit > 0),
    CONSTRAINT gift_codes_redemption_count_check CHECK (redemption_count >= 0),
    CONSTRAINT gift_codes_window_check CHECK (ends_at IS NULL OR starts_at IS NULL OR ends_at > starts_at)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_gift_codes_upper_code ON liveops.gift_codes(upper(code));
CREATE INDEX IF NOT EXISTS ix_gift_codes_status_window ON liveops.gift_codes(status, starts_at, ends_at);
CREATE INDEX IF NOT EXISTS ix_gift_codes_updated ON liveops.gift_codes(updated_at DESC);

CREATE TABLE IF NOT EXISTS liveops.gift_code_redemptions (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    gift_code_id        uuid NOT NULL REFERENCES liveops.gift_codes(id) ON DELETE RESTRICT,
    player_id           uuid NOT NULL REFERENCES identity.players(id) ON DELETE RESTRICT,
    request_id          varchar(160) NOT NULL,
    status              varchar(24) NOT NULL DEFAULT 'PENDING_GRANT',
    reward_snapshot     jsonb NOT NULL DEFAULT '{}'::jsonb,
    eligibility_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    redeemed_at         timestamptz NOT NULL DEFAULT now(),
    granted_at          timestamptz,
    failed_at           timestamptz,
    error_code          varchar(96),
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT gift_code_redemptions_status_check CHECK (status IN ('PENDING_GRANT','GRANTED','FAILED','REVOKED')),
    CONSTRAINT gift_code_redemptions_request_unique UNIQUE(request_id)
);
CREATE INDEX IF NOT EXISTS ix_gift_code_redemptions_code_player ON liveops.gift_code_redemptions(gift_code_id, player_id, redeemed_at DESC);
CREATE INDEX IF NOT EXISTS ix_gift_code_redemptions_player ON liveops.gift_code_redemptions(player_id, redeemed_at DESC);
CREATE INDEX IF NOT EXISTS ix_gift_code_redemptions_status ON liveops.gift_code_redemptions(status, redeemed_at DESC);

COMMENT ON TABLE liveops.gift_codes IS 'Admin-managed gift-code definitions. Reward bundle is a snapshot contract for gameplay/bot redemption; Admin does not directly grant rewards from this table.';
COMMENT ON TABLE liveops.gift_code_redemptions IS 'Atomic redemption reservation/history. Bot/gameplay should grant reward using authoritative reward/ledger services then mark GRANTED.';

CREATE OR REPLACE VIEW admin.v_gift_codes AS
SELECT g.*,
       CASE
         WHEN g.status='ARCHIVED' THEN 'ARCHIVED'
         WHEN g.status='PAUSED' THEN 'PAUSED'
         WHEN g.ends_at IS NOT NULL AND g.ends_at <= now() THEN 'EXPIRED'
         WHEN g.starts_at IS NOT NULL AND g.starts_at > now() THEN 'SCHEDULED'
         WHEN g.status='ACTIVE' THEN 'ACTIVE'
         ELSE g.status
       END AS effective_status,
       CASE WHEN g.max_redemptions IS NULL THEN NULL ELSE GREATEST(g.max_redemptions-g.redemption_count,0) END AS remaining_redemptions
FROM liveops.gift_codes g;

CREATE OR REPLACE VIEW admin.v_gift_code_redemptions AS
SELECT r.*, g.code, g.display_name, p.display_name AS player_name
FROM liveops.gift_code_redemptions r
JOIN liveops.gift_codes g ON g.id=r.gift_code_id
JOIN identity.players p ON p.id=r.player_id;

-- Admin V6 purpose-built Player Control Center permissions.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='lk_admin_readonly') THEN
    EXECUTE 'GRANT SELECT ON liveops.gift_codes, liveops.gift_code_redemptions, admin.v_gift_codes, admin.v_gift_code_redemptions TO lk_admin_readonly';
    EXECUTE 'GRANT SELECT ON identity.accounts, identity.players, identity.discord_links, hero.player_heroes, hero.player_characters, adventure.energy_balances, adventure.player_exploration_progress, commander.player_commanders, inventory.item_instances, kingdom.player_kingdoms, kingdom.kingdom_buildings, kingdom.player_research, kingdom.production_sites, economy.asset_defs, economy.ledger_accounts, economy.ledger_entries, economy.ledger_operations TO lk_admin_readonly';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='lk_admin_config_editor') THEN
    EXECUTE 'GRANT SELECT,INSERT,UPDATE,DELETE ON liveops.gift_codes TO lk_admin_config_editor';
    EXECUTE 'GRANT SELECT,INSERT,UPDATE ON liveops.gift_code_redemptions TO lk_admin_config_editor';
    EXECUTE 'GRANT SELECT ON admin.v_gift_codes, admin.v_gift_code_redemptions TO lk_admin_config_editor';
    EXECUTE 'GRANT SELECT,UPDATE ON identity.accounts, identity.players, hero.player_heroes, hero.player_characters, adventure.energy_balances, adventure.player_exploration_progress, commander.player_commanders, inventory.item_instances, kingdom.kingdom_buildings, kingdom.player_research, kingdom.production_sites TO lk_admin_config_editor';
    EXECUTE 'GRANT SELECT ON economy.asset_defs TO lk_admin_config_editor';
    EXECUTE 'GRANT SELECT,INSERT ON economy.ledger_operations, economy.ledger_entries TO lk_admin_config_editor';
    EXECUTE 'GRANT SELECT,INSERT,UPDATE ON economy.ledger_accounts TO lk_admin_config_editor';
    EXECUTE 'GRANT USAGE,SELECT ON SEQUENCE economy.ledger_entries_id_seq TO lk_admin_config_editor';
  END IF;
END $$;

COMMIT;

-- END 50_giftcode_player_control.sql


-- ======================================================================
-- BEGIN 60_v61_player_economy_permissions_hotfix.sql
-- ======================================================================
-- LOST KINGSLAND ADMIN V6.1 — PLAYER ECONOMY / CHARACTER ART PERMISSION HOTFIX
-- Target database: lost_kingsland_v4_reconciled
-- Run in DBeaver as DB owner (normally: lost_kingsland).
-- Additive + rerunnable. No gameplay data mutation.
-- Fixes: InsufficientPrivilege on economy.ledger_accounts and hardens V6.1 operator permissions.

BEGIN;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='lk_admin_config_editor') THEN
    GRANT USAGE ON SCHEMA identity, hero, adventure, commander, inventory, kingdom, economy, ops, liveops, platform TO lk_admin_config_editor;
    GRANT SELECT ON identity.players, economy.asset_defs TO lk_admin_config_editor;
    GRANT SELECT,INSERT,UPDATE ON economy.ledger_accounts TO lk_admin_config_editor;
    GRANT SELECT,INSERT ON economy.ledger_operations, economy.ledger_entries TO lk_admin_config_editor;
    GRANT USAGE,SELECT ON SEQUENCE economy.ledger_entries_id_seq TO lk_admin_config_editor;
    GRANT SELECT,UPDATE ON hero.character_defs TO lk_admin_config_editor;

    IF to_regclass('platform.media_assets') IS NOT NULL THEN
      GRANT SELECT,INSERT,UPDATE,DELETE ON platform.media_assets TO lk_admin_config_editor;
    END IF;
    IF to_regclass('platform.entity_media_links') IS NOT NULL THEN
      GRANT SELECT,INSERT,UPDATE,DELETE ON platform.entity_media_links TO lk_admin_config_editor;
    END IF;
    IF to_regclass('ops.audit_logs') IS NOT NULL THEN
      GRANT SELECT,INSERT ON ops.audit_logs TO lk_admin_config_editor;
    END IF;
    IF to_regclass('liveops.gift_codes') IS NOT NULL THEN
      GRANT SELECT,INSERT,UPDATE,DELETE ON liveops.gift_codes TO lk_admin_config_editor;
    END IF;
    IF to_regclass('liveops.gift_code_redemptions') IS NOT NULL THEN
      GRANT SELECT,INSERT,UPDATE ON liveops.gift_code_redemptions TO lk_admin_config_editor;
    END IF;
  END IF;

  -- Harden the concrete local login too. This intentionally avoids depending on a
  -- previously misconfigured role chain / NOINHERIT setting.
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='lost_kingsland_admin') THEN
    ALTER ROLE lost_kingsland_admin INHERIT;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='lk_admin_config_editor') THEN
      GRANT lk_admin_config_editor TO lost_kingsland_admin;
    END IF;
    GRANT CONNECT ON DATABASE lost_kingsland_v4_reconciled TO lost_kingsland_admin;
    GRANT USAGE ON SCHEMA identity, hero, adventure, commander, inventory, kingdom, economy, ops, liveops, platform TO lost_kingsland_admin;
    GRANT SELECT ON identity.players, economy.asset_defs TO lost_kingsland_admin;
    GRANT SELECT,INSERT,UPDATE ON economy.ledger_accounts TO lost_kingsland_admin;
    GRANT SELECT,INSERT ON economy.ledger_operations, economy.ledger_entries TO lost_kingsland_admin;
    GRANT USAGE,SELECT ON SEQUENCE economy.ledger_entries_id_seq TO lost_kingsland_admin;
    GRANT SELECT,UPDATE ON hero.character_defs TO lost_kingsland_admin;

    IF to_regclass('platform.media_assets') IS NOT NULL THEN
      GRANT SELECT,INSERT,UPDATE,DELETE ON platform.media_assets TO lost_kingsland_admin;
    END IF;
    IF to_regclass('platform.entity_media_links') IS NOT NULL THEN
      GRANT SELECT,INSERT,UPDATE,DELETE ON platform.entity_media_links TO lost_kingsland_admin;
    END IF;
    IF to_regclass('ops.audit_logs') IS NOT NULL THEN
      GRANT SELECT,INSERT ON ops.audit_logs TO lost_kingsland_admin;
    END IF;
    IF to_regclass('liveops.gift_codes') IS NOT NULL THEN
      GRANT SELECT,INSERT,UPDATE,DELETE ON liveops.gift_codes TO lost_kingsland_admin;
    END IF;
    IF to_regclass('liveops.gift_code_redemptions') IS NOT NULL THEN
      GRANT SELECT,INSERT,UPDATE ON liveops.gift_code_redemptions TO lost_kingsland_admin;
    END IF;
  END IF;
END $$;

COMMIT;

-- Verification: all booleans should be true when connected as lost_kingsland_admin.
-- SELECT current_user,
--   has_table_privilege(current_user,'economy.ledger_accounts','SELECT') AS ledger_select,
--   has_table_privilege(current_user,'economy.ledger_accounts','INSERT') AS ledger_insert,
--   has_table_privilege(current_user,'economy.ledger_accounts','UPDATE') AS ledger_update,
--   has_table_privilege(current_user,'economy.ledger_operations','INSERT') AS op_insert,
--   has_table_privilege(current_user,'economy.ledger_entries','INSERT') AS entry_insert,
--   has_sequence_privilege(current_user,'economy.ledger_entries_id_seq','USAGE') AS seq_usage;

-- END 60_v61_player_economy_permissions_hotfix.sql
