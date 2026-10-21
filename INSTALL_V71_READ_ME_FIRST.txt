LOST KINGSLAND ADMIN V7.1 — ALL-IN-ONE RESOURCE + ORE UPDATE
=============================================================

WHAT THIS ADDS
- 10 core resource icons: GOLD, GEMS, WOOD, ORE, FOOD, ESSENCE, CULTIVATION_QI, SKILL_POINT, CLAN_MARKS, SEASON_TOKEN.
- Exactly 90 equipment-specific crafting ores = 9 slots x 10 rarities, including PET.
- Admin menu: Tài nguyên & Ore.
- Direct Add/Replace/Delete image for every resource/ore.
- One-click demo icon seeder. Images are cached into PostgreSQL shared media.
- Bot/Web stable endpoint + Java reference integration.

INSTALL (CURRENT ADMIN V6.5 -> V7.1)
1) Stop Admin.
2) Extract this ZIP into C:\Project\lost-kingsland-admin and choose Replace All.
3) In DBeaver, connect to lost_kingsland_v4_reconciled.
4) Run this idempotent V7.1 file:
      sql\00_RUN_THIS_IN_DBEAVER_V71.sql
5) Start Admin:
      .\run_admin.bat
6) Browser: Ctrl+F5.
7) Open: Tài nguyên & Ore.
8) Click: "Gắn demo 100 icon".

CLI alternative:
      .\APPLY_V71_RESOURCE_ORE_MEDIA.bat

Checker:
      .\CHECK_V71_RESOURCE_ORE_MEDIA.bat

DO NOT copy images into the gameplay bot folder. Admin stores rendered WebP bytes in PostgreSQL shared media; Bot/Web resolve the same assets.
