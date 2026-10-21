"""The watcher: reads the board every minute without tokens, wakes Codex workers itself and prints a plan for the
dispatcher when there is work.
"""

import copy
import datetime as dt
import os
import socket
import subprocess
import sys
import time
from shlex import quote as shlex_quote

from .system import (
    code_stamp, detached, kill_tree, parent_gone, restart_if_updated, running_in, SELF, self_command,
    session_parent, shell_script
)
from .base import CLAIM_MARK, Fail, iso, now, one_line, parse_time
from .github import comment, create_issue, gh_json, labels_of, login_of, relabel, resolve, view
from .config import capacity, default_role, pulls, pushes, role_of_labels, tests_role, trusted
from .state import (
    comment_key, load_delivered, load_state, mark_delivered, save_state, update_state, waiting_workers, watch_lock
)
from .apps import codex_activity, codex_reachable, message_codex, reserve_codex, session_activity, session_of
from .board import (
    batch_ready, busy_with, holder_of, kept_for, mark_urgent, next_issue, real_board, release_waits, save_board,
    session_held, take_next, taken_elsewhere, unchecked
)
from .health import report_health


def quiet_holder(cfg, state, repo, ref, role, who, last, start, remind, release=True):
    """One reminder for a holder that went quiet; still quiet escalate_minutes later: the owner is told and the task
    goes back to the queue, so a free worker takes it."""
    nudges = state.setdefault('nudges', {})
    nudge = nudges.get(ref)
    if nudge and last > parse_time(nudge['at']):
        nudges.pop(ref)  # it reacted
        nudge = None
    if start - last < dt.timedelta(minutes=cfg['idle_minutes']):
        return
    if nudge is None:
        nudges[ref] = {'at': iso(start)}
        remind()
    elif not nudge.get('told') and start - parse_time(nudge['at']) >= dt.timedelta(minutes=cfg['escalate_minutes']):
        problem = cfg['texts']['stalled'].format(role=role['role'], ref=ref, session=who, last=iso(last), at=nudge['at'])
        report_health(cfg, state, [problem], needs_owner=True, close=False)
        nudge['told'] = iso(start)
        if release:
            number = int(ref.split('#')[1])
            comment(cfg, repo, number, cfg['texts']['released'].format(session=who, last=iso(last)), 'health')
            relabel(repo, number, remove=[cfg['labels']['working']])


def check_held(cfg, state, repo, issues, start, plan):
    """A role that holds a task but whose session went quiet gets one reminder; if it stays quiet, the owner is told.
    Seen without tokens from the session's transcript (a Codex task: its rollout file); where that cannot be seen,
    the dispatcher checks (get_session). A Codex worker gets its reminder as a queued message, without the dispatcher."""
    nudges = state.setdefault('nudges', {})
    checks = state.setdefault('held_checked', {})
    idle = dt.timedelta(minutes=cfg['idle_minutes'])
    told = {r for r, n in nudges.items() if r.startswith(repo + '#') and n.get('told')}
    held = set()
    for role in cfg['roles']:
        for issue in busy_with(cfg, issues, role):
            ref = f"{repo}#{issue['number']}"
            held.add(ref)
            holder = state.get('holders', {}).get(ref)
            codex = state.get('codex', {}).get(holder) if holder else None
            if codex:
                last = codex_activity(codex['thread']) if codex.get('host') == socket.gethostname() else None
                if last:
                    quiet_holder(cfg, state, repo, ref, role, holder, last, start,
                                 lambda: message_codex(codex['thread'], nudge_text(cfg, ref, iso(last))), release=False)
                continue
            if (holder and holder not in role['sessions']) or (not holder and not pushes(role)) or (
                    not holder and taken_elsewhere(cfg, state, repo, issue['number'])):
                continue  # another worker or another computer holds it: nothing to watch here; health reports it
            sid = holder_of(state, role, ref)
            if not sid:
                continue
            last = session_activity(cfg, sid)
            if last is None:
                every = dt.timedelta(minutes=cfg['check_minutes'])
                if cfg['check_minutes'] and start - parse_time(issue['updatedAt']) >= idle and (
                        ref not in checks or start - parse_time(checks[ref]) >= every):
                    plan.append(('held', ref, role, issue['title'], None, sid))
                    checks[ref] = iso(start)
                continue
            quiet_holder(cfg, state, repo, ref, role, sid, last, start,
                         lambda: plan.append(('nudge', ref, role, issue['title'], iso(last), sid)))
    for table in (nudges, checks, state.setdefault('holders', {}), state.setdefault('claim_hosts', {})):
        for ref in [r for r in table if r.startswith(repo + '#') and r not in held]:
            del table[ref]
    resolved = sorted(told - {r for r, n in nudges.items() if n.get('told')})
    if resolved:  # the owner was told it was stuck; it moved on (finished, or taken again): say so and close
        still = [r for r, n in nudges.items() if n.get('told')]
        report_health(cfg, state, [], close=not still, done=resolved)


