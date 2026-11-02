"""Report whether named variables are resolved, never their contents."""
import argparse
import json
import os

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('names', nargs='+')
args = parser.parse_args()
results = []
for name in args.names:
    value = os.environ.get(name, '')
    resolved = bool(value.strip()) and 'op://' not in value and not value.startswith('${')
    results.append({'name': name, 'resolved': resolved})
print(json.dumps({'variables': results}, ensure_ascii=False))
raise SystemExit(0 if all(r['resolved'] for r in results) else 1)
