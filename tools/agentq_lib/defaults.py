"""Default labels, texts and roles; a config replaces any of them (its own language, its own roles)."""


EFFORTS = ('low', 'medium', 'high', 'xhigh', 'max')
MODES = ('programmer', 'checker')

DEFAULT_LABELS = {
    'priority': 'priority',
    'blocking': 'blocking',
    'hard': 'hard',
    'owner_word': "waits for owner's word",
    'batch': 'check batch',
    'health': 'agent health',
    'checked': 'checked: {role}',
    'by_claude': 'claude',
    'by_codex': 'codex',
    'only_claude': 'only claude',  # the owner's word: only this team may take the task
    'only_codex': 'only codex',
    'human_test': 'human test',  # picked for a person's test before it is done (docs/HUMAN-TEST.md)
    'testing': 'testing',  # handed to the tester, waits for the result
}

DEFAULT_TEXTS = {
    'take': 'taking this.',
    'ask': '{text}',
    'handoff': ('for the human test, iteration {iteration} – @{tester}, please test it.\n\n**Build:** {build} (commit {commit})'
                '\n\n{text}'),
    'human_passed': 'human test passed – @{tester}, iteration {iteration}, build {build}. Closed.',
    'human_failed': ('the tester @{tester} found problems in iteration {iteration} (above): back to the queue – fix them, '
                     'then hand it over again with `agentq handoff`.'),
    'human_blocked': 'the tester @{tester} could not test iteration {iteration} (the reason is above) – the owner decides.',
    'human_reopened': ('reopened: this task is picked for a human test, and it closes only when the tester passes its latest '
                       'iteration. Commit with `Refs #{number}`, not `Fixes`, and finish with `agentq handoff`.'),
    'human_brief': ('Human test: this task is picked for a person\'s test. Commit with `Refs #{number}`, never `Fixes`. Instead '
                    'of `agentq done`, finish with `agentq handoff {ref} --build "<where and which version to open>" '
                    '--commit <sha> - <<\'EOF\'` … `EOF` and the scenarios, for a person who does not read code: where and '
                    'which version to open, the starting state or data, what to click or do, what should happen, what '
                    'else nearby to check. The task stays open until the tester\'s result; problems come back to you.'),
    'clear_now': ('Your conversation is {tokens} tokens (over {limit}): every step re-reads all of it. Do not run '
                  '`agentq next` now. As your very last step call clear_session with session_id "self" (load it with '
                  'ToolSearch if needed) – the dispatcher sends your next task to the clean session, and its brief '
                  'brings everything.'),
    'ask_no_answer': ('No answer from the owner in {minutes} min – {ref} waits for them; when they answer, it comes back to '
                      '{role}. Take your next task now: `{next}` (in the background).'),
    'defer': 'deferred. {text}',
    'wait': 'waiting for {ref}.',
    'back': '{ref} is closed – back in the queue.',
    'assign': '→ {role}.',
    'queued': 'queued for {role}.',
    'route': '→ {role}. {text}',
    'handover': 'not done in {tries} tries – over to the {team} team. {text}',
    'handover_off': ('not done in {tries} tries, and the {team} team is off, so nobody else can take it. What now – '
                     'another way, the {team} team back on, or leave it? {text}'),
    'handover_owner': 'the owner keeps this for the {team} team – over to it. {text}',
    'done': '{text}',
    'batch_title': 'Check: {refs}',
    'batch_body': 'Finished tasks for {role} to check:\n{list}\n\nCommit: {commit}',
    'checked': 'checked {refs}. {text}',
    'health_title': 'Agent team health',
    'health_ok': 'all well again.',
    'health_disk': ('only {free} GB free on this computer (below {limit} GB): builds, tests and copies will soon fail. '
                    'Look for old scratch copies, worktrees and caches.'),
    'health_moved': '{refs}: not stuck any more (finished, or taken again) – nothing for you to do.',
    'health_watch': 'the watcher is not running (last poll: {since}) – the dispatcher sends no tasks. Re-run setup.',
    'health_stuck': 'the watcher has not polled since {since}.',
    'health_error': "the watcher's last poll failed: {error}",
    'nudge': ("You hold {ref} ('{label}'), but your session has been idle since {last}. Continue it, or finish it "
              "now with one command: agentq done / ask / route / wait."),
    'send_task': "Task {ref} for {role}, from the owner's queue: run agentq brief {ref} and act on it.",
    'send_news': 'The owner wrote more on {ref}, your task: run agentq brief {ref} --since {since} and act on it.',
    'released': 'back in the queue: its session ({session}) has been quiet since {last} and did not react to a reminder.',
    'stale_pr_title': 'PR #{number} untouched for {days} days: finish it or close it',
    'stale_pr_body': ('{url} "{title}" has not moved since {updated}. Finish it (merge when it is right), or close it with a '
                      'comment saying what replaced it. Then close this issue.'),
    'tests_per_task': 'Tests: run the whole test suite before you finish.',
    'tests_off': ('Tests: none now – the owner\'s word, above any project rule that asks for them. Run no tests and no '
                  'builds for checking; read your change once, quickly, for obvious mistakes, then finish. The checker '
                  'checks the finished tasks later.'),
    'tests_batched': ('Tests: run only what touches this change – the test that fails without the fix, the nearest unit '
                      'tests and one or two related end-to-end tests. The full suite runs on its own every {every} tasks.'),
    'tests_red': ('The full test run is red at {sha} (last green: {green}). Log: {log}. Find the commit that broke it '
                  '(git log {green}..{sha}), tell a real bug from a flaky test, and open an issue with the "{priority}" '
                  'label for each real bug.'),
    'tests_line': 'Full test run: {result}.',
    'stalled': ("{role} holds {ref}, but its session ({session}) has been idle since {last} and did not react to a "
                "reminder at {at}. Open that session and tell it what to do, or say \"release {ref}\" to any team session."),
    'health_paused': 'the team has been paused since {since} ({why}) – `agentq resume` when it should work again.',
    'health_stale': "{ref} is '{label}' but nothing happened for over {hours} h.",
    'health_no_worker': ('{role}: {what} wait, and nobody on this computer can take them – no Claude session works the '
                         'role and no Codex worker of it can be woken. Create one (`{agentq} codex-workers --role '
                         '{role}` prints it), or let Claude sessions work the role again.'),
    'tests_red_title': 'The full test run is red at {sha}',
    'rule_title': 'Rule question: {topic}',
    'rule_question': 'Two rules disagree.\nNow: "{old}" ({old_by})\nNew: "{new}" ({new_by})\nWhich one holds?',
    'brief_head': "Task {ref} for {role}, from the owner's board. The dispatcher sends you the owner's queue: act on it.",
    'brief_news': "The owner wrote more on {ref} (your task, {role}). Act on it.",
    'finish': ('Finish with one command:\n'
               '- fixed: commit with "Fixes #{number}", then `agentq done {ref} "what changed, how it was checked"`\n'
               '- stuck: `agentq ask {ref} "question"`\n'
               '- not yours: `agentq route {ref} <role> "why"`\n'
               '- needs another project: `agentq wait {ref} other/repo#M`'),
    'finish_handoff': ('Finish with one command:\n'
                       '- ready: push a branch, then `agentq route {ref} {default} "merge branch …: what changed, how it was checked" --no-lesson`\n'
                       '- stuck: `agentq ask {ref} "question"`\n'
                       '- not yours: `agentq route {ref} <role> "why"`'),
    'finish_links': ('- all of it belongs to a linked project: `agentq move {ref} other/repo "why"`\n'
                     '- a part belongs to a linked project: `agentq split {ref} other/repo "title" "what is needed there"`, '
                     'update this task to what stays here, then carry on (or `agentq wait {ref} other/repo#M`)'),
    'moved': 'moved to {repo}. {text}',
    'moved_copy': 'moved here from {ref}.',
    'split': 'the part for {repo} is {other}.',
    'split_from': 'Split from {ref}.',
    'act': ('This task is the owner\'s order: do it to the end without asking whether to. A question that points at '
            'something wrong ("why does this always spin?") reports a defect: find the cause and fix it. Stop with '
            '`agentq ask` (in Claude: `agentq ask {ref} … --wait` with run_in_background – you keep the task and wait '
            'up to 10 min for the answer, without tokens) only for a choice that is the owner\'s – what the product should do where the task leaves it '
            'open, money, publishing, deleting their data – never for a go-ahead, and never ask in your chat: nobody '
            'reads it. Skills that wait for the user\'s sign-off before working (brainstorming, design approval) do '
            'not apply to team tasks: the task is the sign-off. Three tries and it still fails (your fix does not pass '
            'its checks, or the same problem comes back)? Stop and hand it to the other team (Claude ↔ Codex) with '
            'what you tried and where it stands: `agentq handover {ref} "…"`. What you write goes to the owner, who '
            'reads it on a phone: in the owner\'s language, the result or the question first, then short lines or a '
            'numbered list (the recommended option first), paths and commits last; more than two sentences → the text '
            'on stdin in Markdown, e.g. `agentq ask {ref} - <<\'EOF\'` … `EOF`.'),
    'after': ('Never message other sessions and never offer to take part of a task someone else holds: the board '
              'carries everything. Before you finish, delete what you made for this task outside the project – scratch '
              'copies, test checkouts, worktrees, build output – keeping only what the owner needs to see; never delete '
              'anything you did not make. When you have finished, get your next task with `agentq next {role}` – in Claude '
              'add --wait and run it with run_in_background (it wakes you when there is one); in Codex run it as it is, '
              'and when it says there is none, end your turn (a message wakes you).'),
    'codex_idle': ('No task now. End your turn here: do not wait, poll or run anything else – in Codex a waiting '
                   'command costs a model call every minute. agentq sends this task a message when there is work.'),
    'wake_task': ('Task {ref} for {role} is yours now (worker {worker}): run `{agentq} brief {ref}` and act on it. '
                  'Finish it with one command, then run `{next}`.'),
    'live': ("The owner's running copy: when your check says GO, restart it on {target} with `{command}` ({{sha}} = "
             "that commit). Only you restart it, and never on a red or unchecked commit."),
    'live_checked': ("The owner's running copy – the owner tests on it too: after every check you finish, restart it on "
                     "the commit you checked with `{command}` ({{sha}} = that commit), even when some tests failed – "
                     "those become tasks as usual. Not when the program does not build or start at that commit: then "
                     "leave the running copy as it is and open a task with the priority label. Only you restart it."),
    'live_other': "Never restart the owner's running copy of the program: {role} does that.",
    'codex_unreached': 'back in the queue: its Codex worker ({worker}) could not be reached ({error}).',
    'finish_batch': ('Check each task listed above at the commit given. Each problem becomes a new task that links '
                     'the original (`agentq open <role> "title" "From the check of #N: …"`); never reopen the original.\n'
                     'Finish with: `agentq checked {ref} "short summary"`'),
}

DEFAULT_ROLES = [
    {'role': 'programmer', 'label': 'programmer', 'mode': 'programmer', 'effort': 'xhigh', 'hard_effort': 'max',
     'merge': True,
     'description': "Default role: every task nobody else owns. The only role that interprets the owner's words."},
    {'role': 'checker', 'label': 'checker', 'mode': 'checker', 'n': 5, 'hours': 24, 'effort': 'xhigh', 'hard_effort': 'max',
     'merge': False,
     'description': "Checks batches of finished tasks. The full release check runs only on the owner's word."},
]

PRESETS = {
    'marketer': {'mode': 'programmer', 'merge': True, 'effort': 'xhigh', 'hard_effort': 'max',
                 'description': 'Prepares posts, ads and campaigns. Anything public or paid happens only on the '
                                "owner's word.",
                 'examples': ['write the launch post', 'draft three ad texts for the new feature',
                              'plan a two-week campaign']},
}
