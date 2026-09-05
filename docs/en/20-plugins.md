# Plugins: adding native tools for every engine

*[Tiếng Việt](../20-plugins.md) · **English***

A plugin is how you add **new tools** to Javis without editing the source: a Python folder dropped in the right place, loaded automatically, and from then on every engine (Claude Code, ChatGPT/Codex, OpenRouter, OpenAI, Anthropic, Gemini) can call that tool.

This page covers reading the plugin list in the dashboard, turning each one on and off, understanding the 11 bundled plugins, and how to install your own with the safety rails you must know before you do.

## What this feature is

A plugin is **one folder** with 2 files:

- `plugin.yaml`: declares the name, slug, description, version, enabled state, minimum permission level, and the lists of tools and hooks.
- `plugin.py`: the Python code, which must have a `register(ctx)` function. Inside it you call `ctx.register_tool(...)` to add a tool, and/or `ctx.register_hook(...)` to add a hook.

A plugin gives Javis two things:

- **A tool**: something an engine can call, for example `javis_now` (asking what time it is in Vietnam) or `javis_generate_image` (creating an image). Plugin tools go through the MCP Hub, so **every engine can use them**, not only Claude Code.
- **A hook**: code that runs **around each tool call**. The current build supports two events: `pre_tool_call` (before the tool runs) and `post_tool_call` (after it finishes). When no plugin registers a hook, Javis wraps nothing at all, so it costs nothing.

Plugin tools **respect Javis's 3 permission levels** exactly like any other tool, so a loop running read-only cannot call a plugin's write tool.

## How a plugin differs from a Skill and an MCP

These three get mixed up often. Tell them apart by asking "what is actually missing":

| What is missing | What to use | What it really is |
|---|---|---|
| Javis does not know **how to do** a kind of work your way | **Skill** | A `SKILL.md` file with instructions. No code runs, it only teaches the AI the right procedure. See [Skills](06-skills.md). |
| You need a **real action** in Python (computation, data transformation, calling a simple API, reading or writing files under custom rules) that nothing else covers | **Plugin** | Real Python code, adding tools and hooks for every engine. |
| You need an **external data source** that already has a server (POS, ads, calendar, email, notes...) | **Connection (MCP)** | Attach the existing server on the Connections page, no code needed. See [Connections and business data](09-connections-and-business-data.md). |

In short: a skill is **know-how**, a plugin is **code that really runs**, an MCP is **an existing data source**. If what you need already has an MCP, do not write a plugin.

## Where to open it in Javis

Open the dashboard (default port 7777), look at the left navigation rail, click the **Capabilities** group to open it, then click **Plugins**. The page header reads **Plugins** with the subtitle "Native tools/hooks for every engine".

Right under the heading are three introductory blocks:

1. A description line: "Plugins add native **tools** (callable by engines) and **hooks** to Javis without touching the core, usable on EVERY engine (Claude Code, Codex, API) through the hub, respecting the 3 permission levels like any other tool."
2. An orange warning box (shown only while it is still locked): "**⚠ Plugins you installed are blocked.** Global and brain plugins run real Python code in the server, so they are OFF by default. To turn them on: set the environment variable `JAVIS_ENABLE_USER_PLUGINS=true` and restart Javis. Bundled plugins keep working normally."
3. A grey signpost line: "Drop a GLOBAL plugin (used by EVERY brain) into `<the real path on your machine>` · each plugin is `plugin.yaml` + `plugin.py`. Or tell Javis in the chat box: 'create a plugin ...'."

The path on the third line is the **real** path on the machine running Javis, so copy it from the screen rather than typing it from the documentation.

Below is the list of plugin cards, ordered by source: Bundled first, then Global, then This brain; within each group they are ordered by name. With no plugins at all, the page reads "No plugins yet. Drop a plugin folder into `<path>` then reload."

## Reading a plugin card

Each plugin is a card. Read it top to bottom:

**First line (left):** the 🧩 icon, the plugin's display name, then the **slug** in small grey type (which is the folder name), then a source label:

