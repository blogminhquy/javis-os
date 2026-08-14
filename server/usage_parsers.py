"""
usage_parsers.py - Ham parse THUAN cho dashboard token. Khong phu thuoc config/DB,
chi nhan dict/path -> tra ve UsageEvent (dict) da chuan hoa. De unit-test doc lap.

UsageEvent = {
  ts:int(epoch), day:'YYYY-MM-DD'(gio dia phuong UTC+7), provider:'claude'|'codex'|'api',
  engine:str, model:str, project:str, session_id:str,
  source:'javis'|'manual', activity:'chat'|'background'|'subagent'|'manual',
  input:int, output:int, cache_read:int, cache_create:int, turns:int,
}
billable_in = input + cache_read + cache_create.

`turns` = SO LAN GOI MODEL ma su kien nay gom lai. Voi Claude moi dong assistant la mot lan
goi nen turns=1; voi Codex mot file rollout gom ca phien nen turns = so ban ghi token_count.
Day KHONG phai "so cau nguoi dung hoi" (mot cau co goi tool sinh ra nhieu lan goi) - no la
mau so dung de tinh "token moi luot", tuc dung thu ma phan tiet kiem ngu canh tac dong vao.
"""
from __future__ import annotations

import localefmt
import json
import os
from datetime import datetime, timezone, timedelta

# Múi giờ để cắt NGÀY của thống kê. Đọc từ cấu hình qua `localefmt`, KHÔNG còn là hằng số.
#
# Đổi múi giờ là DỊCH RANH GIỚI NGÀY, nên phải nói rõ hợp đồng: dữ liệu đã ghi giữ nguyên
# chuỗi ngày của nó, chỉ dữ liệu MỚI mới theo múi giờ mới. Không viết lại lịch sử - một bản
# ghi "2026-08-14" được tạo ra dưới UTC+7 vẫn là ngày đó, kể cả sau khi người dùng chuyển
# sang UTC+9. Đổi lại, ngay lúc chuyển sẽ có một chỗ gợn trong chuỗi ngày; đó là hệ quả không
# tránh được của việc đổi múi giờ, và viết lại lịch sử để làm nó phẳng còn tệ hơn nhiều.
#
# Là HÀM chứ không phải hằng: người dùng đổi múi giờ ở trang Cài đặt là ăn ngay, không phải
# khởi động lại server.
def _tz():
    return localefmt.tz()


_PRICING_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "usage_pricing.json")


def load_prices(path: str = None) -> dict:
    """Doc bang gia usage_pricing.json -> dict {tien_to_model: {in,out,cache_read,cache_write}}.
    Loi/thieu file -> {} (chi phi se = 0, khong chan)."""
    try:
        with open(path or _PRICING_PATH, "r", encoding="utf-8") as fh:
            return (json.load(fh) or {}).get("prices", {}) or {}
    except Exception:
        return {}


# Nho dem model -> khoa bang gia khop dai nhat. Mot o duy nhat, reset khi doi bang gia.
# Vi sao: usage_index._group goi estimate_cost MOI DONG, moi lan lai quet tuyen tinh ca
# bang gia. Do thuc te tren 1825 dong: 26.748 lan goi, 160.491 lan startswith, chiem 65%
# thoi gian cua summary() - trong khi db chi co 11 model phan biet va bang gia co 6 khoa.
# Giu THAM CHIEU MANH toi prices de id() khong bi tai dung cho dict khac.
_KHOA_GIA_MEMO = {"prices": None, "map": {}}


def _khoa_gia(model: str, prices: dict) -> str:
    """Khoa bang gia co tien to DAI NHAT khop model ('' neu khong khop). Ket qua nho dem.

    Thu HAI dang ten: nguyen van ('claude-opus-5'), va phan sau dau '/' ('anthropic/claude-
    opus-4' -> 'claude-opus-4'). OpenRouter luon dat ten kieu '<hang>/<model>', nen neu chi
    khop tien to nguyen van thi MOI model OpenRouter deu khong khop bang gia va ra chi phi 0
    - dung nhanh duy nhat ma nguoi dung tra tien MAT that.
    """
    if _KHOA_GIA_MEMO["prices"] is not prices:
        _KHOA_GIA_MEMO["prices"] = prices
        _KHOA_GIA_MEMO["map"] = {}
    memo = _KHOA_GIA_MEMO["map"]
    if model in memo:
        return memo[model]
    # Model FREE cua OpenRouter co hau to ':free' va gia bang 0. Khong loai no ra thi
    # 'deepseek/deepseek-r1:free' khop khoa 'deepseek-r1' roi bi tinh 0,55$ moi trieu token -
    # tien BIA hoan toan, va no chay thang vao o "tien mat thang nay" va vao phanh ngan sach.
    # Nghia la Javis co the tu phanh viec nen vi mot hoa don khong ton tai.
    if ":free" in str(model or ""):
        memo[model] = ""
        return ""
    ung_vien = [model]
    if "/" in str(model or ""):
        ung_vien.append(str(model).rsplit("/", 1)[-1])
    # Xet CA HAI dang roi lay khoa DAI NHAT, khong dung lai o dang dau tien co khop. Neu dung
    # lai som thi 'deepseek/deepseek-r1' an khoa 'deepseek' (ten hang khop tien to nguyen van)
    # va khong bao gio thu toi 'deepseek-r1' - tra ve gia cua model re hon.
    best_key = ""
    for ten in ung_vien:
        for key in prices:
            if ten.startswith(key) and len(key) > len(best_key):
                best_key = key
    memo[model] = best_key
    return best_key


