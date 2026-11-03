# %% Imports and deterministic helpers
"""Local video evidence preparation; the calling AI writes the meeting minutes.

Use ``stream`` and ``frame-inline``: evidence stays in memory and stdout.
No model downloads, software installation, cloud calls, or source mutation occur.
"""
from __future__ import annotations

import argparse
import base64
import importlib.metadata
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

SAMPLE_RATE = 16000
DLL_HANDLES = []


def timestamp(seconds: float, srt: bool = False) -> str:
    millis = max(0, round(float(seconds) * 1000))
    hours, millis = divmod(millis, 3600000)
    minutes, millis = divmod(millis, 60000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{',' if srt else '.'}{millis:03d}"


def parse_time(value: str) -> float:
    parts = value.split(":")
    if len(parts) not in (1, 2, 3):
        raise argparse.ArgumentTypeError(f"Invalid time: {value}")
    try:
        result = sum(float(p) * (60 ** i) for i, p in enumerate(reversed(parts)))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid time: {value}") from exc
    if not math.isfinite(result) or result < 0:
        raise argparse.ArgumentTypeError("Time must be finite and nonnegative")
    return result


def source_identity(path: Path) -> dict:
    path = path.resolve(strict=True)
    stat = path.stat()
    return {"path": str(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def load_dll_directories(paths: list[str]) -> None:
    resolved = []
    for value in paths:
        path = Path(value).resolve(strict=True)
        if not path.is_dir():
            raise ValueError(f"DLL location is not a directory: {path}")
        resolved.append(str(path))
    if os.name == "nt" and resolved:
        # CTranslate2 also uses LoadLibraryA directly. add_dll_directory alone
        # does not affect that loader; change only this process's environment.
        os.environ["PATH"] = os.pathsep.join(resolved + [os.environ.get("PATH", "")])
        for path in resolved:
            DLL_HANDLES.append(os.add_dll_directory(path))


# %% Metadata and environment inspection
def video_metadata(path: Path) -> dict:
    import av

    with av.open(str(path)) as container:
        origin = float(container.start_time or 0) / av.time_base
        streams = []
        for stream in container.streams:
            item = {"type": stream.type, "index": stream.index,
                    "codec": stream.codec_context.name,
                    "start_seconds": float(stream.start_time * stream.time_base)
                    if stream.start_time is not None else None,
                    "duration_seconds": float(stream.duration * stream.time_base)
                    if stream.duration is not None else None}
            if stream.type == "video":
                item.update(width=stream.codec_context.width, height=stream.codec_context.height,
                            frames=stream.frames,
                            fps=float(stream.average_rate) if stream.average_rate else None)
            elif stream.type == "audio":
                item.update(sample_rate=stream.codec_context.sample_rate,
                            channels=stream.codec_context.channels)
            streams.append(item)
        return {"source": source_identity(path), "duration_seconds":
                float(container.duration / av.time_base) if container.duration else None,
                "timeline_origin_seconds": origin, "streams": streams}


def check_environment(args: argparse.Namespace) -> None:
    load_dll_directories(args.dll_dir)
    packages = {name: package_version(name) for name in
                ["faster-whisper", "ctranslate2", "av", "numpy", "Pillow", "onnxruntime"]}
    result = {"python": sys.executable, "version": sys.version, "packages": packages,
              "dll_directories": args.dll_dir}
    try:
        proc = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total,memory.free",
                               "--format=csv,noheader"], capture_output=True, text=True, timeout=15)
        result["nvidia_smi"] = proc.stdout.strip() or proc.stderr.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        result["nvidia_smi"] = str(exc)
    if packages["ctranslate2"]:
        import ctranslate2
        result["cuda_device_count"] = ctranslate2.get_cuda_device_count()
        result["cuda_compute_types"] = sorted(ctranslate2.get_supported_compute_types("cuda")) \
            if result["cuda_device_count"] else []
    print(json.dumps(result, ensure_ascii=False, indent=2))


# %% Memory-only audio decoding; no WAV, transcript or other intermediate file.
def decode_audio_memory(video: Path, limit: float | None):
    import av
    import numpy as np

    cursor = gaps = trimmed = 0
    blocks = []
    maximum = round(limit * SAMPLE_RATE) if limit is not None else None
    with av.open(str(video)) as container:
        if not container.streams.audio:
            raise ValueError("Video has no audio stream")
        source_duration = float(container.duration / av.time_base) \
            if container.duration is not None else None
        origin = float(container.start_time or 0) / av.time_base
        resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)

        def emit(frame):
            nonlocal cursor, gaps, trimmed
            samples = frame.to_ndarray().reshape(-1)
            position = round((float(frame.pts * frame.time_base) - origin) * SAMPLE_RATE) \
                if frame.pts is not None else cursor
            if position < 0:
                samples = samples[min(-position, len(samples)):]
                position = 0
            if abs(position - cursor) <= 16:
                position = cursor
            if position > cursor:
                count = position - cursor
                if maximum is not None:
                    count = min(count, max(0, maximum - cursor))
                while count:
                    length = min(count, SAMPLE_RATE * 10)
                    blocks.append(np.zeros(length, dtype=np.float32))
                    cursor += length
                    gaps += length
                    count -= length
            elif position < cursor:
                overlap = min(cursor - position, len(samples))
                samples = samples[overlap:]
                trimmed += overlap
            if maximum is not None:
                samples = samples[:max(0, maximum - cursor)]
            if len(samples):
                normalized = samples.astype(np.float32)
                normalized *= 1.0 / 32768.0
                blocks.append(normalized)
                cursor += len(normalized)

        for frame in container.decode(container.streams.audio[0]):
            for converted in resampler.resample(frame):
                emit(converted)
            if maximum is not None and cursor >= maximum:
                break
        else:
            for converted in resampler.resample(None):
                emit(converted)
    if not cursor:
        raise ValueError("Decoded audio is empty")
    audio = np.concatenate(blocks)
    return audio, {"sample_rate": SAMPLE_RATE, "samples": cursor,
                   "duration_seconds": cursor / SAMPLE_RATE,
                   "source_duration_seconds": source_duration,
                   "timeline_origin_seconds": origin, "gap_samples_filled": gaps,
                   "overlap_samples_trimmed": trimmed, "channels": 1}


