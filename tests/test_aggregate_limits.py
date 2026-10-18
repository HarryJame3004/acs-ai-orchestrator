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


def test_linked_worktree_requires_shared_git_storage_even_from_subdirectory(tmp_path):
    checkout = tmp_path/'checkout'
    nested = checkout/'package'
    nested.mkdir(parents=True)
    shared = tmp_path/'repository.git'
    gitdir = shared/'worktrees'/'job'
    gitdir.mkdir(parents=True)
    (checkout/'.git').write_text(f'gitdir: {gitdir}\n')
    (gitdir/'commondir').write_text('../..\n')
    limited = AggregateLimits(tmp_path/'cgroup',(checkout,))
    with pytest.raises(PermissionError,match='outside aggregate'):
        limited.require_workspace(nested)
    AggregateLimits(tmp_path/'cgroup',(checkout,shared)).require_workspace(nested)
    # Accounting the linked metadata alone does not account shared objects/refs.
    with pytest.raises(PermissionError,match='outside aggregate'):
        AggregateLimits(tmp_path/'cgroup',(checkout,gitdir)).require_workspace(nested)


def test_workspace_rejects_git_symlink_outside_inventory(tmp_path):
    checkout = tmp_path/'checkout'
    checkout.mkdir()
    outside = tmp_path/'unaccounted.git'
    outside.mkdir()
    (checkout/'.git').symlink_to(outside,target_is_directory=True)
    with pytest.raises(PermissionError,match='symlinks'):
        AggregateLimits(tmp_path/'cgroup',(checkout,)).require_workspace(checkout)


@pytest.mark.simulated
def test_managed_scratch_stays_accounted_and_cleans_on_failure(tmp_path,monkeypatch):
    from acs_team import aggregate_limits as module
    scratch = tmp_path/'scratch'
    scratch.mkdir(mode=0o700)
    limits = AggregateLimits(tmp_path/'cgroup',(scratch,))
    # Only kernel delegation is substituted; filesystem placement/cleanup is real.
    monkeypatch.setattr(module,'configured_limits',lambda:limits)
    monkeypatch.setenv('ACS_AGGREGATE_SCRATCH_ROOT',str(scratch))
    with pytest.raises(RuntimeError,match='worker failed'):
        with module.managed_temporary_directory(prefix='test-provider-') as directory:
            temporary = Path(directory)
            assert temporary.parent == scratch
            (temporary/'artifact').write_bytes(b'x'*4096)
            assert limits.check_storage() >= 4096
            raise RuntimeError('worker failed')
    assert not temporary.exists()
    scratch.chmod(0o755)
    with pytest.raises(PermissionError,match='private directory'):
        with module.managed_temporary_directory(prefix='test-denied-'):
            pytest.fail('Public scratch was admitted')
    scratch.chmod(0o700)
    monkeypatch.setenv('ACS_AGGREGATE_SCRATCH_ROOT',str(tmp_path))
    with pytest.raises(PermissionError,match='outside aggregate'):
        with module.managed_temporary_directory(prefix='test-denied-'):
            pytest.fail('Unaccounted scratch was admitted')


@pytest.mark.simulated
def test_unaccounted_workspace_is_denied_before_process_spawn(tmp_path,monkeypatch):
    from acs_team import aggregate_limits as module
    accounted = tmp_path/'accounted'
    accounted.mkdir()
    limits = AggregateLimits(tmp_path/'cgroup',(accounted,))
    monkeypatch.setattr(module,'configured_limits',lambda:limits)
    marker = tmp_path/'must-not-start'
    supervisor = ProcessSupervisor()
    with pytest.raises(PermissionError,match='outside aggregate'):
        supervisor.run([sys.executable,'-c',f'open({str(marker)!r},"w").write("started")'],tmp_path)
    with pytest.raises(PermissionError,match='outside aggregate'):
        with supervisor.start_owned(['sleep','1'],tmp_path):
            pytest.fail('Unaccounted protocol process started')
    assert not marker.exists()


