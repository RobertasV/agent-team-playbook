# Changelog

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
