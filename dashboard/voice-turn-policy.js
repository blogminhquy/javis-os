/* Local, deterministic turn policy. Never rewrites the transcript. */
(function(root) {
  'use strict';
  const legacy = typeof module === 'object' && module.exports ? require('./voice-turn.js') : root.JavisVoiceTurn;
  function classify(text) {
    const s = legacy.normalize(text);
    if (/^(vâng )?anh hiểu rồi$|^(được rồi )?cảm ơn$|^vâng cảm ơn$/.test(s)) return 'normal';
    if (legacy.isStopPhrase(text)) return 'stop';
    if (legacy.isWaitPhrase(text) || /^(?:khoan|đợi chút) (?:để )?(?:anh|em|tôi|mình) nghĩ(?: đã| nhé)?$/.test(s)) return 'wait';
    if (/^(javis|jarvis)( ơi)?$/.test(s)) return 'wake';
    if (legacy.looksUnfinished(text) || /^(em|anh|ý là|có phải là|anh muốn em|để anh)$/.test(s) || /(?:muốn|nhờ|bảo) (?:anh|em|bạn)$/.test(s)) return 'unfinished';
    if (/^(?:javis(?: ơi)? )?(?:mở|đóng|chuyển|bật|tắt|tìm|đọc|xem|kiểm tra) .+/.test(s)) return 'command';
    return 'normal';
  }
  const bounds = {command:[900,800,1400], normal:[1200,1000,2200], unfinished:[2800,2200,4000], wake:[2200,2200,2200]};
  function target(group, samples, pace) {
    const [base,min,max] = bounds[group] || bounds.normal;
    const sorted = samples.slice(-20).sort((a,b)=>a-b);
    const learned = sorted.length >=5 ? sorted[Math.ceil(sorted.length*.75)-1]+250 : base;
    return Math.max(min,Math.min(max,Math.max(base,learned)+(pace==='fast'?-200:pace==='patient'?400:0)));
  }
  const api={classify,target,bounds};
  if(typeof module==='object'&&module.exports) module.exports=api; else root.JavisVoiceTurnPolicy=api;
})(typeof window!=='undefined'?window:globalThis);
