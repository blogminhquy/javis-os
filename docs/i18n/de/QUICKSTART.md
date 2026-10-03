<!-- translated-from: QUICKSTART.en.md sha256:2f4928f341af -->
# Javis OS - Schnellstart

*[English](../../../QUICKSTART.en.md) · [Tiếng Việt](../../../QUICKSTART.md) · [简体中文](../zh/QUICKSTART.md) · [Español](../es/QUICKSTART.md) · [日本語](../ja/QUICKSTART.md) · [हिन्दी](../hi/QUICKSTART.md) · [Português](../pt-BR/QUICKSTART.md) · [한국어](../ko/QUICKSTART.md) · [Русский](../ru/QUICKSTART.md) · **Deutsch** · [Français](../fr/QUICKSTART.md) · [Bahasa Indonesia](../id/QUICKSTART.md)*

> Dies ist eine automatische Übersetzung der englischen Schnellstart-Anleitung.

Bring Javis OS in wenigen Minuten zum Laufen. Vollständige Anleitungen: [docs/en/](../../../docs/en/README.md).

## Option 1 - Hostinger VPS (Docker Manager, ein Klick)

1. hPanel → VPS → **Docker Manager** → **Compose** → **Compose from URL**.
2. Füge diese URL ein:
   ```
   https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.hostinger.yml
   ```
3. (Optional, für HTTPS + eine Domain) trage dies im Feld **Environment** ein:
   ```
   DOMAIN_NAME=javis.<vps-hostname>.hstgr.cloud
   ```
   (Den Hostnamen findest du unter hPanel → VPS, z. B. `javis.srv1782015.hstgr.cloud`.)
4. **Deploy**. Warte 1-3 Minuten. Öffne die App über den Button **Open** (oder unter `https://<DOMAIN_NAME>`).
5. Beim ersten Start fordert dich der Bildschirm auf, ein Admin-Konto anzulegen. Melde dich danach einmal im Terminal des Containers bei Claude Code an: `claude auth login --claudeai`.

Zum Aktualisieren: Klicke in Docker Manager auf **Redeploy** (Image `:latest`, `pull_policy: always`). Die Daten des Brains bleiben im Volume erhalten.

## Option 2 - Docker auf einem beliebigen Rechner oder VPS

```
docker compose -f docker-compose.yml up -d
```
Öffne http://localhost:7777. Für HTTPS über Caddy füge `-f docker-compose.https.yml` hinzu.

## Option 3 - Direkt ausführen (Windows, ohne Docker)

1. Installiere Python 3.12 + Node 22.
2. Führe im Projektordner einmal `setup.bat` aus: Es legt .venv an, installiert die Abhängigkeiten und installiert für dich die beiden CLI-Engines (Claude Code, Codex).
3. `start-javis.bat` startet Javis im Hintergrund (`stop-javis.bat` beendet es).
4. Öffne http://localhost:7777.

## Sobald es läuft

- **Eine Engine/ein Modell wählen**: die Seite **Models** (Claude Code, ChatGPT/Codex, Antigravity CLI, OpenRouter, OpenAI, Google Gemini, Anthropic API, Groq, Ollama).
- **Verbindungen einrichten** (Kassensystem, Werbung, Kalender, Zalo...), damit Berichte auf echten Zahlen beruhen: die Seite **Connections**, siehe [docs/09](../../../docs/en/09-connections-and-business-data.md).
- **Das Brain auf GitHub sichern**, damit du keine Daten verlierst: die Seite **Self-learning**, siehe [docs/18](../../../docs/en/18-github-backup.md).
- **Den Tokenverbrauch im Blick behalten**: die Seite **Usage**, siehe [docs/23](../../../docs/en/23-usage-and-cost.md).

## Vollständige Dokumentation

Siehe [docs/en/README.md](../../../docs/en/README.md): eine Anleitung pro Funktion (Chat/Sprache, Wissensgraph, Skills, Agents, Workflows, wiederkehrende Jobs, Kanban, Selbstlernen, Verbindungen, Telegram, Zalo, Plugins, Sicherheit, Sicherung...). Dieselben Anleitungen auf Vietnamesisch: [docs/README.md](../../../docs/README.md).

## Häufige Probleme

- **Der Update-Button in der App tut auf Hostinger nichts**: Das ist so gewollt; nutze auf Hostinger **Redeploy** in Docker Manager. Der Button in der App braucht Watchtower, und Hostinger blockiert meist den Docker-Socket.
- **ChatGPT/Codex meldet "model not supported"**: Wähle auf der Seite Models ein gültiges Codex-Modell (z. B. `gpt-5.5`). Verwende nicht `gpt-5-mini` oder `gpt-4o`: Das sind API-Modelle, die ein Codex-Konto nicht ausführen kann.
- Mehr: [docs/17 - Fehlerbehebung](../../../docs/en/17-troubleshooting.md).
