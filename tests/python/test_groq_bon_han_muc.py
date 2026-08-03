"""Groq siết BỐN chiều cùng lúc, và Javis từng gộp cả bốn vào một rọ.

    python tests/run.py groq_bon_han_muc

Câu chủ repo nhìn thấy trên màn hình (0.12.4):

    "groq báo request quá lớn. Javis đã tự rút gọn ngữ cảnh và thử lại một lần nhưng vẫn
     không vừa. Lượt này cần khoảng 0 token, trong khi groq giới hạn 12,000 token mỗi phút."

Ba thứ sai trong đúng một câu đó:

  1. "request quá lớn" - chưa chắc. Gói Groq siết token/phút, LƯỢT/phút, token/NGÀY và
     LƯỢT/ngày; cả bốn đều mở đầu bằng "Rate limit reached". Bản trước lấy đúng cụm đó làm
     dấu hiệu "vượt kích thước", nên ba chiều kia bị gán nhãn sai.
  2. "cần khoảng 0 token" - số 0 là vì không đọc được gì từ câu lỗi.
  3. "12,000 token mỗi phút" - con số này KHÔNG đến từ Groq. Nó lấy từ bảng tra sẵn trong
     model_limits. Ghép một số đọc-không-ra với một số tra-bảng thành câu nghe như đã hiểu
     chuyện là kiểu hỏng tệ nhất: vừa sai, vừa che mất bằng chứng để lần ra cái sai.

Và hệ quả dây chuyền: đọc không ra số thì shrink_to = 0; shrink_to = 0 thì _shrink_messages
chỉ bỏ lịch sử rồi trả về, KHÔNG đụng system prompt - đúng chỗ phình. Nên "đã tự rút gọn"
thực ra gần như không rút gì.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-groq4-")

import adaptive_context_runtime as acr  # noqa: E402
import config as cfg  # noqa: E402
import limit_learner as ll  # noqa: E402
import main  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# Nguyên văn bốn khuôn Groq trả về. Chỉ khác nhau đúng cụm chiều siết.
def _groq(chieu, limit, used, requested, cho="Please try again in 2s."):
    return (f"Rate limit reached for model `llama-3.3-70b-versatile` in organization "
            f"`org_01` service tier `on_demand` on {chieu}: Limit {limit}, Used {used}, "
            f"Requested {requested}. {cho}")


# ============================================================
# 1. Bốn chiều phải ra bốn kết luận khác nhau
# ============================================================
CA = [
    # (tên, body, kind mong đợi, việc cần làm mong đợi)
    ("token mỗi phút, lượt này quá to",
     "Request too large for model `llama-3.3-70b-versatile` in organization `org_01` service "
     "tier `on_demand` on tokens per minute (TPM): Limit 12000, Requested 21446, please "
     "reduce your message size and try again.", "tpm", "shrink"),
    ("token mỗi phút, cửa sổ đã đầy",
     _groq("tokens per minute (TPM)", 12000, 8812, 4701, "Please try again in 7.5s."),
     "tpm", "wait"),
    ("SỐ LƯỢT mỗi phút", _groq("requests per minute (RPM)", 30, 30, 1), "rpm", "wait"),
    ("token mỗi NGÀY", _groq("tokens per day (TPD)", 100000, 100000, 3200,
                             "Please try again in 6h12m."), "tpd", "wait_long"),
    ("SỐ LƯỢT mỗi ngày", _groq("requests per day (RPD)", 14400, 14400, 1,
                               "Please try again in 3h."), "rpd", "wait_long"),
]
for ten, body, kind, viec in CA:
    f = ll.parse_limit_error(429, body)
    check(f"[{ten}] nhận ra được", f is not None)
    check(f"[{ten}] phân loại là '{kind}'", f is not None and f.kind == kind)
    check(f"[{ten}] việc cần làm là '{viec}'", f is not None and f.remedy == viec)

# ĐÂY là bản vá cốt lõi: ba chiều không phải token-mỗi-phút KHÔNG được gọi là lỗi kích thước.
for ten, body, kind, _viec in CA[2:]:
    f = ll.parse_limit_error(429, body)
    check(f"CANARY: [{ten}] KHÔNG bị gán nhãn lỗi kích thước",
          f is not None and f.kind != "context" and f.source != "unparsed_size_error")

# ============================================================
# 2. Hạn mức đếm LƯỢT tuyệt đối không được thành ngân sách token
# ============================================================
# "Limit 30" của lượt-mỗi-phút mà đem nhân 0,75 thì thành "co ngữ cảnh xuống 22 token".
_rpm = ll.parse_limit_error(429, _groq("requests per minute (RPM)", 30, 30, 1))
check("CANARY: hạn mức 30 LƯỢT/phút không sinh ra mục tiêu co 22 token",
      ll.shrink_target(_rpm) == 0)
check("và không dùng được làm ngân sách", not _rpm.usable_as_budget)

# Hạn mức theo NGÀY đếm token thật, nhưng cũng không phải trần cho MỘT request.
_tpd = ll.parse_limit_error(429, _groq("tokens per day (TPD)", 100000, 100000, 3200))
check("hạn mức 100k token/NGÀY vẫn được ghi nhận là đếm token", _tpd.counts_tokens)
check("CANARY: nhưng KHÔNG dùng làm trần cho một request",
      not _tpd.usable_as_budget and ll.shrink_target(_tpd) == 0)

# ============================================================
# 3. Câu nói cho người dùng phải khớp việc cần làm
# ============================================================
def _noi(body):
    f = ll.parse_limit_error(429, body)
    hit = {"limit": f.limit, "requested": f.requested, "used": f.used, "kind": f.kind,
           "remedy": f.remedy, "retry_after": f.retry_after, "raw": f.raw} if f else {}
    return main._limit_autoshrink_message("groq", "llama-3.3-70b-versatile", hit)


_m = _noi(_groq("tokens per day (TPD)", 100000, 100000, 3200, "Please try again in 6h12m."))
check("[ngày] nói rõ là hạn mức theo NGÀY", "NGÀY" in _m)
# Đây là chỗ bản trước chỉ sai đường cho người đang bí.
check("CANARY: [ngày] nói THẲNG rút gọn không giúp gì", "không giúp gì" in _m)
check("[ngày] chỉ ra lối ra có thật", "sang ngày" in _m and "Models" in _m)
check("[ngày] KHÔNG bảo Javis đã tự rút gọn", "đã tự rút gọn" not in _m)

_m = _noi(_groq("requests per minute (RPM)", 30, 30, 1))
check("[lượt/phút] nói đúng đơn vị là số lượt", "số lượt mỗi phút" in _m)
check("[lượt/phút] bảo chờ chứ không bảo rút gọn",
      "hỏi lại" in _m and "Rút gọn câu hỏi không giúp" in _m)

_m = _noi("Request too large for model `x` on tokens per minute (TPM): Limit 12000, "
          "Requested 21446, please reduce your message size and try again.")
check("[lượt quá to] vẫn giữ đường cũ: đã rút gọn rồi báo", "đã tự rút gọn" in _m)
check("[lượt quá to] nêu ĐÚNG số Groq nói, không phải số tra bảng",
      "12,000" in _m and "21,446" in _m)

# ============================================================
# 4. Không hiểu thì phải đưa nguyên văn, KHÔNG bịa một câu cho tròn
# ============================================================
_m = _noi("Rate limit reached. Please try again in 12s.")
check("[không rõ chiều] có nguyên văn lời Groq", "Rate limit reached" in _m)
check("[không rõ chiều] vẫn nói được việc cần làm (chờ 12 giây)", "12 giây" in _m)
# Ba dấu vết của câu sai cũ. Còn cái nào là còn đúng lỗi đó.
for _xau in ("0 token", "request quá lớn"):
    check(f"CANARY: không còn câu bịa '{_xau}'", _xau not in _m.casefold())

_m = main._limit_autoshrink_message("groq", "m", {"limit": 0, "remedy": "unknown",
                                                  "raw": "Some brand new error text"})
check("[hoàn toàn lạ] thú nhận là chưa biết phải làm gì", "chưa biết" in _m)
check("[hoàn toàn lạ] và vẫn đưa nguyên văn ra", "Some brand new error text" in _m)
check("KHÔNG dùng em dash", "—" not in _m)

# ============================================================
# 5. Không thử lại khi thử lại chắc chắn vô ích
# ============================================================
_src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
_i = _src.find("if not _limit_hit or _attempt == 2:")
# Cắt tới HẾT vòng thử lại (dòng gọi _shrink_messages), không đếm ký tự bừa: đếm ký tự
# thì thêm vài dòng là cửa sổ trượt khỏi chỗ cần soi và assertion đỏ vì lý do vô can.
_khoi = _src[_i:_src.find("or_messages = _shrink_messages(or_messages, _target)", _i) + 60]
check("cắt được đúng vòng thử lại", 0 < len(_khoi) < 4000)
check("CANARY: chỉ thử lại khi việc cần làm là co nhỏ hoặc chờ",
      'if str(_limit_hit.get("remedy") or "") not in ("shrink", "wait"):' in _khoi
      and _khoi.count("break") >= 3)
# Đọc không ra hạn mức lần này thì lấy con số đã HỌC từ lần trước. Đây chính là chỗ trước
# đây bỏ trống: target 0 làm _shrink_messages chỉ bỏ lịch sử, không đụng system prompt.
check("CANARY: không đọc ra số thì dùng hạn mức đã học",
      "limit_learner.learned_token_limit(prov, actual_model)" in _khoi)
check("và không có số nào thì THÔI, không gửi lại y nguyên",
      "if _target <= 0:\n                                break" in _khoi)
check("thông báo nói rõ co xuống bao nhiêu", "rồi thử lại" in _khoi and "{_target:,}" in _khoi)

# ============================================================
# 6. Bộ định tuyến tự dùng hạn mức đã học, khỏi chờ ai khai
# ============================================================
# Thứ tự cũ bị ngược: fail-closed đòi khai quota trước, nên đúng lúc bị siết lại là đúng lúc
# phần tiết kiệm ngữ cảnh không chạy. Sau MỘT lần bị từ chối là đã đủ biết.
_st = {"context_runtime": cfg._DEFAULT["context_runtime"]}
ll.reset()
check("chưa gặp lỗi lần nào → chưa có ngân sách (không đoán bừa)",
      acr.AdaptiveContextCanary._learned_quota(_st, "groq", "llama-3.3-70b-versatile") is None)

ll.remember("groq", "llama-3.3-70b-versatile", ll.parse_limit_error(
    413, "Request too large for model `x` on tokens per minute (TPM): Limit 12000, "
         "Requested 21446"))
_q = acr.AdaptiveContextCanary._learned_quota(_st, "groq", "llama-3.3-70b-versatile")
check("CANARY: sau MỘT lần bị từ chối là có ngân sách", isinstance(_q, dict))
check("ngân sách thấp hơn hạn mức thật (chừa biên cửa sổ trượt)",
      _q and 0 < _q["hard_input"] < 12000)
check("có chừa chỗ cho câu trả lời", _q and _q["reserved"] > 0)
check("ghi rõ nguồn là học được, không giả làm khai tay",
      _q and _q["id"].startswith("learned:"))

# Hạn mức đếm LƯỢT không được lọt vào đây.
ll.reset()
ll.remember("groq", "m2", ll.parse_limit_error(429, _groq("requests per minute (RPM)", 30, 30, 1)))
check("CANARY: hạn mức đếm LƯỢT không thành ngân sách token",
      acr.AdaptiveContextCanary._learned_quota(_st, "groq", "m2") is None)
ll.reset()
ll.remember("groq", "m3", ll.parse_limit_error(429, _groq("tokens per day (TPD)", 100000, 100000, 3200)))
check("CANARY: hạn mức theo NGÀY không thành trần một request",
      acr.AdaptiveContextCanary._learned_quota(_st, "groq", "m3") is None)

# Tắt được bằng cấu hình, và khai hỏng thì trả None chứ không nổ giữa lượt chat.
ll.reset()
ll.remember("groq", "m4", ll.parse_limit_error(
    413, "Request too large on tokens per minute (TPM): Limit 12000, Requested 21446"))
_tat = {"context_runtime": {"learned_quota": {"enabled": False}}}
check("người vận hành tắt được", acr.AdaptiveContextCanary._learned_quota(_tat, "groq", "m4") is None)
for _hong in ({}, {"context_runtime": {"learned_quota": {"safety_factor": "abc"}}},
              {"context_runtime": {"learned_quota": {"reserved_output_tokens": 999999}}}):
    _r = acr.AdaptiveContextCanary._learned_quota(_hong, "groq", "m4")
    check(f"khai hỏng {str(_hong)[:44]} không nổ", _r is None or isinstance(_r, dict))

# NỐI VÀO ĐƯỜNG THẬT. Kiểm hàm chạy đúng là chưa đủ - đúng họ lỗi "code đúng, test xanh, mà
# không ai gọi" đã lặp lại nhiều lần trong nhánh này. Phải soi chính chỗ dựng ngân sách.
_src_acr = (ROOT / "server" / "adaptive_context_runtime.py").read_text(encoding="utf-8")
check("CANARY: _prepare THẬT SỰ gọi tới ngân sách học được",
      "quota = self._learned_quota(settings, provider, model)" in _src_acr)

# Và sự kiện lỗi phải MANG THEO việc-cần-làm + nguyên văn qua tới tầng trên. Thiếu hai trường
# này thì main.py không thể nói thật khi nó không hiểu lỗi, dù limit_learner đã hiểu.
_src_eng = (ROOT / "server" / "engine.py").read_text(encoding="utf-8")
check("CANARY: mọi chỗ báo vượt hạn mức đều mang theo remedy + nguyên văn",
      _src_eng.count('"shrink_to": limit_learner.shrink_target(_fact),')
      == _src_eng.count('"remedy": _fact.remedy, "raw": _fact.raw}')
      and _src_eng.count('"remedy": _fact.remedy, "raw": _fact.raw}') >= 5)

# Khai tay phải THẮNG hạn mức học được: đó là chủ đích rõ ràng của người vận hành.
_i = _src_acr.find("quota = self._quota(settings, provider, model)")
_thu_tu = _src_acr[_i:_i + 400]
check("CANARY: khai tay xét TRƯỚC hạn mức học được",
      _thu_tu.find("self._quota(") < _thu_tu.find("self._learned_quota("))
check("và hạn mức học được xét trước trần gói thuê bao",
      _thu_tu.find("self._learned_quota(") < _thu_tu.find("self._subscription_quota("))

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_groq_bon_han_muc: tất cả pass")
