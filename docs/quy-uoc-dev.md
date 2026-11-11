# Quy ước dev (phiên Claude Code làm việc trên repo này)

File này tách khỏi `CLAUDE.md` ngày 2026-09-22. Lý do: `CLAUDE.md` là system prompt đi vào
MỌI lượt chat của Javis, có trần ngân sách (`tests/python/test_prompt_budget.py`), mà quy ước
dev thì người dùng Javis không bao giờ cần. Để ở đây thì viết bao nhiêu cũng được, không đánh
thuế lên lượt chat nào cả.

## Nhánh, PR và merge

- Vẫn phát triển trên nhánh riêng và mở PR như thường lệ.
- CI xanh rồi thì **merge thẳng vào `main`** (rebase/squash, giữ lịch sử thẳng, repo này không
  dùng merge commit). Chủ repo cho phép từ 2026-07-30 để thay đổi lên VPS thử được ngay, không
  cần hỏi lại mỗi lần. Khác biệt duy nhất so với thường lệ là merge không chờ ai duyệt tay.
- **CI đỏ thì KHÔNG merge.** Sửa cho xanh đã.
- Chủ repo nhắc lại ngày 2026-09-26: **mỗi lần merge vào `main` phải phát hành số phiên bản
  mới** để các máy khác nhận biết có bản cập nhật. Từ 2026-11-04 việc tăng số do máy làm, xem mục
  dưới. Sau khi merge, xác nhận workflow **Release** chạy xanh và `VERSION` trên `main` đã tăng.
  Không coi việc merge code là đã phát hành xong nếu bản mới chưa được xuất bản.

## Số phiên bản: PR KHÔNG tự chọn số (từ 2026-11-04)

Trước đây mỗi PR tự đặt số, tự sửa `VERSION` và đầu `CHANGELOG.md`. Vài phiên chạy song song là
vài PR cùng sửa đúng mấy dòng đó, nên số liên tục bị giành (0.63.3, 0.63.8, 0.63.10, rồi các số
bỏ trống như 0.442, 0.451, 0.456-0.458), dù đã có quy trình xí chỗ số trước khi code. Chủ repo
chốt 2026-11-04: bỏ hẳn việc PR chọn số.

**Mỗi PR làm đúng một việc:** thêm một file `changelog.d/<slug>.md`, tên không trùng ai. Mẫu ở
`changelog.d/README.md`: dòng `bump: patch` (chỉ sửa lỗi) hoặc `bump: minor` (có gì mới), một
`title` tiếng Anh, khối `## vi` và khối `## en` cùng số nhóm `###`. Kiểm trên máy bằng
`python tools/release.py check`.

- **KHÔNG sửa `VERSION`, `CHANGELOG.md`, `CHANGELOG.en.md`** trong PR.
- **Tiêu đề PR không mang số phiên bản.** Viết thẳng nội dung, ví dụ
  `Fix large Zalo images`. Số nằm trong tiêu đề PR bây giờ có nghĩa là "đang giữ chỗ kiểu cũ", bot
  sẽ né số đó.
- Không cần `git fetch` để dò số, không cần mở PR nháp sớm để xí chỗ.
- Job **Changelog fragment** trong CI đỏ khi PR đổi code mà thiếu file, hoặc file sai mẫu. Thay
  đổi chỉ có tài liệu (`docs/`, file `.md` ở gốc) thì không cần file và không ra bản mới.

**Sau khi merge,** workflow **Release** (`.github/workflows/release.yml`) chạy trên `main`:

1. Đọc `main` mới nhất, mỗi file trong `changelog.d/` thành một số phiên bản riêng, theo thứ tự
   merge. Chép nội dung vào hai file nhật ký, xoá file mảnh, mỗi bản một commit `x.y.z: title (#PR)`.
2. Đưa các commit đó lên `main` qua một PR phát hành `release-bot/...`, merge ngay bằng token của
   chủ repo (`RELEASE_TOKEN`), vì luật bảo vệ `main` không cho đẩy thẳng.
3. Lần merge đó kích hoạt lại workflow, lần này không còn mảnh nào nên nó build và đẩy image Docker
   mang số mới.

