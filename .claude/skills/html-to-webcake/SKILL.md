---
name: HTML sang Webcake
description: Chuyển trang HTML thành file .pke mở được trong trình dựng Webcake, giữ đúng màu, cỡ chữ, ảnh và bố cục của bản gốc.
name_en: "HTML to Webcake"
description_en: "Turn an HTML page into a .pke file the Webcake builder can open, keeping the original colours, type sizes, images and layout."
group: Marketing
---

# HTML sang Webcake (.pke)

## Khi nào dùng

Người dùng nói những câu như: "chuyển file html này sang webcake", "đổi html thành pke",
"tạo file webcake từ html", "làm landing này thành file sửa được trên webcake",
"html to webcake", "convert html sang webcake", "bài sales page vừa viết đưa lên webcake".

## Hiểu đúng bản chất trước khi làm

- File `.pke` = `base64( MessagePack( envelope ) )`, trong đó `envelope.source` chính là
  **page_source** của editor Webcake (`settings, popup, page, options, cartConfigs`).
- Webcake là **canvas định vị TUYỆT ĐỐI theo pixel**, mỗi phần tử ghi `top/left/width/height`
  RIÊNG cho 2 khổ: mobile rộng 420, desktop rộng 960. Không phải HTML trôi theo dòng.
- Vì vậy bố cục được **TÁI DỰNG** thành các section xếp dọc + hàng nhiều cột. Còn **màu, cỡ chữ,
  line-height, letter-spacing, ảnh, nội dung, thứ tự** thì lấy nguyên từ nguồn - bộ công cụ đọc
  cascade CSS thật chứ không nhìn bằng mắt. Nói rõ ranh giới này với người dùng.
- HTML do Webcake publish (bản đã xuất) không chứa source biên tập; vẫn đọc lại nội dung được.

## Công cụ (đi kèm skill, không cần cài gói)

Ở thư mục `tools/` cạnh file SKILL.md này. Chạy bằng `node`, không phụ thuộc npm.

- `webcake-from-html.js` - **HTML -> spec.json**. Đọc DOM + cascade CSS thật (biến `var(--x)`,
  `clamp()`, `@media`, class, inline style), suy ra section/heading/text/ảnh/nút/form/bảng giá/
  card/hàng nhiều cột, rồi in ra danh sách cảnh báo.
  `node tools/webcake-from-html.js trang.html spec.json [--name "Tên trang"]`
- `webcake-build.js` - **spec.json -> .pke**. Tự chạy lint sau khi build.
  `node tools/webcake-build.js spec.json out.pke [--check]` (`--check`: exit 1 nếu lint có lỗi)
- `webcake-lint.js` - soát layout (chồng nhau, tràn section, khoảng chết) **và tương phản chữ/nền**.
  `node tools/webcake-lint.js out.pke`
- `webcake-preview.js` - render page_source thành HTML tĩnh mô phỏng đúng canvas để SOI TRƯỚC.
  `node tools/webcake-preview.js out.pke previewBase [--debug]`
- `webcake-pke.js` - codec 2 chiều: `decode file.pke file.json` / `encode file.json file.pke`.
- `webcake-html.js` - thư viện đọc HTML/CSS dùng chung (không gọi trực tiếp).

Ví dụ spec chuẩn viết tay: `examples/salepage-16-buoc-spec.json`. Ví dụ HTML nguồn: `examples/sample.html`.

## Quy trình khi kích hoạt (BẮT BUỘC đủ 6 bước)

1. **Xác định HTML nguồn.** Người dùng đưa file `.html` hoặc dán HTML. Dán thì ghi ra file tạm trước.
2. **Chuyển tự động**: `node tools/webcake-from-html.js trang.html spec.json`.
   **ĐỌC KỸ mục "CẦN LƯU Ý"** nó in ra - đó là những thứ nó KHÔNG mang sang được (ảnh local,
   svg/canvas, hiệu ứng hover, CSS từ file ngoài). Đừng bỏ qua rồi giao file thiếu.
3. **Soát lại spec bằng mắt** rồi sửa tay những chỗ máy không đoán được: `ratio` của ảnh không khai
   kích thước, section nào nên gộp/tách, nút nào là CTA chính. Đây là bước cho "đẹp", không phải
   bước cho "giống" - phần giống máy đã làm xong.
4. **Build**: `node tools/webcake-build.js spec.json out.pke`.
5. **Lint phải 0 ERROR.** Còn lỗi chồng/tràn/chữ chìm vào nền thì sửa spec rồi build lại - KHÔNG
   giao file đang lỗi. Cảnh báo tương phản thấp cũng nên xử, đó là chữ khó đọc thật.
6. **Soi trước khi giao**: `node tools/webcake-preview.js out.pke preview` rồi mở
   `preview.desktop.html` + `preview.mobile.html`. Chụp được màn hình thì đặt cạnh trang gốc mà so:
   thứ tự section, màu nền từng dải, cỡ tiêu đề, vị trí ảnh. Lệch đâu sửa spec rồi lặp lại.
