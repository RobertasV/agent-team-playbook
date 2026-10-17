#!/usr/bin/env python3
"""A stand-in for `gh` in tests: answers from a fixture, logs every call, never touches GitHub."""
import json
import os
import sys

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
    found = {'state': repo.get('states', {}).get(args[2], 'OPEN')}
    for state in ('open', 'closed'):
        for i in repo.get(state, []):
            if str(i['number']) == args[2]:
                found = {**i, 'state': state.upper()}
    print(json.dumps(found))
elif args[:2] == ['issue', 'create']:
    print(f"https://github.com/{opt('-R')}/issues/{repo.get('next', 100)}")
elif args[:2] == ['issue', 'transfer']:
    if repo.get('transfer_fails'):
        print('cannot transfer between accounts', file=sys.stderr)
        sys.exit(1)
    print(f"https://github.com/{args[3]}/issues/{data.get(args[3], {}).get('next', 100)}")
elif args[:2] == ['label', 'list']:
    print(json.dumps([{'name': n} for n in repo.get('labels', [])]))
elif args[:2] in (['issue', 'comment'], ['issue', 'edit'], ['issue', 'close'], ['label', 'create']):
    pass
elif args[0] == 'api':
    print(json.dumps(data.get('api', {}).get(args[1], [] if args[1].endswith('/comments') else {})))
else:
    print(f'fake gh: unexpected {args}', file=sys.stderr)
    sys.exit(2)
