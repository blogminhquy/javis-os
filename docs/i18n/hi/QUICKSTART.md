<!-- translated-from: QUICKSTART.en.md sha256:2f4928f341af -->
# Javis OS - क्विक स्टार्ट

*[English](../../../QUICKSTART.en.md) · [Tiếng Việt](../../../QUICKSTART.md) · [简体中文](../zh/QUICKSTART.md) · [Español](../es/QUICKSTART.md) · [日本語](../ja/QUICKSTART.md) · **हिन्दी** · [Português](../pt-BR/QUICKSTART.md) · [한국어](../ko/QUICKSTART.md) · [Русский](../ru/QUICKSTART.md) · [Deutsch](../de/QUICKSTART.md) · [Français](../fr/QUICKSTART.md) · [Bahasa Indonesia](../id/QUICKSTART.md)*

> यह अंग्रेज़ी quick start का स्वचालित (automatic) अनुवाद है।

कुछ ही मिनटों में Javis OS चालू कीजिए। पूरी guides: [docs/en/](../../../docs/en/README.md)।

## विकल्प 1 - Hostinger VPS (Docker Manager, एक click में)

1. hPanel → VPS → **Docker Manager** → **Compose** → **Compose from URL**।
2. यह URL paste कीजिए:
   ```
   https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.hostinger.yml
   ```
3. (वैकल्पिक, HTTPS + domain के लिए) **Environment** box में यह सेट कीजिए:
   ```
   DOMAIN_NAME=javis.<vps-hostname>.hstgr.cloud
   ```
   (Hostname hPanel → VPS में मिलेगा, जैसे `javis.srv1782015.hstgr.cloud`।)
4. **Deploy** कीजिए। 1-3 मिनट इंतज़ार कीजिए। App को **Open** button से खोलिए (या `https://<DOMAIN_NAME>` पर)।
5. पहली बार चलाने पर screen आपसे एक admin account बनाने को कहती है। उसके बाद container के terminal में एक बार Claude Code में sign in कीजिए: `claude auth login --claudeai`।

Update करने के लिए: Docker Manager में **Redeploy** दबाइए (image `:latest`, `pull_policy: always`)। Brain का डेटा volume में सुरक्षित रहता है।

## विकल्प 2 - किसी भी मशीन या VPS पर Docker

```
docker compose -f docker-compose.yml up -d
```
http://localhost:7777 खोलिए। Caddy के ज़रिए HTTPS के लिए `-f docker-compose.https.yml` जोड़िए।

## विकल्प 3 - सीधे चलाइए (Windows, बिना Docker)

1. Python 3.12 + Node 22 इंस्टॉल कीजिए।
2. Project folder में एक बार `setup.bat` चलाइए: यह .venv बनाता है, dependencies इंस्टॉल करता है, और आपके लिए दोनों CLI engines (Claude Code, Codex) भी इंस्टॉल कर देता है।
3. Background में चलाने के लिए `start-javis.bat` (रोकने के लिए `stop-javis.bat`)।
4. http://localhost:7777 खोलिए।

## चालू होने के बाद

- **एक engine/model चुनिए**: **Models** page (Claude Code, ChatGPT/Codex, Antigravity CLI, OpenRouter, OpenAI, Google Gemini, Anthropic API, Groq, Ollama)।
- **Connections जोड़िए** (POS, ads, calendar, Zalo...) ताकि reports असली आंकड़ों पर चलें: **Connections** page, देखें [docs/09](../../../docs/en/09-connections-and-business-data.md)।
- **Brain का GitHub पर backup लीजिए** ताकि डेटा न खोए: **Self-learning** page, देखें [docs/18](../../../docs/en/18-github-backup.md)।
- **Token खर्च पर नज़र रखिए**: **Usage** page, देखें [docs/23](../../../docs/en/23-usage-and-cost.md)।

## पूरा documentation

देखें [docs/en/README.md](../../../docs/en/README.md): हर फ़ीचर के लिए एक guide (chat/आवाज़, knowledge graph, skills, agents, workflows, recurring jobs, Kanban, self-learning, connections, Telegram, Zalo, plugins, security, backup...)। यही guides वियतनामी में: [docs/README.md](../../../docs/README.md)।

## आम समस्याएँ

- **Hostinger पर app का update button कुछ नहीं करता**: ऐसा जानबूझकर है; Hostinger पर Docker Manager में **Redeploy** इस्तेमाल कीजिए। App वाले button को Watchtower चाहिए, और Hostinger आमतौर पर Docker socket को block कर देता है।
- **ChatGPT/Codex कहता है "model not supported"**: Models page पर कोई मान्य Codex model चुनिए (जैसे `gpt-5.5`)। `gpt-5-mini` या `gpt-4o` इस्तेमाल न कीजिए: ये API models हैं और Codex account इन्हें नहीं चला सकता।
- और जानकारी: [docs/17 - Troubleshooting](../../../docs/en/17-troubleshooting.md)।
