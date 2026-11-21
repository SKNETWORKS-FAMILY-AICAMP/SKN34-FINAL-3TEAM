"""#809 A 계정 번호를 B 계정 번호로 한 번에 바꾸고, 남은 A 번호가 기록용뿐인지 확인한다.

    python scripts/aws_account_switch.py plan --to <B 계정>     # 바꿀 곳·남길 곳만 출력(파일 변경 없음)
    python scripts/aws_account_switch.py apply --to <B 계정>    # 바꿀 목록의 파일만 고친다
    python scripts/aws_account_switch.py check                  # 남은 A 번호가 모두 기록용인지

분류는 아래 RECORD·CHANGE가 기준이다. 어느 쪽에도 없는 파일에 A 번호가 있으면 plan·apply·check 모두
멈추고 그 파일을 알려 준다(새로 생긴 파일을 먼저 분류). 바꿀 파일 안에서도 'A 계정 <번호>'·
'A 계정(<번호>)'처럼 A 계정임을 밝힌 줄은 기록으로 남긴다. AWS·네트워크에 접속하지 않는다.
"""

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
A_ACCOUNT = '347161580747'

# A 값 그대로 두는 기록·근거(관측 결과, 과거 실측, A에서 한 번 실행한 SQL)
RECORD = [
    'docs/report/**',
    'infrastructure/aws/demo-observed.json',
    'infrastructure/eks/demo-observed.json',
    'infrastructure/aws/add-demo-premium-product.sql',
    'infrastructure/aws/add-demo-test-subscription.sql',
    'infrastructure/aws/mark-confirmed-demo-data.sql',
    'evaluation/load/llm-stub.k8s.yaml',
    'scripts/aws_account_switch.py',
    'scripts/tests/test_aws_account_switch.py',
]
# B에서 실행·배포할 값과 그 절차. RECORD보다 먼저 본다(docs/report/scoring.md 6.2·6.3 업로드 절차)
CHANGE = [
    'docs/report/scoring.md',
    'infrastructure/aws/demo-stack.json',
    'infrastructure/aws/iam/*.json',
    'infrastructure/aws/cloudfront-config.redacted.json',
    'infrastructure/aws/README.md',
    'infrastructure/eks/cluster.json',
    'infrastructure/eks/README.md',
    'infrastructure/cd/README.md',
    'infrastructure/gitops/environments/prod/*.json',
    'infrastructure/gitops/environments/prod/images/*.json',
    'infrastructure/gitops/environments/prod/redeploy-app.ps1',
    'infrastructure/gitops/environments/prod/README.md',
    'scripts/tests/test_cd_migration_runner.py',
]


def matches(path, patterns):
    # fnmatch의 *는 /도 넘으므로 '**'가 아닌 패턴은 같은 깊이만 본다
    for pattern in patterns:
        if pattern.endswith('/**'):
            if path.startswith(pattern[:-2]):
                return True
        elif path.count('/') == pattern.count('/') and fnmatch.fnmatchcase(path, pattern):
            return True
    return False


def classify(path):
    if matches(path, CHANGE):
        return 'change'
    if matches(path, RECORD):
        return 'record'
    return 'unknown'


def kept_line(line, account):
    return re.search(r'A 계정\s*\(?\s*' + account, line) is not None


def tracked_files(root):
    out = subprocess.run(['git', '-C', str(root), 'ls-files', '-z'], check=True, capture_output=True).stdout
    return sorted(p for p in out.decode('utf-8').split('\0') if p)


def scan(root, account):
    """{path: (분류, [(줄 번호, 남길 줄인지)])}. 바이너리·UTF-8이 아닌 파일은 건너뛴다."""
    found = {}
    for path in tracked_files(root):
        try:
            text = (root / path).read_bytes().decode('utf-8')
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        if account not in text:
            continue
        lines = [(n, kept_line(line, account)) for n, line in enumerate(text.splitlines(), 1) if account in line]
        found[path] = (classify(path), lines)
    return found


def rewrite(text, old, new):
    return ''.join(line if kept_line(line, old) else line.replace(old, new) for line in text.splitlines(keepends=True))


def report(found):
    unknown = [p for p, (kind, _) in found.items() if kind == 'unknown']
    for path, (kind, lines) in found.items():
        change = sum(1 for _, keep in lines if not keep) if kind == 'change' else 0
        print(f'{kind:7} {path}: 바꿈 {change}, 남김 {len(lines) - change}')
    if unknown:
        print('분류 안 된 파일(RECORD·CHANGE에 먼저 넣는다):', *unknown, sep='\n  ', file=sys.stderr)
    return unknown


def main(argv=None, root=ROOT):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('command', choices=['plan', 'apply', 'check'])
    p.add_argument('--to', help='B 계정 번호(12자리)')
    p.add_argument('--from', dest='old', default=A_ACCOUNT)
    args = p.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    if args.command != 'check':
        if not args.to or not re.fullmatch(r'\d{12}', args.to) or args.to == args.old:
            p.error('--to는 A와 다른 12자리 계정 번호')
    found = scan(root, args.old)
    if report(found):
        return 1
    if args.command == 'check':
        left = [(p, n) for p, (kind, lines) in found.items() for n, keep in lines if kind == 'change' and not keep]
        for path, n in left:
            print(f'남은 실행 값: {path}:{n}', file=sys.stderr)
        return 1 if left else 0
    if args.command == 'apply':
        for path, (kind, _) in found.items():
            if kind != 'change':
                continue
            data = (root / path).read_bytes().decode('utf-8')
            (root / path).write_bytes(rewrite(data, args.old, args.to).encode('utf-8'))
        print('적용함. 이어서 check, scripts/tests, git diff를 본다')
    return 0


if __name__ == '__main__':
    sys.exit(main())