| Source label | Meaning | Where it lives |
|---|---|---|
| **Bundled** (green) | A plugin shipped with the app, published by Javis, trusted | `system/plugins/<slug>/` in the install folder |
| **Global** (blue) | A plugin you installed, shared by **every brain** | Javis's state folder, `<JAVIS_STATE_DIR>/plugins/<slug>/` |
| **This brain** (orange) | A plugin you installed, used by **one brain** only | `<brain>/plugins/<slug>/` (an older brain may have `<brain>/Javis/plugins/<slug>/`) |

On a slug collision, the later source wins: a "This brain" plugin named `datetime-vn` replaces the "Bundled" one of the same name.

**First line (right):** the current status (see the table in "Quick reference of buttons and states").

**Description line:** the content of the `description` field in `plugin.yaml`.

**Information line:** joined with middle dots, containing "minimum level: ..." then the version (`v1.0.0`) then the author. For example: "minimum level: read only · v1.0.0 · Javis (bundled)".

**The chip row:** each tool the plugin provides is a chip with a 🔧 icon and the tool name; each hook is a 🪝 chip with the event name. These are exactly the names the engine will call, so to have Javis use a particular tool, mention the name on the chip.

**The button at the bottom of the card:** **Enable** or **Disable** (the label follows the current state).

The card of a plugin that is not running is dimmed. If the plugin errored, the reason appears in red right under the chip row.

## How to use it (step by step)

### Step 1: See which plugins are running

Go to **Capabilities > Plugins**. Look at the status column on the right of each card. Only cards reading **● running** actually expose tools to the engine. A dimmed card is unusable right now.

### Step 2: Enable or disable a plugin

1. Find the card you want to change.
2. Click **Enable** (or **Disable**) at the bottom of the card.
3. The list reloads and the status changes immediately.

For a **Bundled** plugin, Javis does not edit the app's files: your on/off choice is written to a `plugins.json` file in the state folder. That way updating Javis to a new version **does not lose** your choice.

For **Global** and **This brain** plugins, Javis writes `enabled: true/false` straight into that plugin's `plugin.yaml`.

Enabling and disabling takes effect immediately with no restart: Javis refreshes the hub's cache so the tool appears or disappears on the next chat turn, and the brain's capability index `Javis/index.md` is rebuilt too.

The one exception: if you enable a **Global/This brain** plugin while the environment variable is still locked, Javis shows a dialog saying it was enabled in the manifest BUT user-installed plugins only run once `JAVIS_ENABLE_USER_PLUGINS=true` is set and Javis is restarted (protection against running unknown code). The card then switches to **⚠ waiting for env**.

### Step 3: Check that the tool reached the engine

Open the chat box and ask directly, for example "what time is it" (the `datetime-vn` plugin) or "list my Facebook Pages" (the `meta-pages-graph` plugin). Javis knows which plugins are running because the "Running plugins" list with their tool names is placed into the context of every chat turn.

If a tool is blocked by the permission level, the answer contains the error line verbatim, starting with `ERROR: tool '<name>' needs a higher permission level`. If a tool needs a connection you do not have, the error states which page to go to in order to attach it.

## The bundled plugins

These ship with the app (the **Bundled** label). All are on by default except `tool-audit`.

| Name on the card | slug | Tools provided | Minimum level | Default |
|---|---|---|---|---|
| Time and date (VN) | `datetime-vn` | `javis_now`, `javis_date_add` | read only | On |
| Recurring jobs and reminders | `javis-schedule` | `javis_schedule` | write (safe) | On |
| Queue Kanban work | `javis-task` | `javis_task` | write (safe) | On |
| Attach another MCP | `javis-connect` | `javis_add_mcp` | write (safe) | On |
| Create images (ChatGPT) | `image-chatgpt` | `javis_generate_image` | write (safe) | On |
| Read YouTube videos | `youtube-read` | `javis_youtube_read` | read only | On |
| Meta Ads (Graph API) | `meta-ads-graph` | `meta_ads_accounts`, `meta_ads_insights`, `meta_ads_campaigns`, `meta_ads_get` | read only | On |
| Facebook Pages (Graph API) | `meta-pages-graph` | `fb_pages_list`, `fb_page_posts`, `fb_page_comments`, `fb_page_post`, `fb_page_photo`, `fb_page_album`, `fb_page_video`, `fb_page_edit`, `fb_page_delete`, `fb_page_reply` | full power | On |
| Facebook monitoring (Apify) | `fb-monitor-apify` | `fb_monitor` | read only | On |
| Send images and files over Zalo | `zalo-image` | `zalo_send_image` | full power | On |
| Tool usage log | `tool-audit` | `javis_tool_stats` + the `post_tool_call` hook | read only | **Off** |

