"""Bộ hạn mức gợi ý + endpoint khai quota profile.

    python tests/run.py model_limits

Rào QUAN TRỌNG NHẤT file này: mỗi mục trong `KNOWN_LIMITS` phải PARSE ĐƯỢC thành một
`QuotaRule` thật. `CanaryPolicy.from_settings` bỏ qua rule hỏng trong im lặng (continue),
nên gõ sai một tên trường sẽ cho ra `quota_profiles` có phần tử mà sinh 0 rule. Người vận
hành nhìn trang Chẩn đoán thấy "đã khai" rồi bật canary, và mọi task vẫn rơi về legacy mà
không ai hiểu vì sao. Test này biến lỗi câm đó thành CI đỏ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-limits-")

import config as cfg  # noqa: E402
import fast_path_runtime  # noqa: E402
import model_limits  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- 1. Mọi mục phải parse thành QuotaRule thật (rào chống lỗi câm) ----
check("KNOWN_LIMITS không rỗng", len(model_limits.KNOWN_LIMITS) > 0)

for _item in model_limits.KNOWN_LIMITS:
    _profile = model_limits.as_quota_profile(_item)
    _policy = fast_path_runtime.CanaryPolicy.from_settings({
        "context_runtime": {"mode": "canary",
                            "canary": {"allocation_basis_points": 100,
                                       "quota_profiles": [_profile]}}})
    _rid = _item["id"]
    check(f"'{_rid}' parse ra ĐÚNG 1 QuotaRule (không bị bỏ qua im lặng)",
          len(_policy.rules) == 1)
    if _policy.rules:
        _r = _policy.rules[0]
        check(f"'{_rid}' giữ nguyên rolling_tpm", _r.rolling_tpm == _item["rolling_tpm"])
        check(f"'{_rid}' suy ra hard_max_input_tokens > 0", _r.hard_max_input_tokens > 0)
        check(f"'{_rid}' chừa chỗ cho câu trả lời", _r.reserved_output_tokens > 0)
        check(f"'{_rid}' hard_max_input nhỏ hơn cửa sổ ngữ cảnh",
              _r.hard_max_input_tokens < _item["context_window"])

# ---- 2. as_quota_profile chỉ giữ trường cấu hình, bỏ ghi chú cho người ----
_p = model_limits.as_quota_profile(model_limits.KNOWN_LIMITS[0])
check("as_quota_profile bỏ note/source/verify khỏi cấu hình",
      not ({"note", "source", "verify"} & set(_p)))
check("as_quota_profile giữ đủ trường bắt buộc",
      {"provider", "model_pattern", "rolling_tpm", "context_window",
       "reserved_output_tokens"} <= set(_p))

# ---- 3. suggest_profiles ----
check("suggest_profiles: groq có gợi ý", len(model_limits.suggest_profiles("groq")) > 0)
check("suggest_profiles: lọc đúng theo model",
      all("llama" in s["model_pattern"]
          for s in model_limits.suggest_profiles("groq", "llama-3.3-70b-versatile")))
check("suggest_profiles: provider chưa tra → RỖNG, không bịa",
      model_limits.suggest_profiles("provider-la-hoac") == [])
check("suggest_profiles: provider rỗng → rỗng", model_limits.suggest_profiles("") == [])
check("suggest_profiles: không phân biệt hoa thường", len(model_limits.suggest_profiles("GROQ")) > 0)
check("known_providers nêu groq", "groq" in model_limits.known_providers())

# Mọi mục đều phải tự nhận là con số CẦN ĐỐI CHIẾU. Trình bày hạn mức gợi ý như thể đã biết
# chắc là cách nhanh nhất để admission cho qua đúng request lẽ ra phải chặn.
check("mọi mục đều mang cờ verify",
      all(i.get("verify") is True for i in model_limits.KNOWN_LIMITS))
check("mọi mục đều ghi nguồn tra",
      all(str(i.get("source") or "").strip() for i in model_limits.KNOWN_LIMITS))

# ---- 4. Endpoint khai quota ----
import main  # noqa: E402


async def _endpoint_tests():
    r = await main.runtime_quota_apply(provider="provider-la-hoac", model="", paths="")
    check("endpoint: provider chưa biết → 404, không bịa số",
          getattr(r, "status_code", 0) == 404)

    r = await main.runtime_quota_apply(provider="groq", model="", paths="khong_co_that")
    check("endpoint: đường canary sai tên → 400", getattr(r, "status_code", 0) == 400)

    r = await main.runtime_quota_apply(provider="groq", model="", paths="canary")
    check("endpoint: áp cho một đường → ok", isinstance(r, dict) and r.get("ok"))
    check("endpoint: chỉ áp đúng đường được nêu", r.get("da_ap_cho") == ["canary"])
    check("endpoint: có nhắc phải đối chiếu gói cước thật",
          bool(r.get("can_doi_chieu")) and "GỢI Ý" in r.get("luu_y", ""))

    _saved = cfg.read_settings()["context_runtime"]["canary"]["quota_profiles"]
    check("endpoint: quota đã vào settings thật", len(_saved) > 0)
    check("endpoint: đường KHÁC không bị đụng",
          cfg.read_settings()["context_runtime"]["readonly_canary"]["quota_profiles"] == [])

    # Và điều thật sự quan trọng: khai xong thì bật canary KHÔNG còn bị chặn nữa.
    _entry = cfg.read_settings()["context_runtime"]["canary"]
    _st, _pl = main.canary_set_decision("canary", 100, _entry, False)
    check("khai quota xong thì bật canary không còn bị chặn", _st == 0)

    # Áp cho mọi đường
    r = await main.runtime_quota_apply(provider="groq", model="", paths="")
    check("endpoint: paths rỗng → áp cho nhiều đường", len(r.get("da_ap_cho") or []) > 1)
    check("endpoint: KHÔNG áp cho đường dùng 'models' thay vì 'quota_profiles'",
          "model_router_canary" not in (r.get("da_ap_cho") or []))


asyncio.run(_endpoint_tests())

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_model_limits: tất cả pass")