def check_prs(cfg, state, repo, start, issues=()):
    """Hourly: an open pull request untouched for stale_pr_days becomes a task for the default role (once per stall)."""
    if not cfg['stale_pr_days']:
        return
    seen = state.setdefault('prs', {})
    last = seen.get(f'{repo}:checked')
    if last and start - parse_time(last) < dt.timedelta(hours=1):
        return
    seen[f'{repo}:checked'] = iso(start)
    role = default_role(cfg)
    for pr in gh_json('pr', 'list', '-R', repo, '--state', 'open', '--limit', '100',
                      '--json', 'number,title,updatedAt,url,isDraft'):
        key = f"{repo}#{pr['number']}"
        if start - parse_time(pr['updatedAt']) < dt.timedelta(days=cfg['stale_pr_days']) or seen.get(key) == pr['updatedAt']:
            continue
        texts = cfg['texts']
        title = texts['stale_pr_title'].format(number=pr['number'], days=cfg['stale_pr_days'])
        if any(i['title'] == title for i in issues):  # another dispatcher already opened it
            seen[key] = pr['updatedAt']
            continue
        create_issue(repo, title,
                     "🤖 health: " + texts['stale_pr_body'].format(url=pr['url'], title=pr['title'], updated=pr['updatedAt']),
                     [role['label']])
        seen[key] = pr['updatedAt']


def check_tests(cfg, state, repo, start, plan):
    """Batched test mode: every N finished tasks the watcher runs the full suite itself, detached, in its own checkout
    (no tokens). Green is recorded; red wakes the checker once with the commit range since the last green run."""
    t = cfg['tests']
    if t['mode'] != 'batched' or not t['full'] or not t['checkout'] or repo != cfg['repos'][0]:
        return
    if t.get('host') and t['host'] != socket.gethostname():
        return  # with several dispatchers, the full suite runs on one computer
    ts = state.setdefault('tests', {})
    base = cfg['state_file'] + '.tests'
    run = ts.get('running')
    if run:
        code_file = f"{base}.{run['id']}.code"
        if os.path.exists(code_file):
            with open(code_file, encoding='utf-8') as f:
                code = f.read().strip()
            sha = open(f"{base}.{run['id']}.sha", encoding='utf-8').read().strip() if os.path.exists(f"{base}.{run['id']}.sha") else '?'
            ok = code == '0'
        elif start - parse_time(run['at']) > dt.timedelta(minutes=t['timeout_minutes']):
            try:
                kill_tree(run['pid'])
            except OSError:
                pass
            ok, sha = False, run.get('sha', '?')
        else:
            return
        ts.pop('running')
        log = f"{base}.{run['id']}.log"
        ts['last'] = {'sha': sha, 'ok': ok, 'at': iso(start), 'log': log}
        if ok:
            ts['green'] = sha
        else:
            role = tests_role(cfg)
            line = cfg['texts']['tests_red'].format(sha=sha, green=ts.get('green') or 'none yet', log=log,
                                                    priority=cfg['labels']['priority'])
            plan.append(('tests_red', sha, role, line, None, role['session']))
        return
    ts.setdefault('since', iso(start))
    last = ts.get('counted')
    if last and start - parse_time(last) < dt.timedelta(minutes=5):
        return
    ts['counted'] = iso(start)
    not_tasks = {cfg['labels']['batch'], cfg['labels']['health']}
    done = [i for i in gh_json('issue', 'list', '-R', repo, '--state', 'closed', '--limit', '200', '--search',
                               f"closed:>={ts['since']}", '--json', 'number,labels,closedAt,stateReason')
            if parse_time(i['closedAt']) >= parse_time(ts['since']) and i.get('stateReason') != 'NOT_PLANNED'
            and not not_tasks & set(labels_of(i))]
    if len(done) < int(t['every']):
        return
    run_id = start.strftime('%Y%m%d%H%M%S')
    co = shlex_quote(t['checkout'])
    script = (f"cd {co} && git fetch -q origin && git checkout -q --detach origin/{shlex_quote(t['branch'])} && "
              f"git rev-parse HEAD > {shlex_quote(base + '.' + run_id + '.sha')} && ({t['full']}); "
              f"echo $? > {shlex_quote(base + '.' + run_id + '.code')}")
    with open(f'{base}.{run_id}.log', 'w', encoding='utf-8') as log:
        proc = subprocess.Popen(shell_script(script), stdout=log, stderr=subprocess.STDOUT, **detached())
    ts['running'] = {'id': run_id, 'pid': proc.pid, 'at': iso(start)}
    ts['since'] = iso(start)