7. **Giao file**: đặt `out.pke` cạnh HTML gốc hoặc trong vault, nhúng link markdown cho user tải,
   báo cáo NGẮN: bao nhiêu section, đã QA những gì, nhắc "upload lên Webcake để sửa" + các giới hạn.

## Schema của spec.json

```json
{
  "name": "Tên trang", "title": "Tiêu đề SEO", "description": "Mô tả SEO",
  "font": "Montserrat", "favicon": "https://... (tùy chọn)",
  "extraScript": "JS chạy khi publish/preview (vd đếm ngược)",
  "extraCss": "CSS phụ trợ khi publish",
  "theme": {
    "colors": { "ink": "rgba(242,240,232,1)", "amber": "rgba(232,168,92,1)", "cta": "linear-gradient(...)" },
    "text":    { "color": "$soft", "size": 16 },
    "heading": { "color": "$ink" },
    "badge":   { "color": "$amber", "bg": "rgba(232,168,92,0.08)", "borderColor": "rgba(232,168,92,0.35)" },
    "card":    { "bg": "$cardBg", "borderColor": "$line", "radius": 16, "titleColor": "$ink", "textColor": "$soft" },
    "button":  { "bg": "$cta", "color": "$bg0", "radius": 99, "size": 17 },
    "textMaxWidth": 700, "headingMaxWidth": 800, "cardMaxWidth": 800
  },
  "sections": [ { "name": "hero", "background": "$bg0 hoặc chuỗi CSS gradient", "padTop": 56, "gap": 18, "padBottom": 56,
    "elements": [ ] } ]
}
```

**Token màu**: `"$ten"` (nguyên chuỗi) hoặc `${ten}` (nhúng trong html dài) -> tự thay bằng `theme.colors.ten`. Tên không tồn tại thì giữ nguyên chuỗi (an toàn với chuỗi kiểu "$50").
Mỗi mục `theme.text/heading/badge/card/button/testimonial/priceTable/guarantee/progress/divider/ctaBlock` là **default cho kind tương ứng** - element chỉ ghi field khác default.

### Element LÁ

| kind | field chính | ghi chú |
|---|---|---|
| `heading` | `text` (HTML inline OK), `size`, `tag` h1/h2/h3, `align`, `kicker`, `lineHeight`, `letterSpacing` | `kicker: "01"` tự sinh pill nhỏ phía trên |
| `text` | `html`, `size`, `color`, `align`, `maxWidth`, `lineHeight`, `letterSpacing` | mặc định tự bó về `textMaxWidth` (~700) và căn giữa khối |
| `image` | `src`, `ratio` (w/h), `width` 0..1, `widthMobile`, `radius`, `boxShadow` | |
| `button` | `text`, `href` hoặc `scrollTo`, `width`, `bg`, `color`, `radius`, `boxShadow`, `animation` | glow tự suy từ màu bg; text dài tự tăng height |
| `badge` | `text`, `align`, `bg`, `color`, `borderColor`, `padX`, `padY` | text dài tự HẠ cỡ chữ; vẫn dài nữa thì tự wrap và pill cao lên |
| `card` | `icon`, `iconTop`, `title`, `text`, `accent`, `pad`, `align`, `maxWidth` | hộp nền bo góc + tiêu đề + mô tả |
| `divider` | `width` 0..1, `color`, `thickness` | đường kẻ mảnh căn giữa |
| `progress` | `value` 0..1, `width`, `label`, `fillColor`, `trackColor`, `glow` | thanh tiến trình |
| `priceTable` | `title`, `rows: [{label, price}]`, `total`, `strike`, `today` | bảng giá trị, hàng tổng, dòng gạch giá |
| `testimonial` | `quote`, `author`, `stars` 1..5 | tự bọc card |
| `guarantee` | `icon`, `title`, `text` | icon lớn bên trái, nội dung bên phải |
| `ctaBlock` | `text`, `href`, `sub`, `arrow` + mọi field button | mũi tên + nút + dòng phụ thành 1 khối |
| `spacer` | `height` | |
| `window` | `title`, `lines: [{who: "you\|bot", text}]` | khung cửa sổ chat |
| `form` | `fields`, `submitText`, `submitBg`, `redirect` | input + nút gửi |

Mọi kind còn nhận `customCss` (khai báo CSS thuần cho riêng element đó, đi qua `specials.custom_css`
của Webcake). Chỉ dùng cho thứ TRÔNG THẤY: gradient, bóng, bo, filter, transition. **Cấm** đặt
`position/top/left/width/height/display/flex/grid` ở đây - engine sẽ ném lỗi, vì chúng đè lên hộp
tuyệt đối của canvas và làm vỡ bố cục.

