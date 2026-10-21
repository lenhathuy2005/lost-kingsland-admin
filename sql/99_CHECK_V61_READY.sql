-- LOST KINGSLAND ADMIN V6.1 READY CHECK
-- Run in DBeaver on lost_kingsland_v4_reconciled.

SELECT current_database() AS database_name, current_user AS db_user;

SELECT rolname, rolinherit
FROM pg_roles
WHERE rolname IN ('lost_kingsland_admin','lk_admin_readonly','lk_admin_config_editor')
ORDER BY rolname;

SELECT
  to_regclass('platform.media_assets') AS media_assets,
  to_regclass('platform.entity_media_links') AS entity_media_links,
  to_regclass('liveops.gift_codes') AS gift_codes,
  to_regclass('liveops.gift_code_redemptions') AS gift_code_redemptions;

SELECT cv.version_code, count(*) AS character_count
FROM hero.character_defs c
JOIN platform.config_versions cv ON cv.id=c.config_version_id
GROUP BY cv.version_code,cv.id
ORDER BY cv.id DESC;

-- Evaluate concrete login privileges independent of the DBeaver connection user.
SELECT
  has_table_privilege('lost_kingsland_admin','economy.ledger_accounts','SELECT') AS ledger_accounts_select,
  has_table_privilege('lost_kingsland_admin','economy.ledger_accounts','INSERT') AS ledger_accounts_insert,
  has_table_privilege('lost_kingsland_admin','economy.ledger_accounts','UPDATE') AS ledger_accounts_update,
  has_table_privilege('lost_kingsland_admin','economy.ledger_operations','INSERT') AS ledger_operations_insert,
  has_table_privilege('lost_kingsland_admin','economy.ledger_entries','INSERT') AS ledger_entries_insert,
  has_sequence_privilege('lost_kingsland_admin','economy.ledger_entries_id_seq','USAGE') AS ledger_entries_sequence_usage,
  has_table_privilege('lost_kingsland_admin','hero.character_defs','SELECT') AS character_select,
  has_table_privilege('lost_kingsland_admin','hero.character_defs','UPDATE') AS character_update;
