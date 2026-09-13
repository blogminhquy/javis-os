"""Tự học SỬA skill đã có tại chỗ (op=update), thay vì chỉ biết tạo mới.

Trước bản này `_promote_sync` chặn thẳng mọi skill trùng slug ("đã tồn tại → không ghi đè"),
nên một skill vừa lộ ra chỗ sai trong hội thoại thì vòng học không làm gì được: hoặc bỏ qua,
hoặc đẻ một slug gần giống bên cạnh. Agent và workflow đã có `op=update` từ 26/08 với bốn
rào ép bằng Python; đây là mang đúng khuôn đó sang skill, cộng HAI rào riêng của skill:

  5. Skill HỆ THỐNG do app ship: cấm. Sửa một cái là app ngừng cập nhật đè lên nó, tức mất
     im lặng một năng lực mặc định.
  6. Skill user đã TẮT: cấm, ở cả nhánh tạo lẫn nhánh sửa.

Rào nào mất thì hỏng theo một kiểu riêng, nên mỗi rào một test.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import yaml

from learn import LearnDeps, LearnFeature


def _write(path, text):
    from pathlib import Path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def _feature(tmp_path):
    deps = LearnDeps(
        build_system_prompt=lambda b: "",
        brain_root=lambda b: str(tmp_path),
        brain_memory_dir=lambda b: tmp_path / "memory",
        resolve_subfolder=lambda a, b, c: str(tmp_path / "Wiki"),
        aux_model=lambda: None,
        atomic_write_text=_write,
        sessions_store=None,
        state_dir=tmp_path,
        readonly_tools=["Read"],
    )
    return LearnFeature(deps)


CAPS = {"memory": False, "wiki": False, "skill": True, "task": False,
        "agent": False, "workflow": False}

THAN_CU = "## Khi nào dùng\nKhi cần chốt đơn.\n\n## Quy trình\n1. Bước cũ."
THAN_MOI = "## Khi nào dùng\nKhi cần chốt đơn.\n\n## Quy trình\n1. Bước cũ.\n2. Bước còn thiếu."


def _co_skill(tmp_path, slug="chot-don", extra_fm="", than=THAN_CU):
    fp = tmp_path / "skills" / slug / "SKILL.md"
    _write(fp, f"---\nname: Chốt đơn\ndescription: Chốt đơn cho khách đã hỏi giá.\n"
               f"group: Sales\nstatus: active\ncreated: 2026-01-01\nmodel: sonnet\n{extra_fm}---\n{than}\n")
    return fp


def _sk(**over):
    x = {"op": "update", "slug": "chot-don", "name": "Chốt đơn",
         "description": "Chốt đơn cho khách đã hỏi giá.", "group": "Sales",
         "body": THAN_MOI, "reason": "Làm theo skill cũ bị sót bước xác nhận địa chỉ",
         "confidence": 3}
    x.update(over)
    return x


def _chay(feature, tmp_path, skills):
    return feature._promote_sync("brain", {"skills": skills}, feature.read_config(),
                                 CAPS, allow_write=True)


def _fm(fp):
    text = fp.read_text(encoding="utf-8")
    _, y, body = text.split("---\n", 2)
    return yaml.safe_load(y), body.strip()


# ---- sửa được, và sửa ĐÚNG CHỖ ----

def test_sua_tai_cho_khong_de_ra_ban_sao(tmp_path):
    feature = _feature(tmp_path)
    fp = _co_skill(tmp_path)
    rep = _chay(feature, tmp_path, [_sk()])
    assert rep["skills_updated"] == ["chot-don"], rep
    assert rep["skills"] == []
    assert list((tmp_path / "skills").iterdir()) == [fp.parent]   # không sinh slug thứ hai
    _, body = _fm(fp)
    assert "Bước còn thiếu" in body


def test_giu_nguyen_thu_cua_chu(tmp_path):
    """name, group, status, created và MỌI field lạ chủ tự thêm là của CHỦ. Vòng học chỉ
    được đổi phần chuyên môn, nếu không mỗi lần sửa lại thổi bay lựa chọn của người dùng."""
    feature = _feature(tmp_path)
    fp = _co_skill(tmp_path, extra_fm="uu_tien: cao\n")
    _chay(feature, tmp_path, [_sk(name="Tên fork tự đặt", group="Nhóm fork tự đặt")])
    fm, _ = _fm(fp)
    assert fm["name"] == "Chốt đơn"
    assert fm["group"] == "Sales"
    assert fm["status"] == "active"
    # đọc THÔ: PyYAML tự biến ngày không nháy thành datetime.date, còn thứ phải giữ nguyên
    # là dòng ghi ra đĩa.
    assert "created: 2026-01-01" in fp.read_text(encoding="utf-8")
    assert fm["model"] == "sonnet"
    assert fm["uu_tien"] == "cao"
    assert fm["learned_updated"]


def test_de_trong_description_la_giu_nguyen_khong_phai_xoa(tmp_path):
    """description rỗng = skill mất đường route. Fork bỏ trống phải hiểu là "không đụng"."""
    feature = _feature(tmp_path)
    fp = _co_skill(tmp_path)
    _chay(feature, tmp_path, [_sk(description="")])
    fm, _ = _fm(fp)
    assert fm["description"] == "Chốt đơn cho khách đã hỏi giá."


def test_ghi_lai_lich_su_sua(tmp_path):
    feature = _feature(tmp_path)
    fp = _co_skill(tmp_path)
    _chay(feature, tmp_path, [_sk()])
    _, body = _fm(fp)
    assert "sót bước xác nhận địa chỉ" in body


def test_description_co_dau_hai_cham_van_doc_lai_duoc(tmp_path):
    """Đường hỏng HAY GẶP nhất của frontmatter skill (xem chú thích `_skill_frontmatter`):
    description tiếng Việt có dấu hai chấm, ghi trần thì YAML hiểu thành mapping, router tha
    lỗi trả {} và skill mất SẠCH frontmatter, im lặng không route được. Nhánh sửa đi qua
    `dump_fm` chứ không qua `_skill_frontmatter`, nên phải canh riêng."""
    import skill_router
    feature = _feature(tmp_path)
    fp = _co_skill(tmp_path)
    _chay(feature, tmp_path, [_sk(description="Chốt đơn: khách đã hỏi giá nhưng chưa chốt")])
    meta = skill_router.split_frontmatter(fp.read_text(encoding="utf-8"))[0]
    assert meta.get("description") == "Chốt đơn: khách đã hỏi giá nhưng chưa chốt"


# ---- sáu rào ----

def test_rao1_khong_co_file_thi_khong_am_tham_tao_moi(tmp_path):
    feature = _feature(tmp_path)
    rep = _chay(feature, tmp_path, [_sk(slug="chua-ton-tai")])
    assert not (tmp_path / "skills" / "chua-ton-tai").exists()
    assert any("chưa có skill" in b for b in rep["blocked"]), rep["blocked"]


def test_rao2_sua_ma_khong_neu_ly_do_thi_chan(tmp_path):
    feature = _feature(tmp_path)
    fp = _co_skill(tmp_path)
    rep = _chay(feature, tmp_path, [_sk(reason="  ")])
    assert "Bước còn thiếu" not in fp.read_text(encoding="utf-8")
    assert any("không nêu lý do" in b for b in rep["blocked"]), rep["blocked"]


def test_rao4_learn_lock_la_cam_dung(tmp_path):
    feature = _feature(tmp_path)
    fp = _co_skill(tmp_path, extra_fm="learn_lock: true\n")
    rep = _chay(feature, tmp_path, [_sk()])
    assert "Bước còn thiếu" not in fp.read_text(encoding="utf-8")
    assert any("learn_lock" in b for b in rep["blocked"]), rep["blocked"]


def test_rao5_skill_he_thong_la_cam(tmp_path):
    """javis-builder do app ship và tự cập nhật. Sửa nó là bản đó thành của người dùng và app
    ngừng cập nhật đè lên, mất im lặng một năng lực mặc định."""
    import system_sync
    assert system_sync.is_system_skill("javis-builder")
    feature = _feature(tmp_path)
    fp = _co_skill(tmp_path, slug="javis-builder")
    rep = _chay(feature, tmp_path, [_sk(slug="javis-builder")])
    assert "Bước còn thiếu" not in fp.read_text(encoding="utf-8")
    assert any("hệ thống" in b for b in rep["blocked"]), rep["blocked"]


def test_rao6_skill_user_da_tat_thi_khong_hoi_sinh(tmp_path):
    feature = _feature(tmp_path)
    _write(tmp_path / "skills" / ".disabled" / "chot-don" / "SKILL.md", "---\nname: x\n---\ncũ")
    rep = _chay(feature, tmp_path, [_sk()])
    assert not (tmp_path / "skills" / "chot-don").exists()
    assert any("đã tắt" in b for b in rep["blocked"]), rep["blocked"]


def test_op_create_van_khong_bao_gio_de_skill_da_co(tmp_path):
    """Nhánh tạo mới giữ nguyên hành vi cũ: gặp slug trùng là dừng, không ghi đè."""
    feature = _feature(tmp_path)
    fp = _co_skill(tmp_path)
    rep = _chay(feature, tmp_path, [_sk(op="create")])
    assert "Bước còn thiếu" not in fp.read_text(encoding="utf-8")
    assert any("đã tồn tại" in b for b in rep["blocked"]), rep["blocked"]


def test_tao_moi_van_chay_binh_thuong(tmp_path):
    feature = _feature(tmp_path)
    rep = _chay(feature, tmp_path, [_sk(op="create", slug="viet-email")])
    assert rep["skills"] == ["viet-email"]
    fm, _ = _fm(tmp_path / "skills" / "viet-email" / "SKILL.md")
    assert fm["origin"] == "javis-learned"


# ---- dry-run: chỉ liệt kê, không ghi ----

def test_dry_run_khong_ghi_gi(tmp_path):
    feature = _feature(tmp_path)
    fp = _co_skill(tmp_path)
    rep = feature._promote_sync("brain", {"skills": [_sk()]}, feature.read_config(),
                                CAPS, allow_write=False)
    assert rep["skills_updated"] == ["chot-don"]
    assert "Bước còn thiếu" not in fp.read_text(encoding="utf-8")


# ---- prompt phải NÓI ra danh sách skill sửa được ----

def test_prompt_liet_ke_skill_da_co_va_dan_nhan_cam(tmp_path):
    feature = _feature(tmp_path)
    _co_skill(tmp_path)
    _co_skill(tmp_path, slug="javis-builder")
    _co_skill(tmp_path, slug="da-khoa", extra_fm="learn_lock: true\n")
    p = feature._build_prompt(CAPS, "brain", "hội thoại")
    assert "SKILL ĐÃ CÓ" in p
    assert "- chot-don" in p
    assert "[hệ thống, cấm sửa]" in p
    assert "[chủ đã khoá]" in p


if __name__ == "__main__":
    import sys
    try:
        import pytest
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
