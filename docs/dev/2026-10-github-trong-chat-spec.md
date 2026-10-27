# Spec: GitHub ngay trong khung chat

Trạng thái: **ĐÃ CHỐT MỘT PHẦN ngày 27/10/2026** (chính sách merge và các giới hạn mặc định, xem
mục 17). Các mục còn nhãn [ĐỀ XUẤT] vẫn chờ duyệt. Chưa có dòng code nào theo spec này.

Nguồn: bản brainstorm "Javis - Brainstorm tích hợp GitHub vào chat" (28/10/2026, phiên Codex),
cộng bản đánh giá đối chiếu với mã nguồn `javis-os` ngày 27/10/2026 (phiên Claude Code). Spec
này thay bản brainstorm làm tài liệu triển khai, không cần đọc lại bản kia.

Quy ước đánh dấu trong tài liệu:

- **[CHỐT]**: anh Quý đã xác nhận. Đổi phải hỏi lại.
- **[ĐỀ XUẤT]**: bên viết spec đề xuất, cần anh duyệt. Duyệt xong thì đổi nhãn thành [CHỐT].
- **[MỞ]**: câu hỏi chưa có lời đáp, gom ở mục 17.

---

## 1. Mục tiêu

Người dùng bấm **+ → Repo GitHub** trong khung chat, chọn một hoặc nhiều repo, giao việc bằng
lời. Javis sửa code trên nhánh riêng, tự kiểm tra, đẩy lên, mở PR, theo dõi CI, sửa khi CI đỏ,
và báo trạng thái bằng biểu tượng gọn cạnh cuộc trò chuyện. Người dùng không phải tự quản lý
cửa sổ terminal, nhánh hay trang Actions nào.

Thước đo thành công không phải "Javis push được" mà là **code Javis đẩy lên thường xanh ngay
lần đầu và không xanh giả**. Vì vậy mục 7 (cổng chất lượng) quan trọng ngang phần GitHub.

## 2. Yêu cầu đã chốt [CHỐT]

1. Chọn repo GitHub ở nút cộng của khung chat. Chọn được nhiều repo trong một cuộc trò chuyện.
2. Repo được tải về và quản lý theo brain.
3. Code xong thì tự đẩy thay đổi lên GitHub.
4. Gỡ repo khỏi brain là xoá bản cục bộ, giữ nguyên repo trên GitHub.
5. Mỗi công việc có nhánh riêng, để nhiều cuộc trò chuyện cùng làm trên một repo.
6. Theo dõi CI. CI xanh thì tiếp tục việc kế tiếp **trong phạm vi người dùng đã giao**.
7. Dùng được nhiều mô hình, kể cả mô hình qua API key. Không thêm OpenCode.
8. Bốn biểu tượng trạng thái: đang làm (kèm số việc song song), sẵn sàng merge, đã merge,
   merge gãy cần làm lại. Hình vẽ, màu, chuyển động chưa chốt.

## 3. Javis đã có gì: tái dùng, không xây lại

Bản brainstorm viết khi chưa đọc mã. Thực tế phần nền đã có khá nhiều:

| Cần cho tính năng | Đã có ở đâu | Còn thiếu |
|---|---|---|
| Gắn nhiều thư mục vào một chat | `server/coding_store.py` (sổ thư mục theo brain, `thu_mucs`), gắn được ở mọi khung chat từ 0.347.0 | Nguồn "repo GitHub" bên cạnh "thư mục trên máy" |
| Nhánh riêng, worktree riêng mỗi phiên | `coding_store.tao_worktree` (nhánh `javis/<phiên>`, đặt ở `STATE_DIR/worktrees`), `go_worktree` từ chối gỡ khi còn sửa dở | Worktree chỉ bám thư mục CHÍNH; việc nhiều repo cần một worktree cho mỗi repo |
| Điểm hồi | `server/coding_checkpoint.py` (tag git) | Không |
| Mức quyền Plan / Tự động / Toàn quyền | `coding_store.MUC_QUYEN`, `server/coding_ctx.py` | Không |
| Engine Claude chạy thật | `server/claude_sdk_engine.py`, nạp `CLAUDE.md` của repo qua `setting_sources` | Không |
| Engine API lập trình được | `server/engine.py`, `server/aux_engine.py`, 150 vòng công cụ trong phiên code | Chưa nạp luật của repo (mục 7.1) |
| Gateway tương thích Anthropic | provider `anthropic-compat` (`engine.normalize_anthropic_compat_base`) | Không |
| Việc nền, phụ thuộc, trả kết quả về đúng chat | `server/task_store.py` (`deps`, `chat_id`, trạng thái `blocked`, `waiting_on`) | Không |
| Push bằng token an toàn | `git_brain._auth_url` (token chỉ sống trong một lệnh, không ghi vào `.git/config`), che token trong log | Token GitHub riêng cho tính năng này |
| Mã hoá secret | `server/secrets_store.py` (Fernet, tiền tố `enc:`) | Không |
| Webhook GitHub có kiểm chữ ký | `server/webhook_auth.py` (provider `github`, `X-Hub-Signature-256`) | Đấu vào bộ theo dõi CI |

Phần thiếu thật, cũng là phạm vi của spec này:

