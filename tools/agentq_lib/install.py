"""Installing the team into a project: config, links into the project, labels, the dispatcher folder."""

import json
import os
import re
import subprocess

from .system import PACKAGE, self_command, WINDOWS
from .base import Fail, iso, now, PROJECT_CONFIG, TEMPLATE
from .defaults import DEFAULT_ROLES
from .github import gh, gh_json, git
from .config import checked_label, POINTER, save_config
from .lessons import write_roles


def all_labels(cfg):
    names = {cfg['labels'][k]: k for k in ('working', 'question', 'deferred', 'waiting', 'priority', 'blocking',
                                            'hard', 'owner_word', 'batch', 'health', 'by_claude', 'by_codex',
                                            'only_claude', 'only_codex', 'human_test', 'testing')}
    for role in cfg['roles']:
        names.setdefault(role['label'], f'role: {role["role"]}')
        if role['mode'] == 'checker':
            names.setdefault(checked_label(cfg, role), f'checked by {role["role"]}')
    return names


def ensure_labels(cfg):
    wanted = all_labels(cfg)
    for repo in cfg['repos']:
        have = {l['name'] for l in gh_json('label', 'list', '-R', repo, '--limit', '300', '--json', 'name')}
        for name, what in wanted.items():
            if name not in have:
                gh('label', 'create', name, '-R', repo, '--color', 'BFBFBF', '--description', f'agentq: {what}')
                print(f'{repo}: label "{name}" created')


def install_dispatcher(cfg, folder):
    """Copy the dispatcher's template, link the config. CLAUDE.md is agentq's own and follows the template;
    other files (examples/) are copied only when missing."""
    folder = os.path.abspath(os.path.expanduser(folder))
    agentq = self_command()
    for base, _, files in os.walk(TEMPLATE):
        for name in files:
            source = os.path.join(base, name)
            target = os.path.join(folder, os.path.relpath(source, TEMPLATE))
            managed = name in ('CLAUDE.md', 'AGENTS.md') and base == TEMPLATE
            if os.path.exists(target) and not managed:
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(source, encoding='utf-8') as f:
                text = f.read().replace('{{agentq}}', agentq).replace('{{default_role}}', cfg['default_role'])
            if os.path.exists(target):
                with open(target, encoding='utf-8') as f:
                    old = SESSION_BLOCK.sub('<!-- agentq:session -->\n<!-- /agentq:session -->\n', f.read(), count=1)
                if old == text:
                    continue
            with open(target, 'w', encoding='utf-8') as f:
                f.write(text)
            print(f'dispatcher: {target} written')
    settings = os.path.join(folder, '.claude', 'settings.json')  # the dispatcher needs no memory: compact it early
    try:
        with open(settings, encoding='utf-8') as f:
            current = json.load(f)
    except (OSError, ValueError):
        current = {}
    window = int(cfg['dispatcher'].get('compact_tokens') or 120000)
    if isinstance(current, dict) and current.get('autoCompactWindow') != window:
        os.makedirs(os.path.dirname(settings), exist_ok=True)
        with open(settings, 'w', encoding='utf-8') as f:
            json.dump({**current, 'autoCompactWindow': window}, f, indent=2)
        print(f'dispatcher: {settings} – compacts at {window} tokens')
    at = os.path.join(folder, PROJECT_CONFIG)
    if link(cfg['_path'], at):
        print(f'dispatcher: {at} → {cfg["_path"]}')
    return folder


def exclude_locally(top, *names):
    """Keep agentq's links out of the project's git without touching its .gitignore."""
    names = [n.replace(os.sep, '/') for n in names]  # git patterns use /, also on Windows
    path = git(top, 'rev-parse', '--git-path', 'info/exclude').strip()
    path = path if os.path.isabs(path) else os.path.join(top, path)
    have = open(path, encoding='utf-8').read().split('\n') if os.path.exists(path) else []
    missing = [n for n in names if n not in have]
    if missing:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'a', encoding='utf-8') as f:
            f.write(('\n' if have and have[-1] else '') + '\n'.join(missing) + '\n')


