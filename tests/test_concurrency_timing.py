import asyncio
import json
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from app import config, store, settings_store
from app.model_queue import Gate, gate_for
from app.provider import ChatModel, ProviderError
from app.telemetry import Telemetry


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DB', tmp_path / 'research.sqlite3')
    monkeypatch.setattr(settings_store, 'SETTINGS_FILE', tmp_path / 'settings.json')
    monkeypatch.setattr(config, 'API_KEY', 'test-key')
    store.init()


def profile(limit=1):
    pid = settings_store.save_profile({'name':'Test', 'model':'mock', 'base_url':'https://mock.invalid',
        'api_key':'test-key', 'provider':'openai', 'concurrency':limit})
    return settings_store.to_model(settings_store.load()['profiles'][pid])


def run():
    return store.new_run(store.new_conversation(), 'test task', config_snapshot={})


def model(settings, handler, role='main', observer=None):
    return ChatModel(settings, role, observer, httpx.AsyncClient(base_url='https://mock.invalid/',transport=httpx.MockTransport(handler)))


def reply(text='ok'):
    return httpx.Response(200,json={'choices':[{'message':{'role':'assistant','content':text},'finish_reason':'stop'}],
        'usage':{'prompt_tokens':10,'completion_tokens':2,'total_tokens':12}})


async def eventually(predicate):
    async def wait():
        while not predicate(): await asyncio.sleep(0)
    await asyncio.wait_for(wait(), 3)


@pytest.mark.parametrize('invalid', [0,-1,True,1.5,'2',None])
def test_concurrency_rejects_invalid_values_at_api_and_store(invalid):
    from app.main import app
    p={'name':'Test','base_url':'https://mock.invalid','model':'mock','concurrency':invalid}
    with pytest.raises(ValueError,match='正整数'):settings_store.save_profile(p)
    with TestClient(app) as client:
        assert client.post('/api/settings/profiles',json=p).status_code == 422


def test_concurrency_saved_public_and_snapshot_but_not_provider_parameters():
    p=profile(10000)
    assert p.concurrency == 10000
    assert p.public()['concurrency'] == 10000
    assert 'concurrency' not in p.generation()
    doc=settings_store.load()
    assert doc['profiles'][p.profile_id]['concurrency']==10000
    snap=config.snapshot(models={'main':p,'summary':p})
    assert snap['main_model']['concurrency']==10000
    assert 'test-key' not in json.dumps(snap)
    del doc['profiles'][p.profile_id]['concurrency']
    settings_store.write(doc)
    assert settings_store.public()['profiles'][p.profile_id]['concurrency']==1
    assert settings_store.public()['templates']['deepseek']['concurrency']==1


async def test_same_profile_roles_share_fifo_limit_and_cancelled_queue_does_not_count():
    p=profile(1);release=asyncio.Event();entered=[]
    async def handler(request):
        text=json.loads(request.content)['messages'][0]['content'];entered.append(text)
        assert 'concurrency' not in json.loads(request.content)
        await release.wait();return reply(text)
    observers=[Telemetry(run()) for _ in range(4)]
    clients=[model(p,handler,'main' if i%2==0 else 'summary',observers[i]) for i in range(4)]
    tasks=[]
    try:
        for i,c in enumerate(clients):
            tasks.append(asyncio.create_task(c.complete([{'role':'user','content':str(i)}])))
            await asyncio.sleep(0)
        await eventually(lambda:len(gate_for(p).waiters)==3)
        assert entered==['0']
        assert observers[1].usage['summary']['calls']==0
        tasks[1].cancel()
        with pytest.raises(asyncio.CancelledError):await tasks[1]
        assert not store.requests(observers[1].rid)
        assert 'model_queue_cancelled' in [e['kind'] for e in store.events(observers[1].rid)]
        release.set()
        await asyncio.gather(tasks[0],tasks[2],tasks[3])
        assert entered==['0','2','3']
        assert gate_for(p).active==0 and not gate_for(p).waiters
        assert observers[2].usage['main']['calls']==1
    finally:
        for t in tasks:t.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        await asyncio.gather(*(c.close() for c in clients))