def build_plan(cfg, state, start):
    """Read the board; return the steps for the dispatcher. An owner's comment stays in the plan until a brief
    delivers it (up to forward_hours), so a missed plan or a stopped watcher loses nothing."""
    owners = set(cfg['owner_accounts'])
    labels = cfg['labels']
    waiting_word = {labels['question'], labels['owner_word']}
    window = start - dt.timedelta(hours=cfg['forward_hours'])
    delivered = load_delivered(cfg)
    plan = []
    boards = {}
    for repo in cfg['repos']:
        issues = real_board(cfg, state, repo)
        primary = cfg['primary']
        if primary:
            release_waits(cfg, state, repo, issues, start)
        boards[repo] = {'at': iso(start), 'issues': issues}
        taken = set()
        news, fresh = {}, []
        first = delivered is None or repo not in delivered
        urgent = state.setdefault('urgent', {})
        for item in gh_json('issue', 'list', '-R', repo, '--state', 'all', '--limit', '100',
                            '--search', f'updated:>={iso(window)}', '--json', 'number,title,labels,state,comments,body,author'):
            if primary:
                mark_urgent(cfg, repo, item, issues, urgent)
            answered_at = max([c['createdAt'] for c in item.get('comments', [])
                               if login_of(c) == cfg['agent_account']] or [''])
            # first run: only words on an open issue that waits for the owner or is in progress, with no agent
            # comment after them, may not have reached a role; everything else counts as delivered
            if labels['health'] in labels_of(item):
                continue  # the owner's report, not a task
            open_wait = item.get('state', 'OPEN') == 'OPEN' and (waiting_word | {labels['working']}) & set(labels_of(item))
            for c in item.get('comments', []):
                if login_of(c) not in owners or not window <= parse_time(c['createdAt']) <= start:
                    continue
                if first and (c['createdAt'] < answered_at or not open_wait):
                    fresh.append(c)
                elif first or comment_key(c) not in delivered[repo]:
                    news.setdefault(item['number'], (item, []))[1].append(c['createdAt'])
        if first:
            mark_delivered(cfg, repo, fresh, cfg['forward_hours'])
        held = {i['number']: i for i in issues}
        for number, (item, times) in sorted(news.items()):
            if number in held:
                item = {**item, 'labels': held[number]['labels']}  # without a working label the owner set
            names = labels_of(item)
            role = role_of_labels(cfg, names)
            ref = f'{repo}#{number}'
            is_open = item.get('state', 'OPEN') == 'OPEN'
            if is_open and not primary and (waiting_word & set(names) or (
                    labels['working'] not in names and (cfg['skip'] - {labels['health']}) & set(names))):
                continue  # the main computer's dispatcher hands it back
            if is_open and waiting_word & set(names):
                role = role or default_role(cfg)
                plan.append(('answered', ref, role, item['title'], None))
                taken.add(role['role'])
            elif is_open and labels['working'] not in names and (cfg['skip'] - {labels['health']}) & set(names):
                role = role or default_role(cfg)  # set aside (deferred, waiting…), and the owner wrote on it:
                plan.append(('parked', ref, role, item['title'], None))  # back to the role, which reads the words
                taken.add(role['role'])
            elif not is_open or labels['working'] in names or cfg['skip'] & set(names):
                role = role or default_role(cfg)
                holder = state.get('holders', {}).get(ref)
                if (holder and holder not in role['sessions']) or (not pushes(role) and not holder):
                    continue  # a pulling worker reads new words when it runs `agentq done`
                claims = [m.group(1) for c in item.get('comments', []) for m in [CLAIM_MARK.search(c.get('body') or '')] if m]
                if claims and claims[-1].split('/')[0] != socket.gethostname():
                    continue  # another computer's dispatcher holds this task and forwards the words
                plan.append(('forward', ref, role, item['title'], min(times), holder_of(state, role, ref)))
            # an open issue without a role is classified below; a queued one carries the words in its brief
        check_held(cfg, state, repo, issues, start, plan)
        if primary:
            check_prs(cfg, state, repo, start, issues)
            check_tests(cfg, state, repo, start, plan)
        wake_codex(cfg, state, repo, issues, start)
        cache = {}
        for role in cfg['roles']:
            if not pushes(role) and role.get('active') == 0 and role['sessions']:
                # no Claude session works this role (`scale 0`), but a task kept for Claude (the owner's word, or a
                # Codex worker's hand-over after three tries) must still reach one: a free resting session gets it
                held = set(state.get('holders', {}).values())
                free = [s for s in role['sessions'] if s not in held]
                kept = [i for i in issues if kept_for(cfg, i) == 'claude']
                issue = next_issue(cfg, kept, role, (), 'claude')
                if issue and free:
                    plan.append(('assign_session', f"{repo}#{issue['number']}", role, issue['title'], None, free[0]))
            if not pushes(role):
                continue  # its workers take their own tasks with `agentq next`
            pulling = waiting_workers(cfg, role) & set(role['pool'])  # they take their next task themselves
            slots = capacity(role) - len(session_held(cfg, state, role, repo, busy_with(cfg, issues, role))) \
                - len(pulling) - (role['role'] in taken)
            picked = []
            while slots > 0:
                issue = next_issue(cfg, issues, role, picked, 'claude')
                if not issue:
                    break
                picked.append(issue['number'])
                plan.append(('assign', f"{repo}#{issue['number']}", role, issue['title'], None))
                slots -= 1
            if primary and slots > 0 and role['mode'] == 'checker' and not busy_with(cfg, issues, role) and role['sessions'] and \
                    batch_ready(cfg, role, unchecked(cfg, state, repo, role, cache), start):
                plan.append(('batch', repo, role, None, None))
        skip = cfg['skip'] | {labels['working'], labels['batch']}
        loose = [i for i in sorted(issues, key=lambda i: i['number'])
                 if not role_of_labels(cfg, labels_of(i)) and not skip & set(labels_of(i)) and trusted(cfg, i)]
        for issue in loose[:10] if primary else []:
            plan.append(('classify', f"{repo}#{issue['number']}", None, issue['title'], None))
    save_board(cfg, boards)
    return plan


