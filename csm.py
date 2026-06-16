#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude Desktop - Sohbet (session) Tasiyici  (csm.py)
====================================================
Claude masaustu uygulamasi, sohbetleri HESAP BAZINDA ayri klasorlerde tutar:

    <base>\\<hesap-id>\\<workspace-id>\\local_*.json

<base> birden fazla yerde olabilir. Ozellikle MSIX/Store paketli Claude
kurulumunda %APPDATA% sanallastirilir, bu yuzden veriler IKI yerde tutulur:

    1) %APPDATA%\\Claude\\claude-code-sessions                       (duz yol)
    2) %LOCALAPPDATA%\\Packages\\Claude_*\\LocalCache\\Roaming\\
           Claude\\claude-code-sessions                              (paket deposu)

Bu script bulabildigi TUM base'leri tarar, sohbetleri listeler ve sectigin
kaydi hedef hesaba kopyalar. Yazma islemini var olan TUM base'lere aynalar,
boylece uygulama hangisini okursa okusun sohbet gorunur. Sohbet metni
(.jsonl transkripti) zaten ortak ~/.claude/projects altinda durur, hesaba
bagli degildir; sadece listeleme kaydi tasinir.

Her kayit dosyasinda:
    sessionId    -> "local_<uuid>"  (dosya adiyla AYNI olmali)
    cliSessionId -> transkript .jsonl dosyasini isaret eder (asil sohbet)

Bir sohbet hedef hesapta ZATEN varsa (ayni sessionId YA DA ayni cliSessionId),
script uyarir, her iki kaydin boyutlarini gosterir ve uzerine yazilsin mi diye
sorar.

Kullanim (Store python sorunlarina takilmamak icin py launcher onerilir):
    py C:\\Users\\<sen>\\Desktop\\csm.py
veya:
    python C:\\Users\\<sen>\\Desktop\\csm.py

