"""Internal Linux child launcher; limits are applied before exec, never in threads."""

import resource
import sys


def main():
    output, memory, cpu = map(int, sys.argv[1:4])
    command = sys.argv[4:]
    if command[:1] == ['--aggregate']:
        import json
        from pathlib import Path
        from .aggregate_limits import AggregateLimits
        data = json.loads(command[1])
        data['cgroup'] = Path(data['cgroup'])
        data['storage'] = tuple(Path(p) for p in data['storage'])
        if data.get('storage_volume') is not None:
            data['storage_volume'] = Path(data['storage_volume'])
        if data.get('service_cgroup') is not None:
            data['service_cgroup'] = Path(data['service_cgroup'])
        AggregateLimits(**data).join_current_process()
        command = command[2:]
    expected_parent = None
    if command[:1] == ['--parent-pid']:
        if len(command) < 4 or command[2] != '--':
            raise SystemExit('Invalid parent ownership')
        expected_parent = int(command[1])
        command = command[3:]
    if not command or output < 1024 or memory < 0 or cpu < 0:
        raise SystemExit("Invalid child execution limits")
    if memory:
        resource.setrlimit(resource.RLIMIT_AS, (memory * 1024 * 1024,) * 2)
    if cpu:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
    from .process_guard import run
    raise SystemExit(run(command, expected_parent=expected_parent))


if __name__ == "__main__":
    main()
