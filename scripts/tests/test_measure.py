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
        self.assertEqual(prof['hourly_pct'][0], 50.0)

    def test_syslog_time_without_year(self):
        spec = {'parse': {'regex': r'^(?P<ts>\w{3} [ \d]\d \d\d:\d\d:\d\d) (?P<rest>.*)$'},
                'timestamp': {'path': 'ts', 'format': '%b %d %H:%M:%S', 'year': 2026}}
        res = measure.scan(spec, write(self.dir / 's.log', ['Aug 31 10:00:00 x', 'Aug 31 11:00:00 y']))
        self.assertEqual(res['records'], 2)
        self.assertEqual(res['hours'][10], 1)

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
