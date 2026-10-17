# Agent team 0.2 – design

Agreed with the owner before building 0.2. This is the build spec; `skill/agent-team/SKILL.md` is the short version agents read. Scope: **one project** (how two projects talk is decided later).

## Team

Three core roles exist in every project:

| Role | Model | Effort | Job |
|---|---|---|---|
| Dispatcher | cheapest | lowest | Watches the board through a script and sends tasks. Never codes, never interprets the owner's words. |
| Programmer | strongest | high (issues labelled *hard*: highest) | Default role: every task nobody else owns. The only role that interprets the owner's words. |
| Checker | mid for batch checks, strongest for the release check | high | Checks batches of finished tasks. The full release check runs only on the owner's word. |

The owner is not a role: everyone works for them.

**Ready-made extra role: marketer** (mid model, programmer mode). Setup always offers it. If the owner says no, the programmer does marketing tasks too. A marketer prepares posts, ads and campaigns; anything public or paid happens only on the owner's word.

**Owner-defined roles.** At the end of setup (and any time later, in words) the owner may add roles. Each role has: name, description with 2–3 example tasks (optionally a reference screenshot), mode, model, effort, and whether it merges its own changes or hands them to the programmer.

When a new role overlaps an existing one (e.g. designer and marketer both claim banners), setup asks the owner where the border is and records it as a teaching rule.

## Modes

- **Programmer mode** – gets one task at a time carrying its role label, does it, closes it.
- **Checker mode** – wakes when at least N finished tasks are unchecked by this role, or the oldest has waited 24 h. Optional path filter: only tasks whose changes touched these paths (so a rules reviewer does not wake for tasks that never touched rules). Each checker-mode role has its own `checked: <role>` label, so two checkers never share a batch. Findings become new issues that link the original; the original is not reopened.

## Flow

1. **Watcher** (`agentq watch`, run in the background by the dispatcher) polls GitHub every minute and spends no tokens. It ignores the agent account's own comments, so agents' updates never wake anyone. It builds a plan:
   - owner comments since the last mark → forward to the role holding that issue (default: programmer);
   - a role is **free** when no open issue carries both its role label and the working label; for each free programmer-mode role, the next issue: priority label → blocking label → oldest; unlabelled issues go to the dispatcher to classify;
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
5. **Health** (`agentq health`, daily timer, no tokens): is the watcher alive, is any task "working" with no activity for over 24 h. Problems go to the owner on GitHub (one health issue, so the owner's phone gets notified).

Busy is read from the board, so a role never gets a second task while it works on one. A direct chat between the owner and a session is not on the board; a task message then waits until the session answers the owner.

## Setup

Run once by the programmer session when the skill is first used in a project:

1. Check: `gh`, the AI account signed in and active, Write access, which accounts are the owner's. Show the owner what is missing; only the owner signs in.
2. Labels: working, question, deferred, waiting, priority, blocking, hard, waits-for-owner's-word, each role's label, each checker's `checked: <role>`.
3. Sort the open issues: role labels, deferred; unclear ones go to the owner as one list.
4. Config: the roles table (role, label, mode, N, path filter, model, effort, merge, session).
5. Sessions: the programmer is the session running setup; create the checker and the dispatcher (in its own small folder, so it starts without the project's big rules). The app asks the owner to approve each new session once.
6. Watcher in the dispatcher's background; daily health timer.
7. "Turn on the marketer?"
8. "Add more roles?" – name, what it does, mode (programmer / checker with N), model, effort, merge; repeat until no.

Re-running setup creates nothing that exists: it finds the sessions from the config, recreates missing or archived ones and restarts the watcher (e.g. after a reboot).

## To verify before building on it

1. A background command that finishes wakes an idle session (the watcher depends on it; fallback: a scheduled run, which costs tokens every time).
2. The dispatcher can message the role sessions.
3. The AI account can download screenshots from private repositories.
4. Sessions act on dispatcher messages when the skill says so.
5. Whether the dispatcher can set a session's model or effort per task (batch vs release check, *hard*); otherwise the release check gets its own session.

## Open

- How two projects work together.
- A trial task at the end of setup (keep or drop).
- Existing role sessions: reuse or start fresh (fresh is cheaper: old sessions carry long histories).
- Texts and label names come from the config, so friends can use their own language.
