from __future__ import annotations
import os, subprocess, sys
from pathlib import Path
import psycopg

ROOT=Path(__file__).resolve().parent

def load_env(path:Path):
    out={}
    if path.exists():
        for raw in path.read_text('utf-8').splitlines():
            s=raw.strip()
            if not s or s.startswith('#') or '=' not in s: continue
            k,v=s.split('=',1); out[k.strip()]=v.strip().strip('"').strip("'")
    return out

def db_url():
    if os.getenv('DATABASE_URL'): return os.environ['DATABASE_URL']
    v=load_env(ROOT/'.env').get('DATABASE_URL')
    if v: return v
    raise SystemExit('DATABASE_URL not found in .env')

def main():
    print('Lost Kingsland V6.5 - SAFE DIVERSE MEDIA REBUILD')
    print('Preserve real/admin-uploaded artwork; replace TEST_PLACEHOLDER only.')
    url=db_url()
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT asset_key FROM platform.media_assets WHERE category='TEST_PLACEHOLDER'")
            keys=[r[0] for r in cur.fetchall()]
            print(f'Old TEST_PLACEHOLDER assets: {len(keys)}')
            if keys:
                cur.execute("UPDATE inventory.item_defs SET image_asset_key=NULL WHERE image_asset_key = ANY(%s)",(keys,)); print('Cleared item keys:',cur.rowcount)
                cur.execute("UPDATE hero.character_defs SET image_asset_key=NULL WHERE image_asset_key = ANY(%s)",(keys,)); print('Cleared character keys:',cur.rowcount)
                cur.execute("DELETE FROM platform.entity_media_links WHERE asset_key = ANY(%s)",(keys,)); print('Deleted placeholder links:',cur.rowcount)
                cur.execute("DELETE FROM platform.media_assets WHERE asset_key = ANY(%s)",(keys,)); print('Deleted placeholder assets:',cur.rowcount)
        conn.commit()
    cmd=[sys.executable,str(ROOT/'seed_diverse_media.py'),'--apply','--actor','Viet-DiverseMedia-V65']
    print('\nStarting diverse semantic seed...')
    print(' '.join(cmd))
    rc=subprocess.call(cmd,cwd=str(ROOT))
    if rc:
        raise SystemExit(rc)
    print('\nDONE. Restart/refresh Admin, then run Check Bot/Web.')
    return 0
if __name__=='__main__': raise SystemExit(main())
