"""capability_index.py - Tầng truy xuất hybrid cho Capability Registry.

Trước module này, resolver chọn capability CHỈ bằng lexical (FTS5 cộng chấm điểm phủ từ
khoá). Móc embedding có sẵn nhưng chỉ để QUAN SÁT: kết quả của nó được ghi vào report rồi
bỏ đó, không tham gia xếp hạng.

Với vài chục capability thì lexical đủ. Nhưng lời hứa của cả kiến trúc là "cắm thêm bao
nhiêu MCP cũng được", và đó chính là lúc lexical bắt đầu trượt trong im lặng: người dùng hỏi
"chốt đơn cho khách" trong khi tool tên là `create_invoice`, không chung một từ nào.

Ba thứ ở đây, đều là HÀM THUẦN nên kiểm được mà không cần dựng registry:

1. `rrf_fuse` - trộn nhiều bảng xếp hạng bằng Reciprocal Rank Fusion. Chọn RRF thay vì cộng
   điểm có trọng số vì điểm lexical và điểm cosine KHÔNG cùng thang đo; cộng thẳng là để
   thang đo nào rộng hơn lấn át, và không có cách nào chuẩn hoá đúng mà không cần dữ liệu
   hiệu chỉnh mà ta chưa có. RRF chỉ nhìn THỨ HẠNG nên miễn nhiễm chuyện đó.

2. `needs_widening` - quyết định có nới rộng tìm kiếm không, dựa trên tín hiệu YẾU chứ không
   dựa trên số lượng cố định. Đây là phần trả lời trực tiếp phản biện "bị fix ở cài đặt mặc
   định": không có top_k cứng, chỉ có "kết quả yếu thì tìm rộng hơn".

3. `source_affinity` - tín hiệu đồ thị rẻ nhất mà vẫn thật: capability cùng NGUỒN với một
   kết quả mạnh được cộng nhẹ. Người ta hiếm khi hỏi một việc mà lời giải nằm rải rác ở
   năm nguồn khác nhau; hỏi về POS thì các tool POS khác cũng đáng nhìn.

AN TOÀN: module này chỉ đổi THỨ TỰ và ĐỀ XUẤT THÊM ứng viên. Nó không bao giờ bỏ qua
`_hard_filter` của resolver - ứng viên do widening thêm vào vẫn phải đi qua đúng bộ lọc
quyền, vì lọc chạy SAU khi hợp nhất. Không có đường nào ở đây nới quyền.
"""
from __future__ import annotations

# Hằng RRF chuẩn trong tài liệu gốc. Giá trị lớn làm phẳng ảnh hưởng của thứ hạng đầu,
# giá trị nhỏ làm hạng 1 lấn át. 60 là mặc định đã được dùng rộng rãi.
RRF_K = 60


def rrf_fuse(rank_lists, k: int = RRF_K, weights=None) -> dict:
    """Trộn nhiều danh sách ID đã xếp hạng thành {id: điểm hợp nhất}.

    rank_lists: chuỗi các danh sách ID, mỗi danh sách đã sắp từ tốt nhất xuống.
    weights: trọng số theo từng danh sách; thiếu thì coi như 1.0.

    Điểm của một ID = tổng của w / (k + hạng). ID xuất hiện ở nhiều danh sách được cộng
    dồn, nên thứ mà cả lexical lẫn semantic đều đồng ý sẽ nổi lên - đó chính là điều ta
    muốn, và nó không cần hai bên cùng thang điểm.
    """
    out: dict[str, float] = {}
    lists = list(rank_lists or [])
    ws = list(weights or [])
    kk = max(1, int(k or RRF_K))
    for index, ids in enumerate(lists):
        weight = float(ws[index]) if index < len(ws) else 1.0
        if weight <= 0:
            continue
        for rank, cid in enumerate(ids or []):
            key = str(cid)
            out[key] = out.get(key, 0.0) + weight / (kk + rank + 1)
    return out


def needs_widening(ranked, min_top_score: float, min_gap: float) -> str:
    """Có nên tìm rộng hơn không. Trả mã lý do, "" nghĩa là kết quả đã đủ chắc.

    Ba tín hiệu YẾU, không cái nào là ngưỡng số lượng:
      - không có ứng viên nào,
      - ứng viên tốt nhất vẫn dưới mức đáng tin,
      - hai ứng viên đầu sát nhau (mơ hồ, không biết chọn cái nào).
    """
    if not ranked:
        return "no_candidate"
    top = float(ranked[0].get("score") or 0.0)
    if top < float(min_top_score or 0.0):
        return "weak_top_score"
    if len(ranked) > 1:
        second = float(ranked[1].get("score") or 0.0)
        if (top - second) < float(min_gap or 0.0):
            return "ambiguous_top"
    return ""