def link(target, at):
    """A symlink; on Windows without the right to make one, a junction for a folder and a pointer file for a config."""
    if os.path.lexists(at):
        return False
    os.makedirs(os.path.dirname(at), exist_ok=True)
    try:
        os.symlink(target, at, target_is_directory=os.path.isdir(target))
    except OSError:
        if not WINDOWS:
            raise
        if os.path.isdir(target):
            run = subprocess.run(['cmd', '/c', 'mklink', '/J', at, target], capture_output=True, text=True,
                                 encoding='utf-8', errors='replace')
            if run.returncode != 0:
                raise Fail(f'cannot link {at} to {target}: {run.stderr.strip() or run.stdout.strip()}')
        else:
            with open(at, 'w', encoding='utf-8') as f:
                json.dump({POINTER: target}, f)
    return True


MACHINE_KEYS = ('checkout', 'tests', 'live', 'team_group', 'state_file', 'app_sessions', 'transcripts', 'shots_dir')
ROLE_MACHINE_KEYS = ('session', 'sessions', 'active', 'since', 'shots')


def like_config(path):
    """The team another computer's config describes – owner, AI account, labels, texts, roles, rules, links – without
    what belongs to that computer: its folders, sessions, test runs and running copy."""
    try:
        with open(os.path.expanduser(path), encoding='utf-8') as f:
            raw = json.load(f)
    except (OSError, ValueError) as e:
        raise Fail(f'cannot read the other computer\'s config {path}: {e}')
    if isinstance(raw, dict) and set(raw) == {POINTER}:
        return like_config(raw[POINTER])
    for key in MACHINE_KEYS:
        raw.pop(key, None)
    raw['dispatcher'] = {k: v for k, v in raw.get('dispatcher', {}).items() if k not in ('folder', 'session')}
    raw['roles'] = [{k: v for k, v in role.items() if k not in ROLE_MACHINE_KEYS} for role in raw.get('roles', [])]
    return raw


def cmd_init(opts):
    """Install the team into one project: its own config, the skill link, both kept out of the project's git."""
    top = git(os.path.abspath(opts.project or '.'), 'rev-parse', '--show-toplevel').strip()
    repo = opts.repo
    if not repo:
        url = git(top, 'remote', 'get-url', 'origin').strip()
        m = re.search(r'github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?/?$', url)
        if not m:
            raise Fail(f'cannot tell the GitHub repository from "{url}" (pass --repo owner/name)')
        repo = m.group(1)
    path = os.path.expanduser(opts.config or f"~/.config/agentq/{repo.replace('/', '-')}.json")
    if os.path.exists(path):
        print(f'config exists: {path}')
    else:
        who = gh_json('api', 'user')
        if opts.like:  # the same team from another computer: its labels, texts and roles, this computer's folders
            raw = like_config(opts.like)
        else:
            with open(os.path.join(PACKAGE, 'config.example.json'), encoding='utf-8') as f:
                raw = json.load(f)
        repos = raw.get('repos') if opts.like and repo in (raw.get('repos') or []) else [repo]
        raw.update({'owner_accounts': opts.owner, 'agent_account': who.get('login') or '', 'repos': repos,
                    'checkout': top})
        raw.pop('live', None)  # the example's restart command is a placeholder: `agentq live` sets a real one
        raw.setdefault('dispatcher', {})
        if opts.second:
            raw['primary'] = False
        raw['dispatcher']['folder'] = os.path.expanduser(f"~/agent-team/{repo.replace('/', '-')}-dispatcher")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(raw, f, indent=2, ensure_ascii=False)
            f.write('\n')
        print(f'config written: {path} (AI account: {raw["agent_account"] or "unknown – sign gh in"})')
    skill = os.path.join('.claude', 'skills', 'agent-team')
    if link(path, os.path.join(top, PROJECT_CONFIG)):
        print(f'{top}/{PROJECT_CONFIG} → {path}')
    if link(os.path.join(PACKAGE, 'skill', 'agent-team'), os.path.join(top, skill)):
        print(f'{top}/{skill} → the skill')
    exclude_locally(top, PROJECT_CONFIG, skill)
    if opts.codex:
        line = f"Team rules and the task queue: read `{os.path.join(PACKAGE, 'skill', 'agent-team', 'SKILL.md')}`."
        agents = os.path.join(top, 'AGENTS.md')
        text = open(agents, encoding='utf-8').read() if os.path.exists(agents) else ''
        if line not in text:
            with open(agents, 'a', encoding='utf-8') as f:
                f.write(('\n' if text and not text.endswith('\n') else '') + line + '\n')
            print(f'{agents}: the skill line added (for codex and other agents that read AGENTS.md)')
    print(f'installed in {top} only. Next: agentq setup (from the project folder).')


