"""Nhịp thích nghi của agent, lớp 3 (T3, 0.156.0), chính sách `pulse.v1`.

Thiết kế: docs/superpowers/specs/2026-10-15-team-adaptive-design.md mục 5 (nhịp), 6 (ước lượng hữu ích), 9 (`max_tier`),
12 (di trú). Hợp đồng giữa ba phần T3: docs/dev/team-chat-t3-contract.md mục 1. Tài liệu: docs/dev/team-chat-t3-pulse.md.

Module có hai lớp:
- Hàm THUẦN (không kho, không đồng hồ thật): `compute_k`, `reaction_signal`, `score`, `decide`, `attribute`,
  `effective_due`, `state_for_tier`. Mọi vectơ số của mục 5.3 kiểm trên các hàm này với đồng hồ giả.
- Thao tác kho trên `resonance.sqlite3` (một `resonance_store.GoalStore`), tự tạo bảng của mình (`ensure`):
  `agent_pulse_events`, `pulse_signals` UNIQUE(source_ref, agent_key), `pulse_contrib`, `message_seen`,
  `pulse_opportunities`, `pulse_proactive`, `pulse_policy_changes`, `pulse_meta`, và cột thêm cho `agent_pulse` (bảng của
  T2). Mọi ghi đi qua `GoalStore._Tx` (BEGIN IMMEDIATE).

Ba điều không bao giờ xảy ra ở đây: nghĩa vụ (việc đã nhận, hạn chót, goal, lời gọi trực tiếp) không đọc bảng này nên không
bị làm chậm; reaction của agent không thành tín hiệu; bậc không nhanh hơn `max_tier` do chủ cấp (trưởng nhóm, kể cả Toàn
quyền, không nâng được).
"""
from __future__ import annotations

import json
import math
import time
from contextlib import closing
from typing import Any, Callable, Iterable, Optional

POLICY_VERSION = "pulse.v1"

# Thang bậc (5.2): B0 15 phút ... B7 1 tháng; bậc 8 là ngủ đông (không có lịch chủ động).
TIERS = (900, 3600, 14400, 86400, 3 * 86400, 7 * 86400, 14 * 86400, 30 * 86400)
HIBERNATE = 8
INIT_TIER = 3
DEFAULT_MAX_TIER = 1
DAY = 86400.0
HALF_LIFE_DAYS = 21.0
PRIOR_MASS = 2.0          # estimate = Σ w·v·decay / (Σ w·decay + 2)
CONF_MASS = 4.0           # confidence = n_eff / (n_eff + 4)
UP_U = 0.25
DOWN_U = -0.25
NEW_MIN = 1.0
BUSY_DEFER_S = 60.0       # effective_due: agent đang bận thì dời 60 giây (3.3)
CLAIM_S = 900.0           # lease 15 phút (3.4): lớn hơn hạn một lượt quét (9 phút) và mốc đối soát sổ lượt (10 phút)
SCAN_EVERY = 3            # quét giới hạn mỗi 3 lần thức ở active/awake
SCAN_MIN_GAP_S = DAY      # tối đa một lượt quét giới hạn mỗi ngày mỗi ngữ cảnh
SEEN_WAIT_S = DAY         # tin chủ động đã xem, qua 24 giờ không tương tác
WAITING_REMIND_S = DAY    # chờ chủ: nhắc một lần sau 24 giờ
LONG_QUIET_S = 3 * DAY    # luật low_demand (B): im lâu hơn max(4 x khoảng, 3 ngày)
LONG_QUIET_X = 4
CONTEXT_INIT_FACTOR = 0.5
POLICY_WINDOW_S = 14 * DAY

STATES = ("active", "awake", "slowed", "hibernating", "waiting_owner", "paused", "off")
SCHEDULED = ("active", "awake", "slowed")
TIER_STATES = ("active", "awake", "slowed", "hibernating")

# Bảng tín hiệu 6.1 (giả thuyết khởi tạo `pulse.v1`): (giá trị v0, độ tin nguồn w).
EMOJI_SIGNAL = {"love": (0.8, 1.0), "wow": (0.6, 1.0), "like": (0.4, 1.0), "haha": (0.2, 0.5),
                "sad": (-0.2, 0.4), "angry": (-0.4, 0.4)}
REASON_VALUE = {"on_point": 0.8, "too_long": -0.3, "wrong_facts": -0.6, "missing": -0.6, "unclear": -0.6,
                "off_topic": -0.6}
HOST_EVENT = {"accept": (0.6, 0.8), "decision": (0.6, 0.8), "result_used": (0.6, 0.8),
              "revise": (-0.4, 0.8), "cancel": (-0.4, 0.8), "reject": (-0.4, 0.8), "revoke": (-0.4, 0.8),
              "objective_pass": (0.5, 0.8), "objective_fail": (-0.5, 0.8)}
SEEN_IGNORED = (-0.15, 0.6)
SIGNAL_KINDS = ("reaction", "reaction_reason", "host_event", "seen_ignored", "context_init")
# Không phải "bằng chứng mới" (không đẩy bậc, không chặn low_demand): giá trị khởi tạo ngữ cảnh.
_NOT_EVIDENCE = ("context_init",)
# Không chặn luật low_demand: tin chủ động bị bỏ qua là ít nhu cầu, không phải tương tác.
_NOT_ENGAGEMENT = ("context_init", "seen_ignored")

_K_SMOOTH_ADD = 3.0
_K_SMOOTH_N = 18.0
_K_PBAR = 1.0 / 6.0
_K_GAIN = 0.3
_K_N0 = 20.0
K_MIN, K_MAX = 0.75, 1.25

# Phần cùng phân bổ (6.5).
CONTRIB_INPUTS = 0.8
CONTRIB_SYNTH = 0.2
CONTRIB_CAP = 0.6

_POLICY_REVERTERS: dict = {}


def _now(at: Optional[float]) -> float:
    return time.time() if at is None else float(at)


