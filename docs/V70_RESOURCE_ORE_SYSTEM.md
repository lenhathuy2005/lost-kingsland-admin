# Lost Kingsland Admin V7.0 — Resource & Equipment Ore Demo System

## Scope
V7.0 adds one small operator surface for static economy artwork and exactly **80 equipment crafting ores**.

- 10 rarities: COMMON, UNCOMMON, RARE, EPIC, LEGENDARY, MYTHIC, ANCIENT, DIVINE, RELIC, GOD.
- 8 craft targets: HELM, CHEST, SHOULDER, AMULET, BOOTS, RING, OFF_HAND, WEAPON.
- Total: 10 × 8 = 80 ore assets.
- PET is intentionally excluded from this 80-item equipment ore matrix; pet materials can be a separate soul/egg/core system later.

Each ore is a ledger asset in `economy.asset_defs` with `asset_type=CRAFT_MATERIAL`. The static relationship is stored in metadata:

- `material_family=EQUIPMENT_ORE`
- `target_slot`
- `target_rarity`
- `display_name_vi`
- `purpose_vi`
- `image_asset_key`

Example: `ORE_HELM_COMMON` = `Phàm Thiết Khôi Khoáng`, used only for COMMON helmet crafting.

## Names
Rarity material roots:

COMMON Phàm Thiết; UNCOMMON Linh Đồng; RARE Huyền Ngân; EPIC Địa Tủy; LEGENDARY Thiên Tinh; MYTHIC Thái Hư; ANCIENT Hồng Hoang; DIVINE Thần Tiêu; RELIC Bất Hủ; GOD Chư Thiên.

Slot suffixes:

HELM Khôi Khoáng; CHEST Giáp Khoáng; SHOULDER Hộ Kiên Khoáng; AMULET Linh Phù Khoáng; BOOTS Hành Bộ Khoáng; RING Giới Chỉ Khoáng; OFF_HAND Phụ Bảo Khoáng; WEAPON Binh Nhận Khoáng.

Full catalog: `crafting_ore_catalog.csv`.

## Media architecture
No runtime hotlinking:

Game-icons.net archive → local seeder → 256×256 WebP demo icon → `platform.media_assets` → `platform.entity_media_links` (`ECONOMY_ASSET`) → Admin / Web / Discord Bot.

The ore icon is a small emote-style composition: an ore/mineral silhouette plus a slot glyph. Rarity is represented by the frame/accent palette. This keeps demo assets cheap and readable without pretending they are final artwork.

## Admin
Menu: **Tài nguyên & Ore**.

Functions:
- Show the 10 core economy resources.
- Show/filter all 80 ores by rarity and target slot.
- Upload/replace an image directly from Windows.
- Delete the current image.
- One-click seed 90 demo icons (10 core + 80 ores).

There is deliberately no equipment-stat/affix editor on this page. These resources are static definitions; player balances remain authoritative ledger state.

## Gameplay integration
Reference Java adapters:
- `integration/java/EconomyAssetImageJdbcRepository.java`
- `integration/java/CraftingOreCatalogJdbcRepository.java`

Stable HTTP media endpoint for Bot/Web testing:
`GET /api/public/assets/{asset_code}/image`

Examples:
- `/api/public/assets/GOLD/image`
- `/api/public/assets/ORE_HELM_COMMON/image`
- `/api/public/assets/ORE_WEAPON_GOD/image`

## License
The demo seeder uses Game-icons.net assets. Their site states icons are CC BY (and some public domain); retain author/site attribution if these placeholders remain in a public release. V7.0 is intended as demo/playtest media, not final commissioned art.
