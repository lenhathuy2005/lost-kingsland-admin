# V27 Studio update

- Runtime target changed to `lost_kingsland_v4_reconciled` / `LK-V4.0-P15-RC-001`.
- Offline snapshot rebuilt from final V27 dump: 197 tables, 480 final canonical equipment, 1 current Player.
- Live table discovery replaces stale snapshot whitelist.
- Item Studio pins final `ACTIVE_CANONICAL` catalog.
- Added CRUD for Characters, Faction Bosses, Section/Party rules, Forge, Wheel and final LiveOps rule tables.
- Added generic shared-media studio for Item, Character, Boss, Enemy, Commander, Set, Technique, Building, Research, Race, Path, Affinity, Sect, Region, Clan Boss and Clan Tech.
- Shared binary storage: `platform.media_assets` + `platform.entity_media_links`.
- Added Bot resolver sample `ContentMediaJdbcRepository.java`.
- Fixed V27 Player Support queries (`owner_player_id`, Hero lookup, exploration, breakthrough history, set enabled flag).
- Admin role SQL made V27-safe and conditional.
