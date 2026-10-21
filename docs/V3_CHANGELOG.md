# Admin v3 change summary

- Direct file artwork UI: drag/drop, preview, add, replace, delete.
- No editable image URL / `image_asset_key` in Item CRUD forms.
- Bulk item artwork upload by `<item_code>.<ext>` up to 500 files.
- Optional shared PostgreSQL binary media table `platform.media_assets`.
- Bot/web binary resolver by item code: `/api/public/items/{item_code}/image`.
- Java Spring Boot examples for direct PostgreSQL bytes or HTTP resolver.
- Expanded navigation: Character/Cultivation, World/PvE, Kingdom/Progression, Commander/Clan, Economy/Market, Discord Ops.
- 41 controlled CRUD resources.
- Player 360 support drawer spanning Hero, Inventory, Commander, Kingdom, March, Clan, Economy, Market, Exploration, Adventure, Tribulation, Sanctions and Compensation.
- Dedicated Media Library with missing-artwork queue and media gallery.
