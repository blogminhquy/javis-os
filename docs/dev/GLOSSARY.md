# Glossary: Vietnamese words in the Javis code base

Javis was written by a Vietnamese team, so most identifiers, file names, comments and UI keys
are Vietnamese. This page lets an English reader decode names like `_doi_ngon_ngu_hat_giong`
("change the language of the seed files") or `NGOAI_LE_DU_LIEU` ("data exceptions").
Start with [ARCHITECTURE.md](../../ARCHITECTURE.md) for how the system fits together.

The word list below was built from real data: every identifier in `server/**/*.py` and
`dashboard/*.js` was split on `_` and camelCase boundaries, the parts were counted, English
words were dropped, and the most useful Vietnamese ones were kept. Every example identifier in
the tables exists in the code (two marked "tests" exist only under `tests/`).

## How to read a Vietnamese identifier

- **Diacritics are dropped.** Vietnamese is written with tone marks and modified letters
  (`ă â đ ê ô ơ ư`, plus five tones). Identifiers keep only ASCII, and `đ` becomes `d`. So
  `ngôn ngữ` (language) is written `ngon_ngu`, and `đường dẫn` (path) is `duong_dan`.
- **Words are syllables.** Most Vietnamese words are one or two syllables, and many concepts
  are two-syllable compounds (`danh sách` = list, `trạng thái` = state). Read the compound
  together: `trang_thai` is one word, "state", not "page" + "condition".
- **Styles.** Python uses snake_case (`muc_quyen`, `MUC_QUYEN_MAC_DINH`); JavaScript uses
  camelCase (`veDanhSach` = draw the list). Vietnamese and English mix freely:
  `_tg_model_hieu_luc` is "the effective Telegram model".
- **Single syllables are ambiguous.** Without diacritics one spelling can stand for several
  words. `chu` may be `chữ` (text, letter) or `chủ` (owner); `ban` may be `bản` (version,
  copy) or `bạn` (you); `do` may be `độ` (degree), `đo` (measure) or the `do` in `lý do`
  (reason). The table lists the common readings, most frequent first; the neighbouring word
  usually settles it (`ghi_chu` = note, `chu_khach` = the customer's text, `petMayChu` = the
  server-machine mascot).
- **Word order is head first.** Vietnamese puts the modifier after the noun, so
  `ten_bo_nao` is "name of brain" and `thu_muc_bo_nho` is "folder of memory".

## Common prefixes and abbreviations

Many functions and flags start with a Vietnamese verb or particle:

| Prefix | Vietnamese | Meaning | Example |
|--------|------------|---------|---------|
| `la`, `la_` | là | "is" (boolean test) | `la_git`, `laCuoc` |
| `co_` | có | "has", "there is" | `co_phien`, `co_dinh_kem` |
| `da_` | đã | "already", "has been" (past) | `da_cai`, `da_nap` |
| `dang` | đang | "currently", "-ing" | `dangChay`, `dangTai` |
| `can_` | cần | "needs to" | `can_xac_nhan`, `can_xoa` |
| `so_` | số | "number of" | `so_chua_doc`, `so_hoi_thoai` |
| `ve` | vẽ | draw, render (dashboard) | `veDanhSach`, `veLai` |
| `tai` | tải | load, fetch | `taiDanhSach`, `taiThem` |
| `mo` | mở | open | `moPhien`, `moKho` |
| `doc_` / `ghi_` | đọc / ghi | read / write | `doc_duoc`, `ghi_su_kien` |

Short abbreviations seen in names: `tg` = Telegram (`_tg_answer`), `tk` = `tài khoản`
(account, `taiTK`), `ds` = `danh sách` (list, `_kenhDS`), `qd` = `quyết định` (decision,
`_lang_qd`), `dk` = `đính kèm` (attachment) in `khoi_dk`.

## Whole-phrase names that appear everywhere

These compounds recur so often that it pays to learn them as single words.

