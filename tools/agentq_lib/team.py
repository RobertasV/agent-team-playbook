"""The owner's words about the team: roles, how many work, Claude or Codex, tests, the running copy, stats."""

import copy
import datetime as dt
import os
import re
import socket
from shlex import quote as shlex_quote

from .system import self_command
from .base import ARROW, CLAIM_MARK, Fail, iso, now, parse_time
from .defaults import DEFAULT_ROLES, PRESETS
from .github import create_issue, gh_json, labels_of, resolve
from .config import default_role, pulls, role_by_name, role_entry, save_config
from .state import load_state, save_state, watcher_running
from .lessons import load_lessons, render_roles, rule_role, save_lessons, write_roles
from .apps import codex_activity
from .board import takers
from .tasks import ask_owner
from .install import ensure_labels, install_dispatcher, print_roles_table, sync_dispatcher_session


def cmd_teach(cfg, opts):
    text = ' '.join(opts.rule.split())
    by = 'owner' if opts.owner else 'agent'
    parts = ARROW.split(text, maxsplit=1)
    topic, role = (parts[0].lower(), rule_role(cfg, parts[1])) if len(parts) == 2 else (None, None)
    if role:
        text = f'{parts[0]} → {parts[1]}'
    lessons = load_lessons(cfg)
    rules = lessons['rules']
    same = [r for r in rules if (topic and r.get('topic') == topic) or r['text'].lower() == text.lower()]
    clash = next((r for r in same if r.get('role') != role), None)
    known = next((r for r in same if r.get('role') == role), None)
    if known and not clash:
        if by == 'owner' and known['by'] != 'owner':
            known['by'] = 'owner'
            save_lessons(cfg, lessons)
        print(f'already a rule: {known["text"]}')
        return
    if clash and by == 'owner' and clash['by'] != 'owner':
        rules.remove(clash)
        print(f'the owner\'s rule replaces "{clash["text"]}"')
    elif clash and by != 'owner' and clash['by'] == 'owner':
        print(f'not written: the owner\'s rule stands – "{clash["text"]}". If it looks wrong, ask the owner.')
        return
    elif clash:
        question = cfg['texts']['rule_question'].format(old=clash['text'], old_by=clash['by'], new=text, new_by=by)
        if opts.issue:
            repo, number = resolve(cfg, opts.issue)
            ask_owner(cfg, repo, number, question, cfg['role'])
            print(f'not written: the rules disagree – asked the owner on {repo}#{number}')
        else:
            repo = cfg['repos'][0]
            number = create_issue(repo, cfg['texts']['rule_title'].format(topic=topic),
                                  f"🤖 {cfg['role']}: {question}", [cfg['labels']['question']])
            print(f'not written: the rules disagree – asked the owner in {repo}#{number}')
        return
    rules.append({'text': text, 'topic': topic, 'role': role, 'by': by, 'at': iso(now())})
    save_lessons(cfg, lessons)
    print(f'rule written: {text} ({by})')


def cmd_pause(cfg, opts):
    """Pause the team: the watcher keeps running but plans nothing until `agentq resume`."""
    state = load_state(cfg)
    state['paused'] = {'at': iso(now()), 'why': opts.text or 'no reason given'}
    save_state(cfg, state)
    print(f"paused: the dispatcher gets no work until `agentq resume` ({state['paused']['why']})")


def cmd_resume(cfg, opts):
    state = load_state(cfg)
    was = state.pop('paused', None)
    save_state(cfg, state)
    print('resumed: the watcher plans again from its next poll' if was else 'was not paused')
    if not watcher_running(cfg):
        print(f"the watcher is not running: send the dispatcher ({cfg['dispatcher']['session'] or 'no session id in the config'}) "
              f'"Start the watcher"')


def cmd_roles(cfg, opts):
    print(render_roles(cfg, load_lessons(cfg)), end='')


def warn_untaken(cfg, roles):
    """Roles nobody on this computer can take tasks for now – said at once, not found hours later."""
    state = load_state(cfg)
    lost = [r['role'] for r in roles if not takers(cfg, state, r)]
    if lost:
        print(f"Nobody on this computer can take {', '.join(lost)} tasks now: no Claude session works the role and no "
              f"Codex worker of it can be woken, so its tasks wait. Create Codex workers: `{self_command()} "
              f"codex-workers --role <role>` prints each one.")


