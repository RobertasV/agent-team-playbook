"""The project's config: where it is, loading and saving it, and questions about its roles."""

import copy
import glob
import json
import os

from .system import APP_SESSIONS_DEFAULT, replace_file, temp_path
from .base import DEFAULT_CONFIG, Fail, PROJECT_CONFIG
from .defaults import DEFAULT_LABELS, DEFAULT_ROLES, DEFAULT_TEXTS, MODES
from .github import labels_of, login_of


def find_config(explicit):
    """--config, then AGENTQ_CONFIG, then the nearest .agentq.json from here up (the project opted in), then the user default."""
    if explicit:
        return explicit
    if os.environ.get('AGENTQ_CONFIG'):
        return os.environ['AGENTQ_CONFIG']
    starts = [os.getcwd()]
    session = os.environ.get('CLAUDE_CODE_HOST_SESSION_ID')  # run from a scratch folder: the session's own project
    if session:
        apps = os.path.expanduser(os.environ.get('AGENTQ_APP_SESSIONS') or APP_SESSIONS_DEFAULT)
        for meta in glob.glob(os.path.join(glob.escape(apps), '*', '*', f'{glob.escape(session)}.json')):
            try:
                with open(meta, encoding='utf-8') as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            if isinstance(data, dict):  # the app's record: an unexpected shape is skipped, never a crash
                starts += [d for d in (data.get('cwd'), data.get('originCwd')) if isinstance(d, str) and d]
    for here in starts:
        while True:
            candidate = os.path.join(here, PROJECT_CONFIG)
            if os.path.exists(candidate):
                return candidate
            parent = os.path.dirname(here)
            if parent == here:
                break
            here = parent
    return DEFAULT_CONFIG


def role_entry(raw):
    role = {'label': raw['role'], 'mode': 'programmer', 'n': 5, 'hours': 24, 'paths': [], 'model': '',
            'release_model': '', 'effort': '', 'hard_effort': '', 'session': '', 'description': '', 'examples': [],
            'shots': [], **raw}
    role.setdefault('merge', role['mode'] == 'programmer')
    role.setdefault('agent', 'claude')  # another agent (codex, …) pulls its tasks with `agentq next`
    role['sessions'] = [x for x in (raw.get('sessions') or [raw.get('session')]) if x]  # several sessions: a pool
    active = raw.get('active')
    role['pool'] = role['sessions'][:active] if active is not None else role['sessions']  # the rest rest, kept
    role['session'] = (role['pool'] or role['sessions'] or [''])[0]
    if role['mode'] not in MODES:
        raise Fail(f'role {role["role"]}: mode must be one of {", ".join(MODES)}')
    return role


