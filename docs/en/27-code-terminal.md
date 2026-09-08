# The Code group: a Terminal right in the dashboard

*[Tiếng Việt](../27-tab-code-terminal.md) · **English***

**Code** is its own group on the navigation rail, Javis's developer-style workspace. The first item in the group is **Terminal**: a real command line, running on the very machine running Javis, opened right in the browser. No more opening SSH in another window.

## What this feature is

The terminal here is **a real operating-system pseudo-terminal**, not a simulated text box. Which means:

- Every command you would type over SSH works: `git pull`, `ls`, `tail -f`, `pip install`, `agy`, `claude auth login`...
- Full-screen programs work too: `htop`, `vim`, `nano`, `less`.
- There are colours, Tab completion, command history (up and down arrows), and `Ctrl+C` kills the running command rather than the whole session.
- Resizing the window is noticed by the shell immediately, so text does not wrap oddly.

The Code group is laid out to grow: today it contains only **Terminal**, and other developer tools will become further items in the same group.

## Where to open it in Javis

1. Open the Javis dashboard (default port 7777).
2. On the left navigation rail, open the **Code** group and click **Terminal**.
3. The terminal opens and connects itself. Click the black panel and type as in any terminal.

The shell opens in the **HOME folder of the user running Javis**, exactly like an ordinary terminal on the machine, which suits this tab's main job: installing and signing into CLIs (`agy`, `codex login`...). To get into the brain, type `cd "$JAVIS_BRAIN"`, a variable always pointing at the root of the selected brain.

## Several tabs, each its own shell

Right above the terminal panel is a tab strip, like a browser's:

- Click **+** to open another tab; each is a completely separate shell, and work in one does not touch the other. Handy for `tail -f` on a log in one tab while typing commands in another.
- Click a tab name to switch. A hidden tab keeps running normally: commands do not stop and output is not lost.
- Clicking the **x** on a tab closes that session for good (killing the shell). Closing the last tab makes Javis open a clean one in its place.
- At most **4 tabs** (exactly the server's session ceiling, counted across every browser window). At the ceiling the **+** button locks itself.
- After F5 or navigating away and back: the whole set of tabs reopens, with the tab you were viewing still in view.

## The top bar

| Item | Meaning |
|---|---|
| The dot plus status text | For the tab in view. Green = running. Red = disconnected (Javis reconnects itself). Grey = the shell exited. |
| The path | The folder the shell started in. On a narrow screen it is hidden to make room for the buttons. |
| **Clear** | Clears the screen of the tab in view, like the `clear` command. |
| **Restart** | Closes the session of the tab in view entirely (killing the shell) then opens a clean session in the same tab. Use it when the shell hangs or you want a fresh start. |

## Sessions keep running while you are away

This is the most important thing in daily use: **navigating away or reloading the page does NOT kill the shell.**

- Mid `npm install` and you click over to the Chat page: the command keeps running, in EVERY tab, not only the one in view. Coming back to the Code page shows the whole set of tabs, each as far along as it has got.
- Losing the network, closing the laptop, F5: Javis reconnects to those very sessions.
- Only when nobody comes back for **30 minutes** does Javis close the sessions, so forgotten processes do not run forever.
- To close one now, click the **x** on the tab, click **Restart**, or type `exit`.

At most **4 sessions** can be open at once (counted across every browser window). At the ceiling, Javis says so plainly rather than silently opening more.

## Simple mode on Windows

Python on Windows has no pseudo-terminal, so there the Code tab runs in **simple mode** and shows a warning line right above the panel:

- Type a whole line then Enter, and the command runs with output flowing back. Backspace edits, `Ctrl+C` interrupts a running command.
- There is **no** Tab completion, **no** arrow-key command history, and full-screen programs (`vim`, `htop`) do **not** work.

Linux, macOS and every Docker build run the full mode.

## Who can get in

The terminal is where arbitrary commands run on the server, which is the highest privilege the dashboard can grant. So:

- Only a **signed-in browser** can reach it. API tokens (the `jvs_...` kind used by scripts and the CLI) **cannot** open the terminal, not even a `full`-scope token.
- When Javis runs public (VPS, Docker) login is mandatory, so the terminal sits behind that same fence. See [Security and accounts](14-security-and-accounts.md).
- The shell inherits the server's environment variables, including the keys in `.env`. Exactly like the machine owner's terminal, but worth knowing when you show your screen to someone.
- To remove the feature entirely: set `JAVIS_TERMINAL=0` and restart Javis. The Code tab then shows a notice that it is off rather than an empty panel.

## Environment variables

| Variable | Meaning | Default |
|---|---|---|
| `JAVIS_TERMINAL` | `0`/`off`/`false`/`no` = remove the terminal entirely | On |
| `JAVIS_TERMINAL_SHELL` | The path of the shell to run | `$SHELL`, falling back to `bash`/`sh`. Windows: `powershell.exe` then `cmd.exe` |
| `JAVIS_TERMINAL_CWD` | The folder the shell opens in | The HOME of the user running Javis |
| `JAVIS_TERMINAL_REMOTE` | Tell CLIs the user is sitting at another machine (`SSH_CONNECTION`), so a Google/Anthropic sign-in asks where to paste the code instead of waiting for a browser on this machine | Auto: on for a server with no screen (VPS, Docker), off on native Windows/macOS and on Linux with a display |

How to set variables: [.env configuration](16-env-configuration.md).

## Common problems

**Opening Terminal shows "The terminal is off on this machine".** The server has `JAVIS_TERMINAL=0`. Remove that variable from `.env` then restart Javis.

**It reports "4 terminal sessions are already open".** The ceiling of 4 counts across every browser window. Close a tab (the **x**) in the window holding it, or wait 30 minutes for Javis to clear the unwatched sessions.

**Text wraps oddly and table borders are misaligned.** Click the terminal panel then resize the browser window once so it re-measures. If it is still off, type `clear`.

**Tab produces no completion.** You are in simple mode (Windows). That is an operating-system limit, not a configuration error.

**The shell exits the moment it opens.** Check that `JAVIS_TERMINAL_SHELL` points at a real executable and that the folder in `JAVIS_TERMINAL_CWD` exists.

**Typing `agy` (Antigravity) prints a link then sits there with nowhere to paste the code.** `agy` collects the code through a loopback port on the machine it runs on, and your browser is on a different machine, so it never reaches that port. Since 0.55.46 the terminal declares itself a remote session, so `agy` asks where to paste: after signing into Google, copy the whole `http://localhost:...` address your browser fails to open and paste it into the terminal. On an older `agy` that does not ask, open a second terminal session and run `curl "<the address you copied>"`.

## Related

- [05 - File manager](05-file-manager.md) - browsing and editing those same folders through the interface.
- [24 - The Javis CLI (terminal)](24-cli.md) - the opposite direction: typing `javis "..."` from your own machine's terminal.
- [14 - Security and accounts](14-security-and-accounts.md) - the login fence covering the Code group.
- [16 - .env configuration](16-env-configuration.md) - every environment variable.