async def test_limit_and_different_profiles_run_independently():
    p,q=profile(2),profile(1);release=asyncio.Event();entered=[];active=0;peak=0
    async def handler(request):
        nonlocal active,peak
        entered.append(json.loads(request.content)['messages'][0]['content'])
        active+=1;peak=max(active,peak)
        try:await release.wait();return reply()
        finally:active-=1
    clients=[model(p,handler),model(p,handler),model(p,handler),model(q,handler)]
    tasks=[asyncio.create_task(c.complete([{'role':'user','content':str(i)}])) for i,c in enumerate(clients)]
    try:
        await eventually(lambda:len(entered)==3)
        assert entered==['0','1','3'] and peak==3
        assert len(gate_for(p).waiters)==1
        release.set();await asyncio.gather(*tasks)
        assert entered==['0','1','3','2']
    finally:
        for t in tasks:t.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        await asyncio.gather(*(c.close() for c in clients))


async def test_saving_live_limit_wakes_waiters_without_replacing_model_snapshots():
    p=profile(1);gate=gate_for(p)
    await gate.acquire()
    second=asyncio.create_task(gate.acquire());third=asyncio.create_task(gate.acquire())
    await eventually(lambda:len(gate.waiters)==2)
    await asyncio.to_thread(settings_store.save_profile,{'id':p.profile_id,'concurrency':2})
    await asyncio.wait_for(second,2)
    assert p.concurrency==1 and gate.active==2 and not third.done()
    await asyncio.to_thread(settings_store.save_profile,{'id':p.profile_id,'concurrency':1})
    await eventually(lambda:gate.limit==1)
    gate.release();await asyncio.sleep(0)
    assert not third.done()
    gate.release();await asyncio.wait_for(third,2)
    gate.release()
    assert gate_for(p) is gate and gate.limit==1 and gate.active==0


async def test_cancel_between_grant_and_resume_releases_slot():
    gate=Gate(1);await gate.acquire()
    pending=asyncio.create_task(gate.acquire());await asyncio.sleep(0)
    gate.release();pending.cancel()
    with pytest.raises(asyncio.CancelledError):await pending
    assert gate.active==0
    await asyncio.wait_for(gate.acquire(),1);gate.release()


async def test_retry_releases_slot_and_cancel_inflight_also_releases():
    p=replace(profile(),retry_delay=.02,request_attempts=2)
    entered=[];first=asyncio.Event();release=asyncio.Event()
    async def handler(request):
        value=json.loads(request.content)['messages'][0]['content'];entered.append(value)
        if value=='a' and entered.count('a')==1:
            first.set();await release.wait();return httpx.Response(503,json={'error':{'message':'retry'}})
        return reply()
    a,b=model(p,handler),model(p,handler)
    ta=asyncio.create_task(a.complete([{'role':'user','content':'a'}]));await first.wait()
    tb=asyncio.create_task(b.complete([{'role':'user','content':'b'}]));await asyncio.sleep(0);release.set()
    await asyncio.gather(ta,tb)
    assert entered==['a','b','a'] and gate_for(p).active==0
    await a.close();await b.close()
    active=asyncio.Event()
    async def stuck(_):active.set();await asyncio.Event().wait()
    c=model(p,stuck);task=asyncio.create_task(c.complete([{'role':'user','content':'cancel'}]))
    await active.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert gate_for(p).active==0
    await c.close()
    async def invalid(_):return httpx.Response(200,json={'choices':[]})
    c=model(p,invalid)
    with pytest.raises(ProviderError):await c.complete([])
    assert gate_for(p).active==0
    await c.close()


