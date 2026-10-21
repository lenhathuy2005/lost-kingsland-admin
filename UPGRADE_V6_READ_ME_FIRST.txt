LOST KINGSLAND ADMIN V6 MEGAOPS — NÂNG TỪ ADMIN V27 HIỆN TẠI
==============================================================

1) Tắt Admin đang chạy.
2) Giữ nguyên file .env hiện tại của bạn. Gói V6 không chứa .env nên overwrite code sẽ không đè mật khẩu DB.
3) Ghi đè file V6 vào C:\Project\lost-kingsland-admin.
4) DBeaver -> đúng database lost_kingsland_v4_reconciled -> chạy DUY NHẤT:
      sql\00_INSTALL_V6_ALL_IN_ONE.sql
   File này có thể chạy lại; gộp đúng 20 -> 40 -> 50.
   KHÔNG chạy sql\legacy_v4_DO_NOT_RUN\*.
5) Có thể check bằng sql\99_CHECK_V6_READY.sql.
6) PowerShell:
      cd C:\Project\lost-kingsland-admin
      .\run_admin.bat
7) Trình duyệt: Ctrl+F5 rồi mở http://127.0.0.1:8787

MENU V6
- Người chơi: Player 360 + Control Center + Balance ledger-safe
- Nhân vật & Ảnh: upload trực tiếp PRIMARY/GALLERY
- Giftcode: create/edit/archive/preview/history

Local Owner: Viet / OWNER trên 127.0.0.1, không cần X-Admin-Token.
