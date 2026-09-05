# Connections & business data

*[Tiếng Việt](../09-mcp-va-so-lieu.md) · **English***

The **Connections** page is where you wire Javis into the tools you already use: Pancake POS, Zalo, Webcake Landing, Botcake, Meta/Google/TikTok ads, calendars, CRMs and more. Once connected, Javis reads REAL numbers and, if you grant permission, takes real actions in those tools. This page covers connecting a service from the Store, wiring several accounts, permissions, the call log, and how to read the numbers.

> **Since version 0.55.36: most services live in the Javis Store rather than shipping with the app.**
>
> The app now bundles only **Composio**, the **Google set** (Calendar, Gmail, Drive/Docs, Sheets, Tasks, Keep,
> Ads, Search Console, NotebookLM), **Zalo**, **Botcake**, **Substack**, and the **Add your own (advanced)** card.
>
> Every other service in this document (Pancake POS, Shopify, Meta Ads, Facebook Pages, TikTok
> Ads, Slack, Lark, n8n, Hostinger, Webcake...) works exactly the same, with ONE extra first step: open the
> **Javis Store** tab on the Connections page, find the service and click **Install**. It then appears under
> **Available connections** and every instruction below applies verbatim.
>
> In exchange, a service update reaches you through the store rather than waiting for a new Javis release. If you
> already connected an account, the Connections page shows a button to reinstall exactly that service, and once installed
> the old connection continues with the old login.

## What this feature is

Underneath, each connection is an MCP (Model Context Protocol) pipe joining Javis to an external service, but you do not need to know that detail. What changed in version 0.9:

- **A built-in connection store**: pick a service, paste an API key (or scan a QR code for Zalo) and you are done. Javis checks the key and names the account itself (taking the shop name straight from Pancake POS, for example). No more typing URLs or headers.
- **One service, many accounts**: 3 Pancake shops = 3 accounts inside one Pancake POS card. 2 Zalo numbers = 2 Zalo accounts running side by side. Each account is enabled, permissioned and defaulted separately.
- **Every brain shares them**: Claude Code, ChatGPT (Codex), OpenRouter, OpenAI API, Anthropic API and Google Gemini (API) all use this same Connections store through Javis's hub, so you wire once and change model freely. Gemini has one discrepancy: the runtime already calls tools through the hub, but the Connections page still shows a yellow warning saying the main model is Google Gemini (API) and does not support tool calling, because the interface list has not been updated. Use it normally.
- **Hard permissions**: each account has a permission level. Javis genuinely BLOCKS over-permission actions (rather than merely discouraging them in words), for example creating an order while set to Read only.

## Where to find it in Javis

1. Open the dashboard (port `7777` by default).
2. In the left sidebar, open the **Connections** group and click **Connections** (the plug icon, subtitled "Data sources & tools").
3. The page has 3 areas:
   - **◆ Connected** - the accounts you have wired, with a "Only use Javis connections (ignore the machine's own)" checkbox.
   - **◆ Available connections** - services present on the machine, ready to take an account, with a "Find a service…" box and filter buttons: **All**, App store, Sales, Messaging, Marketing, Office, Ads, Social, Creative. The six Google services collapse into ONE **Google** card reading "6 services"; click **Pick a service** on that card to see the sub-list.
   - **◆ Claude Code and Codex built-in connections** - a COLLAPSED block at the bottom of the page, subtitled "display only, click to view". These are sources already signed into your Claude account (synced from claude.ai) and in the Codex CLI. The list only loads when you open it, and it takes a moment because Javis checks each source's state. It is read-only here.

## How to use it (step by step)

### 1. Connecting Pancake POS (paste an API key)

1. In the **connection store**, find the **Pancake POS** card and click **Connect**.
2. Follow the instructions in the dialog: open Pancake POS > Shop configuration > Apps & API > create an API key, then paste it in.
3. Click **Connect**. Javis verifies the key: on success it reads "✓ Connected: <shop name>" and the account appears under Connected. A wrong key reports the error on the spot.
4. Several shops? Click **+ Add account** on the Pancake POS card and paste the next shop's key. Each shop gets its own chip.

