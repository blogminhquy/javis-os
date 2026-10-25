# Goal cải tiến Javis — kết thúc ở M2 engineering và bàn giao Claude Opus 5.5

**Quyết định chủ ngày24/10/2026, mục18, thay thế điều kiện hoàn thành M0–M8
và mọi lệnh tiếp tục toàn bộ cũ bên dưới.** Goal hiện tại chỉ hoàn thành khi
M2 engineering đạt đầy đủ gate kỹ thuật hiện hành và bộ bàn giao được cập nhật,
commit/tích hợp. Không khởi động M3–M8 hoặc thử account/model/business/live.
Các mục cũ được giữ để bảo toàn hợp đồng và lịch sử, áp dụng khi không mâu thuẫn
với mục18. Điểm vào bàn giao: [HANDOFF](../handoffs/claude-opus-5-5/HANDOFF.md).

Ngày: 22/10/2026, Asia/Saigon.

Tài liệu này là chỉ dẫn cho một Goal sẽ được chủ phát lệnh. Việc soạn/lưu tài liệu không khởi động Goal, không gọi model thử nghiệm và không cấp quyền triển khai production. Phần ủy quyền bên dưới có hiệu lực khi chủ gửi lệnh Goal tham chiếu toàn bộ file này.

## 1. Lệnh khởi động lịch sử — phạm vi đã được mục18 thay thế

```text
/goal Hoàn thành cải tiến agent và skill Javis từ M0 đến M8 theo toàn bộ chỉ dẫn tại D:\Project\Javis-OS\docs\superpowers\AGENT-SKILL-IMPROVEMENT-GOAL.md. Tự lập và thực hiện kế hoạch, kiểm thử, review, sửa lỗi, tạo PR và tích hợp theo quy ước repo; tiếp tục qua các mốc đủ điều kiện mà không hỏi lại xác nhận thông thường. Chỉ hoàn thành khi có bằng chứng đạt đầy đủ các điều kiện trong file; nếu còn gate nghiệp vụ, dữ liệu, quyền hoặc thời gian quan sát thật chưa đạt thì báo chính xác phần bị chặn và tiếp tục mọi phần độc lập còn làm được.
```

Đây là lệnh nhập trong Codex hỗ trợ `/goal`, không phải lệnh chạy PowerShell. Chỉ cần phát một lần; mọi lần tiếp tục phải đọc hồ sơ tiến độ và làm tiếp từ điểm chưa hoàn tất.

## 2. Mục tiêu xuyên suốt

Đưa chức năng **Cải tiến có kiểm chứng** của Javis từ spec thành sản phẩm thực thi được, bao gồm toàn bộ M0–M8: nền revision/guard/nghiệm thu, sandbox và case, thử sửa skill có đối chứng, qualification/canary/rollback, skill routing và adapter engine, cải tiến agent có phạm vi, bundle agent–skill–helper, Team và thư viện kinh nghiệm thích nghi.

Không kết thúc ở viết kế hoạch, demo giao diện, scaffold module, test giả hoặc chỉ MVP M0–M3. Hoàn thành kỹ thuật, hiệu quả nghiệp vụ và đủ điều kiện rollout là ba loại bằng chứng khác nhau, phải theo dõi riêng cho từng mốc.

Nguồn chuẩn:

1. [Spec agent/skill M0–M8](specs/2026-10-22-agent-skill-evidence-improvement-design.md), toàn bộ 29 mục.
2. [Spec nghiệm thu và usage Team](specs/2026-10-22-team-quality-first-design.md), chỉ những phụ thuộc cần cho mốc đang làm.
3. `AGENTS.md` nếu có, `CLAUDE.md`/`AGENT.md` áp dụng, `ARCHITECTURE.md` trên main mới và `docs/quy-uoc-dev.md`.
4. Mã nguồn hiện tại và bằng chứng test/pilot thật. Tài liệu tên hàm/số dòng cũ là điểm dò, không thay mã mới.

Nền nghiên cứu là Javis 0.284.0, `a02e45fcd7c58bb3fde4eac3a850cb87c618621c`. Lúc thực hiện phải lấy main mới nhất, ghi snapshot mới và làm gap analysis trước khi code. Không triển khai lại phần main đã có và đạt.

Nếu source trên main khác spec, giữ mục tiêu và bất biến; ghi quyết định điều chỉnh interface theo mã thật. Không lặng lẽ hạ phạm vi, bỏ gate hoặc sửa tiêu chí đạt để công việc dễ kết thúc. Xung đột có ảnh hưởng ý định/chất lượng/quyền phải báo chủ, trong khi tiếp tục phần độc lập đã được phép.

## 3. Quyền thực hiện khi chủ phát Goal này

Tôi duyệt hướng thiết kế và phạm vi M0–M8 của spec để bắt đầu triển khai. Tôi ủy quyền cho phiên thực hiện:

- Khảo sát mã, tự viết và tự rà soát implementation plan của từng mốc, rồi thực hiện mà không dừng hỏi tôi duyệt lại từng plan, từng bước hoặc “có tiếp tục không”. Đây là lựa chọn thực hiện liên tục của tôi cho công việc này.
- Sửa mã, tài liệu, test, migration và UI liên quan; chạy build/test/checker, dựng môi trường thử và sửa lỗi tìm thấy trong phạm vi Goal.
- Tạo hoặc tái sử dụng worktree phù hợp; tạo nhánh `codex/agent-skill-improvement-*`; commit, push, mở PR và merge theo quy ước repo khi CI và review bắt buộc đạt. Không bỏ gate CI, không force-push nhánh chia sẻ và không merge thay đổi chưa kiểm.
- Triển khai trực tiếp theo từng mốc. Có thể dùng subagent để review hoặc xử lý phần độc lập nếu công cụ/môi trường cho phép; chủ thể chính giữ trách nhiệm tích hợp và kiểm chứng. Không tạo chat sidebar mới hay nhắn task khác không liên quan.
- Chạy model-backed smoke/feasibility trong môi trường thử biệt lập bằng engine/model/reasoning tôi đã chọn và tài khoản đã cấu hình cho tác vụ phát triển, khi cấu hình đó được xác minh. Các lượt này dùng quota/tài nguyên thật; ghi đầy đủ usage. Không tự mua dịch vụ, thêm tài khoản hoặc đổi cấu hình model để chạy được.
- Dùng fixture có nhãn mô phỏng để kiểm kỹ thuật; đọc nguồn nghiệp vụ đã có quyền đọc trong phạm vi dự án/brain được giao để chuẩn bị snapshot. Không tự mở rộng sang brain/tài khoản khác và không lấy dữ liệu riêng không thuộc tác vụ.
- Áp/revert candidate, kiểm canary với clock giả và nghiệm thu UI tự động trên brain thử dùng một lần; luôn ghi rõ đó là kiểm kỹ thuật, không live canary.