def estimate_cost(ev: dict, prices: dict) -> float:
    """Chi phi quy doi USD cho 1 UsageEvent theo bang gia (USD/1M token).
    Khop model theo tien to DAI NHAT; khong khop -> 0."""
    model = ev.get("model") or ""
    best_key = _khoa_gia(model, prices)
    if not best_key:
        return 0.0
    p = prices[best_key]
    cost = (int(ev.get("input") or 0) * float(p.get("in") or 0)
            + int(ev.get("output") or 0) * float(p.get("out") or 0)
            + int(ev.get("cache_read") or 0) * float(p.get("cache_read") or 0)
            + int(ev.get("cache_create") or 0) * float(p.get("cache_write") or 0))
    return cost / 1_000_000.0


def _parse_ts(s: str):
    """ISO (co the hau to Z) -> (epoch:int, day-local:str). None neu khong parse duoc."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp()), dt.astimezone(_tz()).strftime("%Y-%m-%d")
    except Exception:
        return None


def _basename(path: str) -> str:
    if not path:
        return "(unknown)"
    p = str(path).replace("\\", "/").rstrip("/")
    return p.rsplit("/", 1)[-1] or "(unknown)"


def parse_claude_line(obj: dict, chat_sessions: set, session_brains: dict = None) -> dict | None:
    """Mot dong JSONL da json.loads cua Claude Code -> UsageEvent hoac None.

    Bo qua: khong phai type=assistant, model synthetic/thieu, khong co usage, tong token = 0.

    session_brains: {session_id: duong_dan_brain} tu session_brain.py. Moi engine Javis chay
    voi cwd = goc project nen 'project' suy tu cwd gop het ve mot cho ('Javis-OS' / 'app');
    phien nao tra duoc brain thi lay TEN BRAIN lam nhan dung hon. Khong tra duoc -> cwd nhu cu.
    """
    if not isinstance(obj, dict) or obj.get("type") != "assistant":
        return None
    msg = obj.get("message") or {}
    model = msg.get("model")
    if not model or model == "<synthetic>":
        return None
    usage = msg.get("usage")
    if not isinstance(usage, dict):
        return None
    inp = int(usage.get("input_tokens") or 0)
    out = int(usage.get("output_tokens") or 0)
    cread = int(usage.get("cache_read_input_tokens") or 0)
    ccreate = int(usage.get("cache_creation_input_tokens") or 0)
    if inp + out + cread + ccreate <= 0:
        return None

    entrypoint = obj.get("entrypoint") or ""
    source = "javis" if entrypoint.startswith("sdk") else "manual"
    session_id = obj.get("sessionId") or ""

    if obj.get("isSidechain"):
        activity = "subagent"
    elif source == "manual":
        activity = "manual"
    elif session_id in chat_sessions:
        activity = "chat"
    else:
        activity = "background"

    parsed = _parse_ts(obj.get("timestamp"))
    ts, day = parsed if parsed else (0, "")

    brain = (session_brains or {}).get(session_id)
    project = _basename(brain) if brain else _basename(obj.get("cwd") or "")

    return {
        "ts": ts, "day": day, "provider": "claude",
        "engine": entrypoint or "claude", "model": model,
        "project": project, "session_id": session_id,
        "source": source, "activity": activity,
        "input": inp, "output": out, "cache_read": cread, "cache_create": ccreate,
        "turns": 1,
    }


def parse_codex_file(path: str) -> dict | None:
    """Mot file rollout Codex (~/.codex/sessions/**/rollout-*.jsonl) -> mot UsageEvent
    la TONG CA PHIEN, hoac None neu khong tim thay token_count.

    total_token_usage la CONG DON theo phien: lay ban ghi co total_tokens LON NHAT
    (= trang thai cuoi) lam tong. input_tokens da GOM cached, nen input moi = input - cached.
    Codex la engine phu: source='javis', activity='chat' (best-effort, chua tach nen).

    `turns` = so ban ghi token_count trong file. Moi lan Codex goi model xong no ghi mot ban
    ghi nhu vay, nen day la so lan goi that cua ca phien. Truoc day ham nay chi tra ve tong
    token, nen mot phien Codex 200 luot va mot phien 2 luot deu duoc dem la MOT - va "token
    moi luot" cua Codex sai ca tram lan.
    """
    cwd = ""
    model = "codex"
    turns = 0
    best = None            # (total_tokens, info_dict, ts_line)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if not isinstance(obj, dict):
                    continue
                payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
                if obj.get("type") == "session_meta":
                    cwd = payload.get("cwd") or cwd
                m = obj.get("model") or payload.get("model")
                if m:
                    model = m
                if payload.get("type") == "token_count":
                    info = payload.get("info") or {}
                    ttu = info.get("total_token_usage") or {}
                    tot = int(ttu.get("total_tokens") or 0)
                    if ttu:
                        turns += 1
                        if best is None or tot >= best[0]:
                            best = (tot, ttu, obj.get("timestamp"))
    except Exception:
        return None
    if best is None:
        return None
    _, ttu, ts_line = best
    inp_all = int(ttu.get("input_tokens") or 0)
    cread = int(ttu.get("cached_input_tokens") or 0)
    out = int(ttu.get("output_tokens") or 0)
    inp = max(0, inp_all - cread)
    if inp + out + cread <= 0:
        return None
    parsed = _parse_ts(ts_line)
    ts, day = parsed if parsed else (0, "")
    session_id = _basename(path).rsplit(".", 1)[0]
    return {
        "ts": ts, "day": day, "provider": "codex",
        "engine": "codex", "model": model,
        "project": _basename(cwd), "session_id": session_id,
        "source": "javis", "activity": "chat",
        "input": inp, "output": out, "cache_read": cread, "cache_create": 0,
        "turns": max(1, turns),
    }
