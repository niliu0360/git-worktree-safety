#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python -m py_compile "$ROOT"/scripts/*.py
python "$ROOT/tests/test_scripts.py"
