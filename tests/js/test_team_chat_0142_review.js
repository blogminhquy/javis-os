// 0.142.0, đối chiếu goal-claude-v2 và audit: picker @ (không dấu, phím, token, email, nhân dạng theo mã), nút xử lý
// theo từng loại lỗi của lượt trả lời, dòng "Bạn + N trợ lý", hộp chọn kiểu Zalo (Chưa có tag, ảnh ghép, Đã tham gia,
// Điều phối trên chip, bỏ điều phối báo rõ, đang tải/lỗi tải), kết nối lại tải lại nhóm đang mở.
//
//     python tests/run.py --js team_chat_0142_review -v
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const TM = require(path.join(ROOT, "dashboard", "teams.js"));
const TP = require(path.join(ROOT, "dashboard", "team-picker.js"));
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));
const appJs = fs.readFileSync(path.join(ROOT, "dashboard", "app.js"), "latin1");
const teamsJs = fs.readFileSync(path.join(ROOT, "dashboard", "teams.js"), "utf8");
const css = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");
TP.setStrings(vi);

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

// ───────────── gợi ý @: không dấu, đầu từ bất kỳ, vai ─────────────
const mem = [
  { agent_key: "ag_lan", slug: "lan", name: "Lân Nguyễn", title: "Chăm khách", status: "active" },
  { agent_key: "ag_la", slug: "lan-anh", name: "Lan Anh", title: "Viết bài", status: "active" },
  { agent_key: "ag_one", slug: "one", name: "One 🚀", status: "active" },
  { agent_key: "ag_one2", slug: "one-2", name: "One 🚀", status: "active" },
  { agent_key: "ag_cu", slug: "cu", name: "Cũ", status: "left" },
];
const keys = (l) => l.map((m) => m.agent_key).join();
check("tìm KHÔNG DẤU: 'lan' ra cả Lân và Lan Anh", keys(TM.mentionMatches(mem, "lan", [])) === "ag_lan,ag_la");
check("khớp đầu từ bất kỳ: 'anh' ra Lan Anh, 'nguyen' ra Lân Nguyễn",
  keys(TM.mentionMatches(mem, "anh", [])) === "ag_la" && keys(TM.mentionMatches(mem, "nguyen", [])) === "ag_lan");
check("tìm theo vai: 'cham' ra người chăm khách", keys(TM.mentionMatches(mem, "cham", [])) === "ag_lan");
check("người đã rời không được gợi ý; người đã gọi bị bỏ", keys(TM.mentionMatches(mem, "cu", [])) === "" &&
  keys(TM.mentionMatches(mem, "lan", ["ag_lan"])) === "ag_la");
check("tìm chữ dựng tổ hợp (NFD) vẫn khớp", keys(TM.mentionMatches(mem, "Lân Ng".normalize("NFD"), [])) === "ag_lan");

// ───────────── nhân dạng theo mã: lựa chọn từ gợi ý thắng tên ─────────────
let sc = TM.mentionScan("@One 🚀 xem giúp", mem, [{ key: "ag_one2", label: "One 🚀" }]);
check("tên trùng có emoji, chọn bản 2 trong gợi ý: gọi đúng bản 2", sc.keys.join() === "ag_one2" && !sc.ambiguous.length,
  JSON.stringify(sc));
sc = TM.mentionScan("@Lan Anh xem", mem, [{ key: "ag_la", label: "Lan Anh" }]);
check("chọn Lan Anh: gọi Lan Anh", sc.keys.join() === "ag_la");
sc = TM.mentionScan("@Lan xem", mem, [{ key: "ag_la", label: "Lan Anh" }]);
check("sửa token '@Lan Anh' thành '@Lan': lựa chọn cũ mất, không gọi Lan Anh nữa", sc.keys.indexOf("ag_la") < 0,
  JSON.stringify(sc));
sc = TM.mentionScan("xem giúp", mem, [{ key: "ag_la", label: "Lan Anh" }]);
check("xoá token: bỏ gọi", sc.keys.length === 0);
sc = TM.mentionScan("@Lân Nguyễn".normalize("NFD") + " ơi", mem, [{ key: "ag_lan", label: "Lân Nguyễn" }]);
check("chữ gõ bằng bộ gõ tổ hợp (NFD) vẫn khớp token đã chọn (NFC)", sc.keys.join() === "ag_lan", JSON.stringify(sc));
sc = TM.mentionScan("@Cũ ơi", mem, [{ key: "ag_cu", label: "Cũ" }]);
check("người đã rời: lựa chọn cũ không gọi được", sc.keys.length === 0);
check("email không phải mention, không mở gợi ý", TM.mentionScan("gửi ho@lan.vn", mem, []).keys.length === 0 &&
  TM.emailBefore("gửi ho@lan") === true && TM.emailBefore("@lan") === false && TM.emailBefore("xin @lan") === false);