def cmd_scale(cfg, opts):
    """N sessions of a role work in parallel. More than exist: what to start. Fewer: the rest rest and are kept."""
    name = role_by_name(cfg, opts.role)['role']
    if opts.count < 0 or (opts.count == 0 and not pulls(role_by_name(cfg, name))):
        raise Fail(f'at least 1 – {name} works only through its Claude sessions (0 needs Codex workers: '
                   f'`agentq role {name} --agent both`)')

    def change(raw):
        roles = raw.setdefault('roles', [{**r, 'session': ''} for r in DEFAULT_ROLES])
        entry = next(r for r in roles if r['role'] == name)
        entry['active'] = opts.count

    cfg = save_config(cfg, change)
    role = role_by_name(cfg, name)
    have = len(role['sessions'])
    print(f"{name}: {opts.count} sessions work in parallel ({have} exist)." if opts.count else
          f"{name}: no Claude session works – its Codex workers take every task; its {have} session(s) rest, kept.")
    if opts.count > have:
        project = cfg.get('project_name') or cfg['repos'][0].split('/')[-1]
        group = cfg.get('team_group') or 'the team\'s sidebar group (none recorded)'
        print('Now, for each missing session:')
        for m in range(have + 1, opts.count + 1):
            print(f'{m - have}. start a session "{project} {name} {m}" in {cfg.get("checkout") or "the project folder"} '
                  f'(model {role["model"] or "as the role"}, effort {role["effort"] or "as the role"}), move it into '
                  f'{group}, then run `agentq role {name} --add-session <its id>`')
    elif 0 < opts.count < have:
        print(f"Sessions {opts.count + 1}–{have} rest: no new tasks; a task they hold they finish. "
              f"They are kept and reused when the number grows again.")
    write_roles(cfg)
    warn_untaken(cfg, [role])


def cmd_tests(cfg, opts):
    """The test mode in one word: per-task (each task runs the whole suite), batched (the watcher runs it every N tasks)
    or off (no tests: the programmer reads the change once; the checker's batches stay)."""
    if opts.mode:
        def change(raw):
            raw.setdefault('tests', {})['mode'] = opts.mode
        cfg = save_config(cfg, change)
    t = cfg['tests']
    ts = load_state(cfg).get('tests', {})
    print(f"tests: {t['mode']}" + (f", full run every {t['every']} tasks: {t['full'] or 'NO tests.full in the config'} "
                                  f"in {t['checkout'] or 'NO tests.checkout in the config'}" if t['mode'] == 'batched' else ''))
    if ts.get('last'):
        last = ts['last']
        print(f"last full run: {'green' if last['ok'] else 'red'} at {last['sha']} ({last['at']}); last green: {ts.get('green') or '-'}")
    if ts.get('running'):
        print(f"running since {ts['running']['at']}")


def cmd_team(cfg, opts):
    """Who works the roles: claude (Codex off), codex (Claude off) or both (they compete for tasks). The owner moves work
    to whichever has tokens left. The dispatcher keeps running either way: it only sorts tasks, on Claude or Codex."""
    def change(raw):
        raw.setdefault('dispatcher', {})['agent'] = 'both'
        for r in raw.setdefault('roles', [{**x, 'session': ''} for x in DEFAULT_ROLES]):
            r['agent'] = opts.agent
    cfg = save_config(cfg, change)
    if opts.agent == 'claude':
        print('Claude works every role now; Codex workers stop at their next agentq call. '
              f"If the Claude dispatcher is not running, send it ({cfg['dispatcher']['session'] or 'no session id'}) "
              '"Start the watcher".')
    elif opts.agent == 'codex':
        print('Codex works every role now; Claude sessions get no new tasks (they finish what they hold). '
              'Codex workers: `agentq codex-workers` opens one per role. The dispatcher keeps sorting tasks '
              '(Claude, or a Codex task in its folder: "Read AGENTS.md and start the loop").')
    else:
        print('Claude and Codex now both work every role: free workers of both take tasks in turns (the watcher wakes an '
              'idle Codex worker with a message; `agentq codex-workers` opens one per role); claims keep them from '
              'sharing a task.')
    warn_untaken(cfg, cfg['roles'])


