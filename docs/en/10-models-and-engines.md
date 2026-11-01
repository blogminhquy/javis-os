# Models & engines

*[Tiếng Việt](../10-models-va-engine.md) · **English***

The **Models** page is where you pick Javis's "brain": signing into AI providers, ordering them by use (the top card is the main model, the cards below are fallbacks), choosing a model and a thinking level for each provider, and choosing a cheap model for background work. This page decides how smart Javis is and whose quota it spends.

If you are just starting, read [Getting started & first-run setup](01-getting-started.md) first. To attach external tools to Javis, see [Connections & business data](09-connections-and-business-data.md).

## What this feature is

Javis can run on many different "engines" (AI providers). The providers you connected sit in one **Usage order** list: the top card is **MAIN** (the conversation model), the cards below are **Fallback 1, 2...**, and chat moves down automatically when the card above runs out of quota. In addition:

- **Background model**: a cheaper model for what Javis runs while you are away: loops, Kanban work, reminders, self-learning, source ingestion.
- **Effort (thinking level)**: how hard the model thinks before answering. Each provider card has its own level, and the background model has its own too.

The most important thing to understand: **changing model does NOT cost Javis any capability.** Every provider gets the same toolkit through Javis's connection hub (MCP Hub): calling the Connections you wired, reading and writing files in the brain, running skills, queueing Kanban work (the `javis_task` tool), creating agents/workflows/loops/reminders (the `javis_schedule` tool).

| Route | Provider | Javis MCP · brain file tools · skills | Shell commands (Bash) |
|---|---|---|---|
| Through **Claude Code** | Claude Code | Yes, native MCP + native skills | **Yes** |
| Through **Codex** | OpenAI OAuth (ChatGPT) | Yes, MCP through the hub (local connections such as Zalo/Webcake included) + Codex's OWN MCP registry (servers you added with `codex mcp add`) + skills through the router (`javis_use_skill` / reading `skills/` files) | **Yes** |
| Through **Antigravity CLI** | Google Antigravity CLI (`agy`) | Yes, MCP through the hub (written into `~/.gemini/config/mcp_config.json`, see B1b) + skills through the router | **Yes** |
| **Direct API** | OpenRouter | Yes, MCP through the hub + vault file tools + skills through the router | No |
| **Direct API** | OpenAI (API) | Yes, as above | No |
| **Direct API** | Anthropic (API) | Yes, as above | No |
| **Direct API** | Google Gemini (API) | Yes, as above (since 0.9.270 the Connections page no longer misreports it) | No |
| **Direct API** | Groq (API) | Yes, as above | No |
| **Direct API** | DeepSeek (API) | Yes, as above | No |
| **Direct API** | Ollama Cloud | Yes, as above | No |

### The four things API engines lack

Before 0.17.1 this page said the "**only** difference is running shell commands". Neat, but wrong. The real list:

- **Shell commands (Bash)**, running commands on the server.
- **WebFetch and WebSearch**, opening an arbitrary URL to read it and searching the web. An API engine wanting outside data must go through a connected MCP.
- **Task**, spawning sub-agents running in parallel within one turn.
- **Resuming an earlier CLI session**; API engines rebuild the context every turn.

One more practical limit of API engines: each turn has a **cap on tool-call rounds** (it stops and says so beyond that). The answer streams word by word like the CLI engines, including when a turn **calls tools** (since 0.438.5).

Beyond those, every capability is identical. Specifically: calling every connected MCP, reading and writing files in the brain, reading a file you just attached or pasted into the chat, running skills, queueing Kanban work, creating loops and reminders, creating agents/workflows/skills (they are just `.md` files in the vault), generating images, and using plugin tools.

> **Reading attachments on API engines arrived in 0.43.1.** Before that, `javis_read_file` could only see inside the brain, while files you dragged or pasted into the chat landed in `.staging` outside it, so API engines reported an error and told you to copy the file into the brain folder. Now that tool accepts the path of a freshly attached file too. It is still limited to that attachment folder and still read-only: writing stays locked to the brain, and a chatbot talking to your customers cannot see these files.

> **Queueing Kanban work from API engines arrived in 0.17.1.** Before that the only route was `POST /kanban/task`, which requires Bash and curl, so only Claude Code and Codex could do it, even though the documentation promised every brain could. The `javis_task` tool through the hub now makes that promise true.

In short: **capability lives in Javis, not in the model.** The three CLI engines (**Claude Code** on a Claude plan, **Codex** on a ChatGPT plan, **Antigravity CLI** on a Google plan) use the subscription you already pay for and can additionally run shell commands; the six API providers need only an API key and do everything else, orchestration, loops and skills included. Agents in a Workflow can also pick a model per provider, see [Agents & Workflows](07-agents-and-workflows.md).

## Where to find it in Javis

1. Open the Javis dashboard (port `7777` by default).
2. In the left sidebar, open the **Connections** group and click **Models**.
3. The **Cloud Model** tab shows 2 blocks in order: **◆ Usage order** ("signed-in providers, the top card is MAIN") and **◆ Background model** ("loops · Kanban tasks · reminders · self-learning"). At the bottom is a **＋ Connect another provider (N)** button, which reveals the providers not yet connected. Since 0.406.0, when no provider is signed in yet (a first visit), this button moves to the **top** with the provider list already open. Each block has an (i) button next to its name for a short explanation.

> **The Models page was slimmed down in 0.351.0.** Before that it had 4 blocks (**◆ Main Model**, **◆ Providers**, **◆ Background model**, **◆ Reasoning**) plus a Telegram model box. Main Model and Providers are now merged into **Usage order**, the global Reasoning level is replaced by an **Effort** chip on each card, and Telegram follows MAIN (see [Telegram](11-telegram.md) to pin a model for a single conversation with `/model`).

## The ten available providers

The table below lists the available providers. **Connected** providers sit in the **Usage order** block, in the order you set. Providers **not connected** are hidden to reduce clutter: they wait behind the **＋ Connect another provider (N)** button at the bottom of the page (N is how many are waiting), and pressing it shows their cards with the usual sign-in form or key field. Once connected, a provider joins the **end** of the Usage order.

