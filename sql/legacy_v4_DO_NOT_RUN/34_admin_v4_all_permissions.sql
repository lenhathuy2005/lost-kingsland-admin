-- Lost Kingsland Admin SUPER MEGA v4 — apply after 20_admin_roles.sql and media patches.
-- This script is additive and can be rerun safely after the optional v4 media tables exist.

GRANT SELECT, INSERT, UPDATE, DELETE ON platform.media_assets TO lk_admin_config_editor;
GRANT SELECT, INSERT, UPDATE, DELETE ON platform.entity_media_links TO lk_admin_config_editor;
GRANT SELECT, INSERT, UPDATE ON ops.compensation_cases, ops.player_sanctions TO lk_admin_config_editor;
GRANT INSERT ON ops.audit_logs TO lk_admin_config_editor;
