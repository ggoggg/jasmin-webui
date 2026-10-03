from manager.gateway import Gateway
from manager.server import API
from tests.test_selection import request
from jasmin.routing.Interceptors import StaticMTInterceptor
from jasmin.routing.Filters import TagFilter
from jasmin.routing.jasminApi import MTInterceptorScript


def test_interceptor_lifecycle_conflicts_and_validation():
    api=API(Gateway(demo=True),'testing')
    data=dict(type='Default',order=0,script="raise RuntimeError('must never run in manager')",filters=[])
    assert request(api,'interceptors/mo',method='POST',data=data)[0]==200
    assert request(api,'interceptors/mo',method='POST',data=data)[0]==400
    item=request(api,'state')[1]['interceptors']['mo'][0]
    assert item['script']==data['script']
    assert request(api,'interceptors/mo/0',method='POST',data={**data,'revision':'stale'})[0]==400
    assert request(api,'interceptors/mo/0',method='POST',data={**data,'revision':item['revision'],'script':'if : bad'})[0]==400
    assert request(api,'interceptors/mo/0',method='POST',data={**data,'revision':item['revision'],'script':'smpp_status = 0'})[0]==200
    assert request(api,'interceptors/mo/0',method='DELETE',data={'revision':item['revision']})[0]==400
    snapshot=request(api,'state')[1]
    assert request(api,'interceptors/mo',method='DELETE',data={'revision':'stale'})[0]==400
    assert request(api,'interceptors/mo',method='DELETE',data={'revision':snapshot['interceptor_revisions']['mo']})[0]==200
    assert request(api,'state')[1]['interceptors']['mo']==[]
    assert request(api,'interceptors/mt',method='POST',data={**data,'order':1})[0]==400
    assert request(api,'interceptors/mt',method='POST',data={**data,'type':'Static','order':1})[0]==400


def test_references_and_filter_preservation():
    gateway=Gateway(demo=True);api=API(gateway,'testing')
    assert request(api,'groups',method='POST',data={'gid':'group'})[0]==200
    assert request(api,'users',method='POST',data=dict(uid='user',gid='group',username='user',password='secret'))[0]==200
    assert request(api,'connectors',method='POST',data=dict(id='provider',host='localhost',username='test',password='secret'))[0]==200
    for direction,kind,value in [('mt','User','user'),('mo','Connector','provider')]:
        data=dict(type='Static',order=10,script='smpp_status = 0',filters=[{'type':kind,'value':value}])
        assert request(api,'interceptors/'+direction,method='POST',data=data)[0]==200
        state=request(api,'state')[1]
        assert state['interceptors'][direction][0]['filter_specs']==data['filters']
    assert request(api,'users/user',method='DELETE')[0]==400
    assert request(api,'connectors/provider',method='DELETE')[0]==400
    item=request(api,'state')[1]['interceptors']['mo'][0]
    assert request(api,'interceptors/mo/10',method='DELETE',data={'revision':item['revision']})[0]==200
    assert request(api,'connectors/provider',method='DELETE')[0]==200
    native=StaticMTInterceptor([TagFilter('custom')],MTInterceptorScript('smpp_status = 0'))
    gateway.router.interceptors['mt'][20]=native
    item=request(api,'state')[1]['interceptors']['mt'][0]
    assert item['editable_filters'] is False
    assert request(api,'interceptors/mt/20',method='POST',data=dict(order=20,type='Static',script='http_status = 0',preserve_filters=True,revision=item['revision']))[0]==200
    assert isinstance(gateway.router.interceptors['mt'][20].filters[0],TagFilter)
