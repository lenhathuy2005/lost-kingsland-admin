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
