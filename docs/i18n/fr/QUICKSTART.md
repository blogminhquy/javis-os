<!-- translated-from: QUICKSTART.en.md sha256:338011fb77ad -->
# Javis OS - Démarrage rapide

*[English](../../../QUICKSTART.en.md) · [Tiếng Việt](../../../QUICKSTART.md) · [简体中文](../zh/QUICKSTART.md) · [Español](../es/QUICKSTART.md) · [日本語](../ja/QUICKSTART.md) · [हिन्दी](../hi/QUICKSTART.md) · [Português](../pt-BR/QUICKSTART.md) · [한국어](../ko/QUICKSTART.md) · [Русский](../ru/QUICKSTART.md) · [Deutsch](../de/QUICKSTART.md) · **Français** · [Bahasa Indonesia](../id/QUICKSTART.md)*

> Ceci est une traduction automatique du guide de démarrage rapide anglais.

Faites tourner Javis OS en quelques minutes. Guides complets : [docs/en/](../../../docs/en/README.md).

## Ordinateur personnel (Windows, macOS) - télécharger l'installeur

Installez Javis comme n'importe quelle application : téléchargez un fichier, ouvrez-le, et vous avez une icône JAVIS OS à cliquer chaque jour. L'installeur vérifie ce qui manque à l'ordinateur (Git, Python, Node, les cerveaux IA) et n'installe que cela.

