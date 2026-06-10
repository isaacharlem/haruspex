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

# Both engines exit 0 on match, 1 on no-match, 2+ on error. Errors must never
# read as "clean" (a missing binary once silently passed this audit), so scan()
# maps them to the FAIL branch. Test files are excluded from every check.
scan() {
  local status=0
  if command -v rg > /dev/null 2>&1; then
    rg --ignore-case --line-number \
      --glob '!**/*.test.*' --glob '!**/*.spec.*' --glob '!**/tests/**' \
      --glob '!**/__tests__/**' --glob '!**/test/**' "$@" || status=$?
  else
    grep -riEn \
      --exclude='*.test.*' --exclude='*.spec.*' --exclude-dir=tests \
      --exclude-dir=__tests__ --exclude-dir=test "$@" || status=$?
  fi
  if [[ "$status" -ne 0 && "$status" -ne 1 ]]; then
    echo "FAIL: the audit scan errored (exit $status)"
    return 0 # "found" — forces the FAIL branch
  fi
  return "$status"
}

pattern='TODO|FIXME|XXX|NotImplementedError|not implemented|lorem ipsum|placeholder|YOUR_|<your'
if scan "$pattern" backend/src sdk/src frontend/src; then
  echo "FAIL: placeholder markers found in product code (patterns: $pattern)"
  fail=1
fi

if scan '\bprint\(' backend/src sdk/src; then
  echo "FAIL: print( found in Python product code — use structlog (backend) or logging (sdk)"
  fail=1
fi

if scan 'console\.log' frontend/src; then
  echo "FAIL: console.log found in frontend product code"
  fail=1
fi

if [[ "$fail" -ne 0 ]]; then
  exit 1
fi
echo "placeholder audit: clean"
