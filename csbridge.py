#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude Code ⇄ Codex köprüsü (csbridge.py)  /  Claude Code ⇄ Codex bridge
=======================================================================
Claude Code oturumlarını OpenAI Codex oturumuna ve Codex oturumlarını Claude
Code oturumuna dönüştürür. Kaynak dosyaya asla dokunulmaz; hedefte YENİ bir
oturum oluşturulur.

  Claude Code → Codex
    ~/.claude/projects/<proje>/<uuid>.jsonl
      → ~/.codex/sessions/YYYY/MM/DD/rollout-<zaman>-<uuidv7>.jsonl
      (+ isteğe bağlı: Codex uygulamasının thread listesi / state_*.sqlite)

  Codex → Claude Code
    ~/.codex/sessions/.../rollout-*.jsonl
      → ~/.claude/projects/<proje>/<uuid>.jsonl
      (+ isteğe bağlı: Claude masaüstü hesabına local_*.json kaydı)

Araç çağrıları ve sonuçları iki taraf arasında birebir taşınamaz (araç adları
ve şemaları farklı). Codex'in kendi Claude içe aktarıcısı gibi bunlar metne
çevrilir: [external_agent_tool_call: Ad] … / [external_agent_tool_result] …
Böylece model geçmişi okuyabilir, sohbete kaldığı yerden devam edilebilir.

Çalıştırma / Run:
    py csm.py --bridge        (terminal akışı / interactive CLI)
    py csmui.py               ("Claude ⇄ Codex" sekmesi / GUI tab)

Ortam değişkenleri / Env vars:
    CODEX_HOME=<yol>          Codex veri kökü (varsayılan ~/.codex)
    CSM_CODEX=<yol>           aynı, bu araca özel / same, tool-specific override
"""

import os
import re
import sys
import json
import time
import uuid
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
import csm  # noqa: E402

IMPORT_MARKER = "<EXTERNAL SESSION IMPORTED>"
CLAUDE_MODEL_FALLBACK = "claude-opus-5"
CLAUDE_VERSION_FALLBACK = "2.1.0"
CODEX_CLI_VERSION_FALLBACK = "0.147.0"
# Tek bir araç girdisi/çıktısı için üst sınır (dev çıktılar bağlamı şişirmesin)
MAX_BLOCK_CHARS = 50_000
UNSUPPORTED_IMAGE = "[external unsupported block: image]"


# -------------------------------------------------------------------
# YOLLAR / PATHS
# -------------------------------------------------------------------

def codex_home() -> Path:
    if csm.IS_DEMO:
        return csm.SCRIPT_DIR / "sample-data" / "codex"
    env = os.environ.get("CSM_CODEX") or os.environ.get("CODEX_HOME")
    return Path(env) if env else (Path.home() / ".codex")


def codex_sessions_dir() -> Path:
    return codex_home() / "sessions"


def codex_state_db():
    """En yüksek sürümlü state_<n>.sqlite (Codex uygulamasının thread listesi)."""
    best, best_n = None, -1
    for p in codex_home().glob("state_*.sqlite"):
        m = re.fullmatch(r"state_(\d+)\.sqlite", p.name)
        if m and int(m.group(1)) > best_n:
            best, best_n = p, int(m.group(1))
    return best


def claude_project_dir_name(cwd: str) -> str:
    """Claude Code'un cwd -> proje klasörü adı: harf/rakam dışı her karakter '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", cwd or "")


def claude_project_dir_for(cwd: str) -> Path:
    """cwd için transkript klasörü. Mevcut bir klasör aynı cwd'yi kullanıyorsa onu seç
    (uzun yollarda Claude'un kısaltma/hash davranışına karşı güvenli)."""
    pdir = csm.projects_dir()
    cand = pdir / claude_project_dir_name(cwd)
    if cand.is_dir():
        return cand
    if pdir.is_dir() and cwd:
        want = os.path.normcase(os.path.normpath(cwd))
        for d in pdir.iterdir():
            if not d.is_dir():
                continue
            for f in d.glob("*.jsonl"):
                got = _claude_first_cwd(f)
                if got and os.path.normcase(os.path.normpath(got)) == want:
                    return d
                break  # klasör başına bir dosya yeterli
    return cand


def _claude_first_cwd(path, max_lines=50):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for _ in range(max_lines):
                line = f.readline()
                if not line:
                    break
                if '"cwd"' not in line:
                    continue
                try:
                    c = json.loads(line).get("cwd")
                except Exception:
                    continue
                if c:
                    return c
    except Exception:
        pass
    return None


# -------------------------------------------------------------------
# ZAMAN / KİMLİK — TIME / IDS
# -------------------------------------------------------------------

_ISO_RE = re.compile(r"(\d{4})-(\d\d)-(\d\d)[T ](\d\d):(\d\d):(\d\d)(?:\.(\d+))?")


def parse_iso_ms(s):
    """'2026-09-08T20:29:01.383Z' (veya 7 haneli kesir) -> epoch ms. UTC kabul edilir."""
    if not isinstance(s, str):
        return None
    m = _ISO_RE.match(s)
    if not m:
        return None
    y, mo, d, h, mi, se, frac = m.groups()
    try:
        dt = datetime(int(y), int(mo), int(d), int(h), int(mi), int(se), tzinfo=timezone.utc)
    except ValueError:
        return None
    ms = int((frac or "0")[:3].ljust(3, "0"))
    return int(dt.timestamp()) * 1000 + ms


