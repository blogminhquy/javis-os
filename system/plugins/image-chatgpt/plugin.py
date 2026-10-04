"""Plugin bundled: tạo ảnh bằng gói ChatGPT (OAuth) cho MỌI engine.

Đăng ký tool javis_generate_image, gọi image_gen.generate_chatgpt
(Codex Responses + tool image_generation) bằng chính gói ChatGPT đã đăng nhập.
Bất kỳ engine nào (Claude Code/Codex/API) khi user bảo "tạo ảnh ..." đều gọi được tool này.

- min_mode=safe: coi như thao tác GHI (tạo file + dùng quota) → chặn ở chế độ suggest.
- check_fn: chưa kết nối ChatGPT → tool báo rõ cách bật, không lỗi khó hiểu.

Tool thứ hai javis_describe_image (0.73.0) là đôi MẮT cho engine không tự xem được ảnh: hub chỉ
chuyển chữ và sáu engine API không gửi ảnh, nên ChatGPT nhìn ảnh trong brain rồi tả lại bằng chữ
(xem server/image_vision.py). Chỉ đọc nên min_mode=readonly.
"""
from __future__ import annotations

import image_gen
import image_vision
import openai_oauth


def register(ctx):
    def _check():
        try:
            if not openai_oauth.status().get("connected"):
                return ("Chưa kết nối ChatGPT (OAuth). Vào trang Model đăng nhập ChatGPT rồi thử lại - "
                        "tạo ảnh dùng chính gói ChatGPT, không cần API key.")
        except Exception as e:
            return f"Không kiểm tra được kết nối ChatGPT: {e}"
        return None

    async def _gen(args, cctx):
        args = args or {}
        prompt = str(args.get("prompt") or "").strip()
        if not prompt:
            return "ERROR: thiếu 'prompt' (mô tả ảnh cần tạo)."
        aspect = str(args.get("aspect_ratio") or "square")
        quality = str(args.get("quality") or "medium")
        # `images`: đường dẫn ảnh MẪU trong brain. Nhận cả chuỗi một ảnh lẫn mảng nhiều ảnh -
        # engine nào cũng có lúc gửi kiểu này kiểu kia, ép một kiểu là thỉnh thoảng lại hỏng.
        raw = args.get("images") or args.get("image") or []
        if isinstance(raw, str):
            raw = [raw]
        anh = [str(x).strip() for x in raw if str(x or "").strip()]
        res = await image_gen.generate_chatgpt(prompt, aspect, quality,
                                               vault_root=cctx.vault_root, images=anh)
        if not res.get("ok"):
            return "ERROR: " + str(res.get("error") or "tạo ảnh thất bại")
        rel = res["rel_path"]
        theo = f" (dựng theo {res.get('refs') or 0} ảnh mẫu bạn gửi)" if res.get("refs") else ""
        return (f"Đã tạo ảnh ({res['size']}, chất lượng {res['quality']}){theo}, lưu tại {rel}. "
                f"HÃY NHÚNG ngay vào câu trả lời cho người dùng bằng cú pháp markdown: "
                f"![{prompt[:40]}]({rel})")

    ctx.register_tool(
        name="javis_generate_image",
        description=("Tạo hoặc SỬA ẢNH bằng gói ChatGPT đang đăng nhập (không cần API key). Tham số: "
                     "prompt (mô tả, bắt buộc), images (danh sách đường dẫn ảnh MẪU trong brain - "
                     "ChatGPT sẽ NHÌN THẤY ảnh thật để sửa/dựng theo, dùng khi cần giữ đúng sản phẩm, "
                     "nhãn, khuôn mặt, bố cục), aspect_ratio (square|landscape|portrait), "
                     "quality (low|medium|high). Người dùng đưa ảnh và bảo 'dựng theo ảnh này' thì "
                     "PHẢI truyền đường dẫn ảnh đó vào images, đừng tả lại ảnh bằng lời. "
                     "Sau khi gọi, NHÚNG ![](đường-dẫn) trả về vào câu trả lời."),
        handler=_gen, min_mode="safe", check_fn=_check,
        schema={"type": "object", "properties": {
            "prompt": {"type": "string", "description": "Mô tả ảnh cần tạo (càng rõ càng tốt)"},
            "aspect_ratio": {"type": "string", "enum": ["square", "landscape", "portrait"],
                             "description": "Tỉ lệ khung ảnh, mặc định square"},
            "quality": {"type": "string", "enum": ["low", "medium", "high"],
                        "description": "Chất lượng/độ chi tiết, mặc định medium"},
            "images": {"type": "array", "items": {"type": "string"},
                       "description": ("Đường dẫn ảnh MẪU trong brain (vd attachments/chai.jpg) để "
                                       "ChatGPT nhìn và dựng theo. Tối đa 4 ảnh, mỗi ảnh dưới 12MB.")}},
            "required": ["prompt"]},
    )

    async def _describe(args, cctx):
        args = args or {}
        raw = args.get("images") or args.get("image") or args.get("path") or []
        if isinstance(raw, str):
            raw = [raw]
        anh = [str(x).strip() for x in raw if str(x or "").strip()]
        if not anh:
            return "ERROR: thiếu 'images' (đường dẫn ảnh trong brain, vd attachments/abc.jpg)."
        res = await image_vision.describe_images(anh, str(args.get("question") or ""),
                                                 vault_root=cctx.vault_root)
        if not res.get("ok"):
            return "ERROR: " + str(res.get("error") or "không xem được ảnh")
        return f"ChatGPT đã xem {res['count']} ảnh:\n{res['text']}"

    ctx.register_tool(
        name="javis_describe_image",
        description=("XEM ẢNH trong brain: ChatGPT (gói đang đăng nhập) nhìn ảnh thật rồi tả lại bằng chữ, chép nguyên văn "
                     "chữ/số trong ảnh. Dùng khi bạn KHÔNG tự mở được file ảnh (tool đọc file chỉ đọc chữ, không cho thấy "
                     "ảnh). Tham số: images (đường dẫn ảnh trong brain, tối đa 4), question (cần tìm gì trong ảnh, tuỳ chọn)."),
        handler=_describe, min_mode="readonly", check_fn=_check,
        schema={"type": "object", "properties": {
            "images": {"type": "array", "items": {"type": "string"},
                       "description": "Đường dẫn ảnh trong brain (vd attachments/zalo/abc.jpg). Tối đa 4 ảnh."},
            "question": {"type": "string", "description": "Cần biết gì trong ảnh (tuỳ chọn), vd 'tổng tiền trên hoá đơn'"}},
            "required": ["images"]},
    )