### Element BỐ CỤC (chống trang 1 cột đơn điệu)

- `row` `{ "gap": 44, "valign": "center", "cols": [ {"w": 0.55, "items": []}, {"w": 0.45, "items": []} ] }` - desktop xếp cột cạnh nhau, mobile tự xếp dọc.
- `hero` `{ "side": "right|left", "mediaW": 0.4, "media": {element ảnh/window}, "items": [] }` - đường tắt "chữ 1 bên, hình 1 bên".
- `cardsRow` `{ "gap": 18, "cards": [ {icon,title,text} ] }` - 1 hàng card đều nhau.
- `testimonialRow` `{ "items": [ {quote,author} ] }` - hàng testimonial ngang.
- `iconRow` `{ "items": [ {icon, text} ] }` - hàng icon + chú thích ngắn.

## Design pass (checklist thẩm mỹ - chấm TRƯỚC khi giao)

1. **Nhịp nền**: luân phiên nền section đậm / nhạt; tối đa 1 radial-gradient nhấn cho hero + 1 cho khối giá.
2. **>= 3 pattern bố cục** mỗi trang (hero 2 cột, cardsRow, priceTable, testimonial...). Cấm 100% một cột.
3. **Khổ chữ đọc được**: đoạn văn <= ~90 ký tự/dòng (`textMaxWidth` lo việc này).
4. **Heading scale nhất quán**: vd h1 42 / h2 31 / h3 19 desktop (mobile tự nhân ~0.84).
5. **Spacing bội số 8** cho padTop/padBottom/gap; đừng cắt vụn mỗi dòng một section.
6. **CTA lặp 2-3 lần**, cùng màu cùng radius; nút chính nổi bật nhất trang.
7. **Lint 0 ERROR + preview 2 khổ**: không chồng chữ, không hụt nền, không chữ chìm vào nền.

## Nguyên tắc chuyển đổi

- **Chữ nhấn mạnh**: thẻ inline trong html - `<span style='font-weight:700;color:${ink};'>...</span>`,
  gạch giá `<span style='text-decoration:line-through;'>...</span>`. Xuống dòng `<br>`, KHÔNG lồng `<p>`.
- **Chữ tô gradient**: `<span style='background:linear-gradient(...);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;'>`.
  Đây là HTML nằm TRONG `specials.text` nên chạy bình thường; khác hẳn `styles.background` của cả text-block.
- **Màu**: dạng `rgba(r,g,b,a)` hoặc token `$ten`. Nút nổi bật dùng gradient.
- **Ảnh**: Webcake tải theo URL public. Ảnh local/base64 -> CẢNH BÁO user cần upload rồi thay `src`,
  không thì ảnh sẽ trống (lint cũng bắt lỗi này).
- **Đo chữ**: engine dùng bảng độ rộng TỪNG ký tự Montserrat đo thật từ Chromium (chuẩn cả tiếng Việt,
  CHỮ HOA, emoji, số), có tính `line-height`/`letter-spacing`/span đổi cỡ chữ, cộng biên an toàn 1.5%.
  Font khác Montserrat sẽ kém chính xác hơn - cứ chạy preview để soi.
- **Script/CSS động**: `extraScript` / `extraCss` map vào Cài đặt > HTML/JavaScript của Webcake;
  CHỈ chạy khi Xem trước / Xuất bản, KHÔNG chạy trong editor - dặn user bấm Preview mới thấy.
- **KHÔNG dùng ký tự em dash** ở bất cứ đâu (text, spec, báo cáo) - dùng "-".

## Cách nâng cao (tự dựng page_source rồi encode)

Cần kiểm soát sâu (group lồng nhau, popup, radio/checkbox sản phẩm) thì tự dựng nguyên object `source`
(`{settings, popup, page, options, cartConfigs}`) đúng schema node Webcake, ghi ra JSON rồi:
`node tools/webcake-pke.js encode source.json out.pke` (thêm `--name` `--owner` nếu cần).

Có kết nối **Webcake Landing MCP** thì còn đường thứ hai: dựng thẳng trang trên tài khoản qua
`create_page` / `add_section` / `validate_page`. Đường `.pke` này dành cho lúc chưa đấu MCP,
hoặc khi user muốn một file để tự upload.

## Giới hạn cần nói thẳng với người dùng

Bố cục được tái dựng theo lưới dọc + hàng nhiều cột, không sao chép y hệt vị trí pixel của HTML gốc.
Hiệu ứng nền động (canvas, orb blur, svg) không mang sang editor được. Hiệu ứng `:hover` phải thêm lại
tay trong Cài đặt > CSS. Radio/checkbox chọn sản phẩm (gắn `product_id`/`variation` của Pancake)
không tự sinh được - user thêm trong Webcake sau khi upload.
Khuyến khích upload thử file `.pke` trước, lệch đâu chỉnh spec rồi build lại.
