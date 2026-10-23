# The human test stage

A person – not the AI checker – tests chosen tasks by hand before they count as done. It is opt-in per task: a task
without the `human test` label goes through the team exactly as before. This file is the format agentq and a board
(Margin) share; the GitHub issue and its comments keep the whole history.

## Turning it on

- The project's config names the testers: `"testers": ["<GitHub login>", …]`. Without testers the stage is off and
  agentq ignores the labels below.
- A tester is **not** an owner: their comments are not the owner's words, they cannot release or publish anything, and
  they are not added to `owner_accounts`. Their result is the only thing agentq takes from them.
- Labels (config keys `human_test`, `testing`; `agentq setup` creates them):
  - `human test` – the task is picked for the stage. The owner or the dispatcher adds it when sorting.
  - `testing` – handed to the tester; the task waits for the result (a board's "Testing" column).

## The flow

```
coded → testing (iteration N) → passed: closed
                              → found problems: back to the programmers → fixed → testing (iteration N+1) → …
                              → could not test: a question to the owner
```

1. **Hand-off** – the programmer, instead of `agentq done`:
   `agentq handoff <issue> --build "<where and which version to open>" --commit <sha> - <<'EOF'` scenarios `EOF`.
   agentq posts one comment with the scenarios and the build, adds `testing`, removes the working label, assigns the
   tester (`--tester`, default the config's first) and frees the programmer for other work. The comment carries:

   `<!-- agentq:human-test {"iteration": 2, "build": "v1.2-rc2", "commit": "abc123", "tester": "tina"} -->`

   The iteration counts up from 1 on each hand-off; only the AI account's hand-off comments count.
2. **Result** – the tester comments on the same issue with their own account. The comment must carry:

   `<!-- agentq:test-result {"iteration": 2, "result": "pass" | "fail" | "blocked"} -->`

   - `pass` – tested, it works;
   - `fail` – tested, found problems: the steps (and screenshots when needed) in the same comment;
   - `blocked` – could not test: the reason in the same comment.

   A board writes the marker for the tester (buttons "Passed" / "Found problems" / "Could not test"); nobody types it.
   A comment without the marker – a question, a note – is not a result. A result counts only from a configured tester,
   only for the **latest** iteration, and only after that hand-off: a pass for iteration 1 never passes iteration 2.
3. **The watcher** (no tokens) acts on each result once:
   - `pass` → a comment, `testing` removed, the issue closed. Only then does the AI checker's batch see it.
   - `fail` → a comment, `testing` removed: the task is in its role's queue again, and the brief shows the tester's
     findings to the programmer, who fixes them and hands off iteration N+1.
   - `blocked` → a comment, `testing` removed and the owner's question label added: the owner decides.

   Each action leaves `<!-- agentq:test-processed {"iteration": 2, "result": "pass", "comment": <comment id>} -->`
   on the issue, so a restarted watcher, or one that reads the same comment again, never repeats it.

## Guards

- `agentq done` refuses on a picked task: a picked task is never done just because its code is.
- Commits on a picked task say `Refs #N`, never `Fixes #N` (the brief says so). If a commit, or an agent, closes it
  anyway without a pass for its latest iteration, the watcher reopens it. When the **owner** closes it, that stands.
- The AI checker's batches collect closed tasks, so a picked task enters them only after it passed: no deadlock.

## For a board (Margin)

- A tester's "Needs you": open issues with `testing` whose assignee is that tester. The owner's own "Needs you" is
  unchanged.
- Testing progress per tester, project and period, counted from the markers: waiting (`testing`), tested (unique
  issues with a `test-result`; `pass` and `fail` both mean tested), passed, sent back (`fail`), could not test
  (`blocked`, shown apart), waiting for a re-test (iteration > 1 with `testing`). Re-tests are counted apart, so one
  issue never shows as several tested tasks.
