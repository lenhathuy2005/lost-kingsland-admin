package com.lostkingsland.media;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

/**
 * Shared V27 artwork resolver for Discord/gameplay.
 * Admin owns media metadata; gameplay reads only. No artwork is copied into the bot folder.
 *
 * Preferred role for Discord is DISCORD, then PRIMARY, then direct image_asset_key where
 * the canonical table already exposes one (items/characters).
 */
@Repository
public class ContentMediaJdbcRepository {
    private final JdbcTemplate jdbc;

    public ContentMediaJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<ContentImage> item(String itemCode) {
        return first("""
            SELECT a.asset_key,a.content_type,a.content_bytes,a.sha256
            FROM inventory.item_defs e
            JOIN platform.config_versions cv ON cv.id=e.config_version_id
            JOIN LATERAL (
              SELECT x.asset_key
              FROM (
                SELECT l.asset_key,
                       CASE WHEN l.media_role='DISCORD' THEN 0 WHEN l.is_primary THEN 1 ELSE 2 END AS priority,
                       l.sort_order
                FROM platform.entity_media_links l
                WHERE l.entity_type='ITEM_DEF' AND l.entity_id=e.id::text
                UNION ALL
                SELECT e.image_asset_key, 1, 0 WHERE e.image_asset_key IS NOT NULL
              ) x
              ORDER BY x.priority,x.sort_order
              LIMIT 1
            ) chosen ON true
            JOIN platform.media_assets a ON a.asset_key=chosen.asset_key AND a.active=true
            WHERE e.code=? AND COALESCE(e.catalog_status,'ACTIVE_CANONICAL')='ACTIVE_CANONICAL'
            ORDER BY CASE WHEN cv.version_code='LK-V4.0-P15-RC-001' THEN 0 ELSE 1 END,e.config_version_id DESC
            LIMIT 1
            """, itemCode);
    }

    public Optional<ContentImage> character(String characterCode) {
        return first("""
            SELECT a.asset_key,a.content_type,a.content_bytes,a.sha256
            FROM hero.character_defs e
            JOIN LATERAL (
              SELECT x.asset_key
              FROM (
                SELECT l.asset_key,
                       CASE WHEN l.media_role='DISCORD' THEN 0 WHEN l.is_primary THEN 1 ELSE 2 END AS priority,
                       l.sort_order
                FROM platform.entity_media_links l
                WHERE l.entity_type='CHARACTER_DEF' AND l.entity_id=e.code
                UNION ALL
                SELECT e.image_asset_key,1,0 WHERE e.image_asset_key IS NOT NULL
              ) x
              ORDER BY x.priority,x.sort_order
              LIMIT 1
            ) chosen ON true
            JOIN platform.media_assets a ON a.asset_key=chosen.asset_key AND a.active=true
            WHERE e.code=? AND e.active=true
            LIMIT 1
            """, characterCode);
    }

    public Optional<ContentImage> factionBoss(String bossCode) {
        return genericByNaturalCode(
            "adventure.faction_boss_catalog", "boss_code", "boss_code", "FACTION_BOSS", bossCode);
    }

    public Optional<ContentImage> enemy(String enemyCode) {
        return genericByNaturalCode(
            "content.enemy_defs", "id", "code", "ENEMY_DEF", enemyCode);
    }

    public Optional<ContentImage> commander(String commanderCode) {
        return genericByNaturalCode(
            "commander.commander_defs", "id", "code", "COMMANDER_DEF", commanderCode);
    }

    private Optional<ContentImage> genericByNaturalCode(
            String table, String entityIdColumn, String codeColumn, String entityType, String code) {
        // table/column/entityType are constants from methods above, never user-controlled.
        String sql = """
            SELECT a.asset_key,a.content_type,a.content_bytes,a.sha256
            FROM %s e
            JOIN LATERAL (
              SELECT l.asset_key
              FROM platform.entity_media_links l
              WHERE l.entity_type=? AND l.entity_id=e.%s::text
              ORDER BY CASE WHEN l.media_role='DISCORD' THEN 0 WHEN l.is_primary THEN 1 ELSE 2 END,
                       l.sort_order,l.created_at
              LIMIT 1
            ) chosen ON true
            JOIN platform.media_assets a ON a.asset_key=chosen.asset_key AND a.active=true
            WHERE e.%s=?
            LIMIT 1
            """.formatted(table, entityIdColumn, codeColumn);
        return first(sql, entityType, code);
    }

    private Optional<ContentImage> first(String sql, Object... args) {
        List<ContentImage> rows = jdbc.query(sql,
            (rs, rowNum) -> new ContentImage(
                rs.getString("asset_key"),
                rs.getString("content_type"),
                rs.getBytes("content_bytes"),
                rs.getString("sha256")
            ), args);
        return rows.stream().findFirst();
    }

    public record ContentImage(String assetKey, String contentType, byte[] bytes, String sha256) {}
}
