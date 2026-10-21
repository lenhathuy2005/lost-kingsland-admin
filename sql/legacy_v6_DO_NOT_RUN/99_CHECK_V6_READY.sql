-- Lost Kingsland Admin V6 — quick verification
-- Run in DBeaver on lost_kingsland_v4_reconciled after 00_INSTALL_V6_ALL_IN_ONE.sql.
SELECT current_database() AS database_name, current_user AS db_user;

SELECT rolname
FROM pg_roles
WHERE rolname IN ('lk_admin_readonly','lk_admin_config_editor','lost_kingsland_admin')
ORDER BY rolname;

SELECT
  to_regclass('platform.media_assets') AS media_assets,
  to_regclass('platform.entity_media_links') AS entity_media_links,
  to_regclass('liveops.gift_codes') AS gift_codes,
  to_regclass('liveops.gift_code_redemptions') AS gift_code_redemptions,
  to_regclass('admin.v_gift_codes') AS gift_code_view;

SELECT count(*) AS current_config_characters
FROM hero.character_defs c
JOIN platform.config_versions cv ON cv.id=c.config_version_id
WHERE cv.version_code='LK-V4.0-P15-RC-001';