| Provider (on-screen label) | Connection type | Notes |
|---|---|---|
| **Claude Code** | Claude Code sign-in, no key needed | Full MCP/skills/shell. Usually the default MAIN card |
| **OpenAI OAuth (ChatGPT)** | Device code (ChatGPT plan sign-in) | Runs through Codex, wires the Connections store through the hub and uses skills through the router |
| **xAI Grok Build CLI** | Sign in **on the Models page itself** (device code), no key needed | Uses your existing **SuperGrok / X Premium+** plan. Runs through the `grok` binary. Full MCP/skills/shell, and can resume a conversation thread. It is the **only CLI card that can sign in while Javis runs on a VPS**, see [B1a](#b1a-connecting-grok-build-cli-using-a-supergrok--x-premium-plan) |
| **Google Antigravity CLI** | Type `agy` **once in a terminal**, no key needed | Google's designated replacement for Gemini CLI. Runs through the `agy` binary. Full MCP/skills/shell, and can pick **exactly the Antigravity IDE model lineup** (non-Google models included) |
| **OpenRouter** | Paste an API key | Many models in one place, MCP + file tools + skills through the hub |
| **Anthropic (API)** | Paste an API key | MCP + file tools + skills through the hub (since 0.9) |
| **OpenAI (ChatGPT API)** | Paste an API key | MCP + file tools + skills through the hub |
| **Google Gemini (API)** | Paste an API key | MCP + file tools + skills through the hub |
| **Groq (API)** | Paste an API key | MCP + file tools + skills through the hub. Very fast inference, well suited as the background model. This key is also what enables **voice commands on Telegram and Zalo** (Whisper turning speech into text), see [Telegram](11-telegram.md) and [Zalo Bot channel](26-zalo-bot-channel.md); wiring the key is enough, you need not switch the main model to Groq |
| **DeepSeek (API)** | Paste an API key from platform.deepseek.com | MCP + file tools + skills through the hub. Models `deepseek-flash` (cheap, takes images) and `deepseek-v4-pro`. With thinking depth set to **Off** DeepSeek answers directly; turned on, it thinks first, and if an older conversation does not fit that mode Javis answers in normal mode with a one-line notice |
| **Ollama Cloud** | Paste an API key from ollama.com | MCP + file tools + skills through the hub. Large open-source models (gpt-oss, qwen3-coder, deepseek) running on Ollama's servers |

Each provider card shows **● Connected** or **○ Not connected**, the number of available models, and a type label next to the name: **MCP/skills** (Claude Code), **Device code** (ChatGPT), **Javis MCP** (API providers). In the Usage order the top card carries a **MAIN** label and the cards after it read **Fallback 1**, **Fallback 2**... (see section D).

> Before 0.9.270 the API providers were labelled **chat**, which made people think they could only chat. Wrong: they call the Connections store, read and write the brain and run skills exactly like the two CLI engines. The label is now **Javis MCP**, which is accurate.

## How to use it (step by step)

### A. Connecting Claude Code (default)

This is the default engine. It can use every tool, skill and memory, plus run shell commands. It is not mandatory: if you have no Claude plan, skip this and go straight to section B (ChatGPT) or C (API keys), where Javis has the same functionality minus shell commands.

1. Open **Models** and find the **Claude Code** card (while it is not signed in, it sits behind the **＋ Connect another provider** button at the bottom of the page).
2. If you are not signed in, the card reads **○ Not signed in** with two buttons: **Sign into Claude** and **↻ Re-check**. If the machine running Javis has no `claude` command, the card reads **○ Claude Code not installed**, shows one install box (Docker build: update Javis; manual install: one command to copy) and offers only **↻ Re-check**.
3. Click **Sign into Claude**. Javis shows "**1)** Open this link to sign into claude.ai" with the link.
4. Open that link and sign into your claude.ai account.
5. If the page shows **a code**, paste it into the "paste code (if any)" field and click **Send code**. Some flows need no code: Javis waits and re-checks every 3 seconds, and the card updates once connected. After 5 minutes it reports a timeout and asks you to retry.
6. When done, the card switches to **● Connected** with your email and plan.

The **↻ Re-check** button only appears while signed out, for when you just signed in from a terminal and want Javis to look again. Once connected, the card has just one **Disconnect** button.

This works on a headless VPS too. If you prefer the command line, run `claude auth login --claudeai` in a terminal.

### B. Connecting ChatGPT with a subscription

Use your ChatGPT Plus/Pro plan instead of an API key. This runs through Codex, and Javis pushes your connections (a sales POS, for example) into Codex so ChatGPT can call tools too.

While disconnected, the **OpenAI OAuth (ChatGPT)** card has **two** buttons for two sign-in routes:

**Route 1, the "Sign into ChatGPT" button (device code, right for most people):**

1. Click **Sign into ChatGPT**. Javis opens OpenAI's verification page and shows a line like "Open &lt;link&gt; · enter code **XXXX-XXXX**, waiting…".
2. On the page that opened, enter that code.
3. Javis waits and checks automatically. On success it shows **✓ Connected!** and the card switches to **● Connected** with the account plan.
4. Javis waits about 16 minutes before giving up with "Expired, try again"; click **Sign into ChatGPT** again for a fresh code.

**Route 2, the "Through the browser" button (when your workspace BLOCKS device codes):**

Some ChatGPT workspaces disable the device code route, and the first button reports an error. Nothing is broken; use this instead:

1. Click **Through the browser**. Javis opens the ChatGPT sign-in page in a new tab.
2. After signing in, the browser jumps to a **localhost** address and will most likely **fail to load the page, which is normal**, because Javis does not actually open that port.
3. **Copy the whole address bar** (it looks like `http://localhost:1455/auth/callback?code=…`), paste it into the field in Javis and click **Confirm**.
4. Javis extracts the code from that URL and exchanges it for a token. On success it shows **✓ Connected!**.

Because it only needs a pasted URL, this route also works when Javis runs on a VPS and the browser is on your machine.

Once connected, the ChatGPT card joins the end of the **Usage order**. To chat with it, drag the card to the top (or press **⇅ Swap**) so it becomes MAIN, then pick a model with the model chip on the card (see section D).

To disconnect: click **Disconnect** on the card. ChatGPT leaves the Usage order; if it was MAIN, the next card becomes MAIN so chat does not break.

Note: this is an experimental channel (running Codex underneath). For maximum stability, use Claude Code or OpenRouter.

### B1a. Connecting Grok Build CLI (using a SuperGrok / X Premium+ plan)

This is the **xAI** route on the plan you already pay for, rather than buying a separate API key. The big difference from the two Google CLI cards: **you finish the sign-in on the Models page**, even when Javis runs on a browserless VPS.

1. Install the CLI once on the machine running Javis:
   - Linux/macOS: `curl -fsSL https://x.ai/cli/install.sh | bash`
   - Windows PowerShell: `irm https://x.ai/cli/install.ps1 | iex`
   - Docker edition (from 0.85.1): **skip this step**, Javis installs it by itself at startup. While it does, the card says "Javis is installing"; click **Check again** about a minute later.
2. Open **Models**, press **＋ Connect another provider** at the bottom of the page, find the **xAI Grok Build CLI** card and click **Sign in**. It shows a link and a code. Open that link on your machine (a phone works too), enter the code and confirm. The card switches to **● Signed in** with nothing else to click.
3. The newly signed-in card joins the end of the **Usage order**. Drag it to the top (or press **⇅ Swap**) so it becomes MAIN, then pick a model with the model chip on the card.

**Which plan you need:** Grok Build comes with **SuperGrok** or **X Premium+**. With only an `XAI_API_KEY` the CLI technically runs, but Grok Build access is tied to the PLAN rather than the key, so a card reporting *"the signed-in account has no Grok Build access"* is a plan issue, not a configuration error. Click **Re-check** to be sure: that button runs a real chat turn rather than just inspecting files.

**Running 24/7 in the background on a personal plan:** xAI has not spelled this out, so the risk mirrors the warning given for the Anthropic plan. To be safe, point the background model at an API provider.

A few things worth knowing:

- **Javis's tools are wired into `<brain>/.grok/config.toml`**, section `[mcp_servers.javis]`. Grok reads its configuration by **working directory**, and Javis always runs it with the brain root as the working directory, so each brain gets its own hub and Javis **never touches your personal `~/.grok/config.toml`**. A 10-second check: click **Re-check** on the card; it rewrites the configuration, **rereads that same file** and reports *Javis tools wired* / *Javis tools not wired* / *the connection hub is off*.
- **Your `config.toml` is not clobbered.** Javis preserves every other section (`[models]`, `[tools]`...). And if the file has a syntax error Javis cannot parse, it **does not overwrite it**: running without tools beats destroying your configuration, and the card then says the tools are not wired rather than showing a false green.
- **It does resume the CLI conversation thread** (unlike the Antigravity card). `grok` generates its own session id and emits it in the event stream, and Javis only reads that id back rather than inventing one, so there is no saving a wrong id and later attaching to a thread that does not exist. When a thread grows past the threshold, Javis opens a new one and primes it from the saved history.
- **Javis MEASURES the installed CLI's flags rather than guessing.** Before each turn it asks `grok --help` (cached 5 minutes) and only passes flags the binary declares. An older build missing a flag loses exactly that feature instead of breaking the whole turn with "unknown flag".
- **The prompt goes through a file, not the command line** (`--prompt-file`), for the same reason as the Antigravity card: Windows caps a command line at 32767 characters and Javis's system prompt already exceeds 36,000.
- The model list is asked of the CLI rather than kept as a hand-written table, so xAI renaming models does not make the picker stale.
- **Javis disables the CLI's auto-updater** on every turn (the `--no-auto-update` flag where the CLI has it, plus `GROK_DISABLE_AUTOUPDATER=1` always). The reason: Javis runs `grok` headless on a VPS and inside containers, and letting it download a new build mid-turn either prints extra text into the result stream and corrupts the answer, or writes to a read-only location and dies. To let it self-update, set `GROK_DISABLE_AUTOUPDATER=0` yourself; Javis respects your value. Upgrading by hand always works: `grok update`.
- A turn running too long is cut at **900 seconds**; change it with the `JAVIS_GROK_TIMEOUT` environment variable. If the binary lives somewhere unusual, point at it with `JAVIS_GROK_BIN`.

### B1b. Connecting Antigravity CLI (using your Google plan)

This is the route **Google designated** after cutting Gemini CLI off from personal accounts (2026-06-18), and Javis removed the Gemini CLI engine entirely in 0.50.0. The big advantage: you can pick **exactly the model lineup present in the Antigravity IDE**, non-Google models included.

1. Install the CLI once on the machine running Javis:
   - Linux/macOS: `curl -fsSL https://antigravity.google/cli/install.sh | bash`
   - Windows PowerShell: `irm https://antigravity.google/cli/install.ps1 | iex`
   - Docker edition (from 0.85.1): **skip this step**, Javis installs it by itself at startup. While it does, the card says "Javis is installing"; click **Check again** about a minute later.
2. Type `agy` once **in a terminal on the machine running Javis** (the **Code** page inside Javis is the safest spot - it runs as the exact user Javis runs as). A desktop with a screen opens a browser. A server with no screen (VPS, Docker - including Docker on your own Mac) prints a link instead: open it in a browser on your machine, sign into Google, and the browser then jumps to an `http://localhost:...` address that **fails to load, which is the right step** - copy that whole address from the URL bar and paste it back into the terminal, then Enter. The session lives in the operating system keyring, so this is a one-time step.

   > Why the manual paste: `agy` collects the code through a loopback port on the machine running it, and your browser sits on another machine. Since 0.55.46 the Javis terminal declares itself a remote session (`SSH_CONNECTION`) so `agy` asks where to paste instead of waiting in silence. If your `agy` is older and never asks, open a second terminal session and run `curl "<the localhost address you copied>"`. Unusual setups (X11 forwarding, a desktop with a screen) can turn this off with `JAVIS_TERMINAL_REMOTE=0`.
3. Return to **Models**, press **＋ Connect another provider** at the bottom of the page, find the **Google Antigravity CLI** card and click **Re-check** (it runs a real chat turn). The card switches to **● Signed in**.
4. The newly signed-in card joins the end of the **Usage order**. Drag it to the top (or press **⇅ Swap**) so it becomes MAIN, then pick a model with the model chip on the card.

The model list **asks `agy models` directly** rather than using a hand-written table, so you see exactly the models your account is granted, and Google renaming models does not make the picker stale. A new model only appears once `agy` itself is on a build that knows it, so since 0.137.0 Javis runs `agy update` once a day, Docker included (turn it off with the environment variable `JAVIS_AGY_AUTO_UPDATE=0`). If `agy` is up to date and a model is still missing, your Google account has not been granted that model.

A few things worth knowing up front, to avoid confusion:

- **Sign-in happens in the terminal; the dashboard has no button** (since 0.32.2). Version 0.30.0 once built an in-page sign-in flow: Javis opened `agy` in a pseudo-terminal and played postman between it and your browser. It worked on Linux, but what appeared on the page was a terminal box you could not click into, so you still ended up opening a real terminal; and Windows has no pseudo-terminal, so it never worked there at all. `agy` users are developers with a terminal already open, so one command beats a half-finished UI flow. In exchange, Javis holds nobody's token: it lives in the OS keyring.
- **Read-only mode is lighter here.** On Grok Build, `suggest` maps straight to `--deny` flags so the CLI itself blocks. `agy` has no equivalent, so Javis tightens it with `--sandbox` plus instructions in the system prompt. The money/order/publishing guard still sits in the MCP Hub as it does for every engine.
- **`auto` mode does NOT pass `--sandbox`** (since 0.59.44). Measured on agy 1.2.7: `--sandbox` together with `--dangerously-skip-permissions` makes agy's shell tool run as a background task that agy itself kills 5 seconds after leaving print mode, so auto-mode Kanban/Loop work could not list directories or write files, with no error line anywhere. Dropping the flag loses no protection because the outside-action guard lives in the MCP Hub.
- **It does not resume the CLI conversation thread.** Each turn opens a new thread primed from the saved history, so **no context is lost** but it costs more tokens.
- Javis does not install `agy` during setup (unlike the three npm engines): Google's installer is a downloaded script that runs directly, so it is left to you to run when you want.
- **On Windows the prompt no longer goes through the command line** (since 0.33.1, fixed further in 0.33.2). Windows caps a command line at 32767 characters, and Javis's system prompt on an empty brain already exceeds 36,000, meaning this brain used to be completely dead on Windows, with an error message blaming "the conversation is too long" so no number of new chats escaped it.
- **Javis MEASURES how your `agy` build accepts a prompt rather than guessing.** This lesson was paid for twice: version 0.33.1 inferred the syntax from the official documentation (CHANGELOG 1.1.1 says `agy` reads stdin when the prompt is not passed as a flag) and sent `--print ""`, and the real `agy` returned `Error: empty prompt` because it validates the flag value before ever looking at stdin. The documentation was right in principle and wrong in syntax. Now, on the first run Javis tries three ways of feeding stdin with a tiny prompt carrying a unique marker, uses whichever echoes the marker back, and remembers it for later. If none work, it writes the context to a file and tells the model to read it; if the model cannot read it either, it says so plainly rather than quietly answering without the rules.

- **Where Javis's tools are wired, and why there** (fixed in 0.43.0). This was wrong in three consecutive builds without any of them exposing it, because this kind of breakage has no error message: `agy` still ran and still answered fluently, it simply had not a single Javis tool, no MCP, no Kanban, no skills. Two mistakes stacked:
  - **The wrong field name.** Javis wrote `httpUrl`, which is Gemini CLI's schema (a removed engine) copied over. `agy` reads `serverUrl` (Google's migration document says outright that the `url` field was renamed to `serverUrl`). An entry with no field it understands has no address, and it is skipped silently.
  - **The wrong location.** Javis wrote into the brain. `agy` loads MCP from the **HOME-level** configuration: `~/.gemini/config/mcp_config.json` (current, shared with Antigravity 2.0/IDE) and `~/.gemini/antigravity-cli/mcp_config.json` (the old path). The workspace level `<brain>/.agents/mcp_config.json` genuinely exists in the documentation, but issue #60 in the `antigravity-cli` repository itself records that the CLI **finds and then ignores** `mcpServers` there. Javis now writes both levels: HOME so it works today, workspace so any build that fixes that issue gets per-brain isolation automatically.

  The consequence to know: the HOME file is **yours** and shared with the Antigravity IDE, so the IDE will see Javis's tools too; and two brains running `agy` at once means the later one overwrites the earlier. To keep Javis out of HOME, set `JAVIS_AGY_MCP_HOME=0` (leaving only the workspace path, which means only builds that fixed issue #60). To point at another file, set `JAVIS_AGY_MCP_CONFIG=/path/to/mcp_config.json`. If your `agy` build rejects the configuration over an unknown key, set `JAVIS_AGY_MCP_KEY=serverUrl` (or `=url` for older 1.0.x builds) so Javis writes exactly one key.

  **A 10-second self-check:** open **Models**, the **Google Antigravity CLI** card, and click **Re-check**. It rewrites the configuration, rereads that file, and reports one of three things: *Javis tools wired*, *Javis tools not wired*, or *the connection hub is off*. To see the file itself: `cat ~/.gemini/config/mcp_config.json`, which must contain an entry named `javis` with a `serverUrl` pointing at `/hub/mcp`.

