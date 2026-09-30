"""Measurements of Eventum generator captures.

    measure.py report SPEC MANIFEST
        Every number of the acceptance protocol for the captures of a
        capture.py manifest, keyed by criterion.
    measure.py profile SPEC CAPTURE ...
        Records per day, class shares, group shares, hourly curves.
    measure.py chains SPEC --off OFF ... [--on ON ...]
        Complete chains per capture, step hits and chain keys missing
        from background; exit 1 when background forms a chain or lacks
        a step or a key.
    measure.py sample CAPTURE [--nth N] [--contains TEXT]
        One record printed byte for byte, for a README sample.
    measure.py digest GENERATOR [--previous DIGEST.json]
        Hash of the generator's files, per file and in total, and the
        files changed since a previous digest.

A capture is a file of records, one per line, optionally gzipped: JSON
objects, or native lines parsed by the spec's regex. The spec format
is in create-generator/references/measure-spec.md.

Standard library only; Python 3.9+.
"""

import argparse
import concurrent.futures
import gzip
import hashlib
import json
import os
import re
import statistics
import sys
from datetime import datetime, timezone

SCHEMA = 2  # manifest layout written by capture.py

# --- spec -------------------------------------------------------------------


def resolve(obj, path):
    """Value at a dotted path; a literal key with dots is tried first."""
    if isinstance(obj, dict) and path in obj:
        return obj[path]
    cur = obj
    for part in path.split('.') if path else []:
        if isinstance(cur, dict):
            if part not in cur:
                return None
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return None
    return cur


def text(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True)


def compile_value(spec):
    """{path | paths, regex?} -> function(row) -> str or None."""
    if not spec:
        return lambda row: None
    paths = spec.get('paths') or [spec['path']]
    rx = re.compile(spec['regex']) if spec.get('regex') else None

    def get(row):
        vals = []
        for path in paths:
            v = resolve(row, path)
            if isinstance(v, list):
                v = v[0] if v else None
            v = text(v)
            if v is not None and rx is not None:
                m = rx.search(v)
                v = (m.group(1) if m.groups() else m.group(0)) if m else None
            vals.append('' if v is None else v)
        return None if all(v == '' for v in vals) else '|'.join(vals)
    return get


def scalar(item):
    """String form used to compare values: 'true', '5', '1.5', JSON for objects."""
    if isinstance(item, str):
        return item
    if isinstance(item, bool):
        return 'true' if item else 'false'
    if isinstance(item, (dict, list)):
        return json.dumps(item, sort_keys=True)
    return str(item)


def parse_time(v):
    """Epoch seconds from ISO 8601 (Z, +HHMM, long or comma fractions) or epoch
    s / ms / us / ns; None when unreadable."""
    if re.fullmatch(r'-?\d+(\.\d+)?', v):
        x = float(v)
        for limit, scale in ((1e17, 1e9), (1e14, 1e6), (1e11, 1e3)):
            if abs(x) > limit:
                return x / scale
        return x
    s = v.strip().replace(',', '.')
    if 'T' not in s and ' ' in s:
        s = s.replace(' ', 'T', 1)
    s = re.sub(r'[Zz]$', '+00:00', s)
    s = re.sub(r'([+-]\d\d)(\d\d)$', r'\1:\2', s)
    s = re.sub(r'\.(\d{1,6})\d*', lambda m: '.' + m.group(1).ljust(6, '0'), s)
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


NUMERIC = {'gt': lambda a, b: a > b, 'ge': lambda a, b: a >= b,
           'lt': lambda a, b: a < b, 'le': lambda a, b: a <= b}


