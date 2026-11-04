# %% Portable Skill packaging checks without model downloads
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".agents" / "skills" / "lab-meeting-summary"
SCRIPTS = SKILL / "scripts"
REVISION = "0" * 40


def load_source(name, source):
    spec = importlib.util.spec_from_file_location(name, source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# %% Mock only the asset-directory checks; no fixtures or temporary files
@contextlib.contextmanager
def asset_directories(root, *, has_tmp=True, occupied_destination=None):
    directories = {root.resolve()}
    if has_tmp:
        directories.add((root / "tmp").resolve())
    if occupied_destination is not None:
        directories.add(occupied_destination.resolve())

    def exists(path):
        return path.resolve() in directories

    def children(path):
        if occupied_destination is not None and path.resolve() == occupied_destination.resolve():
            return iter([occupied_destination / "model.bin"])
        return iter([])

    with patch.object(Path, "is_dir", exists), patch.object(Path, "exists", exists), \
            patch.object(Path, "iterdir", children):
        yield


class SkillBundleTests(unittest.TestCase):
    def test_bundle_contains_runtime_downloader_and_dependency_specification(self):
        for filename in ("labmeeting.py", "download_model.py", "run.cmd"):
            with self.subTest(filename=filename):
                self.assertTrue((SCRIPTS / filename).is_file())
        specification = (SKILL / "environment.yml").read_text(encoding="utf-8")
        self.assertIn("name: labmeeting-ai", specification)
        self.assertIn("dependencies:", specification)
        self.assertIn("faster-whisper", specification)

    def test_bundled_cli_help_works_from_a_different_directory(self):
        result = subprocess.run([sys.executable, "-I", "-B", "-u", "-X", "utf8",
                                 str(SCRIPTS / "labmeeting.py"), "--help"], cwd=ROOT / "tmp",
                                capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("frame-inline", result.stdout)
        self.assertIn("stream", result.stdout)

    def test_bundled_downloader_help_needs_no_model_or_network(self):
        result = subprocess.run([sys.executable, "-I", "-B", "-u", "-X", "utf8",
                                 str(SCRIPTS / "download_model.py"), "--help"], cwd=ROOT / "tmp",
                                capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("--project-dir", result.stdout)
        self.assertIn("--model-dir", result.stdout)

    @unittest.skipUnless(os.name == "nt", "Windows persistent launcher")
    def test_launcher_uses_bundled_cli(self):
        environment = os.environ.copy()
        environment["LABMEETING_AI_PYTHON"] = sys.executable
        command_interpreter = environment.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
        command = f'"{command_interpreter}" /d /s /c ""{SCRIPTS / "run.cmd"}" --help"'
        result = subprocess.run(command, cwd=ROOT / "tmp", env=environment,
                                capture_output=True, text=True, encoding="utf-8", timeout=30)
        expected = subprocess.run([sys.executable, "-I", "-B", "-u", "-X", "utf8",
                                   str(SCRIPTS / "labmeeting.py"), "--help"], cwd=ROOT / "tmp",
                                  capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(expected.returncode, 0, expected.stdout + expected.stderr)
        self.assertEqual(result.stdout, expected.stdout)

    def test_downloader_defaults_to_skill_asset_root(self):
        module = load_source("download_defaults", SCRIPTS / "download_model.py")
        parser = module.build_parser()
        args = parser.parse_args(["--revision", REVISION])
        with asset_directories(SKILL):
            actual = module.resolve_install_paths(args, parser)
        self.assertEqual(actual, (SKILL.resolve(), (SKILL / "tmp").resolve(),
                                  (SKILL / "models" / "large-v3-turbo").resolve()))

    def test_downloader_explicit_project_and_relative_model_target(self):
        module = load_source("download_explicit", SCRIPTS / "download_model.py")
        parser = module.build_parser()
        args = parser.parse_args(["--revision", REVISION, "--project-dir", str(ROOT),
                                  "--model-dir", "models/custom-model"])
        with asset_directories(ROOT):
            actual = module.resolve_install_paths(args, parser)
        self.assertEqual(actual, (ROOT.resolve(), (ROOT / "tmp").resolve(),
                                  (ROOT / "models" / "custom-model").resolve()))

    def test_downloader_rejects_missing_tmp_without_creating_it(self):
        module = load_source("download_missing_tmp", SCRIPTS / "download_model.py")
        parser = module.build_parser()
        args = parser.parse_args(["--revision", REVISION, "--project-dir", str(ROOT)])
        errors = io.StringIO()
        with asset_directories(ROOT, has_tmp=False), contextlib.redirect_stderr(errors):
            with self.assertRaises(SystemExit) as raised:
                module.resolve_install_paths(args, parser)
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("tmp", errors.getvalue())

    def test_downloader_rejects_model_target_outside_asset_root(self):
        module = load_source("download_escape", SCRIPTS / "download_model.py")
        parser = module.build_parser()
        for target in ("../outside-model", str(ROOT.parent / "outside-model"), "."):
            with self.subTest(target=target):
                args = parser.parse_args(["--revision", REVISION, "--project-dir", str(ROOT),
                                          "--model-dir", target])
                with asset_directories(ROOT), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        module.resolve_install_paths(args, parser)
                self.assertEqual(raised.exception.code, 2)

    def test_downloader_refuses_existing_nonempty_model_directory(self):
        module = load_source("download_occupied", SCRIPTS / "download_model.py")
        parser = module.build_parser()
        destination = ROOT / "models" / "large-v3-turbo"
        args = parser.parse_args(["--revision", REVISION, "--project-dir", str(ROOT)])
        with asset_directories(ROOT, occupied_destination=destination), \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                module.resolve_install_paths(args, parser)
        self.assertEqual(raised.exception.code, 2)


# %% Test command entry point; the caller supplies the verified Conda interpreter
if __name__ == "__main__":
    unittest.main()
