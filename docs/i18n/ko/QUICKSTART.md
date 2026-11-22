<!-- translated-from: QUICKSTART.en.md sha256:338011fb77ad -->
# Javis OS - 빠른 시작

*[English](../../../QUICKSTART.en.md) · [Tiếng Việt](../../../QUICKSTART.md) · [简体中文](../zh/QUICKSTART.md) · [Español](../es/QUICKSTART.md) · [日本語](../ja/QUICKSTART.md) · [हिन्दी](../hi/QUICKSTART.md) · [Português](../pt-BR/QUICKSTART.md) · **한국어** · [Русский](../ru/QUICKSTART.md) · [Deutsch](../de/QUICKSTART.md) · [Français](../fr/QUICKSTART.md) · [Bahasa Indonesia](../id/QUICKSTART.md)*

> 이 문서는 영어 빠른 시작 안내를 자동 번역한 것입니다.

몇 분이면 Javis OS를 실행할 수 있습니다. 전체 안내서: [docs/en/](../../../docs/en/README.md).

## 개인 컴퓨터 (Windows, macOS) - 설치 프로그램 다운로드

Javis를 일반 앱처럼 설치하세요. 파일 하나를 내려받아 열면 매일 클릭할 JAVIS OS 아이콘이 생깁니다. 설치 프로그램은 컴퓨터에 없는 것(Git, Python, Node, AI 브레인)을 확인하고 그것만 설치합니다.

