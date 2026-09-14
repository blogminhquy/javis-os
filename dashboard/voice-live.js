/* voice-live.js - NGHE NÓI THẲNG (Voice V2 bậc Live, docs/dev/2026-09-voice-v2-spec.md mục 2).

   Mở WebSocket /ws/voice-live, đẩy PCM16 mono 16 kHz từ mic lên, nhận PCM16 mono 24 kHz về và
   phát nối tiếp. Server nói chuyện với nhà cung cấp (Gemini Live / OpenAI Realtime) nên file
   này KHÔNG biết nhà cung cấp là ai: đổi nhà cung cấp là chuyện của trang Cài đặt.

   Khung JSON nhận: ready | interrupted (xả hàng đợi phát ngay, đó là ngắt lời) | transcript
   (role, text, final) | tool (name, status) | turn_done | reconnected | error. Byte nhận = audio.
   Khung JSON gửi: text | context (khối ngữ cảnh giao diện, chỉ khi đổi) | played (số ms đã phát
   tới lúc bị ngắt, để server cắt ngữ cảnh đúng chỗ đã nghe) | stop.

   Bắt mic bằng ScriptProcessorNode: đã lỗi thời nhưng chạy trên mọi trình duyệt còn dùng và
   không cần nạp file worklet riêng qua CSP. Khối 4096 mẫu ở 16 kHz = 256 ms mỗi khung.
   Ghi chú: KHÔNG dùng ký tự em dash. */