def iso_ms(ms) -> str:
    dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(ms) % 1000:03d}Z"


def now_ms() -> int:
    return int(time.time() * 1000)


def uuid7(ms=None) -> str:
    """Codex thread kimlikleri UUIDv7'dir (zamana göre sıralanabilir)."""
    ms = now_ms() if ms is None else int(ms)
    rand = int.from_bytes(os.urandom(10), "big")
    val = ((ms & ((1 << 48) - 1)) << 80) | (0x7 << 76) \
        | ((rand >> 68) & 0xFFF) << 64 | (0b10 << 62) | (rand & ((1 << 62) - 1))
    return str(uuid.UUID(int=val))


# -------------------------------------------------------------------
# METİN YARDIMCILARI / TEXT HELPERS
# -------------------------------------------------------------------

def _cap(text: str) -> str:
    if len(text) <= MAX_BLOCK_CHARS:
        return text
    return text[:MAX_BLOCK_CHARS] + f"\n…[truncated {len(text) - MAX_BLOCK_CHARS} chars]"


def _one_line(text: str, limit: int = 140) -> str:
    t = " ".join((text or "").split()).strip()
    return t[:limit] + ("…" if len(t) > limit else "")


def _json_compact(obj) -> str:
    if isinstance(obj, str):
        return obj
    try:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return str(obj)


def fmt_tool_call(name: str, body: str) -> str:
    return f"[external_agent_tool_call: {name}]\n{_cap(body)}\n[/external_agent_tool_call]"


def fmt_tool_result(body: str, is_error: bool = False) -> str:
    head = "[external_agent_tool_result error]" if is_error else "[external_agent_tool_result]"
    body = _cap(body or "")
    return f"{head}\n{body}\n[/external_agent_tool_result]" if body else \
        f"{head}\n[/external_agent_tool_result]"


def fmt_reasoning(body: str) -> str:
    return f"[external_agent_reasoning]\n{_cap(body)}\n[/external_agent_reasoning]"


def _claude_tool_input(inp) -> str:
    """Codex içe aktarıcısının biçimi: kabuk araçları için description+command, diğerleri JSON."""
    if isinstance(inp, dict) and "command" in inp and \
            set(inp) <= {"command", "description", "timeout", "run_in_background"}:
        lines = []
        if inp.get("description"):
            lines.append(f"description: {inp['description']}")
        lines.append(f"command: {inp['command']}")
        return "\n".join(lines)
    return "input: " + _json_compact(inp)


