"""Everything that talks to GitHub (through `gh`, as the AI account) and to git."""

import datetime as dt
import json
import os
import re
import socket
import subprocess
import time
import uuid

from .system import running_in, tool
from .base import CLAIM_MARK, Fail, FULL, now, parse_time, REF, ROUTE_MARK


def gh(*args):
    for attempt in range(3):  # GitHub sometimes answers 502/503 or times out for a moment
        run = subprocess.run([*(tool('gh') or ['gh']), *args], capture_output=True, text=True, encoding='utf-8',
                             errors='replace')
        transient = re.search(r'\b50[234]\b|timeout|timed out|connection reset', run.stderr, re.I)
        if run.returncode == 0 or not transient or attempt == 2:
            break
        time.sleep(2 * (attempt + 1))
    if run.returncode != 0:
        raise Fail(f"gh {' '.join(args[:3])}: {run.stderr.strip() or run.stdout.strip()}")
    return run.stdout


def gh_json(*args):
    out = gh(*args)
    return json.loads(out) if out.strip() else []


def gh_pages(*args):
    """`gh api --paginate` prints one JSON array per page; join them."""
    out, items, at = gh(*args), [], 0
    decoder = json.JSONDecoder()
    while True:
        while at < len(out) and out[at].isspace():
            at += 1
        if at >= len(out):
            return items
        value, at = decoder.raw_decode(out, at)
        items += value if isinstance(value, list) else [value]


def git(checkout, *args):
    run = subprocess.run(['git', '-C', os.path.expanduser(checkout), *args], capture_output=True, text=True,
                         encoding='utf-8', errors='replace')
    if run.returncode != 0:
        raise Fail(f"git {' '.join(args[:2])}: {run.stderr.strip()}")
    return run.stdout


def resolve(cfg, ref):
    m = REF.match(ref.strip())
    if not m:
        raise Fail(f'"{ref}" is not an issue (use N, #N or owner/repo#N)')
    repo = m.group(1) or cfg['repos'][0]
    if repo not in cfg['repos']:
        raise Fail(f'{repo} is not in this config (repos: {", ".join(cfg["repos"])})')
    return repo, int(m.group(2))


def labels_of(issue):
    return [l['name'] for l in issue.get('labels', [])]


def login_of(item):
    who = item.get('author') or item.get('user') or {}
    return who.get('login')


def open_issues(repo):
    return gh_json('issue', 'list', '-R', repo, '--state', 'open', '--limit', '500',
                   '--json', 'number,title,labels,updatedAt,comments')


def board(repo):
    """The open issues without their comments: cheap enough to read every minute."""
    return gh_json('issue', 'list', '-R', repo, '--state', 'open', '--limit', '500',
                   '--json', 'number,title,labels,author,createdAt,updatedAt')


class IssueNotFound(Fail):
    """The issue is absent, while its repository can still be read."""


def view(repo, number):
    try:
        return gh_json('issue', 'view', str(number), '-R', repo, '--json', 'number,title,body,labels,state,author')
    except Fail as error:
        # GraphQL resolved the repository but not this issue. A bare 404 can also mean lost repository access.
        missing = f'Could not resolve to an issue or pull request with the number of {number}. (repository.issue)' in str(error)
        if not missing and 'HTTP 404' in str(error):
            repository = gh_json('repo', 'view', repo, '--json', 'nameWithOwner')
            missing = isinstance(repository, dict) and str(repository.get('nameWithOwner', '')).lower() == repo.lower()
        if missing:
            raise IssueNotFound(str(error)) from error
        raise


def signed(head, text):
    """`🤖 <role>: text` – a text of more than one line (agentq's own markers aside) starts below the signature, so its
    Markdown (lists, paragraphs) renders as the writer laid it out."""
    visible = re.sub(r'\n?<!--.*?-->', '', text or '', flags=re.S).strip()
    return f"🤖 {head}:{chr(10) * 2 if chr(10) in visible else ' '}{text}"


def comment(cfg, repo, number, text, who=None, agent=None, name=None):
    agent = agent or running_in()
    body = signed(f"{who or cfg['role']}{' · ' + agent if agent else ''}{f' ({name})' if name else ''}", text)
    gh('issue', 'comment', str(number), '-R', repo, '--body', body)


def relabel(repo, number, add=(), remove=()):
    args = ['issue', 'edit', str(number), '-R', repo]
    for name in add:
        args += ['--add-label', name]
    for name in remove:
        args += ['--remove-label', name]
    if len(args) > 5:
        gh(*args)


def create_issue(repo, title, body, labels):
    args = ['issue', 'create', '-R', repo, '--title', title, '--body', body]
    for name in labels:
        args += ['--label', name]
    url = gh(*args).strip().splitlines()[-1]
    m = re.search(r'/issues/(\d+)$', url)
    if not m:
        raise Fail(f'gh issue create printed no issue link: {url}')
    return int(m.group(1))


def claim(cfg, repo, number, text, who, agent=None, name=None):
    """GitHub has no lock: post a claim, read the comments back; the earliest claim of the last 10 minutes wins.
    A loser deletes its claim and returns False, so two dispatchers or workers on other computers never share a task."""
    mine = f'{socket.gethostname()}/{who}/{uuid.uuid4().hex[:8]}'
    comment(cfg, repo, number, f'{text}\n<!-- agentq:claim {mine} -->', who, agent, name)
    comments = gh_pages('api', f'repos/{repo}/issues/{number}/comments', '-H', FULL, '--paginate')
    # a claim before the task was handed back (`agentq route`) is over: its worker no longer holds it
    handed = max([c['created_at'] for c in comments if ROUTE_MARK in (c.get('body') or '')] or [''])
    recent = [c for c in comments if CLAIM_MARK.search(c.get('body') or '') and c['created_at'] > handed
              and now() - parse_time(c['created_at']) <= dt.timedelta(minutes=10)]
    recent.sort(key=lambda c: (c['created_at'], c.get('id', 0)))
    if not recent or CLAIM_MARK.search(recent[0]['body']).group(1) == mine:
        return True
    for c in recent:
        if CLAIM_MARK.search(c['body']).group(1) == mine and c.get('id'):
            gh('api', '-X', 'DELETE', f"repos/{repo}/issues/comments/{c['id']}")
    return False
