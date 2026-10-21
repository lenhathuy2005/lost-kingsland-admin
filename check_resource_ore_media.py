#!/usr/bin/env python3
import os,sys,json,urllib.request
from pathlib import Path
try: import psycopg
except: raise SystemExit('Missing psycopg')
ROOT=Path(__file__).resolve().parent
for p in [Path.cwd()/'.env',ROOT/'.env']:
 if p.exists():
  for ln in p.read_text('utf-8').splitlines():
   if '=' in ln and not ln.strip().startswith('#'):
    k,v=ln.split('=',1);os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))
url=os.getenv('DATABASE_URL');
if not url: raise SystemExit('DATABASE_URL missing')
with psycopg.connect(url) as c:
 with c.cursor() as cur:
  cur.execute("SELECT count(*) FROM economy.asset_defs WHERE metadata->>'material_family'='EQUIPMENT_ORE'"); total=cur.fetchone()[0]
  cur.execute("SELECT count(DISTINCT l.asset_key) FROM platform.entity_media_links l JOIN economy.asset_defs a ON a.code=l.entity_id WHERE l.entity_type='ECONOMY_ASSET' AND l.is_primary=true AND a.metadata->>'material_family'='EQUIPMENT_ORE'"); unique=cur.fetchone()[0]
  cur.execute("SELECT count(*) FROM platform.entity_media_links WHERE entity_type='ECONOMY_ASSET' AND is_primary=true AND entity_id IN ('GOLD','GEMS','WOOD','ORE','FOOD','ESSENCE','CULTIVATION_QI','SKILL_POINT','CLAN_MARKS','SEASON_TOKEN')"); core=cur.fetchone()[0]
print('CRAFT ORES',total,'definitions /',unique,'unique primary images (expected 90)')
print('CORE RESOURCES',core,'/ 10 primary images')
base='http://127.0.0.1:8787'
for code in ['GOLD','ORE_HELM_COMMON','ORE_PET_COMMON','ORE_WEAPON_GOD']:
 try:
  with urllib.request.urlopen(f'{base}/api/public/assets/{code}/image',timeout=5) as r: print(code,r.status,r.headers.get('content-type'),r.headers.get('content-length'))
 except Exception as e: print(code,'ERR',e)
