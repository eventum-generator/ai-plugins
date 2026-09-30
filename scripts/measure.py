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


NUMERIC = {'gt': lambda a, b: a > b, 'ge': lambda a, b: a >= b,
           'lt': lambda a, b: a < b, 'le': lambda a, b: a <= b}


def compile_cond(cond):
    """Condition -> predicate. Clauses: {path, values|regex|gt|ge|lt|le|missing};
    combinators any / all / not."""
    if cond is None:
        return None
    if 'path' in cond:
        path = cond['path']
        vals = {str(x) for x in cond['values']} if 'values' in cond else None
        rx = re.compile(cond['regex']) if cond.get('regex') else None
        nums = [(NUMERIC[k], float(cond[k])) for k in NUMERIC if k in cond]
        missing = bool(cond.get('missing'))

        def clause(row):
            v = resolve(row, path)
            if v is None:
                return missing
            for item in (v if isinstance(v, list) else [v]):
                s = item if isinstance(item, str) else (
                    json.dumps(item) if isinstance(item, (dict, list)) else str(item).lower()
                    if isinstance(item, bool) else str(item))
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
        chain = raw.get('chain')
        self.chain = None
        if chain:
            self.chain = {
                'key': compile_value(chain.get('key')) if chain.get('key') else (lambda row: ''),
                'same': chain.get('same') or [],
                'within': float(chain['within']),
                'steps': [dict(s, _c=compile_cond(s['match'])) for s in chain['steps']],
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
        try:
            if self.ts_format and self.ts_year:
                d = datetime.strptime('%s %s' % (self.ts_year, v), '%Y ' + self.ts_format)
            elif self.ts_format:
                d = datetime.strptime(v, self.ts_format)
            else:
                if re.fullmatch(r'\d+(\.\d+)?', v):
                    x = float(v)
                    return x / 1000.0 if x > 1e11 else x
                s = v[:-1] + '+00:00' if v.endswith('Z') else v
                if ' ' in s and 'T' not in s:
                    s = s.replace(' ', 'T', 1)
                d = datetime.fromisoformat(s)
        except ValueError:
            return None
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.timestamp()


# --- one pass over a capture -------------------------------------------------


def open_capture(path):
    if path.endswith('.gz'):
        return gzip.open(path, 'rt', encoding='utf-8', newline='')
    return open(path, encoding='utf-8', newline='')


def step_ok(step, row, binds):
    if not step['_c'](row):
        return None
    for var, path in (step.get('eq') or {}).items():
        if var in binds and text(resolve(row, path)) != binds[var]:
            return None
    for var, path in (step.get('ne') or {}).items():
        val = text(resolve(row, path))
        if any(v in binds and binds[v] == val for v in var.split(',')):
            return None
    if not step.get('bind'):
        return binds
    new = dict(binds)
    for var, path in step['bind'].items():
        new[var] = text(resolve(row, path))
    return new


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


def scan(spec_raw, path):
    """Everything measurable from one capture in one pass."""
    spec = Spec(spec_raw)
    out = {
        'path': os.path.basename(path), 'records': 0, 'unparsed': 0, 'no_time': 0, 'excluded': 0,
        'order_breaks': 0, 'first': None, 'last': None,
        'days': {}, 'hours': [0] * 24, 'classes': {},
        'groups': {g: {'records': 0, 'hours': [0] * 24} for g in spec.groups},
        'actors': {}, 'chains': [], 'step_hits': [], 'keys': [],
    }
    chain = spec.chain
    state, keys = {}, set()
    if chain:
        out['step_hits'] = [0] * len(chain['steps'])
    prev = None
    actor_times = {}
    with open_capture(path) as fh:
        for raw in fh:
            line = raw.rstrip('\r\n')
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
            out['records'] += 1
            if prev is not None and t < prev:
                out['order_breaks'] += 1
            prev = t
            out['first'] = t if out['first'] is None else min(out['first'], t)
            out['last'] = t if out['last'] is None else max(out['last'], t)
            day = datetime.fromtimestamp(t, tz=timezone.utc).strftime('%Y-%m-%d')
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
            if not chain:
                continue
            k = chain_key(chain, row)
            if k is None:
                continue
            keys.add(k)
            steps, within = chain['steps'], chain['within']
            for i, step in enumerate(steps):
                if step['_c'](row):
                    out['step_hits'][i] += 1
            parts = [p for p in state.get(k, ()) if t - p[1] <= within]
            new, seen, done = [], set(), None
            for idx, t0, binds, actor in parts:
                sig = (idx, t0, tuple(sorted(binds.items())))
                if sig not in seen:
                    seen.add(sig)
                    new.append((idx, t0, binds, actor))
                nb = step_ok(steps[idx], row, binds)
                if nb is None:
                    continue
                if idx + 1 == len(steps):
                    if done is None or t0 < done[0]:
                        done = (t0, t, k, actor)
                    continue
                sig = (idx + 1, t0, tuple(sorted(nb.items())))
                if sig not in seen:
                    seen.add(sig)
                    new.append((idx + 1, t0, nb, actor))
            if done:
                out['chains'].append(done)
            nb = step_ok(steps[0], row, {})
            if nb is not None:
                if len(steps) == 1:
                    out['chains'].append((t, t, k, a))
                else:
                    new.append((1, t, nb, a))
            if new:
                state[k] = new
            else:
                state.pop(k, None)
    out['keys'] = sorted(keys)
    out['actors'] = actor_times
    return out


def scan_many(spec_raw, paths):
    if len(paths) == 1:
        return [scan(spec_raw, paths[0])]
    workers = min(len(paths), os.cpu_count() or 2)
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(scan, [spec_raw] * len(paths), paths))


