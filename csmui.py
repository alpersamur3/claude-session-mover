#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude Sohbet Taşıyıcı — Tkinter Arayüzü (csmui.py)  /  Claude Chat Mover — GUI
==============================================================================
csm.py'nin grafik arayüzlü sürümü. İki sekme:

  • Claude Code  → masaüstü sohbetleri
  • Cowork       → agent oturumları (kayıt + yan klasörleriyle birlikte)
  • Claude ⇄ Codex → Claude Code ve Codex oturumları arasında dönüştürme (csbridge.py)

Kaynak/hedef hesaplar e-posta ile gösterilir (çözülemezse kısa UUID), son
aktiviteye göre sıralanır; hedef bilinçli seçilir (otomatik seçilmez).
Sağ üstten TR/EN dil seçimi. Ayrıntı için README.md.

Çalıştırma / Run:
    py csmui.py               (Türkçe)
    py csmui.py --en          (English)
    py csmui.py --demo        (repo içindeki sample-data ile dene / try bundled sample data)

ÖNEMLİ: Çalıştırmadan önce Claude masaüstü uygulamasını TAMAMEN kapatın.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from i18n import Translator, detect_lang  # noqa: E402
import csm  # çekirdek mantık: depo bulma, hesap yükleme, kopyalama  # noqa: E402
from csm import (  # noqa: E402
    existing_bases, build_transcript_index, build_email_index, load_accounts,
    candidate_bases, human_size, fmt_time, session_preview, account_who,
    target_rel_path, find_conflicts, perform_copy, perform_remove, STORE_NAMES,
    find_broken_sessions, perform_broken_cleanup, session_is_broken,
)
import csbridge  # Claude Code ⇄ Codex dönüştürme  # noqa: E402
import cspack  # yedek / aktarma paketi  # noqa: E402

# ----------------------------------------------------------------------------
# ARAYÜZ / GUI
# ----------------------------------------------------------------------------

CLR_BANNER = "#b45309"
CLR_BG = "#f3f4f6"
CLR_ACCENT = "#2563eb"
CLR_ACCENT_HOVER = "#1d4ed8"
CLR_OK = "#15803d"
CLR_MUTED = "#6b7280"
CLR_STRIPE = "#eef2f7"
CLR_DANGER = "#b91c1c"

SESSION_KINDS = ("code", "cowork")


