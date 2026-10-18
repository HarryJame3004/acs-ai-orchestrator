#!/usr/bin/env bash
# Development dependencies only; never starts workers or an operational daemon.
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
python3 -c 'import sys; assert sys.version_info >= (3, 12), "Python 3.12+ required by agpair"'
python3 -m venv .venv
.venv/bin/python -m pip install --disable-pip-version-check --no-cache-dir --upgrade pip==26.2
.venv/bin/python -m pip install --no-cache-dir -c requirements/cloud-dev.txt -r requirements/local-build.txt
.venv/bin/python -m pip install --no-cache-dir -r requirements/cloud-dev.txt
.venv/bin/python -m pip install --no-cache-dir --no-build-isolation --no-deps -e . -e ./agpair
.venv/bin/python -m pip check
