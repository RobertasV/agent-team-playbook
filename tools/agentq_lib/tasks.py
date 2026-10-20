"""The commands a worker uses on a task: next, assign, done, ask, route, handover, wait, batches."""

import argparse
import datetime as dt
import json
import os
import re
import socket
import time
from shlex import quote as shlex_quote

from .system import code_stamp, parent_gone, restart_if_updated, running_in, self_command, session_parent
from .base import BATCH_MARK, Fail, iso, now, one_line, parse_time, ROUTE_MARK, WAIT_MARK
from .github import claim, comment, gh, gh_json, labels_of, login_of, open_issues, relabel, resolve, view
from .config import (
    agent_labels, capacity, checked_label, default_role, holder, pulls, pushes, role_by_name, role_of_labels
)
from .state import (
    load_state, mark_delivered, mark_waiting, read_state_file, save_state, unmark_waiting, update_state,
    waiting_workers
)
from .lessons import load_lessons, save_lessons
from .apps import codex_here, codex_waits, session_of, worker_title
from .board import (
    batch_ready, busy_with, create_batch, free_session, real_board, session_held, shared_board, take_next,
    unchecked
)
from .brief import cmd_brief, unread_words


def cmd_queue(cfg, opts):
    state = load_state(cfg)
    started = now()
    lines = []
    for repo in cfg['repos']:
        since = state.get(repo, {}).get('last')
        issues = open_issues(repo)
        if since is None:
            lines.append(f'{repo}: first run – owner comments from now on will be shown.')
        else:
            since_t = parse_time(since)
            news = []
            for issue in issues:
                for c in issue.get('comments', []):
                    if c['author']['login'] in cfg['owner_accounts'] and parse_time(c['createdAt']) > since_t:
                        news.append(f"  {repo}#{issue['number']} {one_line(issue['title'], 60)}: {one_line(c['body'])}")
            lines.append(f'{repo}: owner comments since {since}: {len(news) or "none"}')
            lines.extend(news)
        working, todo, skipped = [], [], {}
        for issue in sorted(issues, key=lambda i: i['number']):
            names = labels_of(issue)
            hit = [n for n in names if n in cfg['skip']]
            row = f"  {repo}#{issue['number']} [{', '.join(names)}] {one_line(issue['title'], 100)}"
            if cfg['labels']['working'] in names:
                working.append(row)
            elif hit:
                for n in hit:
                    skipped[n] = skipped.get(n, 0) + 1
            else:
                todo.append(row)
        if working:
            lines.append(f'{repo}: in progress ({len(working)}):')
            lines.extend(working)
        lines.append(f'{repo}: queue ({len(todo)}):')
        lines.extend(todo)
        if opts.all and skipped:
            lines.append('  skipped: ' + ', '.join(f'{k} {v}' for k, v in sorted(skipped.items())))
        state.setdefault(repo, {})['last'] = iso(started)
    print('\n'.join(lines))
    if not opts.peek:
        save_state(cfg, state)


def cmd_take(cfg, opts):
    """Start (or resume) a task: working again, no longer waiting for the owner, held by this session or Codex task."""
    repo, number = resolve(cfg, opts.issue)
    issue = view(repo, number)
    labels = cfg['labels']
    comment(cfg, repo, number, cfg['texts']['take'], holder(cfg, issue))
    relabel(repo, number, add=[labels['working']],
            remove=[n for n in {labels['question'], labels['owner_word']} if n in labels_of(issue)])
    here = running_in()
    worker = os.environ.get('CLAUDE_CODE_HOST_SESSION_ID') if here == 'claude' else \
        codex_here(read_state_file(cfg))[0] if here == 'codex' else None
    if worker:  # so reminders and the owner's words go to whoever really works on it
        update_state(cfg, lambda data: data.setdefault('holders', {}).__setitem__(f'{repo}#{number}', worker))
    print(f'{repo}#{number}: taken')


def ask_owner(cfg, repo, number, text, who):
    comment(cfg, repo, number, cfg['texts']['ask'].format(text=text), who)
    relabel(repo, number, add=[cfg['labels']['question']], remove=[cfg['labels']['working']])


