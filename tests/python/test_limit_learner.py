"""Học hạn mức token từ chính lỗi nhà cung cấp trả về.

    python tests/run.py limit_learner

Thiết kế cũ bắt người vận hành KHAI TRƯỚC hạn mức từng model rồi mới bảo vệ được, nghĩa là
chỉ đỡ được nhà cung cấp nào đã có người ngồi tra tài liệu và điền số. Nhưng chính câu báo
lỗi đã chứa sự thật chính xác nhất, do nhà cung cấp nói ra, đúng tài khoản đó, đúng lúc đó.

Rào quan trọng nhất: KHÔNG được nhận nhầm lỗi quá tải tạm thời thành lỗi vượt kích thước.
Nhận nhầm là co prompt vô ích trong khi vấn đề nằm ở phía nhà cung cấp.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-limit-"))

import limit_learner as ll  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- 1. Ca THẬT đã chặn Javis, chép nguyên văn từ ảnh chụp màn hình ----
_groq = ('{"error":{"message":"Request too large for model `llama-3.3-70b-versatile` in '
         'organization `org_01kykn91sqfk5s9nda9m3vpbsc` service tier `on_demand` on tokens '
         'per minute (TPM): Limit 12000, Requested 15447, please reduce your message size '
         'and try again."}}')
_f = ll.parse_limit_error(413, _groq)
check("Groq 413: nhận ra là lỗi vượt hạn mức", _f is not None)
check("Groq 413: rút đúng hạn mức 12000", _f and _f.limit == 12000)
check("Groq 413: rút đúng số đã xin 15447", _f and _f.requested == 15447)
check("Groq 413: phân loại đúng là TPM", _f and _f.kind == "tpm")

# ---- 1b. Dạng 429 "cửa sổ đã đầy" - lỗi chủ repo gặp SAU khi đã vá dạng 413 ----
# Khác hẳn dạng trên: lượt này chỉ xin 4701 (vừa hạn mức), nhưng các lượt TRƯỚC đã ăn 8812.
# Co nhỏ prompt gần như vô ích ở đây; việc đúng là CHỜ, và nhà cung cấp đã nói chờ bao lâu.
_groq429 = ('{"error":{"message":"Rate limit reached for model `llama-3.3-70b-versatile` in '
            'organization `org_01kykn91sqfk5s9nda9m3vpbsc` service tier `on_demand` on tokens '
            'per minute (TPM): Limit 12000, Used 8812, Requested 4701. Please try again in '
            '7.564999999s. Need more tokens? Upgrade to Dev Tier today"}}')
_f = ll.parse_limit_error(429, _groq429)
check("Groq 429: nhận ra (mẫu cũ đòi Requested ngay sau Limit nên trượt)", _f is not None)
check("Groq 429: rút đúng hạn mức", _f and _f.limit == 12000)
check("Groq 429: rút đúng phần ĐÃ dùng", _f and _f.used == 8812)
check("Groq 429: rút đúng phần vừa xin", _f and _f.requested == 4701)
check("Groq 429: biết đây là CỬA SỔ ĐẦY, không phải lượt này quá to",
      _f and _f.window_full is True)
check("Groq 429: đọc được số giây cần chờ", _f and abs(_f.retry_after - 7.565) < 0.01)

# Ngược lại: dạng 413 là lượt này quá to, KHÔNG phải cửa sổ đầy - phải co nhỏ chứ không chờ.
_f413 = ll.parse_limit_error(413, _groq)
check("Groq 413: KHÔNG bị nhầm thành cửa sổ đầy", _f413 and _f413.window_full is False)

# parse_retry_after
check("đọc 'try again in 7.5s'", abs(ll.parse_retry_after("try again in 7.5s") - 7.5) < 0.01)
check("đọc đơn vị ms", abs(ll.parse_retry_after("try again in 500ms") - 0.5) < 0.01)
check("đọc đơn vị phút", abs(ll.parse_retry_after("try again in 2m") - 120.0) < 0.01)
check("không nói thì trả 0", ll.parse_retry_after("some other error") == 0.0)
check("chờ quá lâu bị kẹp trần", ll.parse_retry_after("try again in 9999s") <= 300.0)

# ---- 2. Nhà cung cấp KHÁC, cùng một cơ chế ----
_f = ll.parse_limit_error(400, "This model's maximum context length is 8192 tokens, "
                               "however you requested 9000 tokens.")
check("OpenAI: rút đúng cửa sổ ngữ cảnh", _f and _f.limit == 8192 and _f.requested == 9000)
check("OpenAI: phân loại là context", _f and _f.kind == "context")

# Anthropic viết NGƯỢC thứ tự hai số. Đọc ngược là học đúng cái hạn mức sai.
_f = ll.parse_limit_error(400, "prompt is too long: 210000 tokens > 200000 maximum")
check("Anthropic: thứ tự ngược vẫn rút ĐÚNG hạn mức", _f and _f.limit == 200000)
check("Anthropic: và đúng số đã xin", _f and _f.requested == 210000)

_f = ll.parse_limit_error(400, "The input token count (12345) exceeds the maximum "
                               "number of tokens allowed (8192).")
check("Gemini: thứ tự ngược vẫn rút đúng", _f and _f.limit == 8192 and _f.requested == 12345)

# ---- 3. KHÔNG nhận nhầm lỗi khác thành lỗi kích thước ----
check("quá tải tạm thời KHÔNG phải lỗi kích thước",
      ll.parse_limit_error(503, "The model is overloaded, please try again later") is None)
check("rate limit theo SỐ REQUEST không phải lỗi kích thước",
      ll.parse_limit_error(429, "Too many requests, try again in 20s") is None)
check("lỗi xác thực không phải lỗi kích thước",
      ll.parse_limit_error(401, "Invalid API key provided") is None)
check("body rỗng → None", ll.parse_limit_error(400, "") is None)
check("body None → None", ll.parse_limit_error(400, None) is None)
check("chữ 'limit' trơ trọi không đủ để đoán số",
      ll.parse_limit_error(400, "You have reached your limit for today") is None)

# Lỗi kích thước mà không rút được số: vẫn phải nhận ra, vì tầng trên cần biết là "co prompt"
# chứ không phải "chờ rồi thử lại".
_f = ll.parse_limit_error(413, "Request too large. Please shorten your input.")
check("nhận ra lỗi kích thước dù không rút được số", _f is not None and _f.limit == 0)

# ---- 4. Nhớ và quên ----
ll.reset()
check("chưa học gì → None", ll.learned("groq", "llama-3.3") is None)
ll.remember("groq", "llama-3.3", ll.LimitFact("tpm", 12000, 15447, "groq_tpm"), now=1000.0)
check("nhớ được", (ll.learned("groq", "llama-3.3", now=1100.0) or None) is not None)
check("nhớ đúng số", ll.learned("groq", "llama-3.3", now=1100.0).limit == 12000)
check("provider không phân biệt hoa thường",
      ll.learned("GROQ", "llama-3.3", now=1100.0) is not None)
check("model khác thì chưa biết", ll.learned("groq", "model-khac", now=1100.0) is None)
check("quá hạn thì quên, không tự khoá vào số cũ",
      ll.learned("groq", "llama-3.3", now=1000.0 + ll.LEARNED_TTL_SECONDS + 1) is None)
ll.remember("groq", "x", ll.LimitFact("context", 0, 0, "unparsed_size_error"), now=1000.0)
check("fact không có số thì KHÔNG nhớ (đừng bịa hạn mức 0)",
      ll.learned("groq", "x", now=1000.0) is None)

check("snapshot nêu hạn mức đã học",
      ll.snapshot(now=1100.0).get("groq|llama-3.3", {}).get("limit") == 12000)

# ---- 5. Mục tiêu co lại phải THẤP hơn hạn mức ----
_t = ll.shrink_target(ll.LimitFact("tpm", 12000, 15447, "groq_tpm"))
check("mục tiêu co lại thấp hơn hạn mức", 0 < _t < 12000)
check("nhưng không co xuống mức vô dụng", _t > 3000)
check("không biết hạn mức thì trả 0, KHÔNG đoán bừa",
      ll.shrink_target(ll.LimitFact("context", 0, 0, "x")) == 0)
check("shrink_target(None) không nổ", ll.shrink_target(None) == 0)

# ---- 6. Co ngữ cảnh: giữ thứ không bỏ được, bỏ thứ bỏ được ----
import main  # noqa: E402

_msgs = [
    {"role": "system", "content": "PROMPT LÕI " * 500},
    {"role": "user", "content": "câu hỏi cũ 1"},
    {"role": "assistant", "content": "trả lời cũ 1"},
    {"role": "user", "content": "câu hỏi cũ 2"},
    {"role": "assistant", "content": "trả lời cũ 2"},
    {"role": "user", "content": "CÂU HỎI HIỆN TẠI"},
]
_out = main._shrink_messages(_msgs, 4000)
check("co lại: giữ prompt lõi", any(m["role"] == "system" for m in _out))
check("co lại: KHÔNG bao giờ bỏ câu hỏi hiện tại",
      _out[-1]["content"] == "CÂU HỎI HIỆN TẠI")
check("co lại: bỏ hết lịch sử cũ",
      not any("cũ" in str(m.get("content")) for m in _out))
check("co lại: nhỏ đi thật",
      sum(len(str(m["content"])) for m in _out) < sum(len(str(m["content"])) for m in _msgs))

# Không biết hạn mức vẫn phải co được, vì bỏ lịch sử luôn an toàn.
_out0 = main._shrink_messages(_msgs, 0)
check("không biết hạn mức: vẫn bỏ lịch sử", len(_out0) == 2)
check("không biết hạn mức: vẫn giữ câu hỏi",
      _out0[-1]["content"] == "CÂU HỎI HIỆN TẠI")

# Hạn mức siết tới mức prompt lõi cũng phải cắt.
_tiny = main._shrink_messages(_msgs, 400)
_sys = next(m for m in _tiny if m["role"] == "system")
check("hạn mức siết: cắt cả đuôi prompt lõi", "rút gọn" in _sys["content"])
check("hạn mức siết: vẫn giữ câu hỏi hiện tại",
      _tiny[-1]["content"] == "CÂU HỎI HIỆN TẠI")

check("danh sách rỗng không nổ", main._shrink_messages([], 100) == [])

# Câu báo khi co rồi vẫn vượt phải nêu SỐ THẬT, không nói chung chung.
_msg = main._limit_autoshrink_message("groq", "llama-3.3",
                                      {"limit": 12000, "requested": 15447, "kind": "tpm"})
check("báo lỗi cuối: nêu hạn mức thật", "12,000" in _msg)
check("báo lỗi cuối: nêu số đã cần", "15,447" in _msg)
check("báo lỗi cuối: nói rõ đã tự thử lại", "thử lại" in _msg)

# ---- 7. MỌI đường gọi provider đều phải học hạn mức ----
# Lỗi đã xảy ra thật: bản đầu chỉ vá các hàm stream thuần, trong khi đường Groq thật đi qua
# _cc_tool_loop (luôn có tool vì Javis có builtin tools). Code đúng, test xanh, và không bao
# giờ chạy. Rào này đối chiếu: chỗ nào phát "error" theo status_code thì phải có học hạn mức
# ngay trên đó.
import re as _re  # noqa: E402

_eng = (ROOT / "server" / "engine.py").read_text(encoding="utf-8")
_lines = _eng.split("\n")
_missing = []
for _i, _ln in enumerate(_lines):
    if "status_code != 200" not in _ln:
        continue
    # 12 dòng sau đó phải có parse_limit_error, nếu không là một đường bị bỏ sót.
    _win = "\n".join(_lines[_i:_i + 14])
    if '"type": "error"' in _win and "parse_limit_error" not in _win:
        _missing.append(_i + 1)

check("mọi chỗ báo lỗi HTTP đều học hạn mức, không sót đường nào", not _missing)
if _missing:
    print("     dòng thiếu:", _missing)
check("rào này có ý nghĩa (tìm được nhiều đường thật)",
      _eng.count("parse_limit_error") >= 4)

# ---- 8. Nhánh CHỜ khi cửa sổ hạn mức đã đầy ----
# _cc_tool_loop vốn KHÔNG có retry nào, nên 429 là chết luôn. Đây là lỗi chủ repo gặp sau khi
# đã vá dạng 413: request đã co xuống 4701 (vừa hạn mức) nhưng cửa sổ còn 8812 chưa trôi qua.
check("vòng gọi tool có nhánh chờ cửa sổ hạn mức", "waited_for_window" in _eng)
# Điều kiện phải BAO GỒM window_full: thiếu nó thì nhánh chờ hoặc không bao giờ chạy, hoặc
# chạy cả với lỗi "lượt này quá to" - chờ xong vẫn quá to, chỉ tốn thêm thời gian.
check("nhánh chờ gác đúng trên window_full",
      "_fact.window_full and _fact.retry_after" in _eng)
check("thật sự có ngủ chờ rồi thử lại",
      "await asyncio.sleep(_fact.retry_after" in _eng)
check("có trần thời gian chờ, không treo vô hạn",
      "_fact.retry_after <= _WINDOW_WAIT_MAX" in _eng)
check("chỉ chờ MỘT lần mỗi lượt, không chờ chồng",
      "not waited_for_window" in _eng)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_limit_learner: tất cả pass")
