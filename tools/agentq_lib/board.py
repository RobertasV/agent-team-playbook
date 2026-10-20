"""The board: which task a role takes next, claims, who holds what, batches and tasks waiting for others."""

import datetime as dt
import fnmatch
import json
import re
import socket

from .system import replace_file
from .base import CLAIM_MARK, Fail, FULL, iso, now, parse_time, WAIT_MARK
from .github import board, claim, comment, create_issue, gh_json, gh_pages, git, labels_of, login_of, relabel, view
from .config import agent_labels, capacity, checked_label, pushes, trusted
from .apps import worker_title


def session_held(cfg, state, role, repo, issues):
    """The tasks this role's Claude sessions hold – not those a Codex worker or another computer took."""
    holders = state.get('holders', {})
    return [i for i in issues if holders.get(f"{repo}#{i['number']}") in role['sessions'] or (
        f"{repo}#{i['number']}" not in holders and not taken_elsewhere(cfg, state, repo, i['number']))]


def taken_elsewhere(cfg, state, repo, number):
    """A task in progress that no worker of this computer holds: its last claim names another computer (the same
    project worked from two computers). Read once per task while it is in progress."""
    ref = f'{repo}#{number}'
    hosts = state.setdefault('claim_hosts', {})
    if ref not in hosts:
        try:
            comments = gh_pages('api', f'repos/{repo}/issues/{number}/comments', '-H', FULL, '--paginate')
        except Fail:
            return False
        claims = [m.group(1) for c in comments for m in [CLAIM_MARK.search(c.get('body') or '')] if m]
        hosts[ref] = claims[-1].split('/')[0] if claims else ''
    return hosts[ref] not in ('', socket.gethostname())


def holder_of(state, role, ref):
    """The session of a role's pool that holds this task (recorded by assign); else the role's first session."""
    sid = state.get('holders', {}).get(ref)
    return sid if sid in role['sessions'] else role['session']


def free_session(state, role, held_refs, waiting=()):
    holders = state.get('holders', {})
    taken = {holders.get(r) for r in held_refs if holders.get(r) in role['sessions']}
    unknown = sum(1 for r in held_refs if holders.get(r) not in role['sessions'])
    free = [x for x in role['pool'] if x not in taken][unknown:]
    free = [x for x in free if x not in waiting] or free  # a waiting session takes its next task itself
    return free[0] if free else role['session']


def release_waits(cfg, state, repo, issues, start):
    """A task waiting for another issue (`agentq wait`) goes back to the queue once that issue is closed – checked
    every 10 minutes by the watcher, so nobody has to run `check --fix`."""
    waiting = [i for i in issues if cfg['labels']['waiting'] in labels_of(i)]
    seen = state.setdefault('waits_at', {})
    if not waiting or (seen.get(repo) and start - parse_time(seen[repo]) < dt.timedelta(minutes=10)):
        return
    seen[repo] = iso(start)
    for issue in waiting:
        found = gh_json('issue', 'view', str(issue['number']), '-R', repo, '--json', 'comments')
        marks = [m for c in found.get('comments', []) for m in WAIT_MARK.findall(c.get('body', ''))]
        if not marks:
            continue
        other, other_n = marks[-1]
        if gh_json('issue', 'view', other_n, '-R', other, '--json', 'state').get('state') != 'CLOSED':
            continue
        comment(cfg, repo, issue['number'], cfg['texts']['back'].format(ref=f'{other}#{other_n}'))
        relabel(repo, issue['number'], remove=[cfg['labels']['waiting']])
        issue['labels'] = [l for l in issue['labels'] if l['name'] != cfg['labels']['waiting']]


def busy_with(cfg, issues, role, but=None):
    working = cfg['labels']['working']
    return [i for i in issues if i['number'] != but and role['label'] in labels_of(i) and working in labels_of(i)]


def kept_for(cfg, issue):
    """The team the owner kept this task for ('claude' or 'codex', by its only-label), else None."""
    names = labels_of(issue)
    return next((a for a in ('claude', 'codex') if cfg['labels'][f'only_{a}'] in names), None)


def next_issue(cfg, issues, role, skip_numbers=(), agent=None):
    """Priority label → blocking label → oldest; for a team (agent), none the owner kept for the other team."""
    skip = cfg['skip'] | {cfg['labels']['working'], cfg['labels']['batch']}
    queue = [i for i in issues if role['label'] in labels_of(i) and not skip & set(labels_of(i)) and trusted(cfg, i)
             and i['number'] not in skip_numbers and (not agent or kept_for(cfg, i) in (None, agent))]
    queue.sort(key=lambda i: (cfg['labels']['priority'] not in labels_of(i),
                              cfg['labels']['blocking'] not in labels_of(i), i['number']))
    return queue[0] if queue else None