What each one does:

- **Queue Kanban work**: queue a background job straight from chat (`op=add`) and see how running work is going (`op=list`). Added in 0.17.1. Before that the only route was `POST /kanban/task`, and calling it required running machine commands, so only Claude Code and Codex could do it even though the documentation promised every brain could. This tool calls the in-process queue directly and opens no extra HTTP door. Two hard rails: it **cannot create `full`-level jobs** (the level that spends money, creates orders, sends messages, which you must set yourself on the Work page), and it defaults to `suggest`. Moving columns, cancelling work and approving pending work still happen on the Work page.
- **Attach another MCP**: have Javis attach a new MCP source right from chat, and it **appears on the Connections page** under "Connected" like an account you added by hand, shared by every brain. Before this plugin, Javis had no way to write into the connection store, so all it could do was run `claude mcp add`; that server landed in Claude Code's own configuration where the other six brains could not see it, and on the Connections page it did not sit under "Connected" but fell into the collapsed "Connections already in Claude Code and Codex" section (closed by default), so it looked as if nothing had been added. Three safety rails: the permission level defaults to **read only** (raise it yourself on the Connections page if you want writes); a source that runs a **local command** (stdio) is added **disabled** so you read the command before enabling it; and a service already in the Connections catalogue (Gmail, Calendar, POS...) makes Javis point at the right card rather than spawning a parallel hand-declared copy. If the connection test fails, the entry **stays** on the Connections page with the reason rather than vanishing silently.
- **Send images and files over Zalo**: send an image (one Javis just created, say) or a file with a message over Zalo, from the very account you scanned the QR with on the Connections page. It exists because the standard MCP's `zalo_send_message` tool can only send text, while the library underneath has been able to do more for a long time and 1.6.2 is already the latest release, so waiting on upstream means waiting forever. Only files INSIDE the brain in use can be sent, a deliberate rail, because a sent Zalo message cannot be recalled. Requires Node.js 20+. Details in [Zalo](12-zalo-agent-mcp.md).
- **Time and date (VN)**: tells Javis today's date, the time and the weekday in Vietnam time (UTC+7), and computes relative dates ("in 3 days", "last week"). Pure standard library, no network needed. It is also the simplest example plugin to read when you want to write your own.
- **Recurring jobs and reminders**: lets you create, list and cancel recurring jobs and reminders **right in a chat sentence**, with no YAML typing. Repeating, durable work is written to `Javis/loops/<slug>.md` (editable in Obsidian); one-off reminders or cron schedules go into the reminder store. Details in [Recurring jobs and reminders](08-recurring-jobs.md).
- **Create images (ChatGPT)**: generates images from a description using the **ChatGPT plan** you are signed in to (OAuth), with no OpenAI API key. Images are saved into the brain's `attachments/` then embedded straight into the answer. It requires ChatGPT connected on the **Models** page; without it the tool returns a sentence saying ChatGPT (OAuth) is not connected and telling you to sign in on the Models page and try again.
- **Read YouTube videos**: paste a video link into chat and ask for a summary. The plugin fetches the video's **real subtitles** (the route the YouTube player uses) so Javis reads the dialogue rather than guessing from the title. No API key, no YouTube sign-in, and it works on **every engine**, including API engines that cannot open a URL. When YouTube blocks the server it cycles through six player variants before falling back to yt-dlp, which gets past most robot-suspicion cases. A video with no subtitles, a private video or one YouTube blocks makes the tool state the reason plainly so Javis does not invent anything. A long video that got truncated continues when you ask it to "keep reading". Details in [Chat](02-chat-and-voice.md).
- **Per-chat Zalo rules**: set the behaviour for each Zalo group or customer in words (stay silent, report every message, report on keywords, nudge when a reply is over N minutes late). The rules are written to `Javis/zalo/<slug>.md` so they can be read and edited.
- **Safe Zalo sending**: sends Zalo messages in place of the raw tool. It locks onto the listening account and can only send to chats on the watch list; when a name matches several people it refuses and forces a question back. The two Zalo plugins are shared with [the Zalo channel](12-zalo-agent-mcp.md).
- **Meta Ads (Graph API)**: reads Facebook/Instagram advertising figures (ad accounts, campaigns, performance). **Read only, spends no money.** Requires the "Meta Ads (your own app, Graph API)" connection on the Connections page.
- **Facebook Pages (Graph API)**: manages Pages. Reading the Page list, posts and comments is read-only; posting, uploading photos, albums and videos, editing text, deleting posts and replying to comments are **real, public** actions and need the full-power level. Requires the "Facebook Pages (your own app, Graph API)" connection.
- **Facebook monitoring (Apify)**: monitors **public** Pages and Groups to find heavily shared posts, through the Apify service. Read only, does not touch a personal account, and works on a VPS. Requires pasting an apify.com Personal API token into the "Facebook monitoring (Apify)" connection.
- **Tool usage log**: counts how many times **each** tool is called by the engine (through the `post_tool_call` hook) and lets you see the most-used ones. It is a demonstration of the hook mechanism, so it is off by default; enable it on the Plugins page, chat a few turns that call tools, then ask Javis which tool is used most.

