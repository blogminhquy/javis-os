# Phong cách thiết kế Javis: đọc trước khi làm giao diện

Chủ dự án 15/11/2026: "rà soát lại những lần anh sửa thiết kế để lưu lại phong cách thiết kế. Lần sau làm theo cho anh
đỡ phải nhắc". File này gom mọi lần chủ đã sửa giao diện, lấy từ 2.028 commit (28/06 đến 15/11/2026), `CHANGELOG.md`,
chú thích trong mã, và khoảng 45 phiên Claude Code tháng 10-11/2026 (Javis, kho Javis Store, hoiminh.com, mặt đồng hồ
Garmin). Gu của chủ giống nhau ở mọi dự án, nên phần chung áp cho cả những thứ làm ngoài Javis.

Áp cho: dashboard (`dashboard/`), trang HTML của gói trong kho `javis-store`, và mọi trang HTML làm cho chủ xem. Luật
cứng đã có test thì vẫn nằm ở `docs/quy-uoc-dev.md`; file này dẫn sang chứ không chép lại.

Gặp hai luật ngược nhau: cái có ngày mới hơn thắng (xem mục 11).

---

## 0. Kiểm trước khi gửi

Chạy hết danh sách này trước khi báo xong một việc có giao diện:

1. **Màn mới hoặc thiết kế lại:** đã có bản HTML cho chủ duyệt chưa? Bản đó dựng từ HTML đang có của Javis, không vẽ
   lại từ đầu. Chỉ bỏ bước này khi chủ bảo làm thẳng.
2. **Chụp ảnh thật:** khổ điện thoại 390px và máy tính, giao diện sáng và tối. Không tràn ngang, không chữ nào bị cắt,
   bị đè, hay nằm chồng lên ảnh.
3. **Cỡ:** chữ để đọc từ 16px; ô nhập 16px (iPhone không tự phóng to); vùng bấm từ 44px.
4. **Gọn:** không lặp tiêu đề trang; câu giải thích dài hơn khoảng 100 ký tự nằm trong nút (i).
5. **Thẳng hàng:** một mép trái chung, khoảng cách đều, không có gì dính vào nhau.
6. **Nhấn:** chỉ in đậm thứ quan trọng; icon đủ nghĩa thì bỏ chữ.
7. **Icon:** dùng Lucide; không emoji (trừ 6 emoji thả cảm xúc); logo hãng phải là logo thật.
8. **Chữ:** đi qua `t("...")` hoặc `localefmt.chu(...)`; không có ký tự gạch ngang dài.
9. **Đồng bộ:** đổi khung chat thì áp cho mọi màn có khung chat, trong cùng PR.
10. **Không làm mất gì:** sửa chỗ này mà không xoá nút, icon, chức năng đang có ở chỗ khác.

---

## 1. Gu chung

- **Gọn và tiết kiệm chỗ.** "Phải biết tiết kiệm không gian chứ em" (01/11). Cái gì không cần thì bỏ: nút làm xong khi
  đã có dấu tích, nút loa, nút like, chuông, chỉ số thừa, dòng ghi chú.
- **Vuông vức, đều nhau, thẳng hàng.** "Anh hơi OCD với các bố cục, anh cần kiểu gọn gàng, vuông vức, đều nhau, thuận
  mắt. Em rất thường xuyên cho kiểu bay mỗi nơi một chỗ" (04/11).
- **Ít chạm.** Việc chính xong trong tối đa 3 lần chạm. Popup thay cho mở trang mới, kéo thả thay cho nhiều nút.
- **Học app người ta đã quen,** không tự nghĩ kiểu lạ:
  - app Claude: khung chat, chip và bảng chọn model, gợi ý câu trả lời bấm Tab;
  - Zalo: nhắn tin, thả cảm xúc;
  - Facebook: bình luận mở popup, ảnh bìa;
  - Skool: phần đầu trang cộng đồng;
  - mặt đồng hồ gốc của Garmin: độ mượt.
- **Trong Javis, trang Nhiệm vụ là mẫu phong cách.** Webhook, Link chia sẻ, GitHub, Models đều được làm lại "giống phong
  cách trang nhiệm vụ".
