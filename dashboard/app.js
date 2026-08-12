// Lấy host động → mở từ máy khác / đổi cổng vẫn chạy (không hardcode localhost)
const WS_ORIGIN = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}`;
const WS_URL = `${WS_ORIGIN}/ws`;
let ws = null;
let isProcessing = false;      // = phiên ĐANG XEM có lượt chạy không (dẫn xuất từ turns[savedSessionId])
let cancelledTurn = false;     // (giữ để tương thích - không còn dùng)
// ĐA HỘI THOẠI SONG SONG: mỗi phiên giữ trạng thái stream RIÊNG, định tuyến theo session_id. Mở
// "hội thoại mới" KHÔNG giết phiên đang chạy - nó chạy nền + tự lưu, vào Lịch sử bấm lại xem tiếp.
const turns = {};              // sid -> { text, bubble, spoke, running }
if (!window.JavisRunning) window.JavisRunning = new Set();   // sid đang generate → sidebar hiện icon đang chạy
function newSid() { try { return crypto.randomUUID().replace(/-/g, ""); } catch (e) { return Date.now().toString(36) + Math.random().toString(36).slice(2, 10); } }
function setSessionRunning(sid, on) {
  if (!sid) return;
  if (on) window.JavisRunning.add(sid); else window.JavisRunning.delete(sid);
  try { if (window.JavisChatSide && window.JavisChatSide.refresh) window.JavisChatSide.refresh(); } catch (e) {}
}

// Lưu & khôi phục phiên gần nhất (hội thoại + số liệu + session Claude)
const SESSION_KEY = "javis.session.v1";
let convo = [];            // [{role:"user"|"javis", text, atts}]
let savedSessionId = null; // session_id của Claude để resume sau khi F5
const stopBtn = document.getElementById("stopBtn");
let stopTag = null;        // tag phiên chat server phát qua message hello → Stop chỉ ngắt phiên MÌNH

function updateStopBtn() {
  const active = isProcessing || voice.isSpeaking();
  stopBtn.style.display = active ? "flex" : "none";
  sendBtn.style.display = active ? "none" : "flex";
}

// Đồng bộ nút gửi/dừng + cờ isProcessing theo lượt của phiên ĐANG XEM (savedSessionId).
function syncActiveUI() {
  const t = savedSessionId ? turns[savedSessionId] : null;
  isProcessing = !!(t && t.running);
  sendBtn.disabled = isProcessing;
  // Đang trả lời thì khoá nút gửi lại của mọi tin (CSS .transcript.busy) cho khỏi chồng lượt.
  try { chatArea.classList.toggle("busy", isProcessing); } catch (e) {}
  updateStopBtn();
}

function stopCurrent() {
  voice.stopSpeaking();
  const sid = savedSessionId;
  // Dừng ĐÚNG phiên đang xem (phiên nền khác vẫn chạy). Server huỷ lượt + gửi turn_done về.
  if (sid && ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ action: "stop", session_id: sid }));
  } else if (sid) {
    // WebSocket đang reconnect vẫn Stop được qua HTTP; job không còn phụ thuộc connection cũ.
    fetch("/stop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sid }),
    }).catch(() => {});
  }
  hideActivity();
  if (sid && turns[sid]) turns[sid].running = false;
  setSessionRunning(sid, false);
  if (!handsFreeActive()) setOrbState("", "SẴN SÀNG");
  syncActiveUI();
}
function handsFreeActive() { return typeof handsFree !== "undefined" && handsFree; }
function currentBrainPath() {
  const v = document.getElementById("graphSource").value;
  return v.startsWith("path:") ? v.slice(5) : "brain";
}

// Elements
const chatArea = document.getElementById("chatArea");
const chatInput = document.getElementById("chatInput");
const sendBtn = document.getElementById("sendBtn");
const voiceBtn = document.getElementById("voiceBtn");
const ttsToggle = document.getElementById("ttsToggle");
const voiceInterim = document.getElementById("voiceInterim");
const orbState = document.getElementById("orbState");

// Thanh trạng thái đã bỏ tên workspace + ngày tháng (0.9.195) - element có thể không còn,
// nên mọi truy cập phải guard để trang không chết trắng nếu thiếu.
fetch("/config").then(r => r.json()).then(cfg => {
  const wn = document.getElementById("workspaceName");
  if (wn) wn.textContent = cfg.workspace_name || "Javis OS";
}).catch(() => {});

// ============================================
// Orb state
// ============================================
function setOrbState(state, label) {
  orbState.className = "orb-state " + state;
  orbState.textContent = label;
  const thinking = state === "thinking";
  _thinkingActive = thinking;
  if (javisGraph) javisGraph.setThinking(thinking);
}

// ============================================
// Voice
// ============================================
const voice = new JavisVoice({
  lang: "vi-VN",
  onStart: () => {
    voiceBtn.classList.add("recording");
    setOrbState("listening", handsFree ? "ĐANG NGHE • LUÔN" : "ĐANG NGHE");
    voiceInterim.textContent = "";
  },
  onInterim: (text) => { voiceInterim.textContent = text; },
  onTranscript: (text) => {
    voiceBtn.classList.remove("recording");
    voiceInterim.textContent = "";
    if (text) sendMessage(text);
  },
  onEnd: () => {
    voiceBtn.classList.remove("recording");
    // Hands-free: giữ trạng thái chờ nghe lại, đừng reset về SẴN SÀNG cho đỡ nháy
    if (!isProcessing && !handsFree) setOrbState("", "SẴN SÀNG");
  },
  onError: (err) => {
    voiceBtn.classList.remove("recording");
    setOrbState("", "SẴN SÀNG");
    if (err === "not-allowed") alert("Anh cần cấp quyền microphone cho trang này.");
    else if (err === "not-supported") alert("Trình duyệt không hỗ trợ nhận giọng. Dùng Chrome/Edge.");
  }
});

// ============================================
// WebSocket
// ============================================
function connect() {
  ws = new WebSocket(WS_URL);
  ws.onopen = () => updateSysStatus("active");
  ws.onclose = () => { updateSysStatus("error"); setTimeout(connect, 3000); };
  ws.onerror = () => updateSysStatus("error");
  ws.onmessage = (e) => handleMessage(JSON.parse(e.data));
}

function handleMessage(data) {
  // Server chào khi kết nối: đồng bộ các job vẫn đang chạy. Job thuộc server,
  // không thuộc WebSocket nên đóng/F5 tab rồi mở lại vẫn xem và Stop được.
  if (data.type === "hello") {
    stopTag = data.stop_tag || null;
    if (window.JavisRunning) window.JavisRunning.clear();
    Object.keys(turns).forEach(sid => { if (turns[sid]) turns[sid].running = false; });
    (data.running || []).forEach(job => {
      const sid = job.session_id;
      if (!sid) return;
      const old = turns[sid] || {};
      turns[sid] = {
        text: (job.text || old.text || ""),
        bubble: old.bubble || null,
        spoke: !!old.spoke,
        running: true,
      };
      setSessionRunning(sid, true);
    });
    syncActiveUI();
    notifySessions();
    return;
  }

  // Định tuyến theo session_id: sự kiện của phiên ĐANG XEM thì render trực tiếp; phiên nền thì
  // chỉ tích luỹ vào buffer + đánh dấu "đang chạy" ở Lịch sử (server đã tự lưu vào DB).
  const sid = data.session_id || null;
  const isActive = !!sid && sid === savedSessionId;
  const t = sid ? (turns[sid] || (turns[sid] = { text: "", bubble: null, spoke: false, running: true })) : null;

  if (data.type === "push") {
    // Tin do việc chạy NỀN đẩy vào (việc Kanban / loop / nhắc hẹn xong), không thuộc lượt
    // hỏi-đáp nào. KHÔNG đụng turns[sid]: lượt đang chạy (nếu có) vẫn stream bình thường,
    // tin này chỉ chèn thêm một bong bóng. Server đã lưu vào kho phiên nên F5 vẫn còn.
    if (isActive) {
      const el = appendJavisMessage(data.content || "");
      recordTurn("javis", data.content || "", null, null);
      scrollBottom();
      if (voice.ttsEnabled) voice.enqueueSpeak(data.content || "");
      try { if (el) el.scrollIntoView({ block: "nearest" }); } catch (e) {}
    }
    // Đang xem phiên KHÁC thì tin vẫn nằm trong kho phiên (server ghi trước khi bắn), chỉ là
    // không hiện ở khung đang mở. Làm tươi Lịch sử để phiên đó nổi lên - không thì kết quả
    // nằm im trong DB và người dùng không có cách nào biết là đã có.
    notifySessions();
    // Một việc nền vừa báo xong = hàng đợi vừa đổi. Hỏi lại ngay thay vì đợi hết nhịp 6 giây,
    // để dải trạng thái không còn khoe một việc vừa kết thúc.
    try { if (window.JavisBackground) window.JavisBackground.refresh(); } catch (e) {}
    return;
  }
  if (data.type === "status") {
    if (t) t.running = true;
    setSessionRunning(sid, true);
    if (isActive) { setOrbState("thinking", "ĐANG SUY NGHĨ"); showActivity(escapeHtml(data.content || "")); syncActiveUI(); }
  } else if (data.type === "tool_call") {
    if (data.tool) trackMCP(data.tool);
    if (isActive) showActivity(escapeHtml(data.content || ""));
  } else if (data.type === "tool_result") {
    if (isActive) showActivity(Icons.msg("check", "Nhận data - đang phân tích...", { cls: "ic-ok" }));
  } else if (data.type === "stream") {
    if (!t) return;
    t.text += (data.content || "");
    if (isActive) {
      if (!t.bubble) { t.bubble = createStreamingBubble(); showActivity(Icons.msg("pen-line", "Đang soạn câu trả lời...")); }
      t.bubble.querySelector(".bubble").innerHTML = markdownToHtml(t.text);
      scrollBottom();
      // Đọc NGAY đoạn trung gian (chỉ đọc phiên đang xem). OpenRouter gửi tts:false → đọc 1 lần ở cuối.
      if (voice.ttsEnabled && data.tts !== false) {
        setOrbState("speaking", "ĐANG NÓI");
        const safeChunk = (data.content || "").replace(/<!--[\s\S]*/, "");
        if (safeChunk) voice.enqueueSpeak(safeChunk);
        t.spoke = true;
      }
    }
  } else if (data.type === "response") {
    const { clean: askClean, ask } = window.JavisAsk.extract(data.content || "");
    const finalText = askClean || (t && t.text) || "";
    const shownText = finalText || "_(không có nội dung trả về - thử lại hoặc đổi model)_";
    if (t) t.text = shownText;
    if (isActive) {
      hideActivity();
      let msgEl = t && t.bubble;
      if (!msgEl) msgEl = appendJavisMessage(shownText);
      else msgEl.querySelector(".bubble").innerHTML = markdownToHtml(shownText);
      if (ask) window.JavisAsk.render(msgEl, ask, true);   // chip chỉ mọc khi lượt xong
      if (data.engine) setEngineBadge(data.engine, data.model);   // sự thật engine+model của lượt này
      _renderCtxLine(msgEl, data);   // lượt này đi đường nào, tốn bao nhiêu
      if (finalText.trim()) recordTurn("javis", finalText, null, ask);
      if (voice.ttsEnabled && t && !t.spoke && finalText) { setOrbState("speaking", "ĐANG NÓI"); voice.speak(finalText); }
      else if (!voice.ttsEnabled) setOrbState("", "SẴN SÀNG");
      maybeAutoLearn();
    }
    refreshUsage();     // cập nhật panel Mức dùng sau mỗi lượt
  } else if (data.type === "error") {
    if (isActive) { hideActivity(); appendJavisError(data.content); setOrbState("", "SẴN SÀNG"); }
  } else if (data.type === "system") {
    if (isActive) appendJavisMessage(data.content);
  } else if (data.type === "turn_done") {
    // Lượt của phiên này kết thúc (xong / lỗi / bị dừng): bỏ cờ chạy, dọn buffer, refresh Lịch sử.
    if (t) t.running = false;
    setSessionRunning(sid, false);
    if (isActive) syncActiveUI();
    if (sid) delete turns[sid];
    notifySessions();
    // Lượt vừa xong có thể đã giao việc nền. Đây là ĐÚNG khoảnh khắc người dùng đọc câu trả
    // lời "em đã giao 3 việc" và tự hỏi nó có chạy thật không - dải phải trả lời được ngay.
    try { if (window.JavisBackground) window.JavisBackground.refresh(); } catch (e) {}
  }
}

// ============================================
// Messages
// ============================================
function sendMessage(text) {
  const msg = (text || chatInput.value).trim();
  const atts = pendingAttachments.filter(a => a.path);  // chỉ file đã upload xong
  // Lệnh / : session-command chạy tại chỗ; skill-command bung thành lời gọi skill.
  const _slash = (window.JavisSlash && msg) ? window.JavisSlash.route(msg) : { type: "passthrough" };
  if (_slash.type === "session") {
    chatInput.value = ""; chatInput.style.height = "auto";
    if (_slash.cmd === "stop") { try { stopCurrent(); } catch (e) {} }
    else { try { newChat(); } catch (e) {} }   // new | reset -> hội thoại mới trên web
    return;
  }
  if ((!msg && atts.length === 0) || !ws || ws.readyState !== WebSocket.OPEN) return;
  if (!savedSessionId) {
    savedSessionId = newSid();                           // hội thoại mới → mint id để định tuyến
    // Đang mở một project ở cột Lịch sử thì hội thoại mới rơi thẳng vào project đó, khỏi phải
    // gắn tay. Gắn NGAY tại đây vì đây là chỗ duy nhất biết "id này vừa được sinh ra".
    try { if (window.JavisProjects) window.JavisProjects.claim(savedSessionId); } catch (e) {}
  }
  const sid = savedSessionId;
  if (turns[sid] && turns[sid].running) return;          // phiên này đang trả lời → chưa gửi tiếp
  // Đang BUNG NÃO toàn màn (mobile) mà gửi tin thì thu lại: ở trạng thái đó khung chat bị
  // ẩn hẳn, không thu thì người dùng gõ xong không thấy câu trả lời hiện ở đâu cả. Bấm hộ
  // đúng cái nút để đi chung một đường (đổi aria + canh lại khung đồ thị).
  if (document.body.classList.contains("brain-max")) {
    try { document.getElementById("brainMaxBtn").click(); } catch (e) {}
  }
  voice.stopSpeaking();
  window.JavisAsk.freezeAll();   // trả lời rồi thì chip của lượt trước hết bấm được
  appendUserMessage(msg, atts);
  recordTurn("user", msg, atts.map(a => ({ name: a.name, kind: a.kind })));

  // Soạn message gửi Javis (kèm đường dẫn file trong Sources)
  const _isSkill = _slash.type === "skill";
  let outMsg = _isSkill ? _slash.message : msg;
  if (atts.length) {
    const lines = atts.map(a => `- ${a.path}`).join("\n");
    const src = atts[0].sources || "", attDir = atts[0].attachments || "";
    if (_isSkill) {
      // Với lệnh skill (vd /notes): đưa path như dữ liệu, để chính skill quyết định lưu.
      outMsg = `[File đính kèm (đường dẫn), Sources="${src}", Attachments="${attDir}":\n${lines}]\n\n${_slash.message}`;
    } else {
      const ctx =
        `[File đính kèm để ĐỌC (đường dẫn):\n${lines}\n` +
        `Mặc định: chỉ đọc file rồi trả lời, KHÔNG tự lưu đi đâu.\n` +
        `CHỈ khi user yêu cầu rõ (vd "lưu vào source", "ingest", "ghi vào second brain") thì mới: ` +
        `chuyển thành .md (ảnh thì đọc hiểu + mô tả) lưu vào Sources="${src}" (ảnh gốc chuyển vào Attachments="${attDir}"), kèm frontmatter source.]`;
      outMsg = msg
        ? `${ctx}\n\n${msg}`
        : `${ctx}\n\nHãy đọc (các) file trên và phản hồi / tóm tắt nội dung chính.`;
    }
  }
  // File đang ghim đi TRƯỚC mọi thứ: nó là ngữ cảnh nền của cả lượt, không phải dữ liệu
  // đính kèm một lần. Gửi lại mỗi lượt vì engine API dựng lại payload từ SQLite mỗi lần,
  // không giữ trạng thái "đang mở file nào" giữa các lượt.
  if (pinnedNote) {
    outMsg = `[FILE ĐANG MỞ trong trình sửa của Javis: ${pinnedNote.abs}\n`
      + `Đây là file người dùng ĐANG LÀM VIỆC TRÊN ĐÓ - coi như đầu vào của cuộc trò chuyện này. `
      + `Đọc nó trước khi trả lời. Khi được yêu cầu sửa/viết thêm/dọn lại mà không nói rõ file nào `
      + `thì ghi thẳng vào chính file này.]\n\n${outMsg}`;
  }

  chatInput.value = ""; chatInput.style.height = "auto";
  clearAttachments();
  turns[sid] = { text: "", bubble: null, spoke: false, running: true };
  setSessionRunning(sid, true);
  setOrbState("thinking", "ĐANG SUY NGHĨ");
  showActivity("Javis đang suy nghĩ...");   // hiện NGAY trong khung chat, không đợi server báo
  syncActiveUI();
  ws.send(JSON.stringify({ message: outMsg, brain: currentBrainPath(), session_id: sid }));
}
// Chip lựa chọn (chat-ask.js) gửi đáp án qua đây: bấm chip = y như người dùng gõ tay nhãn đó.
window.JavisSend = sendMessage;

// ============================================
// Lưu / khôi phục phiên
// ============================================
function persistSession() {
  try {
    localStorage.setItem(SESSION_KEY, JSON.stringify({
      convo: convo.slice(-200),
      sessionId: savedSessionId,
      // Brain của phiên đang mở. Ảnh trong tin nhắn là đường dẫn TƯƠNG ĐỐI nên phải biết
      // gốc là brain nào; thiếu nó thì F5 xong đổi brain là ảnh cũ tro sai chỗ rồi 404.
      brain: (typeof currentBrainPath === "function" ? currentBrainPath() : ""),
      savedAt: Date.now(),
    }));
  } catch (e) {}
}
function recordTurn(role, text, atts, ask) {
  convo.push({ role, text: text || "", atts: atts || [], ask: ask || null, ts: Date.now() });
  if (convo.length > 200) convo = convo.slice(-200);
  persistSession();
}
function restoreSession() {
  let s = null;
  try { s = JSON.parse(localStorage.getItem(SESSION_KEY) || "null"); } catch (e) {}
  if (!s) return;
  convo = Array.isArray(s.convo) ? s.convo : [];
  savedSessionId = s.sessionId || null;
  // Dựng lại bong bóng hội thoại
  convo.forEach((t, i) => {
    // t.ts vắng mặt ở tin lưu từ trước bản này -> truyền 0 để ẩn giờ thay vì hiện giờ F5.
    if (t.role === "user") { appendUserMessage(t.text, t.atts || [], t.ts || 0); return; }
    // t.brain vắng ở tin lưu từ trước bản này -> rơi về brain của cả phiên, rồi mới tới
    // brain đang chọn. Không có thì hành vi y như cũ, không hỏng thêm gì.
    const el = appendJavisMessage(t.text, t.ts || 0, t.brain || s.brain);
    // Chip chỉ sống lại ở tin CUỐI: có tin sau nó nghĩa là câu hỏi đã được trả lời rồi.
    if (t.ask) window.JavisAsk.render(el, t.ask, i === convo.length - 1);
  });
  if (convo.length) scrollBottom(true);
  notifySessions();   // panel Lịch sử tô đúng phiên đang xem thay vì không tô cái nào
  syncActiveUI();
}

// ============================================
// Phiên hội thoại lưu DB (panel Lịch sử - sessions-ui.js gọi qua window.JavisSessions)
// ============================================
async function openStoredSession(id) {
  try {
    const sess = await (await fetch(`/sessions/${encodeURIComponent(id)}`)).json();
    if (!sess || sess.error) return;
    convo = [];
    hideActivity();
    chatArea.innerHTML = "";
    (sess.messages || []).forEach(m => {
      const ts = m.ts ? Math.round(m.ts * 1000) : 0;   // server lưu epoch giây (sessions.py)
      if (m.role === "user") { appendUserMessage(m.content || "", [], ts); convo.push({ role: "user", text: m.content || "", atts: [], ts }); }
      // sess.brain: server LƯU SẴN brain của phiên (cột brain trong bảng sessions). Trước đây
      // vứt đi nên ảnh trong hội thoại cũ luôn ghép với brain đang chọn - mở hội thoại của
      // brain khác là ảnh hỏng hết. Giữ luôn vào convo để lần khôi phục sau còn dùng.
      else if (m.role === "assistant") { appendJavisMessage(m.content || "", ts, sess.brain); convo.push({ role: "javis", text: m.content || "", atts: [], ts, brain: sess.brain }); }
    });
    savedSessionId = id;          // lượt gửi tiếp theo → server resume đúng phiên này
    // Phiên này đang generate NỀN → gắn bong bóng SỐNG (kèm phần đã stream) để xem tiếp trực tiếp.
    const t = turns[id];
    if (t && t.running) {
      t.bubble = createStreamingBubble();
      if (t.text) t.bubble.querySelector(".bubble").innerHTML = markdownToHtml(t.text);
      showActivity(Icons.msg("pen-line", "Đang soạn câu trả lời..."));
      setOrbState("thinking", "ĐANG SUY NGHĨ");
    }
    persistSession();
    scrollBottom(true);
    notifySessions();
    syncActiveUI();
    // Dải việc nền đánh dấu "việc CỦA hội thoại này" theo chat_id, nên đổi phiên là nó sai
    // ngay. Xoá rồi hỏi lại thay vì để chip của phiên trước nằm lại vài giây.
    try { if (window.JavisBackground) window.JavisBackground.reset(); } catch (e) {}
  } catch (e) {}
}
// Xoá trắng khung chat về trạng thái "hội thoại mới" - dùng chung cho nút + Hội thoại mới
// và lúc ĐỔI BRAIN (không focus input để đổi brain không bật bàn phím trên mobile).
function resetChatView() {
  convo = [];
  hideActivity();          // dọn chip + timer trước khi xoá trắng khung
  chatArea.innerHTML = "";
  savedSessionId = null;
  persistSession();
  notifySessions();
  syncActiveUI();
  try { if (window.JavisBackground) window.JavisBackground.reset(); } catch (e) {}
}
function newChat() {
  // KHÔNG reset server, KHÔNG đụng lượt đang chạy của phiên khác - chúng chạy nền + tự lưu; vào
  // Lịch sử bấm lại để xem tiếp. Ở đây chỉ mở một khung trống cho hội thoại mới (mint id khi gửi).
  resetChatView();
  try { chatInput.focus(); } catch (e) {}
}
window.JavisSessions = { open: openStoredSession, new: newChat, brain: () => currentBrainPath(), current: () => savedSessionId };
// Báo các UI khác (sidebar Lịch sử trong chat workspace) biết phiên/danh sách vừa đổi
function notifySessions() { try { window.dispatchEvent(new Event("javis:sessions-changed")); } catch (e) {} }

// Hàng nút dưới bong bóng (giờ + gửi lại / sửa lại / copy). Tách sang chat-acts.js để
// test được bằng node; ở đây chỉ là lối thoát khi file đó chưa kịp nạp.
function actsHtml(role, ts, canResend) {
  return window.JavisActs ? window.JavisActs.actsHtml(role, ts, canResend) : "";
}
// Tin chỉ có ảnh (không kèm lời nhắn) thì chẳng có chữ nào để gửi lại. Ở tin của Javis
// thì cái quyết định là CÂU HỎI ngay trên nó, nên soi tin người dùng cuối cùng đã nằm
// trong khung (chatAppend chèn theo đúng thứ tự nên lúc này nó đã có mặt).
function lastUserText() {
  const els = chatArea.querySelectorAll(".msg-user");
  const el = els.length ? els[els.length - 1] : null;
  return el ? (el.dataset.text || "") : "";
}
// ts === undefined nghĩa là tin VỪA xảy ra; còn khôi phục tin cũ thì truyền ts thật
// (hoặc 0 nếu tin lưu từ trước bản này chưa có mốc giờ, khi đó phần giờ được ẩn).
function appendUserMessage(text, attachments, ts) {
  const div = document.createElement("div");
  div.className = "msg msg-user";
  div.dataset.text = text || "";   // giữ nguyên văn để gửi lại / sửa lại đúng chữ gốc
  let attHtml = "";
  if (attachments && attachments.length) {
    attHtml = `<div class="msg-attach">` + attachments.map(a =>
      a.preview
        ? `<img src="${a.preview}" alt="${escapeHtml(a.name)}">`
        : `<span class="file-tag">${ic("file-text")} ${escapeHtml(a.name)}</span>`
    ).join("") + `</div>`;
  }
  // Tin dài (>10 dòng hoặc >900 ký tự) thu gọn lại, bấm "Xem thêm" để mở
  const isLong = text && (text.split("\n").length > 10 || text.length > 900);
  const textHtml = text
    ? `<div class="utext${isLong ? " clamped" : ""}">${escapeHtml(text)}</div>` +
      (isLong ? `<button class="clamp-more" type="button">Xem thêm</button>` : "")
    : "";
  div.innerHTML = `<div class="bubble">${textHtml}${attHtml}</div>` +
    actsHtml("user", ts === undefined ? Date.now() : ts, !!(text || "").trim());
  chatAppend(div); scrollBottom(true);
}
// brain (tuỳ chọn): brain của HỘI THOẠI chứa tin này. Bỏ trống = brain đang chọn (tin mới).
// Truyền vào khi dựng lại tin CŨ, để ảnh trong tin phân giải theo đúng brain của nó thay vì
// brain đang chọn - nếu không thì mở hội thoại cũ ở brain khác là ảnh 404 rồi biến thành ô xám.
function appendJavisMessage(text, ts, brain) {
  const div = document.createElement("div");
  div.className = "msg msg-javis";
  div.innerHTML = `<div class="bubble">${markdownToHtml(text, brain)}</div>` +
    actsHtml("javis", ts === undefined ? Date.now() : ts, !!lastUserText().trim());
  chatAppend(div); scrollBottom();
  return div;
}
// Bong bóng LỖI. KHÔNG nhét icon vào appendJavisMessage: hàm đó chạy nội dung qua
// markdownToHtml, mà bộ render escape HTML - thẻ <svg> sẽ hiện thành chữ, và chữ nào
// escape sẵn trước khi truyền vào thì bị escape lần hai (user đọc ra "&quot;" giữa
// câu log). Nên phần chữ đi đúng đường markdown như mọi tin khác, icon gắn riêng vào
// bong bóng bằng HTML thật.
function appendJavisError(text) {
  const div = appendJavisMessage(text);
  const bubble = div.querySelector(".bubble");
  if (bubble) bubble.insertAdjacentHTML("afterbegin", ic("triangle-alert", { cls: "ic-warn" }) + " ");
  return div;
}
function createStreamingBubble() {
  const div = document.createElement("div");
  div.className = "msg msg-javis";
  div.innerHTML = `<div class="bubble"></div>` +
    actsHtml("javis", Date.now(), !!lastUserText().trim());
  chatAppend(div); scrollBottom();
  return div;
}
function markdownToHtml(text, brain) {
  // Render đầy đủ (markdown + tô màu code + artifact) nằm ở chat-render.js.
  if (typeof window.mdToHtml === "function") return window.mdToHtml(text, brain);
  // Fallback nếu chat-render.js chưa nạp: bộ render gọn cũ (không có artifact).
  const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  const safeHref = (x) => /^(https?:\/\/|mailto:|\/)/i.test((x || "").trim()) ? x : "";
  // 1) Tách & giữ code block ```...``` ra placeholder để không bị xử lý nhầm
  const blocks = [];
  text = text.replace(/```(?:\w+)?\n?([\s\S]*?)```/g, (_, code) => {
    blocks.push(`<div class="code-wrap"><button class="code-copy" type="button">⧉ Copy</button><pre class="code-block">${esc(code.replace(/\n$/, ""))}</pre></div>`);
    return ` B${blocks.length - 1} `;
  });

  // 2) Bảng markdown |a|b| với dòng phân cách |---|
  text = text.replace(
    /(^\|.+\|[ \t]*\n\|[ \t:|-]+\|[ \t]*\n(?:\|.*\|[ \t]*\n?)*)/gm,
    (tbl) => {
      const rows = tbl.trim().split("\n").filter(r => r.trim());
      const cells = r => r.replace(/^\||\|$/g, "").split("|").map(c => c.trim());
      const head = cells(rows[0]);
      const body = rows.slice(2).map(cells);
      const th = head.map(c => `<th>${esc(c)}</th>`).join("");
      const trs = body.map(r => `<tr>${r.map(c => `<td>${esc(c)}</td>`).join("")}</tr>`).join("");
      return ` T${blocks.push(`<table class="md-table"><thead><tr>${th}</tr></thead><tbody>${trs}</tbody></table>`) - 1} `;
    }
  );

  // 2b) Ảnh + link: giữ qua placeholder (NUL) để URL không bị escape. Đường dẫn vault -> /files/raw.
  const _fileUrl = (p) => `/files/raw?brain=${encodeURIComponent(brain || currentBrainPath())}&path=${encodeURIComponent((p || "").replace(/^\.?\//, ""))}`;
  const _resolveSrc = (s) => { s = (s || "").trim(); return /^(https?:|data:|blob:|\/)/i.test(s) ? s : _fileUrl(s); };
  const _imgHtml = (u, alt) => { const _h = safeHref(u); const _img = `<img class="chat-img" style="max-width:min(100%,440px);border-radius:8px;display:block;margin:6px 0;cursor:zoom-in" src="${esc(u)}" alt="${esc(alt || "")}" loading="lazy">`; return _h ? `<a href="${esc(_h)}" target="_blank" rel="noopener">${_img}</a>` : _img; };
  text = text.replace(/!\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]/g, (_m, name) => ` B${blocks.push(_imgHtml(_resolveSrc(name.trim()), name.trim())) - 1} `);
  text = text.replace(/!\[([^\]]*)\]\(([^)\s]+)[^)]*\)/g, (_m, alt, src) => ` B${blocks.push(_imgHtml(_resolveSrc(src), alt)) - 1} `);
  text = text.replace(/\[([^\]]+)\]\(([^)\s]+)[^)]*\)/g, (_m, t, href) => { href = href.trim(); const u = /^(https?:|mailto:)/i.test(href) ? href : _resolveSrc(href); return ` B${blocks.push(`<a href="${esc(u)}" target="_blank" rel="noopener">${esc(t)}</a>`) - 1} `; });

  // 3) Phần còn lại: escape rồi áp inline + list + heading
  let html = esc(text)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`(.+?)`/g, "<code>$1</code>")
    .replace(/^#{2,6} (.+)$/gm, "<h3>$1</h3>")
    .replace(/^\s*[-*] (.+)$/gm, "<li>$1</li>")
    .replace(/^\s*\d+[.)] (.+)$/gm, "<li>$1</li>")
    .replace(/(<li>[\s\S]*?<\/li>\n?)+/g, m => `<ul>${m}</ul>`)
    .replace(/\n{2,}/g, "<br><br>")
    .replace(/\n/g, "<br>");

  // 4) Trả lại các block/table đã giữ
  html = html.replace(/ [BT](\d+) (?:<br>)?/g, (_, i) => blocks[+i]);
  return html;
}
function escapeHtml(t) { return t.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;"); }
// ---- Chip hoạt động trong transcript (thay #toolBar cũ nằm ngoài #chatArea nên
//      biến mất khi phóng to chat). Chip là 1 "bong bóng" 3 chấm nhún + dòng trạng thái
//      + đồng hồ đếm giây, luôn nằm CUỐI khung chat, đi theo cả chế độ zoom. ----
let activityEl = null, activityT0 = 0, activityTimer = null;
// Chip hoạt động cuối khung chat. THAM SỐ LÀ HTML, không phải chữ thuần: nhiều chỗ
// gọi kèm icon (Icons.msg) nên textContent sẽ in nguyên thẻ <svg ...> ra màn hình.
// Chữ từ server BẮT BUỘC đi qua escapeHtml trước khi truyền vào đây.
function showActivity(html) {
  if (!activityEl) {
    activityEl = document.createElement("div");
    activityEl.className = "msg msg-activity";
    activityEl.innerHTML =
      '<div class="act-bubble"><span class="act-dots"><i></i><i></i><i></i></span>' +
      '<span class="act-text"></span><span class="act-time"></span></div>';
    activityT0 = Date.now();
    activityTimer = setInterval(() => {
      if (!activityEl) return;
      const s = Math.floor((Date.now() - activityT0) / 1000);
      // 3s đầu khỏi hiện số cho đỡ rối; câu chậm (CLI/MCP) thì thấy rõ đã đợi bao lâu
      activityEl.querySelector(".act-time").textContent = s >= 3 ? s + "s" : "";
    }, 1000);
  }
  activityEl.querySelector(".act-text").innerHTML = html || "Đang xử lý...";
  chatAppend(activityEl);   // re-append → luôn dưới cùng (kể cả dưới bubble đang stream)
  scrollBottom();
}
function hideActivity() {
  if (activityTimer) { clearInterval(activityTimer); activityTimer = null; }
  if (activityEl && activityEl.parentNode) activityEl.parentNode.removeChild(activityEl);
  activityEl = null;
}
function setProcessing(s) { isProcessing = s; sendBtn.disabled = s; }

// ============================================
// Cuộn thông minh: chỉ tự cuộn khi user đang ở đáy; đang đọc lại phía trên thì
// KHÔNG giật xuống - hiện nút "↓ Tin mới" (sticky trong khung chat) để nhảy xuống.
// Nút được chèn lazy khi có tin đầu tiên → .transcript:empty::after vẫn hoạt động.
// ============================================
let stickBottom = true;
const newMsgBtn = document.createElement("button");
newMsgBtn.id = "newMsgBtn"; newMsgBtn.type = "button";
newMsgBtn.addEventListener("click", () => scrollBottom(true));

// Nút có HAI dạng, vì hai tình huống khác nhau:
//   - Chỉ đang cuộn lên đọc lại  -> nút tròn nhỏ chỉ có mũi tên, đủ để nhảy xuống đáy.
//   - Có tin MỚI tới lúc đang đọc -> nở ra thành "Tin mới" để báo là có cái đáng xuống xem.
// Trước đây chỉ có dạng thứ hai, mà nó lại chỉ hiện khi scrollBottom() được gọi (tức là khi
// có tin mới). Cuộn lên đọc lại một hội thoại dài rồi muốn quay xuống thì KHÔNG có nút nào,
// phải tự kéo tay hết cả khung - đúng chỗ chủ repo kêu mất thời gian.
const XUONG_ICON = (typeof ic === "function") ? ic("chevron-down") : "↓";
function veNutXuong(coTinMoi) {
  newMsgBtn.classList.toggle("has-new", !!coTinMoi);
  newMsgBtn.innerHTML = coTinMoi ? XUONG_ICON + " Tin mới" : XUONG_ICON;
  newMsgBtn.title = coTinMoi ? "Có tin mới - xuống cuối" : "Xuống cuối hội thoại";
  newMsgBtn.setAttribute("aria-label", newMsgBtn.title);
}
veNutXuong(false);

function chatAppend(el) {
  if (newMsgBtn.parentNode !== chatArea) chatArea.appendChild(newMsgBtn);
  chatArea.insertBefore(el, newMsgBtn);
}
// Ngưỡng 90px: coi như "đang ở đáy" nên vẫn tự cuộn theo tin mới, và không hiện nút.
function ganDay() {
  return chatArea.scrollHeight - chatArea.scrollTop - chatArea.clientHeight < 90;
}
function capNhatNutXuong() {
  if (!newMsgBtn.parentNode) return;             // chưa có tin nào thì chưa chèn nút
  if (stickBottom) { newMsgBtn.classList.remove("show"); veNutXuong(false); return; }
  newMsgBtn.classList.add("show");
}
chatArea.addEventListener("scroll", () => {
  stickBottom = ganDay();
  // Rời đáy là hiện nút NGAY, không chờ tin mới nào cả.
  capNhatNutXuong();
});
function scrollBottom(force) {
  if (force) stickBottom = true;
  if (stickBottom) {
    chatArea.scrollTop = chatArea.scrollHeight;
    newMsgBtn.classList.remove("show");
    veNutXuong(false);
  } else if (newMsgBtn.parentNode) {
    veNutXuong(true);                            // đang đọc phía trên mà có tin mới tới
    newMsgBtn.classList.add("show");
  }
}

// ============================================
// Copy code block / copy tin nhắn / xem thêm tin dài - event delegation
// (bubble re-render liên tục khi stream nên KHÔNG gắn handler từng nút)
// ============================================
function copyFallback(s) {   // HTTP LAN/VPS chưa https, hoặc clipboard API bị chặn quyền
  return new Promise((res) => {
    const ta = document.createElement("textarea");
    ta.value = s; ta.style.cssText = "position:fixed;opacity:0";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } catch (e) {}
    ta.remove(); res();
  });
}
function copyText(s) {
  if (navigator.clipboard && window.isSecureContext)
    return navigator.clipboard.writeText(s).catch(() => copyFallback(s));
  return copyFallback(s);
}
function flashCopied(btn, label) {
  const old = btn.textContent;
  btn.innerHTML = ic("check", { cls: "ic-ok" }) + " Đã copy";
  setTimeout(() => { btn.textContent = label || old; }, 1200);
}
// Bấm một nút trong hàng .msg-acts. Gửi lại / sửa lại đều lấy chữ GỐC của tin người
// dùng (dataset.text) chứ không đọc lại DOM, vì tin dài đang thu gọn và tin Javis đã
// thành HTML. Gửi lại = một lượt MỚI ở cuối hội thoại, không xoá gì của lượt cũ.
function runMsgAct(btn) {
  const msgEl = btn.closest(".msg");
  if (!msgEl) return;
  const act = btn.dataset.act;
  if (act === "copy") {
    const b = msgEl.querySelector(".bubble");
    if (b) copyText(b.innerText).then(() => flashCopied(btn, "⧉"));
    return;
  }
  const text = window.JavisActs && window.JavisActs.isUserMsg(msgEl)
    ? (msgEl.dataset.text || "")
    : (window.JavisActs ? window.JavisActs.prevUserText(msgEl) : "");
  if (!text) return;
  if (act === "edit") {
    // Chỉ đổ chữ vào ô nhập, KHÔNG tự gửi - để anh sửa xong tự bấm gửi.
    chatInput.value = text;
    chatInput.style.height = "auto";
    chatInput.style.height = Math.min(chatInput.scrollHeight, 200) + "px";
    try { chatInput.focus(); chatInput.setSelectionRange(text.length, text.length); } catch (e) {}
    return;
  }
  if (act === "retry" && !isProcessing) sendMessage(text);
}
chatArea.addEventListener("click", (e) => {
  const t = e.target;
  const actBtn = t.closest && t.closest(".msg-act");
  if (actBtn) { runMsgAct(actBtn); return; }
  if (t.classList.contains("code-copy")) {
    const wrap = t.closest(".code-wrap");
    const pre = wrap && wrap.querySelector("pre");
    if (pre) copyText(pre.innerText).then(() => flashCopied(t, "⧉ Copy"));
  } else if (t.classList.contains("clamp-more")) {
    const u = t.closest(".bubble") && t.closest(".bubble").querySelector(".utext");
    if (u) { u.classList.toggle("clamped"); t.textContent = u.classList.contains("clamped") ? "Xem thêm" : "Thu gọn"; }
  }
});
// Điện thoại không có hover: chạm vào tin để bật/tắt hàng nút của đúng tin đó.
chatArea.addEventListener("click", (e) => {
  try { if (!window.matchMedia("(hover: none)").matches) return; } catch (err) { return; }
  if (!e.target.closest) return;
  if (e.target.closest(".msg-acts")) return;   // bấm chính nút thì đừng đóng hàng nút
  const msgEl = e.target.closest(".msg");
  chatArea.querySelectorAll(".msg.acts-on").forEach(m => { if (m !== msgEl) m.classList.remove("acts-on"); });
  if (msgEl) msgEl.classList.toggle("acts-on");
});
function updateSysStatus(s) {
  document.getElementById("claudeStatus").className = "mcp-item " + s;
  document.getElementById("ttsStatus").className = "mcp-item " + s;
}

