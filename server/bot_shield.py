"""Keeps a Javis whose address leaked out of search results and away from AI crawlers.

Owner request 2026-11-09: block indexing and block AI bots from reaching Javis OS when the admin link leaks out. A
dashboard reachable from the Internet (VPS, Cloudflare Tunnel, Tailscale Funnel) does get found: its domain shows up in
certificate transparency logs, a link pasted into a group chat gets crawled, and device search engines (Shodan, Censys)
scan every address. The login gate already keeps the data behind a password; this module keeps the address itself out
of search results and stops AI crawlers from reading even the login page.

Three layers, each enough on its own for the bots that obey it:

1. `X-Robots-Tag: noindex, ...` on EVERY HTTP answer (the BotShield middleware), so a page a search engine does reach
   is dropped from results: the login page, share links, error pages.
2. `/robots.txt` (`robots_txt()`): AI crawlers, SEO tools and every unknown robot are told not to fetch anything.
3. A 403 for a request that names itself a crawler, AI agent, SEO tool or device scanner in its User-Agent, or signs
   itself as a bot (`Signature-Agent`, the Web Bot Auth standard used by ChatGPT agent). This stops the ones that
   ignore robots.txt.

Why robots.txt does NOT disallow the big search engines: a search engine only drops a URL it is able to fetch. A URL
blocked by robots.txt is never fetched, so its noindex is never read, and Google can still list the bare link when
another page points at it (Google Search Central, "Block Search indexing with noindex"). Letting Googlebot fetch and
answering it 403 plus noindex is what removes a leaked link for good. Do not "fix" this by moving the search engines
into the Disallow group.

Never blocked:
- requests made on this machine itself (loopback, no forwarding header): Javis's own tools and engines;
- machine endpoints that outside services must reach (webhooks, OAuth callbacks, the MCP hub, plugin routes under
  /ext/ and /.well-known/ such as Javis Gate for ChatGPT and Claude), see `exempt()`;
- link previews (facebookexternalhit, TelegramBot, Zalo, Slackbot, Discordbot, Twitterbot...): they are on no list, so a
  share link pasted into a chat still shows its card;
- ordinary HTTP clients (curl, python-requests, httpx, the claude CLI): the Javis CLI and scripts use them.

`JAVIS_BLOCK_BOTS=0` turns the 403 off, an escape hatch for an integration whose User-Agent happens to match. The noindex
header and robots.txt stay: on a private dashboard they cost nothing.
"""
from __future__ import annotations

import os

# Sent on every answer. noai/noimageai are not a formal standard but several AI crawlers read them; unknown values are
# ignored by the engines that do not.
ROBOTS_TAG = "noindex, nofollow, noarchive, nosnippet, noimageindex, noai, noimageai"

# AI crawlers, AI assistants fetching on a user's behalf, and dataset builders that sell to AI. Each entry is the
# robots.txt token AND, lowercased, a substring of the User-Agent the bot sends (Google-Extended and Applebot-Extended
# are robots.txt tokens only; listing them costs nothing). Sources: each vendor's crawler documentation and the
# ai-robots-txt project list. Keep entries specific: a short generic word would catch real browsers.
AI_AGENTS = (
    # OpenAI
    "GPTBot", "ChatGPT-User", "OAI-SearchBot",
    # Anthropic
    "ClaudeBot", "Claude-Web", "Claude-User", "Claude-SearchBot", "anthropic-ai",
    # Google's AI uses (Googlebot itself is a search engine, below)
    "Google-Extended", "GoogleOther", "Google-CloudVertexBot",
    # Apple, Amazon, Meta, ByteDance
    "Applebot-Extended", "Amazonbot", "NovaAct", "Meta-ExternalAgent", "Meta-ExternalFetcher", "FacebookBot",
    "Bytespider", "TikTokSpider",
    # Perplexity, Mistral, Cohere, You.com, DuckDuckGo's assistant, Allen Institute, Phind
    "PerplexityBot", "Perplexity-User", "MistralAI-User", "cohere-ai", "cohere-training-data-crawler", "YouBot",
    "DuckAssistBot", "AI2Bot", "PhindBot",
    # Dataset builders and scrapers feeding AI
    "CCBot", "Diffbot", "omgili", "Webzio-Extended", "Timpibot", "ImagesiftBot", "img2dataset", "PanguBot",
    "Kangaroo Bot", "iaskspider", "ICC-Crawler", "VelenPublicWebCrawler", "FriendlyCrawler", "Brightbot", "Scrapy",
    "FirecrawlAgent",
)