@pytest.mark.simulated
@pytest.mark.parametrize('omitted',['repository','state','database'])
def test_team_dispatch_refuses_unaccounted_durable_storage(tmp_path,monkeypatch,omitted):
    from acs_team import aggregate_limits as module
    from acs_team.db import DatabaseManager
    from acs_team.team_missions import TeamMissionController
    paths = {name:tmp_path/name for name in ['repository','state','database']}
    for path in paths.values():
        path.mkdir(mode=0o700)
    db = DatabaseManager(paths['database']/'fixture.db')
    controller = TeamMissionController(db,evidence_key='fixture-resource-contract',root=paths['state'])
    monkeypatch.setenv('ACS_ENABLE_COORDINATION','1')
    monkeypatch.setattr(module,'configured_limits',lambda:AggregateLimits(
        tmp_path/'cgroup',tuple(path for name,path in paths.items() if name != omitted)))
    def unexpected():
        pytest.fail('Provider selection ran before durable storage validation')
    monkeypatch.setattr(controller,'_runner',unexpected)
    with pytest.raises(PermissionError,match='outside aggregate'):
        controller._run_mission('fixture-no-dispatch','Create a harmless module',paths['repository'])
    assert db.get_mission('fixture-no-dispatch') is None


def test_hard_storage_without_aggregate_and_without_dedicated_mount_fails_closed(tmp_path,monkeypatch):
    monkeypatch.delenv('ACS_ENABLE_AGGREGATE_LIMITS',raising=False)
    monkeypatch.setenv('ACS_REQUIRE_HARD_STORAGE','1')
    with pytest.raises(PermissionError,match='requires aggregate'):
        configured_limits()
    volume = tmp_path/'not-a-mount'
    volume.mkdir(mode=0o700)
    with pytest.raises(PermissionError,match='dedicated mounted'):
        AggregateLimits(tmp_path/'cgroup',(volume,),storage_volume=volume).validate_storage_volume()


@pytest.mark.simulated
@pytest.mark.parametrize('fault',[None,'capacity','device_capacity','nested_mount','outside_root','public','filesystem_type'])
def test_bounded_filesystem_contract_checks_kernel_mount_device_and_all_roots(tmp_path,monkeypatch,fault):
    from types import SimpleNamespace
    volume = tmp_path/'volume'
    volume.mkdir(mode=0o700)
    root = volume/'managed'
    root.mkdir()
    device = f'{os.major(volume.stat().st_dev)}:{os.minor(volume.stat().st_dev)}'
    devices = tmp_path/'synthetic-kernel-devices'
    (devices/device).mkdir(parents=True)
    (devices/device/'size').write_text(str((32 if fault=='device_capacity' else 16)*2048))
    mount = tmp_path/'synthetic-mountinfo'
    kind = 'fuse.untrusted' if fault=='filesystem_type' else 'ext4'
    mount.write_text(f'123 1 {device} / {volume} rw - {kind} /dev/fixture rw\n')
    if fault=='nested_mount':
        with mount.open('a') as stream:
            stream.write(f'124 123 {device} / {root}/escape rw - ext4 /dev/other rw\n')
    if fault=='public':
        volume.chmod(0o755)
    roots = (tmp_path,) if fault=='outside_root' else (root,)
    limits = AggregateLimits(tmp_path/'cgroup',roots,storage_mb=16,storage_volume=volume)
    monkeypatch.setattr(os,'fstatvfs',lambda fd:SimpleNamespace(f_frsize=4096,f_blocks=(8192 if fault=='capacity' else 4096)))
    if fault is None:
        limits.validate_storage_volume(mount,devices)
    else:
        with pytest.raises(PermissionError):
            limits.validate_storage_volume(mount,devices)


@pytest.mark.simulated
def test_hard_storage_sandbox_tmp_is_backed_by_accounted_private_scratch(tmp_path,monkeypatch):
    from acs_team import aggregate_limits as module
    from acs_team.security import sandbox_argv
    workspace, home = tmp_path/'workspace',tmp_path/'home'
    workspace.mkdir()
    (workspace/'.git').mkdir()
    home.mkdir(mode=0o700)
    limits = AggregateLimits(tmp_path/'cgroup',(workspace,home),storage_volume=tmp_path)
    monkeypatch.setenv('ACS_REQUIRE_HARD_STORAGE','1')
    monkeypatch.setattr(module,'configured_limits',lambda:limits)
    argv = sandbox_argv(workspace,['/usr/bin/true'],home=home)
    index = argv.index('/tmp')
    assert argv[index-2:index+1] == ['--bind',str(home/'tmp'),'/tmp']
    assert (home/'tmp').is_dir() and (home/'tmp').stat().st_mode & 0o777 == 0o700
    (home/'tmp').rmdir()
    (home/'tmp').symlink_to(workspace,target_is_directory=True)
    with pytest.raises(PermissionError,match='scratch may not be a symlink'):
        sandbox_argv(workspace,['/usr/bin/true'],home=home)


