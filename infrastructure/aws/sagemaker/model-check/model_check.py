"""Check the SageMaker model files against manifest.json before vLLM uses them (#777).

SageMaker downloads the model data again from S3 every time the endpoint scales from 0, and it does
not check sha256 itself (#368·#493). This module runs inside the serving container:

  python3 model_check.py model            # startup: /opt/ml/model against the manifest
  python3 model_check.py adapter <dir>     # manual: a LoRA directory against the manifest

`model` checks, in order:
  1. MODEL_MANIFEST_SHA256 (set on the SageMaker model) is 64 hex characters
  2. /opt/ml/model/manifest.json has exactly that sha256
  3. every file under /opt/ml/model is listed (no extra file), present (no missing file), and has the
     listed size and sha256

`AdapterCheckMiddleware` is a vLLM `--middleware`. SageMaker attaches a LoRA (adapter inference
component) through `POST /adapters?name=..&src=<dir>`; the middleware checks `<dir>` against the
manifest entries under MODEL_ADAPTER_DIR before vLLM loads it and answers 400 otherwise. It also
refuses vLLM's own `/v1/load_lora_adapter`, which could otherwise be reached through `/invocations`
with a `route=` custom attribute.

Only the Python standard library is used. File contents are never printed, only relative names.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs

MODEL_DIR = '/opt/ml/model'
MANIFEST = 'manifest.json'
CHUNK = 8 * 1024 * 1024
HEX64 = re.compile(r'^[0-9a-f]{64}$')
BLOCKED_PATHS = ('/v1/load_lora_adapter',)


class CheckError(Exception):
    """The manifest itself cannot be trusted (missing, wrong sha256, malformed)."""


def log(message):
    print(f'[model-check] {message}', file=sys.stderr, flush=True)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            block = f.read(CHUNK)
            if not block:
                return digest.hexdigest()
            digest.update(block)


def load_manifest(model_dir, expected_sha256):
    """Return {relative path: {'bytes', 'sha256'}} after checking manifest.json against expected_sha256.

    Keys in the manifest are S3 keys (`explanation/<version>/base-awq/...`). They are made relative to
    the version root, which is the parent of the listed prefixes and is what SageMaker copies into
    /opt/ml/model.
    """
    expected = (expected_sha256 or '').strip().lower()
    if not HEX64.match(expected):
        raise CheckError('MODEL_MANIFEST_SHA256 is missing or not 64 hex characters')
    path = Path(model_dir) / MANIFEST
    if not path.is_file() or path.is_symlink():
        raise CheckError(f'{MANIFEST} is missing')
    body = path.read_bytes()
    actual = hashlib.sha256(body).hexdigest()
    if actual != expected:
        raise CheckError(f'{MANIFEST} sha256 {actual[:12]} != MODEL_MANIFEST_SHA256 {expected[:12]}')
    try:
        data = json.loads(body)
        prefixes = data['prefixes']
        roots = {p.rstrip('/').rsplit('/', 1)[0] + '/' for p in prefixes}
        if len(roots) != 1 or not all(p.endswith('/') for p in prefixes):
            raise CheckError(f'{MANIFEST} prefixes do not share one version root')
        root = roots.pop()
        entries = {}
        for item in data['files']:
            key = item['key']
            relative = key[len(root):]
            if not key.startswith(root) or not any(key.startswith(p) for p in prefixes) or not safe_relative(relative):
                raise CheckError(f'{MANIFEST} has a key outside its prefixes')
            if relative in entries or relative == MANIFEST:
                raise CheckError(f'{MANIFEST} lists {relative} twice')
            sha = str(item['sha256']).lower()
            if not HEX64.match(sha) or not isinstance(item['bytes'], int) or item['bytes'] < 0:
                raise CheckError(f'{MANIFEST} entry {relative} has no valid sha256/bytes')
            entries[relative] = {'bytes': item['bytes'], 'sha256': sha}
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise CheckError(f'{MANIFEST} is malformed ({type(error).__name__})') from None
    if not entries:
        raise CheckError(f'{MANIFEST} lists no files')
    return entries


def safe_relative(relative):
    parts = relative.split('/')
    return bool(relative) and not relative.startswith('/') and all(p not in ('', '.', '..') for p in parts)


def list_files(directory):
    """Relative names of every non-directory entry (symlinks and special files included, so they fail)."""
    found = {}
    for current, dirs, files in os.walk(directory, followlinks=False):
        for name in files + [d for d in dirs if os.path.islink(os.path.join(current, d))]:
            full = os.path.join(current, name)
            found[os.path.relpath(full, directory).replace(os.sep, '/')] = full
    return found


def check_tree(directory, expected, ignore=(), workers=None):
    """Compare every file under directory with expected {relative: {'bytes', 'sha256'}}.

    Returns (problems, stats). Sizes are compared first so a wrong file fails before hashing.
    """
    if not os.path.isdir(directory):
        return [f'MISSING_DIR {directory}'], {'files': 0, 'bytes': 0, 'seconds': 0.0}
    found = list_files(directory)
    for name in ignore:
        found.pop(name, None)
    problems = [f'MISSING {name}' for name in sorted(set(expected) - set(found))]
    problems += [f'UNEXPECTED {name}' for name in sorted(set(found) - set(expected))]
    to_hash = []
    for name in sorted(set(found) & set(expected)):
        path = found[name]
        if os.path.islink(path) or not os.path.isfile(path):
            problems.append(f'NOT_A_FILE {name}')
        elif os.path.getsize(path) != expected[name]['bytes']:
            problems.append(f'SIZE {name} {os.path.getsize(path)} != {expected[name]["bytes"]}')
        else:
            to_hash.append(name)
    start = time.monotonic()
    total = sum(expected[n]['bytes'] for n in to_hash)
    if not problems:
        workers = workers or min(4, os.cpu_count() or 1)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for name, actual in zip(to_hash, pool.map(lambda n: sha256_file(found[n]), to_hash)):
                if actual != expected[name]['sha256']:
                    problems.append(f'SHA256 {name} {actual[:12]} != {expected[name]["sha256"][:12]}')
    return problems, {'files': len(to_hash), 'bytes': total, 'seconds': round(time.monotonic() - start, 1)}


def check_model(model_dir, expected_sha256, workers=None):
    try:
        entries = load_manifest(model_dir, expected_sha256)
    except CheckError as error:
        return [f'MANIFEST {error}'], {'files': 0, 'bytes': 0, 'seconds': 0.0}
    return check_tree(model_dir, entries, ignore=(MANIFEST,), workers=workers)


def adapter_entries(model_dir, expected_sha256, adapter_dir):
    entries = load_manifest(model_dir, expected_sha256)
    prefix = adapter_dir.strip('/') + '/'
    picked = {k[len(prefix):]: v for k, v in entries.items() if k.startswith(prefix)}
    if not picked:
        raise CheckError(f'{MANIFEST} lists no files under {prefix}')
    return picked


def check_adapter(src, model_dir, expected_sha256, adapter_dir, workers=None):
    try:
        entries = adapter_entries(model_dir, expected_sha256, adapter_dir)
    except CheckError as error:
        return [f'MANIFEST {error}'], {'files': 0, 'bytes': 0, 'seconds': 0.0}
    return check_tree(src, entries, workers=workers)


def settings(env=os.environ):
    return {'model_dir': env.get('MODEL_CHECK_DIR', MODEL_DIR), 'expected_sha256': env.get('MODEL_MANIFEST_SHA256', ''),
            'adapter_dir': env.get('MODEL_ADAPTER_DIR', 'adapter')}


def report(kind, problems, stats):
    gib = stats['bytes'] / 2 ** 30
    if problems:
        for line in problems[:50]:
            log(f'FAIL {line}')
        log(f'{kind} check FAILED: {len(problems)} problem(s); not starting')
        return 1
    log(f'{kind} check OK: {stats["files"]} files {gib:.2f} GiB sha256 in {stats["seconds"]}s')
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    conf = settings()
    if argv[:1] == ['model'] and len(argv) == 1:
        log(f'checking {conf["model_dir"]} against {MANIFEST} (MODEL_MANIFEST_SHA256 {conf["expected_sha256"][:12]})')
        return report('model', *check_model(conf['model_dir'], conf['expected_sha256']))
    if argv[:1] == ['adapter'] and len(argv) == 2:
        return report('adapter', *check_adapter(argv[1], conf['model_dir'], conf['expected_sha256'], conf['adapter_dir']))
    print(__doc__, file=sys.stderr)
    return 2


def effective_path(scope):
    """The path vLLM will route to: /invocations may be rerouted by a `route=` custom attribute."""
    path = scope.get('path', '')
    if path == '/invocations':
        for key, value in scope.get('headers', []):
            if key.lower() == b'x-amzn-sagemaker-custom-attributes':
                match = re.search(r'route=(/[^\s,]+)', value.decode('latin-1'))
                if match:
                    return match.group(1)
    return path


class AdapterCheckMiddleware:
    """ASGI middleware for vLLM `--middleware model_check.AdapterCheckMiddleware`."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get('type') == 'http':
            path = effective_path(scope)
            if path in BLOCKED_PATHS:
                log(f'REFUSED {scope.get("method")} {path}: LoRA loading is allowed only through /adapters')
                return await self.reply(send, 403, 'LoRA loading is allowed only through /adapters with a checked source')
            if path == '/adapters' and scope.get('method') == 'POST':
                import asyncio
                query = parse_qs(scope.get('query_string', b'').decode('latin-1'))
                src = (query.get('src') or [''])[0]
                name = (query.get('name') or [''])[0]
                if not os.path.isabs(src):
                    log(f'REFUSED adapter {name}: no absolute src')
                    return await self.reply(send, 400, 'adapter src is missing')
                conf = settings()
                problems, stats = await asyncio.to_thread(check_adapter, src, conf['model_dir'], conf['expected_sha256'],
                                                          conf['adapter_dir'])
                if report(f'adapter {name}', problems, stats):
                    return await self.reply(send, 400, 'adapter files do not match manifest.json')
        await self.app(scope, receive, send)

    @staticmethod
    async def reply(send, status, message):
        body = json.dumps({'error': message}).encode()
        await send({'type': 'http.response.start', 'status': status,
                    'headers': [(b'content-type', b'application/json'), (b'content-length', str(len(body)).encode())]})
        await send({'type': 'http.response.body', 'body': body})


if __name__ == '__main__':
    sys.exit(main())
