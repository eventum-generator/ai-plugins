"""Test captures of an Eventum generator: bounded copies run in parallel.

    capture.py doctor [--eventum BIN]
        Eventum version (2.8+ required), its Python, gh, slot budget.
    capture.py run GENERATOR --out DIR [--set author|review]
        The run set of the acceptance protocol, in parallel under host
        slots: background, anomaly, short-interval, long and the
        one-record-per-timestamp pair. Writes DIR/manifest.json.
    capture.py one GENERATOR --out DIR --name NAME [--days N]
                   [--mode on|off|as-is] [--interval H]
        One bounded run.
    capture.py live GENERATOR --out DIR [--seconds 90] [--scale 20]
        Live mode at scaled rates: lag behind the wall clock, order,
        bursts, log. Writes DIR/live.json.

The shipped generator is never modified: every run works on a copy in
which every input is bounded to the window (time_patterns pattern files
and cron: start and end; linspace: shifted into the window; timer:
start and repeat), the anomaly parameters are set, and the output is
one local file. YAML is read with the Python of the Eventum
installation ($EVENTUM_PYTHON overrides); copies are written as JSON,
which is valid YAML. SIGINT, SIGTERM and SIGHUP stop every run.

Standard library only; Python 3.9+.
"""

import argparse
import concurrent.futures
import gzip
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import slot  # noqa: E402

MIN_VERSION = (2, 8, 0)
WINDOW_START = '2026-08-31T00:00:00+00:00'  # a Monday midnight UTC
UNIT_SECONDS = {'weeks': 604800, 'days': 86400, 'hours': 3600, 'minutes': 60,
                'seconds': 1, 'milliseconds': 0.001, 'microseconds': 1e-6}
TS_TEMPLATE = '{"t": {{ timestamp.isoformat() | tojson }}, "g": {{ tags | list | tojson }}}'
# The memory baseline drops carrier timestamps as the generator mostly does.
BASE_TEMPLATE = ('{%- if tags | select("in", params._carrier) | list -%}{%- do dispatch.drop() -%}'
                 '{%- else -%}{"t": {{ timestamp.isoformat() | tojson }}}{%- endif -%}')
SETS = {
    'author': {'off': 2, 'on': 2},
    'review': {'off': 3, 'on': 3},
}
CHILD_ENV = dict(os.environ, NO_COLOR='1', TERM='dumb')
SCHEMA = 2  # manifest layout read by measure.py
LIVE_CRON = '* * * * * */20'  # schedules replaced in the live check: a run every 20 s


class CaptureError(Exception):
    pass


# --- time ------------------------------------------------------------------

def parse_iso(value):
    """Aware datetime from ISO 8601 (Z, +HHMM, comma or long fractions), or None."""
    if not isinstance(value, str):
        return None
    s = value.strip().replace(',', '.')
    if 'T' not in s and ' ' in s:
        s = s.replace(' ', 'T', 1)
    s = re.sub(r'[Zz]$', '+00:00', s)
    s = re.sub(r'([+-]\d\d)(\d\d)$', r'\1:\2', s)
    s = re.sub(r'\.(\d{1,6})\d*', lambda m: '.' + m.group(1).ljust(6, '0'), s)
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    return d if d.tzinfo else None


def parse_anchor(value, ref):
    """An oscillator anchor: ISO with offset, or a time of day (today in UTC, as
    Eventum reads it with --timezone UTC) placed on the date of `ref`."""
    d = parse_iso(value)
    if d is not None:
        return d
    m = re.fullmatch(r'\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*', str(value)) if value is not None else None
    if not m:
        return None
    base = ref.astimezone(timezone.utc)
    return base.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=int(m.group(3) or 0),
                        microsecond=0)


def iso(d):
    return d.isoformat()


# --- environment -----------------------------------------------------------

def find_eventum(explicit=None):
    cand = explicit or os.environ.get('EVENTUM_BIN') or shutil.which('eventum')
    if not cand:
        raise CaptureError('eventum not found: install eventum-generator or pass --eventum')
    return cand


def _has_yaml(py):
    return subprocess.run([py, '-c', 'import yaml'], capture_output=True).returncode == 0