| In code | Vietnamese | English | Example |
|---------|------------|---------|---------|
| `mac_dinh` | mặc định | default | `MAC_DINH`, `MUC_QUYEN_MAC_DINH` |
| `chuan_hoa` | chuẩn hoá | normalise | `chuan_hoa_endpoint` |
| `thu_muc` | thư mục | folder, directory | `thu_muc_id` |
| `duong_dan` | đường dẫn | path | `duong_dan_router` |
| `danh_sach` | danh sách | list | `veDanhSach` |
| `trang_thai` | trạng thái | state, status | `TRANG_THAI` |
| `ly_do` | lý do | reason | `_ly_do_im` |
| `muc_quyen` | mức quyền | permission level | `MUC_QUYEN` |
| `che_do` | chế độ | mode | `dat_che_do` |
| `ket_qua` | kết quả | result | `KetQua` |
| `ket_noi` | kết nối | connection, connect | `ket_noi_theo_id` |
| `noi_dung` | nội dung | content | `noi_dung` |
| `du_lieu` | dữ liệu | data | `NGOAI_LE_DU_LIEU` (tests) |
| `tai_khoan` | tài khoản | account | `_gan_tai_khoan` |
| `tai_lieu` | tài liệu | document | `_liet_ke_tai_lieu` |
| `ngon_ngu` | ngôn ngữ | language | `ngon_ngu_giao_dien` |
| `giao_dien` | giao diện | user interface | `cho_giao_dien` |
| `bo_nho` | bộ nhớ | memory | `_thu_muc_bo_nho` |
| `bo_nao` | bộ não | brain (the chosen engine, or a vault) | `ten_bo_nao` |
| `bo_qua` | bỏ qua | skip, ignore | `bo_qua_cache` |
| `toi_da` | tối đa | maximum | `GOAL_TOI_DA` |
| `toi_thieu` | tối thiểu | minimum | `_GIU_TOI_THIEU` |
| `cap_nhat` | cập nhật | update | `capNhatNutTai` |
| `xac_nhan` | xác nhận | confirm | `can_xac_nhan` |
| `tom_tat` | tóm tắt | summary, summarise | `tomTatDoiTuong` |
| `tra_loi` | trả lời | reply, answer | `ngon_ngu_tra_loi` |
| `hoi_thoai` | hội thoại | conversation | `tab_hoi_thoai` |
| `viec_nen` | việc nền | background job | `_viec_nen_view` |
| `tien_trinh` | tiến trình | process | `tien_trinh_nen` |
| `nhac_hen` | nhắc hẹn | reminder | `_bao_nhac_hen` |
| `lich_su` | lịch sử | history | `daDayLichSu` |
| `canh_bao` | cảnh báo | warning | `NGUONG_CANH_BAO` |
| `hien_tai` | hiện tại | current | `muc_hien_tai` |
| `cong_cu` | công cụ | tool | `CONG_CU` |
| `tu_dong` | tự động | automatic | `chatbot_tu_dong` |
| `du_phong` | dự phòng | fallback, spare | `MODELS_DU_PHONG` |
| `nang_luc` | năng lực | capability | `nang_luc` |
| `he_thong` | hệ thống | system | `lenh_he_thong` |
| `het_luot` | hết lượt | out of quota (turns) | `loi_het_luot` |
| `dang_nhap` | đăng nhập | log in | `nhat_ky_dang_nhap` |
| `hat_giong` | hạt giống | seed (seed files of a new brain) | `HAT_GIONG` |
| `ngoai_le` | ngoại lệ | exception (to a rule) | `NGOAI_LE_DU_LIEU` (tests) |
| `phien_ban` | phiên bản | version | `bac_phien_ban` |
| `rang_buoc` | ràng buộc | binding, constraint | `dat_rang_buoc` |
| `ngan_sach` | ngân sách | budget | `_kiem_ngan_sach` |
| `tiet_kiem` | tiết kiệm | saving (tokens, money) | `_uoc_tinh_tiet_kiem` |

## Word table

Alphabetical. The "With diacritics" column lists the words one spelling can stand for, most
frequent first; the meaning column gives the compound in which a word usually appears.

