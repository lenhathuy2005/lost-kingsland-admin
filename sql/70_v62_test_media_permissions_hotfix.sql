-- LOST KINGSLAND ADMIN V6.2 — ONE-CLICK TEST MEDIA PERMISSIONS
-- Target database: lost_kingsland_v4_reconciled
-- Run in DBeaver as DB owner (normally lost_kingsland).
-- Additive/rerunnable. Grants only the tables needed by Admin Media Studio / test seeder.

BEGIN;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='lk_admin_config_editor') THEN
    GRANT USAGE ON SCHEMA platform, inventory, hero, ops TO lk_admin_config_editor;
    GRANT SELECT,INSERT,UPDATE,DELETE ON platform.media_assets, platform.entity_media_links TO lk_admin_config_editor;
    GRANT SELECT,UPDATE ON inventory.item_defs, hero.character_defs TO lk_admin_config_editor;
    IF to_regclass('ops.audit_logs') IS NOT NULL THEN
      GRANT SELECT,INSERT ON ops.audit_logs TO lk_admin_config_editor;
    END IF;
  END IF;

  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='lost_kingsland_admin') THEN
    ALTER ROLE lost_kingsland_admin INHERIT;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='lk_admin_config_editor') THEN
      GRANT lk_admin_config_editor TO lost_kingsland_admin;
    END IF;
    GRANT USAGE ON SCHEMA platform, inventory, hero, ops TO lost_kingsland_admin;
    GRANT SELECT,INSERT,UPDATE,DELETE ON platform.media_assets, platform.entity_media_links TO lost_kingsland_admin;
    GRANT SELECT,UPDATE ON inventory.item_defs, hero.character_defs TO lost_kingsland_admin;
    IF to_regclass('ops.audit_logs') IS NOT NULL THEN
      GRANT SELECT,INSERT ON ops.audit_logs TO lost_kingsland_admin;
    END IF;
  END IF;
END $$;

COMMIT;
