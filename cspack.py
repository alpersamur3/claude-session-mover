#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Oturum paketi — dışa/içe aktarma (cspack.py)  /  Session bundle export & import
==============================================================================
Bir oturumu **tek dosyaya** (.csmpack — aslında bir zip) yedekler ve başka bir
bilgisayarda istenen hesaba geri yükler. Oturumun her parçası pakete girer:

  Claude Code : local_*.json kaydı + transkript (.jsonl)
                + projects/<proje>/<oturum>/   (tool-results, subagents …)
                + projects/<proje>/memory/     (hafıza dosyaları)
                + %TEMP%/claude/<proje>/<oturum>/  (scratchpad, tasks …)
  Cowork      : local_*.json kaydı + yanındaki local_<uuid>/ klasörü
                (audit.jsonl, outputs, uploads, .claude …)
  Codex       : rollout-*.jsonl + visualizations/<tarih>/<thread>/
                + generated_images/<thread>/

İçe aktarırken yollar hedef bilgisayara göre yeniden yazılır (kullanıcı klasörü
ve proje klasörü değişmiş olabilir), kayıt seçilen hesaba yazılır ve hesaba bağlı
UUID/e-posta referansları csm.perform_copy ile hedefe uyarlanır.

Çalıştırma / Run:
    py csm.py --export        (paket oluştur / create a bundle)
    py csm.py --import <yol>  (paketi geri yükle / restore a bundle)
    py csmui.py               ("📦 Yedek / Aktar" sekmesi / GUI tab)
"""

import os
import re
import sys
import json
import time
import shutil
import zipfile
import tempfile
import getpass
import platform
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent))
import csm  # noqa: E402
import csbridge  # noqa: E402

BUNDLE_MAGIC = "csm-bundle"
BUNDLE_VERSION = 1
BUNDLE_EXT = ".csmpack"

# Parça adları: hangi veri nereye ait
PARTS = ("record", "transcript", "extras", "memory", "scratch", "companion",
         "rollout", "codex_extras")
# Varsayılan olarak her şey
DEFAULT_PARTS = set(PARTS)
# İçeriği metin olarak yeniden yazılmayacak (ikili) dosyalar
BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".pdf", ".zip", ".gz",
              ".7z", ".rar", ".mp3", ".mp4", ".wav", ".mov", ".webm", ".exe", ".dll", ".so",
              ".dylib", ".sqlite", ".db", ".bin", ".woff", ".woff2", ".ttf", ".otf", ".pyc"}


# -------------------------------------------------------------------
# YOLLAR / PATHS
# -------------------------------------------------------------------

def claude_temp_root() -> Path:
    """Claude Code'un oturum çalışma alanı kökü: %TEMP%/claude"""
    return Path(tempfile.gettempdir()) / "claude"


def claude_scratch_dir(project_dir_name: str, cli: str):
    if not project_dir_name or not cli:
        return None
    return claude_temp_root() / project_dir_name / cli


def codex_thread_dirs(thread_id: str, when_ms=None):
    """Codex'in oturuma bağlı yan klasörleri (varsa)."""
    home = csbridge.codex_home()
    out = []
    gi = home / "generated_images" / thread_id
    if gi.is_dir():
        out.append(("generated_images", gi))
    vis = home / "visualizations"
    if vis.is_dir():
        hit = next((d for d in vis.glob(f"*/*/*/{thread_id}") if d.is_dir()), None)
        if hit:
            out.append(("visualizations", hit))
    return out


def _project_dir_name(sess) -> str:
    tr = sess.get("transcript")
    if tr:
        return Path(tr).parent.name
    return csbridge.claude_project_dir_name(sess.get("cwd") or "")


def _dir_stats(path):
    n = total = 0
    for dp, _dn, fn in os.walk(path):
        for f in fn:
            try:
                total += os.path.getsize(os.path.join(dp, f))
                n += 1
            except OSError:
                pass
    return n, total


# -------------------------------------------------------------------
# DIŞA AKTARMA / EXPORT
# -------------------------------------------------------------------

