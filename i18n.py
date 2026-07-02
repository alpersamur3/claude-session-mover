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
    "prompt_type":      {"tr": "Tip no (1/2): ", "en": "Type no (1/2): "},
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
