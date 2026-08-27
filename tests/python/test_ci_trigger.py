"""Khối `on:` của CI: đủ ba cửa vào, và không cửa nào được lặng lẽ biến mất.

Ba dòng trong đó không phải chuyện thẩm mỹ, mỗi dòng bịt một khe hở KHÁC nhau:

- `push` nghe `claude/**`: phiên Claude Code luôn đẩy commit lên nhánh TRƯỚC rồi mới mở PR.
  Lúc đẩy thì chưa có PR nên `pull_request` không bắt, mà mở PR sau đó có lúc GitHub không
  sinh run cho commit đã nằm sẵn. Thiếu dòng này là quay lại cảnh phải vào tab Actions bấm
  tay mỗi lần, và có lần sót thật (0.49.x).
- `pull_request`: PR từ fork KHÔNG sinh sự kiện `push` ở repo gốc. Repo đang có hơn 100 fork
  nên bỏ dòng này là đóng CI với mọi đóng góp bên ngoài - đúng nhóm PR cần soi nhất.
- `workflow_dispatch`: lối thoát để chạy lại một commit cũ mà không phải đẩy commit rác.

Test này KHÔNG parse YAML bằng thư viện ngoài (CI chỉ cài requirements.txt + pytest), chỉ
đọc thô khối `on:` - đủ để bắt việc xoá nhầm.
"""
import re  # noqa: E402
from _paths import ROOT  # noqa: E402,F401

CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

fails = []


def check(name: str, condition: bool) -> None:
    print(("PASS: " if condition else "FAIL: ") + name)
    if not condition:
        fails.append(name)


# Cắt đúng khối `on:` (từ dòng `on:` tới `jobs:`) rồi bỏ hết dòng chú thích. Soi nguyên file
# thì một chữ nằm trong comment cũng làm test xanh oan - đúng kiểu canary vô dụng.
_khoi = CI.split("\non:", 1)[1].split("\njobs:", 1)[0]
ON = "\n".join(d for d in _khoi.splitlines() if not d.strip().startswith("#"))

check("có nghe sự kiện push", re.search(r"^\s*push:\s*$", ON, re.M) is not None)
_br = re.search(r"^\s*branches:\s*\[(.*?)\]\s*$", ON, re.M)
_ten = [t.strip().strip("'\"") for t in _br.group(1).split(",")] if _br else []
check("push vẫn nghe main", "main" in _ten)
# CANARY chính của test này. Đây là dòng vừa thêm ở 0.49.4, và cũng là dòng dễ bị dọn nhầm
# nhất về sau vì nhìn qua tưởng là nhánh rác của một phiên làm việc cũ.
check("CANARY: push nghe nhánh claude/** (thiếu là phải bấm CI bằng tay)",
      "claude/**" in _ten)
check("pull_request còn nguyên (cửa duy nhất của PR từ fork)",
      re.search(r"^\s*pull_request:\s*$", ON, re.M) is not None)
check("workflow_dispatch còn nguyên (lối chạy lại commit cũ)",
      re.search(r"^\s*workflow_dispatch:\s*$", ON, re.M) is not None)
# Lý do ba dòng trên tồn tại nằm ở chú thích ngay cạnh chúng. Mất chú thích thì người sau
# đọc file chỉ thấy ba dòng trơ và rất dễ rút gọn lại.
check("lý do vì sao nghe claude/** được ghi ngay trong file",
      "claude/**" in CI and "chưa có PR" in CI)
check("lý do vì sao KHÔNG bỏ pull_request được ghi ngay trong file", "fork" in CI)

if fails:
    raise SystemExit(f"\nFAIL - test_ci_trigger: {len(fails)} lỗi")
print("\nOK - test_ci_trigger: tất cả pass")
