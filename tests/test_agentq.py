"""agentq against a fake `gh`: python3 -m unittest discover -s tests"""
import datetime
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, 'tools', 'agentq')
FAKE = os.path.join(ROOT, 'tests', 'fake_gh.py')
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from agentq_lib import apps, state, system  # noqa: E402 – its file lock and helpers, for tests that look inside


def fake_script(path, log=None, fail=None):
    """A stand-in for codex or open, as a Python file agentq runs with this Python (no shebang on Windows): it logs
    its arguments like `echo "$@"`, or fails with a message."""
    with open(path, 'w', encoding='utf-8') as f:
        if fail is not None:
            f.write('import sys\n' + (f'sys.stderr.write({fail!r} + "\\n")\n' if fail else '') + 'sys.exit(1)\n')
        else:
            f.write(f'import sys\nwith open({log!r}, "a", encoding="utf-8") as f:\n    f.write(" ".join(sys.argv[1:]) + "\\n")\n')
REPO = 'acme/app'
OTHER = 'acme/site'


def issue(number, title, labels=(), updated='2026-01-01T10:00:00Z', comments=(), author='boss', **more):
    return {'number': number, 'title': title, 'labels': [{'name': n} for n in labels],
            'updatedAt': updated, 'comments': list(comments), 'author': {'login': author}, **more}


def said(login, body, at):
    return {'author': {'login': login}, 'body': body, 'createdAt': at, 'id': f'{login}-{at}'}


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)  # Windows: a watcher still has a file open
        d = self.dir.name
        os.makedirs(os.path.join(d, 'bin'))
        for name in ('codex', 'open'):  # never the real Codex: these only log what agentq asked of them
            fake_script(os.path.join(d, 'bin', f'fake_{name}.py'), log=os.path.join(d, f'{name}.log'))
        self.log = os.path.join(d, 'gh.log')
        self.fixture = os.path.join(d, 'fixture.json')
        self.config = os.path.join(d, 'config.json')
        with open(self.config, 'w') as f:
            json.dump({
                'owner_accounts': ['boss'], 'agent_account': 'bot', 'role': 'programmer', 'repos': [REPO],
                'labels': {'working': 'doing', 'question': 'ask owner', 'deferred': 'later', 'waiting': 'waits'},
                'skip_labels': ['after launch'], 'disk_min_gb': 0,
            }, f)
        self.data({})

    def tearDown(self):
        self.dir.cleanup()

    def data(self, value):
        with open(self.fixture, 'w') as f:
            json.dump(value, f)

    def run_tool(self, *args, now='2026-01-02T12:00:00Z', ok=True, env=None):
        run = subprocess.run([sys.executable, TOOL, '--config', self.config, *args],
                             capture_output=True, text=True, env={**self.env(now), **(env or {})})
        if ok:
            self.assertEqual(run.returncode, 0, run.stderr)
        return run

    def as_codex(self, *args, thread='t1', now='2026-01-02T12:00:00Z', ok=True):
        return self.run_tool(*args, now=now, ok=ok, env={'CODEX_THREAD_ID': thread})

    def faked(self, name):
        path = os.path.join(self.dir.name, f'{name}.log')
        return open(path, encoding='utf-8').read() if os.path.exists(path) else ''

    def state(self, change=None):
        path = self.config + '.state.json'
        data = json.load(open(path)) if os.path.exists(path) else {}
        if change:
            change(data)
            with open(path, 'w') as f:
                json.dump(data, f)
        return data

    def env(self, now='2026-01-02T12:00:00Z'):
        return {**os.environ, 'AGENTQ_GH': FAKE, 'USERPROFILE': os.path.join(self.dir.name, 'home'),
                'PYTHONUTF8': '0',  # agentq as it runs for a user: on Windows without Python's UTF-8 mode
                'FAKE_GH_LOG': self.log, 'FAKE_GH_FIXTURE': self.fixture, 'AGENTQ_NOW': now,
                'HOME': os.path.join(self.dir.name, 'home'), 'AGENTQ_CONFIG': '',
                'AGENTQ_APP_SESSIONS': os.path.join(self.dir.name, 'app'), 'AGENTQ_TRANSCRIPTS': os.path.join(self.dir.name, 'tx'),
                'CLAUDECODE': '', 'CODEX_THREAD_ID': '', 'CODEX_SANDBOX': '', 'CLAUDE_CODE_HOST_SESSION_ID': '',
                'AGENTQ_CODEX': os.path.join(self.dir.name, 'bin', 'fake_codex.py'), 'AGENTQ_CODEX_APP': '1',
                'AGENTQ_OPEN': os.path.join(self.dir.name, 'bin', 'fake_open.py'),
                'CODEX_HOME': os.path.join(self.dir.name, 'codexhome')}

    def body(self, call):
        return call[call.index('--body') + 1]

    def calls(self, verb=None):
        if not os.path.exists(self.log):
            return []
        rows = [json.loads(l) for l in open(self.log)]
        return [r for r in rows if verb is None or r[:2] == verb]

class AgentqTest(Base):
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

    def test_a_longer_text_comes_on_stdin_and_starts_below_the_signature(self):
        text = 'Which way?\n\n1. **Read only** – recommended.\n2. Keep the old versions.'
        run = subprocess.run([sys.executable, TOOL, '--config', self.config, 'ask', '#7', '-'], input=text + '\n',
                             capture_output=True, text=True, encoding='utf-8', env=self.env())
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.body(self.calls(['issue', 'comment'])[-1]), f'🤖 programmer:\n\n{text}')
        self.run_tool('wait', '#7', f'{OTHER}#4')  # agentq's own marker on a second line keeps a short text inline
        self.assertTrue(self.body(self.calls(['issue', 'comment'])[-1]).startswith(f'🤖 programmer: waiting for {OTHER}#4.'))

    def test_the_watcher_puts_a_waiting_task_back_when_the_other_closes(self):
        text = f'🤖 programmer: waiting for {OTHER}#4.\n<!-- agentq:wait {OTHER}#4 -->'
        waiting = issue(9, 'Needs the site', ['prog', 'waits'], comments=[said('bot', text, '2026-01-02T10:00:00Z')])
        self.data({REPO: {'open': [waiting]}, OTHER: {'states': {'4': 'OPEN'}}})
        self.assertNotIn(f'{REPO}#9', self.run_tool('watch', '--once').stdout)
        self.data({REPO: {'open': [waiting]}, OTHER: {'states': {'4': 'CLOSED'}}})
        self.assertNotIn(f'{REPO}#9', self.run_tool('watch', '--once', now='2026-01-02T12:05:00Z').stdout)  # 10 min apart
        out = self.run_tool('watch', '--once', now='2026-01-02T12:11:00Z').stdout
        self.assertIn(['issue', 'edit', '9', '-R', REPO, '--remove-label', 'waits'], self.calls(['issue', 'edit']))
        self.assertIn(f'{OTHER}#4 is closed – back in the queue.', self.body(self.calls(['issue', 'comment'])[-1]))
        self.assertIn(f'run `agentq assign {REPO}#9', out)  # in the plan again

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
        self.data({REPO: {'labels': ['doing', 'later']},
                   'api': {'user': {'login': 'bot'}, f'repos/{REPO}': {'permissions': {'push': True}}}})
        self.run_tool('setup')
        made = [c[2] for c in self.calls(['label', 'create'])]
        self.assertIn('ask owner', made)
        self.assertIn('waits', made)
        self.assertIn('checked: checker', made)
        self.assertNotIn('doing', made)
        self.assertNotIn('later', made)

    def test_project_config_is_found_from_a_subfolder(self):
        project = os.path.join(self.dir.name, 'project')
        os.makedirs(os.path.join(project, 'src', 'deep'))
        os.symlink(self.config, os.path.join(project, '.agentq.json'))
        run = subprocess.run([sys.executable, TOOL, 'take', '5'], capture_output=True, text=True, env=self.env(),
                             cwd=os.path.join(project, 'src', 'deep'))
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.calls(['issue', 'edit'])[0][:3], ['issue', 'edit', '5'])

    def test_plain_agentq_shows_its_commands(self):
        run = subprocess.run([sys.executable, TOOL], capture_output=True, text=True, env=self.env())
        self.assertEqual(run.returncode, 0)
        self.assertIn('assign', run.stdout)

    def test_config_may_follow_the_command(self):
        run = subprocess.run([sys.executable, TOOL, 'take', '5', '--config', self.config],
                             capture_output=True, text=True, env=self.env())
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.calls(['issue', 'edit'])[0][:3], ['issue', 'edit', '5'])

    def test_from_a_scratch_folder_the_config_is_found_through_the_session(self):
        project = os.path.join(self.dir.name, 'project')
        scratch = os.path.join(self.dir.name, 'scratch')
        os.makedirs(project)
        os.makedirs(scratch)
        os.symlink(self.config, os.path.join(project, '.agentq.json'))
        meta = os.path.join(self.dir.name, 'app', 'a', 'o')
        os.makedirs(meta)
        with open(os.path.join(meta, 'local_me.json'), 'w') as f:
            json.dump({'sessionId': 'local_me', 'cwd': project}, f)
        run = subprocess.run([sys.executable, TOOL, 'take', '5'], capture_output=True, text=True, cwd=scratch,
                             env={**self.env(), 'CLAUDE_CODE_HOST_SESSION_ID': 'local_me'})
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_missing_config_key_is_named(self):
        with open(self.config, 'w') as f:
            json.dump({'owner_accounts': ['boss']}, f)
        run = self.run_tool('queue', ok=False)
        self.assertIn('"agent_account" is missing', run.stderr)


ROLES = [
    {'role': 'programmer', 'label': 'prog', 'session': 'local_p', 'effort': 'high', 'hard_effort': 'max'},
    {'role': 'designer', 'label': 'design', 'session': 'local_d', 'merge': False, 'description': 'banners, icons'},
    {'role': 'checker', 'label': 'check', 'mode': 'checker', 'n': 2, 'hours': 24, 'session': 'local_c',
     'model': 'mid', 'release_model': 'strong', 'since': '2026-01-01T00:00:00Z'},
]
T0, T1, T2 = '2026-01-02T12:00:00Z', '2026-01-02T12:01:00Z', '2026-01-02T12:02:00Z'
ICON = {f'repos/{REPO}/issues/7': {'title': 'Icon', 'body': 'a round icon', 'labels': [{'name': 'design'}],
                                    'user': {'login': 'boss'}}}


def closed(number, title, at, labels=(), reason='COMPLETED'):
    return issue(number, title, labels, closedAt=at, stateReason=reason)


