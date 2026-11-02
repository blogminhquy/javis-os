<!-- translated-from: QUICKSTART.en.md sha256:2f4928f341af -->
# Javis OS - 快速开始

*[English](../../../QUICKSTART.en.md) · [Tiếng Việt](../../../QUICKSTART.md) · **简体中文** · [Español](../es/QUICKSTART.md) · [日本語](../ja/QUICKSTART.md) · [हिन्दी](../hi/QUICKSTART.md) · [Português](../pt-BR/QUICKSTART.md) · [한국어](../ko/QUICKSTART.md) · [Русский](../ru/QUICKSTART.md) · [Deutsch](../de/QUICKSTART.md) · [Français](../fr/QUICKSTART.md) · [Bahasa Indonesia](../id/QUICKSTART.md)*

> 本文是英文快速开始指南的自动翻译版本。

几分钟内让 Javis OS 跑起来。完整指南：[docs/en/](../../../docs/en/README.md)。

## 个人电脑（Windows、macOS）- 下载安装程序

像安装普通应用一样安装 Javis：下载一个文件，打开它，之后每天点 JAVIS OS 图标即可。安装程序会检查电脑缺少什么（Git、Python、Node、AI 大脑），只安装缺少的部分。

- **Windows 10/11：** 下载 [JavisOS-Setup.exe](https://github.com/blogminhquy/javis-os/releases/download/desktop/JavisOS-Setup.exe)，双击并一路点 Next。黑色窗口会显示安装进度（几分钟）。完成后桌面和开始菜单会出现 JAVIS OS 图标。
- **macOS 11 及以上：** 下载 [JavisOS-macOS.dmg](https://github.com/blogminhquy/javis-os/releases/download/desktop/JavisOS-macOS.dmg)，打开后把 **JAVIS OS** 拖进 **Applications**，再从启动台打开。第一次会打开终端进行安装（可能会让你设置 Javis 管理员账号，并输入一次 Mac 密码）。

点击图标后 Javis 会以独立窗口打开（没有地址栏），Javis 随电脑启动，应用内的 **Update** 按钮照常可用。数据保存在用户文件夹下的 `JavisOS` 文件夹中；卸载应用不会删除该文件夹。

两个安装程序暂未进行代码签名，所以电脑第一次会询问：
- Windows 显示 “Windows protected your PC”：点 **More info**，再点 **Run anyway**。
- macOS 提示无法打开：进入 **System Settings → Privacy & Security**，向下滚动点 **Open Anyway**，然后重新打开 JAVIS OS。

## 方式一 - Hostinger VPS（Docker Manager，一键部署）

> 🛒 **还没有 VPS？** [在这里购买 Hostinger VPS](https://www.hostinger.com?REFERRALCODE=UTRBLOGMIDSN)。它自带 Docker Manager，一键即可安装 Javis。开通后回到下面的步骤。

1. hPanel → VPS → **Docker Manager** → **Compose** → **Compose from URL**。
2. 粘贴这个 URL：
   ```
   https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.hostinger.yml
   ```
3. （可选，用于 HTTPS + 域名）在 **Environment** 框中设置：
   ```
   DOMAIN_NAME=javis.<vps-hostname>.hstgr.cloud
   ```
   （主机名可在 hPanel → VPS 中找到，例如 `javis.srv1782015.hstgr.cloud`。）
4. 点击 **Deploy**。等待 1-3 分钟。用 **Open** 按钮打开应用（或访问 `https://<DOMAIN_NAME>`）。
5. 首次运行时，界面会要求你创建一个管理员账号。之后，在容器终端里登录一次 Claude Code：`claude auth login --claudeai`。

更新方法：在 Docker Manager 中点击 **Redeploy**（镜像 `:latest`，`pull_policy: always`）。Brain 数据保存在数据卷中，不会丢失。

## 方式二 - 在任意机器或 VPS 上使用 Docker

> 🛒 **需要 VPS？** [Hostinger VPS](https://www.hostinger.com?REFERRALCODE=UTRBLOGMIDSN) 同样适用这种方式。

```
docker compose -f docker-compose.yml up -d
```
打开 http://localhost:7777。如需通过 Caddy 提供 HTTPS，再加上 `-f docker-compose.https.yml`。

## 方式三 - 直接运行（Windows，不使用 Docker）

1. 安装 Python 3.12 + Node 22。
2. 在项目文件夹中运行一次 `setup.bat`，它会创建 .venv、安装依赖，并为你安装两个 CLI 引擎（Claude Code、Codex）。
3. 运行 `start-javis.bat` 在后台启动（用 `stop-javis.bat` 停止）。
4. 打开 http://localhost:7777。

## 运行起来之后

- **选择引擎/模型**：在 **Models（模型）** 页面（Claude Code、ChatGPT/Codex、Antigravity CLI、OpenRouter、OpenAI、Google Gemini、Anthropic API、Groq、Ollama）。
- **接入连接**（POS、广告、日历、Zalo...），让报告基于真实数字：在 **Connections（连接）** 页面，参见 [docs/09](../../../docs/en/09-connections-and-business-data.md)。
- **把 Brain 备份到 GitHub**，避免丢失数据：在 **Self-learning（自我学习）** 页面，参见 [docs/18](../../../docs/en/18-github-backup.md)。
- **关注 token 消耗**：在 **Usage（用量）** 页面，参见 [docs/23](../../../docs/en/23-usage-and-cost.md)。

## 完整文档

请参阅 [docs/en/README.md](../../../docs/en/README.md)：每个功能都有一篇指南（聊天/语音、知识图谱、Skill、Agent、Workflow、周期任务、Kanban、自我学习、连接、Telegram、Zalo、Plugin、安全、备份...）。同一套指南的越南语版：[docs/README.md](../../../docs/README.md)。

## 常见问题

- **在 Hostinger 上，应用内的更新按钮没有反应**：这是设计使然。在 Hostinger 上请使用 Docker Manager 中的 **Redeploy**。应用内按钮依赖 Watchtower，而 Hostinger 通常会屏蔽 Docker socket。
- **ChatGPT/Codex 提示 "model not supported"**：在 Models 页面选择一个有效的 Codex 模型（例如 `gpt-5.5`）。不要使用 `gpt-5-mini` 或 `gpt-4o`，它们是 API 模型，Codex 账号无法运行。
- 更多内容：[docs/17 - 故障排查](../../../docs/en/17-troubleshooting.md)。
