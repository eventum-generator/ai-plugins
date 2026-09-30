import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import capture  # noqa: E402

W = datetime.fromisoformat(capture.WINDOW_START)


def config():
    return {
        'input': [
            {'time_patterns': {'tags': ['people'], 'patterns': ['patterns/day.yml', 'patterns/week.yml']}},
            {'cron': {'expression': '0 22 * * *', 'count': 3, 'start': 'now', 'end': 'never', 'tags': ['jobs']}},
            {'timer': {'seconds': 900, 'count': 2}},
        ],
        'event': {'template': {'mode': 'all', 'params': {'anomaly_mode': True, 'anomaly_interval_hours': 24},
                               'templates': [{'e': {'template': 'templates/e.json.jinja'}}]}},
        'output': [{'stdout': {'formatter': {'format': 'json'}}}],
    }


def patterns(root):
    return {
        (root / 'patterns/day.yml').resolve(): {
            'oscillator': {'period': 1, 'unit': 'days', 'start': '2026-01-01T00:00:00Z', 'end': 'never'},
            'multiplier': {'ratio': 100}},
        (root / 'patterns/week.yml').resolve(): {
            'oscillator': {'period': 7, 'unit': 'days', 'start': '2026-01-05T00:00:00+00:00', 'end': 'never'},
            'multiplier': {'ratio': 700}},
    }


class BoundTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_every_input_bounded(self):
        cfg, pats = config(), patterns(self.root)
        capture.bound(self.root, cfg, pats, W, 4)
        end = W + timedelta(days=4)
        day, week = pats.values()
        self.assertEqual(day['oscillator']['start'], W.isoformat())
        self.assertEqual(day['oscillator']['end'], end.isoformat())
        # Monday anchor keeps its weekly phase: the window start is a Monday.
        self.assertEqual(week['oscillator']['start'], W.isoformat())
        cron = cfg['input'][1]['cron']
        self.assertEqual(cron['start'], W.isoformat())
        self.assertEqual(cron['end'], (end - timedelta(seconds=1)).isoformat())
        timer = cfg['input'][2]['timer']
        self.assertEqual(timer['repeat'], 4 * 86400 // 900)

    def test_phase_kept_for_offset_anchor(self):
        start = capture.aligned_start('2026-01-01T00:00:00+03:00', 86400, W)
        self.assertGreaterEqual(start, W)
        self.assertEqual((start - datetime.fromisoformat('2026-01-01T00:00:00+03:00')).total_seconds() % 86400, 0)

    def test_missing_key_named(self):
        cfg, pats = config(), patterns(self.root)
        del cfg['input'][1]['cron']['end']
        with self.assertRaisesRegex(capture.CaptureError, 'cron input: end'):
            capture.bound(self.root, cfg, pats, W, 4)
        cfg, pats = config(), patterns(self.root)
        del next(iter(pats.values()))['oscillator']['start']
        with self.assertRaisesRegex(capture.CaptureError, 'day.yml'):
            capture.bound(self.root, cfg, pats, W, 4)

    def test_scale_live_keeps_times(self):
        cfg, pats = config(), patterns(self.root)
        capture.bound(self.root, cfg, pats, W, 1, scale=10, live=True)
        day = next(iter(pats.values()))
        self.assertEqual(day['oscillator']['end'], 'never')
        self.assertEqual(day['multiplier']['ratio'], 1000)
        self.assertEqual(cfg['input'][1]['cron']['count'], 30)
        self.assertEqual(cfg['input'][2]['timer']['count'], 20)

    def test_http_input_refused(self):
        cfg = config()
        cfg['input'] = [{'http': {'port': 8080}}]
        with self.assertRaises(capture.CaptureError):
            capture.bound(self.root, cfg, {}, W, 1)

    def test_mode_and_output(self):
        cfg = config()
        capture.set_mode(cfg, 'off', 6)
        params = cfg['event']['template']['params']
        self.assertEqual((params['anomaly_mode'], params['anomaly_interval_hours']), (False, 6))
        capture.file_output(cfg, self.root / 'out.jsonl')
        (out,) = cfg['output']
        self.assertEqual(out['file']['formatter'], {'format': 'json'})
        self.assertEqual(out['file']['separator'], '\n')
        cfg['event']['template']['params'] = {}
        with self.assertRaises(capture.CaptureError):
            capture.set_mode(cfg, 'on', None)


if __name__ == '__main__':
    unittest.main()
