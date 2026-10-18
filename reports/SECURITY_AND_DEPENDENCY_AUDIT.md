# Security/dependency checkpoint — PARTIAL, source 511ff9b

Mandatory provider activation/sandbox, isolated profiles, host-owned role identity,
SHA/HMAC Guardian, fencing and bounded corrections remain enforced. New protection
covers synchronized evidence/WAL, baseline fixtures/helpers/configuration, bounded
filesystem and parent-cgroup contracts and controller write admission. A substantive
Guardian re-execution arity/unexecuted-score defect is fixed with six regressions.
Real kernel/account/service proof remains LOCAL_VERIFICATION_REQUIRED.

Scoped source static: 0 Ruff/0 mypy; 15 known detector candidates, zero new.
Committed source history: 51 commits, 71 known candidates, zero unknown/skipped;
canary enforced. Rescan later evidence-only commits. No zero-secret guarantee for
operational/binary/untracked state. The seeded postmerge failure remains an open
reliability/security acceptance concern; retries are not closure.

Current dependency checks completed:

- Isolated pip-audit 2.9.0 queried PyPI advisories for all 34 pinned cloud-dev
  requirements with `--disable-pip --no-deps --vulnerability-service pypi`:
  no known vulnerabilities reported, no skipped package in the JSON result.
  This audits the declared pinned set, not every possible optional installation.
  FULL_TEST_EVIDENCE.json records the command and output artifact.
- Companion `npm audit --json`: zero reported vulnerabilities in all severities.
  npm test compiles and exercises the companion; production build also ran.
- FINAL_DEPENDENCY_LICENSE_METADATA.json inventories 37 installed Python
  distributions. The ACS application itself has no declared license metadata;
  choosing its license requires the owner's decision and is BLOCKED. No license
  has been invented. All other distribution records have a declaration/classifier.
- FINAL_COMPANION_LICENSE_METADATA.json inventories 34 lockfile entries. All
  dependency entries declare a license; the root lockfile entry does not, while
  the companion includes its existing LICENSE file. Metadata presence does not
  certify compatibility or approve redistribution.

The application dependency pins were not changed. Audit tools were installed in
an isolated temporary venv using normal TLS/package verification. The requirements
are version-pinned but not fully hash-locked; this remains disclosed. Advisory
results are a point-in-time database check, not a guarantee of absence of defects.

Outstanding: complete dependency/license review, actual bounded-device/delegated-service measured enforcement, reviewed baseline exceptions/coverage diff,
MCP mission routing/HTTP/per-operation remote write approval, provider quota and
failover, broader adversarial/randomized campaigns and all actual provider/account
and Arch Linux service acceptance. No credentials were printed/requested, no Core
modification, main push/merge, local deployment or release activation occurred.
