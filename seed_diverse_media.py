#!/usr/bin/env python3
"""Lost Kingsland V6.3 semantic diverse media seeder.

Purpose
-------
Create a *diverse* playtest media set from the complete Game-icons.net PNG archive.
Instead of mapping one helmet silhouette to an entire family, this script:

1. downloads the official white-on-transparent PNG archive once (~30 MB),
2. indexes >4,000 icon filenames,
3. matches every Lost Kingsland entity by slot + Vietnamese name semantics + rarity,
4. avoids reusing a silhouette until necessary,
5. colorises/composites the source into a dark Lost-Kingsland-style 512x512 WebP,
6. stores the bytes in platform.media_assets and binds PRIMARY media links.

The source archive is Game-icons.net, CC BY 3.0. This is intended for local/playtest
placeholder use; keep attribution if these assets are retained in a shipped build.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.request
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

try:
    import psycopg
except ImportError:
    print("Missing psycopg. Run the Admin setup first.", file=sys.stderr)
    raise

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:
    print("Missing Pillow. Run the Admin setup first.", file=sys.stderr)
    raise

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "media_seed_urls.csv"
CACHE_DIR = ROOT / "data" / "game_icons_cache"
ARCHIVE_PATH = CACHE_DIR / "game-icons.net.png.zip"
EXTRACT_DIR = CACHE_DIR / "png"
MANIFEST_PATH = CACHE_DIR / "last_diverse_manifest.csv"
ARCHIVE_URL = "https://game-icons.net/archives/ffffff/transparent/game-icons.net.png.zip"

RARITIES = ["COMMON","UNCOMMON","RARE","EPIC","LEGENDARY","MYTHIC","ANCIENT","DIVINE","RELIC","GOD"]
RARITY_COLOR = {
    "COMMON":"#94a3b8", "UNCOMMON":"#4ade80", "RARE":"#60a5fa", "EPIC":"#a78bfa",
    "LEGENDARY":"#f59e0b", "MYTHIC":"#ec4899", "ANCIENT":"#ef4444", "DIVINE":"#fde047",
    "RELIC":"#22d3ee", "GOD":"#d946ef",
}

SLOT_KEYWORDS = {
    "HELM": ["helmet","helm","crown","hood","hat","head","mask","tiara","samurai","barbute"],
    "CHEST": ["armor","armour","breastplate","chest","cuirass","vest","robe","tunic","body"],
    "BOOTS": ["boot","boots","greave","greaves","foot","feet","shoe","shoes","sabatons","leg"],
    "SHOULDER": ["shoulder","pauldron","pauldrons","armor","cape","wing","mantle"],
    "AMULET": ["amulet","pendant","necklace","jewel","gem","talisman","beads","crystal"],
    "RING": ["ring","rings","jewel","gem","circle","signet","crystal"],
    "OFF_HAND": ["talisman","shield","mirror","orb","book","scroll","rune","relic","wand","crystal"],
    "WEAPON": ["sword","blade","katana","dagger","spear","axe","staff","bow","scythe","weapon"],
    "PET": ["fox","wolf","dragon","turtle","bird","eagle","hawk","cat","tiger","deer","monkey","ape","snake","fish","whale","lion","beast","animal"],
}

# Vietnamese name fragments -> highly preferred visual concepts.
SEMANTIC_RULES = [
    (("linh hồ","hồ"), ["fox","fox-head","animal"]),
    (("huyền quy","quy"), ["turtle","tortoise","shell"]),
    (("huyết lang","lang"), ["wolf","wolf-head"]),
    (("ảnh miêu","miêu"), ["cat","cat-face"]),
    (("lôi ưng","ưng"), ["eagle","hawk","bird"]),
    (("chiến viên","viên"), ["gorilla","ape","monkey"]),
    (("linh lộc","lộc"), ["deer","stag","antlers"]),
    (("tổ long","chân long","long"), ["dragon","dragon-head","wyvern"]),
    (("phượng hoàng","phượng"), ["phoenix","fire-bird","hawk","bird"]),
    (("thôn thiên côn","côn"), ["whale","leviathan","sea-creature"]),
    (("bạch hổ","hổ"), ["tiger","big-cat","claw"]),
    (("kỳ lân",), ["unicorn","horned","horn"]),
    (("kim ô",), ["raven","crow","sun","bird"]),
    (("tu la","ma la"), ["demon","oni","devil","skull"]),
    (("huyết","xích","sát"), ["blood","bleeding","drop","scar","slash"]),
    (("viêm","liệt dương","hỏa"), ["fire","flame","sun","ember"]),
    (("linh mộc","thanh mộc","trúc","mộc"), ["leaf","tree","vine","wood","plant"]),
    (("huyền băng","hàn ngọc","băng","hàn","nguyệt"), ["ice","snowflake","frost","moon"]),
    (("thiên lôi","tử điện","lôi","điện"), ["lightning","thunder","electric","storm"]),
    (("u minh","cửu u","dạ ảnh","dạ"), ["ghost","shadow","spectre","skull","night"]),
    (("hỗn độn","vô cực","quy khư"), ["vortex","void","spiral","chaos","abstract"]),
    (("thiên đạo","cửu thiên","thần tiêu","thánh"), ["angel","halo","wing","holy","star"]),
    (("phá vọng",), ["eye","vision","mirror","crystal-ball"]),
    (("liên kích","liên trảm"), ["crossed-swords","sword-clash","multiple","slash"]),
    (("truy tinh",), ["star","comet","speed"]),
    (("truy phong","liệp phong","thanh phong"), ["wind","wing","speed","feather"]),
    (("bất động","hộ thể","trấn sơn","trấn nhạc"), ["shield","armor","fortress","mountain"]),
    (("hấp huyết","phệ hồn"), ["fang","vampire","skull","soul"]),
    (("táng thiên","khai thiên"), ["meteor","cracked","explosion","cosmic"]),
]

TYPE_KEYWORDS = {
    "CHARACTER_DEF": ["warrior","wizard","mage","monk","ninja","knight","archer","assassin","face","head"],
    "FACTION_BOSS": ["monster","demon","angel","skull","dragon","warrior","king","queen","wing","horn"],
    "ENEMY_DEF": ["knight","monster","enemy","warrior"],
    "COMMANDER_DEF": ["commander","general","warrior","knight","crown"],
    "TECHNIQUE_DEF": ["spell","skill","magic","sword","arrow","shield","shadow"],
    "RACE_DEF": ["human","elf","dragon","shadow","face"],
    "PATH_DEF": ["shield","bow","magic","dagger","sword","hood"],
    "AFFINITY_DEF": ["fire","ice","storm","leaf","sun","shadow","vortex"],
    "REGION_DEF": ["swamp","marsh","forest","mountain","landscape"],
    "CLAN_TECH_DEF": ["upgrade","gear","anvil","hammer","level"],
    "EQUIPMENT_SET": ["armor","shield","sword","crown","gem","relic"],
}

COLOR_RULES = [
    (("huyết","xích","viêm","tu la","sát"), "#ef4444"),
    (("linh mộc","thanh mộc","trúc","mộc","nature"), "#22c55e"),
    (("băng","hàn","nguyệt","frost"), "#60a5fa"),
    (("lôi","điện","storm"), "#38bdf8"),
    (("kim","hoàng","legendary"), "#f59e0b"),
    (("u minh","cửu u","dạ","shadow"), "#8b5cf6"),
    (("hỗn độn","vô cực","quy khư","void"), "#d946ef"),
    (("thiên đạo","cửu thiên","thánh","light"), "#fde047"),
]

STOP = {"the","a","an","of","and","or","icon","icons","game","plain","simple"}


def load_env(path: Path) -> dict[str,str]:
    out={}
    if path.exists():
        for raw in path.read_text("utf-8").splitlines():
            s=raw.strip()
            if s and not s.startswith("#") and "=" in s:
                k,v=s.split("=",1); out[k.strip()]=v.strip().strip('"').strip("'")
    return out


def db_url(cli: str|None) -> str:
    if cli: return cli
    if os.getenv("DATABASE_URL"): return os.environ["DATABASE_URL"]
    for p in [Path.cwd()/".env", ROOT/".env"]:
        v=load_env(p).get("DATABASE_URL")
        if v: return v
    raise SystemExit("DATABASE_URL not found")


def strip_accents(s: str) -> str:
    s=s.replace("Đ","D").replace("đ","d")
    return "".join(c for c in unicodedata.normalize("NFD",s) if unicodedata.category(c)!="Mn")


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+"," ",strip_accents(s).lower()).strip()


def tokens(s: str) -> set[str]:
    return {x for x in norm(s).split() if len(x)>1 and x not in STOP}


def download_archive(force=False) -> None:
    CACHE_DIR.mkdir(parents=True,exist_ok=True)
    if ARCHIVE_PATH.exists() and ARCHIVE_PATH.stat().st_size > 5_000_000 and not force:
        print(f"Archive cache OK: {ARCHIVE_PATH} ({ARCHIVE_PATH.stat().st_size/1024/1024:.1f} MB)")
        return
    print("Downloading complete Game-icons.net PNG archive (~30 MB) once...")
    req=urllib.request.Request(ARCHIVE_URL,headers={"User-Agent":"Lost-Kingsland-Diverse-Media/6.3"})
    tmp=ARCHIVE_PATH.with_suffix(".part")
    with urllib.request.urlopen(req,timeout=120) as r, open(tmp,"wb") as f:
        total=int(r.headers.get("Content-Length") or 0); got=0
        while True:
            chunk=r.read(1024*512)
            if not chunk: break
            f.write(chunk); got+=len(chunk)
            if total and got%(5*1024*1024)<1024*512:
                print(f"  {got/1024/1024:.0f}/{total/1024/1024:.0f} MB")
    tmp.replace(ARCHIVE_PATH)
    print("Archive downloaded.")


def ensure_extracted() -> list[Path]:
    marker=EXTRACT_DIR/".complete"
    if not marker.exists():
        print("Extracting icon archive...")
        if EXTRACT_DIR.exists():
            import shutil; shutil.rmtree(EXTRACT_DIR)
        EXTRACT_DIR.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(ARCHIVE_PATH) as z:
            z.extractall(EXTRACT_DIR)
        marker.write_text("ok","utf-8")
    files=[p for p in EXTRACT_DIR.rglob("*.png") if p.stat().st_size>100]
    if len(files)<1000:
        raise RuntimeError(f"Archive extraction looks incomplete: only {len(files)} PNG files")
    print(f"Indexed PNG silhouettes: {len(files)}")
    return files


def icon_record(p: Path) -> dict:
    stem=norm(p.stem)
    # Some archives use names in parent folders as useful context.
    rel=norm(str(p.relative_to(EXTRACT_DIR)).replace("\\","/"))
    return {"path":p,"stem":stem,"tokens":tokens(stem),"context":tokens(rel),"rel":str(p.relative_to(EXTRACT_DIR)).replace("\\","/")}


def item_slot(code: str) -> str:
    m=re.match(r"EQ_([A-Z_]+?)_C\d+_",code)
    return m.group(1) if m else ""


def rarity_of(code: str, name: str = "") -> str:
    up=(code or "").upper()
    # Match whole underscore-delimited token; avoids COMMON matching UNCOMMON.
    for r in reversed(RARITIES):
        if re.search(rf"(?:^|_){re.escape(r)}(?:_|$)", up):
            return r
    return "COMMON"


def semantic_terms(row: dict[str,str]) -> tuple[list[str],list[str]]:
    et=row["entity_type"].upper(); name=norm(row.get("display_name") or ""); code=norm(row.get("code") or "")
    preferred=[]; mandatory=[]
    if et=="ITEM_DEF":
        slot=item_slot(row.get("code") or "")
        mandatory=SLOT_KEYWORDS.get(slot,[])
        preferred+=mandatory
    else:
        preferred+=TYPE_KEYWORDS.get(et,[])
    hay=" "+name+" "+code+" "
    for needles, terms in SEMANTIC_RULES:
        if any(norm(n) in hay for n in needles): preferred+=terms
    # Explicit non-item semantics.
    if et=="FACTION_BOSS":
        if "angel" in code: preferred += ["angel","wing","halo","holy","sword","crown"]
        if "demon" in code: preferred += ["demon","devil","skull","horn","monster","claw"]
    if et=="AFFINITY_DEF":
        preferred += {
            "flame":["fire","flame"],"frost":["ice","snowflake"],"storm":["lightning","storm"],
            "nature":["leaf","tree"],"light":["sun","halo"],"shadow":["shadow","ghost"],"void":["vortex","spiral"]
        }.get(norm(row.get("code") or ""),[])
    return preferred, mandatory


def choose_color(row: dict[str,str]) -> str:
    hay=norm((row.get("display_name") or "")+" "+(row.get("code") or ""))
    for needles,color in COLOR_RULES:
        if any(norm(n) in hay for n in needles): return color
    return RARITY_COLOR.get(rarity_of(row.get("code") or "",hay),"#38bdf8")


def score_icon(rec: dict, preferred:list[str], mandatory:list[str], salt:str) -> float:
    t=rec["tokens"]|rec["context"]; stem=rec["stem"]
    score=0.0
    for i,k in enumerate(preferred):
        kk=norm(k).replace(" ","-")
        parts=tokens(k)
        if kk.replace("-"," ") in stem: score += 24 - min(i,12)*0.3
        for part in parts:
            if part in t: score += 8
            elif any(part in x or x in part for x in t if len(x)>2): score += 2
    if mandatory:
        mparts={p for k in mandatory for p in tokens(k)}
        if t & mparts: score += 12
        else: score -= 18
    # Stable jitter gives similar entities different top picks without random runs.
    h=int(hashlib.sha1((salt+rec["rel"]).encode()).hexdigest()[:8],16)
    score += (h%1000)/1000.0
    return score


def choose_icons(rows:list[dict[str,str]], files:list[Path]) -> list[tuple[dict[str,str],dict]]:
    records=[icon_record(p) for p in files]
    # Prebuild broad pools to avoid O(664*4180) filtering overhead, while still scoring enough diversity.
    by_slot={}
    for slot,keys in SLOT_KEYWORDS.items():
        kset={p for k in keys for p in tokens(k)}
        pool=[r for r in records if (r["tokens"]|r["context"]) & kset]
        by_slot[slot]=pool if len(pool)>=25 else records
    used=set(); out=[]; reuse=Counter()
    for idx,row in enumerate(rows):
        preferred,mandatory=semantic_terms(row)
        if row["entity_type"].upper()=="ITEM_DEF": pool=by_slot.get(item_slot(row.get("code") or ""),records)
        else: pool=records
        # First pass unused only. For repeated family names this forces silhouette diversity.
        candidates=[r for r in pool if r["rel"] not in used]
        if not candidates: candidates=pool
        best=max(candidates,key=lambda r: score_icon(r,preferred,mandatory,row.get("code") or str(idx)) - reuse[r["rel"]]*20)
        used.add(best["rel"]); reuse[best["rel"]]+=1; out.append((row,best))
    return out


def hexrgb(h:str)->tuple[int,int,int]:
    h=h.lstrip("#"); return tuple(int(h[i:i+2],16) for i in (0,2,4))


def render_icon(source:Path, accent_hex:str, rarity:str, entity_type:str) -> bytes:
    accent=hexrgb(accent_hex)
    size=512
    # Dark blue-black vertical gradient.
    bg=Image.new("RGBA",(size,size),(7,15,24,255)); px=bg.load()
    for y in range(size):
        t=y/(size-1); base=(10-int(4*t),25-int(10*t),38-int(14*t))
        for x in range(size): px[x,y]=(*base,255)
    src=Image.open(source).convert("RGBA")
    # Archive is white on transparent. Alpha is the cleanest mask.
    alpha=src.getchannel("A")
    bbox=alpha.getbbox()
    if bbox: src=src.crop(bbox); alpha=src.getchannel("A")
    target=360 if entity_type=="ITEM_DEF" else 382
    scale=min(target/src.width,target/src.height)
    src=src.resize((max(1,int(src.width*scale)),max(1,int(src.height*scale))),Image.Resampling.LANCZOS)
    alpha=src.getchannel("A")
    x=(size-src.width)//2; y=(size-src.height)//2
    # Glow, then coloured silhouette with a pale highlight.
    glow_layer=Image.new("RGBA",(size,size),(0,0,0,0)); glow=Image.new("RGBA",src.size,(*accent,0)); glow.putalpha(alpha.filter(ImageFilter.GaussianBlur(12)))
    glow_layer.alpha_composite(glow,(x,y)); bg=Image.alpha_composite(bg,glow_layer)
    colored=Image.new("RGBA",src.size,(*accent,255)); colored.putalpha(alpha)
    # subtle white inner highlight by compositing a low-opacity white mask
    hi=Image.new("RGBA",src.size,(245,248,255,55)); hi.putalpha(alpha.point(lambda a:int(a*0.22)))
    colored=Image.alpha_composite(colored,hi)
    bg.alpha_composite(colored,(x,y))
    draw=ImageDraw.Draw(bg)
    rc=hexrgb(RARITY_COLOR.get(rarity,accent_hex))
    # Outer frame and small rarity markers: strong variation without text.
    draw.rounded_rectangle((10,10,501,501),radius=28,outline=(*rc,210),width=5)
    draw.rounded_rectangle((18,18,493,493),radius=24,outline=(*accent,80),width=2)
    tier=max(1,RARITIES.index(rarity)+1 if rarity in RARITIES else 1)
    n=min(5,1+(tier-1)//2)
    gap=18; total=n*10+(n-1)*gap; sx=(size-total)//2
    for i in range(n):
        cx=sx+i*(10+gap)+5
        draw.ellipse((cx-5,480,cx+5,490),fill=(*rc,230))
    out=io.BytesIO(); bg.convert("RGB").save(out,"WEBP",quality=90,method=6)
    return out.getvalue()


def existing_primary(cur,etype,eid):
    cur.execute("SELECT asset_key FROM platform.entity_media_links WHERE entity_type=%s AND entity_id=%s AND is_primary=true LIMIT 1",(etype,eid)); r=cur.fetchone(); return r[0] if r else None


def bind(cur,row,asset_key,actor,force):
    et,eid=row["entity_type"],row["entity_id"]
    cur.execute("UPDATE platform.entity_media_links SET is_primary=false, media_role=CASE WHEN media_role='PRIMARY' THEN 'GALLERY' ELSE media_role END WHERE entity_type=%s AND entity_id=%s AND is_primary=true",(et,eid))
    cur.execute("""INSERT INTO platform.entity_media_links(entity_type,entity_id,asset_key,media_role,sort_order,is_primary,created_by,metadata)
                   VALUES(%s,%s,%s,'PRIMARY',0,true,%s,%s::jsonb)
                   ON CONFLICT(entity_type,entity_id,asset_key) DO UPDATE SET media_role='PRIMARY',sort_order=0,is_primary=true,metadata=EXCLUDED.metadata""",
                (et,eid,asset_key,actor,json.dumps({"test_seed":True,"diverse_seed":"6.3"})))
    if et=="ITEM_DEF": cur.execute("UPDATE inventory.item_defs SET image_asset_key=%s WHERE id=%s::uuid",(asset_key,eid))
    elif et=="CHARACTER_DEF":
        cfg=row.get("config_version_id")
        if cfg: cur.execute("UPDATE hero.character_defs SET image_asset_key=%s WHERE code=%s AND config_version_id=%s",(asset_key,row["code"],int(cfg)))
        else: cur.execute("UPDATE hero.character_defs SET image_asset_key=%s WHERE code=%s",(asset_key,row["code"]))


def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--db-url"); ap.add_argument("--apply",action="store_true"); ap.add_argument("--force",action="store_true")
    ap.add_argument("--type",action="append",dest="types"); ap.add_argument("--limit",type=int,default=0); ap.add_argument("--actor",default="Viet-DiverseMedia")
    ap.add_argument("--redownload",action="store_true")
    args=ap.parse_args()
    rows=list(csv.DictReader(open(CSV_PATH,encoding="utf-8-sig",newline="")))
    if args.types:
        allow={x.upper() for x in args.types}; rows=[r for r in rows if r["entity_type"].upper() in allow]
    if args.limit>0: rows=rows[:args.limit]
    print(f"DIVERSE MEDIA 6.3 • targets={len(rows)} • force={args.force}")
    if not args.apply:
        print("Dry-run. Add --apply to download the archive and write DB."); return 0
    download_archive(args.redownload); files=ensure_extracted(); choices=choose_icons(rows,files)
    print(f"Semantic assignment complete: {len({rec['rel'] for _,rec in choices})} unique silhouettes / {len(choices)} entities")
    CACHE_DIR.mkdir(parents=True,exist_ok=True)
    mf=open(MANIFEST_PATH,"w",encoding="utf-8-sig",newline=""); mw=csv.writer(mf); mw.writerow(["entity_type","code","display_name","source_icon","accent","rarity","status"])
    stats=Counter(); url=db_url(args.db_url)
    with psycopg.connect(url) as conn:
        for i,(row,rec) in enumerate(choices,1):
            try:
                with conn.cursor() as cur:
                    current=existing_primary(cur,row["entity_type"],row["entity_id"])
                    if current and not args.force:
                        stats["SKIP_EXISTS"]+=1; mw.writerow([row["entity_type"],row["code"],row["display_name"],rec["rel"],"",rarity_of(row["code"],row["display_name"]),"SKIP_EXISTS"]); continue
                rarity=rarity_of(row.get("code") or "",row.get("display_name") or "")
                accent=choose_color(row); data=render_icon(rec["path"],accent,rarity,row["entity_type"])
                sha=hashlib.sha256(data).hexdigest(); asset_key=f"test/diverse63/{sha[:32]}.webp"
                meta={"test_seed":True,"diverse_seed":"6.3","source_archive":ARCHIVE_URL,"source_icon":rec["rel"],"source":"Game-icons.net","license":"CC BY 3.0","accent":accent}
                with conn.cursor() as cur:
                    cur.execute("""INSERT INTO platform.media_assets(asset_key,category,content_type,content_bytes,sha256,size_bytes,original_filename,created_by,active,metadata)
                                   VALUES(%s,'TEST_PLACEHOLDER','image/webp',%s,%s,%s,%s,%s,true,%s::jsonb)
                                   ON CONFLICT(asset_key) DO UPDATE SET active=true,updated_at=now(),metadata=EXCLUDED.metadata""",
                                (asset_key,data,sha,len(data),f"{row['code']}.webp"[:255],args.actor,json.dumps(meta)))
                    bind(cur,row,asset_key,args.actor,args.force)
                conn.commit(); stats["BOUND"]+=1; mw.writerow([row["entity_type"],row["code"],row["display_name"],rec["rel"],accent,rarity,"BOUND"])
                if i==1 or i%25==0 or i==len(choices): print(f"[{i}/{len(choices)}] bound={stats['BOUND']} skipped={stats['SKIP_EXISTS']} errors={stats['ERROR']}")
            except Exception as e:
                conn.rollback(); stats["ERROR"]+=1; mw.writerow([row["entity_type"],row["code"],row["display_name"],rec["rel"],"","","ERROR: "+str(e)]); print(f"ERROR {row['code']}: {e}",file=sys.stderr)
    mf.close(); print("DONE",dict(stats)); print("Manifest:",MANIFEST_PATH); return 1 if stats["ERROR"] else 0

if __name__=="__main__": raise SystemExit(main())