def cmd_ask(cfg, opts):
    repo, number = resolve(cfg, opts.issue)
    ask_owner(cfg, repo, number, opts.text, holder(cfg, view(repo, number)))
    print(f'{repo}#{number}: asked the owner, out of the queue')


def cmd_defer(cfg, opts):
    repo, number = resolve(cfg, opts.issue)
    who = holder(cfg, view(repo, number))
    comment(cfg, repo, number, cfg['texts']['defer'].format(text=opts.text or '').strip(), who)
    relabel(repo, number, add=[cfg['labels']['deferred']], remove=[cfg['labels']['working']])
    print(f'{repo}#{number}: deferred')


def cmd_wait(cfg, opts):
    repo, number = resolve(cfg, opts.issue)
    m = re.match(r'^([\w.-]+/[\w.-]+)#(\d+)$', opts.other.strip())
    if not m:
        raise Fail(f'"{opts.other}" must be owner/repo#N')
    ref = f'{m.group(1)}#{m.group(2)}'
    text = cfg['texts']['wait'].format(ref=ref) + f'\n<!-- agentq:wait {ref} -->'
    comment(cfg, repo, number, text, holder(cfg, view(repo, number)))
    relabel(repo, number, add=[cfg['labels']['waiting']], remove=[cfg['labels']['working']])
    print(f'{repo}#{number}: waits for {ref}')


def cmd_check(cfg, opts):
    moment = now()
    stale = dt.timedelta(hours=cfg['stale_hours'])
    report, fixed = [], []
    for repo in cfg['repos']:
        for issue in open_issues(repo):
            names = labels_of(issue)
            tag = f"{repo}#{issue['number']}"
            comments = issue.get('comments', [])
            if cfg['labels']['working'] in names and moment - parse_time(issue['updatedAt']) > stale:
                report.append(f"{tag}: '{cfg['labels']['working']}' but nothing happened for over {cfg['stale_hours']} h")
            if comments and comments[-1]['author']['login'] in cfg['owner_accounts']:
                report.append(f"{tag}: the owner's comment waits for an answer – {one_line(comments[-1]['body'], 120)}")
            if cfg['labels']['waiting'] in names:
                marks = [m for c in comments for m in WAIT_MARK.findall(c.get('body', ''))]
                if not marks:
                    report.append(f"{tag}: '{cfg['labels']['waiting']}' without a recorded issue to wait for")
                    continue
                other, other_n = marks[-1]
                ref = f'{other}#{other_n}'
                info = gh_json('issue', 'view', other_n, '-R', other, '--json', 'state')
                if info.get('state') == 'CLOSED':
                    if opts.fix:
                        comment(cfg, repo, issue['number'], cfg['texts']['back'].format(ref=ref))
                        relabel(repo, issue['number'], remove=[cfg['labels']['waiting']])
                        fixed.append(f'{tag}: {ref} closed – back in the queue')
                    else:
                        report.append(f'{tag}: {ref} is closed – run check --fix to put it back in the queue')
        done = gh_json('issue', 'list', '-R', repo, '--state', 'closed', '--label', cfg['labels']['working'],
                       '--limit', '100', '--json', 'number')
        for issue in done:
            tag = f"{repo}#{issue['number']}"
            if opts.fix:
                relabel(repo, issue['number'], remove=[cfg['labels']['working']])
                fixed.append(f"{tag}: closed – '{cfg['labels']['working']}' removed")
            else:
                report.append(f"{tag}: closed but still '{cfg['labels']['working']}'")
    for line in fixed:
        print('fixed  ' + line)
    for line in report:
        print('check  ' + line)
    if not fixed and not report:
        print('all consistent')


def session_settings(cfg, state, role, issue_labels, batch, sid=None):
    """The model and effort this task needs; a line for each that differs from what was last set."""
    want = {'model': role['model'], 'effort': role['effort']}
    if role['mode'] == 'checker' and not batch and role['release_model']:
        want['model'] = role['release_model']
    if cfg['labels']['hard'] in issue_labels and role['hard_effort']:
        want['effort'] = role['hard_effort']
    sid = sid or role['session']
    last = state.setdefault('sessions', {}).setdefault(sid or role['role'], {})
    lines = []
    for key, tool in (('model', 'set_session_model'), ('effort', 'set_session_effort')):
        if want[key] and want[key] != last.get(key):
            lines.append(f'{tool} for {session_of(role, sid)}: {want[key]}')
            last[key] = want[key]
    return lines


