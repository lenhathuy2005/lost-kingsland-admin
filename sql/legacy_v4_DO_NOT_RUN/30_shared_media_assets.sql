-- LOST KINGSLAND ADMIN v3 — shared item artwork storage
-- Additive only. Does not drop/replace gameplay tables.
-- Purpose: Admin uploads image binary directly; item_defs keeps only a stable asset key.
-- Discord bot / website may read the same binary from platform.media_assets or use the Admin public image endpoint.

BEGIN;

CREATE TABLE IF NOT EXISTS platform.media_assets (
    asset_key           varchar(256) PRIMARY KEY,
    category            varchar(64) NOT NULL DEFAULT 'ITEM_IMAGE',
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

CREATE INDEX IF NOT EXISTS ix_media_assets_category_updated
    ON platform.media_assets(category, updated_at DESC);
CREATE INDEX IF NOT EXISTS ix_media_assets_sha256
    ON platform.media_assets(sha256);

COMMENT ON TABLE platform.media_assets IS
'Shared binary media store for admin-managed artwork. Gameplay item rows keep a stable image_asset_key, never a manually entered provider URL or a bot-folder path.';
COMMENT ON COLUMN inventory.item_defs.image_asset_key IS
'Stable reference to shared media. For Admin v3 item artwork, this normally resolves to platform.media_assets.asset_key; Admin UI accepts direct file upload only.';

COMMIT;
