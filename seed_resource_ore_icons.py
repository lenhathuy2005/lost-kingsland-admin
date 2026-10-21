#!/usr/bin/env python3
"""Lost Kingsland V7.1 resource + equipment-ore icon seeder.

Creates lightweight UI/emote-style demo icons from the Game-icons.net PNG archive.
Runtime never hotlinks the source: rendered WebP bytes are stored in PostgreSQL shared media.

Targets:
- 11 core economy assets: GOLD, GEMS, JADE, WOOD, ORE, FOOD, ESSENCE,
  SKILL_POINT, CLAN_MARKS, SEASON_TOKEN, BUILD_SPEEDUP_MINUTE.
- 90 equipment crafting ores: 9 target slots x 10 rarities, including PET.

Game-icons.net icons are CC BY 3.0; retain attribution if placeholders ship in a public build.
"""
from __future__ import annotations
import argparse, hashlib, io, json, os, re, sys, unicodedata, urllib.request, zipfile
from pathlib import Path
from collections import Counter

try:
    import psycopg
except Exception:
    print('Missing psycopg. Run Admin setup first.', file=sys.stderr); raise
try:
    from PIL import Image, ImageDraw, ImageFilter
except Exception:
    print('Missing Pillow. Run Admin setup first.', file=sys.stderr); raise

ROOT=Path(__file__).resolve().parent
CACHE=ROOT/'data'/'game_icons_cache'
ARCHIVE=CACHE/'game-icons.net.png.zip'
EXTRACT=CACHE/'png'
ARCHIVE_URL='https://game-icons.net/archives/ffffff/transparent/game-icons.net.png.zip'
RARITIES=['COMMON','UNCOMMON','RARE','EPIC','LEGENDARY','MYTHIC','ANCIENT','DIVINE','RELIC','GOD']
RARITY_COLOR={
 'COMMON':'#9ca3af','UNCOMMON':'#4ade80','RARE':'#3b82f6','EPIC':'#a855f7','LEGENDARY':'#f59e0b',
 'MYTHIC':'#ef3d7d','ANCIENT':'#dc5b38','DIVINE':'#f5e06b','RELIC':'#22d3ee','GOD':'#e879f9'}
SLOTS=['HELM','CHEST','SHOULDER','AMULET','BOOTS','RING','OFF_HAND','WEAPON','PET']
SLOT_LABEL={'HELM':'MŨ','CHEST':'GIÁP','SHOULDER':'VAI','AMULET':'PHÙ','BOOTS':'GIÀY','RING':'NHẪN','OFF_HAND':'PHÁP BẢO','WEAPON':'VŨ KHÍ','PET':'LINH THÚ'}
SLOT_TERMS={
 'HELM':['helmet','helm','crown','barbute','visored'],
 'CHEST':['chest armor','breastplate','plastron','armor'],
 'SHOULDER':['shoulder armor','pauldron','shoulder scales'],
 'AMULET':['amulet','pendant','necklace','talisman','gem pendant'],
 'BOOTS':['boots','steeltoe boots','walking boot','leather boot'],
 'RING':['ring','diamond ring','signet','jewellery'],
 'OFF_HAND':['shield','orb','talisman','scroll','book','mirror'],
 'WEAPON':['sword','blade','spear','axe','katana','dagger'],
 'PET':['pawprint','animal','wolf head','fox head','dragon head','beast eye']}
CORE={
 'GOLD':('Vàng',['shiny purse','coins','gold bar'],'#f4c542'),
 'GEMS':('Gem',['gems','gem','crystal cluster'],'#60d5ff'),
 'JADE':('Ngọc',['emerald','cut diamond','gem pendant'],'#55e6a5'),
 'WOOD':('Gỗ',['log','wood pile','wood'],'#b87542'),
 'ORE':('Quặng',['ore','rock','mineral'],'#9aa4ad'),
 'FOOD':('Lương thực',['wheat','grain','food'],'#e7c568'),
 'ESSENCE':('Tinh hoa',['concentration orb','orb','energy'],'#35d6c1'),
 'SKILL_POINT':('Điểm kỹ năng',['upgrade','skills','star formation'],'#b68cff'),
 'CLAN_MARKS':('Dấu ấn Clan',['shield','crest','badge'],'#ef9d4d'),
 'SEASON_TOKEN':('Token Mùa',['token','medal','coin'],'#e56ddb'),
 'BUILD_SPEEDUP_MINUTE':('Tăng tốc xây dựng',['stopwatch','time trap','hourglass'],'#ff9f43')}