def render_plan(cfg, plan, start, clear=False, wake=False):
    q = 'agentq'
    lines = [f'agentq plan {iso(start)} – do every step in order, without asking anyone. The session ids come from '
             f'the config and are current, even when they differ from ids you saw before (the owner may replace a session).']
    for n, (kind, ref, role, title, since, *rest) in enumerate(plan, 1):
        sid = rest[0] if rest else None
        if kind == 'forward':
            line = cfg['texts']['send_news'].format(ref=ref, since=since)
            lines.append(f'{n}. the owner wrote on {ref} ({role["role"]}): send this line to {session_of(role, sid)}: `{line}`')
        elif kind == 'parked':
            lines.append(f'{n}. the owner wrote on {ref}, which was set aside: run `{q} assign {ref} {role["role"]} '
                         f'--unpark` and do what it prints.')
        elif kind == 'answered':
            lines.append(f'{n}. the owner answered on {ref}: run `{q} assign {ref} {role["role"]}` and do what it prints.')
        elif kind == 'assign':
            lines.append(f'{n}. next task for {role["role"]}: run `{q} assign {ref} {role["role"]}` and do what it prints.')
        elif kind == 'assign_session':
            lines.append(f'{n}. {ref} is kept for Claude and no Claude session works as {role["role"]} now: run '
                         f'`{q} assign {ref} {role["role"]} --session {sid}` and do what it prints.')
        elif kind == 'nudge':
            line = nudge_text(cfg, ref, since)
            lines.append(f'{n}. {role["role"]} holds {ref} but has been quiet since {since}: send this line to '
                         f'{session_of(role, sid)}: `{line}`')
        elif kind == 'tests_red':
            lines.append(f'{n}. the full test run is red at {ref}: send this line to {session_of(role, sid)}: `{title}`')
        elif kind == 'held':
            lines.append(f'{n}. {role["role"]} holds {ref}: call get_session for {sid or role["session"]}, then run '
                         f'`{q} held {ref} --running <its isRunning> --last <its lastActivityAt>` and do what it prints.')
        elif kind == 'batch':
            lines.append(f'{n}. a batch is ready for {role["role"]}: run `{q} batch {role["role"]} -R {ref}` '
                         f'and do what it prints.')
        else:
            moving = (f' If all of it belongs to a linked project in roles.md, run `{q} move {ref} <owner/repo>` '
                      f'instead.') if cfg['links'] else ''
            lines.append(f'{n}. classify {ref} "{one_line(title, 80)}": pick a role (roles.md; unsure → '
                         f'{cfg["default_role"]}), run `{q} assign {ref} <role>` and do what it prints.{moving}')
    if wake:  # a Codex dispatcher: its watcher keeps running
        lines.append('Last: end your turn – the watcher keeps running and sends the next plan here.')
    elif clear:  # the dispatcher needs no memory: the board and its files hold everything
        lines.append(f'Last: start `{q} watch` again in the background, then call clear_session with session_id "self".')
    else:
        lines.append(f'Last: start `{q} watch` again in the background.')
    return '\n'.join(lines)