const usedMCPs = new Map();
function compactToolLabel(toolName) {
  const raw = String(toolName || "").trim();
  let label = raw || "Tool", cat = "Tool";
  // CLI đôi khi gửi NGUYÊN câu lệnh đang chạy thay vì tên tool. Không đưa command/path dài
  // lên status bar: vừa rối, vừa làm min-content nới cả layout.
  if (/^(?:\/(?:usr\/)?bin\/)?(?:ba|z|k)?sh(?:\s|$)/i.test(raw)
      || /^(?:powershell|pwsh|cmd(?:\.exe)?)(?:\s|$)/i.test(raw)
      || /(?:^|__)(?:shell|exec)_command$/i.test(raw)) {
    return { label: "Terminal", cat: "Local" };
  }
  if (raw.includes("pos_")) { cat = "POS"; label = "Pancake POS"; }
  else if (/facebook|fb_/i.test(raw)) { cat = "Ads"; label = "Facebook"; }
  else if (/instagram|ig_/i.test(raw)) { cat = "Social"; label = "Instagram"; }
  else if (/youtube|yt_/i.test(raw)) { cat = "Social"; label = "YouTube"; }
  else if (/ga4|analytics/i.test(raw)) { cat = "Web"; label = "Analytics"; }
  else if (/Read|Grep|Glob|vault/i.test(raw)) { cat = "Local"; label = "Files/Vault"; }
  else if (raw.startsWith("mcp__")) {
    const p = raw.split("__");
    if (p.length >= 3) label = p[2].replace(/_/g, " ");
    cat = "MCP";
  }
  if (label.length > 48) label = label.slice(0, 47) + "…";
  return { label, cat };
}
function trackMCP(toolName) {
  const list = document.getElementById("mcpList");
  if (!list) return;
  const { label, cat } = compactToolLabel(toolName);
  if (!usedMCPs.has(label)) {
    if (list.querySelector(".dim")) list.innerHTML = "";
    const div = document.createElement("div");
    div.className = "mcp-item active";
    div.title = String(toolName || label);
    div.insertAdjacentHTML("beforeend", `${ic("circle", { cls: "ic-fill ic-sm" })} ${escapeHtml(label)} `);
    const meta = document.createElement("span");
    meta.className = "mcp-kind";
    meta.textContent = `· ${cat}`;
    div.appendChild(meta);
    list.appendChild(div); usedMCPs.set(label, div);
    // Đây là trạng thái gần đây, không phải nhật ký. Giữ tối đa 4 loại để DOM/dải ngang
    // không phình mãi trong một phiên chat dài.
    while (usedMCPs.size > 4) {
      const oldest = usedMCPs.keys().next().value;
      const oldEl = usedMCPs.get(oldest);
      if (oldEl && oldEl.parentNode) oldEl.parentNode.removeChild(oldEl);
      usedMCPs.delete(oldest);
    }
  } else {
    const el = usedMCPs.get(label);
    el.classList.add("loading");
    setTimeout(() => el.classList.replace("loading", "active"), 600);
  }
}

