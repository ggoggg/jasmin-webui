import os
import socket
import subprocess
import sys
import time
import pytest
import requests


@pytest.fixture(scope='module')
def app():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    token='test-admin-token-123456789012345'
    process=subprocess.Popen([sys.executable,'-m','manager.server','--demo','--port',str(port)],env={**os.environ,'MANAGER_TOKEN':token},stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    base=f'http://127.0.0.1:{port}'
    for _ in range(100):
        try:
            requests.get(base,timeout=.2);break
        except requests.ConnectionError: time.sleep(.05)
    else:
        process.terminate()
        raise RuntimeError(process.communicate(timeout=5))
    yield base, {'Authorization':'Bearer '+token,'X-Jasmin-Manager':'1'}
    process.terminate();process.wait(timeout=5)


def test_auth_and_request_protection(app):
    base, headers=app
    assert requests.get(base+'/api/state').json()['can_edit'] is False
    assert requests.get(base+'/api/state',headers=headers).json()['can_edit'] is True
    assert requests.post(base+'/api/groups',headers={'Authorization':headers['Authorization']},json={'gid':'blocked'}).status_code == 403
    assert requests.post(base+'/api/groups',headers=headers,json=[]).status_code == 400
    response=requests.get(base)
    assert response.status_code == 200
    assert "frame-ancestors 'none'" in response.headers['Content-Security-Policy']


def test_management_lifecycle(app):
    base, headers=app
    def call(path, data=None, method='POST', expected=200):
        response=requests.request(method,base+'/api/'+path,headers=headers,json=data,timeout=5)
        assert response.status_code == expected, response.text
        return response.json()
    call('groups',{'gid':'clients'})
    call('users',{'uid':'alice','gid':'clients','username':'alice','password':'secret','balance':100})
    call('groups/clients',method='DELETE',expected=400)
    call('connectors',{'id':'carrier','host':'localhost','username':'client','password':'secret'})
    call('connectors/carrier/start')
    call('routes/mt',{'order':0,'type':'Default','connectors':[{'id':'carrier'}],'rate':.02})
    call('routes/mo',{'order':10,'type':'Static','connectors':[{'id':'hook','type':'http','url':'https://example.com/inbound'}],'filters':[{'type':'Connector','value':'carrier'}]})
    call('connectors/carrier',method='DELETE',expected=400)
    call('routes/mt',{'order':0,'type':'Default','connectors':[{'id':'carrier'}]},expected=400)
    snapshot=call('state',method='GET')
    assert snapshot['connectors'][0]['service_status'] == 1
    assert snapshot['users'][0]['balance'] == 100
    assert 'password' not in str(snapshot)
    assert snapshot['persisted'] is False
    anonymous=requests.get(base+'/api/state',timeout=5).json()
    assert anonymous == {**snapshot, 'can_edit': False}
    # Read requests must never dispatch mutations, even with a valid token.
    for read_headers in ({}, headers):
        assert requests.get(base+'/api/connectors/carrier/stop',headers=read_headers,timeout=5).status_code == 404
    assert call('state',method='GET')['connectors'][0]['service_status'] == 1
    call('persist',{'profile':'jcli-prod'})
    assert call('state',method='GET')['persisted'] is True
    call('users/alice/quotas',{'balance':'25','submit_sm_count':'','http_throughput':3})
    assert call('state',method='GET')['users'][0]['balance'] == 25
    call('users/alice/quotas',{'balance':'NaN'},expected=400)
    call('users/alice/disable')
    assert call('state',method='GET')['users'][0]['enabled'] is False
    for path in ['routes/mt/0','routes/mo/10','users/alice','groups/clients','connectors/carrier']:
        call(path,method='DELETE')
    snapshot=call('state',method='GET')
    assert snapshot['users'] == snapshot['groups'] == snapshot['connectors'] == []


@pytest.mark.parametrize('path,method', [
 ('groups','POST'),('users','POST'),('connectors','POST'),('persist','POST'),
 ('users/any/edit','POST'),('users/any/quotas','POST'),('users/any/enable','POST'),('users/any/disable','POST'),
 ('groups/any/enable','POST'),('groups/any/disable','POST'),('connectors/any/start','POST'),('connectors/any/stop','POST'),('connectors/any/edit','POST'),
 ('routes/mt','POST'),('routes/mo','POST'),('routes/mt/0','DELETE'),('routes/mo/0','DELETE'),
 ('interceptors/mt','POST'),('interceptors/mo','POST'),('interceptors/mt/0','POST'),('interceptors/mo/0','POST'),
 ('interceptors/mt','DELETE'),('interceptors/mo','DELETE'),('interceptors/mt/0','DELETE'),('interceptors/mo/0','DELETE'),
 ('users/any','DELETE'),('groups/any','DELETE'),('connectors/any','DELETE'),
])
@pytest.mark.parametrize('auth', ['', 'Bearer incorrect-token'])
def test_all_mutations_require_token(app,path,method,auth):
    base,_=app
    response=requests.request(method,base+'/api/'+path,headers={'X-Jasmin-Manager':'1','Authorization':auth},json={},timeout=5)
    assert response.status_code==401


def test_anonymous_fields_match_admin_without_secrets(app):
    base,headers=app
    assert requests.get(base+'/api/gateways').status_code==200
    anonymous=requests.get(base+'/api/state').json()
    admin=requests.get(base+'/api/state',headers=headers).json()
    assert anonymous.pop('can_edit') is False
    assert admin.pop('can_edit') is True
    assert anonymous==admin
    assert requests.get(base+'/api/session',headers={'Authorization':'Bearer wrong'}).json()=={'can_edit':False}
