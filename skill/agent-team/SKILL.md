---
name: agent-team
description: How a small team of AI agent sessions works for one human owner on GitHub issues – a dispatcher sends tasks, role sessions do them and finish with one agentq command. Load it when a message from the dispatcher arrives, when you finish, route or split a task, write on GitHub, teach the dispatcher a rule, or when the owner asks to install or extend the team in this project.
---

# Agent team

Applies only in a project that has `.agentq.json` (installed per project). `agentq` is `tools/agentq` in this skill's package (two folders above this file). Run it from the project folder.

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
- stuck → `agentq ask N "question"` (the task leaves the queue until the owner answers);
- not yours → `agentq route N <role> "why"` (teaches the dispatcher);
- your role does not merge → push a branch, `agentq route N <programmer> "merge branch …" --no-lesson`;
- needs another project first → `agentq wait N other/repo#M`;
- all of it belongs to a linked project → `agentq move N other/repo "why"`;
- a part belongs to a linked project → `agentq split N other/repo "title" "what is needed there"`, update this task to what stays, carry on.

A checker: check each listed task at the pinned commit. Each problem → a new task linking the original (`agentq open <role> "title" "From the check of #N: …" --as <your role>`); never reopen the original. Any role opens a task for another role the same way. Then `agentq checked <batch> "summary"`.

New words from the owner on your task arrive the same way. A reminder that you hold a task while your session is quiet: carry on, or finish it now with one of the commands above. A message waits while you talk with the owner directly.

Team sessions never message each other: the board carries everything (a hand-over is `route`, a question is `ask`). Only the dispatcher sends tasks. Exceptions: during install the programmer may message the sessions it starts, and any session may send the dispatcher "Start the watcher".

The owner stops or starts the team with one word to any team session:
- "stop" → `agentq pause "<owner's words>"` – the watcher keeps running but sends nothing;
- "go" → `agentq resume`; when it says the watcher is not running, send the dispatcher it names "Start the watcher" yourself.
The owner never has to message the dispatcher. Never ask the dispatcher to stop its watcher.

## Codex and other agents

