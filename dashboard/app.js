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
  try { ketThucTheoLoi(false); } catch (e) {}
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
  // Nhớ lượt vừa dừng: turn_done của nó có thể về SAU khi lượt mới đã chạy (xem _luotDaDung).
  if (sid && turns[sid] && turns[sid].running && turns[sid].id) _luotDaDung[sid] = turns[sid].id;
  if (sid && turns[sid]) turns[sid].running = false;
  setSessionRunning(sid, false);
  try { runActions(turn.turnDone()); } catch (e) {}   // bấm Dừng: hết lượt, orb theo đạo diễn
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
const voiceInterim = document.getElementById("voiceInterim");

// ---- Voice V3: chữ đang nghe hiện NGAY TRONG KHUNG CHAT (chủ dự án 2026-09-14) ----
// Trước đây chữ tạm đè lên khối não (#voiceInterim), xa cột hội thoại. Nay nó là một bong bóng
// NHÁP ở cuối cột chat, cùng vị trí tin thật sẽ xuất hiện khi gửi, như ChatGPT Voice. Rỗng thì
// gỡ bong bóng. Bong bóng nháp không vào convo, không lưu; khi gửi thì appendUserMessage thay nó.
let _nhapGiongEl = null;
function nhapGiong(text) {
  text = String(text || "").trim();
  if (voiceInterim) voiceInterim.textContent = "";
  if (!text) {
    if (_nhapGiongEl) { try { _nhapGiongEl.remove(); } catch (e) {} _nhapGiongEl = null; }
    return;
  }
  if (!_nhapGiongEl || !_nhapGiongEl.isConnected) {
    const div = document.createElement("div");
    div.className = "msg msg-user msg-nhap-giong";
    div.innerHTML = '<div class="bubble"><div class="utext"></div></div>';
    chatAppend(div);
    _nhapGiongEl = div;
  }
  _nhapGiongEl.querySelector(".utext").textContent = text;
  scrollBottom();
}
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
  // Linh vật ở mép màn hình diễn theo ĐÚNG trạng thái này, không có nguồn riêng: nếu chữ
  // trên orb nói "đang nghĩ" mà pet vẫn ngồi chớp mắt thì một trong hai đang nói dối.
  // Lớp rỗng "" của orb là trạng thái nghỉ.
  try { if (window.JavisPet) window.JavisPet.setState(state || "idle"); } catch (e) {}
  try { if (window.JavisWorkspace) window.JavisWorkspace.onChatState(state || "idle"); } catch (e) {}
}

// ============================================
// Voice
// ============================================
const attention = new window.JavisVoiceAttention.Attention();
const voice = new JavisVoice({
  lang: "vi-VN",
  acceptTranscript: (text) => !handsFree || attention.accept(text),
  onStart: () => {
    voiceBtn.classList.add("recording");
    nhapGiong("");
    runActions(turn.micOn());
  },
  onInterim: (text) => {
    if (handsFree && !attention.preview(text)) { nhapGiong(""); return; }
    nhapGiong(text);
    // Đang tạm dừng vì nghi chen ngang mà có chữ -> chen ngang THẬT: đạo diễn trả stop_tts.
    // Đọc phần Javis đã đọc ra tiếng TRƯỚC khi dừng, để tin kế tiếp mang ngắt_lời=.
    if (turn.interrupted && text) turn.setInterruptedAt(voice.lastSpokenPrefix());
    runActions(turn.interim(text));
  },
  onTranscript: (text) => {
    voiceBtn.classList.remove("recording");
    nhapGiong("");
    text = veTinTuGiong(text);   // luật CHỜ / DỪNG của đạo diễn: trả "" khi không gửi
    if (text) sendMessage(text);
  },
  onEnd: () => {
    voiceBtn.classList.remove("recording");
    // Hands-free: giữ trạng thái chờ nghe lại, đừng reset về SẴN SÀNG cho đỡ nháy.
    // Phiên nghe kết thúc mà không có chữ (tiếng ồn rồi im) thì vẫn phải hạ cờ "đang nói":
    // endpoint("") không gửi gì, chỉ trả đạo diễn về listening để tin nền được đọc tiếp.
    if (!handsFree) runActions(turn.micOff());
    else runActions(turn.endpoint(""));
  },
  onTranscribing: () => capNhatOrb(),
  onError: (err) => {
    voiceBtn.classList.remove("recording");
    // Mic hỏng hẳn thì TẮT chế độ rảnh tay. Không tắt thì vòng giữ mic 500ms bên dưới cứ mở
    // lại mãi, mỗi lần một hộp thoại chặn - người dùng bấm OK xong nửa giây sau nó nổ tiếp,
    // không còn đường nào bấm vào trang nữa. Đúng cảnh người dùng báo 04/09.
    if (voice.micHong && voice.micHong()) { tatRanhTay(); runActions(turn.errorMic(err)); }
    else runActions(turn.micOff());
    alertMic(err);
  },
  // ---- Voice V1: móc nối đạo diễn (voice-turn.js) ----
  endpointDelay: (text) => turn.delayFor(text),
  onBargeStart: () => runActions(turn.bargeStart()),
  // Nhá tiếng xong, chắc là người thật: dừng hẳn và mở tai ngay, không qua cửa sổ chờ chữ.
  onBargeConfirm: () => runActions(turn.bargeConfirmed(voice.lastSpokenPrefix())),
  onSpeakStart: () => runActions(turn.ttsStart()),
  onSpeakEnd: () => runActions(turn.ttsEnd()),
  onSlow: (cham) => runActions(turn.setSlow(cham)),
});

// ============================================
// Voice V1 - đạo diễn hội thoại (docs/dev/2026-09-voice-v1-spec.md mục 3 và 4)
// ============================================
// voice-turn.js giữ toàn bộ luật (chờ bao lâu rồi gửi, "khoan" nghĩa là gì, chen ngang thật
// hay giả); app.js chỉ THỰC HIỆN mảng hành động nó trả về và vẽ orb theo trạng thái thật.
const turn = new window.JavisVoiceTurn.VoiceTurn({
  minDelay: parseInt(localStorage.getItem("javis.endpoint") || "1200", 10) || 1200,
});
let _bargeTimer = null;   // 2 giây sau khi tạm dừng mà không có chữ -> chen ngang giả
let _waitTimer = null;    // "khoan" rồi im lâu -> thôi chờ
let _ngatLoiTai = "";     // câu Javis bị ngắt lúc đọc, đi vào tin kế tiếp rồi xoá

// ---- Voice V3: cắt cụm cho loa + câu tiến độ (docs/dev/2026-09-voice-v2-spec.md mục 11) ----
// Chữ stream của MỌI làn đi qua voice-chunker.js rồi mới ra loa: đọc theo cụm tự nhiên (hết
// câu, hoặc phẩy/liên từ khi cụm đầu, hoặc im lâu mà loa đang im) thay vì đọc từng mẩu vài từ.
const cum = new window.JavisVoiceChunker.Chunker();
let _cumTimer = null;
function docCum(chunks, t) {
  (chunks || []).forEach((c) => {
    if (!c || !c.trim()) return;
    voice.enqueueSpeak(c);
    if (t) t.spoke = true;
    turn.noteSpoke();
  });
}
// Đồng hồ 150 ms chạy suốt lượt: đẩy cụm dở khi im lâu mà loa im, và nói câu tiến độ khi xử lý
// quá lâu chưa có chữ nào (chỉ trong phiên nói chuyện bằng giọng, tức đang rảnh tay).
function batDongHoCum() {
  if (_cumTimer) return;
  _cumTimer = setInterval(() => {
    const t = savedSessionId ? turns[savedSessionId] : null;
    if (!t || !t.running) { clearInterval(_cumTimer); _cumTimer = null; return; }
    if (!voice.ttsEnabled) return;
    docCum(cum.tick(Date.now(), !voice.isSpeaking()), t);
    if (handsFree) runActions(turn.fillerCheck(Date.now()));
  }, 150);
}
function noiTienDo() {
  const opts = String(window.t("app.voice_filler") || "").split("|").map(s => s.trim()).filter(Boolean);
  // uncounted: câu tiến độ không thuộc câu trả lời, không tính vào số từ đã đọc (chữ theo lời).
  if (opts.length) voice.enqueueSpeak(opts[Math.floor(Math.random() * opts.length)], { uncounted: true });
}

// ---- Voice V3: chữ hiện THEO LỜI ĐỌC (karaoke), như ChatGPT Voice ----
// Đang nói chuyện bằng giọng thì hiện trọn cụm đang đọc để chữ không chạy sau loa
// (voice.visibleWords); ở Live thì theo tỉ lệ ms đã phát trên ms
// đã xếp lịch (JavisVoiceLive.progress). Bị ngắt lời thì bong bóng dừng đúng chỗ đã nói kèm "…".
// Đọc xong hết mới vẽ markdown đầy đủ (ảnh, link, bảng, chip hỏi lại). Chữ đã về từ model mà
// chưa tới lượt phát thì chưa hiện.
let _theoLoi = null;   // { el, text, ask, live, shown, chuaXong }
function dangTheoLoi() { return handsFree && voice.ttsEnabled; }
function batTheoLoi(el, text, ask, live) {
  if (!el) return;
  if (_theoLoi && _theoLoi.el !== el) ketThucTheoLoi(false);
  const cu = (_theoLoi && _theoLoi.el === el) ? _theoLoi : null;
  _theoLoi = { el, text: String(text || ""), ask: ask || (cu && cu.ask) || null, live: !!live,
               shown: cu ? cu.shown : -1, chuaXong: cu ? cu.chuaXong : true };
  veTheoLoi();
}
function _chuTheoLoi(s) { return s.live ? s.text : voice._cleanForTTS(s.text); }
function veTheoLoi() {
  const s = _theoLoi; if (!s) return;
  const C = window.JavisVoiceChunker;
  const full = _chuTheoLoi(s), tong = C.countWords(full);
  let n;
  if (s.live) {
    const p = window.JavisVoiceLive ? window.JavisVoiceLive.progress() : null;
    n = (p && p.total > 0) ? Math.round(tong * Math.min(1, p.played / p.total)) : Math.max(0, s.shown);
  } else n = voice.visibleWords();
  n = Math.max(s.shown, Math.min(n, tong));
  if (n === s.shown) return;
  s.shown = n;
  s.el.querySelector(".bubble").innerHTML = n > 0 ? escapeHtml(C.takeWords(full, n)) : '<span class="theo-loi-cho">…</span>';
  scrollBottom();
}
// Kết thúc: vẽ đầy đủ (đọc xong hoặc chuyển lượt) hoặc đóng băng ở chỗ đã nói (bị ngắt lời).
function ketThucTheoLoi(biNgat) {
  const s = _theoLoi; if (!s) return;
  _theoLoi = null;
  const host = s.el.querySelector(".bubble");
  const full = _chuTheoLoi(s), tong = window.JavisVoiceChunker.countWords(full);
  if (biNgat && s.shown > 0 && s.shown < tong) {
    host.innerHTML = escapeHtml(window.JavisVoiceChunker.takeWords(full, s.shown)) + " …";
  } else {
    host.innerHTML = markdownToHtml(s.text);
  }
  if (s.ask) window.JavisAsk.render(s.el, s.ask, true);
  if (s.live && window.JavisVoiceLive) window.JavisVoiceLive.resetProgress();
}
// Gọi ~20 lần/giây từ vòng vẽ orb: cập nhật chữ, và khi lượt xong + loa im thì vẽ đầy đủ.
function nhipTheoLoi() {
  const s = _theoLoi; if (!s) return;
  veTheoLoi();
  let dangChay, loaIm;
  if (s.live) {
    dangChay = s.chuaXong;
    loaIm = !(window.JavisVoiceLive && window.JavisVoiceLive.isSpeaking());
  } else {
    const t = savedSessionId ? turns[savedSessionId] : null;
    dangChay = !!(t && t.running);
    loaIm = !voice.isSpeaking() && !voice.isPaused() && !(voice.speechQueue && voice.speechQueue.length);
  }
  if (!dangChay && loaIm) ketThucTheoLoi(false);
}

const ORB_LABEL = {
  idle: ["", "orb.ready"],
  listening: ["listening", null],
  user_speaking: ["listening", null],
  waiting_for_user: ["waiting", "app.orb_waiting"],
  processing: ["thinking", "app.orb_thinking"],
  speaking: ["speaking", "app.orb_speaking"],
  interrupted: ["paused", "app.orb_paused"],
  reconnecting: ["reconnecting", "app.orb_reconnecting"],
  error: ["error", "app.orb_mic_error"],
};
function capNhatOrb() {
  let [cls, key] = ORB_LABEL[turn.state] || ORB_LABEL.idle;
  let label;
  if (handsFree && attention.waiting()) {
    cls = "waiting"; label = window.t("app.voice_focus_waiting");
  } else if (voice.isTranscribing && !voice.isListening && !voice.isSpeaking()) {
    cls = "thinking"; label = window.t("app.orb_transcribing");
  } else if (turn.state === "listening" || turn.state === "user_speaking") {
    label = handsFree ? window.t("app.orb_listening_always") : window.t("app.orb_listening");
  } else if (turn.state === "processing" && turn.tool) {
    label = window.t("app.orb_tool", { tool: compactToolLabel(turn.tool).label });
  } else {
    label = window.t(key);
  }
  if (turn.slow) label += " · " + window.t("app.orb_slow");
  if (turn.background > 0 && (turn.state === "idle" || turn.state === "listening")) {
    label += " · " + window.t("app.orb_background", { n: turn.background });
  }
  setOrbState(cls, label);
}

function runActions(acts) {
  (acts || []).forEach((a) => {
    switch (a.type) {
      case "state": capNhatOrb(); break;
      case "arm_endpoint": break;                    // voice.js tự đặt đồng hồ qua endpointDelay()
      case "commit": _ngatLoiTai = a.interruptedAt || _ngatLoiTai; break;   // sendMessage đọc rồi xoá
      case "hold":
        clearTimeout(_waitTimer);
        _waitTimer = setTimeout(() => runActions(turn.waitTimeout()), turn.opts.waitTimeoutMs);
        break;
      case "stop_tts":
        if (a.interrupted) { clearTimeout(_bargeTimer); _bargeTimer = null; ketThucTheoLoi(true); }   // V3: đóng băng chỗ đã nói
        voice.stopSpeaking();
        break;
      case "pause_tts":
        voice.pauseSpeaking();
        clearTimeout(_bargeTimer);
        _bargeTimer = setTimeout(() => { _bargeTimer = null; runActions(turn.bargeTimeout()); }, turn.opts.falseInterruptMs);
        break;
      case "resume_tts": voice.resumeSpeaking(); break;
      case "listen": voice.startListening(true, true); break;       // giữ tiếng đang tạm dừng
      case "abort_listen": voice._muteRecognition(); break;         // đóng recognition, mic mở lại sau khi đọc xong
      case "stop_turn": stopCurrent(); break;
      case "flush_deferred": (a.texts || []).forEach(t => { if (voice.ttsEnabled) voice.enqueueSpeak(t, { uncounted: true }); }); break;
      case "speak_filler": noiTienDo(); break;                    // V3: "để mình xem nhé" khi việc lâu
      default: break;
    }
  });
}

// Chữ nghe xong -> đạo diễn quyết: gửi (trả lại chữ), chờ, hay dừng (trả "").
function veTinTuGiong(text) {
  const acts = turn.endpoint(text || "");
  runActions(acts);
  const c = acts.find(a => a.type === "commit");
  if (c) _tuGiong = true;   // sendMessage kế tiếp là tin từ mic
  return c ? c.text : "";
}
let _tuGiong = false;

// ============================================
// Voice V2 - cài đặt giọng nói (chế độ, nghe bằng Groq) và bậc Live
// ============================================
let voiceMode = "standard";   // standard | fast | live (đọc từ /settings)
async function napCaiDatGiong() {
  try {
    const s = await (await fetch("/settings")).json();
    const v = (s && s.voice) || {};
    const focused = v.focus_mode !== false;
    if (voiceMode !== (v.mode || "standard") || voice.sttUpload !== (v.stt_provider === "groq") || attention.enabled !== focused) tatRanhTay();
    attention.enabled = focused;
    voiceMode = v.mode || "standard";
    voice.sttUpload = v.stt_provider === "groq";
  } catch (e) {}
}
napCaiDatGiong();
window.JavisVoiceMode = { refresh: napCaiDatGiong, get: () => voiceMode };

// Bậc Live: mic bấm là mở phiên nghe nói thẳng thay cho Web Speech. Bản ghi chữ hai chiều
// vào khung chat như tin thường; orb theo cùng đạo diễn (nói / nghe / gọi tool).
let _liveUserBubble = null, _liveJavisText = "", _liveJavisBubble = null, _liveCtxTimer = null;
let _liveStartSeq = 0;
let _liveWaitingWake = false, _liveBusyUntil = 0;
let _liveToolCount = 0;
// Only one capture is alive: Live is closed before this free browser listener starts.
const liveWake = new JavisVoice({
  lang: "vi-VN",
  inputOnly: true,
  endpointDelay: text => turn.delayFor(text),
  onInterim: () => {},
  onTranscript: text => {
    if (!_liveWaitingWake || !handsFree || voiceMode !== "live" || !attention.accept(text)) return;
    resumeVoiceFocus(text);
  },
  onError: () => updateVoiceFocus(),
});

function updateVoiceFocus() {
  const button = document.getElementById("voiceFocusResume");
  if (!button) return;
  button.hidden = !handsFree || !attention.waiting();
  const wakeAvailable = voiceMode !== "live" || (liveWake.isSupported() && !liveWake.micHong());
  button.textContent = window.t(wakeAvailable ? "app.voice_focus_waiting" : "app.voice_focus_click");
  voiceBtn.classList.toggle("focus-waiting", !button.hidden);
}

function resumeVoiceFocus(text = "") {
  if (!handsFree) return;
  // A click must not commit the ambient utterance already buffered while waiting.
  if (voiceMode !== "live") voice.cancelListening();
  attention.start();
  if (_liveWaitingWake) {
    _liveWaitingWake = false;
    liveWake.cancelListening();
    batLive(text);
  } else if (voiceMode !== "live") {
    voice.startListening();
  }
  updateVoiceFocus(); capNhatOrb();
}

