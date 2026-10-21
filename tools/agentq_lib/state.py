"""This computer's state beside the config: one writer at a time, merged saves, delivered words, waiting workers and
the watcher lock.
"""

import copy
import datetime as dt
import glob
import json
import os
import time

from .system import lock_file, replace_file, temp_path, unlock_file
from .base import now, parse_time
from .github import login_of


BASE = '_loaded'  # the state as a command loaded it, so its save keeps what others changed meanwhile


class state_lock:
    """Several processes write the state (the watcher, workers, the dispatcher's commands): one at a time."""
    def __init__(self, cfg):
        self.path = cfg['state_file'] + '.lock'

    def __enter__(self):
        self.handle = open(self.path, 'a')
        lock_file(self.handle)

    def __exit__(self, *exc):
        unlock_file(self.handle)


def read_state_file(cfg):
    try:
        with open(cfg['state_file'], encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def write_state_file(cfg, data):
    tmp = temp_path(cfg['state_file'])
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    replace_file(tmp, cfg['state_file'])


def load_state(cfg):
    state = read_state_file(cfg)
    state[BASE] = copy.deepcopy(state)
    return state


def merged(base, ours, disk):
    """Three-way, key by key: what this command changed since it loaded the state wins; what others changed
    meanwhile (a worker took a task, the owner paused the team) stays."""
    out = dict(disk)
    for key in set(base) | set(ours):
        if key not in ours:
            out.pop(key, None)
        elif key not in base or ours[key] != base[key]:
            if all(isinstance(x, dict) for x in (base.get(key), ours[key], disk.get(key))):
                out[key] = merged(base[key], ours[key], disk[key])
            else:
                out[key] = ours[key]
    return out


def save_state(cfg, state):
    ours = {k: v for k, v in state.items() if k != BASE}
    with state_lock(cfg):
        new = merged(state[BASE], ours, read_state_file(cfg)) if BASE in state else ours
        write_state_file(cfg, new)
    state.clear()
    state.update(new)
    state[BASE] = copy.deepcopy(new)


def update_state(cfg, change):
    """Read, change and write the state in one locked step; returns what change returns."""
    with state_lock(cfg):
        data = read_state_file(cfg)
        result = change(data)
        write_state_file(cfg, data)
    return result


def comment_key(c):
    """The same key for a comment from `gh issue list` (GraphQL) and from `gh api` (REST)."""
    return f"{login_of(c)}@{c.get('createdAt') or c.get('created_at')}"


def delivered_path(cfg):
    return cfg['state_file'] + '.delivered.json'


def load_delivered(cfg):
    try:
        with open(delivered_path(cfg), encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def mark_delivered(cfg, repo, comments, keep_hours):
    """The owner's comments that reached a role (brief printed them). Only brief and the first watch write this."""
    with state_lock(cfg):
        data = load_delivered(cfg) or {}
        marks = data.setdefault(repo, {})
        for c in comments:
            marks[comment_key(c)] = c.get('createdAt') or c.get('created_at')
        oldest = now() - dt.timedelta(hours=2 * keep_hours)
        data[repo] = {k: at for k, at in marks.items() if parse_time(at) >= oldest}
        tmp = temp_path(delivered_path(cfg))
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=1)
        replace_file(tmp, delivered_path(cfg))


def watch_lock(cfg, who=None):
    """One watcher per project and agent; with dispatcher agent "both" a Claude and a Codex watcher may run side by side."""
    handle = open(cfg['state_file'] + (f'.watch.{who}.lock' if who else '.watch.lock'), 'a')
    if not lock_file(handle, wait=False):
        handle.close()
        return None
    return handle


def watcher_running(cfg):
    for who in (None, 'claude', 'codex'):
        lock = watch_lock(cfg, who)
        if lock is None:
            return True
        lock.close()
    return False


def waiting_dir(cfg):
    return cfg['state_file'] + '.waiting'


def mark_waiting(cfg, worker, role_names):
    os.makedirs(waiting_dir(cfg), exist_ok=True)
    with open(os.path.join(waiting_dir(cfg), worker.replace('/', '_')), 'w', encoding='utf-8') as f:
        json.dump({'worker': worker, 'roles': role_names}, f)


def unmark_waiting(cfg, worker):
    try:
        os.remove(os.path.join(waiting_dir(cfg), worker.replace('/', '_')))
    except OSError:
        pass


def waiting_workers(cfg, role):
    """Workers of this role waiting in `agentq next --wait` right now (a heartbeat in the last 150 seconds)."""
    found = set()
    for path in glob.glob(os.path.join(glob.escape(waiting_dir(cfg)), '*')):
        try:
            if time.time() - os.path.getmtime(path) > 150:
                continue
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        if role['role'] in data.get('roles', []):
            found.add(data['worker'])
    return found