def print_send(cfg, state, role, ref, issue_labels, batch=False, sid=None):
    steps = session_settings(cfg, state, role, issue_labels, batch, sid)
    line = cfg['texts']['send_task'].format(ref=ref, role=role['role'])
    steps.append(f'send this line to {session_of(role, sid)}: `{line}`')
    for n, step in enumerate(steps, 1):
        print(f'{n}. {step}')


def note_finished(cfg):
    """A Codex worker finished a task: should its turn end without `agentq next`, the watcher still wakes it."""
    if running_in() != 'codex' or not os.environ.get('CODEX_THREAD_ID'):
        return

    def change(data):
        _, info = codex_here(data)
        if info is not None:
            info['finished'] = iso(now())
    update_state(cfg, change)


def cmd_next(cfg, opts):
    """Take the next task and print its brief – the way every worker gets work. One role, or without a role any role
    this worker may pull for. A Claude session runs it with --wait in the background: it waits without tokens and
    wakes the session with the task. A Codex task never waits – Codex checks a running command with a model call
    every minute: with no task it ends its turn, and the watcher claims the next task for it and sends it a message."""
    here = running_in()
    host = socket.gethostname()
    session = os.environ.get('CLAUDE_CODE_HOST_SESSION_ID') if here == 'claude' else None
    thread = os.environ.get('CODEX_THREAD_ID') if here == 'codex' else None
    worker = opts.who or session or (f'codex-{thread[:8]}' if thread else None) or \
        f"{host.split('.')[0]}-{opts.role or 'team'}"

    def may(role):  # a role's own Claude session, or any worker of a role that pulls
        return worker in role['sessions'] or pulls(role)
    wanted = [role_by_name(cfg, opts.role)] if opts.role else cfg['roles']
    roles = [r for r in wanted if may(r)]
    again = ' '.join([self_command(), 'next', *([shlex_quote(opts.role)] if opts.role else []),
                      '--as', shlex_quote(worker)])
    if thread:  # the watcher wakes this Codex task when one of these roles has work
        record = {'thread': thread, 'host': host, 'roles': [r['role'] for r in wanted], 'next': again}

        def register(data):  # one Codex task is one worker: a new name for the same task replaces the old one
            workers = data.setdefault('codex', {})
            for other in [w for w, i in workers.items() if i.get('thread') == thread and w != worker]:
                del workers[other]
            workers[worker] = {**record, 'idle': None}
        update_state(cfg, register)

    if not roles:
        if thread:
            update_state(cfg, lambda data: data['codex'][worker].__setitem__('idle', iso(now())))
            print(f"{', '.join(r['role'] for r in wanted)} does not take Codex workers now (agent: claude). End your "
                  f"turn: agentq sends this task a message when it does again.")
            return 0
        if opts.role:
            print(f"{wanted[0]['role']} does not pull (agent: claude) and {worker} is not its session: the dispatcher "
                  f"sends its tasks. Stop this loop.")
        else:
            print('no role this worker may pull for – `agentq role <name> --agent codex|both` first.')
        return 1
    agent = 'claude' if worker in {x for r in roles for x in r['sessions']} or here == 'claude' else 'codex'
    ids = {worker, session} - {None}  # a Claude session is known by its id even when it runs under another name

    def rests(role):  # a Claude worker outside the role's working sessions (`agentq scale`): no new tasks
        return agent == 'claude' and (role.get('active') == 0 or (bool(role['sessions']) and not ids & set(role['pool'])))
    resting = [r for r in roles if rests(r)]
    wait = opts.wait and here != 'codex'
    code = code_stamp()
    parent = session_parent()
    deadline = time.time() + 60 * opts.max_minutes if opts.max_minutes is not None else None
    try:
        while True:
            if wait:
                if parent_gone(parent):
                    print('agentq next: its session is gone – stop.')
                    return 1
                mark_waiting(cfg, worker, [r['role'] for r in roles])
            state = load_state(cfg)
            if not state.get('paused'):
                holders = state.setdefault('holders', {})
                for ref in [r for r, w in holders.items() if w == worker]:  # checked on GitHub, not in a snapshot
                    repo, number = ref.split('#')
                    fresh = view(repo, int(number)) if repo in cfg['repos'] else {}
                    if fresh.get('state', 'OPEN') == 'OPEN' and cfg['labels']['working'] in labels_of(fresh):
                        save_state(cfg, state)
                        print(f'you hold {ref} – finish it first (agentq done / ask / route / wait); its task again:')
                        cmd_brief(cfg, argparse.Namespace(issue=ref, since=None))
                        return 0
                    del holders[ref]
                if resting and len(resting) == len(roles):
                    save_state(cfg, state)
                    print(f"{worker} rests now: it is not one of the {len(resting[0]['pool'])} Claude session(s) that "
                          f"work as {resting[0]['role']} (agentq scale). No new tasks – stop this loop and end your turn.")
                    return 1
                turns = state.get('last_team', {})
                # Claude took this role's last task and a Codex worker waits for one: this one is Codex's turn
                mine = [r for r in roles if r not in resting and not (
                    agent == 'claude' and pulls(r) and turns.get(r['role']) == 'claude' and codex_waits(cfg, state, r))]
                for repo in cfg['repos'] if mine else []:
                    ref, role = take_next(cfg, state, repo, shared_board(cfg, state, repo), mine, worker, agent)
                    if ref:
                        save_state(cfg, state)
                        print(f'{ref} is yours now ({worker}).')
                        cmd_brief(cfg, argparse.Namespace(issue=ref, since=None))
                        return 0
            if thread:
                state.setdefault('codex', {}).setdefault(worker, record)['idle'] = iso(now())
                save_state(cfg, state)
                print(cfg['texts']['codex_idle'])
                return 0
            save_state(cfg, state)
            if here == 'codex':
                print('No task now, and this Codex task has no CODEX_THREAD_ID, so nothing can wake it: end your turn.')
                return 0
            if not wait or (deadline is not None and time.time() >= deadline):
                print(f"nothing yet – run `{again.replace(' --as', ' --wait --as', 1)}` again.")
                return 0
            time.sleep(cfg['poll_seconds'])
            restart_if_updated(code)
    finally:
        if wait:
            unmark_waiting(cfg, worker)


