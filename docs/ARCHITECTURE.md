# Lost Kingsland Admin Web — Architecture

## Separation rule

This admin is a **standalone project and standalone process**. It does not sit inside the Discord gameplay source tree and does not replace any gameplay handler, combat service, or Discord UI flow.

```text
Discord Gameplay / Bot (existing project)
        |
        +---------------------> PostgreSQL (authoritative game DB)
                                   ^
                                   |
Standalone Admin Web -------------+
  - own port (default 8787)
  - own environment variables
  - own DB login/role
  - read-only by default
```

The application has two modes:

1. **Snapshot mode (default)** — reads `data/snapshot.json` generated from the supplied full pg_dump. It is completely detached from the gameplay database. Any edit is staged only in browser `localStorage` and can be exported as SQL for review.
2. **Live PostgreSQL mode** — enabled only when `DATABASE_URL` is set. Reads from the real DB. Mutating item definition fields is still disabled unless `ADMIN_WRITE_ENABLED=true` and a valid `ADMIN_TOKEN` is supplied.

## Why file 4 is authoritative for this admin build

The supplied full dump is newer than the baseline schema file and contains the actual project data plus later schema changes, including:

- `admin` schema and admin read views;
- 10 item rarities: COMMON, UNCOMMON, RARE, EPIC, LEGENDARY, MYTHIC, ANCIENT, DIVINE, RELIC, GOD;
- equipment set definitions and 2/4/6/8-piece bonuses;
- item image placeholder field `inventory.item_defs.image_asset_key`;
- populated equipment catalog and test player data.

Therefore the snapshot builder reads the **full dump**, not the older baseline schema, to avoid regressing the project to an earlier five-rarity model.

## Safety boundaries

- No SQL is executed when building a snapshot.
- Database Explorer uses a table whitelist derived from the supplied dump.
- Live update endpoint only accepts six whitelisted columns on `inventory.item_defs`.
- Snapshot edits export SQL with `ROLLBACK` as the default final statement. Review is required before changing it to `COMMIT`.
- Recommended DB accounts are `lk_admin_readonly` or the narrowly scoped `lk_admin_item_editor` role.
