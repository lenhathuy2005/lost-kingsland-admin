SELECT current_database(), current_user;
SELECT
  has_table_privilege(current_user,'platform.media_assets','SELECT,INSERT,UPDATE,DELETE') AS media_assets_rw,
  has_table_privilege(current_user,'platform.entity_media_links','SELECT,INSERT,UPDATE,DELETE') AS media_links_rw,
  has_table_privilege(current_user,'inventory.item_defs','UPDATE') AS item_image_update,
  has_table_privilege(current_user,'hero.character_defs','UPDATE') AS character_image_update;
