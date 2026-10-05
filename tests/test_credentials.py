import pytest
from tests.test_editing import setup
from tests.test_selection import request


def edit(api, patch, revision=None):
    user=request(api,'state')[1]['users'][0]
    return request(api,'users/alice/edit',method='POST',data=dict(username='alice',gid='group',password='',revision=revision or user['revision'],credentials=patch))


def test_full_credentials_roundtrip():
    gateway,api=setup()
    view=request(api,'state')[1]['users'][0]['credentials']
    assert len(view['mt_messaging_cred']['authorization'])==13
    assert len(view['mt_messaging_cred']['valuefilter'])==5
    patch={'mt_messaging_cred': {
        'authorization':{key:False for key in view['mt_messaging_cred']['authorization']},
        'valuefilter':dict(dst_addr='^995',src_addr='^Brand$',priority='^[01]$',validity_period=r'^\d{1,3}$',content='^hello'),
        'defaultvalue':{'src_addr':'Brand'},
        'quota':dict(balance=100,early_percent=25,sms_count=123,http_throughput=5,smpps_throughput=6)},
        'smpps_cred':{'authorization':{'bind':False},'quota':{'max_bindings':2}}}
    assert edit(api,patch)[0]==200
    assert request(api,'state')[1]['users'][0]['credentials']==patch
    native=gateway.router.users['alice']
    assert native.mt_credential.getValueFilter('destination_address').match(b'995555')
    assert native.mt_credential.getAuthorization('set_source_address') is False
    assert native.mt_credential.getQuota('early_decrement_balance_percent')==25
    assert native.smpps_credential.getQuota('max_bindings')==2
    assert edit(api,{'mt_messaging_cred':{'defaultvalue':{'src_addr':None},'quota':{'balance':'ND','early_percent':None,'sms_count':''}},'smpps_cred':{'quota':{'max_bindings':None}}})[0]==200
    final=request(api,'state')[1]['users'][0]['credentials']
    assert final['mt_messaging_cred']['defaultvalue']['src_addr'] is None
    assert final['mt_messaging_cred']['quota']['sms_count'] is None
    assert final['smpps_cred']['quota']['max_bindings'] is None


@pytest.mark.parametrize('patch',[
 {'mt_messaging_cred':{'quota':{'early_percent':0}}},
 {'mt_messaging_cred':{'quota':{'early_percent':101}}},
 {'mt_messaging_cred':{'quota':{'sms_count':1.5}}},
 {'smpps_cred':{'quota':{'max_bindings':-1}}},
 {'mt_messaging_cred':{'quota':{'balance':'NaN'}}},
 {'mt_messaging_cred':{'authorization':{'http_send':'False'}}},
 {'mt_messaging_cred':{'authorization':{'http_send':False},'valuefilter':{'content':'['}}},
 {'mt_messaging_cred':{'quota':{'unknown':1}}},
])
def test_invalid_credential_patch_is_not_applied(patch):
    gateway,api=setup()
    before=request(api,'state')[1]['users'][0]
    assert edit(api,patch)[0]==400
    assert request(api,'state')[1]['users'][0]==before


def test_untouched_consumed_quotas_and_stale_permissions():
    gateway,api=setup()
    revision=request(api,'state')[1]['users'][0]['revision']
    gateway.router.users['alice'].mt_credential.updateQuota('balance',-2)
    assert edit(api,{'mt_messaging_cred':{'authorization':{'http_bulk':True}}},revision)[0]==200
    assert gateway.router.users['alice'].mt_credential.getQuota('balance')==40
    assert edit(api,{'smpps_cred':{'authorization':{'bind':False}}},revision)[0]==400
