# V6 MegaOps Operator Guide

## 1. Database install
In DBeaver connect to `lost_kingsland_v4_reconciled` as `lost_kingsland` and execute only:

`sql/00_INSTALL_V6_ALL_IN_ONE.sql`

For an existing V27 Admin that already has scripts 20 + 40, running only `sql/50_giftcode_player_control.sql` is sufficient. Do not use legacy 10/30/32/34 for this baseline.

## 2. Player Control Center
Open **Người chơi**, choose a player. The drawer shows account/Discord, Hero/Cultivation, Energy/Floor, characters, commanders, item instances, kingdom, clan, market, ledger and support history. Editable operational fields use dedicated endpoints, validation, version increments and `ops.audit_logs`.

Currency/assets are adjusted with **DELTA** or **SET** through `economy.ledger_operations` + `economy.ledger_entries`; the UI does not blindly overwrite ledger balances.

## 3. Character Artwork
Open **Nhân vật & Ảnh**. Select a character, drag/drop PNG/JPEG/WebP/GIF, then upload as PRIMARY or gallery. PRIMARY updates the current `ADMIN_GAMEPLAY_CONFIG` version of `hero.character_defs.image_asset_key` only; historical config versions are not overwritten. Binary WebP is shared via `platform.media_assets` and `platform.entity_media_links`.

## 4. Giftcode
Open **Giftcode**. Create a code with status/window/global cap/per-player cap, reward JSON and eligibility JSON. Admin can validate a code against a player and inspect redemption history. The Discord bot integration is intentionally separate; see `docs/GIFTCODE_BOT_INTEGRATION.md`.

## 5. Local Owner
On `127.0.0.1`, `ADMIN_LOCAL_OWNER_MODE=true` identifies the session as `Viet / OWNER` and no `X-Admin-Token` prompt is required. Keep `ADMIN_ALLOW_REMOTE_NO_AUTH=false`.
