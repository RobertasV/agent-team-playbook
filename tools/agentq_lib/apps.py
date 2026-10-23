"""What agentq reads from the Claude and Codex desktop apps (sessions, Codex tasks) and how it messages a Codex task.
See docs/DESIGN.md, "What agentq reads from the apps".
"""

import datetime as dt
import glob
import json
import os
import socket
import subprocess
import time
from shutil import which as shutil_which

from .system import APP_SESSIONS_DEFAULT, command_lines, lock_file, tool, unlock_file, WINDOWS
from .base import one_line, parse_time
from .state import load_state


APP_SESSIONS = os.path.expanduser(os.environ.get('AGENTQ_APP_SESSIONS') or APP_SESSIONS_DEFAULT)

# Every read below is of files the apps write for themselves, in a format they may change: a missing file, a file
# that vanishes between listing and reading, or an unexpected shape means "cannot be seen" – never a crash.


def mtimes(paths):
    """Modification times of the files that still exist (an app may delete one between the listing and the look)."""
    out = []
    for path in paths:
        try:
            out.append(os.path.getmtime(path))
        except OSError:
            pass
    return out


def read_meta(cfg, session):
    """The Claude desktop app's record of a session (its newest file), or {} when it cannot be read."""
    metas = glob.glob(os.path.join(glob.escape(cfg['app_sessions']), '*', '*', f'{glob.escape(session)}.json'))
    for path in sorted(metas, key=lambda p: (mtimes([p]) or [0])[0], reverse=True):
        try:
            with open(path, encoding='utf-8') as f:
                meta = json.load(f)
        except (OSError, ValueError):
            continue
        return meta if isinstance(meta, dict) else {}
    return {}


def session_of(role, sid=None):
    """The session a plan sends to, by id only: a name invites the dispatcher to doubt it against names it remembers.
    When the desktop app's records show the session exists, the plan says so."""
    sid = sid or role['session']
    if not sid:
        return f"session (none in the config for {role['role']} – run setup)"
    seen = glob.glob(os.path.join(glob.escape(APP_SESSIONS), '*', '*', f'{glob.escape(sid)}.json'))
    return f"session {sid}" + (' (agentq checked: it exists)' if seen else '')


def worker_title(cfg, worker):
    """The name the owner sees for a worker: its Codex task's or Claude session's title, else the worker's name."""
    if not worker:
        return None
    info = load_state(cfg).get('codex', {}).get(worker)
    if info:
        names = []
        try:
            with open(os.path.join(CODEX_HOME, 'session_index.jsonl'), encoding='utf-8') as f:
                for line in f:
                    if info['thread'] not in line:
                        continue
                    try:
                        entry = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(entry, dict) and isinstance(entry.get('thread_name'), str) and entry['thread_name']:
                        names.append(entry['thread_name'])
        except OSError:
            pass
        return (names or [worker])[-1]
    title = read_meta(cfg, worker).get('title')
    return title if isinstance(title, str) and title else worker


def session_activity(cfg, session):
    """When a desktop-app session last did anything: its transcript file's time. None when this cannot be seen."""
    if not session:
        return None
    meta = read_meta(cfg, session)
    cli = meta.get('cliSessionId')
    if not isinstance(cli, str) or not cli:
        return None
    seen = mtimes(glob.glob(os.path.join(glob.escape(cfg['transcripts']), '*', f'{glob.escape(cli)}.jsonl')))
    if not seen:
        return None
    last = meta.get('lastActivityAt')  # the app's own time too: a long test run writes nothing to the transcript
    if isinstance(last, (int, float)):
        seen.append(last / 1000)
    return dt.datetime.fromtimestamp(max(seen), dt.timezone.utc).replace(microsecond=0)


CODEX_HOME = os.path.expanduser(os.environ.get('CODEX_HOME') or '~/.codex')


def codex_cli():
    """AGENTQ_CODEX, else `codex` on PATH, else the Codex app's own CLI (a command: a list)."""
    if 'AGENTQ_CODEX' in os.environ:
        return tool('codex')
    bundled = sorted(glob.glob('/Applications/*.app/Contents/Resources/codex-cli/*.app/Contents/MacOS/codex'))
    if WINDOWS:
        local = os.environ.get('LOCALAPPDATA') or ''
        bundled = sorted(glob.glob(os.path.join(glob.escape(local), 'Programs', '*', 'resources', 'codex-cli', 'codex.exe')))
    return tool('codex') or ([bundled[-1]] if bundled else None)