def compile_cond(cond):
    """Condition -> predicate. Clauses: {path, values|regex|gt|ge|lt|le|missing};
    combinators any / all / not."""
    if cond is None:
        return None
    if 'path' in cond:
        path = cond['path']
        vals = {scalar(x) for x in cond['values']} if 'values' in cond else None
        rx = re.compile(cond['regex']) if cond.get('regex') else None
        nums = [(NUMERIC[k], float(cond[k])) for k in NUMERIC if k in cond]
        missing = bool(cond.get('missing'))

        def clause(row):
            v = resolve(row, path)
            if v is None:
                return missing
            for item in (v if isinstance(v, list) else [v]):
                s = scalar(item)
                if vals is not None and s in vals:
                    return True
                if rx is not None and rx.search(s):
                    return True
                if nums:
                    try:
                        x = float(item)
                    except (TypeError, ValueError):
                        continue
                    if all(op(x, ref) for op, ref in nums):
                        return True
            return False
        return clause
    parts = []
    if 'any' in cond:
        subs = [compile_cond(c) for c in cond['any']]
        parts.append(lambda row: any(p(row) for p in subs))
    if 'all' in cond:
        subs_all = [compile_cond(c) for c in cond['all']]
        parts.append(lambda row: all(p(row) for p in subs_all))
    if 'not' in cond:
        neg = compile_cond(cond['not'])
        parts.append(lambda row: not neg(row))
    if not parts:
        raise ValueError('empty condition: %r' % (cond,))
    return lambda row: all(p(row) for p in parts)


class Spec:
    def __init__(self, raw):
        self.raw = raw
        ts = raw.get('timestamp') or {'path': '@timestamp'}
        self.ts_get = compile_value({k: v for k, v in ts.items() if k in ('path', 'paths', 'regex')})
        self.ts_format = ts.get('format')
        self.ts_year = ts.get('year')
        parse = raw.get('parse')
        self.line_rx = re.compile(parse['regex']) if parse else None
        self.include = compile_cond(raw.get('include'))
        self.cls = compile_value(raw.get('class'))
        self.groups = {k: compile_cond(v) for k, v in (raw.get('groups') or {}).items()}
        self.actor = compile_value(raw.get('actor'))
        pres = dict(raw.get('presence') or {})
        if raw.get('actor'):
            pres.setdefault('actor', raw['actor'])
        self.presence = {n: compile_value(v) for n, v in pres.items()}
        self.day_shift = float(raw.get('day_start_hour', 0)) * 3600
        chain = raw.get('chain')
        self.chain = None
        if chain:
            self.chain = {
                'key': compile_value(chain.get('key')) if chain.get('key') else (lambda row: ''),
                'same': chain.get('same') or [],
                'within': float(chain['within']),
                'steps': [dict(s, _c=compile_cond(s['match']),
                               **{'_' + k: {v: compile_binding(t) for v, t in (s.get(k) or {}).items()}
                                  for k in ('bind', 'eq', 'ne')})
                          for s in chain['steps']],
            }

    @classmethod
    def load(cls, path):
        with open(path, encoding='utf-8') as fh:
            return cls(json.load(fh))

    def row(self, raw_line):
        if self.line_rx is not None:
            m = self.line_rx.search(raw_line)
            return m.groupdict() if m else None
        try:
            obj = json.loads(raw_line)
        except ValueError:
            return None
        return obj if isinstance(obj, dict) else None

    def time(self, row):
        v = self.ts_get(row)
        if v is None:
            return None
        if not self.ts_format:
            return parse_time(v)
        try:
            if self.ts_year:
                d = datetime.strptime('%s %s' % (self.ts_year, v), '%Y ' + self.ts_format)
            else:
                d = datetime.strptime(v, self.ts_format)
        except ValueError:
            return None
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.timestamp()


# --- one pass over a capture -------------------------------------------------


def open_capture(path):
    """Binary handle; records are split on \\n only."""
    return gzip.open(path, 'rb') if path.endswith('.gz') else open(path, 'rb')


def step_ok(step, row, binds):
    if not step['_c'](row):
        return None
    for var, get in step['_eq'].items():
        if var in binds and get(row) != binds[var]:
            return None
    for var, get in step['_ne'].items():
        val = get(row)
        if any(v in binds and binds[v] == val for v in var.split(',')):
            return None
    if not step['_bind']:
        return binds
    new = dict(binds)
    for var, get in step['_bind'].items():
        new[var] = get(row)
    return new


def compile_binding(spec):
    """A bind / eq / ne target: a path string or a value spec with regex."""
    return compile_value({'path': spec} if isinstance(spec, str) else spec)


def chain_key(chain, row):
    k = chain['key'](row)
    if k is None:
        return None
    for path in chain['same']:
        v = resolve(row, path)
        if v is None:
            return None
        k += '\x1f' + text(v)
    return k


