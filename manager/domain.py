"""Translate validated web input into Jasmin's native management objects."""
from manager.credentials import credential_view, apply_credentials
import hashlib
import pickle
import math
import re
from jasmin.routing import Filters, Routes, Interceptors
from jasmin.routing.jasminApi import Group, User, SmppClientConnector, SmppServerSystemIdConnector, HttpConnector
from jasmin.protocols.smpp.configs import SMPPClientConfig
from jasmin.routing.jasminApi import MTInterceptorScript, MOInterceptorScript


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,16}', value):
        raise ValueError('IDs must contain 1–16 letters, numbers, underscores or hyphens.')
    return value


def number(value, integer=False):
    result = int(value) if integer else float(value)
    if not math.isfinite(result) or result < 0 or (integer and float(value) != result):
        raise ValueError('Enter a non-negative finite number.')
    return result


def make_user(data, groups):
    group = next((g for g in groups if g.gid == data['gid']), None)
    if group is None:
        raise ValueError('Select an existing group.')
    user = User(identifier(data['uid']), group, data['username'], data['password'])
    for key in ('balance', 'submit_sm_count', 'http_throughput', 'smpps_throughput'):
        value = data.get(key)
        if value not in (None, ''):
            user.mt_credential.setQuota(key, number(value, key == 'submit_sm_count'))
    return user


def make_connector(data):
    # SMPP C-Octet fields include a trailing NUL: system_id=16, password=9.
    # SMPPClientConfig alone does not enforce these on-wire limits.
    for key, label, maximum in (('username', 'SMPP system ID', 15), ('password', 'SMPP password', 8)):
        value = data[key]
        if not isinstance(value, str) or not value.isascii() or '\0' in value or len(value) > maximum:
            raise ValueError(f'{label} must be ASCII, contain no NUL, and be at most {maximum} characters.')
    port = number(data.get('port', 2775), True)
    if not 1 <= port <= 65535:
        raise ValueError('Port must be between 1 and 65535.')
    return SMPPClientConfig(id=identifier(data['id']), host=data['host'], port=port,
                            username=data['username'], password=data['password'],
                            bindOperation=data.get('bindOperation', 'transceiver'),
                            submit_sm_throughput=number(data.get('throughput', 10)))


def make_route(data, direction, users, groups, connector_ids, existing_filters=None):
    if direction not in ('mt', 'mo'):
        raise ValueError('Unknown routing direction.')
    order = number(data['order'], True)
    kind = data['type']
    if kind not in ('Default', 'Static', 'Failover', 'RandomRoundrobin'):
        raise ValueError('Unsupported route type.')
    if (kind == 'Default') != (order == 0):
        raise ValueError('Default routes require order 0; other routes require a positive order.')
    connectors = []
    for spec in data['connectors']:
        cid = identifier(spec['id'])
        if direction == 'mt':
            if cid not in connector_ids:
                raise ValueError(f'Unknown SMPP connector: {cid}')
            connectors.append(SmppClientConnector(cid))
        elif spec['type'] == 'http':
            connectors.append(HttpConnector(cid, spec['url'], spec.get('method', 'POST')))
        elif spec['type'] == 'smpps':
            connectors.append(SmppServerSystemIdConnector(cid))
        else:
            raise ValueError('MO destinations must be HTTP or SMPP server system IDs.')
    if not connectors or (kind in ('Static', 'Default') and len(connectors) != 1):
        raise ValueError('Select one destination for static/default routes, or a destination list for failover/random routes.')
    filters = make_filters(data.get('filters', []), direction, users, groups, connector_ids, existing_filters)
    rate = number(data.get('rate', 0)) if direction == 'mt' else 0.0
    if kind == 'Default':
        if filters:
            raise ValueError('Default routes cannot have filters.')
        route = Routes.DefaultRoute(connectors[0], rate)
    else:
        if not filters:
            raise ValueError('Add a filter; use Transparent to match all messages.')
        cls = getattr(Routes, kind + direction.upper() + 'Route')
        dest = connectors[0] if kind == 'Static' else connectors
        route = cls(filters, dest, rate) if direction == 'mt' else cls(filters, dest)
    return order, route


def user_view(user):
    return dict(credentials=credential_view(user), revision=user_revision(user), uid=user.uid, gid=user.group.gid, username=user.username, enabled=user.enabled,
                **{key: user.mt_credential.getQuota(key) for key in
                   ('balance', 'submit_sm_count', 'http_throughput', 'smpps_throughput')})


def route_view(order, route):
    destinations = route.connector if isinstance(route.connector, list) else [route.connector]
    return dict(order=order, type=type(route).__name__, rate=route.getRate(),
                connectors=[dict(id=c.cid, type=c._type, url=getattr(c, 'baseurl', None),
                                 method=getattr(c, 'method', None)) for c in destinations],
                filters=[str(f) for f in route.filters])