def codex_loaded(thread):
    """A process – normally the Codex app – has the task loaded, so it runs a queued message once the task is idle."""
    lock = os.path.join(CODEX_HOME, 'thread-writer-locks', f'{thread}.lock')
    if not os.path.exists(lock):
        return False
    if WINDOWS:  # no lsof: a file another process holds open or locked cannot be locked here
        try:
            with open(lock, 'a') as handle:
                if not lock_file(handle, wait=False):
                    return True
                unlock_file(handle)
                return False
        except OSError:
            return True
    lsof = shutil_which('lsof') or '/usr/sbin/lsof'
    if not os.path.exists(lsof):
        return True
    try:
        return bool(subprocess.run([lsof, '-t', lock], capture_output=True, text=True, timeout=30).stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        return False


_app_seen = {}


def codex_app_running():
    if 'AGENTQ_CODEX_APP' in os.environ:
        return os.environ['AGENTQ_CODEX_APP'] == '1'
    if _app_seen and time.time() - _app_seen['at'] < 30:  # asking Windows for command lines takes a second or two
        return _app_seen['up']
    pattern = r'codex(\.exe)?"?\s.*app-server' if WINDOWS else r'\.app/Contents/Resources/codex-cli/.*app-server'
    try:
        up = command_lines(pattern)
    except (OSError, subprocess.TimeoutExpired):
        up = False
    _app_seen.update(at=time.time(), up=up)
    return up


def codex_reachable(thread):
    """A message would run soon: the task is loaded, or the Codex app runs and loads it. Codex closed: nothing runs."""
    return codex_loaded(thread) or codex_app_running()


def codex_activity(thread):
    """When a Codex task last did anything: its rollout file's time. None when this cannot be seen."""
    files = glob.glob(os.path.join(glob.escape(CODEX_HOME), 'sessions', '*', '*', '*',
                                   f'rollout-*-{glob.escape(thread)}.jsonl'))
    seen = mtimes(files)
    if not seen:
        return None
    return dt.datetime.fromtimestamp(max(seen), dt.timezone.utc).replace(microsecond=0)


def message_codex(thread, text):
    """Queue a message for a Codex task; it runs as soon as the task is idle. A task the Codex app has not loaded
    (e.g. after the app restarted) is opened in the background, without taking focus, so the app loads it and runs
    the message. Returns (accepted, what went wrong): a message Codex may have accepted is never sent twice."""
    cli = codex_cli()
    if not cli:
        return False, 'no Codex CLI found (set AGENTQ_CODEX to its path)'
    try:
        run = subprocess.run([*cli, 'queue', '--thread', thread, '--message', text], capture_output=True, text=True,
                             encoding='utf-8', errors='replace', timeout=60)
    except OSError as e:
        return False, f'codex queue: {e}'
    except subprocess.TimeoutExpired:
        return True, 'codex queue did not answer in 60 s – the message may be queued'
    if run.returncode != 0:
        return False, one_line(run.stderr or run.stdout or f'codex queue exited with {run.returncode}', 300)
    if not codex_loaded(thread) and codex_app_running():
        try:
            url = f'codex://threads/{thread}'
            if 'AGENTQ_OPEN' in os.environ:
                argv = [*tool('open'), '-g', url]
            elif WINDOWS:  # Windows cannot open it in the background; the Codex window may come forward
                argv = ['cmd', '/c', 'start', '', url]
            else:
                argv = ['open', '-g', url]
            opened = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
        except (OSError, subprocess.TimeoutExpired) as e:
            return True, f'queued, but opening the task failed: {e}'
        if opened.returncode != 0:
            return True, f'queued, but opening the task failed: {one_line(opened.stderr or str(opened.returncode), 200)}'
    return True, None


def codex_here(state):
    """This Codex task's worker record, found by the task's id."""
    thread = os.environ.get('CODEX_THREAD_ID')
    for worker, info in state.get('codex', {}).items():
        if thread and info.get('thread') == thread:
            return worker, info
    return None, None


def codex_waits(cfg, state, role):
    """An idle Codex worker of this computer could take this role's next task: the watcher wakes it within a minute."""
    host = socket.gethostname()
    held = set(state.get('holders', {}).values())
    idle = [i for w, i in state.get('codex', {}).items() if i.get('host') == host and role['role'] in i.get('roles', [])
            and w not in held and i.get('idle') and codex_activity(i['thread'])]
    return bool(idle) and codex_app_running()


def reserve_codex(data, worker, seen, value):
    """Only one watcher wakes a worker: its record must still be as this watcher saw it."""
    info = data.get('codex', {}).get(worker)
    if not info or (info.get('idle'), info.get('finished')) != seen:
        return False
    info['idle'], info['finished'] = value
    return True


def app_started():
    """When the Claude desktop app last started (macOS; None elsewhere or when it cannot be seen): a restart stops every
    session's turn, so a session that holds a task and has been quiet since is reminded at once."""
    if os.environ.get('AGENTQ_APP_STARTED'):
        return parse_time(os.environ['AGENTQ_APP_STARTED'])
    if WINDOWS:
        return None
    try:
        out = subprocess.run(['ps', '-axo', 'lstart=,command='], capture_output=True, text=True, timeout=20).stdout
        started = [line[:24] for line in out.splitlines() if line.rstrip().endswith('/Claude.app/Contents/MacOS/Claude')]
        if not started:
            return None
        return dt.datetime.fromtimestamp(time.mktime(time.strptime(started[0].strip(), '%a %b %d %H:%M:%S %Y')),
                                         dt.timezone.utc)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def context_tokens(cfg, session):
    """How long a Claude session's conversation is now: the tokens its last model call read (new, cached and
    cache-written), from the end of its transcript. None when this cannot be seen."""
    meta = read_meta(cfg, session)
    cli = meta.get('cliSessionId')
    if not isinstance(cli, str) or not cli:
        return None
    paths = glob.glob(os.path.join(glob.escape(cfg['transcripts']), '*', f'{glob.escape(cli)}.jsonl'))
    if not paths:
        return None
    try:
        with open(paths[0], 'rb') as f:
            f.seek(max(0, os.path.getsize(paths[0]) - 2_000_000))
            lines = f.read().decode('utf-8', 'replace').splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if '"usage"' not in line:
            continue
        try:
            usage = json.loads(line).get('message', {}).get('usage') or {}
        except ValueError:
            continue
        if isinstance(usage, dict) and usage:
            return sum(int(usage.get(k) or 0) for k in ('input_tokens', 'cache_read_input_tokens',
                                                        'cache_creation_input_tokens'))
    return None
