# Javis Resonance thiết kế và lộ trình thực thi mục tiêu

Ngày 06 tháng 10 năm 2026. Bản thiết kế để triển khai theo giai đoạn.

**Bản hiện hành:** xem [danh mục tài liệu chốt](../README-RESONANCE.md). Trước M1 phải kiểm main mới nhất, chốt commit nền và dò lại các tham chiếu mã ở mục 14; khảo sát trên checkout cũ không thay thế kiểm chứng tích hợp.

**Phạm vi ưu tiên sau phản biện vòng 2:** triển khai [MVP một agent](../plans/2026-10-06-resonance-00-mvp.md) trước. Tài liệu này mô tả kiến trúc đích; các thành phần mở rộng không phải danh sách phải xây ngay. Ba kế hoạch Foundation/Runtime/Evolution là tài liệu tham chiếu cho giai đoạn sau, không thực hiện song song với MVP.

Javis Resonance giúp một agent, một nhóm hoặc toàn bộ hệ thống nhận nhu cầu bằng ngôn ngữ tự nhiên, tự hình thành mục tiêu phù hợp, tự chọn phương pháp, thu thập bằng chứng và cải thiện cả cách hiểu lẫn cách làm trong phạm vi người dùng đã ủy quyền. Người dùng không phải biết cách đặt mục tiêu hoặc chọn chỉ số. Lõi dùng chung cho mọi lĩnh vực; tri thức chuyên môn nằm trong công cụ, bộ thu thập bằng chứng và bộ đánh giá có thể thay thế.

**Quyết định trung tâm:** nhu cầu người dùng định hướng; agent hình thành mục tiêu như một giả thuyết có thể điều chỉnh; bằng chứng xác định tiến triển; sự ủy quyền xác định phạm vi. Agent chịu trách nhiệm tìm đúng đích và tìm cách đạt đích. Beat là thời điểm hoạt động tiếp theo có ích. Reaction không quyết định hiệu suất, quyền hạn hoặc mức tồn tại của agent.

## 1 Những quyết định giữ lại và cải tiến

| Nội dung | Quyết định cuối cùng | Lý do |
|---|---|---|
| Mục tiêu tối thượng | Mỗi lần thực thi có một mục tiêu chính, gắn với ý định và điều kiện thành công | Tập trung nhưng vẫn cho một agent phục vụ nhiều mục tiêu ở các phiên khác nhau |
| Hình thành mục tiêu | Agent tự suy ra từ yêu cầu, ngữ cảnh được phép đọc và bằng chứng; người dùng có thể sửa cách hiểu | Không yêu cầu người dùng chọn mục tiêu hay biết trước giải pháp |
| Yêu cầu mơ hồ | Hỏi khi câu trả lời có thể đổi quyết định đáng kể; nếu người dùng chưa biết, tự khảo sát hoặc thử nhỏ trong quyền | Sự chưa rõ trở thành công việc cần giải quyết |
| Agent và nhóm | Dùng cùng hợp đồng mục tiêu; nhóm phân rã thành mục tiêu con | Mở rộng theo cùng cấu trúc |
| Quyền tự chủ | Được tự lập kế hoạch, cộng tác và sửa mình trong sự ủy quyền có hiệu lực | Không yêu cầu duyệt lại từng hành động đã được cấp quyền |
| Đánh giá | Dựa trên kết quả và bằng chứng, có trạng thái chưa đủ thông tin | Không biến thiếu dữ liệu thành thất bại hay thành công |
| Beat | Theo sự kiện, khả năng hành động và thời điểm có bằng chứng mới | Không thưởng bằng cách buộc agent chạy nhiều hơn |
| Phản hồi người dùng | Chỉ dẫn cập nhật ý định; nút Đúng ý/Hiểu chưa đúng cung cấp bằng chứng về cách hiểu; xác nhận kết quả gắn sản phẩm; emoji chung phục vụ giao tiếp | Tách người dùng xác nhận điều gì, tránh dùng một lượt bấm cho mọi kết luận |
| Tự cải thiện | Tạo biến thể, thử có đối chứng, kiểm chứng rồi áp dụng | Tự thay đổi phải chứng minh được cải thiện |
| Điểm utility duy nhất | Không dùng làm bộ điều khiển toàn hệ thống | Năng lực, tiến độ, nhu cầu hoạt động và sở thích giao tiếp là thông tin khác nhau |
| Quy công | Lưu đóng góp và mức chắc chắn, không mặc định leader nhận nhiều nhất | Lineage không tự chứng minh quan hệ nhân quả |
| Ngủ đông | Dừng thức theo giờ khi không còn lý do hoạt động, giữ trạng thái và khả năng nhận sự kiện | Không cần thời hạn 90 ngày chung cho mọi nhiệm vụ |
| Tạo sản phẩm đầu ra | Được ghi nhận là hành động; chỉ thành kết quả đạt khi tiêu chí xác nhận | Chống nhầm hoạt động với hiệu quả |
| Mở rộng ngành nghề | Thêm adapter có giao diện chung | Không viết điều kiện theo lĩnh vực trong lõi |

Các lựa chọn triển khai dưới đây là chính sách có phiên bản hoặc cấu hình của hợp đồng. Chỉ ba bất biến ở mục 2 là luật nền. Không biến một con số thử nghiệm thành nguyên lý cố định.

## 2 Ba bất biến

### 2.1 Sự ủy quyền được kế thừa và không tự mở rộng

Người dùng diễn đạt nhu cầu ở mức họ có thể, cùng những ràng buộc hoặc quyền đã cấp. Agent tự suy ra mục tiêu, tiêu chí và phương pháp từ đầu vào ấy; không bắt người dùng xác định đủ trước khi giúp. Agent con chỉ nhận một phần quyền và tài nguyên của cha. Tổng phân bổ đang sử dụng và đã tiêu không vượt phần gốc được cấp. Điểm hiệu suất không tự sinh thêm quyền.

Hình thành và điều chỉnh mục tiêu suy ra là trách nhiệm mặc định của agent khi xử lý yêu cầu, không phải một quyền cần người dùng bật riêng. Agent được sửa giả thuyết về đích đến, tiêu chí suy ra và phương pháp theo bằng chứng, có ghi phiên bản và lý do. Chỉ dẫn rõ và ràng buộc người dùng đã nêu vẫn có hiệu lực; agent không tự bỏ chúng hoặc mở rộng quyền, phạm vi và ngân sách. Khi đầu vào có mâu thuẫn hoặc đích yêu cầu không khả thi, agent giải thích và tìm bước tiến có ích trong phạm vi còn hợp lệ; chỉ người dùng có thể sửa ràng buộc do chính họ đặt.

### 2.2 Thành công phải có bằng chứng theo tiêu chí đã xác lập

Mỗi kết luận gắn với phiên bản hợp đồng, bộ đánh giá và tập bằng chứng. Agent không tự sửa dữ liệu gốc, kết quả phép thử hoặc thước đo của chính phép thử để tuyên bố thắng. Nhận xét của agent khác có nguồn gốc rõ nhưng không tự trở thành sự thật.

Hệ thống chấp nhận kết luận chưa biết. Thay đổi tiêu chí tạo phiên bản mới, không viết lại lịch sử. Phiên bản bị thay ghi superseded cùng kết quả thực tế đã có, không tự biến thành thành công hoặc xóa thất bại. Tiêu chí phép thử đang chạy được giữ cố định; việc tìm mục tiêu phù hợp hơn là một kết luận riêng với việc làm tốt hơn trên cùng mục tiêu. Mục tiêu con hoàn thành không tự làm mục tiêu cha thành công; kết quả cuối vẫn phải được đánh giá theo hợp đồng cha.

### 2.3 Quyền can thiệp của người dùng và lịch sử luôn có hiệu lực

Người dùng có thể dừng, đổi hướng hoặc thu hồi quyền. Mọi phiên bản agent chịu các thao tác này. Lưu được quyết định, tác động, bằng chứng, thay đổi và lý do. Khôi phục phần mềm không được mô tả là đã hoàn tác những tác động bên ngoài chưa được đảo ngược.

Với chế độ sửa code Javis, bộ phận thực thi quyền, giữ bằng chứng và dừng worker phải có ranh giới quyền truy cập thực sự. File nằm ngoài repo nhưng cùng tài khoản có toàn quyền ghi không tạo ra ranh giới đó.

## 3 Mục tiêu và tiêu chí thành công của sản phẩm

Người dùng mô tả điều họ muốn, vấn đề đang gặp hoặc điều chưa hài lòng bằng ngôn ngữ tự nhiên. Agent tự hình thành mục tiêu, cho thấy cách mình đang hiểu và tiến hành phần việc có thể làm trong quyền hiện có. Không có bước bắt buộc chọn mục tiêu, điền chỉ số hoặc duyệt bản hợp đồng trước mỗi lần bắt đầu. Hệ thống xử lý được cả kết quả định lượng, sản phẩm cần hoàn thành và tiêu chí chất lượng.

