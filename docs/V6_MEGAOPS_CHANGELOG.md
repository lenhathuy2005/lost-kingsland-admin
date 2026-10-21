# Lost Kingsland Admin V6 MegaOps

Version: `6.0.0-v27-megaops`

## 1. Giftcode Studio

Thêm database contract độc lập với Discord UI:

- `liveops.gift_codes`
- `liveops.gift_code_redemptions`
- `admin.v_gift_codes`
- `admin.v_gift_code_redemptions`

Admin có thể:

- tạo code thủ công hoặc random;
- bật/tắt/pause/archive;
- đặt `starts_at`, `ends_at`;
- global redemption cap;
- per-player cap;
- reward bundle JSON;
- eligibility JSON;
- xem lịch sử redemption;
- test/preview code với một Player ID.

Admin **không tự grant reward khi tạo code**. Bot/gameplay sau này reserve redemption và grant reward bằng authoritative reward/ledger service.

## 2. Player Control Center

Player 360 không còn chỉ đọc. OWNER có purpose-built editor cho:

- Account name / level / XP / tutorial step;
- Account status / locale / timezone;
- Hero level / XP / Realm / Stage / Linh khí / cultivation / Sect;
- Energy;
- Exploration Floor;
- Secondary Character native level / XP / ascension;
- Commander level / XP / star / status;
- Item instance rarity / item level / state / lock / affixes;
- Kingdom building level/state;
- Economy balance adjustment.

Tất cả update:

- kiểm tra ownership của Player;
- validate basic invariants;
- bump `version` nếu table có version;
- update `updated_at` nếu table có field này;
- ghi `ops.audit_logs`.

### Economy balance

Không raw-update `available_balance` đơn độc. Admin tạo:

1. `economy.ledger_operations`
2. update `economy.ledger_accounts`
3. `economy.ledger_entries`
4. `ops.audit_logs`

Có 2 mode: `DELTA` và `SET`.

## 3. Character Artwork Studio

Thêm menu riêng **Nhân vật & Ảnh** cho `hero.character_defs`.

- filter/search 40 Character;
- preview rarity/role/affinity/signature skill/lore;
- upload ảnh trực tiếp từ Windows;
- PRIMARY + Gallery;
- PRIMARY sync `hero.character_defs.image_asset_key`;
- binary vẫn lưu chung `platform.media_assets`;
- Bot/Web đọc cùng media contract.

## 4. DB install

Sau V27 base Admin:

1. `sql/20_admin_roles.sql`
2. `sql/40_v27_shared_content_media_and_permissions.sql`
3. `sql/50_giftcode_player_control.sql`

File 50 là additive/rerunnable.

## 5. Hardening in final V6 package

- Added `sql/00_INSTALL_V6_ALL_IN_ONE.sql` so DBeaver needs only one installer for V27 (`20 -> 40 -> 50`).
- Dedicated Character media operations now scope `hero.character_defs` to `ADMIN_GAMEPLAY_CONFIG`; PRIMARY changes never overwrite historical config-version rows with the same character code.
- Local Owner mode is preserved: loopback `Viet / OWNER` does not require `X-Admin-Token`.
- `economy.asset_defs` SELECT permission is included for the ledger-safe balance editor.