Pancake POS defaults to **Read only**, so Javis can see revenue, orders and customers but cannot create orders or touch money. To let Javis act, see Permissions below.

### 2. Connecting Zalo (QR scan)

Requires Node.js 20+ on the machine running Javis (download from nodejs.org, install once).

1. In the store, click **Connect** on the **Zalo Agent MCP** card.
2. Read the risk warning: this is an UNOFFICIAL tool, and the Zalo account can be limited or locked, so a secondary account is recommended. Click "I understand the risk, show the QR code".
3. Open Zalo on your phone > the QR icon in the top corner > scan the code on the Javis screen.
4. Once scanned, the account appears. Add another Zalo number with **+ Add account**; accounts run isolated and do not interfere.

Zalo defaults to Full power so the send-message tool is usable. You can lower it to Draft or
Read only on the account chip. The current integration uses the seven `zalo-agent-cli` tools directly,
with no separate listener, webhook or Telegram forwarding. See
[the Zalo Agent MCP guide](12-zalo-agent-mcp.md).

### 3b. Connecting Slack / Systeme.io

- **Slack** (first-party MCP, sign in from the dashboard): Slack requires the MCP to go through an app of your own, so it takes a few one-time steps: go to api.slack.com/apps, create an app in your workspace, under "OAuth & Permissions" add the Redirect URL `http://localhost:7777/connect/oauth/callback` (on a VPS add your domain address too) and add the "User Token Scopes" (search, channels, users, chat:write, canvases...), then copy the Client ID and Secret into the connection dialog. If your workspace requires app approval, an admin must approve it. Defaults to Read only; sending messages needs Full power.
- **Systeme.io** (first-party MCP, paste a key and you are done): go to systeme.io > Profile settings > "MCP & API keys" > create an MCP key (90 days maximum) and paste it in. Javis can manage contacts, tags, newsletters and funnels. Defaults to Read only.
- **Lark** (first-party MCP, runs locally, needs Node.js 18+): messaging, documents, Base tables, wiki and contacts in Lark. Create a Lark app at open.larksuite.com/app, grant scopes (im, docx, bitable, contact...), and paste the App ID and App Secret. Javis can only do what the scopes you granted allow. Defaults to Read only; sending messages and granting file access need Full power.

### 3c. Connecting Shopify (store lookup)

Every Shopify store exposes a public MCP following the UCP standard, making this the easiest connection in the store: **no API key, no app to install, and you do not have to own the shop**.

1. In the **store**, find the **Shopify** card and click **Connect**.
2. Paste the store address (a custom domain or a `...myshopify.com` address both work). Missing `https://`, a trailing slash or pasting a whole product URL is fine; Javis trims it to the right domain.
3. The **UCP agent profile** field is prefilled; leave it as is and click Connect.

Javis can look up products, prices and stock, and build a cart for you to check out. It defaults to **Read only** (lookups only); to let Javis build a real cart, raise it to **Draft**.

Two things to know:

- A cart is **not an order** and charges nothing. Shopify returns a link for a real person to click and pay; Javis does not declare payment capability so it cannot pay by itself.
- This is the store's **public channel**, not an admin portal: it cannot show the shop's revenue, orders or customers.

What the UCP agent profile field is: Shopify requires each call to carry a link to a declaration of "what this agent can do", which the store downloads and agrees to. Javis attaches it on every call and you do nothing. Only change that field if you want to use your own declaration.

### 3. Connecting Webcake Landing / Botcake

- **Webcake Landing**: get a JWT at webcake.io > Settings > Access tokens > Create API keys, and paste it in. Javis then designs and edits landing pages by voice or text. Needs Node.js 18+.
- **Botcake**: open Botcake > Configuration > Integrations > Public API > Create API Key; paste the Page ID and key. Javis can read customers, tags and flows, and (with Full power) send flows to customers.

### 4. Connecting the Google set (Sheets, Search Console, Calendar, Gmail, Workspace, Tasks, Keep)

Apart from Search Console, the Google services share one **Google** card in the store (reading "6 services"). Click **Pick a service** to open the list and choose. Once you have created an OAuth client for one service, later services just need **Reuse key**, with no second trip to Google Cloud.

