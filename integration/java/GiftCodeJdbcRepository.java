package com.lostkingsland.integration;

import javax.sql.DataSource;
import java.sql.*;
import java.time.OffsetDateTime;
import java.util.UUID;

/**
 * Reference integration for the gameplay/Discord service.
 * Reserve first, then grant the reward snapshot through the authoritative RewardService.
 * This class is intentionally framework-neutral and may be adapted to Spring JDBC/JPA.
 */
public final class GiftCodeJdbcRepository {
    private final DataSource dataSource;

    public GiftCodeJdbcRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public record Reservation(UUID redemptionId, UUID giftCodeId, String code, String rewardJson) {}

    public Reservation reserve(String rawCode, UUID playerId, String requestId) throws SQLException {
        String code = rawCode == null ? "" : rawCode.trim().toUpperCase();
        try (Connection c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            try {
                UUID giftId;
                String rewardJson;
                int perPlayerLimit;
                Integer maxRedemptions;
                int redemptionCount;
                String status;
                OffsetDateTime startsAt;
                OffsetDateTime endsAt;
                int minAccountLevel;
                int maxAccountLevel;
                int minExplorationFloor;
                String requiredAccountStatus;

                try (PreparedStatement ps = c.prepareStatement("""
                    SELECT id, code, status, starts_at, ends_at, max_redemptions,
                           per_player_limit, redemption_count, reward_bundle::text,
                           COALESCE(NULLIF(eligibility_json->>'min_account_level','')::int,0) AS min_account_level,
                           COALESCE(NULLIF(eligibility_json->>'max_account_level','')::int,0) AS max_account_level,
                           COALESCE(NULLIF(eligibility_json->>'min_exploration_floor','')::int,0) AS min_exploration_floor,
                           upper(COALESCE(eligibility_json->>'account_status','')) AS required_account_status
                    FROM liveops.gift_codes
                    WHERE upper(code)=upper(?)
                    FOR UPDATE
                    """)) {
                    ps.setString(1, code);
                    try (ResultSet rs = ps.executeQuery()) {
                        if (!rs.next()) throw new SQLException("CODE_NOT_FOUND");
                        giftId = rs.getObject("id", UUID.class);
                        status = rs.getString("status");
                        startsAt = rs.getObject("starts_at", OffsetDateTime.class);
                        endsAt = rs.getObject("ends_at", OffsetDateTime.class);
                        maxRedemptions = (Integer) rs.getObject("max_redemptions");
                        perPlayerLimit = rs.getInt("per_player_limit");
                        redemptionCount = rs.getInt("redemption_count");
                        rewardJson = rs.getString("reward_bundle");
                        minAccountLevel = rs.getInt("min_account_level");
                        maxAccountLevel = rs.getInt("max_account_level");
                        minExplorationFloor = rs.getInt("min_exploration_floor");
                        requiredAccountStatus = rs.getString("required_account_status");
                    }
                }

                OffsetDateTime now = OffsetDateTime.now();
                if (!"ACTIVE".equals(status)) throw new SQLException("CODE_NOT_ACTIVE");
                if (startsAt != null && startsAt.isAfter(now)) throw new SQLException("CODE_NOT_STARTED");
                if (endsAt != null && !endsAt.isAfter(now)) throw new SQLException("CODE_EXPIRED");
                if (maxRedemptions != null && redemptionCount >= maxRedemptions) throw new SQLException("GLOBAL_LIMIT_REACHED");

                try (PreparedStatement ps = c.prepareStatement("""
                    SELECT p.account_level, upper(a.status) AS account_status, COALESCE(ep.highest_floor,1) AS highest_floor
                    FROM identity.players p
                    JOIN identity.accounts a ON a.id=p.account_id
                    LEFT JOIN adventure.player_exploration_progress ep ON ep.player_id=p.id
                    WHERE p.id=?
                    """)) {
                    ps.setObject(1, playerId);
                    try (ResultSet rs = ps.executeQuery()) {
                        if (!rs.next()) throw new SQLException("PLAYER_NOT_FOUND");
                        int level = rs.getInt("account_level");
                        int floor = rs.getInt("highest_floor");
                        String accountStatus = rs.getString("account_status");
                        if (minAccountLevel > 0 && level < minAccountLevel) throw new SQLException("ACCOUNT_LEVEL_TOO_LOW");
                        if (maxAccountLevel > 0 && level > maxAccountLevel) throw new SQLException("ACCOUNT_LEVEL_TOO_HIGH");
                        if (minExplorationFloor > 0 && floor < minExplorationFloor) throw new SQLException("EXPLORATION_FLOOR_TOO_LOW");
                        if (requiredAccountStatus != null && !requiredAccountStatus.isBlank() && !requiredAccountStatus.equals(accountStatus))
                            throw new SQLException("ACCOUNT_STATUS_NOT_ELIGIBLE");
                    }
                }

                try (PreparedStatement ps = c.prepareStatement("""
                    SELECT count(*)
                    FROM liveops.gift_code_redemptions
                    WHERE gift_code_id=? AND player_id=?
                      AND status IN ('PENDING_GRANT','GRANTED')
                    """)) {
                    ps.setObject(1, giftId);
                    ps.setObject(2, playerId);
                    try (ResultSet rs = ps.executeQuery()) {
                        rs.next();
                        if (rs.getInt(1) >= perPlayerLimit) throw new SQLException("PLAYER_LIMIT_REACHED");
                    }
                }

                UUID redemptionId;
                try (PreparedStatement ps = c.prepareStatement("""
                    INSERT INTO liveops.gift_code_redemptions(
                      gift_code_id, player_id, request_id, status, reward_snapshot
                    ) VALUES (?, ?, ?, 'PENDING_GRANT', ?::jsonb)
                    RETURNING id
                    """)) {
                    ps.setObject(1, giftId);
                    ps.setObject(2, playerId);
                    ps.setString(3, requestId);
                    ps.setString(4, rewardJson);
                    try (ResultSet rs = ps.executeQuery()) { rs.next(); redemptionId = rs.getObject(1, UUID.class); }
                }

                try (PreparedStatement ps = c.prepareStatement("""
                    UPDATE liveops.gift_codes
                    SET redemption_count=redemption_count+1, updated_at=now(), version=version+1
                    WHERE id=?
                    """)) {
                    ps.setObject(1, giftId);
                    ps.executeUpdate();
                }

                c.commit();
                return new Reservation(redemptionId, giftId, code, rewardJson);
            } catch (SQLException ex) {
                c.rollback();
                throw ex;
            }
        }
    }

    public void markGranted(UUID redemptionId) throws SQLException {
        updateStatus(redemptionId, "GRANTED", null);
    }

    public void markFailed(UUID redemptionId, String errorCode) throws SQLException {
        updateStatus(redemptionId, "FAILED", errorCode);
    }

    private void updateStatus(UUID id, String status, String error) throws SQLException {
        try (Connection c = dataSource.getConnection(); PreparedStatement ps = c.prepareStatement("""
            UPDATE liveops.gift_code_redemptions
            SET status=?, granted_at=CASE WHEN ?='GRANTED' THEN now() ELSE granted_at END,
                failed_at=CASE WHEN ?='FAILED' THEN now() ELSE failed_at END,
                error_code=?
            WHERE id=?
            """)) {
            ps.setString(1, status); ps.setString(2, status); ps.setString(3, status);
            ps.setString(4, error); ps.setObject(5, id); ps.executeUpdate();
        }
    }
}
