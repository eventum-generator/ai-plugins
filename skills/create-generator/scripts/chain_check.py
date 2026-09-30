"""Anomaly-chain checks for Eventum generator captures.

A capture is a JSON-lines file (.jsonl or .jsonl.gz) written by a
generator run with --live-mode false --keep-order true. A spec
describes the chain the way a detector would see it; the format is in
references/chain-spec.md.

Commands:
    chain_check.py count SPEC CAPTURE [CAPTURE ...]
        Complete chains per capture, their start times and the gaps
        between consecutive starts.
    chain_check.py accept SPEC --off OFF [OFF ...] --on ON [ON ...]
        0 chains in every background capture, every chain step and
        every chain key of the anomaly captures present in each
        background capture. Exit status 1 on any miss.

Standard library only; Python 3.9+.
"""

import argparse
import gzip
import json
import re
import sys
from datetime import datetime, timezone


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
        elif isinstance(cur, list):
            if part.isdigit() and int(part) < len(cur):
                cur = cur[int(part)]
            else:
                return None
        else:
            return None
    return cur


def text(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True)


def extract(obj, spec):
    """Scalar string for a {path | paths, regex} spec, or None."""
    if spec is None:
        return None
    vals = []
    for path in spec.get('paths') or [spec['path']]:
        v = resolve(obj, path)
        if isinstance(v, list):
            v = v[0] if v else None
        if v is None:
            vals.append('')
            continue
        v = text(v)
        rx = spec.get('_rx')
        if rx is not None:
            m = rx.search(v)
            v = (m.group(1) if m.groups() else m.group(0)) if m else ''
        vals.append(v)
    if all(v == '' for v in vals):
        return None
    return '|'.join(vals)


