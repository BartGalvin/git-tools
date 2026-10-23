"""Test portable settings and SSH behavior using only temporary repositories."""

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_SHELL = shutil.which(os.environ.get("TEST_BASH", "bash"))
BARE = "gbinit"
ORIGIN = "gitorigin.sh"


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory(prefix="script-config-tests-")
        self.addCleanup(temporary_directory.cleanup)
        self.work = Path(temporary_directory.name).resolve()
        self.bin = self.work / "bin"
        self.bin.mkdir()
        self.log = self.work / "calls.jsonl"
        self.env = {
            key: value for key, value in os.environ.items()
            if not key.startswith("GIT_")
        }
        self.env.update(
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_TERMINAL_PROMPT="0",
            TEST_CALL_LOG=str(self.log),
        )
        self.env["PATH"] = str(self.bin) + os.pathsep + self.env.get("PATH", "")
        self.git("init", "--initial-branch=main")
        self.write_tool("ssh", "\n".join([
            "import json, os, subprocess, sys",
            "with open(os.environ['TEST_CALL_LOG'], 'a') as log:",
            "    log.write(json.dumps(sys.argv[1:]) + '\\n')",
            "if os.environ.get('MOCK_SSH_EXECUTE') == '1':",
            "    sys.exit(subprocess.run(['/bin/sh', '-c', sys.argv[-1]]).returncode)",
            "sys.exit(int(os.environ.get('MOCK_SSH_EXIT', '0')))",
        ]))


    def write_tool(self, name, body):
        tool = self.bin / name
        tool.write_text(
            "#!/bin/sh\nexec " + shlex.quote(sys.executable)
            + " - \"$@\" <<'FIXTURE_PYTHON'\n" + body + "\nFIXTURE_PYTHON\n"
        )
        tool.chmod(0o755)


    def git(self, *arguments, directory=None, check=True):
        return subprocess.run(
            ["git", "-C", str(directory or self.work), *map(str, arguments)],
            env=self.env, capture_output=True, text=True, check=check, timeout=30,
        )


    def run_script(self, script, *arguments, expected=0):
        result = subprocess.run(
            [SCRIPT_SHELL, str(ROOT / script), *map(str, arguments)],
            cwd=self.work, env=self.env, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(
            result.returncode, expected,
            f"{script}\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )
        return result


    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]


    def config(self, **settings):
        path = self.work / "private settings.conf"
        for key, value in settings.items():
            self.git("config", "--file", path, key, value)
        return path


    def remote_options(self, directory=None):
        return (
            "--host", "git.example.com", "--user", "gituser",
            "--directory", str(directory or self.work / "remote"),
        )


    def assert_no_origin(self):
        self.assertNotEqual(self.git("remote", "get-url", "origin", check=False).returncode, 0)


    def test_bare_config_sets_base_and_branch_and_explicit_options_win(self):
        base = self.work / "bare repositories"
        base.mkdir()
        config = self.config(**{
            "gbinit.directory": str(base), "init.defaultBranch": "development",
        })
        self.run_script(BARE, "--config", config, "first")
        self.assertEqual(
            self.git("symbolic-ref", "HEAD", directory=base / "first.git").stdout.strip(),
            "refs/heads/development",
        )
        explicit = self.work / "explicit.git"
        self.run_script(BARE, "--config", config, "--branch", "release", explicit)
        self.assertTrue(explicit.is_dir())
        self.assertFalse((base / "explicit.git").exists())
        self.assertEqual(
            self.git("symbolic-ref", "HEAD", directory=explicit).stdout.strip(),
            "refs/heads/release",
        )


    def test_bare_rejects_invalid_config_and_branch_before_creating_a_directory(self):
        config = self.work / "broken.conf"
        config.write_text("[not closed\n")
        for options in (
            ("--config", config), ("--config", self.work / "absent.conf"),
            ("--branch", "bad..branch"), ("--branch", "@{-1}"),
            ("--unknown",),
        ):
            with self.subTest(options=options):
                self.run_script(BARE, *options, "new", expected=2)
        self.assertFalse((self.work / "new.git").exists())


    def test_git_config_does_not_execute_shell_values_or_follow_includes(self):
        included = self.work / "included.conf"
        included.write_text("[init]\n    defaultBranch = injected\n")
        config = self.config(**{
            "include.path": str(included),
            "gbinit.directory": "$(touch should-not-exist)",
        })
        self.run_script(BARE, "--config", config, "new", expected=1)
        self.assertFalse((self.work / "should-not-exist").exists())
        self.git("config", "--file", config, "--unset", "gbinit.directory")
        self.run_script(BARE, "--config", config, "new")
        self.assertEqual(
            self.git("symbolic-ref", "HEAD", directory=self.work / "new.git").stdout.strip(),
            "refs/heads/main",
        )


    def test_remote_requires_explicit_settings_and_validates_before_ssh(self):
        self.run_script(ORIGIN, "new", expected=2)
        for options, name in (
            (("--host", "-option", "--user", "gituser", "--directory", "/srv/git"), "new"),
            (("--host", "git.example.com", "--user", "bad user", "--directory", "/srv/git"), "new"),
            (("--host", "git.example.com", "--user", "gituser", "--directory", "relative"), "new"),
            (self.remote_options(), "../escape"),
            (self.remote_options(), "bad\nname"),
            (self.remote_options() + ("--branch", "bad..branch"), "new"),
            (self.remote_options() + ("--config", self.work / "absent.conf"), "new"),
        ):
            with self.subTest(options=options, name=name):
                self.run_script(ORIGIN, *options, name, expected=2)
        self.assertEqual(self.calls(), [])
        self.assert_no_origin()


    def test_remote_config_dry_run_and_cli_precedence_do_not_write_or_connect(self):
        config = self.config(**{
            "remote.host": "configured.example.com", "remote.user": "configured",
            "remote.directory": "/srv/configured", "init.defaultBranch": "development",
        })
        result = self.run_script(ORIGIN, "--config", config, "--dry-run", "new")
        self.assertIn("configured@configured.example.com:/srv/configured/new.git", result.stdout)
        result = self.run_script(
            ORIGIN, "--config", config, *self.remote_options(), "--branch", "release",
            "--dry-run", "new",
        )
        self.assertIn(f"gituser@git.example.com:{self.work}/remote/new.git", result.stdout)
        self.assertNotIn("configured.example.com", result.stdout)
        self.assertIn("release", result.stdout)
        self.assertEqual(self.calls(), [])
        self.assert_no_origin()


    def test_remote_refuses_an_existing_origin_before_ssh(self):
        self.git("remote", "add", "origin", "https://example.invalid/existing.git")
        self.run_script(ORIGIN, *self.remote_options(), "new", expected=1)
        self.assertEqual(self.calls(), [])
        self.assertEqual(
            self.git("remote", "get-url", "origin").stdout.strip(),
            "https://example.invalid/existing.git",
        )
        self.git("config", "--unset", "remote.origin.url")
        self.git("config", "remote.origin.pushurl", "https://example.invalid/push.git")
        self.run_script(ORIGIN, *self.remote_options(), "new", expected=1)
        self.assertEqual(self.calls(), [])


    def test_remote_shell_quoting_preserves_names_and_creates_a_real_bare_repository(self):
        parent = self.work / "remote 'parent'"
        parent.mkdir()
        name = "repo 'quoted'; $(touch injected)"
        self.env["MOCK_SSH_EXECUTE"] = "1"
        self.run_script(ORIGIN, *self.remote_options(parent), "--branch", "release", name)
        target = parent / (name + ".git")
        self.assertEqual(self.git("rev-parse", "--is-bare-repository", directory=target).stdout.strip(), "true")
        self.assertEqual(self.git("symbolic-ref", "HEAD", directory=target).stdout.strip(), "refs/heads/release")
        self.assertEqual(self.git("remote", "get-url", "origin").stdout.strip(), f"gituser@git.example.com:{target}")
        self.assertFalse((self.work / "injected").exists())
        self.assertEqual(self.calls()[0][:2], ["--", "gituser@git.example.com"])


    def test_remote_config_creates_repository_without_double_suffix(self):
        parent = self.work / "remote"
        parent.mkdir()
        config = self.config(**{
            "remote.host": "git.example.com", "remote.user": "gituser",
            "remote.directory": str(parent), "init.defaultBranch": "development",
        })
        self.env["MOCK_SSH_EXECUTE"] = "1"
        self.run_script(ORIGIN, "--config", config, "already.git")
        self.assertTrue((parent / "already.git").is_dir())
        self.assertFalse((parent / "already.git.git").exists())
        self.assertEqual(
            self.git("symbolic-ref", "HEAD", directory=parent / "already.git").stdout.strip(),
            "refs/heads/development",
        )


    def test_remote_refuses_existing_destinations_including_broken_links(self):
        parent = self.work / "remote"
        parent.mkdir()
        (parent / "file.git").write_text("keep this file")
        (parent / "directory.git").mkdir()
        (parent / "link.git").symlink_to(parent / "absent")
        self.env["MOCK_SSH_EXECUTE"] = "1"
        for name in ("file", "directory", "link"):
            with self.subTest(name=name):
                self.run_script(ORIGIN, *self.remote_options(parent), name, expected=1)
                self.assert_no_origin()
        self.assertEqual((parent / "file.git").read_text(), "keep this file")
        self.assertEqual(list((parent / "directory.git").iterdir()), [])
        self.assertTrue((parent / "link.git").is_symlink())


    def test_remote_failure_and_missing_parent_do_not_add_origin(self):
        self.env["MOCK_SSH_EXIT"] = "9"
        self.run_script(ORIGIN, *self.remote_options(), "new", expected=1)
        self.assert_no_origin()
        self.env["MOCK_SSH_EXECUTE"] = "1"
        self.run_script(ORIGIN, *self.remote_options(), "new", expected=1)
        self.assert_no_origin()
        self.assertFalse((self.work / "remote").exists())


    def test_remote_requires_a_local_git_repository_before_ssh(self):
        shutil.rmtree(self.work / ".git")
        self.run_script(ORIGIN, *self.remote_options(), "new", expected=1)
        self.assertEqual(self.calls(), [])



if __name__ == "__main__":
    unittest.main()
