"""Report Gemma SageMaker real-time endpoint (#746): create, schedule, inspect, invoke, delete.

Like demo_stack.py, every call goes through the aws CLI (Python standard library only) and the
desired state lives in sagemaker/explanation-endpoint.json. IAM roles and the security group are
defined in demo-stack.json / iam/ and created separately (see README). Run from the repository root:

  python infrastructure/aws/sagemaker_explanation.py --profile <p> status
  python infrastructure/aws/sagemaker_explanation.py --profile <p> lock --confirm-account <id>   # #777 path lock
  python infrastructure/aws/sagemaker_explanation.py --profile <p> apply --confirm-account <id>
  python infrastructure/aws/sagemaker_explanation.py --profile <p> schedule            # weekly window
  python infrastructure/aws/sagemaker_explanation.py --profile <p> schedule --test-start 2026-11-18T15:10 --test-end 2026-11-18T15:50
  python infrastructure/aws/sagemaker_explanation.py --profile <p> copies 0|1          # manual scale
  python infrastructure/aws/sagemaker_explanation.py --profile <p> invoke --body request.json
  python infrastructure/aws/sagemaker_explanation.py --profile <p> delete --confirm-account <id>

Only synthetic inputs may be sent with `invoke`; generated text is not printed unless --show.
`--spec <file>` swaps the desired-state file (trial endpoints with other names and model paths).

#777: the model data is the whole version root `explanation/<version>/` (manifest.json + base + adapter),
the image is model-check/Dockerfile (DLC + startup sha256 check), and MODEL_MANIFEST_SHA256 is set from
the manifest's S3 FULL_OBJECT SHA-256, so every cold start re-checks the downloaded files.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
SPEC = HERE / 'sagemaker' / 'explanation-endpoint.json'
SCALABLE_DIMENSION = 'sagemaker:inference-component:DesiredCopyCount'


class Aws:
    def __init__(self, profile, region):
        self.profile, self.region = profile, region

    def __call__(self, service, operation, *args, check=True, payload=None, timeout_args=()):
        cmd = ['aws', service, operation, *args, '--output', 'json', '--region', self.region, *timeout_args]
        if self.profile:
            cmd += ['--profile', self.profile]
        tmp = None
        if payload is not None:
            tmp = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8')
            json.dump(payload, tmp)
            tmp.close()
            cmd += ['--cli-input-json', f'file://{tmp.name}']
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        finally:
            if tmp:
                Path(tmp.name).unlink(missing_ok=True)
        if result.returncode != 0:
            if check:
                raise RuntimeError(f'aws {service} {operation} failed: {result.stderr.strip()[:500]}')
            return None
        return json.loads(result.stdout) if result.stdout.strip() else {}


def load_spec(aws, path=SPEC):
    raw = json.loads(Path(path).read_text(encoding='utf-8'))
    account = aws('sts', 'get-caller-identity')['Account']
    values = {'account': account, 'region': raw['region'], 'modelVersion': raw['modelVersion'],
              'imageDigest': raw.get('imageDigest', ''),
              'instanceSlug': raw['instanceType'].replace('ml.', '').replace('.', '-')}

    def fill(v):
        if isinstance(v, str):
            for _ in range(3):
                v = v.format(**values) if '{' in v and not v.startswith('{"') else v
            return v
        if isinstance(v, list):
            return [fill(x) for x in v]
        if isinstance(v, dict):
            return {k: (fill(x) if not k.endswith('nvironment') else x) for k, x in v.items()}
        return v

    spec = fill(raw)
    spec['account'] = account
    spec['tagList'] = [{'Key': k, 'Value': v} for k, v in raw['tags'].items()]
    return spec


def resolve_network(aws, spec):
    subnets = aws('ec2', 'describe-subnets', '--filters', 'Name=tag:Name,Values=' + ','.join(spec['subnetNames']))['Subnets']
    groups = aws('ec2', 'describe-security-groups', '--filters', f'Name=group-name,Values={spec["securityGroup"]}')['SecurityGroups']
    if len(subnets) != len(spec['subnetNames']) or len(groups) != 1:
        raise SystemExit(f'network not found: subnets={len(subnets)} security groups={len(groups)}')
    return {'Subnets': sorted(s['SubnetId'] for s in subnets), 'SecurityGroupIds': [groups[0]['GroupId']]}


def role_arn(spec):
    return f'arn:aws:iam::{spec["account"]}:role/{spec["executionRole"]}'


def s3_source(spec, prefix):
    return {'S3DataSource': {'S3Uri': f's3://{spec["bucket"]}/{prefix}', 'S3DataType': 'S3Prefix',
                             'CompressionType': 'None'}}


def describe(aws, kind, name):
    key = {'model': 'model-name', 'endpoint-config': 'endpoint-config-name', 'endpoint': 'endpoint-name',
           'inference-component': 'inference-component-name'}[kind]
    return aws('sagemaker', f'describe-{kind}', f'--{key}', name, check=False)


def wait_status(aws, kind, name, field, done, timeout=3600):
    start = time.time()
    last = None
    while True:
        info = describe(aws, kind, name)
        status = info.get(field) if info else 'Missing'
        if status != last:
            print(f'  {time.strftime("%H:%M:%S")} {kind} {name}: {status} (+{int(time.time() - start)}s)', flush=True)
            last = status
        if status in done:
            return info
        if status == 'Failed' or time.time() - start > timeout:
            raise SystemExit(f'{kind} {name} {status}: {info.get("FailureReason") if info else ""}')
        time.sleep(15)


def used_prefixes(spec):
    return [spec['baseModelPrefix']] + ([spec['adapterPrefix']] if spec['useAdapter'] else [])


def head_sha256(aws, spec, key):
    import base64
    head = aws('s3api', 'head-object', '--bucket', spec['bucket'], '--key', key, '--checksum-mode', 'ENABLED')
    return head.get('ChecksumType'), base64.b64decode(head.get('ChecksumSHA256', '')).hex(), head['ContentLength']


def manifest(aws, spec, args):
    """Write the approved file list (key·bytes·sha256 of every object SageMaker reads) from the measured
    record and upload it once to explanation/<version>/manifest.json (If-None-Match, FULL_OBJECT SHA-256)."""
    import base64
    import hashlib
    record = json.loads(Path(args.hashes).read_text(encoding='utf-8'))['s3']
    root = spec['manifestKey'].rsplit('/', 1)[0] + '/'
    files = []
    for prefix in used_prefixes(spec):
        part = record[prefix[len(root):]]
        entries = part.get('files', {k: v for k, v in part.items() if isinstance(v, dict)})
        files += [{'key': prefix + name, 'bytes': meta['bytes'], 'sha256': meta['sha256']} for name, meta in sorted(entries.items())]
    body = json.dumps({'modelVersion': spec['modelVersion'], 'prefixes': used_prefixes(spec), 'files': files},
                      ensure_ascii=False, indent=1).encode('utf-8') + b'\n'
    digest = hashlib.sha256(body).digest()
    print(f'manifest {len(files)} files sha256={digest.hex()}')
    if not args.upload:
        Path(args.out).write_bytes(body)
        print(f'wrote {args.out} (not uploaded)')
        return 0
    with tempfile.NamedTemporaryFile('wb', suffix='.json', delete=False) as tmp:
        tmp.write(body)
    try:
        aws('s3api', 'put-object', '--bucket', spec['bucket'], '--key', spec['manifestKey'], '--body', tmp.name,
            '--content-type', 'application/json', '--checksum-sha256', base64.b64encode(digest).decode(),
            '--if-none-match', '*')
    finally:
        Path(tmp.name).unlink(missing_ok=True)
    kind, sha, _ = head_sha256(aws, spec, spec['manifestKey'])
    print(f'uploaded {spec["manifestKey"]} {kind} {sha}')
    return 0 if kind == 'FULL_OBJECT' and sha == digest.hex() else 1


def verify(aws, spec, args):
    """SageMaker does not check sha256 when it loads model data (#368·#493). Before apply, compare every
    object under the version root SageMaker reads (`modelDataPrefix`) with manifest.json: the S3 FULL_OBJECT
    SHA-256 that S3 itself validated on upload must equal the manifest, and no extra or missing object is
    allowed (SageMaker downloads everything under the prefix, so unused formats such as base-gguf/ must be
    removed first). The manifest itself is checked the same way. The serving image repeats the file check
    inside the container on every start (#777)."""
    return check_manifest(aws, spec, args)[0]


def check_manifest(aws, spec, args):
    """(0 or 1, sha256 of manifest.json) for verify/apply/lock."""
    import hashlib
    if getattr(args, 'local_manifest', None):
        body = Path(args.local_manifest).read_bytes()
        good = True
        print(f'LOCAL manifest {args.local_manifest} (not the uploaded copy; for trials before upload)')
    else:
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / 'manifest.json'
            aws('s3api', 'get-object', '--bucket', spec['bucket'], '--key', spec['manifestKey'], str(local))
            body = local.read_bytes()
        kind, sha, _ = head_sha256(aws, spec, spec['manifestKey'])
        good = kind == 'FULL_OBJECT' and sha == hashlib.sha256(body).hexdigest()
        print(f'{"OK  " if good else "DIFF"} manifest.json {sha[:8]}')
    manifest_sha = hashlib.sha256(body).hexdigest()
    data = json.loads(body)
    if data['prefixes'] != used_prefixes(spec):
        print(f'PREFIX     manifest {data["prefixes"]} != spec {used_prefixes(spec)}')
        good = False
    expected = {f['key']: f for f in data['files']}
    if not all(p.startswith(spec['modelDataPrefix']) for p in used_prefixes(spec)) \
            or not spec['manifestKey'].startswith(spec['modelDataPrefix']):
        raise SystemExit('modelDataPrefix must contain manifestKey and every prefix SageMaker reads')
    actual = list_keys(aws, spec['bucket'], spec['modelDataPrefix']) - {spec['manifestKey']}
    good &= actual == set(expected)
    for key in sorted(actual - set(expected)):
        print(f'UNEXPECTED {key}')
    for key in sorted(set(expected) - actual):
        print(f'MISSING    {key}')
    for key in sorted(actual & set(expected)):
        kind, sha, size = head_sha256(aws, spec, key)
        ok = kind == 'FULL_OBJECT' and sha == expected[key]['sha256'] and size == expected[key]['bytes']
        good &= ok
        print(f'{"OK  " if ok else "DIFF"} {key.rsplit("/", 2)[-2]}/{key.rsplit("/", 1)[-1]} {sha[:8]}')
    print('verify:', 'all objects match' if good else 'MISMATCH')
    return (0 if good else 1), manifest_sha


def list_keys(aws, bucket, prefix):
    keys, token = set(), []
    while True:
        listed = aws('s3api', 'list-objects-v2', '--bucket', bucket, '--prefix', prefix, *token)
        keys |= {o['Key'] for o in listed.get('Contents', [])}
        if not listed.get('NextContinuationToken'):
            return keys
        token = ['--continuation-token', listed['NextContinuationToken']]


def model_container(spec, manifest_sha):
    """The SageMaker model container: the check image, the whole version root, and the manifest pin."""
    environment = dict(spec['environment'])
    if spec['useAdapter']:
        environment.update(spec['adapterEnvironment'])
    environment['MODEL_MANIFEST_SHA256'] = manifest_sha
    return {'Image': spec['image'], 'ModelDataSource': s3_source(spec, spec['modelDataPrefix']),
            'Environment': environment}


def lock_sid(prefix):
    return 'LockModel' + re.sub('[^A-Za-z0-9]', '', prefix)[:90]


def lock_statement(bucket, prefix):
    """#777: nobody may write, overwrite or delete (any version of) objects under an approved model path."""
    return {'Sid': lock_sid(prefix), 'Effect': 'Deny', 'Principal': '*',
            'Action': ['s3:PutObject', 's3:DeleteObject', 's3:DeleteObjectVersion'],
            'Resource': f'arn:aws:s3:::{bucket}/{prefix}*'}


def bucket_policy(aws, bucket):
    found = aws('s3api', 'get-bucket-policy', '--bucket', bucket, check=False)
    return json.loads(found['Policy']) if found else None


def locked_policy(current, bucket, prefix, remove=False):
    """Bucket policy with the lock statement for prefix added (or removed); other statements are kept."""
    policy = current or {'Version': '2012-10-17', 'Statement': []}
    statements = [s for s in policy.get('Statement', []) if s.get('Sid') != lock_sid(prefix)]
    if not remove:
        statements.append(lock_statement(bucket, prefix))
    return dict(policy, Statement=statements)


def lock(aws, spec, args):
    """Add the deny statement for the approved version root to the model bucket policy (after verify).
    `--prefix` locks another path (trial); `--remove` drops a lock again (trial revert only)."""
    if args.confirm_account != spec['account']:
        raise SystemExit('lock needs --confirm-account <current account id>')
    prefix = args.prefix or spec['lockPrefix']
    if not prefix.endswith('/') or not prefix.startswith('explanation/'):
        raise SystemExit('lock prefix must be explanation/<path>/')
    if not args.prefix and not args.remove and check_manifest(aws, spec, args)[0] != 0:
        raise SystemExit('model data does not match manifest.json; not locking')
    current = bucket_policy(aws, spec['bucket'])
    policy = locked_policy(current, spec['bucket'], prefix, remove=args.remove)
    print(json.dumps(policy, indent=1))
    if args.dry_run:
        print('dry run: bucket policy not changed')
        return 0
    if policy['Statement']:
        aws('s3api', 'put-bucket-policy', '--bucket', spec['bucket'], '--policy', json.dumps(policy))
    else:
        aws('s3api', 'delete-bucket-policy', '--bucket', spec['bucket'])
    print(f'{"unlocked" if args.remove else "locked"} s3://{spec["bucket"]}/{prefix}')
    return 0


def apply(aws, spec, args):
    if args.confirm_account != spec['account']:
        raise SystemExit('apply needs --confirm-account <current account id>')
    code, manifest_sha = check_manifest(aws, spec, args)
    if code != 0:
        raise SystemExit('model data does not match manifest.json; not applying')
    network = resolve_network(aws, spec)
    if not describe(aws, 'model', spec['model']):
        container = model_container(spec, manifest_sha)
        aws('sagemaker', 'create-model', payload={
            'ModelName': spec['model'],
            'ExecutionRoleArn': role_arn(spec),
            'PrimaryContainer': container,
            'VpcConfig': network,
            'EnableNetworkIsolation': False,
            'Tags': spec['tagList'],
        })
        print('created model', spec['model'])
    if not describe(aws, 'endpoint-config', spec['endpointConfig']):
        aws('sagemaker', 'create-endpoint-config', payload={
            'EndpointConfigName': spec['endpointConfig'],
            'ExecutionRoleArn': role_arn(spec),
            'VpcConfig': network,
            'ProductionVariants': [{
                'VariantName': 'AllTraffic',
                'InstanceType': spec['instanceType'],
                'InitialInstanceCount': 1,
                'ManagedInstanceScaling': {'Status': 'ENABLED', 'MinInstanceCount': 0,
                                           'MaxInstanceCount': spec['maxInstances']},
                'RoutingConfig': {'RoutingStrategy': 'LEAST_OUTSTANDING_REQUESTS'},
                'ModelDataDownloadTimeoutInSeconds': spec['startupTimeoutSeconds'],
                'ContainerStartupHealthCheckTimeoutInSeconds': spec['startupTimeoutSeconds'],
            }],
            'Tags': spec['tagList'],
        })
        print('created endpoint config', spec['endpointConfig'])
    endpoint = describe(aws, 'endpoint', spec['endpoint'])
    if not endpoint:
        aws('sagemaker', 'create-endpoint', '--endpoint-name', spec['endpoint'],
            '--endpoint-config-name', spec['endpointConfig'], '--tags', json.dumps(spec['tagList']))
        print('creating endpoint', spec['endpoint'])
    elif endpoint['EndpointConfigName'] != spec['endpointConfig']:
        # SageMaker rejects update-endpoint with another instance type when inference components are
        # used (ValidationException, 2026-11-18), so the endpoint is recreated.
        if describe(aws, 'inference-component', spec['inferenceComponent']):
            raise SystemExit('delete the inference component before switching the endpoint config')
        wait_status(aws, 'endpoint', spec['endpoint'], 'EndpointStatus', {'InService'})
        aws('sagemaker', 'delete-endpoint', '--endpoint-name', spec['endpoint'])
        print(f'recreating endpoint {endpoint["EndpointConfigName"]} -> {spec["endpointConfig"]}')
        while describe(aws, 'endpoint', spec['endpoint']):
            time.sleep(10)
        aws('sagemaker', 'create-endpoint', '--endpoint-name', spec['endpoint'],
            '--endpoint-config-name', spec['endpointConfig'], '--tags', json.dumps(spec['tagList']))
    wait_status(aws, 'endpoint', spec['endpoint'], 'EndpointStatus', {'InService'})
    if not describe(aws, 'inference-component', spec['inferenceComponent']):
        aws('sagemaker', 'create-inference-component', payload={
            'InferenceComponentName': spec['inferenceComponent'],
            'EndpointName': spec['endpoint'],
            'VariantName': 'AllTraffic',
            'Specification': {
                'ModelName': spec['model'],
                'StartupParameters': {'ModelDataDownloadTimeoutInSeconds': spec['startupTimeoutSeconds'],
                                      'ContainerStartupHealthCheckTimeoutInSeconds': spec['startupTimeoutSeconds']},
                'ComputeResourceRequirements': {'NumberOfAcceleratorDevicesRequired': 1,
                                                'MinMemoryRequiredInMb': spec['minMemoryMb']},
            },
            'RuntimeConfig': {'CopyCount': 1},
            'Tags': spec['tagList'],
        })
        print('creating inference component', spec['inferenceComponent'])
    wait_status(aws, 'inference-component', spec['inferenceComponent'], 'InferenceComponentStatus', {'InService'})
    if spec['useAdapter'] and not describe(aws, 'inference-component', spec['adapterComponent']):
        # SageMaker loads the adapter through the container's POST /adapters (vLLM runtime LoRA loading);
        # calls to this component name are routed to the LoRA (the request body's model name is not used).
        aws('sagemaker', 'create-inference-component', payload={
            'InferenceComponentName': spec['adapterComponent'],
            'EndpointName': spec['endpoint'],
            'Specification': {'BaseInferenceComponentName': spec['inferenceComponent'],
                              'Container': {'ArtifactUrl': f's3://{spec["bucket"]}/{spec["adapterPrefix"]}'}},
            'Tags': spec['tagList'],
        })
        wait_status(aws, 'inference-component', spec['adapterComponent'], 'InferenceComponentStatus', {'InService'})
    register_target(aws, spec, 0, spec['maxInstances'])


def register_target(aws, spec, low, high):
    aws('application-autoscaling', 'register-scalable-target', '--service-namespace', 'sagemaker',
        '--resource-id', f'inference-component/{spec["inferenceComponent"]}',
        '--scalable-dimension', SCALABLE_DIMENSION, '--min-capacity', str(low), '--max-capacity', str(high))
    print(f'scalable target min={low} max={high}')


def schedule(aws, spec, args):
    resource = f'inference-component/{spec["inferenceComponent"]}'
    common = ['--service-namespace', 'sagemaker', '--resource-id', resource, '--scalable-dimension', SCALABLE_DIMENSION]
    if args.test_start:
        plan = [('explanation-test-out', f'at({args.test_start}:00)', 1), ('explanation-test-in', f'at({args.test_end}:00)', 0)]
        tz = 'UTC'
    else:
        plan = [('explanation-window-out', spec['schedule']['scaleOut'], 1), ('explanation-window-in', spec['schedule']['scaleIn'], 0)]
        tz = spec['schedule']['timezone']
    for name, expression, copies in plan:
        aws('application-autoscaling', 'put-scheduled-action', *common, '--scheduled-action-name', name,
            '--schedule', expression, '--timezone', tz,
            '--scalable-target-action', f'MinCapacity={copies},MaxCapacity={copies if copies == 0 else spec["maxInstances"]}')
        print(f'scheduled {name}: {expression} {tz} -> {copies}')


def copies(aws, spec, args):
    n = args.count
    register_target(aws, spec, n, n if n == 0 else spec['maxInstances'])
    aws('sagemaker', 'update-inference-component-runtime-config', '--inference-component-name',
        spec['inferenceComponent'], '--desired-runtime-config', f'CopyCount={n}')
    print(f'copy count -> {n}')
    if args.wait:
        start = time.time()
        while True:
            info = describe(aws, 'inference-component', spec['inferenceComponent'])
            rc = info.get('RuntimeConfig', {})
            variant = describe(aws, 'endpoint', spec['endpoint'])['ProductionVariants'][0]
            print(f'  +{int(time.time() - start)}s ic={info["InferenceComponentStatus"]} copies={rc.get("CurrentCopyCount")}/'
                  f'{rc.get("DesiredCopyCount")} instances={variant.get("CurrentInstanceCount")}', flush=True)
            if rc.get('CurrentCopyCount') == n and info['InferenceComponentStatus'] == 'InService' \
                    and (n > 0 or variant.get('CurrentInstanceCount') == 0):
                return
            time.sleep(15)


def status(aws, spec, args):
    for kind, name, field in [('model', spec['model'], 'ModelName'), ('endpoint-config', spec['endpointConfig'], 'EndpointConfigName'),
                              ('endpoint', spec['endpoint'], 'EndpointStatus'),
                              ('inference-component', spec['inferenceComponent'], 'InferenceComponentStatus')]:
        info = describe(aws, kind, name)
        print(f'{kind:20} {name}: {info.get(field) if info else "missing"}')
        if info and kind == 'endpoint':
            v = info['ProductionVariants'][0]
            print(f'{"":20} instances current={v.get("CurrentInstanceCount")} desired={v.get("DesiredInstanceCount")}')
        if info and kind == 'inference-component':
            print(f'{"":20} copies {info.get("RuntimeConfig")}')
    resource = f'inference-component/{spec["inferenceComponent"]}'
    targets = aws('application-autoscaling', 'describe-scalable-targets', '--service-namespace', 'sagemaker',
                  '--resource-ids', resource)['ScalableTargets']
    for t in targets:
        print(f'scalable target min={t["MinCapacity"]} max={t["MaxCapacity"]}')
    actions = aws('application-autoscaling', 'describe-scheduled-actions', '--service-namespace', 'sagemaker',
                  '--resource-id', resource)['ScheduledActions']
    for a in actions:
        print(f'scheduled {a["ScheduledActionName"]}: {a["Schedule"]} {a.get("Timezone", "UTC")} {a["ScalableTargetAction"]}')
    policy = bucket_policy(aws, spec['bucket']) or {}
    locked = any(s.get('Sid') == lock_sid(spec['lockPrefix']) for s in policy.get('Statement', []))
    print(f'path lock {spec["lockPrefix"]}: {"locked" if locked else "NOT locked"}')


def invoke(aws, spec, args):
    body = Path(args.body).read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / 'out.json'
        start = time.time()
        result = subprocess.run(
            ['aws', 'sagemaker-runtime', 'invoke-endpoint', '--endpoint-name', spec['endpoint'],
             '--inference-component-name', args.component or spec['inferenceComponent'], '--content-type', 'application/json',
             '--body', f'fileb://{Path(args.body).resolve()}', '--region', spec['region'],
             '--cli-read-timeout', '70', '--cli-connect-timeout', '10', *(['--profile', aws.profile] if aws.profile else []),
             str(out)], capture_output=True, text=True, encoding='utf-8')
        elapsed = time.time() - start
        if result.returncode != 0:
            print(json.dumps({'ok': False, 'seconds': round(elapsed, 1), 'error': result.stderr.strip()[:400]}, ensure_ascii=False))
            return 1
        reply = json.loads(out.read_text(encoding='utf-8'))
    choice = reply['choices'][0]
    summary = {'ok': True, 'seconds': round(elapsed, 1), 'model': reply.get('model'), 'finish': choice.get('finish_reason'),
               'usage': reply.get('usage'), 'request_bytes': len(body)}
    print(json.dumps(summary, ensure_ascii=False))
    if args.save:
        Path(args.save).write_text(json.dumps(reply, ensure_ascii=False), encoding='utf-8')
    if args.show:
        print(choice['message'].get('content'))
    return 0


def delete(aws, spec, args):
    if args.confirm_account != spec['account']:
        raise SystemExit('delete needs --confirm-account <current account id>')
    resource = f'inference-component/{spec["inferenceComponent"]}'
    for a in aws('application-autoscaling', 'describe-scheduled-actions', '--service-namespace', 'sagemaker',
                 '--resource-id', resource)['ScheduledActions']:
        aws('application-autoscaling', 'delete-scheduled-action', '--service-namespace', 'sagemaker', '--resource-id', resource,
            '--scalable-dimension', SCALABLE_DIMENSION, '--scheduled-action-name', a['ScheduledActionName'])
    aws('application-autoscaling', 'deregister-scalable-target', '--service-namespace', 'sagemaker', '--resource-id', resource,
        '--scalable-dimension', SCALABLE_DIMENSION, check=False)
    for component in (spec['adapterComponent'], spec['inferenceComponent']):
        if describe(aws, 'inference-component', component):
            aws('sagemaker', 'delete-inference-component', '--inference-component-name', component)
            while describe(aws, 'inference-component', component):
                time.sleep(15)
    if describe(aws, 'endpoint', spec['endpoint']):
        aws('sagemaker', 'delete-endpoint', '--endpoint-name', spec['endpoint'])
        while describe(aws, 'endpoint', spec['endpoint']):
            time.sleep(15)
    for kind, name, flag in [('endpoint-config', spec['endpointConfig'], '--endpoint-config-name'),
                             ('model', spec['model'], '--model-name')]:
        if describe(aws, kind, name):
            aws('sagemaker', f'delete-{kind}', flag, name)
    print('deleted endpoint, inference component, endpoint config, model, scaling (IAM/SG/S3 kept)')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--profile')
    p.add_argument('--spec', default=str(SPEC), help='desired-state JSON (default: sagemaker/explanation-endpoint.json)')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('status')
    hashes = str(HERE.parent.parent / 'ml' / 'sllm' / 'results' / 'serving-compare-20261118.json')
    m = sub.add_parser('manifest'); m.add_argument('--hashes', default=hashes); m.add_argument('--out', default='manifest.json')
    m.add_argument('--upload', action='store_true', help='upload once to S3 (If-None-Match; the path is never rewritten)')
    v = sub.add_parser('verify'); v.add_argument('--local-manifest')
    a = sub.add_parser('apply'); a.add_argument('--confirm-account'); a.add_argument('--local-manifest')
    k = sub.add_parser('lock'); k.add_argument('--confirm-account'); k.add_argument('--dry-run', action='store_true')
    k.add_argument('--prefix', help='lock another explanation/<path>/ (trial)'); k.add_argument('--remove', action='store_true')
    s = sub.add_parser('schedule'); s.add_argument('--test-start', help='UTC yyyy-mm-ddThh:mm'); s.add_argument('--test-end')
    c = sub.add_parser('copies'); c.add_argument('count', type=int, choices=[0, 1]); c.add_argument('--wait', action='store_true')
    i = sub.add_parser('invoke'); i.add_argument('--body', required=True)
    i.add_argument('--component', help='inference component to call (default: base; adapter component applies LoRA)'); i.add_argument('--save'); i.add_argument('--show', action='store_true')
    d = sub.add_parser('delete'); d.add_argument('--confirm-account')
    args = p.parse_args()
    raw = json.loads(Path(args.spec).read_text(encoding='utf-8'))
    aws = Aws(args.profile, raw['region'])
    spec = load_spec(aws, args.spec)
    handler = {'status': status, 'manifest': manifest, 'verify': verify, 'lock': lock, 'apply': apply, 'schedule': schedule,
               'copies': copies, 'invoke': invoke, 'delete': delete}
    return handler[args.command](aws, spec, args) or 0


if __name__ == '__main__':
    sys.exit(main())
