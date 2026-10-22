"""Login vault (0.251.0): the owner's sign-in cookies, kept encrypted, reused by Javis.

The owner signs in on their own browser, exports the cookies of that site and pastes them on the
"Kho đăng nhập" page. Four shapes are read: a Cookie-Editor JSON export, a Playwright storage state,
a Netscape cookies.txt and a bare `Cookie:` header. Javis then uses that sign-in to:

- open a page behind it for every engine (plugin tool `javis_login`, op=fetch), and
- check a page behind it on a schedule (web_watch, a watch with `login_id`).

Rules this module keeps:

- Cookie VALUES never reach a model. Tools return page text and the login's name, never the cookies.
- Values are encrypted at rest (`secrets_store.encrypt_required`). No working encryption means the
  vault refuses to save, instead of writing sign-ins to disk in the clear.
- A cookie only goes to a host it was issued for (domain, path, secure and expiry are checked on
  every hop of a redirect), so a page that redirects elsewhere never carries them along.
- The page and its routes need a real dashboard session; an API token cannot read or add sign-ins.

Spec of the idea and the choice against a built-in browser: the 2026-10-20 conversation that started
this (owner: "Làm Kho đăng nhập trước"). A built-in browser for signing in from a VPS may come later
and would fill this same vault.
"""
from __future__ import annotations

import json
import re
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

import localefmt

MAX_INPUT = 400_000          # characters of pasted text
MAX_COOKIES = 600
MAX_NAME = 80
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_SAMESITE = {"strict": "Strict", "lax": "Lax", "none": "None", "no_restriction": "None",
             "unspecified": "Lax", "": "Lax"}
# A path segment (extension dropped) from this set means the site sent us to its sign-in page. Whole
# segments only: a blog post slug like "/mau-trang-login-dep" is not a sign-in page.
_SIGNED_OUT_SEGMENTS = frozenset({"login", "log-in", "log_in", "signin", "sign-in", "sign_in", "dang-nhap",
                                  "dangnhap", "checkpoint", "servicelogin", "authenticate"})
_SIGNED_OUT_TITLE = re.compile(r"\b(log ?in|sign ?in)\b|đăng nhập|dang nhap", re.I)


class VaultError(Exception):
    """Message already worded for the owner."""


# ============================================================
# Parsing (pure, tested without a server)
# ============================================================
def _host_of(hint: str) -> str:
    hint = str(hint or "").strip()
    if not hint:
        return ""
    if "://" not in hint:
        hint = "https://" + hint
    return (urlparse(hint).hostname or "").lower()


def _clean_domain(domain: str, host_only: Optional[bool]) -> str:
    d = str(domain or "").strip().lower()
    if not d:
        return ""
    dotted = d.startswith(".")
    d = d.lstrip(".")
    if not re.fullmatch(r"[a-z0-9.-]+", d) or "." not in d:
        return ""
    if host_only is None:
        return ("." + d) if dotted else d
    return d if host_only else "." + d


def _cookie(name, value, domain, path="/", expires=-1, http_only=False, secure=False, same_site="Lax",
            host_only=None) -> Optional[dict]:
    name, value = str(name or ""), str(value if value is not None else "")
    if not name or _CTRL.search(name) or _CTRL.search(value) or ";" in name or "=" in name:
        return None
    dom = _clean_domain(domain, host_only)
    if not dom:
        return None
    path = str(path or "/")
    if not path.startswith("/"):
        path = "/"
    try:
        exp = float(expires) if expires not in (None, "", 0, "0") else -1.0
    except (TypeError, ValueError):
        exp = -1.0
    if exp > 1e11:          # milliseconds
        exp = exp / 1000.0
    ss = _SAMESITE.get(str(same_site or "").strip().lower(), "Lax")
    return {"name": name, "value": value, "domain": dom, "path": path, "expires": exp if exp > 0 else -1,
            "httpOnly": bool(http_only), "secure": bool(secure), "sameSite": ss}


