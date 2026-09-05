"""
Hạ tầng engine CLI: factory claude_engine() (engine Claude - chạy qua claude_sdk_engine),
CodexCLI (ChatGPT subscription, spawn `codex exec` bằng Popen + thread cho tương thích mọi
event loop Windows), auth Claude Code, registry ngắt tiến trình theo tag.
Nhánh ClaudeCLI Popen cũ đã gỡ ở v0.9.37 (engine Claude giờ luôn đi qua Agent SDK -
kế hoạch + nhật ký: docs/dev/2026-07-ke-hoach-agent-sdk.md).
"""
import asyncio
import json
import os
import re
import sys
import shutil
import subprocess
import threading
import time
import traceback
from pathlib import Path
from typing import AsyncIterator, Optional

# Chỉ để dùng strip_provider_markers. engine KHÔNG import ngược claude_cli nên không có vòng.
import engine


# Registry các tiến trình Claude đang chạy - để ngắt giữa chừng.
# Map proc -> tag ("chat" | "metrics" | "workflow" | "loop" | ...) để ngắt CÓ CHỌN LỌC.
_ACTIVE_PROCS = {}
_PROC_LOCK = threading.Lock()


def _looks_like_codex_resume_error(message: str) -> bool:
    """Nhận diện lỗi rollout/thread không còn để caller bootstrap từ SQLite đúng một lần."""
    s = (message or "").lower()
    subject = any(x in s for x in ("resume", "session", "thread", "rollout"))
    failure = any(x in s for x in (
        "not found", "does not exist", "could not find", "failed to load",
        "failed to resume", "unable to resume", "invalid session", "no session",
    ))
    return subject and failure


def cancel_all(tag=None):
    """Ngắt tiến trình Claude. tag=None → tất cả; có tag → ngắt nhóm khớp.
    Khớp theo HỌ tag: 'chat' ngắt cả 'chat:abc' (tag đa phiên per-kết-nối/per-chat_id);
    'chat:abc' chỉ ngắt đúng phiên đó. Tương tự 'telegram' vs 'telegram:<chat_id>'.
    Ngắt CẢ hai engine: subprocess CLI (Popen) lẫn phiên Agent SDK đang chạy."""
    with _PROC_LOCK:
        procs = [p for p, t in _ACTIVE_PROCS.items()
                 if tag is None or t == tag or str(t).startswith(str(tag) + ":")]
    for p in procs:
        try:
            if os.name == "nt":
                # Kill cả cây tiến trình (claude spawn node con)
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                p.terminate()
        except Exception:
            pass
    n = len(procs)
    try:
        import claude_sdk_engine
        n += claude_sdk_engine.cancel_all(tag)
    except Exception:
        pass
    return n


