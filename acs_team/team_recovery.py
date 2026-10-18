"""Durable team ownership and Git/SQLite crash reconciliation; never resets a user branch."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import time

from .coordination import ClaimDenied, CoordinationStore
from .db import DatabaseManager
from .evidence import EvidenceEngine
from .security import redact
from .service_lock import ServiceLock
from .supervision import identity
from .upgrade_schema import RECOVERY_SQL


def process_owner() -> dict:
    current = identity(os.getpid())
    if current is None:
        raise RuntimeError('Cannot establish controller process identity')
    return {**current.__dict__, 'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}


def owner_alive(owner: dict) -> bool:
    if owner.get('boot_id') != Path('/proc/sys/kernel/random/boot_id').read_text().strip():
        return False
    current = identity(owner['pid'])
    if current is None or current.start != owner.get('start'):
        return False
    try:
        fields = Path(f'/proc/{current.pid}/stat').read_text().rsplit(')',1)[1].split()
        return fields[0] != 'Z'
    except FileNotFoundError:
        return False


class TeamRecovery:
    def __init__(self, db: DatabaseManager, worktrees: Path, key: str):
        self.db, self.worktrees, self.key = db, worktrees.resolve(), key
        with db.connection() as con:
            for sql in RECOVERY_SQL:
                con.execute(sql)
        self.locks = db.db_path.parent/'team-locks'
        self.locks.mkdir(mode=0o700,exist_ok=True)
        if self.locks.is_symlink() or self.locks.stat().st_mode & 0o077:
            raise PermissionError('Team lock directory is not private')

    def lock(self, mission: str) -> ServiceLock:
        import hashlib
        return ServiceLock(self.locks/(hashlib.sha256(mission.encode()).hexdigest()+'.lock')).acquire()

    def begin(self, mission: str, repository: Path, *, resume=False) -> None:
        with self.db.connection() as con:
            previous = con.execute('SELECT * FROM team_runs WHERE mission=?',(mission,)).fetchone()
            if previous:
                if previous['repository'] != str(repository.resolve()):
                    raise PermissionError('Recovery repository changed')
                if not resume or previous['phase']=='ACTIVE' and owner_alive(json.loads(previous['owner'])):
                    raise PermissionError('An existing team run cannot be stolen or blindly restarted')
            con.execute('INSERT INTO team_runs VALUES (?,?,?,"ACTIVE",NULL,NULL) ON CONFLICT(mission) DO UPDATE SET owner=excluded.owner,phase="ACTIVE"',
                        (mission,str(repository.resolve()),json.dumps(process_owner())))

    def plan(self, mission: str, baseline: str, plan: dict) -> None:
        with self.db.connection() as con:
            con.execute('UPDATE team_runs SET baseline=?,plan=? WHERE mission=?',(baseline,json.dumps(plan),mission))

    def end(self, mission: str) -> None:
        with self.db.connection() as con:
            con.execute('UPDATE team_runs SET phase="FINISHED" WHERE mission=?',(mission,))

    def prepare(self, mission: str, task: str, token: int, repository: Path, branch: str,
                worktree: Path, completion: dict) -> None:
        if not branch.startswith(f'acsai/mission/{mission}') or worktree.is_symlink() or self.worktrees not in worktree.resolve().parents:
            raise PermissionError('Integration intent is outside owned mission paths')
        previous = self.git(worktree,'rev-parse','HEAD')
        value = {'repository':str(repository.resolve()),'branch':branch,'worktree':str(worktree.resolve()),
                 'previous':previous,'worker_commit':completion['commit'],'owner':process_owner()}
        with self.db.connection() as con:
            existing=con.execute('SELECT phase FROM integration_intents WHERE mission=? AND task=?',(mission,task)).fetchone()
            if existing and existing[0]=='PREPARED':
                raise PermissionError('Unreconciled integration intent')
            con.execute('INSERT INTO integration_intents VALUES (?,?,?,?,"PREPARED") ON CONFLICT(mission,task) DO UPDATE SET token=excluded.token,intent=excluded.intent,phase="PREPARED"',
                        (mission,task,token,json.dumps(value)))

    def resolved(self, mission: str, task: str, phase: str) -> None:
        if phase not in {'VERIFIED','ROLLED_BACK'}:
            raise ValueError('Invalid journal phase')
        with self.db.connection() as con:
            con.execute('UPDATE integration_intents SET phase=? WHERE mission=? AND task=?',(phase,mission,task))

    def rolled_back(self, mission: str, task: str) -> None:
        """Resolve a handled error only after proving that Git really rolled back."""
        with self.db.connection() as con:
            row = con.execute('SELECT * FROM integration_intents WHERE mission=? AND task=?',
                              (mission,task)).fetchone()
        if row is None or row['phase'] != 'PREPARED':
            return
        value = json.loads(row['intent'])
        path = Path(value['worktree'])
        self._owned_worktree(Path(value['repository']),path,value['branch'])
        if self.git(path,'rev-parse','HEAD') != value['previous']:
            raise PermissionError('Integration did not roll back; preserve journal for recovery')
        self.resolved(mission,task,'ROLLED_BACK')

    @staticmethod
    def git(path: Path, *args: str) -> str:
        return subprocess.run(['git',*args],cwd=path,check=True,capture_output=True,text=True).stdout.strip()

    def _owned_worktree(self, repository: Path, path: Path, branch: str) -> None:
        if path.is_symlink() or self.worktrees not in path.resolve().parents:
            raise PermissionError('Recovery cannot touch an unowned worktree')
        registered = self.git(repository,'worktree','list','--porcelain')
        if f'worktree {path.resolve()}\n' not in registered+'\n' or self.git(path,'symbolic-ref','--short','HEAD') != branch:
            raise PermissionError('Recovery worktree/branch identity mismatch')
        if self.git(path,'status','--porcelain'):
            raise PermissionError('Retain dirty interrupted integration for explicit review')

    def reconcile(self, mission: str, repository: Path) -> list[str]:
        from .guardian import Guardian
        Guardian(self.db,self.key).verify_corelock_safety(str(repository), [])
        store=CoordinationStore(self.db)
        recovered=[]
        with self.db.connection() as con:
            intents={r['task']:dict(r) for r in con.execute('SELECT * FROM integration_intents WHERE mission=?',(mission,))}
        for row in store.tasks(mission):
            intent=intents.get(row['task'])
            if row['state']=='INTEGRATED':
                if intent and intent['phase']=='PREPARED':
                    result = json.loads(row['result'])
                    value = json.loads(intent['intent'])
                    path = Path(value['worktree'])
                    self._owned_worktree(repository,path,value['branch'])
                    commit = result['integrated_commit_sha']
                    evidence_path = Path(result['evidence_ref'])
                    artifacts = self.worktrees.parent/'artifacts'
                    if evidence_path.is_symlink() or artifacts not in evidence_path.resolve().parents or not evidence_path.is_file() or evidence_path.stat().st_size > 1024*1024:
                        raise PermissionError('Integrated evidence path invalid')
                    evidence = json.loads(evidence_path.read_bytes())
                    if evidence.get('mission_id') != mission or evidence.get('task_id') != row['task'] or not EvidenceEngine(self.key).verify_evidence(evidence,commit):
                        raise PermissionError('Integrated evidence invalid')
                    self.git(path,'merge-base','--is-ancestor',commit,'HEAD')
                    self.resolved(mission,row['task'],'VERIFIED')
                continue
            if row['state'] not in {'RUNNING','COMPLETED','INTEGRATING'}:
                continue
            if row['expires'] > store.clock():
                raise ClaimDenied('Wait for the old claim lease to expire before recovery')
            if row['process']:
                process=json.loads(row['process'])
                if owner_alive(process):
                    descriptor=os.pidfd_open(process['pid'])
                    try:
                        if owner_alive(process):
                            signal.pidfd_send_signal(descriptor,signal.SIGTERM)
                    finally:
                        os.close(descriptor)
                    deadline=time.monotonic()+5
                    while owner_alive(process) and time.monotonic()<deadline:
                        time.sleep(.02)
                    if owner_alive(process):
                        raise PermissionError('Owned old process has not completed cleanup')
            if row['state'] in {'COMPLETED','INTEGRATING'}:
                completion=json.loads(row['result'])
                path=Path(completion['worktree'])
                self._owned_worktree(repository,path,completion['branch'])
                if self.git(path,'rev-parse','HEAD') != completion['commit']:
                    raise PermissionError('Completed worker commit changed')
                evidence_path=Path(completion['worker_evidence_ref'])
                artifacts = self.worktrees.parent/'artifacts'
                if evidence_path.is_symlink() or artifacts not in evidence_path.resolve().parents or not evidence_path.is_file() or evidence_path.stat().st_size > 1024*1024:
                    raise PermissionError('Worker evidence is outside private artifact storage')
                evidence=json.loads(evidence_path.read_bytes())
                if evidence.get('mission_id') != mission or evidence.get('task_id') != row['task'] or not EvidenceEngine(self.key).verify_evidence(evidence,completion['commit']):
                    raise PermissionError('Interrupted completion evidence invalid')
            if intent and intent['phase']=='PREPARED':
                value=json.loads(intent['intent'])
                if owner_alive(value['owner']):
                    raise PermissionError('Original integrator is still alive')
                path=Path(value['worktree'])
                self._owned_worktree(repository,path,value['branch'])
                head=self.git(path,'rev-parse','HEAD')
                if head != value['previous']:
                    parents=self.git(path,'rev-list','--parents','-n','1','HEAD').split()
                    if parents[1:] != [value['previous'],value['worker_commit']]:
                        raise PermissionError('Unexpected integration history; no reset allowed')
                    # Preserve the interrupted merge before rollback of this owned tree.
                    self.git(repository,'update-ref',f"refs/heads/acsai/recovery/{mission}/{row['task']}-{row['token']}",head)
                    self.git(path,'reset','--hard',value['previous'])
                self.resolved(mission,row['task'],'ROLLED_BACK')
            with self.db.connection() as con:
                con.execute('BEGIN IMMEDIATE')
                current=con.execute('SELECT token,state FROM coord_tasks WHERE mission=? AND task=?',(mission,row['task'])).fetchone()
                if current['token']!=row['token'] or current['state']!=row['state']:
                    raise ClaimDenied('Recovery lost its fencing comparison')
                con.execute('INSERT INTO coord_recoveries(mission,task,snapshot) VALUES (?,?,?)',
                            (mission,row['task'],json.dumps(redact(row))))
                if row['state']=='RUNNING':
                    con.execute('UPDATE coord_tasks SET state="PENDING",token=NULL,worker=NULL,expires=NULL,process=NULL,worktree=NULL,result=NULL WHERE mission=? AND task=?',
                                (mission,row['task']))
                else:
                    token=con.execute('INSERT INTO coord_tokens DEFAULT VALUES').lastrowid
                    con.execute('UPDATE coord_tasks SET state="COMPLETED",token=?,expires=?,process=NULL WHERE mission=? AND task=?',
                                (token,store.clock()+300,mission,row['task']))
            recovered.append(row['task'])
        return recovered

    def cleanup_accepted_workers(self, mission: str, repository: Path) -> list[dict]:
        """Remove clean accepted checkouts, retain their branches/evidence.

        Never force removal, prune unrelated registrations or touch failed work.
        Caller must already own the mission lock through finalization.
        """
        from .guardian import Guardian
        Guardian(self.db,self.key).verify_corelock_safety(str(repository), [])
        record = self.db.get_mission(mission)
        if not record or record['state'] != 'COMPLETED':
            raise PermissionError('Cleanup requires completed mission evidence')
        reference = Path(record['evidence_ref'] or '')
        artifacts = self.worktrees.parent/'artifacts'
        if reference.is_symlink() or artifacts not in reference.resolve().parents or not reference.is_file() or reference.stat().st_size > 1024*1024:
            raise PermissionError('Cleanup evidence unavailable')
        evidence = json.loads(reference.read_bytes())
        if evidence.get('mission_id') != mission or not EvidenceEngine(self.key).verify_evidence(evidence,record['commit_sha']):
            raise PermissionError('Cleanup evidence invalid')
        if self.git(repository,'rev-parse',record['git_branch']) != record['commit_sha']:
            raise PermissionError('Accepted branch changed; retain checkouts')
        results = []
        integration_paths = set()
        for row in CoordinationStore(self.db).tasks(mission):
            if row['state'] != 'INTEGRATED':
                raise PermissionError('Cleanup cannot discard unfinished work')
            integrated = json.loads(row['result'])
            integration_paths.add(integrated['integration_worktree'])
            completion = integrated['worker_completion']
            path = Path(completion['worktree'])
            if not path.exists():
                continue
            self._owned_worktree(repository,path,completion['branch'])
            if not completion['branch'].startswith(f'acsai/worker/{mission}/') or self.git(path,'rev-parse','HEAD') != completion['commit']:
                raise PermissionError('Worker checkout changed; retain it')
            if row['process'] and owner_alive(json.loads(row['process'])):
                raise PermissionError('Owned worker process is still alive')
            self.git(repository,'merge-base','--is-ancestor',completion['commit'],record['commit_sha'])
            self.git(repository,'worktree','remove',str(path))
            result = {'task_id':row['task'],'status':'REMOVED_CLEAN_ACCEPTED_CHECKOUT','branch_retained':completion['branch']}
            self.db.record_audit_event(mission,'retention','WORKTREE_CLEANED',result)
            results.append(result)
        for name in sorted(integration_paths):
            path = Path(name)
            if not path.exists():
                continue
            self._owned_worktree(repository,path,record['git_branch'])
            if self.git(path,'rev-parse','HEAD') != record['commit_sha']:
                raise PermissionError('Final integration checkout changed; retain it')
            self.git(repository,'worktree','remove',str(path))
            result = {'task_id':'mission-integration','status':'REMOVED_CLEAN_ACCEPTED_CHECKOUT',
                      'branch_retained':record['git_branch']}
            self.db.record_audit_event(mission,'retention','WORKTREE_CLEANED',result)
            results.append(result)
        return results