- **Google Sheets**: push revenue, stock and receivables reports into spreadsheets. Create a service account in Google Cloud (instructions are in the connection dialog), share a Drive folder with the service account email, and paste the JSON key contents plus the folder ID. Nothing else to sign into.
- **Google Search Console**: website SEO data (which keywords people search, click counts). Also a service account JSON, with that email added as a user in Search Console.
- **Google Calendar** and **Gmail** (2 separate connections, Google's first-party MCPs, running remotely so they work on a VPS too): Calendar reads the schedule, finds free slots, and creates, edits and deletes events and reminders; Gmail reads and searches mail, writes DRAFTS and applies labels. The safety point: the first-party Gmail server has NO direct send tool, so Javis always stops at a draft for you to send. You create an OAuth client once (console.cloud.google.com > Credentials > OAuth client ID of type "Web application", add the redirect URI exactly as the connection dialog states, and add your own email to Test users). Paste the Client ID and Secret, click Connect, and the browser opens for you to sign into Google. Use the SAME OAuth client for both Calendar and Gmail (just enable the matching API). Both default to Read only; raise to Draft to create events and write drafts, and Full power to delete events. **You must declare the full scope list** on the Data Access page of the Google Auth Platform: Google's MCP server does not accept the umbrella `calendar` scope alone, and free/busy lookups specifically require `calendar.events.freebusy`; without it sign-in still turns green but any availability check reports a missing scope, and deleting and reinstalling does not fix it (the connection dialog lists the full set for you to paste).
- **Google Workspace** (Gmail + Calendar + Drive + Docs + Sheets in one connection, running locally): create an OAuth client in Google Cloud once (about 10 minutes, step by step in the connection dialog), of type "Desktop app", so unlike the two cards above you do NOT declare a redirect URI. **Only usable on a machine with a screen**: the first time Javis calls a tool, the browser on the machine running Javis opens for you to approve, so on a VPS use the Calendar and Gmail connections above. Enable the API for each service you intend to use (Gmail, Calendar, Drive and Docs are the four basics; add Sheets, Slides, Forms, People, Tasks if needed); forgetting one makes that tool group fail while the rest keeps working. Fill in the Google email field too, since leaving it empty makes the server ask which account on every tool call. It defaults to Draft: Javis writes mail drafts, creates events and creates documents but does NOT send mail or delete anything; Full power requires acknowledging the risk. Choose this if you want Drive/Docs/Sheets all in one; if you only need Calendar + Gmail, the two separate connections above are leaner (fewer tools, remote, VPS-friendly).
- **Google Tasks** (to-do lists, running locally through `uvx`): view lists, add tasks, set due dates and mark them done. It only requests the Tasks scope and cannot read Gmail or Drive. It shares the OAuth client with Google Workspace; just enable the Google Tasks API for the project and create a "Desktop app" client. Defaults to **Draft**, at which level Javis can already create, edit, complete and delete individual tasks; Full power adds creating, renaming and DELETING whole lists (deleting a list loses every task inside, with no undo). It runs on the same server as Google Workspace, so it is also **only usable on a machine with a screen**: the first tool call opens the browser on the Javis machine for approval.
- **Google Keep** (notes, running locally through `uvx`): search notes, create notes and to-do lists, label, pin and archive. **Read this before connecting**: Keep has no first-party API, so this connection must use a **master token with FULL Google account access** (Gmail, Drive, Photos), not a scoped OAuth token like Gmail or Calendar. Javis only touches notes, but if that token leaks it opens the whole account. To connect: enable 2-step verification, create a 16-character App Password, and paste your email plus that string; Javis exchanges it for a token and does NOT store the App Password. Leaving `unsafe_mode` empty means Javis can only edit notes it created itself; typing `true` lets it edit every note, including ones you wrote by hand. Defaults to **Read only**.

- **Google NotebookLM** (running locally through `uvx`): list notebooks, read the sources inside, ask questions inside a notebook, add sources, save notes, and create summaries or audio in Studio. **Read this before connecting**: NotebookLM has no first-party API, so this connection borrows your **browser session cookie**, a credential equivalent to being signed into your Google account, not a scoped OAuth token like Gmail or Calendar. To connect: on a **personal machine with a browser** (not possible on a VPS) run `uvx --from "notebooklm-py[browser]" notebooklm login`, sign into Google and open NotebookLM once; then open the generated `~/.notebooklm/profiles/default/storage_state.json`, copy its whole contents and paste them into the field in the connection dialog. When the session expires, rerun that command and paste the new string. Defaults to **Read only**: Draft allows asking questions and creating summaries (spending NotebookLM quota), and Full power allows deleting notebooks and sharing them externally. The underlying library (`notebooklm-py`) is unofficial, so a Google protocol change can break this connection at any time.

Tip: if you only need Gmail/Calendar/Drive and you use the Claude Code engine, the faster route is clicking Connect inside the Claude app itself (claude.ai > Settings > Connectors); Javis sees them in the collapsed **◆ Claude Code and Codex built-in connections** block at the bottom of the page.

The same holds for the ChatGPT (Codex) engine: MCPs you registered directly in the Codex CLI (`codex mcp add <name> --url https://...` for an HTTP server, or `codex mcp add <name> -- <command>` for a stdio server) are loaded by the ChatGPT engine at runtime and appear in that same collapsed block (the Codex list sits under the Claude Code list). For an OAuth server, run `codex mcp login <name>` once in the terminal. OAuth servers added through Javis's "Add your own (advanced)" form are registered into both CLIs (Claude Code and Codex) so switching engines does not lose tools.

### 5. Connecting ads (Meta Ads, Google Ads, TikTok Ads)

All 3 default to **Read only**, so Javis reads reports and analyses cost and performance but cannot touch campaigns.

- **Meta Ads (Facebook & Instagram)** has TWO connections in the store; pick one:
  - **Meta Ads (first-party MCP)**: Meta's hosted MCP. It is currently in LIMITED beta: Meta only lets a few pre-approved applications (the ChatGPT/Claude/Perplexity assistants) connect and has disabled self-registration, so Javis, like other tools, CANNOT self-serve yet. This is not a fault on your machine; wait for Meta to widen access. Details below.
  - **Meta Ads (your own app, Graph API)**: the route that WORKS today (the same one Composio and byadsco use), where Javis calls Meta's Marketing API directly using a Facebook App YOU create. READ ONLY for data, spending nothing. Instructions for creating the app are below.
- **Google Ads**: Google's first-party MCP, purely read-only (GAQL queries: campaigns, cost, conversions, keywords). It is the most technical setup in the store and needs four things: a developer token (from the Google Ads API Center of your MCC manager account, Explorer level is enough for reading), a Google Cloud project with the Google Ads API enabled, an OAuth client ID of type **"Web application"**, and inside that client the redirect URI `http://localhost:7777/connect/oauth/callback` (on a VPS add `https://<your-domain>/connect/oauth/callback` too). Fill it in and click the sign-in button, and the browser opens for you to grant access: **Javis builds the credentials file itself, with NO Google Cloud CLI and no commands to run**. If you already ran `gcloud` yourself, paste the contents of `application_default_credentials.json` into the last field for speed. If you run ads through an agency/MCC, add the manager account ID as well. If you see "this app is not verified", click Advanced > Continue, because it is your own app.
- **TikTok Ads**: TikTok has not opened a first-party MCP (only announced at TikTok World in May 2026), so Javis uses a community server on the official Marketing API, purely read-only (accounts, campaigns, reports). Create a Marketing API app at business-api.tiktok.com and paste the App ID, Secret and Access Token. It will be swapped for the first-party version when TikTok ships one.

Google Ads and TikTok Ads run locally through the `uv` tool, which the Javis machine needs once: `winget install astral-sh.uv` (Windows) or see docs.astral.sh/uv. **Google Ads also needs Git** on the Javis machine, because `uvx` pulls the server straight from GitHub. Without Git the connection dies immediately even with `uv` installed.

#### Connecting Meta Ads through the Graph API (your own Facebook App), one-time, about 10 minutes

This is the self-serve route that works today, independent of Meta's MCP beta. You create your own Facebook App and Javis uses it to read your ad account data. Because the app is yours and stays in development mode, you can grant yourself read scopes WITHOUT Meta's App Review.

**Before you start: check which interface you have.** Meta is migrating the app management pages, so two people opening it at the same time can see two different menus. Look at the **left column** in the app:

- Seeing **"Products"** means the **OLD** interface.
- Seeing **"Use cases"** and NO "Products" means the **NEW** interface.

Both are identical except for where you open Facebook Login (step 2). If you cannot find "Products" or "Facebook Login for Business", you are almost certainly on the new interface, and it is not a permission problem or an unverified Business Manager.

1. Go to [developers.facebook.com/apps](https://developers.facebook.com/apps) > **Create App**. Pick the **Business** type (or "Other") and name it anything (for example "Javis reads ads").
2. Open the **Facebook Login** section, depending on the interface:
   - **OLD**: **Products > Add product** > add **Facebook Login** (the REGULAR one, NOT "for Business"), then click **Settings**.
   - **NEW**: left column **Use cases** > open **"Authenticate and request data from users with Facebook Login"** > **Customise** > **Settings**. That use case usually exists as soon as you create the app, so there is nothing to add.
3. The **Valid OAuth Redirect URIs** field behaves **differently depending on where Javis is installed**:
   - **On a personal machine** (a `localhost` address): **skip this field, nothing to fill in.** While the app is in Development mode, Meta **automatically allows** redirects to localhost, so the field deliberately rejects localhost. Meta says so right there: in development mode, http://localhost redirects are automatically allowed and need not be added. Being unable to fill it in is **correct**, not a fault, so move on. Just make sure Javis runs at **localhost** rather than 127.0.0.1.
   - **On a VPS / custom domain**: **it is required**. Paste your exact https address and Save, for example `https://javis.yourdomain.com/connect/oauth/callback`. Outside localhost, Meta does not auto-allow and requires **https**; skipping this makes sign-in fail.
   - **Do not type it by hand**: the Javis connection dialog has an address field with a **Copy** button that generates the EXACT address for your machine's domain; click Copy and paste it verbatim. Facebook matches **character by character** (including a trailing `/`), and one wrong character produces **"URL blocked"**.
   - **Also for VPS / custom domains**: go to **App settings > Basic**, and in **App Domains** enter the bare domain, for example `javis.yourdomain.com` (NO `https://`, NO `/`), then scroll to the bottom and click **Save changes**. The Javis connection dialog has a Copy button for this domain too. Without it, Facebook reports **"Cannot load URL: the domain of this URL is not included in the app's domains"**.
   - Do not go into "App settings > Advanced"; that is somewhere else entirely.
4. Keep the app in **Development** mode (the toggle at the top stays on "In development"). Make sure you are an **Admin** of the app and of the ad account you want to read; that is what lets `ads_read` be granted without App Review.
5. **Skip "Business verification" and "App review"** even though the app's "To do" panel suggests them. Those only matter when your app serves OTHER businesses accessing their data; using it for your own account needs neither, and doing it only adds days of waiting.
6. Go to **App settings > Basic** and copy the **App ID** and **App Secret**.
7. Back in Javis, on the **Connections** page > the **Meta Ads (your own app, Graph API)** card > paste the App ID and App Secret > **Connect**. The browser opens Facebook for you to approve; afterwards return to Javis and refresh.

Once connected, ask Javis in words: "how much did my Facebook ad account spend this week, and how did it perform?". Javis has read tools for the ad account list, performance (spend, impressions, clicks, CTR, CPC, reach, conversions) over a period, and the campaign list. All READ ONLY: Javis does not create or edit campaigns and does not spend your money.

On expiry: Facebook tokens live about 60 days and Javis refreshes them while in use. If it goes unused long enough to expire, just click Connect again to sign into Facebook once more.

### 5b. Connecting Facebook Pages and Facebook Monitoring

These two live in the **Social** group in the store and serve very different purposes:

- **Facebook Pages (your own app, Graph API)**: manage YOUR OWN Pages. Read only shows the Page list, posts and comments; Full power posts text, photos, multi-photo albums and video, edits published posts, and replies to and deletes comments. The setup is identical to Meta Ads (Graph API) above and **reuses the same Facebook App**, with Page scopes added. When Facebook asks for permissions, remember to TICK the Pages. Defaults to **Read only**; deleting a post cannot be undone (Pages have no recycle bin), so only raise to Full power when you genuinely want Javis publishing.
- **Facebook Monitoring (Apify)**: monitor other people's **public** Pages and Groups to find viral posts, returning share/reaction/comment counts so you can filter the hot ones. The important part: it scrapes through the Apify service and does NOT use your personal Facebook account, so there is no lock-out risk and it runs fine on a VPS 24/7. To connect: sign up at apify.com, go to Console > Settings > API & Integrations, copy the "Personal API token" and paste it in. Cost is per scrape, roughly 2.6 USD per 1000 posts. This connection is **read only** with no write path. Private groups are not supported yet (they would need a cookie).

### 5c. The remaining connections in the store

- **Composio** (App store group): one connection opening more than 500 apps (Gmail, Notion, Sheets, GitHub, Linear, Slack...). Go to platform.composio.dev, create an MCP server, copy the `ck_...` API key and paste it in. Then ask for an app in chat ("connect Notion through Composio") and Composio gives you a sign-in link for that app. **Important permission note**: every action of every app runs through ONE shared Composio tool, so Javis cannot separate reads from writes. Read only (the default) can only search and read tool descriptions, doing nothing; to let Javis act you must raise it to **Full power**, and at that point Javis can take ANY action on the apps you connected, including sending messages and deleting data.
- **Higgsfield** (Creative group): create and edit images and video with AI: generate images, generate video, upscale, outpaint, remove backgrounds, cut out subjects. One-tap sign-in with no app to create and no key to paste: click **Connect**, sign into your Higgsfield account and approve. Each generation or edit **spends prepaid credits** in your Higgsfield account. Defaults to Draft (generation works, deletion and payment blocked); to let Javis only browse history and save credits, lower it to Read only.
- **X (Twitter)** (Social group): search and read posts, view public profiles and metrics through X's first-party MCP. Go to developer.x.com > Developer Portal > Projects & Apps > the "Keys and tokens" tab > generate a **Bearer Token** and paste it in. This is an App-only token, so it is **read only** and cannot post.
- **Substack** (Marketing group): write and publish posts and newsletters in words. Javis calls the Substack API directly from internal Python, so NO Node install is needed. It needs three things: your Substack address, a session token (the `substack.sid` cookie from DevTools) and your User ID; the **Instructions** button in the connection dialog opens a page with a helper for fetching the User ID and address quickly. Defaults to **Draft**: it only creates drafts, publishing nothing and emailing nobody. To let Javis publish for REAL you must raise it to Full power; even then, publishing defaults to web only, and only when you explicitly say "email the subscribers" does Javis set the mail flag, and a sent email cannot be recalled. The session token has full account access, so guard it like a password.

### 6. Managing one account (a chip)

Click an account chip under Connected to open its menu:

- **Test connection**: makes a trial call and reports how many tools are available.
- **Set as default**: with several accounts of the same service, Javis prefers the default when you do not name a shop.
- **Rename** / **Disable temporarily** / **Delete**.
- **Change permission**: see Permissions.
- **Block a specific tool**: for advanced users, type the name of a tool to forbid outright.
- **Tool call log**: see what Javis called, when, and what was blocked.

### 7. The 3 permission levels (important)

Each account has a permission level, and Javis blocks HARD at the call site:

- **Read only**: view data only. Creating orders, editing data, sending messages are all blocked. The safest level, and the default for POS.
- **Draft**: may write and edit ordinary data (notes, products...), while still BLOCKING money, order and messaging actions.
- **Full power**: REAL actions: creating orders, sending messages, publishing pages. Enabling it requires ticking "I understand the risk"; Zalo carries its own additional warning.

Smarter than the old build: Javis understands Pancake's "2 in 1" tools, where the same order tool passes for `list orders` but is blocked for `create order` when the permission is insufficient.

Background loops are restricted further by their own mode: a `suggest` loop is read-only, and an `auto` loop never touches money, orders or messaging, regardless of what the account permission says.

### 8. Adding a service that is not in the store (advanced)

Service not in the store? Click the **Add your own (advanced)** card for the technical form from the old build (URL/command + headers/env, supporting HTTP, SSE and stdio). For services using standard MCP OAuth, Javis opens the sign-in page itself and keeps the token, working on a VPS too.

### 9. Removing a service from the store to keep it tidy

The store has 29 services and you normally use a handful. Hover a store card and an **×** appears in the top right: clicking it removes that service from the store, from every brain's tool list, and from the context of every chat turn.

Three things to know before clicking:

- **Removing is not deleting.** The service's files stay in the installation; Javis just remembers that you removed it. That is why updating Javis does **not** bring it back, while reinstalling is one click.
- **Reinstall in the "Removed" area**, below the store and collapsed by default. Each removed service is a row with a **Reinstall** button.
- **Your connections are NOT deleted.** If you have accounts wired to that service, Javis asks before removing. Once removed, those connections **stop running** (Javis no longer calls them) but remain under Connected, and a reminder strip appears at the top of the page. Reinstalling the service resumes them with no rewiring.

### 10. "Only use Javis connections" (strict) mode

Tick this box under Connected if you want Javis to use ONLY the connections declared here, ignoring MCPs installed in Claude Code on the machine: tighter control, avoiding accidental calls to your Claude account's tools. Note: this applies to the Claude Code engine (the Claude CLI strict flag); Codex's own MCP registry is managed by the codex command, so to make the ChatGPT engine drop a native server, remove it with `codex mcp remove <name>`.

## Reading the numbers

Unchanged from before: ask directly in chat ("how much did we sell today, compared with yesterday?"), Javis calls the right source and answers with the formula of numbers + comparison with the previous period + cause + recommendation, and pushes 3 to 6 metrics into the metrics panel in the left column of the Javis screen. Closed periods are cached in the brain's `05 - Data Cache/`. With several shops, name the shop; without a name Javis uses the default account.

## Tips

- Name accounts after the shop so they are easy to reference in chat ("Kim Khi shop" versus "shop 2").
- Leave POS on Read only if you only want reports; then Javis cannot create an order by accident.
- The first message after a restart can be slow for locally running connections (Zalo, Webcake) because the tool has to boot; later turns are fast because Javis keeps the connection alive.
- The tool call log is the first place to look when you suspect Javis "did something odd".

## Common problems

- **Facebook says "URL blocked" during sign-in**: the redirect URI in the Facebook app does not match. Open the Javis connection dialog, click **Copy** on the redirect address and paste it VERBATIM into "Valid OAuth Redirect URIs" (Facebook Login > Settings), then Save. Do not type it; Facebook matches character by character.
- **Facebook says "Cannot load URL: the domain of this URL is not included in the app's domains"**: App Domains is missing. Go to App settings > Basic > "App Domains", paste the bare domain (no https, no slash), using the Copy button in the connection dialog, and click "Save changes" at the bottom.
- **Pasting a key reports that it is wrong or lacks permission**: recreate the API key in the service and paste again. For Pancake, check the key belongs to the right shop.
- **Zalo reports that Node.js 20+ is required**: install Node.js from nodejs.org and try again.
- **Google Ads / TikTok Ads will not connect**: check whether the machine has `uv` (`winget install astral-sh.uv`). **Google Ads also requires Git**, because `uvx` pulls the server from GitHub; without Git, `uv` alone is not enough. The first connection downloads packages so it can be slow; click Test again after a minute or two.
- **Meta Ads (first-party MCP) reports that self-serve / DCR connection is not allowed**: that is accurate rather than a fault on your machine. Meta's hosted MCP is in beta and only accepts a few pre-approved applications. To read your numbers today, use the **Meta Ads (your own app, Graph API)** connection above.
- **Meta Ads (Graph API) reports that Facebook refused / redirect_uri**: check by install type. On a **personal machine**: (1) the app is in Development mode, which is what makes localhost acceptable, and leaving Development breaks it immediately; (2) Javis is opened at `localhost` rather than 127.0.0.1; (3) the App ID and App Secret were pasted correctly. On a **VPS/domain**: check that Valid OAuth Redirect URIs holds your exact **https** address, matching character by character including the `/connect/oauth/callback` path.
- **You cannot enter localhost into "Valid OAuth Redirect URIs"**: correct, and not a fault. In Development mode Meta allows localhost automatically and blocks manual entry, with a note next to the field. Skip it and continue; only VPS/domain installs need to fill it in.
- **A panel appears reading "Invalid Scopes: pages_show_list, pages_read_engagement, ..." (or ads_read, business_management)**: **click OK and continue.** This warning is only shown to the app's creator and **does not block sign-in**; the message itself says "This message is only shown to developers". While the app is in Development mode and you are an app Admin, Facebook still grants the scopes, so in most cases the connection works right away. A quick check: after connecting, ask Javis to "list my Pages"; seeing them all means everything is fine.

  **Only if** the connection completes and Javis sees no Pages (or no ad accounts) do you need to add scopes. In the **new interface**, scopes are gated per use case: an app created with the "Authenticate and request data from users" use case only has `email` and `public_profile`. To add them:
  - **Page scopes**: **Add use case** > pick **"Manage everything on your Page"** > **Customise** > the **Permissions** tab > click Add for `pages_read_engagement`, `pages_manage_posts`, `pages_manage_engagement`. `pages_show_list` and `business_management` usually come with that use case already.
  - **Ads scopes**: **Add use case** > pick the ads-related use case (Marketing API) > **Customise** > the **Permissions** tab > add `ads_read` and `business_management`.
  - **Old interface**: go to **Products > Add product** and add **Marketing API** (for ads) or regular **Facebook Login** (for Pages); in Development mode you can grant these to yourself without App Review.
  Once added, return to Javis and click Connect again.
- **You want Javis to manage ONE MORE Page**: click **Reconnect** on the Facebook Pages card. Facebook shows the **"Choose what you allow"** screen again: tick the new Page while **keeping the old ones ticked** (unticking a Page revokes Javis's access to it), then click Continue. There is no need to delete the account and start over. If Facebook skips straight past with "Continue as <your name>" without letting you choose, check that Javis is on version 0.9.249 or later; older builds lacked the parameter forcing Facebook to ask again, so the Page selection screen was skipped.
- **Meta Ads (Graph API) reports no ad accounts found**: the token lacks `ads_read`, or the signed-in Facebook account is not an admin of any ad account; check your role in Business/Ads Manager.
- **The app has no "Products" item, or no "Facebook Login for Business"**: you are on Meta's **NEW** interface, where the Products menu was replaced by **Use cases**. Go to the left column **Use cases > Customise > Settings** to find the redirect URI field. This is NOT caused by an unverified Business Manager or missing permissions; see step 2 in the guide above.
- **You cannot find "Facebook Login for Business" even in the right place**: the "for Business" version only appears for apps created with the **Business** type, and an app's type cannot be changed. But Javis's setup uses **regular Facebook Login**, so you do not need the business version.
- **The QR code expired**: click retry for a new one (Zalo QR codes live about 3 minutes).
- **A tool was blocked with a note about a restricted permission level**: that is by design. Raise the account's permission in the chip menu if you genuinely want Javis doing that.
- **A source that flickers, such as "the first order goes through, the second drops the connection"** (common with Pancake POS): fixed in **0.52.8**. Each source has one session, and every chat turn re-asks that session for its tool list. That re-ask queues behind the order in flight, and after 20 seconds the old build **killed the whole session**, killing the half-created order with it, after which the source vanished from the toolbox and Javis reported that no POS was connected. Now a source that is running a tool is left alone, and the previous tool list is kept. The Connections page also stops flagging a busy source as broken.
- **After updating from an older build**: old MCP servers migrate into accounts on the Connections page automatically (the original is backed up in `mcp_servers.v1.bak.json`), so nothing needs redeclaring.
- **You want the old mechanism back** (one entry per server, no hub): set `"mcp": {"hub": false}` in `server/settings.json` and restart.

## Related

- [Models & engines](10-models-and-engines.md) - which brain can use what, and where to switch model.
- [Zalo Agent MCP](12-zalo-agent-mcp.md) - QR sign-in, the seven tools and permissions.
- [Chat & voice](02-chat-and-voice.md) - asking for numbers in words.
- [Usage: tokens & cost](23-usage-and-cost.md) - seeing how much tool calling is burning.