// ============================================
// Knowledge graph (2D canvas)
// ============================================
const graphStats = document.getElementById("graphStats");
const graphSource = document.getElementById("graphSource");
let javisGraph = null;

let _lib2dPromise = null;
function _ensure2DLib() {               // force-graph + d3-force, self-hosted và không dùng WebGL
  if (window.ForceGraph) return Promise.resolve();
  if (_lib2dPromise) return _lib2dPromise;
  _lib2dPromise = new Promise((resolve) => {
    const s = document.createElement("script");
    s.src = "/static/vendor/force-graph-1.51.4.min.js";   // self-host: unpkg đo được ~0.7s trên đường boot
    s.onload = resolve; s.onerror = resolve;
    document.head.appendChild(s);
  });
  return _lib2dPromise;
}

async function initGraph() {
  const c2d = document.getElementById("graph2d");
  if (c2d) c2d.style.display = "block";   // "" sẽ rơi về CSS #graph2d{display:none} → bị ẩn
  await _ensure2DLib();
  if (!window.ForceGraph) { graphStats.innerHTML = ic("triangle-alert", { cls: "ic-warn" }) + " Lỗi tải thư viện đồ thị (kiểm tra mạng)"; return; }
  javisGraph = new JavisGraph(c2d);   // resize() gọi bên trong load()
  await reloadGraph();
}

// Click node trong graph → Javis mở & thao tác note đó trong vault
window.onGraphNodeClick = (node) => {
  if (!node || !node.path) return;
  const brainRel = (node.path || "").split("/").slice(1).join("/") || node.path;   // bỏ đoạn gốc → path tương đối brain
  if (typeof window.JavisOpenNote === "function") window.JavisOpenNote(brainRel);   // mở editor cây (WYSIWYG + công cụ)
  else openNodePopup(node);   // dự phòng nếu editor cây chưa sẵn
};