# Search engines and web archives. robots.txt lets the main ones fetch (see the module docstring); the 403 below then
# answers them, which is the signal that drops a page from their index.
SEARCH_ENGINES_UA = (
    "googlebot", "google-inspectiontool", "storebot-google", "adsbot-google", "mediapartners-google",
    "bingbot", "bingpreview", "adidxbot", "msnbot", "slurp", "duckduckbot", "duckduckgo-favicons-bot",
    "yandexbot", "yandex.com/bots", "baiduspider", "applebot", "coccocbot", "seznambot", "sogou web spider",
    "360spider", "yeti/", "daumoa", "petalbot", "qwantbot", "mojeekbot", "exabot",
    "ia_archiver", "archive.org_bot",
)

# The search engines robots.txt names on purpose so they can fetch, read the 403 + noindex and drop the page.
# Every one of these must also match SEARCH_ENGINES_UA (test_bot_shield.py checks it).
SEARCH_ENGINES_ROBOTS = (
    "Googlebot", "Bingbot", "Slurp", "DuckDuckBot", "Applebot", "YandexBot", "Baiduspider", "coccocbot",
    "SeznamBot", "PetalBot", "Yeti",
)

# SEO tools: they build public link databases that list the address.
SEO_TOOLS_UA = (
    "ahrefsbot", "ahrefssiteaudit", "semrushbot", "siteauditbot", "mj12bot", "dotbot", "blexbot", "dataforseobot",
    "serpstatbot", "barkrowler", "megaindex", "screaming frog", "rogerbot", "seokicks", "linkpadbot", "zoominfobot",
    "awariobot",
)

# Device search engines and Internet-wide scanners: they record the page title of every server they find, which is how
# an exposed admin panel gets looked up later.
SCANNERS_UA = (
    "censysinspect", "zgrab", "expanse, a palo alto", "internetmeasurement", "netcraftsurveyagent", "l9explore",
    "l9tcpid", "shodan", "modatscanner",
)

_AI_UA = tuple(t.lower() for t in AI_AGENTS)
_GROUPS = (("ai", _AI_UA), ("search", SEARCH_ENGINES_UA), ("seo", SEO_TOOLS_UA), ("scanner", SCANNERS_UA))

# Paths outside services must keep reaching whatever they call themselves. Mirrors the public machine endpoints of
# main._AUTH_PUBLIC_*; none of them is a page for people to read.
MACHINE_PREFIXES = ("/hooks/", "/ext/", "/.well-known/", "/chatbot-api/")
MACHINE_EXACT = frozenset({
    "/robots.txt", "/health", "/tls-check", "/hub/mcp",
    "/whatsapp/webhook", "/messenger/webhook", "/threads/webhook", "/zalo-oa/webhook",
    "/connect/oauth/callback", "/messenger/oauth/callback", "/threads/oauth/callback", "/zalo-oa/oauth/callback",
    "/threads/uninstall", "/threads/delete", "/messenger/privacy",
})

# A proxy or tunnel on this machine connects from 127.0.0.1 too and adds one of these; a local tool does not.
# main._direct_local_request uses the same tuple.
FORWARD_HEADERS = ("x-forwarded-for", "x-real-ip", "forwarded", "cf-connecting-ip")

_OFF = ("0", "false", "no", "off")
_BLOCK_BODY = b"Javis OS is private. Automated access is not allowed.\n"


def block_enabled() -> bool:
    """The 403 layer is on unless JAVIS_BLOCK_BOTS says off. Read per request so a test or a restart-free env change
    takes effect."""
    return (os.getenv("JAVIS_BLOCK_BOTS", "") or "").strip().lower() not in _OFF


