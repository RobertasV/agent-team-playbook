# Changelog

## 0.1.2 – 2026-10-17
- A session no longer clears itself; a long context is compacted instead. State still goes to the issue, a file or memory after each task.

## 0.1.1 – 2026-10-17
- A session clears its own context after each task; the owner never has to.

## 0.1.0 – 2026-10-17
- Skill `agent-team`: roles, one session per role, the owner's words, the task queue on GitHub issues, a separate AI account, releases, tokens.
- `tools/agentq`: `queue`, `take`, `ask`, `defer`, `wait`, `check [--fix]`, `setup`; per-project `.agentq.json`.
