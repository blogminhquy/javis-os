"""Các thao tác TỐN LƯỢT của bộ chạy pilot achieve (lần 3), tách khỏi script để test được bằng ca âm.

Review bộ chạy achieve (PR #579, P2-1): một kiểm hỏng chỉ được ghi lại, còn luồng vẫn dựng server giai đoạn 2 và cấp
lượt bản sửa. Sửa bằng CỔNG CHI PHÍ đặt ngay trong ba thao tác có thể dẫn tới lượt gọi model: dựng server (nhịp chạy
là lịch được nhận), gửi tin chat, bấm xác nhận. Đã có bất kỳ kiểm nào hỏng thì cả ba từ chối, nên không nhánh điều
phối nào (kể cả nhánh viết sau này) cấp thêm lượt sau khi tiền điều kiện đã hỏng.

P2-2: tin báo của một giai đoạn phải là tin MỚI của đúng giai đoạn đó: dòng outbox đúng mục tiêu, đúng loại, đúng
revision, và tin `outbox:<id>` có biên nhận nằm trong ĐÚNG phiên người giao việc. Cờ `delivered` của outbox không đủ.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time


class GateClosed(Exception):
    """Cổng chi phí đóng: không cấp thêm lượt hay thao tác nào nữa."""


class Checks:
    """Ghi kết quả kiểm và giữ CỔNG CHI PHÍ. kind=technical: lỗi host/bộ chạy; kind=contract: lệch hợp đồng kịch bản.
    Cả hai đều đóng cổng."""

    def __init__(self, echo=print):
        self.log, self.fails, self.contract, self.echo = [], [], [], echo

    def check(self, name, cond, kind="technical") -> bool:
        self.echo(("ok   " if cond else "FAIL ") + name)
        self.log.append({"check": name, "ok": bool(cond), "kind": kind})
        if not cond:
            (self.contract if kind == "contract" else self.fails).append(name)
        return bool(cond)

    def failures(self) -> list:
        return self.fails + self.contract

    def require(self, action: str) -> None:
        bad = self.failures()
        if bad:
            raise GateClosed(f"{action}: không làm vì đã có {len(bad)} kiểm hỏng (đầu tiên: {bad[0]})")


class Server:
    """Server Javis thật của checkout. start() đi qua cổng chi phí TRƯỚC khi dựng tiến trình; kill() không qua cổng
    (dừng luôn được phép). popen/health thay được trong test."""

    def __init__(self, *, root, port, base, env0, phase_ceiling, checks, cli="", popen=None, health=None):
        self.root, self.port, self.base, self.env0 = root, port, base, env0
        self.phase_ceiling, self.checks, self.cli = phase_ceiling, checks, cli
        self.popen = popen or subprocess.Popen
        self.health = health or self._health
        self.n, self.proc, self.started = 0, None, []

    def _health(self) -> bool:
        import httpx
        try:
            return httpx.get(f"http://127.0.0.1:{self.port}/health", timeout=2).status_code == 200
        except Exception:  # noqa: BLE001
            return False

    def env_for(self, phase: int, tick_paused: bool, extra: dict) -> dict:
        env = {**self.env0, **extra, "JAVIS_PORT": str(self.port), "JAVIS_REQUIRE_LOGIN": "0", "PYTHONUTF8": "1",
               "JAVIS_RESONANCE_CALL_CEILING": str(self.phase_ceiling[phase])}
        if self.cli:
            env["JAVIS_CLAUDE_CLI"] = self.cli
        if tick_paused:
            env["JAVIS_RESONANCE_TICK_PAUSED"] = "1"
        return env

    def start(self, phase: int, tick_paused: bool, extra: dict, wait_s=120):
        self.checks.require(f"dựng server giai đoạn {phase} ({'nhịp dừng' if tick_paused else 'nhịp chạy'})")
        self.n += 1
        env = self.env_for(phase, tick_paused, extra)
        self.started.append({"n": self.n, "phase": phase, "tick_paused": tick_paused,
                             "call_ceiling": env["JAVIS_RESONANCE_CALL_CEILING"], "cli_pinned": bool(self.cli)})
        log = open(os.path.join(str(self.base), f"server-{self.n}.log"), "w", encoding="utf-8")
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        self.proc = self.popen([sys.executable, "server/main.py"], cwd=str(self.root), env=env, stdout=log,
                               stderr=subprocess.STDOUT, creationflags=flags)
        t0 = time.time()
        while time.time() - t0 < wait_s:
            if self.proc.poll() is not None:
                raise RuntimeError(f"server thoát sớm, xem server-{self.n}.log")
            if self.health():
                return round(time.time() - t0, 1)
            time.sleep(1)
        raise RuntimeError("server không lên kịp")

    def kill(self):
        if self.proc is None:
            return
        if os.name == "nt" and hasattr(self.proc, "pid") and self.popen is subprocess.Popen:
            subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"], capture_output=True)
        else:
            self.proc.kill()
        self.proc.wait(timeout=30)
        self.proc = None
        if self.popen is subprocess.Popen:
            time.sleep(2)


def chat_turn(checks, ledger, label, send):
    """MỘT lượt chat: qua cổng chi phí, rồi giữ chỗ trong sổ TRƯỚC khi gửi. Lỗi hay hết giờ vẫn tính, không thử lại.
    `send()` trả (session_id, frames, tools, answer). Trả (kết quả của send, trạng thái đã ghi vào sổ)."""
    checks.require(f"gửi tin chat {label}")
    if not ledger.reserve(label):
        raise GateClosed(f"{label}: hết lượt chat đã duyệt ({ledger.used()}/{ledger.limit}), không gửi")
    try:
        res = send()
    except Exception as e:  # noqa: BLE001
        ledger.settle(label, f"error:{type(e).__name__}")
        raise GateClosed(f"{label}: lượt chat lỗi ({type(e).__name__}); đã tính vào hạn mức, không thử lại")
    frames = res[1] or []
    status = "done" if frames and frames[-1] == "turn_done" else "incomplete"
    ledger.settle(label, status)
    return res, status


def accept(checks, http, goal_id, view, criterion, tag="pilot3"):
    """Bấm "Đạt yêu cầu" cho MỘT tiêu chí qua API (thao tác mô phỏng). Qua cổng chi phí trước."""
    checks.require(f"bấm Đạt yêu cầu cho {criterion.get('id')}")
    return http("POST", f"/goals/{goal_id}/feedback",
                json={"kind": "outcome_accepted", "expected_revision": view["revision"],
                      "criterion_id": criterion["id"], "artifact_ref": view.get("artifact_ref"),
                      "idempotency_key": f"{tag}-accept-{goal_id}-{criterion['id']}"})


def outbox_rows(raw_rows) -> list:
    """Chuẩn hoá dòng outbox (id, goal_id, kind, payload_json, delivered_at) thành dict có revision."""
    out = []
    for r in raw_rows:
        try:
            payload = json.loads(r[3] or "{}")
        except Exception:  # noqa: BLE001
            payload = {}
        out.append({"id": int(r[0]), "goal_id": r[1], "kind": r[2], "revision": payload.get("revision"),
                    "delivered": r[4] is not None})
    return out


def stage_notice(rows, session_reports, goal_id, kind, revision) -> tuple:
    """Tin báo của ĐÚNG giai đoạn đã về ĐÚNG phiên chưa. rows: outbox_rows(); session_reports: các khối báo cáo đọc
    từ phiên người giao việc ({goal_id, report, receipt}).

    Đạt khi: có ít nhất một dòng outbox của goal_id, loại `kind`, revision `revision`; MỌI dòng như thế đã giao; và
    mỗi dòng có tin `outbox:<id>` của goal_id kèm biên nhận trong phiên. Tin của loại khác (thẻ reframe), revision
    khác (bản đầu) hay phiên khác không được tính. Trả (ok, lý do)."""
    want = [r for r in rows if r["goal_id"] == goal_id and r["kind"] == kind and r["revision"] == revision]
    if not want:
        return False, f"không có tin {kind} nào cho revision {revision}"
    for r in want:
        if not r["delivered"]:
            return False, f"tin outbox:{r['id']} chưa giao"
        key = f"outbox:{r['id']}"
        hits = [x for x in session_reports if x.get("report") == key and x.get("goal_id") == goal_id]
        if not hits:
            return False, f"tin {key} không có trong phiên người giao việc"
        if not all(x.get("receipt") for x in hits):
            return False, f"tin {key} trong phiên không có biên nhận của host"
    return True, f"{len(want)} tin {kind} của revision {revision} có trong phiên, có biên nhận"