def cmd_assign(cfg, opts):
    repo, number = resolve(cfg, opts.issue)
    role = role_by_name(cfg, opts.role)
    issue = view(repo, number)
    names = labels_of(issue)
    labels = cfg['labels']
    remove = [r['label'] for r in cfg['roles'] if r is not role and r['label'] in names]
    ref = f'{repo}#{number}'
    if opts.queue:  # sorting: the role label only; skip labels (question, deferred, …) stay
        relabel(repo, number, add=[role['label']], remove=remove)
        print(f"{ref} → {role['role']}, in its queue")
        return
    remove += [n for n in {labels['question'], labels['owner_word']} if n in names]  # the owner answered
    if opts.unpark:  # the owner wrote on a set-aside task: the role reads the words and decides (it may defer again)
        remove += [n for n in names if n in cfg['skip'] - {labels['health']} and n not in remove]
    state = load_state(cfg)
    who = cfg['dispatcher']['name']
    only = [labels[f'only_{opts.only}']] if opts.only else []
    if opts.only:  # the owner's word: only that team takes it, from now on
        relabel(repo, number, add=only, remove=[labels[f'only_{a}'] for a in ('claude', 'codex')
                                                if a != opts.only and labels[f'only_{a}'] in names])
        names = [n for n in names if n not in (labels['only_claude'], labels['only_codex'])] + only
    if labels['working'] in names and role['label'] in names and not opts.session:
        print(f"{ref} is already being worked on as {role['role']} – nothing to do.")  # the other dispatcher was first
        return
    if opts.session:  # the owner named a Claude session: it gets the task even if it rests (`scale`)
        sid = opts.session
        if sid not in role['sessions']:
            raise Fail(f"{sid} is not one of {role['role']}'s sessions ({', '.join(role['sessions']) or 'none'})")
        if labels['working'] in names:
            raise Fail(f"{ref} is being worked on – wait until it is back in the queue, or ask the owner")
        if not claim(cfg, repo, number, cfg['texts']['assign'].format(role=role['role']), who,
                     name=worker_title(cfg, sid)):
            print(f'{ref}: another dispatcher took it a moment earlier. Nothing to send.')
            return
        relabel(repo, number, add=[role['label'], labels['working'], *agent_labels(cfg, 'claude')[0]],
                remove=remove + [n for n in agent_labels(cfg, 'claude')[1] if n in names])
        state.setdefault('holders', {})[ref] = sid
        state.setdefault('last_team', {})[role['role']] = 'claude'
        print(f"{ref} → {role['role']}, working, for session {sid}. Now:")
        print_send(cfg, state, role, ref, names, batch=labels['batch'] in names, sid=sid)
        save_state(cfg, state)
        return
    if not pushes(role) or running_in() == 'codex':  # a Codex dispatcher cannot reach Claude sessions: workers pull
        comment(cfg, repo, number, cfg['texts']['queued'].format(role=role['role']), who)
        relabel(repo, number, add=[role['label']], remove=remove)
        print(f"{ref} → {role['role']}, in its queue; it takes its tasks itself (agentq next). Nothing to send.")
        return
    busy = session_held(cfg, state, role, repo, busy_with(cfg, real_board(cfg, state, repo), role, but=number))
    if len(busy) >= capacity(role) or not role['sessions']:
        comment(cfg, repo, number, cfg['texts']['queued'].format(role=role['role']), who)
        relabel(repo, number, add=[role['label']], remove=remove)
        why = f"its sessions work on #{busy[0]['number']}" if busy else 'no Claude session'
        print(f"{ref} → {role['role']}, queued ({why}). Nothing to send.")
        return
    waiting = waiting_workers(cfg, role)
    sid = free_session(state, role, [f"{repo}#{i['number']}" for i in busy], waiting)
    if sid in waiting:  # every free session waits in `agentq next`: one of them takes it itself – a message too would
        # give it two tasks. Neither a working label nor a claim here: either would keep the worker from taking it
        comment(cfg, repo, number, cfg['texts']['queued'].format(role=role['role']), who)
        relabel(repo, number, add=[role['label']], remove=remove)
        print(f"{ref} → {role['role']}, queued: a free session waiting in `agentq next` takes it itself. Nothing to send.")
        return
    if not claim(cfg, repo, number, cfg['texts']['assign'].format(role=role['role']), who, name=worker_title(cfg, sid)):
        print(f'{ref}: another dispatcher took it a moment earlier. Nothing to send.')
        return
    relabel(repo, number, add=[role['label'], labels['working'], *agent_labels(cfg, 'claude')[0]],
            remove=remove + [n for n in agent_labels(cfg, 'claude')[1] if n in names])
    state.setdefault('holders', {})[ref] = sid
    state.setdefault('last_team', {})[role['role']] = 'claude'
    print(f"{ref} → {role['role']}, working. Now:")
    print_send(cfg, state, role, ref, names, batch=labels['batch'] in names, sid=sid)
    save_state(cfg, state)


