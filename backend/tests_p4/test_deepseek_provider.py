"""Mock-only DeepSeek tests: never call paid API."""
import json
import httpx
import pytest
from app.core.config import settings
from app.core.errors import BizError
from app.services import deepseek_provider as ds

@pytest.fixture(autouse=True)
def defaults(monkeypatch):
    for k,v in {'DEEPSEEK_EXTERNAL_ENABLED':False,'DEEPSEEK_API_KEY':'','DEEPSEEK_MODEL':'deepseek-flash',
                'DEEPSEEK_INPUT_MISS_CNY_PER_M':None,'DEEPSEEK_INPUT_HIT_CNY_PER_M':None,
                'DEEPSEEK_OUTPUT_CNY_PER_M':None}.items():monkeypatch.setattr(settings,k,v)

def enable(monkeypatch):
    monkeypatch.setattr(settings,'DEEPSEEK_EXTERNAL_ENABLED',True)
    monkeypatch.setattr(settings,'DEEPSEEK_API_KEY','fake-secret')

def envelope(content=None, reason='stop', usage=None):
    return {'model':'deepseek-flash','choices':[{'finish_reason':reason,'message':{'content':content if content is not None else json.dumps({'explanation':'依据原评分做解释，需人工复核','cautions':['仅供模拟']},ensure_ascii=False)}}],
            'usage': usage or {'prompt_tokens':100,'completion_tokens':30,'prompt_cache_hit_tokens':20}}

def test_offline_by_default():
    calls=[]
    with pytest.raises(BizError) as e:
        ds.generate('bed',{},transport=httpx.MockTransport(lambda r:calls.append(r)))
    assert e.value.status_code==403 and calls==[]

def test_official_endpoint_payload_and_usage(monkeypatch):
    enable(monkeypatch); calls=[]
    def handler(req):
        calls.append(req)
        body=json.loads(req.content)
        assert str(req.url)==ds.DEEPSEEK_CHAT_URL
        assert req.headers['Authorization']=='Bearer fake-secret'
        assert body['model']=='deepseek-flash'
        assert body['thinking']=={'type':'disabled'}
        assert body['response_format']=={'type':'json_object'}
        assert json.loads(body['messages'][1]['content'])=={'final_score':88,'priority_rank':5,'kind':'bed_explanation','teaching_only':True}
        return httpx.Response(200,json=envelope())
    result=ds.generate('bed',{'final_score':88,'priority_rank':5},transport=httpx.MockTransport(handler))
    assert len(calls)==1 and result.model=='deepseek-flash' and result.usage['prompt_tokens']==100
    assert result.cost_estimate_cny is None

def test_plan_sends_aggregates_only(monkeypatch):
    enable(monkeypatch)
    payload={'request_count':4,'candidate_edges':5,'optimized':{'admitted':4,'method':'exact_min_cost_flow'}}
    def handler(req):
        assert json.loads(json.loads(req.content)['messages'][1]['content'])=={**payload,'kind':'aggregate_bed_allocation_preview','teaching_only':True}
        return httpx.Response(200,json=envelope())
    assert ds.generate('plan',payload,transport=httpx.MockTransport(handler)).explanation

@pytest.mark.parametrize('content,finish', [('', 'stop'), ('[]','stop'),('{"explanation":"ok"}','stop'),
                ('{"explanation":"ok","cautions":"bad"}','stop'),
                ('{"explanation":"ok","cautions":[]}','length')])
def test_invalid_structured_response(monkeypatch,content,finish):
    enable(monkeypatch)
    with pytest.raises(BizError) as e:
        ds.generate('bed',{'final_score':70}, transport=httpx.MockTransport(
            lambda req:httpx.Response(200,json=envelope(content,finish))))
    assert e.value.status_code==502

@pytest.mark.parametrize('status', [401,402,429,503])
def test_upstream_errors_redact_provider_body(monkeypatch,status):
    enable(monkeypatch)
    with pytest.raises(BizError) as e:
        ds.generate('bed',{},transport=httpx.MockTransport(
            lambda req:httpx.Response(status,text='Authorization Bearer SENSITIVE-SECRET')))
    assert e.value.status_code in (502,503) and 'SENSITIVE' not in str(e.value)

