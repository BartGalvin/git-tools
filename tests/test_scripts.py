"""Exercise local Git helpers in disposable repositories."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_SHELL = shutil.which(os.environ.get("TEST_BASH", "bash"))
BARE = "gbinit"
ORIGIN = "gitorigin.sh"
SCRIPTS = (BARE, ORIGIN)


class ScriptTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory(prefix="git-script-tests-")
        self.addCleanup(temporary_directory.cleanup)
        self.work = Path(temporary_directory.name).resolve()
        self.bin = self.work / "bin"
        self.bin.mkdir()
        self.env = {
            key: value for key, value in os.environ.items()
            if not key.startswith("GIT_")
        }
        self.env.update(
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_TERMINAL_PROMPT="0",
        )
        self.env["PATH"] = str(self.bin) + os.pathsep + self.env.get("PATH", "")


    def run_script(self, script, *arguments, expected=0):
        result = subprocess.run(
            [SCRIPT_SHELL, str(ROOT / script), *map(str, arguments)],
            cwd=self.work,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if expected is not None:
            self.assertEqual(
                result.returncode, expected,
                f"{script}\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )
        return result


    def git(self, directory, *arguments):
        return subprocess.run(
            ["git", "-C", str(directory), *arguments],
            env=self.env,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout.strip()


    def test_help_has_no_side_effects(self):
        before = set(self.work.iterdir())
        for script in SCRIPTS:
            with self.subTest(script=script):
                self.assertIn("Usage:", self.run_script(script, "--help").stdout)
        self.assertEqual(set(self.work.iterdir()), before)


    def test_missing_and_extra_arguments_are_rejected(self):
        for script in (BARE, ORIGIN):
            with self.subTest(script=script, arguments="missing"):
                self.run_script(script, expected=2)
        for script in SCRIPTS:
            with self.subTest(script=script, arguments="extra"):
                self.run_script(script, self.work / "destination", "extra", expected=2)

    def test_missing_required_tools_fail_before_writing(self):
        self.env["PATH"] = str(self.bin)
        for script, name in ((BARE, "new-repo"), (ORIGIN, "new-remote")):
            with self.subTest(script=script):
                result = self.run_script(script, name, expected=1)
                self.assertIn("git", result.stderr)
        self.assertFalse((self.work / "new-repo.git").exists())


    def test_bare_repository_has_expected_suffix_and_branch(self):
        for name in ("example repo", "already.git"):
            with self.subTest(name=name):
                self.run_script(BARE, name)
                target = self.work / (name if name.endswith(".git") else name + ".git")
                self.assertEqual(self.git(target, "rev-parse", "--is-bare-repository"), "true")
                self.assertEqual(self.git(target, "symbolic-ref", "HEAD"), "refs/heads/main")
                self.run_script(BARE, name, expected=1)
        self.assertFalse((self.work / "already.git.git").exists())


    def test_bare_repository_refuses_existing_files_and_links(self):
        target = self.work / "existing.git"
        target.write_bytes(b"keep this file")
        self.run_script(BARE, "existing", expected=1)
        self.assertEqual(target.read_bytes(), b"keep this file")
        link = self.work / "linked.git"
        link.symlink_to(self.work / "absent")
        self.run_script(BARE, "linked", expected=1)
        self.assertTrue(link.is_symlink())


    def test_bare_repository_rejects_parent_directory_aliases(self):
        for name in ("", ".", "..", "..//", "/", "folder/../"):
            with self.subTest(name=name):
                self.run_script(BARE, name, expected=2)
        self.assertFalse((self.work / ".git").exists())


if __name__ == "__main__":
    unittest.main()
