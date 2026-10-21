"""The dispatcher's routing lessons and rules, and roles.md written from them."""

import json
import os
import re

from .system import replace_file, temp_path
from .base import Fail


def lessons_path(cfg):
    return os.path.join(cfg['team_dir'], 'lessons.json')


def load_lessons(cfg):
    try:
        with open(lessons_path(cfg), encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}
    return {'rules': data.get('rules', []), 'examples': data.get('examples', {})}


def render_roles(cfg, lessons):
    lines = ['# Roles', '',
             'Written by agentq from the config, `agentq route` and `agentq teach`. Do not edit by hand.', '']
    for role in cfg['roles']:
        extra = ' (default: when unsure)' if role['role'] == cfg['default_role'] else ''
        lines.append(f"## {role['role']}{extra}")
        mode = role['mode'] + (f", batches of {role['n']} or {role['hours']} h" if role['mode'] == 'checker' else '')
        lines.append(f"Label `{role['label']}`, {mode}." + (f" Paths: {', '.join(role['paths'])}." if role['paths'] else ''))
        if role['description']:
            lines.append(role['description'])
        lines += [f'- e.g. {e}' for e in role['examples']]
        lines += [f'- reference screenshot: examples/{name}' for name in role['shots']]
        routed = lessons['examples'].get(role['role'], [])
        if routed:
            lines.append('Routed here by a role that got it by mistake:')
            lines += [f"- {e['issue']} {e['title']} (not {e['from']})" for e in routed]
        lines.append('')
    if cfg['links']:
        lines.append('## Linked projects (sharing on)')
        lines.append('A task that belongs wholly to one of these moves there; a mixed one goes to the default role.')
        lines += [f"- {l['repo']}: {l['about']}" for l in cfg['links']]
        moved = lessons['examples'].get('@moved', [])
        if moved:
            lines.append('Moved there by a role after it came here:')
            lines += [f"- {e['issue']} {e['title']} → {e['to']}" for e in moved]
        lines.append('')
    lines.append('## Rules')
    names = {r['role'] for r in cfg['roles']}
    lines += [f"- {r['text']} ({r['by']})" for r in lessons['rules'] if r.get('role') in names | {None}] or ['- none yet']
    return '\n'.join(lines) + '\n'


def save_lessons(cfg, lessons):
    os.makedirs(cfg['team_dir'], exist_ok=True)
    tmp = temp_path(lessons_path(cfg))
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(lessons, f, indent=2, ensure_ascii=False)
    replace_file(tmp, lessons_path(cfg))
    write_roles(cfg, lessons)


def write_roles(cfg, lessons=None):
    os.makedirs(cfg['team_dir'], exist_ok=True)
    with open(os.path.join(cfg['team_dir'], 'roles.md'), 'w', encoding='utf-8') as f:
        f.write(render_roles(cfg, lessons or load_lessons(cfg)))


def rule_role(cfg, rest):
    """The role a rule points to: the role name it starts with; anything after it is a note ("designer (writes only)")."""
    hits = [r['role'] for r in cfg['roles'] if re.match(rf'{re.escape(r["role"])}(?!\w)', rest.strip(), re.I)]
    if not hits:
        raise Fail(f'"{rest}" does not start with a role (roles: {", ".join(r["role"] for r in cfg["roles"])}); '
                   f'write "topic → role", a note may follow the role')
    return max(hits, key=len)
