-- Example grants. Run as DB owner and adapt role name if needed.
-- This does not create the role because installations may use a different admin DB role.

GRANT SELECT, INSERT, UPDATE, DELETE ON platform.media_assets TO lost_kingsland_admin;
GRANT SELECT, UPDATE, INSERT, DELETE ON inventory.item_defs TO lost_kingsland_admin;
GRANT INSERT, SELECT ON ops.audit_logs TO lost_kingsland_admin;
