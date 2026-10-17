# Golden fixtures

fixtures/cases.json is mirrored into packaged acs_team/golden_cases.json. Twelve
small versioned missions generate disposable Git repos. Fake workers write fixed
reference solutions; independent fixture tests execute through real orchestration
and Guardian. The C++ fixture requires c++. Collaboration uses two task branches;
recovery checks a confirmed dead expired claim before replacement.

`acsai bench run --suite smoke --workers fake --report /tmp/smoke.json`
uses the first two cases. Full is deliberate, not run after every edit. Report
paths must be new. Use --baseline FILE to reject missing/regressed passes; suite
and worker modes must match. Runtime and harness child peak RSS are cloud-machine
measurements, not laptop/provider comparisons. Real provider benchmarks remain
BLOCKED until local role adapters/verification are complete. No auto-installation.
