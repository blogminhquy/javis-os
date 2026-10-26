"""Cách tests/run.py chia test thành nhóm cho CI (0.344.0): không sót, không trùng, xác định được.

    python tests/run.py run_chia_nhom

CI chạy test Python trên 2 máy, mỗi máy một nhóm (`--shard i/2`). Một lỗi chia nhóm ở đây là
test lặng lẽ không bao giờ chạy mà CI vẫn xanh, nên canary này kiểm đúng các khe đó, và kiểm
luôn trên danh sách test THẬT đang có trong repo.
"""
from _paths import ROOT  # noqa: E402
import importlib.util
import unittest

_spec = importlib.util.spec_from_file_location("javis_tests_run", ROOT / "tests" / "run.py")
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)


def _ten_that():
    return sorted(f.name for f in R.PY_DIR.glob("test_*.py"))


class ChiaNhom(unittest.TestCase):
    def test_danh_sach_that_khong_sot_khong_trung(self):
        ten = _ten_that()
        self.assertGreater(len(ten), 100, "quét thư mục test ra quá ít file, sai đường dẫn?")
        for so_nhom in (1, 2, 3, 4):
            nhom = R.chia_nhom(ten, so_nhom, R.doc_thoi_gian())
            gop = [t for n in nhom for t in n]
            self.assertEqual(sorted(gop), ten)
            self.assertEqual(len(gop), len(set(gop)))
            self.assertTrue(all(nhom))

    def test_file_moi_chua_co_so_do_van_vao_dung_mot_nhom(self):
        ten = _ten_that() + ["test_zz_moi_tinh.py"]
        nhom = R.chia_nhom(ten, 2, R.doc_thoi_gian())
        self.assertEqual(sum(n.count("test_zz_moi_tinh.py") for n in nhom), 1)

    def test_xac_dinh_duoc(self):
        ten = _ten_that()
        g = R.doc_thoi_gian()
        self.assertEqual(R.chia_nhom(ten, 2, g), R.chia_nhom(list(reversed(ten)), 2, g))

    def test_can_bang_theo_thoi_gian_va_nang_truoc(self):
        g = {"a.py": 100, "b.py": 60, "c.py": 50, "d.py": 10}
        nhom = R.chia_nhom(list(g), 2, g)
        self.assertEqual(nhom, [["a.py", "d.py"], ["b.py", "c.py"]])

    def test_dau_vao_hong_la_loi_ro_rang(self):
        with self.assertRaises(ValueError):
            R.chia_nhom([], 2, {})
        with self.assertRaises(ValueError):
            R.chia_nhom(["a.py", "a.py"], 2, {})
        with self.assertRaises(ValueError):
            R.chia_nhom(["a.py"], 2, {})  # nhóm 2 rỗng
        with self.assertRaises(ValueError):
            R.chia_nhom(["a.py"], 0, {})

    def test_chay_rieng_tro_dung_file_that(self):
        # Đổi tên một test đo thời gian mà quên sửa CHAY_RIENG thì nó lặng lẽ quay lại chạy chung và đỏ oan.
        self.assertEqual(sorted(R.CHAY_RIENG - set(_ten_that())), [])

    def test_tham_so(self):
        ts = R.doc_tham_so(["--py", "--shard", "2/2", "--jobs=4", "-v", "zalo"])
        self.assertEqual((ts["shard"], ts["jobs"], ts["py"], ts["ver"], ts["loc"]), ((2, 2), 4, True, True, ["zalo"]))
        for xau in (["--shard", "3/2"], ["--shard", "0/2"], ["--jobs", "0"], ["--jobs"], ["--la"]):
            with self.assertRaises(ValueError, msg=xau):
                R.doc_tham_so(xau)


if __name__ == "__main__":
    unittest.main()
