package com.lostkingsland.media;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.util.Optional;

/**
 * Preferred integration when Discord gameplay and Admin share the same PostgreSQL.
 * The bot asks by item code and receives the image bytes directly from platform.media_assets.
 * No image needs to exist inside the gameplay/bot folder and no URL is stored in the item definition.
 */
@Repository
public class ItemImageJdbcRepository {
    private final JdbcTemplate jdbc;

    public ItemImageJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<ItemImage> findByItemCode(String itemCode) {
        var rows = jdbc.query(
            """
            SELECT m.content_type, m.content_bytes, m.sha256
            FROM inventory.item_defs i
            JOIN platform.media_assets m ON m.asset_key = i.image_asset_key AND m.active = true
            WHERE i.code = ?
            ORDER BY i.config_version_id DESC
            LIMIT 1
            """,
            (rs, rowNum) -> new ItemImage(
                rs.getString("content_type"),
                rs.getBytes("content_bytes"),
                rs.getString("sha256")
            ),
            itemCode
        );
        return rows.stream().findFirst();
    }

    public record ItemImage(String contentType, byte[] bytes, String sha256) {}
}
