# Khảo sát bảo mật (v0.103.0)

**Phiên bản tài liệu:** v1. Ảnh chụp tại commit `eb73383`, ngày 2026-10-13.
**Phạm vi:** toàn bộ repo (nhánh `main` sạch, không có diff để soát). Trọng tâm: `server/` (217 module Python), `dashboard/`, `system/plugins/`, Docker, script khởi động.
**Cách đọc:** mỗi phát hiện đều kèm `file:line` đã kiểm chứng trực tiếp. Mức độ theo tác động thật, không theo mức "nghe ghê".

Tài liệu này ghi **vì sao** một chỗ là rủi ro và **sửa thì sửa ở đâu**. Cái gì thì đọc code là ra.

---

## 1. Tóm tắt

Nền bảo mật của Javis tốt hơn mức thường thấy ở một dự án cùng quy mô. Phần HTTP đã được siết có chủ đích và có tài liệu giải thích đánh đổi ngay trong code: CSRF, DNS-rebinding, Host header, cookie session, chống traversal, chống SSRF, chống zip-slip đều có thật và đúng.

Rủi ro còn lại không nằm ở "quên kiểm tra đầu vào". Nó nằm ở **mô hình quyền**: mặc định một lượt chat thường chạy ở mức `full` (được ghi, được chạy lệnh) và engine gọi Claude CLI với `--dangerously-bypass-approvals-and-sandbox`. Nghĩa là hàng rào duy nhất giữa "một câu chữ lọt vào ngữ cảnh" và "lệnh chạy trên máy chủ" là **phán đoán của mô hình**, không phải code. Bốn phát hiện dưới đây là các lỗ hổng cụ thể trên đường đó.

Thứ tự ưu tiên ở mục 4. Hai việc đầu (F1, F2) đáng làm trước, và cả hai đều là thay đổi gọn.

---

## 2. Nền tảng đã tốt (giữ nguyên, đừng phá)

Ghi lại để lần sau ai sửa cũng biết đây là chủ đích, không phải tình cờ.

- **Chống CSRF và DNS-rebinding** ở `server/web_security.py`. Hai hàm thuần, dễ test: `csrf_decision()` (dòng 155) và `navigation_decision()` (dòng 141). Chặn `Sec-Fetch-Site` là `cross-site` lẫn `same-site` cho các GET có tác dụng phụ (`SIDE_EFFECT_GET`, dòng 47). Đánh đổi với trình duyệt cũ đã ghi rõ trong docstring.
- **Auth gate** ở `server/main.py:252` (`_csrf_guard`). Dùng `scope["path"]` chứ không dùng `request.url.path`. Đây là chi tiết quan trọng: họ tự vá lỗ Host-header path-confusion của starlette (đã có advisory), nên `url.path` bị nhiễm tiền tố từ Host giả.
- **`external_base()`** (`web_security.py:53`) cố ý **không** tin `X-Forwarded-Host`/`X-Forwarded-Proto` để quyết định quyền. Suy đoán từ header chỉ dùng cho cảnh báo UX (`host_kieu_local()`, dòng 89, có ghi chú rõ).
- **`/files/raw`** dùng `_safe_serve_path()` (`main.py`), chặn `..`, resolve symlink rồi mới kiểm tra nằm trong gốc. Không phải so chuỗi.
- **Chống SSRF khi tải pack** (`server/packs_fetch.py`): chặn đích vào mạng private, và kiểm tra lại **từng chặng redirect**, không chỉ URL gốc. Đúng cách.
- **Chống zip-slip khi cài pack** (`server/pack_install.py`): kiểm tra từng thành viên archive trước khi ghi ra đĩa.
- **Webhook WhatsApp** (`server/main.py:20972`) xác thực `X-Hub-Signature-256` bằng `hmac.compare_digest`. Các bot còn lại (Telegram, Zalo, Slack, Discord) **không** mở cổng vào, chúng kết nối ra ngoài. Đây là lựa chọn an toàn hơn, giữ nguyên.
- **Cookie session** `httponly=True, samesite="lax"` (`main.py:1332`).
- **Ghi mật khẩu** bằng `scrypt`, không phải hash nhanh.
- **Khoá mã hoá secret** (`server/secrets_store.py`): Fernet, và file khoá được `chmod 0o600`.
- **`server/fastyaml.py`** chỉ dùng `CSafeLoader`/`SafeLoader`. Không có `yaml.load` trần.
- **Không có `eval`/`exec` nào trong `server/`.** Không có `shell=True` với chuỗi dựng từ input (5 chỗ `shell=True` đều là hằng số hoặc argv-only).
- **Không có `verify=False`** ở đâu trong repo.
- **Phụ thuộc** được ghim chặt và có ý thức bảo mật: `requirements.txt:18` ghi rõ lý do nâng `starlette==1.6.0` (đóng 7 advisory).
- **Plugin gate** `JAVIS_ENABLE_USER_PLUGINS` (`server/plugins_host.py`). Plugin người dùng chỉ chạy khi được bật, và plugin của pack còn đòi thêm chữ ký tin cậy (`_pack_duoc_nap`, dòng 575).
- **Rate limit đăng nhập**: sai nhiều lần trả 429 (`main.py:1391`).
- **Bộ render chat** `dashboard/chat-render.js` đã được làm cứng có chủ đích: allowlist scheme qua `safeHref` (chặn `javascript:`, `data:`), iframe `sandbox` rỗng, mermaid `securityLevel: "strict"`. Đây là điểm sáng hiếm thấy.

