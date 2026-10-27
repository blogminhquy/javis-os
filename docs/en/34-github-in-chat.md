# GitHub inside chat

*[Tiếng Việt](../34-github-trong-chat.md) · **English***

Attach GitHub repos to a conversation, give the job in words, and Javis does the rest: edits on its own branch, checks its work, pushes, opens a PR, watches CI, fixes red CI and merges when green. A small icon next to the conversation shows where it stands.

Full design: [docs/dev/2026-10-github-trong-chat-spec.md](../dev/2026-10-github-trong-chat-spec.md) (Vietnamese).

## 1. Connect GitHub (once)

Open **Connections**. The **GitHub** card is always first: it is built into Javis, nothing to install.

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
5. **Cross review**: once CI is green, an engine from **another vendor** than the one that wrote the code reads the diff and reports only issues with a concrete failure path. The author verifies each: fixes what is real, rejects the rest with reasons.
6. **Merge**: green CI makes Javis **merge on its own**, with a method the repo allows. It does not merge alone when the repo's switch is off, a flagged change needs a person, the repo has no CI, or the repo still requires a review.

Each repo's local check commands are editable on the GitHub card of the Connections page (**Checks**). The **Auto-merge on green CI** switch is there too, on by default.

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
