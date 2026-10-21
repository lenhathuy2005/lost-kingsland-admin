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
