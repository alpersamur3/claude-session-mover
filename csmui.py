#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude Sohbet Taşıyıcı — Tkinter Arayüzü (csmui.py)  /  Claude Chat Mover — GUI
==============================================================================
csm.py'nin grafik arayüzlü sürümü. İki sekme:

  • Claude Code  → masaüstü sohbetleri
  • Cowork       → agent oturumları (kayıt + yan klasörleriyle birlikte)

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
)

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
    from tkinter import ttk, messagebox, scrolledtext

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
                    written, werr = perform_copy(self.bases, s, rel)
                    for e in werr:
                        self.logln("    [!] " + e, "warn")
                    self.logln(self.tr.t("g_move_over", title=s["title"], n=len(written)), "ok")
                    overwritten += 1
                else:
                    written, werr = perform_copy(self.bases, s, rel)
                    for e in werr:
                        self.logln("    [!] " + e, "warn")
                    self.logln(self.tr.t("g_move_copied", title=s["title"], n=len(written)), "ok")
                    copied += 1

            self.logln(self.tr.t("g_move_done", c=copied, o=overwritten, s=skipped))
            self.app.status(self.tr.t("g_move_status", c=copied, o=overwritten, s=skipped))
            self.app.reload()
            messagebox.showinfo(self.tr.t("mb_done_t"),
                                self.tr.t("mb_done", c=copied, o=overwritten, s=skipped))

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
            # Sekmelerin sabit metinleri (etiketler, sütun başlıkları, taşı tuşu)
            # ilk açılışta da atanmalı; yoksa boş görünürler.
            for pane in self.panes.values():
                pane.retranslate()
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
