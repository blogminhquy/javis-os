const http = require('http');
const fs = require('fs');
const path = require('path');
const WebSocket = require('ws');

const PORT = 8000;
const ROOT = __dirname;
const gamePath = path.join(ROOT, 'child-game.html');

const players = new Map();
const stars = [];
const MAX_STARS = 8;

function createStar() {
  return {
    x: 60 + Math.random() * 780,
    y: -20 - Math.random() * 200,
    radius: 12 + Math.random() * 16,
    speed: 220 + Math.random() * 180,
    drift: (Math.random() - 0.5) * 180,
    pulse: Math.random() * Math.PI * 2,
    color: ['#ffd95a', '#ffa94d', '#ff7dc2', '#7ad7ff'][Math.floor(Math.random() * 4)]
  };
}

function resetStars() {
  stars.length = 0;
  for (let i = 0; i < MAX_STARS; i += 1) {
    stars.push(createStar());
  }
}

resetStars();

function broadcast(payload) {
  const message = JSON.stringify(payload);
  for (const socket of players.keys()) {
    if (socket.readyState === WebSocket.OPEN) {
      socket.send(message);
    }
  }
}

function sanitizeName(name) {
  const trimmed = String(name || '').trim().slice(0, 16);
  return trimmed || 'Player';
}

function updateGame() {
  for (let i = 0; i < stars.length; i += 1) {
    const star = stars[i];
    star.y += star.speed / 40;
    star.x += Math.sin(star.pulse) * (star.drift / 35);
    star.pulse += 0.12;

    if (star.y > 560) {
      stars[i] = createStar();
      continue;
    }

    for (const player of players.values()) {
      const catchX = Math.abs(star.x - player.x) < 52;
      const catchY = star.y + star.radius > 500 && star.y - star.radius < 540;
      if (catchX && catchY) {
        player.score += 1;
        stars[i] = createStar();
        break;
      }
    }
  }

  const payload = {
    type: 'state',
    players: Array.from(players.values()).map(({ id, name, x, score, color }) => ({ id, name, x, score, color })),
    stars
  };

  broadcast(payload);
}

const server = http.createServer((req, res) => {
  if (req.url === '/' || req.url === '/child-game.html') {
    const stream = fs.createReadStream(gamePath);
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    stream.pipe(res);
    return;
  }

  res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
  res.end('Not found');
});

const wss = new WebSocket.Server({ server });

wss.on('connection', (ws) => {
  const id = Math.random().toString(36).slice(2, 9);
  const player = {
    id,
    name: `Player ${players.size + 1}`,
    x: 180 + Math.random() * 540,
    score: 0,
    color: ['#7c6bff', '#ff7dc2', '#ff9d4d', '#49d59d'][Math.floor(Math.random() * 4)],
    ws
  };

  players.set(ws, player);
  ws.send(JSON.stringify({ type: 'welcome', id, name: player.name }));
  broadcast({ type: 'join', player: { id, name: player.name, x: player.x, score: player.score, color: player.color } });

  ws.on('message', (raw) => {
    try {
      const data = JSON.parse(raw.toString());

      if (data.type === 'join') {
        player.name = sanitizeName(data.name || player.name);
        ws.send(JSON.stringify({ type: 'welcome', id, name: player.name }));
        broadcast({ type: 'players', players: Array.from(players.values()).map(({ id, name, x, score, color }) => ({ id, name, x, score, color })) });
        return;
      }

      if (data.type === 'move') {
        player.x = Math.max(50, Math.min(850, Number(data.x) || player.x));
        broadcast({
          type: 'players',
          players: Array.from(players.values()).map(({ id, name, x, score, color }) => ({ id, name, x, score, color }))
        });
      }
    } catch (err) {
      // Ignore malformed messages.
    }
  });

  ws.on('close', () => {
    players.delete(ws);
    broadcast({ type: 'players', players: Array.from(players.values()).map(({ id, name, x, score, color }) => ({ id, name, x, score, color })) });
  });
});

server.listen(PORT, () => {
  console.log(`Server running at http://localhost:${PORT}`);
});

setInterval(updateGame, 1000 / 60);
