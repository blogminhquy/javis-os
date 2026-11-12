"""A leaked admin link stays out of search results and away from AI bots (bot_shield.py, 2026-11-09).

    python tests/run.py bot_shield      (no network)

Owner request: block indexing and block AI bots from reaching Javis OS when the admin link leaks out. Three layers:
X-Robots-Tag noindex on every answer, /robots.txt, and a 403 for requests that declare themselves a crawler, AI agent,
SEO tool or scanner. The traps this file guards:

  - a real browser, an in-app browser (Zalo, Facebook, Coc Coc, Naver) or a link preview caught as a bot;
  - a webhook, OAuth callback, MCP endpoint or plugin route (Javis Gate) answered 403 because the caller's UA matched;
  - robots.txt "fixed" to disallow Googlebot, which would leave a leaked link listed instead of removing it;
  - the middleware wired somewhere other than outermost, so the 401 of the login gate goes out without noindex.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import urllib.robotparser

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-botshield-")
os.environ["BRAINS_DIR"] = tempfile.mkdtemp(prefix="javis-botshield-brains-")
os.environ.pop("JAVIS_BLOCK_BOTS", None)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from starlette.applications import Starlette  # noqa: E402
from starlette.responses import PlainTextResponse, StreamingResponse  # noqa: E402
from starlette.routing import Route  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

import bot_shield as bs  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


# ---- 1. who counts as a bot ------------------------------------------------------------------
BOTS = {
    "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2; +https://openai.com/gptbot)": "ai",
    "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0; +https://openai.com/bot": "ai",
    "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ClaudeBot/1.0; +claudebot@anthropic.com)": "ai",
    "Claude-User (claude-code/2.1.0; +https://support.anthropic.com/)": "ai",
    "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)": "ai",
    "CCBot/2.0 (https://commoncrawl.org/faq/)": "ai",
    "Mozilla/5.0 (Linux; Android 5.0) AppleWebKit/537.36 (KHTML, like Gecko) Mobile Safari/537.36 (compatible; Bytespider; spider-feedback@bytedance.com)": "ai",
    "meta-externalagent/1.1 (+https://developers.facebook.com/docs/sharing/webmasters/crawler)": "ai",
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)": "search",
    "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm) Chrome/116.0 Safari/537.36": "search",
    "Mozilla/5.0 (compatible; coccocbot-web/1.0; +http://help.coccoc.com/searchengine)": "search",
    "Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)": "search",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15 (Applebot/0.1; +http://www.apple.com/go/applebot)": "search",
    "Mozilla/5.0 (compatible; AhrefsBot/7.0; +http://ahrefs.com/robot/)": "seo",
    "Mozilla/5.0 (compatible; SemrushBot/7~bl; +http://www.semrush.com/bot.html)": "seo",
    "Mozilla/5.0 (compatible; CensysInspect/1.1; +https://about.censys.io/)": "scanner",
    "Mozilla/5.0 zgrab/0.x": "scanner",
    "Expanse, a Palo Alto Networks company, searches across the global IPv4 space multiple times per day": "scanner",
}
for ua, kind in BOTS.items():
    check(f"{kind}: {ua[:60]}", bs.classify(ua) == kind, bs.classify(ua))

check("a request signed as a bot (Web Bot Auth, ChatGPT agent) is a bot even with a Chrome UA",
      bs.classify("Mozilla/5.0 Chrome/131.0 Safari/537.36", '"https://chatgpt.com"') == "signed-agent")

PEOPLE_AND_TOOLS = (
    # browsers, including in-app ones whose names sit close to a crawler's
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) coc_coc_browser/131.0 Chrome/125.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36 Zalo android/12100000",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 [FBAN/FBIOS;FBAV/470.0]",
    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36 NAVER(inapp; search; 2000; 12.6.6)",
    "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36 SogouMobileBrowser/5.40",
    "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 YaBrowser/24.10 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SAMSUNG SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/26.0 Chrome/122.0 Mobile Safari/537.36",
    # link previews: a share link pasted into a chat must still show its card
    "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
    "TelegramBot (like TwitterBot)",
    "Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)",
    "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)",
    "Twitterbot/1.0",
    "WhatsApp/2.23.20.0",
    "LinkedInBot/1.0 (compatible; Mozilla/5.0; Apache-HttpClient +http://www.linkedin.com)",
    "facebookexternalua",
    # the Javis CLI, scripts, MCP clients, uptime monitors
    "curl/8.5.0", "python-requests/2.32.3", "python-httpx/0.27.2", "claude-code/2.1.0", "openai-mcp/1.0.0",
    "Mozilla/5.0+(compatible; UptimeRobot/2.0; http://www.uptimerobot.com/)", "GitHub-Hookshot/abc123",
    "",
)
for ua in PEOPLE_AND_TOOLS:
    check(f"not a bot: {ua[:60] or '(no User-Agent)'}", bs.classify(ua) == "", bs.classify(ua))

# Every name in robots.txt must also be caught by the 403, or the file promises what the server does not do.
for token in bs.AI_AGENTS:
    check(f"robots.txt AI name {token} is also answered 403",
          bs.classify(f"Mozilla/5.0 (compatible; {token}/1.0)") == "ai")
for token in bs.SEARCH_ENGINES_ROBOTS:
    check(f"robots.txt search engine {token} is answered 403 + noindex",
          bs.classify(f"Mozilla/5.0 (compatible; {token}/1.0)") == "search")


# ---- 2. robots.txt --------------------------------------------------------------------------
rp = urllib.robotparser.RobotFileParser()
rp.parse(bs.robots_txt().splitlines())
for agent in ("GPTBot", "ClaudeBot", "CCBot", "PerplexityBot", "Google-Extended", "Applebot-Extended", "Bytespider"):
    check(f"robots.txt: {agent} may fetch nothing", not rp.can_fetch(agent, "/") and not rp.can_fetch(agent, "/s/x/"))
for agent in ("AhrefsBot", "SemrushBot", "SomeNewCrawler"):
    check(f"robots.txt: {agent} (falls under *) may fetch nothing", not rp.can_fetch(agent, "/"))
# CANARY. Google only drops a page it can fetch: blocked by robots.txt, a leaked link can stay listed bare.
for agent in ("Googlebot", "Bingbot", "coccocbot", "Applebot"):
    check(f"CANARY robots.txt: {agent} may fetch, to read the 403 + noindex", rp.can_fetch(agent, "/"))
check("robots.txt has no em or en dash", "\u2014" not in bs.robots_txt() and "\u2013" not in bs.robots_txt())


# ---- 3. which paths are never blocked --------------------------------------------------------
for path in ("/robots.txt", "/hooks/abc123", "/ext/javis.gate/mcp", "/.well-known/oauth-authorization-server",
             "/hub/mcp", "/chatbot-api/v1/turn", "/whatsapp/webhook", "/messenger/webhook", "/zalo-oa/webhook",
             "/threads/webhook", "/wechat/webhook", "/connect/oauth/callback", "/messenger/privacy", "/zalo_verifier123.html", "/health"):
    check(f"machine endpoint exempt: {path}", bs.exempt(path))
for path in ("/", "/s/abc/", "/static/app.js", "/auth/login", "/agents", "/hub/other", "/hooksx",
             "/zalo_verifier/../agents.html", "/health/loop", "/robots.txt.bak"):
    check(f"page still guarded: {path}", not bs.exempt(path))


# ---- 4. the middleware on a small app ---------------------------------------------------------
async def page(request):
    return PlainTextResponse("dashboard")


async def own_tag(request):
    return PlainTextResponse("public plugin page", headers={"X-Robots-Tag": "all"})


async def stream(request):
    async def gen():
        yield b"a"
        yield b"b"
    return StreamingResponse(gen(), media_type="text/plain")


inner = Starlette(routes=[Route("/", page), Route("/robots.txt", page), Route("/hooks/x", page, methods=["POST"]),
                          Route("/own", own_tag), Route("/stream", stream)])
app = bs.BotShield(inner)
client = TestClient(app)
BROWSER = {"user-agent": PEOPLE_AND_TOOLS[0]}
GPT = {"user-agent": "Mozilla/5.0 (compatible; GPTBot/1.2; +https://openai.com/gptbot)"}

r = client.get("/", headers=BROWSER)
check("a browser gets the page", r.status_code == 200 and r.text == "dashboard", r.status_code)
check("every answer carries X-Robots-Tag noindex", "noindex" in r.headers.get("x-robots-tag", ""), r.headers)
r = client.get("/", headers=GPT)
check("CANARY: GPTBot gets 403", r.status_code == 403, r.status_code)
check("the 403 itself says noindex", "noindex" in r.headers.get("x-robots-tag", ""))
check("the 403 shows none of the page", "dashboard" not in r.text)
r = client.get("/", headers={"user-agent": "Mozilla/5.0 (compatible; Googlebot/2.1)"})
check("Googlebot gets 403 (drops the page from the index)", r.status_code == 403, r.status_code)
r = client.get("/", headers={**BROWSER, "signature-agent": '"https://chatgpt.com"'})
check("a signed agent with a Chrome UA gets 403", r.status_code == 403, r.status_code)
r = client.get("/robots.txt", headers=GPT)
check("GPTBot can still read robots.txt", r.status_code == 200, r.status_code)
r = client.post("/hooks/x", headers=GPT)
check("a webhook is never answered 403 for its User-Agent", r.status_code == 200, r.status_code)
r = client.get("/own", headers=BROWSER)
check("a route that set its own X-Robots-Tag keeps it", r.headers.get("x-robots-tag") == "all", r.headers)
r = client.get("/stream", headers=BROWSER)
check("a streamed answer passes whole, with the header", r.text == "ab" and "noindex" in r.headers.get("x-robots-tag", ""))

os.environ["JAVIS_BLOCK_BOTS"] = "0"
r = client.get("/", headers=GPT)
check("JAVIS_BLOCK_BOTS=0 lets declared bots through", r.status_code == 200, r.status_code)
check("... and still sends noindex", "noindex" in r.headers.get("x-robots-tag", ""))
os.environ.pop("JAVIS_BLOCK_BOTS")


def call(client_addr, headers):
    """Drive the middleware with a hand-made scope, to set the client address."""
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "http",
             "path": "/", "raw_path": b"/", "query_string": b"", "root_path": "", "server": ("127.0.0.1", 7777),
             "client": client_addr,
             "headers": [(k.encode("latin-1"), v.encode("latin-1")) for k, v in headers.items()]}
    asyncio.run(app(scope, receive, send))
    return next(m["status"] for m in sent if m["type"] == "http.response.start")


check("a tool on this machine is never blocked (Javis's own engines)", call(("127.0.0.1", 5000), GPT) == 200)
check("CANARY: a tunnel or proxy on this machine does not count as local",
      call(("127.0.0.1", 5000), {**GPT, "x-forwarded-for": "203.0.113.9"}) == 403)
check("... nor does Cloudflare Tunnel", call(("127.0.0.1", 5000), {**GPT, "cf-connecting-ip": "203.0.113.9"}) == 403)


# ---- 5. main wires it outermost, robots.txt public, dashboard tagged ----------------------------
os.environ["JAVIS_REQUIRE_LOGIN"] = "1"
import main  # noqa: E402

check("main wires BotShield as the OUTERMOST middleware",
      bool(main.app.user_middleware) and main.app.user_middleware[0].cls is bs.BotShield,
      [getattr(m.cls, "__name__", m.cls) for m in main.app.user_middleware[:3]])
check("/robots.txt is an exact public path", "/robots.txt" in main._AUTH_PUBLIC_EXACT)
check("main and bot_shield share one forwarding-header list", main._FORWARD_HEADERS is bs.FORWARD_HEADERS)

real = TestClient(main.app)
r = real.get("/robots.txt", headers=BROWSER)
check("main serves robots.txt with no session, login on", r.status_code == 200 and "GPTBot" in r.text, r.status_code)
r = real.get("/agents", headers=BROWSER)
check("the login gate's 401 also carries noindex", r.status_code == 401
      and "noindex" in r.headers.get("x-robots-tag", ""), (r.status_code, r.headers.get("x-robots-tag")))
r = real.get("/", headers=GPT)
check("main answers GPTBot 403 on the dashboard", r.status_code == 403, r.status_code)
r = real.get("/s/anything/", headers={"user-agent": "Mozilla/5.0 (compatible; ClaudeBot/1.0)"})
check("main answers ClaudeBot 403 on a share link", r.status_code == 403, r.status_code)

html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
check("dashboard index.html carries <meta name=robots noindex>", '<meta name="robots" content="noindex' in html)

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("ALL PASS")
