"""Đồng bộ CẢ ẢNH lên GitHub (backup.sync_images, mặc định TẮT) - và hai cái bẫy phải chặn:

1. Máy lệch cấu hình xoá chéo: sync 2 chiều nhiều máy, công tắc nằm trong settings TỪNG MÁY.
   Máy TẮT mà prune ảnh "mình không đưa" khỏi mirror thì ảnh máy BẬT vừa đẩy lên bị xoá lan.
   → Máy tắt coi ảnh là NGOÀI PHẠM VI: không chép, không xoá, không nhận.
2. Máy dọn media tự phá backup: media_gc dọn attachments theo hạn; ảnh bị dọn thì lượt sync
   sau ghi nhận "đã xoá" rồi lan đi mọi máy. → Bật sync ảnh thì media_gc bỏ qua attachments.

Chạy: python tests/run.py backup_sync_anh (pytest style, cần git cho nhóm force-add).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import subprocess

import git_brain
import media_gc


def _w(path, data=b"x"):
    from pathlib import Path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))


# ---- nhận diện + cửa lọc ----

def test_la_anh_va_khong_lan_sang_chu():
    assert git_brain.la_anh("a.jpg") and git_brain.la_anh("x/y/B.PNG") and git_brain.la_anh("c.webp")
    assert not git_brain.la_anh("video.mp4") and not git_brain.la_anh("doc.pdf")
    assert not git_brain.la_anh("note.md")
    # svg là CHỮ (đã sync sẵn từ trước), không nằm trong nhóm ảnh raster
    assert git_brain.la_file_chu("logo.svg") and not git_brain.la_anh("logo.svg")


def test_tran_anh_mac_dinh_va_env(monkeypatch):
    monkeypatch.delenv("JAVIS_SYNC_ANH_MAX_MB", raising=False)
    assert git_brain.anh_max_bytes() == git_brain.ANH_MAX_MB_DEFAULT * 1024 * 1024
    monkeypatch.setenv("JAVIS_SYNC_ANH_MAX_MB", "2")
    assert git_brain.anh_max_bytes() == 2 * 1024 * 1024
    monkeypatch.setenv("JAVIS_SYNC_ANH_MAX_MB", "rac")
    assert git_brain.anh_max_bytes() == git_brain.ANH_MAX_MB_DEFAULT * 1024 * 1024


def test_backup_skip_theo_co():
    skip = git_brain._backup_skip
    assert skip("brain/attachments/a.jpg") is True, "mặc định TẮT: ảnh vẫn bị loại như cũ"
    assert skip("brain/attachments/a.jpg", sync_images=True) is False
    assert skip("brain/attachments/clip.mp4", sync_images=True) is True, "video không bao giờ lên"
    assert skip("brain/inbox/a.jpg", sync_images=True) is True, "inbox là chỗ trung chuyển, vẫn loại"
    assert skip("brain/Memory/conversations/x.jpg", sync_images=True) is True, \
        "vùng chặn cứng (log/hội thoại) thắng cả cờ ảnh"
    assert skip("brain/note.md") is False, "chữ đi qua như cũ"


# ---- _sync_mirror: chép + prune ----

def test_tat_khong_chep_va_khong_xoa_cheo(tmp_path):
    """BẪY 1: máy TẮT không chép ảnh, và TUYỆT ĐỐI không xoá ảnh máy khác đã đưa vào mirror."""
    src, mirror = tmp_path / "brains", tmp_path / "mirror"
    _w(src / "b" / "attachments" / "moi.jpg", b"j" * 10)
    _w(src / "b" / "note.md", "chu")
    _w(mirror / "b" / "attachments" / "cua-may-khac.jpg", b"k" * 10)   # máy BẬT khác đẩy lên
    rep = git_brain._sync_mirror(str(src), str(mirror), sync_images=False)
    assert not (mirror / "b" / "attachments" / "moi.jpg").exists(), "tắt thì không chép ảnh"
    assert (mirror / "b" / "attachments" / "cua-may-khac.jpg").exists(), \
        "máy tắt xoá ảnh máy bật khỏi mirror = mất dữ liệu lan sang mọi máy"
    assert (mirror / "b" / "note.md").exists() and rep["media_bo_qua"] == 1


def test_bat_chep_anh_va_tra_danh_sach(tmp_path):
    src, mirror = tmp_path / "brains", tmp_path / "mirror"
    _w(src / "b" / "attachments" / "sp.jpg", b"j" * 10)
    _w(src / "b" / "inbox" / "tam.jpg", b"j" * 10)
    _w(src / "b" / "attachments" / "clip.mp4", b"v" * 10)
    rep = git_brain._sync_mirror(str(src), str(mirror), sync_images=True)
    assert (mirror / "b" / "attachments" / "sp.jpg").exists()
    assert rep["image_rels"] == ["b/attachments/sp.jpg"]
    assert not (mirror / "b" / "inbox" / "tam.jpg").exists(), "inbox không lên dù bật"
    assert not (mirror / "b" / "attachments" / "clip.mp4").exists(), "video không lên"
    assert rep["media_bo_qua"] == 2   # inbox jpg + mp4


def test_bat_anh_qua_tran_bi_bo_va_khong_bi_prune(tmp_path, monkeypatch):
    monkeypatch.setenv("JAVIS_SYNC_ANH_MAX_MB", "1")
    src, mirror = tmp_path / "brains", tmp_path / "mirror"
    _w(src / "b" / "attachments" / "to.jpg", b"j" * (1024 * 1024 + 1))
    _w(mirror / "b" / "attachments" / "to.jpg", b"cu")   # từng sync được (trần cũ cao hơn)
    rep = git_brain._sync_mirror(str(src), str(mirror), sync_images=True)
    assert rep["image_rels"] == [] and rep["media_bo_qua"] == 1
    assert (mirror / "b" / "attachments" / "to.jpg").exists(), \
        "ảnh còn trên đĩa mà vắng khỏi keep (quá trần) thì để yên - đổi trần không phải lệnh xoá"


def test_bat_xoa_that_thi_lan_di(tmp_path):
    """Máy BẬT xoá ảnh trên đĩa → prune khỏi mirror để lệnh xoá lan sang máy khác (đúng ý)."""
    src, mirror = tmp_path / "brains", tmp_path / "mirror"
    _w(src / "b" / "note.md", "chu")
    _w(mirror / "b" / "attachments" / "da-xoa.jpg", b"j")
    git_brain._sync_mirror(str(src), str(mirror), sync_images=True)
    assert not (mirror / "b" / "attachments" / "da-xoa.jpg").exists()


# ---- _apply_back: chiều nhận về ----

def _apply(tmp_path, sync_images):
    mirror, brains = tmp_path / "mirror", tmp_path / "brains"
    _w(mirror / "b" / "attachments" / "tu-may-khac.jpg", b"j")
    _w(mirror / "b" / "note.md", "chu")
    (brains / "b").mkdir(parents=True, exist_ok=True)
    rep = git_brain._apply_back(str(mirror), str(brains),
                                {"b/attachments/tu-may-khac.jpg", "b/note.md"}, 0.0,
                                sync_images=sync_images)
    return brains, rep


def test_apply_back_theo_co(tmp_path):
    brains, rep = _apply(tmp_path, sync_images=False)
    assert not (brains / "b" / "attachments" / "tu-may-khac.jpg").exists(), "tắt: không nhận ảnh"
    assert (brains / "b" / "note.md").exists() and rep["applied"] == 1


def test_apply_back_bat_nhan_anh(tmp_path):
    brains, rep = _apply(tmp_path, sync_images=True)
    assert (brains / "b" / "attachments" / "tu-may-khac.jpg").exists()
    assert rep["applied"] == 2


# ---- force-add: .gitignore của brain (chép sang mirror) chặn ảnh, phải ép đích danh ----

def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)


def test_force_add_vuot_gitignore_cua_brain(tmp_path):
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    _git(mirror, "init")
    _git(mirror, "config", "user.email", "t@t"); _git(mirror, "config", "user.name", "t")
    (mirror / "b").mkdir()
    git_brain._ensure_gitignore_lines(str(mirror / "b"))   # khối allowlist chỉ-chữ của brain
    _w(mirror / "b" / "attachments" / "sp.jpg", b"j")
    _w(mirror / "b" / "note.md", "chu")
    _git(mirror, "add", "-A")
    staged = (_git(mirror, "diff", "--cached", "--name-only").stdout or "")
    assert "b/note.md" in staged and "sp.jpg" not in staged, \
        "tiền đề: add -A bị .gitignore của brain chặn ảnh (không thì force-add là thừa)"
    git_brain._force_add_anh(str(mirror), ["b/attachments/sp.jpg"])
    staged = (_git(mirror, "diff", "--cached", "--name-only").stdout or "")
    assert "b/attachments/sp.jpg" in staged
    # log thô bị ignore ở khối 3 vẫn KHÔNG bị cuốn vào (force đích danh, không phải -f cả cây)
    _w(mirror / "b" / "Javis" / "learn-log" / "2026.md", "log")
    _git(mirror, "add", "-A")
    assert "learn-log" not in (_git(mirror, "diff", "--cached", "--name-only").stdout or "")


# ---- BẪY 2: bật sync ảnh thì media_gc bỏ qua attachments, vẫn dọn inbox ----

def test_media_gc_bo_qua_attachments_khi_giu_anh(tmp_path):
    _w(tmp_path / "attachments" / "cu.jpg", b"j")
    _w(tmp_path / "inbox" / "cu.jpg", b"j")
    rat_cu = 1.0
    os.utime(tmp_path / "attachments" / "cu.jpg", (rat_cu, rat_cu))
    os.utime(tmp_path / "inbox" / "cu.jpg", (rat_cu, rat_cu))
    kq = media_gc.sweep(str(tmp_path), max_age_days=30, max_mb=300, attachments=False)
    assert (tmp_path / "attachments" / "cu.jpg").exists(), \
        "đang backup ảnh mà máy dọn xoá thì lệnh xoá lan đi mọi máy - ảnh backup tự biến mất"
    assert not (tmp_path / "inbox" / "cu.jpg").exists(), "inbox vẫn dọn (không bao giờ sync)"
    assert kq["files"] == 1


def test_media_gc_mac_dinh_van_nhu_cu(tmp_path):
    _w(tmp_path / "attachments" / "cu.jpg", b"j")
    os.utime(tmp_path / "attachments" / "cu.jpg", (1.0, 1.0))
    media_gc.sweep(str(tmp_path), max_age_days=30, max_mb=300)
    assert not (tmp_path / "attachments" / "cu.jpg").exists()


# ---- config: mặc định TẮT ----

def test_mac_dinh_tat():
    import config as cfgmod
    assert cfgmod._DEFAULT["backup"]["sync_images"] is False


if __name__ == "__main__":
    # CI chạy TỪNG FILE như script (`python tests/python/test_x.py`), không gọi pytest.
    import sys
    try:
        import pytest
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
