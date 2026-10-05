"""jCli-compatible credential names, JSON views and validated partial updates."""
import re

MT_AUTH = {key:key for key in ('http_send','http_balance','http_rate','http_bulk','smpps_send','http_long_content')}
MT_AUTH.update(dlr_level='set_dlr_level', http_dlr_method='http_set_dlr_method', src_addr='set_source_address',
               priority='set_priority', validity_period='set_validity_period',
               schedule_delivery_time='set_schedule_delivery_time', hex_content='set_hex_content')
SCHEMA = {
    'mt_messaging_cred': ('mt_credential', {
        'authorization': MT_AUTH,
        'valuefilter': dict(dst_addr='destination_address',src_addr='source_address',priority='priority',validity_period='validity_period',content='content'),
        'defaultvalue': dict(src_addr='source_address'),
        'quota': dict(balance='balance',early_percent='early_decrement_balance_percent',sms_count='submit_sm_count',http_throughput='http_throughput',smpps_throughput='smpps_throughput'),
    }),
    'smpps_cred': ('smpps_credential', {'authorization': {'bind':'bind'}, 'quota': {'max_bindings':'max_bindings'}}),
}
GETTERS = {'authorization':'getAuthorization','valuefilter':'getValueFilter','defaultvalue':'getDefaultValue','quota':'getQuota'}


def credential_view(user):
    result = {}
    for name,(attribute,sections) in SCHEMA.items():
        credential = getattr(user, attribute)
        result[name] = {}
        for section,keys in sections.items():
            result[name][section] = {}
            for label,key in keys.items():
                value = getattr(credential, GETTERS[section])(key)
                if section == 'valuefilter': value = value.pattern
                if isinstance(value, bytes): value = value.decode('latin1')
                result[name][section][label] = value
    return result


def apply_credentials(user, patch):
    from manager.domain import number
    if not isinstance(patch, dict): raise ValueError('Credentials must be an object.')
    for name,sections in patch.items():
        if name not in SCHEMA or not isinstance(sections,dict): raise ValueError('Unknown credential group.')
        attribute,allowed = SCHEMA[name]
        credential = getattr(user, attribute)
        for section,values in sections.items():
            if section not in allowed or not isinstance(values,dict): raise ValueError('Unknown credential section.')
            for label,value in values.items():
                if label not in allowed[section]: raise ValueError('Unknown credential field: '+label)
                key = allowed[section][label]
                if section == 'authorization':
                    if not isinstance(value,bool): raise ValueError(label+' must be true or false.')
                    credential.setAuthorization(key,value)
                elif section == 'quota':
                    if value is None or (isinstance(value,str) and value.strip().lower() in ('','nd','none')): value=None
                    else:
                        if isinstance(value,bool): raise ValueError(label+' must be a number.')
                        value=number(value,label in ('sms_count','max_bindings'))
                    credential.setQuota(key,value)
                elif section == 'valuefilter':
                    if not isinstance(value,str): raise ValueError(label+' must be a regex string.')
                    previous=credential.getValueFilter(key)
                    try:
                        pattern=value.encode('latin1') if isinstance(previous.pattern,bytes) else value
                        credential.setValueFilter(key,re.compile(pattern,previous.flags))
                    except (re.error,UnicodeError,ValueError) as error:
                        raise ValueError('Invalid '+label+' regex: '+str(error)) from None
                elif section == 'defaultvalue':
                    if value is not None and not isinstance(value,str): raise ValueError(label+' must be text or null.')
                    if value == '': value=None
                    if value is not None and isinstance(credential.getDefaultValue(key),bytes):
                        value=value.encode('latin1')
                    credential.setDefaultValue(key,value)
