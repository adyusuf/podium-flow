"""The test deploy check of the prod gate (GATE_CHECK_TEST_DEPLOY, CLAUDE.md #33) - moved verbatim out of
test_gate_core_prod.py so both files stay under the 300-line limit (rule #9). The fixture (ProdGate) and the
covered conf stay there; the reasons the check must fail closed are in that file's docstring.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_gate_core_prod import COVERED, ProdGate  # noqa: E402


class DeployVerification(ProdGate):
    """GATE_CHECK_TEST_DEPLOY=1: the previous behaviour, now opt-in."""

    def run_gate(self, *args, **kw):
        kw.setdefault('env_extra', {'GATE_CHECK_TEST_DEPLOY': '1'})
        return super().run_gate(*args, **kw)

    def test_with_no_source_configured_it_skips_and_does_not_pass(self):
        self.setup_project()
        out, code = self.run_gate()
        self.assertIn('the deployed SHA cannot be read', out)
        self.assertIn('GATE INCOMPLETE', out)
        self.assertNotEqual(0, code, 'an unverified deploy must never exit 0')

    def test_a_command_reporting_this_sha_passes(self):
        sha = self.setup_project()
        # Written AFTER the commit and left uncommitted on purpose: the conf has
        # to name HEAD's own SHA, and committing it would move HEAD.
        self.write('scripts/merge-gate.conf', COVERED + f'TEST_DEPLOY_SHA_CMD="echo {sha}"\n')
        out, _ = self.run_gate()
        self.assertIn('the test environment is running this code', out)

    def test_a_command_reporting_a_different_sha_fails(self):
        self.setup_project(conf='TEST_DEPLOY_SHA_CMD="echo deadbeefdeadbeef"\n')
        out, code = self.run_gate()
        self.assertIn('not', out)
        self.assertIn('GATE CLOSED', out)
        self.assertEqual(1, code)

    def test_html_from_the_version_endpoint_is_a_failure_not_a_sha(self):
        # Recorded incident: the SPA fallback answers /version with index.html,
        # and a lenient reader finds a hex-looking string in the bundle name.
        self.stub('curl', '#!/bin/sh\necho "<!DOCTYPE html><html>deadbeef</html>"\n')
        self.setup_project(conf='TEST_VERSION_URL="http://test.example/version"\n')
        out, code = self.run_gate()
        self.assertIn('returned HTML, not a version', out)
        self.assertEqual(1, code)

    def test_a_version_endpoint_with_no_sha_fails(self):
        self.stub('curl', '#!/bin/sh\necho "ok"\n')
        self.setup_project(conf='TEST_VERSION_URL="http://test.example/version"\n')
        out, code = self.run_gate()
        self.assertIn('reports no commit SHA', out)
        self.assertEqual(1, code)

    def test_two_sites_reporting_different_shas_are_not_deployed(self):
        # A project with several sites on test is deployed only when ALL agree.
        self.stub('curl', '#!/bin/sh\ncase "$*" in *one*) echo aaaaaaa;; *) echo bbbbbbb;; esac\n')
        self.setup_project(conf='TEST_VERSION_URL="http://one.example/v http://two.example/v"\n')
        out, code = self.run_gate()
        self.assertIn('while another site reports', out)
        self.assertEqual(1, code)

    def test_a_matching_short_sha_from_the_endpoint_passes(self):
        sha = self.setup_project(conf='TEST_VERSION_URL="http://test.example/version"\n')
        self.stub('curl', f'#!/bin/sh\necho "{sha[:7]}"\n')  # the short SHA must satisfy it
        out, _ = self.run_gate()
        self.assertIn('the test environment is running this code', out)


class TestEnvironmentIsNotCheckedByDefault(ProdGate):
    """User decision 04/10/2026 (CLAUDE.md #33): the prod gate does not look at the test branch or the
    test environment unless GATE_CHECK_TEST_DEPLOY=1 asks for it."""

    def test_a_project_with_no_test_environment_is_not_blocked(self):
        self.setup_project()
        out, code = self.run_gate()
        self.assertIn('NOT checked', out)
        self.assertNotIn('the deployed SHA cannot be read', out)
        self.assertNotIn('GATE INCOMPLETE', out)
        self.assertEqual(0, code, out)

    def test_a_configured_source_is_not_consulted(self):
        self.stub('curl', '#!/bin/sh\necho SHOULD_NOT_RUN\n')
        self.setup_project(conf='TEST_VERSION_URL="http://test.example/version"\n')
        out, code = self.run_gate()
        self.assertNotIn('SHOULD_NOT_RUN', out)
        self.assertEqual(0, code, out)

    def test_a_stale_test_environment_does_not_close_the_gate(self):
        self.setup_project(conf='TEST_DEPLOY_SHA_CMD="echo deadbeefdeadbeef"\n')
        out, code = self.run_gate()
        self.assertNotIn('GATE CLOSED', out)
        self.assertEqual(0, code, out)

    def test_the_warning_says_what_was_not_proven(self):
        self.setup_project()
        out, _ = self.run_gate()
        self.assertIn('does not prove the code ran on test', out)

    def test_the_list_mode_agrees_with_the_real_run(self):
        self.setup_project()
        listed, list_code = self.run_gate('--list')
        self.assertIn('NOT checked', listed)
        self.assertNotIn('deploy verification', listed)
        self.assertEqual(0, list_code, listed)

    def test_the_dev_and_test_promotions_do_not_mention_it(self):
        self.setup_project()
        for target in ('dev', 'test'):
            out, _ = self.run_gate(target=target)
            self.assertNotIn('test branch / test environment', out, target)


class ListMode(ProdGate):
    """--list with the deploy check requested (GATE_CHECK_TEST_DEPLOY=1)."""

    def run_gate(self, *args, **kw):
        kw.setdefault('env_extra', {'GATE_CHECK_TEST_DEPLOY': '1'})
        return super().run_gate(*args, **kw)

    def test_the_list_mode_names_the_deploy_check_without_running_it(self):
        self.stub('curl', '#!/bin/sh\necho SHOULD_NOT_RUN\n')
        self.setup_project(conf='TEST_VERSION_URL="http://test.example/version"\n')
        out, _ = self.run_gate('--list')
        self.assertIn('deploy verification', out)
        self.assertNotIn('SHOULD_NOT_RUN', out)

    def test_the_list_mode_reaches_the_same_verdict_as_the_real_run(self):
        # --list used to print "<no source configured — would block>" and then count
        # the step as PASS, so the dry run said GATE GREEN while the real run said
        # INCOMPLETE. The dry run is what gets read before asking for a promotion, so
        # a disagreement there is worse than having no dry run at all.
        self.setup_project()
        listed, list_code = self.run_gate('--list')
        real, real_code = self.run_gate()
        self.assertIn('the deployed SHA cannot be read', listed)
        self.assertIn('GATE INCOMPLETE', listed)
        self.assertNotEqual(0, list_code)
        for verdict in ('GATE INCOMPLETE', 'the deployed SHA cannot be read'):
            self.assertEqual(verdict in listed, verdict in real, verdict)

    def test_the_list_mode_still_passes_the_step_when_a_source_is_configured(self):
        self.stub('curl', '#!/bin/sh\necho SHOULD_NOT_RUN\n')
        self.setup_project(conf='TEST_VERSION_URL="http://test.example/version"\n')
        out, _ = self.run_gate('--list')
        self.assertIn('deploy verification', out)
        self.assertNotIn('the deployed SHA cannot be read', out)
        self.assertNotIn('SHOULD_NOT_RUN', out)


if __name__ == '__main__':
    unittest.main()