---

## 3. Phát hiện

### F1. Mặc định lượt chat là `full` + engine bỏ qua approval và sandbox (Mức: CAO)

**Vị trí**
- `server/main.py:5847` `_muc_quyen_luot_chat()` trả `"full"` cho chat thường. Docstring nói thẳng: "Khung chat thường xưa nay chạy `full`".
- `server/claude_cli.py:1529` `self.sandbox = None` (mặc định), và `server/claude_cli.py:1556` khi sandbox rỗng thì thêm `--dangerously-bypass-approvals-and-sandbox`.

**Chuyện gì**
Một lượt chat bình thường chạy với toàn quyền ghi và chạy lệnh, và engine được lệnh bỏ qua mọi bước hỏi duyệt cùng sandbox. Hàng rào còn lại giữa ngữ cảnh và shell là mô hình tự quyết định.

**Khai thác**
Nội dung không tin cậy đi vào cùng ngữ cảnh với chỉ dẫn hệ thống: trang web do agent tự tải, mô tả tool do MCP server bên thứ ba cung cấp, tin nhắn khách hàng ở kênh chatbot, nội dung file trong vault. Một trong số đó chứa câu chỉ dẫn (prompt injection) là đủ để agent gọi tool chạy lệnh, và không có bước nào trong code chặn lại. Đây là rủi ro cốt lõi của sản phẩm, không phải lỗi lập trình đơn lẻ.

**Khuyến nghị**
1. Đổi mặc định của `_muc_quyen_luot_chat()` sang `auto` cho chat thường, để `full` phải là lựa chọn có ý thức của người dùng. Đây là việc phải cân nhắc UX (docstring cảnh báo đúng rằng đổi mặc định là âm thầm siết mọi cuộc trò chuyện đang có), nên cần một thông báo rõ khi nâng cấp.
2. Giữ `--dangerously-bypass-approvals-and-sandbox` cho phiên coding do người dùng chủ động mở, bỏ khỏi chat thường.
3. Cân nhắc tách ngữ cảnh: nội dung tải về từ ngoài không nằm chung khối chỉ dẫn hệ thống, và đánh dấu rõ ranh giới (spotlighting) thay vì tin mô hình tự phân biệt.

---

### F2. Denylist trong `run_command` bị qua mặt (Mức: CAO)

**Vị trí** `server/run_command.py`
- `CHAN_CUNG` (danh sách chặn cứng) gồm các tên shell: `sh`, `bash`, `cmd`, `powershell`...
- `ALLOWLIST_AUTO` (dòng 77) là allowlist của mức `auto`.
- `kiem_quyen()` (dòng 160) phân nhánh theo mức.

**Chuyện gì**
Đây là **blocklist tên chương trình**. Blocklist tên chương trình luôn thua: gọi shell bằng đường dẫn tuyệt đối, bằng tên khác (`dash`, `busybox sh`, `env sh`), bằng trình thông dịch khác đã có trong allowlist (`python`, `node`, `perl`), hoặc qua một binary khác thực thi được lệnh. Chỉ cần một chương trình trong `ALLOWLIST_AUTO` nhận tham số kiểu "chạy file này" là qua được toàn bộ ý định của `CHAN_CUNG`.

**Khai thác**
Agent (hoặc prompt injection ở F1) gọi tool chạy lệnh ở mức `auto` với một chương trình nằm trong allowlist nhưng mang tham số thực thi. Ví dụ điển hình là `git` với các tham số cho phép gọi chương trình ngoài (đã có `_GIT_AUTO` để siết một phần). Kết quả: chạy lệnh tuỳ ý dù `CHAN_CUNG` "đã chặn shell".

