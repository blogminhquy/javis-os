"""
Vòng tự cải thiện MULTI-LOOP - nhiều loop cấu hình song song, THỰC THI TUẦN TỰ.

Nâng cấp từ loop ĐƠN (loop_config.json) thành hệ N loop:
  - ĐỊNH NGHĨA loop = file markdown trong vault: <vault>/Javis/loops/<slug>.md
    (frontmatter YAML: name/slug/enabled/goal/mode/interval_min/workspace/tools_profile/
     quiet_hours/max_runs_per_day/updated; thân file = prompt mục tiêu khi goal=custom,
     goal khác thì thân file là ghi chú). Người / chat / Studio đều sửa được file này.
  - STATE runtime tách riêng, server sở hữu: <vault>/Javis/loop-state.json, key theo slug:
    {last_run, last_summary, last_status, runs_today, day, fail_streak, auto_paused_reason}.
    KHÔNG ghi state vào frontmatter - tránh giẫm chân user đang mở file trong Obsidian.
  - THỰC THI TUẦN TỰ: 1 lock toàn cục, tại 1 thời điểm chỉ 1 vòng chạy. Scheduler mỗi tick
    chọn TỐI ĐA 1 loop: enabled, ngoài quiet_hours, chưa vượt max_runs_per_day, không
    auto-paused, và QUÁ HẠN LÂU NHẤT (now - last_run - interval lớn nhất).
  - TỰ BẢO VỆ: fail_streak >= 3 (CLI lỗi hoặc kiểm chứng ✗ liên tiếp) → tự set
    auto_paused_reason trong state (không sửa file .md của user) + ghi log + báo Telegram
    nếu deps.notify được tiêm. Bật lại / bấm Run now sẽ xoá pause.

Triết lý MỖI VÒNG giữ nguyên bản gốc: Javis tự thức theo lịch, làm ĐÚNG MỘT việc cụ thể,
tự kiểm chứng độc lập (mode=auto, giả định kết quả SAI), ghi log Javis/loop-log/.

An toàn theo tools_profile:
  - "vault-safe" (MẶC ĐỊNH): file tools + MCP do Javis quản lý (POS/ads/lịch...) - loop ĐỌC
    được dữ liệu thật để làm việc. cwd ghim vault. Bash/WebFetch/WebSearch/Task NGOÀI allowlist
    → bị chặn. Chống hành động tiền/đơn qua MCP bằng 3 lớp: (a) deny_tools per-server của MCP
    (apply_mcp gắn --disallowedTools), (b) chỉ dẫn CỨNG trong prompt (_MCP_SAFETY: đọc OK,
    cấm tạo đơn/tiêu tiền/quảng cáo/đăng bài/gửi tin), (c) mode suggest = chỉ tool đọc, và
    kiểm chứng độc lập (mode auto) fail nếu phát hiện hành động ghi ra ngoài qua MCP.
  - "code" (CHỈ đặt qua .md, nâng cao): mở Bash/WebFetch/WebSearch, cwd = workspace, VẪN 0 MCP
    (fail-closed: không tạo được file MCP rỗng thì từ chối chạy) → cho loop sửa mã repo an toàn.
    Kiểm chứng thêm tiêu chí: diff nhỏ, py_compile / node --check phải sạch.

3 mức quyền (mode) - chủ chọn ở UI:
  - "suggest": chỉ tool ĐỌC (+ đọc MCP), không ghi. Mặc định an toàn nhất.
  - "auto": file tools ghi được + đọc MCP, nhưng bị chặn hành động tiền/đơn (allowlist + prompt +
    kiểm chứng fail nếu phát hiện ghi ra ngoài).
  - "full" (TOÀN QUYỀN): allowlist = None → MỌI tool + mọi MCP (trừ deny_tools per-server). Loop tự
    thao tác THẬT ra ngoài (tạo đơn/quảng cáo/gửi tin/đăng bài). Chủ phải chủ động bật + xác nhận
    cảnh báo rủi ro ở UI. Kiểm chứng chỉ soi 'đúng phạm vi nhiệm vụ', KHÔNG fail vì có hành động ghi.

Tương thích ngược: /loop/* cũ là shim trỏ về loop legacy slug "vong-lap-goc" (migrate
một lần từ loop_config.json - giữ nguyên toàn bộ custom_goal vào thân file, không xoá
json cũ). read_config()/write_config() giữ nguyên chữ ký cho shim của main.py
(_read_loop_config/_write_loop_config; Telegram vẫn đọc field "brain" từ đây).

Thiết kế "register(app, deps)" + LoopDeps: module KHÔNG import main.py (tránh vòng).
"""
from __future__ import annotations

import localefmt   # múi giờ theo cấu hình, thay UTC+7 nhúng cứng
import asyncio
import json
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

import yaml
import fastyaml
from fastapi import APIRouter, Form, Query

from claude_cli import claude_engine, cancel_all, _empty_mcp_file
import aux_engine   # engine viec nen theo model phu nguoi dung chon
import channel_context   # bóc khối JAVIS_* trước khi báo Telegram - kênh chữ, không phải web

LEGACY_SLUG = "vong-lap-goc"
# Dấu "đã migrate loop_config.json" ghi thẳng vào chính file đó. Có dấu này thì KHÔNG dựng lại
# loop legacy nữa, kể cả khi người dùng đã xoá nó (xem ensure_migrated).
MIGRATED_KEY = "loops_migrated"
GOALS = ("business", "brain", "product", "custom")

# Chỉ dẫn an toàn CỨNG cho mọi loop có MCP (mặc định): được ĐỌC, cấm hành động ghi ra ngoài.
# Loop chạy nền tự động nên tuyệt đối không được tự tiêu tiền / tạo đơn / đăng bài.
_MCP_SAFETY = (
    "⛔ AN TOÀN (BẮT BUỘC): Bạn ĐƯỢC dùng MCP để ĐỌC dữ liệu thật (POS, quảng cáo, lịch, "
    "analytics...) phục vụ nhiệm vụ. TUYỆT ĐỐI KHÔNG dùng MCP để tạo/sửa/huỷ đơn hàng, tạo/sửa/"
    "bật/tắt quảng cáo, tiêu tiền, chuyển khoản, gửi tin nhắn/email, hay đăng bài - những việc đó "
    "CHỈ chủ mới quyết. Kết quả chỉ được là NHÁP ghi vào file trong vault để chủ duyệt.\n"
)

# Chế độ TOÀN QUYỀN (mode="full"): chủ đã CHỦ ĐỘNG bật + đã đọc cảnh báo rủi ro ở UI.
# Loop được thao tác thật ra ngoài qua MCP. Vẫn nhắc cẩn trọng để không làm quá phạm vi.
_MCP_FULL = (
    "⚠ CHẾ ĐỘ TOÀN QUYỀN (chủ đã bật có chủ đích): Bạn được DÙNG MỌI công cụ và MCP để HOÀN THÀNH "
    "nhiệm vụ, KỂ CẢ hành động THẬT ra bên ngoài (tạo/sửa đơn, chạy/sửa quảng cáo, gửi tin nhắn/email, "
    "đăng bài, thao tác file). MỌI HÀNH ĐỘNG LÀ THẬT, có thể phát sinh chi phí/hệ quả và KHÔNG hoàn tác "
    "được. NGUYÊN TẮC: chỉ làm ĐÚNG phạm vi nhiệm vụ được giao, không làm quá, không đụng thứ ngoài ý "
    "định của chủ. Khi MƠ HỒ một hành động có đúng ý chủ không → GHI đề xuất vào file thay vì tự làm.\n"
)


def _now_vn() -> datetime:
    return localefmt.now()


def _today() -> str:
    return _now_vn().strftime("%Y-%m-%d")


def _ascii_slug(s: str) -> str:
    """Slug ASCII không dấu (bản local, không import main): 'Vòng lặp Hermes' → 'vong-lap-hermes'."""
    t = unicodedata.normalize("NFD", (s or "").lower().replace("đ", "d"))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:60] or "loop"


def _isolate(cli):
    """Cô lập fork nền (profile vault-safe): 0 MCP (file rỗng + strict) + chặn Bash/Web/Task.
    Vá lỗ hổng cũ: trước đây loop chỉ giới hạn allowed_tools nhưng vẫn 'thấy' MCP ambient."""
    mcpf = _empty_mcp_file()
    if mcpf:
        cli.mcp_config = mcpf
        cli.mcp_strict = True
    cli.disallowed_tools = ["Bash", "WebFetch", "WebSearch", "Task"]
    return cli


