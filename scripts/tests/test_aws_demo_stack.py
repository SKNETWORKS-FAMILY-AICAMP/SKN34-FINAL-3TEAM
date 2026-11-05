"""#185 AWS demo stack script: plan/apply against an in-memory AWS, never the real account."""
import importlib.util
import itertools
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('demo_stack', ROOT / 'infrastructure/aws/demo_stack.py')
demo_stack = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(demo_stack)


def args_of(argv):
    """aws CLI style `--key value` pairs; repeated values are kept as a list."""
    parsed, key = {}, None
    for item in argv:
        if item.startswith('--'):
            key = item[2:]
            parsed[key] = []
        elif key:
            parsed[key].append(item)
    return {k: (v[0] if len(v) == 1 else v) for k, v in parsed.items()}


class FakeAws:
    """Just enough EC2/S3/IAM/RDS/EKS state for demo_stack.apply_missing and plan."""

    def __init__(self, spec):
        self.spec, self.calls, self.ids = spec, [], itertools.count(1)
        self.vpcs, self.subnets, self.tables, self.igws, self.nats, self.endpoints, self.groups = ([] for _ in range(7))
        self.buckets, self.roles, self.policies, self.subnet_groups, self.dbs = {}, {}, {}, {}, {}
        self.repositories, self.nodegroups = {}, {}
        self.cluster = None

    def new(self, prefix):
        return f'{prefix}-{next(self.ids):08x}'

    @staticmethod
    def tags(args):
        spec = json.loads(args.get('tag-specifications', '[{"Tags": []}]'))
        return spec[0]['Tags']

    @staticmethod
    def named(items, filters):
        filters = filters if isinstance(filters, list) else [filters]
        result = items
        for f in filters:
            name, values = f.split(',', 1)
            name, value = name[5:], values[7:]
            if name == 'tag:Name':
                result = [i for i in result if demo_stack.tag_name(i) == value]
            elif name == 'vpc-id':
                result = [i for i in result if i.get('VpcId') == value]
            elif name == 'attachment.vpc-id':
                result = [i for i in result if any(a['VpcId'] == value for a in i['Attachments'])]
            elif name == 'group-name':
                result = [i for i in result if i['GroupName'] == value]
            elif name == 'state':
                result = [i for i in result if i['State'] in value.split(',')]
            elif name == 'service-name':
                result = [i for i in result if i['ServiceName'] == value]
        return result

    def __call__(self, service, operation, *argv, region=None, check=True):
        self.calls.append((service, operation))
        a = args_of(argv)
        handler = getattr(self, f'{service}_{operation}'.replace('-', '_'), None)
        if handler is None:
            return {}
        result = handler(a)
        if result is None and check:
            raise RuntimeError(f'{service} {operation} not found')
        return result

    # EC2
    def ec2_describe_vpcs(self, a):
        if 'vpc-ids' in a:
            return {'Vpcs': [v for v in self.vpcs if v['VpcId'] == a['vpc-ids']]}
        return {'Vpcs': self.named(self.vpcs, a['filters'])}

    def ec2_create_vpc(self, a):
        vpc = {'VpcId': self.new('vpc'), 'CidrBlock': a['cidr-block'], 'Tags': self.tags(a)}
        self.vpcs.append(vpc)
        return {'Vpc': vpc}

    def ec2_describe_subnets(self, a):
        return {'Subnets': self.named(self.subnets, a['filters'])}

    def ec2_create_subnet(self, a):
        self.subnets.append({'SubnetId': self.new('subnet'), 'VpcId': a['vpc-id'], 'CidrBlock': a['cidr-block'],
                             'AvailabilityZone': a['availability-zone'], 'Tags': self.tags(a)})
        return {}

    def ec2_create_tags(self, a):
        key, value = a['tags'][4:].split(',Value=')
        for subnet in self.subnets:
            if subnet['SubnetId'] == a['resources']:
                subnet['Tags'].append({'Key': key, 'Value': value})
        return {}

    def ec2_describe_route_tables(self, a):
        return {'RouteTables': self.named(self.tables, a['filters'])}

    def ec2_create_route_table(self, a):
        table = {'RouteTableId': self.new('rtb'), 'VpcId': a['vpc-id'], 'Tags': self.tags(a), 'Routes': [],
                 'Associations': []}
        self.tables.append(table)
        return {'RouteTable': table}

    def ec2_create_route(self, a):
        table = next(t for t in self.tables if t['RouteTableId'] == a['route-table-id'])
        table['Routes'].append({'DestinationCidrBlock': a['destination-cidr-block'],
                                'GatewayId': a.get('gateway-id'), 'NatGatewayId': a.get('nat-gateway-id')})
        return {}

    def ec2_associate_route_table(self, a):
        table = next(t for t in self.tables if t['RouteTableId'] == a['route-table-id'])
        table['Associations'].append({'SubnetId': a['subnet-id']})
        return {}

    def ec2_describe_internet_gateways(self, a):
        return {'InternetGateways': self.named(self.igws, a['filters'])}

    def ec2_create_internet_gateway(self, a):
        igw = {'InternetGatewayId': self.new('igw'), 'Attachments': [], 'Tags': self.tags(a)}
        self.igws.append(igw)
        return {'InternetGateway': igw}

    def ec2_attach_internet_gateway(self, a):
        next(i for i in self.igws if i['InternetGatewayId'] == a['internet-gateway-id'])['Attachments'].append(
            {'VpcId': a['vpc-id']})
        return {}

    def ec2_allocate_address(self, a):
        return {'AllocationId': self.new('eipalloc')}

    def ec2_create_nat_gateway(self, a):
        vpc = next(s['VpcId'] for s in self.subnets if s['SubnetId'] == a['subnet-id'])
        self.nats.append({'NatGatewayId': self.new('nat'), 'SubnetId': a['subnet-id'], 'VpcId': vpc,
                          'State': 'available', 'Tags': self.tags(a)})
        return {}

    def ec2_describe_nat_gateways(self, a):
        return {'NatGateways': self.named(self.nats, a['filter'])}

    def ec2_describe_vpc_endpoints(self, a):
        return {'VpcEndpoints': self.named(self.endpoints, a['filters'])}

    def ec2_create_vpc_endpoint(self, a):
        tables = a['route-table-ids']
        self.endpoints.append({'VpcEndpointId': self.new('vpce'), 'VpcId': a['vpc-id'], 'ServiceName': a['service-name'],
                               'RouteTableIds': tables if isinstance(tables, list) else [tables]})
        return {}

    def ec2_describe_security_groups(self, a):
        return {'SecurityGroups': self.named(self.groups, a['filters'])}

    def ec2_create_security_group(self, a):
        self.groups.append({'GroupId': self.new('sg'), 'GroupName': a['group-name'], 'VpcId': a['vpc-id'],
                            'IpPermissions': []})
        return {}

    # S3
    def s3api_head_bucket(self, a):
        return {} if a['bucket'] in self.buckets else None

    def s3api_create_bucket(self, a):
        self.buckets[a['bucket']] = {}
        return {}

    def s3api_put_bucket_versioning(self, a):
        self.buckets[a['bucket']]['versioning'] = 'Enabled'
        return {}

    def s3api_put_public_access_block(self, a):
        self.buckets[a['bucket']]['block'] = True
        return {}

    def s3api_put_bucket_encryption(self, a):
        self.buckets[a['bucket']]['encryption'] = True
        return {}

    def s3api_get_bucket_versioning(self, a):
        return {'Status': self.buckets[a['bucket']].get('versioning')}

    def s3api_get_public_access_block(self, a):
        on = self.buckets[a['bucket']].get('block', False)
        return {'PublicAccessBlockConfiguration': dict.fromkeys(
            ('BlockPublicAcls', 'IgnorePublicAcls', 'BlockPublicPolicy', 'RestrictPublicBuckets'), on)}

    def s3api_get_bucket_encryption(self, a):
        return {} if self.buckets[a['bucket']].get('encryption') else None

    # IAM
    def iam_get_role(self, a):
        role = self.roles.get(a['role-name'])
        return role and {'Role': {'AssumeRolePolicyDocument': role['trust']}}

    def iam_create_role(self, a):
        self.roles[a['role-name']] = {'trust': json.loads(a['assume-role-policy-document']), 'attached': [], 'inline': {}}
        return {}

    def iam_attach_role_policy(self, a):
        self.roles[a['role-name']]['attached'].append(a['policy-arn'])
        return {}

    def iam_put_role_policy(self, a):
        self.roles[a['role-name']]['inline'][a['policy-name']] = json.loads(a['policy-document'])
        return {}

    def iam_get_policy(self, a):
        return {'Policy': {'DefaultVersionId': 'v1'}} if a['policy-arn'] in self.policies else None

    def iam_create_policy(self, a):
        self.policies[f'arn:aws:iam::{self.spec["account"]}:policy/{a["policy-name"]}'] = json.loads(a['policy-document'])
        return {}

    def iam_get_policy_version(self, a):
        return {'PolicyVersion': {'Document': self.policies[a['policy-arn']]}}

    def iam_list_attached_role_policies(self, a):
        return {'AttachedPolicies': [{'PolicyArn': p} for p in self.roles[a['role-name']]['attached']]}

    def iam_list_role_policies(self, a):
        return {'PolicyNames': list(self.roles[a['role-name']]['inline'])}

    def iam_get_role_policy(self, a):
        return {'PolicyDocument': self.roles[a['role-name']]['inline'][a['policy-name']]}

    # RDS
    def rds_describe_db_subnet_groups(self, a):
        group = self.subnet_groups.get(a['db-subnet-group-name'])
        return group and {'DBSubnetGroups': [{'Subnets': [{'SubnetIdentifier': s} for s in group]}]}

    def rds_create_db_subnet_group(self, a):
        self.subnet_groups[a['db-subnet-group-name']] = a['subnet-ids']
        return {}

    def rds_describe_db_instances(self, a):
        db = self.dbs.get(a['db-instance-identifier'])
        return db and {'DBInstances': [db]}

    def rds_create_db_instance(self, a):
        self.dbs[a['db-instance-identifier']] = {
            'DBInstanceClass': a['db-instance-class'], 'EngineVersion': a['engine-version'],
            'MultiAZ': 'multi-az' in a, 'StorageType': a['storage-type'],
            'MaxAllocatedStorage': int(a['max-allocated-storage']), 'AllocatedStorage': int(a['allocated-storage']),
            'BackupRetentionPeriod': int(a['backup-retention-period']), 'PubliclyAccessible': False,
            'StorageEncrypted': 'storage-encrypted' in a, 'MasterUserSecret': {'SecretArn': 'arn'},
            'DBSubnetGroup': {'DBSubnetGroupName': a['db-subnet-group-name']},
            'VpcSecurityGroups': [{'VpcSecurityGroupId': a['vpc-security-group-ids']}], 'DBInstanceStatus': 'creating'}
        return {}

    # ECR / Secrets Manager
    def ecr_describe_repositories(self, a):
        mutability = self.repositories.get(a['repository-names'])
        return mutability and {'repositories': [{'imageTagMutability': mutability}]}

    def ecr_create_repository(self, a):
        self.repositories[a['repository-name']] = a['image-tag-mutability']
        return {}

    def secretsmanager_describe_secret(self, a):
        return None

    def eks_describe_cluster(self, a):
        return self.cluster

    def eks_describe_nodegroup(self, a):
        group = self.nodegroups.get(a['nodegroup-name'])
        return group and {'nodegroup': group}

    def eks_create_nodegroup(self, a):
        self.nodegroups[a['nodegroup-name']] = a
        return {}


