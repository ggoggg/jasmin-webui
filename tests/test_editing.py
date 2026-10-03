from manager.gateway import Gateway
from manager.server import API
from tests.test_selection import request


def setup():
    gateway=Gateway(demo=True);api=API(gateway,'testing')
    request(api,'groups',method='POST',data={'gid':'group'})
    request(api,'groups',method='POST',data={'gid':'second'})
    request(api,'users',method='POST',data=dict(uid='alice',gid='group',username='alice',password='secret',balance=42))
    request(api,'connectors',method='POST',data=dict(id='provider',host='localhost',username='client',password='secret'))
    return gateway,api


def test_user_edit_preserves_credentials_and_quotas():
    gateway,api=setup();user=gateway.router.users['alice']
    user.mt_credential.setAuthorization('http_send',False)
    user.enabled=False;password=user.password
    snapshot=request(api,'state')[1];revision=snapshot['users'][0]['revision']
    data=dict(username='renamed',gid='second',password='',revision=revision)
    assert request(api,'users/alice/edit',method='POST',data=data)[0]==200
    updated=gateway.router.users['alice']
    assert updated.password==password and updated.enabled is False
    assert updated.group.gid=='second' and updated.username=='renamed'
    assert updated.mt_credential.getQuota('balance')==42
    assert updated.mt_credential.getAuthorization('http_send') is False
    assert request(api,'users/alice/edit',method='POST',data=data)[0]==400
    data['revision']=request(api,'state')[1]['users'][0]['revision'];data['password']='newpass'
    assert request(api,'users/alice/edit',method='POST',data=data)[0]==200
    assert gateway.router.users['alice'].password!=password


def test_connector_edit_preserves_advanced_settings_and_routes():
    gateway,api=setup();original=gateway.smpp.configs['provider']
    original.enquireLinkTimerSecs=75;password=original.password
    request(api,'routes/mt',method='POST',data=dict(type='Default',order=0,connectors=[{'id':'provider'}]))
    revision=request(api,'state')[1]['connectors'][0]['revision']
    data=dict(host='new.example.com',port=2776,username='newid',password='',throughput=12,bindOperation='receiver',revision=revision)
    request(api,'connectors/provider/start',method='POST')
    assert request(api,'connectors/provider/edit',method='POST',data=data)[0]==400
    request(api,'connectors/provider/stop',method='POST')
    assert request(api,'connectors/provider/edit',method='POST',data=data)[0]==200
    updated=gateway.smpp.configs['provider']
    assert updated.host=='new.example.com' and updated.enquireLinkTimerSecs==75
    assert updated.password==password and updated.id=='provider'
    assert gateway.router.routes['mt'][0].connector.cid=='provider'
    assert request(api,'connectors/provider/edit',method='POST',data=data)[0]==400


def test_connector_restore_on_rejected_replacement():
    gateway,api=setup();original=gateway.smpp.configs['provider']
    data=dict(host='rejected.example.com',port=2775,username='client',password='',throughput=10,bindOperation='transceiver',revision=request(api,'state')[1]['connectors'][0]['revision'])
    real_add=gateway.smpp.add
    gateway.smpp.add=lambda config: False if config.host=='rejected.example.com' else real_add(config)
    code,result=request(api,'connectors/provider/edit',method='POST',data=data)
    assert code==502 and 'restored' in result['error']
    assert gateway.smpp.configs['provider'].host==original.host


def test_reuse_filters_and_direction_validation():
    gateway,api=setup()
    request(api,'interceptors/mt',method='POST',data=dict(type='Static',order=10,script='smpp_status = 0',filters=[{'type':'User','value':'alice'}]))
    filters=request(api,'state')[1]['filters'];assert len(filters)==1
    data=dict(type='Static',order=5,connectors=[{'id':'provider'}],filters=[{'type':'Existing','value':filters[0]['id']}])
    assert request(api,'routes/mt',method='POST',data=data)[0]==200
    assert gateway.router.routes['mt'][5].filters[0].user.uid=='alice'
    data['connectors']=[{'type':'http','id':'webhook','url':'https://example.com/inbound'}]
    assert request(api,'routes/mo',method='POST',data=data)[0]==400
    data['filters'][0]['value']='missing'
    assert request(api,'routes/mt',method='POST',data=data)[0]==400