# Frontmatter: ---\n<yaml>\n---\n<body>
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
_QH_RE = re.compile(r"^\s*(\d{1,2})\s*-\s*(\d{1,2})\s*$")


def _in_quiet_hours(spec: str, hour: int) -> bool:
    """'23-07' = im lặng 23h..7h (giờ VN). Sai format / rỗng / a==b → không im lặng."""
    m = _QH_RE.match(spec or "")
    if not m:
        return False
    a, b = int(m.group(1)) % 24, int(m.group(2)) % 24
    if a == b:
        return False
    return (a <= hour < b) if a < b else (hour >= a or hour < b)


@dataclass
class LoopDeps:
    """Các helper của main.py được tiêm vào (tránh import vòng)."""
    build_system_prompt: Callable[[str], str]
    brain_root: Callable[[str], str]
    aux_model: Callable[[], Optional[str]]
    atomic_write_text: Callable[[Any, str], None]
    project_root: Path
    state_dir: Path
    safe_tools: List[str]
    readonly_tools: List[str]
    notify: Optional[Callable] = None        # async notify(text) - broadcast Telegram khi auto-pause (mọi admin)
    report: Optional[Callable] = None        # async report(owner_chat, text) - báo NGƯỜI YÊU CẦU loop mỗi vòng
    apply_mcp: Optional[Callable] = None      # apply_mcp(cli): gắn MCP Javis-quản-lý (config+strict+deny) - loop ĐỌC được dữ liệu thật
    mcp_allow_patterns: Optional[Callable] = None  # () -> ["mcp__<server>", ...] để thêm vào allowlist (MCP mới gọi được)
    # Đổi engine việc nền theo model phụ người dùng chọn (Claude / Codex / API rẻ).
    # None = giữ nguyên Claude như trước (test dựng deps tối giản không cần tiêm).
    aux_swap: Optional[Callable] = None


