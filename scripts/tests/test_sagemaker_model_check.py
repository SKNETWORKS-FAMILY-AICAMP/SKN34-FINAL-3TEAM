"""#777 SageMaker model check: startup manifest check and LoRA middleware, on fake files only."""
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('model_check', ROOT / 'infrastructure/aws/sagemaker/model-check/model_check.py')
model_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(model_check)

VERSION_ROOT = 'explanation/fake-v1/'
FILES = {
    'base-awq/config.json': b'{"fake": true}',
    'base-awq/model-00001-of-00002.safetensors': b'A' * 4096,
    'base-awq/model-00002-of-00002.safetensors': b'B' * 3000,
    'adapter/adapter_config.json': b'{"r": 16}',
    'adapter/adapter_model.safetensors': b'L' * 512,
}


def manifest_body(files=FILES, prefixes=('base-awq/', 'adapter/')):
    entries = [{'key': VERSION_ROOT + name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
               for name, data in sorted(files.items())]
    data = {'modelVersion': 'fake-v1', 'prefixes': [VERSION_ROOT + p for p in prefixes], 'files': entries}
    return json.dumps(data, indent=1).encode() + b'\n'


class ModelDir:
    """A fake /opt/ml/model: the version root SageMaker copies (manifest + base + adapter)."""

    def __init__(self, files=FILES, body=None):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.body = body if body is not None else manifest_body()
        (self.path / 'manifest.json').write_bytes(self.body)
        for name, data in files.items():
            target = self.path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        self.sha = hashlib.sha256(self.body).hexdigest()

    def check(self, sha=None):
        return model_check.check_model(str(self.path), self.sha if sha is None else sha, workers=2)

    def close(self):
        self.tmp.cleanup()


class StartupCheckTest(unittest.TestCase):
    def setUp(self):
        self.model = ModelDir()
        self.addCleanup(self.model.close)

    def test_matching_files_pass_and_report_hash_time(self):
        problems, stats = self.model.check()
        self.assertEqual(problems, [])
        self.assertEqual(stats['files'], len(FILES))
        self.assertEqual(stats['bytes'], sum(len(d) for d in FILES.values()))

    def test_manifest_sha_env_must_be_present_and_match(self):
        for bad in ('', 'abc', 'g' * 64, '0' * 64):
            problems, _ = self.model.check(sha=bad)
            self.assertEqual(len(problems), 1, bad)
            self.assertTrue(problems[0].startswith('MANIFEST '), problems)

    def test_uppercase_manifest_sha_is_accepted(self):
        self.assertEqual(self.model.check(sha=self.model.sha.upper())[0], [])

    def test_changed_manifest_fails_even_if_files_match_it(self):
        changed = dict(FILES, **{'base-awq/config.json': b'{"fake": false}'})
        model = ModelDir(files=changed, body=manifest_body(changed))
        self.addCleanup(model.close)
        problems, _ = model.check(sha=self.model.sha)  # env still names the approved manifest
        self.assertIn('MODEL_MANIFEST_SHA256', problems[0])

    def test_one_changed_byte_fails_with_sha_mismatch(self):
        target = self.model.path / 'base-awq/model-00001-of-00002.safetensors'
        target.write_bytes(b'A' * 4095 + b'Z')
        problems, _ = self.model.check()
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith('SHA256 base-awq/model-00001-of-00002.safetensors'), problems)

    def test_size_change_fails_before_hashing(self):
        (self.model.path / 'adapter/adapter_model.safetensors').write_bytes(b'L' * 513)
        problems, stats = self.model.check()
        self.assertEqual(problems, ['SIZE adapter/adapter_model.safetensors 513 != 512'])
        self.assertEqual(stats['seconds'], 0.0)

    def test_missing_and_extra_files_fail(self):
        (self.model.path / 'base-awq/config.json').unlink()
        (self.model.path / 'base-gguf').mkdir()
        (self.model.path / 'base-gguf/model.gguf').write_bytes(b'G')
        problems, _ = self.model.check()
        self.assertEqual(problems, ['MISSING base-awq/config.json', 'UNEXPECTED base-gguf/model.gguf'])

    @unittest.skipIf(os.name == 'nt', 'symlinks need privileges on Windows')
    def test_symlink_in_place_of_a_file_fails(self):
        target = self.model.path / 'base-awq/config.json'
        target.unlink()
        os.symlink(self.model.path / 'adapter/adapter_config.json', target)
        problems, _ = self.model.check()
        self.assertEqual(problems, ['NOT_A_FILE base-awq/config.json'])

    def test_malformed_manifests_fail_closed(self):
        cases = {
            'not json': b'{',
            'no files': json.dumps({'prefixes': [VERSION_ROOT + 'base-awq/'], 'files': []}).encode(),
            'outside prefix': json.dumps({'prefixes': [VERSION_ROOT + 'base-awq/'], 'files': [
                {'key': 'explanation/other/x', 'bytes': 1, 'sha256': '0' * 64}]}).encode(),
            'parent path': json.dumps({'prefixes': [VERSION_ROOT + 'base-awq/'], 'files': [
                {'key': VERSION_ROOT + 'base-awq/../x', 'bytes': 1, 'sha256': '0' * 64}]}).encode(),
            'two roots': json.dumps({'prefixes': [VERSION_ROOT + 'base-awq/', 'explanation/v2/adapter/'], 'files': [
                {'key': VERSION_ROOT + 'base-awq/x', 'bytes': 1, 'sha256': '0' * 64}]}).encode(),
            'bad sha': json.dumps({'prefixes': [VERSION_ROOT + 'base-awq/'], 'files': [
                {'key': VERSION_ROOT + 'base-awq/x', 'bytes': 1, 'sha256': 'xyz'}]}).encode(),
        }
        for label, body in cases.items():
            model = ModelDir(files={}, body=body)
            self.addCleanup(model.close)
            problems, _ = model.check()
            self.assertEqual(len(problems), 1, label)
            self.assertTrue(problems[0].startswith('MANIFEST '), (label, problems))

    def test_cli_exit_codes(self):
        env = {'MODEL_CHECK_DIR': str(self.model.path), 'MODEL_MANIFEST_SHA256': self.model.sha}
        with mock.patch.dict(os.environ, env), mock.patch('sys.stderr'):
            self.assertEqual(model_check.main(['model']), 0)
            (self.model.path / 'base-awq/config.json').write_bytes(b'{"fake": nope}')
            self.assertEqual(model_check.main(['model']), 1)
            self.assertEqual(model_check.main(['unknown']), 2)


