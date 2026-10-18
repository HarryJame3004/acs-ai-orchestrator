"""Local probe must never promote a cloud/fake provider to authenticated success."""
import os
import json
import subprocess
import sys
import pytest

from acs_team.local_team_probe import run_local_team_probe


def test_real_probe_refuses_missing_activation_before_output_writes(tmp_path,monkeypatch):
    monkeypatch.delenv('ACS_ENABLE_PROVIDER_CONTRACTS',raising=False)
    destination=tmp_path/'must-remain-absent'
    with pytest.raises(PermissionError,match='ACS_ENABLE_PROVIDER_CONTRACTS'):
        run_local_team_probe(destination)
    assert not destination.exists()
    report=tmp_path/'failed-local-report.json'
    command=[sys.executable,'-m','acs_team.cli','verify-team','--output',str(destination),
             '--report',str(report),'--execute-probe']
    result=subprocess.run(command,env={**os.environ,'ACS_HOME':str(tmp_path/'runtime'),
                                      'ACS_BACKUPS_DIR':str(tmp_path/'backups')},capture_output=True,text=True)
    assert result.returncode==1 and not destination.exists()
    data=json.loads(report.read_bytes())
    assert data['summary']=={'pass':0,'fail':1,'skipped':0,'error':0}
    assert data['checks'][0]['label']=='LOCAL_VERIFICATION_REQUIRED'
    assert report.stat().st_mode & 0o777==0o600


@pytest.mark.local_only(reason='Requires explicit local quota authorization and three authenticated sandbox-verified provider profiles')
def test_local_authenticated_team_probe(tmp_path):
    if os.environ.get('ACS_RUN_LOCAL_TEAM_PROBE') != '1':
        pytest.skip('Operator must explicitly authorize real provider quota for the local team probe')
    result=run_local_team_probe(tmp_path/'real-team-fixture')
    assert result['summary']=={'pass':1,'fail':0,'skipped':0,'error':0}
    assert result['checks'][0]['label']=='LOCAL_VERIFICATION_REQUIRED'
