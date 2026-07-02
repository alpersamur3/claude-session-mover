#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude Sohbet Taşıyıcı — Terminal (csm.py)  /  Claude Chat Mover — CLI
=====================================================================
Claude masaüstü uygulamasının oturum kayıtlarını (local_*.json) bir hesaptan
diğerine kopyalar/üzerine yazar. İki oturum tipi desteklenir:

  • Claude Code  → claude-code-sessions   (masaüstü sohbetleri)
  • Cowork       → local-agent-mode-sessions (agent oturumları + yan klasörleri)

Ayrıntı için README.md.

Çalıştırma / Run:
    py csm.py                 (Türkçe)
    py csm.py --en            (English)
    py csm.py --demo          (repo içindeki sample-data ile dene / try bundled sample data)

Ortam değişkenleri / Env vars:
    CSM_LANG=tr|en            arayüz dili / UI language
    CSM_BASE=<yol>            özel depo kökü / custom store root (os.pathsep ile çoklu)
    CSM_PROJECTS=<yol>        transkript klasörü / transcript dir

ÖNEMLİ: Çalıştırmadan önce Claude masaüstü uygulamasını TAMAMEN kapat.
        Store/sandbox python sorununda 'py' launcher kullan.
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

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPT_DIR = Path(__file__).resolve().parent
IS_DEMO = "--demo" in sys.argv[1:]
tr = Translator(detect_lang())

# Oturum tipi -> depo klasör adı / session type -> store dir name
STORE_NAMES = {
    "code": "claude-code-sessions",
    "cowork": "local-agent-mode-sessions",
}
# Cowork deposunda hesap olmayan (atlanacak) üst klasörler
COWORK_SKIP_DIRS = {"skills-plugin"}


def projects_dir() -> Path:
    if IS_DEMO:
        return SCRIPT_DIR / "sample-data" / "projects"
    env = os.environ.get("CSM_PROJECTS")
    return Path(env) if env else (Path.home() / ".claude" / "projects")


def candidate_bases(kind: str = "code") -> list:
    store = STORE_NAMES.get(kind, STORE_NAMES["code"])
    if IS_DEMO:
        return [SCRIPT_DIR / "sample-data" / store]
    if os.environ.get("CSM_BASE"):
        # CSM_BASE claude-code depolarını gösterir; cowork için kardeş klasöre çevir.
        out = []
        for p in os.environ["CSM_BASE"].split(os.pathsep):
            if not p:
                continue
            pp = Path(p)
            out.append(pp if pp.name == store else pp.parent / store)
        return out
    home = Path.home()
    cands = []
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA") or str(home / "AppData" / "Roaming")
        local = os.environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local")
        cands += [
            Path(appdata) / "Claude" / store,
            home / "AppData" / "Roaming" / "Claude" / store,
            Path(local) / "Claude" / store,
        ]
        for pkg in glob.glob(str(Path(local) / "Packages" / "Claude_*")):
            cands.append(Path(pkg) / "LocalCache" / "Roaming" / "Claude" / store)
            cands.append(Path(pkg) / "LocalCache" / "Local" / "Claude" / store)
    elif sys.platform == "darwin":  # macOS (deneysel / experimental)
        cands.append(home / "Library" / "Application Support" / "Claude" / store)
    else:  # Linux/diğer (deneysel / experimental)
        xdg = os.environ.get("XDG_CONFIG_HOME")
        cfg = Path(xdg) if xdg else (home / ".config")
        cands += [
            cfg / "Claude" / store,
            home / ".config" / "Claude" / store,
        ]
    return cands


def existing_bases(kind: str = "code") -> list:
    """Var olan, fiziksel olarak benzersiz base'ler (realpath ile çözülür)."""
    seen = {}
    for c in candidate_bases(kind):
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