# Each rarity gets a different ore/mineral silhouette family; slot overlay makes the target immediately readable.
ORE_TERMS={
 'COMMON':['ore','rock','stone pile'],
 'UNCOMMON':['crystal growth','crystal cluster','mineral'],
 'RARE':['crystal shine','gem chain','crystal ball'],
 'EPIC':['crystal bars','crystal wand','gem pendant'],
 'LEGENDARY':['gold bar','gold nugget','diamond'],
 'MYTHIC':['crystal eye','crystal shrine','crystalize'],
 'ANCIENT':['stone tablet','rune stone','rock'],
 'DIVINE':['star formation','sun radiations','holy symbol'],
 'RELIC':['relic blade','ancient columns','stone bust'],
 'GOD':['vortex','orbital','cosmic egg']}

def load_env(p:Path):
    d={}
    if p.exists():
        for line in p.read_text('utf-8').splitlines():
            s=line.strip()
            if s and not s.startswith('#') and '=' in s:
                k,v=s.split('=',1); d[k.strip()]=v.strip().strip('"').strip("'")
    return d

def db_url(cli=None):
    if cli:return cli
    if os.getenv('DATABASE_URL'):return os.environ['DATABASE_URL']
    for p in [Path.cwd()/'.env',ROOT/'.env']:
        v=load_env(p).get('DATABASE_URL')
        if v:return v
    raise SystemExit('DATABASE_URL not found. Run from the Admin folder or pass --db-url.')

def norm(s):
    s=str(s).replace('Đ','D').replace('đ','d')
    s=''.join(c for c in unicodedata.normalize('NFD',s) if unicodedata.category(c)!='Mn').lower()
    return re.sub(r'[^a-z0-9]+',' ',s).strip()

def toks(s): return {x for x in norm(s).split() if len(x)>1}

def download_archive():
    CACHE.mkdir(parents=True,exist_ok=True)
    if ARCHIVE.exists() and ARCHIVE.stat().st_size>5_000_000:return
    print('Downloading Game-icons.net PNG archive (~30 MB, one time)...')
    req=urllib.request.Request(ARCHIVE_URL,headers={'User-Agent':'Lost-Kingsland-Admin/7.1'})
    tmp=ARCHIVE.with_suffix('.part')
    with urllib.request.urlopen(req,timeout=120) as r, open(tmp,'wb') as f:
        while True:
            b=r.read(1024*512)
            if not b:break
            f.write(b)
    tmp.replace(ARCHIVE)

def files():
    marker=EXTRACT/'.complete'
    if not marker.exists():
        import shutil
        if EXTRACT.exists():shutil.rmtree(EXTRACT)
        EXTRACT.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(ARCHIVE) as z:z.extractall(EXTRACT)
        marker.write_text('ok','utf-8')
    out=[p for p in EXTRACT.rglob('*.png') if p.stat().st_size>100]
    if len(out)<1000:raise RuntimeError(f'Icon archive incomplete: {len(out)} PNG')
    return out

def rec(p):
    rel=str(p.relative_to(EXTRACT)).replace('\\','/')
    return {'p':p,'rel':rel,'text':norm(p.stem+' '+rel),'tokens':toks(p.stem+' '+rel)}

def score(r,terms,salt=''):
    sc=0.0
    for i,t in enumerate(terms):
        nt=norm(t); ts=toks(nt)
        if nt and nt in r['text']:sc+=30-i
        sc+=7*len(ts & r['tokens'])
    sc+=(int(hashlib.sha1((salt+r['rel']).encode()).hexdigest()[:6],16)%1000)/1000
    return sc

