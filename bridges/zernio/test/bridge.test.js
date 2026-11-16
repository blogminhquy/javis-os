import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { Bridge, JsonState } from '../src/bridge.js';
import { createRuntimeClient, createWebhookServer } from '../src/server.js';

const accountId = 'test-account', secret = 'test-secret';
const rawFor = (body) => Buffer.from(JSON.stringify(body));
const sign = (raw) => crypto.createHmac('sha256', secret).update(raw).digest('hex');
function setup({ runtime = { deliver: async () => ({}) }, now = Date.parse('2026-11-14T16:00:00Z') } = {}) {
  const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'zernio-')), 'state.json');
  const bridge = new Bridge({ secret, accountId, username: 'test-shop', state: new JsonState(file), runtime, now: () => now, batchMs: 1 });
  return { bridge, file, now };
}
function event(overrides = {}) { return { id: 'evt-1', event: 'message.received', timestamp: '2026-11-14T16:00:00Z', account: { id: accountId, accountId, platform: 'instagram', username: 'test-shop' }, conversation: { id: 'conv-1' }, message: { id: 'msg-1', conversationId: 'conv-1', platform: 'instagram', platformMessageId: 'native-1', direction: 'incoming', text: 'xin chào', attachments: [], sender: { id: 'customer-1' }, sentAt: '2026-11-14T16:00:00Z', isRead: false }, ...overrides }; }
function receive(bridge, body) { const raw = rawFor(body); return bridge.receive(raw, { 'x-zernio-signature': sign(raw), 'x-zernio-event': body.event, 'x-zernio-event-id': body.id }); }

test('rejects absent or incorrect HMAC without recording state', () => { const { bridge, file } = setup(); const raw = rawFor(event()); assert.equal(bridge.receive(raw, {}).status, 401); assert.equal(bridge.receive(raw, { 'x-zernio-signature': '0'.repeat(64) }).status, 401); assert.equal(fs.existsSync(file), false); });
test('accepts webhook.test but never calls runtime', async () => { let calls = 0; const { bridge } = setup({ runtime: { deliver: async () => { calls++; } } }); const e = { id: 'test-1', event: 'webhook.test', timestamp: '2026-11-14T16:00:00Z', test: true }; assert.equal(receive(bridge, e).code, 'test'); await new Promise(r => setTimeout(r, 5)); assert.equal(calls, 0); });
test('dedupes durable event IDs and rejects stale replays', () => { const { bridge, now } = setup(); assert.equal(receive(bridge, event()).code, 'queued'); assert.equal(receive(bridge, event()).code, 'duplicate'); assert.equal(receive(bridge, event({ id: 'old', timestamp: new Date(now - 53 * 3600e3).toISOString(), message: { ...event().message, sentAt: new Date(now - 53 * 3600e3).toISOString() } })).code, 'replay_or_historical'); });
test('event deduplication survives a bridge restart', () => { const { bridge, file } = setup(); assert.equal(receive(bridge, event()).code, 'queued'); const restarted = new Bridge({ secret, accountId, username: 'test-shop', state: new JsonState(file), runtime: { deliver: async () => ({}) }, now: () => Date.parse('2026-11-14T16:00:00Z'), batchMs: 1 }); assert.equal(receive(restarted, event()).code, 'duplicate'); });
test('dedupes a customer message when Zernio retries it in a new event envelope after restart', () => {
  const { bridge, file } = setup();
  assert.equal(receive(bridge, event()).code, 'queued');
  const restarted = new Bridge({ secret, accountId, username: 'test-shop', state: new JsonState(file), runtime: { deliver: async () => ({}) }, now: () => Date.parse('2026-11-14T16:00:00Z'), batchMs: 1 });
  assert.equal(receive(restarted, event({ id: 'evt-retry' })).code, 'duplicate_message');
});
test('filters a wrong account, echo, bot sender and standby takeover', () => { const { bridge } = setup(); assert.equal(receive(bridge, event({ account: { ...event().account, accountId: 'wrong', id: 'wrong' } })).code, 'ignored_message'); assert.equal(receive(bridge, event({ id: 'echo', message: { ...event().message, direction: 'outgoing' } })).code, 'ignored_message'); assert.equal(receive(bridge, event({ id: 'self', message: { ...event().message, sender: { id: accountId } } })).code, 'ignored_message'); assert.equal(receive(bridge, event({ id: 'standby', metadata: { standby: true } })).code, 'ignored_message'); });
test('filters explicitly historical messages', () => { const { bridge } = setup(); assert.equal(receive(bridge, event({ metadata: { historical: true } })).code, 'ignored_message'); });
test('delivers to inbox despite legacy cap and takeover without a second debounce', async () => {
  const batches = [];
  const { bridge, file } = setup({ runtime: { deliver: async batch => { batches.push(batch); return {ok:true,status:'queued',takeover:true,replySent:false,sammyReplySent:false}; } } });
  receive(bridge, event());
  clearTimeout(bridge.timers.get('conv-1'));
  const state = new JsonState(file).load();
  state.conversations['conv-1'].repliesInWindow = 5;
  state.conversations['conv-1'].takeover = true;
  new JsonState(file).save(state);
  await bridge.flush('conv-1');
  assert.equal(batches.length, 1);
  assert.equal(batches[0].policy, undefined);
  assert.equal(new JsonState(file).load().conversations['conv-1'].processing, undefined);
});
test('runtime timeout/error preserves batch for retry', async () => { const { bridge, file } = setup({ runtime: { deliver: async () => { throw new Error('timeout'); } } }); receive(bridge, event()); await new Promise(r => setTimeout(r, 10)); const saved = new JsonState(file).load(); assert.equal(saved.conversations['conv-1'].processing.length, 1); });
test('runtime client rejects API errors, malformed results and timeouts without exposing its token', async () => {
  const body = { conversationId: 'conv-1' };
  await assert.rejects(createRuntimeClient({ baseUrl: 'https://runtime.example', token: 'private-token', fetchImpl: async () => ({ ok: false }) }).deliver(body), /runtime rejected/);
  await assert.rejects(createRuntimeClient({ baseUrl: 'https://runtime.example', token: 'private-token', fetchImpl: async () => ({ ok: true, json: async () => ({}) }) }).deliver(body), /invalid result/);
  const slowFetch = (_, { signal }) => new Promise((_, reject) => signal.addEventListener('abort', () => reject(new Error('aborted'))));
  await assert.rejects(createRuntimeClient({ baseUrl: 'https://runtime.example', token: 'private-token', fetchImpl: slowFetch, timeoutMs: 1 }).deliver(body), /aborted/);
});
test('HTTP endpoint enforces HTTPS, raw HMAC and body size', async (t) => {
  const { bridge } = setup(); const server = createWebhookServer({ bridge, requireHttps: true, maxBodyBytes: 100 });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve)); t.after(() => server.close());
  const port = server.address().port; const call = (headers, body = '') => new Promise((resolve, reject) => {
    const request = http.request({ host: '127.0.0.1', port, path: '/webhooks/zernio', method: 'POST', headers }, response => { response.resume(); response.on('end', () => resolve(response.statusCode)); });
    request.on('error', reject); request.end(body);
  });
  const raw = rawFor({ id: 'test-http', event: 'webhook.test', timestamp: '2026-11-14T16:00:00Z', test: true });
  assert.equal(await call({ 'x-zernio-signature': sign(raw) }, raw), 400);
  assert.equal(await call({ 'x-forwarded-proto': 'https', 'x-zernio-signature': '0'.repeat(64) }, raw), 401);
  assert.equal(await call({ 'x-forwarded-proto': 'https', 'x-zernio-signature': sign(raw), 'content-length': 101 }, Buffer.alloc(101)), 413);
  assert.equal(await call({ 'x-forwarded-proto': 'https, http', 'x-zernio-signature': sign(raw) }, raw), 200);
});

 test('requires an explicit username and rejects a mismatched account username', () => {
  const state = { load: () => ({ events: {}, messages: {}, conversations: {} }) };
  assert.throws(() => new Bridge({ secret, accountId, state, runtime: {} }), /configuration is incomplete/);
  const { bridge } = setup();
  assert.equal(receive(bridge, event({ account: { ...event().account, username: 'another-shop' } })).code, 'ignored_message');
});

