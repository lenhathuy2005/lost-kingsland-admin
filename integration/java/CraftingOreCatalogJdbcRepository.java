package lost.kingsland.integration;

import java.sql.*;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * V7.1 demo contract: 9 equipment slots x 10 rarities = exactly 90 ore assets, including PET.
 * Economy balances should still be mutated through the authoritative ledger service.
 */
public final class CraftingOreCatalogJdbcRepository {
    public record CraftingOre(
        String code,
        String displayNameVi,
        String targetSlot,
        String targetRarity,
        String purposeVi,
        int demoCraftCost,
        String imageAssetKey
    ) {}

    private static final String BY_CODE = """
        SELECT code, display_name_vi, target_slot, target_rarity, purpose_vi,
               demo_craft_cost, COALESCE(image_asset_key, linked_primary_asset_key) AS image_asset_key
        FROM admin.v_crafting_ore_materials WHERE code=?
        """;

    private static final String ALL = """
        SELECT code, display_name_vi, target_slot, target_rarity, purpose_vi,
               demo_craft_cost, COALESCE(image_asset_key, linked_primary_asset_key) AS image_asset_key
        FROM admin.v_crafting_ore_materials ORDER BY rarity_ordinal, slot_ordinal
        """;

    public Optional<CraftingOre> find(Connection c, String code) throws SQLException {
        try (PreparedStatement ps = c.prepareStatement(BY_CODE)) {
            ps.setString(1, code);
            try (ResultSet rs = ps.executeQuery()) {
                return rs.next() ? Optional.of(read(rs)) : Optional.empty();
            }
        }
    }

    public List<CraftingOre> findAll(Connection c) throws SQLException {
        List<CraftingOre> out = new ArrayList<>();
        try (PreparedStatement ps = c.prepareStatement(ALL); ResultSet rs = ps.executeQuery()) {
            while (rs.next()) out.add(read(rs));
        }
        return out;
    }

    private CraftingOre read(ResultSet rs) throws SQLException {
        return new CraftingOre(
            rs.getString("code"), rs.getString("display_name_vi"),
            rs.getString("target_slot"), rs.getString("target_rarity"),
            rs.getString("purpose_vi"), rs.getInt("demo_craft_cost"),
            rs.getString("image_asset_key")
        );
    }
}