ONEMLI: Calistirmadan ONCE Claude masaustu uygulamasini TAMAMEN kapat
(sistem tepsisinden de cikis yap). Kopyalama bittikten sonra yeniden ac.
"""

import os
import sys
import glob
import json
import shutil
from pathlib import Path
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


PROJECTS_DIR = Path.home() / ".claude" / "projects"


def candidate_bases() -> list:
    """Olasi tum claude-code-sessions kok klasorlerini (var olsun olmasin) dondurur."""
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    cands = [
        Path(appdata) / "Claude" / "claude-code-sessions",
        Path.home() / "AppData" / "Roaming" / "Claude" / "claude-code-sessions",
        Path(local) / "Claude" / "claude-code-sessions",
    ]
    # MSIX/Store paket deposu (Claude_xxxx) - sanallastirilmis Roaming
    for pkg in glob.glob(str(Path(local) / "Packages" / "Claude_*")):
        cands.append(Path(pkg) / "LocalCache" / "Roaming" / "Claude" / "claude-code-sessions")
        cands.append(Path(pkg) / "LocalCache" / "Local" / "Claude" / "claude-code-sessions")
    return cands


def existing_bases() -> list:
    """Var olan, fiziksel olarak ESSIZ base'leri en yeni once siralayarak dondurur.

    Yollar GERCEK (realpath) konuma cozulur; boylece MSIX/Store reparse-point
    (symlink) takip etme sorunlari atlanir ve dogrudan paket deposuna yazilir.
    """
    seen = {}
    for c in candidate_bases():
        try:
            if not c.exists() or not c.is_dir():
                continue
            real = Path(os.path.realpath(str(c)))  # symlink'i coz
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
    bases = [v[0] for v in sorted(seen.values(), key=lambda x: x[1], reverse=True)]
    return bases


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


def first_user_message(transcript_path: Path, limit: int = 140) -> str:
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
                            return t[:limit] + ("..." if len(t) > limit else "")
    except Exception:
        pass
    return ""


def load_entry(path: Path):
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


def make_session(entry_path: Path, entry: dict, tindex: dict, base: Path) -> dict:
    cli = entry.get("cliSessionId", "")
    transcript = tindex.get(cli)
    # base'e gore goreli yol: <hesap>/<workspace>/<dosya>
    try:
        rel = entry_path.relative_to(base)
    except Exception:
        rel = Path(entry_path.parent.parent.name) / entry_path.parent.name / entry_path.name
    return {
        "path": entry_path,
        "rel": rel,
        "entry": entry,
        "title": entry.get("title") or "(basliksiz)",
        "cwd": entry.get("cwd", "?"),
        "cli": cli,
        "sid": entry.get("sessionId", entry_path.stem),
        "last": entry.get("lastActivityAt", 0),
        "transcript": transcript,
        "rec_size": file_size(entry_path),
        "tr_size": file_size(transcript),
    }


def load_accounts(base: Path, tindex: dict) -> list:
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


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nIptal edildi.")
        sys.exit(0)


def yes(answer: str) -> bool:
    return answer.lower() in ("e", "evet", "y", "yes")


def choose_account(accounts: list, role: str, exclude: str = None) -> dict:
    print(f"\n=== {role} HESABI SEC ===")
    visible = []
    for acc in accounts:
        if acc["id"] == exclude:
            continue
        visible.append(acc)
        idx = len(visible)
        last = max((s["last"] for s in acc["sessions"]), default=0)
        samples = ", ".join(s["title"] for s in acc["sessions"][:3]) or "-"
        print(f"  [{idx}] hesap {acc['id'][:8]}...  "
              f"({len(acc['sessions'])} sohbet, son: {fmt_time(last)})")
        print(f"       ornek: {samples}")
    if not visible:
        print("Uygun hesap yok.")
        sys.exit(1)
    if len(visible) == 1:
        print(f"(Tek uygun hesap: otomatik secildi -> {visible[0]['id'][:8]}...)")
        return visible[0]
    while True:
        sel = ask(f"{role} hesap no: ")
        if sel.isdigit() and 1 <= int(sel) <= len(visible):
            return visible[int(sel) - 1]
        print("Gecersiz secim.")


def choose_sessions(account: dict) -> list:
    print(f"\n=== KAYNAK HESAPTAKI SOHBETLER (hesap {account['id'][:8]}...) ===")
    sessions = account["sessions"]
    if not sessions:
        print("Bu hesapta sohbet yok.")
        sys.exit(0)
    for i, s in enumerate(sessions, 1):
        preview = first_user_message(s["transcript"]) if s["transcript"] else ""
        warn = "" if s["transcript"] else "  [!] transkript bulunamadi"
        print(f"  [{i}] {s['title']}{warn}")
        print(f"       klasor: {s['cwd']}   son: {fmt_time(s['last'])}")
        print(f"       boyut: sohbet {human_size(s['tr_size'])} / kayit {human_size(s['rec_size'])}")
        if preview:
            print(f"       ilk mesaj: {preview}")
    while True:
        sel = ask("Tasinacak sohbet no(lari) (virgulle birden fazla): ")
        parts = [p.strip() for p in sel.replace(" ", ",").split(",") if p.strip()]
        if parts and all(p.isdigit() and 1 <= int(p) <= len(sessions) for p in parts):
            return [sessions[int(p) - 1] for p in parts]
        print("Gecersiz secim.")


def target_rel_path(target: dict, source_session: dict) -> Path:
    """Hedef kaydin base'e goreli yolu: <hedef-hesap>/<workspace>/<dosya>."""
    acc_id = target["id"]
    fname = source_session["path"].name
    # cwd eslesen workspace'i tercih et
    src_cwd = source_session.get("cwd")
    ws_name = None
    for t in target["sessions"]:
        if src_cwd and t["cwd"] == src_cwd:
            ws_name = t["rel"].parts[1] if len(t["rel"].parts) >= 2 else t["path"].parent.name
            break
    if ws_name is None and target["sessions"]:
        # en son kullanilan workspace
        newest = max(target["sessions"], key=lambda s: s["last"])
        ws_name = newest["rel"].parts[1] if len(newest["rel"].parts) >= 2 else newest["path"].parent.name
    if ws_name is None:
        # hic workspace yoksa kaynaktakini kullan
        ws_name = source_session["path"].parent.name
    return Path(acc_id) / ws_name / fname


def find_conflicts(target: dict, source_session: dict) -> list:
    """Hedefte ayni sohbeti (ayni cliSessionId veya ayni sessionId) temsil eden kayitlar."""
    conflicts = []
    seen = set()
    s_cli = source_session.get("cli")
    s_sid = source_session.get("sid")
    for t in target["sessions"]:
        if (s_cli and t["cli"] == s_cli) or (s_sid and t["sid"] == s_sid):
            if t["rel"] not in seen:
                conflicts.append(t)
                seen.add(t["rel"])
    return conflicts


def print_size_line(label: str, s: dict):
    print(f"     {label}: sohbet {human_size(s.get('tr_size'))} / "
          f"kayit {human_size(s.get('rec_size'))}   "
          f"son: {fmt_time(s.get('last'))}   "
          f"baslik: {s.get('title')}")