def _from_json_list(items: list) -> list:
    out = []
    for c in items:
        if not isinstance(c, dict):
            continue
        host_only = c.get("hostOnly")
        exp = c.get("expirationDate", c.get("expires", c.get("expiry")))
        if c.get("session") is True:
            exp = -1
        ck = _cookie(c.get("name"), c.get("value"), c.get("domain"), c.get("path") or "/", exp,
                     c.get("httpOnly"), c.get("secure"), c.get("sameSite"),
                     host_only if isinstance(host_only, bool) else None)
        if ck:
            out.append(ck)
    return out


def _from_netscape(text: str) -> list:
    out = []
    for raw in text.splitlines():
        line = raw.strip("\r\n")
        http_only = False
        if line.startswith("#HttpOnly_"):
            line, http_only = line[len("#HttpOnly_"):], True
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, sub, path, secure, exp, name, value = parts[:7]
        ck = _cookie(name, value, domain, path, exp, http_only, secure.upper() == "TRUE", "Lax",
                     host_only=(sub.upper() != "TRUE"))
        if ck:
            out.append(ck)
    return out


def _from_header(text: str, host: str) -> list:
    body = re.sub(r"^\s*cookie\s*:\s*", "", text.strip(), flags=re.I)
    base = host[4:] if host.startswith("www.") else host
    out = []
    for part in body.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        ck = _cookie(name.strip(), value.strip(), "." + base, "/", -1, False, True, "Lax")
        if ck:
            out.append(ck)
    return out


def parse_cookies(text: str, site: str = "") -> tuple[list, list]:
    """Pasted text -> (cookies in Playwright shape, localStorage origins). Raises VaultError."""
    text = str(text or "").strip()
    if not text:
        raise VaultError(localefmt.chu("Chưa dán cookie nào", "Nothing pasted yet"))
    if len(text) > MAX_INPUT:
        raise VaultError(localefmt.chu("Đoạn dán quá dài", "The pasted text is too long"))
    cookies, origins = [], []
    if text[0] in "[{":
        try:
            data = json.loads(text)
        except ValueError as e:
            raise VaultError(localefmt.chu("Đoạn JSON bị lỗi, hãy xuất lại cookie rồi dán nguyên văn",
                                           "The JSON is broken; export the cookies again and paste them as is")) from e
        if isinstance(data, dict):
            cookies = _from_json_list(data.get("cookies") or [])
            for o in data.get("origins") or []:
                if isinstance(o, dict) and str(o.get("origin", "")).startswith(("https://", "http://")):
                    ls = [{"name": str(i.get("name", "")), "value": str(i.get("value", ""))}
                          for i in (o.get("localStorage") or []) if isinstance(i, dict) and i.get("name")]
                    if ls:
                        origins.append({"origin": str(o["origin"]), "localStorage": ls[:500]})
        elif isinstance(data, list):
            cookies = _from_json_list(data)
    elif "\t" in text:
        cookies = _from_netscape(text)
    else:
        host = _host_of(site)
        if not host:
            raise VaultError(localefmt.chu("Dán dạng 'tên=giá trị; ...' thì cần ghi thêm trang web (ví dụ shopee.vn)",
                                           "For a 'name=value; ...' header, also fill in the website (e.g. shopee.vn)"))
        cookies = _from_header(text, host)
    if not cookies:
        raise VaultError(localefmt.chu("Không đọc được cookie nào. Hãy xuất bằng Cookie-Editor (Export, JSON) rồi dán vào.",
                                       "No cookie could be read. Export with Cookie-Editor (Export, JSON) and paste it."))
    if len(cookies) > MAX_COOKIES:
        raise VaultError(localefmt.chu(f"Quá nhiều cookie ({len(cookies)}). Chỉ xuất cookie của một trang.",
                                       f"Too many cookies ({len(cookies)}). Export the cookies of one site only."))
    # Same name, domain and path: the later one wins, as in a browser.
    seen = {}
    for c in cookies:
        seen[(c["name"], c["domain"], c["path"])] = c
    return list(seen.values()), origins


def domains_of(cookies: list) -> list:
    return sorted({c["domain"].lstrip(".") for c in cookies})


def last_expiry(cookies: list) -> float:
    """When the LAST cookie expires (0 = all are session cookies). Past this the sign-in is surely gone."""
    exps = [c["expires"] for c in cookies if c.get("expires", -1) > 0]
    return max(exps) if exps else 0.0


