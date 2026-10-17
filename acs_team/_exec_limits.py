"""Internal Linux child launcher; limits are applied before exec, never in threads."""

import os
import resource
import sys


def main():
    output, memory, cpu = map(int, sys.argv[1:4])
    command = sys.argv[4:]
    if not command or output < 1024 or memory < 0 or cpu < 0:
        raise SystemExit("Invalid child execution limits")
    if memory:
        resource.setrlimit(resource.RLIMIT_AS, (memory * 1024 * 1024,) * 2)
    if cpu:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
    os.execvpe(command[0], command, os.environ)


if __name__ == "__main__":
    main()
