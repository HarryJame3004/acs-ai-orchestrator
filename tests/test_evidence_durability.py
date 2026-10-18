"""Real file publication/failure checks; not a host power-loss simulation."""
import json
import os
import stat

import pytest

from acs_team.evidence import persist_evidence


def test_evidence_is_complete_private_and_file_then_directory_synced(tmp_path,monkeypatch):
    events = []
    sync = os.fsync
    def observe(fd):
        events.append('directory' if stat.S_ISDIR(os.fstat(fd).st_mode) else 'file')
        sync(fd)
    monkeypatch.setattr(os,'fsync',observe)
    artifact = persist_evidence({'commit':'fixture','tests':{'passed':3}},tmp_path/'artifacts')
    assert json.loads(artifact.read_text()) == {'commit':'fixture','tests':{'passed':3}}
    assert events == ['file','directory']
    assert artifact.stat().st_mode & 0o777 == 0o600
    assert artifact.stat().st_nlink == 1
    assert list(artifact.parent.iterdir()) == [artifact]


@pytest.mark.parametrize('fault',['serialization','file_sync','publication','directory_sync'])
def test_failed_persistence_never_returns_an_evidence_reference(tmp_path,monkeypatch,fault):
    directory = tmp_path/'artifacts'
    directory.mkdir(mode=0o700)
    existing = directory/'retained.evidence.json'
    existing.write_text('retained')
    payload = {'result':object()} if fault == 'serialization' else {'result':'complete'}
    sync = os.fsync
    def fail_sync(fd):
        is_directory = stat.S_ISDIR(os.fstat(fd).st_mode)
        if is_directory == (fault == 'directory_sync'):
            raise OSError('injected storage failure')
        sync(fd)
    if fault in {'file_sync','directory_sync'}:
        monkeypatch.setattr(os,'fsync',fail_sync)
    if fault == 'publication':
        def fail_link(*args,**kwargs):
            raise OSError('injected storage failure')
        monkeypatch.setattr(os,'link',fail_link)
    with pytest.raises((OSError,TypeError)):
        persist_evidence(payload,directory)
    assert existing.read_text() == 'retained'
    assert not list(directory.glob('.*.partial'))
    published = [p for p in directory.iterdir() if p != existing]
    if fault == 'directory_sync':
        # Entry visibility is not durability: publication must still raise.
        assert len(published) == 1
        assert json.loads(published[0].read_text()) == payload
    else:
        assert published == []
