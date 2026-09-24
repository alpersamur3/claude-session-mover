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
    py csm.py --bridge        (Claude Code ⇄ Codex dönüştür / convert, bkz. csbridge.py)
    py csm.py --export        (oturumları dosyaya yedekle / back up sessions to a file)
    py csm.py --import <yol>  (paketi geri yükle / restore a bundle, bkz. cspack.py)

Ortam değişkenleri / Env vars:
    CSM_LANG=tr|en            arayüz dili / UI language
    CSM_BASE=<yol>            özel depo kökü / custom store root (os.pathsep ile çoklu)
    CSM_PROJECTS=<yol>        transkript klasörü / transcript dir

ÖNEMLİ: Çalıştırmadan önce Claude masaüstü uygulamasını TAMAMEN kapat.
        Store/sandbox python sorununda 'py' launcher kullan.
"""

import os
import re
import sys
import glob
import json
import uuid
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


def _remap_bytes(path, replacements):
    """Bir dosyanın içeriğinde (byte düzeyinde) eski->yeni değişimlerini uygula."""
    try:
        data = Path(path).read_bytes()
    except Exception:
        return
    orig = data
    for old, new in replacements:
        if old and new and old != new:
            data = data.replace(old.encode("utf-8"), new.encode("utf-8"))
    if data != orig:
        try:
            Path(path).write_bytes(data)
        except Exception:
            pass


def cowork_remap(json_path, companion_dir, replacements):
    """
    Cowork oturumu bir hesaptan diğerine taşınınca, kayıt + yan klasördeki
    kaynak hesap/space UUID'lerini (ve varsa e-postayı) hedefinkilerle değiştirir.

    Kritik olan: transkript, yan klasörde tam yola göre adlandırılmış bir klasörde
    (.claude/projects/C--...-<hesap>-<space>-...-outputs/<cli>.jsonl) tutulur.
    UUID'ler değişmezse Claude, taşınan oturumu yeni cwd'de bulamaz ve bağlamsız
    (boş) yeni bir oturum açar. Bu yüzden hem dosya içerikleri hem de klasör
    adları yeniden yazılır.
    """
    _remap_bytes(json_path, replacements)
    if not (companion_dir and Path(companion_dir).is_dir()):
        return
    # 1) tüm dosya içeriklerini yeniden yaz
    for dp, _dn, fn in os.walk(companion_dir):
        for f in fn:
            _remap_bytes(os.path.join(dp, f), replacements)
    # 2) klasör/dosya adlarını (en derinden başlayarak) yeniden adlandır
    for dp, dn, fn in os.walk(companion_dir, topdown=False):
        for name in fn + dn:
            new_name = name
            for old, new in replacements:
                if old and new and old != new and old in new_name:
                    new_name = new_name.replace(old, new)
            if new_name != name:
                try:
                    os.rename(os.path.join(dp, name), os.path.join(dp, new_name))
                except Exception:
                    pass


def cowork_replacements(session, rel, email_pair=None):
    """Kaynak (session['rel']) ve hedef (rel) yollarından (eski, yeni) çiftlerini üret."""
    reps = []
    s_parts = session["rel"].parts
    t_parts = rel.parts
    if len(s_parts) >= 2 and len(t_parts) >= 2:
        if s_parts[0] != t_parts[0]:      # hesap UUID
            reps.append((s_parts[0], t_parts[0]))
        if s_parts[1] != t_parts[1]:      # space/organizationUuid
            reps.append((s_parts[1], t_parts[1]))
    if email_pair:
        se, te = email_pair
        if se and te and se != te:
            reps.append((se, te))
    return reps


def sanitize_cwd(cwd: str) -> str:
    """Claude Code'un cwd -> proje klasörü adı dönüşümü: \\ / : . karakterleri - olur."""
    if not cwd:
        return ""
    return re.sub(r"[\\/:.]", "-", cwd)


def transcript_path_for(cli: str, cwd: str):
    """Bir oturumun beklenen .jsonl transkript yolu (var/yok bakılmaz)."""
    if not cli or not cwd:
        return None
    return projects_dir() / sanitize_cwd(cwd) / f"{cli}.jsonl"


def session_extras_dir(cli: str, cwd: str):
    """Oturumun yan verileri (subagents/, tool-results/) için beklenen klasör."""
    if not cli or not cwd:
        return None
    return projects_dir() / sanitize_cwd(cwd) / cli


