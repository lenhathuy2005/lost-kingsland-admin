-- Lost Kingsland Admin V27 — least-privilege roles
-- Run while connected as owner to: lost_kingsland_v4_reconciled
-- Additive/rerunnable. No gameplay data mutation.

DO $$ BEGIN
  CREATE ROLE lk_admin_readonly NOLOGIN;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE ROLE lk_admin_config_editor NOLOGIN;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$
DECLARE
  s text;
  t text;
  read_schemas text[] := ARRAY[
    'admin','platform','identity','content','hero','adventure','combat','inventory',
    'kingdom','clan','competitive','liveops','economy','commerce','ops','commander',
    'media','march','market','gacha'
  ];
  editable_tables text[] := ARRAY[
    'inventory.item_defs','inventory.equipment_set_defs','inventory.equipment_set_bonuses',
    'inventory.equipment_stat_defs','inventory.equipment_affix_combinations','inventory.rarity_policy',
    'inventory.recipes','inventory.equipment_forge_recipes',
    'content.race_defs','content.path_defs','content.affinity_defs','content.bloodline_defs',
    'content.realm_defs','content.sect_defs','content.profession_defs','content.technique_defs',
    'content.tags','content.region_defs','content.node_defs','content.enemy_defs',
    'content.exploration_floor_profiles','content.monster_reward_profiles','content.building_defs',
    'content.research_defs','content.march_slot_unlock_rules','content.combat_profiles',
    'content.path_starting_techniques','content.technique_tag_links','content.section_rules',
    'content.adventure_encounter_profiles','content.technique_slot_rules',
    'hero.talent_nodes','hero.character_defs','hero.cultivation_stage_defs','hero.party_combat_rules',
    'commander.commander_defs','clan.clan_tech_defs','clan.clan_quest_defs','clan.clan_boss_defs',
    'clan.playtest_rules','economy.asset_defs','commerce.offer_defs','liveops.event_defs',
    'liveops.leaderboards','liveops.merchant_rotations','platform.feature_flags','competitive.seasons',
    'competitive.arena_rules','media.guild_media_settings','adventure.faction_boss_catalog',
    'adventure.faction_boss_reward_rules','gacha.wheel_rules','market.playtest_rules'
  ];
BEGIN
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO lk_admin_readonly', current_database());
  EXECUTE 'GRANT lk_admin_readonly TO lk_admin_config_editor';

  FOREACH s IN ARRAY read_schemas LOOP
    IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname=s) THEN
      EXECUTE format('GRANT USAGE ON SCHEMA %I TO lk_admin_readonly', s);
      EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA %I TO lk_admin_readonly', s);
    END IF;
  END LOOP;

  FOREACH t IN ARRAY editable_tables LOOP
    IF to_regclass(t) IS NOT NULL THEN
      EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE %s TO lk_admin_config_editor', t);
    END IF;
  END LOOP;

  FOREACH s IN ARRAY ARRAY['inventory','content','hero','commander','clan','economy','commerce','liveops','platform','ops','adventure','competitive','gacha','market'] LOOP
    IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname=s) THEN
      EXECUTE format('GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA %I TO lk_admin_config_editor', s);
    END IF;
  END LOOP;

  IF to_regclass('ops.audit_logs') IS NOT NULL THEN
    EXECUTE 'GRANT INSERT ON ops.audit_logs TO lk_admin_config_editor';
  END IF;
  IF to_regclass('ops.compensation_cases') IS NOT NULL THEN
    EXECUTE 'GRANT SELECT,INSERT,UPDATE ON ops.compensation_cases TO lk_admin_config_editor';
  END IF;
  IF to_regclass('ops.player_sanctions') IS NOT NULL THEN
    EXECUTE 'GRANT SELECT,INSERT,UPDATE ON ops.player_sanctions TO lk_admin_config_editor';
  END IF;
END $$;

-- Create the actual login separately, then grant the editor role:
-- CREATE ROLE lost_kingsland_admin LOGIN PASSWORD 'CHANGE_ME';
-- GRANT lk_admin_config_editor TO lost_kingsland_admin;
