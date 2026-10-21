# Discord Bot ↔ Admin V27 Shared Content Media

## Mục tiêu

Từ giờ ảnh **Item / Character / Boss / Enemy / Commander** chỉ cần upload trong Admin:

```text
Admin upload file
   ↓
platform.media_assets (binary WebP)
   ↓
platform.entity_media_links (PRIMARY / DISCORD / DETAIL / THUMBNAIL / GALLERY)
   ↓
Bot + Web đọc cùng một asset
```

Không copy ảnh vào `Lost-Kingsland-game`.

## Cài DB media layer một lần

Trên `lost_kingsland_v4_reconciled`, chạy bằng DB owner:

```text
sql/20_admin_roles.sql
sql/40_v27_shared_content_media_and_permissions.sql
```

`40_v27...sql` là additive: không sửa Flyway history, không thay gameplay state.

## Bot Java/Spring Boot

Copy `integration/java/ContentMediaJdbcRepository.java` sang gameplay project và dùng nó tại nơi build Discord embed/attachment.

Resolver hỗ trợ:

- `item(itemCode)`
- `character(characterCode)`
- `factionBoss(bossCode)`
- `enemy(enemyCode)`
- `commander(commanderCode)`

Thứ tự ưu tiên ảnh:

1. role `DISCORD`
2. ảnh `PRIMARY`
3. direct `image_asset_key` (Item/Character)

Bot nhận `contentType`, `byte[]`, `sha256` và attach bytes thẳng lên Discord. `sha256` dùng làm cache version nếu cần.

## Hành vi sau integration

Admin đổi PRIMARY/DISCORD image → lần đọc tiếp theo Bot/Web dùng ảnh mới. Không cần sửa folder bot, không cần restart vì đường dẫn file thay đổi.

## Safety

Gameplay/Bot chỉ cần **SELECT** `platform.media_assets` + `platform.entity_media_links`; Admin mới có quyền ghi. Không đưa DB password/token vào source control.
