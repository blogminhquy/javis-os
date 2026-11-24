"""Read-only semantic SQL inputs for a specifically authorized ordinary web session.

This component does not certify a complete prompt. Coding-folder bindings live in
coding.json and adaptive routing lives in settings/runtime state, outside these SQL
databases; the composing host must observe and reject unsupported variants there.
Principal type and credential redaction are mandatory trusted host dependencies so
importing this module cannot import config, create runtime directories or migrate DBs.
Read-only means logical database/WAL data and no application/schema writes. Native
SQLite reader coordination may update an already-existing SHM file. Missing WAL-mode
sidecars and nonempty rollback journals are rejected before reading. Every source
requires the host's concrete initialized native connection and its same mutation/close
lock; this module never opens a new source SQLite connection.
"""
from __future__ import annotations

import inspect
import json
import math
import os
import re
import sqlite3
import stat
import threading
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path

MAX_CONTEXT_ROWS = 1000
MAX_CONTEXT_BYTES = 1024 * 1024
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
_SESSION_FIELDS = ("id", "brain", "channel", "engine", "model", "project_id", "pinned_provider", "pinned_model", "archived")
_PROJECT_FIELDS = ("id", "brain", "name", "instructions")
_WORKFLOW_FIELDS = ("id", "brain", "name", "started_at", "status")
_SESSION_COLUMNS = set(_SESSION_FIELDS) | {
    "title", "cli_session_id", "codex_thread_id", "created_at", "updated_at", "msg_count", "parent_session_id",
    "compact_summary", "compact_count", "last_input_tokens", "thread_rotated_msg", "pinned", "gemini_session_id",
    "grok_session_id", "web_thread_id",
}
_PROJECT_COLUMNS = set(_PROJECT_FIELDS) | {"icon", "pinned", "created_at", "updated_at"}
_WORKFLOW_COLUMNS = set(_WORKFLOW_FIELDS) | {
    "slug", "session_id", "source", "input", "finished_at", "steps_json", "output", "error", "task_id",
}
_TABLES = {"sessions", "projects", "project_files", "project_links", "session_files", "session_links", "workflow_runs"}
_ASSET_TABLES = {"project_files": ("project_id", False), "project_links": ("project_id", True),
                 "session_files": ("session_id", False), "session_links": ("session_id", True)}
_LOCK_TYPES = (type(threading.Lock()), type(threading.RLock()))
_READ_STATEMENTS = {
    "PRAGMA database_list",
    "SELECT name,type,sql FROM main.sqlite_master WHERE name=? COLLATE NOCASE LIMIT 2",
    f"SELECT {','.join(_SESSION_FIELDS)} FROM main.sessions WHERE id=? LIMIT 2",
    f"SELECT {','.join(_PROJECT_FIELDS)} FROM main.projects WHERE id=? LIMIT 2",
    f"SELECT {','.join(_WORKFLOW_FIELDS)} FROM main.workflow_runs WHERE brain=? ORDER BY started_at DESC,rowid DESC LIMIT 1",
    "SELECT id FROM main.workflow_runs WHERE id=? LIMIT 2",
} | {f'PRAGMA main.table_xinfo("{table}")' for table in _TABLES}
for _table, (_parent, _links) in _ASSET_TABLES.items():
    _fields = ("id", "url", "label", "pinned", "added_at") if _links else ("id", "path", "name", "pinned", "added_at")
    _READ_STATEMENTS.add(f"SELECT {','.join(_fields)} FROM main.{_table} WHERE {_parent}=? "
                         "ORDER BY pinned DESC, added_at DESC, rowid DESC LIMIT ?")


class _ScopeError(PermissionError):
    """An authenticated scope mismatch, distinct from a filesystem access error."""


@dataclass(frozen=True)
class ExistingSQLiteSource:
    """Host-owned source, using its actual already initialized connection and lock.

    The lock must be the one all mutation and close operations use. A connection
    opened on demand by a request is not an existing source lifetime guarantee.
    """

    path: Path
    connection: sqlite3.Connection
    lock: object

    def __post_init__(self):
        _path(self.path)
        if not isinstance(self.connection, sqlite3.Connection) or not isinstance(self.lock, _LOCK_TYPES):
            raise ValueError("invalid_existing_sqlite_source")


class _ReadRows:
    def __init__(self, rows):
        self._rows, self._position = rows, 0

    def fetchall(self):
        return self.fetchmany(len(self._rows))

    def fetchmany(self, count):
        result = self._rows[self._position:self._position + count]
        self._position += len(result)
        return result


