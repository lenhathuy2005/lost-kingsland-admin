#!/usr/bin/env python3
"""Build a read-only JSON snapshot from a plain pg_dump SQL file.

This script intentionally parses only COPY ... FROM stdin blocks and CREATE TABLE
metadata. It does not execute SQL. That makes it safe to use against a gameplay dump
without mutating a database.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

COPY_RE = re.compile(r"^COPY\s+([a-zA-Z_][\w]*)\.([a-zA-Z_][\w]*)\s+\((.*?)\)\s+FROM\s+stdin;$")
CREATE_TABLE_RE = re.compile(r"^CREATE TABLE\s+([a-zA-Z_][\w]*)\.([a-zA-Z_][\w]*)\s+\($")
DUMP_STARTED_RE = re.compile(r"^-- Started on (.+)$")


def pg_copy_unescape(value: str) -> str | None:
    if value == r"\N":
        return None
    # PostgreSQL text COPY escapes. Order matters: decode manually instead of unicode_escape.
    out = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch != "\\" or i + 1 >= len(value):
            out.append(ch)
            i += 1
            continue
        nxt = value[i + 1]
        mapping = {"t": "\t", "n": "\n", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "\\": "\\"}
        if nxt in mapping:
            out.append(mapping[nxt])
            i += 2
        else:
            # Preserve unknown escapes rather than silently corrupting data.
            out.append(nxt)
            i += 2
    return "".join(out)


def parse_pg_array(text: str) -> list[str] | str:
    if not (text.startswith("{") and text.endswith("}")):
        return text
    inner = text[1:-1]
    if not inner:
        return []
    # Good enough for this dump's simple varchar arrays; fall back to raw text for complex quoted arrays.
    if '"' in inner:
        return text
    return [x for x in inner.split(",")]


def convert_scalar(value: str | None) -> Any:
    if value is None:
        return None
    if value == "t":
        return True
    if value == "f":
        return False
    if re.fullmatch(r"-?\d+", value):
        try:
            return int(value)
        except ValueError:
            pass
    if re.fullmatch(r"-?\d+\.\d+", value):
        try:
            return float(value)
        except ValueError:
            pass
    if value.startswith(("{", "[")):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            if value.startswith("{"):
                return parse_pg_array(value)
    return value


def parse_dump(path: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    lines = path.read_text("utf-8", errors="replace").splitlines()
    data: dict[str, list[dict[str, Any]]] = {}
    table_defs: set[str] = set()
    started_at = None

    i = 0
    while i < len(lines):
        line = lines[i]
        if started_at is None:
            m = DUMP_STARTED_RE.match(line)
            if m:
                started_at = m.group(1).strip()
        m = CREATE_TABLE_RE.match(line)
        if m:
            table_defs.add(f"{m.group(1)}.{m.group(2)}")
        m = COPY_RE.match(line)
        if not m:
            i += 1
            continue
        schema, table, cols_raw = m.groups()
        cols = [c.strip() for c in cols_raw.split(",")]
        rows: list[dict[str, Any]] = []
        i += 1
        while i < len(lines) and lines[i] != r"\.":
            parts = lines[i].split("\t")
            if len(parts) != len(cols):
                # Preserve visibility of malformed rows instead of failing the entire snapshot.
                rows.append({"__raw__": lines[i], "__parse_error__": f"expected {len(cols)} columns, got {len(parts)}"})
            else:
                row = {col: convert_scalar(pg_copy_unescape(raw)) for col, raw in zip(cols, parts)}
                rows.append(row)
            i += 1
        data[f"{schema}.{table}"] = rows
        i += 1

    # pg_dump includes empty COPY blocks for most tables, so use CREATE TABLE list as a completeness check.
    for table in table_defs:
        data.setdefault(table, [])

    meta = {
        "source_file": path.name,
        "dump_started_at": started_at,
        "table_count": len(table_defs),
        "copy_table_count": sum(1 for k in data if k in table_defs),
        "row_count": sum(len(v) for v in data.values()),
    }
    return data, meta


def index_by(rows: list[dict[str, Any]], key: str) -> dict[Any, dict[str, Any]]:
    return {r.get(key): r for r in rows if r.get(key) is not None}


def build_derived(data: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    accounts = index_by(data.get("identity.accounts", []), "id")
    heroes = index_by(data.get("hero.player_heroes", []), "id")
    hero_by_player = {r.get("player_id"): r for r in data.get("hero.player_heroes", []) if r.get("player_id") is not None}
    primary_links: dict[Any, dict[str, Any]] = {}
    for link in data.get("identity.discord_links", []):
        if link.get("is_primary") and link.get("revoked_at") is None:
            primary_links[link.get("account_id")] = link

    players = []
    for p in data.get("identity.players", []):
        a = accounts.get(p.get("account_id"), {})
        h = hero_by_player.get(p.get("id"), {})
        dl = primary_links.get(p.get("account_id"), {})
        players.append({
            "player_id": p.get("id"),
            "player_name": p.get("display_name"),
            "account_level": p.get("account_level"),
            "account_xp": p.get("account_xp"),
            "account_status": a.get("status"),
            "locale": a.get("locale"),
            "timezone": a.get("timezone"),
            "discord_user_id": dl.get("discord_user_id"),
            "discord_username": dl.get("discord_username"),
            "hero_id": h.get("id"),
            "hero_name": h.get("name"),
            "hero_level": h.get("level"),
            "race_code": h.get("race_code"),
            "path_code": h.get("path_code"),
            "realm_code": h.get("realm_code"),
            "realm_minor_stage": h.get("realm_minor_stage"),
            "cultivation_qi": h.get("cultivation_qi"),
            "cultivation_progress": h.get("cultivation_progress"),
            "tribulation_fail_streak": h.get("tribulation_fail_streak"),
            "created_at": p.get("created_at"),
        })

    rarity_policy = {r.get("rarity"): r.get("power_ordinal") for r in data.get("inventory.rarity_policy", [])}
    config_versions = index_by(data.get("platform.config_versions", []), "id")
    final_gameplay_config_id = next((r.get("id") for r in data.get("platform.config_versions", [])
                                     if r.get("version_code") == "LK-V4.0-P15-RC-001"), None)
    set_defs = index_by(data.get("inventory.equipment_set_defs", []), "set_code")
    affix_map = {}
    for row in data.get("inventory.equipment_affix_combinations", []):
        affix_map[(row.get("equipment_slot"), row.get("combo_code"), row.get("config_version_id"))] = row

    item_catalog = []
    for d in data.get("inventory.item_defs", []):
        if final_gameplay_config_id is not None:
            if d.get("config_version_id") != final_gameplay_config_id or d.get("catalog_status") != "ACTIVE_CANONICAL":
                continue
        sd = set_defs.get(d.get("set_code"), {}) if d.get("set_code") else {}
        eac = affix_map.get((d.get("equipment_slot"), d.get("affix_combo_code"), d.get("config_version_id")), {})
        cv = config_versions.get(d.get("config_version_id"), {})
        allowed = eac.get("stat_codes") or []
        item_catalog.append({
            "item_def_id": d.get("id"),
            "item_code": d.get("code"),
            "item_name": d.get("display_name_vi"),
            "image_asset_key": d.get("image_asset_key"),
            "item_type": d.get("item_type"),
            "family_code": d.get("family_code"),
            "equipment_slot": d.get("equipment_slot"),
            "affix_combo_code": d.get("affix_combo_code"),
            "allowed_stat_combination": allowed,
            "stat_count": len(allowed) if isinstance(allowed, list) else None,
            "rarity": d.get("rarity"),
            "rarity_ordinal": rarity_policy.get(d.get("rarity")),
            "set_code": d.get("set_code"),
            "set_name": d.get("set_name"),
            "set_identity": sd.get("identity_summary"),
            "is_set_piece": d.get("set_code") is not None,
            "transferable": d.get("transferable"),
            "base_stats": d.get("base_stats"),
            "base_effects": d.get("base_effects"),
            "tags": d.get("tags"),
            "salvage_rule": d.get("salvage_rule"),
            "config_version": cv.get("version_code"),
        })
    item_catalog.sort(key=lambda x: (x.get("rarity_ordinal") or 999, x.get("equipment_slot") or "", x.get("item_name") or ""))

    bonuses_by_set: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for b in data.get("inventory.equipment_set_bonuses", []):
        bonuses_by_set[str(b.get("set_code"))].append(b)
    sets = []
    for sd in data.get("inventory.equipment_set_defs", []):
        bonuses = sorted(bonuses_by_set.get(str(sd.get("set_code")), []), key=lambda x: x.get("pieces_required") or 0)
        sets.append({**sd, "rarity_ordinal": rarity_policy.get(sd.get("rarity")), "bonuses": bonuses})
    sets.sort(key=lambda x: (x.get("rarity_ordinal") or 999, x.get("set_name") or ""))

    item_defs_by_code_version = {(r.get("code"), r.get("config_version_id")): r for r in data.get("inventory.item_defs", [])}
    player_names = {r.get("id"): r.get("display_name") for r in data.get("identity.players", [])}
    hero_names = {r.get("id"): r.get("name") for r in data.get("hero.player_heroes", [])}
    player_items = []
    for ii in data.get("inventory.item_instances", []):
        d = item_defs_by_code_version.get((ii.get("item_code"), ii.get("item_config_version_id")), {})
        player_items.append({
            "player_id": ii.get("owner_player_id"),
            "owner_player_id": ii.get("owner_player_id"),
            "player_name": player_names.get(ii.get("owner_player_id")),
            "hero_id": ii.get("hero_id"),
            "hero_name": hero_names.get(ii.get("hero_id")),
            "item_instance_id": ii.get("id"),
            "item_code": ii.get("item_code"),
            "item_name": d.get("display_name_vi"),
            "image_asset_key": d.get("image_asset_key"),
            "equipment_slot": d.get("equipment_slot"),
            "rarity": ii.get("rarity"),
            "item_level": ii.get("item_level"),
            "state": ii.get("state"),
            "is_equipped": ii.get("state") == "EQUIPPED",
            "affixes": ii.get("affixes"),
            "unique_effects": ii.get("unique_effects"),
            "locked": ii.get("locked"),
            "acquired_at": ii.get("acquired_at"),
            "updated_at": ii.get("updated_at"),
        })

    rarity_counts = defaultdict(int)
    slot_counts = defaultdict(int)
    missing_image = 0
    for item in item_catalog:
        rarity_counts[str(item.get("rarity"))] += 1
        slot_counts[str(item.get("equipment_slot"))] += 1
        if not item.get("image_asset_key"):
            missing_image += 1

    feature_flags = data.get("platform.feature_flags", [])
    sample_items = sum(1 for i in item_catalog if "SAMPLE" in str(i.get("item_code") or "").upper())
    production_items = len(item_catalog) - sample_items

    dashboard = {
        "players": len(players),
        "equipment_defs": len(item_catalog),
        "production_equipment_defs": production_items,
        "sample_equipment_defs": sample_items,
        "rarities": len(rarity_policy),
        "equipment_sets": len(sets),
        "set_bonuses": sum(len(x.get("bonuses", [])) for x in sets),
        "player_item_instances": len(player_items),
        "missing_item_images": missing_image,
        "feature_flags": len(feature_flags),
        "feature_flags_enabled": sum(1 for f in feature_flags if f.get("enabled")),
        "active_events": sum(1 for e in data.get("liveops.events", []) if str(e.get("status", "")).upper() in {"ACTIVE", "OPEN", "RUNNING"}),
        "abuse_signals": len(data.get("ops.abuse_signals", [])),
        "rarity_counts": dict(rarity_counts),
        "slot_counts": dict(slot_counts),
    }

    schemas: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for full_name, rows in sorted(data.items()):
        schema, table = full_name.split(".", 1)
        schemas[schema].append({"table": table, "row_count": len(rows)})

    return {
        "dashboard": dashboard,
        "players": players,
        "item_catalog": item_catalog,
        "equipment_sets": sets,
        "player_items": player_items,
        "schemas": dict(schemas),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dump", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    data, meta = parse_dump(args.dump)
    derived = build_derived(data)
    payload = {"meta": meta, "derived": derived, "tables": data}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    print(f"Wrote {args.output} ({meta['table_count']} tables, {meta['row_count']} copied rows)")


if __name__ == "__main__":
    main()