def _kill_tree(p, grace_s: float = 2.0):
    """Giết 1 tiến trình claude/codex VÀ TOÀN BỘ cây con (node) - dùng cho watchdog idle-timeout.
    Tiến trình treo (kẹt auth / flail trên path không tồn tại) nếu không giết sẽ sống mãi, ngốn
    RAM/CPU và làm treo server một-tiến-trình. POSIX dùng killpg (cần start_new_session=True).

    TERM trước, KILL sau (16/08): SIGKILL thẳng tay có thể rơi đúng lúc CLI đang GHI
    ~/.claude/.credentials.json (refresh token OAuth) - file cụt nửa chừng là "tự nhiên bị
    đăng xuất", đúng triệu chứng chủ báo. Cho `grace_s` giây để nó kịp đóng file; vẫn lì
    thì KILL như cũ. Hàm chạy trong THREAD watchdog nên chờ 2 giây không chặn event loop."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                           capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            return
        import signal as _signal
        try:
            pgid = os.getpgid(p.pid)
        except Exception:
            pgid = None
        try:
            if pgid is not None:
                os.killpg(pgid, _signal.SIGTERM)
            else:
                p.terminate()
        except Exception:
            pass
        het = time.time() + max(0.0, grace_s)
        while time.time() < het:
            if p.poll() is not None:
                return
            time.sleep(0.1)
        try:
            if pgid is not None:
                os.killpg(pgid, _signal.SIGKILL)
            else:
                p.kill()
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
    except Exception:
        pass


# Thư mục cài binary hay gặp mà PATH của TIẾN TRÌNH NỀN thường không có. macOS đau nhất:
# tiến trình chạy qua launchd (hoặc `nohup` do install.sh đẻ ra, hoặc app bật từ Finder) nhận
# PATH tối giản `/usr/bin:/bin:/usr/sbin:/sbin`, nên `claude`/`codex` cài bằng Homebrew - Apple
# Silicon để ở /opt/homebrew/bin - hay bằng nvm đều "không tìm thấy", dù gõ trong Terminal vẫn
# chạy ngon. Triệu chứng ở tầng trên là danh sách model rỗng mà không lý do.
_THU_MUC_BIN_THEM = (
    "/opt/homebrew/bin",          # Homebrew trên Apple Silicon
    "/usr/local/bin",             # Homebrew trên Intel + npm global mặc định
    "/opt/homebrew/opt/node/bin",
    "~/.local/bin",
    "~/.npm-global/bin",
    "~/.bun/bin",
    "~/.volta/bin",
    "~/Library/pnpm",             # pnpm global trên macOS
    "~/.yarn/bin",
)


def _duong_dan_tim_binary() -> str:
    """PATH hiện tại CỘNG các thư mục cài quen thuộc. PATH thật đứng trước để không đổi ưu tiên."""
    parts = [os.environ.get("PATH", "")]
    for d in _THU_MUC_BIN_THEM:
        try:
            parts.append(str(Path(d).expanduser()))
        except Exception:
            pass
    try:
        # nvm: mỗi bản Node một thư mục bin riêng. Bản mới nhất trước (sort ngược theo tên).
        nvm = sorted((_home_dir() / ".nvm" / "versions" / "node").glob("*/bin"), reverse=True)
        parts += [str(p) for p in nvm[:5]]
    except Exception:
        pass
    return os.pathsep.join(p for p in parts if p)


def tim_binary(ten: str) -> Optional[str]:
    """`shutil.which` nhưng soi thêm các thư mục cài quen thuộc nằm ngoài PATH."""
    return shutil.which(ten) or shutil.which(ten, path=_duong_dan_tim_binary())


def find_claude_cli() -> Optional[str]:
    """Tìm claude CLI trên máy."""
    cli = tim_binary("claude")
    if cli:
        return cli
    if os.name == "nt":
        candidates = [
            Path(os.environ.get("USERPROFILE", "")) / ".local" / "bin" / "claude.EXE",
            Path(os.environ.get("USERPROFILE", "")) / ".local" / "bin" / "claude.exe",
            Path(os.environ.get("APPDATA", "")) / "npm" / "claude.cmd",
            Path(os.environ.get("APPDATA", "")) / "npm" / "claude.exe",
        ]
        for p in candidates:
            if p.exists():
                return str(p)
    for p in ("/usr/local/bin/claude", "~/.local/bin/claude", "~/.npm-global/bin/claude"):
        path = Path(p).expanduser()
        if path.exists():
            return str(path)
    return None


# ---- Danh sách model của gói Claude Code, đọc từ CHÍNH BINARY `claude` ----
#
# Vì sao phải có: provider `anthropic-cli` chạy bằng đăng nhập của Claude Code, mà Javis KHÔNG
# được đọc token đó (Anthropic cấm - xem claude_auth.py), nên từ 0.26.17 nó không còn nguồn
# danh sách model nào ngoài `anthropic_api_key`. Phần đông người dùng chạy gói thuê bao và
# không có key, nên trình chọn model rơi về mấy alias ghi cứng trong config.py - và một khi
# `settings.json` đã nhớ một danh sách cũ thì danh sách ĐÓ đè luôn bản mặc định mới, tức là
# nâng cấp Javis cũng không thấy dòng model mới. Đúng lỗi chủ repo báo 05/09: cài xong bản
# mới vẫn không có Fable 5.1.
#
# Nguồn mới ở đây KHÔNG đụng vào bất cứ thứ gì của người dùng: binary `claude` nhúng sẵn danh
# mục model của chính nó (thử `claude --model tên-bậy` là nó tự nói "isn't described by this
# version's model catalog"), nên đọc file binary ra là biết bản CLI đang cài hiểu những model
# nào. Cập nhật Claude Code là danh sách tự mới theo, khỏi sửa code Javis - đúng thứ đường
# mượn token ngày trước làm được, mà lần này không chạm credential của ai.
#
# Đây là HEURISTIC trên dữ liệu nội bộ của CLI, nên nó fail-soft: đọc không ra thì trả None và
# caller giữ nguyên catalog mặc định, chứ không bao giờ làm hỏng trình chọn model.
_RX_MODEL_ID = re.compile(rb'"(claude-[a-z]+-[0-9][0-9a-z-]{0,24})"')
_MAX_QUET_MB = 600            # binary Claude Code ~215MB; quá ngưỡng này là file lạ, không quét
_MODELS_CACHE = {"sig": None, "ids": None}


def tach_phien_ban(mid: str):
    """`claude-opus-4-5-20251101` -> ("opus", (4, 5), 1). None = không phải model id.

    Số thứ ba là cờ "có gắn ngày". Tách ngày ra khỏi số phiên bản là bắt buộc chứ không phải
    làm đẹp: `claude-opus-4-20250514` mà để nguyên thì nó thành phiên bản 4.20250514, tức mới
    hơn cả `claude-opus-4-8` - trình chọn model sẽ bày một bản chụp năm ngoái lên đầu.

    Lọc ở đây cũng là chỗ duy nhất phân biệt model thật với chuỗi trùng khuôn: binary còn chứa
    `claude-code-20250219` (tên client) và `claude-desktop-3p`. Luật: sau `claude-` phải là
    một TÊN DÒNG toàn chữ, rồi tới một số phiên bản tối đa 2 chữ số - ngày tháng 8 chữ số
    không bao giờ là số hiệu dòng.
    """
    parts = (mid or "").split("-")
    if len(parts) < 3 or parts[0] != "claude" or not parts[1].isalpha():
        return None
    if not (parts[2].isdigit() and len(parts[2]) <= 2):
        return None
    so = []
    for x in parts[2:]:
        if not x.isdigit():
            return None
        so.append(int(x))
    ngay = 1 if so[-1] > 9999 else 0
    if ngay:
        so = so[:-1]
    return parts[1], tuple(so), ngay


def bac_phien_ban(ver) -> tuple:
    """Số phiên bản -> khoá sắp xếp MỚI NHẤT TRƯỚC, đệm về đủ 2 cấp.

    Đệm là phần dễ quên: `claude-opus-4` là (4,) còn `claude-opus-4-8` là (4, 8). So thẳng thì
    tuple ngắn thắng, tức bản 4 trần đứng trên 4.8. Đệm số 0 vào rồi mới đổi dấu thì đúng thứ
    tự người ta mong: 5.1 > 5 > 4.8 > 4.
    """
    v = tuple(ver[:2])
    v = v + (0,) * (2 - len(v))
    return tuple(-n for n in v)


def _doc_id_model(path: Path) -> list:
    """Mọi model id nhúng trong một file, đọc theo khối để không nuốt 200MB vào RAM."""
    ra = []
    thay = set()
    with path.open("rb") as f:
        du = b""
        while True:
            khoi = f.read(1 << 22)
            if not khoi:
                break
            buf = du + khoi
            for m in _RX_MODEL_ID.finditer(buf):
                mid = m.group(1).decode("ascii", "ignore")
                if mid not in thay:
                    thay.add(mid)
                    ra.append(mid)
            du = buf[-64:]        # id bị cắt ngang ranh giới khối vẫn bắt được ở vòng sau
    return ra


def _file_co_danh_muc() -> Optional[Path]:
    """File chứa danh mục model: binary native, hoặc `cli.js` khi cài bằng npm.

    Bản npm trên Windows là một file .cmd vài trăm byte trỏ sang cli.js, nên quét thẳng nó thì
    không ra gì - phải lần sang bundle thật.
    """
    cli = find_claude_cli()
    if not cli:
        return None
    try:
        p = Path(os.path.realpath(cli))
    except Exception:
        return None
    try:
        if p.is_file() and p.stat().st_size > (1 << 20):
            return p
    except OSError:
        return None
    goc = p.parent
    for phu in ("node_modules/@anthropic-ai/claude-code/cli.js",
                "../lib/node_modules/@anthropic-ai/claude-code/cli.js",
                "../node_modules/@anthropic-ai/claude-code/cli.js"):
        try:
            q = (goc / phu).resolve()
            if q.is_file():
                return q
        except OSError:
            continue
    return p if p.is_file() else None


def list_models() -> Optional[list]:
    """Model của gói Claude Code: alias đứng trước, rồi id đầy đủ MỚI NHẤT trước.

    None = không đọc được (chưa cài CLI, file lạ, hoặc bản CLI không nhúng danh mục) - caller
    giữ nguyên catalog đang có. Kết quả nhớ theo (đường dẫn, cỡ file, mtime) nên cập nhật
    Claude Code là lần hỏi sau tự quét lại, còn bình thường thì không đụng đĩa.
    """
    p = _file_co_danh_muc()
    if not p:
        return None
    try:
        st = p.stat()
        if st.st_size > _MAX_QUET_MB * (1 << 20):
            return None
        sig = (str(p), st.st_size, st.st_mtime_ns)
    except OSError:
        return None
    if _MODELS_CACHE["sig"] == sig:
        return list(_MODELS_CACHE["ids"]) if _MODELS_CACHE["ids"] else None
    try:
        tho = _doc_id_model(p)
    except Exception:
        return None
    hop = []
    for mid in tho:
        v = tach_phien_ban(mid)
        if v:
            hop.append((v[0], v[1], v[2], mid))
    if not hop:
        _MODELS_CACHE.update(sig=sig, ids=None)
        return None
    # Dòng nào có bản mới nhất thì đứng trước; trong một dòng, bản mới trước, và bản KHÔNG
    # gắn ngày đứng trên bản gắn ngày (`claude-haiku-4-5` trước `claude-haiku-4-5-20251001`)
    # vì đó mới là tên người dùng gõ.
    moi_nhat = {}
    for fam, ver, _, _ in hop:
        if ver > moi_nhat.get(fam, ()):
            moi_nhat[fam] = ver
    hop.sort(key=lambda x: (bac_phien_ban(moi_nhat[x[0]]), x[0], bac_phien_ban(x[1]), x[2], x[3]))
    ids = [mid for _, _, _, mid in hop]
    alias = []
    for fam, _, _, _ in hop:
        if fam not in alias:
            alias.append(fam)
    ket_qua = (alias + ids)[:40]
    _MODELS_CACHE.update(sig=sig, ids=list(ket_qua))
    return ket_qua


# ---- Claude Code auth (đăng nhập Anthropic dùng cho engine CLI) ----
def _no_window():
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


# ---- MCP RỖNG cho fork học (cô lập tuyệt đối) ----
# `--strict-mcp-config` của Claude Code CHỈ có hiệu lực khi đi kèm 1 file --mcp-config.
# Fork học phải chạy với 0 MCP → ta ghi 1 file {"mcpServers":{}} rồi truyền strict.
# Gọi _empty_mcp_file() TRẢ path đã ĐẢM BẢO tồn tại + non-empty (fail-closed: caller phải
# assert path này trước khi spawn; None/rỗng ⇒ TỪ CHỐI spawn, không để fork nuốt MCP máy).
import tempfile as _tempfile

def _empty_mcp_file() -> Optional[str]:
    try:
        p = Path(_tempfile.gettempdir()) / "javis-empty-mcp.json"
        if not (p.exists() and p.stat().st_size > 0):
            p.write_text('{"mcpServers":{}}', encoding="utf-8")
        return str(p) if p.stat().st_size > 0 else None
    except Exception:
        return None


# Trạng thái đăng nhập Claude lần hỏi gần nhất CÒN DÙNG ĐƯỢC, nhớ trong RAM.
#
# Vì sao cần: mỗi lần mở trang Models là một lần đẻ tiến trình Node (`claude auth status`), mất
# cỡ một giây khi máy rảnh. Đổi Main Model sang Antigravity thì trang vẽ lại và CÙNG LÚC còn
# `agy models` + /provider/models cũng đang đẻ tiến trình con - trên VPS nhỏ, lượt hỏi này hết
# 25 giây rồi ném TimeoutExpired. Trước bản này lỗi đó trả `connected: False`, mà thẻ thì vẽ
# `connected False` y hệt "chưa đăng nhập" kèm nút đăng nhập - nên chủ repo đổi model xong lại
# tưởng mình bị đăng xuất và phải nối lại Claude (báo 2026-08-13).
_AUTH_CACHE = {"ts": 0.0, "val": None}
_AUTH_TTL = 90.0


def auth_status(bo_qua_cache: bool = False):
    """Trạng thái đăng nhập Claude Code: {connected, email, plan, org}.

    Hai thứ KHÁC NHAU mà bản cũ trộn làm một, nay tách bằng cờ `unknown`:

    - `connected: False` = chính CLI nói chưa đăng nhập. Bày nút đăng nhập là đúng.
    - `unknown: True`    = KHÔNG hỏi được (hết giờ, CLI lỗi, JSON hỏng). Không biết gì hết,
      nên tuyệt đối đừng nói "chưa đăng nhập" - đó là dựng chuyện, và người dùng sẽ đi đăng
      nhập lại một tài khoản vốn chưa hề mất.

    Hỏi hỏng mà trước đó từng hỏi được thì trả lại bản nhớ kèm `stale: True`: trạng thái cũ vài
    chục giây gần sự thật hơn nhiều so với một câu đoán bừa.
    """
    cli = find_claude_cli()
    if not cli:
        return {"connected": False, "error": "Claude CLI chưa cài"}
    now = time.time()
    if not bo_qua_cache and _AUTH_CACHE["val"] and now - _AUTH_CACHE["ts"] < _AUTH_TTL:
        return dict(_AUTH_CACHE["val"])
    try:
        r = subprocess.run([cli, "auth", "status", "--json"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=25, creationflags=_no_window())
        d = json.loads((r.stdout or "").strip() or "{}")
        ra = {"connected": bool(d.get("loggedIn")), "email": d.get("email", ""),
              "plan": d.get("subscriptionType", "") or d.get("authMethod", ""), "org": d.get("orgName", "")}
        cu = _AUTH_CACHE["val"] or {}
        if cu.get("connected") and not ra["connected"]:
            # Đang đăng nhập mà CLI báo mất - in dấu vết CÓ GIỜ để lần sau chủ báo "thi thoảng
            # bị đăng xuất" thì log nói được nó xảy ra lúc nào, cạnh sự kiện gì.
            print(f"[claude auth] CLI báo ĐÃ ĐĂNG XUẤT (trước đó đang đăng nhập) lúc "
                  f"{time.strftime('%Y-%m-%d %H:%M:%S')}", file=sys.stderr)
        _AUTH_CACHE.update(ts=now, val=dict(ra))
        return ra
    except Exception as e:
        cu = _AUTH_CACHE["val"]
        if cu:
            ra = dict(cu)
            ra["stale"] = True
            ra["error"] = f"{type(e).__name__}: {e}"
            return ra
        return {"connected": False, "unknown": True, "error": f"{type(e).__name__}: {e}"}


def auth_quen_cache():
    """Xoá bản nhớ - gọi sau khi đăng nhập/ngắt để thẻ hiện trạng thái mới ngay."""
    _AUTH_CACHE.update(ts=0.0, val=None)


# ---- Vệ sĩ credentials (16/08): chống "tự nhiên bị đăng xuất" ----
# Claude CLI TỰ quản token trong ~/.claude/.credentials.json và tự ghi lại file đó mỗi lần
# refresh OAuth. Javis chạy nhiều tiến trình claude song song và có watchdog giết tiến trình
# treo - kill rơi đúng lúc CLI đang ghi là file cụt nửa chừng, lượt sau CLI đọc không ra và
# coi như chưa đăng nhập. Codex không bao giờ bị vì token ChatGPT do CHÍNH JAVIS giữ và ghi
# nguyên tử. Vệ sĩ: thấy bản lành thì sao lưu; thấy file HỎNG/MẤT mà có bản sao lưu thì phục
# hồi + hô to. Đăng xuất CHỦ ĐỘNG (file lành nhưng không còn token, hoặc bấm Ngắt trên UI)
# thì xoá bản sao lưu - tôn trọng ý người dùng, không "hồi sinh" phiên họ vừa ngắt.
def _cred_path() -> Path:
    return _home_dir() / ".claude" / ".credentials.json"


def _cred_bak_path() -> Path:
    return _cred_path().with_name(".credentials.json.javis-bak")


def _cred_co_token(raw: str) -> bool:
    try:
        oa = (json.loads(raw) or {}).get("claudeAiOauth") or {}
        return bool(oa.get("accessToken") or oa.get("refreshToken"))
    except Exception:
        return False


def giu_credentials() -> str:
    """Một vòng vệ sĩ. Trả nhãn việc đã làm: backup | restore | logout | hong | '' (yên)."""
    p, b = _cred_path(), _cred_bak_path()
    try:
        raw = None
        try:
            raw = p.read_text(encoding="utf-8")
        except FileNotFoundError:
            raw = None
        except Exception:
            return ""                      # đọc lỗi lạ (quyền...) → không kết luận, không đụng
        if raw is not None:
            try:
                json.loads(raw)
                hop_le = True
            except Exception:
                hop_le = False
            if hop_le and _cred_co_token(raw):
                # Bản lành → sao lưu (chỉ ghi khi khác, ghi nguyên tử, quyền 600 như bản gốc).
                try:
                    if not b.exists() or b.read_text(encoding="utf-8") != raw:
                        tmp = b.with_name(b.name + ".tmp")
                        tmp.write_text(raw, encoding="utf-8")
                        try:
                            os.chmod(tmp, 0o600)
                        except Exception:
                            pass
                        os.replace(tmp, b)
                        return "backup"
                except Exception:
                    pass
                return ""
            if hop_le:
                # JSON lành nhưng KHÔNG còn token = CLI đã đăng xuất tử tế → xoá bản sao lưu.
                try:
                    b.unlink(missing_ok=True)
                except Exception:
                    pass
                return "logout"
        # Tới đây: file MẤT hoặc JSON HỎNG. Có bản sao lưu lành thì phục hồi.
        # macOS (token trong Keychain, file không bao giờ tồn tại) tự an toàn: không có file
        # lành thì bản sao lưu chưa từng được tạo, nhánh này không bao giờ chạy.
        try:
            bak = b.read_text(encoding="utf-8")
        except Exception:
            if raw is not None:
                print("[claude auth] .credentials.json HỎNG (JSON không đọc được) và không có "
                      "bản sao lưu - phải đăng nhập lại.", file=sys.stderr)
                return "hong"
            return ""
        if not _cred_co_token(bak):
            return ""
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(bak, encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except Exception:
            pass
        os.replace(tmp, p)
        auth_quen_cache()
        print("[claude auth] .credentials.json "
              + ("hỏng" if raw is not None else "biến mất")
              + " - đã PHỤC HỒI từ bản sao lưu. Đây là dấu vết của một tiến trình claude bị "
              "giết giữa lúc ghi file token.", file=sys.stderr)
        return "restore"
    except Exception as e:
        print(f"[claude auth] vệ sĩ credentials lỗi: {type(e).__name__}: {e}", file=sys.stderr)
        return ""


def auth_logout():
    cli = find_claude_cli()
    if not cli:
        return {"ok": False, "error": "Claude CLI chưa cài"}
    try:
        subprocess.run([cli, "auth", "logout"], capture_output=True, text=True, timeout=25, creationflags=_no_window())
        auth_quen_cache()   # ngắt xong thẻ phải đổi NGAY, không chờ hết 90 giây nhớ
        try:
            # Ngắt CHỦ ĐỘNG thì xoá luôn bản sao lưu của vệ sĩ credentials - không thì vòng
            # vệ sĩ kế tiếp "hồi sinh" đúng phiên người dùng vừa cố tình ngắt.
            _cred_bak_path().unlink(missing_ok=True)
        except Exception:
            pass
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def auth_login():
    """Mở luồng đăng nhập (browser) ở tiến trình nền - tự hoàn tất qua localhost callback rồi thoát.
    Chạy được trên máy có trình duyệt (local). Frontend poll auth_status tới khi connected."""
    cli = find_claude_cli()
    if not cli:
        return {"ok": False, "error": "Claude CLI chưa cài"}
    try:
        subprocess.Popen([cli, "auth", "login", "--claudeai"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=_no_window())
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


# ---- Đăng nhập Claude NGAY TRÊN UI (chạy được cả VPS headless) ----
# Chạy `claude auth login --claudeai` với pipe: đọc LINK nó in cho user mở, nhận CODE user dán rồi
# ghi vào stdin. Trạng thái giữ ở _LOGIN (1 phiên 1 lúc là đủ). KHÔNG mở browser trên server.
import re as _re_login
_LOGIN = {"proc": None, "url": "", "done": False, "error": "", "lines": []}
_LOGIN_URL_RE = _re_login.compile(r"https?://\S+")


def auth_login_ui_start():
    cli = find_claude_cli()
    if not cli:
        return {"ok": False, "error": "Claude CLI chưa cài"}
    try:
        if _LOGIN["proc"] and _LOGIN["proc"].poll() is None:
            _kill_tree(_LOGIN["proc"])
    except Exception:
        pass
    _LOGIN.update({"proc": None, "url": "", "done": False, "error": "", "lines": []})
    try:
        proc = subprocess.Popen(
            [cli, "auth", "login", "--claudeai"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=_no_window(), start_new_session=(os.name != "nt"),
        )
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    _LOGIN["proc"] = proc

    def _reader():
        try:
            for line in proc.stdout:
                line = line.rstrip()
                if not line:
                    continue
                _LOGIN["lines"].append(line)
                if not _LOGIN["url"]:
                    m = _LOGIN_URL_RE.search(line)
                    if m:
                        _LOGIN["url"] = m.group(0)
                low = line.lower()
                if "success" in low or "logged in" in low:
                    _LOGIN["done"] = True
                elif "error" in low or "failed" in low or "invalid" in low:
                    _LOGIN["error"] = line
        except Exception as e:
            _LOGIN["error"] = f"{type(e).__name__}: {e}"
        finally:
            try:
                if proc.poll() is not None and proc.returncode == 0:
                    _LOGIN["done"] = True
            except Exception:
                pass
    threading.Thread(target=_reader, daemon=True).start()
    for _ in range(60):   # đợi tối đa ~12s để có URL / xong sớm / lỗi
        if _LOGIN["url"] or _LOGIN["done"] or _LOGIN["error"]:
            break
        time.sleep(0.2)
    if not (_LOGIN["url"] or _LOGIN["done"] or _LOGIN["error"]):
        return {"ok": False, "error": "Không lấy được link đăng nhập (claude CLI không in URL)."}
    return {"ok": True, "url": _LOGIN["url"], "done": _LOGIN["done"], "error": _LOGIN["error"]}


def auth_login_ui_code(code):
    proc = _LOGIN.get("proc")
    if not proc:
        return {"ok": False, "error": "Chưa bắt đầu đăng nhập (bấm Đăng nhập trước)."}
    try:
        proc.stdin.write((code or "").strip() + "\n")
        proc.stdin.flush()
    except Exception as e:
        return {"ok": False, "error": f"Không gửi được code: {e}"}
    for _ in range(120):   # ~24s
        if _LOGIN["done"]:
            auth_quen_cache()   # đăng nhập xong thẻ phải xanh NGAY, không chờ hết hạn nhớ
            return {"ok": True}
        if _LOGIN["error"]:
            return {"ok": False, "error": _LOGIN["error"]}
        if proc.poll() is not None:
            return {"ok": proc.returncode == 0,
                    "error": "" if proc.returncode == 0 else "Đăng nhập thất bại - thử lại."}
        time.sleep(0.2)
    return {"ok": _LOGIN["done"], "error": _LOGIN.get("error", "")}


# ---- MCP native (cho server OAuth - Claude Code tự lo OAuth; scope user = dùng chung mọi cwd) ----
def mcp_native_add(name, url, transport="http", header=None, client_id=None):
    cli = find_claude_cli()
    if not cli:
        return {"ok": False, "error": "Claude CLI chưa cài"}
    args = [cli, "mcp", "add", "--scope", "user", "--transport", transport]
    if header:
        args += ["--header", header]
    if client_id:
        args += ["--client-id", client_id]
    args += [name, url]
    try:
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=30, creationflags=_no_window())
        ok = r.returncode == 0
        return {"ok": ok, "out": (r.stdout or r.stderr or "").strip()[:300]}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def mcp_native_remove(name):
    cli = find_claude_cli()
    if not cli:
        return {"ok": False, "error": "Claude CLI chưa cài"}
    try:
        subprocess.run([cli, "mcp", "remove", "--scope", "user", name], capture_output=True,
                       text=True, timeout=30, creationflags=_no_window())
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def mcp_native_status(name):
    """Trạng thái server OAuth native: {authenticated, status} qua `claude mcp get` (parse 'Needs authentication')."""
    cli = find_claude_cli()
    if not cli:
        return {"authenticated": False, "status": "no_cli"}
    try:
        r = subprocess.run([cli, "mcp", "get", name], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30, creationflags=_no_window())
        out = ((r.stdout or "") + (r.stderr or "")).lower()
        if "needs authentication" in out:
            return {"authenticated": False, "status": "needs_auth"}
        if r.returncode != 0 or "not found" in out or "no mcp server" in out:
            return {"authenticated": False, "status": "not_found"}
        return {"authenticated": True, "status": "ok"}
    except Exception as e:
        return {"authenticated": False, "status": "error", "error": f"{type(e).__name__}: {e}"}


def mcp_native_list():
    """Liệt kê MCP sẵn trong Claude Code (đồng bộ từ claude.ai) - chỉ để hiển thị.
    Parse output `<tên>: <url> - <trạng thái>` (health check nên hơi lâu)."""
    cli = find_claude_cli()
    if not cli:
        return []
    try:
        r = subprocess.run([cli, "mcp", "list"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60, creationflags=_no_window())
        out = r.stdout or ""
    except Exception:
        return []
    servers = []
    for line in out.splitlines():
        line = line.strip()
        if " - " not in line:
            continue
        pos = line.find("http://")
        if pos < 0:
            pos = line.find("https://")
        if pos < 0:
            continue
        name = line[:pos].rstrip().rstrip(":").strip()
        rest = line[pos:]
        dash = rest.rfind(" - ")
        if dash < 0:
            continue
        url = rest[:dash].strip()
        status = rest[dash + 3:].strip()
        connected = ("connected" in status.lower()) or ("✔" in status) or ("✓" in status)
        servers.append({"name": name, "url": url, "status": status, "connected": connected})
    return servers


def mcp_open_auth_terminal():
    """Mở 1 cửa sổ terminal chạy `claude` để user gõ /mcp xác thực OAuth MCP (chỉ máy local có màn hình)."""
    cli = find_claude_cli()
    if not cli:
        return {"ok": False, "error": "Claude CLI chưa cài"}
    try:
        if os.name == "nt":
            subprocess.Popen('start "Javis - Xac thuc MCP (go /mcp)" cmd /k claude', shell=True)
        else:
            for term in ("x-terminal-emulator", "gnome-terminal", "konsole", "xterm"):
                if shutil.which(term):
                    subprocess.Popen([term, "-e", "claude"])
                    break
            else:
                return {"ok": False, "error": "Không tìm thấy terminal"}
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


_engine_env_warned = False


def claude_engine(system_prompt=None, cwd=None, tag="chat", allowed_tools=None, model=None):
    """FACTORY engine Claude - mọi call site tạo engine qua đây. Từ v0.9.37 engine Claude
    CHỈ chạy qua claude-agent-sdk (claude_sdk_engine.ClaudeSDK); nhánh Popen ClaudeCLI cũ
    đã gỡ sau khi bake ổn (nhật ký ở docs/dev/2026-07-ke-hoach-agent-sdk.md mục 8).
    SDK chưa cài thì ClaudeSDK tự báo lỗi rõ trong .query() (hướng dẫn pip install).
    Env JAVIS_CLAUDE_ENGINE=cli|sdk-loops chỉ còn giá trị lịch sử - bị bỏ qua kèm log 1 lần."""
    global _engine_env_warned
    mode = os.getenv("JAVIS_CLAUDE_ENGINE", "sdk").strip().lower()
    if mode in ("cli", "sdk-loops") and not _engine_env_warned:
        _engine_env_warned = True
        print(f"[claude engine] JAVIS_CLAUDE_ENGINE={mode} đã gỡ từ v0.9.37 - engine Claude "
              "luôn chạy Agent SDK. Gặp lỗi hãy báo issue kèm log.", file=sys.stderr)
    from claude_sdk_engine import ClaudeSDK
    return ClaudeSDK(system_prompt=system_prompt, cwd=cwd, tag=tag,
                     allowed_tools=allowed_tools, model=model)


# ============================================================
# Codex CLI - chạy `codex exec --json` cho provider ChatGPT OAuth (gói subscription).
# Giống cách Hermes spawn codex (app-server); ta dùng `exec` gọn hơn. codex tự lo
# subscription auth (~/.codex/auth.json) + MCP (~/.codex/config.toml) + tool NATIVE
# → ChatGPT subscription DÙNG ĐƯỢC MCP (điều mà raw HTTP endpoint không làm được).
# ============================================================
def _home_dir() -> Path:
    """Thư mục home đáng tin trên MỌI cách khởi động server.

    Không dựa mỗi USERPROFILE: khi server được bật lại bởi tự-cập-nhật, dịch vụ Windows
    hay tác vụ nền, biến này có thể trống - lúc đó home thành Path("") nên mọi đường dẫn
    ~/.codex/... hoá ra tương đối và không tồn tại, khiến Javis báo nhầm "chưa cài Codex CLI"
    dù binary vẫn nằm đó. Thử lần lượt các nguồn rồi mới chịu thua.
    """
    cands = [os.environ.get("USERPROFILE"), os.environ.get("HOME")]
    drive, path = os.environ.get("HOMEDRIVE", ""), os.environ.get("HOMEPATH", "")
    if drive and path:
        cands.append(drive + path)
    for c in cands:
        try:
            if c and Path(c).exists():
                return Path(c)
        except Exception:
            pass
    try:
        h = Path.home()          # dự phòng cuối: pathlib tự suy ra (pwd trên POSIX)
        if h.exists():
            return h
    except Exception:
        pass
    return Path("")


def find_codex_cli() -> Optional[str]:
    envp = os.environ.get("JAVIS_CODEX_BIN")     # cửa thoát: chỉ thẳng chỗ cài lạ
    if envp:
        try:
            if Path(envp).exists():
                return envp
        except Exception:
            pass
    home = _home_dir()
    cands = [
        home / ".codex" / ".sandbox-bin" / "codex.exe",
        home / ".codex" / "plugins" / ".plugin-appserver" / "codex.exe",
        Path(os.environ.get("APPDATA", "")) / "npm" / "codex.cmd",
        Path(os.environ.get("APPDATA", "")) / "npm" / "codex.exe",
        home / ".codex" / ".sandbox-bin" / "codex",
    ]
    # Windows Store có thể đặt app-execution alias ``codex.exe`` lên PATH nhưng
    # service/tiến trình nền không được quyền chạy alias đó (WinError 5). Bản
    # executable Codex Desktop xuất trong ~/.codex chạy được thật, nên ưu tiên
    # nó trên Windows. POSIX vẫn tôn trọng PATH trước như thông lệ.
    cli = tim_binary("codex")
    if cli and (os.name != "nt" or "windowsapps" not in cli.lower()):
        return cli
    for p in cands:
        try:
            if p.exists():
                return str(p)
        except Exception:
            pass
    if cli:
        return cli
    for p in ("/usr/local/bin/codex", "~/.local/bin/codex"):
        pp = Path(p).expanduser()
        if pp.exists():
            return str(pp)
    return None


# ---- MCP NATIVE của Codex (kho gốc ~/.codex/config.toml, quản bằng `codex mcp ...`) ----
# Đối xứng với bộ mcp_native_* của Claude ở trên: Codex cũng có kho MCP gốc riêng (user tự
# `codex mcp add`, hoặc app khác ghi vào config.toml). Javis chạy `codex exec -p javis` mà
# profile chỉ PHỦ THÊM lên config gốc nên kho này vẫn được engine ChatGPT nạp - các hàm dưới
# cho Javis liệt kê/thêm/gỡ/kiểm tra nó, và mở `codex mcp login <tên>` cho server OAuth.
def _codex_run(sub_args, timeout=30):
    """Chạy `codex <sub_args...>` trả CompletedProcess; None nếu chưa cài Codex CLI."""
    cli = find_codex_cli()
    if not cli:
        return None
    return subprocess.run([cli] + list(sub_args), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout,
                          creationflags=_no_window())


def codex_mcp_parse_list(out):
    """Parse output `codex mcp list --json` → list chuẩn hoá [{name, url, command, transport,
    status, connected}]. PURE (test được không cần codex). Format --json từng đổi giữa các bản
    Codex nên chấp nhận nhiều hình dạng: list phẳng, bọc {"servers": [...]}, hay map tên→cấu
    hình; parse hụt trả [] chứ không nổ."""
    out = (out or "").strip()
    if not out:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        inner = data.get("servers") or data.get("mcp_servers") or data
        if isinstance(inner, list):
            data = inner
        elif isinstance(inner, dict):
            data = [dict(v, name=v.get("name") or k) if isinstance(v, dict) else {"name": str(k)}
                    for k, v in inner.items()]
        else:
            return []
    if not isinstance(data, list):
        return []
    servers = []
    for it in data:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "").strip()
        if not name:
            continue
        tr = it.get("transport") if isinstance(it.get("transport"), dict) else {}
        url = str(it.get("url") or tr.get("url") or "")
        cmd = it.get("command") or tr.get("command") or ""
        if not isinstance(cmd, str):
            cmd = " ".join(str(x) for x in cmd)
        args = it.get("args") or tr.get("args") or []
        if cmd and args:
            cmd = (cmd + " " + " ".join(str(a) for a in args)).strip()
        ttype = str((it.get("transport") if isinstance(it.get("transport"), str) else tr.get("type"))
                    or ("http" if url else ("stdio" if cmd else "")))
        enabled = it.get("enabled")
        auth = str(it.get("auth_status") or it.get("auth") or "").lower()
        needs_login = auth in ("unauthenticated", "needs_login", "not_logged_in", "logged_out")
        status = ("tắt" if enabled is False
                  else "cần đăng nhập (codex mcp login)" if needs_login else "đã khai báo")
        servers.append({"name": name, "url": url, "command": cmd, "transport": ttype,
                        "status": status, "connected": enabled is not False and not needs_login})
    return servers


def codex_mcp_parse_list_text(out):
    """Fallback cho bản codex cũ không có `mcp list --json`: parse bảng text, lấy cột tên.
    PURE. Bỏ dòng header/kẻ bảng/'No MCP servers configured'."""
    servers = []
    for line in (out or "").splitlines():
        line = line.strip().strip("│|").strip()
        if not line or "no mcp servers" in line.lower():
            continue
        if not set(line) - set("-─┼┤├┌┐└┘│| "):   # dòng kẻ bảng
            continue
        first = line.split()[0]
        if first.lower() in ("name", "server"):    # dòng header bảng
            continue
        servers.append({"name": first, "url": "", "command": "", "transport": "",
                        "status": "đã khai báo", "connected": True})
    return servers


def codex_mcp_native_list():
    """Liệt kê MCP gốc của Codex (~/.codex/config.toml) - chỉ hiển thị, như mcp_native_list
    bên Claude. Ưu tiên `codex mcp list --json`; bản cũ fallback parse bảng text."""
    try:
        r = _codex_run(["mcp", "list", "--json"], timeout=30)
    except Exception:
        return []
    if r is None:
        return []
    if r.returncode == 0:
        servers = codex_mcp_parse_list(r.stdout)
        if servers:
            return servers
    try:
        r2 = _codex_run(["mcp", "list"], timeout=30)
    except Exception:
        return []
    if r2 is None or r2.returncode != 0:
        return []
    return codex_mcp_parse_list_text(r2.stdout)


def _codex_mcp_add_args(name, url=None, command=None, bearer_env=None):
    """Dựng argv sau `codex` cho `mcp add` (PURE để test). url → server HTTP (bearer_env =
    TÊN biến env chứa token, không phải token); command (str hoặc list) → server stdio sau '--'."""
    args = ["mcp", "add", name]
    if url:
        args += ["--url", url]
        if bearer_env:
            args += ["--bearer-token-env-var", bearer_env]
    elif command:
        cmd = command if isinstance(command, list) else str(command).split()
        args += ["--"] + [str(c) for c in cmd]
    return args


def codex_mcp_native_add(name, url=None, command=None, bearer_env=None):
    """Đăng ký 1 server vào kho MCP gốc của Codex (`codex mcp add`). Server OAuth: thêm bằng
    url rồi user chạy `codex mcp login <tên>` MỘT lần (như claude → /mcp bên Claude)."""
    if not find_codex_cli():
        return {"ok": False, "error": "Codex CLI chưa cài"}
    if not (url or command):
        return {"ok": False, "error": "Thiếu url hoặc command"}
    try:
        r = _codex_run(_codex_mcp_add_args(name, url, command, bearer_env), timeout=30)
        ok = r is not None and r.returncode == 0
        return {"ok": ok, "out": ((r.stdout or "") + (r.stderr or "")).strip()[:300] if r else ""}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def codex_mcp_native_remove(name):
    if not find_codex_cli():
        return {"ok": False, "error": "Codex CLI chưa cài"}
    try:
        _codex_run(["mcp", "remove", name], timeout=30)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def codex_mcp_native_status(name):
    """Trạng thái 1 server trong kho gốc Codex qua `codex mcp get` (parse chuỗi cần đăng nhập) -
    đối xứng mcp_native_status bên Claude."""
    if not find_codex_cli():
        return {"authenticated": False, "status": "no_cli"}
    try:
        r = _codex_run(["mcp", "get", name], timeout=30)
        out = (((r.stdout or "") + (r.stderr or "")) if r else "").lower()
        if r is None or r.returncode != 0 or "not found" in out or "no mcp server" in out:
            return {"authenticated": False, "status": "not_found"}
        if ("not logged in" in out or "needs login" in out or "unauthenticated" in out
                or "login required" in out):
            return {"authenticated": False, "status": "needs_auth"}
        return {"authenticated": True, "status": "ok"}
    except Exception as e:
        return {"authenticated": False, "status": "error", "error": f"{type(e).__name__}: {e}"}


def codex_mcp_open_login_terminal(name):
    """Mở 1 cửa sổ terminal chạy `codex mcp login <tên>` để user xác thực OAuth cho MCP gốc
    của Codex (chỉ máy local có màn hình - như mcp_open_auth_terminal bên Claude)."""
    cli = find_codex_cli()
    if not cli:
        return {"ok": False, "error": "Codex CLI chưa cài"}
    # Tên đi vào chuỗi shell trên Windows → chỉ nhận chữ/số/_/- để khỏi tiêm lệnh.
    safe = "".join(ch for ch in str(name or "") if ch.isalnum() or ch in "_-")
    if not safe or safe != str(name):
        return {"ok": False, "error": "Tên server không hợp lệ"}
    try:
        if os.name == "nt":
            subprocess.Popen(f'start "Javis - Dang nhap MCP Codex" cmd /k codex mcp login {safe}',
                             shell=True)
        else:
            for term in ("x-terminal-emulator", "gnome-terminal", "konsole", "xterm"):
                if shutil.which(term):
                    subprocess.Popen([term, "-e", cli, "mcp", "login", safe])
                    break
            else:
                return {"ok": False, "error": "Không tìm thấy terminal"}
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


# Dấu vết "sandbox của Codex không khởi động nổi trong môi trường này".
#
# Chủ repo báo 2026-08-07 kèm ảnh: loop nền chạy bằng ChatGPT, mọi lệnh đọc/ghi file đều trả
# `bwrap: Failed to make / slave: Permission denied`, và bản báo cáo gửi về Telegram là một
# bài dài model tự kể lại nỗi bối rối của nó. Nguyên nhân nằm ngoài Javis: bubblewrap cần tạo
# được user namespace + đổi propagation của `/`, mà container Javis chạy user thường, không có
# CAP_SYS_ADMIN, và Ubuntu 24.04 còn chặn user namespace không đặc quyền bằng AppArmor.
#
# Hệ quả: TRONG DOCKER, hai mức sandbox `read-only` (mode suggest) và `workspace-write` (mode
# auto) của Codex không bao giờ chạy được. Mà loop tạo từ chat mặc định là suggest, nên mọi
# việc nền chạy bằng ChatGPT trong Docker đều câm theo đúng kiểu này.
_SANDBOX_HONG = re.compile(r"bwrap:|Failed to make / slave", re.I)

_NOTE_SANDBOX_HONG = (
    "⚠ Javis tự kiểm: rào sandbox riêng của Codex (ChatGPT) KHÔNG khởi động được trong môi "
    "trường này, nên mọi lệnh đọc/ghi file của nó đều bị chặn ngay từ đầu. Đây là giới hạn của "
    "container chứ không phải lỗi của lượt chạy, và thử lại bao nhiêu lần cũng vậy. Hai lối ra: "
    "đặt biến môi trường JAVIS_CODEX_SANDBOX=off để Codex chạy không có rào riêng (chính "
    "container vẫn là rào), hoặc chuyển việc nền này sang bộ não Claude."
)


def codex_sandbox_cho_mode(mode: str) -> Optional[str]:
    """Cờ `--sandbox` của Codex cho một mức quyền của Javis. None = không đặt rào riêng.

    `JAVIS_CODEX_SANDBOX=off` bỏ hẳn rào của Codex ở MỌI mức. Cần cho Docker, nơi bubblewrap
    không chạy nổi nên rào đó không phải là "chặt hơn" mà là "chết hẳn". Đánh đổi phải nói rõ:
    lúc đó mức `suggest` không còn thứ gì chặn Codex ghi file, vì Codex không có allowlist
    per-call như Claude. Ai đặt cờ này là đang chọn "container là rào duy nhất".
    """
    if str(os.getenv("JAVIS_CODEX_SANDBOX", "auto")).strip().lower() in ("off", "0", "false", "none"):
        return None
    return {"suggest": "read-only", "auto": "workspace-write", "full": None}.get(mode or "full")


class CodexCLI:
    def __init__(self, cwd: Optional[str] = None, tag: str = "chat", model: Optional[str] = None,
                 instructions: Optional[str] = None):
        self.cli_path = find_codex_cli()
        self.cwd = cwd or os.getcwd()
        self.tag = tag
        self.model = model              # gpt-5.5 / gpt-5.4 ...
        self.instructions = instructions
        self.extra_config = []          # list '-c key=value' (override config, vd thêm mcp_servers)
        self.profile = None             # tên profile codex (-p) - Javis ghi javis.config.toml để thêm MCP
        self.session_id = None          # Codex thread_id; có giá trị → `codex exec resume <id>`
        # Sandbox của Codex: None = toàn quyền (mặc định, giữ nguyên hành vi cũ của chat/workflow).
        # Việc nền đặt 'read-only' / 'workspace-write' để khớp mode suggest/auto của loop -
        # Codex KHÔNG có allowlist per-call như Claude nên đây là lớp chặn thật sự duy nhất.
        self.sandbox = None

    def is_available(self) -> bool:
        return self.cli_path is not None

    def _build_args(self) -> list[str]:
        """Dựng argv cho lượt mới/resume.

        Cờ sandbox/approval/model/profile/config là GLOBAL của Codex CLI. Một số bản CLI
        chấp nhận chúng sau ``exec``, nhưng bản trên VPS không nhận
        ``exec --ask-for-approval`` và thoát exit 2. Đặt tất cả global flag trước
        subcommand để tương thích cả bản cũ lẫn mới.
        """
        args = [self.cli_path]
        if self.sandbox:
            args += ["--sandbox", self.sandbox, "--ask-for-approval", "never"]
        else:
            args += ["--dangerously-bypass-approvals-and-sandbox"]
        if self.model:
            args += ["-m", self.model]
        if self.profile:
            args += ["-p", self.profile]
        for c in (self.extra_config or []):
            args += ["-c", c]
        args += ["exec", "--json", "--skip-git-repo-check"]
        if self.session_id:
            args += ["resume", self.session_id]
        args.append("-")
        return args

    async def query(self, prompt: str) -> AsyncIterator[dict]:
        if not self.cli_path:
            yield {"type": "error", "content": "Không tìm thấy Codex CLI (cần ChatGPT login qua codex)."}
            return
        resume_requested = bool(self.session_id)
        args = self._build_args()
        # Codex exec không nhận system-prompt riêng → gộp instructions (vai trò agent) vào đầu prompt.
        # Prompt bơm qua STDIN (positional "-") thay vì argv - né trần command line 32767 ký tự
        # của Windows (WinError 206 khi dán bài dài).
        full_prompt = (self.instructions.strip() + "\n\n" + prompt) if self.instructions else prompt
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        SENTINEL = object()

        def reader_thread():
            proc = None
            tinfo = {"timed_out": False}
            last = {"t": time.time()}
            from claude_sdk_engine import tran_watchdog
            # Ba trần, None = không giới hạn. Parity với engine Claude SDK, kể cả mặc định:
            # hai trần đo sự IM LẶNG của model đều bỏ trần (im lặng không phải treo - xem
            # `tran_watchdog`), riêng trần chờ TOOL giữ 1 tiếng vì nó đo một tiến trình con
            # có thật đang sống ngoài kia.
            IDLE = tran_watchdog("JAVIS_CLAUDE_IDLE_TIMEOUT", "0")
            TOOL_IDLE = tran_watchdog("JAVIS_CLAUDE_TOOL_TIMEOUT", "3600")
            FIRST_IDLE = tran_watchdog("JAVIS_CLAUDE_FIRST_TIMEOUT", "0")
            busy = {"n": 0}   # số item tool/lệnh đã started mà chưa completed
            seen = {"dong_dau": False}   # đã có dòng đầu tiên chưa (quyết định dùng trần nào)
            _TOOL_ITEMS = ("command_execution", "mcp_tool_call", "function_call",
                           "tool_call", "local_shell_call", "web_search_call")
            try:
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                proc = subprocess.Popen(
                    args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    cwd=self.cwd, text=True, encoding="utf-8", errors="replace", bufsize=1,
                    creationflags=creationflags, start_new_session=(os.name != "nt"),
                )
                with _PROC_LOCK:
                    _ACTIVE_PROCS[proc] = self.tag

                def _feed_stdin():
                    try:
                        proc.stdin.write(full_prompt)
                        proc.stdin.close()
                    except Exception:
                        pass
                threading.Thread(target=_feed_stdin, daemon=True).start()

                def _watchdog(p):
                    while p.poll() is None:
                        if busy["n"] > 0:
                            limit, ly_do = TOOL_IDLE, "tool"
                        elif seen["dong_dau"]:
                            limit, ly_do = IDLE, "im"
                        else:
                            limit, ly_do = FIRST_IDLE, "dau"
                        # limit None = trần đó bị tắt: cứ để codex chạy, người dùng bấm Dừng
                        # được và việc nền vẫn có trần wall-clock riêng.
                        if limit and time.time() - last["t"] > limit:
                            tinfo["timed_out"] = True
                            _kill_tree(p)
                            if ly_do == "tool":
                                err = (f"Tool chạy quá {int(TOOL_IDLE)}s chưa xong - đã dừng để tránh treo "
                                       f"server. (tăng JAVIS_CLAUDE_TOOL_TIMEOUT nếu tác vụ thật sự dài hơn, "
                                       f"đặt 0 để bỏ hẳn trần)")
                            elif ly_do == "dau":
                                err = (f"Codex chưa trả lời gì sau {int(FIRST_IDLE)}s - đã dừng để tránh treo "
                                       f"server. Hay gặp khi hội thoại đã rất dài: lượt đầu phải nạp lại toàn "
                                       f"bộ ngữ cảnh nên lâu. Mở hội thoại mới thường hết ngay. "
                                       f"(JAVIS_CLAUDE_FIRST_TIMEOUT=0 để bỏ hẳn trần này)")
                            else:
                                err = (f"Codex đang trả lời rồi im {int(IDLE)}s - đã dừng để tránh treo server. "
                                       f"(JAVIS_CLAUDE_IDLE_TIMEOUT=0 để bỏ hẳn trần này)")
                            asyncio.run_coroutine_threadsafe(queue.put({"__error__": err}), loop)
                            return
                        time.sleep(5)
                threading.Thread(target=_watchdog, args=(proc,), daemon=True).start()

                stderr_lines = []

                def read_stderr():
                    for line in proc.stderr:
                        line = line.rstrip()
                        if line:
                            stderr_lines.append(line)
                st = threading.Thread(target=read_stderr, daemon=True)
                st.start()
                for line in proc.stdout:
                    last["t"] = time.time()
                    seen["dong_dau"] = True   # có chữ rồi → từ đây dùng trần ngắn IDLE
                    line = line.strip()
                    if line:
                        # Theo dõi tool/lệnh đang chạy dở để watchdog nới trần đúng lúc
                        if '"item.started"' in line and any(t in line for t in _TOOL_ITEMS):
                            busy["n"] += 1
                        elif '"item.completed"' in line and any(t in line for t in _TOOL_ITEMS):
                            busy["n"] = max(0, busy["n"] - 1)
                        asyncio.run_coroutine_threadsafe(queue.put(line), loop)
                proc.wait()
                st.join(timeout=2)
                if proc.returncode not in (0, None) and stderr_lines and not tinfo["timed_out"]:
                    asyncio.run_coroutine_threadsafe(
                        queue.put({"__error__": "Codex lỗi (exit " + str(proc.returncode) + "):\n" + "\n".join(stderr_lines[-5:])}), loop)
            except Exception as e:
                traceback.print_exc()
                asyncio.run_coroutine_threadsafe(queue.put({"__error__": f"Codex subprocess: {type(e).__name__}: {e}"}), loop)
            finally:
                try:
                    if proc is not None:
                        with _PROC_LOCK:
                            _ACTIVE_PROCS.pop(proc, None)
                except Exception:
                    pass
                asyncio.run_coroutine_threadsafe(queue.put(SENTINEL), loop)

        threading.Thread(target=reader_thread, daemon=True).start()

        final_text = ""
        sandbox_hong = False
        while True:
            item = await queue.get()
            if item is SENTINEL:
                break
            if isinstance(item, dict) and "__error__" in item:
                yield {"type": "error", "content": item["__error__"]}
                continue
            # Soi trên DÒNG THÔ: output của lệnh nằm rải trong nhiều khuôn item khác nhau tuỳ
            # bản CLI, còn dấu vết của bwrap thì luôn đi qua đây nguyên văn.
            if not sandbox_hong and isinstance(item, str) and _SANDBOX_HONG.search(item):
                sandbox_hong = True
                print(f"[codex sandbox] rào riêng của Codex không khởi động được "
                      f"(sandbox={self.sandbox or 'bypass'}) - xem _NOTE_SANDBOX_HONG",
                      file=sys.stderr)
            try:
                ev = json.loads(item)
            except json.JSONDecodeError:
                continue
            t = ev.get("type")
            if t == "thread.started":
                thread_id = ev.get("thread_id") or ""
                if thread_id:
                    self.session_id = thread_id
                    # Phát ngay để caller lưu trước cả khi lượt bị ngắt giữa chừng.
                    yield {"type": "session", "session_id": thread_id}
            elif t == "item.completed":
                it = ev.get("item") or {}
                itype = it.get("type")
                if itype == "agent_message":
                    # Bóc dấu trích dẫn nội bộ của OpenAI TRƯỚC khi text đi bất cứ đâu. Nếu
                    # để lọt, ba ký tự vô hình đó hiện thành ô vuông giữa câu trả lời, VÀ đi
                    # thẳng vào lịch sử hội thoại - lượt sau model đọc lại rồi tưởng
                    # "turn4view0" là một nguồn có thật để trích dẫn tiếp.
                    txt = engine.strip_provider_markers(it.get("text") or "")
                    if txt.strip():
                        final_text += (("\n" if final_text else "") + txt)
                        yield {"type": "text", "content": txt}
                elif itype in ("mcp_tool_call", "command_execution", "function_call",
                               "tool_call", "local_shell_call", "web_search_call"):
                    name = it.get("name") or it.get("server") or it.get("command") or itype
                    # Kèm `item` THÔ. Codex không có trường file_path chuẩn hoá như Claude:
                    # đường dẫn nằm rải trong changes[]/arguments/command tuỳ loại item, và
                    # khuôn còn đổi theo bản CLI. Caller tự moi (channel_context
                    # .candidate_paths_from_tool) thay vì tầng này đoán một khuôn cố định.
                    yield {"type": "tool_call", "name": str(name)[:80], "item": it}
                elif itype:
                    # Item lạ (vd bản vá file) - KHÔNG dựng thành "đang gọi tool" để khỏi ồn,
                    # nhưng vẫn đẩy payload lên cho caller moi đường dẫn file vừa ghi.
                    yield {"type": "item", "item": it}
            elif t == "turn.completed":
                u = ev.get("usage") or {}
                # Dán lời giải thích vào chính bản báo cáo. Không dán thì thứ tới tay chủ là
                # một bài dài model tự kể lại nỗi bối rối của nó, và không ai đọc ra được là
                # phải đi sửa ở tầng container.
                if sandbox_hong:
                    final_text = (final_text + "\n\n" if final_text else "") + _NOTE_SANDBOX_HONG
                yield {"type": "final", "content": final_text, "session_id": self.session_id,
                       "tokens_in": (u.get("input_tokens") or 0) + (u.get("cached_input_tokens") or 0),
                       "tokens_out": u.get("output_tokens") or 0}
            elif t in ("error", "turn.failed", "thread.error", "stream.error"):
                msg = ev.get("message") or (ev.get("error") or {}).get("message") or json.dumps(ev)[:200]
                yield {"type": "error", "content": "Codex: " + str(msg),
                       "resume_failed": resume_requested and _looks_like_codex_resume_error(str(msg))}