def build_email_index(kinds=("cowork", "code")) -> dict:
    """
    Hesap UUID -> e-posta eşlemesi. Cowork oturumlarının yan klasöründeki
    .claude/.claude.json dosyalarındaki oauthAccount alanından toplanır.
    Hesaplar iki depoda ortak olduğu için Claude Code hesaplarını da çözer.
    """
    mapping = {}
    for kind in kinds:
        for base in existing_bases(kind):
            try:
                for dp, _dn, fn in os.walk(base):
                    if ".claude.json" not in fn:
                        continue
                    try:
                        with open(os.path.join(dp, ".claude.json"),
                                  encoding="utf-8", errors="ignore") as f:
                            d = json.load(f)
                    except Exception:
                        continue
                    oa = d.get("oauthAccount") or {}
                    u, m = oa.get("accountUuid"), oa.get("emailAddress")
                    if u and m:
                        mapping.setdefault(u, m)
            except Exception:
                continue
    return mapping


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


def dir_size(path):
    if not path:
        return None
    total = 0
    try:
        for dp, _dn, fn in os.walk(path):
            for f in fn:
                try:
                    total += os.path.getsize(os.path.join(dp, f))
                except Exception:
                    pass
    except Exception:
        return None
    return total


def companion_dir(entry_path: Path) -> Path:
    """Cowork oturumunun yan klasörü: local_<sid>.json -> local_<sid>/"""
    return entry_path.with_suffix("")


def first_user_message(transcript_path, limit: int = 140) -> str:
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


def session_preview(session, limit: int = 140) -> str:
    """Oturumun ilk kullanıcı mesajı. Cowork'te kayıttaki initialMessage kullanılır."""
    if session.get("kind") == "cowork":
        msg = (session.get("entry", {}).get("initialMessage") or "").strip()
        if not msg:
            return ""
        t = " ".join(msg.split()).strip()
        return t[:limit] + ("…" if len(t) > limit else "")
    return first_user_message(session.get("transcript"), limit)


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


def account_who(acc) -> str:
    """Hesabı gösterirken e-posta varsa onu, yoksa kısa UUID'yi döndür."""
    email = acc.get("email")
    return email if email else (acc["id"][:8] + "…")


def make_session(entry_path, entry, tindex, base, kind: str = "code") -> dict:
    cli = entry.get("cliSessionId", "")
    transcript = tindex.get(cli)
    try:
        rel = entry_path.relative_to(base)
    except Exception:
        rel = Path(entry_path.parent.parent.name) / entry_path.parent.name / entry_path.name

    folder = None
    cwd = entry.get("cwd", "?")
    if kind == "cowork":
        # Gösterimde sandbox 'outputs' yolu yerine kullanıcının seçtiği klasörü göster.
        picks = entry.get("userSelectedFolders") or []
        if picks:
            cwd = picks[0]
        cand = companion_dir(entry_path)
        if cand.is_dir():
            folder = cand
            audit = cand / "audit.jsonl"
            transcript = audit if audit.exists() else None
        tr_size = dir_size(folder)
    else:
        tr_size = file_size(transcript)

    return {
        "kind": kind,
        "path": entry_path, "rel": rel, "entry": entry,
        "title": entry.get("title") or entry.get("processName") or "(…)",
        "cwd": cwd, "cli": cli,
        "sid": entry.get("sessionId", entry_path.stem),
        "last": entry.get("lastActivityAt", 0), "transcript": transcript,
        "folder": folder,
        "rec_size": file_size(entry_path), "tr_size": tr_size,
    }


def load_accounts(base, tindex, kind: str = "code", email_map=None) -> list:
    email_map = email_map or {}
    accounts = []
    for acc_dir in [d for d in base.iterdir() if d.is_dir()]:
        if kind == "cowork" and acc_dir.name in COWORK_SKIP_DIRS:
            continue
        sessions = []
        entry_paths = acc_dir.glob("*/local_*.json") if kind == "cowork" \
            else acc_dir.rglob("local_*.json")
        for entry_path in entry_paths:
            entry = load_entry(entry_path)
            if not entry:
                continue
            sessions.append(make_session(entry_path, entry, tindex, base, kind))
        sessions.sort(key=lambda s: s["last"], reverse=True)
        last = max((s["last"] for s in sessions), default=0)
        accounts.append({
            "id": acc_dir.name, "dir": acc_dir, "sessions": sessions,
            "last": last, "email": email_map.get(acc_dir.name), "kind": kind,
        })
    # Hesapları son aktiviteye göre (en yeni önce) sırala.
    accounts.sort(key=lambda a: a["last"], reverse=True)
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
    """local_*.json dosyalarını tüm depolardan sil. Hata listesini döndür."""
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
    """local_*.json dosyasını tüm depolara kopyala. (yazılanlar, hatalar) döndür."""
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


