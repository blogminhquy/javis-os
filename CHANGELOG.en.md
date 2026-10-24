# Changelog

*[Tiếng Việt](CHANGELOG.md) · **English***

Javis OS release history, newest first. You can also read it inside the app under **Settings → Updates**.

English entries start at 0.66.0. Every earlier release is described in the Vietnamese [CHANGELOG.md](CHANGELOG.md), which remains the maintainer's original; the in-app Updates page shows those older entries in Vietnamese.

Format: each release is a `## [x.y.z] - date` block, with changes grouped under `### Added / Fixed / Improved / Security`.

## [0.301.0] - 2026-10-24
### Added
- **Facebook Messenger card on the Connections page.** Paste the Page ID, App ID, App secret and any token from Graph API Explorer; Javis derives a non-expiring Page token, registers the webhook (with `messages`) and subscribes the Page to the app. No more user token pasted by mistake and errors 100 or 210.
- **A step-by-step checklist** after connecting: token, permissions, App secret, webhook, Page subscription, running bot. Every red row says how to fix it.
- Every Page has **Check**, **Repair** and **New token** buttons. When the bot goes silent, ask Javis: any brain can check and repair it with the `messenger_check` tool.

## [0.300.0] - 2026-10-24
### Fixed
- **One Hostinger install link works on both Ubuntu 24 and Ubuntu 26.** A plain Ubuntu 26 image has no Traefik, so pasting the link used to give a running Javis whose domain never got HTTPS. The link now carries an HTTPS gateway (Caddy) that turns itself on when there is no Traefik and issues the certificate for `DOMAIN_NAME`; on a VPS with Traefik it stays out of the way.
### Improved
- The install docs say it plainly: Traefik only provides HTTPS, updates are done by the bundled Watchtower, so the **Update now** button works the same on every Ubuntu release.

## [0.298.0] - 2026-10-23
### Fixed
- **A voice picked on one device now applies everywhere.** The reading voice used to live only in the open browser, so picking a female voice on the laptop left the phone on its old voice however many times you saved. It is now saved in Javis, so every device and the voice notes sent through Telegram and Zalo use it.
### Improved
- **The Voice card says which voice you will hear.** Every voice says Female or Male (ChatGPT Live voices like Juniper and Cove too). The top of the card says which voice the call uses and which reads answers.
- **Two clearly separate voice fields:** Call voice and Answer reading voice. When they differ in gender, a warning offers a one-tap switch.
- **Saved shows right under the field you changed**, not at the bottom of the card.
- **A clearer agent Save button:** an orange button with an icon that says Save changes, pinned at the bottom of the form, saying "Unsaved changes" and "Saved". Ctrl+S saves too.

## [0.296.0] - 2026-10-23
### Improved
- **Generate skill proposals from tuning evidence.** Owners can run the baseline on authorized data, seal its results, and ask the model for up to two patches to review.
- **Assess meaning and dependencies separately.** Each patch has an independent assessment record; missing evidence stays unknown and owner approval remains separate.
- **Stronger experiment stop and recovery.** Retain data and active work until cleanup is verified, including abrupt host termination on Windows. Changed-candidate execution and live activation remain disabled.

## [0.295.0] - 2026-10-23
### Security
- **Node.js 2026-10-21 security fixes.** Node.js disclosed 10 vulnerabilities, the worst a Brotli flaw that allows remote code execution. The new Docker image runs the patched Node.js 22.23.4, so Docker installs only need to update Javis.
- **Javis checks this machine's Node.js.** If it runs an unpatched or end-of-life release (Node 20 and older), the News bell shows a Security item with the installed version and the upgrade command for Windows, Mac or Linux. Patched machines are not nagged.
- **Fresh installs get the patched release.** `install.sh` no longer accepts Node 20 or an old Node 22: it installs the latest Node.js 22, and warns about an unpatched Node 24 or 26 so you can upgrade it yourself.

## [0.293.0] - 2026-10-23
### Improved
- **Manage controlled skill experiments.** Freeze experiments, chosen edit authority and paired schedules; reports retain exact published results and complete trial coverage. Owners can safely stop or recover experiments with active work. Changed-candidate execution, final qualification and live activation remain disabled.

## [0.292.0] - 2026-10-23
### Added
- **Review skill body proposals.** Studio displays complete baseline text, diffs and stored trial artifacts. Owners can stage a proposal, authorize an exact region or diff, and revoke edit authority. Encrypted proposal storage and downloads preserve exact hashes and bytes. Changed-candidate execution and live activation remain disabled.

## [0.291.0] - 2026-10-23
### Added
- **Prepare reproducible agent and skill trials.** Build isolated execution, fixed cases and acceptance evidence to test changes without touching live content or actions. Live brains are not enabled automatically.

## [0.290.0] - 2026-10-22
### Added
- **A goal bar right above the chat box.** Once you set `/goal`, a bar tracks it: the goal text, a running timer, buttons to delete, pause or resume, and an arrow for details (which round, what is still missing). It shows in every chat view.
- **Several goals at once.** One goal per conversation. With two or more, the bar starts with a number; press it to drop down the list and press a row to open that conversation.
- **Typed commands are highlighted.** Type `/goal`, `/plan` or a skill name into the chat box and the command part turns orange, so you can see what Javis will read as a command.
### Improved
- **Goals pause instead of vanishing.** Pressing Stop or typing a message mid-run only pauses the goal; moving to another conversation makes it wait and it carries on when you come back; it survives a page reload on the bar.
- **A tidy, aligned / command menu.** One line per command, a shared command column so descriptions line up, smaller text, and group headings for Commands, Agents, Workflows and Skill.

## [0.289.0] - 2026-10-22
### Fixed
- **Webhooks: the AI now reads the whole event.** It used to get only the first 8,000 characters, so even a one-item POSCake order lost its order id and total, and a prompt that decides by the order's status could guess wrong. The AI now gets up to 40,000 characters, written on one line; anything longer is cut and the AI is told so.
- The event detail page shows up to 64,000 characters instead of 8,000.
### Improved
- The webhook guide uses POSCake's real field names and adds a one-webhook-for-every-source setup where the prompt decides what to do.

## [0.287.0] - 2026-10-22
### Added
- **Lay the foundation for evidence-based improvements.** Track agent and skill revisions for isolated comparisons while preserving current content. Trials and activation on live brains remain disabled.

## [0.286.0] - 2026-10-22
### Fixed
- **Choosing a model in an assistant's chat no longer changes the main chat's model.** For every assistant and Javis Core: the model chosen there is pinned to that chat only. An assistant with no model of its own follows the main model, and a new "Follow the main chat's model" row removes the pin.
- **When an assistant's pinned model runs out of plan quota, the chat runs on the main chat's model for now,** and goes back to the pinned model once the plan resets.
- **Javis Core follows the main chat's reasoning level** until you pick one for it. A level set in an assistant's chat is always saved for that assistant.

## [0.285.0] - 2026-10-22
### Improved
- **Review the actual Team result.** Opt-in teams get default acceptance criteria; confirmation binds to the saved result and its version.
- **See usage without sacrificing quality.** Request counts and known, estimated or subscription-equivalent costs are separated. A reference amount never stops work or changes its model.
- **Prepare a fair business comparison.** The paired pilot supports isolated dry runs; real business results still require real inputs and owner grading.

## [0.284.0] - 2026-10-22
### Fixed
- **Changing Javis Core's reasoning level no longer changes the main chat's.** Javis Core now has its own level like every other assistant, Medium by default. Its chats used to share the main chat's level, so changing one changed the other.
### Improved
- The reasoning level in an assistant's settings uses the same English names as the main chat: Off, Light, Medium, High, Extra, Ultra.

## [0.282.0] - 2026-10-22
### Fixed
- **A Zalo bot no longer goes "deaf" while another session of the same account runs.** After today's update, a leftover old Zalo copy kept taking the connection, so the bot only heard messages for a few seconds after each reconnect and missed tags and private messages. Javis now stops old Zalo copies on the machine, the bot card turns red, and the bell tells you when the other session is elsewhere (Zalo Web, another Javis).
- **A bot reply Zalo did not accept now shows as a send error,** instead of looking sent while the customer saw nothing. Zalo MCP 1.6.1 also sends through the new session after every reconnect.
### Added
- **The bot reads the Zalo tags of a chat** (Family, Friends, Work, Customer...), so it knows who it is talking to. Personal Zalo bots get **"Never answer chats with these Zalo tags"**: tick tags listed from Zalo or type one, and the bot stays silent in those chats.
- **Personal Zalo bots decide to send several short messages** (up to 4) when an answer has two or more points, instead of one long hard-to-read block.

## [0.281.0] - 2026-10-22
### Improved
- **Running the test suite no longer fills drive C.** Each run used to leave over 1,000 leftover folders in the Windows Temp folder, at one point piling up to 50,000 folders and about 30 GB. Each test file now gets its own temporary folder, deleted when it finishes.
- **An interrupted run doesn't leave junk for long.** Folders from a run that was stopped halfway are cleared on the next test run.

## [0.280.0] - 2026-10-22
### Improved
- **Private 1-1 chats: the bot can stay silent and alert you on a hard question.** In Auto-judge mode a private message now has a third outcome besides reply and silence: when the documents and the Agent cannot settle it, or you must decide yourself (a discount, a complaint, a refund, a booking), the bot no longer guesses. It stays silent and alerts you in the Javis bell.
- **The alert says what the customer wrote and the bot's note on why it did not answer.** The message stays in the Bot inbox for you to reply by hand. A customer firing several hard questions rings the bell once per 10 minutes; the bot log still records each one.
- **Try bot shows "The bot would stay silent and alert you in the bell"** with the bot's note, so you can test before going live. Your Agent's instructions still win: if the Agent says how to handle a kind of message, the bot does exactly that.

## [0.278.0] - 2026-10-22
### Improved
- **The Team chat now works like the main chat.** Copying a message, the code Copy button, Enter on a phone (a new line, not send), swipe to quote, quoting just the selected part and "Show more" on long messages all behave as in the main chat.
- **Pictures you send in a team open in the in-app viewer;** a missing picture shows a notice instead of a broken icon.
- **Your message appears at once,** and if the network drops you get Try again. A stuck upload now says what went wrong instead of spinning.
- **Reading older messages, the chat no longer jumps down,** and a "New messages" button brings you back; new messages no longer clear your text selection. Buttons inside answer cards now send into the team.

## [0.276.0] - 2026-10-22
### Security
- **Webhooks also mask staff account ids.** The masked event view and exported fixtures used to keep the id of whoever created, edited or sold an order, because the key was `id`. Every value under a creator, editor, seller or care block is now masked like customer data.
- The POSCake fixture in the repository was exported again and holds no account id.
### Improved
- The staging rehearsal deletes its temporary folder when every step passes (kept on a failure, or with `--keep`).

## [0.275.0] - 2026-10-22
### Fixed
- **Background work is more reliable.** Reminders fire on time in every brain, including brains with no loop. A network error right after the machine wakes is now recorded as failed and retried a few minutes later, without re-sending what already went out. When the Claude plan names its reset time (for example 1:50am), Javis schedules the retry itself. Loops remember earlier rounds, so they stop repeating a suggestion.
- **Teams work more smoothly.** Members read Excel files (every sheet, formula results, error cells) and see which PDF pages are scans, without per-command approvals. An approved command is no longer blocked again, and approval cards show the real command. Steps that must run in order do, and a job with steps left is never marked Done.
- **Projects and partners work on every channel.** A project's rules apply on the CLI and Telegram too, and stay when the conversation moves to a new session; the `javis` command gains `--project`. On Telegram, start with `@partner-name` to have that partner answer, `/agent name` hands it the whole chat, `/agent off` brings Javis back.
- **The GitHub backup no longer pushes partners' raw run logs or the text extracted from attachments.** Copies pushed before stay in the repo; once every machine is updated you can delete them on GitHub.

### Improved
- **Clearer where a slip is costly.** The Add-work form says plainly that Full may edit files, run commands and send messages without asking (still the default). The Work board box is renamed "Review the result after it runs". Disconnect on the Claude Code card asks before signing out, and a switch turns off Claude Code's daily auto-update on screen. The Usage page prices work run on DeepSeek and counts Team turns.
- **Fixes for bugs a customer reported on 0.270.0.**

## [0.274.0] - 2026-10-22
### Added
- **Webhooks become a durable event inbox.** Each event is written to disk before Javis answers "received" (202). If the machine stops, updates or crashes midway, Javis carries on when it starts again and no order is lost.
- **Strict filters and duplicate checks.** Filters respect data types (the number 1 is not the text "1"), can check each item of an order, and a duplicate key can combine several fields (shop, order id, status) with an expiry. An event that does not match is logged with the reason and uses no AI run.
- **Forward without AI:** to an HTTP address (the original body unchanged), a Google Apps Script (done only once it returns a receipt) or a plugin such as POSCake Zalo. Each target runs on its own, one can wait for another, and Retry resends only the one that failed.
- **Automatic retries** after 1, 5 and then 30 minutes, for up to 24 hours. Work that may have happened with an unclear result is held for you to decide, never resent on its own.
- **The webhook page has three parts: Configuration, Events, Health.** Two separate switches: Stop receiving (new events are refused) and Pause processing (still received and stored, just not run yet).
- **A real test send with a preview:** paste a sample, see what each action would do, then send. Test events have their own duplicate space.
- **A timeline for each event:** received, verified, filtered, dispatched, each attempt, receipt, result and notice. Search by order id and by date range.
- **Process again with the current setup**, with a preview that says which actions already succeeded, or may have acted, and could act once more. A hook changed after the preview asks for a new preview.
- **Retry all blocked:** after a fix outside the hook (plugin switched back on, key changed at the receiver), one button runs them all again.
- **Failed events keep their payload** until you retry or **Delete** them, so Retry always sends what was received.
- **Signature checks for Stripe, GitHub, Shopify and Systeme.io**, each done its own way, with an overlap period when a key changes. These senders need no Javis key: their signature is enough. Systeme.io was not tried with a real account, so it is marked unverified. POSCake has no signature check yet because there is no official documentation.
- **A rollback tool** (`server/webhook_rollback.py`): backs up the store, exports unfinished events for reconciliation and writes the webhook list back for the older build.
### Security
- API keys and signing keys are encrypted on disk, never shown in the interface and never kept in the configuration history. Back up `webhook_keys.json` together with `webhook_secrets.json`.
- Event payloads are masked by default: only ids, statuses, times, amounts, counts and product names show; every other value is hidden. Viewing or exporting the raw payload is recorded in the audit log.
- New webhooks accept the key only in a header, not as `?token=` in the address (older webhooks keep working). An address that keeps sending a wrong key is held off for a while.
- Outgoing calls always connect to the address that was checked, so a domain cannot switch to an internal address midway.
### Improved
- New limits per webhook: 300 events per minute, 10,000 waiting events. The AI allowance (30 per hour) applies to the AI part only and never blocks code-only forwarding; when it runs out, orders are still kept.
- Notifications: every run, errors only (repeated errors grouped into one), a daily digest in the time zone you pick, or off. Off still keeps system alerts such as a nearly full disk.
- On first start of this version the webhook list moves into the new store (with a backup) and older webhooks run as before.
- A domain that briefly fails to resolve is retried later instead of failing for good.
- Javis starts a little faster: the webhook platform, the push notification crypto library and uvicorn load only when needed.
### Fixed
- An Apps Script that ran but answered with an unreadable page is now "unknown", not "failed", so Retry does not write a second row.
- Saving from an old tab, or from two tabs at once, never brings a secret key back to an older value.
- Deleting a webhook cancels its waiting events, and retention removes them, so no customer data is kept forever.
- List filters (`[*]`) now treat "unknown" as unknown: a `not(any ...)` condition over an order with an item missing the field may now ignore what ran before. Check such filters with Test rules.
- When several events call one plugin at once, the one left waiting for its turn no longer spends an attempt with nothing sent.
- A quarantined event (the rules could not read it) now tells you, grouped into one message, and keeps its body for 30 days. Processing again an order that already ran as another event is refused, never sent twice. Repeated failures are grouped by kind, not one message per order.
- **A retry after an overload refusal (429) now runs.** Before, the duplicate key was kept, so the retry was reported as a duplicate and the order never ran.

## [0.272.0] - 2026-10-22
### Added
- **Paste or drag images straight into a note.** Images are compressed to WebP in the browser, saved in the brain's `images/` folder and inserted into the note; drag the image corner to resize. (Contributed by @quangndna.)
- **Lists continue by themselves in the note editor.** Enter at the end of a bullet, task or numbered item adds the next one; Tab and Shift+Tab indent. Not inside code blocks. (Contributed by @quangndna.)
- **Open today's daily note fast:** the calendar button on the note toolbar, or Ctrl+D (Cmd+D on Mac) while in the notes panel. It opens the note if it exists, creates it otherwise, never overwrites. (Contributed by @quangndna.)
### Fixed
- **Stop really stops Antigravity.** An Antigravity turn used to keep running in the background after Stop, sometimes for 15 minutes. A turn that stays silent too long now has a real deadline. (Contributed by @Aurus2207.)
- Stop now also ends the child processes an engine started, none are left behind.

## [0.270.0] - 2026-10-21
### Fixed
- **npx connections no longer break for good after their first install.** If Javis had just restarted while a connection was still downloading its package, it could be cut off halfway, leaving a half-installed copy that failed with MODULE_NOT_FOUND forever. Javis now waits for the first install, cleans up half-installed copies, and after each restart tries every connection and tells you once if any is not working. A connection still on its first install shows a yellow dot instead of red. (Contributed by @dev23072005.)
- **An agent with an old Codex model no longer changes your main model.** This covers assistant chats on the dashboard and turns sent through `/chat`: Javis fixes only that assistant's or that session's model.
### Added
- **Call one specific assistant through `/chat` and the `javis` command.** An outside app that adds `agent=<slug>` (or `javis --agent <slug>`) runs that turn with the assistant's prompt, skills and model, in its own session, and lessons are recorded as in a dashboard chat. An assistant or brain that does not exist gets a clear error instead of silently running the main model. (Contributed by @QuanAMG.)