def transcript_has_owner_binding(path) -> bool:
    """Transkriptte `bridge-session` satırı (=> ownerAccountUuid) var mı?

    Claude masaüstü uygulaması bu satırlarda hesabı işaret eden UUID'ler
    görürse ve mevcut hesapla eşleşmiyorsa oturumu 'Session not found on disk'
    sayıyor. Bu tespit, kopyalarken transkriptin yeniden yazılması gerekip
    gerekmediğine karar veriyor.
    """
    if not path or not Path(path).is_file():
        return False
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for _ in range(100):
                line = f.readline()
                if not line:
                    break
                if '"ownerAccountUuid"' in line:
                    return True
    except Exception:
        pass
    return False


def _extract_owner_uuids(path):
    """Transkriptteki ilk bridge-session satırından (accountUuid, orgUuid)."""
    if not path or not Path(path).is_file():
        return None, None
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for _ in range(200):
                line = f.readline()
                if not line:
                    break
                if '"ownerAccountUuid"' not in line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                a = o.get("ownerAccountUuid")
                g = o.get("ownerOrganizationUuid")
                if a or g:
                    return a, g
    except Exception:
        pass
    return None, None


def clone_transcript_for_target(src_path, dst_path, src_cli, new_cli,
                                target_acct, target_org):
    """Transkripti hedef hesap için kopyala: sessionId ve owner UUID'lerini yeniden yaz.

    Kritik: Claude masaüstü uygulaması aynı .jsonl dosyasını farklı hesaplarda
    açarken transkript içindeki ownerAccountUuid'i kontrol ediyor. Bu yüzden
    hedef için AYRI bir .jsonl (yeni cliSessionId adıyla) üretiyoruz — kaynak
    hesap kendi orijinal dosyasını açmaya devam edebilir.
    """
    src = Path(src_path)
    dst = Path(dst_path)
    if not src.is_file():
        raise FileNotFoundError(str(src))
    dst.parent.mkdir(parents=True, exist_ok=True)
    src_acct, src_org = _extract_owner_uuids(src)
    reps = []
    if src_cli and new_cli and src_cli != new_cli:
        reps.append((src_cli, new_cli))
    if src_acct and target_acct and src_acct != target_acct:
        reps.append((src_acct, target_acct))
    if src_org and target_org and src_org != target_org:
        reps.append((src_org, target_org))
    if not reps:
        shutil.copy2(src, dst)
        return
    # Satır satır kopyala; UUID'ler satır içinde kalır, satır sınırını aşmaz.
    with open(src, "r", encoding="utf-8", errors="ignore") as fr, \
            open(dst, "w", encoding="utf-8", newline="\n") as fw:
        for line in fr:
            for old, new in reps:
                line = line.replace(old, new)
            fw.write(line)
    try:
        shutil.copystat(src, dst)
    except Exception:
        pass


def clone_extras_for_target(src_dir, dst_dir, src_cli, new_cli,
                            target_acct, target_org):
    """Oturumun yan klasörünü (subagents/, tool-results/) kopyala ve içindeki
    metin dosyalarında UUID'leri yeniden yaz. Yoksa sessizce geç."""
    src = Path(src_dir) if src_dir else None
    if not src or not src.is_dir():
        return
    dst = Path(dst_dir)
    src_acct, src_org = _extract_owner_uuids(src.parent / f"{src_cli}.jsonl")
    reps = []
    if src_cli and new_cli and src_cli != new_cli:
        reps.append((src_cli, new_cli))
    if src_acct and target_acct and src_acct != target_acct:
        reps.append((src_acct, target_acct))
    if src_org and target_org and src_org != target_org:
        reps.append((src_org, target_org))
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    if not reps:
        return
    for dp, _dn, fn in os.walk(dst):
        for name in fn:
            _remap_bytes(os.path.join(dp, name), reps)


