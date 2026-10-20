"""What differs between macOS, Linux and Windows – file locks, processes, paths – and how this agentq is run and
restarted.
"""

import glob
import os
import re
import subprocess
import sys
import time
from shlex import quote as shlex_quote
from shutil import which as shutil_which


WINDOWS = os.name == 'nt'

if WINDOWS:
    import msvcrt
else:
    import fcntl

for _stream in (sys.stdout, sys.stderr):  # a Windows pipe is not UTF-8 by default: "🤖" and "ė" must not crash a print
    if _stream and hasattr(_stream, 'reconfigure') and (_stream.encoding or '').lower().replace('-', '') != 'utf8':
        _stream.reconfigure(encoding='utf-8', errors='replace')

LIB = os.path.dirname(os.path.realpath(__file__))  # tools/agentq_lib
SELF = os.path.join(os.path.dirname(LIB), 'agentq')  # the script every agent runs: tools/agentq
PACKAGE = os.path.dirname(os.path.dirname(LIB))  # the package: the skill, templates, config.example.json


def code_stamp():
    """When this agentq last changed: the script or any of its modules (a long-running loop restarts on a change)."""
    return max(os.path.getmtime(p) for p in [SELF, *glob.glob(os.path.join(glob.escape(LIB), '*.py'))])


def self_command():
    """How a worker's shell runs this agentq. Windows has no shebang: python and the script, in forward slashes, which
    Git Bash (Claude), PowerShell (Codex) and cmd all read; double quotes only when a path has a space."""
    if not WINDOWS:
        return shlex_quote(SELF)
    parts = [p.replace('\\', '/') for p in (sys.executable, SELF)]
    return ' '.join(f'"{p}"' if ' ' in p else p for p in parts)


def tool(name):
    """The command for gh, codex or open: AGENTQ_<NAME> when set (a .py file runs with this Python), else PATH."""
    given = os.environ.get(f'AGENTQ_{name.upper()}')
    if given is not None:
        return ([sys.executable, given] if given.endswith('.py') else [given]) if given else None
    found = shutil_which(name)
    return [found] if found else None


def lock_file(handle, wait=True):
    """Lock an open file against other processes until unlock_file or close. False: another process holds it."""
    if WINDOWS:
        while True:
            try:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                return True
            except OSError:
                if not wait:
                    return False
                time.sleep(0.05)
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        return True
    except OSError:
        return False


def unlock_file(handle):
    if WINDOWS:
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    handle.close()


def replace_file(tmp, path):
    """os.replace; on Windows a reader holding the file open makes it fail for a moment, so try again."""
    for attempt in range(50):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if not WINDOWS or attempt == 49:
                raise
            time.sleep(0.1)


def detached():
    """Popen arguments for a child that outlives this command and its session, in its own process group."""
    if WINDOWS:
        return {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS}
    return {'start_new_session': True}


def kill_tree(pid):
    """Stop a process started with detached() and everything it started."""
    if WINDOWS:
        subprocess.run(['taskkill', '/T', '/F', '/PID', str(pid)], capture_output=True)
    else:
        os.killpg(pid, 15)


def shell_script(script):
    """argv that runs a POSIX shell script: sh, or on Windows the bash of Git for Windows when there is one."""
    if not WINDOWS:
        return ['sh', '-c', script]
    bash = shutil_which('bash')
    return [bash, '-c', script] if bash else ['cmd', '/c', script]


def pid_alive(pid):
    if not WINDOWS:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
    import ctypes  # os.kill(pid, 0) would send CTRL_C_EVENT on Windows
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    code = ctypes.c_ulong()
    ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(handle)
    return code.value == 259  # STILL_ACTIVE


def session_parent():
    """The process that started this command – on Windows a restarted agentq is told its first one's parent."""
    return int(os.environ.get('AGENTQ_PARENT') or os.getppid())


def parent_gone(parent):
    """The session that started this command ended (POSIX: it was re-parented to init)."""
    return not pid_alive(parent) if WINDOWS else os.getppid() == 1


def command_lines(pattern):
    """Whether a running process's command line matches the pattern."""
    if WINDOWS:
        run = subprocess.run(['powershell', '-NoProfile', '-Command',
                              'Get-CimInstance Win32_Process | ForEach-Object { $_.CommandLine }'],
                             capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
        return any(re.search(pattern, line or '') for line in run.stdout.splitlines())
    return subprocess.run(['pgrep', '-f', pattern], capture_output=True).returncode == 0


APP_SESSIONS_DEFAULT = (os.path.join(os.environ.get('APPDATA') or '~', 'Claude', 'claude-code-sessions') if WINDOWS
                        else '~/Library/Application Support/Claude/claude-code-sessions')


def running_in():
    if os.environ.get('CODEX_THREAD_ID') or os.environ.get('CODEX_SANDBOX'):
        return 'codex'
    if os.environ.get('CLAUDECODE'):
        return 'claude'
    return None


def restart_if_updated(code, lock=None, detach=False):
    """agentq changed while this loop ran: carry on in the new version, without waking anyone. Windows has no exec:
    the new version runs as a child that this process waits for (a detached one is started and left), after this
    process let go of its lock."""
    if code_stamp() == code:
        return
    sys.stdout.flush()
    args = [sys.executable, SELF, *sys.argv[1:]]
    if not WINDOWS:
        os.execv(sys.executable, args)
    if lock:
        unlock_file(lock)
    os.environ['AGENTQ_PARENT'] = str(session_parent())  # the session, not this process, decides when to stop
    if detach:
        subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=sys.stdout, stderr=subprocess.STDOUT, **detached())
        sys.exit(0)
    sys.exit(subprocess.call(args))
