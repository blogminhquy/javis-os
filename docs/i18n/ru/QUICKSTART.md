<!-- translated-from: QUICKSTART.en.md sha256:f0e9ed53ea49 -->
# Javis OS - Быстрый старт

*[English](../../../QUICKSTART.en.md) · [Tiếng Việt](../../../QUICKSTART.md) · [简体中文](../zh/QUICKSTART.md) · [Español](../es/QUICKSTART.md) · [日本語](../ja/QUICKSTART.md) · [हिन्दी](../hi/QUICKSTART.md) · [Português](../pt-BR/QUICKSTART.md) · [한국어](../ko/QUICKSTART.md) · **Русский** · [Deutsch](../de/QUICKSTART.md) · [Français](../fr/QUICKSTART.md) · [Bahasa Indonesia](../id/QUICKSTART.md)*

> Это автоматический перевод английского руководства по быстрому старту.

Запустите Javis OS за несколько минут. Полные руководства: [docs/en/](../../../docs/en/README.md).

## Вариант 1 - VPS на Hostinger (Docker Manager, в один клик)

1. hPanel → VPS → **Docker Manager** → **Compose** → **Compose from URL**.
2. Вставьте этот URL:
   ```
   https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.hostinger.yml
   ```
3. (Необязательно, для HTTPS + домена) задайте в поле **Environment**:
   ```
   DOMAIN_NAME=javis.<vps-hostname>.hstgr.cloud
   ```
   (Hostname смотрите в hPanel → VPS, например `javis.srv1782015.hstgr.cloud`.)
4. **Deploy**. Подождите 1-3 минуты. Откройте приложение кнопкой **Open** (или по адресу `https://<DOMAIN_NAME>`).
5. При первом запуске экран попросит создать аккаунт администратора. После этого один раз войдите в Claude Code в терминале контейнера: `claude auth login --claudeai`.

Обновление: нажмите **Redeploy** в Docker Manager (образ `:latest`, `pull_policy: always`). Данные Brain остаются в томе.

## Вариант 2 - Docker на любой машине или VPS

```
docker compose -f docker-compose.yml up -d
```
Откройте http://localhost:7777. Для HTTPS через Caddy добавьте `-f docker-compose.https.yml`.

## Вариант 3 - Прямой запуск (Windows, без Docker)

1. Установите Python 3.12 + Node 22.
2. В папке проекта один раз запустите `setup.bat`: он создаст .venv, установит зависимости и сам поставит два CLI-движка (Claude Code, Codex).
3. `start-javis.bat` для запуска в фоне (`stop-javis.bat` для остановки).
4. Откройте http://localhost:7777.

## Когда всё запущено

- **Выберите движок/модель**: страница **Models** (Claude Code, ChatGPT/Codex, Antigravity CLI, OpenRouter, OpenAI, Google Gemini, Anthropic API, Groq, Ollama).
- **Настройте подключения** (POS, реклама, календарь, Zalo...), чтобы отчёты строились на реальных цифрах: страница **Connections**, см. [docs/09](../../../docs/en/09-connections-and-business-data.md).
- **Сделайте резервную копию Brain на GitHub**, чтобы не потерять данные: страница **Self-learning**, см. [docs/18](../../../docs/en/18-github-backup.md).
- **Следите за расходом токенов**: страница **Usage**, см. [docs/23](../../../docs/en/23-usage-and-cost.md).

## Полная документация

См. [docs/en/README.md](../../../docs/en/README.md): руководство по каждой функции (чат/голос, граф знаний, skills, агенты, workflows, повторяющиеся задания, Kanban, самообучение, подключения, Telegram, Zalo, plugins, безопасность, резервное копирование...). Те же руководства на вьетнамском: [docs/README.md](../../../docs/README.md).

## Частые проблемы

- **Кнопка обновления в приложении ничего не делает на Hostinger**: так задумано, на Hostinger используйте **Redeploy** в Docker Manager. Кнопке в приложении нужен Watchtower, а Hostinger обычно блокирует Docker-сокет.
- **ChatGPT/Codex пишет «model not supported»**: выберите подходящую модель Codex на странице Models (например, `gpt-5.5`). Не используйте `gpt-5-mini` или `gpt-4o`: это API-модели, и аккаунт Codex не может их запускать.
- Ещё: [docs/17 - Решение проблем](../../../docs/en/17-troubleshooting.md).