Workflow chạy lần lượt từng lượt một, nên hai PR merge cách nhau vài giây vẫn ra hai số khác nhau.
Code đè lên nhau (hai PR sửa cùng chỗ) thì vẫn phải rebase như thường, nhưng `VERSION` và nhật ký
không bao giờ là chỗ xung đột nữa.

**Cài một lần (chủ repo):** tạo fine-grained token trên GitHub cho repo `javis-os`, quyền
**Contents** và **Pull requests** là Read and write, lưu thành secret `RELEASE_TOKEN` của repo
(Settings, Secrets and variables, Actions). Thiếu secret thì lượt Release đỏ kèm đúng câu hướng dẫn
này, image vẫn được build như cũ, và các mảnh nằm chờ trên `main`: thêm secret xong bấm **Run
workflow** ở workflow Release là chúng được phát hành hết.

**Chuyển tiếp:** PR mở từ trước, tự sửa `VERSION` theo kiểu cũ, vẫn merge được (CI chỉ cảnh báo).
Nếu bot đã lấy mất số của nó thì phiên đó đánh số lại như trước, lần cuối cùng.

**PR từ người ngoài:** thiếu mảnh thì CI chỉ cảnh báo. Người merge thêm file `changelog.d/` vào
nhánh trước khi merge, hoặc merge xong mở một PR nhỏ chỉ chứa mảnh đó.

## Chữ hiện lên màn hình (từ 0.67.0)

Giao diện chạy bằng tiếng Anh với người dùng trình duyệt tiếng Anh, nên chữ MỚI viết cho màn hình
không được là tiếng Việt trần:

- **Dashboard (JS, HTML):** thêm khoá vào CẢ `dashboard/i18n/vi.json` lẫn `en.json`, gọi `t("...")`
  (hoặc hàm rào `tw()` của file). `tests/js/test_i18n.mjs` đỏ khi một file JS có chữ Việt trong mã
  chạy mà không nằm trong danh sách ngoại lệ dữ liệu.
- **Server:** chữ trả về cho màn hình (lỗi, thông báo, nhãn) viết `localefmt.chu("tiếng Việt",
  "English")`. Không có request (Telegram, việc nền) thì nó theo `ui_lang` của máy.
- **KHÔNG dịch:** prompt và mô tả tool gửi cho model, regex nhận câu người dùng gõ hay nói, log,
  nội dung ghi vào brain của người dùng. Lý do ở `docs/dev/them-mot-ngon-ngu.md`.

## Tên trong mã viết bằng tiếng Anh (từ 2026-11-06)

Chủ repo chốt 06/11/2026: "đừng dùng các biến tiếng Việt, dự án quốc tế mà". Javis có người dùng và người đóng góp
ngoài Việt Nam, họ phải đọc được mã mà không cần biết tiếng Việt.

- **Mọi tên MỚI viết bằng tiếng Anh:** biến, hàm, lớp, hằng số, tham số, tên file và module, tên test. Ví dụ
  `vocabulary`, `fix_vocabulary`, `transcript_fix.py`, không phải `tu_vung`, `tu_vung_sua`, `chinh_nghe.py`.
- **Tên tiếng Việt có sẵn:** không mở PR chỉ để đổi tên hàng loạt. Khi PR sửa một cụm mã, đổi tên cụm đó sang tiếng
  Anh luôn, kèm mọi chỗ gọi và mọi test, trong cùng PR (06/11/2026: cụm `tu_vung` của `nghe_sua.py` thành
  `vocabulary`, `split_vocabulary`, `BASE_VOCABULARY`, `MAX_VOCABULARY`).
- **Không đổi tên những thứ đã thành hợp đồng** khi chưa có đường chuyển đổi: khoá trong file settings, khoá JSON
  mà dashboard hay máy khác đọc (ví dụ `hotwords_goc` của `/voice/options`), tên route, tên tool gửi cho model.
- **Không phải là tên nên không dịch:** chữ hiện lên màn hình (đi qua i18n, xem mục trên), prompt gửi cho model,
  regex nhận câu tiếng Việt người dùng nói, nội dung ghi vào brain.

## Chữ giải thích gập vào nút (i) (từ 0.214.0)

Chủ repo chốt 18/10/2026: "có quá nhiều dòng giải thích, anh muốn các dòng giải thích đấy gọn lại trong chữ (i)
chứ không để xổ hết ra bên ngoài". Luật cứng cho MỌI màn hình của dashboard:

