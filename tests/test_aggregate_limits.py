"""Policy/filesystem checks are real; no claim of delegated cloud cgroup enforcement."""
import os
from pathlib import Path
import sys

import pytest

from acs_team.aggregate_limits import AggregateLimits, ResourceExceeded, configured_limits
from acs_team.supervision import ProcessSupervisor


def test_storage_accounts_hardlinks_once_and_refuses_over_budget_without_following_links(tmp_path):
    root = tmp_path/'managed'
    root.mkdir()
    outside = tmp_path/'outside'
    outside.mkdir()
    (outside/'large').write_bytes(b'x'*20*1024*1024)
    (root/'link').symlink_to(outside,target_is_directory=True)
    data = root/'payload'
    data.write_bytes(b'x'*9*1024*1024)
    os.link(data,root/'same-inode')
    limits = AggregateLimits(tmp_path/'cgroup',(root,),storage_mb=16)
    assert 9*1024*1024 <= limits.check_storage() < 10*1024*1024
    (root/'extra').write_bytes(b'x'*8*1024*1024)
    with pytest.raises(ResourceExceeded):
        limits.check_storage()
    assert (outside/'large').stat().st_size == 20*1024*1024


def test_requested_aggregate_limits_fail_before_any_process_when_delegation_missing(tmp_path,monkeypatch):
    monkeypatch.setenv('ACS_ENABLE_AGGREGATE_LIMITS','1')
    monkeypatch.setenv('ACS_AGGREGATE_CGROUP',str(tmp_path/'not-cgroup'))
    monkeypatch.setenv('ACS_AGGREGATE_STORAGE_ROOTS','["'+str(tmp_path/'owned')+'"]')
    marker = tmp_path/'must-not-start'
    with pytest.raises(PermissionError):
        ProcessSupervisor().run([sys.executable,'-c',f'open({str(marker)!r},"w").write("started")'],tmp_path)
    assert not marker.exists()
    with pytest.raises(PermissionError):
        with ProcessSupervisor().start_owned(['sleep','1'],tmp_path):
            pytest.fail('Protocol started without delegated aggregate enforcement')
    monkeypatch.delenv('ACS_ENABLE_AGGREGATE_LIMITS')
    assert configured_limits() is None


@pytest.mark.simulated
def test_exact_cgroup_contract_rejects_unlimited_or_mismatched_budgets(tmp_path):
    mount = tmp_path/'synthetic-cgroup-files'
    group = mount/'workers'
    group.mkdir(parents=True,mode=0o700)
    values = {'memory.max':str(8192*1024*1024),'memory.swap.max':'0','memory.oom.group':'1',
              'cpu.max':'200000 100000','pids.max':'256','cgroup.procs':''}
    for name,value in values.items():
        (group/name).write_text(value)
    limits = AggregateLimits(group,(tmp_path/'storage',))
    limits.validate_kernel_contract(mount)
    (group/'memory.max').write_text('max')
    with pytest.raises(PermissionError,match='memory.max'):
        limits.validate_kernel_contract(mount)
    with pytest.raises(PermissionError):
        AggregateLimits(Path('/sys/fs/cgroup'),(tmp_path,)).validate_kernel_contract()


@pytest.mark.local_only(reason='Requires an explicitly enabled empty delegated cgroup v2; cloud delegation is unavailable')
def test_local_owned_launcher_really_joins_delegated_kernel_group(tmp_path):
    if os.environ.get('ACS_RUN_LOCAL_AGGREGATE_PROBE') != '1':
        pytest.skip('Operator must explicitly enable the delegated-kernel probe')
    limits = configured_limits()
    assert limits is not None
    assert not (limits.cgroup/'cgroup.procs').read_text().strip(), 'Use an empty dedicated group; never probe active worker groups'
    result = ProcessSupervisor().run([sys.executable,'-c',
        'from pathlib import Path;print(Path("/proc/self/cgroup").read_text())'],tmp_path,timeout=10)
    assert result['exit_code']==0 and result['reason']=='completed'
    expected = str(limits.cgroup.relative_to('/sys/fs/cgroup'))
    assert result['stdout'].strip() == '0::/'+expected
    assert not (limits.cgroup/'cgroup.procs').read_text().strip()
