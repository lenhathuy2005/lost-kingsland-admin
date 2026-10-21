# Lost Kingsland Admin V6.3 — Diverse Semantic Media

Bản này sửa vấn đề placeholder quá lặp lại.

## Cách hoạt động
- Lần đầu Admin tải **toàn bộ PNG white/transparent của Game-icons.net** (~30 MB) từ archive chính thức.
- Archive chứa hơn 4.000 silhouette và được cache ở `data/game_icons_cache/`.
- Seeder đọc `entity_type`, `code`, tên tiếng Việt, equipment slot và rarity.
- Pet được ưu tiên đúng loài (hồ/fox, lang/wolf, quy/turtle, ưng/eagle, lộc/deer, long/dragon...).
- Element/tính chất đổi cả motif và accent (huyết/fire/mộc/frost/lôi/shadow/void/light...).
- Một silhouette đã dùng sẽ không bị lặp lại cho entity kế tiếp nếu còn lựa chọn khác.
- Ảnh nguồn được dựng lại thành WebP 512x512 dark-fantasy, có glow và frame rarity trước khi lưu PostgreSQL.

## Dùng trên Admin
`Ảnh test & Bot` → `✨ Test 30 ảnh đa dạng` → nếu ổn → `✨ Gắn full 664 ảnh đa dạng`.

Muốn đè placeholder cũ: mở `Công cụ test nâng cao` → `Thay toàn bộ bằng ảnh test` (V6.3 dùng diverse strategy), hoặc chạy `APPLY_DIVERSE_MEDIA_FORCE.bat`.

## License
Nguồn silhouette: Game-icons.net, CC BY 3.0. Attribution required nếu giữ các asset này trong build phát hành.