def cmd_route(cfg, opts):
    repo, number = resolve(cfg, opts.issue)
    target = role_by_name(cfg, opts.role)
    issue = view(repo, number)
    names = labels_of(issue)
    old = role_of_labels(cfg, names)
    who = old['role'] if old else cfg['role']
    remove = [r['label'] for r in cfg['roles'] if r is not target and r['label'] in names]
    remove += [cfg['labels']['working']] if cfg['labels']['working'] in names else []
    text = cfg['texts']['route'].format(role=target['role'], text=opts.text or '').strip()
    comment(cfg, repo, number, f'{text}\n{ROUTE_MARK}', who)
    relabel(repo, number, add=[target['label']], remove=remove)
    print(f"{repo}#{number} → {target['role']}")
    if opts.no_lesson or (old and old is target):
        return
    lessons = load_lessons(cfg)
    examples = lessons['examples'].setdefault(target['role'], [])
    examples.append({'issue': f'#{number}', 'title': one_line(issue['title'], 100), 'from': who})
    del examples[:-int(cfg['lesson_examples'])]
    save_lessons(cfg, lessons)
    print(f"lesson recorded for the dispatcher: #{number} is {target['role']}'s, not {who}'s")


def cmd_handover(cfg, opts):
    """Three tries and the task still fails: the other team (Claude ↔ Codex) takes it, with what was tried."""
    repo, number = resolve(cfg, opts.issue)
    issue = view(repo, number)
    names = labels_of(issue)
    labels = cfg['labels']
    here = running_in()
    team = here or ('codex' if labels['by_codex'] in names else 'claude')
    other = 'claude' if team == 'codex' else 'codex'
    role = role_of_labels(cfg, names) or default_role(cfg)
    text = cfg['texts']['handover_owner' if opts.owner else 'handover'].format(tries=opts.tries, team=other,
                                                                              text=opts.text).strip()
    comment(cfg, repo, number, f'{text}\n{ROUTE_MARK}', role['role'], team)  # the route mark ends this team's claim
    relabel(repo, number, add=[labels[f'only_{other}']],
            remove=[n for n in (labels['working'], labels[f'only_{team}']) if n in names])
    update_state(cfg, lambda data: data.get('holders', {}).pop(f'{repo}#{number}', None))
    print(f"{repo}#{number} → the {other} team ({role['role']}); only {other} workers take it now")