CODEX_WORKER = ('You are the Codex {role} of the agent team in this project (worker {name}). Read the skill AGENTS.md '
                'points to (section "Claude and Codex"). Run `{agentq} next {role} --as {name}`, do the task it gives you '
                'by the skill and finish it with one agentq command, then run it again. When it says there is no task, '
                'end your turn: agentq sends this task a message when there is work. Never wait or poll in a command – '
                'in Codex that costs a model call every minute. No progress reports to the owner.')


def cmd_workers(cfg, opts):
    """Codex workers: one Codex task per pulling role (or `count` per role), listed under the project like Claude's
    sessions. Prints a title and a first message for each missing one: a Codex task in the app creates them with its
    create_thread tool (no clicks); elsewhere the owner does it with New task. Workers already running on this computer
    are left out; an archived or deleted one counts as missing."""
    roles = [r for r in cfg['roles'] if pulls(r) and (not opts.role or r is role_by_name(cfg, opts.role))]
    if not roles:
        print('no role takes Codex workers – `agentq team both` (or `agentq role <name> --agent both`) first.')
        return
    host = socket.gethostname()
    have = {w for w, i in load_state(cfg).get('codex', {}).items() if i.get('host') == host and codex_activity(i['thread'])}
    names = [(r['role'], f"codex-{r['role'].replace(' ', '-')}" + (f'-{n}' if n > 1 else ''),
              f"Codex {r['role']}" + (f' {n}' if n > 1 else ''),
              {'max': 'xhigh'}.get(r['effort'], r['effort']) or 'xhigh',  # Codex has no "max"
              r.get('codex_model') or cfg['codex_model'])
             for r in roles for n in range(1, opts.count + 1)]
    missing = [x for x in names if x[1] not in have]
    if not missing:
        print('every role already has its Codex worker; none missing.')
        return
    project = cfg.get('checkout') or os.getcwd()
    print(f"Create one Codex task per block below in the project {project}, titled as the block says, with the "
          f"block's text as its first message, and the model and reasoning effort it names (thinking; xhigh = extra "
          f"high) – never the app's default model when the block names one. In the Codex app: the create_thread tool "
          f"(list_projects gives the project's id); otherwise the owner: New task in that project, pick the model and "
          f"effort, paste, Send.")
    for role, name, title, effort, model in missing:
        print(f"\n--- {title} (model: {model or 'the app default'}, reasoning effort: {effort}) ---\n" + CODEX_WORKER.format(role=shlex_quote(role), name=shlex_quote(name),
                                                           agentq=self_command()))


def cmd_stats(cfg, opts):
    """Who works better: tasks done, time from taking to closing, and problems the checkers found afterwards,
    per team (the claude / codex labels)."""
    since = iso(now() - dt.timedelta(days=opts.days))
    labels = cfg['labels']
    teams = {labels['by_claude']: 'claude', labels['by_codex']: 'codex'}
    rows = {'claude': [], 'codex': []}
    found = {'claude': 0, 'codex': 0}
    agent_of = {}
    for repo in cfg['repos']:
        for issue in gh_json('issue', 'list', '-R', repo, '--state', 'closed', '--limit', '500', '--search',
                             f'closed:>={since}', '--json', 'number,labels,closedAt,stateReason,comments'):
            names = labels_of(issue)
            team = next((teams[n] for n in names if n in teams), None)
            if not team or issue.get('stateReason') == 'NOT_PLANNED' or labels['health'] in names:
                continue
            agent_of[(repo, issue['number'])] = team
            claims = [c['createdAt'] for c in issue.get('comments', []) if CLAIM_MARK.search(c.get('body') or '')]
            hours = (parse_time(issue['closedAt']) - parse_time(claims[-1])).total_seconds() / 3600 if claims else None
            rows[team].append(hours)
        for issue in gh_json('issue', 'list', '-R', repo, '--state', 'all', '--limit', '500', '--search',
                             f'created:>={since} "From the check of" in:body', '--json', 'number,body'):
            for n in re.findall(r'From the check of #(\d+)', issue.get('body') or ''):
                team = agent_of.get((repo, int(n)))
                if team:
                    found[team] += 1
    print(f'last {opts.days:g} days: team | tasks done | median hours from taking to closing | problems found later')
    for team, hours in rows.items():
        known = sorted(h for h in hours if h is not None)
        median = f'{known[len(known) // 2]:.1f}' if known else '-'
        print(f'{team} | {len(hours)} | {median} | {found[team]}')