def perform_copy(bases, session, rel):
    """
    Bir oturumu tüm depolara kopyala. Cowork ise kayıt dosyasıyla birlikte
    yan klasörü (audit.jsonl, outputs, uploads, .claude ...) de kopyalar.
    """
    written, errs = mirror_write(bases, session["path"], rel)
    if session.get("kind") == "cowork" and session.get("folder"):
        src_dir = Path(session["folder"])
        if src_dir.is_dir():
            rel_dir = rel.with_suffix("")
            for base in bases:
                dst = base / rel_dir
                try:
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(src_dir, dst)
                except Exception as e:
                    errs.append(f"{dst} ({e})")
    return written, errs


def perform_remove(bases, conflicts):
    """Çakışan oturumları (kayıt + cowork yan klasörü) tüm depolardan sil."""
    errs = mirror_remove(bases, [c["rel"] for c in conflicts])
    for c in conflicts:
        if c.get("kind") == "cowork":
            rel_dir = c["rel"].with_suffix("")
            for base in bases:
                d = base / rel_dir
                try:
                    if d.exists():
                        shutil.rmtree(d)
                except Exception as e:
                    errs.append(f"{d} ({e})")
    return errs


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print("\n" + tr.t("cancelled"))
        sys.exit(0)


def yes(answer: str) -> bool:
    return answer.lower() in ("e", "evet", "y", "yes")


def choose_type() -> str:
    print("\n" + tr.t("choose_type"))
    print(tr.t("type_opt_code"))
    print(tr.t("type_opt_cowork"))
    while True:
        sel = ask(tr.t("prompt_type"))
        if sel == "1":
            return "code"
        if sel == "2":
            return "cowork"
        print(tr.t("invalid"))


def choose_account(accounts, role_key, exclude=None, require_sessions=False):
    role = tr.t(role_key)
    print("\n" + tr.t("choose_account", role=role))
    visible = []
    for acc in accounts:
        if acc["id"] == exclude:
            continue
        if require_sessions and not acc["sessions"]:
            continue
        visible.append(acc)
        last = max((s["last"] for s in acc["sessions"]), default=0)
        samples = ", ".join(s["title"] for s in acc["sessions"][:3]) or "-"
        print(tr.t("account_line", i=len(visible), id=account_who(acc),
                   n=len(acc["sessions"]), t=fmt_time(last)))
        print(tr.t("account_samples", s=samples))
    if not visible:
        print(tr.t("no_src_accounts") if require_sessions else tr.t("no_account"))
        sys.exit(1)
    if len(visible) == 1:
        print(tr.t("auto_single", id=account_who(visible[0])))
        return visible[0]
    while True:
        sel = ask(tr.t("prompt_account", role=role))
        if sel.isdigit() and 1 <= int(sel) <= len(visible):
            return visible[int(sel) - 1]
        print(tr.t("invalid"))


def choose_sessions(account):
    print("\n" + tr.t("src_sessions", id=account_who(account)))
    sessions = account["sessions"]
    if not sessions:
        print(tr.t("no_sessions"))
        sys.exit(0)
    for i, s in enumerate(sessions, 1):
        preview = session_preview(s)
        warn = "" if s["transcript"] else tr.t("notr_flag")
        print(f"  [{i}] {s['title']}{warn}")
        print(tr.t("folder_line", cwd=s["cwd"], t=fmt_time(s["last"])))
        print(tr.t("size_line2", tr=human_size(s["tr_size"]), rec=human_size(s["rec_size"])))
        if preview:
            print(tr.t("first_msg", m=preview))
    while True:
        sel = ask(tr.t("prompt_pick"))
        parts = [p.strip() for p in sel.replace(" ", ",").split(",") if p.strip()]
        if parts and all(p.isdigit() and 1 <= int(p) <= len(sessions) for p in parts):
            return [sessions[int(p) - 1] for p in parts]
        print(tr.t("invalid"))