def _claude_block_text(content) -> str:
    """tool_result içeriği: str veya [{type:text}, {type:image}] listesi."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts = []
    if isinstance(content, list):
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text":
                parts.append(b.get("text") or "")
            elif b.get("type") == "image":
                parts.append(UNSUPPORTED_IMAGE)
            elif b.get("type") == "tool_reference":
                parts.append(f"[tool: {b.get('tool_name', '?')}]")
    return "\n".join(p for p in parts if p)


# -------------------------------------------------------------------
# CLAUDE CODE TRANSKRİPTİ OKUMA / READ CLAUDE TRANSCRIPT
# -------------------------------------------------------------------

def read_claude_transcript(path):
    """
    Claude Code .jsonl -> (meta, items)
      meta : {cwd, title, git_branch, first_ms, last_ms}
      items: [{"role": "user"|"assistant", "text": str, "ms": int}, ...]
    Yan zincirler (isSidechain), meta mesajlar ve sistem kayıtları atlanır.
    """
    meta = {"cwd": None, "title": None, "git_branch": None, "first_ms": None, "last_ms": None}
    items = []
    seen_any = False
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            t = o.get("type")
            if t == "custom-title" and o.get("customTitle"):
                meta["title"] = o["customTitle"]
                continue
            if t == "summary" and o.get("summary") and not meta["title"]:
                meta["title"] = o["summary"]
                continue
            if t not in ("user", "assistant"):
                continue
            if o.get("isSidechain") or o.get("isMeta"):
                continue
            if o.get("isCompactSummary") and seen_any:
                continue  # önceki mesajlar zaten dosyada
            if not meta["cwd"] and o.get("cwd"):
                meta["cwd"] = o["cwd"]
            if not meta["git_branch"] and o.get("gitBranch"):
                meta["git_branch"] = o["gitBranch"]
            ms = parse_iso_ms(o.get("timestamp")) or 0
            if ms:
                meta["first_ms"] = meta["first_ms"] or ms
                meta["last_ms"] = ms
            content = (o.get("message") or {}).get("content")

            if t == "user":
                if isinstance(content, str):
                    if content.strip():
                        items.append({"role": "user", "text": content, "ms": ms})
                        seen_any = True
                    continue
                human = []
                for b in content or []:
                    if not isinstance(b, dict):
                        continue
                    bt = b.get("type")
                    if bt == "tool_result":
                        items.append({"role": "assistant", "ms": ms,
                                      "text": fmt_tool_result(_claude_block_text(b.get("content")),
                                                              bool(b.get("is_error")))})
                    elif bt == "text" and (b.get("text") or "").strip():
                        human.append(b["text"])
                    elif bt == "image":
                        human.append(UNSUPPORTED_IMAGE)
                    elif bt == "document":
                        human.append("[external unsupported block: document]")
                if human:
                    items.append({"role": "user", "text": "\n\n".join(human), "ms": ms})
                    seen_any = True
                continue

            # assistant
            if isinstance(content, str):
                if content.strip():
                    items.append({"role": "assistant", "text": content, "ms": ms})
                seen_any = True
                continue
            for b in content or []:
                if not isinstance(b, dict):
                    continue
                bt = b.get("type")
                if bt == "text" and (b.get("text") or "").strip():
                    items.append({"role": "assistant", "text": b["text"], "ms": ms})
                elif bt == "thinking" and (b.get("thinking") or "").strip():
                    items.append({"role": "assistant", "text": fmt_reasoning(b["thinking"]), "ms": ms})
                elif bt in ("tool_use", "server_tool_use"):
                    items.append({"role": "assistant", "ms": ms,
                                  "text": fmt_tool_call(b.get("name") or "tool",
                                                        _claude_tool_input(b.get("input")))})
                elif bt and bt.endswith("_tool_result"):
                    items.append({"role": "assistant", "ms": ms,
                                  "text": fmt_tool_result(_claude_block_text(b.get("content")))})
            seen_any = True
    return meta, items


# -------------------------------------------------------------------
# CODEX ROLLOUT OKUMA / READ CODEX ROLLOUT
# -------------------------------------------------------------------

def _codex_content_text(content, image_ok=True) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts = []
    for b in content if isinstance(content, list) else []:
        if not isinstance(b, dict):
            continue
        bt = b.get("type")
        if bt in ("input_text", "output_text", "text", "Text", "summary_text"):
            parts.append(b.get("text") or "")
        elif bt in ("input_image", "image") and image_ok:
            parts.append(UNSUPPORTED_IMAGE)
    return "\n".join(p for p in parts if p)


_AMBIENT_BLOCK_RE = re.compile(
    r"^\s*<([a-zA-Z_][\w-]*(?:context|instructions|state|reminder)[\w-]*)(?:\s[^>]*)?>.*?</\1>\s*",
    re.S | re.I)


def clean_user_text(text: str) -> str:
    """Kullanıcı mesajının başındaki otomatik bağlam bloklarını ayıkla
    (ör. <in-app-browser-context>…</in-app-browser-context> ## My request: …)."""
    t = text or ""
    while True:
        m = _AMBIENT_BLOCK_RE.match(t)
        if not m:
            break
        t = t[m.end():]
    t = re.sub(r"^\s*##\s*My request:\s*", "", t).strip()
    return t or (text or "").strip()


def _looks_injected(text: str) -> bool:
    """Codex'in modele eklediği bağlam blokları (gerçek kullanıcı mesajı değil)."""
    t = (text or "").strip()
    if t.startswith("# AGENTS.md instructions"):
        return True
    m = re.match(r"<([a-zA-Z_][\w-]*)[^>]*>", t)
    return bool(m and t.endswith(f"</{m.group(1)}>"))


def read_codex_rollout(path):
    """
    Codex rollout .jsonl -> (meta, items)
      meta : {id, cwd, title, git_branch, first_ms, last_ms, subagent}
      items: [{"role": "user"|"assistant", "text": str, "ms": int}, ...]
    Model geçmişi olan response_item kayıtları okunur; geliştirici/bağlam
    mesajları ve şifreli (encrypted) içerik atlanır.
    """
    meta = {"id": None, "cwd": None, "title": None, "git_branch": None,
            "first_ms": None, "last_ms": None, "subagent": False}
    real_user = []      # olay kayıtlarından gerçek kullanıcı metinleri
    raw = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            t = o.get("type")
            p = o.get("payload") or {}
            if t == "session_meta":
                meta["id"] = p.get("id") or p.get("session_id")
                meta["cwd"] = p.get("cwd")
                meta["git_branch"] = (p.get("git") or {}).get("branch")
                meta["subagent"] = isinstance(p.get("source"), dict)
                continue
            if t == "event_msg":
                pt = p.get("type")
                if pt == "user_message" and p.get("message"):
                    real_user.append(p["message"].strip())
                elif pt == "item_completed":
                    it = p.get("item") or {}
                    if it.get("type") == "UserMessage":
                        txt = _codex_content_text(it.get("content"), image_ok=False).strip()
                        if txt:
                            real_user.append(txt)
                continue
            if t == "response_item":
                raw.append((parse_iso_ms(o.get("timestamp")) or 0, p))

    real_set = set(real_user)
    items = []
    for ms, p in raw:
        if ms:
            meta["first_ms"] = meta["first_ms"] or ms
            meta["last_ms"] = ms
        pt = p.get("type")
        if pt == "message":
            role = p.get("role")
            text = _codex_content_text(p.get("content")).strip()
            if not text:
                continue
            if role == "user":
                if real_set:
                    plain = _codex_content_text(p.get("content"), image_ok=False).strip()
                    # Birebir eşleşme; ek iliştirilmiş mesajlar için uzun metinlerde kapsama
                    if plain not in real_set and not any(len(r) >= 20 and r in plain for r in real_set):
                        continue
                elif _looks_injected(text):
                    continue
                items.append({"role": "user", "text": clean_user_text(text), "ms": ms})
            elif role == "assistant":
                items.append({"role": "assistant", "text": text, "ms": ms})
            # developer/system: atla
        elif pt == "reasoning":
            summ = _codex_content_text(p.get("summary")).strip()
            if summ:
                items.append({"role": "assistant", "text": fmt_reasoning(summ), "ms": ms})
        elif pt in ("function_call", "custom_tool_call"):
            name = p.get("name") or "tool"
            if p.get("namespace"):
                name = f"{p['namespace']}.{name}"
            body = p.get("arguments") if pt == "function_call" else p.get("input")
            items.append({"role": "assistant", "ms": ms,
                          "text": fmt_tool_call(name, "input: " + _json_compact(body))})
        elif pt in ("function_call_output", "custom_tool_call_output"):
            out = p.get("output")
            if isinstance(out, dict):
                out = out.get("content") if "content" in out else _json_compact(out)
            items.append({"role": "assistant", "ms": ms,
                          "text": fmt_tool_result(_codex_content_text(out))})
        elif pt in ("local_shell_call", "web_search_call", "image_generation_call", "tool_search_call"):
            body = p.get("action") if p.get("action") is not None else \
                {k: v for k, v in p.items() if k not in ("type", "id", "encrypted_content")}
            items.append({"role": "assistant", "ms": ms,
                          "text": fmt_tool_call(pt[:-len("_call")], "input: " + _json_compact(body))})
        # agent_message (alt ajan iletişimi, şifreli) ve diğerleri atlanır
    first = next((i["text"] for i in items if i["role"] == "user"), "")
    meta["title"] = _one_line(first, 80) if first else None
    return meta, items


# -------------------------------------------------------------------
# LİSTELEME / LISTING
# -------------------------------------------------------------------

def _claude_scan_head(path, max_lines=400):
    """Hızlı ön tarama: cwd, başlık, ilk kullanıcı mesajı."""
    cwd = title = first = None
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for _ in range(max_lines):
                line = f.readline()
                if not line:
                    break
                if not any(k in line for k in ('"cwd"', '"user"', '"custom-title"', '"summary"')):
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                t = o.get("type")
                if t == "custom-title" and o.get("customTitle"):
                    title = o["customTitle"]
                elif t == "summary" and o.get("summary") and not title:
                    title = o["summary"]
                if not cwd and o.get("cwd"):
                    cwd = o["cwd"]
                if first is None and t == "user" and not o.get("isMeta") and not o.get("isSidechain"):
                    c = (o.get("message") or {}).get("content")
                    if isinstance(c, str) and c.strip():
                        first = c
                    elif isinstance(c, list) and not any(
                            isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
                        txt = [b.get("text") for b in c
                               if isinstance(b, dict) and b.get("type") == "text" and b.get("text")]
                        if txt:
                            first = "\n".join(txt)
                if cwd and title and first:
                    break
    except Exception:
        pass
    return cwd, title, first


def _claude_desktop_index():
    """cliSessionId -> {title, account, last} (Claude masaüstü kayıtlarından)."""
    idx = {}
    for base in csm.existing_bases("code"):
        for p in base.rglob("local_*.json"):
            e = csm.load_entry(p)
            if not e or not e.get("cliSessionId"):
                continue
            try:
                acc = p.relative_to(base).parts[0]
            except Exception:
                acc = None
            cur = idx.get(e["cliSessionId"])
            if cur is None or (e.get("lastActivityAt") or 0) > cur["last"]:
                idx[e["cliSessionId"]] = {"title": e.get("title"), "account": acc, "cwd": e.get("cwd"),
                                          "last": e.get("lastActivityAt") or 0}
        break  # depolar aynalı; ilki yeterli
    return idx


def list_claude_sessions(email_map=None):
    """~/.claude/projects altındaki tüm Claude Code transkriptleri (yeniden eskiye)."""
    email_map = email_map or {}
    pdir = csm.projects_dir()
    if not pdir.is_dir():
        return []
    desk = _claude_desktop_index()
    out = []
    for p in pdir.glob("*/*.jsonl"):
        try:
            st = p.stat()
        except Exception:
            continue
        cwd, title, first = _claude_scan_head(p)
        if not first and not title:
            continue  # boş / yalnızca kuyruk kaydı olan dosyalar
        d = desk.get(p.stem) or {}
        acc = d.get("account")
        out.append({
            "side": "claude", "path": p, "id": p.stem, "cwd": cwd or d.get("cwd") or "?",
            "title": d.get("title") or title or _one_line(first or "", 80) or p.stem,
            "first": first or "", "last": int(st.st_mtime * 1000), "size": st.st_size,
            "account": acc, "email": email_map.get(acc) if acc else None,
        })
    out.sort(key=lambda s: s["last"], reverse=True)
    return out


def _codex_thread_names():
    names = {}
    p = codex_home() / "session_index.jsonl"
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if o.get("id") and o.get("thread_name"):
                    names[o["id"]] = o["thread_name"]
    except Exception:
        pass
    return names


def _codex_db_threads():
    """Codex uygulamasının thread tablosu (salt okunur). id -> satır sözlüğü."""
    db = codex_state_db()
    if not db:
        return {}
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=2)
        con.row_factory = sqlite3.Row
        rows = {r["id"]: dict(r) for r in con.execute("SELECT * FROM threads")}
        con.close()
        return rows
    except Exception:
        return {}


def _strip_verbatim(p):
    return p[4:] if isinstance(p, str) and p.startswith("\\\\?\\") else p


def _codex_scan_head(path, max_lines=300):
    """session_meta + ilk gerçek kullanıcı mesajı."""
    meta, first = None, None
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for i in range(max_lines):
                line = f.readline()
                if not line:
                    break
                if i > 0 and '"user_message"' not in line and '"UserMessage"' not in line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                p = o.get("payload") or {}
                if o.get("type") == "session_meta":
                    meta = p
                elif p.get("type") == "user_message" and p.get("message"):
                    first = p["message"]
                elif p.get("type") == "item_completed" and (p.get("item") or {}).get("type") == "UserMessage":
                    first = _codex_content_text(p["item"].get("content"), image_ok=False) or None
                if first:
                    break
    except Exception:
        pass
    return meta, first


_ROLLOUT_ID_RE = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$")


def list_codex_sessions():
    """~/.codex/sessions altındaki ana (alt ajan / arşiv olmayan) Codex oturumları."""
    sdir = codex_sessions_dir()
    if not sdir.is_dir():
        return []
    names = _codex_thread_names()
    db = _codex_db_threads()
    out = []
    for p in sdir.rglob("rollout-*.jsonl"):
        try:
            st = p.stat()
        except Exception:
            continue
        m = _ROLLOUT_ID_RE.search(p.name)
        tid = m.group(1) if m else p.stem
        row = db.get(tid)
        if row:
            if row.get("agent_path") or str(row.get("source") or "").startswith("{"):
                continue  # alt ajan
            if row.get("archived"):
                continue
            cwd = _strip_verbatim(row.get("cwd")) or "?"
            first = row.get("first_user_message") or row.get("preview") or ""
            title = names.get(tid) or row.get("name") or row.get("title") or first
            last = row.get("updated_at_ms") or (row.get("updated_at") or 0) * 1000
        else:
            meta, first = _codex_scan_head(p)
            if not meta or isinstance(meta.get("source"), dict):
                continue
            cwd = meta.get("cwd") or "?"
            first = first or ""
            title = names.get(tid) or first
            last = int(st.st_mtime * 1000)
        first = clean_user_text(first)
        title = clean_user_text(title)
        if not (title or first):
            continue
        out.append({
            "side": "codex", "path": p, "id": tid, "cwd": cwd,
            "title": _one_line(title, 80) or tid, "first": first,
            "last": int(last or st.st_mtime * 1000), "size": st.st_size,
        })
    out.sort(key=lambda s: s["last"], reverse=True)
    return out


# -------------------------------------------------------------------
# SÜRÜM / ŞABLON TESPİTİ — VERSION / TEMPLATE DETECTION
# -------------------------------------------------------------------

def _newest(paths, n):
    items = []
    for f in paths:
        try:
            items.append((f.stat().st_mtime, f))
        except Exception:
            pass
    items.sort(key=lambda x: x[0], reverse=True)
    return [f for _m, f in items[:n]]


def detect_claude_version() -> str:
    pdir = csm.projects_dir()
    if not pdir.is_dir():
        return CLAUDE_VERSION_FALLBACK
    for f in _newest(pdir.glob("*/*.jsonl"), 5):
        try:
            with open(f, "r", encoding="utf-8", errors="ignore") as fh:
                for _ in range(80):
                    line = fh.readline()
                    if not line:
                        break
                    m = re.search(r'"version"\s*:\s*"(\d+\.\d+\.\d+)"', line)
                    if m:
                        return m.group(1)
        except Exception:
            continue
    return CLAUDE_VERSION_FALLBACK


def detect_codex_template():
    """En yeni yerel Codex oturumundan (originator, cli_version, source, base_instructions)."""
    tpl = {"originator": "Codex Desktop", "cli_version": None, "source": "vscode",
           "base_instructions": None}
    sdir = codex_sessions_dir()
    candidates = []
    if sdir.is_dir():
        for day in _newest([d for d in sdir.glob("*/*/*") if d.is_dir()], 4):
            candidates += list(day.glob("rollout-*.jsonl"))
    for f in _newest(candidates, 20):
        try:
            with open(f, "r", encoding="utf-8", errors="ignore") as fh:
                o = json.loads(fh.readline())
        except Exception:
            continue
        p = o.get("payload") or {}
        if o.get("type") != "session_meta" or isinstance(p.get("source"), dict):
            continue
        if p.get("originator") not in ("Codex Desktop", "codex_cli_rs", "codex_vscode"):
            continue
        tpl.update(originator=p.get("originator"), cli_version=p.get("cli_version"),
                   source=p.get("source") or "vscode", base_instructions=p.get("base_instructions"))
        break
    if not tpl["cli_version"]:
        try:
            v = json.loads((codex_home() / "version.json").read_text(encoding="utf-8"))
            tpl["cli_version"] = v.get("latest_version")
        except Exception:
            pass
    tpl["cli_version"] = tpl["cli_version"] or CODEX_CLI_VERSION_FALLBACK
    return tpl


# -------------------------------------------------------------------
# CLAUDE CODE → CODEX
# -------------------------------------------------------------------

def _group_turns(items):
    """Her kullanıcı mesajı yeni bir tur başlatır."""
    turns = []
    for it in items:
        if it["role"] == "user" or not turns:
            turns.append([])
        turns[-1].append(it)
    return turns


def write_codex_rollout(items, cwd, title, git_branch=None, first_ms=None, tpl=None):
    """items -> yeni Codex rollout dosyası. (yol, thread_id) döndürür."""
    if not items:
        raise ValueError("empty session")
    cwd = cwd or str(Path.home())
    created = now_ms()
    tid = uuid7(created)
    local = datetime.fromtimestamp(created / 1000.0)
    day_dir = codex_sessions_dir() / local.strftime("%Y") / local.strftime("%m") / local.strftime("%d")
    path = day_dir / f"rollout-{local.strftime('%Y-%m-%dT%H-%M-%S')}-{tid}.jsonl"
    tpl = tpl or detect_codex_template()

    meta = {
        "session_id": tid, "id": tid, "timestamp": iso_ms(created), "cwd": cwd,
        "originator": tpl["originator"], "cli_version": tpl["cli_version"],
        "source": tpl["source"], "model_provider": "openai",
    }
    if tpl["base_instructions"]:
        meta["base_instructions"] = tpl["base_instructions"]
    meta["history_mode"] = "paginated"
    meta["context_window"] = {"window_id": uuid7(created)}
    if git_branch:
        meta["git"] = {"branch": git_branch}

    records = []
    stamp = iso_ms(created)

    def rec(rtype, payload):
        records.append({"timestamp": stamp, "ordinal": len(records), "type": rtype, "payload": payload})

    def item_event(turn_id, kind, item_id, content):
        rec("event_msg", {"type": "item_completed", "thread_id": tid, "turn_id": turn_id,
                          "item": {"type": kind, "id": item_id, "content": content},
                          "completed_at_ms": created})

    rec("session_meta", meta)
    turns = _group_turns(items)
    total_chars = 0
    item_no = 0
    for ti, turn in enumerate(turns, 1):
        turn_id = f"external-import-turn-{ti}"
        started = (turn[0].get("ms") or first_ms or created) // 1000
        rec("event_msg", {"type": "task_started", "turn_id": turn_id, "started_at": started,
                          "model_context_window": None, "collaboration_mode_kind": "default"})
        for it in turn:
            item_no += 1
            text = it["text"]
            total_chars += len(text)
            if it["role"] == "user":
                item_event(turn_id, "UserMessage", f"item-{item_no}",
                           [{"type": "text", "text": text, "text_elements": []}])
                rec("response_item", {"type": "message", "role": "user",
                                      "content": [{"type": "input_text", "text": text}]})
            else:
                item_event(turn_id, "AgentMessage", f"item-{item_no}", [{"type": "Text", "text": text}])
                rec("response_item", {"type": "message", "role": "assistant",
                                      "content": [{"type": "output_text", "text": text}]})
        done = {"type": "task_complete", "turn_id": turn_id, "last_agent_message": None,
                "started_at": started}
        if ti == len(turns):
            # Yalnızca arayüzde görünen işaret (model geçmişine girmez)
            item_no += 1
            item_event(turn_id, "AgentMessage", f"item-{item_no}", [{"type": "Text", "text": IMPORT_MARKER}])
            usage = {"input_tokens": 0, "cached_input_tokens": 0, "cache_write_input_tokens": 0,
                     "output_tokens": 0, "reasoning_output_tokens": 0, "total_tokens": total_chars // 4}
            rec("event_msg", {"type": "token_count",
                              "info": {"total_token_usage": usage, "last_token_usage": dict(usage),
                                       "model_context_window": None},
                              "rate_limits": None})
            done["completed_at"] = started
        rec("event_msg", done)

    day_dir.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
    return path, tid


def _append_codex_thread_name(tid, title):
    p = codex_home() / "session_index.jsonl"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({"id": tid, "thread_name": title, "updated_at": stamp},
                           ensure_ascii=False, separators=(",", ":")) + "\n")


def _verbatim(p: str, use: bool) -> str:
    """Windows'ta Codex veritabanındaki yollar \\\\?\\ önekiyle tutuluyor."""
    if not use or not p or sys.platform != "win32" or p.startswith("\\\\?\\"):
        return p
    return "\\\\?\\" + p


def register_codex_thread(tid, rollout_path, cwd, title, first_user, first_ms, last_ms,
                          git_branch, cli_version):
    """
    Codex uygulamasının thread listesine (state_*.sqlite → threads) satır ekler.
    Codex masaüstü uygulaması listeyi bu tablodan okur; ilk taramadan sonra diske
    eklenen rollout dosyası tek başına listeye girmez. Şema sürüme göre
    değişebileceği için yalnızca var olan sütunlar yazılır; işlemden önce
    veritabanının yedeği (<db>.csm-bak) alınır. Döndürür: (ok, mesaj)
    """
    db = codex_state_db()
    if not db:
        return False, "state db not found"
    try:
        src = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5)
        dst = sqlite3.connect(str(db.with_name(db.name + ".csm-bak")))
        src.backup(dst)
        dst.close()
        src.close()

        con = sqlite3.connect(str(db), timeout=10)
        info = list(con.execute("PRAGMA table_info(threads)"))
        if not info:
            con.close()
            return False, "threads table not found"
        # PRAGMA table_info: (cid, name, type, notnull, dflt_value, pk)
        cols = {r[1]: r for r in info}
        sample = con.execute("SELECT rollout_path FROM threads LIMIT 1").fetchone()
        use_vb = bool(sample and str(sample[0]).startswith("\\\\?\\"))
        now = now_ms()
        first_ms = first_ms or now
        last_ms = last_ms or first_ms
        preview = _one_line(first_user or "", 80)
        values = {
            "id": tid,
            "rollout_path": _verbatim(str(rollout_path), use_vb),
            "created_at": first_ms // 1000, "updated_at": last_ms // 1000,
            "created_at_ms": first_ms, "updated_at_ms": last_ms,
            # listenin en üstünde görünsün
            "recency_at": now // 1000, "recency_at_ms": now,
            "source": "vscode", "model_provider": "openai",
            "cwd": _verbatim(cwd, use_vb), "title": title, "name": title,
            "sandbox_policy": '{"type":"read-only"}', "approval_mode": "on-request",
            "tokens_used": 0, "has_user_event": 0, "archived": 0, "is_pinned": 0,
            "git_branch": git_branch, "cli_version": cli_version or "",
            "first_user_message": preview, "preview": preview,
            "memory_mode": "enabled", "history_mode": "paginated",
        }
        values = {k: v for k, v in values.items() if k in cols}
        missing = [n for n, r in cols.items() if r[3] and r[4] is None and not r[5] and n not in values]
        if missing:
            con.close()
            return False, "unknown required columns: " + ", ".join(missing)
        names = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        with con:
            con.execute(f"INSERT INTO threads ({names}) VALUES ({marks})", list(values.values()))
        con.close()
        return True, str(db)
    except Exception as e:
        return False, str(e)