Lệnh này không tự thay thế quyết định nghiệp vụ cần tôi chấm, không cấp quyền tự bật `auto_scoped`/activation trên brain thật, không duyệt gửi/đăng/thanh toán, không cho sửa luật chủ, không cấp quyền lấy secret vào workspace. Deploy/restart server thật, rollout live và đọc nguồn chưa được cấp cần quyền cụ thể từ phiên hoặc môi trường; không suy từ quyền merge PR.

Không dừng để xin lại những quyền đã có trong Goal này. Chỉ hỏi khi thật sự thiếu thông tin/quyền/nguồn mà không thể lấy từ cấu hình và bằng chứng được phép đọc. Gom câu hỏi còn thiếu thành yêu cầu cụ thể, tránh hỏi rải rác từng việc nhỏ.

## 4. Khởi tạo và bảo toàn công việc hiện có

1. Kiểm tra nhánh, git status, worktrees, PR và VERSION. Checkout chính `D:\Project\Javis-OS` có thể cũ và có nhiều thay đổi của người khác; không reset, clean, đổi nhánh hoặc ghi đè chúng.
2. Đọc các file nguồn chuẩn ngay tại vị trí hiện có. Spec có thể là file chưa commit; sao chép đúng những tài liệu cần dùng vào worktree triển khai, ghi hash nguồn. Không mang cả thay đổi chưa commit không liên quan vào nhánh mới.
3. Ưu tiên worktree đang phù hợp thuộc cùng công việc; nếu chưa có thì tạo từ main mới nhất. Không đụng worktree của chat khác.
4. Kiểm các chức năng/phụ thuộc đã phát hành. Tạo bảng `existing -> missing -> evidence -> milestone`; phần đã đạt có bằng chứng thì ghi reused, không viết lại.
5. Chạy baseline test liên quan trên nền sạch và ghi kết quả. Test đỏ có sẵn không được coi là đạt; xác định nguyên nhân/mức ảnh hưởng và xử lý blocker trong phạm vi. Không chỉnh assert hoặc nới quyền để biến đỏ thành xanh.
6. Trước khi code mỗi PR phát hành, đọc và tuân thủ quy trình xí chỗ version/CHANGELOG của repo hiện hành. Đồng bộ main, tránh trùng version và giải quyết conflict cần thiết.
7. Bắt đầu hồ sơ tiến độ ở `docs/superpowers/status/agent-skill-improvement-progress.md` trong worktree triển khai. Không đánh dấu mốc done chỉ vì có file plan.

## 5. Cách làm liên tục qua các mốc

Thứ tự mặc định: **M0 -> M1 -> M2 -> M3 -> M4 -> M5 -> M6 -> M7 -> M8**. Phụ thuộc thật theo mục 23 của spec quyết định khả năng thực thi. M4/M5 chia sẻ effective view; M7 phải có nền nghiệm thu và usage Team tương ứng. Không mở rollout khi gate phụ thuộc chưa đạt.

Mỗi mốc thực hiện trọn vòng:

1. Đối chiếu mục tiêu, test IDs và interface với main mới, viết implementation plan đủ rõ để thực hiện.
2. Tự review plan theo spec, sửa thiếu sót rồi code. Không ngừng ở kế hoạch chờ một câu “tiếp”.
3. Viết test hành vi có ý nghĩa, thấy lỗi đúng khi thiếu triển khai, rồi làm mã chạy đúng. Giữ test nhanh và kiểm hồi quy tương xứng.
4. Chạy kiểm liên quan, migration/recovery/quyền/scope và UI cần thiết. Nếu lỗi, tìm nguyên nhân rồi sửa; không lặp nguyên cách thất bại hoặc hạ tiêu chí.
5. Review diff và bằng chứng; dùng reviewer độc lập khi có công cụ, ghi phạm vi review thật. Reviewer không làm thay nghiệm thu của chủ và không có quyền tự chấp nhận sản phẩm sai.
6. Cập nhật trạng thái kỹ thuật/pilot/rollout, log test thực đã chạy, hạn chế và bước kế tiếp.
7. Mở/cập nhật PR đủ nhỏ, hoàn tất CI/review theo repo, merge khi đủ điều kiện và chuyển mốc tiếp từ nền đã tích hợp. Nếu một PR chờ ngoại cảnh, xử lý phần độc lập an toàn thay vì mở hàng loạt nhánh chồng chưa kiểm.

Được tiếp tục xây phần kỹ thuật của mốc sau trên nền đã kiểm khi chỉ đang chờ chủ chấm hoặc thời gian live canary, nhưng phải để nhãn **engineering-only/not released**, không vượt gate sử dụng/rollout, không giả mốc phụ thuộc đã nghiệm thu toàn bộ. Một mốc có prerequisite kỹ thuật chưa đạt thì sửa nền trước.

Không rút gọn M4 thành chỉ có một interface adapter rỗng hoặc M8 thành nút bật tắt. Mỗi adapter/surface công bố hỗ trợ phải có enforcement và kiểm thực tương ứng; môi trường không thể kiểm engine nào thì ghi chưa hỗ trợ/chưa xác minh cho engine đó và giữ mốc mở theo phạm vi đã chốt.

## 6. Các bất biến phải giữ trong toàn bộ Goal

- Chất lượng và độ đúng trước chi phí. Không tự đổi model/provider/reasoning, thêm trần USD mặc định, bỏ dữ liệu cần thiết hoặc bỏ kiểm chứng để giảm usage.
- Giữ đường model cấu hình hiện có. Không chạy engine thật nếu chưa xác định được engine được chủ chọn; không dùng engine khác thay thế âm thầm.
- Baseline luôn có trong so sánh; candidate thua hoặc chưa rõ thì giữ baseline. Không viết gate bắt buộc candidate phải thắng.
- Hợp đồng/checker/đáp án được pin và nằm ngoài vùng sửa của solver/improver; qualification kín, tiêu thụ đúng vòng, không chỉnh candidate bằng đáp án rồi dùng lại bộ ấy như holdout mới.
- Trial dùng workspace và context sạch, không sửa canonical/live memory, không side effect. Native shell/web/connector phải được chặn thực bằng host; prompt không phải sandbox.
- Revision/effective view theo scope, receipt và cache generation phải đi xuyên mọi đường nạp đã enable; không nạp nhầm mirror hoặc ảnh hưởng scope khác.
- Giữ nguyên luật chủ, model/reasoning, quyền, disabled state và ownership. Protected content có cả ý nghĩa; giữ chữ gốc rồi thêm câu trái luật vẫn không đạt.
- Reuse ledger, usage, lessons, scheduler và nghiệm thu hiện có. Không tạo runtime/sổ tiền/goal giả để né schema.
- CAS/lease/idempotency, crash recovery, late result, cancellation và rollback phải kiểm thật. Không quay lại bằng cách ghi đè sửa mới của chủ hoặc phục hồi quyền đã thu hồi.
- Trial/compose/qualification không trở thành source tự học/đặt việc production. Không gom nhiều agent đồng tình thành bằng chứng độc lập.
- Unknown, interrupted, quota, thiếu telemetry hoặc thiếu nạp phiên bản phải được ghi đúng. Không đổi thành pass hoặc 0 usage.

