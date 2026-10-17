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


def issue(number, title, labels=(), updated='2026-01-01T10:00:00Z', comments=(), author='boss', **more):
    return {'number': number, 'title': title, 'labels': [{'name': n} for n in labels],
            'updatedAt': updated, 'comments': list(comments), 'author': {'login': author}, **more}


def said(login, body, at):
    return {'author': {'login': login}, 'body': body, 'createdAt': at, 'id': f'{login}-{at}'}


class Base(unittest.TestCase):
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
        run = subprocess.run([sys.executable, TOOL, '--config', self.config, *args],
                             capture_output=True, text=True, env=self.env(now))
        if ok:
            self.assertEqual(run.returncode, 0, run.stderr)
        return run

    def env(self, now='2026-01-02T12:00:00Z'):
        return {**os.environ, 'PATH': os.path.join(self.dir.name, 'bin') + os.pathsep + os.environ['PATH'],
                'FAKE_GH_LOG': self.log, 'FAKE_GH_FIXTURE': self.fixture, 'AGENTQ_NOW': now,
                'HOME': os.path.join(self.dir.name, 'home'), 'AGENTQ_CONFIG': ''}

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


def closed(number, title, at, labels=(), reason='COMPLETED'):
    return issue(number, title, labels, closedAt=at, stateReason=reason)