def cmd_live(cfg, opts):
    """The owner's running copy of the program: which role restarts it, when, and with what command ({sha} = the
    commit). After GO on the last green commit, or with --when checked after every check on the commit it checked,
    red tests or not (the owner tests on it too). None: nothing is restarted – e.g. it runs on another machine."""
    if opts.off or opts.role:
        def change(raw):
            if opts.off:
                raw.pop('live', None)
            elif not opts.command:
                raise Fail('give the restart command too, e.g. agentq live checker "~/bin/restart.sh {sha}"')
            else:
                raw['live'] = {'role': role_by_name(cfg, opts.role)['role'], 'command': opts.command}
                if opts.when == 'checked':
                    raw['live']['when'] = 'checked'
        cfg = save_config(cfg, change)
    live = cfg.get('live') or {}
    when = 'after every check, red tests or not,' if live.get('when') == 'checked' else 'after GO'
    print(f"the owner's running copy: {live['role']} restarts it {when} with `{live['command']}`" if live.get('command')
          else "the owner's running copy: none – nothing is restarted")


def cmd_role(cfg, opts):
    """Add or change a role (or the dispatcher's session) in the config, then create its labels."""
    name = opts.name.strip()

    def change(raw):
        if name.lower() == 'dispatcher':
            disp = raw.setdefault('dispatcher', {})
            for key in ('session', 'model', 'effort'):
                if getattr(opts, key) is not None:
                    disp[key] = getattr(opts, key)
            return
        roles = raw.setdefault('roles', [{**r, 'session': ''} for r in DEFAULT_ROLES])
        entry = next((r for r in roles if r['role'].lower() == name.lower()), None)
        if opts.remove:
            if entry:
                roles.remove(entry)
            return
        if entry is None:
            entry = {'role': name, **copy.deepcopy(PRESETS.get(name.lower(), {}))}
            roles.append(entry)
        for key in ('label', 'mode', 'n', 'hours', 'model', 'codex_model', 'release_model', 'effort', 'hard_effort',
                    'session', 'description', 'agent'):
            if getattr(opts, key) is not None:
                entry[key] = getattr(opts, key)
        if opts.add_session:
            listed = entry.get('sessions') or ([entry['session']] if entry.get('session') else [])
            entry['sessions'] = listed + [x for x in opts.add_session if x not in listed]
            entry['session'] = entry['sessions'][0]
        if opts.sessions is not None:
            entry['sessions'] = [x.strip() for x in opts.sessions.split(',') if x.strip()]
            entry['session'] = entry['sessions'][0] if entry['sessions'] else ''
        elif opts.session is not None:
            entry.pop('sessions', None)
        if opts.paths is not None:
            entry['paths'] = [p.strip() for p in opts.paths.split(',') if p.strip()]
        if opts.example:
            entry['examples'] = opts.example
        for path in opts.shot or []:
            shots = entry.setdefault('shots', [])
            file = f"{entry['role'].replace(' ', '-')}-{len(shots) + 1}{os.path.splitext(path)[1].lower()}"
            os.makedirs(os.path.join(cfg['team_dir'], 'examples'), exist_ok=True)
            with open(os.path.expanduser(path), 'rb') as src, open(os.path.join(cfg['team_dir'], 'examples', file), 'wb') as dst:
                dst.write(src.read())
            shots.append(file)
        if opts.merge is not None:
            entry['merge'] = opts.merge == 'yes'
        if entry.get('mode') == 'checker' and not entry.get('since'):
            entry['since'] = iso(now())
        role_entry(entry)

    cfg = save_config(cfg, change)
    if len(cfg['roles']) == 0 or default_role(cfg) is None:
        raise Fail('the default role is gone')
    if opts.remove:  # its rules and lessons would send tasks to a role that no longer exists
        lessons = load_lessons(cfg)
        kept = [r for r in lessons['rules'] if (r.get('role') or '').lower() != name.lower()]
        if len(kept) != len(lessons['rules']) or name in lessons['examples']:
            lessons['rules'] = kept
            lessons['examples'].pop(name, None)
            save_lessons(cfg, lessons)
            print(f'rules and lessons for {name} removed')
    if not opts.remove:
        ensure_labels(cfg)
    if cfg['dispatcher']['folder'] and os.path.isdir(cfg['team_dir']):
        install_dispatcher(cfg, cfg['dispatcher']['folder'])
    sync_dispatcher_session(cfg)
    write_roles(cfg)
    print_roles_table(cfg)