def eventum_python(eventum):
    """The interpreter of the Eventum installation (it has PyYAML)."""
    env = os.environ.get('EVENTUM_PYTHON')
    if env:
        return env
    real = Path(os.path.realpath(eventum))
    cands = []
    try:
        first = real.read_bytes()[:512].split(b'\n', 1)[0]
    except OSError:
        first = b''
    if first.startswith(b'#!'):
        cands.append(first[2:].decode('utf-8', 'replace').strip().split()[0])
    for name in ('python', 'python3', 'python.exe'):
        cands.append(str(real.parent / name))
    uv = shutil.which('uv')
    if uv:
        out = subprocess.run([uv, 'tool', 'dir'], capture_output=True, text=True)
        if out.returncode == 0 and out.stdout.strip():
            tool = Path(out.stdout.strip()) / 'eventum-generator'
            cands += [str(tool / 'bin' / 'python'), str(tool / 'Scripts' / 'python.exe')]
    pipx = Path.home() / '.local' / 'pipx' / 'venvs' / 'eventum-generator'
    cands += [str(pipx / 'bin' / 'python'), str(pipx / 'Scripts' / 'python.exe')]
    for cand in cands:
        if cand and os.path.exists(cand) and _has_yaml(cand):
            return cand
    raise CaptureError('no Python with PyYAML for %s: set EVENTUM_PYTHON' % eventum)


def eventum_version(eventum):
    out = subprocess.run([eventum, '--version'], capture_output=True, text=True, env=CHILD_ENV)
    m = re.search(r'App version:\s*(\d+)\.(\d+)\.(\d+)', out.stdout + out.stderr)
    if not m:
        raise CaptureError('cannot read the version of %s' % eventum)
    return tuple(int(x) for x in m.groups())


def doctor(eventum=None):
    report = {'python': sys.version.split()[0], 'problems': []}
    try:
        ev = find_eventum(eventum)
        report['eventum'] = ev
        ver = eventum_version(ev)
        report['eventum_version'] = '.'.join(map(str, ver))
        if ver < MIN_VERSION:
            report['problems'].append('Eventum %s < 2.8.0: `uv tool upgrade eventum-generator`'
                                      % report['eventum_version'])
        report['eventum_python'] = eventum_python(ev)
    except CaptureError as exc:
        report['problems'].append(str(exc))
    gh = shutil.which('gh')
    report['gh'] = bool(gh) and subprocess.run([gh, 'auth', 'status'], capture_output=True).returncode == 0
    st = slot.status()
    report['memory_budget_mb'] = st['memory_budget_mb']
    report['memory_reserved_mb'] = st['memory_reserved_mb']
    report['ok'] = not report['problems']
    return report


# --- YAML through the Eventum interpreter ----------------------------------

_LOADER = r'''
import json, sys, yaml, datetime
def conv(o):
    if isinstance(o, (datetime.datetime, datetime.date)):
        return o.isoformat()
    raise TypeError(repr(o))
out = {}
for p in sys.argv[1:]:
    with open(p, encoding='utf-8') as fh:
        out[p] = yaml.safe_load(fh)
print(json.dumps(out, default=conv))
'''


def load_yaml(py, paths):
    res = subprocess.run([py, '-c', _LOADER] + [str(p) for p in paths],
                         capture_output=True, text=True)
    if res.returncode:
        lines = res.stderr.strip().splitlines()
        raise CaptureError('YAML load failed: ' + (lines[-1] if lines else 'exit %d' % res.returncode))
    return {Path(k): v for k, v in json.loads(res.stdout).items()}


