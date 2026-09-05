# The Javis CLI: asking Javis from a terminal

*[Tiếng Việt](../24-cli-terminal.md) · **English***

Install a small package on your computer then type `javis "how is revenue this week"` right in the terminal, with no browser. The answer still comes from your own Javis: the same brain, the same memory, the same attached MCPs, the same conversation history.

> **Read this line first:** the Javis CLI **does not contain Javis inside it**. It is the mouthpiece; at the other end there must be a Javis server running, either on this machine or on a VPS. With no server the CLI can do nothing, and it says so plainly rather than reporting a vague network error.

## What this feature is

- **A third channel**, alongside the web dashboard and Telegram. The same Javis, only a different place to stand.
- Ask one question and exit (`javis "..."`), or open a continuous session (`javis chat`).
- Connect to several Javis instances: one profile for the home machine, one for the VPS, switched with `--profile`.
- Queue Kanban work, browse the brain, view loops, check server status, all from the terminal.
- **Composable in scripts**: the answer goes to stdout, everything else to stderr. So `javis "summarise this week" > report.md` produces exactly the content with no status lines mixed in.
- Javis knows it is speaking through a terminal so it answers differently: no markdown tables, no embedded images, and file paths printed absolute so you can copy and run them.

## Installation

Python 3.9 or newer is required. The package pulls in exactly **one** library (`httpx`), so it installs fine on a machine that has never had Javis.

```bash
pip install javis-cli
```

Installing from source (when you have cloned the Javis repo):

```bash
pip install ./cli
```

That gives you the `javis` command. Check it with `javis --help`.

## Step 1: create a token in the dashboard

The Javis server accepts no outside commands without a token. **No token exists by default**, so until you create one by hand this door is closed.

1. Open the Javis dashboard, go to **Account** (the **System** group at the bottom of the left rail) and scroll to **API tokens (for the CLI)**. It shares the page with the login password, because a token is also a way of signing in.
2. Give it a memorable name, "my laptop" for example, so a later revocation is unambiguous.
3. Choose the scope:
   - **Chat only** - reaches `/chat`, `/version`, `/health`, `/sessions`. Enough for asking questions and viewing history. Choose it if all you plan to do is ask.
   - **Full power** - like being signed in through a browser. Required for `javis task add`, `javis brain`, `javis loops`.
4. Click **Create token**. The string appears **exactly once**: the server hashes it when storing, and there is no way to see it again. Copy it right away.

Lose the token and you cannot look it up, only create a new one and revoke the old one. That is deliberate.

## Step 2: connect the CLI to your Javis

```bash
javis login https://your-javis.com
```

It asks for the token, which you paste. Or give it directly:

```bash
javis login https://your-javis.com --token jvs_xxxxx
```

The CLI **actually tests the connection** before saving, so a wrong address or a wrong token surfaces here rather than at your first question.