Thành công của Resonance được đánh giá bằng các nhiệm vụ đại diện có đối chứng: mục tiêu có bám sát đầu vào và ràng buộc hay không, tỷ lệ đạt tiêu chí, công người dùng phải bỏ ra để sửa/điều phối, thời gian hoàn thành, mức gây phiền và chi phí thực. Đo riêng chất lượng hình thành mục tiêu và hiệu quả thực thi. Không dùng số tin nhắn, số agent, số tool call hoặc số reaction làm thước đo thành công chính.

Không hứa hẹn tự cải thiện vô hạn. Mỗi tuyên bố cải thiện chỉ có giá trị trong phạm vi mục tiêu, dữ liệu và phép thử đã thực hiện.

## 4 Hợp đồng mục tiêu

### 4.0 Khi nào cần một mục tiêu được lưu và theo đuổi

Đầu tiên tận dụng bộ định tuyến hội thoại hiện có để chọn answer_now, task_now, continue_goal hoặc create_goal. Câu hỏi, tư vấn, lập kế hoạch và việc có thể hoàn tất trong lượt hiện tại dùng đường trả lời/làm ngay, không tạo goal bền, lịch hoặc Kanban chỉ vì cần nhiều bước suy nghĩ. Câu trả lời cho một mục tiêu đang mở nối vào đúng mục tiêu đó, không tạo bản trùng.

Chỉ tạo goal bền khi yêu cầu thực sự cần tiếp tục sau lượt chat, theo dõi kết quả về sau, chờ sự kiện hoặc giữ trạng thái để thực hiện công việc đã được giao. “Làm cho xong” là tín hiệu ý định hoàn thành, không phải từ khóa luôn tạo background job. Một việc hẹn giờ đơn giản tiếp tục dùng reminder hiện có. Nếu chưa rõ có cần chạy nền, làm phần có thể hoàn thành ngay; không suy quyền hoạt động dài hạn từ câu hỏi mơ hồ.

Quyết định này dùng ngữ cảnh và kết quả định tuyến của lượt đang có, không gọi thêm một model cho mọi tin nhắn. Chỉ gọi Goal framer khi thật sự cần tạo/điều chỉnh mục tiêu. Cổng này là chính sách phân luồng, không phải bước yêu cầu người dùng chọn mục tiêu.

### 4.1 Các trường chung

| Trường | Nội dung |
|---|---|
| identity | goal_id, brain_id, revision, owner_id, tên dễ đọc |
| intent_ref | Bản ghi nhu cầu và chỉ dẫn gốc có nguồn, phiên bản; tách khỏi phần agent suy ra |
| intent | Cách agent hiện diễn giải kết quả cần tạo và lý do |
| framing | Stage discovery/delivery, giả thuyết mục tiêu, giả định, căn cứ, điều chưa biết, mâu thuẫn chưa giải quyết, lý do chọn và điều kiện xem lại |
| owner | Agent hoặc nhóm chịu trách nhiệm, độc lập với người có thẩm quyền |
| mode | achieve để hoàn thành một mục tiêu, maintain để duy trì một điều kiện |
| success | Danh sách CriterionSpec, cách kết hợp all hoặc any, điều kiện kết thúc |
| evidence | Nguồn được dùng, độ mới cần thiết, cách nhận diện tài nguyên và phiên bản |
| evaluation | Bộ đánh giá và phiên bản; lịch/cửa sổ kiểm tra; chính sách khi thiếu dữ liệu |
| authority | Grant tham chiếu quyền thực hiện, tài nguyên, quyền phân công và quyền sửa mình |
| resources | Hạn mức, đơn vị đo, cách giữ chỗ trước khi chạy, cách đối soát chi phí |
| stop | Điều kiện dừng, phạm vi ảnh hưởng, người nhận thông báo, cách tiếp tục |
| timing | Deadline hoặc lý do không có deadline, các sự kiện cần nghe, chính sách thời gian |
| relations | parent_goal_id, dependencies, vai trò đóng góp vào mục tiêu cha |
| communication | Kênh báo, sự kiện cần báo, yêu cầu báo cáo định kỳ nếu có |

CriterionSpec gồm id, mô tả, evaluator_ref, evaluator_revision, parameters, evidence_selector và acceptance. Parameters thuộc bộ đánh giá; lõi không cần hiểu đó là số, văn bản, trạng thái hay cấu trúc tài liệu.

Điều kiện dừng dùng cùng giao diện đánh giá nhưng được kiểm tra độc lập với điều kiện thành công. Dừng có thể áp dụng cho một hành động, mục tiêu và hậu duệ, một nhóm, hoặc toàn bộ tầng tự chủ. Phạm vi toàn cục cần quyền tương ứng.

### 4.2 Tạo và thay đổi hợp đồng

1. Lưu yêu cầu gốc, nguồn và ràng buộc đã nêu vào IntentRecord. Người dùng bổ sung hoặc sửa chỉ dẫn tạo bản ghi mới liên kết bản trước; agent không viết lại lời người dùng.
2. Goal framer đọc ngữ cảnh được phép, phân biệt nhu cầu, giải pháp người dùng gợi ý, điều kiện bắt buộc và giả định. Khi chỉ có một cách hiểu đủ rõ thì dùng ngay; chỉ tạo vài giả thuyết khi có khác biệt đáng kể, không mở cây tìm kiếm vô hạn.
3. Chọn mục tiêu làm việc phù hợp nhất với bằng chứng hiện có: bám nhu cầu và ràng buộc, tạo lợi ích có thể quan sát, khả thi trong nguồn lực, tránh cam kết lớn khi còn mơ hồ. Không dùng sự tự tin của model làm bằng chứng rằng đã hiểu đúng.
4. Tự đề xuất tiêu chí và nguồn kiểm chứng. Nếu chưa đủ căn cứ xác định đích cuối, chọn một bước khám phá hữu ích như xem hiện trạng, tạo mẫu hoặc thử nhỏ, đồng thời ghi rõ kết quả người dùng vẫn chưa được xác định/đạt. Không biến hoàn thành khảo sát thành đã giải quyết nhu cầu gốc.
5. Hỏi ngắn khi câu trả lời có thể đổi quyết định đáng kể và không thể suy ra từ ngữ cảnh. Nếu người dùng nói chưa biết, agent tiếp tục bằng khảo sát hoặc thử nhỏ có thể đảo ngược trong quyền; không yêu cầu họ tự nghĩ ra mục tiêu. Không trả lời không được hiểu là cấp thêm quyền.
6. Tự kích hoạt phần việc hợp lệ từ yêu cầu đã giao, thông báo ngắn cách đang hiểu khi hữu ích. Việc đặt mục tiêu không có cổng duyệt riêng; lời hỏi làm rõ tùy chọn không khóa các bước độc lập. Chỉ chờ phần phụ thuộc khi thiếu thông tin không thể thay thế hoặc quyền thực sự cần thiết.
7. Xem lại giả thuyết khi có dữ liệu trái với giả định, người dùng sửa ý, kết quả không giúp giải quyết nhu cầu, hoặc bước khám phá tạo hiểu biết mới. Không đổi chỉ để dễ đạt hay vì tới một nhịp timer. Mỗi lần sửa lưu revision, diff, căn cứ và liên kết IntentRecord; run, evidence, assessment đang chạy vẫn mang revision đã ghim.
8. Ngừng cấp hành động theo revision cũ; đối soát tác động đã gửi và chuyển tiếp tại checkpoint phù hợp. Run cũ không tự đóng phiên bản mới. Ngân sách đã tiêu, guard đang kích hoạt, pause và quyền bị thu hồi vẫn còn hiệu lực sau đổi mục tiêu.

V1 hỗ trợ một parent sở hữu mỗi mục tiêu, dependencies là đồ thị không chu trình. Hợp tác chéo mục tiêu dùng liên kết đóng góp, không tạo hai chủ sở hữu ngân sách cho cùng một run. Mục tiêu gốc đóng vai trò cấp tổ chức; không cần một loại đối tượng công ty riêng.

### 4.3 Mục tiêu đạt và mục tiêu duy trì