function tickVoiceFocus() {
  if (!handsFree) return;
  // Only foreground replies prolong an already-open conversation. A background notification
  // cannot reopen it; stale processing is bounded for Live providers without turn_done.
  const busy = voiceMode === "live"
    ? !_liveWaitingWake && (Date.now() < _liveBusyUntil || _liveToolCount > 0 || (window.JavisVoiceLive && window.JavisVoiceLive.isSpeaking()))
    : isProcessing || voice.isSpeaking() || voice.isTranscribing;
  if (busy) attention.keepActive();
  if (attention.waiting() && voiceMode === "live" && !_liveWaitingWake) {
    _liveWaitingWake = true;
    tatLive(); // close the provider BEFORE listening for a wake word
    liveWake.setRecognitionLang(voice.lang);
  }
  if (_liveWaitingWake && liveWake.isSupported() && !liveWake.micHong() && !liveWake.isListening && !liveWake.isTranscribing) {
    liveWake.startListening(true);
  }
  updateVoiceFocus(); capNhatOrb();
}
// Ngữ cảnh giao diện vào phiên Live (GPT-Live gọi là "share UI context"): cùng khối V1 gửi cho
// bộ não chính, đẩy khi ĐỔI (sendContext tự lọc trùng), dò 1,5 s một lần trong lúc mic mở.
function guiNguCanhLive() {
  try {
    if (!window.JavisVoiceLive || !window.JavisVoiceLive.isOn()) return;
    const ctx = window.JavisUiContext ? window.JavisUiContext.build({ page: nguCanhTrang(), selection: nguCanhChon() }) : "";
    window.JavisVoiceLive.sendContext(ctx);
  } catch (e) {}
}
async function batLive(wakeText = "") {
  if (!window.JavisVoiceLive) { alert(window.t("app.live_missing")); return false; }
  const ticket = ++_liveStartSeq;
  // Web Speech abort is asynchronous. On phones, wait until it actually releases capture.
  const released = await liveWake.waitForCaptureEnd();
  if (ticket !== _liveStartSeq || !handsFree) return false;
  if (!released) { tatRanhTay(); appendJavisError(window.t("app.voice_focus_mic_busy")); return false; }
  let pendingWake = wakeText, readySeen = false;
  _liveToolCount = 0;
  _liveBusyUntil = Date.now() + 120000; // bounded setup, cleared by the first ready
  _liveJavisText = ""; _liveJavisBubble = null;
  const ok = await window.JavisVoiceLive.start({
    sessionId: () => savedSessionId,
    brain: () => currentBrainPath(),
    language: () => voice.langAuto ? "auto" : voice.lang,
    onStarted: () => {
      voiceBtn.classList.add("recording"); runActions(turn.micOn());
      clearInterval(_liveCtxTimer); _liveCtxTimer = setInterval(guiNguCanhLive, 1500); guiNguCanhLive();
    },
    onStopped: () => {
      clearInterval(_liveCtxTimer); _liveCtxTimer = null; nhapGiong("");
      if (_liveJavisText.trim()) recordTurn("javis", _liveJavisText.trim(), null, null);
      if (_theoLoi && _theoLoi.live) ketThucTheoLoi(true);
      _liveJavisText = ""; _liveJavisBubble = null;
      voiceBtn.classList.remove("recording"); runActions(turn.micOff());
    },
    onReady: (d) => {
      if (ticket !== _liveStartSeq || !handsFree) return;
      if (!readySeen) { readySeen = true; _liveBusyUntil = 0; attention.keepActive(); }
      if (d && d.session_id && !savedSessionId) { savedSessionId = d.session_id; persistSession(); }
      if (pendingWake) {
        const text = pendingWake; pendingWake = ""; // some providers emit ready twice
        window.JavisVoiceLive.sendText(text);
        appendUserMessage(text, []); recordTurn("user", text, []);
        _liveBusyUntil = Date.now() + 120000;
      }
    },
    onSpeakStart: () => runActions(turn.ttsStart()),
    onSpeakEnd: () => { _liveBusyUntil = 0; attention.keepActive(); runActions(turn.ttsEnd()); },
    onInterrupted: () => { ketThucTheoLoi(true); attention.keepActive(); _liveBusyUntil = Date.now() + 120000; _liveJavisText = ""; _liveJavisBubble = null; },
    onTool: (name, status) => {
      // A running tool is real work, not idle: only done/connection close/user stop may
      // release it. An arbitrary idle timeout must not cancel a legitimate long task.
      if (status === "running") _liveToolCount++;
      else { _liveToolCount = Math.max(0, _liveToolCount - 1); attention.keepActive(); }
      if (status === "running") runActions(turn.toolCall(name)); else runActions(turn.turnDone());
    },
    onTranscript: (role, text, final) => {
      if (role === "user") {
        if (text.trim()) { attention.keepActive(); _liveBusyUntil = Date.now() + 120000; }
        if (final && text.trim()) { nhapGiong(""); appendUserMessage(text.trim(), []); recordTurn("user", text.trim(), []); }
        else nhapGiong(text);
        return;
      }
      _liveJavisText += text;
      if (!_liveJavisBubble) _liveJavisBubble = createStreamingBubble();
      if (dangTheoLoi()) batTheoLoi(_liveJavisBubble, _liveJavisText, null, true);   // V3: chữ theo tiếng
      else { _liveJavisBubble.querySelector(".bubble").innerHTML = markdownToHtml(_liveJavisText); scrollBottom(); }
    },
    onTurnDone: () => {
      _liveBusyUntil = 0; attention.keepActive();
      if (_liveJavisText.trim()) recordTurn("javis", _liveJavisText.trim(), null, null);
      if (_theoLoi && _theoLoi.live && _theoLoi.el === _liveJavisBubble) _theoLoi.chuaXong = false;   // vẽ đủ khi loa im
      _liveJavisText = ""; _liveJavisBubble = null;
      runActions(turn.turnDone());
    },
    onError: (msg) => {
      _liveBusyUntil = 0;
      appendJavisError(String(msg || "").startsWith("mic:") ? window.t("app.mic_denied") : (window.t("app.live_error") + " " + msg));
      runActions(turn.turnDone());
    },
    onClosed: () => tatRanhTay(),
  });
  if (ticket !== _liveStartSeq) return false;
  if (!ok) tatRanhTay();
  return ok;
}
function tatLive() { _liveStartSeq++; try { if (window.JavisVoiceLive) window.JavisVoiceLive.stop(); } catch (e) {} }

// Dải việc nền (background-strip.js) báo số việc đang chạy để orb ghi hậu tố thật.
window.JavisOrb = {
  setBackground: (n) => runActions(turn.setBackground(n)),
  setVoiceJobs: (n) => datSoViecGiong(n),
};

// ---- Voice V3: Javis TỰ HỎI THĂM khi việc nền chạy lâu ----
// Chủ dự án 15/09: giao việc xong thì im lặng hàng phút, "anh không rõ nó có chạy nền thật hay
// không"; anh ấy muốn nó nói kiểu "để em xem nhé", "chờ em tý", "em vẫn chưa xong". Người thật
// nhận việc lâu thì thỉnh thoảng ngẩng lên nói một câu, chứ không ngồi câm.
//
// Ba luật giữ cho nó không thành phiền:
//   - THƯA DẦN: 25 giây, rồi 60, rồi 120, rồi mỗi 180 giây. Nhắc dày là tra tấn.
//   - Chỉ nói khi RẢNH THẬT (đạo diễn cho phép: không ai đang nói, loa đang im). Chen một câu
//     hỏi thăm vào giữa lời người dùng là đúng cái tội mà ngắt lời sinh ra để chữa.
//   - Chỉ khi đang rảnh tay và loa đang bật. Gõ chữ thì màn hình đã có dải việc nền rồi.
// Số việc đến từ /background (sổ thật của server), không phải đếm mò ở trình duyệt.
let _soViecGiong = 0, _mocViecGiong = 0, _lanHoiTham = 0, _hoiThamTimer = null;
const NHIP_HOI_THAM = [25000, 60000, 120000];   // sau đó lặp lại 180 giây một lần
function datSoViecGiong(n) {
  const so = Math.max(0, parseInt(n, 10) || 0);
  if (so === _soViecGiong) return;
  const truoc = _soViecGiong;
  _soViecGiong = so;
  if (so > 0 && truoc === 0) { _mocViecGiong = Date.now(); _lanHoiTham = 0; }
  if (so === 0) { _mocViecGiong = 0; _lanHoiTham = 0; }
}
function nhipHoiTham() {
  return _lanHoiTham < NHIP_HOI_THAM.length ? NHIP_HOI_THAM[_lanHoiTham] : 180000;
}
function hoiThamViecNen() {
  if (!_soViecGiong || !_mocViecGiong) return;
  if (!handsFree || !voice.ttsEnabled) return;
  if (!turn.canSpeakNow()) return;              // đang nghe người dùng nói, hay loa đang bận
  if (Date.now() - _mocViecGiong < nhipHoiTham()) return;
  // Quá hai phút thì đổi giọng điệu: thừa nhận là lâu, đừng "sắp xong rồi" mãi.
  const key = (Date.now() - _mocViecGiong) > 120000 ? "app.voice_cho_viec_lau" : "app.voice_cho_viec";
  const opts = String(window.t(key) || "").split("|").map(s => s.trim()).filter(Boolean);
  if (!opts.length) return;
  _lanHoiTham++;
  _mocViecGiong = Date.now();
  // uncounted: câu hỏi thăm không thuộc câu trả lời nào, không tính vào chữ hiện theo lời đọc.
  voice.enqueueSpeak(opts[Math.floor(Math.random() * opts.length)], { uncounted: true });
}
_hoiThamTimer = setInterval(hoiThamViecNen, 2000);

// ============================================
// WebSocket
// ============================================
function connect() {
  // Chống nối trùng: connect() giờ được gọi từ HAI đường (chuỗi retry 3s của onclose, và
  // bộ hồi sức sau khi app màn hình chính bị iOS đóng băng nền). Hai đường cùng chạy mà
  // không có chốt này là hai socket song song, mọi tin nhắn về gấp đôi.
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  ws = new WebSocket(WS_URL);
  // Mất socket là trạng thái THẬT người dùng cần thấy ("ĐANG KẾT NỐI LẠI"), không phải đoán.
  ws.onclose = () => {
    try { runActions(turn.wsDown()); } catch (e) {}
    baoDutMang(true);
    setTimeout(connect, 3000);
  };
  ws.onmessage = (e) => handleMessage(JSON.parse(e.data));
}

// ---- Hồi sức sau giấc ngủ nền (app "Thêm vào màn hình chính" trên iPhone) ----
// iOS đóng băng toàn bộ JS khi app xuống nền: socket chết, tin nhắn đến trong lúc ngủ
// không bao giờ tới luồng live. Tab Safari thường thì user vuốt F5 là xong; app standalone
// KHÔNG có nút reload nào cả - nên phải tự hồi sức: nối lại socket ngay (không đợi chuỗi
// retry 3s bắt kịp) và kéo lại hội thoại đang xem từ server để bù tin đã lỡ.
let _hiddenAt = 0;
document.addEventListener("visibilitychange", () => {
  if (document.hidden) { _hiddenAt = Date.now(); return; }
  _resumeSauNgu(false);
});
// bfcache trả trang về từ bộ nhớ (persisted): trạng thái là ảnh chụp cũ, luôn hồi sức.
window.addEventListener("pageshow", (e) => { if (e.persisted) _resumeSauNgu(true); });
function _resumeSauNgu(force) {
  // Ngủ dưới 20 giây (chuyển app qua lại) thì socket thường còn sống, đừng kéo lại hội
  // thoại một cách ồn ào - trừ khi bfcache (force) vì khi đó không biết đã ngủ bao lâu.
  if (!force && (!_hiddenAt || Date.now() - _hiddenAt < 20000)) return;
  _hiddenAt = 0;
  try { connect(); } catch (e) {}   // đã có chốt chống trùng, gọi thừa vô hại
  // Phiên đang xem có lưu DB thì dựng lại từ server - openStoredSession tự gắn lại bong
  // bóng sống nếu phiên đang generate nền, nên gọi giữa chừng không mất gì.
  if (savedSessionId) { try { openStoredSession(savedSessionId); } catch (e) {} }
}