- Kết nối tài khoản GitHub, liệt kê repo, clone về.
- Cổng chất lượng trước khi push (mục 7).
- Push, tạo PR, theo dõi CI theo đúng commit, vòng "CI đỏ thì sửa lại".
- Review chéo, chính sách merge, việc kế tiếp.
- Bốn biểu tượng và bảng chi tiết.
- Bài học theo repo và số đo theo engine.

Spec cũ `docs/dev/2026-09-coding-workspace-spec.md` mục 10 đã xếp "Git và PR trong giao diện"
vào "Để lần sau". Spec này là lần sau đó, nên mọi quyết định ở mục 5 và 11 của spec cũ vẫn giữ
(không tự đổi engine giữa chừng, không bảng quota phần trăm, không tầng Handoff riêng).

## 4. Ba quyết định kiến trúc

### 4.1. Lớp GitHub độc lập với engine [ĐỀ XUẤT]

Mọi thứ liên quan GitHub (clone, push, PR, đọc CI, merge, biểu tượng) là **mã của Javis**, chạy
phía server, đọc sự thật từ git và API GitHub. Engine (Claude Code hay bất kỳ engine API nào)
chỉ làm một việc: sửa code và chạy lệnh trong worktree được giao.

Vì sao:

- Biểu tượng và chuyển bước phải dựa trên bằng chứng, không dựa vào lời model tự báo.
- Engine nào cũng dùng được ngay tính năng, không phải viết lại cho từng nhà.
- Đổi engine không làm mất trạng thái PR, CI.

Hệ quả: model **không tự gọi `git push` hay `gh pr merge`**. Nó commit trong worktree (hoặc để
Javis commit hộ, xem mục 8), rồi kết thúc lượt. Bước đẩy và mọi bước sau do Javis làm.

### 4.2. Claude Agent SDK cho model ngoài Claude: thử nghiệm, không phải trục chính [ĐỀ XUẤT]

Bản brainstorm muốn mọi model chạy qua Claude Agent SDK, trỏ tới endpoint tương thích Anthropic
hoặc gateway. Spec này **hạ hướng đó xuống thành thử nghiệm một ngày**, không chặn tính năng.

Vì sao:

1. Spec coding cũ mục 11 đã chốt không ép model chỉ có API chạy qua Codex CLI làm vỏ, vì runtime
   Javis chạy thật còn vỏ kia là giả định chưa kiểm chứng. Dùng Claude SDK làm vỏ cho DeepSeek là
   đúng giả định đó với nhà khác.
2. Anthropic không hỗ trợ chính thức định tuyến Claude Code sang model ngoài Claude. SDK gửi
   thinking, cache, model phụ cho sub-agent; endpoint "tương thích" hay thiếu một phần, và mỗi
   bản `claude` mới có thể làm gãy mà không báo lỗi rõ.
3. Cảm nhận "Claude làm thông minh hơn Codex" chưa tách được phần do model và phần do vỏ. Số đo
   ở mục 13.2 sẽ trả lời câu này bằng số.

Thử nghiệm (giai đoạn T, chạy song song, không chặn giai đoạn nào):

- Một repo thử, DeepSeek qua endpoint Anthropic có tài liệu chính thức.
- Nhiệm vụ: đọc code, sửa, chạy test, dừng, chạy tiếp đúng phiên.
- Kiểm: gọi công cụ nhiều vòng, streaming, ngắt giữa chừng, resume, model phụ, hai tiến trình
  chạy hai endpoint khác nhau cùng lúc không lẫn biến môi trường.
- Đầu ra: một bảng đạt/không đạt theo từng mục, ghi vào `docs/dev/`. Đạt hết thì thêm thành một
  lựa chọn engine; không đạt thì đóng hồ sơ kèm lý do.

### 4.3. Repo nằm ngoài cây thư mục brain [ĐỀ XUẤT]

Yêu cầu [CHỐT] là repo "thuộc brain". Spec hiểu đó là **thuộc về mặt quản lý**, còn vị trí trên
đĩa nằm ngoài cây brain:

```
STATE_DIR/repos/<brain-id>/<owner>/<repo>/      bản clone chính
STATE_DIR/worktrees/<...>                        worktree của từng việc (đã có)
```

Vì sao không để trong brain:

- Brain được đồng bộ lên GitHub (`git_brain.py`). Repo code trong đó sẽ bị đẩy nhầm vào bản sao
  lưu brain, hoặc thành repo lồng repo.
- Graph, wiki, tìm kiếm, dataview quét cây brain. Hàng nghìn file mã sẽ làm bẩn chỉ mục và chậm
  mọi lượt.
- Worktree hiện đã cố ý đặt ngoài cây gốc vì đúng lý do quét file (`coding_store.WORKTREE_DIR`).

Sổ repo vẫn ghi theo `brain-id`, nên đổi brain thì thấy đúng bộ repo của brain đó. Tên thư mục
có cả `owner` để hai repo cùng tên khác chủ không đè nhau.

## 5. Kết nối GitHub và vòng đời repo

### 5.1. Đăng nhập

**[CHỐT 27/10/2026] Kết nối GitHub dựng sẵn trong lõi Javis.** Thẻ GitHub luôn có trên trang Kết
nối của mọi bản cài, không phải cài gói Store, không qua MCP ngoài. Mã nằm trong `server/`, chạy
cả khi người dùng tắt hết gói mở rộng. Brain đã có token sao lưu GitHub (`git_brain`) thì thẻ đề
nghị dùng chung token đó: kiểm quyền trước, thiếu quyền nào thì nói đúng quyền đó và cách thêm,
không âm thầm dùng token thiếu quyền.