- **Vietnamese accents no longer break in transit** (since 0.33.6). The old symptom: the word "gồm" arriving as `g<?><?>m`, each 3-byte Vietnamese character becoming exactly 3 `<?>` marks. That is the signature of a reader chopping the pipe mid-character and decoding each fragment separately. Javis's own side was measured and ruled out (its reader uses incremental decoding, so a byte split mid-character still reassembles correctly), so the break is in `agy`'s reader. Javis cannot patch the CLI, but it can adjust where it places its own boundaries: it now feeds the prompt in chunks ending exactly on character boundaries, so however the other side reads, nothing breaks. If text still comes back with broken characters, Javis switches to the file route and retries once; if that still breaks, it says plainly that the fault is inside the CLI.

- **A model that already carries its own thinking level gets no separate Reasoning depth** (since 0.55.55). `agy models` returns names like `gemini-3.8-flash-medium`, so picking the model *is* picking the thinking level, and `agy` refuses to run if it is handed one again: `invalid model selection ... conflicts with --effort=high`, exit code 1, and the whole chat turn is lost rather than merely degraded. Javis now recognises those names, drops the redundant flag, and turns your chosen depth into a hint inside the prompt instead. If some build of `agy` refuses for another reason, Javis reads that error and reruns the turn immediately without the flag.

