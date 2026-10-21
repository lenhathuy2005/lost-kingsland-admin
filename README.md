# Lost Kingsland Admin V7.1 — Resource & Ore Update

> Start with `INSTALL_V70_READ_ME_FIRST.txt`. V7 adds 10 core resource icons and exactly 90 equipment crafting ores (9 slots × 10 rarities, including PET), plus a compact image-only Admin studio and shared-media integration for Web/Discord Bot.

# Lost Kingsland — Test Media Seed v1

Mục tiêu: gắn ảnh test cho **toàn bộ content đang có trong snapshot V27** mà không phải copy ảnh vào folder gameplay.

## Có gì trong gói

- `media_seed_urls.csv`: 664 mapping entity → URL ảnh test.
- `seed_test_media_from_web.py`: tải ảnh từ web, lưu binary vào `platform.media_assets`, gắn `platform.entity_media_links`, đồng bộ `image_asset_key` cho Item/Character.
- `check_test_media.py`: kiểm tra DB + endpoint mà Web/Discord Bot có thể đọc.
- `COUNTS.txt`: số lượng mapping theo loại.

## Phạm vi mapping hiện tại

- 480 Item (config P15 / id 14)
- 40 Character (catalog gần nhất có dữ liệu: P14 / id 13)
- 100 Faction Boss
- 20 Equipment Set
- 7 Affinity
- 4 Technique
- 4 Race
- 4 Path
- 2 Commander
- 1 Enemy
- 1 Region
- 1 Clan Tech

Tổng: **664 entity**.

## Nguồn ảnh test

### Item
Dùng icon theo slot từ Game-icons.net (HELM/CHEST/BOOTS/SHOULDER/OFF_HAND/AMULET/WEAPON/RING/PET). Đây chỉ là placeholder test nên nhiều item cùng slot sẽ chia sẻ icon.

Game-icons.net dùng CC BY 3.0. Nếu dùng trong bản phát hành, phải attribution tác giả/site hoặc thay bằng artwork chính thức.

### Character / Boss / Skill / content khác
Dùng DiceBear 10.x với seed ổn định từ `entity code`. Các style trong mapping (`pixel-art`, `rings`, `shape-grid`, `glass`) là placeholder; các style DiceBear-owned/được chọn ở đây dùng license CC0 1.0.

## Cách chạy

Copy folder này vào project Admin, ví dụ:

`C:\Project\lost-kingsland-admin\test_media_seed\`

PowerShell:

```powershell
cd C:\Project\lost-kingsland-admin
.\.venv\Scripts\python.exe .\test_media_seed\seed_test_media_from_web.py
```

Lệnh trên chỉ DRY RUN.

Để thực sự tải + gắn ảnh vào DB:

```powershell
.\.venv\Scripts\python.exe .\test_media_seed\seed_test_media_from_web.py --apply
```

Mặc định **không đè ảnh hiện có**. Muốn thay tất cả bằng ảnh test:

```powershell
.\.venv\Scripts\python.exe .\test_media_seed\seed_test_media_from_web.py --apply --force
```

Test thử 20 mapping trước:

```powershell
.\.venv\Scripts\python.exe .\test_media_seed\seed_test_media_from_web.py --apply --limit 20
```

Chỉ Item:

```powershell
.\.venv\Scripts\python.exe .\test_media_seed\seed_test_media_from_web.py --apply --type ITEM_DEF
```

## Check Admin + Bot media

Để Admin đang chạy ở `127.0.0.1:8787`, sau đó:

```powershell
.\.venv\Scripts\python.exe .\test_media_seed\check_test_media.py
```

Script sẽ kiểm tra:

- primary media link theo entity type
- số asset test trong `platform.media_assets`
- vài Item qua `/api/public/items/{item_code}/image`
- vài Character qua `/api/public/media/{asset_key}`

Nếu các endpoint trả HTTP 200 + `image/*`, đường media của Admin đã hoạt động. Discord Bot chỉ cần đọc `image_asset_key`/shared media hoặc gọi endpoint resolver tương ứng.

## Quan trọng

Đây là **TEST PLACEHOLDER MEDIA**, không phải artwork sản xuất. Sau khi pipeline Admin ↔ DB ↔ Bot hoạt động, thay dần bằng artwork chính thức của Lost Kingsland.
