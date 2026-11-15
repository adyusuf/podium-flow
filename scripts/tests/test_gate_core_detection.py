"""Stack detection and the build target of the shared gate - moved verbatim out of test_gate_core_fixes.py so
both files stay under the 300-line limit (rule #9). Whether a tier is checked at all, and what `dotnet build` is
handed. The gate is run from its real path; see the note in test_gate_core_fixes.py.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_gate_core_fixes import ANSI, GATE  # noqa: E402


class StackDetection(unittest.TestCase):
    """Whether a tier is checked at all. A miss here is silent and total."""

    def tearDown(self):
        shutil.rmtree(getattr(self, 'root', ''), ignore_errors=True)

    def build(self, files):
        root = tempfile.mkdtemp()
        subprocess.run(['git', 'init', '-q', root], check=True)
        os.makedirs(os.path.join(root, 'scripts'))
        for name in files:
            path = os.path.join(root, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write('<Project />')
        self.root = root
        result = subprocess.run(['bash', GATE, 'test', '--list'],
                                cwd=root, capture_output=True, text=True)
        return ANSI.sub('', result.stdout)

    def test_a_slnx_solution_is_detected(self):
        out = self.build(['App.slnx'])
        self.assertIn('dotnet build', out, f".slnx was not detected:\n{out}")

    def test_a_csproj_two_levels_down_is_detected(self):
        out = self.build(['src/Api/Api.csproj'])
        self.assertIn('dotnet build', out, f"a nested csproj was not detected:\n{out}")

    def test_a_repository_with_no_dotnet_is_left_alone(self):
        out = self.build(['README.md'])
        self.assertNotIn('dotnet build', out)


class NodeDetection(unittest.TestCase):
    """The rule-#16 document step must not skip a repository whose JS is nested."""

    def tearDown(self):
        shutil.rmtree(getattr(self, 'root', ''), ignore_errors=True)

    def build(self, files):
        root = tempfile.mkdtemp()
        subprocess.run(['git', 'init', '-q', root], check=True)
        os.makedirs(os.path.join(root, 'scripts'))
        for name, text in files.items():
            path = os.path.join(root, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(text)
        self.root = root
        result = subprocess.run(['bash', GATE, 'test'],
                                cwd=root, capture_output=True, text=True)
        out = ANSI.sub('', result.stdout)
        match = re.search(r'▶ project documents[^\n]*\n(.*?)\n▶ ', out, re.S)
        return match.group(1) if match else out

    def test_a_nested_package_json_still_gets_the_document_check(self):
        step = self.build({'frontend/package.json': '{"name":"f"}'})
        self.assertIn('SETUP.md is missing', step, f"the step was skipped:\n{step}")

    def test_a_repository_with_no_stack_is_left_alone(self):
        step = self.build({'README.md': '# nothing here'})
        self.assertIn('nothing to check', step)


class SolutionTarget(unittest.TestCase):
    """`dotnet build` needs a TARGET, not just a detected stack.

    Detection finding a nested project made HAS_DOTNET=1 while the build command
    still ran with no argument, so in a repository whose solution lives under
    api/ or backend/ the step failed with "MSBUILD : error MSB1003: Specify a
    project or solution file" — measured in one repository, and four
    of five .NET repositories here keep their solution below the root.
    """

    def tearDown(self):
        shutil.rmtree(getattr(self, 'root', ''), ignore_errors=True)

    def build(self, files):
        root = tempfile.mkdtemp()
        subprocess.run(['git', 'init', '-q', root], check=True)
        os.makedirs(os.path.join(root, 'scripts'))
        for name in files:
            path = os.path.join(root, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write('<Project />')
        self.root = root
        result = subprocess.run(['bash', GATE, 'test', '--list'],
                                cwd=root, capture_output=True, text=True)
        return ANSI.sub('', result.stdout)

    def test_a_nested_solution_becomes_the_build_target(self):
        out = self.build(['api/App.sln'])
        self.assertIn('api/App.sln', out, f"the nested solution was not passed to dotnet:\n{out}")

    def test_a_root_solution_still_wins(self):
        out = self.build(['App.slnx', 'api/Other.sln'])
        self.assertIn('App.slnx', out)
        self.assertNotIn('api/Other.sln', out)

    def test_with_no_solution_the_project_itself_is_the_target(self):
        out = self.build(['src/Api/Api.csproj'])
        self.assertIn('src/Api/Api.csproj', out,
                      f"with no solution the csproj must be the target:\n{out}")


class BuildOutputIsNotAProject(unittest.TestCase):
    """obj/ and node_modules/ carry .csproj and package.json files of their own.
    If detection counts those, a repository with no product code at all looks
    like it has both stacks, and every step then runs against build output."""

    def tearDown(self):
        shutil.rmtree(getattr(self, 'root', ''), ignore_errors=True)

    def test_obj_and_node_modules_are_not_mistaken_for_a_project(self):
        root = tempfile.mkdtemp()
        subprocess.run(['git', 'init', '-q', root], check=True)
        os.makedirs(os.path.join(root, 'scripts'))
        for name in ('obj/Debug/Ghost.csproj', 'web/node_modules/pkg/package.json'):
            path = os.path.join(root, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write('{}')
        self.root = root
        result = subprocess.run(['bash', GATE, 'test', '--list'],
                                cwd=root, capture_output=True, text=True)
        out = ANSI.sub('', result.stdout)
        stacks = [l for l in out.splitlines() if l.startswith('stacks:')][0]
        self.assertIn('dotnet=0', stacks, stacks)
        self.assertIn('node=0', stacks, stacks)


class TheBuildKeepsWarningsAsErrors(unittest.TestCase):
    """The -warnaserror flag is what turns a NuGet advisory or a deprecation into
    a failing gate rather than a line of scroll nobody reads."""

    def tearDown(self):
        shutil.rmtree(getattr(self, 'root', ''), ignore_errors=True)

    def test_the_planned_build_asks_for_warnings_as_errors(self):
        root = tempfile.mkdtemp()
        subprocess.run(['git', 'init', '-q', root], check=True)
        os.makedirs(os.path.join(root, 'scripts'))
        with open(os.path.join(root, 'App.sln'), 'w', encoding='utf-8') as handle:
            handle.write('')
        self.root = root
        result = subprocess.run(['bash', GATE, 'test', '--list'],
                                cwd=root, capture_output=True, text=True)
        out = ANSI.sub('', result.stdout)
        build = [l for l in out.splitlines() if 'dotnet build' in l]
        self.assertTrue(build, out)
        self.assertIn('-warnaserror', build[0])


if __name__ == '__main__':
    unittest.main()