## 7. Pilot, nghiệm thu và khoảng chờ thực tế

Làm đủ feasibility, pilot A/B và bộ kiểm của các mốc tương ứng theo spec. Chọn nguồn/context từ những gì chủ đã cấp; nếu chưa có, chuẩn bị đầy đủ runner/report và nêu chính xác nguồn, engine hoặc người chấm cần bổ sung. Fixture chỉ chứng minh cơ chế, không được dùng để tuyên bố hiệu quả nghiệp vụ thực.

Không sửa ngưỡng thống kê hoặc cherry-pick case để đạt. Candidate bị rejected/inconclusive là một kết quả hợp lệ; hệ phải xử lý đúng và giữ baseline. Vẫn xem xét giả thuyết có bằng chứng mới trong phạm vi spec, không chạy vô hạn tới khi thắng. Không tự mở rộng rollout chỉ vì mã đã xong.

Live canary đòi **thời gian thật và nhiệm vụ thật** theo spec. Clock giả, tua thời gian hoặc synthetic tasks chỉ được ghi là test kỹ thuật. Chưa đủ 7 ngày/10 việc hoặc thiếu owner confirmation thì gate còn mở; không gọi Goal hoàn thành toàn bộ.

Khi phải chờ quota/thời gian/người chấm, giữ checkpoint và tiếp tục phần độc lập. Không gọi model lặp để báo “vẫn đang chờ”, không tự tạo recurring automation ngoài quyền được chủ cấp. Nếu phiên/môi trường không hỗ trợ tiếp tục qua khoảng chờ, báo rõ checkpoint và điều kiện resume; không hứa sẽ tự thức dậy khi chưa có cơ chế.

Một phép thử kỹ thuật được phép chạy trong brain tạm không đồng nghĩa đã cho phép canary trên brain thật. Đề nghị live rollout phải là một kết quả cụ thể để chủ xem: revision, scope, evidence, model config, nguồn và đường rollback; tận dụng quyền đã cấp nếu phiên đã có quyết định tương ứng.

## 8. Hồ sơ tiến độ và cách tiếp tục sau gián đoạn

File tiến độ giữ tối thiểu:

- Goal/spec/source hashes, snapshot main và phiên bản hiện tại.
- Worktree/branch/PR URL/commit/CI và quyết định review từng mốc.
- Bảng M0–M8 với ba cột **kỹ thuật**, **bằng chứng nghiệp vụ**, **điều kiện rollout**, kèm lý do nếu chưa đạt.
- Test commands đã chạy, kết quả thật và evidence refs; phân biệt fake/real smoke/pilot/live canary.
- Candidate/base/config/case-set ids, trạng thái qualification, activation và pending owner actions.
- Blocker có nguồn, việc đã thử, phần độc lập tiếp tục được và bước tiếp theo cụ thể.

Cập nhật sau mỗi đơn vị có ý nghĩa hoặc trước khi kết thúc lượt; không ghi secret/PII vào progress. Phiên mới phải đọc progress và đối chiếu state/PR thật, không làm lại mốc đã xong hoặc tin một checkbox thiếu chứng cứ.

Không dừng ở cuối một mốc chỉ để tóm tắt. Báo tiến độ ngắn rồi tiếp tục tới phần chưa đạt. Nếu môi trường có lifecycle Goal, dùng đúng trạng thái/lưu lượng của môi trường; không tự đánh dấu complete vì gần hết context hoặc vì đã viết báo cáo.

## 9. Khi nào thật sự cần chủ can thiệp

Chỉ nêu blocker khi không thể tự giải bằng quyền và nguồn sẵn có, ví dụ: thiếu credential/cấu hình engine được chọn, thiếu nguồn nghiệp vụ độc lập, tiêu chí cần chủ chấm, quyền live chưa cấp, quota chưa mở hoặc khoảng canary chưa đủ. Trước đó phải làm các phần chuẩn bị/kiểm kỹ thuật còn làm được.

Báo gọn: mốc/phần nào bị chặn, bằng chứng, đã thử gì, cần đúng thông tin/quyết định nào và các phần khác đang tiếp tục. Không báo toàn Goal xong, không tự thay bằng một phạm vi nhỏ hơn và không yêu cầu anh phê duyệt lại toàn bộ.

Nếu tự review phát hiện spec mâu thuẫn hoặc không thể hiện thực nguyên văn, đưa phương án sửa nhỏ nhất giữ ý định và bằng chứng. Quyết định kỹ thuật thường lệ tự giải; thay chính sách quyền, định nghĩa thành công, dữ liệu sử dụng hoặc trade-off chất lượng trọng yếu cần chủ quyết.

## 10. Điều kiện hoàn thành Goal

Chỉ đánh dấu **hoàn thành toàn bộ** khi:

1. M0–M8 đều có sản phẩm thực thi và bằng chứng tương ứng theo spec, không có scaffold/placeholder/adapter giả được công bố như tính năng đã có.
2. Các test bắt buộc, kiểm hồi quy, migration/recovery/quyền/scope/rollback và review yêu cầu đạt trên snapshot cuối; CI xanh cho mọi thay đổi tích hợp.
3. Pilot có kết luận trung thực cho từng nghiệp vụ/config, gate nội dung cần chủ chấm đã được xử lý; không dùng test giả thay bằng chứng thực.
4. Các phạm vi live được cho phép đã qua đủ điều kiện canary, hoặc chủ đã quyết rõ phạm vi đó không phát hành sau kết quả rejected/inconclusive. Những phần chưa có quyền/nguồn/quan sát không tự được coi là đã đạt.
5. Mọi code thay đổi của Goal đã được commit/PR/tích hợp theo quy ước; không lẫn thay đổi người khác, không bỏ sót source cần chạy.
6. Có tài liệu sử dụng/vận hành/khôi phục, progress đầy đủ và báo cáo cuối gồm bản phát hành, PR/commit, bằng chứng thật, phạm vi hỗ trợ và hạn chế.

