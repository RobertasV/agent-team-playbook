"""agentq against a fake `gh`: python3 -m unittest discover -s tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, 'tools', 'agentq')
FAKE = os.path.join(ROOT, 'tests', 'fake_gh.py')
REPO = 'acme/app'
OTHER = 'acme/site'


def issue(number, title, labels=(), updated='2026-01-01T10:00:00Z', comments=()):
    return {'number': number, 'title': title, 'labels': [{'name': n} for n in labels],
            'updatedAt': updated, 'comments': list(comments)}


def said(login, body, at):
    return {'author': {'login': login}, 'body': body, 'createdAt': at}


class AgentqTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        d = self.dir.name
        os.makedirs(os.path.join(d, 'bin'))
        gh = os.path.join(d, 'bin', 'gh')
        with open(gh, 'w') as f:
            f.write(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n')
        os.chmod(gh, 0o755)
        self.log = os.path.join(d, 'gh.log')
        self.fixture = os.path.join(d, 'fixture.json')
        self.config = os.path.join(d, 'config.json')
        with open(self.config, 'w') as f:
            json.dump({
                'owner_accounts': ['boss'], 'agent_account': 'bot', 'role': 'programmer', 'repos': [REPO],
                'labels': {'working': 'doing', 'question': 'ask owner', 'deferred': 'later', 'waiting': 'waits'},
                'skip_labels': ['after launch'],
            }, f)
        self.data({})

    def tearDown(self):
        self.dir.cleanup()

    def data(self, value):
        with open(self.fixture, 'w') as f:
            json.dump(value, f)

    def run_tool(self, *args, now='2026-01-02T12:00:00Z', ok=True):
        env = {**os.environ, 'PATH': os.path.join(self.dir.name, 'bin') + os.pathsep + os.environ['PATH'],
               'FAKE_GH_LOG': self.log, 'FAKE_GH_FIXTURE': self.fixture, 'AGENTQ_NOW': now}
        run = subprocess.run([sys.executable, TOOL, '--config', self.config, *args],
                             capture_output=True, text=True, env=env)
        if ok:
            self.assertEqual(run.returncode, 0, run.stderr)
        return run

    def calls(self, verb=None):
        if not os.path.exists(self.log):
            return []
        rows = [json.loads(l) for l in open(self.log)]
        return [r for r in rows if verb is None or r[:2] == verb]

    def test_queue_skips_labels_and_shows_new_owner_comments(self):
        self.data({REPO: {'open': [
            issue(3, 'Crash on start'),
            issue(1, 'Later thing', ['later']),
            issue(2, 'After launch', ['after launch']),
            issue(4, 'Being fixed', ['doing']),
            issue(5, 'Old talk', comments=[said('boss', 'old words', '2026-01-01T09:00:00Z')]),
        ]}})
        first = self.run_tool('queue', now='2026-01-02T12:00:00Z').stdout
        self.assertIn('first run', first)
        self.assertIn('acme/app#3', first)
        self.assertIn('acme/app#5', first)
        self.assertNotIn('#1 ', first)
        self.assertNotIn('#2 ', first)
        self.assertIn('in progress (1)', first)
        self.data({REPO: {'open': [
            issue(1, 'Later thing', ['later'], comments=[said('boss', 'do it now please', '2026-01-02T13:00:00Z')]),
            issue(3, 'Crash on start', comments=[said('bot', '🤖 programmer: note', '2026-01-02T13:30:00Z')]),
        ]}})
        second = self.run_tool('queue', '--all', now='2026-01-02T14:00:00Z').stdout
        self.assertIn('owner comments since 2026-01-02T12:00:00Z: 1', second)
        self.assertIn('acme/app#1 Later thing: do it now please', second)
        self.assertIn('skipped: later 1', second)
        third = self.run_tool('queue', now='2026-01-02T15:00:00Z').stdout
        self.assertIn('owner comments since 2026-01-02T14:00:00Z: none', third)

    def test_peek_keeps_the_mark(self):
        self.data({REPO: {'open': []}})
        self.run_tool('queue', '--peek')
        self.assertIn('first run', self.run_tool('queue').stdout)

    def test_take_ask_defer_change_comment_and_labels_together(self):
        self.run_tool('take', '7')
        self.run_tool('ask', '#7', 'Which price level?')
        self.run_tool('defer', 'acme/app#8', '„later“')
        comments = self.calls(['issue', 'comment'])
        edits = self.calls(['issue', 'edit'])
        self.assertEqual(comments[0][comments[0].index('--body') + 1], '🤖 programmer: taking this.')
        self.assertEqual(edits[0], ['issue', 'edit', '7', '-R', REPO, '--add-label', 'doing'])
        self.assertEqual(comments[1][comments[1].index('--body') + 1], '🤖 programmer: Which price level?')
        self.assertEqual(edits[1], ['issue', 'edit', '7', '-R', REPO, '--add-label', 'ask owner', '--remove-label', 'doing'])
        self.assertEqual(comments[2][comments[2].index('--body') + 1], '🤖 programmer: deferred. „later“')
        self.assertEqual(edits[2], ['issue', 'edit', '8', '-R', REPO, '--add-label', 'later', '--remove-label', 'doing'])

    def test_unknown_repo_and_bad_ref_fail_without_calls(self):
        run = self.run_tool('take', 'other/repo#3', ok=False)
        self.assertEqual(run.returncode, 1)
        self.assertIn('not in this config', run.stderr)
        self.assertEqual(self.run_tool('take', 'x', ok=False).returncode, 1)
        self.assertEqual(self.calls(), [])

    def test_wait_then_check_fix_puts_it_back_when_the_other_closes(self):
        self.run_tool('wait', '9', f'{OTHER}#4')
        body = self.calls(['issue', 'comment'])[0]
        text = body[body.index('--body') + 1]
        self.assertIn(f'waiting for {OTHER}#4.', text)
        self.assertIn(f'<!-- agentq:wait {OTHER}#4 -->', text)
        waiting = issue(9, 'Needs the site', ['waits'], comments=[said('bot', text, '2026-01-02T10:00:00Z')])
        self.data({REPO: {'open': [waiting], 'closed': []}, OTHER: {'states': {'4': 'OPEN'}}})
        self.assertIn('all consistent', self.run_tool('check').stdout)
        self.data({REPO: {'open': [waiting], 'closed': []}, OTHER: {'states': {'4': 'CLOSED'}}})
        self.assertIn('run check --fix', self.run_tool('check').stdout)
        out = self.run_tool('check', '--fix').stdout
        self.assertIn(f'fixed  {REPO}#9: {OTHER}#4 closed', out)
        self.assertEqual(self.calls(['issue', 'edit'])[-1], ['issue', 'edit', '9', '-R', REPO, '--remove-label', 'waits'])

    def test_check_reports_stale_work_unanswered_owner_and_closed_working(self):
        self.data({REPO: {
            'open': [issue(1, 'Stale', ['doing'], updated='2026-01-01T00:00:00Z'),
                     issue(2, 'Owner asked', comments=[said('boss', 'why is this red?', '2026-01-02T08:00:00Z')]),
                     issue(3, 'Answered', comments=[said('boss', 'q', '2026-01-02T08:00:00Z'),
                                                    said('bot', 'a', '2026-01-02T09:00:00Z')])],
            'closed': [issue(4, 'Done', ['doing'])]}})
        out = self.run_tool('check', now='2026-01-02T12:00:00Z').stdout
        self.assertIn(f"{REPO}#1: 'doing' but nothing happened for over 24 h", out)
        self.assertIn(f"{REPO}#2: the owner's comment waits for an answer – why is this red?", out)
        self.assertNotIn(f'{REPO}#3', out)
        self.assertIn(f"{REPO}#4: closed but still 'doing'", out)
        self.run_tool('check', '--fix', now='2026-01-02T12:00:00Z')
        self.assertIn(['issue', 'edit', '4', '-R', REPO, '--remove-label', 'doing'], self.calls(['issue', 'edit']))

    def test_setup_creates_only_missing_labels(self):
        self.data({REPO: {'labels': ['doing', 'later']}})
        self.run_tool('setup')
        made = [c[2] for c in self.calls(['label', 'create'])]
        self.assertEqual(sorted(made), ['ask owner', 'waits'])

    def test_project_config_is_found_from_a_subfolder(self):
        project = os.path.join(self.dir.name, 'project')
        os.makedirs(os.path.join(project, 'src', 'deep'))
        os.symlink(self.config, os.path.join(project, '.agentq.json'))
        env = {**os.environ, 'PATH': os.path.join(self.dir.name, 'bin') + os.pathsep + os.environ['PATH'],
               'FAKE_GH_LOG': self.log, 'FAKE_GH_FIXTURE': self.fixture, 'AGENTQ_NOW': '2026-01-02T12:00:00Z'}
        env.pop('AGENTQ_CONFIG', None)
        run = subprocess.run([sys.executable, TOOL, 'take', '5'], capture_output=True, text=True, env=env,
                             cwd=os.path.join(project, 'src', 'deep'))
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.calls(['issue', 'edit'])[0][:3], ['issue', 'edit', '5'])

    def test_missing_config_key_is_named(self):
        with open(self.config, 'w') as f:
            json.dump({'owner_accounts': ['boss']}, f)
        run = self.run_tool('queue', ok=False)
        self.assertIn('"agent_account" is missing', run.stderr)


class NoPrivateNamesTest(unittest.TestCase):
    """The package is shared with friends: none of the owner's private words may appear in it.
    The list lives outside the package (AGENTQ_PRIVATE_WORDS or ~/.config/agentq/private-words.txt)."""

    def test_no_private_words(self):
        path = os.environ.get('AGENTQ_PRIVATE_WORDS', os.path.expanduser('~/.config/agentq/private-words.txt'))
        if not os.path.exists(path):
            self.skipTest(f'no private word list at {path}')
        words = [w.strip().lower() for w in open(path, encoding='utf-8') if w.strip() and not w.startswith('#')]
        hits = []
        for base, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__')]
            for name in files:
                full = os.path.join(base, name)
                try:
                    text = open(full, encoding='utf-8').read().lower()
                except UnicodeDecodeError:
                    continue
                hits += [f'{os.path.relpath(full, ROOT)}: {w}' for w in words if w in text]
        self.assertEqual(hits, [])


if __name__ == '__main__':
    unittest.main()
