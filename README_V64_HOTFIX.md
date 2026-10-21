# Lost Kingsland Admin V6.4 Media Repair Hotfix

Fixes the exact playtest state where `ITEM_DEF links=480 unique_assets=9`, `EQUIPMENT_SET links=20 unique_assets=1`, and `/api/public/items/{code}/image` can return false 404s.

## Why it happened
- V6.2 mapped placeholders already occupied PRIMARY links, so V6.3 `missing` mode correctly refused to overwrite them.
- The Item public endpoint previously selected the newest config row even when that row had no usable media, while the checker could select another image-bearing version of the same item code.

## Upgrade
Overwrite these files into the existing Admin project. No SQL migration is required.
Restart Admin and press Ctrl+F5.

Go to `Ảnh test & Bot` and press:
`♻ Nâng placeholder cũ → Diverse 664`

This removes only `TEST_PLACEHOLDER` assets/links, preserves real manually-uploaded artwork, and reseeds missing entities with semantic diverse media.

After completion run `Check Bot/Web`. For a good test state:
- ITEM_DEF unique_assets should be hundreds, ideally close to 480.
- EQUIPMENT_SET unique_assets should be well above 1.
- Item HTTP checks should return 200 instead of false 404s.
