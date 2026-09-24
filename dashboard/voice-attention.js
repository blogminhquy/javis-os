/* Free browser attention gate. This does not identify speakers or remove audio noise. */
(function (root) {
  "use strict";
  const wake = /^(?:(?:hey|hi|hello|ê|này|alo|chào)\s+)?(?:javis|jarvis)(?=$|[\s,.!?:;])/iu;
  class Attention {
    constructor({ now = Date.now, idleMs = 20000, candidateMs = 120000 } = {}) {
      this.now = now; this.idleMs = idleMs; this.candidateMs = candidateMs;
      this.enabled = true; this.stop();
    }
    start() { this.running = true; this.until = this.now() + this.idleMs; this.candidateUntil = 0; }
    stop() { this.running = false; this.until = 0; this.candidateUntil = 0; }
    waiting() { return this.running && this.enabled && this.now() >= Math.max(this.until, this.candidateUntil); }
    keepActive() { if (this.running && !this.waiting()) this.until = this.now() + this.idleMs; }
    preview(text) {
      if (!String(text || '').trim()) { this.candidateUntil = 0; return false; }
      if (!this.running) return false;
      if (!this.waiting()) {
        // Latch the start, not every interim: a stuck recognizer cannot hold this forever.
        if (!this.candidateUntil) this.candidateUntil = this.now() + this.candidateMs;
        return true;
      }
      // A provisional wake must be present again in the FINAL before it opens the gate.
      return wake.test(String(text).trim());
    }
    accept(text) {
      const ok = this.running && !!String(text || '').trim() &&
        (!this.waiting() || wake.test(String(text).trim()));
      this.candidateUntil = 0;
      if (ok) this.until = this.now() + this.idleMs;
      return ok;
    }
  }
  const api = { Attention };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.JavisVoiceAttention = api;
})(typeof window !== 'undefined' ? window : globalThis);
