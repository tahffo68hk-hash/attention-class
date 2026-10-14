"""M1 true MySQL parallel tests. Runs under existing tests/conftest.py.

Do not run on production DB: fixtures recreate hospital_test schema.
"""
from __future__ import annotations

import threading

from sqlalchemy import func, select

from app.core.errors import BizError
from app.db.session import get_engine, get_session_factory
from app.models.allocation import BedAllocation, AllocationIdempotency
from app.models.enums import AllocationStatus
from app.models.user import User
from app.services.allocation import reserve_bed
from tests.conftest import make_request


def _worker(request_id, bed_id, operator_id, key, barrier, results, index):
    db = get_session_factory()()
    try:
        operator = db.get(User, operator_id)
        barrier.wait(timeout=15)
        obj = reserve_bed(db, request_id=request_id, bed_id=bed_id,
                          operator=operator, idempotency_key=key)
        results[index] = ("OK", obj.id)
    except BizError as exc:
        results[index] = ("BIZ", exc.code, exc.status_code)
    except Exception as exc:
        results[index] = ("EXC", type(exc).__name__, str(exc)[:180])
    finally:
        db.close()


def _run_pair(request_ids, bed_ids, operator_id, keys):
    results = {}
    barrier = threading.Barrier(2)
    threads = [
        threading.Thread(target=_worker, args=(request_ids[i], bed_ids[i], operator_id,
                                               keys[i], barrier, results, i))
        for i in range(2)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in threads), f"线程未结束: {results}"
    assert len(results) == 2, results
    return results


def test_parallel_same_request_different_beds(client, ds):
    """G5: two different beds must never be reserved for the same request."""
    assert get_engine().dialect.name == 'mysql', 'This test requires real MySQL'
    req = make_request(ds, patient_name='男患者甲',department_code='CARD',seq=81)
    results=_run_pair([req,req], [ds.bed('C-W1-01'),ds.bed('C-W1-02')],
                      ds.users['nurse01'], [None,None])
    ok=[v for v in results.values() if v[0]=='OK']
    err=[v for v in results.values() if v[0]!='OK']
    assert len(ok)==1 and len(err)==1,results
    assert err[0][0]=='BIZ' and err[0][2]==409,results
    with get_session_factory()() as db:
        count=db.scalar(select(func.count(BedAllocation.id)).where(
            BedAllocation.admission_request_id==req,
            BedAllocation.status.in_([AllocationStatus.RESERVED,AllocationStatus.ADMITTED]),
        ))
        assert count==1


def test_parallel_same_key_same_request_replays(client, ds):
    """G6: two true simultaneous identical requests return exactly one allocation id."""
    assert get_engine().dialect.name == 'mysql'
    req = make_request(ds, patient_name='男患者甲',department_code='CARD',seq=82)
    bed_id = ds.bed('C-W1-01')
    results=_run_pair([req,req],[bed_id,bed_id],ds.users['nurse01'],
                      ['same-key-retry-0001','same-key-retry-0001'])
    assert all(v[0]=='OK' for v in results.values()),results
    assert results[0][1]==results[1][1],results
    with get_session_factory()() as db:
        assert db.scalar(select(func.count(AllocationIdempotency.id)))==1
        assert db.scalar(select(func.count(BedAllocation.id)))==1


def test_sequential_key_payload_mismatch_returns_409(client,ds,nurse_headers):
    req = make_request(ds, patient_name='男患者甲',department_code='CARD',seq=83)
    headers = {**nurse_headers, 'Idempotency-Key':'same-key-different-payload'}
    one=client.post('/api/v1/allocations',json={
        'admission_request_id':req,'bed_id':ds.bed('C-W1-01')},headers=headers)
    assert one.status_code==201,one.text
    two=client.post('/api/v1/allocations',json={
        'admission_request_id':req,'bed_id':ds.bed('C-W1-02')},headers=headers)
    assert two.status_code==409,two.text
    assert two.json()['code']=='IDEMPOTENCY_KEY_CONFLICT'


def test_same_key_same_payload_api_replays(client,ds,nurse_headers):
    req=make_request(ds,patient_name='男患者甲',department_code='CARD',seq=84)
    headers={**nurse_headers,'Idempotency-Key':'same-key-api-replay-0001'}
    body={'admission_request_id':req,'bed_id':ds.bed('C-W1-01')}
    a=client.post('/api/v1/allocations',json=body,headers=headers)
    b=client.post('/api/v1/allocations',json=body,headers=headers)
    assert (a.status_code,b.status_code)==(201,201),(a.text,b.text)
    assert a.json()['id']==b.json()['id']


def test_reassign_api_moves_reserved_atomically(client,ds,nurse_headers):
    req=make_request(ds,patient_name='男患者甲',department_code='CARD',seq=85)
    one=client.post('/api/v1/allocations',json={
        'admission_request_id':req,'bed_id':ds.bed('C-W1-01')},headers=nurse_headers)
    assert one.status_code==201,one.text
    moved=client.post(f"/api/v1/allocations/{one.json()['id']}/reassign",
        json={'new_bed_id':ds.bed('C-W1-02'),'reason':'人工调整'},headers=nurse_headers)
    assert moved.status_code==201,moved.text
    assert moved.json()['bed_id']==ds.bed('C-W1-02')
    with get_session_factory()() as db:
        assert db.scalar(select(func.count(BedAllocation.id)).where(
            BedAllocation.admission_request_id==req,
            BedAllocation.status.in_([AllocationStatus.RESERVED,AllocationStatus.ADMITTED])
        ))==1
