"""webhook_secrets.py - encrypted secrets for webhooks, with key rotation (0.274.0, webhook platform M4).

What is kept here: the API keys an action sends as headers, and the signing secret a provider uses (Stripe, GitHub,
Shopify, Systeme.io, generic HMAC). `webhooks.json` holds only a reference `{"$secret": "<name>"}`; the value lives
in `STATE_DIR/webhook_secrets.json`, encrypted with AES-256-GCM. The name is the associated data, so a ciphertext
copied under another name does not decrypt.

Keys: `STATE_DIR/webhook_keys.json` (mode 600) holds `{"active": kid, "keys": {kid: base64}}`. `rotate()` adds a new
key, makes it active, re-encrypts every secret with it and then drops the old keys. A crash in the middle leaves both
keys in the file, so every secret still decrypts. `JAVIS_WH_MASTER_KEY` (base64 of 32 bytes) replaces the key file,
for a machine where the state folder is backed up or synced elsewhere.

What this protects: a copy of `webhooks.json` (backup, export, a pasted file) no longer carries the keys, and the
secrets file alone is useless without the key file. What it does not: someone who can read the whole state folder
reads both files (same as any local app that must use the secret unattended). Back up the key file with the secrets
file: without it the secrets cannot be recovered and must be entered again.
"""
from __future__ import annotations

import base64
import json
import os
import re
import secrets as _rand
import threading
import time
from pathlib import Path
from typing import Optional

NAME_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,160}$")
_lock = threading.RLock()


class _FileLock:
    """Several Javis processes may share one state folder (M1 supports that): the read-modify-write of the secrets
    file and the key file is serialised across processes with an advisory lock (POSIX flock; a no-op where it is
    missing)."""

    def __init__(self, path: Path):
        self.path = path
        self.fd = None

    def __enter__(self):
        _lock.acquire()
        try:
            import fcntl
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.fd = os.open(str(self.path), os.O_CREAT | os.O_RDWR, 0o600)
            fcntl.flock(self.fd, fcntl.LOCK_EX)
        except ImportError:
            self.fd = None
        except BaseException:
            _lock.release()
            raise
        return self

    def __exit__(self, *exc):
        try:
            if self.fd is not None:
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_UN)
                os.close(self.fd)
        finally:
            self.fd = None
            _lock.release()