A note about the "Minimum level" column: that is the level declared for the **whole plugin** and what the card shows. Each tool inside still has its own level. For example `meta-pages-graph` says "full power" on the card, but its three post/comment reading tools only need read-only, and only the posting and deleting tools need full power.

## Plugins that come from a Package

Since 0.55.23, a **Package** installed on the **Capabilities > Install store** page can bring plugins along, meaning new tools rather than only connection services. Their cards appear on this page with the source label **From a package**.

They differ from the other three sources in three ways:

- **Enabling, disabling and removing all happen in the Install store**, not here. A plugin travels with its whole package, so toggling it separately only causes confusion. The card on this page has a button that takes you straight there.
- **No `JAVIS_ENABLE_USER_PLUGINS` environment variable needed.** A package goes through the installer, meaning you saw the screen listing every code file before clicking agree. That is the same kind of assurance the environment variable provides, only per package rather than an all-or-nothing switch.
- **The code in the package is locked to its content.** At install time, Javis records a fingerprint of all the code in the package. On every load it recomputes and compares: one byte off and the plugin **does not run**, with the card stating that the code in the package changed since you agreed to install it. To keep using it, reinstall from the Install store to review and confirm again.

A note when editing by hand: opening a package's `plugin.py` in a Windows editor and saving is enough to shift the fingerprint, because many editors change the line endings. That is not a bug, the file content genuinely differs. To modify a plugin, edit it in your own plugin folder rather than inside a package.

A package **may not** carry a plugin whose name collides with one of Javis's bundled plugins. The installer refuses immediately and names the collision, so no package can quietly replace a core tool.

## Removing a plugin from the list entirely

The **Disable** button keeps the card visible; the **Remove** button makes it disappear from the main list. Both make the plugin's tools vanish from every brain, differing only in whether you still intend to use it.

Removing **does not delete the files** in the install. Javis only records the choice in the state folder, so updating Javis does not bring the plugin back, and reinstalling is one click in the **Removed** section at the bottom of the page (collapsed by default).

This applies to **Bundled** plugins shipped with Javis too. It is how you tidy the default set when you do not use one.

## The minimum permission level and run modes

Each plugin tool declares a minimum permission level; each Javis run has a permission ceiling. A tool only runs when the run's ceiling is high enough.

