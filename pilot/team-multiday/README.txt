GÓI PILOT: TEAM LÀM VIỆC NHIỀU NGÀY (0.207.0 tới 0.210.0)
TRẠNG THÁI: ĐÃ CHUẨN BỊ, CHƯA CHẠY. Không có kết quả pilot nào trong thư mục này.

Mục đích
  Chạy thử 3 nhóm trong 3 tới 7 ngày trên một bản Javis riêng để xem ba thứ có đứng vững với model thật không:
  1. Cổng chờ duyệt: bước cần chủ thì dừng thật, hành động ra ngoài chỉ chạy đúng lời gọi đã duyệt, một lần.
  2. Mục tiêu phòng ban: nhóm tự tìm việc trong nguồn được giao, đúng ngân sách, không bịa, có dấu vết.
  3. Nghiệm thu: việc chỉ xong khi sản phẩm đạt tiêu chí của chủ.

Các file
  README.txt              file này: tổng quan và thứ tự đọc
  run_guide.txt           các bước chạy, theo dõi hằng ngày, dừng khẩn và quay về bản cũ
  scenarios.txt           kịch bản 7 ngày cho 3 nhóm, việc chủ làm mỗi ngày
  limits.txt              provider và model, ngân sách, giới hạn, điều kiện dừng
  metrics.txt             chỉ số và cách đo (từ dữ liệu, không từ lời agent)
  report_template.txt     mẫu báo cáo để điền SAU khi chạy (đang trống)
  requirements_matrix.txt yêu cầu -> mã -> test -> bằng chứng
  config/teams.json       cấu hình 3 nhóm: thành viên, quyền, mục tiêu, tiêu chí nghiệm thu mẫu
  trace_export.py         xuất dấu vết mục tiêu -> cơ hội -> quyết định -> duyệt -> việc -> sản phẩm -> nghiệm thu (chỉ đọc)
  ui_narrow_check.mjs     kiểm thẻ duyệt, mục tiêu, nghiệm thu ở màn hẹp 390px bằng tiếng Việt và tiếng Anh

Bản được ghim
  Chạy đúng commit đầu của PR #728 tại thời điểm bắt đầu pilot. Ghi SHA đó vào report_template.txt trước khi bật.
  Lúc chuẩn bị gói này, đầu nhánh là commit có tiêu đề "0.210.0: ..." (xem git log của nhánh
  claude/openmausbot-jarvis-research-ewnzc6). Không chạy trên main cho tới khi PR được chủ duyệt.

Không làm trong goal này
  Không merge, không gọi model thật, không chạy pilot, không deploy, không đụng VPS.
