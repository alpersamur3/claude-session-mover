# Changelog

## v1.2.0 - 2026-10-05

### English

- Export terminal-only Claude Code sessions; create a desktop record when restoring into a selected account.
- Clone owner-bound transcripts and subagents beside the actual source transcript, including projects with nonstandard folder names.
- Bundle edit history (`file-history`), environment files (`session-env`) and task lists (`tasks`).
- Optionally bundle project `.claude/` definitions/settings, excluding dependency and cache directories. Preserve existing project files unless overwrite is enabled.
- Add English/Turkish controls for the expanded bundle groups.
- Keep transfer controls/logs visible when resizing and add horizontal scrolling to session lists.
- Refresh the bilingual README and demo screenshots; document ownership-aware transfer, cleanup, custom roots and Claude Profiles Native usage.
- Add isolated regression tests and Windows CI. Keep PyInstaller 6.22+ as the build baseline without attributing a general failure to older releases.

### Türkçe

- Terminal Claude Code oturumları paketlenebilir; seçilen hedef hesapta masaüstü kaydı oluşturulur.
- Hesaba bağlı transkriptler ve alt ajanlar gerçek kaynak klasöründen kopyalanır; farklı proje klasörü adları doğru işlenir.
- Düzenleme geçmişi (`file-history`), ortam dosyaları (`session-env`) ve görevler (`tasks`) paketlenir.
- Proje `.claude/` tanımları/ayarları isteğe bağlı eklenir; bağımlılık ve önbellek klasörleri atlanır. Üzerine yazma açılmadıkça hedef dosyalar korunur.
- Yeni veri grupları için TR/EN arayüz seçenekleri eklendi.
- Pencere boyutu değişirken taşıma kontrolleri/günlük görünür tutulur; listeler yatay kaydırılabilir.
- README ve demo görselleri yenilendi; sahiplik bilgisine göre taşıma, temizleme, özel kökler ve Claude Profiles Native kullanımı açıklandı.
- Bağımsız regresyon testleri ve Windows CI eklendi. PyInstaller 6.22+ derleme tabanı korunurken eski sürümler hakkındaki genel hata iddiası kaldırıldı.

## v1.1.0 - 2026-09-24

- Claude Code ⇄ Codex session conversion / oturum dönüştürme.
- `.csmpack` backup and restore / yedekleme ve geri yükleme.
- Broken-session cleanup / bozuk oturum temizleme.
- Standalone Windows GUI and CLI executables / tek dosyalık Windows GUI ve CLI.