def scan(spec_raw, path, lo=None, hi=None):
    """Everything measurable from one capture in one pass.

    Records outside [lo, hi) are counted as outside the window and skipped.
    Chains: partial matches are kept per (step, bindings) with their earliest
    and latest first-step time, so every candidate stays alive in linear
    time; a completion whose first step falls inside the previous counted
    chain of the same key belongs to that chain.
    """
    spec = Spec(spec_raw)
    out = {
        'path': path, 'records': 0, 'unparsed': 0, 'no_time': 0, 'excluded': 0,
        'outside_window': 0, 'order_breaks': 0, 'first': None, 'last': None,
        'days': {}, 'hours': [0] * 24, 'classes': {},
        'groups': {g: {'records': 0, 'hours': [0] * 24} for g in spec.groups},
        'actors': {}, 'last_step': {}, 'chains': [], 'step_hits': [], 'keys': [],
        'presence': {n: {} for n in spec.presence},
    }
    chain = spec.chain
    state, keys, last_chain_end = {}, set(), {}
    if chain:
        out['step_hits'] = [0] * len(chain['steps'])
    prev = None
    actor_times = {}
    with open_capture(path) as fh:
        for raw in fh:
            line = raw.rstrip(b'\r\n').decode('utf-8', 'replace')
            if not line.strip():
                continue
            row = spec.row(line)
            if row is None:
                out['unparsed'] += 1
                continue
            if spec.include is not None and not spec.include(row):
                out['excluded'] += 1
                continue
            t = spec.time(row)
            if t is None:
                out['no_time'] += 1
                continue
            try:
                day = datetime.fromtimestamp(t - spec.day_shift, tz=timezone.utc).strftime('%Y-%m-%d')
            except (OverflowError, OSError, ValueError):
                out['no_time'] += 1
                continue
            if (lo is not None and t < lo) or (hi is not None and t >= hi):
                out['outside_window'] += 1
                continue
            out['records'] += 1
            if prev is not None and t < prev:
                out['order_breaks'] += 1
            prev = t
            out['first'] = t if out['first'] is None else min(out['first'], t)
            out['last'] = t if out['last'] is None else max(out['last'], t)
            hour = int(t // 3600 % 24)
            out['days'][day] = out['days'].get(day, 0) + 1
            out['hours'][hour] += 1
            c = spec.cls(row)
            if c is not None:
                out['classes'][c] = out['classes'].get(c, 0) + 1
            for g, pred in spec.groups.items():
                if pred(row):
                    out['groups'][g]['records'] += 1
                    out['groups'][g]['hours'][hour] += 1
            a = spec.actor(row)
            if a is not None:
                actor_times.setdefault(a, []).append(t)
            k = chain_key(chain, row) if chain else None
            for n, get in spec.presence.items():
                v = get(row)
                if v is not None:
                    out['presence'][n].setdefault(v, []).append((t, k))
            if not chain:
                continue
            if k is None:
                continue
            keys.add(k)
            steps, within = chain['steps'], chain['within']
            for i, step in enumerate(steps):
                if step['_c'](row):
                    out['step_hits'][i] += 1
            if a is not None and steps[-1]['_c'](row):
                out['last_step'].setdefault(a, []).append(t)
            # Partials {(idx, binds): (earliest t0, latest t0, actor)}: every path
            # at one step with one binding advances together, so the range of
            # first-step times is exact for existence (the latest decides expiry)
            # and the earliest still-valid time is reported as the start.
            parts = {sig: v for sig, v in state.get(k, {}).items() if t - v[1] <= within}
            nxt, done = dict(parts), None

            def add(sig, lo, hi, actor):
                cur = nxt.get(sig)
                nxt[sig] = (lo, hi, actor) if cur is None else (min(cur[0], lo), max(cur[1], hi), cur[2])

            for (idx, bsig), (e0, l0, actor) in parts.items():
                nb = step_ok(steps[idx], row, dict(bsig))
                if nb is None:
                    continue
                lo = e0 if t - e0 <= within else l0
                if idx + 1 == len(steps):
                    if done is None or lo < done[0]:
                        done = (lo, t, k, actor)
                    continue
                add((idx + 1, tuple(sorted(nb.items()))), lo, l0, actor)
            nb = step_ok(steps[0], row, {})
            if nb is not None:
                if len(steps) == 1:
                    done = done or (t, t, k, a)
                else:
                    add((1, tuple(sorted(nb.items()))), t, t, a)
            if done:
                if done[0] <= last_chain_end.get(k, float('-inf')):
                    last_chain_end[k] = max(last_chain_end[k], done[1])
                else:
                    out['chains'].append(done)
                    last_chain_end[k] = done[1]
            if nxt:
                state[k] = nxt
            else:
                state.pop(k, None)
    out['keys'] = sorted(keys)
    out['actors'] = actor_times
    return out


def _scan_job(args):
    return scan(*args)


def scan_many(spec_raw, paths, windows=None):
    """Scan captures in parallel processes; windows: [(lo, hi)] per path."""
    jobs = [(spec_raw, p) + tuple(windows[i] if windows else (None, None))
            for i, p in enumerate(paths)]
    if len(jobs) == 1:
        return [_scan_job(jobs[0])]
    workers = min(len(jobs), os.cpu_count() or 2)
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_scan_job, jobs))


