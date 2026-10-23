# Agent team – design

Agreed with the owner while building 0.2 and 0.3. This is the build spec; `skill/agent-team/SKILL.md` is the short version agents read (`INSTALL.md` beside it for an install). Scope: one project at a time, installed per project (never globally); projects may share tasks (below).

## Team

Three core roles exist in every project:

| Role | Model | Effort | Job |
|---|---|---|---|
| Dispatcher | mid (e.g. Sonnet) | low | Watches the board through a script and sends tasks. Never codes, never interprets the owner's words. |
| Programmer | strongest | extra high (issues labelled *hard*: highest) | Default role: every task nobody else owns. The only role that interprets the owner's words. |
| Checker | strongest | extra high | Checks batches of finished tasks. The full release check runs only on the owner's word. |

Every role, the marketer and owner-defined roles included, runs on the strongest model at extra-high effort (the owner's word, 2026-10-17); only the dispatcher runs on a mid model at low effort. It started on the cheapest; that one kept doubting the plan's session ids instead of following it, so the owner moved it to a mid model (2026-10-18). It wakes rarely, so this costs little.

The owner is not a role: everyone works for them.

**Ready-made extra role: marketer** (strongest model, programmer mode). Setup always offers it. If the owner says no, the programmer does marketing tasks too. A marketer prepares posts, ads and campaigns; anything public or paid happens only on the owner's word.

**Owner-defined roles.** At the end of setup (and any time later, in words) the owner may add roles. Each role has: name, description with 2–3 example tasks (optionally a reference screenshot), mode, model, effort, and whether it merges its own changes or hands them to the programmer.

When a new role overlaps an existing one (e.g. designer and marketer both claim banners), setup asks the owner where the border is and records it as a teaching rule.

A role may have several sessions (a pool, e.g. five programmers): one label, one queue, one task per session; `assign` records which session holds which task.

## Modes

- **Programmer mode** – gets one task at a time carrying its role label, does it, closes it.
- **Checker mode** – wakes when at least N finished tasks are unchecked by this role, or the oldest has waited 24 h. Optional path filter: only tasks whose changes touched these paths (so a rules reviewer does not wake for tasks that never touched rules). Each checker-mode role has its own `checked: <role>` label, so two checkers never share a batch. Findings become new issues that link the original; the original is not reopened.

## Flow

1. **Watcher** (`agentq watch`, run in the background by the dispatcher) polls GitHub every minute and spends no tokens. It ignores the agent account's own comments, so agents' updates never wake anyone. It builds a plan:
   - owner comments not yet delivered (a brief delivers them; the last 24 h are kept) → forward to the role holding that issue (default: programmer); a plan the dispatcher did not act on wakes it again every 30 minutes, so a missed plan or a stopped watcher loses nothing; on an issue waiting for the owner's answer → back to its role; on a queued issue → nothing (its brief carries them); on an unlabelled one → it is classified anyway;
   - a role is **free** when no open issue carries both its role label and a working label the agent account set (one the owner's own tools set does not count); for each free programmer-mode role, the next issue: priority label → blocking label → oldest; unlabelled issues go to the dispatcher to classify;
   - checker-mode roles with a ready batch → a batch issue (`Check: #a #b #c`, pinned commit) labelled for that role.
   An empty plan means it keeps polling; otherwise it prints the plan and exits, which wakes the dispatcher.
2. **Dispatcher** on wake:
   - classifies unlabelled issues from the role descriptions, examples and lessons; when the text is too thin it looks at the screenshots; when unsure → programmer;
   - `agentq assign N <role>` – role label + working label + a short comment;
   - `agentq brief N` – the issue's title, body and the owner's comments verbatim, with screenshots downloaded to local files – and sends that to the role's session;
   - starts the watcher again.
3. **Role session** on a dispatcher message: the message is the owner's queue, not chatter from another session – act on it. Finish with one command:
   - fixed → a comment on what changed and how it was checked, close (`Fixes #N`);
   - stuck → `agentq ask N "question"`;
   - not mine → `agentq route N <role>` (records a lesson for the dispatcher automatically);
   - needs another project → `agentq wait N other/repo#M`.
   A checker closes its batch with `agentq checked <batch>`, which labels every listed issue `checked: <role>`.
4. **Teaching.** `agentq teach "banners → designer"` – anyone may teach. The owner's rules outrank agents' rules; a rule that contradicts an existing one is not written but becomes a question to the owner. `route` keeps the last ~5 examples per role, so the dispatcher's notes stay short.
5. **Stalled roles.** A role that holds a task while its session has been quiet for 20 minutes gets one reminder; if it stays quiet for 30 more, the task goes back to the queue (a free session takes it) and the owner is told in the health issue ("needs you"). An open pull request untouched for 3 days becomes a task for the programmer: finish it or close it saying what replaced it. The watcher sees a session's last activity without tokens (the desktop app's transcript file); where it cannot, the dispatcher checks with get_session once an hour.
6. **Health** (`agentq health`, hourly timer, no tokens): is the watcher alive, is any task "working" with no activity for over 24 h. Problems go to the owner on GitHub (one health issue, so the owner's phone gets notified).

Busy is read from the board, so a role never gets a second task while it works on one. A direct chat between the owner and a session is not on the board; a task message then waits until the session answers the owner.

## Tokens: no more than one session doing everything

The owner's rule (2026-10-18): the team must not spend more model requests on the same work than one session would. So every worker pulls, and no agent ever waits inside a command that costs tokens:

- **Claude:** after a task a session runs `agentq next <role> --wait` as a background command. The session's turn ends; the command waits without tokens and wakes it when its task arrives.
- **Codex:** Codex checks a running command with a model call about every minute. Measured on 2026-10-18: one 12-minute `agentq next --wait` cost 28 model calls (716k input tokens); a worker waiting 45 minutes cost 137 calls (17M input tokens, nearly all cached). So a Codex worker never waits: with no task it ends its turn. The watcher claims its next task for it and queues one message for its Codex task (`codex queue --thread <id>`); the Codex app runs it as soon as the task is idle. A task the app has not loaded (after an app restart) is opened in the background (`open -g codex://threads/<id>`), which loads it and runs the message without taking focus. With Codex closed, its workers get nothing, so the task waits for Claude. A Codex worker that ends its turn after finishing, without asking for more, is still woken: `done` marks it finished, and once its task has been quiet for two minutes the watcher treats it as idle. When it goes quiet holding a task (seen from its rollout file), the reminder is a queued message too; if it stays quiet the owner is told, but the task is not taken away – a file's time cannot tell a stopped worker from a long silent command. A wake whose message Codex may have accepted is never undone or sent again, so one task never gets two takers. A Codex dispatcher's watcher runs on its own and sends each plan to the dispatcher's task as a message.

Taking a task therefore costs one turn, as it would for a lone session. The dispatcher is woken only to sort new tasks into roles, pass on the owner's words and nudge a quiet Claude session; it sends tasks only to sessions that are not waiting. When Claude sessions and Codex workers both wait for a role, they take turns. Waiting workers read the watcher's board snapshot instead of asking GitHub themselves. A loop that waits (the watcher, `agentq next --wait`) carries on in a new agentq version without waking anyone.

Several processes write the state file (the watcher, workers, the dispatcher's commands). Each save is a three-way merge under a lock, so a save keeps what others changed meanwhile, such as a task a worker just took or the owner's pause.

## Claude and Codex

Two lives, the tickets between them (owner, 2026-10-18): the Claude team (its dispatcher and sessions) and the Codex team (its dispatcher and workers) run side by side and never message each other. Both dispatchers sort the same new issues – the first `assign` wins, the second sees the task taken – and the workers of both compete for tasks through claims. The Codex dispatcher's plan holds only sorting steps, and its `assign` only queues: it cannot reach Claude sessions, so it never takes a task for one.


Decided by the owner on 2026-10-18: Claude and Codex each have their own workers for the same roles and compete for the same tasks; the owner shifts the work to whichever has tokens left (`agentq team claude|codex|both`). A role's agent is claude (the dispatcher sends to its sessions), codex (its workers pull with `agentq next`) or both. Claims keep two workers from taking one task; a task a Codex worker holds does not count against the Claude sessions' capacity, and its new owner words reach it through `agentq done`. The dispatcher keeps running in every mode; Codex worker tasks are opened prefilled (`agentq codex-workers`) and started by the owner.

## Many computers

The owner asked for a universal skill that scales (2026-10-18): one dispatcher per project, workers anywhere. GitHub has no lock, so `next` and `assign` claim a task with a comment carrying a unique mark (`host/who/random`), read the comments back, and keep it only if theirs is the earliest claim of the last ten minutes; a loser deletes its claim and moves on. A claim made before a hand-back (`route`, `handover`) no longer counts. Per-computer state (who holds what, delivered words) stays local; the board is the shared truth.

The same project from a second computer (2026-10-20, a Windows PC beside the Mac): its config has `"primary": false` (`agentq init --second`). Jobs that must happen once – sorting new issues, full test runs, checker batches, handing back answered or waiting tasks, PR checks, reporting others' stuck tasks – run only on the primary computer. A task in progress that no worker of this computer holds is looked up once: when its last claim names another host, this computer never reminds, releases or counts it. Each computer reports its own health in its own issue.

## Test modes

Decided by the owner on 2026-10-18, so programming goes faster (a full suite after every task took 15–25 minutes). Per-task: each task runs the whole suite. Batched: a task runs only the tests that touch it; the watcher (a script, no tokens) runs the whole suite every N finished tasks on the newest main in its own checkout. Green records the last green commit; red wakes the checker once with the range since the last green one, to find the culprit, tell a real bug from a flaky test and open an urgent issue. The checker's batch report states the last full run.

## Sharing between projects

Decided by the owner on 2026-10-17. When the team runs in several projects, the owner may link them (`agentq link other/repo "what belongs there"` in each). Sharing is on while a link exists.

- A task that belongs wholly to a linked project: the dispatcher moves it there (`agentq move`, a GitHub transfer; a copy plus close where GitHub refuses). That project's dispatcher classifies it.
- A mixed task, or one the dispatcher cannot place: it goes to this project's programmer as usual. The programmer works out exactly what belongs to the other project, updates this task to what stays, and creates the other part with `agentq split`, which links back to the task it came from.
- The smarter session fixes what the dispatcher missed: a role may `move` or `split` too; a move by a role records a lesson for the dispatcher.

## Setup

Run once per project by the programmer session when the skill is first used there:

0. `agentq init`: this project's own config, the skill linked into this project only, both kept out of the project's git.
1. Check: `gh`, the AI account signed in and active, Write access, which accounts are the owner's. Show the owner what is missing; only the owner signs in.
2. Labels: working, question, deferred, waiting, priority, blocking, hard, waits-for-owner's-word, each role's label, each checker's `checked: <role>`.
3. Sort the open issues: role labels, deferred; unclear ones go to the owner as one list.
4. Config: the roles table (role, label, mode, N, path filter, model, effort, merge, session).
5. Sessions: the programmer is the session running setup; create the checker and the dispatcher (in its own small folder, so it starts without the project's big rules). The app asks the owner to approve each new session once.
6. Watcher in the dispatcher's background; daily health timer.
7. "Turn on the marketer?"
8. "Add more roles?" – name, what it does, mode (programmer / checker with N), model, effort, merge; repeat until no.
9. When another project has the team too: "Share tasks between the projects?"

Re-running setup creates nothing that exists: it finds the sessions from the config, recreates missing or archived ones and restarts the watcher (e.g. after a reboot).

## Verified before building (2026-10-17)

1. **Worked.** A background command that finishes wakes an idle session (60-second test). The watcher is built on it. Not tested: how long a background command may run.
2. **Worked (from the tools' descriptions).** Any session can message another by its session id (`SendMessage` or `send_message`). The message arrives as a turn labelled with the sender. A session in a different permission mode holds such messages for the owner's approval, so all team sessions run in the same mode.
3. **Worked.** The AI account downloads screenshots from a private repository: `gh api` with `Accept: application/vnd.github.full+json` returns the rendered HTML with short-lived signed image links that need no login.
4. **Not verified.** Whether a session acts on a dispatcher message can only be seen with real sessions, which this build did not create. The skill tells sessions to act on it. Try one task end to end after setup.
5. **Possible, with a condition.** `set_session_model` / `set_session_effort` switch another session from its next turn on. The app asks the owner first for a more expensive model, a higher effort or a session the caller did not start – except in bypass permission mode. So per-task switching (*hard*, release check) is silent only in bypass mode; otherwise the release check gets its own session.

## Code layout

`tools/agentq` is the one command every agent runs; the code is in `tools/agentq_lib/`, one module per part, each importing only from the modules listed before it (no cycles):

| Module | Part |
|---|---|
| `system` | macOS / Linux / Windows differences (file locks, processes, paths), how agentq is run and restarted |
| `base` | errors, time, text helpers, the marks agentq leaves in comments |
| `defaults` | default labels, texts and roles (a config replaces any of them) |
| `github` | `gh` (as the AI account) and `git`; comments, labels, claims |
| `config` | finding, loading and saving a project's config; questions about its roles |
| `state` | this computer's state: one writer at a time, merged saves, delivered words, waiting workers, the watcher lock |
| `lessons` | routing lessons, rules and the dispatcher's `roles.md` |
| `apps` | what is read from the Claude and Codex apps (below), messaging a Codex task |
| `board` | which task a role takes next, who holds what, batches, tasks waiting for others |
| `health` | the hourly check and its one issue |
| `human` | the human test stage: `handoff`, the tester's results, picked tasks kept open (docs/HUMAN-TEST.md) |
| `watch` | the watcher and the dispatcher's plan; waking Codex workers |
| `brief` | a task as a worker reads it, screenshots as files |
| `tasks` · `links` · `install` · `team` | the commands: a worker's, across linked projects, installing, the owner's words about the team |
| `cli` | the command line |

Standard library only. The tests (`tests/`) run every command against a fake `gh` on macOS, Linux and Windows (CI), plus pyflakes.

## What agentq reads from the apps

The Claude and Codex desktop apps have no API for most of what the team needs, so agentq reads some of their own files. They may change with any app update. Each read is of a file the app writes for itself; a missing file, one that vanishes while it is read, or an unexpected shape counts as "cannot be seen" and never stops agentq (`tests/test_agentq.py`, `AppsTest`).

| What | Where (macOS; Windows) | Used for | When it cannot be read |
|---|---|---|---|
| Claude session records | `~/Library/Application Support/Claude/claude-code-sessions/*/*/<id>.json`; `%APPDATA%\Claude\…` | a session's project folder, its transcript id, last activity and title; whether an id exists | no transcript-based reminder (the dispatcher asks `get_session` instead); the id stands for the title |
| Claude transcripts | `~/.claude/projects/*/<transcript id>.jsonl`, modification time only | when a session holding a task last did anything | as above |
| Codex rollouts | `~/.codex/sessions/*/*/*/rollout-*-<thread>.jsonl`, modification time only | whether a Codex task still exists and when it last acted (wakes, reminders, `codex-workers`) | the worker counts as archived and gets no task; the board loses nothing |
| Codex task locks | `~/.codex/thread-writer-locks/<thread>.lock` (`lsof`; on Windows a lock test) | whether the app has the task loaded, so a queued message runs | not loaded: after queuing, agentq opens `codex://threads/<id>` |
| Codex task titles | `~/.codex/session_index.jsonl` | the worker's name in a take comment | the worker's own name |
| Codex app running | the process list (`pgrep`; on Windows a CIM query, cached 30 s) | whether a queued message can run at all | not running: the task waits for a Claude worker or for Codex |
| `codex queue` | the Codex CLI | one message that wakes a Codex worker | the wake is undone and the task goes back to the queue, with the reason in a comment |

The dispatcher also uses the Claude app's session tools (`SendMessage`, `get_session`, `set_session_model`, `set_session_effort`, `clear_session`) because a plan names them; a step that fails is said in one line and the next one runs.

## Open

- A trial task at the end of setup (keep or drop).
- Existing role sessions: reuse or start fresh (fresh is cheaper: old sessions carry long histories).
- Texts and label names come from the config, so friends can use their own language.
