"""Real child exit held waitable while the supervisor resumes after descheduling."""
import os
import sys
from types import SimpleNamespace

import pytest

from acs_team.supervision import ProcessSupervisor


@pytest.mark.parametrize('status', [0, 7, 125])
def test_completed_child_is_repolled_after_monitor_before_timeout(tmp_path, monkeypatch, status):
    from acs_team import supervision
    clock = [0.]
    monkeypatch.setattr(supervision, 'time', SimpleNamespace(monotonic=lambda:clock[0]))
    observed = []
    def monitor(owned):
        # Observe actual guard completion WITHOUT reaping its exit status. The
        # supervisor's first poll was running; it must refresh that observation.
        exited = os.waitid(os.P_PID, owned.pid, os.WEXITED | os.WNOWAIT)
        assert exited.si_pid == owned.pid and exited.si_status == status
        observed.append(owned.pid)
        clock[0] = 10.
    result = ProcessSupervisor().run([sys.executable, '-c', f'raise SystemExit({status})'],
                                     tmp_path, timeout=5, monitor=monitor)
    assert len(observed) == 1
    assert result['exit_code'] == status
    assert result['reason'] == 'completed'
