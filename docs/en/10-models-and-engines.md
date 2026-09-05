# Models & engines

*[Tiếng Việt](../10-models-va-engine.md) · **English***

The **Models** page is where you pick Javis's "brain": which engine and model answers you, signing into AI providers, choosing a cheap model for background work, and enabling deeper reasoning. This page decides how smart Javis is and whose quota it spends.

If you are just starting, read [Getting started & first-run setup](01-getting-started.md) first. To attach external tools to Javis, see [Connections & business data](09-connections-and-business-data.md).

## What this feature is

Javis can run on many different "engines" (AI providers). You pick 1 as the **Main Model** (the conversation model), and optionally also:

- **Background model**: a cheaper model for what Javis runs while you are away: loops, Kanban work, reminders, self-learning, source ingestion.
- **Reasoning**: how hard the model thinks before answering.

The most important thing to understand: **changing model does NOT cost Javis any capability.** Every provider gets the same toolkit through Javis's connection hub (MCP Hub): calling the Connections you wired, reading and writing files in the brain, running skills, queueing Kanban work (the `javis_task` tool), creating agents/workflows/loops/reminders (the `javis_schedule` tool).

| Route | Provider | Javis MCP · brain file tools · skills | Shell commands (Bash) |
|---|---|---|---|
| Through **Claude Code** | Anthropic OAuth (Claude Code) | Yes, native MCP + native skills | **Yes** |
| Through **Codex** | OpenAI OAuth (ChatGPT) | Yes, MCP through the hub (local connections such as Zalo/Webcake included) + Codex's OWN MCP registry (servers you added with `codex mcp add`) + skills through the router (`javis_use_skill` / reading `skills/` files) | **Yes** |
| Through **Antigravity CLI** | Google Antigravity CLI (`agy`) | Yes, MCP through the hub (written into `~/.gemini/config/mcp_config.json`, see B1b) + skills through the router | **Yes** |
| **Direct API** | OpenRouter | Yes, MCP through the hub + vault file tools + skills through the router | No |
| **Direct API** | OpenAI (API) | Yes, as above | No |
| **Direct API** | Anthropic (API) | Yes, as above | No |
| **Direct API** | Google Gemini (API) | Yes, as above (since 0.9.270 the Connections page no longer misreports it) | No |
| **Direct API** | Groq (API) | Yes, as above | No |
| **Direct API** | Ollama Cloud | Yes, as above | No |

### The four things API engines lack

Before 0.17.1 this page said the "**only** difference is running shell commands". Neat, but wrong. The real list:

- **Shell commands (Bash)**, running commands on the server.
- **WebFetch and WebSearch**, opening an arbitrary URL to read it and searching the web. An API engine wanting outside data must go through a connected MCP.
- **Task**, spawning sub-agents running in parallel within one turn.
- **Resuming an earlier CLI session**; API engines rebuild the context every turn.

Two more practical limits of API engines: at most **8 tool-call rounds** per turn (it stops and says so beyond that), and when a turn **calls tools**, the answer arrives as one block at the end rather than streaming word by word (each round is a separate request).

Beyond those, every capability is identical. Specifically: calling every connected MCP, reading and writing files in the brain, reading a file you just attached or pasted into the chat, running skills, queueing Kanban work, creating loops and reminders, creating agents/workflows/skills (they are just `.md` files in the vault), generating images, and using plugin tools.

> **Reading attachments on API engines arrived in 0.43.1.** Before that, `javis_read_file` could only see inside the brain, while files you dragged or pasted into the chat landed in `.staging` outside it, so API engines reported an error and told you to copy the file into the brain folder. Now that tool accepts the path of a freshly attached file too. It is still limited to that attachment folder and still read-only: writing stays locked to the brain, and a chatbot talking to your customers cannot see these files.

> **Queueing Kanban work from API engines arrived in 0.17.1.** Before that the only route was `POST /kanban/task`, which requires Bash and curl, so only Claude Code and Codex could do it, even though the documentation promised every brain could. The `javis_task` tool through the hub now makes that promise true.

