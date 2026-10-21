# V7.1 PET Ore Fix

V7.0 omitted the PET equipment slot from the crafting-material matrix. V7.1 corrects the matrix to **9 slots × 10 rarities = 90 crafting ores**.

Added `ORE_PET_COMMON` through `ORE_PET_GOD`, named from `Phàm Thiết Linh Thú Khoáng` through `Chư Thiên Linh Thú Khoáng`. Each is restricted by metadata to `target_slot=PET` and its matching rarity.

Admin `Tài nguyên & Ore` now filters PET, expects 90 ores, and the one-click seeder produces **100 demo icons total**: 10 core resources + 90 ores.

Existing V7.0 DB: run `sql/00_RUN_THIS_IN_DBEAVER_V71.sql` (idempotent) or the smaller `sql/90_v71_pet_ore_extension.sql`.