class SecretError(Exception):
    pass


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _unb64(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def _write_private(path: Path, text: str) -> None:
    """Atomic and mode 600 from the first byte (the temp file is created private, then renamed over)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    fd = os.open(str(tmp), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


class Vault:
    def __init__(self, state_dir: Path):
        self.dir = Path(state_dir)
        self.keys_path = self.dir / "webhook_keys.json"
        self.path = self.dir / "webhook_secrets.json"
        self.lock = _FileLock(self.dir / "webhook_secrets.lock")

    # ── keys ──
    def _keys(self, create: bool = True) -> dict:
        env = os.environ.get("JAVIS_WH_MASTER_KEY", "").strip()
        if env:
            try:
                k = _unb64(env)
            except (ValueError, TypeError):
                raise SecretError("JAVIS_WH_MASTER_KEY is not valid base64")
            if len(k) != 32:
                raise SecretError("JAVIS_WH_MASTER_KEY must be base64 of 32 bytes")
            return {"active": "env", "keys": {"env": env}}
        if self.keys_path.exists():
            try:
                d = json.loads(self.keys_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                raise SecretError(f"webhook key file is unreadable: {type(e).__name__}")
            if isinstance(d, dict) and d.get("active") in (d.get("keys") or {}):
                return d
            raise SecretError("webhook key file has no active key")
        if not create:
            raise SecretError("no webhook key file")
        kid = "k" + time.strftime("%Y%m%d%H%M%S") + _rand.token_hex(2)
        d = {"active": kid, "keys": {kid: _b64(_rand.token_bytes(32))}}
        _write_private(self.keys_path, json.dumps(d))
        return d

    def _load(self) -> dict:
        if not self.path.exists():
            return {"v": 1, "items": {}}
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise SecretError(f"webhook secrets file is unreadable: {type(e).__name__}")
        if not isinstance(d, dict) or not isinstance(d.get("items"), dict):
            raise SecretError("webhook secrets file is damaged")
        return d

    def _save(self, d: dict) -> None:
        _write_private(self.path, json.dumps(d, indent=1))

    @staticmethod
    def _seal(key_b64: str, kid: str, name: str, value: str) -> dict:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = _rand.token_bytes(12)
        ct = AESGCM(_unb64(key_b64)).encrypt(nonce, value.encode("utf-8"), name.encode("utf-8"))
        return {"kid": kid, "n": _b64(nonce), "c": _b64(ct), "at": int(time.time())}

    @staticmethod
    def _open(keys: dict, name: str, item: dict) -> str:
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        k = (keys.get("keys") or {}).get(item.get("kid"))
        if not k:
            raise SecretError(f"the key that encrypted secret {name} is missing")
        try:
            return AESGCM(_unb64(k)).decrypt(_unb64(item["n"]), _unb64(item["c"]), name.encode("utf-8")).decode("utf-8")
        except (InvalidTag, ValueError, KeyError, TypeError):
            raise SecretError(f"secret {name} does not decrypt (wrong key or damaged)")

    # ── API ──
    def put(self, name: str, value: str) -> None:
        if not NAME_RE.match(name or ""):
            raise SecretError(f"bad secret name: {name!r}")
        with self.lock:
            keys = self._keys()
            d = self._load()
            d["items"][name] = self._seal(keys["keys"][keys["active"]], keys["active"], name, str(value))
            self._save(d)

    def get(self, name: str) -> str:
        with self.lock:
            d = self._load()
            item = d["items"].get(name)
            if item is None:
                raise SecretError(f"secret {name} is not set")
            return self._open(self._keys(create=False), name, item)

    def has(self, name: str) -> bool:
        with self.lock:
            return name in self._load()["items"]

    def delete_prefix(self, prefix: str) -> int:
        with self.lock:
            d = self._load()
            gone = [n for n in d["items"] if n == prefix or n.startswith(prefix + "/")]
            for n in gone:
                del d["items"][n]
            if gone:
                self._save(d)
            return len(gone)

    def names(self) -> list:
        with self.lock:
            return sorted(self._load()["items"])

    def rotate(self) -> dict:
        """New active key; every secret re-encrypted with it; old keys dropped only after the secrets file is
        written. Returns {"active", "rewrapped", "dropped"}."""
        if os.environ.get("JAVIS_WH_MASTER_KEY", "").strip():
            raise SecretError("the key comes from JAVIS_WH_MASTER_KEY: rotate it there")
        with self.lock:
            keys = self._keys()
            d = self._load()
            plain = {n: self._open(keys, n, it) for n, it in d["items"].items()}
            kid = "k" + time.strftime("%Y%m%d%H%M%S") + _rand.token_hex(2)
            new_key = _b64(_rand.token_bytes(32))
            # 1) both keys in the key file; 2) secrets re-encrypted; 3) old keys dropped. A crash after any step
            # leaves every secret readable.
            both = {"active": kid, "keys": dict(keys["keys"], **{kid: new_key})}
            _write_private(self.keys_path, json.dumps(both))
            d["items"] = {n: self._seal(new_key, kid, n, v) for n, v in plain.items()}
            self._save(d)
            old = [k for k in keys["keys"] if k != kid]
            _write_private(self.keys_path, json.dumps({"active": kid, "keys": {kid: new_key}}))
            return {"active": kid, "rewrapped": len(plain), "dropped": len(old)}


def is_ref(v) -> bool:
    return isinstance(v, dict) and set(v) == {"$secret"} and isinstance(v["$secret"], str) \
        and bool(NAME_RE.match(v["$secret"]))
