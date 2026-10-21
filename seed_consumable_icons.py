#!/usr/bin/env python3
"""Seed compact consumable icons into shared PostgreSQL media without replacing Admin artwork."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter

import psycopg

from seed_resource_ore_icons import db_url, download_archive, files, pick, rec, render_core


CONSUMABLES = {
    "P7_CULTIVATION_PILL": ("Đan dược tu luyện", ["pills", "potion ball", "round potion"], "#a855f7"),
    "P7_TRIBULATION_BOOSTER": ("Đan dược trợ kiếp", ["lightning potion", "potion", "thunder"], "#3b82f6"),
    "P7_TRIBULATION_SAFEGUARD": ("Phù hộ kiếp", ["shield", "angel wings", "protection"], "#f59e0b"),
}


def bind(cur, code: str, name: str, data: bytes, source_icon: str, actor: str, force: bool) -> bool:
    cur.execute("SELECT id::text,image_asset_key FROM inventory.item_defs WHERE code=%s ORDER BY config_version_id", (code,))
    definitions = cur.fetchall()
    if not definitions:
        raise RuntimeError(f"Missing item definition: {code}")
    if not force and any(row[1] for row in definitions):
        return False
    sha = hashlib.sha256(data).hexdigest()
    key = f"demo/v72/consumable_icon/{code.lower()}/{sha[:20]}.webp"
    metadata = json.dumps({"demo_seed": "7.2", "source": "Game-icons.net", "license": "CC BY 3.0", "source_icon": source_icon, "display_name_vi": name})
    cur.execute("""
        INSERT INTO platform.media_assets(asset_key,category,content_type,content_bytes,sha256,size_bytes,original_filename,created_by,active,metadata)
        VALUES(%s,'DEMO_CONSUMABLE_ICON','image/webp',%s,%s,%s,%s,%s,true,%s::jsonb)
        ON CONFLICT(asset_key) DO UPDATE SET active=true,updated_at=now(),metadata=EXCLUDED.metadata
    """, (key, data, sha, len(data), f"{code}.webp", actor, metadata))
    for definition_id, _ in definitions:
        cur.execute("UPDATE platform.entity_media_links SET is_primary=false,media_role=CASE WHEN media_role='PRIMARY' THEN 'GALLERY' ELSE media_role END WHERE entity_type='ITEM_DEF' AND entity_id=%s AND is_primary", (definition_id,))
        cur.execute("""
            INSERT INTO platform.entity_media_links(entity_type,entity_id,asset_key,media_role,sort_order,is_primary,created_by,metadata)
            VALUES('ITEM_DEF',%s,%s,'PRIMARY',0,true,%s,%s::jsonb)
            ON CONFLICT(entity_type,entity_id,asset_key) DO UPDATE SET media_role='PRIMARY',sort_order=0,is_primary=true,metadata=EXCLUDED.metadata
        """, (definition_id, key, actor, json.dumps({"demo_seed": "7.2"})))
        cur.execute("UPDATE inventory.item_defs SET image_asset_key=%s,display_name_vi=COALESCE(NULLIF(display_name_vi,''),%s) WHERE id=%s::uuid", (key, name, definition_id))
    cur.execute("UPDATE platform.entity_media_links SET is_primary=false,media_role=CASE WHEN media_role='PRIMARY' THEN 'GALLERY' ELSE media_role END WHERE entity_type='ITEM_CODE' AND entity_id=%s AND is_primary", (code,))
    cur.execute("""
        INSERT INTO platform.entity_media_links(entity_type,entity_id,asset_key,media_role,sort_order,is_primary,created_by,metadata)
        VALUES('ITEM_CODE',%s,%s,'PRIMARY',0,true,%s,%s::jsonb)
        ON CONFLICT(entity_type,entity_id,asset_key) DO UPDATE SET media_role='PRIMARY',sort_order=0,is_primary=true,metadata=EXCLUDED.metadata
    """, (code, key, actor, json.dumps({"demo_seed": "7.2"})))
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-url")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--actor", default="Viet-ConsumableMedia")
    args = parser.parse_args()
    if not args.apply:
        print("Plan: bind three consumable icons. Add --apply to write PostgreSQL.")
        return 0
    download_archive()
    records = [rec(path) for path in files()]
    used = set()
    stats = Counter()
    with psycopg.connect(db_url(args.db_url)) as connection:
        for code, (name, terms, accent) in CONSUMABLES.items():
            chosen = pick(records, terms, used, code)
            used.add(chosen["rel"])
            data = render_core(chosen["p"], accent)
            with connection.cursor() as cursor:
                changed = bind(cursor, code, name, data, chosen["rel"], args.actor, args.force)
            connection.commit()
            stats["bound" if changed else "preserved"] += 1
    print("DONE", dict(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