def mirror_remove(bases: list, rels: list):
    """Verilen goreli yollari TUM base'lerden siler."""
    for base in bases:
        for rel in rels:
            p = base / rel
            try:
                if p.exists():
                    p.unlink()
            except Exception as e:
                print(f"    [uyari] silinemedi: {p} ({e})")


def mirror_write(bases: list, src_file: Path, rel: Path) -> list:
    """Kaynak dosyayi TUM base'lerdeki ayni goreli yola yazar. Yazilan yollar."""
    written = []
    for base in bases:
        dst = base / rel
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst)
            written.append(dst)
        except Exception as e:
            print(f"    [uyari] yazilamadi: {dst} ({e})")
    return written


def print_diagnostics(cands: list):
    print("\n--- TANI BILGISI (lutfen bu cikti ile birlikte bildir) ---")
    print(f"python exe   : {sys.executable}")
    print(f"APPDATA      : {os.environ.get('APPDATA')}")
    print(f"LOCALAPPDATA : {os.environ.get('LOCALAPPDATA')}")
    print(f"USERPROFILE  : {os.environ.get('USERPROFILE')}")
    print(f"home         : {Path.home()}")
    print("Denenen yollar:")
    for c in cands:
        try:
            ex = c.exists()
        except Exception as e:
            ex = f"hata: {e}"
        print(f"  [{'VAR' if ex is True else 'YOK'}] {c}")
    print("\nIpucu: Store python sandbox sorunu olabilir. Su komutu dene:")
    print("  py " + str(Path(sys.argv[0]).resolve()))
    print("veya tam yol ile gercek python:")
    print(r'  & "C:\Users\<sen>\AppData\Local\Programs\Python\Python312\python.exe" ' + str(Path(sys.argv[0]).resolve()))


def main():
    cands = candidate_bases()
    bases = existing_bases()
    if not bases:
        print("Hicbir session klasoru bulunamadi.")
        print_diagnostics(cands)
        sys.exit(1)

    print("Bulunan session depolari (yazma hepsine aynalanir):")
    for b in bases:
        print(f"  - {b}")

    tindex = build_transcript_index()
    primary = bases[0]  # en yeni; hepsi senkron
    accounts = load_accounts(primary, tindex)
    if len(accounts) < 2:
        print(f"\nTasima icin en az 2 hesap gerekli. Bulunan: {len(accounts)}")
        print("(Birden fazla hesapla giris yaptiysan her biri ayri klasor olur.)")
        sys.exit(1)

    print("\nUYARI: Devam etmeden once Claude masaustu uygulamasini TAMAMEN kapat.")
    source = choose_account(accounts, "KAYNAK")
    picked = choose_sessions(source)
    target = choose_account(accounts, "HEDEF", exclude=source["id"])

    print("\n=== OZET ===")
    print(f"Kaynak hesap : {source['id'][:8]}...")
    print(f"Hedef hesap  : {target['id'][:8]}...")
    for s in picked:
        print(f"  - {s['title']}  ({s['cwd']})")
    if not yes(ask("\nDevam edilsin mi? (e/h): ")):
        print("Iptal edildi.")
        return

    copied = skipped = overwritten = 0
    for s in picked:
        rel = target_rel_path(target, s)
        conflicts = find_conflicts(target, s)

        if conflicts:
            print(f"\n[!] UYARI: '{s['title']}' hedef hesapta ZATEN VAR.")
            print("    Ayni sohbet (session id) hedef hesapta bulunuyor:")
            print_size_line("KAYNAK (yeni) ", s)
            for c in conflicts:
                print_size_line("HEDEF (mevcut)", c)
            if not yes(ask("    Uzerine yazilsin mi? (e/h): ")):
                print(f"    [atlandi] {s['title']}")
                skipped += 1
                continue
            mirror_remove(bases, [c["rel"] for c in conflicts])
            written = mirror_write(bases, s["path"], rel)
            print(f"    [uzerine yazildi] {s['title']}  ({len(written)} depoya)")
            for w in written:
                print(f"        -> {w}")
            overwritten += 1
        else:
            written = mirror_write(bases, s["path"], rel)
            print(f"\n[ok] kopyalandi: {s['title']}  ({len(written)} depoya)")
            for w in written:
                print(f"     -> {w}")
            copied += 1

    print(f"\nBitti. kopyalandi={copied}  uzerine_yazildi={overwritten}  atlandi={skipped}")
    print("Simdi Claude masaustu uygulamasini yeniden ac.")
    print("Sohbet(ler) hedef hesabin listesinde gorunecek.")


if __name__ == "__main__":
    main()