// ============================================
// Popup đọc / sửa 1 node của graph. Node.path = "<tên thư mục gốc>/<đường dẫn>"; bỏ đoạn gốc
// để hợp path tương đối của /files. Đọc qua /files/read, lưu qua /files/write (như trang Tệp tin).
// ============================================
let _nodeModal = null;
function _ensureNodeModal() {
  if (_nodeModal) return _nodeModal;
  const css = `
    .node-modal{position:fixed;inset:0;z-index:600;display:none;align-items:center;justify-content:center;background:var(--scrim);backdrop-filter:blur(3px);padding:24px}
    .node-modal.open{display:flex}
    .node-card{width:min(820px,94vw);max-height:88vh;display:flex;flex-direction:column;background:var(--panel-solid);border:1px solid var(--border);border-radius:14px;box-shadow:0 24px 70px rgba(0,0,0,.6);overflow:hidden}
    .node-head{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 14px;border-bottom:1px solid var(--border)}
    .node-title{font-family:var(--font);font-weight:700;font-size:16px;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .node-actions{display:flex;align-items:center;gap:6px;flex:none}
    .nm-btn{background:var(--surface-2);border:1px solid var(--border);color:var(--text2);border-radius:8px;padding:5px 11px;cursor:pointer;font-size:13px;text-decoration:none;display:inline-block;white-space:nowrap}
    .nm-btn:hover{color:var(--accent);border-color:var(--accent)}
    .node-path{padding:6px 14px;font-size:12px;color:var(--text3);border-bottom:1px solid var(--border);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .node-body{flex:1 1 auto;min-height:0;display:flex}
    .node-body textarea{width:100%;min-height:56vh;flex:1;background:var(--field-bg);color:var(--text);border:none;outline:none;padding:14px;font:14px/1.6 ui-monospace,Consolas,monospace;resize:none}
    .node-msg{padding:22px;color:var(--text2);font-size:15px;line-height:1.6}`;
  const st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);
  const m = document.createElement("div");
  m.className = "node-modal"; m.id = "nodeModal";
  m.innerHTML =
    '<div class="node-card">' +
      '<div class="node-head">' +
        '<span class="node-title" id="nodeTitle"></span>' +
        '<span class="node-actions">' +
          '<a class="nm-btn" id="nodeOpenTab" target="_blank" rel="noopener">↗ Tab mới</a>' +
          '<button class="nm-btn" id="nodeSave" type="button">' + ic("save") + ' Lưu</button>' +
          '<button class="nm-btn" id="nodeCloseBtn" type="button">' + ic("x") + '</button>' +
        '</span>' +
      '</div>' +
      '<div class="node-path" id="nodePath"></div>' +
      '<div class="node-body" id="nodeBody"></div>' +
    '</div>';
  document.body.appendChild(m);
  m.addEventListener("click", (e) => { if (e.target === m) closeNodePopup(); });
  m.querySelector("#nodeCloseBtn").addEventListener("click", closeNodePopup);
  _nodeModal = m;
  return m;
}
function closeNodePopup() { if (_nodeModal) _nodeModal.classList.remove("open"); }
async function openNodePopup(node) {
  const m = _ensureNodeModal();
  const brain = currentBrainPath();
  const rel = (node.path || "").split("/").slice(1).join("/") || (node.path || "");
  m.querySelector("#nodeTitle").textContent = node.label || rel || "Note";
  m.querySelector("#nodePath").textContent = rel;
  const rawUrl = `/files/raw?brain=${encodeURIComponent(brain)}&path=${encodeURIComponent(rel)}`;
  m.querySelector("#nodeOpenTab").href = rawUrl;
  const body = m.querySelector("#nodeBody");
  const saveBtn = m.querySelector("#nodeSave");
  saveBtn.style.display = "none";
  body.innerHTML = '<div class="node-msg">Đang mở…</div>';
  m.classList.add("open");
  let d = {};
  try { d = await (await fetch(`/files/read?brain=${encodeURIComponent(brain)}&path=${encodeURIComponent(rel)}`)).json(); }
  catch (e) { body.innerHTML = `<div class="node-msg">Lỗi mở file: ${escapeHtml(String((e && e.message) || e))}</div>`; return; }
  if (!d || d.error || d.editable === false) {
    body.innerHTML = `<div class="node-msg">${escapeHtml((d && d.error) || "File này không sửa trực tiếp được.")} · <a href="${rawUrl}" target="_blank" style="color:var(--accent)">Mở trong tab mới</a></div>`;
    return;
  }
  body.innerHTML = '<textarea id="nodeText" spellcheck="false"></textarea>';
  body.querySelector("#nodeText").value = d.content || "";
  saveBtn.style.display = "";
  saveBtn.innerHTML = ic("save") + " Lưu";
  saveBtn.onclick = async () => {
    saveBtn.textContent = "Đang lưu…";
    const fd = new FormData();
    fd.append("brain", brain); fd.append("path", rel);
    fd.append("content", body.querySelector("#nodeText").value);
    let r = {};
    try { r = await (await fetch("/files/write", { method: "POST", body: fd })).json(); } catch (e) { r = { error: (e && e.message) || "lỗi" }; }
    saveBtn.innerHTML = (r && r.ok) ? ic("check", { cls: "ic-ok" }) + " Đã lưu" : ic("triangle-alert", { cls: "ic-warn" }) + " Lỗi";
    setTimeout(() => { saveBtn.innerHTML = ic("save") + " Lưu"; }, 1600);
  };
  setTimeout(() => { try { body.querySelector("#nodeText").focus(); } catch (e) {} }, 30);
}
async function reloadGraph() {
  if (!javisGraph) return;
  graphStats.textContent = "Đang tải...";
  const val = graphSource.value;
  const query = val.startsWith("path:")
    ? `path=${encodeURIComponent(val.slice(5))}`
    : `source=${val}`;
  try {
    const data = await javisGraph.load(query);
    const stats = data.stats || {};
    graphStats.textContent = `${stats.total_notes} note · ${stats.total_links} kết nối`;
    renderConceptLabels(data.categories || [], stats.total_notes || 0);
  } catch (e) { graphStats.textContent = "Lỗi: " + e.message; }
}
// Đổi brain → khung chat phải đổi theo brain (vụ Mac 0.9.230: transcript giữ nguyên phiên
// brain cũ, tưởng mất hội thoại, phải reload mới thấy). Nhớ phiên đang xem của TỪNG brain
// TRONG TRANG (cố ý không persist - giữ luật boot "mỗi lần tải trang là hội thoại mới"):
// sang brain lạ thì khung trắng, quay lại brain cũ thì mở lại đúng phiên đang xem từ server.
let _lastBrain = currentBrainPath();
const _viewByBrain = {};   // brain -> session id đang xem gần nhất trong phiên trang này
graphSource.addEventListener("change", () => {
  localStorage.setItem("javis.graphSource", graphSource.value);
  const nb = currentBrainPath();
  if (nb !== _lastBrain) {
    if (savedSessionId) _viewByBrain[_lastBrain] = savedSessionId;
    _lastBrain = nb;
    resetChatView();                                       // xoá ngay khung của brain cũ
    if (_viewByBrain[nb]) openStoredSession(_viewByBrain[nb]);   // brain quen → mở lại phiên đang dở
  }
  reloadGraph();
  connectGraphWatch();   // theo dõi realtime trên nguồn mới
  loadMemStats();   // bộ nhớ theo vault → đổi vault thì đổi số ký ức
  loadBrainStats(); // agent/skill/workflow theo vault
  checkVault();     // kiểm tra cấu trúc vault mới chọn
});

// ============================================
// Realtime graph watch - node mọc lên khi brain sinh note mới
// ============================================
let graphWs = null;
let graphWatchReconnect = null;
function connectGraphWatch() {
  if (graphWs) { try { graphWs.onclose = null; graphWs.close(); } catch (e) {} graphWs = null; }
  clearTimeout(graphWatchReconnect);
  const val = graphSource.value;
  const q = val.startsWith("path:")
    ? `path=${encodeURIComponent(val.slice(5))}`
    : `source=${encodeURIComponent(val)}`;
  graphWs = new WebSocket(`${WS_ORIGIN}/ws/graph?${q}`);
  graphWs.onmessage = (e) => {
    let m; try { m = JSON.parse(e.data); } catch (_) { return; }
    if (m.type !== "graph_add" || !javisGraph) return;
    const r = javisGraph.addOrUpdate(m.node, m.linkTargets, m.isNew);
    if (r && r.created) {
      const s = javisGraph.nodeStats();
      graphStats.textContent = `${s.nodes} note · ${s.links} kết nối`;
      // Nháy nhẹ nhãn để báo có note mới sinh ra
      graphStats.classList.add("pulse");
      setTimeout(() => graphStats.classList.remove("pulse"), 700);
    }
  };
  graphWs.onclose = () => {
    graphWatchReconnect = setTimeout(connectGraphWatch, 3000);
  };
  graphWs.onerror = () => { try { graphWs.close(); } catch (e) {} };
}

// ============================================
// Kiểm tra cấu trúc vault (Phase 1)
// ============================================
const vaultBanner = document.getElementById("vaultBanner");
const vbText = document.getElementById("vbText");
const vbInit = document.getElementById("vbInit");

async function checkVault() {
  try {
    const d = await (await fetch(`/vault/check?brain=${encodeURIComponent(currentBrainPath())}`)).json();
    if (d.ok && d.missing === 0) {
      vaultBanner.classList.remove("show");
    } else {
      const miss = d.items.filter(i => !i.present).map(i => i.label).join(", ");
      vbText.textContent = d.ok
        ? `Vault chạy được, nhưng thiếu: ${miss}.`
        : `Cấu trúc vault chưa chuẩn cho Javis - thiếu: ${miss}.`;
      vaultBanner.classList.add("show");
    }
  } catch (e) {}
}

vbInit.addEventListener("click", async () => {
  vbInit.disabled = true;
  const old = vbInit.textContent;
  vbInit.textContent = "Đang tạo...";
  try {
    const fd = new FormData();
    fd.append("brain", currentBrainPath());
    const d = await (await fetch("/vault/init", { method: "POST", body: fd })).json();
    if (d.ok) {
      vbText.innerHTML = `${ic("check", { cls: "ic-ok" })} Đã tạo: ${escapeHtml((d.created || []).join(", ") || "(đã đủ)")}`;
      vbInit.style.display = "none";
      setTimeout(() => { vaultBanner.classList.remove("show"); vbInit.style.display = ""; checkVault(); }, 2500);
    }
  } catch (e) {}
  vbInit.textContent = old;
  vbInit.disabled = false;
});

document.getElementById("vbClose").addEventListener("click", () => vaultBanner.classList.remove("show"));

// Đổi tông: bảng màu danh mục đổi theo, mà chữ "% Vault" đã gắn màu inline lúc dựng
// nên phải tô lại, không thì nhãn giữ màu rực của tông tối và nhợt hẳn trên giấy.
// graph.js bắn "javis-catcolors-change" SAU khi đã hoán bảng.
window.addEventListener("javis-catcolors-change", function repaintConceptLabels() {
  const map = window.__javisCatMap || {};
  document.querySelectorAll("#conceptLabels .concept-label").forEach(div => {
    const fire = div.querySelector(".cl-fire");
    const col = map[div.dataset.cat || ""];
    if (fire && col) fire.style.color = col;
  });
});

// Nhãn concept (HUD brain-region) quanh orb - số liệu THẬT
//
// Nhớ lại danh mục lần vẽ gần nhất để xoay ngang/dọc điện thoại còn rải lại được: số nhãn và
// bán kính phụ thuộc BỀ NGANG khoang não, mà hàm này vốn chỉ chạy lúc nạp đồ thị.
let _catsCache = null;

function renderConceptLabels(categories, total) {
  const container = document.getElementById("conceptLabels");
  container.innerHTML = "";
  if (categories) _catsCache = { categories: categories, total: total };
  if (!categories || !categories.length) return;
  const denom = total || categories.reduce((s, c) => s + c.count, 0);

  // Khoang não hẹp (điện thoại) chỉ cao khoảng 228px và rộng 390px. Rải đủ 8 nhãn cỡ desktop
  // vào đó thì nhãn phủ kín khung, tên dài ("BRAIN DEFAULT") tràn hẳn ra ngoài mép phải, và
  // đồ thị - thứ duy nhất đáng nhìn ở đây - bị dồn vào một cục giữa màn. Chủ repo chụp lại
  // đúng cảnh đó. Hẹp thì rải 4 nhãn ở bốn góc và kéo bán kính vào trong mép.
  const host = container.parentElement;
  const pw = (host && host.clientWidth) || window.innerWidth || 900;
  const ph = (host && host.clientHeight) || 600;
  const hep = pw < 620 || ph < 320;
  const n = Math.min(categories.length, hep ? 4 : 8);
  const rx = hep ? 33 : 40;
  const ry = hep ? 34 : 32;
  const cy = hep ? 44 : 45;
  // Rải nhãn theo cung HỞ ĐÁY: chừa khe dưới-giữa cho "SẴN SÀNG" + dải số liệu
  // → không bao giờ có nhãn nằm chính giữa-đáy đè lên chữ trạng thái.
  const gap = ((hep ? 104 : 76) * Math.PI) / 180;   // khe trống ở đáy (hẹp thì chừa rộng hơn)
  const sweep = Math.PI * 2 - gap;           // cung còn lại để rải nhãn
  const start = Math.PI / 2 + gap / 2;       // bắt đầu ở đáy-trái, đi qua đỉnh tới đáy-phải
  for (let i = 0; i < n; i++) {
    const c = categories[i];
    const frac = n === 1 ? 0.5 : i / (n - 1);
    const angle = start + frac * sweep;
    const x = 50 + Math.cos(angle) * rx;
    const y = cy + Math.sin(angle) * ry;
    const share = denom ? Math.round((c.count / denom) * 100) : 0;
    const div = document.createElement("div");
    div.className = "concept-label";
    div.style.left = x + "%";
    div.style.top = y + "%";
    // Tô chữ "% Vault" đúng màu node của thư mục đó (lấy từ bảng màu danh mục của đồ thị) → dễ nhận màu nào của folder nào.
    // Nhớ luôn catKey trên node để đổi tông còn tô lại được (xem repaintConceptLabels).
    const catKey = c.name.replace(/^\d+\s*[-_.]\s*/, "").trim().toLowerCase();
    const catCol = (window.__javisCatMap || {})[catKey];
    div.dataset.cat = catKey;
    div.innerHTML = `<div class="cl-name">${escapeHtml(c.name.toUpperCase())}</div>` +
      `<div class="cl-meta">${c.count} note · <span class="cl-fire"${catCol ? ` style="color:${catCol}"` : ""}>${share}% Vault</span></div>`;
    // Bấm nhãn danh mục → rọi sáng đúng cụm đó trong đồ thị.
    div.style.cursor = "pointer";
    div.title = "Bấm để rọi sáng cụm " + c.name;
    div.onclick = () => {
      const g = window.__javisGraph;
      if (!g || typeof g.spotlightCategory !== "function") return;
      const key = c.name.replace(/^\d+\s*[-_.]\s*/, "").trim().toLowerCase();
      const on = g._catFilter === key;
      g.spotlightCategory(on ? null : c.name);
      container.querySelectorAll(".concept-label").forEach(d => d.classList.remove("cl-active"));
      if (!on) div.classList.add("cl-active");
    };
    container.appendChild(div);
    setTimeout(() => div.classList.add("show"), 120 + i * 110);
  }
}

// Xoay ngang/dọc điện thoại, hoặc bung/thu khoang não: số nhãn và bán kính đổi theo bề ngang
// nên phải rải lại. Chống dội bằng debounce - resize bắn hàng chục lần mỗi giây.
let _catsT = null;
window.addEventListener("resize", () => {
  if (_catsT) clearTimeout(_catsT);
  _catsT = setTimeout(() => {
    if (_catsCache) renderConceptLabels(_catsCache.categories, _catsCache.total);
  }, 220);
});

// Brain folder tùy chọn - lưu localStorage, hiện trong dropdown.
//
// Thẻ <option> chỉ nhận CHỮ, không nhận SVG, nên đây là chỗ duy nhất trong
// dashboard không dùng được icon. Phân biệt "thư mục ngoài" với brain thật bằng
// <optgroup> - cách gốc của HTML, hiển thị đúng trên mọi máy và vẫn giữ trọn
// thông tin mà trước đây icon thư mục đang mang.
function loadCustomBrains() {
  const brains = JSON.parse(localStorage.getItem("javis.brains") || "[]");
  // Xóa nhóm + option cũ
  const oldGrp = graphSource.querySelector('optgroup[data-custom-group]');
  if (oldGrp) oldGrp.remove();
  [...graphSource.querySelectorAll("option[data-custom]")].forEach(o => o.remove());
  if (!brains.length) return;
  const grp = document.createElement("optgroup");
  grp.label = "Thư mục ngoài";
  grp.dataset.customGroup = "1";
  brains.forEach(b => {
    const opt = document.createElement("option");
    opt.value = "path:" + b.path;
    opt.textContent = b.name;
    opt.dataset.custom = "1";
    grp.appendChild(opt);
  });
  graphSource.appendChild(grp);
}
function addCustomBrain(path) {
  const brains = JSON.parse(localStorage.getItem("javis.brains") || "[]");
  if (brains.some(b => b.path === path)) return;
  const name = path.replace(/[\\/]+$/, "").split(/[\\/]/).pop() || path;
  brains.push({ name, path });
  localStorage.setItem("javis.brains", JSON.stringify(brains));
  loadCustomBrains();
}
loadCustomBrains();
// Khôi phục folder đã chọn lần trước (mặc định: brain)
(function restoreGraphSource() {
  const saved = localStorage.getItem("javis.graphSource");
  if (saved && [...graphSource.options].some(o => o.value === saved)) {
    graphSource.value = saved;
  } else {
    graphSource.value = "brain";
  }
})();

// ============================================
// Folder picker modal
// ============================================
const folderModal = document.getElementById("folderModal");
const fmList = document.getElementById("fmList");
const fmPath = document.getElementById("fmPath");
const fmHint = document.getElementById("fmHint");
let fmCurrent = "";