In short: **capability lives in Javis, not in the model.** The three CLI engines (**Claude Code** on a Claude plan, **Codex** on a ChatGPT plan, **Antigravity CLI** on a Google plan) use the subscription you already pay for and can additionally run shell commands; the six API providers need only an API key and do everything else, orchestration, loops and skills included. Agents in a Workflow can also pick a model per provider, see [Agents & Workflows](07-agents-and-workflows.md).

## Where to find it in Javis

1. Open the Javis dashboard (port `7777` by default).
2. In the left sidebar, open the **Connections** group and click **Models**.
3. The Models page shows 4 blocks in order: **◆ Main Model** ("the conversation model"), **◆ Providers** ("sign into / connect model providers"), **◆ Background model** ("loops · Kanban work · reminders · self-learning · source ingestion"), **◆ Reasoning** ("thinking depth when answering").

## The ten available providers

The **Providers** block lists 10 providers. **Connected ones are sorted first**, unconnected ones below; within each group the original order below is preserved. That way a machine with a few providers wired shows them immediately without scrolling.

| Provider (on-screen label) | Connection type | Notes |
|---|---|---|
| **Anthropic OAuth (Claude Code)** | Claude Code sign-in, no key needed | Full MCP/skills/shell. The default Main Model |
| **OpenAI OAuth (ChatGPT)** | Device code (ChatGPT plan sign-in) | Runs through Codex, wires the Connections store through the hub and uses skills through the router |
| **xAI Grok Build CLI** | Sign in **on the Models page itself** (device code), no key needed | Uses your existing **SuperGrok / X Premium+** plan. Runs through the `grok` binary. Full MCP/skills/shell, and can resume a conversation thread. It is the **only CLI card that can sign in while Javis runs on a VPS**, see [B1a](#b1a-connecting-grok-build-cli-using-a-supergrok--x-premium-plan) |
| **Google Antigravity CLI** | Type `agy` **once in a terminal**, no key needed | Google's designated replacement for Gemini CLI. Runs through the `agy` binary. Full MCP/skills/shell, and can pick **exactly the Antigravity IDE model lineup** (non-Google models included) |
| **OpenRouter** | Paste an API key | Many models in one place, MCP + file tools + skills through the hub |
| **Anthropic (API)** | Paste an API key | MCP + file tools + skills through the hub (since 0.9) |
| **OpenAI (ChatGPT API)** | Paste an API key | MCP + file tools + skills through the hub |
| **Google Gemini (API)** | Paste an API key | MCP + file tools + skills through the hub |
| **Groq (API)** | Paste an API key | MCP + file tools + skills through the hub. Very fast inference, well suited as the background model. This key is also what enables **voice commands on Telegram and Zalo** (Whisper turning speech into text), see [Telegram](11-telegram.md) and [Zalo Bot channel](26-zalo-bot-channel.md); wiring the key is enough, you need not switch the main model to Groq |
| **Ollama Cloud** | Paste an API key from ollama.com | MCP + file tools + skills through the hub. Large open-source models (gpt-oss, qwen3-coder, deepseek) running on Ollama's servers |

Each provider card shows **● Connected** or **○ Not connected**, the number of available models, and a type label next to the name: **MCP/skills** (Claude Code), **Device code** (ChatGPT), **Javis MCP** (API providers). The card currently serving as Main Model carries a **MAIN** label.

> Before 0.9.270 the API providers were labelled **chat**, which made people think they could only chat. Wrong: they call the Connections store, read and write the brain and run skills exactly like the two CLI engines. The label is now **Javis MCP**, which is accurate.

## How to use it (step by step)

### A. Connecting Claude Code (default)

This is the default engine. It can use every tool, skill and memory, plus run shell commands. It is not mandatory: if you have no Claude plan, skip this and go straight to section B (ChatGPT) or C (API keys), where Javis has the same functionality minus shell commands.

1. Open **Models** and find the **Anthropic OAuth (Claude Code)** card.
2. If you are not signed in, the card reads **○ Not signed in** with two buttons: **Sign into Claude** and **↻ Re-check**.
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

To disconnect: click **Disconnect** on the card. If ChatGPT was the Main Model when you disconnect, Javis switches the Main Model back to Claude Code so chat does not break.

Note: this is an experimental channel (running Codex underneath). For maximum stability, use Claude Code or OpenRouter.

### B1a. Connecting Grok Build CLI (using a SuperGrok / X Premium+ plan)

This is the **xAI** route on the plan you already pay for, rather than buying a separate API key. The big difference from the two Google CLI cards: **you finish the sign-in on the Models page**, even when Javis runs on a browserless VPS.

1. Install the CLI once on the machine running Javis:
   - Linux/macOS: `curl -fsSL https://x.ai/cli/install.sh | bash`
   - Windows PowerShell: `irm https://x.ai/cli/install.ps1 | iex`
2. Open **Models**, the **xAI Grok Build CLI** card, and click **Sign in**. It shows a link and a code. Open that link on your machine (a phone works too), enter the code and confirm. The card switches to **● Signed in** with nothing else to click.
3. Click **Change model ▾** in the Main Model block, pick this provider and pick a model.

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
2. Type `agy` once **in a terminal on the machine running Javis**. On a machine with a screen it opens a browser; over SSH it prints a link, which you open on your machine and sign into Google. The session lives in the operating system keyring, so this is a one-time step.
3. Return to **Models**, the **Google Antigravity CLI** card, and click **Re-check** (it runs a real chat turn). The card switches to **● Signed in**.
4. Click **Change model ▾** in the Main Model block, pick this provider and pick a model.

The model list **asks `agy models` directly** rather than using a hand-written table, so you see exactly the models your account is granted, and Google renaming models does not make the picker stale.

A few things worth knowing up front, to avoid confusion:

- **Sign-in happens in the terminal; the dashboard has no button** (since 0.32.2). Version 0.30.0 once built an in-page sign-in flow: Javis opened `agy` in a pseudo-terminal and played postman between it and your browser. It worked on Linux, but what appeared on the page was a terminal box you could not click into, so you still ended up opening a real terminal; and Windows has no pseudo-terminal, so it never worked there at all. `agy` users are developers with a terminal already open, so one command beats a half-finished UI flow. In exchange, Javis holds nobody's token: it lives in the OS keyring.
- **Read-only mode is lighter here.** On Grok Build, `suggest` maps straight to `--deny` flags so the CLI itself blocks. `agy` has no equivalent, so Javis tightens it with `--sandbox` plus instructions in the system prompt. The money/order/publishing guard still sits in the MCP Hub as it does for every engine.
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

**If you still hit errors on Windows**, set the environment variable `JAVIS_AGY_PROMPT_DAI=file` to force the file route, and please report back with the error `agy` printed.

### C. Connecting a provider with an API key (OpenRouter / Anthropic API / OpenAI API / Gemini / Groq)

1. Open **Models** and find the provider card.
2. Paste the API key into the field (labelled "paste an API key to connect").
3. Click **Connect**.
4. The card switches to **● Connected** with a model count.

To change the key later: enter a new one and click **Change key** (the field then reads "change key" with the last 4 characters of the old one). To disconnect: click **Disconnect** (this deletes the key). If that provider was the Main Model when disconnected, Javis switches back to Claude Code.

Where to get a key:

- **OpenRouter**: openrouter.ai (one key reaching many models from many vendors).
- **Anthropic (API)**: console.anthropic.com.
- **OpenAI (ChatGPT API)**: platform.openai.com.
- **Google Gemini (API)**: a Gemini API key from aistudio.google.com.

### D. Setting the Main Model

1. In the **◆ Main Model** block at the top of the Models page you see the current model and provider.
2. Click **Change model ▾**.
3. The **SET MAIN MODEL** dialog opens, with a subtitle reading "current: &lt;model&gt; · &lt;provider&gt;":
   - Left column: the provider list. Unconnected providers are marked **⚠ needs connecting**; the one in use is marked **IN USE**.
   - Right column: the models of the selected provider.
   - A **Filter providers / models…** box at the top for quick searching (it filters both columns at once).
4. Click a provider on the left, then a model on the right. The current model is labelled **IN USE**.
5. Click **Switch** to apply, or **Cancel** (or ✕) to close.

The model list is loaded live from the provider itself (labelled **· live**). If the network fails, Javis uses a fallback list (labelled **· catalog**); while loading it shows **· loading…**. Your choice is saved and applies to new chat sessions.

The Main Model block also carries a line about the engine in use, stating the route and the real limits: "Through Claude Code, Javis MCP + skills + loops + shell commands", "Through Codex, Javis MCP + skills + loops + shell commands", or "Direct API, Javis MCP + skills + loops (no shell commands)". Before 0.9.270 that last line read "plain chat (no MCP)", which was wrong and has been removed.

### E. Choosing the background model

The **◆ Background model** block decides which model runs what Javis does while you are away: **loops · Kanban work · reminders · self-learning · source ingestion**. This is usually the quietest quota burner, so picking a cheap model here saves visibly.

1. Scroll to **◆ Background model**. The large line says what is in use: unchanged, it reads **Claude Code default** with the smaller line "no model override, using the default".
2. Click **Change model ▾**. The dialog is identical to the Main Model picker but titled **BACKGROUND MODEL**, footed with "Background work: loops · Kanban work · reminders · self-learning · source ingestion", and its apply button is named **Select**.
3. Pick a provider on the left, a model on the right, then click **Select**.
4. To revert: click **Back to default** (this button only appears once you set a specific model).

A few things to know:

- **Every provider you connected is selectable**, not just Claude: Claude Code, ChatGPT/Codex, OpenRouter, OpenAI, Gemini, Anthropic API. Choosing another provider makes background work run on that provider's plan or key rather than eating Claude quota.
- If you pick a provider that is **not connected**, the block warns that the provider is not connected and that background work will fall back to Claude. Background work does not die, it just does not save you anything.
- **Tools differ between routes.** Claude Code and Codex read and write brain files directly. API models (OpenRouter, OpenAI, Gemini, Anthropic API) read and write through Javis's vault tools and **cannot run shell commands**, so they suit read-summarise-write-a-note work; leave any background job needing shell commands on Claude.
- On the API route, the file-writing tool locks itself while a loop is in `suggest` mode, exactly as it does on Claude.

### F. Setting Reasoning

Turn it up to make the model think harder before answering: more accurate, but slower and more expensive.

1. Scroll to **◆ Reasoning**.
2. Click one of 4 levels: **Off**, **Low**, **Medium**, **High**.

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

**Choosing a model:** the Recommended section is ordered by machine capability. A machine without a GPU (an ordinary VPS) should prefer **instruct** builds (for example `qwen3:4b-instruct`), which answer directly. Long-thinking builds (plain qwen3, deepseek-r1) on a CPU can spend minutes just "thinking" before the first character appears, and the tab says so on each card. Once downloaded, click **Use as main model** right there in the installed list; the model picker under the chat updates immediately.

## What the Claude engine runs on underneath

Since 0.9.37, Javis's Claude engine runs **exclusively through the Claude Agent SDK** (Anthropic's own library). The old branch that invoked the `claude` command as a separate process was removed. Two things users need to know:

- **The machine still MUST have the `claude` CLI.** The SDK calls that CLI underneath, and both sign-in and native MCP go through it. Without the CLI the Claude Code card reports an error and the engine does not run, see [Getting started & first-run setup](01-getting-started.md).
- **Tool permissions in background sessions are enforced PER CALL.** When a loop or workflow runs in safe background mode, every attempt to call a tool outside the allow list is refused on the spot and logged, rather than only being declared at startup. The refusal message says explicitly that this is the background session's permission guard and **not** a broken MCP connection, so seeing that line is no reason to go re-authenticate a connector.

## How Claude Code (full tools) differs from a direct API

This is the easiest thing to get wrong, so be clear about it:

- **Main Model = Claude Code**: the strongest option. Native file reads and writes, shell commands, MCP calls, native skills, automatic loops, session resume. The mode that gets the most out of Javis OS.
- **Main Model = ChatGPT OAuth (Codex)**: it can call the entire Connections store (the hub pushes them into Codex, local connections such as Zalo included), has Codex's own file tools, and uses skills through the router (Javis injects the skill list into the system prompt plus the `javis_use_skill` tool; Codex runs with cwd=brain so it reads `skills/<slug>/SKILL.md` directly). Codex additionally loads its OWN MCP registry (servers you registered with `codex mcp add`, visible in the collapsed "◆ Claude Code and Codex built-in connections" block on the Connections page), the same way the Claude engine uses Claude Code's native MCPs.
- **Main Model = OpenRouter / OpenAI (API) / Anthropic (API) / Gemini**: since version 0.9 all four call the Connections store through tool-call rounds, with vault file read/write tools and skill activation (`javis_use_skill`). **Background work also runs on these providers** (see section E). The remaining differences from Claude Code: no shell tool (Bash), no WebFetch, and no CLI session resume.