def make_item(kind: str, session: dict, account=None) -> dict:
    """csm/csbridge oturum sözlüğünü paketlenebilir öğeye çevirir."""
    return {"kind": kind, "session": session, "account": account}


def session_sources(item) -> dict:
    """Öğenin diskteki parçaları: {parça: (yol, 'file'|'dir')}"""
    kind, s = item["kind"], item["session"]
    out = {}
    if kind == "codex":
        out["rollout"] = (Path(s["path"]), "file")
        dirs = codex_thread_dirs(s["id"])
        if dirs:
            out["codex_extras"] = ([(name, p) for name, p in dirs], "multi")
        return out

    out["record"] = (Path(s["path"]), "file")
    if kind == "cowork":
        if s.get("folder") and Path(s["folder"]).is_dir():
            out["companion"] = (Path(s["folder"]), "dir")
        return out

    # Claude Code
    cli, cwd = s.get("cli"), s.get("cwd")
    tr = s.get("transcript") or csm.transcript_path_for(cli, cwd)
    if tr and Path(tr).is_file():
        out["transcript"] = (Path(tr), "file")
    proj = _project_dir_name(s)
    extras = csm.session_extras_dir(cli, cwd)
    if tr and Path(tr).is_file():
        extras = Path(tr).parent / cli
    if extras and Path(extras).is_dir():
        out["extras"] = (Path(extras), "dir")
    mem = (Path(tr).parent / "memory") if tr else (csm.projects_dir() / proj / "memory")
    if mem.is_dir():
        out["memory"] = (mem, "dir")
    scratch = claude_scratch_dir(proj, cli)
    if scratch and scratch.is_dir():
        out["scratch"] = (scratch, "dir")
    return out


def estimate_size(items, include=None, quick=False) -> int:
    """Paketin yaklaşık boyutu. quick=True klasörleri taramaz (uzun listelerde hızlı)."""
    include = set(include or DEFAULT_PARTS)
    total = 0
    for it in items:
        for name, (src, typ) in session_sources(it).items():
            if name not in include:
                continue
            if typ == "file":
                total += csm.file_size(src) or 0
            elif quick:
                continue
            elif typ == "dir":
                total += _dir_stats(src)[1]
            else:
                for _n, p in src:
                    total += _dir_stats(p)[1]
    return total


def _zip_dir(z, src: Path, prefix: str, progress=None, skip=None):
    n = total = 0
    for dp, _dn, fn in os.walk(src):
        for f in fn:
            p = Path(dp) / f
            # Paket dosyası taranan klasörün içindeyse kendini paketlemesin
            if skip and os.path.normcase(str(p)) == skip:
                continue
            try:
                rel = p.relative_to(src).as_posix()
                z.write(p, f"{prefix}/{rel}")
                total += p.stat().st_size
                n += 1
            except Exception as e:
                if progress:
                    progress(f"[!] {p}: {e}")
    return n, total