Chủ quyết không phát hành một scope do không tạo giá trị là quyết định sản phẩm hợp lệ, không là bằng chứng candidate tốt. Mọi thay đổi giảm phạm vi Goal cần chủ xác nhận rõ; không dùng một report “chưa đủ bằng chứng” để tự hoàn thành các mốc còn thiếu.

Báo cáo cuối phải tách **đã triển khai**, **đã kiểm bằng model thật**, **đã chứng minh giá trị trong phạm vi nào**, **đã phát hành/bật ở đâu** và **còn phần nào bị chặn**. Nếu còn blocker bắt buộc, Goal vẫn chưa hoàn thành toàn bộ và lifecycle phải phản ánh điều đó theo khả năng môi trường.

## 11. Tham chiếu cú pháp Goal

[OpenAI Docs: Using Goals in Codex](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex) mô tả `/goal <outcome>` và mục tiêu có điều kiện kiểm chứng qua nhiều lượt. Tài liệu này dùng cấu trúc đó; không bảo đảm một Goal có thể vượt quyền, quota, gián đoạn môi trường hoặc rút ngắn thời gian canary thật.

## 12. Bổ sung quy trình từ M2C đến M8 — 23/10/2026

Đây là chỉ dẫn bổ sung của chủ, chuyển từ chat “Xác định bước harness2 tốn thời gian”
(`01a16662-a77c-72e2-9c40-265c5659d5cc`) trong lúc M2C Task1 đang làm. Áp dụng ngay,
không khởi động Goal khác, không làm lại M0–M2B và bảo toàn test đang chạy hữu ích.
Bản nguồn trước bổ sung có SHA-256
`67061573b8c584d65d0ecf1daa4c56b536c78c07fcc5158cfa090d40ea299afd`;
hash này và toàn bộ lineage/bằng chứng lịch sử giữ nguyên. Hash của tài liệu sau
bổ sung được ghi riêng trong hồ sơ tiến độ, không thay hash nguồn ban đầu.

1. Trước mỗi task, ghi ngắn gọn thành phần đổi, bên gọi/phụ thuộc và tập test.
   Trong vòng sửa chạy bài tái hiện/RED→GREEN; cuối task chạy regression theo ảnh
   hưởng; trước tích hợp chạy regression tích hợp cần thiết và đầy đủ CI bắt buộc
   trên commit cuối. Không quét toàn bộ improvement sau mỗi bản vá nhỏ nếu không
   có rủi ro hoặc thay đổi mới đòi hỏi.
2. Mỗi finding ghi phạm vi, commit đã review và trạng thái. Sau vá, reviewer kiểm
   diff, tái hiện gốc và đường bị ảnh hưởng. Chỉ mở lại toàn nhánh khi đổi kiến
   trúc/interface/schema/quyền/vòng đời hoặc có bằng chứng thiếu sót hệ thống;
   không giao nhiều reviewer đọc lại cùng phạm vi không đổi. Giữ review tổng thể
   độc lập khi triển khai ổn định trước tích hợp, và xác minh phù hợp cho mọi sửa
   sau đó trên bản cuối.
3. Tái dùng bằng chứng khi có commit/source hashes, lệnh, môi trường/runtime/config
   và phạm vi, và phần chứng minh không đổi hoặc bị ảnh hưởng gián tiếp. Không
   chắc thì mở rộng kiểm. Nguồn cũ hoặc lượt chạy qua nhiều snapshot không chứng
   minh commit cuối. Không chạy lại chỉ vì compaction/resume hay để báo tiến độ.
4. Kiểm Linux sớm cho filesystem/quyền/subprocess/SQLite/đường dẫn. Không chờ cuối
   nhánh mới phát hiện khác biệt Windows/Linux; không đổi môi trường đích/nới assert.
5. Chỉ chạy song song script đã xác minh cách ly thư mục tạm, HOME/config, DB,
   cổng và tài nguyên khác. Nhóm chia sẻ state hoặc chưa rõ vẫn tuần tự. Tối ưu
   runner/CI cần kiểm riêng, không mở thành dự án refactor làm chậm M2C.
6. Không thêm vòng spec/plan/review hình thức ngoài nhu cầu thật. Plan đủ dùng,
   tự review theo quyền đã có và tiếp tục không hỏi lại quyền chủ đã cấp. Các plan
   từ M2C đến M8 phải kế thừa mục bổ sung này.
7. Giữ nguyên gate owner/grant/scope, luật chủ, dữ liệu/holdout, migration/old-reader,
   native isolation/effective-view/qualification, cancellation/crash/cleanup/
   concurrency/recovery, lineage/usage/unknown, atomic apply/revert/rollback,
   nghiệm thu nghiệp vụ và live canary thật. Khi đổi có thể ảnh hưởng bất biến nào
   thì kiểm bất biến đó. Kiểm toàn bộ theo quy ước repo vẫn bắt buộc trước merge.
   Không giảm model/reasoning, bỏ test bắt buộc, hạ ngưỡng, che failure hoặc đổi
   định nghĩa hoàn thành để tăng tốc.
8. Checkpoint ghi gọn test/review đã chạy, bằng chứng tái dùng và lý do, bằng
   chứng bị vô hiệu bởi thay đổi mới, thời gian thực đo được nếu có. Không hứa
   tỷ lệ tăng tốc chưa đo. Tiếp tục Goal từ checkpoint hiện tại sau khi lưu bổ sung.

## 13. Bổ sung thứ tự thực hiện: code toàn bộ M0–M8 trước — 24/10/2026

Đây là cập nhật trực tiếp của chủ, được chuyển từ chat “Xác định bước harness2
tốn thời gian” (`01a16662-a77c-72e2-9c40-265c5659d5cc`). Áp dụng từ checkpoint
hiện tại, không reset, không dừng ở MVP M2 và không thu hẹp phạm vi. Mục này đổi
thứ tự công việc khi các đoạn trước hoặc spec gắn việc viết code mốc sau với
pilot mốc trước; giữ nguyên tiêu chí chất lượng, quyền và định nghĩa hoàn thành.
Goal trước bổ sung này có SHA-256
`558e91848624c2dbc5daf1d5decb64b43b960285ce0416e40099ca63863b2ec8`.
Hash nguồn ban đầu `67061573b8c584d65d0ecf1daa4c56b536c78c07fcc5158cfa090d40ea299afd`
và mọi lineage/bằng chứng lịch sử giữ nguyên; hash sau bổ sung được ghi riêng.

