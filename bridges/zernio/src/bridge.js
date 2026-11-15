import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

const emptyState = () => ({ events: {}, messages: {}, conversations: {} });

export class JsonState {
  constructor(file) { this.file = file; }
  load() {
    try {
      const state = JSON.parse(fs.readFileSync(this.file, 'utf8'));
      // Keep state files written by the first bridge version compatible while adding
      // message-level idempotency. A Zernio retry can have a new event ID for the
      // same Instagram message, so event-ID deduplication alone is insufficient.
      state.events ||= {}; state.messages ||= {}; state.conversations ||= {};
      return state;
    }
    catch (error) {
      if (error.code === 'ENOENT') return emptyState();
      throw error;
    }
  }
  save(value) {
    fs.mkdirSync(path.dirname(this.file), { recursive: true });
    const temp = `${this.file}.${process.pid}.tmp`;
    fs.writeFileSync(temp, JSON.stringify(value), { mode: 0o600 });
    fs.renameSync(temp, this.file);
  }
}

export function validSignature(raw, signature, secret) {
  if (!secret || !signature || !/^[a-f0-9]{64}$/i.test(signature)) return false;
  const expected = crypto.createHmac('sha256', secret).update(raw).digest();
  const received = Buffer.from(signature, 'hex');
  return received.length === expected.length && crypto.timingSafeEqual(received, expected);
}

export class Bridge {
  constructor({ secret, accountId, username, state, runtime, now = () => Date.now(), batchMs = 0, maxAgeMs = 52 * 60 * 60 * 1000 }) {
    if (!secret || !accountId || !username || !state || !runtime) throw new Error('bridge configuration is incomplete');
    this.secret = secret; this.accountId = accountId; this.username = username;
    this.stateStore = state; this.runtime = runtime; this.now = now;
    this.batchMs = batchMs; this.maxAgeMs = maxAgeMs; this.timers = new Map(); this.inflight = new Set();
  }
  receive(raw, headers) {
    if (!validSignature(raw, headers['x-zernio-signature'], this.secret)) return { status: 401, code: 'invalid_signature' };
    let event;
    try { event = JSON.parse(raw); } catch { return { status: 400, code: 'invalid_json' }; }
    if (headers['x-zernio-event'] && headers['x-zernio-event'] !== event.event) return { status: 400, code: 'event_mismatch' };
    if (headers['x-zernio-event-id'] && headers['x-zernio-event-id'] !== event.id) return { status: 400, code: 'event_id_mismatch' };
    if (!event.id || !event.event || !event.timestamp) return { status: 400, code: 'invalid_envelope' };
    const state = this.stateStore.load();
    if (state.events[event.id]) return { status: 200, code: 'duplicate' };
    const occurredAt = Date.parse(event.timestamp);
    if (!Number.isFinite(occurredAt) || occurredAt > this.now() + 5 * 60 * 1000 || this.now() - occurredAt > this.maxAgeMs) return { status: 202, code: 'replay_or_historical' };
    const markHandled = (code, status) => {
      state.events[event.id] = { receivedAt: new Date(this.now()).toISOString() };
      this.stateStore.save(state);
      return { status, code };
    };
    if (event.event === 'webhook.test' || event.test === true) return markHandled('test', 200);
    if (event.event !== 'message.received') return markHandled('ignored_event', 202);
    if (!this.isEligibleMessage(event, occurredAt)) return markHandled('ignored_message', 202);
    const conversationId = event.conversation?.id || event.message?.conversationId;
    if (!conversationId) return markHandled('invalid_message', 400);
    const messageKey = `${event.account.accountId || event.account.id}:${event.message.platformMessageId}`;
    if (state.messages[messageKey]) return markHandled('duplicate_message', 200);
    // Persist event and message identities in one atomic file replacement before
    // batching, so a crash cannot acknowledge only half of the dedupe state.
    state.events[event.id] = { receivedAt: new Date(this.now()).toISOString() };
    state.messages[messageKey] = { eventId: event.id, receivedAt: new Date(this.now()).toISOString() };
    const conversation = state.conversations[conversationId] ||= { messages: [] };
    conversation.messages.push({ id: event.message.id, platformMessageId: event.message.platformMessageId, text: event.message.text, attachments: event.message.attachments, sender: event.message.sender, sentAt: event.message.sentAt });
    conversation.account = { id: event.account.accountId || event.account.id, username: event.account.username, platform: event.account.platform };
    conversation.dueAt = this.now() + this.batchMs;
    state.conversations[conversationId] = conversation;
    this.stateStore.save(state);
    this.arm(conversationId, this.batchMs);
    return { status: 202, code: 'queued' };
  }
  isEligibleMessage(event, occurredAt) {
    const msg = event.message || {}, account = event.account || {};
    const accountId = account.accountId || account.id;
    if (accountId !== this.accountId || account.platform !== 'instagram' || account.username !== this.username) return false;
    if (msg.platform !== 'instagram' || msg.direction !== 'incoming' || event.metadata?.standby) return false;
    if (event.metadata?.historical || event.metadata?.isHistorical || event.historical || msg.historical || msg.isHistorical) return false;
    if (!msg.id || !msg.platformMessageId || !msg.sender?.id) return false;
    if (msg.sender.id === accountId || msg.sender.username === this.username) return false;
    const sentAt = Date.parse(msg.sentAt);
    return Number.isFinite(sentAt) && Math.abs(sentAt - occurredAt) <= this.maxAgeMs;
  }
  arm(conversationId, delay) {
    clearTimeout(this.timers.get(conversationId));
    const timer = setTimeout(() => this.flush(conversationId), delay);
    timer.unref();
    this.timers.set(conversationId, timer);
  }
  async flush(conversationId) {
    this.timers.delete(conversationId);
    // Runtime owns the five-second debounce, takeover and reply policy. Legacy
    // local cap/takeover values must never prevent delivery to its inbox.
    if (this.inflight.has(conversationId)) return;
    const state = this.stateStore.load();
    const conversation = state.conversations[conversationId];
    if (!conversation) return;
    if (!conversation.processing?.length) {
      if (!conversation.messages?.length) return;
      conversation.processing = conversation.messages.splice(0);
      this.stateStore.save(state);
    }
    const batch = conversation.processing;
    this.inflight.add(conversationId);
    try {
      await this.runtime.deliver({ conversationId, account: conversation.account, messages: batch });
      const updated = this.stateStore.load();
      const current = updated.conversations[conversationId];
      if (current) {
        delete current.processing;
        delete current.takeover;
        delete current.repliesInWindow;
        this.stateStore.save(updated);
        if (current.messages?.length) this.arm(conversationId, this.batchMs);
      }
    } catch {
      // Keep the in-flight batch durable until runtime acknowledges its inbox
      // commit. A restart retries the same message identities safely.
      this.arm(conversationId, Math.max(1000, this.batchMs));
    } finally {
      this.inflight.delete(conversationId);
    }
  }

  resume() {
    const state = this.stateStore.load();
    for (const [id, conversation] of Object.entries(state.conversations)) if (conversation.messages?.length || conversation.processing?.length) this.arm(id, Math.max(0, (conversation.dueAt || this.now()) - this.now()));
  }
}
