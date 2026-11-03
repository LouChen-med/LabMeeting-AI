# %% Meaningful invariants without GPU or model dependencies
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "labmeeting.py"
SPEC = importlib.util.spec_from_file_location("labmeeting", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PipelineInvariants(unittest.TestCase):
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
