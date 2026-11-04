# %% Meaningful invariants without GPU or model dependencies
import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".agents" / "skills" / "lab-meeting-summary" / "scripts" / "labmeeting.py"
SPEC = importlib.util.spec_from_file_location("labmeeting", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PipelineInvariants(unittest.TestCase):
    def test_mixed_language_default_detects_chunks_and_preserves_original_text(self):
        captured_options = []
        spoken_text = ["这个 assay 检测 T cells。", "The results show an increase in CD8 T cells."]

        class FakePipeline:
            def __init__(self, model):
                pass

            def transcribe(self, audio, **options):
                captured_options.append(options)
                return iter(SimpleNamespace(start=index, end=index + 1, text=text)
                            for index, text in enumerate(spoken_text)), SimpleNamespace(language="zh")

        fake_whisper = SimpleNamespace(WhisperModel=lambda *args, **kwargs: object(),
                                       BatchedInferencePipeline=FakePipeline)
        for explicit_language, expected_language, expected_multilingual in [
            (None, None, True), ("zh", "zh", False), ("en", "en", False)
        ]:
            arguments = ["stream", "--video", str(SOURCE), "--model", str(SOURCE.parent)]
            if explicit_language:
                arguments += ["--language", explicit_language]
            args = MODULE.build_parser().parse_args(arguments)
            output = io.StringIO()
            with patch.dict(sys.modules, {"faster_whisper": fake_whisper}), \
                    patch.object(MODULE, "load_dll_directories"), \
                    patch.object(MODULE, "model_identity", return_value={"path": "local-model"}), \
                    patch.object(MODULE, "decode_audio_memory", return_value=(object(),
                                 {"duration_seconds": 10, "source_duration_seconds": 10})), \
                    contextlib.redirect_stdout(output):
                MODULE.stream_transcript(args)
            events = [json.loads(line) for line in output.getvalue().splitlines()]
            texts = [segment["text"] for event in events if event["event"] == "segments"
                     for segment in event["segments"]]
            self.assertEqual(texts, spoken_text)
            self.assertEqual(captured_options[-1]["language"], expected_language)
            self.assertEqual(captured_options[-1]["multilingual"], expected_multilingual)
            self.assertEqual(captured_options[-1]["task"], "transcribe")
            self.assertEqual(events[-1]["settings"]["multilingual"], expected_multilingual)

    def test_runtime_blocks_real_file_mutations_before_creation(self):
        # Exercise actual Python file APIs in an isolated child. No fixture,
        # temporary script or temporary directory is created by the test.
        script = r'''
import io, os, pathlib, runpy, shutil, sys, tempfile
source = pathlib.Path(sys.argv[1])
temporary = pathlib.Path(sys.argv[2])
namespace = runpy.run_path(str(source))
namespace["configure_memory_runtime"]()
target = temporary / "blocked-write-must-not-exist"
assert not target.exists()
operations = [
    lambda: target.open("xb"),
    lambda: os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL),
    lambda: target.mkdir(),
    lambda: target.unlink(),
    lambda: target.rename(str(target) + ".renamed"),
    lambda: os.utime(target, None),
    lambda: shutil.copyfile(source, target),
    lambda: tempfile.NamedTemporaryFile(dir=temporary),
]
if hasattr(os, "O_TEMPORARY"):
    operations.append(lambda: os.open(target, os.O_RDONLY | os.O_TEMPORARY))
for operation in operations:
    try:
        operation()
    except RuntimeError as exc:
        assert "blocked a filesystem mutation before execution" in str(exc), str(exc)
    else:
        raise AssertionError("A filesystem mutation escaped the memory-only guard")
assert not target.exists()
assert len(namespace["BLOCKED_FILE_MUTATIONS"]) == len(operations)
assert source.read_bytes()
assert io.BytesIO(b"memory-only JPEG/audio").getvalue()
with open(os.devnull, "w") as null_device:
    null_device.write("device sink, no disk file")
assert sys.dont_write_bytecode
assert os.environ["CUDA_CACHE_DISABLE"] == "1"
assert os.environ["HF_HUB_OFFLINE"] == "1"
print("All filesystem mutations blocked before execution; memory and read-only access work")
'''
        result = subprocess.run([sys.executable, "-I", "-B", "-u", "-X", "utf8", "-c", script,
                                 str(SOURCE), str(ROOT / "tmp")], capture_output=True, text=True,
                                encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("All filesystem mutations blocked before execution", result.stdout)

    def test_timestamp_rounding_carries_into_next_minute(self):
        self.assertEqual(MODULE.timestamp(59.9996, True), "00:01:00,000")
        self.assertEqual(MODULE.parse_time("02:30:06.25"), 9006.25)

    def test_frame_times_parse_seconds_minutes_and_hours(self):
        args = MODULE.build_parser().parse_args([
            "frame-inline", "--video", str(SOURCE), "--times", "90", "01:30", "01:01:30.5"])
        self.assertEqual(args.times, [90.0, 90.0, 3690.5])
        for invalid in ["nan", "inf", "-1", "invalid", "1:2:3:4"]:
            with self.assertRaises(MODULE.argparse.ArgumentTypeError):
                MODULE.parse_time(invalid)

    def test_segment_validation_rejects_nonfinite_and_wrong_order(self):
        for segments in [[], [{"start": 2, "end": 1}], [{"start": float("nan"), "end": 3}],
                         [{"start": 5, "end": 6}, {"start": 4, "end": 7}],
                         [{"start": 0, "end": 102}]]:
            with self.assertRaises(ValueError):
                MODULE.validate_segments(segments, 100)
        MODULE.validate_segments([{"start": 0, "end": 2}, {"start": 1.9, "end": 4}], 100)

    def test_model_requires_local_tokenizer_and_feature_configuration(self):
        root = Path("read-only-model-fixture")
        available = {"model.bin", "config.json"}
        with patch.object(Path, "resolve", lambda self, **kwargs: self), \
                patch.object(Path, "is_dir", return_value=True), \
                patch.object(Path, "is_file", lambda self: self.name in available), \
                patch.object(Path, "iterdir", return_value=[root / name for name in
                                  ["model.bin", "config.json", "tokenizer.json", "preprocessor_config.json"]]), \
                patch.object(MODULE, "source_identity", side_effect=lambda path: {"path": str(path)}):
            with self.assertRaisesRegex(ValueError, "tokenizer.json.*preprocessor_config.json"):
                MODULE.model_identity(root)
            available.add("tokenizer.json")
            with self.assertRaisesRegex(ValueError, "preprocessor_config.json"):
                MODULE.model_identity(root)
            available.add("preprocessor_config.json")
            self.assertEqual(len(MODULE.model_identity(root)["files"]), 4)

    @unittest.skipUnless(os.name == "nt", "Windows DLL loader behavior")
    def test_dll_directory_is_added_to_process_search_path(self):
        directory = SOURCE.parent
        old_handles = len(MODULE.DLL_HANDLES)
        with patch.dict(os.environ, {"PATH": "existing-process-path"}):
            with patch.object(os, "add_dll_directory", return_value="test-handle") as add:
                MODULE.load_dll_directories([str(directory)])
                self.assertEqual(os.environ["PATH"], str(directory.resolve()) + os.pathsep + "existing-process-path")
                add.assert_called_once_with(str(directory.resolve()))
                self.assertEqual(MODULE.DLL_HANDLES[-1], "test-handle")
        del MODULE.DLL_HANDLES[old_handles:]


if __name__ == "__main__":
    unittest.main()
