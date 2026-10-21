# Admin scope mapped to the GDD

The UI navigation follows the Admin/LiveOps responsibilities specified by the project GDD:

- **Player Support** — player/account/hero overview and owned item inspection.
- **Game Config** — equipment catalog, set bonuses and general content tables.
- **Clan / Competitive / Economy inspection** — available through Database Explorer and relevant raw tables.
- **LiveOps** — feature flags, events, leaderboards, merchant rotations, offers and seasons.
- **Operations / Incident support** — abuse signals, compensation cases, sanctions, audit logs, outbox and scheduled actions.
- **Database Explorer** — read-only table explorer across the schemas present in the full dump.

## Implemented item editing

The first write-capable workflow is intentionally limited to fields that are commonly managed by a content admin:

- `display_name_vi`
- `image_asset_key`
- `transferable`
- `tags`
- `base_stats`
- `base_effects`

Rarity, slot, item code, set identity and config-version ownership are kept read-only in v1 to reduce the chance of breaking gameplay contracts accidentally.
