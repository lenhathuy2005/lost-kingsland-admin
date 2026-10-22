#!/usr/bin/env python3
"""Lost Kingsland Admin V6 MegaOps.

Separate from gameplay. Adds a purpose-built operator layer on top of V27:
- Player 360 + audited player-state controls and ledger-safe balance adjustment,
- Gift Code Studio with redemption contract ready for later Discord-bot integration,
- dedicated Character Artwork Studio plus the shared Item/Content media library,
- config CRUD, support, LiveOps, audit and operational read models.

Gameplay remains authoritative. Shared artwork is stored through platform.media_assets /
platform.entity_media_links so Admin, Web and Discord can resolve the same assets.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import zipfile
import secrets
import string
import uuid
import subprocess
import sys
import threading
from collections import Counter
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
SNAPSHOT_PATH = ROOT / "data" / "snapshot.json"
STATIC_DIR = ROOT / "static"


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader so Windows users do not need another package."""
    if not path.exists():
        return
    for raw in path.read_text("utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
WRITE_ENABLED = os.getenv("ADMIN_WRITE_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
ADMIN_ACTOR_DEFAULT = os.getenv("ADMIN_ACTOR", "local-admin")
ADMIN_HOST_CONFIG = os.getenv("ADMIN_HOST", "127.0.0.1").strip() or "127.0.0.1"
ADMIN_LOCAL_OWNER_MODE = os.getenv("ADMIN_LOCAL_OWNER_MODE", "false").lower() in {"1", "true", "yes", "on"}
ADMIN_OWNER_NAME = os.getenv("ADMIN_OWNER_NAME", ADMIN_ACTOR_DEFAULT or "Viet").strip() or "Viet"
ADMIN_ALLOW_REMOTE_NO_AUTH = os.getenv("ADMIN_ALLOW_REMOTE_NO_AUTH", "false").lower() in {"1", "true", "yes", "on"}
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
LOCAL_OWNER_EFFECTIVE = ADMIN_LOCAL_OWNER_MODE and (ADMIN_HOST_CONFIG in _LOCAL_HOSTS or ADMIN_ALLOW_REMOTE_NO_AUTH)
ADMIN_GAMEPLAY_CONFIG = os.getenv("ADMIN_GAMEPLAY_CONFIG", "LK-V4.0-P15-RC-001").strip() or "LK-V4.0-P15-RC-001"
_media_cfg = Path(os.getenv("ADMIN_MEDIA_DIR", str(ROOT / "data" / "media"))).expanduser()
MEDIA_DIR = (_media_cfg if _media_cfg.is_absolute() else (ROOT / _media_cfg)).resolve()
MEDIA_PUBLIC_BASE_URL = os.getenv("MEDIA_PUBLIC_BASE_URL", "").strip().rstrip("/")
MEDIA_BACKEND = os.getenv("ADMIN_MEDIA_BACKEND", "auto").strip().lower() or "auto"
if MEDIA_BACKEND not in {"auto", "database", "filesystem"}:
    MEDIA_BACKEND = "auto"
MAX_IMAGE_MB = max(1, int(os.getenv("ADMIN_MAX_IMAGE_MB", "10")))
MAX_IMAGE_BYTES = MAX_IMAGE_MB * 1024 * 1024
MAX_IMAGE_DIMENSION = max(512, int(os.getenv("ADMIN_MAX_IMAGE_DIMENSION", "4096")))
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

try:
    import psycopg  # type: ignore
    from psycopg.rows import dict_row  # type: ignore
    from psycopg.types.json import Jsonb  # type: ignore
except Exception:  # pragma: no cover
    psycopg = None
    dict_row = None
    Jsonb = None

try:
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover
    Image = None

app = FastAPI(title="Lost Kingsland Admin", version="7.2.0", docs_url="/api/docs", redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")

# One-click test-media tools. The public placeholder sources are mapped in media_seed_urls.csv;
# the actual bytes are cached into PostgreSQL shared media so Bot/Web do not depend on the remote URL later.
TEST_MEDIA_CSV = ROOT / "media_seed_urls.csv"
TEST_MEDIA_SEED_SCRIPT = ROOT / "seed_test_media_from_web.py"
TEST_MEDIA_CHECK_SCRIPT = ROOT / "check_test_media.py"
DIVERSE_MEDIA_SEED_SCRIPT = ROOT / "seed_diverse_media.py"
_TEST_MEDIA_LOCK = threading.Lock()
_TEST_MEDIA_JOB: dict[str, Any] = {
    "status": "idle", "kind": None, "started_at": None, "finished_at": None,
    "returncode": None, "log": [], "command": None,
}


def load_snapshot() -> dict[str, Any]:
    if not SNAPSHOT_PATH.exists():
        raise RuntimeError(f"Missing snapshot: {SNAPSHOT_PATH}")
    return json.loads(SNAPSHOT_PATH.read_text("utf-8"))


SNAPSHOT = load_snapshot()
KNOWN_TABLES = set(SNAPSHOT.get("tables", {}).keys())
IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")

WRITE_PROTECTED_COLUMNS: dict[str, set[str]] = {
    "combat.enemy_bases": {"version", "updated_at"},
    "endgame.stage_defs": {"enemy_profile", "config_version_id"},
    # Artwork is managed only through direct file upload endpoints. Admin users never paste/edit image URLs or asset keys.
    "inventory.item_defs": {"image_asset_key"},
    "title.title_defs": {"emoji_name", "emoji_id", "artwork_asset_key"},
}

# Curated CONFIG/DEFINITION tables that may be CRUD-managed. Runtime player/economy state
# stays read-only in this console unless a purpose-built workflow is added later.
CRUD_RESOURCES: dict[str, dict[str, str]] = {
    "title-defs": {"table": "title.title_defs", "label": "Danh hiệu & Buff", "group": "Character"},
    "enemy-bases": {"table": "combat.enemy_bases", "label": "Base quái & boss", "group": "Quái & Boss"},
    "endgame-stages": {"table": "endgame.stage_defs", "label": "Tầng Tháp / Abyss và thưởng", "group": "Quái & Boss"},
    "raid-bosses": {"table": "cooperative.boss_defs", "label": "Boss Raid / Thế giới / Bang", "group": "Quái & Boss"},
    "raid-phases": {"table": "cooperative.phase_defs", "label": "Giai đoạn boss", "group": "Quái & Boss"},
    "raid-rewards": {"table": "cooperative.reward_tiers", "label": "Thưởng boss", "group": "Quái & Boss"},
    # Inventory / equipment
    "item-defs": {"table": "inventory.item_defs", "label": "Item Definitions", "group": "Inventory"},
    "equipment-sets": {"table": "inventory.equipment_set_defs", "label": "Equipment Sets", "group": "Inventory"},
    "set-bonuses": {"table": "inventory.equipment_set_bonuses", "label": "Set Bonuses", "group": "Inventory"},
    "equipment-stats": {"table": "inventory.equipment_stat_defs", "label": "Equipment Stats", "group": "Inventory"},
    "affix-combos": {"table": "inventory.equipment_affix_combinations", "label": "Affix Combinations", "group": "Inventory"},
    "rarity-policy": {"table": "inventory.rarity_policy", "label": "Rarity Policy", "group": "Inventory"},
    "recipes": {"table": "inventory.recipes", "label": "Recipes", "group": "Inventory"},
    # Character/content
    "races": {"table": "content.race_defs", "label": "Races", "group": "Character"},
    "paths": {"table": "content.path_defs", "label": "Combat Paths", "group": "Character"},
    "affinities": {"table": "content.affinity_defs", "label": "Affinities", "group": "Character"},
    "bloodlines": {"table": "content.bloodline_defs", "label": "Bloodlines", "group": "Character"},
    "realms": {"table": "content.realm_defs", "label": "Cultivation Realms", "group": "Character"},
    "sects": {"table": "content.sect_defs", "label": "Sects", "group": "Character"},
    "professions": {"table": "content.profession_defs", "label": "Professions", "group": "Character"},
    "techniques": {"table": "content.technique_defs", "label": "Techniques / Arts", "group": "Character"},
    "tags": {"table": "content.tags", "label": "Content Tags", "group": "Character"},
    "path-starting-techniques": {"table": "content.path_starting_techniques", "label": "Path Starting Techniques", "group": "Character"},
    "technique-tags": {"table": "content.technique_tag_links", "label": "Technique Tag Links", "group": "Character"},
    "talent-nodes": {"table": "hero.talent_nodes", "label": "Talent Nodes", "group": "Character"},
    "trait-wheel-defs": {"table": "gacha.trait_wheel_defs", "label": "Gacha Chủng tộc / Hệ / Thuộc tính / Thức tỉnh", "group": "Character"},
    "cultivation-activity": {"table": "hero.cultivation_activity_rules", "label": "Tốc độ và thưởng Tu luyện", "group": "Character"},
    "cultivation-ui": {"table": "admin.cultivation_ui_settings", "label": "Giao diện Tu luyện", "group": "Character"},
    "travel-floors": {"table": "hero.travel_floor_defs", "label": "Du lịch nhiều tầng", "group": "World"},
    "quest-defs": {"table": "quest.definitions", "label": "Nhiệm vụ và phần thưởng", "group": "World"},
    # World/progression
    "regions": {"table": "content.region_defs", "label": "Regions", "group": "World"},
    "nodes": {"table": "content.node_defs", "label": "Adventure Nodes", "group": "World"},
    "enemies": {"table": "content.enemy_defs", "label": "Enemies", "group": "World"},
    "floor-profiles": {"table": "content.exploration_floor_profiles", "label": "Exploration Floor Profiles", "group": "World"},
    "monster-rewards": {"table": "content.monster_reward_profiles", "label": "Monster Reward Profiles", "group": "World"},
    "buildings": {"table": "content.building_defs", "label": "Building Definitions", "group": "Progression"},
    "research": {"table": "content.research_defs", "label": "Research Definitions", "group": "Progression"},
    "march-unlocks": {"table": "content.march_slot_unlock_rules", "label": "March Unlock Rules", "group": "Progression"},
    "combat-profiles": {"table": "content.combat_profiles", "label": "Combat Profiles", "group": "Progression"},
    # Social / commander
    "commander-defs": {"table": "commander.commander_defs", "label": "Commander Definitions", "group": "Social"},
    "clan-tech-defs": {"table": "clan.clan_tech_defs", "label": "Clan Tech Definitions", "group": "Social"},
    "clan-building-defs": {"table": "clan.clan_building_defs", "label": "Clan Building Definitions", "group": "Social"},
    "clan-quest-defs": {"table": "clan.clan_quest_defs", "label": "Clan Quest Definitions", "group": "Social"},
    "clan-boss-defs": {"table": "clan.clan_boss_defs", "label": "Clan Boss Definitions", "group": "Social"},
    # Economy / LiveOps
    "assets": {"table": "economy.asset_defs", "label": "Economy Assets", "group": "Economy / LiveOps"},
    "offers": {"table": "commerce.offer_defs", "label": "Commerce Offers", "group": "Economy / LiveOps"},
    "event-defs": {"table": "liveops.event_defs", "label": "Event Definitions", "group": "Economy / LiveOps"},
    "leaderboards": {"table": "liveops.leaderboards", "label": "Leaderboard Definitions", "group": "Economy / LiveOps"},
    "merchant-rotations": {"table": "liveops.merchant_rotations", "label": "Merchant Rotations", "group": "Economy / LiveOps"},
    "feature-flags": {"table": "platform.feature_flags", "label": "Feature Flags", "group": "Economy / LiveOps"},
    "seasons": {"table": "competitive.seasons", "label": "Season Definitions / State", "group": "Economy / LiveOps"},
    "media-settings": {"table": "media.guild_media_settings", "label": "Discord Guild Media Settings", "group": "Discord Ops"},
    # V27 final content / LiveOps foundations
    "characters": {"table": "hero.character_defs", "label": "Secondary Characters (40)", "group": "V27 Final Content"},
    "faction-bosses": {"table": "adventure.faction_boss_catalog", "label": "Faction Boss Catalog (100)", "group": "V27 Final Content"},
    "boss-reward-rules": {"table": "adventure.faction_boss_reward_rules", "label": "Boss Reward Rules", "group": "V27 Final Content"},
    "section-rules": {"table": "content.section_rules", "label": "Section Rules", "group": "V27 Final Content"},
    "adventure-encounter-profiles": {"table": "content.adventure_encounter_profiles", "label": "Adventure Encounter Profiles", "group": "V27 Final Content"},
    "technique-slot-rules": {"table": "content.technique_slot_rules", "label": "Technique Slot Rules", "group": "V27 Final Content"},
    "cultivation-stages": {"table": "hero.cultivation_stage_defs", "label": "Cultivation Stage Definitions", "group": "V27 Final Content"},
    "party-combat-rules": {"table": "hero.party_combat_rules", "label": "Party Combat Rules", "group": "V27 Final Content"},
    "forge-recipes": {"table": "inventory.equipment_forge_recipes", "label": "Forge Recipes", "group": "V27 Final Content"},
    "wheel-rules": {"table": "gacha.wheel_rules", "label": "Lucky Wheel Rules", "group": "V27 Final Content"},
    "arena-rules": {"table": "competitive.arena_rules", "label": "Arena Rules", "group": "V27 Final Content"},
    "market-rules": {"table": "market.playtest_rules", "label": "Market Rules", "group": "V27 Final Content"},
    "clan-rules": {"table": "clan.playtest_rules", "label": "Clan Rules", "group": "V27 Final Content"},
}

# Read-only runtime hubs: these expose more project data without turning raw gameplay state into casual CRUD.
RUNTIME_GROUPS: dict[str, list[str]] = {
    "Hero & Cultivation": [
        "hero.player_heroes", "hero.hero_affinities", "hero.hero_bloodlines", "hero.hero_techniques",
        "hero.technique_loadouts", "hero.breakthrough_attempts", "hero.voice_cultivation_sessions",
    ],
    "Commander": ["commander.player_commanders", "commander.commander_presets", "commander.level_up_events"],
    "Kingdom": ["kingdom.player_kingdoms", "kingdom.kingdom_buildings", "kingdom.construction_jobs", "kingdom.player_research", "kingdom.research_jobs", "kingdom.production_sites"],
    "March & Gathering": ["march.player_march_slots", "march.hunt_loops", "march.hunt_rounds", "march.resource_sites", "march.gather_jobs"],
    "Clan": ["clan.clans", "clan.clan_members", "clan.clan_technology", "clan.clan_buildings", "clan.clan_donations", "clan.clan_help_requests", "clan.clan_bosses", "clan.clan_boss_attempts"],
    "Market": ["market.listings", "market.direct_trade_offers", "market.item_transfers"],
    "Economy": ["economy.ledger_accounts", "economy.ledger_operations", "economy.ledger_entries", "economy.reward_grants", "economy.inventory_operations"],
    "Adventure & Combat": ["adventure.adventure_runs", "adventure.player_exploration_progress", "adventure.encounters", "adventure.player_floor_first_clears", "combat.combat_instances", "combat.combat_settlements", "combat.combat_actions", "combat.combat_events"],
    "Faction Bosses": ["adventure.player_faction_energy", "adventure.pending_alignment_choices", "adventure.player_faction_boss_state", "adventure.faction_boss_attempts", "adventure.faction_boss_mastery", "adventure.faction_boss_activation_events"],
    "Party & Characters": ["hero.player_characters", "hero.character_shard_balances", "hero.player_party_slots", "hero.character_acquisition_events", "hero.character_ascension_events", "inventory.character_equipment_assignments"],
    "Forge & Wheel": ["inventory.forge_operations", "gacha.player_wheel_pity", "gacha.wheel_transactions", "gacha.wheel_draws"],
}


def live_mode() -> bool:
    return bool(DATABASE_URL)


def ensure_live_available() -> None:
    if not DATABASE_URL:
        raise HTTPException(status_code=409, detail="Admin is running in snapshot mode; DATABASE_URL is not configured.")
    if psycopg is None:
        raise HTTPException(status_code=503, detail="Live DB mode needs psycopg. Install requirements-postgres.txt.")


def live_query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    ensure_live_available()
    assert psycopg is not None and dict_row is not None
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description is None:
                return []
            return [dict(r) for r in cur.fetchall()]


def require_write_token(x_admin_token: str | None) -> None:
    if not WRITE_ENABLED:
        raise HTTPException(status_code=403, detail="Live writes are disabled. Set ADMIN_WRITE_ENABLED=true.")
    # Local Owner Mode is intentionally frictionless for the developer machine.
    # It is only effective on loopback by default; remote bind falls back to token auth.
    if LOCAL_OWNER_EFFECTIVE:
        return
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="ADMIN_TOKEN is not configured; refusing write access.")
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid X-Admin-Token.")


def split_table(full: str) -> tuple[str, str]:
    schema, table = full.split(".", 1)
    if not IDENT_RE.fullmatch(schema) or not IDENT_RE.fullmatch(table):
        raise HTTPException(status_code=400, detail="Invalid table identifier.")
    return schema, table


_LIVE_TABLES_CACHE: set[str] | None = None


def available_tables() -> set[str]:
    global _LIVE_TABLES_CACHE
    if not live_mode():
        return set(KNOWN_TABLES)
    if _LIVE_TABLES_CACHE is not None:
        return _LIVE_TABLES_CACHE
    rows = live_query(
        """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema NOT IN ('pg_catalog','information_schema')
        """
    )
    _LIVE_TABLES_CACHE = {f"{r['table_schema']}.{r['table_name']}" for r in rows}
    return _LIVE_TABLES_CACHE


def get_resource(resource: str) -> dict[str, str]:
    cfg = CRUD_RESOURCES.get(resource)
    if not cfg or cfg["table"] not in available_tables():
        raise HTTPException(status_code=404, detail="Unknown or unavailable CRUD resource in the connected V27 database.")
    return cfg


def safe_media_path(asset_key: str) -> Path:
    key = asset_key.replace("\\", "/").lstrip("/")
    if not key or ".." in Path(key).parts:
        raise HTTPException(status_code=400, detail="Invalid media asset key.")
    p = (MEDIA_DIR / key).resolve()
    try:
        p.relative_to(MEDIA_DIR)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid media asset path.")
    return p


_MEDIA_DB_READY_CACHE: bool | None = None


def media_db_table_exists() -> bool:
    global _MEDIA_DB_READY_CACHE
    if _MEDIA_DB_READY_CACHE is not None:
        return _MEDIA_DB_READY_CACHE
    if not live_mode() or psycopg is None:
        _MEDIA_DB_READY_CACHE = False
        return False
    try:
        rows = live_query("SELECT to_regclass('platform.media_assets')::text AS reg")
        _MEDIA_DB_READY_CACHE = bool(rows and rows[0].get("reg"))
    except Exception:
        _MEDIA_DB_READY_CACHE = False
    return _MEDIA_DB_READY_CACHE


def effective_media_backend() -> str:
    if MEDIA_BACKEND == "filesystem":
        return "filesystem"
    if MEDIA_BACKEND == "database":
        return "database" if media_db_table_exists() else "filesystem"
    return "database" if media_db_table_exists() else "filesystem"


def media_url_for_key(asset_key: str | None) -> str | None:
    if not asset_key:
        return None
    encoded = "/".join(quote(part, safe="") for part in asset_key.replace("\\", "/").split("/") if part)
    # The UI never asks an admin to paste a link. In DB-media mode always use the binary resolver.
    # Filesystem mode may optionally expose a configured public base (reverse proxy/CDN).
    if effective_media_backend() == "database":
        return f"/api/public/media/{encoded}"
    if MEDIA_PUBLIC_BASE_URL:
        return f"{MEDIA_PUBLIC_BASE_URL}/{encoded}"
    return f"/api/public/media/{encoded}"


def enrich_media(row: dict[str, Any]) -> dict[str, Any]:
    if "artwork_asset_key" in row:
        row = dict(row)
        row["artwork_url"] = media_url_for_key(row.get("artwork_asset_key"))
    if "image_asset_key" in row:
        row = dict(row)
        row["image_url"] = media_url_for_key(row.get("image_asset_key"))
    return row


def _write_db_media(cur: Any, *, asset_key: str, content: bytes, content_type: str, sha256: str,
                    width: int, height: int, original_filename: str | None, actor: str,
                    category: str = "ITEM_IMAGE") -> None:
    cur.execute(
        """
        INSERT INTO platform.media_assets(
            asset_key, category, content_type, content_bytes, sha256, size_bytes, width, height,
            original_filename, created_by, updated_at, active
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), true)
        ON CONFLICT(asset_key) DO UPDATE SET
            category=EXCLUDED.category, content_type=EXCLUDED.content_type, content_bytes=EXCLUDED.content_bytes, sha256=EXCLUDED.sha256,
            size_bytes=EXCLUDED.size_bytes, width=EXCLUDED.width, height=EXCLUDED.height,
            original_filename=EXCLUDED.original_filename, created_by=EXCLUDED.created_by, updated_at=now(), active=true
        """,
        (asset_key, category, content_type, content, sha256, len(content), width, height, original_filename, actor),
    )


def _read_media_asset(asset_key: str) -> tuple[bytes, str] | None:
    backend = effective_media_backend()
    if backend == "database" and live_mode():
        rows = live_query(
            "SELECT content_bytes, content_type FROM platform.media_assets WHERE asset_key=%s AND active=true",
            (asset_key,),
        )
        if rows:
            raw = rows[0].get("content_bytes")
            if raw is not None:
                return bytes(raw), rows[0].get("content_type") or "application/octet-stream"
    try:
        p = safe_media_path(asset_key)
    except HTTPException:
        return None
    if p.exists() and p.is_file():
        ctype = "image/webp" if p.suffix.lower() == ".webp" else "application/octet-stream"
        return p.read_bytes(), ctype
    return None


def _asset_reference_count(cur: Any, asset_key: str) -> int:
    cur.execute("SELECT count(*) AS count FROM inventory.item_defs WHERE image_asset_key=%s", (asset_key,))
    row = cur.fetchone()
    total = int(row["count"] if isinstance(row, dict) else row[0])
    try:
        cur.execute("SELECT count(*) AS count FROM hero.character_defs WHERE image_asset_key=%s", (asset_key,))
        char_row = cur.fetchone()
        total += int(char_row["count"] if isinstance(char_row, dict) else char_row[0])
    except Exception:
        pass
    try:
        cur.execute("SELECT to_regclass('platform.entity_media_links')::text AS reg")
        reg_row = cur.fetchone()
        if reg_row and (reg_row.get("reg") if isinstance(reg_row, dict) else reg_row[0]):
            cur.execute("SELECT count(*) AS count FROM platform.entity_media_links WHERE asset_key=%s", (asset_key,))
            link_row = cur.fetchone()
            total += int(link_row["count"] if isinstance(link_row, dict) else link_row[0])
    except Exception:
        pass
    return total


def _delete_db_asset_if_orphan(cur: Any, asset_key: str | None) -> None:
    if not asset_key or not media_db_table_exists():
        return
    if _asset_reference_count(cur, asset_key) == 0:
        cur.execute("DELETE FROM platform.media_assets WHERE asset_key=%s", (asset_key,))


def table_metadata(schema: str, table: str) -> dict[str, Any]:
    rows = live_query(
        """
        SELECT c.column_name, c.ordinal_position, c.data_type, c.udt_schema, c.udt_name,
               c.is_nullable, c.column_default, c.is_identity, c.identity_generation,
               c.is_generated, c.generation_expression,
               pg_catalog.format_type(a.atttypid, a.atttypmod) AS formatted_type
        FROM information_schema.columns c
        JOIN pg_catalog.pg_namespace n ON n.nspname=c.table_schema
        JOIN pg_catalog.pg_class cls ON cls.relnamespace=n.oid AND cls.relname=c.table_name
        JOIN pg_catalog.pg_attribute a ON a.attrelid=cls.oid AND a.attname=c.column_name AND a.attnum>0
        WHERE c.table_schema=%s AND c.table_name=%s
        ORDER BY c.ordinal_position
        """,
        (schema, table),
    )
    pk_rows = live_query(
        """
        SELECT kcu.column_name, kcu.ordinal_position
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON kcu.constraint_name=tc.constraint_name AND kcu.table_schema=tc.table_schema AND kcu.table_name=tc.table_name
        WHERE tc.constraint_type='PRIMARY KEY' AND tc.table_schema=%s AND tc.table_name=%s
        ORDER BY kcu.ordinal_position
        """,
        (schema, table),
    )
    pk = [r["column_name"] for r in pk_rows]
    protected = WRITE_PROTECTED_COLUMNS.get(f"{schema}.{table}", set())
    for col in rows:
        col["primary_key"] = col["column_name"] in pk
        col["enum_values"] = []
        if col["data_type"] == "USER-DEFINED":
            enum_rows = live_query(
                """
                SELECT e.enumlabel
                FROM pg_type t
                JOIN pg_enum e ON e.enumtypid=t.oid
                JOIN pg_namespace n ON n.oid=t.typnamespace
                WHERE n.nspname=%s AND t.typname=%s
                ORDER BY e.enumsortorder
                """,
                (col["udt_schema"], col["udt_name"]),
            )
            col["enum_values"] = [r["enumlabel"] for r in enum_rows]
        col["protected"] = col["column_name"] in protected
        col["writable_create"] = (not col["protected"]) and not (col["is_identity"] == "YES" and col["identity_generation"] == "ALWAYS") and col["is_generated"] == "NEVER"
        col["writable_update"] = col["writable_create"] and not col["primary_key"]
    return {"columns": rows, "primary_key": pk}


def snapshot_resource_rows(full: str) -> list[dict[str, Any]]:
    return [enrich_media(dict(r)) for r in SNAPSHOT.get("tables", {}).get(full, [])]


def normalize_payload(payload: dict[str, Any], metadata: dict[str, Any], *, creating: bool) -> dict[str, Any]:
    cols = {c["column_name"]: c for c in metadata["columns"]}
    out: dict[str, Any] = {}
    for key, value in payload.items():
        col = cols.get(key)
        if not col:
            raise HTTPException(status_code=400, detail=f"Unknown column: {key}")
        writable = col["writable_create"] if creating else col["writable_update"]
        if not writable:
            raise HTTPException(status_code=400, detail=f"Column is not writable in this operation: {key}")
        if value == "" and col["is_nullable"] == "YES":
            value = None
        if value is not None and col["data_type"] in {"json", "jsonb"}:
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError as e:
                    raise HTTPException(status_code=400, detail=f"Invalid JSON in {key}: {e.msg}")
            if Jsonb is not None:
                value = Jsonb(value)
        out[key] = value
    return out


def pk_where(metadata: dict[str, Any], pk_payload: dict[str, Any]) -> tuple[str, list[Any]]:
    pk_cols = metadata["primary_key"]
    if not pk_cols:
        raise HTTPException(status_code=409, detail="This table has no primary key; update/delete is disabled.")
    if set(pk_payload) != set(pk_cols):
        raise HTTPException(status_code=400, detail=f"Primary key must contain exactly: {pk_cols}")
    where = " AND ".join(f'"{c}"=%s' for c in pk_cols)
    return where, [pk_payload[c] for c in pk_cols]


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def audit_write(cur: Any, *, actor: str, action: str, object_type: str, object_id: str | None,
                before: dict[str, Any] | None, after: dict[str, Any] | None, reason: str = "ADMIN_CONSOLE") -> None:
    """Audit every config/media mutation. Missing DB permission intentionally blocks the write."""
    if Jsonb is None:
        return
    cur.execute(
        """
        INSERT INTO ops.audit_logs(actor_type, actor_id, action, object_type, object_id, reason_code, before_json, after_json)
        VALUES ('ADMIN', %s, %s, %s, %s, %s, %s, %s)
        """,
        (actor, action, object_type, object_id, reason, Jsonb(_json_safe(before)) if before is not None else None, Jsonb(_json_safe(after)) if after is not None else None),
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/favicon.ico")
def favicon() -> JSONResponse:
    return JSONResponse({}, status_code=204)


def _db_permission_capabilities() -> dict[str, Any]:
    if not live_mode():
        return {"checked": False}
    try:
        rows = live_query("""
            SELECT current_user AS db_user,
                   has_table_privilege(current_user,'economy.ledger_accounts','SELECT') AS ledger_accounts_select,
                   has_table_privilege(current_user,'economy.ledger_accounts','INSERT') AS ledger_accounts_insert,
                   has_table_privilege(current_user,'economy.ledger_accounts','UPDATE') AS ledger_accounts_update,
                   has_table_privilege(current_user,'economy.ledger_operations','INSERT') AS ledger_operations_insert,
                   has_table_privilege(current_user,'economy.ledger_entries','INSERT') AS ledger_entries_insert,
                   has_sequence_privilege(current_user,'economy.ledger_entries_id_seq','USAGE') AS ledger_entries_sequence_usage,
                   has_table_privilege(current_user,'hero.character_defs','SELECT') AS character_defs_select,
                   has_table_privilege(current_user,'hero.character_defs','UPDATE') AS character_defs_update
        """)
        row = rows[0] if rows else {}
        row["checked"] = True
        row["player_balance_ready"] = all(bool(row.get(k)) for k in (
            "ledger_accounts_select", "ledger_accounts_insert", "ledger_accounts_update",
            "ledger_operations_insert", "ledger_entries_insert", "ledger_entries_sequence_usage"
        ))
        row["character_art_ready"] = bool(row.get("character_defs_select")) and bool(row.get("character_defs_update"))
        return row
    except Exception as exc:
        return {"checked": False, "error": type(exc).__name__}


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "7.2.0",
        "mode": "live" if live_mode() else "snapshot",
        "gameplay_config": ADMIN_GAMEPLAY_CONFIG,
        "write_enabled": WRITE_ENABLED,
        "auth_mode": "local-owner" if LOCAL_OWNER_EFFECTIVE else "token",
        "auth_required": not LOCAL_OWNER_EFFECTIVE,
        "admin_account": ADMIN_OWNER_NAME if LOCAL_OWNER_EFFECTIVE else None,
        "media_backend": effective_media_backend(),
        "media_dir": str(MEDIA_DIR),
        "media_public_base_url": MEDIA_PUBLIC_BASE_URL or None,
        "media_db_ready": media_db_table_exists(),
        "db_permissions": _db_permission_capabilities(),
    }


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    source_meta = SNAPSHOT.get("meta", {})
    return {
        "app": "Lost Kingsland Admin",
        "version": "7.2.0",
        "mode": "live" if live_mode() else "snapshot",
        "gameplay_config": ADMIN_GAMEPLAY_CONFIG,
        "write_enabled": WRITE_ENABLED and live_mode(),
        "auth_mode": "local-owner" if LOCAL_OWNER_EFFECTIVE else "token",
        "auth_required": not LOCAL_OWNER_EFFECTIVE,
        "admin_account": ADMIN_OWNER_NAME if LOCAL_OWNER_EFFECTIVE else None,
        "source_dump": source_meta.get("source_file"),
        "dump_started_at": source_meta.get("dump_started_at"),
        "table_count": source_meta.get("table_count"),
        "snapshot_row_count": source_meta.get("row_count"),
        "crud_resource_count": sum(1 for r in CRUD_RESOURCES.values() if r["table"] in available_tables()),
        "media_base_url": MEDIA_PUBLIC_BASE_URL or "/api/public/media",
        "media_backend": effective_media_backend(),
        "media_db_ready": media_db_table_exists(),
        "max_image_mb": MAX_IMAGE_MB,
        "db_permissions": _db_permission_capabilities(),
    }


@app.get("/api/discord-profile")
def discord_profile(locale: str = Query("vi-VN", pattern=r"^(vi-VN|en-US)$")) -> dict[str, Any]:
    rows = live_query("SELECT * FROM platform.discord_profile_presentations WHERE locale=%s", (locale,))
    if not rows:
        raise HTTPException(status_code=404, detail="Chưa có cấu hình hồ sơ Discord cho ngôn ngữ này.")
    return rows[0]


@app.patch("/api/discord-profile")
def update_discord_profile(payload: dict[str, Any], locale: str = Query("vi-VN", pattern=r"^(vi-VN|en-US)$"),
                           x_admin_token: str | None = Header(default=None),
                           x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available(); require_write_token(x_admin_token)
    text_fields = {
        "card_title": 96, "intro_text": 256, "identity_heading": 64, "progression_heading": 64,
        "combat_heading": 64, "assets_heading": 64, "race_label": 48, "path_label": 48,
        "affinity_label": 48, "realm_label": 48, "stage_label": 48, "level_label": 48,
        "xp_label": 48, "power_label": 48, "vitality_label": 48, "martial_label": 48,
        "mystic_label": 48, "armor_label": 48, "ward_label": 48, "speed_label": 48,
        "crit_label": 48, "penetration_label": 48, "footer_text": 128, "divider_text": 96,
        "cultivation_qi_label": 48, "cultivation_progress_label": 48, "clan_label": 48,
        "clan_role_label": 48, "equipment_heading": 64, "empty_equipment_label": 64,
    }
    values: dict[str, Any] = {}
    for key, maximum in text_fields.items():
        if key in payload:
            value = str(payload[key]).strip()
            if not value or len(value) > maximum:
                raise HTTPException(status_code=400, detail=f"{key} phải có từ 1 đến {maximum} ký tự.")
            values[key] = value
    if "show_assets" in payload:
        if not isinstance(payload["show_assets"], bool):
            raise HTTPException(status_code=400, detail="show_assets phải là bật hoặc tắt.")
        values["show_assets"] = payload["show_assets"]
    if "show_equipment" in payload:
        if not isinstance(payload["show_equipment"], bool):
            raise HTTPException(status_code=400, detail="show_equipment phải là bật hoặc tắt.")
        values["show_equipment"] = payload["show_equipment"]
    if not values:
        raise HTTPException(status_code=400, detail="Không có nội dung cần cập nhật.")
    actor = x_admin_actor or ADMIN_ACTOR_DEFAULT
    assert psycopg is not None and dict_row is not None
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM platform.discord_profile_presentations WHERE locale=%s FOR UPDATE", (locale,))
            old = cur.fetchone()
            if old is None:
                raise HTTPException(status_code=404, detail="Không tìm thấy cấu hình hồ sơ.")
            values["updated_at"] = datetime.now(timezone.utc); values["updated_by"] = actor
            sets = ", ".join(f'"{key}"=%s' for key in values)
            cur.execute(f'UPDATE platform.discord_profile_presentations SET {sets} WHERE locale=%s RETURNING *',
                        tuple(values.values()) + (locale,))
            new = dict(cur.fetchone())
            audit_write(cur, actor=actor, action="UPDATE_PROFILE_PRESENTATION",
                        object_type="platform.discord_profile_presentations", object_id=locale,
                        before=dict(old), after=new)
            conn.commit()
            return new


@app.get("/api/admin-session")
def admin_session() -> dict[str, Any]:
    return {
        "authenticated": True if LOCAL_OWNER_EFFECTIVE else False,
        "account": ADMIN_OWNER_NAME if LOCAL_OWNER_EFFECTIVE else None,
        "role": "OWNER" if LOCAL_OWNER_EFFECTIVE else "TOKEN_ADMIN",
        "auth_mode": "local-owner" if LOCAL_OWNER_EFFECTIVE else "token",
        "write_enabled": WRITE_ENABLED and live_mode(),
        "local_only": LOCAL_OWNER_EFFECTIVE and ADMIN_HOST_CONFIG in _LOCAL_HOSTS,
    }


@app.get("/api/dashboard")
def dashboard() -> dict[str, Any]:
    if not live_mode():
        base = dict(SNAPSHOT["derived"]["dashboard"])
        base["local_media_files"] = sum(1 for p in MEDIA_DIR.rglob("*") if p.is_file() and p.name != ".gitkeep")
        base["media_assets"] = base["local_media_files"]
        base["media_backend"] = effective_media_backend()
        return base
    rows = live_query(
        """
        WITH cfg AS (SELECT id FROM platform.config_versions WHERE version_code=%s)
        SELECT
          (SELECT count(*) FROM identity.players) AS players,
          (SELECT count(*) FROM inventory.item_defs d, cfg WHERE d.config_version_id=cfg.id AND COALESCE(d.catalog_status,'ACTIVE_CANONICAL')='ACTIVE_CANONICAL') AS equipment_defs,
          (SELECT count(*) FROM inventory.item_defs d, cfg WHERE d.config_version_id=cfg.id AND COALESCE(d.catalog_status,'ACTIVE_CANONICAL')='ACTIVE_CANONICAL') AS production_equipment_defs,
          (SELECT count(*) FROM inventory.item_defs d, cfg WHERE d.config_version_id=cfg.id AND COALESCE(d.catalog_status,'ACTIVE_CANONICAL')<>'ACTIVE_CANONICAL') AS sample_equipment_defs,
          (SELECT count(*) FROM inventory.rarity_policy) AS rarities,
          (SELECT count(*) FROM inventory.equipment_set_defs) AS equipment_sets,
          (SELECT count(*) FROM inventory.equipment_set_bonuses) AS set_bonuses,
          (SELECT count(*) FROM inventory.item_instances) AS player_item_instances,
          (SELECT count(*) FROM inventory.item_defs d, cfg WHERE d.config_version_id=cfg.id AND COALESCE(d.catalog_status,'ACTIVE_CANONICAL')='ACTIVE_CANONICAL' AND (d.image_asset_key IS NULL OR d.image_asset_key='')) AS missing_item_images,
          (SELECT count(*) FROM inventory.item_defs d, cfg WHERE d.config_version_id=cfg.id AND COALESCE(d.catalog_status,'ACTIVE_CANONICAL')='ACTIVE_CANONICAL' AND d.image_asset_key IS NOT NULL AND d.image_asset_key<>'') AS items_with_images,
          (SELECT count(*) FROM platform.feature_flags) AS feature_flags,
          (SELECT count(*) FROM platform.feature_flags WHERE enabled) AS feature_flags_enabled,
          (SELECT count(*) FROM ops.abuse_signals) AS abuse_signals
        """,
        (ADMIN_GAMEPLAY_CONFIG,)
    )
    base = rows[0] if rows else {}
    rarity_rows = live_query("""
        SELECT i.rarity::text AS rarity, count(*) AS count
        FROM inventory.item_defs i
        JOIN platform.config_versions cv ON cv.id=i.config_version_id
        JOIN inventory.rarity_policy rp ON rp.rarity=i.rarity
        WHERE cv.version_code=%s AND COALESCE(i.catalog_status,'ACTIVE_CANONICAL')='ACTIVE_CANONICAL'
        GROUP BY i.rarity, rp.power_ordinal ORDER BY rp.power_ordinal
    """, (ADMIN_GAMEPLAY_CONFIG,))
    slot_rows = live_query("""
        SELECT i.equipment_slot::text AS equipment_slot, count(*) AS count
        FROM inventory.item_defs i JOIN platform.config_versions cv ON cv.id=i.config_version_id
        WHERE cv.version_code=%s AND COALESCE(i.catalog_status,'ACTIVE_CANONICAL')='ACTIVE_CANONICAL'
        GROUP BY i.equipment_slot ORDER BY i.equipment_slot
    """, (ADMIN_GAMEPLAY_CONFIG,))
    base["rarity_counts"] = {r["rarity"]: r["count"] for r in rarity_rows}
    base["slot_counts"] = {str(r["equipment_slot"]): r["count"] for r in slot_rows}
    base["local_media_files"] = sum(1 for p in MEDIA_DIR.rglob("*") if p.is_file() and p.name != ".gitkeep")
    if media_db_table_exists():
        m = live_query("SELECT count(*) AS assets, COALESCE(sum(size_bytes),0) AS used_bytes FROM platform.media_assets WHERE active=true")[0]
        base["media_assets"] = m["assets"]
        base["media_used_bytes"] = m["used_bytes"]
    else:
        base["media_assets"] = base["local_media_files"]
        base["media_used_bytes"] = sum(p.stat().st_size for p in MEDIA_DIR.rglob("*") if p.is_file() and p.name != ".gitkeep")
    base["media_backend"] = effective_media_backend()
    base.setdefault("active_events", 0)
    return base


@app.get("/api/players")
def players() -> list[dict[str, Any]]:
    if not live_mode():
        rows = SNAPSHOT.get("derived", {}).get("players", [])
        out=[]
        for r in rows:
            x=dict(r)
            x.setdefault("player_id", x.get("id"))
            x.setdefault("player_name", x.get("display_name"))
            out.append(x)
        return out
    # Direct V27 query: do not depend on optional/legacy admin.v_players shape.
    return live_query(
        """
        SELECT p.id::text AS player_id, p.display_name::text AS player_name, p.account_id::text AS account_id,
               p.account_level, p.account_xp, p.avatar_key, p.active_screen_key, p.tutorial_step,
               p.created_at, p.updated_at, p.version AS player_version,
               a.status AS account_status, a.locale, a.timezone,
               h.id::text AS hero_id, h.name::text AS hero_name, h.level AS hero_level, h.xp AS hero_xp,
               h.race_code, h.path_code, h.realm_code, h.realm_minor_stage, h.cultivation_qi AS cultivation_xp,
               ep.current_floor AS exploration_floor, ep.highest_floor,
               dl.discord_user_id, dl.discord_username
        FROM identity.players p
        JOIN identity.accounts a ON a.id=p.account_id
        LEFT JOIN LATERAL (
          SELECT h0.* FROM hero.player_heroes h0 WHERE h0.player_id=p.id ORDER BY h0.created_at LIMIT 1
        ) h ON true
        LEFT JOIN adventure.player_exploration_progress ep ON ep.player_id=p.id
        LEFT JOIN LATERAL (
          SELECT d.discord_user_id,d.discord_username FROM identity.discord_links d
          WHERE d.account_id=p.account_id AND d.revoked_at IS NULL
          ORDER BY d.is_primary DESC,d.linked_at DESC LIMIT 1
        ) dl ON true
        ORDER BY p.created_at DESC
        """
    )


@app.get("/api/player-items")
def player_items(player_id: str | None = None) -> list[dict[str, Any]]:
    if not live_mode():
        rows = SNAPSHOT["derived"]["player_items"]
        return [enrich_media(dict(r)) for r in rows if player_id is None or str(r.get("owner_player_id") or r.get("player_id")) == str(player_id)]
    if player_id:
        rows = live_query("SELECT * FROM admin.v_player_items WHERE owner_player_id=%s::uuid ORDER BY acquired_at DESC", (player_id,))
    else:
        rows = live_query("SELECT * FROM admin.v_player_items ORDER BY acquired_at DESC LIMIT 1000")
    return [enrich_media(r) for r in rows]



@app.get("/api/players/{player_id}/overview")
def player_overview(player_id: str) -> dict[str, Any]:
    """Wide Player Support read model across core subsystems. No raw runtime mutation is exposed here."""
    if not live_mode():
        tables = SNAPSHOT.get("tables", {})
        def by_player(table: str, col: str = "player_id") -> list[dict[str, Any]]:
            return [enrich_media(dict(r)) for r in tables.get(table, []) if str(r.get(col)) == str(player_id)]
        player = next((dict(r) for r in tables.get("identity.players", []) if str(r.get("id")) == str(player_id)), None)
        hero_rows = by_player("hero.player_heroes")
        hero_ids = {str(r.get("id")) for r in hero_rows}
        return {
            "player": player,
            "heroes": hero_rows,
            "items": [enrich_media(dict(r)) for r in SNAPSHOT["derived"].get("player_items", []) if str(r.get("player_id")) == str(player_id)],
            "commanders": by_player("commander.player_commanders"),
            "kingdoms": by_player("kingdom.player_kingdoms"),
            "marches": by_player("march.player_march_slots"),
            "clan_memberships": by_player("clan.clan_members"),
            "market_listings": [dict(r) for r in tables.get("market.listings", []) if str(r.get("seller_player_id")) == str(player_id) or str(r.get("buyer_player_id")) == str(player_id)],
            "energy": by_player("adventure.energy_balances"),
            "exploration": by_player("adventure.player_exploration_progress"),
            "adventure_runs": by_player("adventure.adventure_runs"),
            "tribulations": [dict(r) for r in tables.get("hero.breakthrough_attempts", []) if str(r.get("player_id")) == str(player_id) or str(r.get("hero_id")) in hero_ids],
            "sanctions": by_player("ops.player_sanctions"),
            "compensations": by_player("ops.compensation_cases"),
            "ledger_accounts": [dict(r) for r in tables.get("economy.ledger_accounts", []) if str(r.get("owner_id")) == str(player_id)],
        }
    # Live read model
    result: dict[str, Any] = {}
    p = live_query("SELECT * FROM identity.players WHERE id=%s::uuid", (player_id,))
    result["player"] = p[0] if p else None
    result["account"] = live_query("SELECT a.* FROM identity.accounts a JOIN identity.players p ON p.account_id=a.id WHERE p.id=%s::uuid", (player_id,))
    result["discord_links"] = live_query("SELECT d.* FROM identity.discord_links d JOIN identity.players p ON p.account_id=d.account_id WHERE p.id=%s::uuid ORDER BY d.is_primary DESC,d.linked_at DESC", (player_id,))
    result["heroes"] = live_query("SELECT * FROM hero.player_heroes WHERE player_id=%s::uuid ORDER BY created_at", (player_id,))
    result["characters"] = live_query("SELECT pc.*, d.display_name_vi, d.rarity::text AS rarity, d.combat_role, d.image_asset_key FROM hero.player_characters pc LEFT JOIN hero.character_defs d ON d.code=pc.character_code AND d.config_version_id=pc.character_config_version_id WHERE pc.player_id=%s::uuid ORDER BY pc.acquired_at DESC", (player_id,))
    result["items"] = [enrich_media(r) for r in live_query("SELECT * FROM admin.v_player_items WHERE owner_player_id=%s::uuid ORDER BY acquired_at DESC", (player_id,))]
    result["commanders"] = live_query("SELECT * FROM commander.player_commanders WHERE player_id=%s::uuid ORDER BY acquired_at NULLS LAST, updated_at", (player_id,))
    result["kingdoms"] = live_query("SELECT * FROM kingdom.player_kingdoms WHERE player_id=%s::uuid", (player_id,))
    result["kingdom_buildings"] = live_query("SELECT kb.* FROM kingdom.kingdom_buildings kb JOIN kingdom.player_kingdoms pk ON pk.id=kb.kingdom_id WHERE pk.player_id=%s::uuid ORDER BY kb.building_code", (player_id,))
    result["kingdom_research"] = live_query("SELECT pr.* FROM kingdom.player_research pr JOIN kingdom.player_kingdoms pk ON pk.id=pr.kingdom_id WHERE pk.player_id=%s::uuid ORDER BY pr.research_code", (player_id,))
    result["production_sites"] = live_query("SELECT ps.* FROM kingdom.production_sites ps JOIN kingdom.player_kingdoms pk ON pk.id=ps.kingdom_id WHERE pk.player_id=%s::uuid ORDER BY ps.resource_code,ps.building_code", (player_id,))
    result["marches"] = live_query("SELECT * FROM march.player_march_slots WHERE player_id=%s::uuid ORDER BY slot_no", (player_id,))
    result["clan_memberships"] = live_query("SELECT cm.*, c.name AS clan_name, c.tag AS clan_tag FROM clan.clan_members cm JOIN clan.clans c ON c.id=cm.clan_id WHERE cm.player_id=%s::uuid", (player_id,))
    result["market_listings"] = live_query("SELECT * FROM market.listings WHERE seller_player_id=%s::uuid OR buyer_player_id=%s::uuid ORDER BY created_at DESC LIMIT 200", (player_id, player_id))
    result["energy"] = live_query("SELECT * FROM adventure.energy_balances WHERE player_id=%s::uuid", (player_id,))
    result["exploration"] = live_query("SELECT * FROM adventure.player_exploration_progress WHERE player_id=%s::uuid", (player_id,))
    result["adventure_runs"] = live_query("SELECT * FROM adventure.adventure_runs WHERE player_id=%s::uuid ORDER BY started_at DESC LIMIT 100", (player_id,))
    result["tribulations"] = live_query("SELECT ba.* FROM hero.breakthrough_attempts ba JOIN hero.player_heroes h ON h.id=ba.hero_id WHERE h.player_id=%s::uuid ORDER BY ba.started_at DESC LIMIT 100", (player_id,))
    result["sanctions"] = live_query("SELECT * FROM ops.player_sanctions WHERE player_id=%s::uuid ORDER BY starts_at DESC", (player_id,))
    result["compensations"] = live_query("SELECT * FROM ops.compensation_cases WHERE player_id=%s::uuid ORDER BY created_at DESC", (player_id,))
    result["ledger_accounts"] = live_query("SELECT * FROM economy.ledger_accounts WHERE owner_scope='PLAYER' AND owner_id=%s::uuid ORDER BY asset_code", (player_id,))
    result["ledger_entries"] = live_query("SELECT le.*, la.asset_code, lo.operation_type, lo.reason_code, lo.source_type, lo.source_id FROM economy.ledger_entries le JOIN economy.ledger_accounts la ON la.id=le.ledger_account_id LEFT JOIN economy.ledger_operations lo ON lo.id=le.operation_id WHERE la.owner_scope='PLAYER' AND la.owner_id=%s::uuid ORDER BY le.created_at DESC LIMIT 200", (player_id,))
    result["inventory_instances"] = live_query("SELECT i.*, d.display_name_vi AS item_name FROM inventory.item_instances i LEFT JOIN inventory.item_defs d ON d.code=i.item_code AND d.config_version_id=i.item_config_version_id WHERE i.owner_player_id=%s::uuid ORDER BY i.acquired_at DESC LIMIT 500", (player_id,))
    return result


@app.get("/api/items")
def items() -> list[dict[str, Any]]:
    if not live_mode():
        raw_by_id = {str(r.get("id")): dict(r) for r in SNAPSHOT["tables"].get("inventory.item_defs", [])}
        out = []
        for view_row in SNAPSHOT["derived"]["item_catalog"]:
            raw = raw_by_id.get(str(view_row.get("item_def_id")), {})
            merged = {**raw, **dict(view_row)}
            out.append(enrich_media(merged))
        return out
    rows = live_query(
        """
        SELECT d.id AS item_def_id, d.code AS item_code, d.display_name_vi AS item_name,
               d.id, d.code, d.config_version_id, d.item_type, d.family_code, d.display_name_vi,
               d.image_asset_key, d.equipment_slot, d.rarity::text AS rarity, d.stackable, d.max_stack,
               d.bind_rule, d.transferable, d.tags, d.base_stats, d.base_effects, d.salvage_rule,
               d.affix_combo_code, d.set_code, d.set_name, d.catalog_status,
               eac.stat_codes AS allowed_stat_combination, cardinality(eac.stat_codes) AS stat_count,
               rp.power_ordinal AS rarity_ordinal, sd.identity_summary AS set_identity,
               (d.set_code IS NOT NULL) AS is_set_piece, cv.version_code AS config_version
        FROM inventory.item_defs d
        JOIN platform.config_versions cv ON cv.id=d.config_version_id
        JOIN inventory.rarity_policy rp ON rp.rarity=d.rarity
        LEFT JOIN inventory.equipment_set_defs sd ON sd.set_code=d.set_code
        LEFT JOIN inventory.equipment_affix_combinations eac
          ON eac.equipment_slot=d.equipment_slot AND eac.combo_code=d.affix_combo_code AND eac.config_version_id=d.config_version_id
        WHERE cv.version_code=%s
          AND COALESCE(d.catalog_status, 'ACTIVE_CANONICAL')='ACTIVE_CANONICAL'
        ORDER BY rp.power_ordinal, d.equipment_slot NULLS LAST, d.affix_combo_code NULLS LAST, d.display_name_vi NULLS LAST, d.code
        """,
        (ADMIN_GAMEPLAY_CONFIG,)
    )
    return [enrich_media(r) for r in rows]


@app.get("/api/sets")
def sets() -> list[dict[str, Any]]:
    if not live_mode():
        return SNAPSHOT["derived"]["equipment_sets"]
    return live_query(
        """
        SELECT sd.set_code, sd.rarity::text AS rarity, rp.power_ordinal AS rarity_ordinal,
               sd.set_name, sd.identity_summary, sd.lore_summary, sd.enabled AS active,
               COALESCE(jsonb_agg(
                 jsonb_build_object(
                   'set_code', b.set_code,
                   'pieces_required', b.pieces_required,
                   'bonus_type', b.bonus_type,
                   'bonus_params', b.bonus_params,
                   'display_text_vi', b.display_text_vi,
                   'design_note', b.design_note,
                   'enabled', b.enabled
                 ) ORDER BY b.pieces_required
               ) FILTER (WHERE b.set_code IS NOT NULL), '[]'::jsonb) AS bonuses
        FROM inventory.equipment_set_defs sd
        JOIN inventory.rarity_policy rp ON rp.rarity=sd.rarity
        LEFT JOIN inventory.equipment_set_bonuses b ON b.set_code=sd.set_code
        GROUP BY sd.set_code, sd.rarity, rp.power_ordinal, sd.set_name, sd.identity_summary, sd.lore_summary, sd.enabled
        ORDER BY rp.power_ordinal, sd.set_name
        """
    )


@app.get("/api/schemas")
def schemas() -> dict[str, Any]:
    if not live_mode():
        return SNAPSHOT["derived"]["schemas"]
    rows = live_query(
        """
        SELECT table_schema AS schema_name, table_name
        FROM information_schema.tables
        WHERE table_schema NOT IN ('pg_catalog','information_schema')
        ORDER BY table_schema, table_name
        """
    )
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(r["schema_name"], []).append({"table": r["table_name"], "row_count": None})
    return out


@app.get("/api/runtime-groups")
def runtime_groups() -> dict[str, list[str]]:
    return {k: [t for t in v if t in available_tables()] for k, v in RUNTIME_GROUPS.items()}


@app.get("/api/table/{schema}/{table}")
def raw_table(schema: str, table: str, limit: int = Query(200, ge=1, le=1000), offset: int = Query(0, ge=0)) -> dict[str, Any]:
    full = f"{schema}.{table}"
    if full not in available_tables() or not IDENT_RE.fullmatch(schema) or not IDENT_RE.fullmatch(table):
        raise HTTPException(status_code=404, detail="Table is not available in the connected Lost Kingsland database.")
    if not live_mode():
        rows = SNAPSHOT["tables"].get(full, [])
        return {"table": full, "total": len(rows), "rows": [enrich_media(dict(r)) for r in rows[offset: offset + limit]], "mode": "snapshot"}
    count = live_query(f'SELECT count(*) AS count FROM "{schema}"."{table}"')[0]["count"]
    rows = live_query(f'SELECT * FROM "{schema}"."{table}" LIMIT %s OFFSET %s', (limit, offset))
    return {"table": full, "total": count, "rows": [enrich_media(r) for r in rows], "mode": "live"}


# -------------------------- Generic config CRUD --------------------------
@app.post("/api/titles/{code}/grant")
def grant_title(code: str, payload: dict[str, Any], x_admin_token: str | None = Header(default=None),
                x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available(); require_write_token(x_admin_token)
    try:
        player_id = uuid.UUID(str(payload.get("player_id", "")))
    except ValueError:
        raise HTTPException(status_code=400, detail="Player ID phải là UUID hợp lệ.")
    actor = x_admin_actor or ADMIN_ACTOR_DEFAULT
    assert psycopg is not None and dict_row is not None
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT code,source_type,active FROM title.title_defs WHERE code=%s", (code,))
            title = cur.fetchone()
            if title is None or not title["active"]:
                raise HTTPException(status_code=404, detail="Danh hiệu không tồn tại hoặc đang tắt.")
            cur.execute("SELECT id FROM identity.players WHERE id=%s", (player_id,))
            if cur.fetchone() is None:
                raise HTTPException(status_code=404, detail="Không tìm thấy Player ID.")
            cur.execute("SELECT * FROM title.player_titles WHERE player_id=%s AND title_code=%s", (player_id, code))
            before = cur.fetchone()
            if before is None:
                cur.execute("INSERT INTO title.player_titles(player_id,title_code,source_type,source_ref) VALUES(%s,%s,'ADMIN',%s) RETURNING *",
                            (player_id, code, actor[:160]))
                after = dict(cur.fetchone())
                audit_write(cur, actor=actor, action="GRANT", object_type="title.player_titles",
                            object_id=f"{player_id}:{code}", before=None, after=after)
            else:
                after = dict(before)
            conn.commit()
            return _json_safe({"title": code, "player_id": str(player_id), "granted": before is None})


@app.get("/api/crud/resources")
def crud_resources() -> list[dict[str, Any]]:
    out = []
    tables = available_tables()
    for key, cfg in CRUD_RESOURCES.items():
        if cfg["table"] not in tables:
            continue
        count = len(SNAPSHOT["tables"].get(cfg["table"], [])) if not live_mode() else None
        out.append({"key": key, **cfg, "row_count": count})
    return out


@app.get("/api/crud/{resource}/schema")
def crud_schema(resource: str) -> dict[str, Any]:
    cfg = get_resource(resource)
    if not live_mode():
        rows = SNAPSHOT["tables"].get(cfg["table"], [])
        fields = list(rows[0].keys()) if rows else []
        return {"resource": resource, "table": cfg["table"], "mode": "snapshot", "primary_key": [], "columns": [{"column_name": f, "data_type": "snapshot", "writable_create": False, "writable_update": False, "primary_key": False, "enum_values": []} for f in fields]}
    schema, table = split_table(cfg["table"])
    m = table_metadata(schema, table)
    if resource == "title-defs":
        m["columns"] = [col for col in m["columns"] if col["column_name"] not in {"emoji_name", "emoji_id"}]
    return {"resource": resource, "table": cfg["table"], "mode": "live", **m}


@app.get("/api/crud/{resource}")
def crud_list(resource: str, limit: int = Query(500, ge=1, le=1000), offset: int = Query(0, ge=0)) -> dict[str, Any]:
    cfg = get_resource(resource)
    schema, table = split_table(cfg["table"])
    if not live_mode():
        rows = snapshot_resource_rows(cfg["table"])
        return {"resource": resource, "table": cfg["table"], "total": len(rows), "rows": rows[offset: offset + limit], "mode": "snapshot"}
    condition = " WHERE config_version_id=(SELECT id FROM platform.config_versions WHERE version_code='LK-V4.0-P20-RC-002')" if resource == "endgame-stages" else ""
    ordering = " ORDER BY mode,stage_no,chamber_no" if resource == "endgame-stages" else " ORDER BY family,enemy_code" if resource == "enemy-bases" else ""
    total = live_query(f'SELECT count(*) AS count FROM "{schema}"."{table}"{condition}')[0]["count"]
    rows = live_query(f'SELECT * FROM "{schema}"."{table}"{condition}{ordering} LIMIT %s OFFSET %s', (limit, offset))
    if resource == "title-defs":
        rows = [{key: value for key, value in row.items() if key not in {"emoji_name", "emoji_id"}} for row in rows]
    return {"resource": resource, "table": cfg["table"], "total": total, "rows": [enrich_media(r) for r in rows], "mode": "live"}


def validate_enemy_base(payload: dict[str, Any], creating: bool = False) -> None:
    limits = {"hp": (1, 10**12), "martial_power": (0, 10**12), "mystic_power": (0, 10**12),
              "armor": (0, 10**9), "ward": (0, 10**9), "speed": (1, 10**6)}
    for field, (low, high) in limits.items():
        if field not in payload:
            if creating and field == "hp":
                raise HTTPException(status_code=400, detail="Cần nhập HP của quái.")
            continue
        try:
            if isinstance(payload[field], bool):
                raise ValueError()
            number = Decimal(str(payload[field]))
            if not number.is_finite() or not low <= number <= high:
                raise ValueError()
        except (ValueError, InvalidOperation):
            raise HTTPException(status_code=400, detail=f"{field}: nhập số từ {low} đến {high}.")
    if "enabled" in payload and not isinstance(payload["enabled"], bool):
        raise HTTPException(status_code=400, detail="Trạng thái base phải là Có hoặc Không.")
    if creating and payload.get("family") in {"TOWER", "ABYSS"}:
        if not re.fullmatch(r"[1-9][0-9]*:[1-9][0-9]*", str(payload.get("enemy_code", ""))):
            raise HTTPException(status_code=400, detail="Mã tầng dùng Tầng:Phòng, ví dụ 12:1.")
        stage, chamber = map(int, payload["enemy_code"].split(":"))
        validate_endgame_stage({"mode": payload["family"], "stage_no": stage, "chamber_no": chamber})


def validate_endgame_stage(payload: dict[str, Any]) -> None:
    mode = payload.get("mode")
    stage, chamber = payload.get("stage_no"), payload.get("chamber_no", 1)
    if mode not in {"TOWER", "ABYSS"}:
        raise HTTPException(status_code=400, detail="Chọn Tháp hoặc Vực sâu.")
    if type(stage) is not int or not 1 <= stage <= 100000:
        raise HTTPException(status_code=400, detail="Số tầng phải là số nguyên từ 1 đến 100000.")
    if type(chamber) is not int or not 1 <= chamber <= (1 if mode == "TOWER" else 3):
        raise HTTPException(status_code=400, detail="Tháp chỉ có phòng 1. Vực sâu có phòng 1, 2, 3.")


TITLE_STAT_KEYS = {"martial_power", "mystic_power", "armor", "ward", "crit_rating", "crit_resist",
                   "penetration", "break_rating", "status_potency", "status_resist", "speed"}


def validate_title_definition(payload: dict[str, Any], *, creating: bool) -> None:
    if creating or "code" in payload:
        code = payload.get("code")
        if not isinstance(code, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", code):
            raise HTTPException(status_code=400, detail="Mã danh hiệu: 3–64 ký tự A-Z, 0-9, _.")
    if creating or "display_name_vi" in payload:
        name = payload.get("display_name_vi")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
            raise HTTPException(status_code=400, detail="Tên danh hiệu: 1–120 ký tự.")
    if creating or "source_type" in payload:
        if payload.get("source_type") not in {"REALM", "GIFTCODE", "ADMIN"}:
            raise HTTPException(status_code=400, detail="Nguồn danh hiệu phải là REALM, GIFTCODE hoặc ADMIN.")
    if "realm_ordinal" in payload and payload["realm_ordinal"] is not None:
        if type(payload["realm_ordinal"]) is not int or not 1 <= payload["realm_ordinal"] <= 10:
            raise HTTPException(status_code=400, detail="Bậc cảnh giới phải từ 1 đến 10.")
    if creating:
        if payload.get("source_type") == "REALM" and payload.get("realm_ordinal") is None:
            raise HTTPException(status_code=400, detail="Danh hiệu cảnh giới cần chọn bậc mở khóa.")
        if payload.get("source_type") != "REALM" and payload.get("realm_ordinal") is not None:
            raise HTTPException(status_code=400, detail="Danh hiệu ngoài cảnh giới không dùng bậc mở khóa.")
    for field, maximum in (("vitality_flat", 10**9), ("attack_flat", 10**9),
                           ("monster_cooldown_reduction_percent", 90)):
        if field in payload and (type(payload[field]) is not int or not 0 <= payload[field] <= maximum):
            raise HTTPException(status_code=400, detail=f"{field}: nhập số nguyên từ 0 đến {maximum}.")
    if "stat_bonuses" in payload:
        bonuses = payload["stat_bonuses"]
        if not isinstance(bonuses, dict) or set(bonuses) - TITLE_STAT_KEYS:
            raise HTTPException(status_code=400, detail="Buff chỉ số chứa thuộc tính không được hỗ trợ.")
        for key, value in bonuses.items():
            if type(value) is not int or not 0 <= value <= 10**9:
                raise HTTPException(status_code=400, detail=f"Buff {key}: nhập số nguyên từ 0 đến 1.000.000.000.")
    if "emoji_name" in payload or "emoji_id" in payload:
        raise HTTPException(status_code=400, detail="Emoji title cũ đã ngừng quản lý. Dùng artwork ảnh.")


@app.post("/api/crud/{resource}")
def crud_create(resource: str, payload: dict[str, Any], x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    if resource == "title-defs":
        validate_title_definition(payload, creating=True)
    if resource == "enemy-bases":
        validate_enemy_base(payload, creating=True)
    if resource == "endgame-stages":
        validate_endgame_stage(payload)
    ensure_live_available(); require_write_token(x_admin_token)
    cfg = get_resource(resource); schema, table = split_table(cfg["table"])
    meta = table_metadata(schema, table)
    values = normalize_payload(payload, meta, creating=True)
    if resource == "endgame-stages":
        values["enemy_profile"] = Jsonb({})
        values["config_version_id"] = live_query("SELECT id FROM platform.config_versions WHERE version_code='LK-V4.0-P20-RC-002'")[0]["id"]
    if not values:
        raise HTTPException(status_code=400, detail="No fields supplied.")
    cols = list(values)
    placeholders = ", ".join(["%s"] * len(cols))
    actor = x_admin_actor or ADMIN_ACTOR_DEFAULT
    assert psycopg is not None and dict_row is not None
    try:
        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f'INSERT INTO "{schema}"."{table}" ({", ".join(f"\"{c}\"" for c in cols)}) VALUES ({placeholders}) RETURNING *',
                    tuple(values[c] for c in cols),
                )
                row = dict(cur.fetchone())
                if resource == "endgame-stages":
                    stage = row["stage_no"]
                    multiplier = Decimal("1.5") if row["mode"] == "ABYSS" else Decimal(1)
                    cur.execute("""INSERT INTO combat.enemy_bases(family,enemy_code,display_name_vi,hp,martial_power,armor,ward)
                        VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING *""",
                        (row["mode"], f'{stage}:{row["chamber_no"]}', f'Tầng {stage} · Phòng {row["chamber_no"]}',
                         (800+200*stage+40*stage*stage)*multiplier, (35+8*stage+2*stage*stage)*multiplier, 10+4*stage, 10+4*stage))
                    base = cur.fetchone()
                    if base:
                        audit_write(cur, actor=actor, action="CREATE", object_type="combat.enemy_bases", object_id=f'{row["mode"]}:{base["enemy_code"]}', before=None, after=dict(base))
                obj_id = ",".join(str(row.get(k)) for k in meta["primary_key"]) if meta["primary_key"] else None
                audit_write(cur, actor=actor, action="CREATE", object_type=cfg["table"], object_id=obj_id, before=None, after=row)
                conn.commit()
                return enrich_media(row)
    except Exception as e:
        if psycopg is not None and isinstance(e, getattr(psycopg, "Error", Exception)):
            raise HTTPException(status_code=409, detail=f"Database rejected create: {getattr(e, 'diag', None).message_primary if getattr(e, 'diag', None) else type(e).__name__}")
        raise


@app.patch("/api/crud/{resource}")
def crud_update(resource: str, payload: dict[str, Any], pk: str = Query(...), x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    payload = dict(payload)
    expected_version = payload.pop("_expected_version", None)
    if resource == "title-defs":
        validate_title_definition(payload, creating=False)
    if resource == "enemy-bases":
        validate_enemy_base(payload)
        if not isinstance(expected_version, int) or isinstance(expected_version, bool) or expected_version < 1:
            raise HTTPException(status_code=409, detail="Hãy tải lại base trước khi lưu.")
    ensure_live_available(); require_write_token(x_admin_token)
    cfg = get_resource(resource); schema, table = split_table(cfg["table"])
    try:
        pk_payload = json.loads(pk)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="pk must be a JSON object.")
    meta = table_metadata(schema, table)
    where, pk_params = pk_where(meta, pk_payload)
    values = normalize_payload(payload, meta, creating=False)
    if not values:
        raise HTTPException(status_code=400, detail="No writable fields supplied.")
    actor = x_admin_actor or ADMIN_ACTOR_DEFAULT
    assert psycopg is not None and dict_row is not None
    try:
        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(f'SELECT * FROM "{schema}"."{table}" WHERE {where} FOR UPDATE', tuple(pk_params))
                old = cur.fetchone()
                if old is None:
                    raise HTTPException(status_code=404, detail="Row not found.")
                if resource == "title-defs":
                    source = payload.get("source_type", old["source_type"])
                    ordinal = payload.get("realm_ordinal", old["realm_ordinal"])
                    if (source == "REALM") != (ordinal is not None):
                        raise HTTPException(status_code=400, detail="Nguồn cảnh giới cần bậc; nguồn khác không dùng bậc.")
                if resource == "enemy-bases" and old["version"] != expected_version:
                    raise HTTPException(status_code=409, detail="Base đã được người khác sửa. Tải lại rồi lưu thay đổi.")
                sets = ", ".join(f'"{c}"=%s' for c in values)
                cur.execute(
                    f'UPDATE "{schema}"."{table}" SET {sets} WHERE {where} RETURNING *',
                    tuple(values[c] for c in values) + tuple(pk_params),
                )
                new = dict(cur.fetchone())
                obj_id = ",".join(str(pk_payload[k]) for k in meta["primary_key"])
                audit_write(cur, actor=actor, action="UPDATE", object_type=cfg["table"], object_id=obj_id, before=dict(old), after=new)
                conn.commit()
                return enrich_media(new)
    except HTTPException:
        raise
    except Exception as e:
        if psycopg is not None and isinstance(e, getattr(psycopg, "Error", Exception)):
            raise HTTPException(status_code=409, detail=f"Database rejected update: {getattr(e, 'diag', None).message_primary if getattr(e, 'diag', None) else type(e).__name__}")
        raise


@app.delete("/api/crud/{resource}")
def crud_delete(resource: str, pk: str = Query(...), x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    if resource == "title-defs":
        raise HTTPException(status_code=400, detail="Ẩn danh hiệu bằng trạng thái Tắt để giữ lịch sử sở hữu.")
    ensure_live_available(); require_write_token(x_admin_token)
    cfg = get_resource(resource); schema, table = split_table(cfg["table"])
    try:
        pk_payload = json.loads(pk)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="pk must be a JSON object.")
    meta = table_metadata(schema, table)
    where, pk_params = pk_where(meta, pk_payload)
    actor = x_admin_actor or ADMIN_ACTOR_DEFAULT
    assert psycopg is not None and dict_row is not None
    try:
        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(f'DELETE FROM "{schema}"."{table}" WHERE {where} RETURNING *', tuple(pk_params))
                row = cur.fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="Row not found.")
                old = dict(row)
                obj_id = ",".join(str(pk_payload[k]) for k in meta["primary_key"])
                audit_write(cur, actor=actor, action="DELETE", object_type=cfg["table"], object_id=obj_id, before=old, after=None)
                conn.commit()
                return {"deleted": True, "row": enrich_media(old)}
    except HTTPException:
        raise
    except Exception as e:
        if psycopg is not None and isinstance(e, getattr(psycopg, "Error", Exception)):
            raise HTTPException(status_code=409, detail=f"Database rejected delete (often because another gameplay row references it): {getattr(e, 'diag', None).message_primary if getattr(e, 'diag', None) else type(e).__name__}")
        raise


# -------------------------- Item editor + shared artwork --------------------------
ALLOWED_ITEM_PATCH_FIELDS = {
    "display_name_vi", "transferable", "tags", "base_stats", "base_effects",
    "item_type", "family_code", "equipment_slot", "rarity", "stackable", "max_stack", "bind_rule",
    "salvage_rule", "affix_combo_code", "set_code", "set_name",
}


@app.patch("/api/items/{item_def_id}")
def patch_item(item_def_id: str, payload: dict[str, Any], x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available(); require_write_token(x_admin_token)
    unknown = set(payload) - ALLOWED_ITEM_PATCH_FIELDS
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unsupported fields: {sorted(unknown)}")
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update.")
    # Reuse schema-driven adapter and audit.
    pk = quote(json.dumps({"id": item_def_id}))
    # Call the underlying function directly, not HTTP, to keep one implementation.
    return crud_update("item-defs", payload, json.dumps({"id": item_def_id}), x_admin_token, x_admin_actor)


def _process_image_to_webp(raw: bytes, *, trim_transparency: bool = False) -> tuple[bytes, int, int]:
    if Image is None:
        raise HTTPException(status_code=503, detail="Image upload needs Pillow. Reinstall requirements.txt.")
    try:
        with Image.open(io.BytesIO(raw)) as check:
            check.verify()
        with Image.open(io.BytesIO(raw)) as img:
            img.load()
            width, height = img.size
            if width <= 0 or height <= 0:
                raise ValueError("Invalid image dimensions")
            if trim_transparency:
                img = img.convert("RGBA")
                visible = img.getchannel("A").point(lambda alpha: 255 if alpha > 8 else 0).getbbox()
                if visible is None:
                    raise ValueError("Image has no visible artwork")
                img = img.crop(visible)
            if max(width, height) > MAX_IMAGE_DIMENSION:
                img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
            # Preserve transparency when present.
            if img.mode not in {"RGB", "RGBA"}:
                img = img.convert("RGBA" if "transparency" in img.info else "RGB")
            out = io.BytesIO()
            img.save(out, format="WEBP", quality=92, method=6)
            return out.getvalue(), img.width, img.height
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="File is not a valid supported image (PNG/JPEG/WebP/GIF source).")


def _delete_local_asset(asset_key: str | None) -> None:
    if not asset_key:
        return
    try:
        p = safe_media_path(asset_key)
    except HTTPException:
        return
    if p.exists() and p.is_file():
        p.unlink(missing_ok=True)
        try:
            if p.parent != MEDIA_DIR and not any(p.parent.iterdir()):
                p.parent.rmdir()
        except OSError:
            pass


def _save_local_asset(asset_key: str, content: bytes) -> None:
    target = safe_media_path(asset_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="lk-item-", suffix=target.suffix or ".bin", dir=str(target.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        tmp_path.write_bytes(content)
        os.replace(tmp_path, target)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def _persist_item_image(item_def_id: str, *, raw: bytes, original_filename: str | None, actor: str) -> dict[str, Any]:
    webp, width, height = _process_image_to_webp(raw)
    digest = hashlib.sha256(webp).hexdigest()
    asset_key = f"items/{item_def_id}/{digest[:24]}.webp"
    backend = effective_media_backend()
    assert psycopg is not None and dict_row is not None
    old_key: str | None = None
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM inventory.item_defs WHERE id=%s::uuid FOR UPDATE", (item_def_id,))
            old = cur.fetchone()
            if old is None:
                raise HTTPException(status_code=404, detail="Item definition not found.")
            old_dict = dict(old)
            old_key = old_dict.get("image_asset_key")

            # Store the binary first inside the SAME PostgreSQL transaction when the shared DB media table exists.
            # If the media patch has not been applied yet, filesystem is used as a compatibility fallback.
            if backend == "database":
                _write_db_media(
                    cur,
                    asset_key=asset_key,
                    content=webp,
                    content_type="image/webp",
                    sha256=digest,
                    width=width,
                    height=height,
                    original_filename=original_filename,
                    actor=actor,
                )
            else:
                _save_local_asset(asset_key, webp)

            cur.execute("UPDATE inventory.item_defs SET image_asset_key=%s WHERE id=%s::uuid RETURNING *", (asset_key, item_def_id))
            new = dict(cur.fetchone())
            # v4 optional multi-image gallery: keep PRIMARY link in sync with image_asset_key.
            try:
                cur.execute("SELECT to_regclass('platform.entity_media_links')::text AS reg")
                reg_row = cur.fetchone()
                if reg_row and reg_row.get("reg"):
                    cur.execute("UPDATE platform.entity_media_links SET is_primary=false, media_role=CASE WHEN media_role='PRIMARY' THEN 'GALLERY' ELSE media_role END WHERE entity_type='ITEM_DEF' AND entity_id=%s", (item_def_id,))
                    cur.execute(
                        "INSERT INTO platform.entity_media_links(entity_type,entity_id,asset_key,media_role,sort_order,is_primary,created_by) VALUES('ITEM_DEF',%s,%s,'PRIMARY',0,true,%s) ON CONFLICT(entity_type,entity_id,asset_key) DO UPDATE SET media_role='PRIMARY',sort_order=0,is_primary=true",
                        (item_def_id, asset_key, actor),
                    )
            except Exception:
                pass
            audit_write(
                cur,
                actor=actor,
                action="ITEM_IMAGE_UPLOAD",
                object_type="inventory.item_defs",
                object_id=item_def_id,
                before=old_dict,
                after={**new, "media_backend": backend, "sha256": digest, "size_bytes": len(webp), "width": width, "height": height},
                reason="ADMIN_DIRECT_UPLOAD",
            )

            # Delete replaced DB blob only after item_def no longer references it.
            if backend == "database" and old_key and old_key != asset_key:
                _delete_db_asset_if_orphan(cur, old_key)
            conn.commit()

    if backend == "filesystem" and old_key and old_key != asset_key:
        _delete_local_asset(old_key)

    return {
        "ok": True,
        "item_def_id": item_def_id,
        "asset_key": asset_key,
        "image_url": media_url_for_key(asset_key),
        "sha256": digest,
        "size_bytes": len(webp),
        "width": width,
        "height": height,
        "content_type": "image/webp",
        "media_backend": backend,
    }


@app.post("/api/items/{item_def_id}/image")
async def upload_item_image(item_def_id: str, file: UploadFile = File(...), x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    """Direct binary upload. No URL/link field is accepted by this endpoint."""
    ensure_live_available(); require_write_token(x_admin_token)
    raw = await file.read(MAX_IMAGE_BYTES + 1)
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail=f"Image is larger than {MAX_IMAGE_MB} MB.")
    if not raw:
        raise HTTPException(status_code=400, detail="Empty image file.")
    return _persist_item_image(
        item_def_id,
        raw=raw,
        original_filename=file.filename,
        actor=x_admin_actor or ADMIN_ACTOR_DEFAULT,
    )


@app.post("/api/items/images/bulk")
async def bulk_upload_item_images(files: list[UploadFile] = File(...), x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    """Bulk direct upload. Filename stem must equal item code, e.g. EQ_HELM_C01_COMMON.png."""
    ensure_live_available(); require_write_token(x_admin_token)
    if len(files) > 500:
        raise HTTPException(status_code=400, detail="Bulk upload is capped at 500 files per request.")
    actor = x_admin_actor or ADMIN_ACTOR_DEFAULT
    results: list[dict[str, Any]] = []
    for f in files:
        name = Path(f.filename or "").name
        code = Path(name).stem.strip()
        if not code:
            results.append({"filename": name, "ok": False, "error": "Filename must contain item code."})
            continue
        rows = live_query("SELECT id::text AS id, code FROM inventory.item_defs WHERE upper(code)=upper(%s) LIMIT 2", (code,))
        if len(rows) != 1:
            results.append({"filename": name, "item_code": code, "ok": False, "error": "No unique item code matched filename stem."})
            continue
        raw = await f.read(MAX_IMAGE_BYTES + 1)
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            results.append({"filename": name, "item_code": code, "ok": False, "error": f"Empty or > {MAX_IMAGE_MB} MB."})
            continue
        try:
            saved = _persist_item_image(rows[0]["id"], raw=raw, original_filename=name, actor=actor)
            results.append({"filename": name, "item_code": rows[0]["code"], "ok": True, **saved})
        except Exception as e:
            detail = e.detail if isinstance(e, HTTPException) else type(e).__name__
            results.append({"filename": name, "item_code": code, "ok": False, "error": str(detail)})
    return {
        "ok": all(r.get("ok") for r in results) if results else True,
        "total": len(results),
        "success": sum(1 for r in results if r.get("ok")),
        "failed": sum(1 for r in results if not r.get("ok")),
        "results": results,
    }


@app.delete("/api/items/{item_def_id}/image")
def delete_item_image(item_def_id: str, x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available(); require_write_token(x_admin_token)
    actor = x_admin_actor or ADMIN_ACTOR_DEFAULT
    assert psycopg is not None and dict_row is not None
    backend = effective_media_backend()
    old_key: str | None = None
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM inventory.item_defs WHERE id=%s::uuid FOR UPDATE", (item_def_id,))
            old = cur.fetchone()
            if old is None:
                raise HTTPException(status_code=404, detail="Item definition not found.")
            old_dict = dict(old); old_key = old_dict.get("image_asset_key")
            cur.execute("UPDATE inventory.item_defs SET image_asset_key=NULL WHERE id=%s::uuid RETURNING *", (item_def_id,))
            new = dict(cur.fetchone())
            try:
                cur.execute("SELECT to_regclass('platform.entity_media_links')::text AS reg")
                reg_row = cur.fetchone()
                if reg_row and reg_row.get("reg") and old_key:
                    cur.execute("DELETE FROM platform.entity_media_links WHERE entity_type='ITEM_DEF' AND entity_id=%s AND asset_key=%s", (item_def_id, old_key))
            except Exception:
                pass
            if backend == "database" and old_key:
                _delete_db_asset_if_orphan(cur, old_key)
            audit_write(cur, actor=actor, action="ITEM_IMAGE_DELETE", object_type="inventory.item_defs", object_id=item_def_id, before=old_dict, after=new, reason="ADMIN_DIRECT_UPLOAD")
            conn.commit()
    if backend == "filesystem":
        _delete_local_asset(old_key)
    return {"ok": True, "item_def_id": item_def_id, "deleted_asset_key": old_key, "image_asset_key": None, "media_backend": backend}


@app.get("/api/public/media/{asset_key:path}")
def public_media(asset_key: str) -> Response:
    """Binary media resolver for Admin previews, website, and Discord bot. No manual URL is stored in item data."""
    found = _read_media_asset(asset_key)
    if not found:
        raise HTTPException(status_code=404, detail="Media asset not found.")
    content, content_type = found
    etag = hashlib.sha256(content).hexdigest()
    return Response(content=content, media_type=content_type, headers={"ETag": etag, "Cache-Control": "public, max-age=3600"})


@app.get("/api/public/items/{item_code}/image")
def public_item_image(item_code: str) -> Response:
    """Stable bot/web endpoint by item code.

    V6.4: prefer the configured gameplay version, but never return a false 404 just
    because a newer historical/config row has no image.  Fall back to the newest
    image-bearing definition and finally to its PRIMARY shared-media link.
    """
    ensure_live_available()
    rows = live_query(
        """
        SELECT d.id::text AS item_def_id, d.image_asset_key, d.config_version_id, cv.version_code,
               (cv.version_code=%s) AS requested
        FROM inventory.item_defs d
        LEFT JOIN platform.config_versions cv ON cv.id=d.config_version_id
        WHERE d.code=%s
        ORDER BY (cv.version_code=%s) DESC,
                 (d.image_asset_key IS NOT NULL AND d.image_asset_key<>'') DESC,
                 d.config_version_id DESC
        """,
        (ADMIN_GAMEPLAY_CONFIG, item_code, ADMIN_GAMEPLAY_CONFIG),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Unknown item code.")

    # Try direct keys in priority order.
    for row in rows:
        key = row.get("image_asset_key")
        if key:
            found = _read_media_asset(key)
            if found:
                content, content_type = found
                etag = hashlib.sha256(content).hexdigest()
                return Response(content=content, media_type=content_type, headers={"ETag": etag, "Cache-Control": "public, max-age=3600"})

    # Direct field may be stale/null while shared PRIMARY is valid.
    for row in rows:
        links = live_query(
            """SELECT asset_key FROM platform.entity_media_links
               WHERE entity_type='ITEM_DEF' AND entity_id=%s AND is_primary=true
               ORDER BY created_at DESC LIMIT 1""",
            (row["item_def_id"],),
        )
        if links and links[0].get("asset_key"):
            found = _read_media_asset(links[0]["asset_key"])
            if found:
                content, content_type = found
                etag = hashlib.sha256(content).hexdigest()
                return Response(content=content, media_type=content_type, headers={"ETag": etag, "Cache-Control": "public, max-age=3600"})

    raise HTTPException(status_code=404, detail="Item has no readable shared-media image.")


@app.get("/api/media/resolve")
def resolve_media(key: str = Query(...)) -> dict[str, Any]:
    found = _read_media_asset(key)
    return {
        "asset_key": key,
        "exists": bool(found),
        "url": media_url_for_key(key),
        "size_bytes": len(found[0]) if found else None,
        "content_type": found[1] if found else None,
        "media_backend": effective_media_backend(),
    }


@app.get("/api/media/assets")
def media_assets(limit: int = Query(500, ge=1, le=2000)) -> dict[str, Any]:
    if media_db_table_exists():
        rows = live_query(
            """
            SELECT asset_key, category, content_type, sha256, size_bytes, width, height, original_filename,
                   created_by, created_at, updated_at, active
            FROM platform.media_assets
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        for r in rows:
            r["url"] = media_url_for_key(r["asset_key"])
        return {"backend": "database", "rows": rows, "total": len(rows)}
    files = [p for p in MEDIA_DIR.rglob("*") if p.is_file() and p.name != ".gitkeep"]
    rows = []
    for p in sorted(files, key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
        key = p.relative_to(MEDIA_DIR).as_posix()
        rows.append({"asset_key": key, "size_bytes": p.stat().st_size, "updated_at": p.stat().st_mtime, "url": media_url_for_key(key), "active": True})
    return {"backend": "filesystem", "rows": rows, "total": len(files)}


@app.get("/api/media/stats")
def media_stats() -> dict[str, Any]:
    if media_db_table_exists():
        r = live_query("SELECT count(*) AS files, COALESCE(sum(size_bytes),0) AS used_bytes FROM platform.media_assets WHERE active=true")[0]
        return {"files": r["files"], "used_bytes": r["used_bytes"], "backend": "database", "db_ready": True}
    files = [p for p in MEDIA_DIR.rglob("*") if p.is_file() and p.name != ".gitkeep"]
    used_bytes = sum(p.stat().st_size for p in files)
    return {"files": len(files), "used_bytes": used_bytes, "backend": "filesystem", "db_ready": False, "media_dir": str(MEDIA_DIR)}



# ---------------------------------------------------------------------------
# V27 Content Media Studio — shared media for Item / Character / Boss / Enemy /
# Commander. Discord/Web resolve the same asset instead of copying bot folders.
# ---------------------------------------------------------------------------
MEDIA_ENTITY_CONFIG: dict[str, dict[str, str | None]] = {
    "title": {"table": "title.title_defs", "pk": "code", "code": "code", "label": "display_name_vi", "entity_type": "TITLE_DEF", "direct_image_column": "artwork_asset_key"},
    "item": {"table": "inventory.item_defs", "pk": "id", "code": "code", "label": "display_name_vi", "entity_type": "ITEM_DEF", "direct_image_column": "image_asset_key"},
    "character": {"table": "hero.character_defs", "pk": "code", "code": "code", "label": "display_name_vi", "entity_type": "CHARACTER_DEF", "direct_image_column": "image_asset_key"},
    "boss": {"table": "adventure.faction_boss_catalog", "pk": "boss_code", "code": "boss_code", "label": "display_name_vi", "entity_type": "FACTION_BOSS", "direct_image_column": None},
    "enemy": {"table": "content.enemy_defs", "pk": "id", "code": "code", "label": "name_key", "entity_type": "ENEMY_DEF", "direct_image_column": None},
    "commander": {"table": "commander.commander_defs", "pk": "id", "code": "code", "label": "name_key", "entity_type": "COMMANDER_DEF", "direct_image_column": None},
    "set": {"table": "inventory.equipment_set_defs", "pk": "set_code", "code": "set_code", "label": "set_name", "entity_type": "EQUIPMENT_SET", "direct_image_column": None},
    "technique": {"table": "content.technique_defs", "pk": "id", "code": "code", "label": "name_key", "entity_type": "TECHNIQUE_DEF", "direct_image_column": None},
    "building": {"table": "content.building_defs", "pk": "id", "code": "code", "label": "name_key", "entity_type": "BUILDING_DEF", "direct_image_column": None},
    "research": {"table": "content.research_defs", "pk": "id", "code": "code", "label": "code", "entity_type": "RESEARCH_DEF", "direct_image_column": None},
    "race": {"table": "content.race_defs", "pk": "id", "code": "code", "label": "name_key", "entity_type": "RACE_DEF", "direct_image_column": None},
    "path": {"table": "content.path_defs", "pk": "id", "code": "code", "label": "name_key", "entity_type": "PATH_DEF", "direct_image_column": None},
    "affinity": {"table": "content.affinity_defs", "pk": "id", "code": "code", "label": "name_key", "entity_type": "AFFINITY_DEF", "direct_image_column": None},
    "sect": {"table": "content.sect_defs", "pk": "id", "code": "code", "label": "name_key", "entity_type": "SECT_DEF", "direct_image_column": None},
    "region": {"table": "content.region_defs", "pk": "id", "code": "code", "label": "name_key", "entity_type": "REGION_DEF", "direct_image_column": None},
    "clan-boss": {"table": "clan.clan_boss_defs", "pk": "id", "code": "boss_code", "label": "boss_code", "entity_type": "CLAN_BOSS_DEF", "direct_image_column": None},
    "clan-tech": {"table": "clan.clan_tech_defs", "pk": "id", "code": "tech_code", "label": "tech_code", "entity_type": "CLAN_TECH_DEF", "direct_image_column": None},
}


def _media_entity_cfg(kind: str) -> dict[str, str | None]:
    cfg = MEDIA_ENTITY_CONFIG.get(kind.lower())
    if not cfg or str(cfg["table"]) not in available_tables():
        raise HTTPException(status_code=404, detail="Unsupported media entity for the connected V27 database.")
    return cfg


def _entity_media_link_ready() -> bool:
    return "platform.entity_media_links" in available_tables()


@app.get("/api/content-media/kinds")
def content_media_kinds() -> list[dict[str, Any]]:
    tables = available_tables()
    return [{"kind": k, "table": cfg["table"], "entity_type": cfg["entity_type"], "available": str(cfg["table"]) in tables}
            for k, cfg in MEDIA_ENTITY_CONFIG.items() if str(cfg["table"]) in tables]


@app.get("/api/content-media/{kind}")
def content_media_entities(kind: str, q: str = Query(""), limit: int = Query(500, ge=1, le=1000)) -> dict[str, Any]:
    ensure_live_available()
    cfg = _media_entity_cfg(kind)
    schema, table = split_table(str(cfg["table"])); pk = str(cfg["pk"]); code = str(cfg["code"]); label = str(cfg["label"])
    entity_type = str(cfg["entity_type"]); direct = cfg.get("direct_image_column")
    direct_sql = f'e."{direct}"' if direct else 'NULL::varchar'
    predicates: list[str] = []
    where_args: list[Any] = []
    # Character catalog may intentionally live in the previous config version.
    # Prefer ADMIN_GAMEPLAY_CONFIG when it contains character rows; otherwise use the
    # newest config_version_id that actually owns a character catalog.
    if kind.lower() == "character":
        predicates.append('''e."config_version_id" = COALESCE(
            (SELECT cv.id FROM platform.config_versions cv
             WHERE cv.version_code=%s
               AND EXISTS (SELECT 1 FROM hero.character_defs cx WHERE cx.config_version_id=cv.id)
             ORDER BY cv.id DESC LIMIT 1),
            (SELECT max(cx.config_version_id) FROM hero.character_defs cx)
        )''')
        where_args.append(ADMIN_GAMEPLAY_CONFIG)
    if q.strip():
        predicates.append(f'(e."{code}"::text ILIKE %s OR e."{label}"::text ILIKE %s)')
        like = f"%{q.strip()}%"; where_args.extend([like, like])
    where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
    if _entity_media_link_ready():
        args: list[Any] = [entity_type, *where_args, limit]
        rows = live_query(
            f'''SELECT e."{pk}"::text AS entity_id, e."{code}"::text AS code, e."{label}"::text AS display_name,
                       COALESCE({direct_sql}, l.asset_key) AS image_asset_key, l.asset_key AS linked_primary_asset_key
                FROM "{schema}"."{table}" e
                LEFT JOIN LATERAL (
                    SELECT em.asset_key FROM platform.entity_media_links em
                    WHERE em.entity_type=%s AND em.entity_id=e."{pk}"::text AND em.is_primary=true
                    ORDER BY em.created_at DESC LIMIT 1
                ) l ON true
                {where}
                ORDER BY e."{label}" NULLS LAST, e."{code}" LIMIT %s''', tuple(args))
    else:
        rows = live_query(
            f'''SELECT e."{pk}"::text AS entity_id, e."{code}"::text AS code, e."{label}"::text AS display_name,
                       {direct_sql} AS image_asset_key, NULL::varchar AS linked_primary_asset_key
                FROM "{schema}"."{table}" e {where}
                ORDER BY e."{label}" NULLS LAST, e."{code}" LIMIT %s''', tuple([*where_args, limit]))
    for row in rows: row["image_url"] = media_url_for_key(row.get("image_asset_key"))
    return {"kind": kind, "entity_type": entity_type, "rows": rows, "total": len(rows)}


@app.get("/api/content-media/{kind}/{entity_id}/gallery")
def content_media_gallery(kind: str, entity_id: str) -> dict[str, Any]:
    ensure_live_available(); cfg = _media_entity_cfg(kind)
    if not _entity_media_link_ready(): return {"kind": kind, "entity_id": entity_id, "rows": [], "gallery_enabled": False}
    rows = live_query("""SELECT l.asset_key,l.media_role,l.sort_order,l.is_primary,l.created_at,
                                a.content_type,a.size_bytes,a.width,a.height,a.original_filename
                         FROM platform.entity_media_links l
                         JOIN platform.media_assets a ON a.asset_key=l.asset_key
                         WHERE l.entity_type=%s AND l.entity_id=%s
                         ORDER BY l.is_primary DESC,l.sort_order,l.created_at""",
                      (str(cfg["entity_type"]), entity_id))
    for row in rows: row["url"] = media_url_for_key(row.get("asset_key"))
    return {"kind": kind, "entity_id": entity_id, "rows": rows, "gallery_enabled": True}


def _lock_media_entity(cur, kind: str, cfg: dict[str, str | None], entity_id: str):
    """Lock one canonical entity row. Character definitions are config-versioned."""
    schema, table = split_table(str(cfg["table"])); pk = str(cfg["pk"])
    if kind.lower() == "character":
        cur.execute(
            f'''SELECT e.* FROM "{schema}"."{table}" e
                WHERE e."{pk}"::text=%s
                  AND e.config_version_id = COALESCE(
                    (SELECT cv.id FROM platform.config_versions cv
                     WHERE cv.version_code=%s
                       AND EXISTS (SELECT 1 FROM hero.character_defs cx WHERE cx.config_version_id=cv.id)
                     ORDER BY cv.id DESC LIMIT 1),
                    (SELECT max(cx.config_version_id) FROM hero.character_defs cx)
                  )
                FOR UPDATE OF e''',
            (entity_id, ADMIN_GAMEPLAY_CONFIG),
        )
    else:
        cur.execute(f'SELECT * FROM "{schema}"."{table}" WHERE "{pk}"::text=%s FOR UPDATE', (entity_id,))
    return cur.fetchone()


def _update_direct_media_column(cur, kind: str, cfg: dict[str, str | None], entity_id: str, value: str | None) -> None:
    direct = cfg.get("direct_image_column")
    if not direct:
        return
    schema, table = split_table(str(cfg["table"])); pk = str(cfg["pk"])
    if kind.lower() == "character":
        cur.execute(
            f'''UPDATE "{schema}"."{table}" e SET "{direct}"=%s
                WHERE e."{pk}"::text=%s
                  AND e.config_version_id = COALESCE(
                    (SELECT cv.id FROM platform.config_versions cv
                     WHERE cv.version_code=%s
                       AND EXISTS (SELECT 1 FROM hero.character_defs cx WHERE cx.config_version_id=cv.id)
                     ORDER BY cv.id DESC LIMIT 1),
                    (SELECT max(cx.config_version_id) FROM hero.character_defs cx)
                  )''',
            (value, entity_id, ADMIN_GAMEPLAY_CONFIG),
        )
    else:
        cur.execute(f'UPDATE "{schema}"."{table}" SET "{direct}"=%s WHERE "{pk}"::text=%s', (value, entity_id))


@app.post("/api/content-media/{kind}/{entity_id}/image")
async def upload_content_media_image(kind: str, entity_id: str, role: str = Query("PRIMARY", max_length=32), file: UploadFile = File(...),
                                     x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available(); require_write_token(x_admin_token)
    if not media_db_table_exists() or not _entity_media_link_ready():
        raise HTTPException(status_code=409, detail="Apply the V27 shared-media SQL patch before uploading content media.")
    cfg = _media_entity_cfg(kind); actor = x_admin_actor or ADMIN_ACTOR_DEFAULT
    raw = await file.read(MAX_IMAGE_BYTES + 1)
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413 if len(raw) > MAX_IMAGE_BYTES else 400, detail=f"Empty image or larger than {MAX_IMAGE_MB} MB.")
    webp, width, height = _process_image_to_webp(raw, trim_transparency=kind.lower()=="title"); digest = hashlib.sha256(webp).hexdigest()
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", entity_id)[:120] or "entity"
    asset_key = f"content/{kind}/{safe_id}/{digest[:24]}.webp"
    schema, table = split_table(str(cfg["table"])); pk = str(cfg["pk"]); direct = cfg.get("direct_image_column"); entity_type = str(cfg["entity_type"])
    assert psycopg is not None and dict_row is not None
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            old = _lock_media_entity(cur, kind, cfg, entity_id)
            if old is None: raise HTTPException(status_code=404, detail="Content entity not found.")
            _write_db_media(cur, asset_key=asset_key, content=webp, content_type="image/webp", sha256=digest, width=width, height=height,
                            original_filename=file.filename, actor=actor, category=f"{kind.upper()}_IMAGE")
            if role.upper() == "PRIMARY":
                cur.execute("UPDATE platform.entity_media_links SET is_primary=false, media_role=CASE WHEN media_role='PRIMARY' THEN 'GALLERY' ELSE media_role END WHERE entity_type=%s AND entity_id=%s", (entity_type, entity_id))
            cur.execute("SELECT COALESCE(max(sort_order),-1)+1 AS n FROM platform.entity_media_links WHERE entity_type=%s AND entity_id=%s", (entity_type, entity_id)); n=int(cur.fetchone()["n"])
            cur.execute("""INSERT INTO platform.entity_media_links(entity_type,entity_id,asset_key,media_role,sort_order,is_primary,created_by)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT(entity_type,entity_id,asset_key) DO UPDATE SET media_role=EXCLUDED.media_role,sort_order=EXCLUDED.sort_order,is_primary=EXCLUDED.is_primary""",
                        (entity_type, entity_id, asset_key, role.upper(), 0 if role.upper()=="PRIMARY" else n, role.upper()=="PRIMARY", actor))
            if direct and role.upper()=="PRIMARY": _update_direct_media_column(cur, kind, cfg, entity_id, asset_key)
            audit_write(cur, actor=actor, action="CONTENT_MEDIA_UPLOAD", object_type=str(cfg["table"]), object_id=entity_id, before=dict(old),
                        after={"asset_key":asset_key,"role":role.upper(),"sha256":digest}, reason="ADMIN_DIRECT_UPLOAD")
            conn.commit()
    return {"ok":True,"kind":kind,"entity_id":entity_id,"asset_key":asset_key,"image_url":media_url_for_key(asset_key),"width":width,"height":height,"size_bytes":len(webp)}


@app.post("/api/content-media/{kind}/{entity_id}/primary")
def set_content_media_primary(kind: str, entity_id: str, payload: dict[str, Any], x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available(); require_write_token(x_admin_token); cfg=_media_entity_cfg(kind)
    if not _entity_media_link_ready(): raise HTTPException(status_code=409, detail="Shared media links are not installed.")
    asset_key=str(payload.get("asset_key") or "").strip()
    if not asset_key: raise HTTPException(status_code=400, detail="asset_key is required.")
    actor=x_admin_actor or ADMIN_ACTOR_DEFAULT; entity_type=str(cfg["entity_type"]); schema,table=split_table(str(cfg["table"])); pk=str(cfg["pk"]); direct=cfg.get("direct_image_column")
    assert psycopg is not None and dict_row is not None
    with psycopg.connect(DATABASE_URL,row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM platform.entity_media_links WHERE entity_type=%s AND entity_id=%s AND asset_key=%s",(entity_type,entity_id,asset_key))
            if not cur.fetchone(): raise HTTPException(status_code=404,detail="Media link not found for entity.")
            cur.execute("UPDATE platform.entity_media_links SET is_primary=false,media_role=CASE WHEN media_role='PRIMARY' THEN 'GALLERY' ELSE media_role END WHERE entity_type=%s AND entity_id=%s",(entity_type,entity_id))
            cur.execute("UPDATE platform.entity_media_links SET is_primary=true,media_role='PRIMARY',sort_order=0 WHERE entity_type=%s AND entity_id=%s AND asset_key=%s",(entity_type,entity_id,asset_key))
            if direct: _update_direct_media_column(cur, kind, cfg, entity_id, asset_key)
            audit_write(cur,actor=actor,action="CONTENT_MEDIA_PRIMARY",object_type=str(cfg["table"]),object_id=entity_id,before=None,after={"asset_key":asset_key},reason="ADMIN_MEDIA_PRIMARY")
            conn.commit()
    return {"ok":True,"asset_key":asset_key,"image_url":media_url_for_key(asset_key)}


@app.delete("/api/content-media/{kind}/{entity_id}/image")
def delete_content_media_image(kind: str, entity_id: str, asset_key: str = Query(...), x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available(); require_write_token(x_admin_token); cfg=_media_entity_cfg(kind)
    if not _entity_media_link_ready(): raise HTTPException(status_code=409, detail="Shared media links are not installed.")
    actor=x_admin_actor or ADMIN_ACTOR_DEFAULT; entity_type=str(cfg["entity_type"]); schema,table=split_table(str(cfg["table"])); pk=str(cfg["pk"]); direct=cfg.get("direct_image_column")
    assert psycopg is not None and dict_row is not None
    with psycopg.connect(DATABASE_URL,row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT is_primary FROM platform.entity_media_links WHERE entity_type=%s AND entity_id=%s AND asset_key=%s FOR UPDATE",(entity_type,entity_id,asset_key)); row=cur.fetchone()
            if not row: raise HTTPException(status_code=404,detail="Media link not found.")
            was_primary=bool(row["is_primary"])
            cur.execute("DELETE FROM platform.entity_media_links WHERE entity_type=%s AND entity_id=%s AND asset_key=%s",(entity_type,entity_id,asset_key))
            if direct and was_primary: _update_direct_media_column(cur, kind, cfg, entity_id, None)
            _delete_db_asset_if_orphan(cur,asset_key)
            audit_write(cur,actor=actor,action="CONTENT_MEDIA_DELETE",object_type=str(cfg["table"]),object_id=entity_id,before={"asset_key":asset_key},after=None,reason="ADMIN_MEDIA_DELETE")
            conn.commit()
    return {"ok":True,"deleted_asset_key":asset_key}

# ---------------------------------------------------------------------------
# SUPER MEGA v4 — command center, global search, data quality, bulk exports,
# richer item artwork gallery, support workflows and operational diagnostics.
# Additive to v3; runtime gameplay authority remains outside generic CRUD.
# ---------------------------------------------------------------------------

def _table_exists(full: str) -> bool:
    if not live_mode():
        return full in KNOWN_TABLES
    try:
        rows = live_query("SELECT to_regclass(%s)::text AS reg", (full,))
        return bool(rows and rows[0].get("reg"))
    except Exception:
        return False


def _item_rows_for_quality() -> list[dict[str, Any]]:
    if not live_mode():
        return [dict(r) for r in items()]
    return live_query(
        """SELECT d.* FROM inventory.item_defs d
           JOIN platform.config_versions cv ON cv.id=d.config_version_id
           WHERE cv.version_code=%s AND COALESCE(d.catalog_status,'ACTIVE_CANONICAL')='ACTIVE_CANONICAL'
           ORDER BY d.code""",
        (ADMIN_GAMEPLAY_CONFIG,)
    )


def _set_rows_for_quality() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not live_mode():
        tables = SNAPSHOT.get("tables", {})
        return ([dict(r) for r in tables.get("inventory.equipment_set_defs", [])],
                [dict(r) for r in tables.get("inventory.equipment_set_bonuses", [])])
    return (live_query("SELECT * FROM inventory.equipment_set_defs ORDER BY set_code"),
            live_query("SELECT * FROM inventory.equipment_set_bonuses ORDER BY set_code, pieces_required"))


def _data_quality_report() -> dict[str, Any]:
    items = _item_rows_for_quality()
    sets, bonuses = _set_rows_for_quality()
    code_counts: dict[str, int] = {}
    for i in items:
        code = str(i.get("code") or "").strip()
        if code:
            code_counts[code] = code_counts.get(code, 0) + 1
    set_codes = {str(s.get("set_code")) for s in sets if s.get("set_code")}
    bonus_by_set: dict[str, set[int]] = {}
    for b in bonuses:
        if b.get("set_code"):
            try:
                bonus_by_set.setdefault(str(b["set_code"]), set()).add(int(b.get("pieces_required") or 0))
            except Exception:
                pass
    expected_bonus = {2, 4, 6, 8}
    issues: list[dict[str, Any]] = []
    missing_images = []
    for i in items:
        code = i.get("code")
        tags = [str(x).upper() for x in (i.get("tags") or [])]
        is_sample = "SAMPLE_BALANCE" in tags or "SAMPLE" in str(code or "").upper()
        if not i.get("display_name_vi"):
            issues.append({"severity":"HIGH","type":"ITEM_NAME_MISSING","entity":code,"message":"Item thiếu display_name_vi."})
        if str(i.get("item_type") or "").upper() == "EQUIPMENT" and not i.get("equipment_slot"):
            issues.append({"severity":"HIGH","type":"ITEM_SLOT_MISSING","entity":code,"message":"Equipment thiếu equipment_slot."})
        if not i.get("rarity"):
            issues.append({"severity":"HIGH","type":"RARITY_MISSING","entity":code,"message":"Item thiếu rarity."})
        if i.get("set_code") and str(i.get("set_code")) not in set_codes:
            issues.append({"severity":"HIGH","type":"ORPHAN_SET_CODE","entity":code,"message":f"set_code {i.get('set_code')} không tồn tại trong equipment_set_defs."})
        if not is_sample and not i.get("image_asset_key"):
            missing_images.append(code)
    for code, count in code_counts.items():
        if count > 1:
            issues.append({"severity":"CRITICAL","type":"DUPLICATE_ITEM_CODE","entity":code,"message":f"Có {count} item definitions cùng code."})
    for s in sets:
        sc = str(s.get("set_code") or "")
        have = bonus_by_set.get(sc, set())
        missing = sorted(expected_bonus - have)
        if missing:
            issues.append({"severity":"MEDIUM","type":"SET_BONUS_GAP","entity":sc,"message":f"Thiếu bonus mốc {missing}."})
    if missing_images:
        issues.append({"severity":"MEDIUM","type":"ITEM_IMAGE_COVERAGE","entity":"inventory.item_defs","message":f"{len(missing_images)} production item chưa có ảnh.","examples":missing_images[:20]})
    sev_order = {"CRITICAL":0,"HIGH":1,"MEDIUM":2,"LOW":3}
    issues.sort(key=lambda x:(sev_order.get(str(x.get("severity")),9),str(x.get("type")),str(x.get("entity"))))
    production = [i for i in items if "SAMPLE_BALANCE" not in [str(x).upper() for x in (i.get("tags") or [])] and "SAMPLE" not in str(i.get("code") or "").upper()]
    with_image = sum(1 for i in production if i.get("image_asset_key"))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "items": len(items), "production_items": len(production), "sets": len(sets), "set_bonuses": len(bonuses),
            "production_items_with_image": with_image, "production_items_missing_image": max(0, len(production)-with_image),
            "image_coverage_pct": round((with_image*100/len(production)), 2) if production else 100.0,
            "issue_count": len(issues),
            "critical": sum(1 for x in issues if x["severity"]=="CRITICAL"),
            "high": sum(1 for x in issues if x["severity"]=="HIGH"),
            "medium": sum(1 for x in issues if x["severity"]=="MEDIUM"),
        },
        "issues": issues[:1000],
    }


@app.get("/api/command-center")
def command_center() -> dict[str, Any]:
    base = dashboard()
    dq = _data_quality_report()
    ops = {"pending_outbox":0,"failed_outbox":0,"pending_jobs":0,"failed_jobs":0,"open_abuse":0,"active_sanctions":0,"pending_compensations":0,"active_events":0}
    if live_mode():
        try:
            ops.update(live_query("""
                SELECT
                  (SELECT count(*) FROM platform.outbox_events WHERE published_at IS NULL) AS pending_outbox,
                  (SELECT count(*) FROM platform.outbox_events WHERE published_at IS NULL AND last_error IS NOT NULL) AS failed_outbox,
                  (SELECT count(*) FROM platform.scheduled_actions WHERE status::text IN ('PENDING','RUNNING')) AS pending_jobs,
                  (SELECT count(*) FROM platform.scheduled_actions WHERE status::text='FAILED') AS failed_jobs,
                  (SELECT count(*) FROM ops.abuse_signals WHERE reviewed_at IS NULL) AS open_abuse,
                  (SELECT count(*) FROM ops.player_sanctions WHERE revoked_at IS NULL AND (ends_at IS NULL OR ends_at>now())) AS active_sanctions,
                  (SELECT count(*) FROM ops.compensation_cases WHERE status='PENDING') AS pending_compensations,
                  (SELECT count(*) FROM liveops.events WHERE status IN ('SCHEDULED','OPEN','ACTIVE','RUNNING')) AS active_events
            """)[0])
        except Exception as e:
            ops["warning"] = type(e).__name__
    return {"dashboard":base,"data_quality":dq["summary"],"operations":ops,"mode":"live" if live_mode() else "snapshot","write_enabled":WRITE_ENABLED and live_mode(),"media_backend":effective_media_backend()}


@app.get("/api/data-quality")
def data_quality() -> dict[str, Any]:
    return _data_quality_report()


@app.get("/api/global-search")
def global_search(q: str = Query(..., min_length=2, max_length=160), limit: int = Query(80, ge=1, le=300)) -> dict[str, Any]:
    needle = q.strip().lower()
    results: list[dict[str, Any]] = []
    # Items
    for row in items():
        hay = " ".join(str(row.get(k) or "") for k in ("item_code","code","item_name","display_name_vi","rarity","equipment_slot","set_code","set_name")).lower()
        if needle in hay:
            results.append({"type":"ITEM","id":str(row.get("item_def_id") or row.get("id") or ""),"title":row.get("item_name") or row.get("display_name_vi") or row.get("item_code") or row.get("code"),"subtitle":f"{row.get('item_code') or row.get('code')} • {row.get('rarity')} • {row.get('equipment_slot')}","route":"items","image_url":row.get("image_url")})
            if len(results)>=limit: break
    if len(results) < limit:
        for row in players():
            hay = json.dumps(_json_safe(row), ensure_ascii=False).lower()
            if needle in hay:
                results.append({"type":"PLAYER","id":str(row.get("player_id") or row.get("id") or ""),"title":row.get("display_name") or row.get("player_name") or row.get("hero_name") or "Player","subtitle":f"Hero: {row.get('hero_name') or '—'} • Discord: {row.get('discord_username') or row.get('discord_user_id') or '—'}","route":"players"})
                if len(results)>=limit: break
    if len(results) < limit:
        for row in sets():
            hay = json.dumps(_json_safe(row), ensure_ascii=False).lower()
            if needle in hay:
                results.append({"type":"SET","id":str(row.get("set_code") or ""),"title":row.get("set_name") or row.get("set_code"),"subtitle":f"{row.get('set_code')} • {row.get('rarity')}","route":"sets"})
                if len(results)>=limit: break
    return {"query":q,"count":len(results),"results":results[:limit]}


@app.get("/api/export/items.csv")
def export_items_csv() -> Response:
    rows = items()
    fields = ["item_def_id","item_code","item_name","rarity","equipment_slot","family_code","set_code","set_name","affix_combo_code","image_asset_key","transferable","tags","base_stats","base_effects"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        x = dict(r)
        for k in ("tags","base_stats","base_effects"):
            if isinstance(x.get(k),(dict,list)):
                x[k] = json.dumps(x[k], ensure_ascii=False, separators=(",",":"))
        w.writerow(x)
    return Response(content='\ufeff'+buf.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition":"attachment; filename=lost_kingsland_items.csv"})


@app.get("/api/export/config.json")
def export_config_json() -> Response:
    payload: dict[str, Any] = {"exported_at":datetime.now(timezone.utc).isoformat(),"mode":"live" if live_mode() else "snapshot","resources":{}}
    for key,cfg in CRUD_RESOURCES.items():
        full = cfg["table"]
        if full not in KNOWN_TABLES: continue
        if live_mode():
            schema, table = split_table(full)
            try: rows = live_query(f'SELECT * FROM "{schema}"."{table}" LIMIT 10000')
            except Exception: rows=[]
        else:
            rows = [dict(r) for r in SNAPSHOT.get("tables",{}).get(full,[])]
        payload["resources"][key] = {"table":full,"label":cfg["label"],"rows":_json_safe(rows)}
    raw=json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    return Response(content=raw, media_type="application/json; charset=utf-8", headers={"Content-Disposition":"attachment; filename=lost_kingsland_config_export.json"})


@app.get("/api/export/snapshot.json")
def export_snapshot_json() -> Response:
    if live_mode():
        payload={"meta":{"source":"LIVE_ADMIN_EXPORT","exported_at":datetime.now(timezone.utc).isoformat()},"derived":{"dashboard":dashboard()},"tables":{}}
        for full in sorted(KNOWN_TABLES):
            schema, table = split_table(full)
            try: payload["tables"][full]=_json_safe(live_query(f'SELECT * FROM "{schema}"."{table}" LIMIT 20000'))
            except Exception as e: payload["tables"][full]={"error":type(e).__name__}
    else:
        payload=SNAPSHOT
    raw=json.dumps(payload,ensure_ascii=False,indent=2,default=str)
    return Response(content=raw, media_type="application/json; charset=utf-8", headers={"Content-Disposition":"attachment; filename=lost_kingsland_admin_snapshot.json"})


def media_link_table_exists() -> bool:
    return _table_exists("platform.entity_media_links")


def _media_gallery_rows(item_def_id: str) -> list[dict[str, Any]]:
    if live_mode() and media_link_table_exists():
        rows=live_query("""
            SELECT l.asset_key,l.media_role,l.sort_order,l.is_primary,l.created_at,
                   a.content_type,a.sha256,a.size_bytes,a.width,a.height,a.original_filename,a.updated_at
            FROM platform.entity_media_links l
            JOIN platform.media_assets a ON a.asset_key=l.asset_key
            WHERE l.entity_type='ITEM_DEF' AND l.entity_id=%s
            ORDER BY l.is_primary DESC,l.sort_order,l.created_at
        """,(item_def_id,))
        for r in rows: r["url"]=media_url_for_key(r.get("asset_key"))
        return rows
    # Compatibility fallback: a single primary image still works without the v4 gallery patch.
    if live_mode():
        rows=live_query("SELECT image_asset_key FROM inventory.item_defs WHERE id=%s::uuid",(item_def_id,))
        key=rows[0].get("image_asset_key") if rows else None
    else:
        row=next((r for r in SNAPSHOT.get("tables",{}).get("inventory.item_defs",[]) if str(r.get("id"))==str(item_def_id)),None)
        key=row.get("image_asset_key") if row else None
    return [{"asset_key":key,"media_role":"PRIMARY","sort_order":0,"is_primary":True,"url":media_url_for_key(key)}] if key else []


@app.get("/api/items/{item_def_id}/gallery")
def item_gallery(item_def_id: str) -> dict[str, Any]:
    return {"item_def_id":item_def_id,"gallery_enabled":media_link_table_exists(),"rows":_media_gallery_rows(item_def_id)}


@app.post("/api/items/{item_def_id}/gallery")
async def upload_item_gallery_image(item_def_id: str, role: str = Query("GALLERY", max_length=32), file: UploadFile = File(...), x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available(); require_write_token(x_admin_token)
    if not media_link_table_exists():
        raise HTTPException(status_code=409, detail="Apply sql/32_entity_media_links.sql to enable multi-image gallery. Primary direct upload still works without it.")
    raw=await file.read(MAX_IMAGE_BYTES+1)
    if not raw or len(raw)>MAX_IMAGE_BYTES: raise HTTPException(status_code=413,detail=f"Empty image or larger than {MAX_IMAGE_MB} MB.")
    webp,width,height=_process_image_to_webp(raw)
    digest=hashlib.sha256(webp).hexdigest()
    role=re.sub(r'[^A-Z0-9_]+','_',role.upper()).strip('_') or 'GALLERY'
    asset_key=f"items/{item_def_id}/{role.lower()}-{digest[:20]}.webp"
    actor=x_admin_actor or ADMIN_ACTOR_DEFAULT
    assert psycopg is not None and dict_row is not None
    with psycopg.connect(DATABASE_URL,row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id::text,code,image_asset_key FROM inventory.item_defs WHERE id=%s::uuid FOR UPDATE",(item_def_id,))
            item=cur.fetchone()
            if item is None: raise HTTPException(status_code=404,detail="Item definition not found.")
            _write_db_media(cur,asset_key=asset_key,content=webp,content_type="image/webp",sha256=digest,width=width,height=height,original_filename=file.filename,actor=actor)
            cur.execute("SELECT COALESCE(max(sort_order),0)+1 AS n FROM platform.entity_media_links WHERE entity_type='ITEM_DEF' AND entity_id=%s",(item_def_id,))
            n=int(cur.fetchone()["n"])
            cur.execute("""INSERT INTO platform.entity_media_links(entity_type,entity_id,asset_key,media_role,sort_order,is_primary,created_by)
                         VALUES('ITEM_DEF',%s,%s,%s,%s,false,%s)
                         ON CONFLICT(entity_type,entity_id,asset_key) DO UPDATE SET media_role=EXCLUDED.media_role,sort_order=EXCLUDED.sort_order""",(item_def_id,asset_key,role,n,actor))
            audit_write(cur,actor=actor,action="ITEM_GALLERY_UPLOAD",object_type="inventory.item_defs",object_id=item_def_id,before=None,after={"asset_key":asset_key,"role":role},reason="ADMIN_DIRECT_UPLOAD")
            conn.commit()
    return {"ok":True,"asset_key":asset_key,"role":role,"url":media_url_for_key(asset_key),"width":width,"height":height,"size_bytes":len(webp)}


@app.post("/api/items/{item_def_id}/gallery/primary")
def set_item_gallery_primary(item_def_id: str, payload: dict[str, Any], x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available(); require_write_token(x_admin_token)
    if not media_link_table_exists(): raise HTTPException(status_code=409,detail="Gallery DB patch is not installed.")
    asset_key=str(payload.get("asset_key") or "").strip()
    if not asset_key: raise HTTPException(status_code=400,detail="asset_key is required.")
    actor=x_admin_actor or ADMIN_ACTOR_DEFAULT
    assert psycopg is not None and dict_row is not None
    with psycopg.connect(DATABASE_URL,row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM inventory.item_defs WHERE id=%s::uuid FOR UPDATE",(item_def_id,)); before=cur.fetchone()
            if before is None: raise HTTPException(status_code=404,detail="Item definition not found.")
            cur.execute("SELECT 1 FROM platform.entity_media_links WHERE entity_type='ITEM_DEF' AND entity_id=%s AND asset_key=%s",(item_def_id,asset_key))
            if cur.fetchone() is None: raise HTTPException(status_code=404,detail="Asset is not linked to this item.")
            cur.execute("UPDATE platform.entity_media_links SET is_primary=false, media_role=CASE WHEN media_role='PRIMARY' THEN 'GALLERY' ELSE media_role END WHERE entity_type='ITEM_DEF' AND entity_id=%s",(item_def_id,))
            cur.execute("UPDATE platform.entity_media_links SET is_primary=true,media_role='PRIMARY' WHERE entity_type='ITEM_DEF' AND entity_id=%s AND asset_key=%s",(item_def_id,asset_key))
            cur.execute("UPDATE inventory.item_defs SET image_asset_key=%s WHERE id=%s::uuid RETURNING *",(asset_key,item_def_id)); after=cur.fetchone()
            audit_write(cur,actor=actor,action="ITEM_IMAGE_SET_PRIMARY",object_type="inventory.item_defs",object_id=item_def_id,before=dict(before),after=dict(after),reason="ADMIN_MEDIA_GALLERY")
            conn.commit()
    return {"ok":True,"asset_key":asset_key,"image_url":media_url_for_key(asset_key)}


@app.delete("/api/items/{item_def_id}/gallery")
def delete_item_gallery_image(item_def_id: str, asset_key: str = Query(...), x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available(); require_write_token(x_admin_token)
    if not media_link_table_exists(): raise HTTPException(status_code=409,detail="Gallery DB patch is not installed.")
    actor=x_admin_actor or ADMIN_ACTOR_DEFAULT
    assert psycopg is not None and dict_row is not None
    with psycopg.connect(DATABASE_URL,row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT image_asset_key FROM inventory.item_defs WHERE id=%s::uuid FOR UPDATE",(item_def_id,)); item=cur.fetchone()
            if item is None: raise HTTPException(status_code=404,detail="Item definition not found.")
            if item.get("image_asset_key")==asset_key: raise HTTPException(status_code=409,detail="Không xóa trực tiếp ảnh PRIMARY. Hãy chọn ảnh khác làm primary hoặc dùng nút Xóa ảnh chính.")
            cur.execute("DELETE FROM platform.entity_media_links WHERE entity_type='ITEM_DEF' AND entity_id=%s AND asset_key=%s RETURNING asset_key",(item_def_id,asset_key))
            deleted=cur.fetchone()
            if deleted is None: raise HTTPException(status_code=404,detail="Gallery image link not found.")
            cur.execute("SELECT count(*) AS c FROM platform.entity_media_links WHERE asset_key=%s",(asset_key,)); link_count=int(cur.fetchone()["c"])
            cur.execute("SELECT count(*) AS c FROM inventory.item_defs WHERE image_asset_key=%s",(asset_key,)); primary_count=int(cur.fetchone()["c"])
            if link_count==0 and primary_count==0: cur.execute("DELETE FROM platform.media_assets WHERE asset_key=%s",(asset_key,))
            audit_write(cur,actor=actor,action="ITEM_GALLERY_DELETE",object_type="inventory.item_defs",object_id=item_def_id,before={"asset_key":asset_key},after=None,reason="ADMIN_MEDIA_GALLERY")
            conn.commit()
    return {"ok":True,"deleted_asset_key":asset_key}


@app.post("/api/items/images/archive")
async def bulk_upload_item_images_archive(file: UploadFile = File(...), x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available(); require_write_token(x_admin_token)
    raw=await file.read(250*1024*1024+1)
    if len(raw)>250*1024*1024: raise HTTPException(status_code=413,detail="ZIP lớn hơn 250 MB.")
    actor=x_admin_actor or ADMIN_ACTOR_DEFAULT
    results=[]
    try:
        z=zipfile.ZipFile(io.BytesIO(raw))
    except Exception:
        raise HTTPException(status_code=400,detail="File không phải ZIP hợp lệ.")
    names=[n for n in z.namelist() if not n.endswith('/') and Path(n).suffix.lower() in {'.png','.jpg','.jpeg','.webp','.gif'}]
    if len(names)>1000: raise HTTPException(status_code=400,detail="ZIP tối đa 1000 ảnh.")
    for name in names:
        code=Path(name).stem.strip()
        rows=live_query("SELECT id::text AS id,code FROM inventory.item_defs WHERE upper(code)=upper(%s) LIMIT 2",(code,))
        if len(rows)!=1:
            results.append({"filename":name,"item_code":code,"ok":False,"error":"No unique item code matched filename stem."}); continue
        try:
            img=z.read(name)
            if not img or len(img)>MAX_IMAGE_BYTES: raise ValueError(f"Empty or > {MAX_IMAGE_MB} MB")
            saved=_persist_item_image(rows[0]["id"],raw=img,original_filename=Path(name).name,actor=actor)
            results.append({"filename":name,"item_code":rows[0]["code"],"ok":True,**saved})
        except Exception as e:
            results.append({"filename":name,"item_code":code,"ok":False,"error":str(getattr(e,'detail',e))})
    return {"ok":all(r.get('ok') for r in results) if results else True,"total":len(results),"success":sum(1 for r in results if r.get('ok')),"failed":sum(1 for r in results if not r.get('ok')),"results":results}


@app.get("/api/media/health")
def media_health() -> dict[str, Any]:
    rows=media_assets(2000)
    assets=rows.get("rows",[])
    dup: dict[str,list[str]]={}
    for a in assets:
        if a.get("sha256"): dup.setdefault(str(a["sha256"]),[]).append(str(a.get("asset_key")))
    duplicates=[{"sha256":k,"asset_keys":v,"count":len(v)} for k,v in dup.items() if len(v)>1]
    primary_refs: set[str]=set()
    gallery_refs: set[str]=set()
    if live_mode():
        try: primary_refs={str(r["image_asset_key"]) for r in live_query("SELECT image_asset_key FROM inventory.item_defs WHERE image_asset_key IS NOT NULL")}
        except Exception: pass
        if media_link_table_exists():
            try: gallery_refs={str(r["asset_key"]) for r in live_query("SELECT DISTINCT asset_key FROM platform.entity_media_links")}
            except Exception: pass
    else:
        primary_refs={str(r.get("image_asset_key")) for r in SNAPSHOT.get("tables",{}).get("inventory.item_defs",[]) if r.get("image_asset_key")}
    all_refs=primary_refs|gallery_refs
    orphans=[a for a in assets if str(a.get("asset_key")) not in all_refs]
    return {"backend":rows.get("backend"),"asset_count":len(assets),"primary_reference_count":len(primary_refs),"gallery_reference_count":len(gallery_refs),"orphan_count":len(orphans),"duplicate_group_count":len(duplicates),"orphans":orphans[:500],"duplicates":duplicates[:200]}


@app.delete("/api/media/assets")
def delete_orphan_media_asset(asset_key: str = Query(...), x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available(); require_write_token(x_admin_token)
    if effective_media_backend()!="database": raise HTTPException(status_code=409,detail="Orphan cleanup endpoint requires database media backend.")
    actor=x_admin_actor or ADMIN_ACTOR_DEFAULT
    assert psycopg is not None and dict_row is not None
    with psycopg.connect(DATABASE_URL,row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS c FROM inventory.item_defs WHERE image_asset_key=%s",(asset_key,)); c=int(cur.fetchone()["c"])
            if media_link_table_exists():
                cur.execute("SELECT count(*) AS c FROM platform.entity_media_links WHERE asset_key=%s",(asset_key,)); c+=int(cur.fetchone()["c"])
            if c: raise HTTPException(status_code=409,detail=f"Asset đang được tham chiếu {c} lần; không thể xóa.")
            cur.execute("DELETE FROM platform.media_assets WHERE asset_key=%s RETURNING asset_key",(asset_key,)); row=cur.fetchone()
            if row is None: raise HTTPException(status_code=404,detail="Media asset not found.")
            audit_write(cur,actor=actor,action="MEDIA_ORPHAN_DELETE",object_type="platform.media_assets",object_id=asset_key,before={"asset_key":asset_key},after=None,reason="ADMIN_MEDIA_CLEANUP")
            conn.commit()
    return {"ok":True,"asset_key":asset_key}


@app.post("/api/support/players/{player_id}/compensation")
def create_compensation_case(player_id: str, payload: dict[str, Any], x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available(); require_write_token(x_admin_token)
    actor=x_admin_actor or ADMIN_ACTOR_DEFAULT
    reason=str(payload.get("reason_code") or "").strip()
    bundle=payload.get("reward_bundle")
    evidence=payload.get("evidence_json") or {}
    if not reason or not isinstance(bundle,(dict,list)): raise HTTPException(status_code=400,detail="reason_code và reward_bundle JSON là bắt buộc.")
    assert psycopg is not None and dict_row is not None and Jsonb is not None
    with psycopg.connect(DATABASE_URL,row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM identity.players WHERE id=%s::uuid",(player_id,))
            if cur.fetchone() is None: raise HTTPException(status_code=404,detail="Player not found.")
            cur.execute("""INSERT INTO ops.compensation_cases(player_id,reason_code,evidence_json,reward_bundle,requested_by,status)
                         VALUES(%s::uuid,%s,%s,%s,%s,'PENDING') RETURNING *""",(player_id,reason,Jsonb(evidence),Jsonb(bundle),actor))
            row=dict(cur.fetchone())
            audit_write(cur,actor=actor,action="COMPENSATION_CASE_CREATE",object_type="ops.compensation_cases",object_id=str(row["id"]),before=None,after=row,reason=reason)
            conn.commit()
    return _json_safe(row)


@app.post("/api/support/players/{player_id}/sanctions")
def create_player_sanction(player_id: str, payload: dict[str, Any], x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available(); require_write_token(x_admin_token)
    actor=x_admin_actor or ADMIN_ACTOR_DEFAULT
    sanction=str(payload.get("sanction_type") or "").strip().upper(); reason=str(payload.get("reason_code") or "").strip(); evidence=payload.get("evidence_json") or {}; ends_at=payload.get("ends_at")
    if not sanction or not reason: raise HTTPException(status_code=400,detail="sanction_type và reason_code là bắt buộc.")
    assert psycopg is not None and dict_row is not None and Jsonb is not None
    with psycopg.connect(DATABASE_URL,row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM identity.players WHERE id=%s::uuid",(player_id,))
            if cur.fetchone() is None: raise HTTPException(status_code=404,detail="Player not found.")
            cur.execute("""INSERT INTO ops.player_sanctions(player_id,sanction_type,reason_code,evidence_json,ends_at,created_by)
                         VALUES(%s::uuid,%s,%s,%s,%s,%s) RETURNING *""",(player_id,sanction,reason,Jsonb(evidence),ends_at or None,actor))
            row=dict(cur.fetchone())
            audit_write(cur,actor=actor,action="PLAYER_SANCTION_CREATE",object_type="ops.player_sanctions",object_id=str(row["id"]),before=None,after=row,reason=reason)
            conn.commit()
    return _json_safe(row)


@app.post("/api/support/sanctions/{sanction_id}/revoke")
def revoke_player_sanction(sanction_id: str, payload: dict[str, Any] | None = None, x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available(); require_write_token(x_admin_token)
    actor=x_admin_actor or ADMIN_ACTOR_DEFAULT
    assert psycopg is not None and dict_row is not None
    with psycopg.connect(DATABASE_URL,row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM ops.player_sanctions WHERE id=%s::uuid FOR UPDATE",(sanction_id,)); before=cur.fetchone()
            if before is None: raise HTTPException(status_code=404,detail="Sanction not found.")
            cur.execute("UPDATE ops.player_sanctions SET revoked_at=COALESCE(revoked_at,now()) WHERE id=%s::uuid RETURNING *",(sanction_id,)); after=dict(cur.fetchone())
            audit_write(cur,actor=actor,action="PLAYER_SANCTION_REVOKE",object_type="ops.player_sanctions",object_id=sanction_id,before=dict(before),after=after,reason=str((payload or {}).get("reason_code") or "ADMIN_REVOKE"))
            conn.commit()
    return _json_safe(after)


# ---------------------------------------------------------------------------
# V6 MegaOps — Gift Code Studio, Player Control Center and Character Artwork.
# ---------------------------------------------------------------------------

PLAYER_EDIT_TARGETS: dict[str, dict[str, Any]] = {
    "account": {"table":"identity.players","pk":"id","owner":"self","allowed":{
        "display_name","account_level","account_xp","avatar_key","active_screen_key","tutorial_step"}},
    "account-settings": {"table":"identity.accounts","pk":"id","owner":"account","allowed":{"status","locale","timezone"}},
    "hero": {"table":"hero.player_heroes","pk":"id","owner":"player_id","allowed":{
        "name","level","xp","race_code","path_code","realm_code","realm_minor_stage","cultivation_qi","cultivation_progress",
        "tribulation_fail_streak","lifetime_voice_cultivation_qi","sect_code","sect_rank","sect_reputation","last_tribulation_state"}},
    "energy": {"table":"adventure.energy_balances","pk":"player_id","owner":"self","allowed":{"current_value","cap_value","regen_seconds","last_regen_at"}},
    "exploration": {"table":"adventure.player_exploration_progress","pk":"player_id","owner":"self","allowed":{"current_floor","highest_floor"}},
    "commander": {"table":"commander.player_commanders","pk":"id","owner":"player_id","allowed":{"level","xp","star_level","status"}},
    "character": {"table":"hero.player_characters","pk":"id","owner":"player_id","allowed":{"native_level","native_xp","level_sync_enabled","ascension_rank"}},
    "item": {"table":"inventory.item_instances","pk":"id","owner":"owner_player_id","allowed":{"rarity","item_level","state","durability","locked","affixes","unique_effects"}},
    "kingdom-building": {"table":"kingdom.kingdom_buildings","pk":"id","owner":"kingdom_join","allowed":{"level","state_json"}},
}


def _giftcode_ready() -> bool:
    return _table_exists("liveops.gift_codes") and _table_exists("liveops.gift_code_redemptions")


def _normalize_gift_code(code: str) -> str:
    code = re.sub(r"[^A-Z0-9_-]+", "", (code or "").strip().upper())
    if not (4 <= len(code) <= 64):
        raise HTTPException(status_code=400, detail="Gift code phải dài 4–64 ký tự và chỉ dùng A-Z, 0-9, _ hoặc -.")
    return code


def _generate_gift_code(prefix: str = "LK", length: int = 12) -> str:
    prefix = re.sub(r"[^A-Z0-9]+", "", (prefix or "LK").upper())[:12] or "LK"
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    n = max(6, min(32, int(length)))
    return f"{prefix}-" + "".join(secrets.choice(alphabet) for _ in range(n))


def _validate_giftcode_reward_contract(reward: Any) -> int:
    if not isinstance(reward,dict): raise HTTPException(status_code=400,detail="reward_bundle phải là JSON object.")
    assets=reward.get("assets") or {}; items=reward.get("items") or []; titles=reward.get("titles") or []
    if not isinstance(assets,dict) or not isinstance(items,list) or not isinstance(titles,list): raise HTTPException(status_code=400,detail="Giftcode reward phải dùng contract assets + items + titles.")
    if not assets and not items and not titles: raise HTTPException(status_code=400,detail="Giftcode phải có ít nhất một phần thưởng.")
    for code,amount in assets.items():
        if not isinstance(code,str) or not code.strip() or not isinstance(amount,(int,float)) or isinstance(amount,bool) or amount<=0:
            raise HTTPException(status_code=400,detail=f"Asset reward không hợp lệ: {code}.")
        found=live_query("SELECT precision_scale FROM economy.asset_defs WHERE code=%s",(code.strip().upper(),))
        if not found: raise HTTPException(status_code=400,detail=f"Asset không tồn tại trong DB: {code}.")
        if int(found[0]["precision_scale"])==0 and float(amount)!=int(amount): raise HTTPException(status_code=400,detail=f"Asset {code} chỉ nhận số nguyên.")
    config=live_query("SELECT id FROM platform.config_versions WHERE version_code=%s AND status='ACTIVE'",(ADMIN_GAMEPLAY_CONFIG,))
    if not config: raise HTTPException(status_code=409,detail=f"Runtime config {ADMIN_GAMEPLAY_CONFIG} không ACTIVE trong DB.")
    config_id=int(config[0]["id"]); total=0
    for item in items:
        if not isinstance(item,dict): raise HTTPException(status_code=400,detail="Item reward phải là JSON object.")
        code=str(item.get("item_code") or "").strip(); quantity=item.get("quantity")
        if not code or not isinstance(quantity,int) or isinstance(quantity,bool) or quantity<1 or quantity>100:
            raise HTTPException(status_code=400,detail=f"Item reward không hợp lệ: {code or '(trống)'}.")
        total+=quantity
        if total>100: raise HTTPException(status_code=400,detail="Tổng item mỗi Giftcode không được vượt 100.")
        found=live_query("""SELECT item_type,stackable,display_name_vi,config_version_id FROM inventory.item_defs
                            WHERE code=%s AND catalog_status IN ('ACTIVE_CANONICAL','ACTIVE_VALID')
                              AND (config_version_id=%s OR (stackable AND item_type='CONSUMABLE'))
                            ORDER BY (config_version_id=%s) DESC,config_version_id DESC LIMIT 1""",(code,config_id,config_id))
        if not found: raise HTTPException(status_code=400,detail=f"Vật phẩm {code} không tồn tại hoặc chưa hỗ trợ trao qua giftcode.")
        if not bool(found[0]["stackable"]) and found[0]["item_type"]!="EQUIPMENT": raise HTTPException(status_code=400,detail=f"Item {code} chưa có storage grant được hỗ trợ.")
    for title in titles:
        code=str(title.get("title_code") if isinstance(title,dict) else title or "").strip().upper()
        found=live_query("SELECT display_name_vi FROM title.title_defs WHERE code=%s AND active",(code,))
        if not code or not found: raise HTTPException(status_code=400,detail=f"Danh hiệu không tồn tại hoặc đã tắt: {code or '(trống)'}.")
    return config_id


def _giftcode_effective(row: dict[str, Any], player_id: str | None = None) -> dict[str, Any]:
    out = dict(row)
    now = datetime.now(timezone.utc)
    start = out.get("starts_at"); end = out.get("ends_at")
    status = str(out.get("status") or "DRAFT")
    if status == "ARCHIVED": effective = "ARCHIVED"
    elif status == "PAUSED": effective = "PAUSED"
    elif end and end <= now: effective = "EXPIRED"
    elif start and start > now: effective = "SCHEDULED"
    elif status == "ACTIVE": effective = "ACTIVE"
    else: effective = status
    out["effective_status"] = effective
    max_r = out.get("max_redemptions")
    out["remaining_redemptions"] = None if max_r is None else max(0, int(max_r) - int(out.get("redemption_count") or 0))
    return out


@app.get("/api/giftcodes/title-options")
def giftcode_title_options() -> dict[str, Any]:
    ensure_live_available()
    rows=live_query("""SELECT code,display_name_vi,source_type,realm_ordinal,active,artwork_asset_key
                       FROM title.title_defs WHERE active
                       ORDER BY realm_ordinal NULLS LAST,display_name_vi""")
    return {"rows":[_json_safe(enrich_media(row)) for row in rows]}


@app.get("/api/giftcodes")
def giftcodes(q: str = Query(""), status: str = Query(""), limit: int = Query(500, ge=1, le=2000)) -> dict[str, Any]:
    ensure_live_available()
    if not _giftcode_ready():
        raise HTTPException(status_code=409, detail="Chưa cài sql/50_giftcode_player_control.sql.")
    where=[]; args=[]
    if q.strip():
        where.append("(code ILIKE %s OR display_name ILIKE %s OR COALESCE(description,'') ILIKE %s)")
        like=f"%{q.strip()}%"; args.extend([like,like,like])
    if status.strip():
        where.append("status=%s"); args.append(status.strip().upper())
    sql="SELECT * FROM liveops.gift_codes" + (" WHERE "+" AND ".join(where) if where else "") + " ORDER BY updated_at DESC LIMIT %s"
    args.append(limit)
    rows=live_query(sql, tuple(args))
    return {"ready":True,"rows":[_json_safe(_giftcode_effective(r)) for r in rows],"total":len(rows)}


@app.get("/api/giftcodes/stats")
def giftcode_stats() -> dict[str, Any]:
    ensure_live_available()
    if not _giftcode_ready(): return {"ready":False,"total":0,"active":0,"redemptions":0,"granted":0,"pending":0}
    g=live_query("SELECT count(*) AS total,count(*) FILTER(WHERE status='ACTIVE') AS active,count(*) FILTER(WHERE status='DRAFT') AS draft,count(*) FILTER(WHERE status='PAUSED') AS paused FROM liveops.gift_codes")[0]
    r=live_query("SELECT count(*) AS total,count(*) FILTER(WHERE status='GRANTED') AS granted,count(*) FILTER(WHERE status='PENDING_GRANT') AS pending,count(DISTINCT player_id) AS players FROM liveops.gift_code_redemptions")[0]
    return {"ready":True,"total":g["total"],"active":g["active"],"draft":g["draft"],"paused":g["paused"],"redemptions":r["total"],"granted":r["granted"],"pending":r["pending"],"unique_players":r["players"]}


@app.get("/api/giftcodes/runtime")
def giftcode_runtime() -> dict[str, Any]:
    ensure_live_available()
    if not _giftcode_ready(): return {"ready":False,"reason":"TABLES_MISSING"}
    state=live_query("""SELECT current_database() AS database_name,
                       (SELECT version FROM flyway_schema_history WHERE success ORDER BY installed_rank DESC LIMIT 1) AS flyway,
                       (SELECT id FROM platform.config_versions WHERE version_code=%s AND status='ACTIVE') AS config_version_id""",(ADMIN_GAMEPLAY_CONFIG,))[0]
    flyway=str(state.get("flyway") or "")
    return _json_safe({"ready":flyway.isdigit() and int(flyway)>=42 and state.get("config_version_id") is not None,
                       "database_name":state.get("database_name"),"flyway":flyway,
                       "gameplay_config":ADMIN_GAMEPLAY_CONFIG,"config_version_id":state.get("config_version_id"),
                       "redemption_command":"/giftcode"})


@app.post("/api/giftcodes/generate")
def generate_giftcode(payload: dict[str, Any] | None = None, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    require_write_token(x_admin_token)
    p=payload or {}
    return {"code":_generate_gift_code(str(p.get("prefix") or "LK"), int(p.get("length") or 12))}


@app.post("/api/giftcodes")
def create_giftcode(payload: dict[str, Any], x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available(); require_write_token(x_admin_token)
    if not _giftcode_ready(): raise HTTPException(status_code=409, detail="Chưa cài sql/50_giftcode_player_control.sql.")
    code=_normalize_gift_code(str(payload.get("code") or "")); name=str(payload.get("display_name") or code).strip()[:160]
    status=str(payload.get("status") or "DRAFT").upper(); actor=x_admin_actor or ADMIN_ACTOR_DEFAULT
    if status not in {"DRAFT","ACTIVE","PAUSED","EXPIRED","ARCHIVED"}: raise HTTPException(status_code=400,detail="Gift code status không hợp lệ.")
    reward=payload.get("reward_bundle") or {}; elig=payload.get("eligibility_json") or {}; tags=payload.get("tags") or []
    if not isinstance(reward,dict) or not isinstance(elig,dict): raise HTTPException(status_code=400,detail="reward_bundle và eligibility_json phải là JSON object.")
    config_id=_validate_giftcode_reward_contract(reward)
    if isinstance(tags,str): tags=[x.strip() for x in tags.split(',') if x.strip()]
    assert psycopg is not None and dict_row is not None and Jsonb is not None
    with psycopg.connect(DATABASE_URL,row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("""INSERT INTO liveops.gift_codes(code,display_name,description,status,starts_at,ends_at,max_redemptions,per_player_limit,reward_bundle,eligibility_json,tags,config_version_id,created_by,updated_by)
                             VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                            (code,name,payload.get("description") or None,status,payload.get("starts_at") or None,payload.get("ends_at") or None,
                             payload.get("max_redemptions") or None,int(payload.get("per_player_limit") or 1),Jsonb(reward),Jsonb(elig),tags,config_id,actor,actor))
                row=dict(cur.fetchone())
            except Exception as e:
                if "ux_gift_codes_upper_code" in str(e) or "duplicate" in str(e).lower(): raise HTTPException(status_code=409,detail="Gift code đã tồn tại.")
                raise
            audit_write(cur,actor=actor,action="GIFT_CODE_CREATE",object_type="liveops.gift_codes",object_id=str(row["id"]),before=None,after=row,reason="ADMIN_GIFTCODE")
            conn.commit()
    return _json_safe(_giftcode_effective(row))


@app.patch("/api/giftcodes/{gift_code_id}")
def update_giftcode(gift_code_id: str, payload: dict[str, Any], x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available(); require_write_token(x_admin_token)
    if not _giftcode_ready(): raise HTTPException(status_code=409, detail="Chưa cài sql/50_giftcode_player_control.sql.")
    allowed={"code","display_name","description","status","starts_at","ends_at","max_redemptions","per_player_limit","reward_bundle","eligibility_json","tags"}
    data={k:v for k,v in payload.items() if k in allowed}
    if not data: raise HTTPException(status_code=400,detail="Không có field được phép sửa.")
    if "code" in data: data["code"]=_normalize_gift_code(str(data["code"]))
    if "status" in data:
        data["status"]=str(data["status"]).upper()
        if data["status"] not in {"DRAFT","ACTIVE","PAUSED","EXPIRED","ARCHIVED"}: raise HTTPException(status_code=400,detail="Gift code status không hợp lệ.")
    if "per_player_limit" in data: data["per_player_limit"]=max(1,int(data["per_player_limit"]))
    if "max_redemptions" in data and data["max_redemptions"] in ("",0,"0"): data["max_redemptions"]=None
    if "tags" in data and isinstance(data["tags"],str): data["tags"]=[x.strip() for x in data["tags"].split(',') if x.strip()]
    if "reward_bundle" in data: data["config_version_id"]=_validate_giftcode_reward_contract(data["reward_bundle"])
    elif data.get("status")=="ACTIVE":
        current=live_query("SELECT reward_bundle FROM liveops.gift_codes WHERE id=%s::uuid",(gift_code_id,))
        if not current: raise HTTPException(status_code=404,detail="Gift code không tồn tại.")
        data["config_version_id"]=_validate_giftcode_reward_contract(current[0]["reward_bundle"])
    actor=x_admin_actor or ADMIN_ACTOR_DEFAULT
    assert psycopg is not None and dict_row is not None and Jsonb is not None
    with psycopg.connect(DATABASE_URL,row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM liveops.gift_codes WHERE id=%s::uuid FOR UPDATE",(gift_code_id,)); before=cur.fetchone()
            if before is None: raise HTTPException(status_code=404,detail="Gift code không tồn tại.")
            sets=[]; vals=[]
            for k,v in data.items():
                sets.append(f'"{k}"=%s')
                vals.append(Jsonb(v) if k in {"reward_bundle","eligibility_json"} else v)
            sets += ["updated_by=%s","updated_at=now()","version=version+1"]; vals.append(actor); vals.append(gift_code_id)
            cur.execute(f"UPDATE liveops.gift_codes SET {','.join(sets)} WHERE id=%s::uuid RETURNING *",tuple(vals)); after=dict(cur.fetchone())
            audit_write(cur,actor=actor,action="GIFT_CODE_UPDATE",object_type="liveops.gift_codes",object_id=gift_code_id,before=dict(before),after=after,reason="ADMIN_GIFTCODE")
            conn.commit()
    return _json_safe(_giftcode_effective(after))


@app.delete("/api/giftcodes/{gift_code_id}")
def archive_giftcode(gift_code_id: str, x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available(); require_write_token(x_admin_token); actor=x_admin_actor or ADMIN_ACTOR_DEFAULT
    assert psycopg is not None and dict_row is not None
    with psycopg.connect(DATABASE_URL,row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM liveops.gift_codes WHERE id=%s::uuid FOR UPDATE",(gift_code_id,)); before=cur.fetchone()
            if before is None: raise HTTPException(status_code=404,detail="Gift code không tồn tại.")
            cur.execute("UPDATE liveops.gift_codes SET status='ARCHIVED',updated_by=%s,updated_at=now(),version=version+1 WHERE id=%s::uuid RETURNING *",(actor,gift_code_id)); after=dict(cur.fetchone())
            audit_write(cur,actor=actor,action="GIFT_CODE_ARCHIVE",object_type="liveops.gift_codes",object_id=gift_code_id,before=dict(before),after=after,reason="ADMIN_GIFTCODE")
            conn.commit()
    return _json_safe(after)


@app.get("/api/giftcodes/{gift_code_id}/redemptions")
def giftcode_redemptions(gift_code_id: str, limit: int = Query(500, ge=1, le=2000)) -> dict[str, Any]:
    ensure_live_available()
    if not _giftcode_ready(): raise HTTPException(status_code=409,detail="Giftcode tables chưa được cài.")
    rows=live_query("""SELECT r.*,p.display_name AS player_name FROM liveops.gift_code_redemptions r JOIN identity.players p ON p.id=r.player_id WHERE r.gift_code_id=%s::uuid ORDER BY r.redeemed_at DESC LIMIT %s""",(gift_code_id,limit))
    return {"rows":_json_safe(rows),"total":len(rows)}


@app.post("/api/giftcodes/validate")
def validate_giftcode(payload: dict[str, Any]) -> dict[str, Any]:
    """Read-only eligibility preview. Bot can reuse the same rules later; no rewards are granted here."""
    ensure_live_available()
    if not _giftcode_ready(): raise HTTPException(status_code=409,detail="Giftcode tables chưa được cài.")
    code=_normalize_gift_code(str(payload.get("code") or "")); player_id=str(payload.get("player_id") or "").strip() or None
    rows=live_query("SELECT * FROM liveops.gift_codes WHERE upper(code)=upper(%s) LIMIT 1",(code,))
    if not rows: return {"valid":False,"reason":"CODE_NOT_FOUND","code":code}
    g=_giftcode_effective(rows[0],player_id)
    if g["effective_status"]!="ACTIVE": return {"valid":False,"reason":f"CODE_{g['effective_status']}","gift_code":_json_safe(g)}
    if g.get("max_redemptions") is not None and int(g.get("redemption_count") or 0)>=int(g["max_redemptions"]): return {"valid":False,"reason":"GLOBAL_LIMIT_REACHED","gift_code":_json_safe(g)}
    player_count=0
    if player_id:
        p=live_query("""SELECT p.account_level,a.status AS account_status,COALESCE(ep.highest_floor,1) AS highest_floor
                        FROM identity.players p JOIN identity.accounts a ON a.id=p.account_id
                        LEFT JOIN adventure.player_exploration_progress ep ON ep.player_id=p.id
                        WHERE p.id=%s::uuid""",(player_id,))
        if not p: return {"valid":False,"reason":"PLAYER_NOT_FOUND","gift_code":_json_safe(g)}
        c=live_query("SELECT count(*) AS c FROM liveops.gift_code_redemptions WHERE gift_code_id=%s::uuid AND player_id=%s::uuid AND status IN ('PENDING_GRANT','GRANTED')",(g["id"],player_id))[0]
        player_count=int(c["c"])
        if player_count>=int(g.get("per_player_limit") or 1): return {"valid":False,"reason":"PLAYER_LIMIT_REACHED","player_redemptions":player_count,"gift_code":_json_safe(g)}
        elig=g.get("eligibility_json") or {}
        if isinstance(elig,dict):
            min_level=int(elig.get("min_account_level") or 0)
            max_level=int(elig.get("max_account_level") or 0)
            min_floor=int(elig.get("min_exploration_floor") or 0)
            required_status=str(elig.get("account_status") or "").strip().upper()
            if min_level and int(p[0].get("account_level") or 0)<min_level: return {"valid":False,"reason":"ACCOUNT_LEVEL_TOO_LOW","required":min_level,"gift_code":_json_safe(g)}
            if max_level and int(p[0].get("account_level") or 0)>max_level: return {"valid":False,"reason":"ACCOUNT_LEVEL_TOO_HIGH","required_max":max_level,"gift_code":_json_safe(g)}
            if min_floor and int(p[0].get("highest_floor") or 1)<min_floor: return {"valid":False,"reason":"EXPLORATION_FLOOR_TOO_LOW","required":min_floor,"gift_code":_json_safe(g)}
            if required_status and str(p[0].get("account_status") or "").upper()!=required_status: return {"valid":False,"reason":"ACCOUNT_STATUS_NOT_ELIGIBLE","required":required_status,"gift_code":_json_safe(g)}
    return {"valid":True,"reason":"OK","player_redemptions":player_count,"gift_code":_json_safe(g),"reward_bundle":_json_safe(g.get("reward_bundle") or {})}


def _validate_player_patch(target: str, values: dict[str, Any], current: dict[str, Any] | None = None) -> dict[str, Any]:
    v=dict(values)
    def _int(name: str, low: int | None=None, high: int | None=None):
        if name not in v or v[name] in (None,""): return
        try: n=int(v[name])
        except Exception: raise HTTPException(status_code=400,detail=f"{name} phải là số nguyên.")
        if low is not None and n<low: raise HTTPException(status_code=400,detail=f"{name} phải >= {low}.")
        if high is not None and n>high: raise HTTPException(status_code=400,detail=f"{name} phải <= {high}.")
        v[name]=n
    if target=="account": _int("account_level",1); _int("account_xp",0)
    elif target=="hero":
        _int("level",1); _int("xp",0); _int("realm_minor_stage",1,10); _int("cultivation_qi",0); _int("cultivation_progress",0); _int("tribulation_fail_streak",0); _int("lifetime_voice_cultivation_qi",0); _int("sect_rank",0); _int("sect_reputation",0)
    elif target=="energy":
        _int("current_value",0); _int("cap_value",1); _int("regen_seconds",1)
        cap=int(v.get("cap_value",(current or {}).get("cap_value") or 0)); cur=int(v.get("current_value",(current or {}).get("current_value") or 0))
        if cap and cur>cap: raise HTTPException(status_code=400,detail="Energy current_value không được lớn hơn cap_value.")
    elif target=="exploration":
        _int("current_floor",1); _int("highest_floor",1)
        cur=int(v.get("current_floor",(current or {}).get("current_floor") or 1)); hi=int(v.get("highest_floor",(current or {}).get("highest_floor") or 1))
        if hi<cur: raise HTTPException(status_code=400,detail="highest_floor phải >= current_floor.")
    elif target=="commander": _int("level",1,5000); _int("xp",0); _int("star_level",1)
    elif target=="character": _int("native_level",1); _int("native_xp",0); _int("ascension_rank",0,5)
    elif target=="item": _int("item_level",1); _int("durability",0)
    elif target=="kingdom-building": _int("level",0)
    for k in ("affixes","unique_effects","state_json"):
        if k in v and isinstance(v[k],str):
            try: v[k]=json.loads(v[k])
            except Exception: raise HTTPException(status_code=400,detail=f"{k} phải là JSON hợp lệ.")
    return v


def _fetch_player_owned_row(cur: Any, player_id: str, target: str, row_id: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
    cfg=PLAYER_EDIT_TARGETS.get(target)
    if not cfg: raise HTTPException(status_code=404,detail="Player edit target không hỗ trợ.")
    table=str(cfg["table"]); schema,name=split_table(table); pk=str(cfg["pk"]); owner=str(cfg["owner"])
    rid=row_id or player_id
    if owner=="self":
        cur.execute(f'SELECT * FROM "{schema}"."{name}" WHERE "{pk}"::text=%s FOR UPDATE',(player_id,))
    elif owner=="player_id":
        cur.execute(f'SELECT * FROM "{schema}"."{name}" WHERE "{pk}"::text=%s AND player_id=%s::uuid FOR UPDATE',(rid,player_id))
    elif owner=="owner_player_id":
        cur.execute(f'SELECT * FROM "{schema}"."{name}" WHERE "{pk}"::text=%s AND owner_player_id=%s::uuid FOR UPDATE',(rid,player_id))
    elif owner=="account":
        cur.execute(f'SELECT a.* FROM "{schema}"."{name}" a JOIN identity.players p ON p.account_id=a.id WHERE a."{pk}"::text=%s AND p.id=%s::uuid FOR UPDATE',(rid,player_id))
    elif owner=="kingdom_join":
        cur.execute(f'SELECT x.* FROM "{schema}"."{name}" x JOIN kingdom.player_kingdoms pkd ON pkd.id=x.kingdom_id WHERE x."{pk}"::text=%s AND pkd.player_id=%s::uuid FOR UPDATE',(rid,player_id))
    else: raise HTTPException(status_code=500,detail="Player edit ownership config invalid.")
    row=cur.fetchone()
    if row is None: raise HTTPException(status_code=404,detail="Không tìm thấy row thuộc player này.")
    return cfg,dict(row)


@app.patch("/api/players/{player_id}/control/{target}")
def player_control_patch(player_id: str, target: str, payload: dict[str, Any], row_id: str | None = Query(None), x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available(); require_write_token(x_admin_token); actor=x_admin_actor or ADMIN_ACTOR_DEFAULT
    reason=str(payload.get("reason_code") or "ADMIN_PLAYER_EDIT").strip()[:96]
    raw_values=payload.get("values") or {}
    if not isinstance(raw_values,dict) or not raw_values: raise HTTPException(status_code=400,detail="values JSON là bắt buộc.")
    assert psycopg is not None and dict_row is not None and Jsonb is not None
    with psycopg.connect(DATABASE_URL,row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cfg,before=_fetch_player_owned_row(cur,player_id,target,row_id)
            allowed=set(cfg["allowed"]); values={k:v for k,v in raw_values.items() if k in allowed}
            if not values: raise HTTPException(status_code=400,detail=f"Không có field được phép sửa. Allowed: {sorted(allowed)}")
            values=_validate_player_patch(target,values,before)
            meta=table_metadata(*split_table(str(cfg["table"])))
            cols={c["column_name"]:c for c in meta["columns"]}
            sets=[]; args=[]
            for k,v in values.items():
                c=cols.get(k)
                if not c: continue
                if c.get("data_type") in {"json","jsonb"} and Jsonb is not None: v=Jsonb(v)
                sets.append(f'"{k}"=%s'); args.append(v)
            if "updated_at" in cols: sets.append("updated_at=now()")
            if "version" in cols: sets.append("version=version+1")
            schema,name=split_table(str(cfg["table"])); pk=str(cfg["pk"]); rid=row_id or player_id
            args.append(rid)
            cur.execute(f'UPDATE "{schema}"."{name}" SET {", ".join(sets)} WHERE "{pk}"::text=%s RETURNING *',tuple(args)); after=cur.fetchone()
            if after is None: raise HTTPException(status_code=409,detail="Player row changed concurrently; refresh and retry.")
            after=dict(after)
            audit_write(cur,actor=actor,action="PLAYER_STATE_EDIT",object_type=str(cfg["table"]),object_id=str(rid),before=before,after=after,reason=reason)
            conn.commit()
    return {"ok":True,"target":target,"row":_json_safe(after)}


@app.get("/api/economy/assets")
def economy_assets() -> list[dict[str, Any]]:
    ensure_live_available()
    return live_query("SELECT code,asset_type,integrity_tier::text AS integrity_tier,precision_scale,transferable,metadata FROM economy.asset_defs ORDER BY asset_type,code")


@app.post("/api/players/{player_id}/balance-adjust")
def player_balance_adjust(player_id: str, payload: dict[str, Any], x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    """Audited ledger adjustment. Never raw-overwrites available_balance without an entry/operation."""
    ensure_live_available(); require_write_token(x_admin_token); actor=x_admin_actor or ADMIN_ACTOR_DEFAULT
    asset=str(payload.get("asset_code") or "").strip().upper(); reason=str(payload.get("reason_code") or "ADMIN_BALANCE_ADJUST").strip()[:96]
    if not asset: raise HTTPException(status_code=400,detail="asset_code là bắt buộc.")
    mode=str(payload.get("mode") or "DELTA").upper()
    if mode not in {"DELTA","SET"}: raise HTTPException(status_code=400,detail="mode phải là DELTA hoặc SET.")
    try: amount=Decimal(str(payload.get("amount")))
    except (InvalidOperation,TypeError): raise HTTPException(status_code=400,detail="amount không hợp lệ.")
    if amount.is_nan() or amount.is_infinite(): raise HTTPException(status_code=400,detail="amount không hợp lệ.")
    assert psycopg is not None and dict_row is not None and Jsonb is not None
    try:
        with psycopg.connect(DATABASE_URL,row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM identity.players WHERE id=%s::uuid",(player_id,))
                if cur.fetchone() is None: raise HTTPException(status_code=404,detail="Player not found.")
                cur.execute("SELECT code FROM economy.asset_defs WHERE code=%s",(asset,))
                if cur.fetchone() is None: raise HTTPException(status_code=400,detail=f"Asset {asset} không có trong economy.asset_defs.")
                cur.execute("SELECT * FROM economy.ledger_accounts WHERE owner_scope='PLAYER' AND owner_id=%s::uuid AND asset_code=%s FOR UPDATE",(player_id,asset)); acc=cur.fetchone()
                if acc is None:
                    cur.execute("INSERT INTO economy.ledger_accounts(owner_scope,owner_id,asset_code,available_balance,reserved_balance,sequence_no,version) VALUES('PLAYER',%s::uuid,%s,0,0,0,0) RETURNING *",(player_id,asset)); acc=cur.fetchone()
                before=dict(acc); old=Decimal(str(before["available_balance"])); new=amount if mode=="SET" else old+amount
                if new<0: raise HTTPException(status_code=400,detail=f"Số dư sau điều chỉnh âm ({new}).")
                delta=new-old
                if delta==0: return {"ok":True,"asset_code":asset,"before":str(old),"after":str(new),"delta":"0","no_change":True}
                operation_id=str(uuid.uuid4()); idem=f"ADMIN:{actor}:{player_id}:{asset}:{uuid.uuid4()}"
                cur.execute("""INSERT INTO economy.ledger_operations(id,operation_type,actor_type,actor_id,source_type,source_id,reason_code,idempotency_key,status,metadata)
                             VALUES(%s::uuid,'ADMIN_BALANCE_ADJUST','ADMIN',NULL,'ADMIN_CONSOLE',%s,%s,%s,'COMMITTED',%s)""",
                            (operation_id,player_id,reason,idem,Jsonb({"admin_actor":actor,"mode":mode,"requested_amount":str(amount)})))
                seq=int(before.get("sequence_no") or 0)+1
                cur.execute("""UPDATE economy.ledger_accounts SET available_balance=%s,sequence_no=%s,version=version+1 WHERE id=%s RETURNING *""",(new,seq,before["id"])); after=dict(cur.fetchone())
                cur.execute("""INSERT INTO economy.ledger_entries(operation_id,ledger_account_id,account_sequence,delta_available,delta_reserved,balance_before,balance_after,entry_role)
                             VALUES(%s::uuid,%s,%s,%s,0,%s,%s,'PRIMARY')""",(operation_id,before["id"],seq,delta,old,new))
                audit_write(cur,actor=actor,action="PLAYER_BALANCE_ADJUST",object_type="economy.ledger_accounts",object_id=str(before["id"]),before=before,after=after,reason=reason)
                conn.commit()
        return {"ok":True,"asset_code":asset,"before":str(old),"after":str(new),"delta":str(delta),"operation_id":operation_id}
    except HTTPException:
        raise
    except Exception as exc:
        if type(exc).__name__ == "InsufficientPrivilege":
            raise HTTPException(
                status_code=503,
                detail="DB user của Admin thiếu quyền Player Economy. Trong DBeaver chạy sql/60_v61_player_economy_permissions_hotfix.sql trên lost_kingsland_v4_reconciled, rồi restart Admin."
            ) from exc
        raise



def _test_media_rows() -> list[dict[str, str]]:
    if not TEST_MEDIA_CSV.exists():
        return []
    with TEST_MEDIA_CSV.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _test_media_permissions() -> dict[str, Any]:
    if not live_mode():
        return {"checked": False, "ready": False, "reason": "snapshot"}
    try:
        rows = live_query("""
            SELECT current_user AS db_user,
                   has_table_privilege(current_user,'platform.media_assets','SELECT,INSERT,UPDATE,DELETE') AS media_assets_rw,
                   has_table_privilege(current_user,'platform.entity_media_links','SELECT,INSERT,UPDATE,DELETE') AS media_links_rw,
                   has_table_privilege(current_user,'inventory.item_defs','UPDATE') AS item_update,
                   has_table_privilege(current_user,'hero.character_defs','UPDATE') AS character_update
        """)
        row = rows[0] if rows else {}
        row["checked"] = True
        row["ready"] = all(bool(row.get(k)) for k in ("media_assets_rw","media_links_rw","item_update","character_update"))
        return row
    except Exception as exc:
        return {"checked": False, "ready": False, "error": type(exc).__name__}


def _test_media_db_stats() -> dict[str, Any]:
    if not live_mode() or not media_db_table_exists():
        return {"test_assets": 0, "primary_links": 0, "items_with_images": 0, "characters_with_images": 0,
                "item_primary_links":0,"item_unique_assets":0,"set_primary_links":0,"set_unique_assets":0,"diversity_ready":False}
    try:
        row = live_query("""
            SELECT
              (SELECT count(*) FROM platform.media_assets WHERE active=true AND category='TEST_PLACEHOLDER') AS test_assets,
              (SELECT count(*) FROM platform.entity_media_links l JOIN platform.media_assets a ON a.asset_key=l.asset_key WHERE l.is_primary=true AND a.category='TEST_PLACEHOLDER') AS primary_links,
              (SELECT count(*) FROM inventory.item_defs WHERE image_asset_key IS NOT NULL AND image_asset_key<>'') AS items_with_images,
              (SELECT count(*) FROM hero.character_defs WHERE image_asset_key IS NOT NULL AND image_asset_key<>'') AS characters_with_images,
              (SELECT count(*) FROM platform.entity_media_links WHERE entity_type='ITEM_DEF' AND is_primary=true) AS item_primary_links,
              (SELECT count(DISTINCT asset_key) FROM platform.entity_media_links WHERE entity_type='ITEM_DEF' AND is_primary=true) AS item_unique_assets,
              (SELECT count(*) FROM platform.entity_media_links WHERE entity_type='EQUIPMENT_SET' AND is_primary=true) AS set_primary_links,
              (SELECT count(DISTINCT asset_key) FROM platform.entity_media_links WHERE entity_type='EQUIPMENT_SET' AND is_primary=true) AS set_unique_assets
        """)[0]
        row["diversity_ready"] = int(row.get("item_unique_assets") or 0) >= 300 and int(row.get("set_unique_assets") or 0) >= 10
        return row
    except Exception:
        return {"test_assets": 0, "primary_links": 0, "items_with_images": 0, "characters_with_images": 0,
                "item_primary_links":0,"item_unique_assets":0,"set_primary_links":0,"set_unique_assets":0,"diversity_ready":False}


def _set_test_media_job(**patch: Any) -> None:
    with _TEST_MEDIA_LOCK:
        _TEST_MEDIA_JOB.update(patch)


def _append_test_media_log(line: str) -> None:
    with _TEST_MEDIA_LOCK:
        logs = list(_TEST_MEDIA_JOB.get("log") or [])
        logs.append(line.rstrip())
        _TEST_MEDIA_JOB["log"] = logs[-500:]


def _run_test_media_process(cmd: list[str], kind: str) -> None:
    _set_test_media_job(status="running", kind=kind, started_at=datetime.now(timezone.utc).isoformat(), finished_at=None, returncode=None, log=[], command=cmd)
    try:
        proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
        if proc.stdout:
            for line in proc.stdout:
                _append_test_media_log(line)
        rc = proc.wait()
        _set_test_media_job(status="done" if rc == 0 else "failed", returncode=rc, finished_at=datetime.now(timezone.utc).isoformat())
    except Exception as exc:
        _append_test_media_log(f"ERROR: {type(exc).__name__}: {exc}")
        _set_test_media_job(status="failed", returncode=-1, finished_at=datetime.now(timezone.utc).isoformat())


@app.get("/api/test-media/plan")
def test_media_plan() -> dict[str, Any]:
    rows = _test_media_rows()
    counts = Counter(r.get("entity_type") or "UNKNOWN" for r in rows)
    return {
        "mapping_file": TEST_MEDIA_CSV.name,
        "total": len(rows),
        "unique_urls": len({r.get("source_url") for r in rows if r.get("source_url")}),
        "by_type": dict(sorted(counts.items())),
        "db": _json_safe(_test_media_db_stats()),
        "permissions": _json_safe(_test_media_permissions()),
        "sources": [
            {"name":"Game-icons.net", "usage":"Item placeholder icons", "license":"CC BY 3.0"},
            {"name":"DiceBear", "usage":"Character/Boss/Content placeholders", "license":"CC0 styles used in mapping"},
        ],
    }


@app.get("/api/test-media/job")
def test_media_job() -> dict[str, Any]:
    with _TEST_MEDIA_LOCK:
        return _json_safe(dict(_TEST_MEDIA_JOB))


@app.post("/api/test-media/start")
def test_media_start(payload: dict[str, Any], x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    require_write_token(x_admin_token)
    ensure_live_available()
    perms = _test_media_permissions()
    if not perms.get("ready"):
        raise HTTPException(status_code=503, detail="DB user thiếu quyền Shared Media. Chạy sql/70_v62_test_media_permissions_hotfix.sql trong DBeaver rồi restart Admin.")
    with _TEST_MEDIA_LOCK:
        if _TEST_MEDIA_JOB.get("status") == "running":
            raise HTTPException(status_code=409, detail="Một job ảnh test đang chạy.")
    mode = str(payload.get("mode") or "missing").lower()
    if mode not in {"missing","replace"}:
        raise HTTPException(status_code=400, detail="mode must be missing or replace")
    strategy = str(payload.get("strategy") or "mapped").lower()
    if strategy not in {"mapped","diverse"}:
        raise HTTPException(status_code=400, detail="strategy must be mapped or diverse")
    try:
        limit = max(0, min(5000, int(payload.get("limit") or 0)))
    except Exception:
        limit = 0
    entity_type = str(payload.get("entity_type") or "").strip().upper()
    seed_script = DIVERSE_MEDIA_SEED_SCRIPT if strategy == "diverse" else TEST_MEDIA_SEED_SCRIPT
    cmd = [sys.executable, str(seed_script), "--apply", "--actor", ADMIN_OWNER_NAME or "Viet-TestMedia"]
    if mode == "replace":
        cmd.append("--force")
    if limit:
        cmd += ["--limit", str(limit)]
    if entity_type:
        cmd += ["--type", entity_type]
    thread = threading.Thread(target=_run_test_media_process, args=(cmd, f"seed-{strategy}-{mode}"), daemon=True)
    thread.start()
    return {"ok": True, "started": True, "mode": mode, "strategy": strategy, "limit": limit, "entity_type": entity_type or None}


@app.post("/api/test-media/rebuild-diverse")
def test_media_rebuild_diverse(x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    """Safely replace only TEST_PLACEHOLDER media with V6.3+ diverse media.

    Real/admin-uploaded artwork is preserved: first remove links/assets whose category is
    TEST_PLACEHOLDER, clear only matching direct keys, then launch diverse seeding in
    missing mode.
    """
    require_write_token(x_admin_token)
    ensure_live_available()
    with _TEST_MEDIA_LOCK:
        if _TEST_MEDIA_JOB.get("status") == "running":
            raise HTTPException(status_code=409, detail="Một job ảnh test đang chạy.")
    assert psycopg is not None and dict_row is not None
    actor = ADMIN_OWNER_NAME if LOCAL_OWNER_EFFECTIVE else (x_admin_actor or ADMIN_ACTOR_DEFAULT)
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT asset_key FROM platform.media_assets WHERE category='TEST_PLACEHOLDER'")
            keys=[r["asset_key"] for r in cur.fetchall()]
            item_rows=char_rows=links=assets=0
            if keys:
                cur.execute("UPDATE inventory.item_defs SET image_asset_key=NULL WHERE image_asset_key = ANY(%s)",(keys,)); item_rows=cur.rowcount
                cur.execute("UPDATE hero.character_defs SET image_asset_key=NULL WHERE image_asset_key = ANY(%s)",(keys,)); char_rows=cur.rowcount
                cur.execute("DELETE FROM platform.entity_media_links WHERE asset_key = ANY(%s)",(keys,)); links=cur.rowcount
                cur.execute("DELETE FROM platform.media_assets WHERE asset_key = ANY(%s)",(keys,)); assets=cur.rowcount
            audit_write(cur, actor=actor, action="TEST_MEDIA_REBUILD_DIVERSE", object_type="TEST_PLACEHOLDER", object_id=None, before={"assets":len(keys)}, after={"queued":"diverse"}, reason="ADMIN_TEST_MEDIA")
        conn.commit()
    cmd=[sys.executable,str(DIVERSE_MEDIA_SEED_SCRIPT),"--apply","--actor",actor]
    thread=threading.Thread(target=_run_test_media_process,args=(cmd,"rebuild-diverse-safe"),daemon=True)
    thread.start()
    return {"ok":True,"started":True,"deleted_assets":assets,"deleted_links":links,"item_fields_cleared":item_rows,"character_fields_cleared":char_rows}


@app.post("/api/test-media/check")
def test_media_check(x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    # Read-only check, but keep it on the local-owner/token operator surface so it cannot be abused remotely.
    if not LOCAL_OWNER_EFFECTIVE:
        require_write_token(x_admin_token)
    ensure_live_available()
    try:
        proc = subprocess.run([sys.executable, str(TEST_MEDIA_CHECK_SCRIPT), "--admin-base-url", f"http://{ADMIN_HOST_CONFIG}:{os.getenv('ADMIN_PORT','8787')}"], cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45)
        return {"ok": proc.returncode == 0, "returncode": proc.returncode, "output": (proc.stdout + ("\n" + proc.stderr if proc.stderr else "")).strip()}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Media/Bot check timed out after 45 seconds.")


@app.delete("/api/test-media/placeholders")
def test_media_cleanup(x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    require_write_token(x_admin_token)
    ensure_live_available()
    assert psycopg is not None and dict_row is not None
    actor = ADMIN_OWNER_NAME if LOCAL_OWNER_EFFECTIVE else (x_admin_actor or ADMIN_ACTOR_DEFAULT)
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT asset_key FROM platform.media_assets WHERE category='TEST_PLACEHOLDER'")
            keys = [r["asset_key"] for r in cur.fetchall()]
            if not keys:
                return {"ok": True, "deleted_assets": 0}
            cur.execute("UPDATE inventory.item_defs SET image_asset_key=NULL WHERE image_asset_key = ANY(%s)", (keys,))
            item_rows = cur.rowcount
            cur.execute("UPDATE hero.character_defs SET image_asset_key=NULL WHERE image_asset_key = ANY(%s)", (keys,))
            char_rows = cur.rowcount
            cur.execute("DELETE FROM platform.entity_media_links WHERE asset_key = ANY(%s)", (keys,))
            links = cur.rowcount
            cur.execute("DELETE FROM platform.media_assets WHERE asset_key = ANY(%s)", (keys,))
            assets = cur.rowcount
            audit_write(cur, actor=actor, action="TEST_MEDIA_CLEANUP", object_type="TEST_PLACEHOLDER", object_id=None, before={"assets":len(keys)}, after={"assets":0}, reason="ADMIN_TEST_MEDIA")
        conn.commit()
    return {"ok": True, "deleted_assets": assets, "deleted_links": links, "item_fields_cleared": item_rows, "character_fields_cleared": char_rows}


@app.get("/api/characters")
def character_studio(q: str = Query(""), rarity: str = Query(""), limit: int = Query(500, ge=1, le=1000)) -> dict[str, Any]:
    ensure_live_available()
    filters: list[str] = []
    args: list[Any] = [ADMIN_GAMEPLAY_CONFIG, ADMIN_GAMEPLAY_CONFIG]
    if q.strip():
        filters.append("(c.code ILIKE %s OR c.display_name_vi ILIKE %s OR c.combat_role ILIKE %s OR c.affinity_code ILIKE %s)")
        like=f"%{q.strip()}%"; args += [like,like,like,like]
    if rarity.strip(): filters.append("c.rarity::text=%s"); args.append(rarity.strip().upper())
    filter_sql = (" AND " + " AND ".join(filters)) if filters else ""
    args.append(limit)
    rows=live_query(f"""
        WITH chosen AS (
          SELECT cv.id, cv.version_code, (cv.version_code=%s) AS is_requested
          FROM platform.config_versions cv
          WHERE EXISTS (SELECT 1 FROM hero.character_defs cx WHERE cx.config_version_id=cv.id)
          ORDER BY (cv.version_code=%s) DESC, cv.id DESC
          LIMIT 1
        )
        SELECT c.code AS entity_id,c.code,c.display_name_vi,c.rarity::text AS rarity,c.combat_role,c.affinity_code,c.weapon_theme,
               c.rarity_power_mult,c.stat_profile,c.signature_skill_vi,c.lore_summary_vi,c.image_asset_key,c.active,
               chosen.version_code AS config_version,chosen.is_requested
        FROM hero.character_defs c JOIN chosen ON chosen.id=c.config_version_id
        WHERE 1=1 {filter_sql}
        ORDER BY c.rarity,c.display_name_vi LIMIT %s
    """,tuple(args))
    # Prefer generic shared-media PRIMARY if present, fallback direct image_asset_key.
    for r in rows:
        if _entity_media_link_ready():
            links=live_query("SELECT asset_key FROM platform.entity_media_links WHERE entity_type='CHARACTER_DEF' AND entity_id=%s AND is_primary=true ORDER BY created_at DESC LIMIT 1",(r["code"],))
            if links: r["image_asset_key"]=links[0]["asset_key"]
        r["image_url"]=media_url_for_key(r.get("image_asset_key"))
    resolved = rows[0].get("config_version") if rows else None
    return {
        "rows":_json_safe(rows),
        "total":len(rows),
        "requested_gameplay_config":ADMIN_GAMEPLAY_CONFIG,
        "content_config_version":resolved,
        "config_fallback":bool(resolved and resolved != ADMIN_GAMEPLAY_CONFIG),
    }



# ---------------------------------------------------------------------------
# V7.1 — Core resource icons + 90 equipment-specific crafting ores (PET included)
# Static definitions only: no equipment stats/affixes. The Admin surface is
# intentionally small and image-first. Runtime balances remain ledger-owned.
# ---------------------------------------------------------------------------
CORE_STATIC_ASSET_CODES = [
    "GOLD","GEMS","JADE","WOOD","ORE","FOOD","ESSENCE","CULTIVATION_QI","SKILL_POINT","CLAN_MARKS","SEASON_TOKEN",
    "BUILD_SPEEDUP_MINUTE","BUILD_SPEEDUP_5_MINUTE","BUILD_SPEEDUP_10_MINUTE","BUILD_SPEEDUP_30_MINUTE",
    "BUILD_SPEEDUP_1_HOUR","BUILD_SPEEDUP_3_HOUR","BUILD_SPEEDUP_8_HOUR"
]


def _asset_image_key(row: dict[str, Any]) -> str | None:
    meta = row.get("metadata") or {}
    if isinstance(meta, str):
        try: meta = json.loads(meta)
        except Exception: meta = {}
    direct = (meta or {}).get("image_asset_key")
    if direct: return str(direct)
    links = live_query(
        "SELECT asset_key FROM platform.entity_media_links WHERE entity_type='ECONOMY_ASSET' AND entity_id=%s AND is_primary=true ORDER BY created_at DESC LIMIT 1",
        (row.get("code"),),
    )
    return links[0]["asset_key"] if links else None


def _decorate_asset(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    meta = out.get("metadata") or {}
    if isinstance(meta, str):
        try: meta = json.loads(meta)
        except Exception: meta = {}
    out["metadata"] = meta
    out["display_name_vi"] = meta.get("display_name_vi") or out.get("code")
    out["target_slot"] = meta.get("target_slot")
    out["target_rarity"] = meta.get("target_rarity")
    out["material_family"] = meta.get("material_family")
    out["purpose_vi"] = meta.get("purpose_vi")
    out["active"] = bool(meta.get("active", True))
    out["demo_craft_cost"] = meta.get("demo_craft_cost", 20)
    key = _asset_image_key(out)
    out["image_asset_key"] = key
    out["image_url"] = media_url_for_key(key)
    return out


@app.get("/api/resource-assets")
def resource_assets(include_ores: bool = Query(True)) -> dict[str, Any]:
    ensure_live_available()
    if include_ores:
        rows = live_query(
            """SELECT code,asset_type,integrity_tier::text AS integrity_tier,precision_scale,transferable,metadata
               FROM economy.asset_defs
               WHERE code = ANY(%s) OR metadata->>'material_family'='EQUIPMENT_ORE'
               ORDER BY CASE WHEN code = ANY(%s) THEN 0 ELSE 1 END,
                        COALESCE((metadata->>'rarity_ordinal')::int,0),COALESCE((metadata->>'slot_ordinal')::int,0),code""",
            (CORE_STATIC_ASSET_CODES, CORE_STATIC_ASSET_CODES),
        )
    else:
        rows = live_query(
            """SELECT code,asset_type,integrity_tier::text AS integrity_tier,precision_scale,transferable,metadata
               FROM economy.asset_defs WHERE code = ANY(%s) ORDER BY code""",
            (CORE_STATIC_ASSET_CODES,),
        )
    out=[_decorate_asset(r) for r in rows]
    return {"rows":_json_safe(out),"total":len(out),"core_count":sum(1 for r in out if r["code"] in CORE_STATIC_ASSET_CODES),"ore_count":sum(1 for r in out if r.get("material_family")=="EQUIPMENT_ORE")}


@app.get("/api/system-shop")
def system_shop_catalog() -> dict[str, Any]:
    ensure_live_available()
    offers = live_query("SELECT * FROM commerce.system_shop_offers ORDER BY display_name,id")
    choices = live_query("""SELECT 'ASSET' AS kind,code,NULL::bigint AS config,
         COALESCE(metadata->>'display_name_vi',code) AS name,NULL::text AS rarity
         FROM economy.asset_defs WHERE code<>'JADE'
         UNION ALL SELECT item_type::text,code,config_version_id,display_name_vi,rarity::text
         FROM inventory.item_defs WHERE item_type::text IN('EQUIPMENT','CONSUMABLE')
         AND (item_type::text='CONSUMABLE' OR catalog_status='ACTIVE_CANONICAL')
         ORDER BY kind,name,config""")
    currencies = live_query("""SELECT code,COALESCE(metadata->>'display_name_vi',code) AS name
        FROM economy.asset_defs WHERE code IN('GOLD','GEMS','JADE') ORDER BY code""")
    return {"offers": _json_safe(offers), "choices": _json_safe(choices), "currencies": _json_safe(currencies)}


def _shop_integer(payload: dict, field: str, minimum: int, maximum: int) -> int:
    value = payload.get(field)
    if isinstance(value, bool):
        raise HTTPException(status_code=400, detail="Số lượng và giá phải là số nguyên hợp lệ.")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Số lượng và giá phải là số nguyên hợp lệ.")
    if not number.is_finite() or number != number.to_integral_value() or number < minimum or number > maximum:
        raise HTTPException(status_code=400, detail="Số lượng hoặc giá nằm ngoài giới hạn cho phép.")
    return int(number)


@app.post("/api/system-shop")
def save_system_shop(payload: dict[str, Any], x_admin_token: str | None = Header(default=None),
                     x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available(); require_write_token(x_admin_token)
    name = str(payload.get("display_name") or "").strip()
    kind = str(payload.get("reward_kind") or "")
    code = str(payload.get("reward_code") or "")
    if not name or len(name) > 160 or kind not in ("ASSET", "CONSUMABLE", "EQUIPMENT"):
        raise HTTPException(status_code=400, detail="Chọn hàng bán và nhập tên hiển thị.")
    quantity = _shop_integer(payload, "quantity", 1, 1000000)
    level = _shop_integer(payload, "item_level", 1, 1000000)
    price = _shop_integer(payload, "price", 1, 1000000000000)
    stock = None if payload.get("stock") is None else _shop_integer(payload, "stock", 0, 1000000000)
    currency = payload.get("price_asset")
    if currency not in ("GOLD", "GEMS", "JADE") or (kind == "EQUIPMENT" and quantity != 1):
        raise HTTPException(status_code=400, detail="Chọn tiền thanh toán hợp lệ. Mỗi gói trang bị chứa một món.")
    if not isinstance(payload.get("enabled"), bool):
        raise HTTPException(status_code=400, detail="Chọn trạng thái bán hàng.")
    config = None if kind == "ASSET" else _shop_integer(payload, "item_config_version_id", 1, 2147483647)
    actor = ADMIN_OWNER_NAME if LOCAL_OWNER_EFFECTIVE else (x_admin_actor or ADMIN_ACTOR_DEFAULT)
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            if kind == "ASSET":
                cur.execute("SELECT code FROM economy.asset_defs WHERE code=%s AND code<>'JADE'", (code,))
            else:
                cur.execute("""SELECT code FROM inventory.item_defs WHERE code=%s AND config_version_id=%s
                    AND item_type::text=%s AND (item_type::text='CONSUMABLE' OR catalog_status='ACTIVE_CANONICAL')""", (code, config, kind))
            if not cur.fetchone():
                raise HTTPException(status_code=400, detail="Vật phẩm không hợp lệ. Không bán Ngọc dưới dạng phần thưởng.")
            values = (name, kind, code, config, quantity, level, currency, price, stock, payload["enabled"])
            before = None
            if payload.get("id"):
                try: offer_id = str(uuid.UUID(str(payload["id"])))
                except (ValueError, AttributeError): raise HTTPException(status_code=400, detail="Hàng bán không hợp lệ.")
                cur.execute("SELECT * FROM commerce.system_shop_offers WHERE id=%s FOR UPDATE", (offer_id,))
                before = cur.fetchone()
                if not before: raise HTTPException(status_code=404, detail="Không tìm thấy hàng bán.")
                if before["version"] != _shop_integer(payload, "version", 0, 9223372036854775807):
                    raise HTTPException(status_code=409, detail="Hàng đã thay đổi hoặc vừa được mua. Tải lại trước khi lưu.")
                cur.execute("""UPDATE commerce.system_shop_offers SET display_name=%s,reward_kind=%s,reward_code=%s,
                    item_config_version_id=%s,quantity=%s,item_level=%s,price_asset=%s,price=%s,stock=%s,enabled=%s,
                    version=version+1,updated_at=now() WHERE id=%s RETURNING *""", values+(offer_id,))
            else:
                cur.execute("""INSERT INTO commerce.system_shop_offers(display_name,reward_kind,reward_code,
                    item_config_version_id,quantity,item_level,price_asset,price,stock,enabled)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""", values)
            saved = cur.fetchone()
            audit_write(cur, actor=actor, action="SAVE_SYSTEM_SHOP", object_type="SYSTEM_SHOP_OFFER",
                        object_id=str(saved["id"]), before=before, after=saved, reason="ADMIN_SHOP_UPDATE")
    return {"ok": True, "offer": _json_safe(saved)}


@app.get("/api/topup")
def topup_admin_catalog() -> dict[str, Any]:
    ensure_live_available()
    ui = live_query("SELECT * FROM payment.topup_ui_config WHERE id=1")[0]
    packages = live_query("SELECT * FROM payment.topup_packages ORDER BY sort_order,amount_vnd")
    orders = live_query("SELECT * FROM admin.v_topup_orders ORDER BY created_at DESC LIMIT 200")
    return {"ui": _json_safe(ui), "packages": _json_safe(packages), "orders": _json_safe(orders)}

@app.post("/api/topup/ui")
def save_topup_ui(payload: dict[str, Any], x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available(); require_write_token(x_admin_token)
    title=str(payload.get("title") or "").strip(); instructions=str(payload.get("instructions") or "").strip(); footer=str(payload.get("footer") or "").strip()
    if not title or not instructions or len(title)>100 or len(instructions)>1000 or len(footer)>300: raise HTTPException(status_code=400,detail="Nội dung giao diện nạp không hợp lệ.")
    version=_shop_integer(payload,"version",0,9223372036854775807); actor=ADMIN_OWNER_NAME if LOCAL_OWNER_EFFECTIVE else (x_admin_actor or ADMIN_ACTOR_DEFAULT)
    with psycopg.connect(DATABASE_URL,row_factory=dict_row) as conn:
      with conn.cursor() as cur:
        cur.execute("SELECT * FROM payment.topup_ui_config WHERE id=1 FOR UPDATE"); before=cur.fetchone()
        if before["version"]!=version: raise HTTPException(status_code=409,detail="Cấu hình vừa thay đổi. Hãy tải lại.")
        cur.execute("UPDATE payment.topup_ui_config SET title=%s,instructions=%s,footer=%s,version=version+1,updated_at=now() WHERE id=1 RETURNING *",(title,instructions,footer)); saved=cur.fetchone()
        audit_write(cur,actor=actor,action="SAVE_TOPUP_UI",object_type="TOPUP_UI",object_id="1",before=before,after=saved,reason="ADMIN_TOPUP_UI_UPDATE")
    return {"ok":True}

@app.post("/api/topup/packages")
def save_topup_packages(payload: dict[str, Any], x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available(); require_write_token(x_admin_token); rows=payload.get("packages")
    if not isinstance(rows,list) or not rows or len(rows)>20: raise HTTPException(status_code=400,detail="Danh sách gói nạp không hợp lệ.")
    actor=ADMIN_OWNER_NAME if LOCAL_OWNER_EFFECTIVE else (x_admin_actor or ADMIN_ACTOR_DEFAULT)
    with psycopg.connect(DATABASE_URL,row_factory=dict_row) as conn:
      with conn.cursor() as cur:
       for row in rows:
        code=str(row.get("code") or ""); amount=_shop_integer(row,"amount_vnd",2000,100000000); reward=_shop_integer(row,"reward_amount",1,100000000); bonus=_shop_integer(row,"bonus_amount",0,100000000); version=_shop_integer(row,"version",0,9223372036854775807)
        if not isinstance(row.get("active"),bool): raise HTTPException(status_code=400,detail="Trạng thái gói không hợp lệ.")
        cur.execute("SELECT * FROM payment.topup_packages WHERE code=%s FOR UPDATE",(code,)); before=cur.fetchone()
        if not before or before["version"]!=version: raise HTTPException(status_code=409,detail=f"Gói {code} vừa thay đổi.")
        cur.execute("UPDATE payment.topup_packages SET amount_vnd=%s,reward_amount=%s,bonus_amount=%s,active=%s,version=version+1,updated_at=now() WHERE code=%s RETURNING *",(amount,reward,bonus,row["active"],code)); saved=cur.fetchone()
        audit_write(cur,actor=actor,action="SAVE_TOPUP_PACKAGE",object_type="TOPUP_PACKAGE",object_id=code,before=before,after=saved,reason="ADMIN_TOPUP_PACKAGE_UPDATE")
    return {"ok":True}
WHEEL_CATEGORY_LABELS = {
    "CHARACTER": "Nhân vật", "EQUIPMENT": "Trang bị",
    "EQUIPMENT_FRAGMENT": "Mảnh trang bị", "CRAFTING_MATERIAL": "Nguyên liệu chế tạo",
    "CONSUMABLE": "Vật phẩm tiêu hao", "CONSTRUCTION_RESOURCE": "Tài nguyên xây dựng",
    "GOLD": "Vàng", "SKILL_POINT": "Điểm kỹ năng",
}


@app.get("/api/gameplay/wheel-rates")
def gameplay_wheel_rates() -> dict[str, Any]:
    ensure_live_available()
    rows = live_query("""SELECT r.category_weights FROM gacha.wheel_rules r
        JOIN platform.config_versions c ON c.id=r.config_version_id
        WHERE c.version_code='LK-V4.0-P15-RC-001'""")
    if not rows:
        raise HTTPException(status_code=404, detail="Chưa có cấu hình vòng quay.")
    weights = rows[0]["category_weights"]
    total = sum(Decimal(str(value)) for value in weights.values())
    if total <= 0:
        raise HTTPException(status_code=409, detail="Tổng tỷ lệ vòng quay không hợp lệ.")
    return {"items": [{"category": code, "name": label,
                        "rate_percent": str(Decimal(str(weights.get(code, 0))) * 100 / total)}
                       for code, label in WHEEL_CATEGORY_LABELS.items()]}

@app.get("/api/gameplay/trait-rates")
def gameplay_trait_rates() -> dict[str, Any]:
    ensure_live_available()
    rows=live_query("""SELECT kind,code,display_name,rarity,weight,vitality_pct,martial_pct,mystic_pct,armor_pct,ward_pct,speed_pct,crit_pct,penetration_pct,cultivation_pct,image_url FROM gacha.trait_wheel_defs ORDER BY kind,code""")
    totals={}
    for row in rows: totals[row["kind"]]=totals.get(row["kind"],0)+row["weight"]
    for row in rows: row["rate_percent"]=str((Decimal(row["weight"])*Decimal(100)/Decimal(totals[row["kind"]])).quantize(Decimal("0.0001")))
    return {"items":rows}

@app.put("/api/gameplay/trait-rates")
def update_gameplay_trait_rates(payload: dict[str, Any],x_admin_token: str|None=Header(default=None),x_admin_actor: str|None=Header(default=None)) -> dict[str, Any]:
    ensure_live_available();require_write_token(x_admin_token);items=payload.get("items")
    if not isinstance(items,list) or not items: raise HTTPException(status_code=400,detail="Danh sách rate không hợp lệ.")
    grouped={}
    for item in items:
        try: rate=Decimal(str(item.get("rate_percent")))
        except Exception: raise HTTPException(status_code=400,detail="Rate phải là số.")
        if rate<0 or rate>100: raise HTTPException(status_code=400,detail="Rate phải từ 0 đến 100%.")
        grouped.setdefault(str(item.get("kind")),[]).append((str(item.get("code")),rate))
    for kind,values in grouped.items():
        if abs(sum((v for _,v in values),Decimal(0))-Decimal(100))>Decimal("0.01"): raise HTTPException(status_code=400,detail=f"Tổng rate {kind} phải đúng 100%.")
    actor=ADMIN_OWNER_NAME if LOCAL_OWNER_EFFECTIVE else (x_admin_actor or ADMIN_ACTOR_DEFAULT)
    with psycopg.connect(DATABASE_URL,row_factory=dict_row) as conn:
      with conn.cursor() as cur:
       for kind,values in grouped.items():
        for code,rate in values:
         cur.execute("UPDATE gacha.trait_wheel_defs SET weight=%s WHERE kind=%s AND code=%s",(max(0,int(rate*10000)),kind,code))
       audit_write(cur,actor=actor,action="UPDATE_TRAIT_GACHA_RATES",object_type="TRAIT_GACHA",object_id=",".join(grouped),before={},after=payload,reason="ADMIN_BALANCE_UPDATE")
    return {"ok":True}

@app.get("/api/gameplay/cultivation-ui")
def gameplay_cultivation_ui() -> dict[str, Any]:
    ensure_live_available();rows=live_query("SELECT title,description,color_rarity,thumbnail_url,footer FROM admin.cultivation_ui_settings WHERE id=1")
    return rows[0] if rows else {}

@app.put("/api/gameplay/cultivation-ui")
def update_gameplay_cultivation_ui(payload: dict[str, Any],x_admin_token: str|None=Header(default=None),x_admin_actor: str|None=Header(default=None)) -> dict[str, Any]:
    ensure_live_available();require_write_token(x_admin_token)
    values={k:str(payload.get(k) or "").strip() for k in ("title","description","color_rarity","thumbnail_url","footer")}
    if not values["title"] or not values["description"]: raise HTTPException(status_code=400,detail="Tiêu đề và mô tả không được trống.")
    actor=ADMIN_OWNER_NAME if LOCAL_OWNER_EFFECTIVE else (x_admin_actor or ADMIN_ACTOR_DEFAULT)
    with psycopg.connect(DATABASE_URL,row_factory=dict_row) as conn:
      with conn.cursor() as cur:
       cur.execute("SELECT * FROM admin.cultivation_ui_settings WHERE id=1 FOR UPDATE");before=cur.fetchone()
       cur.execute("UPDATE admin.cultivation_ui_settings SET title=%s,description=%s,color_rarity=%s,thumbnail_url=NULLIF(%s,''),footer=%s,updated_at=now() WHERE id=1 RETURNING *",(values["title"],values["description"],values["color_rarity"],values["thumbnail_url"],values["footer"]));after=cur.fetchone()
       audit_write(cur,actor=actor,action="UPDATE_CULTIVATION_UI",object_type="CULTIVATION_UI",object_id="1",before=before,after=after,reason="ADMIN_PRESENTATION_UPDATE")
    return {"ok":True}


@app.put("/api/gameplay/wheel-rates")
def update_gameplay_wheel_rates(payload: dict[str, Any], x_admin_token: str | None = Header(default=None),
                               x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available()
    require_write_token(x_admin_token)
    submitted = payload.get("items")
    if not isinstance(submitted, list) or len(submitted) != len(WHEEL_CATEGORY_LABELS):
        raise HTTPException(status_code=400, detail="Nhập đủ các nhóm phần thưởng.")
    weights = {}
    for item in submitted:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="Nhóm phần thưởng không hợp lệ.")
        code = item.get("category")
        try:
            percent = Decimal(str(item.get("rate_percent")))
        except (InvalidOperation, TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Tỷ lệ phải là số nguyên từ 0 đến 100%.")
        if (code not in WHEEL_CATEGORY_LABELS or code in weights or not percent.is_finite()
                or percent < 0 or percent > 100 or percent != percent.to_integral_value()):
            raise HTTPException(status_code=400, detail="Mỗi nhóm phải duy nhất; tỷ lệ là số nguyên từ 0 đến 100%.")
        weights[code] = int(percent)
    if sum(weights.values()) != 100:
        raise HTTPException(status_code=400, detail="Tổng tỷ lệ vòng quay phải đúng 100%.")
    actor = ADMIN_OWNER_NAME if LOCAL_OWNER_EFFECTIVE else (x_admin_actor or ADMIN_ACTOR_DEFAULT)
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT r.config_version_id,r.category_weights FROM gacha.wheel_rules r
                JOIN platform.config_versions c ON c.id=r.config_version_id
                WHERE c.version_code='LK-V4.0-P15-RC-001' FOR UPDATE OF r""")
            before = cur.fetchone()
            if not before:
                raise HTTPException(status_code=404, detail="Chưa có cấu hình vòng quay.")
            cur.execute("UPDATE gacha.wheel_rules SET category_weights=%s WHERE config_version_id=%s",
                        (Jsonb(weights), before["config_version_id"]))
            audit_write(cur, actor=actor, action="UPDATE_WHEEL_RATES", object_type="WHEEL_CATEGORY_POOL",
                        object_id=str(before["config_version_id"]), before=before["category_weights"],
                        after=weights, reason="ADMIN_BALANCE_UPDATE")
    return {"ok": True, "total_percent": 100}


@app.get("/api/gameplay/drop-rates")
def gameplay_drop_rates(config: str = Query("LK-V4.0-P20-RC-002")) -> dict[str, Any]:
    ensure_live_available()
    rows=live_query("""
        SELECT version_code,profile_code,asset_code,display_name_vi,icon_glyph,
               weight_bps AS chance_bps,rate_percent AS chance_percent,
               minimum_quantity,maximum_quantity,pool_total_bps
        FROM admin.v_monster_reward_asset_drop_rates WHERE version_code=%s
        ORDER BY asset_code
    """,(config,))
    ore=live_query("""
        SELECT rule.rarity::text AS rarity,rule.drop_chance_bps,
               round(rule.drop_chance_bps::numeric/100,2) AS chance_percent,
               rule.minimum_quantity,rule.maximum_quantity,rule.craft_cost
        FROM inventory.equipment_ore_drop_rules rule
        JOIN platform.config_versions version ON version.id=rule.config_version_id
        WHERE version.version_code=%s AND rule.enabled
        ORDER BY CASE rule.rarity::text WHEN 'COMMON' THEN 1 WHEN 'UNCOMMON' THEN 2 WHEN 'RARE' THEN 3
          WHEN 'EPIC' THEN 4 WHEN 'LEGENDARY' THEN 5 WHEN 'MYTHIC' THEN 6 WHEN 'ANCIENT' THEN 7
          WHEN 'DIVINE' THEN 8 WHEN 'RELIC' THEN 9 WHEN 'GOD' THEN 10 END
    """,(config,))
    return {"config":config,"resources":_json_safe(rows),"specialized_ores":_json_safe(ore),
            "resource_total_bps":sum(int(row["chance_bps"]) for row in rows)}


@app.put("/api/gameplay/drop-rates")
def update_gameplay_drop_rates(payload: dict[str, Any], x_admin_token: str | None = Header(default=None),
                               x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available();require_write_token(x_admin_token)
    config=str(payload.get("config") or "LK-V4.0-P20-RC-002");submitted=payload.get("items")
    if not isinstance(submitted,list) or not submitted:
        raise HTTPException(status_code=400,detail="Nhập đầy đủ tỷ lệ tài nguyên.")
    normalized=[];seen=set()
    for item in submitted:
        code=str((item or {}).get("asset_code") or "").strip()
        try:
            percent=Decimal(str((item or {}).get("rate_percent")))
            minimum=Decimal(str((item or {}).get("minimum_quantity")))
            maximum=Decimal(str((item or {}).get("maximum_quantity")))
        except (InvalidOperation,TypeError):
            raise HTTPException(status_code=400,detail=f"Dữ liệu của {code or 'vật phẩm'} không hợp lệ.")
        scaled=percent*100
        if not code or code in seen or percent<0 or percent>100 or scaled!=scaled.to_integral_value():
            raise HTTPException(status_code=400,detail="Mỗi tỷ lệ phải từ 0 đến 100%, tối đa 2 số lẻ.")
        if minimum!=minimum.to_integral_value() or maximum!=maximum.to_integral_value() or minimum<0 or maximum<minimum:
            raise HTTPException(status_code=400,detail=f"Số lượng của {code} phải là số nguyên không âm; tối đa không nhỏ hơn tối thiểu.")
        seen.add(code);normalized.append({"asset_code":code,"weight_bps":int(scaled),"minimum_quantity":int(minimum),"maximum_quantity":int(maximum)})
    total=sum(item["weight_bps"] for item in normalized)
    if total>10000:
        raise HTTPException(status_code=400,detail=f"Tổng tỷ lệ không được vượt 100%. Hiện tại: {Decimal(total)/100}%.")
    actor=ADMIN_OWNER_NAME if LOCAL_OWNER_EFFECTIVE else (x_admin_actor or ADMIN_ACTOR_DEFAULT)
    assert psycopg is not None and dict_row is not None and Jsonb is not None
    with psycopg.connect(DATABASE_URL,row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT asset_code,weight_bps,minimum_quantity,maximum_quantity
                           FROM admin.v_monster_reward_asset_drop_rates WHERE version_code=%s ORDER BY asset_code""",(config,))
            before=[dict(row) for row in cur.fetchall()];expected={str(row["asset_code"]) for row in before}
            if not expected: raise HTTPException(status_code=404,detail="Không tìm thấy pool tài nguyên của phiên bản này.")
            if seen!=expected: raise HTTPException(status_code=400,detail="Phải gửi đủ mọi tài nguyên; không được thiếu hoặc thêm mã lạ.")
            cur.execute("""UPDATE content.monster_reward_asset_drop_rules rule
                           SET weight_bps=input.weight_bps,minimum_quantity=input.minimum_quantity,
                               maximum_quantity=input.maximum_quantity,updated_at=now(),updated_by=%s
                           FROM jsonb_to_recordset(%s::jsonb) AS input(asset_code text,weight_bps integer,minimum_quantity integer,maximum_quantity integer)
                           WHERE rule.asset_code=input.asset_code
                             AND rule.config_version_id=(SELECT id FROM platform.config_versions WHERE version_code=%s)""",
                        (actor,Jsonb(normalized),config))
            if cur.rowcount!=len(normalized): raise HTTPException(status_code=409,detail="Dữ liệu đã thay đổi; hãy tải lại trước khi lưu.")
            audit_write(cur,actor=actor,action="UPDATE_RESOURCE_DROP_RATES",object_type="MONSTER_RESOURCE_DROP_POOL",
                        object_id=config,before={"items":before},after={"items":normalized},reason="ADMIN_BALANCE_UPDATE")
    return {"ok":True,"config":config,"total_percent":str(Decimal(total)/100),"updated":len(normalized)}


@app.get("/api/gameplay/item-drop-rates")
def equipment_item_drop_rates(config: str = Query("LK-V4.0-P20-RC-002"),
                              slot: str = Query("HELM"), rarity: str = Query("COMMON")) -> dict[str, Any]:
    ensure_live_available();slot=slot.upper();rarity=rarity.upper()
    rows=live_query("""
        SELECT item_code,display_name_vi,equipment_slot,rarity,weight_bps,rate_percent,
               pool_total_bps,image_asset_key
        FROM admin.v_equipment_item_drop_rates
        WHERE version_code=%s AND equipment_slot=%s AND rarity=%s
        ORDER BY item_code
    """,(config,slot,rarity))
    for row in rows: row["image_url"]=media_url_for_key(row.get("image_asset_key"))
    groups=live_query("""
        SELECT equipment_slot,rarity,count(*) AS item_count,max(pool_total_bps) AS total_bps
        FROM admin.v_equipment_item_drop_rates WHERE version_code=%s
        GROUP BY equipment_slot,rarity ORDER BY equipment_slot,rarity
    """,(config,))
    return {"config":config,"slot":slot,"rarity":rarity,"items":_json_safe(rows),"groups":_json_safe(groups),
            "total_bps":sum(int(row["weight_bps"]) for row in rows)}


@app.put("/api/gameplay/item-drop-rates")
def update_equipment_item_drop_rates(payload: dict[str, Any], x_admin_token: str | None = Header(default=None),
                                     x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available();require_write_token(x_admin_token)
    config=str(payload.get("config") or "LK-V4.0-P20-RC-002");slot=str(payload.get("slot") or "").upper();rarity=str(payload.get("rarity") or "").upper()
    submitted=payload.get("items")
    if not slot or not rarity or not isinstance(submitted,list) or not submitted:
        raise HTTPException(status_code=400,detail="Chọn vị trí, phẩm chất và nhập đầy đủ tỷ lệ vật phẩm.")
    normalized=[];seen=set()
    for item in submitted:
        code=str((item or {}).get("item_code") or "").strip()
        try: percent=Decimal(str((item or {}).get("rate_percent")))
        except (InvalidOperation,TypeError): raise HTTPException(status_code=400,detail=f"Tỷ lệ của {code or 'vật phẩm'} không hợp lệ.")
        scaled=percent*100
        if not code or code in seen or percent<0 or percent>100 or scaled!=scaled.to_integral_value():
            raise HTTPException(status_code=400,detail="Mỗi vật phẩm phải duy nhất, từ 0 đến 100%, tối đa 2 số lẻ.")
        seen.add(code);normalized.append({"item_code":code,"weight_bps":int(scaled)})
    total=sum(item["weight_bps"] for item in normalized)
    if total!=10000: raise HTTPException(status_code=400,detail=f"Tổng tỷ lệ phải đúng 100%. Hiện tại: {Decimal(total)/100}%.")
    actor=ADMIN_OWNER_NAME if LOCAL_OWNER_EFFECTIVE else (x_admin_actor or ADMIN_ACTOR_DEFAULT)
    assert psycopg is not None and dict_row is not None and Jsonb is not None
    with psycopg.connect(DATABASE_URL,row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT rate.item_code,rate.weight_bps FROM admin.v_equipment_item_drop_rates rate
                           WHERE rate.version_code=%s AND rate.equipment_slot=%s AND rate.rarity=%s ORDER BY rate.item_code""",(config,slot,rarity))
            before=[dict(row) for row in cur.fetchall()]
            expected={str(row["item_code"]) for row in before}
            if not expected: raise HTTPException(status_code=404,detail="Không tìm thấy pool vật phẩm này.")
            if seen!=expected: raise HTTPException(status_code=400,detail="Phải gửi đủ mọi vật phẩm trong pool; không được thiếu hoặc thêm mã lạ.")
            cur.execute("""UPDATE inventory.equipment_item_drop_weights weight SET weight_bps=input.weight_bps,updated_at=now(),updated_by=%s
                           FROM jsonb_to_recordset(%s::jsonb) AS input(item_code text,weight_bps integer)
                           WHERE weight.item_code=input.item_code AND weight.config_version_id=(SELECT id FROM platform.config_versions WHERE version_code=%s)""",
                        (actor,Jsonb(normalized),config))
            if cur.rowcount!=len(normalized): raise HTTPException(status_code=409,detail="Số vật phẩm cập nhật không khớp; dữ liệu đã thay đổi, hãy tải lại.")
            after=[{"item_code":item["item_code"],"weight_bps":item["weight_bps"]} for item in normalized]
            audit_write(cur,actor=actor,action="UPDATE_DROP_RATES",object_type="EQUIPMENT_DROP_POOL",object_id=f"{config}:{slot}:{rarity}",before={"items":before},after={"items":after},reason="ADMIN_BALANCE_UPDATE")
    return {"ok":True,"config":config,"slot":slot,"rarity":rarity,"total_percent":100,"updated":len(normalized)}


@app.get("/api/consumable-assets")
def consumable_assets() -> dict[str, Any]:
    ensure_live_available()
    rows=live_query("""
        SELECT DISTINCT ON (definition.code) definition.id::text AS item_def_id,definition.code,
               definition.display_name_vi,definition.config_version_id,definition.image_asset_key,
               COALESCE(link.asset_key,definition.image_asset_key) AS primary_asset_key
        FROM inventory.item_defs definition
        LEFT JOIN LATERAL (SELECT media.asset_key FROM platform.entity_media_links media
          WHERE media.entity_type='ITEM_DEF' AND media.entity_id=definition.id::text AND media.is_primary
          ORDER BY media.created_at DESC LIMIT 1) link ON true
        WHERE definition.item_type='CONSUMABLE'
        ORDER BY definition.code,definition.config_version_id DESC
    """)
    for row in rows:
        row["image_url"]=media_url_for_key(row.get("primary_asset_key"))
    return {"rows":_json_safe(rows),"total":len(rows),"with_images":sum(1 for row in rows if row.get("primary_asset_key"))}


def _persist_consumable_image(item_code: str, *, raw: bytes, original_filename: str | None, actor: str) -> dict[str, Any]:
    webp,width,height=_process_image_to_webp(raw);digest=hashlib.sha256(webp).hexdigest()
    key=f"consumables/{item_code.lower()}/{digest[:24]}.webp";backend=effective_media_backend();old_keys:set[str]=set()
    assert psycopg is not None and dict_row is not None
    with psycopg.connect(DATABASE_URL,row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id::text,image_asset_key FROM inventory.item_defs WHERE code=%s AND item_type='CONSUMABLE' ORDER BY config_version_id FOR UPDATE",(item_code,));definitions=cur.fetchall()
            if not definitions: raise HTTPException(status_code=404,detail="Consumable item not found.")
            old_keys={str(row["image_asset_key"]) for row in definitions if row.get("image_asset_key")}
            if backend=="database": _write_db_media(cur,asset_key=key,content=webp,content_type="image/webp",sha256=digest,width=width,height=height,original_filename=original_filename,actor=actor)
            else: _save_local_asset(key,webp)
            for definition in definitions:
                item_def_id=definition["id"]
                cur.execute("UPDATE inventory.item_defs SET image_asset_key=%s WHERE id=%s::uuid",(key,item_def_id))
                cur.execute("UPDATE platform.entity_media_links SET is_primary=false,media_role=CASE WHEN media_role='PRIMARY' THEN 'GALLERY' ELSE media_role END WHERE entity_type='ITEM_DEF' AND entity_id=%s AND is_primary",(item_def_id,))
                cur.execute("""INSERT INTO platform.entity_media_links(entity_type,entity_id,asset_key,media_role,sort_order,is_primary,created_by,metadata)
                               VALUES('ITEM_DEF',%s,%s,'PRIMARY',0,true,%s,%s::jsonb)
                               ON CONFLICT(entity_type,entity_id,asset_key) DO UPDATE SET media_role='PRIMARY',sort_order=0,is_primary=true,metadata=EXCLUDED.metadata""",
                            (item_def_id,key,actor,json.dumps({"source":"ADMIN_CONSUMABLE_UPLOAD","v":"7.2"})))
            cur.execute("UPDATE platform.entity_media_links SET is_primary=false,media_role=CASE WHEN media_role='PRIMARY' THEN 'GALLERY' ELSE media_role END WHERE entity_type='ITEM_CODE' AND entity_id=%s AND is_primary",(item_code,))
            cur.execute("""INSERT INTO platform.entity_media_links(entity_type,entity_id,asset_key,media_role,sort_order,is_primary,created_by,metadata)
                           VALUES('ITEM_CODE',%s,%s,'PRIMARY',0,true,%s,%s::jsonb)
                           ON CONFLICT(entity_type,entity_id,asset_key) DO UPDATE SET media_role='PRIMARY',sort_order=0,is_primary=true,metadata=EXCLUDED.metadata""",
                        (item_code,key,actor,json.dumps({"source":"ADMIN_CONSUMABLE_UPLOAD","v":"7.2"})))
            audit_write(cur,actor=actor,action="CONSUMABLE_IMAGE_UPLOAD",object_type="inventory.item_defs",object_id=item_code,before={"image_asset_keys":sorted(old_keys)},after={"image_asset_key":key,"sha256":digest},reason="ADMIN_DIRECT_UPLOAD")
            if backend=="database":
                for old_key in old_keys:
                    if old_key!=key:_delete_db_asset_if_orphan(cur,old_key)
        conn.commit()
    if backend=="filesystem":
        for old_key in old_keys:
            if old_key!=key:_delete_local_asset(old_key)
    return {"ok":True,"code":item_code,"asset_key":key,"image_url":media_url_for_key(key),"media_backend":backend,"width":width,"height":height,"size_bytes":len(webp)}


@app.post("/api/consumable-assets/{item_code}/image")
async def upload_consumable_asset_image(item_code: str, file: UploadFile = File(...), x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available();require_write_token(x_admin_token);raw=await file.read(MAX_IMAGE_BYTES+1)
    if not raw: raise HTTPException(status_code=400,detail="Empty image file.")
    if len(raw)>MAX_IMAGE_BYTES: raise HTTPException(status_code=413,detail=f"Image is larger than {MAX_IMAGE_MB} MB.")
    actor=ADMIN_OWNER_NAME if LOCAL_OWNER_EFFECTIVE else (x_admin_actor or ADMIN_ACTOR_DEFAULT)
    return _persist_consumable_image(item_code,raw=raw,original_filename=file.filename,actor=actor)


@app.delete("/api/consumable-assets/{item_code}/image")
def delete_consumable_asset_image(item_code: str, x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available();require_write_token(x_admin_token);actor=ADMIN_OWNER_NAME if LOCAL_OWNER_EFFECTIVE else (x_admin_actor or ADMIN_ACTOR_DEFAULT)
    assert psycopg is not None and dict_row is not None
    backend=effective_media_backend();old_keys:set[str]=set()
    with psycopg.connect(DATABASE_URL,row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id::text,image_asset_key FROM inventory.item_defs WHERE code=%s AND item_type='CONSUMABLE' FOR UPDATE",(item_code,));definitions=cur.fetchall()
            if not definitions: raise HTTPException(status_code=404,detail="Consumable item not found.")
            old_keys={str(row["image_asset_key"]) for row in definitions if row.get("image_asset_key")}
            cur.execute("UPDATE inventory.item_defs SET image_asset_key=NULL WHERE code=%s AND item_type='CONSUMABLE'",(item_code,))
            for definition in definitions: cur.execute("DELETE FROM platform.entity_media_links WHERE entity_type='ITEM_DEF' AND entity_id=%s",(definition["id"],))
            cur.execute("DELETE FROM platform.entity_media_links WHERE entity_type='ITEM_CODE' AND entity_id=%s",(item_code,))
            if backend=="database":
                for old_key in old_keys:_delete_db_asset_if_orphan(cur,old_key)
            audit_write(cur,actor=actor,action="CONSUMABLE_IMAGE_DELETE",object_type="inventory.item_defs",object_id=item_code,before={"image_asset_keys":sorted(old_keys)},after={"image_asset_key":None},reason="ADMIN_DIRECT_UPLOAD")
        conn.commit()
    if backend=="filesystem":
        for old_key in old_keys:_delete_local_asset(old_key)
    return {"ok":True,"code":item_code,"deleted_asset_keys":sorted(old_keys)}


@app.get("/api/crafting-ores")
def crafting_ores(q: str = Query(""), rarity: str = Query(""), slot: str = Query("")) -> dict[str, Any]:
    ensure_live_available()
    filters=["metadata->>'material_family'='EQUIPMENT_ORE'"]; args=[]
    if q.strip():
        filters.append("(code ILIKE %s OR COALESCE(metadata->>'display_name_vi','') ILIKE %s)")
        like=f"%{q.strip()}%"; args += [like,like]
    if rarity.strip(): filters.append("metadata->>'target_rarity'=%s"); args.append(rarity.strip().upper())
    if slot.strip(): filters.append("metadata->>'target_slot'=%s"); args.append(slot.strip().upper())
    rows=live_query(
        f"""SELECT code,asset_type,integrity_tier::text AS integrity_tier,precision_scale,transferable,metadata
            FROM economy.asset_defs WHERE {' AND '.join(filters)}
            ORDER BY COALESCE((metadata->>'rarity_ordinal')::int,0),COALESCE((metadata->>'slot_ordinal')::int,0),code""",
        tuple(args),
    )
    out=[_decorate_asset(r) for r in rows]
    return {"rows":_json_safe(out),"total":len(out),"expected":90}


def _persist_economy_asset_image(asset_code: str, *, raw: bytes, original_filename: str | None, actor: str) -> dict[str, Any]:
    webp,width,height=_process_image_to_webp(raw); digest=hashlib.sha256(webp).hexdigest()
    key=f"economy/{asset_code.lower()}/{digest[:24]}.webp"; backend=effective_media_backend()
    assert psycopg is not None and dict_row is not None
    old_key=None
    with psycopg.connect(DATABASE_URL,row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT code,metadata FROM economy.asset_defs WHERE code=%s FOR UPDATE",(asset_code,)); old=cur.fetchone()
            if old is None: raise HTTPException(status_code=404,detail="Economy asset not found. Run V7 SQL migration first for crafting ores.")
            old_meta=dict(old).get("metadata") or {}; old_key=(old_meta or {}).get("image_asset_key") if isinstance(old_meta,dict) else None
            if backend=="database":
                _write_db_media(cur,asset_key=key,content=webp,content_type="image/webp",sha256=digest,width=width,height=height,original_filename=original_filename,actor=actor)
            else: _save_local_asset(key,webp)
            cur.execute("UPDATE platform.entity_media_links SET is_primary=false,media_role=CASE WHEN media_role='PRIMARY' THEN 'GALLERY' ELSE media_role END WHERE entity_type='ECONOMY_ASSET' AND entity_id=%s AND is_primary=true",(asset_code,))
            cur.execute("""INSERT INTO platform.entity_media_links(entity_type,entity_id,asset_key,media_role,sort_order,is_primary,created_by,metadata)
                           VALUES('ECONOMY_ASSET',%s,%s,'PRIMARY',0,true,%s,%s::jsonb)
                           ON CONFLICT(entity_type,entity_id,asset_key) DO UPDATE SET media_role='PRIMARY',sort_order=0,is_primary=true,metadata=EXCLUDED.metadata""",
                        (asset_code,key,actor,json.dumps({"source":"ADMIN_DIRECT_UPLOAD","v":"7.1"})))
            cur.execute("UPDATE economy.asset_defs SET metadata=jsonb_set(COALESCE(metadata,'{}'::jsonb),'{image_asset_key}',to_jsonb(%s::text),true) WHERE code=%s",(key,asset_code))
            audit_write(cur,actor=actor,action="ECONOMY_ASSET_IMAGE_UPLOAD",object_type="economy.asset_defs",object_id=asset_code,before={"image_asset_key":old_key},after={"image_asset_key":key,"sha256":digest},reason="ADMIN_DIRECT_UPLOAD")
            if backend=="database" and old_key and old_key!=key: _delete_db_asset_if_orphan(cur,old_key)
        conn.commit()
    if backend=="filesystem" and old_key and old_key!=key: _delete_local_asset(old_key)
    return {"ok":True,"code":asset_code,"asset_key":key,"image_url":media_url_for_key(key),"media_backend":backend,"width":width,"height":height,"size_bytes":len(webp)}


@app.post("/api/resource-assets/{asset_code}/image")
async def upload_resource_asset_image(asset_code: str, file: UploadFile = File(...), x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available(); require_write_token(x_admin_token)
    raw=await file.read(MAX_IMAGE_BYTES+1)
    if not raw: raise HTTPException(status_code=400,detail="Empty image file.")
    if len(raw)>MAX_IMAGE_BYTES: raise HTTPException(status_code=413,detail=f"Image is larger than {MAX_IMAGE_MB} MB.")
    actor=ADMIN_OWNER_NAME if LOCAL_OWNER_EFFECTIVE else (x_admin_actor or ADMIN_ACTOR_DEFAULT)
    return _persist_economy_asset_image(asset_code,raw=raw,original_filename=file.filename,actor=actor)


@app.delete("/api/resource-assets/{asset_code}/image")
def delete_resource_asset_image(asset_code: str, x_admin_token: str | None = Header(default=None), x_admin_actor: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available(); require_write_token(x_admin_token)
    actor=ADMIN_OWNER_NAME if LOCAL_OWNER_EFFECTIVE else (x_admin_actor or ADMIN_ACTOR_DEFAULT)
    assert psycopg is not None and dict_row is not None
    backend=effective_media_backend(); old_key=None
    with psycopg.connect(DATABASE_URL,row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT metadata FROM economy.asset_defs WHERE code=%s FOR UPDATE",(asset_code,)); r=cur.fetchone()
            if r is None:
                cur.execute("SELECT asset_key FROM platform.entity_media_links WHERE entity_type='ECONOMY_ASSET' AND entity_id=%s AND is_primary=true FOR UPDATE",(asset_code,)); link=cur.fetchone()
                if link is None: raise HTTPException(status_code=404,detail="Economy asset image not found.")
                old_key=str(link["asset_key"])
            else:
                meta=r.get("metadata") or {}; old_key=meta.get("image_asset_key") if isinstance(meta,dict) else None
                cur.execute("UPDATE economy.asset_defs SET metadata=COALESCE(metadata,'{}'::jsonb)-'image_asset_key' WHERE code=%s",(asset_code,))
            cur.execute("DELETE FROM platform.entity_media_links WHERE entity_type='ECONOMY_ASSET' AND entity_id=%s AND is_primary=true",(asset_code,))
            if backend=="database" and old_key: _delete_db_asset_if_orphan(cur,old_key)
            audit_write(cur,actor=actor,action="ECONOMY_ASSET_IMAGE_DELETE",object_type="economy.asset_defs" if r is not None else "platform.entity_media_links",object_id=asset_code,before={"image_asset_key":old_key},after={"image_asset_key":None},reason="ADMIN_DIRECT_UPLOAD")
        conn.commit()
    if backend=="filesystem" and old_key: _delete_local_asset(old_key)
    return {"ok":True,"code":asset_code,"deleted_asset_key":old_key}


@app.get("/api/public/assets/{asset_code}/image")
def public_economy_asset_image(asset_code: str) -> Response:
    ensure_live_available()
    rows=live_query("SELECT code,metadata FROM economy.asset_defs WHERE code=%s",(asset_code,))
    if not rows: raise HTTPException(status_code=404,detail="Unknown economy asset.")
    key=_asset_image_key(rows[0])
    if not key: raise HTTPException(status_code=404,detail="Economy asset has no image.")
    found=_read_media_asset(key)
    if not found: raise HTTPException(status_code=404,detail="Economy asset image is missing from shared media.")
    content,ctype=found; etag=hashlib.sha256(content).hexdigest()
    return Response(content=content,media_type=ctype,headers={"ETag":etag,"Cache-Control":"public, max-age=3600"})


@app.post("/api/resource-assets/seed-demo-icons")
def seed_resource_demo_icons(force: bool = Query(False), x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_live_available(); require_write_token(x_admin_token)
    script=ROOT/'seed_resource_ore_icons.py'
    if not script.exists(): raise HTTPException(status_code=500,detail="seed_resource_ore_icons.py missing.")
    cmd=[sys.executable,str(script),'--apply'] + (['--force'] if force else [])
    try:
        proc=subprocess.run(cmd,cwd=str(ROOT),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=300)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504,detail="Resource/Ore media seed timed out after 5 minutes.")
    return {"ok":proc.returncode==0,"returncode":proc.returncode,"output":(proc.stdout+("\n"+proc.stderr if proc.stderr else "")).strip()}

@app.exception_handler(Exception)
async def unhandled_error(_request, exc: Exception):  # type: ignore[no-untyped-def]
    if isinstance(exc, HTTPException):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return JSONResponse({"detail": f"Admin server error: {type(exc).__name__}"}, status_code=500)


if __name__ == "__main__":
    import uvicorn
    host = ADMIN_HOST_CONFIG
    port = int(os.getenv("ADMIN_PORT", "8787"))
    uvicorn.run("admin_server:app", host=host, port=port, reload=False)
