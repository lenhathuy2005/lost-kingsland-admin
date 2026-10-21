SELECT current_database(), current_user;
SELECT count(*) AS equipment_ore_count FROM economy.asset_defs WHERE metadata->>'material_family'='EQUIPMENT_ORE';
SELECT target_rarity,count(*) FROM admin.v_crafting_ore_materials GROUP BY target_rarity,rarity_ordinal ORDER BY rarity_ordinal;
SELECT target_slot,count(*) FROM admin.v_crafting_ore_materials GROUP BY target_slot,slot_ordinal ORDER BY slot_ordinal;
SELECT has_table_privilege(current_user,'economy.asset_defs','SELECT') AS asset_select, has_table_privilege(current_user,'economy.asset_defs','UPDATE') AS asset_update, has_table_privilege(current_user,'platform.media_assets','INSERT') AS media_insert, has_table_privilege(current_user,'platform.entity_media_links','INSERT') AS link_insert;
