"""CLOUD_REAL: reports cannot grant arbitrary secret-scan exclusions."""

import hashlib

from scripts.security_scan import known_report_metadata


def test_only_exact_existing_scan_metadata_is_recognized():
    known = hashlib.sha1(b'public fixture reference').hexdigest()
    commit = hashlib.sha1(b'public Git object reference').hexdigest()

    def check(name, field, value, detector=None):
        return known_report_metadata(
            name, f'  "{field}": "{value}",',
            detector or hashlib.sha1(value.encode()).hexdigest(), {known}, [commit],
        )

    for path in ('reports/stage_7_history.json','reports/continuation_history.json'):
        assert check(path, 'fingerprint', known)
        assert check(path, 'commit', commit[:12])
        assert not check(path, 'fingerprint', commit)
        assert not check(path, 'commit', known[:12])
        assert not check('acs_team/config.py', 'fingerprint', known)
        assert not check(path, 'password', known)
        assert not check(path, 'fingerprint', known, detector=commit)
    assert not check('reports/arbitrary.json','fingerprint',known)
    derived = hashlib.sha1(known.encode()).hexdigest()
    public_git_derived = hashlib.sha1(commit[:12].encode()).hexdigest()
    assert check('reports/continuation_history.json','fingerprint',derived)
    assert check('reports/continuation_history.json','fingerprint',public_git_derived)
    assert not check('reports/stage_7_history.json','fingerprint',derived)
    assert not check('reports/continuation_history.json','fingerprint',hashlib.sha1(derived.encode()).hexdigest())
    assert not check('acs_team/config.py','fingerprint',derived)