## [0.269.0] - 2026-10-21
### Fixed
- **The Update button works again when Javis runs as a normal user.** Since 0.267.0, a machine running the Javis service as a non-root user failed every update with "Interactive authentication required" and stayed on the old version. Javis now falls back to a way that needs no admin rights: it downloads the new version while the old one keeps running, then restarts once. Machines running as root are unchanged.
- If the machine still does not allow it, the screen shows the manual update command and one command (`sudo loginctl enable-linger`) that makes the button work from then on.
- **Note:** a machine stuck on 0.267.0 or 0.268.0 needs one manual update to reach this version (`git pull --ff-only`, install the libraries, `sudo systemctl restart javis`). After that the Update button works as usual.

## [0.268.0] - 2026-10-21
### Fixed
- **SharePoint files read through Composio at Read-only.** Every SharePoint command, even listing a folder or downloading a file to read, was blocked as dangerous because the app name starts with the word SHARE. Javis now ignores the app name when it judges a command: reads run at Read-only, while upload, share and delete still need Full access.

## [0.267.0] - 2026-10-21
### Fixed
- **Teams stop asking for approval when an assistant only reads files.** In an "approval needed" team, a chained read (`cd ...; cat ...; sed -n ...; grep "a\|b" ...`) used to count as an outside action and stop the task for the owner. Each command in the chain is now checked on its own: reading, searching and printing run straight away. Writing files, deleting, running code and sending still wait for approval.
- **The Team chat no longer freezes on a phone.** A send that hit a flaky network could leave the send button locked until the app was closed. Every server call now gives up after 30 seconds and says the network dropped; press send again (it is never sent twice). Coming back to the app after more than 20 seconds reloads the open team.
- **A VPS running a self-built image is now told how to update.** Javis moved from a computer to a VPS by packing the image on the spot (a name like `javis-cwi:pc-0.206.0`) stayed on its old version whatever you pressed, because that image lives in no registry. The Updates page now says so and shows how to switch to the official image once, keeping all your data. The steps are in DEPLOY.md, Updating section.
- **Updating on a VPS no longer leaves Javis switched off.** On a systemd install, stopping the service also killed the updater halfway, so Javis stopped and never came back. The updater now moves out on its own first, then stops the service. Installs with their own name (`JAVIS_NAME`, for example `javis-shop`) now stop and start their own service.

## [0.266.0] - 2026-10-21
### Improved
- **Holding a message on a phone selects and copies text again.** The main chat drops the dimmed screen, the emoji row and the Reply / Copy card on a long press: holding a finger now brings up the phone's own selection handles and Copy button, so you copy exactly the part you need. Reply, Copy, Edit and Send again stay in the small row that appears when you tap a message, and swiping a message left still quotes it. To pick another emoji, hold the like button at the corner of the bubble.

## [0.265.0] - 2026-10-21
### Improved
- **The docs now explain how to connect an Anthropic Compatible gateway.** The Models guide gains section C1: what to get from the seller, which 3 boxes to fill, how to make it the main model, and a table for each error message. Send customers a link to that section and they can do it themselves.

## [0.263.0] - 2026-10-20
### Fixed
- **Bots no longer vanish from the Chatbot page.** A bot saved with the full path of Brain Default (created from Telegram, from chat or by an older version) now shows in the list together with its channel accounts, so you can change its token or settings right away instead of deleting and recreating it. Bots of other brains still stay out.
- Deleting an assistant that a bot still uses is now always blocked, however the assistant's brain was written.
### Added
- **The star button menu has a Team chat item** on its last row, which opens the Team page.