def cookie_header(cookies: list, url: str, now: Optional[float] = None) -> str:
    """The Cookie header a browser would send to `url`, or "" (RFC 6265 domain, path and secure rules)."""
    p = urlparse(str(url or ""))
    host = (p.hostname or "").lower()
    if not host:
        return ""
    path = p.path or "/"
    https = p.scheme == "https"
    now = time.time() if now is None else now
    picked = []
    for c in cookies:
        d = c["domain"]
        if d.startswith("."):
            base = d[1:]
            if host != base and not host.endswith("." + base):
                continue
        elif host != d:
            continue
        cp = c.get("path") or "/"
        if not (path == cp or cp == "/" or path.startswith(cp.rstrip("/") + "/")):
            continue
        if c.get("secure") and not https:
            continue
        if c.get("expires", -1) > 0 and c["expires"] <= now:
            continue
        picked.append(c)
    picked.sort(key=lambda c: -len(c.get("path") or "/"))
    return "; ".join(f"{c['name']}={c['value']}" for c in picked)


def matches(cookies: list, url: str) -> bool:
    return bool(cookie_header(cookies, url))


def looks_signed_out(final_url: str, title: str = "", status: int = 0) -> bool:
    """Best guess from the outside: a 401/403, a sign-in address or a 'Log in' page title."""
    if status in (401, 403):
        return True
    p = urlparse(str(final_url or ""))
    for seg in (p.path or "").lower().split("/"):
        if seg.rsplit(".", 1)[0] in _SIGNED_OUT_SEGMENTS:
            return True
    t = str(title or "").strip()
    return bool(t) and len(t) <= 40 and bool(_SIGNED_OUT_TITLE.search(t))   # short: a sign-in page, not an article


# ============================================================
# Store
# ============================================================
_COLS = ("id", "name", "domains", "cookies_enc", "origins_enc", "count", "allow_ai", "test_url", "status",
         "status_note", "checked_at", "used_at", "uses", "expires_at", "created_at", "updated_at")
