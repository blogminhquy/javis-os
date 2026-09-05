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
| `zalo_view_media` | Download/open an image, audio or video from a message | Read |
| `zalo_mark_read` | Mark as handled up to a cursor | Write |
| `zalo_send_message` | Send a message to a person or group | Dangerous |

The list follows the `zalo-agent-cli` 1.6.2 source. Upstream MCP documentation:

<https://github.com/PhucMPham/zalo-agent-cli/blob/main/skill/references/mcp-guide.md>

## Sending images and files

`zalo_send_message` above **only sends text**. To send an image (say one Javis just generated)
or a file (a PDF report, a spreadsheet), use the `zalo_send_image` tool provided by the bundled
`zalo-image` plugin. The plugin is on by default, needs no extra install, and uses exactly the
Zalo account you scanned the QR with.

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
- **Full power**: allows sending (both `zalo_send_message` and `zalo_send_image`).

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
