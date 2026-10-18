# Agent team playbook

A small team of AI agent sessions (Claude Code) that works for one human – the owner – on a project's GitHub issues. The owner writes tasks in plain words, from a phone if they like. A cheap dispatcher hands each task to the right session. Each session does its task and closes it with one command.

## What you get

- **You only write issues.** No labels, no states, no copying text between chats. Comment on an issue and your words reach the session working on it.
- **Low token use while idle.** A script watches the board every minute and spends no tokens. A mid model (the dispatcher) wakes only when there is work, routes it and goes back to sleep.
- **Every worker pulls its next task.** After a task, a session waits in `agentq next --wait` without tokens and is woken with the next one – no dispatcher round-trip per task. The dispatcher only sorts new tasks, passes on your words and nudges a stuck session.
- **One task per session at a time.** Busy is read from the board, so a session never gets a second task while it works on one. A role may have several sessions (e.g. five programmers); each free one gets the next task.
- **Strong where it counts, cheap where it doesn't.** Every role works on the strongest model at extra-high effort (*hard* issues: the highest). Only the dispatcher, which just routes, runs on a mid model at low effort.
- **Checks in batches, not after every task.** A checker wakes after N finished tasks (or 24 h) and turns each problem into a new issue linked to the original.
- **It learns where tasks belong.** When a session gets a task that isn't its own, routing it on teaches the dispatcher. Your rules always outrank the agents' rules.
- **Your words are never lost or reworded.** The dispatcher passes them on verbatim, with screenshots downloaded, even from private repositories.
- **Everything is visible.** Every session is a normal session you can open. Every agent comment on GitHub comes from a separate AI account and starts with `🤖 <role>:`.
- **Problems reach your phone.** An hourly health check (no tokens) opens one GitHub issue when the watcher stopped or a task got stuck. A role that holds a task but went quiet gets one reminder; if that does not help, the task goes back to the queue and the health issue asks for you. A pull request left untouched for days becomes a task: finish it or close it.
- **Projects can share tasks.** A task filed in the wrong project moves to the right one. A task that spans two projects is split, and each part links back to the other.
- **Per project, in your language.** The team is installed per project, never globally. All label names and texts come from the config.

## How it works

```
owner ──writes──▶ GitHub issues ◀──polls every minute, no tokens── agentq watch
                                                                       │ work found: prints a plan, exits
                                                                       ▼
                                   dispatcher session (mid model, own small folder)  
                                     classify → agentq assign → agentq brief → send to the role's session
                                                                       │
             ┌─────────────────────────────┬───────────────────────────┴───────────┐
             ▼                             ▼                                       ▼
        programmer                      checker                         marketer / your own roles
  (default role, interprets      (batches of finished tasks;
   the owner's words)             release check on the owner's word)
             └── finish with one command: done · ask · route · wait · move · split · checked
```

Roles work in one of two modes. **Programmer mode** gets one task at a time. **Checker mode** gets a batch issue (`Check: #a #b #c`, at a pinned commit) once N tasks are finished or the oldest has waited 24 h. Optionally, a checker-mode role only counts tasks whose commits touched given paths. The full design is in [docs/DESIGN.md](docs/DESIGN.md).

## What you need