- **Đẹp, hiện đại, mượt.** Chê thẳng font "xấu và trông không được hiện đại", nét "răng cưa", icon "méo". Icon nào đang
  đẹp thì giữ ("nhớ giữ icon đẹp đấy nhé").
- **Dùng hết bề ngang** khi màn rộng (câu trả lời tới 100ch), nhưng không để lỏng lẻo hay phải cuộn ngang.
- **Sáng và rõ** hơn kiểu ấm, giấy cũ (chọn hướng "Sáng và rõ", hoiminh 09/11).

## 2. Chữ

- **Font:** dashboard dùng Be Vietnam Pro, tự host ở `dashboard/fonts/`, khai trong `--font` của `style.css`. Montserrat
  chỉ dùng cho chữ thương hiệu "JAVIS OS". Mọi nút, ô nhập dùng font của app, không để trình duyệt tự chọn.
- **Cỡ để đọc:** 16px là mức dưới (chữ chat, thẻ, nút, mọi thứ trên điện thoại). Khung chat 16px, giãn dòng 1.75. Trang
  của gói dùng 17px cho thân bài.
- **Ngoại lệ, chữ phụ ở chỗ hẹp được nhỏ hơn:** thanh bên, menu thư mục, cột việc, nhãn Node/Link được 12-14px. Chủ đã
  chê 16px "to quá" ở mấy chỗ đó (22/09, 16/10, 26/10). Đừng ép 16px vào chỗ chật.
- **Độ rộng dòng:** câu trả lời tới 100ch.
- **In đậm** chỉ cho việc quan trọng hoặc quá hạn: "cái nào cũng in đậm không thể hiện được sức nặng" (04/11).
- **Số:** có dấu tách nghìn, chỉ viết "K" từ 10k trở lên, viết gọn ("3,8 ngày").
- **Chữ phải hiện trọn:** không cắt mất tên, không đè lên ảnh, không chữ chèn lên ảnh bìa che mất tên.

## 3. Điện thoại là chính

Chủ thử trên iPhone, iPad và app thêm vào màn hình chính, thường gửi ảnh chụp.

- **Khổ điện thoại:** từ 860px trở xuống, thanh bên thành ngăn kéo, một cột. Không xếp hai hàng hai ô: "nhìn trên điện
  thoại rất khó" (15/09).
- **Chọn, xem thêm, (i):** trên máy tính là popup mở sát ngay chỗ bấm; trên điện thoại là bảng kéo từ dưới lên. Riêng
  trang Models dùng bảng kéo lên ở mọi màn (05/11).
- **Không có gì chỉ hiện khi rê chuột.** Điện thoại dùng nút luôn hiện, menu "..." hoặc nhấn giữ.
- **Kéo thả để sắp xếp,** điện thoại thì nhấn giữ rồi kéo. Không dùng mũi tên lên xuống (05/11).
- **Kỹ thuật:**
  - vùng bấm 44px;
  - ô nhập 16px;
  - chừa vùng an toàn `env(safe-area-inset-*)`;
  - chiều cao màn hình dùng `100dvh`;
  - không cuộn ngang;
  - bàn phím mở thì không che ô nhập.
- **Luôn có đường thoát:** nút đóng; nút Back đóng ảnh, PDF, popup. Nút nổi không được che dòng cuối.
- **Điện thoại theo máy tính** nếu được ("làm giống bản máy tính luôn"). Chỉ ẩn trên điện thoại thứ thật sự thừa ở đó
  ("chỉ ẩn ở điện thoại thôi, đừng ẩn ở máy tính").
- **Khung chọn ở khung chat:** trên điện thoại, vòng hạn mức, model và mức suy luận gộp thành một viên, bấm mở một bảng
  (11/11).
- **Nút cài app:** luôn có nút "Cài lên điện thoại" trong menu; đã cài thì ẩn đi.

## 4. Màu, sáng và tối

- **Giao diện sáng là mặc định** ở mọi giờ: "đừng để mặc định giao diện tối nữa" (05/11). Tối và tự động theo giờ chỉ là
  lựa chọn của người dùng (`localStorage["javis.theme"]`, `dashboard/theme.js`).