Phần dưới là [ĐỀ XUẤT]:

- Bản đầu dùng **fine-grained personal access token**, **một kết nối cho cả bản cài** (sửa lúc làm
  G1, 0.362.0: bản nháp ghi mỗi brain một token, nhưng token sao lưu brain vốn là một cho cả bản
  cài, và chưa có người dùng nào cần hai tài khoản GitHub theo brain). Token mã hoá khi lưu qua
  `_SECRET_PATHS` của `config.py` (`github.token`); sổ repo vẫn tách theo brain. Quyền tối thiểu: Contents (đọc, ghi), Pull requests (đọc, ghi),
  Checks (đọc), Actions (đọc), Commit statuses (đọc), Metadata (đọc).
- Trang Kết nối có hướng dẫn tạo token từng bước, nút **Kiểm tra** gọi `GET /user` và liệt kê
  repo token thấy được.
- Token chỉ đi vào lệnh git theo cách của `git_brain._auth_url` (một lần, không lưu remote) và
  vào header API. Mọi log, lỗi, tin chat đi qua `secret_redact` trước khi hiện.
- GitHub App hoặc OAuth (bấm một nút là xong) để giai đoạn sau, khi có người dùng thật cần.

### 5.2. Chọn repo trong chat

1. Bấm **+ → Repo GitHub**: hiện danh sách repo token thấy được, ô tìm, tích chọn nhiều cái.
2. Repo chưa có bản clone: clone nông (`--filter=blob:none`) về `STATE_DIR/repos/...`, hiện tiến
   độ. Repo đã có: `git fetch`, báo nếu bản cục bộ lệch hoặc bẩn.
3. Repo được gắn vào chat bằng đúng cơ chế `thu_mucs` hiện có, với một cờ `nguon: github`.
4. Hàng chip trên ô nhập hiện repo đang gắn và nhánh của việc hiện hành.

Chọn repo **không** chạy script, không cài phụ thuộc. Cài phụ thuộc chỉ xảy ra khi bước kiểm tra
(mục 7.2) cần, theo lệnh suy ra từ repo, và ở mức quyền cho phép chạy lệnh.

### 5.3. Ba thao tác gỡ [CHỐT phần nghĩa, ĐỀ XUẤT phần chặn]

| Thao tác | Kết quả | Chặn khi |
|---|---|---|
| Bỏ khỏi chat | Gỡ liên kết với chat này, bản clone giữ nguyên | Không chặn |
| Gỡ khỏi brain | Xoá bản clone và mọi worktree của nó, GitHub giữ nguyên | Còn việc đang chạy; còn commit chưa push; còn sửa chưa commit. Hiện rõ việc nào, nhánh nào, và nút "Đẩy lên rồi gỡ" |
| Xoá repo trên GitHub | Không có trong tính năng này | |

Mâu thuẫn cần gỡ: hiện nay "xoá thư mục khỏi sổ KHÔNG đụng đĩa" (`coding_store.py`, ranh giới
có chủ ý). Cách giải: **chỉ xoá đĩa với bản clone do chính Javis tạo** (cờ `nguon: github`, nằm
trong `STATE_DIR/repos`). Thư mục người dùng tự thêm bằng tay giữ nguyên quy tắc cũ.

## 6. Việc, nhánh và worktree

- Một **việc code** là một bản ghi gắn với một chat, có một hoặc nhiều repo. Mỗi repo trong việc
  có **một nhánh và một worktree riêng**. [ĐỀ XUẤT]
- Tên nhánh: `javis/<slug-ngắn>-<id 6 ký tự>`, slug sinh từ nội dung việc, không dấu. Giữ tiền tố
  `javis/` như hiện nay để người dùng nhận ra nhánh do Javis tạo.
- Mở rộng `coding_store` để worktree bám **từng repo** chứ không chỉ thư mục chính. Việc một repo
  vẫn đi đúng đường cũ.
- Sửa code chạy song song được. Giới hạn số việc chạy đồng thời mỗi brain, mặc định **3**. [CHỐT]
- Không cho hai tiến trình cùng điều khiển một phiên engine đang ghi (khoá theo việc).
- Endpoint, model, credential đặt **theo tiến trình**, không đổi biến môi trường chung, để hai
  việc chọn hai model không gọi nhầm nhau.
- Nhiều repo không có merge nguyên tử chung. Mỗi repo có trạng thái riêng; việc chỉ "xong" khi
  mọi repo xong. Một repo lỗi thì báo đúng repo đó, không che bằng repo đã xanh.

Lượt sửa chạy ở đâu:

- Lượt đầu chạy ngay trong chat (người dùng thấy tiến độ như mọi lượt code hiện nay).
- Các vòng sau (sửa CI đỏ, việc kế tiếp) chạy thành việc Kanban với `chat_id` là
  `web:<phiên chat>`, cùng worktree, cùng engine đã chọn. Kết quả tự về đúng chat và inbox.
  Đúng luật của Javis: không hứa "lát em báo", việc nền tự đẩy kết quả.