The practical conclusion: for the fullest "working" Javis, keep Main on **Claude Code**. Move to an API provider when you want to try a specific model from another vendor, or to push background work onto a cheaper plan and spare your Claude quota.

## Token saving applies to subscriptions too

The **Token saving mode** block at the top of the **Usage** page (System group) makes Javis send less text per turn: loading only the memory relevant to the question, and loading skills on demand rather than listing them all.

Since version 0.12.4 this works for **all three brain kinds**, not only API-key brains:

| Brain kind | Why it is still worth enabling |
|---|---|
| API key (OpenRouter, OpenAI, Anthropic, Gemini, Groq) | Fewer tokens is less money, and it avoids per-minute token limit errors |
| Claude plan (Claude Code) | Fewer tokens means more turns inside each 5-hour window |
| ChatGPT plan (Codex) | The same |

Opening the page shows a **Current brain** block: which kind the current brain is, which saving measures apply to it, and which do not and why. Some measures deliberately only run on API-key brains, for example resending conversation history, because Claude Code and Codex already remember their own thread and sending it again sends it twice.

**When a subscription runs out of turns**, Javis says so plainly: which plan ran out, roughly how long until it resets, and which brains you already have wired to use meanwhile. Javis **does not switch brains for you**, because switching spends another account's quota and can cost real money, so that is your decision (made on this page, with the conversation intact). Note that this kind of limit counts **turns per hour** rather than length, so shortening questions does not help.

