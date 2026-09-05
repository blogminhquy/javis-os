# Sessions

*[Tiếng Việt](../04-phien-hoi-thoai.md) · **English***

Every conversation you have with Javis is saved automatically. This page covers how to review, search, rename, delete and continue an old conversation, including one from days ago.

If the chat screen is new to you, read [Chat & voice](02-chat-and-voice.md) first.

## What this feature is

Javis saves every question and answer into a database on your own machine, so nothing is lost when you close the browser or restart the server. Specifically, you can:

- Browse past conversations, newest first.
- Search full text: type a keyword and Javis searches inside every conversation.
- Reopen an old conversation and keep talking in the same thread.
- Rename conversations so they are easy to recognise.
- **Pin** important conversations to the top of the list.
- **Group** conversations into a **Project**.
- **Give each Project an icon** so groups are easy to tell apart visually.
- Delete conversations you no longer need.

## Pinning, Projects and icons

The list is ordered by time, so a conversation you keep returning to slowly sinks. These three tools let you rearrange it, all of them in the **History** column on the left of the chat.

**Pinning.** Hover a conversation and click the pin icon. It moves to the **Pinned** group at the top of the list and stays there. Pinning does not make the conversation look "just used", so the order of the others is unaffected. Click again to unpin.

**Projects.** The bar right under the "New conversation" button is the group picker. Click it to see the list, create a group, rename it, change its icon or delete it. While a project is open:

- The list only shows conversations in that project.
- **New conversations you start land in that project automatically**, with no manual tagging.

Pick "All conversations" to see everything again, or "Ungrouped" to find the leftovers. To move a conversation into another group, hover it and click the folder icon.

**Deleting a project does NOT delete conversations.** The conversations inside are only removed from the group and return to "Ungrouped". The confirmation box says so, along with how many conversations will be released.

**Project icons.** Open the group picker, hover a project and click the palette icon. The picker shows every icon Javis uses, with a name filter (type `star`, `folder`, `brain`...). A project with no icon borrows the folder icon, so every row has one and your eye can scan down the icon column.

Icons exist for **Projects** only, not for individual conversations. The reason: every row in the list is a conversation, so an icon there classifies nothing and only adds a button to click. Each project genuinely is a different thing, so an icon there has work to do.

These are **Javis's own icons**, not emoji, and that is deliberate: Javis icons recolour themselves for the light or dark theme you use, and render identically on every machine. Emoji are drawn differently by each operating system and have fixed colours that glare on dark backgrounds.

Projects belong to a brain, so switching brains switches the project list. Which project is currently open is remembered per machine (per browser) and is not synced elsewhere.

One important point: conversations are attached to the selected "brain" (vault). When you switch brains in the vault picker, the history list follows so it only shows that brain's conversations, **and the chat frame follows too**. See "Switching brains mid-flight" below, and how to pick a brain in [Getting started & first-run setup](01-getting-started.md).

## Where the data lives

The whole history sits in a single file named `conversations.db`.

| Item | Default | Note |
|---|---|---|
| File name | `conversations.db` | SQLite format |
| Folder | Javis's `server/` folder | Same place as `settings.json` |
| Environment variable to move the file | `JAVIS_SESSIONS_DB` | Point it at another `.db` path |
| Environment variable to move the root folder | `JAVIS_STATE_DIR` | Moves the whole state folder |

To move the history file elsewhere (a dedicated data disk, for example), set `JAVIS_SESSIONS_DB` in the config file. Details on environment variables are in [.env configuration](16-env-configuration.md).

Each conversation stores its title, brain, engine in use, model, the channel it came from, message count, creation time and last update time. Each question and answer is stored separately so it can be searched and reopened exactly.

## Conversations that came from Telegram

This list is not just the ones you open on the web. What you say to Javis over **Telegram** is saved here too, labelled **TG** in the list, so at your desk you can reread and search a conversation you had on the road.

Because almost nobody starts a new conversation explicitly on Telegram, Javis cuts to a new one when you pause for more than 12 hours or when the current one reaches about 100 turns. That cut only makes the archive readable; it does not make Javis forget the thread while you are talking on Telegram. Telegram conversations older than 30 days are archived so they do not clutter the default list, but they are still findable through search. Details in [Telegram channel](11-telegram.md).

## Where to find it in Javis

The history sidebar lives on the **Chat** page. Three entrances lead to the same place:

- **Navigation rail.** Open the **Assistant** group on the left and click **Chat**.
- **The ⛶ button** on the **CONVERSATION** panel of the main Javis screen.
- **The 🕘 History button** in the top right button row.

The page has two columns: on the left the **History sidebar** with a **＋ New conversation** button on top, a search box, and the conversation list grouped by time (**Today / Yesterday / Last 7 days / Older**); on the right the chat with the title "Chat with Javis". The open conversation is highlighted in the list so you know where you are.