| The tool's minimum (the card label) | Meaning | Which mode it runs in |
|---|---|---|
| `readonly` - "read only" | Only reads or computes, changes nothing | Every mode |
| `safe` - "write (safe)" | Writes files or spends quota | Auto (safe) mode and Full power |
| `full` - "full power" | A real outside action (posting, deleting, sending) | Full power mode only |

The chat box you type into runs at the full level, so all three kinds are callable. Conversely, a [recurring job](08-recurring-jobs.md) set to **Suggest** can only run read-only tools; meeting a higher-level tool it returns `ERROR: tool '<name>' needs a higher permission level (...)` and stops rather than acting recklessly. This is a hard block in code, not an instruction in the prompt, so no model can talk its way past it.

## Installing your own plugin

### Step 1: Choose where to put it

There are two places, depending on whether the plugin should be shared or private:

- **Global** (recommended): `<JAVIS_STATE_DIR>/plugins/<slug>/`. Every brain sees it and every engine can call it. The real path is already shown on the signpost line of the Plugins page, so copy it from there. `JAVIS_STATE_DIR` defaults to the project's `server/` folder; on Docker/VPS it is usually `/data/state`.
- **One brain only**: `<brain>/plugins/<slug>/`. Only that brain can use it. Suitable when the plugin is tightly bound to one brain's data.

`<slug>` is the folder name and must be lowercase ASCII without diacritics, starting with a letter or digit, containing only letters, digits, dots, underscores and hyphens. Get the character set wrong and Javis skips the plugin, reporting "invalid slug".

### Step 2: Write plugin.yaml

```yaml
name: Shipping calculator
slug: tinh-tien-ship
version: 1.0.0
description: Calculates the delivery fee by weight and area using the shop's price table.
author: You
enabled: false            # always create it DISABLED, enable it after re-reading the code
min_mode: readonly        # readonly | safe | full
tools: [tinh_tien_ship]
hooks: []                 # for example: [post_tool_call]
```

The `tools` and `hooks` fields here only exist **to display the chips on the card**. What actually creates the tool is the code in `plugin.py`, so keep these two lists matching the code to avoid confusion.

### Step 3: Write plugin.py

```python
def register(ctx):
    def handler(args, ctx):        # args is a dict; return a string. On failure return "ERROR: ..."
        kg = float((args or {}).get("kg") or 0)
        return f"Shipping fee: {int(kg * 5000)} dong"

    ctx.register_tool(
        name="tinh_tien_ship",
        description="Calculates the delivery fee by weight (kg). Use when a customer asks about shipping.",
        handler=handler,
        min_mode="readonly",
        schema={"type": "object",
                "properties": {"kg": {"type": "number", "description": "Parcel weight"}},
                "required": ["kg"]},
    )
```

A few things to remember while writing:

- A tool name must start with a lowercase letter and contain only lowercase letters, digits and underscores.
- The `description` is what the engine reads to decide **when** to call the tool, so state the situation and the parameters clearly. A vague description leaves the tool sitting unused.
- The handler can be an ordinary or an `async` function. Returning a string is simplest; returning a dict makes Javis convert it to JSON.
- `ctx` provides `ctx.slug`, `ctx.vault_root` (the working brain) and `ctx.data_dir` (a private folder for the plugin's state, which is **not** inside the brain so it does not pollute your notes).
- To make a tool refuse itself when prerequisites are missing (not signed in, no key), pass `check_fn=`, a function returning `None` when ready or an explanatory sentence when not.
- A broken plugin **does not bring Javis down**: every load step, tool call and hook is wrapped, and the error appears only on that plugin's card.

### Step 4: Unlock with the environment variable

Plugins you install are **blocked by default**, even with `enabled: true`. To unlock them:

1. Open the `.env` file in the project root (create it if absent, see [.env configuration](16-env-configuration.md)).
2. Add one line: `JAVIS_ENABLE_USER_PLUGINS=true`
3. Save the file and **restart Javis**.
4. Return to the **Plugins** page: the orange warning box disappears and enabled plugins switch to **● running**.

Accepted values are `1`, `true`, `yes` or `on` (case insensitive). The old name `JAVIS_ENABLE_VAULT_PLUGINS` still works for compatibility, but prefer the new one.

## Safety rails (read before installing an unfamiliar plugin)

This is the most important part of this page.

- **Plugins you install run real Python code, inside Javis's own server process.** They have that process's rights: reading and writing files, calling the network, reading environment variables. That is why Javis **hard-blocks them by default** and only runs them once you set `JAVIS_ENABLE_USER_PLUGINS=true` yourself and restart. This is the rail against someone who can write a folder into the brain being able to run code on your machine.
- **Only unlock once you have read the code** of every plugin in those two folders. The environment variable unlocks **all** user plugins, not one at a time.
- **Bundled plugins (the "Bundled" label) are not subject to this rail** because they ship with the Javis release. They keep working while the environment variable is off.
- **A plugin Javis creates from chat is always disabled** (`enabled: false`) and at the `readonly` level. Javis never enables it for you; you must read the code then click **Enable** yourself.
- **Do not write plugins that perform money, order, messaging or publishing actions.** Those should go through MCP connections and the permission system, where the blocks and logs already exist. A plugin should be `min_mode: readonly` unless you deliberately need otherwise.
- **Do not clone bundled plugins into a brain.** They travel with the app and update themselves; a copy in the brain shadows the original and stops being updated.

## Asking Javis to create a plugin in words

You do not have to type the two files yourself. Open the chat box and say it plainly, for example: "Create me a plugin that calculates shipping by weight, 5 thousand per kilo, rounding up below 1 kilo."

Javis first picks the right kind of capability (if only instructions are needed it writes a skill; if it is an existing data source it advises attaching an MCP), checks for duplicates against what the brain already has, and only then writes the plugin folder. When it finishes it reports the file names and reminds you the plugin is disabled and how to unlock it with the environment variable.

Then you do 3 things yourself: open `plugin.py` and read the code (using the **Files** page if the plugin is inside a brain), set the environment variable if it is not set, then go to **Plugins** and click **Enable**.

## Hooks: running around each tool call

Besides tools, a plugin can register hooks. The current build has two events:

| Event | When it fires | What it receives |
|---|---|---|
| `pre_tool_call` | Just before any tool runs | `tool_name`, `args`, `mode`, `vault_root` |
| `post_tool_call` | Just after a tool finishes | plus `result` |

A hook wraps **every** tool call, MCP tools and core tools included, not only that plugin's tools. Use it for logging, counting, alerting. When no plugin registers a hook, Javis wraps nothing, so there is no performance cost. The `tool-audit` plugin is a working example: enable it and every tool call is counted into a file private to the plugin.

## Quick reference of buttons and states

| What you see | Meaning / action |
|---|---|
| **● running** (green) | The plugin is loaded and its tools are available to the engine |
| **⚠ waiting for env** (orange) | You enabled the plugin but `JAVIS_ENABLE_USER_PLUGINS=true` is not set, or is set but Javis has not been restarted |
| **⚠ error** (red) | The manifest is broken or the code failed to load; the reason appears under the chip row |
| **○ off** (grey) | The plugin is present but disabled, exposing no tools |
| **● enabled (not loaded)** (orange) | A rare state: enabled but not loaded for some other reason. Reload the page, and if it persists check the server log |
| The **Bundled** / **Global** / **This brain** label | The plugin's source (app / the folder shared by every brain / one brain) |
| A **🔧 name** chip | A tool the plugin provides; this is the name the engine will call |
| A **🪝 name** chip | A hook the plugin registers (`pre_tool_call` or `post_tool_call`) |
| "minimum level: read only / write (safe) / full power" | The minimum permission level for the plugin's tools to be allowed to run |
| The **Enable** button | Enables the plugin (the card is off) |
| The **Disable** button | Disables the plugin (the card is on) |
| A dimmed card | The plugin is not running |
| The orange warning box at the top | User plugins are still locked; bundled plugins keep working |

## Tips

- Before deciding to write a plugin, ask again: is what is missing the **know-how** or the **action**? Missing know-how means writing a skill, which is far cheaper and easier to change.
- Read `system/plugins/datetime-vn/plugin.py` as a starting example: it is short, pure standard library, and enough to illustrate a read tool. For a hook example, read `tool-audit`.
- Put plugins in **Global** unless there is a clear reason to bind one to a brain. Global does not depend on the brain, so switching brains keeps it usable.
- If you do not use a plugin, **disable** it rather than deleting the folder, so re-enabling later is one click.
- Disabling unused plugins also shortens the tool list handed to the model, helping it pick the right tool.
- To see what capabilities Javis currently sees (agents, skills, workflows, loops, plugins), open the brain's `Javis/index.md` file through the **Files** page; it is rebuilt every time you enable or disable a plugin.

## Common problems

- **The card reads "⚠ waiting for env":** you have not set `JAVIS_ENABLE_USER_PLUGINS=true`, or set it but have not restarted Javis. The variable is only read at startup.
- **The environment variable is set and it is still blocked:** check that the `.env` file is in the project root, that the line has no leading `#`, and that the value is `true` (or `1`/`yes`/`on`). On Docker, set the variable in the container's Environment section rather than in a file on the host.
- **A newly dropped plugin does not appear on the page:** the folder must be **directly** inside the plugins folder (no extra nesting) and must contain `plugin.py` (or `__init__.py`). Without that, Javis does not consider it a plugin. The folder name must also be a valid slug (lowercase, no diacritics).
- **The card reads "⚠ error" with "plugin.py missing":** the folder has only `plugin.yaml`. Add the code file.
- **The card reads "⚠ error" with "manifest error: ...":** `plugin.yaml` has invalid YAML. Most often a description containing a colon without quotes.
- **The card reads "⚠ error" with "no register(ctx) function":** `plugin.py` has no `register` function, or you named it something else. It must be named exactly `register` and take one parameter.
- **The card reads "⚠ error" with a Python error name (`ModuleNotFoundError`, say):** the plugin code uses a library not installed in Javis's Python environment. Install it into the virtual environment Javis actually runs in, then restart.
- **The plugin is running but the engine does not see the tool:** most likely the tool name **collides** with an existing MCP or core tool. Javis does not let a plugin take a core tool's place, so it skips the colliding tool and writes a line to the server log. Rename the tool in `plugin.py` (a private prefix is the safest approach). Core names that cannot be reused: `javis_connections`, `javis_read_file`, `javis_list_dir`, `javis_write_file`, `javis_use_skill`.
- **The tool returns `ERROR: tool '<name>' needs a higher permission level`:** the run is permission-restricted. If it is a recurring job, raise that job's mode (see [Recurring jobs and reminders](08-recurring-jobs.md)); if it is your own plugin, review the `min_mode` declared in `register_tool`.
- **The tool returns "not connected ...":** the plugin needs a connection you have not attached. Follow the instruction in the error exactly, usually going to the **Connections** page (or **Models** for the image plugin).
- **Clicking Enable reports "plugin not found":** the list on screen is stale compared to disk (you just deleted or renamed the folder). Reload the page.
- **Clicking Enable reports "failed to write the manifest":** Javis cannot write to `plugin.yaml`, usually a folder permission issue or the file being locked by another program. See also [Troubleshooting and FAQ](17-troubleshooting.md).

## Related

- [Skills](06-skills.md) - when what you lack is know-how rather than running code.
- [Connections and business data](09-connections-and-business-data.md) - attaching external data sources; the Meta Ads, Facebook Pages and Apify plugins take their tokens from here.
- [Models and engines](10-models-and-engines.md) - why every engine can call plugin tools.
- [Recurring jobs and reminders](08-recurring-jobs.md) - the three permission levels of background work, and the `javis-schedule` plugin.
- [Zalo Agent MCP](12-zalo-agent-mcp.md) - Zalo now uses the upstream MCP and no longer has its own plugin.
- [.env configuration](16-env-configuration.md) - how to set an environment variable and restart.
- [Agents and Workflows](07-agents-and-workflows.md) - Javis's other kinds of capability.