def source_affinity(ranked, boost: float = 0.03, top_n: int = 3) -> dict:
    """{capability_id: điểm cộng} cho ứng viên cùng nguồn với các kết quả mạnh nhất.

    Cộng NHẸ và có trần: đây là gợi ý ngữ cảnh, không phải bằng chứng. Để nó lớn thì một
    nguồn đông tool sẽ tự đẩy mình lên đầu chỉ vì đông, đúng kiểu thiên lệch phổ biến mà
    resolver deterministic cố tránh.
    """
    if not ranked:
        return {}
    strong_sources = set()
    for item in ranked[:max(1, int(top_n or 3))]:
        source = str(item.get("source_id") or item.get("source_type") or "")
        if source:
            strong_sources.add(source)
    if not strong_sources:
        return {}
    out = {}
    for item in ranked:
        source = str(item.get("source_id") or item.get("source_type") or "")
        if source and source in strong_sources:
            out[str(item.get("capability_id"))] = float(boost)
    return out


# Ảnh hưởng TỐI ĐA của tầng hybrid lên điểm cuối. Đây là con số quan trọng nhất module này.
#
# Điểm RRF thô rất nhỏ (cỡ 1/61) so với điểm lexical chạy trong 0..1, nên cộng thẳng vào là
# tầng hybrid gần như không đổi được gì - code chạy đúng mà không có tác dụng, kiểu tệ nhất.
# Vì vậy phải CHUẨN HOÁ điểm RRF về 0..1 rồi nhân với hệ số này.
#
# Chọn 0.15 vì hai ràng buộc ngược chiều: đủ lớn để lật một cặp sát nhau (chênh lexical
# thường dưới 0.10), nhưng đủ nhỏ để không bao giờ kéo một mục rác (0.05) lên trên một mục
# khớp mạnh (0.90). `_cut` của resolver vẫn dùng điểm tuyệt đối, nên ảnh hưởng phải có trần.
SEMANTIC_INFLUENCE = 0.15


def apply_fusion(ranked, semantic_ids, semantic_weight: float = 0.6,
                 affinity_boost: float = 0.03,
                 influence: float = SEMANTIC_INFLUENCE) -> list:
    """Xếp lại `ranked` bằng lexical + semantic + affinity nguồn. Trả danh sách MỚI.

    Giữ nguyên mọi trường của từng mục và thêm `fused_score` để trace còn đọc được vì sao
    thứ tự đổi. KHÔNG thêm, KHÔNG bớt mục nào: việc thêm ứng viên là của widening, và mọi
    ứng viên đều đã đi qua hard filter trước khi tới đây.
    """
    if not ranked:
        return []
    # CHỈ trộn các tín hiệu NGOÀI lexical. Điểm lexical đã nằm sẵn trong `score`, nên đưa
    # thứ hạng lexical vào RRF nữa là đếm nó HAI LẦN: phần semantic bị pha loãng tới mức
    # không bao giờ lật được một cặp sát nhau, tức là cả tầng hybrid chạy cho có.
    # (Đã tính tay và kiểm bằng test: với ảnh hưởng 0.15, cách cũ vẫn thiếu 0.006 để kéo
    # được một mục lexical xếp chót lên đầu.)
    lists, weights = [], []
    if semantic_ids:
        lists.append([str(x) for x in semantic_ids])
        weights.append(float(semantic_weight))
    fused = rrf_fuse(lists, weights=weights) if lists else {}
    top_rrf = max(fused.values()) if fused else 0.0
    affinity = source_affinity(ranked, boost=affinity_boost)

    out = []
    for item in ranked:
        cid = str(item.get("capability_id"))
        row = dict(item)
        hybrid = (fused.get(cid, 0.0) / top_rrf * float(influence)) if top_rrf > 0 else 0.0
        row["fused_score"] = round(
            float(item.get("score") or 0.0) + hybrid + affinity.get(cid, 0.0), 6
        )
        out.append(row)
    out.sort(key=lambda x: (-x["fused_score"], -float(x.get("score") or 0.0),
                            str(x.get("capability_id"))))
    return out
