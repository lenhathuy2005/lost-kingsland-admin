#!/usr/bin/env python3
"""Lost Kingsland TEST media seeder.

Downloads placeholder images from the URLs in media_seed_urls.csv and stores them in
platform.media_assets + platform.entity_media_links. Items and characters also get
their direct image_asset_key updated so the current Admin/Web/Bot resolver works.

This script is intended for LOCAL/PLAYTEST only. It does not touch combat/economy state.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import psycopg
except ImportError:
    print("Missing psycopg. Run: python -m pip install psycopg[binary]", file=sys.stderr)
    raise

HERE = Path(__file__).resolve().parent
DEFAULT_CSV = HERE / "media_seed_urls.csv"


def load_env(path: Path) -> dict[str, str]:
    result = {}
    if not path.exists():
        return result
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        result[k.strip()] = v.strip().strip('"').strip("'")
    return result


def get_db_url(cli: str | None) -> str:
    if cli:
        return cli
    # First current environment, then project .env next to cwd / parent.
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    candidates = [Path.cwd() / ".env", HERE.parent / ".env", HERE / ".env"]
    for p in candidates:
        env = load_env(p)
        if env.get("DATABASE_URL"):
            return env["DATABASE_URL"]
    raise SystemExit("DATABASE_URL not found. Pass --db-url or run from lost-kingsland-admin with .env present.")


def download(url: str, retries: int = 4) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "Lost-Kingsland-Test-Media-Seeder/1.0"})
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                ctype = (resp.headers.get_content_type() or "application/octet-stream").lower()
                if not ctype.startswith("image/"):
                    raise RuntimeError(f"URL did not return image content: {ctype}")
                if len(data) < 64:
                    raise RuntimeError("Downloaded image is unexpectedly small")
                return data, ctype
        except Exception as e:
            last = e
            if attempt + 1 < retries:
                time.sleep(1.0 + attempt * 1.5)
    raise RuntimeError(f"Download failed after {retries} attempts: {url}: {last}")


def ext_for(ctype: str) -> str:
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/svg+xml": ".svg",
        "image/gif": ".gif",
    }.get(ctype, mimetypes.guess_extension(ctype) or ".bin")


def existing_primary(cur, entity_type: str, entity_id: str) -> str | None:
    cur.execute(
        "SELECT asset_key FROM platform.entity_media_links WHERE entity_type=%s AND entity_id=%s AND is_primary=true LIMIT 1",
        (entity_type, entity_id),
    )
    row = cur.fetchone()
    return row[0] if row else None


def bind_primary(cur, row: dict[str, str], asset_key: str, actor: str, force: bool) -> str:
    etype, eid = row["entity_type"], row["entity_id"]
    current = existing_primary(cur, etype, eid)
    if current and not force:
        return "SKIP_EXISTS"

    cur.execute(
        """UPDATE platform.entity_media_links
           SET is_primary=false,
               media_role=CASE WHEN media_role='PRIMARY' THEN 'GALLERY' ELSE media_role END
           WHERE entity_type=%s AND entity_id=%s AND is_primary=true""",
        (etype, eid),
    )
    cur.execute(
        """INSERT INTO platform.entity_media_links(
               entity_type, entity_id, asset_key, media_role, sort_order, is_primary, created_by, metadata
           ) VALUES (%s,%s,%s,'PRIMARY',0,true,%s,%s::jsonb)
           ON CONFLICT(entity_type,entity_id,asset_key)
           DO UPDATE SET media_role='PRIMARY', sort_order=0, is_primary=true,
                         metadata=EXCLUDED.metadata""",
        (
            etype,
            eid,
            asset_key,
            actor,
            json.dumps({"test_seed": True, "source_url": row["source_url"], "source": row["source"], "license": row["license"]}),
        ),
    )

    # Keep direct compatibility fields in sync with the current codebase.
    if etype == "ITEM_DEF":
        cur.execute("UPDATE inventory.item_defs SET image_asset_key=%s WHERE id=%s::uuid", (asset_key, eid))
    elif etype == "CHARACTER_DEF":
        cfg = row.get("config_version_id") or None
        if cfg:
            cur.execute(
                "UPDATE hero.character_defs SET image_asset_key=%s WHERE code=%s AND config_version_id=%s",
                (asset_key, row["code"], int(cfg)),
            )
        else:
            cur.execute(
                "UPDATE hero.character_defs SET image_asset_key=%s WHERE code=%s",
                (asset_key, row["code"]),
            )
    return "BOUND"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(DEFAULT_CSV))
    ap.add_argument("--db-url")
    ap.add_argument("--apply", action="store_true", help="Actually download and write media. Without this, dry-run only.")
    ap.add_argument("--force", action="store_true", help="Replace existing primary images. Default: only fill missing images.")
    ap.add_argument("--type", action="append", dest="types", help="Limit to entity type, may be repeated, e.g. --type ITEM_DEF")
    ap.add_argument("--limit", type=int, default=0, help="Only process first N mapping rows (0=all).")
    ap.add_argument("--actor", default="Viet-TestMediaSeeder")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.csv, encoding="utf-8-sig", newline="")))
    if args.types:
        allow = {x.upper() for x in args.types}
        rows = [r for r in rows if r["entity_type"].upper() in allow]
    if args.limit > 0:
        rows = rows[: args.limit]

    from collections import Counter
    counts = Counter(r["entity_type"] for r in rows)
    print("Mapping rows:", len(rows))
    for k in sorted(counts):
        print(f"  {k}: {counts[k]}")
    print("Unique source URLs:", len({r['source_url'] for r in rows}))

    if not args.apply:
        print("\nDRY RUN only. To write to DB: python seed_test_media_from_web.py --apply")
        return 0

    db_url = get_db_url(args.db_url)
    cache: dict[str, tuple[bytes, str, str]] = {}
    stats = Counter()

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            # Fail early with a clear message if V27 shared media schema is missing.
            cur.execute("SELECT to_regclass('platform.media_assets'), to_regclass('platform.entity_media_links')")
            a, l = cur.fetchone()
            if not a or not l:
                raise SystemExit("Shared media tables missing. Apply Admin V27/V6 SQL media patch first.")

        for idx, row in enumerate(rows, 1):
            url = row["source_url"]
            try:
                if url not in cache:
                    data, ctype = download(url)
                    sha = hashlib.sha256(data).hexdigest()
                    asset_key = f"test/webseed/{sha[:32]}{ext_for(ctype)}"
                    cache[url] = (data, ctype, asset_key)
                    time.sleep(0.08)  # be polite to public test services
                data, ctype, asset_key = cache[url]
                sha = hashlib.sha256(data).hexdigest()

                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO platform.media_assets(
                               asset_key,category,content_type,content_bytes,sha256,size_bytes,
                               original_filename,created_by,active,metadata
                           ) VALUES (%s,'TEST_PLACEHOLDER',%s,%s,%s,%s,%s,%s,true,%s::jsonb)
                           ON CONFLICT(asset_key) DO UPDATE SET
                               active=true, updated_at=now(), metadata=EXCLUDED.metadata""",
                        (
                            asset_key,
                            ctype,
                            data,
                            sha,
                            len(data),
                            f"{row['entity_type']}_{row['code']}{ext_for(ctype)}"[:255],
                            args.actor,
                            json.dumps({"test_seed": True, "source_url": url, "source": row["source"], "license": row["license"]}),
                        ),
                    )
                    result = bind_primary(cur, row, asset_key, args.actor, args.force)
                conn.commit()
                stats[result] += 1
                if idx == 1 or idx % 25 == 0 or idx == len(rows):
                    print(f"[{idx}/{len(rows)}] bound={stats['BOUND']} skipped={stats['SKIP_EXISTS']} downloads={len(cache)}")
            except Exception as e:
                conn.rollback()
                stats["ERROR"] += 1
                print(f"ERROR {row['entity_type']} {row['code']}: {e}", file=sys.stderr)

    print("\nDONE")
    print(dict(stats))
    print("Unique images downloaded:", len(cache))
    print("Tip: run check_test_media.py next.")
    return 1 if stats["ERROR"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