def path_hit(name, patterns):
    for p in patterns:
        p = p.rstrip('/')
        if name == p or name.startswith(p + '/') or fnmatch.fnmatch(name, p):
            return True
    return False


def touched(cfg, items, patterns):
    """Only the tasks whose commits (found by "#N" in the message, local git log) changed these paths."""
    if not items:
        return []
    if not cfg.get('checkout'):
        raise Fail('a path filter needs "checkout" (the project folder) in the config')
    numbers = {i['number'] for i in items}
    grep = '#(' + '|'.join(str(n) for n in sorted(numbers)) + ')([^0-9]|$)'
    out = git(cfg['checkout'], 'log', '--all', '-E', f'--grep={grep}', '--format=%x1e%B%x1f', '--name-only')
    hit = set()
    for chunk in out.split('\x1e')[1:]:
        message, _, files = chunk.partition('\x1f')
        refs = {int(n) for n in re.findall(r'#(\d+)\b', message)} & numbers
        if any(path_hit(f.strip(), patterns) for f in files.splitlines() if f.strip()):
            hit |= refs
    return [i for i in items if i['number'] in hit]


def unchecked(cfg, state, repo, role, cache):
    """Finished tasks this checker-mode role has not checked yet, oldest first."""
    since = role.get('since') or state.setdefault('checker_since', {}).setdefault(role['role'], iso(now()))
    if repo not in cache:
        first = min([since] + [r.get('since') or since for r in cfg['roles'] if r['mode'] == 'checker'])
        cache[repo] = gh_json('issue', 'list', '-R', repo, '--state', 'closed', '--limit', '300',
                              '--search', f'closed:>={first}',
                              '--json', 'number,title,labels,closedAt,stateReason,author')
    not_tasks = {checked_label(cfg, role), cfg['labels']['batch'], cfg['labels']['health']}
    items = [i for i in cache[repo]
             if parse_time(i['closedAt']) >= parse_time(since) and i.get('stateReason') != 'NOT_PLANNED'
             and not not_tasks & set(labels_of(i)) and trusted(cfg, i)]
    if role['paths']:
        items = touched(cfg, items, role['paths'])
    return sorted(items, key=lambda i: i['closedAt'])


def batch_ready(cfg, role, items, moment):
    if not items:
        return False
    return len(items) >= int(role['n']) or moment - parse_time(items[0]['closedAt']) >= dt.timedelta(hours=float(role['hours']))


def agent_set_working(cfg, state, repo, issue):
    """Busy means the agent account set the working label; one the owner's own tools set does not count."""
    key = f"{repo}#{issue['number']}"
    cache = state.setdefault('working_by', {})
    hit = cache.get(key)
    if hit and hit['at'] == issue.get('updatedAt'):
        return hit['agent']
    events = gh_pages('api', f"repos/{repo}/issues/{issue['number']}/events?per_page=100", '--paginate')
    setters = [e for e in events if e.get('event') == 'labeled'
               and (e.get('label') or {}).get('name') == cfg['labels']['working']]
    agent = not setters or (setters[-1].get('actor') or {}).get('login') == cfg['agent_account']
    cache[key] = {'at': issue.get('updatedAt'), 'agent': agent}
    return agent


def real_board(cfg, state, repo):
    """The open issues, with a working label the agent account did not set left out."""
    issues = board(repo)
    working = cfg['labels']['working']
    held = set()
    for issue in issues:
        if working in labels_of(issue):
            held.add(f"{repo}#{issue['number']}")
            if not agent_set_working(cfg, state, repo, issue):
                issue['labels'] = [l for l in issue['labels'] if l['name'] != working]
    cache = state.get('working_by', {})
    for key in [k for k in cache if k.startswith(repo + '#') and k not in held]:
        del cache[key]
    return issues


