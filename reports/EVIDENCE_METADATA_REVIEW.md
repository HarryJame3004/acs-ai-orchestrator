# Finite evidence metadata review

The source and history gates flagged 15 values across five retained failure
artifacts plus the new report's public source commit. Inspection identified only
disposable worktree paths, fixture Git commits, error fingerprints and verifier
artifact hashes. No candidate is an API credential. Original private raw evidence
has not been changed; no credential has been tested or rotated.

`acs_team/evidence_metadata.py` binds the five reviewed artifact files to their
exact SHA256 bytes. Any content or path change invalidates that exception. The
checkpoint exception independently requires the exact named report field, exact
detector fingerprint and an actual commit in local Git history. This does not
exclude a report directory, authorize arbitrary future values, or change the
existing source/secret baseline. Static output separately records each reviewed
metadata finding; historical output retains all candidates and classifications.

`tests/scaffolding/test_evidence_metadata.py` checks modified bytes, unrelated
paths, forged field names, unrecognized commits and wrong detector identities.
The original scanner metadata and duplicate/fingerprint regression tests remain
unchanged. These exceptions apply to these diagnostic artifacts only, and are
not an implementation of project baseline test-update authorization.

At d262d4f, hosted root checks failed in both static/history secret gates after
these proof artifacts were committed; hosted bridge and companion jobs passed.
The new finite review addresses those exact false positives. Downloading the raw
hosted log was denied by the Actions results storage endpoint; GitHub API/PR/run
metadata queries succeeded. No new token or environment restart was requested.