function handleMessage(data) {
  // Server chào khi kết nối: đồng bộ các job vẫn đang chạy. Job thuộc server,
  // không thuộc WebSocket nên đóng/F5 tab rồi mở lại vẫn xem và Stop được.
  if (data.type === "hello") {
    stopTag = data.stop_tag || null;
    if (window.JavisRunning) window.JavisRunning.clear();
    Object.keys(turns).forEach(sid => { if (turns[sid]) turns[sid].running = false; });
    _luotDaDung = {};   // socket mới: turn_done của lượt đã dừng trên socket cũ không còn tới

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
    // Lượt đang chờ gói thuê bao mở lại hạn mức: dựng lại thẻ "tự chạy lại" cho phiên đang xem.
    try { if (window.JavisResume) window.JavisResume.fromHello(data.resumes || [], savedSessionId); } catch (e) {}
    runActions(turn.wsUp());   // socket đã nối: orb thôi "ĐANG KẾT NỐI LẠI"
    baoDutMang(false);
    guiTinDutMang();           // và những câu nói lúc mất mạng được gửi đi, không bốc hơi
    return;
  }
  if (data.type === "ui_action") {
    // Tool javis_ui (server) bảo dashboard mở trang / file / việc. ui-actions.js kiểm rồi làm
    // và tự trả ui_result về server để tool trả lời model ngay trong lượt.
    try { if (window.JavisUiActions) window.JavisUiActions.handle(data); } catch (e) {}
    return;
  }

  // Định tuyến theo session_id: sự kiện của phiên ĐANG XEM thì render trực tiếp; phiên nền thì
  // chỉ tích luỹ vào buffer + đánh dấu "đang chạy" ở Lịch sử (server đã tự lưu vào DB).
  const sid = data.session_id || null;
  const isActive = !!sid && sid === savedSessionId;
  // CHỈ khung của một LƯỢT mới được dựng bộ đệm và đánh dấu phiên "đang chạy". Khung NGOÀI
  // lượt (push của việc nền, inbox...) tuyệt đối không được: `turn_done` đã xoá turns[sid] khi
  // lượt kết thúc, nên dựng lại ở đây là HỒI SINH một lượt đã chết với cờ running=true mà
  // không còn turn_done nào tới để hạ nó xuống. Hậu quả dây chuyền: syncActiveUI khoá nút gửi,
  // sendMessage nuốt lặng mọi tin sau đó, và vòng giữ mic không mở lại vì tưởng đang xử lý -
  // khung chat chết cứng ở "đang suy nghĩ" ngay sau khi một việc nền báo xong. Chủ dự án gặp
  // 15/09: "sau khi có đoạn chạy nền thì không nói nữa luôn, không nhắn tiếp vào khung chat".
  const KHUNG_LUOT = ["status", "tool_call", "tool_result", "stream", "response", "error", "turn_done"];
  const t = !sid ? null
    : (turns[sid] || (KHUNG_LUOT.includes(data.type)
        ? (turns[sid] = { text: "", bubble: null, spoke: false, running: true })
        : null));
  // Khung của lượt MỚI đã về: server chỉ nhận tin mới khi job cũ đã dứt, và turn_done của job
  // cũ đi trước trên cùng socket, nên nó không thể còn tới nữa - thôi chờ (xem _luotDaDung).
  if (sid && _luotDaDung[sid] != null && data.type !== "turn_done" && KHUNG_LUOT.includes(data.type)
      && t && t.id && t.id !== _luotDaDung[sid]) delete _luotDaDung[sid];

  if (data.type === "push") {
    // Tin do việc chạy NỀN đẩy vào (việc Kanban / loop / nhắc hẹn xong), không thuộc lượt
    // hỏi-đáp nào. KHÔNG đụng turns[sid]: lượt đang chạy (nếu có) vẫn stream bình thường,
    // tin này chỉ chèn thêm một bong bóng. Server đã lưu vào kho phiên nên F5 vẫn còn.
    if (isActive) {
      const el = appendJavisMessage(data.content || "");
      recordTurn("javis", data.content || "", null, null);
      scrollBottom();
      // Đọc tin nền chỉ khi người dùng KHÔNG đang nói hay đang nghe Javis nói dở (Voice V1):
      // chen một bản tin vào giữa câu người dùng là cắt ngang họ. Hoãn tới lúc rảnh.
      if (voice.ttsEnabled) {
        if (turn.canSpeakNow()) voice.enqueueSpeak(data.content || "", { uncounted: true });
        else turn.defer(data.content || "");
      }
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
  if (data.type === "inbox") {
    // Việc nền vừa để lại một mẩu thư → chấm đỏ trên chuông nhảy NGAY, không đợi tải lại
    // trang. Nếu thư thuộc đúng hội thoại đang mở thì coi như đã đọc luôn: người dùng đang
    // nhìn thẳng vào nội dung, bắt họ bấm thêm một lần nữa trong hòm là đếm hai lần.
    try {
      if (window.JavisInbox) {
        if (sid && sid === savedSessionId) window.JavisInbox.docPhien(sid);
        else window.JavisInbox.refresh();
      }
    } catch (e) {}
    return;
  }
  if (data.type === "status") {
    if (t) t.running = true;
    setSessionRunning(sid, true);
    if (isActive) { runActions(turn.turnStart()); showActivity(escapeHtml(data.content || "")); syncActiveUI(); }
  } else if (data.type === "tool_call") {
    if (t && window.JavisSteps) t.buoc = window.JavisSteps.nhan(t.buoc, data);
    if (isActive) {
      runActions(turn.toolCall(data.tool || ""));
      veKhoiBuoc(t, true);
      showActivity(escapeHtml(data.content || ""));   // chip = dong dang chay + dong ho, luon nam duoi khoi
    }
  } else if (data.type === "tool_result") {
    if (t && window.JavisSteps) t.buoc = window.JavisSteps.nhan(t.buoc, data);
    if (isActive) { veKhoiBuoc(t, true); showActivity(Icons.msg("check", window.t("app.act_analyzing"), { cls: "ic-ok" })); }
  } else if (data.type === "stream") {
    if (!t) return;
    t.text += (data.content || "");
    if (isActive) {
      if (!t.bubble) { t.bubble = createStreamingBubble(); showActivity(Icons.msg("pen-line", window.t("app.act_writing"))); }
      // V3: đang nói chuyện bằng giọng thì chữ hiện THEO LỜI ĐỌC, không hiện trước loa.
      if (dangTheoLoi() && data.tts !== false) batTheoLoi(t.bubble, t.text, null, false);
      else { t.bubble.querySelector(".bubble").innerHTML = markdownToHtml(t.text); scrollBottom(); }
      // Voice V3: gom chữ stream thành CỤM đọc được (voice-chunker.js) thay vì đọc từng mẩu.
      // Trước đây mỗi khung stream của bộ não chính (vài từ) là một yêu cầu TTS riêng nên nghe
      // cà nhắc; làn nhanh gửi nguyên câu thì qua đây vẫn phát ngay. OpenRouter gửi tts:false
      // -> đọc 1 lần ở cuối.
      if (voice.ttsEnabled && data.tts !== false) {
        docCum(cum.push(data.content || "", Date.now()), t);
        batDongHoCum();
      }
    }
  } else if (data.type === "response") {
    // Lượt vấp hạn mức gói thuê bao: câu báo đã hiện ở bong bóng lỗi (kèm thẻ tự chạy lại) và
    // server không có câu trả lời nào, nên không vẽ thêm bong bóng "(không có nội dung)".
    // Cùng luật cho MỌI lỗi engine (sai key, model 404, CLI thoát 1): bong bóng đỏ đã nói rõ,
    // vẽ thêm một bong bóng xám "(không có nội dung)" ngay dưới chỉ làm người dùng tưởng lỗi kép.
    if (t && (t.limit || (t.errored && !(t.text || "").trim())) && !(data.content || "").trim()) {
      if (isActive) { hideActivity(); veKhoiBuoc(t, false); runActions(turn.turnDone()); }
      refreshUsage();
      return;
    }
    const { clean: askClean, ask } = window.JavisAsk.extract(data.content || "");
    const finalText = askClean || (t && t.text) || "";
    const shownText = finalText || window.t("app.no_content");
    if (t) t.text = shownText;
    if (isActive) {
      hideActivity();
      veKhoiBuoc(t, false);   // het luot: khoi tien trinh gap thanh mot dong "Da chay N buoc"
      let msgEl = t && t.bubble;
      if (!msgEl) msgEl = appendJavisMessage(shownText);
      if (dangTheoLoi() && t && finalText) {
        batTheoLoi(msgEl, shownText, ask, false);        // V3: chữ theo lời tới khi đọc xong, rồi vẽ đủ + chip
      } else {
        if (t && t.bubble) msgEl.querySelector(".bubble").innerHTML = markdownToHtml(shownText);
        if (ask) window.JavisAsk.render(msgEl, ask, true);   // chip chỉ mọc khi lượt xong
      }
      _renderCtxLine(msgEl, data);   // lượt này đi đường nào, tốn bao nhiêu
      // V3: bộ não giọng vừa giao một việc chạy NỀN (tách nói khỏi làm). Ghi rõ dưới câu xác
      // nhận để người dùng biết việc đã nhận; kết quả về sau bằng khung push (tự đọc khi loa rảnh).
      if (data.background) {
        const nen = document.createElement("div");
        nen.className = "voice-nen";
        nen.textContent = window.t("app.voice_bg_task", { task: String(data.background).slice(0, 160) });
        msgEl.appendChild(nen);
      }
      if (finalText.trim()) recordTurn("javis", finalText, null, ask, t && t.buoc);
      // data.tts === false: khung "response" này KHÔNG được đọc (vd bản sửa lại sau khi bóc
      // JAVIS_LESSON của phiên trợ lý) - giống hệt cách nhánh "stream" đã tôn trọng data.tts.
      if (voice.ttsEnabled && t && data.tts !== false) {
        docCum(cum.flush(), t);                              // đẩy nốt phần đuôi chưa khép câu
        // Đánh dấu ĐÃ ĐỌC ngay sau khi gọi, không chỉ đọc điều kiện: thiếu dòng này thì một
        // khung "response" thứ hai của CÙNG lượt (vd bản sửa lại) sẽ gọi speak() lần nữa,
        // cắt ngang rồi phát lại từ đầu.
        if (!t.spoke && finalText) { voice.speak(finalText); t.spoke = true; }   // engine gửi tts:false: đọc 1 lần ở cuối
      } else cum.reset();
      maybeAutoLearn();
    }
    refreshUsage();     // cập nhật panel Mức dùng sau mỗi lượt
  } else if (data.type === "error") {
    if (t && data.limit) t.limit = data.limit;
    if (t) t.errored = true;   // khung response rỗng theo sau không vẽ thêm "(không có nội dung)"
    if (isActive) {
      hideActivity();
      veKhoiBuoc(t, false);
      const errEl = appendJavisError(data.content);
      runActions(turn.turnDone());   // lỗi cũng là hết lượt; turn_done theo sau chỉ lặp lại
      if (data.limit) {
        // Hết lượt gói thuê bao: câu báo là tin cuối của lượt (server không trả gì thêm), ghi
        // vào convo để F5 còn thấy, rồi gắn thẻ "tự chạy lại" dưới nó (limit-resume.js).
        recordTurn("javis", data.content || "", null, null);
        try { if (window.JavisResume) window.JavisResume.attach(errEl, sid, data.limit); } catch (e) {}
      }
    }
  } else if (data.type === "resume") {
    // Trạng thái lịch tự chạy lại (hẹn / tắt / đang chạy / huỷ) - thẻ tự vẽ lại.
    try { if (window.JavisResume) window.JavisResume.onFrame(data); } catch (e) {}
  } else if (data.type === "wf_event") {
    // Tiến độ từng bước của một lần chạy quy trình (trang Cộng sự vẽ ở cột phải). Khung chat
    // không vẽ gì: chip trạng thái đã đi bằng khung status riêng.
    try { if (window.JavisWorkspace) window.JavisWorkspace.onWfEvent(data); } catch (e) {}
  } else if (data.type === "user_text") {
    if (data.voice_turn_id && (!t || String(t.id) !== String(data.voice_turn_id))) return;
    // Lượt nói: server đã DIỄN GIẢI câu máy nghe (lớp sửa theo ngữ cảnh, hoặc bộ não giọng
    // viết lại dòng JAVIS_NGHE). Bong bóng người dùng đang hiện chữ thô của máy nghe, nên thay
    // bằng câu đã diễn giải và ghi chữ thô nhỏ bên dưới để đối chiếu. Chủ dự án 16/09: nói
    // "Javis" mà bong bóng vẫn "David" thì không biết Javis đã hiểu đúng chưa.
    // CỬA TẠP ÂM: bộ não giọng xét ra cả lượt chỉ là tiếng TV hay người khác trong phòng,
    // không có câu nào nói với Javis. Gỡ HẲN bong bóng (chủ dự án chốt 17/09: ẩn luôn để mắt
    // chỉ còn nội dung đang bàn), server đã xoá tin khỏi kho phiên nên F5 cũng không thấy lại.
    // Chỉ để lại một dòng ghi chú tự tắt: im hoàn toàn thì lúc cửa xét NHẦM, người dùng nói mà
    // không có gì xảy ra, trông y hệt mic hỏng và không có đầu mối nào để đi tắt bớt lọc.
    if (data.bo_qua) {
      if (isActive && goTinNguoiDungCuoi(data.raw || "")) ghiChuThoang(window.t("app.tap_am_bo_qua"));
    } else if (isActive) capNhatTinNguoiDung(data.text || "", data.raw || "");
  } else if (data.type === "system") {
    if (isActive) appendJavisMessage(data.content);
  } else if (data.type === "turn_done") {
    // Lượt của phiên này kết thúc (xong / lỗi / bị dừng): bỏ cờ chạy, dọn buffer, refresh Lịch sử.
    // turn_done của lượt ĐÃ DỪNG mà về sau khi lượt mới đã gửi (câu nói chen ngang, lưới thời
    // gian nổ trước) thì chỉ là tiếng vọng: bỏ qua, không xoá trạng thái lượt mới đang chạy.
    const _idDung = _luotDaDung[sid];
    if (_idDung != null) {
      delete _luotDaDung[sid];
      if (t && t.id && t.id !== _idDung) return;
    }
    try { if (window.JavisResume) window.JavisResume.turnDone(sid); } catch (e) {}
    // Trang Cộng sự phải biết lượt đã đóng: tiến độ quy trình còn kẹt ở "đang chạy" thì icon
    // quay mãi ở cột trái, kể cả khi lượt chết theo đường không kịp phát sự kiện nào.
    try { if (window.JavisWorkspace) window.JavisWorkspace.onTurnDone(sid); } catch (e) {}
    if (t) t.running = false;
    setSessionRunning(sid, false);
    // Chip "Đang soạn câu trả lời..." phải TẮT ở đây chứ không chỉ ở nhánh `response`: lượt
    // của phiên quy trình (trang Cộng sự) kết thúc bằng `stream` + `turn_done`, không có
    // `response` nào, nên trước đây chip đứng lại đếm giờ mãi dù kết quả đã in xong. Gọi thêm
    // một lần ở đây vô hại với lượt thường - hideActivity() là thao tác không cộng dồn.
    if (isActive) { hideActivity(); veKhoiBuoc(t, false); syncActiveUI(); runActions(turn.turnDone()); cum.reset(); }
    if (sid) delete turns[sid];
    if (isActive && _tinChoLuot) guiTinCho();   // câu người dùng chen ngang: lượt cũ dừng hẳn rồi thì gửi
    notifySessions();
    // Lượt vừa xong có thể đã giao việc nền. Đây là ĐÚNG khoảnh khắc người dùng đọc câu trả
    // lời "em đã giao 3 việc" và tự hỏi nó có chạy thật không - dải phải trả lời được ngay.
    try { if (window.JavisBackground) window.JavisBackground.refresh(); } catch (e) {}
  }
}

// ============================================
// Messages
// ============================================
// Lượt Enter đang ĐỢI file tải lên xong. Chỉ giữ một lượt: bấm Enter hai lần trong lúc chờ
// không được thành hai tin.
let _choTaiLen = null;
let _sendEpoch = 0;   // callbacks queued in an old voice/chat context may not send in a new one

// ---- Tin đang đợi lượt cũ dừng HẲN rồi mới gửi ----
// Server từ chối tin mới khi phiên còn job đang chạy ("Phiên này đang trả lời - đợi lượt hiện
// tại xong đã"), mà lệnh Dừng chỉ HUỶ job chứ không kết thúc nó tức thì: engine CLI có thể mất
// cả giây mới thật sự dừng. Gửi ngay sau stopCurrent() là rơi đúng vào lời từ chối đó, và câu
// người dùng vừa nói biến mất không dấu vết. Nên đợi `turn_done` rồi gửi, kèm lưới thời gian
// phòng khi lượt cũ chết mà không kịp báo.
//
// Lưới ấy từng là 1,5 giây (0.57.17) và đó là một trong hai "trục trặc nhỏ lúc chèn câu" chủ
// dự án báo 15/09: engine CLI bị giết có khi mất hơn thế mới thật sự dừng, lưới nổ trước
// `turn_done` là tin gửi đi đúng lúc server còn job và bị trả về lời từ chối; hoặc gửi được
// rồi `turn_done` của lượt CŨ mới về và xoá sạch trạng thái lượt MỚI (chữ stream không hiện,
// loa câm). Nay lưới rộng 5 giây, `turn_done` vẫn là tín hiệu chính, và lượt cũ được đánh dấu
// (xem _luotDaDung) để turn_done muộn của nó không đụng vào lượt mới.
let _tinChoLuot = null, _tinChoTimer = null;
function datTinCho(text) {
  _tinChoLuot = String(text || "");
  clearTimeout(_tinChoTimer);
  _tinChoTimer = setTimeout(guiTinCho, 5000);
  // Trong lúc chờ, câu vừa nói vẫn phải Ở LẠI trên màn hình (bong bóng nháp), không thì
  // người dùng thấy chữ biến mất vài giây rồi mới hiện lại và tưởng đã mất.
  try { nhapGiong(_tinChoLuot); } catch (e) {}
}
function guiTinCho() {
  clearTimeout(_tinChoTimer); _tinChoTimer = null;
  const t = _tinChoLuot; _tinChoLuot = null;
  // Lưới nổ mà turn_done chưa về: coi như lượt cũ không còn báo gì nữa, thôi chờ nó.
  try { if (savedSessionId) delete _luotDaDung[savedSessionId]; } catch (e) {}
  if (t) sendMessage(t);       // stopCurrent() đã hạ cờ running nên lần này không quay lại đây
}
// Lượt bị bấm Dừng (hay bị câu nói chen ngang dừng) mà chưa nhận turn_done: sid -> id lượt.
// turn_done về sau khi lượt MỚI đã chạy thì thuộc về lượt cũ, không được xoá trạng thái lượt mới.
let _luotDaDung = {}, _luotSeq = 0;

// Báo mất mạng NGAY TRONG KHUNG CHAT. Orb đã có chữ "ĐANG KẾT NỐI LẠI", nhưng orb nằm
// trong .hud-body và khối đó bị ẩn hẳn khi đang ở trang Trò chuyện, nên ở đúng chỗ người
// dùng đang gõ thì không có dấu hiệu nào. Khung chat thì trang nào cũng thấy.
//
// Chờ 2,5 giây mới báo: iOS đóng socket mỗi lần trang bị ẩn rồi nối lại sau một nhịp, báo
// ngay là nhấp nháy suốt ngày vì một chuyện tự khỏi.
let _dutMangTimer = null, _dangBaoDutMang = false;
function baoDutMang(dut) {
  if (dut) {
    if (_dutMangTimer || _dangBaoDutMang) return;
    _dutMangTimer = setTimeout(() => {
      _dutMangTimer = null;
      if (!ws || ws.readyState !== WebSocket.OPEN) { _dangBaoDutMang = true; showActivity(Icons.warn(window.t("app.ws_mat_ket_noi"))); }
    }, 2500);
    return;
  }
  clearTimeout(_dutMangTimer); _dutMangTimer = null;
  // Chỉ dọn dòng CỦA MÌNH: lượt đang chạy cũng dùng activity, xoá bừa là mất dấu "đang nghĩ".
  if (_dangBaoDutMang) { _dangBaoDutMang = false; hideActivity(); }
}

// ---- Tin gửi lúc WebSocket đang đứt ----
// Chỗ này TRƯỚC ĐÂY là một `return` trần, và đó là một lỗi mất chữ im lặng: đứt socket thì
// câu vừa nói biến mất không dấu vết. Trên iPhone nó xảy ra thường xuyên, vì Safari đóng
// WebSocket mỗi lần trang bị ẩn hay bị đóng băng nền (xem chú thích ở connect()), và người
// dùng chỉ đổi khung chat là dính. Tệ hơn nữa: trạng thái "ĐANG KẾT NỐI LẠI" nằm trên orb,
// mà orb bị ẩn hẳn khi đang ở trang Trò chuyện (body.on-chat .hud-body{visibility:hidden}) -
// nên không có một dấu hiệu nào cho biết vì sao câu nói bốc hơi. Đúng lỗi chủ repo báo 15/09.
//
// Nay: giữ câu lại, báo NGAY trong khung chat (chỗ này thì trang nào cũng thấy), gửi khi nối
// lại được. Quá lâu thì TRẢ CHỮ VỀ ô nhập - thà bắt người dùng bấm gửi lại còn hơn để họ
// tưởng đã gửi rồi ngồi đợi một câu trả lời không bao giờ tới.
const CHO_NOI_LAI_MS = 25000;
let _tinDutMang = [], _tinDutMangTimer = null;
function giuTinKhiDutMang(msg) {
  const t = String(msg || "").trim();
  if (!t) return;
  if (_tinDutMang.length >= 5) _tinDutMang.shift();   // trần: đứt mạng lâu thì giữ 5 câu gần nhất
  _tinDutMang.push(t);
  chatInput.value = ""; chatInput.style.height = "auto";
  clearTimeout(_dutMangTimer); _dutMangTimer = null;
  _dangBaoDutMang = true;
  showActivity(Icons.warn(window.t("app.ws_giu_tin")));
  clearTimeout(_tinDutMangTimer);
  _tinDutMangTimer = setTimeout(traTinDutMang, CHO_NOI_LAI_MS);
}
// Nối lại được: gửi lần lượt. Gọi từ nhánh `hello` chứ không từ onopen - hello mới là lúc
// server đã dựng xong phiên và sẵn sàng nhận tin.
function guiTinDutMang() {
  clearTimeout(_tinDutMangTimer); _tinDutMangTimer = null;
  const ds = _tinDutMang; _tinDutMang = [];
  if (!ds.length) return;
  hideActivity();
  const epoch = _sendEpoch;
  ds.forEach((t, i) => setTimeout(() => { if (epoch === _sendEpoch) sendMessage(t); }, i * 150));
}
// Chờ mãi không nối lại: trả chữ về ô nhập, nói thẳng là chưa gửi được.
function traTinDutMang() {
  clearTimeout(_tinDutMangTimer); _tinDutMangTimer = null;
  const ds = _tinDutMang; _tinDutMang = [];
  if (!ds.length) return;
  const con = chatInput.value.trim();
  chatInput.value = ds.concat(con ? [con] : []).join("\n");
  chatInput.style.height = "auto";
  chatInput.style.height = Math.min(chatInput.scrollHeight, 200) + "px";
  showActivity(Icons.warn(window.t("app.ws_tra_tin")));
}

// Phiên cộng sự (agent:/workflow:) -> phiên Trò chuyện đã GỌI nó bằng lệnh "/". Sống trong
// bộ nhớ trang: tải lại trang là quên, và như vậy là đúng - lúc đó người dùng không còn đang
// theo dõi cuộc gọi ấy nữa.
const _gocCongSu = {};

// `opts.wfRun`: tin này đến từ nút CHẠY của trang Cộng sự. Server dùng cờ đó để không
// đoán lại ý người dùng (xem workflow_chat.quyet_dinh_luot): bấm đúng nút Chạy thì chạy,
// dù câu trong ô nhập có nghe như đang nói về chính quy trình.
function sendMessage(text, opts) {
  if (window.JavisWorkspace && !window.JavisWorkspace.canSend()) return;
  const msg = (text || chatInput.value).trim();
  // Lệnh / : session-command chạy tại chỗ; skill-command bung thành lời gọi skill.
  const _slash = (window.JavisSlash && msg) ? window.JavisSlash.route(msg) : { type: "passthrough" };
  if (_slash.type === "agent" || _slash.type === "workflow") {
    if (!window.JavisWorkspace) return;
    // Khung chat NGƯỜI DÙNG đang đứng lúc gõ lệnh. Gõ "/quy-trinh" là trang nhảy hẳn sang
    // Cộng sự, việc chạy ở đó, và khung Trò chuyện vừa rời đi không bao giờ biết kết quả ra
    // sao - đúng chỗ chủ dự án thấy vô lý. Nhớ lại nguồn rồi gửi kèm mỗi tin, để server đẩy
    // kết quả NGƯỢC về đây kèm link mở lại cuộc hội thoại đã làm việc đó.
    const goc = savedSessionId;
    window.JavisWorkspace.openCommand(_slash.type, _slash.slug).then(function (opened) {
      if (!opened) return;
      if (goc && savedSessionId && savedSessionId !== goc) _gocCongSu[savedSessionId] = goc;
      chatInput.value = _slash.message || "";
      if (_slash.message) sendMessage(_slash.message);
      else chatInput.focus();
    });
    return;
  }
  if (_slash.type === "session") {
    chatInput.value = ""; chatInput.style.height = "auto";
    if (_slash.cmd === "stop") { try { stopCurrent(); } catch (e) {} }
    else { try { newChat(); } catch (e) {} }   // new | reset -> hội thoại mới trên web
    return;
  }
  if (!ws || ws.readyState !== WebSocket.OPEN) { giuTinKhiDutMang(msg); return; }
  // File còn ĐANG TẢI LÊN thì đợi nó xong rồi gửi, KHÔNG gửi thiếu. Trước đây dòng lọc
  // `a.path` bên dưới lặng lẽ bỏ file chưa tải xong: dán ảnh hay một đoạn văn dài rồi gõ câu
  // hỏi và Enter ngay là tin bay đi tay không, bong bóng không có ảnh, Javis cũng không nhận
  // được file - đúng lỗi chủ repo báo 2026-09-10. Chip trên thanh đính kèm vẫn hiện "đang
  // tải..." nên người dùng thấy vì sao tin chưa đi.
  const dangTai = pendingAttachments.filter(a => a.uploading);
  if (dangTai.length) {
    if (!_choTaiLen) {
      showActivity(escapeHtml(window.t("app.att_wait_send")));
      const epoch = _sendEpoch;
      _choTaiLen = Promise.all(dangTai.map(a => a.xong || Promise.resolve())).then(() => {
        if (epoch !== _sendEpoch) return;
        _choTaiLen = null;
        const _t = savedSessionId && turns[savedSessionId];
        if (!(_t && _t.running)) hideActivity();
        sendMessage(text, opts);
      });
    }
    return;
  }
  // File tải lên HỎNG cũng không được lặng lẽ bỏ qua: chip đã ghi lý do, thêm một dòng nói
  // thẳng để người dùng gỡ file lỗi hoặc thử lại, rồi mới gửi.
  if (pendingAttachments.some(a => !a.uploading && !a.path)) {
    attachNote = window.t("app.att_failed_send");
    renderChips();
    return;
  }
  const atts = pendingAttachments.filter(a => a.path);
  if (!msg && atts.length === 0) return;
  if (!savedSessionId) {
    savedSessionId = newSid();                           // hội thoại mới → mint id để định tuyến
    // Đang mở một project ở cột Lịch sử thì hội thoại mới rơi thẳng vào project đó, khỏi phải
    // gắn tay. Gắn NGAY tại đây vì đây là chỗ duy nhất biết "id này vừa được sinh ra".
    try { if (window.JavisProjects) window.JavisProjects.claim(savedSessionId); } catch (e) {}
    // Model đã chọn khi khung chat còn trống -> ghim luôn cho phiên vừa sinh (model-picker.js).
    try { if (window.JavisModelBar) window.JavisModelBar.claimPending(savedSessionId); } catch (e) {}
  }
  const sid = savedSessionId;
  // Phiên đang trả lời thì không gửi chồng lượt. NHƯNG tin từ MIC (hay gõ trong lúc rảnh tay)
  // là người dùng CHEN NGANG: họ vừa cắt lời Javis rồi nói câu mới, nên câu mới phải thắng -
  // dừng lượt cũ rồi gửi. Nuốt lặng như trước là kẹt cứng: đạo diễn đã bật `processing` trong
  // endpoint() TRƯỚC khi gọi vào đây, mà lượt bị nuốt thì không bao giờ có turn_done để hạ nó,
  // nên orb đứng mãi ở "đang suy nghĩ" và người dùng không thấy tin mình vừa nói ở đâu cả.
  if (turns[sid] && turns[sid].running) {
    if (!(_tuGiong || handsFree)) return;   // gõ chữ lúc không rảnh tay: giữ chốt cũ
    stopCurrent();
    datTinCho(msg);   // gửi khi lượt cũ dừng HẲN, không gửi ngay (xem chú thích ở datTinCho)
    return;
  }
  // Đang BUNG NÃO toàn màn (mobile) mà gửi tin thì thu lại: ở trạng thái đó khung chat bị
  // ẩn hẳn, không thu thì người dùng gõ xong không thấy câu trả lời hiện ở đâu cả. Bấm hộ
  // đúng cái nút để đi chung một đường (đổi aria + canh lại khung đồ thị).
  if (document.body.classList.contains("brain-max")) {
    try { document.getElementById("brainMaxBtn").click(); } catch (e) {}
  }
  voice.stopSpeaking();
  cum.reset();
  ketThucTheoLoi(false);       // bong bóng trước vẽ đủ
  voice.resetSpokenWords();    // lượt mới đếm từ đã đọc lại từ 0
  nhapGiong("");               // bong bóng nháp (chữ đang nghe) nhường chỗ cho tin thật
  // Voice V3: đang ở phiên Live mà GÕ chữ thì đẩy thẳng vào phiên Live (cùng một cuộc nói
  // chuyện, Javis đáp bằng giọng), không mở lượt chat riêng. Có file đính kèm thì đi đường thường.
  if (voiceMode === "live" && !atts.length && window.JavisVoiceLive && window.JavisVoiceLive.isOn()) {
    chatInput.value = ""; chatInput.style.height = "auto";
    appendUserMessage(msg, []);
    recordTurn("user", msg, []);
    window.JavisVoiceLive.sendText(msg);
    return;
  }
  window.JavisAsk.freezeAll();   // trả lời rồi thì chip của lượt trước hết bấm được
  appendUserMessage(msg, atts);
  // Lưu cả `url` (đường /upload/raw của file stage): thiếu nó thì F5 xong ảnh trong tin cũ
  // không còn gì để trỏ tới, và bong bóng chỉ còn trơ cái tên file.
  recordTurn("user", msg, atts.map(a => ({ name: a.name, kind: a.kind, url: a.url || "" })));

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
  // Ngữ cảnh giao diện (Voice V1, spec mục 5): trang đang mở, đoạn đang bôi đen, câu Javis bị
  // ngắt lời. Đứng SAU khối file ghim và TRƯỚC câu hỏi; rỗng thì không chèn gì.
  try {
    // `voice`: đang nói chuyện bằng giọng (tin từ mic, HAY gõ chữ khi mic rảnh tay đang bật):
    // câu trả lời sẽ đọc ra loa nên model phải trả lời ngắn như người đang nói (V3).
    const ctxUi = window.JavisUiContext ? window.JavisUiContext.build({
      page: nguCanhTrang(), selection: nguCanhChon(), interruptedAt: _ngatLoiTai,
      voice: _tuGiong || handsFree,
    }) : "";
    if (ctxUi) outMsg = `${ctxUi}\n\n${outMsg}`;
  } catch (e) {}
  _ngatLoiTai = "";
  if (pinnedNote) {
    outMsg = `[FILE ĐANG MỞ trong trình sửa của Javis: ${pinnedNote.abs}\n`
      + `Đây là file người dùng ĐANG LÀM VIỆC TRÊN ĐÓ - coi như đầu vào của cuộc trò chuyện này. `
      + `Đọc nó trước khi trả lời. Khi được yêu cầu sửa/viết thêm/dọn lại mà không nói rõ file nào `
      + `thì ghi thẳng vào chính file này.]\n\n${outMsg}`;
  }

  chatInput.value = ""; chatInput.style.height = "auto";
  clearAttachments();
  turns[sid] = { text: "", bubble: null, spoke: false, running: true, id: ++_luotSeq };
  setSessionRunning(sid, true);
  runActions(turn.turnStart());
  showActivity(window.t("app.act_thinking"));   // hiện NGAY trong khung chat, không đợi server báo
  syncActiveUI();
  // Server đóng dấu model đang chạy cho phiên ngay từ tin đầu -> bar hiện "ghim" tại chỗ.
  try { if (window.JavisModelBar) window.JavisModelBar.noteStamped(sid); } catch (e) {}
  // Voice V2: tin đến từ MIC mang cờ `voice` để server đưa qua làn nhanh (bộ não giọng nói)
  // khi cài đặt bật. V3: đang rảnh tay mà GÕ chữ thì cũng đi làn nhanh, vì đó vẫn là cuộc nói
  // chuyện bằng giọng (vừa nói vừa gõ bổ sung, một luồng). Mic tắt thì đi bộ não chính như cũ.
  // `origin_chat` chỉ đi kèm ĐÚNG MỘT tin: tin sinh ra từ cú gõ "/" ở khung Trò chuyện. Sau
  // đó người dùng đã đứng ở trang Cộng sự và biết kết quả nằm đâu, nên chép mọi lượt tiếp
  // theo về khung cũ là làm ngập nó bằng một cuộc trò chuyện của người khác.
  const _goc = _gocCongSu[sid] || "";
  delete _gocCongSu[sid];
  ws.send(JSON.stringify({ message: outMsg, brain: currentBrainPath(), session_id: sid,
                          voice: _tuGiong || handsFree, origin_chat: _goc,
                          voice_input: _tuGiong, voice_turn_id: String(turns[sid].id),
                          wf_run: !!(opts && opts.wfRun) }));
  _tuGiong = false;
}
// Trang đang mở và đoạn đang bôi đen, cho khối NGỮ CẢNH GIAO DIỆN. Chọn trong ô nhập chat thì
// không tính (đó là câu đang gõ, không phải thứ đang nhìn).
function nguCanhTrang() {
  try { return (window.Alpine && Alpine.store("nav") && Alpine.store("nav").active) || ""; } catch (e) { return ""; }
}
function nguCanhChon() {
  try {
    const sel = window.getSelection ? window.getSelection() : null;
    if (!sel || sel.isCollapsed) return "";
    const node = sel.anchorNode && (sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentElement);
    if (node && node.closest && node.closest("#chatInput, .chat-input, .msg-user")) return "";
    return String(sel.toString() || "").trim();
  } catch (e) { return ""; }
}
// Chip lựa chọn (chat-ask.js) gửi đáp án qua đây: bấm chip = y như người dùng gõ tay nhãn đó.
window.JavisSend = sendMessage;
// Module ngoài (limit-resume.js) gửi một khung điều khiển thô lên server. true = đã gửi.
window.JavisWsSend = function (obj) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return false;
  try { ws.send(JSON.stringify(obj)); return true; } catch (e) { return false; }
};

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
      // Con trỏ tin cũ, để F5 xong vẫn cuộn lên đọc tiếp được. CHỈ lưu khi convo chưa bị
      // slice(-200) ở trên cắt bớt: bị cắt thì con trỏ trỏ vào tin đã rụng khỏi khung, lượt
      // tải sau sẽ chừa ra một lỗ hổng giữa cuộc mà không ai thấy.
      tinCu: (_tinCu && convo.length <= 200) ? _tinCu : null,
      savedAt: Date.now(),
    }));
  } catch (e) {}
}
// Thay chữ của tin NGƯỜI DÙNG cuối cùng bằng câu đã diễn giải (sự kiện user_text), cả trên
// bong bóng lẫn trong convo để F5 còn đúng. `raw` là chữ thô của máy nghe, hiện nhỏ bên dưới.
function capNhatTinNguoiDung(text, raw) {
  if (!text || !text.trim()) return;
  const lastUser = [...convo].reverse().find(m => m.role === "user");
  if (raw && (!lastUser || lastUser.text.trim() !== raw.trim())) return;
  const nodes = chatArea.querySelectorAll(".msg-user:not(.msg-nhap-giong)");
  const div = nodes[nodes.length - 1];
  if (div) {
    div.dataset.text = text;
    const u = div.querySelector(".utext");
    if (u) u.textContent = text;
    const bubble = div.querySelector(".bubble");
    if (bubble && raw && raw.trim() !== text.trim()) {
      let tho = bubble.querySelector(".nghe-tho");
      if (!tho) { tho = document.createElement("div"); tho.className = "nghe-tho"; bubble.appendChild(tho); }
      tho.textContent = window.t("app.nghe_tho", { raw });
    }
  }
  for (let i = convo.length - 1; i >= 0; i--) {
    if (convo[i].role === "user") { convo[i].text = text; break; }
  }
  persistSession();
}
// Gỡ bong bóng NGƯỜI DÙNG cuối cùng khỏi khung chat và khỏi convo (cửa tạp âm). Server đã xoá
// tin khỏi kho phiên, đây là bản sao phía trình duyệt: không gỡ thì phải F5 mới sạch, còn màn
// hình đang mở vẫn trơ đoạn tạp âm ra đó.
function goTinNguoiDungCuoi(raw) {
  const lastUser = [...convo].reverse().find(m => m.role === "user");
  if (raw && (!lastUser || lastUser.text.trim() !== raw.trim())) return false;
  const nodes = chatArea.querySelectorAll(".msg-user:not(.msg-nhap-giong)");
  const div = nodes[nodes.length - 1];
  if (div && div.parentNode) div.parentNode.removeChild(div);
  for (let i = convo.length - 1; i >= 0; i--) {
    if (convo[i].role === "user") { convo.splice(i, 1); break; }
  }
  persistSession();
  return true;
}
// Dòng ghi chú THOÁNG QUA giữa khung chat: hiện rồi tự tắt, không vào convo, không lưu
// localStorage, không đọc ra loa, không đi vào ngữ cảnh lượt sau. Dùng cho chuyện Javis vừa
// quyết mà không đáng để lại một lượt trong hội thoại.
const GHI_CHU_MS = 6000;
function ghiChuThoang(text) {
  if (!text) return;
  const el = document.createElement("div");
  el.className = "msg msg-ghichu";
  el.textContent = text;
  chatAppend(el);
  scrollBottom();
  setTimeout(() => { if (el.parentNode) el.parentNode.removeChild(el); }, GHI_CHU_MS);
}
function recordTurn(role, text, atts, ask, buoc) {
  convo.push({ role, text: text || "", atts: atts || [], ask: ask || null, ts: Date.now(),
               // Mach buoc chi ghi khi luot that su co goi cong cu - luot tra loi thang
               // khong co truong nay, nen tin cu luu truoc ban nay cung khong sao.
               buoc: (buoc && window.JavisSteps && window.JavisSteps.tomTat(buoc).hien)
                 ? buoc : undefined });
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
    if (t.buoc && window.JavisSteps && window.JavisSteps.tomTat(t.buoc).hien)
      chatAppend(window.JavisSteps.ve(null, t.buoc, false));
    const el = appendJavisMessage(t.text, t.ts || 0, t.brain || s.brain);
    // Chip chỉ sống lại ở tin CUỐI: có tin sau nó nghĩa là câu hỏi đã được trả lời rồi.
    if (t.ask) window.JavisAsk.render(el, t.ask, i === convo.length - 1);
  });
  if (convo.length) { scrollBottom(true); ghimDay(sessionOpenSeq); }
  // Con trỏ tin cũ sống sót qua F5 → vẫn cuộn lên đọc tiếp được, không phải bấm lại vào
  // hội thoại trong danh sách mới có.
  _tinCu = (s.tinCu && savedSessionId) ? { ...s.tinCu, sid: savedSessionId, dangTai: false } : null;
  datMoiTinCu();
  // hello thường tới SAU bước này; nếu tới trước (kết nối nhanh) thì thẻ "tự chạy lại" gắn ở đây.
  try { if (window.JavisResume && savedSessionId) window.JavisResume.renderFor(savedSessionId); } catch (e) {}
  notifySessions();   // panel Lịch sử tô đúng phiên đang xem thay vì không tô cái nào
  syncActiveUI();
}

