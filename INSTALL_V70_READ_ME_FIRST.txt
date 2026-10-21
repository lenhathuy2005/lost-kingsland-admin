LOST KINGSLAND ADMIN V7.0 — ALL-IN-ONE RESOURCE + ORE UPDATE
=============================================================

WHAT THIS ADDS
- 10 core resource icons: GOLD, GEMS, WOOD, ORE, FOOD, ESSENCE, CULTIVATION_QI, SKILL_POINT, CLAN_MARKS, SEASON_TOKEN.
- Exactly 80 equipment-specific crafting ores = 8 slots x 10 rarities.
- Admin menu: Tài nguyên & Ore.
- Direct Add/Replace/Delete image for every resource/ore.
- One-click demo icon seeder. Images are cached into PostgreSQL shared media.
- Bot/Web stable endpoint + Java reference integration.

INSTALL (CURRENT ADMIN V6.5 -> V7.0)
1) Stop Admin.
2) Extract this ZIP into C:\Project\lost-kingsland-admin and choose Replace All.
3) In DBeaver, connect to lost_kingsland_v4_reconciled.
4) Run ONLY this file for V7:
      sql\00_RUN_THIS_IN_DBEAVER_V70.sql
5) Start Admin:
      .\run_admin.bat
6) Browser: Ctrl+F5.
7) Open: Tài nguyên & Ore.
8) Click: "Gắn demo 90 icon".

CLI alternative:
      .\APPLY_V70_RESOURCE_ORE_MEDIA.bat

Checker:
      .\CHECK_V70_RESOURCE_ORE_MEDIA.bat

DO NOT copy images into the gameplay bot folder. Admin stores rendered WebP bytes in PostgreSQL shared media; Bot/Web resolve the same assets.