@pytest.mark.simulated
@pytest.mark.parametrize('fault',[None,'membership','unlimited','outside_worker','no_overhead'])
def test_service_parent_bounds_controller_and_workers_without_moving_processes(tmp_path,fault):
    mount = tmp_path/'synthetic-service-cgroup'
    service = mount/'acs-service'
    workers = service/'workers'
    workers.mkdir(parents=True,mode=0o700)
    service.chmod(0o700)
    values = {'memory.max':str(10240*1024*1024),'memory.swap.max':'0',
              'memory.oom.group':'1','cpu.max':'250000 100000','pids.max':'384','cgroup.procs':''}
    for name,value in values.items():
        (service/name).write_text(value)
    membership = tmp_path/'synthetic-process-membership'
    membership.write_text('0::/acs-service\n' if fault!='membership' else '0::/unrelated-service\n')
    if fault=='unlimited':
        (service/'memory.max').write_text('max')
    if fault=='outside_worker':
        workers = mount/'unrelated-workers'
    limits = AggregateLimits(workers,(tmp_path/'storage',),service_cgroup=service,
                             service_memory_mb=8192 if fault=='no_overhead' else 10240)
    before = (service/'cgroup.procs').read_text()
    if fault is None:
        limits.validate_service_contract(mount,membership)
    else:
        with pytest.raises(PermissionError):
            limits.validate_service_contract(mount,membership)
    assert (service/'cgroup.procs').read_text() == before
    assert membership.read_text().startswith('0::/')


def test_whole_service_requirement_cannot_be_enabled_without_aggregate(monkeypatch):
    monkeypatch.delenv('ACS_ENABLE_AGGREGATE_LIMITS',raising=False)
    monkeypatch.setenv('ACS_REQUIRE_SERVICE_LIMITS','1')
    with pytest.raises(PermissionError,match='requires aggregate'):
        configured_limits()


@pytest.mark.simulated
@pytest.mark.parametrize('operation',['database','evidence','private_export','backup_or_staging'])
def test_hard_storage_rejects_controller_writes_outside_accounted_roots(tmp_path,monkeypatch,operation):
    from acs_team import aggregate_limits as module
    from acs_team.db import DatabaseManager
    from acs_team.evidence import persist_evidence
    from acs_team.recovery import new_directory,private_write
    accounted = tmp_path/'accounted'
    accounted.mkdir(mode=0o700)
    outside = tmp_path/'outside'
    outside.mkdir()
    target = outside/'must-not-appear'
    limits = AggregateLimits(tmp_path/'cgroup',(accounted,),storage_volume=tmp_path)
    monkeypatch.setenv('ACS_REQUIRE_HARD_STORAGE','1')
    monkeypatch.setattr(module,'configured_limits',lambda:limits)
    with pytest.raises(PermissionError,match='outside aggregate'):
        if operation=='database':
            DatabaseManager(target/'fixture.db')
        elif operation=='evidence':
            persist_evidence({'fixture':'result'},target)
        elif operation=='private_export':
            private_write(target,b'fixture')
        else:
            new_directory(target)
    assert not target.exists()


def test_invalid_hard_contract_stops_runtime_initialization_before_directory_creation(tmp_path):
    import subprocess
    environment = {k:v for k,v in os.environ.items() if not k.startswith(('ACS_','AGPAIR_'))}
    environment.update(ACS_HOME=str(tmp_path/'new-runtime'),ACS_BACKUPS_DIR=str(tmp_path/'new-backup'),
                       ACS_REQUIRE_HARD_STORAGE='1',PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run([sys.executable,'-c','import acs_team.config'],env=environment,
                            cwd=tmp_path,capture_output=True,text=True,timeout=10)
    assert result.returncode != 0 and 'requires aggregate enforcement' in result.stderr
    assert not (tmp_path/'new-runtime').exists()
    assert not (tmp_path/'new-backup').exists()
