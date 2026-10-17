# Changelog

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