def mark_urgent(cfg, repo, item, issues, urgent):
    """The owner wrote an urgent word (e.g. SKUBU) in the title, the text or a comment: the issue gets the priority
    label, so the next free session takes it first. Once per issue: a label the owner later removes stays removed."""
    ref = f"{repo}#{item['number']}"
    label = cfg['labels']['priority']
    if item.get('state', 'OPEN') != 'OPEN' or ref in urgent or label in labels_of(item):
        return
    owners = set(cfg['owner_accounts'])
    words = [w for w in cfg['priority_words'] if w]
    pattern = re.compile(r'(?<!\w)(' + '|'.join(re.escape(w) for w in words) + r')(?!\w)', re.I) if words else None
    texts = [c.get('body') or '' for c in item.get('comments', []) if login_of(c) in owners]
    if login_of(item) in owners:
        texts += [item.get('title') or '', item.get('body') or '']
    if pattern and any(pattern.search(t) for t in texts):
        relabel(repo, item['number'], add=[label])
        urgent[ref] = iso(now())
        for issue in issues:
            if issue['number'] == item['number']:
                issue['labels'] = issue['labels'] + [{'name': label}]


def shared_board(cfg, state, repo):
    """The board as the watcher last read it, when fresh; else read it now. Many waiting workers, one reader."""
    try:
        with open(cfg['state_file'] + '.board.json', encoding='utf-8') as f:
            snap = json.load(f).get(repo)
        if snap and now() - parse_time(snap['at']) <= dt.timedelta(seconds=2 * cfg['poll_seconds'] + 30):
            return snap['issues']
    except (OSError, ValueError, KeyError):
        pass
    return real_board(cfg, state, repo)


def save_board(cfg, boards):
    tmp = cfg['state_file'] + '.board.json.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(boards, f)
    replace_file(tmp, cfg['state_file'] + '.board.json')


def take_next(cfg, state, repo, issues, roles, worker, agent, skip=()):
    """Claim the next task of these roles for a worker: priority, then blocking, then the oldest, each read again on
    GitHub first (the board may be a minute old); else a checker's batch when one is ready. Returns (ref, role)."""
    labels = cfg['labels']
    add_agent, drop_agent = agent_labels(cfg, agent)
    candidates = []
    for role in roles:
        held = busy_with(cfg, issues, role)
        if not pushes(role) and role['pool'] and len(held) >= capacity(role):
            continue
        picked = list(skip)
        while True:  # this role's queue, in its order
            issue = next_issue(cfg, issues, role, picked, agent)
            if not issue:
                break
            picked.append(issue['number'])
            candidates.append((role, issue))
    candidates.sort(key=lambda c: (labels['priority'] not in labels_of(c[1]),
                                   labels['blocking'] not in labels_of(c[1]), c[1]['number']))
    for role, issue in candidates:
        fresh = view(repo, issue['number'])
        if fresh.get('state', 'OPEN') != 'OPEN' or labels['working'] in labels_of(fresh) \
                or role['label'] not in labels_of(fresh) or kept_for(cfg, fresh) not in (None, agent):
            continue
        if claim(cfg, repo, issue['number'], cfg['texts']['take'], role['role'], agent, worker_title(cfg, worker)):
            relabel(repo, issue['number'], add=[labels['working']] + add_agent,
                    remove=[n for n in drop_agent if n in labels_of(fresh)])
            ref = f"{repo}#{issue['number']}"
            state.setdefault('holders', {})[ref] = worker
            state.setdefault('last_team', {})[role['role']] = agent
            return ref, role
        # a loser goes on: another worker took that one a moment earlier
    for role in roles:
        if role['mode'] == 'checker' and not busy_with(cfg, issues, role):
            items = unchecked(cfg, state, repo, role, {})[:20]
            if batch_ready(cfg, role, items, now()):
                ref = create_batch(cfg, state, repo, role, items, add_agent)
                state.setdefault('holders', {})[ref] = worker
                return ref, role
    return None, None


def create_batch(cfg, state, repo, role, items, extra=()):
    refs = ' '.join(f"#{i['number']}" for i in items)
    commit = git(cfg['checkout'], 'rev-parse', 'HEAD').strip() if cfg.get('checkout') else 'not pinned (no checkout in the config)'
    body = cfg['texts']['batch_body'].format(role=role['role'], commit=commit,
                                             list='\n'.join(f"- #{i['number']} {i['title']}" for i in items))
    if cfg['tests']['mode'] == 'batched':
        last = state.get('tests', {}).get('last')
        result = f"{'green' if last['ok'] else 'red'} at {last['sha']}" if last else 'not run yet'
        body += '\n' + cfg['texts']['tests_line'].format(result=result)
    mark = json.dumps({'role': role['role'], 'issues': [i['number'] for i in items]})
    number = create_issue(repo, cfg['texts']['batch_title'].format(refs=refs), f'{body}\n\n<!-- agentq:batch {mark} -->',
                          [role['label'], cfg['labels']['batch'], cfg['labels']['working'], *extra])
    return f'{repo}#{number}'
