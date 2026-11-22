<!-- translated-from: QUICKSTART.en.md sha256:338011fb77ad -->
# Javis OS - Быстрый старт

*[English](../../../QUICKSTART.en.md) · [Tiếng Việt](../../../QUICKSTART.md) · [简体中文](../zh/QUICKSTART.md) · [Español](../es/QUICKSTART.md) · [日本語](../ja/QUICKSTART.md) · [हिन्दी](../hi/QUICKSTART.md) · [Português](../pt-BR/QUICKSTART.md) · [한국어](../ko/QUICKSTART.md) · **Русский** · [Deutsch](../de/QUICKSTART.md) · [Français](../fr/QUICKSTART.md) · [Bahasa Indonesia](../id/QUICKSTART.md)*

> Это автоматический перевод английского руководства по быстрому старту.

Запустите Javis OS за несколько минут. Полные руководства: [docs/en/](../../../docs/en/README.md).

## Личный компьютер (Windows, macOS) - скачайте установщик

Установите Javis как обычное приложение: скачайте один файл, откройте его, и у вас появится значок JAVIS OS для ежедневного запуска. Установщик проверяет, чего не хватает на компьютере (Git, Python, Node, ИИ-движки), и ставит только это.

- **Windows 10/11:** скачайте [JavisOS-Setup.exe](https://github.com/blogminhquy/javis-os/releases/download/desktop/JavisOS-Setup.exe), дважды щёлкните и нажимайте Next до конца. Ход установки показывается прямо в окне Setup, шаг за шагом (несколько минут), без отдельного чёрного окна. После этого на рабочем столе и в меню «Пуск» появится значок JAVIS OS.
- **macOS 11 и новее:** откройте **Терминал** (Launchpad, введите Terminal), вставьте эту строку и нажмите Enter. При такой установке macOS не показывает предупреждений:
  ```
  curl -fsSL https://raw.githubusercontent.com/blogminhquy/javis-os/main/packaging/macos/get-javis.sh | bash
  ```
  Команда скачивает Javis, копирует **JAVIS OS** в **Applications** и устанавливает его прямо в этом окне Терминала (она может один раз попросить создать учётную запись администратора Javis и ввести пароль Mac). После этого откройте JAVIS OS из Launchpad.

  Удобнее файл? Скачайте [JavisOS-macOS.dmg](https://github.com/blogminhquy/javis-os/releases/download/desktop/JavisOS-macOS.dmg), откройте, перетащите **JAVIS OS** в **Applications** и запустите из Launchpad. Файл пока не подписан Apple Developer ID, поэтому macOS заблокирует первый запуск: как его разрешить, написано ниже, в разделе о заблокированных загрузках.

По щелчку на значке Javis открывается в отдельном окне (без адресной строки), запускается вместе с компьютером, а кнопка **Update** в приложении работает как обычно. Данные хранятся в папке `JavisOS` в папке пользователя; удаление приложения эту папку не трогает.

**Windows: установка без экрана предупреждения (рекомендуется).** Установщик для Windows пока не подписан, поэтому загрузку через браузер в первый раз блокируют. Вместо этого вставьте одну строку, и вы получите тот же установщик с логотипом Javis, без блокировки: нажмите «Пуск», введите `PowerShell`, откройте его, вставьте эту строку и нажмите Enter:
```
irm https://raw.githubusercontent.com/blogminhquy/javis-os/main/packaging/windows/get-javis.ps1 | iex
```

Что установщики меняют на компьютере, кто их подписывает и что Javis отправляет и куда: [Code signing policy](../../../docs/code-signing-policy.md) · [Privacy policy](../../../PRIVACY.md) (на английском).

Если вы уже скачали файл браузером и его заблокировали:
- Edge или Chrome пишет "JavisOS-Setup.exe isn't commonly downloaded" и не сохраняет файл: в окне Downloads наведите курсор на эту строку, нажмите на три точки, выберите **Keep**, затем **Show more** и **Keep anyway**.
- Windows пишет "Windows protected your PC": нажмите **More info**, затем **Run anyway**.
- Антивирус удаляет файл, или Windows блокирует его без кнопки **Run anyway** (включён Smart App Control): установите без .exe. Установите [Git](https://git-scm.com/download/win), откройте PowerShell, вставьте эту строку и нажмите Enter. По окончании Javis откроется по адресу http://localhost:7777 и будет запускаться вместе с компьютером:
  ```
  git clone https://github.com/blogminhquy/javis-os.git "$env:USERPROFILE\JavisOS"; cd "$env:USERPROFILE\JavisOS"; powershell -ExecutionPolicy Bypass -File install.ps1
  ```
- macOS сообщает, что не может открыть приложение: откройте **System Settings → Privacy & Security**, прокрутите вниз, нажмите **Open Anyway** и снова откройте JAVIS OS.

## Вариант 1 - VPS на Hostinger (Docker Manager, в один клик)

> 🛒 **Ещё нет VPS?** [Возьмите VPS на Hostinger здесь](https://www.hostinger.com?REFERRALCODE=JAVISOS). Docker Manager там встроен, поэтому Javis ставится в один клик. Когда VPS будет готов, вернитесь к шагам ниже.

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

> 🛒 **Нужен VPS?** [VPS на Hostinger](https://www.hostinger.com?REFERRALCODE=JAVISOS) подходит и для этого варианта.

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
