-- Lost Kingsland V7.1 readiness
SELECT
  count(*) FILTER (WHERE metadata->>'material_family'='EQUIPMENT_ORE') AS ore_defs,
  count(*) FILTER (WHERE metadata->>'material_family'='EQUIPMENT_ORE' AND metadata->>'target_slot'='PET') AS pet_ore_defs,
  count(DISTINCT metadata->>'target_slot') FILTER (WHERE metadata->>'material_family'='EQUIPMENT_ORE') AS ore_slots,
  count(DISTINCT metadata->>'target_rarity') FILTER (WHERE metadata->>'material_family'='EQUIPMENT_ORE') AS ore_rarities
FROM economy.asset_defs;