## Switching model quickly

You do not have to leave the Models page to change model: click **Change model ▾** in the Main Model block to open **SET MAIN MODEL**, pick a provider and model, then **Switch**. The choice is saved and applies to new chat sessions. The **◆ Background model** block has its own **Change model ▾** (opening **BACKGROUND MODEL**), and the level buttons in **◆ Reasoning** apply immediately on click.

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
| **MAIN** | Corner of a provider card | This provider is the Main Model |
| **● Connected** / **○ Not connected** | Provider card | The state, with the number of available models |
| **○ Not signed in** | Claude Code card | Claude Code is not signed in on this machine |
| **Sign into Claude** | Claude Code card | Start the link-based sign-in flow |
| **↻ Re-check** | Claude Code card (only while signed out) | Re-query the sign-in state |
| **Sign into ChatGPT** | OpenAI OAuth card | Sign in with a device code |
| **Through the browser** | OpenAI OAuth card | The fallback when the workspace blocks device codes |
| **Connect** / **Change key** / **Disconnect** | API provider card | Save a new key / replace the key / delete the key |
| **Change model ▾** | Main Model and Background model | Open the matching model picker |
| **Back to default** | Background model | Return background work to Claude Code's default model |
| **IN USE** | Model picker | The provider or model currently set |
| **⚠ needs connecting** | Model picker, left column | That provider has no key / is not signed in |
| **· live** / **· catalog** | Model picker | The list came from the network / the fallback list |
| **Switch** / **Select** | Model picker footer | Apply to the Main Model / to the background model |