def make_filters(items, direction, users, groups, connector_ids, existing_filters=None):
    filters = []
    for item in items:
        key, value = item['type'], item.get('value', '')
        if key == 'Existing':
            original = (existing_filters or {}).get(value)
            if original is None or direction not in original.usedFor:
                raise ValueError('Existing filter is unavailable or incompatible. Refresh the gateway.')
            filters.append(pickle.loads(pickle.dumps(original)))
        elif key in ('SourceAddr', 'DestinationAddr', 'ShortMessage'):
            try:
                filters.append(getattr(Filters, key + 'Filter')(value))
            except re.error as error:
                raise ValueError('Invalid filter regular expression: '+str(error)) from None
        elif key == 'Transparent':
            filters.append(Filters.TransparentFilter())
        elif key == 'User' and direction == 'mt':
            obj = next((u for u in users if u.uid == value), None)
            if obj is None:
                raise ValueError('Unknown user filter ID.')
            filters.append(Filters.UserFilter(obj))
        elif key == 'Group' and direction == 'mt':
            obj = next((g for g in groups if g.gid == value), None)
            if obj is None:
                raise ValueError('Unknown group filter ID.')
            filters.append(Filters.GroupFilter(obj))
        elif key == 'Connector' and direction == 'mo' and value in connector_ids:
            filters.append(Filters.ConnectorFilter(SmppClientConnector(value)))
        else:
            raise ValueError('Invalid filter for this routing direction.')
    return filters


def interceptor_revision(interceptor):
    return hashlib.sha256(pickle.dumps(interceptor)).hexdigest()


def table_revision(table):
    values = [(order, interceptor_revision(item)) for row in table for order, item in row.items()]
    return hashlib.sha256(repr(sorted(values)).encode()).hexdigest()


def filter_view(item):
    kind = type(item).__name__.removesuffix('Filter')
    attrs = {'SourceAddr':'source_addr', 'DestinationAddr':'destination_addr', 'ShortMessage':'short_message'}
    if kind == 'Transparent': value = ''
    elif kind in attrs:
        value = getattr(item, attrs[kind]).pattern
        if isinstance(value, bytes): return None
    elif kind == 'User': value = item.user.uid
    elif kind == 'Group': value = item.group.gid
    elif kind == 'Connector': value = item.connector.cid
    else: return None
    return {'type':kind, 'value':value}


def interceptor_view(order, item):
    specs = [filter_view(f) for f in item.filters]
    return dict(order=order, type=type(item).__name__, script=item.script.pyCode,
                filters=[str(f) for f in item.filters], filter_specs=specs,
                editable_filters=all(f is not None for f in specs), revision=interceptor_revision(item))


def make_interceptor(data, direction, users, groups, connector_ids, existing=None, existing_filters=None):
    if direction not in ('mo', 'mt'): raise ValueError('Invalid interceptor direction.')
    order = number(data['order'], True)
    kind = data['type']
    if kind not in ('Default', 'Static'): raise ValueError('Unsupported interceptor type.')
    if (kind == 'Default') != (order == 0):
        raise ValueError('Default interceptors require order 0; static interceptors require a positive order.')
    source = data['script']
    if not isinstance(source, str) or not source.strip(): raise ValueError('Enter a Python script.')
    try:
        compile(source, '<interceptor>', 'exec')
    except (SyntaxError, ValueError) as error:
        raise ValueError(f'Invalid Python script: {error}') from None
    script = (MTInterceptorScript if direction == 'mt' else MOInterceptorScript)(source)
    if data.get('preserve_filters') is True:
        if existing is None: raise ValueError('No existing filters to preserve.')
        filters = existing.filters
    else:
        filters = make_filters(data.get('filters', []), direction, users, groups, connector_ids, existing_filters)
    if kind == 'Default':
        if filters: raise ValueError('Default interceptors cannot have filters.')
        item = Interceptors.DefaultInterceptor(script)
    else:
        if not filters: raise ValueError('Add a filter; use Transparent to match all messages.')
        item = getattr(Interceptors, 'Static'+direction.upper()+'Interceptor')(filters, script)
    return order, item


def user_revision(user):
    # Exclude traffic-consumed quotas but detect concurrent authorization/filter/limit edits.
    credentials = credential_view(user)
    for key in ('balance', 'sms_count'):
        credentials['mt_messaging_cred']['quota'].pop(key)
    return hashlib.sha256(pickle.dumps((user.uid, user.username, user.group.gid, user.password, user.enabled, credentials))).hexdigest()


def edit_user(existing, data, groups, users):
    import copy
    if data.get('revision') != user_revision(existing):
        raise ValueError('User changed. Refresh before editing.')
    if any(u.uid != existing.uid and u.username == data['username'] for u in users):
        raise ValueError('Username already exists.')
    group = next((g for g in groups if g.gid == data['gid']), None)
    if group is None: raise ValueError('Select an existing group.')
    check = User(existing.uid, group, data['username'], data.get('password') or None)
    result = copy.deepcopy(existing)
    result.username, result.group = check.username, group
    if data.get('password'): result.password = check.password
    apply_credentials(result, data.get('credentials', {}))
    return result


def edit_connector(existing, data):
    import copy
    if data.get('revision') != interceptor_revision(existing):
        raise ValueError('Connection changed. Refresh before editing.')
    values = dict(data, id=existing.id, password=data.get('password') or existing.password)
    checked = make_connector(values)
    result = copy.deepcopy(existing)
    for key in ('host','port','username','password','bindOperation','submit_sm_throughput'):
        setattr(result, key, getattr(checked, key))
    return result
