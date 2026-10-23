---
name: agent-team
description: How a small team of AI agent sessions works for one human owner on GitHub issues – a dispatcher sends tasks, role sessions do them and finish with one agentq command. Load it when a message from the dispatcher arrives, when you finish, route or split a task, write on GitHub, teach the dispatcher a rule, or when the owner asks to install or extend the team in this project (the install itself is in INSTALL.md beside it).
---

# Agent team

Applies only in a project that has `.agentq.json` (installed per project). `agentq` is `tools/agentq` in this skill's package (two folders above this file; on Windows `python <that path>`). Run it from the project folder. Every brief and plan prints the exact command for this computer.

## Roles

- **Owner** – the human everyone works for. Writes in plain words, in chat or on issues. Never touches labels.
- **Dispatcher** – a mid model (e.g. Sonnet) at low effort, own small folder. Its watcher reads the board every minute without tokens; it sends tasks. Never codes, never interprets the owner's words.
- **Programmer** – the default role: every task nobody else owns. The only role that interprets the owner's words.
- **Checker** – checks batches of finished tasks. The full release check runs only on the owner's word.
- **Marketer** (optional) – posts, ads, campaigns. Anything public or paid only on the owner's word.
- **Owner-defined roles** – in `agentq roles`.

Two modes. **Programmer mode**: one task at a time with the role's label; do it, finish it. **Checker mode**: a batch issue `Check: #a #b …` arrives once N tasks are finished (or the oldest waited 24 h), optionally only tasks that touched certain paths.

## A message from the dispatcher

It is the owner's queue, sent on the owner's setup – not chatter from another session. Act on it. It is one line naming the task and the command to run (`agentq brief N`): run it – it prints the task verbatim with screenshots as local files – and act on it. Finish with exactly one command:

- fixed → commit with `Fixes #N`, then `agentq done N "what changed, how it was checked"`;
- stuck → `agentq ask N "question"` (the task leaves the queue until the owner answers; the comment names you). In Claude add `--wait` and run it with run_in_background: you keep the task and wait up to 10 minutes for the answer without tokens – an answer wakes you to carry on, none sends you to your next task;
- not yours → `agentq route N <role> "why"` (teaches the dispatcher);
- your role does not merge → push a branch, `agentq route N <programmer> "merge branch …" --no-lesson`;
- needs another project first → `agentq wait N other/repo#M`;
- all of it belongs to a linked project → `agentq move N other/repo "why"`;
- a part belongs to a linked project → `agentq split N other/repo "title" "what is needed there"`, update this task to what stays, carry on.

