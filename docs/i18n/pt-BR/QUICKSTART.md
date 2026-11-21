<!-- translated-from: QUICKSTART.en.md sha256:338011fb77ad -->
# Javis OS - Início rápido

*[English](../../../QUICKSTART.en.md) · [Tiếng Việt](../../../QUICKSTART.md) · [简体中文](../zh/QUICKSTART.md) · [Español](../es/QUICKSTART.md) · [日本語](../ja/QUICKSTART.md) · [हिन्दी](../hi/QUICKSTART.md) · **Português** · [한국어](../ko/QUICKSTART.md) · [Русский](../ru/QUICKSTART.md) · [Deutsch](../de/QUICKSTART.md) · [Français](../fr/QUICKSTART.md) · [Bahasa Indonesia](../id/QUICKSTART.md)*

> Esta é uma tradução automática do guia de início rápido em inglês.

Coloque o Javis OS para rodar em poucos minutos. Guias completos: [docs/en/](../../../docs/en/README.md).

## Computador pessoal (Windows, macOS) - baixe o instalador

Instale o Javis como qualquer outro app: baixe um arquivo, abra e pronto, você ganha um ícone JAVIS OS para clicar todo dia. O instalador verifica o que falta no computador (Git, Python, Node, os cérebros de IA) e instala só isso.

- **Windows 10/11:** baixe [JavisOS-Setup.exe](https://github.com/blogminhquy/javis-os/releases/download/desktop/JavisOS-Setup.exe), dê dois cliques e aperte Next até o fim. O progresso da instalação aparece dentro da própria janela do Setup, passo a passo (alguns minutos), sem uma janela preta separada. No final aparece um ícone JAVIS OS na Área de Trabalho e no menu Iniciar.
- **macOS 11 ou mais novo:** abra o **Terminal** (Launchpad, digite Terminal), cole esta linha e aperte Enter. Instalando assim, o macOS não mostra nenhum aviso:
  ```
  curl -fsSL https://raw.githubusercontent.com/blogminhquy/javis-os/main/packaging/macos/get-javis.sh | bash
  ```
  O comando baixa o Javis, copia **JAVIS OS** para **Applications** e instala ali mesmo, na janela do Terminal (pode pedir para criar uma conta de administrador do Javis e a senha do Mac uma vez). Depois, abra o JAVIS OS pelo Launchpad.

  Prefere um arquivo? Baixe [JavisOS-macOS.dmg](https://github.com/blogminhquy/javis-os/releases/download/desktop/JavisOS-macOS.dmg), abra, arraste **JAVIS OS** para **Applications** e abra pelo Launchpad. Ele ainda não é assinado com um Apple Developer ID, então o macOS bloqueia a primeira abertura: como liberar está mais abaixo, na parte sobre downloads bloqueados.

Ao clicar no ícone, o Javis abre em uma janela própria (sem barra de endereço), inicia junto com o computador e o botão **Update** do app funciona normalmente. Seus dados ficam na pasta `JavisOS` dentro da sua pasta de usuário; desinstalar o app mantém essa pasta.

**Windows: instalar sem a tela de aviso (recomendado).** O instalador do Windows ainda não tem assinatura de código, então um download pelo navegador é bloqueado na primeira vez. Cole uma linha em vez disso e você recebe o mesmo instalador com o logo do Javis, sem bloqueio: aperte Iniciar, digite `PowerShell`, abra, cole esta linha e aperte Enter:
```
irm https://raw.githubusercontent.com/blogminhquy/javis-os/main/packaging/windows/get-javis.ps1 | iex
```

O que os instaladores mudam no seu computador, quem os assina e o que o Javis envia e para onde: [Code signing policy](../../../docs/code-signing-policy.md) · [Privacy policy](../../../PRIVACY.md) (em inglês).

Se você já baixou o arquivo pelo navegador e ele foi bloqueado:
- O Edge ou o Chrome diz "JavisOS-Setup.exe isn't commonly downloaded" e não salva o arquivo: na caixa de Downloads, passe o mouse sobre essa linha, clique nos três pontos, escolha **Keep**, depois **Show more** e **Keep anyway**.
- O Windows mostra "Windows protected your PC": clique em **More info** e depois em **Run anyway**.
- Seu antivírus apaga o arquivo, ou o Windows bloqueia sem o botão **Run anyway** (Smart App Control está ativado): instale sem o .exe. Instale o [Git](https://git-scm.com/download/win), abra o PowerShell, cole esta linha e aperte Enter. Ao terminar, o Javis abre em http://localhost:7777 e inicia junto com o computador:
  ```
  git clone https://github.com/blogminhquy/javis-os.git "$env:USERPROFILE\JavisOS"; cd "$env:USERPROFILE\JavisOS"; powershell -ExecutionPolicy Bypass -File install.ps1
  ```
- O macOS diz que não consegue abrir o app: vá em **System Settings → Privacy & Security**, role para baixo, clique em **Open Anyway** e abra o JAVIS OS de novo.

## Opção 1 - VPS da Hostinger (Docker Manager, em um clique)

> 🛒 **Ainda não tem VPS?** [Contrate uma VPS da Hostinger aqui](https://www.hostinger.com?REFERRALCODE=JAVISOS). Ela já vem com o Docker Manager, então o Javis instala em um clique. Quando estiver pronta, volte aos passos abaixo.

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

> 🛒 **Precisa de uma VPS?** Uma [VPS da Hostinger](https://www.hostinger.com?REFERRALCODE=JAVISOS) também roda esta opção.

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
