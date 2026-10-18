# Explicit verification profiles

Profiles are opt-in with `ACS_ENABLE_VERIFICATION_PROFILES=1`. A validated team
task can declare `verification_commands: [["acs-profile", "cpp"]]`; the existing
verification runner dispatches this through task tests, independent review,
Guardian re-execution and post-merge tests. `acsai verify-profile PROFILE
--workspace PATH --timeout 180` is the explicit standalone form. Unknown profiles
and disabled profiles are rejected; they never fall back to Python or compilation.

| Profile | Actual verification |
|---|---|
| python | Existing mandatory sandboxed `pytest -q` |
| cpp | CMake configure in private scratch, build with a hash-bound C++ compiler, then nonempty unskipped CTest acceptance |
| node | Native Node `--test --test-reporter=tap`; nonempty passing tests, zero failures, skips, cancellations and todos |
| performance | Explicit `tests/performance` pytest acceptance; absent directory is unsupported |
| resources | Explicit `tests/resources` pytest acceptance; absent directory is unsupported |

The last two profiles select project-owned measurable acceptance tests. They do
not invent a universal performance threshold or certify kernel resource limits.
Projects must provide reviewed tests with their actual budgets. Shared cgroup,
whole-service and hard-storage contracts retain their separate existing opt-ins;
this feature neither disables them nor substitutes an RSS estimate for a hard cap.

C++/Node stages run with network disabled, readonly project sources, private
accounted scratch and readonly toolchains. The controller state, evidence key,
protected projects and configured provider authentication homes are excluded from
binds. The source tree is not used for build output. The entire pipeline shares
one timeout budget, with the existing supervisor's owned-tree cleanup grace.
Missing dependencies/namespaces/capabilities fail closed. Build success alone,
empty tests, skipped tests, truncated output or a non-completed stage cannot pass.
Actual stage argv, exit/reason/output, test counts, durations and tool SHA256s are
recorded; these are source-test provenance, never authenticated provider evidence.

System tools default to `/usr/bin/{cmake,ctest,c++,node}`. Other paths require a
private owner-owned mode-0600 JSON catalog outside the project, selected with
`ACS_VERIFICATION_TOOLCHAIN_FILE`. Strict v1 format:

```json
{
  "schema_version": 1,
  "bindings": [{
    "schema_version": 1,
    "name": "node",
    "executable": "/absolute/path/to/native/node",
    "sha256": "<exact 64-character lowercase SHA256>",
    "root": "/absolute/narrow/toolchain/prefix"
  }]
}
```

Names are `node`, `cmake`, `ctest`, `cxx`; only required tools are mounted. Bind the
actual native ELF binary, not a Python/shell launcher whose imported payload could
change without changing its own hash. Roots must be canonical, narrow, disjoint
from the project and private state, and contain the declared executable. Duplicate
bindings, wrong hashes, project-controlled catalogs and broad roots are rejected.
For pip-distributed CMake, the native tools live under its package `data/bin`, not
the generated venv launcher. Arch system packages usually supply native binaries.

The executable hash binds that binary; this is not a cryptographic inventory of
every system library or a complete dependency hash lock. Keep OS/toolchain packages
reviewed and patched. Optional Arch tools include CMake/CTest, a C++ compiler and
Node; installation never automatically installs system packages or starts tests.
The cloud dev setup pins CMake for repeatable compiler/CTest fixture verification.

Existing baseline protection now includes C/C++/JS/TS test/helper files, CMake
verification controls and package.json. Changes remain default-deny pending the
separate trusted reviewed-exception implementation; this feature grants no waiver.
Initial C++ projects should already have their reviewed CMake/CTest baseline.

`tests/test_verification_profiles.py` tests actual compilation/Node execution on
fixed fixtures with an explicitly injected fixture boundary on restricted CI,
including failures/skips/empty tests/build failures, protected paths and a real
TeamRunner → review → Guardian → Git integration scenario. These tests are
CLOUD_SIMULATED. Separate real bwrap C++ and Node fixture probes were also executed
successfully in this cloud host; that does not certify the laptop kernel, real
provider accounts or every project/language/framework. Rust, arbitrary build
systems and implicit npm lifecycle scripts are unsupported and never silently run.