async function fmBrowse(path) {
  fmHint.textContent = "Đang tải...";
  try {
    const res = await fetch(`/browse?path=${encodeURIComponent(path || "")}`);
    const data = await res.json();
    fmCurrent = data.path || "";
    fmPath.textContent = fmCurrent || "Ổ đĩa";
    fmList.innerHTML = "";
    if (data.parent !== null && data.parent !== undefined) {
      const up = document.createElement("div");
      up.className = "fm-row up";
      up.innerHTML = `<span class="fm-name">${ic("arrow-up")} .. (lên trên)</span>`;
      up.onclick = () => fmBrowse(data.parent);
      fmList.appendChild(up);
    }
    (data.dirs || []).forEach(d => {
      const row = document.createElement("div");
      row.className = "fm-row";
      const mdBadge = d.md ? `<span class="fm-md">${d.md} .md</span>` : "";
      row.innerHTML = `<span class="fm-name">${ic("folder")} ${escapeHtml(d.name)}</span>${mdBadge}`;
      row.onclick = () => fmBrowse(d.path);
      fmList.appendChild(row);
    });
    fmHint.textContent = data.here_md ? `${data.here_md} file .md ở đây` : (data.error || "Chọn folder chứa ghi chú");
  } catch (e) {
    fmHint.textContent = "Lỗi: " + e.message;
  }
}

document.getElementById("pickFolderBtn").addEventListener("click", () => {
  folderModal.classList.add("open");
  fmBrowse("");
});
document.getElementById("fmClose").addEventListener("click", () => folderModal.classList.remove("open"));
folderModal.addEventListener("click", (e) => { if (e.target === folderModal) folderModal.classList.remove("open"); });
document.getElementById("fmUse").addEventListener("click", () => {
  if (!fmCurrent) return;
  addCustomBrain(fmCurrent);
  graphSource.value = "path:" + fmCurrent;
  localStorage.setItem("javis.graphSource", graphSource.value);
  folderModal.classList.remove("open");
  reloadGraph();
});
window.addEventListener("resize", () => { if (javisGraph) javisGraph.resize(); });

let _stopBtnTick = 0;
function pumpAudioLevel() {
  if (javisGraph) javisGraph.setLevel(voice.getLevel());
  // Cập nhật hiển thị nút stop ~6 lần/giây (theo dõi cả lúc Javis đang đọc)
  if ((_stopBtnTick++ % 10) === 0) {
    updateStopBtn();
    // Đọc xong cả hàng đợi (gồm các bước trung gian) → trả orb về nghỉ.
    // Hands-free thì để vòng lặp nghe-lại tự chuyển sang trạng thái ĐANG NGHE.
    if (!isProcessing && !handsFree && !voice.isSpeaking() && orbState.classList.contains("speaking")) {
      setOrbState("", "SẴN SÀNG");
    }
  }
  requestAnimationFrame(pumpAudioLevel);
}
stopBtn.addEventListener("click", stopCurrent);

// ============================================
// Starfield nebula - nền vũ trụ, sáng theo nhịp giọng nói
// ============================================
let _thinkingActive = false;

// Hai bảng màu nền não. Tông TỐI là vũ trụ: sao trắng cộng sáng trên nền đen.
// Tông SÁNG là giấy: cùng bố cục (quầng giữa, lưới sàn, hạt rải) nhưng vẽ bằng
// MỰC SẪM chồng thường lên giấy ngà. Không đảo màu được - "lighter" trên nền
// trắng cho ra trắng bệt, còn sao trắng thì biến mất hẳn.
const SKY_DARK = {
  stars: ["#ffffff", "#c9b3ff", "#b8a3ff", "#d6c9ff"],
  starOp: "lighter",          // cộng sáng: sao chồng nhau càng rực
  starMax: 0.85,
  haloIn: [140, 90, 230],     // quầng giữa - thở theo giọng nói
  haloMid: [90, 60, 170],
  haloOut: "rgba(8,6,20,0)",
  haloBase: 0.10, haloGain: 0.12,
  grid: [165, 115, 230], gridBase: 0.13, gridGain: 0.10,
  ring: [70, 200, 255], ringGain: 1,
};
const SKY_LIGHT = {
  // Hạt bụi giấy: xám tím và xám nâu, đủ sẫm để thấy mà không thành vết bẩn.
  stars: ["#8e86a6", "#a79ab8", "#b9a99a", "#7e7694"],
  starOp: "source-over",      // trên giấy phải chồng thường, không cộng sáng
  starMax: 0.42,
  haloIn: [124, 58, 237],
  haloMid: [232, 93, 31],     // vành đào ấm ôm ngoài quầng lavender
  haloOut: "rgba(255,255,255,0)",
  haloBase: 0.05, haloGain: 0.07,
  grid: [96, 74, 150], gridBase: 0.13, gridGain: 0.08,
  ring: [20, 110, 160], ringGain: 1.5,
};

function initStarfield() {
  const cv = document.getElementById("starfield");
  if (!cv) return;
  const ctx = cv.getContext("2d");
  let stars = [];
  let sky = SKY_DARK;
  let cssW = 0, cssH = 0, dpr = 1, lastDraw = 0;
  const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;

  function paintStars() {
    // Giữ nguyên vị trí/nhịp nháy, chỉ thay màu → đổi tông không làm nền "nhảy".
    stars.forEach(s => { s.c = sky.stars[s.ci % sky.stars.length]; });
  }

  function resize() {
    const rect = cv.parentElement.getBoundingClientRect();
    cssW = Math.round(rect.width);
    cssH = Math.round(rect.height);
    // Canvas cỡ CSS bị trình duyệt kéo giãn trên màn HiDPI → lưới, sao và quầng đều mờ.
    // Giới hạn 1.5 để lấy lại độ nét mà không nhân 4-9 lần chi phí vẽ như DPR 2-3 nguyên bản.
    dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    cv.width = Math.max(1, Math.round(cssW * dpr));
    cv.height = Math.max(1, Math.round(cssH * dpr));
    cv.style.width = cssW + "px";
    cv.style.height = cssH + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    // Ít sao + rải đều, mờ - không tạo cụm lạc
    const count = Math.max(40, Math.floor((cssW * cssH) / 16000));
    stars = Array.from({ length: count }, () => ({
      x: Math.random() * cssW,
      y: Math.random() * cssH,
      r: Math.random() * 1.0 + 0.2,
      tw: Math.random() * Math.PI * 2,
      sp: Math.random() * 0.04 + 0.006,
      ci: Math.floor(Math.random() * 4),
      c: "#ffffff",
    }));
    paintStars();
  }
  resize();
  window.addEventListener("resize", resize);
  // Nghe thẳng sự kiện thay vì javisTheme.on(): hàm này có thể chạy trước khi theme.js
  // kịp dựng window.javisTheme, khi đó đăng ký sẽ hụt im lặng và nền kẹt ở bảng tối.
  function syncSky(light) { sky = light ? SKY_LIGHT : SKY_DARK; paintStars(); }
  window.addEventListener("javis-theme-change", e => syncSky(!!(e && e.detail && e.detail.light)));
  syncSky(document.documentElement.getAttribute("data-theme") === "light");

  function draw(now) {
    requestAnimationFrame(draw);
    if (document.hidden) return;
    // Nền 2D từng tự dựng gradient + grid ở 60 FPS dù não đứng yên. 15 FPS lúc nghỉ vẫn
    // đủ cho sao nhấp nháy chậm; khi có giọng/đang nghĩ nâng lên 30 FPS.
    const lvl = voice.getLevel();
    const interval = (lvl > 0.01 || _thinkingActive) ? 33 : 66;
    if (now && now - lastDraw < interval) return;
    lastDraw = now || 0;
    // Tự đo lại kích thước (sửa lỗi nền dồn 1 góc khi layout chưa xong lúc boot)
    const rect = cv.parentElement.getBoundingClientRect();
    const pw = Math.round(rect.width), ph = Math.round(rect.height);
    if (pw > 0 && (cssW !== pw || cssH !== ph)) resize();
    if (!cssW) return;
    ctx.clearRect(0, 0, cssW, cssH);

    // Quầng ở TRUNG TÂM - phồng nhẹ theo giọng
    const cx = cssW / 2, cy = cssH / 2;
    const rr = Math.min(cssW, cssH) * (0.6 + lvl * 0.15);
    const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, rr);
    const a = sky.haloBase + lvl * sky.haloGain;
    g.addColorStop(0, rgba(sky.haloIn, a));
    g.addColorStop(0.5, rgba(sky.haloMid, a * 0.4));
    g.addColorStop(1, sky.haloOut);
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, cssW, cssH);

    // Grid floor phối cảnh (HUD command center) - đáy màn hình.
    // Khoang não thấp (điện thoại: ~228px) thì 28% cuối là 64px sàn lưới đè lên đúng chỗ đồ
    // thị cần. Panel càng thấp thì đẩy chân trời càng xuống - vẫn còn cảm giác chiều sâu,
    // nhưng không cướp chỗ của thứ người dùng thật sự muốn nhìn.
    const horizonY = cssH * (cssH < 320 ? 0.86 : 0.72);
    const vpX = cssW / 2;
    ctx.strokeStyle = rgba(sky.grid, sky.gridBase + lvl * sky.gridGain);
    ctx.lineWidth = 1;
    const cols = 18;
    for (let i = 0; i <= cols; i++) {
      const fx = (i / cols) * cssW;
      ctx.beginPath(); ctx.moveTo(fx, cssH); ctx.lineTo(vpX, horizonY); ctx.stroke();
    }
    const rows = 9;
    for (let j = 1; j <= rows; j++) {
      const t = j / rows;
      const y = horizonY + (cssH - horizonY) * (t * t);
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(cssW, y); ctx.stroke();
    }

    // Sóng nơron khi đang suy nghĩ - vòng lan toả CHẬM, dịu (bỏ tia nhấp nháy cho đỡ rối)
    if (_thinkingActive) {
      const now = Date.now();
      const ringCount = 2;
      for (let i = 0; i < ringCount; i++) {
        const phase = ((now / 1700) + i / ringCount) % 1;
        const r = phase * Math.min(cssW, cssH) * 0.5;
        const alpha = (1 - phase) * 0.15 * sky.ringGain;
        ctx.strokeStyle = rgba(sky.ring, alpha);
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.stroke();
      }
    }

    // Sao mờ rải đều (tông sáng: hạt bụi giấy)
    ctx.globalCompositeOperation = sky.starOp;
    stars.forEach(s => {
      s.tw += s.sp;
      const tw = (Math.sin(s.tw) * 0.35 + 0.45) * (1 + lvl * 0.6);
      ctx.globalAlpha = Math.min(sky.starMax, tw);
      ctx.fillStyle = s.c;
      ctx.beginPath();
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
  }
  draw();
}

// ============================================
// Bộ nhớ dài hạn / Tự học
// ============================================
const learnBtn = document.getElementById("learnBtn");
const memResult = document.getElementById("memResult");
const memCount = document.getElementById("memCount");
const autoLearnToggle = document.getElementById("autoLearnToggle");

let reflecting = false;
let turnsSinceReflect = 0;
const AUTO_LEARN_EVERY = 6;   // tự học sau mỗi 6 lượt hội thoại

// Khôi phục cài đặt tự học
let autoLearn = localStorage.getItem("javis.autoLearn") !== "off";
if (autoLearnToggle) {
  autoLearnToggle.checked = autoLearn;
  autoLearnToggle.addEventListener("change", () => {
    autoLearn = autoLearnToggle.checked;
    localStorage.setItem("javis.autoLearn", autoLearn ? "on" : "off");
  });
}

async function loadMemStats() {
  if (!memCount) return;   // panel học cũ đã gỡ khỏi index.html (thay bằng trang Tự học)
  try {
    const d = await (await fetch(`/memory/stats?brain=${encodeURIComponent(currentBrainPath())}`)).json();
    memCount.textContent = d.facts ?? 0;
  } catch (e) {}
}

// ============================================
// Lớp Agentic - số agent / skill / workflow ở đáy graph
// ============================================
function _setStat(id, n) {
  const el = document.getElementById(id);
  if (!el) return;
  const prev = parseInt(el.textContent, 10);
  el.textContent = n;
  if (!isNaN(prev) && n > prev) {   // có cái mới → nảy số
    el.classList.remove("bump"); void el.offsetWidth; el.classList.add("bump");
  }
}
async function loadBrainStats() {
  const b = encodeURIComponent(currentBrainPath());
  try {
    const [a, s, w] = await Promise.all([
      fetch(`/agents?brain=${b}`).then(r => r.json()).catch(() => ({})),
      fetch(`/skills?brain=${b}`).then(r => r.json()).catch(() => ({})),
      fetch(`/workflows?brain=${b}`).then(r => r.json()).catch(() => ({})),
    ]);
    _setStat("statAgents", (a.agents || []).length);
    _setStat("statSkills", (s.skills || []).length);
    _setStat("statWorkflows", (w.workflows || []).length);
  } catch (e) {}
}
window.loadBrainStats = loadBrainStats;   // Studio gọi lại sau khi tạo/xoá

document.querySelectorAll(".bstat").forEach(btn =>
  btn.addEventListener("click", () => {
    if (window.openStudio) window.openStudio(btn.dataset.tab);
  }));

async function doReflect(auto) {
  if (reflecting) return;
  reflecting = true;
  turnsSinceReflect = 0;
  if (!auto && learnBtn) { learnBtn.disabled = true; learnBtn.innerHTML = ic("brain") + " Đang học..."; }
  if (memResult) memResult.innerHTML = auto ? ic("brain") + " Đang tự học nền..." : "Javis đang đọc lại hội thoại và rút ra ký ức...";
  try {
    const fd = new FormData();
    fd.append("brain", currentBrainPath());
    const d = await (await fetch("/reflect", { method: "POST", body: fd })).json();
    if (d.ok) {
      if (memResult) memResult.innerHTML = (auto ? ic("brain") + " Tự học: " : "") + escapeHtml(d.summary || "Đã học xong.");
      if (d.facts != null && memCount) memCount.textContent = d.facts;
    } else {
      if (memResult) memResult.innerHTML = ic("triangle-alert", { cls: "ic-warn" }) + " " + escapeHtml(d.error || "Học thất bại");
    }
  } catch (e) {
    if (memResult) memResult.innerHTML = ic("triangle-alert", { cls: "ic-warn" }) + " Lỗi mạng";
  } finally {
    reflecting = false;
    if (!auto && learnBtn) { learnBtn.innerHTML = ic("brain") + " Học từ hội thoại"; learnBtn.disabled = false; }
  }
}

// Panel học cũ đã gỡ khỏi index.html → learnBtn có thể null (trang Tự học + engine learn.py thay thế)
if (learnBtn) learnBtn.addEventListener("click", () => doReflect(false));

// Tự học định kỳ trong phiên dài - gọi sau mỗi N lượt.
// Chỉ chạy khi panel cũ còn tồn tại; không có panel = đã chuyển sang engine tự học
// server-side (learn.py enqueue theo lượt) → không spawn /reflect ngầm nữa.
function maybeAutoLearn() {
  if (!learnBtn) return;
  turnsSinceReflect++;
  if (autoLearn && !reflecting && turnsSinceReflect >= AUTO_LEARN_EVERY) {
    doReflect(true);
  }
}

// ============================================
// File đính kèm → lưu vào Sources
// ============================================
let pendingAttachments = [];
const attachBar = document.getElementById("attachBar");
const fileInput = document.getElementById("fileInput");
const dropOverlay = document.getElementById("dropOverlay");

// ---- File đang mở trong trình sửa, GHIM vào khung chat ----
// Khác đính kèm ở hai điểm: (1) không mất sau khi gửi - nó là "file đầu vào" của cả cuộc
// trò chuyện, mở file nào thì làm việc trên file đó; (2) không upload gì cả, chỉ trỏ tới
// file có sẵn trong brain. Mở file khác thì thay chỗ, bấm nút đóng trên chip thì bỏ ghim.
let pinnedNote = null;      // {name, rel, abs, brain}
const PIN_KEY = "javis.pinnedNote";

function _pinSave() {
  try {
    if (pinnedNote) localStorage.setItem(PIN_KEY, JSON.stringify(pinnedNote));
    else localStorage.removeItem(PIN_KEY);
  } catch (e) {}
}
function _pinRestore() {
  try {
    const raw = localStorage.getItem(PIN_KEY);
    const p = raw ? JSON.parse(raw) : null;
    // Ghim của brain khác là ghim lạc - file không nằm trong brain đang mở nữa.
    if (p && p.abs && p.brain === currentBrainPath()) pinnedNote = p;
  } catch (e) {}
}