SESSION_BLOCK = re.compile(r'<!-- agentq:session -->.*?<!-- /agentq:session -->\n?', re.S)


def sync_dispatcher_session(cfg):
    """Write the dispatcher's own session id into its CLAUDE.md, so it never mistakes a role's id in a plan for its own."""
    path = os.path.join(cfg['team_dir'], 'CLAUDE.md')
    if not cfg['dispatcher']['folder'] or not os.path.exists(path):
        return
    own = cfg['dispatcher']['session']
    line = (f'Your own session id is `{own}`. Never send to it.' if own else
            'Your own session id is not recorded yet (`agentq role dispatcher --session <id>`).')
    block = (f'<!-- agentq:session -->\n{line} Every session id in a plan or in agentq\'s output belongs to a role '
             f'session, never to you: send to that session.\n<!-- /agentq:session -->\n')
    with open(path, encoding='utf-8') as f:
        text = f.read()
    if SESSION_BLOCK.search(text):
        new = SESSION_BLOCK.sub(lambda m: block, text, count=1)
    else:
        head, _, rest = text.partition('\n\n')
        new = f'{head}\n\n{block}\n{rest}'
    if new != text:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new)
        print(f'dispatcher: {path} – own session id {own or "not recorded yet"}')


def cmd_setup(cfg, opts):
    problems = []
    who = gh_json('api', 'user')
    login = who.get('login') if isinstance(who, dict) else None
    if login != cfg['agent_account']:
        problems.append(f"gh is signed in as {login or 'nobody'}, not the AI account {cfg['agent_account']} "
                        f"(the owner runs: gh auth login, or gh auth switch -u {cfg['agent_account']})")
    for repo in cfg['repos']:
        info = gh_json('api', f'repos/{repo}')
        rights = info.get('permissions', {}) if isinstance(info, dict) else {}
        if not rights.get('push'):
            problems.append(f'{cfg["agent_account"]} has no Write access to {repo} (the owner invites it with Write)')
        elif rights.get('admin'):
            problems.append(f'{cfg["agent_account"]} has Admin on {repo}; Write is enough (the owner lowers it)')
    if problems:
        print('missing – only the owner can fix these:\n' + '\n'.join(f'- {p}' for p in problems))
        return 1

    def fill(raw):
        raw.setdefault('roles', [{**r, 'session': ''} for r in DEFAULT_ROLES])
        for r in raw['roles']:
            if r.get('mode') == 'checker' and not r.get('since'):
                r['since'] = iso(now())
        if opts.group:
            raw['team_group'] = opts.group
        if opts.checkout:
            raw['checkout'] = os.path.abspath(os.path.expanduser(opts.checkout))
        disp = raw.setdefault('dispatcher', {})
        if opts.dispatcher_dir:
            disp['folder'] = os.path.abspath(os.path.expanduser(opts.dispatcher_dir))
        elif not disp.get('folder'):
            disp['folder'] = os.path.expanduser(f"~/agent-team/{cfg['repos'][0].replace('/', '-')}-dispatcher")
    cfg = save_config(cfg, fill)
    ensure_labels(cfg)
    install_dispatcher(cfg, cfg['dispatcher']['folder'])
    sync_dispatcher_session(cfg)
    write_roles(cfg)
    print_roles_table(cfg)
    return 0


def print_roles_table(cfg):
    print('role | label | mode | N | paths | model | effort | merge | session')
    for r in cfg['roles']:
        n = f"{r['n']}/{float(r['hours']):g}h" if r['mode'] == 'checker' else '-'
        print(f"{r['role']} | {r['label']} | {r['mode']} | {n} | {','.join(r['paths']) or '-'} | {r['model'] or '-'} | "
              f"{r['effort'] or '-'} | {'yes' if r['merge'] else 'no'} | {', '.join(r['pool']) or 'MISSING'}"
              + (f" (resting: {', '.join(r['sessions'][len(r['pool']):])})" if len(r['sessions']) > len(r['pool']) else ''))
    d = cfg['dispatcher']
    print(f"dispatcher | - | - | - | - | {d.get('model') or '-'} | {d.get('effort') or '-'} | - | "
          f"{d['session'] or 'MISSING'} | folder {d['folder'] or '-'}")
    print(f"sidebar group: {cfg.get('team_group') or 'MISSING'}")
