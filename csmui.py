#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude Sohbet Taşıyıcı — Tkinter Arayüzü (csmui.py)
===================================================
csm.py'nin grafik arayüzlü, daha ayrıntılı sürümü. Claude masaüstü
uygulamasının sohbet listeleme kayıtlarını (local_*.json) bir hesaptan
diğerine kopyalar/üzerine yazar.

Ayrıntılı bilgi ve "neden gerekli" açıklaması için README.md dosyasına bakın.

ÇALIŞTIRMA (gerçek Python + tkinter için py launcher önerilir):
    py csmui.py

ÖNEMLİ: Çalıştırmadan önce Claude masaüstü uygulamasını TAMAMEN kapatın.
"""

import os
import sys
import glob
import json
import shutil
from pathlib import Path
from datetime import datetime

# ----------------------------------------------------------------------------
# ÇEKİRDEK MANTIK (csm.py ile aynı)
# ----------------------------------------------------------------------------

PROJECTS_DIR = Path.home() / ".claude" / "projects"


def candidate_bases() -> list:
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
    """Var olan, fiziksel olarak benzersiz base'ler (realpath ile çözülür)."""
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
    if PROJECTS_DIR.exists():
        for p in PROJECTS_DIR.rglob("*.jsonl"):
            index.setdefault(p.stem, p)
    return index


def human_size(n) -> str:
    if n is None:
        return "yok"
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
        "path": entry_path,
        "rel": rel,
        "entry": entry,
        "title": entry.get("title") or "(başlıksız)",
        "cwd": entry.get("cwd", "?"),
        "cli": cli,
        "sid": entry.get("sessionId", entry_path.stem),
        "last": entry.get("lastActivityAt", 0),
        "transcript": transcript,
        "rec_size": file_size(entry_path),
        "tr_size": file_size(transcript),
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
    s_cli = source_session.get("cli")
    s_sid = source_session.get("sid")
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
                errs.append(f"silinemedi: {p} ({e})")
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
            errs.append(f"yazılamadı: {dst} ({e})")
    return written, errs


# ----------------------------------------------------------------------------
# ARAYÜZ
# ----------------------------------------------------------------------------

# Renk paleti
CLR_BANNER = "#b45309"      # turuncu uyarı
CLR_BG = "#f3f4f6"
CLR_ACCENT = "#2563eb"
CLR_ACCENT_HOVER = "#1d4ed8"
CLR_OK = "#15803d"
CLR_MUTED = "#6b7280"
CLR_STRIPE = "#eef2f7"
CLR_DANGER = "#b91c1c"


def acc_label(acc):
    last = max((s["last"] for s in acc["sessions"]), default=0)
    return f"{acc['id'][:8]}…   •   {len(acc['sessions'])} sohbet   •   son {fmt_time(last)}"


