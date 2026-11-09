---
bump: minor
title: Paper trading on the Markets page with three virtual accounts, entry timing, full order log and historical simulation
---
## vi
### Thêm mới
- **Tab Đầu tư ảo** trên trang Thị trường: ba tài khoản tự giao dịch bằng giá thật (chứng khoán VN 1 tỷ đồng, tiền số 20.000 USD, chứng khoán thế giới 20.000 USD), tính đủ phí, thuế, lô 100 và T+2.
- **Chọn điểm mua cho từng mã**: không mua đuổi giá chạy xa, không mua khi mã đang giảm; mã đạt tiêu chí nhưng chưa tới vùng giá được đưa vào danh sách **Chờ điểm mua**. Mỗi lệnh có cắt lỗ, cắt lỗ đuổi giữ lãi và chốt một nửa.
- **Báo cáo đầy đủ**: giá trị danh mục so với chỉ số chuẩn, lãi lỗ, tỷ lệ thắng, sụt giảm tối đa, vị thế, nhật ký lệnh kèm phân tích trước khi mua bán, và nhật ký từng lần ra quyết định.
- **Mô phỏng 120 hoặc 250 phiên** để xem bộ quy tắc từng chạy ra sao trước khi tin nó. Đây là giao dịch ảo, không bảo đảm lợi nhuận.

## en
### Added
- **Paper trading tab** on the Markets page: three accounts trade by themselves on real prices (Vietnam stocks 1 billion VND, crypto 20,000 USD, world stocks 20,000 USD), with fees, taxes, lots of 100 and T+2.
- **Entry timing per symbol**: no chasing extended prices and no buying a falling day; symbols that qualify but are out of their price zone wait on a **watch list**. Every position has a stop, a trailing stop that keeps gains and a half take-profit.
- **Full report**: account value against the benchmark, P&L, win rate, max drawdown, positions, an order log with the analysis behind each trade, and a log of every decision run.
- **120 or 250-session simulation** to see how the rules would have done before trusting them. Simulated trades only; no profit is guaranteed.