# %% Preferred memory-only transcription, emitting evidence directly to the caller.
def stream_transcript(args: argparse.Namespace) -> None:
    sys.dont_write_bytecode = True
    os.environ["CUDA_CACHE_DISABLE"] = "1"
    os.environ["MKL_THREADING_LAYER"] = "SEQUENTIAL"
    started = time.perf_counter()
    video = args.video.resolve(strict=True)
    if not video.is_file():
        raise ValueError("--video must be an existing file")
    if args.limit_seconds is not None and args.limit_seconds <= 0:
        raise ValueError("--limit-seconds must be positive")
    if args.batch_size <= 0 or args.beam_size <= 0:
        raise ValueError("Batch size and beam size must be positive")
    load_dll_directories(args.dll_dir)
    model_info = model_identity(args.model)
    source = source_identity(video)
    from faster_whisper import WhisperModel, BatchedInferencePipeline
    stage = time.perf_counter()
    audio, audio_info = decode_audio_memory(video, args.limit_seconds)
    timings = {"audio_decode_seconds": time.perf_counter() - stage}
    print(json.dumps({"event": "audio_ready", "audio": audio_info}, ensure_ascii=False), flush=True)
    stage = time.perf_counter()
    model = WhisperModel(str(args.model.resolve()), device="cuda", compute_type=args.compute_type,
                         local_files_only=True)
    pipeline = BatchedInferencePipeline(model=model)
    timings["model_load_seconds"] = time.perf_counter() - stage
    stage = time.perf_counter()
    generator, info = pipeline.transcribe(audio, language=args.language, task="transcribe",
                                          batch_size=args.batch_size, beam_size=args.beam_size,
                                          vad_filter=True, word_timestamps=False,
                                          without_timestamps=False, condition_on_previous_text=False)
    segments = []
    pending = []
    for segment in generator:
        record = {"start": segment.start, "end": segment.end,
                  "time": timestamp(segment.start), "text": segment.text}
        segments.append(record)
        pending.append(record)
        if len(pending) == 100:
            print(json.dumps({"event": "segments", "processed_through_seconds": segment.end,
                              "segments": pending}, ensure_ascii=False), flush=True)
            pending = []
    timings["asr_seconds"] = time.perf_counter() - stage
    validate_segments(segments, audio_info["duration_seconds"])
    if pending:
        print(json.dumps({"event": "segments", "processed_through_seconds": segments[-1]["end"],
                          "segments": pending}, ensure_ascii=False), flush=True)
    timings["stream_wall_seconds"] = time.perf_counter() - started
    timings["seconds_per_video_hour"] = timings["stream_wall_seconds"] * 3600 / audio_info["duration_seconds"]
    timings["end_to_end_status"] = "AI reading, frame review and final minutes remain to be measured"
    print(json.dumps({"event": "complete", "source": source,
                      "scope": "full" if args.limit_seconds is None else "limited",
                      "limit_seconds": args.limit_seconds,
                      "source_duration_seconds": audio_info["source_duration_seconds"],
                      "audio_duration_seconds": audio_info["duration_seconds"],
                      "count": len(segments), "language": info.language, "timings": timings,
                      "settings": {"compute_type": args.compute_type, "batch_size": args.batch_size,
                                   "beam_size": args.beam_size, "model": model_info["path"]}},
                     ensure_ascii=False), flush=True)


