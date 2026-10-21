-- Lost Kingsland — optional Admin read models
-- Safe to apply separately. Does not modify gameplay tables or gameplay code.
-- The supplied FULL dump already contains several admin.v_* views; these statements
-- make the standalone admin contract explicit and add a compact dashboard view.

BEGIN;

CREATE SCHEMA IF NOT EXISTS admin;

CREATE OR REPLACE VIEW admin.v_dashboard_counts AS
SELECT
  (SELECT count(*) FROM identity.players)                    AS players,
  (SELECT count(*) FROM inventory.item_defs)                 AS equipment_defs,
  (SELECT count(*) FROM inventory.rarity_policy)             AS rarities,
  (SELECT count(*) FROM inventory.equipment_set_defs)        AS equipment_sets,
  (SELECT count(*) FROM inventory.equipment_set_bonuses)     AS set_bonuses,
  (SELECT count(*) FROM inventory.item_instances)            AS player_item_instances,
  (SELECT count(*) FROM inventory.item_defs
     WHERE image_asset_key IS NULL OR image_asset_key='')     AS missing_item_images,
  (SELECT count(*) FROM platform.feature_flags)              AS feature_flags,
  (SELECT count(*) FROM platform.feature_flags WHERE enabled) AS feature_flags_enabled,
  (SELECT count(*) FROM ops.abuse_signals)                   AS abuse_signals;

CREATE OR REPLACE VIEW admin.v_feature_flags AS
SELECT ff.id, ff.flag_key, ff.enabled, ff.rule_json,
       cv.version_code AS config_version
FROM platform.feature_flags ff
JOIN platform.config_versions cv ON cv.id = ff.config_version_id
ORDER BY ff.flag_key;

CREATE OR REPLACE VIEW admin.v_abuse_signals AS
SELECT * FROM ops.abuse_signals
ORDER BY COALESCE(detected_at, created_at) DESC NULLS LAST;

COMMENT ON SCHEMA admin IS 'Read models and contracts for the standalone Lost Kingsland Admin Web. Gameplay remains authoritative in its own schemas.';

COMMIT;
