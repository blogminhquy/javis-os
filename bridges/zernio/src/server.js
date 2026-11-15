import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Bridge, JsonState } from './bridge.js';

const required = (name) => { if (!process.env[name]) throw new Error(`Missing ${name}`); return process.env[name]; };
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

export function createRuntimeClient({ baseUrl, token, fetchImpl = fetch, timeoutMs = 4000 }) {
  if (!baseUrl || !token) throw new Error('runtime configuration is incomplete');
  const endpoint = `${baseUrl.replace(/\/$/, '')}/zernio/inbound`;
  return {
    async deliver(body) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeoutMs);
      try {
        const response = await fetchImpl(endpoint, {
          method: 'POST', signal: controller.signal,
          headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
          body: JSON.stringify(body)
        });
        if (!response.ok) throw new Error('runtime rejected batch');
        const result = await response.json();
        if (!result || result.ok !== true || result.status !== 'queued' || result.replySent !== false || result.sammyReplySent !== false || typeof result.takeover !== 'boolean') throw new Error('runtime returned invalid result');
        return result;
      } finally { clearTimeout(timer); }
    }
  };
}

const forwardedHttps = (value) => typeof value === 'string' && value.split(',').some((item) => item.trim().toLowerCase() === 'https');

export function createWebhookServer({ bridge, requireHttps = false, maxBodyBytes = 256 * 1024 }) {
  if (!bridge) throw new Error('bridge is required');
  return http.createServer(async (request, response) => {
    if (request.method !== 'POST' || request.url !== '/webhooks/zernio') { response.writeHead(404).end(); return; }
    if (requireHttps && !forwardedHttps(request.headers['x-forwarded-proto'])) { response.writeHead(400).end('https required'); return; }
    const length = Number(request.headers['content-length']);
    if (Number.isFinite(length) && length > maxBodyBytes) { response.writeHead(413).end(); return; }
    const chunks = []; let received = 0;
    try {
      for await (const chunk of request) {
        received += chunk.length;
        if (received > maxBodyBytes) { response.writeHead(413).end(); request.destroy(); return; }
        chunks.push(chunk);
      }
      const headers = Object.fromEntries(Object.entries(request.headers).map(([key, value]) => [key.toLowerCase(), Array.isArray(value) ? value[0] : value]));
      const result = bridge.receive(Buffer.concat(chunks), headers);
      response.writeHead(result.status, { 'content-type': 'application/json', 'cache-control': 'no-store' }).end(JSON.stringify({ status: result.code }));
    } catch {
      if (!response.headersSent) response.writeHead(400).end();
    }
  });
}

export function start() {
  const runtime = createRuntimeClient({ baseUrl: required('SAMMY_RUNTIME_URL'), token: required('SAMMY_RUNTIME_TOKEN') });
  const bridge = new Bridge({ secret: required('ZERNIO_WEBHOOK_SECRET'), accountId: required('ZERNIO_INSTAGRAM_ACCOUNT_ID'), username: required('ZERNIO_INSTAGRAM_USERNAME'), state: new JsonState(process.env.STATE_FILE || path.join(root, 'data/state.json')), runtime });
  bridge.resume();
  // The Hostinger Caddy gateway uses the host network. In that topology the bridge
  // must bind only to loopback, while a regular private Docker network can use 0.0.0.0.
  return createWebhookServer({ bridge, requireHttps: process.env.REQUIRE_HTTPS === 'true' }).listen(Number(process.env.PORT || 3000), process.env.LISTEN_HOST || '0.0.0.0');
}

if (process.argv[1] === fileURLToPath(import.meta.url)) start();