**If you still hit errors on Windows**, set the environment variable `JAVIS_AGY_PROMPT_DAI=file` to force the file route, and please report back with the error `agy` printed.

### C. Connecting a provider with an API key (OpenRouter / Anthropic API / OpenAI API / Gemini / Groq / DeepSeek)

1. Open **Models**, press **＋ Connect another provider** at the bottom of the page and find the provider card.
2. Paste the API key into the field (labelled "Paste an API key to connect").
3. Click **Connect**.
4. The card switches to **● Connected** with a model count and joins the end of the **Usage order**. To chat with it, drag the card to the top (or press **⇅ Swap**) so it becomes MAIN, then pick a model with the model chip on the card.

Ollama Cloud connects exactly the same way, with a key from ollama.com.

**Several API keys per provider (since 0.351.0).** An API provider's card in the Usage order (OpenRouter, Anthropic API, OpenAI API, Gemini API, Groq, DeepSeek, Ollama Cloud) shows a numbered list of keys 1, 2, 3...:

- Each row shows its number, the key's name, the last 4 characters of the key and a status: **Ready**, **Off**, or **Out of quota, back at HH:MM**.
- Reorder keys with the up/down arrows or by dragging the row. The **⋯** button at the end of the row offers **Turn off** / **Turn on**, **Change key** (paste the new key, then **Save**) and **Remove**.
- **＋ Add a key**: give it a recognisable name (for example "Project B key"), paste the key and click **Save**. A new key goes to the end of the list.
- Javis uses keys **top to bottom**: key 1 until it runs out of quota, then key 2, skipping a resting key straight away; only when every key of this provider is used up does it move to the next card. Once key 1 recovers, it is used first again.
- The key running right now is highlighted: green **Chat uses this**, purple **Background uses this**.
- The card's status line sums it up, for example "Connected · 3 model · 2/2 keys usable".
- Removing the last key disconnects that provider: Javis asks first ("It is the last key: this provider leaves the usage order."), and once you agree the card leaves the Usage order; if it was MAIN, the next card becomes MAIN.

Providers where you enter your own address (OpenAI Compatible, Anthropic Compatible, Ollama Local) keep their single address and key form as before (see C1 and G).

Where to get a key:

- **OpenRouter**: openrouter.ai (one key reaching many models from many vendors).
- **Anthropic (API)**: console.anthropic.com.
- **OpenAI (ChatGPT API)**: platform.openai.com.
- **Google Gemini (API)**: a Gemini API key from aistudio.google.com.

### C1. Connecting an Anthropic Compatible gateway (a key bought from a reseller)

Use this when you bought a Claude key (or another model) from a reseller that offers an **Anthropic-standard endpoint**. Many resellers offer both an OpenAI endpoint and an Anthropic one, and often say the Anthropic one is more stable with Claude. The "anthropic" endpoints of DeepSeek, Kimi and MiniMax connect the same way. Available from 0.254.0.

**Get 3 things from the seller** (for the ANTHROPIC endpoint, not the OpenAI one):

- **Base URL**: the address the seller gives for `ANTHROPIC_BASE_URL`, for example `https://api.seller.com` or `https://api.seller.com/anthropic`. Pasting it with `/v1` or `/v1/messages` at the end is fine, Javis trims it.
- **API key**: the string the seller issued, usually starting with `sk-`.
- **Model name**: for example `claude-sonnet-4-6`. Ask the seller which models your plan includes and copy the names exactly.

**Connect:**

1. Open **Models**, choose the **Cloud Model** tab, press **＋ Connect another provider** at the bottom of the page and find the **Anthropic Compatible** card.
2. Fill the 3 boxes from top to bottom: Base URL, model names (separate several with commas), API key.
3. Click **Connect**. Javis sends one very short test message to the seller first; on success the card shows **● Connected** with a model count.
4. Make it the main model as in section D: the **Anthropic Compatible** card has just joined the end of the Usage order, so drag it to the top (or press **⇅ Swap**) and pick the model name with the model chip on the card. Send a test message; a small line under the reply reading "Anthropic Compatible · model-name" means it went the right way.

Javis only saves when the check succeeds, so an error means nothing was saved. The model name box is needed because most such gateways do not list their models, so Javis cannot know which ones the seller has. When a gateway does list them, Javis adds them too.

