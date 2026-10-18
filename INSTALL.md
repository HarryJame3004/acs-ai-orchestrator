# Personal Arch Linux installation — candidate remains PARTIAL

ACS Core remains the primary free-first executor. ACS AI is optional intelligence
support; direct AI execution remains an explicit compatibility option. Review
[Core-first contract](docs/upgrade/CORE_FIRST_CONTRACT.md) before enabling it.
Open source defects and incomplete cloud requirements still block release. These
instructions prepare isolated evaluation; they are not approval to deploy a service.

Supported combined installation: Linux x86_64/aarch64, Python 3.12+, SQLite with
FTS5, Git, Python venv/pip. Arch packages normally include `python`, `python-pip`,
`git`, and `bubblewrap`; inspect `pacman -Qi` before any owner-approved installation.
Working bubblewrap namespaces and operator-delegated resource contracts are
required for real execution. Binary discovery does not establish authentication.

## Download, verify and inspect

Use a freshly extracted source bundle and the separately recorded trusted SHA256.
The final release candidate has **not** been issued while the reliability defect
and other source gaps remain. Do not substitute the older PARTIAL bundle as final.

```bash
sha256sum -c ACS-CANDIDATE.zip.sha256
unzip -l ACS-CANDIDATE.zip
mkdir acs-ai-review
unzip ACS-CANDIDATE.zip -d acs-ai-review
cd acs-ai-review
python scripts/personal_install.py --preflight
```

Inspect the scripts, exact manifest commit and local policies before installing.
Preflight only inspects dependencies and in-memory SQLite: it does not authenticate,
start workers, access Core internals or configure services. Expected prerequisites:
`PASS`, with `runtime_ready: false` and provider/sandbox acceptance explicitly pending.
Unsupported Python/architecture, missing Git/FTS5 or Linux prerequisites block install.

## Isolated installation

Choose a NEW private prefix outside ACS Core and outside the extracted source:

```bash
python scripts/personal_install.py --prefix "$HOME/.local/share/acs-ai-evaluation"
```

The script prompts before creating that prefix. It verifies all source hashes,
rejects unlisted files/symlinks and protected/broad destinations, copies verified
source privately, creates a venv, installs constrained dependencies and pinned build
backends, checks imports/pip integrity and CLI help, and writes `config.json`,
`bin/acsai` and `INSTALL_RECEIPT.json`. No system packages, PATH files, services,
providers or paid missions are launched. No credentials are requested or copied.
A failed prefix is retained with a private install log; choose a new prefix after
investigation. Repeating a successful installation for the same manifest runs
`pip check` and reports `ALREADY_INSTALLED` without replacing configuration/state.

Offline installation supports `--wheelhouse /path/to/reviewed-wheels`, including
all runtime and build dependencies. The constraints and backend pins are version
pins, **not yet a complete hash lock**. Do not claim fully reproducible dependency
resolution or license approval from source archive reproducibility alone.

Use the installed private wrapper:

```bash
ACS_AI="$HOME/.local/share/acs-ai-evaluation/bin/acsai"
"$ACS_AI" --help
"$ACS_AI" verify-local --repository "$PWD" --report /path/to/NEW-inspection.json
"$ACS_AI" bench run --suite smoke --workers fake --report /path/to/NEW-self-test.json
```

The health report lists actual checks and pending gates. The self-test uses fixed
fake providers and real orchestration/tests; expect two passing smoke cases marked
CLOUD_SIMULATED. It establishes no authenticated provider readiness. Do not replace
`fake` with `real` during installation. `config.json` contains only ACS_ string
settings and private staging paths; its wrapper parses JSON without shell evaluation.
Keep credentials out of this file. Runtime flags remain disabled unless explicitly
configured; hard-mode prerequisites fail closed.

## Configuration, activation and acceptance

Review [TEAM_RUNTIME](docs/upgrade/TEAM_RUNTIME.md), then configure three distinct
private authenticated provider homes, exact executable hashes, narrow toolchain
bindings and a credential-free provider catalog. Discover CLI versions locally
and confirm supported syntax; installed binaries alone cannot activate a provider.
No native paid Core-escalation adapter is enabled without a validated charge ceiling.

After owner authorization for real quota use, run explicit activation for each
provider with its own identity and a fresh report/receipt destination:

```bash
"$ACS_AI" provider-activate codex-primary --contracts /path/to/catalog.json --execute-probe
"$ACS_AI" provider-activate agy-google-a --contracts /path/to/catalog.json --execute-probe
"$ACS_AI" provider-activate agy-google-b --contracts /path/to/catalog.json --execute-probe
"$ACS_AI" verify-team --output /path/to/NEW-team-fixture --report /path/to/NEW-team.json --execute-probe
```

Enable the documented provider-contract, supervision, coordination and
`ACS_ENABLE_PROVIDER_LEDGER=1` flags only after the local prerequisites are
verified. Inspect session ceilings with `"$ACS_AI" provider-usage`. Uncertain
reservations require review; they are not automatically retried or refunded. Configure delegated cgroups/private
bounded storage where required; never bypass absent capabilities. Read
[Arch acceptance](reports/ARCH_LINUX_LOCAL_ACCEPTANCE.md) for kernel, recovery,
MCP, real roles and original integrated-scenario gates. These are all
LOCAL_VERIFICATION_REQUIRED until actual independent local evidence is reviewed.

## Backups, services, removal and troubleshooting

Use [backup/recovery](BACKUP_AND_RECOVERY.md) and the
[rollback guide](reports/BACKUP_AND_ROLLBACK_GUIDE.md). Preserve the only live database;
verify a WAL-aware backup and restore into a NEW scratch target before promotion.
Installation does not initialize or migrate operational state. Disposable migration
and backup verification are available through `verify-local --execute-probes`;
review `--help` first and keep staging paths configured.

`config/acs-ai.service.example` is an optional operator-reviewed user-service
TEMPLATE. It is never installed/enabled automatically. Paths and environment must
match the isolated prefix; service startup, watchdog and resource placement require
separate local approval and verification. Leave daemon execution disabled for the
Core-first workflow unless explicitly evaluating the compatibility executor.

For removal, stop only any explicitly installed ACS AI user service, verify and
retain `state`, `backups`, configuration, reports and authentication outside the
installation, then review and remove the exact private prefix yourself. This script
never deletes state or changes ACS Core/provider installations. Removing a PATH
entry or service file is necessary only if you explicitly created one.

On failure, inspect the private `install.log`, `pip check`, manifest SHA and Python
version. Existing/incomplete prefixes and changed source hashes are intentionally
refused. Namespace/cgroup/device failures require real host support, not disabled
sandboxing. Provider failures require local CLI/authentication diagnostics without
printing secrets; installation never solves them by asking for another token.
