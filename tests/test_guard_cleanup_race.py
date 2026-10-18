"""A scheduling pause must not turn successfully reaped work into exit 125."""
from pathlib import Path
import sys

import pytest

from acs_team.supervision import ProcessSupervisor


@pytest.mark.parametrize('relative', ['acs_team/process_guard.py', 'agpair/agpair/executors/process_guard.py'])
@pytest.mark.parametrize('worker_status', [0, 7, 125])
def test_cleanup_deadline_does_not_exit_before_reaping_ready_descendant(tmp_path, relative, worker_status):
    repository = Path(__file__).resolve().parents[1]
    target = repository / relative
    # Run an inner guard inside the real outer supervisor/subreaper. Even the
    # old broken inner guard cannot orphan its test descendants into container
    # PID 1. The injected pause occurs after a killed descendant is waitable.
    code = r'''
import importlib.util, os, signal, sys, time
spec = importlib.util.spec_from_file_location('guard_under_test', sys.argv[1])
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
original_signal = guard._signal_owned
monotonic = time.monotonic
shift = [0.0]
observed = [False]
signals = []
def scheduled_pause(root, sig):
    signals.append(int(sig))
    original_signal(root, sig)
    if sig == signal.SIGTERM:
        deadline = monotonic() + 5
        while monotonic() < deadline:
            for pid in guard._descendants(root):
                try:
                    ready = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                except ChildProcessError:
                    continue
                if ready is not None:
                    observed[0] = True
                    shift[0] = 3.0
                    return
            time.sleep(0.001)
        raise RuntimeError('Controlled scheduling did not observe a waitable child')
guard._signal_owned = scheduled_pause
guard.time.monotonic = lambda: monotonic() + shift[0]
worker = """
import os, signal
read, write = os.pipe()
pid = os.fork()
if pid == 0:
    os.close(read)
    os.setsid()
    os.write(write, b'1')
    os.close(write)
    while True: signal.pause()
os.close(write)
assert os.read(read, 1) == b'1'
os.close(read)
os._exit(0)
"""
worker = worker.replace('os._exit(0)', 'os._exit(' + sys.argv[2] + ')')
status = guard.run([sys.executable, '-c', worker])
print('CONTROLLED_WAITABLE_CHILD', observed[0], 'GUARD_RESULT', status, flush=True)
assert observed[0], 'Scheduling injection did not execute'
assert signals == [int(signal.SIGTERM)], 'Must reap a waitable child before another expensive discovery/signal pass'
raise SystemExit(status)
'''
    result = ProcessSupervisor().run([sys.executable, '-I', '-c', code, str(target), str(worker_status)], tmp_path, timeout=20)
    assert 'CONTROLLED_WAITABLE_CHILD True' in result['output'], result
    assert result['reason'] == 'completed', result
    assert result['exit_code'] == worker_status, result


@pytest.mark.parametrize('relative', ['acs_team/process_guard.py', 'agpair/agpair/executors/process_guard.py'])
def test_term_ignoring_adopted_child_is_killed_and_reaped(tmp_path, relative):
    target = Path(__file__).resolve().parents[1]/relative
    code = r'''
import importlib.util, os, signal, sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('guard_under_test',sys.argv[1])
guard=importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
original=guard._signal_owned
signals=[]
def record(root,sig):
    signals.append(int(sig))
    original(root,sig)
guard._signal_owned=record
worker="""
import os,signal,sys
from pathlib import Path
read,write=os.pipe()
pid=os.fork()
if pid==0:
    os.close(read)
    os.setsid()
    signal.signal(signal.SIGTERM,signal.SIG_IGN)
    os.write(write,b'1')
    os.close(write)
    while True: signal.pause()
os.close(write)
assert os.read(read,1)==b'1'
os.close(read)
Path(sys.argv[1]).write_text(str(pid))
os._exit(0)
"""
marker=Path(sys.argv[2])
status=guard.run([sys.executable,'-c',worker,str(marker)])
assert status==0
assert signals[0]==int(signal.SIGTERM) and int(signal.SIGKILL) in signals
try:
    os.kill(int(marker.read_text()),0)
except ProcessLookupError:
    pass
else:
    raise AssertionError('Adopted child was not reaped')
print('TERM_KILL_REAP_VERIFIED',flush=True)
'''
    result = ProcessSupervisor().run([sys.executable,'-I','-c',code,str(target),str(tmp_path/'child.pid')], tmp_path, timeout=20)
    assert result['exit_code'] == 0 and result['reason'] == 'completed', result
    assert 'TERM_KILL_REAP_VERIFIED' in result['output']