def run_gui():
    import tkinter as tk
    from tkinter import ttk, messagebox, scrolledtext, filedialog

    tr = Translator(detect_lang())

    class ConflictDialog(tk.Toplevel):
        def __init__(self, parent, src, conflicts, remaining):
            super().__init__(parent)
            self.title(tr.t("cd_title"))
            self.configure(bg="white")
            self.resizable(False, False)
            self.result = ("skip", False)
            self.transient(parent)

            frm = ttk.Frame(self, padding=16, style="Card.TFrame")
            frm.pack(fill="both", expand=True)
            ttk.Label(frm, text=tr.t("cd_header"), style="DlgTitle.TLabel")\
                .grid(row=0, column=0, columnspan=2, sticky="w")
            ttk.Label(frm, text=src["title"], style="DlgSub.TLabel")\
                .grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 12))

            tv = ttk.Treeview(frm, columns=("k", "h"), show="tree headings", height=4)
            tv.heading("#0", text="")
            tv.heading("k", text=tr.t("cd_col_src"))
            tv.heading("h", text=tr.t("cd_col_tgt"))
            tv.column("#0", width=140, anchor="w")
            tv.column("k", width=190, anchor="center")
            tv.column("h", width=190, anchor="center")
            c0 = conflicts[0]
            rows = [
                (tr.t("cd_chat_size"), human_size(src["tr_size"]), human_size(c0["tr_size"])),
                (tr.t("cd_rec_size"), human_size(src["rec_size"]), human_size(c0["rec_size"])),
                (tr.t("cd_last"), fmt_time(src["last"]), fmt_time(c0["last"])),
                ("cliSessionId", (src["cli"][:8] + "…") if src["cli"] else "-",
                 (c0["cli"][:8] + "…") if c0["cli"] else "-"),
            ]
            for label, k, h in rows:
                tv.insert("", "end", text=label, values=(k, h))
            tv.grid(row=2, column=0, columnspan=2, sticky="we")

            if len(conflicts) > 1:
                ttk.Label(frm, text=tr.t("cd_multi", n=len(conflicts)), style="Muted.TLabel")\
                    .grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))

            self.apply_all = tk.BooleanVar(value=False)
            if remaining > 0:
                ttk.Checkbutton(frm, text=tr.t("cd_apply_all", n=remaining),
                                variable=self.apply_all)\
                    .grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 4))

            btns = ttk.Frame(frm, style="Card.TFrame")
            btns.grid(row=5, column=0, columnspan=2, sticky="e", pady=(14, 0))
            ttk.Button(btns, text=tr.t("cd_skip"), command=self._skip).pack(side="right", padx=4)
            ttk.Button(btns, text=tr.t("cd_overwrite"), style="Accent.TButton",
                       command=self._overwrite).pack(side="right", padx=4)

            self.bind("<Escape>", lambda e: self._skip())
            self.protocol("WM_DELETE_WINDOW", self._skip)
            self.grab_set()
            self.update_idletasks()
            self._center(parent)
            self.wait_window()

        def _center(self, parent):
            try:
                px, py = parent.winfo_rootx(), parent.winfo_rooty()
                pw, ph = parent.winfo_width(), parent.winfo_height()
                w, h = self.winfo_width(), self.winfo_height()
                self.geometry(f"+{px + (pw - w)//2}+{py + (ph - h)//3}")
            except Exception:
                pass

        def _overwrite(self):
            self.result = ("overwrite", self.apply_all.get())
            self.destroy()

        def _skip(self):
            self.result = ("skip", self.apply_all.get())
            self.destroy()

    class SessionPane(ttk.Frame):
        """Tek bir oturum tipi (code / cowork) için tam kaynak→hedef paneli."""

        HEADINGS = (("title", "g_col_title"), ("cwd", "g_col_folder"),
                    ("last", "g_col_last"), ("tr", "g_col_chat"), ("rec", "g_col_record"))

        def __init__(self, master, app, kind):
            super().__init__(master, padding=(10, 8))
            self.app = app
            self.tr = app.tr
            self.kind = kind
            self.bases = []
            self.accounts = []       # tüm hesaplar (son aktiviteye göre sıralı)
            self.src_accounts = []   # yalnızca sohbeti olan hesaplar (kaynak)
            self.target_accounts = []
            self._build()

        # ---- arayüz ----
        def _build(self):
            self.stores_var = tk.StringVar(value="…")
            ttk.Label(self, textvariable=self.stores_var, style="Store.TLabel")\
                .pack(fill="x", pady=(0, 6))

            paned = ttk.Panedwindow(self, orient="horizontal")
            paned.pack(fill="both", expand=True)

            left = ttk.Frame(paned, padding=(0, 0, 6, 0))
            paned.add(left, weight=3)

            srow = ttk.Frame(left)
            srow.pack(fill="x", pady=(0, 6))
            self.lbl_source = ttk.Label(srow, style="Bold.TLabel")
            self.lbl_source.pack(side="left")
            self.source_combo = ttk.Combobox(srow, state="readonly", width=44)
            self.source_combo.pack(side="left", padx=6, fill="x", expand=True)
            self.source_combo.bind("<<ComboboxSelected>>", lambda e: self.on_source_change())

            frow = ttk.Frame(left)
            frow.pack(fill="x", pady=(0, 6))
            self.lbl_filter = ttk.Label(frow)
            self.lbl_filter.pack(side="left")
            self.filter_var = tk.StringVar()
            fe = ttk.Entry(frow, textvariable=self.filter_var)
            fe.pack(side="left", fill="x", expand=True, padx=6)
            fe.bind("<KeyRelease>", lambda e: self.populate_sessions())
            self.count_var = tk.StringVar(value="")
            ttk.Label(frow, textvariable=self.count_var, style="Muted.TLabel").pack(side="right")

            tw = ttk.Frame(left)
            tw.pack(fill="both", expand=True)
            self.tree = ttk.Treeview(tw, columns=[c for c, _ in self.HEADINGS],
                                     show="headings", selectmode="extended")
            widths = {"title": (240, "w", True), "cwd": (230, "w", True),
                      "last": (120, "center", False), "tr": (78, "e", False), "rec": (78, "e", False)}
            for col, _ in self.HEADINGS:
                w, anc, stretch = widths[col]
                self.tree.column(col, width=w, anchor=anc, stretch=stretch)
            self.tree.tag_configure("odd", background=CLR_STRIPE)
            self.tree.tag_configure("notr", foreground=CLR_DANGER)
            vsb = ttk.Scrollbar(tw, orient="vertical", command=self.tree.yview)
            self.tree.configure(yscrollcommand=vsb.set)
            self.tree.pack(side="left", fill="both", expand=True)
            vsb.pack(side="right", fill="y")
            self.tree.bind("<<TreeviewSelect>>", self.on_select)

            self.preview_frame = ttk.Labelframe(paned, padding=10)
            paned.add(self.preview_frame, weight=2)
            self.detail_var = tk.StringVar(value="")
            ttk.Label(self.preview_frame, textvariable=self.detail_var, justify="left",
                      anchor="nw", wraplength=380, font=("Segoe UI", 9)).pack(fill="x")
            ttk.Separator(self.preview_frame).pack(fill="x", pady=8)
            self.lbl_firstmsg = ttk.Label(self.preview_frame, style="Muted.TLabel")
            self.lbl_firstmsg.pack(anchor="w")
            self.preview = scrolledtext.ScrolledText(self.preview_frame, height=12, wrap="word",
                                                     font=("Segoe UI", 9), relief="flat",
                                                     background="white")
            self.preview.pack(fill="both", expand=True, pady=(4, 0))
            self.preview.configure(state="disabled")

            trow = ttk.Frame(self, padding=(0, 6))
            trow.pack(fill="x")
            self.lbl_target = ttk.Label(trow, style="Bold.TLabel")
            self.lbl_target.pack(side="left")
            self.target_combo = ttk.Combobox(trow, state="readonly", width=44)
            self.target_combo.pack(side="left", padx=6)
            self.move_btn = ttk.Button(trow, style="Accent.TButton", command=self.on_move)
            self.move_btn.pack(side="left", padx=12)
            self.cleanup_btn = ttk.Button(trow, command=self.on_cleanup_broken)
            self.cleanup_btn.pack(side="right", padx=4)

            self.log_frame = ttk.Labelframe(self, padding=6)
            self.log_frame.pack(fill="both", expand=False, pady=(4, 0))
            self.log = scrolledtext.ScrolledText(self.log_frame, height=6, wrap="word",
                                                 font=("Consolas", 9), relief="flat")
            self.log.pack(fill="both", expand=True)
            self.log.tag_config("ok", foreground=CLR_OK)
            self.log.tag_config("warn", foreground=CLR_BANNER)
            self.log.tag_config("err", foreground=CLR_DANGER)
            self.log.configure(state="disabled")

        # ---- i18n ----
        def acc_label(self, acc):
            return self.tr.t("g_acc_label", id=account_who(acc),
                             n=len(acc["sessions"]), t=fmt_time(acc["last"]))

        def retranslate(self):
            self.lbl_source.config(text=self.tr.t("g_source"))
            self.lbl_filter.config(text=self.tr.t("g_filter"))
            self.preview_frame.config(text=self.tr.t("g_preview"))
            self.lbl_firstmsg.config(text=self.tr.t("g_first_msg"))
            self.lbl_target.config(text=self.tr.t("g_target"))
            self.move_btn.config(text=self.tr.t("g_move_btn"))
            self.cleanup_btn.config(text=self.tr.t("g_cleanup_btn"))
            self.log_frame.config(text=self.tr.t("g_log"))
            for col, key in self.HEADINGS:
                self.tree.heading(col, text=self.tr.t(key))
            # combo etiketlerini yeni dile göre tazele
            self._refresh_source_values(keep_selection=True)
            self.refresh_target()
            self.populate_sessions()

        # ---- yardımcılar ----
        def logln(self, msg, tag=None):
            self.log.configure(state="normal")
            self.log.insert("end", msg + "\n", (tag,) if tag else ())
            self.log.see("end")
            self.log.configure(state="disabled")

        def set_preview(self, text):
            self.preview.configure(state="normal")
            self.preview.delete("1.0", "end")
            self.preview.insert("1.0", text or self.tr.t("g_no_transcript"))
            self.preview.configure(state="disabled")

        def current_source(self):
            i = self.source_combo.current()
            return self.src_accounts[i] if 0 <= i < len(self.src_accounts) else None

        def current_target(self):
            # 0. eleman placeholder; gerçek hesaplar 1'den başlar.
            i = self.target_combo.current()
            if i <= 0:
                return None
            j = i - 1
            return self.target_accounts[j] if 0 <= j < len(self.target_accounts) else None

        def _refresh_source_values(self, keep_selection=False):
            prev = self.current_source() if keep_selection else None
            self.src_accounts = [a for a in self.accounts if a["sessions"]]
            self.source_combo["values"] = [self.acc_label(a) for a in self.src_accounts]
            if not self.src_accounts:
                self.source_combo.set("")
                return
            idx = 0
            if prev:
                for j, a in enumerate(self.src_accounts):
                    if a["id"] == prev["id"]:
                        idx = j
                        break
            self.source_combo.current(idx)

        # ---- eylemler ----
        def reload(self, email_map, tindex):
            self.bases = existing_bases(self.kind)
            if not self.bases:
                self.stores_var.set(self.tr.t("g_no_store_short"))
                self.logln("[!] " + self.tr.t("no_store"), "err")
                for c in candidate_bases(self.kind):
                    self.logln(f"    [{'OK' if c.exists() else '--'}] {c}")
                self.accounts, self.src_accounts, self.target_accounts = [], [], []
                self.source_combo["values"] = []
                self.target_combo["values"] = []
                self.move_btn.state(["disabled"])
                return
            self.stores_var.set("   |   ".join(str(b) for b in self.bases))
            self.accounts = load_accounts(self.bases[0], tindex, self.kind, email_map)
            self._refresh_source_values(keep_selection=True)
            self.refresh_target()
            if len(self.accounts) < 2:
                self.logln(self.tr.t("g_need_two", n=len(self.accounts)), "warn")
                self.move_btn.state(["disabled"])
            else:
                self.move_btn.state(["!disabled"])
            self.populate_sessions()
            self.logln(self.tr.t("g_loaded", nb=len(self.bases), na=len(self.accounts)), "ok")

        def refresh_target(self):
            src = self.current_source()
            self.target_accounts = [a for a in self.accounts if not src or a["id"] != src["id"]]
            ph = self.tr.t("g_target_ph")
            self.target_combo["values"] = [ph] + [self.acc_label(a) for a in self.target_accounts]
            # Hedef bilinçli seçilsin: her zaman placeholder'da başlat.
            self.target_combo.current(0)

        def on_source_change(self):
            self.refresh_target()
            self.populate_sessions()

        def populate_sessions(self):
            self.tree.delete(*self.tree.get_children())
            acc = self.current_source()
            if not acc:
                self.count_var.set("")
                self.set_preview("")
                self.detail_var.set(self.tr.t("g_pick_hint"))
                return
            flt = self.filter_var.get().strip().lower()
            shown = 0
            for i, s in enumerate(acc["sessions"]):
                if flt and flt not in s["title"].lower() and flt not in s["cwd"].lower():
                    continue
                vals = (s["title"], s["cwd"], fmt_time(s["last"]),
                        human_size(s["tr_size"]), human_size(s["rec_size"]))
                tags = ["odd"] if shown % 2 else []
                if not s["transcript"]:
                    tags.append("notr")
                self.tree.insert("", "end", iid=str(i), values=vals, tags=tuple(tags))
                shown += 1
            self.count_var.set(self.tr.t("g_count", shown=shown, total=len(acc["sessions"])))
            self.set_preview("")
            self.detail_var.set(self.tr.t("g_pick_hint"))

        def on_select(self, _evt=None):
            acc = self.current_source()
            iid = self.tree.focus()
            if not acc or not iid:
                return
            s = acc["sessions"][int(iid)]
            none = self.tr.t("none")
            self.detail_var.set(
                f"{self.tr.t('d_title')}    : {s['title']}\n"
                f"{self.tr.t('d_folder')}    : {s['cwd']}\n"
                f"{self.tr.t('d_last')} : {fmt_time(s['last'])}\n"
                f"{self.tr.t('d_chat')}    : {human_size(s['tr_size'])}     "
                f"{self.tr.t('d_record')}: {human_size(s['rec_size'])}\n"
                f"cli       : {s['cli']}\n"
                f"sid       : {s['sid']}\n"
                f"{self.tr.t('d_transcript')}: {s['transcript'] if s['transcript'] else none}")
            self.set_preview(session_preview(s, limit=1500))
            self.app.status(self.tr.t("g_selected", title=s["title"]))

        def on_cleanup_broken(self):
            if not self.bases:
                return
            broken = find_broken_sessions(self.bases, self.kind,
                                          self.app.email_map)
            if not broken:
                messagebox.showinfo(self.tr.t("g_cleanup_title"),
                                    self.tr.t("g_cleanup_none"))
                return
            preview_lines = []
            for e in broken[:20]:
                s = e["session"]
                preview_lines.append(f"• {account_who(e['account'])} · {s['title']}\n    {s['cwd']}")
            if len(broken) > 20:
                preview_lines.append(f"… +{len(broken)-20}")
            msg = self.tr.t("g_cleanup_confirm", n=len(broken)) + "\n\n" + "\n".join(preview_lines)
            if not messagebox.askyesno(self.tr.t("g_cleanup_title"), msg):
                return
            removed, errs = perform_broken_cleanup(self.bases, broken)
            for m in errs:
                self.logln("    [!] " + m, "warn")
            self.logln(self.tr.t("g_cleanup_done", n=removed), "ok")
            messagebox.showinfo(self.tr.t("g_cleanup_title"),
                                self.tr.t("g_cleanup_done", n=removed))
            self.app.reload()

        def on_move(self):
            src = self.current_source()
            if not src:
                messagebox.showwarning(self.tr.t("mb_missing_t"), self.tr.t("mb_missing"))
                return
            tgt = self.current_target()
            if not tgt:
                messagebox.showwarning(self.tr.t("mb_no_target_t"), self.tr.t("mb_no_target"))
                return
            if src["id"] == tgt["id"]:
                messagebox.showwarning(self.tr.t("mb_same_t"), self.tr.t("mb_same"))
                return
            sel = self.tree.selection()
            if not sel:
                messagebox.showinfo(self.tr.t("mb_pick_t"), self.tr.t("mb_pick"))
                return
            picked = [src["sessions"][int(i)] for i in sel]
            # Bozuk (transkripti eksik) oturumlar için tek seferlik uyarı
            broken_picks = [s for s in picked if session_is_broken(s)]
            if broken_picks:
                titles = "\n".join(f"• {s['title']}" for s in broken_picks[:8])
                if len(broken_picks) > 8:
                    titles += f"\n… +{len(broken_picks)-8}"
                if not messagebox.askyesno(
                        self.tr.t("cd_title"),
                        self.tr.t("notr_warn").split("(")[0].strip() + "\n\n" + titles):
                    return
            if not messagebox.askyesno(self.tr.t("mb_confirm_t"),
                                       self.tr.t("mb_confirm", n=len(picked),
                                                 src=account_who(src), tgt=account_who(tgt))):
                return

            copied = skipped = overwritten = 0
            forced = None
            self.logln("")
            self.logln(self.tr.t("g_move_log_hdr", src=account_who(src), tgt=account_who(tgt)))
            remaining_conf = sum(1 for s in picked if find_conflicts(tgt, s))
            for s in picked:
                rel = target_rel_path(tgt, s)
                conflicts = find_conflicts(tgt, s)
                if conflicts:
                    remaining_conf -= 1
                    decision = forced
                    if decision is None:
                        dlg = ConflictDialog(self.app, s, conflicts, remaining_conf)
                        decision, apply_all = dlg.result
                        if apply_all:
                            forced = decision
                    if decision != "overwrite":
                        self.logln(self.tr.t("g_move_skipped", title=s["title"]), "warn")
                        skipped += 1
                        continue
                    for e in perform_remove(self.bases, conflicts):
                        self.logln("    [!] " + e, "warn")
                    written, werr = perform_copy(self.bases, s, rel,
                                                 email_pair=(src.get("email"), tgt.get("email")))
                    for e in werr:
                        self.logln("    [!] " + e, "warn")
                    self.logln(self.tr.t("g_move_over", title=s["title"], n=len(written)), "ok")
                    overwritten += 1
                else:
                    written, werr = perform_copy(self.bases, s, rel,
                                                 email_pair=(src.get("email"), tgt.get("email")))
                    for e in werr:
                        self.logln("    [!] " + e, "warn")
                    self.logln(self.tr.t("g_move_copied", title=s["title"], n=len(written)), "ok")
                    copied += 1

            self.logln(self.tr.t("g_move_done", c=copied, o=overwritten, s=skipped))
            self.app.status(self.tr.t("g_move_status", c=copied, o=overwritten, s=skipped))
            self.app.reload()
            messagebox.showinfo(self.tr.t("mb_done_t"),
                                self.tr.t("mb_done", c=copied, o=overwritten, s=skipped))

    class BridgePane(ttk.Frame):
        """Claude Code ⇄ Codex dönüştürme paneli."""

        HEADINGS = (("title", "g_col_title"), ("cwd", "g_col_folder"), ("last", "g_col_last"),
                    ("size", "g_col_size"), ("acc", "g_col_account"))
        DIRS = ("c2x", "x2c")

        def __init__(self, master, app):
            super().__init__(master, padding=(10, 8))
            self.app = app
            self.tr = app.tr
            self.claude_sessions = []
            self.codex_sessions = []
            self.accounts = []
            self.shown = []
            self._build()

        def _build(self):
            self.paths_var = tk.StringVar(value="…")
            ttk.Label(self, textvariable=self.paths_var, style="Store.TLabel").pack(fill="x")
            self.info_lbl = ttk.Label(self, style="Muted.TLabel", wraplength=1100, justify="left")
            self.info_lbl.pack(fill="x", pady=(2, 6))

            drow = ttk.Frame(self)
            drow.pack(fill="x", pady=(0, 6))
            self.lbl_dir = ttk.Label(drow, style="Bold.TLabel")
            self.lbl_dir.pack(side="left")
            self.dir_combo = ttk.Combobox(drow, state="readonly", width=28)
            self.dir_combo.pack(side="left", padx=6)
            self.dir_combo.bind("<<ComboboxSelected>>", lambda e: self.on_dir_change())
            self.lbl_filter = ttk.Label(drow)
            self.lbl_filter.pack(side="left", padx=(16, 0))
            self.filter_var = tk.StringVar()
            fe = ttk.Entry(drow, textvariable=self.filter_var)
            fe.pack(side="left", fill="x", expand=True, padx=6)
            fe.bind("<KeyRelease>", lambda e: self.populate())
            self.count_var = tk.StringVar(value="")
            ttk.Label(drow, textvariable=self.count_var, style="Muted.TLabel").pack(side="right")

            paned = ttk.Panedwindow(self, orient="horizontal")
            paned.pack(fill="both", expand=True)
            tw = ttk.Frame(paned, padding=(0, 0, 6, 0))
            paned.add(tw, weight=3)
            self.tree = ttk.Treeview(tw, columns=[c for c, _ in self.HEADINGS],
                                     show="headings", selectmode="extended")
            widths = {"title": (280, "w", True), "cwd": (230, "w", True), "last": (120, "center", False),
                      "size": (78, "e", False), "acc": (170, "w", False)}
            for col, _ in self.HEADINGS:
                w, anc, stretch = widths[col]
                self.tree.column(col, width=w, anchor=anc, stretch=stretch)
            self.tree.tag_configure("odd", background=CLR_STRIPE)
            vsb = ttk.Scrollbar(tw, orient="vertical", command=self.tree.yview)
            self.tree.configure(yscrollcommand=vsb.set)
            self.tree.pack(side="left", fill="both", expand=True)
            vsb.pack(side="right", fill="y")
            self.tree.bind("<<TreeviewSelect>>", self.on_select)

            self.preview_frame = ttk.Labelframe(paned, padding=10)
            paned.add(self.preview_frame, weight=2)
            self.detail_var = tk.StringVar(value="")
            ttk.Label(self.preview_frame, textvariable=self.detail_var, justify="left",
                      anchor="nw", wraplength=380, font=("Segoe UI", 9)).pack(fill="x")
            ttk.Separator(self.preview_frame).pack(fill="x", pady=8)
            self.lbl_firstmsg = ttk.Label(self.preview_frame, style="Muted.TLabel")
            self.lbl_firstmsg.pack(anchor="w")
            self.preview = scrolledtext.ScrolledText(self.preview_frame, height=12, wrap="word",
                                                     font=("Segoe UI", 9), relief="flat",
                                                     background="white")
            self.preview.pack(fill="both", expand=True, pady=(4, 0))
            self.preview.configure(state="disabled")

            orow = ttk.Frame(self, padding=(0, 6))
            orow.pack(fill="x")
            self.reg_codex_var = tk.BooleanVar(value=True)
            self.reg_codex_chk = ttk.Checkbutton(orow, variable=self.reg_codex_var)
            self.lbl_reg_claude = ttk.Label(orow, style="Bold.TLabel")
            self.account_combo = ttk.Combobox(orow, state="readonly", width=44)
            self.convert_btn = ttk.Button(orow, style="Accent.TButton", command=self.on_convert)
            self.convert_btn.pack(side="right", padx=4)

            self.log_frame = ttk.Labelframe(self, padding=6)
            self.log_frame.pack(fill="both", expand=False, pady=(4, 0))
            self.log = scrolledtext.ScrolledText(self.log_frame, height=6, wrap="word",
                                                 font=("Consolas", 9), relief="flat")
            self.log.pack(fill="both", expand=True)
            self.log.tag_config("ok", foreground=CLR_OK)
            self.log.tag_config("warn", foreground=CLR_BANNER)
            self.log.tag_config("err", foreground=CLR_DANGER)
            self.log.configure(state="disabled")

        # ---- durum / state ----
        def direction(self):
            i = self.dir_combo.current()
            return self.DIRS[i] if 0 <= i < len(self.DIRS) else "c2x"

        def sessions(self):
            return self.claude_sessions if self.direction() == "c2x" else self.codex_sessions

        def _layout_options(self):
            for w in (self.reg_codex_chk, self.lbl_reg_claude, self.account_combo):
                w.pack_forget()
            if self.direction() == "c2x":
                self.reg_codex_chk.pack(side="left")
            else:
                self.lbl_reg_claude.pack(side="left")
                self.account_combo.pack(side="left", padx=6)

        def _refresh_accounts(self):
            prev = self.account_combo.current()
            labels = [self.tr.t("g_br_reg_none")] + [
                self.tr.t("g_acc_label", id=account_who(a), n=len(a["sessions"]), t=fmt_time(a["last"]))
                for a in self.accounts]
            self.account_combo["values"] = labels
            self.account_combo.current(prev if 0 <= prev < len(labels) else 0)

        def current_account(self):
            i = self.account_combo.current()
            return self.accounts[i - 1] if 1 <= i <= len(self.accounts) else None

        # ---- i18n ----
        def retranslate(self):
            cur = self.dir_combo.current()
            self.dir_combo["values"] = [self.tr.t("br_dir_c2x"), self.tr.t("br_dir_x2c")]
            self.dir_combo.current(cur if cur >= 0 else 0)
            self.lbl_dir.config(text=self.tr.t("g_br_dir"))
            self.lbl_filter.config(text=self.tr.t("g_filter"))
            self.info_lbl.config(text=self.tr.t("g_br_info"))
            self.preview_frame.config(text=self.tr.t("g_preview"))
            self.lbl_firstmsg.config(text=self.tr.t("g_first_msg"))
            self.reg_codex_chk.config(text=self.tr.t("g_br_reg_codex"))
            self.lbl_reg_claude.config(text=self.tr.t("g_br_reg_claude"))
            self.convert_btn.config(text=self.tr.t("g_br_convert_btn"))
            self.log_frame.config(text=self.tr.t("g_log"))
            for col, key in self.HEADINGS:
                self.tree.heading(col, text=self.tr.t(key))
            self._refresh_accounts()
            self._layout_options()
            self.populate()

        # ---- yardımcılar ----
        def logln(self, msg, tag=None):
            self.log.configure(state="normal")
            self.log.insert("end", msg + "\n", (tag,) if tag else ())
            self.log.see("end")
            self.log.configure(state="disabled")

        def set_preview(self, text):
            self.preview.configure(state="normal")
            self.preview.delete("1.0", "end")
            self.preview.insert("1.0", text or "")
            self.preview.configure(state="disabled")

        # ---- eylemler ----
        def reload(self, email_map):
            self.claude_sessions = csbridge.list_claude_sessions(email_map)
            self.codex_sessions = csbridge.list_codex_sessions()
            bases = existing_bases("code")
            self.accounts = load_accounts(bases[0], {}, "code", email_map) if bases else []
            self.paths_var.set(self.tr.t("g_br_paths", c=csm.projects_dir(),
                                         x=csbridge.codex_sessions_dir()))
            self._refresh_accounts()
            self.populate()
            self.logln(self.tr.t("g_br_loaded", nc=len(self.claude_sessions),
                                 nx=len(self.codex_sessions)), "ok")

        def on_dir_change(self):
            self._layout_options()
            self.populate()

        def populate(self):
            self.tree.delete(*self.tree.get_children())
            flt = self.filter_var.get().strip().lower()
            all_s = self.sessions()
            self.shown = [s for s in all_s
                          if not flt or flt in s["title"].lower() or flt in str(s["cwd"]).lower()]
            for i, s in enumerate(self.shown):
                acc = s.get("email") or ((s.get("account") or "")[:8] + "…" if s.get("account") else "")
                vals = (s["title"], s["cwd"], fmt_time(s["last"]), human_size(s["size"]), acc)
                self.tree.insert("", "end", iid=str(i), values=vals, tags=("odd",) if i % 2 else ())
            self.count_var.set(self.tr.t("g_count", shown=len(self.shown), total=len(all_s)))
            self.detail_var.set(self.tr.t("g_pick_hint"))
            self.set_preview("")

        def on_select(self, _evt=None):
            iid = self.tree.focus()
            if not iid:
                return
            s = self.shown[int(iid)]
            self.detail_var.set(
                f"{self.tr.t('d_title')}    : {s['title']}\n"
                f"{self.tr.t('d_folder')}    : {s['cwd']}\n"
                f"{self.tr.t('d_last')} : {fmt_time(s['last'])}\n"
                f"{self.tr.t('d_chat')}    : {human_size(s['size'])}\n"
                f"id        : {s['id']}\n"
                f"{self.tr.t('d_transcript')}: {s['path']}")
            self.set_preview(s.get("first") or "")
            self.app.status(self.tr.t("g_selected", title=s["title"]))

        def on_convert(self):
            sel = self.tree.selection()
            if not sel:
                messagebox.showinfo(self.tr.t("mb_pick_t"), self.tr.t("mb_br_pick"))
                return
            to_codex = self.direction() == "c2x"
            dir_label = self.tr.t("br_dir_c2x" if to_codex else "br_dir_x2c")
            picked = [self.shown[int(i)] for i in sel]
            # Masaüstü uygulamasında görünmesi için gereken kayıt atlanıyorsa uyar
            warn_key = None
            if to_codex and not self.reg_codex_var.get():
                warn_key = "br_no_codex_reg_warn"
            elif not to_codex and self.current_account() is None:
                warn_key = "br_no_account_warn"
            if warn_key and not messagebox.askyesno(
                    self.tr.t("mb_br_warn_t"),
                    self.tr.t(warn_key) + "\n\n" + self.tr.t("mb_br_continue"), icon="warning"):
                return
            if not messagebox.askyesno(self.tr.t("mb_confirm_t"),
                                       self.tr.t("mb_br_confirm", n=len(picked), dir=dir_label)):
                return
            account = None if to_codex else self.current_account()
            ok = failed = 0
            self.logln("")
            self.logln(self.tr.t("g_br_log_hdr", dir=dir_label))
            self.config(cursor="watch")
            self.update_idletasks()
            try:
                for s in picked:
                    try:
                        if to_codex:
                            r = csbridge.claude_to_codex(s, register_app=self.reg_codex_var.get())
                            new_id = r["thread_id"]
                        else:
                            r = csbridge.codex_to_claude(s, account=account)
                            new_id = r["session_id"]
                    except Exception as e:
                        self.logln(self.tr.t("g_br_fail", title=s["title"], e=e), "err")
                        failed += 1
                        continue
                    self.logln(self.tr.t("g_br_ok", title=s["title"], id=new_id, turns=r["turns"]), "ok")
                    self.logln(f"      -> {r['path']}")
                    if to_codex:
                        self.logln("      " + (self.tr.t("br_reg_codex_yes").strip() if r["registered"]
                                               else self.tr.t("br_reg_codex_no", id=new_id).strip()))
                    elif r["records"]:
                        self.logln("      " + self.tr.t("br_reg_claude", n=len(r["records"])).strip())
                    for w in r["warn"]:
                        self.logln("      [!] " + w, "warn")
                    ok += 1
            finally:
                self.config(cursor="")
            self.logln(self.tr.t("g_br_done", c=ok, f=failed))
            self.app.status(self.tr.t("g_br_status", c=ok, f=failed))
            self.app.reload()
            messagebox.showinfo(self.tr.t("mb_done_t"), self.tr.t("mb_br_done", c=ok, f=failed))

    class PackPane(ttk.Frame):
        """Oturumları dosyaya yedekleme ve dosyadan geri yükleme paneli."""

        HEADINGS = (("kind", "g_col_kind"), ("title", "g_col_title"), ("cwd", "g_col_folder"),
                    ("last", "g_col_last"), ("size", "g_col_size"), ("acc", "g_col_account"))
        MODES = ("export", "import")

        def __init__(self, master, app):
            super().__init__(master, padding=(10, 8))
            self.app = app
            self.tr = app.tr
            self.items = []          # dışa aktarma: cspack öğeleri
            self.shown = []
            self.bundle_path = None
            self.manifest = None
            self.entries = []        # içe aktarma: manifest oturumları
            self.cwd_map = {}
            self.accounts = []
            self._build()

        def _build(self):
            top = ttk.Frame(self)
            top.pack(fill="x")
            self.lbl_mode = ttk.Label(top, style="Bold.TLabel")
            self.lbl_mode.pack(side="left")
            self.mode_combo = ttk.Combobox(top, state="readonly", width=26)
            self.mode_combo.pack(side="left", padx=6)
            self.mode_combo.bind("<<ComboboxSelected>>", lambda e: self.on_mode_change())
            self.pick_btn = ttk.Button(top, command=self.on_pick_bundle)
            self.lbl_filter = ttk.Label(top)
            self.filter_var = tk.StringVar()
            self.filter_entry = ttk.Entry(top, textvariable=self.filter_var, width=24)
            self.filter_entry.bind("<KeyRelease>", lambda e: self.populate())
            self.count_var = tk.StringVar(value="")
            ttk.Label(top, textvariable=self.count_var, style="Muted.TLabel").pack(side="right")

            self.info_lbl = ttk.Label(self, style="Muted.TLabel", wraplength=1100, justify="left")
            self.info_lbl.pack(fill="x", pady=(4, 6))
            self.file_var = tk.StringVar(value="")
            ttk.Label(self, textvariable=self.file_var, style="Store.TLabel").pack(fill="x")

            paned = ttk.Panedwindow(self, orient="horizontal")
            paned.pack(fill="both", expand=True, pady=(4, 0))
            tw = ttk.Frame(paned, padding=(0, 0, 6, 0))
            paned.add(tw, weight=3)
            self.tree = ttk.Treeview(tw, columns=[c for c, _ in self.HEADINGS],
                                     show="headings", selectmode="extended")
            widths = {"kind": (90, "w", False), "title": (240, "w", True), "cwd": (210, "w", True),
                      "last": (115, "center", False), "size": (78, "e", False), "acc": (150, "w", False)}
            for col, _ in self.HEADINGS:
                w, anc, stretch = widths[col]
                self.tree.column(col, width=w, anchor=anc, stretch=stretch)
            self.tree.tag_configure("odd", background=CLR_STRIPE)
            vsb = ttk.Scrollbar(tw, orient="vertical", command=self.tree.yview)
            self.tree.configure(yscrollcommand=vsb.set)
            self.tree.pack(side="left", fill="both", expand=True)
            vsb.pack(side="right", fill="y")
            self.tree.bind("<<TreeviewSelect>>", lambda e: self.on_select())

            right = ttk.Frame(paned)
            paned.add(right, weight=2)

            # --- dışa aktarma seçenekleri
            self.export_box = ttk.Labelframe(right, padding=10)
            self.part_vars = {k: tk.BooleanVar(value=True)
                              for k in ("memory", "scratch", "extras")}
            self.part_chks = {}
            for key in ("memory", "scratch", "extras"):
                chk = ttk.Checkbutton(self.export_box, variable=self.part_vars[key],
                                      command=self.update_size)
                chk.pack(anchor="w", pady=2)
                self.part_chks[key] = chk
            self.size_var = tk.StringVar(value="")
            ttk.Label(self.export_box, textvariable=self.size_var, style="Bold.TLabel")\
                .pack(anchor="w", pady=(10, 6))
            self.save_btn = ttk.Button(self.export_box, style="Accent.TButton", command=self.on_save)
            self.save_btn.pack(anchor="w")

            # --- içe aktarma seçenekleri
            self.import_box = ttk.Frame(right)
            self.src_var = tk.StringVar(value="")
            ttk.Label(self.import_box, textvariable=self.src_var, style="Muted.TLabel",
                      wraplength=360, justify="left").pack(anchor="w")
            arow = ttk.Frame(self.import_box)
            arow.pack(fill="x", pady=(8, 4))
            self.lbl_account = ttk.Label(arow, style="Bold.TLabel")
            self.lbl_account.pack(side="left")
            self.account_combo = ttk.Combobox(arow, state="readonly", width=34)
            self.account_combo.pack(side="left", padx=6)
            self.reg_codex_var = tk.BooleanVar(value=True)
            self.reg_codex_chk = ttk.Checkbutton(self.import_box, variable=self.reg_codex_var)
            self.reg_codex_chk.pack(anchor="w")
            self.overwrite_mem_var = tk.BooleanVar(value=False)
            self.overwrite_mem_chk = ttk.Checkbutton(self.import_box, variable=self.overwrite_mem_var)
            self.overwrite_mem_chk.pack(anchor="w", pady=(0, 6))
            self.map_box = ttk.Labelframe(self.import_box, padding=6)
            self.map_box.pack(fill="both", expand=True)
            self.map_tree = ttk.Treeview(self.map_box, columns=("src", "dst"), show="headings", height=4)
            self.map_tree.column("src", width=170, anchor="w")
            self.map_tree.column("dst", width=170, anchor="w")
            self.map_tree.pack(fill="both", expand=True)
            self.map_btn = ttk.Button(self.map_box, command=self.on_change_folder)
            self.map_btn.pack(anchor="w", pady=(6, 0))
            self.restore_btn = ttk.Button(self.import_box, style="Accent.TButton", command=self.on_restore)
            self.restore_btn.pack(anchor="w", pady=(8, 0))

            self.log_frame = ttk.Labelframe(self, padding=6)
            self.log_frame.pack(fill="both", expand=False, pady=(4, 0))
            self.log = scrolledtext.ScrolledText(self.log_frame, height=6, wrap="word",
                                                 font=("Consolas", 9), relief="flat")
            self.log.pack(fill="both", expand=True)
            self.log.tag_config("ok", foreground=CLR_OK)
            self.log.tag_config("warn", foreground=CLR_BANNER)
            self.log.tag_config("err", foreground=CLR_DANGER)
            self.log.configure(state="disabled")

        # ---- durum ----
        def mode(self):
            i = self.mode_combo.current()
            return self.MODES[i] if 0 <= i < len(self.MODES) else "export"

        def _layout_mode(self):
            exporting = self.mode() == "export"
            self.pick_btn.pack_forget()
            self.lbl_filter.pack_forget()
            self.filter_entry.pack_forget()
            self.export_box.pack_forget()
            self.import_box.pack_forget()
            if exporting:
                self.lbl_filter.pack(side="left", padx=(16, 0))
                self.filter_entry.pack(side="left", padx=6)
                self.export_box.pack(fill="both", expand=True)
                self.file_var.set("")
            else:
                self.pick_btn.pack(side="left", padx=(16, 0))
                self.import_box.pack(fill="both", expand=True)
                self.file_var.set(self.tr.t("g_pk_file", p=self.bundle_path)
                                  if self.bundle_path else self.tr.t("g_pk_nofile"))

        def include_parts(self):
            inc = set(cspack.DEFAULT_PARTS)
            if not self.part_vars["memory"].get():
                inc.discard("memory")
            if not self.part_vars["scratch"].get():
                inc.discard("scratch")
            if not self.part_vars["extras"].get():
                inc.discard("extras")
                inc.discard("codex_extras")
            return inc

        def selected_items(self):
            sel = self.tree.selection()
            return [self.shown[int(i)] for i in sel]

        def current_account(self):
            i = self.account_combo.current()
            return self.accounts[i - 1] if 1 <= i <= len(self.accounts) else None

        # ---- i18n ----
        def retranslate(self):
            cur = self.mode_combo.current()
            self.mode_combo["values"] = [self.tr.t("g_pk_mode_export"), self.tr.t("g_pk_mode_import")]
            self.mode_combo.current(cur if cur >= 0 else 0)
            self.lbl_mode.config(text=self.tr.t("g_pk_mode"))
            self.lbl_filter.config(text=self.tr.t("g_filter"))
            self.info_lbl.config(text=self.tr.t("g_pk_info"))
            self.pick_btn.config(text=self.tr.t("g_pk_pick_btn"))
            self.export_box.config(text=self.tr.t("g_pk_parts"))
            for key, chk in self.part_chks.items():
                chk.config(text=self.tr.t("g_pk_part_" + key))
            self.save_btn.config(text=self.tr.t("g_pk_save_btn"))
            self.lbl_account.config(text=self.tr.t("g_pk_account"))
            self.reg_codex_chk.config(text=self.tr.t("g_pk_reg_codex"))
            self.overwrite_mem_chk.config(text=self.tr.t("g_pk_overwrite_mem"))
            self.map_box.config(text=self.tr.t("g_pk_map"))
            self.map_tree.heading("src", text=self.tr.t("g_pk_map_src"))
            self.map_tree.heading("dst", text=self.tr.t("g_pk_map_dst"))
            self.map_btn.config(text=self.tr.t("g_pk_map_btn"))
            self.restore_btn.config(text=self.tr.t("g_pk_restore_btn"))
            self.log_frame.config(text=self.tr.t("g_log"))
            for col, key in self.HEADINGS:
                self.tree.heading(col, text=self.tr.t(key))
            self._refresh_accounts()
            self._layout_mode()
            self.populate()

        def _refresh_accounts(self):
            prev = self.account_combo.current()
            labels = [self.tr.t("g_br_reg_none")] + [
                self.tr.t("g_acc_label", id=account_who(a), n=len(a["sessions"]), t=fmt_time(a["last"]))
                for a in self.accounts]
            self.account_combo["values"] = labels
            self.account_combo.current(prev if 0 <= prev < len(labels) else 0)

        # ---- yardımcılar ----
        def logln(self, msg, tag=None):
            self.log.configure(state="normal")
            self.log.insert("end", msg + "\n", (tag,) if tag else ())
            self.log.see("end")
            self.log.configure(state="disabled")

        def kind_label(self, kind):
            return "Codex" if kind == "codex" else self.tr.t("type_" + kind)

        # ---- eylemler ----
        def reload(self, email_map):
            self.items = csm.all_sessions_for_pack(email_map)
            self.accounts = cspack.import_accounts(email_map)
            self._refresh_accounts()
            self.populate()
            self.logln(self.tr.t("g_pk_loaded", n=len(self.items)), "ok")

        def on_mode_change(self):
            self._layout_mode()
            self.populate()

        def populate(self):
            self.tree.delete(*self.tree.get_children())
            rows = []
            if self.mode() == "export":
                flt = self.filter_var.get().strip().lower()
                self.shown = [it for it in self.items
                              if not flt or flt in (it["session"].get("title") or "").lower()
                              or flt in str(it["session"].get("cwd") or "").lower()]
                total = len(self.items)
                for it in self.shown:
                    s, acc = it["session"], it.get("account")
                    # Listede hızlı boyut (klasörler taranmaz); tam hesap seçim yapılınca
                    rows.append((self.kind_label(it["kind"]), s.get("title") or "(…)",
                                 s.get("cwd") or "?", fmt_time(s.get("last") or 0),
                                 human_size(cspack.estimate_size([it], quick=True)),
                                 account_who(acc) if acc else ""))
            else:
                self.shown = list(self.entries)
                total = len(self.entries)
                for e in self.shown:
                    acc = (e.get("account") or {}).get("email") or \
                        ((e.get("account") or {}).get("uuid") or "")[:8]
                    rows.append((self.kind_label(e["kind"]), e.get("title") or "(…)",
                                 e.get("cwd") or "?", fmt_time(e.get("last") or 0),
                                 human_size(cspack.bundle_entry_size(e)), acc))
            for i, vals in enumerate(rows):
                self.tree.insert("", "end", iid=str(i), values=vals, tags=("odd",) if i % 2 else ())
            self.count_var.set(self.tr.t("g_count", shown=len(self.shown), total=total))
            self.update_size()

        def on_select(self):
            self.update_size()
            sel = self.tree.selection()
            if sel:
                row = self.shown[int(sel[-1])]
                title = (row["session"]["title"] if self.mode() == "export" else row.get("title"))
                self.app.status(self.tr.t("g_selected", title=title or ""))

        def update_size(self):
            if self.mode() != "export":
                return
            picked = self.selected_items() or self.shown
            try:
                size = cspack.estimate_size(picked, self.include_parts())
            except Exception:
                size = 0
            self.size_var.set(self.tr.t("g_pk_size", n=len(self.tree.selection()),
                                        size=human_size(size)))

        def on_save(self):
            picked = self.selected_items()
            if not picked:
                messagebox.showinfo(self.tr.t("mb_pick_t"), self.tr.t("mb_pk_pick"))
                return
            path = filedialog.asksaveasfilename(
                parent=self.app, title=self.tr.t("g_pk_save_btn"),
                initialfile=cspack.default_bundle_name(picked),
                defaultextension=cspack.BUNDLE_EXT,
                filetypes=[("Claude session bundle", "*" + cspack.BUNDLE_EXT), ("Zip", "*.zip")])
            if not path:
                return
            self.logln("")
            self.logln(self.tr.t("g_pk_log_export"))
            self.config(cursor="watch")
            self.update_idletasks()
            try:
                cspack.export_bundle(picked, path, include=self.include_parts(),
                                     progress=lambda m: (self.logln("  " + m), self.update_idletasks()))
            except Exception as e:
                self.logln(f"  [!] {e}", "err")
                messagebox.showerror(self.tr.t("mb_done_t"), str(e))
                return
            finally:
                self.config(cursor="")
            size = human_size(csm.file_size(Path(path)))
            self.logln(self.tr.t("g_pk_status_export", p=path), "ok")
            self.app.status(self.tr.t("g_pk_status_export", p=path))
            messagebox.showinfo(self.tr.t("mb_done_t"),
                                self.tr.t("mb_pk_done_export", p=path, size=size, n=len(picked)))

        def on_pick_bundle(self):
            path = filedialog.askopenfilename(
                parent=self.app, title=self.tr.t("g_pk_pick_btn"),
                filetypes=[("Claude session bundle", "*" + cspack.BUNDLE_EXT),
                           ("Zip", "*.zip"), ("*", "*.*")])
            if not path:
                return
            try:
                self.manifest = cspack.read_bundle(path)
            except Exception as e:
                messagebox.showerror(self.tr.t("mb_done_t"), str(e))
                return
            self.bundle_path = path
            self.entries = self.manifest.get("sessions", [])
            self.cwd_map = cspack.default_cwd_map(self.manifest)
            src = self.manifest.get("source") or {}
            self.src_var.set(self.tr.t("g_pk_source", user=src.get("user"), host=src.get("host"),
                                       platform=src.get("platform"),
                                       t=fmt_time(self.manifest.get("created_at") or 0)))
            self.file_var.set(self.tr.t("g_pk_file", p=path))
            self._refresh_map()
            self.populate()
            self.logln(self.tr.t("g_pk_bundle_loaded", n=len(self.entries)), "ok")

        def _refresh_map(self):
            self.map_tree.delete(*self.map_tree.get_children())
            for i, (src, dst) in enumerate(sorted(self.cwd_map.items())):
                self.map_tree.insert("", "end", iid=str(i), values=(src, dst))

        def on_change_folder(self):
            sel = self.map_tree.focus()
            if not sel:
                return
            src = self.map_tree.item(sel, "values")[0]
            path = filedialog.askdirectory(parent=self.app, title=self.tr.t("g_pk_map_btn"),
                                           initialdir=self.cwd_map.get(src) or str(Path.home()))
            if not path:
                return
            self.cwd_map[src] = str(Path(path))
            self._refresh_map()

        def on_restore(self):
            if not self.bundle_path:
                messagebox.showinfo(self.tr.t("mb_pick_t"), self.tr.t("mb_pk_nofile"))
                return
            picked = [self.shown[int(i)] for i in self.tree.selection()] or self.shown
            if not picked:
                messagebox.showinfo(self.tr.t("mb_pick_t"), self.tr.t("mb_pk_pick"))
                return
            account = self.current_account()
            needs_account = any(e["kind"] in ("code", "cowork") for e in picked)
            if needs_account and account is None and \
                    not messagebox.askyesno(self.tr.t("mb_br_warn_t"), self.tr.t("mb_pk_noaccount"),
                                            icon="warning"):
                return
            if not messagebox.askyesno(self.tr.t("mb_confirm_t"),
                                       self.tr.t("mb_br_confirm", n=len(picked),
                                                 dir=self.tr.t("g_pk_mode_import"))):
                return

            def on_conflict(entry, conflicts):
                return "overwrite" if ConflictDialog(
                    self.app, {"title": entry.get("title"), "tr_size": None, "rec_size": None,
                               "last": entry.get("last") or 0, "cli": entry.get("cli_session_id") or ""},
                    conflicts, 0).result[0] == "overwrite" else "skip"

            ok = skipped = failed = 0
            self.logln("")
            self.logln(self.tr.t("g_pk_log_import"))
            self.config(cursor="watch")
            self.update_idletasks()
            try:
                for e in picked:
                    acc = None
                    if account is not None and e["kind"] in ("code", "cowork"):
                        acc = cspack.account_for(e["kind"], account["id"], self.app.email_map)
                    res = cspack.import_entry(
                        self.bundle_path, e, account=acc, cwd_map=self.cwd_map,
                        overwrite_memory=self.overwrite_mem_var.get(),
                        register_codex=self.reg_codex_var.get(), manifest=self.manifest,
                        conflict_cb=on_conflict)
                    if res["status"] == "failed":
                        self.logln(self.tr.t("pk_failed", title=e.get("title"),
                                             e="; ".join(res["warn"])), "err")
                        failed += 1
                        continue
                    if res["status"] == "skipped":
                        self.logln(self.tr.t("pk_skipped", title=e.get("title")), "warn")
                        skipped += 1
                        continue
                    self.logln(self.tr.t("pk_restored", title=e.get("title")), "ok")
                    for p in res["paths"]:
                        self.logln(f"      -> {p}")
                    if res.get("skipped_memory"):
                        self.logln("      " + self.tr.t("pk_mem_skipped",
                                                        n=len(res["skipped_memory"])).strip())
                    for w in res["warn"]:
                        self.logln("      [!] " + str(w), "warn")
                    ok += 1
                    self.update_idletasks()
            finally:
                self.config(cursor="")
            self.logln(self.tr.t("pk_done", c=ok, s=skipped, f=failed))
            self.app.status(self.tr.t("g_pk_status_import", c=ok, s=skipped, f=failed))
            self.app.reload()
            messagebox.showinfo(self.tr.t("mb_done_t"),
                                self.tr.t("mb_pk_done_import", c=ok, s=skipped, f=failed))

    class App(tk.Tk):
        def __init__(self):
            super().__init__()
            self.tr = tr
            self.geometry("1180x820")
            self.minsize(1000, 680)
            self.configure(bg=CLR_BG)
            self.email_map = {}
            self.tindex = {}
            self.panes = {}
            self._init_style()
            self._build()
            self.retranslate(initial=True)
            self.reload()

        def _init_style(self):
            st = ttk.Style(self)
            try:
                st.theme_use("clam")
            except Exception:
                pass
            st.configure(".", background=CLR_BG)
            st.configure("TFrame", background=CLR_BG)
            st.configure("Card.TFrame", background="white")
            st.configure("TLabel", background=CLR_BG, font=("Segoe UI", 9))
            st.configure("TLabelframe", background=CLR_BG)
            st.configure("TLabelframe.Label", background=CLR_BG,
                         font=("Segoe UI", 9, "bold"), foreground="#374151")
            st.configure("Muted.TLabel", foreground=CLR_MUTED)
            st.configure("Store.TLabel", foreground=CLR_MUTED, font=("Consolas", 8))
            st.configure("DlgTitle.TLabel", background="white",
                         font=("Segoe UI", 11, "bold"), foreground=CLR_DANGER)
            st.configure("DlgSub.TLabel", background="white",
                         font=("Segoe UI", 10), foreground=CLR_ACCENT)
            st.configure("Bold.TLabel", font=("Segoe UI", 9, "bold"))
            st.configure("TButton", font=("Segoe UI", 9), padding=4)
            st.configure("Accent.TButton", font=("Segoe UI", 10, "bold"),
                         foreground="white", background=CLR_ACCENT, padding=6)
            st.map("Accent.TButton",
                   background=[("active", CLR_ACCENT_HOVER), ("disabled", "#9ca3af")])
            st.configure("Treeview", rowheight=27, font=("Segoe UI", 9),
                         fieldbackground="white", background="white")
            st.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
            st.configure("TNotebook.Tab", font=("Segoe UI", 10, "bold"), padding=(16, 6))

        def _build(self):
            banner = tk.Frame(self, bg=CLR_BANNER)
            banner.pack(fill="x")
            self.banner_lbl = tk.Label(banner, bg=CLR_BANNER, fg="white", anchor="w",
                                       font=("Segoe UI", 9, "bold"))
            self.banner_lbl.pack(fill="x", pady=4)

            top = ttk.Frame(self, padding=(12, 8))
            top.pack(fill="x")
            self.title_lbl = ttk.Label(top, style="Bold.TLabel")
            self.title_lbl.pack(side="left")
            self.btn_refresh = ttk.Button(top, command=self.reload)
            self.btn_refresh.pack(side="right")
            self.lang_combo = ttk.Combobox(top, state="readonly", width=10,
                                           values=["Türkçe", "English"])
            self.lang_combo.current(1 if self.tr.lang == "en" else 0)
            self.lang_combo.pack(side="right", padx=8)
            self.lang_combo.bind("<<ComboboxSelected>>", lambda e: self.on_lang_change())
            self.lbl_lang = ttk.Label(top, style="Bold.TLabel")
            self.lbl_lang.pack(side="right")

            self.nb = ttk.Notebook(self)
            self.nb.pack(fill="both", expand=True, padx=12, pady=(0, 6))
            for kind in SESSION_KINDS:
                pane = SessionPane(self.nb, self, kind)
                self.nb.add(pane, text=self.tr.t("type_" + kind))
                self.panes[kind] = pane
            self.bridge = BridgePane(self.nb, self)
            self.nb.add(self.bridge, text=self.tr.t("type_bridge"))
            self.pack_pane = PackPane(self.nb, self)
            self.nb.add(self.pack_pane, text=self.tr.t("type_pack"))

            self.status_var = tk.StringVar(value="")
            status = tk.Frame(self, bg="#e5e7eb")
            status.pack(fill="x", side="bottom")
            tk.Label(status, textvariable=self.status_var, bg="#e5e7eb", anchor="w",
                     font=("Segoe UI", 8), fg="#374151").pack(fill="x", padx=8, pady=2)

        def status(self, msg):
            self.status_var.set(msg)

        def retranslate(self, initial=False):
            self.title(self.tr.t("app_title"))
            self.banner_lbl.config(text=self.tr.t("g_banner"))
            self.title_lbl.config(text=self.tr.t("app_title"))
            self.btn_refresh.config(text=self.tr.t("g_refresh"))
            self.lbl_lang.config(text=self.tr.t("g_lang"))
            for i, kind in enumerate(SESSION_KINDS):
                self.nb.tab(i, text=self.tr.t("type_" + kind))
            self.nb.tab(len(SESSION_KINDS), text=self.tr.t("type_bridge"))
            self.nb.tab(len(SESSION_KINDS) + 1, text=self.tr.t("type_pack"))
            # Sekmelerin sabit metinleri (etiketler, sütun başlıkları, taşı tuşu)
            # ilk açılışta da atanmalı; yoksa boş görünürler.
            for pane in self.panes.values():
                pane.retranslate()
            self.bridge.retranslate()
            self.pack_pane.retranslate()
            if initial:
                self.status_var.set(self.tr.t("g_ready"))
            else:
                self.status(self.tr.t("g_ready"))

        def on_lang_change(self):
            self.tr.set_lang("en" if self.lang_combo.current() == 1 else "tr")
            self.retranslate()

        def reload(self):
            self.email_map = build_email_index()
            self.tindex = build_transcript_index()
            total_bases = 0
            total_accounts = 0
            for kind, pane in self.panes.items():
                ti = self.tindex if kind == "code" else {}
                pane.reload(self.email_map, ti)
                total_bases += len(pane.bases)
                total_accounts += len(pane.accounts)
            self.bridge.reload(self.email_map)
            self.pack_pane.reload(self.email_map)
            self.status(self.tr.t("g_status_loaded", a=total_accounts, b=total_bases))

    App().mainloop()


def main():
    try:
        import tkinter  # noqa: F401
    except Exception as e:
        print("tkinter bulunamadı / not found. Run with real Python:")
        print("  py", str(Path(sys.argv[0]).resolve()))
        print(f"(hata/error: {e})")
        sys.exit(1)
    run_gui()


if __name__ == "__main__":
    main()
