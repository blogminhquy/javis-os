"""Transport của engine Web: nói chuyện với một phiên trình duyệt ĐÃ ĐĂNG NHẬP.

Vì sao chọn cách này
--------------------
Ba đường khả dĩ để lấy chữ ra khỏi ChatGPT Web, và hai đường đầu đều chết:

  1. Dựng lại request `backend-api/conversation` bằng cookie. Phải tự giải proof-of-work
     sentinel và qua Cloudflare. Hỏng vài tuần một lần. LOẠI.
  2. Scrape DOM, đọc bong bóng chat cuối. Hỏng mỗi lần trang đổi giao diện. LOẠI.
  3. **Tee `window.fetch` ngay trong trang đã đăng nhập.** Trang tự lo auth, Cloudflare,
     proof-of-work; Javis chỉ đọc lại cái luồng mà trang VỐN ĐÃ nhận. CHỌN.

Hệ quả của cách 3: Javis không bao giờ chạm vào cookie, token hay PoW. Đổi cơ chế xác thực
không gãy. Chỉ gãy khi nhà cung cấp đổi hẳn khuôn sự kiện SSE, và khi đó lỗi là lỗi NÓI ĐƯỢC
(`TRANSPORT_BROKEN`) chứ không phải trả về chuỗi rỗng.

Ranh giới
---------
File này CHỈ biết cách bơm chữ vào một trang và lấy chữ ra. Nó không biết tool là gì, không
biết mức quyền, không biết brain. Mọi nghiệp vụ nằm ở lớp trên. Nhờ vậy `DeepSeekWebTransport`
sau này chỉ là một bảng selector khác, không phải một kiến trúc khác.

Mọi selector DOM nằm TRONG file này, trong đúng một hằng số. Rải selector khắp nơi là lần sau
trang đổi giao diện thì phải đi tìm.

Playwright là phụ thuộc TÙY CHỌN: thiếu nó thì `kha_dung()` trả False và engine Web tự ẩn,
phần còn lại của Javis chạy bình thường.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from config import STATE_DIR

# Phiên bản, để nhật ký nói được một lượt hỏng là do bản nào (spec mục 22).
# Khung nhìn CỐ ĐỊNH. Phải cố định thì toạ độ cú bấm trên dashboard mới quy đổi được về toạ độ
# trong trang: màn đăng nhập gửi xuống một cặp (x, y) tính theo ảnh chụp, và chỉ đúng khi ảnh
# và trang cùng một kích thước.
KHUNG = {"width": 1280, "height": 860}

TRANSPORT_VERSION = "chatgpt-web-tee-v1"
SELECTOR_VERSION = "chatgpt-2026-09"

PROFILE_DIR = Path(STATE_DIR) / "web-profiles" / "chatgpt"
URL_GOC = "https://chatgpt.com/"

# ============================================================
# SELECTOR: đúng MỘT nơi duy nhất trong cả Javis
# ============================================================
SELECTORS = {
    # Ô soạn. Thử lần lượt tới khi trúng, vì trang đổi khuôn theo đợt.
    "composer": [
        "#prompt-textarea",
        "div[contenteditable='true'][id='prompt-textarea']",
        "textarea[data-id='root']",
        "div.ProseMirror[contenteditable='true']",
    ],
    "send": [
        "button[data-testid='send-button']",
        "button[aria-label*='Send']",
        "button[data-testid='fruitjuice-send-button']",
    ],
    "stop": [
        "button[data-testid='stop-button']",
        "button[aria-label*='Stop']",
    ],
    # Dấu hiệu CHƯA đăng nhập.
    "login_marker": [
        "button[data-testid='login-button']",
        "a[href*='/auth/login']",
    ],
}

# Đường dẫn mà trang gọi khi gửi một tin nhắn. Tee chỉ quan tâm các request này.
_DUONG_LUONG = ("/backend-api/conversation", "/backend-alt/conversation")

# Id cuộc chat nằm trong chính URL: https://chatgpt.com/c/<uuid>. Đây là thứ DUY NHẤT cho
# phép hai hội thoại Javis khác nhau gõ vào hai cuộc chat khác nhau trên cùng một tài khoản.
_THREAD_RE = re.compile(r"/c/([0-9a-zA-Z-]{8,})")

# Đoạn JS bọc `window.fetch`. Chạy TRƯỚC mọi script của trang (`add_init_script`), nên nó bọc
# được cả lời gọi đầu tiên.
#
# Không đụng cookie, không đụng token: chỉ tee lại body mà trang vốn đã nhận. `tee()` đọc một
# nhánh của stream, nhánh kia trả về nguyên vẹn cho trang, nên giao diện vẫn chạy bình thường
# và người dùng nhìn vào không thấy khác gì.
JS_TEE = r"""
(() => {
  if (window.__javisTee) return;
  window.__javisTee = true;
  window.__javisChunks = [];
  const duong = %DUONG%;
  const goc = window.fetch;
  window.fetch = async function (...args) {
    const res = await goc.apply(this, args);
    try {
      const url = (args[0] && (args[0].url || args[0])) + "";
      if (!duong.some((d) => url.indexOf(d) !== -1)) return res;
      if (!res.body) return res;
      const [choTrang, choJavis] = res.body.tee();
      (async () => {
        const reader = choJavis.getReader();
        const dec = new TextDecoder();
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          const s = dec.decode(value, { stream: true });
          window.__javisChunks.push(s);
          if (window.__javisOnChunk) { try { window.__javisOnChunk(s); } catch (e) {} }
        }
        window.__javisChunks.push("\u0000DONE\u0000");
        if (window.__javisOnChunk) { try { window.__javisOnChunk("\u0000DONE\u0000"); } catch (e) {} }
      })();
      return new Response(choTrang, {
        status: res.status, statusText: res.statusText, headers: res.headers,
      });
    } catch (e) {
      return res;
    }
  };
})();
"""

MOC_XONG = "\u0000DONE\u0000"


def js_tee() -> str:
    """Đoạn JS đã nhét danh sách đường dẫn cần tee."""
    return JS_TEE.replace("%DUONG%", json.dumps(list(_DUONG_LUONG)))


# ============================================================
# Bóc chữ ra khỏi luồng SSE
# ============================================================

def ghep_delta(chunks) -> str:
    """Ghép các mẩu SSE đã tee thành câu trả lời.

    Khuôn của ChatGPT Web đổi theo đợt, nên hàm này nhận BA khuôn và bỏ qua cái không hiểu
    thay vì nổ:
      - `{"v": "<chữ>"}` hoặc `{"o":"append","v":"<chữ>"}` - khuôn delta gọn hiện hành
      - `{"message": {"content": {"parts": ["..."]}}}` - khuôn cũ, mỗi mẩu là TOÀN BỘ câu
      - dòng `data: [DONE]`

    PURE: không đụng trình duyệt, nên test được bằng một chuỗi chép tay.
    """
    ra = []
    toan_bo = ""
    for mau in chunks or []:
        if mau == MOC_XONG:
            continue
        for dong in str(mau).splitlines():
            dong = dong.strip()
            if not dong.startswith("data:"):
                continue
            than = dong[5:].strip()
            if not than or than == "[DONE]":
                continue
            try:
                obj = json.loads(than)
            except (TypeError, ValueError):
                continue
            if not isinstance(obj, dict):
                continue
            # Khuôn delta gọn: {"v": "..."} , có thể kèm "o":"append" và "p" là đường dẫn.
            v = obj.get("v")
            if isinstance(v, str) and obj.get("o") in (None, "append"):
                p = obj.get("p")
                # `p` rỗng hoặc trỏ vào parts mới là chữ trả lời; trỏ chỗ khác là metadata.
                if p in (None, "", "/message/content/parts/0"):
                    ra.append(v)
                continue
            # Khuôn cũ: mỗi mẩu mang TOÀN BỘ câu trả lời tới thời điểm đó.
            msg = obj.get("message")
            if isinstance(msg, dict):
                parts = ((msg.get("content") or {}).get("parts") or [])
                if parts and isinstance(parts[0], str):
                    toan_bo = parts[0]
    # Khuôn cũ thắng khi có, vì nó đã là toàn văn; khuôn delta thì phải ghép.
    return toan_bo if (toan_bo and not ra) else "".join(ra)


# ============================================================
# Transport
# ============================================================

@dataclass
class KetQuaGui:
    ok: bool
    text: str = ""
    error: str = ""
    kind: str = ""
    elapsed: float = 0.0
    thread_id: str = ""
    chunks: list = field(default_factory=list)


# Kết quả dò trình duyệt, nhớ lại giữa các lần gọi. `kha_dung()` được gọi mỗi lần vẽ trang
# Models và mỗi lần nạp danh mục model, mà việc dò thì `import playwright` cộng quét đĩa.
# Xoá bằng `dat_lai_do()` sau khi người dùng vừa tải trình duyệt về.
_NHO_DO: dict = {}


def _cong_moi_truong():
    """Biến `JAVIS_ENABLE_WEB_CHAT` có BA trạng thái, không phải hai.

        chưa đặt  -> None  = TỰ DÒ (mặc định từ 0.64.6)
        1/true/…  -> True  = cho phép, nhưng vẫn phải có trình duyệt thật
        0/false/… -> False = ép TẮT, kể cả máy có đủ đồ

    Vì sao mặc định là tự dò chứ không phải tắt: bản 0.64.0 bắt đặt biến này mới thấy model,
    và đó là bắt người dùng tự khai một thứ máy tự biết. Còn vì sao không đơn giản bật sẵn:
    engine này cần một trình duyệt thật, mà phần lớn máy chạy Javis là VPS không màn hình và
    chưa tải trình duyệt. Bật sẵn ở đó là để một model nằm trong ô chọn rồi hỏng lúc được
    chọn - tệ hơn hẳn việc nó không xuất hiện.

    Trạng thái ÉP TẮT vẫn cần: máy có đủ đồ nhưng chủ máy không muốn ai lái phiên ChatGPT
    của mình từ Javis.
    """
    raw = os.environ.get("JAVIS_ENABLE_WEB_CHAT", "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return None


def co_trinh_duyet(dung_nho: bool = True) -> tuple[bool, str]:
    """Máy này có ĐỦ ĐỒ để lái một phiên ChatGPT không. (True, "") hoặc (False, lý do).

    Lý do trả về phải NÓI ĐƯỢC VIỆC CẦN LÀM, không phải "không khả dụng": đây là chữ hiện
    thẳng trên thẻ ChatGPT ở trang Models, và người đọc nó đang muốn biết bấm gì tiếp.
    """
    if dung_nho and "kq" in _NHO_DO:
        return _NHO_DO["kq"]

    def _tra(ok, ly_do):
        _NHO_DO["kq"] = (ok, ly_do)
        return _NHO_DO["kq"]

    # Nạp thư mục thư viện Javis tự cài TRƯỚC khi thử import. Không có bước này thì người dùng
    # bấm cài ở trang Công cụ, thấy báo xong, rồi tính năng vẫn bảo thiếu thư viện.
    try:
        import optional_tools
        optional_tools.nap_pylibs()
    except Exception:
        pass

    try:
        import playwright  # noqa: F401
    except ImportError:
        return _tra(False, (
            "Chưa có thư viện lái trình duyệt. Mở trang Công cụ rồi bấm cài mục "
            "\"Thư viện lái trình duyệt (playwright)\", xong khởi động lại Javis. "
            "Gói này không nằm sẵn trong bản cài vì nó nặng và phần lớn máy không cần."))

    if not _tim_chromium():
        return _tra(False, (
            "Chưa có trình duyệt nào Javis lái được. Mở trang Công cụ rồi bấm tải Chromium "
            "(Javis tải bản gọn về thư mục state, sống qua mỗi lần cập nhật)."))

    return _tra(True, "")


def dat_lai_do() -> None:
    """Quên kết quả dò. Gọi sau khi người dùng vừa tải trình duyệt hoặc cài playwright."""
    _NHO_DO.clear()


def kha_dung() -> tuple[bool, str]:
    """Engine Web dùng được trên máy này không. (True, "") hoặc (False, lý do nói được)."""
    cong = _cong_moi_truong()
    if cong is False:
        return False, ("Engine ChatGPT Web đang bị tắt bằng biến môi trường "
                       "JAVIS_ENABLE_WEB_CHAT=0. Bỏ biến đó đi rồi khởi động lại nếu muốn dùng.")
    return co_trinh_duyet()


def _tim_chromium() -> str:
    """Đường dẫn Chromium, hỏi THẲNG `optional_tools`. "" = để Playwright tự lo.

    Từ 0.64.9 hàm này không tự dò nữa mà uỷ hết cho chỗ đã tải trình duyệt về. Bản cũ tự dò
    một kiểu riêng và bỏ sót `chrome-linux/headless_shell`, nên trang Công cụ báo "Sẵn sàng"
    còn thẻ ChatGPT vẫn nói chưa có trình duyệt (chủ repo báo 22/09). Hai chỗ trả lời cùng một
    câu hỏi thì sớm muộn cũng lệch nhau; giờ chỉ còn một.
    """
    try:
        import optional_tools
        return optional_tools.duong_dan_chrome()
    except Exception:
        return ""


class ChatGPTWebTransport:
    """Một phiên trình duyệt cố định. MỘT lượt tại một thời điểm (xem `_khoa`)."""

    def __init__(self, profile_dir: Optional[str] = None, headless: bool = True,
                 executable_path: str = "", url: str = URL_GOC):
        self.profile_dir = str(profile_dir or PROFILE_DIR)
        # ẨN là mặc định từ 0.64.8. Trước đó phải hiện cửa sổ thì chủ máy mới gõ được mật
        # khẩu, và đúng chỗ đó khiến cả tính năng không dùng được trên VPS. Nay màn đăng nhập
        # nhìn qua dashboard nên không còn cần một màn hình thật nào.
        self.headless = headless
        self.executable_path = executable_path or _tim_chromium()
        self.url = url
        self._pw = None
        self._ctx = None
        self._page = None
        # Cùng một profile, cùng một tài khoản: hai lượt song song là hai tab cùng gõ vào một
        # ô soạn. Khoá ở đây, không để chỗ gọi tự nhớ.
        self._khoa = threading.Lock()
        # MỘT thread cố định cho mọi lời gọi Playwright. Đây KHÔNG phải tối ưu, mà là điều
        # kiện để thư viện chạy được: bản đồng bộ của Playwright bám vào greenlet của đúng
        # thread đã khởi tạo nó, gọi từ thread khác là `greenlet.error: Cannot switch to a
        # different thread`.
        #
        # Mã trước 0.64.8 gọi thẳng qua `asyncio.to_thread`, và chạy được chỉ vì may: pool của
        # asyncio dùng lại đúng một thread KHI các lời gọi nối đuôi nhau. Hai request chồng
        # nhau là rơi sang thread khác và chết. Đã dựng lại bằng thí nghiệm, không suy luận.
        self._may = ThreadPoolExecutor(max_workers=1, thread_name_prefix="javis-web")

    # ---- mọi lời gọi Playwright đi qua ĐÚNG MỘT thread ----

    def _chay(self, fn, *a, tran_gio: float = 300.0, **k):
        """Chạy `fn` trên thread riêng của transport và chờ kết quả.

        Vỏ này là thứ giữ cho Playwright sống: xem chú thích của `self._may`. Ném ra ngoài
        đúng những gì `fn` ném, nên chỗ gọi không phải biết là có một thread ở giữa.
        """
        return self._may.submit(fn, *a, **k).result(timeout=tran_gio)

    def _ban(self) -> bool:
        """Đang có một lượt chat chạy dở không. Không chờ, chỉ hỏi."""
        return self._khoa.locked()

    def san_sang(self) -> tuple[bool, str]:
        """Đối tượng NÀY mở được trình duyệt không. (True, "") hoặc (False, lý do nói được).

        Khác `kha_dung()` cấp module ở đúng một chỗ: đã tự cầm đường dẫn trình duyệt thì
        không cần đi dò nữa.
        """
        if self.executable_path:
            cong = _cong_moi_truong()
            if cong is False:
                return False, ("Engine ChatGPT Web đang bị tắt bằng biến môi trường "
                               "JAVIS_ENABLE_WEB_CHAT=0.")
            try:
                import optional_tools
                optional_tools.nap_pylibs()
            except Exception:
                pass
            try:
                import playwright  # noqa: F401
            except ImportError:
                return False, ("Chưa có thư viện lái trình duyệt. Mở trang Công cụ rồi bấm "
                               "cài mục \"Thư viện lái trình duyệt (playwright)\".")
            return True, ""
        return kha_dung()

    # ---- vòng đời ----

    def _mo_that(self) -> tuple[bool, str]:
        """Mở trình duyệt với profile cố định. Chủ máy đăng nhập TAY một lần vào profile này."""
        if self._page is not None:
            return True, ""
        # Hỏi theo CHÍNH đối tượng này chứ không hỏi hàm dò cấp module: chỗ gọi có thể đã
        # chỉ đích danh một trình duyệt (`executable_path`), và lúc đó "máy này chưa có trình
        # duyệt nào" là câu trả lời sai cho một câu hỏi khác.
        ok, ly_do = self.san_sang()
        if not ok:
            return False, ly_do
        from playwright.sync_api import sync_playwright
        try:
            Path(self.profile_dir).mkdir(parents=True, exist_ok=True)
            self._pw = sync_playwright().start()
            kw = {"headless": self.headless, "viewport": dict(KHUNG),
                  "args": ["--disable-blink-features=AutomationControlled"]}
            if self.executable_path:
                kw["executable_path"] = self.executable_path
            self._ctx = self._pw.chromium.launch_persistent_context(self.profile_dir, **kw)
            self._ctx.add_init_script(js_tee())
            self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
            return True, ""
        except Exception as e:
            self.dong()
            return False, f"Không mở được trình duyệt: {type(e).__name__}: {e}"

    def _dong_that(self) -> None:
        for ten in ("_ctx", "_pw"):
            doi_tuong = getattr(self, ten, None)
            if doi_tuong is None:
                continue
            try:
                doi_tuong.close() if ten == "_ctx" else doi_tuong.stop()
            except Exception:
                pass
            setattr(self, ten, None)
        self._page = None

    # ---- tiện ích DOM, đúng một chỗ ----

    def _tim(self, nhom: str, timeout_ms: int = 4000):
        """Phần tử đầu tiên khớp một trong các selector của nhóm. None nếu không có."""
        for sel in SELECTORS.get(nhom, []):
            try:
                el = self._page.wait_for_selector(sel, timeout=timeout_ms, state="visible")
                if el:
                    return el
            except Exception:
                continue
        return None

    def _da_dang_nhap_that(self) -> bool:
        """Trang hiện đang có phiên đăng nhập không."""
        if self._page is None:
            return False
        for sel in SELECTORS["login_marker"]:
            try:
                if self._page.query_selector(sel):
                    return False
            except Exception:
                continue
        return self._tim("composer", timeout_ms=3000) is not None

    # ---- luồng nào ----

    def thread_hien_tai(self) -> str:
        """Id cuộc chat trang đang mở. Rỗng = đang ở trang gốc (chưa có cuộc nào)."""
        try:
            m = _THREAD_RE.search(self._page.url or "")
            return m.group(1) if m else ""
        except Exception:
            return ""

    def _ve_dung_luong(self, thread_id: str) -> tuple[bool, str]:
        """Đưa trang về ĐÚNG cuộc chat sắp gõ vào.

        Bước này KHÔNG phải tiểu tiết. Transport là MỘT trình duyệt dùng chung cho mọi hội
        thoại Javis, nên thiếu nó thì hội thoại B gõ tiếp vào cuộc chat mà hội thoại A vừa
        mở: hai mạch trộn làm một, và người dùng thấy Javis "nhớ" những thứ họ nói ở chỗ khác.

        `thread_id` rỗng nghĩa là hội thoại này CHƯA có cuộc chat nào, nên phải mở cuộc MỚI
        chứ không được gõ tiếp vào cuộc đang hiện trên màn hình.
        """
        goc = (self.url or "").rstrip("/")
        hien = self.thread_hien_tai()
        try:
            if thread_id and hien != thread_id:
                dich = f"{goc}/c/{thread_id}"
            elif not thread_id and hien:
                dich = self.url
            elif not (self._page.url or "").startswith(goc):
                dich = self.url
            else:
                return True, ""
            self._page.goto(dich, wait_until="domcontentloaded", timeout=45_000)
            self._page.evaluate("window.__javisChunks = []")
            return True, ""
        except Exception as e:
            return False, f"Không mở được trang: {type(e).__name__}: {e}"

    # ---- gửi một lượt ----

    def _gui_that(self, prompt: str, timeout_s: float = 180.0,
            on_chunk: Optional[Callable[[str], None]] = None,
            thread_id: str = "") -> KetQuaGui:
        """Gửi một tin nhắn, chờ luồng trả lời xong, trả về chữ.

        KHÔNG ném. Mọi cảnh hỏng đều thành `KetQuaGui` có `kind` để lớp trên ghi sổ trạng thái.
        """
        t0 = time.time()
        ok, ly_do = self._mo_that()
        if not ok:
            return KetQuaGui(False, kind="TRANSPORT_BROKEN", error=ly_do)

        ok_luong, loi_luong = self._ve_dung_luong(thread_id)
        if not ok_luong:
            return KetQuaGui(False, kind="TRANSPORT_BROKEN", error=loi_luong)

        if not self._da_dang_nhap_that():
            return KetQuaGui(False, kind="AUTH_REQUIRED",
                             error="Phiên ChatGPT Web chưa đăng nhập hoặc đã hết hạn.")

        o_soan = self._tim("composer")
        if o_soan is None:
            return KetQuaGui(False, kind="TRANSPORT_BROKEN",
                             error=(f"Không tìm thấy ô soạn trên trang (selector "
                                    f"{SELECTOR_VERSION}). Trang có thể vừa đổi giao diện."))

        try:
            self._page.evaluate("window.__javisChunks = []")
            o_soan.click()
            o_soan.type(str(prompt or ""), delay=0)
            nut = self._tim("send", timeout_ms=3000)
            if nut is not None:
                nut.click()
            else:
                self._page.keyboard.press("Enter")
        except Exception as e:
            return KetQuaGui(False, kind="TRANSPORT_BROKEN",
                             error=f"Không gửi được tin nhắn: {type(e).__name__}: {e}")

        kq = self._cho_luong(t0, timeout_s, on_chunk)
        # Cuộc chat MỚI chỉ có id sau khi trang tự điều hướng sang /c/<id>, nên đọc id ở
        # đây chứ không đọc trước khi gửi. Đọc không ra thì để rỗng: lượt sau mở cuộc mới
        # và mồi lại transcript đã lưu, chậm hơn nhưng không mất ngữ cảnh.
        kq.thread_id = self.thread_hien_tai()
        return kq

    def _cho_luong(self, t0: float, timeout_s: float,
                   on_chunk: Optional[Callable[[str], None]]) -> KetQuaGui:
        """Đọc `window.__javisChunks` tới khi thấy mốc xong hoặc hết giờ."""
        da_doc = 0
        moc = time.time() + max(5.0, float(timeout_s))
        while time.time() < moc:
            try:
                chunks = self._page.evaluate("window.__javisChunks || []")
            except Exception as e:
                return KetQuaGui(False, kind="TRANSPORT_BROKEN", elapsed=time.time() - t0,
                                 error=f"Mất kết nối với trang: {type(e).__name__}: {e}")
            if on_chunk and len(chunks) > da_doc:
                for c in chunks[da_doc:]:
                    if c != MOC_XONG:
                        try:
                            on_chunk(c)
                        except Exception:
                            pass
                da_doc = len(chunks)
            if chunks and chunks[-1] == MOC_XONG:
                text = ghep_delta(chunks)
                if not text.strip():
                    return KetQuaGui(False, kind="TRANSPORT_BROKEN", chunks=chunks,
                                     elapsed=time.time() - t0,
                                     error=("Luồng trả lời kết thúc nhưng không bóc được chữ "
                                            "nào. Khuôn sự kiện của trang có thể đã đổi."))
                return KetQuaGui(True, text=text, chunks=chunks, elapsed=time.time() - t0)
            time.sleep(0.4)
        return KetQuaGui(False, kind="QUA_HAN", elapsed=time.time() - t0,
                         error=f"Chờ quá {int(timeout_s)} giây mà trang chưa trả lời xong.")

    def _dung_that(self) -> None:
        """Bấm nút Dừng trên trang, nếu có."""
        try:
            el = self._tim("stop", timeout_ms=1500)
            if el:
                el.click()
        except Exception:
            pass

    def _luong_moi_that(self) -> None:
        """Mở một luồng web mới (về trang gốc)."""
        try:
            self._page.goto(self.url, wait_until="domcontentloaded", timeout=45_000)
            self._page.evaluate("window.__javisChunks = []")
        except Exception:
            pass

    # ---- màn đăng nhập nhìn qua dashboard ----
    #
    # VPS không có màn hình nào để mở cửa sổ Chromium cho chủ máy gõ mật khẩu. Nhưng Javis đã
    # lái trang bằng Playwright rồi, nên nó chụp được trang và bấm hộ được. Ghép hai thứ đó
    # lại là một màn đăng nhập nhìn qua dashboard: chủ máy thấy ĐÚNG trang ChatGPT thật và
    # thao tác lên chính nó, chỉ là qua một lớp ảnh.
    #
    # Đánh đổi phải nói thẳng, và chủ repo đã biết khi duyệt (22/09): phím gõ, gồm cả mật
    # khẩu, ĐI QUA máy chủ Javis. Nên ở đây KHÔNG ghi nhật ký nội dung phím, không giữ lại
    # chuỗi đã gõ, và đường vào phải đòi phiên đăng nhập thật (xem routes ở main.py).

    def _mo_dang_nhap_that(self) -> tuple[bool, str]:
        ok, ly_do = self._mo_that()
        if not ok:
            return False, ly_do
        try:
            if not (self._page.url or "").startswith(self.url.rstrip("/")):
                self._page.goto(self.url, wait_until="domcontentloaded", timeout=45_000)
        except Exception as e:
            return False, f"Không mở được trang: {type(e).__name__}: {e}"
        return True, ""

    def _chup_that(self) -> bytes:
        return self._page.screenshot(type="jpeg", quality=60, full_page=False)

    def _bam_that(self, x: float, y: float) -> None:
        self._page.mouse.click(float(x), float(y))

    def _go_that(self, chu: str) -> None:
        # `insert_text` chứ không phải gõ từng phím: nhanh hơn hẳn và không sinh ra chuỗi phím
        # trung gian nào để mà lỡ ghi lại.
        self._page.keyboard.insert_text(str(chu))

    def _phim_that(self, ten: str) -> None:
        self._page.keyboard.press(str(ten))

    def _cuon_that(self, dy: float) -> None:
        self._page.mouse.wheel(0, float(dy))

    # ---- vỏ công khai: giữ nguyên tên cũ, nay đi qua thread riêng ----

    def mo(self) -> tuple[bool, str]:
        return self._chay(self._mo_that, tran_gio=120.0)

    def dong(self) -> None:
        try:
            self._chay(self._dong_that, tran_gio=30.0)
        except Exception:
            pass

    def da_dang_nhap(self) -> bool:
        try:
            return bool(self._chay(self._da_dang_nhap_that, tran_gio=30.0))
        except Exception:
            return False

    def gui(self, prompt: str, timeout_s: float = 180.0,
            on_chunk: Optional[Callable[[str], None]] = None,
            thread_id: str = "") -> KetQuaGui:
        """Gửi một tin nhắn. MỘT lượt tại một thời điểm trên cùng một profile."""
        if not self._khoa.acquire(blocking=False):
            return KetQuaGui(False, kind="BUSY",
                             error="Đang có một lượt ChatGPT Web chạy dở. Chờ nó xong đã.")
        try:
            return self._chay(self._gui_that, prompt, timeout_s, on_chunk, thread_id,
                              tran_gio=max(60.0, float(timeout_s) + 120.0))
        except Exception as e:
            return KetQuaGui(False, kind="TRANSPORT_BROKEN",
                             error=f"Lượt web hỏng: {type(e).__name__}: {e}")
        finally:
            self._khoa.release()

    def dung(self) -> None:
        try:
            self._chay(self._dung_that, tran_gio=20.0)
        except Exception:
            pass

    def luong_moi(self) -> None:
        try:
            self._chay(self._luong_moi_that, tran_gio=60.0)
        except Exception:
            pass

    # ---- vỏ công khai của màn đăng nhập ----

    def mo_dang_nhap(self) -> tuple[bool, str]:
        """Mở trang ChatGPT để chủ máy đăng nhập qua dashboard. CHẠY ẨN, không cần màn hình."""
        try:
            return self._chay(self._mo_dang_nhap_that, tran_gio=120.0)
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    def chup(self) -> tuple[bytes, str]:
        """Ảnh JPEG của trang, hoặc (b"", lý do). Không chờ nếu đang có lượt chat chạy dở."""
        if self._page is None:
            return b"", "Chưa mở trình duyệt."
        if self._ban():
            return b"", "Đang có một lượt chat chạy dở, chờ nó xong đã."
        try:
            return self._chay(self._chup_that, tran_gio=20.0), ""
        except Exception as e:
            return b"", f"{type(e).__name__}: {e}"

    def thao_tac(self, loai: str, **k) -> str:
        """Chuyển một thao tác của chủ máy xuống trang. Trả "" nếu xong, hoặc lý do hỏng.

        Gom một cửa thay vì bốn hàm công khai: chỗ gọi là MỘT endpoint nhận JSON, nên tách ra
        chỉ thêm bốn chỗ phải nhớ kiểm `_ban()` và bắt lỗi y hệt nhau.
        """
        if self._page is None:
            return "Chưa mở trình duyệt."
        if self._ban():
            return "Đang có một lượt chat chạy dở, chờ nó xong đã."
        viec = {"bam": (self._bam_that, ("x", "y")),
                "go": (self._go_that, ("chu",)),
                "phim": (self._phim_that, ("ten",)),
                "cuon": (self._cuon_that, ("dy",))}.get(str(loai or ""))
        if not viec:
            return f"Không có thao tác tên {loai!r}."
        fn, ten_tham_so = viec
        try:
            return self._chay(fn, *[k.get(t) for t in ten_tham_so], tran_gio=30.0) or ""
        except Exception as e:
            return f"{type(e).__name__}: {e}"


# ============================================================
# Transport dùng chung cả tiến trình
# ============================================================
#
# MỘT profile trình duyệt = MỘT tài khoản ChatGPT, và Chromium khoá độc quyền thư mục profile.
# Nên dựng hai đối tượng transport là cái thứ hai không mở nổi trình duyệt, hỏng ngay ở lượt
# chat thứ hai của người dùng chứ không phải trong một cảnh hiếm. Giữ đúng một cái ở đây, thay
# vì để mỗi chỗ gọi tự nhớ luật đó.

_CHUNG: Optional["ChatGPTWebTransport"] = None
_KHOA_CHUNG = threading.Lock()


def chung() -> "ChatGPTWebTransport":
    """Transport dùng chung. Chưa mở trình duyệt - `gui()` tự mở ở lượt đầu."""
    global _CHUNG
    with _KHOA_CHUNG:
        if _CHUNG is None:
            _CHUNG = ChatGPTWebTransport()
        return _CHUNG


def dong_chung() -> None:
    """Đóng trình duyệt dùng chung. Gọi khi tắt server, hoặc khi chủ máy bấm đăng xuất."""
    global _CHUNG
    with _KHOA_CHUNG:
        if _CHUNG is not None:
            try:
                _CHUNG.dong()
            except Exception:
                pass
            _CHUNG = None