## Tips

- If you just want Javis to remember and work smoothly, do not move Main off Claude Code. The other providers are for specific needs.
- Set the **Background model** to something cheap so loops, Kanban work, reminders, self-learning and ingestion do not eat your main plan's quota. To see what is burning most, look at [Usage: tokens & cost](23-usage-and-cost.md).
- Turn **Reasoning** to Medium or High for hard questions (analysis, strategy); turn it off for quick questions to avoid waiting.
- OpenRouter is convenient if you want to try many models from many vendors with one key.
- To let ChatGPT call your sales tools: wire the connection on the [Connections & business data](09-connections-and-business-data.md) page first, and Javis pushes it into Codex.

## Common problems

- **The Claude Code card reports that the Claude CLI is not installed**: the machine has no Claude Code CLI. The Claude engine requires it (the SDK calls that CLI underneath). Install it and click **↻ Re-check**. See [Getting started & first-run setup](01-getting-started.md).
- **ChatGPT sign-in produces no code, or errors immediately**: your workspace may block device codes. Use the **Through the browser** button in section B.
- **ChatGPT sign-in reports "Expired, try again"**: Javis waits about 16 minutes before giving up. Click **Sign into ChatGPT** again for a new code.
- **A provider is selectable but its model column is empty**: that provider is not connected, or has no models. Reconnect it in the Providers block, or add models in `settings.json` (under `model.catalog`). See [.env configuration](16-env-configuration.md).
- **The model returns nothing**: retry, or pick another model in SET MAIN MODEL. With the Anthropic API, the message also carries the reason (for example hitting max_tokens: say "continue" and the model writes on).
- **The Connections page shows a yellow line saying the Main Model does not support tool calling**: since 0.9.270 **no bundled provider** triggers that line any more. Before that, Google Gemini was missing from the list and was misreported even though MCP through the hub worked normally. The yellow line now only guards unknown providers. Claude Code, OpenRouter, OpenAI, Anthropic API, Gemini and Groq all show GREEN cards; ChatGPT OAuth has its own green card noting that it runs through the Codex CLI.

- **A red banner reading "⚠ the claude brain lost its sign-in" on a machine that never had Claude**: fixed in 0.9.270. The brain status lights kept state in RAM with nobody clearing it, so a red light lit while Claude was the Main Model hung around forever after you switched to OpenRouter. The lights now only count brains you ACTUALLY selected (the Main Model, plus the background model when its provider is explicit), and clear as soon as you switch provider rather than waiting for the 10-minute sweep.
- **Disconnecting the provider that is the Main Model**: Javis switches Main back to Claude Code so chat does not break. That is deliberate, not a fault.
- **ChatGPT OAuth reports that the Codex CLI is not installed**: this channel needs the Codex CLI on the machine. Since 0.28.8 both npm CLI engines (Claude Code, Codex) are installed during Javis setup, in the Docker image, `install.sh` and `setup.bat`, so this usually means an older installation and **updating Javis** once is enough. Installing by hand also works: `npm i -g @openai/codex`.

## Related

- [Connections & business data](09-connections-and-business-data.md) - wiring data sources and tools shared by every engine.
- [Usage: tokens & cost](23-usage-and-cost.md) - seeing which model and which work burns most.
- [Agents & Workflows](07-agents-and-workflows.md) - picking a model per agent.
- [Getting started & first-run setup](01-getting-started.md) - installing the Claude Code CLI and the Codex CLI.

Still stuck? See [Troubleshooting & FAQ](17-troubleshooting.md).