// ---- Tải dần tin cũ ----------------------------------------------------------------
// Hội thoại vài trăm lượt mà dựng hết bong bóng một lượt thì mở cuộc nào cũng khựng vài
// giây, và màn hay đứng lưng chừng thay vì rơi xuống câu trả lời gần nhất (ảnh tải xong mới
// đẩy chiều cao ra). Nên mở cuộc chỉ kéo TIN_MOI_LUOT tin cuối; cuộn lên chạm mồi thì kéo
// tiếp khúc cũ hơn.
const TIN_MOI_LUOT = 30;
// {sid, brain, ts, id, con, dangTai} - ts/id là con trỏ tới tin GIÀ NHẤT đang hiện.
let _tinCu = null;
let _moiTinCu = null, _quanSatMoi = null;

// Dựng lại MỘT tin đã lưu thành bong bóng, trả về mục tương ứng cho convo (null nếu bỏ qua).
// Dùng chung cho lượt mở hội thoại và lượt chèn ngược, để hai đường không trôi lệch nhau.
function veTinDaLuu(m, brainCua) {
  const ts = m.ts ? Math.round(m.ts * 1000) : 0;   // server lưu epoch giây (sessions.py)
  // convo là thứ được ghi xuống localStorage rồi dựng lại ở lần F5 sau. Nhét bản CÒN khối
  // vào đây là lỗi sống dai qua mọi lần tải lại, dù bong bóng lượt này đã sạch.
  if (m.role === "user") {
    // Server chỉ lưu CHỮ đã gửi (kèm khối ngữ cảnh), không lưu riêng danh sách đính kèm.
    // Đọc lại từ chính khối đó, không thì mở lại hội thoại là ảnh và file biến mất khỏi
    // bong bóng, người dùng không xem lại được mình đã gửi gì (chủ repo báo 2026-09-10).
    const _sach = chuNguoiGo(m.content || "");
    const _atts = docDinhKem(m.content || "");
    appendUserMessage(_sach, _atts, ts);
    return { role: "user", text: _sach, atts: _atts, ts };
  }
  // brainCua: server LƯU SẴN brain của phiên (cột brain trong bảng sessions). Trước đây
  // vứt đi nên ảnh trong hội thoại cũ luôn ghép với brain đang chọn - mở hội thoại của
  // brain khác là ảnh hỏng hết. Giữ luôn vào convo để lần khôi phục sau còn dùng.
  if (m.role === "assistant") {
    appendJavisMessage(m.content || "", ts, brainCua);
    return { role: "javis", text: m.content || "", atts: [], ts, brain: brainCua };
  }
  return null;
}

// Ghim khung ở ĐÁY trong một quãng ngắn sau lượt mở hội thoại.
//
// Đặt scrollTop đúng một lần là không đủ: khung còn cao thêm vài nhịp nữa sau đó. Thanh mốc
// hội thoại tự chèn nó vào rồi bật lề phải làm bong bóng xuống dòng, ảnh trong tin
// cũ tải xong mới đẩy chiều cao ra. Đo thật trên cuộc 120 tin: mở xong đứng cách đáy 174px,
// tức câu trả lời gần nhất - đúng thứ người ta vào để đọc - bị cắt mất một đoạn.
//
// Nhả NGAY khi người dùng tự cuộn, để cái ghim này không giành tay lái với họ.
function ghimDay(ticket, ms) {
  const het = Date.now() + (ms || 700);
  let thoi = false;
  const nhaTay = () => { thoi = true; };
  chatArea.addEventListener("wheel", nhaTay, { passive: true });
  chatArea.addEventListener("touchmove", nhaTay, { passive: true });
  const go = () => {
    chatArea.removeEventListener("wheel", nhaTay);
    chatArea.removeEventListener("touchmove", nhaTay);
  };
  const nhip = () => {
    if (thoi || ticket !== sessionOpenSeq) { go(); return; }
    scrollBottom(true);
    if (Date.now() < het) requestAnimationFrame(nhip); else go();
  };
  requestAnimationFrame(nhip);
}

// Bong bóng ĐẦU TIÊN trong khung. Chèn ngược phải neo vào nó chứ không vào firstChild: đầu
// khung còn có đồ nội thất dán sẵn (#chatMarks) tính là mình vẫn đứng đầu, chen lên trước là
// đẩy nó ra khỏi chỗ. Chưa có tin nào thì trả null, chatAppend rơi về chèn trước #newMsgBtn.
function dauKhungChat() {
  return chatArea.querySelector(".msg");
}

function goMoiTinCu() {
  if (_quanSatMoi) { try { _quanSatMoi.disconnect(); } catch (e) {} _quanSatMoi = null; }
  if (_moiTinCu && _moiTinCu.parentNode) _moiTinCu.parentNode.removeChild(_moiTinCu);
  _moiTinCu = null;
}

// Mồi đặt ở ĐẦU khung: vừa là điểm quan sát để tự tải, vừa là nút bấm tay. Chỉ chèn khi
// CHẮC CHẮN còn tin cũ - `.transcript:empty::after` là câu mời "Nói hoặc gõ để bắt đầu", một
// node con thường trực là câu đó biến mất im lặng (cùng cái bẫy đã ghi cho #newMsgBtn).
function datMoiTinCu() {
  goMoiTinCu();
  if (!_tinCu || !_tinCu.con) return;
  const d = document.createElement("div");
  d.className = "older-seed";
  d.innerHTML = `<button type="button" class="older-btn">${escapeHtml(window.t("app.older_load"))}</button>`;
  d.querySelector(".older-btn").onclick = () => taiTinCu();
  chatArea.insertBefore(d, dauKhungChat());
  _moiTinCu = d;
  if (typeof IntersectionObserver !== "function") return;   // không có thì còn nút bấm tay
  _quanSatMoi = new IntersectionObserver((mucs) => {
    if (mucs.some(m => m.isIntersecting)) taiTinCu();
  }, { root: chatArea, rootMargin: "240px 0px 0px 0px" });
  _quanSatMoi.observe(d);
}

