"""Curator dọn MEMORY.md: gỡ dòng mục lục đã hết giá trị.

Vì sao đây là việc đáng làm nhất trong "chống rác tri thức": MEMORY.md được nạp TRƯỚC MỌI
câu hỏi. Nhánh `supersedes` của learn đã biết ghi `superseded_by:` vào fact cũ, nhưng CHƯA
AI gỡ dòng mục lục của nó, nên một thông tin đã nghỉ hưu vẫn chảy vào ngữ cảnh từng lượt và
vẫn chiếm chỗ trong trần ~150 dòng.

Hai loại được gỡ, cả hai đều có bằng chứng cứng: fact đã bị thay thế, và dòng trỏ vào file
không còn tồn tại. Cố ý KHÔNG gỡ theo TUỔI - "chủ làm nước mắm truyền thống" mười năm sau
vẫn đúng, y như lập luận một chiều của `skill_usage`.

Và không bao giờ xoá file fact: chỉ gỡ dòng mục lục.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401

from learn import LearnDeps, LearnFeature, _da_bi_thay


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


def _fact(tmp_path, slug, superseded_by=""):
    sup = f"superseded_by: {superseded_by}\n" if superseded_by else ""
    _write(tmp_path / "memory" / "facts" / f"{slug}.md",
           f"---\ntype: business\ncreated: 2026-01-01\n{sup}---\nNội dung.\n")


def _index(tmp_path, *dong):
    fp = tmp_path / "memory" / "MEMORY.md"
    _write(fp, "# Ký ức\n\n" + "\n".join(dong) + "\n")
    return fp


# ---- _da_bi_thay ----

def test_nhan_dien_fact_da_bi_thay(tmp_path):
    _fact(tmp_path, "gia-cu", superseded_by="gia-moi")
    _fact(tmp_path, "gia-moi")
    d = tmp_path / "memory" / "facts"
    assert _da_bi_thay(d / "gia-cu.md")
    assert not _da_bi_thay(d / "gia-moi.md")


def test_superseded_by_rong_khong_tinh_la_da_thay(tmp_path):
    """Frontmatter có khoá nhưng bỏ trống thì chưa ai thay thế nó cả."""
    _fact(tmp_path, "a", superseded_by='""')
    assert not _da_bi_thay(tmp_path / "memory" / "facts" / "a.md")


def test_file_hong_hoac_khong_co_thi_tra_False_chu_khong_no(tmp_path):
    assert not _da_bi_thay(tmp_path / "memory" / "facts" / "khong-ton-tai.md")


# ---- gỡ dòng mục lục ----

def test_go_dong_cua_fact_da_bi_thay(tmp_path):
    feature = _feature(tmp_path)
    _fact(tmp_path, "gia-cu", superseded_by="gia-moi")
    _fact(tmp_path, "gia-moi")
    idx = _index(tmp_path,
                 "- [Giá cũ](facts/gia-cu.md) - bảng giá 2025",
                 "- [Giá mới](facts/gia-moi.md) - bảng giá 2026")
    ket = feature._curator_retire_memory(idx)
    text = idx.read_text(encoding="utf-8")
    assert ket["n"] == 1
    assert "gia-cu.md" not in text
    assert "gia-moi.md" in text


def test_khong_bao_gio_xoa_file_fact(tmp_path):
    """Chỉ gỡ dòng mục lục. File vẫn nằm đó, vẫn đọc được, git vẫn hoàn tác được."""
    feature = _feature(tmp_path)
    _fact(tmp_path, "gia-cu", superseded_by="gia-moi")
    idx = _index(tmp_path, "- [Giá cũ](facts/gia-cu.md) - bảng giá 2025")
    feature._curator_retire_memory(idx)
    assert (tmp_path / "memory" / "facts" / "gia-cu.md").is_file()


def test_go_dong_tro_vao_file_da_xoa(tmp_path):
    feature = _feature(tmp_path)
    idx = _index(tmp_path, "- [Đã xoá tay](facts/khong-con.md) - gì đó")
    ket = feature._curator_retire_memory(idx)
    assert ket["n"] == 1
    assert "khong-con.md" not in idx.read_text(encoding="utf-8")


def test_khong_go_theo_tuoi(tmp_path):
    """Fact cũ mà vẫn đúng thì phải ở lại. Vắng tín hiệu không phải bằng chứng vô dụng."""
    feature = _feature(tmp_path)
    _fact(tmp_path, "nghe-nghiep")
    idx = _index(tmp_path, "- [Nghề](facts/nghe-nghiep.md) - làm nước mắm truyền thống")
    assert feature._curator_retire_memory(idx) is None
    assert "nghe-nghiep.md" in idx.read_text(encoding="utf-8")


def test_giu_nguyen_dong_khong_phai_muc_luc(tmp_path):
    feature = _feature(tmp_path)
    _fact(tmp_path, "a", superseded_by="b")
    _fact(tmp_path, "b")
    idx = _index(tmp_path, "## Nhóm kinh doanh", "- [A](facts/a.md) - cũ",
                 "- [B](facts/b.md) - mới", "_ghi chú chủ viết tay_")
    feature._curator_retire_memory(idx)
    text = idx.read_text(encoding="utf-8")
    assert "## Nhóm kinh doanh" in text
    assert "_ghi chú chủ viết tay_" in text


def test_chuan_hoa_gach_dai_cu(tmp_path):
    """MEMORY.md nạp trước mọi câu hỏi, nên gạch dài ở đây vào cả ngữ cảnh lẫn giọng đọc.
    Luật 8 của CLAUDE.md cấm tuyệt đối, mà bản trước 0.55.65 lại ghi ra đúng dấu đó."""
    feature = _feature(tmp_path)
    _fact(tmp_path, "nghe")
    idx = _index(tmp_path, "- [Nghề](facts/nghe.md) — làm nước mắm")
    feature._curator_retire_memory(idx)
    text = idx.read_text(encoding="utf-8")
    assert "—" not in text
    assert "- [Nghề](facts/nghe.md) - làm nước mắm" in text


# ---- reindex không kéo lại thứ vừa gỡ ----

def test_reindex_khong_keo_lai_fact_da_bi_thay(tmp_path):
    """Không có rào này thì hai vòng curator đá nhau mãi: một bên gỡ, một bên thêm lại."""
    feature = _feature(tmp_path)
    _fact(tmp_path, "gia-cu", superseded_by="gia-moi")
    _fact(tmp_path, "gia-moi")
    idx = _index(tmp_path, "- [Giá mới](facts/gia-moi.md) - bảng giá 2026")
    feature._curator_reindex_memory("brain", str(tmp_path))
    text = idx.read_text(encoding="utf-8")
    assert "gia-cu.md" not in text
    assert "gia-moi.md" in text


def test_reindex_van_bo_sung_fact_binh_thuong_con_thieu(tmp_path):
    feature = _feature(tmp_path)
    _fact(tmp_path, "khach-lon")
    idx = _index(tmp_path, "_(Chưa có ký ức nào)_")
    feature._curator_reindex_memory("brain", str(tmp_path))
    assert "khach-lon.md" in idx.read_text(encoding="utf-8")


if __name__ == "__main__":
    import sys
    try:
        import pytest
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
