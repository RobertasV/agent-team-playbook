"""The brief a worker reads for a task: its text, the owner's words verbatim, screenshots as local files."""

import html
import os
import subprocess
import urllib.parse
import urllib.request

from .system import tool
from .base import BATCH_MARK, FULL, IMG, parse_time, RELEASE_FILE, REPO_FILE, ROUTE_MARK
from .github import gh_json, gh_pages, labels_of, login_of, resolve
from .config import default_role, role_of_labels
from .state import comment_key, load_delivered, load_state, mark_delivered


def shot_name(url, kind, n):
    ext = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/gif': '.gif', 'image/webp': '.webp'}.get(kind)
    if not ext:
        ext = os.path.splitext(urllib.parse.urlparse(url).path)[1][:5] or '.img'
    return f'shot-{n}{ext}'


def repo_file(match):
    """A file in a (maybe private) repository, read through gh as the AI account."""
    owner, repo, ref, path = [g for g in match.groups() if g is not None]
    path = urllib.parse.quote(urllib.parse.unquote(path))
    run = subprocess.run([*(tool('gh') or ['gh']), 'api', f'repos/{owner}/{repo}/contents/{path}?ref={ref}', '-H',
                          'Accept: application/vnd.github.raw'], capture_output=True)
    if run.returncode != 0:
        raise OSError(f'the AI account cannot read {owner}/{repo} (the owner invites it with Read access)')
    return run.stdout


def release_file(match):
    """A file of a (maybe private) repository's release, read through gh as the AI account."""
    owner, repo, tag, name = match.groups()
    run = subprocess.run([*(tool('gh') or ['gh']), 'release', 'download', urllib.parse.unquote(tag), '-R', f'{owner}/{repo}',
                          '-p', urllib.parse.unquote(name), '-O', '-'], capture_output=True)
    if run.returncode != 0:
        raise OSError(f'the AI account cannot read {owner}/{repo} (the owner invites it with Read access)')
    return run.stdout


def download_shots(rendered, folder, first):
    """Uploaded images have short-lived signed links in GitHub's rendered HTML that need no login, even in private
    repos; an image linked from a repository is read through gh."""
    paths = []
    for n, src in enumerate((html.unescape(s) for s in IMG.findall(rendered or '')), first):
        if urllib.parse.urlparse(src).scheme not in ('https', 'file'):  # file: only in tests
            continue
        try:
            in_repo, in_release = REPO_FILE.match(src), RELEASE_FILE.match(src)
            if in_repo:
                data, kind = repo_file(in_repo), ''
            elif in_release:
                data, kind = release_file(in_release), ''
            else:
                with urllib.request.urlopen(src, timeout=30) as r:
                    data, kind = r.read(), (r.headers.get('Content-Type') or '').split(';')[0]
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, shot_name(src, kind, n))
            with open(path, 'wb') as f:
                f.write(data)
            paths.append(path)
        except OSError as e:
            paths.append(f'(could not download screenshot {n}: {e})')
    return paths


def cmd_brief(cfg, opts):
    repo, number = resolve(cfg, opts.issue)
    ref = f'{repo}#{number}'
    issue = gh_json('api', f'repos/{repo}/issues/{number}', '-H', FULL)
    comments = gh_pages('api', f'repos/{repo}/issues/{number}/comments', '-H', FULL, '--paginate')
    owners = set(cfg['owner_accounts'])
    since = parse_time(opts.since) if opts.since else None
    testers = {t.lower() for t in cfg['testers']}  # their results reach the programmer; they are not the owner
    picked = [c for c in comments if (login_of(c) in owners or (login_of(c) or '').lower() in testers)
              and (since is None or parse_time(c['created_at']) >= since)]
    names = labels_of(issue)
    role = role_of_labels(cfg, names) or default_role(cfg)
    folder = os.path.join(cfg['shots_dir'], repo.replace('/', '-'), str(number))
    texts = cfg['texts']
    out = [(texts['brief_news'] if since else texts['brief_head']).format(ref=ref, role=role['role']),
           f"Title: {issue['title']}"]
    if not since and role['description']:  # the role's own rules, every task, so a long-running session has them now
        out.insert(1, f"Your role ({role['role']}): {role['description']}")
    shots = []
    if not since:
        author = login_of(issue)
        tag = 'the owner' if author in owners else 'an agent' if author == cfg['agent_account'] else 'NOT the owner'
        out += [f'Labels: {", ".join(names) or "none"}', f'--- issue text by {author} ({tag}) ---',
                (issue.get('body') or '(empty)').strip()]
        shots += download_shots(issue.get('body_html'), folder, 1)
    handover = [c for c in comments if login_of(c) == cfg['agent_account'] and ROUTE_MARK in (c.get('body') or '')]
    if handover and not since:  # the note of the role that handed it over (e.g. "merge branch …")
        c = handover[-1]
        out += [f"--- handed over, {c['created_at']} ---", c['body'].replace(ROUTE_MARK, '').strip()]
    for c in picked:
        who = 'the owner' if login_of(c) in owners else 'the human tester'
        out += [f"--- {who} ({login_of(c)}), {c['created_at']} ---", (c.get('body') or '').strip()]
        shots += download_shots(c.get('body_html'), folder, len(shots) + 1)
    if shots:
        out.append('--- screenshots, in order, as local files ---')
        out += shots
    mark_delivered(cfg, repo, picked, cfg['forward_hours'])
    if not since:
        batch = BATCH_MARK.search(issue.get('body') or '')
        finish = 'finish_batch' if batch else 'finish' if role['merge'] else 'finish_handoff'
        out += ['---', texts['act'].format(ref=ref), texts[finish].format(ref=ref, number=number, default=cfg['default_role'])]
        if cfg['links'] and not batch:
            out.append(texts['finish_links'].format(ref=ref))
        if cfg['testers'] and cfg['labels']['human_test'] in names:
            out.append(texts['human_brief'].format(ref=ref, number=number))
        if not batch and role['mode'] == 'programmer':
            mode = cfg['tests']['mode']
            out.append(texts['tests_batched' if mode == 'batched' else 'tests_off' if mode == 'off' else 'tests_per_task']
                       .format(every=cfg['tests']['every']))
        live = cfg.get('live') or {}
        if live.get('command'):  # the owner's running copy: one role restarts it, nobody else
            if role['role'].lower() == live['role'].lower():
                green = load_state(cfg).get('tests', {}).get('green') if cfg['tests']['mode'] == 'batched' else None
                target = f'the last green commit, {green}' if green else 'the commit you checked'
                out.append(texts['live_checked' if live.get('when') == 'checked' else 'live']
                           .format(command=live['command'], target=target))
            else:
                out.append(texts['live_other'].format(role=live['role']))
        out.append(texts['after'].format(role=role['role']))
    print('\n'.join(out))


def unread_words(cfg, repo, number):
    """The owner's comments written after the last agent comment that no brief has delivered."""
    comments = gh_pages('api', f'repos/{repo}/issues/{number}/comments', '-H', FULL, '--paginate')
    last_agent = max([c['created_at'] for c in comments if login_of(c) == cfg['agent_account']] or [''])
    delivered = (load_delivered(cfg) or {}).get(repo, {})
    return [c for c in comments if login_of(c) in set(cfg['owner_accounts']) and c['created_at'] > last_agent
            and comment_key(c) not in delivered]