- macOS or Linux with `git`, `python3` (standard library only) and [`gh`](https://cli.github.com).
- The Claude desktop app (Code tab). Sessions message each other, and a finished background command wakes a session.
- A separate GitHub account for the agents (the "AI account"). GitHub allows one free machine account per person. Invite it to your project with **Write** access, not Admin.

## Claude and Codex

Every role can be worked by Claude sessions, by Codex workers, or by both at once – they compete for the same tasks, and claims keep two from taking one. Each task gets a `claude` or `codex` label, and comments say which team wrote them; `agentq stats` compares the teams. Move the work to whichever has tokens left: `agentq team codex` (Claude off), `agentq team claude` (Codex off), `agentq team both`. `agentq codex-workers` opens one prefilled Codex task per role in the Codex app; press Send on each. A Codex worker loops on `agentq next <role> --wait` (waits without tokens), does the task and finishes it with the usual commands. Reminders for quiet sessions and per-task model switches are Claude-only.

## Install into a project

Do this once per project. The team is never installed globally.

1. **Get the package:** `git clone <this repository> ~/Sites/agent-team-playbook` (any folder works).
2. **Sign the AI account in to `gh`:** run `gh auth login` and open the confirmation page in a browser where the AI account is signed in. Your own account can stay signed in, but inactive (`gh auth switch` changes the active one).
3. **Open a Claude Code session in your project** and say:
   > Install the agent team from ~/Sites/agent-team-playbook in this project. My GitHub login is `<you>`.

   The session reads [the skill](skill/agent-team/SKILL.md) and walks through the install steps with you:
   - `agentq init` creates this project's config in `~/.config/agentq/<owner>-<repo>.json`. It links `.agentq.json` and `.claude/skills/agent-team` into the project and keeps both out of git through `.git/info/exclude`.
   - `agentq setup` checks access, then creates the labels, the roles table and the dispatcher's folder (`~/agent-team/<owner>-<repo>-dispatcher`).
   - The session sorts your open issues, starts the checker and dispatcher sessions (you approve each once) and adds a daily health timer.
   - It asks **"Turn on the marketer?"**, then **"Add more roles?"**, and repeats until you say no.
4. **Another project?** Repeat step 3 there. When two projects both have the team, the session asks whether they should share tasks (`agentq link`).

Nothing is installed outside the project and the two folders above. To uninstall, delete the two links in the project, its config and its dispatcher folder, and archive the sessions.

## Daily use

You write issues and comments. To change how many sessions of a role work in parallel, say e.g. "10 programmers": the session creates the missing numbered sessions in the team's group; fewer later just rests the extra ones, and more reuses them. To stop or restart the whole team, say "stop" or "go" to any team session; it pauses or resumes the dispatcher's work and restarts the watcher when needed. Write the priority label's word (e.g. SKUBU) anywhere in an issue or comment and it goes first. Labels you may use if you like: `priority`, `blocking`, `hard` (highest effort), `deferred`. To give a rule to the dispatcher, say it to any session, e.g. "banners go to the designer". The session runs `agentq teach --owner "banners → designer"`.

The commands agents use:

| Command | Who | What |
|---|---|---|
| `watch` | dispatcher (background) | poll every minute; print a plan and exit when there is work |
| `assign N role [--queue]` | dispatcher, setup | role label + working (or queued when the role is busy) |
| `brief N [--since T]` | dispatcher | the task verbatim, the owner's comments, screenshots as local files |
| `done N "text"` | role | fixed: comment, close |
| `ask N "question"` | role | stuck: ask the owner; out of the queue until answered |
| `route N role "why"` | role | not mine: hand it over and teach the dispatcher |
| `wait N other/repo#M` | role | needs another project first; `check --fix` brings it back |
| `move N other/repo` · `split N other/repo "title" "text"` | dispatcher, role | sharing between linked projects |
| `batch role` · `checked N` | dispatcher · checker | create a checker's batch · finish it (labels every task `checked: <role>`) |
| `teach "topic → role" [--owner]` | anyone | a rule for the dispatcher |
| `health` | hourly timer | watcher alive, nothing stuck; problems go to one issue |
| `nudge` · `held` | watcher, dispatcher | a reminder for a quiet session that holds a task |
| `tests per-task\|batched` | any session, on the owner's word | each task runs the whole suite, or the watcher runs it every N tasks (red wakes the checker) |
| `scale role N` | any session, on the owner's word | how many sessions of a role work in parallel; missing ones to start, extra ones rest |
| `init` · `setup` · `role` · `link` · `roles` | install | config, labels, roles table, dispatcher folder |
| `queue` · `take` · `defer` · `check` | anyone | the 0.1 commands, still available |

## Configuration

See [config.example.json](config.example.json). The main parts:

- `owner_accounts`, `agent_account`, `repos`, `checkout` (the project folder, used for path filters and pinned commits);
- `roles`: a table of role, label, mode, `n`/`hours`/`paths` (checker mode), model, `release_model`, effort, `hard_effort`, merge, session, description, examples;
- `dispatcher`: folder, session, model, effort;
- `links`: linked projects and what belongs there (sharing is on while a link exists);
- `poll_seconds` (60), `repeat_minutes` (30: a plan the dispatcher did not act on wakes it again at most this often), `forward_hours` (24: how long an undelivered owner comment stays in the plan), `idle_minutes` (20) and `escalate_minutes` (30) for quiet sessions, `stale_hours` (24);
- `labels` and `texts`: every label name and every text the tool writes, so you can use your own language.

The dispatcher reads `roles.md` in its folder. agentq writes that file from the roles table, the rules and the last 5 routing lessons per role.

## Limits worth knowing

- A role session acts on a dispatcher message because the skill says so. Try one task end to end after installing.
- Sessions must all run in the same permission mode. Otherwise cross-session messages wait for your approval.
- The dispatcher switches a session's model or effort per task without asking only in bypass permission mode. Otherwise the app asks you each time, so leave `hard_effort` and `release_model` empty.
- Moving an issue between projects uses GitHub's transfer, which only works within one account or organisation. Elsewhere agentq copies the issue and closes the original with a link.

## Update

Run `git pull` in the package folder. The links point into the package, so every project gets the new version at once. [CHANGELOG.md](CHANGELOG.md) says what changed.

## Tests

```bash
python3 -I -m unittest discover -s tests
```

The tests run against a fake `gh` and never touch GitHub. The package is meant to be shared, so it must not contain private names. Keep your list of private words outside the package (`~/.config/agentq/private-words.txt`, or set `AGENTQ_PRIVATE_WORDS=<file>`); a test then checks that none of them got into the package.