## 7. Cổng chất lượng trước khi push [ĐỀ XUẤT]

Đây là phần quyết định code tốt hay dở. Mọi bước chạy **trong worktree, trước khi push**, do
Javis điều khiển chứ không trông vào model tự nhớ.

### 7.1. Mọi engine đều đọc luật của repo

Claude Code đã tự nạp `CLAUDE.md` của repo. Engine API thì chưa. Thêm bước: khi một lượt code chạy
trong worktree, Javis nạp vào ngữ cảnh (theo thứ tự, có trần độ dài) `AGENTS.md`, `CLAUDE.md`,
`CONTRIBUTING.md` ở gốc repo, cộng bài học theo repo ở mục 13.1. Không có file nào thì bỏ qua.

### 7.2. Chạy đúng bộ kiểm tra của CI trước khi push

1. Đọc `.github/workflows/*.yml` của repo, rút ra các lệnh chạy trên sự kiện `push` và
   `pull_request` (bước `run:`). Bỏ bước deploy, bước cần secret, bước chỉ chạy trên `main`.
2. Kết hợp với tín hiệu quen thuộc (`package.json` scripts `lint`, `test`, `typecheck`, `build`;
   `pyproject.toml`; `Makefile`) để ra danh sách **lệnh kiểm tra cục bộ** của repo.
3. Danh sách này được **lưu theo repo và hiện cho người dùng sửa** ở bảng chi tiết repo. Lần đầu
   Javis đề xuất, người dùng (hoặc lượt chat) chỉnh, những lần sau dùng lại.
4. Trước mỗi push, chạy danh sách đó. Đỏ thì giao lại cho đúng phiên sửa, không push.
5. Lệnh không chạy được ở máy (thiếu runtime, cần dịch vụ ngoài) thì ghi rõ "bỏ qua ở máy, chờ
   CI", không coi là xanh.

Có trần thời gian cho bước này (mặc định 10 phút, chỉnh được theo repo).

### 7.3. Quét secret trước khi commit

Quét diff sắp commit bằng bộ mẫu của `secret_redact` cộng các mẫu phổ biến (khoá riêng, token
dạng `ghp_`, `sk-`, `AKIA`...). Phát hiện thì **dừng, không commit**, báo dòng nào. Spec coding
cũ đã ghi phần này phải vào cùng lúc Javis bắt đầu đẩy code ra ngoài.

### 7.4. Rào chống "ăn gian cho CI xanh"

Dò trong diff các thay đổi làm CI xanh mà không sửa lỗi:

- Thêm `skip`, `xfail`, `.only`, `@pytest.mark.skip`, `it.skip`, `t.Skip()` và tương tự.
- Xoá file test hoặc xoá hàm test.
- Sửa file trong `.github/workflows/`, nới ngưỡng coverage, tắt quy tắc lint.

Gặp một trong các dấu hiệu: vẫn cho push (có thể là chủ ý hợp lệ) nhưng **chặn tự merge**, gắn
cảnh báo trên PR và trong chat, cần người dùng bấm xác nhận. Model không bao giờ được tự làm
những việc này để qua CI; luật này cũng nằm trong lời nhắc của lượt sửa CI.

### 7.5. Sửa lỗi phải có test tái hiện

Với việc được phân loại là sửa lỗi, và với mọi vòng sửa CI đỏ: lời nhắc yêu cầu **tái hiện lỗi
trước** (một test đỏ, hoặc chạy lại đúng lệnh CI đã đỏ ở máy), sửa, rồi chứng minh cùng lệnh đó
xanh. Javis ghi lại cả hai lần chạy vào bản ghi việc làm bằng chứng.

### 7.6. Diff nhỏ, một PR một việc

Ngưỡng mặc định 400 dòng đổi [CHỐT], không tính lockfile và file sinh tự động. Vượt ngưỡng thì Javis
đề xuất tách việc, nối bằng `deps` trên Kanban. Người dùng vẫn được chọn giữ nguyên.

## 8. Commit, push, PR

1. Cổng chất lượng xanh thì Javis commit (nếu model chưa commit), message theo quy ước repo nếu
   đọc được từ luật repo, không thì dạng ngắn gọn tiếng Anh.
2. Push nhánh việc lên `origin` bằng token theo cách của `git_brain._auth_url`.
3. Ghi **SHA thực tế đã push**. Mọi trạng thái CI về sau bám SHA này.
4. Chưa có PR thì tạo PR. Có template (`.github/pull_request_template.md` và các vị trí chuẩn)
   thì điền theo khung đó. Thân PR có: việc được giao, các bước kiểm tra cục bộ đã chạy và kết quả,
   engine và model đã dùng.
5. PR tạo ở dạng **draft** cho tới khi CI xanh và review chéo (mục 10) xong, rồi chuyển thành
   sẵn sàng review. [ĐỀ XUẤT]

Javis không bao giờ force-push lên nhánh không phải do Javis tạo, không rebase nhánh người khác.

## 9. Theo dõi CI

### 9.1. Nguồn sự kiện

- **Polling** là đường chính vì chạy được ở mọi máy: mỗi SHA đang chờ được hỏi 30 giây một lần
  trong 10 phút đầu, sau đó 2 phút một lần. Với giới hạn 5.000 lượt gọi một giờ của token, đủ cho
  vài chục PR cùng lúc.