A role can run outside the Claude desktop app (`agentq role <name> --agent codex`). Nobody sends it tasks; it pulls them:
1. `agentq next <role> --wait --as <your name, e.g. codex-1>` – waits without tokens (up to 9 minutes; then run it again) and prints your task;
2. do it and finish with the same commands as everyone (`agentq done` shows the owner's new words first if there are any);
3. back to 1.
Such a project points AGENTS.md at this skill (`agentq init --codex`).

The whole team can move: the owner says e.g. "the team goes to Codex" → `agentq team codex` and do what it prints (a Codex task in the dispatcher folder reads AGENTS.md there and loops on `agentq watch --max-minutes 9`; one Codex task per role worker loops on `agentq next`). The Claude dispatcher stops by itself at its next watch. Back: `agentq team claude`.

## The owner's words

- A question or an idea is not a decision. Answer critically: where you disagree, why, cost, risk, a better option. Change nothing until they say so.
- A clear word ("do it", "defer", "won't do") is a decision. Record it with their exact words (`agentq defer N "…"`).
- When a change alters text agents read, tell the owner which rule changed (was → now).

## Teaching

`agentq teach "banners → designer"` – anyone may teach; add `--owner` when the owner said it. The owner's rules outrank agents'. A rule that contradicts one of the same rank is not written; it becomes a question to the owner.

## GitHub

- Write only through the AI account, never as the owner. Every comment starts `🤖 <role>:` (agentq does it).
- Change states only with agentq: one command does comment and labels together.

## Releases and tokens

- A release happens only after a check says GO and the owner says ship. Multi-agent reviews only when the owner asks.
- Before each step ask: is it needed, is there a cheaper way, is someone already doing it?

## Install (per project, by the programmer session, with the owner)

Only when the owner asks for it in words in this project. A session never starts or re-runs the install on its own, not even when it sees the skill or config change.

0. In the project: `<package>/tools/agentq init --owner <owner's login>` – this project's own config, the skill linked into this project only.
1. Check: `agentq setup` checks `gh`, the AI account signed in and active, Write access. Show the owner what is missing; only the owner signs in. Re-run until it passes.
2. Labels: the passing `agentq setup` creates them (working, question, deferred, waiting, priority, blocking, hard, waits for owner's word, each role, each checker's `checked: <role>`), with the dispatcher folder.
3. Sort the open issues: `agentq assign N <role> --queue` (label only), `agentq defer N "…"`. Unclear ones go to the owner as one list.
4. Config: the roles table (`agentq roles`; change a role with `agentq role <name> …`).
5. Sessions: you are the programmer (`agentq role programmer --session <your id>`). Start the checker session in this project and the dispatcher session in the dispatcher folder (mid model such as Sonnet, low effort, prompt "Read CLAUDE.md and start the loop"); every other session on the strongest model at `xhigh`; the dispatcher's folder is outside the project because a project subfolder would still load the project's CLAUDE.md and rules. Record them: `agentq role checker --session <id>`, `agentq role dispatcher --session <id>`. The app asks the owner to approve each new session once. All team sessions run in the same permission mode, or messages wait for approval.
   Then put every team session (yours included) into one sidebar group named after the project, e.g. "<project> team" in the config's language: reuse a group with that name or create it (`create_group`), then `move_sessions`. Record it: `agentq setup --group <group id>`, so a re-run puts recreated sessions into it.
6. The dispatcher starts the watcher itself. Add an hourly health timer (launchd or cron): `<package>/tools/agentq --config <config> health` – no tokens; problems go to one issue for the owner.
7. Ask: "Turn on the marketer?" Yes → start its session, `agentq role marketer --session <id>`. No → the programmer does marketing tasks.
8. Ask: "Add more roles?" For each: name, what it does with 2–3 example tasks (optional screenshot), mode (programmer / checker with N and paths), merge or hand to the programmer (model and effort: the strongest at `xhigh` unless the owner says otherwise) → `agentq role <name> --description "…" --example "…" [--shot file] --mode … --model … --effort … --merge yes|no`; start its session; record `--session`. If it overlaps a role, ask the owner where the border is → `agentq teach --owner "…"`. Repeat until no. Several sessions doing the same job are one role with a pool, never a second role per extra session.

## Test mode

The owner says which, in one word → `agentq tests per-task` or `agentq tests batched`. Per-task: each task runs the whole suite before it finishes. Batched: each task runs only what touches the change (the test that fails without the fix, the nearest unit tests, one or two related end-to-end tests); the watcher runs the whole suite itself every `tests.every` tasks in its own checkout, and a red run wakes the checker with the commits since the last green one. The brief says which mode applies.

## How many work in parallel

The owner says e.g. "10 programmers" → `agentq scale <role> 10` and do what it prints: start each missing session with the printed number in its title (the owner asked, so start them yourself), move it into the team's sidebar group, record it with `agentq role <role> --add-session <id>`. Fewer ("3 programmers") → `agentq scale <role> 3`: the rest get no new tasks and finish what they hold. Never archive or delete them: the next "more" reuses them first (unarchive one if the owner archived it).
9. When the team runs in another project too, ask: "Share tasks between the projects?" Yes → in each project `agentq link other/repo "what belongs there"`.

Models: every role runs on the strongest model at extra-high effort (`xhigh`; `max` for a *hard* issue); only the dispatcher runs on a mid model at low effort (the cheapest kept doubting its plans). Use ids from the app's model picker. The dispatcher switches a session's model or effort per task (a *hard* issue, a release check); without asking the owner only in bypass permission mode – otherwise leave `hard_effort` and `release_model` empty.

Re-running install creates nothing that exists: `agentq setup` shows the roles table; start sessions marked MISSING or archived again, record them and move them into the sidebar group; after a reboot or an app restart send this project's dispatcher (its id is in the table) "Start the watcher".