def iso(t):
    return datetime.fromtimestamp(t, tz=timezone.utc).isoformat()


def full_days(res):
    """Per-day counts without the partial first and last day."""
    days = sorted(res['days'].items())
    return [n for _, n in days[1:-1]] if len(days) > 2 else [n for _, n in days]


def profile(results, top=40):
    total = sum(r['records'] for r in results)
    classes, groups, hours = {}, {}, [0] * 24
    per_day, weekday = [], {}
    for r in results:
        for day, n in sorted(r['days'].items())[1:-1]:
            weekday.setdefault(datetime.strptime(day, '%Y-%m-%d').strftime('%a'), []).append(n)
        for c, n in r['classes'].items():
            classes[c] = classes.get(c, 0) + n
        for g, v in r['groups'].items():
            acc = groups.setdefault(g, {'records': 0, 'hours': [0] * 24})
            acc['records'] += v['records']
            acc['hours'] = [a + b for a, b in zip(acc['hours'], v['hours'])]
        hours = [a + b for a, b in zip(hours, r['hours'])]
        per_day += full_days(r)
    ranked = sorted(classes.items(), key=lambda kv: -kv[1])
    shares = {c: round(100.0 * n / total, 2) for c, n in ranked[:top]}
    if len(ranked) > top:
        shares['(other %d classes)' % (len(ranked) - top)] = round(
            100.0 * sum(n for _, n in ranked[top:]) / total, 2)

    def curve(h):
        s = sum(h) or 1
        return [round(100.0 * x / s, 2) for x in h]
    return {
        'records': total,
        'per_day_utc': {'min': min(per_day), 'median': statistics.median(per_day),
                    'max': max(per_day)} if per_day else None,
        'per_weekday_mean': {d: round(statistics.mean(v)) for d, v in weekday.items()},
        'class_count': len(classes), 'class_share_pct': shares,
        'hourly_pct_utc': curve(hours),
        'groups': {g: {'share_pct': round(100.0 * v['records'] / total, 2) if total else 0,
                       'hourly_pct_utc': curve(v['hours'])} for g, v in groups.items()},
        'outside_window': sum(r['outside_window'] for r in results),
        'unparsed': sum(r['unparsed'] for r in results),
        'no_time': sum(r['no_time'] for r in results),
        'order_breaks': sum(r['order_breaks'] for r in results),
    }


def chains_report(off, on):
    on_keys = set()
    rep = {'on': {}, 'off': {}}
    for r in on:
        on_keys |= {c[2] for c in r['chains']}
        rep['on'][r['path']] = {'chains': len(r['chains'])}
    bad = False
    for r in off:
        keyset = set(r['keys'])
        missing = sorted(k.replace('\x1f', ' | ') for k in on_keys - keyset)
        miss_steps = [i for i, n in enumerate(r['step_hits']) if n == 0]
        rep['off'][r['path']] = {'chains': len(r['chains']), 'step_hits': r['step_hits'],
                                 'missing_steps': miss_steps, 'missing_chain_keys': missing[:20],
                                 'missing_chain_keys_count': len(missing)}
        bad = bad or bool(r['chains'] or miss_steps or missing)
    rep['ok'] = not bad
    return rep


