# Privacy policy

JAVIS OS is software you install and run yourself, on your own computer or server. There is no JAVIS OS cloud service and no JAVIS OS account. The developer does not receive your notes, your chats, your settings or any statistics about how you use the app.

**This program will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it.**

## What stays on your machine

Everything Javis stores: your brain (notes, memory, wiki), chat history, settings, connection tokens and API keys. They live in the install folder (`JavisOS` in your user folder for the desktop installers). API keys and tokens are encrypted in `settings.json` with a key that stays on that machine.

No analytics, no crash reports, no advertising identifiers, no tracking of any kind.

## What Javis downloads on its own

To tell you that an update exists, Javis reads public files over HTTPS. These requests carry no information about you or your data. As with any download, the server sees your IP address.

- **GitHub** (`raw.githubusercontent.com`, `github.com`): the current version number, the changelog, community announcements and the catalog of the add-on store.
- **PyPI** (`pypi.org`): the latest version number of the Claude Agent SDK.

JAVIS OS itself is updated only when you press **Update**. The AI command-line tools are different: once a day Javis runs the vendor's own update command for Claude Code and Antigravity CLI, and takes a newer Claude Agent SDK from PyPI, so that new models and security fixes arrive. The Claude part has a switch on the Models page (or `JAVIS_CLAUDE_AUTO_UPDATE=0`); `JAVIS_AGY_AUTO_UPDATE=0` turns the Antigravity part off.

## What is sent because you asked

Javis is a tool for talking to AI models and to the services you connect. When you use those features, the data they need goes to the service **you** chose, under that service's own privacy policy:

- **The AI brain you pick on the Models page** (Anthropic, OpenAI, Google, xAI, OpenRouter, Groq, DeepSeek, Ollama and others) receives the messages you send it, together with the context Javis attaches: the files, notes and tool results that the conversation needs.
- **Connections you add** (Telegram, Zalo, Slack, Discord, Google, Meta, a POS, any MCP server) exchange data with that service when you or a job you scheduled uses them.
- **Web search and web pages** the AI opens at your request are fetched from the sites concerned.
- **Voice** features send audio or text to the speech service you selected.
- **GitHub backup**, when you turn it on, pushes your brain to the private repository you name.

Nothing in this list happens until you configure it.

## Software the installer adds

The Windows and macOS installers download JAVIS OS from GitHub and install Git, Python and Node.js if they are missing. They also install four AI command-line tools (on Windows this is an option you can untick) from their vendors: Claude Code (Anthropic), Codex (OpenAI), Antigravity CLI (Google) and Grok Build (xAI). Those are separate products with their own terms and privacy policies. JAVIS OS does not control what they send to their vendors.

## People who talk to your bots

If you run Javis as a chatbot for your own customers (Telegram, Zalo, Messenger and so on), their messages are stored on **your** machine and you are responsible for them towards those people.

## Questions

Open an issue at <https://github.com/blogminhquy/javis-os/issues>. For a security problem, follow [SECURITY.md](SECURITY.md).
