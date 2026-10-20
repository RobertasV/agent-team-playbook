"""The hourly health check: watcher alive, disk, stuck tasks, old worktrees; one issue for the owner."""

import datetime as dt
import os
import shutil
import socket
import subprocess
import time

from .system import WINDOWS
from .base import now, parse_time
from .github import board, comment, create_issue, gh, gh_json, labels_of, relabel, view
from .state import load_state, save_state, watcher_running


def sweep_worktrees(cfg):
    """Worktrees of the project whose work is in main: removed. Only one that is clean (`git status` empty), untouched
    for worktree_idle_hours, with no process working in it and whose HEAD main already has; its branch stays, so a task
    that comes back gets a new worktree from it. A Claude session's own worktree (.claude/worktrees) is the app's: left."""
    checkout = os.path.expanduser(cfg.get('checkout') or '')
    if not cfg['worktree_idle_hours'] or not os.path.isdir(checkout):
        return []

    def run(*args, cwd=checkout):
        return subprocess.run(['git', '-C', cwd, *args], capture_output=True, text=True, encoding='utf-8',
                              errors='replace')
    run('worktree', 'prune')
    branch = cfg['tests']['branch']
    mains = [ref for ref in (f'origin/{branch}', branch) if run('rev-parse', '-q', '--verify', ref).returncode == 0]
    cwds = set()
    if not WINDOWS:  # Windows itself refuses to remove a folder a process works in
        try:
            out = subprocess.run(['lsof', '-a', '-d', 'cwd', '-Fn'], capture_output=True, text=True, timeout=60).stdout
        except (OSError, subprocess.TimeoutExpired):
            return []  # cannot tell who works where: remove nothing
        cwds = {os.path.realpath(line[1:]) for line in out.splitlines() if line.startswith('n')}
    trees, cur = [], {}
    for line in run('worktree', 'list', '--porcelain').stdout.splitlines() + ['']:
        if line:
            key, _, value = line.partition(' ')
            cur[key] = value or True
        elif cur:
            trees.append(cur)
            cur = {}
    removed, limit = [], time.time() - cfg['worktree_idle_hours'] * 3600
    for tree in trees[1:]:  # the first is the project's own checkout
        path = tree['worktree']
        real = os.path.realpath(path)
        if tree.get('locked') or tree.get('prunable') or '/.claude/worktrees/' in real.replace(os.sep, '/') + '/' \
                or not os.path.isdir(path):
            continue
        if any(c == real or c.startswith(real + '/') for c in cwds):
            continue
        gitdir = run('rev-parse', '--absolute-git-dir', cwd=path).stdout.strip()
        stamps = [os.path.getmtime(p) for p in (os.path.join(gitdir, n) for n in ('HEAD', 'index', 'logs/HEAD'))
                  if os.path.exists(p)]
        if not stamps or max(stamps) > limit:
            continue
        if not any(run('merge-base', '--is-ancestor', tree['HEAD'], ref).returncode == 0 for ref in mains):
            continue
        status = run('status', '--porcelain', cwd=path)
        if status.returncode or status.stdout.strip():
            continue
        if run('worktree', 'remove', path).returncode == 0:
            removed.append(os.path.normpath(path))  # git writes C:/… on Windows
    return removed


def cmd_health(cfg, opts):
    state = load_state(cfg)
    moment = now()
    texts = cfg['texts']
    grace = dt.timedelta(minutes=cfg['watch_grace_minutes'])
    beat = state.get('watch', {})
    problems = []
    paused = state.get('paused')
    running = watcher_running(cfg)
    if paused:  # a pause is the owner's word; only a forgotten one is a problem
        if moment - parse_time(paused['at']) > dt.timedelta(hours=cfg['stale_hours']):
            problems.append(texts['health_paused'].format(since=paused['at'], why=paused['why']))
    elif not running:
        exited = beat.get('exited')
        if not (exited and exited == beat.get('beat') and moment - parse_time(exited) < grace):
            problems.append(texts['health_watch'].format(since=beat.get('beat') or 'never'))
    elif beat.get('beat') and moment - parse_time(beat['beat']) > grace:
        problems.append(texts['health_stuck'].format(since=beat['beat']))
    if beat.get('error'):
        problems.append(texts['health_error'].format(error=beat['error']))
    stale = dt.timedelta(hours=cfg['stale_hours'])
    free = shutil.disk_usage(os.path.dirname(cfg['state_file']) or '.').free / 1e9
    if cfg['disk_min_gb'] and free < cfg['disk_min_gb']:
        problems.append(texts['health_disk'].format(free=f'{free:.0f}', limit=cfg['disk_min_gb']))
    for repo in cfg['repos'] if cfg['primary'] else []:  # the whole board: the main computer's report
        for issue in board(repo):
            if cfg['labels']['working'] in labels_of(issue) and moment - parse_time(issue['updatedAt']) > stale:
                problems.append(texts['health_stale'].format(ref=f"{repo}#{issue['number']}",
                                                             label=cfg['labels']['working'], hours=cfg['stale_hours']))
    report_health(cfg, state, problems)
    save_state(cfg, state)
    for path in sweep_worktrees(cfg):
        print(f'removed the worktree {path}: its work is in {cfg["tests"]["branch"]}')


def report_health(cfg, state, problems, needs_owner=False, close=True, done=()):
    """One health issue for the owner: created, commented when the problems change, closed when all is well.
    `done`: stuck tasks the owner was told about that moved on – said on the issue, with no need to act."""
    texts = cfg['texts']
    repo = cfg['repos'][0]
    label = cfg['labels']['health']
    title = texts['health_title'] if cfg['primary'] else f"{texts['health_title']} ({socket.gethostname().split('.')[0]})"
    found = [i for i in gh_json('issue', 'list', '-R', repo, '--state', 'open', '--label', label, '--limit', '20',
                                '--json', 'number,title') if i.get('title', title) == title]  # each computer its own
    if not found and state.get('health_issue'):  # created a moment ago: GitHub's list may not show it yet
        known = view(repo, state['health_issue'])
        found = [{'number': state['health_issue']}] if known.get('state') == 'OPEN' else []
    if done and found:
        comment(cfg, repo, found[0]['number'], texts['health_moved'].format(refs=', '.join(done)), 'health')
        if close:
            relabel(repo, found[0]['number'], remove=[cfg['labels']['question']])
    report = '\n'.join(f'- {p}' for p in problems)
    extra = [cfg['labels']['question']] if needs_owner else []
    if problems and found:
        number = found[0]['number']
        if report == state.get('health_report') and not needs_owner:
            print(f'problems unchanged since the last report on {repo}#{number}:\n{report}')
            return number
        comment(cfg, repo, number, '\n' + report, 'health')
        relabel(repo, number, add=extra)
        print(f"problems reported on {repo}#{number}:\n{report}")
    elif problems:
        number = create_issue(repo, title, f'🤖 health:\n{report}', [label] + extra)
        state['health_issue'] = number
        print(f'problems reported in {repo}#{number}:\n{report}')
    elif found and close:
        number = found[0]['number']
        comment(cfg, repo, number, texts['health_ok'], 'health')
        gh('issue', 'close', str(number), '-R', repo)
        print(f"healthy; {repo}#{number} closed")
    else:
        number = None
        print('healthy')
    state['health_report'] = report if problems else ''
    return number
