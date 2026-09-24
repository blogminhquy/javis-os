"""Nhân dạng trợ lý: cùng thư viện hình, màu, màu mắt và cỡ mắt với linh vật (dashboard/pet.js).

Từ 0.64.39 avatar trợ lý dùng CHUNG bộ chỉnh với trang Linh vật, nên ngoài hình và bảng màu
nó còn mang: mã màu thân tự chọn (`color`, khi palette = "custom"), màu mắt (`eye`: den /
trang / custom kèm `eyeColor`) và hệ số cỡ mắt (`eyeSize`). Các khoá mới chỉ xuất hiện khi đã
được chọn: trợ lý cũ giữ nguyên đúng dạng {shape, palette} và mắt vẫn suy tự động theo thân.
"""
import re
import secrets

SHAPES = ("circle", "square", "triangle", "cloud", "pentagon", "star")
# 12 màu ĐẦU là bộ gốc và là bộ bốc mặc định theo slug. Đừng đổi thứ tự hay chèn vào giữa:
# trợ lý cũ chưa lưu avatar lấy màu bằng `seed % 12`, đổi ở đây là cả danh sách đổi màu.
PALETTES_MAC_DINH = ("amber", "pearl", "clay", "rose", "honey", "sage", "jade", "blue",
                     "lavender", "pink", "slate", "cocoa")
# Tám màu thêm ở 0.59.36 trước đây THIẾU ở đây, nên chọn "Cam" cho trợ lý là máy chủ trả 400.
PALETTES = PALETTES_MAC_DINH + ("cam", "nang", "chanh", "bacha", "thanhthien", "cham", "tim",
                                "ruby", "custom")
EYES = ("den", "trang", "custom")
EYE_SIZE_MIN, EYE_SIZE_MAX = 0.8, 1.5
_HEX = re.compile(r"#[0-9a-fA-F]{6}")


def _hex(v):
    return v.lower() if isinstance(v, str) and _HEX.fullmatch(v) else None


def _eye_size(v):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n != n or not EYE_SIZE_MIN <= n <= EYE_SIZE_MAX:   # n != n: NaN
        return None
    return round(n, 2)


def for_agent(meta, slug):
    # Agent cũ có nhân dạng ổn định, không đổi mỗi lần tải trang.
    seed = sum(ord(c) for c in slug)
    avatar = meta.get("avatar") or {}
    if not isinstance(avatar, dict):
        avatar = {}
    out = {"shape": avatar.get("shape") if avatar.get("shape") in SHAPES else SHAPES[seed % len(SHAPES)],
           "palette": avatar.get("palette") if avatar.get("palette") in PALETTES
           else PALETTES_MAC_DINH[seed % len(PALETTES_MAC_DINH)]}
    color = _hex(avatar.get("color"))
    if out["palette"] == "custom":
        if color:
            out["color"] = color
        else:   # "custom" mà mất mã màu thì không vẽ được gì: về màu mặc định theo slug
            out["palette"] = PALETTES_MAC_DINH[seed % len(PALETTES_MAC_DINH)]
    if avatar.get("eye") in EYES:
        eye_color = _hex(avatar.get("eyeColor"))
        if avatar["eye"] != "custom" or eye_color:
            out["eye"] = avatar["eye"]
            if eye_color and avatar["eye"] == "custom":
                out["eyeColor"] = eye_color
    size = _eye_size(avatar.get("eyeSize"))
    if size is not None and size != 1:
        out["eyeSize"] = size
    return out


def for_save(previous, slug, shape=None, palette=None, color=None, eye=None, eye_color=None,
             eye_size=None):
    avatar = for_agent(previous, slug) if previous is not None else {
        "shape": secrets.choice(SHAPES), "palette": secrets.choice(PALETTES_MAC_DINH)}
    for key, value, allowed in (("shape", shape, SHAPES), ("palette", palette, PALETTES),
                                ("eye", eye, EYES)):
        if value is not None:
            if value not in allowed:
                raise ValueError("avatar_" + key)
            avatar[key] = value
    if color is not None:
        if not _hex(color):
            raise ValueError("avatar_color")
        avatar["color"] = _hex(color)
    if eye_color is not None:
        if not _hex(eye_color):
            raise ValueError("avatar_eye_color")
        avatar["eyeColor"] = _hex(eye_color)
    if eye_size is not None:
        n = _eye_size(eye_size)
        if n is None:
            raise ValueError("avatar_eye_size")
        avatar["eyeSize"] = n
    # Mã màu chỉ có nghĩa khi đang dùng ô tự chọn; bỏ đi cho frontmatter gọn.
    if avatar.get("palette") != "custom":
        avatar.pop("color", None)
    elif "color" not in avatar:
        raise ValueError("avatar_color")
    if avatar.get("eye") != "custom":
        avatar.pop("eyeColor", None)
    elif "eyeColor" not in avatar:
        raise ValueError("avatar_eye_color")
    if avatar.get("eyeSize") == 1:
        avatar.pop("eyeSize", None)
    return avatar