test('restart retries an unacknowledged batch and concurrent arrival is preserved', async () => {
  let release;
  const { bridge, file } = setup({runtime:{deliver: () => new Promise(resolve => {release = resolve;})}});
  receive(bridge, event());
  clearTimeout(bridge.timers.get('conv-1'));
  const pending = bridge.flush('conv-1');
  receive(bridge, event({id:'e2', message:{...event().message,id:'m2',platformMessageId:'p2'}}));
  clearTimeout(bridge.timers.get('conv-1'));
  await bridge.flush('conv-1');
  assert.equal(new JsonState(file).load().conversations['conv-1'].processing.length, 1);
  const received = [];
  const restarted = new Bridge({secret,accountId,username:'test-shop',state:new JsonState(file),runtime:{deliver:async body=>received.push(body)},batchMs:0});
  restarted.resume();
  clearTimeout(restarted.timers.get('conv-1'));
  await restarted.flush('conv-1');
  clearTimeout(restarted.timers.get('conv-1'));
  await restarted.flush('conv-1');
  assert.deepEqual(received.map(x=>x.messages[0].id), ['msg-1','m2']);
  release({}); await pending;
});
test('runtime ACK is queue acceptance, never proof of a sent reply', async () => {
  for (const result of [{ok:false,takeover:false,sammyReplySent:false}, {ok:true,status:'queued',takeover:false,replySent:true,sammyReplySent:true}]) {
    const client = createRuntimeClient({baseUrl:'http://local',token:'private',fetchImpl:async()=>({ok:true,json:async()=>result})});
    await assert.rejects(client.deliver({}), /invalid result/);
  }
  const ack = {ok:true,status:'queued',takeover:false,replySent:false,sammyReplySent:false};
  assert.deepEqual(await createRuntimeClient({baseUrl:'http://local',token:'private',fetchImpl:async()=>({ok:true,json:async()=>ack})}).deliver({}),ack);
});


test('explicit echo flags never reach runtime even when direction says incoming', async () => {
  const batches = [];
  const { bridge, file } = setup({ runtime: { deliver: async batch => { batches.push(batch); } } });
  for (const flag of ['isEcho', 'is_echo']) {
    const body = event({ id: 'echo-' + flag, message: { ...event().message, id: 'echo-' + flag,
      platformMessageId: 'echo-' + flag, direction: 'incoming', [flag]: true } });
    assert.equal(receive(bridge, body).code, 'ignored_message');
  }
  await bridge.flush('conv-1');
  assert.deepEqual(batches, []);
  assert.deepEqual(new JsonState(file).load().conversations, {});
});
