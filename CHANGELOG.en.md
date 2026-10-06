# Changelog

*[Tiếng Việt](CHANGELOG.md) · **English***

Javis OS release history, newest first. You can also read it inside the app under **Settings → Updates**.

English entries start at 0.66.0. Every earlier release is described in the Vietnamese [CHANGELOG.md](CHANGELOG.md), which remains the maintainer's original; the in-app Updates page shows those older entries in Vietnamese.

Format: each release is a `## [x.y.z] - date` block, with changes grouped under `### Added / Fixed / Improved / Security`.

## [0.84.4] - 2026-10-06
### Improved
- **Resonance: goals are carried forward and checked against evidence.** A goal Javis has framed is now worked step by step within its budget, reported done only when there is evidence against its criteria, and scheduled for its next step instead of checking in on a timer. Off by default, not enabled for anyone yet.

## [0.84.1] - 2026-10-06
### Improved
- **Resonance: Javis turns a request into a goal by itself.** When you hand Javis something that needs following up after the chat turn, it frames it as a goal with a way to tell when it is done, without asking you to fill anything in. Ordinary questions stay ordinary questions. Off by default, not enabled for anyone yet.

## [0.84.0] - 2026-10-06
### Improved
- **Groundwork for Resonance.** Javis starts gaining a layer that lets a request you hand it be pursued until there is evidence it is done. This release only checks the internal execution path; nothing is switched on for users and nothing about how Javis works today changes.

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
