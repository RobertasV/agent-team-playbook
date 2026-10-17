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
    issues = repo.get(opt('--state'), [])
    label = opt('--label')
    if label:
        issues = [i for i in issues if label in [l['name'] for l in i.get('labels', [])]]
    print(json.dumps(issues))
elif args[:2] == ['issue', 'view']:
    print(json.dumps({'state': repo.get('states', {}).get(args[2], 'OPEN')}))
elif args[:2] == ['label', 'list']:
    print(json.dumps([{'name': n} for n in repo.get('labels', [])]))
elif args[:2] in (['issue', 'comment'], ['issue', 'edit'], ['label', 'create']):
    pass
else:
    print(f'fake gh: unexpected {args}', file=sys.stderr)
    sys.exit(2)