The **🕘** button in the title bar (tooltip: "Show/hide history") collapses or expands the left column. **‹ Shrink** returns to the Javis screen. On narrow screens (under 860px) the sidebar hides itself and opens as a floating drawer; picking a conversation closes the drawer.

## How to use it (step by step)

### Reviewing the conversation list

1. Open the history sidebar in either way above.
2. The list shows conversations for the selected brain, grouped by time, most recently updated on top.
3. Each row shows: the conversation title, the time (or date), a channel label when it is not web (for example **TG**), the engine used and the message count (for example `12 msgs`).
4. The list shows the first **20 conversations**. If there are more, a **Show 20 more** button sits at the bottom; click it to load another 20. There is no ceiling, so keep clicking for more.
5. With nothing saved yet, the sidebar reads "No conversations yet." with "Click ＋ to start."

An unnamed conversation temporarily shows your first question as its title. Javis also generates a short title from that first question (about 48 characters) right after the first answer.

### Spotting a conversation that is still answering

A conversation with a turn still running in the background shows an **⏳** before its title (tooltip: "Answering") and the whole row is highlighted. Go do something else; the answer keeps running on the server and saves itself into that conversation.

If you send another message into that same running conversation, Javis declines and says: "This session is answering, wait for the current turn to finish." To ask something else immediately, click **＋ New conversation** and ask there.

### Full-text search

1. Open the History sidebar.
2. Click the box with the placeholder **Search all conversations…** at the top.
3. Type a keyword. Javis searches shortly after you stop typing, no Enter needed.
4. While searching, the list reads "Searching…".
5. Results show matching rows: the conversation title, a short excerpt around the keyword (the match in bold) and the time of that message.
6. Click a result to open the conversation containing it.
7. Clear the search box to return to the full list.

With no matches, the sidebar shows "Nothing found." Search only covers the selected brain. To search another brain, switch brains first.

### Reopening and continuing an old conversation

1. In the list (or in the search results), click the conversation you want.
2. The chat on the right IMMEDIATELY reloads every past question and answer, and that row is highlighted in the list.
3. Type a new message as usual. Javis continues the same thread rather than starting over.

How Javis keeps the thread differs per engine, see "How Javis remembers the thread" below and [Models & engines](10-models-and-engines.md).

### Starting a new conversation

1. Open the History sidebar.
2. Click **＋ New conversation** at the top.
3. The chat clears and you start fresh. The new conversation is only saved into history after you send the first message.

### Renaming a conversation

1. In the list, hover the row you want to rename. Two small icons appear on the right.
2. Click the pencil **✎** (tooltip: "Rename").
3. A prompt appears reading "New name for this conversation:". Type it and click OK.
4. The list updates with the new name.

Titles are capped at about 120 characters; anything longer is trimmed. Clicking Cancel keeps the old name.

### Deleting a conversation

1. In the list, hover the row you want to delete.
2. Click the bin **🗑** (tooltip: "Delete").
3. A confirmation box appears with the name: `Delete conversation "<name>"?`. Click OK to delete, Cancel to keep it.
4. The conversation and all of its messages are removed from the database, and the list updates.
5. If you deleted the conversation you had open, the chat switches to a new empty one.

Note: deletion is permanent, with no recycle bin. Think twice before deleting something important. (Deleting a whole brain is different: that has a bin that keeps it for 30 days, see [File manager](05-file-manager.md).)

## How Javis remembers the thread

Three engines keep context in three different ways, so reopening an old conversation behaves differently.

**Claude engine (Agent SDK).** Every dashboard conversation stores Claude's native session id. Reopening an old conversation reconnects to that exact session, so both the context and the tools already used are intact.

**Codex engine (ChatGPT plan).** Every conversation stores Codex's own native thread id so the next turn continues that thread. If the thread is gone (the machine was upgraded, an old rollout was cleaned), Javis does not drop the thread: it rebuilds the context from the history already stored in `conversations.db`, opens a new thread, and prints a line in the chat saying the old Codex session no longer exists on the machine and that Javis is restoring context from saved history. The history it feeds back has a budget of about 60,000 characters, preferring the most recent part.

If you switch to another engine and keep asking in the same conversation, the old Codex thread link is dropped (that thread does not contain the latest turns). Coming back to Codex, Javis builds a new thread from the saved history.

**API engines (OpenRouter, OpenAI, Anthropic API, Google Gemini).** Every turn, Javis rebuilds the history from the database and sends it along. In a long conversation the older part is **compressed rather than silently truncated**: Javis summarises the beginning of the conversation, stores that summary, then prepends it to later payloads as a note reading "[Summary of the earlier conversation, compressed to save context...]". The model still remembers the topic, settled decisions, figures and unfinished work, while the payload does not grow without bound.