- **Webhook** khi máy có tên miền hoặc tunnel: đăng ký webhook `check_run`, `check_suite`,
  `status`, `pull_request`, kiểm chữ ký bằng `webhook_auth` sẵn có. Webhook chỉ là tín hiệu "hỏi
  lại ngay"; sự thật vẫn đọc lại từ API, nên mất hay lặp sự kiện không gây sai.

### 9.2. Đọc kết quả

Với SHA đầu nhánh: gộp check runs và commit statuses. Kiểm tra bắt buộc lấy từ branch protection
hoặc ruleset nếu token đọc được; không đọc được thì coi **mọi kiểm tra xuất hiện trên SHA** là bắt
buộc, và cho người dùng chỉnh danh sách theo repo.

### 9.3. Các ca phải xử lý đúng

| Ca | Xử lý |
|---|---|
| Push xong chưa thấy kiểm tra nào | Chờ 3 phút. Vẫn không có thì trạng thái **không có CI**, đi theo chính sách repo (mục 17), không bao giờ tự coi là xanh |
| Kiểm tra bị huỷ, bỏ qua, hết giờ | Không phải xanh. Huỷ do commit mới thì bỏ qua; còn lại báo kẹt |
| Commit mới thay commit cũ | Kết quả của SHA cũ bị bỏ, không mở bước mới nào từ nó |
| Nhánh đích đổi sau khi xanh | Kiểm lại `mergeable`, không dùng kết quả cũ |
| CI đỏ | Lấy log của job đỏ (cắt phần liên quan), giao lại cho đúng phiên sửa thành một việc Kanban. Theo mục 7.5: tái hiện trước rồi mới sửa |
| Lỗi có vẻ chập chờn | Chạy lại job đúng **một lần**. Đỏ lần hai là lỗi thật |
| Đỏ cả trên nhánh đích | Không phải lỗi của việc này. Báo người dùng, không sửa lan sang phạm vi khác |
| Javis khởi động lại | Đọc bản ghi đã lưu, đối chiếu GitHub, rồi mới làm tiếp |
| Sự kiện lặp, timeout chưa rõ kết quả | Kiểm trạng thái thật trước khi thử lại. Mọi bước ghi dấu đã làm để không tạo trùng commit, PR, merge hay việc kế tiếp |

### 9.4. Giới hạn [CHỐT]

Mặc định, chỉnh được theo repo: tối đa **3 vòng sửa CI** mỗi việc, chờ CI tối đa **60 phút** mỗi
SHA, ngân sách token mỗi việc theo cấu hình hiện có của Javis. Vượt giới hạn thì trạng thái **kẹt**
kèm nguyên nhân, gửi về chat và inbox. Không lặp vô hạn.

## 10. Review chéo bằng model khác [ĐỀ XUẤT]

Sau khi CI xanh, Javis giao diff cho **một engine khác với engine đã viết** (người dùng chọn ở cài
đặt repo; mặc định: viết bằng Claude thì review bằng engine API đầu tiên đã kết nối, và ngược lại).

- Vai trò: người soi lỗi. Chỉ được nêu lỗi có **đường gây hỏng cụ thể** (đầu vào nào, ra kết quả
  sai gì). Không nêu chuyện đặt tên hay khẩu vị.
- Mỗi phát hiện được đưa lại cho engine đã viết để kiểm chứng. Đúng thì sửa trong vòng kế (tính
  vào giới hạn mục 9.4); sai thì ghi lý do bác bỏ vào bản ghi.
- Review chéo không chặn được mãi: hết giới hạn vòng thì hiện các phát hiện còn mở cho người dùng.
- Chỉ có một engine đã kết nối thì bỏ bước này, ghi rõ trên PR "chưa review chéo".

Đây là chỗ "nhiều engine" của Javis thành lợi thế: mỗi model có điểm mù riêng.

## 11. Merge và việc kế tiếp

### 11.1. Chính sách merge [CHỐT 27/10/2026]

Anh Quý chốt: "xanh merge luôn, auto merge theo repo".

- Mặc định: **CI xanh thì tự merge luôn**, không dừng chờ bấm tay.
- Công tắc **tự merge theo từng repo**, mặc định bật. Tắt ở repo nào thì repo đó dừng ở **sẵn
  sàng merge**, người dùng bấm Merge trong bảng chi tiết hoặc nói trong chat. Repo `javis-os`
  khớp sẵn với quy ước dev hiện tại (merge thẳng `main` khi CI xanh).
- "Xanh" ở đây là đủ cả bộ điều kiện dưới, không chỉ dấu tích của CI. Tự merge chỉ chạy khi đủ:
  CI bắt buộc xanh trên đúng SHA, `mergeable` đúng, không có cảnh báo mục 7.4, review chéo không còn phát hiện mở, và yêu cầu review của repo (nếu có) đã thoả.
- Kiểu merge theo cài đặt repo trên GitHub (squash, rebase, merge commit), không tự chọn.
- Nhiều việc cùng nhắm một nhánh đích thì merge **theo hàng đợi**, mỗi lần một việc, kiểm lại
  `mergeable` trước từng lần.

### 11.2. Việc kế tiếp

