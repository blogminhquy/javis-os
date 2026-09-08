"""Danh sách model LIVE từ chính Codex CLI.

Codex app-server là giao diện ổn định mà các client Codex dùng để dựng model
picker.  Hỏi ``model/list`` ở đây giúp Javis tự thấy model mới, model mặc định
và các đợt ẩn/deprecate mà không phải ghim version model trong source.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from typing import Any, Optional

from claude_cli import find_codex_cli


def _no_window() -> int:
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


# Thang effort mỗi model Codex nhận, do CHÍNH Codex khai trong `model/list`. Nhớ trong RAM,
# ghi mỗi lần `list_models` chạy trót lọt.
#
# Vì sao phải nhớ chứ không hỏi lại lúc cần: `list_models` đẻ một tiến trình `codex app-server`
# và mất vài giây - không được phép nằm trên đường chat. Bù lại, đường lấy danh sách model
# (trang Models, hộp chọn model, /provider/models) đều gọi qua đây, nên máy đang chạy thì bảng
# này gần như luôn có sẵn. Chưa có thì `efforts_for` trả rỗng và caller KHÔNG truyền effort -
# lượt chat chạy bằng mặc định của Codex, đúng như trước, chứ không hỏng.
_EFFORTS: dict = {}


def efforts_for(model: str) -> list:
    """Các mức effort model này nhận, theo lời của chính Codex. [] = chưa biết."""
    return list(_EFFORTS.get(str(model or "").strip()) or [])


def _nho_efforts(items) -> None:
    for x in items or []:
        muc = [m for m in (x.get("supported_reasoning_efforts") or []) if m]
        if x.get("id") and muc:
            _EFFORTS[x["id"]] = muc


# Thang effort của Codex, xếp từ nhẹ tới nặng. Chỉ dùng để SẮP XẾP thang mà model tự khai,
# không phải để quyết định model nhận mức nào - cái đó là lời của Codex.
_THANG = ("minimal", "low", "medium", "high", "xhigh", "max")


def muc_cho(model: str, muc_javis: str) -> str:
    """Mức của Javis -> mức effort của Codex, lấy từ THANG CỦA CHÍNH MODEL ĐÓ. "" = đừng truyền.

    Không có bảng dịch chép tay, và đó là chủ ý: Codex đổi thang theo từng model và từng đợt
    (`minimal` chỉ vài model có, `xhigh` mới thêm sau). Bảng chép tay thì sai lặng lẽ, còn giá
    trị model không nhận thì hỏng cả lượt chat. Ở đây mọi giá trị trả ra đều LẤY TỪ danh sách
    mà chính Codex vừa khai cho model đó, nên không bao giờ gửi một mức nó không hiểu.

    Luật: "ultra" là nấc trên cùng của Javis nên luôn ra nấc CAO NHẤT model có. Mấy nấc còn
    lại lấy đúng tên nếu model có, không thì lùi xuống nấc thấp hơn gần nhất - lùi chứ không
    tiến, vì tiến là tiêu nhiều tiền hơn mức người dùng chọn.
    """
    thang = [m for m in _THANG if m in efforts_for(model)]
    if not thang or not muc_javis or muc_javis == "off":
        return ""
    if muc_javis == "ultra":
        return thang[-1]
    if muc_javis in thang:
        return muc_javis
    if muc_javis not in _THANG:
        return ""
    i = _THANG.index(muc_javis)
    thap_hon = [m for m in thang if _THANG.index(m) < i]
    return thap_hon[-1] if thap_hon else thang[0]


def _normalize_items(items: Any) -> list[dict]:
    """Chuẩn hoá model/list, giữ nguyên thứ tự picker của Codex và bỏ bản ẩn."""
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for raw in items:
        if not isinstance(raw, dict) or raw.get("hidden"):
            continue
        model_id = str(raw.get("id") or raw.get("model") or "").strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        out.append({
            "id": model_id,
            "display_name": str(raw.get("displayName") or model_id),
            "description": str(raw.get("description") or ""),
            "is_default": bool(raw.get("isDefault")),
            "default_reasoning_effort": raw.get("defaultReasoningEffort"),
            "supported_reasoning_efforts": [
                str(x.get("reasoningEffort"))
                for x in (raw.get("supportedReasoningEfforts") or [])
                if isinstance(x, dict) and x.get("reasoningEffort")
            ],
            "upgrade": raw.get("upgrade"),
        })
    # Codex thường đã xếp default đầu tiên. Bảo đảm điều đó để fallback của
    # Javis cũng dùng đúng default hiện hành nếu upstream đổi thứ tự.
    out.sort(key=lambda x: not x["is_default"])
    return out


def list_models(timeout: float = 20.0, cli_path: Optional[str] = None,
                popen_factory=subprocess.Popen) -> Optional[dict]:
    """Gọi Codex app-server ``model/list``.

    Trả ``None`` khi CLI cũ/chưa cài/chưa đăng nhập để caller dùng nguồn dự
    phòng. Không để subprocess sống sót sau request.
    """
    cli = cli_path or find_codex_cli()
    if not cli:
        return None

    proc = None
    messages: queue.Queue = queue.Queue()
    deadline = time.monotonic() + max(1.0, float(timeout))

    def remaining() -> float:
        return max(0.05, deadline - time.monotonic())

    def send(payload: dict) -> None:
        assert proc is not None and proc.stdin is not None
        proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        proc.stdin.flush()

    def reader() -> None:
        assert proc is not None and proc.stdout is not None
        try:
            for line in iter(proc.stdout.readline, ""):
                try:
                    messages.put(json.loads(line))
                except (TypeError, json.JSONDecodeError):
                    continue
        finally:
            messages.put(None)

    def response(request_id: int) -> Optional[dict]:
        while time.monotonic() < deadline:
            try:
                msg = messages.get(timeout=remaining())
            except queue.Empty:
                return None
            if msg is None:
                return None
            if isinstance(msg, dict) and msg.get("id") == request_id:
                return msg
        return None

    try:
        proc = popen_factory(
            [cli, "app-server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=_no_window(),
        )
        threading.Thread(target=reader, name="javis-codex-models", daemon=True).start()
        send({
            "method": "initialize",
            "id": 0,
            "params": {
                "clientInfo": {
                    "name": "javis_os",
                    "title": "Javis OS",
                    "version": "1.0",
                }
            },
        })
        init = response(0)
        if not init or init.get("error"):
            return None
        send({"method": "initialized", "params": {}})

        all_items: list[dict] = []
        cursor = None
        request_id = 1
        while time.monotonic() < deadline:
            params: dict[str, Any] = {"limit": 100, "includeHidden": False}
            if cursor:
                params["cursor"] = cursor
            send({"method": "model/list", "id": request_id, "params": params})
            msg = response(request_id)
            if not msg or msg.get("error"):
                return None
            result = msg.get("result") or {}
            all_items.extend(result.get("data") or [])
            cursor = result.get("nextCursor")
            if not cursor:
                break
            request_id += 1

        models = _normalize_items(all_items)
        if not models:
            return None
        _nho_efforts(models)
        default = next((x["id"] for x in models if x["is_default"]), models[0]["id"])
        return {
            "models": [x["id"] for x in models],
            "items": models,
            "default_model": default,
            "source": "codex-app-server",
        }
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    finally:
        if proc is not None:
            try:
                if proc.stdin:
                    proc.stdin.close()
            except Exception:
                pass
            try:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