class AdapterMiddlewareTest(unittest.TestCase):
    def setUp(self):
        self.model = ModelDir()
        self.addCleanup(self.model.close)
        self.src = tempfile.TemporaryDirectory()
        self.addCleanup(self.src.cleanup)
        for name in ('adapter_config.json', 'adapter_model.safetensors'):
            (Path(self.src.name) / name).write_bytes(FILES['adapter/' + name])
        self.env = mock.patch.dict(os.environ, {'MODEL_CHECK_DIR': str(self.model.path),
                                                'MODEL_MANIFEST_SHA256': self.model.sha})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.stderr = mock.patch('sys.stderr')
        self.stderr.start()
        self.addCleanup(self.stderr.stop)

    def call(self, path, method='POST', query=b'', headers=()):
        reached, sent = [], []

        async def app(scope, receive, send):
            reached.append(scope['path'])

        async def send(message):
            sent.append(message)

        scope = {'type': 'http', 'method': method, 'path': path, 'query_string': query, 'headers': list(headers)}
        asyncio.run(model_check.AdapterCheckMiddleware(app)(scope, None, send))
        status = sent[0]['status'] if sent else None
        return reached, status

    def adapters(self, src):
        return self.call('/adapters', query=f'name=explain&src={src}'.encode())

    def test_matching_adapter_reaches_vllm(self):
        self.assertEqual(self.adapters(self.src.name), (['/adapters'], None))

    def test_changed_adapter_is_refused(self):
        (Path(self.src.name) / 'adapter_model.safetensors').write_bytes(b'M' * 512)
        self.assertEqual(self.adapters(self.src.name), ([], 400))

    def test_extra_or_missing_adapter_file_is_refused(self):
        (Path(self.src.name) / 'extra.bin').write_bytes(b'x')
        self.assertEqual(self.adapters(self.src.name), ([], 400))
        (Path(self.src.name) / 'extra.bin').unlink()
        (Path(self.src.name) / 'adapter_config.json').unlink()
        self.assertEqual(self.adapters(self.src.name), ([], 400))

    def test_missing_src_or_manifest_sha_is_refused(self):
        self.assertEqual(self.call('/adapters', query=b'name=explain'), ([], 400))
        with mock.patch.dict(os.environ, {'MODEL_MANIFEST_SHA256': '0' * 64}):
            self.assertEqual(self.adapters(self.src.name), ([], 400))

    def test_runtime_lora_route_is_blocked_directly_and_through_invocations(self):
        self.assertEqual(self.call('/v1/load_lora_adapter'), ([], 403))
        header = (b'X-Amzn-SageMaker-Custom-Attributes', b'route=/v1/load_lora_adapter')
        self.assertEqual(self.call('/invocations', headers=[header]), ([], 403))

    def test_other_requests_pass_untouched(self):
        self.assertEqual(self.call('/invocations'), (['/invocations'], None))
        self.assertEqual(self.call('/ping', method='GET'), (['/ping'], None))
        self.assertEqual(self.call('/adapters/explain', method='DELETE'), (['/adapters/explain'], None))