function renderChips() {
  attachBar.classList.toggle("has-items", pendingAttachments.length > 0 || !!pinnedNote);
  attachBar.innerHTML = "";
  if (pinnedNote) {
    const chip = document.createElement("div");
    chip.className = "attach-chip pinned";
    chip.setAttribute("role", "button");
    chip.tabIndex = 0;
    chip.title = `${pinnedNote.abs}\nJavis đang làm việc trên file này - bấm để mở lại trong trình sửa`;
    chip.innerHTML = `<div class="chip-ico">${ic("file-text")}</div>`
      + `<div class="chip-info"><span class="chip-name">${escapeHtml(pinnedNote.name)}</span>`
      + `<span class="chip-meta">đang mở - bấm để sửa tiếp</span></div>`
      + `<span class="chip-edit" aria-hidden="true">${ic("pen-line")}</span>`
      + `<button class="chip-x" data-unpin="1" title="Bỏ ghim file">${ic("x")}</button>`;
    // Bấm vào chip = quay lại đúng chỗ đang sửa. Nút X nằm trong chip nên phải loại nó ra,
    // không thì bỏ ghim xong lại mở file vừa bỏ ra.
    chip.addEventListener("click", (e) => {
      if (e.target.closest && e.target.closest(".chip-x")) return;
      reopenPinnedNote();
    });
    chip.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" && e.key !== " ") return;
      e.preventDefault();
      reopenPinnedNote();
    });
    attachBar.appendChild(chip);
  }
  pendingAttachments.forEach((a, i) => {
    const chip = document.createElement("div");
    chip.className = "attach-chip" + (a.uploading ? " uploading" : "");
    const thumb = a.preview
      ? `<img src="${a.preview}" alt="">`
      : `<div class="chip-ico">${a.uploading ? ic("loader", { cls: "ic-spin" }) : ic("file-text")}</div>`;
    const meta = a.uploading
      ? (a.statusText || "đang xử lý...")
      : (a.statusText ? a.statusText : (fmtSize(a.size) + (a.folder ? ` → ${escapeHtml(a.folder)}` : "")));
    chip.innerHTML = `${thumb}<div class="chip-info"><span class="chip-name">${escapeHtml(a.name)}</span><span class="chip-meta">${meta}</span></div><button class="chip-x" data-i="${i}">${ic("x")}</button>`;
    attachBar.appendChild(chip);
  });
  attachBar.querySelectorAll(".chip-x").forEach(b =>
    b.addEventListener("click", () => {
      if (b.dataset.unpin) JavisPin.clear();
      else removeAttachment(+b.dataset.i);
    }));
}

// Bấm chip ghim = quay lại chỉnh sửa chính file đó. Ba đường, thử theo thứ tự:
//   1. Trình sửa ĐÍNH của console.js (JavisOpenNoteAt) - cùng cái mở ra lúc đầu, có cây vault
//      bên cạnh; nó tự biết file đang mở sẵn thì chỉ đưa mắt về chứ không nạp lại (giữ chữ
//      đang gõ dở). Trả false khi màn hẹp hoặc chưa nạp xong console.js.
//   2. Khung sửa bung giữa màn (file-editor.js) - đường lui cho điện thoại.
//   3. Trang Tệp tin - cùng đường mà link file trong chat vẫn đi.
// pinnedNote.rel là path theo TRẦN DUYỆT (openNote ghim lại đúng cái nó nhận); cả (2) và (3)
// đều nhận path trần lẫn path gốc brain nên không phải gọt gì thêm.
function reopenPinnedNote() {
  if (!pinnedNote || !pinnedNote.rel) return;
  const rel = pinnedNote.rel;
  try {
    if (typeof window.JavisOpenNoteAt === "function" && window.JavisOpenNoteAt(rel, pinnedNote.name)) return;
  } catch (e) {}
  if (typeof window.JavisEditFile === "function") { window.JavisEditFile(rel); return; }
  if (typeof window.JavisOpenFiles === "function") window.JavisOpenFiles(rel);
}

// API cho console.js (trình sửa note) gọi khi mở/đóng file.
const JavisPin = {
  get() { return pinnedNote; },
  set(note) {
    if (!note || !note.abs) return;
    pinnedNote = { name: note.name || note.rel || "", rel: note.rel || "",
                   abs: note.abs, brain: currentBrainPath() };
    _pinSave(); renderChips();
  },
  clear() { pinnedNote = null; _pinSave(); renderChips(); },
};
window.JavisPin = JavisPin;
function fmtSize(b) {
  if (b < 1024) return b + " B";
  if (b < 1048576) return (b / 1024).toFixed(0) + " KB";
  return (b / 1048576).toFixed(1) + " MB";
}
function removeAttachment(i) {
  const a = pendingAttachments[i];
  if (a && a.preview) URL.revokeObjectURL(a.preview);
  pendingAttachments.splice(i, 1);
  renderChips();
}
function clearAttachments() {
  pendingAttachments.forEach(a => { if (a.preview) URL.revokeObjectURL(a.preview); });
  pendingAttachments = [];
  renderChips();
}

async function uploadFile(file) {
  const isImg = file.type.startsWith("image/");
  const att = {
    name: file.name || "paste.png",
    kind: isImg ? "image" : "file",
    preview: isImg ? URL.createObjectURL(file) : null,
    uploading: true, statusText: "đang tải...", path: null, size: file.size,
    sources: null, attachments: null,
  };
  pendingAttachments.push(att);
  renderChips();
  try {
    // Chỉ STAGE để Javis đọc - KHÔNG tự convert/lưu. Lưu Sources chỉ khi user yêu cầu.
    const fd = new FormData();
    fd.append("file", file, att.name);
    fd.append("brain", currentBrainPath());
    // Timeout rộng (3 phút) cho file lớn/mạng chậm; báo lỗi CỤ THỂ để dễ chẩn đoán trên VPS.
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 180000);
    let resp;
    try {
      resp = await fetch("/upload", { method: "POST", body: fd, signal: ctrl.signal });
    } finally {
      clearTimeout(timer);
    }
    if (!resp.ok) { att.uploading = false; att.statusText = "lỗi máy chủ (" + resp.status + ")"; renderChips(); return; }
    const up = await resp.json();
    if (!up.ok) { att.uploading = false; att.statusText = up.error ? ("lỗi: " + up.error) : "lỗi upload"; renderChips(); return; }
    att.path = up.staged; att.name = up.name; att.size = up.size; att.kind = up.kind;
    att.sources = up.sources; att.attachments = up.attachments;
    att.uploading = false; att.statusText = "";
  } catch (e) {
    att.uploading = false;
    att.statusText = (e && e.name === "AbortError") ? "quá thời gian tải" : "lỗi mạng";
  }
  renderChips();
}

document.getElementById("attachBtn").addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => {
  [...fileInput.files].forEach(uploadFile);
  fileInput.value = "";
});

// Dán ảnh (Ctrl+V) + dán VĂN BẢN SIÊU DÀI thành file .txt đính kèm (kiểu Claude):
// bài dài nhồi thẳng vào ô chat vừa khó đọc vừa nặng khung hội thoại - biến thành
// file thì Javis đọc trọn vẹn còn màn hình chỉ hiện một chip gọn.
const PASTE_TXT_CHARS = 1500;   // vượt MỘT trong hai ngưỡng là thành file
const PASTE_TXT_LINES = 25;
function pasteAsTxt(text) {
  const d = new Date(), p = n => String(n).padStart(2, "0");
  const name = `van-ban-dan-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}.txt`;
  const f = new File([new Blob([text], { type: "text/plain" })], name, { type: "text/plain" });
  uploadFile(f);
}
document.addEventListener("paste", (e) => {
  const items = e.clipboardData?.items;
  if (!items) return;
  for (const it of items) {
    if (it.kind === "file") {
      const f = it.getAsFile();
      if (f) { uploadFile(f); e.preventDefault(); }
    }
  }
  // Văn bản dài: CHỈ khi đang dán vào ô chat - không cướp paste của các ô khác
  // (form Kết nối, đặt tên brain...). Ô chat ngắn vẫn dán chữ bình thường.
  if (e.defaultPrevented || e.target !== chatInput) return;
  const txt = e.clipboardData.getData("text/plain") || "";
  if (txt.length > PASTE_TXT_CHARS || txt.split("\n").length > PASTE_TXT_LINES) {
    e.preventDefault();
    pasteAsTxt(txt);
  }
});

// Kéo-thả file
let dragDepth = 0;
window.addEventListener("dragenter", (e) => {
  if (e.dataTransfer && [...e.dataTransfer.types].includes("Files")) {
    dragDepth++; dropOverlay.classList.add("show");
  }
});
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("dragleave", () => { if (--dragDepth <= 0) { dragDepth = 0; dropOverlay.classList.remove("show"); } });
window.addEventListener("drop", (e) => {
  e.preventDefault(); dragDepth = 0; dropOverlay.classList.remove("show");
  if (e.dataTransfer?.files) [...e.dataTransfer.files].forEach(uploadFile);
});

// ============================================
// Events
// ============================================
chatInput.addEventListener("input", () => {
  chatInput.style.height = "auto";
  // Ở trang Trò chuyện (body.on-chat) cho ô nhập cao hơn để gõ dài dễ hơn. Trước đây mốc là
  // .chat-zoomed của lớp phóng to; lớp đó đã bỏ, phóng to giờ là chuyển hẳn sang trang chat.
  const _cap = document.body.classList.contains("on-chat") ? 220 : 90;
  chatInput.style.height = Math.min(chatInput.scrollHeight, _cap) + "px";
});
chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
sendBtn.addEventListener("click", () => sendMessage());

// Chế độ luôn nghe (hands-free): bấm 1 lần → nghe liên tục đến khi bấm lại
let handsFree = false;
voiceBtn.addEventListener("click", () => {
  if (!voice.isSupported()) { alert("Trình duyệt không hỗ trợ giọng nói. Dùng Chrome/Edge."); return; }
  handsFree = !handsFree;
  voiceBtn.classList.toggle("handsfree", handsFree);
  if (handsFree) {
    voice.startListening();
  } else {
    voice.stopListening();
    setOrbState("", "SẴN SÀNG");
  }
});

// Tự nghe lại khi rảnh (không đang xử lý, không đang nói) - giữ mic sống ở hands-free
setInterval(() => {
  if (handsFree && !voice.isListening && !isProcessing && !voice.isSpeaking()) {
    voice.startListening();
  }
}, 500);

let spacePressed = false;
document.addEventListener("keydown", (e) => {
  // KHÔNG cướp phím Space khi con trỏ đang ở BẤT KỲ ô nhập nào (input/textarea/select/
  // contenteditable) - nếu không sẽ không gõ được dấu cách trong form skill, editor file, settings…
  const _ae = document.activeElement;
  const _typing = _ae && (_ae.tagName === "INPUT" || _ae.tagName === "TEXTAREA" || _ae.tagName === "SELECT" || _ae.isContentEditable);
  if (e.code === "Space" && !handsFree && !spacePressed && !_typing) {
    e.preventDefault(); spacePressed = true; voice.startListening();
  }
  if (e.code === "Escape") {
    // Esc chỉ thoát chế độ rảnh tay + tắt mic + đóng popup node nếu đang mở. KHÔNG còn dừng câu
    // trả lời hay ngắt Javis đang nói (đã bỏ theo yêu cầu - đã có nút bật/tắt tiếng và nút Dừng).
    handsFree = false; voiceBtn.classList.remove("handsfree");
    voice.stopListening();
    if (typeof closeNodePopup === "function") closeNodePopup();
  }
});
document.addEventListener("keyup", (e) => {
  if (e.code === "Space" && spacePressed) { spacePressed = false; voice.stopListening(); }
});

// Reset
document.getElementById("resetBtn").addEventListener("click", () => {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ action: "reset" }));
  chatArea.innerHTML = "";
  convo = []; savedSessionId = null;   // xoá phiên đã lưu (số liệu giữ nguyên)
  persistSession();
});

// Voice picker
const voicePickerBtn = document.getElementById("voicePickerBtn");
const voicePopover = document.getElementById("voicePopover");
const rateSlider = document.getElementById("rateSlider");
const rateLabel = document.getElementById("rateLabel");
const savedVoice = localStorage.getItem("javis.voice") || "vi-VN-HoaiMyNeural";
const savedRate = parseFloat(localStorage.getItem("javis.rate") || "1.10");
document.querySelector(`input[name="voice"][value="${savedVoice}"]`)?.click();
rateSlider.value = savedRate; rateLabel.textContent = savedRate.toFixed(2) + "×";
voice.setVoice(savedVoice); voice.setRate(rateToPct(savedRate));
function rateToPct(r) { const p = ((r - 1) * 100).toFixed(0); return (p >= 0 ? "+" : "") + p + "%"; }
voicePickerBtn.addEventListener("click", (e) => { e.stopPropagation(); voicePopover.classList.toggle("open"); });
document.addEventListener("click", (e) => { if (!voicePopover.contains(e.target) && e.target !== voicePickerBtn) voicePopover.classList.remove("open"); });
document.querySelectorAll('input[name="voice"]').forEach(r => r.addEventListener("change", () => { voice.setVoice(r.value); localStorage.setItem("javis.voice", r.value); }));
const savedRecLang = localStorage.getItem("javis.recLang") || "vi-VN";
const recLangInput = document.querySelector(`input[name="recognitionLang"][value="${savedRecLang}"]`);
if (recLangInput) recLangInput.checked = true;
voice.setRecognitionLang(savedRecLang);
document.querySelectorAll('input[name="recognitionLang"]').forEach(r => r.addEventListener("change", () => { voice.setRecognitionLang(r.value); localStorage.setItem("javis.recLang", r.value); }));
rateSlider.addEventListener("input", () => { const r = parseFloat(rateSlider.value); rateLabel.textContent = r.toFixed(2) + "×"; voice.setRate(rateToPct(r)); localStorage.setItem("javis.rate", r.toString()); });
document.getElementById("testVoiceBtn").addEventListener("click", () => {
  const v = document.querySelector('input[name="voice"]:checked').value;
  voice.speak(v.includes("HoaiMy") ? "Xin chào, em là HoaiMy, trợ lý của anh." : "Xin chào, tôi là NamMinh, trợ lý của bạn.");
});
ttsToggle.addEventListener("click", () => {
  const enabled = voice.toggleTTS();
  ttsToggle.classList.toggle("muted", !enabled);
});

// Resume AudioContext khi user tương tác lần đầu (để analyser pulse hoạt động)
function resumeAudio() {
  try { voice._ensureCtx(); } catch (e) {}
}
document.addEventListener("click", resumeAudio, { once: true });
document.addEventListener("keydown", resumeAudio, { once: true });