| In code | With diacritics | English meaning | Example identifier |
|---------|-----------------|-----------------|--------------------|
| `an` | an, ẩn | safe (`an toàn`); hidden | `_an_toan_de_xoa` |
| `anh` | ảnh, Anh | image; English (`tiếng Anh`) | `la_anh`, `la_tu_tieng_anh` |
| `ao` | ảo | virtual, fake; `ảo giác` = hallucination | `tai_khoan_ao`, `loc_ao_giac` |
| `ap` | áp | apply (`áp dụng`) | `apDungTrangThai` |
| `bai` | bài | lesson, article; `bài học` = lesson learned | `_BAI_HOC_HEADER` |
| `ban` | bản, bạn | version, copy; `bản dịch` = translation; you | `chon_ban_dich` |
| `bang` | bảng, bằng | table; by means of, equal | `bangMau` |
| `bao` | báo, bảo, bao | report, notify; protect (`bảo vệ`); include (`bao gồm`) | `bao_cao_tuan`, `_bao_ve_khung_goc` |
| `bat` | bật, bắt | turn on; start (`bắt đầu`); catch | `_batDauLuot`, `batLive` |
| `bien` | biến | variable; change | `_KHOA_BIEN` |
| `bo` | bỏ, bộ | drop, remove; a set or kit (`bộ nhớ` = memory) | `_bo_dau`, `ten_bo_nao` |
| `buoc` | bước, buộc | step; bind (`ràng buộc`) | `veKhoiBuoc`, `rang_buoc` |
| `ca` | cả | all (`tất cả`), both (`cả hai`) | `chonTatCa`, `ca_hai` |
| `cach` | cách | way, method; gap, spacing | `KHOANG_CACH_GIAY` |
| `cai` | cài | install; `cài đặt` = settings | `lenh_cai`, `_so_cai_dat` |
| `cam` | cấm, cảm | forbidden; touch (`cảm ứng`) | `_HOST_KY_TU_CAM` |
| `can` | cần | need, must | `can_xac_nhan` |
| `canh` | cảnh, cạnh | warning (`cảnh báo`); context (`ngữ cảnh`); beside | `canh_bao`, `tep_ngu_canh` |
| `cao` | cao, cáo | high; report (`báo cáo`) | `diem_cao`, `_bao_cao_token` |
| `cap` | cấp, cập, cặp | level, grant; update (`cập nhật`); pair | `capNhatNutTai`, `nang_cap` |
| `cau` | câu, cấu | sentence, question (`câu hỏi`); configuration (`cấu hình`) | `cau_hoi`, `_cau_hinh` |
| `chan` | chặn, chẩn | block; diagnose (`chẩn đoán`) | `_LUAT_CHAN`, `chan_doan_loi` |
| `chay` | chạy | run | `luot_dang_chay` |
| `che` | chế | mode (`chế độ`) | `dat_che_do` |
| `chi` | chỉ, chi | only, point to; detail (`chi tiết`); address (`địa chỉ`) | `chi_huong_dan`, `dia_chi` |
| `chinh` | chính, chỉnh | main; adjust (`hiệu chỉnh`) | `_ten_model_chinh` |
| `cho` | cho, chờ, chỗ | for, give, let; wait; place | `cho_giao_dien`, `cho_duyet` |
| `chon` | chọn | choose, select | `chonMacDinh` |
| `chot` | chốt | finalise, lock in | `_chot_van` |
| `chu` | chữ, chủ | text, letter; owner | `da_co_chu`, `petMayChu` |
| `chua` | chưa, chứa | not yet; contain | `so_chua_doc` |
| `chuan` | chuẩn | standard; `chuẩn hoá` = normalise | `chuan_hoa_endpoint` |
| `chung` | chung | shared, common | `_goc_chung` |
| `chuoi` | chuỗi | string, chain | `_tim_chuoi` |
| `chuyen` | chuyển, chuyên | switch, transfer; specialised | `chuyenSangCoBan` |
| `co` | có, cờ, cỡ | has, there is; flag; size | `co_phien`, `co_that` |
| `con` | còn, con | remaining, still; child | `con_lai`, `bang_con` |
| `cong` | công, cộng | tool (`công cụ`); collaborator (`cộng sự`); community (`cộng đồng`) | `CONG_CU`, `laCongDong` |
| `cu` | cũ, cụ | old, previous; part of `công cụ` (tool) | `_tinCu` |
| `cua` | của, cửa | of, belonging to; door (`cửa sổ` = window) | `kenhCua`, `cua_so` |
| `cuoc` | cuộc | a conversation or call (`cuộc trò chuyện`, `cuộc gọi`) | `laCuoc`, `_cuocGoiDaNoi` |
| `cuoi` | cuối | last, end | `lan_cuoi` |
| `da` | đã, đa | already, done; multi; maximum (`tối đa`) | `da_cai`, `toi_da` |
| `dan` | dẫn | lead; path (`đường dẫn`); guide (`hướng dẫn`) | `duong_dan`, `login_huong_dan` |
| `dang` | đang, đăng, dạng | currently; log in (`đăng nhập`); format (`định dạng`) | `dangChay`, `nhat_ky_dang_nhap` |
| `danh` | danh | list (`danh sách`); identity (`danh tính`) | `veDanhSach`, `loi_danh_tinh` |
| `dat` | đặt | set, place | `dat_rang_buoc` |
| `dau` | đầu, dấu | start, head; mark, diacritic | `bat_dau`, `bo_dau` |
| `de` | để, đề | in order to; title (`tiêu đề`); issue (`vấn đề`) | `tieu_de`, `van_de` |
| `dem` | đếm | count | `demTu` |
| `den` | đến | to, until | `den_ngay` |
| `dich` | dịch, đích | translate; target, destination | `chon_ban_dich`, `links_dich` |
| `dien` | diện, điện | interface (`giao diện`); phone (`điện thoại`) | `ngon_ngu_giao_dien`, `laDienThoai` |
| `dinh` | định, đính | default (`mặc định`); decision (`quyết định`); attached (`đính kèm`) | `mac_dinh`, `co_dinh_kem` |
| `do` | độ, đo, do | degree, level; measure; reason (`lý do`); mode (`chế độ`) | `do_sau`, `do_duoc`, `ly_do` |
| `doc` | đọc, dọc | read; vertical | `doc_duoc` |
| `doi` | đổi, đợi, đối | change, swap; wait; object (`đối tượng`) | `_doi_su_kien`, `apDoiTuong` |
| `don` | dọn, đơn | clean up; order, single | `da_don` |
| `dong` | dòng, đóng, động | line, row; close; automatic (`tự động`) | `loi_thanh_dong`, `dongMenu`, `tuDong` |
| `du` | dữ, dự | data (`dữ liệu`); fallback (`dự phòng`) | `du_lieu`, `ten_du_phong` |
| `dung` | dùng, đúng, dừng | use; correct; stop; content (`nội dung`) | `nutDung`, `noi_dung` |
| `duoc` | được | allowed, can, obtained | `vao_duoc_nhom` |
| `duoi` | đuôi, dưới | suffix, file extension; below | `DUOI_ANH` |
| `duong` | đường | path, route, road | `_duong_lui` |
| `dut` | đứt | cut, broken; `đứt mạng` = network drop | `_tinDutMang` |
| `duyet` | duyệt | approve, review; browser (`trình duyệt`) | `cho_duyet`, `_khong_co_trinh_duyet` |
| `ghep` | ghép | join, combine | `ghepDuoiTam` |
| `ghi` | ghi | write, record; note (`ghi chú`) | `ghi_su_kien`, `ghiChu` |
| `ghim` | ghim | pin | `_bot_ghim_duong` |
| `giam` | giảm, giám | reduce; supervise (`giám sát`) | `giamChuyenDong`, `_giam_sat` |
| `giao` | giao | hand over; interface (`giao diện`) | `cho_giao_dien` |
| `giay` | giây | second (time unit) | `REAP_GIAY` |
| `gio` | giờ | hour, time; now (`bây giờ`) | `theo_gio`, `bayGio` |
| `gioi` | giới | limit (`giới hạn`) | `gioi_han` |
| `giong` | giọng, giống | voice; similar; seed (`hạt giống`) | `nhapGiong`, `HAT_GIONG` |
| `giu` | giữ | keep, hold | `_giu_cau_goc` |
| `go` | gỡ, gõ | remove, uninstall; type (keyboard) | `da_go`, `chuNguoiGo` |
| `goc` | gốc, góc | root, original, source; corner | `_bao_ve_khung_goc` |
| `goi` | gọi, gói, gợi | call; package, plan; suggestion (`gợi ý`) | `goi_y`, `gia_goi` |
| `gom` | gom | gather, group | `gomNhom` |
| `gui` | gửi | send | `gui_loi` |
| `han` | hạn | limit; deadline; `hết hạn` = expired | `gioi_han`, `den_han` |
| `hang` | hàng, hạng | row, queue; rank (`xếp hạng`) | `HangLuot`, `xep_hang` |
| `hat` | hạt | seed (`hạt giống`) | `_doi_ngon_ngu_hat_giong` |
| `he` | hệ | system (`hệ thống`); coefficient (`hệ số`) | `lenh_he_thong`, `he_so` |
| `hen` | hẹn | appointment; reminder (`nhắc hẹn`) | `_bao_nhac_hen` |
| `het` | hết | run out, end | `het_luot` |
| `hien` | hiện, hiển | show, appear; current (`hiện tại`); display (`hiển thị`) | `hien_tai`, `nhanHienThi` |
| `hieu` | hiệu | in effect (`hiệu lực`); effect (`hiệu ứng`); calibrate (`hiệu chỉnh`) | `_tg_model_hieu_luc` |
| `hinh` | hình | shape, image; configuration (`cấu hình`); screen (`màn hình`) | `manHinhLoi` |
| `hoa` | hoá | the "-ise" suffix: `chuẩn hoá` normalise, `mã hoá` encrypt | `ma_hoa` |
| `hoach` | hoạch | plan (`kế hoạch`) | `khoi_ke_hoach` |
| `hoc` | học | learn | `_ghi_bai_hoc` |
| `hoi` | hỏi, hội | ask; conversation (`hội thoại`) | `cau_hoi`, `so_hoi_thoai` |
| `hom` | hôm, hòm | day (`hôm nay` = today); box (`hòm thư` = mailbox) | `tin_hom_nay`, `_bo_vao_hom_thu` |
| `hong` | hỏng | broken, failed | `micHong` |
| `hop` | hợp, hộp | valid (`hợp lệ`); box | `host_hop_le`, `dongHop` |
| `hua` | hứa | promise; `hứa suông` = empty promise | `_canh_bao_hua_suong` |
| `huong` | hướng | direction; instructions (`hướng dẫn`) | `xaLuuHuongDan` |
| `huy` | huỷ | cancel | `huy_dang_ky` |
| `im` | im | silent; `im lặng` = silence | `im_lang_khi_loi` |
| `ke` | kế, kê | plan (`kế hoạch`); enumerate (`liệt kê`); statistics (`thống kê`) | `thong_ke`, `_liet_ke_tai_lieu` |
| `kem` | kèm | attached, along with | `kem_prompt` |
| `kenh` | kênh | channel | `kenhLoc` |
| `ket` | kết | result (`kết quả`); connection (`kết nối`); end (`kết thúc`) | `ket_qua`, `ket_thuc` |
| `khac` | khác | other, different | `kenhKhac` |
| `khach` | khách | customer, guest | `ghi_tin_khach` |
| `khi` | khi | when | `xoa_khi_rong` |
| `kho` | kho | store, repository | `ghi_kho` |
| `khoa` | khoá | key; lock | `khoa_chinh`, `_KHOA_NGON_NGU_RE` |
| `khoan` | khoản | account (`tài khoản`) | `_gan_tai_khoan` |
| `khoi` | khối, khởi, khôi | block (of text or prompt); start; restore (`khôi phục`) | `veKhoiBuoc`, `ma_khoi_phuc` |
| `khong` | không | no, not; zero; without | `khong_dau` |
| `khop` | khớp | match | `NGUONG_KHOP_TU` |
| `khung` | khung | frame, panel, the chat box | `traKhungChat` |
| `kiem` | kiểm, kiệm | check (`kiểm tra`); save (`tiết kiệm`) | `kiem_tra_nhanh`, `tiet_kiem` |
| `ky` | ký, kỳ, kỹ | character (`ký tự`); period; log (`nhật ký`); technical (`kỹ thuật`) | `loi_ky_thuat` |
| `la` | là, lạ | is; strange | `la_git` |
| `lai` | lại | again, back | `veLai` |
| `lam` | làm | do, make; refresh (`làm mới`) | `lam_moi_hub` |
| `lan` | lần, làn | time, occurrence; lane | `_mot_lan`, `_LAN_NHANH_DA_BAO` |
| `lang` | lặng | silence (`im lặng`) | `im_lang` |
| `lay` | lấy | get, take, fetch | `lay_token` |
| `le` | lệ | valid (`hợp lệ`); ratio (`tỷ lệ`) | `hop_le`, `ty_le` |
| `lenh` | lệnh | command | `lenh_he_thong` |
| `lich` | lịch | history (`lịch sử`); schedule | `daDayLichSu` |
| `lien` | liên | consecutive (`liên tiếp`); link (`liên kết`) | `_gay_lien_tiep`, `_la_lien_ket_ngoai` |
| `liet` | liệt | list out (`liệt kê`) | `_liet_ke_home` |
| `lieu` | liệu | data (`dữ liệu`); document (`tài liệu`) | `_tra_tai_lieu` |
| `loai` | loại | type, kind; exclude | `cungLoai`, `loai_tru` |
| `loc` | lọc | filter | `_botLoc` |
| `loi` | lỗi, lời | error; words, reply (`trả lời`) | `chan_doan_loi`, `nguon_tra_loi` |
| `lop` | lớp | layer, class | `lop_phu` |
| `luat` | luật | rule | `_LUAT_CHAN` |
| `luc` | lúc, lực | at (a time); capability (`năng lực`) | `roi_luc`, `nang_luc` |
| `luot` | lượt | turn (one exchange); quota unit | `tong_luot` |
| `luu` | lưu | save | `luuChon` |
| `ly` | lý | reason (`lý do`); handle (`xử lý`) | `_ly_do_im`, `_da_xu_ly` |
| `ma` | mã | code, id, token | `ma_khoi_phuc`, `ma_thoat` |
| `mac` | mặc | default (`mặc định`) | `MUC_QUYEN_MAC_DINH` |
| `mach` | mạch | circuit, connection thread | `_tg_ngat_mach` |
| `mang` | mạng, mang | network; carry | `_CO_MANG_PROMPT` |
| `mat` | mắt, mất, mặt | eye; lose; face | `MAU_MAT` |
| `mau` | màu, mẫu | colour; sample, template, pattern | `mauMatCua`, `_mau_loi_hua` |
| `mo` | mở, mô | open; description (`mô tả`) | `moPhien`, `mo_ta` |
| `moc` | mốc | marker, milestone, timestamp | `_MOC_DI_TRUOC` |
| `moi` | mới, mỗi, mọi | new; each; every | `moi_nhat`, `TYPING_MOI_GIAY` |
| `mot` | một | one, a | `_mot_luot` |
| `muc` | mục, mức | item, section (`thư mục` = folder); level | `thu_muc`, `muc_quyen` |
| `nang` | năng, nâng | capability (`năng lực`); upgrade (`nâng cấp`) | `nang_luc`, `nang_cap` |
| `nao` | não, nào | brain (`bộ não`); which | `bo_nao`, `khi_nao` |
| `nap` | nạp | load | `da_nap` |
| `nay` | này | this; today (`hôm nay`) | `muc_nay` |
| `nen` | nền, nên, nén | background; should; compressed | `_viec_nen`, `da_nen` |
| `ngan` | ngân, ngắn | budget (`ngân sách`); short | `_kiem_ngan_sach`, `parts_ngan` |
| `ngat` | ngắt | interrupt, disconnect | `ngatWs` |
| `ngay` | ngày, ngay | day; immediately | `theo_ngay` |
| `nghe` | nghe | listen, hear | `_nghe_tin_thoai` |
| `nghi` | nghĩ, nghỉ | think (`suy nghĩ`); rest | `_nhac_suy_nghi` |
| `ngoai` | ngoài | outside, external | `dongMenuNgoai` |
| `ngon` | ngôn | language (`ngôn ngữ`) | `theo_ngon_ngu` |
| `ngu` | ngữ, ngủ | language (`ngôn ngữ`); context (`ngữ cảnh`); sleep | `ten_ngu_canh` |
| `nguoi` | người | person; user (`người dùng`) | `theo_nguoi_dung` |
| `nguon` | nguồn | source | `vault_nguon` |
| `nguong` | ngưỡng | threshold | `NGUONG_CANH_BAO` |
| `nhac` | nhắc | remind, mention | `_co_nhac_ten` |
| `nhan` | nhận, nhãn, nhấn | receive; label; press; confirm (`xác nhận`) | `KENH_NHAN`, `xac_nhan` |
| `nhanh` | nhanh, nhánh | fast; branch | `kiem_tra_nhanh`, `nhanh_hien_tai` |
| `nhap` | nhập, nháp | input, enter; log in (`đăng nhập`); draft | `doi_dang_nhap`, `khop_ban_nhap` |
| `nhat` | nhất, nhật | most, "-est"; update (`cập nhật`); log (`nhật ký`) | `gan_nhat`, `_ghi_nhat_ky` |
| `nhip` | nhịp | beat, tick interval | `NHIP_HOI_THAM` |
| `nho` | nhớ, nhỏ | remember, memory (`bộ nhớ`); small | `_thu_muc_bo_nho`, `_BIN_NHO` |
| `nhom` | nhóm | group | `NHOM_MAC_DINH` |
| `noi` | nội, nói, nối, nơi | inner (`nội dung` = content); speak; connect; place | `noi_dung`, `ket_noi` |
| `nuoi` | nuôi | adopt, keep alive | `_nhan_nuoi_tien_trinh` |
| `nut` | nút | button | `capNhatNutTai` |
| `phan` | phần, phân | part; divide; percent (`phần trăm`) | `phan_tram` |
| `phat` | phát | play (audio), emit | `TREO_DANG_PHAT` |
| `phep` | phép | permission (`cho phép` = allow) | `_nhom_duoc_phep` |
| `phien` | phiên | session; version (`phiên bản`); transcription (`phiên âm`) | `co_phien`, `phien_am` |
| `phong` | phòng | fallback, spare (`dự phòng`) | `MODELS_DU_PHONG` |
| `phu` | phụ, phủ | auxiliary, secondary; overlay | `la_phu_engine`, `lop_phu` |
| `phuc` | phục | restore, recover (`khôi phục`) | `sinh_ma_khoi_phuc` |
| `qua` | qua, quá, quả | via, past; too much; result (`kết quả`) | `qua_tran_argv`, `bo_qua` |
| `quan` | quan | take over (`tiếp quản`); observe (`quan sát`); overview (`tổng quan`) | `tiep_quan`, `usage_tong_quan` |
| `quet` | quét | scan | `_quet_md_hong` |
| `quy` | quy | workflow (`quy trình`); convention (`quy ước`) | `chayQuyTrinh` |
| `quyen` | quyền | permission, right | `MUC_QUYEN` |
| `quyet` | quyết | decision (`quyết định`) | `quyet_dinh_luot` |
| `ra` | ra | out, produce | `ra_file` |
| `rang` | ràng | binding, constraint (`ràng buộc`) | `xoa_rang_buoc` |
| `rieng` | riêng | own, private, dedicated | `_logoRieng` |
| `rong` | rỗng, rộng | empty; wide | `xoa_khi_rong`, `_nuaRong` |
| `sach` | sách, sạch | list (`danh sách`); budget (`ngân sách`); clean | `taiDanhSach`, `cay_sach` |
| `sau` | sau, sâu | after, next; deep | `cum_sau`, `do_sau` |
| `so` | số, so, sổ | number; compare; book, registry | `doc_so`, `_xoa_so` |
| `song` | song, sống | parallel (`song song`); alive | `_DIAL_SONG_SONG`, `nhom_con_song` |
| `su` | sử, sự | history (`lịch sử`); event (`sự kiện`); collaborator (`cộng sự`) | `_ghi_lich_su`, `_bao_su_kien` |
| `sua` | sửa | edit, fix | `da_sua` |
| `tach` | tách | split, separate | `tach_phien_ban` |
| `tai` | tải, tài, tại | load, download; account (`tài khoản`); document (`tài liệu`); at | `dangTai`, `tai_khoan` |
| `tam` | tạm | temporary | `_la_loi_tam_thoi` |
| `tat` | tắt, tất | turn off; all (`tất cả`); summary (`tóm tắt`) | `bot_tat`, `tom_tat` |
| `ten` | tên | name | `tenBrain` |
| `thang` | tháng, thẳng | month; straight, direct | `_THANG`, `DUOI_XEM_THANG` |
| `thanh` | thanh, thành | bar; become; member (`thành viên`) | `capNhatThanhGoi`, `_thanh_vien` |
| `that` | thật | real, actual | `co_that` |
| `thay` | thay, thấy | replace; see, find (`tìm thấy`) | `_link_file_khong_thay` |
| `them` | thêm | add, more | `taiThem` |
| `theo` | theo | following, according to, by | `theo_ngay` |
| `thich` | thích | explain (`giải thích`); caption (`chú thích`); compatible (`tương thích`) | `chu_thich_anh` |
| `thieu` | thiếu | missing; minimum (`tối thiểu`) | `_GIU_TOI_THIEU` |
| `tho` | thô | raw | `_doc_tho` |
| `thoai` | thoại | conversation (`hội thoại`); phone (`điện thoại`); voice message (`tin thoại`) | `tab_hoi_thoai` |
| `thoi` | thời | time (`thời gian`); temporary (`tạm thời`) | `thoi_luong` |
| `thong` | thông, thống | notification (`thông báo`); system (`hệ thống`); statistics (`thống kê`) | `la_thong_bao_ket_noi_lai` |
| `thu` | thư, thử, thứ | folder (`thư mục`), mail; try; order, weekday | `thu_muc_id`, `thu_lai_khi_tam_thoi` |
| `thuc` | thức, thực | end (`kết thúc`); authenticate (`xác thực`) | `header_xac_thuc` |
| `thue` | thuê | subscription (`thuê bao`) | `_rule_thue_bao` |
| `tien` | tiến, tiền | process (`tiến trình`); progress (`tiến độ`); money; prefix (`tiền tố`) | `tien_trinh_nen`, `tien_to` |
| `tiep` | tiếp | next, continue | `tu_lam_tiep` |
| `tiet` | tiết | detail (`chi tiết`); saving (`tiết kiệm`); syllable (`âm tiết`) | `_uoc_tinh_tiet_kiem` |
| `tieu` | tiêu | title (`tiêu đề`); goal (`mục tiêu`) | `tachMucTieu` |
| `tim` | tìm | find, search | `tim_binary` |
| `tin` | tin | message; trust | `_tinChoLuot` |
| `tinh` | tính, tĩnh | compute, estimate; static; identity (`danh tính`) | `uoc_tinh`, `_NenTinh` |
| `toi` | tối, tới, tôi | maximum (`tối đa`); to, next; I | `GOAL_TOI_DA`, `nhayToi` |
| `tom` | tóm | summary (`tóm tắt`) | `tomTatDoiTuong` |
| `tong` | tổng | total, sum | `tong_token` |
| `tra` | tra, trả | look up; return; reply (`trả lời`) | `_tra_tai_lieu`, `ngon_ngu_tra_loi` |
| `tran` | trần, tràn | ceiling, cap; overflow | `TRAN_BAO_KHUNG_GOC` |
| `trang` | trang, trạng | page; state (`trạng thái`) | `TRANG_THAI` |
| `trinh` | trình | process (`tiến trình`); workflow (`quy trình`); browser (`trình duyệt`) | `_khi_tien_trinh_xong` |
| `trong` | trong, trống | in, inside; empty | `trong_vault`, `docNhomTrong` |
| `truoc` | trước | before, previous | `nhoPhienTruoc` |
| `truong` | trường | field; environment (`môi trường`) | `_moi_truong` |
| `tu` | từ, tự | word; from; self, auto (`tự động`) | `demTu`, `chatbot_tu_dong`, `_tu_choi` |
| `tuan` | tuần | week | `bao_cao_tuan` |
| `tuy` | tuỳ | optional (`tuỳ chọn`) | `tuyChon` |
| `ung` | ứng | candidate (`ứng viên`); effect (`hiệu ứng`) | `_ung_vien_tai_nguyen` |
| `uoc` | ước | estimate (`ước tính`, `ước lượng`) | `uoc_luong` |
| `uu` | ưu | priority (`ưu tiên`) | `xep_theo_uu_tien` |
| `van` | văn, vấn | text (`văn bản`); issue (`vấn đề`) | `van_ban`, `tim_van_de` |
| `vao` | vào | into, enter; input (`đầu vào`) | `ghep_dau_vao` |
| `ve` | vẽ, về | draw, render; about, back | `veDanhSach`, `henVe` |
| `vet` | vết | trace (`dấu vết`) | `_dauVetTin` |
| `viec` | việc | job, task | `huy_viec_nen_giong` |
| `vien` | viên | member (`thành viên`); library (`thư viện`); candidate (`ứng viên`) | `thu_vien` |
| `vong` | vòng | loop, round | `_het_vong_msg` |
| `xac` | xác | confirm (`xác nhận`); authenticate (`xác thực`) | `LOI_CHUA_XAC_NHAN` |
| `xem` | xem | view, look at | `DAI_XEM_TRUOC` |
| `xep` | xếp | sort, arrange | `sapXep` |
| `xoa` | xoá | delete | `can_xoa` |
| `xong` | xong | done, finished | `_KHI_XONG` |
| `xu` | xử | handle (`xử lý`); adjudicate (`phân xử`) | `_xoa_du_lieu_phan_xu` |