class ImageFilesTest(unittest.TestCase):
    def test_entrypoint_checks_before_dlc_entrypoint(self):
        text = (ROOT / 'infrastructure/aws/sagemaker/model-check/entrypoint.sh').read_text(encoding='utf-8')
        self.assertLess(text.index('model_check.py model'), text.index('exec /usr/local/bin/sagemaker_entrypoint.sh'))
        self.assertIn('export SM_VLLM_MIDDLEWARE=model_check.AdapterCheckMiddleware', text)

    def test_dockerfile_pins_base_by_digest(self):
        text = (ROOT / 'infrastructure/aws/sagemaker/model-check/Dockerfile').read_text(encoding='utf-8')
        base = next(line for line in text.splitlines() if line.startswith('ARG BASE_IMAGE='))
        self.assertRegex(base, r'vllm:server-sagemaker-cuda-v2\.8\.2@sha256:[0-9a-f]{64}$')
        self.assertIn('ENTRYPOINT ["/usr/local/bin/model_check_entrypoint.sh"]', text)


_spec = importlib.util.spec_from_file_location('sagemaker_explanation', ROOT / 'infrastructure/aws/sagemaker_explanation.py')
sagemaker_explanation = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sagemaker_explanation)


class FakeS3Aws:
    """sts + the s3api calls verify/lock make, over an in-memory bucket of {key: bytes}."""

    def __init__(self, objects):
        self.objects, self.policy, self.calls = dict(objects), None, []

    def __call__(self, service, operation, *args, check=True, payload=None):
        import base64
        self.calls.append((service, operation, args))
        opt = {args[i][2:]: args[i + 1] for i in range(len(args) - 1) if str(args[i]).startswith('--')}
        if (service, operation) == ('sts', 'get-caller-identity'):
            return {'Account': '000000000000'}
        if operation == 'get-object':
            Path(args[-1]).write_bytes(self.objects[opt['key']])
            return {}
        if operation == 'head-object':
            data = self.objects[opt['key']]
            return {'ChecksumType': 'FULL_OBJECT', 'ContentLength': len(data),
                    'ChecksumSHA256': base64.b64encode(hashlib.sha256(data).digest()).decode()}
        if operation == 'list-objects-v2':
            return {'Contents': [{'Key': k} for k in sorted(self.objects) if k.startswith(opt['prefix'])]}
        if operation == 'get-bucket-policy':
            return {'Policy': json.dumps(self.policy)} if self.policy else None
        if operation == 'put-bucket-policy':
            self.policy = json.loads(opt['policy'])
            return {}
        if operation == 'delete-bucket-policy':
            self.policy = None
            return {}
        raise AssertionError((service, operation))