def _record_codex_import_ledger(src_path, tid, title):
    """Codex'in 'Claude Code'dan içe aktar' defterine kayıt ekle: aynı oturum
    Codex tarafından ikinci kez içe aktarılıp çift görünmesin."""
    ledger = codex_home() / "external_agent_session_imports.json"
    if not ledger.exists():
        return
    try:
        data = json.loads(ledger.read_text(encoding="utf-8"))
        recs = data.get("records") if isinstance(data, dict) else None
        if not isinstance(recs, list):
            return
        src = Path(src_path)
        st = src.stat()
        recs.append({
            "source_path": _verbatim(str(src.resolve()), True),
            "content_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
            "imported_thread_id": tid, "imported_at": int(time.time()),
            "source_modified_at": int(st.st_mtime * 1_000_000_000),
            "connector_names": [], "title": title,
        })
        tmp = ledger.with_name(ledger.name + ".csm-tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, ledger)
    except Exception:
        pass


def claude_to_codex(sess, register_app=True):
    """
    Bir Claude Code oturumunu (list_claude_sessions öğesi) Codex'e dönüştür.
    Döndürür: {"path", "thread_id", "items", "turns", "registered", "warn"}
    """
    meta, items = read_claude_transcript(sess["path"])
    if not items:
        raise ValueError("no messages")
    title = sess.get("title") or meta.get("title") or _one_line(items[0]["text"], 80)
    cwd = meta.get("cwd") or (sess.get("cwd") if sess.get("cwd") not in (None, "?") else None) \
        or str(Path.home())
    tpl = detect_codex_template()
    path, tid = write_codex_rollout(items, cwd, title, meta.get("git_branch"), meta.get("first_ms"), tpl)
    warn = []
    try:
        _append_codex_thread_name(tid, title)
    except Exception as e:
        warn.append(f"session_index.jsonl ({e})")
    registered = False
    if register_app:
        first_user = next((i["text"] for i in items if i["role"] == "user"), "")
        registered, msg = register_codex_thread(
            tid, path, cwd, title, first_user, meta.get("first_ms"), meta.get("last_ms"),
            meta.get("git_branch"), tpl["cli_version"])
        if registered:
            _record_codex_import_ledger(sess["path"], tid, title)
        elif msg != "state db not found":
            warn.append(f"codex app db: {msg}")
    return {"path": path, "thread_id": tid, "items": len(items),
            "turns": len(_group_turns(items)), "registered": registered, "warn": warn}


# -------------------------------------------------------------------
# CODEX → CLAUDE CODE
# -------------------------------------------------------------------

def write_claude_transcript(items, cwd, title, model=None):
    """items -> yeni Claude Code transkripti. (yol, session_id, tur_sayısı) döndürür."""
    if not items:
        raise ValueError("empty session")
    cwd = cwd or str(Path.home())
    sid = str(uuid.uuid4())
    version = detect_claude_version()
    model = model or CLAUDE_MODEL_FALLBACK
    out_dir = claude_project_dir_for(cwd)
    path = out_dir / f"{sid}.jsonl"

    lines = [{"type": "custom-title", "customTitle": title, "sessionId": sid}]
    parent = None
    msg_id = None
    turns = 0
    last_ms = 0
    fallback_ms = now_ms()
    for it in items:
        ms = max(it.get("ms") or fallback_ms, last_ms + 1)  # kesin artan zaman damgaları
        last_ms = ms
        u = str(uuid.uuid4())
        common = {"parentUuid": parent, "isSidechain": False, "userType": "external",
                  "cwd": cwd, "sessionId": sid, "version": version, "gitBranch": ""}
        if it["role"] == "user":
            turns += 1
            msg_id = None
            lines.append({**common, "type": "user",
                          "message": {"role": "user", "content": it["text"]},
                          "uuid": u, "timestamp": iso_ms(ms)})
        else:
            # Ardışık asistan blokları tek mesajdır (Claude Code da blok başına satır yazar)
            if msg_id is None:
                msg_id = "msg_imported_" + uuid.uuid4().hex[:24]
            lines.append({**common, "type": "assistant",
                          "message": {"id": msg_id, "type": "message", "role": "assistant",
                                      "model": model,
                                      "content": [{"type": "text", "text": it["text"]}],
                                      "stop_reason": None, "stop_sequence": None,
                                      "usage": {"input_tokens": 0, "output_tokens": 0,
                                                "cache_creation_input_tokens": 0,
                                                "cache_read_input_tokens": 0}},
                          "requestId": "req_imported_" + uuid.uuid4().hex[:20],
                          "uuid": u, "timestamp": iso_ms(ms)})
        parent = u

    out_dir.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in lines:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
    return path, sid, turns


def _account_workspace(account) -> str:
    """Hesabın mevcut workspace/org klasörü (en yeni oturumdan), yoksa ilk alt klasör."""
    if account.get("sessions"):
        newest = max(account["sessions"], key=lambda s: s["last"])
        parts = newest["rel"].parts
        if len(parts) >= 2:
            return parts[1]
    try:
        subs = [d.name for d in Path(account["dir"]).iterdir() if d.is_dir()]
        if subs:
            return subs[0]
    except Exception:
        pass
    return str(uuid.uuid4())


def register_claude_desktop(account, cli_sid, cwd, title, first_ms, turns, model=None):
    """Claude masaüstü uygulamasında görünmesi için hesap altına local_*.json yaz
    (tüm aynalı depolara). (yazılanlar, hatalar) döndürür."""
    bases = csm.existing_bases("code")
    if not bases:
        return [], ["claude-code-sessions store not found"]
    # Kullanıcının tercihleri (model, efor, izin modu…) hesabın en yeni oturumundan alınır.
    tpl = {}
    if account.get("sessions"):
        tpl = max(account["sessions"], key=lambda s: s["last"]).get("entry") or {}
    local_id = f"local_{uuid.uuid4()}"
    rel = Path(account["id"]) / _account_workspace(account) / f"{local_id}.json"
    now = now_ms()
    record = {
        "sessionId": local_id, "cliSessionId": cli_sid, "cwd": cwd, "originCwd": cwd,
        "createdAt": first_ms or now, "lastActivityAt": now, "lastFocusedAt": now,
        "model": model or tpl.get("model") or CLAUDE_MODEL_FALLBACK,
        "effort": tpl.get("effort") or "high",
        "isArchived": False, "title": title, "titleSource": "user",
        "permissionMode": tpl.get("permissionMode") or "default",
        "remoteMcpServersConfig": [], "bridgeSessionIds": [], "completedTurns": turns,
        # Masaüstü uygulamasının tüm kayıtlarında bulunan alanlar
        "alwaysAllowedReasons": [], "sessionPermissionUpdates": [],
        "classifierSummaryEnabled": tpl.get("classifierSummaryEnabled", True), "spawnSeed": {},
    }
    for key in ("sessionSettings", "chromePermissionMode"):
        if key in tpl:
            record[key] = tpl[key]
    text = json.dumps(record, ensure_ascii=False)
    written, errs = [], []
    for base in bases:
        dst = base / rel
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            with open(dst, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            written.append(dst)
        except Exception as e:
            errs.append(f"{dst} ({e})")
    return written, errs


def codex_to_claude(sess, account=None):
    """
    Bir Codex oturumunu (list_codex_sessions öğesi) Claude Code'a dönüştür.
    account verilirse Claude masaüstü uygulamasındaki o hesaba da kaydedilir.
    Döndürür: {"path", "session_id", "items", "turns", "records", "warn"}
    """
    meta, items = read_codex_rollout(sess["path"])
    if not items:
        raise ValueError("no messages")
    title = sess.get("title") or meta.get("title") or _one_line(items[0]["text"], 80)
    cwd = meta.get("cwd") or (sess.get("cwd") if sess.get("cwd") not in (None, "?") else None) \
        or str(Path.home())
    path, sid, turns = write_claude_transcript(items, cwd, title)
    records, warn = [], []
    if account is not None:
        records, errs = register_claude_desktop(account, sid, cwd, title, meta.get("first_ms"), turns)
        warn += errs
    return {"path": path, "session_id": sid, "items": len(items), "turns": turns,
            "records": records, "warn": warn}