Compression usually runs in the background after a turn, so you do not feel a delay. Only when the uncompressed part has piled up too far (common on the first API turn right after a stretch of chatting on the Claude engine) does Javis compress inside the turn, adding one beat of delay. If the provider fails and the summarising step breaks, only then does Javis fall back to the old behaviour of trimming the very oldest part.

## Switching brains mid-flight

Switching brains in the top bar picker changes more than the history list; it changes the chat frame too:

- The old brain's content is cleared from the chat immediately, so you never mistake it for a conversation in the new brain.
- For any brain you already visited during this page load, Javis reopens exactly the conversation you left there.
- For a brain you have not opened during this page load, the chat starts blank, as a fresh start.
- This memory only lives for one page load. Reloading (F5) returns to the general rule: every page load starts a new conversation. Old conversations stay in the history list, one click away.

## Quick action table

| Action | Button / key | Where |
|---|---|---|
| Open the Chat page (with the history sidebar) | `Chat` item | Navigation rail, Assistant group |
| Open the Chat page from the Javis screen | `⛶` or `🕘 History` | CONVERSATION panel / top right button row |
| Show or hide the sidebar | `🕘` | The "Chat with Javis" title bar |
| Back to the Javis screen | `‹ Shrink` | Title bar |
| Full-text search | The "Search all conversations…" box | Top of the sidebar |
| New conversation | `＋ New conversation` | Top of the sidebar |
| Reopen a conversation | Click the row | The list (the open one is highlighted) |
| Load older conversations | `Show 20 more` | Bottom of the list |
| Rename | `✎` | Appears on hover |
| Delete | `🗑` | Appears on hover |
| Conversation still answering | `⏳` before the title | An indicator, not a button |

## Tips

- Give important conversations a clear name as soon as you finish, so later you find them without rereading everything.
- To keep one long topic coherent, reopen the same conversation instead of clicking **＋ New conversation**. That way Javis still remembers the earlier context.
- When you start something entirely unrelated, click **＋ New conversation** so old context does not bleed into the answer.
- Search covers message contents, so you can search by a number, a customer name or a phrase you discussed, not only by title.
- The list and the search always follow the selected brain. If a conversation seems missing, check which brain you are in.
- Very long conversations still work, but if you move to a completely different topic a new conversation gives sharper answers: the compressed part only survives as a summary, not verbatim.

## Syncing when you change machines

The conversation history lives in `conversations.db` on the machine running Javis. That file does not sync to the cloud and does not move to another machine by itself.

- To keep the history when moving Javis to a new machine or VPS, copy `conversations.db` (in the `server/` folder) to the same location on the new machine, doing it while the server is stopped so the file is not open.
- Without that copy, the new machine starts with empty history. That is normal, not a fault.
- Do not open the same `conversations.db` from two servers running in parallel; that can cause write conflicts.
- For routine backups, backing up `conversations.db` alone preserves the whole chat history.

## Common problems

**The history panel is empty although there were plenty of conversations.**
Most likely you are in a different brain. The list only shows the selected brain's conversations. Switch back and open the panel again.

**Opening the panel shows "Failed to load the list."**
The Javis server may not be running or just restarted. Check that it is up on the default port (7777) and try again. See [Troubleshooting & FAQ](17-troubleshooting.md).

**A conversation from last week is not at the bottom of the list.**
The list loads 20 at a time. Scroll down and click **Show 20 more** a few times, or faster, type a keyword into the search box.

**Search says "Nothing found" although you are sure you said it.**
Check that you are in the brain that holds that conversation. If it still does not appear, try a shorter keyword or a simpler word instead of a full sentence.

**Sending a new message reports "This session is answering, wait for the current turn to finish."**
That conversation has a turn still running (its row shows ⏳). Wait for it, or click **＋ New conversation** to ask something else in parallel.

**Reopening an old conversation but Javis does not remember the earlier context.**
On the Claude engine, full recall depends on whether the native session still exists. On the Codex engine, the native thread may have been cleaned from the machine; Javis restores from saved history and prints a line in the chat. On API engines, the very old part may exist only as a compressed summary rather than verbatim, so small details can blur; restating the key facts briefly in your new question is enough.

**The chat is blank after switching brains.**
That is by design: a brain you have not opened during this page load starts blank. That brain's old conversations are still in the history sidebar, one click away.

**You deleted a conversation by mistake.**
Deletion is permanent and cannot be undone from the interface. The only prevention is backing up `conversations.db` regularly (see "Syncing when you change machines").

**The renamed title came out truncated.**
Conversation titles are capped at about 120 characters. Anything beyond is dropped, so keep names short.

## Related

- [Chat & voice](02-chat-and-voice.md) - sending questions, attaching files, turning on voice.
- [Models & engines](10-models-and-engines.md) - choosing the Claude engine, Codex or an API provider.
- [Telegram channel](11-telegram.md) - conversations created from Telegram and the TG label.
- [File manager](05-file-manager.md) - picking and managing brains.
- [Troubleshooting & FAQ](17-troubleshooting.md)
