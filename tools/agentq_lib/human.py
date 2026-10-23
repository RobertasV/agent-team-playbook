"""The human test stage, for the tasks picked for it (the `human test` label): the programmer hands the task to a
human tester with scenarios and the build to test; the tester's result – passed, found problems, could not test –
closes it, sends it back for a fix, or asks the owner. Only a result for the latest iteration counts; the watcher
acts on each result once (a marker it leaves on the issue), so a restart never repeats it. docs/HUMAN-TEST.md is
the format Margin and agentq share."""

import json

from .base import Fail, HANDOFF_MARK, PROCESSED_MARK, RESULT_MARK
from .github import comment, gh, gh_pages, labels_of, login_of, relabel, resolve, view
from .config import holder
from .state import update_state

RESULTS = ('pass', 'fail', 'blocked')


def marks(pattern, body):
    found = []
    for m in pattern.finditer(body or ''):
        try:
            data = json.loads(m.group(1))
        except ValueError:
            continue
        if isinstance(data, dict):
            found.append(data)
    return found


def test_history(cfg, comments):
    """The iterations handed to the tester and the marks agentq left (both only from the AI account), and the results,
    in comment order."""
    handoffs, results, processed = [], [], set()
    for c in comments:
        body = c.get('body') or ''
        ours = login_of(c) == cfg['agent_account']
        for h in marks(HANDOFF_MARK, body) if ours else []:
            handoffs.append({**h, 'at': c.get('created_at') or c.get('createdAt'), 'id': c.get('id')})
        for r in marks(RESULT_MARK, body):
            results.append({**r, 'by': login_of(c), 'at': c.get('created_at') or c.get('createdAt'), 'id': c.get('id')})
        for p in marks(PROCESSED_MARK, body) if ours else []:
            processed.add(str(p.get('comment')))
    return handoffs, results, processed


def testers(cfg, issue=None):
    """Who may give a result: the config's testers – not the owner's rights, not a right to publish."""
    return {t.lower() for t in cfg['testers']}


def latest_result(cfg, issue, comments):
    """The tester's result for the latest iteration, or None: an older iteration's result, a question, or anyone
    else's comment never counts."""
    handoffs, results, processed = test_history(cfg, comments)
    if not handoffs:
        return None, handoffs, processed
    current = handoffs[-1]
    allowed = testers(cfg, issue)
    for r in reversed(results):
        if (r.get('by') or '').lower() in allowed and r.get('iteration') == current.get('iteration') \
                and r.get('result') in RESULTS and (r.get('at') or '') >= (current.get('at') or ''):
            return r, handoffs, processed
    return None, handoffs, processed


def cmd_handoff(cfg, opts):
    """The programmer hands a picked task to the human tester: the build to test and the scenarios, one iteration
    more. The task stays open and leaves the queue until the tester's result."""
    repo, number = resolve(cfg, opts.issue)
    issue = view(repo, number)
    names = labels_of(issue)
    labels = cfg['labels']
    if labels['human_test'] not in names:
        raise Fail(f"{repo}#{number} is not picked for a human test (label '{labels['human_test']}'): finish with done")
    if not cfg['testers']:
        raise Fail('no tester in the config ("testers": ["<GitHub login>"])')
    tester = opts.tester or cfg['testers'][0]
    if tester.lower() not in {t.lower() for t in cfg['testers']}:
        raise Fail(f'{tester} is not one of the testers ({", ".join(cfg["testers"])})')
    if not (opts.build or '').strip() or not (opts.text or '').strip():
        raise Fail('a handoff needs --build (where and which version to open) and the scenarios')
    comments = gh_pages('api', f'repos/{repo}/issues/{number}/comments', '--paginate')
    handoffs, _, _ = test_history(cfg, comments)
    iteration = len(handoffs) + 1
    data = {'iteration': iteration, 'build': opts.build.strip(), 'commit': (opts.commit or '').strip(), 'tester': tester}
    text = cfg['texts']['handoff'].format(tester=tester, iteration=iteration, build=data['build'],
                                          commit=data['commit'] or '-', text=opts.text.strip())
    comment(cfg, repo, number, f"{text}\n<!-- agentq:human-test {json.dumps(data, ensure_ascii=False)} -->",
            holder(cfg, issue))
    relabel(repo, number, add=[labels['testing']], remove=[n for n in (labels['working'],) if n in names])
    gh('issue', 'edit', str(number), '-R', repo, '--add-assignee', tester)
    update_state(cfg, lambda d: d.get('holders', {}).pop(f'{repo}#{number}', None))
    print(f'{repo}#{number}: iteration {iteration} handed to {tester} – the task waits for the test; take your next one')


def human_tests(cfg, state, repo, issues, closed_recently):
    """The watcher's part: act on each new tester result once, and reopen a picked task that closed without a pass
    for its latest iteration (a `Fixes #N` commit, or done). Returns lines for the owner (could not test)."""
    labels = cfg['labels']
    told = []
    picked = [i for i in issues if labels['testing'] in labels_of(i)]
    shut = [i for i in closed_recently if labels['human_test'] in labels_of(i)]
    for issue in picked + shut:
        number = issue['number']
        comments = gh_pages('api', f'repos/{repo}/issues/{number}/comments', '--paginate')
        result, handoffs, processed = latest_result(cfg, issue, comments)
        is_open = issue not in shut
        if not is_open:
            passed = result and result.get('result') == 'pass' and str(result.get('id')) in processed
            if not passed and closed_by_work(cfg, repo, number):
                gh('issue', 'reopen', str(number), '-R', repo)
                comment(cfg, repo, number, cfg['texts']['human_reopened'].format(number=number), 'health')
            continue
        if not result or str(result.get('id')) in processed:
            continue
        mark = json.dumps({'iteration': result.get('iteration'), 'result': result['result'], 'comment': result.get('id')})
        who, it = result.get('by'), result.get('iteration')
        if result['result'] == 'pass':
            comment(cfg, repo, number, cfg['texts']['human_passed'].format(tester=who, iteration=it,
                    build=handoffs[-1].get('build', '-')) + f'\n<!-- agentq:test-processed {mark} -->', 'health')
            relabel(repo, number, remove=[labels['testing']])
            gh('issue', 'close', str(number), '-R', repo)
        elif result['result'] == 'fail':
            comment(cfg, repo, number, cfg['texts']['human_failed'].format(tester=who, iteration=it)
                    + f'\n<!-- agentq:test-processed {mark} -->', 'health')
            relabel(repo, number, remove=[labels['testing']])  # back to its role's queue, the findings in the brief
        else:
            comment(cfg, repo, number, cfg['texts']['human_blocked'].format(tester=who, iteration=it)
                    + f'\n<!-- agentq:test-processed {mark} -->', 'health')
            relabel(repo, number, add=[labels['question']], remove=[labels['testing']])  # the owner decides
            told.append(f'{repo}#{number}')
    return told


def closed_by_work(cfg, repo, number):
    """Closed by a commit (`Fixes #N`) or by an agent – not by the owner, whose closing stands."""
    events = gh_pages('api', f'repos/{repo}/issues/{number}/events?per_page=100', '--paginate')
    closed = [e for e in events if e.get('event') == 'closed']
    if not closed:
        return False
    last = closed[-1]
    return bool(last.get('commit_id')) or (last.get('actor') or {}).get('login') == cfg['agent_account']