def test_no_automatic_retry_on_timeout(monkeypatch):
    enable(monkeypatch);seen=[]
    def handler(req):
        seen.append(req)
        raise httpx.ReadTimeout('provider secrets')
    with pytest.raises(BizError) as e:
        ds.generate('bed',{},transport=httpx.MockTransport(handler))
    assert e.value.status_code==502 and len(seen)==1

def test_cost_estimate_configuration(monkeypatch):
    enable(monkeypatch)
    for k,v in {'DEEPSEEK_INPUT_MISS_CNY_PER_M':2.,'DEEPSEEK_INPUT_HIT_CNY_PER_M':0.04,
                'DEEPSEEK_OUTPUT_CNY_PER_M':8.}.items():monkeypatch.setattr(settings,k,v)
    usage={'prompt_tokens':1000,'prompt_cache_hit_tokens':800,'completion_tokens':200}
    out=ds.generate('bed',{},transport=httpx.MockTransport(
        lambda req:httpx.Response(200,json=envelope(usage=usage))))
    assert out.cost_estimate_cny==pytest.approx((200*2+800*0.04+200*8)/1e6)

def test_invalid_model_and_oversize_fail_before_outbound(monkeypatch):
    enable(monkeypatch);calls=[]
    transport=httpx.MockTransport(lambda req:calls.append(req))
    monkeypatch.setattr(settings,'DEEPSEEK_MODEL','not-deepseek')
    with pytest.raises(BizError):ds.generate('bed',{},transport=transport)
    monkeypatch.setattr(settings,'DEEPSEEK_MODEL','deepseek-flash')
    with pytest.raises(BizError):ds.generate('bed',{'x':'z'*10000},transport=transport)
    assert calls==[]

@pytest.mark.parametrize('kind,content', [
    ('bed', {'final_score': 85, 'patient_name': 'secret'}),
    ('bed', {'final_score': 90, 'bed_type': 'BED-009'}),
    ('bed', {'score_dimensions': [{'key': 'patient_name', 'raw_score': 30, 'contribution': 10}]}),
    ('plan', {'request_count': 2, 'admission_request_ids': [123, 124]}),
    ('plan', {'optimized': {'admitted': 2, 'patient_id': 123}}),
])
def test_sensitive_or_unknown_fields_blocked_before_network(monkeypatch, kind, content):
    enable(monkeypatch); calls=[]
    with pytest.raises(BizError) as e:
        ds.generate(kind, content, transport=httpx.MockTransport(lambda req:calls.append(req)))
    assert e.value.status_code==422 and not calls


# --------------------------------------------------------------------------- #
# provider 响应 id 解析（对账用）
# --------------------------------------------------------------------------- #
def test_request_id_parsed_when_present(monkeypatch):
    enable(monkeypatch)
    env={**envelope(),'id':'chatcmpl-abc-123_XYZ.9'}
    out=ds.generate('bed',{},transport=httpx.MockTransport(lambda req:httpx.Response(200,json=env)))
    assert out.request_id=='chatcmpl-abc-123_XYZ.9'

def test_request_id_missing_is_none_and_does_not_fail(monkeypatch):
    enable(monkeypatch)
    env=dict(envelope()); env.pop('id',None)
    out=ds.generate('bed',{},transport=httpx.MockTransport(lambda req:httpx.Response(200,json=env)))
    assert out.request_id is None and out.explanation

@pytest.mark.parametrize('raw', [
    '', ' ', 123, None, {'a':1}, ['x'],
    'has space', 'newline\nhere', 'Bearer sk-live-secret',   # 空格/换行/密钥形态一律拒绝
    'x'*129,                                                  # 超长拒绝
])
def test_unsafe_request_id_dropped(monkeypatch, raw):
    enable(monkeypatch)
    env={**envelope(),'id':raw}
    out=ds.generate('bed',{},transport=httpx.MockTransport(lambda req:httpx.Response(200,json=env)))
    assert out.request_id is None

def test_unsafe_request_id_never_leaks_into_result(monkeypatch):
    """把密钥塞进 id 时，绝不能出现在返回对象里。"""
    enable(monkeypatch)
    leak='sk-LIVE-SECRET-TOKEN-9999'
    env={**envelope(),'id':f'Bearer {leak}'}
    out=ds.generate('bed',{},transport=httpx.MockTransport(lambda req:httpx.Response(200,json=env)))
    assert out.request_id is None and leak not in repr(out)
