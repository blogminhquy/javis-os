"""Tầng truy xuất hybrid: RRF fusion, nới rộng động, affinity nguồn.

    python tests/run.py capability_index

Trước module này, resolver chọn capability CHỈ bằng lexical. Móc embedding có sẵn nhưng chỉ
để quan sát - kết quả ghi vào report rồi bỏ đó, không tham gia xếp hạng.

Bất biến AN TOÀN quan trọng nhất: tầng này chỉ đổi THỨ TỰ và ĐỀ XUẤT THÊM ứng viên. Ứng viên
do widening thêm vào vẫn phải đi qua `_hard_filter`, vì lọc chạy sau khi hợp nhất. Không có
đường nào ở đây nới quyền. Có test riêng khoá chuyện đó.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-capidx-")

import capability_index as ci  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- 1. RRF fusion ----
check("rrf: danh sách rỗng → rỗng", ci.rrf_fuse([]) == {})
_f = ci.rrf_fuse([["a", "b", "c"]])
check("rrf: hạng 1 điểm cao hơn hạng 2", _f["a"] > _f["b"] > _f["c"])

# Điểm mấu chốt: thứ mà CẢ HAI danh sách đồng ý phải nổi lên, kể cả khi nó không đứng đầu
# ở danh sách nào. Đây là lý do dùng RRF thay vì cộng điểm có trọng số.
_f = ci.rrf_fuse([["a", "b"], ["b", "a"]])
check("rrf: hai bên đồng ý thì điểm gần nhau", abs(_f["a"] - _f["b"]) < 1e-9)
_f = ci.rrf_fuse([["x", "b", "a"], ["y", "b", "a"]])
check("rrf: mục cả hai cùng xếp cao thắng mục chỉ một bên xếp nhất",
      _f["b"] > _f["x"] and _f["b"] > _f["y"])

check("rrf: trọng số 0 thì danh sách đó bị bỏ qua",
      ci.rrf_fuse([["a"], ["b"]], weights=[1.0, 0.0]) == ci.rrf_fuse([["a"]]))
check("rrf: k lớn làm phẳng chênh lệch",
      (ci.rrf_fuse([["a", "b"]], k=1000)["a"] - ci.rrf_fuse([["a", "b"]], k=1000)["b"])
      < (ci.rrf_fuse([["a", "b"]], k=1)["a"] - ci.rrf_fuse([["a", "b"]], k=1)["b"]))

# ---- 2. Nới rộng theo tín hiệu YẾU, không theo ngưỡng số lượng ----
check("không có ứng viên → nới", ci.needs_widening([], 0.18, 0.10) == "no_candidate")
check("ứng viên tốt nhất vẫn yếu → nới",
      ci.needs_widening([{"score": 0.10}], 0.18, 0.10) == "weak_top_score")
check("hai ứng viên đầu sát nhau (mơ hồ) → nới",
      ci.needs_widening([{"score": 0.80}, {"score": 0.78}], 0.18, 0.10) == "ambiguous_top")
check("kết quả rõ ràng → KHÔNG nới",
      ci.needs_widening([{"score": 0.80}, {"score": 0.40}], 0.18, 0.10) == "")
check("một ứng viên mạnh duy nhất → KHÔNG nới",
      ci.needs_widening([{"score": 0.90}], 0.18, 0.10) == "")

# ---- 3. Affinity nguồn: nhẹ và có trần ----
_ranked = [{"capability_id": "a", "source_id": "pos"},
           {"capability_id": "b", "source_id": "pos"},
           {"capability_id": "c", "source_id": "ads"}]
_aff = ci.source_affinity(_ranked, boost=0.03, top_n=1)
check("affinity: cùng nguồn với kết quả mạnh được cộng", _aff.get("b") == 0.03)
check("affinity: nguồn khác không được cộng", "c" not in _aff)
check("affinity: rỗng thì trả rỗng", ci.source_affinity([]) == {})

# ---- 4. apply_fusion chỉ ĐỔI THỨ TỰ, không thêm không bớt ----
_ranked = [{"capability_id": "a", "name": "A", "score": 0.50, "source_id": "s1"},
           {"capability_id": "b", "name": "B", "score": 0.48, "source_id": "s2"}]
_out = ci.apply_fusion(_ranked, semantic_ids=["b", "a"])
check("fusion: không thêm không bớt mục nào", len(_out) == len(_ranked))
check("fusion: giữ nguyên các trường gốc",
      all("name" in x and "score" in x for x in _out))
check("fusion: có fused_score để trace đọc được vì sao đổi thứ tự",
      all("fused_score" in x for x in _out))
check("fusion: rỗng thì trả rỗng", ci.apply_fusion([], []) == [])
check("fusion: không có semantic vẫn chạy, giữ thứ tự lexical",
      [x["capability_id"] for x in ci.apply_fusion(_ranked, [])] == ["a", "b"])

# Đây là lý do tồn tại của cả tầng hybrid: lexical xếp c chót vì không chung từ khoá, nhưng
# semantic hiểu ý nên xếp nhất. Nếu ảnh hưởng của hybrid quá nhỏ thì c không bao giờ lên
# được và module này chỉ là code chạy cho có.
_near = [{"capability_id": "a", "score": 0.50, "source_id": "s"},
         {"capability_id": "b", "score": 0.48, "source_id": "s"},
         {"capability_id": "c", "score": 0.44, "source_id": "s"}]
_out2 = ci.apply_fusion(_near, semantic_ids=["c"])
check("fusion: semantic KÉO ĐƯỢC mục lexical xếp chót lên đầu",
      _out2[0]["capability_id"] == "c")

# Nhưng có TRẦN: semantic không được kéo rác lên trên một mục khớp rất mạnh.
_far = [{"capability_id": "manh", "score": 0.92, "source_id": "s"},
        {"capability_id": "rac", "score": 0.20, "source_id": "s"}]
_out3 = ci.apply_fusion(_far, semantic_ids=["rac"])
check("fusion: semantic KHÔNG kéo được mục rác lên trên mục khớp mạnh",
      _out3[0]["capability_id"] == "manh")

# ---- 5. BẤT BIẾN AN TOÀN: widening không bao giờ nới quyền ----
# Đây là rủi ro thật của việc tìm rộng hơn: thêm ứng viên mà quên lọc là mở đường cho một
# tool ghi/nguy hiểm lọt vào phiên chỉ-đọc.
from capability_registry import CapabilityRegistry  # noqa: E402
from capability_resolver import ActorPolicy, DeterministicResolver  # noqa: E402

_tmp = Path(tempfile.mkdtemp(prefix="javis-capidx-reg-"))
_brain = _tmp / "brain"
_reg = CapabilityRegistry(_tmp / "registry")
_tools = [
    {"fn": "cal_list", "name": "cal_list", "description": "doc lich calendar list xem lich",
     "schema": {"type": "object", "properties": {}}},
    {"fn": "cal_delete", "name": "cal_delete", "description": "xoa lich calendar delete",
     "schema": {"type": "object", "properties": {}}},
]
_routes = {
    "cal_list": {"source_type": "mcp", "source_id": "cal", "effect": "read",
                 "required_mode": "readonly", "health": "healthy", "call": lambda a: None},
    "cal_delete": {"source_type": "mcp", "source_id": "cal", "effect": "write",
                   "required_mode": "safe", "health": "healthy", "call": lambda a: None},
}
_reg.refresh_tools(_brain, _tools, _routes)
_resolver = DeterministicResolver(_reg)

# LƯU Ý: capability_id là hash (cap_...), KHÔNG chứa tên tool. So khớp tên bằng
# capability_id là assertion pass RỖNG - đã dính đúng bẫy này một lần. Luôn so bằng `name`.
_res = _resolver.resolve("calendar", str(_brain), ActorPolicy(mode="readonly"))
_names = {x["name"] for x in (_res.get("selected") or [])}
_names |= {x["name"] for x in (_res.get("ranked") or [])}
check("quyền readonly: tool GHI không lọt vào kết quả dù có nới rộng",
      "cal_delete" not in _names and "cal_list" in _names)

# Ca trên KHÔNG đủ: với candidate_limit mặc định 120 và registry chỉ vài tool, nhánh
# widening không bao giờ thêm được gì, nên nó không kiểm được cái nó tưởng đang kiểm.
# (Phát hiện bằng mutation: gỡ hard filter khỏi widening mà test vẫn xanh.)
# Dựng lại với limit bé để widening THẬT SỰ nạp thêm ứng viên mới.
from capability_resolver import ResolverPolicy  # noqa: E402

_tmp2 = Path(tempfile.mkdtemp(prefix="javis-capidx-widen-"))
_brain2 = _tmp2 / "brain"
_reg2 = CapabilityRegistry(_tmp2 / "registry")
_tools2, _routes2 = [], {}
for _i in range(6):
    _fn = f"cal_read_{_i}"
    _tools2.append({"fn": _fn, "name": _fn, "description": "calendar lich doc xem",
                    "schema": {"type": "object", "properties": {}}})
    _routes2[_fn] = {"source_type": "mcp", "source_id": "cal", "effect": "read",
                     "required_mode": "readonly", "health": "healthy",
                     "call": lambda a: None}
# Tool GHI, mô tả khớp mạnh để nó chắc chắn nằm trong tập nới rộng.
_tools2.append({"fn": "cal_wipe", "name": "cal_wipe",
                "description": "calendar lich xoa sach wipe delete",
                "schema": {"type": "object", "properties": {}}})
_routes2["cal_wipe"] = {"source_type": "mcp", "source_id": "cal", "effect": "write",
                        "required_mode": "safe", "health": "healthy",
                        "call": lambda a: None}
_reg2.refresh_tools(_brain2, _tools2, _routes2)

# candidate_limit=2: hai ứng viên đầu điểm sát nhau → "ambiguous_top" → widening chạy thật.
# (limit=1 KHÔNG dùng được: một ứng viên mạnh duy nhất thì needs_widening nói đã đủ chắc.)
_narrow = DeterministicResolver(_reg2, ResolverPolicy(candidate_limit=2, widen_factor=8))
_res2 = _narrow.resolve("calendar lich", str(_brain2), ActorPolicy(mode="readonly"))
_all2 = {x["name"] for x in (_res2.get("ranked") or [])}
check("widening THẬT SỰ nạp thêm ứng viên (nếu không thì test dưới vô nghĩa)",
      len(_all2) > 1)
check("widening nạp thêm nhưng tool GHI vẫn bị hard filter chặn",
      "cal_wipe" not in _all2)

# Và chiều ngược lại: quyền đủ thì tool ghi phải xuất hiện, chứng minh nó CÓ trong tập nới.
_res3 = _narrow.resolve("calendar lich", str(_brain2), ActorPolicy(mode="full"))
check("quyền full thì đúng tool ghi đó xuất hiện qua widening",
      "cal_wipe" in {x["name"] for x in (_res3.get("ranked") or [])})

_res_full = _resolver.resolve("calendar", str(_brain), ActorPolicy(mode="full"))
_full_names = {x["name"] for x in (_res_full.get("ranked") or [])}
check("quyền full thì thấy nhiều hơn quyền readonly (lọc thật sự có tác dụng)",
      len(_full_names) > len(_names))

check("report nêu widen_reason để đọc trên trang Chẩn đoán",
      "widen_reason" in _res)

# Truy vấn không khớp gì: phải nới rộng rồi vẫn không bịa ra kết quả.
_res_miss = _resolver.resolve("zzzz khong khop gi ca", str(_brain), ActorPolicy(mode="full"))
check("truy vấn không khớp: không bịa ra selected",
      not (_res_miss.get("selected") or []))

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_capability_index: tất cả pass")