# %% Validate transcript evidence without writing files
def validate_segments(segments: list[dict], duration: float) -> None:
    if not segments:
        raise ValueError("Transcript contains no speech segments; a successful meeting summary cannot be generated")
    previous_start = -1.0
    for segment in segments:
        start, end = float(segment["start"]), float(segment["end"])
        if not all(math.isfinite(x) for x in (start, end)) \
                or start < 0 or end < start or start < previous_start or end > duration + 1:
            raise ValueError(f"Invalid transcript timestamp: {start}, {end}")
        previous_start = start


def model_identity(path: Path) -> dict:
    path = path.resolve(strict=True)
    required = ("model.bin", "config.json", "tokenizer.json", "preprocessor_config.json")
    missing = [name for name in required if not (path / name).is_file()]
    if not path.is_dir() or missing:
        raise ValueError("--model requires complete local Whisper files: " + ", ".join(missing))
    return {"path": str(path), "files": [source_identity(file) for file in sorted(path.iterdir())
                                        if file.is_file()]}


# %% Sparse evidence frames from requested video timestamps
def inline_frames(args: argparse.Namespace) -> None:
    sys.dont_write_bytecode = True
    import av

    video = args.video.resolve(strict=True)
    if args.width < 1:
        raise ValueError("--width must be positive")
    with av.open(str(video)) as container:
        if not container.streams.video:
            raise ValueError("Input has no video stream")
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        origin = float(container.start_time or 0) / av.time_base
        duration = float(container.duration / av.time_base) if container.duration else None
        for requested in sorted(set(args.times)):
            if duration is not None and requested >= duration:
                raise ValueError(f"Requested time {requested} is outside video duration {duration}")
            target = requested + origin
            container.seek(int(target / float(stream.time_base)), stream=stream,
                           backward=True, any_frame=False)
            selected = None
            actual = None
            for frame in container.decode(stream):
                if frame.pts is None:
                    continue
                actual = float(frame.pts * frame.time_base) - origin
                selected = frame
                if actual + 1e-6 >= requested:
                    break
            if selected is None:
                raise ValueError(f"Could not decode a frame near {requested}")
            image = selected.to_image()
            if image.width > args.width:
                image = image.resize((args.width, round(image.height * args.width / image.width)))
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=85, subsampling=0)
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
            print(json.dumps({"event": "frame", "requested_seconds": requested,
                              "actual_seconds": actual, "width": image.width, "height": image.height,
                              "data_url": "data:image/jpeg;base64," + encoded}), flush=True)


# %% Command line entry point
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    stream = commands.add_parser("stream", help="Preferred: memory-only audio and ASR; emit JSON evidence to stdout")
    stream.add_argument("--video", type=Path, required=True)
    stream.add_argument("--model", type=Path, required=True)
    stream.add_argument("--dll-dir", action="append", default=[])
    stream.add_argument("--compute-type", choices=["int8_float16", "float16", "int8"], default="int8_float16")
    stream.add_argument("--batch-size", type=int, default=2)
    stream.add_argument("--beam-size", type=int, default=1)
    stream.add_argument("--language", default="zh")
    stream.add_argument("--limit-seconds", type=float)
    stream.set_defaults(handler=stream_transcript)
    inline = commands.add_parser("frame-inline", help="Preferred: seek sparse frames and emit in-memory JPEG data URLs")
    inline.add_argument("--video", type=Path, required=True)
    inline.add_argument("--times", type=parse_time, nargs="+", required=True)
    inline.add_argument("--width", type=int, default=1920)
    inline.set_defaults(handler=inline_frames)
    check = commands.add_parser("check", help="Inspect packages, CUDA and explicitly supplied DLL directories")
    check.add_argument("--dll-dir", action="append", default=[])
    check.set_defaults(handler=check_environment)
    metadata = commands.add_parser("metadata", help="Inspect media streams without decoding video")
    metadata.add_argument("--video", type=Path, required=True)
    metadata.set_defaults(handler=lambda args: print(json.dumps(video_metadata(args.video), ensure_ascii=False, indent=2)))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        args.handler(args)
    except Exception as exc:
        print(f"ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
