# 📚 Javis OS documentation

*[Tiếng Việt](../README.md) · **English***

Detailed guides for every feature of Javis OS. Each page is a standalone how-to: where to open it, what to click, how to use it.

> Just starting? Read [Installation in the README](../../README.en.md) first, then go to [01 - Getting started and first setup](01-getting-started.md).

The dashboard's navigation rail groups **19 pages** into **7 groups**: Assistant · Brain · Code · Capabilities · Work · Connections · System. The table of contents below follows the same logic.

## Table of contents

### Getting started
- [01 - Getting started and first setup](01-getting-started.md) - creating the admin, signing the brain in, choosing an engine and model, the Settings page.

### Everyday use (the Assistant and Brain groups)
- [02 - Chat and voice](02-chat-and-voice.md) - chatting, hands-free speech, slash commands, quick-reply buttons, sending files, generating images.
- [03 - Knowledge graph](03-knowledge-graph.md) - wikilinks, category colours, the timelapse and the graph switches.
- [04 - Sessions](04-sessions.md) - saving, reopening, renaming, deleting, full-text search, compacting a long session.
- [05 - File manager](05-file-manager.md) - browsing the brain, finding files by name or content, editing .md/.txt directly, uploading and downloading.

### Code (the Code group)
- [27 - The Code group: Terminal](27-code-terminal.md) - a real command line on the machine running Javis, opened right in the dashboard, with no SSH.

### Extending capabilities (the Capabilities group)
- [06 - Skills](06-skills.md) - grouping, searching, enabling and disabling, adding, editing and deleting, importing and exporting skills.
- [07 - Agents and Workflows](07-agents-and-workflows.md) - creating specialist assistants plus automated multi-step chains.
- [20 - Plugins](20-plugins.md) - adding native tools and hooks for every engine with one Python folder.
- [25 - Chatbot (a dedicated bot)](25-chatbots.md) - putting an Agent in front of customers through a dedicated Telegram or Zalo bot, with its own brain and a handover to a human.

### Background work (the Work and Brain groups)
- [08 - Recurring jobs and reminders](08-recurring-jobs.md) - several background loops plus reminders on a clock or a cron schedule.
- [21 - Work (Kanban)](21-kanban-work.md) - handing over a goal in words, with the AI specifying and running the background task.
- [22 - Self-learning](22-self-learning.md) - Javis extracting memories, distilling Wiki pages and skills after each conversation, undoably.

### Connections and channels (the Connections group)
- [09 - Connections and business data](09-connections-and-business-data.md) - the multi-account store of external services, permissions, reporting real figures.
- [10 - Models and engines](10-models-and-engines.md) - switching the brain between Claude Code, ChatGPT/Codex, Antigravity CLI, OpenRouter, OpenAI, Gemini, Anthropic, Groq and Ollama without losing capability; thinking levels, the background work model.
- [11 - The Telegram channel](11-telegram.md) - asking Javis from a phone, sending and receiving files.
- [26 - The Zalo Bot channel](26-zalo-bot-channel.md) - asking Javis on Zalo through the official API, paired with one click.
- [12 - Zalo Agent MCP](12-zalo-agent-mcp.md) - signing in by QR, reading and searching history, sending messages through the standard MCP.
- [24 - The Javis CLI (terminal)](24-cli.md) - typing `javis "..."` from a terminal, API tokens, composing in scripts.

### The brain and data
- [13 - Second Brain: memory, Wiki, INGEST](13-second-brain.md) - multiple brains, living memory, digesting knowledge.
- [18 - Backing the brain up to GitHub](18-github-backup.md) - two-way sync to a private repo, recovering after losing a machine or VPS.
- [19 - Tasks and Dataview in notes](19-tasks-and-dataview.md) - Obsidian-style self-saving checkboxes, ```dataview blocks that really run.

### Accounts, branding, configuration (the System group)
- [14 - Security and accounts](14-security-and-accounts.md) - forced login, passwords, rate limiting, secret-key encryption.
- [15 - Branding and custom domains](15-branding-and-domains.md) - changing the logo and avatar, pointing a domain and enabling HTTPS.
- [16 - .env configuration](16-env-configuration.md) - a reference for every environment variable.
- [23 - Usage: tokens and cost](23-usage-and-cost.md) - Javis measuring input and output tokens by day, by provider and by source.

### When something goes wrong
- [17 - Troubleshooting and FAQ](17-troubleshooting.md) - common errors and how to handle them.

---

## Also in English at the repository root

- [README.en.md](../../README.en.md) - what Javis is and how to install it.
- [QUICKSTART.en.md](../../QUICKSTART.en.md) - the first 10 minutes.
- [DEPLOY.en.md](../../DEPLOY.en.md) - installing on a server or VPS.
- [CONTRIBUTING.en.md](../../CONTRIBUTING.en.md) - contributing to the project.

Screenshots, button names and menu paths match the interface language you selected on the Settings page, so an English page lines up with an English interface everywhere.

## Adding a language

Translating documentation is step 6 of the language playbook, and it is deliberately last: Javis answers, routes and formats correctly in a new language long before its documentation is translated. The four required steps are in [docs/dev/them-mot-ngon-ngu.md](../dev/them-mot-ngon-ngu.md) (Vietnamese).

---

> Documentation conventions: practical and concise. Never use the em dash character (U+2014), always the hyphen "-" instead. See [CLAUDE.md](../../CLAUDE.md) for the system conventions aimed at AI agents.
