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
    assert requests.get(base+'/api/state').status_code == 401
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