def parse_ts(value, fmt=None):
    """Epoch seconds from ISO 8601, epoch s/ms or a strptime format."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) / (1000.0 if value > 1e11 else 1.0)
    s = str(value)
    if fmt:
        d = datetime.strptime(s, fmt)
    else:
        if s.endswith('Z'):
            s = s[:-1] + '+00:00'
        if ' ' in s and 'T' not in s:
            s = s.replace(' ', 'T', 1)
        d = datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def compile_cond(cond):
    """Compile {path, values | regex} clauses and any/all/not."""
    if not cond:
        return None
    if 'path' in cond:
        cond = {'any': [cond]}
    for key in ('any', 'all'):
        for clause in cond.get(key, []):
            if 'path' in clause:
                if clause.get('regex'):
                    clause['_rx'] = re.compile(clause['regex'])
                if 'values' in clause:
                    clause['_vals'] = {str(x) for x in clause['values']}
            else:
                compile_cond(clause)
    if cond.get('not'):
        cond['not'] = compile_cond(cond['not'])
    return cond


def clause_ok(obj, clause):
    if 'path' not in clause:
        return matches(obj, clause)
    v = resolve(obj, clause['path'])
    if v is None:
        return bool(clause.get('missing'))
    items = v if isinstance(v, list) else [v]
    for item in items:
        s = item if isinstance(item, str) else (
            str(item) if isinstance(v, list) else json.dumps(item))
        if '_vals' in clause and s in clause['_vals']:
            return True
        if clause.get('_rx') is not None and clause['_rx'].search(s):
            return True
    return False


def matches(obj, cond):
    if cond is None:
        return False
    ok = True
    if 'any' in cond:
        ok = any(clause_ok(obj, c) for c in cond['any'])
    if ok and 'all' in cond:
        ok = all(clause_ok(obj, c) for c in cond['all'])
    if ok and cond.get('not') is not None:
        ok = not matches(obj, cond['not'])
    return ok


def load_spec(path):
    with open(path, encoding='utf-8') as fh:
        spec = json.load(fh)
    ts = spec.get('timestamp') or {'path': '@timestamp'}
    spec['timestamp'] = ts
    if ts.get('regex'):
        ts['_rx'] = re.compile(ts['regex'])
    spec['_include'] = compile_cond(spec.get('include'))
    seq = spec['chain_seq']
    key = seq.get('key')
    if isinstance(key, dict) and key.get('regex'):
        key['_rx'] = re.compile(key['regex'])
    for step in seq['steps']:
        step['_c'] = compile_cond(step['match'])
    return spec


def chain_key(seq, obj):
    k = extract(obj, seq['key']) if seq.get('key') else ''
    if k is None:
        return None
    for path in seq.get('same', ()):
        v = resolve(obj, path)
        if v is None:
            return None
        k += '\x1f' + text(v)
    return k


def step_ok(step, obj, binds):
    """New bindings if the row satisfies the step, else None."""
    if not matches(obj, step['_c']):
        return None
    for var, path in (step.get('eq') or {}).items():
        if var in binds and text(resolve(obj, path)) != binds[var]:
            return None
    for var, path in (step.get('ne') or {}).items():
        val = text(resolve(obj, path))
        if any(v in binds and binds[v] == val for v in var.split(',')):
            return None
    if not step.get('bind'):
        return binds
    new = dict(binds)
    for var, path in step['bind'].items():
        new[var] = text(resolve(obj, path))
    return new


def open_capture(path):
    if path.endswith('.gz'):
        return gzip.open(path, 'rt', encoding='utf-8')
    return open(path, encoding='utf-8')


def scan(spec, path):
    """Chains (every binding kept alive), keys and per-step hits.

    A row that advances a partial match keeps the unadvanced copy, so
    every candidate run stays alive; partials expire `within` seconds
    after their first step; a row counts once however many partials it
    completes.
    """
    seq = spec['chain_seq']
    steps, within = seq['steps'], seq['within']
    ts_spec = spec['timestamp']
    state, chains, keys = {}, [], set()
    hits = [0] * len(steps)
    with open_capture(path) as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            obj = json.loads(raw)
            if spec['_include'] is not None and not matches(
                    obj, spec['_include']):
                continue
            k = chain_key(seq, obj)
            if k is None:
                continue
            keys.add(k)
            for i, step in enumerate(steps):
                if matches(obj, step['_c']):
                    hits[i] += 1
            t = parse_ts(extract(obj, ts_spec), ts_spec.get('format'))
            parts = [p for p in state.get(k, ()) if t - p[1] <= within]
            new, seen, done = [], set(), None
            for idx, t0, binds in parts:
                sig = (idx, t0, tuple(sorted(binds.items())))
                if sig not in seen:
                    seen.add(sig)
                    new.append((idx, t0, binds))
                nb = step_ok(steps[idx], obj, binds)
                if nb is None:
                    continue
                if idx + 1 == len(steps):
                    if done is None or t0 < done[0]:
                        done = (t0, t, k)
                    continue
                sig = (idx + 1, t0, tuple(sorted(nb.items())))
                if sig not in seen:
                    seen.add(sig)
                    new.append((idx + 1, t0, nb))
            if done:
                chains.append(done)
            nb = step_ok(steps[0], obj, {})
            if nb is not None:
                if len(steps) == 1:
                    chains.append((t, t, k))
                else:
                    new.append((1, t, nb))
            if new:
                state[k] = new
            else:
                state.pop(k, None)
    return chains, keys, hits


def iso(t):
    return datetime.fromtimestamp(t, tz=timezone.utc).isoformat()


def cmd_count(args):
    spec = load_spec(args.spec)
    report = {}
    for path in args.captures:
        chains, _, _ = scan(spec, path)
        starts = sorted(c[0] for c in chains)
        report[path] = {
            'chains': len(chains),
            'starts': [iso(t) for t in starts],
            'gaps_hours': [round((b - a) / 3600, 2)
                           for a, b in zip(starts, starts[1:])],
            'spans_seconds': sorted(round(c[1] - c[0]) for c in chains),
        }
    print(json.dumps(report, indent=1))
    return 0


def cmd_accept(args):
    spec = load_spec(args.spec)
    report, bad, chain_keys = {'on': {}, 'off': {}}, False, set()
    for path in args.on:
        chains, _, _ = scan(spec, path)
        chain_keys |= {c[2] for c in chains}
        report['on'][path] = {'chains': len(chains)}
    for path in args.off:
        chains, keys, hits = scan(spec, path)
        missing_steps = [i for i, n in enumerate(hits) if n == 0]
        missing_keys = sorted(k.replace('\x1f', ' | ')
                              for k in chain_keys - keys)
        report['off'][path] = {
            'chains': len(chains),
            'step_hits': hits,
            'missing_steps': missing_steps,
            'missing_chain_keys': missing_keys,
        }
        bad = bad or bool(chains or missing_steps or missing_keys)
    report['chain_keys_in_on'] = len(chain_keys)
    report['ok'] = not bad
    print(json.dumps(report, indent=1, ensure_ascii=False))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('count', help='chains, starts and gaps per capture')
    c.add_argument('spec')
    c.add_argument('captures', nargs='+')
    a = sub.add_parser('accept', help='background vs anomaly acceptance')
    a.add_argument('spec')
    a.add_argument('--off', nargs='+', required=True)
    a.add_argument('--on', nargs='+', required=True)
    args = ap.parse_args()
    sys.exit(cmd_count(args) if args.cmd == 'count' else cmd_accept(args))


if __name__ == '__main__':
    main()
