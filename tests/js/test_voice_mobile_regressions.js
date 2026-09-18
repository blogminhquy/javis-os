const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
let rejectPlay = true, plays = 0;
const context = {
  window: { SpeechRecognition: class {}, speechSynthesis: { getVoices: () => [] } },
  navigator: { userAgent: 'iPhone' }, localStorage: { getItem: () => null },
  setTimeout, clearTimeout,
  Audio: class {
    setAttribute() {}
    play() { plays++; return rejectPlay ? Promise.reject(new Error('blocked')) : Promise.resolve(); }
  }
};
vm.runInNewContext(fs.readFileSync('dashboard/voice.js', 'utf8'), context);
const Voice = context.window.JavisVoice;
const v = new Voice();
v.isSpeaking = () => false;
let shown;
v.onInterim = t => { shown = t; };
const result = (text, final = true) => Object.assign([{ transcript: text }], { isFinal: final });
v.recognition.onresult({ results: [result('em kiểm tra'), result('em kiểm tra lại'), result('em kiểm tra lại bản tin giá vàng', false)] });
assert.equal(shown, 'em kiểm tra lại bản tin giá vàng');
clearTimeout(v._silenceTimer);
v.recognition.onresult({ results: [result('Em kiểm tra lại bản tin giá vàng.')] });
assert.equal(shown, 'Em kiểm tra lại bản tin giá vàng.');
clearTimeout(v._silenceTimer);
assert.equal(Voice.ghepManh('không', 'không không'), 'không không');
assert.equal(Voice.ghepManh('xem giá vàng', 'và giá bạc'), 'xem giá vàng và giá bạc');
assert.equal(Voice.ghepManh('Em kiểm tra.', 'em kiểm tra lại'), 'em kiểm tra lại');
v._iosCache = false;
v.recognition.start = () => {};
v.recognition.onend();
assert.equal(v._committed, 'Em kiểm tra lại bản tin giá vàng.');
v._iosCache = true;
v.isPlaying = true; v._countThis = true; v._wordsDone = 4;
v.ttsChunks = ['một hai ba bốn']; v._chunkIndex = 0;
v.currentAudio = { currentTime: 0.1, duration: Infinity };
assert.equal(v.visibleWords(), 8);
v.currentAudio.currentTime = 0;
assert.equal(v.visibleWords(), 4);
(async () => {
  v._moKhoaAudioIOS();
  const audio = v._iosAudio;
  const wav = Buffer.from(audio.src.split(',')[1], 'base64');
  assert.equal(wav.length, 204);
  assert.equal(wav.readUInt32LE(40), wav.length - 44);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(v._iosUnlocked, false);
  rejectPlay = false;
  v._moKhoaAudioIOS();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(v._iosAudio, audio);
  assert.equal(v._iosUnlocked, true);
  v._moKhoaAudioIOS();
  assert.equal(plays, 2);
  console.log('ok mobile transcript, streaming text, iOS audio unlock regressions');
})().catch(e => { console.error(e); process.exitCode = 1; });