## Vietnamese file names

| File | Meaning |
|------|---------|
| `server/anh_codex.py` | Codex images (moves images Codex drew into the brain) |
| `server/chatbot_cuoc_chat.py` | chatbot conversations (the people and groups picker) |
| `server/chatbot_tu_dong.py` | chatbot auto mode (decides by itself when to speak in a group) |
| `server/lenh_he_thong.py` | system commands (`/` slash commands) |
| `server/luot_dang_chay.py` | turns currently running |
| `server/nghe_sua.py` | hear and fix (corrects misheard speech) |
| `server/phien_am.py`, `server/data_phien_am/` | phonetic transcription (English words read the Vietnamese way) |
| `server/tien_trinh_nen.py` | background processes |
| `dashboard/chat-lenh.js`, `dashboard/chat-viec.js` | chat commands; chat background-job cards |
| `docs/quy-uoc-dev.md` | developer conventions |
| `docs/dev/them-mot-ngon-ngu.md` | adding a language |
| `docs/dev/01-kien-truc.md` | architecture (older note) |

Test file names follow the same pattern: `test_lang_bat_bien.py` is "language invariants",
`test_tai_lieu_song_ngu.py` is "bilingual documents", `test_da_ngon_ngu.py` is
"multilingual".

## Dashboard i18n keys and prompt markers

Dictionary keys in `dashboard/i18n/*.json` are ASCII and often Vietnamese:
`nav.group.bo_nao` (Brain), `nav.group.nang_luc` (Capabilities), `nav.group.viec` (Work),
`nav.group.ket_noi` (Connections), `nav.group.he_thong` (System). Translate the values, never
the keys.

The system prompt is split by Vietnamese section markers that code searches for, so they must
not be translated (see [them-mot-ngon-ngu.md](them-mot-ngon-ngu.md)):

| Marker | Meaning |
|--------|---------|
| `# === BỘ NHỚ DÀI HẠN (nạp sẵn) ===` | long-term memory (preloaded) |
| `# === SKILL KHẢ DỤNG ... ===` | available skills |
| `# === LỚP AGENTIC (vault đang làm việc) ===` | agentic layer (the working vault) |
| `# === KÊNH HỘI THOẠI HIỆN TẠI ... ===` | current conversation channel |
| `# === BÂY GIỜ ===` | now (current date and time) |
| `# === NGÔN NGỮ ===` | language (which language to reply in) |
| `# === MỨC DÙNG HÔM NAY ... ===` | today's usage |