MUTATING = ('create', 'put', 'attach', 'associate', 'allocate', 'modify', 'authorize', 'update', 'delete', 'stop', 'start')


class DemoStackTest(unittest.TestCase):
    def setUp(self):
        self.spec = demo_stack.load_spec()

    def test_empty_account_plan_reports_missing_and_apply_creates_everything_except_eks(self):
        aws = FakeAws(self.spec)
        report = demo_stack.plan(aws, self.spec)
        self.assertFalse(report.ok)
        self.assertIn(('vpc', 'sagomungchi-demo-vpc', 'MISSING', ''), report.rows)

        created = demo_stack.apply_missing(aws, self.spec, wait=lambda _: None)
        kinds = [kind for kind, _ in created]
        self.assertEqual(kinds.count('subnet'), 4)
        self.assertEqual(kinds.count('s3'), 4)
        self.assertEqual(kinds.count('iam-role'), 10)
        self.assertEqual(kinds.count('ecr'), 7)
        self.assertIn(('rds', 'sagomungchi-demo-db'), created)

        report = demo_stack.plan(aws, self.spec)
        missing = {(kind, status) for kind, _, status, _ in report.rows if status != 'OK'}
        # The cluster belongs to eksctl; secret values are entered by their owners.
        self.assertEqual(missing, {('eks', 'MISSING'), ('secret', 'MISSING')}, report.rows)

    def test_apply_on_complete_account_changes_nothing(self):
        aws = FakeAws(self.spec)
        demo_stack.apply_missing(aws, self.spec, wait=lambda _: None)
        aws.calls.clear()
        self.assertEqual(demo_stack.apply_missing(aws, self.spec, wait=lambda _: None), [])
        changed = [c for c in aws.calls if c[1].split('-')[0] in MUTATING]
        self.assertEqual(changed, [])

    def test_private_subnets_route_through_nat_and_s3_endpoint(self):
        aws = FakeAws(self.spec)
        demo_stack.apply_missing(aws, self.spec, wait=lambda _: None)
        ids = demo_stack.discover(aws, self.spec)
        nat = ids['nat']['NatGatewayId']
        for subnet in self.spec['vpc']['subnets']:
            table = ids['routeTables'][subnet['routeTable']]
            default = next(r for r in table['Routes'] if r['DestinationCidrBlock'] == '0.0.0.0/0')
            if subnet['tier'] == 'private':
                self.assertEqual(default['NatGatewayId'], nat)
                self.assertIn(table['RouteTableId'], ids['s3Endpoint']['RouteTableIds'])
            else:
                self.assertEqual(default['GatewayId'], ids['igw'])
        self.assertEqual(ids['nat']['SubnetId'], ids['subnets'][self.spec['vpc']['natGateway']['subnet']]['SubnetId'])

    def test_existing_cluster_gets_only_the_missing_platform_node_group(self):
        aws = FakeAws(self.spec)
        demo_stack.apply_missing(aws, self.spec, wait=lambda _: None)
        self.assertEqual(demo_stack.create_missing_nodegroups(aws, self.spec), [])  # no cluster yet
        aws.cluster = {'cluster': {'name': self.spec['eks']['cluster']}}
        aws.nodegroups['application'] = {'name': 'application'}
        self.assertEqual(demo_stack.create_missing_nodegroups(aws, self.spec), [('nodegroup', 'platform-observability')])
        created = aws.nodegroups['platform-observability']
        ids = demo_stack.discover(aws, self.spec)
        private = sorted(s['SubnetId'] for n, s in ids['subnets'].items() if 'private' in n)
        self.assertEqual(sorted(created['subnets']), private)
        self.assertEqual(created['capacity-type'], 'ON_DEMAND')
        self.assertEqual(created['labels'], 'workload=platform')
        self.assertEqual(json.loads(created['taints']), [{'key': 'workload', 'value': 'platform', 'effect': 'NO_SCHEDULE'}])
        self.assertEqual(created['scaling-config'], 'minSize=2,maxSize=2,desiredSize=2')
        self.assertEqual(demo_stack.create_missing_nodegroups(aws, self.spec), [])

    def test_platform_charts_and_node_group_agree_on_label_and_taint(self):
        config = json.loads((demo_stack.HERE / self.spec['eks']['config']).read_text(encoding='utf-8'))
        group = next(g for g in config['managedNodeGroups'] if g['name'] == 'platform-observability')
        self.assertNotIn('spot', json.dumps(group).lower())
        for name in ('platform-data', 'observability'):
            values = json.loads((ROOT / f'infrastructure/gitops/environments/prod/{name}.json').read_text(encoding='utf-8'))
            self.assertEqual(values['scheduling']['nodeSelector'], group['labels'])
            taint = group['taints'][0]
            self.assertIn({'key': taint['key'], 'operator': 'Equal', 'value': taint['value'], 'effect': taint['effect']},
                          values['scheduling']['tolerations'])
        self.assertEqual(self.spec['eks']['nodegroups'], [g['name'] for g in config['managedNodeGroups']])

    def test_iam_documents_compare_without_order_or_string_list_difference(self):
        a = {'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow', 'Action': 's3:GetObject', 'Resource': ['b', 'a']}]}
        b = {'Statement': [{'Resource': ['a', 'b'], 'Action': ['s3:GetObject'], 'Effect': 'Allow'}], 'Version': '2012-10-17'}
        self.assertTrue(demo_stack.same_policy(a, b))
        b['Statement'][0]['Action'].append('s3:PutObject')
        self.assertFalse(demo_stack.same_policy(a, b))

    def test_spec_files_exist_and_pod_identity_roles_are_declared(self):
        for role in self.spec['iamRoles']:
            for path in [role['trust'], *role.get('inline', {}).values(), *role.get('customerManaged', {}).values()]:
                self.assertTrue((demo_stack.HERE / path).is_file(), path)
        config = json.loads((demo_stack.HERE / self.spec['eks']['config']).read_text(encoding='utf-8'))
        declared = {r['name'] for r in self.spec['iamRoles']}
        used = [a['roleARN'] for a in config['iam']['podIdentityAssociations']]
        used += [p['roleARN'] for addon in config['addons'] for p in addon.get('podIdentityAssociations', [])]
        used += [config['iam']['serviceRoleARN'], config['managedNodeGroups'][0]['iam']['instanceRoleARN']]
        # GitHub Actions 게시 역할(#186)은 EKS가 아니라 cd-release workflow가 쓴다
        self.assertEqual({arn.rsplit('/', 1)[1] for arn in used}, declared - {'sagomungchi-demo-github-cd-publish'})
        self.assertTrue(all(c.startswith('__') for c in config['vpc']['publicAccessCIDRs']))

    def test_bootstrap_job_reads_credentials_from_secrets_only(self):
        config_map, job = demo_stack.bootstrap_manifest(self.spec, 'rds-bootstrap-master', 'postgres:17')
        env = job['spec']['template']['spec']['containers'][0]['env']
        literal = {e['name'] for e in env if 'value' in e}
        self.assertEqual(literal, {'PGHOST', 'PGPORT', 'PGDATABASE', 'PGSSLMODE', 'PGSSLROOTCERT'})
        self.assertEqual(len([e for e in env if 'valueFrom' in e]), 14)
        self.assertEqual(set(config_map['data']), {'rds-bootstrap.sql', 'rds-bootstrap-db.sql'})
        self.assertIn('\\ir rds-bootstrap-db.sql', config_map['data']['rds-bootstrap.sql'])


if __name__ == '__main__':
    unittest.main()