class TeamTest(Base):
    def setUp(self):
        super().setUp()
        with open(self.config) as f:
            cfg = json.load(f)
        cfg.update({'roles': ROLES, 'dispatcher': {'folder': os.path.join(self.dir.name, 'disp'), 'session': 'local_x'}})
        with open(self.config, 'w') as f:
            json.dump(cfg, f)

    def board(self, **extra):
        return {REPO: {'open': [
            issue(1, 'Old bug', ['prog']),
            issue(2, 'Urgent bug', ['prog', 'priority']),
            issue(3, 'Banner', ['design', 'doing'], comments=[said('boss', 'old', '2026-01-02T08:00:00Z'),
                                                              said('boss', 'recent', '2026-01-02T11:55:00Z')]),
            issue(4, 'Something new', comments=[said('bot', '🤖 programmer: noted', '2026-01-02T11:00:00Z')]),
            issue(5, 'Spam', author='stranger'),
            issue(6, 'Which colour?', ['prog', 'ask owner']),
        ], 'closed': [closed(10, 'Done A', '2026-01-02T09:00:00Z'), closed(11, 'Done B', '2026-01-02T10:00:00Z'),
                      closed(12, 'Dropped', '2026-01-02T10:00:00Z', reason='NOT_PLANNED'),
                      closed(13, 'Seen', '2026-01-02T10:00:00Z', ['checked: checker'])], **extra}}

    def test_watch_plan_assigns_classifies_batches_and_forwards_owner_words(self):
        self.data(self.board())
        first = self.run_tool('watch', '--once', now=T0).stdout
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
        self.assertIn(f'the owner wrote on {REPO}#3 (designer): send the output of '
                      f'`agentq brief {REPO}#3 --since 2026-01-02T12:00:30Z` to session local_d', second)
        self.assertIn(f'the owner answered on {REPO}#6: run `agentq assign {REPO}#6 programmer`', second)
        self.assertNotIn(f'assign {REPO}#2', second)
        third = self.run_tool('watch', '--once', now=T2).stdout
        self.assertNotIn('the owner', third)

    def test_watch_without_work_keeps_polling_and_a_second_watcher_steps_back(self):
        self.data({REPO: {'open': [issue(3, 'Banner', ['design', 'doing']), issue(7, 'Busy', ['prog', 'doing'])]}})
        self.assertIn('no work', self.run_tool('watch', '--once').stdout)
        with open(self.config + '.state.json') as f:
            self.assertEqual(json.load(f)['watch']['beat'], '2026-01-02T12:00:00Z')
        import fcntl
        with open(self.config + '.state.json.watch.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.assertIn('already running', self.run_tool('watch').stdout)
        self.data(self.board())
        self.assertIn('the owner wrote', self.run_tool('watch', '--once', now=T0).stdout)
        self.assertIn('agentq plan', self.run_tool('watch', '--once', now=T1).stdout)
        self.assertIn('no work', self.run_tool('watch', '--once', now=T2).stdout)
        self.assertIn('agentq plan', self.run_tool('watch', '--once', now='2026-01-02T12:32:00Z').stdout)
        with open(self.config + '.state.json', 'w') as f:
            json.dump({}, f)
        run = subprocess.run([sys.executable, TOOL, '--config', self.config, 'watch', '--interval', '0'],
                             capture_output=True, text=True, env=self.env(), timeout=20)
        self.assertIn('agentq plan', run.stdout)

    def test_assign_starts_a_free_role_queues_for_a_busy_one_and_sets_effort(self):
        self.data({REPO: {'open': [issue(3, 'Banner', ['design', 'doing']), issue(4, 'Icon', ['ask owner']),
                                   issue(8, 'Hard one', ['hard']), issue(9, 'Easy one')]}})
        out = self.run_tool('assign', '4', 'designer').stdout
        self.assertIn('queued (designer works on #3)', out)
        self.assertEqual(self.calls(['issue', 'edit'])[-1],
                         ['issue', 'edit', '4', '-R', REPO, '--add-label', 'design', '--remove-label', 'ask owner'])
        self.assertEqual(self.body(self.calls(['issue', 'comment'])[-1]), '🤖 dispatcher: queued for designer.')
        out = self.run_tool('assign', '8', 'programmer').stdout
        self.assertIn('1. set_session_effort local_p max', out)
        self.assertIn(f'2. send the output of `agentq brief {REPO}#8` to session local_p', out)
        self.assertEqual(self.calls(['issue', 'edit'])[-1], ['issue', 'edit', '8', '-R', REPO, '--add-label', 'prog',
                                                             '--add-label', 'doing'])
        self.data({REPO: {'open': [issue(9, 'Easy one')]}})
        self.assertIn('1. set_session_effort local_p high', self.run_tool('assign', '9', 'programmer').stdout)
        self.assertNotIn('set_session', self.run_tool('assign', '9', 'programmer').stdout)
        comments = len(self.calls(['issue', 'comment']))
        self.run_tool('assign', '4', 'designer', '--queue')
        self.assertEqual(len(self.calls(['issue', 'comment'])), comments)
        self.assertEqual(self.calls(['issue', 'edit'])[-1], ['issue', 'edit', '4', '-R', REPO, '--add-label', 'design'])

    def test_brief_gives_the_owners_words_verbatim_and_screenshots_as_files(self):
        shot = os.path.join(self.dir.name, 'pic.png')
        with open(shot, 'wb') as f:
            f.write(b'\x89PNG fake')
        img = f'<p><img src="file://{shot}" alt="x"></p>'
        self.data({'api': {
            f'repos/{REPO}/issues/3': {'title': 'Banner', 'body': 'Make it  *bold*\nsee ![x](u)', 'body_html': img,
                                       'labels': [{'name': 'design'}], 'user': {'login': 'boss'}},
            f'repos/{REPO}/issues/3/comments': [
                {'user': {'login': 'boss'}, 'body': 'first words', 'body_html': '', 'created_at': '2026-01-02T08:00:00Z'},
                {'user': {'login': 'bot'}, 'body': 'agent noise', 'body_html': img, 'created_at': '2026-01-02T09:00:00Z'},
                {'user': {'login': 'boss'}, 'body': 'and red', 'body_html': img, 'created_at': '2026-01-02T10:00:00Z'}]}})
        out = self.run_tool('brief', '3').stdout
        self.assertIn('Task acme/app#3 for designer', out)
        self.assertIn('Make it  *bold*\nsee ![x](u)', out)
        self.assertIn('first words', out)
        self.assertIn('and red', out)
        self.assertNotIn('agent noise', out)
        self.assertIn('--no-lesson', out)
        files = [l for l in out.splitlines() if l.endswith('.png')]
        self.assertEqual(len(files), 2)
        self.assertEqual(open(files[0], 'rb').read(), b'\x89PNG fake')
        news = self.run_tool('brief', '3', '--since', '2026-01-02T10:00:00Z').stdout
        self.assertIn('and red', news)
        self.assertNotIn('first words', news)
        self.assertNotIn('bold', news)

    def test_route_relabels_and_keeps_the_last_five_lessons(self):
        for n in range(20, 27):
            self.data({REPO: {'open': [issue(n, f'Logo {n}', ['prog', 'doing'])]}})
            self.run_tool('route', str(n), 'designer', 'a logo')
        self.assertEqual(self.calls(['issue', 'edit'])[-1], ['issue', 'edit', '26', '-R', REPO, '--add-label', 'design',
                                                             '--remove-label', 'prog', '--remove-label', 'doing'])
        self.assertEqual(self.body(self.calls(['issue', 'comment'])[-1]), '🤖 programmer: → designer. a logo')
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
        self.data({**self.board(next=50)})
        out = self.run_tool('batch', 'reviewer').stdout
        self.assertIn(f'{REPO}#50 created: reviewer checks #10.', out)
        made = self.calls(['issue', 'create'])[-1]
        self.assertIn('Check: #10', made)
        self.assertEqual(made[made.index('--label') + 1:], ['reviewer', '--label', 'check batch', '--label', 'doing'])
        self.assertIn(f'Commit: {head}', self.body(made))
        self.assertNotIn('#11', self.body(made))
        out = self.run_tool('batch', 'checker').stdout
        self.assertIn('1. set_session_model local_c mid', out)
        body = self.body(self.calls(['issue', 'create'])[-1])
        self.assertIn('- #10 Done A\n- #11 Done B', body)
        self.data({REPO: {'open': [issue(50, 'Check: #10 #11', ['check', 'check batch', 'doing'], body=body)]}})
        self.run_tool('checked', '50', 'all fine')
        edits = self.calls(['issue', 'edit'])
        self.assertIn(['issue', 'edit', '10', '-R', REPO, '--add-label', 'checked: checker'], edits)
        self.assertIn(['issue', 'edit', '11', '-R', REPO, '--add-label', 'checked: checker'], edits)
        self.assertEqual(self.body(self.calls(['issue', 'comment'])[-1]), '🤖 checker: checked #10 #11. all fine')
        self.assertEqual(self.calls(['issue', 'close'])[-1], ['issue', 'close', '50', '-R', REPO])

    def test_done_comments_drops_working_and_closes(self):
        self.data({REPO: {'open': [issue(7, 'Bug', ['design', 'doing'])]}})
        self.run_tool('done', '7', 'fixed the colour; checked on a phone')
        self.assertEqual(self.body(self.calls(['issue', 'comment'])[-1]), '🤖 designer: fixed the colour; checked on a phone')
        self.assertEqual(self.calls(['issue', 'edit'])[-1], ['issue', 'edit', '7', '-R', REPO, '--remove-label', 'doing'])
        self.assertEqual(self.calls(['issue', 'close'])[-1], ['issue', 'close', '7', '-R', REPO])

    def test_health_reports_to_one_issue_and_closes_it_when_well(self):
        stale = issue(7, 'Stuck', ['prog', 'doing'], updated='2026-01-01T00:00:00Z')
        self.data({REPO: {'open': [stale], 'next': 60}})
        out = self.run_tool('health').stdout
        self.assertIn('the watcher is not running', out)
        self.assertIn(f"{REPO}#7 is 'doing' but nothing happened for over 24 h", out)
        self.assertIn('agent health', self.calls(['issue', 'create'])[-1])
        report = issue(60, 'Agent team health', ['agent health'])
        self.data({REPO: {'open': [stale, report]}})
        self.run_tool('health')
        self.assertEqual(self.calls(['issue', 'comment'])[-1][2], '60')
        self.data({REPO: {'open': [report]}})
        with open(self.config + '.state.json', 'w') as f:
            json.dump({'watch': {'beat': '2026-01-02T11:59:00Z'}}, f)
        import fcntl
        with open(self.config + '.state.json.watch.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
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
        out = self.run_tool('setup').stdout
        made = [c[2] for c in self.calls(['label', 'create'])]
        for name in ('prog', 'design', 'check', 'checked: checker', 'priority', "waits for owner's word", 'check batch'):
            self.assertIn(name, made)
        self.assertNotIn('checked: designer', made)
        self.assertIn('designer | design | programmer | - | - | - | - | no | local_d', out)
        disp = os.path.join(self.dir.name, 'disp')
        claude = open(os.path.join(disp, 'CLAUDE.md')).read()
        self.assertIn(f'`{os.path.realpath(TOOL)} watch`', claude)
        self.assertNotIn('{{', claude)
        self.assertTrue(os.path.exists(os.path.join(disp, 'examples', 'README.md')))
        self.assertEqual(os.path.realpath(os.path.join(disp, '.agentq.json')), os.path.realpath(self.config))
        self.assertIn('## designer', open(os.path.join(disp, 'roles.md')).read())

    def test_role_adds_the_ready_made_marketer_and_sets_the_dispatcher_session(self):
        self.data({REPO: {'labels': []}})
        shot = os.path.join(self.dir.name, 'ad.png')
        with open(shot, 'wb') as f:
            f.write(b'png')
        self.run_tool('role', 'marketer', '--session', 'local_m', '--model', 'mid', '--shot', shot)
        self.run_tool('role', 'dispatcher', '--session', 'local_x2')
        with open(self.config) as f:
            cfg = json.load(f)
        marketer = cfg['roles'][-1]
        self.assertEqual((marketer['role'], marketer['session'], marketer['model']), ('marketer', 'local_m', 'mid'))
        self.assertIn('public or paid', marketer['description'])
        self.assertEqual(cfg['dispatcher']['session'], 'local_x2')
        self.assertIn('marketer', [c[2] for c in self.calls(['label', 'create'])])
        self.assertTrue(os.path.exists(os.path.join(self.dir.name, 'disp', 'examples', 'marketer-1.png')))
        self.assertIn('reference screenshot: examples/marketer-1.png', self.run_tool('roles').stdout)
        self.run_tool('role', 'checker', '--remove')
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
        self.assertIn(f'🤖 programmer: → {OTHER}#9', closing)

    def test_split_creates_the_other_part_with_a_link_back(self):
        self.run_tool('link', OTHER, 'the website')
        self.data({REPO: {'open': [issue(4, 'Launch', ['prog', 'doing'])]}, OTHER: {'next': 12}})
        self.assertIn(f'{OTHER}#12 created from {REPO}#4', self.run_tool('split', '4', OTHER, 'Launch page', 'a page for the launch').stdout)
        made = self.calls(['issue', 'create'])[-1]
        self.assertEqual(self.body(made), f'🤖 programmer: a page for the launch\n\nSplit from {REPO}#4.')
        self.assertEqual(self.body(self.calls(['issue', 'comment'])[-1]), f'🤖 programmer: the part for {OTHER} is {OTHER}#12.')
        self.assertEqual(self.calls(['issue', 'edit']), [])


class InitTest(Base):
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
        self.assertEqual(os.path.realpath(os.path.join(project, '.claude', 'skills', 'agent-team')),
                         os.path.join(ROOT, 'skill', 'agent-team'))
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
            for name in files:
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