- **Màu chỉ lấy từ biến của `dashboard/style.css`,** không viết mã màu trần (`tests/python/test_theme_tokens.py`). Màu
  chính:
  - cam nhấn `--accent`: #e85d1f khi sáng, #ff7a3c khi tối;
  - nền cam đặc dưới chữ trắng `--accent-solid`: #c2410c khi sáng;
  - tím phụ `--accent2`.
- **Nút phải thấy rõ:** có viền, đạt chuẩn tương phản AA ("nhiều nút vẫn hơi mờ", 25/10). Nút đứng cạnh ô nhập cao bằng
  ô đó (`--ctl-h`).
- **Màu theo trạng thái:**
  - đỏ: cần bạn;
  - xanh dương: đang làm;
  - cam: đang chờ;
  - xanh lá: xong;
  - vàng hổ phách: model dự phòng đang thay.
- **Nền nhạt để tách nhóm:** "trắng tinh hết là dễ nhìn lẫn lộn" (04/11).
- **Thẻ đặc, không trong suốt** (16/10).
- **Logo hãng là logo thật,** nền trong suốt, to bằng logo bên cạnh, nhìn rõ cả khi giao diện tối.
- **Mỗi bộ icon một tông màu.**

## 5. Bố cục và mật độ

- **Không lặp tiêu đề trang;** phần tổng quan đầu trang chỉ một hàng thấp. Luật đầy đủ ở `docs/quy-uoc-dev.md`, mục
  "Không lặp lại tiêu đề trang".
- **Một mép trái chung cho cả trang.** Mục không có dấu sao vẫn thẳng hàng với mục có sao, không thụt vào.
- **Bo góc lồng nhau phải song song:** góc trong bằng góc ngoài trừ khoảng đệm. Không bo quá tròn trên điện thoại. Khung
  chat và thẻ lớn bo 24px.
- **Khoảng cách đều,** không có gì dính sát vào chữ ("margin các thứ đang dính hết vào nhau", 05/11).
- **Hàng tóm tắt chỉ hiện con số;** chi tiết mở trong popup. Danh sách dài thì mỗi trang 20 mục, có ô tìm.
- **Popup thay cho thả xuống** với nội dung chi tiết, và popup đứng yên tới khi người dùng tự đóng. Danh sách ngắn, đơn
  giản thì mở ngay tại chỗ, không cần popup (07/11).