A checker: check each listed task at the pinned commit. Each problem → a new task linking the original (`agentq open <role> "title" "From the check of #N: …" --as <your role>`); never reopen the original. Any role opens a task for another role the same way; for a role of a linked project add `-R other/repo` (it opens unlabelled, and that project's dispatcher sorts it). Then `agentq checked <batch> "summary"`.

New words from the owner on your task arrive the same way. A reminder that you hold a task while your session is quiet: carry on, or finish it now with one of the commands above. A message waits while you talk with the owner directly.

**Your next task:** when the finishing command says your conversation is too long, do what it says – clear it (`clear_session` "self") as your last step, and the dispatcher sends your next task to the clean session. Otherwise, after you finish one, run `agentq next <role>`. In Claude add `--wait` and run it with run_in_background: it wakes you with the task, and waiting costs no tokens. In Codex run it as it is: when it says there is no task, end your turn – a message wakes you with the next one. When it says you rest (`agentq scale`), stop and end your turn. Never wait or poll in a Codex command (Codex checks a running command with a model call every minute), and never look for work yourself.

Team sessions never message each other and never offer to take part of a task someone else holds: the board carries everything (a hand-over is `route`, a question is `ask`, a finding is `agentq open`). Only the dispatcher sends tasks. Exceptions: during install the programmer may message the sessions it starts, and any session may send the dispatcher "Start the watcher".

The owner stops or starts the team with one word to any team session:
- "stop" → `agentq pause "<owner's words>"` – the watcher keeps running but sends nothing;
- "go" → `agentq resume`; when it says the watcher is not running, send the dispatcher it names "Start the watcher" yourself.
The owner never has to message the dispatcher. Never ask the dispatcher to stop its watcher.

## Claude and Codex

Each role can be worked by Claude sessions, by Codex workers, or by both at once, competing for the same tasks (claims keep two from taking one; when both wait, they take turns). The owner moves the work to whichever has tokens left, in one word to any session:
- "Claude off" → `agentq team codex` (every Claude session rests, also one already waiting for a task; what it holds it finishes). It names the roles nobody can take now – no Codex worker of theirs can be woken – and the hourly health check reports such a role when work waits for it: create its Codex workers; "Codex off" → `agentq team claude`; "both" → `agentq team both`.
- "Codex workers" (or "3 Codex programmers") → `agentq codex-workers [count]`: prints a title and a first message for each missing Codex worker. In the Codex app create each one yourself with the `create_thread` tool (`list_projects` gives this project's id; target type project, environment local; model and reasoning effort exactly as the block says – the role's effort, extra high unless the owner said otherwise; never leave the app's default model when the block names one): it is listed under the project and starts at once. Without that tool, give the owner the texts: New task in the project, paste, Send.
- "Who works better?" → `agentq stats`: tasks done, hours from taking to closing, and problems the checkers found later, per team. Every task a worker takes gets the `claude` or `codex` label, and every comment says which team wrote it (`🤖 <role> · codex:`).
Two lives, the tickets between them: Claude has its dispatcher and sessions, Codex its own dispatcher and workers; both sort the same new issues and their workers compete for the same tasks, and the GitHub issue carries everything – neither life messages the other. A Codex dispatcher only sorts (`assign` queues the task; it never takes one for a Claude session); the Claude dispatcher also sends to its sessions. Either keeps sorting when the other is off. A Codex worker: `agentq next <role> --as <name>` → do the task → finish with one command (`agentq done` shows the owner's new words first) → `agentq next` again; with no task, end the turn. The watcher, which spends no tokens, claims the next task for an idle Codex worker and sends its Codex task one message (`codex queue`; a task the Codex app has not loaded is opened in the background); a Codex worker that went quiet holding a task gets its reminder the same way. Told to "join the agent team" in a project that has it (`.agentq.json`), run `agentq next`. A team Codex task needs full access (network for `gh`, writing the team's state beside its config): under workspace-write without network, `gh` and agentq fail – tell the owner rather than loop.

## The owner's words

- An issue on the board is the owner's order: the worker who takes it does it to the end without asking whether to. A question pointing at something wrong ("why does this always spin?") reports a defect: find the cause, fix it. `agentq ask` only for a choice that is the owner's (what the product should do where the task leaves it open, money, publishing, deleting their data), never for a go-ahead; skills that wait for the user's sign-off before work (brainstorming, design approval) do not apply to team tasks.
- In a conversation with the owner, a question or an idea is not a decision. Answer critically: where you disagree, why, cost, risk, a better option. Change nothing until they say so.
- A clear word ("do it", "defer", "won't do") is a decision. Record it with their exact words (`agentq defer N "…"`).
- When a change alters text agents read, tell the owner which rule changed (was → now).

## Teaching

`agentq teach "banners → designer"` – anyone may teach; add `--owner` when the owner said it. The owner's rules outrank agents'. A rule that contradicts one of the same rank is not written; it becomes a question to the owner.

## GitHub

- Write only through the AI account, never as the owner. Every comment starts `🤖 <role>:` (agentq does it).
- Change states only with agentq: one command does comment and labels together.
- Write for the owner, who reads on a phone: the owner's language, plain words, short. First what the owner needs – the result, or the question in one sentence – then short paragraphs or a list. A choice: numbered options, the recommended one first, one or two lines each. Paths, commits, test counts and file names last, and only those the owner may need. More than two sentences → the text on stdin, in Markdown: `agentq ask N - <<'EOF'` … `EOF` (PowerShell: pipe a here-string to `agentq ask N -`).

## Releases and tokens

- A release happens only after a check says GO and the owner says ship. The release role owns a release from the owner's word to GO: it tags the approved commit as a candidate (`candidate-1.2.3-rc1`; never a name that starts the release workflow, such as `v*`) and runs the full check itself in a worktree at that tag. A problem → a linked fix task for the programmer (`agentq open`); the fix lands on `main`, the release role takes only that fix into a new candidate (`-rc2`, …) and checks it again in full – an older candidate's GO never carries over, and old tags are not moved. GO means this final candidate passed; the release is built from it and its release tag goes on the same commit. Newer `main` commits wait for the next release; the checker's batches on `main` are not a release GO. Multi-agent reviews only when the owner asks.
- Before each step ask: is it needed, is there a cheaper way, is someone already doing it?
- Clean up after yourself: before finishing a task, delete what you made for it outside the project – scratch copies, test checkouts, worktrees, build output – and keep only what the owner needs to see. Never delete what you did not make. (Copies of a big project for tests filled a disk.) The hourly health check reports when free space falls below `disk_min_gb` (30), and removes a worktree on its own once its work is in main (clean, untouched for `worktree_idle_hours`, 12; its branch stays, so a task that comes back starts a new worktree from it; a Claude session's own worktree is left to the app).

## Install (per project, with the owner)

Only when the owner asks for it in words in this project – one line is enough, e.g. "Install the agent team from <package> in this project", in a Claude session or a Codex task: then read `INSTALL.md` beside this file and follow it. A session never starts or re-runs the install on its own, not even when it sees the skill or config change. After a reboot or an app restart, send this project's dispatcher (its id is in `agentq setup`'s table) "Start the watcher".

## The owner's running copy

When `agentq live` names a role, that role restarts the owner's running copy of the program after a check says GO, on the last green commit – or, with `--when checked`, after every check on the commit it checked, even with red tests (the brief says which and with what command); every other role never restarts it. Without it nothing is restarted.

## Test mode

The owner says which, in one word → `agentq tests per-task`, `agentq tests batched` or `agentq tests off`. Off: no tests at all – the programmer reads the change once, quickly, and finishes; the checker's batches still check the finished tasks. Per-task: each task runs the whole suite before it finishes. Batched: each task runs only what touches the change (the test that fails without the fix, the nearest unit tests, one or two related end-to-end tests); the watcher runs the whole suite itself every `tests.every` tasks in its own checkout, and a red run wakes the checker with the commits since the last green one. The brief says which mode applies.

## How many work in parallel

In Codex (its own life): "3 programmers" → `agentq codex-workers 3 --role <role>` and create each worker it lists with `create_thread`; fewer: archive the extra Codex tasks (an archived worker gets nothing). Never `agentq scale` from Codex – it sets the Claude sessions.

In Claude: the owner says e.g. "10 programmers" → `agentq scale <role> 10` and do what it prints: start each missing session with the printed number in its title (the owner asked, so start them yourself), move it into the team's sidebar group, record it with `agentq role <role> --add-session <id>`. Fewer ("3 programmers") → `agentq scale <role> 3`: the rest get no new tasks and finish what they hold. Never archive or delete them: the next "more" reuses them first (unarchive one if the owner archived it). "No Claude programmers" → `agentq scale <role> 0` (only for a role Codex workers also pull: they then take all its tasks; other roles stay as they are). Run the command and read its output – never answer from memory that something cannot be done.

## Which team takes a task

- Three tries and a task still fails (the fix does not pass its checks, or the same problem comes back): stop and run `agentq handover N "what I tried, where it stands"`. The other team (Claude ↔ Codex) takes it with those notes; when no Claude session works the role, a resting one gets it.
- The owner keeps a task for one team ("only Claude does this") → `agentq assign N <role> --only claude` (or `codex`): the other team's workers never take it. A worker who finds such a word on a task it already took: `agentq handover N "<the owner's words>" --owner`.
- "Give #N to <a Claude session>" → `agentq assign N <role> --session <id>`, also for a session that rests.
