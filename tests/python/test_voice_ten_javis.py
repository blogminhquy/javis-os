"""Nói "Javis" mà máy nghe chép "David" thì Javis vẫn hiểu là gọi mình (0.64.38).

0.64.32 gỡ lớp sửa tên ở cửa WebSocket cùng lúc với việc chặn AI viết lại câu, và dặn bộ não
giọng "không tự đoán tên người". Kết quả (chủ dự án 24/09): Javis đáp "anh nói là David" và
bong bóng giữ nguyên "David". Test này giữ cả ba mắt xích: lớp sửa tất định, chỗ gọi nó trước
khi lưu tin, và lời dặn bộ não giọng.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "server"))

import nghe_sua  # noqa: E402
import voice_brain  # noqa: E402


class TenJavis(unittest.TestCase):
    def test_cau_that_cua_nguoi_dung(self):
        tv = nghe_sua.tu_vung({})
        self.assertEqual(nghe_sua.sua("Ok bây giờ giọng nói chắc là tốt rồi đúng không David", tv),
                         "Ok bây giờ giọng nói chắc là tốt rồi đúng không Javis")
        self.assertEqual(nghe_sua.sua("David ơi", tv), "Javis ơi")
        # Người thứ ba và câu không có tên thì để yên.
        self.assertEqual(nghe_sua.sua("nhắn cho David là mai họp", tv), "nhắn cho David là mai họp")
        self.assertEqual(nghe_sua.sua("Em phải trả lời vâng", tv), "Em phải trả lời vâng")

    def test_websocket_sua_ten_truoc_khi_luu(self):
        src = open(os.path.join(ROOT, "server", "main.py"), encoding="utf-8").read()
        i_sua = src.find("_sua = nghe_sua.sua(_speech, _tv)")
        i_luu = src.find('store.append_message(conv_sid, "user", user_message)\n            # Bong bóng')
        self.assertGreater(i_sua, 0, "cửa WebSocket phải sửa tên nghe nhầm cho tin từ mic")
        self.assertGreater(i_luu, i_sua, "phải sửa trước khi lưu tin vào phiên")
        self.assertIn('"raw": _nghe_tho', src, "phải báo bong bóng kèm chữ thô, không âm thầm")

    def test_bo_nao_giong_hieu_ten_nghe_nham(self):
        p = voice_brain.SYSTEM_PROMPT
        self.assertIn("'David'", p)
        self.assertIn("không nói người dùng đã nói 'David'", p)


if __name__ == "__main__":
    unittest.main()