def rewrite_target_code_record(dst_path, new_cli):
    """Kopyalanan local_*.json'daki cliSessionId'i yenile, bridgeSessionIds'i sıfırla.

    bridgeSessionIds bulut tarafında kaynak hesaba ait; hedef hesap onu
    çözemez. Boşaltmak, oturumu 'yerel-modda' açılabilir hale getirir.
    """
    p = Path(dst_path)
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            d = json.load(f)
    except Exception:
        return
    old_cli = d.get("cliSessionId")
    d["cliSessionId"] = new_cli
    d["bridgeSessionIds"] = []
    text = json.dumps(d, ensure_ascii=False)
    if old_cli and new_cli and old_cli != new_cli:
        text = text.replace(old_cli, new_cli)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def perform_copy(bases, session, rel, email_pair=None):
    """
    Bir oturumu tüm depolara kopyala. Cowork ise kayıt dosyasıyla birlikte
    yan klasörü (audit.jsonl, outputs, uploads, .claude ...) de kopyalar ve
    iç yol/UUID referanslarını hedef hesaba göre yeniden yazar (bkz. cowork_remap).

    Claude Code oturumu (kind='code') hedef hesap için tam ayrıştırılır:
      • Transkriptte ownerAccountUuid varsa yeni bir cliSessionId üretilir ve
        transkriptin owner UUID'leri hedef hesap/organizasyon ile yeniden yazılır.
      • Kaynak hesabın .jsonl dosyası yerinde kalır; hedef kendi kopyasını kullanır.
      • Aksi halde (yerel-only oturum) klasik davranışa geri düşülür: sadece kayıt
        dosyası kopyalanır, transkript hedef ile paylaşılır.
    """
    written, errs = mirror_write(bases, session["path"], rel)
    if session.get("kind") == "cowork":
        src_dir = session.get("folder")
        reps = cowork_replacements(session, rel, email_pair)
        rel_dir = rel.with_suffix("")
        for base in bases:
            dst_dir = base / rel_dir
            if src_dir and Path(src_dir).is_dir():
                try:
                    if dst_dir.exists():
                        shutil.rmtree(dst_dir)
                    shutil.copytree(src_dir, dst_dir)
                except Exception as e:
                    errs.append(f"{dst_dir} ({e})")
            if reps:
                cowork_remap(base / rel, dst_dir, reps)
        return written, errs

    # Claude Code oturumu
    src_cli = session.get("cli")
    cwd = session.get("cwd")
    src_transcript = session.get("transcript")
    if not src_transcript:
        src_transcript = transcript_path_for(src_cli, cwd)
    needs_owner_rewrite = transcript_has_owner_binding(src_transcript)
    if needs_owner_rewrite and src_transcript and Path(src_transcript).is_file():
        # Hedef hesap/organizasyon UUID'leri rel yolundan çözülür:
        #   rel = <acct>/<org>/local_*.json
        target_acct = rel.parts[0] if len(rel.parts) >= 1 else None
        target_org = rel.parts[1] if len(rel.parts) >= 2 else None
        new_cli = str(uuid.uuid4())
        # Hedef için ayrı transkript
        dst_tr = transcript_path_for(new_cli, cwd)
        try:
            clone_transcript_for_target(src_transcript, dst_tr,
                                        src_cli, new_cli,
                                        target_acct, target_org)
        except Exception as e:
            errs.append(f"transcript clone: {dst_tr} ({e})")
        # Varsa yan klasör (subagents, tool-results)
        try:
            src_extras = session_extras_dir(src_cli, cwd)
            dst_extras = session_extras_dir(new_cli, cwd)
            if src_extras and Path(src_extras).is_dir() and dst_extras:
                clone_extras_for_target(src_extras, dst_extras,
                                        src_cli, new_cli,
                                        target_acct, target_org)
        except Exception as e:
            errs.append(f"extras clone: {e}")
        # Her yazılan local_*.json'un cliSessionId'ini yenile
        for dst_rec in written:
            try:
                rewrite_target_code_record(dst_rec, new_cli)
            except Exception as e:
                errs.append(f"record rewrite: {dst_rec} ({e})")
    return written, errs


# -------------------------------------------------------------------
# BOZUK OTURUM TESPİTİ / ORPHAN CLEANUP
# -------------------------------------------------------------------


def session_is_broken(session) -> bool:
    """Oturumun transkripti diskte var mı? code için beklenen path'e bakılır;
    cowork için yan klasör kontrol edilir."""
    if session.get("kind") == "cowork":
        d = session.get("folder")
        return not (d and Path(d).is_dir())
    tp = session.get("transcript")
    if tp and Path(tp).is_file():
        return False
    # tindex sadece stem üzerinden eşleştirir; asıl beklenen yol kontrol edilir
    expected = transcript_path_for(session.get("cli"), session.get("cwd"))
    return not (expected and Path(expected).is_file())