# --- summaries ----------------------------------------------------------------


def iso(t):
    return datetime.fromtimestamp(t, tz=timezone.utc).isoformat()


def full_days(res):
    """Per-day counts without the partial first and last day."""
    days = sorted(res['days'].items())
    return [n for _, n in days[1:-1]] if len(days) > 2 else [n for _, n in days]


def profile(results, top=40):
    total = sum(r['records'] for r in results)
    classes, groups, hours = {}, {}, [0] * 24
    per_day = []
    for r in results:
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
        'per_day': {'min': min(per_day), 'median': statistics.median(per_day),
                    'max': max(per_day)} if per_day else None,
        'class_count': len(classes), 'class_share_pct': shares,
        'hourly_pct': curve(hours),
        'groups': {g: {'share_pct': round(100.0 * v['records'] / total, 2) if total else 0,
                       'hourly_pct': curve(v['hours'])} for g, v in groups.items()},
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


def episodes_report(on, off, interval_h, window_start, around=1800):
    """Recurrence and the actor's activity around each episode."""
    out = {'interval_hours': interval_h, 'captures': []}
    base = {}
    for r in off:
        for actor, times in r['actors'].items():
            base.setdefault(actor, []).append((r, times))
    ratios_before, ratios_after = [], []
    for r in on:
        starts = sorted(r['chains'])
        s_times = [c[0] for c in starts]
        gaps = [round((b - a) / 3600, 2) for a, b in zip(s_times, s_times[1:])]
        first = round((s_times[0] - window_start) / 3600, 2) if s_times else None
        hours = [int(t // 3600 % 24) for t in s_times]
        actors = [c[3] for c in starts]
        keys = [c[2] for c in starts]
        neigh = []
        for t0, t1, _, actor in starts:
            if actor is None:
                continue
            times = r['actors'].get(actor, [])
            before = sum(1 for x in times if t0 - around <= x < t0)
            after = sum(1 for x in times if t1 < x <= t1 + around)
            sod = t0 % 86400
            samples = []
            for rr, btimes in base.get(actor, []):
                day0 = (rr['first'] // 86400) * 86400
                d = day0
                while d < rr['last']:
                    lo = d + sod
                    samples.append(sum(1 for x in btimes if lo - around <= x < lo))
                    d += 86400
            mean = statistics.mean(samples) if samples else None
            neigh.append({'start': iso(t0), 'actor': actor, 'before': before, 'after': after,
                          'baseline_mean': None if mean is None else round(mean, 2),
                          'baseline_max': max(samples) if samples else None})
            if mean:
                ratios_before.append(before / mean)
                ratios_after.append(after / mean)
        w = min(interval_h / 4.0, 6.0) if interval_h else None
        out['captures'].append({
            'path': r['path'], 'episodes': len(starts), 'first_start_hours': first,
            'gaps_hours': gaps, 'gap_tolerance_hours': None if w is None else round(w / 2, 2),
            'gaps_outside_tolerance': [g for g in gaps if w is not None and abs(g - interval_h) > w / 2],
            'start_hours': hours, 'distinct_actors': len(set(actors)),
            'distinct_keys': len(set(keys)),
            'spans_seconds': sorted(round(c[1] - c[0]) for c in starts),
            'around': neigh,
        })
    out['activity_ratio_before'] = round(statistics.mean(ratios_before), 2) if ratios_before else None
    out['activity_ratio_after'] = round(statistics.mean(ratios_after), 2) if ratios_after else None
    return out


def presence(off, on):
    """Episode actors and their record counts in every background capture."""
    used = set()
    for r in on:
        used |= {c[3] for c in r['chains'] if c[3] is not None}
    rows = {}
    for r in off:
        for a in used:
            rows.setdefault(a, []).append(len(r['actors'].get(a, [])))
    lows = sorted(((min(v), a) for a, v in rows.items()))[:10]
    return {'episode_actors': len(used),
            'absent_in_some_background': sorted(a for a, v in rows.items() if min(v) == 0),
            'lowest_counts': [{'actor': a, 'min_records_per_capture': n} for n, a in lows]}


def state_growth(run):
    series = run.get('rss_mb') or []
    if len(series) < 8:
        return None
    vals = [v for _, v in series]
    q = len(vals) // 4
    second, last = statistics.mean(vals[q:2 * q]), statistics.mean(vals[3 * q:])
    return {'rss_second_quarter_mb': round(second), 'rss_last_quarter_mb': round(last),
            'growth_pct': round(100.0 * (last - second) / second, 1) if second else None,
            'peak_mb': run.get('peak_mb')}


def report(spec_path, manifest_path):
    with open(manifest_path, encoding='utf-8') as fh:
        man = json.load(fh)
    with open(spec_path, encoding='utf-8') as fh:
        spec_raw = json.load(fh)
    runs = {r['name']: r for r in man['runs']}
    caps = [r for r in man['runs'] if r.get('capture')]
    scanned = dict(zip([r['name'] for r in caps], scan_many(spec_raw, [r['capture'] for r in caps])))
    off = [scanned[r['name']] for r in caps if r['kind'] == 'off']
    on = [scanned[r['name']] for r in caps if r['kind'] == 'on']
    short = [scanned[r['name']] for r in caps if r['kind'] == 'short']
    long_ = [scanned[r['name']] for r in caps if r['kind'] == 'long']
    window = datetime.fromisoformat(man['window_start']).timestamp()
    rep = {'manifest': manifest_path, 'eventum': man['eventum'], 'set': man['set']}
    rep['2_runs'] = {'ok': man['ok'], 'problems': man['problems']}
    chk = runs.get('check')
    rep['3_one_record_per_timestamp'] = None if not chk else {
        'timestamps': chk.get('timestamps'), 'records': chk.get('lines'),
        'dropped': chk.get('dropped'), 'carrier_excluded': chk.get('carrier_excluded')}
    rep['4_5_profile'] = profile(long_ or off)
    rep['6_state'] = state_growth(runs['long']) if 'long' in runs else None
    live_path = os.path.join(os.path.dirname(manifest_path), 'live.json')
    if os.path.exists(live_path):
        with open(live_path, encoding='utf-8') as fh:
            rep['7_live'] = json.load(fh)
    else:
        rep['7_live'] = 'not run: capture.py live'
    if 'long' in runs and long_:
        rep['speed_records_per_s'] = round(long_[0]['records'] / max(runs['long']['wall_s'], 0.001))
    if man.get('has_chain') and spec_raw.get('chain'):
        rep['12_chains'] = chains_report(off, on + short)
        rep['13_presence'] = presence(off, on + short)
        interval = man.get('default_interval_hours')
        rep['15_18_episodes_default'] = episodes_report(on, off, interval, window)
        short_run = runs.get('short')
        if short:
            rep['18_episodes_short'] = episodes_report(short, off, short_run.get('interval'), window)
    rep['flags'] = flags(rep)
    return rep


def flags(rep):
    """Measured facts that fail a criterion outright; each needs a finding."""
    out = []
    if not rep['2_runs']['ok']:
        out.append('2: runs failed or logged: %s' % '; '.join(rep['2_runs']['problems']))
    chk = rep.get('3_one_record_per_timestamp')
    if chk and chk.get('dropped'):
        out.append('3: %d of %d timestamps yielded no record' % (chk['dropped'], chk['timestamps']))
    prof = rep['4_5_profile']
    if prof['unparsed'] or prof['no_time']:
        out.append('1: %d unparsed records, %d without a timestamp' % (prof['unparsed'], prof['no_time']))
    if prof['order_breaks']:
        out.append('2: %d records out of time order' % prof['order_breaks'])
    st = rep.get('6_state')
    if st and st['growth_pct'] is not None and st['growth_pct'] > 10:
        out.append('6: memory grew %s%% between the second and last quarter of the long run' % st['growth_pct'])
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
    pr = rep.get('13_presence')
    if pr and pr['absent_in_some_background']:
        out.append('13: episode actors absent from some background: %s' % pr['absent_in_some_background'][:10])
    for key in ('15_18_episodes_default', '18_episodes_short'):
        ep = rep.get(key)
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
    s.add_argument('--nth', type=int, default=1)
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
        return 0
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
        n = 0
        opener = gzip.open if args.capture.endswith('.gz') else open
        with opener(args.capture, 'rb') as fh:
            for line in fh:
                if not line.strip():
                    continue
                if args.contains and args.contains.encode('utf-8') not in line:
                    continue
                n += 1
                if n == args.nth:
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
