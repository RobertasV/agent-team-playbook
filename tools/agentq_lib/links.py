"""Linked projects: moving, splitting and opening tasks across them."""

import re

from .base import Fail, one_line
from .github import comment, create_issue, gh, labels_of, relabel, resolve, view
from .config import holder, role_by_name, role_of_labels, save_config
from .lessons import load_lessons, save_lessons, write_roles
from .state import update_state


def linked(cfg, repo):
    if repo not in [l['repo'] for l in cfg['links']]:
        raise Fail(f'{repo} is not a linked project (links: {", ".join(l["repo"] for l in cfg["links"]) or "none"}; '
                   f'agentq link adds one)')
    return repo


def cmd_move(cfg, opts):
    """All of it belongs to a linked project: transfer the issue there (or copy and close when GitHub refuses)."""
    repo, number = resolve(cfg, opts.issue)
    target = linked(cfg, opts.repo)
    issue = view(repo, number)
    names = labels_of(issue)
    owner = role_of_labels(cfg, names)  # no role label: the dispatcher is classifying it
    who = owner['role'] if owner else cfg['dispatcher']['name']
    ref = f'{repo}#{number}'
    comment(cfg, repo, number, cfg['texts']['moved'].format(repo=target, text=opts.text or '').strip(), who)
    ours = [r['label'] for r in cfg['roles']] + [cfg['labels']['working']]
    relabel(repo, number, remove=[n for n in names if n in ours])
    try:
        url = gh('issue', 'transfer', str(number), target, '-R', repo).strip().splitlines()[-1]
    except Fail:
        body = f"{cfg['texts']['moved_copy'].format(ref=ref)}\n\n{issue.get('body') or ''}"
        new = create_issue(target, issue['title'], body, [])
        gh('issue', 'close', str(number), '-R', repo, '--reason', 'not planned', '--comment', f'🤖 {who}: → {target}#{new}')
        url = f'{target}#{new}'
    update_state(cfg, lambda data: data.get('holders', {}).pop(ref, None))
    print(f'{ref} → {url}')
    if owner and not opts.no_lesson:
        lessons = load_lessons(cfg)
        moved = lessons['examples'].setdefault('@moved', [])
        moved.append({'issue': f'#{number}', 'title': one_line(issue['title'], 100), 'to': target})
        del moved[:-int(cfg['lesson_examples'])]
        save_lessons(cfg, lessons)
        print(f'lesson recorded for the dispatcher: #{number} belonged to {target}')


def cmd_open(cfg, opts):
    """A new task for a role in this project (e.g. a finding for the programmer), with the role's label. In a
    linked project: the task without labels, naming the role – that project's dispatcher sorts it."""
    repo = opts.repo or cfg['repos'][0]
    if repo not in cfg['repos']:
        linked(cfg, repo)
        number = create_issue(repo, opts.title, f"🤖 {opts.who or cfg['role']} ({cfg['repos'][0]}), for the "
                                                f"{opts.role} role: {opts.text}", [])
        print(f"{repo}#{number} opened in the linked project; its dispatcher gives it to {opts.role}")
        return
    role = role_by_name(cfg, opts.role)
    number = create_issue(repo, opts.title, f"🤖 {opts.who or cfg['role']}: {opts.text}", [role['label']])
    print(f"{repo}#{number} opened for {role['role']}")


def cmd_split(cfg, opts):
    """A part belongs to a linked project: a new issue there that links back; this one stays."""
    repo, number = resolve(cfg, opts.issue)
    target = linked(cfg, opts.repo)
    ref = f'{repo}#{number}'
    who = holder(cfg, view(repo, number))
    body = f"🤖 {who}: {opts.text}\n\n{cfg['texts']['split_from'].format(ref=ref)}"
    new = create_issue(target, opts.title, body, [])
    comment(cfg, repo, number, cfg['texts']['split'].format(repo=target, other=f'{target}#{new}'), who)
    print(f'{target}#{new} created from {ref}; {ref} stays here')


def cmd_link(cfg, opts):
    """Sharing between projects: add, change or remove a linked project in this project's config."""
    def change(raw):
        links = [l for l in raw.get('links', []) if l['repo'] != opts.repo]
        if not opts.remove:
            if not re.match(r'^[\w.-]+/[\w.-]+$', opts.repo):
                raise Fail(f'"{opts.repo}" must be owner/repo')
            if not opts.about:
                raise Fail('say what belongs there, e.g. "the website: pages, blog, SEO"')
            links.append({'repo': opts.repo, 'about': opts.about})
        raw['links'] = links
    cfg = save_config(cfg, change)
    write_roles(cfg)
    for l in cfg['links']:
        print(f"{l['repo']}: {l['about']}")
    if not cfg['links']:
        print('no linked projects: sharing is off')
