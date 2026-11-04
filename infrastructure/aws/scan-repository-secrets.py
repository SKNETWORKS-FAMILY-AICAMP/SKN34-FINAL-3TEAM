"""Scan available Git history and current non-ignored files; never print secrets."""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gitleaks', required=True, help='Gitleaks 8.30.1 executable')
    parser.add_argument('--reports', required=True, type=Path, help='Directory outside the repository')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    reports = args.reports.resolve()
    if reports.is_relative_to(root):
        parser.error('Reports must be outside the repository')
    reports.mkdir(parents=True, exist_ok=True)
    scanner = str(Path(args.gitleaks).resolve())
    version = subprocess.check_output([scanner, 'version'], text=True).strip()
    if version != '8.30.1':
        parser.error(f'Expected Gitleaks 8.30.1, got {version}')
    common = ['--config', str(root / '.gitleaks.toml'), '--redact=100', '--report-format', 'json', '--no-banner']
    history = subprocess.run([scanner, 'git', str(root), '--log-opts=--all',
                              '--report-path', str(reports / 'history.json'), *common], cwd=root)
    # Git history excludes uncommitted content; scan a separate snapshot too.
    files = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=root)
    with tempfile.TemporaryDirectory(prefix='issue185-secret-scan-') as directory:
        snapshot = Path(directory)
        count = 0
        for name in set(files.decode('utf-8').split('\0')):
            if not name:
                continue
            source = root / name
            if source.is_symlink():
                raise RuntimeError(f'Review symlink before scanning: {name}')
            if not source.is_file():
                continue  # Deleted working-tree files remain covered by history.
            target = snapshot / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            count += 1
        current = subprocess.run([scanner, 'dir', str(snapshot), '--report-path',
                                  str(reports / 'worktree.json'), *common], cwd=root)
        print(f'Current files: {count}; history exit: {history.returncode}; worktree exit: {current.returncode}')
    return 0 if history.returncode == current.returncode == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
