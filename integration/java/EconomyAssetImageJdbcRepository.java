package lost.kingsland.integration;

import java.sql.*;
import java.util.Optional;

/**
 * Reference-only adapter for the gameplay bot/web service.
 * Reads the same shared media written by Lost Kingsland Admin V7.0.
 * Do not copy image files into the bot project.
 */
public final class EconomyAssetImageJdbcRepository {
    public record Media(String assetKey, String contentType, byte[] bytes) {}

    private static final String SQL = """
        SELECT m.asset_key, m.content_type, m.content_bytes
        FROM economy.asset_defs a
        LEFT JOIN platform.entity_media_links l
          ON l.entity_type='ECONOMY_ASSET' AND l.entity_id=a.code AND l.is_primary=true
        JOIN platform.media_assets m
          ON m.asset_key=COALESCE(NULLIF(a.metadata->>'image_asset_key',''), l.asset_key)
        WHERE a.code=? AND m.active=true
        LIMIT 1
        """;

    public Optional<Media> find(Connection connection, String assetCode) throws SQLException {
        try (PreparedStatement ps = connection.prepareStatement(SQL)) {
            ps.setString(1, assetCode);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) return Optional.empty();
                return Optional.of(new Media(
                    rs.getString("asset_key"),
                    rs.getString("content_type"),
                    rs.getBytes("content_bytes")
                ));
            }
        }
    }
}
