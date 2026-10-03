"""Exercise real PB authentication, serialization and calls against local test avatars."""
import os
import pickle
from zope.interface import implementer
from twisted.cred import portal, checkers
from twisted.spread import pb
from twisted.internet import defer, task
from manager.demo import DemoRouter, DemoSMPP
from manager.gateway import Gateway


class Avatar(pb.Avatar):
    def __init__(self, target): self.target=target
    def perspectiveMessageReceived(self, broker, message, args, kw):
        args=broker.unserialize(args)
        kw=broker.unserialize(kw)
        name=message.decode() if isinstance(message,bytes) else message
        if isinstance(self.target,DemoSMPP):
            name={'connector_add':'add','connector_remove':'remove','connector_start':'start','connector_stop':'stop'}.get(name,name)
        if name in ('group_add','user_add','mtroute_add','moroute_add','mtinterceptor_add','mointerceptor_add','add'):
            args=(pickle.loads(args[0]),*args[1:])
        return broker.serialize(getattr(self.target,name)(*args))


@implementer(portal.IRealm)
class Realm:
    def __init__(self,target):self.target=target
    def requestAvatar(self, avatarId, mind, *interfaces):
        return pb.IPerspective,Avatar(self.target),lambda:None


@defer.inlineCallbacks
def main(reactor):
    ports=[]
    try:
        for prefix,target,username in [('ROUTER',DemoRouter(),'radmin'),('SMPP',DemoSMPP(),'cmadmin')]:
            checker=checkers.InMemoryUsernamePasswordDatabaseDontUse()
            checker.addUser(username,b'secret')
            listener=reactor.listenTCP(0,pb.PBServerFactory(portal.Portal(Realm(target),[checker])),interface='127.0.0.1')
            ports.append(listener)
            os.environ[prefix+'_PORT']=str(listener.getHost().port)
            os.environ[prefix+'_PASSWORD']='secret'
        gateway=Gateway()
        yield gateway.execute('POST',['groups'],{'gid':'clients'})
        yield gateway.execute('POST',['users'],dict(uid='alice',gid='clients',username='alice',password='secret'))
        yield gateway.execute('POST',['connectors'],dict(id='carrier',host='localhost',username='client',password='secret'))
        yield gateway.execute('POST',['routes','mt'],dict(order=0,type='Default',connectors=[{'id':'carrier'}]))
        yield gateway.execute('POST',['interceptors','mt'],dict(order=0,type='Default',script='smpp_status = 0'))
        result=yield gateway.execute('GET',['state'],{})
        assert result['interceptors']['mt'][0]['script']=='smpp_status = 0'
        assert result['mode']=='live'
        assert result['users'][0]['uid']=='alice'
        assert result['connectors'][0]['id']=='carrier'
        assert result['routes']['mt'][0]['type']=='DefaultRoute'
        for prefix, target in [('ROUTER', DemoRouter()), ('SMPP', DemoSMPP())]:
            checker = checkers.AllowAnonymousAccess()
            listener = reactor.listenTCP(0, pb.PBServerFactory(portal.Portal(Realm(target), [checker])), interface='127.0.0.1')
            ports.append(listener)
            os.environ[prefix + '_PORT'] = str(listener.getHost().port)
            os.environ[prefix + '_AUTHENTICATION'] = 'false'
        anonymous = yield Gateway().execute('GET',['state'],{})
        assert anonymous['mode']=='live'
        print('PB integration passed: authenticated and anonymous access, native serialization, provisioning and snapshot.')
    finally:
        for listener in ports:yield listener.stopListening()


if __name__=='__main__':task.react(main)
