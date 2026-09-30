import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import slot  # noqa: E402

SLOT = str(Path(__file__).resolve().parents[1] / 'slot.py')


class SlotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['CONTENT_DESIGN_STATE'] = self.tmp.name
        os.environ['CONTENT_DESIGN_MEM_MB'] = '1024'

    def tearDown(self):
        self.tmp.cleanup()

    def test_capacity_follows_budget(self):
        self.assertEqual(slot.capacity('memory'), 1024 // slot.UNIT_MB)
        self.assertEqual(slot.capacity('docs-build'), 1)

    def test_memory_over_budget_waits(self):
        first = slot.acquire(mem_mb=768)
        self.assertIsNotNone(first)
        self.assertIsNone(slot.acquire(mem_mb=512, wait=0.6))
        small = slot.acquire(mem_mb=256, wait=0.6)
        self.assertIsNotNone(small)
        small.release()
        first.release()
        again = slot.acquire(mem_mb=512, wait=0.6)
        self.assertIsNotNone(again)
        again.release()

    def test_waiter_proceeds_after_release(self):
        first = slot.acquire(mem_mb=1024)
        got = {}

        def waiter():
            got['lease'] = slot.acquire(mem_mb=512, wait=5)

        t = threading.Thread(target=waiter)
        t.start()
        time.sleep(0.8)
        self.assertNotIn('lease', got)
        first.release()
        t.join()
        self.assertIsNotNone(got['lease'])
        got['lease'].release()

    def test_exclusive_pool_admits_one(self):
        a = slot.acquire(pools=['docs-build'])
        self.assertIsNone(slot.acquire(pools=['docs-build'], wait=0.6))
        b = slot.acquire(pools=['git-x'], wait=0.6)
        self.assertIsNotNone(b)
        b.release()
        a.release()

    def test_killed_holder_frees_slot(self):
        holder = subprocess.Popen(
            [sys.executable, SLOT, 'run', '--pool', 'docs-build', '--',
             sys.executable, '-c', 'import time; time.sleep(30)'],
            env=os.environ.copy())
        deadline = time.time() + 10
        while time.time() < deadline and not slot.status()['holders']:
            time.sleep(0.2)
        self.assertTrue(slot.status()['holders'])
        self.assertIsNone(slot.acquire(pools=['docs-build'], wait=0.6))
        holder.kill()
        holder.wait()
        lease = slot.acquire(pools=['docs-build'], wait=5)
        self.assertIsNotNone(lease)
        lease.release()

    def test_timeout_kills_tree(self):
        res = slot.run([sys.executable, '-c', 'import time; time.sleep(30)'],
                       mem_mb=64, timeout=1)
        self.assertEqual(res['exit'], 124)
        self.assertEqual(res['reason'], 'timeout')
        self.assertLess(res['wall_s'], 10)
        self.assertEqual(slot.status()['holders'], [])

    @unittest.skipUnless(sys.platform.startswith('linux'), 'RSS watchdog is Linux only')
    def test_memory_watchdog(self):
        code = 'x = bytearray(400 * 1024 * 1024); import time; time.sleep(20)'
        res = slot.run([sys.executable, '-c', code], mem_mb=128, timeout=30)
        self.assertEqual(res['exit'], 137)
        self.assertEqual(res['reason'], 'memory')

    def test_exit_code_passes_through(self):
        res = slot.run([sys.executable, '-c', 'raise SystemExit(3)'], mem_mb=64)
        self.assertEqual(res['exit'], 3)
        self.assertEqual(res['reason'], 'exit')


if __name__ == '__main__':
    unittest.main()
