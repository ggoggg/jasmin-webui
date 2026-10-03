import pytest
from jasmin.routing.jasminApi import Group
from manager.domain import make_user, make_connector, make_route, user_view


def test_user_quotas_and_password_redaction():
    user = make_user(dict(uid='alice',gid='clients',username='alice',password='secret',balance='12.5',submit_sm_count='100'), [Group('clients')])
    assert user_view(user)['balance'] == 12.5
    assert user_view(user)['submit_sm_count'] == 100
    assert 'password' not in user_view(user)


@pytest.mark.parametrize('rate', ['nan', 'inf', '-1'])
def test_invalid_numbers(rate):
    with pytest.raises(ValueError):
        make_connector(dict(id='provider',host='localhost',username='client',password='secret',throughput=rate))


def test_mt_failover_and_mo_http():
    order, route = make_route(dict(order=10,type='Failover',rate='0.1',connectors=[{'id':'one'},{'id':'two'}],filters=[{'type':'DestinationAddr','value':'^995'}]), 'mt', [], [], ['one','two'])
    assert [c.cid for c in route.connector] == ['one','two']
    assert route.getRate() == .1
    _, route = make_route(dict(order=0,type='Default',connectors=[{'id':'webhook','type':'http','url':'https://example.com/inbound','method':'POST'}]),'mo',[],[],[])
    assert route.connector.baseurl == 'https://example.com/inbound'


@pytest.mark.parametrize('data', [
    dict(order=1,type='Default',connectors=[{'id':'one'}]),
    dict(order=0,type='Static',connectors=[{'id':'one'}]),
    dict(order=1,type='Static',connectors=[{'id':'missing'}]),
    dict(order=1,type='Static',connectors=[{'id':'one'}],filters=[{'type':'Connector','value':'one'}]),
])
def test_invalid_routes(data):
    with pytest.raises(ValueError): make_route(data,'mt',[],[],['one'])


@pytest.mark.parametrize('key,value', [('username','a'*16), ('password','a'*9), ('password','abc\0def'), ('username','é')])
def test_connector_rejects_unencodable_bind_credentials(key, value):
    data=dict(id='provider',host='localhost',username='client',password='secret')
    data[key]=value
    with pytest.raises(ValueError, match='ASCII'):
        make_connector(data)


def test_connector_credentials_encode_at_wire_limits():
    from io import BytesIO
    from smpp.pdu.operations import BindTransceiver
    from smpp.pdu.pdu_encoding import PDUEncoder
    config=make_connector(dict(id='provider',host='localhost',username='a'*15,password='b'*8))
    encoder=PDUEncoder()
    encoded=encoder.encode(BindTransceiver(seqNum=1,system_id=config.username,password=config.password))
    decoded=encoder.decode(BytesIO(encoded))
    assert decoded.params['system_id']==b'a'*15
    assert decoded.params['password']==b'b'*8