def run_gui():
    import tkinter as tk
    from tkinter import ttk, messagebox, scrolledtext

    class ConflictDialog(tk.Toplevel):
        """Boyut karşılaştırması gösterip 'üzerine yazılsın mı?' sorar."""
        def __init__(self, parent, src, conflicts, remaining):
            super().__init__(parent)
            self.title("Çakışma — sohbet hedefte zaten var")
            self.configure(bg="white")
            self.resizable(False, False)
            self.result = ("skip", False)
            self.transient(parent)

            frm = ttk.Frame(self, padding=16, style="Card.TFrame")
            frm.pack(fill="both", expand=True)

            ttk.Label(frm, text="⚠  Bu sohbet hedef hesapta zaten var",
                      style="DlgTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
            ttk.Label(frm, text=src["title"], style="DlgSub.TLabel").grid(
                row=1, column=0, columnspan=2, sticky="w", pady=(2, 12))

            tv = ttk.Treeview(frm, columns=("k", "h"), show="tree headings", height=4)
            tv.heading("#0", text="")
            tv.heading("k", text="KAYNAK (yeni)")
            tv.heading("h", text="HEDEF (mevcut)")
            tv.column("#0", width=140, anchor="w")
            tv.column("k", width=190, anchor="center")
            tv.column("h", width=190, anchor="center")
            c0 = conflicts[0]
            rows = [
                ("Sohbet boyutu", human_size(src["tr_size"]), human_size(c0["tr_size"])),
                ("Kayıt boyutu", human_size(src["rec_size"]), human_size(c0["rec_size"])),
                ("Son tarih", fmt_time(src["last"]), fmt_time(c0["last"])),
                ("cliSessionId", (src["cli"][:8] + "…") if src["cli"] else "-",
                 (c0["cli"][:8] + "…") if c0["cli"] else "-"),
            ]
            for label, k, h in rows:
                tv.insert("", "end", text=label, values=(k, h))
            tv.grid(row=2, column=0, columnspan=2, sticky="we")

            note = ""
            if len(conflicts) > 1:
                note = f"(Hedefte {len(conflicts)} eşleşen kayıt var; hepsi değişecek.)"
            if note:
                ttk.Label(frm, text=note, style="Muted.TLabel").grid(
                    row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))

            self.apply_all = tk.BooleanVar(value=False)
            if remaining > 0:
                ttk.Checkbutton(frm, text=f"Bu kararı kalan {remaining} çakışmaya da uygula",
                                variable=self.apply_all).grid(
                    row=4, column=0, columnspan=2, sticky="w", pady=(10, 4))

            btns = ttk.Frame(frm, style="Card.TFrame")
            btns.grid(row=5, column=0, columnspan=2, sticky="e", pady=(14, 0))
            ttk.Button(btns, text="Atla", command=self._skip).pack(side="right", padx=4)
            ttk.Button(btns, text="Üzerine yaz", style="Accent.TButton",
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
        def __init__(self):
            super().__init__()
            self.title("Claude Sohbet Taşıyıcı")
            self.geometry("1180x740")
            self.minsize(980, 600)
            self.configure(bg=CLR_BG)

            self.bases = []
            self.tindex = {}
            self.accounts = []        # birincil base'den tüm hesaplar
            self.target_accounts = [] # hedefte gösterilenler (kaynak hariç)

            self._init_style()
            self._build()
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
            st.configure("TButton", font=("Segoe UI", 9), padding=4)
            st.configure("Accent.TButton", font=("Segoe UI", 10, "bold"),
                         foreground="white", background=CLR_ACCENT, padding=6)
            st.map("Accent.TButton",
                   background=[("active", CLR_ACCENT_HOVER), ("disabled", "#9ca3af")])
            st.configure("Treeview", rowheight=27, font=("Segoe UI", 9),
                         fieldbackground="white", background="white")
            st.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
            st.configure("TCombobox", padding=3)

        # ---- arayüz kurulumu ----
        def _build(self):
            # Uyarı bandı
            banner = tk.Frame(self, bg=CLR_BANNER)
            banner.pack(fill="x")
            tk.Label(banner, bg=CLR_BANNER, fg="white", anchor="w",
                     font=("Segoe UI", 9, "bold"),
                     text="  ⚠  Taşımadan önce Claude masaüstü uygulamasını TAMAMEN kapatın "
                          "(sistem tepsisinden de çıkın). İşlem bitince yeniden açıp 🔄 Yenile deyin.")\
                .pack(fill="x", pady=4)

            # Araç çubuğu
            top = ttk.Frame(self, padding=(12, 8))
            top.pack(fill="x")
            ttk.Label(top, text="📁 Depo:", font=("Segoe UI", 9, "bold")).pack(side="left")
            self.stores_var = tk.StringVar(value="taranıyor…")
            ttk.Label(top, textvariable=self.stores_var, style="Store.TLabel").pack(side="left", padx=(6, 0))
            ttk.Button(top, text="🔄 Yenile", command=self.reload).pack(side="right")

            # Orta bölüm: sol (liste) | sağ (önizleme)
            paned = ttk.Panedwindow(self, orient="horizontal")
            paned.pack(fill="both", expand=True, padx=12, pady=(0, 6))

            # --- sol ---
            left = ttk.Frame(paned, padding=(0, 0, 6, 0))
            paned.add(left, weight=3)

            srow = ttk.Frame(left)
            srow.pack(fill="x", pady=(0, 6))
            ttk.Label(srow, text="Kaynak hesap:", font=("Segoe UI", 9, "bold")).pack(side="left")
            self.source_combo = ttk.Combobox(srow, state="readonly", width=44)
            self.source_combo.pack(side="left", padx=6)
            self.source_combo.bind("<<ComboboxSelected>>", lambda e: self.on_source_change())

            frow = ttk.Frame(left)
            frow.pack(fill="x", pady=(0, 6))
            ttk.Label(frow, text="🔍 Filtre:").pack(side="left")
            self.filter_var = tk.StringVar()
            fe = ttk.Entry(frow, textvariable=self.filter_var)
            fe.pack(side="left", fill="x", expand=True, padx=6)
            fe.bind("<KeyRelease>", lambda e: self.populate_sessions())
            self.count_var = tk.StringVar(value="")
            ttk.Label(frow, textvariable=self.count_var, style="Muted.TLabel").pack(side="right")

            tw = ttk.Frame(left)
            tw.pack(fill="both", expand=True)
            cols = ("title", "cwd", "last", "tr", "rec")
            self.tree = ttk.Treeview(tw, columns=cols, show="headings", selectmode="extended")
            for c, txt, w, anc, stretch in (
                ("title", "Başlık", 240, "w", True),
                ("cwd", "Klasör", 230, "w", True),
                ("last", "Son tarih", 120, "center", False),
                ("tr", "Sohbet", 78, "e", False),
                ("rec", "Kayıt", 78, "e", False),
            ):
                self.tree.heading(c, text=txt)
                self.tree.column(c, width=w, anchor=anc, stretch=stretch)
            self.tree.tag_configure("odd", background=CLR_STRIPE)
            self.tree.tag_configure("notr", foreground=CLR_DANGER)
            vsb = ttk.Scrollbar(tw, orient="vertical", command=self.tree.yview)
            self.tree.configure(yscrollcommand=vsb.set)
            self.tree.pack(side="left", fill="both", expand=True)
            vsb.pack(side="right", fill="y")
            self.tree.bind("<<TreeviewSelect>>", self.on_select)

            # --- sağ (önizleme) ---
            right = ttk.Labelframe(paned, text=" Önizleme ", padding=10)
            paned.add(right, weight=2)
            self.detail_var = tk.StringVar(value="Soldan bir sohbet seçin…")
            ttk.Label(right, textvariable=self.detail_var, justify="left",
                      anchor="nw", wraplength=380, font=("Segoe UI", 9)).pack(fill="x")
            ttk.Separator(right).pack(fill="x", pady=8)
            ttk.Label(right, text="İlk mesaj:", style="Muted.TLabel").pack(anchor="w")
            self.preview = scrolledtext.ScrolledText(right, height=14, wrap="word",
                                                     font=("Segoe UI", 9), relief="flat",
                                                     background="white")
            self.preview.pack(fill="both", expand=True, pady=(4, 0))
            self.preview.configure(state="disabled")

            # Hedef + taşı
            trow = ttk.Frame(self, padding=(12, 4))
            trow.pack(fill="x")
            ttk.Label(trow, text="Hedef hesap:", font=("Segoe UI", 9, "bold")).pack(side="left")
            self.target_combo = ttk.Combobox(trow, state="readonly", width=44)
            self.target_combo.pack(side="left", padx=6)
            self.move_btn = ttk.Button(trow, text="Seçili sohbet(leri) taşı  →",
                                       style="Accent.TButton", command=self.on_move)
            self.move_btn.pack(side="left", padx=12)

            # Günlük
            logf = ttk.Labelframe(self, text=" İşlem günlüğü ", padding=6)
            logf.pack(fill="both", expand=False, padx=12, pady=(4, 4))
            self.log = scrolledtext.ScrolledText(logf, height=8, wrap="word",
                                                 font=("Consolas", 9), relief="flat")
            self.log.pack(fill="both", expand=True)
            self.log.tag_config("ok", foreground=CLR_OK)
            self.log.tag_config("warn", foreground=CLR_BANNER)
            self.log.tag_config("err", foreground=CLR_DANGER)
            self.log.configure(state="disabled")

            # Durum çubuğu
            self.status_var = tk.StringVar(value="Hazır.")
            status = tk.Frame(self, bg="#e5e7eb")
            status.pack(fill="x", side="bottom")
            tk.Label(status, textvariable=self.status_var, bg="#e5e7eb", anchor="w",
                     font=("Segoe UI", 8), fg="#374151").pack(fill="x", padx=8, pady=2)

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
            self.preview.insert("1.0", text or "(transkript bulunamadı)")
            self.preview.configure(state="disabled")

        def current_source(self):
            i = self.source_combo.current()
            return self.accounts[i] if 0 <= i < len(self.accounts) else None

        def current_target(self):
            i = self.target_combo.current()
            return self.target_accounts[i] if 0 <= i < len(self.target_accounts) else None

        # ---- olaylar / eylemler ----
        def reload(self):
            self.bases = existing_bases()
            if not self.bases:
                self.stores_var.set("HİÇBİR DEPO BULUNAMADI")
                self.status("Depo yok — gerçek Python ile çalıştırın: py csmui.py")
                self.logln("[hata] Session deposu bulunamadı.", "err")
                self.logln(f"       python : {sys.executable}")
                for c in candidate_bases():
                    self.logln(f"       [{'VAR' if c.exists() else 'YOK'}] {c}")
                self.accounts, self.target_accounts = [], []
                self.source_combo["values"] = []
                self.target_combo["values"] = []
                self.move_btn.state(["disabled"])
                return

            self.stores_var.set("   |   ".join(str(b) for b in self.bases))
            self.tindex = build_transcript_index()
            self.accounts = load_accounts(self.bases[0], self.tindex)
            self.source_combo["values"] = [acc_label(a) for a in self.accounts]

            if len(self.accounts) < 2:
                self.logln(f"[uyarı] Taşıma için 2 hesap gerekli, bulunan: {len(self.accounts)}", "warn")
                self.move_btn.state(["disabled"])
            else:
                self.move_btn.state(["!disabled"])

            if self.accounts:
                self.source_combo.current(0)
                self.on_source_change()
            self.logln(f"[ok] {len(self.bases)} depo, {len(self.accounts)} hesap yüklendi.", "ok")
            self.status(f"{len(self.accounts)} hesap • {len(self.bases)} fiziksel depo")

        def refresh_target(self):
            """Hedef listesini kaynak HARİÇ yeniden kurar (önceki seçimi korur)."""
            src = self.current_source()
            prev_id = None
            ct = self.current_target()
            if ct:
                prev_id = ct["id"]
            self.target_accounts = [a for a in self.accounts if not src or a["id"] != src["id"]]
            self.target_combo["values"] = [acc_label(a) for a in self.target_accounts]
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
            self.count_var.set(f"{shown}/{len(acc['sessions'])} sohbet")
            self.set_preview("")
            self.detail_var.set("Soldan bir sohbet seçin…")

        def on_select(self, _evt=None):
            acc = self.current_source()
            iid = self.tree.focus()
            if not acc or not iid:
                return
            s = acc["sessions"][int(iid)]
            self.detail_var.set(
                f"Başlık    : {s['title']}\n"
                f"Klasör    : {s['cwd']}\n"
                f"Son tarih : {fmt_time(s['last'])}\n"
                f"Sohbet    : {human_size(s['tr_size'])}     Kayıt: {human_size(s['rec_size'])}\n"
                f"cli       : {s['cli']}\n"
                f"sid       : {s['sid']}\n"
                f"transkript: {s['transcript'] if s['transcript'] else 'YOK'}")
            self.set_preview(first_user_message(s["transcript"]))
            self.status(f"Seçili: {s['title']}")

        def on_move(self):
            src = self.current_source()
            tgt = self.current_target()
            if not src or not tgt:
                messagebox.showwarning("Eksik seçim", "Kaynak ve hedef hesap seçilmeli.")
                return
            if src["id"] == tgt["id"]:
                messagebox.showwarning("Aynı hesap", "Kaynak ve hedef aynı olamaz.")
                return
            sel = self.tree.selection()
            if not sel:
                messagebox.showinfo("Sohbet seçin", "Taşımak için en az bir sohbet seçin.")
                return
            picked = [src["sessions"][int(i)] for i in sel]
            if not messagebox.askyesno(
                    "Onay",
                    f"{len(picked)} sohbet\n  {src['id'][:8]}…  →  {tgt['id'][:8]}…\n"
                    "hesabına taşınsın mı?\n\n"
                    "(Claude uygulamasının KAPALI olduğundan emin olun.)"):
                return

            copied = skipped = overwritten = 0
            forced = None
            self.logln("")
            self.logln(f"═══ TAŞIMA: {src['id'][:8]}… → {tgt['id'][:8]}… ═══")
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
                        self.logln(f"  • atlandı       : {s['title']}", "warn")
                        skipped += 1
                        continue
                    for e in mirror_remove(self.bases, [c["rel"] for c in conflicts]):
                        self.logln("    [uyarı] " + e, "warn")
                    written, werr = mirror_write(self.bases, s["path"], rel)
                    for e in werr:
                        self.logln("    [uyarı] " + e, "warn")
                    self.logln(f"  • üzerine yazıldı: {s['title']}  ({len(written)} depo)", "ok")
                    overwritten += 1
                else:
                    written, werr = mirror_write(self.bases, s["path"], rel)
                    for e in werr:
                        self.logln("    [uyarı] " + e, "warn")
                    self.logln(f"  • kopyalandı     : {s['title']}  ({len(written)} depo)", "ok")
                    copied += 1

            self.logln(f"─── Bitti.  kopyalandı={copied}  üzerine yazıldı={overwritten}  atlandı={skipped}")
            self.status(f"Tamamlandı: {copied} kopya, {overwritten} üzerine yazıldı, {skipped} atlandı")
            self.reload()
            messagebox.showinfo(
                "Tamamlandı",
                f"Kopyalandı       : {copied}\n"
                f"Üzerine yazıldı  : {overwritten}\n"
                f"Atlandı          : {skipped}\n\n"
                "Şimdi Claude masaüstü uygulamasını yeniden açın.")

    App().mainloop()


def main():
    try:
        import tkinter  # noqa: F401
    except Exception as e:
        print("tkinter bulunamadı. Gerçek Python ile çalıştırın (örn. py launcher):")
        print("  py", str(Path(sys.argv[0]).resolve()))
        print(f"(hata: {e})")
        sys.exit(1)
    run_gui()


if __name__ == "__main__":
    main()
