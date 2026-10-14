# Changelog

*[Tiếng Việt](CHANGELOG.md) · **English***

Javis OS release history, newest first. You can also read it inside the app under **Settings → Updates**.

English entries start at 0.66.0. Every earlier release is described in the Vietnamese [CHANGELOG.md](CHANGELOG.md), which remains the maintainer's original; the in-app Updates page shows those older entries in Vietnamese.

Format: each release is a `## [x.y.z] - date` block, with changes grouped under `### Added / Fixed / Improved / Security`.

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