- **Mở file (HTML, .md, PDF) ngay trong khung,** bấm mới phóng toàn màn hình.
- **Phó nhóm nổi bật trong danh sách thành viên của team** (18/11: "tag phó nhóm trong cài đặt team nổi bật lên một
  chút vì phó nhóm sẽ điều phối toàn bộ team"): đứng ngay dưới trưởng nhóm, nền màu nhấn nhạt, viền trái màu nhấn,
  huy hiệu "Phó nhóm" có ngôi sao. Ảnh và chữ vẫn thẳng mép trái với các hàng khác.
- **Đặt chỗ theo việc:** thứ bấm nhiều ở trên, thứ nguy hiểm ở cuối. Khung viết bài, khung bình luận ghim ở chỗ dễ với.

## 6. Nút, icon, điều khiển

- **Icon thay chữ** khi icon đủ nghĩa; không thêm chữ giải thích icon: "icon lửa và số 12 là được" (04/11).
- **Tới 3 hành động thì hiện thẳng 3 icon,** không gom vào "...". Nhiều hơn thì một nút "..." cho cả hàng; hàng
  trong danh sách hội thoại cũng dùng một nút "..." như app Claude.
- **Số đứng bên phải icon của nó.**
- **Bộ icon:** Lucide (`dashboard/icons.js`), cộng hai icon riêng của Javis (ngôi sao linh vật, mạng nơ-ron). Biểu tượng
  của Javis là ngôi sao.
- **Danh sách:**
  - nút X để bỏ một mục;
  - kéo để đổi chỗ;
  - không có mũi tên lên xuống;
  - không có nút mắt ẩn hiện.
- **Ô tích có hiệu lực ngay,** không bắt bấm Lưu riêng.
- **Ít lựa chọn thì dùng nút chọn tròn (radio),** đừng dùng hộp thả xuống.
- **Nút nguy hiểm** (ngắt, xoá, chạy lại) đứng riêng, ở cuối, màu đỏ, không đặt sát nút hay bấm như nút Chép.
- **Gợi ý nhỏ thì làm nhỏ:** mũi tên gợi ý chỉ là ">" nhỏ ngay sau chữ, không làm thành nút tròn (13/11).
- **Thao tác trên tin nhắn** nằm thành một hàng dưới bong bóng. Thả cảm xúc kiểu Zalo ở góc bong bóng.

## 7. Câu chữ trên màn hình

- **Tiếng Việt như văn nói,** không thuật ngữ khó, không viết tắt lạ. Mô tả "ngắn gọn dễ hiểu thôi".
- **Từ trung tính,** không gắn với một nghề: "đừng có dùng tiền, đơn, đăng bài, nó cá nhân hoá với anh quá" (05/08).
- **Tên gọi đã chốt:**
  - Cộng sự (không gọi trợ lý);
  - trong team: **Trưởng nhóm** là bạn, người tạo team; **Phó nhóm** là cộng sự dẫn team (không gọi "điều phối", 17/11);
  - Mạng nơ-ron (không gọi đồ thị);
  - Node, Link;
  - Tags;
  - "Của Javis" và "Của tôi";
  - Claude, Codex, Grok (không viết CLI hay tên nội bộ);
  - Tài khoản bot.
- **Đặt tên theo lợi ích người dùng thấy** ("Tiết kiệm token", không gọi "Chẩn đoán").
- **Xưng hô theo người dùng.** Chủ là "anh", đừng gọi "chị".
- **Ngôn ngữ giao diện:** chỉ tiếng Việt và tiếng Anh, qua i18n (`docs/quy-uoc-dev.md`, mục "Chữ hiện lên màn hình").
- **Không dùng ký tự gạch ngang dài,** cả em dash lẫn en dash.
- **Lỗi:**
  - một câu thường nói chuyện gì xảy ra và phải làm gì;
  - không hiện JSON hay mã lỗi trần;
  - không bắt chủ làm việc chủ không sửa được.
- **Không im lặng:** nút bị ẩn phải nói vì sao; lỗi không tự biến mất sau vài giây.
- **Không lộ máy móc cho khách:** "anh muốn ẩn đi để như cảm giác người thật nói".

## 8. Giải thích, hướng dẫn, trạng thái trống

- **Giải thích dài vào nút (i):** luật cứng, có test, ở `docs/quy-uoc-dev.md`, mục "Chữ giải thích gập vào nút (i)".
  Bấm (i) thì mở popup cạnh nút; trên điện thoại là bảng kéo lên.
- **Giao diện tốt thì không cần ghi chú.** Chỉ để ngoài một câu ngắn khi có rủi ro mất tiền hay mất dữ liệu.
- **Hướng dẫn từng bước:**
  - bước có số tròn;
  - mỗi bước một câu;
  - chia tab theo nền tảng (ví dụ ChatGPT, Claude, Khác);
  - nói rõ dán vào đâu, không chỉ đưa một nút Chép.
- **Trạng thái trống:** hiện nút tạo hoặc một gợi ý việc nên làm, không chỉ một câu "chưa có gì".
- **Việc chạy nền phải thấy được nhưng gọn:**
  - một viên thuốc kèm popup;
  - khối công cụ đóng sẵn;
  - không đổ danh sách nhắc việc vào khung chat.
- **Báo câu trả lời mới theo nơi đang xem** (chủ chốt 16/11/2026): từng cuộc chat có chấm đỏ khi có câu trả lời chưa
  đọc. Thanh chọn dự án và các dòng trong bộ chọn chỉ báo đỏ cho dự án khác đang có câu trả lời chưa đọc; dự án đang
  xem dùng chấm đỏ ở từng chat, không báo trùng ở thư mục. Mở dự án không đánh dấu các chat là đã đọc.
- **Tạo động lực:** trang Nhiệm vụ có chuỗi ngày, sao, gợi ý việc khi trống (kiểu trò chơi, 04/11).

## 9. Trang HTML của gói trong Javis Store

Mẫu là trang của gói `javis.gate` 2.2.2 (`packs/javis.gate/plugins/javis-gate/plugin.py`, hàm `_trang_cai_dat`). Thứ
tự trên trang:

1. trạng thái (sẵn sàng, hoặc lỗi kèm cách sửa);
2. việc chính (một nút lớn);
3. cài đặt dạng thẻ chọn;
4. danh sách có nút riêng cho từng dòng;
5. phần ít dùng thu gọn;
6. vùng nguy hiểm ở cuối, viền đỏ.

Mọi giải thích nằm sau nút (i), đóng sẵn.

- Thân chữ 17px, tối thiểu 16px; nút cao 48px; không tràn ngang ở 390px; chụp cả sáng lẫn tối.
- JS của trang viết thành chuỗi thường, đọc đường dẫn từ một khối JSON, để khỏi nhân đôi ngoặc trong f-string.
- **Sáng/tối, màu và font theo dashboard** (từ `javis.gate` 2.2.2):
  - một đoạn script trong `<head>` đọc `localStorage["javis.theme"]`, cùng phép tính với đoạn đầu
    `dashboard/index.html`; chưa chọn thì sáng;
  - màu lấy theo biến của `dashboard/style.css`;
  - font Be Vietnam Pro từ `/static/fonts/fonts.css`, mở được khi chưa đăng nhập.

  Trang gói mới chép `_JS_GIAO_DIEN` và `_CSS` của gói đó. Không dùng `prefers-color-scheme`.

## 10. Cách làm việc thiết kế với chủ

- **Đọc kỹ ảnh chụp chủ gửi:** đó là bản mô tả lỗi.
- **Tự phản biện trước:** liệt kê chỗ chưa ổn của màn hiện tại, rồi mới đề xuất. Chủ hay giao việc theo kiểu "tự phản
  biện và thiết kế lại".
- **Duyệt trước, code sau:** màn mới hoặc thiết kế lại thì làm bản HTML cho chủ duyệt trước ("quên không bảo em thiết kế
  html trước đã, rồi mới code", 05/11). Dựng từ HTML hiện có của Javis, không vẽ lại từ đầu.
- **Gửi ảnh trước và sau** ở khổ điện thoại, kèm danh sách ngắn những gì đã đổi.
- **Không thiết kế lại thứ đã có:** "độ sâu suy nghĩ có thiết kế rồi mà đừng thiết kế lại nó nữa". Cái gì có rồi thì
  dùng lại, đừng bê nguyên một bản sao.
- **Sửa một màn thì rà mọi màn giống nó** ("Rà lại luôn tất cả màn") và sửa cùng lúc.
- **Báo cáo ngắn, đọc được trên điện thoại.** Chủ quyết nhanh ("merge luôn"); việc sửa đường đơn giản hơn thì bỏ code
  (lần vệt mờ iOS 09/11).

## 11. Những lần đổi ý: cái mới nhất thắng

| Chủ đề | Trước | Bây giờ |
|---|---|---|
| Giao diện mặc định | tối, rồi tự động 06:00-18:00 | **sáng ở mọi giờ** (05/11) |
| Độ rộng câu trả lời | 76, rồi 72 ký tự | **tới 100ch** (09/11) |
| Kiểu trả lời trong chat | văn nói, không bảng | **trình bày cho mắt đọc**, có bảng khi so sánh (09/08) |
| Thả cảm xúc | 6 nút kèm bảng lý do | **một like kiểu Zalo**, bỏ bảng lý do |
| Menu linh vật | mũi tên, nút mắt | **kéo thả, nút X cho mọi mục** (05/11) |
| Linh vật trên điện thoại | 150px | **100px** |
| Chữ nút "Cho sao" ở thanh bên | 16px | **13px** (16px to quá) |
| Xưng hô mặc định | bạn/mình | **theo người dùng** (14/09) |
| Ngôn ngữ giao diện | có cả tiếng Đức | **chỉ Việt và Anh** (08/11) |
| Sao ưu tiên | 3 sao một ngày | **1 sao** |
| Dải công cụ cạnh chọn model | bỏ hẳn | **chỉ 3 công cụ gần nhất** |
| Tên vai trong team | trưởng nhóm, rồi điều phối | **phó nhóm** cho cộng sự dẫn team, **trưởng nhóm** là bạn (17/11) |
| Việc team chờ bạn trong khung chat | thẻ dài ở đầu khung chat | **viên thuốc một dòng trên khung nhập** như việc nền ở chat chính, tự ẩn khi bạn đã nhắn sau lúc việc dừng (17/11) |

## 12. Trích lời chủ theo thời gian

Để tra nhanh khi gặp lại một chủ đề; nguồn đầy đủ ở commit và PR tương ứng.

- **31/07:** "các phần mô tả không cần thiết phải dài đến thế, ngắn gọn dễ hiểu thôi".
- **06/08:** khung brain "quá bé không thấy gì cả".
- **07/08:** "muốn xuống cách dòng nhiều hơn chứ đọc khó quá".
- **05/08:** "đừng có dùng tiền, đơn, đăng bài, nó cá nhân hoá với anh quá".
- **15/09:** "hai hàng hai ô nhìn trên điện thoại rất khó".
- **18/10:** "có quá nhiều dòng giải thích, anh muốn các dòng giải thích đấy gọn lại trong chữ (i)".
- **25/10:** "nhiều nút vẫn hơi mờ".
- **27/10:** "uxui nhìn điện thoại trong phần team loạn lắm".
- **29/10:** (i) "phải hiện popup chứ không phải hiện tooltip bên dưới".
- **01/11:**
  - "đừng lặp lại tiêu đề, thật tốn diện tích hiển thị";
  - "popup lên chứ không drop xuống";
  - "Rà lại luôn tất cả màn".
- **04/11:**
  - "anh hơi OCD với các bố cục";
  - "đường bo với đường của chấm tròn phải đều nhau kiểu song song";
  - "cái nào cũng in đậm không thể hiện được sức nặng";
  - "trắng tinh hết là dễ nhìn lẫn lộn".
- **05/11:**
  - "giao diện sáng là màn mặc định";
  - "kéo lên kéo xuống được chứ không phải mũi tên";
  - "quên không bảo em thiết kế html trước đã";
  - "cần có logo đúng của các nhà cung cấp";
  - "từ lần sau các thay đổi về giao diện khung chat là phải rà soát lại toàn bộ các màn khác".
- **06/11:** "các button làm thành icon như phong cách trang nhiệm vụ"; bỏ nút lịch sử và reset "không cần thiết".
- **07/11:** dòng vai trò xám "vừa xấu vừa không đọc được thông tin gì cả".
- **09/11:**
  - "anh muốn kéo rộng ra để tận dụng màn hình";
  - "làm giống bản máy tính luôn";
  - "nhớ giữ icon đẹp đấy nhé".
- **10/11 (hoiminh):**
  - "chỉ cần nhấn giữ kéo thả thôi sao phải khổ nhiều nút vậy";
  - "làm 1 ảnh to rồi thêm slide ở cuối".
- **11/11:** điện thoại "gọn hơn"; hoiminh: "ôi nhìn admin gói này trông kinh khủng quá, tự phản biện và thiết kế lại".
- **13/11:**
  - "không cần hiện chữ tab đâu em, và nhớ phải giữ lại các nút khác";
  - "mũi tên nhỏ theo kiểu > thôi".
- **14/11:** popup chọn model "bị nhảy lên trên khá xa với khung".
- **15/11:**
  - "các phần thông tin hướng dẫn làm gọn lại nút i và các bước nhìn dễ đọc";
  - "tự phản biện lại ux ui trang này rồi thiết kế lại".
- **16/11:**
  - "cải tiến phần việc của team giống trải nghiệm của trang nhiệm vụ ... ux ui có nhiều icon ít button";
  - "click vào việc đã hoàn thành thì phải có 1 tóm tắt những gì đã làm".
- **17/11:**
  - "các thông tin này có thể co gọn lại và để xuống dưới giống như việc kanban nền chạy";
  - "chữ điều phối đổi thành phó nhóm và người tạo ra nhóm mặc định là trưởng nhóm";
  - "khi đã nhắn ở khung chat xử lý vấn đề thông báo rồi thì phải tự tắt cái thông báo đó đi";
  - "mấy cái phần chia việc với Làm này cũng cần làm kiểu tag trông cho đẹp, chia việc trên 1 dòng thôi";
  - "thứ tự sẽ là Việc, thông tin, rồi mới đến team" (chưa có việc thì mở tab Thông tin).
