LOST KINGSLAND ADMIN V6.1 — FIX PACK
====================================

BẢN NÀY SỬA 3 LỖI/ĐIỂM YẾU NHÌN THẤY TRONG V6:
1) InsufficientPrivilege khi chỉnh balance Player (economy.ledger_accounts).
2) Nhân vật & Ảnh hiện 0 vì character catalog đang ở config_version_id=13,
   trong khi gameplay config hiện tại LK-V4.0-P15-RC-001 là id=14.
3) Player Control drawer quá hẹp / input dễ hiện nền sáng / balance card rối.

NÂNG TỪ V6 ĐANG CHẠY
---------------------
A. Tắt Admin.
B. Copy/overwrite toàn bộ file của gói Upgrade Only vào:
   C:\Project\lost-kingsland-admin
C. Trong DBeaver, connection lost_kingsland_v4_reconciled, chạy DUY NHẤT:
   sql\60_v61_player_economy_permissions_hotfix.sql
D. Có thể kiểm tra bằng:
   sql\99_CHECK_V61_READY.sql
E. Chạy lại:
   .\run_admin.bat
F. Browser: Ctrl+F5 một lần (v6.1 cũng đã cache-bust CSS/JS).

KỲ VỌNG
-------
- /api/health -> version 6.1.0
- db_permissions.player_balance_ready = true
- Nhân vật & Ảnh -> 40 characters
- Character catalog note sẽ báo fallback sang config có dữ liệu nếu gameplay config
  hiện tại không chứa character_defs.
- Player drawer rộng, dark controls, balance gọn theo row.

KHÔNG CẦN CHẠY LẠI legacy 10/30/32/34.
