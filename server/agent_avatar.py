"""Nhân dạng trợ lý: chỉ nhận hình và bảng màu trong thư viện linh vật."""
import secrets

SHAPES = ("circle", "square", "triangle", "cloud", "pentagon")
PALETTES = ("amber", "pearl", "clay", "rose", "honey", "sage", "jade", "blue",
            "lavender", "pink", "slate", "cocoa")


def for_agent(meta, slug):
    # Agent cũ có nhân dạng ổn định, không đổi mỗi lần tải trang.
    seed = sum(ord(c) for c in slug)
    avatar = meta.get("avatar") or {}
    if not isinstance(avatar, dict):
        avatar = {}
    return {"shape": avatar.get("shape") if avatar.get("shape") in SHAPES else SHAPES[seed % len(SHAPES)],
            "palette": avatar.get("palette") if avatar.get("palette") in PALETTES else PALETTES[seed % len(PALETTES)]}


def for_save(previous, slug, shape=None, palette=None):
    avatar = for_agent(previous, slug) if previous is not None else {
        "shape": secrets.choice(SHAPES), "palette": secrets.choice(PALETTES)}
    for key, value, allowed in (("shape", shape, SHAPES), ("palette", palette, PALETTES)):
        if value is not None:
            if value not in allowed:
                raise ValueError("avatar_" + key)
            avatar[key] = value
    return avatar