@pytest.mark.parametrize('status',['completed','failed','cancelled','incomplete'])
def test_terminal_time_frozen_and_live_start_saved(status,monkeypatch):
    monkeypatch.setattr(store.time,'time',lambda:100.)
    rid=run();first=store.get_run(rid)
    assert first['started_at']==100 and first['finished_at'] is None and first['duration_seconds'] is None
    monkeypatch.setattr(store.time,'time',lambda:145.5)
    store.update(rid,status=status)
    monkeypatch.setattr(store.time,'time',lambda:200.)
    store.update(rid,status=status,usage={'main':{'calls':3}})
    saved=store.get_run(rid)
    assert saved['finished_at']==145.5 and saved['duration_seconds']==45.5
    latest=store.conversations()[0]
    assert latest['latest_status']==status and latest['finished_at']==145.5


def test_legacy_and_abrupt_restart_do_not_invent_finish_times():
    rid=run()
    with store.connect() as db:db.execute('UPDATE runs SET started_at=NULL WHERE id=?',(rid,))
    store.init()
    saved=store.get_run(rid)
    assert saved['status']=='interrupted'
    assert saved['started_at']==saved['created'] and saved['finished_at'] is None and saved['duration_seconds'] is None
    store.init()
    assert store.get_run(rid)==saved


async def test_two_conversations_run_simultaneously_and_cancel_independently(monkeypatch):
    from app import main
    release=asyncio.Event();entered=set()
    async def fake_research(rid,**kwargs):
        entered.add(rid)
        try:
            await release.wait()
            store.update(rid,status='completed',answer=store.get_run(rid)['question'])
        except asyncio.CancelledError:
            store.update(rid,status='cancelled');raise
    monkeypatch.setattr(main,'research',fake_research)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://testserver') as c:
        cids=[(await c.post('/api/conversations')).json()['id'] for _ in range(2)]
        runs=[(await c.post(f'/api/conversations/{cid}/runs',json={'question':f'question {i}'})).json() for i,cid in enumerate(cids)]
        await eventually(lambda:len(entered)==2)
        assert all(r['started_at'] and r['finished_at'] is None for r in runs)
        assert (await c.post(f'/api/conversations/{cids[0]}/runs',json={'question':'overlap'})).status_code==409
        listing=(await c.get('/api/conversations')).json()
        assert sum(r['latest_status']=='running' for r in listing)==2
        await c.post(f"/api/runs/{runs[0]['id']}/cancel")
        assert store.get_run(runs[0]['id'])['status']=='cancelled'
        assert store.get_run(runs[1]['id'])['status']=='running'
        assert store.get_run(runs[0]['id'])['finished_at'] is not None
        release.set();await asyncio.gather(*list(main.TASKS.values()),return_exceptions=True)
        assert store.get_run(runs[1]['id'])['answer']=='question 1'
        assert store.get_run(runs[1]['id'])['finished_at'] is not None


async def test_cancel_before_coroutine_start_still_sets_end_time():
    from app.main import task_finished, TASKS
    rid=run()
    async def never():raise AssertionError('Should not start')
    task=asyncio.create_task(never());TASKS[rid]=task;task.add_done_callback(lambda t:task_finished(rid,t))
    task.cancel();await asyncio.gather(task,return_exceptions=True)
    assert store.get_run(rid)['status']=='cancelled'
    assert store.get_run(rid)['finished_at'] is not None and rid not in TASKS


async def test_setup_failure_cannot_leave_run_running():
    from app.main import task_finished, TASKS
    rid=run()
    async def fail():raise RuntimeError('private provider details')
    task=asyncio.create_task(fail());TASKS[rid]=task;task.add_done_callback(lambda t:task_finished(rid,t))
    await asyncio.gather(task,return_exceptions=True)
    saved=store.get_run(rid)
    assert saved['status']=='failed' and saved['finished_at'] is not None
    assert 'private' not in saved['error'] and rid not in TASKS


def test_old_client_update_preserves_saved_concurrency():
    from app.main import app
    p=profile(7)
    with TestClient(app) as c:
        response=c.post('/api/settings/profiles',json={'id':p.profile_id,'name':'Renamed','base_url':p.base_url,'model':p.model})
        assert response.status_code==200
        assert response.json()['settings']['profiles'][p.profile_id]['concurrency']==7
