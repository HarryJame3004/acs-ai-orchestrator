"""Opt-in cgroup contract, bounded filesystem contract and storage monitoring.

The operator delegates/configures the cgroup. This module never changes global
limits, mounts filesystems or kills unregistered processes. CPU/RAM/PID limits
are kernel enforced. Without the optional dedicated bounded block filesystem,
storage enforcement is sampled and can overshoot between samples.
"""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import stat
import threading
import tempfile
import time


class ResourceExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class AggregateLimits:
    cgroup: Path
    storage: tuple[Path, ...]
    memory_mb: int = 8192
    cpu_percent: int = 200
    pids: int = 256
    storage_mb: int = 8192
    storage_volume: Path | None = None

    def encoded(self) -> str:
        return json.dumps({'cgroup':str(self.cgroup),'storage':[str(p) for p in self.storage],
                           'memory_mb':self.memory_mb,'cpu_percent':self.cpu_percent,
                           'pids':self.pids,'storage_mb':self.storage_mb,
                           'storage_volume':str(self.storage_volume) if self.storage_volume else None})

    def __post_init__(self):
        if not 128 <= self.memory_mb <= 131072 or not 1 <= self.cpu_percent <= 3200:
            raise ValueError('Invalid aggregate CPU/RAM budget')
        if not 8 <= self.pids <= 4096 or not 16 <= self.storage_mb <= 1048576 or not 1 <= len(self.storage) <= 8:
            raise ValueError('Invalid aggregate PID/storage budget')

    def validate_kernel_contract(self, mount: Path = Path('/sys/fs/cgroup')) -> None:
        path = self.cgroup
        if not path.is_absolute() or path.is_symlink() or path == mount or mount.resolve() not in path.resolve().parents:
            raise PermissionError('A dedicated delegated cgroup v2 is required')
        # Refuse symlink ancestors and a group writable by unrelated identities.
        for parent in (path, *path.parents):
            if parent == mount:
                break
            if parent.is_symlink():
                raise PermissionError('Cgroup paths may not traverse symlinks')
        if path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o022:
            raise PermissionError('Cgroup must be exclusively owned by the operator')
        expected = {'memory.max':str(self.memory_mb*1024*1024), 'memory.swap.max':'0',
                    'memory.oom.group':'1', 'pids.max':str(self.pids),
                    'cpu.max':f'{self.cpu_percent*1000} 100000'}
        for name, value in expected.items():
            if (path/name).read_text().strip() != value:
                raise PermissionError(f'Aggregate kernel budget mismatch: {name}')
        if not os.access(path/'cgroup.procs',os.W_OK):
            raise PermissionError('Cgroup has not been delegated for worker attachment')

    def join_current_process(self) -> None:
        self.validate_kernel_contract()
        # Linux moves only this launcher, before it forks any untrusted process.
        (self.cgroup/'cgroup.procs').write_text(str(os.getpid()))
        if os.getpid() not in {int(v) for v in (self.cgroup/'cgroup.procs').read_text().split()}:
            raise PermissionError('Kernel did not attach the owned launcher')

    def require_accounted(self, path: Path) -> None:
        """Refuse execution/storage paths outside the explicitly inventoried roots."""
        if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
            raise PermissionError('Accounted storage paths must be absolute and free of symlinks')
        canonical = path.resolve()
        if not any(canonical == root.resolve() or root.resolve() in canonical.parents for root in self.storage):
            raise PermissionError('Execution storage is outside aggregate storage roots')

    def require_workspace(self, workspace: Path) -> None:
        self.require_accounted(workspace)
        # Linked worktrees write objects and refs in the shared Git directory.
        marker = next((parent / '.git' for parent in (workspace, *workspace.parents)
                       if (parent / '.git').exists() or (parent / '.git').is_symlink()), None)
        if marker is None:
            return
        self.require_accounted(marker)
        if marker.is_file():
            if marker.is_symlink() or marker.stat().st_size > 4096:
                raise PermissionError('Invalid linked worktree Git directory')
            value = marker.read_text().strip()
            if not value.startswith('gitdir: '):
                raise PermissionError('Invalid linked worktree Git directory')
            gitdir = marker.parent / value[8:]
            self.require_accounted(gitdir)
            common = gitdir / 'commondir'
            if common.exists():
                if common.is_symlink() or common.stat().st_size > 4096:
                    raise PermissionError('Invalid shared Git directory')
                self.require_accounted(gitdir / common.read_text().strip())

    def check_storage(self) -> int:
        if self.storage_volume is not None:
            self.validate_storage_volume()
        seen: set[tuple[int,int]] = set()
        total = 0
        entries = 0
        roots = []
        for root in self.storage:
            if not root.is_absolute() or root.is_symlink() or root.resolve() in {
                Path('/'),Path('/tmp'),Path('/home'),Path('/workspace'),Path.home()}:
                raise PermissionError('Storage accounting requires narrow owned roots')
            if root.exists():
                for parent in root.parents:
                    if parent.is_symlink():
                        raise PermissionError('Storage root traverses a symlink')
                roots.append(root)

        def visit(parent_fd, name):
            nonlocal entries, total
            try:
                info = os.stat(name,dir_fd=parent_fd,follow_symlinks=False)
            except FileNotFoundError:
                return
            entries += 1
            if entries > 100000:
                raise ResourceExceeded('Storage inventory exceeded its bounded entry budget')
            inode = (info.st_dev,info.st_ino)
            if inode in seen:
                return
            seen.add(inode)
            if stat.S_ISLNK(info.st_mode):
                return  # Never traverse outside an owned storage root.
            total += max(info.st_size,info.st_blocks*512)
            if total > self.storage_mb*1024*1024:
                raise ResourceExceeded('Aggregate owned storage budget exceeded')
            if stat.S_ISDIR(info.st_mode):
                fd = os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent_fd)
                try:
                    actual = os.fstat(fd)
                    if (actual.st_dev,actual.st_ino) != inode:
                        raise PermissionError('Storage directory identity changed')
                    with os.scandir(fd) as children:
                        for child in children:
                            visit(fd,child.name)
                finally:
                    os.close(fd)
        for root in roots:
            visit(None,str(root))
        return total

    def validate_storage_volume(self, mountinfo: Path = Path('/proc/self/mountinfo'),
                                block_devices: Path = Path('/sys/dev/block')) -> None:
        """Require a dedicated mounted disk filesystem whose entire capacity fits.

        This deliberately accepts no operator-written quota receipt and performs
        no mount/privileged action. The kernel filesystem ceiling bounds all
        managed roots together, even between inventory samples.
        """
        volume = self.storage_volume
        if volume is None or not volume.is_absolute() or volume.resolve() in {
            Path('/'), Path('/tmp'), Path('/home'), Path('/workspace'), Path.home()}:
            raise PermissionError('Hard storage requires a dedicated narrow filesystem')
        if any(p.is_symlink() for p in (volume, *volume.parents)):
            raise PermissionError('Hard storage volume may not traverse symlinks')
        with mountinfo.open() as stream:
            inventory = stream.read(1024*1024+1)
        if len(inventory) > 1024*1024:
            raise PermissionError('Mount inventory exceeds the verification budget')
        matches = []
        for line in inventory.splitlines():
            left, separator, right = line.partition(' - ')
            fields = left.split()
            if not separator or len(fields) < 6 or len(right.split()) < 3:
                raise PermissionError('Malformed kernel mount inventory')
            target = re.sub(r'\\([0-7]{3})', lambda match: chr(int(match[1],8)), fields[4])
            if volume in Path(target).parents:
                raise PermissionError('Hard storage volume may not contain nested mounts')
            if Path(target) == volume:
                matches.append((right.split()[0],fields[2]))
        if len(matches) != 1 or matches[0][0] not in {'ext2','ext3','ext4','xfs','f2fs'}:
            raise PermissionError('Hard storage requires a dedicated mounted disk filesystem')
        fd = os.open(volume,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            metadata = os.fstat(fd)
            if metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
                raise PermissionError('Hard storage volume must be an owned private directory')
            device = f'{os.major(metadata.st_dev)}:{os.minor(metadata.st_dev)}'
            if matches[0][1] != device:
                raise PermissionError('Mounted filesystem device identity changed')
            with (block_devices/device/'size').open() as stream:
                sectors = stream.read(65).strip()
            if not sectors.isdecimal() or len(sectors) > 32 or not 0 < int(sectors)*512 <= self.storage_mb*1024*1024:
                raise PermissionError('Backing block device exceeds the hard storage budget')
            capacity = os.fstatvfs(fd)
            if capacity.f_frsize <= 0 or capacity.f_blocks <= 0 or capacity.f_blocks*capacity.f_frsize > self.storage_mb*1024*1024:
                raise PermissionError('Filesystem capacity exceeds the aggregate hard storage budget')
            for root in self.storage:
                if not root.is_absolute() or any(p.is_symlink() for p in (root,*root.parents)):
                    raise PermissionError('Hard storage roots must be absolute without symlinks')
                resolved = root.resolve()
                if resolved != volume and volume not in resolved.parents:
                    raise PermissionError('Every managed root must lie on the bounded filesystem')
                existing = root
                while not existing.exists():
                    existing = existing.parent
                if existing.stat().st_dev != metadata.st_dev:
                    raise PermissionError('Managed storage crosses a filesystem boundary')
        finally:
            os.close(fd)


def configured_limits() -> AggregateLimits | None:
    if os.environ.get('ACS_ENABLE_AGGREGATE_LIMITS') != '1':
        if os.environ.get('ACS_REQUIRE_HARD_STORAGE') == '1':
            raise PermissionError('Hard storage requires aggregate enforcement')
        return None
    roots = json.loads(os.environ['ACS_AGGREGATE_STORAGE_ROOTS'])
    if not isinstance(roots,list) or not all(isinstance(p,str) for p in roots):
        raise ValueError('Aggregate storage roots must be a bounded JSON path list')
    if os.environ.get('ACS_REQUIRE_HARD_STORAGE') == '1' and not os.environ.get('ACS_AGGREGATE_STORAGE_VOLUME'):
        raise PermissionError('Hard storage requires ACS_AGGREGATE_STORAGE_VOLUME')
    limits = AggregateLimits(Path(os.environ['ACS_AGGREGATE_CGROUP']),tuple(Path(p) for p in roots),
        int(os.environ.get('ACS_AGGREGATE_MEMORY_MB','8192')),
        int(os.environ.get('ACS_AGGREGATE_CPU_PERCENT','200')),
        int(os.environ.get('ACS_AGGREGATE_PIDS','256')),
        int(os.environ.get('ACS_AGGREGATE_STORAGE_MB','8192')),
        Path(os.environ['ACS_AGGREGATE_STORAGE_VOLUME']) if os.environ.get('ACS_REQUIRE_HARD_STORAGE') == '1' else None)
    if ' - cgroup2 ' not in Path('/proc/self/mountinfo').read_text():
        raise PermissionError('Aggregate enforcement requires mounted cgroup v2')
    limits.validate_kernel_contract()
    limits.check_storage()
    return limits


@contextmanager
def managed_temporary_directory(*, prefix: str):
    """Keep provider/tool scratch inside accounting when aggregate limits are on.

    This covers host-backed scratch, not sandbox tmpfs or a filesystem quota.
    The operator provisions the private scratch root; no global temp is adopted.
    """
    limits = configured_limits()
    directory = None
    if limits is not None:
        directory = Path(os.environ['ACS_AGGREGATE_SCRATCH_ROOT'])
        limits.require_accounted(directory)
        info = directory.stat()
        if not directory.is_dir() or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise PermissionError('Aggregate scratch root must be an owned private directory')
    with tempfile.TemporaryDirectory(prefix=prefix, dir=directory) as temporary:
        yield temporary


class StorageMonitor:
    """Serialize scans shared by the controller's concurrent supervisors."""
    lock = threading.Lock()
    def __init__(self, limits: AggregateLimits):
        self.limits, self.next_scan = limits, 0.

    def __call__(self, _owned=None):
        with self.lock:
            if time.monotonic() >= self.next_scan:
                self.limits.check_storage()
                self.next_scan = time.monotonic()+.1
