#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude Sohbet Taşıyıcı — Tkinter Arayüzü (csmui.py)  /  Claude Chat Mover — GUI
==============================================================================
csm.py'nin grafik arayüzlü, daha ayrıntılı sürümü. Sağ üstten TR/EN dil seçimi.
Ayrıntı için README.md.

Çalıştırma / Run:
    py csmui.py               (Türkçe)
    py csmui.py --en          (English)
    py csmui.py --demo        (repo içindeki sample-data ile dene / try bundled sample data)

ÖNEMLİ: Çalıştırmadan önce Claude masaüstü uygulamasını TAMAMEN kapatın.
"""

import os
import sys
import glob
import json
import shutil
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent))
from i18n import Translator, detect_lang  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
IS_DEMO = "--demo" in sys.argv[1:]

# ----------------------------------------------------------------------------
# ÇEKİRDEK MANTIK / CORE
# ----------------------------------------------------------------------------

def projects_dir() -> Path:
    if IS_DEMO:
        return SCRIPT_DIR / "sample-data" / "projects"
    env = os.environ.get("CSM_PROJECTS")
    return Path(env) if env else (Path.home() / ".claude" / "projects")


def candidate_bases() -> list:
    if IS_DEMO:
        return [SCRIPT_DIR / "sample-data" / "claude-code-sessions"]
    if os.environ.get("CSM_BASE"):
        return [Path(p) for p in os.environ["CSM_BASE"].split(os.pathsep) if p]
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    cands = [
        Path(appdata) / "Claude" / "claude-code-sessions",
        Path.home() / "AppData" / "Roaming" / "Claude" / "claude-code-sessions",
        Path(local) / "Claude" / "claude-code-sessions",
    ]
    for pkg in glob.glob(str(Path(local) / "Packages" / "Claude_*")):
        cands.append(Path(pkg) / "LocalCache" / "Roaming" / "Claude" / "claude-code-sessions")
        cands.append(Path(pkg) / "LocalCache" / "Local" / "Claude" / "claude-code-sessions")
    return cands


def existing_bases() -> list:
    seen = {}
    for c in candidate_bases():
        try:
            if not c.exists() or not c.is_dir():
                continue
            real = Path(os.path.realpath(str(c)))
            key = os.path.normcase(str(real))
            if key in seen:
                continue
            mt = 0
            for f in real.rglob("local_*.json"):
                try:
                    mt = max(mt, f.stat().st_mtime)
                except Exception:
                    pass
            seen[key] = (real, mt)
        except Exception:
            continue
    return [v[0] for v in sorted(seen.values(), key=lambda x: x[1], reverse=True)]


def build_transcript_index() -> dict:
    index = {}
    pdir = projects_dir()
    if pdir.exists():
        for p in pdir.rglob("*.jsonl"):
            index.setdefault(p.stem, p)
    return index


def human_size(n) -> str:
    if n is None:
        return "—"
    try:
        n = float(n)
    except Exception:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{int(n)} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} GB"


def file_size(path):
    try:
        return path.stat().st_size if path else None
    except Exception:
        return None


def first_user_message(transcript_path, limit: int = 1500) -> str:
    if not transcript_path:
        return ""
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if o.get("type") == "user":
                    content = o.get("message", {}).get("content")
                    if isinstance(content, str):
                        t = " ".join(content.split()).strip()
                        if t and not t.startswith("[Request interrupted"):
                            return t[:limit] + ("…" if len(t) > limit else "")
    except Exception:
        pass
    return ""


def load_entry(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return json.load(f)
    except Exception:
        return None


def fmt_time(ms) -> str:
    try:
        return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "?"


def make_session(entry_path, entry, tindex, base) -> dict:
    cli = entry.get("cliSessionId", "")
    transcript = tindex.get(cli)
    try:
        rel = entry_path.relative_to(base)
    except Exception:
        rel = Path(entry_path.parent.parent.name) / entry_path.parent.name / entry_path.name
    return {
        "path": entry_path, "rel": rel, "entry": entry,
        "title": entry.get("title") or "(…)",
        "cwd": entry.get("cwd", "?"), "cli": cli,
        "sid": entry.get("sessionId", entry_path.stem),
        "last": entry.get("lastActivityAt", 0), "transcript": transcript,
        "rec_size": file_size(entry_path), "tr_size": file_size(transcript),
    }


def load_accounts(base, tindex) -> list:
    accounts = []
    for acc_dir in sorted([d for d in base.iterdir() if d.is_dir()]):
        sessions = []
        for entry_path in acc_dir.rglob("local_*.json"):
            entry = load_entry(entry_path)
            if not entry:
                continue
            sessions.append(make_session(entry_path, entry, tindex, base))
        sessions.sort(key=lambda s: s["last"], reverse=True)
        accounts.append({"id": acc_dir.name, "dir": acc_dir, "sessions": sessions})
    return accounts


def target_rel_path(target, source_session) -> Path:
    acc_id = target["id"]
    fname = source_session["path"].name
    src_cwd = source_session.get("cwd")
    ws_name = None
    for t in target["sessions"]:
        if src_cwd and t["cwd"] == src_cwd:
            ws_name = t["rel"].parts[1] if len(t["rel"].parts) >= 2 else t["path"].parent.name
            break
    if ws_name is None and target["sessions"]:
        newest = max(target["sessions"], key=lambda s: s["last"])
        ws_name = newest["rel"].parts[1] if len(newest["rel"].parts) >= 2 else newest["path"].parent.name
    if ws_name is None:
        ws_name = source_session["path"].parent.name
    return Path(acc_id) / ws_name / fname


def find_conflicts(target, source_session) -> list:
    conflicts, seen = [], set()
    s_cli, s_sid = source_session.get("cli"), source_session.get("sid")
    for t in target["sessions"]:
        if (s_cli and t["cli"] == s_cli) or (s_sid and t["sid"] == s_sid):
            if t["rel"] not in seen:
                conflicts.append(t)
                seen.add(t["rel"])
    return conflicts


def mirror_remove(bases, rels):
    errs = []
    for base in bases:
        for rel in rels:
            p = base / rel
            try:
                if p.exists():
                    p.unlink()
            except Exception as e:
                errs.append(f"{p} ({e})")
    return errs


def mirror_write(bases, src_file, rel):
    written, errs = [], []
    for base in bases:
        dst = base / rel
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst)
            written.append(dst)
        except Exception as e:
            errs.append(f"{dst} ({e})")
    return written, errs


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

    class App(tk.Tk):
        HEADINGS = (("title", "g_col_title"), ("cwd", "g_col_folder"),
                    ("last", "g_col_last"), ("tr", "g_col_chat"), ("rec", "g_col_record"))

        def __init__(self):
            super().__init__()
            self.tr = tr
            self.geometry("1180x760")
            self.minsize(1000, 620)
            self.configure(bg=CLR_BG)
            self.bases = []
            self.tindex = {}
            self.accounts = []
            self.target_accounts = []
            self._init_style()
            self._build()
            self.retranslate(initial=True)
            self.reload()

        # ---- stil ----
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

        # ---- arayüz ----
        def _build(self):
            # banner
            banner = tk.Frame(self, bg=CLR_BANNER)
            banner.pack(fill="x")
            self.banner_lbl = tk.Label(banner, bg=CLR_BANNER, fg="white", anchor="w",
                                       font=("Segoe UI", 9, "bold"))
            self.banner_lbl.pack(fill="x", pady=4)

            # toolbar
            top = ttk.Frame(self, padding=(12, 8))
            top.pack(fill="x")
            self.lbl_store = ttk.Label(top, style="Bold.TLabel")
            self.lbl_store.pack(side="left")
            self.stores_var = tk.StringVar(value="…")
            ttk.Label(top, textvariable=self.stores_var, style="Store.TLabel").pack(side="left", padx=(6, 0))

            self.btn_refresh = ttk.Button(top, command=self.reload)
            self.btn_refresh.pack(side="right")
            self.lang_combo = ttk.Combobox(top, state="readonly", width=10,
                                           values=["Türkçe", "English"])
            self.lang_combo.current(1 if self.tr.lang == "en" else 0)
            self.lang_combo.pack(side="right", padx=8)
            self.lang_combo.bind("<<ComboboxSelected>>", lambda e: self.on_lang_change())
            self.lbl_lang = ttk.Label(top, style="Bold.TLabel")
            self.lbl_lang.pack(side="right")

            # orta
            paned = ttk.Panedwindow(self, orient="horizontal")
            paned.pack(fill="both", expand=True, padx=12, pady=(0, 6))

            left = ttk.Frame(paned, padding=(0, 0, 6, 0))
            paned.add(left, weight=3)
            srow = ttk.Frame(left)
            srow.pack(fill="x", pady=(0, 6))
            self.lbl_source = ttk.Label(srow, style="Bold.TLabel")
            self.lbl_source.pack(side="left")
            self.source_combo = ttk.Combobox(srow, state="readonly", width=46)
            self.source_combo.pack(side="left", padx=6)
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
            self.preview = scrolledtext.ScrolledText(self.preview_frame, height=14, wrap="word",
                                                     font=("Segoe UI", 9), relief="flat",
                                                     background="white")
            self.preview.pack(fill="both", expand=True, pady=(4, 0))
            self.preview.configure(state="disabled")

            trow = ttk.Frame(self, padding=(12, 4))
            trow.pack(fill="x")
            self.lbl_target = ttk.Label(trow, style="Bold.TLabel")
            self.lbl_target.pack(side="left")
            self.target_combo = ttk.Combobox(trow, state="readonly", width=46)
            self.target_combo.pack(side="left", padx=6)
            self.move_btn = ttk.Button(trow, style="Accent.TButton", command=self.on_move)
            self.move_btn.pack(side="left", padx=12)

            self.log_frame = ttk.Labelframe(self, padding=6)
            self.log_frame.pack(fill="both", expand=False, padx=12, pady=(4, 4))
            self.log = scrolledtext.ScrolledText(self.log_frame, height=8, wrap="word",
                                                 font=("Consolas", 9), relief="flat")
            self.log.pack(fill="both", expand=True)
            self.log.tag_config("ok", foreground=CLR_OK)
            self.log.tag_config("warn", foreground=CLR_BANNER)
            self.log.tag_config("err", foreground=CLR_DANGER)
            self.log.configure(state="disabled")

            self.status_var = tk.StringVar(value="")
            status = tk.Frame(self, bg="#e5e7eb")
            status.pack(fill="x", side="bottom")
            tk.Label(status, textvariable=self.status_var, bg="#e5e7eb", anchor="w",
                     font=("Segoe UI", 8), fg="#374151").pack(fill="x", padx=8, pady=2)

        # ---- i18n ----
        def acc_label(self, acc):
            last = max((s["last"] for s in acc["sessions"]), default=0)
            return self.tr.t("g_acc_label", id=acc["id"][:8], n=len(acc["sessions"]), t=fmt_time(last))

        def retranslate(self, initial=False):
            self.title(self.tr.t("app_title"))
            self.banner_lbl.config(text=self.tr.t("g_banner"))
            self.lbl_store.config(text=self.tr.t("g_store"))
            self.btn_refresh.config(text=self.tr.t("g_refresh"))
            self.lbl_lang.config(text=self.tr.t("g_lang"))
            self.lbl_source.config(text=self.tr.t("g_source"))
            self.lbl_filter.config(text=self.tr.t("g_filter"))
            self.preview_frame.config(text=self.tr.t("g_preview"))
            self.lbl_firstmsg.config(text=self.tr.t("g_first_msg"))
            self.lbl_target.config(text=self.tr.t("g_target"))
            self.move_btn.config(text=self.tr.t("g_move_btn"))
            self.log_frame.config(text=self.tr.t("g_log"))
            for col, key in self.HEADINGS:
                self.tree.heading(col, text=self.tr.t(key))
            if not initial:
                self._refresh_account_combos()
                self.populate_sessions()
                self.status(self.tr.t("g_ready"))
            else:
                self.detail_var.set(self.tr.t("g_pick_hint"))
                self.status_var.set(self.tr.t("g_ready"))

        def on_lang_change(self):
            self.tr.set_lang("en" if self.lang_combo.current() == 1 else "tr")
            self.retranslate()

        # ---- yardımcılar ----
        def logln(self, msg, tag=None):
            self.log.configure(state="normal")
            self.log.insert("end", msg + "\n", (tag,) if tag else ())
            self.log.see("end")
            self.log.configure(state="disabled")

        def status(self, msg):
            self.status_var.set(msg)

        def set_preview(self, text):
            self.preview.configure(state="normal")
            self.preview.delete("1.0", "end")
            self.preview.insert("1.0", text or self.tr.t("g_no_transcript"))
            self.preview.configure(state="disabled")

        def current_source(self):
            i = self.source_combo.current()
            return self.accounts[i] if 0 <= i < len(self.accounts) else None

        def current_target(self):
            i = self.target_combo.current()
            return self.target_accounts[i] if 0 <= i < len(self.target_accounts) else None

        def _refresh_account_combos(self):
            prev_src = self.current_source()
            self.source_combo["values"] = [self.acc_label(a) for a in self.accounts]
            if self.accounts:
                idx = 0
                if prev_src:
                    for j, a in enumerate(self.accounts):
                        if a["id"] == prev_src["id"]:
                            idx = j
                            break
                self.source_combo.current(idx)
            self.refresh_target()

        # ---- eylemler ----
        def reload(self):
            self.bases = existing_bases()
            if not self.bases:
                self.stores_var.set(self.tr.t("g_no_store_short"))
                self.status(self.tr.t("g_no_store_status"))
                self.logln("[!] " + self.tr.t("no_store"), "err")
                self.logln(f"    python: {sys.executable}")
                for c in candidate_bases():
                    self.logln(f"    [{'OK' if c.exists() else '--'}] {c}")
                self.accounts, self.target_accounts = [], []
                self.source_combo["values"] = []
                self.target_combo["values"] = []
                self.move_btn.state(["disabled"])
                return
            self.stores_var.set("   |   ".join(str(b) for b in self.bases))
            self.tindex = build_transcript_index()
            self.accounts = load_accounts(self.bases[0], self.tindex)
            self.source_combo["values"] = [self.acc_label(a) for a in self.accounts]
            if len(self.accounts) < 2:
                self.logln(self.tr.t("g_need_two", n=len(self.accounts)), "warn")
                self.move_btn.state(["disabled"])
            else:
                self.move_btn.state(["!disabled"])
            if self.accounts:
                self.source_combo.current(0)
                self.on_source_change()
            self.logln(self.tr.t("g_loaded", nb=len(self.bases), na=len(self.accounts)), "ok")
            self.status(self.tr.t("g_status_loaded", a=len(self.accounts), b=len(self.bases)))

        def refresh_target(self):
            src = self.current_source()
            prev_id = self.current_target()["id"] if self.current_target() else None
            self.target_accounts = [a for a in self.accounts if not src or a["id"] != src["id"]]
            self.target_combo["values"] = [self.acc_label(a) for a in self.target_accounts]
            if not self.target_accounts:
                self.target_combo.set("")
                return
            idx = 0
            for j, a in enumerate(self.target_accounts):
                if a["id"] == prev_id:
                    idx = j
                    break
            self.target_combo.current(idx)

        def on_source_change(self):
            self.refresh_target()
            self.populate_sessions()

        def populate_sessions(self):
            self.tree.delete(*self.tree.get_children())
            acc = self.current_source()
            if not acc:
                self.count_var.set("")
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
            self.set_preview(first_user_message(s["transcript"]))
            self.status(self.tr.t("g_selected", title=s["title"]))

        def on_move(self):
            src = self.current_source()
            tgt = self.current_target()
            if not src or not tgt:
                messagebox.showwarning(self.tr.t("mb_missing_t"), self.tr.t("mb_missing"))
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
                                                 src=src["id"][:8], tgt=tgt["id"][:8])):
                return

            copied = skipped = overwritten = 0
            forced = None
            self.logln("")
            self.logln(self.tr.t("g_move_log_hdr", src=src["id"][:8], tgt=tgt["id"][:8]))
            remaining_conf = sum(1 for s in picked if find_conflicts(tgt, s))
            for s in picked:
                rel = target_rel_path(tgt, s)
                conflicts = find_conflicts(tgt, s)
                if conflicts:
                    remaining_conf -= 1
                    decision = forced
                    if decision is None:
                        dlg = ConflictDialog(self, s, conflicts, remaining_conf)
                        decision, apply_all = dlg.result
                        if apply_all:
                            forced = decision
                    if decision != "overwrite":
                        self.logln(self.tr.t("g_move_skipped", title=s["title"]), "warn")
                        skipped += 1
                        continue
                    for e in mirror_remove(self.bases, [c["rel"] for c in conflicts]):
                        self.logln("    [!] " + e, "warn")
                    written, werr = mirror_write(self.bases, s["path"], rel)
                    for e in werr:
                        self.logln("    [!] " + e, "warn")
                    self.logln(self.tr.t("g_move_over", title=s["title"], n=len(written)), "ok")
                    overwritten += 1
                else:
                    written, werr = mirror_write(self.bases, s["path"], rel)
                    for e in werr:
                        self.logln("    [!] " + e, "warn")
                    self.logln(self.tr.t("g_move_copied", title=s["title"], n=len(written)), "ok")
                    copied += 1

            self.logln(self.tr.t("g_move_done", c=copied, o=overwritten, s=skipped))
            self.status(self.tr.t("g_move_status", c=copied, o=overwritten, s=skipped))
            self.reload()
            messagebox.showinfo(self.tr.t("mb_done_t"),
                                self.tr.t("mb_done", c=copied, o=overwritten, s=skipped))

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
