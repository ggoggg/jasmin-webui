import io
import json
import pytest
from twisted.web.test.requesthelper import DummyRequest
from twisted.web.server import NOT_DONE_YET
from manager.config import load_profiles
from manager.gateway import Gateway
from manager.server import API


def request(api, path, gateway=None, method='GET', data=None):
    req=DummyRequest([part.encode() for part in path.split('/')])
    req.method=method.encode()
    req.content=io.BytesIO(json.dumps(data or {}).encode())
    req._disconnected=False
    req.requestHeaders.addRawHeader(b'authorization', b'Bearer testing')
    req.requestHeaders.addRawHeader(b'x-jasmin-manager', b'1')
    if gateway is not None: req.requestHeaders.addRawHeader(b'x-jasmin-gateway', gateway.encode())
    result=api.render(req)
    body=b''.join(req.written) if result==NOT_DONE_YET else result
    return req.responseCode or 200, json.loads(body)


def test_gateway_isolation_and_discovery():
    profiles={key:dict(id=key,name=key,host='localhost',settings={'PASSWORD':'never-expose'}) for key in ('production','test')}
    api=API({key:Gateway(demo=True) for key in profiles}, 'testing', profiles, 'production')
    _,catalog=request(api,'gateways')
    assert 'PASSWORD' not in json.dumps(catalog)
    assert catalog['default']=='production'
    assert request(api,'state')[0]==400
    assert request(api,'groups',method='POST',data={'gid':'wrong'})[0]==400
    assert request(api,'groups','unknown','POST',{'gid':'wrong'})[0]==400
    assert request(api,'groups','production','POST',{'gid':'prod'})[0]==200
    assert request(api,'groups','test','POST',{'gid':'test'})[0]==200
    _,prod=request(api,'state','production')
    _,test=request(api,'state','test')
    assert prod['gateway_id']=='production' and test['gateway_id']=='test'
    assert prod['groups']==[{'gid':'prod','enabled':True}]
    assert test['groups']==[{'gid':'test','enabled':True}]
    assert request(api,'groups/prod','test','DELETE')[0]==400
    assert request(api,'persist','test','POST',{'profile':'jcli-prod'})[0]==200
    assert request(api,'state','test')[1]['persisted'] is True
    assert request(api,'state','production')[1]['persisted'] is False


def test_gateway_settings_are_captured(monkeypatch):
    monkeypatch.setenv('ROUTER_HOST','first')
    first=Gateway()
    monkeypatch.setenv('ROUTER_HOST','second')
    second=Gateway()
    assert first.settings['ROUTER_HOST']=='first'
    assert second.settings['ROUTER_HOST']=='second'


def test_named_profiles_do_not_inherit_legacy_credentials(monkeypatch):
    monkeypatch.setenv('JASMIN_GATEWAYS','production,test')
    monkeypatch.setenv('JASMIN_DEFAULT_GATEWAY','production')
    monkeypatch.setenv('ROUTER_PASSWORD','legacy-secret')
    profiles,_=load_profiles(demo=True)
    assert profiles['production']['settings']['ROUTER_PASSWORD']==''
    with pytest.raises(ValueError,match='PASSWORD'):
        load_profiles()


@pytest.mark.parametrize('value',['prod,prod','bad-name','UPPER'])
def test_invalid_profile_ids(monkeypatch,value):
    monkeypatch.setenv('JASMIN_GATEWAYS',value)
    with pytest.raises(ValueError): load_profiles(demo=True)