1. **Giai đoạn 1:** hoàn thiện code và kiểm kỹ thuật toàn bộ M0–M8, gồm backend,
   runtime, UI, migration, adapters trong phạm vi đã chọn, agent/bundle/Team và
   vận hành. **Giai đoạn 2:** sau khi phần kỹ thuật hoàn thiện mới chạy thử thực
   tế bằng model/tài khoản/dữ liệu nghiệp vụ, feasibility/pilot A/B, đánh giá và
   correction theo kết quả, đủ thời gian/nhiệm vụ canary và rollout có quyền.
2. Giai đoạn 1 vẫn làm unit test, RED/GREEN hành vi, integration/E2E mô phỏng,
   migration/rollback/quyền/scope/cancellation/crash/recovery, runtime với fixture
   và localhost fake provider/credential giả, review độc lập và CI bắt buộc;
   kế thừa toàn bộ mục12 về giảm lặp. Hoãn inference tài khoản thật, model-backed
   feasibility nghiệp vụ, pilot thật và live canary sang Giai đoạn 2. Không tự
   tạo dữ liệu hoặc quyết định nghiệp vụ thay chủ. Nếu có lượt thật đang chạy,
   bảo toàn ownership/settlement/bằng chứng và không khởi động thêm.
3. Hoàn thiện prerequisite kỹ thuật trước consumer tương ứng. Gate chờ bằng
   chứng nghiệp vụ/canary không ngăn xây code độc lập của mốc sau: tách interface
   và policy, dùng dependency injection/fixture để kiểm kỹ thuật, không giả gate
   đã đạt hoặc mở activation/runtime thật chưa qualified.
4. Mỗi mốc đánh dấu riêng **code hoàn thiện / kiểm kỹ thuật đạt ở môi trường nào /
   cần kiểm engine thật / chờ pilot nghiệp vụ / chờ canary và rollout**. Adapter
   chưa xác minh thực tế không được công bố hỗ trợ đầy đủ. Có thể xác nhận riêng
   “giai đoạn code hoàn tất” đúng phạm vi/bằng chứng; không đánh Goal toàn bộ
   complete khi Giai đoạn 2 còn mở.
5. Không bỏ test kỹ thuật quan trọng, review độc lập hoặc exact-final-head full
   CI; không tạo scaffold/placeholder thay chức năng. Không dùng mô phỏng khẳng
   định native isolation, hiệu quả nghiệp vụ hoặc readiness thật. Khi thiếu bằng
   chứng thực tế, giữ production/activation gated và ghi rõ giới hạn. Merge/phát
   hành code theo quyền và quy ước hiện có không đồng nghĩa deploy/restart/bật
   trên brain thật.
6. Chuyển các task đòi thử nghiệm thực tế trong plan hiện tại sang danh sách
   Giai đoạn 2 có truy vết, giữ nguyên tiêu chí và evidence cũ. Nếu một phụ thuộc
   kỹ thuật thật sự cần thông tin chỉ thử thật mới biết, ghi rõ phần chưa xác
   minh và tiếp tục phần độc lập; không lặp nghiên cứu/tự thử thật để trì hoãn
   toàn bộ code.
7. Lưu mục bổ sung này vào Goal, progress/checkpoint, plan hiện tại và kế tiếp;
   bảo toàn hash nguồn gốc và lineage như mục12. Tiếp tục từ checkpoint hiện
   tại, không làm lại phần đã đạt và không hỏi lại xác nhận thông thường.

## 14. Bổ sung ưu tiên tái sử dụng Harness² cho phần chưa viết — 24/10/2026

Chỉ dẫn trực tiếp của chủ được chuyển từ chat “Xác định bước harness2 tốn thời
gian” (`01a16662-a77c-72e2-9c40-265c5659d5cc`), áp dụng từ checkpoint hiện tại.
Goal trước mục14 có SHA-256
`f683ff6abba61e110ef8034fe1451d80390d6688866c2def5f2f964ec4fcd356`.
Giữ hash nguồn gốc, toàn bộ lineage và bằng chứng cũ; ghi hash mới riêng.