const rm = TM.removeMention("@Lan Anh và @One 🚀 làm", mem, [{ key: "ag_la", label: "Lan Anh" }, { key: "ag_one", label: "One 🚀" }], "ag_la");
check("bấm x trên token: xoá đúng token trong chữ và bỏ lựa chọn", rm.text === "và @One 🚀 làm" &&
  rm.picked.length === 1 && rm.picked[0].key === "ag_one", JSON.stringify(rm));
const calls = TM.callsHtml(["ag_la"], [{ agent_key: "ag_la", name: "<b>Lan</b>", slug: "la" }]);
check("hàng Gọi: token riêng có nút bỏ gọi, tên escape", calls.includes('data-unmention="ag_la"') &&
  calls.includes("@&lt;b&gt;Lan&lt;/b&gt;") && calls.includes(vi["teams.calls"]));
check("khung soạn: phím lên/xuống/Enter/Tab/Escape cho gợi ý, không gửi khi đang chọn, bỏ qua bộ gõ (IME)",
  /function sugKey\(e\)[\s\S]{0,300}e\.isComposing \|\| e\.keyCode === 229/.test(teamsJs) &&
  /ArrowDown[\s\S]{0,400}pickMention\(S\.sugKeys/.test(teamsJs) &&
  /classList\.contains\("tm-input"\) && sugKey\(e\)\) return;/.test(teamsJs) &&
  teamsJs.indexOf('contains("tm-input") && sugKey(e)') < teamsJs.indexOf('if (e.key === "Escape" && S.side)'));
check("gợi ý là listbox có aria-activedescendant", teamsJs.includes('role="listbox"') && teamsJs.includes("aria-activedescendant"));

// ───────────── nút xử lý theo từng loại lỗi ─────────────
const members = [{ agent_key: "ag_lan", slug: "lan", name: "Lan", status: "active" }];
const row = (x) => TM.replyStatusHtml({ id: 7, replies: [Object.assign({ status: "error", attempt: 1 }, x)] },
  { members: members, authors: {}, retrying: {}, leaderKey: "ag_lan" });
let h = row({ agent_key: "ag_lan", reason: "timeout", detail: "10" });
check("timeout: nói số phút, có Đổi model và Thử lại", h.includes("Quá 10 phút") && h.includes('data-reply-act="agent"')
  && h.includes("tm-reply-retry"), h);
h = row({ agent_key: "ag_lan", reason: "auth", detail: "token hết hạn" });
check("lỗi đăng nhập: mở trang Models", h.includes('data-reply-act="models"') && h.includes(vi["teams.reply.why.auth"]), h);
h = row({ agent_key: "ag_lan", reason: "cap", detail: "daily_turns" });
check("hết lượt: mở giới hạn của nhóm", h.includes('data-reply-act="limits"'), h);
h = row({ agent_key: "__leader__", reason: "no_leader" });
check("chưa có điều phối: dòng 'Điều phối ... chưa có ai trả lời' kèm Chọn điều phối và Thử lại",
  h.includes(vi["teams.reply.leader_slot"]) && h.includes('data-reply-act="leader"') && h.includes('data-retry-key="__leader__"'), h);
h = row({ agent_key: "ag_lan", reason: "member_left" });
check("điều phối đã rời: Chọn điều phối, không Thử lại", h.includes('data-reply-act="leader"') && !h.includes("tm-reply-retry"), h);
h = row({ agent_key: "ag_lan", reason: "team_paused" });
check("nhóm tạm dừng: Chạy lại nhóm", h.includes('data-reply-act="resume"'), h);
h = TM.replyStatusHtml({ id: 8, replies: [{ agent_key: "ag_lan", status: "running", reason: "waiting_busy", detail: "Bán hàng" }] },
  { members: members, authors: {}, retrying: {} });
check("bận ở nhóm khác: 'Đang chờ ... ở nhóm Bán hàng'", h.includes("Bán hàng") && h.includes("Đang chờ"), h);
h = TM.replyStatusHtml({ id: 9, replies: [{ agent_key: "__leader__", status: "done", reason: "handed_to_leader" }] },
  { members: members, authors: {}, retrying: {} });
