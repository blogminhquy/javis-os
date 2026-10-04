# Changelog

*[Tiếng Việt](CHANGELOG.md) · **English***

Javis OS release history, newest first. You can also read it inside the app under **Settings → Updates**.

English entries start at 0.66.0. Every earlier release is described in the Vietnamese [CHANGELOG.md](CHANGELOG.md), which remains the maintainer's original; the in-app Updates page shows those older entries in Vietnamese.

Format: each release is a `## [x.y.z] - date` block, with changes grouped under `### Added / Fixed / Improved / Security`.

## [0.74.2] - 2026-10-04
### Fixed
- (in progress)

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