1. Ưu tiên tái sử dụng mã [Google Harness²](https://github.com/google-research/harness2)
   ở các phần **chưa viết**, để giảm công thực tế. Nguồn chuẩn đã pin trong spec
   là `1cfe254e8d25b15f37048c3730134686abe60335`. Nếu cần nguồn mới, pin SHA riêng
   và ghi chênh lệch liên quan; không âm thầm đổi snapshot chuẩn.
2. Trước mỗi thành phần mới, đối chiếu upstream có mục tiêu, ghi bảng ngắn:
   chức năng Javis cần → file/hàm/SHA upstream → dùng nguyên / adapter / viết
   riêng → lý do và test hợp đồng cần. Chỉ đọc dependency trực tiếp đủ quyết
   định, không audit lại toàn repo hoặc mở đợt refactor lớn.
3. Ưu tiên prompt Propose/Compose/Reflection và ranh giới evidence trong
   `core/prompts.py`, điều phối Propose–Probe–Compose trong `core/recursion.py`,
   selection độc lập trong `core/selection.py`, kinh nghiệm/chỉ mục trong
   `core/library.py`, cùng helper/context/tree/protocol/test thực sự liên quan.
   Compose, recipe/library và bundle còn thiếu phải kiểm upstream trước.
4. Chọn import/dependency pin hoặc vendor một phần có nguồn gốc rõ và adapter
   hẹp theo tổng công tích hợp/bảo trì. Kiểm dependency, side effect, ownership
   và interface thật; không tạo runtime, usage ledger hay executor trùng Javis.
5. Không thay phần Javis đã hoàn thiện chỉ để tăng tỷ lệ reuse. Chỉ đổi khi có
   lỗi hoặc lợi ích cụ thể đủ bù chi phí, có phạm vi/bằng chứng. Không hứa phần
   trăm tiết kiệm chưa đo; không thêm hồ sơ/review hình thức.
6. Khi thực sự lấy code, giữ Apache-2.0, copyright/attribution và NOTICE nếu
   áp dụng; ghi SHA và sửa đổi trong nguồn/manifest. Kiểm riêng giấy phép của
   dependency/third_party/dataset được lấy; không tự copy benchmark/dataset.
7. Không lấy policy upstream trái hợp đồng Javis: `selection_pool` snapshot
   chuẩn chỉ chọn finals và loại baseline; Javis luôn giữ baseline trong so
   sánh/quyết định, candidate thua hoặc inconclusive thì giữ bản cũ. Khả năng
   sửa system prompt/guardrails/plugins của upstream không cấp quyền sửa luật
   chủ, quyền hay model của Javis. Prompt không thay host enforcement.
8. Giữ mọi gate source/owner/grant/scope, protected content, holdout kín,
   lineage/config/version, native isolation/effective view, cancellation/crash/
   cleanup/concurrency/recovery, usage/unknown, migration/old-reader, atomic
   apply/revert, review độc lập và full CI trên commit cuối. Test upstream
   không thay kiểm adapter/Javis; chỉ lặp regression theo ảnh hưởng thực tế.
9. Giữ mục13: Giai đoạn1 hoàn thiện code M0–M8 với kiểm kỹ thuật, mô phỏng và
   localhost fake provider; thử model/tài khoản/nghiệp vụ, pilot và live canary
   vẫn ở Giai đoạn2. Reuse không cho phép thử thật hoặc rollout sớm.
10. Lưu chỉ dẫn vào Goal và tham chiếu progress/checkpoint/plan hiện tại;
    plan sau kế thừa. Checkpoint ghi gọn module đã tận dụng, phần cần adapter
    và phần phải viết riêng. Bảo toàn công việc đang chạy, tiếp tục Goal và
    không hỏi lại xác nhận thường lệ.

## 15. Bổ sung tận dụng prompt và cấu trúc bằng chứng cho phần đã viết — 24/10/2026

Chỉ dẫn trực tiếp tiếp theo của chủ từ cùng chat
`01a16662-a77c-72e2-9c40-265c5659d5cc`, mở rộng có mục tiêu mục14, không cho
refactor diện rộng. Goal trước mục15 có SHA-256
`77310e4c4635b012efb8f565bd842d314c82d6e2d168b90dd1ef006f484a2b2b`;
nguồn/hash/evidence lịch sử giữ nguyên. Nguồn Harness² vẫn pin
`1cfe254e8d25b15f37048c3730134686abe60335`.

1. Sau khi bảo toàn đơn vị đang làm, chọn delta nhỏ ở
   `server/improvement_generation_protocol.py:render_proposer_input` và consumer
   thật, đối chiếu `harness2/core/prompts.py`. Tăng hướng dẫn tìm lỗi sớm nhất
   có bằng chứng, giữ hai góc `execution/domain_process`, sửa nhỏ đúng nguyên
   nhân, nêu tác dụng dự kiến/rủi ro, KEEP_BASE/no-change khi thiếu căn cứ.
   Giữ JSON/patch contract, giới hạn candidate/repair, byte offsets và luật chủ;
   không lấy các quyền sửa system prompt/guardrails/plugins của upstream.
2. Dùng cấu trúc reflection: chỉnh sửa cụ thể → run/trace/nguồn được phép →
   khác biệt hành vi quan sát → helped/hurt/no observed effect/confounded.
   Không suy nguyên nhân từ selection win, nhiều sửa cùng lúc hoặc một rollout.
   Kết quả tổng thể và đánh giá ý nghĩa/luật chủ là bằng chứng riêng.
3. Recipe/report còn thiếu dùng bài học có điều kiện áp dụng và evidence,
   cho phép không tạo bài học. Không nạp cả thư viện. Phần đã có ưu tiên
   projection/renderer/adapter hẹp; giữ lịch sử/schema/format đã phát hành,
   chỉ version/migrate khi có nhu cầu thật, không để giống upstream.
4. Pure anonymization/seeded order của `selection.py` là ưu tiên sau, chỉ khi
   có điểm nối rõ. Giữ baseline, comparator/ngưỡng độc lập; không lấy
   finals-only selection_pool hoặc thay bằng phán xét model.
5. Chỉ dùng nguồn được cấp, không thêm raw CoT/secret/holdout/đáp án hay
   checker-private vào input. Giữ native/provider/asset-use unknown và giới
   hạn quan sát; khác giả định evidence thì chỉ lấy cấu trúc lập luận phù hợp.
6. Không làm lại store/sandbox/worker/native qualification/ledger/usage/quyền/
   lifecycle để reuse prompt. Không nghiên cứu/review lại toàn nhánh. Ghi đúng
   function/SHA upstream, delta, callers và test ảnh hưởng trong reuse map.
7. Khi trích code/prompt giữ Apache-2.0/copyright/NOTICE và provenance/sửa đổi.
   Review contract, kiểm hành vi renderer/evidence/boundary/output compatibility
   và regression ảnh hưởng; không chỉ assert một câu literal. Đổi nguồn thuộc
   native footprint phải làm mất hiệu lực/tái qualification theo cơ chế thật.
8. Giữ review độc lập theo delta và full CI commit cuối. Giai đoạn1 chỉ code/
   kiểm kỹ thuật/mô phỏng; model/account/nghiệp vụ/canary ở Giai đoạn2. Không
   tuyên bố prompt nâng chất lượng hay tiết kiệm token khi chưa đo.
9. Lưu bổ sung vào Goal/progress/checkpoint/plan/reuse map, bảo toàn việc đang
   làm và lineage. Tiếp tục từ checkpoint thuận tiện, không restart hay xin
   lại xác nhận thông thường. Mục tiêu là cải thiện đề xuất/bằng chứng cụ thể,
   không kéo dài việc bằng viết lại hạ tầng.

## 16. Bổ sung cho phép thay có chọn lọc phần đã viết bằng Harness² — 24/10/2026

Chỉ dẫn trực tiếp mới của chủ từ chat
`01a16662-a77c-72e2-9c40-265c5659d5cc`. Goal trước mục16 có SHA-256
`e868339ebd3ad1a73fe9faea13b74e2af959c8b3f8148eb4c2ddbae63ac8fc20`;
bảo toàn hash nguồn gốc và mọi lineage lịch sử. Mục này nới các hạn chế ở mục14–15
đúng phạm vi sau: **cho phép thay phần đã viết khi chứng minh phù hợp hơn và đáng
tổng công chuyển đổi**, không giữ thiết kế chỉ vì đã tốn công. Không sửa hồi tố
quyết định/evidence cũ, không refactor rộng chỉ để giống Google hay tăng tỷ lệ copy.

1. Áp dụng tại đơn vị hiện tại hoặc kế tiếp; không restart, không bỏ ownership
   việc đang chạy, không khảo sát lại toàn bộ code. Khi upstream có lõi tốt hơn,
   ghi so sánh trước/sau ngắn với file/hàm/SHA cụ thể trước khi thay.
2. Lợi ích cần cụ thể: giảm logic/nhánh/dependency tự duy trì; tách propose/probe/
   compose/selection/reflection tốt hơn; tăng kiểm chứng/tái lập/truy vết; hoặc
   reuse implementation thật. Không mặc định Google tốt hơn hay suy chất lượng
   nghiệp vụ cao hơn khi chưa thử thật.
3. Ưu tiên prompt phân tích/đề xuất/compose/reflection; cấu trúc chỉnh sửa →
   run/trace được phép → khác biệt quan sát → helped/hurt/no observed effect/
   confounded; hàm thuần và lõi điều phối; recipe/library/bundle khi đến phần ấy.
4. So tổng công adapter, consumer, migration, backward compatibility,
   qualification, regression và review với lợi ích bảo trì/độ đúng dài hạn.
   Đáng làm thì tự thực hiện trong quyền đã có. Phương án rộng/tốn nhiều công
   hoặc đổi chính sách thì ghi trade-off, tiếp tục phần độc lập; không audit vô hạn.
5. Ưu tiên upstream nguyên hoặc vendor có provenance và adapter hẹp. Giữ pin
   `1cfe254e8d25b15f37048c3730134686abe60335`; snapshot khác cần pin/lý do/chênh
   lệch riêng. Giữ Apache-2.0/copyright/NOTICE, ghi sửa đổi và kiểm third-party dùng.
6. Giữ boundary source/owner/grant/brain/scope, luật chủ, baseline trong quyết
   định và inconclusive/thua giữ baseline; holdout/private answers kín; giới hạn
   candidate/repair/compose; source/runtime/config pins; history/usage/unknown;
   actual Trial/Call ownership; cancellation/crash/cleanup/concurrency/recovery;
   migration/old-reader; atomic apply/revert; native/session/resume/activation.
   Không thay gate bằng prompt/model vote hoặc tạo executor/ledger song song.
7. Database/quyền/native lifecycle không được mặc định bất khả xâm phạm, nhưng
   chỉ thay khi có lợi ích cụ thể và kế hoạch giữ compatibility/recovery. Không
   lấy benchmark framework làm production authority; giữ action/model/reasoning
   và quyền live đã có.
8. Mỗi thay đổi là delta nhỏ review được, giữ test hợp đồng hành vi trước/sau,
   thêm test theo rủi ro cần kiểm, kiểm consumer/integration bị ảnh hưởng. Reuse
   evidence phần không đổi khi đủ điều kiện. Không giữ hai runtime dài hạn để
   né chuyển đổi, không xóa đường cũ trước khi bảo toàn user/history/consumer.
9. Đổi prompt/code thuộc native footprint phải invalidate/requalify đúng cơ
   chế; không nhận proof cũ cho nguồn mới. Giữ review độc lập theo delta và full
   required CI commit cuối. Phase1 code/kiểm kỹ thuật/mô phỏng/localhost fake;
   model/account/business pilot/canary vẫn Phase2 như mục13.
10. Checkpoint ghi upstream dùng thật, phần thay/giữ và lý do, test/review/
    qualification và lợi ích đo được nếu có. Không hứa phần trăm tiết kiệm chưa đo.
11. Lưu Goal/progress/checkpoint/plan/reuse map; bảo toàn công việc và quyền
    chủ đã cấp. Tự quyết kỹ thuật thường lệ theo tiêu chí này, tiếp tục từ
    checkpoint, không hỏi lại xác nhận thường lệ.

## 17. Bổ sung ưu tiên compose và experience library trực tiếp qua adapter — 24/10/2026

Chủ chốt trực tiếp qua chat `01a16662-a77c-72e2-9c40-265c5659d5cc`: ưu tiên
dùng implementation compose và thư viện kinh nghiệm Google Harness² qua adapter,
sau đó so thay lõi điều phối nếu tổng công ít hơn/giá trị tốt hơn. Goal trước
mục17 có SHA-256 `76e349119bd3f7148204b2e57800d9769aac4f7cb73c271e6f8541ff0a6c5b18`.
Kế thừa mục12–16, bảo toàn hash/history/lineage, không reset/audit toàn repo hay
bỏ ownership đang chạy. Áp dụng từ đơn vị phù hợp gần nhất sau điểm nối an toàn.

1. **Compose trước:** pin `1cfe254e8d25b15f37048c3730134686abe60335`; đối chiếu
   `core/prompts.py:aggregate/compose_round`, chỗ gọi trong `core/recursion.py`
   và dependency trực tiếp. Ưu tiên import/vendor phần implementation thật dùng
   được, adapter hẹp vào input/evidence/runner/patch hoặc bundle validator Javis;
   được trích phần độc lập nếu cả module kéo executor/benchmark không cần. Không
   chỉ viết lại lời mô tả rồi gọi dùng trực tiếp. Giữ surface được chủ cho phép,
   tuning data và giới hạn candidate/repair/compose. Compose tạo candidate/bundle
   mới phải kiểm riêng, không thừa hưởng pass/qualification; KEEP_BASE/unknown giữ.
2. **Experience library kế tiếp:** kiểm `core/library.py` và tree/context/spec
   liên quan, ưu tiên cấu trúc/serialization/index/entry trực tiếp qua adapter
   brain/scope/evidence/revision. `rmtree/copy/write` và mutable index chỉ chạm
   root riêng đã kiểm/thuộc quyền. Dùng snapshot/index dẫn xuất thì nguồn chuẩn
   Javis vẫn bất biến, encrypted, có quyền/retention/revocation/trace links. Không
   tạo filesystem canonical/authority song song hay nạp cả thư viện mọi scope.
   Hàm không giữ nguyên được cần ghi xung đột thật và tận dụng phần còn phù hợp.
3. **Điều phối sau hai phần trên:** so `run_parallel/run_sequential/_run_stage`,
   BenchmarkAdapter/RunView/Proposer với ExperimentService/Trial/Operation. Tính
   đủ dependency, synchronous ThreadPoolExecutor/filesystem lifetime, cancellation,
   lease/restart/replay, ledger/usage, consumer migration/qualification/test/review.
   Nếu thay toàn lõi tăng công, giữ owner/state machine Javis và lấy thuật toán
   độc lập; không giữ hai executor/ledger authoritative trùng nhau.
4. Mỗi đơn vị ghi bảng ngắn trước code: file/hàm/SHA, phần nguyên/vendor/adapter,
   phần Javis giữ, consumer, tổng công/lợi ích và test/gate. Không phân tích vô hạn
   làm chậm tích hợp hiện tại. Sớm làm lát cắt fixture chạy được để kiểm adapter;
   scaffold không được tính tích hợp.
5. Tận dụng source/test upstream kèm kiểm contract/adapter/hành vi Javis có ý
   nghĩa. Giữ license/copyright/NOTICE/provenance/modifications; không tự lấy
   benchmark/dataset/third_party ngoài nhu cầu và giấy phép.
6. Baseline luôn trong quyết định, thua/inconclusive giữ bản cũ; không lấy
   finals-only selection_pool. Không mở mặt sửa luật chủ/model/reasoning/quyền/
   system guardrails hay tăng số vòng/candidate vượt giới hạn. Nhiều rollout
   không mặc nhiên tiết kiệm token vận hành.
7. Giữ gate owner/grant/brain/scope/source/protected content; holdout/private
   answer/secret; immutable version/config/evidence; actual Trial/Call usage và
   unknown; native source/profile/qualification; cancellation/crash/cleanup/
   concurrency/recovery; migration/old readers/history; atomic apply/revert;
   review độc lập và full required CI commit cuối. Đổi footprint phải invalidate/
   requalify, không dùng proof sai nguồn.
8. Phase1 vẫn hoàn thiện code M0–M8/kiểm kỹ thuật/mô phỏng/localhost fake được
   phép; model/account/business pilot/live canary vẫn Phase2. Reuse code không
   chứng minh chất lượng nghiệp vụ/native readiness hay cấp quyền activation.
9. Checkpoint phân biệt đã đối chiếu / dùng trực tiếp upstream / adapter /
   fixture / review và CI / gate còn mở. Chỉ báo tiết kiệm có cơ sở đo, không
   tối ưu tỷ lệ dòng copy. Lưu Goal/progress/checkpoint/code-first/reuse map,
   tự quyết kỹ thuật trong quyền hiện có, tiếp tục không hỏi lại xác nhận.

## 18. Chủ thu hẹp Goal tới M2 engineering và yêu cầu bàn giao — 24/10/2026

Quyết định trực tiếp của chủ chuyển từ chat “Xác định bước harness2 tốn thời gian”
(`01a16662-a77c-72e2-9c40-265c5659d5cc`), nhận trong phiên Goal này ngày24/10.
Mục18 **supersede** yêu cầu hoàn thành M0–M8/Phase2 trong Goal hiện tại, gồm
mục1/2/5/8/10/13/17 và mọi kế hoạch/lệnh tiếp tục cũ có phạm vi rộng hơn.
Không tạo Goal mới, không đánh dấu complete ngay lúc nhận quyết định.

1. Hoàn thiện M2A–F và D1/D2 theo hợp đồng kỹ thuật: backend/runtime/UI,
   manual apply/revert/recovery/usage/provenance cần cho M2. Reuse M0/M1 và
   M2A–C đã đạt; không triển khai lại.
2. Nghiệm thu Goal là **M2 engineering + bàn giao**, code/kiểm kỹ thuật trước.
   Không đợi hoặc khởi động real-account/model/business feasibility/pilot/canary
   để tiêu thêm quota. Chuẩn bị và kiểm mô phỏng workflow feasibility M2F;
   business/live acceptance vẫn **PENDING**, không tuyên bố hiệu quả M2.
   Mọi gate qualification kỹ thuật/source/runtime/CI/review bắt buộc của mã
   bàn giao vẫn phải đạt hoặc ghi blocker thật; không hạ gate, không báo blocked
   chỉ vì chờ CI.
3. Không mở rộng recipe/library/compose vượt phụ thuộc thật sự của M2.
   Bảo toàn code/evidence thuộc M3–M8 đã xây, chốt an toàn đơn vị đang chạy;
   phần còn lại chuyển backlog Claude. Không chạy M3–M8 trong Goal này.
4. Bàn giao bắt đầu ngay tại `docs/handoffs/claude-opus-5-5/`, cập nhật dần:
   `HANDOFF.md` là điểm vào trạng thái/gate/môi trường/quyền/khôi phục;
   `NEXT-PROMPT.md` là prompt ngắn cho Claude Opus5.5. Có roadmap M3–M8,
   phần làm trước, actual Google vendor/adapter/SHA/license/provenance và các
   addendum test theo ảnh hưởng/thay chọn lọc/code-first/compose-library reuse.
5. Ghi evidence theo actual commit/source; early Linux/scoped/mock không thay
   full final-head CI/review/native qualification. Liệt kê invalidated/chưa
   verified. Khi kết thúc phải settle/dọn đúng ownership mọi process/reservation/
   workspace của Goal; không để helper/model chạy ngầm.
6. Không đưa secret/key/token/credential/plaintext private vào bàn giao.
   Không xóa/di chuyển worktree hoặc key, không mass-copy private blobs.
   Giữ ignored lịch sử/khôi phục và ghi vị trí/trạng thái an toàn.
7. Commit docs/bàn giao và cập nhật tới actual final M2 state; tích hợp PR theo
   quyền/CI/review đã có, bảo toàn checkout chính bẩn và nhánh chat khác.
   Sau khi đạt scope mới trả đường dẫn tuyệt đối HANDOFF/NEXT-PROMPT,
   release/PR/commit và pending real-test gates rồi mới complete Goal.

Chủ đã cho phép thay scope và bàn giao, không hỏi lại xác nhận thông thường.
Đổi coding assistant sang Claude Opus5.5 không đổi engine/model/reasoning của
Javis và không cấp quyền thử thật/deploy/restart/activation. API Goal hiện có
chỉ create/get/update-status, không có objective-update; giữ một Goal ACTIVE,
dùng mục18 và checkpoint làm scope có hiệu lực, không tạo Goal thay thế.


## 19. Chủ giao lại M0–M8 cho phiên Claude Opus 5.5, 25/10/2026

Lệnh trực tiếp của chủ trong phiên Claude Code ngày 25/10: đọc và thực hiện toàn bộ
file này, hoàn thành cải tiến agent và skill từ M0 đến M8, kiểm tra phần phiên
ChatGPT làm dở do hết token rồi tiếp tục. Lệnh này mới hơn mục18, nên mở lại phạm
vi M0–M8; mục18 vẫn giữ làm lịch sử bàn giao. Thứ tự giữ nguyên: chốt M2 trước,
rồi M3–M8 theo phụ thuộc mục23 của spec. Các giới hạn quyền ở mục3, 6, 7, 13 vẫn
nguyên: không chạy tài khoản/model thật, pilot, canary live, deploy/restart hay bật
activation trên brain thật nếu chủ chưa cấp riêng. Tiến độ ghi ở progress, mục
"Checkpoint Claude".