def start_codex_watcher(cfg, opts, who):
    """A Codex dispatcher never waits in a command (Codex checks a running command with a model call every minute):
    the watcher runs on its own and sends each plan to the dispatcher's Codex task as a message."""
    thread = os.environ.get('CODEX_THREAD_ID')
    if not thread:
        print('agentq watch: no CODEX_THREAD_ID, so no plan could reach this task – run it from a Codex task.')
        return 1
    update_state(cfg, lambda data: data.__setitem__('dispatcher_thread', thread))
    lock = watch_lock(cfg, who)
    if lock is None:
        print('agentq watch: already running – it sends each plan to this task now. End your turn.')
        return 0
    lock.close()
    args = [sys.executable, SELF, '--config', cfg['_path'], 'watch', '--wake']
    for name in ('interval', 'max_minutes'):
        if getattr(opts, name) is not None:
            args += [f"--{name.replace('_', '-')}", str(getattr(opts, name))]
    with open(cfg['state_file'] + '.watch.log', 'a') as log:
        child = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, **detached())
    for _ in range(50):  # up to 10 s for it to take its lock
        if child.poll() is not None:
            break
        held = watch_lock(cfg, who)
        if held is None:
            print('agentq watch: the watcher runs on its own now and sends each plan to this task as a message. '
                  'End your turn.')
            return 0
        held.close()
        time.sleep(0.2)
    print(f"agentq watch: the watcher did not start – see {cfg['state_file']}.watch.log. Tell the owner.")
    return 1


