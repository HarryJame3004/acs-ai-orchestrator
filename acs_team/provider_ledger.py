"""Durable, conservative admission for native mission calls (not dollar metering)."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import hmac
import json
import os
import secrets
from typing import Iterator
import sqlite3

from .db import DatabaseManager
from .security import redact


class ProviderInvocationBlocked(PermissionError):
    """A call is uncertain, already mutating, corrupt, or above its session budget."""


class ProviderLedger:
    def __init__(self, db: DatabaseManager, key: bytes):
        self.db, self.key = db, key
        if not key:
            raise ValueError('Provider ledger requires a host signing key')
        with self.transaction() as con:
            con.execute('''CREATE TABLE IF NOT EXISTS provider_invocations (
                invocation_id TEXT PRIMARY KEY, mission_id TEXT NOT NULL,
                worker_id TEXT NOT NULL, request_digest TEXT NOT NULL, readonly INTEGER NOT NULL,
                state TEXT NOT NULL, owner TEXT NOT NULL,
                result_json TEXT, signature TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        con = self.db.get_connection()
        try:
            con.execute('PRAGMA synchronous=FULL')
            if con.execute('PRAGMA synchronous').fetchone()[0] != 2:
                raise ProviderInvocationBlocked('Provider admission requires FULL SQLite durability')
            con.execute('BEGIN IMMEDIATE')
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    @staticmethod
    def limit(name: str, default: int, maximum: int) -> int:
        value = int(os.environ.get(name, str(default)))
        if not 1 <= value <= maximum:
            raise ProviderInvocationBlocked(f'{name} is outside its safe range')
        return value

    def signature(self, invocation: str, request: str, result: str) -> str:
        return hmac.new(self.key, (invocation+'\n'+request+'\n'+result).encode(), hashlib.sha256).hexdigest()

    def reserve(self, mission: str, worker: str, contract: str, prompt: str,
                readonly: bool) -> tuple[str, str, dict | None]:
        request = hashlib.sha256(json.dumps([mission, worker, contract, prompt, readonly],
                                            separators=(',', ':')).encode()).hexdigest()
        # An uncertain task cannot escape its reservation by changing workers,
        # contracts or instructions on recovery/failover. Readonly analysis is
        # keyed by its input; implementation is keyed by the logical task.
        logical: object = prompt
        try:
            payload = json.loads(prompt)
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            if payload.get('role') == 'implementer' and isinstance(payload.get('task_id'), str):
                logical = ['implementer', payload['task_id']]
            else:
                logical = {name:value for name,value in payload.items() if name != 'worker_id'}
        invocation = hashlib.sha256(json.dumps([mission, logical, readonly], sort_keys=True,
                                               separators=(',', ':')).encode()).hexdigest()
        owner = secrets.token_hex(16)
        per_mission = self.limit('ACS_PROVIDER_MAX_MISSION_CALLS', 16, 64)
        lifetime = self.limit('ACS_PROVIDER_MAX_TOTAL_CALLS', 64, 10000)
        with self.transaction() as con:
            row = con.execute('SELECT * FROM provider_invocations WHERE invocation_id=?', (invocation,)).fetchone()
            if row:
                if (row['state'] == 'COMPLETED' and readonly and row['readonly'] == 1
                        and row['mission_id'] == mission and row['worker_id'] == worker
                        and row['request_digest'] == request
                        and isinstance(row['result_json'], str) and isinstance(row['signature'], str)
                        and hmac.compare_digest(self.signature(invocation, request, row['result_json']), row['signature'])):
                    return invocation, '', json.loads(row['result_json'])
                raise ProviderInvocationBlocked('Existing provider invocation requires reconciliation; no automatic redispatch')
            count = con.execute('SELECT COUNT(*) FROM provider_invocations WHERE mission_id=?', (mission,)).fetchone()[0]
            total = con.execute('SELECT COUNT(*) FROM provider_invocations').fetchone()[0]
            if count >= per_mission or total >= lifetime:
                raise ProviderInvocationBlocked('Provider session budget exhausted (not a currency budget)')
            con.execute('INSERT INTO provider_invocations '
                        '(invocation_id,mission_id,worker_id,request_digest,readonly,state,owner) VALUES (?,?,?,?,?,?,?)',
                        (invocation, mission, worker, request, int(readonly), 'RESERVED', owner))
        return invocation, owner, None

    def complete(self, invocation: str, owner: str, result: dict) -> None:
        if (set(result) != {'text', 'session_id', 'worker_id', 'label'}
                or not all(isinstance(value, str) for value in result.values())
                or result['label'] not in {'CLOUD_SIMULATED', 'LOCAL_VERIFICATION_REQUIRED'}):
            raise ProviderInvocationBlocked('Invalid provider result provenance')
        data = json.dumps(result, sort_keys=True, separators=(',', ':'))
        if len(data.encode()) > 131072 or redact(result) != result:
            raise ProviderInvocationBlocked('Provider result exceeds retention policy or contains sensitive data')
        with self.transaction() as con:
            row = con.execute('SELECT worker_id,request_digest FROM provider_invocations WHERE invocation_id=?', (invocation,)).fetchone()
            if row is None or row['worker_id'] != result['worker_id']:
                raise ProviderInvocationBlocked('Provider result worker identity mismatch')
            cursor = con.execute("UPDATE provider_invocations SET state='COMPLETED',result_json=?,signature=?,"
                                 "updated_at=CURRENT_TIMESTAMP WHERE invocation_id=? AND owner=? AND state='RESERVED'",
                                 (data, self.signature(invocation, row['request_digest'], data), invocation, owner))
            if cursor.rowcount != 1:
                raise ProviderInvocationBlocked('Provider invocation ownership changed')


def provider_usage(db: DatabaseManager) -> dict:
    """Read-only counts, never prompts, cached output, auth data or fake prices."""
    with db.connection() as con:
        exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='provider_invocations'").fetchone()
        rows = con.execute('SELECT mission_id,worker_id,state,COUNT(*) AS calls '
                           'FROM provider_invocations GROUP BY mission_id,worker_id,state '
                           'ORDER BY mission_id,worker_id,state').fetchall() if exists else []
    return {'accounting':'SESSION_RESERVATIONS_NOT_CURRENCY',
            'total_reserved_calls':sum(row['calls'] for row in rows),
            'uncertain_calls':sum(row['calls'] for row in rows if row['state'] != 'COMPLETED'),
            'max_mission_calls':ProviderLedger.limit('ACS_PROVIDER_MAX_MISSION_CALLS',16,64),
            'max_total_calls':ProviderLedger.limit('ACS_PROVIDER_MAX_TOTAL_CALLS',64,10000),
            'groups':[dict(row) for row in rows]}