async function taiTinCu() {
  const st = _tinCu;
  if (!st || !st.con || st.dangTai) return;
  st.dangTai = true;
  const nut = _moiTinCu && _moiTinCu.querySelector(".older-btn");
  if (nut) { nut.disabled = true; nut.textContent = window.t("app.older_loading"); }
  try {
    const u = `/sessions/${encodeURIComponent(st.sid)}/messages?limit=${TIN_MOI_LUOT}` +
      `&before_ts=${encodeURIComponent(st.ts)}&before_id=${encodeURIComponent(st.id)}`;
    const d = await (await fetch(u)).json();
    // Đổi phiên giữa chừng thì khúc vừa về là của cuộc khác - vứt đi, đừng chèn nhầm.
    if (!_tinCu || _tinCu !== st || st.sid !== savedSessionId || !d || d.error) return;
    const ds = d.messages || [];
    if (!ds.length) { st.con = false; goMoiTinCu(); return; }
    // Giữ chỗ cuộn: đo khoảng cách từ ĐÁY khung trước khi chèn rồi đặt lại sau, vì phần chèn
    // nằm phía trên nên scrollHeight tăng đúng bằng phần đó. Đo theo scrollTop thì sai.
    const cachDay = chatArea.scrollHeight - chatArea.scrollTop;
    _dangChenCu = true;
    _neoChenCu = _moiTinCu ? _moiTinCu.nextSibling : dauKhungChat();
    const them = [];
    ds.forEach(m => { const t = veTinDaLuu(m, st.brain); if (t) them.push(t); });
    _neoChenCu = null; _dangChenCu = false;
    convo = them.concat(convo);
    st.ts = ds[0].ts; st.id = ds[0].id; st.con = !!d.has_more;
    // Dựng LẠI cái mồi (hoặc gỡ hẳn khi hết tin) TRƯỚC khi đặt lại chỗ cuộn, để chiều cao
    // chốt xong rồi mới đo - gỡ mồi sau là màn nhích lên đúng bằng chiều cao cái mồi.
    // Dựng lại chứ không dùng tiếp cái cũ: IntersectionObserver KHÔNG bắn lần nữa khi node
    // vẫn nằm trong tầm nhìn liên tục, nên khúc vừa chèn mà ngắn hơn khung chat là kẹt luôn,
    // cuộn thêm cũng không tải tiếp. observe() mới thì luôn có một nhịp đầu.
    datMoiTinCu();
    chatArea.scrollTop = chatArea.scrollHeight - cachDay;
    persistSession();
  } catch (e) {
    if (nut) { nut.disabled = false; nut.textContent = window.t("app.older_load"); }
  } finally { st.dangTai = false; _dangChenCu = false; _neoChenCu = null; }
}

// ============================================
// Phiên hội thoại lưu DB (panel Lịch sử - sessions-ui.js gọi qua window.JavisSessions)
// ============================================
let sessionOpenSeq = 0;
async function openStoredSession(id, stillCurrent) {
  tatRanhTay();
  const ticket = ++sessionOpenSeq;
  try {
    const sess = await (await fetch(`/sessions/${encodeURIComponent(id)}?limit=${TIN_MOI_LUOT}`)).json();
    if (ticket !== sessionOpenSeq || (stillCurrent && !stillCurrent()) || !sess || sess.error) return;
    convo = [];
    hideActivity();
    goMoiTinCu();
    chatArea.innerHTML = "";
    const ds = sess.messages || [];
    ds.forEach(m => { const t = veTinDaLuu(m, sess.brain); if (t) convo.push(t); });
    _tinCu = ds.length
      ? { sid: id, brain: sess.brain, ts: ds[0].ts, id: ds[0].id, con: !!sess.has_more, dangTai: false }
      : null;
    datMoiTinCu();
    savedSessionId = id;          // lượt gửi tiếp theo → server resume đúng phiên này
    try { if (window.JavisInbox) window.JavisInbox.docPhien(id); } catch (e) {}
    // Phiên này đang generate NỀN → gắn bong bóng SỐNG (kèm phần đã stream) để xem tiếp trực tiếp.
    const t = turns[id];
    if (t && t.running) {
      t.bubble = createStreamingBubble();
      if (t.text) t.bubble.querySelector(".bubble").innerHTML = markdownToHtml(t.text);
      showActivity(Icons.msg("pen-line", window.t("app.act_writing")));
      runActions(turn.turnStart());
    } else {
      runActions(turn.turnDone());   // đổi sang phiên không chạy gì: đừng kẹt ở "ĐANG SUY NGHĨ"
    }
    // Phiên này đang chờ gói thuê bao mở lại hạn mức → gắn thẻ "tự chạy lại" dưới tin cuối.
    try { if (window.JavisResume) window.JavisResume.renderFor(id); } catch (e) {}
    persistSession();
    scrollBottom(true);
    ghimDay(ticket);
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
  tatRanhTay();
  convo = [];
  hideActivity();          // dọn chip + timer trước khi xoá trắng khung
  _tinCu = null; goMoiTinCu();
  chatArea.innerHTML = "";
  savedSessionId = null;
  persistSession();
  notifySessions();
  syncActiveUI();
  try { if (window.JavisBackground) window.JavisBackground.reset(); } catch (e) {}
}
function newChat() {
  sessionOpenSeq++;
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
// Khối ngữ cảnh do CHÍNH dashboard chèn vào ĐẦU tin trước khi gửi: file đang ghim trong trình
// sửa, đường dẫn file đính kèm. Chúng là chỉ dẫn cho model, không phải câu người dùng gõ.
// "[SKILL: " là khối do chat-slash.js dựng khi người dùng gõ lệnh "/". Gỡ nó ra thì bong bóng
// hiện ĐÚNG câu họ đã gõ, thay vì câu máy dựng quanh câu đó - khách báo đúng chuyện này 16/09.
// Giữ MỘT DÒNG: test_dinh_kem_khong_roi.js bóc đúng dòng này ra để chạy docDinhKem bằng node.
const _KHOI_NGU_CANH = ["[FILE ĐANG MỞ trong trình sửa của Javis:", "[File đính kèm", "[NGỮ CẢNH GIAO DIỆN:", "[SKILL: "];

// Gỡ mấy khối đó ra để lấy lại ĐÚNG câu người dùng đã gõ.
//
// Vì sao cần: lúc gõ, `appendUserMessage` nhận chữ sạch nên bong bóng đúng. Nhưng mở lại hội
// thoại cũ (F5, bấm vào một cuộc trong danh sách) thì `loadSession` dựng bong bóng từ chữ
// SERVER LƯU - tức là bản đã kèm khối. Và khối "file đang ghim" được gửi lại MỖI LƯỢT, nên
// hội thoại càng dài thì càng nhiều bong bóng chỉ toàn chữ máy, còn thanh mốc hội thoại thành
// một dãy dòng giống hệt nhau "[FILE ĐANG MỞ trong trình sửa..." - không nhìn ra câu nào với
// câu nào. Đó đúng là cảnh chủ repo chụp lại (2026-08-12).
//
// Cắt ở ĐÂY chứ không ở từng nơi gọi: hàm này là cửa duy nhất dựng bong bóng người dùng, nên
// mọi đường (gõ mới, F5, mở hội thoại cũ) đi qua cùng một chỗ. Và vì `dataset.text` cũng sạch
// theo, ba thứ đọc ké nó được sửa luôn: thanh mốc hội thoại, nút gửi lại, nút sửa câu hỏi -
// trước đây "gửi lại" một câu cũ là gửi kèm nguyên khối rồi bị chèn thêm khối mới lần nữa.
function chuNguoiGo(text) {
  let s = String(text == null ? "" : text);
  for (let vong = 0; vong < 4; vong++) {   // ghim + đính kèm có thể lồng nhau
    const t = s.replace(/^\s+/, "");
    if (!_KHOI_NGU_CANH.some(k => t.startsWith(k))) break;
    const i = t.indexOf("]\n\n");
    if (i < 0) break;   // không thấy chỗ kết thúc → thà giữ nguyên còn hơn cắt mất câu hỏi
    s = t.slice(i + 3);
  }
  return s;
}
// Chiều ngược của chuNguoiGo: đọc lại DANH SÁCH FILE ĐÍNH KÈM từ khối "[File đính kèm ...]"
// mà sendMessage đã chèn vào đầu tin. Server chỉ lưu chữ đã gửi, không lưu riêng đính kèm,
// nên đây là nguồn duy nhất để mở lại hội thoại mà bong bóng vẫn còn ảnh và thẻ file.
//
// Mỗi dòng "- <đường dẫn stage>" là một file. Tên file = đoạn cuối đường dẫn (nhận cả "/" lẫn
// "\" vì máy chủ có thể là Windows). Ảnh trỏ về /upload/raw?name=<tên> - đúng URL mà /upload
// đã trả lúc tải lên, nên xem lại được y như tin vừa gửi; stage bị dọn thì rơi vào khung
// "không còn xem lại được" như mọi ảnh cũ khác.
const _ANH_EXT = /\.(png|jpe?g|gif|webp|bmp)$/i;
function docDinhKem(text) {
  const out = [];
  let s = String(text == null ? "" : text);
  for (let vong = 0; vong < 4; vong++) {
    const t = s.replace(/^\s+/, "");
    if (!_KHOI_NGU_CANH.some(k => t.startsWith(k))) break;
    const i = t.indexOf("]\n\n");
    if (i < 0) break;
    const khoi = t.slice(0, i);
    if (khoi.startsWith("[File đính kèm")) {
      khoi.split("\n").forEach(dong => {
        const m = /^- (.+)$/.exec(dong.trim());
        if (!m) return;
        const ten = m[1].trim().split(/[\\/]/).pop();
        if (!ten) return;
        out.push({ name: ten, kind: _ANH_EXT.test(ten) ? "image" : "file",
                   url: "/upload/raw?name=" + encodeURIComponent(ten) });
      });
    }
    s = t.slice(i + 3);
  }
  return out;
}
window.JavisChuNguoiGo = chuNguoiGo;   // console.js dùng lại khi dựng bản xem trước hội thoại

// Ảnh/file đính kèm hiện NGAY TRONG bong bóng tin của người dùng.
//
// Trước đây ô này trỏ vào `URL.createObjectURL(file)` - một URL chỉ sống trong tab đang mở,
// và `clearAttachments()` thu hồi nó ngay sau khi gửi. Nên ảnh vừa gửi đã hỏng, F5 một cái
// là mất hẳn (lịch sử chỉ lưu tên + loại), và cũng không bấm phóng to được. Nay ảnh trỏ vào
// `/upload/raw` - chính file trong thư mục stage tạm trên máy chủ - nên xem lại được sau khi
// tải lại trang, và bọc trong `a.jv-img-link` để dùng chung lightbox với mọi ảnh khác.
//
// Staging là chỗ trung chuyển, bị dọn sau vài ngày. Ảnh 404 KHÔNG được để trơ thành ô vỡ:
// `vaAnhHong` đổi nó thành một khung nói thẳng là không xem lại được nữa.
function attachHtml(attachments) {
  if (!attachments || !attachments.length) return "";
  return `<div class="msg-attach">` + attachments.map(a => {
    const url = a.url || a.preview || "";
    if (a.kind === "image" && url) {
      const _u = escapeHtml(url), _t = escapeHtml(a.name || "");
      return `<a class="jv-img-link att-img" href="${_u}" data-img-ten="${_t}"`
        + ` target="_blank" rel="noopener" data-i18n-title="chat.att_zoom"`
        + ` title="${escapeHtml(t("chat.att_zoom"))}">`
        + `<img src="${_u}" alt="${_t}" loading="lazy"></a>`;
    }
    // Ảnh KHÔNG còn URL nào (tin cũ lưu từ bản trước, chỉ có tên + loại): nói thẳng là hết
    // xem lại được, chứ đừng giả vờ nó là một file đính kèm bình thường.
    if (a.kind === "image") return anhHetHan(a.name);
    return `<span class="file-tag">${ic("file-text")} ${escapeHtml(a.name || "")}</span>`;
  }).join("") + `</div>`;
}
// `data-i18n*` đi KÈM chữ đã dịch sẵn, không thay nó: từ điển nạp bằng fetch nên tin dựng lại
// lúc F5 có thể vẽ TRƯỚC khi từ điển về, và khi đó `t()` trả về chính cái khoá. Có thuộc tính
// này thì lượt quét `applyDom()` lúc từ điển về sẽ chữa lại - đúng lưới đã dựng ở 0.52.2.
function anhHetHan(ten) {
  return `<span class="att-mat" data-i18n-title="chat.att_gone_hint"`
    + ` title="${escapeHtml(t("chat.att_gone_hint"))}">`
    + `${ic("image")}<span class="att-mat-ten">${escapeHtml(ten || "")}</span>`
    + `<span class="att-mat-note" data-i18n="chat.att_gone">`
    + `${escapeHtml(t("chat.att_gone"))}</span></span>`;
}
// File tạm đã bị dọn -> ảnh 404. Thay thẻ <img> bằng khung "không còn xem lại được" thay vì
// để trình duyệt vẽ ô ảnh vỡ (người dùng đọc ô vỡ thành "app hỏng", không thành "hết hạn").
function vaAnhHong(root) {
  if (!root) return;
  root.querySelectorAll(".msg-attach img").forEach(img => {
    img.addEventListener("error", () => {
      const link = img.closest("a.att-img") || img;
      const ten = img.getAttribute("alt") || "";
      const tam = document.createElement("span");
      tam.innerHTML = anhHetHan(ten);
      if (link.parentNode) link.replaceWith(tam.firstElementChild || tam);
    }, { once: true });
  });
}

function appendUserMessage(text, attachments, ts) {
  text = chuNguoiGo(text);
  const div = document.createElement("div");
  div.className = "msg msg-user";
  div.dataset.text = text || "";   // giữ nguyên văn để gửi lại / sửa lại đúng chữ gốc
  const attHtml = attachHtml(attachments);
  // Tin dài (>10 dòng hoặc >900 ký tự) thu gọn lại, bấm "Xem thêm" để mở
  const isLong = text && (text.split("\n").length > 10 || text.length > 900);
  const textHtml = text
    ? `<div class="utext${isLong ? " clamped" : ""}">${escapeHtml(text)}</div>` +
      (isLong ? `<button class="clamp-more" type="button">${window.t("app.show_more")}</button>` : "")
    : "";
  div.innerHTML = `<div class="bubble">${textHtml}${attHtml}</div>` +
    actsHtml("user", ts === undefined ? Date.now() : ts, !!(text || "").trim());
  vaAnhHong(div);
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
// Thời lượng đọc được cho task dài: "45s" → "1m 56s" → "1h 30m 40s". Chủ repo báo (2026-08-24)
// việc nền chạy hàng chục phút mà đồng hồ đếm "1856s" thì không ai nhẩm ra là bao lâu.
function fmtElapsed(s) {
  if (s < 60) return s + "s";
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), giay = s % 60;
  return (h ? h + "h " + m + "m " : m + "m ") + giay + "s";
}
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
      activityEl.querySelector(".act-time").textContent = s >= 3 ? fmtElapsed(s) : "";
    }, 1000);
  }
  activityEl.querySelector(".act-text").innerHTML = html || window.t("app.act_processing");
  chatAppend(activityEl);   // re-append → luôn dưới cùng (kể cả dưới bubble đang stream)
  scrollBottom();
}
// Khoi tien trinh cua MOT luot: danh sach cong cu da goi, nam ngay tren bong bong tra loi.
// Khac chip o tren: chip chi co mot dong (buoc moi ghi de buoc cu, het luot la xoa), con khoi
// nay GIU lai du buoc va song qua F5. Luot khong goi cong cu nao thi khong dung khoi nao.
function veKhoiBuoc(t, dangChay) {
  if (!t || !window.JavisSteps || !window.JavisSteps.tomTat(t.buoc).hien) return null;
  const moi = !t.buocEl;
  t.buocEl = window.JavisSteps.ve(t.buocEl, t.buoc, dangChay);
  if (moi) { chatAppend(t.buocEl); scrollBottom(); }
  return t.buocEl;
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
  newMsgBtn.innerHTML = coTinMoi ? XUONG_ICON + " " + window.t("app.new_msg") : XUONG_ICON;
  newMsgBtn.title = coTinMoi ? window.t("app.new_msg_title") : window.t("app.scroll_bottom");
  newMsgBtn.setAttribute("aria-label", newMsgBtn.title);
}
veNutXuong(false);
window.addEventListener("javis:i18n", () => veNutXuong(newMsgBtn.classList.contains("has-new")));

// _neoChenCu: lúc CHÈN NGƯỢC tin cũ (cuộn lên tải tiếp), mọi bong bóng dựng ra phải nằm
// TRƯỚC tin cũ nhất đang hiện chứ không phải cuối khung. Đặt cái neo ở đây thay vì thêm
// tham số cho appendUserMessage/appendJavisMessage: hai hàm đó được gọi từ cả chục chỗ, thêm
// tham số là mười chỗ phải nhớ truyền đúng.
let _neoChenCu = null, _dangChenCu = false;
function chatAppend(el) {
  if (newMsgBtn.parentNode !== chatArea) chatArea.appendChild(newMsgBtn);
  chatArea.insertBefore(el, _neoChenCu || newMsgBtn);
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
  // Đang chèn ngược tin cũ: appendUserMessage/appendJavisMessage vẫn gọi vào đây theo thói
  // quen, mà cuộn xuống đáy lúc này là quăng người đọc khỏi chỗ họ đang đứng.
  if (_dangChenCu) return;
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
  btn.innerHTML = ic("check", { cls: "ic-ok" }) + " " + window.t("app.copied");
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
  // Chi tin NGUOI DUNG mang nut gui lai / sua lai, nen chu goc luon nam ngay tren chinh no.
  // Truoc day con mot nhanh nguoc len tim tin nguoi dung gan nhat - do la duong cua nut "tra
  // loi lai cau hoi phia tren" o tin Javis, da bo o 0.52.13.
  const text = msgEl.dataset.text || "";
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
    if (u) { u.classList.toggle("clamped"); t.textContent = u.classList.contains("clamped") ? window.t("app.show_more") : window.t("app.show_less"); }
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
  if (!window.ForceGraph) { graphStats.innerHTML = ic("triangle-alert", { cls: "ic-warn" }) + " " + window.t("app.graph_lib_err"); return; }
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
          '<a class="nm-btn" id="nodeOpenTab" target="_blank" rel="noopener">↗ ' + window.t("app.new_tab") + '</a>' +
          '<button class="nm-btn" id="nodeSave" type="button">' + ic("save") + ' ' + window.t("common.save") + '</button>' +
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
  body.innerHTML = `<div class="node-msg">${window.t("models.opening")}</div>`;
  m.classList.add("open");
  let d = {};
  try { d = await (await fetch(`/files/read?brain=${encodeURIComponent(brain)}&path=${encodeURIComponent(rel)}`)).json(); }
  catch (e) { body.innerHTML = `<div class="node-msg">${window.t("app.file_open_err")} ${escapeHtml(String((e && e.message) || e))}</div>`; return; }
  if (!d || d.error || d.editable === false) {
    body.innerHTML = `<div class="node-msg">${escapeHtml((d && d.error) || window.t("app.file_not_editable"))} · <a href="${rawUrl}" target="_blank" style="color:var(--accent)">${window.t("app.open_in_new_tab")}</a></div>`;
    return;
  }
  body.innerHTML = '<textarea id="nodeText" spellcheck="false"></textarea>';
  body.querySelector("#nodeText").value = d.content || "";
  saveBtn.style.display = "";
  saveBtn.innerHTML = ic("save") + " " + window.t("common.save");
  saveBtn.onclick = async () => {
    saveBtn.textContent = window.t("settings.saving");
    const fd = new FormData();
    fd.append("brain", brain); fd.append("path", rel);
    fd.append("content", body.querySelector("#nodeText").value);
    let r = {};
    try { r = await (await fetch("/files/write", { method: "POST", body: fd })).json(); } catch (e) { r = { error: (e && e.message) || window.t("app.err_low") }; }
    saveBtn.innerHTML = (r && r.ok) ? ic("check", { cls: "ic-ok" }) + " " + window.t("proj.instr_saved") : ic("triangle-alert", { cls: "ic-warn" }) + " " + window.t("app.err_cap");
    setTimeout(() => { saveBtn.innerHTML = ic("save") + " " + window.t("common.save"); }, 1600);
  };
  setTimeout(() => { try { body.querySelector("#nodeText").focus(); } catch (e) {} }, 30);
}
async function reloadGraph() {
  if (!javisGraph) return;
  graphStats.textContent = window.t("common.loading");
  const val = graphSource.value;
  const query = val.startsWith("path:")
    ? `path=${encodeURIComponent(val.slice(5))}`
    : `source=${val}`;
  try {
    const data = await javisGraph.load(query);
    const stats = data.stats || {};
    graphStats.textContent = window.t("app.graph_stats", { n: stats.total_notes, l: stats.total_links });
    renderConceptLabels(data.categories || [], stats.total_notes || 0);
  } catch (e) { graphStats.textContent = window.t("models.err") + " " + e.message; }
}
// ---- Việc CHỈ THẤY ĐƯỢC ở màn chính: hoãn khi đang đứng ở trang quản lý ----
// Đổi brain là đổi cả cockpit: đồ thị, số ký ức, số cộng sự, cờ cấu trúc vault. Nhưng bốn thứ
// đó chỉ NHÌN THẤY ĐƯỢC ở màn chính. Chạy chúng trong lúc người dùng đang ở trang Cộng sự là
// thiệt đôi đường: một lượt /graph nặng cộng /agents /skills /workflows lặp lại tranh chỗ với
// chính trang đang mở (trình duyệt chỉ mở được 6 kết nối một lúc), rồi thư viện đồ thị quay
// warmupTicks ĐỒNG BỘ trên toàn bộ node - màn hình đứng hình vài giây, trắng trơn. Chủ dự án
// báo 22/09: đổi bộ não ở trang Cộng sự thì "bị đen màn hình luôn, nó bị trắng tinh".
// Hoãn lại; quay về màn chính mới chạy, và chỉ chạy một lần cho lần đổi gần nhất.
let _cockpitCho = false;
function _oManChinh() {
  // Không biết đang ở trang nào (console.js chưa dựng xong) thì cứ chạy như cũ: thà làm thừa
  // một lượt còn hơn treo vĩnh viễn số liệu của màn chính.
  try { return !(window.JavisNav && window.JavisNav.active) || window.JavisNav.active() === "home"; }
  catch (e) { return true; }
}
function capNhatManChinh() {
  if (!_oManChinh()) {
    _cockpitCho = true;
    // Ô đếm note nằm ngay cạnh ô chọn brain nên NHÌN THẤY ĐƯỢC cả ở trang quản lý: để nguyên
    // con số của brain cũ là nói dối. Về gạch ngang cho tới lúc đếm thật (số note của từng
    // brain vẫn có sẵn trong chính tên từng dòng của ô chọn).
    graphStats.textContent = "-";
    return;
  }
  _cockpitCho = false;
  reloadGraph();
  connectGraphWatch();   // theo dõi realtime trên nguồn mới
  loadMemStats();   // bộ nhớ theo vault → đổi vault thì đổi số ký ức
  loadBrainStats(); // agent/skill/workflow theo vault
  checkVault();     // kiểm tra cấu trúc vault mới chọn
}
// console.js gọi mỗi lần đổi trang: về tới màn chính thì trả nợ lần đổi brain đang hoãn.
window.JavisCockpit = { veManChinh() { if (_cockpitCho) capNhatManChinh(); },
                        dangCho: () => _cockpitCho };

