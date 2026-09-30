"""Host-wide resource slots for parallel content-design work.

Every heavy command (an Eventum run, a docs build, git on a shared
clone) runs through a slot so that parallel agents on one host never
exhaust its memory or collide on an exclusive resource.

    slot.py run [--mem MB] [--pool NAME ...] [--timeout S] [--wait S]
                [--json] -- CMD [ARG ...]
        Reserves MB of the host memory budget and every named exclusive
        pool, runs CMD, releases them. Exit status is CMD's, or 124 on
        timeout, 137 when the process tree exceeded 1.5 x MB (Linux),
        75 when the slots were not free within --wait seconds.
    slot.py status
        Memory budget, reservations and exclusive pools in use.

Slots are OS file locks under $CONTENT_DESIGN_STATE (default
~/.cache/content-design, %LOCALAPPDATA%\\content-design on Windows):
the OS releases them when a holder dies, so a crash never leaks one.
The memory budget is $CONTENT_DESIGN_MEM_MB or half the physical
memory. Only the command's own process tree is ever killed.

Standard library only; Python 3.9+.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

UNIT_MB = 64
DEFAULT_MEM_MB = 512
MEMORY_POOL = 'memory'
WINDOWS = os.name == 'nt'

if WINDOWS:
    import msvcrt
else:
    import fcntl


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


def _grab(pool, units):
    """All `units` free units of `pool`, or None; caller holds the mutex."""
    pdir = state_dir() / pool
    pdir.mkdir(exist_ok=True)
    got = []
    for i in range(capacity(pool)):
        fh = open(pdir / ('u%d.lock' % i), 'a+')
        if _try_lock(fh):
            got.append(fh)
            if len(got) == units:
                return got
        else:
            fh.close()
    for fh in got:
        _unlock(fh)
    return None


def acquire(mem_mb=0, pools=(), wait=None, label=''):
    """Reserve memory and exclusive pools atomically; Lease or None."""
    need = [(p, 1) for p in sorted(set(pools))]
    if mem_mb:
        units = min(-(-mem_mb // UNIT_MB), capacity(MEMORY_POOL))
        need.append((MEMORY_POOL, units))
    root = state_dir()
    deadline = None if wait is None else time.monotonic() + wait
    while True:
        mutex = _lock_blocking(root / '.mutex')
        held = []
        try:
            for pool, units in need:
                got = _grab(pool, units)
                if got is None:
                    break
                held.extend(got)
            else:
                info = root / ('holder-%d-%s.json' % (os.getpid(), uuid.uuid4().hex[:8]))
                info.write_text(json.dumps({
                    'pid': os.getpid(), 'label': label, 'mem_mb': mem_mb,
                    'pools': sorted(set(pools)), 'since': time.time()}))
                return Lease(held, info)
            for fh in held:
                _unlock(fh)
        finally:
            _unlock(mutex)
        if deadline is not None and time.monotonic() >= deadline:
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
    for entry in os.listdir('/proc'):
        if not entry.isdigit():
            continue
        try:
            with open('/proc/%s/stat' % entry) as fh:
                stat = fh.read().rsplit(')', 1)[1].split()
            if int(stat[2]) != pgid:
                continue
            with open('/proc/%s/statm' % entry) as fh:
                total += int(fh.read().split()[1]) * os.sysconf('SC_PAGE_SIZE')
        except (OSError, IndexError, ValueError):
            continue
    return total / (1024 * 1024)


def _kill_tree(proc):
    if proc.poll() is not None:
        return
    if WINDOWS:
        subprocess.run(['taskkill', '/T', '/F', '/PID', str(proc.pid)],
                       capture_output=True)
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def run(cmd, mem_mb=0, pools=(), timeout=None, wait=None, cwd=None,
        stdout=None, stderr=None):
    """Run cmd under a lease; dict with exit, reason, wall_s, peak_mb."""
    lease = acquire(mem_mb, pools, wait, label=' '.join(cmd)[:200])
    if lease is None:
        return {'exit': 75, 'reason': 'no-slot', 'wall_s': 0.0, 'peak_mb': None}
    start = time.monotonic()
    kwargs = {'cwd': cwd, 'stdout': stdout, 'stderr': stderr}
    if WINDOWS:
        kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs['start_new_session'] = True
    reason, peak = 'exit', None
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
            if not WINDOWS:
                rss = _tree_rss_mb(proc.pid)
                if rss is not None:
                    peak = rss if peak is None else max(peak, rss)
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
    code = {'timeout': 124, 'memory': 137}.get(reason, proc.returncode)
    return {'exit': code, 'reason': reason,
            'wall_s': round(time.monotonic() - start, 2),
            'peak_mb': None if peak is None else round(peak)}


def _on_signal(signum, _frame):
    raise KeyboardInterrupt


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
    if not WINDOWS:
        signal.signal(signal.SIGTERM, _on_signal)
    try:
        res = run(cmd, args.mem, args.pool, args.timeout, args.wait)
    except KeyboardInterrupt:
        return 130
    if args.json or res['reason'] != 'exit':
        print('slot: ' + json.dumps(res), file=sys.stderr)
    return res['exit']


if __name__ == '__main__':
    sys.exit(main())