// ============================================
// Badge engine+model (sự thật, không hỏi model)
// ============================================
// Nhãn hiển thị cho TỪNG provider. Trước đây chỉ có hai nhánh openrouter-hoặc-CLI, nên chọn
// Groq/Gemini/OpenAI đều bị dán nhãn "CLI" - vừa sai, vừa phạm đúng luật trong CLAUDE.md là
// phải trả lời ĐÚNG engine đang chạy. Chủ repo chụp lại cảnh badge ghi "CLI · openai/gpt-oss-120b"
// trong khi thanh model ngay bên cạnh ghi "Groq".
const ENGINE_LABEL = {
  "anthropic-cli": "Claude Code", "openai-oauth": "ChatGPT", "openrouter": "OpenRouter",
  "openai": "OpenAI", "anthropic-api": "Anthropic", "gemini": "Gemini", "groq": "Groq",
  "ollama": "Ollama",
};
// Một dòng nhỏ dưới câu trả lời: lượt này chạy ở chế độ nào, và tốn bao nhiêu
// token vào. Trước đây chuyện này hoàn toàn vô hình - chỉ lộ ra khi nhà cung cấp báo vượt hạn
// mức, tức là đã muộn. Thấy được thì người dùng tự biết mức vừa bật có ăn thật hay không.
// Tên NÓI ĐÚNG NÓ LÀM GÌ, không phải nó cũ hay mới. "Đường cũ" là góc nhìn của người viết
// code; với người dùng đó là chế độ gửi đủ mọi thứ, an toàn nhất, và đúng là thứ họ chọn khi
// bấm "Tắt" - gọi nó là "cũ" vừa nghe như đang xin lỗi, vừa làm người ta tưởng máy đang hỏng.
// Tên ở đây khớp tên nút bên trang Mức dùng để nhìn một dòng là biết mình đang ở đâu.
const CTX_PATH_LABEL = {
  legacy: "Đầy đủ", sources: "Tối ưu", fast: "Tức thì",
  readonly: "Tra cứu", orchestrator: "Tra cứu sâu", write: "Thực thi",
  workflow: "Quy trình",
  // Bot chuyên trách vốn nhẹ hơn cả mức Siêu tiết kiệm (không CLAUDE.md, không MEMORY.md,
  // không đặc tả tool) nên nó có tên riêng - gộp vào "Đầy đủ" là nói ngược hẳn sự thật.
  bot: "Bot chuyên trách",
};
function _renderCtxLine(msgEl, data) {
  if (!msgEl || !data || !data.ctx_path) return;
  const cu = data.ctx_path === "legacy";
  const ten = CTX_PATH_LABEL[data.ctx_path] || data.ctx_path;
  const tok = Number(data.ctx_in) || 0;
  const old = msgEl.querySelector(".msg-ctx");
  if (old) old.remove();
  const el = document.createElement("div");
  el.className = "msg-ctx" + (cu ? "" : " saved");
  // Bấm vào là sang trang Mức dùng, nơi có khối chọn mức ngay đầu trang - thấy chế độ đang
  // chạy mà không biết chỉnh ở đâu thì thông tin đó cũng chỉ để bực mình.
  el.dataset.usageGoto = "usage";
  el.title = cu ? "Đang gửi đủ mọi thứ. Bấm để chọn mức tiết kiệm."
                : "Đang tiết kiệm token. Bấm để xem chi tiết.";
  el.textContent = ten + (tok ? " · " + _fmtTok(tok) + " token" : "");
  msgEl.appendChild(el);
}

function setEngineBadge(engine, model) {
  const el = document.getElementById("engineBadge");
  if (!el) return;
  const label = ENGINE_LABEL[engine] || engine || "Chưa rõ";
  el.textContent = label + (model ? " · " + model : "");
  // Chỉ còn hai lớp màu: giữ nguyên bộ mặt cũ, không đẻ thêm 7 biến thể CSS.
  el.className = "engine-badge " + (engine === "openrouter" ? "or" : "cli");
}
async function refreshTgStatus() {
  const el = document.getElementById("setTgStatus");
  if (!el) return;
  try {
    const s = await (await fetch("/telegram/status")).json();
    if (!s.enabled) el.innerHTML = ic("circle", { cls: "ic-fill ic-dim" }) + " Tắt";
    else if (!s.token_set) el.innerHTML = ic("triangle-alert", { cls: "ic-warn" }) + " Đã bật nhưng chưa có token";
    else el.innerHTML = s.running ? ic("circle", { cls: "ic-fill ic-ok" }) + " Đang chạy" + (s.chat_id ? " · chỉ chat_id " + s.chat_id : " · MỌI người (nên đặt chat_id)") : ic("loader") + " Chưa chạy (lưu lại)";
    // Menu lệnh "/" đặt hụt: bot vẫn chạy nên mọi thứ ở trên vẫn xanh, chỉ là gõ "/" trong
    // Telegram không sổ ra danh sách lệnh. Không nói ra thì không ai đoán được vì sao.
    if (s.loi_menu_lenh) el.innerHTML += '<div class="set-note">' + ic("triangle-alert", { cls: "ic-warn" }) + " " + escapeHtml(s.loi_menu_lenh) + "</div>";
  } catch (e) { el.textContent = ""; }
}
// Xuất ra window: console.js gọi lại sau khi đổi model để badge engine không bị cũ.
// Model chính HIỆU LỰC, soi theo đúng thứ tự server dùng (_effective_main trong main.py):
// model.main nếu đã đặt, không thì suy từ trường engine cũ. Đọc thiếu bước này là badge
// đứng ì ở "CLI" cho mọi provider API.
function _mainProviderModel(m) {
  const main = m.main || {};
  if (main.provider) return [main.provider, main.model || ""];
  if (m.engine === "openrouter") return ["openrouter", m.openrouter_model || ""];
  if (m.engine === "anthropic-api") return ["anthropic-api", m.claude_model || ""];
  return ["anthropic-cli", m.claude_model || "mặc định"];
}
async function refreshEngineBadge() {
  try {
    const s = await (await fetch("/settings")).json();
    const [prov, model] = _mainProviderModel(s.model || {});
    setEngineBadge(prov, model || "mặc định");
  } catch (e) {}
}

// ============================================
// Mức dùng (token Javis tự đo, đa nhà cung cấp) - panel sidebar
// ============================================
const _PROV_LABEL = { cli: "Claude Code", codex: "ChatGPT", openrouter: "OpenRouter", openai: "OpenAI", "anthropic-api": "Anthropic", gemini: "Gemini", groq: "Groq" };
function _fmtTok(n) {
  n = +n || 0;
  if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(n >= 1e4 ? 0 : 1) + "k";
  return "" + n;
}
function _shortModel(m) { return (m || "").split("/").pop().replace(/^(claude-|gpt-)/, "").slice(0, 22); }
async function refreshUsage() {
  const el = document.getElementById("usagePanel"); if (!el) return;
  let d; try { d = await (await fetch("/usage")).json(); } catch (e) { return; }
  // Hôm nay chưa có lượt nào → hiện TỔNG tích luỹ để không trống trơn.
  let src = d.today, scope = "hôm nay";
  if ((!src || !(src.items || []).length) && d.all_time && (d.all_time.items || []).length) { src = d.all_time; scope = "tổng"; }
  const items = (src && src.items) || [];
  const tot = (src && src.total) || { in: 0, out: 0, cost: 0 };
  const row = (nameHtml, tok, extra) => `<div style="display:flex;justify-content:space-between;gap:6px;font-size:11px;padding:1px 0;${extra || ""}"><span style="color:var(--text2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${nameHtml}</span><span style="color:#7aa2ff;white-space:nowrap;font-variant-numeric:tabular-nums">${tok}</span></div>`;
  let html;
  if (!items.length) {
    html = `<div class="mcp-item dim">Chưa có lượt nào hôm nay</div>`;
  } else {
    html = items.map(i => {
      const lbl = _PROV_LABEL[i.provider] || escapeHtml(i.provider);
      const cost = i.cost > 0 ? ` · $${i.cost.toFixed(i.cost < 0.01 ? 4 : 2)}` : "";
      const nm = `${escapeHtml(lbl)} <span class="dim">${escapeHtml(_shortModel(i.model))}</span>`;
      return row(nm, `${_fmtTok(i.in)}↑ ${_fmtTok(i.out)}↓${cost}`);
    }).join("");
    html += row(`<b>Tổng ${scope}</b>`, `<b>${_fmtTok(tot.in)}↑ ${_fmtTok(tot.out)}↓${tot.cost > 0 ? " · $" + tot.cost.toFixed(2) : ""}</b>`, "border-top:1px solid var(--hairline);margin-top:2px;padding-top:3px");
  }
  html += await _usageSavingRow();
  if (d.openrouter && d.openrouter.remaining != null) {
    html += row("OpenRouter còn", `$${(+d.openrouter.remaining).toFixed(2)}`, "margin-top:4px;color:var(--green)");
  }
  el.innerHTML = html;
}

// Một dòng "đang tiết kiệm bao nhiêu" ngay dưới bảng Mức dùng.
//
// Vì sao đặt ở đây: panel này trả lời "tiêu bao nhiêu", nhưng con số đó vô nghĩa nếu không
// biết mình đang ở mức nào. Người dùng nhìn thấy 40k token mà không biết đáng lẽ là 400k, hay
// đáng lẽ chỉ 4k. Ghép hai thứ lại thì một liếc mắt là đủ hiểu.
//
// Cache 60 giây: refreshUsage chạy sau MỖI lượt chat, mà /runtime/muc phải dựng lại prompt
// thật để ước lượng - gọi mỗi lượt là tự bắt mình trả giá cho cái panel đo giá.
let _savingCache = { at: 0, html: "" };
async function _usageSavingRow() {
  const now = Date.now();
  if (now - _savingCache.at < 60000) return _savingCache.html;
  let d;
  try { d = await (await fetch("/runtime/muc")).json(); }
  catch (e) { return _savingCache.html; }
  const ten = ((d.danh_sach || []).find(p => p.id === d.muc) || {}).nhan
    || (d.muc === "custom" ? "Tự chỉnh" : "?");
  const dod = d.do_duoc || {};
  const uoc = ((d.uoc_tinh || {}).muc || {})[d.muc] || {};
  // Ưu tiên số ĐO ĐƯỢC; chưa đủ dữ liệu thì mới dùng ước lượng, và nói rõ là ước lượng.
  let phu;
  if (dod.du_du_lieu) phu = `giảm ${dod.phan_tram}% (đo thật)`;
  else if (d.muc === "off") phu = "chưa bật tiết kiệm";
  else if (uoc.phan_tram) phu = `giảm ~${uoc.phan_tram}% (ước lượng)`;
  else phu = "chưa đo được";
  const html = `<div style="display:flex;justify-content:space-between;gap:6px;font-size:11px;padding:3px 0 0;margin-top:3px;border-top:1px solid var(--hairline);cursor:pointer" data-usage-goto="usage" title="Mở trang Mức dùng">`
    + `<span style="color:var(--text2)">Tiết kiệm: <b>${escapeHtml(ten)}</b></span>`
    + `<span style="color:#7aa2ff;white-space:nowrap">${escapeHtml(phu)}</span></div>`;
  _savingCache = { at: now, html };
  return html;
}

// Bấm vào dòng đó thì sang thẳng trang Mức dùng - đỡ phải đi tìm trong rail.
document.addEventListener("click", (e) => {
  const hit = e.target && e.target.closest && e.target.closest("[data-usage-goto]");
  if (!hit) return;
  try { window.Alpine.store("nav").go(hit.dataset.usageGoto); } catch (err) {}
});

// Nút thu nhỏ / mở to hộp MỨC DÙNG (nhớ trạng thái qua localStorage).
(function initUsageToggle() {
  const box = document.getElementById("usageFloat"), btn = document.getElementById("usageToggle");
  if (!box || !btn) return;
  const apply = (col) => { box.classList.toggle("collapsed", col); btn.textContent = col ? "▸" : "▾"; };
  apply(localStorage.getItem("javis.usageCollapsed") === "1");
  btn.onclick = () => {
    const col = !box.classList.contains("collapsed");
    apply(col);
    try { localStorage.setItem("javis.usageCollapsed", col ? "1" : "0"); } catch (e) {}
  };
})();

// ============================================
// Auth (đăng nhập) + Settings
// ============================================
const authOverlay = document.getElementById("authOverlay");
const settingsOverlay = document.getElementById("settingsOverlay");
let _settingsCache = null;

async function initAuth() {
  try {
    const s = await (await fetch("/auth/status")).json();
    if (s.auth_required && !s.authed) {
      authOverlay.classList.add("open");   // chặn cho tới khi đăng nhập
    }
  } catch (e) {}
}

// Cổng đăng nhập THỐNG NHẤT (thay initSetup+initAuth ở boot):
// - đã đăng nhập (hoặc local không bắt buộc) → onboarding tùy chọn.
// - public/đã đặt mật khẩu mà CHƯA có tài khoản → ÉP wizard tạo tài khoản (mật khẩu bắt buộc).
// - đã có tài khoản mà chưa đăng nhập → màn đăng nhập.
let _wizardMandatory = false;
async function initAuthGate() {
  let s = {};
  try { s = await (await fetch("/auth/status")).json(); } catch (e) {}
  if (s.authed) { initSetup(); return; }
  if (s.needs_setup) {
    _wizardMandatory = !!s.require_login;
    const wz = document.getElementById("setupWizard");
    if (!wz) { authOverlay.classList.add("open"); return; }
    if (_wizardMandatory) {
      const pass = document.getElementById("wzPass"); if (pass) pass.required = true;
      const tw = document.getElementById("wzTokenWrap"); if (tw) tw.style.display = "";
      const note = document.getElementById("wzErr"); if (note) note.textContent = "Đặt tài khoản + mật khẩu (≥8 ký tự) + MÃ THIẾT LẬP để bảo vệ Javis trên server công khai.";
    }
    wz.classList.add("open");
  } else {
    authOverlay.classList.add("open");
  }
}
document.getElementById("authSubmit").addEventListener("click", async () => {
  const codeWrap = document.getElementById("authCodeWrap");
  const codeInp = document.getElementById("authCode");
  const fd = new FormData();
  fd.append("username", document.getElementById("authUser").value.trim());
  fd.append("password", document.getElementById("authPass").value);
  if (codeInp && codeInp.value.trim()) fd.append("code", codeInp.value.trim());
  const err = document.getElementById("authErr"); err.textContent = "";
  try {
    const r = await fetch("/auth/login", { method: "POST", body: fd });
    const d = await r.json();
    if (d.ok) { location.reload(); return; }
    // needs_2fa = mật khẩu ĐÚNG rồi, chỉ còn thiếu mã. Hiện ô mã và đưa con trỏ vào đó luôn,
    // đừng bắt người ta tự nhận ra là có thêm một ô mới xuất hiện bên dưới.
    if (d.needs_2fa && codeWrap) {
      codeWrap.style.display = "";
      if (codeInp) { codeInp.value = ""; codeInp.focus(); }
    }
    err.textContent = d.error || "Đăng nhập thất bại";
  } catch (e) { err.textContent = "Lỗi mạng"; }
});
["authPass", "authCode"].forEach((id) => {
  const el = document.getElementById(id);
  if (el) el.addEventListener("keydown", (e) => { if (e.key === "Enter") document.getElementById("authSubmit").click(); });
});

