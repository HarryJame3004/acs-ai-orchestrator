# Verification failures and corrections

These are actual observed failures, not waived or rewritten baseline entries.
Final reports/CI_STATUS.json and suite reports identify the last verified code.
All cloud provider/SDK/protocol fixtures remain CLOUD_SIMULATED; local checks are
LOCAL_VERIFICATION_REQUIRED. Static/process/SQLite checks are CLOUD_REAL.

| Observation | Diagnosis and correction | Evidence/gate |
|---|---|---|
| Recovery increment initially left one postmerge regression | Cloud fixture verification wrote untracked bytecode, unlike production. The fixture now uses PYTHONDONTWRITEBYTECODE/PYTHONNOUSERSITE; the original FAILED/INTEGRATED assertions are unchanged. | bf9e542; subsequent 167-pass root run |
| New verify-team refusal CLI initially lacked a failure JSON artifact | The LocalCheck error path omitted required duration. Added measured/capped duration and kept the nonzero exit, private report, no-output-before-activation assertions. | Targeted real refusal/CLI test and subsequent stable-head root 171 pass / 7 local skips |
| Persisting raw history metadata produced 33 working-tree/history candidates | All were detector hashes/public Git refs in the new report. Current summaries avoid raw hashes. History recognizes only the two exact report paths, exact fields, matching detector hash, known baseline/public Git identity and one bounded derivation for the first continuation artifact; 16 residual values were independently proven to derive from 11 known fingerprints and 5 public Git refs. Unknown fields/values/source files and further recursion remain rejected. No baseline reset or report-wide exclusion. | tests/scaffolding/test_history_metadata.py; final working-tree/history reports |
| Original root 37 passed / 5 failed | Four actual local prerequisites, one workstation-specific CLI interpreter; entry point also broken. Separate source/test portability commits, original baseline unchanged. | 1cb2ad7, fd23285; PR #1 hosted pass |
| V2.3 hosted periodic backup failure | Fresh VM uptime below one-hour interval incorrectly delayed first backup. Initial backup immediately due, uptime=10 regression retained. | cebfd08; PR #3 hosted pass |
| Stage 7 first hosted lint failure | New test used semicolon-separated statements. Formatting corrected without exclusions. | e69f67e; root/static hosted pass |
| Companion compile failed: three state modules missing | Root state/ ignore hid TypeScript source; reviewed exact pinned upstream blobs restored and ignore narrowed. Build's hidden IDE deployment removed. | COMPANION_STATE_RESTORATION.md; 138 tests/build pass |
| Companion low dependency advisory | esbuild 0.27.4 development-server advisory; exact 0.28.2 update, locked installation and fresh audit/build/tests. | COMPANION_DEPENDENCY_AUDIT.json: zero |
| Expanded bridge hosted profile initially failed nine cases | Fake Codex preflight needed its explicit harmless executable, alias precedence needed isolation, terminal assertions needed stable dimensions; a real fast-terminal race replaced stored controller with generic. | Separate fixtures, preserved assertions; 8595f48 policy fix plus deterministic regression; hosted bridge pass at 2892d6c |
| Bridge failing-task fixture refused dispatch | Fixture exited nonzero even for --help; distinguish successful launch probe from intended task failure. | 422d0c3; task failure assertions unchanged |
| Bridge auth cleanup strict PID check intermittently failed under load | Reaper was killed too soon; full host scans added cost. Signal owned helper, allow bounded reaping, avoid redundant unowned descendant signaling. | Existing strict process tests retained; 2892d6c and subsequent kernel fallback |
| New cloud guard run: 147 pass / 2 fail / 5 local skips | This kernel omits /proc/.../children. Added birth-checked /proc fallback and explicit regression. A fake oversized-response test's 200ms interpreter-start budget expired before protocol rejection under concurrent load. Protocol-error modes now get 2s; the explicit timeout mode retains 200ms and exact error/cleanup assertions. | Final stage_7_tests.json; no expected exception weakened |
| Artificial missing-primary-binary profile: 844 pass / 3 fail | Two alias fixtures inherited an overriding primary environment variable; the third assertion's visible phrase wrapped in rich output. Clear the primary only in alias tests, stabilize terminal dimensions and strip invisible ANSI for visible-text comparisons. | 7f0bc44 and follow-up; no runtime availability fabricated |
| Committed history report triggered its own detector | Historical report carried known SHA1 scanner fingerprints and public Git references. Exact report-field/value plus detector-hash identity validation now recognizes only known fingerprints/reachable commits; negative tests reject arbitrary values, source paths and password fields. Current report is compact. Original baseline unchanged. | Final history gate and test_history_metadata.py |
| Offline candidate gate flagged archive checksum | It was the public ZIP SHA256 digest, not a credential. Full checksum moved to private artifact sidecar; repository metadata references that file. No scanner exclusion/baseline expansion. | local_bundle.json, final static gate |

Actions log downloads remained separately proxy-blocked; sanitized check
annotations exposed actionable failures. GitHub API and existing authentication
continued working. No token request, TLS bypass, repeated blind retry, baseline
reset, skip relabeling or assertion weakening was used to obtain final results.

## Final directive V2 continuation

- Direct isolated pytest: 173 passed, 3 legacy provider-availability failures,
  2 gated skips. Preserved in directive_direct_pytest.json; not a full pass.
- Concurrent focused supervisor profile: 1 failed / 6 passed because the CPU
  test reached its five-second wall deadline (-15) before one scheduled CPU
  second. Unchanged sequential case passed. d641fea retains RLIMIT_CPU=1 and
  signal assertions, increases only scheduler wall allowance to 30 seconds and
  additionally rejects wall cancellation as CPU enforcement proof. Final focused
  profile: 7 passed.
- Initial hard-storage sandbox policy fixture: 18 passed / 1 failed / 1 skipped.
  The empty test workspace inherited an unrelated ancestor `/tmp/.git` and was
  correctly rejected as unaccounted shared Git. The positive fixture now creates
  its own `.git` directory; production rejection remains. Final hard-storage
  profile: 19 passed / 1 explicit local skip. Later service profile: 25 / 1.
- New reports initially duplicated scanner fingerprints and a quoted full Git
  ID, yielding 52 derived metadata candidates. Retained the exact raw scan in
  /tmp and committed a count/known/unknown summary instead; did not change
  scanner rules, canaries, baselines or allowlist. Full later scoped scans had
  15 existing candidates and zero new candidates before subsequent updates.
- Found and fixed a substantive Guardian issue after green earlier checkpoints:
  verifier wrapper arity raised a caught TypeError, and unexecuted tests received
  a passing T score. f461c9d propagates timeout and gives unexecuted tests zero
  plus an unconditional veto, even with a low threshold. New regression: six
  passed, existing Guardian profile: four passed. Latest full root evidence is
  recorded separately, including the native controller routes.

- Reproducible archive check initially failed: ordinary entries had fixed 1980
  timestamps, but the generated ACS_BUNDLE_MANIFEST.json entry used wall time.
  Packaging now sets its timestamp/mode/compression explicitly. Existing secret/
  symlink/existing-destination assertions remain; the test additionally fixes the
  clock to 2031 and requires byte-identical archives. Initial 9676296 ZIPs were
  not offered as verified artifacts and are superseded by the later bundle.
