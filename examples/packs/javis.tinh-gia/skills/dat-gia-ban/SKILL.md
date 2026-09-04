---
name: Đặt giá bán
description: Đặt giá bán từ giá vốn - phân biệt biên lợi nhuận với markup, cộng VAT, làm tròn số đẹp. Dùng kèm tool javis_tinh_gia_ban.
description_en: "Set a selling price from cost: margin versus markup, VAT, tidy rounding. Pairs with the javis_tinh_gia_ban tool."
group: Bán hàng
---

# Đặt giá bán

## Khi nào dùng

Khi người dùng hỏi "bán cái này bao nhiêu", "lãi 30% thì để giá nào", "nhập 120k thì bán
bao nhiêu", hoặc đưa một bảng giá vốn và muốn ra giá niêm yết.

## Chỗ sai hay gặp nhất

**Biên lợi nhuận và markup không phải một thứ.** Biên tính trên giá BÁN, markup tính trên
giá VỐN. Nhập 120.000 mà "lãi 30%" hiểu theo hai lối sẽ ra hai giá khác nhau:

- Biên 30 phần trăm: giá bán 171.429, lãi 51.429
- Markup 30 phần trăm: giá bán 156.000, lãi 36.000

Chênh nhau hơn mười lăm nghìn một đơn vị. Khi người dùng chỉ nói "lãi 30%" mà không nói rõ
tính trên đâu, **hỏi lại một câu** rồi mới tính, đừng đoán.

Dấu hiệu họ đang nghĩ theo markup: nói "cộng 30% lên", "nhân 1.3", "gấp rưỡi". Dấu hiệu
nghĩ theo biên: nói "lãi gộp", "margin", "30% doanh thu".

## Cách làm

Gọi `javis_tinh_gia_ban` với `gia_von`, rồi một trong hai: `bien_loi_nhuan` hoặc
`ty_le_markup`. Thêm `vat` nếu giá niêm yết đã gồm thuế, và `lam_tron` theo bội số mà cửa
hàng hay dùng (1.000 cho hàng lẻ, 10.000 cho hàng giá trị cao).

Tool làm tròn ở giá CUỐI CÙNG, tức số trên tem, nên biên thực tế xê dịch một chút so với
con số vừa đặt ra. Nó trả về `bien_loi_nhuan_thuc` - **báo lại số này**, không báo lại con
số người dùng vừa nhập vào.

## Nói lại kết quả thế nào

Một câu là đủ: giá niêm yết, lãi một đơn vị, biên thực. Chỉ bung bảng khi người dùng đưa
nhiều mặt hàng cùng lúc.

Nếu giá tính ra trông vô lý (dưới giá vốn, hoặc cao gấp nhiều lần mặt bằng), nói ra điều
đó trước khi đưa số, chứ đừng đọc số ra rồi thôi.