def print_diagnostics(kind: str = "code"):
    print("\n" + tr.t("diag_hdr"))
    print(f"python exe   : {sys.executable}")
    print(f"APPDATA      : {os.environ.get('APPDATA')}")
    print(f"LOCALAPPDATA : {os.environ.get('LOCALAPPDATA')}")
    print(f"home         : {Path.home()}")
    print(tr.t("diag_tried"))
    for c in candidate_bases(kind):
        try:
            ex = c.exists()
        except Exception as e:
            ex = f"err: {e}"
        print(f"  [{'VAR' if ex is True else 'YOK'}] {c}")
    print("\n" + tr.t("diag_hint"))
    print("  py " + str(Path(sys.argv[0]).resolve()))
    print(tr.t("diag_real"))
    print(r'  & "C:\Users\<you>\AppData\Local\Programs\Python\Python312\python.exe" '
          + str(Path(sys.argv[0]).resolve()))


def main():
    kind = choose_type()
    print(tr.t("type_active", name=tr.t("type_" + kind)))

    email_map = build_email_index()
    bases = existing_bases(kind)
    if not bases:
        print(tr.t("no_store"))
        print_diagnostics(kind)
        sys.exit(1)

    print(tr.t("stores_found"))
    for b in bases:
        print(f"  - {b}")

    tindex = build_transcript_index() if kind == "code" else {}
    accounts = load_accounts(bases[0], tindex, kind, email_map)
    if len(accounts) < 2:
        print("\n" + tr.t("need_two", n=len(accounts)))
        print(tr.t("multi_hint"))
        sys.exit(1)

    print("\n" + tr.t("close_app"))
    source = choose_account(accounts, "role_source", require_sessions=True)
    picked = choose_sessions(source)
    target = choose_account(accounts, "role_target", exclude=source["id"])

    print("\n" + tr.t("summary"))
    print(tr.t("src_acc", id=account_who(source)))
    print(tr.t("tgt_acc", id=account_who(target)))
    for s in picked:
        print(f"  - {s['title']}  ({s['cwd']})")
    if not yes(ask("\n" + tr.t("proceed_q"))):
        print(tr.t("cancelled"))
        return

    copied = skipped = overwritten = 0
    for s in picked:
        rel = target_rel_path(target, s)
        conflicts = find_conflicts(target, s)
        if conflicts:
            print("\n" + tr.t("conflict_warn", title=s["title"]))
            print(tr.t("conflict_sub"))
            print(tr.t("size_line", label=tr.t("lbl_source_new"), tr=human_size(s["tr_size"]),
                       rec=human_size(s["rec_size"]), t=fmt_time(s["last"]), title=s["title"]))
            for c in conflicts:
                print(tr.t("size_line", label=tr.t("lbl_target_cur"), tr=human_size(c["tr_size"]),
                           rec=human_size(c["rec_size"]), t=fmt_time(c["last"]), title=c["title"]))
            if not yes(ask(tr.t("overwrite_q"))):
                print(tr.t("r_skipped", title=s["title"]))
                skipped += 1
                continue
            for e in perform_remove(bases, conflicts):
                print(f"    [!] {e}")
            written, werr = perform_copy(bases, s, rel)
            for e in werr:
                print(f"    [!] {e}")
            print(tr.t("r_overwritten", title=s["title"], n=len(written)))
            overwritten += 1
        else:
            written, werr = perform_copy(bases, s, rel)
            for e in werr:
                print(f"    [!] {e}")
            print("\n" + tr.t("r_copied", title=s["title"], n=len(written)))
            for w in written:
                print(tr.t("arrow", p=w))
            copied += 1

    print("\n" + tr.t("done", c=copied, o=overwritten, s=skipped))
    print(tr.t("reopen"))
    print(tr.t("appear_hint"))


if __name__ == "__main__":
    main()