def load_config(path):
    try:
        with open(path, encoding='utf-8') as f:
            raw = json.load(f)
    except FileNotFoundError:
        raise Fail(f'no config at {path} (copy config.example.json there, or pass --config)')
    if isinstance(raw, dict) and set(raw) == {POINTER}:
        return load_config(raw[POINTER])
    cfg = copy.deepcopy(raw)
    for key in ('owner_accounts', 'agent_account', 'repos', 'labels'):
        if not cfg.get(key):
            raise Fail(f'config {path}: "{key}" is missing')
    for key in ('working', 'question', 'deferred', 'waiting'):
        if not cfg['labels'].get(key):
            raise Fail(f'config {path}: "labels.{key}" is missing')
    cfg['_raw'], cfg['_path'] = raw, os.path.realpath(path)
    cfg['labels'] = {**DEFAULT_LABELS, **cfg['labels']}
    cfg['texts'] = {**DEFAULT_TEXTS, **cfg.get('texts', {})}
    cfg['roles'] = [role_entry(r) for r in (cfg.get('roles') or DEFAULT_ROLES)]
    names = [r['role'] for r in cfg['roles']]
    cfg['default_role'] = cfg.get('default_role') or ('programmer' if 'programmer' in names else names[0])
    cfg['role'] = cfg.get('role') or cfg['default_role']
    cfg['dispatcher'] = {'name': 'dispatcher', 'folder': '', 'session': '', 'agent': 'claude', **cfg.get('dispatcher', {})}
    skip = set(cfg.get('skip_labels', []))
    skip.update(cfg['labels'][k] for k in ('question', 'deferred', 'waiting', 'owner_word', 'health', 'testing'))
    cfg['skip'] = skip
    cfg['state_file'] = os.path.expanduser(cfg.get('state_file') or cfg['_path'] + '.state.json')
    cfg['stale_hours'] = cfg.get('stale_hours', 24)
    cfg['poll_seconds'] = cfg.get('poll_seconds', 60)
    cfg['watch_grace_minutes'] = cfg.get('watch_grace_minutes', 30)
    cfg['lesson_examples'] = cfg.get('lesson_examples', 5)
    cfg['repeat_minutes'] = cfg.get('repeat_minutes', 30)
    cfg['forward_hours'] = cfg.get('forward_hours', 24)
    cfg['check_minutes'] = cfg.get('check_minutes', 60)
    cfg['stale_pr_days'] = cfg.get('stale_pr_days', 3)
    cfg['disk_min_gb'] = cfg.get('disk_min_gb', 30)
    # one computer sorts new issues, runs the full tests and releases waits; another computer on the same project
    # ("primary": false) only serves its own sessions and Codex workers
    cfg['primary'] = cfg.get('primary', True)
    cfg['worktree_idle_hours'] = cfg.get('worktree_idle_hours', 12)  # merged, clean, untouched this long → removed; 0: off
    cfg['codex_model'] = cfg.get('codex_model', '')  # the model Codex workers start on; a role's codex_model wins
    cfg['clear_every'] = cfg.get('clear_every', 0)
    cfg['priority_words'] = cfg.get('priority_words') or [cfg['labels']['priority']]  # off: after a clear a watcher started before it wakes nobody
    tests = {'mode': 'per-task', 'full': '', 'every': 5, 'checkout': '', 'branch': 'main', 'timeout_minutes': 60,
             'role': '', **cfg.get('tests', {})}
    tests['checkout'] = os.path.expanduser(tests['checkout'])
    cfg['tests'] = tests
    cfg['idle_minutes'] = cfg.get('idle_minutes', 20)
    cfg['ask_wait_minutes'] = cfg.get('ask_wait_minutes', 10)
    cfg['testers'] = [t for t in cfg.get('testers') or [] if isinstance(t, str) and t.strip()]  # human test
    cfg['clear_tokens'] = int(cfg.get('clear_tokens') or 0)  # off: the project's autoCompactWindow keeps it short
    cfg['ask_poll_seconds'] = cfg.get('ask_poll_seconds', 20)
    cfg['escalate_minutes'] = cfg.get('escalate_minutes', 30)
    cfg['app_sessions'] = os.path.expanduser(os.environ.get('AGENTQ_APP_SESSIONS') or cfg.get('app_sessions') or
                                             APP_SESSIONS_DEFAULT)
    cfg['transcripts'] = os.path.expanduser(os.environ.get('AGENTQ_TRANSCRIPTS') or cfg.get('transcripts') or
                                            '~/.claude/projects')
    cfg['links'] = [{'repo': l['repo'], 'about': l.get('about', '')} for l in cfg.get('links', [])]
    folder = cfg['dispatcher']['folder']
    cfg['team_dir'] = os.path.expanduser(folder) if folder else os.path.dirname(cfg['state_file'])
    cfg['shots_dir'] = os.path.normpath(os.path.expanduser(cfg.get('shots_dir') or '~/.cache/agentq/shots'))  # never beside a config in a repo
    return cfg


def save_config(cfg, change):
    """Change the raw config (as written by the owner), write it back, return the reloaded config."""
    raw = copy.deepcopy(cfg['_raw'])
    change(raw)
    tmp = temp_path(cfg['_path'])
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(raw, f, indent=2, ensure_ascii=False)
        f.write('\n')
    replace_file(tmp, cfg['_path'])
    return load_config(cfg['_path'])


def role_by_name(cfg, name):
    """A role by its name, or by its label (agents name a role by the label they see on the board)."""
    for key in ('role', 'label'):
        for role in cfg['roles']:
            if role[key].lower() == name.strip().lower():
                return role
    raise Fail(f'no role "{name}" (roles: {", ".join(r["role"] for r in cfg["roles"])})')


def role_of_labels(cfg, names):
    for role in cfg['roles']:
        if role['label'] in names:
            return role
    return None


def default_role(cfg):
    return role_by_name(cfg, cfg['default_role'])


def checked_label(cfg, role):
    return cfg['labels']['checked'].format(role=role['role'])


def pulls(role):
    """Its workers take tasks themselves (`agentq next`): codex, or both (Claude sessions and Codex workers compete)."""
    return role.get('agent', 'claude') != 'claude'


def pushes(role):
    """The dispatcher sends tasks to its Claude sessions: claude, or both – unless `scale <role> 0` rested them all."""
    return role.get('agent', 'claude') in ('claude', 'both') and role.get('active') != 0


def capacity(role):
    return max(1, len(role['pool']))


def holder(cfg, issue):
    """Who writes on this issue: the role whose label it carries, else the session's own role."""
    role = role_of_labels(cfg, labels_of(issue))
    return role['role'] if role else cfg['role']


def trusted(cfg, issue):
    if cfg.get('accept_issues_from_others'):
        return True
    return login_of(issue) in set(cfg['owner_accounts']) | {cfg['agent_account']}


def tests_role(cfg):
    named = cfg['tests']['role']
    if named:
        return role_by_name(cfg, named)
    return next((r for r in cfg['roles'] if r['mode'] == 'checker'), default_role(cfg))


def agent_labels(cfg, agent):
    """The label saying which team works a task (for `agentq stats`), and the other one to remove."""
    mine, other = ('by_codex', 'by_claude') if agent == 'codex' else ('by_claude', 'by_codex')
    return [cfg['labels'][mine]], [cfg['labels'][other]]


POINTER = 'agentq_config'  # a .agentq.json that only names the real config: Windows without symlink rights
