# Giftcode — Bot Integration Contract

Admin web và Discord Bot dùng trực tiếp cùng PostgreSQL authoritative. Flyway `V42__gift_code_redemption.sql` sở hữu schema; Admin không tự grant reward.

## Redemption flow khuyến nghị

1. Player nhập `/giftcode CODE`.
2. Normalize uppercase.
3. `SELECT ... FOR UPDATE` row `liveops.gift_codes`.
4. Validate status/time/global cap.
5. Count `PENDING_GRANT` + `GRANTED` của player so với `per_player_limit`.
6. Insert `liveops.gift_code_redemptions` với `status=PENDING_GRANT` và `reward_snapshot=gift_codes.reward_bundle`.
7. Increment `gift_codes.redemption_count` trong cùng transaction.
8. Commit reservation.
9. Gameplay authoritative `GiftCodeRewardService` grant `reward_snapshot` với idempotency key = redemption ID.
10. Thành công -> `GRANTED`; lỗi -> `FAILED` + error_code.

Không grant trực tiếp từ Discord handler bằng raw SQL balance update.

## Admin preview

`POST /api/giftcodes/validate`

Body:

```json
{"code":"LK-WELCOME","player_id":"<uuid optional>"}
```

Đây chỉ là preview/read-only, không phải redemption endpoint production. Player redeem bằng `/giftcode code:<CODE>`.

## Runtime contract

- Admin `.env` `DATABASE_URL` và game `.env` `DATABASE_URL` phải cùng database.
- Admin `ADMIN_GAMEPLAY_CONFIG` phải trùng game `ACTIVE_GAMEPLAY_CONFIG`.
- `GET /api/giftcodes/runtime` phải trả `ready=true`, Flyway `>=42`.
- Admin pin `config_version_id` khi tạo hoặc kích hoạt Giftcode.
- Assets được kiểm tra với `economy.asset_defs`.
- Items được kiểm tra với `inventory.item_defs` trong config runtime.
- Equipment tạo immutable ownership event; stackable items tăng `inventory.inventory_stacks` trong transaction grant.

## Reward bundle contract recommended by V6

```json
{
  "assets": {
    "GOLD": 1000,
    "GEMS": 50,
    "SKILL_POINT": 10
  },
  "items": [
    {"item_code": "SOME_ITEM_CODE", "quantity": 1}
  ]
}
```

Asset codes should be validated against `economy.asset_defs`; item codes should be validated against the active gameplay config before RewardService grants them.

## Eligibility keys currently previewed in Admin

```json
{
  "min_account_level": 1,
  "max_account_level": 0,
  "min_exploration_floor": 1,
  "account_status": "ACTIVE"
}
```

`max_account_level=0` means no maximum. The bot redemption service should apply the same eligibility contract before creating a reservation.