**Errors when clicking Connect:**

| Message | Meaning | What to do |
|---|---|---|
| Invalid API key (HTTP 401) or (HTTP 403) | The key is wrong, expired or blocked | Copy the key again (no extra spaces), or ask the seller for a new one |
| This gateway does not list its models | No model name was entered | Enter the model name the seller gave you and click Connect again |
| .../v1/messages not found (HTTP 404) | The Base URL is wrong | Ask the seller for the Anthropic endpoint address; the usual mistake is using the OpenAI one |
| The gateway returned HTTP 400 for model ... | Usually a wrong model name, or a model your plan lacks | Check the spelling, or ask the seller for the exact name |
| Could not reach ... | The machine running Javis cannot reach that address | Check the Base URL and the network, or ask the seller whether the endpoint is up |

If chat later reports **429** or **529**, the seller is overloaded or you have used up your quota: wait a moment and retry, or ask the seller about your plan's limits.

**Good to know:**

- Change the key: enter the new key in the API key box and click **Save**. Leaving the key box empty keeps the old key.
- Add or remove models: edit the model name box and click **Save**.
- Switching to a different Base URL requires entering the key again: Javis never sends a saved key to a new address.
- Stop using it: click **Disconnect** (clears the address, key and model names). The card leaves the Usage order; if it was MAIN, the next card becomes MAIN.
- Javis sends the key both ways (`x-api-key` and `Bearer`), so it works whichever one the seller reads.
- This gateway gets MCP, reading and writing the brain, skills, agents, background work and chatbots like the other API engines. Like every API engine it cannot run shell commands (see "The four things API engines lack").

### D. Usage order: choosing MAIN and fallbacks

The **◆ Usage order** block at the top of the Cloud Model tab holds only the providers that are **signed in / connected**, as cards in the order they are used:

- **The top card is MAIN** (labelled **MAIN**): this is your chat model.
- The cards after it read **Fallback 1**, **Fallback 2**... When MAIN is out of quota, or fails before doing anything, chat moves to the next card. A fallback card carrying chat right now shows a green **IN USE** badge.
- **Once a step has run, a failure does not switch.** An engine that already called a tool (sent a message, posted an article, created an order...) and then fails makes Javis stop and report, rather than run that step again on another provider, so nothing gets sent or posted twice.
- Falling back only changes the route of that one turn; it **does not change** your saved order or models.

**Changing the order:**

- **Drag a card**: on a computer, hold the mouse anywhere on the card's head and drag. On a phone, hold the 6-dot handle at the head of the card, or press and hold the card for about a third of a second, then drag.
- Or press the **⇅ Swap** button between two neighbouring cards to swap them.

Whichever card reaches the top becomes MAIN immediately, with nothing to save.

**Each card's model and Effort.** Every card has two chips exactly like the ones under the chat composer:

- **Model chip** (green dot, model name, ▾): opens a list of that provider's models only, with a search box at the top. The first row, **default**, means the provider's default model; when Javis knows which model that is, its name follows in brackets, for example **default (llama-3.3-70b-versatile)**. A plan card (Claude Code, ChatGPT, Grok, Antigravity) with no model set runs whatever the CLI picks for your plan, shown as **CLI default (picked by your plan)**. The list comes from the provider itself, so a renamed model shows up right away.
- **Effort chip** (level, ▾): opens a 6-step slider **Off**, **Light**, **Medium**, **High**, **Extra**, **Ultra** (see section F).

Each card remembers its own model and Effort, so reordering never loses any card's choice. MAIN's Effort is the level shown on the chat composer's Effort chip.

**How it ties to the chat composer.** The composer works as before: picking a model on the model chip under the chat pins it for that session and also changes the main model. Picking a model from **another provider** there moves that provider's card **to the top** as MAIN; the other cards keep their order and the old MAIN becomes Fallback 1. The composer's model list now **shows connected providers only**.

**Plan provider cards** (Claude Code, ChatGPT, Grok Build, Antigravity) keep their sign-in controls inside the card: the **Runs on** choice (your signed-in plan or an Anthropic API key) and the **↻ Update Claude Code** button on the Claude card, **Re-check**, **Disconnect** and so on, as in sections A, B, B1a and B1b. Since 0.353.0 the ChatGPT, Grok Build and Claude Code cards accept several accounts (see section D1), while Antigravity stays at one account; API provider cards accept several keys (see section C).

With no provider signed in yet, the block says "No provider is signed in yet. Press Connect another provider below."

Telegram follows MAIN too: changing MAIN on the web changes your Telegram conversations with it, except a conversation you pinned yourself with `/model` (see [Telegram](11-telegram.md)).

### D1. Several accounts on one plan (from 0.353.0)

The cards of three plan providers, **ChatGPT (Codex)**, **Grok Build** and **Claude Code**, accept several accounts. When one account is out of quota, Javis carries on with the next account of the same plan before moving to a fallback card.

**Account 1** is the sign-in the machine already has, done with the existing controls at the top of the card as in sections A, B and B1a. Nothing about it changes.

**Adding an account.** When the card is signed in and sits in the Usage order, an **＋ Add an account** button appears under the sign-in controls:

1. Press **＋ Add an account** and type a name for the account (for example "Pro plan 2" or "Max 200 plan").
2. Read the gentle warning: "Several accounts on one plan carry a lock risk, though Javis has no reported case. If it happens, please tell the developer through Issues on Javis's GitHub."
3. Press **Get the sign-in link**, open the link on any device, and sign in with the account you want to add.
   - **ChatGPT** and **Grok Build**: the card shows a link plus a code. Once you sign in it finishes on its own: the page checks every 3 seconds, for up to 15 minutes.
   - **Claude Code**: the card shows a link. After signing in, paste the code shown back into the box on the card and press **Confirm**.
4. To stop a sign-in that has not finished, press **Cancel**.

**The Accounts list.** With 2 or more accounts the card shows an **Accounts** block with an (i) button:

- Each row is numbered 1, 2, 3... with its state: **Signed in**, **Not signed in**, **Off** or **Out of quota, back at HH:MM**.
- The account carrying the work has a green **Chat uses this** or a purple **Background uses this** label.
- Reorder with the up / down arrows, or drag the row.
- The **⋯** button at the end of a row: **Turn off** / **Turn on**; accounts other than account 1 also get **Sign in again** and **Remove**. Removing deletes that account's sign-in folder on this machine. Account 1 cannot be removed here.
- The card's status line adds "x/y accounts usable".

**How they take turns:**

- Top to bottom: an account that reports out of quota rests until its reset time and the next one runs; once it is back it is used first again.
- All accounts of a card are used before the next card of the Usage order. The card only counts as out of quota when none of its accounts can run.
- The same goes for chat (web and Telegram) and background work (each account is its own fallback link).

**Underneath.** Each extra account has its own sign-in folder on the machine (under the Javis state folder, `accounts/<id>/codex`, `accounts/<id>/grok` or `accounts/<id>/claude`), and the CLI runs pointed at it (`CODEX_HOME`, `GROK_HOME`, `CLAUDE_CONFIG_DIR`). Javis copies account 1's settings into it (the Codex config and the Javis hub profile, Grok's `config.toml`, Claude's `settings.json`); sign-ins are never copied.

**Limits to know:**

