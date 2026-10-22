# Changelog

## 0.3.7 – 2026-10-22
- `agentq tests off`: no tests at all – every brief tells the programmer to run no tests or check builds, read the change once quickly and finish; the watcher starts no full runs; the checker's batches still check the finished tasks.

## 0.3.6 – 2026-10-21
- A role nobody can take is said at once: `agentq team` and `agentq scale` name the roles with no working Claude session and no Codex worker the watcher can wake, and the hourly health check reports such a role when its tasks or a check batch wait. A Codex worker that never reported back (the owner's own Codex conversation that once ran `agentq next`) does not count. After "Claude off" a project's checker had no Codex worker for five hours, and nothing said so.
- A red full test run becomes a task for the checker role when no Claude session works it (Claude off, or a Codex dispatcher), instead of a message to a Claude session that should not spend tokens on it – or, from a Codex dispatcher, no word at all.

## 0.3.5 – 2026-10-21
- Comments the owner can read on a phone: a text of more than one line starts below the `🤖 <role>:` signature, so its Markdown renders; any text argument may be `-` to read it from stdin (a heredoc); the skill and every brief say how to lay a comment out – the result or the question first, a numbered choice with the recommended option first, paths and commits last. A worker's question to the owner had come as one long paragraph.

## 0.3.4 – 2026-10-21
- Every file agentq rewrites (state, board, delivered marks, lessons, config) is first written to a temporary file of its own process. A Claude and a Codex watcher of one project (dispatcher agent `both`) wrote the board through the same temporary file, so one moved the other's copy away and crashed.
- Since 0.3.3, also: checker batches are pinned to published commits, and a batch checks that the commit closing each task is in it.

## 0.3.3 – 2026-10-21
- "Claude off" (`agentq team codex`) now rests every Claude session of the team: before, a Claude session in a role's sessions kept taking tasks itself, because only `scale` made it rest.
- A watcher and a waiting worker (`agentq next --wait`) restart when their config changes, as they already did when agentq changed: `team`, `scale` and `role` reach a loop that read the config before (a Claude session waiting since before the change kept the old settings until it restarted).

## 0.3.2 – 2026-10-20
- Moving an issue releases its old local holder after the transfer (or copy and close) succeeds. `next` also recovers a stale holder whose issue was moved or deleted: it takes the next task or stops normally when none waits. Other workers' claims stay intact; an unknown read, network failure or lost repository access keeps the claim.

## 0.3.1 – 2026-10-20
- `agentq init --like <config>`: a second computer takes the first computer's team – owner, AI account, repos, labels, texts, roles, rules, links – in the team's language, without that computer's folders, sessions, test runs and running copy. Before it, `init --second` started from the example's English labels, and a team that works in another language had to be copied by hand.

## 0.3.0 – 2026-10-20 – the first audited baseline

What agentq and the skill are, after four days of building them against a live team (0.1.0–0.2.84 below, one entry per fix):

- **The loop.** The owner writes GitHub issues. A watcher reads the board every minute without tokens and wakes the dispatcher only with a plan; the dispatcher sorts new issues to roles and sends or queues tasks. A worker takes a task (`agentq next` or a dispatcher's message), reads it (`brief`) and finishes it with exactly one command (`done`, `ask`, `route`, `handover`, `wait`, `move`, `split`) that changes comment and labels together.
- **Two teams.** Every role can be worked by Claude sessions, Codex workers or both; they compete for tasks through claims on GitHub, take turns, and a task can be kept for one team. A Codex worker never waits in a command: the watcher claims its next task and wakes it with one queued message.
- **Checks.** Per-task or batched tests; a checker role checks finished tasks in batches and opens linked tasks for what it finds; a release role owns release candidates; one role may restart the owner's running copy of the program.
- **Health.** Stuck tasks are reminded and then reported, the owner's new words reach the worker holding the task, waiting tasks come back when what they wait for closes, old worktrees are removed, low disk is reported – in one issue per computer.
- **Anywhere.** Per project, in the config's language, on macOS, Linux and Windows, from one or two computers.
- **Code.** `tools/agentq` runs `tools/agentq_lib/` (one module per part, see docs/DESIGN.md "Code layout"); standard library only; 81 tests against a fake `gh` on macOS, Linux and Windows, plus pyflakes in CI. What it reads from the Claude and Codex apps, and what happens when that changes: docs/DESIGN.md "What agentq reads from the apps" – every such read now fails safe.
- In this release: the code split into modules (every definition moved unchanged, checked against the old file's syntax tree); the Codex unlock on Windows imported its module (it would have failed there); app files of an unexpected shape, or vanishing while read, count as unknown instead of raising.

## 0.2.84 – 2026-10-20
- The install steps and model settings moved from SKILL.md to INSTALL.md beside it: every session reads the skill, only an install needs the steps – the skill is about 40 % shorter.

## 0.2.83 – 2026-10-20
- The skill read through again: the scale paragraph no longer mixes in which team takes a task (its own section now), a resting worker is told to stop, Windows' command form, the team labels in setup, a project without a checker. `agentq handover --owner` for the owner's word that the other team does a task. The README lists every command.

## 0.2.82 – 2026-10-20
- Three tries and a task still fails: the worker stops and runs `agentq handover N "what I tried"` – the task gets the other team's only-label (Claude ↔ Codex), its claim ends, and the other team takes it with the notes. Every brief says so. A Codex programmer spent four hours and eleven versions on one flaky-test task.
- A task kept for Claude in a role with no working Claude session (`scale 0`) goes to a free resting session (`assign --session`), and the owner's words and reminders reach a Claude session that holds such a task.

## 0.2.81 – 2026-10-20
- agentq runs on Windows: a portable file lock (msvcrt), `shutil.disk_usage`, `taskkill /T` for a test run past its time, Windows process checks instead of `pgrep`/`lsof`, a restart into a new version without `exec`, the Claude app's sessions under `%APPDATA%`, UTF-8 for gh, git and its own output, a junction or a pointer file where symlinks are not allowed, and the commands it prints for the agents in a form Git Bash, PowerShell and cmd run. Git exclude patterns use `/` everywhere.
- The same project from two computers: `agentq init --second` makes a computer serve only its own sessions and Codex workers (`"primary": false`); sorting, full test runs, batches, handing back answered or waiting tasks, PR checks and others' stuck tasks stay with the first. A task in progress whose last claim names another computer is never reminded, released or counted against this computer's sessions. Each computer reports its health in its own issue.
- CI runs the tests on Linux and Windows; the fakes are Python scripts (`AGENTQ_GH`, `AGENTQ_CODEX`, `AGENTQ_OPEN`), so the tests need no shell.

## 0.2.80 – 2026-10-20
- A claim made before a task was handed back (`agentq route`) no longer counts: for ten minutes it kept anyone else from taking the task.

## 0.2.79 – 2026-10-20
- A task the owner keeps for one team: `agentq assign N <role> --only claude|codex` adds the `only claude` / `only codex` label, and the other team's workers never take it nor get woken for it – Codex programmers took a Claude-only task five times, each handing it back. `--session <id>` gives a task to a named Claude session of the role, even one that rests (`scale`).

## 0.2.78 – 2026-10-19
- The skill names `agentq scale <role> 0` and says to run a command rather than answer from memory – a dispatcher told the owner 0 was impossible after it had become possible.

## 0.2.77 – 2026-10-19
- The comment a worker takes a task with names it as the owner sees it: its Codex task's title or its Claude session's title (`🤖 programmer · codex (Codex programmer 2): taking this.`); a task the dispatcher sends to a session names that session.

## 0.2.76 – 2026-10-19
- A Claude session that is not one of a role's working sessions takes no new task, also when it runs `agentq next` under a name instead of its session id, and none when the role is scaled to 0 – one such session kept taking tasks after the owner left no Claude programmer.

## 0.2.75 – 2026-10-19
- `agentq assign` for a role whose free session waits in `agentq next` only queues the task: it set the working label and a claim first, so the task looked taken and nobody took it (a task sat locked for 36 minutes).

## 0.2.74 – 2026-10-19
- `agentq scale <role> 0` for a role Codex workers also pull: no Claude session works on it (none gets a task, the dispatcher sends none), its Codex workers take every task.

## 0.2.73 – 2026-10-19
- A Claude session that `agentq scale` rested takes no new task in `agentq next` (it is told to stop), and a Claude session leaves a role's next task to an idle Codex worker when Claude took the last one – with one Claude programmer left, the resting sessions kept taking tasks while three Codex programmers stood idle.

## 0.2.72 – 2026-10-19
- The watcher puts a waiting task (`agentq wait`) back in the queue once the issue it waits for is closed, checked every 10 minutes – only `check --fix` did that, and a task waited 17 hours for an issue of the linked project closed long before.

## 0.2.71 – 2026-10-19
- `agentq live <role> "<cmd>" --when checked`: the checker restarts the owner's running copy after every check on the commit it checked, even when some tests failed (not when it does not build or start) – the owner tests on it too.

## 0.2.70 – 2026-10-19
- `agentq health` removes the project's worktrees whose work is already in main: clean, untouched for `worktree_idle_hours` (12; 0 turns it off), with no process in them; the branch stays. A Claude session's own worktree is left to the app – 193 old worktrees had piled up.

## 0.2.69 – 2026-10-19
- `agentq batch` for a checker that already has its batch says "nothing to do" instead of failing – a pulling tester made its batch seconds after the plan said one was ready.

## 0.2.68 – 2026-10-19
- A task is the owner's order: every brief says to do it to the end without asking whether to; a question about something wrong is a defect to fix; `agentq ask` only for a choice that is the owner's; sign-off skills (brainstorming) do not apply to team tasks – Codex workers stopped to ask "shall I fix it?".

## 0.2.67 – 2026-10-19
- Codex workers start on a named model: config `codex_model` (a role's `--codex-model` wins), shown in each `agentq codex-workers` block – workers created with `create_thread` had taken the app's default model.

## 0.2.66 – 2026-10-18
- `agentq open <role> … -R other/repo` opens a task in a linked project (without labels, naming the role; that project's dispatcher sorts it) – a programmer could not hand the website's marketer a task.

## 0.2.65 – 2026-10-18
- Every command accepts `--as <role>` (agents add it out of habit; `agentq checked … --as testuotojas` failed).

## 0.2.64 – 2026-10-18
- Workers clean up: every brief and the skill say to delete what was made for the task outside the project (scratch copies, test checkouts, worktrees, build output) before finishing, never anything else.
- The hourly health check reports when free disk space falls below `disk_min_gb` (default 30 GB).

## 0.2.63 – 2026-10-18
- One health issue, even when two problems are reported in the same minute (GitHub's list did not show the issue created a moment before, so a second one was opened).

## 0.2.62 – 2026-10-18
- When a task the owner was told is stuck moves on (its session woke up, or it got finished), the watcher says so on the health issue at once and closes it when nothing else is wrong – the owner no longer finds a stale alarm.

## 0.2.61 – 2026-10-18
- A Claude session's activity also counts the app's own last-activity time, not only its transcript: a session running a long test run looked quiet and its tasks were released while it worked.

## 0.2.60 – 2026-10-18
- `agentq take` (resuming a task, e.g. after the owner answered in chat) removes the waiting-for-the-owner label and records the session or Codex task as the holder – seen live: a Codex worker resumed a task that kept "needs you", and with no holder the reminders would have gone to a Claude session.

## 0.2.59 – 2026-10-18
- The release role owns the release cycle: candidate tag `-rc1` on the approved commit, its own full check there, fixes through linked programmer tasks, a new `-rcN` checked again in full, GO only for the final candidate (from a Codex review of the release flow).

## 0.2.58 – 2026-10-18
- A brief starts with the role's own description, so a long-running session follows its role's current rules on every task.
- Releases go by a candidate tag: the approved commit is tagged (`candidate-1.2.3`), checked at that tag and built from it on GO; the release tag goes on the same commit.

## 0.2.57 – 2026-10-18
- The owner's words on a set-aside task (deferred, waiting for another project, …) bring it back: the plan says `agentq assign N <role> --unpark`, which drops those labels, and the role reads the words and decides – before, such comments went nowhere.
- The skill: a release is built from exactly the commit the check said GO on, never from a newer `main`.

## 0.2.56 – 2026-10-18
- "3 programmers" in Codex: `agentq codex-workers 3 --role <role>` lists the missing Codex workers of one role (codex-<role>, codex-<role>-2, …) to create with `create_thread`; `agentq scale` stays for Claude sessions (a Codex dispatcher had used it and rested a Claude session).

## 0.2.55 – 2026-10-18
- Two lives, the tickets between them: a Codex dispatcher's plan only sorts (classify, answered) and its `assign` only queues – it never takes a task for a Claude session it cannot reach; `assign` of a task the other dispatcher already started does nothing.

## 0.2.54 – 2026-10-18
- A Codex worker whose task the owner archived or deleted is never woken, so no task waits on it. To keep Codex off a role: `agentq role <role> --agent claude`, then archive its Codex task.

## 0.2.53 – 2026-10-18
- Codex workers get the role's reasoning effort (extra high by default): `agentq codex-workers` names it per worker and the skill passes it to `create_thread` (the first ones ran at Codex's default, medium).

## 0.2.52 – 2026-10-18
- Codex workers are created like Claude sessions: `agentq codex-workers [count]` lists a title and a first message per missing worker, and a Codex task in the app creates each with its `create_thread` tool – listed under the project, started at once, no clicks (found by a Codex investigation).

## 0.2.51 – 2026-10-18
- From the second Codex review: a wake message Codex may have accepted (queued, or no answer in time) is never undone or sent again – only a refused one puts the task back; a quiet Codex worker gets a reminder and the owner is told, but its task is no longer taken away by its rollout file's time alone.
- `agentq codex-workers` prints the text for each missing Codex worker: only the owner can create a Codex task listed under the project (drafts opened from outside replaced each other).

## 0.2.50 – 2026-10-18
- From a Codex review of the Codex part: a wake that fails is undone (the task back in the queue, the worker idle again); `codex queue`, `open` and `lsof` have time limits and a failed `open` is reported; a Codex dispatcher's watcher is reported running only once it holds its lock; an archived or deleted Codex worker counts as missing for `codex-workers`; paths and role names in Codex commands are shell-quoted; the skill says a team Codex task needs full access.

## 0.2.49 – 2026-10-18
- One Codex task is one worker: registering it under a new name replaces the old name, so the watcher never wakes one task for two tasks.

## 0.2.48 – 2026-10-18
- `agentq codex-workers` opens the Codex worker tasks one by one, listed under the project like Claude's sessions: the Codex app holds one new-task draft at a time, so the next draft opens by itself when the worker before it starts. No codex-bridge needed.

## 0.2.47 – 2026-10-18
- `assign` no longer sends a task to a session that waits in `agentq next`: it queues it and that session takes it itself (seen live: a programmer held two tasks at once – one pushed, one pulled).

## 0.2.46 – 2026-10-18
- `agentq live <role> "<command {sha}>"`: one role (usually the checker) restarts the owner's running copy after a check says GO, on the last green commit; every other role's brief says never to restart it. Off by default and with `--off` – for a program that runs on another machine or deploys itself. The install asks about it.

## 0.2.45 – 2026-10-18
- A Codex task never waits in a command: Codex checks a running command with a model call every minute (one worker waiting 45 minutes cost 17M input tokens). A Codex worker with no task ends its turn; the watcher claims its next task and queues one message for it (`codex queue`; an unloaded task is opened in the background). Reminders for a quiet Codex worker go the same way. A Codex dispatcher's watcher runs on its own and sends each plan as a message.
- Claude sessions and Codex workers waiting for the same role take turns.
- The watcher and `agentq next --wait` carry on in a new agentq version without waking anyone.
- The state file is saved with a three-way merge under a lock, so concurrent writers no longer drop each other's changes (a worker's task, the owner's pause).

## 0.2.44 – 2026-10-18
- Every worker pulls: a Claude session runs `agentq next <role> --wait` in the background after each task and is woken with the next one; the dispatcher sends tasks only to sessions that are not waiting, so it wakes far less (the owner's rule: no more requests than one session doing everything). Waiting workers use the watcher's board snapshot; a worker's own held task is checked on GitHub.
- Team labels: a task gets `claude` or `codex` when taken; comments say which team wrote them; `agentq stats` compares the teams (tasks, hours from taking to closing, problems found later).
- Briefs and the skill: never message other sessions or offer to take part of someone else's task; no work means waiting in `agentq next`.

## 0.2.43 – 2026-10-18
- Claude and Codex compete for the same roles: a role's agent can be `both`; the dispatcher sends to free Claude sessions while Codex workers pull, and a task a Codex worker holds does not make the Claude sessions busy. `agentq team claude|codex|both` moves the work between them (the dispatcher keeps running in every mode); `agentq codex-workers` opens one prefilled Codex worker per role.
- The Codex install asks "together with Claude, or alone?" and defaults to together; it never moves roles away from Claude on its own.

## 0.2.42 – 2026-10-18
- `agentq codex-workers N`: opens the missing Codex worker tasks in the Codex app, prefilled (codex-bridge), numbered; the owner presses Send. The Codex install asks how many workers and runs it.

## 0.2.41 – 2026-10-18
- An install run in Codex always does the Codex part of step 5, even when the team already runs on Claude: it asks which roles work in Codex, switches them, and starts working.

## 0.2.40 – 2026-10-18
- One Codex worker for the whole team: `agentq next --wait` without a role takes the next task of any pulling role (priority first).
- Install in Codex as in Claude: one line, the same steps and questions; step 5 makes the roles pull, opens a Codex dispatcher task when there is no Claude one, and the installing task becomes the first worker ("Join the agent team in this project" adds more).

## 0.2.39 – 2026-10-18
- Several dispatchers at once: `agentq team both` lets a Claude and a Codex dispatcher run side by side (one watcher lock each); the owner's words are forwarded only by the computer whose claim holds the task; a stale-PR task already on the board is not opened again; the full test suite runs only on `tests.host` when set.

## 0.2.38 – 2026-10-18
- Safe across computers: `next` and `assign` claim a task with a marked comment, read it back and keep it only when theirs is the earliest claim of the last 10 minutes; a loser deletes its claim and takes the next task. Workers on any number of computers, and even two dispatchers, never share a task.

## 0.2.37 – 2026-10-18
- The whole team can run on Codex: `agentq team codex|claude` switches the dispatcher and every role; a dispatcher running on the other agent stops at its next watch. The dispatcher folder gets an AGENTS.md for a Codex dispatcher, which loops on `agentq watch --max-minutes 9`.

## 0.2.36 – 2026-10-18
- `agentq next` refuses a role that does not pull (agent: claude) and tells the loop to stop, so a role switched back to Claude never has two workers.

## 0.2.35 – 2026-10-18
- An urgent word from the owner (`priority_words`, default the priority label's name, e.g. SKUBU) in an issue's title, text or a comment gives it the priority label, so the next free session takes it first. Once per issue; any case; only the owner's words.

## 0.2.34 – 2026-10-18
- Codex and other agents: a role with `agent: codex` pulls its tasks with `agentq next <role> --wait [--as name]` (waits without tokens, takes the next task or its checker batch, prints the brief); the watcher plans nothing for it and `assign` only queues. `agentq init --codex` points AGENTS.md at the skill.
- `agentq done` first shows the owner's words written after the last agent comment that no brief delivered, and closes only on the next run.

## 0.2.33 – 2026-10-18
- Plain `agentq` shows its commands instead of an error.

## 0.2.32 – 2026-10-18
- `agentq open <role> "title" "text" [--as <role>]`: a new task for a role, with its label – checkers' findings, or a watcher role handing real failures to the programmer.

## 0.2.31 – 2026-10-18
- Clearing the dispatcher is off by default (`clear_every` 0): in the live test, a watcher started before the clear woke nobody when it ended, and the team stood still. It stays available for when a safe order is found.

## 0.2.30 – 2026-10-18
- Removing a role removes its rules and lessons; roles.md never shows a rule for a role that no longer exists.

## 0.2.29 – 2026-10-18
- Run from a folder outside the project (a session's scratch folder), agentq finds the project's config through the session that ran it.

## 0.2.28 – 2026-10-18
- Every `clear_every` (20) plans the plan ends with "then call clear_session with session_id \"self\"": the dispatcher empties its own conversation (the owner's word, written into its CLAUDE.md), so each wake no longer re-reads hundreds of thousands of tokens of history. Its Remote Control must be off for the app to allow it.

## 0.2.27 – 2026-10-18
- Test modes (`agentq tests per-task|batched`, config `tests`): batched lets each task run only the tests that touch it while the watcher runs the full suite every `tests.every` finished tasks, detached, in its own checkout – no tokens. Green records the last green commit; red wakes the checker once with the commit range. Briefs say which mode applies; batch reports state the last full run.

## 0.2.26 – 2026-10-18
- The dispatcher runs on a mid model (e.g. Sonnet) at low effort instead of the cheapest: the cheapest kept doubting the plan's session ids instead of following it (the owner's word). It wakes only when there is work, so the cost stays small.

## 0.2.25 – 2026-10-18
- `gh` calls retry twice on a 502/503/504 or a timeout.
- A plan says "(agentq checked: it exists)" for a session the desktop app knows; the dispatcher never checks ids against list_sessions or linked-session notes.

## 0.2.24 – 2026-10-18
- A task whose session ignored the reminder goes back to the queue (working label removed, a comment says why) besides the owner's "needs you", so a free session takes it.
- Open pull requests: checked hourly; one untouched for `stale_pr_days` (3) becomes a task for the default role – finish it or close it saying what replaced it. Once per stall.

## 0.2.23 – 2026-10-18
- Plans name the target session by id only ("send this line to session local_…"); the dispatcher stopped doubting ids it remembered under another role's name.

## 0.2.22 – 2026-10-18
- `agentq scale <role> N`: N sessions of a role work in parallel. More than exist: it lists the numbered sessions to start (in the team's sidebar group) and `role --add-session` records them. Fewer: the rest rest – no new tasks, never deleted – and are reused first when the number grows again.

## 0.2.21 – 2026-10-18
- Fewer tokens in coordination: the dispatcher sends a role one line ("run agentq brief N and act on it") instead of reading and re-sending the whole task; the role reads the task itself, once. Reminders are one line in the plan too.

## 0.2.20 – 2026-10-18
- A role may have several sessions (`agentq role <name> --sessions a,b,c`): one label and queue, one task per session. The watcher plans as many tasks as there are free sessions; `assign` picks a free session and records it, so forwarded words, reminders and model or effort changes go to the session that holds the task.

## 0.2.19 – 2026-10-18
- The dispatcher's CLAUDE.md: read the ended watcher's output file first, every time; never assume what it says or that a watcher still runs.

## 0.2.18 – 2026-10-18
- A watcher started with `&` or nohup (its parent gone) stops at once: its end would wake nobody and the team would stall silently. The dispatcher's CLAUDE.md says to start it only with run_in_background.

## 0.2.17 – 2026-10-17
- The dispatcher's CLAUDE.md: one command per call; never chain a command whose number an earlier one has not printed yet.

## 0.2.16 – 2026-10-17
- Stalled roles: a role that holds a task while its session has been quiet for `idle_minutes` (20) gets one reminder (`agentq nudge`); quiet for `escalate_minutes` (30) more, the owner is told in the health issue with the question label. The watcher reads a session's last activity from the desktop app's transcript, without tokens; where it cannot, the dispatcher checks with get_session every `check_minutes` (60) via `agentq held`.
- `health` comments only when the problems change; an hourly timer is fine.
- A running watcher exits when agentq is updated, so the dispatcher restarts it on the new code.

## 0.2.15 – 2026-10-17
- The first watch (no delivery record yet) forwards only owner words on an open issue that waits for the owner or is in progress and that no agent comment followed; everything else counts as delivered, so a pause or an upgrade loses no answer and floods nothing.
- An owner's comment stays in the plan until a `brief` delivers it (up to `forward_hours`, 24): a plan the dispatcher missed, or a comment written while no watcher ran, is no longer lost; the plan wakes the dispatcher again every `repeat_minutes`.
- A working label set by someone other than the agent account (e.g. the owner's own tools) no longer makes a role busy.
- The owner's answer on an issue waiting for the owner's word (the question or the owner-word label, also when both are one label) puts it back to its role; `assign` removes both labels.

## 0.2.14 – 2026-10-17
- Stop and go in one word: the owner says "stop" or "go" to any team session; it runs `pause` / `resume` and, if needed, tells the dispatcher "Start the watcher" itself.

## 0.2.13 – 2026-10-17
- The dispatcher makes sure its watcher runs whenever it wakes (a plan, a message, a notice that a command was stopped, e.g. after an app restart), and starts it on a "Start the watcher" message from any team session.
- `resume` says when the watcher is not running and whom to tell. `health` raises no alarm during a pause, only for one older than `stale_hours`.

## 0.2.12 – 2026-10-17
- The plan and the dispatcher's CLAUDE.md: do every step without asking anyone; the session ids are current even when they differ from earlier ones; always restart the watcher after a plan.
- The dispatcher's CLAUDE.md is agentq's own: `setup` and `role` rewrite it from the template (keeping its session id); other files in its folder are left alone.

## 0.2.11 – 2026-10-17
- `agentq pause "why"` / `agentq resume`: any session can pause the team on the owner's word; the watcher stays up and sends nothing. No session has to ask the dispatcher to stop its watcher.

## 0.2.10 – 2026-10-17
- Screenshots go to `~/.cache/agentq/shots` (or `shots_dir`), never beside a config that may live in a git repository.

## 0.2.9 – 2026-10-17
- `brief` downloads images linked from a repository (`github.com/o/r/raw/…`, `raw.githubusercontent.com/…`) through `gh` as the AI account; when the account cannot read that repository, it says so (the owner invites it with Read).

## 0.2.8 – 2026-10-17
- The skill: team sessions never message each other; the board carries hand-overs and questions. Only the dispatcher sends tasks.

## 0.2.7 – 2026-10-17
- Every role runs on the strongest model at extra-high effort (`xhigh`, `max` for *hard* issues); only the dispatcher stays on the cheapest. Defaults, the skill, README and design updated.

## 0.2.6 – 2026-10-17
- Install step 5: every team session goes into one sidebar group named after the project; `agentq setup --group <id>` records it and the roles table shows it. The skill says why the dispatcher's folder is outside the project.

## 0.2.5 – 2026-10-17
- `--config` works after the command too (`agentq init --owner X --config file`).
- `teach "topic → role (note)"`: the role is the name the text after the arrow starts with; a note may follow it.

## 0.2.4 – 2026-10-17
- `brief` includes the note of the role that handed the task over with `route` (e.g. "merge branch …"), so the next role gets it without reading the thread.

## 0.2.3 – 2026-10-17
- The skill: install only when the owner asks for it in words in that project; a session never starts it on its own.

## 0.2.2 – 2026-10-17
- Plans and `assign`/`batch` name each session with its role: "send … to programmer (local_…)", "set_session_effort for programmer (local_…): max".
- The dispatcher's CLAUDE.md states its own session id and that every id in a plan is a role session, never its own. `setup` and `agentq role dispatcher --session` write it, also into a CLAUDE.md made by 0.2.0/0.2.1.

## 0.2.1 – 2026-10-17
- `assign --queue` (sorting at setup) adds the role label only and drops another role's label; it never removes a skip label such as the question for the owner.
- `role --hours 24` stores a whole number; the roles table shows `5/24h`.

## 0.2.0 – 2026-10-17
- New team design (docs/DESIGN.md): a cheap dispatcher sends tasks, the programmer is the default role, a checker checks batches, a ready-made marketer, owner-defined roles in programmer or checker mode.
- `agentq watch`: polls the board every minute without tokens and prints a plan when there is work; ignores the AI account's own comments.
- `assign`, `brief` (the task verbatim, the owner's comments, screenshots as local files), `done`, `route` (teaches the dispatcher; last 5 examples per role), `teach` (owner rules outrank agent rules; a contradiction becomes a question to the owner), `batch` / `checked` (checker batches of N or 24 h, optional path filter, pinned commit), `health` (one issue for the owner).
- Install per project: `init` (own config, skill link, git exclude), `setup` (access checks, labels, roles table, dispatcher folder from `templates/dispatcher`), `role`, `roles`.
- Sharing between projects: `link`, `move`, `split`.
- All label names and texts come from the config. README in English.

## 0.1.3 – 2026-10-17
- The skill no longer says how a session handles its context; that belongs to the tools, not the rules.

## 0.1.2 – 2026-10-17
- A session no longer clears itself; a long context is compacted instead. State still goes to the issue, a file or memory after each task.

## 0.1.1 – 2026-10-17
- A session clears its own context after each task; the owner never has to.

## 0.1.0 – 2026-10-17
- Skill `agent-team`: roles, one session per role, the owner's words, the task queue on GitHub issues, a separate AI account, releases, tokens.
- `tools/agentq`: `queue`, `take`, `ask`, `defer`, `wait`, `check [--fix]`, `setup`; per-project `.agentq.json`.
