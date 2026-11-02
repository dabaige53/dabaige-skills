"""Locate credential candidates; output metadata only, not source lines or values."""
import argparse
import json
import os
from pathlib import Path
import re
import stat

EXCLUDE = {'.git', '.codex', '.agents', '.venv', 'venv', 'node_modules',
           'site-packages', '__pycache__', '.cache', '.next', 'dist', 'build',
           'vendor', 'logs', 'archive', 'backups'}
SUFFIXES = {'.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
            '.py', '.js', '.ts', '.tsx', '.sh', '.bash', '.zsh', '.md',
            '.pem', '.key', '.properties', '.env'}
SENSITIVE = re.compile(r'(?:^|[_\-.])(?:api[_-]?key|secret|pass(?:word|wd)|credential|token|'
                       r'private[_-]?key|database[_-]?url|sub[_-]?url)(?:$|[_\-.])|'
                       r'^(?:apiKey|clientSecret|accessToken|refreshToken|privateKey)$', re.I)
ASSIGNMENTS = [
    re.compile(r'^[ \t]*(?:export[ \t]+)?(?P<key>[A-Za-z_][\w.-]*)\s*[:=]\s*(?P<value>[^\n]*)', re.M),
    re.compile(r'''(?P<quote>["'])(?P<key>[A-Za-z_][\w.-]*)(?P=quote)\s*:\s*(?P<value>[^,\n}]*)'''),
]
ENV_READ = re.compile(r'''(?:getenv\(|environ\.get\(|process\.env\.|secrets\.)(?:["'])?(?P<key>[A-Za-z_]\w*)''')
PEM = re.compile(r'-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----')
TOKEN = re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,})')
URL = re.compile(r'[a-z][a-z0-9+.-]*://[^\s/:]+:[^\s/@]+@', re.I)
PLACEHOLDERS = {'changeme', 'change-me', 'your-api-key', 'your_api_key',
                'placeholder', 'dummy', 'not-needed', 'test', 'none'}


def audit(root):
    findings, skipped, seen = [], [], set()
    checked = 0

    def add(path, text, position, name, kind):
        line = text.count('\n', 0, position) + 1
        key = (str(path), line, name, kind)
        if key not in seen:
            seen.add(key)
            findings.append({'path': str(path), 'line': line, 'name': name, 'kind': kind})

    for current, directories, files in os.walk(root, followlinks=False):
        directories[:] = sorted(d for d in directories if d not in EXCLUDE
                                and not (Path(current) / d).is_symlink())
        for name in sorted(files):
            path = Path(current) / name
            if not (name.startswith('.env') or path.suffix.lower() in SUFFIXES
                    or name in {'id_rsa', 'id_ed25519'}):
                continue
            try:
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode):
                    skipped.append({'path': str(path), 'reason': 'not-regular-file'})
                    continue
                if info.st_size > 512 * 1024:
                    skipped.append({'path': str(path), 'reason': 'over-512-KiB'})
                    continue
                text = path.read_text(encoding='utf-8')
            except (OSError, UnicodeError):
                skipped.append({'path': str(path), 'reason': 'unreadable-text'})
                continue
            checked += 1
            for match in (m for pattern in ASSIGNMENTS for m in pattern.finditer(text)):
                field = match['key']
                if not SENSITIVE.search(field):
                    continue
                value = match['value'].strip().rstrip(',').strip().strip('"\'')
                kind = 'assignment-candidate'
                if 'op://' in value:
                    kind = '1password-reference'
                elif not value or value.lower() in PLACEHOLDERS or value.startswith('<'):
                    kind = 'empty-or-placeholder'
                elif value.startswith(('$', 'os.', 'process.env.', 'getenv(')):
                    kind = 'runtime-reference'
                add(path, text, match.start(), field, kind)
            for match in ENV_READ.finditer(text):
                if SENSITIVE.search(match['key']):
                    add(path, text, match.start(), match['key'], 'runtime-reference')
            for pattern, label, kind in [(PEM, 'PRIVATE_KEY', 'private-key-candidate'),
                                         (TOKEN, 'TOKEN_LITERAL', 'token-literal-candidate'),
                                         (URL, 'CREDENTIAL_URL', 'credential-url-candidate')]:
                for match in pattern.finditer(text):
                    add(path, text, match.start(), label, kind)
    return {'root': str(root), 'files_checked': checked, 'findings': findings,
            'skipped': skipped, 'excluded_directories': sorted(EXCLUDE),
            'limits': ['Candidate metadata only; not proof of active credentials.',
                       'Git history, cloud secrets, excluded paths and large files not checked.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    if not root.is_dir():
        parser.error('root must be an existing directory')
    if root in {Path.home() / '.codex', Path.home() / 'code/CodeX-Settings'}:
        parser.error('Codex configuration is excluded by the current user preference')
    print(json.dumps(audit(root), ensure_ascii=False, indent=2))
