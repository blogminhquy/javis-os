"""Derived, rebuildable memory index for Adaptive Context Runtime Phase 8.

Markdown files remain the source of truth. This module stores bounded excerpts and
relative source references only; deleting the database never deletes memory files.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import time
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from capability_registry import brain_scope
from context_compiler import ContextItem, HeuristicTokenizer

INDEX_SCHEMA_VERSION = "memory-index-v2"   # v2: line-ref theo dòng thật của file
INDEX_POLICY_VERSION = "memory-retrieval-cascade-v1"
_WORD_RE = re.compile(r"[^\W_]{2,}", re.UNICODE)
_WIKI_RE = re.compile(r"\[\[([^\]|#]+)")
_CODE_RE = re.compile(r"`([^`]{2,80})`")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_MEMORY_HINT_RE = re.compile(
    r"\b(nhớ|memory|trước đây|lần trước|đã nói|hôm trước|của anh|của tôi|"
    r"remember|previously|last time|my preference|we decided)\b", re.IGNORECASE,
)


def _sha(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8", errors="replace")).hexdigest()


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _norm(value: str) -> str:
    # "đ" không phân rã qua NFKD - map tay để token hai phía (index và query) nhất quán.
    raw = str(value or "").replace("đ", "d").replace("Đ", "D")
    raw = unicodedata.normalize("NFKD", raw.casefold())
    return " ".join(_WORD_RE.findall("".join(c for c in raw if not unicodedata.combining(c))))


def _terms(value: str) -> list[str]:
    stop = {"cua", "cho", "voi", "nhung", "mot", "nay", "kia", "the", "anh", "toi",
            "co", "khong", "la", "gi", "nho", "and", "for", "that", "what", "does"}
    return [x for x in dict.fromkeys(_norm(value).split()) if x not in stop]


def _memory_dir(brain: Path) -> Path:
    canonical = brain / "memory"
    legacy = brain / "Memory"
    return canonical if canonical.is_dir() or not legacy.is_dir() else legacy


@dataclass(frozen=True)
class MemoryRetrieval:
    records: tuple[dict, ...]
    confidence: float
    coverage: float
    stages: tuple[str, ...]
    widened: bool
    fallback_required: bool
    fallback_reason: str
    conflicts: tuple[tuple[str, str], ...]
    index_revision: str

    def context_items(self, chars_per_token: float = 3.0) -> tuple[ContextItem, ...]:
        tokenizer = HeuristicTokenizer("memory", "derived", chars_per_token)
        items = []
        conflict_map: dict[str, list[str]] = {}
        for left, right in self.conflicts:
            conflict_map.setdefault(left, []).append(right)
            conflict_map.setdefault(right, []).append(left)
        for rank, record in enumerate(self.records):
            source_refs = record.get("source_refs") or []
            source_ref = source_refs[0] if source_refs else "memory:unknown"
            content = (
                f"Memory fact (source: {source_ref}):\n{record.get('detail') or record.get('excerpt') or ''}"
            )
            items.append(ContextItem(
                id=str(record["record_id"]), kind="retrieved_memory", content=content,
                source_ref=source_ref, token_cost=tokenizer.count_text(content),
                relevance=max(0.2, 1.0 - rank * 0.08),
                confidence=float(record.get("retrieval_score") or self.confidence or 0.5),
                authority=float(record.get("importance") or 0.7), freshness=1.0,
                required=False, trust="memory_source",
                conflicts_with=tuple(conflict_map.get(str(record["record_id"]), [])),
                metadata={"index_revision": self.index_revision,
                          "source_hash": record.get("source_hash") or ""},
            ))
        return tuple(items)


class MemoryIndex:
    def __init__(self, state_dir: str | Path):
        self.state_dir = Path(state_dir)
        self.path = self.state_dir / "memory_index.db"
        self._db: sqlite3.Connection | None = None
        self._lock = threading.RLock()
        self._fts = True

    def _conn(self) -> sqlite3.Connection:
        with self._lock:
            if self._db is not None:
                return self._db
            self.state_dir.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(str(self.path), timeout=10, check_same_thread=False)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS index_meta(
                    scope TEXT PRIMARY KEY, schema_version TEXT NOT NULL,
                    source_fingerprint TEXT NOT NULL, revision TEXT NOT NULL,
                    source_count INTEGER NOT NULL, record_count INTEGER NOT NULL,
                    rebuilt_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_sources(
                    scope TEXT NOT NULL, source_path TEXT NOT NULL, source_hash TEXT NOT NULL,
                    record_count INTEGER NOT NULL, PRIMARY KEY(scope,source_path)
                );
                CREATE TABLE IF NOT EXISTS memory_records(
                    record_id TEXT PRIMARY KEY, scope TEXT NOT NULL, title TEXT NOT NULL,
                    content_ref TEXT NOT NULL, excerpt TEXT NOT NULL, normalized TEXT NOT NULL,
                    topics_json TEXT NOT NULL, entities_json TEXT NOT NULL,
                    valid_from TEXT, valid_to TEXT, confidence REAL NOT NULL,
                    importance REAL NOT NULL, source_refs_json TEXT NOT NULL,
                    source_hash TEXT NOT NULL, subject TEXT NOT NULL, always_on INTEGER NOT NULL,
                    line_start INTEGER NOT NULL, line_end INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_records_scope
                    ON memory_records(scope,always_on,subject);
                CREATE TABLE IF NOT EXISTS memory_links(
                    scope TEXT NOT NULL, left_id TEXT NOT NULL, right_id TEXT NOT NULL,
                    relation TEXT NOT NULL, weight REAL NOT NULL,
                    PRIMARY KEY(scope,left_id,right_id)
                );
                """
            )
            try:
                db.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS memory_records_fts USING fts5("
                    "record_id UNINDEXED,title,excerpt,topics,entities,"
                    "tokenize='unicode61 remove_diacritics 2')"
                )
                self._fts = True
            except sqlite3.OperationalError:
                self._fts = False
            db.commit()
            self._db = db
            return db

    def close(self) -> None:
        with self._lock:
            if self._db is not None:
                self._db.close()
                self._db = None

    @staticmethod
    def _frontmatter(lines: list[str]) -> tuple[dict, int]:
        if not lines or lines[0].strip() != "---":
            return {}, 0
        end = next((i for i in range(1, min(len(lines), 200)) if lines[i].strip() == "---"), -1)
        if end < 0:
            return {}, 0
        meta = {}
        for line in lines[1:end]:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip().casefold()
            value = value.strip().strip("'\"")
            if key:
                meta[key] = value
        return meta, end + 1

    @classmethod
    def _chunks(cls, text: str, relative: str, source_hash: str) -> list[dict]:
        lines = text.splitlines()
        meta, start = cls._frontmatter(lines)
        default_title = str(meta.get("title") or Path(relative).stem)
        current_title = default_title
        blocks: list[tuple[str, int, int, str]] = []
        # Buffer giữ (số dòng 1-based, nội dung) để ref file:#Lx-Ly luôn trỏ đúng dòng
        # THẬT. Bản cũ đếm dòng bằng cách cộng dồn số newline sau khi đã strip dòng
        # trống, nên mọi đoạn từ thứ hai trở đi lệch dần và _read_detail có thể đọc
        # nhầm sang fact khác rồi thay thế excerpt đúng.
        buffer: list[tuple[int, str]] = []

        def flush(_end_line: int):
            nonlocal buffer
            paragraph: list[tuple[int, str]] = []

            def emit(para: list[tuple[int, str]]):
                if not para:
                    return
                chunk: list[tuple[int, str]] = []
                size = 0
                for lineno, content in para:
                    if chunk and size + len(content) + 1 > 1400:
                        text_chunk = "\n".join(x[1] for x in chunk).strip()
                        if text_chunk:
                            blocks.append((current_title, chunk[0][0], chunk[-1][0], text_chunk))
                        chunk, size = [], 0
                    if len(content) > 1400:
                        # Dòng đơn quá dài: cắt theo ký tự nhưng giữ nguyên số dòng.
                        for offset in range(0, len(content), 1400):
                            piece = content[offset:offset + 1400].strip()
                            if piece:
                                blocks.append((current_title, lineno, lineno, piece))
                        continue
                    chunk.append((lineno, content))
                    size += len(content) + 1
                text_chunk = "\n".join(x[1] for x in chunk).strip()
                if text_chunk:
                    blocks.append((current_title, chunk[0][0], chunk[-1][0], text_chunk))

            for lineno, content in buffer:
                if content.strip():
                    paragraph.append((lineno, content))
                else:
                    emit(paragraph)
                    paragraph = []
            emit(paragraph)
            buffer = []

        for index in range(start, len(lines)):
            match = _HEADING_RE.match(lines[index])
            if match:
                flush(index)
                current_title = match.group(2).strip()[:240]
            else:
                buffer.append((index + 1, lines[index]))
        flush(len(lines))
        if not blocks and text.strip():
            blocks = [(default_title, 1, min(len(lines), 1), text.strip()[:1400])]

        records = []
        for title, line_start, line_end, excerpt in blocks:
            clean = re.sub(r"\s+", " ", excerpt).strip()
            if len(clean) < 8:
                continue
            entities = list(dict.fromkeys(
                [x.strip() for x in _WIKI_RE.findall(excerpt) + _CODE_RE.findall(excerpt) if x.strip()]
            ))[:20]
            topic_seed = str(meta.get("topics") or meta.get("tags") or "") + " " + title
            topics = _terms(topic_seed)[:20]
            subject_match = re.match(r"^[-*]?\s*([^:\n=]{2,100})\s*[:=]", clean)
            subject = _norm(subject_match.group(1) if subject_match else title)[:160]
            lower_rel = relative.casefold()
            always_on = str(meta.get("always_on") or "").casefold() in ("1", "true", "yes", "on")
            always_on = always_on or any(x in lower_rel for x in ("identity", "profile", "core-facts"))
            source_ref = f"file:{relative}#L{line_start}-L{line_end}"
            record_id = "mem_" + _sha(f"{relative}|{line_start}|{clean}")[:24]
            records.append({
                "record_id": record_id, "title": title, "content_ref": relative,
                "excerpt": clean, "normalized": _norm(title + " " + clean),
                "topics": topics, "entities": entities,
                "valid_from": meta.get("valid_from") or None,
                "valid_to": meta.get("valid_to") or None,
                "confidence": float(meta.get("confidence") or 0.8) if str(meta.get("confidence") or "").replace(".", "", 1).isdigit() else 0.8,
                "importance": float(meta.get("importance") or (1.0 if always_on else 0.7)) if str(meta.get("importance") or "").replace(".", "", 1).isdigit() else (1.0 if always_on else 0.7),
                "source_refs": [source_ref], "source_hash": source_hash,
                "subject": subject, "always_on": int(always_on),
                "line_start": line_start, "line_end": line_end,
            })
        return records

    @staticmethod
    def _source_paths(brain: Path) -> tuple[Path, list[tuple[str, Path, int, int]]]:
        memory_dir = _memory_dir(brain)
        files = []
        if memory_dir.is_dir():
            for path in sorted(memory_dir.rglob("*.md")):
                try:
                    relative_mem = path.relative_to(memory_dir).as_posix()
                    if relative_mem.casefold().startswith("conversations/"):
                        continue
                    stat = path.stat()
                    relative = path.relative_to(brain).as_posix()
                    files.append((relative, path, stat.st_mtime_ns, stat.st_size))
                except (OSError, ValueError):
                    continue
        return memory_dir, files

    def rebuild(self, brain: str | Path, force: bool = False) -> dict:
        brain = Path(brain).resolve()
        scope = brain_scope(brain)
        _mem_dir, paths = self._source_paths(brain)
        # Stat-only fast gate: unchanged memory does not reread every Markdown body per turn.
        fingerprint = _sha(_json([(rel, mtime_ns, size)
                                  for rel, _path, mtime_ns, size in paths]))
        db = self._conn()
        with self._lock:
            previous = db.execute("SELECT * FROM index_meta WHERE scope=?", (scope,)).fetchone()
            # Fingerprint chỉ bắt file đổi. Nâng cấp code (đổi cách chunk, đổi cách
            # chấm điểm) không đổi file nào, nên phải so schema_version, nếu không
            # index cũ sai vẫn được phục vụ mãi dù bản vá đã lên.
            if (previous and previous["source_fingerprint"] == fingerprint and not force and
                    previous["schema_version"] == INDEX_SCHEMA_VERSION):
                return {"rebuilt": False, "revision": previous["revision"],
                        "source_count": previous["source_count"], "record_count": previous["record_count"]}
            files = []
            for relative, path, _mtime_ns, _size in paths:
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                files.append((relative, path, text, _sha(text)))
            all_records = []
            source_rows = []
            for relative, _path, text, source_hash in files:
                records = self._chunks(text, relative, source_hash)
                all_records.extend(records)
                source_rows.append((relative, source_hash, len(records)))
            revision = "memory_" + _sha(_json([
                (x["record_id"], x["source_hash"]) for x in all_records
            ]))[:24]
            with db:
                old_ids = [r[0] for r in db.execute(
                    "SELECT record_id FROM memory_records WHERE scope=?", (scope,)
                )]
                if self._fts:
                    for record_id in old_ids:
                        db.execute("DELETE FROM memory_records_fts WHERE record_id=?", (record_id,))
                db.execute("DELETE FROM memory_links WHERE scope=?", (scope,))
                db.execute("DELETE FROM memory_records WHERE scope=?", (scope,))
                db.execute("DELETE FROM memory_sources WHERE scope=?", (scope,))
                for relative, source_hash, count in source_rows:
                    db.execute("INSERT INTO memory_sources VALUES(?,?,?,?)",
                               (scope, relative, source_hash, count))
                for item in all_records:
                    db.execute(
                        "INSERT INTO memory_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (item["record_id"], scope, item["title"], item["content_ref"], item["excerpt"],
                         item["normalized"], _json(item["topics"]), _json(item["entities"]),
                         item["valid_from"], item["valid_to"], item["confidence"], item["importance"],
                         _json(item["source_refs"]), item["source_hash"], item["subject"],
                         item["always_on"], item["line_start"], item["line_end"]),
                    )
                    if self._fts:
                        db.execute("INSERT INTO memory_records_fts VALUES(?,?,?,?,?)", (
                            item["record_id"], item["title"], item["excerpt"],
                            " ".join(item["topics"]), " ".join(item["entities"]),
                        ))
                # Bounded inverted graph. Avoid O(n²) rebuild when memory grows large;
                # generic postings are ignored and each record keeps at most 12 neighbors.
                postings: dict[tuple[str, str], list[str]] = {}
                by_id = {item["record_id"]: item for item in all_records}
                for item in all_records:
                    for entity in {_norm(x) for x in item["entities"] if _norm(x)}:
                        postings.setdefault(("entity", entity), []).append(item["record_id"])
                    for topic in set(item["topics"]):
                        postings.setdefault(("topic", topic), []).append(item["record_id"])
                for left in all_records:
                    scores: dict[str, tuple[float, str]] = {}
                    keys = [("entity", _norm(x)) for x in left["entities"] if _norm(x)]
                    keys += [("topic", x) for x in set(left["topics"])]
                    for relation, key in keys:
                        neighbors = postings.get((relation, key), [])
                        cap = 200 if relation == "entity" else 80
                        if len(neighbors) > cap:
                            continue
                        increment = 0.75 if relation == "entity" else 0.2
                        for right_id in neighbors:
                            if right_id == left["record_id"] or right_id not in by_id:
                                continue
                            previous_score, previous_relation = scores.get(right_id, (0.0, relation))
                            scores[right_id] = (min(1.0, previous_score + increment),
                                                "entity" if relation == "entity" else previous_relation)
                    for right_id, (weight, relation) in sorted(
                            scores.items(), key=lambda pair: (-pair[1][0], pair[0]))[:12]:
                        db.execute("INSERT OR IGNORE INTO memory_links VALUES(?,?,?,?,?)",
                                   (scope, left["record_id"], right_id, relation, weight))
                db.execute(
                    "INSERT INTO index_meta VALUES(?,?,?,?,?,?,?) ON CONFLICT(scope) DO UPDATE SET "
                    "schema_version=excluded.schema_version,source_fingerprint=excluded.source_fingerprint,"
                    "revision=excluded.revision,source_count=excluded.source_count,"
                    "record_count=excluded.record_count,rebuilt_at=excluded.rebuilt_at",
                    (scope, INDEX_SCHEMA_VERSION, fingerprint, revision, len(files), len(all_records), time.time()),
                )
            return {"rebuilt": True, "revision": revision, "source_count": len(files),
                    "record_count": len(all_records)}

    @staticmethod
    def _row(row: sqlite3.Row) -> dict:
        item = dict(row)
        item["topics"] = json.loads(item.pop("topics_json") or "[]")
        item["entities"] = json.loads(item.pop("entities_json") or "[]")
        item["source_refs"] = json.loads(item.pop("source_refs_json") or "[]")
        item["always_on"] = bool(item.get("always_on"))
        return item

    def _read_detail(self, brain: Path, record: dict) -> str:
        try:
            path = (brain / record["content_ref"]).resolve()
            path.relative_to(brain.resolve())
            text = path.read_text(encoding="utf-8", errors="replace")
            if _sha(text) != record["source_hash"]:
                return ""
            lines = text.splitlines()
            start = max(0, int(record["line_start"]) - 1)
            end = min(len(lines), int(record["line_end"]))
            return re.sub(r"\s+", " ", "\n".join(lines[start:end])).strip()[:1800]
        except (OSError, ValueError, KeyError):
            return ""

    def retrieve(self, brain: str | Path, query: str, active_state: Iterable[str] = (),
                 limit: int = 6, min_confidence: float = 0.38) -> MemoryRetrieval:
        brain = Path(brain).resolve()
        meta = self.rebuild(brain)
        scope = brain_scope(brain)
        db = self._conn()
        current_terms = _terms(str(query or ""))[:16]
        query_text = " ".join([str(query or "")] + [str(x) for x in active_state or []])
        terms = list(dict.fromkeys(current_terms + _terms(query_text)))[:24]
        coverage_terms = current_terms or terms
        stages = ["active_task_state"] if list(active_state or []) else []
        selected: dict[str, dict] = {}

        with self._lock:
            core_rows = db.execute(
                "SELECT * FROM memory_records WHERE scope=? AND always_on=1 "
                "ORDER BY importance DESC,record_id LIMIT 3", (scope,)
            ).fetchall()
            for row in core_rows:
                item = self._row(row); item["retrieval_score"] = 0.92
                selected[item["record_id"]] = item
            if core_rows:
                stages.append("identity_core")

            exact_rows = []
            for term in terms[:8]:
                exact_rows.extend(db.execute(
                    "SELECT * FROM memory_records WHERE scope=? AND "
                    "(normalized LIKE ? OR lower(entities_json) LIKE ?) LIMIT 20",
                    (scope, f"%{term}%", f"%{term}%"),
                ).fetchall())
            exact_seen = set()
            for row in exact_rows:
                item = self._row(row)
                if item["record_id"] in exact_seen:
                    continue
                exact_seen.add(item["record_id"])
                hit = len(set(terms) & set(item["normalized"].split())) / max(1, len(terms))
                entity_hit = any(_norm(entity) in set(terms) for entity in item.get("entities") or [])
                item["retrieval_score"] = min(0.98, 0.22 + hit * 0.72 + (0.14 if entity_hit else 0))
                selected[item["record_id"]] = item
            if exact_seen:
                stages.append("exact_keyword_entity")

            if self._fts and terms:
                match = " OR ".join('"' + t.replace('"', '') + '"*' for t in terms)
                try:
                    fts_rows = db.execute(
                        "SELECT r.*,bm25(memory_records_fts) AS fts_rank FROM memory_records_fts "
                        "JOIN memory_records r ON r.record_id=memory_records_fts.record_id "
                        "WHERE memory_records_fts MATCH ? AND r.scope=? ORDER BY fts_rank LIMIT 20",
                        (match, scope),
                    ).fetchall()
                except sqlite3.OperationalError:
                    fts_rows = []
                for rank, row in enumerate(fts_rows):
                    item = self._row(row)
                    overlap = len(set(terms) & set(item["normalized"].split())) / max(1, len(terms))
                    fts_score = max(0.18, 0.20 + overlap * 0.72 - rank * 0.01)
                    item["retrieval_score"] = max(
                        float(selected.get(item["record_id"], {}).get("retrieval_score") or 0),
                        fts_score,
                    )
                    selected[item["record_id"]] = item
                if fts_rows:
                    stages.append("fts_semantic")

            ranked = sorted(selected.values(), key=lambda x: (
                -float(x.get("retrieval_score") or 0), -float(x.get("importance") or 0), x["record_id"]
            ))
            combined = " ".join(x.get("normalized") or "" for x in ranked)
            coverage = (len(set(coverage_terms) & set(combined.split())) /
                        max(1, len(set(coverage_terms)))) if coverage_terms else 1.0
            widened = False
            if ranked and coverage < 0.65:
                seed_ids = [x["record_id"] for x in ranked[:4]]
                marks = ",".join("?" for _ in seed_ids)
                links = db.execute(
                    f"SELECT right_id,MAX(weight) weight FROM memory_links WHERE scope=? "
                    f"AND left_id IN ({marks}) GROUP BY right_id ORDER BY weight DESC LIMIT 12",
                    (scope, *seed_ids),
                ).fetchall() if seed_ids else []
                for link in links:
                    if link["right_id"] in selected:
                        continue
                    row = db.execute("SELECT * FROM memory_records WHERE record_id=? AND scope=?",
                                     (link["right_id"], scope)).fetchone()
                    if row:
                        item = self._row(row); item["retrieval_score"] = 0.28 + 0.25 * float(link["weight"])
                        selected[item["record_id"]] = item
                if links:
                    widened = True; stages.append("graph_widening")

        ranked = sorted(selected.values(), key=lambda x: (
            -float(x.get("retrieval_score") or 0), -float(x.get("importance") or 0), x["record_id"]
        ))[:max(1, min(int(limit or 6), 12))]
        combined = " ".join(x.get("normalized") or "" for x in ranked)
        coverage = (len(set(coverage_terms) & set(combined.split())) /
                    max(1, len(set(coverage_terms)))) if coverage_terms else 1.0
        conflicts = []
        by_subject: dict[str, list[dict]] = {}
        for item in ranked:
            if item.get("subject"):
                by_subject.setdefault(item["subject"], []).append(item)
        for group in by_subject.values():
            for index, left in enumerate(group):
                for right in group[index + 1:]:
                    if left["source_hash"] != right["source_hash"] and left["normalized"] != right["normalized"]:
                        conflicts.append((left["record_id"], right["record_id"]))

        # Source-file reads are the last cascade stage and validate stale/conflicting excerpts.
        source_read = False
        for item in ranked:
            if conflicts or float(item.get("retrieval_score") or 0) >= 0.55:
                detail = self._read_detail(brain, item)
                if detail:
                    item["detail"] = detail
                    source_read = True
        if source_read:
            stages.append("source_file_read")

        non_core = [x for x in ranked if not x.get("always_on")]
        top = max((float(x.get("retrieval_score") or 0) for x in non_core), default=0.0)
        confidence = min(1.0, top * 0.65 + coverage * 0.35) if non_core else (0.9 if ranked else 0.0)
        needs_memory = bool(_MEMORY_HINT_RE.search(str(query or "")))
        fallback = bool(needs_memory and (not non_core or confidence < min_confidence))
        reason = "low_confidence" if fallback and non_core else ("no_relevant_memory" if fallback else "")
        return MemoryRetrieval(
            records=tuple(ranked), confidence=round(confidence, 6), coverage=round(coverage, 6),
            stages=tuple(dict.fromkeys(stages)), widened=widened,
            fallback_required=fallback, fallback_reason=reason,
            conflicts=tuple(conflicts), index_revision=str(meta.get("revision") or ""),
        )

    def integrity_check(self, brain: str | Path) -> dict:
        scope = brain_scope(Path(brain).resolve())
        db = self._conn()
        row = db.execute("SELECT * FROM index_meta WHERE scope=?", (scope,)).fetchone()
        quick = db.execute("PRAGMA quick_check").fetchone()[0]
        count = db.execute("SELECT COUNT(*) FROM memory_records WHERE scope=?", (scope,)).fetchone()[0]
        return {"ok": quick == "ok" and bool(row) and count == (row["record_count"] if row else -1),
                "quick_check": quick, "record_count": count,
                "revision": row["revision"] if row else "", "schema_version": INDEX_SCHEMA_VERSION}