def find_broken_sessions(bases, kind: str, email_map=None):
    """Tüm hesaplarda transkripti bulunmayan (bozuk) oturumları listeler."""
    email_map = email_map or {}
    tindex = build_transcript_index() if kind == "code" else {}
    results = []
    for base in bases:
        accounts = load_accounts(base, tindex, kind, email_map)
        for acc in accounts:
            for s in acc["sessions"]:
                if session_is_broken(s):
                    results.append({"base": base, "account": acc, "session": s})
    return results


def perform_broken_cleanup(bases, entries):
    """Verilen bozuk kayıtları tüm depolardan sil (kayıt + varsa cowork yan
    klasörü). (silinen sayısı, hata listesi) döndürür."""
    rels = []
    seen = set()
    for e in entries:
        s = e["session"]
        key = str(s["rel"])
        if key in seen:
            continue
        seen.add(key)
        rels.append((s["rel"], s.get("kind")))
    removed = 0
    errs = []
    for rel, kind in rels:
        for base in bases:
            p = base / rel
            try:
                if p.exists():
                    p.unlink()
                    removed += 1
            except Exception as ex:
                errs.append(f"{p} ({ex})")
            if kind == "cowork":
                d = base / rel.with_suffix("")
                try:
                    if d.exists():
                        shutil.rmtree(d)
                except Exception as ex:
                    errs.append(f"{d} ({ex})")
    return removed, errs


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
    print(tr.t("type_opt_bridge"))
    print(tr.t("type_opt_pack"))
    while True:
        sel = ask(tr.t("prompt_type"))
        if sel == "1":
            return "code"
        if sel == "2":
            return "cowork"
        if sel == "3":
            return "bridge"
        if sel == "4":
            return "pack"
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


def cleanup_main():
    """Bozuk kayıtları (transkripti eksik) her iki depoda da tespit edip silme."""
    email_map = build_email_index()
    total_removed = 0
    for kind in ("code", "cowork"):
        bases = existing_bases(kind)
        if not bases:
            continue
        print("\n" + tr.t("broken_hdr", name=tr.t("type_" + kind)))
        tindex = build_transcript_index() if kind == "code" else {}
        accounts = load_accounts(bases[0], tindex, kind, email_map)
        total = sum(len(a["sessions"]) for a in accounts)
        broken = find_broken_sessions(bases, kind, email_map)
        print(tr.t("broken_summary", total=total, broken=len(broken)))
        if not broken:
            print(tr.t("broken_none"))
            continue
        for i, e in enumerate(broken, 1):
            s = e["session"]
            print(tr.t("broken_line", i=i, acct=account_who(e["account"]),
                       title=s["title"], cwd=s["cwd"], t=fmt_time(s["last"])))
        if yes(ask("\n" + tr.t("broken_ask"))):
            n, errs = perform_broken_cleanup(bases, broken)
            for msg in errs:
                print(f"    [!] {msg}")
            print(tr.t("broken_done", n=n))
            total_removed += n
    return total_removed


def _pick_numbers(count, prompt_key):
    while True:
        sel = ask(tr.t(prompt_key))
        parts = [p.strip() for p in sel.replace(" ", ",").split(",") if p.strip()]
        if parts and all(p.isdigit() and 1 <= int(p) <= count for p in parts):
            return [int(p) - 1 for p in dict.fromkeys(parts)]
        print(tr.t("invalid"))


