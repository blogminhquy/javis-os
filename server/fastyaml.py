"""yaml.safe_load nhưng dùng bộ nạp C (libyaml) khi có.

Vì sao: mọi frontmatter trong Javis (SKILL.md, agent, workflow, plugin.yaml, note) đều đi
qua yaml.safe_load, mà hàm đó chọn SafeLoader bản thuần Python. Đo trên frontmatter SKILL.md
130 byte thật: 0,446ms bản Python so với 0,072ms bản C, nhanh 6,2 lần. YAML chiếm 64% chi phí
build_system_prompt - hàm chặn event loop 150ms MỖI lượt chat, mỗi task Kanban, mỗi lần nhắc
hẹn nổ và mỗi tick loop. Nên một dòng đổi bộ nạp đáng giá hơn nhiều tối ưu khác.

libyaml đã có sẵn trong requirements (PyYAML build kèm wheel có C extension trên mọi nền
Javis chạy). Thiếu thì tự rơi về bản Python, không vỡ gì.

Dùng: `import fastyaml` rồi `fastyaml.safe_load(text)` - thay thẳng cho `yaml.safe_load`.
"""
import re

import yaml

try:
    from yaml import CSafeLoader as _CLoader   # libyaml
    HAS_C = True
except ImportError:                            # PyYAML build thuần Python
    _CLoader = None
    HAS_C = False

_PyLoader = yaml.SafeLoader


def safe_load(stream):
    """Như yaml.safe_load. Bộ nạp C từ chối thì thử lại bằng bộ nạp Python.

    Hai bộ nạp KHÔNG khớp tuyệt đối ở vài góc hiếm (khoá trùng, một số ký tự ngắt dòng
    unicode, chữ trong thông báo lỗi). Lần thử lại làm cho mọi thứ bản Python đọc được
    thì bản này cũng đọc được, tức không thể thành bước lùi. Chỉ tốn thêm ở nhánh lỗi,
    mà nhánh lỗi vốn hiếm.
    """
    if _CLoader is None:
        return yaml.load(stream, Loader=_PyLoader)
    try:
        return yaml.load(stream, Loader=_CLoader)
    except yaml.YAMLError:
        return yaml.load(stream, Loader=_PyLoader)


# Frontmatter delimiters are LINES of their own. Splitting on the first "---" anywhere cut a
# workflow whose `task:` said "... giữa hai dòng --- gồm ..." in half and silently dropped its
# later steps (16 steps read as 14, 2026-10-15).
_FM_OPEN_RE = re.compile(r"---[ \t]*\r?\n")
_FM_CLOSE_RE = re.compile(r"^---[ \t]*\r?$", re.MULTILINE)


def split_frontmatter(text):
    """(header, body) of a Markdown file with a YAML frontmatter block, or None if it has none.

    Both delimiters must be a line holding only `---` (trailing spaces and CRLF allowed); a
    `---` inside a sentence is content. For a valid file the result is byte-identical to the
    old `text.split("---", 2)[1:]`: header is everything between the two delimiter lines
    (newlines included) and body starts right after the closing dashes.
    """
    if not text or not text.startswith("---"):
        return None
    m = _FM_OPEN_RE.match(text)
    if not m:
        return None
    c = _FM_CLOSE_RE.search(text, m.end())
    if not c:
        return None
    return text[3:c.start()], text[c.start() + 3:]
