<!-- translated-from: QUICKSTART.en.md sha256:f0e9ed53ea49 -->
# Javis OS - Início rápido

*[English](../../../QUICKSTART.en.md) · [Tiếng Việt](../../../QUICKSTART.md) · [简体中文](../zh/QUICKSTART.md) · [Español](../es/QUICKSTART.md) · [日本語](../ja/QUICKSTART.md) · [हिन्दी](../hi/QUICKSTART.md) · **Português** · [한국어](../ko/QUICKSTART.md) · [Русский](../ru/QUICKSTART.md) · [Deutsch](../de/QUICKSTART.md) · [Français](../fr/QUICKSTART.md) · [Bahasa Indonesia](../id/QUICKSTART.md)*

> Esta é uma tradução automática do guia de início rápido em inglês.

Coloque o Javis OS para rodar em poucos minutos. Guias completos: [docs/en/](../../../docs/en/README.md).

## Opção 1 - VPS da Hostinger (Docker Manager, em um clique)

1. hPanel → VPS → **Docker Manager** → **Compose** → **Compose from URL**.
2. Cole esta URL:
   ```
   https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.hostinger.yml
   ```
3. (Opcional, para HTTPS + um domínio) defina isto na caixa **Environment**:
   ```
   DOMAIN_NAME=javis.<vps-hostname>.hstgr.cloud
   ```
   (O hostname fica em hPanel → VPS, ex.: `javis.srv1782015.hstgr.cloud`.)
4. **Deploy**. Espere 1-3 minutos. Abra o app pelo botão **Open** (ou em `https://<DOMAIN_NAME>`).
5. Na primeira execução, a tela pede para você criar uma conta de admin. Depois disso, faça login no Claude Code uma vez pelo terminal do container: `claude auth login --claudeai`.

Para atualizar: clique em **Redeploy** no Docker Manager (imagem `:latest`, `pull_policy: always`). Os dados do Brain ficam no volume.

## Opção 2 - Docker em qualquer máquina ou VPS

```
docker compose -f docker-compose.yml up -d
```
Abra http://localhost:7777. Para ter HTTPS via Caddy, adicione `-f docker-compose.https.yml`.

## Opção 3 - Rodar direto (Windows, sem Docker)

1. Instale o Python 3.12 + Node 22.
2. Na pasta do projeto, rode `setup.bat` uma vez: ele cria o .venv, instala as dependências e instala para você os dois motores CLI (Claude Code, Codex).
3. `start-javis.bat` para rodar em segundo plano (`stop-javis.bat` para parar).
4. Abra http://localhost:7777.

## Depois que estiver rodando

- **Escolha um motor/modelo**: a página **Models** (Modelos) (Claude Code, ChatGPT/Codex, Antigravity CLI, OpenRouter, OpenAI, Google Gemini, Anthropic API, Groq, Ollama).
- **Configure as conexões** (PDV, anúncios, agenda, Zalo...) para que os relatórios usem números reais: a página **Connections** (Conexões), veja [docs/09](../../../docs/en/09-connections-and-business-data.md).
- **Faça backup do Brain no GitHub** para não perder dados: a página **Self-learning** (Autoaprendizado), veja [docs/18](../../../docs/en/18-github-backup.md).
- **Acompanhe o gasto de tokens**: a página **Usage** (Uso), veja [docs/23](../../../docs/en/23-usage-and-cost.md).

## Documentação completa

Veja [docs/en/README.md](../../../docs/en/README.md): um guia por recurso (chat/voz, grafo de conhecimento, skills, agents, workflows, jobs recorrentes, Kanban, autoaprendizado, conexões, Telegram, Zalo, plugins, segurança, backup...). Os mesmos guias em vietnamita: [docs/README.md](../../../docs/README.md).

## Problemas comuns

- **O botão de atualizar dentro do app não faz nada na Hostinger**: isso é proposital. Na Hostinger, use **Redeploy** no Docker Manager. O botão do app precisa do Watchtower, e a Hostinger normalmente bloqueia o socket do Docker.
- **O ChatGPT/Codex diz "model not supported"**: escolha um modelo válido do Codex na página Models (ex.: `gpt-5.5`). Não use `gpt-5-mini` nem `gpt-4o`: esses são modelos de API e uma conta do Codex não consegue rodá-los.
- Mais: [docs/17 - Solução de problemas](../../../docs/en/17-troubleshooting.md).
