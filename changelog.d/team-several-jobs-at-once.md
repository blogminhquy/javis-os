---
bump: minor
title: A team runs up to three jobs at once when they belong to different assistants
---
## vi
### Thêm mới
- **Một team chạy được nhiều việc cùng lúc.** Trước đây mỗi team chỉ chạy một việc tại một thời điểm, nên việc của cộng sự này phải chờ việc của cộng sự kia xong. Giờ tối đa 3 việc chạy song song khi chúng thuộc các cộng sự khác nhau.
- **Việc của cùng một cộng sự vẫn chạy lần lượt** theo đúng thứ tự trong hàng chờ. Các việc do người điều phối lên kế hoạch cũng vậy.
- **Muốn việc sau chờ kết quả việc trước thì nói rõ trong yêu cầu.** Việc có câu như "sau khi ... xong", "lần lượt" hay "theo thứ tự" sẽ chờ mọi việc đứng trước nó xong rồi mới chạy, và không việc nào phía sau chen lên trước.
### Cải thiện
- **Dải việc đầu khung chat hiện đủ các việc đang chạy**, không chỉ một việc.
- Cần quay về kiểu từng việc một thì đặt biến môi trường `JAVIS_TEAM_JOBS=1`.

## en
### Added
- **One team can run several jobs at once.** A team used to run one job at a time, so one assistant's job waited for another assistant's job to end. Now up to 3 jobs run side by side when they belong to different assistants.
- **Jobs of the same assistant still run one after the other**, in the order of the queue. So do the jobs the coordinator plans.
- **To make a job wait for an earlier result, say so in the request.** A job with words such as "after ... is done", "one after another" or "in sequence" waits for every job before it, and no later job starts ahead of it.
### Improved
- **The job strip on top of the chat shows every running job**, not only one.
- To go back to one job at a time, set the environment variable `JAVIS_TEAM_JOBS=1`.
