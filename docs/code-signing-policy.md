# Code signing policy

Free code signing provided by [SignPath.io](https://about.signpath.io/), certificate by [SignPath Foundation](https://signpath.org/).

> **Status (2026-11-13):** the application to SignPath Foundation is being prepared. Until it is accepted, `JavisOS-Setup.exe` is published **unsigned**, and Windows shows a warning when you download or open it. [QUICKSTART](../QUICKSTART.en.md) explains how to install anyway. This page describes how signing works once it is on.

## What is signed

Only one file: **`JavisOS-Setup.exe`**, the Windows installer of JAVIS OS, published on the [`desktop` release](https://github.com/blogminhquy/javis-os/releases/tag/desktop).

- It is built from this repository by the public workflow [`.github/workflows/desktop-installers.yml`](../.github/workflows/desktop-installers.yml), on GitHub-hosted runners, from [`packaging/windows/javis-setup.iss`](../packaging/windows/javis-setup.iss). Nobody builds or signs a release on a personal computer.
- It contains the installer script `bootstrap.ps1`, two short text pages, an icon and the wizard pictures. No third-party binary is packed inside it.
- The signing key never leaves SignPath. The workflow hands the freshly built file to SignPath, which checks that it came out of that workflow run, and returns it signed. The repository holds no certificate and no private key.
- The publisher shown by Windows is **SignPath Foundation**, which vouches that the file was built from this repository.

No other file of the project is signed: not the macOS disk image, not the scripts, not the Docker image.

## What the installer does

The installer is small because it downloads the rest. It tells you so on a page before it starts, and the two optional parts can be unticked:

1. Clones this repository from GitHub into `%USERPROFILE%\JavisOS` (a git clone, so the in-app **Update** button works).
2. Installs Git, Python and Node.js if they are missing, through winget or from git-scm.com, python.org and nodejs.org.
3. Installs the Python libraries listed in [`requirements.txt`](../requirements.txt).
4. Optional, ticked by default: installs four AI command-line tools **from their own vendors**: Claude Code (Anthropic), Codex (OpenAI), Antigravity CLI (Google) and Grok Build (xAI). They are separate products, not part of JAVIS OS, with their own licenses and privacy policies. JAVIS OS itself is MIT licensed and also runs without them, with an API key.
5. Optional, ticked by default: starts JAVIS OS when you sign in to Windows.

Uninstalling (Windows Settings, Apps, **JAVIS OS**) stops Javis, removes the shortcuts and the start with Windows, and keeps the `JavisOS` folder with your notes until you delete it.

## Team roles

JAVIS OS is maintained by one person, who holds every role. Multi-factor authentication is required on the GitHub account and on the SignPath account.

| Role | Who | What it means here |
| --- | --- | --- |
| Committers and reviewers | [Nguyen Minh Quy (@blogminhquy)](https://github.com/blogminhquy) | Owns the repository. Changes reach `main` only through a pull request with green CI. Pull requests from outside contributors are reviewed by the maintainer before they merge. |
| Approvers | [Nguyen Minh Quy (@blogminhquy)](https://github.com/blogminhquy) | Approves each signing request at SignPath by hand, after checking that it comes from a workflow run on `main`. |

## Privacy policy

This program will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it.

The details, including the public files Javis downloads on its own to check for updates, are in [PRIVACY.md](../PRIVACY.md).

## Checking a download

Right-click `JavisOS-Setup.exe`, **Properties**, **Digital Signatures**: a signed file lists **SignPath Foundation**. In PowerShell:

```
Get-AuthenticodeSignature .\JavisOS-Setup.exe | Format-List Status, SignerCertificate
```

`Status` must be `Valid`. A file that claims to be the JAVIS OS installer and is signed by someone else, or a signed file that misbehaves, is a security problem: please report it as described in [SECURITY.md](../SECURITY.md).

## For the maintainer: switching signing on

The workflow already contains the signing job (`sign-windows`). It stays off until the repository has, under **Settings, Secrets and variables, Actions**:

| Kind | Name | Value |
| --- | --- | --- |
| Secret | `SIGNPATH_API_TOKEN` | API token of a SignPath user allowed to submit signing requests |
| Variable | `SIGNPATH_ORGANIZATION_ID` | Organization ID from the SignPath dashboard |
| Variable | `SIGNPATH_PROJECT_SLUG` | Slug of the project at SignPath |
| Variable | `SIGNPATH_SIGNING_POLICY_SLUG` | Slug of the signing policy (usually `release-signing`) |
| Variable | `SIGNPATH_ARTIFACT_CONFIGURATION_SLUG` | Optional. Empty uses the project's default artifact configuration |

The artifact the workflow submits is the zip GitHub makes of one file, so the artifact configuration at SignPath is a `zip-file` holding the installer:

```xml
<?xml version="1.0" encoding="utf-8"?>
<artifact-configuration xmlns="http://signpath.io/artifact-configuration/v1">
  <zip-file>
    <pe-file path="JavisOS-Setup.exe">
      <authenticode-sign/>
    </pe-file>
  </zip-file>
</artifact-configuration>
```

After that, a change to the installer on `main` (or **Run workflow** by hand) creates a signing request. It waits up to two hours for the approval at SignPath, then the signed file replaces the published one. A run that does not change the installer asks for nothing and keeps the published file, so its hash and its reputation stay.

Not signed yet: the uninstaller that Setup writes into the install folder. It never comes from a download, so SmartScreen does not judge it.