## [0.262.0] - 2026-10-20
### Added
- **Every brain can search and read the web.** OpenRouter, OpenAI, Anthropic API, Gemini, Groq, DeepSeek and Ollama now search the internet and read web pages and PDFs to answer about news, prices and documentation instead of guessing from memory. No key needed: DuckDuckGo by default. With a Tavily or Brave key (`TAVILY_API_KEY`, `BRAVE_API_KEY`) or your own SearXNG (`SEARXNG_URL`) Javis uses that first. Long pages are read in parts, nothing is cut off.
- **Every chat gets the full Code page toolkit.** The normal chat, assistant chats and your Telegram now also have the terminal, section edits, file search, restore points and 150 tool rounds per turn. With no pinned folder Javis works right in the brain; with one, it works in that folder.
- **Undo in every chat**: the composer's "+" menu has "Undo Javis's changes", which opens the same Undo panel as the Code page.
### Improved
- File reads, the terminal and web reads can return up to 60,000 characters at a time (normal chat used to cut at 8,000), so nothing is lost mid-way. Results from outside connections (POS, ads...) keep the old cap so chat turns do not grow heavier.
### Security
- Web reads never touch the internal network (localhost, the LAN, a cloud server's metadata address), checked again on every redirect. Page content is marked as data, not instructions, so a page that plants commands cannot steer Javis.
- Chatbots talking to customers get neither the terminal nor the web tools, even at Full access.

## [0.261.0] - 2026-10-20
### Improved
- **The Login vault is now called Cookies**, with a cookie icon, so it fits the sidebar. Buttons and text on the page say "cookies" too.
- **Upload a cookie file.** Press **Upload file** at the top of the page (or **Choose file** in the form, or drop the file on the box): Javis takes a Cookie-Editor JSON file or a `cookies.txt`, and names the entry after the file. No more opening the file to copy and paste.

## [0.260.0] - 2026-10-20
### Improved
- **Calling several members in one message makes them answer at the same time.** Before, @ three members meant waiting for each one in turn. For the old way (each reads the previous answer first), open the team's Advanced section and set "When one message calls several members" to One by one.
- **When the leader splits a job, the members work at the same time**, up to 3 per round, and the summary comes once all are done. If one member hits an error, the others' parts are kept and Retry only redoes the failed part.
- **Teams of the same brain can run tool work side by side.** Before, every step that read or wrote files in one brain waited in line. Now each working folder allows up to 3 turns at once, and a team with its own pinned folder never waits for another team. When they run together, each member is told to edit only the files of its own part.
- For the stricter old behavior set `JAVIS_TEAM_TOOL_SLOTS=1` (one writer at a time) or `JAVIS_TEAM_JOB_PARALLEL=1` (one step at a time).

## [0.257.0] - 2026-10-20
### Improved
- **One assistant can work in several teams at once.** Before, an assistant answering in one team made every other team wait, sometimes up to 30 minutes. Each team now has its own thread, so they run in parallel. Within one team an assistant still answers one message at a time.
- **More teams run jobs at once:** up from 2 to 4. Change it with `JAVIS_TEAM_PARALLEL`.
- **A brake so a subscription plan is not overloaded.** Each plan engine (Claude Code, ChatGPT, Grok, Antigravity) runs at most 3 team turns at once, each API-key engine at most 6. Turns over the limit wait, nothing is lost. Change with `JAVIS_TEAM_CLI_SLOTS` and `JAVIS_TEAM_API_SLOTS`.
- One limit remains: **Work steps with tools** of teams in the same brain still take turns, so two teams never overwrite the same file. A later release loosens this.

## [0.256.0] - 2026-10-20
### Added
- **API brains can really code on the Code page.** OpenRouter, OpenAI, Anthropic API, Gemini, Groq, DeepSeek and Ollama now do a developer's job in the folder you attach: search the code, read it in pages, change just a few lines, run commands, start a dev server. The design borrows from Hermes Agent.
- **Edit a section instead of rewriting the whole file.** Javis replaces only the part that needs changing, even when the model gets indentation or quotes slightly wrong, and shows the diff. If the edit breaks the file's syntax you are told right away. You can also search code by content or by file name.
- **A real terminal at Full access.** Commands with `|`, `&&` and `cd` work, and the folder is remembered between commands. Dev servers and long jobs run in the background; Javis reads their logs, can stop them, and reports in the chat when they finish.
- **An Undo button on the Code page.** Before the first turn that edits files, Javis saves a restore point. Undo shows which files changed and the differences, then puts them back. Files you edited yourself afterwards stay as they are. Your project's git is never touched, and folders without git work too.
### Fixed
- Before this release an API brain in a Code session could not actually read any file of the project, because the working folder was never passed in. It is now.
- A new file at the project root no longer lands in the brain folder by mistake.
- At the Plan level the command tool no longer appears.
### Improved
- A turn on the Code page can use up to 150 tool rounds (normal chat stays at 30), and with 10 left Javis is told to sum up and wrap up. Change it with `JAVIS_MAX_TOOL_ROUNDS_CODING`.
### Security
- The terminal does not carry Javis's API keys and its output has secrets masked. Commands that could wreck the whole machine (deleting system folders, formatting disks, `sudo`, shutting down) are blocked at every level. Every command is logged.

## [0.255.0] - 2026-10-20
### Improved
- **ElevenLabs can be picked even when calls run on ChatGPT Live.** The ElevenLabs choice used to show only on the Basic call path, so most machines never saw it. The Voice card now has a **Message reading voice** row: pick ElevenLabs there and Javis reads chat answers with it.
- **No more pasting a Voice ID.** Once the API key is in, the voices of your ElevenLabs account show by name, your own cloned voices first. The key, voice and model boxes sit right under the choice instead of inside Advanced.
- **ElevenLabs reads Vietnamese properly.** The old default model (Multilingual v2) has no Vietnamese and sounded foreign. The default is now Flash v2.5 (fast, has Vietnamese), with Eleven v3 (most expressive) as an option; a machine that saved the old model uses Flash v2.5 for Vietnamese sentences.
- **Voice notes sent over Telegram and Zalo use the ElevenLabs voice too** when it is chosen. If ElevenLabs fails (quota, broken key) the note is read with Edge instead of being lost. ChatGPT Live and Live over an API calls still speak with their own voices.

## [0.254.0] - 2026-10-20
### Added
- **Connect an "Anthropic Compatible" gateway.** The Models page has a new card: paste the Base URL, the API key and the model name the seller gave you. It suits Claude resellers and the "anthropic" endpoints of DeepSeek, Kimi and MiniMax. When a seller says their Anthropic endpoint is more stable than their OpenAI one, you can now use it directly.
- **Gateways without a model list still work:** type the model name in the second box (separate several with commas). Javis sends one very short test message before saving, so a wrong key or address is reported at once and nothing is saved.
- It gets the full toolkit like every other brain: MCP, reading and writing the brain, skills, agents, background work, chatbots. The label under each reply says "Anthropic Compatible" so you know what answered.

## [0.253.0] - 2026-10-20
### Security
- **Remote access no longer exposes the reminder endpoints.** Four endpoints Javis uses on the machine itself (create, edit, cancel a reminder and send a file over Telegram) skip the login. Cloudflare Tunnel, Tailscale and a proxy on a VPS also come in from the machine itself, so anyone with the tunnel address could create a reminder that runs an AI task or a script without the password. Requests through a tunnel or proxy now need the login; Javis's own calls on the machine work as before.
- If you turned on remote access before this version, check the Recurring work page for reminders you did not create.

## [0.251.0] - 2026-10-20
### Added
- **Login vault** (sidebar, Connections group): sign in in your own browser, export the cookies with Cookie-Editor and paste them. Javis reuses that session to read pages behind the sign-in (seller centers, affiliate dashboards, admin pages) and **Page watch** can watch them. Each card says whether it is still signed in and until when, with a switch to let Javis use it.
- Cookies are encrypted on the server, the AI never sees a cookie value, and customer chatbots cannot use it. Javis only reads pages; it does not click buttons or send forms. Guide in `docs/en/33-login-vault.md`.
### Improved
- **The conversation's name now sits next to the Shrink button** at the top of the Chat and Code pages, so you always know which chat you are in. Long names end in an ellipsis, and on a phone the name shrinks first so the buttons on the right stay on screen.
- **Click the name to rename it** without opening the Conversations column. A chat with no messages yet shows a dimmed "New conversation".

## [0.249.0] - 2026-10-20
### Improved
- **The Plugins page has a search box.** Type a plugin name, a tool inside it or a word from its description and the list filters at once, and Vietnamese accent marks are optional. Press Esc or the X to clear it.
- **Quick filter: All, On, Off**, each with a count, plus Errors when a plugin has failed.
- **Your own plugins come first**, then plugins from Javis Store, then the ones built into Javis. Before, your own plugins sat below all 20 built-in ones.
- **Cards are less than half as tall, with an on/off switch** on the right like the Skills page. Switching keeps your search text and your place on the page.

## [0.248.0] - 2026-10-20
### Fixed
- **Domain on Hostinger: Javis says which step is broken.** Before, when DNS was right but the domain did not open, Settings only said "SSL: via Hostinger" with a hint that DNS might be wrong. Now Javis opens the domain from the server and names the cause: Hostinger has no route yet (set DOMAIN_NAME and Redeploy), the certificate is pending, the proxy cannot reach Javis, the domain opens another site, or port 443 does not answer.
- If you edit the `Host(...)` line in the YAML instead of setting DOMAIN_NAME, Javis no longer keeps saying "Redeploy still needed" once the domain works.

## [0.246.0] - 2026-10-20
### Improved
- **The History (clock) button on the chat is gone.** It did exactly what the collapse button in the corner of the Conversations column does, so on a computer only that button remains. Applies to the Chat page and the Code page.
- **On a phone, the button that opens the conversation column is now the collapse/expand icon.** Once open, the column has its own collapse button in the corner, so you do not have to reach for the top bar.
- **Phone: tapping a conversation folds the column away** so the messages show right away. The Partners page now does the same when you pick a conversation in its History tab on the right. A computer keeps the column open since there is room.

## [0.244.0] - 2026-10-20
### Added
- **Remote access gains a Tailscale option.** If Tailscale is installed, pick Tailscale and turn it on to get a private `https://...ts.net` link: only your own devices (Tailscale, same account) can open it, nothing is on the Internet. Javis runs `tailscale serve` itself, no commands needed.
- If Tailscale first asks to switch HTTPS on for your network, Javis shows the link to click and retries once it is on. If Tailscale is missing or signed out, Javis says so and links to the download.
- Turning it off, switching to another option or losing the password removes only what Javis added, never your other Tailscale settings.

## [0.242.0] - 2026-10-20
### Added
- **Open Javis from your phone or another computer, even when it runs on a Windows or macOS machine at home.** Settings has a new **Remote access** section: turn it on and you get an HTTPS link, with no VPS, no router port and no terminal. The microphone and voice work over that link.
- **Two ways:** a **Quick link** that works right away with no account (it changes on every restart), or **Your own domain** for a fixed link like `https://javis.yourdomain.com`: paste the command Cloudflare shows into the token box and Javis picks out the token and reads back your hostname.
- Javis downloads Cloudflare's `cloudflared` tool in the right build for the machine, turns it back on after a restart or an update, and reconnects when the network drops.
- **Safety:** it only turns on once a login password is set; while it is on, login cannot be switched off; if the password is removed, the tunnel stops. The token is stored encrypted and never sent to the browser.

## [0.240.0] - 2026-10-20
### Improved
- **Copy just part of a message on a phone, like Zalo.** Hold a message as before to open the card (emoji, Reply, Copy the whole message). Lift your finger, then hold the bright message again: the phone shows its selection handles, drag them over the part you want and tap the phone's own Copy (or Translate).
- **Long messages can be selected in full.** The bright copy fits between the top of the screen and the action card; swipe inside it to scroll to the part you need. It opens at the spot you were reading.
- Tapping the bright message does not open links in it. Tapping the dim area closes the card and clears the selection. Works in the main chat and on the Teams page, on iPhone and Android.

### Fixed
- **Turning an iPhone sideways and back no longer leaves the text bigger.** Safari enlarges text in landscape on its own and sometimes does not shrink it back; the Javis interface now switches that off.

## [0.239.0] - 2026-10-20
### Added
- **Web page watching that spends no tokens.** Watch a page on a schedule: get an alert when it changes, when some text appears (for example "In stock") or when a price drops below a threshold. Each check only loads the page and compares the text, without calling AI. Watching a page used to need a loop, and every loop cycle cost an AI call.
- **Understands Vietnamese prices:** amounts with the dong sign, VND, millions written the Vietnamese way (full word or the short tr form), thousands written as 250k, as well as $ and USD.
- **No crying wolf:** times like "3 minutes ago" that tick on their own do not count as a change; a line where only the price moved is reported as "Updated"; a restart never repeats an alert. A failing page is retried less and less often, and after 5 failures in a row the watch pauses and tells you exactly once.
- **Create one by asking in chat** ("watch this page, tell me below $20") or on the **Page watch** tab of the Recurring work page. Optional AI summary on each change, off by default.
- Technical details: new module `web_watch.py` (store `web_watch.sqlite3`), tool `javis_watch` (plugin `javis-watch`, owner only, customer bots never see it), `/watch` routes, tab `dashboard/web-watch.js`. Addresses pointing into a private network are blocked at every redirect hop. Docs: `docs/en/32-page-watch.md`. The idea comes from OpenMuse's `page-diff.ts` (CopilotKit, MIT license), rewritten for Javis.

## [0.238.0] - 2026-10-20
### Fixed
- **A background job that runs again no longer sends, posts or orders twice.** Jobs run again after a temporary error, a server restart or when you press Retry, and each run used to start from scratch, including messages already sent to customers. Javis now records every outside action of a job, so whatever is already done is skipped next time.
- **If the server stops right while sending, Javis asks you instead of sending again.** The job waits under "Needs you" and names the action that may not have gone through. Answer "sent" to skip it, "not sent" to send it again exactly once.
- Ordinary chat is unchanged. Limits: Claude account connectors and shell commands do not go through the hub and are not recorded yet; Grok Build and Antigravity CLI cannot carry the job id to the hub yet.
- Technical details: new module `once_ledger.py` (record `once_ledger.sqlite3` next to `kanban.sqlite3`), hooked into the hub's `_guard` for non-read MCP calls and into `full`-level plugin tools. A Kanban job binds `job` into `turn_context` while it runs. The idea comes from OpenMuse's `outcome_unknown` handling and operation cache (CopilotKit, MIT license), rewritten for Javis.

## [0.236.0] - 2026-10-19
### Fixed
- **Pasting an image during a Live call no longer gets two overlapping spoken answers.** The image used to be read twice: once by the chat (in Vietnamese) and once more by the Live voice handing it over again (often in English). Now it is read once and only the Live voice speaks the result. The image still shows in the chat and stays after a reload.
- **The Live voice answers in the chosen language.** With the mic on auto-detect and nothing heard yet, Javis uses the reply language from Settings instead of guessing from the model.

## [0.235.0] - 2026-10-19
### Added
- **Background jobs can ask you a question and carry on with your answer.** A job missing some information used to stop under "Needs you" with nowhere to reply. Pressing Retry ran it again from scratch, and it asked the very same thing. Now the question comes back to the chat where you gave the job, Telegram and Zalo included. Answer it and the job carries on.
- **Answer wherever is handy:** the box right under the question in the web chat, the answer box on the job's card on the Work page, or just reply in chat and Javis routes it to the right job.
- **The job continues instead of starting over.** The next run reads the question, your answer and what the previous run already finished. Asking and answering does not use up an attempt. A job that asks several times keeps every round in its detail drawer.
- Technical details: questions live in the job's `metadata.qa`, a new `POST /kanban/task/answer` endpoint, and `javis_task` gains `op=answer` so every engine can pass an answer on. The idea comes from OpenMuse's `ask_user` mechanism (CopilotKit, MIT license), rewritten for Javis.

## [0.234.0] - 2026-10-19
### Fixed
- **A bot tagging someone in a Zalo group no longer shows raw code.** Now and then a group reply showed a `<a_mention href="zm://Profile/...">` snippet instead of a clean tag. That snippet is now removed before sending, and the person being answered still gets a real tag.
- **The bot no longer copies Zalo's tag code.** Messages whose tags arrive from Zalo as code are cleaned to "@Name" before the bot reads them, so it does not imitate that code.

## [0.231.0] - 2026-10-19
### Improved
- **The chat box is down to two buttons: the mic and one all-purpose button.** With an empty box it is voice chat (the sound wave); type or attach a file and it turns into send, clear the text and it turns back.
- **During a call the mic steps aside**, leaving only the red hang-up button, so nothing gets pressed by mistake.
- **A customer's photo on the Conversations page opens inside Javis** with a close button (Back works too) instead of a new tab, so you land right back on the message you were reading.

### Fixed
- **Dictating a sentence that mixes English and Vietnamese comes out right more often.** Browser speech hears one language only, so "Claude Code" became "lót code". A machine with an OpenAI API key (no Groq needed) now has the audio heard again by gpt-4o-transcribe on stop, keeping both languages.
- **The listening hint now names AI products** (ChatGPT, Claude, Gemini, OpenAI...) so they are spelled right. With no key at all, Javis tells you once how to turn this on.

## [0.230.0] - 2026-10-19
### Added
- **Dictate button in the chat box.** Press the mic, speak, and the words appear in the text box as you talk. Press the square to stop and edit before sending, the arrow to send right away, or X to cancel. Nothing is sent by itself.
- **The voice chat button now shows a sound wave.** It is still the live conversation with Javis, now sitting next to the mic so the two are easy to tell apart.
- **A level meter and a timer run while recording**, so you can see the mic is listening. Long notes no longer get cut off midway, up to 5 minutes per recording. With the Groq ear on, the text is checked again when you stop for better accuracy.

## [0.228.0] - 2026-10-19
### Fixed
- **Assistants running on an API key (Anthropic API, OpenAI API...) can create agents and workflows and set a model.** Chatting with an assistant on an API model used to end in "I can't", because it was never told where those files go or how to set a model. Every assistant now knows, on every model.
- **Assistants give the real reason when browser control is missing.** Connections tied to your Claude account (such as Composio connected on claude.ai) only work when the chat model is Claude Code. On an API key the assistant now says so and offers the two fixes: connect that source on the Javis Connections page, or switch to Claude Code.

## [0.227.0] - 2026-10-19
### Fixed
- **The bot reads long Zalo group messages in full.** It used to see only the first 300 characters of each earlier message, so the end of a long one was lost and the bot asked again for what the customer had already said (real case: the surcharge was at the end of the message). Each message now keeps up to 2000 characters and the latest ones always stay whole. A message longer than that is shortened with a marker, and the bot is told not to tell the customer their message was cut.
- **The bot no longer stays quiet when the question sits at the end of a long message.** The step that decides whether the bot should answer in a group now reads up to 1500 characters of the message instead of 400.

## [0.226.0] - 2026-10-19
### Security
- **Turning off login no longer deletes 2FA.** The "Turn off login" button used to wipe the two-factor setup too. 2FA is now kept and comes back on its own when you set a password again.
- **Turning off login needs your current password and a 2FA code** (or a recovery code). A borrowed session or a leaked API token can no longer do it.
- **A server reachable from outside (VPS, Docker, tunnel) cannot turn off login**, and the button is hidden there. Only a personal machine, with the dashboard opened on that machine, can.

## [0.225.0] - 2026-10-19
### Improved
- **Switching brains loads notes much faster.** Measured on a 2000-note brain over a VPS-like connection: first open went from 1.6 s to 0.24 s, and going back to a brain you just viewed takes 0.12 s. Javis no longer re-reads notes that did not change, remembers that across restarts, and does not download the graph again when you go back.
- **The whole app is lighter on a VPS:** lists and the main page are compressed before sending, the note graph data is about 16 times smaller and the main page 3 times smaller. Chat replies still stream word by word.

## [0.223.0] - 2026-10-19
### Added
- **Pin straight from conversation search results.** Searching in the History column (Chat page, an assistant's or Javis Core's history, the Coding page) now shows a pin button on each result, with pinned chats first. No need to clear the search and dig through the list.
- **Pin chats in the bot Inbox.** Hover a chat (on a phone the button is always shown) and press the pin to keep it at the top of the inbox, marked with a colored bar. Press again to unpin.
### Fixed
- **Push notifications stay off once you turn them off.** Before, pressing Off worked until the next time Javis opened, when it quietly turned them back on because the browser still held the notification permission. Javis now remembers you turned them off on that device and only turns them on again when you press On.

## [0.222.0] - 2026-10-19
### Added
- **Test mic and Test speaker buttons** in Settings → Voice: speak for 5 seconds and the meter shows whether the mic hears you, with a hint when it is muted or the wrong one. The speaker test plays two chimes.
- **A Morning brief template** on the recurring-work page: one click fills in a 7 a.m. reminder (greeting, today's calendar, yesterday's talk, notable news). It is only created when you press Save.
### Improved
- **Background jobs stop wasting time on a broken model.** A model that just failed rests for a while (5 minutes after a quota error, 30 after an outage, 6 hours after an access error) and the next jobs go straight to one that works.
- **Javis still finds old memories when the list is too long:** memories that no longer fit are named so Javis knows to open them.

## [0.221.0] - 2026-10-19
### Improved
- **Javis only says "opened" when the app really came up.** After opening an app it checks the app is running; if not, it says plainly that it is not sure, instead of reporting success.
- **An app that is already running is brought to the front** instead of being started twice. If Zalo sits behind other windows, "open Zalo" shows it.
- **No more opening the wrong app with a similar name.** Very short names like "wp" must match exactly, and an unclear name gets a question instead of a guess.
- Closing an app, forced or not, is also checked to make sure it really closed.

## [0.220.0] - 2026-10-19
### Improved
- **Gemini Live calls no longer go silent while Javis looks something up.** Javis answers with a short sentence at once and keeps listening; the result is read out when nobody is talking. Long jobs get an occasional progress update.
- **No more answering the TV or the person next to you** (Gemini Live). Settings → Voice → Advanced has a new **Background speech filter** (on by default) and a **Reply pace**: Fast, Medium, Relaxed.
- **The voice follows the language being read:** pick "Auto by language" and Vietnamese is read by Hoai My, English by Emma, Japanese, Chinese and Korean by a native voice. A short "OK" does not flip the voice.
- **Smoother microphone on Live calls over an API key**, even while the page is busy. Japanese and Chinese replies are read sentence by sentence so speech starts sooner, and version numbers like "0.220.0" are no longer read in pieces.

## [0.219.0] - 2026-10-19
### Added
- **Brains can be renamed now, Brain Default included, without breaking a single link.** Click the pencil next to the brain picker and type the new name. Javis changes only the display name and leaves the folder alone, so wiki links, links to files in notes and chats, bots, reminders, loops, background jobs and the GitHub backup all keep pointing to the right place.
- **The name travels with the brain:** it is stored inside the brain (`Javis/brain.json`), so the GitHub backup carries it to other machines. Leave it empty to go back to the folder name.
- **The new name shows everywhere:** the brain picker, the Work page, Settings, webhooks, Telegram (`/brain`, `/status`) and the `/brain` chat command. Typing the old folder name still selects it.

## [0.217.0] - 2026-10-18
### Fixed
- **Wiki pages no longer vanish after a learning run.** On a brain whose wiki folder is a lowercase `wiki` (every new brain), the learning run treated the whole wiki folder as "out of scope" and cleaned up what it had just touched. A page the chat had just created, to which the run only added a Contradiction section, was wiped, while the "contradiction" line stayed in the open questions. Pages the run created itself were lost too. The run now uses each brain's real wiki folder, including names like `07 - Wiki`.
- **The learning run's cleanup never deletes a file that is not in the history yet.** Such a file may be yours or the chat's, so it is left in place.
- **The contradiction line in the open questions names the real page**, not the near match the model gave.

## [0.216.0] - 2026-10-18
### Added
- **The bot inbox can search by phone number.** 0912 345 678, 84912345678 and +84 912 345 678 all find the same person.
- **A number the inbox does not know yet is looked up on Zalo:** type a full number and Javis asks the connected personal Zalo accounts whose number it is, then shows the chat with that person. The number is kept on the customer, so the next search finds it at once.
- **Someone who never wrote is reported plainly:** "This number is Lan's Zalo, no conversation yet". A number with no Zalo account, or whose owner turned off search by phone, is reported too.
- **Zalo is not asked twice:** answers are remembered (30 days when found, 1 day when not). At most 20 numbers are looked up per hour, because Zalo caps lookups per day.
- **Swipe a message to the left to quote it (phone):** like Zalo, pull a bubble to the left until the orange quote mark shows, then lift your finger, and the message lands in the "Quoting" box above the input. Works on Javis's messages and your own, in the main chat and in chats with Javis Core or a partner. A short swipe or scrolling up and down does nothing.

### Fixed
- **The phone menu no longer closes by itself and leaves the screen dim:** on iPhone the menu slid in, then vanished, leaving only the dark backdrop. The menu now has a solid background instead of a blur (Safari can stop drawing a box that is blurred and sliding at once). The dim layer always goes with the menu, so closing the menu clears it. A single tap counted as two clicks no longer closes the menu it just opened.

## [0.214.0] - 2026-10-18
### Fixed
- **Antigravity no longer blames Google when a turn runs too long:** a turn over 15 minutes is stopped by Antigravity CLI itself, and Javis used to report "Google is having a temporary problem, retried 2 times" without retrying at all. The message now says the turn ran too long, finished steps keep their results, and you can send "continue" or give the job to the background queue.
- **"Retried N times" only shows when Javis really retried.** A turn that already did part of the work is not run again (that would repeat it), and the message says so.

### Improved
- **Pages are much cleaner: explanations fold into an (i) button.** The page keeps titles, states, inputs and buttons; the why, the caveats and the step-by-step help sit behind the (i) next to the title and open on a tap. Applied across Javis: Models, Settings, Channels, Chatbots, Plugins, Learning, Work, Teams, Assistants, Usage.
- **Long descriptions on cards (plugins, workflows) show two lines**, the full text is in the (i).
- **Text in the explanation box is 16px**, easy to read on a phone.

## [0.213.0] - 2026-10-18
### Added
- **Send more while Javis is working, now on Telegram, Discord, Slack, Lark, Messenger and Zalo too:** before, the bot replied "still on the previous message, send /stop" and dropped yours. Now it is kept, nothing is lost.
- **Codex (ChatGPT plan) now reads the new message within the turn**, on the web and the channels, like Enter in the Codex app: no more waiting for the current work to finish. Turn it off with `JAVIS_CODEX_STEER=0` if needed.
- **On chat channels the bot answers with one short line** saying whether Javis reads it at the next step (Claude Code, Codex, the API-key brains) or right after the current answer (Grok, Antigravity).
- **/stop ends the current work and drops what was waiting.** Customer-facing bots keep their old way: silent, follow-up messages merged into the next turn.

## [0.211.0] - 2026-10-17
### Improved
- **The Claude Code card says one thing when the CLI is missing:** a single install box (Docker: update Javis; manual install: one command to copy) and only a Check again button. The Sign in button that could only fail is gone, and so are the version line and Update button for a program that is not there.
- **Messages are no longer squeezed into a narrow column:** errors and hints sit under the buttons at full width, and buttons keep their height. The PATH and Windows details fold under "Installed but still missing?".
- **Provider cards use 16px text**, easier to read on a phone. The card is now named "Claude Code" (Javis never uses its OAuth token), and the green shield lights only when the CLI is there.

## [0.210.0] - 2026-10-17
### Improved
- **Team cards read well on a phone:** buttons and helper text in the Department mandate and Acceptance sections are now 16px, and long lines wrap instead of being cut. Checked at 390px wide in Vietnamese and English.
- **The mandate trace now ends with the acceptance:** it goes all the way from the mandate, observation, opportunity, decision and approval to the job and its acceptance result.

### Added
- **Preparation pack for a multi-day Team pilot** (`pilot/team-multiday`, not run yet): a 7-day scenario for 3 teams, limits and stop conditions, emergency stop and rollback, metrics, a read-only trace export, an empty report template.

## [0.209.0] - 2026-10-17
### Added
- **Product acceptance for Team jobs:** set criteria right on the job (file exists, enough content, JSON keys, a passing check command, your confirmation). A job is done only when the product really passes.
- **Bounded fix rounds when it fails:** the member gets a fix step saying what failed; past the rounds the job stops for you. Every check keeps evidence (hash, size, modified time) and its history.
- **Product acceptance card** for criteria you review: Passes or Send back with a note. A file changed after the check cannot be accepted; editing a product after acceptance shows a warning.

## [0.208.0] - 2026-10-17
### Added
- **Department mandate for a Team:** set the outcome, how it is measured, granted sources (folders, failed Kanban jobs, connections, check commands), scope, daily budget and how much it may decide. Older teams stay off.
- **The team finds opportunities within its scope:** a change in a source becomes a proposal with its source, reason and benefit; it opens the job, opens it waiting for your approval or only proposes, as you choose. A missing source is reported, never made up.
- **No repeats, with limits:** the same data never opens twice, a skipped opportunity returns only when the data changes, proposals expire after 48 hours. Pause or revoke at any time.

## [0.207.0] - 2026-10-17
### Fixed
- **A Team that asks for your approval really stops:** "@Owner please approve?" is no longer taken as the result that closes the job. The job waits for your approval, frees its slot for other jobs, and nothing is done before you decide.

### Added
- **Approval request card in the Team chat:** what will be done, scope, impact, evidence and the exact calls that will run, with Approve, Ask for changes, Reject and Revoke. Editing or cancelling the job voids old cards; a retry or a second tab never acts twice.
- **Outside actions are stopped before they run:** with the default "Needs your approval", a Team's sends, posts, payments or machine commands are blocked and become an approval card; once approved only that exact call runs, once, even after a restart.
- **"The team acts without asking" switch** on the Team tab for a team you trust, which runs as before this release.

## [0.206.0] - 2026-10-17
### Added
- **Send more while Javis is working, like Claude Code and Codex:** type and send while a turn runs; the work in progress is not stopped. Before, a message typed at this point was silently ignored.
- **Claude Code and the API-key brains read the new message at their next step:** a correction applies at once, a new task is taken on too, in parallel where possible.
- **Codex, Grok and Antigravity run your message right after the current work**, since those engines run in one go. Nothing is lost.
- **A status line under the message you sent:** will read it at the next step, read, or working on it.

## [0.205.0] - 2026-10-17
### Improved
- **A partner with a new message moves to the top of the list:** you writing, the partner replying, or a background job reporting into its chat all push that card up (after Javis Core and the pinned ones).
- **An unread count on each partner card**, next to the time. Opening the chat clears it, in every open tab.
- **Mute notifications per partner:** the ⋮ button has **Mute notifications** for 1 hour, 4 hours, until 8:00 AM or until turned back on. Messages still reach the chat and the bell, just without a sound or a push.

## [0.204.0] - 2026-10-17
### Improved
- **A tidier Scheduled page:** a brain picker instead of every brain stacked up, a **Repeating job / Reminder** filter and paging at 10 jobs a page. Incidents and Log are their own tabs; Webhooks have their own page in the Work group.

### Fixed
- **Scheduled calls really ring now:** the call used to ring only when the chat receiving the reminder was the open one, so usually nothing showed. The call card now shows on whichever Javis page is open.
- **A bigger Read all button in Notifications:** lit while something is unread, dimmed once all is read, and it now reads both tabs instead of only the open one.
- **@mentions in Team messages look normal again**, no longer squeezed into a small circle with one letter per line.

## [0.203.0] - 2026-10-17
### Added
- **Javis calls you at a set time:** reminders get a **Call me** box (or say "call me at 7am and read the report"). At that time an open Javis tab rings and shows an incoming-call card with **Answer** and **Decline**.
- **Answer starts a voice call:** Javis reads the reminder or report briefly, asks if you need anything else, and you keep talking as with the mic button (ChatGPT Live when it is set up).
- **Missing it costs nothing:** after 45 seconds it is a missed call and the content stays in the chat; with no Javis tab open, Telegram gets the message like any other reminder.

## [0.202.1] - 2026-10-17
### Improved
- **Reminders that read aloud now really "call":** at the set time, if Javis is open, the voice note plays at once like a call, no press needed. When the browser blocks autoplay the player stays there to press; Telegram still receives the audio file as before.

## [0.202.0] - 2026-10-17
### Added
- **Voice notes:** ask Javis to "read it to me" and it records a short spoken message as an mp3; the chat shows a player under the answer and Telegram receives it as audio. The words are still there as text below.
- **Reminders that read aloud:** tick **Read it aloud** and the reminder or report arrives with a voice note, easy to hear while driving or cooking.
- **Keep the cache warm (optional, off by default):** on the Token usage page, switch it on and Javis keeps a Claude Code chat's one-hour prompt cache alive across a short break, so the next message does not reload the whole conversation. It stops at a usage limit or a cold cache.

## [0.201.0] - 2026-10-17
### Added
- **Charts and number tiles in the chat:** a revenue, order or ads report can carry a bar or line chart and a few key figures with their change, drawn right under the answer.
- **Quick-choice buttons:** Javis can offer up to 4 buttons such as "Approve draft A"; a press sends that text as if you typed it. Telegram and Zalo get a readable text version.
- **Javis recalls earlier chats:** start a new chat that mentions something from before and Javis looks through your other chats for a few relevant lines as context. Team chats and customer chats are never used.

## [0.200.0] - 2026-10-17
### Added
- **Share a whole team as one file:** a team's ⋯ menu has **Share team**, which downloads its partners, skills and shared instructions. No chat history, keys, models or Auto switches; text that looks like a password or API key is removed before writing.
- **Import a team:** the **Import team** button on the Teams page reads the file and shows who comes in before adding it. Partners you already have under the same name keep your version.
- **See at once what Javis just created:** a chat turn that creates, edits or removes a schedule, loop, partner, workflow or skill shows a small "Created schedule: ..." line under the answer. New items get an **Undo** button.

## [0.199.0] - 2026-10-17
### Added
- **Javis Core handles broken background runs:** when a Kanban job, loop, reminder or webhook fails, Javis Core hears first. A passing failure (a network glitch, a timeout) is run again once; something only you can fix (a sign-in, a key, a setting) gets one or two plain sentences on what to do.
- **No storm of messages:** a job that keeps failing is one incident, and a retry that fails again sends exactly one "needs you" message.
- **Background health on the Work page:** see open incidents, close them with Done, and the last 24 hours of failures grouped by cause (14 runs of the same token error show as one line).
- **Health scan from outside:** `python tools/sentinel.py` reads the data (read only) and works even while Javis is down.

## [0.198.0] - 2026-10-17
### Added
- **Webhooks: outside systems start work in Javis.** On the Work page, the **Webhooks** section creates a secret link. When a landing page form, a payment or another app calls it, Javis runs the workflow or job you chose with the event data, then reports like a reminder.
- **Safe by default:** the secret is shown once, with buttons to send a test, switch off and make a new token. A repeated delivery does not run twice, and each webhook runs at most 30 times an hour.
- **A task reminder can remember its last run:** tick **Remember the last result** and each run knows what it already reported, so it reports only what is new. Good for watching competitor prices or a metric.

### Improved
- **Repeating schedules show their next three runs** on the job card, and a schedule made from chat is read back as those three dates for you to confirm. A run that fires late because the machine was off knows it is late.

## [0.197.1] - 2026-10-17
### Fixed
- **Safari no longer loses the connection for minutes.** Safari has its own bug with the compression used on the live connection: a large message makes it cut the line, and every reconnect is cut again, while Chrome keeps working. Javis now turns that compression off, so every browser stays as stable as Chrome.
- **If it still drops, there is a trace:** each disconnect records the browser, the close code and how long it was down, and sends it to the server once back online, shown at `/health/loop`.

## [0.197.0] - 2026-10-17
### Added
- **Unread count on each team:** the Teams list shows a red count like Zalo, with the team name in bold while messages wait. Opening the team reads it, on every device.
- **@ mark when a message calls you:** a team with a message calling "@Owner" gets an @ mark next to the count, visible even when the list is folded to logos.
- **Only the leader calls you:** a member who needs your decision asks the leader, who gathers it into one question, so you are not called over and over.
- **Team notifications only when you are called:** ordinary team messages never notify; only the leader calling "@Owner" rings your bell. Press "..." on a team and pick **Mute notifications** to silence it completely, even when you are called.

## [0.196.0] - 2026-10-17
### Improved
- **Drag narrow and it tucks away:** on Graph, Chat, Partners and Teams, dragging a column divider past a set width hides that column, just like on the Partners page. The column fades first so you know it is about to hide.
- **Team list shrinks to logos:** drag the Teams list in far and only each team's logo stays; hover a logo for a detail card (name, time, last message, status), the same card as on the Partners page.
- **Resize both sides of Teams:** the team list and the right info panel can both be dragged, and the width is remembered for next time.

## [0.195.0] - 2026-10-17
### Added
- **Teams opens where you left off:** the Teams page opens the team you worked in most recently (the one you last messaged or opened, on any device), no searching.
- **Tag teams:** press "..." on a team and pick **Tag**, the same way you tag a partner. Teams on one project share the same tag.
- **Filter teams by tag:** the filter on top of the team list is the same as on the Partners page: All teams, No tag yet, then each tag with its team count.

## [0.194.1] - 2026-10-17
### Improved
- **Team message buttons sit under the bubble:** send time, Reply (quote), Copy and Pin now form one row right under the message, like the main chat, instead of a cluttered strip beside the bubble.

## [0.194.0] - 2026-10-17
### Added
- **Teams do real work:** when you assign a job in a Team, a member's **Work** and **Help** turns get the same tools as a private chat: read and write files in the brain and the team's working folder, call connections (MCP), run skills. Members do the job and return real results (files, links) instead of sending you to a private chat. Work turns on the same brain run one at a time, so nobody overwrites another member's file.

### Fixed
- **Fewer long "Lost connection to the server" stalls:** one dead tab (a phone asleep, dropped Wi-Fi) no longer freezes the running chat for every other tab; the page retries a reconnect that gets stuck, and waits longer for a busy server before calling the connection lost.
- **The culprit gets caught next time:** the server records the code that froze it and any unexpected restarts, readable at `/health/loop`.

### Improved
- **Chat stays fast and cheap:** ordinary chat replies in a Team are still text only. When a reply needs files or connections, the member suggests turning it into a job.

## [0.193.0] - 2026-10-16
### Added
- **Finished jobs stay until you clear them:** in a partner's Jobs tab and a team's Jobs tab, finished jobs have their own section; **Open** shows a short report (who did what, the result). **Done** moves a job to the **Archive**, nothing is deleted; only the Archive has **Delete** and **Delete all**.
- **Each partner's own reasoning level:** Medium by default, set in the agent editor or with the reasoning button on that partner's chat. It applies to private chat and team replies.
- **Message privately from a team:** a **Message privately** button in the agent editor, the member list and the Info tab opens the private chat with that partner.

### Improved
- **Job cards coloured by state:** red needs you, blue working, orange waiting, green finished, with a label on each card.

## [0.192.0] - 2026-10-16
### Added
- **Paste and drop in a team:** paste a picture (Ctrl+V) or drop a file into a team chat and it is attached, with a preview. A very long pasted text becomes a .txt file.
- **Team members read pictures:** a picture sent in a team is described in words by a connected brain before the team answers.
- **See who is replying:** a small strip above the input shows "Lan is replying...", "Minh is working..." with their pictures. New answers appear block by block, one member after another.
- **Clear mentions:** type **@all** to call the whole team. A member's reply quotes the message it answers; a message that needs you is labelled "Needs your answer".
- **Pins you can see:** pinned messages show in a strip on top of the chat; tap one to go to it. The whole team always follows them.

### Fixed
- **Easier to read team chat:** a member's picture sits next to their name, quotes carry the same quote mark as the main chat, and job titles in the Jobs tab are no longer squeezed into a narrow column.

## [0.191.1] - 2026-10-16
### Improved
- **Four-colour status dot on avatars:** when the partner list shrinks to avatars, a small dot shows each partner's work: red needs you (or just failed), blue working, orange waiting, green finished in the last 24 hours. Hover to read it in words.

### Fixed
- **The hover card is readable:** it has a solid background, so the chat behind no longer shows through the words.
- **Source and Status dropdowns are no longer white:** the list that opens uses the theme's colours, readable in both light and dark.

## [0.191.0] - 2026-10-16
### Added
- **Teams can share files and pin a working folder:** the **+** button of a team chat now has **Attach a file or picture** and **Pin working folder**. The whole team reads text files (.md, .txt, PDF, Word...); a pinned folder shows up as a folder tree so everyone knows what the project holds.
- **Team info panel:** tap the team picture at the top left to see the members, the working folder, and the pictures, files and links shared in the team. Add a file, paste a link or remove one right there.

### Improved
- **Shrink the partner list to avatars:** drag the list edge in far enough and it turns into a strip of avatars; hover one to see its name and role. Drag the edge back out for the full list, or double-click the edge for the default size.

### Fixed
- **Pinning a subfolder:** in the folder picker, a folder with folders inside has a **>**. Tap it to go inside, tap the name to pin that folder.
- **Tapping a notice goes to the right place:** the "Ask Javis Core" button is gone. A notice that answers a chat reopens that chat; a system notice opens in Javis Core.
- **Jobs tab:** with no jobs it says "No jobs yet" instead of "Could not load jobs". The selected tab has room around its label.

## [0.190.0] - 2026-10-16
### Improved
- **Settings like the apps you know:** a colleague's settings column keeps only picture, name, description, instructions, documents, skills and model. Lessons, Revoke, Use everywhere and the Javis Core Memory section are gone: to change or forget something, just say so in chat, for example "forget the sales channel note".
- **See what Javis just remembered:** a chat turn that saves, changes or forgets a memory shows a small "Remembered: ..." line under the answer, with **Undo**. If Javis says it remembered or forgot something while nothing changed, a correction line says so.
- **Tidier colleague cards:** the chat time is small and sits on the same row as the Auto switch in the bottom corner; the switch is back on every colleague. The Auto block in Settings is down to "Work on its own up to ... times a day" plus anything waiting on you.
- **Release news stays out of Javis Core:** cards in the bell's News tab no longer have "Ask Javis Core".

## [0.189.1] - 2026-10-16
### Fixed
- **The create-team picker no longer breaks when you pick several members:** picking a third one used to push the whole box up, hiding the title, leaving the Create button floating mid-screen and a blank area below. The box now stays put however many people you pick.

### Improved
- **The Vietnamese interface now uses the word "Team"** for teams, in the sidebar and across this feature, and calls team members colleagues rather than assistants.
- **The colleagues page uses one name throughout** in Vietnamese: its tab, create button and filters now match the page title instead of saying "assistant" or "agent".

## [0.188.0] - 2026-10-16
### Fixed
- **A chat always runs on its own brain:** open a chat of another brain (from the bell or history) and keep writing, and Javis now answers with that brain's memory and files; the chat says which brain it belongs to, with a switch button. Clicking a notice of another brain switches the dashboard to it first.
- **A quieter Javis Core:** runs that went fine stay in the notification bell; only reports that need you land in the chat. Reports sent to the Telegram of someone else sharing the bot are no longer copied into your Javis Core.
- **Turning learning off really blocks Claude Code:** when off, Claude Code cannot write anything into that brain's memory folder.
- **New memories always carry a source:** Javis records the chat and date that produced them. The "Your Telegram" field is now a picker of the allowed IDs.

## [0.187.0] - 2026-10-16
### Added
- **Ask Javis Core about a notice:** cards in the bell have an **Ask Javis Core** button. The notice goes into your own Javis Core chat with its source and time so you can follow up; the shared notice itself does not change.
- **See, edit and forget memories:** the Javis Core card has a **This brain's memory** section listing what Javis remembers and where it came from. Once forgotten, Javis does not learn it again from old chats; a switch turns off saving new memories.
- **Your profile, shared by every brain:** write once how to address you, language and level of detail; each brain's own memory still wins where they differ.
### Improved
- **News read on one device is read on every device**, and push notifications are tied to the login: logging out stops that device receiving them. There is an option to **hide the text** in push notifications.

## [0.186.0] - 2026-10-16
### Fixed
- **Reports without a chat of their own now go to the right brain's Javis Core:** background jobs, loops and reminders created on the Work page or without a chat report into the Javis Core of the brain that produced them, whatever brain you have open.
- **No more guessing on Telegram:** a report with no known recipient used to go to the FIRST Telegram ID on the list (possibly someone else sharing the bot), and a loop pausing itself went to EVERY ID. Now only your own Telegram gets them.
- **New field "Your Telegram (receives reports)"** in the Telegram settings. With a single ID Javis uses it; with several you choose, Javis does not guess.
- **No duplicates on retry:** a report sent again after a failure appears once. If the original chat was deleted the report goes to Javis Core; with neither a chat nor a brain it stays in the notification bell only.

## [0.185.0] - 2026-10-16
### Added
- **Javis Core, a system assistant built into every brain:** it is always first on the Assistants page with a **System** badge, in old and new brains alike. It is the place to receive reports, ask follow-up questions and hand out work, with everything Javis can do.
- **It cannot be deleted, renamed, unpinned or edited:** the server refuses it, not just the buttons. Choosing its model works like any chat.
- **Each brain has one default Javis Core chat:** delete or archive it and Javis makes a new empty one next time, without bringing back what you deleted.
- **One update for every brain:** the Javis Core definition ships with the app instead of being copied into each brain, so your memory and personal settings stay as they are across updates.

## [0.184.0] - 2026-10-16
### Fixed
- **Long press on a phone no longer triggers the phone's own text selection (iPhone and Android):** holding a message a little longer used to highlight the text and show the phone's Copy bar on top of the Javis menu. Now only the Javis menu appears (reactions, Reply, Copy...).
- **Copying still works:** Copy in the menu copies the whole message. Text fields can still be selected and pasted into.

## [0.183.0] - 2026-10-16
### Fixed
- **Zalo no longer silently misses a contact's reply:** every Javis restart or update used to wipe the Zalo message store, so a message that came in right then could vanish from all three ways of reading. The store is now kept (30 days) and survives restarts.
- **Javis knows when messages may be missing:** each Zalo read now says whether the connection was down during that period. If it was, Javis says it is not certain, keeps the waiting step (approval, publishing) on hold and tells you, instead of concluding the contact has not replied.
- **Messages from an outage reach the Inbox:** messages Zalo replays after a reconnect now show up in the conversation Inbox too, not only in history.

## [0.182.0] - 2026-10-16
### Fixed
- **The chat no longer slides left and right:** on a phone the reaction button at the bubble's corner stuck out past the edge, so the whole chat could be dragged sideways. It now sits inside the bubble and the chat only scrolls up and down.
- **Tapping Like works every time:** an invisible area from the previous version covered the top half of the button, so a tap on a phone, or a click near its top on a computer, did nothing.
- **Holding the reaction button at the bottom-right corner also opens the emoji row**, the same as holding the message; slide your finger to pick.

### Improved
- **Phone: the model button is back in the top bar** as before, still showing just the model name and the pin icon. Pressing it opens the provider picker as usual.

## [0.181.1] - 2026-10-16
### Improved
- **VPS install docs that are easier to follow:** the README, the quick start and the server install guide were tidied, and the translations follow.

## [0.181.0] - 2026-10-16
### Improved
- **Filter assistants with Auto on:** the tag menu on the Assistants page has a new **Auto on** entry with a count. Pick it to see only assistants running Auto; switch one off and it leaves the list, so reviewing and turning them off is quick.
- **Smaller text in assistant and team settings:** the Auto, goals and proactive pulse blocks now match the rest of the panel. The chat and other pages keep 16px text.

### Fixed
- **Answers on the Assistants page no longer hug the right edge:** answers keep the same comfortable width as the main chat instead of running up to the outline bar. The sideways scrollbar that shifted the chat is gone too.

## [0.180.0] - 2026-10-16
### Improved
- **A tidy model button, like the Claude app:** it shows the model name only (for example "Opus 4.8", "GPT-5 mini"), without the provider. Pressing it still opens the provider and model picker as before; hover it to see the provider. A session with its own pinned model shows a small pin icon on the button; pinning works as before.
- **Phone: the model button sits right under the message box**, next to the thinking-level button, instead of in the top bar. Pick a model where you type.
- **Copy no longer slides away (computer):** while Javis is answering, the chat stops following the answer while your mouse is on a message's buttons or moving over a message. Move the mouse away and it catches up to the bottom.

## [0.179.0] - 2026-10-16
### Improved
- **Long press on a phone now works (Zalo style):** hold a message about half a second, the screen dims, that message stays bright, 6 emoji pop up above your finger and a card with Reply, Copy, Edit, Send again sits at the bottom. Main chat and the Team page alike.
- **Slide your finger to pick an emoji (Facebook style):** without lifting, slide across the row; the one under your finger grows and shows its name, lift to pick it. Lift elsewhere and the card stays open.
- **Copy in the card shows "Copied"** and copies the whole message, no text selection needed.
- **On a computer the emoji row no longer vanishes too fast:** a wider hover area and a half-second wait before it hides, so moving the mouse sideways across the emoji is easy.

## [0.178.0] - 2026-10-16
### Added
- **Use your own picture for an assistant:** when editing an assistant, an **Upload a picture** button sits under the preview. The picture is cropped square and shrunk before upload, then shows everywhere the assistant appears: the list, the chat and teams. Press **Use the Javis character** to go back.
- **A picture of your own for a team:** the Team picture field in team settings has the same Upload button. By default a team still shows the collage of its members' faces.
- PNG, JPG, WEBP and GIF pictures up to 2MB are accepted.

### Fixed
- **Selecting your own message is no longer blocked by the outline:** the outline bar on the right of the chat used to cover the end of your messages, so reaching the end of a line popped its list open. The bar now sits in the margin, clear of the text, and opens only when you rest the mouse on it for a moment.

## [0.177.0] - 2026-10-16
### Improved
- **Zalo-style reactions in the main chat:** a 👍 button sits on the bottom-right corner of each answer bubble; one press likes, a second press removes it. Hovering it shows 6 emoji; on a phone, long press the answer.
- **The reasons and feedback panel is gone** (On point, Wrong facts, Speak or stay silent, the comment box, the "Received" label) in the main chat and on the Assistants page. To correct an answer, just reply or quote it.

## [0.176.0] - 2026-10-16
### Improved
- **Team chat that reads like a real chat app:** bold text, lists and colours look exactly like the main chat. The "Teams" title bar is gone to give the chat more room, and the settings panel uses smaller text.
- **Reply to any message:** hover a message and press Reply (on a phone, swipe it to the left). Replying to an assistant's message goes straight to that assistant, so feedback is just a chat reply, no reasons to pick.
- **Zalo-style reactions:** the latest assistant message always shows a Like button, hovering it opens 6 emoji (long press on a phone). The reasons panel and comment box are gone.
- **Cleaner composer:** a **+** button holds Assign job, Mention an assistant and Search; a new **mic button** turns speech into text. Each team has a ⋯ menu to Pin, Rename or Delete; click the team name to rename it; click an assistant's picture to open its settings.

## [0.175.0] - 2026-10-16
### Fixed
- **Connecting Higgsfield (and other MCP servers that sign in through Clerk) no longer fails with invalid_grant:** Javis asks only for the permissions the MCP server needs. If the provider refuses one, Javis drops it and reopens the sign-in page; other sign-in errors now show their real name.

### Improved
- **Tidier assistant cards:** each card shows name, time and role. A third line appears only when something is going on, "Needs you 1" or "Working 2" in words, instead of a hand icon that looked like a pin. Auto shows as a small label only while it is on (turn it on from the three-dot menu or the Settings tab). Tags are no longer drawn on the card (filter at the top of the column, hover a card to see them).
- **Assistants waiting on you move to the top,** under "Waiting on you", ahead of pinned and the rest.
- **The goal card folds itself once you press "That's right":** just the short understanding, status and next run; press Show details for everything. The Jobs tab is tidier: two-line titles, one row of buttons, "Waiting on you" in plain words.
- **Less to read in the Settings tab:** each section keeps only its title, numbers and pickers. Explanations sit behind a small **i** button next to the title and appear only when pressed.

## [0.174.0] - 2026-10-16
### Added
- **Import old personal Zalo messages into the Inbox:** right after signing Zalo in to Javis, press **Import old messages** (on the Zalo account card, or on the Zalo chip of a bot card). Javis takes about the last 2 weeks Zalo lets it reload, up to 5,000 messages.
- **Safe to run:** only chats with no message in the Inbox yet are filled, the bot does not answer these messages and they are not counted as unread. Pressing again never duplicates anything.

## [0.173.1] - 2026-10-16
### Improved
- **Clearer /goal:** every time Javis nudges itself to keep going you see a line you can expand (round n/5) with a Stop goal button, and it survives a page reload.
- Javis stops at once when it lacks a permission, a tool or data, says why and how to unblock it, instead of nudging itself again and again. At most 5 rounds.

## [0.173.0] - 2026-10-16
### Added
- **Javis creates and manages team chats from the chat box.** Ask for "a test team of three assistants" and Javis creates any missing assistant, sets up the team and picks the leader; renaming, adding or removing members, archiving or deleting a team works the same way.
- Each assistant created this way can run its own model, so a mixed-model test team takes one request.
- An archived team can now be deleted for good. If the team you have open is deleted, the Teams page closes it and tells you.

## [0.172.0] - 2026-10-16
### Added
- **Personal Zalo: set how many minutes the bot steps aside after you type by hand** (0 means never). The clock starts at your last hand-typed message, so in private chats the bot answers for you sooner than before. Once a number is set, a direct tag in a group is still answered right away.
- **Per-chat exceptions:** one trusted person (a family member, say) gets their own permission level and wait, without raising the bot that answers strangers. Accept Zalo friend requests automatically (off by default) and hand the introduction to the bot. Plugins can add one line of context to each bot turn.
### Fixes
- **Personal Zalo understands customers better:** a photo sent without text in a private chat reaches the bot and stays attached for 10 minutes. If the customer keeps typing while the bot composes, the stale reply is dropped and one answer covers everything. The role instructions you write always win over Javis's default. The bot no longer quotes old backups or agent and workflow files as documents.
- **Small fixes:** a reminder answering `[SILENT]` sends nothing. What you write under the self-learning history heading is no longer wiped. A `---` inside a sentence no longer turns a 16-step workflow into 14.

## [0.171.4] - 2026-10-16
### Fixed
- **Calling an assistant by name in a team, without @, is now noticed.** An assistant named Minh never noticed its own name before, because without accents the name matched a common Vietnamese word and was ignored. Javis now compares names with their accents, so an everyday word that only looks like the name is still not a call.

## [0.171.3] - 2026-10-16
### Fixed
- **Team chat no longer shows made-up command names.** When an assistant's reply contains a command Javis does not support, the team now notes "the reply had an unsupported Javis command, dropped" instead of printing the raw code in the bubble.

## [0.171.2] - 2026-10-16
### Fixes
- **A dropped connection no longer kills the whole turn:** when the connection to the model provider is cut (errors like `ReadError ... WinError 1236` on Windows), Javis resends up to 3 times, even in the middle of a turn that uses tools. If it still fails, the message names the usual causes (network, VPN, antivirus) instead of just pasting the error chain.
- **Long Zalo replies are split into several messages:** a long reply on personal Zalo is cut at the end of a paragraph or sentence and sent in order, instead of Zalo refusing it and the customer getting nothing. In groups, the person being answered is tagged only in the first message.
### Improved
- **Bot alerts go to the notification bell only:** the Telegram message to an "on-duty person" is gone (its field had long been hidden from the form). A customer asking for a human, or the bot getting stuck twice in a row, now lands in the Javis bell with the customer's name. Technical failures still ring the bell as before.

## [0.171.0] - 2026-10-15
### Added
- **Quote to ask a follow-up:** every chat message has a Quote button. It puts that passage above the input box so you just type the next question, no retyping. Select part of a message first to quote only that part.
- **Share a conversation by link:** the Share button next to the paperclip at the top of the chat makes a link anyone can read without signing in, and copies it for you. Readers see only the questions and answers, never attachments, tools or hidden notes.
- **The bot inbox shows the photos and files customers send:** photos appear right in the chat (click for full size) and files become a card with a Download button, instead of a long link or a server path. Works for personal Zalo and the Telegram, Zalo Bot, Slack, WhatsApp, Messenger, Discord and Lark bot channels.
- **The link is a snapshot up to when you shared:** later messages do not show up on their own. Press "Update to the latest message" to include them; the link stays the same. Conversation links live on the Share links page next to file links, and can be renamed or revoked the same way.

## [0.170.0] - 2026-10-15
### Improved
- **Teams with thousands of messages still remember what matters:** every assistant turn still sees pinned decisions, the original request and status of open jobs, who contributed to the latest result, and your feedback still waiting for review, however far back they are in the history.
- **Long teams do not slow each turn:** each of those items is read once with a limit, so a 5,000 message team costs as much to read as a team with a few dozen.

## [0.169.0] - 2026-10-15
### Added
- **Assistants pace themselves:** an assistant with Auto on reviews its own work on a rhythm from 15 minutes to 1 month. Praise and used results make it faster (up to 1 hour by default, only you can raise it); little demand makes it slower until it sleeps; a direct call wakes it at once. Assigned jobs, deadlines and goals are never slowed down.
- **Assistants judge when to speak:** when nobody calls them, each assistant weighs speaking, waiting or staying quiet; at most one volunteers per message. @ calls and assigned jobs are always answered. You can correct each decision ("Should have spoken", "Should stay quiet") and the assistant learns for that team only.
- **Learning from feedback and teammates:** an assistant reviews the reactions you leave and keeps its approach, asks back, sends a revision or records a lesson. Lessons are scoped to a team or a private chat and never leak elsewhere; teammates can give each other feedback. Revoke a lesson right on the assistant card.
- **Pulse panel on assistant cards and team member rows:** state per place, last and next review, why the pace changed, speak/wait/quiet decisions, lessons, work proposals (accept or reject) and autonomous turns per day.

## [0.168.0] - 2026-10-15
### Added
- **React to replies in private chat:** the same six emoji as team chat, on the Chat and Partners pages, available as soon as a reply is saved, kept after a reload and shown in other tabs. Goal reports use the same six emoji instead of the Helpful / Not quite row.
- **Clearer feedback:** besides reasons, pick "Should have spoken" or "Should stay quiet (interrupted)" and add an optional comment. A status such as Received, Waiting for review or Adjusted shows under the reaction; in teams you also see the coordinator's and members' reactions.
- **Assistants with Auto on get your feedback for review:** many taps fold into one review; with Auto off it is only stored, and turning it back on does not replay old feedback.
### Fixed
- **The server's shared turn ceiling now covers team turns:** when it is reached, a team turn stops before calling a model and says why.

## [0.167.0] - 2026-10-15
### Fixed
- **Taking back the right to decide alone covers a turn already running:** if you take it back, give it again or give it for the first time, the admin commands of the coordinator's unfinished turn are dropped with a note; only the next turn uses the new permission.
- **Long jobs are not cut in on:** an assistant working on a long step keeps its slot until done. A turn that loses its slot midway only shows its result for you to read and changes nothing in the team.
- When the coordinator turns Auto back on for an assistant the team manages, its goals resume right away; limit fields reject invalid numbers instead of returning a server error.
### Improved
- **Limits table under the team's Advanced section:** every limit, grouped by what you can change, what the coordinator can change, what the server fixes and what the provider decides. Replies, steps and nested help can be set to **Unlimited**.

## [0.166.4] - 2026-10-15
### Fixed
- **Saving a setting can no longer wipe the admin account, models and admin channels.** If `settings.json` was locked for a split second while Javis read it (common on Windows when antivirus scans a freshly written file), Javis took it for a fresh install, showed the setup wizard again, and the next save (saving the Lark channel, for example) wrote an empty setup over the real one. Javis now retries the read until it works, and never writes an empty setup over a machine that is already set up.

## [0.166.3] - 2026-10-15
### Fixed
- **The bot no longer sends customers the "please wait a moment while I check" line when something technical breaks** (out of tokens, plan limit reached, model error). The customer receives nothing at all, on personal Zalo, Zalo OA, Telegram and WhatsApp.
- **The owner hears about it in the Javis notification bell:** which bot failed, which customer wrote without an answer, and the error. One notice per failure streak; the next one comes only after the bot has worked again. The on-duty person (if set) is still alerted as before.

## [0.166.2] - 2026-10-15
### Fixed
- **Creating images on the ChatGPT plan no longer gets stuck on "The 'gpt-5.5' model is not supported".** When your plan lacks that model, Javis switches to another model from your own account's ChatGPT model list and makes the image, with nothing to configure.
- Next time Javis goes straight to the model that worked, so no extra failed round. Letting ChatGPT look at images for you is fixed the same way.

## [0.165.1] - 2026-10-15
### Fixed
- **Files and links in a Project (and in each conversation) stay newest first** even when two were added in the same instant. Before, two items with the same timestamp could swap places at random between visits.

## [0.164.1] - 2026-10-15
### Fixed
- **Conversations and projects created in the same instant now keep their order**, newest on top. On a fast machine two of them written in the same tick could swap places at random in the sidebar.

## [0.164.0] - 2026-10-15
### Added
- **The Fast mode bolt now really switches each brain:** Claude Code and the Anthropic API (Opus 5.5, Opus 5, Opus 4.8), ChatGPT through Codex, the OpenAI API, OpenRouter and Gemini. Brains without Fast mode (Grok, Antigravity, Groq, DeepSeek, Ollama) keep a dimmed bolt.
- **Bolt off means normal speed:** for Codex, Javis forces the normal tier even when the model or the Codex config defaults to Fast. Background runs (loops, reminders, Kanban, workflows, teams) and customer chatbots always run at normal speed, even if you once turned on `/fast` in Claude Code.
- **When a provider refuses Fast mode** (account not eligible, limit reached), Javis resends at normal speed and the turn does not fail; hover the bolt to see why (e.g. usage credits need turning on).

## [0.162.0] - 2026-10-15
### Security
- **Plugins you install load by default**, no environment variable needed. Each plugin still runs only after you click **Enable** on its card (a plugin Javis creates from chat always starts disabled), and the permission level still decides every tool call.
- To block user plugins on a machine altogether (a shared server, bots for strangers), set `JAVIS_ENABLE_USER_PLUGINS=false` and restart.

## [0.160.0] - 2026-10-15
### Improved
- **The Effort chip reads the real level of Antigravity models** that carry it in their name (e.g. `-high`), on the chip and in the slider popover.
- **The slider popover stays on screen** on narrow phones, the orange particle effect is lighter (nothing is re-measured every frame), and an interrupted swipe no longer makes the slider jump.
- **Ctrl+U opens the file picker only when a usable chat box is there**, not on other pages or while the chat box is locked.
- **The connections-to-fix count in the + menu** is refreshed each time the menu opens.
- **Leaving the Partners page mid-turn** no longer re-enables the Send button by mistake.

## [0.159.0] - 2026-10-15
### Improved
- **Sturdier folder pinning:** switching brain no longer binds a pending pin in the new brain; a folder inside the brain picked with the browser is no longer labelled "outside the brain"; the folder search returns folders only, so files cannot crowd them out.
- **The folder chip shows "+N"** when the conversation still has extra folders bound from before, with their names on hover. Unpinning removes a folder nobody else uses from the registry (nothing on disk is touched).
- **The pin panel shows the pinned folder and the Unpin button as separate rows.**
- **The Coding page shows errors in their own slot**, so a chip redraw no longer wipes them; leftovers of the old folder picker are cleaned up.
- **If the connection drops while the first message waits for the folder pin**, the text goes back to the input with a notice instead of being lost.

## [0.158.0] - 2026-10-15
### Improved
- **Pin a working folder straight from the chat box.** The **+** menu has **Pin working folder**: pick a folder in the brain (with search) or browse to another one. Once pinned, a 📁 chip with the folder name sits next to the bolt and that conversation works right inside the folder, handy for code projects. The pin is per conversation.
- **Adding a folder no longer uploads its files** as attachments: a folder is a place to work in.
- **The Coding page uses the same folder chip** instead of its own folder button; the branch, worktree, restore point and permission chips stay.
- **A tidier assistant Work tab:** the two sideways-scrolling chip rows are now two dropdowns, **Source** and **Status** (with counts and an amber dot when something needs you), and the text is smaller to fit the narrow column.

## [0.153.0] - 2026-10-15
### Improved
- **The chat composer is redesigned in the style of Claude:** one rounded card holding attachments, the text box and a single button row underneath (the **+** button, model chip, Effort chip, Fast mode bolt, a small mic and a round send button).
- **The + button opens a menu:** attach a file or photo (Ctrl+U), attach a whole folder (skips hidden files, .git and node_modules, up to 50 files), pick a file already in the brain, commands and skills "/", **Connections** with the health of each, and **Assistants and workflows** for a quick call.
- **Effort is now its own chip** next to the model chip, opening a six-stop slider Off, Light, Medium, High, Extra, Ultra with an orange particle effect.
- **Fast mode bolt:** click to turn it on (an animated orange wave), click again to turn it off; hover for a cost note for the selected brain. This release stores the choice; wiring it into each engine comes next.

## [0.151.0] - 2026-10-15
### Improved
- **Resizable panels:** on the graph page (folder column and chat panel) and the Chat page (conversation list), hover the edge and drag; double-click to reset. The width is remembered.
- **The Chatbot inbox shows each conversation's message count** (grey pill, e.g. "12 msgs"), next to the red unread count.

## [0.147.0] - 2026-10-14
### Improved
- **Background jobs now take one tidy line above the chat box.** The old "running in the background" block took three lines with a button and a row of chips, and cut job names off mid-word. Now it is one small pill: a green dot, the most relevant job (the one you just assigned in this chat first) and "+2" when more are running.
- **Click the pill for the details:** each job with its status, how long it has been running, which ones came from this chat, and a button to open the Tasks page. Click outside or press Esc to close it.
- Jobs that were assigned but will not run on their own (orchestration off) still show in amber and say so on the pill, with how to turn it on in the details.

## [0.146.0] - 2026-10-14
### Fixed
- **Team chat is no longer silent.** Assistants answer with their own model, or the main model when they have none, ChatGPT (Codex) included. Each message shows who is waiting, answering or could not answer, with the reason and a fix (**Try again**, change the model, pick a coordinator); it survives a dropped connection or a reload.
### Added
- **Create a team and add members like on a messaging app:** accent-free search, tag filters, a ready-made team picture, members already in the team marked "Already in the team", the coordinator picked right on the chosen people; the team reads "You + N assistants". Typing @ works with the keyboard, each person called shows as its own chip, and two assistants with the same name still get the right one.
- **Jobs tab on the Partners page** (replacing the Folder tab): every job of one assistant from teams, private chat and Auto, filtered by source, with the next step. **Assign a job** takes done criteria, lets you choose where the result goes and shows a review before creating; you can also assign a **verification** job to another assistant.
### Improved
- **Tidier Partners page:** Resonance is now called **Auto**, with its switch on the tag row and in the three-dot menu; cards show the time of the last message; the right panel starts hidden so text gets wider, and both columns can be resized by dragging their edge. Fixed reviewers are gone: old goals waiting for review are paused for you to check, never counted as passed.

## [0.145.0] - 2026-10-14
### Fixed
- **A finished background job is no longer blocked just for mentioning [[NEEDS_INPUT]].** Any mention anywhere in the result used to count, even in a sentence like "no need to write [[NEEDS_INPUT]]", so a job that met its completion criteria still waited for you. Now a job only waits when the worker starts a line with the marker, as it is told to. The block reason on the bell is taken from such a line too.

## [0.141.0] - 2026-10-14
### Improved
- **Zalo bots can see the photo in a quoted message.** Quote (reply to) a photo and tag the bot with "look at this" and the bot sees that photo. Before, the bot got only the text and said it could not see the photo, so you had to send the photo again and tag within 3 minutes.
- Works in groups and private chats, and when you press "Reply for me" in the inbox. The photo must be one Javis read when it was sent, that is, sent after the Zalo account was connected.

## [0.140.0] - 2026-10-14
### Added
- **Teams page: several assistants in one chat**, like a group on a messaging app. Write to the team and the lead answers; type @ to ask one person. Turn on **Assign job** and the lead splits the work across the team, with progress and results right in the chat.
- **Team jobs have a queue** with Prioritize, Edit request and Cancel. A blocked job comes with one button that resolves it, such as **Allow more turns** or **Try again**. You choose how much the lead decides alone: Ask me first, Act then tell me, or Run the whole team.
- **React and leave feedback** on answers so assistants adjust on the next turn. **Search old messages** in a team without typing accents. A team's picture is built from its assistants' real avatars, and you can **pin a team** to the top of the list (press and hold on a phone).
### Improved
- **Turn Resonance on or off right from the assistant list** on the Partners page. The switch only changes once the server confirms.

## [0.139.0] - 2026-10-14
### Fixed
- **Sending Excel, PDF and Word files on Zalo no longer hangs.** Javis used to wait up to 2 minutes on such a file, then fail without delivering it (images went fine). Files now go through the Zalo connection that serves the inbox, so they reach the recipient.
- **If Zalo does not confirm within a minute, Javis says so clearly and sends nothing**, so retrying is safe. No more waiting without knowing whether the file went.
- After updating, **update the "Zalo extras" pack to 1.2.0** from the Store. Javis moves the Zalo connection to javis-zalo 1.4.0 on its own (no new QR scan).
- Thanks to @thanhtmfyu-lang for the contribution.

## [0.137.0] - 2026-10-14
### Fixed
- **Antigravity CLI updates itself every day, so new models (such as Gemini 4 Argon) show up in Javis on their own.** The Antigravity model list comes straight from `agy`, and `agy` was never updated: the Docker build installed it once and left it there. Javis now runs `agy update` daily, Docker included. If `agy` is up to date and a model is still missing, your Google account has not been granted that model.
- **The bot no longer says it is having technical trouble and asks the customer to write again later** when a reply fails. That line told customers they were talking to a machine and made them do the work. The bot now asks them to wait a moment while it checks. The person on duty is still told about the real error, as before.

## [0.136.0] - 2026-10-14
### Improved
- **The personal Zalo bot answers when you have not replied within 10 minutes.** Before, once you typed into a chat yourself, customer messages that came after were dropped and nobody answered. Javis now holds them; if you do not answer within 10 minutes the bot answers them all once, in private chats only.
- **A customer who sends only a file or a photo without text also gets a fitting reply**: the bot is told what arrived (file name, photo), and a bot with Can write opens the file too. If you answer on the phone or from the Inbox, the bot stays out.
- Thanks to @thanhtmfyu-lang for the contribution.

## [0.135.0] - 2026-10-14
### Fixed
- **The Tools page now shows the Browser (Chromium) as Ready when it was installed by a recent Playwright.** Since Playwright 1.57 the headless browser's executable is called `chrome-headless-shell`. Javis did not know that name, so it kept saying "There is a browser folder but no executable, the download broke midway" on a complete, working install, however many times it was removed and downloaded again. Javis now recognises both the new and the old names. No new download is needed: after updating, the Tools page shows Ready.

## [0.134.0] - 2026-10-14
### Added
- **Bots answer your Facebook Page inbox (Messenger).** Add a Messenger channel on the Chatbot page; attach it to an existing bot and that bot answers on Zalo and Messenger with the same Agent. Customer messages land in the inbox like on every other channel.
- **The add-channel form shows the webhook address and verify token** to paste into the Meta app. When the bot is switched on, Javis subscribes the Page to the webhook by itself. If the token lacks the permission for that, the bot still runs and reminds you to subscribe the Page once by hand.
- **A wrong App secret is refused when you save**, instead of a bot that looks healthy but never hears a message.
- **Meta errors read as words:** more than 24 hours since the customer last wrote, app not yet approved to message the public, expired token. Step-by-step guide in docs/en/31-messenger.md.
- Thanks to @thanhtmfyu-lang for the contribution.

## [0.133.0] - 2026-10-14
### Added
- **The personal Zalo bot reads files customers send.** When a customer sends a file (Excel, PDF, CSV...) in a private chat, or sends a file and then asks "can you check this", the bot saves it to `inbox/khach` in its brain and answers with the file in hand. Text files (txt, md, csv, json...) are read directly; other formats are reported as not read, never guessed.
- Only bots with **Can write** or higher download files. A read-only bot still answers the text and knows a file was sent.
- No download for strangers, chats under human takeover, or files dropped into a group without anyone calling the bot. Files over 20 MB or with an expired link are reported as unreadable.
- Thanks to @tuanlong1989florist for the contribution.

## [0.131.0] - 2026-10-14
### Added
- **An operator theme.** Put a `theme.css` file in the `branding` folder of Javis's data (next to the logo) and the dashboard takes your brand colours and fonts, kept across every update. Delete the file to get the original look back. See the Branding and domain guide.
- Thanks to @hodaclong for the contribution.

## [0.130.0] - 2026-10-14
### Added
- **Chatbots have active hours.** In the Edit bot form on the Chatbot page, fill in **Active hours** From and Until, e.g. 08:00 to 02:00 (past midnight is fine). Leave both empty and the bot answers all day as before.
- **Outside active hours the bot stays fully silent** and sends nothing. Messages for the bot still land in the **inbox** so whoever is on duty reads them in the morning. Times follow the timezone in Settings.
- The bot card shows its active hours, and **Try bot** outside them says so plainly. Replying by hand from the inbox works at any hour.
- Thanks to @thanhtmfyu-lang for the contribution.

## [0.128.0] - 2026-10-14
### Improved
- **The personal Zalo bot waits until the customer has finished typing.** When a customer splits one thought over several messages, the bot waits for 5 seconds of quiet and answers once, covering everything, instead of replying piece by piece like a machine.
- **Sending a photo and then "can you check this"** in a private chat now reaches the bot as one question with the photo.
- If you type into the chat yourself while it waits, or turn the bot off, nothing is sent. Zalo groups work as before.
- To keep the wait short, an account that just had a private customer message is read every 2 seconds (instead of 20) for one minute. This only touches the buffer on the machine, with no extra calls to Zalo.
- Thanks to @thanhtmfyu-lang for the contribution.

## [0.127.0] - 2026-10-14
### Fixed
- **Bots on the ChatGPT plan no longer drop tool calls.** ChatGPT sometimes streams a tool call piece by piece and leaves the final summary empty, so the bot skipped the call and answered with half the work. The bot now collects them all, never runs one twice, and retries a stream that was cut off instead of acting on half of it.
- Thanks to @tuanlong1989florist for the contribution.

## [0.125.0] - 2026-10-14
### Fixed
- **Background jobs on ChatGPT (Codex) no longer report a fake success when tools are missing.** Reminders, loops and Kanban jobs on Codex now wait for Javis's MCP Hub to come up. If it does not, the job fails with a clear reason instead of running without tools and still being recorded as done.
- Thanks to @dev23072005 for the contribution.

## [0.123.0] - 2026-10-14
### Fixed
- **The bot really tags everyone it names in a Zalo group.** Before, only the person the bot was answering got a tag; an extra "@Anna" or "@Ben" in its message was plain text and Zalo notified no one. Now each "@Name" that matches someone who has written in the group becomes a real tag, ignoring case and accents.
- **A line you type in the inbox with "@Name" tags for real too.** People who have never written in the group cannot be tagged yet; their name shows as plain text.

## [0.122.0] - 2026-10-14
### Security
- **The open-file tool no longer runs programs.** Opening a file on the machine running Javis now refuses runnable files (scripts, programs, shortcuts). Opening an app by name works as before.
- **The login session file is readable by the owner only**, like the secret key and the hub token.

## [0.119.0] - 2026-10-14
### Fixed
- **Tools no longer land on the wrong brain when a session stores a short brain name.** Some chat sessions stored the brain as "brain" (the default brain) instead of a full path, so tools through the MCP Hub could not tell which brain to use, or could end up in a folder that is not a brain. They now resolve to the right brain. Thanks to @dev23072005 for the report.

## [0.118.0] - 2026-10-14
### Security
- **Tighter checks on live connections to Javis.** Every real-time connection (chat, terminal, voice, graph) now passes the same origin checks as write actions, including on machines with no password set. Your dashboard, Telegram and command-line tools are not affected. Updating soon is recommended.

## [0.117.0] - 2026-10-14
### Security
- **Background jobs on ChatGPT (Codex) keep their permission level.** A reminder, loop or Kanban job set to Read-only or Draft that ran on Codex could still call tools at Full access. It now runs at the level it was given, like the other engines.

## [0.114.0] - 2026-10-14
### Fixed
- **The Zalo bot no longer goes silent after Javis restarts.** A Javis that stopped uncleanly (a crash, a hard stop during an update) used to leave the old Zalo process running, so the account had two listening sessions. Zalo delivers to only one of them, the bot read the other and stayed quiet. Javis now records every connector process it starts and clears what an earlier run left behind.
- **Safe cleanup.** It only clears a process when the old server is really gone and the process still runs the command Javis started, so nothing else is touched.

## [0.109.0] - 2026-10-13
### Added
- **An assistant can have a reviewer (Resonance A5).** On the page of an assistant with Resonance on, pick another assistant in the **Reviewer** box. From then on, new goals of this assistant count as done only after the reviewer checks the exact published version and passes it. Existing goals do not change.
- **When the review asks for changes, the assistant applies the feedback by itself**, at most twice. A goal with a team uses at most 8 calls, 4 per role; when the rounds or calls run out it stops and tells you, without extending them.
- **The goal card shows who makes and who reviews**, which version was reviewed, who is being waited on and the calls left per role. **Turn the reviewer back on** and **Drop the review requirement** buttons appear when the goal is stuck.
- Ongoing goals and discovery steps also wait for the reviewer to pass the version before reporting an update or a finished step; the same version is not reviewed again on schedule.
- A call that fails before the model is reached is given back, not counted.
- If a published file is edited by hand, a goal with a team waits instead of counting as done. To go back to 0.108.0: stop Javis and run `tools/resonance_restore_pre_a5.py`.

## [0.108.0] - 2026-10-13
### Fixed
- **The bot no longer sends plan-limit notices to customers.** Lines like "You've hit your session limit" or "API Error" used to be posted straight into a Zalo group, tagging the person who asked. That turn now counts as failed: whoever asked gets the usual apology, and the real reason is in the bot log.
- **Messages you type by hand on personal Zalo reach the inbox.** Replies the owner or staff send from the phone now show as "You", and the bot steps back in that chat. The cause was in the Zalo CLI, which dropped every message from the account itself; Javis now runs javis-zalo 1.3.0.
- **No duplicates, no wrongful silence.** Images the bot just sent and lines you type in the inbox are recognised when they come back, so they are not recorded twice and the bot does not think you just stepped in.

## [0.107.0] - 2026-10-13
### Fixed
- **Background jobs only reach Done when they really pass.** After the worker finishes, a separate AI pass checks the result against the acceptance criteria and opens the files and images they name. A job that falls short waits for you with the real reason (no longer the last line of the report), and the alert names the jobs waiting on it.
- **Workflows no longer "accept for now".** A verify step that errors or answers vaguely now counts as a fail; a step still failing after its retries stops the workflow there instead of running on. A switched-off workflow no longer runs in the background.
- **Chat can queue a job that runs a real workflow** with `route: wf:<name>`; a wrong name is refused, and only naming the workflow in the description gets a warning. A job that needs images gets the image tools alone, without opening Full access, and each workflow step can declare its own tools.
- **Usage, learning, reminders and Docker are more accurate.** A long chat moved onto a new thread still counts as chat instead of swelling "background"; the learning token cap counts real tokens. Script reminders are no longer skipped while a long reminder runs, and Docker keeps the Claude Code config and the Google Workspace sign-in across rebuilds.

## [0.105.0] - 2026-10-13
### Fixed
- **Self-learning no longer makes an agent forget rules you gave it.** Before, each time self-learning improved an agent it rewrote the agent's whole instructions, so a rule like "no markdown in Zalo messages" could vanish after a few rounds. Now self-learning can only add new rules at the end, and what you wrote stays as it is.
- **Rules you give in chat are kept for good.** When you give an agent a lasting rule, it goes into an **Owner rules** section of the agent's memory. That section is never pushed out the way self-made lessons are (only the 15 newest are kept).
- **A last safety check.** Any write that would drop even one line you wrote in an agent or its memory is refused.

## [0.103.0] - 2026-10-13
### Improved
- **Permissions per command for bundled tools.** An MCP tool that bundles several commands, such as GitHub's label tool that creates, edits and deletes labels, is now checked against the command actually called. Create and edit run at Draft level, delete still needs Full access.
- **Tools with only write commands no longer show at Read-only.** Before, they were offered and then blocked on every call. Now they only appear from the level that can run them, and the block message names the blocked command.

## [0.102.1] - 2026-10-12
### Fixed
- **Bots no longer apologise to people who did not ask them.** In Auto-judge mode a bot looks at group messages that do not name it. Before, when such a turn failed, the bot tagged the sender and posted its "I'm having technical trouble" apology to the whole group. Now it stays quiet, the error still goes to the bot log and the on-duty person is still told. Someone who called the bot and hit an error still gets the apology.
- **Full-access bots no longer show technical text to customers.** Lines such as "error during the turn" or the model warning now appear only in the bot log, not in the reply.
- **Full-access bots no longer change your main model.** When the Agent's model does not run on the ChatGPT plan, the bot still runs on a replacement, but no longer overwrites the model you picked on the Models page.

### Improved
- **The bot form says "Zalo Bot" or "personal Zalo".** The two share one logo but only personal Zalo can join groups. When a bot only has private-chat channels, the form says why there are no group options (Mentioned, Auto-judge, Every message) and which channel to add to get them.

## [0.102.0] - 2026-10-12
### Added
- **Lark (and Feishu) as a chatbot channel.** On the Chatbot page, add a Lark account with the App ID and App Secret of a separate Lark app, attach it to a bot, and the bot answers customers on Lark, with every chat in the Inbox and takeover like the other channels. No domain needed: Javis opens the connection out to Lark.
- **Lark bots join groups, send images and documents**, see the photos customers send, and you can reply to a customer straight from the Inbox.
- **Javis works out whether the app is on Lark or Feishu**, nothing to pick. Pasting the app that runs your admin channel is refused right away, since two connections on one app get messages split at random.
- **The Inbox shows Lark customer and group names** when the app may read contacts and chat info. Without those permissions the bot still runs and shows the ids.

## [0.100.0] - 2026-10-12
### Improved
- **Assistants can carry several tags.** Instead of one group, each assistant now has any number of tags (Marketing, Writing, Engineering...). The old group becomes one tag; nothing is lost.
- **Add and remove tags on the Partners page:** the **...** button on an assistant, item **Tags**. Click a tag to add or remove just that one, or type a name to create a new tag. The bar above filters by **All agents**, **Untagged** or one tag; an assistant with several tags shows only once.
- **Renaming or deleting a tag** applies to every assistant that has it; renaming to an existing name merges the two. Deleting a tag only removes the label, never the assistant or its chats.
- Tags only sort: they add no one to a group chat and grant nothing. Workflows keep their groups.
- Going back to an older release: an assistant shows under a group named after its first tag.

## [0.99.0] - 2026-10-12
### Added
- **German interface (first step).** With a German browser the dashboard shows German in the navigation, the Settings tabs and common messages. Anything not translated yet shows in English. Translation contributed by @sirschnake.
- **"Deutsch" in the language pickers**, both under the side rail and in Settings, so you can switch back to German after choosing another language.

### Fixed
- **Readers of the German interface no longer get Vietnamese from Javis.** The server speaks only Vietnamese and English, so for a language that exists only in the dashboard, Telegram messages, background work, the voice and the default brain now use English. Before, they could fall back to Vietnamese.

Thanks to @sirschnake for contributing the German translation (#618).

## [0.96.1] - 2026-10-11
### Fixed
- **Updating no longer locks you out.** On servers that set the account from the environment (Docker, Hostinger) where `JAVIS_ADMIN_PASSWORD` carried a stray space, from 0.92.1 the first boot after an update took the environment password as changed and reset the account. The password you had changed in the dashboard was overwritten and the username became `admin`. Updating now leaves the account alone; only a real change of the environment value resets it.
- **If your server was already reset:** sign in with `admin` (or your `JAVIS_ADMIN_USER` value, if you set one) and the password in `JAVIS_ADMIN_PASSWORD` on Hostinger, without the stray space. Then change the name and password back in Settings.

## [0.96.0] - 2026-10-11
### Added
- **Resonance assistants only write to files you have allowed.** A new goal, or a switch to another file, makes the card ask "The assistant wants to write to ... Allow?" with the exact path. Once allowed, the assistant keeps working without asking again for each revision.
- **What the assistant drafts before you allow it is kept as a draft.** Preview it, then Allow publishes exactly that version, with no new model call.
- **Codex and API-key brains can also hand in their work during the chat**, through the same check as Claude: Javis reads, verifies and publishes the submission itself, and never overwrites a file you edited.
- **A Revoke permission button on the goal card** stops the goal right away; press Resume to grant it again. To go back to 0.95.1, stop Javis and run `tools/resonance_restore_pre_a4.py`.

## [0.95.1] - 2026-10-11
### Fixed
- **Ollama (Local) no longer "returns nothing" after thinking too long.** Models like qwen3 turn thinking on by themselves, and a job such as counting the rows of a file could spend the whole turn thinking without writing a word. Javis now switches thinking off for local models, with or without tools, so they answer directly.
- **The Effort button no longer drags the local model along.** Leave Effort at Medium or Very high for Claude and the local model still answers directly, so switching between the two no longer means toggling it every time.
- **When a model only thinks and never answers, Javis says exactly that**, with what to do (lower the thinking level or split the task), instead of a "returned nothing" that looks like a lost connection.

Thanks to the user who reported this with a patch tested on a Mac.

## [0.94.0] - 2026-10-11
### Improved
- **Bots see customer photos whatever model runs them.** A bot whose model can see images still looks at the photo itself. When the model cannot (Antigravity, Grok Build, a text-only model) or returns nothing for a photo, another brain you already connected looks at it and describes it, copying prices, order codes and phone numbers exactly. The order: your main brain, then the ChatGPT plan, then Claude Code.
- **Bots remember what the earlier photo showed.** When a customer follows up about "the thing in that photo", the bot still knows, because the description stays in the conversation.

### Fixed
- **Zalo photos are no longer dropped by mistake.** Zalo's photo server labels some photos as generic binary files instead of images, and Javis skipped them before the bot could see them. Javis now checks the file's own content to recognise an image.
- **The bot card shows the real error when a model rejects a photo**, instead of a generic "refused the image". When no brain can look, the card says why each one could not.

## [0.92.2] - 2026-10-11
### Fixed
- **Ollama (Local) can use tools.** With a model running in Ollama on your own machine, the model could not read files or call any connection and said it had no tool permission, because Javis forgot to load tools for this kind of model. Local models now get the same tools as the API models, and the Connections page no longer says they cannot call tools.
- **The Local Model page on Apple-chip Macs says the GPU is used.** It used to say "Runs on CPU and RAM" while Ollama ran fully on the chip's GPU. Javis now recognises Apple chips even when Python runs under Rosetta, counts the shared RAM as GPU memory, and no longer drops the GPU when you enter the RAM size by hand.

### Improved
- **API and local models can read PDF and Word (.docx) files.** These files used to come out as binary noise. A scanned PDF (images only) is reported plainly as having no text to read.

Thanks to the user who sent the bug report along with a patch tested on a Mac.

## [0.92.1] - 2026-10-11
### Fixed
- **Signing in no longer fails on capital letters or invisible spaces.** Usernames ignore case now, so "Phong" and "phong" both work. A stray space before or after the password, which phone keyboards often add, no longer reads as a wrong password.
- **When the password is right but the browser does not keep the session, Javis says so**, with the usual causes, instead of silently returning to an empty sign-in form.
- **On a server that sets the account from its environment, the wrong-password message points out that the username is `JAVIS_ADMIN_USER`** (default admin). Resetting the password through Hostinger also resets the username, which is easy to miss.
### Improved
- **The first-run screen is readable on the light theme.** Brain names, card borders and the Claude sign-in command used to be nearly invisible on a light background. On a public server, the admin account section now says it is required right away instead of a red line at the bottom.

## [0.91.0] - 2026-10-10
### Added
- **DeepSeek is a new brain.** Paste a DeepSeek API key on the Models page to pick `deepseek-flash` or `deepseek-v4-pro` as the main brain, for agents or for background work, with the same tools as the other API engines.
- **Thinking depth works with DeepSeek.** Set to Off, DeepSeek answers directly, cheaper and faster; turned on, it thinks first. If an older conversation does not fit thinking mode, Javis answers in normal mode with a one-line notice.

## [0.89.2] - 2026-10-10
### Improved
- **When a bot says it cannot see a photo, the bot card says why.** The reason used to stay in the server log, so a bot running on a VPS said it could not see the photo and the owner had no way to know what to fix. The warning line on the bot card now gives one of four reasons: the photo message carried no link, downloading the photo from Zalo failed (with the exact error), the bot's brain does not take images (Antigravity, Grok Build: switch the bot to a model that can see images), or the model refused the image.

## [0.89.1] - 2026-10-10
### Fixed
- **A customer-care bot no longer silently drops groups past the 50th.** A bot used to remember only its first 50 groups, so newly approved customer groups reported success but never made it into the list and the bot stayed silent there. The group list is no longer cut. (Contributed by @nhuy288-8.)

## [0.89.0] - 2026-10-10
### Added
- **Resonance assistants learn from feedback, with checks.** React to an assistant's notice to suggest shorter or less disruptive updates; you preview the change and decide whether to apply it.
- **When stuck, the assistant tries one other method, only if the goal's budget covers both the trial and one more pass on the deliverable,** compared with the old method on the same criteria; a losing or unclear result keeps the old method.
- **Every lesson has a source, a scope and a revoke button.** After you revoke or dismiss a suggestion, Javis waits 14 days before suggesting the same change again. Feedback never marks a goal done by itself and never grants more permissions or budget.

## [0.88.6] - 2026-10-10
### Fixed
- **The Zalo bot card states the real reason when the Zalo connection drops.** The card used to show only a technical config line like `process closed stdout ([mcp] Config loaded: ...)`, with the real reason cut off. It now says it in plain words. If Zalo closed the session because the account was just opened somewhere else (Zalo Web in a browser, or another Javis machine signed in to the same account), the card says to close the other one and that Javis reconnects in about 2 minutes. If the Zalo sign-in expired, it says to sign in again with the QR code on the Connections page. Any other error shows the end of the message, where the real reason is.

## [0.88.5] - 2026-10-10
### Improved
- **Conversations with many goal cards open faster.** Cards of the same goal share one load instead of one each, and are redrawn once.
- **Opening a goal card no longer makes other pages wait.** Javis reads goal state on a separate thread and only reads what the card shows, so goals with a long history still open quickly.
- **You can see how long Javis spends on each request.** Every response carries a `Server-Timing` header, to tell slowness in Javis from slowness in the network or proxy (Cloudflare).

## [0.88.4] - 2026-10-09
### Fixed
- **The Partners page no longer shows up empty now and then even though the brain has assistants.** Opening the app straight on this page, Javis does not know the brain yet, so it loads the default brain's list (empty), then loads again once the real brain is known. If the first load came back later, it overwrote the right list and the page said there were no partners yet. Results from an outdated load are now dropped. If the server reports an error while loading the list, the page shows the error with a Retry button instead of pretending the list is empty.

## [0.88.3] - 2026-10-09
### Fixed
- **A bot in a Zalo group sees the photo when a customer sends a plain photo and then calls the bot.** A photo without a caption used to be dropped on arrival, so the most common way to ask, a photo followed by "@bot take a look", made the bot say it had not seen any photo. A photo with a few words of caption worked, which made it look random. The bot now remembers a plain photo for 3 minutes and sees it when that person calls the bot.
  - In Auto-evaluate mode, an untagged message like "look at the photo above" that the bot decides to answer also comes with the photo.
  - A brief failure downloading the photo from Zalo (a network blip, a photo not ready yet) is retried once instead of reporting the photo as unseen right away.

## [0.88.2] - 2026-10-09
### Fixed
- **Old ChatGPT chats recover by themselves after moving to another machine or VPS.** The Codex session files stay on the old machine, so an old chat kept failing with "no rollout found" while a new chat worked fine. Javis already rebuilds the context from chat history in this case, but did not recognise this error, especially when Codex only printed it and exited. Javis now recognises it and rebuilds once. Sign-in, usage limit and network errors are still reported as before. (Reported by @dev23072005, issue #595.)

## [0.88.1] - 2026-10-09
### Fixed
- **Assistants with accented Vietnamese names open their Settings tab on the Partners page.** An assistant whose name had Vietnamese accents always showed "Could not load this assistant", and could not be deleted or exported either, because its file name kept the accents while the read step only accepted plain letters. Existing assistants now work normally, and new ones get a file name without accents. The Studio starter set also no longer fails to find its reviewer assistant in the verify step.

## [0.88.0] - 2026-10-09
### Improved
- **Resonance assistants call the model only for a reason.** A new task, new feedback from you, or a retry still within its limit. While waiting on you they sleep; periodic reviews are code-only checks that back off to once a week.
- **No pointless retries.** Two attempts in a row without progress pause retries until you give feedback; errors are retried at most 3 times; automatic retries always leave one call for your feedback.
- **Files you edit by hand are not overwritten or redone.** Javis tells you once and re-checks on its own; a paused goal still watches its protective conditions, and turning an assistant off says clearly that watching stopped.
- **The goal card shows why the assistant woke up** and its recent wake-ups, with or without a model call.

## [0.87.0] - 2026-10-08
### Added
- **Resonance per assistant.** Each assistant has its own switch on the Team page. Only an assistant with it on sets and pursues goals; regular chat no longer creates goals. The assistant's right panel lists the goals it is pursuing.
### Changed
- **The per-brain Resonance switch is no longer used.** Goals set before this version wait under "Waiting for assignment" in Settings and do not run until you assign them to an assistant.
- **Deleting and recreating an assistant with the same name makes a new assistant.** It must be turned on again; old goals and conversations stay with the old one. Turning it on in a conversation opened before that prompts you to open a new conversation.

## [0.86.2] - 2026-10-08
### Fixed
- **Settings are no longer wiped when you open the WhatsApp tab or allow someone to message a bot.** Since 0.71.0, three places meant to save one small piece but overwrote the whole settings file: opening the WhatsApp tab on the Admin channels page for the first time, allowing a Zalo chat, and allowing a Slack, WhatsApp, Discord or Lark user. Each time, the HTTPS domain, API keys, the Telegram connection and every other setting were lost. A Docker install with its own domain could also lose HTTPS after the next reverse proxy restart. All three now update only their own part. Thanks to the DaoVix team for reviewing the code and sending a detailed bug report.
- **The settings file is written more safely.**
  - Writes are atomic: a machine shutting down mid-save no longer leaves a broken file.
  - A backup of the last good save is kept in `settings.json.bak`. If the file is broken, Javis reads the backup instead of quietly falling back to defaults and writing them over it, and keeps the broken copy for manual recovery.
  - Several saves at once no longer overwrite each other's changes.

## [0.86.1] - 2026-10-08
### Improved
- **With ChatGPT as the brain, the chat shows the step Javis is working on right away instead of going quiet until it finishes.** When Codex ran a long command (installing packages, scanning files, running a script), the chat used to show only "Javis is thinking..." counting up until the command finished, which looked like a hang. The step now appears the moment it starts, like "Running command: npm install", and is marked done when it finishes, just as with Claude.

## [0.86.0] - 2026-10-08
### Added
- **Resonance: Javis follows a task through until it is done.** When you hand over work that continues after the chat turn, Javis sets a goal with a clear finish line, works on it in the background within its budget, reports done only with evidence, and keeps the goal across restarts. The feature ships off and is turned on per brain.
- **A "What I'm working toward" card in the chat.** Tap Right or Not quite for how Javis understood you, Accepted for the result, or pause it. Feedback you add in chat attaches to the same goal and Javis revises the version you actually saw; a draft Javis writes during the chat turn is kept as the first version instead of being rewritten.
- **Try a new method before switching.** Javis compares its current way of working with one alternative on the same set of cases and switches only when the new one clearly wins; without enough evidence it keeps the current method.
### Fixed
- **A chat turn that lands while Claude Code is refreshing its sign-in now says it can simply be resent.** Newer Claude Code reports this with a different message that Javis used to show raw in English; normal answers that happen to contain "already used" are no longer replaced by that error note.

## [0.85.11] - 2026-10-08
### Fixed
- **The chat no longer sits on "Javis is thinking..." when the connection dies silently.** A sleeping laptop, a Wi-Fi switch or a flaky network can kill the link between the page and Javis without the browser noticing. Javis still finished the work, but the answer never reached the page, so "thinking" kept counting and you had to resend the command. The page now checks in with Javis after a stretch of silence. If nothing answers, it reconnects by itself and pulls in the answer that is already done. The Stop button also always reaches Javis, even when the connection is dead.

## [0.85.10] - 2026-10-08
### Fixed
- **A ChatGPT Live call in Vietnamese gets its answers in Vietnamese, no more sudden switch to English.** To look something up, ChatGPT Live rewrites the request and hands it to the main brain, sometimes in English. The main brain answered in the language of that rewrite, and Live then read the English answer aloud, which sounded like the voice changing mid-call. The main brain now answers in the language you actually spoke. Speak English and it still answers in English, and a language pinned in Settings still comes first. The same fix covers background jobs handed off from the regular talk mode.

## [0.85.9] - 2026-10-08
### Fixed
- **Update now on Docker keeps spinning until the new version is up, then reloads the page, with no false error.** The page used to wait only about 36 seconds and then say "The new version has not come up after a while - it may have failed", while Watchtower was still pulling the new version; a little later the page reloaded onto it anyway. The page now waits up to 10 minutes. Past 45 seconds it says plainly that the new version is still being pulled, which can take a few minutes on a slow machine. Real errors (Watchtower reports a failure, no new image yet) still show right away. The "Reload / Later" bar no longer pops up in the middle of an update either.

## [0.85.8] - 2026-10-08
### Added
- **Plugins know who is talking in a tool call.** The `pre_tool_call` and `post_tool_call` hooks get a new `turn` key (channel, sender, group or private, whether it is the owner), so a plugin wrapping an app with per-staff permissions can run tools with the rights of the person messaging the bot. The identity comes from the real message, never from what the model writes, and a bot is never treated as the owner. (Contributed by @nnbaonam96.)

## [0.85.7] - 2026-10-08
### Fixed
- **Brain sync with GitHub no longer fails on its very first push from a machine whose system language is not English.** When the GitHub repo was still empty, Javis read git's messages in the OS language and missed that case. It now talks to git in a neutral locale, so bootstrapping works regardless of the machine's language. (Contributed by @dev23072005.)

## [0.85.5] - 2026-10-07
### Improved
- **No more caps on the bot speaking up on its own in groups.** In auto mode the bot used to auto-reply at most 8 times per group and 3 times per person per hour, with a pause between turns. Speaking or staying quiet is now decided by the reply judge and the model, following the Agent's role and the documents; tune it with Right/Wrong in the reply judge.
- The bot still waits a beat and yields when you are typing by hand from that same account. A busy group will use more model usage; to cut it, switch that group back to answering only when called by name.

## [0.85.4] - 2026-10-07
### Improved
- **Bots no longer cap answers at 20 per person per hour.** Anyone who messages the bot directly or calls it by name gets an answer; the "you are typing too fast" reply is gone.
- The limit on the bot speaking up on its own in a group nobody called it in (auto mode) stays, so it does not flood groups. With no cap, one person messaging non-stop keeps spending model usage; if something looks off, take over that chat.

## [0.85.3] - 2026-10-07
### Fixed
- **Bots at Full power now run exactly like the admin channel.** This level used to take the bot's narrow route: with Grok Build and Antigravity the bot could use no tool at all, and with Claude Code it could not see the Gmail, Drive and calendar connections of the Claude account. A Full power bot now has the same brain, tools, MCP and skills as when you chat directly, keeping only the Agent's role.
- So Full power now also grants running commands on the server and reading every file. The warning before turning it on says so: only use it for a bot that only you or people you fully trust can message.
- Replies through Telegram, Zalo, Slack... from Grok Build or Antigravity are now saved properly to history and memory instead of being recorded as an error.

## [0.85.1] - 2026-10-07
### Improved
- **The Docker edition installs Antigravity CLI and Grok Build by itself.** These two cards on the Models page used to say "CLI not installed" with a command to type, and a Hostinger install has nowhere to type it. Javis now installs them at startup, once, and keeps them across updates.
- While installing, the card says "Javis is installing" instead of showing a command. If the install fails (no Internet on the server), the card says so and how to retry. Turn it off with `JAVIS_AUTO_INSTALL_CLIS=0`.

## [0.85.0] - 2026-10-07
### Added
- **Chat with Javis from Lark/Feishu and Discord.** Both new channels connect outwards, so they run on a laptop too, no domain needed. A stranger who messages the bot gets a pairing code; click Allow and you are done.
### Improved
- **The "Channels" page is now "Admin channels"**, so it is not mixed up with the customer bots on the Chatbot page, and each channel has its own tab with a dot showing which ones are running.
- **The confusing "Enable bot" checkbox is gone.** Each tab now starts with an On/Off switch that works immediately, the button at the bottom says what it does ("Save and turn on" or "Save changes"), and a missing field is named.

## [0.84.10] - 2026-10-07
### Fixed
- **Dedicated bots now read the Google Docs and Google Sheets links attached to their Agent.** Bots used to search only brain files, so an Agent told to "answer only from the documents" with its price list on Google Sheets said "no information" about every product.
- Spreadsheets are read tab by tab, every row with its column names. Edits on Google reach the bot within a few minutes. Works at every permission level, no need to raise the bot to Can write.
- The file must be shared with "Anyone with the link". An unshared file shows a yellow warning on the bot card naming the link. A link a customer pastes into a message is never opened.

## [0.84.8] - 2026-10-07
### Improved
- The Chatbots guide now states the actual limit: the bot answers each person at most 20 times an hour, counted per person in groups, and the number cannot be changed on the Chatbots page yet.

## [0.84.7] - 2026-10-06
### Added
- **Approve people asking to join a Zalo group from Javis.** When someone asks to join a group that requires approval, Javis tells you through the bell and Telegram. Ask "who is waiting to join group X" to see the list, then say "approve everyone" or "approve Lan, reject Minh" and Javis does it and reports back per person.
- A dedicated bot never approves on its own. The Zalo account must be the group's owner or a deputy, with the Zalo connection at Full access.

## [0.84.6] - 2026-10-06
### Fixed
- **A group bot no longer tells someone asking for the first time that they are "typing too fast".** The hourly reply limit used to be shared by the whole group, so once a busy group had called the bot 20 times, anyone who tagged it next was turned away with their name tagged. The limit now counts per person, as the setting says.

## [0.84.3] - 2026-10-06
### Added
- **Dedicated bots can send images to customers.** Tell the Agent when to send which image (e.g. "when asked about shirts, send `![Shirt](attachments/shirt.jpg)`") and the bot sends the real image right after its reply. Works on personal Zalo, Telegram, Slack and WhatsApp, at every permission level.
- Only real images inside the bot's own brain are sent, at most 4 per reply and 10 MB each. Documents such as PDFs are not sent, and the bot never attaches anything other than images the Agent named on purpose.

## [0.84.2] - 2026-10-06
### Added
- **See who joined a Zalo group and when.** Ask "who joined group X this week" and Javis answers with names and join times, including people your own account added. The log survives restarts.
- **Bots receive a "new member joined" event.** In a group the bot is allowed in, its Agent follows the instructions you wrote (welcome, a question) and what it sends tags the newcomer. Javis has no greeting of its own: if the Agent was told nothing about newcomers, the bot stays silent.
- Zalo only reports joins while connected, and the member list has no join date, so people who joined before this feature or while the machine was off have no join time.

## [0.83.2] - 2026-10-06
### Security
- **Bots can no longer be steered by invisible characters.** A stranger could slip instructions into a message using characters that do not show on screen (hidden characters, text-direction overrides), so the bot read them while the owner saw nothing in the inbox. Every message from Telegram, Zalo and customer bots is now cleaned of them before it reaches the brain and before it is saved.
### Improved
- **A broken connection no longer makes Javis sit and wait.** When a source has just failed to start, further calls to it within a minute get an error right away instead of each one waiting up to a minute to fail. A successful Check on the Connections page puts the source back in use at once.

## [0.83.1] - 2026-10-05
### Fixed
- **On Windows, file paths in replies are clickable again.** When Javis says "Saved to C:\...\post-1.txt" without backticks, the chat now turns it into a link that opens the file, as it already did on Linux and macOS.
- **On Windows, changing the time zone in Settings now takes effect.** Any zone other than Vietnam used to fall back to Vietnam time without a word, because Windows has no time zone table. The update installs it.

## [0.83.0] - 2026-10-05
### Improved
- **Zalo runs Javis's own build.** The personal Zalo connection now uses `javis-zalo`, which Javis maintains and fixes itself, instead of a third-party tool. Accounts already signed in by QR switch over on their own, no new scan needed.
- **Group message history works.** The brain can read older messages in groups as well as private chats, see who replied to whom and who was tagged, and find every message from one person or within a date range.
- When the QR code expires or Zalo rejects it, the sign-in window says why, instead of reporting success and then not working.
### Security
- The Zalo QR sign-in page no longer sends the machine's IP address to an outside service, and opening a browser or file no longer goes through a shell, so an odd file name cannot inject a command.

## [0.82.0] - 2026-10-05
### Improved
- **Third-party MCP connections always run the latest official release.** Google Search Console, Google Workspace, Google Tasks, Google Keep, NotebookLM and Google Ads move to each new release as the publisher ships it, instead of staying on whatever version a machine downloaded first.
- **Connections made earlier move to the new command too.** Each connection used to keep the command it was created with, so app fixes never reached machines that were already connected (old Zalo connections ran an unpinned version, old Google Sheets ones missed a fix). A command you edited by hand is kept.
- **Google Ads no longer needs Git.** Javis runs Google's official PyPI release instead of unreleased code from GitHub, and the Google Cloud Project ID box is gone because nothing reads it.
### Security
- **Google Workspace can no longer run Apps Script at the Draft level.** The new Workspace release added a tool that runs Apps Script functions, and Javis had filed it as read-only. It now needs Full access, and the tools that import files into Docs, Sheets and Slides count as writes.
- Gateway connections (one tool that runs many commands, like the new Hostinger release) are checked per command inside: reads run at Read-only, unknown commands count as dangerous.

## [0.81.1] - 2026-10-05
### Fixed
- **A mismatched encryption key no longer wipes your connections.** API keys, the ChatGPT login and the Telegram token are encrypted with the machine's own key. When that key did not match (volume recreated, key file lost), a single settings save, or the first startup after an update, used to overwrite them with empty values for good. Javis now keeps the old encrypted values, so putting the right key back restores every connection.
- With the right key nothing changes: clearing or changing a key works as before, and a key you type again is always saved.

## [0.81.0] - 2026-10-05
### Added
- **Bots look at customer photos with their own brain.** The photo goes straight into the chat turn for Claude, GPT, Gemini, OpenRouter, Groq, Ollama, the ChatGPT plan or the Claude Code plan to see, no longer depending on ChatGPT describing it. Photos are stored in the bot's brain and cleaned up like every other download.
- **Telegram reads photos in groups.** A photo with the bot tagged in the caption, a reply to a photo that tags the bot, or a photo sent just before tagging the bot (within 3 minutes, same person) all work. A logo sent as a File counts as a photo too.
- A brain that cannot see images (Antigravity, Grok Build, text-only models) makes the bot say plainly that it cannot see the photo, never guessing. If a model rejects the image, Javis resends the text so the customer still gets an answer.
### Fixed
- The Telegram bot used to say it could read photos while it actually received only a file path line, which also leaked a server path to the model. That line is now removed before it reaches the bot.

## [0.80.1] - 2026-10-05
### Fixed
- **Picking drive C in the brain folder picker no longer hangs on "Loading...".** Javis counted note files inside every subfolder, and `C:\Windows` alone holds hundreds of thousands of files, so the scan never finished. Each folder now gets a short counting budget, so drive C opens within a few seconds.

## [0.80.0] - 2026-10-05
### Added
- **A new bot permission level: Reads documents.** It sits between Read only and Can write: the bot searches, lists and opens documents in its own brain, so when a customer uses different words than the document ("money back" vs "refund") it still finds the answer instead of saying it has no information.
- **Still no writing and no data sources.** The bot gets three read-only tools, opens only the documents the pre-search already uses (no `memory/`, no customer uploads, no internal agent instructions), and only in its own brain. That is why this level needs no risk consent tick.
- **The reply judge sees the table of contents too.** At this level a group message that misses the keyword search is no longer silenced straight away; the judge decides whether it fits a document's topic.
- The **Try** button runs this level as is. A bot on the ChatGPT plan may not be able to call tools yet; then the bot card shows a yellow strip and that turn answers as Read only.

## [0.78.0] - 2026-10-05
### Added
- **A Try button on each bot card.** Type a message as a customer would (private or in a group, tagging the bot or not) and see right away whether the bot would reply or stay silent, why, what it would say and which documents it used.
- **Nothing goes out.** A try sends nothing to Zalo or Telegram, writes nothing to the Inbox, does not skew the reply judge's self-learning, and runs read-only so the bot never places an order or sends a real message.
- If a Telegram bot still has privacy mode on, the result says so: in a real group that message would not reach the bot.

## [0.77.2] - 2026-10-05
### Fixed
- **The Telegram warning on a bot card no longer breaks apart.** Each bold phrase used to become its own narrow column, one word per line. It now reads as a normal paragraph.
- **The Telegram privacy mode steps are complete.** After disabling it in @BotFather you must remove the bot from the group and add it again; that step was missing, so following the old steps still left the bot silent in groups.

## [0.77.1] - 2026-10-05
### Fixed
- **Changing the admin password on Hostinger now works.** `JAVIS_ADMIN_PASSWORD` used to apply only when no admin existed, so changing it in the Environment box and redeploying still said "Wrong username or password". Now, when the env value differs from last time, Javis resets the account to it; 2FA stays on and old sessions are signed out.
- An unchanged env touches nothing, so a password you change in the dashboard is not overwritten on every restart. This is also the way to recover a forgotten password on a VPS, no SSH needed.
### Improved
- **An eye button on the sign-in password field** so you can check what you typed.

## [0.77.0] - 2026-10-05
### Added
- **The group bot's reply judge reviews and tunes itself.** Once enough feedback has gathered, Javis gives the bot's numbers to your main brain (the strongest model you picked) to find repeated patterns, and it changes at most 3 things: lessons, examples, each group's threshold, eagerness. You get one message whenever it changes something.
- **Wrong turns undo themselves.** After each review the bot is measured again: if it is marked wrong more often, that review is undone. Issues that need a code change are written to `Javis/gop-y-bo-phan-xu.md`.
- **To adjust it, just tell Javis.** "Why is my bot so quiet?", "let the bot answer for me when customers tag me about class times", "undo the last review": Javis reads the real numbers and makes the change. Customer-facing bots never see these tools.
### Fixed
- Messages that start by **@tagging someone else** (say, a customer tagging the owner about the bot's topic) used to be ignored no matter how often you marked them wrong. A thumbs-down now works, and the self-review can turn on considering such messages.

## [0.76.0] - 2026-10-05
### Improved
- **The Skills page is easier to use.** Each skill has its own on/off switch on the right, so there are no longer two look-alike checkboxes where a wrong click turned a skill off. Click a skill to open its details: description, "When to use", usage, and Edit, Export, Delete.
- **Pick several skills to take elsewhere.** A checkbox at the start of every card is always there; pick some and an "Export N skills" button appears. The .zip imports into another Javis, or unzip it into a .claude folder and Claude Code uses it right away. The other way round, importing a bundle with several skill folders now brings them all in, not just the first.
- **Filter and sort:** show On, Off or System skills, sort by Most used or Name. Duplicate groups such as "ai" and "AI" are merged, and saving a skill fixes its group name.
- **Fixes:** turning a skill on or off on page 3 no longer jumps back to page 1. The description box counts characters and warns as soon as it passes 150 (the part Javis cannot read is shown in red), and a failed save now says why instead of closing the form as if it had saved.

## [0.75.1] - 2026-10-05
### Improved
- **The theme now defaults to Auto.** A device that never picked a theme turns light at 06:00 and dark at 18:00 by itself, instead of staying dark all day. If you already picked Dark or Light by hand, that choice stays.

## [0.74.2] - 2026-10-04
### Fixed
- **ChatGPT no longer dies on the first turn with "Could not find home directory".** On some Windows computers Codex could not find the user folder, so it missed the ChatGPT sign-in even though the Models page showed it as connected. Javis now tells Codex where that folder is, so chat, the model list and ChatGPT Live work there.
- **If it still happens, the error says what to do**: sign out of Windows and back in, or restart, instead of one cryptic English line.

## [0.74.1] - 2026-10-04
### Fixed
- **The Zalo bot can see the images customers send.** Tag the bot on a photo (like "@YourBot here it is") and it no longer replies "I can only read the caption": Javis saves the photo into the bot's brain and has ChatGPT on your signed-in plan look at it and describe it, so the bot answers from what the photo actually shows. It also works when you press "Reply for me" in the Inbox.
- **Without ChatGPT signed in, the bot still replies as before**, from the caption, and says plainly it could not see the photo, never guessing what is in it.

## [0.74.0] - 2026-10-04
### Added
- **The theme can follow the clock.** In **Settings → General → Theme** pick Dark, Light or Auto. On Auto the page turns light at the morning time and dark at the evening time by itself, 06:00 and 18:00 by default, and you can change both.
- **Each device chooses for itself.** Your phone can stay on Auto while your computer stays dark. The moon button in the top bar still switches by hand; pick Auto again in Settings to go back.

## [0.73.0] - 2026-10-04
### Added
- **Javis can see the images people post in a Zalo group.** Ask something like "look at the receipt Lan just posted in the Sales group" and Javis fetches it, shows it right in chat and says what is in it, copying text and numbers verbatim. Images come straight from Zalo, so the 2-hour limit is gone.
- **Every brain can see images.** Claude Code and Codex open the image themselves. OpenRouter, Gemini and the other API engines have ChatGPT on your signed-in plan look at it and describe it, no API key needed, for any image in the brain, not only Zalo ones.
### Improved
- **The extra Zalo tools moved to the "Zalo extras" pack on Javis Store.** Sending images, tagging people, notes, reminders, polls and reading group images no longer ship inside the app, so people who do not use Zalo do not carry them. Javis offers the pack right after you scan the Zalo QR.
- **Already using Zalo?** Open the Connections page and press **Install companion pack** once to get every tool back. The Zalo connection, the Inbox and the Zalo chatbot keep working without it.

## [0.72.1] - 2026-10-04
### Fixed
- **When Claude Code is too slow to start, Javis now says where it got stuck instead of guessing "probably a data source".** The error now tells you whether Claude Code reached Javis's tool hub at all, whether the hub answered fast or slow, and quotes the line Claude Code itself printed, such as an expired sign-in. The verdict comes first, so it stays readable on the bot card.
- **The error no longer says "the allowed limit" from the second turn on.** It always names the real number of seconds.
- Full details of every timeout are also written to the server log on a `[claude init timeout]` line.

## [0.71.2] - 2026-10-04
### Fixed
- **A ChatGPT Live call no longer goes silent while Javis works on something long.** Every follow-up question used to wait behind the running job, so "are you done yet?" got no answer, and when the job finished Javis read out a pile of stale replies. Now a progress question is answered at once from the real state: what is running, for how long, and which step it is on.
- **A new request no longer waits for the old one.** Asking for something else while Javis is still working runs it alongside, and each result is read out as it arrives.
- **Javis speaks up during long jobs.** Past one minute, about every minute and a half, Javis says a short line that it is still working, whenever you are not talking. These lines are not saved to the chat history.

## [0.71.1] - 2026-10-03
### Fixed
- **The Models page lists the newest ChatGPT models, such as GPT-6.1-Sol.** On a machine with both Codex Desktop and the Codex CLI, Javis always asked the copy bundled with Codex Desktop, even when it was months old, so the model list stopped at an older generation. Javis now picks the newest Codex on the machine.

## [0.71.0] - 2026-10-03
### Added
- **Chat with Javis on Slack and WhatsApp.** Turn them on from the Channels page, like Telegram and Zalo. Slack even runs on a laptop with no domain; WhatsApp uses Meta's official API and needs Javis on an HTTPS domain.
- **Customer bots on Slack and WhatsApp.** Add an account on the Chatbot page and an agent answers whoever writes in, with every chat in the shared inbox and takeover, as with Telegram and Zalo.
- **Strangers never reach your brain.** An empty allow-list lets nobody in: whoever writes gets a pairing code and you click Allow once. Background work handed over from Slack or WhatsApp reports back there.
- **A step-by-step guide** in docs/en/29-slack-whatsapp.md, with a Slack app manifest you paste and go.

## [0.70.2] - 2026-10-03
### Security
- **The sign-in screen now fully covers the dashboard.** It used to sit over the dashboard behind a blur, so you could still make out the layout underneath, most clearly in the light theme. The backdrop is now solid: until you sign in, all you see is the sign-in box. Your data was already blocked by the server; this hides the rest.

## [0.70.1] - 2026-10-03
### Improved
- **The README explains why your data stays yours.** "Why Javis" now covers the lock-in of keeping all your work on one AI vendor, and lists where each thing you build up (chat history, memory, skills, agents, workflows) lives on your machine, so a new model is a switch, not a fresh start.
- **A row of flags at the top of the README.** Twelve flags, each linking to its translation. Emoji flags show as letters on Windows; these are real images.

## [0.70.0] - 2026-10-03
### Improved
- **Five animated diagrams in the README:** one-command install, a swappable brain that keeps every tool, one chat message turning into the right action, a growing Second Brain, and work running overnight. They are light, sharp on phones, and hold still when the device asks for reduced motion.
- **The README in 7 more languages:** Hindi, Portuguese, Korean, Russian, German, French and Indonesian, 12 in all. Language bars are generated from one list, so they never miss a language or point at a missing page.

## [0.69.0] - 2026-10-03
### Improved
- **The README now also comes in Chinese, Spanish and Japanese**, and so does the quick start. Each says plainly that it is a machine translation, that Javis replies in any language, and that the interface is in English and Vietnamese.
- **Stale translations get flagged.** After an edit to the English README, GitHub points out which translations need updating, without blocking a release.
- **The website folder is gone.** The landing page will live elsewhere, which keeps the repo lean.

## [0.68.1] - 2026-10-03
### Improved
- **The GitHub page shows a real brain.** The screenshot at the top of the README and the link preview image now show the graph of a brain with more than 1,600 notes, instead of an empty one.

## [0.68.0] - 2026-10-03
### Improved
- **The Updates page speaks English.** Devices reading in English see the release notes in English from 0.66.0 on; older releases still show in Vietnamese.
- **Open to international contributors.** The repo now has an English contributing guide, an architecture overview and a glossary of the Vietnamese names used in the code, plus forms for bug reports, feature requests and translation offers.
- **A security policy and a code of conduct.** Security problems are reported privately, never in a public issue.

## [0.67.0] - 2026-10-02
### Improved
- **Javis now speaks English all the way through.** Error messages, the Models page, the connection store (descriptions, guides, permission warnings), the Plugins page and newly created brains all appear in English when your browser is set to English. Vietnamese users see exactly what they saw before.
- **One language per device.** A phone set to Vietnamese and a laptop set to English each see their own language, including the text that comes back from the server.
- **The website has an English version**, with the Vietnamese one a click away under "Tiếng Việt" in the menu.

## [0.66.0] - 2026-10-02
### Improved
- **The GitHub page is now in English**, with real screenshots, a table of the 12 brains and a language bar. The Vietnamese version is complete too, one click away at the top of the page.
- **The interface follows your browser's language** on a device that has not picked one yet. A device already using Vietnamese keeps it.
- **Anything not translated yet shows in English** instead of Vietnamese, so people reading in another language can still follow it.
- **The Linux/macOS install and update scripts print their messages in English.**
