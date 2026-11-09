# GitHub inside chat

*[Tiếng Việt](../34-github-trong-chat.md) · **English***

Attach GitHub repos to a conversation, give the job in words, and Javis does the rest: edits on its own branch, checks its work, pushes, opens a PR, watches CI, fixes red CI and merges when green. A small icon next to the conversation shows where it stands.

Full design: [docs/dev/2026-10-github-trong-chat-spec.md](../dev/2026-10-github-trong-chat-spec.md) (Vietnamese).

## 1. Connect GitHub (once)

Open **Connections**. The **GitHub** card is always first: it is built into Javis, nothing to install.

**git comes first.** Javis downloads repos with git, so pressing **Connect** checks for git on this machine. When it is missing, Javis installs it and then opens the sign-in step, usually within 1 to 3 minutes:

- **Windows:** winget, or the official Git for Windows installer when winget is absent. Both install for the signed-in user only, no admin rights needed.
- **Mac:** Homebrew when the machine has it, otherwise Apple opens its developer tools dialog: press **Install** and Javis carries on when it is done.
- **Linux/VPS:** the package manager (apt, dnf, yum, apk, pacman, zypper) when Javis runs as root or has password-less sudo. The official Docker image already ships git.

If the install fails, the dialog shows the exact command to run by hand, **Try again** and **Skip, connect anyway**. A git installed by hand while Javis runs is picked up right away, no restart. A connected card on a machine without git has its own **Install git** button.

1. On github.com: **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. Pick the repos Javis may work on. Grant **Contents**, **Pull requests**, **Workflows** (Read and write); **Checks**, **Actions**, **Commit statuses**, **Metadata** (Read).
3. Paste the token into the GitHub card and press **Connect**.

Already using [brain backup to GitHub](18-github-backup.md)? Press **Use the brain-backup token** to share it; Javis checks its permissions first. A classic `ghp_...` token needs the `repo` and `workflow` scopes.

The token is encrypted at rest and never sent back to the browser. Javis hands it to git through the environment of that one command, so a model running commands in the repo folder has no way to push on its own.

## 2. Attach repos to a conversation

In a chat press **plus → GitHub repo**, tick one or more repos, press **Attach**. A chip with the repo name appears next to the input.

- Javis downloads the repo to this machine, **outside** the brain folder (`<state folder>/repos/<brain>/<owner>/<repo>`), so code never ends up in the brain backup or in search.
- Each conversation works on **its own branch and folder** (`javis/...`). Two chats editing the same repo never overwrite each other.
- Attaching runs no script and installs nothing until a check needs it.

## 3. After every turn that changes code

Javis does this on its own:

1. **Local checks**: runs the repo's own CI commands (read from `.github/workflows`, leaving out steps that install into the machine, need secrets or deploy), scans the diff for secrets, and looks for "green CI by cheating" (skipped or deleted tests, edited workflows, loosened coverage). A failing command means **no push**: Javis opens a fix turn with the error.
2. **Commit, push, open a PR** (as a draft) under your GitHub account.
3. **Watch CI** on exactly the pushed commit. A new commit never inherits the green result of an older one.
4. **Red CI**: Javis opens a fix turn in that same conversation, with the logs. At most **3 rounds**, then it reports being stuck with the reason. Red on the base branch too means it is not this job's fault; Javis does not widen the job.
5. **Cross review (your call, off by default)**: a model reads the diff and reports only bugs with a concrete failure path. Javis no longer reviews on its own unless you say so.
   - **Turn it on for a repo:** GitHub card, the repo's "..." menu, **Cross review**, switch on **Review before merging**. From then on every commit with green CI is reviewed before the merge.
   - **Review a PR any time:** press the GitHub icon next to the conversation, pick a model and press **Review now**. Or say "review this PR", "review it with DeepSeek". The PR does not merge until the review is done.
   - **Reviewer:** by default **the model you are chatting with**; it need not be another vendor. For another model, pick it in **Reviewer** (per repo, or each time you press Review now); it runs on the model and reasoning level picked on its card of the Models page.
   - **Findings:** Javis stops, does not merge, and lists them with two buttons, **Fix them** (the model that wrote the code checks and fixes each) and **Skip and merge**. Replying in the chat works too. Pushing a new commit leaves the old findings behind.
   - **Who cannot review:** the ChatGPT, Grok Build and Antigravity plans run through a CLI that keeps file tools, so they never read a repo's diff. Chatting on one of them, Javis uses the next card of the Models page (Claude, or a provider on an API key). A reviewer that fails is named in the chat with the reason, then skipped for that commit.
6. **Merge**: green CI makes Javis **merge on its own**, with a method the repo allows. It does not merge alone when the repo's switch is off, a flagged change needs a person, the repo has no CI, or the repo still requires a review.

Each repo's local check commands are editable on the GitHub card of the Connections page (**Checks**). The **Auto-merge on green CI** switch is there too, on by default. **Cross review** sits in the repo's "..." menu, off by default.

## 4. Four icons next to the conversation

| Icon | Meaning |
|---|---|
| Pulsing branch (with a count) | Working, or waiting for CI; the count is how many jobs run in parallel |
| Green branch with a tick | Ready to merge |
| Purple merge icon | Merged (with a warning mark when the checks after the merge failed) |
| Warning triangle | Needs attention: conflict, failed merge, or stuck |

Press the icon to open the details: branch, PR link, each CI check, why it is stuck, flagged changes, queued next jobs, and a **Merge** button when the PR is ready.

## 5. Next jobs

Gave several jobs at once ("when this is done, do that")? Javis queues the next one and **starts it only once the current PR is merged and the checks on the base branch after the merge passed**. Green CI never creates work you did not ask for.

## 6. Lessons and numbers

- Each time CI or a local check failed and was then fixed, Javis writes one lesson line for that repo into `Javis/learned/repos/` in the brain, and feeds it back on the next turn.
- The **Numbers** button on the GitHub card shows, per engine and model: share of jobs green on the first push, average fix rounds, issues caught by the cross review. Pick a model with real numbers.

## 7. Removing a repo

- **Detach from a conversation** (untick it under plus → GitHub repo): the downloaded copy stays.
- **Remove from brain** (GitHub card on the Connections page): deletes the local copy only; the repo on GitHub stays as it is. Javis refuses while there are unsaved edits, unpushed commits or a running job.
- Deleting a conversation removes its clean working folders and keeps any folder with work left in it.