- Chỉ chạy việc **người dùng đã giao**. CI xanh không sinh việc mới. Một bước tiếp theo do model
  tự nghĩ ra chỉ được nói trong câu trả lời, không được xếp hàng (đúng luật điều phối của Javis).
- Việc kế tiếp nối bằng `deps` của `task_store`. Việc cần code đã vào nhánh chính thì phụ thuộc vào
  mốc **đã merge và kiểm tra sau merge xanh** (nếu repo có kiểm tra trên `main`).
- Việc mẹ bị kẹt thì việc con đứng chờ, và báo cáo kẹt liệt kê việc con đang chờ (`waiting_on`
  đã có sẵn).

## 12. Bốn biểu tượng và bảng chi tiết

### 12.1. Lưu trạng thái tách, tính biểu tượng sau [ĐỀ XUẤT]

Mỗi repo trong một việc lưu **ba trường riêng**, không gộp làm một:

- `thuc_thi`: `cho`, `dang_chay`, `xong`, `ket`, `huy`
- `ci`: `chua_co`, `dang_chay`, `xanh`, `do`, `khong_co_ci`, `huy`
- `tich_hop`: `chua_pr`, `pr_mo`, `san_sang`, `da_merge`, `xung_dot`, `merge_loi`, `sau_merge_do`

Biểu tượng được **tính** từ ba trường:

| Biểu tượng [CHỐT nghĩa] | Điều kiện |
|---|---|
| Đang làm (kèm số việc) | Có ít nhất một repo `thuc_thi = dang_chay`, hoặc `ci = dang_chay` |
| Sẵn sàng merge | `ci = xanh` trên SHA đầu nhánh và `tich_hop = san_sang` |
| Đã merge | GitHub xác nhận PR đã merge (`tich_hop = da_merge`) |
| Merge gãy, cần làm lại | `tich_hop` là `xung_dot`, `merge_loi` hoặc `sau_merge_do` |

PR đã merge mà kiểm tra sau merge đỏ: **giữ biểu tượng đã merge kèm dấu cảnh báo**, không xoá sự
thật đã merge.

Dấu phụ (chấm nhỏ hoặc chữ trong mô tả) cho các trạng thái bốn biểu tượng không diễn được: chờ CI,
chờ duyệt, kẹt. Một chat nhiều việc thì danh sách hội thoại hiện biểu tượng **xấu nhất** cộng số
việc đang chạy; bảng chi tiết hiện từng việc, từng repo.

### 12.2. Bảng chi tiết

Bấm biểu tượng mở bảng: mỗi repo một dòng gồm nhánh, SHA ngắn, PR (link), từng kiểm tra CI, các
lệnh kiểm tra cục bộ đã chạy, phát hiện của review chéo, nguyên nhân kẹt, và nút: Mở PR, Merge,
Chạy lại kiểm tra, Dừng việc.

### 12.3. Giao diện

- Dùng bộ biểu tượng sẵn có của dashboard, tham khảo ảnh Claude anh gửi.
- Chữ mới đi qua `t("...")` với cả `vi.json` và `en.json`; câu giải thích dài vào nút (i) theo
  quy ước 0.214.0; chữ trong khối giải thích 16px.
- Làm được trên màn hình điện thoại.

## 13. Học theo repo và đo theo engine [ĐỀ XUẤT]

### 13.1. Bài học theo repo