def classify(user_agent: str, signature_agent: str = "") -> str:
    """Which kind of bot this request says it is: "ai", "search", "seo", "scanner", "signed-agent", or "" for none.

    Pure: only what the request declares about itself. A bot that pretends to be Chrome is not caught here; the login
    gate is what stands in front of the data either way."""
    if (signature_agent or "").strip():
        return "signed-agent"
    ua = (user_agent or "").lower()
    if not ua:
        return ""
    for kind, tokens in _GROUPS:
        if any(t in ua for t in tokens):
            return kind
    return ""


def exempt(path: str) -> bool:
    """A machine endpoint (webhook, OAuth callback, MCP, plugin route) or robots.txt itself: never answered 403."""
    if path in MACHINE_EXACT or any(path.startswith(p) for p in MACHINE_PREFIXES):
        return True
    # Zalo's domain check fetches /zalo_verifier<code>.html (see main._auth_guard).
    return path.startswith("/zalo_verifier") and path.endswith(".html") and "/" not in path[1:]


def robots_txt() -> str:
    """The /robots.txt body. Built from the lists above so robots.txt and the 403 never disagree."""
    lines = [
        "# Javis OS is a private dashboard. Nothing here may be indexed or used to train or feed AI.",
        "",
        "# AI crawlers and assistants: fetch nothing.",
    ]
    lines += ["User-agent: " + t for t in AI_AGENTS]
    lines += ["Disallow: /", ""]
    lines += [
        "# Search engines are NOT disallowed here on purpose. Every answer they get is 403 with",
        "# X-Robots-Tag: noindex, and a crawler only drops a page it is able to fetch. A robots.txt block",
        "# would leave a leaked link listed with no description instead of removing it.",
    ]
    lines += ["User-agent: " + t for t in SEARCH_ENGINES_ROBOTS]
    lines += ["Disallow:", ""]
    lines += ["# Everyone else, SEO tools and scanners included.", "User-agent: *", "Disallow: /", ""]
    return "\n".join(lines)


def _is_direct_local(scope, headers: dict) -> bool:
    client = scope.get("client") or ("", 0)
    host = client[0] if client else ""
    if host not in ("127.0.0.1", "::1"):
        return False
    return not any(headers.get(h) for h in FORWARD_HEADERS)


class BotShield:
    """ASGI middleware: adds X-Robots-Tag to every HTTP answer and answers declared bots 403.

    Pure ASGI rather than @app.middleware("http"): it wraps streaming answers (chat, SSE) without buffering them, and
    it runs before the auth and CSRF gates so a blocked crawler costs no session lookup."""

    def __init__(self, app, enabled=block_enabled):
        self.app = app
        self.enabled = enabled
        self._tag = ROBOTS_TAG.encode("latin-1")

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path") or ""
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
        if (not exempt(path) and self._enabled()
                and classify(headers.get("user-agent", ""), headers.get("signature-agent", ""))
                and not _is_direct_local(scope, headers)):
            await send({"type": "http.response.start", "status": 403, "headers": [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"content-length", str(len(_BLOCK_BODY)).encode()),
                (b"cache-control", b"no-store"),
                (b"x-robots-tag", self._tag),
            ]})
            await send({"type": "http.response.body", "body": _BLOCK_BODY})
            return

        tag = self._tag

        async def send_with_tag(message):
            if message.get("type") == "http.response.start":
                raw = list(message.get("headers") or [])
                # A route that set its own X-Robots-Tag keeps it (a plugin page meant to be public, say).
                if not any(k.lower() == b"x-robots-tag" for k, _ in raw):
                    raw.append((b"x-robots-tag", tag))
                    message = {**message, "headers": raw}
            await send(message)

        await self.app(scope, receive, send_with_tag)

    def _enabled(self) -> bool:
        try:
            return bool(self.enabled())
        except Exception:  # noqa: BLE001 - an unreadable switch keeps the protection on
            return True
