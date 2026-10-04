# Zalo Agent MCP

*[Tiếng Việt](../12-zalo.md) · **English***

> **Javis touches Zalo in THREE places, do not mix them up.** This page covers the first:
> signing in with **your own Zalo account** so Javis can act on your behalf. The other two
> use the official API, which is safe, but they only see what people send directly to the bot.
>
> | | Zalo Agent MCP (this page) | [Zalo Bot channel](26-zalo-bot-channel.md) | [Chatbot](25-chatbots.md) |
> |---|---|---|---|
> | Who it is | You yourself | A separate bot | A separate bot, under an Agent's name |
> | API | Unofficial (zca-js) | Official | Official |
> | Risk of account lockout | Yes | No | No |
> | Can read old conversations | Yes | Only messages sent to the bot | Only messages sent to the bot |
> | Can message someone who never contacted the bot | Yes | No | No |
> | Used for | Javis working on your behalf | **You** messaging Javis | **Customers** messaging Javis |
>
> Running all three at once is fine, they do not collide.

Javis connects a personal Zalo account through the standard MCP of the
[`zalo-agent-cli`](https://github.com/PhucMPham/zalo-agent-cli) project. The new flow has a
single MCP process: sign in by QR, read or search conversations and send messages through the
tools the upstream project provides.

> `zalo-agent-cli` uses the unofficial Zalo API via `zca-js`. Zalo does not support this way
> of connecting and the account may be restricted or locked. Use a secondary account, avoid
> automated bulk sending, and accept the risk yourself.

## What you need

- Node.js 20 or newer on the machine or VPS running Javis.
- A phone already signed in to the Zalo account you want to connect.
- Javis started and you able to sign in to the dashboard.

Javis pins `zalo-agent-cli` at version `1.6.2`, the version verified against the seven MCP
tools below.

## Connecting by QR

1. Open **Connections** → find **Zalo Agent MCP** → click **Connect**.
2. Read the risk warning, type a memorable name if you want, then click **Show QR code**.
3. In the Zalo app on your phone, open the QR scanner and scan the code on the dashboard.
4. When the account card appears under **Connected**, the connection is ready.
5. To attach another account, click **＋ Add account**. Each account uses its own session
   folder so they never overwrite one another.

The **Guide on GitHub** button in the Zalo card always opens this documentation page:

<https://github.com/blogminhquy/javis-os/blob/main/docs/en/12-zalo-agent-mcp.md>

## The MCP tools

| Tool | What it does | Action level |
|---|---|---|
| `zalo_get_messages` | Read new messages in the buffer, supports a cursor | Read |
| `zalo_get_history` | Fetch the history of one chat, paginated | Read |
| `zalo_list_threads` | List the chats currently in the buffer | Read |
| `zalo_search_threads` | Find a group or person by name | Read |
| `zalo_view_media` | Download/open an image, audio or video on the server (the brain does not see it, see `zalo_read_images` below) | Read |
| `zalo_mark_read` | Mark as handled up to a cursor | Write |
| `zalo_send_message` | Send a message to a person or group | Dangerous |

The list follows the `zalo-agent-cli` 1.6.2 source. Upstream MCP documentation:

<https://github.com/PhucMPham/zalo-agent-cli/blob/main/skill/references/mcp-guide.md>

## The Zalo extras pack (Javis Store)

The three groups of tools below (reading images, sending images and files, tagging people plus
notes, reminders and polls) fill exactly what the standard MCP lacks. Since 0.73.0 they live in
the **`javis.zalo`** pack on Javis Store instead of shipping inside the app, so people who do not
use Zalo do not carry them:

- **Right after you scan the Zalo QR, Javis offers the pack** through the store's own consent
  screen: it lists every code file, with the "run now" switch on because you just connected
  Zalo yourself. Press Install and every tool is there.
- **On a machine that connected Zalo earlier**, the Connections page shows a reminder with an
  **Install companion pack** button. Javis never installs a code pack without asking.
- The Zalo connection, the Inbox and the Zalo chatbot stay in the app and keep working without
  the pack. Without it you only miss the extra tools.

## Reading images in a group

The Zalo MCP only returns a **link** to an image, keeps messages for 2 hours, and
`zalo_view_media` opens the image in the server's own image viewer instead of handing it to the
brain. So the `javis.zalo` pack has the `zalo_read_images` tool:

| Tool | What it does | Action level |
|---|---|---|
| `zalo_read_images` | Fetches the images people post in a group into the brain and tells the brain what is in them | Write (saves images to the brain) |

Just ask in chat, for example "look at the receipt Lan just posted in the Sales group".

- **Images come straight from Zalo**, not from the MCP's 2-hour buffer: Javis asks Zalo for the
  group's recent messages (30 by default, at most 100) and takes up to the 8 newest images. For a
  private chat, only images still in the MCP buffer can be fetched.
- **Images are saved to `attachments/zalo/<group id>/`** in the brain, so they show right in chat.
- **Every brain can "see" them.** Claude Code and Codex open the image file themselves. The API
  engines (OpenRouter, Gemini...) cannot view images, so ChatGPT on the plan you are signed in to
  looks at them and describes them, copying any text and numbers verbatim. Without ChatGPT signed
  in on the Models page the images are still fetched, just without the description.

The part where ChatGPT looks at images lives in the app (the bundled `image-chatgpt` plugin, tool
`javis_describe_image`), so it can view any other image in the brain too, with or without the
Zalo pack.

## Sending images and files

`zalo_send_message` above **only sends text**. To send an image (say one Javis just generated)
or a file (a PDF report, a spreadsheet), use the `zalo_send_image` tool from the `javis.zalo`
pack. It uses exactly the Zalo account you scanned the QR with.

| Tool | What it does | Action level |
|---|---|---|
| `zalo_send_image` | Send an image or file with a message | Dangerous (Full power level) |

Just say it in chat, for example "send this image to the Sales group" or "send the July report
to Nam over Zalo".

Three things worth knowing:

- **Only files inside the brain in use can be sent.** This is a deliberate safety rail: without
  it, one cleverly worded chat message could make Javis send any file on the server outside, and
  a Zalo message cannot be recalled.
- **One send carries one kind**, either all images or all files, up to 10 files. Mixing them
  makes Zalo display the wrong type, so Javis reports back instead of guessing.
- **With several Zalo accounts attached, Javis asks** which one to send from. Sending from the
  wrong account means sending under someone else's identity, so this is not a place to guess.

Node.js 20+ is required on the machine running Javis, same as for the Zalo connection itself.

## Tagging people, notes, reminders and polls

`zalo_send_message` only sends text, so it cannot tag anyone, and the Zalo MCP has no notes, reminders or polls either. The
`javis.zalo` pack fills exactly those gaps with five tools that every brain can call:

| Tool | What it does | Action level |
|---|---|---|
| `zalo_group_members` | List the members of a group (id with name), or look one person up by name | Read |
| `zalo_send_mention` | Send a message to a group and tag the right people | Dangerous (Full power level) |
| `zalo_create_note` | Create a group note, can be pinned | Dangerous (Full power level) |
| `zalo_create_reminder` | A reminder shown inside Zalo, with a time and repeat (daily, weekly, monthly) | Dangerous (Full power level) |
| `zalo_create_poll` | A poll for the group: multiple answers, anonymous, closing time | Dangerous (Full power level) |

Just say it in chat, for example "message the Sales group and tag @minhquy: meeting at 9am" or "create a poll in the Javis class group: what for lunch".

Four things worth knowing:

- **You only need to say a name to tag.** "@minhquy" or "Minh Quý" both work, ignoring case and accents. Javis looks up the real Zalo
  id among the people who already spoke in that group first, then in Zalo's member list. **If a name is ambiguous or not found, Javis
  asks back with the candidates** instead of guessing, because a wrong tag cannot be undone. `@All` only when you ask for it explicitly.
- **This reminder is not Javis's own reminder** (`javis_schedule`): it shows up inside Zalo, so the whole group sees it. Times use Javis's timezone.
- **If the group locks note or poll creation for members**, Zalo refuses and Javis reports that reason as is. If a command times out,
  Javis says it is **not sure whether it was created** and asks you to check the group before trying again, so you do not get two polls.
- **With several Zalo accounts attached, Javis asks** which one to use, same as for sending images.

## Using it in chat

You can speak naturally:

- "Find the Sales group on Zalo."
- "Read the 20 most recent messages in the Sales group."
- "Any new Zalo messages?"
- "Send the Sales group: meeting at 9am tomorrow."

When sending, state the name or `threadId` clearly, the content, and whether it is a person or a
group. If the search returns several chats with the same name, Javis must ask back rather than
guess. If exactly one result matches, Javis sends right away with `zalo_send_message`; no
listener has to be enabled, the recipient does not have to message first, and nothing depends on
a watch list.

## Permissions

A new connection defaults to **Full power** so that `zalo_send_message` can be used.

- **Read only**: only the five read tools.
- **Draft writes**: adds `zalo_mark_read`, still blocks sending.
- **Full power**: allows sending (`zalo_send_message`, `zalo_send_image`) and the tools that tag people or create notes, reminders and polls.

You change the level in the menu of the account chip on the **Connections** page. Background
work running at a restricted level is still blocked from sending by the MCP Hub, even when the
account is set to Full power.

## Differences from the old Zalo integration

The new flow dropped the `listen --webhook` sidecar, the `/hook/zalo` endpoint, the "Listen
continuously" panel, the per-chat rules file and the two plugins `javis_zalo_rule` and
`javis_zalo_send`. No listener process turns the MCP connector off and back on any more.

Because of that, Javis does not forward Zalo messages to Telegram in the background. When you
want to check messages, ask Javis; MCP can use `zalo_get_messages` for buffered messages or
`zalo_get_history` for history.

## Troubleshooting

- **No QR appears**: check that `node --version` is 20 or higher and that the machine can reach
  npm.
- **QR expired**: close the connection window and click **Connect** to generate a new code.
- **A chat is missing**: try `zalo_search_threads`; for older messages use `zalo_get_history`
  rather than only `zalo_get_messages`.
- **The send tool is blocked**: open the account chip menu and switch the level to **Full
  power**.
- **It reports the session is in use elsewhere**: close Zalo Web or another `zalo-agent-cli`
  process using the same account, then try again.
- **You want to sign in from scratch**: delete the connection on the dashboard, then connect and
  scan the QR again. Other connections' session folders are unaffected.

## References

- [The `zalo-agent-cli` repository](https://github.com/PhucMPham/zalo-agent-cli)
- [Upstream MCP guide](https://github.com/PhucMPham/zalo-agent-cli/blob/main/skill/references/mcp-guide.md)
- [Connections and MCP permissions in Javis](09-connections-and-business-data.md)