def bridge_main():
    """Claude Code ⇄ Codex oturum dönüştürme (bkz. csbridge.py)."""
    # Betik olarak çalışırken csbridge'in 'import csm'i bu modülü yeniden yüklemesin.
    sys.modules.setdefault("csm", sys.modules[__name__])
    import csbridge

    print("\n" + tr.t("br_choose_dir"))
    print(tr.t("br_opt_c2x"))
    print(tr.t("br_opt_x2c"))
    while True:
        sel = ask(tr.t("br_prompt_dir"))
        if sel in ("1", "2"):
            break
        print(tr.t("invalid"))
    to_codex = sel == "1"
    dir_label = tr.t("br_dir_c2x" if to_codex else "br_dir_x2c")
    print("\n" + tr.t("br_close_apps"))
    print(tr.t("br_about"))

    email_map = build_email_index()
    if to_codex:
        side, where = "Claude Code", projects_dir()
        sessions = csbridge.list_claude_sessions(email_map)
    else:
        side, where = "Codex", csbridge.codex_sessions_dir()
        sessions = csbridge.list_codex_sessions()
    if not sessions:
        print("\n" + tr.t("br_no_sessions", side=side, p=where))
        sys.exit(1)

    flt = ask("\n" + tr.t("br_filter_q")).lower()
    shown = [s for s in sessions
             if not flt or flt in s["title"].lower() or flt in str(s["cwd"]).lower()]
    if not shown:
        print(tr.t("no_sessions"))
        return
    limit = 40
    print("\n" + tr.t("br_list_hdr", side=side, n=len(shown)))
    for i, s in enumerate(shown[:limit], 1):
        title = s["title"] + (f"  <{s['email']}>" if s.get("email") else "")
        print(tr.t("br_line", i=i, title=title, cwd=s["cwd"], t=fmt_time(s["last"]),
                   size=human_size(s["size"])))
    if len(shown) > limit:
        print(tr.t("br_more", n=len(shown) - limit))
    picked = [shown[i] for i in _pick_numbers(min(len(shown), limit), "br_prompt_pick")]

    register_codex = False
    account = None
    if to_codex:
        register_codex = yes(ask("\n" + tr.t("br_register_codex_q")))
        if not register_codex:
            print(tr.t("br_no_codex_reg_warn"))
    else:
        bases = existing_bases("code")
        accounts = load_accounts(bases[0], {}, "code", email_map) if bases else []
        if accounts:
            print("\n" + tr.t("br_account_hdr"))
            print(tr.t("br_account_none"))
            for i, acc in enumerate(accounts, 1):
                print(tr.t("account_line", i=i, id=account_who(acc),
                           n=len(acc["sessions"]), t=fmt_time(acc["last"])))
            while True:
                sel = ask(tr.t("br_prompt_account"))
                if sel.isdigit() and 0 <= int(sel) <= len(accounts):
                    account = accounts[int(sel) - 1] if int(sel) else None
                    break
                print(tr.t("invalid"))
        if account is None:
            print(tr.t("br_no_account_warn"))

    print("\n" + tr.t("br_summary", dir=dir_label, n=len(picked)))
    for s in picked:
        print(f"  - {s['title']}  ({s['cwd']})")
    if not yes(ask("\n" + tr.t("proceed_q"))):
        print(tr.t("cancelled"))
        return

    ok = failed = 0
    for s in picked:
        try:
            if to_codex:
                r = csbridge.claude_to_codex(s, register_app=register_codex)
                new_id = r["thread_id"]
            else:
                r = csbridge.codex_to_claude(s, account=account)
                new_id = r["session_id"]
        except Exception as e:
            print(tr.t("br_fail", title=s["title"], e=e))
            failed += 1
            continue
        print("\n" + tr.t("br_ok", title=s["title"], p=r["path"], id=new_id,
                          turns=r["turns"], items=r["items"]))
        if to_codex:
            print(tr.t("br_reg_codex_yes") if r["registered"] else tr.t("br_reg_codex_no", id=new_id))
        elif r["records"]:
            print(tr.t("br_reg_claude", n=len(r["records"])))
        for w in r["warn"]:
            print(f"    [!] {w}")
        ok += 1

    print("\n" + tr.t("br_done", c=ok, f=failed))
    print(tr.t("br_hint_codex" if to_codex else "br_hint_claude"))


def _load_pack():
    """csbridge/cspack'i yükler (betik olarak çalışırken csm'yi ikinci kez yüklemeden)."""
    sys.modules.setdefault("csm", sys.modules[__name__])
    import cspack
    return cspack


def all_sessions_for_pack(email_map=None):
    """Paketlenebilecek tüm oturumlar: Claude Code, Cowork ve Codex."""
    import csbridge
    cspack = _load_pack()
    email_map = email_map or build_email_index()
    items = []
    for kind in ("code", "cowork"):
        bases = existing_bases(kind)
        if not bases:
            continue
        tindex = build_transcript_index() if kind == "code" else {}
        for acc in load_accounts(bases[0], tindex, kind, email_map):
            for s in acc["sessions"]:
                items.append(cspack.make_item(kind, s, acc))
    for s in csbridge.list_codex_sessions():
        items.append(cspack.make_item("codex", s))
    items.sort(key=lambda it: it["session"].get("last") or 0, reverse=True)
    return items


def _pack_item_size(item, cspack):
    # Listede hızlı boyut; tam hesap paketleme öncesi yapılır.
    return cspack.estimate_size([item], quick=True)


