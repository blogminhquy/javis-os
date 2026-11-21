<!-- translated-from: QUICKSTART.en.md sha256:338011fb77ad -->
# Javis OS - Schnellstart

*[English](../../../QUICKSTART.en.md) · [Tiếng Việt](../../../QUICKSTART.md) · [简体中文](../zh/QUICKSTART.md) · [Español](../es/QUICKSTART.md) · [日本語](../ja/QUICKSTART.md) · [हिन्दी](../hi/QUICKSTART.md) · [Português](../pt-BR/QUICKSTART.md) · [한국어](../ko/QUICKSTART.md) · [Русский](../ru/QUICKSTART.md) · **Deutsch** · [Français](../fr/QUICKSTART.md) · [Bahasa Indonesia](../id/QUICKSTART.md)*

> Dies ist eine automatische Übersetzung der englischen Schnellstart-Anleitung.

Bring Javis OS in wenigen Minuten zum Laufen. Vollständige Anleitungen: [docs/en/](../../../docs/en/README.md).

## Eigener Computer (Windows, macOS) - Installer herunterladen

Installiere Javis wie jede andere App: eine Datei herunterladen, öffnen, und du hast ein JAVIS OS-Symbol für jeden Tag. Der Installer prüft, was dem Computer fehlt (Git, Python, Node, die KI-Gehirne), und installiert nur das.

- **Windows 10/11:** Lade [JavisOS-Setup.exe](https://github.com/blogminhquy/javis-os/releases/download/desktop/JavisOS-Setup.exe) herunter, doppelklicke und drücke bis zum Ende auf Next. Der Fortschritt erscheint Schritt für Schritt direkt im Setup-Fenster (einige Minuten), ohne separates schwarzes Fenster. Danach liegt ein JAVIS OS-Symbol auf dem Desktop und im Startmenü.
- **macOS 11 oder neuer:** Öffne das **Terminal** (Launchpad, Terminal eintippen), füge diese Zeile ein und drücke Enter. So installiert zeigt macOS keine Warnung:
  ```
  curl -fsSL https://raw.githubusercontent.com/blogminhquy/javis-os/main/packaging/macos/get-javis.sh | bash
  ```
  Der Befehl lädt Javis herunter, kopiert **JAVIS OS** nach **Applications** und installiert es direkt in diesem Terminal-Fenster (er fragt eventuell einmal nach einem Javis-Admin-Konto und nach deinem Mac-Passwort). Danach öffnest du JAVIS OS über das Launchpad.

  Lieber eine Datei? Lade [JavisOS-macOS.dmg](https://github.com/blogminhquy/javis-os/releases/download/desktop/JavisOS-macOS.dmg) herunter, öffne es, ziehe **JAVIS OS** in **Applications** und öffne es über das Launchpad. Die Datei ist noch nicht mit einer Apple Developer ID signiert, daher blockiert macOS das erste Öffnen: Wie du es erlaubst, steht unten im Abschnitt zu blockierten Downloads.

Ein Klick auf das Symbol öffnet Javis in einem eigenen Fenster (ohne Adressleiste), Javis startet mit dem Computer, und der **Update**-Knopf in der App funktioniert wie gewohnt. Deine Daten liegen im Ordner `JavisOS` in deinem Benutzerordner; beim Deinstallieren bleibt dieser Ordner erhalten.

**Windows: Installation ohne Warnbildschirm (empfohlen).** Der Windows-Installer ist noch nicht signiert, daher wird ein Download über den Browser beim ersten Mal blockiert. Füge stattdessen eine Zeile ein und du bekommst denselben Installer mit dem Javis-Logo, ohne Blockade: Drücke Start, tippe `PowerShell`, öffne es, füge diese Zeile ein und drücke Enter:
```
irm https://raw.githubusercontent.com/blogminhquy/javis-os/main/packaging/windows/get-javis.ps1 | iex
```

Was die Installer auf deinem Computer ändern, wer sie signiert und was Javis wohin sendet: [Code signing policy](../../../docs/code-signing-policy.md) · [Privacy policy](../../../PRIVACY.md) (auf Englisch).

Wenn du die Datei schon mit dem Browser heruntergeladen hast und sie blockiert wurde:
- Edge oder Chrome meldet "JavisOS-Setup.exe isn't commonly downloaded" und speichert die Datei nicht: Fahre im Downloads-Feld mit der Maus über diese Zeile, klicke auf die drei Punkte, wähle **Keep**, dann **Show more** und **Keep anyway**.
- Windows zeigt "Windows protected your PC": klicke auf **More info** und dann auf **Run anyway**.
- Dein Virenscanner löscht die Datei, oder Windows blockiert sie ohne den Knopf **Run anyway** (Smart App Control ist aktiv): Installiere ohne die .exe. Installiere [Git](https://git-scm.com/download/win), öffne PowerShell, füge diese Zeile ein und drücke Enter. Am Ende öffnet sich Javis unter http://localhost:7777 und startet mit dem Computer:
  ```
  git clone https://github.com/blogminhquy/javis-os.git "$env:USERPROFILE\JavisOS"; cd "$env:USERPROFILE\JavisOS"; powershell -ExecutionPolicy Bypass -File install.ps1
  ```
- macOS meldet, dass die App nicht geöffnet werden kann: Gehe zu **System Settings → Privacy & Security**, scrolle nach unten, klicke auf **Open Anyway** und öffne JAVIS OS erneut.

## Option 1 - Hostinger VPS (Docker Manager, ein Klick)

> 🛒 **Noch keinen VPS?** [Hol dir hier einen Hostinger VPS](https://www.hostinger.com?REFERRALCODE=JAVISOS). Docker Manager ist eingebaut, Javis installiert sich also mit einem Klick. Sobald er bereit ist, mach mit den Schritten unten weiter.

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

> 🛒 **Brauchst du einen VPS?** Ein [Hostinger VPS](https://www.hostinger.com?REFERRALCODE=JAVISOS) eignet sich auch für diese Option.

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