// Trang đang mở có MƯỢN khung chat và tự mở phiên của nó không (Cộng sự: phiên agent:<slug>
// hay workflow:<slug>; Coding: phiên của repo). Phiên đó KHÔNG phải cuộc chính của brain.
function _trangGiuKhungChat() {
  try { return !!(window.JavisNav && window.JavisNav.giuKhungChat && window.JavisNav.giuKhungChat()); }
  catch (e) { return false; }
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
    // Trang Cộng sự (và Coding) tự dựng lại theo brain mới rồi tự mở phiên của nó. Nhớ phiên
    // của nó vào _viewByBrain là lần sau quay lại brain này, trang Trò chuyện mở thẳng vào
    // hội thoại của một trợ lý; còn khôi phục cuộc chính vào đây là ĐÈ lên đúng phiên trang
    // kia vừa mở - chủ dự án 22/09: "màn ở giữa khung chat hiển thị dữ liệu của hội thoại cũ".
    // Ở đó chỉ xoá trắng, phần mở phiên để trang kia lo.
    const muon = _trangGiuKhungChat();
    if (savedSessionId && !muon) _viewByBrain[_lastBrain] = savedSessionId;
    _lastBrain = nb;
    resetChatView();                                       // xoá ngay khung của brain cũ
    if (!muon && _viewByBrain[nb]) openStoredSession(_viewByBrain[nb]);   // brain quen → mở lại phiên đang dở
  }
  capNhatManChinh();
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
      graphStats.textContent = window.t("app.graph_stats", { n: s.nodes, l: s.links });
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
        ? window.t("app.vault_ok_missing", { miss: miss })
        : window.t("app.vault_bad", { miss: miss });
      vaultBanner.classList.add("show");
    }
  } catch (e) {}
}

