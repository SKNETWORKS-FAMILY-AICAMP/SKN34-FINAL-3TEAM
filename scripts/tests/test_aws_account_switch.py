"""#809 계정 번호 일괄 교체: 임시 git 저장소에서만 시험한다(실제 저장소 파일은 바꾸지 않음)."""

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import aws_account_switch as switch  # noqa: E402

A = switch.A_ACCOUNT
B = '111122223333'


class AccountSwitchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        subprocess.run(['git', '-C', str(self.root), 'config', 'core.autocrlf', 'false'], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode('utf-8'))
        subprocess.run(['git', '-C', str(self.root), 'add', path], check=True)

    def read(self, path):
        return (self.root / path).read_bytes().decode('utf-8')

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = switch.main(list(argv), root=self.root)
        return code, out.getvalue() + err.getvalue()

    def test_apply_changes_only_change_files_and_keeps_marked_lines(self):
        self.put('infrastructure/aws/iam/x.trust.json', f'{{"arn": "arn:aws:iam::{A}:role/r"}}\r\n')
        self.put('infrastructure/aws/README.md', f'apply --confirm-account {A}\n기존 프로필로 A 계정 {A}을 확인했다\n'
                                                  f'A 계정({A}) 종료\n')
        self.put('docs/report/infra.md', f'계정 {A}\n')
        self.put('infrastructure/aws/demo-observed.json', f'"{A}"\n')
        self.assertEqual(self.run_main('plan', '--to', B)[0], 0)
        self.assertIn(A, self.read('infrastructure/aws/iam/x.trust.json'))  # plan은 바꾸지 않음
        self.assertEqual(self.run_main('check')[0], 1)

        self.assertEqual(self.run_main('apply', '--to', B)[0], 0)
        self.assertEqual(self.read('infrastructure/aws/iam/x.trust.json'), f'{{"arn": "arn:aws:iam::{B}:role/r"}}\r\n')
        self.assertEqual(self.read('infrastructure/aws/README.md'),
                         f'apply --confirm-account {B}\n기존 프로필로 A 계정 {A}을 확인했다\nA 계정({A}) 종료\n')
        self.assertEqual(self.read('docs/report/infra.md'), f'계정 {A}\n')
        self.assertEqual(self.read('infrastructure/aws/demo-observed.json'), f'"{A}"\n')
        self.assertEqual(self.run_main('check')[0], 0)

    def test_unclassified_file_stops_every_command(self):
        self.put('infrastructure/aws/iam/x.json', A)
        self.put('frontend/new.ts', f'const a = "{A}"\n')
        for argv in (('plan', '--to', B), ('apply', '--to', B), ('check',)):
            code, output = self.run_main(*argv)
            self.assertEqual(code, 1, argv)
            self.assertIn('frontend/new.ts', output)
        self.assertEqual(self.read('infrastructure/aws/iam/x.json'), A)

    def test_patterns_do_not_reach_deeper_folders(self):
        self.assertEqual(switch.classify('infrastructure/aws/iam/a.json'), 'change')
        self.assertEqual(switch.classify('infrastructure/aws/iam/old/a.json'), 'unknown')
        self.assertEqual(switch.classify('infrastructure/gitops/environments/prod/migrations/core-service.json'), 'change')
        self.assertEqual(switch.classify('docs/report/evidence/a.json'), 'record')
        self.assertEqual(switch.classify('docs/report/scoring.md'), 'change')

    def test_target_account_must_be_another_twelve_digit_number(self):
        for bad in ('12345', A, 'abcdefghijkl'):
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                switch.main(['plan', '--to', bad], root=self.root)


if __name__ == '__main__':
    unittest.main()
