"""Host-wide resource slots for parallel content-design work.

Every heavy command (an Eventum run, a docs build, git on a shared
clone) runs through a slot so that parallel agents on one host never
exhaust its memory or collide on an exclusive resource.

    slot.py run [--mem MB] [--pool NAME ...] [--timeout S] [--wait S]
                [--json] -- CMD [ARG ...]
        Reserves MB of the host memory budget and every named exclusive
        pool, runs CMD, releases them. Exit status is CMD's (128+N when
        killed by signal N), 124 on timeout, 137 when the process tree
        exceeded 1.5 x MB (Linux), 75 when the slots were not free
        within --wait seconds, 130 when cancelled.
    slot.py status
        Memory budget, reservations and exclusive pools in use.

Slots are OS file locks under $CONTENT_DESIGN_STATE (default
~/.cache/content-design, %LOCALAPPDATA%\\content-design on Windows):
the OS releases them when a holder dies, so a crash never leaks one.
On Linux a command dies with the process that started it. The memory
budget is $CONTENT_DESIGN_MEM_MB or half the physical memory. Only
the command's own process tree is ever killed.

Standard library only; Python 3.9+.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

UNIT_MB = 256
DEFAULT_MEM_MB = 512
MEMORY_POOL = 'memory'
FAIR_AFTER_S = 30
WINDOWS = os.name == 'nt'
CANCEL = threading.Event()  # set by a signal handler: running commands stop

if WINDOWS:
    import msvcrt
else:
    import fcntl
    import resource
    try:  # one descriptor per held unit: lift the soft limit to the hard one
        _soft, _hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        _want = 65536 if _hard == resource.RLIM_INFINITY else min(_hard, 65536)
        if _soft != resource.RLIM_INFINITY and _soft < _want:
            resource.setrlimit(resource.RLIMIT_NOFILE, (_want, _hard))
    except (ValueError, OSError):
        pass


def state_dir():
    env = os.environ.get('CONTENT_DESIGN_STATE')
    if env:
        base = Path(env)
    elif WINDOWS:
        base = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'content-design'
    else:
        base = Path.home() / '.cache' / 'content-design'
    path = base / 'slots'
    path.mkdir(parents=True, exist_ok=True)
    return path


def physical_mb():
    if WINDOWS:
        import ctypes

        class Status(ctypes.Structure):
            _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong),
                        ('total', ctypes.c_ulonglong), ('avail', ctypes.c_ulonglong),
                        ('pt', ctypes.c_ulonglong), ('pa', ctypes.c_ulonglong),
                        ('vt', ctypes.c_ulonglong), ('va', ctypes.c_ulonglong),
                        ('ve', ctypes.c_ulonglong)]
        st = Status()
        st.length = ctypes.sizeof(Status)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
        return st.total // (1024 * 1024)
    return os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE') // (1024 * 1024)


def budget_mb():
    env = os.environ.get('CONTENT_DESIGN_MEM_MB')
    return int(env) if env else physical_mb() // 2


def capacity(pool):
    """Units of a pool: memory in UNIT_MB units, every other pool 1."""
    if pool == MEMORY_POOL:
        return max(1, budget_mb() // UNIT_MB)
    return 1


def _try_lock(fh):
    try:
        if WINDOWS:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(fh):
    try:
        if WINDOWS:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    fh.close()


def _lock_blocking(path):
    fh = open(path, 'a+')
    while not _try_lock(fh):
        time.sleep(0.05)
    return fh


class Lease:
    """Held slot units; released explicitly or by the OS on exit."""

    def __init__(self, handles, info_path):
        self._handles = handles
        self._info = info_path

    def release(self):
        for fh in self._handles:
            _unlock(fh)
        self._handles = []
        if self._info:
            try:
                self._info.unlink()
            except OSError:
                pass
            self._info = None


def _grab(pool, units, held):
    """Lock free units of `pool` into `held` until it holds `units` of them."""
    pdir = state_dir() / pool
    pdir.mkdir(exist_ok=True)
    have = sum(1 for p, _ in held if p == pool)
    for i in range(capacity(pool)):
        if have >= units:
            break
        path = pdir / ('u%d.lock' % i)
        if any(str(fh.name) == str(path) for _, fh in held):
            continue
        fh = open(path, 'a+')
        if _try_lock(fh):
            held.append((pool, fh))
            have += 1
        else:
            fh.close()
    return have >= units


def acquire(mem_mb=0, pools=(), wait=None, label=''):
    """Reserve memory and exclusive pools atomically; Lease or None.

    A request waits its turn: after FAIR_AFTER_S seconds it keeps the
    pool mutex and collects units as holders release them, so a large
    request is not starved by a stream of small ones.
    """
    need = [(p, 1) for p in sorted(set(pools))]
    if mem_mb:
        units = min(-(-mem_mb // UNIT_MB), capacity(MEMORY_POOL))
        need.append((MEMORY_POOL, units))
    root = state_dir()
    started = time.monotonic()
    deadline = None if wait is None else started + wait
    while True:
        mutex = _lock_blocking(root / '.mutex')
        held = []
        fair = time.monotonic() - started >= FAIR_AFTER_S
        try:
            while True:
                if all(_grab(pool, units, held) for pool, units in need):
                    info = root / ('holder-%d-%s.json' % (os.getpid(), uuid.uuid4().hex[:8]))
                    info.write_text(json.dumps({
                        'pid': os.getpid(), 'label': label, 'mem_mb': mem_mb,
                        'pools': sorted(set(pools)), 'since': time.time()}))
                    lease = Lease([fh for _, fh in held], info)
                    held = []
                    return lease
                out_of_time = deadline is not None and time.monotonic() >= deadline
                if not fair or out_of_time or CANCEL.is_set():
                    break
                time.sleep(0.5)
        finally:
            for _, fh in held:
                _unlock(fh)
            _unlock(mutex)
        if deadline is not None and time.monotonic() >= deadline or CANCEL.is_set():
            return None
        time.sleep(0.5)


def _pid_alive(pid):
    if WINDOWS:
        out = subprocess.run(['tasklist', '/FI', 'PID eq %d' % pid],
                             capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def status():
    root = state_dir()
    holders = []
    for path in sorted(root.glob('holder-*.json')):
        try:
            info = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if _pid_alive(info['pid']):
            holders.append(info)
        else:
            try:
                path.unlink()
            except OSError:
                pass
    used = sum(h['mem_mb'] for h in holders)
    return {'state_dir': str(root), 'memory_budget_mb': budget_mb(),
            'memory_reserved_mb': used, 'holders': holders}


def _tree_rss_mb(pgid):
    """RSS of every process in the group (Linux), MB; None elsewhere."""
    if not sys.platform.startswith('linux'):
        return None
    total = 0
    page = os.sysconf('SC_PAGE_SIZE')
    for entry in os.listdir('/proc'):
        if not entry.isdigit():
            continue
        try:
            with open('/proc/%s/stat' % entry) as fh:
                stat = fh.read().rsplit(')', 1)[1].split()
            if int(stat[2]) != pgid:
                continue
            with open('/proc/%s/statm' % entry) as fh:
                total += int(fh.read().split()[1]) * page
        except (OSError, IndexError, ValueError):
            continue
    return total / (1024 * 1024)


def _die_with_parent():
    """Linux: the child gets SIGKILL when the process that started it dies."""
    try:
        import ctypes
        ctypes.CDLL('libc.so.6', use_errno=True).prctl(1, signal.SIGKILL)  # PR_SET_PDEATHSIG
    except (OSError, AttributeError):
        pass


def _kill_tree(proc):
    if WINDOWS:
        if proc.poll() is None:
            subprocess.run(['taskkill', '/T', '/F', '/PID', str(proc.pid)],
                           capture_output=True)
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)  # members that outlived the leader
    except (ProcessLookupError, PermissionError):
        pass


def run(cmd, mem_mb=0, pools=(), timeout=None, wait=None, cwd=None,
        stdout=None, stderr=None, env=None):
    """Run cmd under a lease: exit, reason, wall_s, peak_mb, rss_mb series."""
    lease = acquire(mem_mb, pools, wait, label=' '.join(cmd)[:200])
    if lease is None:
        reason = 'cancelled' if CANCEL.is_set() else 'no-slot'
        return {'exit': 130 if reason == 'cancelled' else 75, 'reason': reason,
                'wall_s': 0.0, 'peak_mb': None, 'rss_mb': []}
    start = time.monotonic()
    kwargs = {'cwd': cwd, 'stdout': stdout, 'stderr': stderr, 'env': env}
    if WINDOWS:
        kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs['start_new_session'] = True
        if sys.platform.startswith('linux'):
            kwargs['preexec_fn'] = _die_with_parent
    reason, peak, series = 'exit', None, []
    proc = None
    try:
        proc = subprocess.Popen(cmd, **kwargs)
        limit = mem_mb * 1.5 if mem_mb else None
        while proc.poll() is None:
            try:
                proc.wait(0.5)
            except subprocess.TimeoutExpired:
                pass
            if proc.poll() is not None:
                break
            if CANCEL.is_set():
                reason = 'cancelled'
                _kill_tree(proc)
                break
            rss = None if WINDOWS else _tree_rss_mb(proc.pid)
            if rss is not None:
                peak = rss if peak is None else max(peak, rss)
                series.append((round(time.monotonic() - start, 1), round(rss)))
                if limit and rss > limit:
                    reason = 'memory'
                    _kill_tree(proc)
                    break
            if timeout and time.monotonic() - start > timeout:
                reason = 'timeout'
                _kill_tree(proc)
                break
        proc.wait()
    except BaseException:
        if proc is not None:
            _kill_tree(proc)
        raise
    finally:
        lease.release()
    rc = proc.returncode
    code = {'timeout': 124, 'memory': 137, 'cancelled': 130}.get(
        reason, 128 - rc if rc < 0 else rc)
    step = max(1, len(series) // 40)
    return {'exit': code, 'reason': reason,
            'wall_s': round(time.monotonic() - start, 2),
            'peak_mb': None if peak is None else round(peak),
            'rss_mb': [list(x) for x in series[::step]]}


def cancel_on_signals():
    """SIGINT, SIGTERM and SIGHUP stop running commands and pending waits."""
    def handler(_signum, _frame):
        CANCEL.set()
    for name in ('SIGINT', 'SIGTERM', 'SIGHUP', 'SIGBREAK'):
        sig = getattr(signal, name, None)
        if sig is not None:
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):
                pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run', help='run a command under slots')
    r.add_argument('--mem', type=int, default=0, help='memory to reserve, MB')
    r.add_argument('--pool', action='append', default=[], help='exclusive pool')
    r.add_argument('--timeout', type=float, help='seconds before the tree is killed')
    r.add_argument('--wait', type=float, help='seconds to wait for slots')
    r.add_argument('--json', action='store_true', help='summary on stderr')
    r.add_argument('command', nargs=argparse.REMAINDER)
    sub.add_parser('status', help='budget and holders')
    args = ap.parse_args()
    if args.cmd == 'status':
        print(json.dumps(status(), indent=1))
        return 0
    cmd = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not cmd:
        ap.error('no command given')
    cancel_on_signals()
    res = run(cmd, args.mem, args.pool, args.timeout, args.wait)
    if args.json or res['reason'] != 'exit':
        print('slot: ' + json.dumps({k: v for k, v in res.items() if k != 'rss_mb'}), file=sys.stderr)
    return res['exit']


if __name__ == '__main__':
    sys.exit(main())