(function () {
  "use strict";

  var IN_RATE = 16000, OUT_RATE = 24000;
  var ws = null, inCtx = null, outCtx = null, proc = null, src = null, stream = null;
  var nextAt = 0, playing = [], on = false, opts = {};
  var wasSpeaking = false, speakTimer = null;
  var utterStartAt = 0, lastCtx = "";   // mốc bắt đầu phát câu hiện tại; ngữ cảnh đã gửi lần cuối

  function emit(name) {
    var fn = opts[name];
    if (typeof fn === "function") { try { fn.apply(null, Array.prototype.slice.call(arguments, 1)); } catch (e) {} }
  }

  function floatToPcm16(f32) {
    var out = new Int16Array(f32.length);
    for (var i = 0; i < f32.length; i++) {
      var s = Math.max(-1, Math.min(1, f32[i]));
      out[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return out;
  }

  // Giảm mẫu thô về 16 kHz khi AudioContext không chịu chạy đúng 16 kHz (Safari).
  function downsample(f32, from, to) {
    if (from === to) return f32;
    var ratio = from / to, n = Math.floor(f32.length / ratio), out = new Float32Array(n);
    for (var i = 0; i < n; i++) out[i] = f32[Math.floor(i * ratio)];
    return out;
  }

  function playChunk(buf) {
    if (!outCtx) return;
    var i16 = new Int16Array(buf);
    if (!i16.length) return;
    var f32 = new Float32Array(i16.length);
    for (var i = 0; i < i16.length; i++) f32[i] = i16[i] / 0x8000;
    var ab = outCtx.createBuffer(1, f32.length, OUT_RATE);
    ab.getChannelData(0).set(f32);
    var node = outCtx.createBufferSource();
    node.buffer = ab;
    node.connect(outCtx.destination);
    var t = Math.max(outCtx.currentTime + 0.02, nextAt);
    if (!playing.length && !utterStartAt) utterStartAt = t;
    node.start(t);
    nextAt = t + ab.duration;
    playing.push(node);
    node.onended = function () { var k = playing.indexOf(node); if (k >= 0) playing.splice(k, 1); tickSpeaking(); };
    tickSpeaking();
  }

  // Số ms của câu hiện tại đã thật sự phát ra loa (0 nếu chưa phát gì).
  function playedMs() {
    if (!outCtx || !utterStartAt) return 0;
    return Math.max(0, Math.round((outCtx.currentTime - utterStartAt) * 1000));
  }

  function flushPlayback() {
    playing.forEach(function (n) { try { n.stop(); } catch (e) {} });
    playing = [];
    nextAt = 0;
    utterStartAt = 0;
    tickSpeaking();
  }

  function sendJson(obj) {
    if (ws && ws.readyState === WebSocket.OPEN) { try { ws.send(JSON.stringify(obj)); } catch (e) {} }
  }

  // Báo trạng thái "Javis đang nói" theo hàng đợi phát thật (không có sự kiện nào khác đáng tin).
  function tickSpeaking() {
    clearTimeout(speakTimer);
    var now = !!playing.length;
    if (now !== wasSpeaking) { wasSpeaking = now; emit(now ? "onSpeakStart" : "onSpeakEnd"); }
    if (now) speakTimer = setTimeout(tickSpeaking, 250);
  }

  async function start(o) {
    if (on) return true;
    opts = o || {};
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 } });
    } catch (e) { emit("onError", "mic:" + (e && e.name || "error")); return false; }
    var AC = window.AudioContext || window.webkitAudioContext;
    try { inCtx = new AC({ sampleRate: IN_RATE }); } catch (e) { inCtx = new AC(); }
    outCtx = new AC({ sampleRate: OUT_RATE });
    try { await inCtx.resume(); await outCtx.resume(); } catch (e) {}
    var sid = "", brain = "brain";
    try { sid = (opts.sessionId && opts.sessionId()) || ""; brain = (opts.brain && opts.brain()) || "brain"; } catch (e) {}
    var proto = location.protocol === "https:" ? "wss://" : "ws://";
    ws = new WebSocket(proto + location.host + "/ws/voice-live?session_id=" + encodeURIComponent(sid) + "&brain=" + encodeURIComponent(brain));
    ws.binaryType = "arraybuffer";
    ws.onmessage = function (e) {
      if (e.data instanceof ArrayBuffer) { playChunk(e.data); return; }
      var d; try { d = JSON.parse(e.data); } catch (err) { return; }
      if (d.type === "ready") emit("onReady", d);
      else if (d.type === "interrupted") {
        var ms = playedMs();          // đo TRƯỚC khi xả, xả xong là mất mốc
        flushPlayback();
        sendJson({ type: "played", ms: ms });
        emit("onInterrupted", ms);
      }
      else if (d.type === "transcript") emit("onTranscript", d.role, d.text || "", !!d.final);
      else if (d.type === "tool") emit("onTool", d.name, d.status);
      else if (d.type === "turn_done") { utterStartAt = 0; emit("onTurnDone"); }
      else if (d.type === "reconnected") emit("onReconnected");
      else if (d.type === "error") emit("onError", d.message || "error");
    };
    ws.onclose = function () { if (on) { stop(); emit("onClosed"); } };
    ws.onerror = function () { emit("onError", "ws"); };
    await new Promise(function (res) { ws.onopen = res; setTimeout(res, 4000); });
    src = inCtx.createMediaStreamSource(stream);
    proc = inCtx.createScriptProcessor(4096, 1, 1);
    proc.onaudioprocess = function (ev) {
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      var f32 = downsample(ev.inputBuffer.getChannelData(0), inCtx.sampleRate, IN_RATE);
      ws.send(floatToPcm16(f32).buffer);
    };
    src.connect(proc);
    proc.connect(inCtx.destination);   // Chrome chỉ chạy onaudioprocess khi node nối tới đích
    on = true;
    emit("onStarted");
    return true;
  }

  function sendText(text) {
    if (text) sendJson({ type: "text", text: String(text) });
  }

  // Ngữ cảnh giao diện (trang đang mở, đoạn bôi đen): chỉ gửi khi ĐỔI, rỗng cũng là một trạng thái.
  function sendContext(text) {
    text = String(text || "");
    if (text === lastCtx || !ws || ws.readyState !== WebSocket.OPEN) return false;
    lastCtx = text;
    sendJson({ type: "context", text: text });
    return true;
  }

  function stop() {
    on = false;
    flushPlayback();
    try { if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "stop" })); } catch (e) {}
    try { if (ws) ws.close(); } catch (e) {}
    ws = null;
    lastCtx = ""; utterStartAt = 0;
    try { if (proc) { proc.disconnect(); proc.onaudioprocess = null; } if (src) src.disconnect(); } catch (e) {}
    proc = null; src = null;
    try { if (stream) stream.getTracks().forEach(function (t) { t.stop(); }); } catch (e) {}
    stream = null;
    try { if (inCtx) inCtx.close(); } catch (e) {}
    try { if (outCtx) outCtx.close(); } catch (e) {}
    inCtx = null; outCtx = null;
    emit("onStopped");
  }

  window.JavisVoiceLive = { start: start, stop: stop, sendText: sendText, sendContext: sendContext,
                            playedMs: playedMs, isOn: function () { return on; },
                            isSpeaking: function () { return !!playing.length; } };
})();