def pick(records,terms,used=None,salt=''):
    used=used or set(); pool=[r for r in records if r['rel'] not in used] or records
    return max(pool,key=lambda r:score(r,terms,salt))

def rgb(h): h=h.lstrip('#'); return tuple(int(h[i:i+2],16) for i in (0,2,4))

def mask_icon(source:Path,target=150):
    im=Image.open(source).convert('RGBA'); a=im.getchannel('A'); box=a.getbbox()
    if box: im=im.crop(box); a=im.getchannel('A')
    s=min(target/im.width,target/im.height); im=im.resize((max(1,int(im.width*s)),max(1,int(im.height*s))),Image.Resampling.LANCZOS)
    return im.getchannel('A')

def canvas(accent,size=256):
    c=Image.new('RGBA',(size,size),(5,12,19,255)); px=c.load(); ar,ag,ab=rgb(accent)
    for y in range(size):
        t=y/(size-1)
        for x in range(size):
            dx=(x-size*.5)/(size*.7); dy=(y-size*.42)/(size*.72); glow=max(0,1-(dx*dx+dy*dy))
            px[x,y]=(int(6+ar*.035*glow),int(14+ag*.045*glow),int(22+ab*.055*glow),255)
    return c

def place_mask(c,mask,xy,color,glow=True):
    x,y=xy
    if glow:
        g=Image.new('RGBA',mask.size,(*color,0)); g.putalpha(mask.filter(ImageFilter.GaussianBlur(8)))
        c.alpha_composite(g,(x,y))
    layer=Image.new('RGBA',mask.size,(*color,255)); layer.putalpha(mask); c.alpha_composite(layer,(x,y))

def render_core(source,accent):
    c=canvas(accent); a=mask_icon(source,172); x=(256-a.width)//2;y=(256-a.height)//2
    place_mask(c,a,(x,y),rgb(accent),True)
    d=ImageDraw.Draw(c); d.rounded_rectangle((7,7,248,248),radius=25,outline=(*rgb(accent),180),width=4)
    out=io.BytesIO();c.convert('RGB').save(out,'WEBP',quality=88,method=6);return out.getvalue()

