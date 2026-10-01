/* voice-live.js - NGHE NÓI THẲNG (Voice V2 bậc Live, docs/dev/2026-10-voice-call-spec.md phụ lục A5).

   Mở WebSocket /ws/voice-live, đẩy PCM16 mono 16 kHz từ mic lên, nhận PCM16 mono 24 kHz về và
   phát nối tiếp. Server nói chuyện với nhà cung cấp (Gemini Live / OpenAI Realtime) nên file
   này KHÔNG biết nhà cung cấp là ai: đổi nhà cung cấp là chuyện của trang Cài đặt.

   Khung JSON nhận: ready | interrupted (xả hàng đợi phát ngay, đó là ngắt lời) | transcript
   (role, text, final) | tool (name, status) | turn_done | reconnected | error. Byte nhận = audio.
   Khung JSON gửi: text | context (khối ngữ cảnh giao diện, chỉ khi đổi) | played (số ms đã phát
   tới lúc bị ngắt, để server cắt ngữ cảnh đúng chỗ đã nghe) | stop.

   Bắt mic bằng ScriptProcessorNode: đã lỗi thời nhưng chạy trên mọi trình duyệt còn dùng và
   không cần nạp file worklet riêng qua CSP. Khối 4096 mẫu ở 16 kHz = 256 ms mỗi khung.

   ChatGPT Live (0.65.17, docs/dev/2026-10-voice-call-spec.md mục 3.4): khung `ready` mang
   transport "webrtc" thì KHÔNG đẩy PCM. Trình duyệt dựng RTCPeerConnection lấy track mic, kênh
   dữ liệu "oai-events" (offer thiếu nó là bị từ chối), gửi offer qua khung webrtc_offer, nhận
   webrtc_answer rồi nói chuyện THẲNG với OpenAI; tiếng Javis là track remote. onReady chỉ báo
   sau khi bắt tay xong, vì chữ gửi trước lúc đó (câu gọi Javis) không có phiên nào nhận.
   Ghi chú: KHÔNG dùng ký tự em dash. */