- **Windows 10/11 :** téléchargez [JavisOS-Setup.exe](https://github.com/blogminhquy/javis-os/releases/download/desktop/JavisOS-Setup.exe), double-cliquez et appuyez sur Next jusqu'au bout. La progression s'affiche dans la fenêtre Setup elle-même, étape par étape (quelques minutes), sans fenêtre noire séparée. À la fin, une icône JAVIS OS apparaît sur le Bureau et dans le menu Démarrer.
- **macOS 11 ou plus récent :** ouvrez le **Terminal** (Launchpad, tapez Terminal), collez cette ligne et appuyez sur Entrée. Installé ainsi, macOS n'affiche aucun avertissement :
  ```
  curl -fsSL https://raw.githubusercontent.com/blogminhquy/javis-os/main/packaging/macos/get-javis.sh | bash
  ```
  La commande télécharge Javis, copie **JAVIS OS** dans **Applications** et l'installe directement dans cette fenêtre du Terminal (elle peut demander une fois de créer un compte administrateur Javis et le mot de passe du Mac). Ensuite, ouvrez JAVIS OS depuis le Launchpad.

  Vous préférez un fichier ? Téléchargez [JavisOS-macOS.dmg](https://github.com/blogminhquy/javis-os/releases/download/desktop/JavisOS-macOS.dmg), ouvrez-le, glissez **JAVIS OS** dans **Applications**, puis ouvrez-le depuis le Launchpad. Il n'est pas encore signé avec un Apple Developer ID, macOS bloque donc la première ouverture : la marche à suivre se trouve plus bas, dans la partie sur les téléchargements bloqués.

Un clic sur l'icône ouvre Javis dans sa propre fenêtre (sans barre d'adresse), Javis démarre avec l'ordinateur et le bouton **Update** de l'application fonctionne comme d'habitude. Vos données sont dans le dossier `JavisOS` de votre dossier utilisateur ; désinstaller l'application conserve ce dossier.

**Windows : installer sans l'écran d'avertissement (recommandé).** L'installeur Windows n'est pas encore signé, un téléchargement par le navigateur est donc bloqué la première fois. Collez plutôt une ligne et vous obtenez le même installeur avec le logo Javis, sans blocage : appuyez sur Démarrer, tapez `PowerShell`, ouvrez-le, collez cette ligne et appuyez sur Entrée :
```
irm https://raw.githubusercontent.com/blogminhquy/javis-os/main/packaging/windows/get-javis.ps1 | iex
```

Ce que les installeurs modifient sur votre ordinateur, qui les signe et ce que Javis envoie et où : [Code signing policy](../../../docs/code-signing-policy.md) · [Privacy policy](../../../PRIVACY.md) (en anglais).

Si vous avez déjà téléchargé le fichier avec le navigateur et qu'il a été bloqué :
- Edge ou Chrome indique "JavisOS-Setup.exe isn't commonly downloaded" et n'enregistre pas le fichier : dans la zone Téléchargements, survolez cette ligne, cliquez sur les trois points, choisissez **Keep**, puis **Show more** et **Keep anyway**.
- Windows affiche "Windows protected your PC" : cliquez sur **More info**, puis sur **Run anyway**.
- Votre antivirus supprime le fichier, ou Windows le bloque sans bouton **Run anyway** (Smart App Control est activé) : installez sans le .exe. Installez [Git](https://git-scm.com/download/win), ouvrez PowerShell, collez cette ligne et appuyez sur Entrée. À la fin, Javis s'ouvre sur http://localhost:7777 et démarre avec l'ordinateur :
  ```
  git clone https://github.com/blogminhquy/javis-os.git "$env:USERPROFILE\JavisOS"; cd "$env:USERPROFILE\JavisOS"; powershell -ExecutionPolicy Bypass -File install.ps1
  ```
- macOS indique qu'il ne peut pas ouvrir l'application : allez dans **System Settings → Privacy & Security**, faites défiler, cliquez sur **Open Anyway**, puis rouvrez JAVIS OS.

## Option 1 - VPS Hostinger (Docker Manager, en un clic)

> 🛒 **Pas encore de VPS ?** [Prenez un VPS Hostinger ici](https://www.hostinger.com?REFERRALCODE=JAVISOS). Docker Manager est intégré, donc Javis s'installe en un clic. Une fois prêt, revenez aux étapes ci-dessous.

1. hPanel → VPS → **Docker Manager** → **Compose** → **Compose from URL**.
2. Collez cette URL :
   ```
   https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.hostinger.yml
   ```
3. (Facultatif, pour le HTTPS + un domaine) définissez ceci dans le champ **Environment** :
   ```
   DOMAIN_NAME=javis.<vps-hostname>.hstgr.cloud
   ```
   (Le hostname se trouve dans hPanel → VPS, par ex. `javis.srv1782015.hstgr.cloud`.)
4. **Deploy**. Attendez 1-3 minutes. Ouvrez l'application avec le bouton **Open** (ou via `https://<DOMAIN_NAME>`).
5. Au premier lancement, l'écran vous demande de créer un compte administrateur. Ensuite, connectez-vous une fois à Claude Code depuis le terminal du conteneur : `claude auth login --claudeai`.

Pour mettre à jour : cliquez sur **Redeploy** dans Docker Manager (image `:latest`, `pull_policy: always`). Les données du Brain restent dans le volume.

## Option 2 - Docker sur n'importe quelle machine ou VPS

> 🛒 **Besoin d'un VPS ?** Un [VPS Hostinger](https://www.hostinger.com?REFERRALCODE=JAVISOS) convient aussi à cette option.

```
docker compose -f docker-compose.yml up -d
```
Ouvrez http://localhost:7777. Pour le HTTPS via Caddy, ajoutez `-f docker-compose.https.yml`.

## Option 3 - Lancement direct (Windows, sans Docker)

1. Installez Python 3.12 + Node 22.
2. Dans le dossier du projet, lancez `setup.bat` une fois : il crée .venv, installe les dépendances et installe pour vous les deux moteurs CLI (Claude Code, Codex).
3. `start-javis.bat` pour le lancer en arrière-plan (`stop-javis.bat` pour l'arrêter).
4. Ouvrez http://localhost:7777.

## Une fois lancé

- **Choisir un moteur/modèle** : la page **Models** (Claude Code, ChatGPT/Codex, Antigravity CLI, OpenRouter, OpenAI, Google Gemini, Anthropic API, Groq, Ollama).
- **Brancher des connexions** (caisse, publicité, agenda, Zalo...) pour que les rapports reposent sur de vrais chiffres : la page **Connections** (voir [docs/09](../../../docs/en/09-connections-and-business-data.md)).
- **Sauvegarder le Brain sur GitHub** pour ne pas perdre de données : la page **Self-learning** (voir [docs/18](../../../docs/en/18-github-backup.md)).
- **Surveiller la consommation de tokens** : la page **Usage** (voir [docs/23](../../../docs/en/23-usage-and-cost.md)).

## Documentation complète

Voir [docs/en/README.md](../../../docs/en/README.md) : un guide par fonctionnalité (chat/voix, graphe de connaissances, skills, agents, workflows, tâches récurrentes, Kanban, auto-apprentissage, connexions, Telegram, Zalo, plugins, sécurité, sauvegarde...). Les mêmes guides en vietnamien : [docs/README.md](../../../docs/README.md).

## Problèmes courants

- **Le bouton de mise à jour de l'application ne fait rien sur Hostinger** : c'est voulu. Sur Hostinger, utilisez **Redeploy** dans Docker Manager. Le bouton de l'application a besoin de Watchtower, et Hostinger bloque généralement le socket Docker.
- **ChatGPT/Codex indique "model not supported"** : choisissez un modèle Codex valide sur la page Models (par ex. `gpt-5.5`). N'utilisez pas `gpt-5-mini` ni `gpt-4o` : ce sont des modèles d'API, et un compte Codex ne peut pas les exécuter.
- Plus d'informations : [docs/17 - Dépannage](../../../docs/en/17-troubleshooting.md).
