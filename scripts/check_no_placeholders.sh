#!/usr/bin/env bash
# Mechanical enforcement of Law 1: no placeholders anywhere in product code.
# Scans backend/src, sdk/src, frontend/src. Test code is excluded.
# scripts/placeholder_allowlist.txt exists and must remain empty; any content
# there fails the audit too (the allowlist is a tripwire, not an escape hatch).
set -euo pipefail
cd "$(dirname "$0")/.."

fail=0

allowlist="scripts/placeholder_allowlist.txt"
if [[ ! -f "$allowlist" ]]; then
  echo "FAIL: $allowlist is missing"
  fail=1
elif [[ -s "$allowlist" ]]; then
  echo "FAIL: $allowlist must remain empty, but contains:"
  cat "$allowlist"
  fail=1
fi

# Test files are excluded from every check below.
test_globs=(--glob '!**/*.test.*' --glob '!**/*.spec.*' --glob '!**/tests/**' --glob '!**/__tests__/**' --glob '!**/test/**')

pattern='TODO|FIXME|XXX|NotImplementedError|not implemented|lorem ipsum|placeholder|YOUR_|<your'
if rg --ignore-case --line-number "${test_globs[@]}" "$pattern" backend/src sdk/src frontend/src 2>/dev/null; then
  echo "FAIL: placeholder markers found in product code (patterns: $pattern)"
  fail=1
fi

if rg --line-number "${test_globs[@]}" '\bprint\(' backend/src sdk/src 2>/dev/null; then
  echo "FAIL: print( found in Python product code — use structlog (backend) or logging (sdk)"
  fail=1
fi

if rg --line-number "${test_globs[@]}" 'console\.log' frontend/src 2>/dev/null; then
  echo "FAIL: console.log found in frontend product code"
  fail=1
fi

if [[ "$fail" -ne 0 ]]; then
  exit 1
fi
echo "placeholder audit: clean"