The configuration is saved at `~/.javis/config.json` with `600` permissions (only the machine's owner can read it). That file holds the token, so keep it out of repos and public backups.

### Several Javis instances at once

```bash
javis login http://localhost:7777 --name home
javis login https://javis.company.com --name company --brain brain-company
javis --profile company "how is the company side this week"
javis profiles          # list saved profiles, the * marks the default
```

### Setting it through environment variables (for CI, Docker, servers)

These variables override the configuration file, useful when you do not want the token on disk:

| Variable | Meaning |
|---|---|
| `JAVIS_URL` | the Javis server address |
| `JAVIS_TOKEN` | the API token |
| `JAVIS_BRAIN` | the default brain |
| `JAVIS_PROFILE` | the default profile name |

## Everyday use

### Asking one question

```bash
javis "how is revenue this week"
javis "summarise last week's notes"
```

No subcommand is needed, typing the question runs it. Sitting at the terminal you see progress lines alongside (which MCP Javis is calling, which file it is reading), then the answer.

### A continuous session

```bash
javis chat
```

Type, Enter, read the answer, type again. The whole session shares one conversation id so Javis keeps the thread: asking "and last month?" is understood as being about what you just discussed. `Ctrl+D` or `/thoat` exits.

To resume the same thread on a later run, set the session id yourself:

```bash
javis chat --session sales-august
```

### Composing in scripts

This is the CLI's most valuable reason to exist. The answer goes to stdout and progress to stderr, so redirecting gives a clean file:

```bash
javis "write a summary of this week's sales" > weekly-report.md
javis -q "how are things today" | mail -s "Javis" boss@company.com
```

The `-q` flag also turns off the progress lines. On failure the CLI exits non-zero and **prints nothing to stdout**, so `&&` behaves correctly in a script.

### Checking the status

```bash
javis status
```

It reports the Javis version, whether a newer one exists, which brain engine is running, where the token saving level is set, and how much was saved over the last 24 hours.

### Queueing work, browsing the brain, viewing loops

These commands need a **full power** token.

```bash
javis task add "draft a post about the new product"     # queue one Kanban job
javis task add "run the monthly report" --mode auto     # suggest (default) | auto | full
javis tasks                                              # see the jobs and which column they are in

javis brain ls                                           # list the brain root
javis brain ls "05 - Data Cache"
javis brain cat "Memory/MEMORY.md"

javis loops                                              # which loops are on, at what level
```

Queued work runs in the background on the server. The result returns to wherever you queued it from, and progress is on the **Work** page of the dashboard or from `javis tasks` again.

### Starting Javis on this very machine

If the machine has Javis installed (the repo cloned):

```bash
javis up
```

It finds the install (through the `JAVIS_HOME` variable, the current folder, or `~/javis-os`), starts it, then saves a `local` profile so `javis "..."` works next time. If Javis is already running, it recognises that and does not start a second one.

When it cannot find an install it says so plainly: **`javis up` does not contain the server inside it**, and there are only three ways forward (set `JAVIS_HOME`, run from inside the Javis folder, or `javis login` to a Javis somewhere else).

## Managing tokens

Go to **Account > API tokens** in the dashboard. The list shows the name, the first 12 characters, the scope, and the **last used** time; a token you do not recognise being used regularly is the sign to revoke it right away.

Clicking **Revoke** kills the token instantly, any machine using it loses its connection at once, and it cannot be undone.

A few things worth knowing about how Javis keeps tokens:

- **Only a hash is on disk** (SHA-256). Whoever can read the server's config file still cannot obtain the token.
- **A token cannot create a token.** Creating a new one requires a signed-in browser. If a token leaks, whoever holds it cannot mint another, so revoking ends it.
- **But a token can revoke itself.** Losing a laptop with no way to open a browser still lets you take the credential down.
- **More than 10 wrong tokens in 5 minutes blocks that IP for 15 minutes**, and each failure is written into `auth_audit.jsonl` (only the first 12 characters, because log files are often attached to bug reports). A token-guessing run becomes visible instead of running silently for months.

## When something goes wrong

**"Not connected to any Javis"** - run `javis login <address>` first.

**A 401 or "invalid token"** - the token is wrong or was revoked. Create a new one at Account > API tokens then `javis login` again.

**A 403 on `javis task add` or `javis brain ls`** - your token is the **chat only** kind. Create a **full power** token for these commands.

**Temporarily blocked** - too many wrong tokens in a row. Wait 15 minutes, or restart the Javis server.

**Cannot connect** - check that the Javis server is still running (`javis status`, or open the dashboard in a browser). If Javis is on a VPS, check the port and the domain.

**Vietnamese text renders wrong on Windows** - run `chcp 65001` in the terminal first, or use Windows Terminal instead of the old cmd.exe.

See also [17 - Troubleshooting and FAQ](17-troubleshooting.md).

## Why the CLI cannot run on its own

A fair question: why not build a standalone agent in the terminal with no server at all?

Because almost everything that makes Javis what it is demands a **long-lived** process: loops on a cycle, reminders waiting for their time, the MCP Hub holding connections to the POS and the ads platform, the capability store holding the registry, the token-saving runtime learning turn by turn. A CLI that exits when you finish typing is no home for those.

Building a second implementation means copying all of it then letting the two drift apart, and whichever has fewer users keeps its bugs quietly. So the CLI goes through **the very same core** the dashboard and Telegram use. In exchange: a new feature added to Javis appears in the CLI immediately, with nothing to fix in two places.

Design details in the [CLI spec](../dev/2026-08-cli-spec.md).

## Related

- [02 - Chat and voice](02-chat-and-voice.md) - the web channel.
- [11 - The Telegram channel](11-telegram.md) - the phone channel.
- [14 - Security and accounts](14-security-and-accounts.md) - passwords, sign-in, secret-key encryption.
- [21 - Work (Kanban)](21-kanban-work.md) - where the work `javis task add` queues actually runs.