class WriteTest(unittest.TestCase):
    def test_two_processes_writing_the_board_at_once_never_take_each_others_copy(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:  # a Claude and a Codex watcher, side by side
            code = ('import sys; sys.path.insert(0, sys.argv[1]); from agentq_lib.board import save_board\n'
                    'for n in range(300): save_board({"state_file": sys.argv[2]}, {"n": n})')
            writers = [subprocess.Popen([sys.executable, '-c', code, os.path.join(ROOT, 'tools'),
                                         os.path.join(d, 'state.json')], stderr=subprocess.PIPE, text=True)
                       for _ in range(2)]
            for w in writers:
                _, err = w.communicate(timeout=60)
                self.assertEqual(w.returncode, 0, err)
            self.assertEqual(sorted(os.listdir(d)), ['state.json.board.json'])


class AppsTest(unittest.TestCase):
    """The desktop apps' files are theirs: a change in their shape means "cannot be seen", never a crash."""

    def test_unexpected_app_files_are_read_as_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = {'app_sessions': os.path.join(d, 'app'), 'transcripts': os.path.join(d, 'tx'), 'state_file': os.path.join(d, 's.json')}
            meta = os.path.join(d, 'app', 'a', 'b', 'local_s.json')
            os.makedirs(os.path.dirname(meta))
            for shape in ('[1, 2]', '{"cliSessionId": 7}', 'not json', '{"cliSessionId": "c", "lastActivityAt": "soon"}'):
                with open(meta, 'w') as f:
                    f.write(shape)
                self.assertIsNone(apps.session_activity(cfg, 'local_s'), shape)
                self.assertEqual(apps.worker_title(cfg, 'local_s'), 'local_s', shape)
            os.makedirs(os.path.join(d, 'tx', 'p'))
            open(os.path.join(d, 'tx', 'p', 'c.jsonl'), 'w').close()
            self.assertIsNotNone(apps.session_activity(cfg, 'local_s'))  # its transcript is there: seen, bad time or not


class TeamTest(Base):
    def setUp(self):
        super().setUp()
        with open(self.config) as f:
            cfg = json.load(f)
        cfg.update({'roles': ROLES, 'dispatcher': {'folder': os.path.join(self.dir.name, 'disp'), 'session': 'local_x'},
                    'check_minutes': 0})
        with open(self.config, 'w') as f:
            json.dump(cfg, f)

    def board(self, **extra):
        return {REPO: {'open': [
            issue(1, 'Old bug', ['prog']),
            issue(2, 'Urgent bug', ['prog', 'priority']),
            issue(3, 'Banner', ['design', 'doing'], comments=[said('boss', 'old', '2026-01-02T08:00:00Z'),
                                                              said('boss', 'recent', '2026-01-02T11:55:00Z'),
                                                              said('bot', '🤖 designer: on it', '2026-01-02T11:58:00Z')]),
            issue(4, 'Something new', comments=[said('bot', '🤖 programmer: noted', '2026-01-02T11:00:00Z')]),
            issue(5, 'Spam', author='stranger'),
            issue(6, 'Which colour?', ['prog', 'ask owner']),
        ], 'closed': [closed(10, 'Done A', '2026-01-02T09:00:00Z'), closed(11, 'Done B', '2026-01-02T10:00:00Z'),
                      closed(12, 'Dropped', '2026-01-02T10:00:00Z', reason='NOT_PLANNED'),
                      closed(13, 'Seen', '2026-01-02T10:00:00Z', ['checked: checker'])], **extra}}

    def test_watch_plan_assigns_classifies_batches_and_forwards_owner_words(self):
        self.data(self.board())
        first = self.run_tool('watch', '--once', now=T0).stdout
        self.assertIn('without asking anyone. The session ids come from the config and are current', first)
        self.assertIn(f'next task for programmer: run `agentq assign {REPO}#2 programmer`', first)
        self.assertNotIn(f'{REPO}#1 programmer', first)
        self.assertNotIn('designer:', first)
        self.assertIn(f'classify {REPO}#4 "Something new"', first)
        self.assertNotIn('#5', first)
        self.assertIn(f'a batch is ready for checker: run `agentq batch checker -R {REPO}`', first)
        self.assertNotIn('the owner wrote', first)
        fixture = self.board()
        fixture[REPO]['open'][2]['comments'].append(said('boss', 'make it red', '2026-01-02T12:00:30Z'))
        fixture[REPO]['open'][5]['comments'].append(said('boss', 'blue', '2026-01-02T12:00:40Z'))
        fixture[REPO]['open'][3]['comments'].append(said('bot', '🤖 programmer: more', '2026-01-02T12:00:50Z'))
        self.data(fixture)
        second = self.run_tool('watch', '--once', now=T1).stdout
        self.assertIn(f'the owner wrote on {REPO}#3 (designer): send this line to session local_d: `The owner wrote '
                      f'more on {REPO}#3, your task: run agentq brief {REPO}#3 --since 2026-01-02T12:00:30Z and act on it.`', second)
        self.assertIn(f'the owner answered on {REPO}#6: run `agentq assign {REPO}#6 programmer`', second)
        self.assertNotIn(f'assign {REPO}#2', second)
        self.assertIn('no work', self.run_tool('watch', '--once', now=T2).stdout)
        fixture['api'] = {f'repos/{REPO}/issues/3': {'title': 'Banner', 'body': '', 'labels': [{'name': 'design'}],
                                                    'user': {'login': 'boss'}},
                          f'repos/{REPO}/issues/3/comments': [
                              {'user': {'login': 'boss'}, 'body': 'make it red', 'created_at': '2026-01-02T12:00:30Z'}]}
        self.data(fixture)
        self.assertIn('make it red', self.run_tool('brief', '3', '--since', '2026-01-02T12:00:30Z', now=T2).stdout)
        later = self.run_tool('watch', '--once', now='2026-01-02T12:40:00Z').stdout
        self.assertNotIn('the owner wrote', later)  # delivered by the brief
        self.assertIn(f'the owner answered on {REPO}#6', later)  # not delivered yet: it stays in the plan

    def test_the_first_watch_forwards_only_words_no_agent_answered(self):
        self.data({REPO: {'open': [
            issue(3, 'Banner', ['design', 'doing'], comments=[said('boss', 'seen', '2026-01-02T09:00:00Z'),
                                                              said('bot', '🤖 designer: ok', '2026-01-02T09:30:00Z')]),
            issue(6, 'Which colour?', ['prog', 'ask owner'], comments=[said('bot', '🤖 programmer: which?', '2026-01-02T08:00:00Z'),
                                                                        said('boss', 'blue', '2026-01-02T10:00:00Z')])]}})
        first = self.run_tool('watch', '--once').stdout
        self.assertIn(f'the owner answered on {REPO}#6', first)
        self.assertNotIn(f'{REPO}#3', first)

    def session(self, local_id, quiet_since):
        """A desktop-app session whose transcript was last written at quiet_since."""
        meta = os.path.join(self.dir.name, 'app', 'acct', 'org')
        os.makedirs(meta, exist_ok=True)
        with open(os.path.join(meta, f'{local_id}.json'), 'w') as f:
            json.dump({'sessionId': local_id, 'cliSessionId': f'cli-{local_id}'}, f)
        tx = os.path.join(self.dir.name, 'tx', '-proj')
        os.makedirs(tx, exist_ok=True)
        path = os.path.join(tx, f'cli-{local_id}.jsonl')
        open(path, 'a').close()
        moment = datetime.datetime.fromisoformat(quiet_since.replace('Z', '+00:00')).timestamp()
        os.utime(path, (moment, moment))

    def config_change(self, **values):
        with open(self.config) as f:
            cfg = json.load(f)
        cfg.update(values)
        with open(self.config, 'w') as f:
            json.dump(cfg, f)

    def test_a_second_computer_serves_only_its_own_sessions(self):
        self.config_change(primary=False)  # the team already runs on another computer for this project
        self.data(self.board())
        out = self.run_tool('watch', '--once', now=T0).stdout
        self.assertIn(f'next task for programmer: run `agentq assign {REPO}#2 programmer`', out)  # its own session
        self.assertNotIn('classify', out)  # sorting, batches and test runs are the main computer's
        self.assertNotIn('a batch is ready', out)

    def test_a_task_another_computer_took_is_left_to_it(self):
        claim = {'id': 5, 'user': {'login': 'bot'}, 'created_at': '2026-01-02T09:00:00Z',
                 'body': '🤖 programmer: taking this.\n<!-- agentq:claim otherpc/programmer/abc -->'}
        self.data({REPO: {'open': [issue(7, 'Fix', ['prog', 'doing'], updated='2026-01-02T09:00:00Z'),
                                   issue(8, 'Menu', ['prog'])]},
                   'api': {f'repos/{REPO}/issues/7/comments': [claim]}})
        self.session('local_p', '2026-01-02T11:00:00Z')
        out = self.run_tool('watch', '--once', now='2026-01-02T12:15:00Z').stdout
        self.assertNotIn(f'holds {REPO}#7', out)  # never reminded or released here
        self.assertIn(f'next task for programmer: run `agentq assign {REPO}#8 programmer`', out)  # its session is free
        self.assertEqual(self.state()['claim_hosts'], {f'{REPO}#7': 'otherpc'})

    def test_a_second_computer_reports_its_health_in_its_own_issue(self):
        self.config_change(primary=False, disk_min_gb=10 ** 9)
        report = issue(60, 'Agent team health', ['agent health'])  # the main computer's
        self.data({REPO: {'open': [report], 'next': 61}})
        out = self.run_tool('health').stdout
        made = self.calls(['issue', 'create'])[-1]
        self.assertTrue(made[made.index('--title') + 1].startswith('Agent team health ('))
        self.assertIn('GB free on this computer', out)
        self.assertEqual(self.calls(['issue', 'comment']), [])  # nothing written on the main computer's issue

    def test_a_quiet_session_holding_a_task_is_reminded_once_then_the_owner_is_told(self):
        self.data({REPO: {'open': [issue(7, 'Fix', ['prog', 'doing'], updated='2026-01-02T09:00:00Z')], 'next': 70}})
        self.session('local_p', '2026-01-02T11:50:00Z')
        self.assertIn('no work', self.run_tool('watch', '--once', now=T0).stdout)  # quiet 10 min: fine
        out = self.run_tool('watch', '--once', now='2026-01-02T12:15:00Z').stdout
        self.assertIn(f'programmer holds {REPO}#7 but has been quiet since 2026-01-02T11:50:00Z: send this line to '
                      f"session local_p (agentq checked: it exists): `You hold {REPO}#7 ('doing'), but your session has been idle since 2026-01-02T11:50:00Z.", out)
        self.assertIn("You hold acme/app#7 ('doing')", self.run_tool('nudge', '7', '--last', '2026-01-02T11:50:00Z').stdout)
        self.assertIn('no work', self.run_tool('watch', '--once', now='2026-01-02T12:30:00Z').stdout)  # one reminder
        self.assertEqual(self.calls(['issue', 'create']), [])
        self.run_tool('watch', '--once', now='2026-01-02T12:46:00Z')
        made = self.calls(['issue', 'create'])[-1]
        self.assertIn('ask owner', made)
        self.assertIn(f'programmer holds {REPO}#7, but its session (local_p) has been idle since 2026-01-02T11:50:00Z', self.body(made))
        self.assertEqual(self.calls(['issue', 'edit'])[-1], ['issue', 'edit', '7', '-R', REPO, '--remove-label', 'doing'])
        self.assertIn('back in the queue: its session (local_p)', self.body(self.calls(['issue', 'comment'])[-1]))
        self.run_tool('watch', '--once', now='2026-01-02T13:30:00Z')
        self.assertEqual(len(self.calls(['issue', 'create'])), 1)  # told once
        self.session('local_p', '2026-01-02T13:31:00Z')  # it woke up
        self.data({REPO: {'open': [issue(7, 'Fix', ['prog', 'doing'], updated='2026-01-02T09:00:00Z'),
                                   issue(70, 'Agent team health', ['agent health', 'ask owner'])], 'next': 71}})
        self.assertIn('no work', self.run_tool('watch', '--once', now='2026-01-02T13:40:00Z').stdout)
        said = [self.body(c) for c in self.calls(['issue', 'comment'])[-2:]]  # the owner hears it; the issue closes
        self.assertIn(f'{REPO}#7: not stuck any more', said[0])
        self.assertIn('all well again', said[1])

    def test_where_sessions_cannot_be_seen_the_dispatcher_checks_them(self):
        with open(self.config) as f:
            cfg = json.load(f)
        cfg['check_minutes'] = 60
        with open(self.config, 'w') as f:
            json.dump(cfg, f)
        self.data({REPO: {'open': [issue(7, 'Fix', ['prog', 'doing'], updated='2026-01-02T09:00:00Z')], 'next': 70}})
        out = self.run_tool('watch', '--once', now=T0).stdout
        self.assertIn(f'programmer holds {REPO}#7: call get_session for local_p, then run `agentq held {REPO}#7 '
                      f'--running <its isRunning> --last <its lastActivityAt>`', out)
        self.assertIn('nothing to do', self.run_tool('held', '7', '--running', 'true', '--last', '2026-01-02T09:00:00Z').stdout)
        out = self.run_tool('held', '7', '--running', 'false', '--last', '2026-01-02T11:00:00Z').stdout
        self.assertIn(f"send this line to session local_p: `You hold {REPO}#7 ('doing'), but your session has been idle since 2026-01-02T11:00:00Z", out)
        self.assertIn('waiting – nothing to do', self.run_tool('held', '7', '--running', 'false', '--last',
                                                              '2026-01-02T11:00:00Z', now='2026-01-02T12:10:00Z').stdout)
        self.assertIn('told the owner', self.run_tool('held', '7', '--running', 'false', '--last', '2026-01-02T11:00:00Z',
                                                      now='2026-01-02T12:40:00Z').stdout)
        self.assertIn('ask owner', self.calls(['issue', 'create'])[-1])

    def test_a_role_with_several_sessions_takes_one_task_per_session(self):
        self.data({REPO: {'labels': []}})
        self.run_tool('role', 'programmer', '--sessions', 'local_p1,local_p2,local_p3')
        self.data({REPO: {'open': [issue(1, 'A', ['prog', 'doing']), issue(2, 'B', ['prog']), issue(3, 'C', ['prog']),
                                   issue(4, 'D', ['prog'])]}})
        out = self.run_tool('watch', '--once').stdout
        self.assertIn(f'assign {REPO}#2 programmer', out)
        self.assertIn(f'assign {REPO}#3 programmer', out)
        self.assertNotIn(f'assign {REPO}#4', out)
        out = self.run_tool('assign', '2', 'programmer').stdout
        self.assertIn(f'send this line to session local_p2: `Task {REPO}#2 for programmer', out)  # #1 holds p1
        self.data({REPO: {'open': [issue(1, 'A', ['prog', 'doing']), issue(2, 'B', ['prog', 'doing']),
                                   issue(3, 'C', ['prog']), issue(4, 'D', ['prog'])]}})
        self.assertIn('to session local_p3', self.run_tool('assign', '3', 'programmer').stdout)
        self.data({REPO: {'open': [issue(1, 'A', ['prog', 'doing']), issue(2, 'B', ['prog', 'doing']),
                                   issue(3, 'C', ['prog', 'doing']), issue(4, 'D', ['prog'])]}})
        self.assertIn('queued', self.run_tool('assign', '4', 'programmer').stdout)
        self.assertIn('local_p1, local_p2, local_p3', self.run_tool('role', 'programmer').stdout)
        self.session('local_p2', '2026-01-02T11:00:00Z')
        self.session('local_p1', '2026-01-02T11:59:00Z')
        self.session('local_p3', '2026-01-02T11:59:00Z')
        out = self.run_tool('watch', '--once').stdout
        self.assertIn(f'programmer holds {REPO}#2 but has been quiet since 2026-01-02T11:00:00Z: send this line to '
                      f'session local_p2 (agentq checked: it exists): `You hold {REPO}#2', out)

    def test_scale_starts_numbered_sessions_and_keeps_resting_ones(self):
        self.data({REPO: {'labels': []}})
        out = self.run_tool('scale', 'programmer', '3').stdout
        self.assertIn('programmer: 3 sessions work in parallel (1 exist).', out)
        self.assertIn('1. start a session "app programmer 2"', out)
        self.assertIn('2. start a session "app programmer 3"', out)
        self.run_tool('role', 'programmer', '--add-session', 'local_p2', '--add-session', 'local_p3')
        self.assertIn('local_p, local_p2, local_p3', self.run_tool('role', 'programmer').stdout)
        self.assertIn('Sessions 2–3 rest', self.run_tool('scale', 'programmer', '1').stdout)
        table = self.run_tool('role', 'programmer').stdout
        self.assertIn('| local_p (resting: local_p2, local_p3)', table)
        self.data({REPO: {'open': [issue(1, 'A', ['prog', 'doing']), issue(2, 'B', ['prog'])]}})
        self.assertIn('queued', self.run_tool('assign', '2', 'programmer').stdout)
        out = self.run_tool('scale', 'programmer', '2').stdout
        self.assertNotIn('start a session', out)  # reused, nothing new
        self.assertIn('to session local_p2', self.run_tool('assign', '2', 'programmer').stdout)

    def test_an_untouched_pull_request_becomes_a_task_once(self):
        pr = {'number': 1, 'title': 'Accounts', 'updatedAt': '2025-12-20T10:00:00Z', 'url': 'https://x/pull/1', 'isDraft': False}
        fresh = {'number': 2, 'title': 'New', 'updatedAt': '2026-01-02T10:00:00Z', 'url': 'https://x/pull/2', 'isDraft': False}
        self.data({REPO: {'open': [], 'prs': [pr, fresh], 'next': 90}})
        self.run_tool('watch', '--once')
        made = self.calls(['issue', 'create'])
        self.assertEqual(len(made), 1)
        self.assertIn('PR #1 untouched for 3 days: finish it or close it', made[0])
        self.assertEqual(made[0][made[0].index('--label') + 1], 'prog')
        self.run_tool('watch', '--once', now='2026-01-02T14:00:00Z')
        self.assertEqual(len(self.calls(['issue', 'create'])), 1)

    def test_batched_tests_run_by_the_watcher_and_red_wakes_the_checker(self):
        import time
        origin, co = os.path.join(self.dir.name, 'origin'), os.path.join(self.dir.name, 'testco')
        git = ['git', '-c', 'user.name=t', '-c', 'user.email=t@t']
        subprocess.run(['git', 'init', '-q', '-b', 'main', origin], check=True)
        open(os.path.join(origin, 'ok'), 'w').close()
        subprocess.run(git + ['-C', origin, 'add', '.'], check=True)
        subprocess.run(git + ['-C', origin, 'commit', '-qm', 'green'], check=True)
        subprocess.run(['git', 'clone', '-q', origin, co], check=True)
        with open(self.config) as f:
            cfg = json.load(f)
        cfg['tests'] = {'mode': 'per-task', 'full': 'test -f ok', 'every': 2, 'checkout': co}
        with open(self.config, 'w') as f:
            json.dump(cfg, f)
        self.assertIn('tests: batched, full run every 2 tasks: test -f ok', self.run_tool('tests', 'batched').stdout)

        def finished(*numbers, at):
            self.data({REPO: {'open': [], 'closed': [closed(n, f'T{n}', at) for n in numbers]}})

        def wait_for_result(now):
            for _ in range(50):
                out = self.run_tool('watch', '--once', now=now).stdout
                if 'running' not in json.load(open(self.config + '.state.json')).get('tests', {}):
                    return out
                time.sleep(0.2)
            self.fail('the full run did not finish')
        finished(at='2026-01-02T11:00:00Z')
        self.run_tool('watch', '--once', now=T0)  # starts counting
        finished(10, 11, at='2026-01-02T12:01:00Z')
        self.run_tool('watch', '--once', now='2026-01-02T12:06:00Z')  # two tasks done: the full run starts
        wait_for_result('2026-01-02T12:07:00Z')
        self.assertIn('last full run: green', self.run_tool('tests').stdout)
        subprocess.run(git + ['-C', origin, 'rm', '-q', 'ok'], check=True)
        subprocess.run(git + ['-C', origin, 'commit', '-qm', 'break'], check=True)
        finished(12, 13, at='2026-01-02T12:08:00Z')
        self.run_tool('watch', '--once', now='2026-01-02T12:13:00Z')
        out = wait_for_result('2026-01-02T12:14:00Z')
        self.assertIn('the full test run is red at', out)
        self.assertIn('send this line to session local_c', out)
        self.assertIn('(git log ', out)
        self.data({'api': {f'repos/{REPO}/issues/5': {'title': 'Bug', 'body': 'x', 'labels': [{'name': 'prog'}],
                                                       'user': {'login': 'boss'}}}})
        self.assertIn('The full suite runs on its own every 2 tasks.', self.run_tool('brief', '5').stdout)

    def test_a_codex_role_pulls_its_own_tasks(self):
        self.data({REPO: {'labels': []}})
        self.run_tool('role', 'designer', '--agent', 'codex')
        board = {REPO: {'open': [issue(7, 'Icon', ['design']), issue(8, 'Logo', ['design', 'priority'])]},
                 'api': {f'repos/{REPO}/issues/8': {'title': 'Logo', 'body': 'make it round', 'labels': [{'name': 'design'}],
                                                     'user': {'login': 'boss'}}}}
        self.data(board)
        self.assertNotIn('designer', self.run_tool('watch', '--once').stdout)  # nobody sends it anything
        out = self.run_tool('next', 'designer', '--as', 'codex-1').stdout
        self.assertIn(f'{REPO}#8 is yours now (codex-1).', out)
        self.assertIn('make it round', out)
        self.assertEqual(self.calls(['issue', 'edit'])[-1], ['issue', 'edit', '8', '-R', REPO, '--add-label', 'doing',
                                                             '--add-label', 'codex'])
        board[REPO]['open'][1]['labels'].append({'name': 'doing'})
        self.data(board)
        self.assertIn(f'you hold {REPO}#8 – finish it first', self.run_tool('next', 'designer', '--as', 'codex-1').stdout)
        out = self.run_tool('assign', '7', 'designer').stdout
        self.assertIn('it takes its tasks itself (agentq next). Nothing to send.', out)
        self.data({REPO: {'open': []}})
        self.assertIn('nothing yet', self.run_tool('next', 'designer', '--wait', '--max-minutes', '0').stdout)
        self.run_tool('role', 'designer', '--agent', 'claude')
        self.assertIn('Stop this loop.', self.run_tool('next', 'designer', ok=False).stdout)

    def test_a_task_another_computer_claimed_first_is_left_to_it(self):
        self.data({REPO: {'labels': []}})
        self.run_tool('role', 'designer', '--agent', 'codex')
        other = {'id': 5, 'user': {'login': 'bot'}, 'body': '🤖 designer: taking this.\n<!-- agentq:claim pc2/designer/abc -->',
                 'created_at': '2026-01-02T11:59:58Z'}
        self.data({REPO: {'open': [issue(7, 'Icon', ['design']), issue(8, 'Logo', ['design', 'priority'])]},
                   'api': {f'repos/{REPO}/issues/8/comments': [other],
                           f'repos/{REPO}/issues/7': {'title': 'Icon', 'body': 'x', 'labels': [{'name': 'design'}],
                                                       'user': {'login': 'boss'}}}})
        out = self.run_tool('next', 'designer').stdout
        self.assertIn(f'{REPO}#7 is yours now', out)  # #8 went to pc2
        deleted = [c for c in self.calls() if c[:3] == ['api', '-X', 'DELETE']]
        self.assertEqual(deleted, [['api', '-X', 'DELETE', f'repos/{REPO}/issues/comments/1001']])
        self.assertNotIn(['issue', 'edit', '8', '-R', REPO, '--add-label', 'doing'], self.calls(['issue', 'edit']))
        back = {'id': 6, 'user': {'login': 'bot'}, 'body': '🤖 designer: → designer. not mine\n<!-- agentq:route -->',
                'created_at': '2026-01-02T11:59:59Z'}  # pc2 handed #8 back: its claim is over
        self.data({REPO: {'open': [issue(8, 'Logo', ['design', 'priority'])]},
                   'api': {f'repos/{REPO}/issues/8/comments': [other, back],
                           f'repos/{REPO}/issues/8': {'title': 'Logo', 'body': 'x', 'labels': [{'name': 'design'}],
                                                       'user': {'login': 'boss'}}}})
        self.assertIn(f'{REPO}#8 is yours now', self.run_tool('next', 'designer').stdout)

    def test_one_worker_pulls_for_every_pulling_role(self):
        self.data({REPO: {'labels': []}})
        self.run_tool('role', 'designer', '--agent', 'codex')
        self.run_tool('role', 'programmer', '--agent', 'codex')
        self.data({REPO: {'open': [issue(7, 'Icon', ['design']), issue(9, 'Crash', ['prog', 'priority'])],
                          'labels': []},
                   'api': {f'repos/{REPO}/issues/9': {'title': 'Crash', 'body': 'x', 'labels': [{'name': 'prog'}],
                                                       'user': {'login': 'boss'}}}})
        self.assertIn(f'{REPO}#9 is yours now (w1).', self.run_tool('next', '--as', 'w1').stdout)

    def test_codex_workers_prints_what_to_paste_for_the_missing_ones(self):
        self.data({REPO: {'open': []}})
        self.run_tool('team', 'both')
        out = self.run_tool('codex-workers').stdout
        self.assertIn('the create_thread tool', out)
        self.assertIn('--- Codex programmer (model: the app default, reasoning effort: high) ---', out)
        self.assertIn('next programmer --as codex-programmer', out)
        self.assertIn('end your turn', out)
        for role, thread in (('programmer', 't1'), ('designer', 't2'), ('checker', 't3')):
            self.as_codex('next', role, '--as', f'codex-{role}', thread=thread)
            self.rollout(thread, T0)
        self.assertIn('none missing', self.run_tool('codex-workers').stdout)
        os.remove(os.path.join(self.dir.name, 'codexhome', 'sessions', '2026', '01', '02',
                               'rollout-2026-01-02T08-00-00-t2.jsonl'))  # the owner archived codex-designer
        out = self.run_tool('codex-workers').stdout
        self.assertIn('--- Codex designer (model: the app default, reasoning effort: xhigh) ---', out)
        self.run_tool('role', 'programmer', '--codex-model', 'model-b')
        more = self.run_tool('codex-workers', '3', '--role', 'programmer').stdout  # "3 Codex programmers"
        self.assertIn('--- Codex programmer 2 (model: model-b, reasoning effort: high) ---', more)
        self.assertIn('--- Codex programmer 2', more)
        self.assertIn('--as codex-programmer-3', more)
        self.assertNotIn('designer', more)
        self.assertNotIn('--- Codex programmer', out)

    def test_claude_sessions_and_codex_workers_compete_for_a_role(self):
        self.data({REPO: {'open': []}})
        self.run_tool('team', 'both')
        board = {REPO: {'open': [issue(7, 'Icon', ['prog']), issue(8, 'Logo', ['prog'])]},
                 'api': {f'repos/{REPO}/issues/{n}': {'title': 't', 'body': 'x', 'labels': [{'name': 'prog'}],
                                                       'user': {'login': 'boss'}} for n in (7, 8)}}
        self.data(board)
        self.assertIn(f'{REPO}#7 is yours now (codex-programmer).', self.run_tool('next', 'programmer', '--as', 'codex-programmer').stdout)
        board[REPO]['open'][0]['labels'].append({'name': 'doing'})
        self.data(board)
        out = self.run_tool('watch', '--once').stdout  # the Codex worker's task does not make the Claude session busy
        self.assertIn(f'next task for programmer: run `agentq assign {REPO}#8 programmer`', out)
        self.assertIn('send this line to session local_p', self.run_tool('assign', '8', 'programmer').stdout)

    def test_a_claude_session_pulls_and_the_dispatcher_leaves_it_alone(self):
        board = {REPO: {'open': [issue(7, 'Icon', ['prog']), issue(8, 'Logo', ['prog'])]},
                 'api': {f'repos/{REPO}/issues/{n}': {'title': 't', 'body': 'x', 'labels': [{'name': 'prog'}],
                                                       'user': {'login': 'boss'}} for n in (7, 8)}}
        self.data(board)
        claude = {**self.env(), 'CLAUDECODE': '1', 'CLAUDE_CODE_HOST_SESSION_ID': 'local_p'}
        run = subprocess.run([sys.executable, TOOL, '--config', self.config, 'next', 'programmer'], capture_output=True,
                             text=True, env=claude)
        self.assertIn(f'{REPO}#7 is yours now (local_p).', run.stdout)
        self.assertIn('🤖 programmer · claude (local_p): taking this.', self.body(self.calls(['issue', 'comment'])[-1]))
        self.assertIn('--add-label', self.calls(['issue', 'edit'])[-1])
        self.assertIn('claude', self.calls(['issue', 'edit'])[-1])
        os.makedirs(self.config + '.state.json.waiting', exist_ok=True)  # local_p waits for its next task
        with open(self.config + '.state.json.waiting/local_p', 'w') as f:
            json.dump({'worker': 'local_p', 'roles': ['programmer']}, f)
        board[REPO]['open'] = [issue(8, 'Logo', ['prog'])]
        self.data(board)
        self.assertNotIn('assign', self.run_tool('watch', '--once').stdout)  # no dispatcher wake for it
        out = self.run_tool('assign', '8', 'programmer').stdout  # e.g. the owner answered: no message on top of its pull
        self.assertIn('queued: a free session waiting in `agentq next` takes it itself', out)
        edits = [c for c in self.calls(['issue', 'edit']) if c[2] == '8']
        self.assertNotIn('doing', [x for c in edits for x in c[c.index('--add-label'):] if '--add-label' in c])
        self.assertFalse(any('agentq:claim' in self.body(c) for c in self.calls(['issue', 'comment']) if c[2] == '8'))

    def rollout(self, thread, at):
        """The Codex task's rollout file, last written at this time."""
        path = os.path.join(self.dir.name, 'codexhome', 'sessions', '2026', '01', '02', f'rollout-2026-01-02T08-00-00-{thread}.jsonl')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, 'a').close()
        moment = datetime.datetime.fromisoformat(at.replace('Z', '+00:00')).timestamp()
        os.utime(path, (moment, moment))

    def test_a_codex_worker_without_a_task_ends_its_turn_and_the_watcher_wakes_it(self):
        self.data({REPO: {'labels': []}})
        self.run_tool('role', 'designer', '--agent', 'codex')
        self.data({REPO: {'open': []}})
        self.assertIn('End your turn here', self.as_codex('next', 'designer', '--wait', '--as', 'cx').stdout)  # never waits
        self.assertEqual(self.state()['codex']['cx']['thread'], 't1')
        self.as_codex('next', 'designer', '--as', 'cy')  # the same Codex task under a new name: still one worker
        self.assertEqual(list(self.state()['codex']), ['cy'])
        self.as_codex('next', 'designer', '--as', 'cx')
        board = {REPO: {'open': [issue(7, 'Icon', ['design'])]}}
        self.data(board)
        self.run_tool('watch', '--once', env={'CODEX_HOME': os.path.join(self.dir.name, 'none')})
        self.assertEqual(self.faked('codex'), '')  # its Codex task was archived or deleted: nothing sent
        self.rollout('t1', T0)
        with open(os.path.join(self.dir.name, 'codexhome', 'session_index.jsonl'), 'w') as f:  # its title in the app
            f.write(json.dumps({'id': 't1', 'thread_name': 'Codex designer 1'}) + '\n')
        self.assertNotIn('designer', self.run_tool('watch', '--once').stdout)  # no dispatcher wake: the watcher sent it
        self.assertIn(f'queue --thread t1 --message Task {REPO}#7 for designer is yours now (worker cx)', self.faked('codex'))
        self.assertIn('next designer --as cx', self.faked('codex'))
        self.assertIn('-g codex://threads/t1', self.faked('open'))  # the app had not loaded it: opened in the background
        self.assertIn('🤖 designer · codex (Codex designer 1): taking this.', self.body(self.calls(['issue', 'comment'])[-1]))
        self.assertEqual(self.calls(['issue', 'edit'])[-1], ['issue', 'edit', '7', '-R', REPO, '--add-label', 'doing',
                                                             '--add-label', 'codex'])
        self.assertEqual(self.state()['holders'], {f'{REPO}#7': 'cx'})
        board[REPO]['open'][0]['labels'].append({'name': 'doing'})
        self.data(board)
        self.run_tool('watch', '--once', now=T1)
        self.assertEqual(self.faked('codex').count('queue'), 1)  # it works on it: woken once

    def test_a_wake_that_fails_is_undone(self):
        self.data({REPO: {'labels': []}})
        self.run_tool('role', 'designer', '--agent', 'codex')
        self.data({REPO: {'open': []}})
        self.as_codex('next', 'designer', '--as', 'cx')
        self.rollout('t1', T0)
        fake_script(os.path.join(self.dir.name, 'bin', 'fake_codex.py'), fail='no such thread')
        self.data({REPO: {'open': [issue(7, 'Icon', ['design'])]}})
        self.run_tool('watch', '--once')
        self.assertIn('could not be reached (no such thread)', self.body(self.calls(['issue', 'comment'])[-1]))
        self.assertEqual(self.calls(['issue', 'edit'])[-1], ['issue', 'edit', '7', '-R', REPO, '--remove-label', 'doing'])
        state = self.state()
        self.assertEqual(state.get('holders', {}), {})
        self.assertTrue(state['codex']['cx']['idle'])  # woken again at the next poll

    def test_a_queued_wake_stays_even_when_opening_the_task_fails(self):
        self.data({REPO: {'labels': []}})
        self.run_tool('role', 'designer', '--agent', 'codex')
        self.data({REPO: {'open': []}})
        self.as_codex('next', 'designer', '--as', 'cx')
        self.rollout('t1', T0)
        fake_script(os.path.join(self.dir.name, 'bin', 'fake_open.py'), fail='')
        self.data({REPO: {'open': [issue(7, 'Icon', ['design'])]}})
        self.run_tool('watch', '--once')
        state = self.state()
        self.assertEqual(state['holders'], {f'{REPO}#7': 'cx'})  # the message is queued: never a second taker
        self.assertIn('opening the task failed', state['codex']['cx']['error'])

    def test_with_codex_closed_its_workers_get_nothing(self):
        self.data({REPO: {'labels': []}})
        self.run_tool('role', 'designer', '--agent', 'codex')
        self.data({REPO: {'open': []}})
        self.as_codex('next', 'designer', '--as', 'cx')
        self.data({REPO: {'open': [issue(7, 'Icon', ['design'])]}})
        self.run_tool('watch', '--once', env={'AGENTQ_CODEX_APP': '0'})
        self.assertEqual(self.faked('codex'), '')
        self.assertEqual(self.calls(['issue', 'comment']), [])  # left for another worker

    def test_a_codex_worker_that_finished_without_asking_for_more_is_still_woken(self):
        self.data({REPO: {'labels': []}})
        self.run_tool('role', 'designer', '--agent', 'codex')
        self.data({REPO: {'open': [issue(7, 'Icon', ['design'])]}, 'api': ICON})
        self.assertIn(f'{REPO}#7 is yours now (cx)', self.as_codex('next', 'designer', '--as', 'cx').stdout)
        self.data({REPO: {'open': [issue(7, 'Icon', ['design', 'doing'])]}})
        self.as_codex('done', '7', 'drew it', now='2026-01-02T11:50:00Z')
        self.assertTrue(self.state()['codex']['cx']['finished'])
        self.rollout('t1', '2026-01-02T11:51:00Z')  # its turn ended there, without `agentq next`
        self.data({REPO: {'open': [issue(8, 'Logo', ['design'])]}})
        self.run_tool('watch', '--once')
        self.assertIn(f'Task {REPO}#8 for designer is yours now (worker cx)', self.faked('codex'))

    def test_a_quiet_codex_worker_is_reminded_by_a_message_then_its_task_goes_back(self):
        self.data({REPO: {'labels': []}})
        self.run_tool('role', 'designer', '--agent', 'codex')
        self.data({REPO: {'open': [issue(7, 'Icon', ['design'])]}, 'api': ICON})
        self.as_codex('next', 'designer', '--as', 'cx')
        self.rollout('t1', '2026-01-02T11:50:00Z')
        self.data({REPO: {'open': [issue(7, 'Icon', ['design', 'doing'])], 'next': 70}})
        self.assertIn('no work', self.run_tool('watch', '--once', now='2026-01-02T12:15:00Z').stdout)  # no dispatcher
        self.assertIn(f"queue --thread t1 --message You hold {REPO}#7 ('doing')", self.faked('codex'))
        self.run_tool('watch', '--once', now='2026-01-02T12:46:00Z')
        self.assertIn('ask owner', self.calls(['issue', 'create'])[-1])  # the owner is told
        self.assertNotIn(['issue', 'edit', '7', '-R', REPO, '--remove-label', 'doing'], self.calls(['issue', 'edit']))

    def test_claude_and_codex_take_turns_when_both_wait(self):
        self.data({REPO: {'open': []}})
        self.run_tool('team', 'both')
        self.as_codex('next', 'programmer', '--as', 'cx')
        self.rollout('t1', T0)
        os.makedirs(self.config + '.state.json.waiting', exist_ok=True)  # the Claude session local_p waits too
        with open(self.config + '.state.json.waiting/local_p', 'w') as f:
            json.dump({'worker': 'local_p', 'roles': ['programmer']}, f)
        self.state(lambda s: s.__setitem__('last_team', {'programmer': 'codex'}))
        self.data({REPO: {'open': [issue(7, 'Icon', ['prog'])]}})
        self.assertNotIn('assign', self.run_tool('watch', '--once').stdout)  # Claude's turn: local_p takes it itself
        self.assertEqual(self.faked('codex'), '')
        self.state(lambda s: s.__setitem__('last_team', {'programmer': 'claude'}))
        self.run_tool('watch', '--once', now=T1)
        self.assertIn(f'Task {REPO}#7 for programmer is yours now (worker cx)', self.faked('codex'))

    def test_a_resting_claude_session_takes_nothing_and_claude_leaves_codex_its_turn(self):
        self.data({REPO: {'open': [], 'labels': []}})
        self.run_tool('team', 'both')
        self.run_tool('role', 'programmer', '--sessions', 'local_p,local_q')
        self.run_tool('scale', 'programmer', '1')  # the owner: one Claude programmer
        self.data({REPO: {'open': []}})
        self.as_codex('next', 'programmer', '--as', 'cx')  # an idle Codex programmer
        self.rollout('t1', T0)
        self.data({REPO: {'open': [issue(7, 'Icon', ['prog'])]},
                   'api': {f'repos/{REPO}/issues/7': {'title': 'Icon', 'body': 'x', 'labels': [{'name': 'prog'}],
                                                       'user': {'login': 'boss'}}}})
        out = self.run_tool('next', 'programmer', '--as', 'local_q', ok=False).stdout
        self.assertIn('local_q rests now', out)
        self.assertEqual(self.calls(['issue', 'comment']), [])
        self.state(lambda s: s.__setitem__('last_team', {'programmer': 'claude'}))
        self.assertIn('nothing yet', self.run_tool('next', 'programmer', '--as', 'local_p').stdout)  # Codex's turn
        self.state(lambda s: s.__setitem__('last_team', {'programmer': 'codex'}))
        self.assertIn(f'{REPO}#7 is yours now (local_p)', self.run_tool('next', 'programmer', '--as', 'local_p').stdout)
        self.assertIn('no Claude session works', self.run_tool('scale', 'programmer', '0').stdout)  # Codex only
        self.data({REPO: {'open': [issue(8, 'Menu', ['prog'])]}})
        self.assertIn('local_p rests now', self.run_tool('next', 'programmer', '--as', 'local_p', ok=False).stdout)
        claude = {'CLAUDECODE': '1', 'CLAUDE_CODE_HOST_SESSION_ID': 'local_z'}  # under a name, not its session id
        self.assertIn('rests now', self.run_tool('next', 'programmer', '--as', 'Programmer 4', ok=False, env=claude).stdout)
        self.assertNotIn('send this line', self.run_tool('watch', '--once', now=T1).stdout)
        self.assertIn(f'Task {REPO}#8 for programmer is yours now (worker cx)', self.faked('codex'))

    def test_claude_off_reaches_a_claude_session_already_waiting_for_a_task(self):
        self.data({REPO: {'open': [], 'labels': []}})
        with open(self.config) as f:
            cfg = json.load(f)
        with open(self.config, 'w') as f:
            json.dump({**cfg, 'poll_seconds': 0.2}, f)
        self.run_tool('team', 'both')
        self.run_tool('role', 'programmer', '--sessions', 'local_p')
        claude = {**self.env(), 'CLAUDECODE': '1', 'CLAUDE_CODE_HOST_SESSION_ID': 'local_p', 'AGENTQ_PARENT': str(os.getpid())}
        waiting = subprocess.Popen([sys.executable, TOOL, '--config', self.config, 'next', 'programmer', '--wait'],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=claude)
        try:
            time.sleep(1.5)
            self.assertIsNone(waiting.poll())  # no task: it waits
            self.run_tool('team', 'codex')  # the owner: "Claude off" – it read the config before
            out, _ = waiting.communicate(timeout=20)
        finally:
            system.kill_tree(waiting.pid) if waiting.poll() is None else None
        self.assertEqual(waiting.returncode, 1, out)
        self.assertIn('local_p rests now: Codex works programmer alone (agentq team codex)', out)
        self.assertIn('rests now', self.run_tool('next', 'programmer', ok=False, env={'CLAUDECODE': '1',
                                                 'CLAUDE_CODE_HOST_SESSION_ID': 'local_p'}).stdout)

    def test_a_task_kept_for_claude_goes_to_no_codex_worker_and_to_the_named_session(self):
        self.data({REPO: {'open': [], 'labels': []}})
        self.run_tool('team', 'both')
        self.run_tool('role', 'programmer', '--sessions', 'local_p,local_q')
        self.run_tool('scale', 'programmer', '0')  # Codex programmers only
        self.as_codex('next', 'programmer', '--as', 'cx')
        self.rollout('t1', T0)
        kept = issue(7, 'Agree button', ['prog', 'only claude'])
        api = {f'repos/{REPO}/issues/7': {'title': 'Agree button', 'body': 'x', 'user': {'login': 'boss'},
                                           'labels': [{'name': 'prog'}, {'name': 'only claude'}]}}
        self.data({REPO: {'open': [kept]}, 'api': api})
        self.assertIn('No task now', self.as_codex('next', 'programmer', '--as', 'cx').stdout)
        self.run_tool('watch', '--once', now=T1)
        self.assertEqual(self.faked('codex'), '')  # nobody woken for it
        out = self.run_tool('assign', '7', 'programmer', '--only', 'claude', '--session', 'local_q').stdout
        self.assertIn(f'{REPO}#7 → programmer, working, for session local_q', out)
        self.assertIn('send this line to session local_q', out)
        self.assertEqual(self.state()['holders'][f'{REPO}#7'], 'local_q')
        self.assertIn('doing', self.calls(['issue', 'edit'])[-1])

    def test_three_failed_tries_hand_the_task_to_the_other_team(self):
        self.data({REPO: {'open': [], 'labels': []}})
        self.run_tool('team', 'both')
        self.run_tool('role', 'programmer', '--sessions', 'local_p,local_q')
        self.run_tool('scale', 'programmer', '0')  # Codex programmers only
        self.state(lambda s: s.setdefault('holders', {}).__setitem__(f'{REPO}#7', 'cx'))
        api = {f'repos/{REPO}/issues/7': {'title': 'Flaky e2e', 'body': 'x', 'user': {'login': 'boss'},
                                           'labels': [{'name': 'prog'}, {'name': 'doing'}, {'name': 'codex'}]}}
        self.data({REPO: {'open': [issue(7, 'Flaky e2e', ['prog', 'doing', 'codex'])]}, 'api': api})
        self.assertIn('Three tries and it still fails', self.run_tool('brief', '7').stdout)
        out = self.as_codex('handover', '7', 'v1–v3 still red under load; logs in task-7/').stdout
        self.assertIn(f'{REPO}#7 → the claude team (programmer)', out)
        said_ = self.body(self.calls(['issue', 'comment'])[-1])
        self.assertIn('not done in 3 tries – over to the claude team. v1–v3 still red under load', said_)
        self.assertIn('<!-- agentq:route -->', said_)  # the Codex claim is over
        self.assertEqual(self.calls(['issue', 'edit'])[-1], ['issue', 'edit', '7', '-R', REPO, '--add-label',
                                                             'only claude', '--remove-label', 'doing'])
        self.assertNotIn(f'{REPO}#7', self.state().get('holders', {}))
        self.data({REPO: {'open': [issue(7, 'Flaky e2e', ['prog', 'codex', 'only claude'])]}, 'api': api})
        out = self.run_tool('watch', '--once', now=T1).stdout  # no Claude programmer works, so a resting one gets it
        self.assertIn(f'{REPO}#7 is kept for Claude and no Claude session works as programmer now: run '
                      f'`agentq assign {REPO}#7 programmer --session local_p`', out)

    def test_a_codex_dispatcher_gets_its_plans_as_messages(self):
        self.data({REPO: {'open': [issue(4, 'Something new')]}})
        self.run_tool('team', 'both')
        self.assertIn('runs on its own now', self.as_codex('watch', '--max-minutes', '0.05', thread='d1').stdout)
        self.assertEqual(self.state()['dispatcher_thread'], 'd1')
        for _ in range(100):  # the watcher it started sends the plan, then sleeps until its next poll
            if 'Last: end your turn' in self.faked('codex') and self.state().get('watch', {}).get('pid'):
                break
            time.sleep(0.1)
        system.kill_tree(self.state()['watch']['pid'])
        self.assertEqual(self.faked('codex').count('queue --thread d1 --message agentq plan'), 1)
        self.assertIn(f'classify {REPO}#4', self.faked('codex'))
        self.assertIn('Last: end your turn – the watcher keeps running', self.faked('codex'))
        self.assertNotIn('plan sent', self.run_tool('watch', '--wake', '--once', now=T1).stdout)  # sent once

    def test_two_lives_the_codex_dispatcher_only_sorts_and_never_takes_for_claude(self):
        self.data({REPO: {'open': [issue(1, 'Old bug', ['prog']), issue(4, 'Something new')]}})
        self.run_tool('team', 'both')
        codex = self.run_tool('watch', '--once', env={'CODEX_THREAD_ID': 'd1'}).stdout
        self.assertIn(f'classify {REPO}#4', codex)
        self.assertNotIn('next task for programmer', codex)  # Claude sessions are the Claude dispatcher's
        self.data({REPO: {'open': [issue(4, 'Something new')]}})
        out = self.run_tool('assign', '4', 'programmer', env={'CODEX_THREAD_ID': 'd1'}).stdout
        self.assertIn('in its queue', out)  # a worker of either life takes it
        self.data({REPO: {'open': [issue(4, 'Something new', ['prog', 'doing'])]}})
        self.assertIn('already being worked on', self.run_tool('assign', '4', 'programmer').stdout)

    def test_the_owners_words_on_a_set_aside_task_bring_it_back(self):
        self.data({REPO: {'open': []}})
        self.run_tool('watch', '--once', now='2026-01-02T11:00:00Z')
        self.data({REPO: {'open': [issue(20, 'Telegram idea', ['prog', 'later'],
                                         comments=[said('boss', 'we do not defer this', '2026-01-02T11:59:00Z')])]}})
        out = self.run_tool('watch', '--once').stdout
        self.assertIn(f'the owner wrote on {REPO}#20, which was set aside: run `agentq assign {REPO}#20 programmer --unpark`', out)
        self.run_tool('assign', '20', 'programmer', '--unpark')
        edit = [c for c in self.calls(['issue', 'edit']) if c[2] == '20'][-1]
        self.assertIn('later', edit[edit.index('--remove-label') + 1:])

    def test_taking_a_task_again_clears_the_question_and_records_who_holds_it(self):
        self.data({REPO: {'labels': []}})
        self.run_tool('role', 'designer', '--agent', 'codex')
        self.data({REPO: {'open': []}})
        self.as_codex('next', 'designer', '--as', 'cx')
        self.data({REPO: {'open': [issue(7, 'Icon', ['design', 'ask owner'])]}})
        self.as_codex('take', '7')  # the owner answered in the Codex chat
        self.assertEqual(self.calls(['issue', 'edit'])[-1], ['issue', 'edit', '7', '-R', REPO, '--add-label', 'doing',
                                                             '--remove-label', 'ask owner'])
        self.assertEqual(self.state()['holders'], {f'{REPO}#7': 'cx'})

    def test_saving_the_state_keeps_what_others_changed_meanwhile(self):
        tool = state
        base = {'holders': {'a#1': 'w1', 'a#2': 'w2'}, 'watch': {'beat': 1}}
        ours = {'holders': {'a#1': 'w1', 'a#5': 'w5'}, 'watch': {'beat': 2}}  # took #5, let go of #2
        disk = {'holders': {'a#1': 'w1', 'a#2': 'w2', 'a#9': 'w9'}, 'watch': {'beat': 1}, 'paused': {'why': 'stop'}}
        self.assertEqual(tool.merged(base, ours, disk), {'holders': {'a#1': 'w1', 'a#5': 'w5', 'a#9': 'w9'},
                                                         'watch': {'beat': 2}, 'paused': {'why': 'stop'}})

    def test_one_role_restarts_the_owners_running_copy(self):
        self.data({REPO: {'open': [], 'labels': []}})
        self.assertIn('none – nothing is restarted', self.run_tool('live').stdout)
        self.assertIn('checker restarts it after GO', self.run_tool('live', 'checker', '~/bin/restart.sh {sha}').stdout)
        api = {f'repos/{REPO}/issues/{n}': {'title': 't', 'body': b, 'labels': [{'name': l}], 'user': {'login': 'boss'}}
               for n, b, l in ((7, 'x', 'prog'), (9, 'Check: #7\n<!-- agentq:batch {"role": "checker", "issues": [7]} -->', 'check'))}
        self.data({REPO: {'open': []}, 'api': api})
        self.assertIn('restart it on the commit you checked with `~/bin/restart.sh {sha}`', self.run_tool('brief', '9').stdout)
        self.assertIn("Never restart the owner's running copy of the program: checker does", self.run_tool('brief', '7').stdout)
        self.assertIn('after every check, red tests or not', self.run_tool('live', 'checker', '~/bin/restart.sh {sha}',
                                                                          '--when', 'checked').stdout)
        self.assertIn('after every check you finish, restart it on the commit you checked with `~/bin/restart.sh {sha}`',
                      self.run_tool('brief', '9').stdout)
        self.run_tool('live', '--off')
        self.assertNotIn('running copy', self.run_tool('brief', '7').stdout)

    def test_stats_compare_the_teams(self):
        claim = '\n<!-- agentq:claim h/x/1 -->'
        def done(n, team, taken, closed):
            return {'number': n, 'labels': [{'name': team}], 'closedAt': closed, 'stateReason': 'COMPLETED',
                    'comments': [{'body': 'taking this.' + claim, 'createdAt': taken, 'author': {'login': 'bot'}}]}
        self.data({REPO: {'closed': [done(1, 'claude', '2026-01-02T08:00:00Z', '2026-01-02T10:00:00Z'),
                                     done(2, 'codex', '2026-01-02T08:00:00Z', '2026-01-02T09:00:00Z'),
                                     {'number': 3, 'labels': [], 'closedAt': '2026-01-02T09:00:00Z', 'body': 'From the check of #1: wrong'}]}})
        out = self.run_tool('stats').stdout
        self.assertIn('claude | 1 | 2.0 | 1', out)
        self.assertIn('codex | 1 | 1.0 | 0', out)

    def test_done_shows_the_owners_new_words_before_closing(self):
        self.data({REPO: {'open': [issue(7, 'Bug', ['prog', 'doing'])]},
                   'api': {f'repos/{REPO}/issues/7/comments': [
                       {'user': {'login': 'bot'}, 'body': '🤖 dispatcher: → programmer.', 'created_at': '2026-01-02T10:00:00Z'},
                       {'user': {'login': 'boss'}, 'body': 'also the footer', 'created_at': '2026-01-02T11:00:00Z'}]}})
        run = self.run_tool('done', '7', 'fixed', ok=False)
        self.assertEqual(run.returncode, 1)
        self.assertIn('also the footer', run.stdout)
        self.assertEqual(self.calls(['issue', 'close']), [])
        self.run_tool('done', '7', 'fixed, footer too')  # the words are delivered now
        self.assertEqual(self.calls(['issue', 'close'])[-1], ['issue', 'close', '7', '-R', REPO])

    def test_an_urgent_word_from_the_owner_makes_the_task_first(self):
        with open(self.config) as f:
            cfg = json.load(f)
        cfg['priority_words'] = ['SKUBU', 'priority']
        with open(self.config, 'w') as f:
            json.dump(cfg, f)
        self.data({REPO: {'open': [issue(1, 'Old bug', ['prog']),
                                   issue(5, 'Checkout broken', ['prog'], body='skubu! people cannot pay'),
                                   issue(6, 'Footer', ['prog'], comments=[said('boss', 'Priority, please', '2026-01-02T11:00:00Z')]),
                                   issue(7, 'Spam priority', ['prog'], author='stranger')]}})
        out = self.run_tool('watch', '--once').stdout
        self.assertIn(f'next task for programmer: run `agentq assign {REPO}#5 programmer`', out)
        added = [c for c in self.calls(['issue', 'edit']) if '--add-label' in c and 'priority' in c]
        self.assertEqual(sorted(c[2] for c in added), ['5', '6'])
        self.run_tool('watch', '--once', now=T2)
        self.assertEqual(len([c for c in self.calls(['issue', 'edit']) if 'priority' in c]), 2)  # once per issue

    def test_team_moves_the_work_between_claude_and_codex(self):
        self.data({REPO: {'open': [issue(7, 'Icon', ['design'])]}})
        self.assertIn('Codex works every role now', self.run_tool('team', 'codex').stdout)
        with open(self.config) as f:
            cfg = json.load(f)
        self.assertEqual({r['agent'] for r in cfg['roles']}, {'codex'})
        self.assertEqual(cfg['dispatcher']['agent'], 'both')
        claude = subprocess.run([sys.executable, TOOL, '--config', self.config, 'watch', '--once'], capture_output=True,
                                text=True, env={**self.env(), 'CLAUDECODE': '1'})
        self.assertNotIn('assign', claude.stdout)  # Claude sessions get no tasks; the dispatcher still runs
        self.assertIn('Claude works every role now', self.run_tool('team', 'claude').stdout)
        self.assertIn('Stop this loop.', self.run_tool('next', 'designer', ok=False).stdout)

    def test_claude_and_codex_dispatchers_side_by_side(self):
        self.data({REPO: {'open': []}})
        self.assertIn('both work every role', self.run_tool('team', 'both').stdout)
        with open(self.config + '.state.json.watch.claude.lock', 'a') as lock:  # a Claude watcher runs
            system.lock_file(lock)
            codex = subprocess.run([sys.executable, TOOL, '--config', self.config, 'watch', '--once'], capture_output=True,
                                   text=True, env={**self.env(), 'CODEX_THREAD_ID': 't1'})
            self.assertIn('no work', codex.stdout)
            claude = subprocess.run([sys.executable, TOOL, '--config', self.config, 'watch', '--once'], capture_output=True,
                                    text=True, env={**self.env(), 'CLAUDECODE': '1'})
            self.assertIn('already running', claude.stdout)

    def test_words_on_a_task_another_computer_holds_are_left_to_it(self):
        self.data({REPO: {'open': []}})
        self.run_tool('watch', '--once', now=T0)
        held = [said('bot', '🤖 designer: → designer.\n<!-- agentq:claim pc2/dispatcher/x1 -->', '2026-01-02T11:00:00Z'),
                said('boss', 'make it red', '2026-01-02T12:00:30Z')]
        self.data({REPO: {'open': [issue(3, 'Banner', ['design', 'doing'], comments=held)]}})
        self.assertNotIn('the owner wrote', self.run_tool('watch', '--once', now=T1).stdout)

    def test_a_stale_pr_task_already_on_the_board_is_not_opened_twice(self):
        pr = {'number': 1, 'title': 'Accounts', 'updatedAt': '2025-12-20T10:00:00Z', 'url': 'https://x/pull/1', 'isDraft': False}
        self.data({REPO: {'open': [issue(40, 'PR #1 untouched for 3 days: finish it or close it', ['prog', 'doing'])],
                          'prs': [pr]}})
        self.run_tool('watch', '--once')
        self.assertEqual(self.calls(['issue', 'create']), [])

    def test_an_answer_written_while_no_watcher_ran_is_not_lost(self):
        self.data({REPO: {'open': [issue(9, 'Busy', ['prog', 'doing'])]}})
        self.run_tool('watch', '--once', now='2026-01-02T08:00:00Z')
        self.data({REPO: {'open': [issue(9, 'Busy', ['prog', 'doing']),
                                   issue(6, 'Which colour?', ['prog', 'ask owner'],
                                         comments=[said('boss', 'blue', '2026-01-02T09:00:00Z')])]}})
        self.assertIn(f'the owner answered on {REPO}#6', self.run_tool('watch', '--once', now='2026-01-02T12:00:00Z').stdout)

    def test_a_working_label_the_owner_set_does_not_make_a_role_busy(self):
        self.data({REPO: {'open': [issue(3, 'Banner', ['design', 'doing']), issue(7, 'Icon', ['design'])]},
                   'api': {f'repos/{REPO}/issues/3/events?per_page=100': [
                       {'event': 'labeled', 'label': {'name': 'doing'}, 'actor': {'login': 'boss'}}]}})
        self.assertIn(f'next task for designer: run `agentq assign {REPO}#3 designer`', self.run_tool('watch', '--once').stdout)
        self.data({REPO: {'open': [issue(3, 'Banner', ['design', 'doing'], updated='2026-01-02T11:00:00Z'),
                                   issue(7, 'Icon', ['design'])]},
                   'api': {f'repos/{REPO}/issues/3/events?per_page=100': [
                       {'event': 'labeled', 'label': {'name': 'doing'}, 'actor': {'login': 'bot'}}]}})
        self.assertNotIn('designer', self.run_tool('watch', '--once', now=T1).stdout)

    def test_watch_without_work_keeps_polling_and_a_second_watcher_steps_back(self):
        self.data({REPO: {'open': [issue(3, 'Banner', ['design', 'doing']), issue(7, 'Busy', ['prog', 'doing'])]}})
        self.assertIn('no work', self.run_tool('watch', '--once').stdout)
        self.assertIn('no work yet – run it again', self.run_tool('watch', '--max-minutes', '0').stdout)
        with open(self.config + '.state.json') as f:
            self.assertEqual(json.load(f)['watch']['beat'], '2026-01-02T12:00:00Z')
        with open(self.config + '.state.json.watch.lock', 'a') as lock:
            system.lock_file(lock)
            self.assertIn('already running', self.run_tool('watch').stdout)
        self.data(self.board())
        self.assertIn('the owner wrote', self.run_tool('watch', '--once', now=T0).stdout)
        self.assertIn('no work', self.run_tool('watch', '--once', now=T1).stdout)  # same plan, not acted on yet
        self.assertIn('the owner wrote', self.run_tool('watch', '--once', now='2026-01-02T12:31:00Z').stdout)
        with open(self.config + '.state.json', 'w') as f:
            json.dump({}, f)
        run = subprocess.run([sys.executable, TOOL, '--config', self.config, 'watch', '--interval', '0'],
                             capture_output=True, text=True, env=self.env(), timeout=20)
        self.assertIn('agentq plan', run.stdout)

    def test_pause_keeps_the_watcher_up_but_plans_nothing(self):
        self.data(self.board())
        self.assertIn('paused:', self.run_tool('pause', "owner's word: stop for today").stdout)
        out = self.run_tool('watch', '--once').stdout
        self.assertIn("paused since 2026-01-02T12:00:00Z – owner's word: stop for today", out)
        self.assertNotIn('agentq plan', out)
        self.assertEqual(self.calls(), [])
        self.assertNotIn('watcher', self.run_tool('health', now='2026-01-02T20:00:00Z').stdout)
        late = self.run_tool('health', now='2026-01-03T13:00:00Z').stdout
        self.assertIn("paused since 2026-01-02T12:00:00Z (owner's word", late)
        self.assertNotIn('watcher is not running', late)
        out = self.run_tool('resume').stdout
        self.assertIn('resumed', out)
        self.assertIn('the watcher is not running: send the dispatcher (local_x) "Start the watcher"', out)
        self.assertIn('agentq plan', self.run_tool('watch', '--once').stdout)

    def test_every_nth_plan_tells_the_dispatcher_to_clear_its_conversation(self):
        with open(self.config) as f:
            cfg = json.load(f)
        cfg['clear_every'] = 2
        with open(self.config, 'w') as f:
            json.dump(cfg, f)
        self.data({REPO: {'open': [issue(4, 'New', comments=[])]}})
        first = self.run_tool('watch', '--once', now=T0).stdout
        self.assertNotIn('clear_session', first)
        self.data({REPO: {'open': [issue(5, 'Newer')]}})
        second = self.run_tool('watch', '--once', now=T1).stdout
        self.assertIn('then call clear_session with session_id "self"', second)

    def test_assign_starts_a_free_role_queues_for_a_busy_one_and_sets_effort(self):
        self.data({REPO: {'open': [issue(3, 'Banner', ['design', 'doing']), issue(4, 'Icon', ['ask owner']),
                                   issue(8, 'Hard one', ['hard']), issue(9, 'Easy one')]}})
        out = self.run_tool('assign', '4', 'designer').stdout
        self.assertIn('queued (its sessions work on #3)', out)
        self.assertEqual(self.calls(['issue', 'edit'])[-1],
                         ['issue', 'edit', '4', '-R', REPO, '--add-label', 'design', '--remove-label', 'ask owner'])
        self.assertEqual(self.body(self.calls(['issue', 'comment'])[-1]), '🤖 dispatcher: queued for designer.')
        out = self.run_tool('assign', '8', 'programmer').stdout
        self.assertIn('1. set_session_effort for session local_p: max', out)
        self.assertIn(f"2. send this line to session local_p: `Task {REPO}#8 for programmer, from the owner's queue: "
                      f"run agentq brief {REPO}#8 and act on it.`", out)
        self.assertEqual(self.calls(['issue', 'edit'])[-1], ['issue', 'edit', '8', '-R', REPO, '--add-label', 'prog',
                                                             '--add-label', 'doing', '--add-label', 'claude'])
        self.data({REPO: {'open': [issue(9, 'Easy one')]}})
        self.assertIn('1. set_session_effort for session local_p: high', self.run_tool('assign', '9', 'programmer').stdout)
        self.assertNotIn('set_session', self.run_tool('assign', '9', 'programmer').stdout)
        comments = len(self.calls(['issue', 'comment']))
        self.data({REPO: {'open': [issue(4, 'Icon', ['ask owner', 'prog'])]}})
        self.run_tool('assign', '4', 'designer', '--queue')
        self.assertEqual(len(self.calls(['issue', 'comment'])), comments)
        self.assertEqual(self.calls(['issue', 'edit'])[-1],
                         ['issue', 'edit', '4', '-R', REPO, '--add-label', 'design', '--remove-label', 'prog'])

    def test_brief_gives_the_owners_words_verbatim_and_screenshots_as_files(self):
        shot = os.path.join(self.dir.name, 'pic.png')
        with open(shot, 'wb') as f:
            f.write(b'\x89PNG fake')
        img = f'<p><img src="{pathlib.Path(shot).as_uri()}" alt="x"></p>'
        self.data({'api': {
            f'repos/{REPO}/issues/3': {'title': 'Banner', 'body': 'Make it  *bold*\nsee ![x](u)', 'body_html': img,
                                       'labels': [{'name': 'design'}], 'user': {'login': 'boss'}},
            f'repos/{REPO}/issues/3/comments': [
                {'user': {'login': 'boss'}, 'body': 'first words', 'body_html': '', 'created_at': '2026-01-02T08:00:00Z'},
                {'user': {'login': 'bot'}, 'body': 'agent noise', 'body_html': img, 'created_at': '2026-01-02T09:00:00Z'},
                {'user': {'login': 'bot'}, 'body': '🤖 marketer: → designer. texts in branch copy-1\n<!-- agentq:route -->',
                 'body_html': '', 'created_at': '2026-01-02T09:30:00Z'},
                {'user': {'login': 'boss'}, 'body': 'and red', 'body_html': img, 'created_at': '2026-01-02T10:00:00Z'}]}})
        out = self.run_tool('brief', '3').stdout
        self.assertIn('Task acme/app#3 for designer', out)
        self.assertIn('Make it  *bold*\nsee ![x](u)', out)
        self.assertIn('first words', out)
        self.assertIn('and red', out)
        self.assertNotIn('agent noise', out)
        self.assertIn('--- handed over, 2026-01-02T09:30:00Z ---\n🤖 marketer: → designer. texts in branch copy-1\n', out)
        self.assertNotIn('agentq:route', out)
        self.assertIn('--no-lesson', out)
        self.assertIn("the owner's order: do it to the end without asking whether to", out)
        files = [l for l in out.splitlines() if l.endswith('.png')]
        self.assertEqual(len(files), 2)
        self.assertTrue(os.path.realpath(files[0]).startswith(
            os.path.realpath(os.path.join(self.dir.name, 'home', '.cache', 'agentq', 'shots'))))
        self.assertEqual(open(files[0], 'rb').read(), b'\x89PNG fake')
        repo_img = ('<img src="https://github.com/acme/shots/raw/main/s/a%20b.png">'
                    '<img src="https://raw.githubusercontent.com/acme/closed/main/x.png">')
        self.data({'api': {f'repos/{REPO}/issues/5': {'title': 'Shot', 'body': 'see', 'body_html': repo_img,
                                                       'labels': [], 'user': {'login': 'boss'}}},
                   'raw': {'repos/acme/shots/contents/s/a%20b.png?ref=main': 'PNGDATA'}})
        out = self.run_tool('brief', '5').stdout
        files = [l for l in out.splitlines() if l.endswith('.png')]
        self.assertEqual(open(files[0]).read(), 'PNGDATA')
        self.assertIn('could not download screenshot 2: the AI account cannot read acme/closed', out)
        self.data({'api': {
            f'repos/{REPO}/issues/3': {'title': 'Banner', 'body': 'Make it  *bold*', 'body_html': img,
                                       'labels': [{'name': 'design'}], 'user': {'login': 'boss'}},
            f'repos/{REPO}/issues/3/comments': [
                {'user': {'login': 'boss'}, 'body': 'first words', 'body_html': '', 'created_at': '2026-01-02T08:00:00Z'},
                {'user': {'login': 'boss'}, 'body': 'and red', 'body_html': img, 'created_at': '2026-01-02T10:00:00Z'}]}})
        news = self.run_tool('brief', '3', '--since', '2026-01-02T10:00:00Z').stdout
        self.assertIn('and red', news)
        self.assertNotIn('first words', news)
        self.assertNotIn('bold', news)
        self.assertNotIn('handed over', news)

    def test_route_relabels_and_keeps_the_last_five_lessons(self):
        for n in range(20, 27):
            self.data({REPO: {'open': [issue(n, f'Logo {n}', ['prog', 'doing'])]}})
            self.run_tool('route', str(n), 'designer', 'a logo')
        self.assertEqual(self.calls(['issue', 'edit'])[-1], ['issue', 'edit', '26', '-R', REPO, '--add-label', 'design',
                                                             '--remove-label', 'prog', '--remove-label', 'doing'])
        self.assertEqual(self.body(self.calls(['issue', 'comment'])[-1]), '🤖 programmer: → designer. a logo\n<!-- agentq:route -->')
        with open(os.path.join(self.dir.name, 'disp', 'lessons.json')) as f:
            kept = [e['issue'] for e in json.load(f)['examples']['designer']]
        self.assertEqual(kept, ['#22', '#23', '#24', '#25', '#26'])
        roles = open(os.path.join(self.dir.name, 'disp', 'roles.md')).read()
        self.assertIn('#26 Logo 26 (not programmer)', roles)
        self.data({REPO: {'open': [issue(30, 'Merge me', ['design'])]}})
        self.run_tool('route', '30', 'programmer', 'merge branch x', '--no-lesson')
        with open(os.path.join(self.dir.name, 'disp', 'lessons.json')) as f:
            self.assertNotIn('programmer', json.load(f)['examples'])

    def test_teach_owner_outranks_agents_and_a_tie_asks_the_owner(self):
        self.assertIn('rule written: Banners → designer (agent)', self.run_tool('teach', 'Banners -> designer').stdout)
        self.assertIn("the owner's rule replaces", self.run_tool('teach', 'banners → programmer', '--owner').stdout)
        self.assertIn("not written: the owner's rule stands", self.run_tool('teach', 'banners → designer').stdout)
        self.run_tool('teach', 'icons → designer')
        self.data({REPO: {'next': 41}})
        out = self.run_tool('teach', 'icons → programmer').stdout
        self.assertIn(f'asked the owner in {REPO}#41', out)
        made = self.calls(['issue', 'create'])[-1]
        self.assertIn('Rule question: icons', made)
        self.assertIn('ask owner', made)
        self.run_tool('teach', 'icons → programmer', '--issue', '7')
        self.assertEqual(self.calls(['issue', 'edit'])[-1],
                         ['issue', 'edit', '7', '-R', REPO, '--add-label', 'ask owner', '--remove-label', 'doing'])
        out = self.run_tool('teach', 'ad texts → designer (writes; never touches code)').stdout
        self.assertIn('rule written: ad texts → designer (writes; never touches code) (agent)', out)
        self.assertIn('does not start with a role', self.run_tool('teach', 'logos → nobody', ok=False).stderr)
        rules = self.run_tool('roles').stdout
        self.assertIn('- banners → programmer (owner)', rules)
        self.assertIn('- icons → designer (agent)', rules)
        self.assertNotIn('icons → programmer', rules)

    def test_batch_pins_a_commit_and_checked_labels_every_task(self):
        project = os.path.join(self.dir.name, 'project')
        os.makedirs(os.path.join(project, 'rules'))
        os.makedirs(os.path.join(project, 'src'))

        def commit(path, message):
            with open(os.path.join(project, path), 'a') as f:
                f.write(message)
            subprocess.run(['git', '-C', project, 'add', '.'], check=True)
            subprocess.run(['git', '-C', project, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', message],
                           check=True)
        subprocess.run(['git', 'init', '-q', project], check=True)
        commit('rules/a.md', 'Fixes #10')
        commit('src/x.py', 'Fixes #11')
        head = subprocess.run(['git', '-C', project, 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
        with open(self.config) as f:
            cfg = json.load(f)
        cfg['checkout'] = project
        cfg['roles'].append({'role': 'reviewer', 'mode': 'checker', 'n': 1, 'paths': ['rules/'], 'since': '2026-01-01T00:00:00Z'})
        with open(self.config, 'w') as f:
            json.dump(cfg, f)
        subprocess.run(['git', '-C', project, 'remote', 'add', 'origin', project], check=True)
        self.data({**self.board(next=50), 'api': {f'repos/{REPO}/commits/HEAD': {'sha': head}}})
        out = self.run_tool('batch', 'reviewer').stdout
        self.assertIn(f'{REPO}#50 created: reviewer checks #10.', out)
        made = self.calls(['issue', 'create'])[-1]
        self.assertIn('Check: #10', made)
        self.assertEqual(made[made.index('--label') + 1:], ['reviewer', '--label', 'check batch', '--label', 'doing',
                                                           '--label', 'claude'])
        self.assertIn(f'Commit: {head}', self.body(made))
        self.assertNotIn('#11', self.body(made))
        out = self.run_tool('batch', 'checker').stdout
        self.assertIn('1. set_session_model for session local_c: mid', out)
        body = self.body(self.calls(['issue', 'create'])[-1])
        self.assertIn('- #10 Done A\n- #11 Done B', body)
        self.data({REPO: {'open': [issue(50, 'Check: #10 #11', ['check', 'check batch', 'doing'], body=body)]}})
        self.run_tool('checked', '50', 'all fine')
        edits = self.calls(['issue', 'edit'])
        self.assertIn(['issue', 'edit', '10', '-R', REPO, '--add-label', 'checked: checker'], edits)
        self.assertIn(['issue', 'edit', '11', '-R', REPO, '--add-label', 'checked: checker'], edits)
        self.assertEqual(self.body(self.calls(['issue', 'comment'])[-1]), '🤖 checker: checked #10 #11. all fine')
        self.assertEqual(self.calls(['issue', 'close'])[-1], ['issue', 'close', '50', '-R', REPO])
        self.data({REPO: {'open': [issue(51, 'Check: #12', ['check', 'check batch', 'doing'])]}})
        made = len(self.calls(['issue', 'create']))  # it made its own batch since the plan said one was ready
        self.assertIn(f'nothing to do: checker is already on {REPO}#51', self.run_tool('batch', 'checker').stdout)
        self.assertEqual(len(self.calls(['issue', 'create'])), made)

    def batch_checkout(self):
        origin = os.path.join(self.dir.name, 'origin')
        checkout = os.path.join(self.dir.name, 'checkout')

        def git(folder, *args):
            return subprocess.run(['git', '-C', folder, '-c', 'user.name=t', '-c', 'user.email=t@t', *args],
                                  check=True, capture_output=True, text=True).stdout.strip()
        os.makedirs(origin)
        git(origin, 'init', '-q', '-b', 'main')
        git(origin, 'commit', '-qm', 'initial', '--allow-empty')
        git(origin, 'clone', '-q', origin, checkout)
        old = git(checkout, 'rev-parse', 'HEAD')
        git(checkout, 'switch', '-qc', 'unrelated-local-branch')
        pathlib.Path(checkout, 'owner.txt').write_text('keep this uncommitted file', encoding='utf-8')
        git(origin, 'commit', '-qm', 'Fixes #10', '--allow-empty')
        source = git(origin, 'rev-parse', 'HEAD')
        cfg = json.loads(pathlib.Path(self.config).read_text())
        cfg['checkout'] = checkout
        pathlib.Path(self.config).write_text(json.dumps(cfg))
        fixture = {**self.board(next=50), 'api': {
            f'repos/{REPO}/commits/HEAD': {'sha': source},
            f'repos/{REPO}/issues/10/events?per_page=100': [{'event': 'closed', 'commit_id': source}],
            f'repos/{REPO}/issues/11/events?per_page=100': [{'event': 'closed', 'commit_id': None}],
        }}
        self.data(fixture)
        return git, checkout, old, source, fixture

    def test_batch_fetches_published_commit_without_changing_stale_checkout(self):
        git, checkout, old, source, fixture = self.batch_checkout()
        self.run_tool('batch', 'checker')
        body = self.body(self.calls(['issue', 'create'])[-1])
        self.assertIn(f'Commit: {source}', body)
        self.assertIn(f'"closing_commits": {{"10": "{source}"}}', body)
        self.assertEqual(git(checkout, 'rev-parse', 'HEAD'), old)
        self.assertEqual(git(checkout, 'branch', '--show-current'), 'unrelated-local-branch')
        self.assertEqual(pathlib.Path(checkout, 'owner.txt').read_text(), 'keep this uncommitted file')
        self.assertEqual(git(checkout, 'status', '--porcelain'), '?? owner.txt')

    def test_batch_rejects_closing_commit_outside_published_history(self):
        git, checkout, old, source, fixture = self.batch_checkout()
        git(checkout, 'commit', '-qm', 'unpublished Fixes #10', '--allow-empty')
        missing = git(checkout, 'rev-parse', 'HEAD')
        fixture['api'][f'repos/{REPO}/issues/10/events?per_page=100'][0]['commit_id'] = missing
        self.data(fixture)
        run = self.run_tool('batch', 'checker', ok=False)
        self.assertEqual(run.returncode, 1)
        self.assertIn('not a verified ancestor', run.stderr)
        self.assertIn(missing, run.stderr)
        self.assertEqual(self.calls(['issue', 'create']), [])

    def test_batch_does_not_fall_back_to_head_when_fetch_fails(self):
        git, checkout, old, source, fixture = self.batch_checkout()
        git(checkout, 'remote', 'set-url', 'origin', os.path.join(self.dir.name, 'missing-origin'))
        run = self.run_tool('batch', 'checker', ok=False)
        self.assertEqual(run.returncode, 1)
        self.assertIn('git fetch', run.stderr)
        self.assertEqual(self.calls(['issue', 'create']), [])

    def test_batch_rejects_missing_remote_sha_and_reopened_task(self):
        git, checkout, old, source, fixture = self.batch_checkout()
        fixture['api'][f'repos/{REPO}/commits/HEAD'] = {}
        self.data(fixture)
        run = self.run_tool('batch', 'checker', ok=False)
        self.assertEqual(run.returncode, 1)
        self.assertIn('cannot pin', run.stderr)
        fixture['api'][f'repos/{REPO}/issues/10/events?per_page=100'].append({'event': 'reopened'})
        self.data(fixture)
        run = self.run_tool('batch', 'checker', ok=False)
        self.assertEqual(run.returncode, 1)
        self.assertIn('reopened', run.stderr)
        self.assertEqual(self.calls(['issue', 'create']), [])

    def test_open_creates_a_task_for_a_role(self):
        self.data({REPO: {'next': 77}})
        self.assertIn(f'{REPO}#77 opened for programmer', self.run_tool('open', 'programmer', 'Export fails', 'evidence: …',
                                                                       '--as', 'checker').stdout)
        made = self.calls(['issue', 'create'])[-1]
        self.assertEqual(self.body(made), '🤖 checker: evidence: …')
        self.assertEqual(made[made.index('--label') + 1], 'prog')

    def test_an_extra_as_role_is_accepted(self):
        self.data({REPO: {'open': [issue(7, 'Bug', ['prog', 'doing'])]}})
        self.run_tool('done', '7', 'fixed', '--as', 'checker')

    def test_done_comments_drops_working_and_closes(self):
        self.data({REPO: {'open': [issue(7, 'Bug', ['design', 'doing'])]}})
        self.run_tool('done', '7', 'fixed the colour; checked on a phone')
        self.assertEqual(self.body(self.calls(['issue', 'comment'])[-1]), '🤖 designer: fixed the colour; checked on a phone')
        self.assertEqual(self.calls(['issue', 'edit'])[-1], ['issue', 'edit', '7', '-R', REPO, '--remove-label', 'doing'])
        self.assertEqual(self.calls(['issue', 'close'])[-1], ['issue', 'close', '7', '-R', REPO])

    def test_health_warns_when_the_disk_is_nearly_full(self):
        with open(self.config) as f:
            cfg = json.load(f)
        cfg['disk_min_gb'] = 10 ** 9  # more than any disk has
        with open(self.config, 'w') as f:
            json.dump(cfg, f)
        self.data({REPO: {'open': [], 'next': 60}})
        self.assertIn('GB free on this computer', self.run_tool('health').stdout)

    def test_health_removes_the_worktrees_whose_work_is_in_main(self):
        base = os.path.realpath(self.dir.name)  # git prints /private/var/…, not /var/…
        project = os.path.join(base, 'proj')

        def git(*args, cwd=project):
            return subprocess.run(['git', '-C', cwd, '-c', 'user.name=t', '-c', 'user.email=t@t', *args],
                                  check=True, capture_output=True, text=True).stdout
        subprocess.run(['git', 'init', '-q', '-b', 'main', project], check=True)
        git('commit', '-q', '--allow-empty', '-m', 'one')
        trees = {name: os.path.join(base, name) for name in ('merged', 'dirty', 'ahead', 'fresh')}
        trees['session'] = os.path.join(project, '.claude', 'worktrees', 'session')
        for name, path in trees.items():
            git('worktree', 'add', '-q', '-b', name, path)
        with open(os.path.join(trees['dirty'], 'x.txt'), 'w') as f:
            f.write('not committed')
        git('commit', '-q', '--allow-empty', '-m', 'not in main', cwd=trees['ahead'])
        old = time.time() - 13 * 3600
        for name, path in trees.items():
            gitdir = git('rev-parse', '--absolute-git-dir', cwd=path).strip()
            for part in ('HEAD', 'index', 'logs/HEAD'):
                if name != 'fresh' and os.path.exists(os.path.join(gitdir, part)):
                    os.utime(os.path.join(gitdir, part), (old, old))
        with open(self.config) as f:
            cfg = json.load(f)
        cfg['checkout'] = project
        with open(self.config, 'w') as f:
            json.dump(cfg, f)
        self.data({REPO: {'open': [], 'next': 60}})
        out = self.run_tool('health').stdout
        self.assertIn(f"removed the worktree {os.path.normpath(trees['merged'])}: its work is in main", out)
        self.assertFalse(os.path.exists(trees['merged']))
        for name in ('dirty', 'ahead', 'fresh', 'session'):
            self.assertTrue(os.path.exists(trees[name]), name)
        self.assertIn('merged', git('branch'))  # the branch stays for a task that comes back

    def test_health_reports_to_one_issue_and_closes_it_when_well(self):
        stale = issue(7, 'Stuck', ['prog', 'doing'], updated='2026-01-01T00:00:00Z')
        self.data({REPO: {'open': [stale], 'next': 60}})
        out = self.run_tool('health').stdout
        self.assertIn('the watcher is not running', out)
        self.assertIn(f"{REPO}#7 is 'doing' but nothing happened for over 24 h", out)
        self.assertIn('agent health', self.calls(['issue', 'create'])[-1])
        report = issue(60, 'Agent team health', ['agent health'])
        self.data({REPO: {'open': [stale, report]}})
        self.assertIn('unchanged', self.run_tool('health').stdout)
        self.assertEqual(self.calls(['issue', 'comment']), [])
        other = issue(8, 'Stuck too', ['design', 'doing'], updated='2026-01-01T00:00:00Z')
        self.data({REPO: {'open': [stale, other, report]}})
        self.run_tool('health')
        self.assertEqual(self.calls(['issue', 'comment'])[-1][2], '60')
        self.data({REPO: {'open': [report]}})
        with open(self.config + '.state.json', 'w') as f:
            json.dump({'watch': {'beat': '2026-01-02T11:59:00Z'}}, f)
        with open(self.config + '.state.json.watch.lock', 'a') as lock:
            system.lock_file(lock)
            self.assertIn('healthy', self.run_tool('health').stdout)
        self.assertEqual(self.calls(['issue', 'close'])[-1], ['issue', 'close', '60', '-R', REPO])

    def test_setup_checks_access_then_builds_labels_and_the_dispatcher_folder(self):
        self.data({REPO: {'labels': []}, 'api': {'user': {'login': 'someone'}, f'repos/{REPO}': {'permissions': {}}}})
        run = self.run_tool('setup', ok=False)
        self.assertEqual(run.returncode, 1)
        self.assertIn('not the AI account bot', run.stdout)
        self.assertIn('no Write access', run.stdout)
        self.assertEqual(self.calls(['label', 'create']), [])
        self.data({REPO: {'labels': []}, 'api': {'user': {'login': 'bot'}, f'repos/{REPO}': {'permissions': {'push': True}}}})
        self.assertIn('sidebar group: MISSING', self.run_tool('setup').stdout)
        out = self.run_tool('setup', '--group', 'grp-1').stdout
        self.assertIn('sidebar group: grp-1', out)
        with open(self.config) as f:
            self.assertEqual(json.load(f)['team_group'], 'grp-1')
        made = [c[2] for c in self.calls(['label', 'create'])]
        for name in ('prog', 'design', 'check', 'checked: checker', 'priority', "waits for owner's word", 'check batch'):
            self.assertIn(name, made)
        self.assertNotIn('checked: designer', made)
        self.assertIn('designer | design | programmer | - | - | - | - | no | local_d', out)
        disp = os.path.join(self.dir.name, 'disp')
        claude = open(os.path.join(disp, 'CLAUDE.md')).read()
        self.assertIn(f'`{system.self_command()} watch`', claude)
        self.assertNotIn('{{', claude)
        self.assertIn('Your own session id is `local_x`. Never send to it. Every session id in a plan', claude)
        old = claude.replace(claude[claude.index('<!-- agentq:session'):claude.index('You are')], '')
        with open(os.path.join(disp, 'CLAUDE.md'), 'w') as f:
            f.write(old)
        self.run_tool('role', 'dispatcher', '--session', 'local_y')
        claude = open(os.path.join(disp, 'CLAUDE.md')).read()
        self.assertEqual(claude.count('<!-- agentq:session -->'), 1)
        self.assertIn('Your own session id is `local_y`.', claude)
        self.assertTrue(claude.startswith('# Dispatcher\n\n<!-- agentq:session -->'))
        self.assertIn('\n\nYou are the dispatcher', claude)
        self.assertIn('Never hold a step to ask anyone', claude)
        with open(os.path.join(disp, 'examples', 'README.md'), 'w') as f:
            f.write('my own notes')
        self.run_tool('role', 'dispatcher', '--session', 'local_y')
        self.assertIn('Your own session id is `local_y`.', open(os.path.join(disp, 'CLAUDE.md')).read())
        self.assertEqual(open(os.path.join(disp, 'examples', 'README.md')).read(), 'my own notes')
        self.assertTrue(os.path.exists(os.path.join(disp, 'examples', 'README.md')))
        self.assertEqual(os.path.realpath(os.path.join(disp, '.agentq.json')), os.path.realpath(self.config))
        self.assertIn('## designer', open(os.path.join(disp, 'roles.md')).read())
        agents = open(os.path.join(disp, 'AGENTS.md')).read()
        self.assertIn(f'Run `{system.self_command()} watch` once. It starts the watcher on its own', agents)

    def test_role_adds_the_ready_made_marketer_and_sets_the_dispatcher_session(self):
        self.data({REPO: {'labels': []}})
        shot = os.path.join(self.dir.name, 'ad.png')
        with open(shot, 'wb') as f:
            f.write(b'png')
        self.run_tool('role', 'marketer', '--session', 'local_m', '--model', 'mid', '--shot', shot)
        self.run_tool('role', 'dispatcher', '--session', 'local_x2')
        self.assertIn('checker | check | checker | 2/36h', self.run_tool('role', 'checker', '--hours', '36').stdout)
        with open(self.config) as f:
            cfg = json.load(f)
        marketer = cfg['roles'][-1]
        self.assertEqual((marketer['role'], marketer['session'], marketer['model']), ('marketer', 'local_m', 'mid'))
        self.assertIn('public or paid', marketer['description'])
        self.assertEqual(cfg['dispatcher']['session'], 'local_x2')
        self.assertIs(type(cfg['roles'][2]['hours']), int)
        self.assertIn('marketer', [c[2] for c in self.calls(['label', 'create'])])
        self.assertTrue(os.path.exists(os.path.join(self.dir.name, 'disp', 'examples', 'marketer-1.png')))
        self.assertIn('reference screenshot: examples/marketer-1.png', self.run_tool('roles').stdout)
        self.run_tool('teach', 'audits → checker')
        self.assertIn('rules and lessons for checker removed', self.run_tool('role', 'checker', '--remove').stdout)
        self.assertNotIn('audits', self.run_tool('roles').stdout)
        with open(self.config) as f:
            self.assertNotIn('checker', [r['role'] for r in json.load(f)['roles']])


class LinkTest(Base):
    def setUp(self):
        super().setUp()
        with open(self.config) as f:
            cfg = json.load(f)
        cfg.update({'roles': ROLES, 'dispatcher': {'folder': os.path.join(self.dir.name, 'disp')}})
        with open(self.config, 'w') as f:
            json.dump(cfg, f)

    def test_sharing_is_off_until_a_link_is_added(self):
        self.data({REPO: {'open': [issue(4, 'New page')]}})
        self.assertNotIn('move', self.run_tool('watch', '--once').stdout)
        run = self.run_tool('move', '4', OTHER, ok=False)
        self.assertIn('not a linked project', run.stderr)
        self.run_tool('link', OTHER, 'the website: pages, blog')
        self.assertIn(f'- {OTHER}: the website: pages, blog', self.run_tool('roles').stdout)
        self.assertIn(f'run `agentq move {REPO}#4 <owner/repo>` instead', self.run_tool('watch', '--once').stdout)
        self.run_tool('link', OTHER, '--remove')
        self.assertNotIn(OTHER, self.run_tool('roles').stdout)

    def test_move_transfers_without_our_labels_and_teaches_the_dispatcher(self):
        self.run_tool('link', OTHER, 'the website')
        self.data({REPO: {'open': [issue(4, 'New blog page', ['prog', 'doing', 'priority'])]}, OTHER: {'next': 9}})
        out = self.run_tool('move', '4', OTHER, 'it is a page').stdout
        self.assertIn(f'{REPO}#4 → https://github.com/{OTHER}/issues/9', out)
        self.assertEqual(self.body(self.calls(['issue', 'comment'])[-1]), f'🤖 programmer: moved to {OTHER}. it is a page')
        self.assertEqual(self.calls(['issue', 'edit'])[-1],
                         ['issue', 'edit', '4', '-R', REPO, '--remove-label', 'prog', '--remove-label', 'doing'])
        self.assertIn(f'#4 New blog page → {OTHER}', self.run_tool('roles').stdout)

    def test_move_copies_and_closes_when_github_refuses_the_transfer(self):
        self.run_tool('link', OTHER, 'the website')
        self.data({REPO: {'open': [issue(4, 'New page', body='the text')], 'transfer_fails': True}, OTHER: {'next': 9}})
        self.run_tool('move', '4', OTHER)
        made = self.calls(['issue', 'create'])[-1]
        self.assertEqual(made[made.index('-R') + 1], OTHER)
        self.assertEqual(self.body(made), f'moved here from {REPO}#4.\n\nthe text')
        closing = self.calls(['issue', 'close'])[-1]
        self.assertEqual(closing[:4], ['issue', 'close', '4', '-R'])
        self.assertIn(f'🤖 dispatcher: → {OTHER}#9', closing)
        self.assertNotIn('lesson', self.run_tool('roles').stdout)
        self.assertFalse(os.path.exists(os.path.join(self.dir.name, 'disp', 'lessons.json')))

    def test_move_releases_only_the_transferred_task_holder(self):
        self.run_tool('role', 'programmer', '--agent', 'codex')
        self.run_tool('link', OTHER, 'the website')
        self.data({REPO: {'open': [issue(4, 'A page', ['prog', 'doing'])]}, OTHER: {'next': 9}})
        holders = {f'{REPO}#4': 'codex-1', f'{REPO}#5': 'codex-2'}
        self.state(lambda s: s.update({'holders': holders}))
        self.run_tool('move', '4', OTHER)
        self.assertEqual(self.state()['holders'], {f'{REPO}#5': 'codex-2'})
        reads = len(self.calls(['issue', 'view']))
        self.data({REPO: {'open': [], 'view_errors': {'4': 'GraphQL: Could not resolve to an issue or pull request with the number of 4. (repository.issue)'}}})
        self.assertNotIn('you hold', self.run_tool('next', 'programmer', '--as', 'codex-1').stdout)
        self.assertEqual(len(self.calls(['issue', 'view'])), reads, 'next must not look up the transferred number again')

    def test_move_copy_fallback_releases_holder_only_after_success(self):
        self.run_tool('link', OTHER, 'the website')
        holders = {f'{REPO}#4': 'codex-1', f'{REPO}#5': 'codex-2'}
        self.state(lambda s: s.update({'holders': holders}))
        fixture = {REPO: {'open': [issue(4, 'A page', ['prog', 'doing'])], 'transfer_fails': True},
                   OTHER: {'next': 9, 'create_fails': True}}
        self.data(fixture)
        self.assertNotEqual(self.run_tool('move', '4', OTHER, ok=False).returncode, 0)
        self.assertEqual(self.state()['holders'], holders, 'a failed transfer and copy must keep the task held')
        fixture[OTHER]['create_fails'] = False
        self.data(fixture)
        self.run_tool('move', '4', OTHER)
        self.assertEqual(self.state()['holders'], {f'{REPO}#5': 'codex-2'})

    def test_next_recovers_a_missing_held_issue_and_takes_the_next_task(self):
        self.run_tool('role', 'programmer', '--agent', 'codex')
        for error in ('GraphQL: Could not resolve to an issue or pull request with the number of 4. (repository.issue)',
                      'gh: Not Found (HTTP 404)'):
            with self.subTest(error=error):
                self.state(lambda s: s.update({'holders': {f'{REPO}#4': 'codex-1', f'{REPO}#5': 'codex-2'}}))
                self.data({REPO: {'open': [issue(6, 'Next', ['prog'])], 'view_errors': {'4': error}},
                           'api': {f'repos/{REPO}/issues/6': {'title': 'Next', 'body': '', 'user': {'login': 'boss'}}}})
                out = self.run_tool('next', 'programmer', '--as', 'codex-1').stdout
                self.assertIn(f'{REPO}#6 is yours now', out)
                self.assertEqual(self.state()['holders'], {f'{REPO}#5': 'codex-2', f'{REPO}#6': 'codex-1'})

    def test_next_missing_held_issue_with_no_next_task_stops_normally(self):
        self.run_tool('role', 'programmer', '--agent', 'codex')
        self.state(lambda s: s.update({'holders': {f'{REPO}#4': 'codex-1', f'{REPO}#5': 'codex-2'}}))
        self.data({REPO: {'open': [], 'view_errors': {'4': 'gh: Not Found (HTTP 404)'}}})
        self.assertIn('No task now', self.as_codex('next', 'programmer', '--as', 'codex-1').stdout)
        self.assertEqual(self.state()['holders'], {f'{REPO}#5': 'codex-2'})

    def test_next_keeps_claims_when_the_issue_or_repository_read_is_unknown(self):
        self.run_tool('role', 'programmer', '--agent', 'codex')
        for error, repo_error in [('HTTP 403: Resource not accessible', None),
                                  ('Connection refused', None),
                                  ('GraphQL: Could not resolve to a Repository with the name acme/app.', None),
                                  ('gh: Not Found (HTTP 404)', 'gh: Not Found (HTTP 404)')]:
            with self.subTest(error=error, repo_error=repo_error):
                holders = {f'{REPO}#4': 'codex-1', f'{REPO}#5': 'codex-2'}
                self.state(lambda s: s.update({'holders': holders}))
                self.data({REPO: {'open': [issue(6, 'Next', ['prog'])], 'view_errors': {'4': error}, 'repo_error': repo_error}})
                run = self.run_tool('next', 'programmer', '--as', 'codex-1', ok=False)
                self.assertNotEqual(run.returncode, 0)
                self.assertEqual(self.state()['holders'], holders)
                self.assertEqual(self.calls(['issue', 'comment']), [])

    def test_split_creates_the_other_part_with_a_link_back(self):
        self.run_tool('link', OTHER, 'the website')
        self.data({REPO: {'open': [issue(4, 'Launch', ['prog', 'doing'])]}, OTHER: {'next': 12}})
        self.assertIn(f'{OTHER}#12 created from {REPO}#4', self.run_tool('split', '4', OTHER, 'Launch page', 'a page for the launch').stdout)
        made = self.calls(['issue', 'create'])[-1]
        self.assertEqual(self.body(made), f'🤖 programmer: a page for the launch\n\nSplit from {REPO}#4.')
        self.assertEqual(self.body(self.calls(['issue', 'comment'])[-1]), f'🤖 programmer: the part for {OTHER} is {OTHER}#12.')
        self.assertEqual(self.calls(['issue', 'edit']), [])

    def test_open_in_a_linked_project_leaves_the_sorting_to_it(self):
        self.run_tool('link', OTHER, 'the website')
        self.data({REPO: {'open': []}, OTHER: {'next': 13}})
        out = self.run_tool('open', 'marketer', 'Launch video page', 'texts and SEO', '-R', OTHER, '--as', 'programmer').stdout
        self.assertIn(f'{OTHER}#13 opened in the linked project', out)
        made = self.calls(['issue', 'create'])[-1]
        self.assertNotIn('--label', made)
        self.assertIn('for the marketer role: texts and SEO', self.body(made))


class InitTest(Base):
    def test_a_config_pointer_stands_for_a_symlink(self):
        pointer = os.path.join(self.dir.name, 'pointer.json')  # what init writes on Windows without symlink rights
        with open(pointer, 'w') as f:
            json.dump({'agentq_config': self.config}, f)
        run = subprocess.run([sys.executable, TOOL, '--config', pointer, 'roles'], capture_output=True, text=True,
                             env=self.env())
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('programmer', run.stdout)

    def test_the_command_workers_run_works_in_every_shell(self):
        import shlex
        if not system.WINDOWS:
            self.assertEqual(system.self_command(), shlex.quote(os.path.realpath(TOOL)))
        was = (system.WINDOWS, system.SELF, sys.executable)
        try:
            system.WINDOWS, system.SELF = True, 'C:\\Users\\me\\Sites\\agent-team-playbook\\tools\\agentq'
            sys.executable = 'C:\\Program Files\\Python313\\python.exe'
            self.assertEqual(system.self_command(), '"C:/Program Files/Python313/python.exe" '
                                                'C:/Users/me/Sites/agent-team-playbook/tools/agentq')
        finally:
            system.WINDOWS, system.SELF, sys.executable = was

    def test_init_installs_into_one_project_only(self):
        project = os.path.join(self.dir.name, 'proj')
        subprocess.run(['git', 'init', '-q', project], check=True)
        subprocess.run(['git', '-C', project, 'remote', 'add', 'origin', 'git@github.com:acme/app.git'], check=True)
        self.data({'api': {'user': {'login': 'bot'}}})
        for _ in range(2):
            run = subprocess.run([sys.executable, TOOL, 'init', '--owner', 'boss', '--project', project],
                                 capture_output=True, text=True, env=self.env())
            self.assertEqual(run.returncode, 0, run.stderr)
        home = os.path.join(self.dir.name, 'home')
        config = os.path.join(home, '.config', 'agentq', 'acme-app.json')
        with open(config) as f:
            cfg = json.load(f)
        self.assertEqual((cfg['owner_accounts'], cfg['agent_account'], cfg['repos']), (['boss'], 'bot', ['acme/app']))
        self.assertEqual(os.path.realpath(os.path.join(project, '.agentq.json')), os.path.realpath(config))
        self.assertIs(cfg.get('primary', True), True)
        self.assertNotIn('live', cfg)  # the example's restart command is a placeholder, never a real one
        second = os.path.join(self.dir.name, 'second.json')  # the same project from another computer
        run = subprocess.run([sys.executable, TOOL, 'init', '--owner', 'boss', '--project', project, '--second',
                              '--config', second], capture_output=True, text=True, env=self.env())
        self.assertEqual(run.returncode, 0, run.stderr)
        with open(second) as f:
            self.assertIs(json.load(f)['primary'], False)
        first = os.path.join(self.dir.name, 'first.json')  # the first computer's team, in its own language
        with open(first, 'w') as f:
            json.dump({'owner_accounts': ['boss'], 'agent_account': 'bot', 'repos': ['acme/app', 'acme/site'],
                       'checkout': '/Users/x/app', 'labels': {'working': 'taisau', 'question': 'reikia tavęs',
                                                              'deferred': 'atidėta', 'waiting': 'laukia'},
                       'texts': {'take': 'imu.'}, 'default_role': 'programuotojas', 'team_group': 'cg-1',
                       'live': {'role': 'testuotojas', 'command': 'restart {sha}'}, 'codex_model': 'model-b',
                       'tests': {'mode': 'batched', 'checkout': '/Users/x/tests'},
                       'dispatcher': {'folder': '/Users/x/disp', 'session': 'local_d', 'agent': 'both'},
                       'roles': [{'role': 'programuotojas', 'label': 'programuotojas', 'mode': 'programmer',
                                  'description': 'viskas', 'agent': 'both', 'session': 'local_a',
                                  'sessions': ['local_a', 'local_b'], 'active': 0, 'shots': ['/Users/x/a.png']}]}, f)
        copy = os.path.join(self.dir.name, 'copy.json')
        run = subprocess.run([sys.executable, TOOL, 'init', '--owner', 'boss', '--project', project, '--second',
                              '--like', first, '--config', copy], capture_output=True, text=True, env=self.env())
        self.assertEqual(run.returncode, 0, run.stderr)
        with open(copy) as f:
            made = json.load(f)
        self.assertEqual(made['labels']['working'], 'taisau')
        self.assertEqual((made['texts'], made['default_role'], made['codex_model']), ({'take': 'imu.'}, 'programuotojas',
                                                                                       'model-b'))
        self.assertEqual(made['roles'], [{'role': 'programuotojas', 'label': 'programuotojas', 'mode': 'programmer',
                                          'description': 'viskas', 'agent': 'both'}])
        self.assertEqual(made['repos'], ['acme/app', 'acme/site'])
        self.assertTrue(made['dispatcher']['folder'].endswith('acme-app-dispatcher'))
        self.assertNotIn('session', made['dispatcher'])
        for key in ('live', 'tests', 'team_group'):
            self.assertNotIn(key, made)
        self.assertIs(made['primary'], False)
        self.assertEqual(os.path.realpath(os.path.join(project, '.claude', 'skills', 'agent-team')),
                         os.path.join(ROOT, 'skill', 'agent-team'))
        run = subprocess.run([sys.executable, TOOL, 'init', '--owner', 'boss', '--project', project, '--codex'],
                             capture_output=True, text=True, env=self.env())
        self.assertEqual(run.returncode, 0, run.stderr)
        agents = open(os.path.join(project, 'AGENTS.md')).read()
        self.assertIn(os.path.join('skill', 'agent-team', 'SKILL.md'), agents)
        exclude = open(os.path.join(project, '.git', 'info', 'exclude')).read().splitlines()
        self.assertEqual(exclude.count('.agentq.json'), 1)
        self.assertEqual(exclude.count('.claude/skills/agent-team'), 1)
        self.assertFalse(os.path.exists(os.path.join(home, '.claude')))


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
            for name in [f for f in files if f != '.git']:  # in a git worktree .git is a file naming the main checkout
                full = os.path.join(base, name)
                try:
                    with open(full, encoding='utf-8') as f:
                        text = f.read().lower()
                except UnicodeDecodeError:
                    continue
                hits += [f'{os.path.relpath(full, ROOT)}: {w}' for w in words if w in text]
        self.assertEqual(hits, [])


if __name__ == '__main__':
    unittest.main()
