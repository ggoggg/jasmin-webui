"""PB operations run on the same Twisted reactor as the HTTP server."""
import os
import pickle
from twisted.internet import defer, reactor
from jasmin.routing.proxies import RouterPBProxy
from jasmin.managers.proxies import SMPPClientManagerPBProxy
from jasmin.routing.jasminApi import Group
from manager.domain import identifier, number, make_user, make_connector, make_route, user_view, route_view, make_interceptor, interceptor_view, interceptor_revision, table_revision, edit_user, edit_connector


def pb_authentication_enabled(prefix, settings=None):
    value = (os.environ if settings is None else settings).get(f'{prefix}_AUTHENTICATION', 'true').strip().lower()
    if value not in ('true', 'false'):
        raise ValueError(f'{prefix}_AUTHENTICATION must be true or false.')
    return value == 'true'


class Gateway:
    def __init__(self, demo=False, settings=None):
        self.settings = dict(os.environ if settings is None else settings)
        self.demo = demo
        self.lock = defer.DeferredLock()
        if demo:
            from manager.demo import DemoRouter, DemoSMPP
            self.router, self.smpp = DemoRouter(), DemoSMPP()

    @defer.inlineCallbacks
    def call(self, obj, method, *args):
        result = yield defer.maybeDeferred(getattr(obj, method), *args).addTimeout(12, reactor)
        if result is False:
            raise ValueError(f'Jasmin rejected {method}. Check the ID, dependencies and gateway logs.')
        return result

    def execute(self, method, path, data):
        return self.lock.run(self._execute, method, path, data)

    @defer.inlineCallbacks
    def _execute(self, method, path, data):
        router = self.router if self.demo else RouterPBProxy()
        smpp = self.smpp if self.demo else SMPPClientManagerPBProxy()
        try:
            if not self.demo:
                for proxy, prefix, port, username in ((router, 'ROUTER', 8988, 'radmin'), (smpp, 'SMPP', 8989, 'cmadmin')):
                    if pb_authentication_enabled(prefix, self.settings):
                        login = (self.settings.get(f'{prefix}_USERNAME', username), self.settings[f'{prefix}_PASSWORD'])
                    else:
                        login = (None, None)
                    yield self.call(proxy, 'connect', self.settings.get(f'{prefix}_HOST', '127.0.0.1'),
                                    int(self.settings.get(f'{prefix}_PORT', port)), *login)
            groups = pickle.loads((yield self.call(router, 'group_get_all')))
            users = pickle.loads((yield self.call(router, 'user_get_all')))
            connectors = yield self.call(smpp, 'connector_list')
            filter_pool = {}
            if path == ['state'] or (path and path[0] in ('routes', 'interceptors')):
                for direction in ('mt', 'mo'):
                    for family in ('route', 'interceptor'):
                        table = pickle.loads((yield self.call(router, direction + family + '_get_all')))
                        for row in table:
                            for item in row.values():
                                for f in item.filters: filter_pool[interceptor_revision(f)] = f
            if method == 'GET' and path == ['state']:
                routes = {}
                for direction in ('mt', 'mo'):
                    table = pickle.loads((yield self.call(router, direction + 'route_get_all')))
                    routes[direction] = [route_view(order, route) for row in table for order, route in row.items()]
                interceptors, interceptor_revisions = {}, {}
                for direction in ('mt', 'mo'):
                    table = pickle.loads((yield self.call(router, direction + 'interceptor_get_all')))
                    interceptors[direction] = [interceptor_view(order, item) for row in table for order, item in row.items()]
                    interceptor_revisions[direction] = table_revision(table)
                connector_views = []
                for item in connectors:
                    config = pickle.loads((yield self.call(smpp, 'connector_config', item['id'])))
                    connector_views.append(dict(revision=interceptor_revision(config), id=item['id'], host=config.host, port=config.port,
                        username=config.username, bindOperation=config.bindOperation,
                        throughput=config.submit_sm_throughput, session_state=item['session_state'],
                        service_status=item['service_status']))
                router_saved = yield defer.maybeDeferred(router.is_persisted).addTimeout(12, reactor)
                smpp_saved = yield defer.maybeDeferred(smpp.is_persisted).addTimeout(12, reactor)
                return dict(mode='demo' if self.demo else 'live', users=[user_view(u) for u in users],
                            groups=[dict(gid=g.gid, enabled=g.enabled) for g in groups],
                            filters=[dict(id=key, label=str(f), directions=f.usedFor) for key, f in filter_pool.items()],
                            connectors=connector_views, routes=routes, interceptors=interceptors, interceptor_revisions=interceptor_revisions, persisted=bool(router_saved and smpp_saved))
            if len(path) in (2, 3) and path[0] == 'interceptors' and path[1] in ('mt', 'mo'):
                direction = path[1]
                table = pickle.loads((yield self.call(router, direction + 'interceptor_get_all')))
                items = {order: item for row in table for order, item in row.items()}
                if method == 'POST' and len(path) == 2:
                    order, item = make_interceptor(data, direction, users, groups, [c['id'] for c in connectors], existing_filters=filter_pool)
                    if order in items: raise ValueError('Interceptor order already exists. Use Edit instead.')
                    yield self.call(router, direction + 'interceptor_add', item, order)
                elif method in ('POST', 'DELETE') and len(path) == 3:
                    order = number(path[2], True)
                    existing = items.get(order)
                    if existing is None: raise ValueError('Interceptor no longer exists. Refresh the gateway.')
                    if data.get('revision') != interceptor_revision(existing):
                        raise ValueError('Interceptor changed since it was loaded. Refresh before continuing.')
                    if method == 'DELETE':
                        yield self.call(router, direction + 'interceptor_remove', order)
                    else:
                        new_order, item = make_interceptor(data, direction, users, groups, [c['id'] for c in connectors], existing, existing_filters=filter_pool)
                        if new_order != order: raise ValueError('Order cannot be changed during an edit.')
                        yield self.call(router, direction + 'interceptor_add', item, order)
                elif method == 'DELETE' and len(path) == 2:
                    if data.get('revision') != table_revision(table):
                        raise ValueError('Interceptor table changed. Refresh before removing all interceptors.')
                    yield self.call(router, direction + 'interceptor_flush')
                else: raise ValueError('Unsupported interceptor operation.')
                return {'ok': True}
            if method == 'POST' and path == ['groups']:
                gid = identifier(data['gid'])
                if any(g.gid == gid for g in groups):
                    raise ValueError('Group ID already exists.')
                yield self.call(router, 'group_add', Group(gid))
            elif method == 'POST' and path == ['users']:
                if any(u.uid == data['uid'] or u.username == data['username'] for u in users):
                    raise ValueError('User ID or username already exists.')
                yield self.call(router, 'user_add', make_user(data, groups))
            elif method == 'POST' and path == ['connectors']:
                if any(c['id'] == data['id'] for c in connectors):
                    raise ValueError('Connector ID already exists.')
                yield self.call(smpp, 'add', make_connector(data))
            elif method == 'POST' and len(path) == 3 and path[2] == 'edit' and path[0] == 'users':
                existing = next((u for u in users if u.uid == path[1]), None)
                if existing is None: raise ValueError('User no longer exists.')
                yield self.call(router, 'user_add', edit_user(existing, data, groups, users))
            elif method == 'POST' and len(path) == 3 and path[2] == 'edit' and path[0] == 'connectors':
                details = next((c for c in connectors if c['id'] == path[1]), None)
                if details is None: raise ValueError('Connection no longer exists.')
                if details['service_status']: raise ValueError('Stop the connection before editing it.')
                original = pickle.loads((yield self.call(smpp, 'connector_config', path[1])))
                updated = edit_connector(original, data)
                # PB has no connector-update method. Keep the CID, queue and all unedited settings.
                yield self.call(smpp, 'remove', path[1])
                try:
                    yield self.call(smpp, 'add', updated)
                except Exception:
                    try:
                        current = yield self.call(smpp, 'connector_list')
                        if any(c['id'] == path[1] for c in current):
                            raise RuntimeError('Connection replacement outcome is uncertain. Refresh and inspect before retrying.')
                        yield self.call(smpp, 'add', original)
                    except Exception as error:
                        raise RuntimeError('Connection update failed; restoration could not be confirmed. Check the gateway before retrying.') from error
                    raise RuntimeError('Connection update failed. Original configuration restored; connection remains stopped.')
            elif method == 'POST' and len(path) == 3 and path[0] == 'connectors' and path[2] in ('start', 'stop'):
                yield self.call(smpp, path[2], path[1])
            elif method == 'POST' and len(path) == 3 and path[0] == 'users' and path[2] == 'quotas':
                if not any(u.uid == path[1] for u in users):
                    raise ValueError('Unknown user ID.')
                quotas = {}
                for key in ('balance', 'submit_sm_count', 'http_throughput', 'smpps_throughput'):
                    if key in data:
                        quotas[key] = None if data[key] in (None, '') else number(data[key], key == 'submit_sm_count')
                for key, value in quotas.items():
                    yield self.call(router, 'user_set_quota', path[1], 'mt_credential', key, value)
            elif method == 'POST' and len(path) == 3 and path[0] in ('users', 'groups') and path[2] in ('enable', 'disable'):
                yield self.call(router, path[0][:-1] + '_' + path[2], path[1])
            elif method == 'POST' and len(path) == 2 and path[0] == 'routes' and path[1] in ('mt', 'mo'):
                order, route = make_route(data, path[1], users, groups, [c['id'] for c in connectors], existing_filters=filter_pool)
                table = pickle.loads((yield self.call(router, path[1] + 'route_get_all')))
                if any(order in row for row in table):
                    raise ValueError('Route order already exists. Remove the existing route first.')
                yield self.call(router, path[1] + 'route_add', route, order)
            elif method == 'DELETE' and len(path) == 2 and path[0] in ('users', 'groups', 'connectors'):
                if path[0] == 'groups' and any(u.group.gid == path[1] for u in users):
                    raise ValueError('Remove users in this group first.')
                if path[0] in ('users', 'groups'):
                    table = pickle.loads((yield self.call(router, 'mtroute_get_all')))
                    table += pickle.loads((yield self.call(router, 'mtinterceptor_get_all')))
                    attr, key = ('user', 'uid') if path[0] == 'users' else ('group', 'gid')
                    for row in table:
                        for route in row.values():
                            if any(getattr(getattr(f, attr, None), key, None) == path[1] for f in route.filters):
                                raise ValueError('Remove MT routes or interceptors referencing this account first.')
                if path[0] == 'connectors':
                    for direction in ('mt', 'mo'):
                        table = pickle.loads((yield self.call(router, direction + 'route_get_all')))
                        table += pickle.loads((yield self.call(router, direction + 'interceptor_get_all')))
                        for row in table:
                            for route in row.values():
                                connector = getattr(route, 'connector', None)
                                destinations = connector if isinstance(connector, list) else [connector]
                                references = destinations + [getattr(f, 'connector', None) for f in route.filters]
                                if any(c is not None and c._type == 'smppc' and c.cid == path[1] for c in references):
                                    raise ValueError('Remove routes or interceptors referencing this connector first.')
                    yield self.call(smpp, 'remove', path[1])
                else:
                    yield self.call(router, path[0][:-1] + '_remove', path[1])
            elif method == 'DELETE' and len(path) == 3 and path[0] == 'routes' and path[1] in ('mt', 'mo'):
                yield self.call(router, path[1] + 'route_remove', int(path[2]))
            elif method == 'POST' and path == ['persist']:
                profile = identifier(data.get('profile', 'jcli-prod'))
                # These services persist separately; report partial completion explicitly.
                yield self.call(router, 'persist', profile)
                try:
                    yield self.call(smpp, 'persist', profile)
                except Exception as exc:
                    raise RuntimeError('Router saved, but SMPP configuration was not confirmed saved. Retry Save configuration.') from exc
            else:
                raise ValueError('Unknown management operation.')
            return {'ok': True}
        finally:
            if not self.demo:
                router.disconnect()
                smpp.disconnect()