def _j(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def _jl(s: Any, default: Any) -> Any:
    try:
        return json.loads(s) if s else default
    except Exception:  # noqa: BLE001
        return default


# ═════════════════════════════ hàm thuần ═════════════════════════════

def interval(tier: int) -> Optional[float]:
    """Khoảng của bậc (giây); None ở ngủ đông."""
    t = int(tier)
    return float(TIERS[t]) if 0 <= t < len(TIERS) else None


def state_for_tier(tier: int) -> str:
    t = int(tier)
    if t >= HIBERNATE:
        return "hibernating"
    if t <= 2:
        return "active"
    if t <= 4:
        return "awake"
    return "slowed"


def ctx_kind(context_ref: str) -> str:
    c = str(context_ref or "")
    return "team" if c.startswith("team:") else "dm" if c.startswith("dm:") else ""


def decay(age_s: float) -> float:
    """Suy giảm theo nửa đời 21 ngày. Tuổi âm (lệch đồng hồ) kẹp về 0."""
    return 0.5 ** (max(0.0, float(age_s)) / DAY / HALF_LIFE_DAYS)


def compute_k(n: int, count_e: int) -> float:
    """Cá nhân hoá theo người phản hồi và loại ngữ cảnh (6.3), chỉ cho reaction KHÔNG lý do:
    `p_s(e) = (count_e + 3)/(n + 18)`, `k = clamp(1 + 0.3 × (p̄ − p_s)/p̄ × n/(n + 20), 0.75, 1.25)`."""
    n = max(0, int(n))
    ps = (max(0, int(count_e)) + _K_SMOOTH_ADD) / (n + _K_SMOOTH_N)
    k = 1.0 + _K_GAIN * (_K_PBAR - ps) / _K_PBAR * (n / (n + _K_N0))
    return min(K_MAX, max(K_MIN, k))


def reaction_signal(value: Optional[str], reasons: Iterable[str] = ()) -> Optional[tuple]:
    """(kind, v0, w, personalize) của một reaction của CHỦ, hay None khi không tạo tín hiệu (chỉ trục nói/im, chỉ góp ý
    chữ, bỏ hết). Lý do chất lượng THẮNG emoji (`k = 1`); nhiều lý do thì lấy trung bình giá trị của chúng."""
    rs = [r for r in (reasons or []) if r in REASON_VALUE]
    if rs:
        return "reaction_reason", sum(REASON_VALUE[r] for r in rs) / len(rs), 1.0, False
    if value in EMOJI_SIGNAL:
        v0, w = EMOJI_SIGNAL[value]
        return "reaction", v0, w, True
    return None


def score(signals: Iterable[dict], now: float, k_of: Optional[Callable[[dict], float]] = None,
          since: float = 0.0) -> dict:
    """Ước lượng hữu ích (6.3) từ các tín hiệu SỐNG của một ngữ cảnh. Mỗi tín hiệu: {value, w, share, at, kind,
    personalize, ...}; `k_of(sig)` trả `k` (tính lại mỗi kỳ). `since`: mốc của "bằng chứng mới" (max(last_change_at,
    resumed_at)). Trả {estimate, confidence, n_eff, u, new, engagement_new, last_engagement_at}."""
    num = den = new = 0.0
    eng = 0
    last_eng = None
    for s in signals:
        w = float(s.get("w") or 0) * float(s.get("share") if s.get("share") is not None else 1.0)
        v = float(s.get("value") or 0)
        if s.get("personalize") and k_of is not None:
            v *= float(k_of(s))
        d = decay(now - float(s.get("at") or 0))
        num += w * v * d
        den += w * d
        kind = s.get("kind")
        at = float(s.get("at") or 0)
        if kind not in _NOT_EVIDENCE and at > since:
            new += w * d
            if kind not in _NOT_ENGAGEMENT:
                eng += 1
        if kind not in _NOT_ENGAGEMENT:
            last_eng = at if last_eng is None else max(last_eng, at)
    est = num / (den + PRIOR_MASS)
    conf = den / (den + CONF_MASS)
    return {"estimate": est, "confidence": conf, "n_eff": den, "u": est * conf, "new": new, "engagement_new": eng,
            "last_engagement_at": last_eng}


def decide(row: dict, sc: dict, now: float, has_opportunity: bool = False) -> dict:
    """Một kỳ đánh giá bậc (5.3). `row`: {tier, max_tier, last_change_at, last_change_dir, holds, resumed_at,
    last_opp_at}. `has_opportunity`: có cơ hội CHƯA tiêu thụ (hay lý do đang chờ) lúc này. Trả {tier, dir, reason}.

    Thứ tự: dwell -> lên (u ≥ +0.25 và new ≥ 1.0, không quá max_tier) -> xuống `unhelpful` (u ≤ -0.25 và new ≥ 1.0) ->
    xuống `low_demand` (không tín hiệu tương tác mới từ lần đổi trước, không cơ hội trong hai lần khoảng) -> giữ.
    Hysteresis: đổi chiều chỉ sau ít nhất một kỳ giữ. Từ B7 chỉ `low_demand` mới đưa vào ngủ đông."""
    tier = int(row.get("tier", INIT_TIER))
    if tier >= HIBERNATE:
        return {"tier": tier, "dir": 0, "reason": "hibernating"}
    iv = float(TIERS[tier])
    since_change = float(row.get("last_change_at") or row.get("resumed_at") or 0.0)
    if now - since_change < max(2 * iv, DAY):
        return {"tier": tier, "dir": 0, "reason": "dwell"}
    max_tier = int(row.get("max_tier") if row.get("max_tier") is not None else DEFAULT_MAX_TIER)
    u, new = float(sc.get("u") or 0), float(sc.get("new") or 0)
    want, reason = 0, "hold"
    rise = u >= UP_U and new >= NEW_MIN
    if rise and tier > max_tier:
        want, reason = +1, "helpful"
    elif rise:
        # Đã ở trần `max_tier`: luật lên không áp; vẫn xét các luật sau (im lâu thì vẫn chậm lại).
        reason = "max_tier"
    if want:
        pass
    elif u <= DOWN_U and new >= NEW_MIN and tier < 7:
        want, reason = -1, "unhelpful"
    elif not has_opportunity:
        base = max(since_change, float(row.get("resumed_at") or 0))
        opp = float(row.get("last_opp_at") or 0)
        # (A) Không tín hiệu tương tác mới từ lần đổi bậc trước và không cơ hội trong hai lần khoảng hiện tại.
        quiet_a = int(sc.get("engagement_new") or 0) == 0 and now - max(base, opp) >= 2 * iv
        # (B) Im lâu: tín hiệu tương tác gần nhất (kể cả trước lần đổi) và cơ hội gần nhất đều cũ hơn
        #     max(4 x khoảng, 3 ngày). Không có (B) thì một reaction ngay sau lần đổi giữ bậc nhanh mãi mãi.
        last_eng = float(sc.get("last_engagement_at") or 0)
        quiet_b = now - max(base, opp, last_eng) >= max(LONG_QUIET_X * iv, LONG_QUIET_S)
        if quiet_a or quiet_b:
            want, reason = -1, "low_demand"
    if want == 0:
        return {"tier": tier, "dir": 0, "reason": reason}
    last_dir = int(row.get("last_change_dir") or 0)
    if last_dir and want != last_dir and int(row.get("holds") or 0) < 1:
        return {"tier": tier, "dir": 0, "reason": "hysteresis"}
    return {"tier": tier - 1 if want > 0 else tier + 1, "dir": want, "reason": reason}


def effective_due(next_due_at: Optional[float], pending_reason_at: Optional[float], busy: bool,
                  now: float) -> Optional[float]:
    """Hợp nhất lịch chủ động và lý do lớp 3 đang chờ (5.1). Agent đang có lượt A2 hay lượt nhóm (khoá bận) thì dời 60
    giây. None: không có gì tới hạn (ngủ đông, không lý do)."""
    cands = [x for x in (next_due_at, pending_reason_at) if x is not None]
    if not cands:
        return None
    due = min(cands)
    if busy and due <= now:
        return now + BUSY_DEFER_S
    return due


def attribute(synth: str, inputs: Iterable[str]) -> dict:
    """Phân bổ một phản hồi của chủ trên bản tổng hợp (6.5). `inputs`: agent của từng mục trong TẬP ĐẦU VÀO host đưa cho
    bước tổng hợp (mỗi bước một mục, có thể lặp agent). 0.8 chia đều theo tập đó, trần 0.6 mỗi agent, phần vượt trần chia
    tiếp cho người còn dưới trần, chỉ khi ai cũng chạm trần mới về tác giả tổng hợp; 0.2 về tác giả tổng hợp; tập rỗng thì
    tác giả nhận 1.0; một agent vừa làm bước vừa tổng hợp thì gộp phần. Tổng luôn bằng 1."""
    items = [str(a) for a in (inputs or []) if a]
    synth = str(synth or "")
    if not items:
        return {synth: 1.0}
    per = CONTRIB_INPUTS / len(items)
    raw: dict = {}
    for a in items:
        raw[a] = raw.get(a, 0.0) + per
    alloc = {a: min(v, CONTRIB_CAP) for a, v in raw.items()}
    over = sum(max(0.0, v - CONTRIB_CAP) for v in raw.values())
    to_synth = 0.0
    # Rót phần vượt trần cho người còn dưới trần (mỗi vòng ít nhất một người chạm trần hay hết phần dư).
    while over > 1e-12:
        under = [a for a in alloc if alloc[a] < CONTRIB_CAP - 1e-12]
        if not under:
            to_synth += over
            break
        each, over = over / len(under), 0.0
        for a in under:
            give = min(each, CONTRIB_CAP - alloc[a])
            alloc[a] += give
            over += each - give
    alloc[synth] = alloc.get(synth, 0.0) + CONTRIB_SYNTH + to_synth
    total = sum(alloc.values())
    if abs(total - 1.0) > 1e-9:
        alloc[synth] += 1.0 - total
    return alloc


# ═════════════════════════════ kho ═════════════════════════════

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pulse_meta(name TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_pulse_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, agent_key TEXT NOT NULL, context_ref TEXT NOT NULL, kind TEXT NOT NULL,
  before_json TEXT NOT NULL DEFAULT '{}', after_json TEXT NOT NULL DEFAULT '{}', source TEXT NOT NULL DEFAULT '',
  reason TEXT NOT NULL DEFAULT '', u REAL, new REAL, policy_version TEXT NOT NULL DEFAULT 'pulse.v1',
  payload_json TEXT NOT NULL DEFAULT '{}', reverted_by INTEGER, created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS agent_pulse_events_agent ON agent_pulse_events(agent_key, context_ref, id);
CREATE TABLE IF NOT EXISTS pulse_signals(
  id INTEGER PRIMARY KEY AUTOINCREMENT, source_ref TEXT NOT NULL, agent_key TEXT NOT NULL, context_ref TEXT NOT NULL,
  ctx_kind TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL, value REAL NOT NULL, w REAL NOT NULL,
  share REAL NOT NULL DEFAULT 1.0, reactor TEXT NOT NULL DEFAULT '', emoji TEXT NOT NULL DEFAULT '',
  reasons_json TEXT NOT NULL DEFAULT '[]', personalize INTEGER NOT NULL DEFAULT 0, subject_ref TEXT NOT NULL DEFAULT '',
  at REAL NOT NULL, status TEXT NOT NULL DEFAULT 'live', superseded_by TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL, updated_at REAL NOT NULL, UNIQUE(source_ref, agent_key),
  CHECK (status IN ('live','superseded','void')));
CREATE INDEX IF NOT EXISTS pulse_signals_ctx ON pulse_signals(agent_key, context_ref, status, at);
CREATE INDEX IF NOT EXISTS pulse_signals_reactor ON pulse_signals(reactor, ctx_kind, status);
CREATE INDEX IF NOT EXISTS pulse_signals_subject ON pulse_signals(subject_ref);
CREATE TABLE IF NOT EXISTS pulse_contrib(
  id INTEGER PRIMARY KEY AUTOINCREMENT, source_ref TEXT NOT NULL, result_ref TEXT NOT NULL DEFAULT '',
  agent_key TEXT NOT NULL, share REAL NOT NULL, role TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'live',
  inputs_json TEXT NOT NULL DEFAULT '[]', created_at REAL NOT NULL, superseded_at REAL,
  CHECK (status IN ('live','superseded','void')));
CREATE INDEX IF NOT EXISTS pulse_contrib_source ON pulse_contrib(source_ref, status);
CREATE TABLE IF NOT EXISTS message_seen(
  context_ref TEXT NOT NULL, message_id INTEGER NOT NULL, agent_key TEXT NOT NULL DEFAULT '',
  session_id TEXT NOT NULL DEFAULT '', seen_at REAL NOT NULL, PRIMARY KEY(context_ref, message_id));
CREATE TABLE IF NOT EXISTS pulse_opportunities(
  agent_key TEXT NOT NULL, context_ref TEXT NOT NULL, source_ref TEXT NOT NULL, version TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT '', first_seen_at REAL NOT NULL, consumed_at REAL, consumed_by TEXT NOT NULL DEFAULT '',
  PRIMARY KEY(agent_key, context_ref, source_ref, version));
CREATE TABLE IF NOT EXISTS pulse_proactive(
  id INTEGER PRIMARY KEY AUTOINCREMENT, agent_key TEXT NOT NULL, context_ref TEXT NOT NULL,
  session_id TEXT NOT NULL DEFAULT '', message_id INTEGER NOT NULL, said_at REAL NOT NULL, seen_at REAL,
  outcome TEXT NOT NULL DEFAULT '', signal_ref TEXT NOT NULL DEFAULT '', UNIQUE(context_ref, message_id));
CREATE TABLE IF NOT EXISTS pulse_policy_changes(
  id INTEGER PRIMARY KEY AUTOINCREMENT, agent_key TEXT NOT NULL, context_ref TEXT NOT NULL, kind TEXT NOT NULL,
  before_json TEXT NOT NULL DEFAULT '{}', after_json TEXT NOT NULL DEFAULT '{}', source TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'observing', policy_version TEXT NOT NULL DEFAULT 'pulse.v1',
  base_estimate REAL NOT NULL DEFAULT 0, base_conf REAL NOT NULL DEFAULT 0, base_error REAL,
  labels INTEGER NOT NULL DEFAULT 0, errors INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL,
  window_until REAL NOT NULL, decided_at REAL, decided_reason TEXT NOT NULL DEFAULT '',
  CHECK (status IN ('observing','kept','reverted')));
CREATE INDEX IF NOT EXISTS pulse_policy_changes_open ON pulse_policy_changes(status, agent_key);
CREATE TABLE IF NOT EXISTS pulse_proposals(
  id INTEGER PRIMARY KEY AUTOINCREMENT, agent_key TEXT NOT NULL, context_ref TEXT NOT NULL, source_ref TEXT NOT NULL,
  version TEXT NOT NULL DEFAULT '', title TEXT NOT NULL, brief TEXT NOT NULL DEFAULT '', session_id TEXT NOT NULL DEFAULT '',
  message_id INTEGER, status TEXT NOT NULL DEFAULT 'pending', task_id TEXT NOT NULL DEFAULT '',
  decided_by TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, decided_at REAL,
  CHECK (status IN ('pending','accepted','rejected')));
CREATE INDEX IF NOT EXISTS pulse_proposals_src ON pulse_proposals(agent_key, context_ref, source_ref, version);
CREATE INDEX IF NOT EXISTS pulse_proposals_msg ON pulse_proposals(context_ref, message_id);
CREATE TABLE IF NOT EXISTS pulse_followups(
  id INTEGER PRIMARY KEY AUTOINCREMENT, agent_key TEXT NOT NULL, context_ref TEXT NOT NULL, due_at REAL NOT NULL,
  note TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'pending', created_at REAL NOT NULL,
  created_by TEXT NOT NULL DEFAULT '', fired_at REAL, closed_at REAL, closed_by TEXT NOT NULL DEFAULT '',
  CHECK (status IN ('pending','done','cancelled')));
CREATE INDEX IF NOT EXISTS pulse_followups_due ON pulse_followups(status, due_at);
CREATE INDEX IF NOT EXISTS pulse_followups_ctx ON pulse_followups(agent_key, context_ref, status, due_at);
"""
# Cột thêm cho `agent_pulse` (bảng T2, mục 5.4 đã đủ). Chỉ thêm, đều có mặc định: bản 0.154.x vẫn đọc ghi được.
_PULSE_COLS = (
    ("holds", "INTEGER NOT NULL DEFAULT 0"),
    ("last_opp_at", "REAL"),
    ("last_u", "REAL NOT NULL DEFAULT 0"),
    ("last_new", "REAL NOT NULL DEFAULT 0"),
    ("waiting_since", "REAL"),
    ("reminded_at", "REAL"),
    ("last_scan_at", "REAL"),
    ("wake_count", "INTEGER NOT NULL DEFAULT 0"),
    ("last_wake_why", "TEXT NOT NULL DEFAULT ''"),
    ("last_wake_at", "REAL"),
    ("claim_token", "TEXT NOT NULL DEFAULT ''"),
    ("claim_until", "REAL"),
    ("quota_wait", "INTEGER NOT NULL DEFAULT 0"),
)
UPGRADE_MARK = "pulse_v1_upgraded_at"
T3_TABLES = ("pulse_meta", "agent_pulse_events", "pulse_signals", "pulse_contrib", "message_seen",
             "pulse_opportunities", "pulse_proactive", "pulse_policy_changes", "pulse_proposals", "pulse_followups")
_READY: set = set()


def ensure(store, force: bool = False) -> None:
    """Tạo bảng của nhịp (một lần mỗi kho mỗi tiến trình) và nâng cấp lần đầu (mục 12): mọi dòng `agent_pulse` về B3 với
    `resumed_at = lúc nâng cấp` (agent đang tắt Cộng hưởng: `off`); reaction cũ không được backfill thành tín hiệu."""
    key = str(getattr(store, "path", id(store)))
    if key in _READY and not force:
        return
    with closing(store._conn()) as c:
        names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        cols = {r[1] for r in c.execute("PRAGMA table_info(agent_pulse)").fetchall()}
        done = c.execute("SELECT value FROM pulse_meta WHERE name=?", (UPGRADE_MARK,)).fetchone()             if "pulse_meta" in names else None
    if set(T3_TABLES) <= names and all(col in cols for col, _ in _PULSE_COLS) and done is not None:
        # Kho đã đủ: chỉ đọc, không ghi (mở kho không tốn lần ghi đĩa nào, kể cả khi mở trong event loop).
        _READY.add(key)
        return
    # Tạo bảng, thêm cột và nâng cấp trong MỘT giao dịch (một lần ghi đĩa).
    with store._Tx(store) as c:
        for stmt in [x.strip() for x in _SCHEMA.split(";") if x.strip()]:
            c.execute(stmt)
        cols = {r[1] for r in c.execute("PRAGMA table_info(agent_pulse)").fetchall()}
        for col, decl in _PULSE_COLS:
            if col not in cols:
                c.execute(f"ALTER TABLE agent_pulse ADD COLUMN {col} {decl}")
        if c.execute("SELECT 1 FROM pulse_meta WHERE name=?", (UPGRADE_MARK,)).fetchone() is None:
            now = time.time()
            for r in c.execute("SELECT agent_key, enabled, status FROM resonance_agents").fetchall():
                on = bool(r["enabled"]) and r["status"] == "active"
                c.execute("INSERT OR IGNORE INTO agent_pulse(agent_key, context_ref, state, updated_at) VALUES(?,?,?,?)",
                          (r["agent_key"], "*", "awake" if on else "off", now))
                if on:
                    c.execute("UPDATE agent_pulse SET tier=?, state=CASE WHEN state IN ('paused','waiting_owner') "
                              "THEN state ELSE 'awake' END, resumed_at=?, last_change_at=?, last_change_dir=0, holds=0, "
                              "next_due_at=CASE WHEN context_ref='*' THEN NULL ELSE ? END, updated_at=? "
                              "WHERE agent_key=?", (INIT_TIER, now, now, now + TIERS[INIT_TIER], now, r["agent_key"]))
                else:
                    c.execute("UPDATE agent_pulse SET tier=?, state='off', next_due_at=NULL, updated_at=? "
                              "WHERE agent_key=?", (INIT_TIER, now, r["agent_key"]))
            c.execute("INSERT INTO pulse_meta(name, value) VALUES(?, ?)", (UPGRADE_MARK, str(now)))
    _READY.add(key)


def _agent_on(c, agent_key: str) -> bool:
    r = c.execute("SELECT enabled, status FROM resonance_agents WHERE agent_key=?", (agent_key,)).fetchone()
    return bool(r and r["enabled"] and r["status"] == "active")


def _event(c, agent_key: str, context_ref: str, kind: str, *, before: Any = None, after: Any = None, source: str = "",
           reason: str = "", u: Optional[float] = None, new: Optional[float] = None, payload: Any = None,
           at: float) -> int:
    cur = c.execute("INSERT INTO agent_pulse_events(agent_key,context_ref,kind,before_json,after_json,source,reason,u,new,"
                    "policy_version,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (agent_key, context_ref, kind, _j(before or {}), _j(after or {}), str(source or ""),
                     str(reason or ""), u, new, POLICY_VERSION, _j(payload or {}), at))
    return int(cur.lastrowid)


def _row(c, agent_key: str, context_ref: str) -> Optional[dict]:
    r = c.execute("SELECT * FROM agent_pulse WHERE agent_key=? AND context_ref=?", (agent_key, context_ref)).fetchone()
    return dict(r) if r else None


def _live_signals(c, agent_key: str, context_ref: Optional[str] = None) -> list:
    if context_ref is None:
        rows = c.execute("SELECT * FROM pulse_signals WHERE agent_key=? AND status='live' AND kind<>'context_init'",
                         (agent_key,)).fetchall()
    else:
        rows = c.execute("SELECT * FROM pulse_signals WHERE agent_key=? AND context_ref=? AND status='live'",
                         (agent_key, context_ref)).fetchall()
    return [dict(r) for r in rows]


def _k_table(c, reactors: Iterable[tuple], now: float) -> dict:
    """{(reactor, ctx_kind): (n, {emoji: count})} từ lịch sử HIỆN TẠI (6.3: k tính lại mỗi kỳ). Đếm mỗi sự kiện nguồn
    một lần (một phản hồi chia cho nhiều agent vẫn là một reaction), chỉ reaction không lý do còn sống, tới `now`."""
    out = {}
    for reactor, kind in set(reactors):
        rows = c.execute("SELECT emoji, COUNT(DISTINCT source_ref) AS n FROM pulse_signals WHERE reactor=? AND ctx_kind=? "
                         "AND kind='reaction' AND status='live' AND at<=? GROUP BY emoji", (reactor, kind, now)).fetchall()
        counts = {r["emoji"]: int(r["n"]) for r in rows}
        out[(reactor, kind)] = (sum(counts.values()), counts)
    return out


def _score_rows(c, rows: list, now: float, since: float) -> dict:
    kt = _k_table(c, [(s["reactor"], s["ctx_kind"]) for s in rows if s.get("personalize")], now)

    def k_of(s):
        n, counts = kt.get((s["reactor"], s["ctx_kind"]), (0, {}))
        return compute_k(n, counts.get(s["emoji"], 0))
    return score(rows, now, k_of, since)


def _aggregate_in(c, agent_key: str, now: float) -> dict:
    return _score_rows(c, _live_signals(c, agent_key, None), now, 0.0)


def _ensure_row_in(c, agent_key: str, context_ref: str, now: float) -> dict:
    """Dòng nhịp của (agent, ngữ cảnh); chưa có thì tạo ở B3, kế thừa `resumed_at`, `max_tier`, trạng thái tắt của dòng
    tổng hợp `*`, và một tín hiệu khởi tạo = 0,5 x bằng chứng tổng hợp (6.3; không phải bằng chứng mới)."""
    cur = _row(c, agent_key, context_ref)
    if cur is not None:
        return cur
    on = _agent_on(c, agent_key)
    star = _row(c, agent_key, "*")
    if star is None:
        c.execute("INSERT INTO agent_pulse(agent_key, context_ref, state, resumed_at, updated_at) VALUES(?,?,?,?,?)",
                  (agent_key, "*", "awake" if on else "off", now if on else None, now))
        star = _row(c, agent_key, "*")
    if context_ref == "*":
        return star
    resumed = star.get("resumed_at") if star.get("resumed_at") is not None else (now if on else None)
    state = "off" if (not on or star.get("state") == "off") else ("paused" if star.get("state") == "paused" else "awake")
    mt = int(star.get("max_tier") if star.get("max_tier") is not None else DEFAULT_MAX_TIER)
    t0 = max(INIT_TIER, mt)   # không nhanh hơn trần chủ đặt (review T3 P P3)
    c.execute("INSERT INTO agent_pulse(agent_key,context_ref,state,tier,next_due_at,last_change_at,resumed_at,max_tier,"
              "updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
              (agent_key, context_ref, state, t0, now + TIERS[t0] if state == "awake" else None, now,
               resumed, mt, now))
    agg = _aggregate_in(c, agent_key, now)
    if agg["n_eff"] > 0:
        w = min(1.0, CONTEXT_INIT_FACTOR * agg["n_eff"])
        v = max(-1.0, min(1.0, agg["estimate"]))
        c.execute("INSERT OR IGNORE INTO pulse_signals(source_ref,agent_key,context_ref,ctx_kind,kind,value,w,share,at,"
                  "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (f"init:{agent_key}:{context_ref}", agent_key, context_ref, ctx_kind(context_ref), "context_init",
                   v, w, 1.0, now, now, now))
    _event(c, agent_key, context_ref, "context_created", after={"tier": t0, "state": state},
           source="host", payload={"init_estimate": agg["estimate"], "init_n_eff": agg["n_eff"]}, at=now)
    return _row(c, agent_key, context_ref)


def ensure_row(store, agent_key: str, context_ref: str, at: Optional[float] = None) -> dict:
    ensure(store)
    with store._Tx(store) as c:
        return _ensure_row_in(c, str(agent_key), str(context_ref), _now(at))


# ───────────── tín hiệu (6.1, 6.3) ─────────────

def record_signal(store, *, source_ref: str, agent_key: str, context_ref: str, kind: str, value: float, w: float,
                  share: float = 1.0, reactor: str = "", emoji: str = "", reasons: Iterable[str] = (),
                  at: Optional[float] = None, subject_ref: str = "", personalize: Optional[bool] = None) -> bool:
    """Ghi MỘT tín hiệu (`pulse_signals`), idempotent theo `(source_ref, agent_key)`: gọi lại trả False, không ghi thêm.
    Reaction của agent (reactor `agent:...`) không bao giờ thành tín hiệu (chống tự thưởng). Mỗi sự kiện nguồn đóng góp
    `|w·v| ≤ 1`. `personalize` mặc định: reaction không lý do."""
    ensure(store)
    src, key, ctx = str(source_ref or "").strip(), str(agent_key or "").strip(), str(context_ref or "").strip()
    if not src or not key or not ctx or ctx == "*":
        raise ValueError("thiếu source_ref, agent_key hay context_ref")
    if kind not in SIGNAL_KINDS:
        raise ValueError(f"loại tín hiệu không hợp lệ: {kind}")
    if str(reactor or "").startswith("agent:"):
        return False
    v, ww, sh = float(value), float(w), float(share)
    if abs(ww * v) > 1.0 + 1e-9:
        raise ValueError("mỗi sự kiện nguồn đóng góp |w·v| ≤ 1")
    if not (0.0 < sh <= 1.0 + 1e-9):
        raise ValueError("share phải trong (0, 1]")
    t = _now(at)
    pers = (kind == "reaction") if personalize is None else bool(personalize)
    with store._Tx(store) as c:
        if c.execute("SELECT 1 FROM pulse_signals WHERE source_ref=? AND agent_key=?", (src, key)).fetchone():
            return False
        _ensure_row_in(c, key, ctx, t)
        c.execute("INSERT INTO pulse_signals(source_ref,agent_key,context_ref,ctx_kind,kind,value,w,share,reactor,emoji,"
                  "reasons_json,personalize,subject_ref,at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (src, key, ctx, ctx_kind(ctx), kind, v, ww, min(1.0, sh), str(reactor or ""), str(emoji or ""),
                   _j(list(reasons or [])), 1 if pers else 0, str(subject_ref or ""), t, time.time(), time.time()))
    return True


def record_reaction(store, *, source_ref: str, agent_key: str, context_ref: str, value: Optional[str],
                    reasons: Iterable[str] = (), reactor: str = "owner", share: float = 1.0,
                    at: Optional[float] = None, subject_ref: str = "") -> bool:
    """Tín hiệu của một reaction của chủ (bảng 6.1). Chỉ trục nói/im hay chỉ góp ý: không tín hiệu (False)."""
    sig = reaction_signal(value, reasons)
    if sig is None:
        return False
    kind, v0, w, pers = sig
    return record_signal(store, source_ref=source_ref, agent_key=agent_key, context_ref=context_ref, kind=kind,
                         value=v0, w=w, share=share, reactor=reactor, emoji=str(value or ""), reasons=list(reasons or []),
                         at=at, subject_ref=subject_ref, personalize=pers)


def record_host_event(store, *, event: str, source_ref: str, agents: dict, context_ref: str,
                      at: Optional[float] = None, subject_ref: str = "") -> list:
    """Tín hiệu từ sự kiện host (chấp nhận đề xuất, chốt quyết định, sửa yêu cầu sau kết quả, huỷ, kiểm khách quan).
    `agents`: {agent_key: share} (tổng 1). Trả các agent đã ghi."""
    if event not in HOST_EVENT:
        raise ValueError(f"sự kiện host không hợp lệ: {event}")
    v0, w = HOST_EVENT[event]
    done = []
    for key, share in (agents or {}).items():
        if key and share > 0 and record_signal(store, source_ref=source_ref, agent_key=key, context_ref=context_ref,
                                               kind="host_event", value=v0, w=w, share=share, emoji=event, at=at,
                                               subject_ref=subject_ref, personalize=False):
            done.append(key)
    return done


def record_objective(store, *, goal_id: str, revision: int, passed: bool, agents: dict, context_ref: str,
                     at: Optional[float] = None) -> str:
    """Kiểm khách quan (6.1, ±0.5 w 0.8): MỘT tín hiệu cho kết luận CUỐI của mỗi (mục tiêu, revision), nguồn
    `obj:<goal_id>:<revision>`. Không bao giờ gọi cho đánh giá trung gian trong vòng làm việc. Kết luận cuối đổi chiều (vd.
    revision bị gác vì hết hạn mức rồi chủ nới hạn mức và nó đạt) thì SỬA giá trị của chính tín hiệu đó, không thêm dòng.
    Trả "recorded" | "unchanged" | "changed" | "none"."""
    ensure(store)
    src = f"obj:{goal_id}:{int(revision)}"
    event = "objective_pass" if passed else "objective_fail"
    v0, _w = HOST_EVENT[event]
    t = _now(at)
    with store._Tx(store) as c:
        live = [dict(r) for r in c.execute("SELECT * FROM pulse_signals WHERE source_ref=? AND status='live'",
                                           (src,)).fetchall()]
        if live:
            if all(abs(float(r["value"]) - v0) < 1e-12 for r in live):
                return "unchanged"
            c.execute("UPDATE pulse_signals SET value=?, emoji=?, at=?, updated_at=? WHERE source_ref=? AND status='live'",
                      (v0, event, t, time.time(), src))
            for r in live:
                _event(c, r["agent_key"], r["context_ref"], "objective_changed", before={"value": r["value"]},
                       after={"value": v0}, source="host", reason=event, payload={"source_ref": src}, at=t)
            return "changed"
    done = record_host_event(store, event=event, source_ref=src, agents=agents, context_ref=context_ref, at=t,
                             subject_ref=f"goal:{goal_id}:{int(revision)}")
    return "recorded" if done else "none"


def supersede_signal(store, source_ref: str, by_ref: str) -> int:
    """Thay reaction: dòng cũ `superseded_by` dòng mới (6.3), mọi agent của nguồn đó. Không cộng dồn."""
    ensure(store)
    with store._Tx(store) as c:
        c.execute("UPDATE pulse_contrib SET status='superseded', superseded_at=? WHERE source_ref=? AND status='live'",
                  (time.time(), str(source_ref)))
        return c.execute("UPDATE pulse_signals SET status='superseded', superseded_by=?, updated_at=? "
                         "WHERE source_ref=? AND status='live'", (str(by_ref or ""), time.time(),
                                                                  str(source_ref))).rowcount


def void_signal(store, source_ref: str) -> int:
    """Xoá nguồn (xoá tin, xoá agent): `void`, mọi agent của nguồn đó."""
    ensure(store)
    with store._Tx(store) as c:
        n = c.execute("UPDATE pulse_signals SET status='void', updated_at=? WHERE source_ref=? AND status<>'void'",
                      (time.time(), str(source_ref))).rowcount
        c.execute("UPDATE pulse_contrib SET status='void' WHERE source_ref=? AND status='live'", (str(source_ref),))
        return n


def void_subject(store, prefix: str) -> int:
    """Xoá tin hay phiên: mọi tín hiệu có `subject_ref` bắt đầu bằng `prefix` thành `void`."""
    ensure(store)
    p = str(prefix or "")
    if not p:
        return 0
    with store._Tx(store) as c:
        return c.execute("UPDATE pulse_signals SET status='void', updated_at=? WHERE subject_ref LIKE ? AND status<>'void'",
                         (time.time(), p.replace("%", "") + "%")).rowcount


def void_agent(store, agent_key: str) -> int:
    ensure(store)
    with store._Tx(store) as c:
        return c.execute("UPDATE pulse_signals SET status='void', updated_at=? WHERE agent_key=? AND status<>'void'",
                         (time.time(), str(agent_key))).rowcount


def signals(store, agent_key: str, context_ref: Optional[str] = None, status: Optional[str] = None) -> list:
    ensure(store)
    q, args = "SELECT * FROM pulse_signals WHERE agent_key=?", [str(agent_key)]
    if context_ref is not None:
        q += " AND context_ref=?"
        args.append(str(context_ref))
    if status is not None:
        q += " AND status=?"
        args.append(str(status))
    with closing(store._conn()) as c:
        return [dict(r) for r in c.execute(q + " ORDER BY id", args).fetchall()]


# ───────────── ghi nhận đóng góp (6.5) ─────────────

def record_contrib(store, *, source_ref: str, result_ref: str, synth: str, inputs: Iterable[str], context_ref: str,
                   value: Optional[str] = None, reasons: Iterable[str] = (), reactor: str = "owner",
                   at: Optional[float] = None, subject_ref: str = "", signal: Optional[tuple] = None) -> dict:
    """Một phản hồi của chủ trên bản tổng hợp `result_ref`, phân bổ theo tập đầu vào host đã ghi (`inputs`, agent của
    từng mục). Ghi `pulse_contrib` và một dòng `pulse_signals` mỗi agent với `share` (tác giả tổng hợp KHÔNG có thêm tín
    hiệu trực tiếp riêng cho cùng nguồn). Gọi lại cùng `result_ref`: không đổi gì. Bản kết quả khác (thay bản): phân bổ
    cũ `superseded`, tính lại theo bản mới, không cộng dồn. Trả {agent_key: share}."""
    ensure(store)
    if str(reactor or "").startswith("agent:"):
        return {}   # agent không tự thưởng nhau, kể cả qua bản tổng hợp
    sig = signal or reaction_signal(value, reasons)
    inputs = [str(a) for a in (inputs or []) if a]
    alloc = attribute(synth, inputs)
    if sig is None:
        return {}
    kind, v0, w, pers = sig
    t = _now(at)
    src = str(source_ref)
    with store._Tx(store) as c:
        live = [dict(r) for r in c.execute("SELECT * FROM pulse_contrib WHERE source_ref=? AND status='live'",
                                           (src,)).fetchall()]
        if live and all(r["result_ref"] == str(result_ref) for r in live):
            return {r["agent_key"]: r["share"] for r in live}
        if live:
            c.execute("UPDATE pulse_contrib SET status='superseded', superseded_at=? WHERE source_ref=? AND status='live'",
                      (t, src))
        for key, share in alloc.items():
            role = ("merged" if key == synth and key in inputs else "synth" if key == synth and inputs else
                    "author" if key == synth else "input")
            c.execute("INSERT INTO pulse_contrib(source_ref,result_ref,agent_key,share,role,inputs_json,created_at) "
                      "VALUES(?,?,?,?,?,?,?)", (src, str(result_ref), key, share, role, _j(inputs), t))
        old = {r["agent_key"]: dict(r) for r in c.execute("SELECT * FROM pulse_signals WHERE source_ref=?",
                                                          (src,)).fetchall()}
        if old and all(r["status"] == "void" for r in old.values()):
            # Nguồn đã xoá (xoá tin, xoá agent): không phân bổ lại, không hồi sinh (review T3 P P3).
            return {}
        for key, r in old.items():
            if key not in alloc and r["status"] == "live":
                c.execute("UPDATE pulse_signals SET status='superseded', superseded_by=?, updated_at=? WHERE id=?",
                          (f"{src}#{result_ref}", time.time(), r["id"]))
        for key, share in alloc.items():
            _ensure_row_in(c, key, context_ref, t)
            if key in old:
                if old[key]["status"] == "void":
                    continue   # dòng của agent đã xoá giữ `void`
                c.execute("UPDATE pulse_signals SET share=?, status='live', superseded_by='', updated_at=? WHERE id=?",
                          (min(1.0, share), time.time(), old[key]["id"]))
            else:
                c.execute("INSERT INTO pulse_signals(source_ref,agent_key,context_ref,ctx_kind,kind,value,w,share,reactor,"
                          "emoji,reasons_json,personalize,subject_ref,at,created_at,updated_at) "
                          "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (src, key, context_ref, ctx_kind(context_ref), kind, v0, w, min(1.0, share), reactor,
                           str(value or ""), _j(list(reasons or [])), 1 if pers else 0, subject_ref, t, time.time(),
                           time.time()))
    return alloc


def contrib(store, source_ref: str, live_only: bool = True) -> list:
    ensure(store)
    q = "SELECT * FROM pulse_contrib WHERE source_ref=?" + (" AND status='live'" if live_only else "")
    with closing(store._conn()) as c:
        return [dict(r) for r in c.execute(q + " ORDER BY id", (str(source_ref),)).fetchall()]


# ───────────── đánh giá, thức, trạng thái (5.2-5.4) ─────────────

def evaluate(store, agent_key: str, context_ref: str, at: Optional[float] = None, *, has_opportunity: bool = False,
             count_wake: bool = False, source: str = "schedule") -> dict:
    """Một kỳ đánh giá của (agent, ngữ cảnh): tính lại ước lượng (k tính lại từ lịch sử hiện tại), áp `decide`, ghi
    trước/sau vào `agent_pulse_events` khi đổi bậc. Chỉ cho trạng thái có lịch (active/awake/slowed); trạng thái khác chỉ
    cập nhật ước lượng. Trả {tier_before, tier, state, changed, reason, u, new, estimate, confidence, n_eff}."""
    ensure(store)
    t = _now(at)
    key, ctx = str(agent_key), str(context_ref)
    with store._Tx(store) as c:
        row = _ensure_row_in(c, key, ctx, t)
        since = max(float(row.get("last_change_at") or 0), float(row.get("resumed_at") or 0))
        sc = _score_rows(c, _live_signals(c, key, ctx), t, since)
        out = {"tier_before": int(row["tier"]), "tier": int(row["tier"]), "state": row["state"], "changed": False,
               "reason": "not_scheduled", "u": sc["u"], "new": sc["new"], "estimate": sc["estimate"],
               "confidence": sc["confidence"], "n_eff": sc["n_eff"]}
        sets = {"estimate": sc["estimate"], "confidence": sc["confidence"], "n_eff": sc["n_eff"], "last_u": sc["u"],
                "last_new": sc["new"], "last_eval_at": t, "updated_at": t}
        if has_opportunity:
            sets["last_opp_at"] = t
            row["last_opp_at"] = t
        if row["state"] in SCHEDULED:
            d = decide(row, sc, t, has_opportunity)
            out["reason"] = d["reason"]
            if d["dir"]:
                nt = int(d["tier"])
                sets.update({"tier": nt, "state": state_for_tier(nt), "last_change_at": t, "last_change_dir": d["dir"],
                             "holds": 0, "next_due_at": (t + TIERS[nt]) if nt < HIBERNATE else None})
                _event(c, key, ctx, "tier_change", before={"tier": int(row["tier"]), "state": row["state"]},
                       after={"tier": nt, "state": state_for_tier(nt)}, source=source, reason=d["reason"],
                       u=sc["u"], new=sc["new"], at=t)
                out.update({"tier": nt, "state": state_for_tier(nt), "changed": True})
            else:
                sets["holds"] = int(row.get("holds") or 0) + 1
            if count_wake and out["state"] in ("active", "awake"):
                sets["scan_counter"] = int(row.get("scan_counter") or 0) + 1
        cols = ", ".join(f"{k}=?" for k in sets)
        c.execute(f"UPDATE agent_pulse SET {cols} WHERE agent_key=? AND context_ref=?", (*sets.values(), key, ctx))
    return out


OWNER_WAKES = ("owner_message", "direct_call", "owner_reply", "new_job", "manual")


def wake(store, agent_key: str, context_ref: str, why: str, at: Optional[float] = None) -> bool:
    """Thức lại (5.2): bậc mới = `min(bậc hiện tại, B3)` (đang nhanh hơn B3 thì giữ), giữ nguyên ước lượng, ký ức và lịch
    sử. Kích hoạt bởi lời gọi trực tiếp, chủ nhắn, giao việc mới, reaction mới hợp lệ, sự kiện liên quan có cấu trúc.
    `paused`/`off`: không đổi gì (False). `waiting_owner`: chỉ chủ (trả lời, gọi, giao việc) mới gỡ."""
    ensure(store)
    t = _now(at)
    key, ctx = str(agent_key), str(context_ref)
    if not key or not ctx or ctx == "*":
        return False
    with store._Tx(store) as c:
        row = _ensure_row_in(c, key, ctx, t)
        st = row["state"]
        if st in ("paused", "off"):
            return False
        if st == "waiting_owner" and why not in OWNER_WAKES:
            return False
        tier = int(row["tier"])
        # min(bậc, B3) nhưng không nhanh hơn `max_tier` chủ đặt (review T3 P P3: trần B4-B7 bị thức lại về B3).
        mt = int(row.get("max_tier") if row.get("max_tier") is not None else DEFAULT_MAX_TIER)
        nt = max(min(tier, INIT_TIER), mt)
        sets = {"state": state_for_tier(nt), "wake_count": int(row.get("wake_count") or 0) + 1, "last_wake_why": str(why),
                "last_wake_at": t, "updated_at": t, "waiting_since": None, "reminded_at": None}
        nd = t + TIERS[nt] if nt < HIBERNATE else None
        if nd is None:
            sets["next_due_at"] = None
        else:
            sets["next_due_at"] = min(float(row["next_due_at"]), nd) if (row.get("next_due_at") is not None
                                                                         and tier < HIBERNATE) else nd
        if nt != tier:
            sets.update({"tier": nt, "last_change_at": t, "last_change_dir": +1, "holds": 0})
            _event(c, key, ctx, "tier_change", before={"tier": tier, "state": st}, after={"tier": nt,
                   "state": state_for_tier(nt)}, source=str(why), reason="wake", at=t)
        elif st == "waiting_owner":
            _event(c, key, ctx, "waiting_done", before={"state": st}, after={"state": sets["state"]}, source=str(why),
                   at=t)
        cols = ", ".join(f"{k}=?" for k in sets)
        c.execute(f"UPDATE agent_pulse SET {cols} WHERE agent_key=? AND context_ref=?", (*sets.values(), key, ctx))
        return True


def set_state(store, agent_key: str, context_ref: str, state: str, by: str = "owner",
              at: Optional[float] = None) -> int:
    """Đổi trạng thái do chủ hay host: `paused` (Tạm dừng), `resume` (Tiếp), `waiting_owner`, `off` (tắt Cộng hưởng),
    `on` (bật lại: mọi ngữ cảnh về B3, giữ ước lượng cũ, ghi `resumed_at = now`). `context_ref = '*'`: mọi dòng của agent.
    Trả số dòng đổi. Chỉ dừng phần CHỦ ĐỘNG: việc đã nhận, hạn chót, goal, lời gọi trực tiếp không đọc bảng này."""
    ensure(store)
    t = _now(at)
    key, ctx = str(agent_key), str(context_ref or "*")
    if state not in ("paused", "resume", "waiting_owner", "off", "on"):
        raise ValueError(f"trạng thái không hợp lệ: {state}")
    with store._Tx(store) as c:
        if ctx != "*":
            _ensure_row_in(c, key, ctx, t)
        else:
            _ensure_row_in(c, key, "*", t)
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM agent_pulse WHERE agent_key=?" + ("" if ctx == "*" else " AND context_ref=?"),
            (key,) if ctx == "*" else (key, ctx)).fetchall()]
        n = 0
        for r in rows:
            before = {"state": r["state"], "tier": int(r["tier"])}
            if state == "paused":
                if r["state"] in ("off", "paused"):
                    continue
                sets = {"state": "paused"}
            elif state == "resume":
                if r["state"] != "paused":
                    continue
                tier = int(r["tier"])
                sets = {"state": state_for_tier(tier), "next_due_at": None if (tier >= HIBERNATE or
                        r["context_ref"] == "*") else t + TIERS[tier]}
            elif state == "waiting_owner":
                if r["state"] in ("off", "paused") or r["context_ref"] == "*":
                    continue
                sets = {"state": "waiting_owner", "waiting_since": t, "reminded_at": None}
            elif state == "off":
                if r["state"] == "off":
                    continue
                sets = {"state": "off", "next_due_at": None}
            else:  # on
                t0 = max(INIT_TIER, int(r["max_tier"] if r["max_tier"] is not None else DEFAULT_MAX_TIER))
                sets = {"state": "awake", "tier": t0, "resumed_at": t, "last_change_at": t, "last_change_dir": 0,
                        "holds": 0, "next_due_at": None if r["context_ref"] == "*" else t + TIERS[t0]}
            sets["updated_at"] = t
            cols = ", ".join(f"{k}=?" for k in sets)
            c.execute(f"UPDATE agent_pulse SET {cols} WHERE agent_key=? AND context_ref=?",
                      (*sets.values(), key, r["context_ref"]))
            _event(c, key, r["context_ref"], state, before=before, after={k: sets[k] for k in ("state", "tier")
                                                                          if k in sets}, source=str(by), at=t)
            n += 1
        return n


def reset(store, agent_key: str, context_ref: str, by: str = "owner", at: Optional[float] = None) -> bool:
    """Đặt lại nhịp ngữ cảnh: về B3, bằng chứng trước mốc này không còn là "mới" (`resumed_at = now` của ngữ cảnh), lịch
    sử và ước lượng giữ nguyên. Trạng thái tạm dừng hay tắt giữ nguyên."""
    ensure(store)
    t = _now(at)
    key, ctx = str(agent_key), str(context_ref)
    if ctx == "*":
        raise ValueError("chọn một ngữ cảnh để đặt lại")
    with store._Tx(store) as c:
        r = _ensure_row_in(c, key, ctx, t)
        st = r["state"] if r["state"] in ("paused", "off") else "awake"
        t0 = max(INIT_TIER, int(r["max_tier"] if r["max_tier"] is not None else DEFAULT_MAX_TIER))
        c.execute("UPDATE agent_pulse SET tier=?, state=?, last_change_at=?, last_change_dir=0, holds=0, resumed_at=?, "
                  "scan_counter=0, next_due_at=?, updated_at=? WHERE agent_key=? AND context_ref=?",
                  (t0, st, t, t, t + TIERS[t0] if st == "awake" else None, t, key, ctx))
        _event(c, key, ctx, "reset", before={"tier": int(r["tier"]), "state": r["state"]},
               after={"tier": t0, "state": st}, source=str(by), at=t)
    return True


def revert(store, agent_key: str, event_id: int, by: str = "owner", at: Optional[float] = None) -> Optional[dict]:
    """Quay lại MỘT lần đổi bậc (`tier_change`): về bậc trước của sự kiện đó, ghi sự kiện `revert`. Đã quay lại rồi hay
    không phải sự kiện đổi bậc của agent này: None."""
    ensure(store)
    t = _now(at)
    with store._Tx(store) as c:
        ev = c.execute("SELECT * FROM agent_pulse_events WHERE id=? AND agent_key=?", (int(event_id),
                                                                                       str(agent_key))).fetchone()
        if ev is None or ev["kind"] != "tier_change" or ev["reverted_by"] is not None:
            return None
        before = _jl(ev["before_json"], {})
        r = _row(c, ev["agent_key"], ev["context_ref"])
        if r is None or "tier" not in before:
            return None
        nt = max(int(r["max_tier"] if r["max_tier"] is not None else DEFAULT_MAX_TIER), int(before["tier"]))
        st = r["state"] if r["state"] in ("paused", "off", "waiting_owner") else state_for_tier(nt)
        c.execute("UPDATE agent_pulse SET tier=?, state=?, last_change_at=?, last_change_dir=?, holds=0, next_due_at=?, "
                  "updated_at=? WHERE agent_key=? AND context_ref=?",
                  (nt, st, t, (1 if nt < int(r["tier"]) else -1 if nt > int(r["tier"]) else 0),
                   (t + TIERS[nt]) if (st in SCHEDULED and nt < HIBERNATE) else None, t, ev["agent_key"],
                   ev["context_ref"]))
        rid = _event(c, ev["agent_key"], ev["context_ref"], "revert", before={"tier": int(r["tier"]), "state": r["state"]},
                     after={"tier": nt, "state": st}, source=str(by), reason=f"event:{int(event_id)}", at=t)
        c.execute("UPDATE agent_pulse_events SET reverted_by=? WHERE id=?", (rid, int(event_id)))
        return {"tier": nt, "state": st, "event_id": rid}


def set_max_tier(store, agent_key: str, tier: int, by: str = "owner", at: Optional[float] = None) -> int:
    """`max_tier` (nhịp nhanh nhất, mục 9): CHỈ chủ đặt (tới B0). Trưởng nhóm, kể cả Toàn quyền, không nâng được: mọi
    người gọi khác `owner` bị từ chối. Bậc đang nhanh hơn trần mới thì chậm lại tới trần."""
    if str(by) != "owner":
        raise PermissionError("chỉ chủ mới đổi được nhịp nhanh nhất")
    nt = int(tier)
    if not 0 <= nt <= 7:
        raise ValueError("bậc không hợp lệ")
    ensure(store)
    t = _now(at)
    key = str(agent_key)
    with store._Tx(store) as c:
        _ensure_row_in(c, key, "*", t)
        rows = [dict(r) for r in c.execute("SELECT * FROM agent_pulse WHERE agent_key=?", (key,)).fetchall()]
        for r in rows:
            sets = {"max_tier": nt, "updated_at": t}
            if r["context_ref"] != "*" and int(r["tier"]) < nt:
                sets.update({"tier": nt, "last_change_at": t, "last_change_dir": -1, "holds": 0})
                if r["state"] in SCHEDULED:
                    sets["state"] = state_for_tier(nt)
                    sets["next_due_at"] = t + TIERS[nt]
            cols = ", ".join(f"{k}=?" for k in sets)
            c.execute(f"UPDATE agent_pulse SET {cols} WHERE agent_key=? AND context_ref=?",
                      (*sets.values(), key, r["context_ref"]))
        _event(c, key, "*", "max_tier", before={"max_tier": rows[0]["max_tier"] if rows else DEFAULT_MAX_TIER},
               after={"max_tier": nt}, source="owner", at=t)
        return len(rows)


def row(store, agent_key: str, context_ref: str) -> Optional[dict]:
    ensure(store)
    with closing(store._conn()) as c:
        return _row(c, str(agent_key), str(context_ref))


def rows(store, agent_key: str) -> list:
    ensure(store)
    with closing(store._conn()) as c:
        return [dict(r) for r in c.execute("SELECT * FROM agent_pulse WHERE agent_key=? ORDER BY context_ref",
                                           (str(agent_key),)).fetchall()]


def events(store, agent_key: str, context_ref: Optional[str] = None, kinds: Optional[Iterable[str]] = None,
           limit: int = 50) -> list:
    ensure(store)
    q, args = "SELECT * FROM agent_pulse_events WHERE agent_key=?", [str(agent_key)]
    if context_ref is not None:
        q += " AND context_ref=?"
        args.append(str(context_ref))
    ks = list(kinds or [])
    if ks:
        q += f" AND kind IN ({','.join('?' * len(ks))})"
        args += ks
    with closing(store._conn()) as c:
        out = []
        for r in c.execute(q + " ORDER BY id DESC LIMIT ?", (*args, int(limit))).fetchall():
            d = dict(r)
            d["before"] = _jl(d.pop("before_json"), {})
            d["after"] = _jl(d.pop("after_json"), {})
            d["payload"] = _jl(d.pop("payload_json"), {})
            out.append(d)
        return out


def record_event(store, agent_key: str, context_ref: str, kind: str, *, source: str = "host", reason: str = "",
                 payload: Any = None, at: Optional[float] = None) -> int:
    ensure(store)
    with store._Tx(store) as c:
        return _event(c, str(agent_key), str(context_ref), kind, source=source, reason=reason, payload=payload,
                      at=_now(at))


# ───────────── cơ hội (5.5) ─────────────

def fresh_opportunities(store, agent_key: str, context_ref: str, items: Iterable[dict],
                        at: Optional[float] = None) -> list:
    """Lọc danh sách cơ hội lập bằng code: mỗi cơ hội khoá `(source_ref, version)`, đã tiêu thụ thì bỏ (kể cả khi lượt
    quét trước trả `none`) cho tới khi nguồn có phiên bản mới. Ghi `first_seen_at` cho cơ hội mới."""
    ensure(store)
    t = _now(at)
    out = []
    with store._Tx(store) as c:
        for it in items or []:
            src, ver = str(it.get("source_ref") or ""), str(it.get("version") or "")
            if not src:
                continue
            r = c.execute("SELECT consumed_at FROM pulse_opportunities WHERE agent_key=? AND context_ref=? AND "
                          "source_ref=? AND version=?", (agent_key, context_ref, src, ver)).fetchone()
            if r is not None and r["consumed_at"] is not None:
                continue
            if r is None:
                c.execute("INSERT INTO pulse_opportunities(agent_key,context_ref,source_ref,version,kind,first_seen_at) "
                          "VALUES(?,?,?,?,?,?)", (agent_key, context_ref, src, ver, str(it.get("kind") or ""), t))
            out.append(dict(it, source_ref=src, version=ver))
    return out


def consume_opportunities(store, agent_key: str, context_ref: str, items: Iterable[dict], by: str,
                          at: Optional[float] = None) -> int:
    ensure(store)
    t = _now(at)
    n = 0
    with store._Tx(store) as c:
        for it in items or []:
            n += c.execute("UPDATE pulse_opportunities SET consumed_at=?, consumed_by=? WHERE agent_key=? AND "
                           "context_ref=? AND source_ref=? AND version=? AND consumed_at IS NULL",
                           (t, str(by), agent_key, context_ref, str(it.get("source_ref")),
                            str(it.get("version") or ""))).rowcount
    return n


# ───────────── đề xuất của lượt quét (5.5, 6.1) ─────────────

def record_proposal(store, *, agent_key: str, context_ref: str, source_ref: str, version: str, title: str,
                    brief: str = "", session_id: str = "", message_id: Optional[int] = None,
                    at: Optional[float] = None) -> int:
    ensure(store)
    with store._Tx(store) as c:
        cur = c.execute("INSERT INTO pulse_proposals(agent_key,context_ref,source_ref,version,title,brief,session_id,"
                        "message_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                        (str(agent_key), str(context_ref), str(source_ref), str(version or ""), str(title)[:160],
                         str(brief or "")[:4000], str(session_id or ""), message_id, _now(at)))
        return int(cur.lastrowid)


def proposal_blocked(store, agent_key: str, context_ref: str, source_ref: str, version: str) -> bool:
    """Đề xuất không mở lại khi không có dữ kiện mới (5.5): đã có đề xuất (chờ, đã bác hay đã nhận) cho cùng nguồn và
    cùng phiên bản thì không đề xuất lần nữa. Nguồn có phiên bản mới thì được."""
    ensure(store)
    with closing(store._conn()) as c:
        return c.execute("SELECT 1 FROM pulse_proposals WHERE agent_key=? AND context_ref=? AND source_ref=? AND "
                         "version=? LIMIT 1", (str(agent_key), str(context_ref), str(source_ref),
                                               str(version or ""))).fetchone() is not None


def proposal(store, proposal_id: Optional[int] = None, *, context_ref: str = "",
             message_id: Optional[int] = None) -> Optional[dict]:
    ensure(store)
    with closing(store._conn()) as c:
        if proposal_id is not None:
            r = c.execute("SELECT * FROM pulse_proposals WHERE id=?", (int(proposal_id),)).fetchone()
        else:
            r = c.execute("SELECT * FROM pulse_proposals WHERE context_ref=? AND message_id=? ORDER BY id DESC LIMIT 1",
                          (str(context_ref), int(message_id))).fetchone()
        return dict(r) if r else None


def decide_proposal(store, proposal_id: int, decision: str, by: str = "owner", task_id: str = "",
                    signal: bool = True, at: Optional[float] = None) -> Optional[dict]:
    """Chủ (hay trưởng nhóm có quyền) chấp nhận (+0.6 w 0.8) hay bác (-0.4 w 0.8) MỘT đề xuất còn chờ (CAS). `signal`:
    False khi nơi gọi đã ghi tín hiệu theo nguồn của chính nó (thẻ đề xuất trong nhóm). Đã quyết rồi: None."""
    if decision not in ("accepted", "rejected"):
        raise ValueError("quyết định không hợp lệ")
    ensure(store)
    t = _now(at)
    with store._Tx(store) as c:
        n = c.execute("UPDATE pulse_proposals SET status=?, decided_by=?, decided_at=?, task_id=? WHERE id=? AND "
                      "status='pending'", (decision, str(by), t, str(task_id or ""), int(proposal_id))).rowcount
        if not n:
            return None
        row = dict(c.execute("SELECT * FROM pulse_proposals WHERE id=?", (int(proposal_id),)).fetchone())
        on = _agent_on(c, row["agent_key"])
        _event(c, row["agent_key"], row["context_ref"], "proposal_" + ("accept" if decision == "accepted" else "reject"),
               source=str(by), reason=row["source_ref"], payload={"proposal_id": row["id"], "task_id": task_id}, at=t)
    if signal and on:
        ev = "accept" if decision == "accepted" else "reject"
        record_host_event(store, event=ev, source_ref=f"{ev}:pp:{row['id']}", agents={row["agent_key"]: 1.0},
                          context_ref=row["context_ref"], at=t, subject_ref=f"proposal:{row['id']}")
    return row


def proposals(store, agent_key: str, limit: int = 20) -> list:
    ensure(store)
    with closing(store._conn()) as c:
        return [dict(r) for r in c.execute("SELECT * FROM pulse_proposals WHERE agent_key=? ORDER BY "
                                           "CASE status WHEN 'pending' THEN 0 ELSE 1 END, id DESC LIMIT ?",
                                           (str(agent_key), int(limit))).fetchall()]


# ───────────── đã xem, tin chủ động (6.2, 6.1) ─────────────

def mark_seen(store, context_ref: str, message_ids: Iterable[int], agent_key: str = "", session_id: str = "",
              at: Optional[float] = None) -> int:
    """Ghi lần ĐẦU tin của agent được thấy (≥ 1,5 giây, tab hiển thị). Trả số tin mới ghi."""
    ensure(store)
    t = _now(at)
    n = 0
    with store._Tx(store) as c:
        for mid in message_ids or []:
            cur = c.execute("INSERT OR IGNORE INTO message_seen(context_ref,message_id,agent_key,session_id,seen_at) "
                            "VALUES(?,?,?,?,?)", (str(context_ref), int(mid), str(agent_key or ""), str(session_id or ""),
                                                  t))
            if cur.rowcount:
                n += 1
                c.execute("UPDATE pulse_proactive SET seen_at=? WHERE context_ref=? AND message_id=? AND seen_at IS NULL",
                          (t, str(context_ref), int(mid)))
    return n


def seen_at(store, context_ref: str, message_id: int) -> Optional[float]:
    ensure(store)
    with closing(store._conn()) as c:
        r = c.execute("SELECT seen_at FROM message_seen WHERE context_ref=? AND message_id=?",
                      (str(context_ref), int(message_id))).fetchone()
        return float(r["seen_at"]) if r else None


def record_proactive(store, agent_key: str, context_ref: str, session_id: str, message_id: int,
                     at: Optional[float] = None) -> None:
    ensure(store)
    t = _now(at)
    with store._Tx(store) as c:
        seen = c.execute("SELECT seen_at FROM message_seen WHERE context_ref=? AND message_id=?",
                         (str(context_ref), int(message_id))).fetchone()
        c.execute("INSERT OR IGNORE INTO pulse_proactive(agent_key,context_ref,session_id,message_id,said_at,seen_at) "
                  "VALUES(?,?,?,?,?,?)", (str(agent_key), str(context_ref), str(session_id or ""), int(message_id), t,
                                          seen["seen_at"] if seen else None))


# ───────────── mốc hẹn kiểm lại (Auto toàn quyền, 2026-11-14) ─────────────
#
# Chủ repo 14/11/2026: bật Auto là agent tự quét công cụ, TỰ ĐẶT LỊCH NHẮC và chỉ nhắn gợi ý, nhắc nhở thật sự hữu ích, đúng
# lúc. Nhịp theo bậc (1 giờ ... 1 tháng) không đủ cho "tối hôm trước giải chạy": agent tự hẹn một mốc, tới mốc thì một lần
# thức riêng (không đổi bậc). Mốc là việc agent tự đặt, không phải nghĩa vụ: tạm dừng, tắt hay ngủ đông thì mốc không kích
# hoạt (còn nằm chờ tới lần thức kế).

FOLLOWUP_MIN_S = 600.0              # mốc sớm nhất: 10 phút sau lúc hẹn
FOLLOWUP_MAX_S = 60 * DAY           # muộn nhất: 60 ngày
FOLLOWUP_MAX_PENDING = 8            # mỗi (agent, ngữ cảnh) giữ tối đa 8 mốc đang chờ
FOLLOWUP_MAX_PER_SCAN = 3           # một lượt quét hẹn tối đa 3 mốc
FOLLOWUP_NOTE_MAX = 300
FOLLOWUP_DEDUP_S = 1800.0           # cùng ghi chú, cách nhau dưới 30 phút: coi là một mốc


def parse_when(value: Any, tz: Any = None) -> Optional[float]:
    """Mốc giờ agent viết ra thành epoch. Nhận số (epoch giây) hay chuỗi ISO ("2026-11-14 19:00", "2026-11-14T19:00+07:00").
    Chuỗi không có múi giờ hiểu theo `tz` (múi giờ của chủ); thiếu `tz` thì UTC. Sai dạng: None."""
    from datetime import datetime, timezone
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        return v if math.isfinite(v) and v > 0 else None
    s = str(value or "").strip()
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=tz or timezone.utc)
    return d.timestamp()


def add_followups(store, agent_key: str, context_ref: str, items: Iterable[Any], *, tz: Any = None, by: str = "",
                  at: Optional[float] = None) -> dict:
    """Ghi các mốc agent vừa hẹn ({"at", "note"}). Kẹp vào [lúc hẹn + 10 phút, + 60 ngày], bỏ mốc trùng (cùng ghi chú, cách
    dưới 30 phút), tối đa 3 mốc mỗi lần và 8 mốc đang chờ mỗi ngữ cảnh. Trả {"added": [...], "dropped": [lý do...]}."""
    ensure(store)
    t = _now(at)
    key, ctx = str(agent_key), str(context_ref)
    added, dropped = [], []
    with store._Tx(store) as c:
        n_pending = c.execute("SELECT COUNT(*) FROM pulse_followups WHERE agent_key=? AND context_ref=? AND "
                              "status='pending'", (key, ctx)).fetchone()[0]
        for it in list(items or [])[:3 * FOLLOWUP_MAX_PER_SCAN]:
            if len(added) >= FOLLOWUP_MAX_PER_SCAN:
                dropped.append("per_scan")
                continue
            if not isinstance(it, dict):
                dropped.append("bad_item")
                continue
            due = parse_when(it.get("at"), tz)
            note = " ".join(str(it.get("note") or "").split())[:FOLLOWUP_NOTE_MAX]
            if due is None:
                dropped.append("bad_time")
                continue
            if due > t + FOLLOWUP_MAX_S:
                dropped.append("too_far")
                continue
            due = max(due, t + FOLLOWUP_MIN_S)
            if n_pending >= FOLLOWUP_MAX_PENDING:
                dropped.append("too_many")
                continue
            dup = c.execute("SELECT id FROM pulse_followups WHERE agent_key=? AND context_ref=? AND status='pending' AND "
                            "note=? AND ABS(due_at-?)<?", (key, ctx, note, due, FOLLOWUP_DEDUP_S)).fetchone()
            if dup is not None:
                dropped.append("duplicate")
                continue
            fid = c.execute("INSERT INTO pulse_followups(agent_key,context_ref,due_at,note,created_at,created_by) "
                            "VALUES(?,?,?,?,?,?)", (key, ctx, due, note, t, str(by or ""))).lastrowid
            n_pending += 1
            added.append({"id": int(fid), "due_at": due, "note": note})
        if added:
            _event(c, key, ctx, "followup_set", source="agent", reason=str(by or ""),
                   payload={"added": added, "dropped": dropped}, at=t)
    return {"added": added, "dropped": dropped}


def cancel_followups(store, agent_key: str, context_ref: str, ids: Iterable[Any], *, by: str = "",
                     at: Optional[float] = None) -> int:
    """Huỷ mốc đang chờ của CHÍNH (agent, ngữ cảnh) này (mã của ngữ cảnh khác bị bỏ qua)."""
    ensure(store)
    t = _now(at)
    want = []
    for x in list(ids or [])[:FOLLOWUP_MAX_PENDING]:
        try:
            want.append(int(x))
        except (TypeError, ValueError):
            continue
    if not want:
        return 0
    n = 0
    with store._Tx(store) as c:
        for fid in want:
            n += c.execute("UPDATE pulse_followups SET status='cancelled', closed_at=?, closed_by=? WHERE id=? AND "
                           "agent_key=? AND context_ref=? AND status='pending'",
                           (t, str(by or ""), fid, str(agent_key), str(context_ref))).rowcount
        if n:
            _event(c, str(agent_key), str(context_ref), "followup_cancel", source="agent", reason=str(by or ""),
                   payload={"ids": want}, at=t)
    return n


def pending_followups(store, agent_key: str, context_ref: str, limit: int = FOLLOWUP_MAX_PENDING) -> list:
    ensure(store)
    with closing(store._conn()) as c:
        return [dict(r) for r in c.execute(
            "SELECT id, due_at, note, created_at, fired_at FROM pulse_followups WHERE agent_key=? AND context_ref=? AND "
            "status='pending' ORDER BY due_at LIMIT ?", (str(agent_key), str(context_ref), int(limit))).fetchall()]


def take_due_followups(store, agent_key: str, context_ref: str, at: Optional[float] = None) -> list:
    """Mốc đang chờ đã tới giờ của (agent, ngữ cảnh), đánh dấu đã kích hoạt (`fired_at`). Mốc vẫn `pending` tới khi một lượt
    quét chạy xong (`close_followups`); lượt lỗi thì mốc chờ lần thức theo bậc kế tiếp, không kích hoạt lại mỗi nhịp."""
    ensure(store)
    t = _now(at)
    with store._Tx(store) as c:
        rows = [dict(r) for r in c.execute(
            "SELECT id, due_at, note, fired_at FROM pulse_followups WHERE agent_key=? AND context_ref=? AND "
            "status='pending' AND due_at<=? ORDER BY due_at LIMIT ?",
            (str(agent_key), str(context_ref), t, FOLLOWUP_MAX_PENDING)).fetchall()]
        for r in rows:
            if r.get("fired_at") is None:
                c.execute("UPDATE pulse_followups SET fired_at=? WHERE id=?", (t, r["id"]))
    return rows


def close_followups(store, ids: Iterable[Any], *, by: str = "", at: Optional[float] = None) -> int:
    ensure(store)
    t = _now(at)
    n = 0
    with store._Tx(store) as c:
        for fid in ids or []:
            n += c.execute("UPDATE pulse_followups SET status='done', closed_at=?, closed_by=? WHERE id=? AND "
                           "status='pending'", (t, str(by or ""), int(fid))).rowcount
    return n


def followup_wakes(store, at: Optional[float] = None, limit: int = 50) -> list:
    """Dòng nhịp có mốc tới giờ CHƯA kích hoạt (chỉ ĐỌC; host nhận lịch bằng CAS như lịch theo bậc). Chỉ trạng thái có lịch
    (active, awake, slowed) và chưa bị nhận."""
    ensure(store)
    t = _now(at)
    with closing(store._conn()) as c:
        return [dict(r) for r in c.execute(
            "SELECT p.*, (SELECT MIN(f.due_at) FROM pulse_followups f WHERE f.agent_key=p.agent_key AND "
            "f.context_ref=p.context_ref AND f.status='pending' AND f.fired_at IS NULL AND f.due_at<=?) AS followup_due "
            "FROM agent_pulse p WHERE p.context_ref<>'*' AND p.state IN ('active','awake','slowed') AND "
            "(p.claim_until IS NULL OR p.claim_until<?) AND EXISTS (SELECT 1 FROM pulse_followups f WHERE "
            "f.agent_key=p.agent_key AND f.context_ref=p.context_ref AND f.status='pending' AND f.fired_at IS NULL AND "
            "f.due_at<=?) LIMIT ?", (t, t, t, int(limit))).fetchall()]


def sweep_seen_ignored(store, interacted: Callable[[dict], bool], at: Optional[float] = None) -> list:
    """Tin CHỦ ĐỘNG đã có bằng chứng xem, qua 24 giờ kể từ lúc xem mà không tương tác: tín hiệu -0,15 w 0,6 (nguồn
    `seen:<ngữ cảnh>:<mã tin>`). Chưa có bằng chứng xem: không tạo tín hiệu (chưa biết). Agent tắt Cộng hưởng: bỏ qua."""
    ensure(store)
    t = _now(at)
    with closing(store._conn()) as c:
        due = [dict(r) for r in c.execute("SELECT * FROM pulse_proactive WHERE outcome='' AND seen_at IS NOT NULL AND "
                                          "seen_at<=?", (t - SEEN_WAIT_S,)).fetchall()]
    done = []
    for p in due:
        with closing(store._conn()) as c:
            on = _agent_on(c, p["agent_key"])
        try:
            hit = bool(interacted(p))
        except Exception:  # noqa: BLE001
            continue
        ref = ""
        outcome = "interacted" if hit else ("ignored" if on else "skipped_off")
        if not hit and on:
            ref = f"seen:{p['context_ref']}:{int(p['message_id'])}"
            v, w = SEEN_IGNORED
            record_signal(store, source_ref=ref, agent_key=p["agent_key"], context_ref=p["context_ref"],
                          kind="seen_ignored", value=v, w=w, at=t, subject_ref=f"{p['context_ref']}:{p['message_id']}")
            done.append(ref)
        with store._Tx(store) as c:
            c.execute("UPDATE pulse_proactive SET outcome=?, signal_ref=? WHERE id=? AND outcome=''", (outcome, ref, p["id"]))
    return done


# ───────────── thay đổi chính sách, quay lại (6.4) ─────────────

def register_policy_reverter(kind: str, fn: Callable[[dict], Any]) -> None:
    """Phần J (độ lệch ngưỡng) và L (bài học, độ hăng hái) đăng ký hàm quay lại cho loại thay đổi của mình."""
    _POLICY_REVERTERS[str(kind)] = fn


def apply_policy_change(store, agent_key: str, context_ref: str, change: dict, at: Optional[float] = None) -> int:
    """Ghi một thay đổi CHÍNH SÁCH đã áp (độ lệch ngưỡng, độ hăng hái, bài học tự áp, phiên bản pulse) và mở cửa sổ quan
    sát (≥ 6 nhãn hay ≥ 5 tín hiệu mới, tối đa 14 ngày). `change`: {kind, before, after, source, base_error_rate?}.
    Không áp cho bước bậc (bậc chỉ theo 5.3). Trả mã thay đổi."""
    ensure(store)
    t = _now(at)
    key, ctx = str(agent_key), str(context_ref)
    kind = str((change or {}).get("kind") or "").strip()
    if not kind:
        raise ValueError("thiếu loại thay đổi")
    with store._Tx(store) as c:
        r = _ensure_row_in(c, key, ctx, t) if ctx != "*" else _ensure_row_in(c, key, "*", t)
        sc = _score_rows(c, _live_signals(c, key, None if ctx == "*" else ctx), t, 0.0)
        cur = c.execute("INSERT INTO pulse_policy_changes(agent_key,context_ref,kind,before_json,after_json,source,"
                        "policy_version,base_estimate,base_conf,base_error,created_at,window_until) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (key, ctx, kind, _j(change.get("before")), _j(change.get("after")),
                         str(change.get("source") or ""), str(r.get("policy_version") or POLICY_VERSION),
                         sc["estimate"], sc["confidence"], change.get("base_error_rate"), t, t + POLICY_WINDOW_S))
        cid = int(cur.lastrowid)
        if kind == "pulse_version" and change.get("after"):
            c.execute("UPDATE agent_pulse SET policy_version=? WHERE agent_key=?", (str(change["after"]), key))
        _event(c, key, ctx, "policy_change", before=change.get("before"), after=change.get("after"),
               source=str(change.get("source") or ""), reason=kind, payload={"change_id": cid}, at=t)
        return cid


def record_policy_labels(store, change_id: int, labels: int, errors: int) -> None:
    """Phần J báo số nhãn và số lỗi phán xử từ sau thay đổi (để luật "tỷ lệ lỗi tăng quá 0,15")."""
    ensure(store)
    with store._Tx(store) as c:
        c.execute("UPDATE pulse_policy_changes SET labels=?, errors=? WHERE id=?", (int(labels), int(errors),
                                                                                    int(change_id)))


def revert_policy_change(store, change_id: int, reason: str = "owner", by: str = "owner",
                         at: Optional[float] = None) -> Optional[dict]:
    """Quay lại một thay đổi chính sách: gọi hàm quay lại đã đăng ký của loại đó (J/L), đánh `reverted`, ghi lý do.
    Đã quyết rồi thì None."""
    ensure(store)
    t = _now(at)
    with closing(store._conn()) as c:
        r = c.execute("SELECT * FROM pulse_policy_changes WHERE id=?", (int(change_id),)).fetchone()
    if r is None or r["status"] == "reverted":
        return None
    ch = dict(r)
    ch["before"], ch["after"] = _jl(ch.pop("before_json"), {}), _jl(ch.pop("after_json"), {})
    fn = _POLICY_REVERTERS.get(ch["kind"])
    # Hàm quay lại của J/L biết ai quay lại và vì sao (chủ bấm nút thì ghi `owner`, không phải `policy_revert`).
    ch["revert_reason"], ch["revert_by"] = str(reason), str(by)
    if fn is not None:
        fn(ch)
    with store._Tx(store) as c:
        if ch["kind"] == "pulse_version" and ch["before"]:
            c.execute("UPDATE agent_pulse SET policy_version=? WHERE agent_key=?", (str(ch["before"]), ch["agent_key"]))
        n = c.execute("UPDATE pulse_policy_changes SET status='reverted', decided_at=?, decided_reason=? WHERE id=? AND "
                      "status<>'reverted'", (t, str(reason), int(change_id))).rowcount
        if n:
            _event(c, ch["agent_key"], ch["context_ref"], "policy_revert", before=ch["after"], after=ch["before"],
                   source=str(by), reason=str(reason), payload={"change_id": int(change_id),
                                                                "reverter": fn is not None}, at=t)
    ch["status"] = "reverted"
    return ch


def observe_policy_changes(store, at: Optional[float] = None) -> list:
    """Đóng các cửa sổ quan sát đã đủ (6.4): tỷ lệ lỗi phán xử tăng quá 0,15 (≥ 6 nhãn) hay `estimate` của ngữ cảnh giảm
    quá 0,3 khi `confidence ≥ 0.5` thì tự quay lại và ghi lý do; còn lại `kept`. Chưa đủ cửa sổ: không tuyên bố gì."""
    ensure(store)
    t = _now(at)
    with closing(store._conn()) as c:
        open_rows = [dict(r) for r in c.execute("SELECT * FROM pulse_policy_changes WHERE status='observing'").fetchall()]
    out = []
    for ch in open_rows:
        with closing(store._conn()) as c:
            ctx = None if ch["context_ref"] == "*" else ch["context_ref"]
            sigs = _live_signals(c, ch["agent_key"], ctx)
            sc = _score_rows(c, sigs, t, 0.0)
            n_new = sum(1 for s in sigs if s["kind"] not in _NOT_EVIDENCE and float(s["at"]) > float(ch["created_at"]))
        done = int(ch["labels"]) >= 6 or n_new >= 5 or t >= float(ch["window_until"])
        if not done:
            continue
        why = ""
        if int(ch["labels"]) >= 6 and ch["base_error"] is not None and \
                int(ch["errors"]) / max(1, int(ch["labels"])) - float(ch["base_error"]) > 0.15:
            why = "judge_error_up"
        elif sc["confidence"] >= 0.5 and sc["estimate"] - float(ch["base_estimate"]) < -0.3:
            why = "estimate_down"
        if why:
            revert_policy_change(store, ch["id"], reason=why, by="auto", at=t)
            out.append({"change_id": ch["id"], "decision": "reverted", "reason": why})
        else:
            with store._Tx(store) as c:
                c.execute("UPDATE pulse_policy_changes SET status='kept', decided_at=?, decided_reason='window_ok' "
                          "WHERE id=? AND status='observing'", (t, ch["id"]))
            out.append({"change_id": ch["id"], "decision": "kept", "reason": "window_ok"})
    return out


def policy_changes(store, agent_key: str, limit: int = 20) -> list:
    ensure(store)
    with closing(store._conn()) as c:
        out = []
        for r in c.execute("SELECT * FROM pulse_policy_changes WHERE agent_key=? ORDER BY id DESC LIMIT ?",
                           (str(agent_key), int(limit))).fetchall():
            d = dict(r)
            d["before"], d["after"] = _jl(d.pop("before_json"), {}), _jl(d.pop("after_json"), {})
            out.append(d)
        return out


# ───────────── hiển thị ─────────────

def view(store, agent_key: str, at: Optional[float] = None) -> dict:
    """Khung `GET /agents/{slug}/pulse` (phần nhịp): trạng thái và bậc theo từng ngữ cảnh, tổng hợp `*` (chỉ hiển thị),
    lần xem xét gần nhất và dự kiến, lý do thức, đổi nhịp gần đây (trước/sau, nguồn), phản hồi đã xử lý và trạng thái."""
    ensure(store)
    t = _now(at)
    key = str(agent_key)
    with closing(store._conn()) as c:
        on = _agent_on(c, key)
        rs = [dict(r) for r in c.execute("SELECT * FROM agent_pulse WHERE agent_key=? ORDER BY context_ref",
                                         (key,)).fetchall()]
        agg = _aggregate_in(c, key, t)
        sig_rows = [dict(r) for r in c.execute(
            "SELECT source_ref, context_ref, kind, value, w, share, emoji, reasons_json, status, superseded_by, at "
            "FROM pulse_signals WHERE agent_key=? AND kind<>'context_init' ORDER BY id DESC LIMIT 20", (key,)).fetchall()]
    contexts = []
    for r in rs:
        tier = int(r["tier"])
        item = {"context_ref": r["context_ref"], "state": r["state"], "tier": tier, "interval_s": interval(tier),
                "max_tier": int(r["max_tier"] if r["max_tier"] is not None else DEFAULT_MAX_TIER),
                "next_due_at": r["next_due_at"], "last_eval_at": r["last_eval_at"],
                "last_wake_why": r.get("last_wake_why") or "", "last_wake_at": r.get("last_wake_at"),
                "estimate": r["estimate"], "confidence": r["confidence"], "n_eff": r["n_eff"],
                "u": r.get("last_u") or 0.0, "quota_wait": bool(r.get("quota_wait")),
                "waiting_since": r.get("waiting_since"), "resumed_at": r["resumed_at"],
                "policy_version": r["policy_version"]}
        if r["context_ref"] == "*":
            item.update({"estimate": agg["estimate"], "confidence": agg["confidence"], "n_eff": agg["n_eff"],
                         "u": agg["u"]})
        contexts.append(item)
    star = next((x for x in contexts if x["context_ref"] == "*"), None)
    per = [x for x in contexts if x["context_ref"] != "*"]
    if star is not None and per:
        star["tier"] = min(x["tier"] for x in per)
    changes = events(store, key, kinds=("tier_change", "revert", "reset", "max_tier", "on", "off", "paused", "resume",
                                        "policy_change", "policy_revert"), limit=20)
    recent = events(store, key, kinds=("scan", "no_action", "quota", "said", "propose", "enqueue", "waiting_remind",
                                       "deferred"), limit=10)
    feedback = []
    for s in sig_rows:
        feedback.append({"source_ref": s["source_ref"], "context_ref": s["context_ref"], "kind": s["kind"],
                         "emoji": s["emoji"], "reasons": _jl(s["reasons_json"], []), "value": s["value"], "w": s["w"],
                         "share": s["share"], "status": s["status"], "superseded_by": s["superseded_by"], "at": s["at"]})
    return {"agent_key": key, "resonance": on, "policy_version": POLICY_VERSION, "tiers": list(TIERS),
            "aggregate": star, "contexts": per, "changes": changes, "recent": recent, "feedback": feedback,
            "policy_changes": policy_changes(store, key, 10), "proposals": proposals(store, key, 10),
            "followups": followups_of(store, key)}


def followups_of(store, agent_key: str, limit: int = 20) -> list:
    """Mốc đang chờ của một agent ở mọi ngữ cảnh (cho bảng Nhịp: chủ thấy trợ lý định kiểm lại gì, lúc nào)."""
    ensure(store)
    with closing(store._conn()) as c:
        return [dict(r) for r in c.execute(
            "SELECT id, context_ref, due_at, note, created_at FROM pulse_followups WHERE agent_key=? AND status='pending' "
            "ORDER BY due_at LIMIT ?", (str(agent_key), int(limit))).fetchall()]
