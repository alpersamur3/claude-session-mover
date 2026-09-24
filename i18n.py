# -*- coding: utf-8 -*-
"""
Ortak çeviri (i18n) modülü — csm.py ve csmui.py tarafından kullanılır.
Shared translation module used by both csm.py and csmui.py.

Kullanım / Usage:
    from i18n import Translator
    tr = Translator("tr")          # veya "en"
    tr.t("done")                   # -> "Bitti." / "Done."
    tr.t("found_stores", n=2)      # .format(n=2)
"""

import os

LANGS = ("tr", "en")

# key -> {"tr": ..., "en": ...}
T = {
    # --- ortak / common ---
    "app_title":        {"tr": "Claude Sohbet Taşıyıcı", "en": "Claude Chat Mover"},
    "role_source":      {"tr": "KAYNAK", "en": "SOURCE"},
    "role_target":      {"tr": "HEDEF", "en": "TARGET"},
    "none":             {"tr": "YOK", "en": "NONE"},
    "invalid":          {"tr": "Geçersiz seçim.", "en": "Invalid selection."},
    "cancelled":        {"tr": "İptal edildi.", "en": "Cancelled."},

    # --- session tipi / session type ---
    "type_code":        {"tr": "Claude Code", "en": "Claude Code"},
    "type_cowork":      {"tr": "Cowork", "en": "Cowork"},
    "choose_type":      {"tr": "=== TAŞINACAK SESSION TİPİNİ SEÇ ===",
                          "en": "=== SELECT SESSION TYPE TO MOVE ==="},
    "type_opt_code":    {"tr": "  [1] Claude Code — masaüstü sohbetleri",
                          "en": "  [1] Claude Code — desktop chats"},
    "type_opt_cowork":  {"tr": "  [2] Cowork — agent oturumları",
                          "en": "  [2] Cowork — agent sessions"},
    "type_bridge":      {"tr": "Claude ⇄ Codex", "en": "Claude ⇄ Codex"},
    "type_opt_bridge":  {"tr": "  [3] Claude Code ⇄ Codex — oturum dönüştür",
                          "en": "  [3] Claude Code ⇄ Codex — convert sessions"},
    "type_pack":        {"tr": "📦 Yedek / Aktar", "en": "📦 Backup / Transfer"},
    "type_opt_pack":    {"tr": "  [4] 📦 Yedek / Aktar — dosyaya yedekle, başka bilgisayarda geri yükle",
                          "en": "  [4] 📦 Backup / Transfer — save to a file, restore on another computer"},
    "prompt_type":      {"tr": "Tip no (1/2/3/4): ", "en": "Type no (1/2/3/4): "},
    "type_active":      {"tr": "Seçilen tip: {name}", "en": "Selected type: {name}"},

    # --- depo / store ---
    "no_store":         {"tr": "Hiçbir session deposu bulunamadı.",
                          "en": "No session store found."},
    "stores_found":     {"tr": "Bulunan session depoları (yazma hepsine aynalanır):",
                          "en": "Session stores found (writes are mirrored to all):"},
    "need_two":         {"tr": "Taşıma için en az 2 hesap gerekli. Bulunan: {n}",
                          "en": "At least 2 accounts are required. Found: {n}"},
    "multi_hint":       {"tr": "(Birden fazla hesapla giriş yaptıysan her biri ayrı klasör olur.)",
                          "en": "(If you signed in with multiple accounts, each is a separate folder.)"},
    "close_app":        {"tr": "UYARI: Devam etmeden önce Claude masaüstü uygulamasını TAMAMEN kapat.",
                          "en": "WARNING: Fully close the Claude desktop app before continuing."},

    # --- hesap seçimi / account selection ---
    "choose_account":   {"tr": "=== {role} HESABI SEÇ ===", "en": "=== SELECT {role} ACCOUNT ==="},
    "account_line":     {"tr": "  [{i}] {id}  ({n} sohbet, son: {t})",
                          "en": "  [{i}] {id}  ({n} chats, last: {t})"},
    "account_samples":  {"tr": "       örnek: {s}", "en": "       examples: {s}"},
    "no_account":       {"tr": "Uygun hesap yok.", "en": "No eligible account."},
    "no_src_accounts":  {"tr": "Bu tipte, sohbeti olan hesap yok.",
                          "en": "No account with chats for this type."},
    "auto_single":      {"tr": "(Tek uygun hesap otomatik seçildi -> {id})",
                          "en": "(Only one eligible account, auto-selected -> {id})"},
    "prompt_account":   {"tr": "{role} hesap no: ", "en": "{role} account no: "},

    # --- sohbet listesi / session list ---
    "src_sessions":     {"tr": "=== KAYNAK HESAPTAKİ SOHBETLER ({id}) ===",
                          "en": "=== CHATS IN SOURCE ACCOUNT ({id}) ==="},
    "no_sessions":      {"tr": "Bu hesapta sohbet yok.", "en": "No chats in this account."},
    "notr_flag":        {"tr": "  [!] transkript bulunamadı", "en": "  [!] transcript not found"},
    "folder_line":      {"tr": "       klasör: {cwd}   son: {t}", "en": "       folder: {cwd}   last: {t}"},
    "size_line2":       {"tr": "       boyut: sohbet {tr} / kayıt {rec}",
                          "en": "       size: chat {tr} / record {rec}"},
    "first_msg":        {"tr": "       ilk mesaj: {m}", "en": "       first message: {m}"},
    "prompt_pick":      {"tr": "Taşınacak sohbet no(ları) (virgülle birden fazla): ",
                          "en": "Chat no(s) to move (comma-separated for multiple): "},

    # --- özet / summary ---
    "summary":          {"tr": "=== ÖZET ===", "en": "=== SUMMARY ==="},
    "src_acc":          {"tr": "Kaynak hesap : {id}", "en": "Source account : {id}"},
    "tgt_acc":          {"tr": "Hedef hesap  : {id}", "en": "Target account : {id}"},
    "proceed_q":        {"tr": "Devam edilsin mi? (e/h): ", "en": "Proceed? (y/n): "},

    # --- çakışma / conflict ---
    "conflict_warn":    {"tr": "[!] UYARI: '{title}' hedef hesapta ZATEN VAR.",
                          "en": "[!] WARNING: '{title}' already EXISTS in the target account."},
    "conflict_sub":     {"tr": "    Aynı sohbet (session id) hedef hesapta bulunuyor:",
                          "en": "    The same chat (session id) is present in the target:"},
    "lbl_source_new":   {"tr": "KAYNAK (yeni) ", "en": "SOURCE (new)  "},
    "lbl_target_cur":   {"tr": "HEDEF (mevcut)", "en": "TARGET (current)"},
    "size_line":        {"tr": "     {label}: sohbet {tr} / kayıt {rec}   son: {t}   başlık: {title}",
                          "en": "     {label}: chat {tr} / record {rec}   last: {t}   title: {title}"},
    "overwrite_q":      {"tr": "    Üzerine yazılsın mı? (e/h): ", "en": "    Overwrite? (y/n): "},

    # --- sonuç / results ---
    "r_skipped":        {"tr": "    [atlandı] {title}", "en": "    [skipped] {title}"},
    "r_overwritten":    {"tr": "    [üzerine yazıldı] {title}  ({n} depoya)",
                          "en": "    [overwritten] {title}  (to {n} stores)"},
    "r_copied":         {"tr": "[ok] kopyalandı: {title}  ({n} depoya)",
                          "en": "[ok] copied: {title}  (to {n} stores)"},
    "arrow":            {"tr": "        -> {p}", "en": "        -> {p}"},
    "done":             {"tr": "Bitti. kopyalandı={c}  üzerine_yazıldı={o}  atlandı={s}",
                          "en": "Done. copied={c}  overwritten={o}  skipped={s}"},
    "reopen":           {"tr": "Şimdi Claude masaüstü uygulamasını yeniden aç.",
                          "en": "Now reopen the Claude desktop app."},
    "appear_hint":      {"tr": "Sohbet(ler) hedef hesabın listesinde görünecek.",
                          "en": "The chat(s) will appear in the target account's list."},

    # --- tanı / diagnostics ---
    "diag_hdr":         {"tr": "--- TANI BİLGİSİ (lütfen bu çıktıyla birlikte bildir) ---",
                          "en": "--- DIAGNOSTICS (please report along with this output) ---"},
    "diag_tried":       {"tr": "Denenen yollar:", "en": "Paths tried:"},
    "diag_hint":        {"tr": "İpucu: Store python sandbox sorunu olabilir. Şunu dene:",
                          "en": "Hint: This may be a Store-python sandbox issue. Try:"},
    "diag_real":        {"tr": "veya tam yol ile gerçek python:",
                          "en": "or the real python via full path:"},

    # --- GUI ---
    "g_store":          {"tr": "📁 Depo:", "en": "📁 Store:"},
    "g_refresh":        {"tr": "🔄 Yenile", "en": "🔄 Refresh"},
    "g_lang":           {"tr": "Dil:", "en": "Lang:"},
    "g_source":         {"tr": "Kaynak hesap:", "en": "Source account:"},
    "g_target":         {"tr": "Hedef hesap:", "en": "Target account:"},
    "g_target_ph":      {"tr": "— Hedef hesap seçin —", "en": "— Select target account —"},
    "g_filter":         {"tr": "🔍 Filtre:", "en": "🔍 Filter:"},
    "g_col_title":      {"tr": "Başlık", "en": "Title"},
    "g_col_folder":     {"tr": "Klasör", "en": "Folder"},
    "g_col_last":       {"tr": "Son tarih", "en": "Last activity"},
    "g_col_chat":       {"tr": "Sohbet", "en": "Chat"},
    "g_col_record":     {"tr": "Kayıt", "en": "Record"},
    "g_preview":        {"tr": " Önizleme ", "en": " Preview "},
    "g_pick_hint":      {"tr": "Soldan bir sohbet seçin…", "en": "Select a chat on the left…"},
    "g_first_msg":      {"tr": "İlk mesaj:", "en": "First message:"},
    "g_no_transcript":  {"tr": "(transkript bulunamadı)", "en": "(transcript not found)"},
    "g_move_btn":       {"tr": "Seçili sohbet(leri) taşı  →", "en": "Move selected chat(s)  →"},
    "g_log":            {"tr": " İşlem günlüğü ", "en": " Activity log "},
    "g_banner":         {"tr": "  ⚠  Taşımadan önce Claude masaüstü uygulamasını TAMAMEN kapatın "
                               "(sistem tepsisinden de çıkın). İşlem bitince yeniden açıp 🔄 Yenile deyin.",
                          "en": "  ⚠  Fully close the Claude desktop app before moving "
                               "(quit from the system tray too). When done, reopen it and click 🔄 Refresh."},
    "g_acc_label":      {"tr": "{id}   •   {n} sohbet   •   son {t}",
                          "en": "{id}   •   {n} chats   •   last {t}"},
    "g_count":          {"tr": "{shown}/{total} sohbet", "en": "{shown}/{total} chats"},
    "g_selected":       {"tr": "Seçili: {title}", "en": "Selected: {title}"},
    "g_ready":          {"tr": "Hazır.", "en": "Ready."},
    "g_status_loaded":  {"tr": "{a} hesap • {b} fiziksel depo", "en": "{a} accounts • {b} physical stores"},
    "g_no_store_short": {"tr": "HİÇBİR DEPO BULUNAMADI", "en": "NO STORE FOUND"},
    "g_no_store_status":{"tr": "Depo yok — gerçek Python ile çalıştırın: py csmui.py",
                          "en": "No store — run with real Python: py csmui.py"},
    "g_loaded":         {"tr": "[ok] {nb} depo, {na} hesap yüklendi.",
                          "en": "[ok] loaded {nb} store(s), {na} account(s)."},
    "g_need_two":       {"tr": "[uyarı] Taşıma için 2 hesap gerekli, bulunan: {n}",
                          "en": "[warning] 2 accounts required, found: {n}"},

    # GUI detay alanları / detail fields
    "d_title":          {"tr": "Başlık", "en": "Title"},
    "d_folder":         {"tr": "Klasör", "en": "Folder"},
    "d_last":           {"tr": "Son tarih", "en": "Last"},
    "d_chat":           {"tr": "Sohbet", "en": "Chat"},
    "d_record":         {"tr": "Kayıt", "en": "Record"},
    "d_transcript":     {"tr": "transkript", "en": "transcript"},

    # GUI çakışma penceresi / conflict dialog
    "cd_title":         {"tr": "Çakışma — sohbet hedefte zaten var",
                          "en": "Conflict — chat already exists in target"},
    "cd_header":        {"tr": "⚠  Bu sohbet hedef hesapta zaten var",
                          "en": "⚠  This chat already exists in the target account"},
    "cd_chat_size":     {"tr": "Sohbet boyutu", "en": "Chat size"},
    "cd_rec_size":      {"tr": "Kayıt boyutu", "en": "Record size"},
    "cd_last":          {"tr": "Son tarih", "en": "Last activity"},
    "cd_col_src":       {"tr": "KAYNAK (yeni)", "en": "SOURCE (new)"},
    "cd_col_tgt":       {"tr": "HEDEF (mevcut)", "en": "TARGET (current)"},
    "cd_multi":         {"tr": "(Hedefte {n} eşleşen kayıt var; hepsi değişecek.)",
                          "en": "({n} matching records in target; all will be replaced.)"},
    "cd_apply_all":     {"tr": "Bu kararı kalan {n} çakışmaya da uygula",
                          "en": "Apply this decision to the remaining {n} conflicts"},
    "cd_overwrite":     {"tr": "Üzerine yaz", "en": "Overwrite"},
    "cd_skip":          {"tr": "Atla", "en": "Skip"},

    # GUI mesaj kutuları / message boxes
    "mb_missing_t":     {"tr": "Eksik seçim", "en": "Missing selection"},
    "mb_missing":       {"tr": "Kaynak ve hedef hesap seçilmeli.",
                          "en": "Source and target accounts must be selected."},
    "mb_same_t":        {"tr": "Aynı hesap", "en": "Same account"},
    "mb_same":          {"tr": "Kaynak ve hedef aynı olamaz.", "en": "Source and target cannot be the same."},
    "mb_no_target_t":   {"tr": "Hedef seçilmedi", "en": "No target selected"},
    "mb_no_target":     {"tr": "Lütfen bir hedef hesap seçin.", "en": "Please select a target account."},
    "mb_pick_t":        {"tr": "Sohbet seçin", "en": "Select a chat"},
    "mb_pick":          {"tr": "Taşımak için en az bir sohbet seçin.",
                          "en": "Select at least one chat to move."},
    "mb_confirm_t":     {"tr": "Onay", "en": "Confirm"},
    "mb_confirm":       {"tr": "{n} sohbet\n  {src}  →  {tgt}\nhesabına taşınsın mı?\n\n"
                               "(Claude uygulamasının KAPALI olduğundan emin olun.)",
                          "en": "Move {n} chat(s)\n  {src}  →  {tgt}\nto this account?\n\n"
                               "(Make sure the Claude app is CLOSED.)"},
    "mb_done_t":        {"tr": "Tamamlandı", "en": "Completed"},
    "mb_done":          {"tr": "Kopyalandı       : {c}\nÜzerine yazıldı  : {o}\nAtlandı          : {s}\n\n"
                               "Şimdi Claude masaüstü uygulamasını yeniden açın.",
                          "en": "Copied       : {c}\nOverwritten  : {o}\nSkipped      : {s}\n\n"
                               "Now reopen the Claude desktop app."},
    "g_move_log_hdr":   {"tr": "═══ TAŞIMA: {src} → {tgt} ═══",
                          "en": "═══ MOVE: {src} → {tgt} ═══"},
    "g_move_skipped":   {"tr": "  • atlandı       : {title}", "en": "  • skipped     : {title}"},
    "g_move_over":      {"tr": "  • üzerine yazıldı: {title}  ({n} depo)",
                          "en": "  • overwritten : {title}  ({n} stores)"},
    "g_move_copied":    {"tr": "  • kopyalandı     : {title}  ({n} depo)",
                          "en": "  • copied      : {title}  ({n} stores)"},
    "g_move_done":      {"tr": "─── Bitti.  kopyalandı={c}  üzerine yazıldı={o}  atlandı={s}",
                          "en": "─── Done.  copied={c}  overwritten={o}  skipped={s}"},
    "g_move_status":    {"tr": "Tamamlandı: {c} kopya, {o} üzerine yazıldı, {s} atlandı",
                          "en": "Completed: {c} copied, {o} overwritten, {s} skipped"},

    # --- bozuk oturum temizleme / broken session cleanup ---
    "broken_hdr":       {"tr": "=== BOZUK OTURUM TESPİTİ ({name}) ===",
                          "en": "=== BROKEN SESSION SCAN ({name}) ==="},
    "broken_summary":   {"tr": "Toplam kayıt: {total}  •  Transkripti eksik (bozuk): {broken}",
                          "en": "Total records: {total}  •  Missing transcript (broken): {broken}"},
    "broken_none":      {"tr": "Temiz. Bozuk kayıt yok.", "en": "Clean. No broken records."},
    "broken_line":      {"tr": "  [{i}] {acct} · {title}\n       cwd: {cwd}  son: {t}",
                          "en": "  [{i}] {acct} · {title}\n       cwd: {cwd}  last: {t}"},
    "broken_ask":       {"tr": "Bunları TAMAMEN silmek ister misin? Geri alınamaz (e/h): ",
                          "en": "Delete these permanently? Cannot be undone (y/n): "},
    "broken_done":      {"tr": "Temizlendi. Silinen dosya: {n}", "en": "Cleanup done. Files removed: {n}"},
    "broken_menu_hint": {"tr": "İpucu: bozuk kayıtları temizlemek için `py csm.py --cleanup` çalıştır.",
                          "en": "Hint: run `py csm.py --cleanup` to remove broken records."},
    "notr_warn":        {"tr": "[!] Uyarı: bu oturumun transkripti diskte yok. Hedef hesapta da 'Session not found on disk' görünecek. Yine de kopyalansın mı? (e/h): ",
                          "en": "[!] Warning: this session's transcript is missing on disk. The target will also show 'Session not found on disk'. Copy anyway? (y/n): "},

    # --- GUI: broken cleanup ---
    "g_cleanup_btn":    {"tr": "🧹 Bozuk oturumları temizle",
                          "en": "🧹 Clean broken sessions"},
    "g_cleanup_none":   {"tr": "Bu tipte bozuk kayıt yok.",
                          "en": "No broken records for this type."},
    "g_cleanup_title":  {"tr": "Bozuk oturum temizliği",
                          "en": "Broken session cleanup"},
    "g_cleanup_confirm":{"tr": "{n} bozuk kayıt bulundu (transkript diskte yok). Hepsi silinsin mi?\n\nBu işlem geri alınamaz.",
                          "en": "{n} broken records found (transcript missing on disk). Delete all?\n\nThis cannot be undone."},
    "g_cleanup_done":   {"tr": "Temizlendi: {n} dosya silindi.",
                          "en": "Done: {n} file(s) removed."},

    # --- Claude Code ⇄ Codex köprüsü / bridge (CLI) ---
    "br_dir_c2x":       {"tr": "Claude Code → Codex", "en": "Claude Code → Codex"},
    "br_dir_x2c":       {"tr": "Codex → Claude Code", "en": "Codex → Claude Code"},
    "br_choose_dir":    {"tr": "=== DÖNÜŞÜM YÖNÜNÜ SEÇ ===", "en": "=== SELECT CONVERSION DIRECTION ==="},
    "br_opt_c2x":       {"tr": "  [1] Claude Code → Codex", "en": "  [1] Claude Code → Codex"},
    "br_opt_x2c":       {"tr": "  [2] Codex → Claude Code", "en": "  [2] Codex → Claude Code"},
    "br_prompt_dir":    {"tr": "Yön no (1/2): ", "en": "Direction no (1/2): "},
    "br_close_apps":    {"tr": "UYARI: Devam etmeden önce Claude ve Codex masaüstü uygulamalarını TAMAMEN kapat.",
                          "en": "WARNING: Fully close the Claude and Codex desktop apps before continuing."},
    "br_about":         {"tr": "Kaynak oturuma dokunulmaz; hedefte YENİ bir oturum oluşturulur. Araç çağrıları\n"
                               "ve sonuçları metin olarak aktarılır (iki tarafın araçları farklıdır).",
                          "en": "The source session is not modified; a NEW session is created on the target.\n"
                               "Tool calls and results are carried over as text (the tools differ per side)."},
    "br_no_sessions":   {"tr": "{side} oturumu bulunamadı. Aranan klasör: {p}",
                          "en": "No {side} sessions found. Looked in: {p}"},
    "br_list_hdr":      {"tr": "=== {side} OTURUMLARI ({n}) ===", "en": "=== {side} SESSIONS ({n}) ==="},
    "br_filter_q":      {"tr": "Filtre (başlık/klasör, boş = hepsi): ",
                          "en": "Filter (title/folder, empty = all): "},
    "br_line":          {"tr": "  [{i}] {title}\n       klasör: {cwd}   son: {t}   boyut: {size}",
                          "en": "  [{i}] {title}\n       folder: {cwd}   last: {t}   size: {size}"},
    "br_more":          {"tr": "  … +{n} oturum daha (daraltmak için filtre kullan)",
                          "en": "  … +{n} more sessions (use a filter to narrow down)"},
    "br_prompt_pick":   {"tr": "Dönüştürülecek oturum no(ları) (virgülle birden fazla): ",
                          "en": "Session no(s) to convert (comma-separated for multiple): "},
    "br_register_codex_q": {"tr": "Codex uygulamasının sohbet listesine de eklensin mi? (e/h): ",
                             "en": "Also add to the Codex app's chat list? (y/n): "},
    "br_account_hdr":   {"tr": "=== CLAUDE MASAÜSTÜ HESABI (isteğe bağlı) ===",
                          "en": "=== CLAUDE DESKTOP ACCOUNT (optional) ==="},
    "br_account_none":  {"tr": "  [0] Kaydetme — yalnızca transkript (claude --resume ile açılır)",
                          "en": "  [0] Don't register — transcript only (open with claude --resume)"},
    "br_prompt_account":{"tr": "Hesap no (0 = kaydetme): ", "en": "Account no (0 = don't register): "},
    "br_no_account_warn": {"tr": "Claude hesabı seçilmedi: oturum Claude MASAÜSTÜ uygulamasında GÖRÜNMEZ,\n"
                                 "yalnızca terminalde `claude --resume <kimlik>` ile açılır.",
                            "en": "No Claude account selected: the session will NOT appear in the Claude DESKTOP app,\n"
                                 "it can only be opened in a terminal with `claude --resume <id>`."},
    "br_no_codex_reg_warn": {"tr": "Codex listesine eklenmeyecek: oturum Codex MASAÜSTÜ uygulamasında GÖRÜNMEZ,\n"
                                   "yalnızca terminalde `codex resume <kimlik>` ile açılır.",
                              "en": "Not adding to the Codex list: the session will NOT appear in the Codex DESKTOP app,\n"
                                   "it can only be opened in a terminal with `codex resume <id>`."},
    "br_summary":       {"tr": "=== ÖZET: {dir} — {n} oturum ===", "en": "=== SUMMARY: {dir} — {n} session(s) ==="},
    "br_ok":            {"tr": "[ok] {title}\n        -> {p}\n        kimlik: {id}  ({turns} tur, {items} mesaj)",
                          "en": "[ok] {title}\n        -> {p}\n        id: {id}  ({turns} turns, {items} messages)"},
    "br_reg_codex_yes": {"tr": "        Codex uygulamasının listesine eklendi.",
                          "en": "        Added to the Codex app's list."},
    "br_reg_codex_no":  {"tr": "        Codex listesine eklenmedi — `codex resume {id}` ile açılabilir.",
                          "en": "        Not added to the Codex list — open with `codex resume {id}`."},
    "br_reg_claude":    {"tr": "        Claude hesabına kaydedildi ({n} depo).",
                          "en": "        Registered to the Claude account ({n} store(s))."},
    "br_fail":          {"tr": "[!] {title}: {e}", "en": "[!] {title}: {e}"},
    "br_done":          {"tr": "Bitti. dönüştürüldü={c}  hata={f}", "en": "Done. converted={c}  failed={f}"},
    "br_hint_codex":    {"tr": "Codex uygulamasını yeniden aç (veya terminalde: codex resume <kimlik>).",
                          "en": "Reopen the Codex app (or in a terminal: codex resume <id>)."},
    "br_hint_claude":   {"tr": "Claude uygulamasını yeniden aç (veya proje klasöründe: claude --resume <kimlik>).",
                          "en": "Reopen the Claude app (or in the project folder: claude --resume <id>)."},

    # --- Claude Code ⇄ Codex köprüsü / bridge (GUI) ---
    "g_br_dir":         {"tr": "Yön:", "en": "Direction:"},
    "g_br_info":        {"tr": "Kaynak oturuma dokunulmaz, hedefte yeni oturum oluşturulur. Araç çağrıları metin "
                               "olarak aktarılır. İşlemden önce Claude ve Codex uygulamalarını kapatın.",
                          "en": "The source is not modified; a new session is created on the target. Tool calls are "
                               "carried over as text. Close the Claude and Codex apps before converting."},
    "g_br_paths":       {"tr": "Claude: {c}   |   Codex: {x}", "en": "Claude: {c}   |   Codex: {x}"},
    "g_col_size":       {"tr": "Boyut", "en": "Size"},
    "g_col_account":    {"tr": "Hesap", "en": "Account"},
    "g_br_reg_codex":   {"tr": "Codex uygulamasının listesine de ekle",
                          "en": "Also add to the Codex app's list"},
    "g_br_reg_claude":  {"tr": "Claude hesabına kaydet:", "en": "Register to Claude account:"},
    "g_br_reg_none":    {"tr": "— Kaydetme (yalnızca transkript) —", "en": "— Don't register (transcript only) —"},
    "g_br_convert_btn": {"tr": "Seçili oturum(ları) dönüştür  →", "en": "Convert selected session(s)  →"},
    "g_br_loaded":      {"tr": "[ok] {nc} Claude Code, {nx} Codex oturumu bulundu.",
                          "en": "[ok] found {nc} Claude Code and {nx} Codex sessions."},
    "g_br_log_hdr":     {"tr": "═══ DÖNÜŞÜM: {dir} ═══", "en": "═══ CONVERT: {dir} ═══"},
    "g_br_ok":          {"tr": "  • {title}  →  {id}  ({turns} tur)", "en": "  • {title}  →  {id}  ({turns} turns)"},
    "g_br_fail":        {"tr": "  • HATA {title}: {e}", "en": "  • FAILED {title}: {e}"},
    "g_br_done":        {"tr": "─── Bitti.  dönüştürüldü={c}  hata={f}", "en": "─── Done.  converted={c}  failed={f}"},
    "g_br_status":      {"tr": "Tamamlandı: {c} dönüştürüldü, {f} hata", "en": "Completed: {c} converted, {f} failed"},
    "mb_br_confirm":    {"tr": "{n} oturum dönüştürülsün mü?\n  {dir}\n\n"
                               "(Claude ve Codex uygulamalarının KAPALI olduğundan emin olun.)",
                          "en": "Convert {n} session(s)?\n  {dir}\n\n"
                               "(Make sure the Claude and Codex apps are CLOSED.)"},
    "mb_br_warn_t":     {"tr": "Masaüstü uygulamasında görünmeyecek", "en": "Won't appear in the desktop app"},
    "mb_br_continue":   {"tr": "Yine de devam edilsin mi?", "en": "Continue anyway?"},
    "mb_br_pick":       {"tr": "Dönüştürmek için en az bir oturum seçin.",
                          "en": "Select at least one session to convert."},
    "mb_br_done":       {"tr": "Dönüştürüldü : {c}\nHata         : {f}\n\nİlgili uygulamayı yeniden açın.",
                          "en": "Converted : {c}\nFailed    : {f}\n\nReopen the target app."},

    # --- yedek / aktarma paketi (CLI) ---
    "pk_choose_mode":   {"tr": "=== YEDEK / AKTARMA ===", "en": "=== BACKUP / TRANSFER ==="},
    "pk_opt_export":    {"tr": "  [1] Dosyaya aktar (yedek)", "en": "  [1] Export to a file (backup)"},
    "pk_opt_import":    {"tr": "  [2] Dosyadan geri yükle", "en": "  [2] Restore from a file"},
    "pk_prompt_mode":   {"tr": "Seçim (1/2): ", "en": "Choice (1/2): "},
    "pk_about":         {"tr": "Oturumun her şeyi pakete girer: kayıt, transkript, hafıza dosyaları,\n"
                               "scratchpad, araç çıktıları, Cowork yan klasörü, Codex görselleri.",
                          "en": "Everything belonging to a session goes into the bundle: record, transcript,\n"
                               "memory files, scratchpad, tool outputs, Cowork folder, Codex images."},
    "pk_no_sessions":   {"tr": "Paketlenecek oturum bulunamadı.", "en": "No sessions found to bundle."},
    "pk_list_hdr":      {"tr": "=== OTURUMLAR ({n}) ===", "en": "=== SESSIONS ({n}) ==="},
    "pk_line":          {"tr": "  [{i}] {kind} · {title}{acc}\n       klasör: {cwd}   son: {t}   boyut: {size}",
                          "en": "  [{i}] {kind} · {title}{acc}\n       folder: {cwd}   last: {t}   size: {size}"},
    "pk_prompt_pick":   {"tr": "Paketlenecek oturum no(ları) (virgülle birden fazla): ",
                          "en": "Session no(s) to bundle (comma-separated for multiple): "},
    "pk_all_q":         {"tr": "Hafıza, scratchpad ve araç çıktıları da eklensin mi? (e/h): ",
                          "en": "Include memory, scratchpad and tool outputs too? (y/n): "},
    "pk_out_q":         {"tr": "Paket dosyası [{d}]: ", "en": "Bundle file [{d}]: "},
    "pk_exporting":     {"tr": "Paketleniyor… ({size} civarı)", "en": "Bundling… (about {size})"},
    "pk_export_done":   {"tr": "Paket hazır: {p}  ({size})", "en": "Bundle ready: {p}  ({size})"},
    "pk_export_hint":   {"tr": "Bu dosyayı diğer bilgisayara kopyalayıp `py csm.py --import <dosya>` ile yükle.",
                          "en": "Copy this file to the other computer and run `py csm.py --import <file>`."},
    "pk_bundle_q":      {"tr": "Paket dosyası (.csmpack): ", "en": "Bundle file (.csmpack): "},
    "pk_bundle_bad":    {"tr": "Paket okunamadı: {e}", "en": "Could not read the bundle: {e}"},
    "pk_bundle_info":   {"tr": "Paket: {p}\n  kaynak: {user}@{host} ({platform})  •  {n} oturum  •  {t}",
                          "en": "Bundle: {p}\n  source: {user}@{host} ({platform})  •  {n} sessions  •  {t}"},
    "pk_prompt_pick_in": {"tr": "Geri yüklenecek oturum no(ları) (boş = hepsi): ",
                           "en": "Session no(s) to restore (empty = all): "},
    "pk_map_hdr":       {"tr": "=== KLASÖR EŞLEMESİ (proje klasörü bu bilgisayarda farklıysa) ===",
                          "en": "=== FOLDER MAPPING (if the project folder differs on this computer) ==="},
    "pk_map_q":         {"tr": "  {src}\n  hedef [{dst}]: ", "en": "  {src}\n  target [{dst}]: "},
    "pk_mem_q":         {"tr": "Aynı adlı hafıza dosyalarının üzerine yazılsın mı? (e/h): ",
                          "en": "Overwrite memory files that already exist? (y/n): "},
    "pk_reg_codex_q":   {"tr": "Codex oturumları Codex uygulamasının listesine eklensin mi? (e/h): ",
                          "en": "Add Codex sessions to the Codex app's list? (y/n): "},
    "pk_conflict_q":    {"tr": "    '{title}' hedef hesapta zaten var. Üzerine yazılsın mı? (e/h): ",
                          "en": "    '{title}' already exists in the target account. Overwrite? (y/n): "},
    "pk_restored":      {"tr": "[ok] {title}", "en": "[ok] {title}"},
    "pk_path":          {"tr": "        -> {p}", "en": "        -> {p}"},
    "pk_mem_skipped":   {"tr": "        {n} hafıza dosyası atlandı (aynı adlı dosya vardı)",
                          "en": "        {n} memory file(s) skipped (same name already existed)"},
    "pk_skipped":       {"tr": "[atlandı] {title}", "en": "[skipped] {title}"},
    "pk_failed":        {"tr": "[!] {title}: {e}", "en": "[!] {title}: {e}"},
    "pk_done":          {"tr": "Bitti. geri yüklendi={c}  atlandı={s}  hata={f}",
                          "en": "Done. restored={c}  skipped={s}  failed={f}"},
    "pk_hint":          {"tr": "Claude / Codex uygulamasını yeniden aç.", "en": "Reopen the Claude / Codex app."},

    # --- yedek / aktarma paketi (GUI) ---
    "g_pk_mode":        {"tr": "İşlem:", "en": "Action:"},
    "g_pk_mode_export": {"tr": "Dosyaya aktar (yedek)", "en": "Export to a file (backup)"},
    "g_pk_mode_import": {"tr": "Dosyadan geri yükle", "en": "Restore from a file"},
    "g_pk_info":        {"tr": "Oturumun her şeyi tek dosyaya girer: kayıt, transkript, hafıza, scratchpad, "
                               "araç çıktıları, Cowork klasörü, Codex görselleri. Geri yüklerken yollar bu "
                               "bilgisayara uyarlanır.",
                          "en": "Everything goes into one file: record, transcript, memory, scratchpad, tool "
                               "outputs, Cowork folder, Codex images. On restore, paths are adapted to this "
                               "computer."},
    "g_col_kind":       {"tr": "Tip", "en": "Type"},
    "g_pk_parts":       {"tr": " Pakete eklenecekler ", "en": " Include in the bundle "},
    "g_pk_part_memory": {"tr": "Hafıza dosyaları (memory/)", "en": "Memory files (memory/)"},
    "g_pk_part_scratch": {"tr": "Scratchpad ve görevler", "en": "Scratchpad and tasks"},
    "g_pk_part_extras": {"tr": "Araç çıktıları / alt ajanlar", "en": "Tool outputs / subagents"},
    "g_pk_size":        {"tr": "Seçili: {n} oturum  •  yaklaşık {size}",
                          "en": "Selected: {n} session(s)  •  about {size}"},
    "g_pk_save_btn":    {"tr": "Dosyaya kaydet…  →", "en": "Save to file…  →"},
    "g_pk_pick_btn":    {"tr": "📂 Paket seç…", "en": "📂 Choose bundle…"},
    "g_pk_file":        {"tr": "Paket: {p}", "en": "Bundle: {p}"},
    "g_pk_nofile":      {"tr": "Paket seçilmedi.", "en": "No bundle selected."},
    "g_pk_source":      {"tr": "Kaynak: {user}@{host} ({platform}) • {t}",
                          "en": "Source: {user}@{host} ({platform}) • {t}"},
    "g_pk_account":     {"tr": "Claude hesabı:", "en": "Claude account:"},
    "g_pk_reg_codex":   {"tr": "Codex oturumlarını Codex listesine ekle",
                          "en": "Add Codex sessions to the Codex list"},
    "g_pk_overwrite_mem": {"tr": "Hafıza dosyalarının üzerine yaz", "en": "Overwrite memory files"},
    "g_pk_map":         {"tr": " Klasör eşlemesi ", "en": " Folder mapping "},
    "g_pk_map_src":     {"tr": "Paketteki klasör", "en": "Folder in the bundle"},
    "g_pk_map_dst":     {"tr": "Bu bilgisayarda", "en": "On this computer"},
    "g_pk_map_btn":     {"tr": "Klasörü değiştir…", "en": "Change folder…"},
    "g_pk_restore_btn": {"tr": "Seçilileri geri yükle  →", "en": "Restore selected  →"},
    "g_pk_loaded":      {"tr": "[ok] {n} oturum paketlenebilir.", "en": "[ok] {n} session(s) available."},
    "g_pk_bundle_loaded": {"tr": "[ok] Paket okundu: {n} oturum.", "en": "[ok] Bundle read: {n} session(s)."},
    "g_pk_log_export":  {"tr": "═══ PAKETLEME ═══", "en": "═══ EXPORT ═══"},
    "g_pk_log_import":  {"tr": "═══ GERİ YÜKLEME ═══", "en": "═══ RESTORE ═══"},
    "g_pk_status_export": {"tr": "Paket hazır: {p}", "en": "Bundle ready: {p}"},
    "g_pk_status_import": {"tr": "Geri yüklendi: {c}, atlandı: {s}, hata: {f}",
                            "en": "Restored: {c}, skipped: {s}, failed: {f}"},
    "mb_pk_pick":       {"tr": "En az bir oturum seçin.", "en": "Select at least one session."},
    "mb_pk_nofile":     {"tr": "Önce bir paket dosyası seçin.", "en": "Choose a bundle file first."},
    "mb_pk_done_export": {"tr": "Paket hazır:\n{p}\n\nBoyut: {size}\nOturum: {n}",
                           "en": "Bundle ready:\n{p}\n\nSize: {size}\nSessions: {n}"},
    "mb_pk_done_import": {"tr": "Geri yüklendi : {c}\nAtlandı       : {s}\nHata          : {f}\n\n"
                                "Claude / Codex uygulamasını yeniden açın.",
                           "en": "Restored : {c}\nSkipped  : {s}\nFailed   : {f}\n\n"
                                "Reopen the Claude / Codex app."},
    "mb_pk_noaccount":  {"tr": "Claude hesabı seçilmedi: Claude oturumları masaüstü uygulamasında görünmez,\n"
                               "yalnızca dosyaları geri yüklenir.\n\nYine de devam edilsin mi?",
                          "en": "No Claude account selected: Claude sessions won't appear in the desktop app,\n"
                               "only their files are restored.\n\nContinue anyway?"},
}


def detect_lang(default="tr") -> str:
    """CLI argümanı / ortam değişkeninden dil tespiti."""
    import sys
    argv = sys.argv[1:]
    if "--en" in argv:
        return "en"
    if "--tr" in argv:
        return "tr"
    if "--lang" in argv:
        i = argv.index("--lang")
        if i + 1 < len(argv) and argv[i + 1] in LANGS:
            return argv[i + 1]
    env = (os.environ.get("CSM_LANG") or "").lower()
    if env in LANGS:
        return env
    return default


class Translator:
    def __init__(self, lang="tr"):
        self.lang = lang if lang in LANGS else "tr"

    def set_lang(self, lang):
        if lang in LANGS:
            self.lang = lang

    def t(self, key, **kw):
        entry = T.get(key)
        if not entry:
            return key
        s = entry.get(self.lang) or entry.get("tr") or key
        if kw:
            try:
                return s.format(**kw)
            except Exception:
                return s
        return s
