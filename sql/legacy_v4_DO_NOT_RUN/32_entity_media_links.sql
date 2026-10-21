-- LOST KINGSLAND ADMIN SUPER MEGA v4 — multi-image media gallery links
-- Additive only. Does not replace gameplay tables.
-- Run after sql/30_shared_media_assets.sql.

BEGIN;

CREATE TABLE IF NOT EXISTS platform.entity_media_links (
    entity_type     varchar(64)  NOT NULL,
    entity_id       varchar(160) NOT NULL,
    asset_key       varchar(256) NOT NULL REFERENCES platform.media_assets(asset_key) ON DELETE CASCADE,
    media_role      varchar(32)  NOT NULL DEFAULT 'GALLERY',
    sort_order      integer      NOT NULL DEFAULT 0,
    is_primary      boolean      NOT NULL DEFAULT false,
    created_by      varchar(160),
    created_at      timestamptz  NOT NULL DEFAULT now(),
    metadata        jsonb        NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY(entity_type, entity_id, asset_key),
    CHECK (sort_order >= 0)
);

CREATE INDEX IF NOT EXISTS ix_entity_media_links_entity
    ON platform.entity_media_links(entity_type, entity_id, sort_order);
CREATE INDEX IF NOT EXISTS ix_entity_media_links_asset
    ON platform.entity_media_links(asset_key);
CREATE UNIQUE INDEX IF NOT EXISTS ux_entity_media_one_primary
    ON platform.entity_media_links(entity_type, entity_id)
    WHERE is_primary = true;

COMMENT ON TABLE platform.entity_media_links IS
'Multi-image media links managed by Admin v4. inventory.item_defs.image_asset_key remains the primary Discord/web artwork reference for backwards compatibility.';

-- Backfill existing primary item artwork if media asset exists.
INSERT INTO platform.entity_media_links(entity_type, entity_id, asset_key, media_role, sort_order, is_primary, created_by)
SELECT 'ITEM_DEF', i.id::text, i.image_asset_key, 'PRIMARY', 0, true, 'v4-backfill'
FROM inventory.item_defs i
JOIN platform.media_assets m ON m.asset_key=i.image_asset_key
WHERE i.image_asset_key IS NOT NULL
ON CONFLICT(entity_type, entity_id, asset_key)
DO UPDATE SET media_role='PRIMARY', sort_order=0, is_primary=true;

COMMIT;