**Khuyến nghị**
1. Chuyển từ blocklist sang **allowlist theo cặp (chương trình, mẫu tham số)**. Mỗi mục trong `ALLOWLIST_AUTO` cần một mẫu tham số được phép, không chỉ tên chương trình.
2. Loại khỏi allowlist mọi chương trình có khả năng thực thi file hoặc gọi chương trình khác, trừ khi tham số được mô tả chặt.
3. Thêm test cho từng đường vòng đã biết (đường dẫn tuyệt đối, tên thay thế, `busybox`, trình thông dịch trong allowlist, tham số `-c`/`-e`/`--exec`).
4. Ghi rõ trong docstring rằng `CHAN_CUNG` chỉ là lớp phòng ngừa tai nạn, **không** phải hàng rào bảo mật.

---

### F3. `javis_app_open` chạy được file tuỳ ý trên máy chủ (Mức: TRUNG BÌNH CAO)

**Vị trí** `system/plugins/desktop-apps/plugin.py`
- Đăng ký tool với `min_mode="full"` (quanh dòng 465, cùng chỗ `name="javis_app_open"`).
- `_open()` gọi `resolve_open()` rồi `_launch()`.
- `_launch()` (dòng 242) trên Windows gọi `os.startfile(target)` (dòng 257) cho **mọi** `kind`, kể cả `kind == "path"`.

**Chuyện gì**
`resolve_open()` trả `kind="path"` khi tham số là một đường dẫn có thật. Trên Windows, `os.startfile()` với một file `.bat`, `.cmd`, `.exe`, `.ps1` hoặc `.lnk` là **thực thi nó**. Nghĩa là tool tên là "mở app" thực chất là "chạy file bất kỳ" trên máy đang chạy Javis.

**Khai thác**
Ở mức `full` (mặc định của chat thường, xem F1), chỉ cần ghi được một file thực thi vào vault hoặc bất kỳ thư mục nào, rồi gọi `javis_app_open(name="<đường dẫn file đó>")`. Kết hợp với F1 thì một prompt injection từ nội dung tải về là đủ trọn chuỗi: ghi file, rồi chạy file. Trên macOS/Linux đường này hẹp hơn (`xdg-open`/`open`) nhưng vẫn mở được `.desktop`.

**Khuyến nghị**
1. Với `kind == "path"`, **chỉ** mở bằng ứng dụng liên kết và chặn đuôi thực thi (`.bat`, `.cmd`, `.exe`, `.ps1`, `.lnk`, `.desktop`, `.scr`, `.com`). Tốt nhất là mở bằng `ShellExecute` ở chế độ "open" qua allowlist đuôi an toàn.
2. Tách "mở tài liệu" khỏi "chạy chương trình" thành hai tool khác mức quyền, và tool chạy chương trình để `min_mode` cao hơn `full` hoặc luôn hỏi duyệt.
3. Giới hạn đường dẫn mở được vào trong vault root (hiện `resolve_open` chỉ cần file tồn tại).

---

### F4. Phân loại tác dụng của tool dựa vào tên, mặc định là `read` (Mức: TRUNG BÌNH)

**Vị trí** `server/capability_registry.py:61` `_infer_effect()`

```python
def _infer_effect(name: str) -> str:
    low = str(name or "").casefold()
    if any(x in low for x in ("delete", "remove", "cancel", "execute", "shell", "danger")):
        return "danger"
    if any(x in low for x in ("write", "create", "update", "send", "post", "edit", "upload")):
        return "write"
    return "read"
```

**Chuyện gì**
Phân loại dựa trên **chuỗi con trong tên tool**. Tên không chứa từ khoá nào trong hai danh sách thì mặc định `read`. Với tool một hành động thì tạm ổn. Với tool nhiều hành động con (đúng loại mà commit gần đây nói tới: "classify multi-action tools per sub-command"), phân loại theo tên tool là quá thô: cùng một tool vừa có hành động con đọc vừa có hành động con ghi.

**Khai thác**
Một hành động con có tác dụng phụ nhưng tên không chứa từ khoá nào trong hai danh sách (ví dụ `javis_app_open`, `git_push`, `mail_forward`, các tool MCP đặt tên tuỳ ý) sẽ rơi vào `read`, tức là **không** kích hoạt bước hỏi duyệt. Vì tên tool do bên thứ ba (MCP server) đặt, kẻ tấn công kiểm soát được đầu vào của hàm này.

