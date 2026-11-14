"""twin-drift.sh reads each project's LOCAL origin/dev and fetches nothing (F-025).

That is deliberate (a gate does not go to the network), but a stale ref then looks current, so the
script says it in its header. Split from test_twin_drift.py, which is already over 300 lines (#9);
it reuses that file's Fleet fixture.
"""
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_twin_drift import Fleet, git  # noqa: E402

HEADER = "compares each project's LOCAL origin/dev as last fetched — nothing is fetched here"


class TheFetchIsNamed(Fleet):
    def test_the_header_says_the_local_origin_dev_is_compared_without_fetching(self):
        self.project('alpha', '#!/usr/bin/env bash\necho canonical\n')
        out, code = self.run_drift()
        self.assertEqual(0, code, out)
        self.assertIn(HEADER, out)

    def test_the_header_is_printed_when_there_is_nothing_to_compare_too(self):
        empty = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, empty, True)
        out, code = self.run_drift(search=empty)
        self.assertEqual(0, code, out)
        self.assertIn(HEADER, out)

    def test_a_push_the_checkout_has_not_fetched_is_not_seen(self):
        # What the header warns about: another clone pushed a stale copy to origin, this checkout never
        # fetched it, and its origin/dev still carries the aligned blob.
        self.project('alpha', '#!/usr/bin/env bash\necho canonical\n')
        other = os.path.join(self.home, 'alpha-other')
        git(self.home, 'clone', '-q', '-b', 'dev', os.path.join(self.home, 'alpha.git'), other)
        git(other, 'config', 'user.email', 't@t')
        git(other, 'config', 'user.name', 't')
        self.write(other, 'scripts/gate-core.sh', '#!/usr/bin/env bash\necho STALE\n')
        git(other, 'commit', '-qam', 'stale')
        git(other, 'push', '-q', 'origin', 'dev')
        shutil.rmtree(other)                 # a checkout beside the others would be compared as a project
        out, code = self.run_drift()
        self.assertEqual(0, code, out)
        self.assertIn('alpha: aligned', out)
        git(os.path.join(self.home, 'alpha'), 'fetch', '-q', 'origin')
        out, code = self.run_drift()
        self.assertEqual(1, code, out)


if __name__ == '__main__':
    import unittest
    unittest.main()
