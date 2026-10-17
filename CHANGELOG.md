# Changelog

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