def cmd_watch(cfg, opts):
    here = running_in()
    agent = cfg['dispatcher']['agent']
    if here and agent != 'both' and here != agent:  # the team moved: this dispatcher stops, the other one runs
        print(f"agentq watch: this team's dispatcher runs on {agent} now – stop this loop.")
        return 1
    who = here if agent == 'both' else None
    if here == 'codex' and not opts.once and not opts.wake:
        return start_codex_watcher(cfg, opts, who)
    lock = watch_lock(cfg, who)
    if lock is None:
        print('agentq watch: already running – nothing to do.')
        return 0
    interval = cfg['poll_seconds'] if opts.interval is None else opts.interval
    code = code_stamp(cfg['_path'])
    parent = session_parent()
    deadline = time.time() + 60 * opts.max_minutes if opts.max_minutes is not None else None
    while True:
        if deadline is not None and time.time() >= deadline:
            print('agentq watch: no work yet – run it again.')
            return 0
        if not opts.wake and parent_gone(parent):  # started with & or nohup: its end would wake nobody
            print('agentq watch: not started by the session (its parent is gone) – start it with run_in_background.')
            return 1
        restart_if_updated(code, lock, detach=opts.wake, watched=(cfg['_path'],))
        state = load_state(cfg)
        start = now()
        work = copy.deepcopy(state)
        if state.get('paused'):  # the team is paused: stay alive, send nothing
            state['watch'] = {**state.get('watch', {}), 'pid': os.getpid(), 'beat': iso(start)}
            state['watch'].pop('error', None)
            save_state(cfg, state)
            if opts.once:
                print(f"agentq watch: paused since {state['paused']['at']} – {state['paused']['why']}")
                return 0
            time.sleep(interval)
            continue
        try:
            plan = build_plan(cfg, work, start)
            if here == 'codex':  # the Codex life: it sorts tasks; Claude sessions are the Claude dispatcher's to reach
                plan = [step for step in plan if step[0] in ('classify', 'answered', 'parked')]
        except Fail as e:
            state['watch'] = {'pid': os.getpid(), 'beat': iso(start), 'error': str(e)}
            save_state(cfg, state)
            if opts.once:
                raise
        else:
            last = state.get('watch', {})
            count = state.get('plans', 0) + 1
            clear = bool(cfg['clear_every']) and count % int(cfg['clear_every']) == 0
            text = render_plan(cfg, plan, start, clear, opts.wake) if plan else ''
            body = text.split('\n', 1)[-1]
            work['watch'] = {'pid': os.getpid(), 'beat': iso(start), 'plan': last.get('plan'), 'sent': last.get('sent')}
            if plan and body == last.get('plan') and start - parse_time(last['sent']) < dt.timedelta(minutes=cfg['repeat_minutes']):
                plan = None  # the dispatcher did not act on this plan: do not wake it every minute for it
            elif plan and opts.wake:  # a Codex dispatcher: the plan goes to its task as a message
                accepted, error = message_codex(state.get('dispatcher_thread') or '-', text)
                if not accepted:
                    work['watch']['error'] = f'the plan did not reach the dispatcher: {error}'
                    plan = None  # tried again at the next poll
            if plan:
                work['watch'].update(exited=iso(start), plan=body, sent=iso(start))
                work['plans'] = count
            save_state(cfg, work)
            if plan and not opts.wake:
                print(text)
                return 0
            if opts.once:
                print('agentq watch: plan sent to the dispatcher.' if plan else 'agentq watch: no work.')
                return 0
        time.sleep(interval)


