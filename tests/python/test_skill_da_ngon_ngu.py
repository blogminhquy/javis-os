"""Mô tả skill theo ngôn ngữ - Đợt 5 của tầng đa ngôn ngữ.

    python tests/run.py skill_da_ngon_ngu

Mô tả skill KHÔNG phải chữ trang trí. Nó là bề mặt ĐỐI CHIẾU giữa câu người dùng vừa gõ và
danh sách skill: router bơm nguyên danh sách đó vào system prompt của mọi engine, rồi model tự
chọn skill nào khớp. Cùng thứ tiếng với câu hỏi thì chọn sắc hơn.

Nhưng luật quan trọng nhất ở đây là luật RƠI VỀ. Thiếu bản dịch phải rơi về mô tả gốc, KHÔNG
được rơi về rỗng: mô tả tiếng Việt vẫn định tuyến được cho người hỏi tiếng Anh (model đọc được
cả hai), còn mô tả rỗng thì skill BIẾN MẤT khỏi router. Hỏng thầm, và hỏng nặng hơn nhiều.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import pathlib
import shutil
import sys
import tempfile

import skill_router
import system_sync

_loi = []


def check(ten, dieu_kien):
    print(f"       {'ok  ' if dieu_kien else 'FAIL'} {ten}")
    if not dieu_kien:
        _loi.append(ten)


# ============================================================
# 1. Chọn theo ngôn ngữ, và LUẬT RƠI VỀ
# ============================================================
_meta = {"name": "Notes", "description": "Lưu note", "description_en": "Save a note"}

check("có bản dịch thì lấy bản dịch",
      skill_router.theo_ngon_ngu(_meta, "description", "en") == "Save a note")
check("ngôn ngữ gốc thì lấy bản gốc",
      skill_router.theo_ngon_ngu(_meta, "description", "vi") == "Lưu note")
check("KHÔNG có bản dịch thì rơi về bản gốc, không rơi về rỗng",
      skill_router.theo_ngon_ngu(_meta, "description", "th") == "Lưu note")
check("không truyền ngôn ngữ cũng ra bản gốc",
      skill_router.theo_ngon_ngu(_meta, "description") == "Lưu note")
check("bản dịch RỖNG bị bỏ qua, rơi về gốc (chuỗi trắng không phải bản dịch)",
      skill_router.theo_ngon_ngu({"description": "Lưu note", "description_en": "   "},
                                 "description", "en") == "Lưu note")
check("mã ngôn ngữ dạng vùng vẫn khớp (en-US -> en)",
      skill_router.theo_ngon_ngu(_meta, "description", "en-US") == "Save a note")
check("meta hỏng kiểu thì trả rỗng chứ không nổ",
      skill_router.theo_ngon_ngu(None, "description", "en") == ""
      and skill_router.theo_ngon_ngu({"description": 123}, "description") == "")

check("nhận ra khoá bản dịch",
      skill_router.la_khoa_ngon_ngu("description_en")
      and skill_router.la_khoa_ngon_ngu("name_th"))
check("KHÔNG nhận nhầm khoá thường",
      not skill_router.la_khoa_ngon_ngu("description")
      and not skill_router.la_khoa_ngon_ngu("group")
      and not skill_router.la_khoa_ngon_ngu("description_long"))
check("liệt kê được mọi bản dịch có trong file",
      skill_router.ban_dich({"description": "a", "description_en": "b", "name_en": "c"})
      == {"en": "b"})


# ============================================================
# 2. Skill HỆ THỐNG: đủ bản tiếng Anh, và bản dịch chịu đúng cái trần của bản gốc
# ============================================================
# Bản dịch đi vào ĐÚNG chỗ bản gốc đi vào (phần đầu cố định của mọi lượt chat), nên nó phải
# chịu đúng trần đó. Miễn cho bản dịch là mở lại đúng cái lỗ 61% token mà trần này bịt.
_sys = system_sync.SYSTEM_SKILLS_DIR
_thieu, _dai, _sao_rong = [], [], []
for _f in sorted(_sys.glob("*/SKILL.md")):
    _m, _ = skill_router.split_frontmatter(_f.read_text(encoding="utf-8"))
    _en = skill_router.theo_ngon_ngu(_m, "description", "en")
    if not _en or _en == skill_router.theo_ngon_ngu(_m, "description", "vi"):
        _thieu.append(_f.parent.name)
        continue
    if len(_en) > skill_router.SKILL_DESC_MAX:
        _dai.append(f"{_f.parent.name}={len(_en)}")
    if skill_router.validate_description(_en):
        _sao_rong.append(_f.parent.name)

check(f"mọi skill hệ thống có description_en ({len(list(_sys.glob('*/SKILL.md')))} skill)",
      not _thieu)
if _thieu:
    print("              thiếu: " + ", ".join(_thieu))
check("bản tiếng Anh lọt trần SKILL_DESC_MAX", not _dai)
if _dai:
    print("              " + ", ".join(_dai))
check("bản tiếng Anh không mở đầu bằng cụm sáo rỗng", not _sao_rong)


# ============================================================
# 3. Đọc cả cây skill theo ngôn ngữ
# ============================================================
_tmp = pathlib.Path(tempfile.mkdtemp(prefix="javis-skill-i18n-"))
(_tmp / "skills" / "co-ban-dich").mkdir(parents=True)
(_tmp / "skills" / "co-ban-dich" / "SKILL.md").write_text(
    '---\nname: Ghi chú\nname_en: Notes\ndescription: Lưu note nhanh\n'
    'description_en: Save a note fast\ngroup: AI\n---\n\nthân skill\n', encoding="utf-8")
(_tmp / "skills" / "chua-dich").mkdir(parents=True)
(_tmp / "skills" / "chua-dich" / "SKILL.md").write_text(
    '---\nname: Chưa dịch\ndescription: Mô tả chỉ có tiếng Việt\ngroup: AI\n---\n\nthân\n',
    encoding="utf-8")

_en = {s["slug"]: s for s in skill_router.list_skills(_tmp, "en")}
_vi = {s["slug"]: s for s in skill_router.list_skills(_tmp, "vi")}
check("list_skills(en) trả mô tả tiếng Anh",
      _en["co-ban-dich"]["description"] == "Save a note fast"
      and _en["co-ban-dich"]["name"] == "Notes")
check("list_skills(vi) trả mô tả gốc",
      _vi["co-ban-dich"]["description"] == "Lưu note nhanh"
      and _vi["co-ban-dich"]["name"] == "Ghi chú")
check("skill CHƯA dịch vẫn có mô tả khi đọc bằng tiếng Anh (không biến mất khỏi router)",
      _en["chua-dich"]["description"] == "Mô tả chỉ có tiếng Việt")
check("ngôn ngữ chưa ai dịch gì cũng không làm rỗng danh sách",
      all(s["description"] for s in skill_router.list_skills(_tmp, "th")))

_mf = {s["slug"]: s for s in skill_router.list_skill_manifests(_tmp, "en")}
check("manifest (Phase 8) cũng theo ngôn ngữ",
      _mf["co-ban-dich"]["description"] == "Save a note fast")


# ============================================================
# 3b. Phase 8: chấm điểm skill là so TRÙNG TỪ, nên đây là chỗ ngôn ngữ đổi HÀNH VI
# ============================================================
# Router trong system prompt đưa cả danh sách cho model đọc, nên mô tả lệch tiếng vẫn chọn
# đúng. `LazySkillSource._score` thì không có model nào cả - nó đếm từ chung giữa câu hỏi và
# mô tả. Câu tiếng Anh gặp mô tả tiếng Việt là điểm gần 0, skill không bao giờ được chọn.
import lazy_skill_runtime
import capability_registry

_nguon = lazy_skill_runtime.LazySkillSource(capability_registry.CapabilityRegistry())
_cau = "save a note fast"
_diem_en = _nguon.resolve(_tmp, _cau, lang="en").score
_diem_vi = _nguon.resolve(_tmp, _cau, lang="vi").score
check(f"câu tiếng Anh chấm trên mô tả tiếng Anh có điểm ({_diem_en:.2f})", _diem_en > 0.24)
check(f"cùng câu đó chấm trên mô tả tiếng Việt thì KHÔNG đủ điểm ({_diem_vi:.2f})",
      _diem_vi < _diem_en)

# Cache phải tách theo ngôn ngữ. Không tách thì lượt đầu nạp bộ manifest nào, mọi lượt sau
# dùng bộ đó - đổi ngôn ngữ ở trang Cài đặt xong vẫn chấm trên thứ tiếng cũ, im lặng.
check("CANARY: cache manifest tách theo ngôn ngữ",
      len({k for k in _nguon._refresh_cache}) == 2)
check("và khoá cache có mang mã ngôn ngữ",
      {k[1] for k in _nguon._refresh_cache} == {"en", "vi"})


# ============================================================
# 4. Cắt mô tả lúc mirror: cắt CẢ bản dịch, và KHÔNG đụng vào thân skill
# ============================================================
_cap = skill_router.SKILL_DESC_MAX
_qua_dai_vi = "V" * (_cap + 40)
_qua_dai_en = "E" * (_cap + 40)
_goc = (f"---\nname: X\ndescription: {_qua_dai_vi}\ndescription_en: {_qua_dai_en}\n"
        "group: AI\n---\n\n# Hướng dẫn\n\nVí dụ frontmatter cho skill mới:\n\n"
        "```yaml\ndescription: " + "M" * (_cap + 40) + "\n```\n")
_moi = system_sync._cap_desc(_goc, _cap)
check("cắt được (có chỗ vượt trần)", _moi is not None)
if _moi:
    _m2, _body2 = skill_router.split_frontmatter(_moi)
    check("bản GỐC bị cắt về đúng trần",
          len(skill_router.theo_ngon_ngu(_m2, "description", "vi")) <= _cap)
    # Đây là mục đích của cả thay đổi: trước Đợt 5 regex chỉ khớp đúng khoá `description`,
    # nên mô tả tiếng Anh dài bao nhiêu cũng lọt vào phần đầu cố định của mọi lượt chat.
    check("bản DỊCH cũng bị cắt về đúng trần",
          len(skill_router.theo_ngon_ngu(_m2, "description", "en")) <= _cap)
    # Bản một-khoá cũ né được chuyện này nhờ ăn may (nó lấy match ĐẦU TIÊN). Quét nhiều khoá
    # mà không chặn ở hết frontmatter là sẽ sửa nhầm đoạn mẫu YAML nằm trong thân hướng dẫn.
    check("CANARY: dòng `description:` trong THÂN skill KHÔNG bị đụng tới",
          ("M" * (_cap + 40)) in _body2)

check("không có gì vượt trần thì trả None (không ghi lại file vô ích)",
      system_sync._cap_desc("---\nname: X\ndescription: ngắn\ndescription_en: short\n---\n\nthân\n",
                            _cap) is None)
check("file không có frontmatter thì không đụng vào",
      system_sync._cap_desc("description: " + "Z" * 400 + "\n", _cap) is None)


# ============================================================
# 5. CHỐT CHẶN: sửa skill qua giao diện KHÔNG được xoá bản dịch
# ============================================================
# Form của trang Kỹ năng chỉ gửi lên {name, description, group}. Ghi đè trắng frontmatter là
# mỗi lần user bấm Lưu lại xoá sạch bản dịch mà không ai thấy - skill hệ thống sẽ lặng lẽ tụt
# về mô tả tiếng Việt cho người dùng tiếng Anh.
_src = pathlib.Path(SERVER, "main.py").read_text(encoding="utf-8")
_ghi = _src[_src.find("async def save_skill("):]
_ghi = _ghi[:_ghi.find('@app.post("/skills/delete")')]
check("CANARY: POST /skills đọc frontmatter cũ trước khi ghi đè",
      "_read_md(d / \"SKILL.md\")" in _ghi)
check("CANARY: POST /skills giữ lại khoá bản dịch",
      "la_khoa_ngon_ngu" in _ghi)

shutil.rmtree(_tmp, ignore_errors=True)

print()
if _loi:
    print(f"ĐỎ {len(_loi)} mục: " + "; ".join(_loi[:4]))
    sys.exit(1)
print("Tất cả xanh.")