// ---- Settings ----
async function openSettings() {
  settingsOverlay.classList.add("open");
  try {
    const s = await (await fetch("/settings")).json();
    _settingsCache = s;
    document.getElementById("setWsName").value = s.workspace_name || "";
    document.getElementById("setEngine").value = (s.model && s.model.engine) || "cli";
    document.getElementById("setClaudeModel").value = (s.model && s.model.claude_model) || "";
    loadOrModels((s.model && s.model.openrouter_model) || "");
    document.getElementById("setKeyHint").textContent = (s.model && s.model.openrouter_key_set) ? "(đã lưu " + s.model.openrouter_key + ")" : "(chưa có)";
    document.getElementById("setTgEnabled").checked = !!(s.telegram && s.telegram.enabled);
    document.getElementById("setTgChat").value = (s.telegram && s.telegram.chat_id) || "";
    document.getElementById("setTgHint").textContent = (s.telegram && s.telegram.token_set) ? "(đã lưu " + s.telegram.token + ")" : "(chưa có)";
    refreshTgStatus();
    await refreshAuthRow();
  } catch (e) {}
}
// Đổ trạng thái tài khoản vào khối #quickSet. Đọc /auth/status chứ không dựa vào _settingsCache:
// khối này còn được NHÚNG sang trang Cài đặt của console (console.js renderSettings) mà đường đó
// KHÔNG đi qua openSettings(), nên cache rỗng - và cache rỗng thì nút Lưu tưởng là "chưa có tài
// khoản" rồi đi nhầm sang /auth/setup, nhận 400 "Đã có tài khoản". Đó đúng là lỗi bấm-Lưu-không-ăn.
async function refreshAuthRow() {
  const st = document.getElementById("setAuthState");
  if (!st) return false;
  let a = {};
  try { a = await (await fetch("/auth/status")).json(); } catch (e) { return false; }
  const co = !a.needs_setup;
  st.innerHTML = co
    ? ic("check", { cls: "ic-ok" }) + " Đã đặt mật khẩu - đăng nhập bắt buộc."
    : ic("triangle-alert", { cls: "ic-warn" }) + " Chưa đặt mật khẩu - ai mở trang cũng dùng được. Đặt mật khẩu trước khi lên VPS.";
  const u = document.getElementById("setAuthUser");
  if (u && a.username) u.value = a.username;
  const cur = document.getElementById("setAuthCur");
  const curLbl = document.getElementById("setAuthCurLbl");
  if (cur) { cur.hidden = !co; if (!co) cur.value = ""; }
  if (curLbl) curLbl.hidden = !co;
  const p = document.getElementById("setAuthPass");
  if (p) p.placeholder = co ? "Mật khẩu mới (để trống nếu chỉ đổi tên)" : "Đặt mật khẩu (tối thiểu 8 ký tự)";
  return co;
}
window.__javisRefreshAuthRow = refreshAuthRow;
function _saveSetting(section, dataObj, btn) {
  const fd = new FormData();
  fd.append("section", section);
  fd.append("data", JSON.stringify(dataObj));
  const old = btn.textContent; btn.disabled = true; btn.textContent = "Đang lưu...";
  return fetch("/settings", { method: "POST", body: fd }).then(r => r.json()).then(d => {
    btn.innerHTML = d.ok ? ic("check", { cls: "ic-ok" }) + " Đã lưu" : (ic("triangle-alert", { cls: "ic-warn" }) + " " + escapeHtml(d.error || "lỗi"));
    setTimeout(() => { btn.textContent = old; btn.disabled = false; }, 1500);
    return d;
  }).catch(() => { btn.textContent = old; btn.disabled = false; });
}
if (document.getElementById("settingsBtn")) {
  document.getElementById("settingsBtn").addEventListener("click", openSettings);
  document.getElementById("settingsClose").addEventListener("click", () => settingsOverlay.classList.remove("open"));
  settingsOverlay.addEventListener("click", (e) => { if (e.target === settingsOverlay) settingsOverlay.classList.remove("open"); });

  document.getElementById("saveGeneral").addEventListener("click", (e) => {
    _saveSetting("general", { workspace_name: document.getElementById("setWsName").value.trim() }, e.target)
      .then(() => { document.getElementById("workspaceName").textContent = document.getElementById("setWsName").value.trim() || "Javis OS"; });
  });
  document.getElementById("saveModel").addEventListener("click", (e) => {
    const sel = document.getElementById("setOrModelSel");
    const orModel = (sel.value === "__custom__") ? document.getElementById("setOrModel").value.trim() : sel.value;
    const d = { engine: document.getElementById("setEngine").value, claude_model: document.getElementById("setClaudeModel").value, openrouter_model: orModel };
    const k = document.getElementById("setOrKey").value.trim(); if (k) d.openrouter_key = k;
    _saveSetting("model", d, e.target).then(() => { document.getElementById("setOrKey").value = ""; openSettings(); refreshEngineBadge(); });
  });
  // Dropdown model OpenRouter: chọn custom → hiện ô nhập tay
  document.getElementById("setOrModelSel").addEventListener("change", (e) => {
    document.getElementById("setOrModel").style.display = (e.target.value === "__custom__") ? "block" : "none";
  });
  document.getElementById("loadModelsBtn").addEventListener("click", (e) => {
    e.preventDefault();
    const cur = document.getElementById("setOrModelSel").value;
    loadOrModels(cur === "__custom__" ? document.getElementById("setOrModel").value.trim() : cur, true);
  });
  document.getElementById("saveTelegram").addEventListener("click", (e) => {
    document.getElementById("setTgEnabled").checked = true;   // "Lưu & bật" = luôn bật
    const d = { enabled: true, chat_id: document.getElementById("setTgChat").value.trim() };
    const t = document.getElementById("setTgToken").value.trim(); if (t) d.token = t;
    _saveSetting("telegram", d, e.target).then(() => { document.getElementById("setTgToken").value = ""; setTimeout(() => { openSettings(); refreshTgStatus(); }, 600); });
  });
  // Toggle bật/tắt tức thì (off → dừng bot, on → chạy lại)
  document.getElementById("setTgEnabled").addEventListener("change", async (ev) => {
    const fd = new FormData(); fd.append("section", "telegram"); fd.append("data", JSON.stringify({ enabled: ev.target.checked }));
    try { await fetch("/settings", { method: "POST", body: fd }); } catch (e) {}
    setTimeout(refreshTgStatus, 600);
  });
  document.getElementById("testTelegram").addEventListener("click", async (e) => {
    const btn = e.target; btn.disabled = true; const old = btn.textContent; btn.textContent = "Đang gửi...";
    try {
      const r = await (await fetch("/telegram/test", { method: "POST" })).json();
      btn.innerHTML = r.ok
        ? (r.total > 1 ? `${ic("check", { cls: "ic-ok" })} Đã gửi ${Number(r.sent) || 0}/${Number(r.total) || 0} ID` + (r.error ? " (có lỗi)" : "") : ic("check", { cls: "ic-ok" }) + " Đã gửi (xem Telegram)")
        : (ic("triangle-alert", { cls: "ic-warn" }) + " " + escapeHtml(r.error || "lỗi"));
    } catch (e) { btn.innerHTML = ic("triangle-alert", { cls: "ic-warn" }) + " lỗi mạng"; }
    setTimeout(() => { btn.textContent = old; btn.disabled = false; }, 2500);
  });
  document.getElementById("savePassword").addEventListener("click", async (e) => {
    const user = document.getElementById("setAuthUser").value.trim();
    const pass = document.getElementById("setAuthPass").value;
    const curEl = document.getElementById("setAuthCur");
    const btn = e.target; const old = btn.textContent;
    const bao = (ok, msg) => {
      btn.innerHTML = (ok ? ic("check", { cls: "ic-ok" }) : ic("triangle-alert", { cls: "ic-warn" })) + " " + escapeHtml(msg);
      btn.disabled = false;
      setTimeout(() => { btn.textContent = old; }, 3000);
    };
    // Hỏi trạng thái TƯƠI ngay lúc bấm. Trang Cài đặt của console nhúng khối này mà không gọi
    // openSettings(), nên tin vào _settingsCache là đi nhầm nhánh và bấm Lưu không ăn.
    let hasPw = false;
    try { hasPw = !(await (await fetch("/auth/status")).json()).needs_setup; }
    catch (err) { bao(false, "Không đọc được trạng thái đăng nhập."); return; }
    btn.disabled = true; btn.textContent = "Đang lưu...";
    if (!hasPw) {
      // Lần đầu đặt mật khẩu → /auth/setup (cấp cookie luôn)
      if (!pass || pass.length < 8) { bao(false, "Mật khẩu tối thiểu 8 ký tự."); return; }
      const fd = new FormData(); fd.append("username", user || "admin"); fd.append("password", pass);
      try {
        const d = await (await fetch("/auth/setup", { method: "POST", body: fd })).json();
        bao(!!d.ok, d.ok ? "Đã đặt mật khẩu" : (d.error || "lỗi"));
        if (d.ok) { document.getElementById("setAuthPass").value = ""; openSettings(); }
      } catch (err) { bao(false, "lỗi mạng"); }
      return;
    }
    // Đã có tài khoản → ĐỔI qua /auth/password (đòi mật khẩu hiện tại). /auth/setup là đường
    // lần-đầu, gọi nó ở đây chỉ nhận về "Đã có tài khoản - hãy đăng nhập".
    const cur = curEl ? curEl.value : "";
    if (!cur) { bao(false, "Nhập mật khẩu hiện tại."); return; }
    if (pass && pass.length < 8) { bao(false, "Mật khẩu mới tối thiểu 8 ký tự."); return; }
    if (!pass && !user) { bao(false, "Chưa đổi gì cả."); return; }
    const fd = new FormData();
    fd.append("current_password", cur); fd.append("username", user);
    if (pass) fd.append("password", pass);
    try {
      const d = await (await fetch("/auth/password", { method: "POST", body: fd })).json();
      bao(!!d.ok, d.ok ? (pass ? "Đã đổi mật khẩu" : "Đã đổi tên đăng nhập") : (d.error || "lỗi"));
      if (d.ok) {
        document.getElementById("setAuthPass").value = "";
        if (curEl) curEl.value = "";
        refreshAuthRow();
      }
    } catch (err) { bao(false, "lỗi mạng"); }
  });
  document.getElementById("logoutBtn").addEventListener("click", async () => {
    await fetch("/auth/logout", { method: "POST" }); location.reload();
  });
  document.getElementById("disableAuthBtn").addEventListener("click", async () => {
    if (!confirm("Tắt đăng nhập? Ai mở trang cũng dùng được (chỉ nên dùng khi chạy máy cá nhân, không phải VPS).")) return;
    await fetch("/auth/disable", { method: "POST" }); location.reload();
  });
}
// Lối thoát khi quên mật khẩu (trên màn đăng nhập)
if (document.getElementById("authForgot")) {
  document.getElementById("authForgot").addEventListener("click", () => {
    const r = document.getElementById("authResetInfo");
    r.style.display = r.style.display === "none" ? "block" : "none";
  });
}

// ---- OpenRouter: tải danh sách model động ----
let _orModelsLoaded = false;
async function loadOrModels(saved, force) {
  const sel = document.getElementById("setOrModelSel");
  const input = document.getElementById("setOrModel");
  if (!sel) return;
  if (!_orModelsLoaded || force) {
    sel.innerHTML = '<option value="__custom__">Nhập tên model khác (custom)…</option><option disabled>đang tải…</option>';
    try {
      const d = await (await fetch("/openrouter/models")).json();
      sel.innerHTML = '<option value="__custom__">Nhập tên model khác (custom)…</option>';
      (d.models || []).forEach(m => {
        const o = document.createElement("option");
        o.value = m.id; o.textContent = m.id;
        sel.appendChild(o);
      });
      _orModelsLoaded = (d.models || []).length > 0;
    } catch (e) {
      sel.innerHTML = '<option value="__custom__">Nhập tên model khác (custom)…</option>';
    }
  }
  // Chọn model đã lưu nếu có trong list, ngược lại dùng custom
  if (saved && [...sel.options].some(o => o.value === saved)) {
    sel.value = saved; input.style.display = "none";
  } else if (saved) {
    sel.value = "__custom__"; input.value = saved; input.style.display = "block";
  } else {
    sel.value = "__custom__"; input.style.display = "block";
  }
}

// ---- Bộ cài đặt lần đầu ----
function _fd(obj) { const f = new FormData(); Object.entries(obj).forEach(([k, v]) => f.append(k, v)); return f; }
async function initSetup() {
  try {
    const s = await (await fetch("/settings")).json();
    // Đã setup, đã có tài khoản, hoặc bị chặn auth (đang ở màn đăng nhập) → không hiện wizard
    if (s.setup_done || (s.auth && s.auth.has_password) || s.auth_required) return false;
    document.getElementById("wzWsName").value = s.workspace_name || "";
    document.getElementById("setupWizard").classList.add("open");
    return true;
  } catch (e) { return false; }
}
if (document.getElementById("wzFinish")) {
  document.getElementById("wzFinish").addEventListener("click", async () => {
    const err = document.getElementById("wzErr"); err.textContent = "";
    const ws = document.getElementById("wzWsName").value.trim();
    const user = document.getElementById("wzUser").value.trim();
    const pass = document.getElementById("wzPass").value;
    const prov = (document.querySelector('input[name="wzprov"]:checked') || {}).value || "anthropic-cli";
    const btn = document.getElementById("wzFinish"); btn.disabled = true; btn.textContent = "Đang lưu…";
    if (_wizardMandatory && !pass) { err.textContent = "Bắt buộc đặt mật khẩu khi chạy trên server công khai."; btn.disabled = false; btn.textContent = "Bắt đầu dùng Javis →"; return; }
    try {
      if (pass) {
        const _tok = document.getElementById("wzToken");
        const d = await (await fetch("/auth/setup", { method: "POST", body: _fd({ username: user || "admin", password: pass, setup_token: _tok ? _tok.value.trim() : "" }) })).json();
        if (!d.ok) { err.textContent = d.error || "Đặt mật khẩu lỗi"; btn.disabled = false; btn.textContent = "Bắt đầu dùng Javis →"; return; }
      }
      await fetch("/settings", { method: "POST", body: _fd({ section: "general", data: JSON.stringify({ workspace_name: ws, setup_done: true }) }) });
      const _PM = { "anthropic-cli": "sonnet", "openai-oauth": "gpt-5.5", "openrouter": "openai/gpt-4o-mini" };
      const _mp = { main: { provider: prov, model: _PM[prov] || "sonnet" } };
      const _ork = (document.getElementById("wzOrKeyInput") || {}).value;
      if (prov === "openrouter" && _ork && _ork.trim()) _mp.openrouter_key = _ork.trim();
      await fetch("/settings", { method: "POST", body: _fd({ section: "model", data: JSON.stringify(_mp) }) });
      location.reload();
    } catch (e) { err.textContent = "Lỗi mạng"; btn.disabled = false; btn.textContent = "Bắt đầu dùng Javis →"; }
  });
}

// Wizard - chọn nhà cung cấp (card radio) + hiện ô key OpenRouter + gợi ý cách kết nối
(function () {
  const cards = document.querySelectorAll("#wzProv .wz-card");
  if (!cards.length) return;
  const orKey = document.getElementById("wzOrKey");
  const hint = document.getElementById("wzProvHint");
  const HINTS = {
    "anthropic-cli": "Sau khi vào: đăng nhập Claude 1 lần - chạy <code>claude auth login --claudeai</code> trong terminal (Hostinger: App terminal).",
    "openai-oauth": "Sau khi vào: mục <b>Models</b> → đăng nhập ChatGPT (hoặc <code>codex login</code> trong terminal).",
    "openrouter": "Lấy key tại <a href='https://openrouter.ai/keys' target='_blank' style='color:var(--link-ink)'>openrouter.ai/keys</a> rồi dán ở trên (hoặc sau ở Models).",
  };
  function pick(prov) {
    cards.forEach(c => c.classList.toggle("sel", c.dataset.prov === prov));
    const r = document.querySelector('input[name="wzprov"][value="' + prov + '"]'); if (r) r.checked = true;
    if (orKey) orKey.style.display = prov === "openrouter" ? "" : "none";
    if (hint) hint.innerHTML = HINTS[prov] || "";
  }
  cards.forEach(c => c.addEventListener("click", () => pick(c.dataset.prov)));
  pick("anthropic-cli");
})();

// ============================================
// Boot
// ============================================
initAuthGate();
refreshEngineBadge();
refreshUsage();
connect();
initStarfield();
initGraph().then(connectGraphWatch).catch(connectGraphWatch);
pumpAudioLevel();
loadMemStats();
loadBrainStats();
checkVault();
// Mặc định: tải lại trang (hoặc mở thêm tab) thì VÀO LẠI ĐÚNG HỘI THOẠI ĐANG DỞ.
// 0.9.88 từng đổi thành luôn mở khung trống; dùng thật thì mỗi lần F5 lại mất mạch chuyện
// đang nói, phải vào Lịch sử bấm lại. Muốn khung trống thì bấm nút + (hội thoại mới).
// Khôi phục lấy từ localStorage nên hiện tức thì, giữ nguyên cả ảnh đính kèm lẫn chip chọn
// đáp án - thứ mà tải lại từ server (/sessions) không có. savedSessionId sống lại theo, nên
// lượt đang chạy nền của phiên này vẫn stream tiếp vào đúng khung sau khi tải lại.
restoreSession();
// File ghim sống qua F5 luôn - tải lại trang mà mất file đang làm việc thì đúng cái phiền
// mà khôi phục hội thoại ở trên sinh ra để tránh.
_pinRestore();
renderChips();

// Đồng bộ badge engine từ module khác (console.js sau khi đổi model).
window.refreshEngineBadge = refreshEngineBadge;