def dump(path, obj):
    Path(path).write_text(json.dumps(obj, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')


# --- bounding --------------------------------------------------------------

def aligned_start(anchor, period_s, window):
    """Last phase point of the oscillator at or before the window start."""
    a = parse_anchor(anchor, window)
    if a is None or period_s <= 0:
        return window
    k = math.floor((window - a).total_seconds() / period_s)
    return a + timedelta(seconds=k * period_s)


def spread_pdf(dist, prm, x):
    """Density of a uniform or triangular spreader at fraction x of the period."""
    if dist == 'uniform':
        low, high = float(prm.get('low', 0)), float(prm.get('high', 1))
        return 1.0 / (high - low) if low <= x < high else 0.0
    left, mode, right = float(prm['left']), float(prm['mode']), float(prm['right'])
    if not left <= x <= right or right <= left:
        return 0.0
    if x < mode:
        return 2 * (x - left) / ((right - left) * (mode - left))
    return 2 * (right - x) / ((right - left) * (right - mode)) if right > mode else 0.0


def busiest_hour(patterns, ref=None):
    """(UTC hour of the week with the most timestamps, timestamps per hour then)
    across uniform and triangular daily and weekly patterns, or (None, 0)."""
    density = [0.0] * 168
    for pat in patterns.values():
        osc, spread = pat.get('oscillator') or {}, pat.get('spreader') or {}
        a = parse_anchor(osc.get('start'), ref or datetime.now(timezone.utc))
        period_h = float(osc.get('period', 1)) * UNIT_SECONDS.get(osc.get('unit', 'days'), 0) / 3600
        dist = spread.get('distribution', 'uniform')
        if a is None or period_h not in (24, 168) or dist not in ('uniform', 'triangular'):
            continue
        prm = spread.get('parameters') or {}
        au = a.astimezone(timezone.utc)
        anchor_how = au.weekday() * 24 + au.hour + au.minute / 60.0
        for h in range(168):
            x = ((h + 0.5 - anchor_how) % period_h) / period_h  # fraction of the period
            density[h] += pat['multiplier']['ratio'] * spread_pdf(dist, prm, x) / period_h
    peak = max(range(168), key=lambda h: density[h])
    if density[peak] - min(density) <= 1e-9:
        return None, density[peak]
    return peak, density[peak]


def live_plan(gen_dir, cfg, patterns, window, seconds, carrier=(), target=80):
    """The busiest UTC hour of the week, the rate scale that gives about
    `target` non-carrier records in `seconds`, notes."""
    own = {}
    for item in cfg.get('input') or []:
        (plugin, conf), = item.items()
        conf = conf or {}
        if plugin == 'time_patterns' and not set(conf.get('tags') or ()) & set(carrier):
            for rel in conf.get('patterns') or []:
                path = (gen_dir / rel).resolve()
                own[path] = patterns[path]
    peak, per_hour = busiest_hour(own, window)
    notes = []
    if peak is not None:
        notes.append('curves shifted so that the busiest hour (weekday %d, %02d:00 UTC) runs now'
                     % (peak // 24, peak % 24))
    expected = per_hour / 3600.0 * seconds
    scale = min(1000, max(20, math.ceil(target / expected))) if expected > 0 else 20
    return peak, scale, notes


def bound(gen_dir, cfg, patterns, window, days, scale=1, live=False, shift=None, move=True, carrier=()):
    """Bound every input of a loaded config in place; notes of what changed.

    `patterns` maps pattern paths (resolved) to their loaded content and is
    modified in place. With live=True inputs keep their own start and end.
    Oscillators keep their phase, so they may start before the window;
    measure.py clips records to the window.
    """
    end = window + timedelta(days=days)
    notes = []
    base_scale = scale
    for item in cfg.get('input') or []:
        (plugin, conf), = item.items()
        conf = conf or {}
        item[plugin] = conf
        is_carrier = bool(set(conf.get('tags') or ()) & set(carrier))
        scale = 1 if is_carrier else base_scale  # carriers keep their rate
        if plugin == 'time_patterns':
            for rel in conf.get('patterns') or []:
                path = (gen_dir / rel).resolve()
                pat = patterns[path]
                osc = pat.get('oscillator') or {}
                if 'start' not in osc or 'end' not in osc:
                    raise CaptureError('%s: oscillator needs start and end' % rel)
                if not live:
                    period = float(osc.get('period', 1)) * UNIT_SECONDS[osc.get('unit', 'days')]
                    osc['start'] = iso(aligned_start(osc['start'], period, window))
                    osc['end'] = iso(end)
                elif shift is not None:
                    period_h = float(osc.get('period', 1)) * UNIT_SECONDS[osc.get('unit', 'days')] / 3600
                    if period_h in (24, 168):  # anchor in the past, busiest phase now
                        now_hour = window.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
                        osc['start'] = iso(now_hour - timedelta(hours=shift % period_h))
                if scale != 1:
                    pat['multiplier']['ratio'] = max(1, int(round(pat['multiplier']['ratio'] * scale)))
        elif plugin == 'cron':
            if not live:
                for key in ('start', 'end'):
                    if key not in conf:
                        raise CaptureError('cron input: %s must be set explicitly' % key)
                conf['start'] = iso(window)
                conf['end'] = iso(end - timedelta(seconds=1))
            elif move and is_carrier and not every_minute(conf['expression']):
                # an hour-restricted carrier serves the moved schedules at any hour
                fields = conf['expression'].split()
                every = ' '.join(['*'] * 5 + fields[5:6]) if len(fields) == 6 else '* * * * * *'
                notes.append('carrier %s runs at every hour as %s for the live check' % (conf['expression'], every))
                conf['expression'] = every
            elif move and not every_minute(conf['expression']):
                notes.append('schedule %s replaced by %s for the live check' % (conf['expression'], LIVE_CRON))
                conf['expression'] = LIVE_CRON
            elif scale != 1:
                conf['count'] = max(1, int(round(conf['count'] * scale)))
        elif plugin == 'linspace':
            a, b = parse_iso(conf.get('start')), parse_iso(conf.get('end'))
            if a is None or b is None:
                raise CaptureError('linspace input: start and end must be datetimes with an offset')
            if not live:
                conf['start'], conf['end'] = iso(window), iso(window + (b - a))
            if scale != 1:
                conf['count'] = max(1, int(round(conf['count'] * scale)))
        elif plugin == 'timer':
            seconds = float(conf['seconds'])
            if not live:
                conf['start'] = iso(window - timedelta(seconds=seconds))  # first tick at the window start
                conf['repeat'] = max(1, int(days * 86400 // seconds))
            if scale != 1:
                conf['count'] = max(1, int(round(conf.get('count', 1) * scale)))
        elif plugin == 'timestamps':
            notes.append('timestamps input replays its own moments')
        elif plugin == 'static':
            notes.append('static input emits at run time, outside the window')
        else:
            raise CaptureError('%s input cannot be bounded for a capture' % plugin)
    return notes


def every_minute(expression):
    """True when a cron expression fires at least once a minute (a rate, not a schedule)."""
    fields = expression.split()
    return len(fields) >= 5 and all(f == '*' for f in fields[:5])


def set_mode(cfg, mode, interval):
    if mode == 'as-is':
        return
    event = cfg.get('event') or {}
    if 'template' not in event:
        raise CaptureError('mode %s needs the template event plugin' % mode)
    params = event['template'].get('params') or {}
    event['template']['params'] = params
    if 'anomaly_mode' not in params:
        raise CaptureError('mode %s requested but the generator has no anomaly_mode' % mode)
    params['anomaly_mode'] = mode == 'on'
    if interval is not None:
        if 'anomaly_interval_hours' not in params:
            raise CaptureError('no anomaly_interval_hours parameter')
        params['anomaly_interval_hours'] = int(interval) if float(interval).is_integer() else interval


def set_params(cfg, pairs):
    """KEY=VALUE overrides of event.template.params (VALUE parsed as JSON when it can be)."""
    params = cfg['event']['template'].setdefault('params', {})
    for pair in pairs or ():
        key, _, raw = pair.partition('=')
        if not key or not _:
            raise CaptureError('--param needs KEY=VALUE: %s' % pair)
        try:
            params[key] = json.loads(raw)
        except ValueError:
            params[key] = raw


def file_output(cfg, path):
    fmt = {'format': 'json'}
    for item in cfg.get('output') or []:
        (_, conf), = item.items()
        if isinstance(conf, dict) and conf.get('formatter'):
            fmt = conf['formatter']
            break
    cfg['output'] = [{'file': {'path': str(path), 'write_mode': 'overwrite',
                               'separator': '\n', 'formatter': fmt}}]


def prepare(src, dst, py, window, days, mode='as-is', interval=None, scale=1, live=False,
            seconds=90, carrier=(), params=(), plan=True, replace=()):
    """Copy the generator to dst and bound it; (generator.yml path, config, notes)."""
    src = Path(src).resolve()
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns('output', '.*'))
    for pair in replace or ():  # REL=PATH: a file of the copy replaced (a broken sample)
        rel, _, path = pair.partition('=')
        target = (dst / rel).resolve()
        if not _ or dst.resolve() not in target.parents:
            raise CaptureError('--replace needs REL=PATH inside the generator: %s' % pair)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    cfg_path = dst / 'generator.yml'
    cfg = load_yaml(py, [cfg_path])[cfg_path]
    pat_paths = []
    for item in cfg.get('input') or []:
        (plugin, conf), = item.items()
        if plugin == 'time_patterns':
            for rel in (conf or {}).get('patterns') or []:
                path = (dst / rel).resolve()
                if dst.resolve() not in path.parents:
                    raise CaptureError('pattern %s lies outside the generator directory' % rel)
                pat_paths.append(path)
    patterns = load_yaml(py, pat_paths) if pat_paths else {}
    shift, plan_notes = None, []
    if live and plan:
        shift, auto, plan_notes = live_plan(dst, cfg, patterns, window, seconds, carrier)
        scale = auto if scale is None else scale
        plan_notes.append('rates scaled x%s' % scale)
    elif live:
        scale = 1
    notes = plan_notes + bound(dst, cfg, patterns, window, days, scale, live, shift, move=plan, carrier=carrier)
    set_mode(cfg, mode, interval)
    set_params(cfg, params)
    file_output(cfg, dst / 'output' / 'events.out')
    for path, pat in patterns.items():
        dump(path, pat)
    dump(cfg_path, cfg)
    text = cfg_path.read_text(encoding='utf-8')
    if '${params.' in text or '${secrets.' in text:
        raise CaptureError('the configuration still needs --params or secrets outside the output')
    return cfg_path, cfg, notes


# --- running ---------------------------------------------------------------

def gzip_to(src, dst):
    lines = 0
    with open(src, 'rb') as fin, gzip.open(dst, 'wb', compresslevel=5) as fout:
        for line in fin:
            if line.strip():
                lines += 1
                fout.write(line if line.endswith(b'\n') else line + b'\n')
    return lines


def log_lines(path):
    with open(path, encoding='utf-8', errors='replace') as fh:
        return [ln.rstrip() for ln in fh if ln.strip()]


ANSI = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')


def execute(eventum, cfg_path, run_id, out_dir, mem, timeout, live=False, seconds=None):
    log = out_dir / (run_id + '.log')
    cmd = [eventum, 'generate', '--path', str(cfg_path), '--id', run_id,
           '--live-mode', 'true' if live else 'false', '-vvv']
    if not live:  # live runs as users run it; batch captures are kept in time order
        cmd[-1:-1] = ['--keep-order', 'true']
    with open(log, 'w', encoding='utf-8') as fh:
        res = slot.run(cmd, mem_mb=mem, timeout=seconds if live else timeout,
                       stdout=fh, stderr=subprocess.STDOUT, env=CHILD_ENV,
                       label='eventum %s (%s)' % (run_id, out_dir))
    text_log = log.read_text(encoding='utf-8', errors='replace')
    if '\x1b[' in text_log:  # Eventum colours its console log even into a file
        log.write_text(ANSI.sub('', text_log), encoding='utf-8')
    res['log'] = str(log)
    res['log_lines'] = len(log_lines(log))
    return res


def ts_template_config(cfg, dst, template=TS_TEMPLATE):
    """Replace the templates by one that writes each timestamp and its tags."""
    (dst / 'templates').mkdir(exist_ok=True)
    (dst / 'templates' / '_ts.json.jinja').write_text(template, encoding='utf-8')
    tpl = cfg['event']['template']
    tpl['mode'] = 'all'
    tpl['templates'] = [{'ts': {'template': 'templates/_ts.json.jinja'}}]
    tpl.pop('chain', None)
    cfg['output'][0]['file']['formatter'] = {'format': 'json'}


def replay_config(cfg, groups, dst):
    """Inputs replaced by `timestamps` inputs, one per tag set."""
    inputs = []
    for i, (tags, stamps) in enumerate(sorted(groups.items())):
        f = dst / ('replay-%d.txt' % i)
        f.write_text('\n'.join(stamps) + '\n', encoding='utf-8')
        conf = {'source': str(f)}
        if tags:
            conf['tags'] = list(tags)
        inputs.append({'timestamps': conf})
    cfg['input'] = inputs


def count_lines(path):
    if not path.exists():
        return 0
    with open(path, 'rb') as fh:
        return sum(1 for ln in fh if ln.strip())


def one(args, name, kind, mode, interval, days, eventum, py, window, carrier=()):
    out = Path(args.out).resolve()
    work = out / 'work' / name
    rec = {'name': name, 'kind': kind, 'mode': mode, 'interval': interval, 'days': days,
           'window_start': iso(window), 'window_end': iso(window + timedelta(days=days))}
    try:
        cfg_path, cfg, notes = prepare(args.generator, work, py, window, days, mode, interval,
                                       params=args.param, replace=getattr(args, 'replace', ()))
        rec['notes'] = notes
        if kind == 'check':
            return check_pair(args, rec, cfg_path, cfg, work, eventum, py, window, days, mode, interval, carrier)
        if kind == 'base':  # same inputs, trivial template: Eventum's own memory curve
            ts_template_config(cfg, work, BASE_TEMPLATE)
            cfg['event']['template'].setdefault('params', {})['_carrier'] = list(carrier)
            dump(cfg_path, cfg)
        rec.update(execute(eventum, cfg_path, name, out, args.mem, args.timeout))
        produced = work / 'output' / 'events.out'
        rec['lines'] = 0
        if produced.exists():
            capture = out / (name + '.jsonl.gz')
            rec['lines'] = gzip_to(produced, capture)
            rec['capture'] = str(capture)
    except CaptureError as exc:
        rec.update({'exit': 2, 'reason': 'config', 'error': str(exc)})
    except Exception as exc:  # a run never takes the whole set down
        rec.update({'exit': 2, 'reason': 'error', 'error': '%s: %s' % (type(exc).__name__, exc)})
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)
    return rec


def check_pair(args, rec, cfg_path, cfg, work, eventum, py, window, days, mode, interval, carrier):
    """Exact one-record-per-timestamp check: timestamps, then replay."""
    out = Path(args.out).resolve()
    ts_template_config(cfg, work)
    dump(cfg_path, cfg)
    res = execute(eventum, cfg_path, rec['name'] + '-ts', out, args.mem, args.timeout)
    rec.update({'ts_exit': res['exit'], 'ts_reason': res['reason'], 'ts_log_lines': res['log_lines']})
    stamps_file = work / 'output' / 'events.out'
    groups, total = {}, 0
    if stamps_file.exists():
        with open(stamps_file, encoding='utf-8') as fh:
            for line in fh:
                if not line.strip():
                    continue
                obj = json.loads(line)
                tags = tuple(obj['g'])
                if carrier and set(tags) & set(carrier):
                    continue
                groups.setdefault(tags, []).append(obj['t'])
                total += 1
    rec['timestamps'] = total
    work2 = out / 'work' / (rec['name'] + '-replay')
    try:
        cfg2_path, cfg2, _ = prepare(args.generator, work2, py, window, days, mode, interval,
                                     params=args.param)
        replay_config(cfg2, groups, work2)
        dump(cfg2_path, cfg2)
        res2 = execute(eventum, cfg2_path, rec['name'] + '-replay', out, args.mem, args.timeout)
        rec['lines'] = count_lines(work2 / 'output' / 'events.out')
        rec.update({k: res2[k] for k in ('exit', 'reason', 'wall_s', 'peak_mb', 'cpu_s', 'log', 'log_lines')})
    finally:
        if not args.keep:
            shutil.rmtree(work2, ignore_errors=True)
    rec['missing'] = max(0, total - rec['lines'])
    rec['extra'] = max(0, rec['lines'] - total)
    rec['carrier_excluded'] = list(carrier)
    return rec


def plan(args, has_chain):
    counts = dict(SETS[args.set])
    if args.off_runs:
        counts['off'] = args.off_runs
    if args.on_runs:
        counts['on'] = args.on_runs
    runs = []
    for i in range(counts['off']):
        runs.append(('off-%d' % (i + 1), 'off', 'off' if has_chain else 'as-is', None, args.days))
    if has_chain:
        for i in range(counts['on']):
            runs.append(('on-%d' % (i + 1), 'on', 'on', None, args.days))
        for h in args.short_interval:
            if h:
                runs.append(('short-%g' % h, 'short', 'on', h, args.days))
    for i in range(args.long_runs):
        runs.append(('long' if i == 0 else 'long-%d' % (i + 1), 'long', 'as-is', None, args.long_days))
    runs.append(('long-base', 'base', 'as-is', None, args.long_days))
    runs.append(('check', 'check', 'on' if has_chain else 'as-is', None, args.check_days))
    return runs


def window_start(value):
    d = parse_iso(value)
    if d is None:
        raise CaptureError('--start must be an ISO datetime with an offset: %s' % value)
    return d


def run_problems(results):
    problems = []
    for r in results:
        empty = r.get('kind') in ('off', 'on', 'short', 'long', 'custom') and not r.get('lines')
        bad = (r.get('exit') != 0 or r.get('log_lines') or empty
               or r.get('ts_exit') not in (None, 0) or r.get('ts_log_lines'))
        if not bad:
            continue
        if empty and r.get('exit') == 0:
            problems.append('%s: no records in the window' % r['name'])
            continue
        hint = {'memory': ': memory above 1.5 x --mem, rerun with a larger --mem',
                'timeout': ': exceeded --timeout', 'no-slot': ': no slot',
                'cancelled': ': cancelled'}.get(r.get('reason') or r.get('ts_reason'), '')
        problems.append('%s: exit %s, %s log lines%s%s (log: %s)' % (
            r['name'], r.get('exit'), r.get('log_lines'), hint,
            ' (%s)' % r['error'] if r.get('error') else '', r.get('log')))
    return problems


def cleanup_work(out):
    try:
        (Path(out) / 'work').rmdir()  # only when no other command still uses it
    except OSError:
        pass


def cmd_run(args):
    eventum = find_eventum(args.eventum)
    ver = eventum_version(eventum)
    if ver < MIN_VERSION:
        raise CaptureError('Eventum %s is older than 2.8.0' % '.'.join(map(str, ver)))
    py = eventum_python(eventum)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    window = window_start(args.start)
    gen = Path(args.generator).resolve()
    cfg = load_yaml(py, [gen / 'generator.yml'])[gen / 'generator.yml']
    params = ((cfg.get('event') or {}).get('template') or {}).get('params') or {}
    has_chain = 'anomaly_mode' in params
    runs = plan(args, has_chain)
    started = time.time()
    slot.cancel_on_signals()
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(runs)) as pool:
        futs = [pool.submit(one, args, n, k, m, i, d, eventum, py, window, args.carrier)
                for n, k, m, i, d in runs]
        results = [f.result() for f in futs]
    if not args.keep:
        cleanup_work(out)
    problems = run_problems(results)
    manifest = {
        'schema': SCHEMA, 'generator': str(gen), 'eventum': '.'.join(map(str, ver)),
        'window_start': iso(window), 'has_chain': has_chain,
        'default_interval_hours': params.get('anomaly_interval_hours'),
        'set': args.set, 'wall_s': round(time.time() - started, 1),
        'ok': not problems, 'problems': problems, 'runs': results,
    }
    dump(out / 'manifest.json', manifest)
    print(json.dumps({'manifest': str(out / 'manifest.json'), 'ok': manifest['ok'],
                      'problems': problems, 'wall_s': manifest['wall_s']}, indent=1))
    return 130 if slot.CANCEL.is_set() else (0 if manifest['ok'] else 1)


def cmd_one(args):
    eventum = find_eventum(args.eventum)
    py = eventum_python(eventum)
    Path(args.out).mkdir(parents=True, exist_ok=True)
    slot.cancel_on_signals()
    rec = one(args, args.name, 'custom', args.mode, args.interval, args.days, eventum, py,
              window_start(args.start))
    if not args.keep:
        cleanup_work(args.out)
    if args.expect_error:  # an invalid parameter or sample: one readable error, nothing written
        rec['expected_error_ok'] = (rec.get('exit') == 0 and rec.get('log_lines') == 1
                                    and not rec.get('lines'))
        if rec.get('log'):
            first = log_lines(rec['log'])
            rec['error_line'] = first[0][:400] if first else None
        print(json.dumps({k: v for k, v in rec.items() if k != 'rss_mb'}, indent=1))
        return 0 if rec['expected_error_ok'] else 1
    print(json.dumps({k: v for k, v in rec.items() if k != 'rss_mb'}, indent=1))
    return 0 if not run_problems([rec]) else 1


def resolve(obj, path):
    """Value at a dotted path; a literal key with dots is tried first."""
    if isinstance(obj, dict) and path in obj:
        return obj[path]
    for part in path.split('.'):
        if not isinstance(obj, dict) or part not in obj:
            return None
        obj = obj[part]
    return obj


def cmd_live(args):
    """Live run at scaled rates; follows the output while it grows."""
    eventum = find_eventum(args.eventum)
    py = eventum_python(eventum)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = out / 'work' / 'live'
    slot.cancel_on_signals()
    now = datetime.now(timezone.utc)
    shipped = {}
    try:  # the configuration as shipped runs live without errors (criterion 2)
        cfg0, _, _ = prepare(args.generator, out / 'work' / 'live-shipped', py, now, 1, 'as-is', None,
                             live=True, params=args.param, plan=False)
        res0 = execute(eventum, cfg0, 'live-shipped', out, args.mem, None, live=True, seconds=20)
        shipped = {'seconds': 20, 'log_lines': res0['log_lines'], 'stopped_by': res0['reason'],
                   'exit': res0['exit'], 'log': res0['log']}
    finally:
        if not args.keep:
            shutil.rmtree(out / 'work' / 'live-shipped', ignore_errors=True)
    try:
        cfg_path, _, notes = prepare(args.generator, work, py, now, 1, 'as-is', None,
                                     scale=args.scale, live=True, seconds=args.seconds,
                                     carrier=args.carrier, params=args.param)
        produced = work / 'output' / 'events.out'
        samples, stop = [], threading.Event()

        def follow():
            pos, buf = 0, b''
            while not stop.is_set():
                time.sleep(1)
                if not produced.exists():
                    continue
                with open(produced, 'rb') as fh:
                    fh.seek(pos)
                    chunk = fh.read()
                    pos = fh.tell()
                wall = time.time()
                buf += chunk
                *lines, buf = buf.split(b'\n')
                samples.extend((wall, ln) for ln in lines if ln.strip())

        t = threading.Thread(target=follow, daemon=True)
        t.start()
        res = execute(eventum, cfg_path, 'live', out, args.mem, None, live=True, seconds=args.seconds)
        time.sleep(1.5)
        stop.set()
        t.join()
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)
            cleanup_work(out)
    if args.spec:  # read records the way measure.py does: native lines, any time format
        import measure
        with open(args.spec, encoding='utf-8') as fh:
            spec = measure.Spec(json.load(fh))

        def record_time(line):
            row = spec.row(line.decode('utf-8', 'replace'))
            return None if row is None else spec.time(row)
    else:
        def record_time(line):
            try:
                ts = parse_iso(resolve(json.loads(line), args.ts_path))
            except ValueError:
                return None
            return None if ts is None else ts.timestamp()
    lags, order_breaks, prev = [], 0, None
    for wall, ln in samples:
        t = record_time(ln)
        if t is None:
            continue
        ts = t
        lags.append(wall - t)
        if prev is not None and ts < prev:
            order_breaks += 1
        prev = ts
    per_sec = {}
    for wall, _ in samples:
        per_sec[int(wall)] = per_sec.get(int(wall), 0) + 1
    counts = [per_sec[k] for k in sorted(per_sec)]
    median = sorted(counts)[len(counts) // 2] if counts else 0
    report = {
        'seconds': args.seconds, 'records': len(samples),
        'records_with_time': len(lags), 'order_breaks': order_breaks,
        'lag_s': {'min': round(min(lags), 2), 'max': round(max(lags), 2),
                  'median': round(sorted(lags)[len(lags) // 2], 2)} if lags else None,
        'future_records': sum(1 for x in lags if x < -1.0),
        'first_second': counts[0] if counts else 0, 'median_per_second': median,
        'log_lines': res['log_lines'], 'log': res['log'], 'peak_mb': res['peak_mb'],
        'stopped_by': res['reason'], 'notes': notes, 'shipped': shipped, 'problems': [],
    }
    if shipped.get('log_lines') or shipped.get('stopped_by') != 'timeout':
        report['problems'].append('the shipped configuration failed live: %s' % shipped)
    if res['log_lines']:
        report['problems'].append('log not empty')
    if order_breaks:
        report['problems'].append('records out of order')
    if report['future_records']:
        report['problems'].append('records ahead of the wall clock')
    late = sum(1 for x in lags if x > 5.0)
    report['late_records'] = late
    if late:
        report['problems'].append('%d records more than 5 s behind the wall clock (catch-up)' % late)
    if len(lags) < 30:
        report['problems'].append('%d records with a readable time: too few to judge (raise --scale or '
                                  '--seconds; native output: pass --spec measure.json)' % len(lags))
    report['ok'] = not report['problems']
    dump(out / 'live.json', report)
    print(json.dumps(report, indent=1))
    return 0 if report['ok'] else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--eventum', help='eventum executable (default: $EVENTUM_BIN or PATH)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('doctor', help='check the environment')
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('generator')
    common.add_argument('--out', required=True)
    common.add_argument('--start', default=WINDOW_START, help='window start with offset')
    common.add_argument('--mem', type=int, default=slot.DEFAULT_MEM_MB, help='MB per run')
    common.add_argument('--timeout', type=float, default=3600, help='seconds per run')
    common.add_argument('--keep', action='store_true', help='keep the working copies')
    common.add_argument('--param', action='append', default=[],
                        help='KEY=VALUE override of event.template.params (JSON value)')
    r = sub.add_parser('run', parents=[common], help='the protocol run set')
    r.add_argument('--set', choices=sorted(SETS), default='author')
    r.add_argument('--days', type=int, default=4)
    r.add_argument('--long-days', type=int, default=14)
    r.add_argument('--off-runs', type=int, help='background runs (default: by --set)')
    r.add_argument('--on-runs', type=int, help='anomaly runs at the default interval (default: by --set)')
    r.add_argument('--long-runs', type=int, default=1,
                   help='default-configuration runs; more give the README per-run ranges')
    r.add_argument('--check-days', type=int, default=2)
    r.add_argument('--short-interval', type=float, nargs='+', default=[],
                   help='hours: the shortest interval the design admits and any interval the README '
                        'quotes; 0 for none')
    r.add_argument('--carrier', action='append', default=[], help='tag of a carrier input')
    o = sub.add_parser('one', parents=[common], help='one bounded run')
    o.add_argument('--name', required=True)
    o.add_argument('--days', type=float, default=4)
    o.add_argument('--mode', choices=['on', 'off', 'as-is'], default='as-is')
    o.add_argument('--interval', type=float)
    o.add_argument('--replace', action='append', default=[],
                   help='REL=PATH: replace a file of the copy (a broken sample for a validation check)')
    o.add_argument('--expect-error', action='store_true',
                   help='succeed only on exactly one log line and no records (invalid input checks)')
    lv = sub.add_parser('live', parents=[common], help='live-mode check')
    lv.add_argument('--seconds', type=float, default=90)
    lv.add_argument('--scale', type=float, help='rate multiplier (default: aims at about 80 records)')
    lv.add_argument('--carrier', action='append', default=[], help='tag of a carrier input')
    lv.add_argument('--ts-path', default='@timestamp', help='time field of JSON records')
    lv.add_argument('--spec', help='measure.json: read records with its parse and timestamp')
    args = ap.parse_args()
    try:
        if args.cmd == 'doctor':
            rep = doctor(args.eventum)
            print(json.dumps(rep, indent=1))
            return 0 if rep['ok'] else 1
        return {'run': cmd_run, 'one': cmd_one, 'live': cmd_live}[args.cmd](args)
    except CaptureError as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