Achieve chuyển sang succeeded khi tiêu chí đã được xác nhận và không có mâu thuẫn chưa giải quyết với nhu cầu/ràng buộc đã biết. Nếu mục tiêu gốc còn ở stage discovery để tìm hiểu đích cuối, đạt tiêu chí khám phá chuyển sang xem lại mục tiêu, chưa đóng nhu cầu gốc. Mục tiêu con khám phá có thể hoàn thành riêng. Một yêu cầu chỉ nhằm nghiên cứu hoặc khảo sát có thể thuộc delivery vì chính kết quả nghiên cứu là điều người dùng yêu cầu. Nếu muốn theo dõi sau hoàn thành, tạo mục tiêu maintain đã được ủy quyền, hoặc thực hiện chính sách tiếp nối đã ghi trong hợp đồng. Không tự tăng chỉ tiêu sau khi thắng.

Maintain ở trạng thái active, ghi healthy/degraded/unknown qua assessment và tiếp tục quan sát tới khi bị kết thúc. Không đóng vĩnh viễn ngay lần đầu điều kiện đạt.

### 4.4 Làm rõ và khám phá có giới hạn

Agent chịu trách nhiệm lựa chọn bước tiếp theo; người dùng không phải chọn giữa một danh sách mục tiêu. Khi cần hỏi, ưu tiên điều gần trải nghiệm của họ, ví dụ điều gì đang gây khó khăn hoặc kết quả nào có ích, thay vì yêu cầu đặt KPI. Agent có thể đưa ví dụ để giúp hiểu, nhưng không biến việc chọn ví dụ thành điều kiện mặc định để làm việc.

Nếu người dùng chưa rõ, ghi giả định có thể kiểm tra và làm bước ít tốn kém, dễ sửa, có khả năng phân biệt các cách hiểu. Tài nguyên khám phá dùng chung hạn mức của yêu cầu; giới hạn câu hỏi, thời gian và thử nghiệm là chính sách cấu hình theo bối cảnh. Không hỏi lại cùng một điều đã được trả lời là chưa biết khi chưa có thông tin mới.

Nếu không có hành động hợp lệ giúp giảm bất định, trả phần kết quả đã có, nêu đúng điều còn thiếu và chờ sự kiện có ích. Không gọi model hoặc đổi mục tiêu liên tục chỉ để tỏ ra chủ động. Với yêu cầu có ràng buộc mâu thuẫn, giữ các ràng buộc và làm phần tương thích; sự bất định về mong muốn khác với thiếu quyền thực hiện.

Ví dụ: người dùng nói “giúp anh làm việc đỡ rối”. Agent xem ngữ cảnh công việc đã được cấp quyền, chọn giả thuyết về điểm gây rối và tạo một cách sắp xếp thử có thể sửa. Nếu người dùng cũng chưa biết mình cần gì, mẫu thử tạo cơ sở để quan sát và điều chỉnh. Agent không tự coi nhu cầu này là quyền xóa công việc, gửi tin thay người dùng hoặc tối ưu số việc hoàn thành bất kể chất lượng.

### 4.5 Tách chất lượng mục tiêu khỏi kết quả thực thi

Đánh giá hai câu riêng: “mục tiêu có phù hợp với nhu cầu và ràng buộc đã biết không?” và “kết quả có đạt tiêu chí của mục tiêu đó không?”. Việc vế thứ hai đạt không chứng minh vế thứ nhất đúng. Khi thông tin chưa đủ, mức phù hợp vẫn là giả thuyết, không gắn nhãn đã hiểu trọn ý người dùng.

Không có một hàm lợi ích chung xác định điều tốt nhất cho mọi người. Chính sách mặc định ưu tiên bằng chứng từ đầu vào, ràng buộc rõ và bước tiến hữu ích trong nguồn lực. Chỉ dẫn sửa sai của người dùng có giá trị định hướng; reaction đơn lẻ không đủ để đổi mục tiêu hoặc kết luận hiệu suất. Các nguyên tắc này triển khai ba bất biến, không thêm bộ luật riêng theo ngành.

### 4.6 SMART giúp agent làm rõ mục tiêu