- Switching account mid-conversation starts a fresh CLI thread for that turn, and Javis reloads the history.
- Usage meters, image generation, voice and the ChatGPT paths that do not use the Codex CLI still use account 1.
- Antigravity stays at one account (its token is in the OS keyring).
- Claude Code on an Anthropic API key has no account list.
- On macOS, a Claude account counts as signed in once Javis saw the sign-in finish (the token lives in the Keychain).

### D2. Running out of quota during a chat turn (from 0.354.0)

When the route that is running (an account or a key) reports it is out of quota **before writing a single word or calling a tool**, Javis runs the same question again right away on the next route: the next account or key of the same card first, then the next card in the usage order. You do not have to send it again.

- A quiet line shows in the chat, for example "Using ChatGPT because Claude Code is out of quota." or "Using ChatGPT (account 2) because account 1 is out of quota.", and the new route's answer appears below it as usual.
- At most 3 route changes per question. With no route left, Javis reports the quota and schedules the automatic rerun as before.
- **Out of quota halfway** (part of the answer already written): the answer stops there, with a **Run again now** card. Tapping it asks the same question again on a route that still has quota, and the half answer is replaced by the new one. Javis never reruns this case by itself.
- **Out of quota after a tool call**: Javis stops and reports, and does not rerun on another route, so nothing gets sent or posted twice.
- Telegram changes route the same way, with the "Using..." line in the status message. A customer chatbot does not: it always runs the model of the Agent it points to.
- Changing route does not touch your saved order or models. The next turn starts from MAIN again, unless MAIN is still resting.

### E. Choosing the background model

The **◆ Background model** block decides which model runs what Javis does while you are away: **loops · Kanban work · reminders · self-learning · source ingestion**. This is usually the quietest quota burner, so picking a cheap model here saves visibly.

1. The **◆ Background model** block sits right under the Usage order. The large orange line is the model name, the smaller line under it is the provider. Next to it are the background work's own **Effort** chip and a **Change model ▾** button.
2. Click **Change model ▾**. On a computer, the two-column picker (provider | model) opens, titled **BACKGROUND MODEL**. On a phone (screen up to 600px wide), it opens a list like the chat composer's model chip: a search box at the top, provider names in capitals that open or collapse when tapped, and a ✓ on the current model. Both **list connected providers only**.
3. Pick a provider, then a model.
4. Adjust the **Effort** chip next to it if you want background work to think deeper or run faster.

There is no **Back to default** button any more (removed in 0.351.0). To return to a provider's default model, open **Change model ▾** and pick that provider's **default** row.

A few things to know:

- **The background model does not follow MAIN.** The first time (a new install, or an upgrade where it was never set) Javis picks the provider's default setup: its default model and that model's default Effort. After that the background model **stays fixed** until you change it; dragging another card up to MAIN does not drag the background model along.
- **Every provider you connected is selectable**, not just Claude: Claude Code, ChatGPT/Codex, OpenRouter, OpenAI, Gemini, Anthropic API... Choosing another provider makes background work run on that provider's plan or key rather than eating Claude quota.
- **Out of quota, it follows the Usage order (since 0.350.0, tied to the Usage order since 0.351.0).** Background work runs on the background model first; when that model is out of quota it moves through **Fallback 1, Fallback 2...** and uses **MAIN last**, each on its provider's default setup (not the model you picked for chat). A provider with several API keys tries each key before moving on, and a plan card with several accounts tries each account first too (see section D1). Javis never slips in a provider you have not connected.
- **The page only speaks up when needed.** The chain above is not shown all the time. Only when the background model is out of quota does a line appear, for example "Haiku 5.5 is out of quota, background work runs on ChatGPT · GPT-5.5 for now." If the background model's provider is not connected, a warning reads "This provider is not connected, background work starts from Fallback 1." When nothing can run, it says "No account can run background work right now."
- **Nothing is done twice.** An engine that already used a tool (sent a message, posted an article, created an order...) and then broke stops the job with an error instead of running it again on another engine.
- **Tools differ between routes.** Claude Code and Codex read and write brain files directly. API models (OpenRouter, OpenAI, Gemini, Anthropic API) read and write through Javis's vault tools and **cannot run shell commands**, so they suit read-summarise-write-a-note work; leave any background job needing shell commands on Claude.
- On the API route, the file-writing tool locks itself while a loop is in `suggest` mode, exactly as it does on Claude.

### E1. Which model runs where (lookup table)

Javis has three places to set a model, and the most common question is "which one wins". The order: **the Agent's model** (the Model field in the assistant's settings) beats **the main model**, while **the background model** only applies to background routes.

| Where you are | The model that actually runs |
|---|---|
| Ordinary chat on the dashboard / Telegram | The MAIN card of the Usage order, falling back to Fallback 1, 2... when it is out of quota (or the web session's own pin, or the pin of exactly the Telegram conversation where you typed `/model`) |
| Chatting with an assistant on the Partners page | That assistant's model; left on **Default**, the main model |
| A **Chatbot** answering outside customers | The model of the assistant the bot points to; left on **Default**, the main model |
| A step in a workflow | The model of the assistant at that step; left on **Default**, the **background model** |
| Loops, Kanban work, reminders, self-learning, source ingestion | The background model |

If the provider an assistant picked has its key removed, Javis falls back to the main model rather than leaving the assistant or bot dead silent.

The **Model** field in the assistant's settings uses the same picker as the model bar under the chat: type to search, and providers without an API key still appear with a lock, clicking which takes you to the Models page to unlock them. (The picker in the chat composer itself now lists connected providers only.)

### F. Setting the thinking level (Effort)

Turn it up to make the model think harder before answering: more accurate, but slower and more expensive.

1. On a provider card in **◆ Usage order**, click the **Effort** chip (for background work, click the Effort chip in the **◆ Background model** block).
2. Slide to one of 6 steps: **Off**, **Light**, **Medium**, **High**, **Extra**, **Ultra**.

Each card remembers its own level together with its model. MAIN's Effort is the level shown on the chat composer's Effort chip; changing either one changes the other. An assistant (agent) with its own level keeps it.

> **The global Reasoning box was removed in 0.351.0.** Before that the **◆ Reasoning** block had 4 buttons, Off, Low, Medium, High, applied to every engine at once. Now each provider has its own level, so moving MAIN to another provider no longer carries over a level that does not suit the new model.

A few things to know:

- **Off** means no thinking parameter is sent. A model that must think runs at its own default level; a model with no thinking runs as Off.
- A model lacking the exact step you chose runs at the **nearest step** it has (on a tie, the lower one). Your saved choice is not altered, so switching back to the old model returns to the old level.

It applies differently per engine:

- **Claude API / OpenRouter**: adaptive thinking plus the matching effort level.
- **OpenAI**: only applies to the o-series (o1/o3/o4) and gpt-5; ordinary models ignore it.
- **Gemini**: only applies to 2.5 and newer (and models with "thinking" in the name). Older models are not sent the parameter, to avoid errors.
- **Claude Code**: inserts thinking hints into the question (from think to ultrathink as depth increases).

### G. Local Model: Ollama on your machine or your VPS

The **Local Model** tab (next to Cloud Model on the Models page) connects Javis to an Ollama you run yourself: open-source models, offline, no usage caps. The matching provider in the model picker is **Ollama (Local)**, distinct from **Ollama Cloud** on the Cloud tab (the paid service through ollama.com).

**Javis running directly on your machine (Windows/Mac/Linux):** install Ollama with the command the tab shows, then click Connect with the prefilled `http://127.0.0.1:11434`. Done.

**Javis running in Docker/on a VPS:** three steps, done over SSH on the real host, not the terminal inside Javis (that terminal lives in the container, has no root, and anything installed there is wiped on the next update).

1. Install Ollama on the host: `curl -fsSL https://ollama.com/install.sh | sh`.
2. Make Ollama listen on the Docker bridge address. The Local tab already detected the address and generated the command; just copy it. It writes a systemd override with `OLLAMA_HOST=<bridge address>:11434` and restarts. Binding to that exact address means only containers on that host can call it, nothing is exposed to the internet, and no firewall rule is needed. Only when Javis cannot detect the address does the command fall back to `0.0.0.0`, and then you must block port 11434 in the firewall, because Ollama has no password.
3. Click **Connect** (the address is prefilled).

Still not connecting after three steps? On the host run `ss -ltnp | grep 11434`: no output means Ollama is not running (`systemctl status ollama`); a line with `127.0.0.1` means step 2 did not take effect.

**Choosing a model:** the Recommended section is ordered by machine capability. A machine without a GPU (an ordinary VPS) should prefer **instruct** builds (for example `qwen3:4b-instruct`), which answer directly. Long-thinking builds (plain qwen3, deepseek-r1) on a CPU can spend minutes just "thinking" before the first character appears, and the tab says so on each card. Once downloaded, click **Use as main model** right there in the installed list: the **Ollama (Local)** card moves to the top of the Usage order as MAIN, and the model picker under the chat updates immediately.

## What the Claude engine runs on underneath

Since 0.9.37, Javis's Claude engine runs **exclusively through the Claude Agent SDK** (Anthropic's own library). The old branch that invoked the `claude` command as a separate process was removed. Two things users need to know:

- **The machine still MUST have the `claude` CLI.** The SDK calls that CLI underneath, and both sign-in and native MCP go through it. Without the CLI the Claude Code card reports an error and the engine does not run, see [Getting started & first-run setup](01-getting-started.md).
- **Tool permissions in background sessions are enforced PER CALL.** When a loop or workflow runs in safe background mode, every attempt to call a tool outside the allow list is refused on the spot and logged, rather than only being declared at startup. The refusal message says explicitly that this is the background session's permission guard and **not** a broken MCP connection, so seeing that line is no reason to go re-authenticate a connector.

## How Claude Code (full tools) differs from a direct API

This is the easiest thing to get wrong, so be clear about it:

- **MAIN = Claude Code**: the strongest option. Native file reads and writes, shell commands, MCP calls, native skills, automatic loops, session resume. The mode that gets the most out of Javis OS.
- **MAIN = ChatGPT OAuth (Codex)**: it can call the entire Connections store (the hub pushes them into Codex, local connections such as Zalo included), has Codex's own file tools, and uses skills through the router (Javis injects the skill list into the system prompt plus the `javis_use_skill` tool; Codex runs with cwd=brain so it reads `skills/<slug>/SKILL.md` directly). Codex additionally loads its OWN MCP registry (servers you registered with `codex mcp add`, visible in the collapsed "◆ Claude Code and Codex built-in connections" block on the Connections page), the same way the Claude engine uses Claude Code's native MCPs.
- **MAIN = OpenRouter / OpenAI (API) / Anthropic (API) / Gemini**: since version 0.9 all four call the Connections store through tool-call rounds, with vault file read/write tools and skill activation (`javis_use_skill`). **Background work also runs on these providers** (see section E). The remaining differences from Claude Code: no shell tool (Bash), no WebFetch, and no CLI session resume.

The practical conclusion: for the fullest "working" Javis, keep the **Claude Code** card on top (MAIN). Move to an API provider when you want to try a specific model from another vendor, or to push background work onto a cheaper plan and spare your Claude quota.

## Token saving applies to subscriptions too

The **Token saving mode** block at the top of the **Usage** page (System group) makes Javis send less text per turn: loading only the memory relevant to the question, and loading skills on demand rather than listing them all.

Since version 0.12.4 this works for **all three brain kinds**, not only API-key brains:

| Brain kind | Why it is still worth enabling |
|---|---|
| API key (OpenRouter, OpenAI, Anthropic, Gemini, Groq) | Fewer tokens is less money, and it avoids per-minute token limit errors |
| Claude plan (Claude Code) | Fewer tokens means more turns inside each 5-hour window |
| ChatGPT plan (Codex) | The same |

Opening the page shows a **Current brain** block: which kind the current brain is, which saving measures apply to it, and which do not and why. Some measures deliberately only run on API-key brains, for example resending conversation history, because Claude Code and Codex already remember their own thread and sending it again sends it twice.

