"""AWS demo stack (#185): read-only drift plan, create-only apply, eksctl rendering, pause/resume.

Every AWS/Kubernetes call goes through the aws CLI or kubectl. Nothing is modified unless
--execute (pause/resume/rds-bootstrap) or `apply --confirm-account` is given. Secret values are
never printed.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
SPEC = HERE / 'demo-stack.json'
# Shared with the local PostgreSQL init (#230); Helm .Files reads only inside the chart.
BOOTSTRAP_SQL = HERE.parent / 'gitops/charts/platform-data/files/postgres'


class Aws:
    def __init__(self, profile, region, executable='aws'):
        self.profile, self.region, self.executable = profile, region, executable

    def __call__(self, service, operation, *args, region=None, check=True):
        cmd = [self.executable, service, operation, *args, '--output', 'json',
               '--region', region or self.region]
        if self.profile:
            cmd += ['--profile', self.profile]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            if check:
                raise RuntimeError(f'aws {service} {operation} failed: {result.stderr.strip()[:300]}')
            return None
        return json.loads(result.stdout) if result.stdout.strip() else {}


class Kubectl:
    def __init__(self, kubeconfig, executable='kubectl'):
        self.kubeconfig, self.executable = kubeconfig, executable

    def __call__(self, *args, stdin=None, check=True):
        result = subprocess.run([self.executable, '--kubeconfig', self.kubeconfig, *args],
                                input=stdin, capture_output=True, text=True)
        if check and result.returncode != 0:
            raise RuntimeError(f'kubectl {args[0]} failed: {result.stderr.strip()[:300]}')
        return result.stdout


def load_spec(path=SPEC):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def read_doc(relative):
    return json.loads((HERE / relative).read_text(encoding='utf-8'))


def normalize(value):
    """Order-insensitive form of an IAM document (lists of scalars sorted, single string == list)."""
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        items = [normalize(v) for v in value]
        if all(not isinstance(v, (dict, list)) for v in items):
            return sorted(items, key=str)
        return sorted(items, key=lambda v: json.dumps(v, sort_keys=True))
    return value


def same_policy(a, b):
    def expand(doc):
        doc = normalize(doc)
        for statement in doc.get('Statement', []):
            for key in ('Action', 'Resource'):
                if isinstance(statement.get(key), str):
                    statement[key] = [statement[key]]
        return normalize(doc)
    return expand(a) == expand(b)


def tag_name(resource):
    return next((t['Value'] for t in resource.get('Tags') or [] if t['Key'] == 'Name'), None)


class Report:
    def __init__(self):
        self.rows = []

    def add(self, kind, name, status, detail=''):
        self.rows.append((kind, name, status, detail))

    def check(self, kind, name, expected, actual, field):
        if expected != actual:
            self.add(kind, name, 'DIFF', f'{field}: expected {expected!r}, actual {actual!r}')
            return False
        return True

    def print(self):
        for kind, name, status, detail in self.rows:
            print(f'{status:8} {kind:16} {name}' + (f'  {detail}' if detail else ''))
        counts = {}
        for row in self.rows:
            counts[row[2]] = counts.get(row[2], 0) + 1
        print('summary:', ', '.join(f'{k}={v}' for k, v in sorted(counts.items())))

    @property
    def ok(self):
        return all(row[2] == 'OK' for row in self.rows)


# ---------------------------------------------------------------- discovery

def find_by_name(aws, operation, key, name, extra=()):
    found = aws('ec2', operation, '--filters', f'Name=tag:Name,Values={name}', *extra)[key]
    return found[0] if found else None


def discover(aws, spec):
    """Current IDs by Name tag; missing resources are absent from the result."""
    net = spec['vpc']
    ids = {'subnets': {}, 'routeTables': {}}
    vpc = find_by_name(aws, 'describe-vpcs', 'Vpcs', net['name'])
    if not vpc:
        return ids
    ids['vpc'] = vpc['VpcId']
    scope = (f'Name=vpc-id,Values={vpc["VpcId"]}',)
    for subnet in aws('ec2', 'describe-subnets', '--filters', *scope)['Subnets']:
        ids['subnets'][tag_name(subnet)] = subnet
    for table in aws('ec2', 'describe-route-tables', '--filters', *scope)['RouteTables']:
        if tag_name(table):
            ids['routeTables'][tag_name(table)] = table
    igw = aws('ec2', 'describe-internet-gateways', '--filters',
              f'Name=attachment.vpc-id,Values={vpc["VpcId"]}')['InternetGateways']
    if igw:
        ids['igw'] = igw[0]['InternetGatewayId']
    nat = aws('ec2', 'describe-nat-gateways', '--filter', *scope,
              'Name=state,Values=pending,available')['NatGateways']
    if nat:
        ids['nat'] = nat[0]
    endpoints = aws('ec2', 'describe-vpc-endpoints', '--filters', *scope,
                    f'Name=service-name,Values=com.amazonaws.{spec["region"]}.s3')['VpcEndpoints']
    if endpoints:
        ids['s3Endpoint'] = endpoints[0]
    groups = aws('ec2', 'describe-security-groups', '--filters', *scope,
                 f'Name=group-name,Values={spec["rds"]["securityGroup"]["name"]}')['SecurityGroups']
    if groups:
        ids['rdsSg'] = groups[0]
    return ids


# ---------------------------------------------------------------- plan

def plan_network(aws, spec, ids, report):
    net = spec['vpc']
    if 'vpc' not in ids:
        report.add('vpc', net['name'], 'MISSING')
        return
    vpc = aws('ec2', 'describe-vpcs', '--vpc-ids', ids['vpc'])['Vpcs'][0]
    if report.check('vpc', net['name'], net['cidr'], vpc['CidrBlock'], 'cidr'):
        report.add('vpc', net['name'], 'OK')
    report.add('igw', net['internetGateway'], 'OK' if 'igw' in ids else 'MISSING')
    nat = ids.get('nat')
    nat_subnet = ids['subnets'].get(net['natGateway']['subnet'], {}).get('SubnetId')
    if not nat:
        report.add('nat', net['natGateway']['name'], 'MISSING')
    elif report.check('nat', net['natGateway']['name'], nat_subnet, nat['SubnetId'], 'subnet'):
        report.add('nat', net['natGateway']['name'], 'OK')
    for want in net['subnets']:
        have = ids['subnets'].get(want['name'])
        if not have:
            report.add('subnet', want['name'], 'MISSING')
            continue
        good = report.check('subnet', want['name'], want['cidr'], have['CidrBlock'], 'cidr')
        good &= report.check('subnet', want['name'], want['az'], have['AvailabilityZone'], 'az')
        role = 'kubernetes.io/role/elb' if want['tier'] == 'public' else 'kubernetes.io/role/internal-elb'
        good &= report.check('subnet', want['name'], '1',
                             next((t['Value'] for t in have.get('Tags', []) if t['Key'] == role), None), role)
        table = ids['routeTables'].get(want['routeTable'])
        if not table:
            report.add('route-table', want['routeTable'], 'MISSING')
            continue
        associated = {a.get('SubnetId') for a in table.get('Associations', [])}
        good &= report.check('subnet', want['name'], True, have['SubnetId'] in associated, 'route table association')
        default = next((r for r in table['Routes'] if r.get('DestinationCidrBlock') == '0.0.0.0/0'), {})
        target = default.get('GatewayId') if want['tier'] == 'public' else default.get('NatGatewayId')
        expected = ids.get('igw') if want['tier'] == 'public' else (nat or {}).get('NatGatewayId')
        good &= report.check('route-table', want['routeTable'], expected, target, 'default route')
        if want['tier'] == 'private':
            endpoint_tables = set((ids.get('s3Endpoint') or {}).get('RouteTableIds', []))
            good &= report.check('route-table', want['routeTable'], True,
                                 table['RouteTableId'] in endpoint_tables, 's3 gateway endpoint')
        if good:
            report.add('subnet', want['name'], 'OK')


def plan_buckets(aws, spec, report):
    for bucket in spec['buckets']:
        if aws('s3api', 'head-bucket', '--bucket', bucket, check=False) is None:
            report.add('s3', bucket, 'MISSING')
            continue
        good = report.check('s3', bucket, 'Enabled',
                            aws('s3api', 'get-bucket-versioning', '--bucket', bucket).get('Status'), 'versioning')
        block = aws('s3api', 'get-public-access-block', '--bucket', bucket, check=False) or {}
        good &= report.check('s3', bucket, True,
                             all((block.get('PublicAccessBlockConfiguration') or {}).get(k) for k in
                                 ('BlockPublicAcls', 'IgnorePublicAcls', 'BlockPublicPolicy', 'RestrictPublicBuckets')),
                             'public access block')
        good &= report.check('s3', bucket, True,
                             aws('s3api', 'get-bucket-encryption', '--bucket', bucket, check=False) is not None,
                             'default encryption')
        if good:
            report.add('s3', bucket, 'OK')


def plan_registry_and_secrets(aws, spec, report):
    for repository in spec['ecrRepositories']:
        found = aws('ecr', 'describe-repositories', '--repository-names', repository, check=False)
        if not found:
            report.add('ecr', repository, 'MISSING')
        elif report.check('ecr', repository, 'IMMUTABLE', found['repositories'][0]['imageTagMutability'], 'tags'):
            report.add('ecr', repository, 'OK')
    for name in spec['secrets']:
        # Metadata only; values are never read here.
        found = aws('secretsmanager', 'describe-secret', '--secret-id', name, check=False)
        report.add('secret', name, 'OK' if found else 'MISSING')


def plan_rds(aws, spec, ids, report):
    want = spec['rds']
    group = ids.get('rdsSg')
    report.add('security-group', want['securityGroup']['name'], 'OK' if group else 'MISSING')
    subnet_group = aws('rds', 'describe-db-subnet-groups', '--db-subnet-group-name',
                       want['subnetGroup']['name'], check=False)
    if not subnet_group:
        report.add('db-subnet-group', want['subnetGroup']['name'], 'MISSING')
    else:
        actual = sorted(s['SubnetIdentifier'] for s in subnet_group['DBSubnetGroups'][0]['Subnets'])
        expected = sorted(ids['subnets'].get(n, {}).get('SubnetId') or n for n in want['subnetGroup']['subnets'])
        if report.check('db-subnet-group', want['subnetGroup']['name'], expected, actual, 'subnets'):
            report.add('db-subnet-group', want['subnetGroup']['name'], 'OK')
    found = aws('rds', 'describe-db-instances', '--db-instance-identifier', want['id'], check=False)
    if not found:
        report.add('rds', want['id'], 'MISSING')
        return
    db = found['DBInstances'][0]
    pairs = [
        ('class', want['class'], db['DBInstanceClass']),
        ('engine version', want['version'], db['EngineVersion']),
        ('multi-AZ', want['multiAZ'], db['MultiAZ']),
        ('storage type', want['storageType'], db['StorageType']),
        ('max storage', want['maxStorageGiB'], db.get('MaxAllocatedStorage')),
        ('backup days', want['backupDays'], db['BackupRetentionPeriod']),
        ('public', False, db['PubliclyAccessible']),
        ('encrypted', True, db['StorageEncrypted']),
        ('managed master secret', True, db.get('MasterUserSecret') is not None),
        ('subnet group', want['subnetGroup']['name'], db['DBSubnetGroup']['DBSubnetGroupName']),
        ('security group', [group['GroupId']] if group else None,
         [g['VpcSecurityGroupId'] for g in db['VpcSecurityGroups']]),
    ]
    good = True
    for field, expected, actual in pairs:
        good &= report.check('rds', want['id'], expected, actual, field)
    if db['AllocatedStorage'] < want['storageGiB']:
        report.add('rds', want['id'], 'DIFF', f'storage below {want["storageGiB"]}GiB')
        good = False
    if good:
        report.add('rds', want['id'], 'OK', f'status={db["DBInstanceStatus"]}')


def plan_iam(aws, spec, report):
    for role in spec['iamRoles']:
        name = role['name']
        found = aws('iam', 'get-role', '--role-name', name, check=False)
        if not found:
            report.add('iam-role', name, 'MISSING')
            continue
        good = report.check('iam-role', name, True,
                            same_policy(read_doc(role['trust']), found['Role']['AssumeRolePolicyDocument']), 'trust')
        attached = aws('iam', 'list-attached-role-policies', '--role-name', name)['AttachedPolicies']
        expected = set(role.get('managed', [])) | {
            f'arn:aws:iam::{spec["account"]}:policy/{p}' for p in role.get('customerManaged', {})}
        good &= report.check('iam-role', name, sorted(expected), sorted(p['PolicyArn'] for p in attached),
                             'attached policies')
        for policy, path in role.get('customerManaged', {}).items():
            arn = f'arn:aws:iam::{spec["account"]}:policy/{policy}'
            meta = aws('iam', 'get-policy', '--policy-arn', arn, check=False)
            document = meta and aws('iam', 'get-policy-version', '--policy-arn', arn, '--version-id',
                                    meta['Policy']['DefaultVersionId'])['PolicyVersion']['Document']
            good &= report.check('iam-policy', policy, True, bool(document) and same_policy(read_doc(path), document),
                                 'document')
        inline = set(aws('iam', 'list-role-policies', '--role-name', name)['PolicyNames'])
        good &= report.check('iam-role', name, sorted(role.get('inline', {})), sorted(inline), 'inline names')
        for policy, path in role.get('inline', {}).items():
            if policy in inline:
                document = aws('iam', 'get-role-policy', '--role-name', name, '--policy-name', policy)['PolicyDocument']
                good &= report.check('iam-inline', f'{name}/{policy}', True, same_policy(read_doc(path), document),
                                     'document')
        if good:
            report.add('iam-role', name, 'OK')


def eks_taints(group):
    """eksctl taint (NoSchedule) -> EKS API form (NO_SCHEDULE)."""
    effect = {'NoSchedule': 'NO_SCHEDULE', 'NoExecute': 'NO_EXECUTE', 'PreferNoSchedule': 'PREFER_NO_SCHEDULE'}
    return sorted(({'key': t['key'], 'value': t['value'], 'effect': effect[t['effect']]} for t in group.get('taints', [])),
                  key=json.dumps)


def plan_eks(aws, spec, report):
    config = json.loads((HERE / spec['eks']['config']).read_text(encoding='utf-8'))
    name = config['metadata']['name']
    found = aws('eks', 'describe-cluster', '--name', name, check=False)
    if not found:
        report.add('eks', name, 'MISSING')
        return
    cluster = found['cluster']
    good = report.check('eks', name, config['metadata']['version'], cluster['version'], 'version')
    good &= report.check('eks', name, config['iam']['serviceRoleARN'], cluster['roleArn'], 'service role')
    good &= report.check('eks', name, config['accessConfig']['authenticationMode'],
                         cluster['accessConfig']['authenticationMode'], 'authentication mode')
    good &= report.check('eks', name, config['kubernetesNetworkConfig']['serviceIPv4CIDR'],
                         cluster['kubernetesNetworkConfig']['serviceIpv4Cidr'], 'service CIDR')
    if good:
        report.add('eks', name, 'OK')
    for group in config['managedNodeGroups']:
        found = aws('eks', 'describe-nodegroup', '--cluster-name', name, '--nodegroup-name', group['name'], check=False)
        if not found:
            report.add('nodegroup', group['name'], 'MISSING')
            continue
        node = found['nodegroup']
        good = report.check('nodegroup', group['name'], [group['instanceType']], node['instanceTypes'], 'type')
        good &= report.check('nodegroup', group['name'],
                             {'minSize': group['minSize'], 'desiredSize': group['desiredCapacity'], 'maxSize': group['maxSize']},
                             node['scalingConfig'], 'scaling')
        good &= report.check('nodegroup', group['name'], group['volumeSize'], node.get('diskSize'), 'disk')
        good &= report.check('nodegroup', group['name'], group['iam']['instanceRoleARN'], node['nodeRole'], 'node role')
        good &= report.check('nodegroup', group['name'], group.get('labels', {}), node.get('labels') or {}, 'labels')
        good &= report.check('nodegroup', group['name'], eks_taints(group),
                             sorted(node.get('taints') or [], key=json.dumps), 'taints')
        if good:
            report.add('nodegroup', group['name'], 'OK')
    wanted = {(a['namespace'], a['serviceAccountName']): a['roleARN'] for a in config['iam']['podIdentityAssociations']}
    for addon in config['addons']:
        found = aws('eks', 'describe-addon', '--cluster-name', name, '--addon-name', addon['name'], check=False)
        if not found:
            report.add('addon', addon['name'], 'MISSING')
            continue
        current = found['addon']
        good = report.check('addon', addon['name'], addon['version'], current['addonVersion'], 'version')
        if 'configurationValues' in addon:
            good &= report.check('addon', addon['name'], json.loads(addon['configurationValues']),
                                 json.loads(current.get('configurationValues') or '{}'), 'configuration')
        if good:
            report.add('addon', addon['name'], 'OK')
        for association in addon.get('podIdentityAssociations', []):
            wanted[(association['namespace'], association['serviceAccountName'])] = association['roleARN']
    actual = {}
    for summary in aws('eks', 'list-pod-identity-associations', '--cluster-name', name)['associations']:
        detail = aws('eks', 'describe-pod-identity-association', '--cluster-name', name,
                     '--association-id', summary['associationId'])['association']
        actual[(detail['namespace'], detail['serviceAccount'])] = detail['roleArn']
    for key in sorted(set(wanted) | set(actual)):
        label = '/'.join(key)
        if key not in actual:
            report.add('pod-identity', label, 'MISSING')
        elif key not in wanted:
            report.add('pod-identity', label, 'EXTRA')
        elif report.check('pod-identity', label, wanted[key], actual[key], 'role'):
            report.add('pod-identity', label, 'OK')


def plan(aws, spec):
    report = Report()
    ids = discover(aws, spec)
    plan_network(aws, spec, ids, report)
    plan_buckets(aws, spec, report)
    plan_registry_and_secrets(aws, spec, report)
    plan_rds(aws, spec, ids, report)
    plan_iam(aws, spec, report)
    plan_eks(aws, spec, report)
    return report


# ---------------------------------------------------------------- apply (create missing only)

def tag_spec(spec, kind, name):
    tags = [{'Key': 'Name', 'Value': name}] + [{'Key': k, 'Value': v} for k, v in spec['tags'].items()]
    return json.dumps([{'ResourceType': kind, 'Tags': tags}])


def apply_missing(aws, spec, wait=time.sleep):
    """Create resources reported MISSING. Existing resources are never changed or deleted."""
    net, created = spec['vpc'], []
    ids = discover(aws, spec)
    if 'vpc' not in ids:
        vpc = aws('ec2', 'create-vpc', '--cidr-block', net['cidr'],
                  '--tag-specifications', tag_spec(spec, 'vpc', net['name']))['Vpc']['VpcId']
        aws('ec2', 'modify-vpc-attribute', '--vpc-id', vpc, '--enable-dns-hostnames', '{"Value":true}')
        created.append(('vpc', net['name']))
        ids = discover(aws, spec)
    vpc = ids['vpc']
    for want in net['subnets']:
        if want['name'] not in ids['subnets']:
            aws('ec2', 'create-subnet', '--vpc-id', vpc, '--cidr-block', want['cidr'],
                '--availability-zone', want['az'], '--tag-specifications', tag_spec(spec, 'subnet', want['name']))
            created.append(('subnet', want['name']))
    if 'igw' not in ids:
        igw = aws('ec2', 'create-internet-gateway', '--tag-specifications',
                  tag_spec(spec, 'internet-gateway', net['internetGateway']))['InternetGateway']['InternetGatewayId']
        aws('ec2', 'attach-internet-gateway', '--internet-gateway-id', igw, '--vpc-id', vpc)
        created.append(('igw', net['internetGateway']))
    ids = discover(aws, spec)
    for want in net['subnets']:
        subnet = ids['subnets'][want['name']]['SubnetId']
        role = 'kubernetes.io/role/elb' if want['tier'] == 'public' else 'kubernetes.io/role/internal-elb'
        if not any(t['Key'] == role for t in ids['subnets'][want['name']].get('Tags', [])):
            aws('ec2', 'create-tags', '--resources', subnet, '--tags', f'Key={role},Value=1')
    if 'nat' not in ids:
        allocation = aws('ec2', 'allocate-address', '--domain', 'vpc', '--tag-specifications',
                         tag_spec(spec, 'elastic-ip', net['natGateway']['name']))['AllocationId']
        aws('ec2', 'create-nat-gateway', '--subnet-id', ids['subnets'][net['natGateway']['subnet']]['SubnetId'],
            '--allocation-id', allocation, '--tag-specifications', tag_spec(spec, 'natgateway', net['natGateway']['name']))
        created.append(('nat', net['natGateway']['name']))
        for _ in range(60):
            ids = discover(aws, spec)
            if ids.get('nat', {}).get('State') == 'available':
                break
            wait(10)
        else:
            raise RuntimeError('NAT gateway did not become available')
    for want in net['subnets']:
        if want['routeTable'] not in ids['routeTables']:
            table = aws('ec2', 'create-route-table', '--vpc-id', vpc, '--tag-specifications',
                        tag_spec(spec, 'route-table', want['routeTable']))['RouteTable']['RouteTableId']
            target = ['--gateway-id', ids['igw']] if want['tier'] == 'public' else \
                ['--nat-gateway-id', ids['nat']['NatGatewayId']]
            aws('ec2', 'create-route', '--route-table-id', table, '--destination-cidr-block', '0.0.0.0/0', *target)
            created.append(('route-table', want['routeTable']))
            ids = discover(aws, spec)
        table = ids['routeTables'][want['routeTable']]
        subnet = ids['subnets'][want['name']]['SubnetId']
        if subnet not in {a.get('SubnetId') for a in table.get('Associations', [])}:
            aws('ec2', 'associate-route-table', '--route-table-id', table['RouteTableId'], '--subnet-id', subnet)
    private_tables = sorted({ids['routeTables'][s['routeTable']]['RouteTableId']
                             for s in net['subnets'] if s['tier'] == 'private'})
    if 's3Endpoint' not in ids:
        aws('ec2', 'create-vpc-endpoint', '--vpc-id', vpc, '--vpc-endpoint-type', 'Gateway',
            '--service-name', f'com.amazonaws.{spec["region"]}.s3', '--route-table-ids', *private_tables,
            '--tag-specifications', tag_spec(spec, 'vpc-endpoint', net['s3Endpoint']))
        created.append(('vpc-endpoint', net['s3Endpoint']))
    for bucket in spec['buckets']:
        if aws('s3api', 'head-bucket', '--bucket', bucket, check=False) is None:
            aws('s3api', 'create-bucket', '--bucket', bucket,
                '--create-bucket-configuration', f'LocationConstraint={spec["region"]}')
            aws('s3api', 'put-public-access-block', '--bucket', bucket, '--public-access-block-configuration',
                'BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true')
            aws('s3api', 'put-bucket-versioning', '--bucket', bucket, '--versioning-configuration', 'Status=Enabled')
            aws('s3api', 'put-bucket-encryption', '--bucket', bucket, '--server-side-encryption-configuration',
                '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}')
            created.append(('s3', bucket))
    for repository in spec['ecrRepositories']:
        if not aws('ecr', 'describe-repositories', '--repository-names', repository, check=False):
            aws('ecr', 'create-repository', '--repository-name', repository,
                '--image-tag-mutability', 'IMMUTABLE', '--encryption-configuration', 'encryptionType=AES256')
            created.append(('ecr', repository))
    # Secrets need values from their owners; apply only reports them (see plan).
    for role in spec['iamRoles']:
        if aws('iam', 'get-role', '--role-name', role['name'], check=False):
            continue
        aws('iam', 'create-role', '--role-name', role['name'], '--assume-role-policy-document',
            json.dumps(read_doc(role['trust'])))
        for arn in role.get('managed', []):
            aws('iam', 'attach-role-policy', '--role-name', role['name'], '--policy-arn', arn)
        for policy, path in role.get('customerManaged', {}).items():
            arn = f'arn:aws:iam::{spec["account"]}:policy/{policy}'
            if not aws('iam', 'get-policy', '--policy-arn', arn, check=False):
                aws('iam', 'create-policy', '--policy-name', policy, '--policy-document', json.dumps(read_doc(path)))
            aws('iam', 'attach-role-policy', '--role-name', role['name'], '--policy-arn', arn)
        for policy, path in role.get('inline', {}).items():
            aws('iam', 'put-role-policy', '--role-name', role['name'], '--policy-name', policy,
                '--policy-document', json.dumps(read_doc(path)))
        created.append(('iam-role', role['name']))
    rds = spec['rds']
    if 'rdsSg' not in ids:
        aws('ec2', 'create-security-group', '--group-name', rds['securityGroup']['name'], '--description',
            rds['securityGroup']['description'], '--vpc-id', vpc, '--tag-specifications',
            tag_spec(spec, 'security-group', rds['securityGroup']['name']))
        created.append(('security-group', rds['securityGroup']['name']))
        ids = discover(aws, spec)
    if not aws('rds', 'describe-db-subnet-groups', '--db-subnet-group-name', rds['subnetGroup']['name'], check=False):
        aws('rds', 'create-db-subnet-group', '--db-subnet-group-name', rds['subnetGroup']['name'],
            '--db-subnet-group-description', rds['subnetGroup']['description'], '--subnet-ids',
            *[ids['subnets'][n]['SubnetId'] for n in rds['subnetGroup']['subnets']])
        created.append(('db-subnet-group', rds['subnetGroup']['name']))
    if not aws('rds', 'describe-db-instances', '--db-instance-identifier', rds['id'], check=False):
        aws('rds', 'create-db-instance', '--db-instance-identifier', rds['id'], '--engine', rds['engine'],
            '--engine-version', rds['version'], '--db-instance-class', rds['class'],
            '--allocated-storage', str(rds['storageGiB']), '--max-allocated-storage', str(rds['maxStorageGiB']),
            '--storage-type', rds['storageType'], '--storage-encrypted', '--no-publicly-accessible',
            '--no-multi-az' if not rds['multiAZ'] else '--multi-az', '--master-username', 'postgres',
            '--manage-master-user-password', '--db-subnet-group-name', rds['subnetGroup']['name'],
            '--vpc-security-group-ids', ids['rdsSg']['GroupId'], '--backup-retention-period', str(rds['backupDays']),
            '--preferred-backup-window', rds['backupWindow'], '--preferred-maintenance-window',
            rds['maintenanceWindow'], '--db-parameter-group-name', rds['parameterGroup'], '--copy-tags-to-snapshot',
            '--enable-performance-insights' if rds['performanceInsights'] else '--no-enable-performance-insights',
            '--tags', *[f'Key={k},Value={v}' for k, v in spec['tags'].items()])
        created.append(('rds', rds['id']))
    return created


def allow_rds_from_cluster(aws, spec, ids):
    """RDS ingress needs the EKS cluster security group, so it runs after eksctl."""
    cluster = aws('eks', 'describe-cluster', '--name', spec['eks']['cluster'], check=False)
    group = ids.get('rdsSg')
    if not cluster or not group:
        return False
    source = cluster['cluster']['resourcesVpcConfig']['clusterSecurityGroupId']
    for permission in group.get('IpPermissions', []):
        if permission.get('FromPort') == 5432 and any(p['GroupId'] == source for p in permission.get('UserIdGroupPairs', [])):
            return False
    aws('ec2', 'authorize-security-group-ingress', '--group-id', group['GroupId'], '--ip-permissions',
        json.dumps([{'IpProtocol': 'tcp', 'FromPort': 5432, 'ToPort': 5432,
                     'UserIdGroupPairs': [{'GroupId': source}]}]))
    return True


def create_missing_nodegroups(aws, spec):
    """Managed node groups for an existing cluster (eksctl does not own the console-created one)."""
    config = json.loads((HERE / spec['eks']['config']).read_text(encoding='utf-8'))
    cluster = config['metadata']['name']
    if not aws('eks', 'describe-cluster', '--name', cluster, check=False):
        return []
    ids, created = discover(aws, spec), []
    private = {s['az']: ids['subnets'][s['name']]['SubnetId'] for s in spec['vpc']['subnets'] if s['tier'] == 'private'}
    for group in config['managedNodeGroups']:
        if aws('eks', 'describe-nodegroup', '--cluster-name', cluster, '--nodegroup-name', group['name'], check=False):
            continue
        args = ['--cluster-name', cluster, '--nodegroup-name', group['name'],
                '--subnets', *[private[az] for az in group['availabilityZones']],
                '--instance-types', group['instanceType'], '--ami-type', 'AL2023_x86_64_STANDARD',
                '--capacity-type', 'ON_DEMAND', '--disk-size', str(group['volumeSize']),
                '--node-role', group['iam']['instanceRoleARN'],
                '--scaling-config', f'minSize={group["minSize"]},maxSize={group["maxSize"]},desiredSize={group["desiredCapacity"]}',
                '--update-config', f'maxUnavailable={group["updateConfig"]["maxUnavailable"]}',
                '--tags', ','.join(f'{k}={v}' for k, v in spec['tags'].items())]
        if group.get('labels'):
            args += ['--labels', ','.join(f'{k}={v}' for k, v in group['labels'].items())]
        if group.get('taints'):
            args += ['--taints', json.dumps(eks_taints(group))]
        aws('eks', 'create-nodegroup', *args)
        created.append(('nodegroup', group['name']))
    return created


def render_eksctl(aws, spec, operator_cidrs):
    ids = discover(aws, spec)
    config = (HERE / spec['eks']['config']).read_text(encoding='utf-8')
    names = {s['name']: s for s in spec['vpc']['subnets']}
    values = {'__VPC_ID__': ids['vpc']}
    for name, subnet in names.items():
        suffix = subnet['az'][-2:].upper()
        values[f'__{subnet["tier"].upper()}_SUBNET_{suffix}__'] = ids['subnets'][name]['SubnetId']
    for placeholder, value in values.items():
        config = config.replace(placeholder, value)
    document = json.loads(config)
    document['vpc']['publicAccessCIDRs'] = operator_cidrs
    if '__' in json.dumps(document):
        raise RuntimeError('Unresolved placeholder in eksctl config')
    return document


# ---------------------------------------------------------------- pause / resume

def workload_state(kubectl, spec):
    state = []
    for namespace, kind, name in spec['pause']['drainOrder']:
        data = json.loads(kubectl('get', kind, name, '-n', namespace, '-o', 'json'))
        state.append({'namespace': namespace, 'kind': kind, 'name': name, 'replicas': data['spec'].get('replicas', 1)})
    return state


def pending_messages(kubectl):
    out = kubectl('exec', '-n', 'platform', 'rabbitmq-0', '--', 'rabbitmqctl', 'list_queues', '--quiet',
                  '--formatter', 'json', 'name', 'messages_ready', 'messages_unacknowledged')
    queues = json.loads(out or '[]')
    return {q['name']: q['messages_ready'] + q['messages_unacknowledged']
            for q in queues if q['messages_ready'] + q['messages_unacknowledged']}


def persistent_volumes(kubectl):
    volumes = []
    for pv in json.loads(kubectl('get', 'pv', '-o', 'json'))['items']:
        claim = pv['spec'].get('claimRef', {})
        handle = (pv['spec'].get('csi') or {}).get('volumeHandle')
        if handle:
            volumes.append({'claim': f'{claim.get("namespace")}/{claim.get("name")}', 'volumeId': handle})
    return volumes


def pause(aws, kubectl, spec, state_path, execute, allow_pending=False, wait=time.sleep):
    eks, rds = spec['eks'], spec['rds']['id']
    nodegroups = {name: aws('eks', 'describe-nodegroup', '--cluster-name', eks['cluster'],
                            '--nodegroup-name', name)['nodegroup']['scalingConfig'] for name in eks['nodegroups']}
    state = {'nodegroups': nodegroups, 'workloads': workload_state(kubectl, spec),
             'rdsStatus': aws('rds', 'describe-db-instances', '--db-instance-identifier', rds)['DBInstances'][0]['DBInstanceStatus'],
             'volumes': persistent_volumes(kubectl), 'snapshots': {}}
    pending = pending_messages(kubectl)
    steps = ['scale workloads to 0 in drain order: ' + ', '.join(w['name'] for w in state['workloads']),
             f'RDS snapshot of {rds}', 'EBS snapshot of ' + ', '.join(v['claim'] for v in state['volumes']),
             'nodegroups -> 0 nodes: ' + ', '.join(f'{n} {c}' for n, c in nodegroups.items()), f'stop RDS {rds}']
    print('current:', json.dumps({k: state[k] for k in ('nodegroups', 'rdsStatus')}), 'pending queues:', pending or 'none')
    for number, step in enumerate(steps, 1):
        print(f'{number}. {step}')
    if not execute:
        print('dry run: nothing changed (add --execute to run)')
        return state
    if pending and not allow_pending:
        raise RuntimeError(f'RabbitMQ has unfinished messages: {sorted(pending)}')
    if state['rdsStatus'] != 'available':
        raise RuntimeError(f'RDS is {state["rdsStatus"]}, expected available')
    Path(state_path).write_text(json.dumps(state, indent=2), encoding='utf-8')
    for workload in state['workloads']:
        target = f'{workload["kind"]}/{workload["name"]}'
        kubectl('scale', target, '-n', workload['namespace'], '--replicas=0')
        kubectl('rollout', 'status', target, '-n', workload['namespace'], '--timeout=600s', check=False)
        kubectl('wait', '--for=delete', 'pod', '-n', workload['namespace'], '-l',
                f'app.kubernetes.io/name={workload["name"]}', '--timeout=300s', check=False)
    stamp = time.strftime('%Y%m%d-%H%M%S')
    snapshot = f'{rds}-pause-{stamp}'
    aws('rds', 'create-db-snapshot', '--db-instance-identifier', rds, '--db-snapshot-identifier', snapshot)
    state['snapshots']['rds'] = snapshot
    for volume in state['volumes']:
        made = aws('ec2', 'create-snapshot', '--volume-id', volume['volumeId'], '--description',
                   f'{spec["prefix"]} pause {stamp} {volume["claim"]}')
        state['snapshots'][volume['claim']] = made['SnapshotId']
    Path(state_path).write_text(json.dumps(state, indent=2), encoding='utf-8')
    aws('rds', 'wait', 'db-snapshot-available', '--db-snapshot-identifier', snapshot)
    ebs = [v for k, v in state['snapshots'].items() if k != 'rds']
    if ebs:
        aws('ec2', 'wait', 'snapshot-completed', '--snapshot-ids', *ebs)
    for name, scaling in nodegroups.items():
        aws('eks', 'update-nodegroup-config', '--cluster-name', eks['cluster'], '--nodegroup-name', name,
            '--scaling-config', f'minSize=0,maxSize={scaling["maxSize"]},desiredSize=0')
    for name in nodegroups:
        aws('eks', 'wait', 'nodegroup-active', '--cluster-name', eks['cluster'], '--nodegroup-name', name)
    aws('rds', 'stop-db-instance', '--db-instance-identifier', rds)
    print(f'paused; state saved to {state_path}. RDS restarts automatically after 7 days.')
    return state


def resume(aws, kubectl, spec, state_path, execute, wait=time.sleep):
    state = json.loads(Path(state_path).read_text(encoding='utf-8'))
    eks, rds = spec['eks'], spec['rds']['id']
    nodegroups = state['nodegroups']
    ordered = sorted(state['workloads'], key=lambda w: w['kind'] != 'statefulset')
    stateful = [w for w in ordered if w['kind'] == 'statefulset']
    apps = list(reversed([w for w in ordered if w['kind'] != 'statefulset']))
    print(f'1. start RDS {rds}\n2. nodegroups -> {nodegroups}\n3. statefulsets: {[w["name"] for w in stateful]}\n'
          f'4. deployments: {[w["name"] for w in apps]}')
    if not execute:
        print('dry run: nothing changed (add --execute to run)')
        return
    status = aws('rds', 'describe-db-instances', '--db-instance-identifier', rds)['DBInstances'][0]['DBInstanceStatus']
    if status == 'stopped':
        aws('rds', 'start-db-instance', '--db-instance-identifier', rds)
    aws('rds', 'wait', 'db-instance-available', '--db-instance-identifier', rds)
    for name, scaling in nodegroups.items():
        aws('eks', 'update-nodegroup-config', '--cluster-name', eks['cluster'], '--nodegroup-name', name,
            '--scaling-config', f'minSize={scaling["minSize"]},maxSize={scaling["maxSize"]},desiredSize={scaling["desiredSize"]}')
    for name in nodegroups:
        aws('eks', 'wait', 'nodegroup-active', '--cluster-name', eks['cluster'], '--nodegroup-name', name)
    kubectl('wait', '--for=condition=Ready', 'node', '--all', '--timeout=600s')
    for workload in stateful + apps:
        target = f'{workload["kind"]}/{workload["name"]}'
        kubectl('scale', target, '-n', workload['namespace'], f'--replicas={workload["replicas"]}')
        kubectl('rollout', 'status', target, '-n', workload['namespace'], '--timeout=600s')
    print('resumed; verify login -> learning submit -> report before reopening.')


# ---------------------------------------------------------------- RDS bootstrap

def bootstrap_manifest(spec, master_secret_name, image):
    files = {name: (BOOTSTRAP_SQL / name).read_text(encoding='utf-8') for name in ('rds-bootstrap.sql', 'rds-bootstrap-db.sql')}
    env = [{'name': 'PGHOST', 'value': '__RDS_ENDPOINT__'}, {'name': 'PGPORT', 'value': '5432'},
           {'name': 'PGDATABASE', 'value': 'postgres'}, {'name': 'PGSSLMODE', 'value': 'verify-full'},
           {'name': 'PGSSLROOTCERT', 'value': '/rds-ca/global-bundle.pem'},
           {'name': 'PGUSER', 'valueFrom': {'secretKeyRef': {'name': master_secret_name, 'key': 'username'}}},
           {'name': 'PGPASSWORD', 'valueFrom': {'secretKeyRef': {'name': master_secret_name, 'key': 'password'}}}]
    for service in ('core', 'learning', 'report'):
        for role, secret in (('APP', f'{service}-db-credentials'), ('MIGRATE', f'{service}-migrate-credentials')):
            for key, field in (('USER', 'DB_USERNAME'), ('PASSWORD', 'DB_PASSWORD')):
                env.append({'name': f'{service.upper()}_{role}_{key}',
                            'valueFrom': {'secretKeyRef': {'name': secret, 'key': field}}})
    labels = {'app.kubernetes.io/name': 'rds-bootstrap', 'app.kubernetes.io/part-of': 'sagomungchi'}
    config_map = {'apiVersion': 'v1', 'kind': 'ConfigMap',
                  'metadata': {'name': 'rds-bootstrap-sql', 'namespace': 'app', 'labels': labels}, 'data': files}
    job = {'apiVersion': 'batch/v1', 'kind': 'Job',
           'metadata': {'name': 'rds-bootstrap', 'namespace': 'app', 'labels': labels},
           'spec': {'backoffLimit': 0, 'activeDeadlineSeconds': 300, 'template': {
               'metadata': {'labels': labels},
               'spec': {'restartPolicy': 'Never', 'automountServiceAccountToken': False,
                        'securityContext': {'runAsNonRoot': True, 'runAsUser': 999, 'seccompProfile': {'type': 'RuntimeDefault'}},
                        'containers': [{'name': 'psql', 'image': image,
                                        'command': ['psql', '-X', '-v', 'ON_ERROR_STOP=1', '-f', '/sql/rds-bootstrap.sql'],
                                        'workingDir': '/sql', 'env': env,
                                        'securityContext': {'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True,
                                                            'capabilities': {'drop': ['ALL']}},
                                        'resources': {'requests': {'cpu': '50m', 'memory': '64Mi'}, 'limits': {'memory': '128Mi'}},
                                        'volumeMounts': [{'name': 'sql', 'mountPath': '/sql', 'readOnly': True},
                                                         {'name': 'rds-ca', 'mountPath': '/rds-ca', 'readOnly': True}]}],
                        'volumes': [{'name': 'sql', 'configMap': {'name': 'rds-bootstrap-sql'}},
                                    {'name': 'rds-ca', 'configMap': {'name': 'rds-ca'}}]}}}}
    return config_map, job


def rds_bootstrap(aws, kubectl, spec, execute, image):
    db = aws('rds', 'describe-db-instances', '--db-instance-identifier', spec['rds']['id'])['DBInstances'][0]
    master_arn = db['MasterUserSecret']['SecretArn']
    missing = [s for s in ('core', 'learning', 'report') for kind in ('db', 'migrate')
               if not kubectl('get', 'secret', '-n', 'app', f'{s}-{kind}-credentials', '--ignore-not-found', '-o', 'name').strip()]
    if not kubectl('get', 'configmap', 'rds-ca', '-n', 'app', '--ignore-not-found', '-o', 'name').strip():
        missing.append('configmap/rds-ca')
    print(f'RDS {spec["rds"]["id"]} status={db["DBInstanceStatus"]}; master secret is RDS-managed')
    print('missing inputs:', missing or 'none')
    config_map, job = bootstrap_manifest(spec, 'rds-bootstrap-master', image)
    print('steps: temporary Secret rds-bootstrap-master -> ConfigMap rds-bootstrap-sql -> Job rds-bootstrap '
          '-> delete Secret/Job/ConfigMap')
    if not execute:
        print('dry run: nothing changed (add --execute to run)')
        return
    if missing:
        raise RuntimeError(f'Prepare inputs first: {missing}')
    master = json.loads(aws('secretsmanager', 'get-secret-value', '--secret-id', master_arn)['SecretString'])
    secret = {'apiVersion': 'v1', 'kind': 'Secret', 'type': 'Opaque',
              'metadata': {'name': 'rds-bootstrap-master', 'namespace': 'app'},
              'stringData': {'username': master['username'], 'password': master['password']}}
    endpoint = db['Endpoint']['Address']
    job['spec']['template']['spec']['containers'][0]['env'][0]['value'] = endpoint
    try:
        kubectl('apply', '-f', '-', stdin=json.dumps(secret))
        del master, secret
        kubectl('apply', '-f', '-', stdin=json.dumps({'apiVersion': 'v1', 'kind': 'List', 'items': [config_map, job]}))
        kubectl('wait', '--for=condition=complete', 'job/rds-bootstrap', '-n', 'app', '--timeout=300s')
        print(kubectl('logs', 'job/rds-bootstrap', '-n', 'app'))
    finally:
        kubectl('delete', 'secret', 'rds-bootstrap-master', '-n', 'app', '--ignore-not-found')
        kubectl('delete', 'job', 'rds-bootstrap', '-n', 'app', '--ignore-not-found', '--wait=false')
        kubectl('delete', 'configmap', 'rds-bootstrap-sql', '-n', 'app', '--ignore-not-found')


# ---------------------------------------------------------------- CLI

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', default=None)
    parser.add_argument('--aws', default='aws', help='aws CLI executable')
    parser.add_argument('--spec', default=str(SPEC))
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('plan', help='read-only drift report')
    apply_cmd = sub.add_parser('apply', help='create missing resources only')
    apply_cmd.add_argument('--confirm-account', required=True)
    apply_cmd.add_argument('--after-eksctl', action='store_true', help='add RDS ingress from the EKS cluster SG')
    render = sub.add_parser('render-eksctl', help='write eksctl config with current subnet IDs')
    render.add_argument('--operator-cidr', action='append', required=True)
    render.add_argument('--out', required=True, type=Path)
    for name in ('pause', 'resume', 'rds-bootstrap'):
        command = sub.add_parser(name)
        command.add_argument('--kubeconfig', required=True)
        command.add_argument('--kubectl', default='kubectl')
        command.add_argument('--execute', action='store_true')
        command.add_argument('--confirm-account')
        if name != 'rds-bootstrap':
            command.add_argument('--state', required=True, type=Path, help='state file outside the repository')
        if name == 'pause':
            command.add_argument('--allow-pending-messages', action='store_true')
        if name == 'rds-bootstrap':
            command.add_argument('--image', default='public.ecr.aws/docker/library/postgres:17.6')
    args = parser.parse_args(argv)
    spec = load_spec(args.spec)
    aws = Aws(args.profile, spec['region'], args.aws)
    account = aws('sts', 'get-caller-identity')['Account']
    if account != spec['account']:
        parser.error(f'Profile account {account} is not {spec["account"]}')
    confirm = getattr(args, 'confirm_account', None)
    if (args.command == 'apply' or getattr(args, 'execute', False)) and confirm != spec['account']:
        parser.error(f'Changes need --confirm-account {spec["account"]}')
    for attr in ('state', 'out'):
        path = getattr(args, attr, None)
        if path and path.resolve().is_relative_to(HERE.parents[1]):
            parser.error(f'--{attr} must be outside the repository')
    if args.command == 'plan':
        report = plan(aws, spec)
        report.print()
        return 0 if report.ok else 1
    if args.command == 'apply':
        for kind, name in apply_missing(aws, spec) + create_missing_nodegroups(aws, spec):
            print('created', kind, name)
        if args.after_eksctl and allow_rds_from_cluster(aws, spec, discover(aws, spec)):
            print('created rds ingress from EKS cluster security group')
        return 0
    if args.command == 'render-eksctl':
        args.out.write_text(json.dumps(render_eksctl(aws, spec, args.operator_cidr), indent=2), encoding='utf-8')
        print(f'wrote {args.out}; run: eksctl create cluster -f {args.out} --dry-run')
        return 0
    kubectl = Kubectl(args.kubeconfig, args.kubectl)
    if args.command == 'pause':
        pause(aws, kubectl, spec, args.state, args.execute, args.allow_pending_messages)
    elif args.command == 'resume':
        resume(aws, kubectl, spec, args.state, args.execute)
    else:
        rds_bootstrap(aws, kubectl, spec, args.execute, args.image)
    return 0


if __name__ == '__main__':
    sys.exit(main())