class LoopFeature:
    def __init__(self, deps: LoopDeps):
        self.deps = deps
        # loop_config.json cũ GIỮ NGUYÊN vị trí: nguồn migrate + nơi lưu field "brain" legacy
        # (Telegram đọc) + danh sách "brains" mà scheduler quét.
        self.config_path = Path(deps.state_dir) / "loop_config.json"
        self.DEFAULT = {
            "enabled": False, "brain": "brain", "mode": "suggest",
            "goal": "business", "custom_goal": "",
            "interval_min": 60, "last_run": 0.0, "last_summary": "", "last_status": "",
        }
        self.lock = asyncio.Lock()           # THỰC THI TUẦN TỰ: 1 vòng/lúc trên toàn hệ
        self._running: Optional[Tuple[str, str]] = None   # (brain_root_resolved, slug) đang chạy
        self._migrated = False
        self.router = self._make_router()

    # ══════════════════════ legacy config I/O (giữ chữ ký cho shim main.py) ══════════════════════

    def _read_legacy_raw(self) -> dict:
        cfg = dict(self.DEFAULT)
        try:
            if self.config_path.exists():
                cfg.update(json.loads(self.config_path.read_text(encoding="utf-8")))
        except Exception:
            pass
        return cfg

    @staticmethod
    def _has_legacy_content(cfg: dict) -> bool:
        """Config cũ có gì ĐÁNG migrate không? register_brain() cũng ghi ra file này chỉ để nhớ
        danh sách brain, nên "file tồn tại" KHÔNG đồng nghĩa "có loop cũ cần chuyển"."""
        return bool(str(cfg.get("custom_goal") or "").strip()
                    or cfg.get("enabled")
                    or float(cfg.get("last_run") or 0) > 0)

    def read_config(self) -> dict:
        """Legacy shape (Telegram đọc 'brain'; /loop/config cũ đọc cả cụm). Field loop
        (enabled/mode/goal/interval/custom_goal/last_*) overlay LIVE từ loop vong-lap-goc."""
        cfg = self._read_legacy_raw()
        try:
            brain = cfg.get("brain") or "brain"
            lp = self.get_loop(brain, LEGACY_SLUG)
            if lp:
                st = self.read_state(brain).get(LEGACY_SLUG, {})
                cfg.update({
                    "enabled": lp["enabled"], "mode": lp["mode"], "goal": lp["goal"],
                    "interval_min": lp["interval_min"], "custom_goal": lp["body"],
                    "last_run": float(st.get("last_run", 0)),
                    "last_summary": st.get("last_summary", ""),
                    "last_status": st.get("last_status", ""),
                })
        except Exception:
            pass
        return cfg

    def write_config(self, cfg: dict) -> None:
        """Legacy write: ghi json cũ (backup + giữ 'brain') RỒI đồng bộ field loop vào
        vong-lap-goc.md để 2 nguồn không lệch nhau."""
        try:
            self.deps.atomic_write_text(self.config_path, json.dumps(cfg, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"[loop config write] {e}", file=__import__('sys').stderr)
        try:
            brain = cfg.get("brain") or "brain"
            self.ensure_migrated()
            old = self.get_loop(brain, LEGACY_SLUG)
            # Loop legacy KHÔNG còn (người dùng đã xoá) và lệnh ghi này cũng rỗng → đừng dựng lại
            # một loop trắng. Client cũ bật thật (enabled) hay có nội dung thì mới tạo.
            if old is None and not self._has_legacy_content(cfg):
                return
            old = old or {"slug": LEGACY_SLUG, "name": "Vòng lặp tự cải thiện",
                          "workspace": "vault", "tools_profile": "vault-safe",
                          "quiet_hours": "", "max_runs_per_day": 0, "body": ""}
            old.update({
                "enabled": bool(cfg.get("enabled")), "mode": cfg.get("mode", "suggest"),
                "goal": cfg.get("goal", "business"),
                "interval_min": max(5, int(cfg.get("interval_min", 60) or 60)),
                "body": cfg.get("custom_goal", old.get("body", "")),
            })
            self.save_loop(brain, old)
        except Exception as e:
            print(f"[loop legacy sync] {e}", file=__import__('sys').stderr)

    def _sync_legacy_state(self, patch: dict) -> None:
        """Sau mỗi vòng của loop legacy: giữ last_* trong json cũ khớp (backup coherent)."""
        try:
            raw = self._read_legacy_raw()
            raw.update({k: patch[k] for k in ("last_run", "last_summary", "last_status") if k in patch})
            self.deps.atomic_write_text(self.config_path, json.dumps(raw, ensure_ascii=False, indent=2))
        except Exception:
            pass

    # ══════════════════════ registry: Javis/loops/<slug>.md ══════════════════════

    def _loops_dir(self, brain: str) -> Path:
        return Path(self.deps.brain_root(brain)) / "Javis" / "loops"

    def _loop_path(self, brain: str, slug: str) -> Optional[Path]:
        """Path file loop AN TOÀN theo slug tuỳ ý (kể cả stem tiếng Việt user tự đặt):
        file PHẢI nằm NGAY TRONG Javis/loops - chặn '../' traversal. None = slug không hợp lệ."""
        d = self._loops_dir(brain)
        fp = d / f"{slug}.md"
        try:
            if fp.resolve().parent != d.resolve():
                return None
        except Exception:
            return None
        return fp

    def _state_path(self, brain: str) -> Path:
        return Path(self.deps.brain_root(brain)) / "Javis" / "loop-state.json"

    def _norm_loop(self, fm: dict, body: str, stem: str) -> dict:
        # MẶC ĐỊNH 'custom' (thân file = việc loop làm mỗi vòng) - đúng "format ĐƠN GIẢN" ở
        # CLAUDE.md và khớp cả 2 đường tạo loop (plugin javis_schedule ép 'goal: custom';
        # form web /loops mặc định 'custom'). TRƯỚC ĐÂY rơi về 'business' → _build_prompt BỎ
        # HOÀN TOÀN thân file, chỉ bơm số liệu MCP: loop thiếu dòng 'goal:' (viết tay trong
        # Obsidian hay tạo bằng bản cũ) chạy sai việc - vd loop "nhắc uống thuốc" lại đi đọc
        # POS. 'business' giờ phải KHAI TƯỜNG MINH mới bật.
        goal = str(fm.get("goal", "custom") or "custom").strip().lower()
        if goal not in GOALS:
            goal = "custom"
        mode = str(fm.get("mode", "suggest") or "").strip().lower()
        if mode not in ("suggest", "auto", "full"):
            mode = "suggest"
        try:
            interval = max(5, int(fm.get("interval_min", 60)))
        except (TypeError, ValueError):
            interval = 60
        try:
            maxr = max(0, int(fm.get("max_runs_per_day", 0)))
        except (TypeError, ValueError):
            maxr = 0
        prof = "code" if str(fm.get("tools_profile", "") or "").strip().lower() == "code" else "vault-safe"
        # notify: mặc định BẬT (báo Telegram mỗi vòng cho chủ loop). Chỉ tắt khi ghi rõ false/0/no.
        notify_raw = fm.get("notify", True)
        notify = str(notify_raw).strip().lower() not in ("false", "0", "no", "off", "")
        # ambient_mcp: OPT-IN cho loop THẤY LẠI connector của máy (claude.ai: Gmail/Drive/lịch...)
        # như thời engine Popen cũ. MẶC ĐỊNH TẮT - bản fork sạch, không lộ kết nối của ai. Chỉ bật
        # khi ghi rõ true. Bật = loop chạy nhánh không-gated (nạp cấu hình máy), vẫn chặn Bash/Web/Task.
        ambient_mcp = str(fm.get("ambient_mcp", False)).strip().lower() in ("true", "1", "yes", "on")
        return {
            # identity = TÊN FILE (stem) - frontmatter slug chỉ để hiển thị, tránh lệch nhau
            "slug": stem,
            "name": str(fm.get("name") or stem),
            "enabled": bool(fm.get("enabled", False)),
            "goal": goal, "mode": mode, "interval_min": interval,
            "workspace": str(fm.get("workspace", "vault") or "vault").strip() or "vault",
            "tools_profile": prof,
            "quiet_hours": str(fm.get("quiet_hours", "") or "").strip(),
            "max_runs_per_day": maxr,
            # owner_chat = chat_id người YÊU CẦU loop (để báo về đúng người). Rỗng = web → ID đầu.
            "owner_chat": str(fm.get("owner_chat", "") or "").strip(),
            "notify": notify,
            "ambient_mcp": ambient_mcp,
            "updated": str(fm.get("updated", "") or ""),
            "body": (body or "").strip(),
        }

    def list_loops(self, brain: str) -> List[dict]:
        """Đọc mọi loop của brain. Chịu lỗi tốt: file hỏng → bỏ qua + log stderr, không crash."""
        d = self._loops_dir(brain)
        out: List[dict] = []
        if not d.is_dir():
            return out
        for fp in sorted(d.glob("*.md")):
            try:
                m = _FM_RE.match(fp.read_text(encoding="utf-8"))
                if not m:
                    print(f"[loops] bỏ qua {fp.name}: không có frontmatter", file=__import__('sys').stderr)
                    continue
                fm = fastyaml.safe_load(m.group(1))
                if not isinstance(fm, dict):
                    print(f"[loops] bỏ qua {fp.name}: frontmatter không phải mapping", file=__import__('sys').stderr)
                    continue
                out.append(self._norm_loop(fm, m.group(2), fp.stem))
            except Exception as e:
                print(f"[loops] bỏ qua {fp.name}: {type(e).__name__}: {e}", file=__import__('sys').stderr)
        return out

    def get_loop(self, brain: str, slug: str) -> Optional[dict]:
        for lp in self.list_loops(brain):
            if lp["slug"] == slug:
                return lp
        return None

    def save_loop(self, brain: str, loop: dict) -> dict:
        """Ghi file định nghĩa (server là người render frontmatter - format ổn định).
        Identity = TÊN FILE: nếu slug trỏ đúng file ĐANG CÓ (kể cả stem tiếng Việt user tự
        đặt trong Obsidian) → ghi đè CHÍNH file đó; chỉ loop MỚI mới sinh slug ascii.
        (Không thì toggle/sửa loop tên tự do sẽ fork bản sao ascii, bản gốc vẫn chạy.)"""
        raw = str(loop.get("slug") or loop.get("name") or "loop").strip()
        fp = self._loop_path(brain, raw)
        if fp is not None and fp.exists():
            slug = raw
        else:
            slug = _ascii_slug(raw)
        loop = self._norm_loop({**loop, "slug": slug}, loop.get("body", ""), slug)
        fm = {
            "type": "loop", "name": loop["name"], "slug": loop["slug"],
            "enabled": bool(loop["enabled"]), "goal": loop["goal"], "mode": loop["mode"],
            "interval_min": int(loop["interval_min"]), "workspace": loop["workspace"],
            "tools_profile": loop["tools_profile"], "quiet_hours": loop["quiet_hours"],
            "max_runs_per_day": int(loop["max_runs_per_day"]),
            "owner_chat": loop.get("owner_chat", ""), "notify": bool(loop.get("notify", True)),
            "updated": _today(),
        }
        # Chỉ ghi ambient_mcp khi BẬT - giữ file loop mặc định sạch (fork không thấy cờ lạ).
        if loop.get("ambient_mcp"):
            fm["ambient_mcp"] = True
        y = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False, width=1000).strip()
        d = self._loops_dir(brain)
        d.mkdir(parents=True, exist_ok=True)
        body = loop["body"].replace("\r\n", "\n")   # chuẩn hoá CRLF (textarea/config cũ) → file .md thuần LF
        self.deps.atomic_write_text(d / f"{slug}.md", f"---\n{y}\n---\n\n{body}\n")
        return loop

    def delete_loop(self, brain: str, slug: str) -> bool:
        fp = self._loop_path(brain, slug)   # chặn traversal: chỉ xoá file NGAY TRONG loops/
        if fp is None or not fp.exists():
            return False
        fp.unlink()
        st = self.read_state(brain)
        if slug in st:
            st.pop(slug, None)
            self._write_state(brain, st)
        return True

    def move_loop(self, from_brain: str, to_brain: str, slug: str) -> dict:
        """Dời 1 loop (file .md) sang brain khác, giữ NGUYÊN tên file + nội dung + trạng thái.

        Copy nguyên byte file (KHÔNG round-trip qua save_loop - nó chỉ render lại các field
        chuẩn nên sẽ nuốt mọi frontmatter lạ user tự thêm trong Obsidian). Định danh loop = TÊN
        FILE, nên đích đã có file cùng slug thì TỪ CHỐI, không ghi đè (2 brain có loop trùng
        slug -> đây là va chạm thật sẽ gặp). Trả {"ok":bool, "error":str}."""
        src_fp = self._loop_path(from_brain, slug)
        if src_fp is None or not src_fp.exists():
            return {"ok": False, "error": "không thấy việc ở brain nguồn"}
        dst_fp = self._loop_path(to_brain, slug)
        if dst_fp is None:
            return {"ok": False, "error": "tên việc không hợp lệ"}
        try:
            src_root = str(Path(self.deps.brain_root(from_brain)).resolve())
            dst_root = str(Path(self.deps.brain_root(to_brain)).resolve())
        except Exception:
            return {"ok": False, "error": "brain không hợp lệ"}
        if src_root == dst_root:
            return {"ok": False, "error": "brain nguồn và đích trùng nhau"}
        # Đang chạy đúng loop này -> để yên, tránh dời file dưới chân vòng đang thực thi.
        if self._running and self._running[1] == slug and self._running[0] == src_root:
            return {"ok": False, "error": "việc đang chạy, thử lại sau"}
        if dst_fp.exists():
            return {"ok": False,
                    "error": f"brain đích đã có việc '{slug}' - đổi tên hoặc xoá bên đó trước"}
        try:
            content = src_fp.read_text(encoding="utf-8")
            dst_fp.parent.mkdir(parents=True, exist_ok=True)
            self.deps.atomic_write_text(dst_fp, content)   # ghi ĐÍCH trước (mất điện = còn nguồn)
        except Exception as e:
            return {"ok": False, "error": f"ghi file đích lỗi: {type(e).__name__}: {e}"}
        # Dời entry state runtime (last_run/runs_today/fail_streak) để đích không nổ lại ngay.
        try:
            src_state = self.read_state(from_brain)
            entry = src_state.get(slug)
            if entry is not None:
                dst_state = self.read_state(to_brain)
                dst_state[slug] = entry
                self._write_state(to_brain, dst_state)
        except Exception:
            pass   # state phù du: dời không được thì đích chạy như loop mới, không sao
        self.delete_loop(from_brain, slug)   # xoá file + entry state nguồn (đích đã ghi xong)
        self.register_brain(to_brain)
        return {"ok": True}

    # ══════════════════════ state runtime: Javis/loop-state.json ══════════════════════

    def read_state(self, brain: str) -> dict:
        try:
            p = self._state_path(brain)
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {}

    def _write_state(self, brain: str, state: dict) -> None:
        try:
            self.deps.atomic_write_text(self._state_path(brain), json.dumps(state, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"[loop state write] {e}", file=__import__('sys').stderr)

    def _update_state(self, brain: str, slug: str, **patch) -> dict:
        state = self.read_state(brain)
        st = state.setdefault(slug, {})
        st.update(patch)
        self._write_state(brain, state)
        return st

    # ══════════════════════ migration 1 lần từ loop_config.json ══════════════════════

    def _mark_migrated(self, cfg: dict) -> None:
        """Đóng dấu ĐÃ MIGRATE vào loop_config.json - chạy một lần là xong VĨNH VIỄN."""
        try:
            cfg[MIGRATED_KEY] = True
            self.deps.atomic_write_text(self.config_path, json.dumps(cfg, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"[loops migrate mark] {e}", file=__import__('sys').stderr)

    def ensure_migrated(self) -> None:
        """Idempotent: loop_config.json còn nội dung THẬT của bản cũ → sinh vong-lap-goc.md
        (giữ nguyên goal/mode/interval/enabled; TOÀN BỘ custom_goal vào thân file - không mất
        quy trình Hermes). Không xoá json cũ (giữ backup).

        Hai rào chống HỒI SINH - trước đây thiếu nên "Vòng lặp tự cải thiện" mọc lại mãi:
          1. Đóng dấu MIGRATED_KEY sau lần đầu. Điều kiện cũ là "thư mục loops chưa có .md nào",
             mà người dùng XOÁ loop cuối cùng là thư mục rỗng lại → lần khởi động sau nó dựng lại,
             xoá bao nhiêu lần cũng vô ích.
          2. Config rỗng thì KHÔNG có gì để migrate. loop_config.json được register_brain() tạo ra
             chỉ để nhớ danh sách brain cho scheduler, nên bản mới hoàn toàn sạch vẫn có file này -
             và bản cũ đã dựng ra một loop trắng tên "Vòng lặp tự cải thiện" trên MỌI máy fork về.
        """
        if self._migrated:
            return
        self._migrated = True
        try:
            if not self.config_path.exists():
                return
            cfg = self._read_legacy_raw()
            if cfg.get(MIGRATED_KEY):
                return
            if not self._has_legacy_content(cfg):
                self._mark_migrated(cfg)
                return
            brain = cfg.get("brain") or "brain"
            # Vault cũ ghi trong config KHÔNG còn trên máy này (đổi máy, dọn ổ đĩa, fork sang chỗ
            # khác) → không có gì migrate một cách trung thực. Cứ migrate thì brain_root() rơi về
            # brain MẶC ĐỊNH và loop cũ mọc ra ở một brain chẳng liên quan - đúng cái "Vòng lặp tự
            # cải thiện" lạ mà người dùng thấy trong Brain Default rồi xoá mãi không hết.
            if brain != "brain" and not Path(brain).is_dir():
                print(f"[loops] bỏ qua migrate: vault cũ '{brain}' không còn trên máy này",
                      file=__import__('sys').stderr)
                self._mark_migrated(cfg)
                return
            d = self._loops_dir(brain)
            if d.is_dir() and any(d.glob("*.md")):
                self._mark_migrated(cfg)
                return
            self.save_loop(brain, {
                "slug": LEGACY_SLUG, "name": "Vòng lặp tự cải thiện",
                "enabled": bool(cfg.get("enabled")), "goal": cfg.get("goal", "business"),
                "mode": cfg.get("mode", "suggest"),
                "interval_min": cfg.get("interval_min", 60),
                "workspace": "vault", "tools_profile": "vault-safe",
                "quiet_hours": "", "max_runs_per_day": 0,
                "body": cfg.get("custom_goal", ""),
            })
            self._update_state(brain, LEGACY_SLUG,
                               last_run=float(cfg.get("last_run", 0) or 0),
                               last_summary=cfg.get("last_summary", ""),
                               last_status=cfg.get("last_status", ""),
                               runs_today=0, day="", fail_streak=0, auto_paused_reason="")
            self._mark_migrated(cfg)
            print(f"[loops] đã migrate loop_config.json → Javis/loops/{LEGACY_SLUG}.md",
                  file=__import__('sys').stderr)
        except Exception as e:
            print(f"[loops migrate] {type(e).__name__}: {e}", file=__import__('sys').stderr)

    # ══════════════════════ scheduler ══════════════════════

    def scheduler_brains(self) -> List[str]:
        """Các brain mà scheduler quét loop: legacy brain + brain đã đăng ký (khi user
        tạo/toggle loop trên brain khác) + brain mặc định. Dedup theo root đã resolve."""
        cfg = self._read_legacy_raw()
        cands = list(cfg.get("brains") or []) + [cfg.get("brain") or "brain", "brain"]
        out, seen = [], set()
        for b in cands:
            try:
                root = str(Path(self.deps.brain_root(b)).resolve())
            except Exception:
                continue
            if root in seen:
                continue
            seen.add(root)
            out.append(b)
        return out

    def register_brain(self, brain: str) -> None:
        """Ghi nhớ brain có loop để scheduler quét (gọi khi tạo/toggle/run-now)."""
        try:
            root = str(Path(self.deps.brain_root(brain)).resolve())
            cfg = self._read_legacy_raw()
            known = {str(Path(self.deps.brain_root(b)).resolve()) for b in self.scheduler_brains()}
            if root in known:
                return
            brains = list(cfg.get("brains") or [])
            brains.append(brain)
            cfg["brains"] = brains
            self.deps.atomic_write_text(self.config_path, json.dumps(cfg, ensure_ascii=False, indent=2))
        except Exception:
            pass

    def _eligible_overdue(self, loop: dict, st: dict, now_ts: float, hour: int) -> Optional[float]:
        """None = không đủ điều kiện; số >= 0 = đã quá hạn bấy nhiêu giây."""
        if not loop["enabled"] or st.get("auto_paused_reason"):
            return None
        if _in_quiet_hours(loop["quiet_hours"], hour):
            return None
        if loop["max_runs_per_day"] > 0:
            runs = int(st.get("runs_today", 0)) if st.get("day") == _today() else 0
            if runs >= loop["max_runs_per_day"]:
                return None
        overdue = now_ts - float(st.get("last_run", 0)) - loop["interval_min"] * 60
        return overdue if overdue >= 0 else None

    def _pick_due(self) -> Optional[Tuple[str, dict]]:
        now, hour = time.time(), _now_vn().hour
        best = None
        for brain in self.scheduler_brains():
            try:
                loops = self.list_loops(brain)
                if not loops:
                    continue
                st_all = self.read_state(brain)
            except Exception:
                continue
            for lp in loops:
                ov = self._eligible_overdue(lp, st_all.get(lp["slug"], {}), now, hour)
                if ov is not None and (best is None or ov > best[2]):
                    best = (brain, lp, ov)
        return (best[0], best[1]) if best else None

    async def tick(self) -> None:
        """Scheduler gọi mỗi ~30s: chọn TỐI ĐA 1 loop quá hạn lâu nhất rồi chạy (tuần tự)."""
        self.ensure_migrated()
        if self.lock.locked():
            return
        target = self._pick_due()
        if target:
            await self.run_cycle(target[0], target[1]["slug"], "scheduled")

    async def run_due(self, reason: str = "scheduled") -> dict:
        """Shim run_loop_cycle của main.py: chạy loop đến hạn nhất (nếu có)."""
        self.ensure_migrated()
        if self.lock.locked():
            return {"ok": False, "error": "Đang chạy một vòng khác"}
        target = self._pick_due()
        if not target:
            return {"ok": True, "summary": "Không có loop nào đến hạn."}
        return await self.run_cycle(target[0], target[1]["slug"], reason)

    # ══════════════════════ log ══════════════════════

    def _log_append(self, brain: str, entry: dict) -> None:
        try:
            d = Path(self.deps.brain_root(brain)) / "Javis" / "loop-log"
            d.mkdir(parents=True, exist_ok=True)
            now = _now_vn()
            with open(d / f"{now.strftime('%Y-%m-%d')}.md", "a", encoding="utf-8") as fh:
                fh.write(f"\n## [{now.strftime('%Y-%m-%d %H:%M')}] {entry['title']}\n{entry['body']}\n")
        except Exception as e:
            print(f"[loop log] {e}", file=__import__('sys').stderr)

    def _read_log_entries(self, brain: str, slug: str = "", limit: int = 10) -> List[str]:
        d = Path(self.deps.brain_root(brain)) / "Javis" / "loop-log"
        entries: List[str] = []
        if d.is_dir():
            # Đọc file mới nhất trước; trong mỗi file entry mới nằm DƯỚI (ghi nối) nên đảo lại để
            # nhật ký xếp MỚI NHẤT TRƯỚC. Đọc tiếp file cho tới khi gom đủ 'limit' (dashboard phân
            # trang nên có thể xin nhiều), thay vì cứng 3 file như trước.
            for f in sorted(d.glob("*.md"), reverse=True):
                if len(entries) >= limit:
                    break
                try:
                    txt = f.read_text(encoding="utf-8")
                except Exception:
                    continue
                chunks: List[str] = []
                for chunk in re.split(r"(?=^## \[)", txt, flags=re.MULTILINE):
                    chunk = chunk.strip()
                    if not chunk.startswith("## ["):
                        continue
                    # entry mới có "] <slug> · loop (...)"; entry cũ (trước multi-loop) không slug
                    if slug and f"] {slug} · " not in chunk.split("\n", 1)[0]:
                        continue
                    chunks.append(chunk)
                entries.extend(reversed(chunks))
        return entries[:limit]

    # ══════════════════════ 1 vòng (giữ khung 4 bước bản gốc) ══════════════════════

    async def _build_prompt(self, loop: dict) -> Tuple[str, str]:
        """Trả (prompt, skip_reason). skip_reason != '' → bỏ qua vòng này (vd business chưa có số)."""
        goal, mode = loop["goal"], loop["mode"]
        is_write = mode in ("auto", "full")   # auto/full = được ghi; suggest = chỉ đọc
        # Chỉ dẫn an toàn theo mode: full = toàn quyền; còn lại = đọc MCP nhưng cấm tiền/đơn.
        if loop["tools_profile"] == "code":
            safety = ("⛔ AN TOÀN: KHÔNG gọi MCP/tiền/đơn/đăng bài. Chỉ thao tác file trong workspace được giao.\n")
        else:
            safety = _MCP_FULL if mode == "full" else _MCP_SAFETY
        if goal == "business":
            # Trước đây vòng này mồi sẵn số liệu từ job thẻ dashboard (/metrics). Job đó đã gỡ
            # vì tự spawn agent kèm MCP mỗi lần mở dashboard, tốn hạn mức cho một bảng không ai
            # xem. Giờ loop tự lấy số qua MCP ngay trong vòng - đúng nguồn, đúng lúc cần.
            base = (
                "VÒNG TỰ CẢI THIỆN - MỤC TIÊU: CẢI THIỆN CHỈ SỐ KINH DOANH.\n"
                "BƯỚC 1 - lấy số thật: xem các MCP đang kết nối rồi lấy 3-6 chỉ số kinh doanh quan trọng nhất "
                "của kỳ hiện tại, có so kỳ trước nếu lấy được. Ưu tiên nguồn theo thứ tự: Pancake POS (tool pos_*) "
                "→ kênh bán / mạng xã hội → quảng cáo → bất kỳ nguồn kinh doanh nào khác. Dùng số THẬT, KHÔNG bịa. "
                "Nếu KHÔNG có nguồn kinh doanh nào đang đấu thì dừng vòng và báo đúng một câu là chưa có nguồn dữ liệu.\n"
                "BƯỚC 2 - phân tích: "
                "Đọc thêm context trong vault (Wiki marketing/sales/funnel/content, data cache, projects) để hiểu bối cảnh. "
                "Xác định CHỈ SỐ YẾU NHẤT hoặc đòn bẩy lớn nhất, rồi đề ra 1 hành động khả thi TUẦN NÀY để cải thiện nó "
                "(vd: ý tưởng + caption content nháp, khung email, kịch bản khuyến mãi, điểm tối ưu funnel, danh sách lead cần gọi lại).\n"
                "Báo cáo phải NÊU RÕ các con số đã lấy được ở bước 1, kèm nguồn.\n"
                + safety
            )
            if is_write:
                return base + (
                    "GHI kết quả vào vault: tạo/cập nhật 1 note kế hoạch trong '05 - Projects' (đặt tên rõ, vd "
                    "'Cải thiện [chỉ số] - <ngày>'), kèm vật liệu nháp. Nếu cần hành động → thêm task vào Daily Log hôm nay.\n"
                    "Báo cáo NGẮN: nhắm chỉ số nào, hành động gì, đã ghi file nào."
                ), ""
            return base + (
                "CHẾ ĐỘ ĐỀ XUẤT - chỉ phân tích, KHÔNG ghi file. Nêu chỉ số yếu nhất + 2-3 đề xuất hành động cụ thể để cải thiện."
            ), ""
        if goal == "product":
            base = (
                "MỤC TIÊU: TỰ CẢI THIỆN JAVIS hữu dụng hơn với người dùng.\n"
                "Đọc log hội thoại gần đây (Memory/conversations) + các agent/workflow trong Javis/ + ghi chú phản hồi. "
                "Nhận diện: người dùng hay vướng gì, yêu cầu lặp lại gì, thiếu agent/workflow/skill nào, chỗ nào gây khó. "
                "KHÔNG sửa code server.\n"
                + safety
            )
            if is_write:
                return base + (
                    "Thực hiện 1 cải tiến cụ thể: tạo/cải thiện 1 agent hoặc workflow trong Javis/ (đúng format frontmatter), "
                    "hoặc ghi 1 note đề xuất cải tiến UX/tính năng vào '05 - Projects'. Báo cáo NGẮN: cải tiến gì, file nào, vì sao."
                ), ""
            return base + (
                "CHẾ ĐỘ ĐỀ XUẤT - chỉ đọc, không ghi. Liệt kê 3-5 cải tiến giá trị nhất để Javis hữu dụng hơn (mỗi cái 1 dòng + lý do)."
            ), ""
        if goal == "custom":
            objective = (loop.get("body") or "").strip() or "Cải thiện vault theo cách hữu ích nhất bạn thấy."
            base = f"NHIỆM VỤ CỦA LOOP NÀY (làm ĐÚNG 1 lần mỗi vòng rồi dừng):\n{objective}\n{safety}"
            return base + ("Thực hiện 1 bước cụ thể cho nhiệm vụ trên rồi báo cáo ngắn (làm gì, chạm file nào)." if is_write
                           else "CHẾ ĐỘ ĐỀ XUẤT - chỉ đọc, không ghi file. Đề xuất 2-3 hành động cụ thể cho nhiệm vụ trên."), ""
        # goal == brain - làm dày bộ não
        if is_write:
            return (
                "VÒNG TỰ CẢI THIỆN (làm dày bộ não, chế độ TỰ LÀM).\n"
                "Chọn ĐÚNG 1 việc giá trị nhất: (1) INGEST 1 source unprocessed, (2) trả lời 1 _open-question, "
                "(3) sửa 1 lỗi Wiki (broken link/thiếu citation/orphan/trùng). TUÂN THỦ quy ước CLAUDE.md + cập nhật index.md & log.md.\n"
                + safety +
                "Báo cáo NGẮN: làm gì, chạm file nào. Nếu không có việc → 'Không có việc mới'."
            ), ""
        return (
            "VÒNG TỰ CẢI THIỆN (làm dày bộ não, chế độ ĐỀ XUẤT - chỉ đọc).\n"
            "Quét vault, liệt kê 3-5 việc giá trị nhất: source unprocessed, _open-questions mở, lỗi Wiki, task quá hạn. "
            "Mỗi việc 1 dòng '- [loại] mô tả → hành động'. Không có gì → 'Không có việc mới'."
        ), ""

    def _make_cli(self, loop: dict, cwd: str, sysprompt: Optional[str], for_verify: bool = False,
                  brain: str = ""):
        """Dựng CLI cho 1 vòng loop.
        - profile 'code' (nâng cao, chỉ đặt qua .md): Bash/Web + file, cwd=workspace, VẪN 0 MCP
          (fail-closed nếu không tạo được file MCP rỗng) - cho loop sửa mã repo.
        - MẶC ĐỊNH (mọi loop tạo qua form): file tools + MCP do Javis quản lý (POS/ads/lịch...).
          Loop ĐỌC được dữ liệu thật; ghi allowlist kèm 'mcp__<server>' để tool MCP gọi được.
          An toàn tiền/đơn dựa vào: (a) deny_tools per-server (apply_mcp gắn --disallowedTools),
          (b) chỉ dẫn cứng trong prompt, (c) mode suggest = chỉ tool đọc.
        - mode 'full' (TOÀN QUYỀN, chủ chủ động bật + đã đọc cảnh báo): allowlist = None
          → MỌI tool (file + Bash/Web + mọi tool MCP, trừ deny_tools per-server) để tự thao
          tác thật. Bước KIỂM CHỨNG (for_verify) LUÔN chạy readonly, không nới quyền."""
        mode = loop["mode"]
        if loop["tools_profile"] == "code":
            mcpf = _empty_mcp_file()
            if not mcpf:
                return None   # không có file MCP rỗng → Bash + MCP ambient quá nguy hiểm, từ chối
            if for_verify:
                tools = list(self.deps.readonly_tools) + ["Bash"]   # Bash để chạy py_compile / node --check
            else:
                base = self.deps.safe_tools if mode in ("auto", "full") else self.deps.readonly_tools
                tools = list(base) + ["Bash", "WebFetch", "WebSearch"]
            cli = claude_engine(system_prompt=sysprompt, cwd=cwd, tag="loop", allowed_tools=tools)
            cli.mcp_config = mcpf
            cli.mcp_strict = True
            cli.disallowed_tools = ["Task"]
        elif mode == "full" and not for_verify:
            # TOÀN QUYỀN: không giới hạn allowlist → mọi tool + mọi MCP. Vẫn tôn trọng
            # deny_tools per-server (apply_mcp đặt --disallowedTools) - chặn user đã chủ ý.
            cli = claude_engine(system_prompt=sysprompt, cwd=cwd, tag="loop", allowed_tools=None)
            if self.deps.apply_mcp:
                # allowed_tools=None ở NHÁNH NÀY = ungated = plugin in-process CÓ nạp
                # (claude_sdk_engine._mcp_servers: allowed_tools rỗng mới gọi _plugins_server()).
                # PHẢI truyền brain để cli.javis_vault đúng brain đang chạy - thiếu brain thì
                # plugin (vd javis_generate_image) không suy được vault, rơi về Brain Default.
                try:
                    self.deps.apply_mcp(cli, mode="full", brain=brain)   # hub nhận mode qua header X-Javis-Mode
                except TypeError:
                    self.deps.apply_mcp(cli)
            # KHÔNG _isolate: full mode chủ đích mở MCP + Bash. Không có apply_mcp (test) → vẫn None allowlist.
        elif loop.get("ambient_mcp") and not for_verify:
            # OPT-IN (frontmatter ambient_mcp: true, mode suggest/auto): loop THẤY LẠI connector
            # của máy (claude.ai: Gmail/Drive/lịch) như bản Popen cũ. Dùng nhánh KHÔNG gated
            # (allowed_tools=None) → engine SDK nạp setting_sources → connector ambient xuất hiện.
            # An toàn giữ nguyên: chặn CỨNG Bash/Web/Task; tool tiền/đơn đi qua hub vẫn khoá theo
            # mode (suggest = chỉ đọc). Connector gọi TRỰC TIẾP (ngoài hub) dựa vào kỷ luật prompt
            # như bản cũ - đây là đánh đổi user CHỦ ĐỘNG bật, không phải mặc định.
            cli = claude_engine(system_prompt=sysprompt, cwd=cwd, tag="loop", allowed_tools=None)
            if self.deps.apply_mcp:
                # Cũng ungated (allowed_tools=None) như nhánh full ở trên - PHẢI truyền brain
                # cùng lý do (plugin in-process cần javis_vault đúng).
                hub_mode = "auto" if mode == "auto" else "suggest"
                try:
                    self.deps.apply_mcp(cli, mode=hub_mode, brain=brain)
                except TypeError:
                    self.deps.apply_mcp(cli)
            base_deny = ["Bash", "WebFetch", "WebSearch", "Task"]
            cur = list(cli.disallowed_tools or [])
            cli.disallowed_tools = base_deny + [d for d in cur if d not in base_deny]
        else:
            base = self.deps.readonly_tools if for_verify else (
                self.deps.safe_tools if mode in ("auto", "full") else self.deps.readonly_tools)
            tools = list(base)
            # Thêm pattern MCP vào allowlist để loop GỌI được tool MCP (Bash/Web/Task vẫn ngoài list → chặn)
            if self.deps.mcp_allow_patterns:
                try:
                    tools += list(self.deps.mcp_allow_patterns() or [])
                except Exception:
                    pass
            cli = claude_engine(system_prompt=sysprompt, cwd=cwd, tag="loop", allowed_tools=tools)
            if self.deps.apply_mcp:
                # Hub ENFORCE quyền theo mode: suggest → chỉ đọc, auto → chặn danger (lớp cứng,
                # cộng thêm allowlist + prompt sẵn có). for_verify luôn coi như suggest.
                # Nhánh này GATED (allowed_tools=tools) nên plugin in-process KHÔNG nạp (_mcp_servers
                # trả sớm khi allowed_tools có giá trị) - truyền brain vẫn AN TOÀN + nhất quán,
                # phòng trường hợp allowlist sau này mở thêm pattern plugin.
                hub_mode = "suggest" if (for_verify or mode not in ("auto",)) else "auto"
                try:
                    self.deps.apply_mcp(cli, mode=hub_mode, brain=brain)
                except TypeError:
                    self.deps.apply_mcp(cli)   # deps cũ (test) không nhận mode
            else:
                _isolate(cli)              # không có hook (vd unit test) → giữ 0-MCP như cũ
        cli = aux_engine.apply(self.deps, cli, mode=("suggest" if for_verify else mode), tag="loop")
        return cli

    async def run_cycle(self, brain: str, slug: str, reason: str = "manual") -> dict:
        """1 vòng của 1 loop: dựng prompt theo goal → chạy CLI cô lập → (mode auto) kiểm chứng
        độc lập 'giả định SAI' → ghi log + cập nhật state. Giữ nguyên khung bản gốc."""
        if self.lock.locked():
            return {"ok": False, "error": "Đang chạy một vòng khác"}
        async with self.lock:
            loop = self.get_loop(brain, slug)
            if not loop:
                return {"ok": False, "error": f"Không tìm thấy loop '{slug}'"}
            self._running = (str(Path(self.deps.brain_root(brain)).resolve()), slug)
            try:
                return await self._run_cycle_inner(brain, slug, loop, reason)
            finally:
                self._running = None

    async def _run_cycle_inner(self, brain: str, slug: str, loop: dict, reason: str) -> dict:
        vault_root = self.deps.brain_root(brain)
        goal, mode = loop["goal"], loop["mode"]
        today = _today()

        # Run now thủ công = user chủ động → xoá auto-pause + reset chuỗi lỗi
        st0 = self.read_state(brain).get(slug, {})
        if reason == "manual" and (st0.get("auto_paused_reason") or st0.get("fail_streak")):
            self._update_state(brain, slug, auto_paused_reason="", fail_streak=0)

        def _finish(summary: str, verify_line: str, failed: bool) -> dict:
            st = self.read_state(brain).get(slug, {})
            runs = (int(st.get("runs_today", 0)) if st.get("day") == today else 0) + 1
            streak = (int(st.get("fail_streak", 0)) + 1) if failed else 0
            patch = {
                "last_run": time.time(), "last_summary": summary[:1000],
                "last_status": verify_line or ("lỗi" if failed else "ok"),
                "runs_today": runs, "day": today, "fail_streak": streak,
            }
            paused_now = False
            if streak >= 3 and not st.get("auto_paused_reason"):
                patch["auto_paused_reason"] = (f"Tự tạm dừng {_now_vn().strftime('%d/%m %H:%M')}: "
                                               "3 lần lỗi/kiểm chứng không đạt liên tiếp")
                paused_now = True
            self._update_state(brain, slug, **patch)
            if slug == LEGACY_SLUG:
                self._sync_legacy_state(patch)
            title = f"{slug} · loop ({goal}/{mode}) - {reason}"
            body = summary + (f"\n\n**Kiểm chứng:** {verify_line}" if verify_line else "")
            if paused_now:
                body += f"\n\n⚠ **{patch['auto_paused_reason']}** - bật lại hoặc bấm Chạy ngay để tiếp tục."
            self._log_append(brain, {"title": title, "body": body})
            # BÁO CÁO mỗi vòng cho NGƯỜI YÊU CẦU loop (mặc định của Javis; đặt notify: false
            # trong frontmatter để tắt loop nào quá ồn). owner_chat rỗng (loop tạo trên web) →
            # helper report tự gửi ID Telegram đầu tiên.
            report_sent = False
            if loop.get("notify", True) and self.deps.report:
                head = "⚠" if failed else "✅"
                parts = [f"{head} Loop '{loop['name']}' vừa chạy ({reason})."]
                if summary:
                    parts.append(summary[:1500])
                if verify_line:
                    parts.append("Kiểm chứng: " + verify_line)
                if paused_now:
                    parts.append("⚠ " + patch["auto_paused_reason"] + " - bật lại hoặc bấm Chạy ngay để tiếp tục.")
                try:
                    # Telegram là kênh chữ thuần: lọc khối JAVIS_METRICS/JAVIS_ASK trước khi báo,
                    # kẻo lộ nguyên cụm "<!-- JAVIS_...: ... -->" (system prompt loop dùng chung
                    # CLAUDE.md nên có thể sinh các khối này).
                    asyncio.create_task(self.deps.report(
                        loop.get("owner_chat", ""),
                        channel_context.strip_control_blocks("\n\n".join(parts))))
                    report_sent = True
                except Exception:
                    pass
            # Auto-pause: broadcast tới MỌI admin (sự kiện an toàn hiếm). Bỏ nếu báo-mỗi-vòng đã
            # gửi chủ loop rồi (tránh nhắn trùng ở setup 1 người dùng).
            if paused_now and self.deps.notify and not report_sent:
                try:
                    asyncio.create_task(self.deps.notify(
                        f"⚠ Loop '{loop['name']}' ({slug}) đã tự tạm dừng sau 3 lần lỗi liên tiếp. "
                        "Mở trang Việc định kỳ để xem log."))
                except Exception:
                    pass
            return {"ok": not failed, "summary": summary, "verify": verify_line,
                    "auto_paused": bool(patch.get("auto_paused_reason") or (st.get("auto_paused_reason") and not paused_now))}

        # Workspace: vault (mặc định) | đường dẫn tuyệt đối (loop code)
        if loop["workspace"] and loop["workspace"] != "vault":
            ws = Path(loop["workspace"])
            if not ws.is_dir():
                return _finish(f"Lỗi: workspace '{loop['workspace']}' không tồn tại", "", True)
            cwd = str(ws)
        else:
            cwd = vault_root

        prompt, skip = await self._build_prompt(loop)
        if skip:
            self._log_append(brain, {"title": f"{slug} · loop ({goal}/{mode}) - {reason}", "body": skip})
            # KHÔNG ghi day (skip không tiêu quota ngày): ghi day mà không reset runs_today
            # sẽ gán số đếm hôm QUA cho hôm nay → chặn nhầm max_runs_per_day cả ngày.
            self._update_state(brain, slug, last_run=time.time(), last_summary=skip[:200],
                               last_status="no-data")
            return {"ok": True, "summary": skip}

        sysprompt = self.deps.build_system_prompt(brain)
        gcli = self._make_cli(loop, cwd, sysprompt, brain=brain)
        if gcli is None:
            return _finish("Lỗi: không tạo được file MCP rỗng để cô lập (profile code từ chối chạy)", "", True)
        if not gcli.is_available():
            return {"ok": False, "error": "Claude CLI chưa cài"}
        summary = ""
        async for ev in gcli.query(prompt):
            if ev["type"] == "final":
                summary = ev.get("content", "") or summary
            elif ev["type"] == "error":
                summary = "Lỗi: " + ev["content"][:200]

        verify_line, verify_failed = "", False
        if mode in ("auto", "full") and summary and not summary.startswith("Lỗi:") \
                and "không có việc mới" not in summary.lower():
            # Kiểm chứng độc lập: giả định kết quả SAI, kiểm tra thực tế
            vcli = self._make_cli(loop, cwd, "Bạn là người KIỂM CHỨNG độc lập, giả định kết quả vừa rồi SAI.",
                                  for_verify=True, brain=brain)
            if vcli is not None:
                if loop["tools_profile"] == "code":
                    criteria = ("thay đổi có đúng mục tiêu không, diff có NHỎ không (dưới ~80 dòng), có phá API hiện có "
                                "không; BẮT BUỘC chạy `python -m py_compile <file .py đã sửa>` và `node --check "
                                "<file .js đã sửa>` cho từng file bị đổi - tất cả phải sạch mới được pass")
                elif goal == "business":
                    criteria = ("đề xuất/hành động có BÁM số liệu thật không, có khả thi/đủ cụ thể không, có bịa số không")
                elif goal == "brain":
                    criteria = "thay đổi có đúng quy ước Wiki không, có bịa/thiếu citation không, có làm hỏng link không"
                else:
                    criteria = "kết quả có đúng mục tiêu không, có hợp lý/khả thi không, có bịa hay làm hỏng file nào không"
                # mode full = chủ cho toàn quyền → CHỈ kiểm 'đúng phạm vi', KHÔNG fail vì có hành động ghi ra ngoài.
                if mode == "full":
                    criteria += ("; đây là loop TOÀN QUYỀN nên hành động thật ra ngoài LÀ ĐƯỢC PHÉP - chỉ FAIL nếu "
                                 "làm SAI/QUÁ phạm vi nhiệm vụ, gây hại rõ ràng, hoặc thao tác thứ ngoài ý định")
                elif loop["tools_profile"] != "code":
                    criteria += ("; và TUYỆT ĐỐI KHÔNG có hành động tiền/đơn/quảng cáo/đăng bài/gửi tin qua MCP "
                                 "(chỉ được đọc dữ liệu) - nếu có thì FAIL ngay")
                vprompt = (
                    "Một vòng tự cải thiện vừa chạy. Kết quả của nó:\n" + summary + "\n\n"
                    f"Kiểm tra thực tế (đọc lại file liên quan): {criteria}. "
                    'CHỈ trả JSON 1 dòng: {"pass":true|false,"reason":"ngắn gọn"}.'
                )
                v_out = ""
                async for ev in vcli.query(vprompt):
                    if ev["type"] == "final":
                        v_out = ev.get("content", "") or v_out
                vm = re.search(r"\{.*\}", v_out, re.DOTALL)
                if vm:
                    try:
                        vj = json.loads(vm.group(0))
                        verify_failed = not vj.get("pass")
                        verify_line = ("✓ Đạt" if vj.get("pass") else "✗ Chưa đạt") + ": " + str(vj.get("reason", ""))
                    except json.JSONDecodeError:
                        verify_line = "Kiểm chứng: không parse được"

        failed = (not summary) or summary.startswith("Lỗi:") or verify_failed
        return _finish(summary or "Lỗi: fork không phản hồi", verify_line, failed)

    # ══════════════════════ helpers cho API/automations ══════════════════════

    def loop_view(self, brain: str, lp: dict, st_all: Optional[dict] = None) -> dict:
        """Định nghĩa + state + next_run + running - cho GET /loops và tab Lịch."""
        st = (st_all if st_all is not None else self.read_state(brain)).get(lp["slug"], {})
        today = _today()
        last_run = float(st.get("last_run", 0))
        running = bool(self._running and self._running[1] == lp["slug"]
                       and self._running[0] == str(Path(self.deps.brain_root(brain)).resolve()))
        return {
            **lp,
            "last_run": last_run,
            "last_summary": st.get("last_summary", ""),
            "last_status": st.get("last_status", ""),
            "runs_today": int(st.get("runs_today", 0)) if st.get("day") == today else 0,
            "fail_streak": int(st.get("fail_streak", 0)),
            "auto_paused_reason": st.get("auto_paused_reason", ""),
            "next_run": (last_run + lp["interval_min"] * 60) if (lp["enabled"] and not st.get("auto_paused_reason")) else 0,
            "running": running,
        }

    def toggle(self, brain: str, slug: str) -> Optional[dict]:
        lp = self.get_loop(brain, slug)
        if not lp:
            return None
        lp["enabled"] = not lp["enabled"]
        if lp["enabled"]:   # bật lại = user chủ động → xoá auto-pause
            self._update_state(brain, slug, auto_paused_reason="", fail_streak=0)
        self.save_loop(brain, lp)
        self.register_brain(brain)
        return lp

    # ══════════════════════ API router ══════════════════════

    def _make_router(self) -> APIRouter:
        router = APIRouter()

        # ---------- API mới /loops/* ----------

        @router.get("/loops")
        async def loops_list(brain: str = Query("brain")):
            self.ensure_migrated()
            st_all = self.read_state(brain)
            loops = [self.loop_view(brain, lp, st_all) for lp in self.list_loops(brain)]
            if loops:
                # brain có loop (kể cả loop do CHAT ghi file trực tiếp) → đăng ký cho scheduler
                self.register_brain(brain)
            return {"loops": loops, "running": self.lock.locked(),
                    "running_slug": self._running[1] if self._running else ""}

        @router.post("/loops")
        async def loops_save(
            name: str = Form(...), slug: str = Form(""), enabled: str = Form(None),
            goal: str = Form(None), mode: str = Form("suggest"), interval_min: str = Form("60"),
            workspace: str = Form(None), tools_profile: str = Form(None),
            quiet_hours: str = Form(None), max_runs_per_day: str = Form(None),
            owner_chat: str = Form(None), notify: str = Form(None),
            body: str = Form(""), brain: str = Form("brain"),
        ):
            self.ensure_migrated()
            if mode not in ("suggest", "auto", "full"):
                return {"ok": False, "error": "mode phải là suggest, auto hoặc full"}
            # Tra loop cũ theo slug NGUYÊN VĂN trước (stem tự do, vd tiếng Việt user tự đặt),
            # rồi mới thử bản ascii - để "Sửa" ghi đè đúng file gốc thay vì fork bản sao.
            raw = (slug or name).strip()
            old = self.get_loop(brain, raw) or self.get_loop(brain, _ascii_slug(raw))
            s = old["slug"] if old else _ascii_slug(raw)
            # Form đơn giản (Tên + Mô tả) KHÔNG gửi goal/workspace/tools_profile/quiet/maxruns →
            # giữ giá trị loop cũ (sửa), hoặc mặc định an toàn (tạo mới: goal=custom = freeform).
            goal = goal or (old["goal"] if old else "custom")
            if goal not in GOALS:
                return {"ok": False, "error": f"goal phải là 1 trong {'/'.join(GOALS)}"}
            tools_profile = tools_profile or (old["tools_profile"] if old else "vault-safe")
            if tools_profile not in ("vault-safe", "code"):
                return {"ok": False, "error": "tools_profile phải là vault-safe hoặc code"}
            workspace = workspace if workspace is not None else (old["workspace"] if old else "vault")
            ws = (workspace or "vault").strip() or "vault"
            if ws != "vault" and not Path(ws).is_dir():
                return {"ok": False, "error": f"workspace '{ws}' không tồn tại"}
            if quiet_hours is None:
                quiet_hours = old["quiet_hours"] if old else ""
            if max_runs_per_day is None:
                max_runs_per_day = str(old["max_runs_per_day"]) if old else "0"
            try:
                iv = max(5, int(interval_min or 60))
            except ValueError:
                iv = 60
            try:
                mr = max(0, int(max_runs_per_day or 0))
            except ValueError:
                mr = 0
            en = (enabled in ("1", "true", "True", "on")) if enabled is not None \
                else bool(old and old["enabled"])
            # owner_chat: web KHÔNG gửi → giữ của loop cũ, hoặc rỗng (→ báo ID Telegram đầu tiên).
            oc = owner_chat if owner_chat is not None else (old["owner_chat"] if old else "")
            nf = (notify in ("1", "true", "True", "on", "yes")) if notify is not None \
                else (bool(old["notify"]) if old else True)
            loop = self.save_loop(brain, {
                "slug": s, "name": name.strip() or s, "enabled": en, "goal": goal, "mode": mode,
                "interval_min": iv, "workspace": ws, "tools_profile": tools_profile,
                "quiet_hours": quiet_hours.strip(), "max_runs_per_day": mr,
                "owner_chat": (oc or "").strip(), "notify": nf, "body": body,
            })
            self.register_brain(brain)
            return {"ok": True, "loop": self.loop_view(brain, loop)}

        @router.post("/loops/toggle")
        async def loops_toggle(slug: str = Form(...), brain: str = Form("brain")):
            self.ensure_migrated()
            lp = self.toggle(brain, slug)
            if not lp:
                return {"ok": False, "error": "not found"}
            return {"ok": True, "enabled": lp["enabled"],
                    "status": "active" if lp["enabled"] else "paused"}

        @router.post("/loops/delete")
        async def loops_delete(slug: str = Form(...), brain: str = Form("brain")):
            if not self.delete_loop(brain, slug):
                return {"ok": False, "error": "not found"}
            return {"ok": True}

        @router.post("/loops/move")
        async def loops_move(slug: str = Form(...), from_brain: str = Form(...),
                             to_brain: str = Form(...)):
            self.ensure_migrated()
            return self.move_loop(from_brain, to_brain, slug)

        @router.post("/loops/run-now")
        async def loops_run_now(slug: str = Form(...), brain: str = Form("brain")):
            if self.lock.locked():
                return {"ok": False, "error": "Đang chạy một vòng khác"}
            if not self.get_loop(brain, slug):
                return {"ok": False, "error": "not found"}
            self.register_brain(brain)
            asyncio.create_task(self.run_cycle(brain, slug, "manual"))
            return {"ok": True, "started": True}

        @router.get("/loops/log")
        async def loops_log(brain: str = Query("brain"), slug: str = Query(""), limit: int = Query(10)):
            return {"entries": self._read_log_entries(brain, slug, limit),
                    "running": self.lock.locked(),
                    "running_slug": self._running[1] if self._running else ""}

        @router.post("/loops/stop")
        async def loops_stop():
            return {"ok": True, "cancelled": cancel_all("loop")}

        # ---------- Shim /loop/* cũ (trỏ về loop legacy vong-lap-goc) ----------

        @router.get("/loop/config")
        async def loop_config_get():
            self.ensure_migrated()
            cfg = self.read_config()
            nxt = cfg["last_run"] + max(5, int(cfg.get("interval_min", 60))) * 60 if cfg.get("enabled") else 0
            cfg["next_run"] = nxt
            cfg["running"] = self.lock.locked()
            return cfg

        @router.post("/loop/config")
        async def loop_config_set(
            enabled: str = Form(None), mode: str = Form(None), goal: str = Form(None),
            interval_min: str = Form(None), brain: str = Form(None), custom_goal: str = Form(None),
        ):
            cfg = self.read_config()
            if custom_goal is not None:
                cfg["custom_goal"] = custom_goal
            if enabled is not None:
                cfg["enabled"] = enabled in ("1", "true", "True", "on")
            if mode in ("suggest", "auto", "full"):
                cfg["mode"] = mode
            if goal in GOALS:
                cfg["goal"] = goal
            if interval_min is not None:
                try:
                    cfg["interval_min"] = max(5, int(interval_min))
                except ValueError:
                    pass
            if brain:
                cfg["brain"] = brain
            self.write_config(cfg)
            return {"ok": True, "config": cfg}

        @router.post("/loop/run-now")
        async def loop_run_now():
            if self.lock.locked():
                return {"ok": False, "error": "Đang chạy"}
            self.ensure_migrated()
            brain = self._read_legacy_raw().get("brain") or "brain"
            if not self.get_loop(brain, LEGACY_SLUG):
                return {"ok": False, "error": f"Chưa có loop {LEGACY_SLUG}"}
            asyncio.create_task(self.run_cycle(brain, LEGACY_SLUG, "manual"))
            return {"ok": True, "started": True}

        @router.post("/loop/stop")
        async def loop_stop():
            return {"ok": True, "cancelled": cancel_all("loop")}

        @router.get("/loop/log")
        async def loop_log(brain: str = Query("brain"), limit: int = Query(10)):
            return {"entries": self._read_log_entries(brain, "", limit), "running": self.lock.locked()}

        return router


def register(app, deps: LoopDeps) -> LoopFeature:
    """Tạo LoopFeature, gắn router /loops/* + shim /loop/* vào app, trả feature cho main giữ shim."""
    feat = LoopFeature(deps)
    app.include_router(feat.router)
    return feat
