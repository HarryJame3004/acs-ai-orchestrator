#!/usr/bin/env bash
# User-run only. Read-only host discovery unless --execute-probes is passed.
set -euo pipefail
exec acsai verify-local "$@"