**Khuyến nghị**
1. Mặc định phải là **`write`** (hoặc `danger`), không phải `read`. Rơi vào nhánh không nhận diện được là lúc cần hỏi duyệt, không phải lúc bỏ qua.
2. Bắt buộc tool khai báo tác dụng tường minh, và **từ chối** tool không khai báo thay vì đoán từ tên. Đây đã là hướng của `Resolver` hard-filter (schema rỗng thì `read`), nhưng cần đảo chiều mặc định.
3. Với tool nhiều hành động con, phân loại theo **tham số hành động** trong lời gọi, không theo tên tool. Thiếu trong bảng thì coi là hành động nặng nhất.
4. Thêm test: mọi tool đã đăng ký phải nằm trong bảng phân loại tường minh, và test fail khi có tool mới chưa phân loại.

---

### F5. WebSocket không kiểm tra `Origin` (Mức: TRUNG BÌNH)

**Vị trí** Cả bốn cổng vào đều chỉ kiểm session, không kiểm nguồn gốc:
- `server/main.py:16368` `/ws/terminal` (đây là shell thật, không phải chỉ đọc)
- `server/main.py:14263` `/ws`
- `server/main.py:13716` `/ws/voice-live`
- `server/routes/graph.py:151` `/ws/graph`

Cả bốn đều theo đúng một mẫu:

```python
if cfgmod.gate_active() and not cfgmod.valid_session(ws.cookies.get("javis_session", "")):
    await ws.close(code=1008)
    return
await ws.accept()
```

**Chuyện gì**
`@app.middleware("http")` ở `main.py:252` **không** chạy cho WebSocket, nên toàn bộ lớp kiểm `Host`/`Origin` mà HTTP có (`csrf_decision`) không áp dụng cho các cổng này. Hiện tại `SameSite=Lax` trên cookie session (`main.py:1332`) đang gánh thay: bắt tay WebSocket từ trang khác site là request cross-site, nên cookie Lax không được gửi kèm.

Điểm yếu là **chỉ có một lớp**, và nó không phải lớp do Javis chủ động dựng. Nó mất tác dụng khi: triển khai dưới domain tuỳ chỉnh và có trang khác cùng site (subdomain), trình duyệt/tiện ích can thiệp SameSite, hoặc người dùng tắt kiểm tra. Lúc đó `/ws/terminal` nhận được shell. Đây cũng là chỗ không nhất quán với phần HTTP đã siết rất kỹ.

**Khuyến nghị**
1. Viết một helper dùng chung, ví dụ `ws_guard(ws)` trong `server/web_security.py`, kiểm `Origin`/`Host` theo `allowed_web_hosts()` trước `accept()`, rồi gọi ở cả bốn chỗ. Tái dùng logic đã có, đừng viết lại.
2. `/ws/terminal` nên kiểm chặt nhất, vì nó cho shell chứ không chỉ cho đọc.
3. Thêm test cho helper: `Origin` lạ, `Origin` thiếu, `Origin` trùng host đều phải cho kết quả mong đợi.

---

### F6. Cập nhật phần mềm chỉ dựa vào TLS, và quyền file secret (Mức: TRUNG BÌNH)

**Vị trí**
- `server/updater.py`: `git fetch` từ remote GitHub cố định rồi `git rev-parse`.
- `server/system_sync.py`, `server/claude_update.py`, `server/cli_autoinstall.py`: cùng họ.

**Chuyện gì**
Không có xác thực chữ ký hay so checksum với giá trị ghim. Tin cậy hoàn toàn vào TLS tới GitHub, cộng với việc remote không bị đổi. Đây là mức tin cậy phổ biến và chấp nhận được cho một dự án tự host, nhưng cần ghi nhận: kẻ kiểm soát được remote (hoặc MITM được TLS, hoặc chiếm được repo) đẩy được code tuỳ ý xuống máy người dùng. Với một sản phẩm mà toàn bộ giá trị nằm ở việc chạy lệnh trên máy người dùng, đây là bề mặt đáng kể.

Điểm cộng: `updater.py` có chặn tham số bắt đầu bằng `-` trước khi đưa vào `git`, tức là đã để ý chuyện argument injection.

**Kèm theo, quyền file secret:** `.secret_key` và `.hub_token` trên đĩa đang là `0644` (`-rw-r--r--`), trong khi `secrets_store.py` chmod `0600` cho file khoá Fernet. Không nhất quán: hai file nhạy cảm nhất lại để mọi user trên máy đọc được. Trên máy nhiều người dùng thì `.secret_key` đọc được là giả được session.

**Khuyến nghị**
1. Ghi rõ trong tài liệu rằng cập nhật tin cậy theo TLS + remote cố định, và cảnh báo khi remote bị đổi khác giá trị mặc định.
2. Cân nhắc ghim theo tag hoặc commit đã ký, hoặc phát hành checksum kèm bản phát hành và đối chiếu.
3. Chmod `0600` cho `.secret_key`, `.hub_token`, `.sessions.json` ngay tại chỗ tạo file, giống `secrets_store.py` đã làm. Thêm test khẳng định quyền file sau khi tạo.