- **Windows 10/11:** [JavisOS-Setup.exe](https://github.com/blogminhquy/javis-os/releases/download/desktop/JavisOS-Setup.exe)를 내려받아 더블클릭하고 끝까지 Next를 누르세요. 설치 진행 상황은 Setup 창 안에 단계별로 표시되며(몇 분), 별도의 검은 창은 뜨지 않습니다. 끝나면 바탕 화면과 시작 메뉴에 JAVIS OS 아이콘이 생깁니다.
- **macOS 11 이상:** **터미널**을 열고(Launchpad에서 Terminal 입력) 아래 한 줄을 붙여 넣은 뒤 Enter를 누르세요. 이렇게 설치하면 macOS 경고가 뜨지 않습니다:
  ```
  curl -fsSL https://raw.githubusercontent.com/blogminhquy/javis-os/main/packaging/macos/get-javis.sh | bash
  ```
  이 명령은 Javis를 내려받아 **JAVIS OS**를 **Applications**에 복사하고 그 터미널 창에서 바로 설치합니다(Javis 관리자 계정 설정과 Mac 암호를 한 번 물어볼 수 있습니다). 설치가 끝나면 Launchpad에서 JAVIS OS를 여세요.

  파일로 설치하고 싶다면 [JavisOS-macOS.dmg](https://github.com/blogminhquy/javis-os/releases/download/desktop/JavisOS-macOS.dmg)를 내려받아 열고 **JAVIS OS**를 **Applications**로 끌어 놓은 뒤 Launchpad에서 여세요. 아직 Apple Developer ID로 서명되지 않아 처음 열 때 macOS가 차단합니다. 허용하는 방법은 아래 "차단된 경우"에 있습니다.

아이콘을 클릭하면 Javis가 별도 창(주소 표시줄 없음)으로 열리고, 컴퓨터와 함께 자동으로 시작되며, 앱의 **Update** 버튼도 평소처럼 동작합니다. 데이터는 사용자 폴더의 `JavisOS` 폴더에 있으며, 앱을 제거해도 이 폴더는 남습니다.

**Windows: 경고 화면 없이 설치하기(권장).** Windows 설치 프로그램은 아직 코드 서명이 없어, 브라우저로 내려받으면 처음에 차단됩니다. 대신 한 줄을 붙여 넣으면 Javis 로고가 있는 같은 설치 프로그램이 차단 없이 열립니다. 시작을 누르고 `PowerShell`을 입력해 연 다음, 아래 한 줄을 붙여 넣고 Enter를 누르세요:
```
irm https://raw.githubusercontent.com/blogminhquy/javis-os/main/packaging/windows/get-javis.ps1 | iex
```

설치 프로그램이 컴퓨터에서 무엇을 바꾸는지, 누가 서명하는지, Javis가 무엇을 어디로 보내는지: [Code signing policy](../../../docs/code-signing-policy.md) · [Privacy policy](../../../PRIVACY.md) (영어).

이미 브라우저로 파일을 내려받았는데 차단된 경우:
- Edge나 Chrome에서 "JavisOS-Setup.exe isn't commonly downloaded"라고 나오고 파일이 저장되지 않으면: 다운로드 상자에서 그 줄에 마우스를 올리고 점 세 개를 누른 뒤 **Keep**을 선택하고, 이어서 **Show more**와 **Keep anyway**를 누르세요.
- Windows에서 "Windows protected your PC"가 나오면 **More info**를 누른 다음 **Run anyway**를 누르세요.
- 백신 프로그램이 파일을 지우거나, Windows가 **Run anyway** 버튼 없이 차단하면(Smart App Control이 켜져 있음): .exe 없이 설치하세요. [Git](https://git-scm.com/download/win)을 설치하고 PowerShell을 연 다음, 아래 한 줄을 붙여 넣고 Enter를 누르세요. 끝나면 Javis가 http://localhost:7777 에서 열리고 컴퓨터와 함께 자동으로 시작됩니다:
  ```
  git clone https://github.com/blogminhquy/javis-os.git "$env:USERPROFILE\JavisOS"; cd "$env:USERPROFILE\JavisOS"; powershell -ExecutionPolicy Bypass -File install.ps1
  ```
- macOS에서 앱을 열 수 없다고 나오면 **System Settings → Privacy & Security**로 가서 아래로 내려 **Open Anyway**를 누른 뒤 JAVIS OS를 다시 여세요.

## 방법 1 - Hostinger VPS (Docker Manager, 원클릭)

> 🛒 **아직 VPS가 없나요?** [여기서 Hostinger VPS 신청하기](https://www.hostinger.com?REFERRALCODE=JAVISOS). Docker Manager가 기본 탑재되어 있어 Javis를 원클릭으로 설치합니다. 준비되면 아래 단계로 돌아오세요.

1. hPanel → VPS → **Docker Manager** → **Compose** → **Compose from URL**.
2. 다음 URL을 붙여 넣습니다.
   ```
   https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.hostinger.yml
   ```
3. (선택, HTTPS + 도메인을 쓰려면) **Environment** 상자에 다음을 설정합니다.
   ```
   DOMAIN_NAME=javis.<vps-hostname>.hstgr.cloud
   ```
   (호스트 이름은 hPanel → VPS에서 확인할 수 있습니다. 예: `javis.srv1782015.hstgr.cloud`.)
4. **Deploy** 를 누릅니다. 1-3분 기다린 뒤 **Open** 버튼(또는 `https://<DOMAIN_NAME>`)으로 앱을 엽니다.
5. 처음 실행하면 관리자 계정을 만들라는 화면이 나옵니다. 그다음 컨테이너 터미널에서 Claude Code에 한 번 로그인합니다: `claude auth login --claudeai`.

업데이트하려면 Docker Manager에서 **Redeploy** 를 누릅니다(이미지 `:latest`, `pull_policy: always`). Brain 데이터는 볼륨에 그대로 남습니다.

## 방법 2 - 아무 컴퓨터나 VPS에서 Docker로

> 🛒 **VPS가 필요하신가요?** 이 방법도 [Hostinger VPS](https://www.hostinger.com?REFERRALCODE=JAVISOS)에서 동작합니다.

```
docker compose -f docker-compose.yml up -d
```
http://localhost:7777 을 엽니다. Caddy를 통해 HTTPS를 쓰려면 `-f docker-compose.https.yml` 을 추가합니다.

## 방법 3 - 직접 실행 (Windows, Docker 없이)

1. Python 3.12 + Node 22를 설치합니다.
2. 프로젝트 폴더에서 `setup.bat` 을 한 번 실행합니다. .venv를 만들고, 의존성을 설치하고, CLI 엔진 두 가지(Claude Code, Codex)도 대신 설치해 줍니다.
3. `start-javis.bat` 으로 백그라운드에서 실행합니다(멈추려면 `stop-javis.bat`).
4. http://localhost:7777 을 엽니다.

## 실행한 다음에는

- **엔진/모델 선택**: **Models** 페이지(Claude Code, ChatGPT/Codex, Antigravity CLI, OpenRouter, OpenAI, Google Gemini, Anthropic API, Groq, Ollama).
- 보고서가 실제 수치로 만들어지도록 **연결 설정**(POS, 광고, 캘린더, Zalo...): **Connections** 페이지. [docs/09](../../../docs/en/09-connections-and-business-data.md) 참고.
- 데이터를 잃지 않도록 **Brain을 GitHub에 백업**: **Self-learning** 페이지. [docs/18](../../../docs/en/18-github-backup.md) 참고.
- **토큰 사용량 확인**: **Usage** 페이지. [docs/23](../../../docs/en/23-usage-and-cost.md) 참고.

## 전체 문서

[docs/en/README.md](../../../docs/en/README.md) 를 참고하세요. 기능별 안내서가 있습니다(채팅/음성, 지식 그래프, Skill, Agent, Workflow, 반복 작업, Kanban, 자기 학습, 연결, Telegram, Zalo, Plugin, 보안, 백업...). 같은 안내서의 베트남어판: [docs/README.md](../../../docs/README.md).

## 자주 겪는 문제

- **Hostinger에서 앱 내 업데이트 버튼이 아무 동작도 하지 않음**: 의도된 동작입니다. Hostinger에서는 Docker Manager의 **Redeploy** 를 쓰세요. 앱 내 버튼은 Watchtower가 필요한데, Hostinger는 보통 Docker 소켓을 막아 둡니다.
- **ChatGPT/Codex가 "model not supported" 라고 함**: Models 페이지에서 유효한 Codex 모델을 고르세요(예: `gpt-5.5`). `gpt-5-mini` 나 `gpt-4o` 는 쓰지 마세요. 이들은 API 모델이라 Codex 계정으로는 실행할 수 없습니다.
- 더 보기: [docs/17 - 문제 해결](../../../docs/en/17-troubleshooting.md).