def _print_pack_list(items, cspack, limit=40):
    print("\n" + tr.t("pk_list_hdr", n=len(items)))
    for i, it in enumerate(items[:limit], 1):
        s, acc = it["session"], it.get("account")
        print(tr.t("pk_line", i=i, kind=tr.t("type_" + it["kind"]) if it["kind"] != "codex" else "Codex",
                   title=s.get("title") or "(…)",
                   acc=f"  <{account_who(acc)}>" if acc else "",
                   cwd=s.get("cwd") or "?", t=fmt_time(s.get("last") or 0),
                   size=human_size(_pack_item_size(it, cspack))))
    if len(items) > limit:
        print(tr.t("br_more", n=len(items) - limit))


def pack_export_main(cspack):
    items = all_sessions_for_pack()
    if not items:
        print(tr.t("pk_no_sessions"))
        return
    flt = ask("\n" + tr.t("br_filter_q")).lower()
    if flt:
        items = [it for it in items
                 if flt in (it["session"].get("title") or "").lower()
                 or flt in str(it["session"].get("cwd") or "").lower()]
        if not items:
            print(tr.t("no_sessions"))
            return
    _print_pack_list(items, cspack)
    picked = [items[i] for i in _pick_numbers(min(len(items), 40), "pk_prompt_pick")]
    include = set(cspack.DEFAULT_PARTS)
    if not yes(ask("\n" + tr.t("pk_all_q"))):
        include -= {"memory", "scratch", "extras", "codex_extras"}
    size = cspack.estimate_size(picked, include)
    default = str(Path.cwd() / cspack.default_bundle_name(picked))
    out = ask(tr.t("pk_out_q", d=default)) or default
    print(tr.t("pk_exporting", size=human_size(size)))
    cspack.export_bundle(picked, out, include=include, progress=lambda m: print("  " + m))
    print("\n" + tr.t("pk_export_done", p=out, size=human_size(file_size(Path(out)))))
    print(tr.t("pk_export_hint"))


def pack_import_main(cspack, path=None):
    path = path or ask("\n" + tr.t("pk_bundle_q"))
    path = Path(path.strip().strip('"'))
    try:
        man = cspack.read_bundle(path)
    except Exception as e:
        print(tr.t("pk_bundle_bad", e=e))
        return
    src = man.get("source") or {}
    entries = man.get("sessions", [])
    print("\n" + tr.t("pk_bundle_info", p=path, user=src.get("user"), host=src.get("host"),
                      platform=src.get("platform"), n=len(entries),
                      t=fmt_time(man.get("created_at") or 0)))
    print("\n" + tr.t("pk_list_hdr", n=len(entries)))
    for i, e in enumerate(entries, 1):
        print(tr.t("pk_line", i=i,
                   kind=tr.t("type_" + e["kind"]) if e["kind"] != "codex" else "Codex",
                   title=e.get("title") or "(…)",
                   acc=f"  <{(e.get('account') or {}).get('email') or ''}>" if e.get("account") else "",
                   cwd=e.get("cwd") or "?", t=fmt_time(e.get("last") or 0),
                   size=human_size(cspack.bundle_entry_size(e))))
    sel = ask("\n" + tr.t("pk_prompt_pick_in")).strip()
    if sel:
        parts = [p.strip() for p in sel.replace(" ", ",").split(",") if p.strip()]
        if not all(p.isdigit() and 1 <= int(p) <= len(entries) for p in parts):
            print(tr.t("invalid"))
            return
        chosen = [entries[int(p) - 1] for p in dict.fromkeys(parts)]
    else:
        chosen = entries

    cwd_map = cspack.default_cwd_map(man)
    needs_map = sorted({e.get("cwd") for e in chosen if e.get("cwd")})
    if needs_map:
        print("\n" + tr.t("pk_map_hdr"))
        for c in needs_map:
            got = ask(tr.t("pk_map_q", src=c, dst=cwd_map.get(c, c))).strip().strip('"')
            if got:
                cwd_map[c] = got

    account = None
    if any(e["kind"] in ("code", "cowork") for e in chosen):
        accounts = cspack.import_accounts(build_email_index())
        print("\n" + tr.t("br_account_hdr"))
        print(tr.t("br_account_none"))
        for i, acc in enumerate(accounts, 1):
            print(tr.t("account_line", i=i, id=account_who(acc),
                       n=len(acc["sessions"]), t=fmt_time(acc["last"])))
        while True:
            s = ask(tr.t("br_prompt_account"))
            if s.isdigit() and 0 <= int(s) <= len(accounts):
                account = accounts[int(s) - 1] if int(s) else None
                break
            print(tr.t("invalid"))
        if account is None:
            print(tr.t("br_no_account_warn"))
    overwrite_mem = yes(ask("\n" + tr.t("pk_mem_q")))
    register_codex = True
    if any(e["kind"] == "codex" for e in chosen):
        register_codex = yes(ask(tr.t("pk_reg_codex_q")))

    print("\n" + tr.t("br_summary", dir=tr.t("pk_opt_import").strip(), n=len(chosen)))
    if not yes(ask("\n" + tr.t("proceed_q"))):
        print(tr.t("cancelled"))
        return

    def on_conflict(entry, conflicts):
        return "overwrite" if yes(ask(tr.t("pk_conflict_q", title=entry.get("title")))) else "skip"

    ok = skipped = failed = 0
    for e in chosen:
        acc = account
        if acc is not None and e["kind"] in ("code", "cowork"):
            acc = cspack.account_for(e["kind"], account["id"], build_email_index())
        res = cspack.import_entry(path, e, account=acc if e["kind"] != "codex" else None,
                                  cwd_map=cwd_map, overwrite_memory=overwrite_mem,
                                  register_codex=register_codex, manifest=man,
                                  conflict_cb=on_conflict)
        if res["status"] == "failed":
            print(tr.t("pk_failed", title=e.get("title"), e="; ".join(res["warn"])))
            failed += 1
            continue
        if res["status"] == "skipped":
            print(tr.t("pk_skipped", title=e.get("title")))
            skipped += 1
            continue
        print("\n" + tr.t("pk_restored", title=e.get("title")))
        for p in res["paths"]:
            print(tr.t("pk_path", p=p))
        if res.get("skipped_memory"):
            print(tr.t("pk_mem_skipped", n=len(res["skipped_memory"])))
        for w in res["warn"]:
            print(f"    [!] {w}")
        ok += 1
    print("\n" + tr.t("pk_done", c=ok, s=skipped, f=failed))
    print(tr.t("pk_hint"))