def _before(times, t, around):
    return sum(1 for x in times if t - around <= x < t)


def _after(times, t, around):
    return sum(1 for x in times if t < x <= t + around)


def episodes_report(on, off, interval_h, window_start, around=1800):
    """Recurrence, and the actor's activity around each episode compared with
    its activity around ordinary background records of the chain's last step
    (the same kind of moment without the chain) and at the same clock time
    on background days."""
    out = {'interval_hours': interval_h, 'around_seconds': around, 'captures': []}
    same_moment, same_clock = {}, {}
    for r in off:
        for actor, lasts in r['last_step'].items():
            times = r['actors'].get(actor, [])
            for t in lasts:
                same_moment.setdefault(actor, []).append((_before(times, t, around), _after(times, t, around)))
        for actor, times in r['actors'].items():
            same_clock.setdefault(actor, []).append((r, times))
    ratios = {'before_vs_moment': [], 'after_vs_moment': [], 'before_vs_clock': []}
    for r in on:
        starts = sorted(r['chains'], key=lambda c: (c[0], c[1]))
        s_times = [c[0] for c in starts]
        gaps = [round((b - a) / 3600, 2) for a, b in zip(s_times, s_times[1:])]
        first = round((s_times[0] - window_start) / 3600, 2) if s_times else None
        neigh = []
        for t0, t1, _, actor in starts:
            if actor is None:
                continue
            times = r['actors'].get(actor, [])
            before, after = _before(times, t0, around), _after(times, t1, around)
            moments = same_moment.get(actor, [])
            clock = []
            for rr, btimes in same_clock.get(actor, []):
                d = (rr['first'] // 86400) * 86400
                while d < rr['last']:
                    lo = d + t0 % 86400
                    clock.append(_before(btimes, lo, around))
                    d += 86400
            item = {'start': iso(t0), 'actor': actor, 'before': before, 'after': after}
            if moments:
                mb = statistics.mean(m[0] for m in moments)
                ma = statistics.mean(m[1] for m in moments)
                item.update({'moment_before_mean': round(mb, 2), 'moment_after_mean': round(ma, 2),
                             'moments': len(moments)})
                if mb:
                    ratios['before_vs_moment'].append(before / mb)
                if ma:
                    ratios['after_vs_moment'].append(after / ma)
            if clock:
                cm = statistics.mean(clock)
                item.update({'clock_before_mean': round(cm, 2), 'clock_before_range': [min(clock), max(clock)]})
                if cm:
                    ratios['before_vs_clock'].append(before / cm)
            neigh.append(item)
        w = min(interval_h / 4.0, 6.0) if interval_h else None
        out['captures'].append({
            'path': r['path'], 'episodes': len(starts), 'first_start_hours': first,
            'gaps_hours': gaps, 'gap_tolerance_hours': None if w is None else round(w / 2, 2),
            'gaps_outside_tolerance': [g for g in gaps if w is not None and abs(g - interval_h) > w / 2],
            'start_hours_utc': [int(t // 3600 % 24) for t in s_times],
            'distinct_actors': len({c[3] for c in starts}), 'distinct_keys': len({c[2] for c in starts}),
            'spans_seconds': sorted(round(c[1] - c[0]) for c in starts),
            'around': neigh,
        })
    out['activity_ratios'] = {k: round(statistics.mean(v), 2) if v else None for k, v in ratios.items()}
    return out


def presence(off, on):
    """Per presence spec (actor, pairs, ...): the values episodes use (records of
    the episode's key inside its span) and their counts in every background capture."""
    out = {}
    for name in (on[0]['presence'] if on else {}):
        used = set()
        for r in on:
            spans = {}
            for t0, t1, k, _ in r['chains']:
                spans.setdefault(k, []).append((t0, t1))
            for v, hits in r['presence'][name].items():
                if any(k in spans and any(a <= t <= b for a, b in spans[k]) for t, k in hits):
                    used.add(v)
        counts = {v: [len(r['presence'][name].get(v, ())) for r in off] for v in used}
        lows = sorted((min(c), v) for v, c in counts.items())[:10]
        out[name] = {'episode_values': len(used),
                     'absent_in_some_background': sorted(v for v, c in counts.items() if min(c or [0]) == 0),
                     'lowest': [{'value': v, 'min_records_per_capture': n} for n, v in lows]}
    return out


def step_pairs(spec_raw, off_paths, windows):
    """Background occurrences of every ordered pair of chain steps with the links
    between them (bind at the first, eq / ne at the second) within the chain
    window: a pair only episodes contain is a zero-noise rule on part of the chain."""
    steps = spec_raw['chain']['steps']
    if len(steps) < 3:
        return None
    jobs, names = [], []
    for i in range(len(steps)):
        for j in range(i + 1, len(steps)):
            pair = dict(spec_raw, chain=dict(spec_raw['chain'], steps=[steps[i], steps[j]]))
            pair.pop('presence', None)
            for p, w in zip(off_paths, windows):
                jobs.append((pair, p) + tuple(w))
                names.append('steps %d-%d' % (i, j))
    workers = min(len(jobs), os.cpu_count() or 2)
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
        res = list(pool.map(_scan_job, jobs))
    out = {}
    for n, r in zip(names, res):
        out.setdefault(n, []).append(len(r['chains']))
    return out


def _growth(run):
    vals = [v for _, v in run.get('rss_mb') or []]
    if len(vals) < 8:
        return None
    q = len(vals) // 4
    return statistics.mean(vals[q:2 * q]), statistics.mean(vals[3 * q:])


def state_growth(run, base=None):
    """Memory growth of the long run between its second and last quarter,
    minus the growth Eventum shows on the same inputs with a trivial template."""
    g = _growth(run)
    if g is None:
        return None
    second, last = g
    b = _growth(base) if base else None
    excess = (last - second) - ((b[1] - b[0]) if b else 0)
    return {'rss_second_quarter_mb': round(second), 'rss_last_quarter_mb': round(last),
            'baseline_growth_mb': round(b[1] - b[0]) if b else None,
            'excess_growth_mb': round(excess),
            'excess_growth_pct': round(100.0 * excess / second, 1) if second else None,
            'peak_mb': run.get('peak_mb')}


def report(spec_path, manifest_path):
    with open(manifest_path, encoding='utf-8') as fh:
        man = json.load(fh)
    if man.get('schema') != SCHEMA:
        raise SystemExit('manifest schema %s, expected %s: rerun capture.py with the current scripts'
                         % (man.get('schema'), SCHEMA))
    with open(spec_path, encoding='utf-8') as fh:
        spec_raw = json.load(fh)
    runs = {r['name']: r for r in man['runs']}
    caps = [r for r in man['runs'] if r.get('capture') and os.path.exists(r['capture'])]
    windows = [(parse_time(r['window_start']), parse_time(r['window_end'])) if r.get('window_start')
               else (None, None) for r in caps]
    results = scan_many(spec_raw, [r['capture'] for r in caps], windows)
    for res in results:
        res['path'] = os.path.basename(res['path'])
    scanned = dict(zip([r['name'] for r in caps], results))
    off = [scanned[r['name']] for r in caps if r['kind'] == 'off']
    on = [scanned[r['name']] for r in caps if r['kind'] == 'on']
    short_runs = [r for r in caps if r['kind'] == 'short']
    short = [scanned[r['name']] for r in short_runs]
    long_ = [scanned[r['name']] for r in caps if r['kind'] == 'long']
    window = parse_time(man['window_start'])
    rep = {'manifest': manifest_path, 'eventum': man['eventum'], 'set': man['set']}
    rep['2_runs'] = {'ok': man['ok'], 'problems': man['problems']}
    chk = runs.get('check')
    rep['3_one_record_per_timestamp'] = None if not chk else {
        'timestamps': chk.get('timestamps'), 'records': chk.get('lines'),
        'missing': chk.get('missing'), 'extra': chk.get('extra'),
        'carrier_excluded': chk.get('carrier_excluded')}
    rep['4_5_profile'] = profile(long_ or off) if (long_ or off) else None
    rep['6_state'] = state_growth(runs['long'], runs.get('long-base')) if 'long' in runs else None
    live_path = os.path.join(os.path.dirname(manifest_path), 'live.json')
    if os.path.exists(live_path):
        with open(live_path, encoding='utf-8') as fh:
            rep['7_live'] = json.load(fh)
    else:
        rep['7_live'] = 'not run: capture.py live'
    if 'long' in runs and long_:
        cpu = runs['long'].get('cpu_s')
        rep['speed'] = {'records_per_cpu_s': round(long_[0]['records'] / cpu) if cpu else None,
                        'records_per_wall_s': round(long_[0]['records'] / max(runs['long']['wall_s'], 0.001)),
                        'note': 'CPU seconds do not depend on parallel load; wall seconds do'}
    if man.get('has_chain') and spec_raw.get('chain'):
        rep['12_chains'] = chains_report(off, on + short)
        rep['13_presence'] = presence(off, on + short)
        off_caps = [r for r in caps if r['kind'] == 'off']
        rep['13_step_pairs_in_background'] = step_pairs(
            spec_raw, [r['capture'] for r in off_caps],
            [(parse_time(r['window_start']), parse_time(r['window_end'])) for r in off_caps])
        interval = man.get('default_interval_hours')
        rep['15_18_episodes_default'] = episodes_report(on, off, interval, window)
        rep['18_episodes_short'] = {r['name']: episodes_report([scanned[r['name']]], off, r.get('interval'), window)
                                    for r in short_runs}
    rep['flags'] = flags(rep)
    return rep


def flags(rep):
    """Measured facts that fail a criterion outright; each needs a finding."""
    out = []
    if not rep['2_runs']['ok']:
        out.append('2: runs failed or logged: %s' % '; '.join(rep['2_runs']['problems']))
    chk = rep.get('3_one_record_per_timestamp')
    if chk and chk.get('missing'):
        out.append('3: %d of %d timestamps yielded no record' % (chk['missing'], chk['timestamps']))
    if chk and chk.get('extra'):
        out.append('3: %d records more than the %d timestamps' % (chk['extra'], chk['timestamps']))
    prof = rep['4_5_profile'] or {'unparsed': 0, 'no_time': 0, 'order_breaks': 0}
    if not rep['4_5_profile']:
        out.append('2: no background or long capture to measure')
    if prof['unparsed'] or prof['no_time']:
        out.append('1: %d unparsed records, %d without a timestamp' % (prof['unparsed'], prof['no_time']))
    if prof['order_breaks']:
        out.append('2: %d records out of time order' % prof['order_breaks'])
    st = rep.get('6_state')
    if st and st['excess_growth_pct'] is not None and st['excess_growth_pct'] > 10 and st['excess_growth_mb'] > 50:
        out.append('6: memory grew %s MB (%s%%) more than Eventum alone between the second and last '
                   'quarter of the long run' % (st['excess_growth_mb'], st['excess_growth_pct']))
    live = rep.get('7_live')
    if isinstance(live, dict) and not live.get('ok'):
        out.append('7: live check failed')
    ch = rep.get('12_chains')
    if ch:
        for path, v in ch['off'].items():
            if v['chains']:
                out.append('12: %d complete chains in background %s' % (v['chains'], path))
            if v['missing_steps']:
                out.append('13: steps %s absent from background %s' % (v['missing_steps'], path))
            if v['missing_chain_keys_count']:
                out.append('13: %d chain keys absent from background %s' % (v['missing_chain_keys_count'], path))
        for path, v in ch['on'].items():
            if not v['chains']:
                out.append('12: no chain in anomaly capture %s' % path)
    for name, pr in (rep.get('13_presence') or {}).items():
        if pr['absent_in_some_background']:
            out.append('13: episode %s values absent from some background: %s'
                       % (name, pr['absent_in_some_background'][:10]))
    for pair, counts in (rep.get('13_step_pairs_in_background') or {}).items():
        if not any(counts):
            out.append('13: chain %s with their links never occur in background: only episodes contain them'
                       % pair)
    eps = [rep.get('15_18_episodes_default')] + list((rep.get('18_episodes_short') or {}).values())
    for ep in eps:
        if not ep:
            continue
        for cap in ep['captures']:
            if cap['gaps_outside_tolerance']:
                out.append('18: gaps %s h outside %s ± %s h in %s' % (
                    cap['gaps_outside_tolerance'], ep['interval_hours'], cap['gap_tolerance_hours'], cap['path']))
    return out


def digest(root, previous=None):
    root = os.path.abspath(root)
    files = {}
    for base, dirs, names in os.walk(root):
        rel_base = os.path.relpath(base, root)
        dirs[:] = sorted(d for d in dirs if not (rel_base == '.' and d == 'output')
                         and not d.startswith('.'))
        for n in names:
            if n.startswith('.'):
                continue
            rel = os.path.normpath(os.path.join(rel_base, n)).replace(os.sep, '/')
            with open(os.path.join(root, rel), 'rb') as fh:
                files[rel] = hashlib.sha256(fh.read()).hexdigest()
    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(rel.encode('utf-8') + b'\0' + bytes.fromhex(files[rel]))
    out = {'digest': h.hexdigest(), 'files': files}
    if previous:
        with open(previous, encoding='utf-8') as fh:
            old = json.load(fh).get('files', {})
        out['changed'] = sorted(f for f in files if f in old and old[f] != files[f])
        out['added'] = sorted(f for f in files if f not in old)
        out['removed'] = sorted(f for f in old if f not in files)
    return out


# --- commands -----------------------------------------------------------------


def emit(obj):
    print(json.dumps(obj, indent=1, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('report')
    r.add_argument('spec')
    r.add_argument('manifest')
    r.add_argument('--save', help='also write the report to this file')
    p = sub.add_parser('profile')
    p.add_argument('spec')
    p.add_argument('captures', nargs='+')
    p.add_argument('--top', type=int, default=40)
    c = sub.add_parser('chains')
    c.add_argument('spec')
    c.add_argument('--off', nargs='+', required=True)
    c.add_argument('--on', nargs='*', default=[])
    s = sub.add_parser('sample')
    s.add_argument('capture')
    s.add_argument('--nth', type=int, help='default: the middle matching record')
    s.add_argument('--contains')
    d = sub.add_parser('digest')
    d.add_argument('generator')
    d.add_argument('--previous')
    d.add_argument('--save')
    args = ap.parse_args()
    if args.cmd == 'report':
        rep = report(args.spec, args.manifest)
        if args.save:
            with open(args.save, 'w', encoding='utf-8') as fh:
                json.dump(rep, fh, indent=1, ensure_ascii=False)
        emit(rep)
        return 1 if rep['flags'] else 0
    if args.cmd == 'profile':
        with open(args.spec, encoding='utf-8') as fh:
            spec_raw = json.load(fh)
        emit(profile(scan_many(spec_raw, args.captures), args.top))
        return 0
    if args.cmd == 'chains':
        with open(args.spec, encoding='utf-8') as fh:
            spec_raw = json.load(fh)
        res = scan_many(spec_raw, args.off + args.on)
        rep = chains_report(res[:len(args.off)], res[len(args.off):])
        for r in res[len(args.off):]:
            starts = sorted(c[0] for c in r['chains'])
            rep['on'][r['path']].update({
                'starts': [iso(t) for t in starts],
                'gaps_hours': [round((b - a) / 3600, 2) for a, b in zip(starts, starts[1:])]})
        emit(rep)
        return 0 if rep['ok'] else 1
    if args.cmd == 'sample':
        opener = gzip.open if args.capture.endswith('.gz') else open

        def matching():
            with opener(args.capture, 'rb') as fh:
                for line in fh:
                    if line.strip() and (not args.contains or args.contains.encode('utf-8') in line):
                        yield line
        nth = args.nth or (sum(1 for _ in matching()) + 1) // 2  # default: the middle record
        for n, line in enumerate(matching(), 1):
            if n == nth:
                sys.stdout.buffer.write(line if line.endswith(b'\n') else line + b'\n')
                return 0
        return 1
    if args.cmd == 'digest':
        out = digest(args.generator, args.previous)
        if args.save:
            with open(args.save, 'w', encoding='utf-8') as fh:
                json.dump(out, fh, indent=1)
        emit({k: v for k, v in out.items() if k != 'files'} if args.previous else out)
        return 0
    return 2


if __name__ == '__main__':
    sys.exit(main())
