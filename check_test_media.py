#!/usr/bin/env python3
"""Validate shared media bindings and Admin/Bot media endpoints."""
from __future__ import annotations
import argparse, os, sys, urllib.parse, urllib.request
from pathlib import Path
try:
    import psycopg
except ImportError:
    print("Missing psycopg. Run: python -m pip install psycopg[binary]", file=sys.stderr); raise

HERE=Path(__file__).resolve().parent

def load_env(path):
    d={}
    if Path(path).exists():
        for raw in Path(path).read_text(encoding='utf-8').splitlines():
            line=raw.strip()
            if line and not line.startswith('#') and '=' in line:
                k,v=line.split('=',1); d[k.strip()]=v.strip().strip('"').strip("'")
    return d

def db_url(cli):
    if cli: return cli
    if os.getenv('DATABASE_URL'): return os.environ['DATABASE_URL']
    for p in [Path.cwd()/'.env', HERE.parent/'.env']:
        d=load_env(p)
        if d.get('DATABASE_URL'): return d['DATABASE_URL']
    raise SystemExit('DATABASE_URL not found')

def http_ok(url):
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'Lost-Kingsland-Media-Check/1.0'})
        with urllib.request.urlopen(req,timeout=10) as r:
            return r.status, r.headers.get_content_type(), len(r.read(2048))
    except Exception as e:
        return 'ERR', str(e), 0

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--db-url')
    ap.add_argument('--admin-base-url',default='http://127.0.0.1:8787')
    args=ap.parse_args()
    with psycopg.connect(db_url(args.db_url)) as conn, conn.cursor() as cur:
        cur.execute("""SELECT entity_type,count(*) FILTER (WHERE is_primary) AS primary_links,
                              count(DISTINCT asset_key) FILTER (WHERE is_primary) AS unique_assets
                       FROM platform.entity_media_links GROUP BY entity_type ORDER BY entity_type""")
        print('PRIMARY MEDIA COUNTS')
        media_rows=cur.fetchall()
        for row in media_rows:
            ratio=(float(row[2])/float(row[1])*100.0) if row[1] else 0.0
            flag=''
            if row[0]=='ITEM_DEF' and row[1]>=100 and row[2]<max(100,int(row[1]*0.60)): flag='  << LOW DIVERSITY / OLD PLACEHOLDER'
            if row[0]=='EQUIPMENT_SET' and row[1]>=10 and row[2]<max(5,int(row[1]*0.50)): flag='  << LOW DIVERSITY / OLD PLACEHOLDER'
            print(f'  {row[0]:18} links={row[1]:4} unique_assets={row[2]:4} diversity={ratio:5.1f}%{flag}')
        cur.execute("SELECT count(*) FROM platform.media_assets WHERE active=true AND category='TEST_PLACEHOLDER'")
        print('TEST_PLACEHOLDER assets:',cur.fetchone()[0])
        cur.execute("""SELECT code,image_asset_key FROM inventory.item_defs
                       WHERE image_asset_key IS NOT NULL ORDER BY config_version_id DESC,code LIMIT 3""")
        items=cur.fetchall()
        cur.execute("""SELECT code,image_asset_key FROM hero.character_defs
                       WHERE image_asset_key IS NOT NULL ORDER BY config_version_id DESC,code LIMIT 3""")
        chars=cur.fetchall()

    with psycopg.connect(db_url(args.db_url)) as conn, conn.cursor() as cur:
        cur.execute("""SELECT count(*) FROM inventory.item_defs d
                           WHERE d.image_asset_key IS NOT NULL AND d.image_asset_key<>''
                             AND NOT EXISTS (SELECT 1 FROM platform.media_assets a WHERE a.asset_key=d.image_asset_key AND a.active=true)""")
        stale=cur.fetchone()[0]
        print('STALE ITEM image_asset_key -> missing media_assets:',stale)

    print('\nBOT/WEB HTTP CHECK')
    for code,key in items:
        url=f"{args.admin_base_url.rstrip('/')}/api/public/items/{urllib.parse.quote(code)}/image"
        print(' ITEM',code,http_ok(url),url)
    for code,key in chars:
        url=f"{args.admin_base_url.rstrip('/')}/api/public/media/{urllib.parse.quote(key,safe='/')}"
        print(' CHAR',code,http_ok(url),url)

if __name__=='__main__': main()
