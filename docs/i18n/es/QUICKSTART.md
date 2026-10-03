<!-- translated-from: QUICKSTART.en.md sha256:f0e9ed53ea49 -->
# Javis OS - Inicio rápido

*[English](../../../QUICKSTART.en.md) · [Tiếng Việt](../../../QUICKSTART.md) · [简体中文](../zh/QUICKSTART.md) · **Español** · [日本語](../ja/QUICKSTART.md) · [हिन्दी](../hi/QUICKSTART.md) · [Português](../pt-BR/QUICKSTART.md) · [한국어](../ko/QUICKSTART.md) · [Русский](../ru/QUICKSTART.md) · [Deutsch](../de/QUICKSTART.md) · [Français](../fr/QUICKSTART.md) · [Bahasa Indonesia](../id/QUICKSTART.md)*

> Esta es una traducción automática de la guía de inicio rápido en inglés.

Pon Javis OS en marcha en pocos minutos. Guías completas: [docs/en/](../../../docs/en/README.md).

## Opción 1 - VPS de Hostinger (Docker Manager, en un clic)

1. hPanel → VPS → **Docker Manager** → **Compose** → **Compose from URL**.
2. Pega esta URL:
   ```
   https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.hostinger.yml
   ```
3. (Opcional, para HTTPS + un dominio) define esto en el cuadro **Environment**:
   ```
   DOMAIN_NAME=javis.<vps-hostname>.hstgr.cloud
   ```
   (El hostname está en hPanel → VPS, p. ej. `javis.srv1782015.hstgr.cloud`.)
4. **Deploy**. Espera de 1-3 minutos. Abre la app con el botón **Open** (o en `https://<DOMAIN_NAME>`).
5. En el primer arranque, la pantalla te pide crear una cuenta de administrador. Después, inicia sesión en Claude Code una vez desde el terminal del contenedor: `claude auth login --claudeai`.

Para actualizar: pulsa **Redeploy** en Docker Manager (imagen `:latest`, `pull_policy: always`). Los datos del Brain se conservan en el volumen.

## Opción 2 - Docker en cualquier máquina o VPS

```
docker compose -f docker-compose.yml up -d
```
Abre http://localhost:7777. Para HTTPS mediante Caddy, añade `-f docker-compose.https.yml`.

## Opción 3 - Ejecutarlo directamente (Windows, sin Docker)

1. Instala Python 3.12 + Node 22.
2. En la carpeta del proyecto, ejecuta `setup.bat` una vez: crea .venv, instala las dependencias e instala por ti los dos motores CLI (Claude Code, Codex).
3. `start-javis.bat` para ejecutarlo en segundo plano (`stop-javis.bat` para detenerlo).
4. Abre http://localhost:7777.

## Una vez en marcha

- **Elige un motor/modelo**: la página **Models** (Claude Code, ChatGPT/Codex, Antigravity CLI, OpenRouter, OpenAI, Google Gemini, Anthropic API, Groq, Ollama).
- **Configura las conexiones** (TPV, anuncios, calendario, Zalo...) para que los informes usen cifras reales: la página **Connections**; consulta [docs/09](../../../docs/en/09-connections-and-business-data.md).
- **Haz una copia de seguridad del Brain en GitHub** para no perder datos: la página **Self-learning**; consulta [docs/18](../../../docs/en/18-github-backup.md).
- **Vigila el gasto de tokens**: la página **Usage**; consulta [docs/23](../../../docs/en/23-usage-and-cost.md).

## Documentación completa

Consulta [docs/en/README.md](../../../docs/en/README.md): una guía por función (chat/voz, grafo de conocimiento, skills, agents, workflows, trabajos periódicos, Kanban, autoaprendizaje, conexiones, Telegram, Zalo, plugins, seguridad, copias de seguridad...). Las mismas guías en vietnamita: [docs/README.md](../../../docs/README.md).

## Problemas habituales

- **El botón de actualización de la app no hace nada en Hostinger**: es así por diseño; en Hostinger usa **Redeploy** en Docker Manager. El botón de la app necesita Watchtower, y Hostinger suele bloquear el socket de Docker.
- **ChatGPT/Codex dice "model not supported"**: elige un modelo de Codex válido en la página Models (p. ej. `gpt-5.5`). No uses `gpt-5-mini` ni `gpt-4o`: son modelos de API y una cuenta de Codex no puede ejecutarlos.
- Más: [docs/17 - Solución de problemas](../../../docs/en/17-troubleshooting.md).
