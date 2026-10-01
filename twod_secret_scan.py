import re
import subprocess
import sys
from pathlib import Path

PATTERNS = [
    (r'\brnd_[A-Za-z0-9]{20,}', 'Render API key'),
    (r'\bgh[pousr]_[A-Za-z0-9]{20,}', 'GitHub token'),
    (r'\bsk-[A-Za-z0-9]{20,}', 'OpenAI-style API key'),
    (r'\bAKIA[0-9A-Z]{16}\b', 'AWS access key id'),
    (r'-----BEGIN [A-Z ]*PRIVATE KEY-----', 'private key block'),
    (r'\bey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b', 'JWT'),
    (r'(?i)\b(?:password|passwd|secret[_-]?key|api[_-]?key|token)\s*[:=]\s*[\'"][^\'"]{8,}[\'"]', 'hardcoded credential'),
]

ALLOW = re.compile(
    r'django-insecure-2d-parser-dev-key-change-me'
    r'|generateValue'
    r'|BettorPass123!'
    r'|OwnerPass123!'
    r'|PlainPass123!'
    r'|ClerkPass123!'
    r'|qa-tmp-pass'
    r'|e\.g\.|example|your[-_]'
    r'|os\.environ|getenv|settings\.',
    re.I,
)


def staged_files():
    out = subprocess.run(
        ['git', 'diff', '--cached', '--name-only', '--diff-filter=ACM'],
        capture_output=True, text=True,
    ).stdout
    return [line for line in out.splitlines() if line.strip()]


def tracked_files():
    out = subprocess.run(
        ['git', 'ls-files'],
        capture_output=True, text=True,
    ).stdout
    return [line for line in out.splitlines() if line.strip()]


def main():
    scan_all = '--all' in sys.argv
    files = tracked_files() if scan_all else staged_files()
    label = 'tracked' if scan_all else 'staged'

    if not files:
        print(f'secret-scan: no {label} files, nothing to check')
        return 0

    findings = []
    for name in files:
        path = Path(name)
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        for pattern, pattern_label in PATTERNS:
            for match in re.finditer(pattern, text):
                snippet = match.group(0)
                if ALLOW.search(snippet):
                    continue
                line_no = text.count('\n', 0, match.start()) + 1
                findings.append((name, line_no, pattern_label, snippet[:24]))

    if findings:
        print(f'secret-scan: BLOCKED - possible secrets in {label} files\n')
        for name, line_no, pattern_label, snippet in findings:
            print(f'  {name}:{line_no}  {pattern_label}  ->  {snippet}...')
        print('\nCommit aborted. If a hit is a false positive, stage the file')
        print('without the value, or rotate the credential if it is real.')
        return 1

    print(f'secret-scan: clean ({len(files)} {label} files)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