(function () {
  "use strict";

  var IN_RATE = 16000, OUT_RATE = 24000;
  var ws = null, inCtx = null, outCtx = null, proc = null, src = null, stream = null;
  var nextAt = 0, playing = [], on = false, opts = {};
  var wasSpeaking = false, speakTimer = null;
  var generation = 0, starting = null, cancelOpen = null;
  var utterStartAt = 0, lastCtx = "";   // mốc bắt đầu phát câu hiện tại; ngữ cảnh đã gửi lần cuối
  var utterAudio = [], nextUtterance = true;
  // ---- WebRTC (ChatGPT Live) ----
  var pc = null, rtc = false, remoteAudio = null, remoteSrc = null, rtcTimer = null;
  var rtcSpeaking = false, rtcLoudAt = 0, answerWaiter = null, muted = false;
  // Nối sớm (0.65.24, opts.deferMic): bắt tay xong mà CHƯA giữ mic, vì lúc đó bộ nghe của trình duyệt
  // còn đang nghe nốt câu đánh thức và điện thoại chỉ cho một bên giữ mic. attachMic() gắn sau.
  var rtcSender = null, pcmSocket = null;
  var RTC_LOUD = 0.01, RTC_HANGOVER_MS = 400;

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
    if (nextUtterance) { utterStartAt = t; utterAudio = []; nextUtterance = false; }
    utterAudio.push({ at: t, duration: ab.duration });
    node.start(t);
    nextAt = t + ab.duration;
    schedMs += ab.duration * 1000;
    playing.push(node);
    node.onended = function () { var k = playing.indexOf(node); if (k >= 0) playing.splice(k, 1); tickSpeaking(); };
    tickSpeaking();
  }

  // V3: tiến độ phát kể từ lần resetProgress (app.js gọi khi vẽ xong một bong bóng): tổng ms đã
  // xếp lịch và số ms đã thật sự ra loa. Bong bóng hiện chữ theo tỉ lệ này, vì bản ghi chữ của
  // nhà cung cấp về trước tiếng nhiều.
  var schedMs = 0;
  function progress() {
    // WebRTC: chữ của model về gần như cùng lúc với tiếng, hiện hết phần đã về.
    if (rtc) return { played: 1, total: 1 };
    var remaining = (outCtx && playing.length) ? Math.max(0, (nextAt - outCtx.currentTime) * 1000) : 0;
    return { played: Math.max(0, Math.round(schedMs - remaining)), total: Math.round(schedMs) };
  }
  function resetProgress() { schedMs = 0; }

  // Số ms của câu hiện tại đã thật sự phát ra loa (0 nếu chưa phát gì).
  function playedMs() {
    if (!outCtx || !utterStartAt) return 0;
    // Count only scheduled audio, excluding buffering gaps and time after playback ends.
    var seconds = utterAudio.reduce(function (sum, chunk) {
      return sum + Math.max(0, Math.min(chunk.duration, outCtx.currentTime - chunk.at));
    }, 0);
    return Math.round(seconds * 1000);
  }

  function flushPlayback() {
    playing.forEach(function (n) { try { n.stop(); } catch (e) {} });
    playing = [];
    nextAt = 0;
    utterStartAt = 0;
    schedMs = 0;
    utterAudio = []; nextUtterance = true;
    tickSpeaking();
  }

  function sendJson(obj) {
    if (ws && ws.readyState === WebSocket.OPEN) { try { ws.send(JSON.stringify(obj)); } catch (e) {} }
  }

  // WebRTC: "Javis đang nói" đo bằng mức âm track remote (không có hàng đợi phát nào để đếm).
  function setRtcSpeaking(now) {
    if (now === rtcSpeaking) return;
    rtcSpeaking = now;
    emit(now ? "onSpeakStart" : "onSpeakEnd");
  }

  function attachRemote(remote, id) {
    if (id !== generation) return;
    try {
      remoteAudio = new Audio();
      remoteAudio.autoplay = true;
      remoteAudio.srcObject = remote;
      var p = remoteAudio.play();
      // iOS có thể chặn phát vì không còn trong cử chỉ bấm: phát qua outCtx đã mở khoá lúc bấm mic.
      if (p && p.catch) p.catch(function () { try { if (remoteSrc && outCtx) remoteSrc.connect(outCtx.destination); } catch (e) {} });
    } catch (e) {}
    try {
      remoteSrc = outCtx.createMediaStreamSource(remote);
      var an = outCtx.createAnalyser();
      an.fftSize = 512;
      remoteSrc.connect(an);
      var buf = new Float32Array(an.fftSize);
      clearInterval(rtcTimer);
      rtcTimer = setInterval(function () {
        if (id !== generation) return;
        an.getFloatTimeDomainData(buf);
        var sum = 0;
        for (var i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
        var rms = Math.sqrt(sum / buf.length), t = Date.now();
        if (rms > RTC_LOUD) { rtcLoudAt = t; setRtcSpeaking(true); }
        else if (rtcSpeaking && t - rtcLoudAt > RTC_HANGOVER_MS) setRtcSpeaking(false);
      }, 50);
    } catch (e) {}
  }

  function waitIce(conn, ms) {
    return new Promise(function (res) {
      if (conn.iceGatheringState === "complete") return res();
      var timer = setTimeout(res, ms);
      conn.onicegatheringstatechange = function () {
        if (conn.iceGatheringState === "complete") { clearTimeout(timer); res(); }
      };
    });
  }

  async function startWebRTC(id) {
    try {
      pc = new RTCPeerConnection();
      var conn = pc;
      var tr = conn.addTransceiver("audio", { direction: "sendrecv" });
      rtcSender = tr.sender;
      if (stream) await tr.sender.replaceTrack(stream.getAudioTracks()[0]);
      conn.createDataChannel("oai-events");
      conn.ontrack = function (e) { attachRemote(e.streams && e.streams[0] ? e.streams[0] : new MediaStream([e.track]), id); };
      conn.onconnectionstatechange = function () {
        if (id !== generation || pc !== conn) return;
        if (conn.connectionState === "failed") { stop(); emit("onError", "webrtc"); emit("onClosed"); }
      };
      var offer = await conn.createOffer();
      await conn.setLocalDescription(offer);
      await waitIce(conn, 3000);
      if (id !== generation) return false;
      var answer = await new Promise(function (res) {
        var timer = setTimeout(function () { answerWaiter = null; res(null); }, 35000);
        answerWaiter = function (sdp) { clearTimeout(timer); answerWaiter = null; res(sdp); };
        sendJson({ type: "webrtc_offer", sdp: conn.localDescription.sdp });
      });
      if (id !== generation) return false;
      if (!answer) return false;
      await conn.setRemoteDescription({ type: "answer", sdp: answer });
      return true;
    } catch (e) {
      return false;
    }
  }

  // Báo trạng thái "Javis đang nói" theo hàng đợi phát thật (không có sự kiện nào khác đáng tin).
  function tickSpeaking() {
    clearTimeout(speakTimer);
    var now = !!playing.length;
    if (now !== wasSpeaking) { wasSpeaking = now; emit(now ? "onSpeakStart" : "onSpeakEnd"); }
    if (now) speakTimer = setTimeout(tickSpeaking, 250);
  }

  function start(o) {
    if (on) return Promise.resolve(true);
    if (starting) return starting;
    opts = o || {};
    var id = ++generation;
    var task = startSession(id);
    starting = task;
    task.then(function () { if (starting === task) starting = null; });
    return task;
  }

  async function startSession(id) {
    // Mở context ngay trong thao tác bấm mic, trước await xin quyền microphone.
    var AC = window.AudioContext || window.webkitAudioContext;
    try {
      try { inCtx = new AC({ sampleRate: IN_RATE }); } catch (e) { inCtx = new AC(); }
      outCtx = new AC({ sampleRate: OUT_RATE });
    } catch (e) { stop(); emit("onError", "audio"); return false; }
    inCtx.resume().catch(function () {});
    outCtx.resume().catch(function () {});
    if (!opts.deferMic) {
      try {
        var acquired = await getMic();
        if (id !== generation) { acquired.getTracks().forEach(function (t) { t.stop(); }); return false; }
        stream = acquired;
      } catch (e) {
        if (id === generation) { stop(); emit("onError", "mic:" + (e && e.name || "error")); }
        return false;
      }
    }
    // Nối lại tự động (khi người dùng nói) không nằm trong cú bấm nào; trên iPhone resume() lúc đó có
    // thể treo mãi. Chờ tối đa 1 giây: WebRTC phát tiếng qua thẻ audio, không cần outCtx mới có tiếng.
    try {
      await Promise.race([Promise.all([inCtx.resume(), outCtx.resume()]),
                          new Promise(function (r) { setTimeout(r, 1000); })]);
    } catch (e) {}
    if (id !== generation) return false;
    var sid = "", brain = "brain", language = "vi-VN";
    try { sid = (opts.sessionId && opts.sessionId()) || ""; brain = (opts.brain && opts.brain()) || "brain"; } catch (e) {}
    try { language = (typeof opts.language === "function" ? opts.language() : opts.language) || "vi-VN"; } catch (e) {}
    var proto = location.protocol === "https:" ? "wss://" : "ws://";
    try {
      ws = new WebSocket(proto + location.host + "/ws/voice-live?session_id=" + encodeURIComponent(sid) + "&brain=" + encodeURIComponent(brain) + "&lang=" + encodeURIComponent(language));
    } catch (e) { stop(); emit("onError", "ws"); return false; }
    var socket = ws;
    ws.binaryType = "arraybuffer";
    var readyData = null, readyWaiter = null, rtcErrorShown = false;
    ws.onmessage = function (e) {
      if (id !== generation || ws !== socket) return;
      if (e.data instanceof ArrayBuffer) { playChunk(e.data); return; }
      var d; try { d = JSON.parse(e.data); } catch (err) { return; }
      if (d.type === "ready") {
        // Khung ready đầu tiên quyết định đường âm thanh; WebRTC báo onReady sau khi bắt tay xong.
        if (!readyData) { readyData = d; if (readyWaiter) readyWaiter(d); }
        if (d.transport !== "webrtc" || on) emit("onReady", d);
      }
      else if (d.type === "webrtc_answer") { if (answerWaiter) answerWaiter(String(d.sdp || "")); }
      else if (d.type === "tool_result") emit("onToolResult", d.name || "", d.text || "");
      else if (d.type === "interrupted") {
        var ms = playedMs();          // đo TRƯỚC khi xả, xả xong là mất mốc
        flushPlayback();
        sendJson({ type: "played", ms: ms });
        emit("onInterrupted", ms);
      }
      else if (d.type === "transcript") emit("onTranscript", d.role, d.text || "", !!d.final);
      else if (d.type === "tool") emit("onTool", d.name, d.status);
      else if (d.type === "turn_done") { nextUtterance = true; emit("onTurnDone"); }
      else if (d.type === "reconnected") emit("onReconnected");
      else if (d.type === "error") {
        // Lỗi trong lúc chờ answer (Codex cũ, gói không cho realtime...): báo một lần, dừng chờ.
        if (answerWaiter) { rtcErrorShown = true; answerWaiter(null); }
        emit("onError", d.message || "error");
      }
    };
    ws.onclose = function () {
      if (id !== generation || ws !== socket) return;
      stop(); emit("onClosed");
    };
    ws.onerror = function () {
      if (id !== generation || ws !== socket) return;
      stop(); emit("onError", "ws"); emit("onClosed");
    };
    var opened = await new Promise(function (res) {
      var timer;
      function finish(ok) { clearTimeout(timer); cancelOpen = null; res(ok); }
      cancelOpen = function () { finish(false); };
      socket.onopen = function () { if (id === generation && ws === socket) finish(true); };
      timer = setTimeout(function () { finish(false); }, 4000);
    });
    if (id !== generation) return false;
    if (!opened || socket.readyState !== WebSocket.OPEN) {
      stop(); emit("onError", "ws"); emit("onClosed"); return false;
    }
    // Chờ ready: máy chủ dựng nhà cung cấp (lần đầu ChatGPT Live phải khởi động Codex app-server).
    var ready = readyData || await new Promise(function (res) {
      var timer = setTimeout(function () { readyWaiter = null; res(null); }, 25000);
      readyWaiter = function (d) { clearTimeout(timer); readyWaiter = null; res(d); };
    });
    if (id !== generation) return false;
    if (!ready) { stop(); emit("onError", "ws"); emit("onClosed"); return false; }
    if (ready.transport === "webrtc") {
      rtc = true;
      var ok = await startWebRTC(id);
      if (id !== generation) return false;
      if (!ok) { stop(); if (!rtcErrorShown) emit("onError", "webrtc"); emit("onClosed"); return false; }
      on = true;
      emit("onStarted");
      emit("onReady", ready);
      return true;
    }
    pcmSocket = socket;
    if (stream && !wirePcm(id)) { stop(); emit("onError", "audio"); return false; }
    on = true;
    emit("onStarted");
    return true;
  }

  function getMic() {
    return navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 } });
  }

  // Đường PCM (Live qua API): tiếng mic đi qua WebSocket của máy chủ.
  function wirePcm(id) {
    var socket = pcmSocket;
    try {
      src = inCtx.createMediaStreamSource(stream);
      proc = inCtx.createScriptProcessor(4096, 1, 1);
      proc.onaudioprocess = function (ev) {
        if (id !== generation || ws !== socket || socket.readyState !== WebSocket.OPEN) return;
        var f32 = downsample(ev.inputBuffer.getChannelData(0), inCtx.sampleRate, IN_RATE);
        try { ws.send(floatToPcm16(f32).buffer); } catch (e) { socket.onerror(e); }
      };
      src.connect(proc);
      proc.connect(inCtx.destination);   // Chrome chỉ chạy onaudioprocess khi node nối tới đích
      return true;
    } catch (e) { return false; }
  }

  // Gắn mic vào phiên đã nối sớm (opts.deferMic). Gọi khi bộ nghe của trình duyệt đã nhả mic.
  async function attachMic() {
    if (stream) return true;
    var id = generation;
    try {
      var acquired = await getMic();
      if (id !== generation) { acquired.getTracks().forEach(function (t) { t.stop(); }); return false; }
      stream = acquired;
      if (muted) stream.getAudioTracks().forEach(function (t) { t.enabled = false; });
      if (rtc) {
        if (!rtcSender) return false;
        await rtcSender.replaceTrack(stream.getAudioTracks()[0]);
      } else if (!wirePcm(id)) {
        stop(); emit("onError", "audio"); return false;
      }
      return true;
    } catch (e) {
      if (id === generation) { stop(); emit("onError", "mic:" + (e && e.name || "error")); emit("onClosed"); }
      return false;
    }
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

  // Tắt mic giữa cuộc gọi: track vẫn sống (bật lại tức thì), chỉ không gửi tiếng. Dùng cho cả hai đường.
  function setMuted(value) {
    muted = !!value;
    try { if (stream) stream.getAudioTracks().forEach(function (t) { t.enabled = !muted; }); } catch (e) {}
    return muted;
  }

  function stopRtc() {
    if (answerWaiter) answerWaiter(null);
    clearInterval(rtcTimer); rtcTimer = null;
    try { if (pc) { pc.ontrack = pc.onconnectionstatechange = null; pc.close(); } } catch (e) {}
    pc = null; rtcSender = null;
    try { if (remoteAudio) { remoteAudio.pause(); remoteAudio.srcObject = null; } } catch (e) {}
    remoteAudio = null;
    try { if (remoteSrc) remoteSrc.disconnect(); } catch (e) {}
    remoteSrc = null;
    if (rtcSpeaking) setRtcSpeaking(false);
    rtc = false;
  }

  function stop() {
    generation++;
    starting = null;
    if (cancelOpen) cancelOpen();
    on = false;
    stopRtc();
    muted = false;
    flushPlayback();
    try { if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "stop" })); } catch (e) {}
    try {
      if (ws) { ws.onopen = ws.onmessage = ws.onclose = ws.onerror = null; ws.close(); }
    } catch (e) {}
    ws = null;
    lastCtx = ""; utterStartAt = 0;
    try { if (proc) { proc.disconnect(); proc.onaudioprocess = null; } if (src) src.disconnect(); } catch (e) {}
    proc = null; src = null; pcmSocket = null;
    try { if (stream) stream.getTracks().forEach(function (t) { t.stop(); }); } catch (e) {}
    stream = null;
    try { if (inCtx) inCtx.close().catch(function () {}); } catch (e) {}
    try { if (outCtx) outCtx.close().catch(function () {}); } catch (e) {}
    inCtx = null; outCtx = null;
    emit("onStopped");
  }

  window.JavisVoiceLive = { start: start, stop: stop, sendText: sendText, sendContext: sendContext, attachMic: attachMic,
                            hasMic: function () { return !!stream; },
                            playedMs: playedMs, progress: progress, resetProgress: resetProgress,
                            setMuted: setMuted, isMuted: function () { return muted; },
                            isOn: function () { return on; },
                            transport: function () { return rtc ? "webrtc" : "pcm"; },
                            isSpeaking: function () { return rtc ? rtcSpeaking : !!playing.length; } };
})();