class SageMakerConfigTest(unittest.TestCase):
    def setUp(self):
        self.version = 'gemma4-26b-a4b-lora-20261118'
        self.root = f'explanation/{self.version}/'
        files = {'base-awq/config.json': b'{}', 'base-awq/model.safetensors': b'W' * 64,
                 'adapter/adapter_config.json': b'{"r":16}', 'adapter/adapter_model.safetensors': b'L' * 32}
        body = json.dumps({'modelVersion': self.version, 'prefixes': [self.root + 'base-awq/', self.root + 'adapter/'],
                           'files': [{'key': self.root + n, 'bytes': len(d), 'sha256': hashlib.sha256(d).hexdigest()}
                                     for n, d in sorted(files.items())]}).encode()
        self.manifest_sha = hashlib.sha256(body).hexdigest()
        self.aws = FakeS3Aws({self.root + 'manifest.json': body, **{self.root + n: d for n, d in files.items()}})
        self.spec = sagemaker_explanation.load_spec(self.aws)
        self.args = mock.Mock(local_manifest=None, confirm_account='000000000000', prefix=None, remove=False,
                              dry_run=False)
        self.stdout = mock.patch('sys.stdout')
        self.stdout.start()
        self.addCleanup(self.stdout.stop)

    def test_spec_reads_the_whole_version_root_with_the_check_image(self):
        spec = self.spec
        self.assertEqual(spec['modelDataPrefix'], self.root)
        self.assertEqual(spec['lockPrefix'], spec['modelDataPrefix'])
        self.assertTrue(spec['manifestKey'].startswith(spec['modelDataPrefix']))
        for prefix in sagemaker_explanation.used_prefixes(spec):
            self.assertTrue(prefix.startswith(spec['modelDataPrefix']))
        base = spec['baseModelPrefix'][len(spec['modelDataPrefix']):].rstrip('/')
        self.assertEqual(spec['environment']['SM_VLLM_MODEL'], f'/opt/ml/model/{base}')
        self.assertEqual(spec['adapterPrefix'][len(spec['modelDataPrefix']):].rstrip('/'),
                         spec['environment']['MODEL_ADAPTER_DIR'])
        self.assertRegex(spec['image'], r'^000000000000\.dkr\.ecr\.ap-northeast-2\.amazonaws\.com/'
                                        r'sagomungchi/sagemaker-explanation@sha256:[0-9a-f]{64}$')
        stack = json.loads((ROOT / 'infrastructure/aws/demo-stack.json').read_text(encoding='utf-8'))
        self.assertIn(spec['imageRepository'], stack['ecrRepositories'])
        role = (ROOT / 'infrastructure/aws/iam/sagemaker-explanation-role.inline.sagemaker-explanation-run.json')
        self.assertIn(f'repository/{spec["imageRepository"]}"', role.read_text(encoding='utf-8'))

    def test_model_container_pins_manifest_sha(self):
        container = sagemaker_explanation.model_container(self.spec, self.manifest_sha)
        source = container['ModelDataSource']['S3DataSource']
        self.assertEqual(source['S3Uri'], f's3://{self.spec["bucket"]}/{self.root}')
        self.assertEqual(source['CompressionType'], 'None')
        self.assertEqual(container['Environment']['MODEL_MANIFEST_SHA256'], self.manifest_sha)
        self.assertEqual(container['Environment']['VLLM_ALLOW_RUNTIME_LORA_UPDATING'], 'true')
        self.assertNotIn('MODEL_MANIFEST_SHA256', self.spec['environment'])

    def test_verify_rejects_unused_formats_left_under_the_version_root(self):
        self.assertEqual(sagemaker_explanation.check_manifest(self.aws, self.spec, self.args), (0, self.manifest_sha))
        self.aws.objects[self.root + 'base-gguf/model-00001-of-00004.gguf'] = b'G'
        self.assertEqual(sagemaker_explanation.check_manifest(self.aws, self.spec, self.args)[0], 1)

    def test_lock_adds_deny_after_verify_and_keeps_other_statements(self):
        other = {'Sid': 'Other', 'Effect': 'Deny', 'Principal': '*', 'Action': 's3:*',
                 'Resource': 'arn:aws:s3:::x/*', 'Condition': {'Bool': {'aws:SecureTransport': 'false'}}}
        self.aws.policy = {'Version': '2012-10-17', 'Statement': [other]}
        self.assertEqual(sagemaker_explanation.lock(self.aws, self.spec, self.args), 0)
        statements = self.aws.policy['Statement']
        self.assertEqual(statements[0], other)
        lock = statements[1]
        self.assertEqual((lock['Effect'], lock['Principal']), ('Deny', '*'))
        self.assertEqual(sorted(lock['Action']), ['s3:DeleteObject', 's3:DeleteObjectVersion', 's3:PutObject'])
        self.assertEqual(lock['Resource'], f'arn:aws:s3:::{self.spec["bucket"]}/{self.root}*')
        self.assertRegex(lock['Sid'], r'^[A-Za-z0-9]+$')
        sagemaker_explanation.lock(self.aws, self.spec, self.args)  # idempotent
        self.assertEqual(len(self.aws.policy['Statement']), 2)

    def test_lock_refuses_mismatch_wrong_account_and_other_paths(self):
        self.aws.objects[self.root + 'adapter-gguf/explain.gguf'] = b'G'
        with self.assertRaises(SystemExit):
            sagemaker_explanation.lock(self.aws, self.spec, self.args)
        self.assertIsNone(self.aws.policy)
        for change in ({'confirm_account': '111111111111'}, {'prefix': 'reports/'}, {'prefix': 'explanation/x'}):
            args = mock.Mock(
                local_manifest=None, confirm_account=change.get('confirm_account', '000000000000'),
                prefix=change.get('prefix'), remove=False, dry_run=False)
            with self.assertRaises(SystemExit):
                sagemaker_explanation.lock(self.aws, self.spec, args)
        self.assertIsNone(self.aws.policy)

    def test_trial_lock_dry_run_and_remove(self):
        trial = mock.Mock(local_manifest=None, confirm_account='000000000000', prefix='explanation/trial/',
                          remove=False, dry_run=True)
        sagemaker_explanation.lock(self.aws, self.spec, trial)
        self.assertIsNone(self.aws.policy)
        trial.dry_run = False
        sagemaker_explanation.lock(self.aws, self.spec, trial)
        self.assertEqual(len(self.aws.policy['Statement']), 1)
        trial.remove = True
        sagemaker_explanation.lock(self.aws, self.spec, trial)
        self.assertIsNone(self.aws.policy)  # empty policy is deleted, not stored


if __name__ == '__main__':
    unittest.main()