Agent dùng SMART để rà soát mục tiêu sau bước phân luồng: Specific, Measurable, Achievable, Relevant, Time-bound, theo cách diễn giải phổ biến trong [hướng dẫn SMART của CDC](https://www.cdc.gov/youth-advisory-councils/action-plans/smart-framework.html). Ánh xạ vào Javis dưới đây là đề xuất thiết kế, không phải yêu cầu người dùng điền biểu mẫu.

| Thành phần | Cách agent áp dụng |
|---|---|
| Specific | Nêu kết quả cụ thể và người/đối tượng được phục vụ |
| Measurable | Chọn bằng chứng nhận biết đạt; có thể là sản phẩm hoặc xác nhận cụ thể, không ép thành phần trăm |
| Achievable | Kiểm quyền, công cụ và nguồn lực; thiếu căn cứ thì khảo sát, không âm thầm hạ yêu cầu |
| Relevant | Giải thích mục tiêu phục vụ nhu cầu gốc ra sao |
| Time-bound | Dùng hạn người dùng đã nêu; nếu chưa có thì đặt mốc xem lại nội bộ có lý do, chưa coi là deadline người dùng |

Mục tiêu discovery có thể chỉ SMART ở bước tìm hiểu tiếp theo. Không tự bịa số nền, chỉ tiêu hoặc hạn chót để lấp đủ năm ô. SMART hỗ trợ chất lượng mục tiêu; không chứng minh đã hiểu đúng mong muốn và không quyết định câu chat nào cần goal bền.

### 4.7 Phản hồi nhanh có ý nghĩa rõ ràng

Thẻ Em đang hướng tới có Đúng ý và Hiểu chưa đúng, tùy chọn kèm biểu tượng. Nút gửi ý nghĩa tường minh goal_fit_confirmed/goal_fit_rejected, gắn người xác nhận, goal_id và revision. Bấm vào thẻ cũ không xác nhận phiên bản mới; im lặng giữ unknown. Bác cách hiểu làm xem lại phần liên quan trước tác động tiếp theo, không tự biến thành lệnh dừng toàn hệ thống hoặc tăng quyền. Không bắt bấm mới được bắt đầu.

Ở sản phẩm đầu ra, Đạt yêu cầu/Cần chỉnh là loại bằng chứng khác, gắn artifact revision và criterion. Xác nhận mục tiêu không đồng nghĩa đầu ra đạt; xác nhận gu viết có thể đủ cho tiêu chí sở thích nếu hợp đồng cho phép, nhưng không ghi đè kiểm tra khách quan đã thất bại hoặc guard. Emoji dưới tin nhắn chung không được tự diễn giải thành các xác nhận này.

Như vậy phản hồi con người vẫn được dùng ở nơi nó có ý nghĩa. Hệ thống không phụ thuộc phản hồi để duy trì năng lực, tăng nhịp hoặc chứng minh mọi loại hiệu quả.

## 5 Kiến trúc tổng thể

| Thành phần | Trách nhiệm | Được thay đổi bởi agent |
|---|---|---|
| Goal framer | Từ nhu cầu hình thành mục tiêu, chọn điều cần làm rõ hoặc khám phá, xem lại giả thuyết theo bằng chứng | Có, qua revision; không viết lại chỉ dẫn gốc hoặc quyền |
| Goal service | Lưu hợp đồng, revision, quan hệ và trạng thái | Qua API và đúng grant |
| Authority service | Kiểm quyền, thu hồi, giữ chỗ tài nguyên | Không tự mở rộng quyền của bên gọi |
| Planner | Chọn hành động, phương pháp, phân công và thời điểm tiếp theo | Có, theo quyền sửa mình |
| Executor | Thực thi qua engine, workflow, MCP và công cụ đã có | Phương pháp/công cụ được cấp; không bỏ cổng quyền |
| Evidence bridge | Thu receipt, lưu nguồn và liên kết bằng chứng | Worker được gửi quan sát, không ghi đè xác nhận của host |
| Evaluator registry | Chạy các bộ đánh giá có phiên bản | Được đề xuất biến thể; không tự thay thước đo của phép thử hiện tại |
| Beat scheduler | Nhận sự kiện, đặt lịch, chống chạy trùng và đánh thức | Chính sách trong giới hạn được cấp |
| Experiment service | So sánh biến thể và quản lý áp dụng/khôi phục | Có thể cải thiện phương pháp thử trong cùng quy tắc chứng minh |
| Supervisor | Dừng worker, thực thi quyền và khôi phục bản phần mềm | Ngoài phạm vi tự sửa đang được thử |

V1 tiếp tục Python, FastAPI, SQLite và dashboard JavaScript hiện có. Không dựng message broker, cơ sở dữ liệu graph, thị trường agent hoặc framework model mới. Dùng transaction và outbox trong SQLite để phối hợp chắc chắn.

Giai đoạn đầu chỉ tự thực thi qua backend có khả năng cưỡng chế phạm vi đã được kiểm tra. Tool native của CLI có thể đi ngoài MCP Hub; không xem allowlist trong prompt là sandbox. Shell và plugin tùy ý chạy cùng quyền host không được mang nhãn đã cô lập. Quyền tự sửa code live chỉ mở sau giai đoạn supervisor.

Ngữ cảnh chạy phải đi xuyên tiến trình: host cấp thông tin xác thực ngắn hạn gắn brain/goal/revision/run/actor và grant cho worker gọi Hub qua HTTP; engine trong tiến trình dùng cùng context đã được host xác nhận. Header tên actor chỉ là nhãn nếu chưa được đối chiếu với ngữ cảnh đó. ContextVar được set/reset bằng token trong try/finally, không được rò sang yêu cầu khác. Cache danh sách tool không giữ context của run trước. Từng invocation có id riêng liên kết action, run và nguồn bằng chứng; slug hoặc khoảng thời gian gần nhau không đủ để quy công.

## 6 Bằng chứng và đánh giá

### 6.1 Định dạng bằng chứng

EvidenceEnvelope chứa evidence_id, brain_id, goal_id, contract_revision, action_id nếu biết, nguồn, source_event_id, resource_ref, resource_version, observed_at, received_at, content_hash, evidence_ref, trust_class, freshness và supersedes_id nếu là đính chính.

Phân biệt nguồn xác nhận: tool receipt do host ghi, dữ liệu từ adapter, đánh giá model, xác nhận người dùng và lời tự báo của worker. Content hash xác nhận nội dung được giữ nguyên, không chứng minh nội dung đúng. Nhiều bản sao từ cùng một nguồn không tạo thêm bằng chứng độc lập.

Ghi bằng chứng mới để đính chính, không xóa bản cũ. Mọi đọc/ghi phải kiểm tra brain_id và người có quyền; đường dẫn hoặc id do model đưa ra không đủ làm quyền truy cập.

### 6.2 Kết quả đánh giá

Assessment gồm goal/revision, evaluator/revision, criterion_results, evidence_ids, verdict, confidence, rationale, evaluated_at và next_observation_at.

Verdict của tiêu chí: met, not_met hoặc unknown. Lỗi chạy evaluator được ghi riêng là error; không ép thành not_met. Guard báo triggered, clear hoặc unknown. V1 dùng confidence low/medium/high có giải thích, không hiển thị xác suất giả từ sự tự tin của model.

Điều kiện all đạt khi mọi tiêu chí đều met. Điều kiện any đạt khi có tiêu chí met, nhưng mọi guard và ràng buộc bắt buộc vẫn phải được thỏa. Thiếu evaluator, dữ liệu quá hạn, sai revision hoặc không đọc được bằng chứng đều ngăn xác nhận thành công.

### 6.3 Bộ đánh giá mở rộng

Giao diện chung Evaluator.evaluate(contract, evidence, now) trả Assessment. Adapter mô tả id, version, input schema, loại bằng chứng, khả năng đọc/ghi, thời gian chờ và điều kiện lỗi. Evaluator mặc định không có quyền tạo tác động ngoài việc ghi assessment.

Các adapter đầu tiên:

- artifact_contract: kiểm tra tài nguyên có tồn tại và đáp ứng cấu trúc/tiêu chí đã khai.
- state_predicate: đánh giá biểu thức dữ liệu khai báo, không chạy mã tùy ý hoặc eval chuỗi từ model.
- rubric: đánh giá chất lượng theo tiêu chí ghim phiên bản, chỉ được xác nhận đạt nếu hợp đồng chấp nhận phương pháp này.
- human_confirmation: dùng cho phần kết quả chỉ người dùng mới có thể xác nhận.

Trong MVP ưu tiên artifact_contract và human_confirmation; rubric model hoãn tới khi cần. Về sau, rubric chỉ chấm sản phẩm có bằng chứng nguồn, bằng phiên bản và tiêu chí đã ghim, không nhận lời tự báo của worker làm sản phẩm đã hoàn thành. Không bắt mọi việc định tính phải chờ người dùng: hợp đồng có thể chấp nhận đánh giá model độc lập cho tiêu chí phù hợp, kèm kiểm tra các điều kiện khách quan. Kết luận cần ghi rõ phương pháp và giới hạn, không giả đó là phép đo chắc chắn.

Tài liệu và MCP trả về là dữ liệu, không có quyền thay hợp đồng hoặc cấp thêm quyền. MCP annotations chỉ là gợi ý về công cụ, không tự xác định chất lượng kết quả hay ý định hoàn tác.

Nhãn read/write/danger của catalog dùng hỗ trợ phân quyền, không chứng minh khả năng hoàn tác. Tool đa hành động phải được phân loại theo arguments thực tế, không lấy effect lúc liệt kê làm kết luận cho mọi invocation. Kết quả ERROR:, isError hoặc lỗi cấu trúc phải được adapter giữ là lỗi; việc hàm trả về bình thường không đồng nghĩa tool thực hiện thành công. Các lần đọc dùng để đánh giá cũng phải lưu nguồn và thời điểm, dù không cần ghi toàn bộ nội dung đọc vào nhật ký hoạt động.

### 6.4 Chỉ số dẫn dắt và quy công

Agent được đề xuất hành động có thể tác động và giả thuyết vì sao chúng giúp đạt mục tiêu. Đây là giả thuyết để kiểm tra, không phải cách tự nhận thưởng bằng số lượng hoạt động. Định kỳ đối chiếu hành động với kết quả, đổi phương pháp khi giả thuyết không còn được hỗ trợ.

Lineage lưu đóng góp, phản biện, bằng chứng và quyết định. V1 ghi nhận hiệu quả ở mức phương pháp và nhóm khi không có đủ căn cứ tách từng người. Không nhân một kết quả thành nhiều phần thưởng độc lập; không mặc định người tổng hợp nhận nhiều nhất.

### 6.5 Phép đo số và chất lượng dữ liệu

Khi cần so sánh chỉ số theo thời gian, dùng adapter metric_series có schema: source, selector, unit, observed_at, window, aggregation, baseline, direction, acceptance và missing_data_policy. Lấy trường được chỉ định từ dữ liệu cấu trúc; không lấy số đầu tiên của văn bản. Văn bản chỉ được chuyển thành số qua parser theo nguồn đã kiểm thử; không khớp schema thì unknown. Agent tự đề xuất cấu hình, người dùng không phải viết frontmatter hoặc chọn metric.

Phân biệt chỉ số là trạng thái tại thời điểm, lượng phát sinh trong kỳ hay bộ đếm tích lũy để chọn last/sum/delta/time_weighted_mean thích hợp. Cửa sổ, múi giờ và baseline có phiên bản. Mẫu dùng observed_at của nguồn; received_at phục vụ theo dõi độ trễ. Gọi nguồn nhiều lần không tạo thêm mẫu độc lập hoặc làm thay đổi cách tính cùng một chuỗi sự kiện. Đánh giá sau khi nhận mẫu phải dùng thời điểm bao phủ mẫu mới; dữ liệu đến muộn được xử lý theo cửa sổ và chính sách đã khai.

Theo dõi riêng khả năng đọc, độ mới, mức bao phủ, tính tương thích và mức chắc chắn khi quy công. Dữ liệu ổn định vẫn có thể rất đáng tin; có hành động xảy ra không chứng minh hành động gây ra thay đổi. Không trộn các đại lượng này thành trọng số chuyển sang reaction khi kết quả không biến động. Chỉ có ba mẫu không đủ làm quy tắc chung xác nhận độ tin cậy; số mẫu và điều kiện bao phủ thuộc adapter và hợp đồng.

Guard bảo vệ trạng thái mong muốn độc lập với việc quy trách nhiệm: khi điều kiện dừng đã được xác nhận, dừng phạm vi đã quy định dù chưa biết ai gây ra. Guard unknown khác clear; chính sách thiếu dữ liệu xác định phần nào còn được làm. Baseline bằng không, số không hữu hạn, đổi đơn vị hoặc thiếu nguồn không được tự coi là 0% thay đổi hay mọi việc bình thường.

## 7 Trạng thái và vòng vận hành

Tách GoalStatus khỏi RunState:

- GoalStatus: draft, active, succeeded, failed, cancelled.
- RunState: ready, running, waiting, blocked, paused, dormant.

Framing lưu mức chắc chắn có giải thích và các giả định chưa kiểm chứng, độc lập với GoalStatus. Một mục tiêu active vẫn có thể dựa trên giả thuyết tạm thời. Superseded mô tả revision đã được thay, không thêm một kết quả thành công vào lịch sử goal. Bước khám phá có tiêu chí riêng; hoàn thành bước này không tự hoàn thành nhu cầu gốc.

Failed chỉ khi có kết luận không đạt theo điều kiện kết thúc hợp đồng. Deadline tới mà chưa có dữ liệu phải ghi rõ unknown và áp dụng chính sách deadline đã chốt, không gọi nhầm là đã chứng minh thất bại. Paused là người dùng tạm dừng. Blocked là có điều kiện cản trở, giữ mã lý do và điều kiện mở lại.

Vòng điều khiển:

1. Nhận sự kiện hoặc lịch tới hạn, kiểm tra hợp đồng vẫn active.
2. Kiểm tra quyền hiện hành, guard, nguồn lực và phiên bản.
3. Thu dữ liệu cần thiết, đánh giá bằng chứng hiện có.
4. Nếu có bằng chứng cách hiểu không còn phù hợp, chuyển Goal framer xem lại trước khi kết luận. Nếu tiêu chí đã đạt và không có mâu thuẫn chưa giải quyết với nhu cầu/ràng buộc đã biết, xác nhận và kết thúc hoặc duy trì theo mode.
5. Nếu cần bước mới, planner trả Decision: act, delegate, experiment, clarify, reframe, wait, escalate hoặc finish. Clarify mở câu hỏi; reframe yêu cầu xem lại hợp đồng có căn cứ. Cả hai đi qua goal service, không phải quyền tự sửa state hoặc grant.
6. Authority service kiểm tra Decision, giữ chỗ tài nguyên, ghi action intent trước khi thực thi.
7. Executor chạy; receipt và kết quả được lưu; đánh giá lại khi có bằng chứng phù hợp.
8. Ghi bài học đủ căn cứ, báo sự kiện có ý nghĩa, đặt lần quan sát tiếp theo.

Finish là yêu cầu kiểm chứng hoàn thành, không có quyền tự set succeeded. Một task hoặc workflow có status done/COMPLETED không tự hoàn thành mục tiêu.

## 8 Beat và giao tiếp

Beat là WakePlan gồm lý do, earliest_at, wake_on, observation_due_at, expires_at và policy_revision. Không gắn tần suất hoạt động trực tiếp với điểm khen/chê.

Ưu tiên sự kiện từ tác vụ, tài nguyên, deadline, nguồn dữ liệu và người dùng. Timer là đường dự phòng khi không có sự kiện phù hợp. Tick của scheduler chỉ làm kiểm tra rẻ bằng code; chỉ gọi model khi có thông tin mới hoặc quyết định cần suy luận.

Waiting có điều kiện mở lại rõ. Dormant không gọi model theo giờ, nhưng giữ subscription cần thiết và nhận lệnh người dùng. Sự kiện phù hợp được đánh thức agent ngủ đông; sự kiện không được tự bỏ user pause hoặc mở lại guard yêu cầu người dùng.

Lịch quan sát guard tách khỏi lịch gọi agent nhưng dùng chung scheduler: một loop giãn nhịp hoặc worker đang bận không được kéo dài khoảng mù của điều kiện dừng. Chỉ đọc để giám sát trong quyền và nguồn lực còn hiệu lực; người dùng thu hồi cả quan sát thì ngừng đọc và báo mất khả năng giám sát. Guard đã nhảy không tự mở lại do một mẫu tốt; điều kiện phục hồi, chống dao động và thông báo lặp thuộc chính sách có phiên bản. Nếu chính sách cho phép phục hồi tự động thì host thực hiện, còn user pause luôn giữ hiệu lực.

Agent đề xuất thời điểm tiếp theo dựa trên thời gian có bằng chứng và khả năng tác động. Host chuẩn hóa timestamp, gom sự kiện trùng, giới hạn theo ngân sách và khả năng phục vụ. Không tự chạy lại liên tục vì nhận chính thông báo do mình tạo.

Mục tiêu không có nguồn sự kiện dùng lần xem lại hữu ích hoặc polling nguồn đã được phép với giới hạn tài nguyên. Chỉ dẫn như “hỏi lại vào thứ Sáu” điều chỉnh WakePlan trực tiếp. Phản hồi về tần suất chỉ sửa chính sách giao tiếp/lịch trong phạm vi yêu cầu; emoji hài lòng không làm worker thức dày. Không có dữ liệu mới hoặc hành động có ích thì ngủ, không gọi model định kỳ chỉ để hỏi người dùng đã hài lòng chưa.

Thông báo mặc định của mục tiêu mới: đạt mốc có ý nghĩa, hoàn thành, chạm guard, lỗi cần can thiệp hoặc cần quyết định. Chi tiết từng hành động có trong nhật ký. Yêu cầu báo định kỳ được ghi riêng. Loop/cron cũ giữ hành vi báo hiện có nếu chưa được chuyển sang mục tiêu.

Khi người dùng nhắn lại, agent tiếp tục hoặc lập mục tiêu mới từ trạng thái và ý định hiện tại, không phục hồi quyền đã hết hạn. Không xóa năng lực vì lâu không nhận reaction.

## 9 Nhóm có người chốt

Mỗi group gắn goal_id, leader_id, membership và epoch điều phối. Chỉ leader đang giữ epoch có quyền chốt kế hoạch thực thi; leader không có quyền bỏ guard hoặc sửa quyền gốc. Nếu leader gián đoạn, host chuyển quyền điều phối có ghi nhận và ngăn leader cũ cùng chốt.

Thành viên tự chọn nói, phản biện, làm việc hoặc im trong phạm vi nhiệm vụ. Không ép round-robin; cũng không đánh thức toàn bộ thành viên cho mọi tin. Subscription theo vai trò và thay đổi liên quan giúp giảm lượt gọi vô ích. Thảo luận tự do vẫn được hỗ trợ trong một run được cấp tài nguyên.

Kết luận cần giữ lý do, bằng chứng và phản biện chưa giải quyết. Bất đồng về phương pháp có thể tạo hai thử nghiệm nhỏ nếu còn nguồn lực. Leader quyết định dùng kết quả nào theo hợp đồng, không đồng nhất đa số đồng ý với bằng chứng đúng.

Leader được phân bổ lại công việc và tăng/giảm nhịp trong grant khi người dùng vắng. Khi cần quyết định ngoài quyền, nhóm chờ và gửi một yêu cầu tổng hợp. Các bước độc lập vẫn có thể chạy nếu phạm vi chờ cho phép; nếu hợp đồng yêu cầu dừng cả cây, toàn bộ hậu duệ dừng.

Leader chịu trách nhiệm thống nhất cách hiểu nhu cầu và tự điều chỉnh mục tiêu suy ra trong ràng buộc gốc. Thành viên được phản biện cách đặt mục tiêu bằng bằng chứng; không cần chờ người dùng tự chọn mục tiêu cho từng agent. Đổi mục tiêu cha làm các con liên quan kiểm tra lại trước tác động tiếp theo; một câu hỏi tổng hợp thay cho nhiều agent hỏi lặp.

V1 không xây chat mạng xã hội giữa agent. Trao đổi phải thuộc một mục tiêu hoặc một phép thử được cấp tài nguyên. Việc khám phá ý tưởng mới là mục tiêu con hợp lệ khi nằm trong sự ủy quyền khám phá.

## 10 Quyền và tài nguyên

Giữ tên và nghĩa suggest, auto, full hiện có. Tự chủ và quyền sửa mình là trục riêng, không gom thành một bậc thứ tư mặc nhiên có mọi quyền:

- chủ động: có được tự chọn công việc trong mục tiêu hay chỉ chạy khi được giao;
- sửa phương pháp: memory đề xuất, prompt, skill, workflow;
- phân công: gọi agent sẵn có hoặc tạo agent con;
- sửa code: workspace/phạm vi code được cho phép;
- áp dụng phiên bản: có được tự đưa bản đã kiểm chứng vào chạy hay chỉ chuẩn bị bản đề xuất.

Đây là các capability trong grant, UI có thể cung cấp preset dễ hiểu. Full không tự mang quyền sửa code Javis. Người dùng có thể bật quyền đó một lần cho đúng agent/nhóm/phạm vi và không bị hỏi lại mỗi thay đổi hợp lệ.

Mỗi grant có principal, brain_id, scope, capability revisions, expires_at nếu có, parent_grant_id và generation thu hồi. Kiểm tra ở lúc quyết định và ngay trước tác động. Quyền ghi qua shell/API khác phải nằm trong cùng biên thực thi, không chỉ qua MCP.

ResourceEnvelope dùng map tên tài nguyên và đơn vị, không bắt buộc tiền. V1 đo lượt gọi, token và thời gian worker; chi phí tiền chỉ ghi khi provider cung cấp dữ liệu đáng tin. Giữ chỗ trước run, đối soát sau run. Khi giá/usage chưa rõ, thể hiện unknown và dùng trần tài nguyên thay thế đã chốt, không coi là miễn phí.

Tác vụ và experiment kế thừa engine, model và hạn mức chung đã cấu hình; không bắt khai lại mỗi goal. Ghi số lượt gọi, thời gian và usage nhà cung cấp thực sự trả về; quota gói thuê bao không đọc được thì unknown. Khi gặp giới hạn, lưu checkpoint và chờ đúng điều kiện, không vòng retry vô hạn, tự chuyển sang API trả phí hoặc dùng tài khoản khác. Kiểm khả năng chạy nền và điều kiện dịch vụ của engine được chọn ở lúc triển khai; không giả mọi gói thuê bao đều hỗ trợ cùng cách tự động hóa.

Thu hồi chặn cấp run mới và hủy run đang chạy bằng supervisor. Tác động đã gửi ra ngoài có thể không thu hồi được; ghi nhận kết quả chưa chắc chắn và đối soát trước khi retry. Hành động không hỗ trợ idempotency không được chạy lại mù sau crash.

## 11 Tự cải thiện bằng thử nghiệm

### 11.1 Vòng thử nghiệm

Mỗi Experiment lưu mục tiêu liên quan, giả thuyết, baseline_revision, candidate_revision, evaluation_revision, tập tình huống, ngân sách, phạm vi sửa, điều kiện áp dụng và bản khôi phục.

Các bước: phát hiện điểm yếu cụ thể; tạo biến thể; chạy baseline và candidate trên tình huống tương đương; thu receipt độc lập; so sánh thành công, lỗi, công người dùng và chi phí; áp dụng nếu đủ bằng chứng. Unknown giữ candidate ở trạng thái chưa kết luận.

Có tập tình huống giữ riêng để kiểm tra khả năng khái quát, không cho candidate đọc đáp án hoặc sửa kết quả chấm. Agent có thể đề xuất thêm phép thử nhưng không tự thay tập kiểm chứng đang dùng để áp dụng chính nó.

Không buộc mọi mục tiêu có một hàm điểm cộng dồn. Acceptance có thể yêu cầu đạt chất lượng tối thiểu và giảm chi phí, hoặc tốt hơn trên tiêu chí chính mà không vi phạm điều kiện khác. Tiêu chí được ghim trước khi so sánh.

Phân biệt vòng điều chỉnh mục tiêu với vòng so sánh phương pháp. Nếu hợp đồng thay đổi trong khi experiment đang chạy, kết quả cũ giữ nguyên phạm vi; experiment không còn phù hợp ghi inconclusive với lý do goal_reframed. Muốn áp dụng cho mục tiêu mới phải kiểm tra lại tính áp dụng và tạo phép so sánh trên cùng revision mới. Không thưởng cho việc đổi đề để thắng. Cải thiện Goal framer được thử trên cùng đầu vào và ràng buộc giữ riêng, đánh giá cả độ phù hợp lẫn kết quả công việc.

### 11.2 Quyền khám phá

Người dùng có thể dành một phần nguồn lực cho khám phá trong grant. Agent tự chọn phép thử đáng làm; không phải có reaction tích cực mới được thử. Phân bổ khám phá nằm trong tổng hạn mức, không sinh ví tài nguyên riêng vô hạn.

Giữ số lượng biến thể theo ngân sách lưu trữ đã cấp. Có thể giữ biến thể khác biệt dù chưa thắng, kèm lý do, để tiếp tục tìm kiếm sau. Không cố giữ mọi phiên bản hoặc tạo agent vô hạn.

### 11.3 Trí nhớ và bài học

Quan sát mới vào sổ bằng chứng trước. Bài học có status proposed/validated/superseded, phạm vi áp dụng và evidence_ids. Chỉ bài học validated được đưa vào phần tự học của memory; chỉ dẫn rõ của người dùng có thể xác nhận trực tiếp.

Tận dụng đường JAVIS_LESSON đang có nhưng bổ sung xác nhận cho nguồn từ Resonance. Không biến mỗi emoji thành một bài học. Bài học bị bằng chứng mới bác bỏ được rút khỏi ngữ cảnh sử dụng, giữ lịch sử để giải thích.

### 11.4 Sửa chính Javis

Code candidate chạy trong checkout và worker riêng. Supervisor ngoài candidate giữ quyền cấp run, kiểm chứng, áp dụng và khôi phục. Bản thử không ghi được evaluator được bảo vệ, bằng chứng gốc, grant hoặc thông tin xác thực của supervisor.

Cho phép tự áp dụng khi grant có quyền deploy và kiểm chứng đạt: kiểm tra chức năng, tương thích dữ liệu, build/CI theo repo, kiểm tra khởi động, chạy thử hạn chế rồi mở rộng. Health endpoint chỉ chứng minh một phần liveness; phải có kiểm tra hành vi đại diện trước khi xác nhận bản tốt.

Triển khai code và khôi phục dữ liệu là hai việc khác nhau. Migration đầu tiên phải tương thích ngược hoặc có snapshot và đường phục hồi đã kiểm thử. Không chỉ reset Git rồi tuyên bố rollback hoàn chỉnh.

Nếu môi trường chưa tạo được ranh giới quyền thật, chỉ hỗ trợ thử trong workspace cô lập và chuẩn bị candidate; UI ghi rõ chưa hỗ trợ tự cập nhật live có kiểm soát. Không tuyên bố file cờ cùng tài khoản là kill switch bất khả sửa.

## 12 Dữ liệu và khả năng phục hồi

Lưu hợp đồng và runtime ở JAVIS_STATE_DIR/resonance.sqlite3, phân vùng theo brain_id. Các bảng dự kiến: intent_records, goals, goal_revisions, goal_events, goal_evidence_links, assessments, actions, wakeups, reservations, grants, group_memberships, experiments, variants và outbox. IntentRecord lưu tham chiếu đầu vào, ràng buộc và nguồn; framing nằm trong goal_revisions; câu hỏi và câu trả lời nằm trong goal_events có id liên kết. Payload bằng chứng dùng EvidenceStore có sẵn, không sao chép secret vào JSONL hoặc prompt.

SQLite là nguồn chuẩn cho revision/quyền/trạng thái. Có thể xuất bản hợp đồng Markdown cho người dùng đọc và mang đi; chỉnh bản xuất chỉ tạo draft khi nhập lại, không tự cấp quyền. Không thêm folder goals vào prompt toàn cục.

Sự kiện có source_event_id chống trùng và thời gian xảy ra/nhận riêng. Transaction ghi trạng thái và outbox cùng lúc. Consumer được nhận lại sự kiện nhưng idempotent. Unique key chống nhận hai run cho cùng logical action; worker lease có hạn và kiểm tra generation thu hồi.

EvidenceStore hiện có retention hữu hạn. Bằng chứng dùng cho mục tiêu hoặc experiment chưa đóng phải được pin hoặc giữ snapshot phù hợp; sau khi kết thúc, giữ theo chính sách lưu trữ được cấp. Người dùng vẫn có quyền xóa dữ liệu; nếu dữ liệu bị xóa, assessment lịch sử ghi unavailable và không được giả vờ tái kiểm chứng được.

Hash chain/log append không thay thế ranh giới hệ điều hành. Bản ghi không thể sửa chỉ được cam kết trong phạm vi quyền truy cập đã kiểm tra.

Phân biệt log giao tiếp tùy chọn với sổ bắt buộc để tự hành động: mất log phụ không làm hỏng chat; không lưu được action intent/quyền/reservation trước tác động thì chặn tác động đó. Nếu tác động đã gửi nhưng chưa lưu được receipt, đối soát trước khi cấp tiếp hoặc retry. Không tạo id rồi báo đã ghi thành công khi thao tác lưu thất bại. Xuất JSONL phục vụ đọc lại được, nhưng không dùng file xoay có thể mất lịch sử làm nguồn chuẩn cho hoàn tác hoặc quyền.

Mỗi EvidenceEnvelope được liên kết với assessment và thời gian quan sát, không chỉ với lần tool trả dữ liệu. Pin giữ được bản ghi không làm dữ liệu cũ trở thành dữ liệu mới; độ mới luôn do hợp đồng và evaluator kiểm tra.

Liên kết tin nhắn lưu bền bằng brain_id, session_id, message_id, run_id và các action_id thực sự thuộc lượt đó; bảng message_links nối với sổ actions. Lưu tin trước khi phát WebSocket và trả cùng định danh trên API đọc lịch sử. Tải lại trang khôi phục được liên kết kết quả và trạng thái hoàn tác; lưu/phát thành công không tự chứng minh người dùng đã đọc hoặc sử dụng kết quả. Không gắn các file của cùng actor trong mười phút gần nhất vào một tin bất kỳ.

### 12.1 Hoàn tác có điều kiện

Hoàn tác là tiện ích riêng để người dùng kiểm soát tác động, không phải tín hiệu phạt hiệu suất mặc định. Chỉ hiện khi adapter có khả năng và tiền điều kiện còn đúng. Với file, host giữ bản trước được mã hóa, hash/phiên bản sau ghi, phạm vi đường dẫn được phép và action id. Khi hoàn tác phải kiểm quyền hiện tại và so trạng thái file hiện tại với trạng thái sau ghi; nếu người dùng hoặc tác vụ khác đã sửa thì trả conflict, không ghi đè hoặc xóa bản mới.

Hoàn tác tạo một action mới trỏ tới action gốc, có idempotency, giữ chỗ và receipt; crash hoặc hai yêu cầu cùng lúc không tạo hai tác động bù. Kiểm tra đường dẫn sau resolve, symlink/junction và khóa/CAS theo khả năng backend. Nếu không bảo đảm phát hiện thay đổi xen giữa kiểm tra và ghi, chỉ tạo bản phục hồi riêng để xem và so sánh. Bản chụp hết hạn hoặc không tồn tại thì không quảng bá là có thể hoàn tác. Không suy ra khả năng hoàn tác của dịch vụ ngoài từ nhãn write; việc phục hồi code cũng không thay thế hoàn tác tác động ngoài.

## 13 Giao diện người dùng

Điểm vào là hội thoại “Anh muốn em giúp điều gì?” trong Cộng sự hoặc nhóm. Người dùng mô tả nhu cầu; agent tự tạo mục tiêu và bắt đầu phần việc hợp lệ. Bỏ màn hình bắt chọn mục tiêu, biểu mẫu chỉ số và bước xác nhận mục tiêu mặc định. Trang Việc hiển thị mục tiêu agent đang theo đuổi và liên kết đến tác vụ thực thi. Không tạo một hệ Kanban thứ hai.

Thẻ “Em đang hướng tới” hiển thị: cách hiểu hiện tại, tình trạng, giả định quan trọng chưa rõ, bằng chứng mới nhất, việc đang làm, điều đang chờ và lý do lần hoạt động tiếp theo. Chỉ giải thích khi đổi hướng có ý nghĩa; không xin duyệt lại mỗi revision. Không hiển thị phần trăm tiến độ nếu tiêu chí không có cách tính có nghĩa.

Các thao tác: mô tả thêm hoặc sửa cách hiểu bằng lời, tạm dừng, tiếp tục, xem bằng chứng, xem lịch sử, điều chỉnh quyền, dừng cây mục tiêu. Chi tiết mục tiêu và tiêu chí có thể mở để kiểm tra, không phải biểu mẫu bắt điền. Câu trả lời “anh chưa biết” được chấp nhận và chuyển sang khám phá trong quyền hiện có. Thao tác dừng nói rõ phạm vi và những tác động đã xảy ra. Kết quả và yêu cầu can thiệp gửi về đúng người/kênh đã giao việc.

Nút hoàn tác file chỉ thêm sau khi adapter ở mục 12.1 đạt kiểm chứng; không phải điều kiện để ra mắt vòng mục tiêu đầu tiên. Không gán biểu tượng cảm xúc thành lệnh dừng ngầm. Lệnh dừng và sửa ý có thao tác hoặc ngôn ngữ rõ, tách khỏi reaction giao tiếp.

Giao diện dùng nhãn tiếng Việt dễ hiểu; chuỗi mới có vi/en theo cấu trúc i18n hiện tại. Tham số evaluator, token, revision chỉ nằm trong phần chi tiết khi hữu ích. Reaction có thể giữ như tính năng giao tiếp độc lập, không phải phụ thuộc để bật Resonance.

## 14 Những thành phần có thể dùng lại

Ảnh chụp mã nguồn ban đầu dùng để lập kế hoạch: HEAD 5b4a9be1, nhánh codex/restore-chat-colors. Đối chiếu remote ngày 06 tháng 10 năm 2026 xác nhận origin/main tại 7d264236 (0.83.2), có 121 commit checkout cũ chưa có; checkout cũ có 3 commit riêng. Trên main này có _reply_policy_sandbox_engine và _reply_policy_ask. Trước M1 phải kiểm main mới nhất, ghi commit nền và dò lại toàn bộ bảng dưới cùng các điểm nối trong kế hoạch trên commit đó. Các mô tả sau là khảo sát lịch sử, không phải xác nhận đường chạy live hay hợp đồng tích hợp đã được nghiệm thu trên main.

AgentPolicy trong server/agent_runtime.py mặc định off/allocation 0 khi thiếu cấu hình. Main có đường nối và đường cũ tiếp tục hoạt động; việc file tồn tại không chứng minh canary đã chạy live. MVP phải có phép thử end-to-end với engine được chọn và dữ liệu mô phỏng trên host trước khi đặt phụ thuộc vào runtime này. Không bật toàn bộ canary chỉ để làm demo; tái sử dụng đường chạy hiện có đã được kiểm chứng cho phạm vi hẹp.

| Thành phần hiện có | Dùng lại | Phần cần bổ sung |
|---|---|---|
| server/self_improve.py | LoopFeature.tick, run_cycle, scheduler, mode, báo kết quả | Adapter gắn goal_id, một chủ sở hữu lịch, không dùng utility EMA để đóng mục tiêu |
| server/agent_runtime.py | AgentRunner, CapabilityGrant, replan trong quyền | Nhận GoalRunContext và grant được host xác nhận; quyền phân công linh hoạt có kiểm tra |
| server/workflow_runtime.py | Checkpoint, revision, resume, lịch sử node | Nhận authorization đã cấp; workflow legacy tiếp tục hỏi ở write như hiện tại |
| server/workflow_runs.py | Lịch sử các lần chạy | Liên kết run với goal/revision; done của run không thay verdict mục tiêu |
| server/task_store.py và server/tasks.py | Kanban, transaction, claim, dependency | Metadata mục tiêu và chống enqueue trùng qua outbox |
| server/evidence_store.py | Evidence có hash, mã hóa, redaction và retention | Pin theo mục tiêu/experiment; liên kết provenance và thời gian quan sát |
| server/capability_executor.py | Lease, invocation, idempotency/resource lock helpers | Adapter quyền mục tiêu; không coi executor read-only này đã hỗ trợ mọi write |
| server/context_runtime.py | Trace, checkpoint, audit và runtime event | Kết nối các id mục tiêu, không phụ thuộc trạng thái canary để ghi bằng chứng bắt buộc |
| server/updater.py và server/update_state.py | Khởi động, health check, lùi mã nguồn | Bao bằng supervisor được bảo vệ, kiểm chứng hành vi và tương thích dữ liệu |
| dashboard/workspace.js và dashboard/console.js | Cộng sự, nhóm hiển thị, Việc, loop | Goal panel và scoreboard; group hiển thị hiện tại không tự là group runtime |

Không dùng tỷ lệ phần trăm sẵn sàng để ước lượng công việc. Các đường ghi qua workflow, bảo vệ shell, retention bằng chứng và self-update là các hạng mục phải kiểm thử riêng.

## 15 Lộ trình triển khai

**Ưu tiên hiện tại:** [kế hoạch MVP](../plans/2026-10-06-resonance-00-mvp.md), một agent/một goal, ba module lõi mới và hai evaluator nhỏ. Hoãn nhóm, module tự học tổng quát, metric chuỗi thời gian, supervisor và self-update. Bảng dưới là hướng mở rộng sau khi có một vòng chạy thật, không phải yêu cầu đầu vào của MVP.

| Giai đoạn | Đầu ra sử dụng được | Điều kiện qua giai đoạn |
|---|---|---|
| A Lõi mục tiêu và bằng chứng | Từ nhu cầu suy ra hợp đồng, làm rõ, nhập bằng chứng, đánh giá, xem scoreboard | Đầu vào mơ hồ không đòi người dùng chọn mục tiêu; hai loại mục tiêu dùng cùng lõi; quyền/revision/unknown đúng |
| B1 Một agent thực thi | Thực hiện mục tiêu qua runner hiện có, tiếp tục sau gián đoạn | Không chạy trùng, thu hồi có hiệu lực, task done không tự thành công |
| C1 Phép thử cải thiện nhỏ | So sánh hai phương pháp trên fixture, áp dụng cấu hình trong quyền | Cải thiện được xác nhận bằng receipt độc lập, candidate không sửa được phép chấm |
| B2 Nhóm và beat thích nghi | Phân công, chốt, chờ sự kiện, ngủ đông, tiếp tục | Leader failover không chốt trùng; con không vượt quyền/ngân sách cha |
| C2 Tự sửa phương pháp | Bài học, skill/workflow, thư viện biến thể có giới hạn | Bản kém không được áp dụng; rút được bài học sai |
| C3 Tự sửa và cập nhật Javis | Candidate code, supervisor, thử hạn chế, khôi phục | Test ranh giới thực và phục hồi qua crash/migration đạt |

Thứ tự là A -> B1 -> C1 -> B2 -> C2 -> C3. Không chờ làm xong cảm xúc hoặc nhiều tuần sử dụng mới kiểm tra tự cải thiện. Không ấn định thời gian lịch trước khi hoàn thành giai đoạn A và đo điểm nghẽn tích hợp.

Kế hoạch triển khai chi tiết:

1. [Lõi mục tiêu và bằng chứng](../plans/2026-10-06-resonance-01-foundation.md).
2. [Thực thi mục tiêu và cộng tác](../plans/2026-10-06-resonance-02-runtime.md).
3. [Tự cải thiện và áp dụng phiên bản](../plans/2026-10-06-resonance-03-evolution.md).

Mốc trình diễn đầu tiên chỉ cần một yêu cầu tự nhiên, một agent, một adapter đầu ra và một phép thử cải thiện trên tài nguyên mô phỏng. Chọn lần lượt các phần cần thiết từ A, B1 đến B3 và C1/C2 để chứng minh vòng khép kín; chưa gọi toàn bộ giai đoạn hoàn thành nếu các tiêu chí còn lại chưa đạt. Nhóm, reaction và nút hoàn tác không nằm trên đường bắt buộc của mốc này. Quan sát guard đã chọn và liên kết bằng chứng vẫn phải hoạt động từ đầu.

## 16 Thử nghiệm và nghiệm thu toàn hệ thống

Ba nhóm fixture không phụ thuộc nghiệp vụ: tạo một tài liệu đúng cấu trúc và nguồn dẫn; duy trì một chỉ mục khớp với bộ file thay đổi; cải thiện cách xử lý một tập yêu cầu trên tài nguyên mô phỏng. Việc thêm bộ fixture thứ ba không được thêm nhánh if theo ngành vào lõi.

Đối chứng gồm cùng runner không học, runner Resonance có học, và nhóm khi cần so hiệu quả cộng tác. Dùng mục tiêu tương đương, cùng ngân sách, tách dữ liệu phát triển với dữ liệu giữ lại, đảo thứ tự thử để giảm tác động thời gian. Ghi cả lần không thành công và tiêu chí chưa đo được. Không suy ra hiệu quả dài hạn từ vài ví dụ thắng.

| Tình huống bắt buộc | Kết quả mong muốn |
|---|---|
| Worker nói xong nhưng không có bằng chứng | Mục tiêu chưa được xác nhận đạt |
| Yêu cầu mơ hồ, người dùng không biết đặt mục tiêu | Agent tự hình thành giả thuyết, chọn bước khám phá hữu ích trong quyền |
| Câu hỏi tùy chọn không được trả lời hoặc trả lời chưa biết | Không hỏi lặp vô ích; tiếp tục phần độc lập; không coi im lặng là cấp quyền |
| Mục tiêu suy ra đạt nhưng có bằng chứng lệch nhu cầu | Xem lại mục tiêu, không tuyên bố đã giải quyết nhu cầu chỉ vì đạt chỉ số |
| Agent sửa mục tiêu hoặc tiêu chí giữa phép thử | Revision cũ giữ kết quả; không tính đổi đề là cải thiện; kiểm chứng lại trước áp dụng |
| Đổi mục tiêu khi hết ngân sách, paused hoặc guard kích hoạt | Không reset chi phí hoặc tự mở lại hoạt động bị chặn |
| Yêu cầu có ràng buộc mâu thuẫn hoặc đích không khả thi | Giải thích giới hạn, làm phần hữu ích tương thích; không tự bỏ ràng buộc người dùng |
| Dữ liệu đến muộn, đính chính hoặc lặp | Cập nhật đúng revision, không nhân điểm hoặc hành động |
| Người dùng sửa mục tiêu khi worker đang chạy | Không áp kết quả cũ để đóng mục tiêu mới |
| Hai worker cùng claim hoặc cùng phân ngân sách | Một hành động hợp lệ, tổng tài nguyên không vượt |
| Tool timeout sau khi có thể đã ghi ra ngoài | Trạng thái uncertain, đối soát trước retry |
| Người dùng dừng cả cây | Không cấp run mới cho hậu duệ, hủy run trong khả năng host |
| Mất dữ liệu đánh giá hoặc hết hạn bằng chứng | Unknown, không dùng tóm tắt để giả chứng minh |
| Maintain đạt một lần rồi điều kiện thay đổi | Tiếp tục theo dõi và ghi degraded/unknown đúng |
| Agent con thắng nhưng cha không tiến triển | Cha vẫn chưa đạt; xem lại cách phân rã |
| Candidate sửa evaluator hoặc giả log test | Không được công nhận hoặc áp dụng |
| Update khởi động được nhưng hành vi sai | Không mở rộng triển khai, khôi phục bản trước theo kế hoạch |
| Reaction thay đổi, kết quả giữ nguyên | Không đổi đánh giá hiệu suất |
| Hai brain có loop trùng slug hoặc hai run cùng actor | Không trộn mẫu, quyền, bằng chứng hay liên kết tin nhắn |
| Công cụ trả lỗi dạng nội dung hoặc chứa nhiều số | Không coi mã lỗi/ngày tháng/id là kết quả mục tiêu |
| Tool đa hành động được liệt kê là read nhưng invocation ghi | Kiểm quyền và ghi receipt theo arguments thực tế |
| Guard vượt ngưỡng khi chưa có hành động agent hoặc worker đang ngủ | Dừng theo hợp đồng; không đợi quy công hoặc đợi worker thức |
| Mất kho audit trước hoặc sau tác động | Trước: chặn tác động; sau: uncertain và đối soát, không retry mù |
| File đã được người dùng sửa sau action cần hoàn tác | Conflict hoặc bản phục hồi riêng, không mất thay đổi mới |
| Refresh chat hoặc WebSocket nhận lại sự kiện | Giữ đúng liên kết message/run/action, không nhân tin hoặc hoàn tác |

## 17 Quy tắc triển khai và chuyển đổi

Feature mới mặc định off cho cài đặt mới và bản fork. Bật theo goal/brain được chọn, không tự chuyển loop đang chạy sang mục tiêu. Không thay đổi giá trị mặc định full của loop legacy chỉ vì thêm Resonance.

Mỗi giai đoạn có migration tương thích, kiểm thử hồi quy và đường tắt tính năng. Theo docs/quy-uoc-dev.md khi bắt đầu code: nhánh riêng, đặt chỗ phiên bản và PR nháp trước khi viết code, CI xanh mới tích hợp. Việc viết bộ tài liệu này chưa tạo runtime, chưa cấp quyền tự chủ và chưa khởi chạy mục tiêu.

Những lựa chọn hoãn: reward market giữa agent; một chỉ số xếp hạng tất cả agent; học trọng số emoji; bộ máy retrain model; graph database; tự sửa supervisor trong cùng experiment. Chỉ thêm khi có vấn đề thực tế và phép thử chứng minh cần thiết.

Đối chiếu phần mã tham khảo với [bản review mới nhất](2026-10-06-resonance-revised-package-review.md), gồm các lỗi đã tái hiện và đính chính về nhánh mã. Các phản biện cũ đã lưu trong [gói lịch sử](../../../exports/archive/Javis-Resonance-LICH-SU-2026-10-06.zip). Danh mục và thứ tự sử dụng hiện hành nằm trong [README Resonance](../README-RESONANCE.md).

## 18 Nguồn tham khảo

- [FranklinCovey về bốn nguyên tắc thực thi](https://www.franklincovey.com/courses/the-4-disciplines/): tập trung mục tiêu, chỉ số dẫn dắt, bảng điểm và nhịp trách nhiệm. Ánh xạ vào agent trong tài liệu này là thiết kế của Javis.
- [FranklinCovey về mục tiêu có điểm xuất phát và thời hạn](https://www.franklincovey.com/blog/strategic-execution-in-uncertainty-and-complexity/).
- [FranklinCovey về chỉ số dẫn dắt và kết quả](https://www.franklincovey.com/courses/the-4-disciplines/discipline-2-act/).
- [FranklinCovey về nhịp trách nhiệm](https://www.franklincovey.com/courses/the-4-disciplines/discipline-4-accountability/).
- [Sakana AI về Darwin Gödel Machine](https://sakana.ai/dgm/): nghiên cứu tự sửa code, đánh giá và giữ các biến thể; không phải bảo đảm Resonance tự cải thiện vô hạn.
- [MCP về giới hạn của tool annotations](https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/).