def wake_codex(cfg, state, repo, issues, start):
    """Idle Codex workers of this computer get their next task without tokens: the watcher claims it for them and
    queues one message for their Codex task. While Claude sessions wait for the same role, the teams take turns."""
    host = socket.gethostname()
    held_by = set(state.get('holders', {}).values())
    taken = []
    workers = state.get('codex', {})
    for worker in sorted(workers, key=lambda w: workers[w].get('idle') or workers[w].get('finished') or ''):
        info = workers[worker]
        if info.get('host') != host or worker in held_by:
            continue
        seen = (info.get('idle'), info.get('finished'))
        if not seen[0]:
            last = codex_activity(info['thread']) if seen[1] else None
            if not last or start - last < dt.timedelta(minutes=2):
                continue  # busy, or it may still run `agentq next` itself
        turns = state.get('last_team', {})
        roles = [r for r in cfg['roles'] if r['role'] in info.get('roles', []) and pulls(r)
                 and not (turns.get(r['role']) == 'codex' and waiting_workers(cfg, r))]
        if not any(next_issue(cfg, issues, r, taken, 'codex') or r['mode'] == 'checker' for r in roles):
            continue
        if not codex_activity(info['thread']):
            continue  # the owner archived or deleted this Codex task: it gets nothing
        if not codex_reachable(info['thread']):
            continue  # Codex is closed: the task waits for Claude, or until the owner opens Codex
        if not update_state(cfg, lambda data: reserve_codex(data, worker, seen, (None, None))):
            continue  # another watcher on this computer woke it a moment ago
        ref, role = take_next(cfg, state, repo, issues, roles, worker, 'codex', taken)
        if not ref:
            update_state(cfg, lambda data: reserve_codex(data, worker, (None, None), seen))
            continue
        info['idle'] = info['finished'] = None
        update_state(cfg, lambda data: data.setdefault('holders', {}).__setitem__(ref, worker))
        number = int(ref.split('#')[1])
        taken.append(number)
        for issue in issues:
            if issue['number'] == number:
                issue['labels'] = issue['labels'] + [{'name': cfg['labels']['working']}]
        text = cfg['texts']['wake_task'].format(ref=ref, role=role['role'], worker=worker,
                                                agentq=self_command(), next=info.get('next'))
        accepted, error = message_codex(info['thread'], text)
        if accepted:  # it may run any moment: the task stays its own; a reminder follows if it stays quiet
            info['error'] = error
        else:  # undone: the task back in the queue, the worker idle again for the next poll
            comment(cfg, repo, number, cfg['texts']['codex_unreached'].format(worker=worker, error=error), 'health')
            relabel(repo, number, remove=[cfg['labels']['working']])

            def undo(data):
                if data.get('holders', {}).get(ref) == worker:
                    del data['holders'][ref]
                if worker in data.get('codex', {}):
                    data['codex'][worker].update(idle=seen[0] or seen[1], finished=None, error=error)
            update_state(cfg, undo)
            state['holders'].pop(ref, None)
            info.update(idle=seen[0] or seen[1], finished=None, error=error)


def cmd_held(cfg, opts):
    """A role holds a task: is its session working on it? Remind it once when idle; tell the owner when that did not help."""
    repo, number = resolve(cfg, opts.issue)
    ref = f'{repo}#{number}'
    state = load_state(cfg)
    nudges = state.setdefault('nudges', {})
    moment = now()
    issue = view(repo, number)
    role = role_of_labels(cfg, labels_of(issue)) or default_role(cfg)
    if issue.get('state', 'OPEN') != 'OPEN' or cfg['labels']['working'] not in labels_of(issue):
        nudges.pop(ref, None)
        save_state(cfg, state)
        print(f'{ref} is not held any more – nothing to do.')
        return
    last = parse_time(opts.last)
    running = opts.running.strip().lower() in ('true', 'yes', '1', 'running')
    nudge = nudges.get(ref)
    if nudge and last > parse_time(nudge['at']):
        nudges.pop(ref)  # it reacted to the reminder
        nudge = None
    if running or moment - last < dt.timedelta(minutes=cfg['idle_minutes']):
        save_state(cfg, state)
        print(f"{role['role']} is working on {ref} – nothing to do.")
        return
    if nudge is None:
        nudges[ref] = {'at': iso(moment)}
        save_state(cfg, state)
        print(f"{role['role']} holds {ref} but has been idle since {iso(last)}. Now:")
        print(f'1. send this line to {session_of(role, holder_of(state, role, ref))}: `{nudge_text(cfg, ref, iso(last))}`')
        return
    if moment - parse_time(nudge['at']) >= dt.timedelta(minutes=cfg['escalate_minutes']) and not nudge.get('told'):
        problem = cfg['texts']['stalled'].format(role=role['role'], ref=ref, session=holder_of(state, role, ref) or '-',
                                                  last=iso(last), at=nudge['at'])
        where = report_health(cfg, state, [problem], needs_owner=True, close=False)
        nudge['told'] = iso(moment)
        save_state(cfg, state)
        print(f'told the owner in {repo}#{where} – nothing to send.')
        return
    print(f"reminded {role['role']} at {nudge['at']}; waiting – nothing to do.")


def nudge_text(cfg, ref, last):
    return cfg['texts']['nudge'].format(ref=ref, label=cfg['labels']['working'], last=last or 'a while')


def cmd_nudge(cfg, opts):
    repo, number = resolve(cfg, opts.issue)
    print(nudge_text(cfg, f'{repo}#{number}', opts.last))