check("dòng chỗ trống đã giao cho điều phối: ẩn", h === "");

// ───────────── người tạo và dòng đầu nhóm ─────────────
const team = { team_id: "tm1", leader_key: "ag_lan", creator: { kind: "owner", you: true, name: "minhquy" },
  members: [{ agent_key: "ag_lan", slug: "lan", name: "Lan", status: "active", role: "leader" },
    { agent_key: "ag_m", slug: "m", name: "Minh", status: "active", role: "member" }] };
check("đầu nhóm: 'Bạn + 2 cộng sự · Lan điều phối'", TM.headLine(team) === "Bạn + 2 cộng sự · Lan điều phối", TM.headLine(team));
check("chưa có điều phối: nói rõ", TM.headLine(Object.assign({}, team, { leader_key: null })).includes(vi["teams.no_leader_short"]));
const mh = TM.membersHtml(team, [], null);
check("ngăn Nhóm: dòng Bạn (tên đăng nhập do server cấp) · Người tạo nhóm/quản lý, đứng đầu", mh.indexOf("Bạn (minhquy)") >= 0 &&
  mh.indexOf("Bạn (minhquy)") < mh.indexOf("Lan") && mh.includes(vi["teams.pick.you_role"]), mh.slice(0, 300));
check("chữ 'trưởng nhóm' trên giao diện nhóm đổi thành 'điều phối'",
  Object.keys(vi).filter((k) => k.indexOf("teams.") === 0 && /trưởng nhóm/i.test(vi[k])).length === 0 &&
  Object.keys(en).filter((k) => k.indexOf("teams.") === 0 && /\blead\b/i.test(en[k])).length === 0);

// ───────────── hộp chọn kiểu Zalo ─────────────
const roster = [
  { slug: "a", name: "An", role: "Bán hàng", tags: ["Bán hàng"], tag_keys: ["ban hang"] },
  { slug: "b", name: "Bình", role: "Nội dung", tags: [], tag_keys: [] },
  { slug: "c", name: "Chi", role: "", tags: ["Bán hàng"], tag_keys: ["ban hang"] },
];
let st = { mode: "create", query: "", tag: "", selected: [], leader: "", leaderTouched: false, name: "", desc: "" };
let html = TP.html(st, roster);
check("chip 'Chưa có tag' có số đếm", html.includes('data-pick-tag="__none"') && html.includes(vi["teams.pick.untagged"]), html);
check("lọc 'Chưa có tag' ra đúng người không tag", TP.visible(roster, Object.assign({}, st, { tag: "__none" })).map((a) => a.slug).join() === "b");
check("mô tả thu gọn (details, không mở sẵn), không có nút đổi ảnh nhóm", /<details class="tmp-desc">/.test(html) &&
  !/camera|tmp-photo/.test(html), html);
check("ảnh nhóm xem trước trống khi chưa chọn", html.includes("tmp-preview-empty"));
st = TP.toggle(TP.toggle(TP.toggle(st, "a"), "b"), "c");
html = TP.html(st, roster);
check("ảnh nhóm xem trước ghép từ người đã chọn", /tmp-preview tmp-preview-3/.test(html));
check("ba người: Điều phối mặc định người đầu, đổi ngay trên chip", st.leader === "a" && /data-pick-leader="b"/.test(html));
st = TP.setLeader(st, "c");
check("bấm Điều phối trên chip Chi", st.leader === "c" && st.leaderTouched);
st = TP.toggle(st, "c");
html = TP.html(st, roster);
check("bỏ người đang Điều phối khi còn nhiều người: để trống và BÁO RÕ, không âm thầm giao người khác",
  st.leader === "" && st.leaderDropped === true && html.includes(vi["teams.pick.leader_dropped"]), JSON.stringify(st));
st = TP.toggle(st, "b");
check("còn đúng một người: người đó điều phối, hết cảnh báo", st.leader === "a" && !st.leaderDropped);
st = TP.normalize(Object.assign({}, st, { selected: [], rosterState: "loading" }));
check("đang tải danh sách: hiện 'Đang tải', không báo 'chưa có trợ lý'",
  TP.listHtml([], Object.assign({}, st, { rosterState: "loading" })).includes(vi["teams.pick.loading"]));