- **Ngoài mặt chỉ để thứ cần nhìn và cần bấm:** tiêu đề, nhãn, trạng thái, số liệu, ô nhập, nút. Một dòng phụ ngắn
  (tới khoảng 100 ký tự, một câu) được đứng ngoài nếu thiếu nó người ta không biết bấm gì.
- **Câu giải thích dài hơn thế** (vì sao, lưu ý, cách làm từng bước, rủi ro, khác nhau giữa hai lựa chọn) **nằm trong
  nút (i)**: `JavisInfo.btn(t("info.more"))` cạnh tiêu đề hoặc nhãn, `JavisInfo.body(...)` ngay sau, hoặc
  `JavisInfo.pair(html, nhãn)` khi không có tiêu đề để đứng cạnh (`dashboard/info-tip.js`). HTML tĩnh dùng cùng hai lớp
  `info-i` / `info-body`, mẫu ở đầu file đó. Bấm mới mở, trong một popup cạnh nút (điện thoại: bảng từ dưới lên), không xổ ra trong trang (chủ repo 29/10/2026). Khối `info-body` chỉ là nguồn chữ cho popup và luôn ẩn.
- **Không gập:** lỗi và câu xác nhận hiện ra sau khi người dùng bấm (họ đang chờ đúng câu đó), placeholder, nội dung
  người dùng mở ra để đọc (nhật ký cập nhật, nội dung chat, ghi chú). Cảnh báo về tiền hay mất dữ liệu: để ngoài một câu
  ngắn nói rủi ro, phần giải thích vẫn vào (i).
- **Mô tả do server gửi** (plugin, kênh): thẻ hiện tối đa hai dòng, đầy đủ trong (i).
- `tests/python/test_info_tip_rule.py` đỏ khi một chuỗi trên 100 ký tự được vẽ ra mà không nằm trong khối (i). Chuỗi
  dài hợp lệ (lỗi, xác nhận...) ghi vào `tests/python/info_tip_allow.json` kèm lý do; đừng ghi một lời giải thích
  vào đó để cho qua test.

## Không lặp lại tiêu đề trang (từ 0.432.0)

Chủ repo chốt 01/11/2026: "đừng lặp lại tiêu đề như vậy, thật tốn diện tích hiển thị và không có tác dụng gì", "phải
biết tiết kiệm không gian". Đầu mỗi trang đã có thanh tiêu đề chung (`.cview-head`, chữ lấy từ `page.<id>.title` và
`page.<id>.sub`), nên:

- **Thân trang không vẽ lại tên trang**, kể cả khi kèm một câu khẩu hiệu ("Webhook: sự kiện bên ngoài gọi Javis làm
  việc" ngay dưới tiêu đề "Webhook" là sai). Mở trang là vào thẳng thứ cần nhìn: số liệu, danh sách, nút bấm.
- Nút (i) từng đứng cạnh cái tiêu đề thừa thì dời sang cạnh nút hành động chính, hoặc dùng `JavisInfo.pair(html, nhãn)`
  với một nhãn nói đúng nội dung bên trong ("Cách lấy cookie").
- Tiêu đề thẻ bên trong trang phải mang thông tin mới (một con số, một trạng thái), không nhắc lại tên trang hay tên tab.
- Trang tự ẩn `.cview-head` (Nhiệm vụ, Hội thoại, Nhóm, Chat) thì được có tiêu đề riêng, vì không còn gì để lặp.
- Tiết kiệm chỗ nói chung: phần tổng quan đầu trang giữ một hàng thấp, cái gì bấm mới cần thì mở trong popup thay vì
  xổ xuống đẩy cả trang.

## Khung chat: sửa một chỗ là rà và đồng bộ mọi màn (từ 2026-11-05)

Chủ repo chốt 05/11/2026: "từ lần sau các thay đổi về giao diện khung chat là phải rà soát lại toàn bộ các màn khác để
đồng bộ cùng". Lý do: lần đổi mic thành kiểu máy ghi âm chỉ làm ở ô chat chính, chủ phải nhắc thêm một lượt cho trang
Nhóm và trang Hội thoại.

- Đổi cách khung chat trông hoặc chạy (ô nhập, nút mic, nút gửi, đính kèm, Enter, trích dẫn, thẻ tin nhắn...) thì
  **trong cùng PR** phải áp cho mọi màn có khung chat tương tự, không đợi chủ nhắc.
- Các màn hiện có: chat chính (`app.js`, `composer-dictate.js`), Nhóm (`teams.js`), Hội thoại/Chatbot
  (`conversations.js`). Mic đọc chữ dùng chung `dictate.js`: tìm mọi chỗ gọi bằng `grep -n "JavisDictate" dashboard/*.js`.
  Có màn chat mới thì thêm tên vào danh sách này.
- Tự nhảy số thứ tự khi xuống dòng (`chat-list.js`, từ 11/11/2026) chạy bằng MỘT bộ nghe chung, nhận ô chat qua danh
  sách `BOXES` trong file đó. Có ô chat mới thì thêm selector của nó vào `BOXES`, kèm một dòng kiểm trong
  `tests/js/test_chat_list_continue.js`.
- Màn nào cố ý để khác thì ghi lý do trong mô tả PR, và nói rõ với chủ.
- Thêm test cho từng màn đã đổi, để lần sau lệch là CI đỏ.

## Tính năng Zalo mới vào plugin `zalo-extras`, không tạo plugin mới (từ 2026-11-08)

Chủ repo chốt 08/11/2026: "nếu mà update tính năng mới thì cho vào trong plugin của Zalo luôn chứ đừng tạo một plugin
mới". Lý do: mỗi tính năng Zalo từng đẻ thêm một plugin (gửi ảnh, nhóm, đọc ảnh, kết bạn), trang Plugin bị phân mảnh
thành bốn mục cho một thứ chủ coi là một. Gói `javis.zalo` 2.0.0 (kho `javis-store`) đã gộp cả bốn thành MỘT plugin.

- Tool Zalo mới mà MCP của javis-zalo chưa có thì viết trong gói `javis.zalo` của `javis-store`, vào plugin
  `packs/javis.zalo/plugins/zalo-extras/`: thêm hàm vào module đúng mảng (`send_media.py`, `group.py`,
  `read_images.py`, `friend.py`), hoặc một module mới cạnh đó rồi thêm tên vào `_PARTS` trong `plugin.py`. Thêm tên
  tool vào `tools` của `plugin.yaml`, nâng số bản của plugin và của gói cùng nhau.
- **Không tạo thư mục plugin Zalo thứ hai**, trong gói đó hay trong `system/plugins/` của lõi.
  `tests/javis.zalo/test_zalo_extras.py` của kho đỏ khi gói có thêm thư mục plugin, mất một tool hay một tool bị đổi
  mức quyền.
- Mỗi tool tự khai mức quyền khi đăng ký (`min_mode`): đọc là `readonly`, ghi vào brain là `safe`, gửi hay đổi gì trên
  Zalo là `full`.
- Không thuộc luật này: phần lõi của kênh Zalo (đăng nhập QR, vòng đọc Hộp thư, bot trả lời) vẫn nằm trong
  `server/zalo_*.py` như trước. Luật chỉ nói về tool mới cho model gọi.

## Viết CHANGELOG.md

Chủ repo đọc nhật ký cập nhật trên màn hình dọc (2026-08-12), nên viết CHO NGƯỜI ĐỌC TRÊN ĐIỆN
THOẠI, không phải cho lập trình viên đọc diff:

- Nhiều nhất 3 đến 4 gạch đầu dòng mỗi phiên bản, mỗi cái 1 đến 2 câu.
- Nói NGƯỜI DÙNG THẤY GÌ KHÁC, đừng kể tên hàm và đường dẫn file. Chi tiết kỹ thuật để trong
  thân commit và phần mô tả PR.
- Dùng `**` và dấu nháy ngược vừa phải. Trang có render markdown, nhưng một dòng dày đặc ký
  hiệu thì đọc trên màn hẹp rất mệt.
- **Từ 0.68.0 viết HAI bản:** khối tiếng Việt (bản gốc) và khối tiếng Anh, cùng số nhóm `###`.
  Trang Cập nhật hiện bản tiếng Anh cho thiết bị đọc tiếng Anh. Từ 2026-11-04 cả hai viết trong
  cùng file `changelog.d/<slug>.md` (khối `## vi` và `## en`); bot chép sang `CHANGELOG.md` và
  `CHANGELOG.en.md`. `tests/python/test_nhat_ky_song_ngu.py` vẫn canh hai file nhật ký.

## Ngôn ngữ của commit, PR và code (từ 0.68.0)

Repo mở cho người đóng góp quốc tế, nên phần NGƯỜI NGOÀI ĐỌC viết bằng tiếng Anh:

- **Commit message, tiêu đề và mô tả PR:** tiếng Anh.
- **Mọi code mới viết tiếng Anh** (chủ repo chốt 15/10/2026): tên module, hàm, biến, trường dữ
  liệu, comment, docstring, tên test và câu in trong `check(...)`, kể cả khi thêm vào một file cũ
  đang viết tiếng Việt. Không dịch lại phần code cũ không đụng tới. Chữ hiện cho người dùng đi qua
  i18n (`vi.json` có dấu, `en.json`). Bảng từ điển định danh tiếng Việt cũ cho người nước ngoài ở
  `docs/dev/GLOSSARY.md`, kiến trúc ở `ARCHITECTURE.md`.
- **Giữ tiếng Việt:** `CHANGELOG.md` (bản gốc, chủ repo đọc), file quy ước này, spec trong
  `docs/dev/`, và prompt gửi cho model (lý do ở `docs/dev/them-mot-ngon-ngu.md`).
- PR từ người ngoài không cần đụng `VERSION`/CHANGELOG: người merge thêm file `changelog.d/`.

## Bản dịch README và hướng dẫn cài nhanh (từ 0.69.0)

- `README.md` và `QUICKSTART.en.md` (tiếng Anh) là bản gốc. Bản tiếng Việt ở `docs/i18n/vi/` và
  `QUICKSTART.md` vẫn sửa tay cùng lúc như trước.
- Các bản khác ở `docs/i18n/<mã>/` (Trung, Tây Ban Nha, Nhật, Hindi, Bồ Đào Nha, Hàn, Nga, Đức,
  Pháp, Indonesia) là bản MÁY DỊCH. Thanh chọn ngôn ngữ sinh từ danh sách `LANGS` trong
  `tools/check_translations.py` bằng lệnh `--bars`, đừng sửa tay từng file. Dòng đầu mỗi file ghi
  file gốc và hash của nó lúc dịch. Sửa README tiếng Anh xong KHÔNG bắt buộc dịch lại ngay:
  workflow **Translations** sẽ cảnh báo bản nào đã cũ. Khi dịch lại, chạy
  `python tools/check_translations.py --stamp <file>` để cập nhật hash.
- Hình động trong README nằm ở `docs/assets/diagrams/*.svg`: chữ trong hình là tiếng Anh, mọi
  bản dịch dùng chung. Chú thích (alt) của hình thì dịch theo từng bản.
- `tests/python/test_machine_translations.py` canh link chết, anchor lệch và dấu gạch dài trong
  các bản dịch, nên dịch lại xong phải chạy test này.
- **Giao diện chỉ có tiếng Anh và tiếng Việt** (chủ repo chốt 08/11/2026: "gỡ tiếng Đức, chỉ để tiếng Anh và tiếng
  Việt"). File `dashboard/i18n/de.json` đã bị gỡ; đừng nhận thêm từ điển giao diện thứ tiếng khác. Cơ chế đọc từ điển
  chỉ-giao-diện (`dashboard_only_languages`) vẫn để đó, nhưng không có file nào để nó nhận. Mục dưới là lịch sử.
- Server, giọng đọc và tài liệu hướng dẫn đầy đủ chỉ giữ tiếng Anh và tiếng Việt. Chủ repo chốt
  ngày 2026-10-03: thêm thứ tiếng ĐẦY ĐỦ (lang_registry) khi có người dùng thật cần. Từ 0.99.0
  (chủ chốt 2026-10-12, nhận tiếng Đức của @sirschnake) bản dịch CHỈ DASHBOARD (`dashboard/i18n/xx.json`)
  được nhận riêng: nó hiện cho trình duyệt thứ tiếng đó và có trong ô chọn ngôn ngữ, còn server lưu
  `ui_lang` là tiếng Anh (`uiLangForServer` trong console.js) để Telegram, việc nền, giọng đọc ra
  tiếng Anh thay vì rơi về tiếng Việt.