def export_bundle(items, out_path, include=None, progress=None) -> dict:
    """Seçili oturumları tek bir .csmpack dosyasına yazar; manifesti döndürür."""
    include = set(include or DEFAULT_PARTS)
    out_path = Path(out_path).absolute()
    skip_self = os.path.normcase(str(out_path))
    home = str(Path.home())
    manifest = {
        "format": BUNDLE_MAGIC, "version": BUNDLE_VERSION,
        "created_at": int(time.time() * 1000),
        "source": {
            "host": platform.node(), "user": getpass.getuser(), "home": home,
            "platform": sys.platform, "temp_root": str(claude_temp_root()),
            "claude_version": csbridge.detect_claude_version(),
            "projects_dir": str(csm.projects_dir()), "codex_home": str(csbridge.codex_home()),
        },
        "included_parts": sorted(include), "sessions": [],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        for i, it in enumerate(items, 1):
            sid = f"s{i}"
            s, acc = it["session"], it.get("account")
            kind = it["kind"]
            rel = s.get("rel")
            entry = {
                "id": sid, "kind": kind,
                "title": s.get("title") or "(…)", "cwd": s.get("cwd") or "",
                "project_dir": _project_dir_name(s) if kind == "code" else None,
                "cli_session_id": s.get("cli"), "session_id": s.get("sid"),
                "thread_id": s.get("id") if kind == "codex" else None,
                "workspace": (rel.parts[1] if rel is not None and len(rel.parts) >= 2 else None),
                "account": ({"uuid": acc["id"], "email": acc.get("email")} if acc else None),
                "last": s.get("last"), "parts": {},
            }
            if progress:
                progress(f"» {entry['title']}")
            for name, (src, typ) in session_sources(it).items():
                if name not in include:
                    continue
                prefix = f"sessions/{sid}/{name}"
                try:
                    if typ == "file":
                        arc = f"{prefix}/{Path(src).name}"
                        z.write(src, arc)
                        entry["parts"][name] = {"type": "file", "path": arc,
                                                "name": Path(src).name,
                                                "bytes": Path(src).stat().st_size}
                    elif typ == "dir":
                        n, b = _zip_dir(z, Path(src), prefix, progress, skip_self)
                        entry["parts"][name] = {"type": "dir", "path": prefix,
                                                "name": Path(src).name, "files": n, "bytes": b}
                    else:  # multi: [(ad, yol), …]
                        subs = []
                        for sub_name, p in src:
                            n, b = _zip_dir(z, Path(p), f"{prefix}/{sub_name}", progress, skip_self)
                            subs.append({"name": sub_name, "dir": Path(p).name,
                                         "files": n, "bytes": b})
                        entry["parts"][name] = {"type": "multi", "path": prefix, "items": subs}
                except Exception as e:
                    if progress:
                        progress(f"[!] {name}: {e}")
            manifest["sessions"].append(entry)
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
    return manifest


# -------------------------------------------------------------------
# PAKET OKUMA / READ
# -------------------------------------------------------------------

def read_bundle(path) -> dict:
    """Paketin manifestini okur (dosyaları açmadan)."""
    with zipfile.ZipFile(path) as z:
        man = json.loads(z.read("manifest.json").decode("utf-8"))
    if man.get("format") != BUNDLE_MAGIC:
        raise ValueError("not a csm bundle")
    if int(man.get("version", 0)) > BUNDLE_VERSION:
        raise ValueError(f"bundle version {man['version']} is newer than this tool "
                         f"(supports {BUNDLE_VERSION})")
    return man


def bundle_entry_size(entry) -> int:
    total = 0
    for p in entry.get("parts", {}).values():
        total += p.get("bytes") or 0
        for sub in p.get("items") or []:
            total += sub.get("bytes") or 0
    return total


def import_accounts(email_map=None) -> list:
    """İçe aktarmada seçilebilecek Claude hesapları (code + cowork depolarının birleşimi)."""
    email_map = email_map or {}
    seen = {}
    for kind in ("code", "cowork"):
        bases = csm.existing_bases(kind)
        if not bases:
            continue
        tindex = csm.build_transcript_index() if kind == "code" else {}
        for acc in csm.load_accounts(bases[0], tindex, kind, email_map):
            cur = seen.get(acc["id"])
            if cur is None or acc["last"] > cur["last"]:
                seen[acc["id"]] = acc
    return sorted(seen.values(), key=lambda a: a["last"], reverse=True)


def account_for(kind: str, account_id: str, email_map=None):
    """Kaydın yazılacağı depodaki (code/cowork) hesap nesnesi; yoksa yeni klasör olarak kurgulanır."""
    if not account_id:
        return None
    bases = csm.existing_bases(kind)
    if not bases:
        return None
    email_map = email_map or {}
    tindex = csm.build_transcript_index() if kind == "code" else {}
    for acc in csm.load_accounts(bases[0], tindex, kind, email_map):
        if acc["id"] == account_id:
            return acc
    return {"id": account_id, "dir": bases[0] / account_id, "sessions": [], "last": 0,
            "email": email_map.get(account_id), "kind": kind}


def default_cwd_map(manifest) -> dict:
    """Kaynak cwd -> hedef cwd önerisi: kullanıcı klasörü bu bilgisayara uyarlanır."""
    src_home = (manifest.get("source") or {}).get("home") or ""
    dst_home = str(Path.home())
    out = {}
    for e in manifest.get("sessions", []):
        cwd = e.get("cwd") or ""
        if not cwd:
            continue
        target = cwd
        if src_home and dst_home and os.path.normcase(cwd).startswith(os.path.normcase(src_home)):
            target = dst_home + cwd[len(src_home):]
        out[cwd] = target
    return out


# -------------------------------------------------------------------
# YOL / METİN UYARLAMA — PATH REMAPPING
# -------------------------------------------------------------------

def _replacement_pairs(manifest, src_cwd, dst_cwd):
    """
    (eski, yeni) çiftleri. Her yol için üç biçim üretilir:
      C:\\Users\\a\\p   (düz)   C:\\\\Users\\\\a\\\\p  (JSON kaçışlı)   C:/Users/a/p  (eğik)
    Ayrıca Claude'un klasör adı biçimi (C--Users-a-p) da eklenir.
    """
    src = manifest.get("source") or {}
    base = []

    def add(a, b):
        if a and b and a != b and (a, b) not in base:
            base.append((a, b))

    if src_cwd and dst_cwd:
        add(src_cwd, dst_cwd)
        add(csbridge.claude_project_dir_name(src_cwd), csbridge.claude_project_dir_name(dst_cwd))
    s_home, d_home = src.get("home"), str(Path.home())
    add(s_home, d_home)
    if s_home:
        add(csbridge.claude_project_dir_name(s_home), csbridge.claude_project_dir_name(d_home))
    add(src.get("temp_root"), str(claude_temp_root()))
    add(src.get("projects_dir"), str(csm.projects_dir()))
    add(src.get("codex_home"), str(csbridge.codex_home()))

    pairs = []
    for a, b in base:
        for fa, fb in ((a, b),
                       (a.replace("\\", "\\\\"), b.replace("\\", "\\\\")),
                       (a.replace("\\", "/"), b.replace("\\", "/"))):
            if fa != fb and (fa, fb) not in pairs:
                pairs.append((fa, fb))
    # En uzun eşleşme önce uygulansın (kaçışlı biçim ve iç içe yollar bozulmasın)
    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    return pairs


def _remap_text_file(path, pairs):
    if Path(path).suffix.lower() in BINARY_EXT:
        return
    try:
        data = Path(path).read_bytes()
    except OSError:
        return
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return  # ikili içerik: dokunma
    out = text
    for old, new in pairs:
        if old in out:
            out = out.replace(old, new)
    if out != text:
        try:
            Path(path).write_bytes(out.encode("utf-8"))
        except OSError:
            pass


def remap_tree(root, pairs):
    """Klasördeki tüm metin dosyalarının içeriğini ve dosya/klasör adlarını uyarlar."""
    if not pairs:
        return
    root = Path(root)
    if root.is_file():
        _remap_text_file(root, pairs)
        return
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            _remap_text_file(os.path.join(dp, f), pairs)
    for dp, dn, fn in os.walk(root, topdown=False):
        for name in fn + dn:
            new_name = name
            for old, new in pairs:
                if old in new_name:
                    new_name = new_name.replace(old, new)
            if new_name != name:
                try:
                    os.rename(os.path.join(dp, name), os.path.join(dp, new_name))
                except OSError:
                    pass


# -------------------------------------------------------------------
# İÇE AKTARMA / IMPORT
# -------------------------------------------------------------------

def _extract_part(z, entry, name, stage: Path):
    """Paketten bir parçayı geçici klasöre açar; kök yolu döndürür."""
    part = (entry.get("parts") or {}).get(name)
    if not part:
        return None
    dst = stage / name
    if part["type"] == "file":
        dst.mkdir(parents=True, exist_ok=True)
        target = dst / part["name"]
        with z.open(part["path"]) as fsrc, open(target, "wb") as fdst:
            shutil.copyfileobj(fsrc, fdst)
        return target
    prefix = part["path"].rstrip("/") + "/"
    got = False
    for info in z.infolist():
        if info.is_dir() or not info.filename.startswith(prefix):
            continue
        rel = info.filename[len(prefix):]
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        with z.open(info) as fsrc, open(target, "wb") as fdst:
            shutil.copyfileobj(fsrc, fdst)
        got = True
    return dst if got else None


def _copy_tree(src: Path, dst: Path, overwrite=True, skipped=None):
    dst.mkdir(parents=True, exist_ok=True)
    for dp, _dn, fn in os.walk(src):
        rel = Path(dp).relative_to(src)
        (dst / rel).mkdir(parents=True, exist_ok=True)
        for f in fn:
            target = dst / rel / f
            if target.exists() and not overwrite:
                if skipped is not None:
                    skipped.append(str(target))
                continue
            shutil.copy2(Path(dp) / f, target)


def import_entry(zip_path, entry, account=None, cwd_map=None, include=None,
                 overwrite_memory=False, register_codex=True, manifest=None,
                 conflict_cb=None, progress=None) -> dict:
    """
    Paketteki bir oturumu bu bilgisayara geri yükler.
    account: Claude hesabı (code/cowork için; None ise masaüstü kaydı yazılmaz)
    cwd_map: {kaynak_cwd: hedef_cwd}
    conflict_cb(entry, conflicts) -> "overwrite" | "skip"
    Döndürür: {"status", "paths", "warn", "cli", "rel"}
    """
    include = set(include or DEFAULT_PARTS)
    manifest = manifest or read_bundle(zip_path)
    src_cwd = entry.get("cwd") or ""
    dst_cwd = (cwd_map or {}).get(src_cwd) or src_cwd or str(Path.home())
    pairs = _replacement_pairs(manifest, src_cwd, dst_cwd)
    result = {"status": "ok", "paths": [], "warn": [], "cli": entry.get("cli_session_id"),
              "rel": None, "skipped_memory": []}
    stage = Path(tempfile.mkdtemp(prefix="csm-import-"))
    try:
        with zipfile.ZipFile(zip_path) as z:
            parts = {name: _extract_part(z, entry, name, stage)
                     for name in (entry.get("parts") or {}) if name in include}
        for p in parts.values():
            if p:
                remap_tree(p, pairs)

        if entry["kind"] == "codex":
            return _import_codex(entry, parts, dst_cwd, register_codex, result)

        cli = entry.get("cli_session_id")
        proj_dir = csbridge.claude_project_dir_for(dst_cwd)
        if entry["kind"] == "code":
            tr_src = parts.get("transcript")
            tr_dst = proj_dir / f"{cli}.jsonl" if cli else None
            if tr_src and tr_dst:
                tr_dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(tr_src, tr_dst)
                result["paths"].append(tr_dst)
            if parts.get("extras") and cli:
                _copy_tree(parts["extras"], proj_dir / cli)
                result["paths"].append(proj_dir / cli)
            if parts.get("memory"):
                skipped = []
                _copy_tree(parts["memory"], proj_dir / "memory",
                           overwrite=overwrite_memory, skipped=skipped)
                result["skipped_memory"] = skipped
                result["paths"].append(proj_dir / "memory")

        # Masaüstü kaydı (hesap seçilmişse)
        rec_src = parts.get("record")
        final_cli = cli
        if account is not None and rec_src:
            entry_json = csm.load_entry(rec_src) or {}
            src_acc = (entry.get("account") or {}).get("uuid") or "unknown-account"
            src_ws = entry.get("workspace") or "unknown-workspace"
            sess = {
                "kind": entry["kind"], "path": Path(rec_src), "entry": entry_json,
                "cli": entry_json.get("cliSessionId") or cli,
                "sid": entry_json.get("sessionId") or entry.get("session_id"),
                "cwd": dst_cwd, "title": entry.get("title"),
                "last": entry.get("last") or 0,
                "transcript": (proj_dir / f"{cli}.jsonl") if cli else None,
                "folder": parts.get("companion"),
                "rel": Path(src_acc) / src_ws / Path(rec_src).name,
            }
            bases = csm.existing_bases(entry["kind"] if entry["kind"] == "cowork" else "code")
            if not bases:
                result["warn"].append("session store not found")
                result["status"] = "partial"
            else:
                # Hedef hesapta hiç oturum yoksa target_rel_path'in klasör tahmini
                # geçici klasör adını kullanır; bu durumda kaynak workspace'i koru.
                rel = (csm.target_rel_path(account, sess) if account.get("sessions")
                       else Path(account["id"]) / src_ws / Path(rec_src).name)
                conflicts = csm.find_conflicts(account, sess)
                if conflicts:
                    decision = conflict_cb(entry, conflicts) if conflict_cb else "overwrite"
                    if decision != "overwrite":
                        result["status"] = "skipped"
                        return result
                    result["warn"] += csm.perform_remove(bases, conflicts)
                written, errs = csm.perform_copy(
                    bases, sess, rel,
                    email_pair=((entry.get("account") or {}).get("email"), account.get("email")))
                result["warn"] += errs
                result["paths"] += written
                result["rel"] = rel
                if written:
                    new_entry = csm.load_entry(written[0]) or {}
                    final_cli = new_entry.get("cliSessionId") or cli
        elif rec_src:
            result["warn"].append("no account selected: desktop record not written")

        # Scratchpad (nihai oturum kimliğine göre)
        if parts.get("scratch") and final_cli:
            dst = claude_temp_root() / proj_dir.name / final_cli
            _copy_tree(parts["scratch"], dst)
            result["paths"].append(dst)
        result["cli"] = final_cli
        return result
    except Exception as e:
        result["status"] = "failed"
        result["warn"].append(str(e))
        return result
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def _import_codex(entry, parts, dst_cwd, register_codex, result):
    src = parts.get("rollout")
    if not src:
        result["status"] = "failed"
        result["warn"].append("rollout missing in bundle")
        return result
    tid = entry.get("thread_id") or Path(src).stem
    meta, items = csbridge.read_codex_rollout(src)
    when = meta.get("first_ms") or entry.get("last") or csbridge.now_ms()
    local = datetime.fromtimestamp(when / 1000.0)
    y, m, d = local.strftime("%Y"), local.strftime("%m"), local.strftime("%d")
    day = csbridge.codex_sessions_dir() / y / m / d
    dst = day / Path(src).name
    if dst.exists():
        # Aynı thread bu bilgisayarda zaten var: yeni kimlikle yaz
        new_tid = csbridge.uuid7(when)
        remap_tree(src, [(tid, new_tid)])
        dst = day / Path(src).name.replace(tid, new_tid)
        result["warn"].append(f"thread already exists, imported as {new_tid}")
        tid = new_tid
    day.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    result["paths"].append(dst)
    result["cli"] = tid
    extras = parts.get("codex_extras")
    if extras:
        for sub in sorted(p for p in Path(extras).iterdir() if p.is_dir()):
            if sub.name == "generated_images":
                _copy_tree(sub, csbridge.codex_home() / "generated_images" / tid)
            elif sub.name == "visualizations":
                _copy_tree(sub, csbridge.codex_home() / "visualizations" / y / m / d / tid)
            result["paths"].append(sub.name)
    if register_codex:
        first_user = next((i["text"] for i in items if i["role"] == "user"), "")
        ok, msg = csbridge.register_codex_thread(
            tid, dst, dst_cwd, entry.get("title") or tid, first_user,
            meta.get("first_ms"), meta.get("last_ms"), meta.get("git_branch"),
            csbridge.detect_codex_template()["cli_version"])
        if ok:
            try:
                csbridge._append_codex_thread_name(tid, entry.get("title") or tid)
            except Exception:
                pass
        elif msg != "state db not found":
            result["warn"].append(f"codex app db: {msg}")
            result["status"] = "partial"
    return result


def default_bundle_name(items=None) -> str:
    stamp = time.strftime("%Y%m%d-%H%M")
    if items and len(items) == 1:
        title = re.sub(r"[^\w\-. ]", "", (items[0]["session"].get("title") or "session"))[:40].strip()
        return f"{title or 'session'}-{stamp}{BUNDLE_EXT}"
    n = len(items) if items else 0
    return f"claude-sessions-{n}x-{stamp}{BUNDLE_EXT}" if n else f"claude-sessions-{stamp}{BUNDLE_EXT}"