def render_ore(ore_source,slot_source,rarity,slot):
    accent=RARITY_COLOR[rarity]; c=canvas(accent); rc=rgb(accent)
    ore=mask_icon(ore_source,175); ox=(256-ore.width)//2;oy=36+(165-ore.height)//2
    place_mask(c,ore,(ox,oy),rc,True)
    # slot medallion at lower right: slot-specific identity, ore stays the main object.
    d=ImageDraw.Draw(c); d.ellipse((156,151,239,234),fill=(5,13,20,235),outline=(*rc,220),width=3)
    sm=mask_icon(slot_source,54); sx=197-sm.width//2; sy=192-sm.height//2
    place_mask(c,sm,(sx,sy),(236,242,246),False)
    d.rounded_rectangle((7,7,248,248),radius=25,outline=(*rc,205),width=4)
    # tiny rarity dots, no text
    n=min(5,1+(RARITIES.index(rarity)//2)); start=20
    for i in range(n): d.ellipse((start+i*13,229,start+7+i*13,236),fill=(*rc,230))
    out=io.BytesIO();c.convert('RGB').save(out,'WEBP',quality=88,method=6);return out.getvalue()

def write_asset(cur,code,data,category,source_meta,actor,force):
    sha=hashlib.sha256(data).hexdigest(); key=f'demo/v71/{category.lower()}/{code.lower()}/{sha[:20]}.webp'
    if not force:
        cur.execute("SELECT asset_key FROM platform.entity_media_links WHERE entity_type='ECONOMY_ASSET' AND entity_id=%s AND is_primary=true LIMIT 1",(code,))
        r=cur.fetchone()
        if r:return False,r[0]
    meta={'demo_seed':'7.1','source':'Game-icons.net','license':'CC BY 3.0',**source_meta}
    cur.execute("""INSERT INTO platform.media_assets(asset_key,category,content_type,content_bytes,sha256,size_bytes,original_filename,created_by,active,metadata)
                   VALUES(%s,%s,'image/webp',%s,%s,%s,%s,%s,true,%s::jsonb)
                   ON CONFLICT(asset_key) DO UPDATE SET active=true,updated_at=now(),metadata=EXCLUDED.metadata""",
                (key,category,data,sha,len(data),f'{code}.webp',actor,json.dumps(meta)))
    cur.execute("UPDATE platform.entity_media_links SET is_primary=false,media_role=CASE WHEN media_role='PRIMARY' THEN 'GALLERY' ELSE media_role END WHERE entity_type='ECONOMY_ASSET' AND entity_id=%s AND is_primary=true",(code,))
    cur.execute("""INSERT INTO platform.entity_media_links(entity_type,entity_id,asset_key,media_role,sort_order,is_primary,created_by,metadata)
                   VALUES('ECONOMY_ASSET',%s,%s,'PRIMARY',0,true,%s,%s::jsonb)
                   ON CONFLICT(entity_type,entity_id,asset_key) DO UPDATE SET media_role='PRIMARY',sort_order=0,is_primary=true,metadata=EXCLUDED.metadata""",
                (code,key,actor,json.dumps({'demo_seed':'7.1'})))
    cur.execute("UPDATE economy.asset_defs SET metadata=jsonb_set(COALESCE(metadata,'{}'::jsonb),'{image_asset_key}',to_jsonb(%s::text),true) WHERE code=%s",(key,code))
    return True,key

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--db-url'); ap.add_argument('--apply',action='store_true'); ap.add_argument('--force',action='store_true'); ap.add_argument('--core-only',action='store_true'); ap.add_argument('--ores-only',action='store_true'); ap.add_argument('--actor',default='Viet-ResourceDemo')
    a=ap.parse_args()
    if not a.apply:
        print('Plan: 11 core resource icons + 90 equipment-ore icons (including PET). Add --apply to write PostgreSQL.'); return 0
    download_archive(); rs=[rec(p) for p in files()]; print('Icon archive indexed:',len(rs))
    used=set(); core_choices={}
    for code,(_,terms,_) in CORE.items():
        r=pick(rs,terms,used,code);used.add(r['rel']);core_choices[code]=r
    ore_choices={}
    for rarity in RARITIES:
        r=pick(rs,ORE_TERMS[rarity],used,'ORE_'+rarity);used.add(r['rel']);ore_choices[rarity]=r
    slot_choices={}
    for slot in SLOTS:
        r=pick(rs,SLOT_TERMS[slot],used,'SLOT_'+slot);used.add(r['rel']);slot_choices[slot]=r
    stats=Counter(); url=db_url(a.db_url)
    with psycopg.connect(url) as conn:
        if not a.ores_only:
            for code,(name,terms,accent) in CORE.items():
                data=render_core(core_choices[code]['p'],accent)
                with conn.cursor() as cur:
                    ok,key=write_asset(cur,code,data,'DEMO_RESOURCE_ICON',{'source_icon':core_choices[code]['rel'],'display_name_vi':name},a.actor,a.force)
                conn.commit();stats['core_bound' if ok else 'core_skipped']+=1
        if not a.core_only:
            for rarity in RARITIES:
                for slot in SLOTS:
                    code=f'ORE_{slot}_{rarity}'
                    data=render_ore(ore_choices[rarity]['p'],slot_choices[slot]['p'],rarity,slot)
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1 FROM economy.asset_defs WHERE code=%s",(code,))
                        if not cur.fetchone(): raise RuntimeError(f'{code} missing. Run sql/80_v70_equipment_ore_materials.sql first.')
                        ok,key=write_asset(cur,code,data,'DEMO_CRAFT_ORE',{'ore_source_icon':ore_choices[rarity]['rel'],'slot_source_icon':slot_choices[slot]['rel'],'rarity':rarity,'target_slot':slot},a.actor,a.force)
                    conn.commit();stats['ore_bound' if ok else 'ore_skipped']+=1
    print('DONE',dict(stats)); print('Runtime uses PostgreSQL shared media, not web hotlinks.'); return 0
if __name__=='__main__': raise SystemExit(main())
