# %% Explicit first-time download; normal inference remains local-only.
"""Download one immutable public ASR model revision after installation approval.

Downloads and resumable caches stay under the existing project tmp. The model
directory contains only reusable model files and provenance, never meeting data.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time


# %% Optional explicit weight URL: bounded, verified, resumable range download.
def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def cache_json(path: Path, value: dict) -> None:
    partial = path.with_name(path.name + '.part')
    partial.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    partial.replace(path)


def download_weight(url: str, expected_sha256: str, cache: Path, direct: bool) -> Path:
    """Use at most eight workers, 32 MiB ranges, three retries and 15 minutes."""
    import requests

    identity = hashlib.sha256((url + '\n' + expected_sha256.lower()).encode('utf-8')).hexdigest()
    directory = cache / ('weights-' + identity)
    directory.mkdir(parents=True, exist_ok=True)
    final = directory / 'model.bin'
    if final.is_file() and file_sha256(final) == expected_sha256.lower():
        print(json.dumps({'weight_status': 'verified_cache', 'path': str(final)}), flush=True)
        return final
    chunk_bytes = 32 * 1024 * 1024
    deadline = time.monotonic() + 900
    stop = threading.Event()

    def check_deadline():
        if stop.is_set():
            raise RuntimeError('Weight download cancelled after another range failed')
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Weight download exceeded its 900 second total deadline')
        return remaining

    def response_range(response, start, end, total=None):
        if response.status_code != 206:
            raise ValueError(f'Expected HTTP 206, received {response.status_code}')
        match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
        if not match:
            raise ValueError('Missing or invalid Content-Range')
        got_start, got_end, got_total = map(int, match.groups())
        if (got_start, got_end) != (start, end) or got_total <= end \
                or (total is not None and got_total != total):
            raise ValueError('Content-Range does not match the requested byte interval')
        length = end - start + 1
        if response.headers.get('Content-Length') is not None \
                and int(response.headers['Content-Length']) != length:
            raise ValueError('Content-Length does not match the requested byte interval')
        return got_total

    # A one-byte range discovers total size without trusting a HEAD response.
    last_error = None
    total = None
    for attempt in range(4):
        remaining = check_deadline()
        try:
            with requests.Session() as session:
                session.trust_env = not direct
                with session.get(url, headers={'Range': 'bytes=0-0', 'Accept-Encoding': 'identity'},
                                 timeout=(min(15, remaining), min(30, remaining)), stream=True) as response:
                    candidate_total = response_range(response, 0, 0)
                    body = response.raw.read(2, decode_content=False)
                    if len(body) != 1:
                        raise ValueError('One-byte range probe has an invalid body length')
                    total = candidate_total
            break
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                stop.wait(min(2 ** attempt, check_deadline()))
    if total is None:
        raise RuntimeError(f'Weight size probe failed after four attempts: {last_error}')
    cache_json(directory / 'source.json', {'url': url, 'expected_sha256': expected_sha256,
                                          'bytes': total, 'cache_signature': identity})

    def fetch_part(number):
        start = number * chunk_bytes
        end = min(total - 1, start + chunk_bytes - 1)
        length = end - start + 1
        path = directory / f'range_{number:04d}_{start}_{end}.bin'
        metadata = path.with_suffix('.json')
        check_deadline()
        if path.is_file() and metadata.is_file() and path.stat().st_size == length:
            try:
                record = json.loads(metadata.read_text(encoding='utf-8'))
                if record.get('cache_signature') == identity and record.get('total') == total \
                        and record.get('start') == start and record.get('end') == end \
                        and file_sha256(path) == record.get('sha256'):
                    return number, path
            except (ValueError, OSError):
                pass
        last_error = None
        for attempt in range(4):
            remaining = check_deadline()
            attempt_deadline = min(deadline, time.monotonic() + 180)
            partial = path.with_name(path.name + '.part')
            received = 0
            digest = hashlib.sha256()
            try:
                with requests.Session() as session:
                    session.trust_env = not direct
                    with session.get(url, headers={'Range': f'bytes={start}-{end}',
                                                   'Accept-Encoding': 'identity'},
                                     timeout=(min(15, remaining), min(30, remaining)), stream=True) as response:
                        response_range(response, start, end, total)
                        with partial.open('wb') as writer:
                            for block in response.iter_content(chunk_size=1024 * 1024):
                                check_deadline()
                                if time.monotonic() > attempt_deadline:
                                    raise TimeoutError('Range attempt exceeded its 180 second deadline')
                                if not block:
                                    continue
                                received += len(block)
                                if received > length:
                                    raise ValueError('Range response exceeds the requested length')
                                writer.write(block)
                                digest.update(block)
                if received != length or partial.stat().st_size != length:
                    raise ValueError(f'Truncated range body: {received}/{length}')
                partial.replace(path)
                cache_json(metadata, {'cache_signature': identity, 'start': start, 'end': end,
                                       'total': total, 'sha256': digest.hexdigest()})
                return number, path
            except Exception as exc:
                last_error = exc
                print(json.dumps({'weight_range': number, 'attempt': attempt + 1,
                                  'error': str(exc)}, ensure_ascii=False), flush=True)
                if attempt < 3:
                    stop.wait(min(2 ** attempt, check_deadline()))
        stop.set()
        raise RuntimeError(f'Weight range {number} failed after four attempts: {last_error}')

    count = (total + chunk_bytes - 1) // chunk_bytes
    print(json.dumps({'weight_status': 'downloading', 'ranges': count, 'bytes': total,
                      'workers': min(8, count)}), flush=True)
    paths = {}
    with ThreadPoolExecutor(max_workers=min(8, count)) as pool:
        futures = [pool.submit(fetch_part, number) for number in range(count)]
        try:
            for future in as_completed(futures, timeout=check_deadline()):
                number, path = future.result()
                paths[number] = path
                check_deadline()
        except Exception:
            stop.set()
            for future in futures:
                future.cancel()
            raise
    merged = directory / 'model.bin.assembling'
    digest = hashlib.sha256()
    with merged.open('wb') as writer:
        for number in range(count):
            with paths[number].open('rb') as reader:
                for block in iter(lambda: reader.read(4 * 1024 * 1024), b''):
                    check_deadline()
                    writer.write(block)
                    digest.update(block)
    if merged.stat().st_size != total or digest.hexdigest() != expected_sha256.lower():
        raise ValueError('Complete weight file does not match the independently verified SHA256')
    merged.replace(final)
    print(json.dumps({'weight_status': 'verified', 'path': str(final),
                      'bytes': total, 'sha256': digest.hexdigest()}), flush=True)
    return final


# %% First-time download command; no alternate URL is enabled by default.
def main() -> int:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default='dropbox-dash/faster-whisper-large-v3-turbo')
    parser.add_argument('--revision', required=True, help='Immutable 40-character model commit SHA')
    parser.add_argument('--model-dir', type=Path, default=root / 'models' / 'large-v3-turbo')
    parser.add_argument('--endpoint', default='https://huggingface.co', help='Explicitly recorded download endpoint')
    parser.add_argument('--direct', action='store_true', help='Ignore proxy environment for this download process')
    parser.add_argument('--expected-model-sha256', help='Independently verified SHA256 of model.bin')
    parser.add_argument('--weight-url', help='Explicit HTTPS alternate weight URL; requires --expected-model-sha256')
    args = parser.parse_args()
    if len(args.revision) != 40 or any(c not in '0123456789abcdef' for c in args.revision.lower()):
        parser.error('--revision must be an immutable 40-character hexadecimal SHA')
    if args.expected_model_sha256 and not re.fullmatch(r'[0-9a-fA-F]{64}', args.expected_model_sha256):
        parser.error('--expected-model-sha256 must be a 64-character hexadecimal digest')
    if args.weight_url and (not args.expected_model_sha256 or not args.weight_url.startswith('https://')):
        parser.error('--weight-url requires HTTPS and --expected-model-sha256')
    temporary = root / 'tmp'
    if not temporary.is_dir():
        parser.error('Project tmp must already exist; do not create it automatically')
    destination = args.model_dir.resolve()
    if root not in destination.parents:
        parser.error('--model-dir must remain inside the project')
    if destination.exists() and any(destination.iterdir()):
        parser.error('Refusing an existing nonempty model directory; use the existing model or a new path')
    cache = temporary / 'model-download'
    os.environ['HF_HOME'] = str(cache)
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    from huggingface_hub import snapshot_download
    if args.direct:
        import requests
        from huggingface_hub import configure_http_backend
        def direct_session():
            session = requests.Session()
            session.trust_env = False
            return session
        configure_http_backend(backend_factory=direct_session)

    started = time.perf_counter()
    patterns = ['config.json', 'tokenizer.json', 'preprocessor_config.json', 'vocabulary.*']
    if not args.weight_url:
        patterns.append('model.bin')
    snapshot = Path(snapshot_download(
        repo_id=args.repo, revision=args.revision, endpoint=args.endpoint, cache_dir=str(cache / 'hub'),
        allow_patterns=patterns, max_workers=4,
    ))
    for required in ('config.json', 'tokenizer.json', 'preprocessor_config.json'):
        if not (snapshot / required).is_file():
            raise ValueError(f'Model download is incomplete: missing {required}')
    weight = download_weight(args.weight_url, args.expected_model_sha256, cache, args.direct) \
        if args.weight_url else snapshot / 'model.bin'
    if not weight.is_file():
        raise ValueError('Model download is incomplete: missing model.bin')
    if args.expected_model_sha256:
        if file_sha256(weight) != args.expected_model_sha256.lower():
            raise ValueError('Downloaded model.bin does not match the independently verified SHA256')
    destination.mkdir(parents=True, exist_ok=True)
    files = []
    sources = [snapshot / name for name in ('config.json', 'tokenizer.json', 'preprocessor_config.json')]
    sources.extend(source for source in sorted(snapshot.glob('vocabulary.*')) if source.is_file())
    sources.append(weight)
    for source in sources:
        target = destination / source.name
        # Never overwrite existing weights, including after a partial earlier copy.
        digest = hashlib.sha256()
        with source.open('rb') as reader, target.open('xb') as writer:
            while True:
                block = reader.read(8 * 1024 * 1024)
                if not block:
                    break
                writer.write(block)
                digest.update(block)
        files.append({'name': source.name, 'bytes': target.stat().st_size, 'sha256': digest.hexdigest()})
    record = {'repo': args.repo, 'revision': args.revision, 'endpoint': args.endpoint,
              'weight_url': args.weight_url,
              'expected_model_sha256': args.expected_model_sha256, 'files': files,
              'download_and_copy_seconds': time.perf_counter() - started}
    with (destination / 'provenance.json').open('x', encoding='utf-8') as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


# %% CLI entry point
if __name__ == '__main__':
    raise SystemExit(main())
