import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import measure  # noqa: E402

T0 = 1788134400  # 2026-08-31T00:00:00Z


def iso(t):
    return measure.iso(t)


def write(path, rows, gz=False):
    data = ''.join((r if isinstance(r, str) else json.dumps(r)) + '\n' for r in rows)
    if gz:
        with gzip.open(path, 'wt', encoding='utf-8') as fh:
            fh.write(data)
    else:
        Path(path).write_text(data, encoding='utf-8')
    return str(path)


CHAIN = {
    'timestamp': {'path': '@timestamp'},
    'class': {'path': 'event.action'},
    'actor': {'path': 'user.name'},
    'chain': {
        'key': {'path': 'user.name'}, 'within': 600,
        'steps': [
            {'match': {'path': 'event.action', 'values': ['fail']}},
            {'match': {'path': 'event.action', 'values': ['fail']}},
            {'match': {'all': [{'path': 'event.action', 'values': ['login']},
                               {'path': 'event.risk', 'gt': 70}]}},
        ],
    },
}


def ev(t, action, user='alice', **extra):
    row = {'@timestamp': iso(t), 'event': {'action': action}, 'user': {'name': user}}
    row['event'].update(extra)
    return row


class ChainTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def scan(self, rows, spec=CHAIN, gz=False):
        return measure.scan(spec, write(self.dir / ('c.jsonl.gz' if gz else 'c.jsonl'), rows, gz))

    def test_complete_chain_counted_once(self):
        rows = [ev(T0, 'fail'), ev(T0 + 1, 'fail'), ev(T0 + 2, 'fail'), ev(T0 + 3, 'login', risk=90)]
        res = self.scan(rows, gz=True)
        self.assertEqual(len(res['chains']), 1)
        self.assertEqual(res['chains'][0][3], 'alice')

    def test_numeric_threshold(self):
        rows = [ev(T0, 'fail'), ev(T0 + 1, 'fail'), ev(T0 + 2, 'login', risk=50)]
        self.assertEqual(len(self.scan(rows)['chains']), 0)
        rows[-1] = ev(T0 + 2, 'login', risk='71')
        self.assertEqual(len(self.scan(rows)['chains']), 1)

    def test_expiry_and_keys(self):
        rows = [ev(T0, 'fail'), ev(T0 + 700, 'fail'), ev(T0 + 701, 'login', risk=90)]
        self.assertEqual(len(self.scan(rows)['chains']), 0)
        rows = [ev(T0, 'fail'), ev(T0 + 1, 'fail', user='bob'), ev(T0 + 2, 'login', risk=90)]
        self.assertEqual(len(self.scan(rows)['chains']), 0)

    def test_every_binding_kept(self):
        # A later first step must not be lost when an earlier one advances.
        rows = [ev(T0, 'fail'), ev(T0 + 590, 'fail'), ev(T0 + 700, 'fail'),
                ev(T0 + 800, 'login', risk=90)]
        self.assertEqual(len(self.scan(rows)['chains']), 1)

    def test_repeated_last_step_is_one_episode(self):
        rows = [ev(T0, 'fail'), ev(T0 + 1, 'fail'), ev(T0 + 2, 'login', risk=90),
                ev(T0 + 3, 'login', risk=90), ev(T0 + 4, 'login', risk=90)]
        self.assertEqual(len(self.scan(rows)['chains']), 1)

    def test_many_first_steps_stay_linear(self):
        import time as _t
        rows = [ev(T0 + i * 0.5, 'fail') for i in range(20000)]
        began = _t.monotonic()
        res = self.scan(rows)
        self.assertLess(_t.monotonic() - began, 10)
        self.assertEqual(res['chains'], [])

    def test_window_clip_and_bool_values(self):
        spec = {'class': {'path': 'event.action'},
                'groups': {'ok': {'path': 'event.ok', 'values': [True]}}}
        rows = [ev(T0 - 10, 'x', ok=True), ev(T0, 'x', ok=True), ev(T0 + 5, 'x', ok=False)]
        res = measure.scan(spec, write(self.dir / 'w.jsonl', rows), T0, T0 + 86400)
        self.assertEqual(res['outside_window'], 1)
        self.assertEqual(res['groups']['ok']['records'], 1)

    def test_identical_steps_need_distinct_records(self):
        spec = {'chain': {'key': {'path': 'user.name'}, 'within': 3600,
                          'steps': [{'match': {'path': 'event.action', 'values': ['q']}}] * 4}}
        for n, expected in ((3, 0), (4, 1), (7, 1)):
            rows = [ev(T0 + i * 60, 'q') for i in range(n)]
            self.assertEqual(len(self.scan(rows, spec)['chains']), expected, n)
        rows = [ev(T0, 'q'), ev(T0 + 3000, 'q'), ev(T0 + 3500, 'q'), ev(T0 + 4000, 'q'), ev(T0 + 4100, 'q')]
        self.assertEqual(len(self.scan(rows, spec)['chains']), 1)  # the run from 3000 completes at 4100

    def test_linked_step_pairs(self):
        spec = {'chain': {'key': {'path': 'user.name'}, 'within': 600, 'steps': [
            {'match': {'path': 'event.action', 'values': ['login']}},
            {'match': {'path': 'event.action', 'values': ['token-created']}, 'bind': {'T': 'token'}},
            {'match': {'path': 'event.action', 'values': ['token-revoked']},
             'eq': {'T': {'path': 'message', 'regex': 'token (\\w+)'}}}]}}
        rows = [ev(T0, 'login'), dict(ev(T0 + 1, 'token-created'), token='a1'),
                dict(ev(T0 + 2, 'token-revoked'), message='revoked token b2')]
        pairs = measure.step_pairs(spec, [write(self.dir / 'p.jsonl', rows)], [(None, None)])
        self.assertEqual(pairs['steps 0-1'], [1])
        self.assertEqual(pairs['steps 1-2'], [0])  # created and revoked, but never the same token
        self.assertEqual(pairs['steps 0-2'], [1])

    def test_presence_of_pairs(self):
        spec = dict(CHAIN, presence={'pair': {'paths': ['user.name', 'event.ip']}})
        on = measure.scan(spec, write(self.dir / 'on2.jsonl', [
            ev(T0, 'fail', ip='1'), ev(T0 + 1, 'fail', ip='1'), ev(T0 + 2, 'login', risk=90, ip='1')]))
        off = measure.scan(spec, write(self.dir / 'off2.jsonl', [ev(T0, 'fail', ip='2')]))
        rep = measure.presence([off], [on])
        self.assertEqual(rep['pair']['absent_in_some_background'], ['alice|1'])
        self.assertEqual(rep['actor']['absent_in_some_background'], [])

    def test_accept_report(self):
        off = self.scan([ev(T0, 'fail'), ev(T0 + 2, 'login', risk=90)])
        on = measure.scan(CHAIN, write(self.dir / 'on.jsonl', [
            ev(T0, 'fail', user='carol'), ev(T0 + 1, 'fail', user='carol'),
            ev(T0 + 2, 'login', user='carol', risk=90)]))
        rep = measure.chains_report([off], [on])
        self.assertFalse(rep['ok'])
        (v,) = rep['off'].values()
        self.assertEqual(v['missing_steps'], [])
        self.assertEqual(v['missing_chain_keys'], ['carol'])


class ParseProfileTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_native_lines(self):
        spec = {'parse': {'regex': r'^(?P<ts>\S+) (?P<host>\S+) sshd\[\d+\]: (?P<msg>(?P<verb>\w+) .*)$'},
                'timestamp': {'path': 'ts'}, 'class': {'path': 'verb'}}
        rows = ['%s h1 sshd[42]: Accepted password for alice' % iso(T0),
                '%s h1 sshd[43]: Failed password for bob' % iso(T0 + 3600),
                'garbage line']
        res = measure.scan(spec, write(self.dir / 'n.log', rows))
        self.assertEqual(res['records'], 2)
        self.assertEqual(res['unparsed'], 1)
        prof = measure.profile([res])
        self.assertEqual(prof['class_share_pct'], {'Accepted': 50.0, 'Failed': 50.0})
        self.assertEqual(prof['hourly_pct_utc'][0], 50.0)

    def test_time_formats(self):
        self.assertEqual(measure.parse_time('2026-08-31T00:00:00+0000'), T0)
        self.assertEqual(measure.parse_time(str(T0 * 1000000)), T0)
        self.assertEqual(measure.parse_time(str(T0 * 1000000000)), T0)
        self.assertAlmostEqual(measure.parse_time('2026-08-31T00:00:00.123456789Z'), T0 + 0.123456)

    def test_lone_cr_is_not_a_record_break(self):
        spec = {'parse': {'regex': r'^(?P<ts>\S+) (?P<msg>.*)$'}, 'timestamp': {'path': 'ts'}}
        path = self.dir / 'cr.log'
        path.write_bytes(('%s a\rb\n%s c\n' % (iso(T0), iso(T0 + 1))).encode())
        self.assertEqual(measure.scan(spec, str(path))['records'], 2)

    def test_syslog_time_without_year(self):
        spec = {'parse': {'regex': r'^(?P<ts>\w{3} [ \d]\d \d\d:\d\d:\d\d) (?P<rest>.*)$'},
                'timestamp': {'path': 'ts', 'format': '%b %d %H:%M:%S', 'year': 2026}}
        res = measure.scan(spec, write(self.dir / 's.log', ['Aug 31 10:00:00 x', 'Aug 31 11:00:00 y']))
        self.assertEqual(res['records'], 2)
        self.assertEqual(res['hours'][10], 1)

    def test_sequences_and_window_days(self):
        spec = {'class': {'path': 'event.action'},
                'sequences': {'login-to-logout': {'group': {'path': 'user.name'},
                                                  'from': {'path': 'event.action', 'values': ['login']},
                                                  'to': {'path': 'event.action', 'values': ['logout']}}}}
        rows = [ev(T0 + 3600, 'login'), ev(T0 + 3700, 'logout'),
                ev(T0 + 86400 + 10, 'login', user='bob'), ev(T0 + 86400 + 40, 'logout', user='bob')]
        res = measure.scan(spec, write(self.dir / 'seq.jsonl', rows), T0, T0 + 2 * 86400)
        prof = measure.profile([res])
        self.assertEqual(prof['sequence_delays_s']['login-to-logout']['max'], 100)
        self.assertEqual(prof['per_day_utc']['min'], 2)  # both days lie wholly inside the window

    def test_groups_and_order(self):
        spec = {'class': {'path': 'event.action'},
                'groups': {'failures': {'path': 'event.action', 'values': ['fail']}}}
        rows = [ev(T0 + 7200, 'fail'), ev(T0, 'ok'), ev(T0 + 7201, 'ok')]
        res = measure.scan(spec, write(self.dir / 'g.jsonl', rows))
        self.assertEqual(res['order_breaks'], 1)
        prof = measure.profile([res])
        self.assertEqual(prof['groups']['failures']['share_pct'], 33.33)


class DigestTest(unittest.TestCase):
    def test_changed_files(self):
        root = Path(tempfile.mkdtemp())
        (root / 'templates').mkdir()
        (root / 'generator.yml').write_text('a')
        (root / 'templates' / 'e.jinja').write_text('b')
        (root / 'output').mkdir()
        (root / 'output' / 'x.json').write_text('ignored')
        first = measure.digest(str(root))
        self.assertEqual(sorted(first['files']), ['generator.yml', 'templates/e.jinja'])
        prev = root.parent / (root.name + '-digest.json')
        prev.write_text(json.dumps(first))
        (root / 'templates' / 'e.jinja').write_text('c')
        (root / 'README.md').write_text('d')
        second = measure.digest(str(root), str(prev))
        self.assertNotEqual(first['digest'], second['digest'])
        self.assertEqual(second['changed'], ['templates/e.jinja'])
        self.assertEqual(second['added'], ['README.md'])


if __name__ == '__main__':
    unittest.main()