**When a subscription runs out of turns**, chat follows the **Usage order** you set: when MAIN is out of quota, that turn runs on the Fallback 1 card (with that card's model and Effort), then Fallback 2... A plan card with several accounts uses all of them before moving on (see section D1). Javis only moves to providers **you connected and placed there yourself**, because moving spends another account's quota and can cost real money. To keep a provider from ever stepping in, disconnect it, or for an API provider **Turn off** its keys. Falling back changes nothing saved: the next turn tries MAIN first again. When no card can run, Javis says so plainly: which plan ran out and roughly how long until it resets. Note that this kind of limit counts **turns per hour** rather than length, so shortening questions does not help.

Since 0.55.44, when the provider states the **reset time**, a card **"Auto-resume at HH:MM"** appears under that notice: at that time Javis asks the same question again and answers in the same conversation, even with the tab closed or the phone screen off (the job lives on the server). The card carries an **"Auto-continue when limits reset"** checkbox (off means it only shows the time; the choice is remembered for next time) and a **"Retry now"** button. Sending a new message while waiting cancels the schedule. Javis only schedules when it knows the reset time, at most 3 times per question, never more than a day ahead; a server restart drops pending schedules, and the limit notice stays in the conversation so you can hit "Resend".

## Switching model quickly

On the Models page: drag the provider you want to the top of the **Usage order** (or press **⇅ Swap**) and pick a model with the model chip on that card. The top card becomes MAIN immediately. The **◆ Background model** block has its own **Change model ▾** (opening **BACKGROUND MODEL**), and the **Effort** chip on each card applies as soon as you pick a level.

You do not even need the Models page: pick a model on the model chip under the chat. Picking a model from another provider moves that provider's card to the top of the Usage order.

## Switching model mid-conversation

Changing model while chatting keeps the **conversation continuous**: the new model reads everything said before and continues, without asking you to start over. You can switch as many times as you like within one conversation.

Underneath, Javis does this two ways depending on the brain kind:

- **API-key brains** (OpenRouter, OpenAI, Anthropic, Gemini, Groq, Ollama) remember nothing themselves, so Javis resends the conversation history every turn.
- **Subscription brains** (Claude Code, ChatGPT/Codex, Grok Build) keep their own thread, and Javis reattaches to it because that is cheaper. But as soon as another brain answers a turn, that thread is **missing exactly that turn**. So Javis drops every other brain's thread link after each turn; when you return to that brain, it rebuilds the context from saved history rather than continuing a thread with a hole in it.

Put briefly: switching back and forth stays continuous, and only the first turn after a switch costs a little extra because the history is resent.

Up to and including 0.42.1 there was a bug in exactly this place: only ChatGPT/Codex threads were unlinked, while other thread-keeping engines were not, so returning to one of them made it talk as if the turns in between had never happened.

## Quick reference: buttons and states

| Button / text | Where | What it means |
|---|---|---|
| **MAIN** | Top card of the Usage order | This provider is chat's main model |
| **Fallback 1**, **Fallback 2**... | The following cards of the Usage order | The order chat moves down when the card above is out of quota |
| **IN USE** (green) | A fallback card | Chat is temporarily running on this card because the one above cannot run |
| **⇅ Swap** | Between two cards in the Usage order | Swap those two cards |
| 6-dot handle | Head of a card (phone) | Hold to drag a card or a key row |
| Model chip / **Effort** chip | On each card | Pick the model (the **default** row = the provider's default model) / pick that card's thinking level |
| **● Connected** / **○ Not connected** | Provider card | The state, with the number of available models (a multi-key provider adds something like "2/2 keys usable") |
| **Ready** / **Off** / **Out of quota, back at HH:MM** | Key row on an API provider card | Each key's state |
| **Chat uses this** (green) / **Background uses this** (purple) | Key row on an API provider card | The key carrying chat / background work right now |
| **⋯** | End of a key row | Turn off / Turn on, Change key, Remove |
| **＋ Add a key** | API provider card | Add a named key, at the end of the list |
| **＋ Add an account** | ChatGPT, Grok Build, Claude Code card (signed in) | Add another account to the same plan (see section D1) |
| **Get the sign-in link** | The add-account box | Get the link (ChatGPT, Grok with a code) to sign in the account being added; for Claude Code paste the code and press **Confirm** |
| **Accounts** list | Plan provider card with 2 or more accounts | Used top to bottom; states **Signed in** / **Not signed in** / **Off** / **Out of quota, back at HH:MM**; **⋯** for Turn off / Turn on, Sign in again, Remove |
| **＋ Connect another provider (N)** | Bottom of the page | Show the N providers not yet connected, to sign in / paste a key |
| **○ Not signed in** | Claude Code card | Claude Code is not signed in on this machine |
| **○ Claude Code not installed** | Claude Code card | The machine running Javis has no `claude` command; follow the install box on the card |
| **Sign into Claude** | Claude Code card | Start the link-based sign-in flow |
| **↻ Re-check** | Claude Code card (only while signed out) | Re-query the sign-in state |
| **Sign into ChatGPT** | OpenAI OAuth card | Sign in with a device code |
| **Through the browser** | OpenAI OAuth card | The fallback when the workspace blocks device codes |
| **Connect** | API provider card not yet connected | Save the first key; the provider joins the end of the Usage order |
| **Save** / **Disconnect** | OpenAI Compatible, Anthropic Compatible card | Save the address, key, models / clear everything and leave the Usage order |
| **Change model ▾** | Background model | Open the background model picker (**BACKGROUND MODEL** on a computer, a composer-style list on a phone) |

## Tips

- If you just want Javis to remember and work smoothly, keep the Claude Code card on top (MAIN). The other providers are for specific needs.
- Put at least one fallback card under MAIN (an API key provider, for example) so chat keeps going when your main plan runs out instead of waiting.
- If you have several API keys for the same provider, add them all to that card with **＋ Add a key**: Javis uses them in turn and skips any that are resting.
- If you have more than one ChatGPT, Grok or Claude account, add them to that card with **＋ Add an account** (see section D1): when the account above runs out, the one below carries on before another provider is needed. Read the lock-risk warning before adding one.
- Set the **Background model** to something cheap so loops, Kanban work, reminders, self-learning and ingestion do not eat your main plan's quota. To see what is burning most, look at [Usage: tokens & cost](23-usage-and-cost.md).
- Push the **Effort** chip to Medium or High for hard questions (analysis, strategy); leave it on Off or Light for quick questions to avoid waiting.
- OpenRouter is convenient if you want to try many models from many vendors with one key.
- To let ChatGPT call your sales tools: wire the connection on the [Connections & business data](09-connections-and-business-data.md) page first, and Javis pushes it into Codex.

## Common problems

- **The Claude Code card reports that the Claude CLI is not installed**: the machine has no Claude Code CLI. The Claude engine requires it (the SDK calls that CLI underneath). Install it and click **↻ Re-check**. See [Getting started & first-run setup](01-getting-started.md).
- **ChatGPT sign-in produces no code, or errors immediately**: your workspace may block device codes. Use the **Through the browser** button in section B.
- **ChatGPT sign-in reports "Expired, try again"**: Javis waits about 16 minutes before giving up. Click **Sign into ChatGPT** again for a new code.
- **The model chip opens an empty list**: that provider could not return its model list yet, or has no models. Click **Re-check** or reconnect that provider, or add models in `settings.json` (under `model.catalog`). See [.env configuration](16-env-configuration.md).
- **A provider is missing from the Usage order**: it is not connected (or Claude Code is not signed in). Press **＋ Connect another provider** at the bottom of the page.
- **The model returns nothing**: retry, or pick another model with the model chip on the MAIN card. With the Anthropic API, the message also carries the reason (for example hitting max_tokens: say "continue" and the model writes on).
- **The Connections page shows a yellow line saying the Main Model does not support tool calling**: since 0.9.270 **no bundled provider** triggers that line any more. Before that, Google Gemini was missing from the list and was misreported even though MCP through the hub worked normally. The yellow line now only guards unknown providers. Claude Code, OpenRouter, OpenAI, Anthropic API, Gemini and Groq all show GREEN cards; ChatGPT OAuth has its own green card noting that it runs through the Codex CLI.

- **A red banner reading "⚠ the claude brain lost its sign-in" on a machine that never had Claude**: fixed in 0.9.270. The brain status lights kept state in RAM with nobody clearing it, so a red light lit while Claude was the Main Model hung around forever after you switched to OpenRouter. The lights now only count brains you ACTUALLY selected (the Main Model, plus the background model when its provider is explicit), and clear as soon as you switch provider rather than waiting for the 10-minute sweep.
- **Disconnecting (or removing the last key of) the provider that is MAIN**: that provider leaves the Usage order and the next card becomes MAIN so chat does not break. That is deliberate, not a fault.
- **Chat answers from a provider other than MAIN**: MAIN is out of quota (or every one of its keys is resting), so that turn ran on a fallback card, which carries the **IN USE** badge. The next turn tries MAIN first again.
- **ChatGPT OAuth reports that the Codex CLI is not installed**: this channel needs the Codex CLI on the machine. Since 0.28.8 both npm CLI engines (Claude Code, Codex) are installed during Javis setup, in the Docker image, `install.sh` and `setup.bat`, so this usually means an older installation and **updating Javis** once is enough. Installing by hand also works: `npm i -g @openai/codex`.

## Related

- [Connections & business data](09-connections-and-business-data.md) - wiring data sources and tools shared by every engine.
- [Usage: tokens & cost](23-usage-and-cost.md) - seeing which model and which work burns most.
- [Agents & Workflows](07-agents-and-workflows.md) - picking a model per agent.
- [Getting started & first-run setup](01-getting-started.md) - installing the Claude Code CLI and the Codex CLI.

Still stuck? See [Troubleshooting & FAQ](17-troubleshooting.md).