STATUSES = ("unknown", "ok", "signed_out", "error")


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(self.path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=5000")
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS logins (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, domains TEXT NOT NULL DEFAULT '[]',
                cookies_enc TEXT NOT NULL, origins_enc TEXT NOT NULL DEFAULT '',
                count INTEGER NOT NULL DEFAULT 0, allow_ai INTEGER NOT NULL DEFAULT 1,
                test_url TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'unknown',
                status_note TEXT NOT NULL DEFAULT '', checked_at REAL NOT NULL DEFAULT 0,
                used_at REAL NOT NULL DEFAULT 0, uses INTEGER NOT NULL DEFAULT 0,
                expires_at REAL NOT NULL DEFAULT 0, created_at REAL NOT NULL, updated_at REAL NOT NULL
            );
            """)
        self._db.commit()
        try:
            import os
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def close(self):
        with self._lock:
            self._db.close()

    def add(self, row: dict) -> dict:
        with self._lock:
            keys = [k for k in _COLS if k in row]
            self._db.execute(f"INSERT INTO logins({','.join(keys)}) VALUES ({','.join('?' * len(keys))})",
                             [row[k] for k in keys])
            self._db.commit()
        return self.get(row["id"])

    def get(self, lid: str) -> Optional[dict]:
        with self._lock:
            r = self._db.execute("SELECT * FROM logins WHERE id=?", (str(lid or ""),)).fetchone()
        return dict(r) if r else None

    def update(self, lid: str, **cols) -> Optional[dict]:
        cols = {k: v for k, v in cols.items() if k in _COLS and k != "id"}
        if cols:
            with self._lock:
                self._db.execute(f"UPDATE logins SET {', '.join(f'{k}=?' for k in cols)} WHERE id=?",
                                 (*cols.values(), lid))
                self._db.commit()
        return self.get(lid)

    def delete(self, lid: str) -> bool:
        with self._lock:
            n = self._db.execute("DELETE FROM logins WHERE id=?", (lid,)).rowcount
            self._db.commit()
        return bool(n)

    def list(self) -> list:
        with self._lock:
            rows = self._db.execute("SELECT * FROM logins ORDER BY name COLLATE NOCASE").fetchall()
        return [dict(r) for r in rows]

    def find_name(self, name: str) -> Optional[dict]:
        with self._lock:
            r = self._db.execute("SELECT * FROM logins WHERE lower(name)=lower(?)", (str(name or "").strip(),)).fetchone()
        return dict(r) if r else None


# ============================================================
# Feature
# ============================================================
@dataclass
class LoginVaultDeps:
    state_dir: Callable[[], Path]
    # Request -> True only for a real dashboard sign-in (API tokens are refused)
    has_session: Callable[[Request], bool]
    # async fetch(url, cookies) -> (final_url, title, text); raises web_watch.FetchError
    fetch: Optional[Callable] = None


def _encrypt(obj) -> str:
    import secrets_store
    try:
        return secrets_store.encrypt_required(json.dumps(obj, ensure_ascii=False))
    except RuntimeError as e:
        raise VaultError(localefmt.chu("Máy này chưa mã hoá được dữ liệu (thiếu thư viện cryptography), nên Javis "
                                       "không lưu đăng nhập. Cài lại Javis hoặc chạy: pip install cryptography",
                                       "This machine cannot encrypt data (the cryptography library is missing), so "
                                       "Javis will not store sign-ins. Reinstall Javis or run: pip install cryptography")) from e


def _decrypt(value: str):
    import secrets_store
    raw = secrets_store.decrypt(value or "")
    try:
        return json.loads(raw) if raw else []
    except ValueError:
        return []


class LoginVault:
    def __init__(self, deps: LoginVaultDeps):
        self.deps = deps
        self.store = Store(Path(deps.state_dir()) / "login_vault.sqlite3")
        self.router = self._make_router()

    # ---------- reading ----------
    @staticmethod
    def view(row: dict) -> dict:
        """What the page and tools may see. Never the cookies."""
        now = time.time()
        exp = float(row.get("expires_at") or 0)
        try:
            domains = json.loads(row.get("domains") or "[]")
        except ValueError:
            domains = []
        return {"id": row["id"], "name": row["name"], "domains": domains, "count": row.get("count") or 0,
                "allow_ai": bool(row.get("allow_ai")), "test_url": row.get("test_url") or "",
                "status": row.get("status") or "unknown", "status_note": row.get("status_note") or "",
                "checked_at": row.get("checked_at") or 0, "used_at": row.get("used_at") or 0,
                "uses": row.get("uses") or 0, "expires_at": exp, "expired": bool(exp and exp <= now),
                "created_at": row.get("created_at") or 0, "updated_at": row.get("updated_at") or 0}

    def cookies(self, lid: str) -> list:
        row = self.store.get(lid)
        return _decrypt(row["cookies_enc"]) if row else []

    def pick(self, url: str, login: str = "", only_allowed: bool = True) -> tuple[Optional[dict], list, str]:
        """(row, cookies, error) for opening `url`. `login` = id or name; empty = the one whose cookies fit."""
        if login:
            row = self.store.get(login) or self.store.find_name(login)
            if not row:
                return None, [], localefmt.chu(f"Không có đăng nhập nào tên '{login}' trong trang Cookies.",
                                               f"No sign-in named '{login}' on the Cookies page.")
            if only_allowed and not row.get("allow_ai"):
                return None, [], localefmt.chu(f"Đăng nhập '{row['name']}' đang tắt quyền cho Javis dùng.",
                                               f"The sign-in '{row['name']}' is not allowed for Javis.")
            ck = _decrypt(row["cookies_enc"])
            if not matches(ck, url):
                return None, [], localefmt.chu(f"Đăng nhập '{row['name']}' không dùng cho địa chỉ này.",
                                               f"The sign-in '{row['name']}' does not cover this address.")
            return row, ck, ""
        host = (urlparse(str(url or "")).hostname or "").lower()
        best = None
        for row in self.store.list():
            if only_allowed and not row.get("allow_ai"):
                continue
            ck = _decrypt(row["cookies_enc"])
            if matches(ck, url):
                # Prefer the one that worked last and was used most recently.
                score = (row.get("status") == "ok", row.get("used_at") or 0)
                if best is None or score > best[0]:
                    best = (score, row, ck)
        if not best:
            return None, [], localefmt.chu(f"Trang Cookies chưa có đăng nhập nào cho {host or 'địa chỉ này'}.",
                                           f"The Cookies page has no sign-in for {host or 'this address'}.")
        return best[1], best[2], ""

    # ---------- writing ----------
    def create(self, name: str, text: str, site: str = "", test_url: str = "") -> dict:
        cookies, origins = parse_cookies(text, site)
        name = (str(name or "").strip() or domains_of(cookies)[0])[:MAX_NAME]
        if self.store.find_name(name):
            raise VaultError(localefmt.chu(f"Đã có đăng nhập tên '{name}'. Đặt tên khác, hoặc bấm Cập nhật ở thẻ đó.",
                                           f"A sign-in named '{name}' exists. Pick another name or press Update on it."))
        now = time.time()
        row = {"id": "lg_" + secrets.token_hex(5), "name": name, "domains": json.dumps(domains_of(cookies)),
               "cookies_enc": _encrypt(cookies), "origins_enc": _encrypt(origins) if origins else "",
               "count": len(cookies), "allow_ai": 1, "test_url": self._test_url(test_url, cookies),
               "status": "unknown", "expires_at": last_expiry(cookies), "created_at": now, "updated_at": now}
        return self.view(self.store.add(row))

    def replace(self, lid: str, text: str, site: str = "") -> dict:
        row = self.store.get(lid)
        if not row:
            raise VaultError(localefmt.chu("Không thấy đăng nhập này", "Sign-in not found"))
        cookies, origins = parse_cookies(text, site)
        upd = self.store.update(lid, cookies_enc=_encrypt(cookies), origins_enc=_encrypt(origins) if origins else "",
                                count=len(cookies), domains=json.dumps(domains_of(cookies)),
                                expires_at=last_expiry(cookies), status="unknown", status_note="",
                                updated_at=time.time())
        return self.view(upd)

    @staticmethod
    def _test_url(test_url: str, cookies: list) -> str:
        u = str(test_url or "").strip()
        if u:
            if "://" not in u:
                u = "https://" + u
            if urlparse(u).scheme not in ("http", "https") or not urlparse(u).hostname:
                raise VaultError(localefmt.chu("Trang kiểm tra phải là địa chỉ web", "The test page must be a web address"))
            return u[:500]
        doms = domains_of(cookies)
        return ("https://" + doms[0] + "/") if doms else ""

    def control(self, lid: str, action: str, payload: Optional[dict] = None) -> dict:
        p = payload or {}
        row = self.store.get(lid)
        if not row:
            raise VaultError(localefmt.chu("Không thấy đăng nhập này", "Sign-in not found"))
        action = str(action or "").strip().lower()
        if action in ("allow", "deny"):
            return self.view(self.store.update(lid, allow_ai=int(action == "allow"), updated_at=time.time()))
        if action == "rename":
            name = str(p.get("name") or "").strip()[:MAX_NAME]
            if not name:
                raise VaultError(localefmt.chu("Tên không được trống", "The name cannot be empty"))
            other = self.store.find_name(name)
            if other and other["id"] != lid:
                raise VaultError(localefmt.chu(f"Đã có đăng nhập tên '{name}'", f"A sign-in named '{name}' exists"))
            return self.view(self.store.update(lid, name=name, updated_at=time.time()))
        if action == "test_url":
            return self.view(self.store.update(lid, test_url=self._test_url(p.get("test_url"), self.cookies(lid)),
                                               status="unknown", status_note="", updated_at=time.time()))
        if action == "replace":
            return self.replace(lid, p.get("text", ""), p.get("site", ""))
        if action == "delete":
            self.store.delete(lid)
            return {"id": lid, "deleted": True}
        raise VaultError(localefmt.chu("Thao tác chỉ nhận: allow, deny, rename, test_url, replace, delete, check",
                                       "Action must be allow, deny, rename, test_url, replace, delete or check"))

    # ---------- using ----------
    def mark(self, lid: str, status: str, note: str = "", used: bool = False) -> None:
        row = self.store.get(lid)
        if not row:
            return
        cols = {"status": status if status in STATUSES else "unknown", "status_note": str(note or "")[:300],
                "checked_at": time.time()}
        if used:
            cols.update(used_at=time.time(), uses=(row.get("uses") or 0) + 1)
        self.store.update(lid, **cols)

    async def open(self, url: str, login: str = "", only_allowed: bool = True, check_only: bool = False) -> dict:
        """Open `url` with a stored sign-in. Returns {ok, signed_out, login, final_url, title, text, error}."""
        row, ck, err = self.pick(url, login, only_allowed)
        if err:
            return {"ok": False, "error": err}
        if not self.deps.fetch:
            return {"ok": False, "error": localefmt.chu("Chưa sẵn sàng", "Not ready")}
        import web_watch
        try:
            final_url, title, text = await self.deps.fetch(url, ck)
        except web_watch.FetchError as e:
            status = getattr(e, "status", 0)
            if looks_signed_out("", "", status):
                note = localefmt.chu(f"Trang trả lỗi {status}: có vẻ đã đăng xuất", f"The page returned {status}: looks signed out")
                self.mark(row["id"], "signed_out", note, used=not check_only)
                return {"ok": False, "signed_out": True, "login": row["name"], "error": note}
            self.mark(row["id"], "error", str(e), used=not check_only)
            return {"ok": False, "login": row["name"], "error": str(e)}
        if looks_signed_out(final_url, title):
            note = localefmt.chu("Trang chuyển về màn đăng nhập", "The site sent us to its sign-in page")
            self.mark(row["id"], "signed_out", note, used=not check_only)
            return {"ok": False, "signed_out": True, "login": row["name"], "final_url": final_url,
                    "title": title, "error": note}
        self.mark(row["id"], "ok", title[:120] if title else "", used=not check_only)
        return {"ok": True, "login": row["name"], "login_id": row["id"], "final_url": final_url,
                "title": title, "text": text}

    async def check(self, lid: str) -> dict:
        row = self.store.get(lid)
        if not row:
            raise VaultError(localefmt.chu("Không thấy đăng nhập này", "Sign-in not found"))
        if not row.get("test_url"):
            raise VaultError(localefmt.chu("Chưa có trang kiểm tra", "No test page set"))
        await self.open(row["test_url"], lid, only_allowed=False, check_only=True)
        return self.view(self.store.get(lid))

    # ---------- routes ----------
    def _make_router(self) -> APIRouter:
        router = APIRouter()

        def denied():
            return JSONResponse({"ok": False, "error": localefmt.chu("cần đăng nhập dashboard", "dashboard sign-in required")},
                                status_code=401)

        def bad(e: Exception):
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

        @router.get("/logins")
        async def logins_list(request: Request):
            if not self.deps.has_session(request):
                return denied()
            import secrets_store
            return {"ok": True, "logins": [self.view(r) for r in self.store.list()],
                    "encryption": secrets_store.encryption_available()}

        @router.post("/logins")
        async def logins_create(request: Request, payload: dict = Body(None)):
            if not self.deps.has_session(request):
                return denied()
            p = payload or {}
            try:
                return {"ok": True, "login": self.create(p.get("name", ""), p.get("text", ""), p.get("site", ""),
                                                         p.get("test_url", ""))}
            except VaultError as e:
                return bad(e)

        @router.post("/logins/action")
        async def logins_action(request: Request, payload: dict = Body(None)):
            if not self.deps.has_session(request):
                return denied()
            p = payload or {}
            try:
                if str(p.get("action") or "") == "check":
                    return {"ok": True, "login": await self.check(str(p.get("id") or ""))}
                return {"ok": True, "login": self.control(str(p.get("id") or ""), str(p.get("action") or ""), p)}
            except VaultError as e:
                return bad(e)

        return router


_CURRENT: Optional[LoginVault] = None


def current() -> Optional[LoginVault]:
    return _CURRENT


def register(app, deps: LoginVaultDeps) -> LoginVault:
    global _CURRENT
    feat = LoginVault(deps)
    app.include_router(feat.router)
    _CURRENT = feat
    return feat
