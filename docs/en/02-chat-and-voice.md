# Chat & voice

*[Tiếng Việt](../02-tro-chuyen-va-giong-noi.md) · **English***

This is where you spend most of your time with Javis: type or speak, and Javis answers in text while reading the answer aloud. This page covers the whole chat frame, from keyboard shortcuts, slash commands and the buttons under each message to picking a voice and asking Javis to generate images.

If you have not finished the first-run setup, read [Getting started & first-run setup](01-getting-started.md) first.

## What this feature is

One place to work with Javis:

- Type messages like any chat app.
- Speak, and Javis listens then sends automatically when you stop talking.
- Javis answers in text and reads the answer aloud in a Vietnamese voice.
- Attach files or images to a message for Javis to read.
- Javis embeds images, files, diagrams and HTML pages back into its answers so you can view them in place.
- Watch the knowledge globe react to sound (it lights up while listening and while speaking).

Answers are produced by **the engine you selected**, not Claude by default: Claude Code, ChatGPT (Codex), OpenRouter, OpenAI API, Anthropic API or Google Gemini API. The small badge next to the CONVERSATION label shows the engine and model that ACTUALLY ran that turn. Every engine can call Javis tools and data sources through the MCP Hub, not just Claude. Details in [Models & engines](10-models-and-engines.md).

While Javis thinks, an activity chip appears at the bottom of the chat with three bouncing dots, a status line ("Javis is thinking...", "✓ Data received, analysing...", "✍ Writing the answer...") and a seconds counter (the number only appears from the third second onward).

## Where to find it in Javis

There are **two** chat surfaces sharing one conversation, so switching between them loses nothing.

### The main "Javis" screen

Left navigation rail, group **Assistant** → item **Javis**. This is also the default screen when you open the dashboard (port 7777 by default), so it is already open when the page loads.

| Area | Position | Contents |
|---|---|---|
| VAULT | Left column | The folder tree of the selected brain, a **Find note...** box, two filter modes **Name** / **Content**, and three buttons **＋** (new file), **📁** (new folder), **⟳** (refresh the tree) |
| Knowledge graph + status | Centre | The note network, the status line (READY, LISTENING...), and the **AGENTS** / **SKILLS** / **WORKFLOWS** counters at the bottom |
| CONVERSATION | Right column | Chat history, the engine badge, and the **⛶** button that opens the Chat page |
| Model bar | Just above the input | The model and Effort chip, plus the **SYSTEM** and **MCP** strips currently in use |
| Input bar | Bottom | Mic button, attach button, speaker button, the text box, and the send button (which becomes a stop button while a turn runs) |

The left column **no longer** holds a grid of business metric cards; it is the vault explorer, and clicking a note opens it for editing right there (see [File manager](05-file-manager.md)). Clicking the AGENTS / SKILLS / WORKFLOWS numbers jumps straight to the matching page in the **Capabilities** group.

### The dedicated "Chat" page

Rail, group **Assistant** → item **Chat**. This is a full-screen chat page with no globe and no vault tree:

- The left column is the **conversation history** (reopen, search, rename, delete old sessions).
- The top bar reads **Chat with Javis**, with the engine badge on the right.
- The chat area, attachment chips, model bar and input are **the same** elements borrowed from the Javis screen, so messages, pending attachments and the running turn all stay intact.

Use this page when you want the full width just for chatting. To see the globe and the folder tree again, go back to **Javis**.

## How to use it (step by step)

### Step 1 - Type a question

1. Click the input box at the bottom (the one that reads "Talk to Javis, type here, or drag and drop a file...").
2. Type your question.
3. Press **Enter** to send. To add a line break inside the same message, press **Shift + Enter**.
4. Or click the send button (the arrow) at the right end of the input bar.

Javis's answer streams into the CONVERSATION column on the right, character by character.

### Step 2 - Speak: hold the Space bar

The fastest way to say one sentence:

1. Make sure the cursor is **not** inside the chat box or any other input (while typing, Space produces a space instead of opening the mic).
2. **Hold the Space bar**. The status line in the middle changes to **LISTENING** and the mic button lights up.
3. Say your sentence. What you say appears under the status line so you can see whether Javis heard you correctly.
4. **Release Space**. Javis sends everything you just said and starts answering.

The first time you use the mic, the browser asks for microphone permission. Allow it. If you deny it, Javis cannot hear you and reports that the page needs microphone permission.