check("lỗi tải: báo lỗi kèm Tải lại", /tmp-load-error[\s\S]*tmp-reload/.test(TP.listHtml([], Object.assign({}, st, { rosterState: "error" }))));
html = TP.html({ mode: "add", query: "", tag: "", selected: ["b"], exclude: ["a"] }, roster);
check("Thêm thành viên: người đã ở nhóm hiện 'Đã tham gia', không bỏ chọn được, chỉ đếm người mới",
  /data-pick-slug="a" checked disabled/.test(html) && html.includes(vi["teams.pick.joined"]) && html.includes("1 người mới"), html);
check("bấm vào người đã tham gia: không đổi lựa chọn", TP.toggle({ selected: [], exclude: ["a"] }, "a").selected.length === 0);
check("Tạo nhóm gửi mã yêu cầu chống trùng, tạo xong focus khung soạn", teamsJs.includes("client_req_id: st.reqId") &&
  /S\.focusComposer = true;[\s\S]{0,120}openTeam/.test(teamsJs) && /if \(S\.focusComposer && !off\)/.test(teamsJs));
check("chữ mới của hộp chọn và gợi ý tối thiểu 16px",
  !/\.(tm-sug-slug|tmp-chip-n|tmp-badge|tm-sug-role|tmp-lead|tm-call|tm-reply-act)[^{]*\{[^}]*font-size: 1[0-5]px/.test(css));
check("bàn phím ảo mở: hộp chọn co theo visualViewport", /body\.kb-open \.tmp-layer \{[^}]*var\(--vv-h/.test(css));

// ───────────── kết nối lại: tải lại nhóm đang mở ─────────────
check("socket nối lại phát team_resync", /if \(_daChao\) \{ try \{ window\.dispatchEvent\(new CustomEvent\("javis:team-event", \{ detail: \{ type: "team_resync" \} \}\)\)/.test(appJs));
check("trang Nhóm nhận team_resync: tải lại tin, hàng việc, nhóm", /d\.type === "team_resync"\)[\s\S]{0,260}loadMsgs\(false\); loadQueue\(\); loadTeam\(\);/.test(teamsJs));
check("Auto đổi ở nơi khác: trang Nhóm đọc lại thành viên", teamsJs.includes('addEventListener("javis:resonance-agents-changed"'));

// ───────────── review độc lập 0.142.0 ─────────────
const mem2 = [
  { agent_key: "k_lan", slug: "lan", name: "Lan", status: "active" },
  { agent_key: "k_la", slug: "lan-anh", name: "Lan Anh", status: "active" },
];
sc = TM.mentionScan("@Lan Anh làm giúp", mem2, [{ key: "k_lan", label: "Lan" }, { key: "k_la", label: "Lan Anh" }]);
check("review #1: chọn Lan rồi xoá, chọn lại Lan Anh: lựa chọn MỚI giữ token, gọi Lan Anh", sc.keys.join() === "k_la",
  JSON.stringify(sc));
sc = TM.mentionScan("@One 🚀 xem", mem, [{ key: "ag_one", label: "One 🚀" }, { key: "ag_one2", label: "One 🚀" }]);
check("review #1: hai trợ lý trùng tên, chọn lại bản sau: gọi bản sau", sc.keys.join() === "ag_one2", JSON.stringify(sc));
let rm2 = TM.removeMention("@Lan Anh và @Lan", mem2, [], "k_lan");
check("review #4: bỏ gọi Lan không phá token '@Lan Anh' của người khác", rm2.text === "@Lan Anh và ", JSON.stringify(rm2));
rm2 = TM.removeMention("@Lan Anh và @Lan", mem2, [], "k_la");
check("review #4: bỏ gọi Lan Anh chỉ xoá token của Lan Anh", rm2.text === "và @Lan", JSON.stringify(rm2));
check("review #9: bỏ điều phối thì nút Tạo nhóm khoá tới khi chọn lại",
  !TP.canSubmit({ mode: "create", selected: ["a", "b"], leader: "", leaderDropped: true }) &&
  TP.canSubmit({ mode: "create", selected: ["a", "b"], leader: "a" }) && TP.canSubmit({ mode: "add", selected: ["a"] }));
const ajJs = fs.readFileSync(path.join(ROOT, "dashboard", "agent-jobs.js"), "utf8");
check("review #3: tab Công việc không vẽ lại khi đang gõ form Giao việc hay đang dùng IME",
  /function typing\(\)[\s\S]{0,300}st\.ui\.assignOpen \|\| !!host\._ajComposing/.test(ajJs) &&
  /if \(typing\(\)\) \{ schedule\(\); return; \}/.test(ajJs) && ajJs.includes('addEventListener("compositionstart"'));
const wsJs = fs.readFileSync(path.join(ROOT, "dashboard", "workspace.js"), "utf8");
check("review #6: đếm việc chỉ khi danh sách trợ lý đang hiện và tab đang mở",
  /function henDemViec\(\) \{[\s\S]{0,400}S\.loai !== "agent"[\s\S]{0,80}document\.hidden/.test(wsJs));
check("lọc theo việc đã xong: thanh lọc và nhãn hiện tên việc (không hiện mã)",
  /S\.filterTask && r\.j\.task && r\.j\.task\.id\)[\s\S]{0,200}S\.taskTitles\[r\.j\.task\.id\]/.test(teamsJs));

// ───────────── rà soát trước khi phát hành (giao diện) ─────────────
h = TM.replyStatusHtml({ id: 3, replies: [{ agent_key: "ag_7f3a", status: "error", reason: "member_left" }] },
  { members: [], authors: { ag_7f3a: { name: "Lan" } }, retrying: {} });
check("người đã rời nhóm: dòng trạng thái hiện TÊN (sổ tác giả), không hiện mã", h.includes("<b>Lan</b>") && !h.includes("ag_7f3a</b>"), h);
check("Thử lại: phản hồi 200 có trạng thái mới thì mở khoá nút, không chỉ trông vào gói WS",
  /x\.agent_key === d\.retryKey && x\.status !== "error"\) delete S\.retrying\[rk\]/.test(teamsJs));
check("hộp chọn: chọn xong focus lại đúng ô, Escape đóng được cả khi focus ở ngoài",
  /function pickToggle\(slug\)[\s\S]{0,900}back\.focus\(\{ preventScroll: true \}\)/.test(teamsJs) &&
  /document\.addEventListener\("keydown", pickEsc, true\)/.test(teamsJs) && /document\.removeEventListener\("keydown", pickEsc, true\)/.test(teamsJs));
// 0.189.1: chọn tới người thứ ba ở dưới thấp thì cả hộp chọn bị cuộn (tiêu đề trôi mất, đáy hộp trống). Ô tick ẩn phải nằm
// trong dòng của nó (.tmp-row position: relative) và hộp không được cuộn bằng code (overflow: clip).
const consoleCss = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");
check("hộp chọn không bị cuộn cả khung khi focus lại ô tick",
  /\.tmp-row \{ position: relative;/.test(consoleCss) && /\.tmp-dialog \{[^}]*overflow: hidden; overflow: clip;/.test(consoleCss));
check("ghi chú cho chủ đọc không bị lọc (chỉ lọc mã như daily_cap)", teamsJs.includes("return !/^[a-z_]+$/.test(n);"));
const consoleJs = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");
check("Vị trí file ở trang Cộng sự: mở trang Tệp tin (không còn tab Thư mục)",
  /if \(workspace\) \{[\s\S]{0,300}window\.JavisNav\.go\("files"\)/.test(consoleJs) && !/\[data-rtab="files"\]'\)\?\.click\(\)/.test(consoleJs));

// ───────────── i18n đủ hai thứ tiếng ─────────────
const need = ["teams.calls", "teams.uncall", "teams.head_people", "teams.head_leader", "teams.reply.why.timeout",
  "teams.reply.why.auth", "teams.reply.why.no_leader", "teams.reply.act.models", "teams.reply.act.agent",
  "teams.reply.act.limits", "teams.reply.act.leader", "teams.reply.act.resume", "teams.reply.waiting_busy_in",
  "teams.pick.untagged", "teams.pick.joined", "teams.pick.leader_dropped", "teams.pick.loading", "teams.pick.load_error",
  "teams.pick.count_new", "teams.pick.desc_add", "teams.pick.preview"];
check("khoá mới có ở vi và en", need.every((k) => vi[k] && en[k]), need.filter((k) => !vi[k] || !en[k]).join());
check("không còn 'cộng hưởng' trong chữ tiếng Việt của Auto", !/cộng hưởng/i.test(vi["resonance.settings_title"] + vi["resonance.st_feature_off"]));

console.log();
if (fails) { console.log("ĐỎ " + fails + " mục"); process.exit(1); }
console.log("XANH");