def cmd_done(cfg, opts):
    repo, number = resolve(cfg, opts.issue)
    issue = view(repo, number)
    unread = unread_words(cfg, repo, number)
    if unread:
        mark_delivered(cfg, repo, unread, cfg['forward_hours'])
        print(f'not closed: the owner wrote on {repo}#{number} while you worked – act on it, then run done again:')
        for c in unread:
            print(f"--- the owner ({login_of(c)}), {c['created_at']} ---\n{(c.get('body') or '').strip()}")
        return 1
    comment(cfg, repo, number, cfg['texts']['done'].format(text=opts.text), holder(cfg, issue))
    if cfg['labels']['working'] in labels_of(issue):
        relabel(repo, number, remove=[cfg['labels']['working']])
    if issue.get('state', 'OPEN') == 'OPEN':
        gh('issue', 'close', str(number), '-R', repo)
    print(f'{repo}#{number}: done')


def cmd_batch(cfg, opts):
    role = role_by_name(cfg, opts.role)
    if role['mode'] != 'checker':
        raise Fail(f'{role["role"]} is not a checker-mode role')
    repo = opts.repo or cfg['repos'][0]
    if repo not in cfg['repos']:
        raise Fail(f'{repo} is not in this config')
    state = load_state(cfg)
    busy = busy_with(cfg, real_board(cfg, state, repo), role)
    if busy:  # it made its batch itself (`agentq next`) since the plan: nothing left to do
        print(f"nothing to do: {role['role']} is already on {repo}#{busy[0]['number']}")
        return
    items = unchecked(cfg, state, repo, role, {})[:20]
    if not items:
        print(f'nothing for {role["role"]} to check')
        return
    if not opts.now and not batch_ready(cfg, role, items, now()):
        print(f'not ready: {len(items)} of {role["n"]}, the oldest closed {items[0]["closedAt"]} (--now to check anyway)')
        return
    ref = create_batch(cfg, state, repo, role, items, agent_labels(cfg, 'claude')[0])
    refs = ' '.join(f"#{i['number']}" for i in items)
    print(f"{ref} created: {role['role']} checks {refs}. Now:")
    print_send(cfg, state, role, ref, [], batch=True)
    save_state(cfg, state)


def cmd_checked(cfg, opts):
    repo, number = resolve(cfg, opts.issue)
    issue = view(repo, number)
    m = BATCH_MARK.search(issue.get('body') or '')
    if not m:
        raise Fail(f'{repo}#{number} is not a batch made by `agentq batch`')
    mark = json.loads(m.group(1))
    role = role_by_name(cfg, mark['role'])
    label = checked_label(cfg, role)
    for n in mark['issues']:
        relabel(repo, n, add=[label])
    refs = ' '.join(f'#{n}' for n in mark['issues'])
    comment(cfg, repo, number, cfg['texts']['checked'].format(refs=refs, text=opts.text or '').strip(), role['role'])
    relabel(repo, number, remove=[cfg['labels']['working']])
    gh('issue', 'close', str(number), '-R', repo)
    print(f"{repo}#{number}: {refs} labelled '{label}', batch closed")