### Step 3 - Speak: click the mic button (hands-free mode)

The mic button (the large microphone on the left of the input bar) turns on **always-listening mode**, handy when you do not want to hold a key:

1. Click the mic button once. The status becomes **LISTENING • ALWAYS** and the mic button lights up.
2. Talk naturally. When you pause (about 1.5 seconds of silence), Javis closes the sentence and sends it.
3. After answering, Javis reopens the mic on its own; you do not have to click again.
4. To turn the mode off: click the mic button again, or press **Esc**.

In hands-free mode, Javis stops speaking the moment you start talking, so you can interrupt at any time. The mechanism measures loudness on the echo-cancelled mic stream (about 0.3 seconds of continuous speech, clearly louder than the room), so Javis's own speaker output does not interrupt it.

Interrupting only works while the **mic is open**. With the mic off, a noise in the room will not reopen it even while Javis is speaking.

### Step 4 - Hear Javis answer out loud

By default Javis **reads every answer aloud** in a Vietnamese voice (Edge TTS running on the server). The graph pulses along with the speech.

Turning speech on and off has **3 places** that do the same thing, always in sync, and the choice survives a page reload:

- The **speaker** button in the top right corner (tooltip: "Toggle Javis voice"). When muted, the button dims noticeably.
- The **speaker** button on the chat input bar (tooltip "Mute voice" / "Unmute voice"). When muted, the button turns red with a slash through it. This button is hidden on phones.
- **Settings → Voice, branding & access**, toggle **"🔊 Read answers aloud"**.

### Step 5 - Stop Javis mid-answer

While Javis is thinking or speaking, the send button turns into a **stop button** (a square). Clicking it aborts the running turn and stops the speech immediately, and the status returns to READY. Typing **`/stop`** and pressing Enter does exactly the same.

**The Esc key NO LONGER stops an answer or the speech.** Esc only exits hands-free mode, turns off the mic and closes any open popup. The "(Esc)" hint on the stop button is leftover text from an older build.

The stop button only stops **the session you are looking at**; other sessions running in the background continue. See [Sessions](04-sessions.md).

## Slash "/" commands in the chat box

Typing **`/`** opens a command menu just above the input box, and it works **at the start of the box or mid-sentence**.

Three session commands lead the list:

| Command | Name in the menu | What it does |
|---|---|---|
| `/new` | New conversation | Start a new conversation |
| `/reset` | Reset session | Clear the context and start over |
| `/stop` | Stop | Stop the running answer |

On the web build, `/new` and `/reset` both open a new conversation.

Below those three sit **all skills of the selected brain**, each row showing `/slug`, the skill name and a one-line description.

Controlling the menu:

- Keep typing to narrow the list. Slug matches rank ahead of name matches.
- **Arrow up / down** to move, **Enter** or **Tab** to confirm, **Esc** to close. Clicking a row works too.
- Picking a **session command** runs it immediately, no Enter needed.
- Picking a **skill** inserts `/slug ` **exactly at the cursor**, keeping the text on both sides; keep typing, then press Enter to send.

When you send a skill command, Javis turns it into a prompt: "Use the skill `<slug>` for this request: ... If no skill by that name exists, just handle my request normally."

### Calling a skill mid-sentence

You do not always think of the skill before you write. Write the request first and type `/` where it fits: *"test using a skill mid-chat `/notes`"* runs the `notes` skill with the **remaining text** as the request. Text before and after the command is merged into the request, so *"write me `/notes` about the meeting"* becomes the request "write me about the meeting".

A few rules so nothing is misread as a command:

- The `/` must sit **at the start of the message or right after a space**. That is why `https://example.com/notes` and `3/4 of a cake` are never read as commands.
- Mid-sentence, the command name must be a **real skill** in the selected brain. `/home/user/notes` or `/does-not-exist` go through as plain text.
- With several commands in one message, the **last one** wins (your latest intent). A command at the very start of the box always takes absolute priority.
- **The three session commands (`/new`, `/reset`, `/stop`) only run at the start of the box**, and the menu does not suggest them mid-sentence: writing half a message and accidentally hitting `/reset`, losing all the context, hurts more than it helps.

Skill details are in [Skills](06-skills.md).

## When Javis asks back with buttons

When Javis has to guess a parameter and guessing wrong would hurt (which period, which shop, which channel), it asks back and attaches a row of buttons under the answer bubble:

- One question line, optionally with a short topic label in front.
- At most **4 option buttons**, plus an **"Something else…"** button.
- Clicking a button sends **exactly the text on that button** as your message. "Something else…" sends nothing and just puts the cursor in the box for you to write.
- Labels longer than 40 characters are trimmed with an ellipsis; whatever text the button shows is exactly what gets sent, never something different.

Only the **newest** button row is clickable. Once you answer (by clicking or typing), every older row freezes, and scrolling back to click does nothing. Javis always writes the question in words too, so you can type an answer without touching the buttons.

## Attaching files in chat

You can put files or images into a message for Javis to read. Three ways:

1. Click the **paperclip** button (next to the mic) and pick files. Multiple files are allowed.
2. **Drag and drop** files from your computer onto the Javis window (an overlay shows the drop zone).
3. **Paste** directly with Ctrl + V.

Pasting has one trick of its own: pasting an **image** attaches it as a file as usual, while pasting **very long text** (over 1500 characters or over 25 lines) into the chat box makes Javis package it as an attached `.txt` file instead of stuffing the whole thing into the input. Javis still reads all of it, and the screen only shows a tidy chip. This applies to the chat box only; other inputs still take plain text.

Files appear as small chips above the input bar. Wait for the chip to report the upload finished, then type or speak your request and send as usual. Click the ✕ on a chip to drop that file from the message.

Important, in terms of how Javis handles files:

- **Default: read only.** Javis reads the file (looks at images and describes them) and answers, and saves **nothing** anywhere. The drag-and-drop overlay label that says files are saved into Sources is old text; the real behaviour is read-only.
- **It only saves when you ask clearly.** To have Javis store a file in the Second Brain, say so in the message, for example "save this to sources", "ingest this" or "write this into the second brain". Only then does Javis convert the file into a note and save it in the vault's Sources folder. See [Second Brain: memory, Wiki, INGEST](13-second-brain.md) and [File manager](05-file-manager.md).

## The "open file" chip: what you are editing becomes an input to the conversation

Besides attachments there is a second kind of chip: when you open a text file in the editor (see [File manager](05-file-manager.md)), Javis pins that file to the chat as an orange chip reading "open, click to keep editing".

It differs from an attachment chip in two ways: there is only **one** pinned chip (opening another file replaces it), and it **does not disappear after you send**, because that file is an input to the whole conversation rather than a one-off payload. That is why you can say "clean up the overdue section" or "write me a closing paragraph" without naming the file, and Javis still knows which file you mean and writes straight into it.

The pinned chip is also a **way back**: click it and the file reopens in the editor exactly where you left off (if it is already open, the view simply scrolls to it without reloading, so unsaved text survives). Click **✕** on the chip to unpin it.

## Javis shows images, files and artifacts inside answers

The reverse direction works too: Javis can put images and files from the brain straight into an answer.

- **Images**: Javis writes `![description](attachments/image-name.png)` and the dashboard renders the real image in the chat bubble. Click the image to open that exact file in the **Files** page.
- **Other files** (pdf, docx, xlsx...): Javis writes a markdown link that opens the file in the Files page.
- **Paths in backticks** such as `Javis/loops/morning-report.md` also become links that open the file.
- **Wikilinks** `[[Note name]]` become Wikipedia-style navigation links: clicking one makes Javis find that note in the vault and open it.
- Images that **can no longer be loaded** (expired from the cache area, deleted by hand or renamed) render as a grey box reading **"Image expired"** instead of a broken icon. The brain's `attachments/` and `inbox/` folders are cache areas: they are cleaned after 30 days or when they hit the 300MB ceiling.

### Artifact blocks

Long or visual content does not flood the chat frame; it collapses into a tidy **artifact card**:

| Type | Card label | When it becomes an artifact |
|---|---|---|
| HTML page | HTML page | A ```` ```html ```` block, or content starting with `<!doctype html>` / `<html>` |
| SVG image | SVG image | A ```` ```svg ```` block, or content starting with `<svg` |
| Mermaid diagram | Diagram | A ```` ```mermaid ```` block |
| Long source code | Code + language name | A code block of 24 lines or 800 characters or more |

The card also shows the line count and a "click to view" hint, with an **Open ▸** button on the right. Clicking the card opens a panel on the right of the screen with:

- Two tabs, **Preview** and **Source** (long code only has the source tab).
- A **⧉** button to copy the source, a **⇩** button to download it as a file, and a **✕** button to close the panel.
- Pressing **Esc** also closes the panel.

Mermaid diagrams need a rendering library fetched from the internet; offline, the panel says the library could not load and shows the source instead. ```` ```dataview ```` and ```` ```tasks ```` blocks do not become artifacts; they run and render as result tables, see [Tasks & Dataview in notes](19-tasks-and-dataview.md).

## Asking Javis to generate images

Javis generates images right inside the chat using **the ChatGPT plan you signed into** (OAuth), with no extra OpenAI API key. Just ask in words, for example "make me a photo of a fish sauce bottle on a wooden table, dark background, landscape".

Under the hood, Javis calls the `javis_generate_image` tool (from the bundled `image-chatgpt` plugin) with three parameters:

| Parameter | Values | Default |
|---|---|---|
| `prompt` | The image description, the clearer the better (required) | none |
| `aspect_ratio` | `square` (1024x1024), `landscape` (1536x1024), `portrait` (1024x1536) | `square` |
| `quality` | `low`, `medium`, `high` | `medium` |

Generated images are saved into the selected brain's `attachments/` folder, then Javis embeds `![...](attachments/...)` in the answer so you see it in place. Because `attachments/` is a cache area that expires after 30 days, copy anything you want to keep into another folder in the brain.

A few things to know:

- **You must connect ChatGPT first.** Without it, the tool answers plainly that ChatGPT (OAuth) is not connected and points you at the **Models** page to sign in. See [Models & engines](10-models-and-engines.md).
- Image generation is a `safe`-level action (it writes a file and spends quota), so background work running in read-only mode will not generate images on its own.
- AI-generated images carry provenance marks (Content Credentials). **Settings → Interface & Brain → AI image provenance** has **Keep marks** / **Strip marks**; the default is to keep them.
- Outside chat you can call it directly through `POST /image/generate` with the fields `prompt`, `aspect_ratio`, `quality`, `brain`.

## Summarising YouTube videos

Paste a video link into the chat and say what you want, for example "summarise this video for me" or "does this video mention the price". Javis reads the video's **captions** and answers from the actual dialogue, with timestamps for each main point.

It accepts every link shape: `youtube.com/watch?v=...`, `youtu.be/...`, Shorts, live links, links carrying a playlist or a timestamp, and links buried in the middle of your sentence.

Under the hood, Javis calls the `javis_youtube_read` tool (bundled `youtube-read` plugin). This is a **read-only** action, so background work in read-only mode can summarise videos too, and it runs on **every engine**, including the six API engines that cannot open web pages themselves.

A few things to know:

- **A video with no captions cannot be summarised.** Javis says so plainly rather than guessing the content from the title. Most Vietnamese and English videos have machine captions, but a video posted minutes ago may not have them yet.
- **Private, age-restricted or region-blocked videos** cannot be read either, and Javis names which of those it hit.
- **"YouTube suspects this server is a robot" is not a problem with your video.** The root cause is **IP reputation**: YouTube flags hosting-provider IP ranges, so the same video opens fine at home but gets challenged on a VPS. Javis rotates through eight player types before falling back to yt-dlp, so most such cases pass on their own. Seeing that message means all nine routes were refused.
  - Trying again a few minutes later usually works, because YouTube throttles in waves.
  - If it repeats, the server IP is heavily flagged. The definitive fix is to set the environment variable `JAVIS_YOUTUBE_PROXY` to a residential proxy and restart, see [.env configuration](16-env-configuration.md). Only YouTube traffic goes through it.
- **To see exactly which route failed**, run this on the server:
  ```
  python server/youtube_read.py <video link>
  ```
  It tries each route in turn and prints a table: which lived, which died, what reason YouTube gave, and whether yt-dlp is installed. One run tells you the diagnosis without guessing.
- **Long videos get truncated.** One read takes at most about 40,000 characters of dialogue (enough for a 60 to 90 minute video). Beyond that, Javis says which minute it reached; say "keep reading" and it continues.
- **For captions in another language**, say so, for example "read the English track". By default Javis prefers captions matching the interface language, then English, and always prefers human-made captions over machine ones because human captions carry punctuation and summarise better.
- Machine transcripts often get proper nouns and figures wrong. For numbers that matter, open the video at the timestamp Javis cites and check.

## The button row under each message

Hovering over a message (yours or Javis's) reveals a small button row underneath. On phones, **tap** the message to show it.

| Button | Tooltip | What it does |
|---|---|---|
| Timestamp | The full date, for example "Wednesday, 29/07/2026 14:05" | Display only |
| ↻ | "Send this again" (your message) or "Answer the question above again" (Javis's message) | Resends the original text as a NEW turn at the end of the conversation, deleting nothing from the old turn |
| ✎ | "Edit and send" | Only on your messages. Loads the original text into the input for editing; it does **not** send by itself |
| ⧉ | "Copy content" | Copies the whole message; the button briefly reads "✓ Copied" |

Common points:

- While a turn is running, ↻ dims and cannot be clicked, which prevents overlapping turns.
- Messages with only an image and no text have no ↻ or ✎ buttons (there is nothing to resend).
- Messages saved before timestamps existed simply hide the time rather than showing a made-up current time.
- **Long** messages of yours (over 10 lines or over 900 characters) collapse, with **Show more** / **Show less** buttons.
- Every code block has its own **⧉ Copy** button in the corner.
- If you have scrolled up to reread something while Javis answers, the chat does NOT jump down; a **↓ New messages** button appears at the bottom to jump when you are ready.

## Choosing a model, Effort and the engine badge

Just above the input bar there is a dedicated strip:

- **Model chip**: shows the short name of the provider and model in use, plus **Effort: Off / Low / Medium / High** (thinking depth). Clicking it opens a picker with a **Find model...** box and a provider list, each expanding into its models. Providers that are not configured show a 🔒 with the line "+ Add an API key on the Models page to unlock". The Effort row sits at the bottom of the picker.
- **SYSTEM strip**: two status lights, "⬤ Claude Code CLI" and "⬤ Voice (Edge TTS)".
- **MCP strip**: the data sources and tools Javis called during this session. With nothing called yet it reads "No activity". See [Connections & business data](09-connections-and-business-data.md).

The badge next to **CONVERSATION** (and in the top right of the Chat page) shows the **real** engine and model of the last turn, taken from the server rather than from what the model claims about itself. If the badge disagrees with what you expected, trust the badge.

On phones, the model chip moves into the header and the picker opens in the middle of the screen.

## How Javis formats answers

Since version 0.26.9, answers in the web chat are written for **eyes**, not for ears:

- Short paragraphs of 2 to 4 sentences, then a line break, instead of unbroken prose.
- Lists of 3 or more items use bullets.
- **Bold** on figures, proper nouns and conclusions, the things you scan for.
- Long answers with several distinct parts get a heading per part.
- Tables when comparing the same set of fields across several items, for example revenue for three channels by week.

Before that, Javis was told to write flowing prose because it was often used by **voice**. That trade-off is gone: the speaker button **strips markdown** (headings, bold, bullets, links, code blocks) before reading aloud, so formatting that looks good on screen does not trip up the voice.

Short questions still get a one-sentence answer. Formatting exists for readability, not to make every answer look like a report.

Plain-text channels are stricter because they cannot render: **Telegram** and **Zalo** have no markdown tables, and the **terminal** has no tables, inline images or markdown links. All three still use ordinary bullets. See [Telegram](11-telegram.md) and [CLI in the terminal](24-cli.md).

> If Javis still answers in long prose: most likely the brain's long-term memory still holds an old fact such as "dislikes markdown tables, prefers short spoken prose" from when you used voice, and that memory is loaded into **every** turn. Open `memory/MEMORY.md` in the **Files** page, find the line about answer style, and delete it along with the matching file in `memory/facts/`. See [Second Brain, memory & wiki](13-second-brain.md).

## Voice: provider, voice, speed

Everything about the voice lives in **Settings → Voice, branding & access**.

### Choosing a voice provider

The **VOICE PROVIDER** block has three options:

| Option in the list | What else it needs |
|---|---|
| Edge TTS - free (default) | Nothing |
| OpenAI - smooth, multilingual | An OpenAI API key (shared with chat) plus one of 11 voices: alloy, ash, ballad, coral, echo, fable, nova, onyx, sage, shimmer, verse |
| ElevenLabs - most natural | An ElevenLabs API key plus a **Voice ID** (from ElevenLabs → Voices) |

Pick one and click **Save provider**. The status line underneath says which one is active. If a paid provider fails (quota exhausted, wrong key, network down), Javis **falls back to Edge TTS** automatically so the voice never goes silent.

When you pick OpenAI or ElevenLabs, the two Edge voices (Ngọc Thu / Nam Minh) hide themselves, because the voice is then chosen inside the provider's own block.

### Choosing an Edge voice and the speed

| Option | Value | Note |
|---|---|---|
| Voice | **Ngọc Thu** | Female, natural and warm (default; Edge code `vi-VN-HoaiMyNeural`) |
| Voice | **Nam Minh** | Male, deeper (Edge code `vi-VN-NamMinhNeural`) |
| Speed | Slider from 0.70× to 1.80× | Default 1.10× |
| Listening language | **Vietnamese** (vi-VN) | Default |
| Listening language | **English** (en-US) | Use it if you speak entirely in English |

Steps:

1. Pick Ngọc Thu or Nam Minh.
2. Drag the **SPEED** slider; the number next to it shows the current rate (for example 1.10×).
3. Click **▶ Preview** to hear a sample greeting in the chosen voice.
4. "Listening language" is the language Javis uses to recognise your speech, which is separate from the answer voice. Leave it on Vietnamese unless you normally speak English.

Voice, speed and listening language are all remembered for next time.

## Enlarging the chat

When you work in chat for a while on the **Javis** screen, click the **⛶** button in the corner of the CONVERSATION panel to jump to the **Chat** page: a full-screen chat, with the **conversation history** on the left (reopen, search, rename, delete old sessions, see [Sessions](04-sessions.md)) and the chat centred on the right for easier reading, with a taller input for longer writing.

To go back to the Javis screen: click **‹ Shrink** in the Chat page title bar.

It is still **one single conversation**: chatting on the Javis screen or on the Chat page is the same thread, the same model bar, the same attachment area. Since version 0.12.4, the enlarge button no longer opens a separate overlay; before that there were two nearly identical chat frames that behaved differently, which was easy to confuse.

## Asking for business numbers

The fixed grid of metric cards in the left column was removed in version 0.9.166. Previously, every time you opened the dashboard Javis ran a scan of the connected sources to fill that grid, spending quota that mostly nobody looked at.

Now, when you want numbers, just ask in chat ("how is revenue today", "compare with last week"). Javis calls the right connected source (POS, sales channels, ads...) and answers in words, so it only runs when you actually need it. Details about data sources are in [Connections & business data](09-connections-and-business-data.md).

## Using it on a phone

Below 860px wide, the interface changes to fit the screen:

- Navigation collapses into a drawer: tap **☰** to open it, then tap the dimmed background, pick an item or press Esc to close.
- The **model chip** and the **+** button (new conversation) move into the header.
- The **System** group (brain picker, light/dark toggle, speaker button, the SYSTEM and MCP strips) moves to the bottom of the navigation drawer.
- The input shortens its placeholder to "Speak or type to Javis…".
- The speaker button on the input bar and the **🕘 History** button in the header are hidden (the drawer already has a speaker button, and the **Chat** page has the history built in).
- There is no mouse to hover with, so **tap a message** to reveal its button row; tapping elsewhere hides it again.
- On the **Chat** page, the **🕘** button in the title bar opens and closes the history drawer sliding in from the left.

## What the status line in the middle means

The line under the globe says what Javis is doing:

| Text shown | Meaning |
|---|---|
| READY | Idle, waiting for you |
| LISTENING | Listening to you (Space held) |
| LISTENING • ALWAYS | Hands-free mode is on |
| THINKING | The brain is processing the question |
| SPEAKING | Javis is reading the answer aloud |

## Quick reference: buttons and shortcuts

Buttons around the chat frame:

| Button | Where | What it does |
|---|---|---|
| Large mic | Left of the input | Toggle hands-free (always listening) mode |
| Paperclip | Next to the mic | Pick files to attach |
| Speaker | Next to the paperclip | Toggle reading answers aloud (hidden on phones) |
| Arrow | Right of the input | Send the message |
| Square | Replaces send while running | Stop the running turn and stop speaking |
| ⛶ | Corner of the CONVERSATION panel | Enlarge the chat |
| 🕘 History | Top right | Open the wide chat with conversation history |
| Engine badge | Next to CONVERSATION | The real engine and model of the last turn |
| Model chip · Effort | Above the input | Change provider, model and thinking depth |

Keyboard shortcuts:

| Action | Result |
|---|---|
| Hold **Space** (outside an input) | Open the mic and listen until you release |
| Release **Space** | Send what you just said |
| **Enter** | Send the message you typed |
| **Shift + Enter** | Line break inside a message |
| **Ctrl + V** | Paste an image, or paste long text as an attached .txt file |
| **/** (start of the input) | Open the command menu; ↑ ↓ to move, Enter or Tab to confirm |
| **Esc** | Exit hands-free mode and turn off the mic; close the command menu; close the artifact panel. Does **not** stop the answer |

## Tips

- To speak several sentences without Javis sending early, use hands-free mode (the mic button) and talk continuously; only pause fully when you are actually done.
- Tired of listening and would rather read in silence: turn off "🔊 Read answers aloud"; the answer still appears in full as text.
- Send several screenshots at once by dragging them all into the window; Javis processes each one.
- If you normally speak English, switch "Listening language" to English for better recognition.
- Feel free to paste a whole long article into the chat box: Javis turns it into an attached `.txt` file and the chat stays tidy.
- To reask a question with a few words changed: click **✎** on the old message, edit it in the input and send, instead of retyping.
- The **⛶** button on the CONVERSATION panel and the **Chat** item in the Assistant group lead to the same place; use whichever is closer.

## Common problems

- **Holding Space does not open the mic.** The cursor is inside the chat box or another input. Click an empty part of the page, then hold Space again.
- **A sentence you never typed appears in the chat.** Almost certainly the mic picked up room noise (music, TV, someone talking), transcribed it and sent it, because Javis sends as soon as a sentence ends rather than asking first. Look at the status line: **LISTENING** or **LISTENING • ALWAYS** means the mic is still open, so click the mic button or press **Esc** to close it. Since version 0.52.6 the mic no longer sticks open when you tap and release Space very quickly, and Javis speaking no longer reopens the mic by itself. To clear that stray message, start a new conversation; Javis has no way to type into your chat box, and every background result appears as a bubble on the left.
- **The browser cannot hear.** Javis reports that the browser does not support speech and suggests Chrome or Edge. Open the dashboard in Chrome or Edge.
- **The microphone does not work.** The browser is blocking microphone permission. Open the site permissions in your browser, allow the microphone, then reload the page.
- **Pressing Esc but Javis keeps talking.** That is the current design: Esc no longer stops a turn. Click the stop button (the square) on the input bar, or click the speaker button to mute.
- **You cannot hear Javis.** Check whether the speaker button is muted (dimmed in the top right, or red with a slash on the input bar), and check the system volume. Click "▶ Preview" to test speech on its own. If you use OpenAI or ElevenLabs and the voice sounds unfamiliar, that provider probably failed and Javis fell back to Edge.
- **Typing "/" shows no menu.** The menu only opens when "/" starts the input with no space after it. If there are still no skill rows, the selected brain has no enabled skills.
- **Clicking one of Javis's option buttons does nothing.** That row belongs to an older turn and froze when you sent a new message. Just type the answer instead.
- **An image in the conversation became a grey "Image expired" box.** The file lived in the `attachments/` cache area and passed 30 days, or was cleaned when the 300MB ceiling was hit. Ask Javis to regenerate it, or next time copy important images into another folder in the brain.
- **A diagram does not render, only the code shows.** The diagram library is fetched from the internet; the machine is offline or blocked. The content is still intact on the source tab.
- **Asking for an image reports that ChatGPT is not connected.** Go to the **Models** page and sign into ChatGPT (OAuth), no API key needed, then try again.
- **An empty answer.** If the answer area shows a hint to retry or change model, the selected model may be having trouble. See [Models & engines](10-models-and-engines.md) to switch model or engine.
- **A file never finishes uploading.** Large file or slow network; the file chip reports the specific error (upload timeout, server error). Try a smaller file or check the connection.

## Related

- [Sessions](04-sessions.md) - save, reopen, rename and delete old conversations.
- [Skills](06-skills.md) - write and call skills with `/slug`.
- [Models & engines](10-models-and-engines.md) - the providers and how to switch engines.
- [Connections & business data](09-connections-and-business-data.md) - connect data sources to ask for real numbers.
- [File manager](05-file-manager.md) - the VAULT column and the Files page.
- [Tasks & Dataview in notes](19-tasks-and-dataview.md) - `dataview` and `tasks` blocks in answers.
- [Telegram channel](11-telegram.md) and [Zalo](12-zalo-agent-mcp.md) - chat with Javis outside the dashboard.

Still stuck? See [Troubleshooting & FAQ](17-troubleshooting.md).
