#!/usr/bin/env python3
"""A stand-in for `gh` in tests: answers from a fixture, logs every call, never touches GitHub."""
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')  # agentq reads gh's output as UTF-8, as the real gh writes it
args = sys.argv[1:]
with open(os.environ['FAKE_GH_LOG'], 'a', encoding='utf-8') as log:
    log.write(json.dumps(args) + '\n')
with open(os.environ['FAKE_GH_FIXTURE'], encoding='utf-8') as f:
    data = json.load(f)


def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default


repo = data.get(opt('-R'), {})
if args[:2] == ['issue', 'list']:
    state = opt('--state')
    issues = repo.get('open', []) + repo.get('closed', []) if state == 'all' else repo.get(state, [])
    label = opt('--label')
    if label:
        issues = [i for i in issues if label in [l['name'] for l in i.get('labels', [])]]
    print(json.dumps(issues))
elif args[:2] == ['issue', 'view']:
    if error := repo.get('view_errors', {}).get(args[2]):
        print(error, file=sys.stderr)
        sys.exit(1)
    found = {'state': repo.get('states', {}).get(args[2], 'OPEN')}
    for state in ('open', 'closed'):
        for i in repo.get(state, []):
            if str(i['number']) == args[2]:
                found = {**i, 'state': state.upper()}
    print(json.dumps(found))
elif args[:2] == ['issue', 'create']:
    if repo.get('create_fails'):
        print('issue creation refused', file=sys.stderr)
        sys.exit(1)
    print(f"https://github.com/{opt('-R')}/issues/{repo.get('next', 100)}")
elif args[:2] == ['repo', 'view']:
    if error := data.get(args[2], {}).get('repo_error'):
        print(error, file=sys.stderr)
        sys.exit(1)
    print(json.dumps({'nameWithOwner': args[2]}))
elif args[:2] == ['issue', 'transfer']:
    if repo.get('transfer_fails'):
        print('cannot transfer between accounts', file=sys.stderr)
        sys.exit(1)
    print(f"https://github.com/{args[3]}/issues/{data.get(args[3], {}).get('next', 100)}")
elif args[:2] == ['pr', 'list']:
    print(json.dumps(repo.get('prs', [])))
elif args[:2] == ['label', 'list']:
    print(json.dumps([{'name': n} for n in repo.get('labels', [])]))
elif args[:2] == ['issue', 'comment']:  # remembered, so a claim can read itself back
    key = f"repos/{opt('-R')}/issues/{args[2]}/comments"
    listing = data.setdefault('api', {}).setdefault(key, [])
    listing.append({'id': 1000 + len(listing), 'user': {'login': 'bot'}, 'body': opt('--body'),
                    'created_at': os.environ.get('AGENTQ_NOW', '2026-01-02T12:00:00Z')})
    with open(os.environ['FAKE_GH_FIXTURE'], 'w', encoding='utf-8') as f:
        json.dump(data, f)
elif args[:2] in (['issue', 'edit'], ['issue', 'close'], ['issue', 'reopen'], ['label', 'create']):
    pass
elif args[:3] == ['api', '-X', 'DELETE']:
    pass
elif args[0] == 'api' and '/contents/' in args[1]:
    if args[1] not in data.get('raw', {}):
        print('gh: Not Found (HTTP 404)', file=sys.stderr)
        sys.exit(1)
    sys.stdout.write(data['raw'][args[1]])
elif args[0] == 'api':
    listing = args[1].split('?')[0].endswith(('/comments', '/events'))
    print(json.dumps(data.get('api', {}).get(args[1], [] if listing else {})))
else:
    print(f'fake gh: unexpected {args}', file=sys.stderr)
    sys.exit(2)
