"""Ephemeral demo implementing the same proxy contract as Jasmin."""
import pickle
from jasmin.routing.jasminApi import Group


class DemoRouter:
    def __init__(self):
        self.groups = {}
        self.users = {}
        self.routes = {'mt': {}, 'mo': {}}
        self.interceptors = {'mt': {}, 'mo': {}}
        self.saved = True

    def group_get_all(self): return pickle.dumps(list(self.groups.values()))
    def user_get_all(self, gid=None): return pickle.dumps([u for u in self.users.values() if gid is None or u.group.gid == gid])
    def is_persisted(self): return self.saved
    def persist(self, profile, scope="all"):
        self.saved = True
        return True
    def group_add(self, group):
        self.groups[group.gid] = group
        self.saved = False
        return True
    def user_add(self, user):
        self.users[user.uid] = user
        self.saved = False
        return True
    def user_set_quota(self, uid, credential, quota, value):
        if uid not in self.users: return False
        getattr(self.users[uid], credential).setQuota(quota, value)
        self.saved = False
        return True
    def __getattr__(self, name):
        def operation(*args):
            self.saved = False if not name.endswith('get_all') else self.saved
            if name.startswith(('mtroute_', 'moroute_', 'mtinterceptor_', 'mointerceptor_')):
                table = (self.interceptors if 'interceptor' in name else self.routes)[name[:2]]
                action = name.split('_', 1)[1]
                if action == 'get_all': return pickle.dumps([{k: table[k]} for k in sorted(table, reverse=True)])
                if action == 'flush': table.clear(); return True
                if action == 'add': table[args[1]] = args[0]; return True
                if action == 'remove': return table.pop(args[0], None) is not None
            kind, action = name.split('_')
            table = self.users if kind == 'user' else self.groups
            obj = table.get(args[0])
            if obj is None: return False
            if action == 'remove': del table[args[0]]
            elif action in ('enable', 'disable'): obj.enabled = action == 'enable'
            else: raise AttributeError(name)
            return True
        return operation


class DemoSMPP:
    def __init__(self): self.configs, self.running, self.saved = {}, set(), True
    def is_persisted(self): return self.saved
    def persist(self, profile, scope="all"): self.saved = True; return True
    def add(self, config): self.configs[config.id] = config; self.saved = False; return True
    def connector_config(self, cid): return pickle.dumps(self.configs[cid])
    def connector_list(self):
        return [dict(id=cid, service_status=int(cid in self.running),
                     session_state='BOUND_TRX' if cid in self.running else 'NONE') for cid in self.configs]
    def start(self, cid):
        if cid not in self.configs: return False
        self.running.add(cid)
        self.saved = False
        return True
    def stop(self, cid, delQueues=False):
        if cid not in self.configs: return False
        self.running.discard(cid)
        self.saved = False
        return True
    def remove(self, cid):
        self.running.discard(cid)
        self.saved = False
        return self.configs.pop(cid, None) is not None