---

### F7. Danh sách route miễn đăng nhập cho localhost (Mức: THẤP, ranh giới cục bộ)

**Vị trí** `server/main.py:213` `_AUTH_LOCAL_EXACT` (`/telegram/*`, `/auth/status`...), dùng ở `main.py:288`.

**Chuyện gì**
Các route này miễn đăng nhập khi request đến từ localhost. Bất kỳ tiến trình nào trên máy (kể cả chạy dưới user khác, kể cả phần mềm không đáng tin người dùng vừa cài) gọi được mà không cần session. Ranh giới ở đây là ranh giới tiến trình cục bộ, không phải ranh giới mạng. Chấp nhận được cho `curl`/CLI, nhưng đây là lý do phải chmod `0600` các file secret ở F6: cùng một giả định "máy này tin cậy".

**Khuyến nghị**
Giữ nguyên nếu CLI là bắt buộc, nhưng ghi lại giả định này thành một dòng trong tài liệu, và đảm bảo F6 được sửa để hai lớp khớp nhau.

---

### F8. 643 chỗ gán `innerHTML` trong dashboard (Mức: THẤP, cần rà soát)

**Vị trí** `dashboard/*.js`, `dashboard/*.html`: 643 lần gán `innerHTML`/`insertAdjacentHTML`.

**Chuyện gì**
`chat-render.js` đã được làm cứng rất tốt, nhưng đó chỉ là đường render tin nhắn chat. 643 chỗ còn lại chưa được rà soát. Bất kỳ chuỗi nào do mô hình sinh ra (tên tool, mô tả MCP, kết quả tool, tiêu đề phiên) được nội suy vào một trong các chỗ đó là XSS.

**Khuyến nghị**
1. Rà soát theo thứ tự ưu tiên: chỗ nào nội suy dữ liệu từ mô hình hoặc từ MCP server bên thứ ba thì sửa trước.
2. Ưu tiên `textContent` thay `innerHTML`; chỗ cần HTML thì đi qua bộ escape đã có trong `chat-render.js`.
3. Thêm `Content-Security-Policy` thật (hiện `main.py:6024` mới có vài header, chưa thấy CSP đầy đủ) làm lớp chặn thứ hai.

---

## 4. Thứ tự ưu tiên

| Thứ tự | Việc | Phát hiện | Quy mô |
|---|---|---|---|
| 1 | Đảo mặc định `_infer_effect` sang `write`, bắt buộc khai báo tường minh | F4 | Nhỏ, một hàm + bảng |
| 2 | Chặn đuôi thực thi ở `kind == "path"` của `javis_app_open` | F3 | Nhỏ |
| 3 | Thêm `ws_guard` dùng chung cho bốn WebSocket | F5 | Nhỏ |
| 4 | Chmod `0600` cho `.secret_key`, `.hub_token`, `.sessions.json` | F6 | Rất nhỏ |
| 5 | Allowlist theo cặp (chương trình, mẫu tham số) trong `run_command` | F2 | Vừa, cần test kỹ |
| 6 | Bàn lại mặc định `full` + bỏ bypass approval cho chat thường | F1 | Vừa, cần quyết định UX |
| 7 | Rà 643 chỗ `innerHTML` + thêm CSP | F8 | Lớn, làm dần |
| 8 | Xác thực chữ ký/checksum cho đường cập nhật | F6 | Vừa, cần hạ tầng phát hành |

Việc 1 đến 4 gọn và không đổi hành vi người dùng thấy được, làm được trong một phiên. Việc 5 và 6 cần bàn vì chạm vào cách hệ chạy hằng ngày.

---

## 5. Giới hạn của khảo sát

- Khảo sát trên cây làm việc sạch tại `eb73383`, không soát diff. Kết luận đúng cho ảnh chụp này, không tự động đúng cho commit sau.
- Chưa chạy thử khai thác thật (không dựng môi trường tấn công). Các đường khai thác ở trên là suy ra từ code đã đọc, đã kiểm chứng từng `file:line`, nhưng chưa bắn thử.
- Chưa rà 643 chỗ `innerHTML` (F8), chỉ xác nhận `chat-render.js` là đường đã cứng.
- Chưa khảo sát phần phụ thuộc bên ngoài ở mức CVE từng gói, chỉ xác nhận ghim phiên bản và có ý thức nâng vì advisory.