def pack_main(mode=None, path=None):
    """Oturumları dosyaya yedekleme / dosyadan geri yükleme (bkz. cspack.py)."""
    cspack = _load_pack()
    print(tr.t("pk_about"))
    if mode is None:
        print("\n" + tr.t("pk_choose_mode"))
        print(tr.t("pk_opt_export"))
        print(tr.t("pk_opt_import"))
        while True:
            sel = ask(tr.t("pk_prompt_mode"))
            if sel in ("1", "2"):
                mode = "export" if sel == "1" else "import"
                break
            print(tr.t("invalid"))
    if mode == "export":
        pack_export_main(cspack)
    else:
        pack_import_main(cspack, path)


def main():
    argv = sys.argv[1:]
    if "--cleanup" in argv:
        cleanup_main()
        return
    if "--bridge" in argv:
        bridge_main()
        return
    if "--export" in argv:
        pack_main("export")
        return
    if "--import" in argv:
        i = argv.index("--import")
        pack_main("import", argv[i + 1] if i + 1 < len(argv) else None)
        return

    kind = choose_type()
    if kind == "bridge":
        bridge_main()
        return
    if kind == "pack":
        pack_main()
        return
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
    print(tr.t("broken_menu_hint"))
    source = choose_account(accounts, "role_source", require_sessions=True)
    picked = choose_sessions(source)
    # Bozuk transkriptli oturumları taşımaya izin verme (isteğe göre uyarı+onay)
    picked_ok = []
    for s in picked:
        if session_is_broken(s):
            if not yes(ask("\n" + tr.t("notr_warn"))):
                continue
        picked_ok.append(s)
    picked = picked_ok
    if not picked:
        print(tr.t("cancelled"))
        return
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
            written, werr = perform_copy(bases, s, rel, email_pair=(source.get("email"), target.get("email")))
            for e in werr:
                print(f"    [!] {e}")
            print(tr.t("r_overwritten", title=s["title"], n=len(written)))
            overwritten += 1
        else:
            written, werr = perform_copy(bases, s, rel, email_pair=(source.get("email"), target.get("email")))
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