vbInit.addEventListener("click", async () => {
  vbInit.disabled = true;
  const old = vbInit.textContent;
  vbInit.textContent = window.t("app.creating");
  try {
    const fd = new FormData();
    fd.append("brain", currentBrainPath());
    const d = await (await fetch("/vault/init", { method: "POST", body: fd })).json();
    if (d.ok) {
      vbText.innerHTML = `${ic("check", { cls: "ic-ok" })} ${window.t("app.created")} ${escapeHtml((d.created || []).join(", ") || window.t("app.already_full"))}`;
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
    div.title = window.t("app.spotlight_cluster", { ten: c.name });
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
  grp.label = window.t("app.external_folder");
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
  fmHint.textContent = window.t("common.loading");
  try {
    const res = await fetch(`/browse?path=${encodeURIComponent(path || "")}`);
    const data = await res.json();
    fmCurrent = data.path || "";
    fmPath.textContent = fmCurrent || window.t("app.drives");
    fmList.innerHTML = "";
    if (data.parent !== null && data.parent !== undefined) {
      const up = document.createElement("div");
      up.className = "fm-row up";
      up.innerHTML = `<span class="fm-name">${ic("arrow-up")} ${window.t("app.up_one_level")}</span>`;
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
    fmHint.textContent = data.here_md ? window.t("app.md_here", { count: Number(data.here_md) }) : (data.error || window.t("app.pick_notes_folder"));
  } catch (e) {
    fmHint.textContent = window.t("models.err") + " " + e.message;
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
  // BÁO ĐỔI BRAIN như mọi đường khác, thay vì chỉ vẽ lại đồ thị. Gán thẳng `.value` không sinh
  // sự kiện `change`, nên bản cũ đổi não mà khung chat vẫn giữ hội thoại của não trước, trang
  // Cộng sự vẫn liệt kê trợ lý của não trước và cây thư mục vẫn là cây cũ - mọi thứ ăn theo
  // brain đều nghe ô này.
  graphSource.dispatchEvent(new Event("change"));
});
window.addEventListener("resize", () => { if (javisGraph) javisGraph.resize(); });

let _stopBtnTick = 0;
function pumpAudioLevel() {
  if (javisGraph) javisGraph.setLevel(voice.getLevel());
  // Cập nhật hiển thị nút stop ~6 lần/giây (theo dõi cả lúc Javis đang đọc)
  if (_theoLoi && (_stopBtnTick % 3) === 0) nhipTheoLoi();   // V3: chữ theo lời ~20 lần/giây
  if ((_stopBtnTick++ % 10) === 0) {
    updateStopBtn();
    // (Voice V1) orb do đạo diễn vẽ từ sự kiện thật: voice.js báo onSpeakEnd khi hết hàng đợi.
    // Chốt an toàn: nếu giọng đã im mà đạo diễn còn tưởng đang nói (vd trình duyệt nuốt sự
    // kiện ended), ép về đúng sự thật.
    if (turn.speaking && !voice.isSpeaking() && !voice.isPaused()) runActions(turn.ttsEnd());
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
  if (!auto && learnBtn) { learnBtn.disabled = true; learnBtn.innerHTML = ic("brain") + " " + window.t("app.learning"); }
  if (memResult) memResult.innerHTML = auto ? ic("brain") + " " + window.t("app.learning_bg") : window.t("app.learning_msg");
  try {
    const fd = new FormData();
    fd.append("brain", currentBrainPath());
    const d = await (await fetch("/reflect", { method: "POST", body: fd })).json();
    if (d.ok) {
      if (memResult) memResult.innerHTML = (auto ? ic("brain") + " " + window.t("app.selflearn_prefix") + " " : "") + escapeHtml(d.summary || window.t("app.learned_done"));
      if (d.facts != null && memCount) memCount.textContent = d.facts;
    } else {
      if (memResult) memResult.innerHTML = ic("triangle-alert", { cls: "ic-warn" }) + " " + escapeHtml(d.error || window.t("app.learn_failed"));
    }
  } catch (e) {
    if (memResult) memResult.innerHTML = ic("triangle-alert", { cls: "ic-warn" }) + " " + window.t("app.err_net");
  } finally {
    reflecting = false;
    if (!auto && learnBtn) { learnBtn.innerHTML = ic("brain") + " " + window.t("app.learn_from_convo"); learnBtn.disabled = false; }
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

// Dòng nhắc ngay dưới các chip (vd "có file chưa tải lên được"). Tự xoá ở lần gỡ file hay
// tải file mới kế tiếp.
let attachNote = "";
function renderChips() {
  attachBar.classList.toggle("has-items", pendingAttachments.length > 0 || !!pinnedNote || !!attachNote);
  attachBar.innerHTML = "";
  if (pinnedNote) {
    const chip = document.createElement("div");
    chip.className = "attach-chip pinned";
    chip.setAttribute("role", "button");
    chip.tabIndex = 0;
    chip.title = `${pinnedNote.abs}\n${window.t("app.pin_title")}`;
    chip.innerHTML = `<div class="chip-ico">${ic("file-text")}</div>`
      + `<div class="chip-info"><span class="chip-name">${escapeHtml(pinnedNote.name)}</span>`
      + `<span class="chip-meta">${window.t("app.pin_meta")}</span></div>`
      + `<span class="chip-edit" aria-hidden="true">${ic("pen-line")}</span>`
      + `<button class="chip-x" data-unpin="1" title="${window.t("app.unpin_file")}">${ic("x")}</button>`;
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
    // Ảnh vừa dán/chọn cũng phải BẤM PHÓNG TO được ngay ở thanh đính kèm - trước đây ô này
    // là ảnh chết, muốn xem cho rõ phải gửi đi rồi mở lại. Ưu tiên URL trên máy chủ (tải xong),
    // lúc còn đang tải thì tạm dùng blob để không phải chờ mới thấy hình.
    const _tUrl = a.kind === "image" ? (a.url || a.preview || "") : "";
    const thumb = _tUrl
      ? `<a class="jv-img-link chip-thumb" href="${escapeHtml(_tUrl)}"`
        + ` data-img-ten="${escapeHtml(a.name || "")}" target="_blank"`
        + ` rel="noopener" data-i18n-title="chat.att_zoom"`
        + ` title="${escapeHtml(t("chat.att_zoom"))}">`
        + `<img src="${escapeHtml(_tUrl)}" alt=""></a>`
      : `<div class="chip-ico">${a.uploading ? ic("loader", { cls: "ic-spin" }) : ic("file-text")}</div>`;
    const meta = a.uploading
      ? (a.statusText || window.t("app.att_processing"))
      : (a.statusText ? a.statusText : (fmtSize(a.size) + (a.folder ? ` → ${escapeHtml(a.folder)}` : "")));
    chip.innerHTML = `${thumb}<div class="chip-info"><span class="chip-name">${escapeHtml(a.name)}</span><span class="chip-meta">${meta}</span></div><button class="chip-x" data-i="${i}">${ic("x")}</button>`;
    attachBar.appendChild(chip);
  });
  if (attachNote) {
    const note = document.createElement("div");
    note.className = "attach-note";
    note.textContent = attachNote;
    attachBar.appendChild(note);
  }
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
  attachNote = "";
  renderChips();
}
function clearAttachments() {
  pendingAttachments.forEach(a => { if (a.preview) URL.revokeObjectURL(a.preview); });
  pendingAttachments = [];
  attachNote = "";
  renderChips();
}

async function uploadFile(file) {
  const isImg = file.type.startsWith("image/");
  let _xong = null;
  const att = {
    name: file.name || "paste.png",
    kind: isImg ? "image" : "file",
    preview: isImg ? URL.createObjectURL(file) : null,
    uploading: true, statusText: window.t("app.att_uploading"), path: null, size: file.size,
    sources: null, attachments: null,
  };
  // Lời hứa "tải xong" (thành hay hỏng đều xong) để sendMessage đợi được thay vì gửi thiếu.
  att.xong = new Promise(r => { _xong = r; });
  pendingAttachments.push(att);
  attachNote = "";
  renderChips();
  try {
    await _taiLen(file, att);
  } finally {
    att.uploading = false;
    renderChips();
    if (_xong) _xong();
  }
}
async function _taiLen(file, att) {
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
    if (!resp.ok) { att.uploading = false; att.statusText = window.t("app.att_server_err", { code: resp.status }); renderChips(); return; }
    const up = await resp.json();
    if (!up.ok) { att.uploading = false; att.statusText = up.error ? (window.t("app.err_low") + ": " + up.error) : window.t("app.att_upload_err"); renderChips(); return; }
    att.path = up.staged; att.name = up.name; att.size = up.size; att.kind = up.kind;
    att.url = up.url || "";   // đường xem lại trên máy chủ (bong bóng chat dùng, không phải blob)
    att.sources = up.sources; att.attachments = up.attachments;
    att.uploading = false; att.statusText = "";
  } catch (e) {
    att.uploading = false;
    att.statusText = (e && e.name === "AbortError") ? window.t("app.att_timeout") : window.t("app.err_net_low");
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
// Vài khung có ô thả RIÊNG của nó (ngăn kéo project...) và tự đánh dấu [data-localdrop].
// Thả vào đó thì file phải đi vào đúng khung đó, không được rơi tiếp xuống khung chat -
// chủ repo báo 03/09: kéo file vào ô "kéo thả vào đây" của project thì nó nhảy sang chat.
const inLocalDrop = (e) => !!(e.target && e.target.closest && e.target.closest("[data-localdrop]"));
let dragDepth = 0;
window.addEventListener("dragenter", (e) => {
  if (e.dataTransfer && [...e.dataTransfer.types].includes("Files")) {
    dragDepth++; if (!inLocalDrop(e)) dropOverlay.classList.add("show");
  }
});
// dragover nổ liên tục nên nó là chỗ chuẩn nhất để bật/tắt lớp phủ: rê qua ô thả riêng thì
// lớp phủ biến đi, rê ra ngoài lại hiện.
window.addEventListener("dragover", (e) => {
  e.preventDefault();
  if (inLocalDrop(e)) dropOverlay.classList.remove("show");
  else if (dragDepth > 0) dropOverlay.classList.add("show");
});
window.addEventListener("dragleave", () => { if (--dragDepth <= 0) { dragDepth = 0; dropOverlay.classList.remove("show"); } });
window.addEventListener("drop", (e) => {
  dragDepth = 0; dropOverlay.classList.remove("show");
  if (inLocalDrop(e)) return;   // chỗ kia đã preventDefault + chặn bọt, không đụng vào
  e.preventDefault();
  if (e.dataTransfer?.files) [...e.dataTransfer.files].forEach(uploadFile);
});

// ============================================
// Events
// ============================================
chatInput.addEventListener("input", () => {
  chatInput.style.height = "auto";
  // Ô nhập NỞ THEO CHỮ như claude.ai (chủ yêu cầu 27/08): xuống dòng là thấy toàn bộ văn
  // bản, không phải cuộn trong một ô 3 dòng. Trần ở trang Trò chuyện là 40% màn hình
  // (đo lúc gõ nên đổi cỡ cửa sổ vẫn đúng); màn chính ô nhập nằm trong cột phải hẹp hơn
  // nên trần 200px, quá nữa mới cuộn trong ô. CSS chỉ giữ lưới đỡ 45vh, không chặn nữa.
  const _cap = document.body.classList.contains("on-chat")
    ? Math.round(window.innerHeight * 0.4) : 200;
  chatInput.style.height = Math.min(chatInput.scrollHeight, _cap) + "px";
});
// Bộ gõ tiếng Việt/IME có thể phát keydown Enter trước compositionend. Nếu gửi và xoá
// textarea ở thời điểm đó, trình duyệt sẽ chốt phần chữ đang ghép vào ô vừa xoá, làm sót
// lại ký tự hoặc từ cuối. Giữ cờ riêng cho các trình duyệt báo isComposing không ổn định.
let chatInputComposing = false;
chatInput.addEventListener("compositionstart", () => { chatInputComposing = true; });
chatInput.addEventListener("compositionend", () => { chatInputComposing = false; });
chatInput.addEventListener("keydown", (e) => {
  if (chatInputComposing || e.isComposing || e.keyCode === 229) return;
  // Máy chạm (điện thoại/tablet): Enter là XUỐNG DÒNG như mọi app nhắn tin, gửi bằng nút
  // Gửi. Bàn phím ảo không có Shift+Enter nên giữ lối desktop là user không cách nào viết
  // tin nhiều dòng. Đo bằng pointer: coarse (con trỏ CHÍNH là ngón tay) chứ không đo bề
  // rộng màn hình - laptop cảm ứng có chuột vẫn giữ Enter-gửi như cũ.
  if (window.matchMedia("(pointer: coarse)").matches) return;
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
sendBtn.addEventListener("click", () => sendMessage());

// Chế độ luôn nghe (hands-free): bấm 1 lần → nghe liên tục đến khi bấm lại
let handsFree = false;

// Tắt rảnh tay từ chỗ KHÔNG phải cú bấm của người dùng (mic hỏng). Gom về một hàm vì trạng
// thái này nằm ở ba nơi - biến, lớp CSS của nút, và công tắc loa - và bỏ sót một nơi thì giao
// diện nói dối: nút vẫn sáng "đang nghe" trong khi không có gì đang nghe cả.
function tatRanhTay() {
  attention.stop(); _liveWaitingWake = false; _liveBusyUntil = 0;
  _liveToolCount = 0;
  liveWake.cancelListening();
  _sendEpoch++;
  clearTimeout(_tinChoTimer); _tinChoTimer = null; _tinChoLuot = null;
  clearTimeout(_tinDutMangTimer); _tinDutMangTimer = null; _tinDutMang = [];
  _choTaiLen = null; _tuGiong = false;
  handsFree = false;
  voice.handsFree = false;        // thôi rình ngắt lời ngay, đừng đợi vòng 500 ms
  voiceBtn.classList.remove("handsfree");
  voice.cancelListening();
  voice.stopSpeaking();
  tatLive();
  runActions(turn.micOff());
  updateVoiceFocus();
  try { if (window.JavisTts) window.JavisTts.set(false); } catch (e) {}
}

// Câu báo lỗi mic. Nói ĐÚNG nguyên nhân, vì ba nguyên nhân cần ba hành động khác hẳn nhau và
// câu chung "hãy cấp quyền" là lời khuyên KHÔNG LÀM ĐƯỢC với hai trong ba trường hợp.
function alertMic(err) {
  if (err === "not-allowed") {
    // Trang không chạy ở ngữ cảnh bảo mật thì trình duyệt chặn thẳng, và KHÔNG hề hỏi quyền.
    // Bảo họ "cấp quyền" lúc này là chỉ họ đi tìm một cái nút không tồn tại. Hay gặp khi mở
    // Javis qua địa chỉ LAN hoặc tên miền chưa có HTTPS.
    if (!window.isSecureContext) {
      alert(window.t("app.mic_insecure") + "\n" + "\n"
        + window.t("app.mic_insecure_fix"));
    } else {
      alert(window.t("app.mic_denied") + "\n" + "\n"
        + window.t("app.mic_denied_fix"));
    }
  } else if (err === "audio-capture") {
    // Trước đây lỗi này im lặng hoàn toàn: mic không bao giờ chạy mà không ai nói vì sao.
    alert(window.t("app.mic_none") + "\n" + "\n"
      + window.t("app.mic_none_fix"));
  } else if (err === "service-not-allowed") {
    alert(window.t("app.mic_service_blocked") + "\n" + "\n"
      + window.t("app.mic_service_blocked_fix"));
  } else if (err === "not-supported") {
    alert(window.t("app.mic_unsupported"));
  }
  // Lỗi khác (mạng, start-failed…) KHÔNG hiện hộp thoại: chúng thoáng qua và tự thử lại được,
  // còn hộp thoại thì chặn cứng cả trang.
}
voiceBtn.addEventListener("click", () => {
  if (voiceMode !== "live" && !voice.isSupported()) { alert(window.t("app.voice_unsupported")); return; }
  handsFree = !handsFree;
  if (handsFree) attention.start();
  voiceBtn.classList.toggle("handsfree", handsFree);
  voice.handsFree = handsFree && voiceMode !== "live";   // bật ngay, không đợi vòng 500 ms
  // Loa đi theo mic (chủ repo yêu cầu 02/09): bật nghe là muốn NÓI CHUYỆN bằng giọng, nên
  // Javis phải đáp bằng giọng; tắt nghe là quay về gõ chữ, Javis im. Điện thoại từng không
  // có chỗ nào bật loa cả, nên gộp vào mic là một nút lo cả hai chiều.
  try { if (window.JavisTts) window.JavisTts.set(handsFree); } catch (e) {}
  // Voice V2 bậc Live: nút mic mở phiên nghe nói thẳng thay cho Web Speech + TTS.
  if (voiceMode === "live") {
    if (handsFree) batLive();
    else tatRanhTay();
    return;
  }
  if (handsFree) {
    voice.startListening();
  } else {
    tatRanhTay();
  }
});

// ---- Voice V1: hai nút trong Cài đặt nhanh (lưu localStorage, không đụng settings.json) ----
// Im lặng bao lâu thì gửi (500 / 800 / 1200 ms, mặc định 1200 - chủ dự án chốt 17/09) và có cho ngắt lời Javis bằng giọng không.
(function () {
  // 0.58.8: ba thẻ radio đổi thành một ô chọn (#endpointSel). Giá trị lưu KHÔNG đổi nên
  // người đang dùng không bị reset về mặc định.
  const ep = localStorage.getItem("javis.endpoint") || "1200";
  const epSel = document.getElementById("endpointSel");
  if (epSel) {
    epSel.value = ep;
    if (!epSel.value) epSel.value = "1200";      // giá trị cũ không còn trong danh sách
    turn.opts.minDelay = parseInt(epSel.value, 10) || 1200;
    epSel.addEventListener("change", () => {
      turn.opts.minDelay = parseInt(epSel.value, 10) || 1200;
      localStorage.setItem("javis.endpoint", epSel.value);
    });
  }
  const barge = localStorage.getItem("javis.bargeIn") !== "0";
  voice.bargeEnabled = barge;
  const qb = document.getElementById("qsBarge");
  if (qb) {
    qb.checked = barge;
    qb.addEventListener("change", () => {
      voice.bargeEnabled = qb.checked;
      localStorage.setItem("javis.bargeIn", qb.checked ? "1" : "0");
    });
  }
})();

// Tự nghe lại khi rảnh (không đang xử lý, không đang nói) - giữ mic sống ở hands-free
setInterval(() => {
  // Cờ rảnh tay cho voice.js: NGẮT LỜI chỉ được rình khi người dùng đang thật sự nói chuyện
  // bằng giọng. Đồng bộ ở đây chứ không rải theo từng chỗ bật/tắt rảnh tay (nút mic, Esc,
  // mic hỏng, phiên Live đóng - năm nơi), vì sót một nơi là ngắt lời hoặc chết câm hoặc rình
  // cả lúc người ta đã quay về gõ chữ. Vòng này chạy hai lần mỗi giây nên lệch không đáng kể.
  tickVoiceFocus();
  voice.handsFree = handsFree && voiceMode !== "live" && !attention.waiting();
  // `micHong()` là chốt thứ hai (chốt thứ nhất là tatRanhTay() trong onError). Giữ cả hai vì
  // vòng này chạy hai lần mỗi giây: sót một nhịp là một hộp thoại nữa đập vào mặt người dùng.
  //
  // KHÔNG còn đòi `!isProcessing`: trong lúc Javis đang nghĩ, người ta vẫn phải nói chen vào
  // hay nói thêm ngữ cảnh được, y như nói chuyện với người thật. Chốt cũ đóng mic suốt thời
  // gian xử lý (có khi vài chục giây) nên nói vào chỗ trống, không ai nghe (chủ dự án báo
  // 15/09). Tin nói lúc ấy đi qua sendMessage: nó dừng lượt cũ rồi gửi lại câu mới, và tin
  // đầu đã nằm trong kho phiên nên model vẫn thấy đủ ngữ cảnh.
  if (handsFree && voiceMode !== "live" && !voice.isListening && !voice.isSpeaking()
      && !voice.isTranscribing
      && !(voice.micHong && voice.micHong())) {
    voice.startListening(true);   // true = máy tự gọi, không phải người bấm
  }
}, 500);

document.getElementById("voiceFocusResume").addEventListener("click", () => resumeVoiceFocus());

let spacePressed = false;
document.addEventListener("keydown", (e) => {
  // KHÔNG cướp phím Space khi con trỏ đang ở BẤT KỲ ô nhập nào (input/textarea/select/
  // contenteditable) - nếu không sẽ không gõ được dấu cách trong form skill, editor file, settings…
  const _ae = document.activeElement;
  const _typing = _ae && (_ae.tagName === "INPUT" || _ae.tagName === "TEXTAREA" || _ae.tagName === "SELECT" || _ae.isContentEditable);
  if (e.code === "Space" && !handsFree && !spacePressed && !_typing) {
    // Bấm-giữ Space cũng là mở mic -> bật loa. Thả phím là hết câu, không phải "tắt nghe",
    // nên KHÔNG tắt loa ở keyup - tắt thì câu trả lời ngay sau đó bị câm.
    try { if (window.JavisTts) window.JavisTts.set(true); } catch (e2) {}
    e.preventDefault(); spacePressed = true; voice.startListening();
  }
  if (e.code === "Escape") {
    // Esc chỉ thoát chế độ rảnh tay + tắt mic + đóng popup node nếu đang mở. KHÔNG còn dừng câu
    // trả lời hay ngắt Javis đang nói (đã bỏ theo yêu cầu - đã có nút bật/tắt tiếng và nút Dừng).
    tatRanhTay();
    try { if (window.JavisTts) window.JavisTts.set(false); } catch (e2) {}   // Esc = thoát nói chuyện bằng giọng
    if (typeof closeNodePopup === "function") closeNodePopup();
  }
});
document.addEventListener("keyup", (e) => {
  if (e.code === "Space" && spacePressed) { spacePressed = false; voice.stopListening(); }
});

// Reset
document.getElementById("resetBtn").addEventListener("click", () => {
  tatRanhTay();
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ action: "reset" }));
  chatArea.innerHTML = "";
  convo = []; savedSessionId = null;   // xoá phiên đã lưu (số liệu giữ nguyên)
  persistSession();
});

// ---- Chọn giọng / tốc độ / ngôn ngữ nghe ----
// 0.58.8: bảy thẻ radio giọng + thanh trượt tốc độ + hai thẻ ngôn ngữ nghe đổi hết thành ô
// chọn, và popover nổi (di sản từ hồi bộ chọn nằm trên thanh tiêu đề) đã gỡ - mọi thứ nay
// nằm thẳng trong trang Cài đặt. KHOÁ localStorage giữ nguyên nên không ai bị reset.
const voiceSel = document.getElementById("voiceSel");
const rateSel = document.getElementById("rateSel");
const recLangSel = document.getElementById("recLangSel");
const savedVoice = localStorage.getItem("javis.voice") || "vi-VN-HoaiMyNeural";
const savedRate = parseFloat(localStorage.getItem("javis.rate") || "1.10");
const savedRecLang = localStorage.getItem("javis.recLang") || "vi-VN";
function rateToPct(r) { const p = ((r - 1) * 100).toFixed(0); return (p >= 0 ? "+" : "") + p + "%"; }
// Gán value cho <select> mà giá trị đó không có trong danh sách thì select về RỖNG (ô trắng,
// không lỗi, không ai biết). Nên mọi chỗ gán đều phải có đường lùi.
function _chonHoacDau(sel, val) {
  if (!sel) return val;
  sel.value = val;
  if (!sel.value) sel.selectedIndex = 0;
  return sel.value;
}
const voiceNow = _chonHoacDau(voiceSel, savedVoice);
const recNow = _chonHoacDau(recLangSel, savedRecLang);
// Tốc độ: thanh trượt cũ đẻ ra giá trị bất kỳ (1,37×) còn ô chọn chỉ có 5 mức, nên phải NÉO
// về mức gần nhất thay vì bỏ trống ô.
let rateNow = savedRate;
if (rateSel) {
  let gan = null;
  Array.from(rateSel.options).forEach(o => {
    const x = parseFloat(o.value);
    if (gan === null || Math.abs(x - savedRate) < Math.abs(gan - savedRate)) gan = x;
  });
  if (gan !== null) { rateNow = gan; rateSel.value = gan.toFixed(2); }
}
voice.setVoice(voiceNow); voice.setRate(rateToPct(rateNow)); voice.setRecognitionLang(recNow);
if (voiceSel) voiceSel.addEventListener("change", () => {
  voice.setVoice(voiceSel.value); localStorage.setItem("javis.voice", voiceSel.value);
});
if (rateSel) rateSel.addEventListener("change", () => {
  const r = parseFloat(rateSel.value);
  voice.setRate(rateToPct(r)); localStorage.setItem("javis.rate", r.toString());
});
if (recLangSel) recLangSel.addEventListener("change", () => {
  tatRanhTay();
  voice.setRecognitionLang(recLangSel.value); localStorage.setItem("javis.recLang", recLangSel.value);
});
document.getElementById("testVoiceBtn")?.addEventListener("click", () => {
  const v = (voiceSel && voiceSel.value) || savedVoice;
  // force: nghe thử là hành động chủ động của user, phải kêu kể cả khi đang tắt tiếng (mặc định).
  voice.speak(v.includes("HoaiMy") ? window.t("app.voice_sample_hoaimy") : window.t("app.voice_sample_namminh"), { force: true });
});
// Nút loa header đã bỏ (0.48.3) - công tắc giọng nay chỉ còn nút trên THANH NHẬP
// (#ttsToggleBar) và công tắc trong Cài đặt nhanh, cả hai do quick-settings.js lo.

// Resume AudioContext khi user tương tác lần đầu (để analyser pulse hoạt động)
function resumeAudio() {
  try { voice._ensureCtx(); } catch (e) {}
}
document.addEventListener("click", resumeAudio, { once: true });
document.addEventListener("keydown", resumeAudio, { once: true });


// Nhãn hiển thị cho TỪNG provider. Trước đây chỉ có hai nhánh openrouter-hoặc-CLI, nên chọn
// Groq/Gemini/OpenAI đều bị dán nhãn "CLI" - vừa sai, vừa phạm đúng luật trong CLAUDE.md là
// phải trả lời ĐÚNG engine đang chạy.
const ENGINE_LABEL = {
  "anthropic-cli": "Claude Code", "openai-oauth": "ChatGPT", "openrouter": "OpenRouter",
  "openai": "OpenAI", "anthropic-api": "Anthropic", "gemini": "Gemini", "groq": "Groq",
  "ollama": "Ollama",
  // Hai engine CLI gói thuê bao. Nhãn phải TÁCH khỏi nhà cung cấp API cùng tên: khác đường
  // và khác hoá đơn (gói đã trả, so với API key trả theo lượt gọi).
  "grok-cli": "Grok Build", "antigravity-cli": "Antigravity",
};
// Một dòng nhỏ dưới câu trả lời: lượt này chạy BẰNG GÌ, ở chế độ nào, và tốn bao nhiêu
// token vào. Trước đây chuyện này hoàn toàn vô hình - chỉ lộ ra khi nhà cung cấp báo vượt hạn
// mức, tức là đã muộn. Thấy được thì người dùng tự biết mức vừa bật có ăn thật hay không.
// Tên NÓI ĐÚNG NÓ LÀM GÌ, không phải nó cũ hay mới. "Đường cũ" là góc nhìn của người viết
// code; với người dùng đó là chế độ gửi đủ mọi thứ, an toàn nhất, và đúng là thứ họ chọn khi
// bấm "Tắt" - gọi nó là "cũ" vừa nghe như đang xin lỗi, vừa làm người ta tưởng máy đang hỏng.
// Tên ở đây khớp tên nút bên trang Mức dùng để nhìn một dòng là biết mình đang ở đâu.
//
// Engine+model đứng ĐẦU dòng này từ 0.52.13. Trước đó nó là một badge riêng ở đầu khung hội
// thoại, và badge ấy có hai vấn đề: nó chiếm chỗ để lặp lại thứ thanh model ngay dưới ô chat
// đã nói, và nó chỉ nói về LƯỢT CUỐI - cuộn ngược lên một hội thoại từng đổi model, hay từng
// bị đẩy sang model dự phòng lúc model chính quá tải, thì badge nói sai về mọi tin phía trên.
// Gắn vào TỪNG TIN thì mỗi tin tự khai đúng bộ não đã sinh ra nó, và đầu khung được trả lại.
const CTX_PATH_LABEL = {
  legacy: "app.ctx_legacy", sources: "app.ctx_sources", fast: "app.ctx_fast",
  readonly: "app.ctx_readonly", orchestrator: "app.ctx_orchestrator", write: "app.ctx_write",
  workflow: "app.ctx_workflow",
  // Bot chuyên trách vốn nhẹ hơn cả mức Siêu tiết kiệm (không CLAUDE.md, không MEMORY.md,
  // không đặc tả tool) nên nó có tên riêng - gộp vào "Đầy đủ" là nói ngược hẳn sự thật.
  bot: "app.ctx_bot",
};
function _renderCtxLine(msgEl, data) {
  // Có engine mà chưa có ctx_path thì VẪN vẽ: hai thứ đến từ hai chỗ khác nhau trong payload,
  // và bỏ cả dòng chỉ vì thiếu một nửa là mất luôn nửa đang có.
  if (!msgEl || !data || !(data.ctx_path || data.engine)) return;
  const cu = data.ctx_path === "legacy";
  const tok = Number(data.ctx_in) || 0;
  const old = msgEl.querySelector(".msg-ctx");
  if (old) old.remove();
  const el = document.createElement("div");
  // Lớp "saved" (tô khác) chỉ có nghĩa khi BIẾT lượt này đi đường tiết kiệm. Không có ctx_path
  // thì đừng đoán - gắn bừa là nói dối bằng màu sắc.
  el.className = "msg-ctx" + (data.ctx_path && !cu ? " saved" : "");
  // Bấm vào là sang trang Mức dùng, nơi có khối chọn mức ngay đầu trang - thấy chế độ đang
  // chạy mà không biết chỉnh ở đâu thì thông tin đó cũng chỉ để bực mình.
  el.dataset.usageGoto = "usage";
  const phan = [];
  if (data.engine) {
    // Tên model cắt ngắn cho vừa dòng; tên đầy đủ nằm ở tooltip bên dưới.
    phan.push((ENGINE_LABEL[data.engine] || data.engine)
              + (data.model ? " · " + _shortModel(data.model) : ""));
  }
  if (data.ctx_path) phan.push(CTX_PATH_LABEL[data.ctx_path] ? window.t(CTX_PATH_LABEL[data.ctx_path]) : data.ctx_path);
  if (tok) phan.push(_fmtTok(tok) + " token");
  el.textContent = phan.join(" · ");
  const chuThich = [];
  if (data.engine) {
    chuThich.push(window.t("app.ctx_engine", { model: data.model ? ": " + data.model : "" }));
  }
  if (data.ctx_path) {
    chuThich.push(cu ? window.t("app.ctx_hint_full")
                     : window.t("app.ctx_hint_saving"));
  }
  el.title = chuThich.join("\n");
  msgEl.appendChild(el);
}

async function refreshTgStatus() {
  const el = document.getElementById("setTgStatus");
  if (!el) return;
  try {
    const s = await (await fetch("/telegram/status")).json();
    if (!s.enabled) el.innerHTML = ic("circle", { cls: "ic-fill ic-dim" }) + " " + window.t("settings.tag_off");
    else if (!s.token_set) el.innerHTML = ic("triangle-alert", { cls: "ic-warn" }) + " " + window.t("app.tg_no_token");
    else el.innerHTML = s.running ? ic("circle", { cls: "ic-fill ic-ok" }) + " " + window.t("kanban.st_running") + (s.chat_id ? " " + window.t("app.tg_only_chat") + " " + s.chat_id : " " + window.t("app.tg_everyone")) : ic("loader") + " " + window.t("app.tg_not_running");
    // Menu lệnh "/" đặt hụt: bot vẫn chạy nên mọi thứ ở trên vẫn xanh, chỉ là gõ "/" trong
    // Telegram không sổ ra danh sách lệnh. Không nói ra thì không ai đoán được vì sao.
    if (s.loi_menu_lenh) el.innerHTML += '<div class="set-note">' + ic("triangle-alert", { cls: "ic-warn" }) + " " + escapeHtml(s.loi_menu_lenh) + "</div>";
  } catch (e) { el.textContent = ""; }
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
  let src = d.today, scope = window.t("app.usage_today");
  if ((!src || !(src.items || []).length) && d.all_time && (d.all_time.items || []).length) { src = d.all_time; scope = window.t("app.usage_alltime"); }
  const items = (src && src.items) || [];
  const tot = (src && src.total) || { in: 0, out: 0, cost: 0 };
  const row = (nameHtml, tok, extra) => `<div style="display:flex;justify-content:space-between;gap:6px;font-size:11px;padding:1px 0;${extra || ""}"><span style="color:var(--text2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${nameHtml}</span><span style="color:#7aa2ff;white-space:nowrap;font-variant-numeric:tabular-nums">${tok}</span></div>`;
  let html;
  if (!items.length) {
    html = `<div class="mcp-item dim">${window.t("app.usage_none_today")}</div>`;
  } else {
    html = items.map(i => {
      const lbl = _PROV_LABEL[i.provider] || escapeHtml(i.provider);
      const cost = i.cost > 0 ? ` · $${i.cost.toFixed(i.cost < 0.01 ? 4 : 2)}` : "";
      const nm = `${escapeHtml(lbl)} <span class="dim">${escapeHtml(_shortModel(i.model))}</span>`;
      return row(nm, `${_fmtTok(i.in)}↑ ${_fmtTok(i.out)}↓${cost}`);
    }).join("");
    html += row(`<b>${window.t("app.usage_total")} ${scope}</b>`, `<b>${_fmtTok(tot.in)}↑ ${_fmtTok(tot.out)}↓${tot.cost > 0 ? " · $" + tot.cost.toFixed(2) : ""}</b>`, "border-top:1px solid var(--hairline);margin-top:2px;padding-top:3px");
  }
  html += await _usageSavingRow();
  if (d.openrouter && d.openrouter.remaining != null) {
    html += row(window.t("app.or_remaining"), `$${(+d.openrouter.remaining).toFixed(2)}`, "margin-top:4px;color:var(--green)");
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
    || (d.muc === "custom" ? window.t("app.saving_custom") : "?");
  const dod = d.do_duoc || {};
  const uoc = ((d.uoc_tinh || {}).muc || {})[d.muc] || {};
  // Ưu tiên số ĐO ĐƯỢC; chưa đủ dữ liệu thì mới dùng ước lượng, và nói rõ là ước lượng.
  let phu;
  if (dod.du_du_lieu) phu = window.t("app.saving_measured", { p: dod.phan_tram });
  else if (d.muc === "off") phu = window.t("app.saving_off");
  else if (uoc.phan_tram) phu = window.t("app.saving_est", { p: uoc.phan_tram });
  else phu = window.t("app.saving_unknown");
  const html = `<div style="display:flex;justify-content:space-between;gap:6px;font-size:11px;padding:3px 0 0;margin-top:3px;border-top:1px solid var(--hairline);cursor:pointer" data-usage-goto="usage" title="${window.t("app.open_usage_page")}">`
    + `<span style="color:var(--text2)">${window.t("app.saving_label")} <b>${escapeHtml(ten)}</b></span>`
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

// Gọi /auth/status với vài lần thử lại - app "Thêm vào màn hình chính" trên iPhone khởi
// động NGUỘI mỗi lần mở lại (tiến trình mạng mới tinh, không như tab Safari giữ ấm), nên
// lần gọi đầu hay timeout/lỗi trong lúc mạng chưa kịp lên. Trả về null (KHÔNG PHẢI {})
// khi hỏi mãi vẫn không được, để bên gọi phân biệt "chưa rõ" với "chắc chắn chưa đăng nhập".
async function _fetchAuthStatus(retries = 3, delayMs = 500) {
  for (let i = 0; i < retries; i++) {
    try {
      const r = await fetch("/auth/status");
      if (r.ok) return await r.json();
    } catch (e) {}
    if (i < retries - 1) await new Promise((res) => setTimeout(res, delayMs));
  }
  return null;
}

// Cổng đăng nhập THỐNG NHẤT (thay initSetup+initAuth ở boot):
// - đã đăng nhập (hoặc local không bắt buộc) → onboarding tùy chọn.
// - public/đã đặt mật khẩu mà CHƯA có tài khoản → ÉP wizard tạo tài khoản (mật khẩu bắt buộc).
// - đã có tài khoản mà chưa đăng nhập → màn đăng nhập.
let _wizardMandatory = false;
async function initAuthGate() {
  const s = await _fetchAuthStatus();
  // null = hỏi server thất bại hẳn (mất mạng thật) - ĐỪNG ép màn đăng nhập lên trong lúc
  // cookie phiên rất có thể vẫn còn hợp lệ, chỉ là chưa hỏi được. Cứ để nguyên UI, mọi lệnh
  // gọi API thật sự (chat, file...) tự lộ ra nếu phiên đã hết hạn thật.
  if (!s) return;
  if (s.authed) { initSetup(); return; }
  if (s.needs_setup) {
    _wizardMandatory = !!s.require_login;
    const wz = document.getElementById("setupWizard");
    if (!wz) { authOverlay.classList.add("open"); return; }
    if (_wizardMandatory) {
      const pass = document.getElementById("wzPass"); if (pass) pass.required = true;
      const tw = document.getElementById("wzTokenWrap"); if (tw) tw.style.display = "";
      const note = document.getElementById("wzErr"); if (note) note.textContent = window.t("app.wz_mandatory");
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
    err.textContent = d.error || window.t("app.login_failed");
  } catch (e) { err.textContent = window.t("app.err_net"); }
});
["authPass", "authCode"].forEach((id) => {
  const el = document.getElementById(id);
  if (el) el.addEventListener("keydown", (e) => { if (e.key === "Enter") document.getElementById("authSubmit").click(); });
});

// ---- Settings ----
// Ô "Model Claude (khi dùng CLI)" nạp danh sách từ server thay vì ba lựa chọn ghi cứng trong
// index.html. Ghi cứng là một cái bẫy im lặng: dòng model mới (Fable) không có trong ô, mà
// gán `select.value` một giá trị không có option thì trình duyệt lặng lẽ nhả về "" - tức mở
// Cài đặt rồi bấm Lưu là model đang chạy bị đổi về Mặc định mà không ai nói gì.
async function loadClaudeModels(cur) {
  const sel = document.getElementById("setClaudeModel");
  if (!sel) return;
  let ids = [];
  try {
    const d = await (await fetch("/provider/models?provider=anthropic-cli")).json();
    ids = d.models || [];
  } catch (e) {}
  if (cur && ids.indexOf(cur) < 0) ids.unshift(cur);   // model đang chạy luôn phải có mặt
  const nhan = (id) => id.charAt(0).toUpperCase() + id.slice(1);
  sel.innerHTML = '<option value="">' + window.t("common.default") + '</option>'
    + ids.map((id) => `<option value="${id}">${nhan(id)}</option>`).join("");
  sel.value = cur || "";
}

async function openSettings() {
  settingsOverlay.classList.add("open");
  try {
    const s = await (await fetch("/settings")).json();
    _settingsCache = s;
    document.getElementById("setWsName").value = s.workspace_name || "";
    document.getElementById("setEngine").value = (s.model && s.model.engine) || "cli";
    await loadClaudeModels((s.model && s.model.claude_model) || "");
    loadOrModels((s.model && s.model.openrouter_model) || "");
    document.getElementById("setKeyHint").textContent = (s.model && s.model.openrouter_key_set) ? window.t("app.saved_paren", { v: s.model.openrouter_key }) : window.t("app.none_paren");
    document.getElementById("setTgEnabled").checked = !!(s.telegram && s.telegram.enabled);
    document.getElementById("setTgChat").value = (s.telegram && s.telegram.chat_id) || "";
    document.getElementById("setTgHint").textContent = (s.telegram && s.telegram.token_set) ? window.t("app.saved_paren", { v: s.telegram.token }) : window.t("app.none_paren");
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
    ? ic("check", { cls: "ic-ok" }) + " " + window.t("app.pw_set")
    : ic("triangle-alert", { cls: "ic-warn" }) + " " + window.t("app.pw_unset");
  const u = document.getElementById("setAuthUser");
  if (u && a.username) u.value = a.username;
  const cur = document.getElementById("setAuthCur");
  const curLbl = document.getElementById("setAuthCurLbl");
  if (cur) { cur.hidden = !co; if (!co) cur.value = ""; }
  if (curLbl) curLbl.hidden = !co;
  const p = document.getElementById("setAuthPass");
  if (p) p.placeholder = co ? window.t("app.pw_ph_change") : window.t("app.pw_ph_set");
  return co;
}
window.__javisRefreshAuthRow = refreshAuthRow;
function _saveSetting(section, dataObj, btn) {
  const fd = new FormData();
  fd.append("section", section);
  fd.append("data", JSON.stringify(dataObj));
  const old = btn.textContent; btn.disabled = true; btn.textContent = window.t("settings.saving");
  return fetch("/settings", { method: "POST", body: fd }).then(r => r.json()).then(d => {
    btn.innerHTML = d.ok ? ic("check", { cls: "ic-ok" }) + " " + window.t("proj.instr_saved") : (ic("triangle-alert", { cls: "ic-warn" }) + " " + escapeHtml(d.error || window.t("app.err_low")));
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
      .then(() => { const wn = document.getElementById("workspaceName"); if (wn) wn.textContent = document.getElementById("setWsName").value.trim() || "Javis OS"; });
  });
  document.getElementById("saveModel").addEventListener("click", (e) => {
    const sel = document.getElementById("setOrModelSel");
    const orModel = (sel.value === "__custom__") ? document.getElementById("setOrModel").value.trim() : sel.value;
    const d = { engine: document.getElementById("setEngine").value, claude_model: document.getElementById("setClaudeModel").value, openrouter_model: orModel };
    const k = document.getElementById("setOrKey").value.trim(); if (k) d.openrouter_key = k;
    _saveSetting("model", d, e.target).then(() => { document.getElementById("setOrKey").value = ""; openSettings(); });
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
    const btn = e.target; btn.disabled = true; const old = btn.textContent; btn.textContent = window.t("app.sending");
    try {
      const r = await (await fetch("/telegram/test", { method: "POST" })).json();
      btn.innerHTML = r.ok
        ? (r.total > 1 ? `${ic("check", { cls: "ic-ok" })} ${window.t("app.tg_sent_n", { sent: Number(r.sent) || 0, total: Number(r.total) || 0 })}` + (r.error ? " " + window.t("app.tg_has_err") : "") : ic("check", { cls: "ic-ok" }) + " " + window.t("app.tg_sent"))
        : (ic("triangle-alert", { cls: "ic-warn" }) + " " + escapeHtml(r.error || window.t("app.err_low")));
    } catch (e) { btn.innerHTML = ic("triangle-alert", { cls: "ic-warn" }) + " " + window.t("app.err_net_low"); }
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
    catch (err) { bao(false, window.t("app.auth_status_err")); return; }
    btn.disabled = true; btn.textContent = window.t("settings.saving");
    if (!hasPw) {
      // Lần đầu đặt mật khẩu → /auth/setup (cấp cookie luôn)
      if (!pass || pass.length < 8) { bao(false, window.t("app.pw_min8")); return; }
      const fd = new FormData(); fd.append("username", user || "admin"); fd.append("password", pass);
      try {
        const d = await (await fetch("/auth/setup", { method: "POST", body: fd })).json();
        bao(!!d.ok, d.ok ? window.t("app.pw_set_ok") : (d.error || window.t("app.err_low")));
        if (d.ok) { document.getElementById("setAuthPass").value = ""; openSettings(); }
      } catch (err) { bao(false, window.t("app.err_net_low")); }
      return;
    }
    // Đã có tài khoản → ĐỔI qua /auth/password (đòi mật khẩu hiện tại). /auth/setup là đường
    // lần-đầu, gọi nó ở đây chỉ nhận về "Đã có tài khoản - hãy đăng nhập".
    const cur = curEl ? curEl.value : "";
    if (!cur) { bao(false, window.t("app.pw_need_cur")); return; }
    if (pass && pass.length < 8) { bao(false, window.t("app.pw_new_min8")); return; }
    if (!pass && !user) { bao(false, window.t("app.nothing_changed")); return; }
    const fd = new FormData();
    fd.append("current_password", cur); fd.append("username", user);
    if (pass) fd.append("password", pass);
    try {
      const d = await (await fetch("/auth/password", { method: "POST", body: fd })).json();
      bao(!!d.ok, d.ok ? (pass ? window.t("app.pw_changed") : window.t("app.user_changed")) : (d.error || window.t("app.err_low")));
      if (d.ok) {
        document.getElementById("setAuthPass").value = "";
        if (curEl) curEl.value = "";
        refreshAuthRow();
      }
    } catch (err) { bao(false, window.t("app.err_net_low")); }
  });
  document.getElementById("logoutBtn").addEventListener("click", async () => {
    await fetch("/auth/logout", { method: "POST" }); location.reload();
  });
  document.getElementById("disableAuthBtn").addEventListener("click", async () => {
    if (!confirm(window.t("app.disable_auth_confirm"))) return;
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
    sel.innerHTML = `<option value="__custom__">${window.t("app.or_custom_model")}</option><option disabled>${window.t("models.mp_loading_tag")}</option>`;
    try {
      const d = await (await fetch("/openrouter/models")).json();
      sel.innerHTML = `<option value="__custom__">${window.t("app.or_custom_model")}</option>`;
      (d.models || []).forEach(m => {
        const o = document.createElement("option");
        o.value = m.id; o.textContent = m.id;
        sel.appendChild(o);
      });
      _orModelsLoaded = (d.models || []).length > 0;
    } catch (e) {
      sel.innerHTML = `<option value="__custom__">${window.t("app.or_custom_model")}</option>`;
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
  // Công cụ tuỳ chọn trong trình hướng dẫn: chỉ HỎI khi máy thật sự thiếu. Máy cá nhân
  // thường đã có sẵn Chrome, mời họ tải thêm cả trăm MB là mời một việc vô nghĩa.
  (async () => {
    try {
      const d = await (await fetch("/tools/optional")).json();
      const ct = ((d && d.tools) || []).find(x => x.id === "browser");
      if (ct && ct.trang_thai === "chua_cai") {
        const o = document.getElementById("wzCongCu");
        if (o) o.style.display = "";
      }
    } catch (e) {}
  })();
  document.getElementById("wzFinish").addEventListener("click", async () => {
    const err = document.getElementById("wzErr"); err.textContent = "";
    const ws = document.getElementById("wzWsName").value.trim();
    const user = document.getElementById("wzUser").value.trim();
    const pass = document.getElementById("wzPass").value;
    const prov = (document.querySelector('input[name="wzprov"]:checked') || {}).value || "anthropic-cli";
    const btn = document.getElementById("wzFinish"); btn.disabled = true; btn.textContent = window.t("settings.saving");
    // Ô mã thiết lập nằm ở mục 2, còn nút bấm và dòng báo lỗi nằm tít dưới đáy. Bỏ trống rồi
    // bấm thì người dùng chỉ thấy một dòng đỏ ở đáy, không thấy ô nào đang trống - có người
    // còn không biết là CÓ một ô như vậy. Nên khi lỗi phải KÉO MÀN HÌNH tới đúng ô đó.
    const _soiOTrong = (o, cau) => {
      err.textContent = cau;
      btn.disabled = false; btn.textContent = window.t("app.wz_start");
      if (o) { try { o.scrollIntoView({ block: "center", behavior: "smooth" }); o.focus(); } catch (e) {} }
    };
    if (_wizardMandatory && !pass) {
      return _soiOTrong(document.getElementById("wzPass"),
                        window.t("app.wz_pw_required"));
    }
    // Chặn ngay ở đây thay vì để server trả 403: cùng một câu lỗi, nhưng người dùng thấy con
    // trỏ nhảy vào đúng ô đang trống nên hiểu ngay phải làm gì.
    const _tokO = document.getElementById("wzToken");
    if (_wizardMandatory && _tokO && !_tokO.value.trim()) {
      return _soiOTrong(_tokO, window.t("app.wz_token_missing"));
    }
    try {
      if (pass) {
        const d = await (await fetch("/auth/setup", { method: "POST", body: _fd({ username: user || "admin", password: pass, setup_token: _tokO ? _tokO.value.trim() : "" }) })).json();
        // Server từ chối vì mã sai (403) thì cũng kéo về đúng ô mã, đừng để người dùng tự dò.
        if (!d.ok) { return _soiOTrong(/MÃ THIẾT LẬP/i.test(d.error || "") ? _tokO : null,
                                       d.error || window.t("app.wz_pw_err")); }
      }
      await fetch("/settings", { method: "POST", body: _fd({ section: "general", data: JSON.stringify({ workspace_name: ws, setup_done: true }) }) });
      const _PM = { "anthropic-cli": "sonnet", "openai-oauth": "gpt-5.5", "openrouter": "openai/gpt-4o-mini" };
      const _mp = { main: { provider: prov, model: _PM[prov] || "sonnet" } };
      const _ork = (document.getElementById("wzOrKeyInput") || {}).value;
      if (prov === "openrouter" && _ork && _ork.trim()) _mp.openrouter_key = _ork.trim();
      await fetch("/settings", { method: "POST", body: _fd({ section: "model", data: JSON.stringify(_mp) }) });
      // Người dùng đã tick "cài trình duyệt": khởi động việc tải ở NỀN rồi vào app luôn. Không
      // bắt họ ngồi nhìn thanh tiến độ cả trăm MB ngay phút đầu tiên; trang Công cụ có đủ
      // trạng thái để xem sau. Hỏng thì cũng không chặn đường vào app.
      const _ctB = document.getElementById("wzCtBrowser");
      if (_ctB && _ctB.checked) {
        try {
          await fetch("/tools/optional/install", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: "browser" }),
          });
        } catch (e) {}
      }
      location.reload();
    } catch (e) { err.textContent = window.t("app.err_net"); btn.disabled = false; btn.textContent = window.t("app.wz_start"); }
  });
}

// Wizard - chọn nhà cung cấp (card radio) + hiện ô key OpenRouter + gợi ý cách kết nối
(function () {
  const cards = document.querySelectorAll("#wzProv .wz-card");
  if (!cards.length) return;
  const orKey = document.getElementById("wzOrKey");
  const hint = document.getElementById("wzProvHint");
  const HINTS = {
    "anthropic-cli": () => window.t("app.wz_hint_cli_1") + "<code>claude auth login --claudeai</code>" + window.t("app.wz_hint_cli_2"),
    "openai-oauth": () => window.t("app.wz_hint_gpt_1") + "<b>Models</b>" + window.t("app.wz_hint_gpt_2") + "<code>codex login</code>" + window.t("app.wz_hint_gpt_3"),
    "openrouter": () => window.t("app.wz_hint_or_1") + "<a href='https://openrouter.ai/keys' target='_blank' style='color:var(--link-ink)'>openrouter.ai/keys</a>" + window.t("app.wz_hint_or_2"),
  };
  function pick(prov) {
    cards.forEach(c => c.classList.toggle("sel", c.dataset.prov === prov));
    const r = document.querySelector('input[name="wzprov"][value="' + prov + '"]'); if (r) r.checked = true;
    if (orKey) orKey.style.display = prov === "openrouter" ? "" : "none";
    if (hint) hint.innerHTML = HINTS[prov] ? HINTS[prov]() : "";
  }
  cards.forEach(c => c.addEventListener("click", () => pick(c.dataset.prov)));
  pick("anthropic-cli");
  window.addEventListener("javis:i18n", () => {
    const da = document.querySelector('input[name="wzprov"]:checked');
    pick((da && da.value) || "anthropic-cli");
  });
})();

// ============================================
// Boot
// ============================================
initAuthGate();
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

// ============================================
// "Mở như app" (cài PWA) - desktop lẫn Android, không chỉ mobile.
// Chrome/Edge bắn beforeinstallprompt khi manifest đủ điều kiện cài (icon PNG vuông có
// sizes - xem manifest.json). Giữ event lại rồi hiện nút trên thanh trạng thái; bấm nút
// mới bung hộp cài của trình duyệt. Safari/Firefox không có event → nút không hiện,
// iOS vẫn đi đường Share → Thêm vào màn hình chính như cũ.
// ============================================
(() => {
  const btn = document.getElementById("installAppBtn");
  if (!btn) return;
  let deferredPrompt = null;
  const daLaApp = () => {
    try {
      return window.matchMedia("(display-mode: standalone)").matches
        || window.navigator.standalone === true;   // iOS standalone cũ
    } catch (e) { return false; }
  };
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();   // chặn mini-infobar tự bung trên Android, để nút của mình chủ động
    deferredPrompt = e;
    if (!daLaApp()) btn.hidden = false;
  });
  btn.addEventListener("click", async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    try { await deferredPrompt.userChoice; } catch (e) {}
    deferredPrompt = null;
    btn.hidden = true;   // từ chối thì trình duyệt sẽ bắn lại event ở phiên sau, nút tự hiện lại
  });
  window.addEventListener("appinstalled", () => { deferredPrompt = null; btn.hidden = true; });
  // Mở cho install-nudge.js dùng chung ĐÚNG một event beforeinstallprompt này. Trình duyệt
  // chỉ bắn nó MỘT lần mỗi phiên và chỉ dùng lại được một lần, nên hai nơi cùng bắt là một
  // nơi mất - phải đi qua cùng một chỗ giữ.
  window.JavisInstall = {
    daLaApp: daLaApp,
    coHopCai: () => !!deferredPrompt,
    moHopCai: async () => {
      if (!deferredPrompt) return false;
      deferredPrompt.prompt();
      let ket = null;
      try { ket = await deferredPrompt.userChoice; } catch (e) {}
      deferredPrompt = null;
      btn.hidden = true;
      return !!(ket && ket.outcome === "accepted");
    },
  };
})();
