---
bump: minor
title: Scan drives, mapped drives and NAS for duplicate files
---
## vi
### Thêm mới
- **Javis quét được ổ đĩa, thư mục, ổ mạng map và NAS.** Hỏi kiểu "quét ổ E tìm file trùng" hay "ổ nào đang có trên máy", Javis liệt kê cả ổ mạng và đường dẫn NAS.
- **Tìm file trùng giống hệt, kể cả giữa máy và NAS.** So dung lượng, rồi phần đầu cuối, rồi toàn bộ nội dung, nên chỉ ra đúng file thật sự giống nhau và dung lượng đang bị chiếm thừa.
- **Báo cáo dung lượng theo loại file, thư mục nặng nhất, file lớn nhất**, lưu được vào thư mục exports của brain. Bản này chỉ đọc: Javis không di chuyển hay xoá file nào.

## en
### Added
- **Javis can scan drives, folders, mapped network drives and a NAS.** Ask "scan drive E for duplicate files" or "which drives are on this computer" and Javis lists network drives and NAS paths too.
- **Finds identical duplicate files, including between the computer and the NAS.** It compares size, then the start and end, then the whole content, so it names only files that truly match and the space they waste.
- **Reports space by file type, the heaviest folders and the biggest files**, and can save the report into the brain's exports folder. This version only reads: Javis never moves or deletes a file.
