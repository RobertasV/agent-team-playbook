"""The command line: every agentq command and its options."""

import argparse
import sys

from .base import Fail, number
from .defaults import EFFORTS, MODES
from .config import find_config, load_config
from .health import cmd_health
from .watch import cmd_held, cmd_nudge, cmd_watch
from .brief import cmd_brief
from .tasks import (
    cmd_ask, cmd_assign, cmd_batch, cmd_check, cmd_checked, cmd_defer, cmd_done, cmd_handover, cmd_next, cmd_queue,
    cmd_route, cmd_take, cmd_wait, note_finished
)
from .links import cmd_link, cmd_move, cmd_open, cmd_split
from .install import cmd_init, cmd_setup
from .team import (
    cmd_live, cmd_pause, cmd_resume, cmd_role, cmd_roles, cmd_scale, cmd_stats, cmd_teach, cmd_team, cmd_tests,
    cmd_workers
)


def main(argv=None):
    p = argparse.ArgumentParser(prog='agentq', description='Task queue of an agent team on GitHub issues.')
    p.add_argument('--config', help='config file (default: AGENTQ_CONFIG, the nearest .agentq.json, ~/.config/agentq/config.json)')
    sub = p.add_subparsers(dest='cmd')
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--config', default=argparse.SUPPRESS, help='config file (also accepted before the command)')
    add_parser = sub.add_parser
    sub.add_parser = lambda *a, **k: add_parser(*a, parents=[common], **k)
    q = sub.add_parser('queue', help="the queue and the owner's new comments")
    q.add_argument('--all', action='store_true', help='also count skipped issues by label')
    q.add_argument('--peek', action='store_true', help='do not move the "since" mark')
    sub.add_parser('take', help='start an issue').add_argument('issue')
    a = sub.add_parser('ask', help='ask the owner; the issue leaves the queue')
    a.add_argument('issue')
    a.add_argument('text')
    d = sub.add_parser('defer', help='the owner deferred it')
    d.add_argument('issue')
    d.add_argument('text', nargs='?')
    w = sub.add_parser('wait', help='wait for an issue in another project')
    w.add_argument('issue')
    w.add_argument('other')
    c = sub.add_parser('check', help='find inconsistent states')
    c.add_argument('--fix', action='store_true')
    wt = sub.add_parser('watch', help='poll the board every minute; print a plan and exit when there is work')
    wt.add_argument('--once', action='store_true', help='poll once')
    wt.add_argument('--interval', type=float, help='seconds between polls (default: poll_seconds)')
    wt.add_argument('--max-minutes', type=float, help='give up after this long')
    wt.add_argument('--wake', action='store_true', help=argparse.SUPPRESS)  # the detached watcher of a Codex dispatcher
    nx = sub.add_parser('next', help="take the role's next task and print its brief (every worker gets work this way)")
    nx.add_argument('role', nargs='?', help='one role; without it, any role that pulls (one worker for the team)')
    nx.add_argument('--wait', action='store_true', help='Claude: wait without tokens until there is one (in Codex '
                                                         'a waiting command costs tokens: it ends its turn instead)')
    nx.add_argument('--max-minutes', type=float, help='with --wait: give up after this long (default: wait until there is one)')
    nx.add_argument('--as', dest='who', help='which worker takes it (default: this Claude session, or <host>-<role>)')
    s = sub.add_parser('assign', help='give an issue to a role (working if the role is free, else queued)')
    s.add_argument('issue')
    s.add_argument('role')
    s.add_argument('--queue', action='store_true', help='only the role label: no comment, no start (sorting at setup)')
    s.add_argument('--unpark', action='store_true', help='the owner wrote on a set-aside task: drop deferred/waiting labels')
    s.add_argument('--only', choices=('claude', 'codex'), help="the owner's word: only this team may take the task")
    s.add_argument('--session', help="the owner's word: this Claude session of the role takes it, even a resting one")
    b = sub.add_parser('brief', help="the issue's title, text, the owner's comments verbatim and screenshots as files")
    b.add_argument('issue')
    b.add_argument('--since', help="only the owner's comments from this time on")
    ho = sub.add_parser('handover', help='three tries and it still fails: the other team (Claude ↔ Codex) takes it')
    ho.add_argument('issue')
    ho.add_argument('text', help='what you tried and where it stands')
    ho.add_argument('--tries', type=int, default=3)
    ho.add_argument('--owner', action='store_true', help="not tries: the owner's word keeps it for the other team")
    r = sub.add_parser('route', help='not mine: give it to another role (records a lesson for the dispatcher)')
    r.add_argument('issue')
    r.add_argument('role')
    r.add_argument('text', nargs='?')
    r.add_argument('--no-lesson', action='store_true', help='a hand-over, not a mistake: record no lesson')
    t = sub.add_parser('teach', help='a rule for the dispatcher, e.g. "banners → designer"')
    t.add_argument('rule')
    t.add_argument('--owner', action='store_true', help='the owner said it')
    t.add_argument('--issue', help='ask a contradiction on this issue instead of a new one')
    sub.add_parser('roles', help='the roles, rules and lessons the dispatcher reads')
    sub.add_parser('pause', help='pause the team: the watcher stays up but sends nothing').add_argument('text', nargs='?')
    sub.add_parser('resume', help='end a pause')
    mv = sub.add_parser('move', help='all of it belongs to a linked project: move the issue there')
    mv.add_argument('issue')
    mv.add_argument('repo')
    mv.add_argument('text', nargs='?')
    mv.add_argument('--no-lesson', action='store_true')
    sp = sub.add_parser('split', help='a part belongs to a linked project: a new issue there, linked to this one')
    sp.add_argument('issue')
    sp.add_argument('repo')
    sp.add_argument('title')
    sp.add_argument('text')
    op = sub.add_parser('open', help='a new task for a role in this project, e.g. a finding')
    op.add_argument('role')
    op.add_argument('title')
    op.add_argument('text')
    op.add_argument('-R', '--repo')
    op.add_argument('--as', dest='who', help='the role that opens it (shown as 🤖 <role>:)')
    ln = sub.add_parser('link', help='share tasks with another project (sharing is on while a link exists)')
    ln.add_argument('repo')
    ln.add_argument('about', nargs='?', help='what belongs there')
    ln.add_argument('--remove', action='store_true')
    dn = sub.add_parser('done', help='fixed: comment, drop the working label, close')
    dn.add_argument('issue')
    dn.add_argument('text')
    bt = sub.add_parser('batch', help='create the batch issue for a checker-mode role')
    bt.add_argument('role')
    bt.add_argument('-R', '--repo')
    bt.add_argument('--now', action='store_true', help='even if fewer than N and younger than the wait')
    ck = sub.add_parser('checked', help="a checker's batch is done: label every listed issue, close the batch")
    ck.add_argument('issue')
    ck.add_argument('text', nargs='?')
    sub.add_parser('health', help='watcher alive, no stale work; problems go to one health issue')
    hd = sub.add_parser('held', help="the dispatcher's check of a role's session that holds a task")
    hd.add_argument('issue')
    hd.add_argument('--running', required=True, help="the session's isRunning (get_session)")
    hd.add_argument('--last', required=True, help="the session's lastActivityAt (get_session)")
    ng = sub.add_parser('nudge', help='the reminder for an idle session that holds a task')
    ng.add_argument('issue')
    ng.add_argument('--last')
    su = sub.add_parser('setup', help='check access, write default roles, create labels and the dispatcher folder')
    su.add_argument('--checkout', help='the project folder (for path filters and pinned commits)')
    su.add_argument('--dispatcher-dir', help='the dispatcher folder (default ~/agent-team/<owner>-<repo>-dispatcher)')
    su.add_argument('--group', help="the id of the app's sidebar group holding the team's sessions")
    ro = sub.add_parser('role', help='add or change a role ("dispatcher" sets the dispatcher\'s session)')
    ro.add_argument('name')
    ro.add_argument('--label')
    ro.add_argument('--mode', choices=MODES)
    ro.add_argument('--agent', help='claude (the dispatcher sends tasks), codex (its workers pull them), or both (they compete)')
    ro.add_argument('--n', type=int)
    ro.add_argument('--hours', type=number)
    ro.add_argument('--paths', help='comma-separated path prefixes or globs (checker mode)')
    ro.add_argument('--model')
    ro.add_argument('--codex-model', help="the model this role's Codex workers start on (config codex_model otherwise)")
    ro.add_argument('--release-model')
    ro.add_argument('--effort', choices=EFFORTS)
    ro.add_argument('--hard-effort', choices=EFFORTS)
    ro.add_argument('--merge', choices=('yes', 'no'))
    ro.add_argument('--session')
    ro.add_argument('--sessions', help='several sessions for one role (a pool), comma-separated')
    ro.add_argument('--add-session', action='append', help='add one session to the role\'s pool (repeat)')
    te = sub.add_parser('tests', help='test mode: per-task or batched (the watcher runs the full suite every N tasks)')
    te.add_argument('mode', nargs='?', choices=('per-task', 'batched'))
    st = sub.add_parser('stats', help='who works better: Claude or Codex (tasks, time, problems found later)')
    st.add_argument('--days', type=float, default=30)
    cw = sub.add_parser('codex-workers', help='open one Codex worker task per role (prefilled; the owner presses Send)')
    cw.add_argument('count', type=int, nargs='?', default=1, help='workers per role (default 1)')
    cw.add_argument('--role', help='only this role, e.g. "3 Codex programmers": codex-workers 3 --role programmer')
    lv = sub.add_parser('live', help="which role restarts the owner's running copy, when and how (--off: none)")
    lv.add_argument('role', nargs='?')
    lv.add_argument('command', nargs='?', help='the restart command; {sha} is the commit')
    lv.add_argument('--when', choices=('go', 'checked'), default='go',
                    help='go: after GO, on the last green commit; checked: after every check, red tests or not')
    lv.add_argument('--off', action='store_true')
    tm = sub.add_parser('team', help='move the whole team (dispatcher and roles) to claude or to codex')
    tm.add_argument('agent', choices=('claude', 'codex', 'both'))
    sc = sub.add_parser('scale', help='how many sessions of a role work in parallel; sessions are kept, never deleted')
    sc.add_argument('role')
    sc.add_argument('count', type=int)
    ro.add_argument('--description')
    ro.add_argument('--example', action='append', help='an example task (repeat for 2–3)')
    ro.add_argument('--shot', action='append', help='a reference screenshot, copied into the dispatcher\'s examples/')
    ro.add_argument('--remove', action='store_true')
    ini = sub.add_parser('init', help='install the team into this project only: config, skill link, git exclude')
    ini.add_argument('--owner', action='append', required=True, help="the owner's GitHub login (repeat for more)")
    ini.add_argument('--repo', help='owner/name (default: from the git remote "origin")')
    ini.add_argument('--project', help='the project folder (default: here)')
    ini.add_argument('--codex', action='store_true', help='also point AGENTS.md at the skill (codex and other agents)')
    ini.add_argument('--second', action='store_true', help='the team already runs on another computer for this project: '
                                                         'this one serves only its own sessions and Codex workers')
    for name, parser in sub.choices.items():  # agents add `--as <role>` out of habit: accepted everywhere
        if name not in ('next', 'open') and not any('--as' in a.option_strings for a in parser._actions):
            parser.add_argument('--as', dest='who', help=argparse.SUPPRESS)
    opts = p.parse_args(argv)
    if not opts.cmd:  # plain `agentq`: what it can do
        p.print_help()
        return 0
    if opts.cmd == 'init':
        try:
            cmd_init(opts)
            return 0
        except Fail as e:
            print(f'agentq: {e}', file=sys.stderr)
            return 1
    commands = {'queue': cmd_queue, 'take': cmd_take, 'ask': cmd_ask, 'defer': cmd_defer, 'wait': cmd_wait,
                'check': cmd_check, 'watch': cmd_watch, 'assign': cmd_assign, 'brief': cmd_brief, 'route': cmd_route, 'handover': cmd_handover,
                'teach': cmd_teach, 'roles': cmd_roles, 'done': cmd_done, 'batch': cmd_batch, 'checked': cmd_checked,
                'health': cmd_health, 'setup': cmd_setup, 'role': cmd_role, 'move': cmd_move, 'split': cmd_split, 'open': cmd_open,
                'link': cmd_link, 'scale': cmd_scale, 'stats': cmd_stats, 'codex-workers': cmd_workers, 'team': cmd_team, 'live': cmd_live, 'next': cmd_next, 'tests': cmd_tests, 'pause': cmd_pause, 'resume': cmd_resume, 'held': cmd_held, 'nudge': cmd_nudge}
    try:
        cfg = load_config(find_config(opts.config))
        code = commands[opts.cmd](cfg, opts) or 0
        if code == 0 and opts.cmd in ('done', 'ask', 'route', 'handover', 'wait', 'move', 'checked'):
            note_finished(cfg)
        return code
    except Fail as e:
        print(f'agentq: {e}', file=sys.stderr)
        return 1
