#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "Python 3.9+ is required" >&2
  exit 2
fi
"$PYTHON" -m py_compile "$ROOT"/scripts/*.py
PYTHONPATH="$ROOT/tests:$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}" \
  "$PYTHON" -m unittest discover -s "$ROOT/tests" -p 'test_*.py' -v
