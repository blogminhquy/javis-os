"""Sửa chữ NGHE NHẦM ngay khi đang nói, hiện lên bong bóng nháp (2026-11-06).

Hai lớp, chạy theo thứ tự:
  1. Luật (nghe_sua.sua): các ca đã biết (Jarvis -> Javis, Javis OS, Groq/Grok...). Không tốn gì,
     chạy tức thì, và luôn có mặt dù không có model nào.
  2. Model: đọc câu đã qua luật rồi sửa tiếp những từ nghe nhầm mà luật chưa biết, dựa vào
     bộ từ vựng. Chọn model theo thứ tự:
       - có khoá Groq thì dùng Groq (nhanh, rẻ, đã có ô nhập ở trang Models);
       - không có Groq thì dùng MODEL NỀN (việc nền, `model.auxiliary`), miễn là đó là một API
         có khoá (OpenAI, OpenRouter, Gemini, DeepSeek, Groq);
       - model nền là Claude Code, Codex hay CLI khác thì không gọi được một lượt nhỏ như vậy:
         chỉ dùng luật.

Luật an toàn của lớp model (sửa sai còn tệ hơn nghe sai):
  - Model chỉ được sửa, không được viết lại: số chữ không đổi quá một phần ba, không rỗng.
  - Lỗi mạng, hết giờ (3 giây), câu trả lời lạ: rơi về kết quả của luật, không báo lỗi lên màn.
  - Kết quả được nhớ tạm, cùng một câu không gọi model hai lần.
  - Nhật ký chỉ ghi SỐ ĐO (độ dài, nguồn), không ghi lời người dùng.
"""
from __future__ import annotations

import sys

import httpx

import aux_engine
import model_routing
import nghe_sua

TIMEOUT_S = 3.0
_CACHE_MAX = 200
_cache: dict = {}

# Địa chỉ chat/completions của từng API tương thích OpenAI (trùng engine.py).
_URL = {
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    "deepseek": "https://api.deepseek.com/chat/completions",
}
_MODEL_MAC_DINH = {
    "groq": "llama-3.3-70b-versatile",
    "openai": "gpt-4o-mini",
    "openrouter": "openai/gpt-4o-mini",
    "gemini": "gemini-2.5-flash",
    "deepseek": "deepseek-flash",
}

SYSTEM_PROMPT = (
    "Bạn sửa lỗi máy nghe giọng nói, câu thường là tiếng Việt xen tiếng Anh. Chỉ sửa những từ bị "
    "nghe thành từ gần âm nhưng sai, ưu tiên tên riêng và thuật ngữ trong danh sách được cho. Giữ "
    "nguyên mọi chữ khác: không thêm, không bớt, không viết lại câu, không giải thích, không đổi "
    "dấu câu. Nếu không chắc thì giữ nguyên. Chỉ trả về đúng câu đã sửa."
)


def _chon_model(cfg: dict):
    """(provider, api_key, model, url) của model dùng để sửa, hoặc None nếu chỉ dùng luật."""
    m = (cfg or {}).get("model") or {}
    if m.get("groq_api_key"):
        return ("groq", m["groq_api_key"], _MODEL_MAC_DINH["groq"], _URL["groq"])
    spec = model_routing.background_spec(m)
    p = spec.get("provider") or ""
    if p not in _URL:
        return None
    key = m.get(aux_engine._KEY_FIELD.get(p, "")) or ""
    if not key:
        return None
    return (p, key, spec.get("model") or _MODEL_MAC_DINH.get(p, ""), _URL[p])


def _an_toan(goc: str, sua: str) -> bool:
    """Kết quả model chỉ là SỬA: không rỗng, và số chữ không lệch quá một phần ba."""
    if not sua:
        return False
    n_goc = len(goc.split())
    n_sua = len(sua.split())
    return abs(n_sua - n_goc) <= max(1, n_goc // 3)


def _sach(t: str) -> str:
    t = (t or "").strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'“”":
        t = t[1:-1].strip()
    return " ".join(t.split())


async def _hoi_model(pick, cau: str, danh_sach: list) -> str:
    provider, key, model, url = pick
    user = "Danh sách tên và thuật ngữ đúng chính tả: " + ", ".join(danh_sach) + "\nCâu nghe được: " + cau
    body = {
        "model": model,
        "temperature": 0,
        "max_tokens": min(400, 3 * len(cau.split()) + 30),
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}],
    }
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        r = await client.post(url, json=body, headers={"Authorization": "Bearer " + key})
        r.raise_for_status()
        return _sach(r.json()["choices"][0]["message"]["content"])


async def sua_nhanh(cfg: dict, text) -> dict:
    """Trả {"text": câu đã sửa, "nguon": "luat" | <provider>, "ai": bool}.

    Không bao giờ ném lỗi: mọi trục trặc đều rơi về kết quả của luật.
    """
    goc = str(text or "").strip()
    if not goc:
        return {"text": "", "nguon": "luat", "ai": False}
    tv = nghe_sua.tu_vung(cfg or {})
    qua_luat = nghe_sua.sua(goc, tv)
    pick = _chon_model(cfg or {})
    if pick is None:
        return {"text": qua_luat, "nguon": "luat", "ai": False}
    khoa = (qua_luat, pick[0], pick[2])
    if khoa in _cache:
        return dict(_cache[khoa])
    try:
        sua = await _hoi_model(pick, qua_luat, tv)
    except Exception as e:  # mạng, hết giờ, khoá sai, JSON lạ: không làm vỡ bong bóng
        print(f"[nghe_sua] model {pick[0]} không sửa được: {type(e).__name__}", file=sys.stderr)
        return {"text": qua_luat, "nguon": "luat", "ai": False}
    if not _an_toan(qua_luat, sua):
        print(f"[nghe_sua] model {pick[0]} trả câu lạ, giữ kết quả luật ({len(qua_luat)} ký tự)", file=sys.stderr)
        return {"text": qua_luat, "nguon": "luat", "ai": False}
    ket_qua = {"text": sua, "nguon": pick[0], "ai": True}
    if len(_cache) >= _CACHE_MAX:
        _cache.clear()
    _cache[khoa] = ket_qua
    return dict(ket_qua)