class _ReadFacade:
    """Only the module's literal SELECT/schema queries, never native write APIs."""

    def __init__(self, connection):
        self._connection = connection

    def execute(self, statement, parameters=()):
        if statement not in _READ_STATEMENTS:
            raise ValueError("unsupported_sql_context_query")
        cursor = self._connection.cursor()
        try:
            cursor.row_factory = sqlite3.Row
            cursor.execute(statement, parameters)
            return _ReadRows(cursor.fetchall())
        finally:
            cursor.close()


def _text(value, maximum=8192, *, empty=False, multiline=False, nullable=False):
    if value is None and nullable:
        return None
    if (not isinstance(value, str) or (not empty and not value.strip())
            or len(value.encode("utf-8")) > maximum
            or any(ord(char) < 32 and (not multiline or char not in "\r\n\t") for char in value)
            or "\x7f" in value):
        raise ValueError("insufficient_source: invalid_sql_context_text")
    return value


def _identifier(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError("invalid_sql_context_identifier")
    return value


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("insufficient_source: invalid_sql_context_number")
    return value


def _boolean_integer(value):
    if type(value) is not int or value not in (0, 1):
        raise ValueError("insufficient_source: invalid_sql_context_flag")
    return value


def _path(value):
    if not isinstance(value, Path) or not value.is_absolute() or ".." in value.parts:
        raise ValueError("invalid_sql_context_path")
    return value


def _checked_stat(path, *, optional=False):
    leaf = None
    for component in reversed((path, *path.parents)):
        try:
            info = component.lstat()
        except FileNotFoundError:
            if optional and component == path:
                return None
            raise
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("insufficient_source: linked_sql_context_path")
        if component != path and not stat.S_ISDIR(info.st_mode):
            raise ValueError("insufficient_source: invalid_sql_context_parent")
        leaf = info
    return leaf


def _canonical_root(path):
    path = _path(path)
    try:
        info = _checked_stat(path)
        canonical = path.resolve(strict=True)
        if not stat.S_ISDIR(info.st_mode) or path != canonical:
            raise ValueError("invalid_sql_context_brain")
        return canonical
    except (OSError, RuntimeError):
        raise ValueError("invalid_sql_context_brain") from None


def _database_identity(path):
    info = _checked_stat(path)
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("insufficient_source: nonregular_sql_context_database")
    # SQLite may read live WAL sidecars. Never follow a linked/reparse sidecar.
    sidecars = {}
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = _checked_stat(path.with_name(path.name + suffix), optional=True)
        if sidecar is not None and not stat.S_ISREG(sidecar.st_mode):
            raise ValueError("insufficient_source: nonregular_sql_context_sidecar")
        sidecars[suffix] = sidecar
    if sidecars["-journal"] is not None and sidecars["-journal"].st_size > 0:
        raise ValueError("insufficient_source: sql_context_hot_journal")
    # Even mode=ro can create reader sidecars. The persistent header records WAL
    # mode after the last writer closes and removes both sidecars, so checking
    # only a currently nonempty -wal file misses an ordinary closed-database case.
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as handle:
        opened = os.fstat(handle.fileno())
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
            raise ValueError("insufficient_source: sql_context_database_replaced")
        header = handle.read(100)
    after = _checked_stat(path)
    if (after.st_dev, after.st_ino) != (info.st_dev, info.st_ino):
        raise ValueError("insufficient_source: sql_context_database_replaced")
    if len(header) != 100 or header[:16] != b"SQLite format 3\x00" or header[18:20] not in (b"\x01\x01", b"\x02\x02"):
        raise ValueError("insufficient_source: unsupported_sql_context_header")
    if ((header[18:20] == b"\x02\x02" or sidecars["-wal"] is not None or sidecars["-shm"] is not None)
            and (sidecars["-wal"] is None or sidecars["-shm"] is None)):
        raise ValueError("insufficient_source: sql_context_wal_sidecars_required")
    # Content/mtime are intentionally absent: live WAL commits/checkpoints are not
    # identity replacement, and unrelated message inserts are not semantic changes.
    return (info.st_dev, info.st_ino, getattr(info, "st_birthtime_ns", None),
            header[18:20] == b"\x02\x02" or sidecars["-wal"] is not None or sidecars["-shm"] is not None)


@contextmanager
def _existing_reader(source):
    connection, started = source.connection, False
    try:
        identity = _database_identity(source.path)
        if connection.in_transaction:
            raise ValueError("sql_context_transaction_active")
        facade = _ReadFacade(connection)
        databases = facade.execute("PRAGMA database_list").fetchall()
        main = [row["file"] for row in databases if row["name"] == "main"]
        if len(main) != 1 or not isinstance(main[0], str) or not main[0] or Path(main[0]) != source.path:
            raise ValueError("sql_context_connection_mismatch")
        connection.execute("BEGIN")
        started = True
        yield facade
        if _database_identity(source.path) != identity:
            raise ValueError("insufficient_source: sql_context_database_replaced")
    except _ScopeError:
        raise
    except (sqlite3.Error, OSError, UnicodeError, RuntimeError):
        raise ValueError("insufficient_source: sql_context_unavailable") from None
    finally:
        if started:
            try:
                connection.rollback()
            except sqlite3.Error:
                raise ValueError("insufficient_source: sql_context_rollback_unavailable") from None


def _schema(connection, table, required, allowed):
    definitions = connection.execute("SELECT name,type,sql FROM main.sqlite_master WHERE name=? COLLATE NOCASE LIMIT 2", (table,)).fetchall()
    if (len(definitions) != 1 or definitions[0]["name"] != table or definitions[0]["type"] != "table"
            or not isinstance(definitions[0]["sql"], str)
            or re.match(r"\s*CREATE\s+VIRTUAL\b", definitions[0]["sql"], re.I)):
        raise ValueError("insufficient_source: unsupported_sql_context_schema")
    columns = connection.execute(f'PRAGMA main.table_xinfo("{table}")').fetchall()
    names = {row["name"] for row in columns}
    if not set(required) <= names or not names <= set(allowed) or any(row["hidden"] != 0 for row in columns):
        raise ValueError("insufficient_source: unsupported_sql_context_schema")


def _one(connection, sql, parameters):
    rows = connection.execute(sql, parameters).fetchmany(2)
    if len(rows) != 1:
        raise ValueError("insufficient_source: missing_or_ambiguous_sql_context")
    return dict(rows[0])


class SQLiteContextProjection:
    """Host-created callable. No client-controlled database, dependency or alias policy."""

    def __init__(self, session_db: Path, workflow_db: Path | None = None, *, default_brain_aliases=None,
                 existing_sources=None, principal_type, redactor):
        if (not isinstance(principal_type, type) or not callable(redactor)
                or inspect.iscoroutinefunction(redactor) or inspect.isasyncgenfunction(redactor)
                or inspect.iscoroutinefunction(getattr(redactor, "__call__", None))):
            raise ValueError("host_sql_context_dependencies_required")
        self.session_db = _path(session_db)
        self.workflow_db = _path(workflow_db) if workflow_db is not None else None
        self.principal_type, self.redactor = principal_type, redactor
        if existing_sources is None:
            existing_sources = {}
        if not isinstance(existing_sources, dict):
            raise ValueError("invalid_existing_sqlite_sources")
        self.existing_sources = {}
        for path, source in existing_sources.items():
            _path(path)
            if (path not in (self.session_db, self.workflow_db) or type(source) is not ExistingSQLiteSource
                    or source.path != path):
                raise ValueError("invalid_existing_sqlite_sources")
            self.existing_sources[path] = source
        if default_brain_aliases is None:
            default_brain_aliases = {}
        if not isinstance(default_brain_aliases, dict) or not set(default_brain_aliases) <= {"brain"}:
            raise ValueError("invalid_sql_context_brain_aliases")
        self.aliases = {alias: _canonical_root(path) for alias, path in default_brain_aliases.items()}

    def _principal(self, principal):
        if (type(principal) is not self.principal_type or getattr(principal, "kind", None) != "owner"
                or not isinstance(getattr(principal, "id", None), str) or not principal.id.strip()
                or not isinstance(getattr(principal, "brain_id", None), str)):
            raise PermissionError("owner_required")
        root = _canonical_root(Path(principal.brain_id))
        if str(root) != principal.brain_id:
            raise PermissionError("canonical_brain_required")
        return root

    def _ownership(self, stored, root):
        _text(stored)
        if stored == str(root):
            return
        alias = self.aliases.get(stored)
        if alias is None or _canonical_root(alias) != root:
            raise _ScopeError("sql_context_cross_brain")

    @staticmethod
    def _assets(connection, table, parent, identifier, *, links=False):
        fields = ("id", "url", "label", "pinned", "added_at") if links else ("id", "path", "name", "pinned", "added_at")
        allowed = set(fields) | {parent}
        _schema(connection, table, allowed, allowed)
        rows = connection.execute(f"SELECT {','.join(fields)} FROM main.{table} WHERE {parent}=? "
                                  "ORDER BY pinned DESC, added_at DESC, rowid DESC LIMIT ?",
                                  (identifier, MAX_CONTEXT_ROWS + 1)).fetchall()
        if len(rows) > MAX_CONTEXT_ROWS:
            raise ValueError("insufficient_source: sql_context_inventory_too_large")
        result, identifiers, refs = [], set(), set()
        for row in rows:
            item = dict(row)
            _identifier(item["id"])
            ref = _text(item["url"] if links else item["path"])
            _text(item["label"] if links else item["name"], 4000, empty=True, nullable=links)
            _boolean_integer(item["pinned"])
            _number(item["added_at"])
            key = ref if links else ref.casefold()
            if item["id"] in identifiers or key in refs:
                raise ValueError("insufficient_source: duplicate_sql_context_membership")
            identifiers.add(item["id"])
            refs.add(key)
            result.append(item)
        return result

    def capture(self, principal, session_id, project_id="") -> dict:
        root = self._principal(principal)
        _identifier(session_id)
        if project_id != "":
            _identifier(project_id)
        with ExitStack() as stack:
            paths = list(dict.fromkeys(path for path in (self.session_db, self.workflow_db) if path is not None))
            if any(path not in self.existing_sources for path in paths):
                raise ValueError("sql_context_lifetime_required")
            held_locks = set()
            for path in sorted(paths, key=lambda item: (str(item).casefold(), str(item))):
                source = self.existing_sources[path]
                if id(source.lock) not in held_locks:
                    stack.enter_context(source.lock)
                    held_locks.add(id(source.lock))
            readers = {}
            for path in paths:
                readers[path] = stack.enter_context(_existing_reader(self.existing_sources[path]))
            connection = readers[self.session_db]
            workflow = readers[self.workflow_db] if self.workflow_db is not None else None
            _schema(connection, "sessions", _SESSION_FIELDS, _SESSION_COLUMNS)
            _schema(connection, "projects", _PROJECT_FIELDS, _PROJECT_COLUMNS)
            # Even an empty inventory must be observed, never inferred from a
            # missing table in an old/corrupt database.
            for table, parent, links in (("project_files", "project_id", False), ("project_links", "project_id", True),
                                         ("session_files", "session_id", False), ("session_links", "session_id", True)):
                fields = {"id", "url", "label", "pinned", "added_at"} if links else {"id", "path", "name", "pinned", "added_at"}
                _schema(connection, table, fields | {parent}, fields | {parent})
            if workflow is not None:
                _schema(workflow, "workflow_runs", _WORKFLOW_FIELDS, _WORKFLOW_COLUMNS)
            session = _one(connection, f"SELECT {','.join(_SESSION_FIELDS)} FROM main.sessions WHERE id=? LIMIT 2", (session_id,))
            _identifier(session["id"])
            self._ownership(session["brain"], root)
            if session["channel"] != "web" or _boolean_integer(session["archived"]) != 0:
                raise ValueError("unsupported_trial_surface")
            for field in ("engine", "model", "pinned_provider", "pinned_model"):
                _text(session[field], 512, empty=True, nullable=True)
            if session["project_id"] is not None and session["project_id"] != "":
                _identifier(session["project_id"])
            if project_id != (session["project_id"] or ""):
                raise _ScopeError("sql_context_project_mismatch")
            project, project_files, project_links = None, [], []
            if project_id:
                project = _one(connection, f"SELECT {','.join(_PROJECT_FIELDS)} FROM main.projects WHERE id=? LIMIT 2", (project_id,))
                _identifier(project["id"])
                self._ownership(project["brain"], root)
                _text(project["name"], 4000)
                _text(project["instructions"], MAX_CONTEXT_BYTES, empty=True, multiline=True, nullable=True)
                project_files = self._assets(connection, "project_files", "project_id", project_id)
                project_links = self._assets(connection, "project_links", "project_id", project_id, links=True)
            session_files = self._assets(connection, "session_files", "session_id", session_id)
            session_links = self._assets(connection, "session_links", "session_id", session_id, links=True)
            latest = None
            if workflow is not None:
                rows = workflow.execute(f"SELECT {','.join(_WORKFLOW_FIELDS)} FROM main.workflow_runs WHERE brain=? "
                                        "ORDER BY started_at DESC,rowid DESC LIMIT 1", (str(root),)).fetchall()
                if rows:
                    latest = dict(rows[0])
                    _identifier(latest["id"])
                    self._ownership(latest["brain"], root)
                    _text(latest["name"], 4000, empty=True)
                    _number(latest["started_at"])
                    if latest["status"] not in {"running", "done", "error", "waiting"}:
                        raise ValueError("insufficient_source: unsupported_workflow_status")
                    _one(workflow, "SELECT id FROM main.workflow_runs WHERE id=? LIMIT 2", (latest["id"],))
            result = {"version": 1, "session": session, "project": project, "project_files": project_files,
                      "project_links": project_links, "session_files": session_files, "session_links": session_links,
                      "latest_workflow": latest}
            raw = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
            if len(raw) > MAX_CONTEXT_BYTES:
                raise ValueError("insufficient_source: sql_context_too_large")
            # A host redactor must reject capture when meaning would change. Give
            # it an independent JSON value so an in-place implementation cannot
            # mutate both sides of the comparison or rewrite captured owner rules.
            if self.redactor(json.loads(raw)) != result:
                raise ValueError("insufficient_source: credential_bearing_sql_context")
            return result

    __call__ = capture