Mỗi lần CI đỏ rồi sửa xanh, hoặc review chéo bắt được lỗi thật, Javis rút **một dòng bài học**
gắn với repo (ví dụ "chạy `npm run build` trước test", "đổi chữ giao diện phải sửa cả hai file
dịch"). Lưu trong brain (`Javis/learned/repos/<owner>__<repo>.md`), không ghi vào repo của người
dùng. Nạp ở bước 7.1.

Đúng luật tự học hiện có: chỉ học khi lỗi thật vừa xảy ra, không có vòng nền nâng cấp hàng loạt.
Trùng bài học cũ thì cập nhật, không thêm dòng. Trần 30 dòng mỗi repo, quá thì gộp.

### 13.2. Số đo theo engine và model

Mỗi việc ghi: engine, model, CI xanh ngay lần push đầu hay không, số vòng sửa, số phát hiện review
chéo được xác nhận, thời gian, chi phí token. Trang chi tiết repo có bảng tổng hợp theo model.
Sau vài chục việc, người dùng chọn model bằng số thật.

## 14. Dữ liệu [ĐỀ XUẤT]

Kho mới `STATE_DIR/github_work.db` (SQLite, cùng kiểu với `task_store`):

- `repos`: brain, owner, tên, đường dẫn clone, nhánh mặc định, lệnh kiểm tra cục bộ, kiểm tra bắt
  buộc, chính sách merge, chính sách khi không có CI, giới hạn, engine review chéo.
- `jobs` (việc code): brain, phiên chat nhận kết quả, nội dung và phạm vi đã giao, engine và model
  thực tế, id phiên engine, id việc Kanban liên quan, số vòng đã sửa.
- `job_repos`: việc, repo, nhánh, worktree, SHA nền, SHA đầu nhánh đã push, số PR, ba trường trạng
  thái mục 12.1, nguyên nhân kẹt, thời điểm đối chiếu GitHub gần nhất.
- `checks`: SHA, tên kiểm tra, kết quả, link, thời điểm.
- `steps`: khoá chống lặp cho mỗi thao tác ra ngoài (push, tạo PR, merge, tạo việc kế tiếp).
- `metrics`: số đo mục 13.2.

Token không nằm trong kho này, chỉ có tham chiếu tới `secrets_store`.

Đổi engine giữa chừng: theo spec coding cũ, đổi bằng tay qua tấm xác nhận; engine mới đọc lại repo
và bản ghi việc. Không hứa tiếp tục nguyên phiên của engine cũ.

## 15. Giai đoạn triển khai [ĐỀ XUẤT]

Mỗi giai đoạn là một hoặc vài PR, mỗi PR mang số phiên bản riêng theo `docs/quy-uoc-dev.md`.

| Giai đoạn | Nội dung | Xong khi |
|---|---|---|
| G1. Kết nối và clone | Thẻ GitHub dựng sẵn trên trang Kết nối (mục 5.1), liệt kê repo, clone vào `STATE_DIR/repos`, gắn vào chat, ba thao tác gỡ | Chọn repo trong chat, Javis sửa được trong worktree như thư mục thường |
| G2. Cổng chất lượng | 7.1 luật repo cho engine API, 7.2 lệnh kiểm tra cục bộ, 7.3 quét secret, 7.4 rào ăn gian | Một việc đỏ ở máy không bao giờ được push |
| G3. Push, PR, CI một repo | Mục 8, 9; vòng CI đỏ thì sửa; restart giữa chừng | Một repo đi hết vòng tới sẵn sàng merge, kể cả ca CI đỏ rồi sửa |
| G4. Biểu tượng, merge | Mục 11, 12 | Bốn biểu tượng đúng bằng chứng, merge theo chính sách, việc kế tiếp chạy đúng phụ thuộc |
| G5. Nhiều repo, review chéo, học | Worktree theo từng repo, mục 10, 13 | Việc hai repo báo riêng từng repo; review chéo chạy; bảng số đo có số |
| T. Thử nghiệm SDK | Mục 4.2 | Có bảng đạt/không đạt |

G1 và G2 đáng giá ngay cả khi chưa có G3: code sửa trong repo GitHub đã tốt hơn nhờ cổng chất lượng.

## 16. Tiêu chí chấp nhận và test

Test tự động (thêm vào `tests/python/`, dùng repo git tạm và GitHub API giả):

1. Chọn repo lần hai dùng lại bản clone cũ, không clone lại.
2. Hai việc trên cùng repo ở hai worktree khác nhau, không sửa đè file của nhau.
3. Gỡ khỏi brain bị chặn khi còn commit chưa push; không bao giờ gọi API xoá repo.
4. Thư mục người dùng tự thêm vẫn không bị xoá đĩa khi bỏ khỏi sổ.
5. Lệnh kiểm tra cục bộ đỏ thì không có lệnh push nào chạy.
6. Diff có token giả bị chặn commit.
7. Diff thêm `@pytest.mark.skip` hoặc sửa workflow thì tự merge bị chặn.
8. Commit mới không thừa hưởng trạng thái xanh của commit cũ.
9. "Không có kiểm tra nào" không bao giờ ra `ci = xanh`.
10. Sự kiện webhook lặp, hoặc restart giữa lúc chờ, không tạo trùng PR, merge hay việc kế tiếp.
11. Hai việc chọn hai model khác nhau chạy cùng lúc không dùng nhầm endpoint hay credential.
12. Việc hai repo, một xanh một đỏ: biểu tượng chat là trạng thái xấu nhất, không báo hoàn tất.
13. Hết 3 vòng sửa CI thì trạng thái kẹt, có nguyên nhân, về đúng chat và inbox.
14. PR đã merge mà kiểm tra sau merge đỏ: vẫn là đã merge, kèm cảnh báo.
15. Việc kế tiếp không chạy khi việc mẹ chưa đủ điều kiện.

Kiểm tay trên dashboard (cả máy tính và điện thoại): chọn repo, giao việc, xem biểu tượng đổi theo
từng bước, mở bảng chi tiết, merge.

## 17. Câu hỏi cần anh chốt

| Câu hỏi | Đề xuất của spec |
|---|---|
| CI xanh thì tự merge hay chờ duyệt? | **ĐÃ CHỐT 27/10:** xanh thì tự merge luôn, công tắc tự merge theo từng repo (mục 11.1) |
| Repo không có CI thì "xong" là gì? | Mặc định: cổng chất lượng cục bộ xanh thì sẵn sàng merge, nhưng ghi rõ "không có CI" và không tự merge |
| Đăng nhập GitHub bằng gì? | Token fine-grained mỗi brain trước, GitHub App sau |
| Chọn repo ở mức chat hay từng việc? | Gắn ở chat; mỗi việc lưu danh sách repo thực dùng |
| Giới hạn mặc định | **ĐÃ CHỐT 27/10:** 3 việc song song, 3 vòng sửa CI, chờ CI 60 phút, diff 400 dòng |
| Vị trí bản clone | `STATE_DIR/repos/<brain>/<owner>/<repo>`, ngoài cây brain (mục 4.3) |
| Model ngoài Claude qua Claude SDK | Thử nghiệm một ngày, không phải trục chính (mục 4.2) |
| Có review chéo mặc định không? | Bật khi có từ hai engine trở lên |

## 18. Quyết định KHÔNG làm

- **Ép mọi model qua một vỏ engine duy nhất** (Claude SDK hay Codex). Xem 4.2 và spec coding cũ mục 11.
- **Thêm OpenCode.** [CHỐT]
- **Xoá repo trên GitHub.** Ngoài phạm vi. [CHỐT]
- **Model tự push, tự merge bằng lệnh của nó.** Mọi thao tác ra GitHub do lớp Javis làm, có chống lặp.
- **Coi lời model tự báo là trạng thái.** Biểu tượng chỉ tính từ git và API GitHub.
- **Tự sinh việc mới khi CI xanh.** Chỉ chạy việc người dùng đã giao.
- **Bỏ qua, tắt hay cách ly test để có CI xanh.** Không bao giờ, kể cả khi người dùng bật Toàn quyền.
- **Clone repo vào trong cây brain.** Xem 4.3.

## 19. Lệnh goal triển khai trọn gói

Dán nguyên khối dưới vào một phiên Claude Code mở trên repo `javis-os`. Phiên đó tự làm từ G1 tới
G5, mỗi giai đoạn một PR theo quy ước, xong hết mới kiểm toàn bộ và tự sửa tới khi sạch.

```text
/goal Triển khai TRỌN spec docs/dev/2026-10-github-trong-chat-spec.md, giai đoạn G1 tới G5,
rồi tự kiểm toàn bộ và tự sửa cho tới khi đạt đủ 15 tiêu chí mục 16. Chỉ dừng khi xong hết
hoặc chỉ còn việc cần chính anh làm.

TRƯỚC KHI CODE
- Đọc CLAUDE.md, docs/quy-uoc-dev.md, spec trên và docs/dev/2026-09-coding-workspace-spec.md.
- Mục [CHỐT] làm đúng nguyên văn. Mục [ĐỀ XUẤT] làm theo đúng đề xuất trong spec, không tự
  đổi thiết kế. Thấy spec sai so với mã thật thì sửa spec trong cùng PR và ghi lý do.
- Kết nối GitHub DỰNG SẴN trong lõi Javis (mục 5.1): thẻ GitHub luôn có trên trang Kết nối,
  không qua gói Store, không qua MCP ngoài.
- Dùng lại hạ tầng có sẵn (bảng mục 3), không dựng bộ điều phối thứ hai.

MỖI GIAI ĐOẠN G1 -> G5, LÀM ĐÚNG THỨ TỰ
1. Xí chỗ số phiên bản theo docs/quy-uoc-dev.md, mở PR nháp mang số đó ngay đầu nhánh.
2. Viết code: tiếng Anh cho code và comment; chữ trên màn hình qua i18n (vi.json + en.json,
   localefmt.chu phía server); giải thích dài vào nút (i); chữ tối thiểu 16px; chạy được
   trên điện thoại.
3. Viết test cho các tiêu chí mục 16 thuộc giai đoạn đó. Test KHÔNG gọi GitHub thật: dùng
   repo git tạm và API GitHub giả.
4. Chạy python tests/run.py cùng test JS. Đỏ thì tìm gốc rồi sửa. TUYỆT ĐỐI không skip,
   xoá hay nới test để cho xanh.
5. Tự review diff như người soi lỗi (bảo mật token, chống lặp, restart giữa chừng, nhiều
   repo), sửa hết rồi mới push.
6. Viết CHANGELOG.md và CHANGELOG.en.md cho người đọc trên điện thoại, 3-4 gạch đầu dòng.
7. Push, chờ CI. CI đỏ thì đọc log, tái hiện ở máy, sửa, push lại cho tới khi xanh. CI xanh
   thì merge vào main theo quy ước repo và xác nhận bản phát hành đã ra.
8. Giai đoạn sau tách nhánh từ main mới nhất.

VÒNG KIỂM CUỐI (sau G5, lặp tới khi sạch)
- Lấy main mới nhất, chạy toàn bộ test.
- Chạy app thật, đi hết luồng bằng GitHub giả: kết nối, chọn repo trong chat, giao việc, cổng
  chất lượng, push, PR, CI đỏ rồi tự sửa, CI xanh rồi tự merge, bốn biểu tượng, gỡ repo.
  Chụp màn hình ở khổ máy tính và khổ điện thoại.
- Lập bảng 15 tiêu chí mục 16: đạt/không đạt kèm bằng chứng (tên test, ảnh chụp).
- Còn tiêu chí nào không đạt, còn test đỏ hay lỗi giao diện: mở PR sửa (có số phiên bản),
  merge khi xanh, rồi chạy lại TOÀN BỘ vòng kiểm cuối từ đầu.

KHÔNG LÀM
- Thử nghiệm T (Claude SDK với model ngoài Claude), OpenCode, xoá repo trên GitHub, clone
  vào trong cây brain, để model tự push hay merge.

GẶP CHỖ CHỈ ANH LÀM ĐƯỢC (token thật, tài khoản, quyết định ngoài spec)
- Không đoán. Ghi vào danh sách "Cần anh", làm tiếp phần còn lại.

BÁO CÁO CUỐI (tiếng Việt, ngắn): các PR và số phiên bản đã phát hành, bảng 15 tiêu chí,
danh sách "Cần anh".
```
