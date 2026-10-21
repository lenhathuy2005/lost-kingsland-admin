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
