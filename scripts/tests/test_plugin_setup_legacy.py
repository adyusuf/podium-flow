"""scripts/plugin-setup.py — an install under the plugin's old name, adyusuf (from adyusuf/claude-code-standards), moves to
podium in its own repository (02/11/2026, rule #4). The new one is linked and installed first, in the old install's
branch and scope; then the old plugin is removed, its data kept; a disabled one stays disabled; the desktop app's
CLAUDE_CODE_PLUGIN_DIRS follows; the old marketplace link stays for sessions still running.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plugin_setup_helpers import Case, Fake, NEW, OLD, setup  # noqa: E402

OLD_DIR = '/home/u/.claude/plugins/marketplaces/adyusuf-marketplace'


class LegacyFake(Fake):
    """The old plugin and its marketplace link are there; uninstalling or unlinking takes them away."""

    def __init__(self, home, ref='prod', scope='user', **given):
        self.legacy_market = {'name': setup.LEGACY_MARKETPLACE, 'source': 'github', 'repo': setup.REPO, 'ref': ref}
        self.legacy_installed, self.legacy_scope = True, scope
        super().__init__(home, **given)

    def write(self, sha, scope='user'):
        self.current = sha
        super().write(sha, scope)
        if getattr(self, 'legacy_installed', False):
            with open(self.record, encoding='utf-8') as handle:
                data = json.load(handle)
            data['plugins'][setup.LEGACY_ID] = [{'scope': self.legacy_scope, 'version': OLD[:12], 'gitCommitSha': OLD,
                                                 'installPath': '/old'}]
            with open(self.record, 'w', encoding='utf-8') as handle:
                json.dump(data, handle)

    def __call__(self, command):
        key = ' '.join(command[:4])
        if command[:4] == ['claude', 'plugin', 'uninstall', setup.LEGACY_ID] and not any(key.startswith(f) for f in self.fail):
            self.commands.append(command)
            self.legacy_installed = False
            self.write(self.current)           # the new plugin stays as it is
            return 0, 'ok uninstall'
        return super().__call__(command)

    def marketplace(self, action):
        if action == 'list':
            listed = ([self.market] if self.market else []) + ([self.legacy_market] if self.legacy_market else [])
            return 0, json.dumps(listed)
        if action == 'remove':
            self.legacy_market = None
        return super().marketplace(action)


class Legacy(Case):
    def settings(self, data):
        path = os.path.join(self.home, '.claude', 'settings.json')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(data, handle)
        return path

    def claude(self, fake):
        return [c[2:] for c in fake.commands if c[0] == 'claude']

    def test_the_new_one_comes_first_in_the_old_scope_and_branch_then_the_old_plugin_goes_and_its_link_stays(self):
        fake = LegacyFake(self.home, ref='test', scope='project')
        code, out, _ = self.go(fake)
        self.assertEqual(code, 0)
        self.assertEqual('adyusuf/podium-flow', setup.REPO)
        self.assertEqual(self.claude(fake)[1:], [
            ['marketplace', 'add', f'{setup.REPO}#test'],
            ['install', setup.PLUGIN_ID, '--scope', 'project'],
            ['uninstall', setup.LEGACY_ID, '--keep-data', '--scope', 'project']])
        self.assertIsNotNone(fake.legacy_market)
        self.assertIn(f'found the plugin under its old name ({setup.LEGACY_ID})', out)
        self.assertIn(f'claude plugin marketplace remove {setup.LEGACY_MARKETPLACE}', out)
        self.assertIn('✓ podium@podium-marketplace', out)

    def test_it_asks_first_and_a_no_changes_nothing(self):
        fake = LegacyFake(self.home)
        code, out, _ = self.go(fake, answer='n')
        self.assertEqual((0, ['marketplace']), (code, [c[0] for c in self.claude(fake)]))
        self.assertIn('left as it is', out)
        self.assertEqual(2, self.go(LegacyFake(self.home), tty=False)[0])        # no terminal and no --yes

    def test_check_only_says_the_move_is_due(self):
        fake = LegacyFake(self.home)
        code, out, _ = self.go(fake, '--check')
        self.assertEqual(code, 1)
        self.assertIn('moving from the old name is due', out)
        self.assertEqual([['marketplace', 'list', '--json']], self.claude(fake))

    def test_github_not_answering_changes_nothing(self):
        fake = LegacyFake(self.home, fail=('git',))
        code, out, _ = self.go(fake)
        self.assertEqual(2, code)
        self.assertEqual([['marketplace', 'list', '--json']], self.claude(fake))
        self.assertTrue(fake.legacy_installed)

    def test_a_failing_new_link_leaves_the_old_install_and_a_failing_removal_says_both_are_there(self):
        fake = LegacyFake(self.home, fail=('claude plugin marketplace add',))
        code, out, _ = self.go(fake)
        self.assertEqual(2, code)
        self.assertTrue(fake.legacy_installed)
        self.assertIn('the old one is left as it was', out)
        self.assertIn(f'claude plugin marketplace add {setup.REPO}#prod && claude plugin install {setup.PLUGIN_ID}', out)
        fake = LegacyFake(self.home, fail=('claude plugin uninstall',))
        code, out, _ = self.go(fake)
        self.assertEqual(0, code)
        self.assertIn(f'both are installed now; remove the old one with: claude plugin uninstall {setup.LEGACY_ID}', out)

    def test_a_disabled_old_install_stays_disabled_and_the_desktop_folder_follows(self):
        path = self.settings({'enabledPlugins': {setup.LEGACY_ID: False}, 'env': {'CLAUDE_CODE_PLUGIN_DIRS': OLD_DIR}})
        fake = LegacyFake(self.home)
        fake.enable = lambda: None            # the fake's install would rewrite settings.json; keep the test's own
        code, out, _ = self.go(fake)
        self.assertEqual(code, 0)
        self.assertIn(['disable', setup.PLUGIN_ID], self.claude(fake))
        with open(path, encoding='utf-8') as handle:
            self.assertEqual(OLD_DIR.replace('adyusuf-marketplace', 'podium-marketplace'),
                             json.load(handle)['env']['CLAUDE_CODE_PLUGIN_DIRS'])
        backup = os.path.join(self.home, '.claude-standards', 'backups')
        self.assertTrue(any('settings.json' in files for _, _, files in os.walk(backup)))

    def test_without_the_old_name_nothing_extra_runs(self):
        fake = Fake(self.home, installed=NEW, market={'name': setup.MARKETPLACE, 'source': 'github', 'repo': setup.REPO, 'ref': 'prod'})
        self.assertEqual(self.go(fake)[0], 0)
        self.assertEqual(fake.verbs(), ['claude plugin marketplace', 'git'])


if __name__ == '__main__':
    unittest.main()
